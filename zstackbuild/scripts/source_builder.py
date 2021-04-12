#!/usr/bin/python
import functools
import os
import socket
import subprocess
import sys
import tempfile
import time

import typing
import argparse
from pkg_resources import Requirement, Distribution
import threading
import simplejson


def info(msg):
    sys.stdout.write('INFO: %s\n' % msg)
    sys.stdout.flush()


def warning(msg):
    sys.stdout.write('WARNING: %s\n' % msg)
    sys.stdout.flush()


def error(msg):
    sys.stderr.write('\n\nERROR: %s\n' % msg)
    sys.stderr.flush()
    sys.exit(1)


class TimeoutError(Exception):
    def __init__(self, timeout, cause=None):
        self.timeout = timeout
        self.cause = cause

    def __str__(self):
        if not self.cause:
            return 'timeout after %s seconds' % self.timeout
        else:
            return 'timeout after %s seconds, %s' % (self.timeout, self.cause)


class MissingShellCommand(Exception):
    pass


class BashError(Exception):
    def __init__(self, msg, cmd, retcode, stdout, stderr, work_dir=None):
        self.msg = msg
        self.cmd = cmd
        self.retcode = retcode
        self.stdout = stdout
        self.stderr = stderr
        if work_dir is None:
            self.work_dir = os.getcwd()
        else:
            self.work_dir = work_dir

    def __str__(self):
        return 'shell command failure. %s. details [command: %s, retcode:%s, stdout:%s, stderr: %s, workdir:%s]' % \
               (self.msg, self.cmd, self.retcode, self.stdout, self.stderr, self.work_dir)


def _merge_shell_stdout_stderr(stdout, stderr):
    # type: (str, str) -> str

    lst = []
    if stdout.strip('\t\n\r ') != '':
        lst.append(stdout)
    if stderr.strip('\t\n\r ') != '':
        lst.append(stderr)

    return ','.join(lst)


def run(command, work_dir=None):
    # type: (str, str) -> (int, str, str)

    p = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         cwd=work_dir,
                         close_fds=True,
                         env=os.environ)
    o, e = p.communicate()
    return p.returncode, str(o), str(e)


def call(command, success_code=0, work_dir=None):
    # type: (str, int, str) -> str

    r, o, e = run(command, work_dir=work_dir)

    if r != success_code:
        raise BashError(msg='command[%s] failed', cmd=command, retcode=r, stdout=o, stderr=e)

    return o


def call_with_screen_output(cmd, ret_code=0, raise_error=True, work_dir=None):
    # type: (str, typing.Union[int, list], bool, str) -> int

    if work_dir is None:
        print('[BASH]: %s' % cmd)
    else:
        print('[BASH (%s) ]: %s' % (work_dir, cmd))

    p = subprocess.Popen(cmd, shell=True, stdout=sys.stdout,
                         stdin=subprocess.PIPE, stderr=sys.stderr,
                         cwd=work_dir,
                         env=os.environ,
                         close_fds=True)
    r = p.wait()
    if raise_error:
        is_err = False
        if isinstance(ret_code, int) and ret_code != r:
            is_err = True
        elif isinstance(ret_code, list) and r not in ret_code:
            is_err = True

        if is_err:
            raise BashError(msg='command[%s] failed' % cmd, cmd=cmd, retcode=r, stdout='', stderr='')

    return r


def run_with_command_check(command, work_dir=None):
    # type: (str, str) -> (int, str, str)

    r, o, e = run(command, work_dir=work_dir)
    if r == 127:
        raise MissingShellCommand('command[%s] not found in target system, %s' % (command, _merge_shell_stdout_stderr(o, e)))

    return r, o, e


def run_with_err_msg(command, err_msg, work_dir=None):
    # type: (str, str, str) -> str

    r, o, e = run_with_command_check(command, work_dir=work_dir)

    if r != 0:
        raise BashError(msg=err_msg, cmd=command, retcode=r, stdout=o, stderr=e)

    return o


def retry(time_out=5, check_interval=1):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            expired = time.time() + time_out
            while True:
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if time.time() < expired:
                        time.sleep(check_interval)
                    else:
                        raise TimeoutError(time_out, e)

        return inner
    return wrap


class Builder(object):
    PYPI_DIR = 'zstackbuild/pypi_source/pypi'
    PYPI_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'
    REQUIREMENTS_TXT = 'zstackbuild/pypi_source/requirements.txt'
    EXCLUDES = ['bm-instance-agent']

    def __init__(self):
        self.sub_projects = []
        self.existing_packages = []
        self.requirements = {}

        parser = argparse.ArgumentParser(description='Build pypi repo')
        sub_parser = parser.add_subparsers(help='sub-command help', dest="sub_command_name")
        sp = sub_parser.add_parser(name='print', help='only print packages being required')
        sp.add_argument('--exclude', '-e', action='append', dest='excludes', default=[], help='[Support Multiple] sub projects to be excluded from scan, e.g. -e bm-instance-agent')

        sp = sub_parser.add_parser(name='build', help='only print packages being required')
        sp.add_argument('--dry-run', '-d', action='store_true', dest='dry', default=False, help='only print modification information instead of do the real build')
        sp.add_argument('--exclude', '-e', action='append', dest='excludes', default=[], help='[Support Multiple] sub projects to be excluded from scan, e.g. -e bm-instance-agent')

        sp = sub_parser.add_parser(name='verify', help='verify the pipy repo through a virtualenv')
        sp.add_argument('--exclude', '-e', action='append', dest='excludes', default=[], help='[Support Multiple] sub projects to be excluded from scan, e.g. -e bm-instance-agent')

        sp = sub_parser.add_parser(name='deps', help='show dependencies of project requirements')
        sp.add_argument('--exclude', '-e', action='append', dest='excludes', default=[], help='[Support Multiple] sub projects to be excluded from scan, e.g. -e bm-instance-agent')
        sp.add_argument('--json', '-j', dest='json', default=None, help='the path of file where to output the json result, default is pypi_deps.json in current directory')

        self.args, _ = parser.parse_known_args()
        self.command = self.args.sub_command_name

        self.packages_to_add = {}

    def _scan_setup_py(self):
        excludes = set()
        excludes.update(self.EXCLUDES)
        excludes.update(self.args.excludes)

        for d in os.listdir('.'):
            if d in excludes:
                info('exclude project[%s]' % d)
                continue

            setup_py_path = os.path.join(d, 'setup.py')
            if not os.path.isfile(setup_py_path):
                continue

            self.sub_projects.append((d, setup_py_path))

    def _get_project_requires(self, setup_py):
        tmp_dir = tempfile.mkdtemp()

        def cleanup():
            call('rm -rf %s' % tmp_dir)

        setup_py_dir = os.path.dirname(setup_py)
        cmd = 'python setup.py egg_info -e %s' % tmp_dir
        r, o, e = run(cmd, work_dir=setup_py_dir)
        err = _merge_shell_stdout_stderr(o, e)
        if r != 0 and 'invalid command' in err and 'egg_info' in err:
            # the package not supporting egg_info which means no dependencies
            cleanup()
            return []
        elif r != 0:
            cleanup()
            raise BashError(
                msg='cannot get requirements from %s' % setup_py,
                cmd=cmd,
                retcode=r,
                stdout=o,
                stderr=e,
                work_dir=setup_py_dir
            )

        dirs = os.listdir(tmp_dir)
        assert len(dirs) == 1, '%s contains more than one folder: %s' % (tmp_dir, os.listdir(tmp_dir))
        try:
            requires_file = os.path.join(tmp_dir, dirs[0], 'requires.txt')
            if not os.path.isfile(requires_file):
                return []

            with open(requires_file, 'r') as fd:
                reqs = fd.read().split('\n')
                return [r.strip(' \t\r') for r in reqs if r.strip(' \t\r')]
        finally:
            cleanup()

    def _collect_requirements(self, project_name, requires):
        for r in requires:
            reqs = self.requirements.get(project_name, [])
            reqs.append(Requirement.parse(r))
            self.requirements[project_name] = reqs

    def _generate_existing_package_distribution(self):
        for root, _, files in os.walk(self.PYPI_DIR):
            for f in files:
                if f.endswith('.tar.gz') or f.endswith('.zip'):
                    egg = f.replace('tar.gz', 'egg').replace('zip', 'egg')
                    self.existing_packages.append((Distribution.from_filename(egg), os.path.join(root, f)))

    def _calculate_modifications(self):
        def is_req_to_add(req):
            for ep in self.existing_packages:
                distro, _ = ep
                if distro in req:
                    return False

            return True

        for project_name, reqs in self.requirements.items():
            to_add = []

            for req in reqs:
                if is_req_to_add(req):
                    to_add.append(req)

            self.packages_to_add[project_name] = to_add

    def _collect_system_requirements(self):
        if not os.path.isfile(self.REQUIREMENTS_TXT):
            info('%s not found, skip collecting system requirements' % self.REQUIREMENTS_TXT)
            return

        with open(self.REQUIREMENTS_TXT, 'r') as fd:
            reqs = fd.readlines()

        project_name = 'system-requirements'

        for r in reqs:
            lst = self.requirements.get(project_name, [])
            lst.append(Requirement.parse(r))
            self.requirements[project_name] = lst

    def _print_requirements(self):
        print('Below are packages required by projects:')
        for project_name, reqs in self.requirements.items():
            print('%s:\n' % project_name)
            if not reqs:
                print('\tNone\n')
            else:
                req_names = ['\t%s' % r for r in reqs]
                print('%s\n' % '\n'.join(req_names))

    def _check_requirements(self):
        errors = {}
        for project_name, reqs in self.requirements.items():
            for r in reqs:
                if not r.specs:
                    lst = errors.get(project_name, [])
                    lst.append(r)
                    errors[project_name] = lst

        if errors:
            sys.stdout.write('\n\nERROR: below project containing requirements not specifying package version:\n\n')

            for project_name, reqs in errors.items():
                print('%s:\n' % project_name)
                req_names = ['\t%s' % r for r in reqs]
                print('%s\n' % '\n'.join(req_names))

            sys.exit(1)

    def _verify(self):
        def start_http_server():
            import psutil

            for p in psutil.process_iter():
                cmdline = p.cmdline()
                if 'python' in cmdline and 'SimpleHTTPServer' in cmdline and '18008'in cmdline:
                    call_with_screen_output('kill -9 %s' % p.pid)

            t = threading.Thread(target=lambda : call('python -m SimpleHTTPServer 18008', work_dir=self.PYPI_DIR))
            t.setDaemon(True)
            t.start()

        @retry(time_out=5)
        def wait_for_http_server():
            so = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            so.settimeout(1)  # 1s
            so.connect(("127.0.0.1", 18008))

        self._collect_requirements_of_projects()
        start_http_server()
        wait_for_http_server()

        tmp_dir = tempfile.mkdtemp()

        def cleanup():
            call_with_screen_output('rm -rf %s' % tmp_dir)

        call_with_screen_output('virtualenv pypi_verify', work_dir=tmp_dir)
        venv_dir = os.path.join(tmp_dir, 'pypi_verify')
        activate_bin_path = os.path.join(venv_dir, 'bin/activate')

        for project_name, reqs in self.requirements.items():
            info('Verifying requirements in project: %s' % project_name)
            for r in reqs:
                ret = call_with_screen_output('source %s && pip install "%s" -i http://127.0.0.1:18008/simple && deactivate' % (activate_bin_path, r), raise_error=False)
                if ret != 0:
                    cleanup()
                    error('failed to install requirement[%s] for project[%s]' % (r, project_name))

        cleanup()
        info('\n\n\nAll requirements verified successfully')

    def run(self):
        if not os.path.isdir(self.PYPI_DIR):
            raise Exception('%s not found. You must run this script in root folder of zstack-utiltiy' % self.PYPI_DIR)

        self._check_tools()

        if self.command == 'build':
            self._build()
        elif self.command == 'print':
            self._print()
        elif self.command == 'verify':
            self._verify()
        elif self.command == 'deps':
            self._deps()

    def _collect_requirements_of_projects(self):
        self._scan_setup_py()

        for project_name, setup_py in self.sub_projects:
            info('collecting requirements ...')
            requires = self._get_project_requires(setup_py)
            self._collect_requirements(project_name, requires)

        self._collect_system_requirements()
        self._check_requirements()

    def _print(self):
        self._collect_requirements_of_projects()
        self._print_requirements()

    def _build(self):
        self._collect_requirements_of_projects()
        self._generate_existing_package_distribution()
        self._calculate_modifications()

        if self.args.dry:
            self._print_modification_information()
        else:
            self._do_download()

    def _print_modification_information(self):
        print('Below are packages to be added')
        for project_name, reqs in self.packages_to_add.items():
            print('%s:\n' % project_name)
            if not reqs:
                print('\tNone\n')
            else:
                req_names = ['\t%s' % r for r in reqs]
                print('%s\n' % '\n'.join(req_names))

    def _do_download(self):
        downloads = set()

        for project_name, reqs in self.packages_to_add.items():
            info('Downloading requirements for project: %s' % project_name)

            req_names = [str(r) for r in reqs]
            downloads.update(req_names)
            fd, req_file = tempfile.mkstemp()
            os.write(fd, '\n'.join(req_names))
            os.close(fd)
            call_with_screen_output('pip2pi %s --index-url %s -r %s --no-binary=:all:' % (self.PYPI_DIR, self.PYPI_URL, req_file))
            os.remove(req_file)

        req_names = ['\t%s' % r for r in downloads]
        info('SUCCESSFULLY download all requirements:\n\n%s' % '\n'.join(req_names))

    def _check_tools(self):
        r, _, _ = run('which pip')
        if r != 0:
            raise Exception('pip not installed')

        r, _, _ = run('which pip2pi')
        if r != 0:
            call_with_screen_output('pip install -i %s pip2pi' % self.PYPI_URL)

        try:
            import psutil
        except ImportError:
            call_with_screen_output('pip install -i %s psutil' % self.PYPI_URL)

    def _deps(self):
        self._collect_requirements_of_projects()
        self._generate_existing_package_distribution()

        def find_tgz(req):
            for ep in self.existing_packages:
                distro, path = ep
                if distro in req:
                    return path

            return None

        def find_setup_py(folder):
            for root, _, files in os.walk(folder):
                for f in files:
                    if f == 'setup.py':
                        return os.path.join(root, f)

            return None

        result = {}
        for project_name, reqs in self.requirements.items():
            for r in reqs:
                tgz_path = find_tgz(r)
                if tgz_path is None:
                    error('unable to find any package in %s satisfying %s for project[%s], you may need to run "source_builder build" first' % (self.PYPI_DIR, r, project_name))

                tmp_dir = tempfile.mkdtemp()

                def cleanup():
                    call('rm -rf %s' % tmp_dir)
                    pass

                info('collecting dependencies[project:%s, requirement:%s] ...' % (project_name, r))
                if tgz_path.endswith('.zip'):
                    call('unzip %s -d %s' % (tgz_path, tmp_dir))
                else:
                    call('tar xzf %s -C %s' % (tgz_path, tmp_dir))

                setup_py = find_setup_py(tmp_dir)
                if setup_py is None:
                    cleanup()
                    error('no setup.py found in package[%s], is it broken?' % tgz_path)

                requires = self._get_project_requires(setup_py)

                req_dict = result.get(project_name, {})
                req_dict[str(r)] = requires
                result[project_name] = req_dict
                cleanup()

        print('\n\nDependencies are dumped as below:\n\n')
        for project_name, req_dict in result.items():
            print('%s:\n' % project_name)
            if not req_dict:
                print('\tNone\n')
            else:
                for req_name, deps in req_dict.items():
                    print('\t%s\n' % req_name)
                    dep_names = ['\t\t%s' % r for r in deps]
                    print('%s\n' % '\n'.join(dep_names))

        if self.args.json is not None:
            result_json = self.args.json
            dir_name = os.path.dirname(result_json)
            if not os.path.isdir(dir_name):
                os.makedirs(dir_name)
        else:
            result_json = 'pypi_deps.json'

        with open(result_json, 'w+') as fd:
            fd.write(simplejson.dumps(result, ensure_ascii=True, sort_keys=True, indent=4))

        info('\n\n results is written into %s' % result_json)


def main():
    Builder().run()


if __name__ == '__main__':
    main()



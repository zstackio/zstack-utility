#!/usr/bin/python

import os
import subprocess
import sys
import tempfile

import typing
import argparse
from pkg_resources import Requirement, Distribution


def info(msg):
    sys.stdout.write('INFO: %s\n' % msg)


def warning(msg):
    sys.stdout.write('WARNING: %s\n' % msg)


class MissingShellCommand(Exception):
    pass


class BashError(Exception):
    def __init__(self, msg, cmd, retcode, stdout, stderr):
        self.msg = msg
        self.cmd = cmd
        self.retcode = retcode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return 'shell command failure. %s. details [command: %s, retcode:%s, stdout:%s, stderr: %s]' % \
               (self.msg, self.cmd, self.retcode, self.stdout, self.stderr)


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
    # type: (str, typing.Union[int, list], bool, str) -> None

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


class Builder(object):
    PYPI_DIR = 'zstackbuild/pypi_source/pypi/simple'
    PYPI_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'
    EXCLUDES = ['bm-instance-agent']

    def __init__(self):
        self.sub_projects = []
        self.existing_packages = []
        self.requirements = {}

        parser = argparse.ArgumentParser(description='Build pypi repo')
        parser.add_argument('--dry-run', '-d', action='store_true', dest='dry', default=False, help='only print modification information instead of do the real build')
        parser.add_argument('--exclude', '-e', action='append', dest='excludes', default=[], help='[Support Multiple] sub projects to be excluded from scan, e.g. -e bm-instance-agent')

        self.args = parser.parse_args()

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
        info('collecting requirements ...')

        tmp_dir = tempfile.mkdtemp()
        call('python %s egg_info -e %s' % (setup_py, tmp_dir))
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
            call('rm -rf %s' % tmp_dir)

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
                    self.existing_packages.append(Distribution.from_filename(egg))

    def _calculate_modifications(self):
        def is_req_to_add(req):
            for distro in self.existing_packages:
                if distro in req:
                    return False

            return True

        for project_name, reqs in self.requirements.items():
            to_add = []

            for req in reqs:
                if is_req_to_add(req):
                    to_add.append(req)

            self.packages_to_add[project_name] = to_add

    def build(self):
        if not os.path.isdir(self.PYPI_DIR):
            raise Exception('%s not found. You must run this script in root folder of zstack-utiltiy' % self.PYPI_DIR)

        self._check_tools()
        self._scan_setup_py()
        self._generate_existing_package_distribution()

        for project_name, setup_py in self.sub_projects:
            requires = self._get_project_requires(setup_py)
            self._collect_requirements(project_name, requires)

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
        for reqs in self.packages_to_add.values():
            downloads.update(reqs)

        if not downloads:
            info('\n\nNO package needs to be added')
            return

        req_names = [str(r) for r in downloads]
        fd, req_file = tempfile.mkstemp()
        os.write(fd, '\n'.join(req_names))
        os.close(fd)
        pkg_dir = os.path.dirname(self.PYPI_DIR)
        call_with_screen_output('pip2tgz %s --index-url %s -r %s --no-binary=:all:' % (pkg_dir, self.PYPI_URL, req_file))
        call_with_screen_output('dir2pi %s' % pkg_dir)
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


def main():
    Builder().build()


if __name__ == '__main__':
    main()



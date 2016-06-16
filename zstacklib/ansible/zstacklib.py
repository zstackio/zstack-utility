#!/usr/bin/env python
# encoding: utf-8
import ansible.runner
import ansible.constants
import os
import sys
import urllib2
from urllib2 import URLError
from datetime import datetime
import logging
import json
from logging.handlers import TimedRotatingFileHandler
import time
import functools
import jinja2
import commands

# set global default value
start_time = datetime.now()
logger = logging.getLogger("deploy-agent-Log")
pip_url = ""
zstack_root = ""
host = ""
pkg_zstacklib = ""
yum_server = ""
trusted_host = ""
ansible.constants.HOST_KEY_CHECKING = False


class AgentInstallArg(object):
    def __init__(self, trusted_host, pip_url, virtenv_path, init_install):
        self.trusted_host = trusted_host
        self.pip_url = pip_url
        self.virtenv_path = virtenv_path
        self.init_install = init_install
        self.agent_name = None
        self.agent_root = None
        self.pkg_name = None
        self.virtualenv_site_packages = None


class ZstackLibArgs(object):
    def __init__(self):
        self.zstack_repo = None
        self.yum_server = None
        self.distro = None
        self.distro_version = None
        self.distro_release = None
        self.zstack_root = None
        self.host_post_info = None
        self.pip_url = None


class Msg(object):
    def ___init__(self):
        self.level = None
        self.label = None
        self.parameters = None
        self.details = None


class AnsibleStartResult(object):
    def __init__(self):
        self.result = None
        self.post_url = None
        self.host = None


class HostPostInfo(object):
    def __init__(self):
        self.trusted_host = None
        self.remote_user = 'root'
        self.remote_pass = None
        self.remote_port = None
        self.become = False
        self.become_exe = '/usr/bin/sudo'
        self.become_user = 'root'
        self.private_key = None
        self.host_inventory = None
        self.host = None
        self.vip= None
        self.post_url = ""
        self.post_label = None
        self.post_label_param = None
        self.start_time = None
        self.rabbit_password = None
        self.mysql_password = None
        self.mysql_userpassword = None
        self.transport = 'smart'


class PipInstallArg(object):
    def __init__(self):
        self.name = None
        self.extra_args = None
        self.version = None
        self.virtualenv = None
        self.virtualenv_site_packages = None


class CopyArg(object):
    def __init__(self):
        self.src = None
        self.dest = None
        self.args = None


class FetchArg(object):
    def __init__(self):
        self.src = None
        self.dest = None
        self.args = None


class UnarchiveArg(object):
    def __init__(self):
        self.src = None
        self.dest = None
        self.args = None


class ZstackRunnerArg(object):
    def  __init__(self):
        self.host_post_info = None
        self.module_name = None
        self.module_args = None


class ZstackRunner(object):
    def __init__(self, runner_args):
        self.host_inventory = runner_args.host_post_info.host_inventory
        self.private_key = runner_args.host_post_info.private_key
        self.host = runner_args.host_post_info.host
        self.post_url = runner_args.host_post_info.post_url
        self.pattern = runner_args.host_post_info.host
        self.module_name = runner_args.module_name
        self.module_args = runner_args.module_args
        self.remote_port = runner_args.host_post_info.remote_port
        self.remote_user = runner_args.host_post_info.remote_user
        self.remote_pass = runner_args.host_post_info.remote_pass
        self.become = runner_args.host_post_info.become
        self.become_user = runner_args.host_post_info.become_user
        self.become_pass = runner_args.host_post_info.remote_pass
        self.transport = runner_args.host_post_info.transport

    def run(self):
        runner = ansible.runner.Runner(
            transport=self.transport,
            host_list=self.host_inventory,
            private_key_file=self.private_key,
            module_name=self.module_name,
            module_args=self.module_args,
            pattern=self.host,
            remote_port=self.remote_port,
            remote_user=self.remote_user,
            remote_pass=self.remote_pass,
            become = self.become,
            become_user=self.become_user,
            become_pass=self.become_pass
        )
        result = runner.run()
        return  result

def error(msg):
    logger.error(msg)
    sys.stderr.write('ERROR: %s\n' % msg)
    sys.exit(1)

def retry(times=3, sleep_time=3):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            for i in range(0, times):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    logger.error(e)
                    time.sleep(sleep_time)
            error("The task failed, please make sure the host can be connected and no error happened, then try again. "
                  "Below is detail:\n %s" % e)
        return inner
    return wrap


def create_log(logger_dir):
    if not os.path.exists(logger_dir):
        os.makedirs(logger_dir)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler = logging.handlers.RotatingFileHandler(logger_dir + "/deploy.log", maxBytes=1 * 1024 * 1024,
                                                   backupCount=10)
    handler.setFormatter(fmt)
    logger.addHandler(handler)


def post_msg(msg, post_url):
    '''post message to zstack, label for support i18n'''
    if msg.parameters is not None:
        data = json.dumps({"label": msg.label, "level": msg.level, "parameters": msg.parameters})
    else:
        data = json.dumps({"label": msg.label ,"level": msg.level})
    if post_url == "":
        logger.info("Warning: no post_url defined by user")
        return 0
    if msg.label is not None:
        try:
            headers = {"content-type": "application/json"}
            req = urllib2.Request(post_url, data, headers)
            response = urllib2.urlopen(req)
            response.close()
        except URLError, e:
            logger.debug(e.reason)
            error("Please check the post_url: %s and check the server status" % post_url)
    else:
        logger.warn("No label defined for message")
    # This output will capture by management log for debug
    if msg.level == "ERROR":
        error(msg.details)
    elif msg.level == "WARNING":
        logger.warn(msg.details)
    else:
        logger.info(msg.details)


def handle_ansible_start(ansible_start):
    msg = Msg()
    msg.details = "Can't start ansible process to host: %s Detail: %s  \n" % (ansible_start.host,
                                                                                ansible_start.result)
    msg.label = "ansible.start.error"
    msg.level = "ERROR"
    msg.parameters = [host]
    post_msg(msg, ansible_start.post_url)


def handle_ansible_failed(description, result, host_post_info):
    msg = Msg()
    host = host_post_info.host
    post_url = host_post_info.post_url
    start_time = host_post_info.start_time
    end_time = datetime.now()
    # Fix python2.6 compatible issue: no total_seconds() attribute for timedelta
    td = end_time - start_time
    cost_time = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / 10 ** 6.0 * 1000
    msg.label = host_post_info.post_label
    msg.parameters = host_post_info.post_label_param
    if 'stderr' in result['contacted'][host]:
        msg.details = "[ HOST: %s ] " % host_post_info.host + description + "error: " + result['contacted'][host]['stderr']
    elif 'msg' in result['contacted'][host]:
        msg.details = "[ HOST: %s ] " % host_post_info.host + description + "error: " + result['contacted'][host]['msg']
    msg.level = "ERROR"
    post_msg(msg, post_url)


def handle_ansible_info(details, host_post_info, level):
    msg = Msg()
    post_url = host_post_info.post_url
    start_time = host_post_info.start_time
    end_time = datetime.now()
    # Fix python2.6 compatible issue: no total_seconds() attribute for timedelta
    td = end_time - start_time
    cost_time = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / 10 ** 6.0 * 1000
    if "SUCC" in details:
        msg.details = "[ HOST: %s ] " % host_post_info.host + details + " [ cost %sms to finish ]" % int(cost_time)
    else:
        msg.details = "[ HOST: %s ] " % host_post_info.host + details
    msg.level = level
    msg.label = host_post_info.post_label
    msg.parameters = host_post_info.post_label_param
    post_msg(msg, post_url)


def agent_install(install_arg, host_post_info):
    host_post_info.post_label = "ansible.install.agent"
    host_post_info.post_label_param = [install_arg.agent_name]
    handle_ansible_info("INFO: Start to install %s ......" % install_arg.agent_name, host_post_info, "INFO")
    pip_install_arg = PipInstallArg()
    pip_install_arg.extra_args = "\"--trusted-host %s -i %s\"" % (install_arg.trusted_host, install_arg.pip_url)
    # upgrade only
    if install_arg.init_install is False:
        host_post_info.post_label = "ansible.upgrade.agent"
        handle_ansible_info("INFO: Only need to upgrade %s ......" % install_arg.agent_name, host_post_info,
                            "INFO")
        pip_install_arg.extra_args = "\"--trusted-host %s -i %s -U \"" % (install_arg.trusted_host, install_arg.pip_url)

    pip_install_arg.name = "%s/%s" % (install_arg.agent_root, install_arg.pkg_name)
    pip_install_arg.virtualenv = install_arg.virtenv_path
    pip_install_arg.virtualenv_site_packages = install_arg.virtualenv_site_packages
    if pip_install_package(pip_install_arg, host_post_info) is False:
        command = "rm -rf %s && rm -rf %s" % (install_arg.virtenv_path, install_arg.agent_root)
        run_remote_command(command, host_post_info)
        error("agent %s install failed" % install_arg.agent_name)


def yum_enable_repo(name, enablerepo, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.yum.enable.repo"
    host_post_info.post_label_param = name
    handle_ansible_info("INFO: Starting enable yum repo %s ... " % name, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'yum'
    runner_args.module_args = 'name=' + name + ' enablerepo=' + enablerepo + " state=present"
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: Enable yum repo failed"
            host_post_info.post_label = "ansible.yum.enable.repo.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: yum enable repo %s " % enablerepo
            host_post_info.post_label = "ansible.yum.enable.repo.succ"
            host_post_info.post_label_param = enablerepo
            handle_ansible_info(details, host_post_info, "INFO")
            return True


@retry(times=3, sleep_time=3)
def yum_check_package(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.yum.search.pkg"
    host_post_info.post_label_param = name
    handle_ansible_info("INFO: Searching yum package %s ... " % name, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = 'rpm -q %s ' % name,
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'rc' not in result['contacted'][host]:
            logger.warning("Maybe network problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['rc']
            if status == 0:
                details = "SUCC: The package %s exist in system" % name
                host_post_info.post_label = "ansible.yum.search.pkg.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                details = "SUCC: The package %s not exist in system" % name
                host_post_info.post_label = "ansible.yum.search.pkg.fail"
                handle_ansible_info(details, host_post_info, "INFO")
                return False

@retry(times=3, sleep_time=3)
def script(file, host_post_info, script_arg=None):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.script.run"
    host_post_info.post_label_param = [file, host]
    handle_ansible_info("INFO: Running script %s on host %s ... " % (file,host), host_post_info, "INFO")
    if script_arg is not None:
        args = file + " " + script_arg
    else:
        args = file
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'script'
    runner_args.module_args = args
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'rc' not in result['contacted'][host]:
            logger.warning("Network problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['rc']
            if status == 0:
                details = "SUCC: The script %s on host %s finish " % (file, host)
                host_post_info.post_label = "ansible.script.run.succ"
                host_post_info.post_label_param = file
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                description = "ERROR: The script %s failed on host %s" % (file, host)
                host_post_info.post_label = "ansible.script.run.fail"
                host_post_info.post_label_param = file
                handle_ansible_failed(description, result, host_post_info)


@retry(times=3, sleep_time=3)
def yum_install_package(name, host_post_info, ignore_error=False, force_install=False):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.yum.start.install.package"
    host_post_info.post_label_param = name
    handle_ansible_info("INFO: Starting yum install package %s ... " % name, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = "rpm -q %s" % name
    runner_args.name = name
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'rc' not in result['contacted'][host]:
            logger.warning("Network problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['rc']
            if status == 0 and not force_install:
                details = "SKIP: The package %s exist in system" % name
                host_post_info.post_label = "ansible.skip.install.pkg"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                details = "INFO: Yum installing package %s ..." % name
                host_post_info.post_label = "ansible.yum.install.pkg"
                handle_ansible_info(details, host_post_info, "INFO")
                runner_args = ZstackRunnerArg()
                runner_args.host_post_info = host_post_info
                runner_args.module_name = 'yum'
                runner_args.module_args = 'name=' + name + ' disable_gpg_check=yes state=latest'
                zstack_runner = ZstackRunner(runner_args)
                result = zstack_runner.run()
                logger.debug(result)
                if 'failed' in result['contacted'][host] and not ignore_error:
                    description = "ERROR: YUM install package %s failed" % name
                    host_post_info.post_label = "ansible.yum.install.pkg.fail"
                    handle_ansible_failed(description,  result, host_post_info)
                else:
                    details = "SUCC: yum install package %s successfully" % name
                    host_post_info.post_label = "ansible.yum.install.pkg.succ"
                    handle_ansible_info(details, host_post_info, "INFO")
                    return True


@retry(times=3, sleep_time=3)
def yum_remove_package(name, host_post_info):
    start_time = datetime.now()
    host_post_info.post_label_param = name
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.yum.start.remove.pkg"
    handle_ansible_info("INFO: yum start removing package %s ... " % name, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = 'yum list installed ' + name
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    if 'rc' not in result['contacted'][host]:
        logger.warning("Network problem, try again now, ansible reply is below:\n %s" % result)
        raise Exception(result)
    else:
        status = result['contacted'][host]['rc']
        if status == 0:
            details = "INFO: yum removing %s ... " % name
            host_post_info.post_label = "ansible.yum.remove.pkg"
            handle_ansible_info(details, host_post_info, "INFO")
            runner_args = ZstackRunnerArg()
            runner_args.host_post_info = host_post_info
            runner_args.module_name = 'yum'
            runner_args.module_args = 'name=' + name + ' state=absent',
            zstack_runner = ZstackRunner(runner_args)
            result = zstack_runner.run()
            logger.debug(result)
            if 'failed' in result['contacted'][host]:
                description = "ERROR: yum remove package %s failed" % name
                host_post_info.post_label = "ansible.yum.remove.pkg.fail"
                handle_ansible_failed(description, result, host_post_info)
            else:
                details = "SUCC: yum remove package %s successfully" % name
                host_post_info.post_label = "ansible.yum.remove.pkg.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
        else:
            details = "SKIP: The package %s is not exist in system" % name
            host_post_info.post_label = "ansible.skip.remove.pkg"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def check_pkg_status(name_list, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.check.pkgs.exist"
    post_name_list = ','.join(name_list)
    host_post_info.post_label_param = post_name_list
    handle_ansible_info("INFO: check all packages %s exist in system... " % name_list, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    for name in name_list:
        host_post_info.post_label_param = name
        runner_args.module_args = 'dpkg-query -l %s | grep ^ii ' % name
        zstack_runner = ZstackRunner(runner_args)
        result = zstack_runner.run()
        logger.debug(result)
        if result['contacted'] == {}:
            ansible_start = AnsibleStartResult()
            ansible_start.host = host
            ansible_start.post_url = post_url
            ansible_start.result = result
            handle_ansible_start(ansible_start)
        else:
            if 'rc' not in result['contacted'][host]:
                logger.warning("Maybe network problem, try again now, ansible reply is below:\n %s" % result)
                raise Exception(result)
            else:
                status = result['contacted'][host]['rc']
                if status == 0:
                    details = "SUCC: the package %s exist in system" % name
                    host_post_info.post_label = "ansible.check.pkg.exist.succ"
                    handle_ansible_info(details, host_post_info, "INFO")
                else:
                    details = "SUCC: the package %s not exist in system" % name
                    host_post_info.post_label = "ansible.check.pkg.exist.fail"
                    handle_ansible_info(details, host_post_info, "INFO")
                    return False


def apt_install_packages(name_list, host_post_info):
    def _apt_install_package(name, host_post_info):
        start_time = datetime.now()
        host_post_info.start_time = start_time
        host = host_post_info.host
        post_url = host_post_info.post_url
        host_post_info.post_label_param = name
        host_post_info.post_label = "ansible.apt.install.pkg"
        handle_ansible_info("INFO: starting apt install package %s ... " % name, host_post_info, "INFO")
        runner_args = ZstackRunnerArg()
        runner_args.host_post_info = host_post_info
        runner_args.module_name = 'apt'
        runner_args.module_args = 'name=' + name + ' state=present'
        zstack_runner = ZstackRunner(runner_args)
        result = zstack_runner.run()
        logger.debug(result)
        if result['contacted'] == {}:
            ansible_start = AnsibleStartResult()
            ansible_start.host = host
            ansible_start.post_url = post_url
            ansible_start.result = result
            handle_ansible_start(ansible_start)
        else:
            if 'failed' in result['contacted'][host]:
                description = "ERROR: apt install package %s failed" % name
                host_post_info.post_label = "ansible.apt.install.pkg.fail"
                handle_ansible_failed(description, result, host_post_info)
            elif 'changed' in result['contacted'][host]:
                details = "SUCC: apt install package %s successfully" % name
                host_post_info.post_label = "ansible.apt.install.pkg.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                description = "ERROR: apt install package %s meet unknown issue: %s" % (name, result)
                host_post_info.post_label = "ansible.apt.install.pkg.issue"
                host_post_info.post_label_param = None
                handle_ansible_failed(description, result, host_post_info)
    all_pkg_exist = check_pkg_status(name_list, host_post_info)
    if all_pkg_exist is False:
        command = "apt-get clean && apt-get update -o Acquire::http::No-Cache=True --fix-missing"
        apt_update_status = run_remote_command(command, host_post_info, return_status=True)
        if apt_update_status is False:
            error("apt-get update on host %s failed, please update the repo on the host manually and try again."
                  % host_post_info.host )
        for pkg in name_list:
            _apt_install_package(pkg, host_post_info)




def pip_install_package(pip_install_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    name = pip_install_arg.name
    host = host_post_info.host
    post_url = host_post_info.post_url
    version = pip_install_arg.version
    if pip_install_arg.extra_args is not None:
        if 'pip' not in name:
            extra_args = '\"' + '--disable-pip-version-check ' + pip_install_arg.extra_args.split('"')[1] + '\"'
        else:
            extra_args = '\"' + pip_install_arg.extra_args.split('"')[1] + '\"'
    else:
        extra_args = None
    virtualenv = pip_install_arg.virtualenv
    virtualenv_site_packages = pip_install_arg.virtualenv_site_packages
    host_post_info.post_label = "ansible.pip.install.pkg"
    host_post_info.post_label_param = name
    handle_ansible_info("INFO: pip installing package %s ..." % name, host_post_info, "INFO")
    param_dict = {}
    param_dict_raw = dict(version=version, extra_args=extra_args, virtualenv=virtualenv,
                          virtualenv_site_packages=virtualenv_site_packages)
    for item in param_dict_raw:
        if param_dict_raw[item] is not None:
            param_dict[item] = param_dict_raw[item]
    option = 'name=' + name + ' ' + ' '.join(['{0}={1}'.format(k, v) for k, v in param_dict.iteritems()])
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'pip'
    runner_args.module_args = option
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: pip install package %s failed" % name
            host_post_info.post_label = "ansible.pip.install.pkg.fail"
            handle_ansible_failed(description, result, host_post_info)
            return False
        else:
            details = "SUCC: pip install pacakge %s successfully " % name
            host_post_info.post_label = "ansible.pip.install.pkg.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True

def cron(name, arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.cron.set.task"
    host_post_info.post_label_param = arg
    handle_ansible_info("INFO: starting set cron task %s ... " % arg, host_post_info, "INFO")
    args = 'name=%s %s' % (name,arg)
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'cron'
    runner_args.module_args = args
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: set cron task %s failed!" % arg
            host_post_info.post_label = "ansible.cron.set.task.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: set cron task %s successfully " % arg
            host_post_info.post_label = "ansible.cron.set.task.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the copy result to outside
            return True

def copy(copy_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    src = copy_arg.src
    dest = copy_arg.dest
    args = copy_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.copy.start"
    host_post_info.post_label_param = [src, dest]
    handle_ansible_info("INFO: starting copy %s to %s ... " % (src, dest), host_post_info, "INFO")
    if args is not None:
        copy_args = 'src=' + src + ' dest=' + dest + ' ' + args
    else:
        copy_args = 'src=' + src + ' dest=' + dest
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'copy'
    runner_args.module_args = copy_args
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: copy %s to %s failed" % (src, dest)
            host_post_info.post_label = "ansible.copy.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            change_status = "changed:" + str(result['contacted'][host]['changed'])
            details = "SUCC: copy %s to %s successfully, the change status is %s" % (src, dest, change_status)
            host_post_info.post_label = "ansible.copy.change"
            host_post_info.post_label_param = [src, dest, change_status]
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the copy result to outside
            return change_status

def fetch(fetch_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    src = fetch_arg.src
    dest = fetch_arg.dest
    args = fetch_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.fetch.start"
    host_post_info.post_label_param = [src, dest]
    handle_ansible_info("INFO: starting fetch %s to %s ... " % (src, dest), host_post_info, "INFO")
    if args is not None:
        fetch_args = 'src=' + src + ' dest=' + dest + ' ' + args
    else:
        fetch_args = 'src=' + src + ' dest=' + dest
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'fetch'
    runner_args.module_args = fetch_args
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: fetch from %s to %s failed" % (src, dest)
            host_post_info.post_label = "ansible.fetch.fail"
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            change_status = "changed:" + str(result['contacted'][host]['changed'])
            details = "SUCC: fetch %s to %s, the change status is %s" % (src, dest, change_status)
            host_post_info.post_label = "ansible.fetch.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the fetch result to outside
            return change_status

def check_host_reachable(host_post_info):
    '''This interface used by zstackctl'''
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    handle_ansible_info("INFO: Starting check host %s is reachable ..." % host, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'ping'
    runner_args.module_args = ''
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        return False
    elif result['contacted'][host]['ping'] == 'pong':
        return True
    else:
        error("Unknown error when check host %s is reachable" % host)

@retry(times=3, sleep_time=3)
def run_remote_command(command, host_post_info, return_status=False):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.command"
    host_post_info.post_label_param = command
    handle_ansible_info("INFO: starting run command [ %s ] ..." % command, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = command
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'rc' not in result['contacted'][host]:
            logger.warning("Network problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['rc']
            if status == 0:
                details = "SUCC: run shell command: %s successfully " % command
                host_post_info.post_label = "ansible.command.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                if return_status is False:
                    description = "ERROR: run shell command: %s failed!" % command
                    host_post_info.post_label = "ansible.command.fail"
                    handle_ansible_failed(description, result, host_post_info)
                    sys.exit(1)
                else:
                    details = "ERROR: shell command %s failed " % command
                    host_post_info.post_label = "ansible.command.fail"
                    handle_ansible_info(details, host_post_info, "WARNING")
                    return False


@retry(times=3, sleep_time=3)
def check_pip_version(version, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.check.pip.version"
    host_post_info.post_label_param = version
    handle_ansible_info("INFO: check pip version %s exist ..." % version, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = "pip --version | grep %s" % version
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'rc' not in result['contacted'][host]:
            logger.warning("Network problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['rc']
            if status == 0:
                details = "SUCC: pip-%s exist in system " % version
                host_post_info.post_label = "ansible.check.pip.version.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                details = "INFO: pip-%s not exist in system" % version
                host_post_info.post_label = "ansible.check.pip.version.fail"
                handle_ansible_info(details, host_post_info, "INFO")
                return False


@retry(times=3, sleep_time=3)
def file_dir_exist(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.check.file.dir.exist"
    host_post_info.post_label_param = name
    handle_ansible_info("INFO: starting check file or dir %s exist ... " % name, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'stat'
    runner_args.module_args = name
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'stat' not in result['contacted'][host]:
            logger.warning("Network problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['stat']['exists']
            if status is True:
                details = "INFO: %s exist" % name
                host_post_info.post_label = "ansible.check.file.dir.exist.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                details = "INFO: %s not exist" % name
                host_post_info.post_label = "ansible.check.file.dir.exist.fail"
                handle_ansible_info(details, host_post_info, "INFO")
                return False


def file_operation(file, args, host_post_info):
    ''''This function will change file attribute'''
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.change.file.attribute.start"
    host_post_info.post_label_param = file
    handle_ansible_info("INFO: starting change file attribute %s ... " % file, host_post_info, "INFO")
    args = "path=%s " % file + args
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'file'
    runner_args.module_args = args
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'failed' in result['contacted'][host]:
            details = "INFO: %s not be changed" % file
            host_post_info.post_label = "ansible.change.file.attribute.fail"
            handle_ansible_info(details, host_post_info, "INFO")
            return False
        else:
            details = "INFO: %s changed successfully" % file
            host_post_info.post_label = "ansible.change.file.attribute.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True

@retry(times=3, sleep_time=3)
def get_remote_host_info(host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.get.host.info"
    host_post_info.post_label_param = host
    handle_ansible_info("INFO: starting get remote host %s info ... " % host, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'setup'
    runner_args.module_args = 'filter=ansible_distribution*'
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'ansible_facts' in result['contacted'][host]:
            (distro, version, release) = [result['contacted'][host]['ansible_facts']['ansible_distribution'],
                                 int(result['contacted'][host]['ansible_facts']['ansible_distribution_major_version']),
                                 result['contacted'][host]['ansible_facts']['ansible_distribution_release']]
            host_post_info.post_label = "ansible.get.host.info.succ"
            handle_ansible_info("SUCC: Get remote host %s info successful" % host, host_post_info, "INFO")
            return (distro, version, release)
        else:
            host_post_info.post_label = "ansible.get.host.info.succ"
            logger.warning("get_remote_host_info on host %s failed!" % host)
            raise Exception(result)

def set_ini_file(file, section, option, value, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.set.ini.file"
    host_post_info.post_label_param = [file, section]
    handle_ansible_info("INFO: starting update file %s section %s ... " % (file, section), host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'ini_file'
    runner_args.module_args = 'dest=' + file + ' section=' + section + ' option=' + option + " value=" + value
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        details = "SUCC: update file: %s option: %s value %s" % (file, option, value)
        host_post_info.post_label = "ansible.set.ini.file.succ"
        host_post_info.post_label_param = [file, option, value]
        handle_ansible_info(details, host_post_info, "INFO")
    return True


@retry(times=3, sleep_time=3)
def check_and_install_virtual_env(version, trusted_host, pip_url, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.check.install.virtualenv"
    host_post_info.post_label_param = version
    handle_ansible_info("INFO: starting install virtualenv-%s ... " % version, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args ='virtualenv --version | grep %s' % version
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'rc' not in result['contacted'][host]:
            logger.warning("Network problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['rc']
            if status == 0:
                details = "SUCC: the virtualenv-%s exist in system" % version
                host_post_info.post_label = "ansible.check.install.virtualenv.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                extra_args = "\"--trusted-host %s -i %s \"" % (trusted_host, pip_url)
                pip_install_arg = PipInstallArg()
                pip_install_arg.extra_args = extra_args
                pip_install_arg.version = version
                pip_install_arg.name = "virtualenv"
                return pip_install_package(pip_install_arg, host_post_info)


def service_status(name, args, host_post_info, ignore_error=False):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.service.status"
    host_post_info.post_label_param = [name, args]
    handle_ansible_info("INFO: changing %s service status to %s " % (name, args), host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'service'
    runner_args.module_args ="name=%s " % name + args
    zstack_runner = ZstackRunner(runner_args)
    if ignore_error is True:
        try:
            result = zstack_runner.run()
            logger.debug(result)
            if result['contacted'] == {}:
                ansible_start = AnsibleStartResult()
                ansible_start.host = host
                ansible_start.post_url = post_url
                ansible_start.result = result
                handle_ansible_start(ansible_start)
            else:
                if 'failed' in result['contacted'][host]:
                    details = "ERROR: change service %s status failed!" % name
                    host_post_info.post_label = "ansible.service.status.fail"
                    handle_ansible_info(details, host_post_info, "WARNING")
                else:
                    details = "SUCC: change service %s status to %s successfully" % (name, args)
                    host_post_info.post_label = "ansible.service.status.succ"
                    handle_ansible_info(details, host_post_info, "INFO")
        except:
            logger.debug("WARNING: The service %s status changed failed" % name)
    else:
        result = zstack_runner.run()
        logger.debug(result)
        if result['contacted'] == {}:
            ansible_start = AnsibleStartResult()
            ansible_start.host = host
            ansible_start.post_url = post_url
            ansible_start.result = result
            handle_ansible_start(ansible_start)
        else:
            if 'failed' in result['contacted'][host]:
                description = "ERROR: change service %s status to %s failed!" % (name, args)
                host_post_info.post_label = "ansible.service.status.fail"
                handle_ansible_failed(description, result, host_post_info)
            else:
                details = "SUCC: change service %s status to %s successfully" % (name, args)
                host_post_info.post_label = "ansible.service.status.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True


def update_file(dest, args, host_post_info):
    '''Use this function to change the file content'''
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.update.file"
    host_post_info.post_label_param = dest
    handle_ansible_info("INFO: updating file %s" % dest, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'lineinfile'
    runner_args.module_args = "dest=%s %s" % (dest, args)
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: update file %s failed" % dest
            host_post_info.post_label = "ansible.update.file.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: update file %s successfully" % dest
            host_post_info.post_label = "ansible.update.file.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def set_selinux(args, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.set.selinux"
    host_post_info.post_label_param = args
    handle_ansible_info("INFO: set selinux status to %s" % args, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'selinux'
    runner_args.module_args = args
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: set selinux status to %s failed" % args
            host_post_info.post_label = "ansible.set.selinux.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: set selinux to %s successfully" % args
            host_post_info.post_label = "ansible.set.selinux.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def authorized_key(user, key_path, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    if not os.path.exists(key_path):
        error("key_path %s is not exist!" % key_path)
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.add.key"
    host_post_info.post_label_param = [key_path, host]
    handle_ansible_info("INFO: updating key %s to host %s" % (key_path, host), host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = "cat %s" % key_path
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        key = result['contacted'][host]['stdout']
        key = '\'' + key + '\''
        args = "user=%s key=%s" % (user, key)
        runner_args = ZstackRunnerArg()
        runner_args.host_post_info = host_post_info
        runner_args.module_name ='authorized_key'
        runner_args.module_args = args
        zstack_runner = ZstackRunner(runner_args)
        result = zstack_runner.run()
        logger.debug(result)
        if 'failed' in result['contacted'][host]:
            description = "ERROR: update key %s to host %s failed" % (key_path,host)
            host_post_info.post_label = "ansible.add.key.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: update key %s to host %s successfully" % (key_path, host)
            host_post_info.post_label = "ansible.add.key.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def unarchive(unarchive_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    src = unarchive_arg.src
    dest = unarchive_arg.dest
    args = unarchive_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.unarchive"
    host_post_info.post_label_param = [src, dest]
    handle_ansible_info("INFO: starting unarchive %s to %s ... " % (src, dest), host_post_info, "INFO")
    if args != None:
        unarchive_args = 'src=' + src + ' dest=' + dest + ' ' + args
    else:
        unarchive_args = 'src=' + src + ' dest=' + dest
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'unarchive'
    runner_args.module_args = unarchive_args
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    result = zstack_runner.run()
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
    else:
        if 'failed' in result['contacted'][host]:
            description = "ERROR: unarchive %s to %s failed" % (src, dest)
            host_post_info.post_label = "ansible.unarchive.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: unarchive %s to %s successfully" % (src, dest)
            host_post_info.post_label = "ansible.unarchive.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


class ZstackLib(object):
    def __init__(self, args):
        distro = args.distro
        distro_release = args.distro_release
        distro_version = args.distro_version
        zstack_repo = args.zstack_repo
        zstack_root = args.zstack_root
        host_post_info = args.host_post_info
        trusted_host = args.trusted_host
        pip_url = args.pip_url
        pip_version = "7.0.3"
        yum_server = args.yum_server
        current_dir =  os.path.dirname(os.path.realpath(__file__))
        if distro == "CentOS" or distro == "RedHat":
            epel_repo_exist = file_dir_exist("path=/etc/yum.repos.d/epel.repo", host_post_info)
            # To avoid systemd bug :https://github.com/systemd/systemd/issues/1961
            run_remote_command("rm -f /run/systemd/system/*.scope", host_post_info)
            # set ALIYUN mirror yum repo firstly avoid 'yum clean --enablerepo=alibase metadata' failed
            command = """
echo -e "#aliyun base
[alibase]
name=CentOS-\$releasever - Base - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/
gpgcheck=0
enabled=0
#released updates
[aliupdates]
name=CentOS-\$releasever - Updates -mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/
enabled=0
gpgcheck=0
[aliextras]
name=CentOS-\$releasever - Extras - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/
enabled=0
gpgcheck=0
[aliepel]
name=Extra Packages for Enterprise Linux \$releasever - \$basearch - mirrors.aliyun.com
baseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch
failovermethod=priority
enabled=0
gpgcheck=0
[ali-qemu-ev]
name=CentOS-\$releasever - QEMU EV
baseurl=http://mirrors.aliyun.com/centos/\$releasever/virt/\$basearch/kvm-common/
gpgcheck=0
enabled=0" > /etc/yum.repos.d/zstack-aliyun-yum.repo
        """
            run_remote_command(command, host_post_info)

            if zstack_repo == "false":
                # zstack_repo defined by user
                yum_install_package("libselinux-python", host_post_info)
                # Enable extra repo for install centos-release-qemu-ev in kvm.py
                if distro_version >= 7 :
                    copy_arg = CopyArg()
                    copy_arg.src = "files/zstacklib/zstack-redhat.repo"
                    copy_arg.dest = "/etc/yum.repos.d/"
                    copy(copy_arg, host_post_info)
                # install epel-release
                if epel_repo_exist is False:
                    copy_arg = CopyArg()
                    copy_arg.src = "files/zstacklib/epel-release-source.repo"
                    copy_arg.dest = "/etc/yum.repos.d/"
                    copy(copy_arg, host_post_info)
                    # install epel-release
                    yum_enable_repo("epel-release", "epel-release-source", host_post_info)
                    set_ini_file("/etc/yum.repos.d/epel.repo", 'epel', "enabled", "1", host_post_info)
                for pkg in ["python-devel", "python-setuptools", "python-pip", "gcc", "autoconf", "ntp", "ntpdate"]:
                    yum_install_package(pkg, host_post_info)
            else:
                # generate repo defined in zstack_repo
                if '163' in zstack_repo:
                    # set 163 mirror yum repo
                    command = """
echo -e "#163 base
[163base]
name=CentOS-\$releasever - Base - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/
gpgcheck=0
enabled=0
#released updates
[163updates]
name=CentOS-\$releasever - Updates - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/
enabled=0
gpgcheck=0
#additional packages that may be useful
[163extras]
name=CentOS-\$releasever - Extras - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/
enabled=0
gpgcheck=0
[ustcepel]
name=Extra Packages for Enterprise Linux \$releasever - \$basearch - ustc
baseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch
failovermethod=priority
enabled=0
gpgcheck=0
[163-qemu-ev]
name=CentOS-\$releasever - QEMU EV
baseurl=http://mirrors.163.com/centos/\$releasever/virt/\$basearch/kvm-common/
gpgcheck=0
enabled=0" > /etc/yum.repos.d/zstack-163-yum.repo
        """
                    run_remote_command(command, host_post_info)
                if 'zstack-mn' in zstack_repo:
                    generate_mn_repo_raw_command = """
echo -e "[zstack-mn]
name=zstack-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-dvd/
gpgcheck=0
enabled=0" >  /etc/yum.repos.d/zstack-mn.repo
               """
                    generate_mn_repo_template = jinja2.Template(generate_mn_repo_raw_command)
                    generate_mn_repo_command = generate_mn_repo_template.render({
                       'yum_server' : yum_server
                    })
                    run_remote_command(generate_mn_repo_command, host_post_info)
                if 'qemu-kvm-ev-mn' in zstack_repo:
                    generate_kvm_repo_raw_command = """
echo -e "[qemu-kvm-ev-mn]
name=qemu-kvm-ev-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-dvd/Extra/qemu-kvm-ev/
gpgcheck=0
enabled=0" >  /etc/yum.repos.d/qemu-kvm-ev-mn.repo
               """
                    generate_kvm_repo_template = jinja2.Template(generate_kvm_repo_raw_command)
                    generate_kvm_repo_command = generate_kvm_repo_template.render({
                        'yum_server':yum_server
                    })
                    run_remote_command(generate_kvm_repo_command, host_post_info)
                # install libselinux-python and other command system libs from user defined repos
                # enable alibase repo for yum clean avoid no repo to be clean
                command = (
                          "yum clean --enablerepo=alibase metadata &&  pkg_list=`rpm -q libselinux-python python-devel "
                          "python-setuptools python-pip gcc autoconf ntp ntpdate | grep \"not installed\" | awk"
                          " '{ print $2 }'` && for pkg in $pkg_list; do yum --disablerepo=* --enablerepo=%s install "
                          "-y $pkg; done;") % zstack_repo
                run_remote_command(command, host_post_info)

            # enable ntp service for RedHat
            service_status("ntpd", "state=restarted enabled=yes", host_post_info)

        elif distro == "Debian" or distro == "Ubuntu":
            command = '/bin/cp -f /etc/apt/sources.list /etc/apt/sources.list.zstack.%s' \
                      % datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            run_remote_command(command, host_post_info)
            update_repo_raw_command = """
cat > /etc/apt/sources.list << EOF
deb http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }} main restricted universe multiverse
deb http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-security main restricted universe multiverse
deb http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-updates main restricted universe multiverse
deb http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-proposed main restricted universe multiverse
deb http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-backports main restricted universe multiverse
deb-src http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }} main restricted universe multiverse
deb-src http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-security main restricted universe multiverse
deb-src http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-updates main restricted universe multiverse
deb-src http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-proposed main restricted universe multiverse
deb-src http://mirrors.{{ zstack_repo }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-backports main restricted universe multiverse
                """
            if 'ali' in zstack_repo:
                update_repo_command_template = jinja2.Template(update_repo_raw_command)
                update_repo_command = update_repo_command_template.render({
                    'zstack_repo' : 'aliyun',
                    'DISTRIB_CODENAME' : distro_release
                })
                run_remote_command(update_repo_command, host_post_info)
            if '163' in zstack_repo:
                update_repo_command_template = jinja2.Template(update_repo_raw_command)
                update_repo_command = update_repo_command_template.render({
                    'zstack_repo' : '163',
                    'DISTRIB_CODENAME' : distro_release
                })
                run_remote_command(update_repo_command, host_post_info)

            # install dependency packages for Debian based OS
            service_status('unattended-upgrades', 'state=stopped enabled=no', host_post_info, ignore_error=True)
            #apt_update_cache(86400, host_post_info)
            install_pkg_list =["python-dev", "python-setuptools", "python-pip", "gcc", "autoconf", "ntp", "ntpdate"]
            apt_install_packages(install_pkg_list, host_post_info)

            # name: enable ntp service for Debian
            run_remote_command("update-rc.d ntp defaults; service ntp restart", host_post_info)

        else:
            error("ERROR: Unsupported distribution")

        # check the pip 7.0.3 exist in system to avoid site-packages enable potential issue
        pip_match = check_pip_version(pip_version, host_post_info)
        if pip_match is False:
            # make dir for copy pip
            run_remote_command("mkdir -p %s" % zstack_root, host_post_info)
            # copy pip 7.0.3
            copy_arg = CopyArg()
            copy_arg.src = "files/pip-7.0.3.tar.gz"
            copy_arg.dest = "%s/pip-7.0.3.tar.gz" % zstack_root
            copy(copy_arg, host_post_info)
            # install pip 7.0.3
            pip_install_arg = PipInstallArg()
            pip_install_arg.extra_args = "\"--ignore-installed\""
            pip_install_arg.name = "%s/pip-7.0.3.tar.gz" % zstack_root
            pip_install_package(pip_install_arg, host_post_info)


def main():
    # Reserve for test api
    pass

if __name__ == "__main__":
    main()

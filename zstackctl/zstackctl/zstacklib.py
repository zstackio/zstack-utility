#!/usr/bin/env python
# encoding: utf-8
import pprint
import traceback

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
import re

# set global default value
start_time = datetime.now()
logger = logging.getLogger("deploy-ha-Log")
pip_url = ""
zstack_root = ""
host = ""
pkg_zstacklib = ""
yum_server = ""
trusted_host = ""
ansible.constants.HOST_KEY_CHECKING = False

RPM_BASED_OS = ["centos", "redhat", "alibaba", "kylin10"]
DEB_BASED_OS = ["ubuntu", "kylin4.0.2", "uos", "debian", "uniontech"]
DISTRO_WITH_RPM_DEB = ["kylin"]


def ignoreerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            logger.warn(err)
    return wrap


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
        self.zstack_apt_source = None
        self.yum_server = None
        self.apt_server = None
        self.distro = None
        self.distro_version = None
        self.distro_release = None
        self.zstack_root = None
        self.host_post_info = None
        self.pip_url = None


class Log(object):
    def __init__(self):
        self.level = None
        self.details = None


class Error(object):
    def __init__(self):
        self.code = None
        self.description = None
        self.details = None


class Msg(object):
    def ___init__(self):
        self.type = None
        self.data = None


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
        self.chrony_servers = None
        self.post_url = ""
        self.start_time = None
        self.rabbit_password = None
        self.mysql_password = None
        self.mysql_userpassword = None


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

class SyncArg(object):
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

    def run(self):
        runner = ansible.runner.Runner(
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

def warn(msg):
    logger.warning(msg)
    sys.stdout.write('WARNING: %s\n' % msg)

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


def create_log(logger_dir, logger_file):
    if not os.path.exists(logger_dir):
        os.makedirs(logger_dir)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler = logging.handlers.RotatingFileHandler(logger_dir + '/' + logger_file, maxBytes=10 * 1024 * 1024,
                                                   backupCount=30)
    handler.setFormatter(fmt)
    logger.addHandler(handler)

def get_mn_release():
    # file /etc/zstack-release from zstack-release.rpm
    # file content like: ZStack release c76
    return commands.getoutput("awk '{print $3}' /etc/zstack-release").strip()

def get_host_releasever(ansible_distribution):
    supported_release_info = {
        "kylin10 tercel 10": "ns10",
        "uniontech fou 20": "uos20",
        "redhat maipo 7.4": "ns10", # old kylinV10, oem 7.4 incompletely
        "centos core 7.6.1810": "c76",
        "centos core 7.4.1708": "c74",
        "centos core 7.2.1511": "c74", # c74 for old releases
        "centos core 7.1.1503": "c74",
    }
    _key = " ".join(ansible_distribution).lower()
    _releasever = supported_release_info.get(_key)
    return _releasever if _releasever else get_mn_release()

def post_msg(msg, post_url):
    logger.info(msg.data.details)
    if msg.type == "log":
        data = json.dumps({"level": msg.data.level, "details": msg.data.details})
    elif msg.type == "error":
        data = json.dumps({"code": msg.data.code, "description": msg.data.description, "details": msg.data.details})
        # This output will capture by management log
        error(msg.data.description + "\nDetail: " + msg.data.details)
    else:
        error("ERROR: undefined message type: %s" % msg.type)

    if post_url == "":
        logger.info("Warning: no post_url defined by user")
        return 0
    try:
        headers = {"content-type": "application/json"}
        req = urllib2.Request(post_url, data, headers)
        response = urllib2.urlopen(req)
        response.close()
    except URLError, e:
        logger.debug(e.reason)
        error("Please check the post_url: %s and check the server status" % post_url)


def handle_ansible_start(ansible_start):
    msg = Msg()
    error = Error()
    error.code = "ansible.1000"
    error.description = "ERROR: Can't start ansible process"
    error.details = "Can't start ansible process to host: %s Detail: %s, check authentication and inventory file then" \
                    " try again  \n" % (ansible_start.host, ansible_start.result)
    msg.type = "error"
    msg.data = error
    post_msg(msg, ansible_start.post_url)


def handle_ansible_failed(description, result, host_post_info):
    msg = Msg()
    error = Error()
    host = host_post_info.host
    post_url = host_post_info.post_url
    start_time = host_post_info.start_time
    end_time = datetime.now()
    # Fix python2.6 compatible issue: no total_seconds() attribute for timedelta
    td = end_time - start_time
    cost_time = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / 10 ** 6.0 * 1000
    error.code = "ansible.1001"
    error.description = "[ HOST: %s ] " % host_post_info.host + description + " [ cost %sms to finish ]" % int(cost_time)
    if 'stderr' in result['contacted'][host]:
        error.details = "[ HOST: %s ] " % host_post_info.host + "ERROR: \n" + result['contacted'][host]['stderr']
    elif 'msg' in result['contacted'][host]:
        error.details = "[ HOST: %s ] " % host_post_info.host +  "ERROR: \n" + result['contacted'][host]['msg']
    msg.type = "error"
    msg.data = error
    post_msg(msg, post_url)


def handle_ansible_info(details, host_post_info, level):
    msg = Msg()
    log = Log()
    post_url = host_post_info.post_url
    start_time = host_post_info.start_time
    end_time = datetime.now()
    # Fix python2.6 compatible issue: no total_seconds() attribute for timedelta
    td = end_time - start_time
    cost_time = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10 ** 6) / 10 ** 6.0 * 1000
    log.level = level
    if "SUCC" in details:
        log.details = "[ HOST: %s ] " % host_post_info.host + details + " [ cost %sms to finish ]" % int(cost_time)
    else:
        log.details = "[ HOST: %s ] " % host_post_info.host + details
    msg.type = "log"
    msg.data = log
    post_msg(msg, post_url)


def agent_install(install_arg, host_post_info):
    handle_ansible_info("INFO: Start to install %s .................." % install_arg.agent_name, host_post_info, "INFO")
    pip_install_arg = PipInstallArg()
    pip_install_arg.extra_args = "\"--trusted-host %s -i %s\"" % (install_arg.trusted_host, install_arg.pip_url)
    # upgrade only
    if install_arg.init_install is False:
        handle_ansible_info("INFO: Only need to upgrade %s .................." % install_arg.agent_name, host_post_info,
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
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: yum enable repo %s " % enablerepo
            handle_ansible_info(details, host_post_info, "INFO")
            return True


@retry(times=3, sleep_time=3)
def yum_check_package(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
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
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                details = "SUCC: The package %s not exist in system" % name
                handle_ansible_info(details, host_post_info, "INFO")
                return False

@retry(times=3, sleep_time=3)
def script(file, host_post_info, script_arg=None):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
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
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                description = "ERROR: The script %s failed on host %s" % (file, host)
                handle_ansible_failed(description, result, host_post_info)


@retry(times=3, sleep_time=3)
def yum_install_package(name, host_post_info, \
        ignore_error=False, force_install=False):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
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
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                details = "Installing package %s ..." % name
                handle_ansible_info(details, host_post_info, "INFO")
                runner_args = ZstackRunnerArg()
                runner_args.host_post_info = host_post_info
                runner_args.module_name = 'yum'
                runner_args.module_args = 'name=' + name + ' disable_gpg_check=no state=latest'
                zstack_runner = ZstackRunner(runner_args)
                result = zstack_runner.run()
                logger.debug(result)
                if 'failed' in result['contacted'][host] and not ignore_error:
                    description = "ERROR: YUM install package %s failed" % name
                    handle_ansible_failed(description, result, host_post_info)
                else:
                    details = "SUCC: yum install package %s successful!" % name
                    handle_ansible_info(details, host_post_info, "INFO")
                    return True


@retry(times=3, sleep_time=3)
def yum_remove_package(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting yum remove package %s ... " % name, host_post_info, "INFO")
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
            details = "Removing %s ... " % name
            handle_ansible_info(details, host_post_info, "INFO")
            runner_args = ZstackRunnerArg()
            runner_args.host_post_info = host_post_info
            runner_args.module_name = 'yum'
            runner_args.module_args = 'name=' + name + ' state=absent',
            zstack_runner = ZstackRunner(runner_args)
            result = zstack_runner.run()
            logger.debug(result)
            if 'failed' in result['contacted'][host]:
                description = "ERROR: Yum remove package %s failed!" % name
                handle_ansible_failed(description, result, host_post_info)
            else:
                details = "SUCC: Remove package %s " % name
                handle_ansible_info(details, host_post_info, "INFO")
                return True
        else:
            details = "SKIP: The package %s is not exist in system" % name
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def check_pkg_status(name_list, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    private_key = host_post_info.private_key
    host_inventory = host_post_info.host_inventory
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting check package %s exist in system... " % name_list, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    for name in name_list:
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
                    details = "SUCC: The package %s exist in system" % name
                    handle_ansible_info(details, host_post_info, "INFO")
                else:
                    details = "SUCC: The package %s not exist in system" % name
                    handle_ansible_info(details, host_post_info, "INFO")
                    return False


def apt_install_packages(name_list, host_post_info):
    def _apt_install_package(name, host_post_info):
        start_time = datetime.now()
        host_post_info.start_time = start_time
        host = host_post_info.host
        post_url = host_post_info.post_url
        handle_ansible_info("INFO: Starting apt install package %s ... " % name, host_post_info, "INFO")
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
                description = "ERROR: Apt install %s failed!" % name
                handle_ansible_failed(description, result, host_post_info)
            elif 'changed' in result['contacted'][host]:
                details = "SUCC: apt install package %s " % name
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                description = "ERROR: Apt install %s meet unknown issue: %s" % (name, result)
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

def apt_update_packages(name_list, host_post_info):
    pkg_list = ' '.join(name_list)
    command = "apt-get clean && apt-get install -y --allow-unauthenticated --only-upgrade {}".format(pkg_list)
    apt_update_status = run_remote_command(command, host_post_info, return_status=True)
    if apt_update_status is False:
        error("apt-get update packages on host {} failed, please update the repo on the host manually and try again.".format(host_post_info.host))



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
    handle_ansible_info("INFO: Pip installing module %s ..." % name, host_post_info, "INFO")
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
            command = "pip uninstall -y %s" % name
            run_remote_command(command, host_post_info)
            description = "ERROR: pip install package %s failed!" % name
            handle_ansible_failed(description, result, host_post_info)
            return False
        else:
            details = "SUCC: Install python module %s " % name
            handle_ansible_info(details, host_post_info, "INFO")
            return True

def cron(name, arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting set cron task %s ... " % arg, host_post_info, "INFO")
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
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: set cron task %s " % arg
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
    handle_ansible_info("INFO: Starting copy %s to %s ... " % (src, dest), host_post_info, "INFO")
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
            description = "ERROR: copy %s to %s failed!" % (src, dest)
            handle_ansible_failed(description, result, host_post_info)
        else:
            change_status = "changed:" + str(result['contacted'][host]['changed'])
            details = "SUCC: copy %s to %s, the change status is %s" % (src, dest, change_status)
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the copy result to outside
            return change_status

def sync(sync_arg, host_post_info):
    '''The copy module recursively copy facility does not scale to lots (>hundreds) of files.
    so we add sync module which will use ansible synchronize module, which is a wrapper around rsync.'''
    start_time = datetime.now()
    host_post_info.start_time = start_time
    src = sync_arg.src
    dest = sync_arg.dest
    args = sync_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting sync %s to %s ... " % (src, dest), host_post_info, "INFO")
    if args is not None:
        sync_args = 'src=' + src + ' dest=' + dest + ' ' + args
    else:
        sync_args = 'src=' + src + ' dest=' + dest
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'synchronize'
    runner_args.module_args = sync_args
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
            description = "ERROR: sync %s to %s failed!" % (src, dest)
            handle_ansible_failed(description, result, host_post_info)
        else:
            change_status = "changed:" + str(result['contacted'][host]['changed'])
            details = "SUCC: sync %s to %s, the change status is %s" % (src, dest, change_status)
            handle_ansible_info(details, host_post_info, "INFO")
            return change_status


def fetch(fetch_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    src = fetch_arg.src
    dest = fetch_arg.dest
    args = fetch_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting fetch %s to %s ... " % (src, dest), host_post_info, "INFO")
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
            description = "ERROR: fetch file from %s to %s failed!" % (src, dest)
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            change_status = "changed:" + str(result['contacted'][host]['changed'])
            details = "SUCC: fetch %s to %s, the change status is %s" % (src, dest, change_status)
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the fetch result to outside
            return change_status

def check_host_reachable(host_post_info, warning=False):
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
    elif 'failed' in result['contacted'][host]:
        if result['contacted'][host]['failed'] is True:
            return False
    elif result['contacted'][host]['ping'] == 'pong':
        return True
    else:
        if warning is False:
            error("Unknown error when check host %s is reachable" % host)
        else:
            warn("Unknown error when check host %s is reachable" % host)
        return False

@retry(times=3, sleep_time=3)
def run_remote_command(command, host_post_info, return_status=False, return_output=False):
    '''return status all the time except return_status is False, return output is set to True'''
    if 'yum' in command:
        set_yum0 = '''rpm -q zstack-release >/dev/null && releasever=`awk '{print $3}' /etc/zstack-release` || releasever=%s;\
                    export YUM0=$releasever; grep $releasever /etc/yum/vars/YUM0 || echo $releasever > /etc/yum/vars/YUM0;''' % (get_mn_release())
        command = set_yum0 + command
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting run command [ %s ] ..." % command, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = command
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        if 'Broken pipe' in str(result):
            logger.debug("find broken pipe in ansible result, retry it")
            raise Exception(result)

        ansible_start = AnsibleStartResult()
        ansible_start.host = host
        ansible_start.post_url = post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        sys.exit(1)
    else:
        if 'rc' not in result['contacted'][host]:
            logger.warning("Network or file system problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['rc']
            if status == 0:
                details = "SUCC: shell command: '%s' " % command
                handle_ansible_info(details, host_post_info, "INFO")
                if return_output is False:
                    return True
                else:
                    return (True, result['contacted'][host]['stdout'])
            else:
                if return_status is False:
                    description = "ERROR: command %s failed!" % command
                    handle_ansible_failed(description, result, host_post_info)
                    sys.exit(1)
                else:
                    details = "ERROR: shell command %s failed " % command
                    handle_ansible_info(details, host_post_info, "WARNING")
                    if return_output is False:
                        return False
                    else:
                        return (False, result['contacted'][host]['stdout'])


@retry(times=3, sleep_time=3)
def check_pip_version(version, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Check pip version %s exist ..." % version, host_post_info, "INFO")
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
                details = "SUCC: Check pip-%s exist in system " % version
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                details = "INFO: Check pip-%s is not exist in system" % version
                handle_ansible_info(details, host_post_info, "INFO")
                return False


@retry(times=3, sleep_time=3)
def file_dir_exist(name, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting check file or dir exist %s ... " % name, host_post_info, "INFO")
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
        if 'failed' in result['contacted'][host] and result['contacted'][host]['failed'] is True:
            logger.warning("Check file or dir %s status failed" % name)
            sys.exit(1)
        elif 'stat' not in result['contacted'][host]:
            logger.warning("Network problem, try again now, ansible reply is below:\n %s" % result)
            raise Exception(result)
        else:
            status = result['contacted'][host]['stat']['exists']
            if status is True:
                details = "INFO: %s exist" % name
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                details = "INFO: %s not exist" % name
                handle_ansible_info(details, host_post_info, "INFO")
                return False


def file_operation(file, args, host_post_info):
    ''''This function will change file attribute'''
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting change file %s ... " % file, host_post_info, "INFO")
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
            handle_ansible_info(details, host_post_info, "INFO")
            return False
        else:
            details = "INFO: %s changed successfully" % file
            handle_ansible_info(details, host_post_info, "INFO")
            return True

@retry(times=3, sleep_time=3)
def get_remote_host_info(host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting get remote host %s info ... " % host, host_post_info, "INFO")
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
            (distro, major_version, release, distro_version) = [
                                 result['contacted'][host]['ansible_facts']['ansible_distribution'].split()[0].lower(),
                                 int(result['contacted'][host]['ansible_facts']['ansible_distribution_major_version']),
                                 result['contacted'][host]['ansible_facts']['ansible_distribution_release'],
                                 result['contacted'][host]['ansible_facts']['ansible_distribution_version']]
            handle_ansible_info("SUCC: Get remote host %s info successful" % host, host_post_info, "INFO")
            if distro in DISTRO_WITH_RPM_DEB:
                distro = "%s%s" % (distro, major_version)
            return (distro, major_version, release, distro_version)
        else:
            logger.warning("get_remote_host_info on host %s failed!" % host)
            raise Exception(result)


def set_ini_file(file, section, option, value, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting update file %s section %s ... " % (file, section), host_post_info, "INFO")
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
        details = "SUCC: Update file: %s option: %s value %s" % (file, option, value)
        handle_ansible_info(details, host_post_info, "INFO")
    return True


@retry(times=3, sleep_time=3)
def check_and_install_virtual_env(version, trusted_host, pip_url, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting install virtualenv-%s ... " % version, host_post_info, "INFO")
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
                details = "SUCC: The virtualenv-%s exist in system" % version
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
    handle_ansible_info("INFO: Changing %s service status to %s " % (name, args), host_post_info, "INFO")
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
                    handle_ansible_info(details, host_post_info, "WARNING")
                else:
                    details = "SUCC: Service %s status changed" % name
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
                description = "ERROR: change service status failed!"
                handle_ansible_failed(description, result, host_post_info)
            else:
                details = "SUCC: Service status changed"
                handle_ansible_info(details, host_post_info, "INFO")
                return True


def update_file(dest, args, host_post_info):
    '''Use this function to change the file content'''
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Updating file %s" % dest, host_post_info, "INFO")
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
            description = "ERROR: Update file %s failed" % dest
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: Update file %s" % dest
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def set_selinux(args, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Set selinux status to %s" % args, host_post_info, "INFO")
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
            description = "ERROR: set selinux to %s failed" % args
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: Reset selinux to %s" % args
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def authorized_key(user, key_path, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    if not os.path.exists(key_path):
        error("key_path %s is not exist!" % key_path)
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Updating key %s to host %s" % (key_path, host), host_post_info, "INFO")
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
            description = "ERROR: Authorized on remote host %s failed!" % host
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: update public key to host %s" % host
            handle_ansible_info(details, host_post_info, "INFO")
            return True

def check_pswd_rules(pswd):
    if not len(pswd) >= 8:
        return False
    if not re.search(r"[0-9]+", pswd):
        return False
    if not re.search(r"[a-zA-Z]+", pswd):
        return False
    if not re.search(r"[^a-z0-9A-Z]+", pswd):
        return False
    return True

def unarchive(unarchive_arg, host_post_info):
    start_time = datetime.now()
    host_post_info.start_time = start_time
    src = unarchive_arg.src
    dest = unarchive_arg.dest
    args = unarchive_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting unarchive %s to %s ... " % (src, dest), host_post_info, "INFO")
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
            description = "ERROR: unarchive %s to %s failed!" % (src, dest)
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: unarchive %s to %s" % (src, dest)
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
        if distro in RPM_BASED_OS:
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
name=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com
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
                if epel_repo_exist is False:
                    copy_arg = CopyArg()
                    copy_arg.src = "files/zstacklib/epel-release-source.repo"
                    copy_arg.dest = "/etc/yum.repos.d/"
                    copy(copy_arg, host_post_info)
                    # install epel-release
                    yum_enable_repo("epel-release", "epel-release-source", host_post_info)
                    set_ini_file("/etc/yum.repos.d/epel.repo", 'epel', "enabled", "1", host_post_info)
                for pkg in ["python-devel", "python-setuptools", "python-pip", "gcc", "autoconf"]:
                    yum_install_package(pkg, host_post_info)
                if distro_version >=7:
                    # to avoid install some pkgs on virtual router which release is Centos 6.x
                    yum_install_package("chrony", host_post_info)
                    yum_install_package("python-backports-ssl_match_hostname", host_post_info)
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
baseurl=http://{{ yum_server }}/zstack/static/zstack-repo/\$basearch/\$YUM0/
gpgcheck=0
enabled=0" >  /etc/yum.repos.d/zstack-mn.repo
               """
                    generate_mn_repo_template = jinja2.Template(generate_mn_repo_raw_command)
                    generate_mn_repo_command = generate_mn_repo_template.render({
                       'yum_server' : yum_server
                    })
                    run_remote_command(generate_mn_repo_command, host_post_info)
                    run_remote_command("sync", host_post_info)
                if 'qemu-kvm-ev-mn' in zstack_repo:
                    generate_kvm_repo_raw_command = """
echo -e "[qemu-kvm-ev-mn]
name=qemu-kvm-ev-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-repo/\$basearch/\$YUM0/Extra/qemu-kvm-ev/
gpgcheck=0
enabled=0" >  /etc/yum.repos.d/qemu-kvm-ev-mn.repo
               """
                    generate_kvm_repo_template = jinja2.Template(generate_kvm_repo_raw_command)
                    generate_kvm_repo_command = generate_kvm_repo_template.render({
                        'yum_server':yum_server
                    })
                    run_remote_command(generate_kvm_repo_command, host_post_info)
                    run_remote_command("sync", host_post_info)
                if 'mlnx-ofed' in zstack_repo:
                    generate_mlnx_repo_raw_command = """
echo -e "[mlnx-ofed-mn]
name=mlnx-ofed-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-repo/\$basearch/\$YUM0/Extra/mlnx-ofed/
gpgcheck=0
enabled=0" >  /etc/yum.repos.d/mlnx-ofed-mn.repo
               """
                    generate_mlnx_repo_template = jinja2.Template(generate_mlnx_repo_raw_command)
                    generate_mlnx_repo_command = generate_mlnx_repo_template.render({
                        'yum_server':yum_server
                    })
                    run_remote_command(generate_mlnx_repo_command, host_post_info)
                    run_remote_command("sync", host_post_info)

                # generate zstack experimental repo anyway
                generate_exp_repo_raw_command = """
echo -e "[zstack-experimental-mn]
name=zstack-experimental-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-repo/\$basearch/\$YUM0/Extra/zstack-experimental/
gpgcheck=0
enabled=0" >  /etc/yum.repos.d/zstack-experimental-mn.repo
               """
                generate_exp_repo_template = jinja2.Template(generate_exp_repo_raw_command)
                generate_exp_repo_command = generate_exp_repo_template.render({
                        'yum_server':yum_server
                })
                run_remote_command(generate_exp_repo_command, host_post_info)
                run_remote_command("sync", host_post_info)

                # install libselinux-python and other command system libs from user defined repos
                command = (
                          "yum clean --enablerepo=%s metadata &&  pkg_list=`rpm -q libselinux-python python-devel "
                          "python-setuptools python-pip gcc autoconf | grep \"not installed\" | awk"
                          " '{ print $2 }'` && for pkg in $pkg_list; do yum --disablerepo=* --enablerepo=%s install "
                          "-y $pkg; done;") % (zstack_repo, zstack_repo)
                run_remote_command(command, host_post_info)
                if distro_version >= 7:
                    # to avoid install some pkgs on virtual router which release is Centos 6.x
                    command = (
                                  "yum clean --enablerepo=%s metadata &&  pkg_list=`rpm -q python-backports-ssl_match_hostname chrony | "
                                  "grep \"not installed\" | awk"
                                  " '{ print $2 }'` && for pkg in $pkg_list; do yum --disablerepo=* --enablerepo=%s install "
                                  "-y $pkg; done;") % (zstack_repo, zstack_repo)
                    run_remote_command(command, host_post_info)
                    # enable chrony service and disable ntp for RedHat 7
                    service_status("ntpd", "state=stopped enabled=no", host_post_info, ignore_error=True)
                    service_status("chronyd", "state=restarted enabled=yes", host_post_info)


        elif distro in DEB_BASED_OS:
            command = '[ -f /etc/apt/sources.list ] && /bin/mv -f /etc/apt/sources.list /etc/apt/sources.list.zstack.bak || true'
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
            install_pkg_list =["python-dev", "python-setuptools", "python-pip", "gcc", "autoconf", "chrony"]
            apt_install_packages(install_pkg_list, host_post_info)

            # name: enable chrony service for Debian
            run_remote_command("update-rc.d chrony defaults; service ntp stop || true; service chrony restart", host_post_info)

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

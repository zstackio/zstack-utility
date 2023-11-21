#!/usr/bin/env python
# encoding: utf-8
import commands
import datetime
import functools
import logging
import re
from logging import handlers as logging_handlers
import json
import os
import sys
import threading

from ansible import constants as ansible_constants
from ansible import context as ansible_context
from ansible.executor import task_queue_manager as ansible_tqm
from ansible.module_utils.common import collections as ansible_collections
from ansible.inventory import manager as ansible_im
from ansible.parsing import dataloader as ansible_dataloader
from ansible.playbook import play as ansible_play
from ansible.plugins import cache
from ansible.plugins.cache import memory
from ansible.plugins import callback as ansible_callback
from ansible.vars import manager as ansible_vm
import jinja2
import time
import urllib2
import yaml


__metaclass__ = type
# set global default value
start_time = datetime.datetime.now()
logger = logging.getLogger("deploy-agent-Log")
pip_url = ""
zstack_root = ""
host = ""
pkg_zstacklib = ""
yum_server = ""
apt_server = ""
trusted_host = ""
uos = ['uos20', 'uos1021a']
kylin = ["ky10sp1", "ky10sp2", "ky10sp3"]
centos = ['c74', 'c76', 'c79', 'h76c', 'h79c', 'rl84', 'h84r']
enable_networkmanager_list = kylin + ["euler20", "uos1021a", "nfs4", "rl84", "oe2203sp1", "h2203sp1o"]
supported_arch_list = ["x86_64", "aarch64", "mips64el", "loongarch64"]

RPM_BASED_OS = ["kylin_zstack", "kylin_tercel", "kylin_sword", "kylin_lance",
                "alibaba", "centos", "openeuler", "uniontech_kongzi", "nfs",
                "redhat", "rocky", "helix"]
DEB_BASED_OS = ["ubuntu", "uos", "kylin4.0.2", "debian", "uniontech_fou"]
DISTRO_WITH_RPM_DEB = ["kylin", "uniontech"]

qemu_alias = {
    "ky10sp1": "qemu-kvm qemu-img",
    "ky10sp2": "qemu-kvm qemu-img",
    "ky10sp3": "qemu-kvm qemu-img",
    "uos20": "qemu-system",
    "c74": "qemu-kvm-ev",
    "c76": "qemu-kvm",
    "c79": "qemu-kvm",
    "euler20": "qemu",
    "oe2203sp1": "qemu",
    "h2203sp1o": "qemu",
    "uos1021a": "qemu-kvm",
    "nfs4": "qemu-kvm",
    'h76c': 'qemu-kvm',
    'h79c': 'qemu-kvm',
    'h84r': 'qemu-kvm'
}

ansible_constants.set_constant('HOST_KEY_CHECKING', False)
ansible_constants.set_constant('CACHE_PLUGIN', 'memory')
ansible_constants.set_constant('DEFAULT_GATHERING', 'smart')

_ansible_cache = {}


class MemCache(cache.BaseCacheModule):
    def __init__(self, *args, **kwargs):
        global _ansible_cache
        self._cache = _ansible_cache

    def get(self, key):
        return self._cache.get(key)

    def set(self, key, value):
        self._cache[key] = value

    def keys(self):
        return self._cache.keys()

    def contains(self, key):
        return key in self._cache

    def delete(self, key):
        del self._cache[key]

    def flush(self):
        self._cache = {}

    def copy(self):
        return self._cache.copy()

    def __getstate__(self):
        return self.copy()

    def __setstate__(self, data):
        self._cache = data


memory.CacheModule = MemCache


vm_cache = {}

class VM(ansible_vm.VariableManager):
    def __init__(self, loader, inventory, key):
        super(VM, self).__init__(loader, inventory)
        self._key = key

    def get_vars(self, *args, **kwargs):
        global vm_cache
        flag = str(args) + str(kwargs) + self._key
        if flag not in vm_cache:
            vars = super(VM, self).get_vars(*args, **kwargs)
            vm_cache[flag] = vars
        return vm_cache[flag]


ansible_module_cache = {}


class AnsibleModules(object):
    def __init__(self, runner_args):
        self.host_inventory = runner_args.host_post_info.host_inventory
        self.private_key = runner_args.host_post_info.private_key
        self.host = runner_args.host_post_info.host
        self.module_name = runner_args.module_name
        self.module_args = runner_args.module_args
        self.remote_port = runner_args.host_post_info.remote_port
        self.remote_user = runner_args.host_post_info.remote_user
        self.remote_pass = runner_args.host_post_info.remote_pass
        self.become = runner_args.host_post_info.become
        self.become_user = runner_args.host_post_info.become_user
        self.become_pass = runner_args.host_post_info.remote_pass
        self.transport = runner_args.host_post_info.transport
        self.environment = runner_args.host_post_info.environment

        global ansible_module_cache
        self.key = '%s-%s' % (self.host, threading.currentThread().ident)
        if self.key not in ansible_module_cache:
            ansible_module_cache[self.key] = {}

    @property
    def _passwords(self):
        return {
            'conn_pass': self.remote_pass,
            'become_pass': self.become_pass
        }

    @property
    def loader(self):
        if not hasattr(self, 'data_loader'):
            self.data_loader = ansible_dataloader.DataLoader()
        return self.data_loader

    @property
    def result_callback(self):
        if not hasattr(self, 'rc'):
            self.rc = ResultsCollectorJSONCallback()
        return self.rc

    @property
    def inventory(self):
        global ansible_module_cache
        if'inventory' not in ansible_module_cache[self.key]:
            inv = ansible_im.InventoryManager(
                loader=self.loader,
                sources=self.host_inventory)
            ansible_module_cache[self.key]['inventory'] = inv
        if not hasattr(self, 'inv'):
            self.inv = ansible_module_cache[self.key]['inventory']
        return self.inv

    @property
    def variable_manager(self):
        global ansible_module_cache
        if'variable_manager' not in ansible_module_cache[self.key]:
            vm = VM(loader=self.inventory._loader,
                    inventory=self.inventory,
                    key=self.key)
            ansible_module_cache[self.key]['variable_manager'] = vm
        if not hasattr(self, 'vm'):
            self.vm = ansible_module_cache[self.key]['variable_manager']
        return self.vm

    @property
    def task_queue_manager(self):
        if not hasattr(self, 'tqm'):
            self.tqm = ansible_tqm.TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variable_manager,
                loader=self.inventory._loader,
                passwords=self._passwords,
                stdout_callback=self.result_callback,
                run_additional_callbacks=False)
            self.tqm._callbacks_loaded = True
        return self.tqm


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
        self.zstack_releasever = None
        self.zstack_apt_source = None
        self.yum_server = None
        self.apt_server = None
        self.distro = None
        self.distro_version = None
        self.distro_release = None
        self.zstack_root = None
        self.host_post_info = None
        self.pip_url = None
        self.require_python_env = "true"
        self.host_info = None


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
        self.environment = {
            "LC_ALL": "C",
            "PATH": ("/usr/local/bin:/bin:/usr/bin:/usr/local/sbin:"
                     "/usr/sbin:/sbin"),
        }
        self.remote_user = 'root'
        self.remote_pass = None
        self.remote_port = None
        self.become = False
        self.become_exe = '/usr/bin/sudo'
        self.become_user = 'root'
        self.private_key = None
        self.host_inventory = None
        self.host = None
        self.host_uuid = None
        self.vip = None
        self.chrony_servers = None
        self.post_url = ""
        self.post_label = None
        self.post_label_param = None
        self.start_time = None
        self.rabbit_password = None
        self.mysql_password = None
        self.mysql_userpassword = None
        self.transport = 'smart'
        self.releasever = None


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


class ModProbeArg(object):
    def __init__(self):
        self.name = None
        self.state = None
        self.params = None


class ZstackRunnerArg(object):
    def __init__(self):
        self.host_post_info = None
        self.module_name = None
        self.module_args = None


class ResultsCollectorJSONCallback(ansible_callback.CallbackBase):
    def __init__(self, *args, **kwargs):
        super(ResultsCollectorJSONCallback, self).__init__(*args, **kwargs)
        self.ret = {}

    def v2_runner_on_unreachable(self, result):
        host = result._host
        r = result._result
        r.update({'failed': True, 'failed_reason': 'unreachable'})
        self.ret[host.get_name()] = r

    def v2_runner_on_ok(self, result):
        host = result._host
        r = result._result
        r.update({'failed': False, 'failed_reason': ''})
        self.ret[host.get_name()] = r

    def v2_runner_on_failed(self, result, *args, **kwargs):
        host = result._host
        r = result._result
        r.update({'failed': True, 'failed_reason': 'failed'})
        self.ret[host.get_name()] = r

    def v2_runner_on_skipped(self, result):
        host = result._host
        r = result._result
        r.update({'failed': False, 'failed_reason': ''})
        self.ret[host.get_name()] = r

    def fetch_result(self):
        return {
            'dark': {},
            'contacted': self.ret
        }


class ZstackRunner(object):
    def __init__(self, runner_args):
        self.host_inventory = runner_args.host_post_info.host_inventory
        self.private_key = runner_args.host_post_info.private_key
        self.host = runner_args.host_post_info.host
        self.module_name = runner_args.module_name
        self.module_args = runner_args.module_args
        self.remote_port = runner_args.host_post_info.remote_port
        self.remote_user = runner_args.host_post_info.remote_user
        self.remote_pass = runner_args.host_post_info.remote_pass
        self.become = runner_args.host_post_info.become
        self.become_user = runner_args.host_post_info.become_user
        self.become_pass = runner_args.host_post_info.remote_pass
        self.transport = runner_args.host_post_info.transport
        self.environment = runner_args.host_post_info.environment

        ansible_context.CLIARGS = ansible_collections.ImmutableDict(
            connection=self.transport,
            become=self.become,
            become_user=self.become_user,
            private_key_file=self.private_key,
            become_method='sudo',
            ssh_extra_args='-C -o ControlMaster=auto -o ControlPersist=1800s',
        )
        self.ansible_module = AnsibleModules(runner_args)

    def run(self):
        action = {'module': self.module_name}
        if self.module_name == 'shell':
            action['_raw_params'] = self.module_args
        else:
            action['args'] = self.module_args
        play_source = dict(
            hosts=self.host,
            tasks=[{'action': action,
                    'register': 'shell_out',
                    'environment': self.environment,
                    }],
            vars={'ansible_user': self.remote_user,
                  'ansible_port': self.remote_port,
                  'ansible_pipelining': True}
        )
        play = ansible_play.Play().load(
            play_source,
            variable_manager=self.ansible_module.variable_manager,
            loader=self.ansible_module.loader)
        try:
            ret = self.ansible_module.task_queue_manager.run(play)
        finally:
            self.ansible_module.task_queue_manager.cleanup()
            if self.ansible_module.tqm._loader:
                self.ansible_module.tqm._loader.cleanup_all_tmp_files()
        return self.ansible_module.result_callback.fetch_result()


def banner(text, ch='*', length=78):
    star_text = "**"
    spaced_text = ' %s ' % text
    for i in range(1, len(text)):
        star_text = star_text + "*"
    banner = spaced_text.center(length, ch)
    banner_star = star_text.center(length, ch)
    logger.info(banner_star)
    logger.info(banner)
    logger.info(banner_star)


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
            error(("The task failed, please make sure the host can be "
                   "connected and no error happened, then try again. "
                   "Below is detail:\n %s") % e)
        return inner
    return wrap


def create_log(logger_dir):
    if not os.path.exists(logger_dir):
        os.makedirs(logger_dir)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler = logging_handlers.RotatingFileHandler(
        logger_dir + "/deploy.log", maxBytes=10 * 1024 * 1024,
        backupCount=30)
    handler.setFormatter(fmt)
    logger.addHandler(handler)


def with_arch(todo_list=supported_arch_list, host_arch=None):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            if set(todo_list) - set(supported_arch_list):
                error("Unknown arch in {}".format(todo_list))
            if not host_arch:
                error("Host arch is needed.")
            if host_arch in todo_list:
                return f(*args, **kwargs)
            else:
                logger.info("Skip function[{}] on {} host.".format(
                    f.__name__, host_arch))
        return inner
    return wrap


def on_redhat_based(distro=None, exclude=[]):
    def wrap(f):
        @functools.wraps(f)
        def innner(*args, **kwargs):
            if not distro:
                error("Distro info is needed.")
            if distro in list(set(RPM_BASED_OS) - set(exclude)):
                return f(*args, **kwargs)
        return innner
    return wrap


def on_debian_based(distro=None, exclude=[]):
    def wrap(f):
        @functools.wraps(f)
        def innner(*args, **kwargs):
            if not distro:
                error("Distro info is needed.")
            if distro in list(set(DEB_BASED_OS) - set(exclude)):
                return f(*args, **kwargs)
        return innner
    return wrap


def get_mn_release():
    # file /etc/zstack-release from zstack-release.rpm
    # file content like: ZStack release c76
    return commands.getoutput("awk '{print $3}' /etc/zstack-release").strip()


def get_host_releasever(host_info):
    supported_release_info = {
        "kylin_tercel tercel 10": "ky10sp1",
        "kylin_sword sword 10": "ky10sp2",
        "kylin_zstack zstack 10": "ky10sp2",
        "kylin_lance lance 10": "ky10sp3",
        "uniontech fou 20": "uos20",
        "redhat maipo 7.4": "ky10", # old kylinV10, oem 7.4 incompletely
        "centos core 7.9.2009": "c79",
        "centos core 7.6.1810": "c76",
        "centos core 7.4.1708": "c74",
        "centos core 7.2.1511": "c74",  # c74 for old releases
        "centos core 7.1.1503": "c74",
        'helix core 7.6c': 'h76c',
        'helix core 7.9c': 'h79c',
        'helix green obsidian 8.4r': 'h84r',
        "helix lts-sp1 22.03": "h2203sp1o",
        "openeuler lts-sp1 20.03": "euler20",
        "openeuler lts-sp1 22.03": "oe2203sp1",
        "uos fou 20": "uos20",
        "uniontech_kongzi kongzi 20": "uos1021a",
        "rocky green obsidian 8.4": "rl84",
    }
    # _key = " ".join(ansible_distribution).lower()
    _releasever = supported_release_info.get(host_info.ansible_distribution)
    return _releasever if _releasever else get_mn_release()


def post_msg(msg, post_url):
    '''post message to zstack, label for support i18n'''
    if msg.parameters is not None:
        if type(msg.parameters) is str:
            msg.parameters = msg.parameters.split(',')
        data = json.dumps(
            {"label": msg.label,
             "level": msg.level,
             "parameters": msg.parameters})
    else:
        data = json.dumps({"label": msg.label, "level": msg.level})
    if post_url != "":
        if msg.label is not None:
            try:
                headers = {"content-type": "application/json"}
                req = urllib2.Request(post_url, data, headers)
                response = urllib2.urlopen(req)
                response.close()
            except urllib2.URLError as e:
                logger.debug(e.reason)
                logger.warning(("Post msg failed! Please check the "
                                "post_url: %s and check the server "
                                "status") % post_url)
        else:
            logger.warning("No label defined for message")
    else:
        logger.info("Warning: no post_url defined by user")
    # This output will capture by management log for debug
    if msg.level == "ERROR":
        error(msg.details)
    elif msg.level == "WARNING":
        logger.warning(msg.details)
    else:
        logger.info(msg.details)


def handle_ansible_start(ansible_start):
    msg = Msg()
    msg.details = ("Can't start ansible process to "
                   "host: %s Detail: %s  \n") % (ansible_start.host,
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
    end_time = datetime.datetime.now()
    # Fix python2.6 compatible issue: no total_seconds() attribute for
    # timedelta
    td = end_time - start_time
    cost_time = (td.microseconds + (td.seconds + td.days *
                 24 * 3600) * 10 ** 6) / 10 ** 6.0 * 1000
    msg.label = host_post_info.post_label
    msg.parameters = host_post_info.post_label_param
    if 'stdout' in result['contacted'][host]:
        msg.details = "[ HOST: %s ] " % host_post_info.host + \
            description + "stdout: " + result['contacted'][host]['stdout']
    else:
        msg.details = "[ HOST: %s ] " % host_post_info.host + description

    if 'stderr' in result['contacted'][host]:
        msg.details += " error: " + result['contacted'][host]['stderr']
    elif 'msg' in result['contacted'][host]:
        msg.details += " error: " + result['contacted'][host]['msg']

    msg.level = "ERROR"
    post_msg(msg, post_url)


def handle_ansible_info(details, host_post_info, level):
    msg = Msg()
    post_url = host_post_info.post_url
    start_time = host_post_info.start_time
    end_time = datetime.datetime.now()
    # Fix python2.6 compatible issue: no total_seconds() attribute for
    # timedelta
    td = end_time - start_time
    cost_time = (td.microseconds + (td.seconds + td.days *
                 24 * 3600) * 10 ** 6) / 10 ** 6.0 * 1000
    if "SUCC" in details:
        msg.details = "[ HOST: %s ] " % host_post_info.host + \
            details + " [ cost %sms to finish ]" % int(cost_time)
    else:
        msg.details = "[ HOST: %s ] " % host_post_info.host + details
    msg.level = level
    msg.label = host_post_info.post_label
    msg.parameters = host_post_info.post_label_param
    post_msg(msg, post_url)


def agent_install(install_arg, host_post_info):
    host_post_info.post_label = "ansible.install.agent"
    host_post_info.post_label_param = [install_arg.agent_name]
    handle_ansible_info("INFO: Start to install %s ......" %
                        install_arg.agent_name, host_post_info, "INFO")
    pip_install_arg = PipInstallArg()
    pip_install_arg.extra_args = "\"--trusted-host %s -i %s\"" % (
        install_arg.trusted_host, install_arg.pip_url)
    # upgrade only
    if install_arg.init_install is False:
        host_post_info.post_label = "ansible.upgrade.agent"
        msg = "INFO: Only need to upgrade %s ......" % install_arg.agent_name
        handle_ansible_info(msg, host_post_info, "INFO")
        pip_install_arg.extra_args = "\"--trusted-host %s -i %s -U \"" % (
            install_arg.trusted_host, install_arg.pip_url)

    pip_install_arg.name = "%s/%s" % (install_arg.agent_root,
                                      install_arg.pkg_name)
    pip_install_arg.virtualenv = install_arg.virtenv_path
    pip_install_arg.virtualenv_site_packages = \
        install_arg.virtualenv_site_packages
    if pip_install_package(pip_install_arg, host_post_info) is False:
        command = "rm -rf %s && rm -rf %s" % (
            install_arg.virtenv_path, install_arg.agent_root)
        run_remote_command(command, host_post_info)
        error("agent %s install failed" % install_arg.agent_name)


def yum_enable_repo(name, enablerepo, host_post_info):
    '''install package from enablerepo'''
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.yum.enable.repo"
    host_post_info.post_label_param = name
    handle_ansible_info("INFO: Starting enable yum repo %s ... " %
                        name, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'yum'
    runner_args.module_args = 'name={} enablerepo={} state=present'.format(
        name, enablerepo)
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
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
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.yum.search.pkg"
    host_post_info.post_label_param = name
    handle_ansible_info("INFO: Searching yum package %s ... " %
                        name, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = 'rpm -q %s' % name
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
        ret = result['contacted'][host]
        if 'rc' not in ret:
            logger.warning(("Maybe network problem, try again now, ansible "
                            "reply is below:\n %s") % result)
            raise Exception(result)
        else:
            status = ret['rc']
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
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.script.run"
    host_post_info.post_label_param = [file, host]
    handle_ansible_info("INFO: Running script %s on host %s ... " %
                        (file, host), host_post_info, "INFO")
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
        ret = result['contacted'][host]
        if 'rc' not in ret:
            logger.warning(("Network problem, try again now, ansible reply "
                            "is below:\n %s") % result)
            raise Exception(result)
        else:
            status = ret['rc']
            if status == 0:
                details = "SUCC: The script %s on host %s finish " % (
                    file, host)
                host_post_info.post_label = "ansible.script.run.succ"
                host_post_info.post_label_param = file
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                description = "ERROR: The script %s failed on host %s" % (
                    file, host)
                host_post_info.post_label = "ansible.script.run.fail"
                host_post_info.post_label_param = file
                handle_ansible_failed(description, result, host_post_info)


@retry(times=3, sleep_time=3)
def yum_install_package(name, host_post_info, ignore_error=False,
                        force_install=False):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.yum.start.install.package"
    host_post_info.post_label_param = name
    msg = "INFO: Starting yum install package %s ... " % (name,
                                                          host_post_info)
    handle_ansible_info(msg, "INFO")
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
        ret = result['contacted'][host]
        if 'rc' not in ret:
            logger.warning(("Network problem, try again now, ansible reply "
                            "is below:\n %s") % result)
            raise Exception(result)
        else:
            status = ret['rc']
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
                args = 'name=%s disable_gpg_check=yes state=latest' % name
                runner_args.module_args = args
                zstack_runner = ZstackRunner(runner_args)
                result = zstack_runner.run()
                logger.debug(result)
                ret = result['contacted'][host]
                if ret.get('failed', True) and not ignore_error:
                    description = "ERROR: YUM install package %s failed" % name
                    host_post_info.post_label = "ansible.yum.install.pkg.fail"
                    handle_ansible_failed(description, result, host_post_info)
                else:
                    details = \
                        "SUCC: yum install package %s successfully" % name
                    host_post_info.post_label = "ansible.yum.install.pkg.succ"
                    handle_ansible_info(details, host_post_info, "INFO")
                    return True


@retry(times=3, sleep_time=3)
def yum_remove_package(name, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.post_label_param = name
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.yum.start.remove.pkg"
    handle_ansible_info("INFO: yum start removing package %s ... " %
                        name, host_post_info, "INFO")
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
    ret = result['contacted'][host]
    if 'rc' not in ret:
        logger.warning(("Network problem, try again now, ansible reply "
                        "is below:\n %s") % result)
        raise Exception(result)
    else:
        status = ret['rc']
        if status == 0:
            details = "INFO: yum removing %s ... " % name
            host_post_info.post_label = "ansible.yum.remove.pkg"
            handle_ansible_info(details, host_post_info, "INFO")
            runner_args = ZstackRunnerArg()
            runner_args.host_post_info = host_post_info
            runner_args.module_name = 'yum'
            runner_args.module_args = 'name=' + name + ' state=absent'
            zstack_runner = ZstackRunner(runner_args)
            result = zstack_runner.run()
            logger.debug(result)
            ret = result['contacted'][host]
            if ret.get('failed', True):
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
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.check.pkgs.exist"
    post_name_list = ','.join(name_list)
    host_post_info.post_label_param = post_name_list
    handle_ansible_info("INFO: check all packages %s exist in system... " %
                        name_list, host_post_info, "INFO")
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
            ret = result['contacted'][host]
            if 'rc' not in ret:
                logger.warning(("Maybe network problem, try again now, "
                                "ansible reply is below:\n %s") % result)
                raise Exception(result)
            else:
                status = ret['rc']
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
        start_time = datetime.datetime.now()
        host_post_info.start_time = start_time
        host = host_post_info.host
        post_url = host_post_info.post_url
        host_post_info.post_label_param = name
        host_post_info.post_label = "ansible.apt.install.pkg"
        msg = "INFO: starting apt install package %s ... " % name
        handle_ansible_info(msg, host_post_info, "INFO")
        runner_args = ZstackRunnerArg()
        runner_args.host_post_info = host_post_info
        runner_args.module_name = 'apt'
        runner_args.module_args = 'name={} state=present '.format(name)
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
            ret = result['contacted'][host]
            if ret.get('failed', True):
                description = "ERROR: apt install package %s failed" % name
                host_post_info.post_label = "ansible.apt.install.pkg.fail"
                handle_ansible_failed(description, result, host_post_info)
            elif 'changed' in ret:
                details = "SUCC: apt install package %s successfully" % name
                host_post_info.post_label = "ansible.apt.install.pkg.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                description = ("ERROR: apt install package %s meet "
                               "unknown issue: %s") % (name, result)
                host_post_info.post_label = "ansible.apt.install.pkg.issue"
                host_post_info.post_label_param = None
                handle_ansible_failed(description, result, host_post_info)
    all_pkg_exist = check_pkg_status(name_list, host_post_info)
    if all_pkg_exist is False:
        command = ("apt-get clean && apt-get update "
                   "--allow-insecure-repositories "
                   "-o Acquire::http::No-Cache=True --fix-missing")
        apt_update_status = run_remote_command(
            command, host_post_info, return_status=True)
        if apt_update_status is False:
            error(("apt-get update on host %s failed, please update the "
                   "repo on the host manually and try again.")
                  % host_post_info.host)
        for pkg in name_list:
            _apt_install_package(pkg, host_post_info)


def apt_update_packages(name_list, host_post_info):
    pkg_list = ' '.join(name_list)
    command = ("apt-get clean && apt-get install -y "
               "--allow-unauthenticated --only-upgrade {}").format(pkg_list)
    apt_update_status = run_remote_command(
        command, host_post_info, return_status=True)
    if apt_update_status is False:
        error(("apt-get update packages on host {} failed, please update "
               "the repo on the host manually and try again.").format(
                   host_post_info.host))


IS_REMOTE_PIP_READY = {}


def pip_install_package(pip_install_arg, host_post_info):
    global IS_REMOTE_PIP_READY
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    name = pip_install_arg.name
    host = host_post_info.host
    post_url = host_post_info.post_url
    version = pip_install_arg.version
    if pip_install_arg.extra_args is not None:
        if 'pip' not in name:
            extra_args = '\"' + '--disable-pip-version-check ' + \
                pip_install_arg.extra_args.split('"')[1] + '\"'
        else:
            extra_args = '\"' + pip_install_arg.extra_args.split('"')[1] + '\"'
    else:
        extra_args = None
    virtualenv = pip_install_arg.virtualenv
    virtualenv_site_packages = pip_install_arg.virtualenv_site_packages
    host_post_info.post_label = "ansible.pip.install.pkg"
    host_post_info.post_label_param = name
    handle_ansible_info("INFO: pip installing package %s ..." %
                        name, host_post_info, "INFO")
    if host not in IS_REMOTE_PIP_READY.keys() or not IS_REMOTE_PIP_READY[host]:
        command = "which pip || ln -s /usr/bin/pip2 /usr/bin/pip"
        run_remote_command(command, host_post_info)
        IS_REMOTE_PIP_READY[host] = True
    param_dict = {}
    param_dict_raw = dict(version=version,
                          extra_args=extra_args,
                          virtualenv=virtualenv,
                          virtualenv_site_packages=virtualenv_site_packages)
    for item in param_dict_raw:
        if param_dict_raw[item] is not None:
            param_dict[item] = param_dict_raw[item]
    option = 'name=' + name + ' ' + \
        ' '.join(['{0}={1}'.format(k, v) for k, v in param_dict.iteritems()])
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            command = "pip2 uninstall -y %s" % name
            run_remote_command(command, host_post_info)
            description = "ERROR: pip install package %s failed" % name
            host_post_info.post_label = "ansible.pip.install.pkg.fail"
            handle_ansible_failed(description, result, host_post_info)
            return False
        else:
            details = "SUCC: pip install package %s successfully " % name
            host_post_info.post_label = "ansible.pip.install.pkg.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def cron(name, arg, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.cron.set.task"
    host_post_info.post_label_param = arg
    handle_ansible_info("INFO: starting set cron task %s ... " %
                        arg, host_post_info, "INFO")
    args = 'name=%s %s' % (name, arg)
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
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
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    src = copy_arg.src
    dest = copy_arg.dest
    args = copy_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.copy.start"
    host_post_info.post_label_param = [src, dest]
    handle_ansible_info("INFO: starting copy %s to %s ... " %
                        (src, dest), host_post_info, "INFO")
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = "ERROR: copy %s to %s failed" % (src, dest)
            host_post_info.post_label = "ansible.copy.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            change_status = "changed:" + \
                str(ret['changed'])
            details = ("SUCC: copy %s to %s successfully, the change "
                       "status is %s") % (src, dest, change_status)
            host_post_info.post_label = "ansible.copy.succ"
            host_post_info.post_label_param = [src, dest, change_status]
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the copy result to outside
            return change_status


def copy_to_remote(src, dest, args, host_post_info):
    copy_arg = CopyArg()
    copy_arg.src = src
    copy_arg.dest = dest
    copy_arg.args = args
    return copy(copy_arg, host_post_info)


def sync(sync_arg, host_post_info):
    '''The copy module recursively copy facility does not scale to
    lots (>hundreds) of files.
    so we add sync module which will use ansible synchronize module,
    which is a wrapper around rsync.'''
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    src = sync_arg.src
    dest = sync_arg.dest
    args = sync_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: Starting sync %s to %s ... " %
                        (src, dest), host_post_info, "INFO")
    if args is not None:
        copy_args = 'src=' + src + ' dest=' + dest + ' ' + args
    else:
        copy_args = 'src=' + src + ' dest=' + dest
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'synchronize'
    runner_args.module_args = sync_arg
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = "ERROR: sync %s to %s failed!" % (src, dest)
            handle_ansible_failed(description, result, host_post_info)
        else:
            change_status = "changed:" + \
                str(ret['changed'])
            details = "SUCC: sync %s to %s, the change status is %s" % (
                src, dest, change_status)
            handle_ansible_info(details, host_post_info, "INFO")
            return change_status


def fetch(fetch_arg, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    src = fetch_arg.src
    dest = fetch_arg.dest
    args = fetch_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.fetch.start"
    host_post_info.post_label_param = [src, dest]
    handle_ansible_info("INFO: starting fetch %s to %s ... " %
                        (src, dest), host_post_info, "INFO")
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = "ERROR: fetch from %s to %s failed" % (src, dest)
            host_post_info.post_label = "ansible.fetch.fail"
            handle_ansible_failed(description, result, host_post_info)
            sys.exit(1)
        else:
            change_status = "changed:" + \
                str(ret['changed'])
            details = "SUCC: fetch %s to %s, the change status is %s" % (
                src, dest, change_status)
            host_post_info.post_label = "ansible.fetch.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            # pass the fetch result to outside
            return change_status


def check_host_reachable(host_post_info, warning=False):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    handle_ansible_info(
        "INFO: Starting check host %s is reachable ..." % host,
        host_post_info,
        "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'ping'
    runner_args.module_args = ''
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    ret = result['contacted'][host]
    if result['contacted'] == {}:
        return False
    elif ret.get('failed', True):
        return False
    elif ret['ping'] == 'pong':
        return True
    else:
        if warning is False:
            error("Unknown error when check host %s is reachable" % host)
        else:
            warn("Unknown error when check host %s is reachable" % host)
        return False


@retry(times=3, sleep_time=3)
def run_remote_command(command, host_post_info, return_status=False,
                       return_output=False, stderr_match_regexp=''):
    '''return status all the time except return_status is False,
    return output is set to True'''
    if 'yum' in command:
        set_yum0 = '''rpm -q zstack-release >/dev/null && releasever=`awk '{print $3}' /etc/zstack-release`;\
                    export YUM0=$releasever; grep $releasever /etc/yum/vars/YUM0 || echo $releasever > /etc/yum/vars/YUM0;'''
        command = set_yum0 + command
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    if host_post_info.post_label is None:
        host_post_info.post_label = "ansible.command"
        host_post_info.post_label_param = command
    handle_ansible_info(
        "INFO: starting run command [ %s ] ..." % command,
        host_post_info,
        "INFO")
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
        ret = result['contacted'][host]
        if 'rc' not in ret:
            logger.warning(("Network problem, try again now, ansible "
                            "reply is below:\n %s") % result)
            raise Exception(result)
        else:
            status = ret['rc']
            if status == 0:
                if ret['stderr'] and stderr_match_regexp and re.search(stderr_match_regexp, ret['stderr']):
                    description = \
                        "ERROR: run shell command: %s failed!" % command
                    host_post_info.post_label = \
                        host_post_info.post_label + ".fail"
                    handle_ansible_failed(description, result, host_post_info)
                    sys.exit(1)

                details = "SUCC: run shell command: %s successfully " % command
                host_post_info.post_label = host_post_info.post_label + ".succ"
                handle_ansible_info(details, host_post_info, "INFO")
                if return_output is False:
                    return True
                else:
                    return (True, ret['stdout'])
            else:
                if return_status is False:
                    description = \
                        "ERROR: run shell command: %s failed!" % command
                    host_post_info.post_label = \
                        host_post_info.post_label + ".fail"
                    handle_ansible_failed(description, result, host_post_info)
                    sys.exit(1)
                else:
                    details = "ERROR: shell command %s failed " % command
                    host_post_info.post_label = \
                        host_post_info.post_label + ".fail"
                    handle_ansible_info(details, host_post_info, "WARNING")
                    if return_output is False:
                        return False
                    else:
                        return (False, ret['stdout'])


@retry(times=3, sleep_time=3)
def check_pip_version(version, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.check.pip.version"
    host_post_info.post_label_param = version
    handle_ansible_info("INFO: check pip version %s exist ..." %
                        version, host_post_info, "INFO")
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
        ret = result['contacted'][host]
        if 'rc' not in ret:
            logger.warning(("Network problem, try again now, ansible reply "
                            "is below:\n %s") % result)
            raise Exception(result)
        else:
            status = ret['rc']
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
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.check.file.dir.exist.start"
    host_post_info.post_label_param = name
    handle_ansible_info(
        "INFO: starting check file or dir %s exist ... " % name,
        host_post_info,
        "INFO")
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            logger.warning("Check file or dir %s status failed" % name)
            sys.exit(1)
        if 'stat' not in ret:
            logger.warning(("Network problem, try again now, ansible reply "
                            "is below:\n %s") % result)
            raise Exception(result)
        else:
            status = ret['stat']['exists']
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
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.change.file.attribute.start"
    host_post_info.post_label_param = file
    handle_ansible_info(
        "INFO: starting change file attribute %s ... " % file,
        host_post_info,
        "INFO")
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            details = "INFO: %s not be changed" % file
            host_post_info.post_label = "ansible.change.file.attribute.fail"
            handle_ansible_info(details, host_post_info, "INFO")
            return False
        else:
            details = "INFO: %s changed successfully" % file
            host_post_info.post_label = "ansible.change.file.attribute.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


class HostInfo(object):
    def __init__(self):
        self.distro = ''
        self.major_version_str = ''
        self.distro_release = ''
        self.distro_version = ''
        self.host_arch = ''
        self.cpu_info = ''
        self.kernel_version = ''

    @property
    def ansible_distribution(self):
        return '{distro} {release} {version}'.format(
            distro=self.distro,
            release=self.distro_release,
            version=self.distro_version).lower()

    @property
    def major_version(self):
        return int(self.major_version_str)


@retry(times=3, sleep_time=3)
def get_remote_host_info_obj(host_post_info):
    start_time = datetime.datetime.now()
    host_info = HostInfo()
    host = host_post_info.host
    host_post_info.start_time = start_time
    host_post_info.post_label = "ansible.get.host.info"
    host_post_info.post_label_param = host
    handle_ansible_info(
        "INFO: starting get remote host %s info ... " % host,
        host_post_info,
        "INFO")

    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'setup'
    runner_args.module_args = ('gather_subset=machine,processor '
                               'filter=ansible_dist*,ansible_machine,'
                               'ansible_processor,ansible_kernel')
    zstack_runner = ZstackRunner(runner_args)
    result = zstack_runner.run()
    logger.debug(result)
    if result['contacted'] == {}:
        ansible_start = AnsibleStartResult()
        ansible_start.host = host_post_info.host
        ansible_start.post_url = host_post_info.post_url
        ansible_start.result = result
        handle_ansible_start(ansible_start)
        # return

    ret = result['contacted'][host]
    if 'ansible_facts' in ret:
        facts = ret['ansible_facts']
        host_info.distro = facts['ansible_distribution'].split()[0].lower()
        host_info.major_version_str = \
            facts['ansible_distribution_major_version']
        host_info.distro_release = facts['ansible_distribution_release']
        host_info.distro_version = facts['ansible_distribution_version']
        host_info.cpu_info = ' '.join(str(p) for p in
                                      facts['ansible_processor']).lower()
        host_info.host_arch = facts['ansible_machine']
        host_info.kernel_version = facts['ansible_kernel']

        host_post_info.post_label = "ansible.get.host.info.succ"
        handle_ansible_info(
            "SUCC: Get remote host %s info successful" % host,
            host_post_info,
            "INFO")

        if host_info.distro in DISTRO_WITH_RPM_DEB:
            host_info.distro = ('%s_%s' % (host_info.distro,
                                           host_info.distro_release)).lower()
    else:
        host_post_info.post_label = "ansible.get.host.info.fail"
        logger.warning("get_remote_host_info on host %s failed!" % host)
        raise Exception(result)
    return host_info


def set_ini_file(file, section, option, value, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.set.ini.file"
    host_post_info.post_label_param = [file, section]
    handle_ansible_info("INFO: starting update file %s section %s ... " % (
        file, section), host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'ini_file'
    runner_args.module_args = 'dest=' + file + ' section=' + \
        section + ' option=' + option + " value=" + value
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
        details = "SUCC: update file: %s option: %s value %s" % (
            file, option, value)
        host_post_info.post_label = "ansible.set.ini.file.succ"
        host_post_info.post_label_param = [file, option, value]
        handle_ansible_info(details, host_post_info, "INFO")
    return True


@retry(times=3, sleep_time=3)
def check_and_install_virtual_env(version, trusted_host, pip_url,
                                  host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.check.install.virtualenv"
    host_post_info.post_label_param = version
    handle_ansible_info("INFO: starting install virtualenv-%s ... " %
                        version, host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'shell'
    runner_args.module_args = 'virtualenv --version | grep %s' % version
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
        ret = result['contacted'][host]
        if 'rc' not in ret:
            logger.warning(("Network problem, try again now, ansible "
                            "reply is below:\n %s") % result)
            raise Exception(result)
        else:
            status = ret['rc']
            if status == 0:
                details = "SUCC: the virtualenv-%s exist in system" % version
                host_post_info.post_label = \
                    "ansible.check.install.virtualenv.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True
            else:
                extra_args = "\"--trusted-host %s -i %s \"" % (
                    trusted_host, pip_url)
                pip_install_arg = PipInstallArg()
                pip_install_arg.extra_args = extra_args
                pip_install_arg.version = version
                pip_install_arg.name = "virtualenv"
                return pip_install_package(pip_install_arg, host_post_info)


def service_status(name, args, host_post_info, ignore_error=False):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.service.status"
    host_post_info.post_label_param = [name, args]
    handle_ansible_info("INFO: changing %s service status to %s " %
                        (name, args), host_post_info, "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'service'
    runner_args.module_args = "name=%s " % name + args
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
                ret = result['contacted'][host]
                if ret.get('failed', True):
                    details = "ERROR: change service %s status failed!" % name
                    host_post_info.post_label = "ansible.service.status.fail"
                    handle_ansible_info(details, host_post_info, "WARNING")
                else:
                    details = ("SUCC: change service %s status to %s "
                               "successfully") % (name, args)
                    host_post_info.post_label = "ansible.service.status.succ"
                    handle_ansible_info(details, host_post_info, "INFO")
        except:
            logger.debug(
                "WARNING: The service %s status changed failed" % name)
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
            ret = result['contacted'][host]
            if ret.get('failed', True):
                description = ("ERROR: change service %s status to %s "
                               "failed!") % (name, args)
                host_post_info.post_label = "ansible.service.status.fail"
                handle_ansible_failed(description, result, host_post_info)
            else:
                details = ("SUCC: change service %s status to %s "
                           "successfully") % (name, args)
                host_post_info.post_label = "ansible.service.status.succ"
                handle_ansible_info(details, host_post_info, "INFO")
                return True


def replace_content(dest, args, host_post_info):
    '''
    This module will replace all instances of a pattern within a file
    dest required
    The file to modify. Before Ansible 2.3 this option was only usable as dest,
    destfile and name.
    args:
    regexp string required
    The regular expression to look for in the contents of the file. Uses Python
    regular expressions; see http://docs.python.org/2/library/re.html.
    replace string
    The string to replace regexp matches.
    May contain backreferences that will get expanded with the regexp capture
    groups if the regexp matches.
    If not set, matches are removed entirely.
    '''
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    handle_ansible_info("INFO: replace file %s content" % dest,
                        host_post_info,
                        "INFO")
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'replace'
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = "ERROR: replace file %s content failed" % dest
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: replace file %s content successfully" % dest
            handle_ansible_info(details, host_post_info, "INFO")
            command = "rm -rf %s"
            return True


def update_file(dest, args, host_post_info):
    '''
    This module will search a file for lines, and ensure that it is present or
    absent. This is primarily useful
    when you want to change lines in a file
    '''
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.update.file"
    host_post_info.post_label_param = dest
    handle_ansible_info("INFO: updating file %s" %
                        dest, host_post_info, "INFO")
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = "ERROR: update file %s failed" % dest
            host_post_info.post_label = "ansible.update.file.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: update file %s successfully" % dest
            host_post_info.post_label = "ansible.update.file.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def set_selinux(args, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.set.selinux"
    host_post_info.post_label_param = args
    handle_ansible_info("INFO: set selinux status to %s" %
                        args, host_post_info, "INFO")
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = "ERROR: set selinux status to %s failed" % args
            host_post_info.post_label = "ansible.set.selinux.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: set selinux to %s successfully" % args
            host_post_info.post_label = "ansible.set.selinux.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def authorized_key(user, key_path, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    if not os.path.exists(key_path):
        error("key_path %s is not exist!" % key_path)
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.add.key"
    host_post_info.post_label_param = [key_path, host]
    handle_ansible_info("INFO: updating key %s to host %s" %
                        (key_path, host), host_post_info, "INFO")
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
        runner_args.module_name = 'authorized_key'
        runner_args.module_args = args
        zstack_runner = ZstackRunner(runner_args)
        result = zstack_runner.run()
        logger.debug(result)
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = "ERROR: update key %s to host %s failed" % (
                key_path, host)
            host_post_info.post_label = "ansible.add.key.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: update key %s to host %s successfully" % (
                key_path, host)
            host_post_info.post_label = "ansible.add.key.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def unarchive(unarchive_arg, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    src = unarchive_arg.src
    dest = unarchive_arg.dest
    args = unarchive_arg.args
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.unarchive"
    host_post_info.post_label_param = [src, dest]
    handle_ansible_info("INFO: starting unarchive %s to %s ... " %
                        (src, dest), host_post_info, "INFO")
    if args is not None:
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = "ERROR: unarchive %s to %s failed" % (src, dest)
            host_post_info.post_label = "ansible.unarchive.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: unarchive %s to %s successfully" % (src, dest)
            host_post_info.post_label = "ansible.unarchive.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def modprobe(modprobe_arg, host_post_info):
    start_time = datetime.datetime.now()
    host_post_info.start_time = start_time
    name = modprobe_arg.name
    state = modprobe_arg.state
    params = modprobe_arg.params
    host = host_post_info.host
    post_url = host_post_info.post_url
    host_post_info.post_label = "ansible.modprobe"
    host_post_info.post_label_param = [name, state]
    handle_ansible_info(
        "INFO: starting change kernel module %s to %s ... " % (name, state),
        host_post_info,
        "INFO")
    if params is not None:
        modprobe_args = 'name=%s state=%s params=%s' % (name, state, params)
    else:
        modprobe_args = 'name=%s state=%s' % (name, state)
    runner_args = ZstackRunnerArg()
    runner_args.host_post_info = host_post_info
    runner_args.module_name = 'modprobe'
    runner_args.module_args = modprobe_args
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
        ret = result['contacted'][host]
        if ret.get('failed', True):
            description = ("ERROR: change kernel module %s status to %s "
                           "failed ") % (name, state)
            host_post_info.post_label = "ansible.modprobe.fail"
            handle_ansible_failed(description, result, host_post_info)
        else:
            details = "SUCC: change kernel module %s to %s successfully" % (
                name, state)
            host_post_info.post_label = "ansible.modprobe.succ"
            handle_ansible_info(details, host_post_info, "INFO")
            return True


def do_enable_ntp(trusted_host, host_post_info, distro):
    logger.debug("Starting enable ntp service")

    def get_ha_mn_list(conf_file):
        if os.path.isfile(conf_file):
            with open(conf_file, 'r') as fd:
                ha_conf_content = yaml.load(fd.read())
                mn_list = ha_conf_content['host_list'].split(',')
            return mn_list
        else:
            return []

    def sync_date(distro):
        if trusted_host != host_post_info.host:
            if host_post_info.host not in commands.getoutput(
                    "ip a  | grep 'inet ' | awk '{print $2}'"):
                if host_post_info.host not in get_ha_mn_list(
                        "/var/lib/zstack/ha/ha.yaml"):
                    if distro in RPM_BASED_OS:
                        service_status(
                            "ntpd", "state=stopped enabled=yes", host_post_info)
                    elif distro in DEB_BASED_OS:
                        service_status(
                            "ntp", "state=stopped enabled=yes", host_post_info)
                    command = "ntpdate %s" % trusted_host
                    run_remote_command(command, host_post_info, True, True)
        if distro in RPM_BASED_OS:
            service_status(
                "ntpd", "state=restarted enabled=yes", host_post_info)
        elif distro in DEB_BASED_OS:
            service_status(
                "ntp", "state=restarted enabled=yes", host_post_info)

    if trusted_host != host_post_info.host:
        if host_post_info.host not in commands.getoutput(
                "ip a  | grep 'inet ' | awk '{print $2}'"):
            if host_post_info.host not in get_ha_mn_list(
                    "/var/lib/zstack/ha/ha.yaml"):
                replace_content(
                    "/etc/ntp.conf",
                    "regexp='^server ' replace='#server '",
                    host_post_info)
                update_file("/etc/ntp.conf",
                            "regexp='#server %s' state=absent" %
                            trusted_host, host_post_info)
                update_file("/etc/ntp.conf",
                            "line='server %s'" % trusted_host, host_post_info)
    replace_content("/etc/ntp.conf",
                    ("regexp='restrict default nomodify notrap nopeer noquery'"
                     " replace='restrict default nomodify notrap nopeer' "
                     "backup=yes"),
                    host_post_info)
    if distro in RPM_BASED_OS:
        command = (" iptables -C INPUT -p udp -m state --state NEW -m udp "
                   "--dport 123 -j ACCEPT 2>&1 || (iptables -I INPUT -p udp "
                   "-m state --state NEW -m udp --dport 123 -j ACCEPT && "
                   "service iptables save)")
        run_remote_command(command, host_post_info)
    elif distro in DEB_BASED_OS:
        command = (" ! iptables -C INPUT -p udp -m state --state NEW -m udp "
                   "--dport 123 -j ACCEPT 2>&1 || (iptables -I INPUT -p udp "
                   "-m state --state NEW -m udp --dport 123 -j ACCEPT && "
                   "/etc/init.d/iptables-persistent save)")
        run_remote_command(command, host_post_info)
    sync_date(distro)


def do_deploy_chrony(host_post_info, svrs, distro):
    # ensure config file not locked by user
    run_remote_command(("[ -f /etc/chrony.conf ] || touch /etc/chrony.conf && "
                        "true; chattr -i /etc/chrony.conf || true"),
                       host_post_info)
    replace_content("/etc/chrony.conf",
                    "regexp='^server ' replace='#server '",
                    host_post_info)
    for svr in svrs:
        update_file("/etc/chrony.conf",
                    "regexp='#server %s' state=absent" % svr,
                    host_post_info)
        update_file("/etc/chrony.conf", "line='server %s iburst'" % svr,
                    host_post_info)

    command = ("systemctl disable ntpd || true; systemctl enable chronyd; "
               "systemctl restart chronyd || true")
    host_post_info.post_label = "ansible.shell.enable.chronyd"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)


def enable_chrony(trusted_host, host_post_info, distro):
    if not host_post_info.chrony_servers:
        return

    svrs = host_post_info.chrony_servers.split(',')
    if host_post_info.host in svrs:
        return

    logger.debug("Starting enable chrony service")
    do_deploy_chrony(host_post_info, svrs, distro)


def enforce_history(trusted_host, host_post_info):
    enforce_history_cmd = '''
mkdir -p /var/log/history.d/
cat << 'EOF' > /etc/logrotate.d/history
/var/log/history.d/history {
    create 0666 root root
    monthly
    rotate 6
    create
    dateext
    compress
    minsize 1M
}'''
    host_post_info.post_label = "ansible.shell.enforce.history"
    host_post_info.post_label_param = None
    run_remote_command(enforce_history_cmd, host_post_info)

    enforce_history_cmd = '''
cat << 'EOF' > /etc/profile.d/history.sh
shopt -s histappend
HISTTIMEFORMAT='%F %T '
HISTSIZE="5000"
HISTFILESIZE=5000
PROMPT_COMMAND='(umask 000; msg=$(history 1 | { read x y; echo $y; }); echo [$(who am i | awk "{print \$(NF-2),\$(NF-1),\$NF}")] [$(whoami)@`pwd`]" $msg" >>/var/log/history.d/history)'
export HISTTIMEFORMAT HISTSIZE HISTFILESIZE PROMPT_COMMAND'''
    host_post_info.post_label = "ansible.shell.enforce.history"
    host_post_info.post_label_param = None
    run_remote_command(enforce_history_cmd, host_post_info)


def check_umask(host_post_info):
    check_umask_cmd = ("[[ ! `umask` == '0022' ]] && echo 'umask 0022' >> "
                       "/etc/bashrc || true")
    host_post_info.post_label = "ansible.shell.check.umask"
    host_post_info.post_label_param = None
    run_remote_command(check_umask_cmd, host_post_info)


def upgrade_to_helix(host_info, host_post_info):
    releasever = get_host_releasever(host_info)
    if releasever in ['c76', 'c79', 'rl84', 'oe2203sp1']:
        distro_name = {
            'c76': 'h76c',
            'c79': 'h79c',
            'rl84': 'h84r',
            'oe2203sp1': 'h2203sp1o'
    # if releasever in ['c76', 'c79', 'oe2203sp1']:
    #     distro_name = {
    #         'c76': 'h76c',
    #         'c79': 'h79c',
    #         'oe2203sp1': 'h2203sp1o'
            }.get(releasever)
        if not os.path.exists('/opt/zstack-dvd/%s/%s' % (host_info.host_arch,
                                                         distro_name)):
            return host_info
        pkg_name = {
            'c76': ['helix-release-7-6c.0.h7.helix.x86_64.rpm'],
            'c79': ['helix-release-7-9c.0.h7.helix.x86_64.rpm'],
            'rl84': ['helix-gpg-keys-8.4r-36.el8.noarch.rpm',
                     'helix-repos-8.4r-36.el8.noarch.rpm',
                     'helix-release-8.4r-36.el8.noarch.rpm'],
            'oe2203sp1': ['helix-gpg-keys-1.0-3.5.aarch64.rpm',
                          'helix-latest-release-1.0-158479755920.03.aarch64.rpm',
                          'helix-repos-1.0-3.5.aarch64.rpm']
        }.get(releasever)
        # helix_release_pkg = '/opt/zstack-dvd/x86_64/%s/Packages/%s' % (
        #     distro_name, pkg_name)
        helix_pkgs = ['/opt/zstack-dvd/%s/%s/Packages/%s' % (
            host_info.host_arch, distro_name, x) for x in pkg_name]
        dest_pkg_path = ' '.join(['/opt/%s' % x for x in pkg_name])
        install_cmd = ('yum install -y %s && sed -i "/distroverpkg=/d; '
                       '/bugtracker_url=/d" /etc/yum.conf') % dest_pkg_path

        for helix_pkg in helix_pkgs:
            copy_arg = CopyArg()
            copy_arg.src = helix_pkg
            copy_arg.dest = '/opt'
            copy(copy_arg, host_post_info)
        run_remote_command(install_cmd, host_post_info)

        # flush ansible cache after upgrading
        global _ansible_cache
        _ansible_cache = {}
        host_info = get_remote_host_info_obj(host_post_info)

    return host_info


def install_release_on_host(is_rpm, host_info, host_post_info):
    releasever = get_host_releasever(host_info)
    if is_rpm:
        release_name_mapping = {
            'rl84': 'el8',
            'h76c': 'h7',
            'h79c': 'h7',
            'h84r': 'h8',
            'h2203sp1o': 'h2203sp1'}
        release_name = release_name_mapping.get(releasever, 'el7')
        pkg_name = 'zstack-release-{0}-1.{1}.zstack.noarch.rpm'.format(releasever, release_name)
        src_pkg = '/opt/zstack-dvd/{0}/{1}/Packages/{2}'.format(host_info.host_arch, releasever, pkg_name)
        install_cmd = ("[[ x`rpm -qi zstack-release |awk -F ':' '/Version/{print $2}' |sed 's/ //g'` == x%s ]] || "
                       "(rpm -e zstack-release; rpm -i /opt/%s);") % (releasever, pkg_name)
    else:
        src_pkg = '/opt/zstack-dvd/{0}/{1}/Packages/zstack-release_{1}_all.deb'.format(host_info.host_arch, releasever)
        install_cmd = "dpkg -l zstack-release || dpkg -i /opt/zstack-release_{}_all.deb".format(releasever)
    copy_arg = CopyArg()
    copy_arg.src = src_pkg
    copy_arg.dest = '/opt'
    copy(copy_arg, host_post_info)
    run_remote_command(install_cmd, host_post_info)


def repair_rpmdb_if_damaged(host_post_info):
    cmd = "yum --disablerepo=* --enablerepo=zstack-local list >/dev/null 2>&1 || " \
          "(rm -f /var/lib/rpm/_db.*; rpm --rebuilddb)"
    run_remote_command(cmd, host_post_info)


class ZstackLib(object):
    def __init__(self, args):
        self.distro = args.distro
        self.distro_release = args.distro_release
        self.distro_version = args.distro_version
        self.zstack_repo = args.zstack_repo
        self.zstack_apt_source = args.zstack_apt_source
        zstack_root = args.zstack_root
        self.host_post_info = args.host_post_info
        trusted_host = args.trusted_host
        pip_url = args.pip_url
        pip_version = "7.0.3"
        self.yum_server = args.yum_server
        self.zstack_releasever = args.zstack_releasever
        apt_server = args.apt_server
        current_dir = os.path.dirname(os.path.realpath(__file__))
        # require_python_env for deploy host which may not need python
        # environment, default is true
        if args.require_python_env is not None:
            self.require_python_env = args.require_python_env
        else:
            self.require_python_env = "true"

        # enforce history
        enforce_history(trusted_host, self.host_post_info)
        check_umask(self.host_post_info)
        configure_hosts(self.host_post_info)

        host_info = args.host_info
        if not host_info:
            host_info = get_remote_host_info_obj(self.host_post_info)

        if self.distro in RPM_BASED_OS:
            repair_rpmdb_if_damaged(self.host_post_info)
            install_release_on_host(True, host_info, self.host_post_info)
            # always add aliyun yum repo
            self.generate_aliyun_yum_repo()

            user_defined = self.zstack_repo == "false"
            if user_defined:
                # zstack_repo is empty, will use system repo
                # libselinux-python depend by ansible copy/file/template module
                # when selinux enabled on host
                yum_install_package("libselinux-python", self.host_post_info)
                # Enable extra repo for install centos-release-qemu-ev in
                # kvm.py
                if self.distro_version >= 7:
                    self.copy_redhat_yum_repo()
                # install epel-release
                self.enable_epel_yum_repo()
                set_ini_file("/etc/yum.repos.d/epel.repo", 'epel',
                             "enabled", "1", self.host_post_info)
            else:
                # user defined zstack_repo, will generate repo defined in
                # zstack_repo
                if '163' in self.zstack_repo:
                    self.generate_163_yum_repo()
                if 'zstack-mn' in self.zstack_repo:
                    self.generate_mn_yum_repo()
                if 'qemu-kvm-ev-mn' in self.zstack_repo and (
                        self.distro == 'nfs' or self.distro_version >= 7):
                    self.generate_qemu_kvm_ev_yum_repo()
                if 'mlnx-ofed' in self.zstack_repo:
                    self.generate_mlnx_yum_repo()

                # generate zstack experimental repo anyway
                self.generate_zstack_experimental_yum_repo()

            # install libselinux-python and other command system libs from user
            # defined repos
            self.install_rpm_based_os_requirements(
                self.zstack_repo, user_defined)
        elif self.distro in DEB_BASED_OS:
            install_release_on_host(False, host_info, self.host_post_info)
            self.update_debian_repo(
                self.zstack_apt_source,
                self.host_post_info,
                self.distro_release,
                self.zstack_releasever)
            self.enable_debian_services(
                self.host_post_info,
                self.require_python_env,
                self.distro)
        else:
            error("ERROR: Unsupported distribution %s" % self.distro)

    def _python_rpm_set(self):
        python_requirement_set = {
            "python2-devel",
            "python2-setuptools",
        }

        if self.distro == 'nfs' or self.distro_version >= 7:
            python_requirement_set.add("python2-pip")
        else:
            python_requirement_set.add("python-pip")

        if self.distro_version >= 7:
            # to avoid install some pkgs on virtual router which release is
            # Centos 6.x
            python_requirement_set.add("python2-backports-ssl_match_hostname")

        return python_requirement_set

    def _basic_rpm_set(self):
        basic = {
            "gcc",
            "autoconf",
            "vim-minimal",
        }

        if self.distro in ["kylin_zstack", "kylin_tercel", "kylin_sword"]:
            basic.add("chrony")
            basic.add("iptables")
            basic.add("python2-libselinux")
            return basic

        basic.add("libselinux-python")
        if self.distro_version >= 7:
            # to avoid install some pkgs on virtual router which release is
            # Centos 6.x
            basic.add("chrony")
            basic.add("iptables-services")

        return basic

    # install system packages required by cloud

    def install_rpm_based_os_requirements(self, zstack_repo,
                                          skip_clean_yum_metadata=True):
        required_rpm_set = self._basic_rpm_set()

        # imagestore do not need python env will skip python packages
        if self.require_python_env == "true":
            required_rpm_set.update(self._python_rpm_set())

        before_install_command = ""
        if not skip_clean_yum_metadata:
            before_install_command += \
                "yum clean --enablerepo=%s metadata && " % zstack_repo

        # install libselinux-python and other command system libs from user
        # defined repos
        selinux_pkgs = [p for p in required_rpm_set if "selinux" in p]
        command = "yum --disablerepo=* --enablerepo={0} install -y {1} || true" \
                  .format(zstack_repo, " ".join(selinux_pkgs))
        run_remote_command(command, self.host_post_info)

        command = ("%s pkg_list=`rpm -q %s | grep \"not installed\" | awk"
                   " '{ print $2 }'` && for pkg in $pkg_list; do yum"
                   " --disablerepo=* --enablerepo=%s install -y $pkg;"
                   " done;") % (before_install_command,
                                " ".join(required_rpm_set),
                                zstack_repo)
        self.host_post_info.post_label = "ansible.shell.install.pkg"
        self.host_post_info.post_label_param = ",".join(required_rpm_set)
        run_remote_command(command, self.host_post_info, stderr_match_regexp=r'.*pre-existing rpmdb problem.*(?:lvm2|librados).*')
        if "chrony" in required_rpm_set:
            # enable chrony service for RedHat
            enable_chrony(trusted_host, self.host_post_info, self.distro)

    def generate_zstack_experimental_yum_repo(self):
        generate_exp_repo_raw_command = """
echo -e "[zstack-experimental-mn]
name=zstack-experimental-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-repo/\$basearch/\$YUM0/Extra/zstack-experimental/
gpgcheck=0
module_hotfixes=true
enabled=0" >  /etc/yum.repos.d/zstack-experimental-mn.repo; sync
               """
        generate_exp_repo_template = jinja2.Template(
            generate_exp_repo_raw_command)
        generate_exp_repo_command = generate_exp_repo_template.render({
            'yum_server': self.yum_server
        })
        run_remote_command(generate_exp_repo_command, self.host_post_info)

    # generate mlnx yum repo
    def generate_mlnx_yum_repo(self):
        generate_mlnx_repo_raw_command = """
echo -e "[mlnx-ofed-mn]
name=mlnx-ofed-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-repo/\$basearch/\$YUM0/Extra/mlnx-ofed/
gpgcheck=0
module_hotfixes=true
enabled=0" >  /etc/yum.repos.d/mlnx-ofed-mn.repo; sync
               """
        generate_mlnx_repo_template = jinja2.Template(
            generate_mlnx_repo_raw_command)
        generate_mlnx_repo_command = generate_mlnx_repo_template.render({
            'yum_server': self.yum_server
        })
        run_remote_command(generate_mlnx_repo_command, self.host_post_info)

    # generate qemu-kvm-ev.repo
    def generate_qemu_kvm_ev_yum_repo(self):
        generate_kvm_repo_raw_command = """
echo -e "[qemu-kvm-ev-mn]
name=qemu-kvm-ev-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-repo/\$basearch/\$YUM0/Extra/qemu-kvm-ev/
gpgcheck=0
module_hotfixes=true
enabled=0" >  /etc/yum.repos.d/qemu-kvm-ev-mn.repo; sync
               """
        generate_kvm_repo_template = jinja2.Template(
            generate_kvm_repo_raw_command)
        generate_kvm_repo_command = generate_kvm_repo_template.render({
            'yum_server': self.yum_server
        })
        self.host_post_info.post_label = "ansible.shell.deploy.repo"
        self.host_post_info.post_label_param = "qemu-kvm-ev-mn"
        run_remote_command(generate_kvm_repo_command, self.host_post_info)

    # generate zstack-mn.repo
    def generate_mn_yum_repo(self):
        generate_mn_repo_raw_command = """
echo -e "[zstack-mn]
name=zstack-mn
baseurl=http://{{ yum_server }}/zstack/static/zstack-repo/\$basearch/\$YUM0/
gpgcheck=0
module_hotfixes=true
enabled=0" >  /etc/yum.repos.d/zstack-mn.repo; sync
               """
        generate_mn_repo_template = jinja2.Template(
            generate_mn_repo_raw_command)
        generate_mn_repo_command = generate_mn_repo_template.render({
            'yum_server': self.yum_server
        })
        run_remote_command(generate_mn_repo_command, self.host_post_info)

    def generate_yum_repo_config_from_zstack_lib(self, repo_conf_name):
        yum_repo_file_path = self.find_preferred_yum_repo_conf_path(
            repo_conf_name)

        # read yum repo content from repo_file
        yum_repo_contents = []
        with open(yum_repo_file_path, 'r') as f:
            yum_repo_contents = f.readlines()

        if len(yum_repo_contents) == 0:
            raise Exception(
                "failed to read yum repo content from %s" % yum_repo_file_path)

        # copy module may not supported due to libselinux-python requirement
        # manually create yum repo to /etc/yum.repos.d/
        command = """
cat << 'EOF' > /etc/yum.repos.d/%s
%s
EOF
""" % (repo_conf_name, "".join(yum_repo_contents))
        run_remote_command(command, self.host_post_info)

    # copy zstack-163-yum.repo to /etc/yum.repos.d/
    def generate_163_yum_repo(self):
        self.generate_yum_repo_config_from_zstack_lib("zstack-163-yum.repo")

    # copy zstack-aliyun-yum.repo to /etc/yum.repos.d/
    def generate_aliyun_yum_repo(self):
        self.generate_yum_repo_config_from_zstack_lib("zstack-aliyun-yum.repo")

    def find_preferred_yum_repo_conf_path(self, conf_file_name):
        repo_conf_path = "files/zstacklib/%s/%s/%s" % (self.distro,
                                                       self.distro_version,
                                                       conf_file_name)
        # if distro based config not exist, use default repo config
        logger.debug("try to read yum repo config file %s" % repo_conf_path)
        if os.path.exists(repo_conf_path):
            return repo_conf_path

        logger.debug("yum repo config file %s not exists" % repo_conf_path)
        repo_conf_path = "files/zstacklib/%s" % conf_file_name
        logger.debug("try to read yum repo config file %s" % repo_conf_path)
        if not os.path.exists(repo_conf_path):
            raise Exception("cannot find yum repo config file %s" %
                            conf_file_name)

        return repo_conf_path

    # copy zstack-redhat-yum.repo to /etc/yum.repos.d/
    def copy_redhat_yum_repo(self):
        copy_arg = CopyArg()
        copy_arg.src = "files/zstacklib/zstack-redhat.repo"
        copy_arg.dest = "/etc/yum.repos.d/"
        copy(copy_arg, self.host_post_info)

    def enable_epel_yum_repo(self):
        epel_repo_exist = file_dir_exist(
            "path=/etc/yum.repos.d/epel.repo", self.host_post_info)
        if epel_repo_exist:
            return

        # read eple release source from local
        repo_epel = "files/zstacklib/epel-release-source.repo"
        self.generate_yum_repo_config_from_zstack_lib(repo_epel)
        # install epel-release
        yum_enable_repo("epel-release", "epel-release-source",
                        self.host_post_info)

    def enable_debian_services(self, host_post_info, require_python_env, distro):
        # install dependency packages for Debian based OS
        service_status('unattended-upgrades', 'state=stopped enabled=no',
                       host_post_info, ignore_error=True)
        # apt_update_cache(86400, host_post_info)
        if require_python_env == "true":
            install_pkg_list = ["python-dev", "python-setuptools",
                                "python-pip", "gcc", "g++", "autoconf",
                                "chrony", "iptables-persistent"]
            apt_install_packages(install_pkg_list, host_post_info)
            enable_chrony(trusted_host, host_post_info, distro)

    def update_debian_repo(self, zstack_apt_source, host_post_info,
                           distro_release, zstack_releasever):
        # copy apt-conf
        copy_arg = CopyArg()
        copy_arg.src = "files/kvm/apt.conf"
        copy_arg.dest = "/etc/apt/apt.conf"
        copy(copy_arg, host_post_info)

        # backup sources.list
        command = '[ -f /etc/apt/sources.list ] && /bin/mv -f /etc/apt/sources.list /etc/apt/sources.list.zstack.bak || true'
        host_post_info.post_label = "ansible.shell.backup.file"
        host_post_info.post_label_param = "/etc/apt/srouces.list"
        run_remote_command(command, host_post_info)

        update_aptsource_command_base = """
cat > /etc/apt/sources.list << EOF
deb http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }} main restricted universe multiverse
deb http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-security main restricted universe multiverse
deb http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-updates main restricted universe multiverse
deb http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-proposed main restricted universe multiverse
deb http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-backports main restricted universe multiverse
deb-src http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }} main restricted universe multiverse
deb-src http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-security main restricted universe multiverse
deb-src http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-updates main restricted universe multiverse
deb-src http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-proposed main restricted universe multiverse
deb-src http://mirrors.{{ zstack_apt_source }}.com/ubuntu/ {{ DISTRIB_CODENAME }}-backports main restricted universe multiverse
"""

        if 'ali' in str(zstack_apt_source):
            update_repo_command_template = jinja2.Template(
                update_aptsource_command_base)
            update_repo_command = update_repo_command_template.render({
                'zstack_apt_source': 'aliyun',
                'DISTRIB_CODENAME': distro_release
            })
            host_post_info.post_label = "ansible.shell.deploy.repo"
            host_post_info.post_label_param = "aliyun"
            run_remote_command(update_repo_command, host_post_info)
        elif '163' in str(zstack_apt_source):
            update_repo_command_template = jinja2.Template(
                update_aptsource_command_base)
            update_repo_command = update_repo_command_template.render({
                'zstack_apt_source': '163',
                'DISTRIB_CODENAME': distro_release
            })
            host_post_info.post_label = "ansible.shell.deploy.repo"
            host_post_info.post_label_param = "163"
            run_remote_command(update_repo_command, host_post_info)
        else:
            update_aptsource_command = """
basearch=`uname -m`;
cat > /etc/apt/sources.list.d/zstack-mn.list << EOF
deb http://{{ apt_server }}/zstack/static/zstack-repo/$basearch/{{ zstack_releasever }}/ Packages/
deb http://{{ apt_server }}/zstack/static/zstack-repo/$basearch/{{ zstack_releasever }}/ qemu_libvirt/
                """
            update_repo_command_template = jinja2.Template(
                update_aptsource_command)
            update_repo_command = update_repo_command_template.render({
                'apt_server': apt_server,
                'zstack_releasever': zstack_releasever
            })
            host_post_info.post_label = "ansible.shell.deploy.repo"
            host_post_info.post_label_param = "zstack"
            run_remote_command(update_repo_command, host_post_info)

    def install_debian_system_requirements(self):
        # install dependency packages for Debian based OS
        service_status('unattended-upgrades', 'state=stopped enabled=no',
                       self.host_post_info, ignore_error=True)
        # apt_update_cache(86400, host_post_info)
        install_pkg_list = ["python-dev", "python-setuptools",
                            "python-pip", "gcc", "autoconf", "chrony"]
        apt_install_packages(install_pkg_list, self.host_post_info)


def configure_hosts(host_post_info):
    configure_hosts_cmd = ('grep `hostname` /etc/hosts >/dev/null || echo'
                           ' "127.0.0.1 `hostname` # added by ZStack" >>'
                           ' /etc/hosts')
    run_remote_command(configure_hosts_cmd, host_post_info)


def remote_bin_installed(host_post_info, bin_name, return_status=False):
    command = "which {}".format(bin_name)
    status = run_remote_command(command, host_post_info, return_status)
    return status


def get_qemu_img_version(host_post_info):
    command = "qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1"
    (status, qemu_img_version) = run_remote_command(command, host_post_info, False, True)
    return status, qemu_img_version


def main():
    # Reserve for test api
    pass


if __name__ == "__main__":
    main()

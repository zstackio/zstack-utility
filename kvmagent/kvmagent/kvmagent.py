'''

@author: frank
'''
import re
import time
import psutil

from zstacklib.utils import plugin
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import jsonobject
from zstacklib.utils import daemon
from zstacklib.utils import linux
from zstacklib.utils import qemu
import os.path
import traceback
import pprint
import functools
import subprocess
import platform

logger = log.get_logger(__name__)


class KvmError(Exception):
    '''kvm error'''

class BlockJobError(Exception):
    '''block job error'''

class KvmAgent(plugin.Plugin):
    '''
    classdocs
    '''

    def __init__(self):
        '''
        Constructor
        '''
        linux.recover_fake_dead('kvmagent')
        super(KvmAgent, self).__init__()

ha_cleanup_handlers = [] # type: list[callable]

def register_ha_cleanup_handler(handler):
    # type: (callable) -> None
    logger.debug('start registered ha cleanup handler %s' % handler)
    global ha_cleanup_handlers
    ha_cleanup_handlers.append(handler)
    logger.debug('success registered ha cleanup handlers %s' % ha_cleanup_handlers)

metric_collectors = []  # type: list[callable]

def register_prometheus_collector(collector):
    # type: (callable) -> None
    logger.debug('start registered %s' % collector)
    global metric_collectors
    metric_collectors.append(collector)
    logger.debug('success registered %s' % metric_collectors)

_rest_service = None
_tf_service = None
_qemu_path = None
host_arch = linux.HOST_ARCH
NM_DISTROS = ('kylin', 'alinux')

def new_rest_service(config={}):
    global _rest_service
    if not _rest_service:
        _rest_service = KvmRESTService(config)
    return _rest_service

def get_http_server():
    return _rest_service.http_server

def set_tf_service(service):
    global _tf_service
    _tf_service = service

def get_tf_service():
    return _tf_service

def get_host_yum_release():
    return subprocess.getoutput("rpm -q zstack-release 2>/dev/null | awk -F'-' '{print $3}'").strip()

def get_host_distribution():
    return platform.freedesktop_os_release().get('ID', '').lower()

def get_host_os_type():
    os_info = platform.freedesktop_os_release()
    dist, version = os_info['ID'], re.sub(r'[a-zA-Z]+$', '', os_info['VERSION_ID'])
    if dist.lower() in linux.DIST_WITH_RPM_DEB:
        dist = "%s%s" % (dist.lower(), version)
    is_debian = any([x in dist.lower() for x in linux.DEB_BASED_OS])
    return 'debian' if is_debian else 'redhat'


def get_qemu_path():
    global _qemu_path
    if not _qemu_path:
        try:
            _qemu_path = qemu.get_path()
        except Exception as e:
            raise KvmError(str(e))

    return _qemu_path
        
    
class KvmRESTService(object):
    http_server = http.HttpServer()
    http_server.logfile_path = log.get_logfile_path()
    
    NO_DAEMON = 'no_deamon'
    PLUGIN_PATH = 'plugin_path'
    WORKSPACE = 'workspace'
    
    def __init__(self, config={}):
        self.config = config
        plugin_path = self._get_config(self.PLUGIN_PATH)
        if not plugin_path:
            plugin_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plugins')
        self.plugin_path = plugin_path
        self.plugin_rgty = plugin.PluginRegistry(self.plugin_path)
    
    def _get_config(self, name):
        return None if name not in self.config else self.config[name]
    
    def start(self, in_thread=True):
        config = {}
        self.plugin_rgty.configure_plugins(config)
        self.plugin_rgty.start_plugins()
        if in_thread:
            self.http_server.start_in_thread()
        else:
            self.http_server.start()
    
    def stop(self):
        self.plugin_rgty.stop_plugins()
        self.http_server.stop()

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

class AgentCommand(object):
    def __init__(self):
        pass

def _build_url_for_test(paths):
    builder = http.UriBuilder('http://localhost:7070')
    for p in paths:
        builder.add_path(p)
    return builder.build()

def replyerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            rsp = AgentResponse()
            rsp.success = False
            rsp.error = str(e)
            logger.warn(err)
            return jsonobject.dumps(rsp)
    return wrap


def deleteImage(path):
     linux.rm_file_checked(path)
     logger.debug('successfully delete %s' % path)
     if (path.endswith('.qcow2')):
        imfFiles = [".imf",".imf2"]
        for f in imfFiles:
            filePath = path.replace(".qcow2", f)
            linux.rm_file_force(filePath)
     linux.rm_file_force('%s.json' % path)
     pdir = os.path.dirname(path)
     linux.rmdir_if_empty(pdir)


class KvmDaemon(daemon.Daemon):
    STOP_TIMEOUT = 30

    def __init__(self, pidfile, py_process_name, config={}):
        super(KvmDaemon, self).__init__(pidfile, py_process_name)

    @staticmethod
    def _process_is_alive(process):
        try:
            # is_running() hides AccessDenied while constructing its fresh
            # Process. Explicit creation-time reads must fail, not imply exit.
            if psutil.Process(process.pid).create_time() != process.create_time():
                return False
            if process.status() != psutil.STATUS_ZOMBIE:
                return True
            # A zombie leader may still have live workers. Only an inspectable
            # group containing the leader alone proves that the agent exited.
            threads = process.threads()
            if psutil.Process(process.pid).create_time() != process.create_time():
                return False
            if (len(threads) != 1 or threads[0].id != process.pid or
                    process.num_threads() != 1):
                raise KvmError('Cannot establish thread-group exit for zombie pid %s' % process.pid)
            return False
        except psutil.ZombieProcess:
            # ZombieProcess subclasses NoSuchProcess, but is not proof of exit.
            raise KvmError('Cannot inspect thread-group exit for zombie pid %s' % process.pid)
        except psutil.NoSuchProcess:
            return False

    def _get_agent_process(self, pid):
        try:
            process = psutil.Process(pid)
            # Process.__init__ suppresses AccessDenied when reading this field;
            # require a known identity before relying on its PID reuse checks.
            process.create_time()
            if not self._process_is_alive(process):
                return None
            try:
                command = process.cmdline()
            except psutil.ZombieProcess:
                if not self._process_is_alive(process):
                    return None
                raise
            if not command:
                raise KvmError('Cannot identify live process with pid %s' % pid)
            if (len(command) != 4 or
                    not re.match(r'^python(?:\d+(?:\.\d+)*)?$', os.path.basename(command[0])) or
                    command[1] != '-c' or command[3] not in ('start', 'restart') or
                    not re.match(r'^from\s+kvmagent\s+import\s+kdaemon\s*;\s*kdaemon\.main\(\)\s*;?\s*$', command[2])):
                raise KvmError('Refusing to stop non-KVM command with pid %s' % pid)
            return process if self._process_is_alive(process) else None
        except psutil.ZombieProcess:
            raise KvmError('Cannot identify zombie process with pid %s' % pid)
        except psutil.NoSuchProcess:
            return None

    def _process_exists(self, pid):
        try:
            return self._process_is_alive(psutil.Process(pid))
        except psutil.ZombieProcess:
            raise KvmError('Cannot inspect zombie process with pid %s' % pid)
        except psutil.NoSuchProcess:
            return False

    def stop_agent_by_pid(self, pid, wait_stop):
        process = self._get_agent_process(pid)
        if process is None:
            return
        started = time.monotonic()
        killed = False
        try:
            # Retain this Process: terminate/kill also check PID + create_time.
            process.terminate()
            while self._process_is_alive(process):
                elapsed = time.monotonic() - started
                if elapsed >= self.STOP_TIMEOUT:
                    raise KvmError('Timed out after %s seconds stopping KVM agent pid %s' %
                                   (self.STOP_TIMEOUT, pid))
                if not killed and elapsed >= wait_stop:
                    process.kill()
                    killed = True
                time.sleep(min(0.1, self.STOP_TIMEOUT - elapsed))
        except psutil.ZombieProcess:
            raise KvmError('Cannot establish thread-group exit for zombie pid %s' % pid)
        except psutil.NoSuchProcess:
            if self._process_is_alive(process):
                raise
        print("Stop Daemon Successfully")

    def run(self):
        self.agent = new_rest_service()
        self.agent.start(in_thread=False)

SEND_COMMAND_URL = 'SEND_COMMAND_URL'
HOST_UUID = 'HOST_UUID'
VERSION = 'VERSION'
kvmagent_physical_memory_usage_alarm_threshold = None
kvmagent_physical_memory_usage_hardlimit = None

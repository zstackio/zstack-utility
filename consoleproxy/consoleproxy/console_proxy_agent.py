from zstacklib.utils import plugin
from zstacklib.utils import http
from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import jsonobject
from zstacklib.utils import daemon
from zstacklib.utils import linux
from zstacklib.utils import filedb
from zstacklib.utils import lock
from zstacklib.utils.bash import *
import os
import os.path
import atexit
import time
import traceback
import pprint
import functools
import sys
import subprocess
import threading

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

class AgentCommand(object):
    def __init__(self):
        pass

class EstablishProxyCmd(AgentCommand):
    def __init__(self):
        super(EstablishProxyCmd, self).__init__()
        self.token = None
        self.targetSchema = None
        self.targetHostname = None
        self.targetPort = None
        self.proxyHostname = None
        self.vmUuid = None
        self.scheme = None
        self.idleTimeout = None

class EstablishProxyRsp(AgentResponse):
    def __init__(self):
        super(EstablishProxyRsp, self).__init__()
        self.proxyPort = None
        self.token = None

class CheckAvailabilityCmd(AgentCommand):
    def __init__(self):
        super(CheckAvailabilityCmd, self).__init__()
        self.proxyHostname = None
        self.proxyPort = None
        self.targetPort = None
        self.targetHostname = None
        self.targetSchema = None
        self.scheme = None
        self.token = None
        self.proxyIdentity = None
        self.vncTokenTimeout = None

class CheckAvailabilityRsp(AgentResponse):
    def __init__(self):
        super(CheckAvailabilityRsp, self).__init__()
        self.available = None

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

class ConsoleProxyError(Exception):
    ''' console proxy error '''

class ConsoleProxyAgent(object):

    PORT = 7758
    http_server = http.HttpServer(PORT)
    http_server.logfile_path = log.get_logfile_path()

    CHECK_AVAILABILITY_PATH = "/console/check"
    ESTABLISH_PROXY_PATH = "/console/establish"
    DELETE_PROXY_PATH = "/console/delete"
    PING_PATH = "/console/ping"

    TOKEN_FILE_DIR = "/var/lib/zstack/consoleProxy/"
    PROXY_LOG_DIR = "/var/log/zstack/consoleProxy/"
    DB_NAME = "consoleProxy"

    BM2_INSTANCE_NGINX_CONF_DIR = "/var/lib/zstack/nginx/baremetal/v2/management_node/"

    #TODO: sync db status and current running processes
    def __init__(self):
        self.http_server.register_async_uri(self.CHECK_AVAILABILITY_PATH, self.check_proxy_availability)
        self.http_server.register_async_uri(self.ESTABLISH_PROXY_PATH, self.establish_new_proxy)
        self.http_server.register_async_uri(self.DELETE_PROXY_PATH, self.delete)
        self.http_server.register_sync_uri(self.PING_PATH, self.ping)

        if not os.path.exists(self.PROXY_LOG_DIR):
            os.makedirs(self.PROXY_LOG_DIR, 0755)
        if not os.path.exists(self.TOKEN_FILE_DIR):
            os.makedirs(self.TOKEN_FILE_DIR, 0755)

        self.db = filedb.FileDB(self.DB_NAME)

        self.token_ctrl = ConsoleTokenFileController()


    def _make_token_file_name(self, prefix, timeout):
        return '%s_%s' % (prefix, time.time() + timeout)


    def _get_token_name_prefix(self, cmd):
        return '_'.join(cmd.token.split('_')[:2])

    def _get_pid_on_port(self, port):
        out = shell.ShellCmd('netstat -anp | grep ":%s" | grep LISTEN' % port)
        out(False)
        out = out.stdout.strip()
        if "" == out:
            return None

        pid = out.split()[-1].split('/')[0]
        try:
            pid = int(pid)
            return pid
        except:
            return None


    def _check_proxy_availability(self, args):
        targetSchema = args['targetSchema']
        if targetSchema == 'vnc':
            return self._check_vnc_proxy_availability(args)

        if targetSchema == 'http':
            return self._check_http_proxy_availability(args)

        return False


    def _check_http_proxy_availability(self, args):
        ret, out, err = bash_roe("systemctl status zstack-baremetal-nginx.service")
        if ret != 0:
            # try to restart the service
            bash_roe("systemctl start zstack-baremetal-nginx.service")
            ret, out, err = bash_roe("systemctl status zstack-baremetal-nginx.service")
            if ret != 0:
                logger.warn('zstack-baremetal-nginx.service is not running, availability false')
                return False
        return True


    def _check_vnc_proxy_availability(self, args):
        proxyPort = args['proxyPort']
        targetHostname = args['targetHostname']
        targetPort = args['targetPort']
        token = args['token']

        pid = self._get_pid_on_port(proxyPort)
        if not pid:
            logger.debug('no websockify on proxy port[%s], availability false' % proxyPort)
            return False

        with open(os.path.join('/proc', str(pid), 'cmdline'), 'r') as fd:
            process_cmdline = fd.read()

        if 'websockify' not in process_cmdline:
            logger.debug('process[pid:%s] on proxy port[%s] is not websockify process, availability false' % (pid, proxyPort))
            return False

        info_str = self.db.get(token)
        if not info_str:
            logger.debug('cannot find information for process[pid:%s] on proxy port[%s], availability false' % (pid, proxyPort))
            return False

        info = jsonobject.loads(info_str)
        if token != info['token']:
            logger.debug('metadata[token] for process[pid:%s] on proxy port[%s] are changed[%s --> %s], availability false' % (pid, proxyPort, token, info['token']))
            return False

        if targetPort != info['targetPort']:
            logger.debug('metadata[targetPort] for process[pid:%s] on proxy port[%s] are changed[%s --> %s], availability false' % (pid, proxyPort, targetPort, info['targetPort']))
            return False

        if targetHostname != info['targetHostname']:
            logger.debug('metadata[targetHostname] for process[pid:%s] on proxy port[%s] are changed[%s --> %s], availability false' % (pid, proxyPort, targetHostname, info['targetHostname']))
            return False

        return True

    @replyerror
    def ping(self, req):
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def check_proxy_availability(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        ret = self._check_proxy_availability({
            'proxyPort':cmd.proxyPort,
            'targetSchema': cmd.targetSchema,
            'targetHostname':cmd.targetHostname,
            'targetPort':cmd.targetPort,
            'token':cmd.token
            })

        rsp = CheckAvailabilityRsp()
        rsp.available = ret

        return jsonobject.dumps(rsp)

    @replyerror
    @lock.lock('console-proxy')
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        if not cmd.targetSchema or cmd.targetSchema == 'vnc':
            return self._delete_vnc_proxy(req)

        if cmd.targetSchema == 'http':
            return self._delete_http_proxy(req)

        rsp.error("unknown target schema %s" % cmd.targetSchema)
        rsp.sucess = False
        return jsonobject.dumps(rsp)


    def _delete_http_proxy(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        # make sure the service is running
        ret, out, err = bash_roe("systemctl status zstack-baremetal-nginx.service")
        if ret != 0:
            ret, out, err = bash_roe("systemctl start zstack-baremetal-nginx.service")
            if ret != 0:
                rsp.error = "failed to start zstack-baremetal-nginx.service"
                rsp.success = False
            return jsonobject.dumps(rsp)

        # remote nginx configuration for bm instance
        conf_path = os.path.join(self.BM2_INSTANCE_NGINX_CONF_DIR, cmd.vmUuid + ".conf")
        if os.path.exists(conf_path):
            os.remove(conf_path)

        # reload the service
        ret, out, err = bash_roe("systemctl reload zstack-baremetal-nginx.service")
        if ret != 0:
            rsp.error = "failed to reload zstack-baremetal-nginx.service"
            rsp.success = False
        return jsonobject.dumps(rsp)


    def _delete_vnc_proxy(self, req):
        def kill_proxy_process():
            out = shell.ShellCmd(
                "netstat -ntp | grep '%s:%s *ESTABLISHED.*python'" % (cmd.targetHostname, cmd.targetPort))
            out(False)
            pids = [line.strip().split(' ')[-1].split('/')[0] for line in out.stdout.splitlines()]
            for pid in pids:
                try:
                    os.kill(int(pid), 15)
                except OSError:
                    continue

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        token_file = ConsoleTokenFile(cmd.token)
        self.token_ctrl.delete_by_prefix(token_file.prefix)
        kill_proxy_process()
        logger.debug('deleted a vnc proxy by command: %s' % req[http.REQUEST_BODY])

        rsp = AgentResponse()
        return jsonobject.dumps(rsp)

    @replyerror
    @lock.lock('console-proxy')
    def establish_new_proxy(self, req):
        # check parameters, generate token file,set db,check process is alive,start process if not,
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = EstablishProxyRsp()
        port_conflict_msg = None
        ##
        def check_parameters():
            if not cmd.targetHostname:
                raise ConsoleProxyError('targetHostname cannot be null')
            if not cmd.targetPort:
                raise ConsoleProxyError('targetPort cannot be null')
            if not cmd.token:
                raise ConsoleProxyError('token cannot be null')
            if not cmd.proxyHostname:
                raise ConsoleProxyError('proxyHostname cannot be null')

        def check_port_conflict():
            if cmd.proxyPort is None or str(cmd.proxyPort).isdigit() is False:
                raise ConsoleProxyError('proxyPort is None or is not a Number')
            system_port_cmd = 'sysctl -n net.ipv4.ip_local_port_range'
            ret, out, err = bash_roe(system_port_cmd)
            if ret != 0:
                logger.warn(err)
            elif out.strip() is None:
                logger.warn("None is net.ipv4.ip_local_port_range in current system")
            else:
                port_range = out.strip().split()
                if len(port_range) == 2 and str(port_range[0]).isdigit() and str(port_range[1]).isdigit():
                    if int(port_range[0]) < int(cmd.proxyPort) < int(port_range[1]):
                        port_conflict_msg = "cmd.proxyPort [%s] is probably conflict with linux ip_local_port_range: %s" % (cmd.proxyPort, port_range)
                        logger.warn(port_conflict_msg)

        try:
            check_parameters()
            check_port_conflict()
        except ConsoleProxyError as e:
            err = linux.get_exception_stacktrace()
            logger.warn(err)
            rsp.error = str(e)
            rsp.success = False
            return jsonobject.dumps(rsp)

        if not cmd.targetSchema or cmd.targetSchema == 'vnc':
            return self._establish_new_vnc_proxy(req)

        if cmd.targetSchema == 'http':
            return self._establish_new_http_proxy(req)

        rsp.error("unknown target schema %s" % cmd.targetSchema)
        rsp.sucess = False
        return jsonobject.dumps(rsp)


    def _establish_new_http_proxy(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = EstablishProxyRsp()
        rsp.proxyPort = cmd.proxyPort
        rsp.token = cmd.token

        # make sure the service is running
        ret, out, err = bash_roe("systemctl status zstack-baremetal-nginx.service")
        if ret != 0:
            ret, out, err = bash_roe("systemctl start zstack-baremetal-nginx.service")
            if ret != 0:
                rsp.error = "failed to start zstack-baremetal-nginx.service"
                rsp.success = False
            return jsonobject.dumps(rsp)

        # add new nginx configuration for bm instance
        if not os.path.exists(self.BM2_INSTANCE_NGINX_CONF_DIR):
            os.makedirs(self.BM2_INSTANCE_NGINX_CONF_DIR, exist_ok=True)

        conf_path = os.path.join(self.BM2_INSTANCE_NGINX_CONF_DIR, cmd.vmUuid + ".conf")
        with open(conf_path, 'w') as f:
            content = "location ^~/%s/ { proxy_set_header Host $host; proxy_pass http://%s:%s; }" % (cmd.token, cmd.targetHostname, cmd.targetPort)
            f.write(content)

        # reload the service
        ret, out, err = bash_roe("systemctl reload zstack-baremetal-nginx.service")
        if ret != 0:
            rsp.error = "failed to reload zstack-baremetal-nginx.service"
            rsp.success = False
        return jsonobject.dumps(rsp)


    def _establish_new_vnc_proxy(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = EstablishProxyRsp()
        log_file = os.path.join(self.PROXY_LOG_DIR, cmd.proxyHostname)

        token_file = ConsoleTokenFile(cmd.token)
        exist_token = self.token_ctrl.search_by_prefix(token_file.prefix)

        # this logic only execute when request from ZStack API
        if not exist_token or exist_token.is_stale():
            self.token_ctrl.delete_by_prefix(token_file.prefix)
            token_file = self.token_ctrl.create_token_file(token_file.prefix, cmd.vncTokenTimeout)
            self.token_ctrl.submit_delete_token_task(token_file)
        else:
            token_file = exist_token

        rsp.token = token_file.get_full_name()
        token_file.flush_write('%s: %s:%s' % (token_file.get_full_name(), cmd.targetHostname, cmd.targetPort))
        info = {
                 'proxyHostname': cmd.proxyHostname,
                 'proxyPort': cmd.proxyPort,
                 'targetHostname': cmd.targetHostname,
                 'targetPort': cmd.targetPort,
                 'token': cmd.token,
                 'logFile': log_file,
                 'tokenFile': token_file.get_absolute_path(),
                }
        info_str = jsonobject.dumps(info)
        self.db.set(cmd.token, info_str)
        rsp.proxyPort = cmd.proxyPort
        logger.debug('successfully add new vnc proxy token file %s' % info_str)

        ## kill garbage websockify process: same proxyip:proxyport, different cert file
        if not cmd.sslCertFile:
            command = "ps aux | grep '[z]stack.*websockify_init' | grep '%s:%d' | grep 'cert=' | awk '{ print $2 }'" % (cmd.proxyHostname, cmd.proxyPort)
        else:
            command = "ps aux | grep '[z]stack.*websockify_init' | grep '%s:%d' | grep -v '%s' | awk '{ print $2 }'" % (cmd.proxyHostname, cmd.proxyPort, cmd.sslCertFile)
        ret,out,err = bash_roe(command)
        for pid in out.splitlines():
            try:
                os.kill(int(pid), 15)
            except OSError:
                continue

        ## if websockify process exists, then return
        alive = False
        ret,out,err = bash_roe("ps aux | grep '[z]stack.*websockify_init'")
        for o in out.splitlines():
            if o.find("%s:%d" % (cmd.proxyHostname, cmd.proxyPort)) != -1:
                alive = True
                break
        if alive:
            return jsonobject.dumps(rsp)

        ##start a new websockify process
        timeout = cmd.idleTimeout
        if not timeout:
            timeout = 600

        @in_bash
        def start_proxy():
            LOG_FILE = log_file
            PROXY_HOST_NAME = cmd.proxyHostname
            PROXY_PORT = cmd.proxyPort
            TOKEN_FILE_DIR = self.TOKEN_FILE_DIR 
            TIMEOUT = timeout
            start_cmd = '''python -c "from zstacklib.utils import log; import websockify; log.configure_log('{{LOG_FILE}}'); websockify.websocketproxy.websockify_init()" {{PROXY_HOST_NAME}}:{{PROXY_PORT}} -D --target-config={{TOKEN_FILE_DIR}} --idle-timeout={{TIMEOUT}}'''
            if cmd.sslCertFile:
                start_cmd += ' --cert=%s' % cmd.sslCertFile
            ret,out,err = bash_roe(start_cmd)
            if ret != 0:
                err = []
                if port_conflict_msg is not None:
                    err.append(port_conflict_msg)
                else:
                    err.append('failed to execute bash command: %s' % start_cmd)
                    err.append('return code: %s' % ret)
                    err.append('stdout: %s' % out)
                    err.append('stderr: %s' % err)
                raise ConsoleProxyError('\n'.join(err))

        start_proxy()
        logger.debug('successfully establish new vnc proxy%s' % info_str)
        return jsonobject.dumps(rsp)


class ConsoleProxyDaemon(daemon.Daemon):
    def __init__(self, pidfile, py_process_name):
        super(ConsoleProxyDaemon, self).__init__(pidfile, py_process_name)

    def run(self):
        self.agent = ConsoleProxyAgent()
        self.agent.http_server.start()

class ConsoleTokenFile(object):
    directory = None
    prefix = None
    timeout_stamp = 0

    def __init__(self, raw=None, directory=ConsoleProxyAgent.TOKEN_FILE_DIR):
        self.directory = directory
        if not raw:
            return

        tmp = raw.split('_')
        self.prefix = '_'.join(tmp[:2])
        if len(tmp) > 2:
            self.timeout_stamp = tmp[2]

    def get_full_name(self):
        return "%s_%s" % (self.prefix, self.timeout_stamp)

    def is_stale(self):
        return time.time() > self.timeout_stamp

    def get_absolute_path(self):
        return os.path.join(self.directory, self.get_full_name())

    def flush_write(self, context):
        with open(os.path.join(self.directory, self.get_full_name()), 'w') as fd:
            fd.write(context)


class ConsoleTokenFileController(object):
    def __init__(self, token_dir=ConsoleProxyAgent.TOKEN_FILE_DIR):
        self.token_dir = token_dir

    def search_by_prefix(self, prefix):
        token_prefix_path = os.path.join(self.token_dir, prefix)
        token_full_name = shell.call("find %s* -type f -exec basename {} \; | head -1" % token_prefix_path).strip()
        if token_full_name:
            return ConsoleTokenFile(token_full_name)

    def delete_by_prefix(self, prefix):
        token_prefix_path = os.path.join(self.token_dir, prefix)
        shell.call("rm -f %s*" % token_prefix_path)

    def submit_delete_token_task(self, token_file):
        threading.Timer(token_file.timeout_stamp - time.time(), self.delete_by_prefix, args=[token_file.prefix]).start()

    def create_token_file(self, prefix, timeout):
        t = ConsoleTokenFile()
        t.prefix = prefix
        t.timeout_stamp = time.time() + timeout
        t.directory = self.token_dir
        return t

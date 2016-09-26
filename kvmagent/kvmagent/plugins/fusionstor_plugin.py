'''

@author: frank
'''

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import lichbd
from zstacklib.utils import sizeunit
from zstacklib.utils import linux
from zstacklib.utils import thread
import os.path
import re
import threading
import time
import traceback

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class ScanRsp(object):
    def __init__(self):
        super(ScanRsp, self).__init__()
        self.result = None

def kill_vm(maxAttempts):
    vm_uuid_list = shell.call("virsh list | grep running | awk '{print $2}'")
    for vm_uuid in vm_uuid_list.split('\n'):
        vm_uuid = vm_uuid.strip(' \t\n\r')
        if not vm_uuid:
            continue

        vm_pid = shell.call("ps aux | grep '/opt/fusionstack/qemu/bin/qemu-system-x86_64' | grep -v 'grep' | awk '/%s/{print $2}'" % vm_uuid)
        vm_pid = vm_pid.strip(' \t\n\r')
        kill = shell.ShellCmd('kill -9 %s' % vm_pid)
        kill(False)
        if kill.return_code == 0:
            logger.warn('kill the vm[uuid:%s, pid:%s] because we lost connection to the fusionstor storage.'
                        'failed to read the heartbeat file %s times' % (vm_uuid, vm_pid, maxAttempts))
        else:
            logger.warn('failed to kill the vm[uuid:%s, pid:%s] %s' % (vm_uuid, vm_pid, kill.stderr))

class FusionstorPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''
    KVM_FUSIONSTOR_QUERY_PATH = "/fusionstor/query"

    SCAN_HOST_PATH = "/ha/scanhost"
    SETUP_SELF_FENCER_PATH = "/ha/selffencer/setup"
    FUSIONSTOR_SELF_FENCER = "/ha/fusionstor/setupselffencer"

    RET_SUCCESS = "success"
    RET_FAILURE = "failure"
    RET_NOT_STABLE = "unstable"

    @kvmagent.replyerror
    def setup_fusionstor_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        @thread.AsyncThread
        def heartbeat_on_fusionstor():
            try:
                failure = 0

                while True:
                    time.sleep(cmd.interval)

                    mon_url = '\;'.join(cmd.monUrls)
                    mon_url = mon_url.replace(':', '\\\:')
                    create = shell.ShellCmd('timeout %s lichbd create %s -s 1b -p nbd' %
                                                (cmd.storageCheckerTimeout, cmd.heartbeatImagePath))
                    create(False)

                    read_heart_beat_file = False
                    if create.return_code == 0:
                        failure = 0
                        continue
                    elif "File exists" in create.stderr:
                        read_heart_beat_file = True
                    else:
                        # will cause failure count +1
                        logger.warn('cannot create heartbeat image; %s' % create.stderr)

                    if read_heart_beat_file:
                        touch = shell.ShellCmd('timeout %s qemu-img info nbd:unix:/tmp/nbd-socket:exportname=%s' %
                                               (cmd.storageCheckerTimeout, cmd.heartbeatImagePath))
                        touch(False)

                        if touch.return_code == 0:
                            failure = 0
                            continue

                    failure += 1
                    if failure == cmd.maxAttempts:
                        kill_vm(cmd.maxAttempts)

                        # reset the failure count
                        failure = 0

            except:
                content = traceback.format_exc()
                logger.warn(content)

        heartbeat_on_fusionstor()

        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        @thread.AsyncThread
        def heartbeat_file_fencer(heartbeat_file_path):
            try:
                failure = 0

                while True:
                    time.sleep(cmd.interval)

                    touch = shell.ShellCmd('timeout %s touch %s; exit $?' % (cmd.storageCheckerTimeout, heartbeat_file_path))
                    touch(False)
                    if touch.return_code == 0:
                        failure = 0
                        continue

                    logger.warn('unable to touch %s, %s %s' % (heartbeat_file_path, touch.stderr, touch.stdout))
                    failure += 1

                    if failure == cmd.maxAttempts:
                        logger.warn('failed to touch the heartbeat file[%s] %s times, we lost the connection to the storage,'
                                    'shutdown ourselves' % (heartbeat_file_path, cmd.maxAttempts))
                        kill_vm(cmd.maxAttempts)
            except:
                content = traceback.format_exc()
                logger.warn(content)


        gateway = cmd.storageGateway
        if not gateway:
            gateway = linux.get_gateway_by_default_route()

        @thread.AsyncThread
        def storage_gateway_fencer(gw):
            failure = 0

            try:
                while True:
                    time.sleep(cmd.interval)

                    ping = shell.ShellCmd("nmap -sP -PI %s | grep 'Host is up'" % gw)
                    ping(False)
                    if ping.return_code == 0:
                        failure = 0
                        continue

                    logger.warn('unable to ping the storage gateway[%s], %s %s' % (gw, ping.stderr, ping.stdout))
                    failure += 1

                    if failure == cmd.maxAttempts:
                        logger.warn('failed to ping storage gateway[%s] %s times, we lost connection to the storage,'
                                    'shutdown ourselves' % (gw, cmd.maxAttempts))
                        kill_vm(cmd.maxAttempts)
            except:
                content = traceback.format_exc()
                logger.warn(content)

        for mount_point in cmd.mountPoints:
            if not os.path.isdir(mount_point):
                raise Exception('the mount point[%s] is not a directory' % mount_point)

            hb_file = os.path.join(mount_point, 'heartbeat-file-kvm-host-%s.hb' % cmd.hostUuid)
            heartbeat_file_fencer(hb_file)

        if gateway:
            storage_gateway_fencer(gateway)
        else:
            logger.warn('cannot find storage gateway, unable to setup storage gateway fencer')

        return jsonobject.dumps(AgentRsp())


    @kvmagent.replyerror
    def scan_host(self, req):
        rsp = ScanRsp()

        success = 0
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for i in range(0, cmd.times):
            if shell.run("nmap -sP -PI %s | grep 'Host is up'" % cmd.ip) == 0:
                success += 1

            time.sleep(cmd.interval)

        if success == cmd.successTimes:
            rsp.result = self.RET_SUCCESS
            return jsonobject.dumps(rsp)

        if success == 0:
            rsp.result = self.RET_FAILURE
            return jsonobject.dumps(rsp)

        # WE SUCCEED A FEW TIMES, IT SEEMS THE CONNECTION NOT STABLE
        success = 0
        for i in range(0, cmd.successTimes):
            if shell.run("nmap -sP -PI %s | grep 'Host is up'" % cmd.ip) == 0:
                success += 1

            time.sleep(cmd.successInterval)

        if success == cmd.successTimes:
            rsp.result = self.RET_SUCCESS
            return jsonobject.dumps(rsp)

        rsp.result = self.RET_NOT_STABLE
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def fusionstor_query(self, req):
        protocol = lichbd.get_protocol()
        if protocol == 'lichbd':
            lichbd.makesure_qemu_img_with_lichbd()
        elif protocol == 'sheepdog' or protocol == 'nbd':
            pass
        else:
            raise shell.ShellError('Do not supprot protocols, only supprot lichbd, sheepdog and nbd')

        o = shell.call('lich.node --stat 2>/dev/null')
        if 'running' not in o:
            raise shell.ShellError('the lichd process of this node is not running, Please check the lichd service')

        return jsonobject.dumps(kvmagent.AgentResponse())

    def start(self):
        self.host_uuid = None
        
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.KVM_FUSIONSTOR_QUERY_PATH, self.fusionstor_query)
        http_server.register_async_uri(self.SCAN_HOST_PATH, self.scan_host)
        http_server.register_async_uri(self.SETUP_SELF_FENCER_PATH, self.setup_self_fencer)
        http_server.register_async_uri(self.FUSIONSTOR_SELF_FENCER, self.setup_fusionstor_self_fencer)

    def stop(self):
        pass

    def configure(self, config):
        self.config = config

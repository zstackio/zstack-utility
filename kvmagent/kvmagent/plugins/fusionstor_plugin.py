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
from zstacklib.utils import qemu_img
import zstacklib.utils.lichbd_factory as lichbdfactory
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
                    create = shell.ShellCmd('timeout %s %s %s -s 1b -p nbd' %
                                                (cmd.storageCheckerTimeout,lichbdfactory.get_lichbd_version_class().LICHBD_CMD_VOL_CREATE, cmd.heartbeatImagePath))
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
                        touch = shell.ShellCmd('timeout %s %s nbd:unix:/tmp/nbd-socket:exportname=%s' %
                                (cmd.storageCheckerTimeout, qemu_img.subcmd('info'), cmd.heartbeatImagePath))
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
        http_server.register_async_uri(self.FUSIONSTOR_SELF_FENCER, self.setup_fusionstor_self_fencer)

    def stop(self):
        pass

    def configure(self, config):
        self.config = config

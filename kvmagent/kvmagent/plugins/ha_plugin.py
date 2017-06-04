from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import thread
import os.path
import re
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


class ReportPsStatusCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.psPath = None
        self.psStatus = None

def kill_vm(maxAttempts, mountPath = None, isFileSystem = None):
    vm_uuid_list = shell.call("virsh list | grep running | awk '{print $2}'")
    for vm_uuid in vm_uuid_list.split('\n'):
        vm_uuid = vm_uuid.strip(' \t\n\r')
        if not vm_uuid:
            continue

        if mountPath and isFileSystem is not None \
                and not is_need_kill(vm_uuid, mountPath, isFileSystem):
            continue

        vm_pid = shell.call("ps aux | grep qemu-kvm | grep -v grep | awk '/%s/{print $2}'" % vm_uuid)
        vm_pid = vm_pid.strip(' \t\n\r')
        kill = shell.ShellCmd('kill -9 %s' % vm_pid)
        kill(False)
        if kill.return_code == 0:
            logger.warn('kill the vm[uuid:%s, pid:%s] because we lost connection to the storage.'
                        'failed to read the heartbeat file %s times' % (vm_uuid, vm_pid, maxAttempts))
        else:
            logger.warn('failed to kill the vm[uuid:%s, pid:%s] %s' % (vm_uuid, vm_pid, kill.stderr))


def is_need_kill(vmUuid, mountPath, isFileSystem):
    def vm_match_storage_type(vmUuid, isFileSystem):
        o = shell.ShellCmd("virsh dumpxml %s | grep \"disk type='file'\"" % vmUuid)
        o(False)
        if (o.return_code == 0 and isFileSystem) or (o.return_code != 0 and not isFileSystem):
            return True
        return False

    def vm_in_this_file_system_storage(vm_uuid, ps_path):
        cmd = shell.ShellCmd("virsh dumpxml %s | grep \"source file=\" | head -1 |awk -F \"'\" '{print $2}'" % vm_uuid)
        cmd(False)
        vm_path = cmd.stdout.strip()
        if cmd.return_code != 0 or vm_path == "" or ps_path in vm_path:
            return True
        return False

    def vm_in_this_distributed_storage(vm_uuid, ps_path):
        cmd = shell.ShellCmd("virsh dumpxml %s | grep \"source protocol\" | head -1 | awk -F \"'\" '{print $4}'" % vm_uuid)
        cmd(False)
        vm_path = cmd.stdout.strip()
        if cmd.return_code != 0 or vm_path == "":
            return True
        elif ps_path in vm_path:
            info = shell.ShellCmd("rbd info %s" % vm_path)
            info(False)
            if info.return_code != 0:
                return True
        return False

    if vm_match_storage_type(vmUuid, isFileSystem):
        if isFileSystem and vm_in_this_file_system_storage(vmUuid, mountPath):
            return True
        elif not isFileSystem and vm_in_this_distributed_storage(vmUuid, mountPath):
            return True

    return False


def report_storage_status(self, ps_path, ps_status):
    url = self.config.get(kvmagent.SEND_COMMAND_URL)
    if not url:
        logger.warn('cannot find SEND_COMMAND_URL, unable to report storage status[ps:%s, status:%s]' % (
            ps_path, ps_status))
        return

    host_uuid = self.config.get(kvmagent.HOST_UUID)
    if not host_uuid:
        logger.warn(
            'cannot find HOST_UUID, unable to report storage status[ps:%s, status:%s]' % (ps_path, ps_status))
        return

    @thread.AsyncThread
    def report_to_management_node():
        cmd = ReportPsStatusCmd()
        cmd.psPath = ps_path
        cmd.hostUuid = host_uuid
        cmd.psStatus = ps_status

        logger.debug(
            'primary storage[path:%s] has new connection status[%s], report it to %s' % (ps_path, ps_status, url))
        http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportstoragestatus'})

    report_to_management_node()




class HaPlugin(kvmagent.KvmAgent):
    SCAN_HOST_PATH = "/ha/scanhost"
    SETUP_SELF_FENCER_PATH = "/ha/selffencer/setup"
    CANCEL_SELF_FENCER_PATH = "/ha/selffencer/cancel"
    CEPH_SELF_FENCER = "/ha/ceph/setupselffencer"
    CANCEL_CEPH_SELF_FENCER = "/ha/ceph/cancelselffencer"

    RET_SUCCESS = "success"
    RET_FAILURE = "failure"
    RET_NOT_STABLE = "unstable"

    def __init__(self):
        self.run_ceph_fencer = False
        self.run_filesystem_fencer = False

    @kvmagent.replyerror
    def cancel_ceph_self_fencer(self, req):
        self.run_ceph_fencer = False
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def cancel_filesystem_self_fencer(self, req):
        self.run_filesystem_fencer = False
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_ceph_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        mon_url = '\;'.join(cmd.monUrls)
        mon_url = mon_url.replace(':', '\\\:')

        self.run_ceph_fencer = True

        def ceph_in_error_stat():
            healthStatus = shell.call('ceph health')
            return healthStatus.startswith('HEALTH_ERR')

        def heartbeat_file_exists():
            touch = shell.ShellCmd('timeout %s qemu-img info rbd:%s:id=zstack:key=%s:auth_supported=cephx\;none:mon_host=%s' %
                                   (cmd.storageCheckerTimeout, cmd.heartbeatImagePath, cmd.userKey, mon_url))
            touch(False)

            if touch.return_code == 0:
                return True

            logger.warn('cannot query heartbeat image: %s: %s' % (cmd.heartbeatImagePath, touch.stderr))
            return False

        def create_heartbeat_file():
            create = shell.ShellCmd('timeout %s qemu-img create -f raw rbd:%s:id=zstack:key=%s:auth_supported=cephx\;none:mon_host=%s 1' %
                                        (cmd.storageCheckerTimeout, cmd.heartbeatImagePath, cmd.userKey, mon_url))
            create(False)

            if create.return_code == 0 or "File exists" in create.stderr:
                return True

            logger.warn('cannot create heartbeat image: %s: %s' % (cmd.heartbeatImagePath, create.stderr))
            return False

        def delete_heartbeat_file():
            delete = shell.ShellCmd("timeout %s rbd rm --id zstack %s -m %s" %
                    (cmd.storageCheckerTimeout, cmd.heartbeatImagePath, mon_url))
            delete(False)

        @thread.AsyncThread
        def heartbeat_on_ceph():
            try:
                failure = 0

                while self.run_ceph_fencer:
                    time.sleep(cmd.interval)

                    if heartbeat_file_exists() or create_heartbeat_file():
                        failure = 0
                        continue

                    failure += 1
                    if failure == cmd.maxAttempts:
                        # c.f. We discovered that, Ceph could behave the following:
                        #  1. Create heart-beat file, failed with 'File exists'
                        #  2. Query the hb file in step 1, and failed again with 'No such file or directory'
                        if ceph_in_error_stat():
                            path = (os.path.split(cmd.heartbeatImagePath))[0]
                            kill_vm(cmd.maxAttempts, path, False)
                        else:
                            delete_heartbeat_file()

                        # reset the failure count
                        failure = 0

                logger.debug('stop self-fencer on ceph primary storage')
            except:
                content = traceback.format_exc()
                logger.warn(content)

        heartbeat_on_ceph()

        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        self.run_filesystem_fencer = True

        @thread.AsyncThread
        def heartbeat_file_fencer(heartbeat_file_path):
            try:
                failure = 0

                while self.run_filesystem_fencer:
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
                        mountPath = (os.path.split(heartbeat_file_path))[0]
                        report_storage_status(mountPath, 'Disconnected')
                        kill_vm(cmd.maxAttempts, mountPath, True)

                logger.debug('stop heartbeat[%s] for filesystem self-fencer' % heartbeat_file_path)
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
                while self.run_filesystem_fencer:
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

                logger.debug('stop gateway[%s] fencer for filesystem self-fencer' % gw)
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


    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.SCAN_HOST_PATH, self.scan_host)
        http_server.register_async_uri(self.SETUP_SELF_FENCER_PATH, self.setup_self_fencer)
        http_server.register_async_uri(self.CEPH_SELF_FENCER, self.setup_ceph_self_fencer)
        http_server.register_async_uri(self.CANCEL_SELF_FENCER_PATH, self.cancel_filesystem_self_fencer)
        http_server.register_async_uri(self.CANCEL_CEPH_SELF_FENCER, self.cancel_ceph_self_fencer)

    def stop(self):
        pass

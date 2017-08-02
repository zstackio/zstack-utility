from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import thread
import os.path
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
        self.psUuids = None
        self.psStatus = None


def kill_vm(maxAttempts, mountPaths=None, isFileSystem=None):
    zstack_uuid_pattern = "'[0-9a-f]{8}[0-9a-f]{4}[1-5][0-9a-f]{3}[89ab][0-9a-f]{3}[0-9a-f]{12}'"

    virsh_list = shell.call("virsh list --all")
    logger.debug("virsh_list:\n" + virsh_list)

    vm_in_process_uuid_list = shell.call("virsh list | egrep -o " + zstack_uuid_pattern + " | sort | uniq")
    logger.debug('vm_in_process_uuid_list:\n' + vm_in_process_uuid_list)

    # kill vm's qemu process
    for vm_uuid in vm_in_process_uuid_list.split('\n'):
        vm_uuid = vm_uuid.strip(' \t\n\r')
        if not vm_uuid:
            continue

        if mountPaths and isFileSystem is not None \
                and not is_need_kill(vm_uuid, mountPaths, isFileSystem):
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

    if isFileSystem :
        for mp in mountPaths:
            kill_and_umount(mp, mount_path_is_nfs(mp))

def mount_path_is_nfs(mount_path):
    typ = shell.call("mount | grep '%s' | awk '{print $5}'" % mount_path)
    return typ.startswith('nfs')


@linux.retry(times=8, sleep_time=2)
def do_kill_and_umount(mount_path, is_nfs):
    kill_progresses_using_mount_path(mount_path)
    umount_fs(mount_path, is_nfs)

def kill_and_umount(mount_path, is_nfs):
    do_kill_and_umount(mount_path, is_nfs)
    if is_nfs:
        shell.ShellCmd("systemctl start nfs-client.target")(False)

def umount_fs(mount_path, is_nfs):
    if is_nfs:
        shell.ShellCmd("systemctl stop nfs-client.target")(False)
    shell.call("sleep 2; umount -f %s" % mount_path)


def kill_progresses_using_mount_path(mount_path):
    list_ps = []
    o = shell.ShellCmd("ps aux | grep '%s' | awk '{print $2}'" % mount_path)
    o(False)
    if o.return_code == 0:
        list_ps = o.stdout.splitlines()

    logger.warn('kill the progresses, pids:%s with mount path: %s' % (list_ps, mount_path))
    for ps_id in list_ps:
        shell.ShellCmd("kill -9 %s || true" % ps_id)


def is_need_kill(vmUuid, mountPaths, isFileSystem):
    def vm_match_storage_type(vmUuid, isFileSystem):
        o = shell.ShellCmd("virsh dumpxml %s | grep \"disk type='file'\" | grep -v \"device='cdrom'\"" % vmUuid)
        o(False)
        if (o.return_code == 0 and isFileSystem) or (o.return_code != 0 and not isFileSystem):
            return True
        return False

    def vm_in_this_file_system_storage(vm_uuid, ps_paths):
        cmd = shell.ShellCmd("virsh dumpxml %s | grep \"source file=\" | head -1 |awk -F \"'\" '{print $2}'" % vm_uuid)
        cmd(False)
        vm_path = cmd.stdout.strip()
        if cmd.return_code != 0 or vm_in_storage_list(vm_path, ps_paths):
            return True
        return False

    def vm_in_this_distributed_storage(vm_uuid, ps_paths):
        cmd = shell.ShellCmd("virsh dumpxml %s | grep \"source protocol\" | head -1 | awk -F \"'\" '{print $4}'" % vm_uuid)
        cmd(False)
        vm_path = cmd.stdout.strip()
        if cmd.return_code != 0 or vm_in_storage_list(vm_path, ps_paths):
            return True
        return False

    def vm_in_storage_list(vm_path, storage_paths):
        if vm_path == "" or any([vm_path.startswith(ps_path) for ps_path in storage_paths]):
            return True
        return False

    if vm_match_storage_type(vmUuid, isFileSystem):
        if isFileSystem and vm_in_this_file_system_storage(vmUuid, mountPaths):
            return True
        elif not isFileSystem and vm_in_this_distributed_storage(vmUuid, mountPaths):
            return True

    return False

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

        def get_ceph_rbd_args():
            if cmd.userKey is None:
                return 'rbd:%s:mon_host=%s' % (cmd.heartbeatImagePath, mon_url)
            return 'rbd:%s:id=zstack:key=%s:auth_supported=cephx\;none:mon_host=%s' % (cmd.heartbeatImagePath, cmd.userKey, mon_url)

        def ceph_in_error_stat():
            # HEALTH_OK,HEALTH_WARN,HEALTH_ERR and others(may be empty)...
            health = shell.ShellCmd('timeout %s ceph health' % cmd.storageCheckerTimeout)
            health(False)
            # If the command times out, then exit with status 124
            if health.return_code == 124:
                return True

            health_status = health.stdout
            return not (health_status.startswith('HEALTH_OK') or health_status.startswith('HEALTH_WARN'))

        def heartbeat_file_exists():
            touch = shell.ShellCmd('timeout %s qemu-img info %s' %
                                   (cmd.storageCheckerTimeout, get_ceph_rbd_args()))
            touch(False)

            if touch.return_code == 0:
                return True

            logger.warn('cannot query heartbeat image: %s: %s' % (cmd.heartbeatImagePath, touch.stderr))
            return False

        def create_heartbeat_file():
            create = shell.ShellCmd('timeout %s qemu-img create -f raw %s 1' %
                                        (cmd.storageCheckerTimeout, get_ceph_rbd_args()))
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
                            kill_vm(cmd.maxAttempts, [path], False)
                        else:
                            delete_heartbeat_file()

                        # reset the failure count
                        failure = 0

                logger.debug('stop self-fencer on ceph primary storage')
            except:
                logger.debug('self-fencer on ceph primary storage stopped abnormally')
                content = traceback.format_exc()
                logger.warn(content)

        heartbeat_on_ceph()

        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        self.run_filesystem_fencer = True

        @thread.AsyncThread
        def heartbeat_file_fencer(mount_path, ps_uuid):
            heartbeat_file_path = os.path.join(mount_path, 'heartbeat-file-kvm-host-%s.hb' % cmd.hostUuid)
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
                        self.report_storage_status([ps_uuid], 'Disconnected')
                        kill_vm(cmd.maxAttempts, [mount_path], True)
                        break

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
                        # there might be a race condition with very small probabilities because report action is async,
                        # cause vm ha slow because starting vm might select this broken host
                        # due to ps-report arriving later than vm-report.
                        # a sure card is to modify it to sync action with try-except
                        # but if http post fail to retry too many times, kill vm will be too late.
                        # so for ha efficiency, that's it..
                        self.report_storage_status(cmd.psUuids, 'Disconnected')
                        kill_vm(cmd.maxAttempts, cmd.mountPoints, True)

                logger.debug('stop gateway[%s] fencer for filesystem self-fencer' % gw)
            except:
                content = traceback.format_exc()
                logger.warn(content)

        for mount_point, uuid in zip(cmd.mountPoints, cmd.uuids):
            if not linux.timeout_isdir(mount_point):
                raise Exception('the mount point[%s] is not a directory' % mount_point)

            heartbeat_file_fencer(mount_point, uuid)

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

    def configure(self, config):
        self.config = config

    @thread.AsyncThread
    def report_storage_status(self, ps_uuids, ps_status):
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            logger.warn('cannot find SEND_COMMAND_URL, unable to report storages status[psList:%s, status:%s]' % (
                ps_uuids, ps_status))
            return

        host_uuid = self.config.get(kvmagent.HOST_UUID)
        if not host_uuid:
            logger.warn(
                'cannot find HOST_UUID, unable to report storages status[psList:%s, status:%s]' % (ps_uuids, ps_status))
            return

        def report_to_management_node():
            cmd = ReportPsStatusCmd()
            cmd.psUuids = ps_uuids
            cmd.hostUuid = host_uuid
            cmd.psStatus = ps_status

            logger.debug(
                'primary storage[psList:%s] has new connection status[%s], report it to %s' % (
                ps_uuids, ps_status, url))
            http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportstoragestatus'})

        report_to_management_node()


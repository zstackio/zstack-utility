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
import threading

logger = log.get_logger(__name__)

class UmountException(Exception):
    pass

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
    vm_pids_dict = {}
    for vm_uuid in vm_in_process_uuid_list.split('\n'):
        vm_uuid = vm_uuid.strip(' \t\n\r')
        if not vm_uuid:
            continue

        if mountPaths and isFileSystem is not None \
                and not is_need_kill(vm_uuid, mountPaths, isFileSystem):
            continue

        vm_pid = shell.call("ps aux | grep qemu-kvm | grep -v grep | awk '/%s/{print $2}'" % vm_uuid)
        vm_pid = vm_pid.strip(' \t\n\r')
        vm_pids_dict[vm_uuid] = vm_pid

    for vm_uuid, vm_pid in vm_pids_dict.items():
        kill = shell.ShellCmd('kill -9 %s' % vm_pid)
        kill(False)
        if kill.return_code == 0:
            logger.warn('kill the vm[uuid:%s, pid:%s] because we lost connection to the storage.'
                        'failed to read the heartbeat file %s times' % (vm_uuid, vm_pid, maxAttempts))
        else:
            logger.warn('failed to kill the vm[uuid:%s, pid:%s] %s' % (vm_uuid, vm_pid, kill.stderr))

    return vm_pids_dict.values()


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
    time.sleep(2)
    o = shell.ShellCmd("umount -f %s" % mount_path)
    o(False)
    if o.return_code != 0:
        raise UmountException(o.stderr)


def kill_progresses_using_mount_path(mount_path):
    list_ps = []
    o = shell.ShellCmd("ps aux | grep '%s' | awk '{print $2}'" % mount_path)
    o(False)
    if o.return_code == 0:
        list_ps = o.stdout.splitlines()

    logger.warn('kill the progresses, pids:%s with mount path: %s' % (list_ps, mount_path))
    for ps_id in list_ps:
        linux.kill9_process(ps_id)


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
        self.run_filesystem_fencer_timestamp = {}
        self.fencer_lock = threading.RLock()

    @kvmagent.replyerror
    def cancel_ceph_self_fencer(self, req):
        self.run_ceph_fencer = False
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def cancel_filesystem_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        with self.fencer_lock:
            for ps_uuid in cmd.psUuids:
                self.run_filesystem_fencer_timestamp.pop(ps_uuid, None)
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_ceph_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        def check_tools():
            ceph = shell.run('which ceph')
            rbd = shell.run('which rbd')

            if ceph == 0 and rbd == 0:
                return True

            return False

        if not check_tools():
            rsp = AgentRsp()
            rsp.error = "no ceph or rbd on current host, please install the tools first"
            rsp.success = False
            return jsonobject.dumps(rsp)

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
            shell.run("timeout %s rbd rm --id zstack %s -m %s" %
                    (cmd.storageCheckerTimeout, cmd.heartbeatImagePath, mon_url))

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

        @thread.AsyncThread
        def heartbeat_file_fencer(mount_path, ps_uuid, mounted_by_zstack):
            def try_remount_fs():
                if mount_path_is_nfs(mount_path):
                    shell.run("systemctl start nfs-client.target")

                while self.run_filesystem_fencer(ps_uuid, created_time):
                    if linux.is_mounted(path=mount_path) and touch_heartbeat_file():
                        self.report_storage_status([ps_uuid], 'Connected')
                        logger.debug("fs[uuid:%s] is reachable again, report to management" % ps_uuid)
                        break
                    try:
                        logger.debug('fs[uuid:%s] is unreachable, it will be remounted after 180s' % ps_uuid)
                        time.sleep(180)
                        if not self.run_filesystem_fencer(ps_uuid, created_time):
                            break
                        linux.remount(url, mount_path, options)
                        self.report_storage_status([ps_uuid], 'Connected')
                        logger.debug("remount fs[uuid:%s] success, report to management" % ps_uuid)
                        break
                    except:
                        logger.warn('remount fs[uuid:%s] fail, try again soon' % ps_uuid)
                        kill_progresses_using_mount_path(mount_path)

                logger.debug('stop remount fs[uuid:%s]' % ps_uuid)

            def after_kill_vm():
                if not killed_vm_pids or not mounted_by_zstack:
                    return

                try:
                    kill_and_umount(mount_path, mount_path_is_nfs(mount_path))
                except UmountException:
                    if shell.run('ps -p %s' % ' '.join(killed_vm_pids)) == 0:
                        virsh_list = shell.call("timeout 10 virsh list --all || echo 'cannot obtain virsh list'")
                        logger.debug("virsh_list:\n" + virsh_list)
                        logger.error('kill vm[pids:%s] failed because of unavailable fs[mountPath:%s].'
                                     ' please retry "umount -f %s"' % (killed_vm_pids, mount_path, mount_path))
                        return

                try_remount_fs()


            def touch_heartbeat_file():
                touch = shell.ShellCmd('timeout %s touch %s' % (cmd.storageCheckerTimeout, heartbeat_file_path))
                touch(False)
                if touch.return_code != 0:
                    logger.warn('unable to touch %s, %s %s' % (heartbeat_file_path, touch.stderr, touch.stdout))
                return touch.return_code == 0

            heartbeat_file_path = os.path.join(mount_path, 'heartbeat-file-kvm-host-%s.hb' % cmd.hostUuid)
            created_time = time.time()
            with self.fencer_lock:
                self.run_filesystem_fencer_timestamp[ps_uuid] = created_time
            try:
                failure = 0
                url = shell.call("mount | grep -e '%s' | awk '{print $1}'" % mount_path).strip()
                options = shell.call("mount | grep -e '%s' | awk -F '[()]' '{print $2}'" % mount_path).strip()

                while self.run_filesystem_fencer(ps_uuid, created_time):
                    time.sleep(cmd.interval)
                    if touch_heartbeat_file():
                        failure = 0
                        continue

                    failure += 1
                    if failure == cmd.maxAttempts:
                        logger.warn('failed to touch the heartbeat file[%s] %s times, we lost the connection to the storage,'
                                    'shutdown ourselves' % (heartbeat_file_path, cmd.maxAttempts))
                        self.report_storage_status([ps_uuid], 'Disconnected')
                        killed_vm_pids = kill_vm(cmd.maxAttempts, [mount_path], True)
                        after_kill_vm()

                logger.debug('stop heartbeat[%s] for filesystem self-fencer' % heartbeat_file_path)

            except:
                content = traceback.format_exc()
                logger.warn(content)

        for mount_path, uuid, mounted_by_zstack in zip(cmd.mountPaths, cmd.uuids, cmd.mountedByZStack):
            if not linux.timeout_isdir(mount_path):
                raise Exception('the mount path[%s] is not a directory' % mount_path)

            heartbeat_file_fencer(mount_path, uuid, mounted_by_zstack)

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

        if success == 0:
            rsp.result = self.RET_FAILURE
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

    def run_filesystem_fencer(self, ps_uuid, created_time):
        with self.fencer_lock:
            if not self.run_filesystem_fencer_timestamp[ps_uuid] or self.run_filesystem_fencer_timestamp[ps_uuid] > created_time:
                return False

            self.run_filesystem_fencer_timestamp[ps_uuid] = created_time
            return True


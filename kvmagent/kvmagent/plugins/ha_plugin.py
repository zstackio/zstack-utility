from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import lvm
from zstacklib.utils import thread
from zstacklib.utils import qemu_img
import os.path
import re
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

class ScanRsp(AgentRsp):
    def __init__(self):
        super(ScanRsp, self).__init__()
        self.result = None


class SanlockScanRsp(AgentRsp):
    def __init__(self):
        super(SanlockScanRsp, self).__init__()
        self.result = None  # type: dict[str, bool]


class ReportPsStatusCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.psUuids = None
        self.psStatus = None
        self.reason = None

class ReportSelfFencerCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.psUuids = None
        self.reason = None


class SanlockHostStatus(object):
    def __init__(self, record):
        lines = record.strip().splitlines()
        hid, s, ts = lines[0].split()
        if s != 'timestamp':
            raise Exception('unexpected sanlock host status: ' + record)
        self.host_id = int(hid)
        self.timestamp = int(ts)

        for line in lines[1:]:
            k, v = line.strip().split('=', 2)
            if k == 'io_timeout': self.io_timeout = int(v)
            elif k == 'last_check': self.last_check = int(v)
            elif k == 'last_live': self.last_live = int(v)

        if not all([self.io_timeout, self.last_check, self.last_live]):
            raise Exception('unexpected sanlock host status: ' + record)

    def get_timestamp(self):
        return self.timestamp

    def get_io_timeout(self):
        return self.io_timeout

    def get_last_check(self):
        return self.last_check

    def get_last_live(self):
        return self.last_live


class SanlockHostStatusParser(object):
    def __init__(self, status):
        self.status = status

    def is_timed_out(self, hostId):
        r = self.get_record(hostId)
        if r is None:
            return None

        return r.get_timestamp() == 0 or r.get_last_check() - r.get_last_live() > 10 * r.get_io_timeout()

    def is_alive(self, hostId):
        r = self.get_record(hostId)
        if r is None:
            return None

        return r.get_timestamp() != 0 and r.get_last_check() - r.get_last_live() < 2 * r.get_io_timeout()

    def get_record(self, hostId):
        m = re.search(r"^%d\b" % hostId, self.status, re.M)
        if not m:
            return None

        substr = self.status[m.end():]
        m = re.search(r"^\d+\b", substr, re.M)
        remainder = substr if not m else substr[:m.start()]
        return SanlockHostStatus(str(hostId) + remainder)


last_multipath_run = time.time()


def clean_network_config(vm_uuids):
    for c in kvmagent.ha_cleanup_handlers:
        logger.debug('clean network config handler: %s\n' % c)
        thread.ThreadFacade.run_in_thread(c, (vm_uuids,))


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
                and not need_kill(vm_uuid, mountPaths, isFileSystem):
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

    return vm_pids_dict


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
    o = shell.ShellCmd("pkill -9 -e -f '%s'" % mount_path)
    o(False)
    logger.warn('kill the progresses with mount path: %s, killed process: %s' % (mount_path, o.stdout))


def get_running_vm_root_volume_path(vm_uuid, is_file_system):
    # 1. get "-drive ... -device ... bootindex=1,
    # 2. get "-boot order=dc ... -drive id=drive-virtio-disk"
    # 3. make sure io has error
    # 4. filter for pv
    out = shell.call("pgrep -a qemu-kvm | grep %s" % vm_uuid)
    if not out:
        return None

    pid = out.split(" ")[0]
    cmdline = out.split(" ", 3)[-1]
    if "bootindex=1" in cmdline:
        root_volume_path = cmdline.split("bootindex=1")[0].split(" -drive file=")[-1].split(",")[0]
    elif " -boot order=dc" in cmdline:
        # TODO: maybe support scsi volume as boot volume one day
        root_volume_path = cmdline.split("id=drive-virtio-disk0")[0].split(" -drive file=")[-1].split(",")[0]
    else:
        logger.warn("found strange vm[pid: %s, cmdline: %s], can not find boot volume" % (pid, cmdline))
        return None

    if not is_file_system:
        return root_volume_path.replace("rbd:", "")

    return root_volume_path


def need_kill(vm_uuid, storage_paths, is_file_system):
    vm_path = get_running_vm_root_volume_path(vm_uuid, is_file_system)

    if not vm_path or vm_path == "" or any([vm_path.startswith(ps_path) for ps_path in storage_paths]):
        return True

    return False


class HaPlugin(kvmagent.KvmAgent):
    SCAN_HOST_PATH = "/ha/scanhost"
    SANLOCK_SCAN_HOST_PATH = "/sanlock/scanhost"
    SETUP_SELF_FENCER_PATH = "/ha/selffencer/setup"
    CANCEL_SELF_FENCER_PATH = "/ha/selffencer/cancel"
    CEPH_SELF_FENCER = "/ha/ceph/setupselffencer"
    CANCEL_CEPH_SELF_FENCER = "/ha/ceph/cancelselffencer"
    SHAREDBLOCK_SELF_FENCER = "/ha/sharedblock/setupselffencer"
    CANCEL_SHAREDBLOCK_SELF_FENCER = "/ha/sharedblock/cancelselffencer"
    ALIYUN_NAS_SELF_FENCER = "/ha/aliyun/nas/setupselffencer"
    CANCEL_NAS_SELF_FENCER = "/ha/aliyun/nas/cancelselffencer"

    RET_SUCCESS = "success"
    RET_FAILURE = "failure"
    RET_NOT_STABLE = "unstable"

    def __init__(self):
        # {ps_uuid: created_time} e.g. {'07ee15b2f68648abb489f43182bd59d7': 1544513500.163033}
        self.run_fencer_timestamp = {}  # type: dict[str, float]
        self.fencer_fire_timestamp = {}  # type: dict[str, float]
        self.fencer_lock = threading.RLock()

    @kvmagent.replyerror
    def cancel_ceph_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.cancel_fencer(cmd.uuid)
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def cancel_filesystem_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for ps_uuid in cmd.psUuids:
            self.cancel_fencer(ps_uuid)

        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def cancel_aliyun_nas_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.cancel_fencer(cmd.uuid)
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_aliyun_nas_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        created_time = time.time()
        self.setup_fencer(cmd.uuid, created_time)

        @thread.AsyncThread
        def heartbeat_on_aliyunnas():
            failure = 0

            while self.run_fencer(cmd.uuid, created_time):
                try:
                    time.sleep(cmd.interval)

                    mount_path = cmd.mountPath

                    test_file = os.path.join(mount_path, cmd.heartbeat, '%s-ping-test-file-%s' % (cmd.uuid, kvmagent.HOST_UUID))
                    touch = shell.ShellCmd('timeout 5 touch %s' % test_file)
                    touch(False)
                    if touch.return_code != 0:
                        logger.debug('touch file failed, cause: %s' % touch.stderr)
                        failure += 1
                    else:
                        failure = 0
                        linux.rm_file_force(test_file)
                        continue

                    if failure < cmd.maxAttempts:
                        continue

                    try:
                        logger.warn("aliyun nas storage %s fencer fired!" % cmd.uuid)

                        if cmd.strategy == 'Permissive':
                            continue

                        vm_uuids = kill_vm(cmd.maxAttempts).keys()

                        if vm_uuids:
                            self.report_self_fencer_triggered([cmd.uuid], ','.join(vm_uuids))
                            clean_network_config(vm_uuids)

                        # reset the failure count
                        failure = 0
                    except Exception as e:
                        logger.warn("kill vm failed, %s" % e.message)
                        content = traceback.format_exc()
                        logger.warn("traceback: %s" % content)
                    finally:
                        self.report_storage_status([cmd.uuid], 'Disconnected')

                except Exception as e:
                    logger.debug('self-fencer on aliyun nas primary storage %s stopped abnormally' % cmd.uuid)
                    content = traceback.format_exc()
                    logger.warn(content)

            logger.debug('stop self-fencer on aliyun nas primary storage %s' % cmd.uuid)

        heartbeat_on_aliyunnas()
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def cancel_sharedblock_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.cancel_fencer(cmd.vgUuid)
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_sharedblock_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        @thread.AsyncThread
        def heartbeat_on_sharedblock():
            fire = 0
            failure = 0

            while self.run_fencer(cmd.vgUuid, created_time):
                try:
                    time.sleep(cmd.interval)
                    global last_multipath_run
                    if cmd.fail_if_no_path and time.time() - last_multipath_run > 3600:
                        last_multipath_run = time.time()
                        thread.ThreadFacade.run_in_thread(linux.set_fail_if_no_path)

                    health = lvm.check_vg_status(cmd.vgUuid, cmd.storageCheckerTimeout, check_pv=False)
                    logger.debug("sharedblock group primary storage %s fencer run result: %s" % (cmd.vgUuid, health))
                    if health[0] is True:
                        fire = 0
                        failure = 0
                        continue

                    failure += 1
                    if failure < cmd.maxAttempts:
                        continue

                    if self.fencer_fire_timestamp.get(cmd.vgUuid) is not None and \
                            time.time() > self.fencer_fire_timestamp.get(cmd.vgUuid) and \
                            time.time() - self.fencer_fire_timestamp.get(cmd.vgUuid) < (300 * (fire + 1 if fire < 10 else 10)):
                        logger.warn("last fencer fire: %s, now: %s, passed: %s seconds, within %s seconds, skip fire",
                                    self.fencer_fire_timestamp[cmd.vgUuid], time.time(),
                                    time.time() - self.fencer_fire_timestamp.get(cmd.vgUuid),
                                    300 * (fire + 1 if fire < 10 else 10))
                        failure = 0
                        continue

                    self.fencer_fire_timestamp[cmd.vgUuid] = time.time()
                    try:
                        logger.warn("shared block storage %s fencer fired!" % cmd.vgUuid)
                        self.report_storage_status([cmd.vgUuid], 'Disconnected', health[1])
                        fire += 1

                        if cmd.strategy == 'Permissive':
                            continue

                        # we will check one qcow2 per pv to determine volumes on pv should be kill
                        invalid_pv_uuids = lvm.get_invalid_pv_uuids(cmd.vgUuid, cmd.checkIo)
                        vms = lvm.get_running_vm_root_volume_on_pv(cmd.vgUuid, invalid_pv_uuids, True)
                        killed_vm_uuids = []
                        for vm in vms:
                            kill = shell.ShellCmd('kill -9 %s' % vm.pid)
                            kill(False)
                            if kill.return_code == 0:
                                logger.warn(
                                    'kill the vm[uuid:%s, pid:%s] because we lost connection to the storage.'
                                    'failed to run health check %s times' % (vm.uuid, vm.pid, cmd.maxAttempts))
                                killed_vm_uuids.append(vm.uuid)
                            else:
                                logger.warn(
                                    'failed to kill the vm[uuid:%s, pid:%s] %s' % (vm.uuid, vm.pid, kill.stderr))

                            for volume in vm.volumes:
                                used_process = linux.linux_lsof(volume)
                                if len(used_process) == 0:
                                    try:
                                        lvm.deactive_lv(volume, False)
                                    except Exception as e:
                                        logger.debug("deactivate volume %s for vm %s failed, %s" % (volume, vm.uuid, e.message))
                                        content = traceback.format_exc()
                                        logger.warn("traceback: %s" % content)
                                else:
                                    logger.debug("volume %s still used: %s, skip to deactivate" % (volume, used_process))

                        if len(killed_vm_uuids) != 0:
                            self.report_self_fencer_triggered([cmd.vgUuid], ','.join(killed_vm_uuids))
                            clean_network_config(killed_vm_uuids)

                        lvm.remove_partial_lv_dm(cmd.vgUuid)

                        if lvm.check_vg_status(cmd.vgUuid, cmd.storageCheckerTimeout, True)[0] is False:
                            lvm.drop_vg_lock(cmd.vgUuid)
                            lvm.remove_device_map_for_vg(cmd.vgUuid)

                    except Exception as e:
                        logger.warn("kill vm failed, %s" % e.message)
                        content = traceback.format_exc()
                        logger.warn("traceback: %s" % content)
                    finally:
                        failure = 0

                except Exception as e:
                    logger.debug('self-fencer on sharedblock primary storage %s stopped abnormally, try again soon...' % cmd.vgUuid)
                    content = traceback.format_exc()
                    logger.warn(content)

            if not self.run_fencer(cmd.vgUuid, created_time):
                logger.debug('stop self-fencer on sharedblock primary storage %s for judger failed' % cmd.vgUuid)
            else:
                logger.warn('stop self-fencer on sharedblock primary storage %s' % cmd.vgUuid)

        created_time = time.time()
        self.setup_fencer(cmd.vgUuid, created_time)
        heartbeat_on_sharedblock()
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_ceph_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        mon_url = '\;'.join(cmd.monUrls)
        mon_url = mon_url.replace(':', '\\\:')

        created_time = time.time()
        self.setup_fencer(cmd.uuid, created_time)

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
            touch = shell.ShellCmd('timeout %s %s %s' %
                    (cmd.storageCheckerTimeout, qemu_img.subcmd('info'), get_ceph_rbd_args()))
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

                while self.run_fencer(cmd.uuid, created_time):
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
                            if cmd.strategy == 'Permissive':
                                continue

                            path = (os.path.split(cmd.heartbeatImagePath))[0]
                            vm_uuids = kill_vm(cmd.maxAttempts, [path], False).keys()

                            if vm_uuids:
                                self.report_self_fencer_triggered([cmd.uuid], ','.join(vm_uuids))
                                clean_network_config(vm_uuids)
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
        def heartbeat_file_fencer(mount_path, ps_uuid, mounted_by_zstack, url, options):
            def try_remount_fs():
                if mount_path_is_nfs(mount_path):
                    shell.run("systemctl start nfs-client.target")

                while self.run_fencer(ps_uuid, created_time):
                    if linux.is_mounted(path=mount_path) and touch_heartbeat_file():
                        self.report_storage_status([ps_uuid], 'Connected')
                        logger.debug("fs[uuid:%s] is reachable again, report to management" % ps_uuid)
                        break
                    try:
                        logger.debug('fs[uuid:%s] is unreachable, it will be remounted after 180s' % ps_uuid)
                        time.sleep(180)
                        if not self.run_fencer(ps_uuid, created_time):
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

            def touch_heartbeat_file():
                touch = shell.ShellCmd('timeout %s touch %s' % (cmd.storageCheckerTimeout, heartbeat_file_path))
                touch(False)
                if touch.return_code != 0:
                    logger.warn('unable to touch %s, %s %s' % (heartbeat_file_path, touch.stderr, touch.stdout))
                return touch.return_code == 0

            def prepare_heartbeat_dir():
                heartbeat_dir = os.path.join(mount_path, "zs-heartbeat")
                if not mounted_by_zstack or linux.is_mounted(mount_path):
                    if not os.path.exists(heartbeat_dir):
                        os.makedirs(heartbeat_dir, 0755)
                else:
                    if os.path.exists(heartbeat_dir):
                        linux.rm_dir_force(heartbeat_dir)
                return heartbeat_dir

            heartbeat_file_dir = prepare_heartbeat_dir()
            heartbeat_file_path = os.path.join(heartbeat_file_dir, 'heartbeat-file-kvm-host-%s.hb' % cmd.hostUuid)
            created_time = time.time()
            self.setup_fencer(ps_uuid, created_time)
            try:
                failure = 0
                while self.run_fencer(ps_uuid, created_time):
                    time.sleep(cmd.interval)
                    if touch_heartbeat_file():
                        failure = 0
                        continue

                    failure += 1
                    if failure == cmd.maxAttempts:
                        logger.warn('failed to touch the heartbeat file[%s] %s times, we lost the connection to the storage,'
                                    'shutdown ourselves' % (heartbeat_file_path, cmd.maxAttempts))
                        self.report_storage_status([ps_uuid], 'Disconnected')

                        if cmd.strategy == 'Permissive':
                            continue

                        killed_vms = kill_vm(cmd.maxAttempts, [mount_path], True)

                        if len(killed_vms) != 0:
                            self.report_self_fencer_triggered([ps_uuid], ','.join(killed_vms.keys()))
                            clean_network_config(killed_vms.keys())

                        killed_vm_pids = killed_vms.values()
                        after_kill_vm()

                        if mounted_by_zstack and not linux.is_mounted(mount_path):
                            try_remount_fs()
                            prepare_heartbeat_dir()

                logger.debug('stop heartbeat[%s] for filesystem self-fencer' % heartbeat_file_path)

            except:
                content = traceback.format_exc()
                logger.warn(content)

        for mount_path, uuid, mounted_by_zstack, url, options in zip(cmd.mountPaths, cmd.uuids, cmd.mountedByZStack, cmd.urls, cmd.mountOptions):
            if not linux.timeout_isdir(mount_path):
                raise Exception('the mount path[%s] is not a directory' % mount_path)

            heartbeat_file_fencer(mount_path, uuid, mounted_by_zstack, url, options)

        return jsonobject.dumps(AgentRsp())


    @kvmagent.replyerror
    def scan_host(self, req):
        rsp = ScanRsp()

        success = 0
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for i in range(0, cmd.times):
            if shell.run("nmap --host-timeout 10s -sP -PI %s | grep -q 'Host is up'" % cmd.ip) == 0:
                success += 1

            if success == cmd.successTimes:
                rsp.result = self.RET_SUCCESS
                return jsonobject.dumps(rsp)

            time.sleep(cmd.interval)

        if success == 0:
            rsp.result = self.RET_FAILURE
            return jsonobject.dumps(rsp)

        # WE SUCCEED A FEW TIMES, IT SEEMS THE CONNECTION NOT STABLE
        success = 0
        for i in range(0, cmd.successTimes):
            if shell.run("nmap --host-timeout 10s -sP -PI %s | grep -q 'Host is up'" % cmd.ip) == 0:
                success += 1

            time.sleep(cmd.successInterval)

        if success == cmd.successTimes:
            rsp.result = self.RET_SUCCESS
            return jsonobject.dumps(rsp)

        if success == 0:
            rsp.result = self.RET_FAILURE
            return jsonobject.dumps(rsp)

        rsp.result = self.RET_NOT_STABLE
        logger.info('scanhost[%s]: %s' % (cmd.ip, rsp.result))
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def sanlock_scan_host(self, req):
        rsp = SanlockScanRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        cstatus = shell.call("timeout 5 sanlock client gets -h 1")
        logger.info("[SANLOCK] reports client status:\n" + cstatus)
        myIds = [ int(line.split(':', 3)[1]) for line in filter(lambda x: x.startswith('s'), cstatus.splitlines()) ]

        if len(myIds) == 0:
            logger.info("[SANLOCK] host id not found")
            return jsonobject.dumps(rsp)

        hstatus = shell.call("timeout 5 sanlock client host_status -D")
        parser = SanlockHostStatusParser(hstatus)

        is_alive = False
        for hostId in myIds:
            is_alive = parser.is_alive(hostId)
            if is_alive: break

        if not is_alive:
            logger.info("[SANLOCK] current node has no LIVE records")
            return jsonobject.dumps(rsp)

        result = {}
        for hostId in cmd.hostIds:
            timed_out = parser.is_timed_out(hostId)
            if timed_out is not None:
                result[str(hostId)] = not timed_out

        rsp.result = result
        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.SCAN_HOST_PATH, self.scan_host)
        http_server.register_async_uri(self.SANLOCK_SCAN_HOST_PATH, self.sanlock_scan_host)
        http_server.register_async_uri(self.SETUP_SELF_FENCER_PATH, self.setup_self_fencer)
        http_server.register_async_uri(self.CEPH_SELF_FENCER, self.setup_ceph_self_fencer)
        http_server.register_async_uri(self.CANCEL_SELF_FENCER_PATH, self.cancel_filesystem_self_fencer)
        http_server.register_async_uri(self.CANCEL_CEPH_SELF_FENCER, self.cancel_ceph_self_fencer)
        http_server.register_async_uri(self.SHAREDBLOCK_SELF_FENCER, self.setup_sharedblock_self_fencer)
        http_server.register_async_uri(self.CANCEL_SHAREDBLOCK_SELF_FENCER, self.cancel_sharedblock_self_fencer)
        http_server.register_async_uri(self.ALIYUN_NAS_SELF_FENCER, self.setup_aliyun_nas_self_fencer)
        http_server.register_async_uri(self.CANCEL_NAS_SELF_FENCER, self.cancel_aliyun_nas_self_fencer)

    def stop(self):
        pass

    def configure(self, config):
        self.config = config

    @thread.AsyncThread
    def report_self_fencer_triggered(self, ps_uuids, vm_uuids_string=None):
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            logger.warn('cannot find SEND_COMMAND_URL, unable to report self fencer triggered on [psList:%s]' % ps_uuids)
            return

        host_uuid = self.config.get(kvmagent.HOST_UUID)
        if not host_uuid:
            logger.warn(
                'cannot find HOST_UUID, unable to report self fencer triggered on [psList:%s]' % ps_uuids)
            return

        def report_to_management_node():
            cmd = ReportSelfFencerCmd()
            cmd.psUuids = ps_uuids
            cmd.hostUuid = host_uuid
            cmd.vmUuidsString = vm_uuids_string
            cmd.reason = "primary storage[uuids:%s] on host[uuid:%s] heartbeat fail, self fencer has been triggered" % (ps_uuids, host_uuid)

            logger.debug(
                'host[uuid:%s] primary storage[psList:%s], triggered self fencer, report it to %s' % (
                    host_uuid, ps_uuids, url))
            http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportselffencer'})

        report_to_management_node()


    @thread.AsyncThread
    def report_storage_status(self, ps_uuids, ps_status, reason=""):
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
            cmd.reason = reason

            logger.debug(
                'primary storage[psList:%s] has new connection status[%s], report it to %s' % (
                    ps_uuids, ps_status, url))
            http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportstoragestatus'})

        report_to_management_node()

    def run_fencer(self, ps_uuid, created_time):
        with self.fencer_lock:
            if not self.run_fencer_timestamp[ps_uuid] or self.run_fencer_timestamp[ps_uuid] > created_time:
                return False

            self.run_fencer_timestamp[ps_uuid] = created_time
            return True

    def setup_fencer(self, ps_uuid, created_time):
        with self.fencer_lock:
            self.run_fencer_timestamp[ps_uuid] = created_time

    def cancel_fencer(self, ps_uuid):
        with self.fencer_lock:
            self.run_fencer_timestamp.pop(ps_uuid, None)

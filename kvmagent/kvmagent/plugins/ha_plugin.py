from kvmagent import kvmagent
from zstacklib.utils import bash
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import lvm
from zstacklib.utils import thread
from zstacklib.utils import qemu_img
from zstacklib.utils import ceph
import os.path
import re
from string import whitespace
import time
import traceback
import threading
import rados
import rbd
from datetime import datetime, timedelta

logger = log.get_logger(__name__)

class UmountException(Exception):
    pass

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


class CephHostHeartbeatCheckRsp(AgentRsp):
    def __init__(self):
        super(CephHostHeartbeatCheckRsp, self).__init__()
        self.result = None


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
        self.fencerFailure = None


class SanlockHostStatus(object):
    def __init__(self, record):
        lines = record.strip().splitlines()
        hid, s, ts = lines[0].split()
        if s != 'timestamp':
            raise Exception('unexpected sanlock host status: ' + record)
        self.host_id = int(hid)
        self.timestamp = int(ts)

        for line in lines[1:]:
            try:
                k, v = line.strip().split('=', 2)
                if k == 'io_timeout': self.io_timeout = int(v)
                elif k == 'last_check': self.last_check = int(v)
                elif k == 'last_live': self.last_live = int(v)
            except ValueError:
                logger.warn("unexpected sanlock status: %s" % line)

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


class SanlockClientStatus(object):
    def __init__(self, status_lines):
        self.lockspace = status_lines[0].split()[1]
        self.is_adding = ':0 ADD' in status_lines[0]

        for line in status_lines[1:]:
            try:
                k, v = line.strip().split('=', 2)
                if k == 'renewal_last_result': self.renewal_last_result = int(v)
                elif k == 'renewal_last_attempt': self.renewal_last_attempt = int(v)
                elif k == 'renewal_last_success': self.renewal_last_success = int(v)
            except ValueError:
                logger.warn("unexpected sanlock client status: %s" % line)

    def get_lockspace(self):
        return self.lockspace

    def get_renewal_last_result(self):
        return self.renewal_last_result

    def get_renewal_last_attempt(self):
        return self.renewal_last_attempt

    def get_renewal_last_success(self):
        return self.renewal_last_success


class SanlockClientStatusParser(object):
    def __init__(self, status):
        self.status = status
        self.lockspace_records = None  # type: list[SanlockClientStatus]

    def get_lockspace_records(self):
        if self.lockspace_records is None:
            self.lockspace_records = self._do_get_lockspace_records()
        return self.lockspace_records

    def get_lockspace_record(self, needle):
        for r in self.get_lockspace_records():
            if needle in r.get_lockspace():
                return r
        return None

    def _do_get_lockspace_records(self):
        records = []
        current_lines = []

        for line in self.status.splitlines():
            if len(line) == 0:
                continue

            if line[0] in whitespace and len(current_lines) > 0:
                current_lines.append(line)
                continue

            # found new records - check whether to complete last record.
            if len(current_lines) > 0:
                records.append(SanlockClientStatus(current_lines))
                current_lines = []

            if line.startswith("s "):
                current_lines.append(line)

        if len(current_lines) > 0:
            records.append(SanlockClientStatus(current_lines))

        return records


class SanlockHealthChecker(object):
    def __init__(self):
        self.vg_failures = {}   # type: dict[str, int]
        self.all_vgs = {}       # type: dict[str, object]
        self.fencer_created_time = {}     # type: dict[str, float]
        self.fencer_fire_cnt = {}         # type: dict[str, int]

    def inc_vg_failure_cnt(self, vg_uuid):
        count = self.vg_failures.get(vg_uuid)
        if count is None:
            self.vg_failures[vg_uuid] = 1
            return 1

        self.vg_failures[vg_uuid] = count+1
        return count+1

    def reset_vg_failure_cnt(self, vg_uuid):
        self.vg_failures.pop(vg_uuid, 0)

    def inc_fencer_fire_cnt(self, vg_uuid):
        count = self.fencer_fire_cnt.get(vg_uuid)
        if count is None:
            self.fencer_fire_cnt[vg_uuid] = 1
            return 1

        self.fencer_fire_cnt[vg_uuid] = count+1
        return count+1

    def reset_fencer_fire_cnt(self, vg_uuid):
        self.fencer_fire_cnt.pop(vg_uuid, 0)

    def get_fencer_fire_cnt(self, vg_uuid):
        cnt = self.fencer_fire_cnt.get(vg_uuid)
        return 0 if cnt is None else cnt

    def addvg(self, created_time, fencer_cmd):
        vg_uuid = fencer_cmd.vgUuid
        self.all_vgs[vg_uuid] = fencer_cmd
        self.fencer_created_time[vg_uuid] = created_time

    def delvg(self, vg_uuid):
        self.all_vgs.pop(vg_uuid, None)
        self.vg_failures.pop(vg_uuid, None)
        self.fencer_created_time.pop(vg_uuid, None)
        self.fencer_fire_cnt.pop(vg_uuid, None)

    def get_vg_fencer_cmd(self, vg_uuid):
        return self.all_vgs.get(vg_uuid)

    def get_created_time(self, vg_uuid):
        return self.fencer_created_time.get(vg_uuid)

    def _do_health_check_vg(self, vg, lockspaces, r):
        if not r:
            failure = "lockspace for vg %s not found" % vg
            logger.warn(failure)
            return self.inc_vg_failure_cnt(vg), failure

        if r.is_adding:
            logger.warn("lockspace for vg %s is adding, skip run fencer" % vg)
            return 0, None

        if r.get_lockspace() not in lockspaces:
            failure = "can not find lockspace of %s" % vg
            logger.warn(failure)
            return self.inc_vg_failure_cnt(vg), failure

        if r.get_renewal_last_result() != 1:
            if (r.get_renewal_last_attempt() > r.get_renewal_last_success() and \
                    r.get_renewal_last_attempt() - r.get_renewal_last_success() > 100) or \
                    (r.get_renewal_last_attempt() < r.get_renewal_last_success() - 100 < r.get_renewal_last_success()):
                failure = "sanlock last renewal failed with %s and last attempt is %s, last success is %s" % \
                        (r.get_renewal_last_result(), r.get_renewal_last_attempt(), r.get_renewal_last_success())
                logger.warn(failure)
                return self.inc_vg_failure_cnt(vg), failure

        return 0, None

    def _do_health_check(self, storage_timeout, max_failure):
        def _do_get_client_status():
            return bash.bash_o("sanlock client status -D")

        def _do_get_lockspaces():
            lines = bash.bash_o("sanlock client gets").splitlines()
            return [ s.split()[1] for s in lines if s.startswith('s ') ]

        lockspaces = _do_get_lockspaces()
        p = SanlockClientStatusParser(_do_get_client_status())
        victims = {}  # type: dict[str, str]

        for vg in self.all_vgs:
            r = p.get_lockspace_record(vg)
            try:
                cnt, failure = self._do_health_check_vg(vg, lockspaces, r)
                if cnt == 0:
                    self.reset_vg_failure_cnt(vg)
                else:
                    logger.info("vg %s failure count: %d" % (vg, cnt))
                    if cnt >= max_failure:
                        victims[vg] = failure
            except Exception as e:
                logger.warn("_do_health_check_vg(%s) failed, %s" % (vg, e.message))

        return victims

    def runonce(self, storage_timeout, max_failure):
        if len(self.all_vgs) == 0:
            return {}

        logger.debug('running sblk health checker')
        return self._do_health_check(storage_timeout, max_failure)


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
    for vm_uuid in vm_in_process_uuid_list.splitlines():
        vm_uuid = vm_uuid.strip()
        if not vm_uuid:
            continue

        if mountPaths and isFileSystem is not None \
                and not need_kill(vm_uuid, mountPaths, isFileSystem):
            continue

        vm_pid = linux.find_vm_pid_by_uuid(vm_uuid)
        if not vm_pid:
            logger.warn('vm %s pid not found' % vm_uuid)
            continue

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
    out = linux.find_vm_process_by_uuid(vm_uuid)
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
    CEPH_HOST_HEARTBEAT_CHECK_PATH = "/ceph/host/heartbeat/check"
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
        self.sblk_health_checker = SanlockHealthChecker()
        self.sblk_fencer_running = False

    class CephHeartbeatController(object):
        def __init__(self):
            self.failure = 0
            self.storage_failure = False
            self.report_storage_status = False
            self.max_attempts = None
            self.host_uuid = None
            self.pool_name = None
            self.primary_storage_uuid = None
            self.strategy = None
            self.storage_check_timeout = None
            self.heartbeat_object_name = None
            self.fencer_triggered_callback = None

        def ceph_in_error_stat(self):
            # HEALTH_OK,HEALTH_WARN,HEALTH_ERR and others(may be empty)...
            health = shell.ShellCmd('timeout %s ceph health' % self.storage_check_timeout)
            health(False)
            # If the command times out, then exit with status 124
            if health.return_code == 124:
                return True

            health_status = health.stdout
            return not (health_status.startswith('HEALTH_OK') or health_status.startswith('HEALTH_WARN'))

        def handle_heartbeat_failure(self):
            self.failure += 1
            logger.debug("heartbeat of host:%s on ceph storage:%s pool:%s failure(%d/%d)" %
                        (self.host_uuid, self.primary_storage_uuid, self.pool_name, self.failure, self.max_attempts))

            if self.failure >= self.max_attempts:
                # c.f. We discovered that, Ceph could behave the following:
                #  1. Create heart-beat file, failed with 'File exists'
                #  2. Query the hb file in step 1, and failed again with 'No such file or directory'
                if self.ceph_in_error_stat():
                    if self.strategy == 'Permissive':
                        logger.debug("ceph fencer detect ha strategy is %s skip fence vms" % self.strategy)
                        self.reset_failure_count()
                        return

                    # for example, pool name is aaa
                    # add slash to confirm kill_vm matches vm with volume aaa/volume_path
                    # but not aaa_suffix/volume_path
                    vm_uuids = kill_vm(self.max_attempts, ['%s/' % self.pool_name], False).keys()

                    if vm_uuids:
                        try:
                            self.fencer_triggered_callback([self.primary_storage_uuid], ','.join(vm_uuids))
                        except Exception as e:
                            logger.debug('failed to report fencer triggered result to management node')
                            content = traceback.format_exc()
                            logger.warn(content)
                        clean_network_config(vm_uuids)

                    self.storage_failure = True
                    self.report_storage_status = True

                # reset the failure count
                self.reset_failure_count()

        def reset_failure_count(self):
            self.failure = 0

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

        def _do_fencer_vg(vg, failure):

            fire = self.sblk_health_checker.get_fencer_fire_cnt(vg)
            if self.fencer_fire_timestamp.get(vg) is not None and \
                    time.time() > self.fencer_fire_timestamp.get(vg) and \
                    time.time() - self.fencer_fire_timestamp.get(vg) < (300 * (fire + 1 if fire < 10 else 10)):
                logger.warn("last fencer fire: %s, now: %s, passed: %s seconds, within %s seconds, skip fire",
                            self.fencer_fire_timestamp[vg], time.time(),
                            time.time() - self.fencer_fire_timestamp.get(vg),
                            300 * (fire + 1 if fire < 10 else 10))
                return False

            self.fencer_fire_timestamp[vg] = time.time()

            logger.warn("shared block storage %s fencer fired!" % vg)
            self.report_storage_status([vg], 'Disconnected', failure)
            self.sblk_health_checker.inc_fencer_fire_cnt(vg)

            cmd = self.sblk_health_checker.get_vg_fencer_cmd(vg)
            if cmd.strategy == 'Permissive':
                return False

            # we will check one io to determine volumes on pv should be kill
            invalid_pv_uuids = lvm.get_invalid_pv_uuids(vg, cmd.checkIo)
            logger.debug("got invalid pv uuids: %s" % invalid_pv_uuids)
            vms = lvm.get_running_vm_root_volume_on_pv(vg, invalid_pv_uuids, True)
            killed_vm_uuids = []
            for vm in vms:
                try:
                    linux.kill_process(vm.pid)
                    logger.warn(
                        'kill the vm[uuid:%s, pid:%s] because we lost connection to the storage.' % (vm.uuid, vm.pid))
                    killed_vm_uuids.append(vm.uuid)
                except:
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
                self.report_self_fencer_triggered([vg], ','.join(killed_vm_uuids))
                clean_network_config(killed_vm_uuids)

            lvm.remove_partial_lv_dm(vg)

            if lvm.check_vg_status(vg, cmd.storageCheckerTimeout, True)[0] is False:
                lvm.drop_vg_lock(vg)
                lvm.remove_device_map_for_vg(vg)

            return True


        @thread.AsyncThread
        def fire_fencer(failed_vgs):
            logger.debug("SBLK failed vgs: %s" % failed_vgs)

            for vg, failure in failed_vgs.items():
                try:
                    if _do_fencer_vg(vg, failure):
                        self.sblk_health_checker.delvg(vg)
                except Exception as e:
                    logger.warn("fencer for vg %s failed, %s\n%s" % (vg, e.message, traceback.format_exc()))


        @thread.AsyncThread
        def heartbeat_on_sharedblock(interval, storage_timeout, max_failure):
            while True:
                try:
                    time.sleep(interval)
                    global last_multipath_run
                    if cmd.fail_if_no_path and time.time() - last_multipath_run > 3600:
                        last_multipath_run = time.time()
                        thread.ThreadFacade.run_in_thread(linux.set_fail_if_no_path)

                    failed_vgs = self.sblk_health_checker.runonce(storage_timeout, max_failure)
                    if len(failed_vgs) != 0:
                        fire_fencer(failed_vgs)

                except Exception as e:
                    logger.debug('self-fencer on sharedblock primary storage stopped abnormally, try again soon...')
                    content = traceback.format_exc()
                    logger.warn(content)


        created_time = time.time()
        self.setup_fencer(cmd.vgUuid, created_time)

        self.sblk_health_checker.addvg(created_time, cmd)
        with self.fencer_lock:
            if not self.sblk_fencer_running:
                heartbeat_on_sharedblock(cmd.interval, cmd.storageCheckerTimeout, cmd.maxAttempts)
                self.sblk_fencer_running = True

        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def setup_ceph_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        mon_url = '\;'.join(cmd.monUrls)
        mon_url = mon_url.replace(':', '\\\:')

        created_time = time.time()

        def get_fencer_key(ps_uuid, pool_name):
            return '%s-%s' % (ps_uuid, pool_name)

        def update_heartbeat_timestamp(ioctx, heartbeat_object_name, heartbeat_count, write_timeout=5):
            def update_heartbeat_timestamp_callback(*ignores):
                pass

            completion = ioctx.aio_write(heartbeat_object_name, str(heartbeat_count), 0, update_heartbeat_timestamp_callback)

            waited_time = 0
            while not completion.is_complete():
                time.sleep(1)
                waited_time += 1
                if waited_time == write_timeout:
                    logger.debug("write operation to %s not finished util timeout, report update failure" % heartbeat_object_name)
                    return False, waited_time

            return True, waited_time

        @thread.AsyncThread
        def heartbeat_on_ceph(ps_uuid, pool_name):
            self.setup_fencer(get_fencer_key(ps_uuid, pool_name), created_time)

            ceph_controller = self.CephHeartbeatController()
            ceph_controller.pool_name = pool_name
            ceph_controller.primary_storage_uuid = ps_uuid
            ceph_controller.max_attempts = cmd.maxAttempts
            ceph_controller.report_storage_status = False
            ceph_controller.storage_failure = False
            ceph_controller.failure = 0
            ceph_controller.strategy = cmd.strategy
            ceph_controller.storage_check_timeout = cmd.storageCheckerTimeout
            ceph_controller.host_uuid = cmd.hostUuid
            ceph_controller.heartbeat_object_name = ceph.get_heartbeat_object_name(cmd.uuid, cmd.hostUuid)
            ceph_controller.fencer_triggered_callback = self.report_self_fencer_triggered

            try:
                conf_path, keyring_path, username = ceph.update_ceph_client_access_conf(ps_uuid, cmd.monUrls, cmd.userKey, cmd.manufacturer)
                logger.debug("config file: %s, pool name: %s" % (conf_path, pool_name))
                heartbeat_counter = 0
                additional_conf_dict = {}
                if keyring_path:
                    additional_conf_dict['keyring'] = keyring_path

                with rados.Rados(conffile=conf_path, conf=additional_conf_dict, name=username) as cluster:
                    logger.debug("connected to ceph[uuid: %s] cluster" % ceph_controller.primary_storage_uuid)
                    with cluster.open_ioctx(pool_name) as ioctx:
                        logger.debug("open ceph[uuid: %s] pool: %s]" % (ceph_controller.primary_storage_uuid, ceph_controller.pool_name))
                        write_heartbeat_used_time = None
                        while self.run_fencer(get_fencer_key(ps_uuid, pool_name), created_time):
                            if write_heartbeat_used_time:
                                # wait an interval before next heartbeat
                                time.sleep(cmd.interval)

                            # reset variables
                            write_heartbeat_used_time = 0
                            heartbeat_success = False
                                                            
                            heartbeat_success, write_heartbeat_used_time = update_heartbeat_timestamp(ioctx, ceph_controller.heartbeat_object_name, heartbeat_counter, cmd.storageCheckerTimeout)

                            if heartbeat_counter > 100000:
                                heartbeat_counter = 0
                            else:
                                heartbeat_counter += 1
                            if heartbeat_success and ceph_controller.storage_failure and not ceph_controller.report_storage_status:
                                # if heartbeat recovered and storage failure has occured before 
                                # set report_storage_status to False to report fencer recoverd to management node
                                ceph_controller.report_storage_status = True
                                ceph_controller.storage_failure = False

                            if ceph_controller.report_storage_status:
                                if ceph_controller.storage_failure:
                                    self.report_storage_status([cmd.uuid], 'Disconnected')
                                else:
                                    self.report_storage_status([cmd.uuid], 'Connected')
                                
                                ceph_controller.report_storage_status = False
                            
                            # after fencer state reported, set fencer_state_reported to False
                            if heartbeat_success:
                                logger.debug("heartbeat of host:%s on ceph storage:%s pool:%s success" % (cmd.hostUuid, cmd.uuid, pool_name))
                                # reset failure count after heartbeat succeed
                                ceph_controller.reset_failure_count()
                                continue

                            ceph_controller.handle_heartbeat_failure()

                logger.debug('stop self-fencer on pool %s of ceph primary storage' % pool_name)
            except:
                logger.debug('self-fencer on pool %s ceph primary storage stopped abnormally' % pool_name)
                content = traceback.format_exc()
                logger.warn(content)
                self.report_storage_status([cmd.uuid], 'Disconnected')

        for pool_name in cmd.poolNames:
            heartbeat_on_ceph(cmd.uuid, pool_name)

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
                        os.makedirs(heartbeat_dir, 0o755)
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
    def ceph_host_heartbeat_check(self, req):
        rsp = CephHostHeartbeatCheckRsp()
        result = {}

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        ceph_conf, keyring_path, username = ceph.get_ceph_client_conf(cmd.primaryStorageUuid, cmd.manufacturer)

        if not os.path.exists(ceph_conf):
            rsp.success = False
            return jsonobject.dumps(rsp)

        additional_conf_dict = {}
        if keyring_path:
            # use additional_conf_dict to make keyring file a config of Rados connection
            # and resolve compatibility issue of open-source and other types of ceph storage.
            additional_conf_dict['keyring'] = keyring_path

        heartbeat_success = False
        for pool_name in cmd.poolNames:
            image = None
            with rados.Rados(conffile=ceph_conf, conf=additional_conf_dict, name=username) as cluster:
                with cluster.open_ioctx(pool_name) as ioctx:
                    heartbeat_object_name = ceph.get_heartbeat_object_name(cmd.primaryStorageUuid, cmd.targetHostUuid)
                    if not heartbeat_object_name:
                        logger.debug("Failed to get heartbeat file info of pool %s" % pool_name)
                        continue

                    lastest_heartbeat_count = [None]
                    current_heartbeat_count = [None]
                    def get_current_completion(_, content):
                        current_heartbeat_count[0] = int(str(content).strip())
                        logger.debug("host last heartbeat is %s, host current heartbeat count is %s" % (lastest_heartbeat_count[0], current_heartbeat_count[0]))

                    logger.debug("check if %s is still alive" % cmd.targetHostUuid)
                    wait_heartbeat_count_failure = 0
                    remain_timeout = cmd.storageCheckerTimeout
                    while wait_heartbeat_count_failure < cmd.times + 1:
                        if lastest_heartbeat_count[0]:
                            time.sleep(cmd.interval + remain_timeout)
                        remain_timeout = cmd.storageCheckerTimeout

                        completion = ioctx.aio_read(heartbeat_object_name, 10, 0, get_current_completion)
                        #print str(content).strip()
                        failure_count = 0
                        while not completion.is_complete():
                            if failure_count == cmd.storageCheckerTimeout:
                                break

                            time.sleep(1)
                            failure_count = failure_count + 1
                        
                        remain_timeout = remain_timeout - failure_count
 
                        completion.wait_for_complete_and_cb()

                        if current_heartbeat_count[0] is None:
                            wait_heartbeat_count_failure += 1
                            continue

                        if lastest_heartbeat_count[0] is None:
                            lastest_heartbeat_count[0] = current_heartbeat_count[0]
                            continue

                        heartbeat_success = current_heartbeat_count[0] != lastest_heartbeat_count[0]
                        if heartbeat_success and lastest_heartbeat_count[0] is not None:
                            logger.debug("host[uuid:%s]'s heartbeat updated, it is still alive" % cmd.targetHostUuid)
                            break
                        else:
                            wait_heartbeat_count_failure += 1

                    result[pool_name] = heartbeat_success
                    if not heartbeat_success:
                        break
        
        rsp.result = result
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def sanlock_scan_host(self, req):
        def parseLockspaceHostIdPair(s):
            xs = s.split(':', 3)
            return xs[0].split()[-1], int(xs[1])

        def check_host_status(myHostId, lkspc, hostIds):
            hstatus = shell.call("timeout 5 sanlock client host_status -s %s -D" % lkspc)
            parser = SanlockHostStatusParser(hstatus)

            result = {}
            if not parser.is_alive(myHostId):
                logger.info("[SANLOCK] current node has no LIVE records for lockspace: %s" % lkspc)
                return result

            for target in cmd.hostIds:
                hostId, psUuid = target.hostId, target.psUuid
                if psUuid not in lkspc: continue

                timed_out = parser.is_timed_out(hostId)
                if timed_out is not None:
                    result[psUuid + '_' + str(hostId)] = not timed_out
            return result

        rsp = SanlockScanRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        cstatus = shell.call("timeout 5 sanlock client gets -h 1")
        logger.info("[SANLOCK] reports client status:\n" + cstatus)
        pairs = [ parseLockspaceHostIdPair(line) for line in filter(lambda x: x.startswith('s'), cstatus.splitlines()) ]

        if len(pairs) == 0:
            logger.info("[SANLOCK] host id not found")
            return jsonobject.dumps(rsp)

        result = {}
        for lkspc, hid in pairs:
            res = check_host_status(hid, lkspc, cmd.hostIds)
            result.update(res)

        if len(result) == 0:
            return jsonobject.dumps(rsp)

        rsp.result = result
        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.SCAN_HOST_PATH, self.scan_host)
        http_server.register_async_uri(self.SANLOCK_SCAN_HOST_PATH, self.sanlock_scan_host)
        http_server.register_async_uri(self.CEPH_HOST_HEARTBEAT_CHECK_PATH, self.ceph_host_heartbeat_check)
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
            cmd.fencerFailure = True
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
            if ps_uuid not in self.run_fencer_timestamp or self.run_fencer_timestamp[ps_uuid] > created_time:
                return False

            self.run_fencer_timestamp[ps_uuid] = created_time
            return True

    def setup_fencer(self, ps_uuid, created_time):
        with self.fencer_lock:
            self.run_fencer_timestamp[ps_uuid] = created_time

    def cancel_fencer(self, ps_uuid):
        with self.fencer_lock:
            for key in self.run_fencer_timestamp.keys():
                if ps_uuid in key:
                    self.run_fencer_timestamp.pop(ps_uuid, None)
                    self.sblk_health_checker.delvg(ps_uuid)  # ugly ...

import os
import os.path
import re
import random
import tempfile
import time
import traceback


from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import lock
from zstacklib.utils import lvm
from zstacklib.utils import bash
from zstacklib.utils import qemu_img
from zstacklib.utils import traceable_shell
from zstacklib.utils.report import *
from zstacklib.utils.plugin import completetask
import zstacklib.utils.uuidhelper as uuidhelper
from zstacklib.utils import secret

logger = log.get_logger(__name__)
LOCK_FILE = "/var/run/zstack/sharedblock.lock"
INIT_TAG = "zs::sharedblock::init"
HEARTBEAT_TAG = "zs::sharedblock::heartbeat"
VOLUME_TAG = "zs::sharedblock::volume"
IMAGE_TAG = "zs::sharedblock::image"
DEFAULT_VG_METADATA_SIZE = "2g"
DEFAULT_SANLOCK_LV_SIZE = "1024"
QMP_SOCKET_PATH = "/var/lib/libvirt/qemu/zstack"
MAX_ACTUAL_SIZE_FACTOR = 3


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None
        self.totalCapacity = None
        self.availableCapacity = None
        self.lunCapacities = None


class ConnectRsp(AgentRsp):
    def __init__(self):
        super(ConnectRsp, self).__init__()
        self.isFirst = False
        self.hostId = None
        self.vgLvmUuid = None
        self.hostUuid = None


class RevertVolumeFromSnapshotRsp(AgentRsp):
    def __init__(self):
        super(RevertVolumeFromSnapshotRsp, self).__init__()
        self.newVolumeInstallPath = None
        self.size = None


class CreateTemplateFromVolumeRsp(AgentRsp):
    def __init__(self):
        super(CreateTemplateFromVolumeRsp, self).__init__()
        self.size = None
        self.actualSize = None


class MergeSnapshotRsp(AgentRsp):
    def __init__(self):
        super(MergeSnapshotRsp, self).__init__()
        self.size = None
        self.actualSize = None

class CreateDataVolumeWithBackingRsp(AgentRsp):
    def __init__(self):
        super(CreateDataVolumeWithBackingRsp, self).__init__()
        self.size = None
        self.actualSize = None

class CheckBitsRsp(AgentRsp):
    def __init__(self):
        super(CheckBitsRsp, self).__init__()
        self.existing = False


class GetVolumeSizeRsp(AgentRsp):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None


class ResizeVolumeRsp(AgentRsp):
    def __init__(self):
        super(ResizeVolumeRsp, self).__init__()
        self.size = None


class ExtendMergeTargetRsp(AgentRsp):
    def __init__(self):
        super(ExtendMergeTargetRsp, self).__init__()


class OfflineMergeSnapshotRsp(AgentRsp):
    def __init__(self):
        super(OfflineMergeSnapshotRsp, self).__init__()
        self.deleted = False


class ConvertVolumeFormatRsp(AgentRsp):
    def __init__(self):
        super(ConvertVolumeFormatRsp, self).__init__()
        self.size = None


class RetryException(Exception):
    pass


class SharedBlockConnectException(Exception):
    pass


class GetBlockDevicesRsp(AgentRsp):
    blockDevices = None  # type: list[lvm.SharedBlockCandidateStruct]

    def __init__(self):
        super(GetBlockDevicesRsp, self).__init__()
        self.blockDevices = None


class GetBackingChainRsp(AgentRsp):
    backingChain = None  # type: list[str]
    totalSize = 0L

    def __init__(self):
        super(GetBackingChainRsp, self).__init__()
        self.backingChain = None
        self.totalSize = 0L


class SharedBlockMigrateVolumeStruct:
    volumeUuid = None  # type: str
    snapshotUuid = None  # type: str
    currentInstallPath = None  # type: str
    targetInstallPath = None  # type: str
    safeMode = False
    compareQcow2 = True
    exists_lock = None

    def __init__(self):
        pass


class ConvertVolumeProvisioningRsp(AgentRsp):
    actualSize = None  # type: int

    def __init__(self):
        super(ConvertVolumeProvisioningRsp, self).__init__()
        self.actualSize = 0

class GetDownloadBitsFromKvmHostProgressRsp(AgentRsp):
    def __init__(self):
        super(GetDownloadBitsFromKvmHostProgressRsp, self).__init__()
        self.totalSize = None

class DownloadBitsFromKvmHostRsp(AgentRsp):
    def __init__(self):
        super(DownloadBitsFromKvmHostRsp, self).__init__()
        self.format = None

class ShrinkSnapShotRsp(AgentRsp):
    def __init__(self):
        super(ShrinkSnapShotRsp, self).__init__()
        self.oldSize = None
        self.size = None


class GetQcow2HashValueRsp(AgentRsp):
    def __init__(self):
        super(GetQcow2HashValueRsp, self).__init__()
        self.hashValue = None


def translate_absolute_path_from_install_path(path):
    if path is None:
        raise Exception("install path can not be null")
    return path.replace("sharedblock:/", "/dev")


def get_primary_storage_uuid_from_install_path(path):
    # type: (str) -> str
    if path is None:
        raise Exception("install path can not be null")
    return path.split("/")[2]


class CheckDisk(object):
    def __init__(self, identifier):
        self.identifier = identifier

    def __eq__(self, other):
        if isinstance(other, CheckDisk):
            return self.identifier == other.identifier
        return False

    def get_path(self, raise_exception=True):
        o = self.check_disk_by_wwid()
        if o is not None:
            return o

        o = self.check_disk_by_uuid()
        if o is not None:
            return o

        o = self.check_disk_by_absolute_path()
        if o is not None:
            return o

        if raise_exception is False:
            return None

        raise Exception("can not find disk with %s as wwid, uuid or wwn, "
                        "or multiple disks qualify but no mpath device found" % self.identifier)

    @bash.in_bash
    def rescan(self, disk_name=None):
        """
        :type disk_name: str
        """
        if disk_name is None:
            disk_name = self.get_path().split("/")[-1]

        def rescan_slave(slave, raise_exception=True):
            linux.write_file("/sys/block/%s/device/rescan" % slave, "1")
            logger.debug("rescaned disk %s" % slave)

        multipath_dev = lvm.get_multipath_dmname(disk_name)
        if multipath_dev:
            t, disk_name = disk_name, multipath_dev
            # disk name is dm-xx when multi path
            slaves = linux.listdir("/sys/class/block/%s/slaves/" % disk_name)
            if slaves is None or len(slaves) == 0 or (len(slaves) == 1 and slaves[0].strip() == ""):
                logger.debug("can not get any slaves of multipath device %s" % disk_name)
                rescan_slave(disk_name, False)
            else:
                for s in slaves:
                    rescan_slave(s)
                cmd = shell.ShellCmd("multipathd resize map %s" % disk_name)
                cmd(is_exception=True)
                logger.debug("resized multipath device %s, return code: %s, stdout %s, stderr: %s" %
                             (disk_name, cmd.return_code, cmd.stdout, cmd.stderr))
            disk_name = t
        else:
            rescan_slave(disk_name)

        command = "pvresize /dev/%s" % disk_name
        if multipath_dev is not None and multipath_dev != disk_name:
            command = "pvresize /dev/%s || pvresize /dev/%s" % (disk_name, multipath_dev)
        r, o, e = bash.bash_roe(command, errorout=False)

        if r != 0 and e and re.search(r'VG(.*)lock failed', e):
            lvm.check_stuck_vglk()
            r, o, e = bash.bash_roe(command, errorout=True)
        logger.debug("resized pv %s (wwid: %s), return code: %s, stdout %s, stderr: %s" %
                     (disk_name, self.identifier, r, o, e))

    def check_disk_by_uuid(self):
        for cond in ['TYPE=\\\"mpath\\\"', '\"\"']:
            cmd = shell.ShellCmd("lsblk --pair -p -o NAME,TYPE,FSTYPE,LABEL,UUID,VENDOR,MODEL,MODE,WWN | "
                                 " grep %s | grep %s | sort | uniq" % (cond, self.identifier))
            cmd(is_exception=False)
            if len(cmd.stdout.splitlines()) == 1:
                pattern = re.compile(r'\/dev\/[^ \"]*')
                return pattern.findall(cmd.stdout)[0]

    def check_disk_by_wwid(self):
        for cond in ['dm-uuid-mpath-', "", 'scsi-', "nvme-"]:
            rp = os.path.realpath("/dev/disk/by-id/%s%s" % (cond, self.identifier))
            if os.path.exists(rp):
                return rp

    def check_disk_by_absolute_path(self):
        if os.path.exists(self.identifier):
            return self.identifier
        return None


class SharedBlockPlugin(kvmagent.KvmAgent):

    PING_PATH = "/sharedblock/ping"
    CONNECT_PATH = "/sharedblock/connect"
    DISCONNECT_PATH = "/sharedblock/disconnect"
    CREATE_VOLUME_FROM_CACHE_PATH = "/sharedblock/createrootvolume"
    DELETE_BITS_PATH = "/sharedblock/bits/delete"
    CREATE_TEMPLATE_FROM_VOLUME_PATH = "/sharedblock/createtemplatefromvolume"
    CREATE_IMAGE_CACHE_FROM_VOLUME_PATH = "/sharedblock/createimagecachefromvolume"
    UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH = "/sharedblock/sftp/upload"
    DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH = "/sharedblock/sftp/download"
    UPLOAD_BITS_TO_IMAGESTORE_PATH = "/sharedblock/imagestore/upload"
    COMMIT_BITS_TO_IMAGESTORE_PATH = "/sharedblock/imagestore/commit"
    DOWNLOAD_BITS_FROM_IMAGESTORE_PATH = "/sharedblock/imagestore/download"
    REVERT_VOLUME_FROM_SNAPSHOT_PATH = "/sharedblock/volume/revertfromsnapshot"
    MERGE_SNAPSHOT_PATH = "/sharedblock/snapshot/merge"
    EXTEND_MERGE_TARGET_PATH = "/sharedblock/snapshot/extendmergetarget";
    OFFLINE_MERGE_SNAPSHOT_PATH = "/sharedblock/snapshot/offlinemerge"
    CREATE_EMPTY_VOLUME_PATH = "/sharedblock/volume/createempty"
    CREATE_DATA_VOLUME_WITH_BACKING_PATH = "/sharedblock/volume/createwithbacking"
    CHECK_BITS_PATH = "/sharedblock/bits/check"
    RESIZE_VOLUME_PATH = "/sharedblock/volume/resize"
    CONVERT_IMAGE_TO_VOLUME = "/sharedblock/image/tovolume"
    CHANGE_VOLUME_ACTIVE_PATH = "/sharedblock/volume/active"
    GET_VOLUME_SIZE_PATH = "/sharedblock/volume/getsize"
    CHECK_DISKS_PATH = "/sharedblock/disks/check"
    ADD_SHARED_BLOCK = "/sharedblock/disks/add"
    MIGRATE_DATA_PATH = "/sharedblock/volume/migrate"
    GET_BLOCK_DEVICES_PATH = "/sharedblock/blockdevices"
    DOWNLOAD_BITS_FROM_KVM_HOST_PATH = "/sharedblock/kvmhost/download"
    CANCEL_DOWNLOAD_BITS_FROM_KVM_HOST_PATH = "/sharedblock/kvmhost/download/cancel"
    GET_DOWNLOAD_BITS_FROM_KVM_HOST_PROGRESS_PATH = "/sharedblock/kvmhost/download/progress"
    GET_BACKING_CHAIN_PATH = "/sharedblock/volume/backingchain"
    CONVERT_VOLUME_PROVISIONING_PATH = "/sharedblock/volume/convertprovisioning"
    CONFIG_FILTER_PATH = "/sharedblock/disks/filter"
    CONVERT_VOLUME_FORMAT_PATH = "/sharedblock/volume/convertformat"
    SHRINK_SNAPSHOT_PATH = "/sharedblock/snapshot/shrink"
    GET_QCOW2_HASH_VALUE_PATH = "/sharedblock/getqcow2hash"

    vgs_in_progress = set()
    vg_size = {}
    pvs_in_progress = set()
    lun_capacities = {}

    vgs_path_and_wwid = {}

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.PING_PATH, self.ping)
        http_server.register_async_uri(self.CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.DISCONNECT_PATH, self.disconnect)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.create_root_volume)
        http_server.register_async_uri(self.CREATE_DATA_VOLUME_WITH_BACKING_PATH, self.create_data_volume_with_backing)
        http_server.register_async_uri(self.DELETE_BITS_PATH, self.delete_bits)
        http_server.register_async_uri(self.CREATE_TEMPLATE_FROM_VOLUME_PATH, self.create_template_from_volume)
        http_server.register_async_uri(self.CREATE_IMAGE_CACHE_FROM_VOLUME_PATH, self.create_image_cache_from_volume)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH, self.upload_to_sftp)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH, self.download_from_sftp)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_IMAGESTORE_PATH, self.upload_to_imagestore)
        http_server.register_async_uri(self.COMMIT_BITS_TO_IMAGESTORE_PATH, self.commit_to_imagestore)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_IMAGESTORE_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.REVERT_VOLUME_FROM_SNAPSHOT_PATH, self.revert_volume_from_snapshot)
        http_server.register_async_uri(self.MERGE_SNAPSHOT_PATH, self.merge_snapshot)
        http_server.register_async_uri(self.EXTEND_MERGE_TARGET_PATH, self.extend_merge_target)
        http_server.register_async_uri(self.OFFLINE_MERGE_SNAPSHOT_PATH, self.offline_merge_snapshots)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.create_empty_volume)
        http_server.register_async_uri(self.CONVERT_IMAGE_TO_VOLUME, self.convert_image_to_volume)
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize_volume)
        http_server.register_async_uri(self.CHANGE_VOLUME_ACTIVE_PATH, self.active_lv)
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        http_server.register_async_uri(self.CHECK_DISKS_PATH, self.check_disks)
        http_server.register_async_uri(self.ADD_SHARED_BLOCK, self.add_disk)
        http_server.register_async_uri(self.MIGRATE_DATA_PATH, self.migrate_volumes)
        http_server.register_async_uri(self.GET_BLOCK_DEVICES_PATH, self.get_block_devices)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_KVM_HOST_PATH, self.download_from_kvmhost)
        http_server.register_async_uri(self.CANCEL_DOWNLOAD_BITS_FROM_KVM_HOST_PATH, self.cancel_download_from_kvmhost)
        http_server.register_async_uri(self.GET_BACKING_CHAIN_PATH, self.get_backing_chain)
        http_server.register_async_uri(self.CONVERT_VOLUME_PROVISIONING_PATH, self.convert_volume_provisioning)
        http_server.register_async_uri(self.CONFIG_FILTER_PATH, self.config_filter)
        http_server.register_async_uri(self.CONVERT_VOLUME_FORMAT_PATH, self.convert_volume_format)
        http_server.register_async_uri(self.GET_DOWNLOAD_BITS_FROM_KVM_HOST_PROGRESS_PATH, self.get_download_bits_from_kvmhost_progress)
        http_server.register_async_uri(self.SHRINK_SNAPSHOT_PATH, self.shrink_snapshot)
        http_server.register_async_uri(self.GET_QCOW2_HASH_VALUE_PATH, self.get_qcow2_hashvalue)

        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    @kvmagent.replyerror
    def check_disks(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if cmd.failIfNoPath:
            linux.set_fail_if_no_path()

        if cmd.rescan_scsi:
            shell.run("timeout 30 iscsiadm -m session -R")
            shell.run("timeout 120 /usr/bin/rescan-scsi-bus.sh")

        try:
            for diskUuid in cmd.sharedBlockUuids:
                disk = CheckDisk(diskUuid)
                path = disk.get_path()
                if cmd.rescan:
                    disk.rescan(path.split("/")[-1])
        except Exception as e:
            if cmd.vgUuid is not None and lvm.vg_exists(cmd.vgUuid) and not cmd.rescan:
                logger.warn("disk missing but volume group exists! pass it since no rescan required. details: %s" % e)
            else:
                raise e

        if cmd.vgUuid is not None and lvm.vg_exists(cmd.vgUuid):
            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, False)
            rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)

        return jsonobject.dumps(rsp)

    @staticmethod
    def get_disk_paths(disks):
        diskPaths = set()
        for disk in disks:
            diskPaths.add(disk.get_path())

        return diskPaths

    def create_vg_if_not_found(self, vgUuid, disks, hostUuid, allDisks, forceWipe=False):
        # type: (str, set([CheckDisk]), str, set([CheckDisk]), bool) -> bool
        @linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
        def find_vg(vgUuid, raise_exception = True):
            cmd = shell.ShellCmd("timeout 5 vgscan --ignorelockingfailure; vgs --nolocking %s -otags | grep %s" % (vgUuid, INIT_TAG))
            cmd(is_exception=False)
            if cmd.return_code != 0 and raise_exception:
                raise RetryException("can not find vg %s with tag %s" % (vgUuid, INIT_TAG))
            elif cmd.return_code != 0:
                return False
            return True

        @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
        def create_vg(hostUuid, vgUuid, diskPaths, raise_excption = True):
            cmd = shell.ShellCmd("vgcreate -qq --shared --addtag '%s::%s::%s::%s' --metadatasize %s %s %s" %
                                 (INIT_TAG, hostUuid, time.time(), linux.get_hostname(),
                                  DEFAULT_VG_METADATA_SIZE, vgUuid, " ".join(diskPaths)))
            cmd(is_exception=False)
            logger.debug("created vg %s, ret: %s, stdout: %s, stderr: %s" %
                         (vgUuid, cmd.return_code, cmd.stdout, cmd.stderr))
            if cmd.return_code != 0 and raise_excption:
                raise RetryException("ret: %s, stdout: %s, stderr: %s" %
                                (cmd.return_code, cmd.stdout, cmd.stderr))
            elif cmd.return_code != 0:
                return False
            else:
                return True

        diskPaths = self.get_disk_paths(disks)
        try:
            find_vg(vgUuid)
        except RetryException as e:
            if forceWipe is True:
                lvm.wipe_fs(diskPaths, vgUuid)
                lvm.config_lvm_filter(["lvm.conf", "lvmlocal.conf"], preserve_disks=self.get_disk_paths(allDisks))

            lvm.check_gl_lock()
            try:
                create_vg(hostUuid, vgUuid, self.get_disk_paths(disks))
                find_vg(vgUuid)
            except RetryException as ee:
                raise Exception("can not find vg %s with disks: %s and create vg with forceWipw=%s, %s" %
                                (vgUuid, diskPaths, forceWipe, str(ee)))
            except Exception as ee:
                raise ee
        except Exception as e:
            raise e

        return False

    @kvmagent.replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        size_cache = self.vg_size.get(cmd.vgUuid)
        if size_cache != None and linux.get_current_timestamp() - size_cache['currentTimestamp'] < 60:
            rsp.totalCapacity = size_cache['totalCapacity']
            rsp.availableCapacity = size_cache['availableCapacity']
        elif cmd.vgUuid not in self.vgs_in_progress:
            try:
                self.vgs_in_progress.add(cmd.vgUuid)
                rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
                self.vg_size[cmd.vgUuid] = {}
                self.vg_size[cmd.vgUuid]['totalCapacity'] = rsp.totalCapacity
                self.vg_size[cmd.vgUuid]['availableCapacity'] = rsp.availableCapacity
                self.vg_size[cmd.vgUuid]['currentTimestamp'] = long(linux.get_current_timestamp())
            finally:
                self.vgs_in_progress.remove(cmd.vgUuid)

        lun_capacities_cache = self.lun_capacities.get(cmd.vgUuid)
        if lun_capacities_cache is not None and linux.get_current_timestamp() - lun_capacities_cache['currentTimestamp'] < 60:
            rsp.lunCapacities = lun_capacities_cache['lun_capacities']
        elif cmd.vgUuid not in self.pvs_in_progress:
            try:
                self.pvs_in_progress.add(cmd.vgUuid)
                rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
                self.lun_capacities[cmd.vgUuid] = {}
                self.lun_capacities[cmd.vgUuid]['lun_capacities'] = rsp.lunCapacities
                self.lun_capacities[cmd.vgUuid]['currentTimestamp'] = long(linux.get_current_timestamp())
            finally:
                self.pvs_in_progress.remove(cmd.vgUuid)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def connect(self, req):
        @linux.retry(times=10, sleep_time=random.uniform(0.1, 1))
        def get_lock(sblk_lock):
            sblk_lock.lock = lock._get_lock(sblk_lock.name)
            if sblk_lock.lock.acquire(False) is False:
                raise SharedBlockConnectException("can not get %s lock, there is other thread running" % sblk_lock.name)

        def release_lock(sblk_lock):
            try:
                sblk_lock.lock.release()
            except Exception:
                return

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        global MAX_ACTUAL_SIZE_FACTOR
        MAX_ACTUAL_SIZE_FACTOR = cmd.maxActualSizeFactor
        sblk_lock = lock.NamedLock("sharedblock-%s" % cmd.vgUuid)
        rsp = None
        try:
            get_lock(sblk_lock)
            rsp = self.do_connect(cmd)
        except SharedBlockConnectException as e:
            r = AgentRsp()
            r.success = False
            r.error = "can not connect sharedblock primary storage[uuid: %s] on host[uuid: %s], " \
                        "because other thread is connecting now" % (cmd.vgUuid, cmd.hostUuid)
            rsp = jsonobject.dumps(r)
        except Exception as e:
            if rsp is None:
                r = AgentRsp()
                r.success = False
                content = traceback.format_exc()
                r.error = "%s\n%s" % (str(e), content)
                rsp = jsonobject.dumps(r)
        finally:
            release_lock(sblk_lock)
            return rsp

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def do_connect(self, cmd):
        rsp = ConnectRsp()
        diskPaths = set()
        disks = set()
        allDiskPaths = set()
        allDisks = set()

        self.vgs_path_and_wwid[cmd.vgUuid] = {}
        for diskUuid in cmd.sharedBlockUuids:
            disk = CheckDisk(diskUuid)
            disks.add(disk)
            diskPaths.add(disk.get_path())

        for diskUuid in cmd.allSharedBlockUuids:
            disk = CheckDisk(diskUuid)
            p = disk.get_path()
            if p is not None:
                allDiskPaths.add(p)
                allDisks.add(disk)
                if diskUuid in cmd.sharedBlockUuids:
                    self.vgs_path_and_wwid[cmd.vgUuid][p] = diskUuid

        allDiskPaths = allDiskPaths.union(diskPaths)
        allDisks = allDisks.union(disks)

        try:
            root_disks = ["%s[0-9]*" % d for d in linux.get_physical_disk()]
            allDiskPaths = allDiskPaths.union(root_disks)
        except Exception as e:
            logger.warn("get exception: %s" % e.message)
            allDiskPaths.add("/dev/sd*")
            allDiskPaths.add("/dev/vd*")

        def config_lvm(host_id, enableLvmetad=False):
            lvm.backup_lvm_config()
            lvm.reset_lvm_conf_default()
            lvm.config_lvm_by_sed("use_lvmlockd", "use_lvmlockd=1", ["lvm.conf", "lvmlocal.conf"])
            if enableLvmetad:
                lvm.config_lvm_by_sed("use_lvmetad", "use_lvmetad=1", ["lvm.conf", "lvmlocal.conf"])
            else:
                lvm.config_lvm_by_sed("use_lvmetad", "use_lvmetad=0", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("host_id", "host_id=%s" % host_id, ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("sanlock_lv_extend", "sanlock_lv_extend=%s" % DEFAULT_SANLOCK_LV_SIZE, ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("lvmlockd_lock_retries", "lvmlockd_lock_retries=6", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("issue_discards", "issue_discards=1", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("reserved_stack", "reserved_stack=256", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("reserved_memory", "reserved_memory=131072", ["lvm.conf", "lvmlocal.conf"])
            if kvmagent.get_host_os_type() == "debian":
                lvm.config_lvm_by_sed("udev_rules", "udev_rules=0", ["lvm.conf", "lvmlocal.conf"])
                lvm.config_lvm_by_sed("udev_sync", "udev_sync=0", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_filter(["lvm.conf", "lvmlocal.conf"], preserve_disks=allDiskPaths)

            lvm.modify_sanlock_config("sh_retries", 20)
            lvm.modify_sanlock_config("logfile_priority", 7)
            lvm.modify_sanlock_config("renewal_read_extend_sec", 24)
            lvm.modify_sanlock_config("debug_renew", 1)
            lvm.modify_sanlock_config("use_watchdog", 0)
            lvm.modify_sanlock_config("zstack_vglock_timeout", 0)
            lvm.modify_sanlock_config("use_zstack_vglock_timeout", 0)
            lvm.modify_sanlock_config("zstack_vglock_large_delay", 8)
            lvm.modify_sanlock_config("use_zstack_vglock_large_delay", 0)

            sanlock_hostname = "%s-%s-%s" % (cmd.vgUuid[:8], cmd.hostUuid[:8], linux.get_hostname()[:20])
            lvm.modify_sanlock_config("our_host_name", sanlock_hostname)
            shell.call("sed -i 's/.*rotate .*/rotate 10/g' /etc/logrotate.d/sanlock", exception=False)
            shell.call("sed -i 's/.*size .*/size 20M/g' /etc/logrotate.d/sanlock", exception=False)

        config_lvm(cmd.hostId, cmd.enableLvmetad)

        lvm.start_lvmlockd(cmd.ioTimeout)
        logger.debug("find/create vg %s lock..." % cmd.vgUuid)
        rsp.isFirst = self.create_vg_if_not_found(cmd.vgUuid, disks, cmd.hostUuid, allDisks, cmd.forceWipe)

#       sanlock table:
#       
#       | sanlock patch version | delta lease sleep time | retry times |
#       | --------------------- | ---------------------- | ----------- |
#       | 1                     | 40 seconds             | 15          |
#       | 2 or higher           | 0 second               | 3           |
#       
#       
#       explain:
#       
#       In sanlock patch version 1, when you start a vg lock, it takes around 40 seconds
#       in delta lease. So 15 retry times are required to check if vg lockspace exists.
#       
#       In sanlock patch version 2, the sleep time in delta lease can be defined by zstack
#       utility in sanlock.conf. It's 0 second by default, so retry times can be reduced to
#       3 in order to save time.

        @bash.in_bash
        def get_retry_times_for_checking_vg_lockspace():
            r, sanlock_patch_version = bash.bash_ro("sanlock get_patch_version")
            # if version is not a digit, e.g. "client action get_patch_version is unknown", it also means that sanlock patch version < 2
            if sanlock_patch_version.strip().isdigit() is False:
                return 15
            elif int(sanlock_patch_version.strip()) >= 2:
                return 3
            else:
                return 15

        retry_times_for_checking_vg_lockspace = get_retry_times_for_checking_vg_lockspace()

        lvm.check_stuck_vglk()
        logger.debug("starting vg %s lock..." % cmd.vgUuid)
        lvm.start_vg_lock(cmd.vgUuid, retry_times_for_checking_vg_lockspace)

        if lvm.lvm_vgck(cmd.vgUuid, 60)[0] is False and lvm.lvm_check_operation(cmd.vgUuid) is False:
            lvm.drop_vg_lock(cmd.vgUuid)
            logger.debug("restarting vg %s lock..." % cmd.vgUuid)
            lvm.start_vg_lock(cmd.vgUuid, retry_times_for_checking_vg_lockspace)

        # lvm.clean_vg_exists_host_tags(cmd.vgUuid, cmd.hostUuid, HEARTBEAT_TAG)
        # lvm.add_vg_tag(cmd.vgUuid, "%s::%s::%s::%s" % (HEARTBEAT_TAG, cmd.hostUuid, time.time(), linux.get_hostname()))
        self.clear_stalled_qmp_socket()

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.hostId = lvm.get_running_host_id(cmd.vgUuid)
        rsp.vgLvmUuid = lvm.get_vg_lvm_uuid(cmd.vgUuid)
        rsp.hostUuid = cmd.hostUuid
        rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
        return jsonobject.dumps(rsp)

    @staticmethod
    @bash.in_bash
    def clear_stalled_qmp_socket():
        def get_used_qmp_file():
            t = bash.bash_o("ps aux | grep -Eo -- '-qmp unix:%s/\w*\.sock'" % QMP_SOCKET_PATH).splitlines()
            qmp = []
            for i in t:
                qmp.append(i.split("/")[-1])
            return qmp

        exists_qmp_files = set(linux.listdir(QMP_SOCKET_PATH))
        if len(exists_qmp_files) == 0:
            return

        running_qmp_files = set(get_used_qmp_file())
        if len(running_qmp_files) == 0:
            bash.bash_roe("/bin/rm %s/*" % QMP_SOCKET_PATH)
            return

        need_delete_qmp_files = exists_qmp_files.difference(running_qmp_files)
        if len(need_delete_qmp_files) == 0:
            return

        for f in need_delete_qmp_files:
            linux.rm_file_force(os.path.join(QMP_SOCKET_PATH, f))

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def disconnect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        self.vgs_path_and_wwid.pop(cmd.vgUuid)

        @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
        def find_vg(vgUuid):
            cmd = shell.ShellCmd("vgs --nolocking %s -otags | grep %s" % (vgUuid, INIT_TAG))
            cmd(is_exception=False)
            if cmd.return_code == 0:
                return True

            logger.debug("can not find vg %s with tag %s" % (vgUuid, INIT_TAG))
            cmd = shell.ShellCmd("vgs --nolocking %s" % vgUuid)
            cmd(is_exception=False)
            if cmd.return_code == 0:
                logger.warn("found vg %s without tag %s" % (vgUuid, INIT_TAG))
                return True

            raise RetryException("can not find vg %s with or without tag %s" % (vgUuid, INIT_TAG))

        try:
            find_vg(cmd.vgUuid)
        except RetryException:
            logger.debug("can not find vg %s; return success" % cmd.vgUuid)
            return jsonobject.dumps(rsp)
        except Exception as e:
            raise e

        @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
        def deactive_lvs_on_vg(vgUuid):
            active_lvs = lvm.list_local_active_lvs(vgUuid)
            if len(active_lvs) == 0:
                return
            logger.warn("active lvs %s will be deactivate" % active_lvs)
            lvm.deactive_lv(vgUuid)
            active_lvs = lvm.list_local_active_lvs(vgUuid)
            if len(active_lvs) != 0:
                raise RetryException("lvs [%s] still active, retry deactive again" % active_lvs)

        def _do_detach_disks(devnames):
            for name in devnames:
                logger.info("flushing disk: %s" % name)
                shell.run('blockdev --flushbufs %s' % os.path.join("/dev", name))
                linux.write_file("/sys/block/%s/device/delete" % name, "1")

        # c.f.: https://access.redhat.com/solutions/3941
        def detach_physical_disks(vgUuid):
            pvs = lvm.list_pvs(vgUuid)
            if pvs is None:
                raise Exception("list PV failed for VG %s" + vgUuid)

            for pv in pvs:
                bname = os.path.basename(pv)
                if os.path.basename(pv).startswith('mpath'):
                    slaves = linux.listdir('/sys/class/block/%s/slaves' % os.path.basename(os.path.realpath(pv)))
                    logger.info("flushing multipath: %s" % pv)
                    bash.bash_r("multipath -f %s" % pv)
                    _do_detach_disks(slaves)
                elif pv.startswith('/dev/sd'):
                    _do_detach_disks([bname])


        deactive_lvs_on_vg(cmd.vgUuid)
        lvm.clean_vg_exists_host_tags(cmd.vgUuid, cmd.hostUuid, HEARTBEAT_TAG)
        lvm.stop_vg_lock(cmd.vgUuid)
        if cmd.stopServices:
            lvm.quitLockServices()
        lvm.clean_lvm_archive_files(cmd.vgUuid)
        detach_physical_disks(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def add_disk(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        disk = CheckDisk(cmd.diskUuid)

        allDiskPaths = set()
        allDisks = set()

        for diskUuid in cmd.allSharedBlockUuids:
            _disk = CheckDisk(diskUuid)
            p = _disk.get_path()
            if p is not None:
                allDiskPaths.add(p)
                allDisks.add(_disk)
                if diskUuid == cmd.diskUuid:
                    self.vgs_path_and_wwid[cmd.vgUuid][p] = diskUuid
        allDiskPaths.add(disk.get_path())
        allDisks.add(disk)
        try:
            root_disks = ["%s[0-9]*" % d for d in linux.get_physical_disk()]
            allDiskPaths = allDiskPaths.union(root_disks)
        except Exception as e:
            logger.warn("get exception: %s" % e.message)
            allDiskPaths.add("/dev/sd*")
            allDiskPaths.add("/dev/vd*")

        lvm.config_lvm_filter(["lvm.conf", "lvmlocal.conf"], preserve_disks=allDiskPaths)

        if cmd.onlyGenerateFilter:
            rsp = AgentRsp
            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
            return jsonobject.dumps(rsp)

        command = shell.ShellCmd("vgs --nolocking %s -otags | grep %s" % (cmd.vgUuid, INIT_TAG))
        command(is_exception=False)
        if command.return_code != 0:
            self.create_vg_if_not_found(cmd.vgUuid, {disk}, cmd.hostUuid, allDisks, cmd.forceWipe)
        else:
            if cmd.forceWipe is True:
                lvm.wipe_fs([disk.get_path()], cmd.vgUuid)
            lvm.check_gl_lock()
            lvm.add_pv(cmd.vgUuid, disk.get_path(), DEFAULT_VG_METADATA_SIZE)

        rsp = AgentRsp
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def resize_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        with lvm.RecursiveOperateLv(install_abs_path, shared=False):
            lvm.resize_lv_from_cmd(install_abs_path, cmd.size, cmd)
            fmt = linux.get_img_fmt(install_abs_path)
            if not cmd.live and fmt == 'qcow2':
                shell.call("qemu-img resize %s %s" % (install_abs_path, cmd.size))
            ret = linux.qcow2_virtualsize(install_abs_path)

        rsp = ResizeVolumeRsp()
        rsp.size = ret
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        self.create_volume_with_backing(cmd)
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, False)
        rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_data_volume_with_backing(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateDataVolumeWithBackingRsp()
        rsp.size, rsp.actualSize = self.create_volume_with_backing(cmd)
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, False)
        return jsonobject.dumps(rsp)

    def create_volume_with_backing(self, cmd):
        template_abs_path_cache = translate_absolute_path_from_install_path(cmd.templatePathInCache)
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        qcow2_options = self.calc_qcow2_option(self, cmd.kvmHostAddons, True, cmd.provisioning)

        with lvm.RecursiveOperateLv(template_abs_path_cache, shared=True, skip_deactivate_tags=[IMAGE_TAG]):
            if cmd.virtualSize :
                virtual_size = cmd.virtualSize
            else:
                virtual_size = linux.qcow2_virtualsize(template_abs_path_cache)
            lvm.create_lv_from_cmd(install_abs_path, virtual_size, cmd,
                                   "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), lvmlock=False)
            linux.qcow2_clone_with_option(template_abs_path_cache, install_abs_path, qcow2_options)

        lvm.deactive_lv(install_abs_path)
        return virtual_size, lvm.get_lv_size(install_abs_path)

    @kvmagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if cmd.folder:
            raise Exception("not support this operation")

        self.do_delete_bits(cmd.path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
        return jsonobject.dumps(rsp)

    def do_delete_bits(self, path):
        install_abs_path = translate_absolute_path_from_install_path(path)
        if lvm.has_lv_tag(install_abs_path, IMAGE_TAG):
            logger.info('deleting lv image: ' + install_abs_path)
            lvm.delete_image(install_abs_path, IMAGE_TAG)
        else:
            logger.info('deleting lv volume: ' + install_abs_path)
            lvm.delete_lv(install_abs_path)

    @staticmethod
    def get_total_required_size(abs_path):
        virtual_size = linux.qcow2_virtualsize(abs_path)
        total_size = -1
        if linux.get_img_fmt(abs_path) == "qcow2":
            try:
                total_size = linux.qcow2_measure_required_size(abs_path)
            except Exception as e:
                logger.warn("can not get qcow2 measure size: %s" % e)

        if total_size > virtual_size or total_size == -1:
            total_size = virtual_size

        return total_size

    @staticmethod
    @bash.in_bash
    def compare_qcow2(src, dst):
        logger.debug("comparing qcow2 between %s and %s")
        bash.bash_errorout("time %s %s %s" % (qemu_img.subcmd('compare'), src, dst))
        logger.debug("confirmed qcow2 %s and %s are identical" % (src, dst))

    @kvmagent.replyerror
    def create_template_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateTemplateFromVolumeRsp()
        volume_abs_path = translate_absolute_path_from_install_path(cmd.volumePath)
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        if cmd.sharedVolume:
            lvm.do_active_lv(volume_abs_path, lvm.LvmlockdLockType.SHARE, True)

        with lvm.RecursiveOperateLv(volume_abs_path, shared=cmd.sharedVolume, skip_deactivate_tags=[IMAGE_TAG]):
            if not lvm.lv_exists(install_abs_path):
                total_size = self.get_total_required_size(volume_abs_path)
                lvm.update_pv_allocate_strategy(cmd)
                lvm.create_lv_from_absolute_path(install_abs_path, total_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                t_shell = traceable_shell.get_shell(cmd)
                linux.create_template(volume_abs_path, install_abs_path, shell=t_shell)
                logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))

                if cmd.compareQcow2:
                    self.compare_qcow2(volume_abs_path, install_abs_path)

                rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(install_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_image_cache_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateTemplateFromVolumeRsp()
        volume_abs_path = translate_absolute_path_from_install_path(cmd.volumePath)
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        with lvm.RecursiveOperateLv(volume_abs_path, shared=True, skip_deactivate_tags=[IMAGE_TAG]):
            if not lvm.lv_exists(install_abs_path):
                total_size = self.get_total_required_size(volume_abs_path)
                lvm.update_pv_allocate_strategy(cmd)
                lvm.create_lv_from_absolute_path(install_abs_path, total_size, IMAGE_TAG)
            with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                t_shell = traceable_shell.get_shell(cmd)
                linux.create_template(volume_abs_path, install_abs_path, shell=t_shell)
                logger.debug('successfully created template cache [%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))

                if cmd.compareQcow2:
                    self.compare_qcow2(volume_abs_path, install_abs_path)

                rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(install_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        install_abs_path = translate_absolute_path_from_install_path(cmd.primaryStorageInstallPath)

        def upload():
            if not os.path.exists(cmd.primaryStorageInstallPath):
                raise kvmagent.KvmError('cannot find %s' % cmd.primaryStorageInstallPath)

            linux.scp_upload(cmd.hostname, cmd.sshKey, cmd.primaryStorageInstallPath, cmd.backupStorageInstallPath, cmd.username, cmd.sshPort)

        with lvm.OperateLv(install_abs_path, shared=True):
            upload()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def download_from_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        install_abs_path = translate_absolute_path_from_install_path(cmd.primaryStorageInstallPath)

        self.do_download_from_sftp(cmd, install_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    def do_download_from_sftp(self, cmd, install_abs_path):
        if not lvm.lv_exists(install_abs_path):
            size = linux.sftp_get(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, install_abs_path, cmd.username, cmd.sshPort, True)
            lvm.update_pv_allocate_strategy(cmd)
            lvm.create_lv_from_absolute_path(install_abs_path, size,
                                             "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))

        with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
            linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, install_abs_path, cmd.username, cmd.sshPort, cmd.bandWidth)
        logger.debug('successfully download %s/%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))

        self.do_active_lv(cmd.primaryStorageInstallPath, cmd.lockType, False)

    def cancel_download_from_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.primaryStorageInstallPath)
        shell.run("pkill -9 -f '%s'" % install_abs_path)

        self.do_delete_bits(cmd.primaryStorageInstallPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @completetask
    def download_from_kvmhost(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DownloadBitsFromKvmHostRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.primaryStorageInstallPath)

        # todo: assume agent will not restart, maybe need clean
        last_task = self.load_and_save_task(req, rsp, os.path.exists, install_abs_path)
        if last_task and last_task.agent_pid == os.getpid():
            rsp = self.wait_task_complete(last_task)
            return jsonobject.dumps(rsp)

        self.do_download_from_sftp(cmd, install_abs_path)
        rsp.format = linux.get_img_fmt(install_abs_path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cancel_download_from_kvmhost(self, req):
        return self.cancel_download_from_sftp(req)

    @kvmagent.replyerror
    def upload_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.upload_to_imagestore(cmd, req)

    @kvmagent.replyerror
    def commit_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.commit_to_imagestore(cmd, req)

    @kvmagent.replyerror
    def download_from_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        install_abs_path = translate_absolute_path_from_install_path(cmd.primaryStorageInstallPath)

        def clean():
            lvm.delete_lv(install_abs_path)

        image_info = self.imagestore_client.image_info(cmd.hostname, cmd.backupStorageInstallPath)
        if image_info:
            lvm.update_pv_allocate_strategy(cmd)
            if lvm.create_lv_from_absolute_path(install_abs_path, image_info.size, tag=IMAGE_TAG):
                lvm.delete_lv_meta(install_abs_path)

        self.imagestore_client.download_from_imagestore(None, cmd.hostname, cmd.backupStorageInstallPath,
                                                            cmd.primaryStorageInstallPath, failure_action=clean)
        self.do_active_lv(cmd.primaryStorageInstallPath, cmd.lockType, True)
        rsp = AgentRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()
        snapshot_abs_path = translate_absolute_path_from_install_path(cmd.snapshotInstallPath)
        qcow2_options = self.calc_qcow2_option(self, cmd.kvmHostAddons, True, cmd.provisioning)
        new_volume_path = cmd.installPath
        if new_volume_path is None or new_volume_path == "":
            new_volume_path = "/dev/%s/%s" % (cmd.vgUuid, uuidhelper.uuid())
        else:
            new_volume_path = translate_absolute_path_from_install_path(new_volume_path)

        with lvm.RecursiveOperateLv(snapshot_abs_path, shared=True):
            size = linux.qcow2_virtualsize(snapshot_abs_path)
            pe_ranges = lvm.get_lv_affinity_sorted_pvs(snapshot_abs_path, cmd)
            lvm.create_lv_from_cmd(new_volume_path, size, cmd,
                                             "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), pe_ranges=pe_ranges)
            with lvm.OperateLv(new_volume_path, shared=False, delete_when_exception=True):
                linux.qcow2_clone_with_option(snapshot_abs_path, new_volume_path, qcow2_options)
                size = linux.qcow2_virtualsize(new_volume_path)

        rsp.newVolumeInstallPath = new_volume_path
        rsp.size = size
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def merge_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MergeSnapshotRsp()
        snapshot_abs_path = translate_absolute_path_from_install_path(cmd.snapshotInstallPath)
        workspace_abs_path = translate_absolute_path_from_install_path(cmd.workspaceInstallPath)

        lvm.update_pv_allocate_strategy(cmd)
        with lvm.RecursiveOperateLv(snapshot_abs_path, shared=True):
            virtual_size = linux.qcow2_virtualsize(snapshot_abs_path)
            if not lvm.lv_exists(workspace_abs_path):
                pe_ranges = lvm.get_lv_affinity_sorted_pvs(snapshot_abs_path, cmd)
                lvm.create_lv_from_absolute_path(workspace_abs_path, virtual_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()),
                                                 pe_ranges=pe_ranges)
            with lvm.OperateLv(workspace_abs_path, shared=False, delete_when_exception=True):
                t_shell = traceable_shell.get_shell(cmd)
                linux.create_template(snapshot_abs_path, workspace_abs_path, shell=t_shell)
                rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(workspace_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.actualSize = rsp.size
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def extend_merge_target(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ExtendMergeTargetRsp()
        dst_abs_path = translate_absolute_path_from_install_path(cmd.destPath)

        with lvm.RecursiveOperateLv(dst_abs_path, shared=False):
            measure_size = linux.qcow2_measure_required_size(dst_abs_path)
            current_size = int(lvm.get_lv_size(dst_abs_path))
            if current_size < measure_size:
                lvm.resize_lv_from_cmd(dst_abs_path, measure_size, cmd, extend_thin_by_specified_size=True)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offline_merge_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OfflineMergeSnapshotRsp()
        src_abs_path = translate_absolute_path_from_install_path(cmd.srcPath)
        dst_abs_path = translate_absolute_path_from_install_path(cmd.destPath)

        with lvm.RecursiveOperateLv(dst_abs_path, shared=False):
            try:
                measure_size = linux.qcow2_measure_required_size(dst_abs_path)
            except Exception as e:
                logger.warn("can not get qcow2 measure size: %s" % e)
                measure_size = linux.qcow2_virtualsize(dst_abs_path)

            current_size = int(lvm.get_lv_size(dst_abs_path))
            if not cmd.fullRebase:
                if current_size < measure_size:
                    lvm.resize_lv_from_cmd(dst_abs_path, measure_size, cmd, extend_thin_by_specified_size=True)

                with lvm.RecursiveOperateLv(src_abs_path, shared=True):
                    linux.qcow2_rebase(src_abs_path, dst_abs_path)
            else:
                tmp_abs_path = os.path.join(os.path.dirname(dst_abs_path), 'tmp_%s' % uuidhelper.uuid())
                logger.debug("creating temp lv %s" % tmp_abs_path)
                lv_size = max(measure_size, current_size)
                pe_ranges = lvm.get_lv_affinity_sorted_pvs(dst_abs_path, cmd)
                lvm.create_lv_from_absolute_path(tmp_abs_path, lv_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()),
                                                 pe_ranges=pe_ranges)
                with lvm.OperateLv(tmp_abs_path, shared=False, delete_when_exception=True):
                    linux.create_template(dst_abs_path, tmp_abs_path)
                    lvm.lv_rename(tmp_abs_path, dst_abs_path, overwrite=True)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        if cmd.backingFile:
            qcow2_options = self.calc_qcow2_option(self, cmd.kvmHostAddons, True, cmd.provisioning)
            backing_abs_path = translate_absolute_path_from_install_path(cmd.backingFile)
            with lvm.RecursiveOperateLv(backing_abs_path, shared=True):
                virtual_size = linux.qcow2_virtualsize(backing_abs_path)

                if not lvm.lv_exists(install_abs_path):
                    lvm.create_lv_from_cmd(install_abs_path, virtual_size, cmd,
                                                     "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
                with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                    linux.qcow2_create_with_backing_file_and_option(backing_abs_path, install_abs_path, qcow2_options)
        elif not lvm.lv_exists(install_abs_path):
            lvm.create_lv_from_cmd(install_abs_path, cmd.size, cmd,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            if cmd.volumeFormat != 'raw':
                qcow2_options = self.calc_qcow2_option(self, cmd.kvmHostAddons, False, cmd.provisioning)
                with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                    linux.qcow2_create_with_option(install_abs_path, cmd.size, qcow2_options)
                    linux.qcow2_fill(0, 1048576, install_abs_path)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def convert_image_to_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.primaryStorageInstallPath)
        with lvm.OperateLv(install_abs_path, shared=False):
            lvm.clean_lv_tag(install_abs_path, IMAGE_TAG)
            lvm.add_lv_tag(install_abs_path, "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))

        lvm.delete_lv_meta(install_abs_path)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        install_abs_path = translate_absolute_path_from_install_path(cmd.path)
        rsp.existing = lvm.lv_exists(install_abs_path)
        if cmd.vgUuid is not None and lvm.vg_exists(cmd.vgUuid):
            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, False)
        return jsonobject.dumps(rsp)

    @staticmethod
    def get_temp_lv_path(install_path):
        return "%s_temp" % install_path

    @kvmagent.replyerror
    def convert_volume_format(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConvertVolumeFormatRsp()
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        temp_path = self.get_temp_lv_path(install_abs_path)
        with lvm.RecursiveOperateLv(install_abs_path, shared=False):
            src_format = linux.get_img_fmt(install_abs_path)
            if cmd.dstFormat != src_format:
                lv_size = lvm.get_lv_size(install_abs_path)

                if lvm.lv_exists(temp_path):
                    lvm.delete_lv(temp_path)

                lvm.update_pv_allocate_strategy(cmd)
                lvm.create_lv_from_absolute_path(temp_path, lv_size)
                with lvm.OperateLv(temp_path, shared=False, delete_when_exception=True):
                    shell.call('%s -f %s -O %s %s %s' % (qemu_img.subcmd('convert'),
                                                         src_format, cmd.dstFormat,
                                                         install_abs_path, temp_path))
                    converted_format = linux.get_img_fmt(temp_path)
                    if converted_format != cmd.dstFormat:
                        rsp.success = False
                        rsp.error = "convert volume format failed, dest format %s, actual format %s" % (cmd.dstFormt, converted_format)
                        lvm.delete_lv(temp_path)
                        lvm.delete_lv(install_abs_path)
                    else:
                        lvm.lv_rename(temp_path, install_abs_path, True)

        return jsonobject.dumps(rsp)

    def do_active_lv(self, installPath, lockType, recursive, killProcess=False, raise_exception=False):
        def handle_lv(lockType, fpath):
            if lockType > lvm.LvmlockdLockType.NULL:
                lvm.active_lv_with_check(fpath, lockType == lvm.LvmlockdLockType.SHARE)
            else:
                try:
                    lvm.deactive_lv(fpath)
                except Exception as e:
                    if raise_exception:
                        raise e
                    if not killProcess:
                        return
                    qemus = lvm.find_qemu_for_lv_in_use(fpath)
                    if len(qemus) == 0:
                        return
                    for qemu in qemus:
                        if qemu.state != "running":
                            linux.kill_process(qemu.pid)
                    lvm.deactive_lv(fpath)

        install_abs_path = translate_absolute_path_from_install_path(installPath)
        handle_lv(lockType, install_abs_path)

        if recursive is False or lockType is lvm.LvmlockdLockType.NULL:
            return

        while linux.qcow2_get_backing_file(install_abs_path) != "":
            install_abs_path = linux.qcow2_get_backing_file(install_abs_path)
            if lockType == lvm.LvmlockdLockType.NULL:
                handle_lv(lvm.LvmlockdLockType.NULL, install_abs_path)
            else:
                # activate backing files only in shared mode
                handle_lv(lvm.LvmlockdLockType.SHARE, install_abs_path)

    @kvmagent.replyerror
    def active_lv(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, raise_exception=False)

        try:
            cmd.installPath = cmd.installPath.split('?', 1)[0]
            self.do_active_lv(cmd.installPath, cmd.lockType, cmd.recursive, cmd.killProcess,
                          raise_exception=True)
        except Exception as e:
            lv_in_use = "Logical volume %s in use" % translate_absolute_path_from_install_path(cmd.installPath).replace("/dev/", "")
            if not re.search(lv_in_use, str(e)):
                raise e
            rsp.inUse = True
            rsp.success = False
            rsp.error = lv_in_use

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeSizeRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        with lvm.OperateLv(install_abs_path, shared=True):
            rsp.size = linux.qcow2_virtualsize(install_abs_path)
        rsp.actualSize = lvm.get_lv_size(install_abs_path)
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def migrate_volumes(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        total_size = 0
        migrated_size = 0

        lvm.update_pv_allocate_strategy(cmd)
        for struct in cmd.migrateVolumeStructs:
            target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
            current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)
            with lvm.OperateLv(current_abs_path, shared=True):
                lv_size = int(lvm.get_lv_size(current_abs_path))
                struct.put('lv_size', lv_size)

                if lvm.lv_exists(target_abs_path):
                    if struct.skipIfExisting:
                        struct.put('skip_copy', True)
                        continue
                    target_ps_uuid = get_primary_storage_uuid_from_install_path(struct.targetInstallPath)
                    raise Exception("found %s already exists on ps %s" %
                                    (target_abs_path, target_ps_uuid))
                lvm.create_lv_from_absolute_path(target_abs_path, lv_size,
                                                     "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), exact_size=True)
                lvm.active_lv(target_abs_path, lvm.LvmlockdLockType.SHARE)
                total_size += lv_size

        PFILE = linux.create_temp_file()
        try:
            report = Report.from_spec(cmd, 'MigrateVolumes')
            parent_stage = get_task_stage(cmd, "10-90")

            def _get_progress(synced):
                last = linux.tail_1(PFILE).strip()
                if not last or not last.isdigit():
                    return synced

                report.progress_report(get_exact_percent_from_scale(last, start, end), "report")
                return synced

            for struct in cmd.migrateVolumeStructs:
                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)

                if struct.skip_copy:
                    migrated_size += struct.lv_size
                    continue

                start = get_exact_percent(float(migrated_size) / total_size * 100, parent_stage)
                end = get_exact_percent(float(struct.lv_size + migrated_size) / total_size * 100, parent_stage)

                with lvm.OperateLv(current_abs_path, shared=True):
                    t_bash = traceable_shell.get_shell(cmd)
                    t_bash.bash_progress_1("pv -n %s > %s 2>%s" % (current_abs_path, target_abs_path, PFILE), _get_progress)

                migrated_size += struct.lv_size

            for struct in cmd.migrateVolumeStructs:
                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)
                with lvm.RecursiveOperateLv(current_abs_path, shared=True):
                    previous_ps_uuid = get_primary_storage_uuid_from_install_path(struct.currentInstallPath)
                    target_ps_uuid = get_primary_storage_uuid_from_install_path(struct.targetInstallPath)

                    current_backing_file = linux.qcow2_get_backing_file(current_abs_path)  # type: str
                    target_backing_file = current_backing_file.replace(previous_ps_uuid, target_ps_uuid)

                    if struct.compareQcow2:
                        self.compare_qcow2(current_abs_path, target_abs_path)
                    if current_backing_file is not None and current_backing_file != "":
                        lvm.active_lv(target_backing_file, lvm.LvmlockdLockType.SHARE)
                        logger.debug("rebase %s to %s" % (target_abs_path, target_backing_file))
                        linux.qcow2_rebase_no_check(target_backing_file, target_abs_path)
        except Exception as e:
            for struct in cmd.migrateVolumeStructs:
                if struct.skip_copy:
                    continue

                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                if struct.currentInstallPath == struct.targetInstallPath:
                    logger.debug("current install path %s equals target %s, skip to delete" %
                                 (struct.currentInstallPath, struct.targetInstallPath))
                else:
                    logger.debug("error happened, delete lv %s" % target_abs_path)
                    lvm.delete_lv(target_abs_path, False)
            raise e
        finally:
            for struct in cmd.migrateVolumeStructs:
                if struct.skip_copy:
                    continue

                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                lvm.deactive_lv(target_abs_path)

            linux.rm_file_force(PFILE)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @staticmethod
    def calc_qcow2_option(self, options, has_backing_file, provisioning=None):
        if options is None or options == "" or options.qcow2Options is None or options.qcow2Options == "":
            return " "
        if has_backing_file or provisioning == lvm.VolumeProvisioningStrategy.ThinProvisioning:
            return re.sub("-o preallocation=\w* ", " ", options.qcow2Options)
        return options.qcow2Options

    @kvmagent.replyerror
    def get_block_devices(self, req):
        rsp = GetBlockDevicesRsp()
        rsp.blockDevices = lvm.get_block_devices()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_backing_chain(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetBackingChainRsp()
        abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        with lvm.RecursiveOperateLv(abs_path, shared=True, skip_deactivate_tags=[IMAGE_TAG], delete_when_exception=False):
            rsp.backingChain = linux.qcow2_get_file_chain(abs_path)
            if not cmd.containSelf:
                rsp.backingChain.pop(0)

            rsp.totalSize = 0L
            for path in rsp.backingChain:
                rsp.totalSize += long(lvm.get_lv_size(path))

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def convert_volume_provisioning(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConvertVolumeProvisioningRsp()

        if cmd.provisioningStrategy != "ThinProvisioning":
            raise NotImplementedError

        abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        with lvm.RecursiveOperateLv(abs_path, shared=False):
            image_offest = long(
                bash.bash_o("%s %s | grep 'Image end offset' | awk -F ': ' '{print $2}'" %
                        (qemu_img.subcmd('check'), abs_path)).strip())
            current_size = long(lvm.get_lv_size(abs_path))
            virtual_size = linux.qcow2_virtualsize(abs_path)
            size = image_offest + cmd.addons[lvm.thinProvisioningInitializeSize]
            if size > current_size:
                size = current_size
            if size > virtual_size:
                size = virtual_size
            lvm.resize_lv(abs_path, size, True)

        rsp.actualSize = size
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def config_filter(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        allDiskPaths = set()

        for diskUuid in cmd.allSharedBlockUuids:
            disk = CheckDisk(diskUuid)
            p = disk.get_path()
            if p is not None:
                allDiskPaths.add(p)

        try:
            root_disks = ["%s[0-9]*" % d for d in linux.get_physical_disk()]
            allDiskPaths = allDiskPaths.union(root_disks)
        except Exception as e:
            logger.warn("get exception: %s" % e.message)
            allDiskPaths.add("/dev/sd*")
            allDiskPaths.add("/dev/vd*")

        lvm.config_lvm_filter(["lvm.conf", "lvmlocal.conf"], preserve_disks=allDiskPaths)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_download_bits_from_kvmhost_progress(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetDownloadBitsFromKvmHostProgressRsp()
        totalSize = 0
        for path in cmd.volumePaths:
            install_abs_path = translate_absolute_path_from_install_path(path)
            actualSize = lvm.get_lv_size(install_abs_path)
            totalSize += long(actualSize)
        rsp.totalSize = totalSize
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def shrink_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ShrinkSnapShotRsp()

        size = None
        old_size = None
        abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        with lvm.RecursiveOperateLv(abs_path, shared=False):
            old_size = long(lvm.get_lv_size(abs_path))
            check_result = qemu_img.get_check_result(abs_path)  # type: qemu_img.CheckResult
            if check_result.allocated_clusters is None:
                size = check_result.image_end_offset
                lvm.resize_lv(abs_path, size, True)
            else:
                # if full allocated, do nothing
                if check_result.allocated_clusters != check_result.total_clusters:
                    size = check_result.image_end_offset
                    lvm.resize_lv(abs_path, size, True)

            size = long(lvm.get_lv_size(abs_path))

        rsp.oldSize = old_size
        rsp.size = size
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_qcow2_hashvalue(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetQcow2HashValueRsp()
        abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        rsp.hashValue = secret.get_image_hash(abs_path)
        return jsonobject.dumps(rsp)
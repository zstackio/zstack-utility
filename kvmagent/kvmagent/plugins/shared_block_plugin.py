import os
import os.path
import re
import random
import traceback

from kvmagent import kvmagent
from kvmagent.plugins import volume_secret
from kvmagent.plugins.imagestore import ImageStoreClient
from kvmagent.plugins.ha_plugin import stop_vg_heartbeat
from zstacklib.utils import jsonobject
from zstacklib.utils import shell
from zstacklib.utils import lock
from zstacklib.utils import lvm, sanlock
from zstacklib.utils import list_ops
from zstacklib.utils import bash
from zstacklib.utils import qemu_img, qcow2
from zstacklib.utils import traceable_shell
from zstacklib.utils.lv_metadata import SblkMetadataHandler, sblk_prefix_rebase_backing_files
from zstacklib.utils.report import *
from zstacklib.utils.plugin import completetask
import zstacklib.utils.uuidhelper as uuidhelper
from zstacklib.utils import secret
from zstacklib.utils.misc import IgnoreError

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
LUKS_HEADER_OVERHEAD = 8 * 1024 * 1024
CONNECTED_PREFIX = "sblkConnected"
ZSTACK_RUN_DIR = "/var/run/zstack"


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


class EstimateTemplateSizeRsp(AgentRsp):
    def __init__(self):
        super(EstimateTemplateSizeRsp, self).__init__()
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

class GetBatchVolumeSizeRsp(AgentRsp):
    def __init__(self):
        super(GetBatchVolumeSizeRsp, self).__init__()
        self.actualSizes = {}

class ResizeVolumeRsp(AgentRsp):
    def __init__(self):
        super(ResizeVolumeRsp, self).__init__()
        self.size = None


class ExtendMergeTargetRsp(AgentRsp):
    def __init__(self):
        super(ExtendMergeTargetRsp, self).__init__()
        self.size = None


class ExtendLogicalVolumeRsp(AgentRsp):
    def __init__(self):
        super(ExtendLogicalVolumeRsp, self).__init__()


class OfflineMergeSnapshotRsp(AgentRsp):
    def __init__(self):
        super(OfflineMergeSnapshotRsp, self).__init__()
        self.deleted = False
        self.actualSize = None


class OfflineCommitSnapshotRsp(AgentRsp):
    def __init__(self):
        super(OfflineCommitSnapshotRsp, self).__init__()
        self.actualSize = None


class ConvertVolumeFormatRsp(AgentRsp):
    def __init__(self):
        super(ConvertVolumeFormatRsp, self).__init__()
        self.size = None


class ConvertVolumeEncryptionRsp(AgentRsp):
    def __init__(self):
        super(ConvertVolumeEncryptionRsp, self).__init__()
        self.actualSizes = {}


class RetryException(Exception):
    pass


class SharedBlockConnectException(Exception):
    pass


class WriteVmMetadataRsp(AgentRsp):
    def __init__(self):
        super(WriteVmMetadataRsp, self).__init__()


class ScanVmMetadataRsp(AgentRsp):
    def __init__(self):
        super(ScanVmMetadataRsp, self).__init__()
        self.metadataEntries = []


class CleanupVmMetadataRsp(AgentRsp):
    def __init__(self):
        super(CleanupVmMetadataRsp, self).__init__()


class CleanupAllVmMetadataRsp(AgentRsp):
    def __init__(self):
        super(CleanupAllVmMetadataRsp, self).__init__()
        self.skipped = False
        self.currentGeneration = None


class GetVmInstanceMetadataRsp(AgentRsp):
    def __init__(self):
        super(GetVmInstanceMetadataRsp, self).__init__()
        self.metadata = None


class PrefixRebaseBackingFilesRsp(AgentRsp):
    def __init__(self):
        super(PrefixRebaseBackingFilesRsp, self).__init__()
        self.rebasedCount = 0


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
    def __init__(self):
        self.volumeUuid = None  # type: str
        self.snapshotUuid = None  # type: str
        self.currentInstallPath = None  # type: str
        self.targetInstallPath = None  # type: str
        self.safeMode = False
        self.compareQcow2 = True
        self.skip_copy = False
        self.independent = False
        self.exists_lock = None


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


class CreateEmptyVolumeRsp(AgentRsp):
    def __init__(self):
        super(CreateEmptyVolumeRsp, self).__init__()
        self.actualSize = None
        self.size = None


class CreateVolumeFromCacheRsp(AgentRsp):
    def __init__(self):
        super(CreateVolumeFromCacheRsp, self).__init__()
        self.actualSize = None
        self.size = None


class TakeoverRsp(AgentRsp):
    def __init__(self):
        super(TakeoverRsp, self).__init__()


class GetVgsInfoRsp(AgentRsp):
    def __init__(self):
        super(GetVgsInfoRsp, self).__init__()
        self.groupDiskInfos = {}


class GetManagedVgsInfoRsp(AgentRsp):
    def __init__(self):
        super(GetManagedVgsInfoRsp, self).__init__()
        self.groupDiskInfos = {}


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
            lvm.check_stuck_vglk_and_gllk()
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


class CommitToImageStoreCmd(kvmagent.AgentCommand):
    @log.sensitive_fields("addons.ImageStoreEncryption.encryptedDek")
    def __init__(self):
        super(CommitToImageStoreCmd, self).__init__()


class SharedBlockPlugin(kvmagent.KvmAgent):

    PING_PATH = "/sharedblock/ping"
    CONNECT_PATH = "/sharedblock/connect"
    DISCONNECT_PATH = "/sharedblock/disconnect"
    CREATE_VOLUME_FROM_CACHE_PATH = "/sharedblock/createrootvolume"
    DELETE_BITS_PATH = "/sharedblock/bits/delete"
    CREATE_TEMPLATE_FROM_VOLUME_PATH = "/sharedblock/createtemplatefromvolume"
    ESTIMATE_TEMPLATE_SIZE_PATH = "/sharedblock/estimatetemplatesize"
    CREATE_IMAGE_CACHE_FROM_VOLUME_PATH = "/sharedblock/createimagecachefromvolume"
    UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH = "/sharedblock/sftp/upload"
    DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH = "/sharedblock/sftp/download"
    UPLOAD_BITS_TO_IMAGESTORE_PATH = "/sharedblock/imagestore/upload"
    COMMIT_BITS_TO_IMAGESTORE_PATH = "/sharedblock/imagestore/commit"
    DOWNLOAD_BITS_FROM_IMAGESTORE_PATH = "/sharedblock/imagestore/download"
    CLEAN_LV_META = "/sharedblock/lv/meta/clean"
    REVERT_VOLUME_FROM_SNAPSHOT_PATH = "/sharedblock/volume/revertfromsnapshot"
    MERGE_SNAPSHOT_PATH = "/sharedblock/snapshot/merge"
    EXTEND_MERGE_TARGET_PATH = "/sharedblock/snapshot/extendmergetarget"
    EXTEND_LOGICAL_VOLUME_PATH = "/sharedblock/logicalvolume/extend"
    OFFLINE_MERGE_SNAPSHOT_PATH = "/sharedblock/snapshot/offlinemerge"
    OFFLINE_COMMIT_SNAPSHOT_PATH = "/sharedblock/snapshot/offlinecommit"
    CREATE_EMPTY_VOLUME_PATH = "/sharedblock/volume/createempty"
    CREATE_DATA_VOLUME_WITH_BACKING_PATH = "/sharedblock/volume/createwithbacking"
    CHECK_BITS_PATH = "/sharedblock/bits/check"
    RESIZE_VOLUME_PATH = "/sharedblock/volume/resize"
    CONVERT_IMAGE_TO_VOLUME = "/sharedblock/image/tovolume"
    CHANGE_VOLUME_ACTIVE_PATH = "/sharedblock/volume/active"
    GET_VOLUME_SIZE_PATH = "/sharedblock/volume/getsize"
    BATCH_GET_VOLUME_SIZE_PATH = "/sharedblock/volume/batchgetsize"
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
    CHECK_STATE_PATH = "/sharedblock/vgstate/check"
    TAKEOVER_PATH = "/sharedblock/takeover"
    VGS_ALL_PATH = "/sharedblock/vgs/all"
    VGS_MANAGED_PATH = "/sharedblock/vgs/managed"
    WRITE_VM_METADATA_PATH = "/sharedblock/vm/metadata/write"
    GET_VM_INSTANCE_METADATA_PATH = "/sharedblock/vm/metadata/get"
    SCAN_VM_METADATA_PATH = "/sharedblock/vm/metadata/scan"
    CLEANUP_VM_METADATA_PATH = "/sharedblock/vm/metadata/cleanup"
    CLEANUP_ALL_VM_METADATA_PATH = "/sharedblock/vm/metadata/cleanupall"
    PREFIX_REBASE_BACKING_FILES_PATH = "/sharedblock/snapshot/prefixrebasebackingfiles"
    ENCRYPT_VOLUME_BITS_PATH = "/sharedblock/volume/encryptinplace"
    CONVERT_VOLUME_ENCRYPTION_PATH = "/sharedblock/volume/convertencryption"

    _metadata_handler = SblkMetadataHandler(lvm, bash)

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
        http_server.register_async_uri(self.ESTIMATE_TEMPLATE_SIZE_PATH, self.estimate_template)
        http_server.register_async_uri(self.CREATE_IMAGE_CACHE_FROM_VOLUME_PATH, self.create_image_cache_from_volume)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH, self.upload_to_sftp)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH, self.download_from_sftp)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_IMAGESTORE_PATH, self.upload_to_imagestore)
        http_server.register_async_uri(self.COMMIT_BITS_TO_IMAGESTORE_PATH, self.commit_to_imagestore,
                                       cmd=CommitToImageStoreCmd())
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_IMAGESTORE_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.CLEAN_LV_META, self.clean_lv_meta)
        http_server.register_async_uri(self.REVERT_VOLUME_FROM_SNAPSHOT_PATH, self.revert_volume_from_snapshot)
        http_server.register_async_uri(self.MERGE_SNAPSHOT_PATH, self.merge_snapshot)
        http_server.register_async_uri(self.EXTEND_MERGE_TARGET_PATH, self.extend_merge_target)
        http_server.register_async_uri(self.EXTEND_LOGICAL_VOLUME_PATH, self.extend_logical_volume)
        http_server.register_async_uri(self.OFFLINE_MERGE_SNAPSHOT_PATH, self.offline_merge_snapshots)
        http_server.register_async_uri(self.OFFLINE_COMMIT_SNAPSHOT_PATH, self.offline_commit_snapshots)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.create_empty_volume)
        http_server.register_async_uri(self.CONVERT_IMAGE_TO_VOLUME, self.convert_image_to_volume)
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize_volume)
        http_server.register_async_uri(self.CHANGE_VOLUME_ACTIVE_PATH, self.active_lv)
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        http_server.register_async_uri(self.BATCH_GET_VOLUME_SIZE_PATH, self.batch_get_volume_size)
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
        http_server.register_async_uri(self.CHECK_STATE_PATH, self.check_vg_state)
        http_server.register_async_uri(self.TAKEOVER_PATH, self.takeover)
        http_server.register_async_uri(self.VGS_ALL_PATH, self.vgs_all_info)
        http_server.register_async_uri(self.VGS_MANAGED_PATH, self.vgs_managed_info)
        http_server.register_async_uri(self.WRITE_VM_METADATA_PATH, self.write_vm_metadata)
        http_server.register_async_uri(self.SCAN_VM_METADATA_PATH, self.scan_vm_metadata)
        http_server.register_async_uri(self.CLEANUP_VM_METADATA_PATH, self.cleanup_vm_metadata)
        http_server.register_async_uri(self.CLEANUP_ALL_VM_METADATA_PATH, self.cleanup_all_vm_metadata)
        http_server.register_async_uri(self.GET_VM_INSTANCE_METADATA_PATH, self.get_vm_instance_metadata)
        http_server.register_async_uri(self.PREFIX_REBASE_BACKING_FILES_PATH, self.prefix_rebase_backing_files)
        http_server.register_async_uri(self.ENCRYPT_VOLUME_BITS_PATH, self.encrypt_volume_bits)
        http_server.register_async_uri(self.CONVERT_VOLUME_ENCRYPTION_PATH, self.convert_volume_encryption)

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

    def create_vg_if_not_found(self, vgUuid, disks, hostUuid, allDisks, forceWipe=False, is_first_create_vg=False):
        # type: (str, set([CheckDisk]), str, set([CheckDisk]), bool) -> bool
        @linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
        def find_vg(vgUuid, raise_exception=True):
            cmd = shell.ShellCmd("timeout 5 vgscan --ignorelockingfailure; vgs --nolocking -t %s -otags | grep %s" % (vgUuid, INIT_TAG))
            cmd(is_exception=False)
            if cmd.return_code != 0 and raise_exception:
                raise RetryException("can not find vg %s with tag %s" % (vgUuid, INIT_TAG))
            elif cmd.return_code != 0:
                return False
            return True

        @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
        def create_vg(hostUuid, vgUuid, diskPaths, raise_exception=True):
            if not is_first_create_vg:
                raise Exception("vg %s has already been created before, and there may be a risk of data loss during "
                                "secondary creation. Please check your storage" % vgUuid)
            cmd = shell.ShellCmd("vgcreate -qq --shared --addtag '%s::%s::%s::%s' --metadatasize %s %s %s" %
                                 (INIT_TAG, hostUuid, time.time(), linux.get_hostname(),
                                  DEFAULT_VG_METADATA_SIZE, vgUuid, " ".join(diskPaths)))
            cmd(is_exception=False)
            logger.debug("created vg %s, ret: %s, stdout: %s, stderr: %s" %
                         (vgUuid, cmd.return_code, cmd.stdout, cmd.stderr))
            if cmd.return_code != 0 and raise_exception:
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
        if size_cache is not None and linux.get_current_timestamp() - size_cache['currentTimestamp'] < 60:
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

        ## lvm.refresh_lv_uuid_cache_if_need()
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

    def connected(self, vgUuid):
        linux.touch_file(os.path.join(ZSTACK_RUN_DIR, "%s.%s" % (CONNECTED_PREFIX, vgUuid)))

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
            p = disk.get_path(raise_exception=False)
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

        lvm.config_lvm(cmd.hostId, allDiskPaths, cmd.vgUuid, cmd.hostUuid, DEFAULT_SANLOCK_LV_SIZE,
                       kvmagent.get_host_os_type(), cmd.enableLvmetad)

        lvm.start_lock_service(cmd.ioTimeout)
        logger.debug("find/create vg %s lock..." % cmd.vgUuid)
        rsp.isFirst = self.create_vg_if_not_found(cmd.vgUuid, disks, cmd.hostUuid, allDisks, cmd.forceWipe, cmd.isFirst)

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

        retry_times_for_checking_vg_lockspace = lvm.get_retry_times_for_checking_vg_lockspace()

        lvm.check_stuck_vglk_and_gllk()
        running_lockspace = sanlock.get_lockspace(cmd.vgUuid)
        if not running_lockspace:
            logger.info("connect: remove stale device maps for %s before lock start" % cmd.vgUuid)
            lvm.remove_device_map_for_vg(cmd.vgUuid)
        else:
            logger.info("connect: skip stale device map cleanup for %s, active lockspace exists: %s" %
                        (cmd.vgUuid, running_lockspace))
        logger.debug("starting vg %s lock..." % cmd.vgUuid)
        try:
            lvm.start_vg_lock(cmd.vgUuid, cmd.hostId, retry_times_for_checking_vg_lockspace)
        except Exception:
            lvm.log_vg_lock_diagnostics(cmd.vgUuid, "after connect lock start failure", warn=True)
            raise

        if lvm.lvm_vgck(cmd.vgUuid, 60)[0] is False and lvm.lvm_check_operation(cmd.vgUuid) is False:
            lvm.drop_vg_lock(cmd.vgUuid)
            logger.debug("restarting vg %s lock..." % cmd.vgUuid)
            lvm.start_vg_lock(cmd.vgUuid, cmd.hostId, retry_times_for_checking_vg_lockspace)

        # lvm.clean_vg_exists_host_tags(cmd.vgUuid, cmd.hostUuid, HEARTBEAT_TAG)
        # lvm.add_vg_tag(cmd.vgUuid, "%s::%s::%s::%s" % (HEARTBEAT_TAG, cmd.hostUuid, time.time(), linux.get_hostname()))
        self.clear_stalled_qmp_socket()
        lvm.check_missing_pv(cmd.vgUuid)
        lvm.update_lockspace_io_timeout_if_need(cmd.vgUuid, cmd.ioTimeout)

        self.connected(cmd.vgUuid)
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
        if cmd.vgUuid in self.vgs_path_and_wwid.keys():
            self.vgs_path_and_wwid.pop(cmd.vgUuid)

        @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
        def find_vg(vgUuid):
            cmd = shell.ShellCmd("vgs --nolocking -t %s -otags | grep %s" % (vgUuid, INIT_TAG))
            cmd(is_exception=False)
            if cmd.return_code == 0:
                return True

            logger.debug("can not find vg %s with tag %s" % (vgUuid, INIT_TAG))
            cmd = shell.ShellCmd("vgs --nolocking -t %s" % vgUuid)
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


        stop_vg_heartbeat(cmd.vgUuid)
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
            p = _disk.get_path(raise_exception=False)
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
            rsp = AgentRsp()
            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
            return jsonobject.dumps(rsp)

        command = shell.ShellCmd("vgs --nolocking -t %s -otags | grep %s" % (cmd.vgUuid, INIT_TAG))
        command(is_exception=False)
        if command.return_code != 0:
            self.create_vg_if_not_found(cmd.vgUuid, {disk}, cmd.hostUuid, allDisks, cmd.forceWipe)
        else:
            if cmd.forceWipe is True:
                lvm.wipe_fs([disk.get_path()], cmd.vgUuid)
            lvm.check_gl_lock()
            lvm.add_pv(cmd.vgUuid, disk.get_path(), DEFAULT_VG_METADATA_SIZE)

        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def resize_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        secret_material_file = getattr(cmd, 'encryptLuksSecretMaterialFilePath', None)
        encrypted = bool(getattr(cmd, 'encrypted', False) or secret_material_file)
        lv_size = int(cmd.size) + LUKS_HEADER_OVERHEAD if encrypted else cmd.size

        with lvm.RecursiveOperateLv(install_abs_path, shared=False):
            if cmd.force:
                lvm.resize_lv(install_abs_path, lv_size, True)
            else:
                lvm.extend_lv_from_cmd(install_abs_path, lv_size, cmd)
            fmt = linux.get_img_fmt(install_abs_path)
            if not cmd.live and fmt == 'qcow2':
                if secret_material_file:
                    linux.qemu_img_resize_with_secret(install_abs_path, cmd.size, secret_material_file,
                                                      cmd.force, skip_if_sufficient=True)
                elif encrypted:
                    raise Exception("encrypted shared block volume resize requires LUKS secret material file")
                else:
                    linux.qemu_img_resize(install_abs_path, cmd.size, 'qcow2', cmd.force, skip_if_sufficient=True)
            ret = cmd.size if cmd.live and encrypted else (
                linux.qcow2_get_virtual_size(install_abs_path) if encrypted else linux.qcow2_virtualsize(install_abs_path))

        rsp = ResizeVolumeRsp()
        rsp.size = ret
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVolumeFromCacheRsp()
        rsp.size, rsp.actualSize = self.create_volume_with_backing(cmd)
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
        encrypted_dek = getattr(cmd, 'encryptedDek', None)

        with lvm.RecursiveOperateLv(template_abs_path_cache, shared=True, skip_deactivate_tags=[IMAGE_TAG]):
            if cmd.virtualSize:
                virtual_size = cmd.virtualSize
            else:
                virtual_size = linux.qcow2_virtualsize(template_abs_path_cache)
            lvm.create_lv_from_cmd(install_abs_path, virtual_size, cmd,
                                   "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), lvmlock=False)
            size = cmd.virtualSize if cmd.virtualSize else virtual_size
            if encrypted_dek:
                with volume_secret.luks_secret_channel(encrypted_dek) as secret_material_file:
                    lvm.extend_lv(install_abs_path, int(virtual_size) + LUKS_HEADER_OVERHEAD,
                                  skip_if_sufficient=True)
                    linux.qcow2_clone_encrypted(template_abs_path_cache, install_abs_path,
                                                secret_material_file, size=size, opt=qcow2_options)
            else:
                linux.qcow2_clone_with_option(template_abs_path_cache, install_abs_path, qcow2_options, size)

        virtual_size = linux.qcow2_get_virtual_size(install_abs_path)
        lvm.deactive_lv(install_abs_path)
        return virtual_size, lvm.get_lv_size(install_abs_path)

    @kvmagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if cmd.folder:
            raise Exception("not support this operation")

        try:
            deadline = get_deadline(cmd)
        except Exception as e:
            logger.warn("skip discard deadline for deleting bits because %s" % str(e))
            deadline = 0

        self.do_delete_bits(cmd.path, discard=cmd.issueDiscards, deadline=deadline)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
        return jsonobject.dumps(rsp)

    def do_delete_bits(self, path, discard=lvm.LvDiscardStrategy.NEVER, deadline=None):
        install_abs_path = translate_absolute_path_from_install_path(path)
        if lvm.has_lv_tag(install_abs_path, IMAGE_TAG):
            logger.info('deleting lv image: ' + install_abs_path)
            lvm.delete_image(install_abs_path, IMAGE_TAG)
        else:
            logger.info('deleting lv volume: ' + install_abs_path)
            lvm.discard_lv(install_abs_path, discard, deadline=deadline)
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
    def get_convert_volume_encryption_lv_size(source_abs_path, target_encrypted, target_backing_abs_path):
        lv_size = int(lvm.get_lv_size(source_abs_path))
        if not target_backing_abs_path:
            lv_size = max(lv_size, SharedBlockPlugin.get_total_required_size(source_abs_path))
        if target_encrypted:
            lv_size += LUKS_HEADER_OVERHEAD
        return lv_size

    @staticmethod
    @bash.in_bash
    def compare_qcow2(src, dst):
        logger.debug("comparing qcow2 between %s and %s" % (src, dst))
        bash.bash_errorout("time %s %s %s" % (qemu_img.subcmd('compare'), src, dst))
        logger.debug("confirmed qcow2 %s and %s are identical" % (src, dst))

    @kvmagent.replyerror
    def create_template_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateTemplateFromVolumeRsp()
        volume_abs_path = translate_absolute_path_from_install_path(cmd.volumePath)
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        encrypted_dek = getattr(cmd, 'encryptedDek', None)

        if cmd.sharedVolume:
            lvm.do_active_lv(volume_abs_path, lvm.LvmlockdLockType.SHARE, True)

        with lvm.RecursiveOperateLv(volume_abs_path, shared=cmd.sharedVolume, skip_deactivate_tags=[IMAGE_TAG]):
            if not lvm.lv_exists(install_abs_path):
                total_size = self.get_total_required_size(volume_abs_path)
                if encrypted_dek:
                    total_size += LUKS_HEADER_OVERHEAD
                lvm.update_pv_allocate_strategy(cmd)
                lvm.create_lv_from_absolute_path(install_abs_path, total_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                t_shell = traceable_shell.get_shell(cmd)
                if encrypted_dek:
                    with volume_secret.luks_secret_channel(encrypted_dek) as secret_file:
                        linux.create_encrypted_template_with_secret(
                            volume_abs_path, install_abs_path, secret_file, shell=t_shell)
                else:
                    linux.create_template(volume_abs_path, install_abs_path, shell=t_shell)
                logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))

                if cmd.compareQcow2:
                    self.compare_qcow2(volume_abs_path, install_abs_path)

                rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(install_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def estimate_template(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = EstimateTemplateSizeRsp()
        volume_abs_path = translate_absolute_path_from_install_path(cmd.volumePath)

        with lvm.RecursiveOperateLv(volume_abs_path, shared=True, skip_deactivate_tags=[IMAGE_TAG]):
            rsp.actualSize = linux.qcow2_measure_required_size(volume_abs_path)
            rsp.size, _ = linux.qcow2_size_and_actual_size(volume_abs_path)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_image_cache_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateTemplateFromVolumeRsp()
        volume_abs_path = translate_absolute_path_from_install_path(cmd.volumePath)
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        encrypted_dek = getattr(cmd, 'encryptedDek', None)

        with lvm.RecursiveOperateLv(volume_abs_path, shared=True, skip_deactivate_tags=[IMAGE_TAG]):
            if not lvm.lv_exists(install_abs_path):
                total_size = self.get_total_required_size(volume_abs_path)
                if encrypted_dek:
                    total_size += LUKS_HEADER_OVERHEAD
                lvm.update_pv_allocate_strategy(cmd)
                lvm.create_lv_from_absolute_path(install_abs_path, total_size, IMAGE_TAG)
            with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                t_shell = traceable_shell.get_shell(cmd)
                if encrypted_dek:
                    with volume_secret.luks_secret_channel(encrypted_dek) as secret_file:
                        linux.create_encrypted_template_with_secret(
                            volume_abs_path, install_abs_path, secret_file, shell=t_shell)
                else:
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
            if not os.path.exists(install_abs_path):
                raise kvmagent.KvmError('cannot find %s' % install_abs_path)

            linux.scp_upload(cmd.hostname, cmd.sshKey, install_abs_path, cmd.backupStorageInstallPath, cmd.username, cmd.sshPort)

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
            size = linux.sftp_get(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, install_abs_path, sshPort=cmd.sshPort, get_size=True)
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
            lvm.delete_lv(install_abs_path, raise_exception=False)

        image_info = self.imagestore_client.image_info(cmd.hostname, cmd.backupStorageInstallPath)
        if image_info:
            lvm.update_pv_allocate_strategy(cmd)
            if lvm.create_lv_from_absolute_path(install_abs_path, image_info.size, tag=IMAGE_TAG):
                lvm.delete_lv_meta(install_abs_path)

        self.imagestore_client.download_from_imagestore(None, cmd.hostname, cmd.backupStorageInstallPath,
                                                        cmd.primaryStorageInstallPath, cmd.concurrency,
                                                        failure_action=clean)
        self.do_active_lv(cmd.primaryStorageInstallPath, cmd.lockType, True)
        rsp = AgentRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def clean_lv_meta(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        install_abs_path = translate_absolute_path_from_install_path(cmd.primaryStorageInstallPath)
        lvm.delete_lv_meta(install_abs_path)

        rsp = AgentRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()
        snapshot_abs_path = translate_absolute_path_from_install_path(cmd.snapshotInstallPath)
        qcow2_options = self.calc_qcow2_option(self, cmd.kvmHostAddons, True, cmd.provisioning)
        secret_material_file = getattr(cmd, 'encryptLuksSecretMaterialFilePath', None)
        new_volume_path = cmd.installPath
        if new_volume_path is None or new_volume_path == "":
            new_volume_path = "/dev/%s/%s" % (cmd.vgUuid, uuidhelper.uuid())
        else:
            new_volume_path = translate_absolute_path_from_install_path(new_volume_path)

        with lvm.RecursiveOperateLv(snapshot_abs_path, shared=True):
            size = linux.qcow2_virtualsize(snapshot_abs_path)
            lv_size = int(size) + LUKS_HEADER_OVERHEAD if secret_material_file else size
            pe_ranges = lvm.get_lv_affinity_sorted_pvs(snapshot_abs_path, cmd)
            lvm.create_lv_from_cmd(new_volume_path, lv_size, cmd,
                                             "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), pe_ranges=pe_ranges)
            with lvm.OperateLv(new_volume_path, shared=False, delete_when_exception=True):
                if secret_material_file:
                    linux.qcow2_clone_encrypted(snapshot_abs_path, new_volume_path,
                                                secret_material_file, size=size, opt=qcow2_options)
                else:
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
        secret_material_file = getattr(cmd, 'encryptLuksSecretMaterialFilePath', None)

        lvm.update_pv_allocate_strategy(cmd)
        with lvm.RecursiveOperateLv(snapshot_abs_path, shared=True):
            virtual_size = linux.qcow2_virtualsize(snapshot_abs_path)
            lv_size = max(self.get_total_required_size(snapshot_abs_path), int(lvm.get_lv_size(snapshot_abs_path)))
            if secret_material_file:
                lv_size += LUKS_HEADER_OVERHEAD
            if not lvm.lv_exists(workspace_abs_path):
                pe_ranges = lvm.get_lv_affinity_sorted_pvs(snapshot_abs_path, cmd)
                lvm.create_lv_from_absolute_path(workspace_abs_path, lv_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()),
                                                 pe_ranges=pe_ranges,
                                                 exact_size=True)
            with lvm.OperateLv(workspace_abs_path, shared=False, delete_when_exception=True):
                t_shell = traceable_shell.get_shell(cmd)
                if secret_material_file:
                    linux.create_encrypted_template_with_secret(
                        snapshot_abs_path, workspace_abs_path, secret_material_file, shell=t_shell)
                else:
                    linux.create_template(snapshot_abs_path, workspace_abs_path, shell=t_shell)
                rsp.size = virtual_size
                rsp.actualSize = int(lvm.get_lv_size(workspace_abs_path))

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
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
                lvm.extend_lv_from_cmd(dst_abs_path, measure_size, cmd, extend_thin_by_specified_size=True)
            rsp.size = max(measure_size, current_size)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def extend_logical_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ExtendLogicalVolumeRsp()
        dst_abs_path = translate_absolute_path_from_install_path(cmd.destPath)

        with lvm.OperateLv(dst_abs_path, shared=False):
            lvm.extend_lv_from_cmd(dst_abs_path, cmd.requiredSize, cmd, extend_thin_by_specified_size=True, skip_if_sufficient=True)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offline_merge_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OfflineMergeSnapshotRsp()
        src_abs_path = translate_absolute_path_from_install_path(cmd.srcPath) if not cmd.fullRebase else ""
        dst_abs_path = translate_absolute_path_from_install_path(cmd.destPath)
        encrypted_dek = getattr(cmd, 'encryptedDek', None)

        try:
            with lvm.RecursiveOperateLv(dst_abs_path, shared=False, skip_deactivate_tags=[IMAGE_TAG]):
                raw_backing = linux.qcow2_get_backing_file(dst_abs_path, normalize=False)
                backing_needs_reset = encrypted_dek and raw_backing and raw_backing.startswith('json:')
                if linux.qcow2_get_backing_file(dst_abs_path) == src_abs_path and not backing_needs_reset:
                    rsp.actualSize = lvm.get_lv_size(dst_abs_path)
                    rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
                    return jsonobject.dumps(rsp)

                total_required_size = self.get_total_required_size(dst_abs_path)
                current_size = int(lvm.get_lv_size(dst_abs_path))
                if not cmd.fullRebase:
                    if current_size < total_required_size:
                        lvm.extend_lv_from_cmd(dst_abs_path, total_required_size, cmd, extend_thin_by_specified_size=True)

                    with lvm.RecursiveOperateLv(src_abs_path, shared=True):
                        if encrypted_dek:
                            linux.qcow2_rebase_with_secret(src_abs_path, dst_abs_path,
                                                           lambda: volume_secret.luks_secret_channel(encrypted_dek))
                        else:
                            linux.qcow2_rebase(src_abs_path, dst_abs_path)
                else:
                    tmp_abs_path = os.path.join(os.path.dirname(dst_abs_path), 'tmp_%s' % uuidhelper.uuid())
                    logger.debug("creating temp lv %s" % tmp_abs_path)
                    lv_size = max(total_required_size, current_size)
                    if encrypted_dek:
                        lv_size += LUKS_HEADER_OVERHEAD
                    pe_ranges = lvm.get_lv_affinity_sorted_pvs(dst_abs_path, cmd)
                    lvm.create_lv_from_absolute_path(tmp_abs_path, lv_size,
                                                     "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()),
                                                     pe_ranges=pe_ranges,
                                                     exact_size=True)
                    with lvm.OperateLv(tmp_abs_path, shared=False, delete_when_exception=True):
                        if encrypted_dek:
                            linux.create_encrypted_template_with_secret(dst_abs_path, tmp_abs_path, volume_secret.make_luks_secret_file(encrypted_dek))
                        else:
                            qcow2.create_template_with_task_daemon(dst_abs_path, tmp_abs_path, task_spec=cmd)
                        lvm.lv_rename(tmp_abs_path, dst_abs_path, overwrite=True)
                lvm.delete_lv_meta(dst_abs_path)
                rsp.actualSize = lvm.get_lv_size(dst_abs_path)
        finally:
            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offline_commit_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OfflineCommitSnapshotRsp()
        top = translate_absolute_path_from_install_path(cmd.top)
        base = translate_absolute_path_from_install_path(cmd.base)
        encrypted_dek = getattr(cmd, 'encryptedDek', None)
        with lvm.RecursiveOperateLv(top, shared=True):
            if linux.qcow2_get_backing_file(top) != linux.qcow2_get_backing_file(base):
                if encrypted_dek:
                    linux.qcow2_commit_with_secret(top, base, volume_secret.make_luks_secret_file(encrypted_dek))
                else:
                    linux.qcow2_commit(top, base)

            if cmd.topChildrenInstallPathInDb:
                for childrenInstallPath in cmd.topChildrenInstallPathInDb:
                    with lvm.RecursiveOperateLv(childrenInstallPath, shared=True):
                        if linux.qcow2_get_backing_file(childrenInstallPath) != base:
                            if encrypted_dek:
                                linux.qcow2_rebase_no_check_with_secret(base, childrenInstallPath, volume_secret.make_luks_secret_file(encrypted_dek))
                            else:
                                linux.qcow2_rebase_no_check(base, childrenInstallPath)

            lvm.delete_lv_meta(base)

        rsp.actualSize = lvm.get_lv_size(base)
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateEmptyVolumeRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        encrypted_dek = getattr(cmd, 'encryptedDek', None)

        def make_secret():
            if encrypted_dek:
                return volume_secret.make_luks_secret_file(encrypted_dek)

        is_encrypted = bool(encrypted_dek)

        if cmd.backingFile:
            qcow2_options = self.calc_qcow2_option(self, cmd.kvmHostAddons, True, cmd.provisioning)
            backing_abs_path = translate_absolute_path_from_install_path(cmd.backingFile)
            with lvm.RecursiveOperateLv(backing_abs_path, shared=True):
                virtual_size = linux.qcow2_virtualsize(backing_abs_path)

                if not lvm.lv_exists(install_abs_path):
                    lvm.create_lv_from_cmd(install_abs_path, virtual_size, cmd,
                                                     "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
                with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                    if is_encrypted:
                        lvm.extend_lv(install_abs_path, int(virtual_size) + LUKS_HEADER_OVERHEAD,
                                      skip_if_sufficient=True)
                        linux.qcow2_clone_encrypted(backing_abs_path, install_abs_path,
                                                    make_secret(), size=virtual_size, opt=qcow2_options)
                    else:
                        linux.qcow2_create_with_backing_file_and_option(backing_abs_path, install_abs_path, qcow2_options)
                    rsp.size = linux.qcow2_virtualsize(install_abs_path)
        elif not lvm.lv_exists(install_abs_path):
            lvm.create_lv_from_cmd(install_abs_path, cmd.size, cmd,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            if cmd.volumeFormat != 'raw':
                qcow2_options = self.calc_qcow2_option(self, cmd.kvmHostAddons, False, cmd.provisioning)
                with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                    if is_encrypted:
                        lvm.extend_lv(install_abs_path, int(cmd.size) + LUKS_HEADER_OVERHEAD,
                                      skip_if_sufficient=True)
                        linux.qcow2_create_encrypted(install_abs_path, cmd.size,
                                                     make_secret(), opt=qcow2_options)
                    else:
                        linux.qcow2_create_with_option(install_abs_path, cmd.size, qcow2_options, discard_on_metadata=False)
                    if cmd.zeroFilled and not is_encrypted:
                        # Skip zero-fill on LUKS volumes: qcow2 LUKS clusters are
                        # always cipher-noise so a deliberate-zero pre-pass adds
                        # nothing and just wastes IO.
                        linux.qcow2_fill(0, 1048576, install_abs_path)
                    rsp.size = linux.qcow2_virtualsize(install_abs_path)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.lunCapacities = lvm.get_lun_capacities_from_vg(cmd.vgUuid, self.vgs_path_and_wwid)
        rsp.actualSize = lvm.get_lv_size(install_abs_path)
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
    @lock.file_lock(LOCK_FILE)
    def encrypt_volume_bits(self, req):
        """
        In-place LUKS encryption of a plain volume on a SharedBlock LV.

        Strategy (block-device path; cannot mv-overwrite like LocalStorage):
          1. lvcreate a sibling tmp LV in the same VG, sized = src + LUKS header
             overhead so qemu-img convert has room for the LUKS header.
          2. qemu-img convert  -f <auto>  -O luks  (or -O qcow2 + encrypt.format=luks)
             src  ->  tmp_lv.  Source format dispatches per
             linux.encrypt_plain_volume_block_to_block:
                 raw   -> -O luks         (standalone LUKS, guest sees raw)
                 qcow2 -> -O qcow2 +encrypt.format=luks (LUKS-in-qcow2)
          3. Replace src with tmp_lv via lvrename (atomic, O(1), no data copy):
                 lvrename src     -> <src>.old.<ts>
                lvrename tmp_lv  -> src           tmp now lives at the install path
                 lvremove <src>.old.<ts>
             lvm.lv_rename(..., overwrite=True) implements exactly this dance.
          4. On any failure, lvremove the tmp LV best-effort.
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        tmp_lv_path = None
        try:
            install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
            encrypted_dek = getattr(cmd, 'encryptedDek', None)
            sec_file = volume_secret.make_luks_secret_file(encrypted_dek)

            with lvm.OperateLv(install_abs_path, shared=False):
                # qemu-img convert -O luks needs dst >= src virtual size + LUKS
                # header (~2MB). On a raw LV, virtual size = block device size.
                # We make dst strictly larger by LUKS_HEADER_OVERHEAD;
                # `create_lv_from_cmd` internally re-pads via calcLvReservedSize
                # so dst ends up larger than src by the LUKS and LVM margins.
                # We deliberately do NOT touch src -- growing src would only
                # enlarge what qemu-img has to write into LUKS payload.
                src_size = int(lvm.get_lv_size(install_abs_path))
                dst_request_size = src_size + LUKS_HEADER_OVERHEAD

                vg_uuid = cmd.vgUuid
                tmp_lv_name = "%s-encrypting-%s" % (
                    os.path.basename(install_abs_path), uuidhelper.uuid()[:8])
                tmp_lv_path = "/dev/%s/%s" % (vg_uuid, tmp_lv_name)
                lvm.create_lv_from_cmd(tmp_lv_path, dst_request_size, cmd,
                                       "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))

                with lvm.OperateLv(tmp_lv_path, shared=False, delete_when_exception=True):
                    # Run the LUKS convert: tmp_lv now holds [LUKS header | encrypted payload].
                    linux.encrypt_plain_volume_block_to_block(install_abs_path, tmp_lv_path, sec_file)

                # Atomic swap: tmp_lv takes over the install path, original src
                # LV is renamed aside and then removed. lvm.lv_rename(overwrite=True)
                # does the 3-step dance internally; if the second rename fails it
                # rolls back. After success, tmp_lv_path no longer exists -- the
                # encrypted bits live at install_abs_path under the original name.
                lvm.lv_rename(tmp_lv_path, install_abs_path, overwrite=True)
                tmp_lv_path = None     # ownership transferred; nothing to clean

            logger.debug('successfully LUKS-encrypted volume bits at %s' % install_abs_path)
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.success = False
            rsp.error = 'failed to LUKS-encrypt volume bits at %s: %s' % (cmd.installPath, str(e))
        finally:
            # Reap leftover tmp LV when the convert / rename never completed.
            # On the happy path tmp_lv_path was set to None right after lv_rename,
            # so this is a no-op then.
            if tmp_lv_path is not None and lvm.lv_exists(tmp_lv_path):
                try:
                    lvm.delete_lv(tmp_lv_path, raise_exception=False)
                except Exception as cleanup_ex:
                    logger.warn("failed to lvremove tmp encrypt LV %s: %s" %
                                (tmp_lv_path, cleanup_ex))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def convert_volume_encryption(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConvertVolumeEncryptionRsp()
        encrypted_dek = getattr(cmd, 'encryptedDek', None)
        converted_targets = []

        try:
            if cmd.targetEncrypted and not encrypted_dek:
                raise Exception("target encrypted conversion requires encryptedDek")

            lvm.update_pv_allocate_strategy(cmd)
            for index, item in enumerate(cmd.items):
                source_abs_path = translate_absolute_path_from_install_path(item.sourceInstallPath)
                target_abs_path = translate_absolute_path_from_install_path(item.targetInstallPath)
                if not lvm.lv_exists(source_abs_path):
                    raise Exception("source lv %s does not exist" % source_abs_path)
                if lvm.lv_exists(target_abs_path):
                    raise Exception("target lv %s already exists" % target_abs_path)

                target_backing_abs_path = None
                if getattr(item, 'targetBackingInstallPath', None):
                    target_backing_abs_path = translate_absolute_path_from_install_path(item.targetBackingInstallPath)

                secret_file_provider = (lambda: volume_secret.luks_secret_channel(encrypted_dek)) if encrypted_dek else None
                with lvm.RecursiveOperateLv(source_abs_path, shared=True):
                    lv_size = self.get_convert_volume_encryption_lv_size(
                        source_abs_path, cmd.targetEncrypted, target_backing_abs_path)
                    lvm.create_lv_from_absolute_path(target_abs_path, lv_size, exact_size=True)
                    converted_targets.append(target_abs_path)

                    if target_backing_abs_path:
                        with lvm.RecursiveOperateLv(target_backing_abs_path, shared=True):
                            with lvm.OperateLv(target_abs_path, shared=False, delete_when_exception=True):
                                actual_size = linux.convert_qcow2_volume_encryption(
                                    source_abs_path, target_abs_path, cmd.targetEncrypted,
                                    secret_file_provider, target_backing_abs_path)
                    else:
                        with lvm.OperateLv(target_abs_path, shared=False, delete_when_exception=True):
                            actual_size = linux.convert_qcow2_volume_encryption(
                                source_abs_path, target_abs_path, cmd.targetEncrypted,
                                secret_file_provider, target_backing_abs_path)

                rsp.actualSizes[item.resourceUuid] = long(lvm.get_lv_size(target_abs_path) or actual_size)

            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            for target_abs_path in converted_targets:
                lvm.delete_lv(target_abs_path, False)
            rsp.success = False
            rsp.error = 'failed to convert volume[%s] encryption: %s' % (cmd.volumeUuid, str(e))

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
                lvm.create_lv_from_absolute_path(temp_path, lv_size, exact_size=True)
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
                    if killProcess:
                        qemus = linux.find_qemu_for_volume_in_use(fpath)
                        if len(qemus) == 0:
                            return
                        for qemu in qemus:
                            if qemu.state != "running":
                                linux.kill_process(qemu.pid)
                        lvm.deactive_lv(fpath)
                    elif raise_exception:
                        raise e

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
    def batch_get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetBatchVolumeSizeRsp()

        for uuid, installPath in cmd.volumeUuidInstallPaths.__dict__.items():
            with IgnoreError():
                install_abs_path = translate_absolute_path_from_install_path(installPath)
                rsp.actualSizes[uuid] = lvm.get_lv_size(install_abs_path)

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

        top = translate_absolute_path_from_install_path(cmd.volumePath)

        for struct in cmd.migrateVolumeStructs:
            target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
            current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)
            with lvm.RecursiveOperateLv(current_abs_path, shared=True):
                if linux.get_img_fmt(current_abs_path) == 'raw':
                    lv_size = int(lvm.get_lv_size(current_abs_path))
                elif top == current_abs_path:
                    lv_size = int(linux.qcow2_virtualsize(current_abs_path))
                    lv_size = lvm.calcLvReservedSize(lv_size)
                elif struct.independent:
                    cluster_size = linux.qcow2_get_cluster_size(current_abs_path)
                    lv_size = linux.qcow2_measure_required_size(current_abs_path, cluster_size=cluster_size)
                    lv_size = lvm.calcLvReservedSize(lv_size)
                else:
                    lv_size = int(lvm.get_lv_size(current_abs_path))
                    if linux.qcow2_get_backing_file(current_abs_path) == '':
                        cluster_size = linux.qcow2_get_cluster_size(current_abs_path)
                        measure_size = linux.qcow2_measure_required_size(current_abs_path, cluster_size=cluster_size)
                        if lvm.calcLvReservedSize(measure_size) > lv_size:
                            struct.put('compressed_qcow2', True)
                struct.put('lv_size', lv_size)

            if lvm.lv_exists(target_abs_path):
                if struct.skipIfExisting:
                    struct.put('skip_copy', True)
                    lvm.active_lv(target_abs_path, shared=True)
                    continue
                target_ps_uuid = get_primary_storage_uuid_from_install_path(struct.targetInstallPath)
                raise Exception("found %s already exists on ps %s" %
                                (target_abs_path, target_ps_uuid))
            lvm.create_lv_from_absolute_path(target_abs_path, lv_size,
                                             "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), exact_size=True)
            lvm.active_lv(target_abs_path, shared=True)
            total_size += lv_size

        PFILE = linux.create_temp_file()
        try:
            parent_stage = get_task_stage(cmd, "10-90")

            for struct in cmd.migrateVolumeStructs:
                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)

                if struct.skip_copy:
                    migrated_size += struct.lv_size
                    continue

                start = get_exact_percent(float(migrated_size) / total_size * 100, parent_stage)
                end = get_exact_percent(float(struct.lv_size + migrated_size) / total_size * 100, parent_stage)

                with lvm.RecursiveOperateLv(current_abs_path, shared=True):
                    if struct.compressed_qcow2 or linux.get_img_fmt(current_abs_path) == 'raw':
                        t_bash = traceable_shell.get_shell(cmd)
                        t_bash.bash_errorout("pv -n %s > %s" % (current_abs_path, target_abs_path))
                    else:
                        backing_file = None if struct.independent else linux.qcow2_get_backing_file(current_abs_path)
                        opts = "" if not backing_file else " -B %s " % backing_file
                        if backing_file and not qemu_img.take_default_backing_fmt_for_convert():
                            opts += " -F %s " % linux.get_img_fmt(backing_file)

                        opts += re.sub("-o preallocation=\w*", "", cmd.kvmHostAddons.qcow2Options)
                        if current_abs_path != top:
                            # keep origin cluster_size
                            opts = re.sub(r"(cluster_size=)\w+", r"\g<1>"+str(linux.qcow2_get_cluster_size(current_abs_path)), opts)
                        qcow2.create_template_with_task_daemon(current_abs_path, target_abs_path, cmd,
                                                           opts=opts,
                                                           dst_format=linux.get_img_fmt(current_abs_path),
                                                           stage="%s-%s" % (start, end),
                                                           task_name="MigrateVolumes")

                    if top == current_abs_path and cmd.provisioning == lvm.VolumeProvisioningStrategy.ThinProvisioning:
                        lvm.active_lv(target_abs_path, shared=False)
                        old_size, new_size = self.shrink_lv_on_qcow2(target_abs_path, cmd.addons[lvm.thinProvisioningInitializeSize])
                        logger.debug("shrink lv %s from %s to %s on qcow2 after migration" % (target_abs_path, old_size, new_size))
                        lvm.active_lv(target_abs_path, shared=True)

                migrated_size += struct.lv_size

            for struct in cmd.migrateVolumeStructs:
                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)
                with lvm.RecursiveOperateLv(current_abs_path, shared=True):
                    previous_ps_uuid = get_primary_storage_uuid_from_install_path(struct.currentInstallPath)
                    target_ps_uuid = get_primary_storage_uuid_from_install_path(struct.targetInstallPath)

                    current_backing_file = linux.qcow2_get_backing_file(current_abs_path)  # type: str

                    if struct.compareQcow2 and not struct.independent:
                        if linux.get_img_fmt(current_abs_path) == "qcow2":
                            r, o, e = bash.bash_roe("%s %s" % (qemu_img.subcmd("check"), target_abs_path))
                            if r != 0 and "No errors were found" not in str(o):
                                raise Exception("target qcow2 image[%s] has been corrupted after migration, stdout: %s, stderr: %s" % (target_abs_path, o ,e))
                    if current_backing_file and not struct.independent:
                        target_backing_file = current_backing_file.replace(previous_ps_uuid, target_ps_uuid)
                        lvm.active_lv(target_backing_file, shared=True)
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
                if struct.skipIfExisting:
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
            p = disk.get_path(raise_exception=False)
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

        abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        with lvm.RecursiveOperateLv(abs_path, shared=False):
            rsp.oldSize, rsp.size = self.shrink_lv_on_qcow2(abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    def shrink_lv_on_qcow2(self, installPath, extra_size=0):
        old_size = long(lvm.get_lv_size(installPath))
        if 'qcow2' != linux.get_img_fmt(installPath):
            return old_size, old_size

        virtual_size = linux.qcow2_get_virtual_size(installPath)
        check_result = qemu_img.get_check_result(installPath)  # type: qemu_img.CheckResult
        if check_result.allocated_clusters is None or check_result.allocated_clusters != check_result.total_clusters:
            new_size = long(check_result.image_end_offset) + extra_size
            if new_size >= old_size:
                return old_size, old_size
            if new_size > virtual_size:
                new_size = virtual_size

            lvm.resize_lv(installPath, new_size, True)

        new_size = long(lvm.get_lv_size(installPath))
        return old_size, new_size

    @kvmagent.replyerror
    def get_qcow2_hashvalue(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetQcow2HashValueRsp()
        abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        with lvm.RecursiveOperateLv(abs_path, shared=True):
            rsp.hashValue = secret.get_image_hash(abs_path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.lock('check_vg')
    def check_vg_state(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        lvm.check_stuck_vglk_and_gllk()

        if cmd.vgUuids is None or len(cmd.vgUuids) == 0:
            return jsonobject.dumps(rsp)

        def _check(cur_vg):
            if lvmlockd_status.failed:
                return "Cannot access lvmlockd"

            if lvmlockd_status.ls_status.get(cur_vg) is None or lvmlockd_status.ls_status.get(cur_vg).killed or \
                    lvmlockd_status.ls_status.get(cur_vg).dropped:
                return "no working lockspace for vg %s on lvmlockd" % cur_vg

            if sanlock_ls.get_lockspace_record(cur_vg) is None or sanlock_ls.get_lockspace_record(cur_vg).is_space_dead():
                return "no working lockspace for vg %s on sanlock" % cur_vg

            invalid_pv_uuid, err = lvm.get_invalid_pv_uuids(cur_vg, checkIo=False, timeout=60)
            if err:
                return err
            elif len(invalid_pv_uuid) != 0:
                return "vg %s is missing pv: %s" % (cur_vg, invalid_pv_uuid)

        sanlock_ls = sanlock.SanlockClientStatusParser()
        lvmlockd_status = lvm.LvmlockdStatus()
        rsp.failedVgs = {}

        for vg_uuid in set(cmd.vgUuids):
            error = _check(vg_uuid)
            if error:
                rsp.failedVgs.update({vg_uuid: error})

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def takeover(self, req):
        def _takeover_get_lock(sblk_lock, retry_times=10, retry_interval=(1, 2)):
            for i in range(retry_times):
                sblk_lock.lock = lock._get_lock(sblk_lock.name)
                if sblk_lock.lock.acquire(False):
                    return
                if i < retry_times - 1:
                    sleep = random.uniform(*retry_interval)
                    logger.debug(
                        "cannot get %s lock, retry %d/%d after %.1fs" % (sblk_lock.name, i + 1, retry_times, sleep))
                    time.sleep(sleep)
            raise SharedBlockConnectException("can not get %s lock after %d retries" % (sblk_lock.name, retry_times))

        def _takeover_release_lock(sblk_lock):
            try:
                sblk_lock.lock.release()
            except Exception:
                return

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        sblk_lock = lock.NamedLock("sharedblock-%s" % cmd.vgUuid)
        rsp = None
        try:
            _takeover_get_lock(sblk_lock)
            rsp = self.do_takeover(cmd)
        except SharedBlockConnectException as e:
            r = AgentRsp()
            r.success = False
            r.error = "can not take over sharedblock primary storage[uuid: %s] on host[uuid: %s], " \
                      "because another sharedblock operation (connect or takeover) is in progress" % (cmd.vgUuid, cmd.hostUuid)
            rsp = jsonobject.dumps(r)
        except Exception as e:
            if rsp is None:
                r = AgentRsp()
                r.success = False
                content = traceback.format_exc()
                r.error = "%s\n%s" % (str(e), content)
                rsp = jsonobject.dumps(r)
        finally:
            _takeover_release_lock(sblk_lock)
            return rsp

    @lock.file_lock(LOCK_FILE)
    def do_takeover(self, cmd):
        rsp = TakeoverRsp()
        logger.info("takeover starts: vgUuid=%s, hostId=%s, hostUuid=%s, disks=%s"
                    % (cmd.vgUuid, cmd.hostId, cmd.hostUuid, cmd.sharedBlockUuids))

        # Step 1: prepare disk paths - all disks are required (consistent with do_connect)
        diskPaths = set()
        allDiskPaths = set()

        for diskUuid in cmd.sharedBlockUuids:
            disk = CheckDisk(diskUuid)
            diskPaths.add(disk.get_path())

        for diskUuid in (cmd.allSharedBlockUuids or []):
            disk = CheckDisk(diskUuid)
            p = disk.get_path(raise_exception=False)
            if p is not None:
                allDiskPaths.add(p)

        allDiskPaths = allDiskPaths.union(diskPaths)
        try:
            root_disks = ["%s[0-9]*" % d for d in linux.get_physical_disk()]
            allDiskPaths = allDiskPaths.union(root_disks)
        except Exception as e:
            logger.warn("get exception: %s" % e.message)
            allDiskPaths.add("/dev/sd*")
            allDiskPaths.add("/dev/vd*")
        logger.info("takeover[1/8] prepared %d disk paths" % len(allDiskPaths))

        # Step 2: configure LVM
        lvm.config_lvm(cmd.hostId, allDiskPaths, cmd.vgUuid, cmd.hostUuid, DEFAULT_SANLOCK_LV_SIZE,
                       kvmagent.get_host_os_type(), cmd.enableLvmetad)
        logger.info("takeover[2/8] LVM config applied")

        # Step 3: start lock service
        lvm.start_lock_service(cmd.ioTimeout)
        logger.info("takeover[3/8] lock service started")

        # Step 4: find VG on storage by exact WWID match
        def get_vg_name_by_shared_block_uuid():
            groupDiskInfos = lvm.get_managed_vgs(tag=INIT_TAG)
            target_wwids = set(w.strip().lower() for w in cmd.sharedBlockUuids if w and w.strip())
            matched_vgs = []

            for _vg_uuid, disk_info in groupDiskInfos.items():
                block_devices = disk_info["disks"]
                expected_pv_count = disk_info["diskCount"]
                if any(not bd.wwid for bd in block_devices) or len(block_devices) != expected_pv_count:
                    logger.warn("skip VG %s: incomplete WWID set" % _vg_uuid)
                    continue
                vg_wwids = set(bd.wwid.strip().lower() for bd in block_devices)
                if target_wwids == vg_wwids:
                    matched_vgs.append(_vg_uuid)

            if len(matched_vgs) == 0:
                available = {k: [bd.wwid for bd in v["disks"]]
                             for k, v in groupDiskInfos.items()}
                raise Exception("cannot find VG with tag prefix [%s] and exact WWID match. "
                                "target=%s, available=%s" % (INIT_TAG, cmd.sharedBlockUuids, available))
            if len(matched_vgs) > 1:
                raise Exception("found multiple VGs matching the same WWID set: %s" % matched_vgs)
            return matched_vgs[0]

        vg_uuid_on_storage = get_vg_name_by_shared_block_uuid()
        logger.info("takeover[4/8] matched VG: %s (target: %s)" % (vg_uuid_on_storage, cmd.vgUuid))

        # Step 5: reset sanlock lockspace and re-establish lock
        lvm.check_stuck_vglk_and_gllk()
        retry_times = lvm.get_retry_times_for_checking_vg_lockspace()

        active_vg_uuid = vg_uuid_on_storage
        drop_lock_on_failure = False
        try:
            running_lockspace = sanlock.get_lockspace(vg_uuid_on_storage)
            if not running_lockspace:
                drop_lock_on_failure = True
                logger.info("takeover[5/8] remove stale device maps for %s before lock start" %
                            vg_uuid_on_storage)
                lvm.remove_device_map_for_vg(vg_uuid_on_storage, raise_exception=True)
            else:
                logger.info("takeover[5/8] skip stale device map cleanup for %s, active lockspace exists: %s" %
                            (vg_uuid_on_storage, running_lockspace))

            reset_done = False
            try:
                lvm.start_vg_lock(vg_uuid_on_storage, cmd.hostId, retry_times)
            except Exception as e:
                if running_lockspace:
                    raise
                lockspace_after_failed_start = sanlock.get_lockspace(vg_uuid_on_storage)
                if lockspace_after_failed_start:
                    raise Exception("lockspace for %s became active after lock start failure, "
                                    "skip offline reset: %s" %
                                    (vg_uuid_on_storage, lockspace_after_failed_start))
                logger.warn("takeover[5/8] initial lock start failed for %s, "
                            "reset sanlock lockspace and retry: %s" % (vg_uuid_on_storage, str(e)))
                lvm.reset_sanlock_lockspace(vg_uuid_on_storage, cmd.ioTimeout)
                lvm.drop_vg_lock(vg_uuid_on_storage)
                lvm.start_vg_lock(vg_uuid_on_storage, cmd.hostId, retry_times)
                reset_done = True

            if running_lockspace:
                logger.info("takeover[5/8] sanlock lockspace already active for %s, skip reset" %
                            vg_uuid_on_storage)
            elif not reset_done:
                lvm.reset_sanlock_lockspace(vg_uuid_on_storage, cmd.ioTimeout)
                lvm.drop_vg_lock(vg_uuid_on_storage)
                lvm.start_vg_lock(vg_uuid_on_storage, cmd.hostId, retry_times)
                logger.info("takeover[5/8] sanlock lockspace reset for %s" % vg_uuid_on_storage)
            else:
                logger.info("takeover[5/8] sanlock lockspace reset for %s" % vg_uuid_on_storage)

            lvm.check_gl_lock()

            # Step 6: rename VG to match the target platform's database UUID
            if vg_uuid_on_storage != cmd.vgUuid:
                lvm.rename_vg(vg_uuid_on_storage, cmd.vgUuid)
                active_vg_uuid = cmd.vgUuid
                logger.info("takeover[6/8] VG renamed %s -> %s" % (vg_uuid_on_storage, cmd.vgUuid))
                lvm.start_vg_lock(cmd.vgUuid, cmd.hostId, retry_times)
                drop_lock_on_failure = True
            else:
                logger.info("takeover[6/8] VG name already matches, skip rename")

            self.clear_stalled_qmp_socket()

            # Step 7: fix PV state
            lvm.check_missing_pv(cmd.vgUuid)
            lvm.update_lockspace_io_timeout_if_need(cmd.vgUuid, cmd.ioTimeout)
            lvm.reset_pv_uuids(cmd.vgUuid)
            logger.info("takeover[7/8] PV state fixed for %s" % cmd.vgUuid)

            # Step 8: stamp VG tag with current host info
            new_tag = "%s::%s::%s::%s" % (INIT_TAG, cmd.hostUuid, time.time(), linux.get_hostname())
            lvm.update_vg_tag(cmd.vgUuid, INIT_TAG, new_tag)
            logger.info("takeover[8/8] VG tag updated for %s" % cmd.vgUuid)
        except Exception:
            if drop_lock_on_failure:
                logger.warn("takeover failed after lockspace setup, "
                            "dropping vg lock for %s to allow next host to retry" % active_vg_uuid)
                try:
                    lvm.drop_vg_lock(active_vg_uuid)
                except Exception as drop_err:
                    logger.warn("drop vg lock failed for %s during takeover cleanup: %s" %
                                (active_vg_uuid, str(drop_err)))
            else:
                logger.warn("takeover failed while lockspace already active for %s, skip dropping vg lock" %
                            active_vg_uuid)
            raise

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def vgs_all_info(self, req):
        rsp = GetVgsInfoRsp()
        rsp.groupDiskInfos = lvm.get_all_vgs(tag=INIT_TAG)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def vgs_managed_info(self, req):
        rsp = GetManagedVgsInfoRsp()
        rsp.groupDiskInfos = lvm.get_managed_vgs(tag=INIT_TAG)
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def write_vm_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = WriteVmMetadataRsp()
        self._metadata_handler.write(cmd)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def scan_vm_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ScanVmMetadataRsp()
        rsp.metadataEntries = self._metadata_handler.scan(cmd)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cleanup_vm_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CleanupVmMetadataRsp()
        self._metadata_handler.cleanup(cmd)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cleanup_all_vm_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CleanupAllVmMetadataRsp()
        result = self._metadata_handler.cleanup_all(cmd) or {}
        if result.get('error'):
            rsp.success = False
            rsp.error = result.get('error')
        rsp.skipped = result.get('skipped', False)
        rsp.currentGeneration = result.get('currentGeneration')
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_vm_instance_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVmInstanceMetadataRsp()
        result = self._metadata_handler.get(cmd)
        rsp.metadata = result.get('metadata')
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def prefix_rebase_backing_files(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = PrefixRebaseBackingFilesRsp()

        rsp.rebasedCount = sblk_prefix_rebase_backing_files(
            file_paths=cmd.filePaths,
            old_prefix=cmd.oldPrefix,
            new_prefix=cmd.newPrefix,
            normalize_path=translate_absolute_path_from_install_path,
            lvm_module=lvm,
        )
        return jsonobject.dumps(rsp)

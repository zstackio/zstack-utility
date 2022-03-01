import os.path
import re
import random
import time

from typing import Dict, Any

from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from kvmagent.plugins import mini_fencer
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import lock
from zstacklib.utils import lvm
from zstacklib.utils import bash
from zstacklib.utils import drbd
from zstacklib.utils import iproute

logger = log.get_logger(__name__)
LOCK_FILE = "/var/run/zstack/ministorage.lock"
BACKUP_DIR = "/var/lib/zstack/ministorage/backup"

INIT_TAG = "zs::ministorage::init"
FENCER_TAG = "zs::ministorage::fencer"
MANAGEMENT_TAG = "zs::ministorage::management"
HEARTBEAT_TAG = "zs::ministorage::heartbeat"
VOLUME_TAG = "zs::ministorage::volume"
IMAGE_TAG = "zs::ministorage::image"
DEFAULT_VG_METADATA_SIZE = "1g"

INIT_POOL_RATIO = 0.1
DEFAULT_CHUNK_SIZE = "4194304"
DRBD_START_PORT = 20000


class AgentCmd(object):
    def __init__(self):
        pass


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None
        self.totalCapacity = None
        self.availableCapacity = None


class ConnectCmd(AgentCmd):
    @log.sensitive_fields("peerSshPassword", "peerSshUsername")
    def __init__(self):
        super(ConnectCmd, self).__init__()
        self.diskIdentifiers = []
        self.forceWipe = False
        self.storageNetworkCidr = None
        self.fencerAddress = None
        self.magementAddress = None
        self.peerManagementAddress = None
        self.peerSshPassword = None
        self.peerSshUsername = None


class ConnectRsp(AgentRsp):
    def __init__(self):
        super(ConnectRsp, self).__init__()
        self.hostUuid = None
        self.storageNetworkAddress = None


class VolumeRsp(AgentRsp):
    def __init__(self):
        super(VolumeRsp, self).__init__()
        self.actualSize = None
        self.resourceUuid = None
        self.localRole = None
        self.localDiskStatus = None
        self.localNetworkStatus = None
        self.remoteRole = None
        self.remoteDiskStatus = None
        self.remoteNetworkStatus = None
        self.minor = None

    def _init_from_drbd(self, r):
        """

        :type r: drbd.DrbdResource
        """
        if not r.minor_allocated():
            self.localNetworkStatus = drbd.DrbdNetState.Unconfigured
            return
        self.actualSize = int(lvm.get_lv_size(r.config.local_host.disk))
        self.resourceUuid = r.name
        self.localRole = r.get_role()
        self.localDiskStatus = r.get_dstate()
        self.remoteRole = r.get_remote_role()
        self.remoteDiskStatus = r.get_remote_dstate()
        self.localNetworkStatus = r.get_cstate()
        self.minor = int(r.config.local_host.minor)



class ActiveRsp(VolumeRsp):
    def __init__(self):
        super(ActiveRsp, self).__init__()
        self.snapPath = ""


class CheckBitsRsp(AgentRsp):
    existing = False  # type: bool
    replications = {}  # type: Dict[str, ReplicationInformation]

    def __init__(self):
        super(CheckBitsRsp, self).__init__()
        self.existing = False
        self.replications = dict()
        self.storageNetworkStatus = "Connected"


class ReplicationInformation(object):
    diskStatus = None  # type: str
    networkStatus = None  # type: str
    role = None  # type: str
    size = None  # type: long
    name = None  # type: str
    minor = None  # type: long

    def __init__(self):
        super(ReplicationInformation, self).__init__()
        self.diskStatus = None  # type: str
        self.networkStatus = None  # type: str
        self.role = None  # type: str
        self.size = None  # type: long
        self.name = None  # type: str
        self.minor = None  # type: long



class GetVolumeSizeRsp(VolumeRsp):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None


class ResizeVolumeRsp(VolumeRsp):
    def __init__(self):
        super(ResizeVolumeRsp, self).__init__()
        self.size = None


class RetryException(Exception):
    pass


class GetBlockDevicesRsp(AgentRsp):
    blockDevices = None  # type: list[lvm.SharedBlockCandidateStruct]

    def __init__(self):
        super(GetBlockDevicesRsp, self).__init__()
        self.blockDevices = None


class ConvertVolumeProvisioningRsp(AgentRsp):
    actualSize = None  # type: int

    def __init__(self):
        super(ConvertVolumeProvisioningRsp, self).__init__()
        self.actualSize = 0


class RevertVolumeFromSnapshotRsp(VolumeRsp):
    def __init__(self):
        super(RevertVolumeFromSnapshotRsp, self).__init__()
        self.newVolumeInstallPath = None
        self.size = None


class GetQCOW2ReferenceRsp(AgentRsp):
    def __init__(self):
        super(GetQCOW2ReferenceRsp, self).__init__()
        self.referencePaths = None


class UploadBitsToFileSystemRsp(AgentRsp):
    def __init__(self):
        super(UploadBitsToFileSystemRsp, self).__init__()
        self.totalSize = 0


class DownloadBitsFromFileSystemRsp(AgentRsp):
    def __init__(self):
        super(DownloadBitsFromFileSystemRsp, self).__init__()
        self.downloadedInfos = []  # type: list[LvInfo]


class LvInfo(object):
    def __init__(self, install_path, size):
        self.installPath = install_path
        self.size = size


def get_absolute_path_from_install_path(path):
    if path is None:
        raise Exception("install path can not be null")
    return path.replace("mini:/", "/dev")


def get_primary_storage_uuid_from_install_path(path):
    # type: (str) -> str
    if path is None:
        raise Exception("install path can not be null")
    return path.split("/")[2]


class CheckDisk(object):
    def __init__(self, identifier):
        self.identifier = identifier

    def get_path(self):
        if os.path.exists(self.identifier):
            return self.identifier

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
            _cmd = shell.ShellCmd("echo 1 > /sys/block/%s/device/rescan" % slave)
            _cmd(is_exception=raise_exception)
            logger.debug("rescaned disk %s (wwid: %s), return code: %s, stdout %s, stderr: %s" %
                         (slave, self.identifier, _cmd.return_code, _cmd.stdout, _cmd.stderr))

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
        r, o, e = bash.bash_roe(command, errorout=True)
        logger.debug("resized pv %s (wwid: %s), return code: %s, stdout %s, stderr: %s" %
                     (disk_name, self.identifier, r, o, e))


class MiniFileConverter(linux.AbstractFileConverter):
    def __init__(self, cmd=None):
        super(MiniFileConverter, self).__init__()
        self.cmd = cmd
        self.resourceId = os.path.basename(cmd.srcInstallPath) if cmd else None

    def get_backing_file(self, path):
        return linux.qcow2_direct_get_backing_file(path)

    def convert_from_file_with_backing(self, src, dst, dst_backing, backing_fmt):
        # type: (str, str, str, str) -> int
        if self.cmd.srcInstallPath != src:  # base:
            return self._convert_image_from_file(src, dst, dst_backing, backing_fmt)
        else:  # top
            return self._convert_volume_from_file(src, dst, dst_backing, backing_fmt)

    def convert_to_file(self, src, dst):
        drbd_res = drbd.DrbdResource(os.path.basename(src))
        if drbd_res.exists:
            drbd_res.dd_out(dst)
        else:
            if not os.path.exists(src):
                lvm.active_lv(src, shared=True)
            shell.call('dd if=%s of=%s conv=sparse bs=1M' % (src, dst))

    def get_size(self, path):
        # type: (str) -> int
        return lvm.get_lv_size(path)

    def exists(self, path):
        # type: (str) -> bool
        return os.path.exists(path)

    def _convert_volume_from_file(self, src, dst, dst_backing, backing_fmt):
        drbdResource = drbd.DrbdResource(os.path.basename(dst), False)
        if not drbdResource.exists or drbdResource.config.local_host.minor != str(self.cmd.local_host_port - DRBD_START_PORT):
            drbdResource.config.local_host.hostname = self.cmd.local_host_name
            drbdResource.config.local_host.disk = dst
            drbdResource.config.local_host.minor = self.cmd.local_host_port - DRBD_START_PORT
            drbdResource.config.local_host.address = "%s:%s" % (self.cmd.local_address, self.cmd.local_host_port)

            drbdResource.config.remote_host.hostname = self.cmd.remote_host_name
            drbdResource.config.remote_host.disk = dst
            drbdResource.config.remote_host.minor = self.cmd.remote_host_port - DRBD_START_PORT
            drbdResource.config.remote_host.address = "%s:%s" % (self.cmd.remote_address, self.cmd.remote_host_port)

            drbdResource.config.write_config()

        size = linux.qcow2_get_virtual_size(src)
        tag = "%s::%s::%s" % (VOLUME_TAG, self.cmd.hostUuid, time.time())

        try:
            if not lvm.lv_exists(dst):
                lvm.create_lv_from_cmd(dst, size, self.cmd, tag, False)
            lvm.active_lv(dst)
            drbdResource.initialize_with_file(True, src, backing=dst_backing, backing_fmt=backing_fmt)
            return size
        except Exception as e:
            drbdResource.destroy()
            lvm.delete_lv(dst)
            logger.debug('failed to convert lv from file[size:%s] at %s' % (size, dst))
            raise e

    def _convert_image_from_file(self, src, dst, dst_backing, backing_fmt):
        try:
            size = linux.qcow2_measure_required_size(src)
        except Exception as e:
            logger.warn("can not get qcow2 %s measure size: %s" % (src, e))
            size = linux.get_local_file_size(src)
        tag = "%s::%s::%s" % (IMAGE_TAG, self.cmd.hostUuid, time.time())
        if not lvm.lv_exists(dst):
            lvm.create_lv_from_cmd(dst, size, self.cmd, tag, False)
        lvm.active_lv(dst)
        bash.bash_errorout('dd if=%s of=%s bs=1M' % (src, dst))
        if dst_backing:
            linux.qcow2_rebase_no_check(dst_backing, dst, backing_fmt=backing_fmt)

        return size


class MiniStoragePlugin(kvmagent.KvmAgent):

    CONNECT_PATH = "/ministorage/connect"
    DISCONNECT_PATH = "/ministorage/disconnect"
    CREATE_VOLUME_FROM_CACHE_PATH = "/ministorage/createrootvolume"
    DELETE_BITS_PATH = "/ministorage/bits/delete"
    CREATE_TEMPLATE_FROM_VOLUME_PATH = "/ministorage/createtemplatefromvolume"
    UPLOAD_BITS_TO_IMAGESTORE_PATH = "/ministorage/imagestore/upload"
    COMMIT_BITS_TO_IMAGESTORE_PATH = "/ministorage/imagestore/commit"
    DOWNLOAD_BITS_FROM_IMAGESTORE_PATH = "/ministorage/imagestore/download"
    CREATE_EMPTY_VOLUME_PATH = "/ministorage/volume/createempty"
    CREATE_SECONDARY_VOLUME = "/ministorage/volume/createsecondary"
    CREATE_EMPTY_CACHE_VOLUME_PATH = "/ministorage/cachevolume/createempty"
    CHECK_BITS_PATH = "/ministorage/bits/check"
    RESIZE_VOLUME_PATH = "/ministorage/volume/resize"
    CONVERT_IMAGE_TO_VOLUME = "/ministorage/image/tovolume"
    CHANGE_VOLUME_ACTIVE_PATH = "/ministorage/volume/active"
    GET_VOLUME_SIZE_PATH = "/ministorage/volume/getsize"
    CHECK_DISKS_PATH = "/ministorage/disks/check"
    MIGRATE_DATA_PATH = "/ministorage/volume/migrate"
    REVERT_VOLUME_FROM_SNAPSHOT_PATH = "/ministorage/volume/revertfromsnapshot"
    GET_QCOW2_REFERENCE = "/ministorage/getqcow2reference"
    FLUSH_CACHE = "/ministorage/cache/flush"
    UPLOAD_BITS_TO_FILESYSTEM_PATH = "/ministorage/filesystem/upload"
    DOWNLOAD_BITS_FROM_FILESYSTEM_PATH = "/ministorage/filesystem/download"
    SYNC_BACKING_CHAIN = "/ministorage/volume/syncbackingchain"
    DISCARD_RESOURCE = "/ministorage/volume/discard"
    FORCE_CONNECT_RESOURCE = "/ministorage/volume/connect"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CONNECT_PATH, self.connect, cmd=ConnectCmd())
        http_server.register_async_uri(self.DISCONNECT_PATH, self.disconnect)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.create_root_volume)
        http_server.register_async_uri(self.DELETE_BITS_PATH, self.delete_bits)
        http_server.register_async_uri(self.CREATE_TEMPLATE_FROM_VOLUME_PATH, self.create_template_from_volume)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_IMAGESTORE_PATH, self.upload_to_imagestore)
        http_server.register_async_uri(self.COMMIT_BITS_TO_IMAGESTORE_PATH, self.commit_to_imagestore)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_IMAGESTORE_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.create_empty_volume)
        http_server.register_async_uri(self.CREATE_SECONDARY_VOLUME, self.create_secondary_volume)
        http_server.register_async_uri(self.CREATE_EMPTY_CACHE_VOLUME_PATH, self.create_empty_cache_volume)
        http_server.register_async_uri(self.CONVERT_IMAGE_TO_VOLUME, self.convert_image_to_volume)
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize_volume)
        http_server.register_async_uri(self.CHANGE_VOLUME_ACTIVE_PATH, self.active_lv)
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        http_server.register_async_uri(self.CHECK_DISKS_PATH, self.check_disks)
        http_server.register_async_uri(self.REVERT_VOLUME_FROM_SNAPSHOT_PATH, self.revert_volume_from_snapshot)
        http_server.register_async_uri(self.GET_QCOW2_REFERENCE, self.get_qcow2_reference)
        http_server.register_async_uri(self.FLUSH_CACHE, self.flush_cache)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_FILESYSTEM_PATH, self.upload_to_filesystem)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_FILESYSTEM_PATH, self.download_from_filesystem)
        http_server.register_async_uri(self.SYNC_BACKING_CHAIN, self.sync_backing_chain)
        http_server.register_async_uri(self.DISCARD_RESOURCE, self.discard_resource)
        http_server.register_async_uri(self.FORCE_CONNECT_RESOURCE, self.force_connect_resource)

        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    @kvmagent.replyerror
    def check_disks(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        for diskId in cmd.diskIdentifiers:
            disk = CheckDisk(diskId)
            path = disk.get_path()
            if cmd.rescan:
                disk.rescan(path.split("/")[-1])
            if cmd.failIfNoPath:
                linux.set_fail_if_no_path()

        if cmd.vgUuid is not None and lvm.vg_exists(cmd.vgUuid):
            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, False)

        return jsonobject.dumps(rsp)

    @staticmethod
    @bash.in_bash
    def create_thin_pool_if_not_found(vgUuid, init_pool_ratio):
        def round_sector(size, sector):
            return round(float(size) / float(sector)) * sector

        if lvm.lv_exists("/dev/%s/%s_thinpool" % (vgUuid, vgUuid)):
            return
        tot, avil = lvm.get_vg_size(vgUuid)
        init_pool_size = float(tot) * float(init_pool_ratio)
        # meta_size = "%s" % ((tot / DEFAULT_CHUNK_SIZE) * 48 * 2)  # ref: https://www.kernel.org/doc/Documentation/device-mapper/thin-provisioning.txt
        meta_size = 1024**3  # ref: https://www.systutorials.com/docs/linux/man/7-lvmthin/#lbBD
        bash.bash_errorout("lvcreate --type thin-pool -L %sB -c %sB --poolmetadatasize %sB -n %s_thinpool %s" %
                           (int(round_sector(init_pool_size, 4096)), DEFAULT_CHUNK_SIZE, meta_size, vgUuid, vgUuid))

    @staticmethod
    def create_vg_if_not_found(vgUuid, disks, diskPaths, hostUuid, forceWipe=False):
        @linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
        def find_vg(vgUuid, raise_exception=True):
            cmd = shell.ShellCmd("timeout 5 vgscan --ignorelockingfailure; vgs --nolocking %s -otags | grep %s" % (vgUuid, INIT_TAG))
            cmd(is_exception=False)
            if cmd.return_code != 0 and raise_exception:
                raise RetryException("can not find vg %s with tag %s" % (vgUuid, INIT_TAG))
            elif cmd.return_code != 0:
                return False
            return True

        try:
            find_vg(vgUuid)
        except RetryException as e:
            if forceWipe is True:
                running_vm = bash.bash_o("virsh list | grep -E 'running|paused' | awk '{print $2}'").strip().split()
                if running_vm != [] and running_vm[0] != "":
                    for vm in running_vm:
                        bash.bash_r("virsh destroy %s" % vm)
                r = bash.bash_r("drbdadm down all")
                if r == 0:
                    bash.bash_r("mkdir -p %s" % BACKUP_DIR)
                    bash.bash_r("mv /etc/drbd.d/*.res %s" % BACKUP_DIR)

                mini_cache_volume_mount_dir = "/var/lib/zstack/colo/cachevolumes/"
                linux.umount_by_path(mini_cache_volume_mount_dir)
                linux.rm_dir_force(mini_cache_volume_mount_dir)
                lvm.wipe_fs(diskPaths, vgUuid)
                newDiskPaths = set()
                for disk in disks:
                    newDiskPaths.add(disk.get_path())
                diskPaths = newDiskPaths

            cmd = shell.ShellCmd("vgcreate -qq --addtag '%s::%s::%s::%s' --metadatasize %s %s %s" %
                                 (INIT_TAG, hostUuid, time.time(), linux.get_hostname(),
                                  DEFAULT_VG_METADATA_SIZE, vgUuid, " ".join(diskPaths)))
            cmd(is_exception=False)
            logger.debug("created vg %s, ret: %s, stdout: %s, stderr: %s" %
                         (vgUuid, cmd.return_code, cmd.stdout, cmd.stderr))
            if cmd.return_code == 0 and find_vg(vgUuid, False) is True:
                return True
            try:
                if find_vg(vgUuid) is True:
                    return True
            except RetryException as ee:
                raise Exception("can not find vg %s with disks: %s and create vg return: %s %s %s " %
                                (vgUuid, diskPaths, cmd.return_code, cmd.stdout, cmd.stderr))
            except Exception as ee:
                raise ee
        except Exception as e:
            raise e

        return False

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE, debug=True)
    def connect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConnectRsp()
        diskPaths = set()
        disks = set()

        def config_lvm(enableLvmetad=False):
            lvm.backup_lvm_config()
            lvm.reset_lvm_conf_default()
            if enableLvmetad:
                lvm.config_lvm_by_sed("use_lvmetad", "use_lvmetad=1", ["lvm.conf", "lvmlocal.conf"])
            else:
                lvm.config_lvm_by_sed("use_lvmetad", "use_lvmetad=0", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("issue_discards", "issue_discards=1", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("reserved_stack", "reserved_stack=256", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("reserved_memory", "reserved_memory=131072", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("thin_pool_autoextend_threshold", "thin_pool_autoextend_threshold=80", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("snapshot_autoextend_threshold", "snapshot_autoextend_threshold=80", ["lvm.conf", "lvmlocal.conf"])

            lvm.config_lvm_filter(["lvm.conf", "lvmlocal.conf"], True)

        def config_drbd():
            bash.bash_r("sed -i 's/usage-count yes/usage-count no/g' /etc/drbd.d/global_common.conf")

        def build_mini_storage_adm_link():
            bash.bash_r("rm -f /usr/local/bin/mini-storage-adm && ln -s `which drbdadm` /usr/local/bin/mini-storage-adm")

        drbd.install_drbd()
        config_lvm()
        config_drbd()
        build_mini_storage_adm_link()
        for diskId in cmd.diskIdentifiers:
            disk = CheckDisk(diskId)
            disks.add(disk)
            diskPaths.add(disk.get_path())
        logger.debug("find/create vg %s ..." % cmd.vgUuid)
        self.create_vg_if_not_found(cmd.vgUuid, disks, diskPaths, cmd.hostUuid, cmd.forceWipe)
        self.create_thin_pool_if_not_found(cmd.vgUuid, INIT_POOL_RATIO)
        drbd.up_all_resouces()

        if lvm.lvm_check_operation(cmd.vgUuid) is False:
            logger.warn("lvm operation test failed!")

        lvm.clean_vg_exists_host_tags(cmd.vgUuid, cmd.hostUuid, HEARTBEAT_TAG)
        lvm.add_vg_tag(cmd.vgUuid, "%s::%s::%s::%s" % (HEARTBEAT_TAG, cmd.hostUuid, time.time(), linux.get_hostname()))

        if cmd.fencerAddress:
            lvm.clean_vg_exists_host_tags(cmd.vgUuid, '\'\'', FENCER_TAG)
            lvm.add_vg_tag(cmd.vgUuid, "%s::%s" % (FENCER_TAG, cmd.fencerAddress))
        lvm.clean_vg_exists_host_tags(cmd.vgUuid, '\'\'', MANAGEMENT_TAG)
        lvm.add_vg_tag(cmd.vgUuid, "%s::%s" % (MANAGEMENT_TAG, cmd.magementAddress))
        self.generate_fencer(cmd.peerManagementAddress, cmd.peerSshUsername, cmd.peerSshPassword)

        if cmd.storageNetworkCidr is not None:
            nics = linux.get_nics_by_cidr(cmd.storageNetworkCidr)
            if len(nics) != 0:
                rsp.storageNetworkAddress = nics[0].values()[0]
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.vgLvmUuid = lvm.get_vg_lvm_uuid(cmd.vgUuid)
        rsp.hostUuid = cmd.hostUuid
        logger.debug("mini primary storage[uuid: %s] on host[uuid: %s] connected" % (cmd.vgUuid, cmd.hostUuid))
        return jsonobject.dumps(rsp)

    @staticmethod
    @bash.in_bash
    def generate_fencer(peer_addr, peer_username, peer_password):
        def configure_ssh_key():
            bash.bash_roe("/bin/rm %s*" % mini_fencer.MINI_FENCER_KEY)
            bash.bash_roe("ssh-keygen -P \"\" -f %s" % mini_fencer.MINI_FENCER_KEY)
            ssh_pswd_file = linux.write_to_temp_file(peer_password)
            r, o, e = bash.bash_roe("sshpass -f %s ssh-copy-id -i %s %s@%s" % (ssh_pswd_file, mini_fencer.MINI_FENCER_KEY, peer_username, peer_addr))
            linux.write_to_temp_file(ssh_pswd_file)
            if r == 0:
                return

        configure_ssh_key()
        current_dir = os.path.split(os.path.realpath(__file__))[0]
        fencer_path = "%s/mini_fencer.py" % current_dir
        bash.bash_roe("sed -i 's/^PEER_USERNAME = .*$/PEER_USERNAME = \"%s\"/g' %s" % (peer_username, fencer_path))
        bash.bash_roe("sed -i 's/^PEER_MGMT_ADDR = .*$/PEER_MGMT_ADDR = \"%s\"/g' %s" % (peer_addr, fencer_path))
        bash.bash_roe("cp %s /usr/lib/drbd/mini_fencer.py" % fencer_path)
        linux.sync_file(fencer_path)
        linux.sync_file("/usr/lib/drbd/mini_fencer.py")
        os.chmod("/usr/lib/drbd/mini_fencer.py", 0o755)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def disconnect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
        def find_vg(vgUuid):
            cmd = shell.ShellCmd("vgs --nolocking %s -otags | grep %s" % (vgUuid, INIT_TAG))
            cmd(is_exception=False)
            if cmd.return_code == 0:
                return True

            logger.debug("can not find vg %s with tag %s" % (vgUuid, INIT_TAG))
            cmd = shell.ShellCmd("vgs %s" % vgUuid)
            cmd(is_exception=False)
            if cmd.return_code == 0:
                logger.warn("found vg %s without tag %s" % (vgUuid, INIT_TAG))
                return True

            raise RetryException("can not find vg %s with or without tag %s" % (vgUuid, INIT_TAG))

        @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
        def deactive_drbd_resouces_on_vg(vgUuid):
            active_lvs = lvm.list_local_active_lvs(vgUuid)
            if len(active_lvs) == 0:
                return
            drbd_resources = [drbd.DrbdResource(lv.split("/")[-1]) for lv in active_lvs]
            for r in drbd_resources:
                r.destroy()
            logger.warn("active lvs %s will be deactivate" % active_lvs)
            lvm.deactive_lv(vgUuid)
            active_lvs = lvm.list_local_active_lvs(vgUuid)
            if len(active_lvs) != 0:
                raise RetryException("lvs [%s] still active, retry deactive again" % active_lvs)

        try:
            find_vg(cmd.vgUuid)
        except RetryException:
            logger.debug("can not find vg %s; return success" % cmd.vgUuid)
            return jsonobject.dumps(rsp)
        except Exception as e:
            raise e

        deactive_drbd_resouces_on_vg(cmd.vgUuid)
        lvm.clean_vg_exists_host_tags(cmd.vgUuid, cmd.hostUuid, HEARTBEAT_TAG)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def add_disk(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        disk = CheckDisk(cmd.diskUuid)
        command = shell.ShellCmd("vgs --nolocking %s -otags | grep %s" % (cmd.vgUuid, INIT_TAG))
        command(is_exception=False)
        if command.return_code != 0:
            self.create_vg_if_not_found(cmd.vgUuid, set(disk), [disk.get_path()], cmd.hostUuid, cmd.forceWipe)
        else:
            if cmd.forceWipe is True:
                lvm.wipe_fs([disk.get_path()], cmd.vgUuid)
            lvm.add_pv(cmd.vgUuid, disk.get_path(), DEFAULT_VG_METADATA_SIZE)

        rsp = AgentRsp
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def resize_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        install_abs_path = get_absolute_path_from_install_path(cmd.installPath)
        rsp = ResizeVolumeRsp()

        if not cmd.drbd:
            lvm.resize_lv_from_cmd(install_abs_path, cmd.size, cmd)
            if cmd.isFileSystem:
                lvm.active_lv(install_abs_path)
                mountPath = self.convertInstallPathToMount(cmd.installPath)
                if not os.path.exists(mountPath):
                    linux.mkdir(mountPath)

                if not linux.is_mounted(cmd.mountPath):
                    linux.mount(install_abs_path, mountPath)

                cache_volume_path = os.path.join(mountPath, mountPath.rsplit('/', 1)[-1])
                shell.call("qemu-img resize %s %s" % (cache_volume_path, cmd.size))
                rsp.size = linux.qcow2_virtualsize(cache_volume_path)
                linux.umount(mountPath)
                linux.rmdir_if_empty(mountPath)
                lvm.deactive_lv(install_abs_path)
            else:
                rsp.size = linux.qcow2_virtualsize(install_abs_path)
            return jsonobject.dumps(rsp)

        r = drbd.DrbdResource(cmd.installPath.split("/")[-1])
        r._init_from_disk(install_abs_path)
        with drbd.OperateDrbd(r):
            r.resize()

        with drbd.OperateDrbd(r):
            fmt = linux.get_img_fmt(r.get_dev_path())
            if not cmd.live and fmt == 'qcow2':
                shell.call("qemu-img resize %s %s" % (r.get_dev_path(), cmd.size))
            ret = linux.qcow2_virtualsize(r.get_dev_path())
        rsp.size = ret
        rsp._init_from_drbd(r)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VolumeRsp()
        template_abs_path_cache = get_absolute_path_from_install_path(cmd.templatePathInCache)
        install_abs_path = get_absolute_path_from_install_path(cmd.installPath)

        drbdResource = drbd.DrbdResource(self.get_name_from_installPath(cmd.installPath), False)
        drbdResource.config.local_host.hostname = cmd.local_host_name
        drbdResource.config.local_host.disk = install_abs_path
        drbdResource.config.local_host.minor = cmd.local_host_port - DRBD_START_PORT
        drbdResource.config.local_host.address = "%s:%s" % (cmd.local_address, cmd.local_host_port)

        drbdResource.config.remote_host.hostname = cmd.remote_host_name
        drbdResource.config.remote_host.disk = install_abs_path
        drbdResource.config.remote_host.minor = cmd.remote_host_port - DRBD_START_PORT
        drbdResource.config.remote_host.address = "%s:%s" % (cmd.remote_address, cmd.remote_host_port)

        drbdResource.config.write_config()
        virtual_size = linux.qcow2_virtualsize(template_abs_path_cache)

        try:
            lvm.qcow2_lv_recursive_active(template_abs_path_cache, lvm.LvmlockdLockType.SHARE)
            if not lvm.lv_exists(install_abs_path):
                lvm.create_lv_from_cmd(install_abs_path, virtual_size, cmd,
                                       "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), False)
            lvm.active_lv(install_abs_path)
            drbdResource.initialize(cmd.init, cmd, template_abs_path_cache)
        except Exception as e:
            drbdResource.destroy()
            lvm.delete_lv(install_abs_path)
            raise e

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp._init_from_drbd(drbdResource)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if cmd.folder:
            raise Exception("not support this operation")

        self.do_delete_bits(cmd.path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    def do_delete_bits(self, path):
        install_abs_path = get_absolute_path_from_install_path(path)
        if lvm.has_lv_tag(install_abs_path, IMAGE_TAG):
            logger.info('deleting lv image: ' + install_abs_path)
            if lvm.lv_exists(install_abs_path):
                lvm.delete_image(install_abs_path, IMAGE_TAG, deactive=False)
        else:
            linux.umount_by_url(install_abs_path)

            logger.info('deleting lv volume: ' + install_abs_path)
            r = drbd.DrbdResource(self.get_name_from_installPath(path))
            if r.exists is True:
                r.destroy()
            lvm.delete_lv(install_abs_path, deactive=False)
        lvm.delete_snapshots(install_abs_path)

    @kvmagent.replyerror
    def get_qcow2_reference(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        rsp = GetQCOW2ReferenceRsp()
        rsp.referencePaths = []
        real_path = get_absolute_path_from_install_path(cmd.path)
        for f in lvm.list_local_active_lvs(cmd.vgUuid):
            try:
                backing_file = linux.qcow2_direct_get_backing_file(f)
                if backing_file in [real_path ,cmd.path]:
                    rsp.referencePaths.append(f)
            except Exception as e:
                logger.warn(e)
                continue
        for f in bash.bash_o("ls -l /dev/drbd* | grep -E '^b' | awk '{print $NF}'").splitlines():
            f = f.strip()
            if f == "":
                continue
            try:
                if linux.qcow2_get_backing_file(f) in [real_path, cmd.path]:
                    rsp.referencePaths.append(f)
            except Exception as e:
                logger.warn(e)
                continue
        logger.debug("find qcow2 %s referencess: %s" % (real_path, rsp.referencePaths))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def flush_cache(self, req):
        shell.call("/opt/MegaRAID/MegaCli/MegaCli64 -AdpCacheFlush -aAll")
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def create_template_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VolumeRsp()
        volume_abs_path = get_absolute_path_from_install_path(cmd.volumePath)
        snap_name = cmd.installPath.split("/")[-1]

        r = drbd.DrbdResource(volume_abs_path.split("/")[-1])
        with drbd.OperateDrbd(r):
            volume_snap_abs_path = lvm.create_lvm_snapshot(volume_abs_path, snapName=snap_name, drbd_path=r.get_dev_path())
            rsp.actualSize = lvm.get_lv_size(volume_snap_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

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
        if cmd.size is not None and cmd.provisioning is not None:
            lvm.create_lv_from_cmd(self.convertInstallPathToAbsolute(cmd.primaryStorageInstallPath), cmd.size, cmd,
                                   "%s::%s::%s" % (IMAGE_TAG, cmd.hostUuid, time.time()), False)
            lvm.active_lv(self.convertInstallPathToAbsolute(cmd.primaryStorageInstallPath))
        self.imagestore_client.download_from_imagestore(cmd.mountPoint, cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)
        rsp = AgentRsp()
        return jsonobject.dumps(rsp)

    @staticmethod
    def convertInstallPathToAbsolute(path):
        # type: (str) -> str
        return path.replace("mini:/", "/dev")

    @staticmethod
    def convertInstallPathToMount(path):
        # type: (string) -> string
        return path.replace("mini:/", "/tmp")

    @kvmagent.replyerror
    def create_empty_cache_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VolumeRsp()

        install_abs_path = get_absolute_path_from_install_path(cmd.installPath)
        try:
            if not lvm.lv_exists(install_abs_path):
                lvm.create_lv_from_cmd(install_abs_path, cmd.size, cmd,
                                       "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), False)
                lvm.active_lv(install_abs_path)
                shell.call("mkfs.ext4 -F %s" % install_abs_path)
                mountPath = self.convertInstallPathToMount(cmd.installPath)
                if not os.path.exists(mountPath):
                    linux.mkdir(mountPath)

                if not linux.is_mounted(cmd.mountPath):
                    linux.mount(install_abs_path, mountPath)

                linux.qcow2_create(mountPath + '/' + mountPath.rsplit('/', 1)[-1], cmd.size)
                linux.umount(mountPath)
                linux.rmdir_if_empty(mountPath)
                lvm.deactive_lv(install_abs_path)
        except Exception as e:
            lvm.delete_lv(install_abs_path)
            logger.debug('failed to create empty volume[uuid:%s, size:%s] at %s' %
                         (cmd.volumeUuid, cmd.size, cmd.installPath))
            raise e

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s and mount' %
                     (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_filesystem(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UploadBitsToFileSystemRsp()
        vol_path = self.convertInstallPathToAbsolute(cmd.srcInstallPath)
        dst_dir = os.path.dirname(cmd.dstInstallPath)

        if not cmd.skipIfExisting:
            linux.rm_dir_force(dst_dir)

        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir, 0755)
        linux.upload_chain_to_filesystem(MiniFileConverter(), vol_path, dst_dir, overwrite=not cmd.skipIfExisting)
        rsp.totalSize = linux.get_filesystem_folder_size(dst_dir)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def download_from_filesystem(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DownloadBitsFromFileSystemRsp()
        dst_dir = os.path.dirname(self.convertInstallPathToAbsolute(cmd.dstInstallPath))
        chain_info = linux.download_chain_from_filesystem(MiniFileConverter(cmd=cmd), cmd.srcInstallPath, dst_dir,
                                                          overwrite=not cmd.skipIfExisting)

        for info in chain_info:
            rsp.downloadedInfos.append(LvInfo(install_path=info[0], size=info[1]))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def sync_backing_chain(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        remote_hostname = cmd.remoteHostname
        # rsync cannot satisfy without --keep-links(it is supposed to be similar to --keep-dirlinks)
        for info in cmd.backingFileInfos:
            if not lvm.lv_exists(info.installPath):
                lvm.create_lv_from_cmd(info.installPath, info.size, cmd,
                                   "%s::%s::%s" % (IMAGE_TAG, cmd.hostUuid, time.time()), False)
            lvm.active_lv(info.installPath)
            sync_command = "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s " \
                           "dd if=%s bs=1M | dd of=%s bs=1M" % \
                           (remote_hostname, info.installPath, info.installPath)
            shell.call(sync_command)

        rsp = AgentRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def discard_resource(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VolumeRsp()
        drbd_resource = drbd.DrbdResource(cmd.resourceUuid)
        drbd_resource.discard()

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp._init_from_drbd(drbd_resource)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def force_connect_resource(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VolumeRsp()
        drbd_resource = drbd.DrbdResource(cmd.resourceUuid)
        drbd_resource.force_connect()

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp._init_from_drbd(drbd_resource)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VolumeRsp()

        install_abs_path = get_absolute_path_from_install_path(cmd.installPath)
        drbdResource = drbd.DrbdResource(self.get_name_from_installPath(cmd.installPath), False)
        drbdResource.config.local_host.hostname = cmd.local_host_name
        drbdResource.config.local_host.disk = install_abs_path
        drbdResource.config.local_host.minor = cmd.local_host_port - DRBD_START_PORT
        drbdResource.config.local_host.address = "%s:%s" % (cmd.local_address, cmd.local_host_port)

        drbdResource.config.remote_host.hostname = cmd.remote_host_name
        drbdResource.config.remote_host.disk = install_abs_path
        drbdResource.config.remote_host.minor = cmd.remote_host_port - DRBD_START_PORT
        drbdResource.config.remote_host.address = "%s:%s" % (cmd.remote_address, cmd.remote_host_port)

        drbdResource.config.write_config()

        try:
            if cmd.backingFile:
                backing_abs_path = get_absolute_path_from_install_path(cmd.backingFile)
                virtual_size = linux.qcow2_virtualsize(backing_abs_path)

                lvm.create_lv_from_cmd(install_abs_path, virtual_size, cmd,
                                       "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), False)
                lvm.active_lv(install_abs_path)
                drbdResource.initialize(cmd.init, cmd, backing_abs_path)
            elif not lvm.lv_exists(install_abs_path):
                lvm.create_lv_from_cmd(install_abs_path, cmd.size, cmd,
                                       "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), False)
                lvm.active_lv(install_abs_path)
                drbdResource.initialize(cmd.init, cmd)
        except Exception as e:
            drbdResource.destroy()
            lvm.delete_lv(install_abs_path)
            logger.debug('failed to create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
            raise e

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp._init_from_drbd(drbdResource)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_secondary_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VolumeRsp()

        install_abs_path = get_absolute_path_from_install_path(cmd.installPath)
        drbdResource = drbd.DrbdResource(self.get_name_from_installPath(cmd.installPath), False)

        if not drbdResource.exists or drbdResource.config.local_host.minor != str(cmd.local_host_port - DRBD_START_PORT):
            drbdResource.config.local_host.hostname = cmd.local_host_name
            drbdResource.config.local_host.disk = install_abs_path
            drbdResource.config.local_host.minor = cmd.local_host_port - DRBD_START_PORT
            drbdResource.config.local_host.address = "%s:%s" % (cmd.local_address, cmd.local_host_port)

            drbdResource.config.remote_host.hostname = cmd.remote_host_name
            drbdResource.config.remote_host.disk = install_abs_path
            drbdResource.config.remote_host.minor = cmd.remote_host_port - DRBD_START_PORT
            drbdResource.config.remote_host.address = "%s:%s" % (cmd.remote_address, cmd.remote_host_port)

            drbdResource.config.write_config()

        try:
            if not lvm.lv_exists(install_abs_path):
                lvm.create_lv_from_cmd(install_abs_path, cmd.size, cmd,
                                   "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()), False)
                lvm.active_lv(install_abs_path)
                drbdResource.initialize(primary=False, cmd=cmd)
        except Exception as e:
            drbdResource.destroy()
            lvm.delete_lv(install_abs_path)
            logger.debug('failed to create secondary volume[uuid:%s, size:%s] at %s' % (cmd.resourceUuid, cmd.size, cmd.installPath))
            raise e

        logger.debug('successfully create secondary volume[uuid:%s, size:%s] at %s' % (cmd.resourceUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp._init_from_drbd(drbdResource)
        return jsonobject.dumps(rsp)


    @staticmethod
    def get_name_from_installPath(path):
        return path.split("/")[3]

    @kvmagent.replyerror
    def convert_image_to_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VolumeRsp()

        install_abs_path = get_absolute_path_from_install_path(cmd.primaryStorageInstallPath)
        lvm.active_lv(install_abs_path)
        lvm.clean_lv_tag(install_abs_path, IMAGE_TAG)
        lvm.add_lv_tag(install_abs_path, "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
        lvm.delete_lv_meta(install_abs_path)

        drbdResource = drbd.DrbdResource(install_abs_path.split("/")[-1], False)
        drbdResource.config.local_host.hostname = cmd.local_host_name
        drbdResource.config.local_host.disk = install_abs_path
        drbdResource.config.local_host.minor = cmd.local_host_port - DRBD_START_PORT
        drbdResource.config.local_host.address = "%s:%s" % (cmd.local_address, cmd.local_host_port)

        drbdResource.config.remote_host.hostname = cmd.remote_host_name
        drbdResource.config.remote_host.disk = install_abs_path
        drbdResource.config.remote_host.minor = cmd.remote_host_port - DRBD_START_PORT
        drbdResource.config.remote_host.address = "%s:%s" % (cmd.remote_address, cmd.remote_host_port)

        drbdResource.config.write_config()
        drbdResource.initialize(False, None, skip_clear_bits=cmd.init)

        rsp._init_from_drbd(drbdResource)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        if cmd.path is not None:
            install_abs_path = get_absolute_path_from_install_path(cmd.path)
            rsp.existing = lvm.lv_exists(install_abs_path)
        else:
            rsp = self.replications_status()

        if cmd.vgUuid is not None and lvm.vg_exists(cmd.vgUuid):
            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, False)

        if cmd.peerIps is None:
            return jsonobject.dumps(rsp)

        # successCount = 0
        # for ip in cmd.peerIps:
        #     if self.test_network_ok_to_peer(ip):
        #         successCount += 1

        # if successCount == cmd.peerIps:
        rsp.storageNetworkStatus = "Connected"
        # elif successCount > 0:
        #     rsp.storageNetworkStatus = "PartialConnected"
        # else:
        #     rsp.storageNetworkStatus = "Disconnected"

        return jsonobject.dumps(rsp)


    @staticmethod
    def replications_status():
        # type: () -> CheckBitsRsp
        r = CheckBitsRsp()
        raw = linux.read_file("/proc/drbd")

        for line in raw.splitlines():
            try:
                splited = line.strip().split(" ")
                if ": cs:" in line:
                    info = ReplicationInformation()
                    info.minor = splited[0].split(":")[0]
                    info.networkStatus = splited[1].split(":")[1]
                    info.diskStatus = splited[3].split(":")[1].split("/")[0]
                    info.role = splited[2].split(":")[1].split("/")[0]
                    configPath = bash.bash_o("grep 'minor %s;' /etc/drbd.d/*.res -l | awk -F '.res' '{print $1}'" % info.minor).strip()
                    info.name = configPath.split("/")[-1]
                    size = lvm.get_lv_size(
                        bash.bash_o("grep -E 'disk .*/dev' %s.res | head -n1  | awk '{print $2}'" % configPath).strip().strip(";"))
                    if size != '':
                        info.size = int(size)

                    r.replications[info.name] = info
            except Exception as e:
                logger.warn("exception %s when get info of %s" % (e, line))

        logger.debug(jsonobject.dumps(r.replications))
        return r


    @staticmethod
    def handle_cache_volume(drbd_role, mount_path, install_abs_path):
        if drbd_role == drbd.DrbdRole.Primary:
            lvm.active_lv(install_abs_path)

            if not os.path.exists(mount_path):
                linux.mkdir(mount_path)

            if not linux.is_mounted(mount_path, install_abs_path):
                linux.mount(install_abs_path, mount_path)

            logger.debug("successfully mount %s to %s" % (install_abs_path, mount_path))
        else:
            if linux.is_mounted(mount_path):
                linux.umount(mount_path)

            lvm.deactive_lv(install_abs_path)


    @kvmagent.replyerror
    def active_lv(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ActiveRsp()
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, raise_exception=False)

        install_abs_path = get_absolute_path_from_install_path(cmd.installPath)
        if lvm.has_lv_tag(install_abs_path, IMAGE_TAG):
            lvm.qcow2_lv_recursive_active(install_abs_path, lvm.LvmlockdLockType.SHARE)
            return jsonobject.dumps(rsp)

        if cmd.mountPath:
            self.handle_cache_volume(cmd.role, cmd.mountPath, install_abs_path)
            return jsonobject.dumps(rsp)

        drbdResource = drbd.DrbdResource(self.get_name_from_installPath(cmd.installPath))
        if cmd.role == drbd.DrbdRole.Secondary:
            drbdResource.demote()
            rsp._init_from_drbd(drbdResource)
            return jsonobject.dumps(rsp)

        if drbdResource.exists is False:
            raise Exception("can not find volume %s" % cmd.installPath)

        if cmd.checkPeer and drbdResource.get_remote_role() == drbd.DrbdRole.Primary:
            raise Exception("remote is also in primary role, can not promote")

        # if drbdResource.get_dstate() != "UpToDate":
        #    raise Exception("local data is not uptodate, can not promote")

        lvm.qcow2_lv_recursive_active(install_abs_path, lvm.LvmlockdLockType.EXCLUSIVE)
        try:
            force = self.test_network_ok_to_peer(drbdResource.config.remote_host.address.split(":")[0]) is False
            drbdResource.promote(force=force, single=cmd.single)
        except Exception as e:
            if not cmd.force:
                raise e
            if self.test_network_ok_to_peer(drbdResource.config.remote_host.address.split(":")[0]):
                raise Exception("storage network address %s still connected, wont force promote" %
                                drbdResource.config.remote_host.address.split(":")[0])
            if cmd.vmNics:
                for vmNic in cmd.vmNics:
                    if self.test_network_ok_to_peer(vmNic.ipAddress, vmNic.bridgeName):
                        raise Exception("could arping %s via %s, it may split brain, wont proceed force promote"
                                        % (vmNic.ipAddress, vmNic.bridgeName))
            snap_path = None
            try:
                snap_path = lvm.create_lvm_snapshot(install_abs_path)
                drbdResource.promote(True, 2, 2)
                rsp.snapPath = snap_path
            except Exception as ee:
                if snap_path is not None:
                    lvm.delete_lv(snap_path)
                raise ee

        rsp._init_from_drbd(drbdResource)
        return jsonobject.dumps(rsp)

    @staticmethod
    @bash.in_bash
    def test_network_ok_to_peer(peer_address, via_dev=None):
        if not via_dev:
            via_dev = iproute.get_routes_by_ip(peer_address)[0].get_related_link_device().ifname
        for i in range(5):
            recv = bash.bash_r("timeout 2 arping -w 1 -b %s -I %s -c 1" % (peer_address, via_dev))
            if recv == 0:
                return True
        return False

    @kvmagent.replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeSizeRsp()

        install_abs_path = get_absolute_path_from_install_path(cmd.installPath)
        r = drbd.DrbdResource(cmd.installPath.split("/")[-1])
        with drbd.OperateDrbd(r):
            rsp.size = linux.qcow2_virtualsize(r.get_dev_path())
        rsp.actualSize = lvm.get_lv_size(install_abs_path)
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp._init_from_drbd(r)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()
        snapshot_abs_path = get_absolute_path_from_install_path(cmd.snapshotInstallPath)
        install_abs_path = get_absolute_path_from_install_path(cmd.installPath)
        rsp.size = False
        rsp.error = "not supported yet!"

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return rsp

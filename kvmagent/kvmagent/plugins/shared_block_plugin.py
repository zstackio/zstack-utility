import os.path
import re
import random
import time

from zstacklib.utils import lock

from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import lvm
from zstacklib.utils import bash
import zstacklib.utils.uuidhelper as uuidhelper

logger = log.get_logger(__name__)
LOCK_FILE = "/var/run/zstack/sharedblock.lock"
INIT_TAG = "zs::sharedblock::init"
HEARTBEAT_TAG = "zs::sharedblock::heartbeat"
VOLUME_TAG = "zs::sharedblock::volume"
IMAGE_TAG = "zs::sharedblock::image"
DEFAULT_VG_METADATA_SIZE = "2g"
DEFAULT_SANLOCK_LV_SIZE = "1024"


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None
        self.totalCapacity = None
        self.availableCapacity = None


class ConnectRsp(AgentRsp):
    def __init__(self):
        super(ConnectRsp, self).__init__()
        self.isFirst = False
        self.hostId = None


class RevertVolumeFromSnapshotRsp(AgentRsp):
    def __init__(self):
        super(RevertVolumeFromSnapshotRsp, self).__init__()
        self.newVolumeInstallPath = None
        self.size = None


class MergeSnapshotRsp(AgentRsp):
    def __init__(self):
        super(MergeSnapshotRsp, self).__init__()
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


class OfflineMergeSnapshotRsp(AgentRsp):
    def __init__(self):
        super(OfflineMergeSnapshotRsp, self).__init__()
        self.deleted = False


class GetVolumeSizeRsp(AgentRsp):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None


class RetryException(Exception):
    pass


class GetBlockDevicesRsp(AgentRsp):
    blockDevices = None  # type: list[lvm.SharedBlockCandidateStruct]

    def __init__(self):
        super(GetBlockDevicesRsp, self).__init__()
        self.blockDevices = None


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

    def get_path(self):
        o = self.check_disk_by_wwid()
        if o is not None:
            return o

        o = self.check_disk_by_uuid()
        if o is not None:
            return o

        raise Exception("can not find disk with %s as wwid, uuid or wwn, "
                        "or multiple disks qualify but no mpath device found" % self.identifier)

    def rescan(self, disk_name=None):
        """

        :type disk_name: str
        """
        if disk_name is None:
            disk_name = self.get_path().split("/")[-1]

        def rescan_slave(slave):
            _cmd = shell.ShellCmd("echo 1 > /sys/block/%s/device/rescan" % slave)
            _cmd(is_exception=True)
            logger.debug("rescaned disk %s (wwid: %s), return code: %s, stdout %s, stderr: %s" %
                         (slave, self.identifier, _cmd.return_code, _cmd.stdout, _cmd.stderr))

        if lvm.is_multipath(disk_name):
            # disk name is dm-xx when multi path
            slaves = shell.call("ls /sys/class/block/%s/slaves/" % disk_name).strip().split("\n")
            if slaves is None or len(slaves) == 0:
                logger.debug("can not get any slaves of multipath device %s" % disk_name)
                rescan_slave(disk_name)
            else:
                for s in slaves:
                    rescan_slave(s)
                cmd = shell.ShellCmd("multipathd resize map %s" % disk_name)
                cmd(is_exception=True)
                logger.debug("resized multipath device %s, return code: %s, stdout %s, stderr: %s" %
                             (disk_name, cmd.return_code, cmd.stdout, cmd.stderr))
        else:
            rescan_slave(disk_name)

        cmd = shell.ShellCmd("pvresize /dev/%s" % disk_name)
        cmd(is_exception=True)
        logger.debug("resized pv %s (wwid: %s), return code: %s, stdout %s, stderr: %s" %
                     (disk_name, self.identifier, cmd.return_code, cmd.stdout, cmd.stderr))

    def check_disk_by_uuid(self):
        for cond in ['TYPE=\\\"mpath\\\"', '\"\"']:
            cmd = shell.ShellCmd("lsblk --pair -p -o NAME,TYPE,FSTYPE,LABEL,UUID,VENDOR,MODEL,MODE,WWN | "
                                 " grep %s | grep %s | sort | uniq" % (cond, self.identifier))
            cmd(is_exception=False)
            if len(cmd.stdout.splitlines()) == 1:
                pattern = re.compile(r'\/dev\/[^ \"]*')
                return pattern.findall(cmd.stdout)[0]

    def check_disk_by_wwid(self):
        for cond in ['dm-uuid-mpath-', '']:
            cmd = shell.ShellCmd("readlink -e /dev/disk/by-id/%s%s" % (cond, self.identifier))
            cmd(is_exception=False)
            if cmd.return_code == 0:
                return cmd.stdout.strip()


class SharedBlockPlugin(kvmagent.KvmAgent):

    CONNECT_PATH = "/sharedblock/connect"
    DISCONNECT_PATH = "/sharedblock/disconnect"
    CREATE_VOLUME_FROM_CACHE_PATH = "/sharedblock/createrootvolume"
    DELETE_BITS_PATH = "/sharedblock/bits/delete"
    CREATE_TEMPLATE_FROM_VOLUME_PATH = "/sharedblock/createtemplatefromvolume"
    UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH = "/sharedblock/sftp/upload"
    DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH = "/sharedblock/sftp/download"
    UPLOAD_BITS_TO_IMAGESTORE_PATH = "/sharedblock/imagestore/upload"
    COMMIT_BITS_TO_IMAGESTORE_PATH = "/sharedblock/imagestore/commit"
    DOWNLOAD_BITS_FROM_IMAGESTORE_PATH = "/sharedblock/imagestore/download"
    REVERT_VOLUME_FROM_SNAPSHOT_PATH = "/sharedblock/volume/revertfromsnapshot"
    MERGE_SNAPSHOT_PATH = "/sharedblock/snapshot/merge"
    OFFLINE_MERGE_SNAPSHOT_PATH = "/sharedblock/snapshot/offlinemerge"
    CREATE_EMPTY_VOLUME_PATH = "/sharedblock/volume/createempty"
    CHECK_BITS_PATH = "/sharedblock/bits/check"
    RESIZE_VOLUME_PATH = "/sharedblock/volume/resize"
    CONVERT_IMAGE_TO_VOLUME = "/sharedblock/image/tovolume"
    CHANGE_VOLUME_ACTIVE_PATH = "/sharedblock/volume/active"
    GET_VOLUME_SIZE_PATH = "/sharedblock/volume/getsize"
    CHECK_DISKS_PATH = "/sharedblock/disks/check"
    ADD_SHARED_BLOCK = "/sharedblock/disks/add"
    MIGRATE_DATA_PATH = "/sharedblock/volume/migrate"
    GET_BLOCK_DEVICES_PATH = "/sharedblock/blockdevices"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.DISCONNECT_PATH, self.disconnect)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.create_root_volume)
        http_server.register_async_uri(self.DELETE_BITS_PATH, self.delete_bits)
        http_server.register_async_uri(self.CREATE_TEMPLATE_FROM_VOLUME_PATH, self.create_template_from_volume)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH, self.upload_to_sftp)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH, self.download_from_sftp)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_IMAGESTORE_PATH, self.upload_to_imagestore)
        http_server.register_async_uri(self.COMMIT_BITS_TO_IMAGESTORE_PATH, self.commit_to_imagestore)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_IMAGESTORE_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.REVERT_VOLUME_FROM_SNAPSHOT_PATH, self.revert_volume_from_snapshot)
        http_server.register_async_uri(self.MERGE_SNAPSHOT_PATH, self.merge_snapshot)
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

        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    @kvmagent.replyerror
    def check_disks(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        for diskUuid in cmd.sharedBlockUuids:
            disk = CheckDisk(diskUuid)
            path = disk.get_path()
            if cmd.rescan:
                disk.rescan(path.split("/")[-1])

        if cmd.vgUuid is not None and lvm.vg_exists(cmd.vgUuid):
            rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid, False)

        return jsonobject.dumps(rsp)

    @staticmethod
    def create_vg_if_not_found(vgUuid, diskPaths, hostUuid, forceWipe=False):
        @linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
        def find_vg(vgUuid):
            cmd = shell.ShellCmd("vgs %s -otags | grep %s" % (vgUuid, INIT_TAG))
            cmd(is_exception=False)
            if cmd.return_code != 0:
                raise RetryException("can not find vg %s with tag %s" % (vgUuid, INIT_TAG))
            return True

        try:
            find_vg(vgUuid)
        except RetryException as e:
            if forceWipe is True:
                lvm.wipe_fs(diskPaths)

            cmd = shell.ShellCmd("vgcreate -qq --shared --addtag '%s::%s::%s' --metadatasize %s %s %s" %
                                 (INIT_TAG, hostUuid, time.time(),
                                  DEFAULT_VG_METADATA_SIZE, vgUuid, " ".join(diskPaths)))
            cmd(is_exception=False)
            logger.debug("created vg %s, ret: %s, stdout: %s, stderr: %s" %
                         (vgUuid, cmd.return_code, cmd.stdout, cmd.stderr))
            if cmd.return_code == 0 and find_vg(vgUuid) is True:
                return True
            if find_vg(vgUuid) is False:
                raise Exception("can not find vg %s with disks: %s and create vg return: %s %s %s " %
                                (vgUuid, diskPaths, cmd.return_code, cmd.stdout, cmd.stderr))
        except Exception as e:
            raise e

        return False

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def connect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConnectRsp()
        diskPaths = set()

        def config_lvm(host_id):
            lvm.backup_lvm_config()
            lvm.reset_lvm_conf_default()
            lvm.config_lvm_by_sed("use_lvmlockd", "use_lvmlockd=1", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("use_lvmetad", "use_lvmetad=0", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("host_id", "host_id=%s" % host_id, ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("sanlock_lv_extend", "sanlock_lv_extend=%s" % DEFAULT_SANLOCK_LV_SIZE, ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("lvmlockd_lock_retries", "lvmlockd_lock_retries=6", ["lvm.conf", "lvmlocal.conf"])
            lvm.config_lvm_by_sed("issue_discards", "issue_discards=1", ["lvm.conf", "lvmlocal.conf"])

            lvm.config_sanlock_by_sed("sh_retries", "sh_retries=20")
            lvm.config_sanlock_by_sed("logfile_priority", "logfile_priority=7")
            lvm.config_sanlock_by_sed("renewal_read_extend_sec", "renewal_read_extend_sec=24")
            lvm.config_sanlock_by_sed("debug_renew", "debug_renew=1")
            lvm.config_sanlock_by_sed("use_watchdog", "use_watchdog=0")

        config_lvm(cmd.hostId)
        for diskUuid in cmd.sharedBlockUuids:
            disk = CheckDisk(diskUuid)
            diskPaths.add(disk.get_path())
        lvm.start_lvmlockd()
        lvm.check_gl_lock()
        rsp.isFirst = self.create_vg_if_not_found(cmd.vgUuid, diskPaths, cmd.hostUuid, cmd.forceWipe)
        lvm.start_vg_lock(cmd.vgUuid)
        lvm.clean_vg_exists_host_tags(cmd.vgUuid, cmd.hostUuid, HEARTBEAT_TAG)
        lvm.add_vg_tag(cmd.vgUuid, "%s::%s::%s" % (HEARTBEAT_TAG, cmd.hostUuid, time.time()))

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.hostId = lvm.get_running_host_id(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def disconnect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
        def find_vg(vgUuid):
            cmd = shell.ShellCmd("vgs %s -otags | grep %s" % (vgUuid, INIT_TAG))
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

        deactive_lvs_on_vg(cmd.vgUuid)
        lvm.clean_vg_exists_host_tags(cmd.vgUuid, cmd.hostUuid, HEARTBEAT_TAG)
        lvm.stop_vg_lock(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def add_disk(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        disk = CheckDisk(cmd.diskUuid)
        command = shell.ShellCmd("vgs %s -otags | grep %s" % (cmd.vgUuid, INIT_TAG))
        command(is_exception=False)
        if command.return_code != 0:
            self.create_vg_if_not_found(cmd.vgUuid, [disk.get_path()], cmd.hostUuid, cmd.forceWipe)
        else:
            lvm.check_gl_lock()
            if cmd.forceWipe is True:
                lvm.wipe_fs([disk.get_path()])
            lvm.add_pv(cmd.vgUuid, disk.get_path(), DEFAULT_VG_METADATA_SIZE)

        rsp = AgentRsp
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def resize_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        with lvm.RecursiveOperateLv(install_abs_path, shared=False):
            lvm.resize_lv(install_abs_path, cmd.size)
            if not cmd.live:
                shell.call("qemu-img resize %s %s" % (install_abs_path, cmd.size))
            ret = linux.qcow2_virtualsize(install_abs_path)

        rsp = ResizeVolumeRsp()
        rsp.size = ret
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        template_abs_path_cache = translate_absolute_path_from_install_path(cmd.templatePathInCache)
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        qcow2_options = self.calc_qcow2_option(self, cmd.qcow2Options, True)

        with lvm.RecursiveOperateLv(template_abs_path_cache, shared=True, skip_deactivate_tag=IMAGE_TAG):
            virtual_size = linux.qcow2_virtualsize(template_abs_path_cache)
            if not lvm.lv_exists(install_abs_path):
                lvm.create_lv_from_absolute_path(install_abs_path, virtual_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                linux.qcow2_clone_with_option(template_abs_path_cache, install_abs_path, qcow2_options)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if cmd.folder:
            raise Exception("not support this operation")

        install_abs_path = translate_absolute_path_from_install_path(cmd.path)
        if lvm.has_lv_tag(install_abs_path, IMAGE_TAG):
            logger.info('deleting lv image: ' + install_abs_path)
            lvm.delete_image(install_abs_path, IMAGE_TAG)
        else:
            logger.info('deleting lv volume: ' + install_abs_path)
            lvm.delete_lv(install_abs_path)
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_template_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        volume_abs_path = translate_absolute_path_from_install_path(cmd.volumePath)
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        if cmd.sharedVolume:
            lvm.do_active_lv(volume_abs_path, lvm.LvmlockdLockType.SHARE, True)

        with lvm.RecursiveOperateLv(volume_abs_path, shared=cmd.sharedVolume, skip_deactivate_tag=IMAGE_TAG):
            virtual_size = linux.qcow2_virtualsize(volume_abs_path)
            if not lvm.lv_exists(install_abs_path):
                lvm.create_lv_from_absolute_path(install_abs_path, virtual_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                linux.create_template(volume_abs_path, install_abs_path)
                logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))
                if cmd.compareQcow2 is True:
                    logger.debug("comparing qcow2 between %s and %s")
                    bash.bash_errorout("time qemu-img compare %s %s" % (volume_abs_path, install_abs_path))
                    logger.debug("confirmed qcow2 %s and %s are identical" % (volume_abs_path, install_abs_path))

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

        size = linux.sftp_get(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, install_abs_path, cmd.username, cmd.sshPort, True)
        if not lvm.lv_exists(install_abs_path):
            lvm.create_lv_from_absolute_path(install_abs_path, size,
                                             "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))

        with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
            linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, install_abs_path, cmd.username, cmd.sshPort)
        logger.debug('successfully download %s/%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))

        self.do_active_lv(cmd.primaryStorageInstallPath, cmd.lockType, False)

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
        self.imagestore_client.download_from_imagestore(cmd.mountPoint, cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)
        self.do_active_lv(cmd.primaryStorageInstallPath, cmd.lockType, True)
        rsp = AgentRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()
        snapshot_abs_path = translate_absolute_path_from_install_path(cmd.snapshotInstallPath)
        qcow2_options = self.calc_qcow2_option(self, cmd.qcow2Options, True)

        with lvm.RecursiveOperateLv(snapshot_abs_path, shared=True):
            size = linux.qcow2_virtualsize(snapshot_abs_path)
            new_volume_path = "/dev/%s/%s" % (cmd.vgUuid, uuidhelper.uuid())

            lvm.create_lv_from_absolute_path(new_volume_path, size,
                                             "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
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

        with lvm.RecursiveOperateLv(snapshot_abs_path, shared=True):
            virtual_size = linux.qcow2_virtualsize(snapshot_abs_path)
            if not lvm.lv_exists(workspace_abs_path):
                lvm.create_lv_from_absolute_path(workspace_abs_path, virtual_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(workspace_abs_path, shared=False, delete_when_exception=True):
                linux.create_template(snapshot_abs_path, workspace_abs_path)
                rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(workspace_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        rsp.actualSize = rsp.size
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offline_merge_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OfflineMergeSnapshotRsp()
        src_abs_path = translate_absolute_path_from_install_path(cmd.srcPath)
        dst_abs_path = translate_absolute_path_from_install_path(cmd.destPath)

        with lvm.RecursiveOperateLv(src_abs_path, shared=True):
            virtual_size = linux.qcow2_virtualsize(src_abs_path)
            if not lvm.lv_exists(dst_abs_path):
                lvm.create_lv_from_absolute_path(dst_abs_path, virtual_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.RecursiveOperateLv(dst_abs_path, shared=False):
                if not cmd.fullRebase:
                    linux.qcow2_rebase(src_abs_path, dst_abs_path)
                else:
                    tmp_lv = 'tmp_%s' % uuidhelper.uuid()
                    tmp_abs_path = os.path.join(os.path.dirname(dst_abs_path), tmp_lv)
                    logger.debug("creating temp lv %s" % tmp_abs_path)
                    lvm.create_lv_from_absolute_path(tmp_abs_path, virtual_size,
                                                     "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
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
            qcow2_options = self.calc_qcow2_option(self, cmd.qcow2Options, True)
            backing_abs_path = translate_absolute_path_from_install_path(cmd.backingFile)
            with lvm.RecursiveOperateLv(backing_abs_path, shared=True):
                virtual_size = linux.qcow2_virtualsize(backing_abs_path)
                if not lvm.lv_exists(install_abs_path):
                    lvm.create_lv_from_absolute_path(install_abs_path, virtual_size,
                                                     "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
                with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                    linux.qcow2_create_with_backing_file_and_option(backing_abs_path, install_abs_path, qcow2_options)
        elif not lvm.lv_exists(install_abs_path):
            qcow2_options = self.calc_qcow2_option(self, cmd.qcow2Options, False)
            lvm.create_lv_from_absolute_path(install_abs_path, cmd.size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(install_abs_path, shared=False, delete_when_exception=True):
                linux.qcow2_create_with_option(install_abs_path, cmd.size, qcow2_options)
                linux.qcow2_fill(0, 1048576, install_abs_path)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def convert_image_to_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.primaryStorageInstallPath)
        with lvm.OperateLv(install_abs_path, shared=False):
            lvm.clean_lv_tag(install_abs_path, IMAGE_TAG)
            lvm.add_lv_tag(install_abs_path, "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        install_abs_path = translate_absolute_path_from_install_path(cmd.path)
        rsp.existing = lvm.lv_exists(install_abs_path)
        return jsonobject.dumps(rsp)

    def do_active_lv(self, installPath, lockType, recursive):
        def handle_lv(lockType, fpath):
            if lockType > lvm.LvmlockdLockType.NULL:
                lvm.active_lv(fpath, lockType == lvm.LvmlockdLockType.SHARE)
            else:
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
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)

        self.do_active_lv(cmd.installPath, cmd.lockType, cmd.recursive)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeSizeRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        rsp.size = lvm.get_lv_size(install_abs_path)
        rsp.actualSize = rsp.size
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def migrate_volumes(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        for struct in cmd.migrateVolumeStructs:
            target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
            current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)
            with lvm.OperateLv(current_abs_path, shared=True):
                virtual_size = lvm.get_lv_size(current_abs_path)

                if lvm.lv_exists(target_abs_path):
                    target_ps_uuid = get_primary_storage_uuid_from_install_path(struct.targetInstallPath)
                    raise Exception("found %s already exists on ps %s" %
                                    (target_abs_path, target_ps_uuid))
                lvm.create_lv_from_absolute_path(target_abs_path, virtual_size,
                                                     "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
                lvm.active_lv(target_abs_path, lvm.LvmlockdLockType.SHARE)

        try:
            for struct in cmd.migrateVolumeStructs:
                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)

                with lvm.OperateLv(current_abs_path, shared=True):
                    bash.bash_errorout("cp %s %s" % (current_abs_path, target_abs_path))

            for struct in cmd.migrateVolumeStructs:
                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                current_abs_path = translate_absolute_path_from_install_path(struct.currentInstallPath)
                with lvm.RecursiveOperateLv(current_abs_path, shared=True):
                    previous_ps_uuid = get_primary_storage_uuid_from_install_path(struct.currentInstallPath)
                    target_ps_uuid = get_primary_storage_uuid_from_install_path(struct.targetInstallPath)

                    current_backing_file = linux.qcow2_get_backing_file(current_abs_path)  # type: str
                    target_backing_file = current_backing_file.replace(previous_ps_uuid, target_ps_uuid)

                    if current_backing_file is not None and current_backing_file != "":
                        lvm.do_active_lv(target_backing_file, lvm.LvmlockdLockType.SHARE, False)
                        logger.debug("rebase %s to %s" % (target_abs_path, target_backing_file))
                        linux.qcow2_rebase_no_check(target_backing_file, target_abs_path)
                    if struct.compareQcow2:
                        bash.bash_errorout("time qemu-img compare %s %s" % (current_abs_path, target_abs_path))
        except Exception as e:
            for struct in cmd.migrateVolumeStructs:
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
                target_abs_path = translate_absolute_path_from_install_path(struct.targetInstallPath)
                lvm.deactive_lv(target_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @staticmethod
    def calc_qcow2_option(self, options, has_backing_file):
        if options is None or options == "":
            return " "
        if has_backing_file:
            return re.sub("-o preallocation=\w* ", " ", options)
        return options

    @kvmagent.replyerror
    def get_block_devices(self, req):
        rsp = GetBlockDevicesRsp()
        rsp.blockDevices = lvm.get_block_devices()
        return jsonobject.dumps(rsp)

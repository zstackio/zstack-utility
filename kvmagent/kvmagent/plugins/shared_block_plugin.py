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
import zstacklib.utils.uuidhelper as uuidhelper

logger = log.get_logger(__name__)
LOCK_FILE = "/var/run/zstack/sharedblock.lock"
INIT_TAG = "zs::sharedblock::init"
HEARTBEAT_TAG = "zs::sharedblock::heartbeat"
VOLUME_TAG = "zs::sharedblock::volume"
IMAGE_TAG = "zs::sharedblock::image"
DEFAULT_VG_METADATA_SIZE = "2g"


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


def translate_absolute_path_from_install_path(path):
    if path == None:
        raise Exception("install path can not be null")
    return path.replace("sharedblock:/", "/dev")


class SharedBlockPlugin(kvmagent.KvmAgent):

    CONNECT_PATH = "/sharedblock/connect"
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
    CHANGE_VOLUME_ACTIVE_PATH = "/sharedblock/volume/active"
    GET_VOLUME_SIZE_PATH = "/sharedblock/volume/getsize"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CONNECT_PATH, self.connect)
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
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize_volume)
        http_server.register_async_uri(self.CHANGE_VOLUME_ACTIVE_PATH, self.active_lv)
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)

        self.imagestore_client = ImageStoreClient()
        self.id_files = {}

    def stop(self):
        pass

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

            lvm.config_sanlock_by_sed("sh_retries", "sh_retries=20")
            lvm.config_sanlock_by_sed("logfile_priority", "logfile_priority=7")
            lvm.config_sanlock_by_sed("renewal_read_extend_sec", "renewal_read_extend_sec=24")
            lvm.config_sanlock_by_sed("debug_renew", "debug_renew=1")

        def check_disk_by_uuid(diskUuid):
            for cond in ['TYPE=\\\"mpath\\\"', '\"\"']:
                cmd = shell.ShellCmd("lsblk --pair -p -o NAME,TYPE,FSTYPE,LABEL,UUID,VENDOR,MODEL,MODE,WWN | "
                                     " grep %s | grep %s | sort | uniq" % (cond, diskUuid))
                cmd(is_exception=False)
                if len(cmd.stdout.splitlines()) == 1:
                    pattern = re.compile(r'\/dev\/[^ \"]*')
                    return pattern.findall(cmd.stdout)[0]

            raise Exception("can not find disk with %s as uuid or wwn, "
                            "or multiple disks qualify but no mpath device found" % diskUuid)

        def create_vg_if_not_found(vgUuid, diskPaths, hostUuid):
            @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
            def find_vg(vgUuid):
                cmd = shell.ShellCmd("vgs %s -otags | grep %s" % (vgUuid, INIT_TAG))
                cmd(is_exception=False)
                if cmd.return_code != 0:
                    raise RetryException("can not find vg %s with tag %s" % (vgUuid, INIT_TAG))
                return True

            try:
                find_vg(vgUuid)
            except RetryException:
                cmd = shell.ShellCmd("vgcreate --shared --addtag '%s::%s::%s' --metadatasize %s %s %s" %
                                     (INIT_TAG, hostUuid, time.time(),
                                      DEFAULT_VG_METADATA_SIZE, vgUuid, " ".join(diskPaths)))
                cmd(is_exception=False)
                if cmd.return_code == 0:
                    return True
                if find_vg(vgUuid) is False:
                    raise Exception("can not find vg %s with disks: %s and create failed for %s " %
                                (vgUuid, diskPaths, cmd.stderr))
            except Exception as e:
                raise e

            return False

        config_lvm(cmd.hostId)
        for diskUuid in cmd.sharedBlockUuids:
            diskPaths.add(check_disk_by_uuid(diskUuid))
        lvm.start_lvmlockd()
        rsp.isFirst = create_vg_if_not_found(cmd.vgUuid, diskPaths, cmd.hostUuid)
        lvm.start_vg_lock(cmd.vgUuid)
        lvm.clean_vg_exists_host_tags(cmd.vgUuid, cmd.hostUuid, HEARTBEAT_TAG)
        lvm.add_vg_tag(cmd.vgUuid, "%s::%s::%s" % (HEARTBEAT_TAG, cmd.hostUuid, time.time()))

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def resize_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        with lvm.RecursiveOperateLv(install_abs_path, False):
            lvm.resize_lv(install_abs_path, cmd.size)
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
        qcow2_options = self.calc_qcow2_option(self, cmd.qcow2_options, True)

        with lvm.RecursiveOperateLv(template_abs_path_cache, shared=True):
            virtual_size = linux.qcow2_virtualsize(template_abs_path_cache)
            if not lvm.lv_exists(install_abs_path):
                lvm.create_lv_from_absolute_path(install_abs_path, virtual_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(install_abs_path, shared=False):
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

        with lvm.RecursiveOperateLv(volume_abs_path, shared=False):
            virtual_size = linux.qcow2_virtualsize(volume_abs_path)
            if not lvm.lv_exists(install_abs_path):
                lvm.create_lv_from_absolute_path(install_abs_path, virtual_size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(install_abs_path, shared=False):
                linux.create_template(volume_abs_path, install_abs_path)

        logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))
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

        with lvm.OperateLv(install_abs_path, shared=False):
            linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, install_abs_path, cmd.username, cmd.sshPort)
        logger.debug('successfully download %s/%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))

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
        rsp = AgentRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()
        snapshot_abs_path = translate_absolute_path_from_install_path(cmd.snapshotInstallPath)
        qcow2_options = self.calc_qcow2_option(self, cmd.qcow2_options, True)

        with lvm.RecursiveOperateLv(snapshot_abs_path, shared=True):
            size = linux.qcow2_virtualsize(snapshot_abs_path)
            new_volume_path = "/dev/%s/%s" % (cmd.vgUuid, uuidhelper.uuid())

            lvm.create_lv_from_absolute_path(new_volume_path, size,
                                             "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(new_volume_path, shared=False):
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
            with lvm.OperateLv(workspace_abs_path, shared=False):
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
                    # TODO(weiw): add tmp disk and then rename is better
                    linux.create_template(src_abs_path, dst_abs_path)

        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.file_lock(LOCK_FILE)
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)

        if cmd.backingFile:
            qcow2_options = self.calc_qcow2_option(self, cmd.qcow2_options, True)
            backing_abs_path = translate_absolute_path_from_install_path(cmd.backingFile)
            with lvm.RecursiveOperateLv(backing_abs_path, shared=True):
                virtual_size = linux.qcow2_virtualsize(backing_abs_path)
                if not lvm.lv_exists(install_abs_path):
                    lvm.create_lv_from_absolute_path(install_abs_path, virtual_size,
                                                     "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
                with lvm.OperateLv(install_abs_path, shared=False):
                    linux.qcow2_create_with_backing_file_and_option(backing_abs_path, install_abs_path, qcow2_options)
        elif not lvm.lv_exists(install_abs_path):
            qcow2_options = self.calc_qcow2_option(self, cmd.qcow2_options, False)
            lvm.create_lv_from_absolute_path(install_abs_path, cmd.size,
                                                 "%s::%s::%s" % (VOLUME_TAG, cmd.hostUuid, time.time()))
            with lvm.OperateLv(install_abs_path, shared=False):
                linux.qcow2_create_with_option(install_abs_path, cmd.size, qcow2_options)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        rsp.existing = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def active_lv(self, req):
        def handle_lv(lockType, fpath):
            if lockType > lvm.LvmlockdLockType.NULL:
                lvm.active_lv(fpath, lockType == lvm.LvmlockdLockType.SHARE)
            else:
                lvm.deactive_lv(fpath)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = lvm.get_vg_size(cmd.vgUuid)

        install_abs_path = translate_absolute_path_from_install_path(cmd.installPath)
        handle_lv(cmd.lockType, install_abs_path)

        if cmd.recursive is False:
            return jsonobject.dumps(rsp)

        while linux.qcow2_get_backing_file(install_abs_path) != "":
            install_abs_path = linux.qcow2_get_backing_file(install_abs_path)
            if cmd.lockType == lvm.LvmlockdLockType.NULL:
                handle_lv(lvm.LvmlockdLockType.NULL, install_abs_path)
            else:
                # activate backing files only in shared mode
                handle_lv(lvm.LvmlockdLockType.SHARE, install_abs_path)

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

    @staticmethod
    def calc_qcow2_option(self, options, has_backing_file):
        if options is None or options == "":
            return ""
        if has_backing_file:
            return re.sub("-o preallocation=\w* ", " ", options)

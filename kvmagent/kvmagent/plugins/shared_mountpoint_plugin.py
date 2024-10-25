import os.path
import traceback

from zstacklib.utils import lock

from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import traceable_shell
from zstacklib.utils import rollback
from zstacklib.utils import linux
from zstacklib.utils import qcow2
import zstacklib.utils.uuidhelper as uuidhelper
from zstacklib.utils.plugin import completetask
from zstacklib.utils import secret

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None
        self.totalCapacity = None
        self.availableCapacity = None
        self.actualSize = None

class ConnectRsp(AgentRsp):
    def __init__(self):
        super(ConnectRsp, self).__init__()
        self.isFirst = False

class RevertVolumeFromSnapshotRsp(AgentRsp):
    def __init__(self):
        super(RevertVolumeFromSnapshotRsp, self).__init__()
        self.newVolumeInstallPath = None
        self.size = None

class ReinitImageRsp(AgentRsp):
    def __init__(self):
        super(ReinitImageRsp, self).__init__()
        self.newVolumeInstallPath = None

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

class GetSubPathRsp(AgentRsp):
    def __init__(self):
        super(GetSubPathRsp, self).__init__()
        self.paths = []

class GetDownloadBitsFromKvmHostProgressRsp(AgentRsp):
    def __init__(self):
        super(GetDownloadBitsFromKvmHostProgressRsp, self).__init__()
        self.totalSize = None

class DownloadBitsFromKvmHostRsp(AgentRsp):
    def __init__(self):
        super(DownloadBitsFromKvmHostRsp, self).__init__()
        self.format = None

class CreateVolumeWithBackingRsp(AgentRsp):
    def __init__(self):
        super(CreateVolumeWithBackingRsp, self).__init__()
        self.size = None
        self.actualSize = None


class GetQcow2HashValueRsp(AgentRsp):
    def __init__(self):
        super(GetQcow2HashValueRsp, self).__init__()
        self.hash = None


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

class GetBackingChainRsp(AgentRsp):
    def __init__(self):
        super(GetBackingChainRsp, self).__init__()
        self.totalSize = 0
        self.backingChain = []

class SharedMountPointPrimaryStoragePlugin(kvmagent.KvmAgent):

    CONNECT_PATH = "/sharedmountpointprimarystorage/connect"
    CREATE_VOLUME_FROM_CACHE_PATH = "/sharedmountpointprimarystorage/createrootvolume"
    CREATE_DATA_VOLUME_WITH_BACKING_PATH = "/sharedmountpointprimarystorage/createvolumewithbacking"
    DELETE_BITS_PATH = "/sharedmountpointprimarystorage/bits/delete"
    UNLINK_BITS_PATH = "/sharedmountpointprimarystorage/bits/unlink"
    CREATE_TEMPLATE_FROM_VOLUME_PATH = "/sharedmountpointprimarystorage/createtemplatefromvolume"
    ESTIMATE_TEMPLATE_SIZE_PATH = "/sharedmountpointprimarystorage/estimatetemplatesize"
    UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH = "/sharedmountpointprimarystorage/sftp/upload"
    DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH = "/sharedmountpointprimarystorage/sftp/download"
    UPLOAD_BITS_TO_IMAGESTORE_PATH = "/sharedmountpointprimarystorage/imagestore/upload"
    COMMIT_BITS_TO_IMAGESTORE_PATH = "/sharedmountpointprimarystorage/imagestore/commit"
    DOWNLOAD_BITS_FROM_IMAGESTORE_PATH = "/sharedmountpointprimarystorage/imagestore/download"
    CLEAN_IMAGE_META = "/sharedmountpointprimarystorage/imagestore/meta/clean"
    REVERT_VOLUME_FROM_SNAPSHOT_PATH = "/sharedmountpointprimarystorage/volume/revertfromsnapshot"
    MERGE_SNAPSHOT_PATH = "/sharedmountpointprimarystorage/snapshot/merge"
    OFFLINE_MERGE_SNAPSHOT_PATH = "/sharedmountpointprimarystorage/snapshot/offlinemerge"
    CREATE_EMPTY_VOLUME_PATH = "/sharedmountpointprimarystorage/volume/createempty"
    CREATE_FOLDER_PATH = "/sharedmountpointprimarystorage/volume/createfolder"
    CHECK_BITS_PATH = "/sharedmountpointprimarystorage/bits/check"
    GET_VOLUME_SIZE_PATH = "/sharedmountpointprimarystorage/volume/getsize"
    RESIZE_VOLUME_PATH = "/sharedmountpointprimarystorage/volume/resize"
    HARD_LINK_VOLUME = "/sharedmountpointprimarystorage/volume/hardlink"
    REINIT_IMAGE_PATH = "/sharedmountpointprimarystorage/volume/reinitimage"
    DOWNLOAD_BITS_FROM_KVM_HOST_PATH = "/sharedmountpointprimarystorage/kvmhost/download"
    CANCEL_DOWNLOAD_BITS_FROM_KVM_HOST_PATH = "/sharedmountpointprimarystorage/kvmhost/download/cancel"
    GET_DOWNLOAD_BITS_FROM_KVM_HOST_PROGRESS_PATH = "/sharedmountpointprimarystorage/kvmhost/download/progress"
    GET_QCOW2_HASH_VALUE_PATH = "/sharedmountpointprimarystorage/getqcow2hash"
    GET_BACKING_CHAIN_PATH = "/sharedmountpointprimarystorage/volume/getbackingchain"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.create_root_volume)
        http_server.register_async_uri(self.CREATE_DATA_VOLUME_WITH_BACKING_PATH, self.create_volume_with_backing)
        http_server.register_async_uri(self.DELETE_BITS_PATH, self.delete_bits)
        http_server.register_async_uri(self.UNLINK_BITS_PATH, self.unlink)
        http_server.register_async_uri(self.CREATE_TEMPLATE_FROM_VOLUME_PATH, self.create_template_from_volume)
        http_server.register_async_uri(self.ESTIMATE_TEMPLATE_SIZE_PATH, self.estimate_template)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH, self.upload_to_sftp)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH, self.download_from_sftp)
        http_server.register_async_uri(self.UPLOAD_BITS_TO_IMAGESTORE_PATH, self.upload_to_imagestore)
        http_server.register_async_uri(self.COMMIT_BITS_TO_IMAGESTORE_PATH, self.commit_to_imagestore)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_IMAGESTORE_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.CLEAN_IMAGE_META, self.clean_image_meta)
        http_server.register_async_uri(self.REVERT_VOLUME_FROM_SNAPSHOT_PATH, self.revert_volume_from_snapshot)
        http_server.register_async_uri(self.MERGE_SNAPSHOT_PATH, self.merge_snapshot)
        http_server.register_async_uri(self.OFFLINE_MERGE_SNAPSHOT_PATH, self.offline_merge_snapshots)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.create_empty_volume)
        http_server.register_async_uri(self.CREATE_FOLDER_PATH, self.create_folder)
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize_volume)
        http_server.register_async_uri(self.HARD_LINK_VOLUME, self.hardlink_volume)
        http_server.register_async_uri(self.REINIT_IMAGE_PATH, self.reinit_image)
        http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_KVM_HOST_PATH, self.download_from_kvmhost)
        http_server.register_async_uri(self.CANCEL_DOWNLOAD_BITS_FROM_KVM_HOST_PATH, self.cancel_download_from_kvmhost)
        http_server.register_async_uri(self.GET_DOWNLOAD_BITS_FROM_KVM_HOST_PROGRESS_PATH, self.get_download_bits_from_kvmhost_progress)
        http_server.register_async_uri(self.GET_QCOW2_HASH_VALUE_PATH, self.get_qcow2_hashvalue)
        http_server.register_async_uri(self.GET_BACKING_CHAIN_PATH, self.get_backing_chain)

        self.imagestore_client = ImageStoreClient()
        self.id_files = {}

    def stop(self):
        pass

    @kvmagent.replyerror
    def resize_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        install_path = cmd.installPath
        rsp = ResizeVolumeRsp()
        linux.qemu_img_resize(install_path, cmd.size, 'qcow2', cmd.force)
        ret = linux.qcow2_virtualsize(install_path)
        rsp.size = ret
        return jsonobject.dumps(rsp)

    @staticmethod
    def _get_disk_capacity(mount_point):
        if not mount_point:
            raise Exception('storage mount point cannot be None')
        return linux.get_disk_capacity_by_df(mount_point)

    @kvmagent.replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeSizeRsp()
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def connect(self, req):
        none_shared_mount_fs_type = ['xfs', 'ext2', 'ext3', 'ext4', 'vfat', 'tmpfs', 'btrfs']
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if not linux.timeout_isdir(cmd.mountPoint):
            raise kvmagent.KvmError('%s is not a directory, the mount point seems not setup' % cmd.mountPoint)

        folder_fs_type = shell.call("df -T %s|tail -1|awk '{print $2}'" % cmd.mountPoint).strip()
        if folder_fs_type in none_shared_mount_fs_type:
            raise kvmagent.KvmError(
                '%s filesystem is %s, which is not a shared mount point type.' % (cmd.mountPoint, folder_fs_type))

        id_dir = os.path.join(cmd.mountPoint, "zstack_smp_id_file")
        shell.call("mkdir -p %s" % id_dir)
        lock_file = os.path.join(id_dir, "uuid.lock")

        @lock.file_lock(lock_file, locker=lock.Flock())
        def check_other_smp_and_set_id_file(uuid, existUuids):
            o = shell.ShellCmd('''\
            ls %s | grep -v %s | grep -o "[0-9a-f]\{8\}[0-9a-f]\{4\}[1-5][0-9a-f]\{3\}[89ab][0-9a-f]\{3\}[0-9a-f]\{12\}"\
            ''' % (id_dir, uuid))
            o(False)
            if o.return_code != 0:
                file_uuids = []
            else:
                file_uuids = o.stdout.splitlines()

            for file_uuid in file_uuids:
                if file_uuid in existUuids:
                    raise Exception(
                        "the mount point [%s] has been occupied by other SMP[uuid:%s], Please attach this directly"
                        % (cmd.mountPoint, file_uuid))

            logger.debug("existing id files: %s" % file_uuids)
            self.id_files[uuid] = os.path.join(id_dir, uuid)

            if not os.path.exists(self.id_files[uuid]):
                # check if hosts in the same cluster mount the same path but different storages.
                rsp.isFirst = True
                for file_uuid in file_uuids:
                    linux.rm_file_force(os.path.join(id_dir, file_uuid))
                linux.touch_file(self.id_files[uuid])
                linux.sync_file(self.id_files[uuid])

        rsp = ConnectRsp()
        check_other_smp_and_set_id_file(cmd.uuid, cmd.existUuids)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_volume_with_backing(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVolumeWithBackingRsp()
        self.do_create_volume_with_backing(cmd.templatePathInCache, cmd.installPath, cmd)
        rsp.size = linux.qcow2_get_virtual_size(cmd.installPath)
        rsp.actualSize = os.path.getsize(cmd.installPath)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVolumeFromCacheRsp()

        if not os.path.exists(cmd.templatePathInCache):
            rsp.error = "unable to find image in cache"
            rsp.success = False
            return jsonobject.dumps(rsp)

        self.do_create_volume_with_backing(cmd.templatePathInCache, cmd.installPath, cmd)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        return jsonobject.dumps(rsp)

    @staticmethod
    def do_create_volume_with_backing(backing_path, vol_path, cmd):
        dirname = os.path.dirname(vol_path)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0775)

        linux.qcow2_clone_with_cmd(backing_path, vol_path, cmd)

    @kvmagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        try:
            if cmd.folder:
                linux.rm_dir_checked(cmd.path)
            else:
                kvmagent.deleteImage(cmd.path)
        except linux.VolumeInUseError:
            rsp.success = False
            rsp.error = "%s %s is still in use, unable to delete" % ("dir" if cmd.folder else "file", cmd.path)
            rsp.inUse = True
            logger.debug(rsp.error)
            return jsonobject.dumps(rsp)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def unlink(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        if os.path.isdir(cmd.installPath):
            for f in linux.list_all_file(cmd.installPath):
                if os.stat(f).st_nlink > 1:
                    linux.unlink_file_checked(f)
                    continue
                logger.debug("file %s only has 1 link, skip unlink." % f)
        else:
            if os.stat(cmd.installPath).st_nlink > 1:
                linux.unlink_file_checked(cmd.installPath)
            logger.debug("file %s only has 1 link, skip unlink." % cmd.installPath)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @rollback.rollback
    def create_template_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateTemplateFromVolumeRsp()
        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0755)

        @rollback.rollbackable
        def _0():
            linux.rm_file_force(cmd.installPath)
        _0()

        t_shell = traceable_shell.get_shell(cmd)
        linux.create_template(cmd.volumePath, cmd.installPath, shell=t_shell)

        logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))

        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def estimate_template(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = EstimateTemplateSizeRsp()
        rsp.actualSize = linux.qcow2_measure_required_size(cmd.volumePath)
        rsp.size, _ = linux.qcow2_size_and_actual_size(cmd.volumePath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        def upload():
            if not os.path.exists(cmd.primaryStorageInstallPath):
                raise kvmagent.KvmError('cannot find %s' % cmd.primaryStorageInstallPath)

            linux.scp_upload(cmd.hostname, cmd.sshKey, cmd.primaryStorageInstallPath, cmd.backupStorageInstallPath, cmd.username, cmd.sshPort)

        upload()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def download_from_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath, cmd.username, cmd.sshPort)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        logger.debug('successfully download %s/%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))

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
        cachedir = None if cmd.isData else cmd.mountPoint
        self.imagestore_client.download_from_imagestore(cachedir, cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath, cmd.concurrency)
        if cmd.isData:
            self.imagestore_client.clean_meta(cmd.primaryStorageInstallPath)
        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def clean_image_meta(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.imagestore_client.clean_meta(cmd.primaryStorageInstallPath)

        rsp = kvmagent.AgentResponse()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def reinit_image(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ReinitImageRsp()

        install_path = cmd.imageInstallPath
        dirname = os.path.dirname(cmd.volumeInstallPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0775)

        new_volume_path = os.path.join(dirname, '{0}.qcow2'.format(uuidhelper.uuid()))
        linux.qcow2_clone_with_cmd(install_path, new_volume_path, cmd)
        rsp.newVolumeInstallPath = new_volume_path
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()

        install_path = cmd.snapshotInstallPath
        new_volume_path = os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
        linux.qcow2_clone_with_cmd(install_path, new_volume_path, cmd)
        size = linux.qcow2_virtualsize(new_volume_path)
        rsp.newVolumeInstallPath = new_volume_path
        rsp.size = size
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def merge_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MergeSnapshotRsp()

        workspace_dir = os.path.dirname(cmd.workspaceInstallPath)
        if not os.path.exists(workspace_dir):
            os.makedirs(workspace_dir)

        t_shell = traceable_shell.get_shell(cmd)
        linux.create_template(cmd.snapshotInstallPath, cmd.workspaceInstallPath, shell=t_shell)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.workspaceInstallPath)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offline_merge_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        src_path = cmd.srcPath if not cmd.fullRebase else ""
        if linux.qcow2_get_backing_file(cmd.destPath) == src_path:
            rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
            return jsonobject.dumps(rsp)

        if not cmd.fullRebase:
            linux.qcow2_rebase(cmd.srcPath, cmd.destPath)
        else:
            tmp = os.path.join(os.path.dirname(cmd.destPath), '%s.qcow2' % uuidhelper.uuid())
            qcow2.create_template_with_task_daemon(cmd.destPath, tmp, task_spec=cmd)
            shell.call("mv %s %s" % (tmp, cmd.destPath))

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_folder(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateEmptyVolumeRsp()

        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        if cmd.backingFile:
            linux.qcow2_create_with_backing_file_and_cmd(cmd.backingFile, cmd.installPath, cmd)
        else:
            linux.qcow2_create_with_cmd(cmd.installPath, cmd.size, cmd)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        rsp.existing = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @completetask
    def download_from_kvmhost(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DownloadBitsFromKvmHostRsp()

        install_abs_path = cmd.primaryStorageInstallPath

        last_task = self.load_and_save_task(req, rsp, os.path.exists, install_abs_path)
        if last_task and last_task.agent_pid == os.getpid():
            rsp = self.wait_task_complete(last_task)
            return jsonobject.dumps(rsp)

        linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, install_abs_path, cmd.username, cmd.sshPort, cmd.bandWidth)
        rsp.format = linux.get_img_fmt(install_abs_path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cancel_download_from_kvmhost(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        install_abs_path = cmd.primaryStorageInstallPath
        shell.run("pkill -9 -f '%s'" % install_abs_path)

        linux.rm_file_force(cmd.primaryStorageInstallPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_download_bits_from_kvmhost_progress(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetDownloadBitsFromKvmHostProgressRsp()
        rsp.totalSize = linux.get_total_file_size(cmd.volumePaths)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def hardlink_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.hardlink_and_rebase(cmd.srcDir, cmd.dstDir, cmd.mountPoint)

        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    def hardlink_and_rebase(self, src_dir, dst_dir, storage_dir):
        src_dst_dict = {}
        for f in linux.list_all_file(src_dir):
            src_dst_dict[f] = os.path.realpath(f.replace(src_dir, dst_dir))

        for f in linux.list_all_file(storage_dir):
            backing_file = os.path.realpath(linux.qcow2_get_backing_file(f))
            if backing_file in src_dst_dict:
                dst_file = src_dst_dict[backing_file]
                linux.link(backing_file, dst_file)
                linux.qcow2_rebase_no_check(dst_file, f)

        for src_file, dst_file in src_dst_dict.iteritems():
            linux.link(src_file, dst_file)

    @kvmagent.replyerror
    def get_qcow2_hashvalue(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetQcow2HashValueRsp()

        rsp.hashValue = secret.get_image_hash(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_backing_chain(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetBackingChainRsp()

        rsp.backingChain = linux.qcow2_get_backing_chain(cmd.installPath)
        rsp.totalSize = linux.get_total_file_size(rsp.backingChain)

        return jsonobject.dumps(rsp)

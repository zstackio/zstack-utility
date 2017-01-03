import os.path
import traceback

from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
import zstacklib.utils.uuidhelper as uuidhelper

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None
        self.totalCapacity = None
        self.availableCapacity = None

class RevertVolumeFromSnapshotRsp(AgentRsp):
    def __init__(self):
        super(RevertVolumeFromSnapshotRsp, self).__init__()
        self.newVolumeInstallPath = None

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


class SharedMountPointPrimaryStoragePlugin(kvmagent.KvmAgent):

    CONNECT_PATH = "/sharedmountpointprimarystorage/connect"
    CREATE_VOLUME_FROM_CACHE_PATH = "/sharedmountpointprimarystorage/createrootvolume"
    DELETE_BITS_PATH = "/sharedmountpointprimarystorage/bits/delete"
    CREATE_TEMPLATE_FROM_VOLUME_PATH = "/sharedmountpointprimarystorage/createtemplatefromvolume"
    UPLOAD_BITS_TO_SFTP_BACKUPSTORAGE_PATH = "/sharedmountpointprimarystorage/sftp/upload"
    DOWNLOAD_BITS_FROM_SFTP_BACKUPSTORAGE_PATH = "/sharedmountpointprimarystorage/sftp/download"
    UPLOAD_BITS_TO_IMAGESTORE_PATH = "/sharedmountpointprimarystorage/imagestore/upload"
    COMMIT_BITS_TO_IMAGESTORE_PATH = "/sharedmountpointprimarystorage/imagestore/commit"
    DOWNLOAD_BITS_FROM_IMAGESTORE_PATH = "/sharedmountpointprimarystorage/imagestore/download"
    REVERT_VOLUME_FROM_SNAPSHOT_PATH = "/sharedmountpointprimarystorage/volume/revertfromsnapshot"
    MERGE_SNAPSHOT_PATH = "/sharedmountpointprimarystorage/snapshot/merge"
    OFFLINE_MERGE_SNAPSHOT_PATH = "/sharedmountpointprimarystorage/snapshot/offlinemerge"
    CREATE_EMPTY_VOLUME_PATH = "/sharedmountpointprimarystorage/volume/createempty"
    CHECK_BITS_PATH = "/sharedmountpointprimarystorage/bits/check"
    GET_VOLUME_SIZE_PATH = "/sharedmountpointprimarystorage/volume/getsize"

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
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)

        self.mount_point = None
        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    def _get_disk_capacity(self):
        return linux.get_disk_capacity_by_df(self.mount_point)

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
        self.mount_point = cmd.mountPoint
        if not os.path.isdir(self.mount_point):
            raise kvmagent.KvmError('%s is not a directory, the mount point seems not setup' % self.mount_point)

        folder_fs_type = shell.call("df -T %s|tail -1|awk '{print $2}'" % self.mount_point).strip()
        if folder_fs_type in none_shared_mount_fs_type:
            raise kvmagent.KvmError('%s filesystem is %s, which is not a shared mount point type.' % (self.mount_point, folder_fs_type))

        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        if not os.path.exists(cmd.templatePathInCache):
            rsp.error = "UNABLE_TO_FIND_IMAGE_IN_CACHE"
            rsp.success = False
            return jsonobject.dumps(rsp)

        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0775)

        linux.qcow2_clone(cmd.templatePathInCache, cmd.installPath)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        shell.call('rm -f %s' % cmd.path)
        pdir = os.path.dirname(cmd.path)
        linux.rmdir_if_empty(pdir)

        logger.debug('successfully delete %s' % cmd.path)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_template_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0755)

        linux.qcow2_create_template(cmd.volumePath, cmd.installPath)

        logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
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
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        logger.debug('successfully download %s/%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.upload_to_imagestore(cmd, req)

    @kvmagent.replyerror
    def commit_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.commit_to_imagestore(cmd.primaryStorageInstallPath)

    @kvmagent.replyerror
    def download_from_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.imagestore_client.download_from_imagestore(self.mount_point, cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)
        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()

        install_path = cmd.snapshotInstallPath
        new_volume_path = os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
        linux.qcow2_clone(install_path, new_volume_path)
        rsp.newVolumeInstallPath = new_volume_path
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def merge_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MergeSnapshotRsp()

        workspace_dir = os.path.dirname(cmd.workspaceInstallPath)
        if not os.path.exists(workspace_dir):
            os.makedirs(workspace_dir)

        linux.qcow2_create_template(cmd.snapshotInstallPath, cmd.workspaceInstallPath)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.workspaceInstallPath)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offline_merge_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if not cmd.fullRebase:
            linux.qcow2_rebase(cmd.srcPath, cmd.destPath)
        else:
            tmp = os.path.join(os.path.dirname(cmd.destPath), '%s.qcow2' % uuidhelper.uuid())
            linux.qcow2_create_template(cmd.destPath, tmp)
            shell.call("mv %s %s" % (tmp, cmd.destPath))

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        if cmd.backingFile:
            linux.qcow2_create_with_backing_file(cmd.backingFile, cmd.installPath)
        else:
            linux.qcow2_create(cmd.installPath, cmd.size)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        rsp.existing = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)

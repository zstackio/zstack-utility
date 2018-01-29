import os.path
import traceback

from zstacklib.utils import lock

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

class GetSubPathRsp(AgentRsp):
    def __init__(self):
        super(GetSubPathRsp, self).__init__()
        self.paths = []

class SharedMountPointPrimaryStoragePlugin(kvmagent.KvmAgent):

    CONNECT_PATH = "/sharedmountpointprimarystorage/connect"
    CREATE_VOLUME_FROM_CACHE_PATH = "/sharedmountpointprimarystorage/createrootvolume"
    DELETE_BITS_PATH = "/sharedmountpointprimarystorage/bits/delete"
    GET_SUBPATH_PATH = "/sharedmountpointprimarystorage/sub/path"
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
    RESIZE_VOLUME_PATH = "/sharedmountpointprimarystorage/volume/resize"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.create_root_volume)
        http_server.register_async_uri(self.DELETE_BITS_PATH, self.delete_bits)
        http_server.register_async_uri(self.GET_SUBPATH_PATH, self.get_sub_path)
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
        http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize_volume)

        self.imagestore_client = ImageStoreClient()
        self.id_files = {}

    def stop(self):
        pass

    @kvmagent.replyerror
    def resize_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        install_path = cmd.installPath
        rsp = ResizeVolumeRsp()
        shell.call("qemu-img resize %s %s" % (install_path, cmd.size))
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
                    shell.call("rm -rf %s" % os.path.join(id_dir, file_uuid))
                shell.call("touch %s && sync" % self.id_files[uuid])

        rsp = ConnectRsp()
        check_other_smp_and_set_id_file(cmd.uuid, cmd.existUuids)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        if not os.path.exists(cmd.templatePathInCache):
            rsp.error = "unable to find image in cache"
            rsp.success = False
            return jsonobject.dumps(rsp)

        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0775)

        linux.qcow2_clone(cmd.templatePathInCache, cmd.installPath)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        kvmagent.deleteImage(cmd.path)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_sub_path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetSubPathRsp()
        rsp.paths = kvmagent.listPath(cmd.path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_template_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0755)
        linux.create_template(cmd.volumePath, cmd.installPath)

        logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
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
        self.imagestore_client.download_from_imagestore(cmd.mountPoint, cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)
        rsp = AgentRsp()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()

        install_path = cmd.snapshotInstallPath
        new_volume_path = os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
        linux.qcow2_clone(install_path, new_volume_path)
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

        linux.create_template(cmd.snapshotInstallPath, cmd.workspaceInstallPath)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.workspaceInstallPath)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offline_merge_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if not cmd.fullRebase:
            linux.qcow2_rebase(cmd.srcPath, cmd.destPath)
        else:
            tmp = os.path.join(os.path.dirname(cmd.destPath), '%s.qcow2' % uuidhelper.uuid())
            linux.create_template(cmd.destPath, tmp)
            shell.call("mv %s %s" % (tmp, cmd.destPath))

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
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
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.mountPoint)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        rsp.existing = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)

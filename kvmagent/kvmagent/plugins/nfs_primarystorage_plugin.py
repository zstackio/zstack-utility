'''

@author: frank
'''
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

class NfsResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(NfsResponse, self).__init__()
        self.totalCapacity = None
        self.availableCapacity = None

class MountResponse(NfsResponse):
    def __init__(self):
        super(MountResponse, self).__init__()

class UnmountResponse(NfsResponse):
    def __init__(self):
        super(UnmountResponse, self).__init__()

class DeleteSnapshotResponse(NfsResponse):
    def __init__(self):
        super(DeleteSnapshotResponse, self).__init__()

class RevertVolumeFromSnapshotResponse(NfsResponse):
    def __init__(self):
        super(RevertVolumeFromSnapshotResponse, self).__init__()
        self.newVolumeInstallPath = None


class NfsError(Exception):
    '''Nfs primary storage error'''

class CreateRootVolumeFromTemplateResponse(NfsResponse):
    def __init__(self):
        super(CreateRootVolumeFromTemplateResponse, self).__init__()


class CreateEmptyVolumeResponse(NfsResponse):
    def __init__(self):
        super(CreateEmptyVolumeResponse, self).__init__()

class DownloadBitsFromSftpBackupStorageResponse(NfsResponse):
    def __init__(self):
        super(DownloadBitsFromSftpBackupStorageResponse, self).__init__()


class CreateTemplateFromRootVolumeRsp(NfsResponse):
    def __init__(self):
        super(CreateTemplateFromRootVolumeRsp, self).__init__()

class GetCapacityResponse(NfsResponse):
    def __init__(self):
        super(GetCapacityResponse, self).__init__()

class DeleteResponse(NfsResponse):
    def __init__(self):
        super(DeleteResponse, self).__init__()

class CheckIsBitsExistingRsp(NfsResponse):
    def __init__(self):
        super(CheckIsBitsExistingRsp, self).__init__()
        self.existing = None

class BaseImageMetaData(object):
    def __init__(self):
        self.download_from = None
        self.size = None
        self.md5sum = None

class VolumeMeta(object):
    def __init__(self):
        self.name = None
        self.account_uuid = None
        self.uuid = None
        self.hypervisor_type = None
        self.size = None

class CopyToSftpBackupStorageResponse(NfsResponse):
    def __init__(self):
        super(CopyToSftpBackupStorageResponse, self).__init__()

class MergeSnapshotResponse(NfsResponse):
    def __init__(self):
        super(MergeSnapshotResponse, self).__init__()
        self.size = None
        self.actualSize = None

class RebaseAndMergeSnapshotsResponse(NfsResponse):
    def __init__(self):
        super(RebaseAndMergeSnapshotsResponse, self).__init__()
        self.size = None
        self.actualSize = None

class MoveBitsRsp(NfsResponse):
    def __init__(self):
        super(MoveBitsRsp, self).__init__()

class OfflineMergeSnapshotRsp(NfsResponse):
    def __init__(self):
        super(OfflineMergeSnapshotRsp, self).__init__()

class GetVolumeSizeRsp(NfsResponse):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class GetVolumeBaseImagePathRsp(NfsResponse):
    def __init__(self):
        super(GetVolumeBaseImagePathRsp, self).__init__()
        self.path = None

class NfsPrimaryStoragePlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    MOUNT_PATH = '/nfsprimarystorage/mount'
    UNMOUNT_PATH = '/nfsprimarystorage/unmount'
    CREATE_VOLUME_FROM_TEMPLATE_PATH = "/nfsprimarystorage/sftp/createvolumefromtemplate"
    CREATE_EMPTY_VOLUME_PATH = "/nfsprimarystorage/createemptyvolume"
    GET_CAPACITY_PATH = "/nfsprimarystorage/getcapacity"
    CREATE_TEMPLATE_FROM_VOLUME_PATH = "/nfsprimarystorage/sftp/createtemplatefromvolume"
    REVERT_VOLUME_FROM_SNAPSHOT_PATH = "/nfsprimarystorage/revertvolumefromsnapshot"
    DELETE_PATH = "/nfsprimarystorage/delete"
    CHECK_BITS_PATH = "/nfsprimarystorage/checkbits"
    UPLOAD_TO_SFTP_PATH = "/nfsprimarystorage/uploadtosftpbackupstorage"
    DOWNLOAD_FROM_SFTP_PATH = "/nfsprimarystorage/downloadfromsftpbackupstorage"
    UPLOAD_TO_IMAGESTORE_PATH = "/nfsprimarystorage/imagestore/upload"
    COMMIT_TO_IMAGESTORE_PATH = "/nfsprimarystorage/imagestore/commit"
    DOWNLOAD_FROM_IMAGESTORE_PATH = "/nfsprimarystorage/imagestore/download"
    MERGE_SNAPSHOT_PATH = "/nfsprimarystorage/mergesnapshot"
    REBASE_MERGE_SNAPSHOT_PATH = "/nfsprimarystorage/rebaseandmergesnapshot"
    MOVE_BITS_PATH = "/nfsprimarystorage/movebits"
    OFFLINE_SNAPSHOT_MERGE = "/nfsprimarystorage/offlinesnapshotmerge"
    REMOUNT_PATH = "/nfsprimarystorage/remount"
    GET_VOLUME_SIZE_PATH = "/nfsprimarystorage/getvolumesize"
    PING_PATH = "/nfsprimarystorage/ping"
    GET_VOLUME_BASE_IMAGE_PATH = "/nfsprimarystorage/getvolumebaseimage"

    ERR_UNABLE_TO_FIND_IMAGE_IN_CACHE = "UNABLE_TO_FIND_IMAGE_IN_CACHE"
    
    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_sync_uri(self.MOUNT_PATH, self.mount)
        http_server.register_sync_uri(self.UNMOUNT_PATH, self.umount)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_TEMPLATE_PATH, self.create_root_volume_from_template)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.create_empty_volume)
        http_server.register_async_uri(self.DOWNLOAD_FROM_SFTP_PATH, self.download_from_sftp)
        http_server.register_async_uri(self.GET_CAPACITY_PATH, self.get_capacity)
        http_server.register_async_uri(self.DELETE_PATH, self.delete)
        http_server.register_async_uri(self.CREATE_TEMPLATE_FROM_VOLUME_PATH, self.create_template_from_root_volume)
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        http_server.register_async_uri(self.REVERT_VOLUME_FROM_SNAPSHOT_PATH, self.revert_volume_from_snapshot)
        http_server.register_async_uri(self.UPLOAD_TO_SFTP_PATH, self.upload_to_sftp)
        http_server.register_async_uri(self.UPLOAD_TO_IMAGESTORE_PATH, self.upload_to_imagestore)
        http_server.register_async_uri(self.COMMIT_TO_IMAGESTORE_PATH, self.commit_to_imagestore)
        http_server.register_async_uri(self.DOWNLOAD_FROM_IMAGESTORE_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.MERGE_SNAPSHOT_PATH, self.merge_snapshot)
        http_server.register_async_uri(self.REBASE_MERGE_SNAPSHOT_PATH, self.rebase_and_merge_snapshot)
        http_server.register_async_uri(self.MOVE_BITS_PATH, self.move_bits)
        http_server.register_async_uri(self.OFFLINE_SNAPSHOT_MERGE, self.merge_snapshot_to_volume)
        http_server.register_async_uri(self.REMOUNT_PATH, self.remount)
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        http_server.register_async_uri(self.PING_PATH, self.ping)
        http_server.register_async_uri(self.GET_VOLUME_BASE_IMAGE_PATH, self.get_volume_base_image_path)
        self.mount_path = {}
        self.image_cache = None
        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass
    
    def _get_disk_capacity(self, uuid):
        path = self.mount_path.get(uuid)
        if not path:
            raise Exception('cannot find mount path of primary storage[uuid: %s]' % uuid)
        return linux.get_disk_capacity_by_df(path)

    def _json_meta_file_name(self, path):
        return path + '.json'

    def _set_capacity_to_response(self, uuid, rsp):
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(uuid)

    @kvmagent.replyerror
    def get_volume_base_image_path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeBaseImagePathRsp()
        rsp.path = linux.get_qcow2_base_image_path_recusively(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        mount_path = self.mount_path[cmd.uuid]
        if not mount_path or not os.path.isdir(mount_path):
            raise Exception('the mount path[%s] of the nfs primary storage[uuid:%s] is not existing' % (mount_path, cmd.uuid))

        test_file = os.path.join(mount_path, '%s-ping-test-file' % uuidhelper.uuid())
        touch = shell.ShellCmd('timeout 60 touch %s' % test_file)
        touch(False)
        if touch.return_code == 124:
            raise Exception('unable to access the mount path[%s] of the nfs primary storage[uuid:%s] in 60s, timeout' %
                            (mount_path, cmd.uuid))
        elif touch.return_code != 0:
            touch.raise_error()

        shell.call('rm -f %s' % test_file)
        return jsonobject.dumps(NfsResponse())

    @kvmagent.replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeSizeRsp()

        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def merge_snapshot_to_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OfflineMergeSnapshotRsp()
        if not cmd.fullRebase:
            linux.qcow2_rebase(cmd.srcPath, cmd.destPath)
        else:
            tmp = os.path.join(os.path.dirname(cmd.destPath), '%s.qcow2' % uuidhelper.uuid())
            linux.qcow2_create_template(cmd.destPath, tmp)
            shell.call("mv %s %s" % (tmp, cmd.destPath))

        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def move_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MoveBitsRsp()
        if not os.path.exists(cmd.srcPath):
            rsp.error = "%s is not existing" % cmd.srcPath
            rsp.success = False
        else:
            dirname = os.path.dirname(cmd.destPath)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            shell.call("mv %s %s" % (cmd.srcPath, cmd.destPath))

        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def rebase_and_merge_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        snapshots = cmd.snapshotInstallPaths
        count = len(snapshots)
        for i in range(count):
            if i+1 < count:
                target = snapshots[i]
                backing_file = snapshots[i+1]
                linux.qcow2_rebase_no_check(backing_file, target)

        latest = snapshots[0]
        rsp = RebaseAndMergeSnapshotsResponse()
        workspace_dir = os.path.dirname(cmd.workspaceInstallPath)
        if not os.path.exists(workspace_dir):
            os.makedirs(workspace_dir)

        try:
            linux.qcow2_create_template(latest, cmd.workspaceInstallPath)
            rsp.size, rsp.actualSize = cmd.workspaceInstallPath
            self._set_capacity_to_response(cmd.uuid, rsp)
        except linux.LinuxError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def merge_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MergeSnapshotResponse()

        workspace_dir = os.path.dirname(cmd.workspaceInstallPath)
        if not os.path.exists(workspace_dir):
            os.makedirs(workspace_dir)

        try:
            linux.qcow2_create_template(cmd.snapshotInstallPath, cmd.workspaceInstallPath)
            rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.workspaceInstallPath)
            self._set_capacity_to_response(cmd.uuid, rsp)
        except linux.LinuxError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CopyToSftpBackupStorageResponse()

        def upload():
            if not os.path.exists(cmd.primaryStorageInstallPath):
                raise kvmagent.KvmError('cannot find %s' % cmd.primaryStorageInstallPath)

            linux.scp_upload(cmd.backupStorageHostName, cmd.backupStorageSshKey, cmd.primaryStorageInstallPath, cmd.backupStorageInstallPath, cmd.backupStorageUserName, cmd.backupStorageSshPort)

        try:
            upload()
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.upload_to_imagestore(cmd.hostname, cmd.primaryStorageInstallPath)

    @kvmagent.replyerror
    def commit_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.commit_to_imagestore(cmd.primaryStorageInstallPath)

    @kvmagent.replyerror
    def download_from_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.imagestore_client.download_from_imagestore(self.mount_path.get(cmd.uuid), cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)
        rsp = kvmagent.AgentResponse()
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_volume_from_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotResponse()

        install_path = cmd.snapshotInstallPath
        new_volume_path = os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
        linux.qcow2_clone(install_path, new_volume_path)
        rsp.newVolumeInstallPath = new_volume_path
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckIsBitsExistingRsp()
        rsp.existing = os.path.exists(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteResponse()

        if cmd.isFolder:
            shell.call('rm -rf %s' % cmd.installPath)
        else:
            shell.call('rm -f %s' % cmd.installPath)
            pdir = os.path.dirname(cmd.installPath)
            linux.rmdir_if_empty(pdir)

        logger.debug('successfully delete %s' % cmd.installPath)
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def remount(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MountResponse()
        linux.is_valid_nfs_url(cmd.url)

        if not linux.is_mounted(cmd.mountPath, cmd.url):
            linux.mount(cmd.url, cmd.mountPath, cmd.options)

        shell.call('mount -o remount %s' % cmd.mountPath)
        self.mount_path[cmd.uuid] = cmd.mountPath
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def mount(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MountResponse()
        linux.is_valid_nfs_url(cmd.url)
        
        if not linux.is_mounted(cmd.mountPath, cmd.url):
            linux.mount(cmd.url, cmd.mountPath, cmd.options)
        
        self.mount_path[cmd.uuid] = cmd.mountPath
        logger.debug(http.path_msg(self.MOUNT_PATH, 'mounted %s on %s' % (cmd.url, cmd.mountPath)))
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)
    
    @kvmagent.replyerror
    def umount(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UnmountResponse()
        if linux.is_mounted(path=cmd.mountPath): 
            ret = linux.umount(cmd.mountPath)
            if not ret: logger.warn(http.path_msg(self.UNMOUNT_PATH, 'unmount %s from %s failed' % (cmd.mountPath, cmd.url)))
        logger.debug(http.path_msg(self.UNMOUNT_PATH, 'umounted %s from %s' % (cmd.mountPath, cmd.url)))
        return jsonobject.dumps(rsp)
    
    @kvmagent.replyerror
    def get_capacity(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetCapacityResponse()
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)
        
    @kvmagent.replyerror
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateEmptyVolumeResponse()
        try:
            dirname = os.path.dirname(cmd.installUrl)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
                
            linux.qcow2_create(cmd.installUrl, cmd.size)
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = 'unable to create empty volume[uuid:%s, name:%s], %s' % (cmd.uuid, cmd.name, str(e))
            rsp.success = False
            return jsonobject.dumps(rsp)
        
        meta = VolumeMeta()
        meta.account_uuid = cmd.accountUuid
        meta.hypervisor_type = cmd.hypervisorType
        meta.name = cmd.name
        meta.uuid = cmd.volumeUuid
        meta.size = cmd.size
        meta_path = self._json_meta_file_name(cmd.installUrl)
        with open(meta_path, 'w') as fd:
            fd.write(jsonobject.dumps(meta, pretty=True))

        self._set_capacity_to_response(cmd.uuid, rsp)
        logger.debug('successfully create empty volume[uuid:%s, name:%s, size:%s] at %s' % (cmd.uuid, cmd.name, cmd.size, cmd.installUrl))
        return jsonobject.dumps(rsp)
        
    @kvmagent.replyerror
    def create_template_from_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateTemplateFromRootVolumeRsp()
        try:
            dirname = os.path.dirname(cmd.installPath)
            if not os.path.exists(dirname):
                os.makedirs(dirname, 0755)

            linux.qcow2_create_template(cmd.rootVolumePath, cmd.installPath)
        except linux.LinuxError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = 'unable to create image to root@%s:%s from root volume[%s], %s' % (cmd.sftpBackupStorageHostName,
                                                                                           cmd.installPath, cmd.rootVolumePath, str(e))
            rsp.success = False

        self._set_capacity_to_response(cmd.uuid, rsp)
        logger.debug('successfully created template[%s] from root volume[%s]' % (cmd.installPath, cmd.rootVolumePath))
        return jsonobject.dumps(rsp)
    
    @kvmagent.replyerror
    def download_from_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DownloadBitsFromSftpBackupStorageResponse()
        try:
            linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath, cmd.username, cmd.sshPort)
            logger.debug('successfully download %s/%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))
            self._set_capacity_to_response(cmd.uuid, rsp)
        except Exception as e:
            content = traceback.format_exc()
            logger.warn(content)
            err = "unable to download %s/%s, because %s" % (cmd.hostname, cmd.backupStorageInstallPath, str(e))
            rsp.error = err
            rsp.success = False
            
        return jsonobject.dumps(rsp)
        
    @kvmagent.replyerror
    def create_root_volume_from_template(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateRootVolumeFromTemplateResponse()
        if not os.path.exists(cmd.templatePathInCache):
            rsp.error = self.ERR_UNABLE_TO_FIND_IMAGE_IN_CACHE
            rsp.success = False
            return jsonobject.dumps(rsp)
            
        try:
            dirname = os.path.dirname(cmd.installUrl)
            if not os.path.exists(dirname):
                os.makedirs(dirname, 0775)
                
            linux.qcow2_clone(cmd.templatePathInCache, cmd.installUrl)
            logger.debug('successfully create root volume[%s] from template in cache[%s]' % (cmd.installUrl, cmd.templatePathInCache))
            meta = VolumeMeta()
            meta.account_uuid = cmd.accountUuid
            meta.hypervisor_type = cmd.hypervisorType
            meta.name = cmd.name
            meta.uuid = cmd.volumeUuid
            meta.size = os.path.getsize(cmd.templatePathInCache)
            meta_path = self._json_meta_file_name(cmd.installUrl)
            with open(meta_path, 'w') as fd:
                fd.write(jsonobject.dumps(meta, pretty=True))
            self._set_capacity_to_response(cmd.uuid, rsp)
            logger.debug('successfully create root volume[%s] from template in cache[%s]' % (cmd.installUrl, cmd.templatePathInCache))
        except Exception as e:
            content = traceback.format_exc()
            logger.warn(content)
            err = 'unable to clone qcow2 template[%s] to %s' % (cmd.templatePathInCache, cmd.installUrl)
            rsp.error = err
            rsp.success = False
            

        return jsonobject.dumps(rsp)

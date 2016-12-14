__author__ = 'frank'

import os.path
import traceback

import zstacklib.utils.uuidhelper as uuidhelper
from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import shell
from zstacklib.utils.report import Progress
from zstacklib.utils.bash import *

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        self.success = None
        self.error = None

class RevertVolumeFromSnapshotRsp(AgentResponse):
    def __init__(self):
        super(RevertVolumeFromSnapshotRsp, self).__init__()
        self.newVolumeInstallPath = None

class MergeSnapshotRsp(AgentResponse):
    def __init__(self):
        super(MergeSnapshotRsp, self).__init__()
        self.size = None
        self.actualSize = None

class RebaseAndMergeSnapshotsRsp(AgentResponse):
    def __init__(self):
        super(RebaseAndMergeSnapshotsRsp, self).__init__()
        self.size = None
        self.actualSize = None

class CheckBitsRsp(AgentResponse):
    def __init__(self):
        super(CheckBitsRsp, self).__init__()
        self.existing = False

class GetMd5Rsp(AgentResponse):
    def __init__(self):
        super(GetMd5Rsp, self).__init__()
        self.md5s = None

class GetBackingFileRsp(AgentResponse):
    def __init__(self):
        super(GetBackingFileRsp, self).__init__()
        self.size = None
        self.backingFilePath = None

class GetVolumeSizeRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.actualSize = None
        self.size = None

class GetVolumeBaseImagePathRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeBaseImagePathRsp, self).__init__()
        self.path = None

class GetQCOW2ReferenceRsp(AgentResponse):
    def __init__(self):
        super(GetQCOW2ReferenceRsp, self).__init__()
        self.referencePaths = None

class LocalStoragePlugin(kvmagent.KvmAgent):

    INIT_PATH = "/localstorage/init";
    GET_PHYSICAL_CAPACITY_PATH = "/localstorage/getphysicalcapacity";
    CREATE_EMPTY_VOLUME_PATH = "/localstorage/volume/createempty";
    CREATE_VOLUME_FROM_CACHE_PATH = "/localstorage/volume/createvolumefromcache";
    DELETE_BITS_PATH = "/localstorage/delete";
    UPLOAD_BIT_PATH = "/localstorage/sftp/upload";
    DOWNLOAD_BIT_PATH = "/localstorage/sftp/download";
    UPLOAD_TO_IMAGESTORE_PATH = "/localstorage/imagestore/upload"
    COMMIT_TO_IMAGESTORE_PATH = "/localstorage/imagestore/commit"
    DOWNLOAD_FROM_IMAGESTORE_PATH = "/localstorage/imagestore/download"
    REVERT_SNAPSHOT_PATH = "/localstorage/snapshot/revert";
    MERGE_SNAPSHOT_PATH = "/localstorage/snapshot/merge";
    MERGE_AND_REBASE_SNAPSHOT_PATH = "/localstorage/snapshot/mergeandrebase";
    OFFLINE_MERGE_PATH = "/localstorage/snapshot/offlinemerge";
    CREATE_TEMPLATE_FROM_VOLUME = "/localstorage/volume/createtemplate"
    CHECK_BITS_PATH = "/localstorage/checkbits"
    REBASE_ROOT_VOLUME_TO_BACKING_FILE_PATH = "/localstorage/volume/rebaserootvolumetobackingfile"
    VERIFY_SNAPSHOT_CHAIN_PATH = "/localstorage/snapshot/verifychain"
    REBASE_SNAPSHOT_BACKING_FILES_PATH = "/localstorage/snapshot/rebasebackingfiles"
    COPY_TO_REMOTE_BITS_PATH = "/localstorage/copytoremote"
    GET_MD5_PATH = "/localstorage/getmd5"
    CHECK_MD5_PATH = "/localstorage/checkmd5"
    GET_BACKING_FILE_PATH = "/localstorage/volume/getbackingfile"
    GET_VOLUME_SIZE = "/localstorage/volume/getsize"
    GET_BASE_IMAGE_PATH = "/localstorage/volume/getbaseimagepath"
    GET_QCOW2_REFERENCE = "/localstorage/getqcow2reference"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.GET_PHYSICAL_CAPACITY_PATH, self.get_physical_capacity)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.create_empty_volume)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.create_root_volume_from_template)
        http_server.register_async_uri(self.DELETE_BITS_PATH, self.delete)
        http_server.register_async_uri(self.DOWNLOAD_BIT_PATH, self.download_from_sftp)
        http_server.register_async_uri(self.UPLOAD_BIT_PATH, self.upload_to_sftp)
        http_server.register_async_uri(self.UPLOAD_TO_IMAGESTORE_PATH, self.upload_to_imagestore)
        http_server.register_async_uri(self.COMMIT_TO_IMAGESTORE_PATH, self.commit_to_imagestore)
        http_server.register_async_uri(self.DOWNLOAD_FROM_IMAGESTORE_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.REVERT_SNAPSHOT_PATH, self.revert_snapshot)
        http_server.register_async_uri(self.MERGE_SNAPSHOT_PATH, self.merge_snapshot)
        http_server.register_async_uri(self.MERGE_AND_REBASE_SNAPSHOT_PATH, self.merge_and_rebase_snapshot)
        http_server.register_async_uri(self.OFFLINE_MERGE_PATH, self.offline_merge_snapshot)
        http_server.register_async_uri(self.CREATE_TEMPLATE_FROM_VOLUME, self.create_template_from_volume)
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        http_server.register_async_uri(self.REBASE_ROOT_VOLUME_TO_BACKING_FILE_PATH, self.rebase_root_volume_to_backing_file)
        http_server.register_async_uri(self.VERIFY_SNAPSHOT_CHAIN_PATH, self.verify_backing_file_chain)
        http_server.register_async_uri(self.REBASE_SNAPSHOT_BACKING_FILES_PATH, self.rebase_backing_files)
        http_server.register_async_uri(self.COPY_TO_REMOTE_BITS_PATH, self.copy_bits_to_remote)
        http_server.register_async_uri(self.GET_MD5_PATH, self.get_md5)
        http_server.register_async_uri(self.CHECK_MD5_PATH, self.check_md5)
        http_server.register_async_uri(self.GET_BACKING_FILE_PATH, self.get_backing_file_path)
        http_server.register_async_uri(self.GET_VOLUME_SIZE, self.get_volume_size)
        http_server.register_async_uri(self.GET_BASE_IMAGE_PATH, self.get_volume_base_image_path)
        http_server.register_async_uri(self.GET_QCOW2_REFERENCE, self.get_qcow2_reference)

        self.path = None
        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    @kvmagent.replyerror
    def get_qcow2_reference(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        out = shell.call('find %s -type f' % cmd.searchingDir)

        rsp = GetQCOW2ReferenceRsp()
        rsp.referencePaths = []
        for f in out.split('\n'):
            f = f.strip(' \t\r\n')
            if not f: continue
            backing_file = linux.qcow2_get_backing_file(f)
            if backing_file == cmd.path:
                rsp.referencePaths.append(f)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeSizeRsp()
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_volume_base_image_path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeBaseImagePathRsp()
        rsp.path = linux.get_qcow2_base_image_path_recusively(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_backing_file_path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        out = linux.qcow2_get_backing_file(cmd.path)
        rsp = GetBackingFileRsp()

        if out:
            rsp.backingFilePath = out
            rsp.size = os.path.getsize(out)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_md5(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetMd5Rsp()
        rsp.md5s = []
        for to in cmd.md5s:
            progress = Progress()
            progress.processType = "LocalStorageMigrateVolume"
            progress.resourceUuid = to.resourceUuid
            progress.stages = {1: "0:10", 2: "10:90", 3: "90:100"}
            progress.stage = 1
            progress.total = os.path.getsize(to.path)
            _, md5, _ = bash_progress("md5sum %s | cut -d ' ' -f 1" % to.path, progress)
            rsp.md5s.append({
                'resourceUuid': to.resourceUuid,
                'path': to.path,
                'md5': md5
            })

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_md5(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for to in cmd.md5s:
            progress = Progress()
            progress.processType = "LocalStorageMigrateVolume"
            progress.resourceUuid = to.resourceUuid
            progress.stages = {1: "0:10", 2: "10:90", 3: "90:100"}
            progress.stage = 3
            progress.total = os.path.getsize(to.path)
            progress.flag = "end"
            _, dst_md5, _ = bash_progress("md5sum %s | cut -d ' ' -f 1" % to.path, progress)
            if dst_md5 != to.md5:
                raise Exception("MD5 unmatch. The file[uuid:%s, path:%s]'s md5 (src host:%s, dst host:%s)" %
                                (to.resourceUuid, to.path, to.md5, dst_md5))

        rsp = AgentResponse()
        return jsonobject.dumps(rsp)


    def _get_disk_capacity(self):
        return linux.get_disk_capacity_by_df(self.path)

    @kvmagent.replyerror
    @in_bash
    def copy_bits_to_remote(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        chain = sum([linux.qcow2_get_file_chain(p) for p in cmd.paths], [])
        total = 0
        progress = Progress()
        progress.processType = "LocalStorageMigrateVolume"
        progress.resourceUuid = cmd.uuid
        progress.stages = {1: "0:10", 2: "10:90", 3: "90:100"}
        progress.stage = 2
        for path in set(chain):
            total = total + os.path.getsize(path)

        progress.total = total
        for path in set(chain):
            PATH = path
            PASSWORD = cmd.dstPassword
            USER = cmd.dstUsername
            IP = cmd.dstIp
            PORT = (cmd.dstPort and cmd.dstPort or "22")

            bash_progress('rsync -avz --progress --relative {{PATH}} --rsh="/usr/bin/sshpass -p {{PASSWORD}} ssh -o StrictHostKeyChecking=no -p {{PORT}} -l {{USER}}" {{IP}}:/', progress)
            bash_errorout('/usr/bin/sshpass -p {{PASSWORD}} ssh -p {{PORT}} {{USER}}@{{IP}} "/bin/sync {{PATH}}"')

        rsp = AgentResponse()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def verify_backing_file_chain(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for sp in cmd.snapshots:
            if not os.path.exists(sp.path):
                raise Exception('cannot find the file[%s]' % sp.path)

            if sp.parentPath and not os.path.exists(sp.parentPath):
                raise Exception('cannot find the backing file[%s]' % sp.parentPath)

            if sp.parentPath:
                out = linux.qcow2_get_backing_file(sp.path)

                if sp.parentPath != out:
                    raise Exception("resource[Snapshot or Volume, uuid:%s, path:%s]'s backing file[%s] is not equal to %s" %
                                (sp.snapshotUuid, sp.path, out, sp.parentPath))

        return jsonobject.dumps(AgentResponse())

    @kvmagent.replyerror
    def rebase_backing_files(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for sp in cmd.snapshots:
            if sp.parentPath:
                linux.qcow2_rebase_no_check(sp.parentPath, sp.path)

        return jsonobject.dumps(AgentResponse())

    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        rsp.existing = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_template_from_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0755)

        linux.qcow2_create_template(cmd.volumePath, cmd.installPath)

        logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def revert_snapshot(self, req):
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
    def merge_and_rebase_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        snapshots = cmd.snapshotInstallPaths
        count = len(snapshots)
        for i in range(count):
            if i+1 < count:
                target = snapshots[i]
                backing_file = snapshots[i+1]
                linux.qcow2_rebase_no_check(backing_file, target)

        latest = snapshots[0]
        rsp = RebaseAndMergeSnapshotsRsp()
        workspace_dir = os.path.dirname(cmd.workspaceInstallPath)
        if not os.path.exists(workspace_dir):
            os.makedirs(workspace_dir)

        linux.qcow2_create_template(latest, cmd.workspaceInstallPath)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.workspaceInstallPath)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offline_merge_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        if not cmd.fullRebase:
            linux.qcow2_rebase(cmd.srcPath, cmd.destPath)
        else:
            tmp = os.path.join(os.path.dirname(cmd.destPath), '%s.qcow2' % uuidhelper.uuid())
            linux.qcow2_create_template(cmd.destPath, tmp)
            shell.call("mv %s %s" % (tmp, cmd.destPath))

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_physical_capacity(self, req):
        rsp = AgentResponse()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def rebase_root_volume_to_backing_file(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        linux.qcow2_rebase_no_check(cmd.backingFilePath, cmd.rootVolumePath)
        return jsonobject.dumps(AgentResponse())

    @kvmagent.replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.path = cmd.path

        if not os.path.exists(self.path):
            os.makedirs(self.path, 0755)

        rsp = AgentResponse()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        try:
            dirname = os.path.dirname(cmd.installUrl)
            if not os.path.exists(dirname):
                os.makedirs(dirname)

            if cmd.backingFile:
                linux.qcow2_create_with_backing_file(cmd.backingFile, cmd.installUrl)
            else:
                linux.qcow2_create(cmd.installUrl, cmd.size)
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = 'unable to create empty volume[uuid:%s, name:%s], %s' % (cmd.uuid, cmd.name, str(e))
            rsp.success = False
            return jsonobject.dumps(rsp)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installUrl))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_root_volume_from_template(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        if not os.path.exists(cmd.templatePathInCache):
            rsp.error = "UNABLE_TO_FIND_IMAGE_IN_CACHE"
            rsp.success = False
            logger.debug('error: %s: %s' % (rsp.error, cmd.templatePathInCache))
            return jsonobject.dumps(rsp)

        dirname = os.path.dirname(cmd.installUrl)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0775)

        linux.qcow2_clone(cmd.templatePathInCache, cmd.installUrl)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        shell.call('rm -f %s' % cmd.path)
        pdir = os.path.dirname(cmd.path)
        linux.rmdir_if_empty(pdir)

        logger.debug('successfully delete %s' % cmd.path)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        def upload():
            if not os.path.exists(cmd.primaryStorageInstallPath):
                raise kvmagent.KvmError('cannot find %s' % cmd.primaryStorageInstallPath)

            linux.scp_upload(cmd.hostname, cmd.sshKey, cmd.primaryStorageInstallPath, cmd.backupStorageInstallPath, cmd.username, cmd.sshPort)

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
    def download_from_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        try:
            linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath, cmd.username, cmd.sshPort)
            logger.debug('successfully download %s/%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))
        except Exception as e:
            content = traceback.format_exc()
            logger.warn(content)
            err = "unable to download %s/%s, because %s" % (cmd.hostname, cmd.backupStorageInstallPath, str(e))
            rsp.error = err
            rsp.success = False

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def download_from_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.imagestore_client.download_from_imagestore(self.path, cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)
        rsp = AgentResponse()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

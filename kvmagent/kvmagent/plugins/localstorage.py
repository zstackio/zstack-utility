__author__ = 'frank'

import os.path
import traceback

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
import zstacklib.utils.uuidhelper as uuidhelper

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

class RebaseAndMergeSnapshotsRsp(AgentResponse):
    def __init__(self):
        super(RebaseAndMergeSnapshotsRsp, self).__init__()
        self.size = None

class CheckBitsRsp(AgentResponse):
    def __init__(self):
        super(CheckBitsRsp, self).__init__()
        self.existing = False

class LocalStoragePlugin(kvmagent.KvmAgent):

    INIT_PATH = "/localstorage/init";
    GET_PHYSICAL_CAPACITY_PATH = "/localstorage/getphysicalcapacity";
    CREATE_EMPTY_VOLUME_PATH = "/localstorage/volume/createempty";
    CREATE_VOLUME_FROM_CACHE_PATH = "/localstorage/volume/createvolumefromcache";
    DELETE_BITS_PATH = "/localstorage/delete";
    UPLOAD_BIT_PATH = "/localstorage/sftp/upload";
    DOWNLOAD_BIT_PATH = "/localstorage/sftp/download";
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

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.GET_PHYSICAL_CAPACITY_PATH, self.get_physical_capacity)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.create_empty_volume)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.create_root_volume_from_template)
        http_server.register_async_uri(self.DELETE_BITS_PATH, self.delete)
        http_server.register_async_uri(self.DOWNLOAD_BIT_PATH, self.download_from_sftp)
        http_server.register_async_uri(self.UPLOAD_BIT_PATH, self.upload_to_sftp)
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

        self.path = None

    def stop(self):
        pass

    def _get_disk_capacity(self):
        return linux.get_disk_capacity_by_df(self.path)

    @kvmagent.replyerror
    def copy_bits_to_remote(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for path in cmd.paths:
            shell.call('rsync -a --relative %s --rsh="/usr/bin/sshpass -p %s ssh -o StrictHostKeyChecking=no -l %s" %s:/' %
                       (path, cmd.dstPassword, cmd.dstUsername, cmd.dstIp))

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
                out = shell.call("qemu-img info %s | grep 'backing file' | cut -d ':' -f 2" % sp.path)
                out = out.strip(' \t\r\n')

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
        rsp.size = os.path.getsize(cmd.workspaceInstallPath)

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
        rsp.size = os.path.getsize(cmd.workspaceInstallPath)

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
            shell.call('mkdir -p %s' % self.path)

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

            linux.qcow2_create(cmd.installUrl, cmd.size)
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = 'unable to create empty volume[uuid:%s, name:%s], %s' % (cmd.uuid, cmd.name, str(e))
            rsp.success = False
            return jsonobject.dumps(rsp)

        logger.debug('successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installUrl))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_root_volume_from_template(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        if not os.path.exists(cmd.templatePathInCache):
            rsp.error = "UNABLE_TO_FIND_IMAGE_IN_CACHE"
            rsp.success = False
            return jsonobject.dumps(rsp)

        dirname = os.path.dirname(cmd.installUrl)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0775)

        linux.qcow2_clone(cmd.templatePathInCache, cmd.installUrl)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        shell.call('rm -f %s' % cmd.path)
        pdir = os.path.dirname(cmd.path)
        linux.rmdir_if_empty(pdir)

        logger.debug('successfully delete %s' % cmd.path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        def upload():
            if not os.path.exists(cmd.primaryStorageInstallPath):
                raise kvmagent.KvmError('cannot find %s' % cmd.primaryStorageInstallPath)

            linux.scp_upload(cmd.hostname, cmd.sshKey, cmd.primaryStorageInstallPath, cmd.backupStorageInstallPath)

        try:
            upload()
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def download_from_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        try:
            linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)
            logger.debug('successfully download %s/%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))
        except Exception as e:
            content = traceback.format_exc()
            logger.warn(content)
            err = "unable to download %s/%s, because %s" % (cmd.hostname, cmd.backupStorageInstallPath, str(e))
            rsp.error = err
            rsp.success = False

        return jsonobject.dumps(rsp)


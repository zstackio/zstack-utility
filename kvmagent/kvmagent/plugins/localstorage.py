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

        self.path = None

    def stop(self):
        pass

    def _get_disk_capacity(self):
        total = linux.get_total_disk_size(self.path)
        used = linux.get_used_disk_apparent_size(self.path)
        return total, total-used

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


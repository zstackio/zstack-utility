__author__ = 'frank'

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.log as log
import zstacklib.utils.shell as shell
import zstacklib.utils.lichbd as lichbd
import zstacklib.utils.iptables as iptables
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.lock as lock
import zstacklib.utils.linux as linux
import zstacklib.utils.sizeunit as sizeunit
from zstacklib.utils import plugin
from zstacklib.utils.rollback import rollback, rollbackable
import os
import functools
import traceback
import pprint
import threading

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None

class InitRsp(AgentResponse):
    def __init__(self):
        super(InitRsp, self).__init__()
        self.fsid = None
        self.userKey = None

class DownloadRsp(AgentResponse):
    def __init__(self):
        super(DownloadRsp, self).__init__()
        self.size = None

class CpRsp(AgentResponse):
    def __init__(self):
        super(CpRsp, self).__init__()
        self.size = None

class CreateSnapshotRsp(AgentResponse):
    def __init__(self):
        super(CreateSnapshotRsp, self).__init__()
        self.size = None

def replyerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            rsp = AgentResponse()
            rsp.success = False
            rsp.error = str(e)
            logger.warn(err)
            return jsonobject.dumps(rsp)
    return wrap

class FusionstorAgent(object):

    INIT_PATH = "/fusionstor/primarystorage/init"
    CREATE_VOLUME_PATH = "/fusionstor/primarystorage/volume/createempty"
    DELETE_PATH = "/fusionstor/primarystorage/delete"
    CLONE_PATH = "/fusionstor/primarystorage/volume/clone"
    FLATTEN_PATH = "/fusionstor/primarystorage/volume/flatten"
    SFTP_DOWNLOAD_PATH = "/fusionstor/primarystorage/sftpbackupstorage/download"
    SFTP_UPLOAD_PATH = "/fusionstor/primarystorage/sftpbackupstorage/upload"
    ECHO_PATH = "/fusionstor/primarystorage/echo"
    CREATE_SNAPSHOT_PATH = "/fusionstor/primarystorage/snapshot/create"
    DELETE_SNAPSHOT_PATH = "/fusionstor/primarystorage/snapshot/delete"
    PROTECT_SNAPSHOT_PATH = "/fusionstor/primarystorage/snapshot/protect"
    ROLLBACK_SNAPSHOT_PATH = "/fusionstor/primarystorage/snapshot/rollback"
    UNPROTECT_SNAPSHOT_PATH = "/fusionstor/primarystorage/snapshot/unprotect"
    CP_PATH = "/fusionstor/primarystorage/volume/cp"
    DELETE_POOL_PATH = "/fusionstor/primarystorage/deletepool"

    http_server = http.HttpServer(port=7764)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DELETE_PATH, self.delete)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create)
        self.http_server.register_async_uri(self.CLONE_PATH, self.clone)
        self.http_server.register_async_uri(self.CREATE_SNAPSHOT_PATH, self.create_snapshot)
        self.http_server.register_async_uri(self.DELETE_SNAPSHOT_PATH, self.delete_snapshot)
        self.http_server.register_async_uri(self.PROTECT_SNAPSHOT_PATH, self.protect_snapshot)
        self.http_server.register_async_uri(self.UNPROTECT_SNAPSHOT_PATH, self.unprotect_snapshot)
        self.http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)
        self.http_server.register_async_uri(self.FLATTEN_PATH, self.flatten)
        self.http_server.register_async_uri(self.SFTP_DOWNLOAD_PATH, self.sftp_download)
        self.http_server.register_async_uri(self.SFTP_UPLOAD_PATH, self.sftp_upload)
        self.http_server.register_async_uri(self.CP_PATH, self.cp)
        self.http_server.register_async_uri(self.DELETE_POOL_PATH, self.delete_pool)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)

    def _set_capacity_to_response(self, rsp):
        total = lichbd.lichbd_get_capacity()
        used = lichbd.lichbd_get_used()
        logger.debug("-------- total: %s, used: %s ---------" % (total, used))

        rsp.totalCapacity = total
        rsp.availableCapacity = total - used

    def _get_file_size(self, path):
        lichbd_file = os.path.join("/iscsi", path)
        return lichbd.lichbd_file_size(lichbd_file)

    @replyerror
    def delete_pool(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for p in cmd.poolNames:
            p = os.path.join("/iscsi", p)
            lichbd.lichbd_unlink(p)
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def rollback_snapshot(self, req):
        logger.debug("============ rollback_snapshot ==============")
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        src_path = self.spath2src_normal(spath)
        snap_name = self.spath2normal(spath)
        snap_path = "%s@%s" % (src_path, snap_name)
        lichbd.lichbd_snap_rollback(snap_path)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def cp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        src_path = os.path.join("/iscsi", src_path)
        dst_path = os.path.join("/iscsi", dst_path)
        lichbd.lichbd_copy(src_path, dst_path)

        rsp = CpRsp()
        rsp.size = self._get_file_size(dst_path)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    def spath2src_normal(self, spath):
        #fusionstor://bak-t-95036217321343c2a8d64d32e085211e/382b3757a54045e5b7dbcfcdcfb07200@382b3757a54045e5b7dbcfcdcfb07200"
        image_name, sp_name = spath.split('@')
        return os.path.join("/iscsi", image_name)

    def spath2normal(self, spath):
        image_name, sp_name = spath.split('@')
        return os.path.join("/iscsi", image_name.split("/")[0], "snap_" + sp_name)

    @replyerror
    def create_snapshot(self, req):
        logger.debug("============ create_snapshot ==============")
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)
        src_path = self.spath2src_normal(spath)

        do_create = True
        image_name, sp_name = spath.split('@')
        if cmd.skipOnExisting:
            snaps = lichbd.lichbd_snap_list(src_path)
            for s in snaps:
                do_create = False

        if do_create:
            snap_path = "%s@%s" % (src_path, sp_name)
            lichbd.lichbd_snap_create(snap_path)

        rsp = CreateSnapshotRsp()
        rsp.size = self._get_file_size(src_path)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_snapshot(self, req):
        logger.debug("============ delete_snapshot ==============")
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        spath = self._normalize_install_path(cmd.snapshotPath)
        snap_path = "/iscsi/%s" % (spath)
        lichbd.lichbd_snap_delete(snap_path)
        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def unprotect_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)
        src_path = os.path.join("/iscsi", spath)
        lichbd.lichbd_snap_unprotect(src_path)

        return jsonobject.dumps(AgentResponse())

    @replyerror
    def protect_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)
        src_path = os.path.join("/iscsi", spath)
        lichbd.lichbd_snap_protect(src_path)

        rsp = AgentResponse()
        return jsonobject.dumps(rsp)

    @replyerror
    def clone(self, req):
        logger.debug("============ clone ==============")
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        src_path = os.path.join("/iscsi", src_path)
        dst_path = os.path.join("/iscsi", dst_path)

        lichbd.lichbd_mkdir(os.path.dirname(dst_path))
        lichbd.lichbd_snap_clone(src_path, dst_path)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def flatten(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.path)
        path = os.path.join("/iscsi", path)
        #shell.call('rbd flatten %s' % path)
        #lichbd.lichbd_snap_flatten(path)

        rsp = AgentResponse()
        rsp.success = False
        rsp.error = 'unsupported flatten'
        return jsonobject.dumps(rsp)

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        logger.debug("------- cmd: %s -------" % (cmd))

        rsp = InitRsp()
        rsp.fsid = "96a91e6d-892a-41f4-8fd2-4a18c9002425"
        rsp.userKey = "AQDVyu9VXrozIhAAuT2yMARKBndq9g3W8KUQvw=="
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    def _normalize_install_path(self, path):
        return path.lstrip('fusionstor:').lstrip('//')

    def _parse_install_path(self, path):
        return self._normalize_install_path(path).split('/')

    @replyerror
    def create(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        path = self._normalize_install_path(cmd.installPath)
        size_M = sizeunit.Byte.toMegaByte(cmd.size) + 1
        size = "%dM" % (size_M)
        path = "/iscsi/%s" % (path)

        lichbd.lichbd_create_raw(path, size)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def sftp_upload(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        src_path = self._normalize_install_path(cmd.primaryStorageInstallPath)
        prikey_file = linux.write_to_temp_file(cmd.sshKey)
        bs_folder = os.path.dirname(cmd.backupStorageInstallPath)

        rsp = AgentResponse()
        rsp.success = False
        rsp.error = 'unsupported SimpleSftpBackupStorage,  only supports fusionstor backupstorage'
        return jsonobject.dumps(rsp)


    @replyerror
    @rollback
    def sftp_download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        hostname = cmd.hostname
        prikey = cmd.sshKey
        pool, image_name = self._parse_install_path(cmd.primaryStorageInstallPath)
        tmp_image_name = 'tmp-%s' % image_name
        prikey_file = linux.write_to_temp_file(prikey)

        rsp = AgentResponse()
        rsp.success = False
        rsp.error = 'unsupported SimpleSftpBackupStorage,  only supports fusionstor backupstorage'
        #self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)

        path = os.path.join("/iscsi", path)
        lichbd.lichbd_unlink(path)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)


class FusionstorDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(FusionstorDaemon, self).__init__(pidfile)

    def run(self):
        logger.debug("------- start fusionstor... -----------")
        self.agent = FusionstorAgent()
        self.agent.http_server.start()

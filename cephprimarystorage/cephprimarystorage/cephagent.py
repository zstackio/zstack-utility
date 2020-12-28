import tempfile

__author__ = 'frank'

import pprint
import traceback

import zstacklib.utils.daemon as daemon
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.lock as lock
import zstacklib.utils.sizeunit as sizeunit
from zstacklib.utils.report import *
from zstacklib.utils.bash import *
from zstacklib.utils.rollback import rollback, rollbackable
from zstacklib.utils.plugin import completetask
import os
from zstacklib.utils import shell
from zstacklib.utils import plugin
from zstacklib.utils import linux
from zstacklib.utils import ceph
from zstacklib.utils import bash
from zstacklib.utils import qemu_img
from zstacklib.utils import traceable_shell
from imagestore import ImageStoreClient
from zstacklib.utils.linux import remote_shell_quote

logger = log.get_logger(__name__)


class CephPoolCapacity(object):
    def __init__(self, name, availableCapacity, replicatedSize, used, totalCapacity):
        self.name = name
        self.availableCapacity = availableCapacity
        self.replicatedSize = replicatedSize
        self.usedCapacity = used
        self.totalCapacity = totalCapacity


class AgentCommand(object):
    def __init__(self):
        pass


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None
        self.poolCapacities = None
        self.type = None

    def set_err(self, err):
        self.success = False
        self.error = err


class CephToCephMigrateVolumeSegmentCmd(AgentCommand):
    @log.sensitive_fields("dstMonSshPassword")
    def __init__(self):
        super(CephToCephMigrateVolumeSegmentCmd, self).__init__()
        self.parentUuid = None
        self.resourceUuid = None
        self.srcInstallPath = None
        self.dstInstallPath = None
        self.dstMonHostname = None
        self.dstMonSshUsername = None
        self.dstMonSshPassword = None
        self.dstMonSshPort = None  # type:int


class CheckIsBitsExistingRsp(AgentResponse):
    def __init__(self):
        super(CheckIsBitsExistingRsp, self).__init__()
        self.existing = None

class SetPasswordResponse(AgentResponse):
    def __init__(self):
        self.cephInstallPath = None
        self.vmUuid = None
        self.account = None
        self.password = None


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
        self.actualSize = None

class CreateSnapshotRsp(AgentResponse):
    def __init__(self):
        super(CreateSnapshotRsp, self).__init__()
        self.size = None
        self.actualSize = None

class RollbackSnapshotRsp(AgentResponse):
    def __init__(self):
        super(RollbackSnapshotRsp, self).__init__()
        self.size = None

class GetVolumeSizeRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None


class GetVolumeWatchersRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeWatchersRsp, self).__init__()
        self.watchers = None

class GetVolumeSnapshotSizeRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSnapshotSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class PingRsp(AgentResponse):
    def __init__(self):
        super(PingRsp, self).__init__()
        self.failure = None


class GetFactsRsp(AgentResponse):
    def __init__(self):
        super(GetFactsRsp, self).__init__()
        self.fsid = None
        self.monAddr = None

class ResizeVolumeRsp(AgentResponse):
    def __init__(self):
        super(ResizeVolumeRsp, self).__init__()
        self.size = None

class GetVolumeSnapInfosRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSnapInfosRsp, self).__init__()
        self.snapInfos = None

class CreateEmptyVolumeRsp(AgentResponse):
    def __init__(self):
        super(CreateEmptyVolumeRsp, self).__init__()
        self.size = 0


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


class CephAgent(plugin.TaskManager):
    INIT_PATH = "/ceph/primarystorage/init"
    CREATE_VOLUME_PATH = "/ceph/primarystorage/volume/createempty"
    DELETE_PATH = "/ceph/primarystorage/delete"
    CLONE_PATH = "/ceph/primarystorage/volume/clone"
    FLATTEN_PATH = "/ceph/primarystorage/volume/flatten"
    SFTP_DOWNLOAD_PATH = "/ceph/primarystorage/sftpbackupstorage/download"
    SFTP_UPLOAD_PATH = "/ceph/primarystorage/sftpbackupstorage/upload"
    ECHO_PATH = "/ceph/primarystorage/echo"
    CREATE_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/create"
    DELETE_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/delete"
    PURGE_SNAPSHOT_PATH = "/ceph/primarystorage/volume/purgesnapshots"
    COMMIT_IMAGE_PATH = "/ceph/primarystorage/snapshot/commit"
    PROTECT_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/protect"
    ROLLBACK_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/rollback"
    UNPROTECT_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/unprotect"
    CHECK_BITS_PATH = "/ceph/primarystorage/snapshot/checkbits"
    CP_PATH = "/ceph/primarystorage/volume/cp"
    DELETE_POOL_PATH = "/ceph/primarystorage/deletepool"
    GET_VOLUME_SIZE_PATH = "/ceph/primarystorage/getvolumesize"
    GET_VOLUME_WATCHES_PATH = "/ceph/primarystorage/getvolumewatchers"
    GET_VOLUME_SNAPSHOT_SIZE_PATH = "/ceph/primarystorage/getvolumesnapshotsize"
    PING_PATH = "/ceph/primarystorage/ping"
    GET_FACTS = "/ceph/primarystorage/facts"
    DELETE_IMAGE_CACHE = "/ceph/primarystorage/deleteimagecache"
    ADD_POOL_PATH = "/ceph/primarystorage/addpool"
    CHECK_POOL_PATH = "/ceph/primarystorage/checkpool"
    RESIZE_VOLUME_PATH = "/ceph/primarystorage/volume/resize"
    MIGRATE_VOLUME_SEGMENT_PATH = "/ceph/primarystorage/volume/migratesegment"
    GET_VOLUME_SNAPINFOS_PATH = "/ceph/primarystorage/volume/getsnapinfos"
    UPLOAD_IMAGESTORE_PATH = "/ceph/primarystorage/imagestore/backupstorage/commit"
    DOWNLOAD_IMAGESTORE_PATH = "/ceph/primarystorage/imagestore/backupstorage/download"
    DOWNLOAD_BITS_FROM_KVM_HOST_PATH = "/ceph/primarystorage/kvmhost/download"
    CANCEL_DOWNLOAD_BITS_FROM_KVM_HOST_PATH = "/ceph/primarystorage/kvmhost/download/cancel"
    JOB_CANCEL = "/job/cancel"

    http_server = http.HttpServer(port=7762)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        super(CephAgent, self).__init__()
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.ADD_POOL_PATH, self.add_pool)
        self.http_server.register_async_uri(self.CHECK_POOL_PATH, self.check_pool)
        self.http_server.register_async_uri(self.DELETE_PATH, self.delete)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create)
        self.http_server.register_async_uri(self.CLONE_PATH, self.clone)
        self.http_server.register_async_uri(self.COMMIT_IMAGE_PATH, self.commit_image)
        self.http_server.register_async_uri(self.CREATE_SNAPSHOT_PATH, self.create_snapshot)
        self.http_server.register_async_uri(self.DELETE_SNAPSHOT_PATH, self.delete_snapshot)
        self.http_server.register_async_uri(self.PURGE_SNAPSHOT_PATH, self.purge_snapshots)
        self.http_server.register_async_uri(self.PROTECT_SNAPSHOT_PATH, self.protect_snapshot)
        self.http_server.register_async_uri(self.UNPROTECT_SNAPSHOT_PATH, self.unprotect_snapshot)
        self.http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)
        self.http_server.register_async_uri(self.FLATTEN_PATH, self.flatten)
        self.http_server.register_async_uri(self.SFTP_DOWNLOAD_PATH, self.sftp_download)
        self.http_server.register_async_uri(self.SFTP_UPLOAD_PATH, self.sftp_upload)
        self.http_server.register_async_uri(self.CP_PATH, self.cp)
        self.http_server.register_async_uri(self.UPLOAD_IMAGESTORE_PATH, self.upload_imagestore)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGESTORE_PATH, self.download_imagestore)
        self.http_server.register_async_uri(self.DELETE_POOL_PATH, self.delete_pool)
        self.http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        self.http_server.register_async_uri(self.GET_VOLUME_WATCHES_PATH, self.get_volume_watchers)
        self.http_server.register_async_uri(self.GET_VOLUME_SNAPSHOT_SIZE_PATH, self.get_volume_snapshot_size)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_FACTS, self.get_facts)
        self.http_server.register_async_uri(self.DELETE_IMAGE_CACHE, self.delete_image_cache)
        self.http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        self.http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize_volume)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.MIGRATE_VOLUME_SEGMENT_PATH, self.migrate_volume_segment, cmd=CephToCephMigrateVolumeSegmentCmd())
        self.http_server.register_async_uri(self.GET_VOLUME_SNAPINFOS_PATH, self.get_volume_snapinfos)
        self.http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_KVM_HOST_PATH, self.download_from_kvmhost)
        self.http_server.register_async_uri(self.CANCEL_DOWNLOAD_BITS_FROM_KVM_HOST_PATH, self.cancel_download_from_kvmhost)
        self.http_server.register_async_uri(self.JOB_CANCEL, self.cancel)

        self.imagestore_client = ImageStoreClient()

    def _set_capacity_to_response(self, rsp):
        o = shell.call('ceph df -f json')
        df = jsonobject.loads(o)

        if df.stats.total_bytes__ is not None:
            total = long(df.stats.total_bytes_)
        elif df.stats.total_space__ is not None:
            total = long(df.stats.total_space__) * 1024
        else:
            raise Exception('unknown ceph df output: %s' % o)

        if df.stats.total_avail_bytes__ is not None:
            avail = long(df.stats.total_avail_bytes_)
        elif df.stats.total_avail__ is not None:
            avail = long(df.stats.total_avail_) * 1024
        else:
            raise Exception('unknown ceph df output: %s' % o)

        rsp.totalCapacity = total
        rsp.availableCapacity = avail
        if ceph.is_xsky():
            rsp.type = "xsky"

        if not df.pools:
            return

        pools = ceph.getCephPoolsCapacity()
        if not pools:
            return

        rsp.poolCapacities = []
        for pool in pools:
            poolCapacity = CephPoolCapacity(pool.poolName, pool.availableCapacity, pool.replicatedSize, pool.usedCapacity, pool.poolTotalSize)
            rsp.poolCapacities.append(poolCapacity)

    @in_bash
    def _get_file_actual_size(self, path):
        ret = bash.bash_r("rbd info %s | grep -q fast-diff" % path)

        # if no fast-diff supported and not xsky ceph skip actual size check
        if ret != 0 and not ceph.is_xsky():
            return None

        # use json format result first
        r, jstr = bash.bash_ro("rbd du %s --format json" % path)
        if r == 0 and bool(jstr):
            total_size = 0
            result = jsonobject.loads(jstr)
            if result.images is not None:
                for item in result.images:
                    total_size += int(item.used_size)
                return total_size

        r, size = bash.bash_ro("rbd du %s | awk 'END {if(NF==3) {print $3} else {print $4,$5} }' | sed s/[[:space:]]//g" % path, pipe_fail=True)
        if r != 0:
            return None

        size = size.strip()
        if not size:
            return None

        return sizeunit.get_size(size)

    def _get_file_size(self, path):
        o = shell.call('rbd --format json info %s' % path)
        o = jsonobject.loads(o)
        return long(o.size_)

    def _read_file_content(self, path):
        with open(path) as f:
            return f.read()

    @replyerror
    @in_bash
    def resize_volume(self, req):
        rsp = ResizeVolumeRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        pool, image_name = self._parse_install_path(cmd.installPath)
        path = self._normalize_install_path(cmd.installPath)

        shell.call("qemu-img resize -f raw rbd:%s/%s %s" % (pool, image_name, cmd.size))
        rsp.size = self._get_file_size(path)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    @lock.lock('delete_image_cache')
    def delete_image_cache(self, req):
        rsp = AgentResponse()

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        SP_PATH = self._normalize_install_path(cmd.snapshotPath)
        IMAGE_PATH = self._normalize_install_path(cmd.imagePath)

        if bash_r('rbd info {{IMAGE_PATH}}') != 0:
            return jsonobject.dumps(rsp)

        o = bash_o('rbd children {{SP_PATH}}')
        o = o.strip(' \t\r\n')
        if o:
            raise Exception('the image cache[%s] is still in used' % cmd.imagePath)

        bash_errorout('rbd snap unprotect {{SP_PATH}}')
        bash_errorout('rbd snap rm {{SP_PATH}}')
        bash_errorout('rbd rm {{IMAGE_PATH}}')
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        o = bash_o('ceph mon_status')
        mon_status = jsonobject.loads(o)
        fsid = mon_status.monmap.fsid_

        rsp = GetFactsRsp()

        facts = bash_o('ceph -s -f json')
        mon_facts = jsonobject.loads(facts)
        for mon in mon_facts.monmap.mons:
            ADDR = mon.addr.split(':')[0]
            if bash_r('ip route | grep -w {{ADDR}} > /dev/null') == 0:
                rsp.monAddr = ADDR
                break

        if not rsp.monAddr:
            raise Exception('cannot find mon address of the mon server[%s]' % cmd.monUuid)

        rsp.fsid = fsid
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        facts = bash_o('ceph -s -f json')
        mon_facts = jsonobject.loads(facts)
        found = False
        for mon in mon_facts.monmap.mons:
            if cmd.monAddr in mon.addr:
                found = True
                break

        rsp = PingRsp()

        if not found:
            rsp.success = False
            rsp.failure = "MonAddrChanged"
            rsp.error = 'The mon addr is changed on the mon server[uuid:%s], not %s anymore.' \
                        'Reconnect the ceph primary storage' \
                        ' may solve this issue' % (cmd.monUuid, cmd.monAddr)
            return jsonobject.dumps(rsp)

        def retry(times=3, sleep_time=3):
            def wrap(f):
                @functools.wraps(f)
                def inner(*args, **kwargs):
                    for i in range(0, times):
                        try:
                            return f(*args, **kwargs)
                        except Exception as e:
                            logger.error(e)
                            time.sleep(sleep_time)
                    rsp.error = ("Still failed after retry. Below is detail:\n %s" % e)

                return inner

            return wrap

        @retry()
        def doPing():
            # try to delete test file, ignore the result
            pool, objname = cmd.testImagePath.split('/')
            bash_r("rados -p '%s' rm '%s'" % (pool, objname))
            r, o, e = bash_roe("echo zstack | timeout 60 rados -p '%s' put '%s' -" % (pool, objname))
            if r != 0:
                rsp.success = False
                rsp.failure = "UnableToCreateFile"
                if r == 124:
                    # timeout happened
                    rsp.error = 'failed to create heartbeat object on ceph, timeout after 60s, %s %s' % (e, o)
                    raise Exception(rsp.error)
                else:
                    rsp.error = "%s %s" % (e, o)

        doPing()

        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)
        rsp = GetVolumeSizeRsp()
        rsp.size = self._get_file_size(path)
        rsp.actualSize = self._get_file_actual_size(path)
        return jsonobject.dumps(rsp)

    @replyerror
    def get_volume_watchers(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.volumePath)
        rsp = GetVolumeWatchersRsp()

        watchers_result = shell.call('timeout 10 rbd status %s' % path)
        if not watchers_result:
            return jsonobject.dumps(rsp)

        rsp.watchers = []
        for watcher in watchers_result.splitlines():
            if "watcher=" in watcher:
                rsp.watchers.append(watcher.lstrip())

        return jsonobject.dumps(rsp)

    @replyerror
    def get_volume_snapshot_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)
        rsp = GetVolumeSnapshotSizeRsp()
        rsp.size = self._get_file_size(path)
        rsp.actualSize = self._get_file_actual_size(path)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_pool(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for p in cmd.poolNames:
            shell.call('ceph osd pool delete %s %s --yes-i-really-really-mean-it' % (p, p))
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def rollback_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        shell.call('rbd snap rollback %s' % spath)
        rsp = RollbackSnapshotRsp()
        rsp.size = self._get_file_size(spath)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def cp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        if cmd.sendCommandUrl:
            Report.url = cmd.sendCommandUrl

        report = Report(cmd.threadContext, cmd.threadContextStack)
        report.processType = "CephCpVolume"
        _, PFILE = tempfile.mkstemp()
        stage = (cmd.threadContext['task-stage'], "10-90")[cmd.threadContext['task-stage'] is None]

        def _get_progress(synced):
            if not Report.url:
                return synced

            logger.debug("getProgress in ceph-agent")
            percent = shell.call("tail -1 %s | grep -o '1\?[0-9]\{1,2\}%%' | tail -1" % PFILE).strip(' \t\n\r%')
            if percent and Report.url:
                report.progress_report(get_exact_percent(percent, stage), "report")
            return synced

        t_shell = traceable_shell.get_shell(cmd)
        _, _, err = t_shell.bash_progress_1('rbd cp %s %s 2> %s' % (src_path, dst_path, PFILE), _get_progress)

        if os.path.exists(PFILE):
            os.remove(PFILE)

        if err:
            shell.run('rbd rm %s' % dst_path)
            raise err

        rsp = CpRsp()
        rsp.size = self._get_file_size(dst_path)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def upload_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.upload_imagestore(cmd, req)

    @replyerror
    def commit_image(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)
        dpath = self._normalize_install_path(cmd.dstPath)

        shell.call('rbd snap protect %s' % spath, exception=not cmd.ignoreError)
        shell.call('rbd clone %s %s' % (spath, dpath))

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        rsp.size = self._get_file_size(dpath)
        return jsonobject.dumps(rsp)

    @replyerror
    def download_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.download_imagestore(cmd)

    @replyerror
    def create_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        do_create = True
        if cmd.skipOnExisting:
            image_name, sp_name = spath.split('@')
            o = shell.call('rbd --format json snap ls %s' % image_name)
            o = jsonobject.loads(o)
            for s in o:
                if s.name_ == sp_name:
                    do_create = False

        if do_create:
            o = shell.ShellCmd('rbd snap create %s' % spath)
            o(False)
            if o.return_code != 0:
                shell.run("rbd snap rm %s" % spath)
                o.raise_error()


        rsp = CreateSnapshotRsp()
        rsp.size = self._get_file_size(spath)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        spath = self._normalize_install_path(cmd.snapshotPath)

        shell.call('rbd snap rm %s' % spath)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def purge_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vpath = self._normalize_install_path(cmd.volumePath)
        shell.call('rbd snap purge %s' % vpath)
        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def unprotect_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        shell.call('rbd snap unprotect %s' % spath)

        return jsonobject.dumps(AgentResponse())

    @replyerror
    def protect_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        shell.call('rbd snap protect %s' % spath, exception=not cmd.ignoreError)

        rsp = AgentResponse()
        return jsonobject.dumps(rsp)

    @replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)
        rsp = CheckIsBitsExistingRsp()
        try:
            shell.call('rbd info %s' % path)
        except Exception as e:
            if 'No such file or directory' in str(e):
                rsp.existing = False
                return jsonobject.dumps(rsp)
            else:
                raise e
        rsp.existing = True
        return jsonobject.dumps(rsp)

    @replyerror
    def clone(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        shell.call('rbd clone %s %s' % (src_path, dst_path))

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def flatten(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.path)

        shell.call('rbd flatten %s' % path)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @replyerror
    def add_pool(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        existing_pools = shell.call('ceph osd pool ls')

        pool_names = existing_pools.split("\n")

        realname = eval('u"' + cmd.poolName + '"').encode('utf-8')
        if not cmd.isCreate and realname not in pool_names:
            raise Exception('cannot find the pool[%s] in the ceph cluster, you must create it manually' % realname)

        if cmd.isCreate and realname in pool_names:
            raise Exception('have pool named[%s] in the ceph cluster, can\'t create new pool with same name' % realname)

        if (ceph.is_xsky() or ceph.is_sandstone()) and cmd.isCreate and realname not in pool_names:
                raise Exception(
                    'current ceph storage type only support add exist pool, please create it manually')

        if realname not in pool_names:
            shell.call('ceph osd pool create %s 128' % realname)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    @replyerror
    def check_pool(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        existing_pools = shell.call('ceph osd lspools')
        for pool in cmd.pools:
            if pool.name not in existing_pools:
                raise Exception('cannot find pool[%s] in the ceph cluster, you must create it manually' % pool.name)

        return jsonobject.dumps(AgentResponse())

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        o = shell.call('ceph mon_status')
        mon_status = jsonobject.loads(o)
        fsid = mon_status.monmap.fsid_

        existing_pools = shell.call('ceph osd lspools')
        for pool in cmd.pools:
            if pool.name in existing_pools:
                continue

            if pool.predefined:
                raise Exception('cannot find pool[%s] in the ceph cluster, you must create it manually' % pool.name)
            if ceph.is_xsky() or ceph.is_sandstone():
                raise Exception('The ceph storage type to be added does not support auto initialize pool, please create it manually')

            shell.call('ceph osd pool create %s 128' % pool.name)

        rsp = InitRsp()

        if cmd.nocephx is False:
            o = shell.call("ceph -f json auth get-or-create client.zstack mon 'allow r' osd 'allow *' 2>/dev/null").strip(
                ' \n\r\t')
            o = jsonobject.loads(o)
            rsp.userKey = o[0].key_

        rsp.fsid = fsid
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    def _normalize_install_path(self, path):
        return path.replace('ceph://', '')

    def _parse_install_path(self, path):
        return self._normalize_install_path(path).split('/')

    @replyerror
    def create(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        path = self._normalize_install_path(cmd.installPath)
        rsp = CreateEmptyVolumeRsp()

        call_string = None
        if ceph.is_xsky():
            # do NOT round to MB
            call_string = 'rbd create --size %dB --image-format 2 %s' % (cmd.size, path)
            rsp.size = cmd.size
        else:
            size_M = sizeunit.Byte.toMegaByte(cmd.size) + 1
            call_string = 'rbd create --size %s --image-format 2 %s' % (size_M, path)
            rsp.size = cmd.size + sizeunit.MegaByte.toByte(1)

        if cmd.shareable:
            call_string = call_string + " --image-shared"

        skip_cmd = "rbd info %s ||" % path if cmd.skipIfExisting else ""
        shell.call(skip_cmd + call_string)


        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def sftp_upload(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        src_path = self._normalize_install_path(cmd.primaryStorageInstallPath)
        prikey_file = linux.write_to_temp_file(cmd.sshKey)

        bs_folder = os.path.dirname(cmd.backupStorageInstallPath)
        shell.call('ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s "mkdir -p %s"' %
                   (cmd.sshPort, prikey_file, cmd.hostname, bs_folder))

        try:
            shell.call("set -o pipefail; rbd export %s - | ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s 'cat > %s'" %
                       (src_path, prikey_file, cmd.hostname, cmd.backupStorageInstallPath))
        finally:
            os.remove(prikey_file)

        return jsonobject.dumps(AgentResponse())

    @replyerror
    def sftp_download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.primaryStorageInstallPath)

        self.do_sftp_download(cmd, pool, image_name)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @rollback
    @in_bash
    def do_sftp_download(self, cmd, pool, image_name):
        hostname = cmd.hostname
        prikey = cmd.sshKey
        port = cmd.sshPort

        if cmd.bandWidth is not None:
            bandWidth = 'pv -q -L %s |' % cmd.bandWidth
        else:
            bandWidth = ''

        tmp_image_name = 'tmp-%s' % image_name

        prikey_file = linux.write_to_temp_file(prikey)

        @rollbackable
        def _0():
            tpath = "%s/%s" % (pool, tmp_image_name)
            shell.call('rbd info %s > /dev/null && rbd rm %s' % (tpath, tpath))

        _0()

        def rbd_check_rm(pool, name):
            if shell.run('rbd info %s/%s' % (pool, name)) == 0:
                shell.check_run('rbd rm %s/%s' % (pool, name))

        try:
            rbd_check_rm(pool, tmp_image_name)
            shell.call('set -o pipefail; ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s cat %s | %s rbd import --image-format 2 - %s/%s' % (port, prikey_file, hostname, remote_shell_quote(cmd.backupStorageInstallPath), bandWidth, pool, tmp_image_name))
        finally:
            os.remove(prikey_file)

        @rollbackable
        def _1():
            shell.call('rbd rm %s/%s' % (pool, tmp_image_name))

        _1()

        file_format = shell.call(
            "set -o pipefail; %s rbd:%s/%s | grep 'file format' | cut -d ':' -f 2" %
                    (qemu_img.subcmd('info'), pool, tmp_image_name))
        file_format = file_format.strip()
        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)

        rbd_check_rm(pool, image_name)
        if file_format == 'qcow2':
            conf_path = None
            try:
                with open('/etc/ceph/ceph.conf', 'r') as fd:
                    conf = fd.read()
                    conf = '%s\n%s\n' % (conf, 'rbd default format = 2')
                    conf_path = linux.write_to_temp_file(conf)

                shell.call('%s -f qcow2 -O rbd rbd:%s/%s rbd:%s/%s:conf=%s' % (
                    qemu_img.subcmd('convert'), pool, tmp_image_name, pool, image_name, conf_path))
                shell.call('rbd rm %s/%s' % (pool, tmp_image_name))
            finally:
                if conf_path:
                    os.remove(conf_path)
        else:
            shell.call('rbd mv %s/%s %s/%s' % (pool, tmp_image_name, pool, image_name))

    def cancel_sftp_download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        def check():
            return shell.run("rbd ls %s | grep -q %s" % (pool, image_name)) != 0

        def remove(target_name):
            return shell.run("rbd info {0}/{1} || rbd rm {0}/{1}".format(pool, target_name)) == 0

        pool, image_name = self._parse_install_path(cmd.primaryStorageInstallPath)
        tmp_image_name = 'tmp-%s' % image_name

        if check():
            return jsonobject.dumps(rsp)

        for image in (tmp_image_name, image_name):
            shell.run("pkill -9 -f '%s'" % image)
            linux.wait_callback_success(remove, image, timeout=30)

        if not check():
            rsp.set_err("remove image %s/%s fail" % (pool, image_name))

        return jsonobject.dumps(rsp)

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)
        rsp = AgentResponse()
        try:
            o = shell.call('rbd snap ls --format json %s' % path)
        except Exception as e:
            if 'No such file or directory' not in str(e):
                raise
            logger.warn('delete %s;encounter %s' % (cmd.installPath, str(e)))
            return jsonobject.dumps(rsp)

        o = jsonobject.loads(o)
        if len(o) > 0:
            raise Exception('unable to delete %s; the volume still has snapshots' % cmd.installPath)

        @linux.retry(times=30, sleep_time=5)
        def do_deletion():
            shell.call('rbd rm %s' % path)

        do_deletion()

        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    def _get_dst_volume_size(self, dst_install_path, dst_mon_addr, dst_mon_user, dst_mon_passwd, dst_mon_port):
        o = linux.sshpass_call(dst_mon_addr, dst_mon_passwd, "rbd --format json info %s" % dst_install_path, dst_mon_user, dst_mon_port)
        o = jsonobject.loads(o)
        return long(o.size_)

    def _resize_dst_volume(self, dst_install_path, size, dst_mon_addr, dst_mon_user, dst_mon_passwd, dst_mon_port):
        r, _, e = linux.sshpass_run(dst_mon_addr, dst_mon_passwd, "qemu-img resize -f raw rbd:%s %s" % (dst_install_path, size), dst_mon_user, dst_mon_port)
        if r != 0:
            logger.error('failed to resize volume %s before migrate, cause: %s' % (dst_install_path, e))
            return r
        return 0

    def _migrate_volume_segment(self, parent_uuid, resource_uuid, src_install_path,
                                dst_install_path, dst_mon_addr, dst_mon_user, dst_mon_passwd, dst_mon_port, cmd):
        src_install_path = self._normalize_install_path(src_install_path)
        dst_install_path = self._normalize_install_path(dst_install_path)

        traceable_bash = traceable_shell.get_shell(cmd)
        ssh_cmd, tmp_file = linux.build_sshpass_cmd(dst_mon_addr, dst_mon_passwd, "tee >(md5sum >/tmp/%s_dst_md5) | rbd import-diff - %s"
                                                    % (resource_uuid, dst_install_path), dst_mon_user, dst_mon_port)
        r, _, e = traceable_bash.bash_roe('set -o pipefail; rbd export-diff {FROM_SNAP} {SRC_INSTALL_PATH} - | tee >(md5sum >/tmp/{RESOURCE_UUID}_src_md5) | {SSH_CMD}'.format(
            RESOURCE_UUID=resource_uuid,
            SSH_CMD=ssh_cmd,
            SRC_INSTALL_PATH=src_install_path,
            FROM_SNAP='--from-snap ' + parent_uuid if parent_uuid != '' else ''))
        linux.rm_file_force(tmp_file)
        if r != 0:
            logger.error('failed to migrate volume %s: %s' % (src_install_path, e))
            return r

        # compare md5sum of src/dst segments
        src_segment_md5 = self._read_file_content('/tmp/%s_src_md5' % resource_uuid)
        dst_segment_md5 = linux.sshpass_call(dst_mon_addr, dst_mon_passwd, 'cat /tmp/%s_dst_md5' % resource_uuid, dst_mon_user, dst_mon_port)
        if src_segment_md5 != dst_segment_md5:
            logger.error('check sum mismatch after migration: %s' % src_install_path)
            return -1
        return 0

    @replyerror
    @in_bash
    def migrate_volume_segment(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        src_install_path = self._normalize_install_path(cmd.srcInstallPath)
        dst_install_path = self._normalize_install_path(cmd.dstInstallPath)
        src_size = self._get_file_size(src_install_path)
        dst_size = self._get_dst_volume_size(dst_install_path, cmd.dstMonHostname, cmd.dstMonSshUsername, cmd.dstMonSshPassword, cmd.dstMonSshPort)
        if dst_size > src_size:
            if cmd.isXsky:
                # xsky / ceph -> xsky, size must be equal
                rsp.success = False
                rsp.error = "Failed to migrate volume segment because dst size: %s > src size: %s" % (dst_size, src_size)
                return jsonobject.dumps(rsp)
            elif ceph.is_xsky() == False:
                # ceph -> ceph, don't check size
                rsp.success = True
            else:
                # xsky -> ceph, not supported
                rsp.success = False
                rsp.error = "Failed to migrate volume segment because xsky migrate to ceph is not supported now"
                return jsonobject.dumps(rsp)
        if dst_size < src_size:
            ret = self._resize_dst_volume(dst_install_path, src_size, cmd.dstMonHostname, cmd.dstMonSshUsername, cmd.dstMonSshPassword, cmd.dstMonSshPort)
            if ret != 0:
                rsp.success = False
                rsp.error = "Failed to resize volume before migrate."
                return jsonobject.dumps(rsp)

        ret = self._migrate_volume_segment(cmd.parentUuid, cmd.resourceUuid, cmd.srcInstallPath,
                                           cmd.dstInstallPath, cmd.dstMonHostname, cmd.dstMonSshUsername,
                                           cmd.dstMonSshPassword, cmd.dstMonSshPort, cmd)
        if ret != 0:
            rsp.success = False
            rsp.error = "Failed to migrate volume segment from one ceph primary storage to another."
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def get_volume_snapinfos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vpath = self._normalize_install_path(cmd.volumePath)
        ret = shell.call('rbd --format=json snap ls %s' % vpath)
        rsp = GetVolumeSnapInfosRsp()
        rsp.snapInfos = jsonobject.loads(ret)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @completetask
    @rollback
    def download_from_kvmhost(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        pool, image_name = self._parse_install_path(cmd.primaryStorageInstallPath)

        def validate_task_result_existing(_):
            return shell.run("rbd ls %s | grep -q %s" % (pool, image_name)) == 0

        last_task = self.load_and_save_task(req, rsp, validate_task_result_existing, None)
        if last_task and last_task.agent_pid == os.getpid():
            rsp = self.wait_task_complete(last_task)
            return jsonobject.dumps(rsp)

        self.do_sftp_download(cmd, pool, image_name)
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def cancel_download_from_kvmhost(self, req):
        return self.cancel_sftp_download(req)

    @replyerror
    def cancel(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        if not traceable_shell.cancel_job(cmd):
            rsp.success = False
            rsp.error = "no matched job to cancel"
        return jsonobject.dumps(rsp)

class CephDaemon(daemon.Daemon):
    def __init__(self, pidfile, py_process_name):
        super(CephDaemon, self).__init__(pidfile, py_process_name)

    def run(self):
        self.agent = CephAgent()
        self.agent.http_server.start()


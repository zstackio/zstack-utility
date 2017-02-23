__author__ = 'frank'

import pprint
import traceback

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.linux as linux
import zstacklib.utils.lock as lock
import zstacklib.utils.sizeunit as sizeunit
from zstacklib.utils import log
from zstacklib.utils.bash import *
from zstacklib.utils.rollback import rollback, rollbackable
import os
from zstacklib.utils import shell

logger = log.get_logger(__name__)


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None

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


class GetVolumeSizeRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
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


class CephAgent(object):
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
    COMMIT_IMAGE_PATH = "/ceph/primarystorage/snapshot/commit"
    PROTECT_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/protect"
    ROLLBACK_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/rollback"
    UNPROTECT_SNAPSHOT_PATH = "/ceph/primarystorage/snapshot/unprotect"
    CHECK_BITS_PATH = "/ceph/primarystorage/snapshot/checkbits"
    CP_PATH = "/ceph/primarystorage/volume/cp"
    DELETE_POOL_PATH = "/ceph/primarystorage/deletepool"
    GET_VOLUME_SIZE_PATH = "/ceph/primarystorage/getvolumesize"
    PING_PATH = "/ceph/primarystorage/ping"
    GET_FACTS = "/ceph/primarystorage/facts"
    DELETE_IMAGE_CACHE = "/ceph/primarystorage/deleteimagecache"
    ADD_POOL_PATH = "/ceph/primarystorage/addpool"

    http_server = http.HttpServer(port=7762)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.ADD_POOL_PATH, self.add_pool)
        self.http_server.register_async_uri(self.DELETE_PATH, self.delete)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create)
        self.http_server.register_async_uri(self.CLONE_PATH, self.clone)
        self.http_server.register_async_uri(self.COMMIT_IMAGE_PATH, self.commit_image)
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
        self.http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_FACTS, self.get_facts)
        self.http_server.register_async_uri(self.DELETE_IMAGE_CACHE, self.delete_image_cache)
        self.http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)

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

    def _get_file_size(self, path):
        o = shell.call('rbd --format json info %s' % path)
        o = jsonobject.loads(o)
        return long(o.size_)


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
            bash_r('rbd rm %s' % cmd.testImagePath)
            r, o, e = bash_roe('timeout 60 rbd create %s --image-format 2 --size 1' % cmd.testImagePath)
            if r != 0:
                rsp.success = False
                rsp.failure = "UnableToCreateFile"
                if r == 124:
                    # timeout happened
                    rsp.error = 'failed to create temporary file on ceph, timeout after 60s, %s %s' % (e, o)
                    raise Exception(rsp.error)
                else:
                    rsp.error = "%s %s" % (e, o)

        doPing()
        return jsonobject.dumps(rsp)

    @replyerror
    def get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)
        rsp = GetVolumeSizeRsp()
        rsp.size = self._get_file_size(path)
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
        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def cp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        shell.call('rbd cp %s %s' % (src_path, dst_path))

        rsp = CpRsp()
        rsp.size = self._get_file_size(dst_path)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

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
            shell.call('rbd snap create %s' % spath)

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
            shell.call('rbd snap ls --format json %s' % path)
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
        existing_pools = shell.call('ceph osd lspools')

        if cmd.errorIfNotExist and cmd.poolName not in existing_pools:
            raise Exception('cannot find the pool[%s] in the ceph cluster, you must create it manually' % cmd.poolName)

        if cmd.poolName not in existing_pools:
            shell.call('ceph osd pool create %s 100' % cmd.poolName)

        return jsonobject.dumps(AgentResponse())


    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        o = shell.call('ceph mon_status')
        mon_status = jsonobject.loads(o)
        fsid = mon_status.monmap.fsid_

        existing_pools = shell.call('ceph osd lspools')
        for pool in cmd.pools:
            if pool.predefined and pool.name not in existing_pools:
                raise Exception('cannot find pool[%s] in the ceph cluster, you must create it manually' % pool.name)
            elif pool.name not in existing_pools:
                shell.call('ceph osd pool create %s 100' % pool.name)

        o = shell.call("ceph -f json auth get-or-create client.zstack mon 'allow r' osd 'allow *' 2>/dev/null").strip(
            ' \n\r\t')
        o = jsonobject.loads(o)

        rsp = InitRsp()
        rsp.fsid = fsid
        rsp.userKey = o[0].key_
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
        size_M = sizeunit.Byte.toMegaByte(cmd.size) + 1
        call_string = 'rbd create --size %s --image-format 2 %s ' % (size_M, path)
        if cmd.shareable:
            call_string = call_string + " --image-shared"
        shell.call(call_string)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def sftp_upload(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        src_path = self._normalize_install_path(cmd.primaryStorageInstallPath)
        prikey_file = linux.write_to_temp_file(cmd.sshKey)

        bs_folder = os.path.dirname(cmd.backupStorageInstallPath)
        shell.call('ssh -p %d -o StrictHostKeyChecking=no -i %s root@%s "mkdir -p %s"' %
                   (cmd.sshPort, prikey_file, cmd.hostname, bs_folder))

        try:
            shell.call("set -o pipefail; rbd export %s - | ssh -o StrictHostKeyChecking=no -i %s root@%s 'cat > %s'" %
                       (src_path, prikey_file, cmd.hostname, cmd.backupStorageInstallPath))
        finally:
            os.remove(prikey_file)

        return jsonobject.dumps(AgentResponse())

    @replyerror
    @rollback
    def sftp_download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        hostname = cmd.hostname
        prikey = cmd.sshKey
        port = cmd.sshPort

        pool, image_name = self._parse_install_path(cmd.primaryStorageInstallPath)
        tmp_image_name = 'tmp-%s' % image_name

        prikey_file = linux.write_to_temp_file(prikey)

        @rollbackable
        def _0():
            tpath = "%s/%s" % (pool, tmp_image_name)
            shell.call('rbd info %s > /dev/null && rbd rm %s' % (tpath, tpath))

        _0()

        try:
            shell.call(
                'set -o pipefail; ssh -p %d -o StrictHostKeyChecking=no -i %s root@%s "cat %s" | rbd import --image-format 2 - %s/%s' %
                (port, prikey_file, hostname, cmd.backupStorageInstallPath, pool, tmp_image_name))
        finally:
            os.remove(prikey_file)

        @rollbackable
        def _1():
            shell.call('rbd rm %s/%s' % (pool, tmp_image_name))

        _1()

        file_format = shell.call(
            "set -o pipefail; qemu-img info rbd:%s/%s | grep 'file format' | cut -d ':' -f 2" % (pool, tmp_image_name))
        file_format = file_format.strip()
        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)

        if file_format == 'qcow2':
            conf_path = None
            try:
                with open('/etc/ceph/ceph.conf', 'r') as fd:
                    conf = fd.read()
                    conf = '%s\n%s\n' % (conf, 'rbd default format = 2')
                    conf_path = linux.write_to_temp_file(conf)

                shell.call('qemu-img convert -f qcow2 -O rbd rbd:%s/%s rbd:%s/%s:conf=%s' % (
                    pool, tmp_image_name, pool, image_name, conf_path))
                shell.call('rbd rm %s/%s' % (pool, tmp_image_name))
            finally:
                if conf_path:
                    os.remove(conf_path)
        else:
            shell.call('rbd mv %s/%s %s/%s' % (pool, tmp_image_name, pool, image_name))

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)
        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
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

        shell.call('rbd rm %s' % path)

        return jsonobject.dumps(rsp)


class CephDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(CephDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = CephAgent()
        self.agent.http_server.start()


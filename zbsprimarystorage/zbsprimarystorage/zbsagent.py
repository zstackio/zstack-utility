__author__ = 'Xingwei Yu'

import traceback
import pprint
import os

import zbsutils
import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils import plugin
from zstacklib.utils import daemon
from zstacklib.utils import linux
from zstacklib.utils import traceable_shell
from zstacklib.utils.report import *
from zstacklib.utils.bash import *


log.configure_log('/var/log/zstack/zbs-primarystorage.log')
logger = log.get_logger(__name__)


FORMAT_CBD_LUN_PATH = "cbd:{}/{}/{}"
FORMAT_CBD_SNAPSHOT_PATH = FORMAT_CBD_LUN_PATH + "@{}"
ZBS_CLIENT_CONF = "/etc/zbs/client.conf"


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

    def set_error(self, error):
        self.success = False
        self.error = error


class CbdToNbdRsp(AgentResponse):
    def __init__(self):
        super(CbdToNbdRsp, self).__init__()
        self.ip = None
        self.port = 0


class ExpandVolumeRsp(AgentResponse):
    def __init__(self):
        super(ExpandVolumeRsp, self).__init__()
        self.size = 0


class CopyRsp(AgentResponse):
    def __init__(self):
        super(CopyRsp, self).__init__()
        self.installPath = None
        self.size = 0


class RollbackSnapshotRsp(AgentResponse):
    def __init__(self):
        super(RollbackSnapshotRsp, self).__init__()
        self.installPath = None
        self.size = 0
        self.actualSize = 0


class QueryVolumeRsp(AgentResponse):
    def __init__(self):
        super(QueryVolumeRsp, self).__init__()
        self.size = 0
        self.actualSize = 0


class CloneVolumeRsp(AgentResponse):
    def __init__(self):
        super(CloneVolumeRsp, self).__init__()
        self.installPath = None
        self.size = 0
        self.actualSize = 0


class CreateSnapshotRsp(AgentResponse):
    def __init__(self):
        super(CreateSnapshotRsp, self).__init__()
        self.size = 0
        self.actualSize = 0


class CreateVolumeRsp(AgentResponse):
    def __init__(self):
        super(CreateVolumeRsp, self).__init__()
        self.size = 0
        self.actualSize = 0


class GetCapacityRsp(AgentResponse):
    def __init__(self):
        super(GetCapacityRsp, self).__init__()
        self.capacity = 0
        self.usedSize = 0


class GetFactsRsp(AgentResponse):
    def __init__(self):
        super(GetFactsRsp, self).__init__()
        self.version = None


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


def get_logical_pool_name(install_path):
    return install_path.split(":")[1].split("/")[1]


def get_lun_name(install_path):
    return install_path.split(":")[1].split("/")[2].split("@")[0]


def get_snapshot_name(install_path):
    return install_path.split(":")[1].split("/")[2].split("@")[1]


class ZbsAgent(plugin.TaskManager):
    ECHO_PATH = "/zbs/primarystorage/echo"
    GET_FACTS_PATH = "/zbs/primarystorage/facts"
    GET_CAPACITY_PATH = "/zbs/primarystorage/capacity"
    COPY_PATH = "/zbs/primarystorage/copy"
    CREATE_VOLUME_PATH = "/zbs/primarystorage/volume/create"
    DELETE_VOLUME_PATH = "/zbs/primarystorage/volume/delete"
    QUERY_VOLUME_PATH = "/zbs/primarystorage/volume/query"
    CLONE_VOLUME_PATH = "/zbs/primarystorage/volume/clone"
    CBD_TO_NBD_PATH = "/zbs/primarystorage/volume/cbdtonbd"
    CLEAN_NBD_PATH = "/zbs/primarystorage/volume/cleannbd"
    CREATE_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/create"
    DELETE_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/delete"
    ROLLBACK_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/rollback"
    EXPAND_VOLUME_PATH = "/zbs/primarystorage/volume/expand"

    http_server = http.HttpServer(port=7763)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        super(ZbsAgent, self).__init__()
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.GET_FACTS_PATH, self.get_facts)
        self.http_server.register_async_uri(self.GET_CAPACITY_PATH, self.get_capacity)
        self.http_server.register_async_uri(self.COPY_PATH, self.copy)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create_volume)
        self.http_server.register_async_uri(self.DELETE_VOLUME_PATH, self.delete_volume)
        self.http_server.register_async_uri(self.QUERY_VOLUME_PATH, self.query_volume)
        self.http_server.register_async_uri(self.CLONE_VOLUME_PATH, self.clone_volume)
        self.http_server.register_async_uri(self.EXPAND_VOLUME_PATH, self.expand_volume)
        self.http_server.register_async_uri(self.CBD_TO_NBD_PATH, self.cbd_to_nbd)
        self.http_server.register_async_uri(self.CLEAN_NBD_PATH, self.clean_nbd)
        self.http_server.register_async_uri(self.CREATE_SNAPSHOT_PATH, self.create_snapshot)
        self.http_server.register_async_uri(self.DELETE_SNAPSHOT_PATH, self.delete_snapshot)
        self.http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)

    @replyerror
    def expand_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ExpandVolumeRsp()

        o = zbsutils.expand_volume(cmd.logicalPoolName, cmd.lunName, cmd.size)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to expand lun[%s], error[%s]' % (cmd.lunName, ret.error.message))

        o = zbsutils.query_volume_info(cmd.logicalPoolName, cmd.lunName)
        rsp.size = jsonobject.loads(o).result.info.fileInfo.length

        return jsonobject.dumps(rsp)

    @replyerror
    def copy(self, req):
        class CopyDaemon(plugin.TaskDaemon):
            def __init__(self, task_spec):
                super(CopyDaemon, self).__init__(task_spec, "copy")
                self.task_spec = task_spec

            def _cancel(self):
                traceable_shell.cancel_job_by_api(self.api_id)
                zbsutils.delete_volume(self.task_spec.logicalPoolName, self.task_spec.dstLunName)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CopyRsp()

        snapshot_path = cmd.logicalPoolName + "/" + cmd.lunName + "@" + cmd.snapshotName
        dst_lun_path = cmd.logicalPoolName + "/" + cmd.dstLunName

        with CopyDaemon(task_spec=cmd):
            o = zbsutils.query_snapshot_info(cmd.logicalPoolName, cmd.lunName)
            ret = jsonobject.loads(o)
            if not ret.result.hasattr('fileInfo'):
                raise Exception('failed to found snapshot for lun[%s]' % cmd.lunName)

            o = zbsutils.copy(snapshot_path, dst_lun_path, True)
            ret = jsonobject.loads(o)
            if ret.error.code != 0:
                raise Exception('failed to copy snapshot[%s] to lun[%s], error[%s]' % (snapshot_path, dst_lun_path, ret.error.message))
            elif ret.result.hasattr('fileStatus') and ret.result.fileStatus != 0:
                zbsutils.delete_volume(cmd.logicalPoolName, cmd.dstLunName)
                raise Exception('target lun[%s] exception[fileStatus:%d], deleted' % (dst_lun_path, ret.result.fileStatus))
            rsp.size = ret.result.fileLength
            rsp.installPath = FORMAT_CBD_LUN_PATH.format(zbsutils.get_physical_pool_name(cmd.logicalPoolName), cmd.logicalPoolName, cmd.dstLunName)

            return jsonobject.dumps(rsp)

    @replyerror
    def rollback_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RollbackSnapshotRsp()

        o = zbsutils.rollback_snapshot(cmd.logicalPoolName, cmd.lunName, cmd.snapshotName)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to rollback snapshot[%s@%s], error[%s]' % (cmd.lunName, cmd.snapshotName, ret.error.message))

        o = zbsutils.query_volume_info(cmd.logicalPoolName, cmd.lunName)
        rsp.size = jsonobject.loads(o).result.info.fileInfo.length
        rsp.installPath = FORMAT_CBD_LUN_PATH.format(zbsutils.get_physical_pool_name(cmd.logicalPoolName), cmd.logicalPoolName, cmd.lunName)

        return jsonobject.dumps(rsp)

    @replyerror
    def delete_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        o = zbsutils.query_snapshot_info(cmd.logicalPoolName, cmd.lunName)
        r = jsonobject.loads(o)
        if r.error.code != 0:
            raise Exception('cannot found snapshot for lun[%s/%s], error[%s]' % (cmd.logicalPoolName, cmd.lunName, r.error.message))
        if not r.result.hasattr('fileInfo'):
            return jsonobject.dumps(rsp)

        file_infos = []
        for file_info in r.result.fileInfo:
            if file_info.fileName == cmd.snapshotName:
                file_infos.append(file_info)
                break
        if not file_infos:
            return jsonobject.dumps(rsp)

        zbsutils.delete_snapshot(cmd.logicalPoolName, cmd.lunName, file_infos)

        return jsonobject.dumps(rsp)

    @replyerror
    def query_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = QueryVolumeRsp()

        o = zbsutils.query_volume_info(cmd.logicalPoolName, cmd.lunName)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('cannot found lun[%s/%s] info, error[%s]' % (cmd.logicalPoolName, cmd.lunName, ret.error.message))
        rsp.size = ret.result.info.fileInfo.length
        rsp.actualSize = ret.result.info.fileInfo.usedSize

        return jsonobject.dumps(rsp)

    @replyerror
    def clone_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CloneVolumeRsp()

        isProtected = False
        o = zbsutils.query_snapshot_info(cmd.logicalPoolName, cmd.lunName)
        ret = jsonobject.loads(o)
        if not ret.result.hasattr('fileInfo'):
            raise Exception('failed to found snapshot for lun[%s]' % cmd.lunName)
        for info in ret.result.fileInfo:
            if cmd.snapshotName in info.fileName:
                isProtected = info.isProtected
                break

        if not isProtected:
            zbsutils.protect_snapshot(cmd.logicalPoolName, cmd.lunName, cmd.snapshotName)

        o = zbsutils.clone_volume(cmd.logicalPoolName, cmd.lunName, cmd.snapshotName, cmd.dstLunName)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to clone lun[%s] to lun[%s], error[%s]' % (cmd.srcPath, cmd.destPath, ret.error.message))

        rsp.installPath = FORMAT_CBD_LUN_PATH.format(zbsutils.get_physical_pool_name(cmd.logicalPoolName), cmd.logicalPoolName, cmd.dstLunName)
        rsp.size = ret.result.fileInfo.length

        return jsonobject.dumps(rsp)

    @replyerror
    def create_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateSnapshotRsp()

        found = False
        install_path = FORMAT_CBD_SNAPSHOT_PATH.format(zbsutils.get_physical_pool_name(cmd.logicalPoolName), cmd.logicalPoolName, cmd.lunName, cmd.snapshotName)

        o = zbsutils.query_snapshot_info(cmd.logicalPoolName, cmd.lunName)
        ret = jsonobject.loads(o)
        if ret.result.hasattr('fileInfo'):
            for info in ret.result.fileInfo:
                if cmd.snapshotName in info.fileName:
                    found = True
                    rsp.size = info.length
                    rsp.installPath = install_path
                    break

        if cmd.skipOnExisting and found:
            return jsonobject.dumps(rsp)

        o = zbsutils.create_snapshot(cmd.logicalPoolName, cmd.lunName, cmd.snapshotName)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to create snapshot[%s@%s], error[%s]' % (cmd.lunName, cmd.snapshotName, ret.error.message))

        rsp.size = ret.result.snapShotFileInfo.length
        rsp.installPath = install_path

        return jsonobject.dumps(rsp)

    @replyerror
    def clean_nbd(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        fullname = "qemu-nbd -D cbd2nbd.%d -f raw -p %d" % (cmd.port, cmd.port)
        linux.kill_process_by_fullname(fullname, 9)

        return jsonobject.dumps(rsp)

    @replyerror
    def cbd_to_nbd(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CbdToNbdRsp()

        logical_pool_name = get_logical_pool_name(cmd.installPath)
        lun_name = get_lun_name(cmd.installPath)

        if '@' in cmd.installPath:
            snapshot_name = get_snapshot_name(cmd.installPath)

            seq_num = ""
            o = zbsutils.query_snapshot_info(logical_pool_name, lun_name)
            ret = jsonobject.loads(o)
            if not ret.result.hasattr('fileInfo'):
                raise Exception('failed to found snapshot for lun[%s]' % lun_name)
            for info in ret.result.fileInfo:
                if snapshot_name in info.fileName:
                    seq_num = info.seqNum
                    break

            install_path = FORMAT_CBD_SNAPSHOT_PATH.format(zbsutils.get_physical_pool_name(logical_pool_name), logical_pool_name, lun_name, str(seq_num))
        else:
            install_path = cmd.installPath

        port = linux.get_free_port_in_range(10600, 10800)
        desc = "cbd2nbd.%d" % port
        zbsutils.cbd_to_nbd(desc, port, install_path)
        rsp.ip = cmd.mdsAddr
        rsp.port = port
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        zbsutils.delete_volume(cmd.logicalPoolName, cmd.lunName)

        return jsonobject.dumps(rsp)

    @replyerror
    def create_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVolumeRsp()

        install_path = FORMAT_CBD_LUN_PATH.format(zbsutils.get_physical_pool_name(cmd.logicalPoolName), cmd.logicalPoolName, cmd.lunName)

        o = zbsutils.query_volume_info(cmd.logicalPoolName, cmd.lunName)
        ret = jsonobject.loads(o)
        if ret.error.code == 0 and cmd.skipIfExisting:
            rsp.size = ret.result.info.fileInfo.length
            rsp.actualSize = ret.result.info.fileInfo.usedSize
            rsp.installPath = install_path
            return jsonobject.dumps(rsp)

        o = zbsutils.create_volume(cmd.logicalPoolName, cmd.lunName, cmd.size)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to create lun[%s], error[%s]' % (cmd.lunName, ret.error.message))

        o = zbsutils.query_volume_info(cmd.logicalPoolName, cmd.lunName)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('cannot found lun[%s/%s] info, error[%s]' % (cmd.logicalPoolName, cmd.lunName, ret.error.message))
        rsp.size = ret.result.info.fileInfo.length
        rsp.installPath = install_path

        return jsonobject.dumps(rsp)

    @replyerror
    def get_capacity(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetCapacityRsp()

        o = zbsutils.query_logical_pool_info()
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('cannot found logical pool info, error[%s]' % ret.error.message)

        found = False
        for lp in jsonobject.loads(o).result[0].logicalPoolInfos:
            if cmd.logicalPoolName in lp.logicalPoolName:
                rsp.capacity = lp.capacity
                rsp.usedSize = lp.usedSize
                found = True
                break

        if not found:
            raise Exception('cannot found logical pool[%s], you must create it manually' % cmd.logicalPoolName)

        return jsonobject.dumps(rsp)

    @replyerror
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetFactsRsp()

        if not os.path.exists(ZBS_CLIENT_CONF):
            raise Exception('missing directory %s, please check the environment libcbd installation' % ZBS_CLIENT_CONF)

        shell.call('sed -i "s/^mds\.listen\.addr=.*/mds.listen.addr=%s/" %s' % (cmd.mdsListenAddr, ZBS_CLIENT_CONF))

        o = zbsutils.query_mds_status_info()
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('cannot found mds info, error[%s]' % ret.error.message)

        found = False
        for mds in ret.result:
            if cmd.mdsAddr in mds.addr:
                rsp.version = mds.version
                found = True
                break

        if not found:
            rsp.success = False
            rsp.error = 'mds addr was not found on the server[uuid:%s], not %s anymore.' % (cmd.psUuid, cmd.mdsAddr)
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''


class ZbsDaemon(daemon.Daemon):
    def __init__(self, pidfile, py_process_name):
        super(ZbsDaemon, self).__init__(pidfile, py_process_name)

    def run(self):
        self.agent = ZbsAgent()
        self.agent.http_server.start()

__author__ = 'Xingwei Yu'

import traceback
import pprint

import zbsutils
import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils import plugin
from zstacklib.utils import daemon
from zstacklib.utils.report import *
from zstacklib.utils.bash import *


log.configure_log('/var/log/zstack/zbs-primarystorage.log')
logger = log.get_logger(__name__)


PROTOCOL_CBD_PREFIX = "cbd:"
PROTOCOL_NBD_PREFIX = "nbd://"


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


class CopySnapshotRsp(AgentResponse):
    def __init__(self):
        super(CopySnapshotRsp, self).__init__()
        self.installPath = None
        self.size = 0


class RollbackSnapshotRsp(AgentResponse):
    def __init__(self):
        super(RollbackSnapshotRsp, self).__init__()
        self.installPath = None
        self.size = 0


class QueryVolumeRsp(AgentResponse):
    def __init__(self):
        super(QueryVolumeRsp, self).__init__()
        self.size = 0


class CloneVolumeRsp(AgentResponse):
    def __init__(self):
        super(CloneVolumeRsp, self).__init__()
        self.installPath = None
        self.size = 0


class CreateSnapshotRsp(AgentResponse):
    def __init__(self):
        super(CreateSnapshotRsp, self).__init__()
        self.size = 0


class CreateVolumeRsp(AgentResponse):
    def __init__(self):
        super(CreateVolumeRsp, self).__init__()
        self.size = 0


class GetCapacityRsp(AgentResponse):
    def __init__(self):
        super(GetCapacityRsp, self).__init__()
        self.capacity = None
        self.storedSize = None


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


class ZbsAgent(plugin.TaskManager):
    ECHO_PATH = "/zbs/primarystorage/echo"
    GET_FACTS_PATH = "/zbs/primarystorage/facts"
    GET_CAPACITY_PATH = "/zbs/primarystorage/capacity"
    CREATE_VOLUME_PATH = "/zbs/primarystorage/volume/create"
    DELETE_VOLUME_PATH = "/zbs/primarystorage/volume/delete"
    QUERY_VOLUME_PATH = "/zbs/primarystorage/volume/query"
    CLONE_VOLUME_PATH = "/zbs/primarystorage/volume/clone"
    CBD_TO_NBD_PATH = "/zbs/primarystorage/volume/cbdtonbd"
    CREATE_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/create"
    DELETE_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/delete"
    ROLLBACK_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/rollback"
    COPY_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/copy"
    EXPAND_VOLUME_PATH = "/zbs/primarystorage/volume/expand"

    http_server = http.HttpServer(port=7763)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        super(ZbsAgent, self).__init__()
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.GET_FACTS_PATH, self.get_facts)
        self.http_server.register_async_uri(self.GET_CAPACITY_PATH, self.get_capacity)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create_volume)
        self.http_server.register_async_uri(self.DELETE_VOLUME_PATH, self.delete_volume)
        self.http_server.register_async_uri(self.QUERY_VOLUME_PATH, self.query_volume)
        self.http_server.register_async_uri(self.CLONE_VOLUME_PATH, self.clone_volume)
        self.http_server.register_async_uri(self.EXPAND_VOLUME_PATH, self.expand_volume)
        self.http_server.register_async_uri(self.CBD_TO_NBD_PATH, self.cbd_to_nbd)
        self.http_server.register_async_uri(self.CREATE_SNAPSHOT_PATH, self.create_snapshot)
        self.http_server.register_async_uri(self.DELETE_SNAPSHOT_PATH, self.delete_snapshot)
        self.http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)
        self.http_server.register_async_uri(self.COPY_SNAPSHOT_PATH, self.copy_snapshot)

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
    def copy_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CopySnapshotRsp()

        found = False
        seq_num = ""
        o = zbsutils.query_snapshot_info(cmd.logicalPoolName, cmd.lunName)
        ret = jsonobject.loads(o)
        if ret.result.fileInfo is not None:
            for info in ret.result.fileInfo:
                if cmd.snapshotName in info.fileName:
                    found = True
                    seq_num = info.seqNum
                    break
        if not found or seq_num is None:
            raise Exception('cannot found snapshot info on lun[%s/%s]' % (cmd.logicalPoolName, cmd.lunName))

        path_prefix = PROTOCOL_CBD_PREFIX + cmd.physicalPoolName + "/" + cmd.logicalPoolName
        src_snapshot_path = path_prefix + "/" + cmd.lunName + "@" + str(seq_num)
        dst_lun_path = path_prefix + "/" + cmd.dstLunName

        o = zbsutils.create_volume(cmd.logicalPoolName, cmd.dstLunName, cmd.dstLunSize)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to create lun[%s], error[%s]' % (dst_lun_path, ret.error.message))

        if zbsutils.copy_snapshot(src_snapshot_path, dst_lun_path) != 0:
            raise Exception('failed to copy snapshot[%s] to lun[%s]' % (src_snapshot_path, dst_lun_path))
        rsp.size = cmd.dstLunSize
        rsp.installPath = dst_lun_path

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
        rsp.installPath = PROTOCOL_CBD_PREFIX + zbsutils.get_physical_pool_name(cmd.logicalPoolName) + "/" + cmd.logicalPoolName + "/" + cmd.lunName

        return jsonobject.dumps(rsp)

    @replyerror
    def delete_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        o = zbsutils.delete_snapshot(cmd.logicalPoolName, cmd.lunName, cmd.snapshotName)
        ret = jsonobject.loads(o)
        if ret.error.code == 0:
            return jsonobject.dumps(rsp)
        else:
            raise Exception('failed to delete snapshot[%s@%s], error[%s]' % (cmd.lunName, cmd.snapshotName, ret.error.message))

    @replyerror
    def query_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = QueryVolumeRsp()

        if zbsutils.query_volume(cmd.logicalPoolName, cmd.lunName) == 0:
            o = zbsutils.query_volume_info(cmd.logicalPoolName, cmd.lunName)
            rsp.size = jsonobject.loads(o).result.info.fileInfo.length
        else:
            raise Exception('failed to query lun[%s] info' % cmd.lunName)

        return jsonobject.dumps(rsp)

    @replyerror
    def clone_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CloneVolumeRsp()

        isProtected = False
        o = zbsutils.query_snapshot_info(cmd.logicalPoolName, cmd.lunName)
        ret = jsonobject.loads(o)
        if ret.result.fileInfo:
            for info in ret.result.fileInfo:
                if cmd.snapshotName in info.fileName:
                    isProtected = info.isProtected
                    break
        else:
            raise Exception('failed to found snapshot for lun[%s]' % cmd.lunName)

        if not isProtected:
            zbsutils.protect_snapshot(cmd.logicalPoolName, cmd.lunName, cmd.snapshotName)

        o = zbsutils.clone_volume(cmd.logicalPoolName, cmd.lunName, cmd.snapshotName, cmd.dstLunName)
        ret = jsonobject.loads(o)
        if ret.error.code == 0:
            rsp.installPath = PROTOCOL_CBD_PREFIX + zbsutils.get_physical_pool_name(cmd.logicalPoolName) + "/" + cmd.logicalPoolName + "/" + cmd.dstLunName
            rsp.size = ret.result.fileInfo.length
        else:
            raise Exception('failed to clone lun[%s] to lun[%s], error[%s]' % (cmd.srcPath, cmd.destPath, ret.error.message))

        return jsonobject.dumps(rsp)

    @replyerror
    def create_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateSnapshotRsp()

        found = False
        o = zbsutils.query_snapshot_info(cmd.logicalPoolName, cmd.lunName)
        ret = jsonobject.loads(o)
        if ret.result.fileInfo is not None:
            for info in ret.result.fileInfo:
                if cmd.snapshotName in info.fileName:
                    found = True
                    break

        if cmd.skipOnExisting and found:
            return jsonobject.dumps(rsp)

        o = zbsutils.create_snapshot(cmd.logicalPoolName, cmd.lunName, cmd.snapshotName)
        ret = jsonobject.loads(o)
        if ret.error is None:
            rsp.size = ret.result.snapShotFileInfo.length
            rsp.installPath = PROTOCOL_CBD_PREFIX + zbsutils.get_physical_pool_name(cmd.logicalPoolName) + "/" + cmd.logicalPoolName + "/" + cmd.lunName + "@" + cmd.snapshotName
        else:
            raise Exception('failed to create snapshot[%s@%s] on zbs, error[%s]' % (cmd.lunName, cmd.snapshotName, ret.error.message))

        return jsonobject.dumps(rsp)

    @replyerror
    def cbd_to_nbd(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CbdToNbdRsp()

        zbsutils.cbd_to_nbd(10086, cmd.installPath)

        rsp.ip = cmd.mdsAddr
        rsp.port = 10086

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

        if cmd.skipIfExisting and zbsutils.query_volume(cmd.logicalPoolName, cmd.lunName) == 0:
            return jsonobject.dumps(rsp)

        o = zbsutils.create_volume(cmd.logicalPoolName, cmd.lunName, cmd.size)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to create lun[%s], error[%s]' % (cmd.lunName, ret.error.message))

        o = zbsutils.query_volume_info(cmd.logicalPoolName, cmd.lunName)
        rsp.size = jsonobject.loads(o).result.info.fileInfo.length
        rsp.installPath = PROTOCOL_CBD_PREFIX + zbsutils.get_physical_pool_name(cmd.logicalPoolName) + "/" + cmd.logicalPoolName + "/" + cmd.lunName

        return jsonobject.dumps(rsp)

    @replyerror
    def get_capacity(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetCapacityRsp()

        o = zbsutils.query_logical_pool_info()

        found = False
        for lp in jsonobject.loads(o).result[0].logicalPoolInfos:
            if cmd.logicalPoolName in lp.logicalPoolName:
                rsp.capacity = lp.capacity
                rsp.storedSize = lp.storedSize
                found = True
                break

        if not found:
            raise Exception('cannot found logical pool[%s], you must create it manually' % cmd.logicalPoolName)

        return jsonobject.dumps(rsp)

    @replyerror
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetFactsRsp()

        o = zbsutils.query_mds_status_info()

        found = False
        for mds in jsonobject.loads(o).result:
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

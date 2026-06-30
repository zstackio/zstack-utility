__author__ = 'Xingwei Yu'

import base64
import pprint
import traceback

import zbsutils
from zstacklib.utils import daemon
from zstacklib.utils import iproute
from zstacklib.utils import plugin
from zstacklib.utils import traceable_shell
from zstacklib.utils.bash import *
from zstacklib.utils.report import *

logger = log.get_logger(__name__)


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

    def set_error(self, error):
        self.success = False
        self.error = error


class SyncMetadataRsp(AgentResponse):
    def __init__(self):
        super(SyncMetadataRsp, self).__init__()
        self.externalAddr = None


class CbdToNbdRsp(AgentResponse):
    def __init__(self):
        super(CbdToNbdRsp, self).__init__()
        self.ip = None
        self.port = 0


class ExpandVolumeRsp(AgentResponse):
    def __init__(self):
        super(ExpandVolumeRsp, self).__init__()
        self.size = 0


class FlattenVolumeRsp(AgentResponse):
    def __init__(self):
        super(FlattenVolumeRsp, self).__init__()
        self.size = 0
        self.actualSize = 0


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


class GetVolumeClientsRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeClientsRsp, self).__init__()
        self.clients = []


class QueryVolumeRsp(AgentResponse):
    def __init__(self):
        super(QueryVolumeRsp, self).__init__()
        self.size = 0
        self.actualSize = 0
        self.parentUri = None


class BatchQueryVolumeRsp(AgentResponse):
    def __init__(self):
        super(BatchQueryVolumeRsp, self).__init__()
        self.volumes = {}


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


class QuerySnapshotRsp(AgentResponse):
    def __init__(self):
        super(QuerySnapshotRsp, self).__init__()
        self.hasSnapshot = False
        self.installPath = None


class CreateVolumeRsp(AgentResponse):
    def __init__(self):
        super(CreateVolumeRsp, self).__init__()
        self.size = 0
        self.actualSize = 0


class GetCapacityRsp(AgentResponse):
    def __init__(self):
        super(GetCapacityRsp, self).__init__()
        self.logicalPoolInfos = []


class GetFactsRsp(AgentResponse):
    def __init__(self):
        super(GetFactsRsp, self).__init__()
        self.uuid = None
        self.version = None


class LogicalPoolInfo:
    class RedundanceAndPlacementPolicy:
        def __init__(self, copyset_number=None, replica_number=None, zone_number=None):
            self.copysetNum = copyset_number
            self.replicaNum = replica_number
            self.zoneNum = zone_number

    def __init__(self, logical_pool_info):
        self.logicalPoolID = logical_pool_info.logicalPoolID
        self.logicalPoolName = logical_pool_info.logicalPoolName
        self.physicalPoolID = logical_pool_info.physicalPoolID
        self.physicalPoolName = logical_pool_info.physicalPoolName
        self.type = logical_pool_info.type
        self.createTime = logical_pool_info.createTime
        self.redundanceAndPlaceMentPolicy = self.decode_redundance_and_placement_policy(
            logical_pool_info.redundanceAndPlaceMentPolicy
        )
        self.userPolicy = logical_pool_info.userPolicy
        self.allocateStatus = logical_pool_info.allocateStatus
        self.capacity = logical_pool_info.capacity
        self.usedSize = logical_pool_info.usedSize
        self.allocatedSize = logical_pool_info.allocatedSize
        self.rawUsedSize = logical_pool_info.rawUsedSize
        self.rawWalUsedSize = logical_pool_info.rawWalUsedSize
        self.quota = logical_pool_info.quota

    def decode_redundance_and_placement_policy(self, redundance_and_placement_policy):
        if not redundance_and_placement_policy:
            return None

        try:
            d = jsonobject.loads(base64.b64decode(redundance_and_placement_policy))
            return self.RedundanceAndPlacementPolicy(
                copyset_number=d.copysetNum,
                replica_number=d.replicaNum,
                zone_number=d.zoneNum
            )
        except Exception as e:
            logger.error('failed to decode redundance and placement policy[%s], error[%s]' % (
                redundance_and_placement_policy, e.message
            ))


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
    PING_PATH = "/zbs/primarystorage/ping"
    GET_FACTS_PATH = "/zbs/primarystorage/facts"
    SYNC_METADATA_PATH = "/zbs/primarystorage/metadata/sync"
    DEPLOY_CLIENT_PATH = "/zbs/primarystorage/client/deploy"
    GET_CAPACITY_PATH = "/zbs/primarystorage/capacity"
    COPY_PATH = "/zbs/primarystorage/copy"
    CREATE_VOLUME_PATH = "/zbs/primarystorage/volume/create"
    DELETE_VOLUME_PATH = "/zbs/primarystorage/volume/delete"
    QUERY_VOLUME_PATH = "/zbs/primarystorage/volume/query"
    BATCH_QUERY_VOLUME_PATH = "/zbs/primarystorage/volume/query/batch"
    CLONE_VOLUME_PATH = "/zbs/primarystorage/volume/clone"
    CBD_TO_NBD_PATH = "/zbs/primarystorage/volume/cbdtonbd"
    CLEAN_NBD_PATH = "/zbs/primarystorage/volume/cleannbd"
    CREATE_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/create"
    DELETE_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/delete"
    QUERY_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/query"
    ROLLBACK_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/rollback"
    EXPAND_VOLUME_PATH = "/zbs/primarystorage/volume/expand"
    FLATTEN_VOLUME_PATH = "/zbs/primarystorage/volume/flatten"
    GET_VOLUME_CLIENTS_PATH = "/zbs/primarystorage/volume/clients"

    http_server = http.HttpServer(port=7763)
    http_server.logfile_path = log.get_logfile_path()

    SUPPORT_GET_VOLUME_CLIENTS = False

    def __init__(self):
        super(ZbsAgent, self).__init__()
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_FACTS_PATH, self.get_facts)
        self.http_server.register_async_uri(self.SYNC_METADATA_PATH, self.sync_metadata)
        self.http_server.register_async_uri(self.DEPLOY_CLIENT_PATH, self.deploy_client)
        self.http_server.register_async_uri(self.GET_CAPACITY_PATH, self.get_capacity)
        self.http_server.register_async_uri(self.COPY_PATH, self.copy)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create_volume)
        self.http_server.register_async_uri(self.DELETE_VOLUME_PATH, self.delete_volume)
        self.http_server.register_async_uri(self.QUERY_VOLUME_PATH, self.query_volume)
        self.http_server.register_async_uri(self.BATCH_QUERY_VOLUME_PATH, self.batch_query_volume)
        self.http_server.register_async_uri(self.CLONE_VOLUME_PATH, self.clone_volume)
        self.http_server.register_async_uri(self.EXPAND_VOLUME_PATH, self.expand_volume)
        self.http_server.register_async_uri(self.FLATTEN_VOLUME_PATH, self.flatten_volume)
        self.http_server.register_async_uri(self.CBD_TO_NBD_PATH, self.cbd_to_nbd)
        self.http_server.register_async_uri(self.CLEAN_NBD_PATH, self.clean_nbd)
        self.http_server.register_async_uri(self.CREATE_SNAPSHOT_PATH, self.create_snapshot)
        self.http_server.register_async_uri(self.DELETE_SNAPSHOT_PATH, self.delete_snapshot)
        self.http_server.register_async_uri(self.QUERY_SNAPSHOT_PATH, self.query_snapshot)
        self.http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)
        self.http_server.register_sync_uri(self.GET_VOLUME_CLIENTS_PATH, self.get_volume_clients)

    @replyerror
    def get_facts(self, req):
        rsp = GetFactsRsp()

        try:
            rsp.version = zbsutils.get_version()
        except Exception as e:
            raise Exception('failed to get version, error[%s]' % str(e))

        rsp.uuid = zbsutils.get_cluster_uuid(rsp.version)

        return jsonobject.dumps(rsp)

    @replyerror
    def sync_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SyncMetadataRsp()

        o = zbsutils.query_mds_status_info()
        r = jsonobject.loads(o)
        if not r.result:
            raise Exception('failed to query mds info, error[%s]' % r.error.message)

        ipv4_addrs = [addr.address for addr in iproute.query_addresses(ip_version=4) if
                      addr.address and not addr.address.startswith("127.")]

        found = False
        for m in r.result:
            if m.externalAddr and any(m.externalAddr.split(":")[0] == ip for ip in ipv4_addrs):
                rsp.externalAddr = m.externalAddr
                found = True
                break

        if not found:
            rsp.success = False
            rsp.error = 'cannot found external address of mds[%s]' % cmd.addr
            return jsonobject.dumps(rsp)

        self.SUPPORT_GET_VOLUME_CLIENTS = zbsutils.is_support_get_volume_clients()

        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        current_cluster_uuid = zbsutils.get_cluster_uuid(cmd.clusterInfo.version)
        if current_cluster_uuid != cmd.clusterInfo.uuid:
            raise Exception('cluster uuid does not match, current cluster uuid[%s], old cluster uuid[%s]' % (
            current_cluster_uuid, cmd.clusterInfo.uuid))

        o = zbsutils.query_mds_status_info()
        r = jsonobject.loads(o)
        if not r.result:
            raise Exception('failed to query mds info, error[%s]' % r.error.message)

        found = False
        for m in r.result:
            if m.status == "leader":
                found = True
                break

        if not found:
            rsp.success = False
            rsp.error = 'cannot found mds leader'
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @replyerror
    def expand_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ExpandVolumeRsp()

        _, logical_pool, volume, _ = zbsutils.parse_cbd_path(cmd.path)

        o = zbsutils.expand_volume(logical_pool, volume, cmd.size, cmd.unit if cmd.unit else '')
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to expand volume[%s], error[%s]' % (volume, ret.error.message))

        o = zbsutils.query_volume_info(logical_pool, volume)
        rsp.size = jsonobject.loads(o).result.info.fileInfo.length

        return jsonobject.dumps(rsp)

    @replyerror
    def flatten_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = FlattenVolumeRsp()

        _, logical_pool, volume, _ = zbsutils.parse_cbd_path(cmd.path)

        o = zbsutils.query_volume_info(logical_pool, volume)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('cannot found volume[%s/%s] info, error[%s]' % (logical_pool, volume, ret.error.message))
        if not zbsutils.is_clonal_type(ret.result.info.fileInfo.fileType):
            logger.debug("target volume[%s/%s] is a non-clonal, no flatten is required, skip" % (logical_pool, volume))
            rsp.size = ret.result.info.fileInfo.length
            rsp.actualSize = ret.result.info.fileInfo.usedSize
            return jsonobject.dumps(rsp)

        o = zbsutils.flatten_volume(logical_pool, volume)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to flatten volume[%s/%s], error[%s]' % (logical_pool, volume, ret.error.message))

        o = zbsutils.query_volume_info(logical_pool, volume)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('cannot found volume[%s/%s] info, error[%s]' % (logical_pool, volume, ret.error.message))
        rsp.size = ret.result.info.fileInfo.length
        rsp.actualSize = ret.result.info.fileInfo.usedSize

        return jsonobject.dumps(rsp)

    @replyerror
    def copy(self, req):
        class CopyDaemon(plugin.TaskDaemon):
            def __init__(self, task_spec):
                super(CopyDaemon, self).__init__(task_spec, "copy")
                self.task_spec = task_spec

            def _cancel(self):
                traceable_shell.cancel_job_by_api(self.api_id)
                _, logical_pool, _, _ = zbsutils.parse_cbd_path(self.task_spec.path)
                zbsutils.delete_volume_and_snapshots(logical_pool, self.task_spec.dstVolume)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CopyRsp()

        physical_pool, logical_pool, volume, snapshot = zbsutils.parse_cbd_path(cmd.path)

        snapshot_path = logical_pool + "/" + volume + "@" + snapshot
        dst_volume_path = logical_pool + "/" + cmd.dstVolume

        with CopyDaemon(task_spec=cmd):
            o = zbsutils.query_snapshot_info(logical_pool, volume)
            ret = jsonobject.loads(o)
            if ret.error.code != 0:
                raise Exception('failed to query snapshot info for volume[%s], error[%s]' % (volume, ret.error.message))

            o = zbsutils.copy(snapshot_path, dst_volume_path, True)
            ret = jsonobject.loads(o)
            if ret.error.code != 0:
                raise Exception('failed to copy snapshot[%s] to volume[%s], error[%s]' % (
                snapshot_path, dst_volume_path, ret.error.message))
            elif ret.result.hasattr('fileStatus') and ret.result.fileStatus != 0:
                zbsutils.delete_volume_and_snapshots(logical_pool, cmd.dstVolume)
                raise Exception(
                    'target volume[%s] exception[fileStatus:%d], deleted' % (dst_volume_path, ret.result.fileStatus))
            rsp.size = ret.result.fileLength
            rsp.installPath = zbsutils.CBD_VOLUME_PATH.format(physical_pool, logical_pool, cmd.dstVolume)

            return jsonobject.dumps(rsp)

    @replyerror
    def rollback_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RollbackSnapshotRsp()

        physical_pool, logical_pool, volume, snapshot = zbsutils.parse_cbd_path(cmd.path)

        o = zbsutils.rollback_snapshot(logical_pool, volume, snapshot)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to rollback snapshot[%s@%s], error[%s]' % (volume, snapshot, ret.error.message))

        o = zbsutils.query_volume_info(logical_pool, volume)
        rsp.size = jsonobject.loads(o).result.info.fileInfo.length
        rsp.installPath = zbsutils.CBD_VOLUME_PATH.format(physical_pool, logical_pool, volume)

        return jsonobject.dumps(rsp)

    @replyerror
    def get_volume_clients(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeClientsRsp()
        if not self.SUPPORT_GET_VOLUME_CLIENTS:
            return jsonobject.dumps(rsp)

        _, logical_pool, volume, _ = zbsutils.parse_cbd_path(cmd.path)
        if "?r=" in volume:
            logger.info("volume[%s] is a remote volume, skip get clients" % volume)
            return jsonobject.dumps(rsp)

        rsp.clients = zbsutils.get_volume_clients(logical_pool, volume)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        physical_pool, logical_pool, volume, snapshot = zbsutils.parse_cbd_path(cmd.path)

        o = zbsutils.query_snapshot_info(logical_pool, volume)
        r = jsonobject.loads(o)
        if r.error.code != 0:
            raise Exception(
                'cannot found snapshot for volume[%s/%s], error[%s]' % (logical_pool, volume, r.error.message))
        if not r.result.hasattr('fileInfo'):
            return jsonobject.dumps(rsp)

        file_infos = []
        for file_info in r.result.fileInfo:
            if file_info.fileName == snapshot:
                file_infos.append(file_info)
                break
        if not file_infos:
            return jsonobject.dumps(rsp)

        zbsutils.delete_snapshots(logical_pool, volume, file_infos)

        return jsonobject.dumps(rsp)

    @replyerror
    def query_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = QuerySnapshotRsp()

        physical_pool, logical_pool, volume, snapshot = zbsutils.parse_cbd_path(cmd.path)

        o = zbsutils.query_snapshot_info(logical_pool, volume)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception(
                'cannot found snapshot for volume[%s/%s], error[%s]' % (logical_pool, volume, ret.error.message))

        file_infos = ret.result.fileInfo if ret.result and ret.result.hasattr('fileInfo') else []
        rsp.hasSnapshot = bool(file_infos)
        if snapshot is None:
            rsp.installPath = cmd.path
            return jsonobject.dumps(rsp)

        for info in file_infos:
            if info.fileName == snapshot or (info.hasattr('seqNum') and str(info.seqNum) == snapshot):
                rsp.installPath = zbsutils.CBD_SNAPSHOT_PATH.format(
                    physical_pool, logical_pool, volume, str(info.seqNum))
                return jsonobject.dumps(rsp)

        raise Exception('cannot found snapshot[%s] for volume[%s/%s]' % (snapshot, logical_pool, volume))

    @replyerror
    def query_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = QueryVolumeRsp()

        physical_pool, logical_pool, volume, _ = zbsutils.parse_cbd_path(cmd.path)

        o = zbsutils.query_volume_info(logical_pool, volume)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('cannot found volume[%s] info, error[%s]' % (cmd.path, ret.error.message))
        rsp.size = ret.result.info.fileInfo.length
        rsp.actualSize = ret.result.info.fileInfo.usedSize
        if zbsutils.is_clonal_type(ret.result.info.fileInfo.fileType) and ret.result.info.fileInfo.hasattr(
                'cloneSourceSnap'):
            rsp.parentUri = "{}:{}/{}".format(
                zbsutils.CBD_PREFIX,
                physical_pool,
                ret.result.info.fileInfo.cloneSourceSnap
            )

        return jsonobject.dumps(rsp)

    @replyerror
    def batch_query_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = BatchQueryVolumeRsp()

        logical_pool_to_install_paths = {}
        install_path_to_volume_name = {}

        for install_path in cmd.installPaths:
            logical_pool_name = get_logical_pool_name(install_path)
            volume_name = get_lun_name(install_path)
            if logical_pool_name not in logical_pool_to_install_paths:
                logical_pool_to_install_paths[logical_pool_name] = []
            logical_pool_to_install_paths[logical_pool_name].append(install_path)
            install_path_to_volume_name[install_path] = volume_name

        for logical_pool_name, install_paths in logical_pool_to_install_paths.items():
            o = zbsutils.query_volumes_in_logical_pool(logical_pool_name)
            r = jsonobject.loads(o)
            if r.error.code != 0:
                raise Exception('cannot found lun infos in logical pool[%s], error[%s]' % (logical_pool_name, r.error.message))
            for install_path in install_paths:
                for info in r.result.fileInfo:
                    if info.fileName != install_path_to_volume_name.get(install_path):
                        continue
                    rsp.volumes[install_path] = {'length': info.length, 'usedSize': info.usedSize}
                    break

        return jsonobject.dumps(rsp)

    @replyerror
    def clone_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CloneVolumeRsp()

        physical_pool, logical_pool, volume, snapshot = zbsutils.parse_cbd_path(cmd.path)

        is_protected = False
        o = zbsutils.query_snapshot_info(logical_pool, volume)
        ret = jsonobject.loads(o)
        if not ret.result.hasattr('fileInfo'):
            raise Exception('failed to found snapshot for volume[%s]' % volume)
        for info in ret.result.fileInfo:
            if snapshot in info.fileName:
                is_protected = info.isProtected
                break

        if not is_protected:
            zbsutils.protect_snapshot(logical_pool, volume, snapshot)

        o = zbsutils.clone_volume(logical_pool, volume, snapshot, cmd.dstVolume)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception(
                'failed to clone volume[%s] to volume[%s], error[%s]' % (volume, cmd.dstVolume, ret.error.message))

        rsp.installPath = zbsutils.CBD_VOLUME_PATH.format(physical_pool, logical_pool, cmd.dstVolume)
        rsp.size = ret.result.fileInfo.length

        return jsonobject.dumps(rsp)

    @replyerror
    def create_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateSnapshotRsp()

        physical_pool, logical_pool, volume, _ = zbsutils.parse_cbd_path(cmd.path)

        found = False
        install_path = zbsutils.CBD_SNAPSHOT_PATH.format(physical_pool, logical_pool, volume, cmd.snapshot)

        o = zbsutils.query_snapshot_info(logical_pool, volume)
        ret = jsonobject.loads(o)
        if ret.result.hasattr('fileInfo'):
            for info in ret.result.fileInfo:
                if cmd.snapshot in info.fileName:
                    found = True
                    rsp.size = info.length
                    rsp.installPath = install_path
                    break

        if cmd.skipOnExisting and found:
            return jsonobject.dumps(rsp)

        o = zbsutils.create_snapshot(logical_pool, volume, cmd.snapshot)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to create snapshot[%s@%s], error[%s]' % (volume, cmd.snapshot, ret.error.message))

        rsp.size = ret.result.snapShotFileInfo.length
        rsp.installPath = install_path

        return jsonobject.dumps(rsp)

    @replyerror
    def clean_nbd(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        fullname = "qemu-nbd -D cbd2nbd.%d -f raw -p %d" % (cmd.port, cmd.port)
        linux.kill_process_by_fullname(fullname, 15)

        return jsonobject.dumps(rsp)

    @replyerror
    def cbd_to_nbd(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CbdToNbdRsp()

        physical_pool, logical_pool, volume, snapshot = zbsutils.parse_cbd_path(cmd.path)
        if snapshot:
            seq_num = ""
            o = zbsutils.query_snapshot_info(logical_pool, volume)
            ret = jsonobject.loads(o)
            if not ret.result.hasattr('fileInfo'):
                raise Exception('failed to found snapshot for volume[%s]' % volume)
            for info in ret.result.fileInfo:
                if snapshot in info.fileName:
                    seq_num = info.seqNum
                    break
            install_path = zbsutils.CBD_SNAPSHOT_PATH.format(physical_pool, logical_pool, volume, str(seq_num))
        else:
            install_path = cmd.path

        start_port, end_port = linux.parse_port_range(cmd.portRange)
        port, lock = linux.find_free_port_with_locking(start_port, end_port)
        desc = "cbd2nbd.%d" % port
        zbsutils.cbd_to_nbd(desc, port, install_path)
        if lock:
            lock.release()
        rsp.ip = cmd.addr
        rsp.port = port
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        _, logical_pool, volume, _ = zbsutils.parse_cbd_path(cmd.path)

        zbsutils.delete_volume_and_snapshots(logical_pool, volume)

        return jsonobject.dumps(rsp)

    @replyerror
    def create_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVolumeRsp()

        volume_path = zbsutils.CBD_VOLUME_PATH.format(
            zbsutils.get_physical_pool_name(cmd.logicalPool),
            cmd.logicalPool,
            cmd.volume
        )

        o = zbsutils.query_volume_info(cmd.logicalPool, cmd.volume)
        ret = jsonobject.loads(o)
        if ret.error.code == 0 and cmd.skipIfExisting:
            rsp.size = ret.result.info.fileInfo.length
            rsp.actualSize = ret.result.info.fileInfo.usedSize
            rsp.installPath = volume_path
            return jsonobject.dumps(rsp)

        o = zbsutils.create_volume(cmd.logicalPool, cmd.volume, cmd.size, cmd.unit if cmd.unit else "")
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to create volume[%s], error[%s]' % (cmd.volume, ret.error.message))

        o = zbsutils.query_volume_info(cmd.logicalPool, cmd.volume)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception(
                'cannot found volume[%s/%s] info, error[%s]' % (cmd.logicalPool, cmd.volume, ret.error.message))
        rsp.size = ret.result.info.fileInfo.length
        rsp.installPath = volume_path

        return jsonobject.dumps(rsp)

    @replyerror
    def get_capacity(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetCapacityRsp()

        o = zbsutils.query_logical_pool_info()
        r = jsonobject.loads(o)
        if r.error.code != 0:
            raise Exception('cannot found logical pool info, error[%s]' % r.error.message)

        found = False
        for physical_pool in r.result:
            for logical_pool in physical_pool.logicalPoolInfos:
                rsp.logicalPoolInfos.append(LogicalPoolInfo(logical_pool))
                if cmd.logicalPool in logical_pool.logicalPoolName:
                    found = True

        if not found:
            raise Exception('cannot found logical pool[%s], you must create it manually' % cmd.logicalPool)

        return jsonobject.dumps(rsp)

    @replyerror
    def deploy_client(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        o = zbsutils.deploy_client(cmd.ip, cmd.port, cmd.username, cmd.password)
        r = jsonobject.loads(o)
        if r.error.code != 0:
            rsp.success = False
            rsp.error = 'failed to deploy client, error[%s]' % r.error.message

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

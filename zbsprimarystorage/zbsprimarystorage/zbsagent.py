__author__ = 'Xingwei Yu'

import base64
import os
import pprint
import traceback

from . import zbsutils
import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils import daemon
from zstacklib.utils import iproute
from zstacklib.utils import plugin
from zstacklib.utils import resource_control
from zstacklib.utils import shell
from zstacklib.utils import traceable_shell
from zstacklib.utils.bash import *
from zstacklib.utils.report import *

logger = log.get_logger(__name__)
_physical_server_serial_number = None


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

    def set_error(self, error):
        self.success = False
        self.error = error


class PingResponse(AgentResponse):
    def __init__(self):
        super(PingResponse, self).__init__()
        self.agentVersion = None


class SyncMetadataRsp(AgentResponse):
    def __init__(self):
        super(SyncMetadataRsp, self).__init__()
        self.externalAddr = None
        self.physicalServerSerialNumber = None


class ResourceUsageRsp(AgentResponse):
    def __init__(self):
        super(ResourceUsageRsp, self).__init__()
        self.physicalServerSerialNumber = None
        self.usages = []


def read_physical_server_serial_number():
    global _physical_server_serial_number
    if _physical_server_serial_number is not None:
        return _physical_server_serial_number

    if os.path.isfile('/sys/class/dmi/id/product_serial'):
        with open('/sys/class/dmi/id/product_serial') as serial_file:
            serial_number = serial_file.read().strip()
            if serial_number:
                _physical_server_serial_number = serial_number
                return _physical_server_serial_number

    serial_number = shell.call('dmidecode -s system-serial-number', exception=False).strip()
    if serial_number:
        _physical_server_serial_number = serial_number
    return _physical_server_serial_number


class CbdToNbdRsp(AgentResponse):
    def __init__(self):
        super(CbdToNbdRsp, self).__init__()
        self.ip = None
        self.port = 0


class CreateVhostBdevRsp(AgentResponse):
    def __init__(self):
        super(CreateVhostBdevRsp, self).__init__()
        self.socketPath = None


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
            d = jsonobject.loads(base64.b64decode(redundance_and_placement_policy).decode())
            return self.RedundanceAndPlacementPolicy(
                copyset_number=d.copysetNum,
                replica_number=d.replicaNum,
                zone_number=d.zoneNum
            )
        except Exception as e:
            logger.error('failed to decode redundance and placement policy[%s], error[%s]' % (
                redundance_and_placement_policy, str(e)
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
    GET_RESOURCE_USAGE_PATH = "/zbs/primarystorage/resource/usage"
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
    ROLLBACK_SNAPSHOT_PATH = "/zbs/primarystorage/snapshot/rollback"
    EXPAND_VOLUME_PATH = "/zbs/primarystorage/volume/expand"
    FLATTEN_VOLUME_PATH = "/zbs/primarystorage/volume/flatten"
    GET_VOLUME_CLIENTS_PATH = "/zbs/primarystorage/volume/clients"
    DEPLOY_VHOST_PATH = "/zbs/primarystorage/vhost/deploy"
    DESTROY_VHOST_PATH = "/zbs/primarystorage/vhost/destroy"
    CREATE_VHOST_BDEV_PATH = "/zbs/primarystorage/vhost/bdev/create"
    DELETE_VHOST_BDEV_PATH = "/zbs/primarystorage/vhost/bdev/delete"
    RESOURCE_USAGE_CGROUP_NAMES = frozenset(['zstone.share.slice', 'zstone.cs.slice', 'zstone.vhost.slice'])

    http_server = http.HttpServer(port=7763)
    http_server.logfile_path = log.get_logfile_path()

    SUPPORT_GET_VOLUME_CLIENTS = False

    def __init__(self):
        super(ZbsAgent, self).__init__()
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_FACTS_PATH, self.get_facts)
        self.http_server.register_async_uri(self.SYNC_METADATA_PATH, self.sync_metadata)
        self.http_server.register_async_uri(self.GET_RESOURCE_USAGE_PATH, self.get_resource_usage)
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
        self.http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)
        self.http_server.register_sync_uri(self.GET_VOLUME_CLIENTS_PATH, self.get_volume_clients)
        self.http_server.register_async_uri(self.DEPLOY_VHOST_PATH, self.deploy_vhost)
        self.http_server.register_async_uri(self.DESTROY_VHOST_PATH, self.destroy_vhost)
        self.http_server.register_async_uri(self.CREATE_VHOST_BDEV_PATH, self.create_vhost_bdev)
        self.http_server.register_async_uri(self.DELETE_VHOST_BDEV_PATH, self.delete_vhost_bdev)

        self.agent_version = None

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

        rsp.physicalServerSerialNumber = read_physical_server_serial_number()
        self.SUPPORT_GET_VOLUME_CLIENTS = zbsutils.is_support_get_volume_clients()
        self.agent_version = cmd.agentVersion
        return jsonobject.dumps(rsp)

    @replyerror
    def get_resource_usage(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        names = cmd.cgroupNames
        if (not isinstance(names, list) or not names
                or any(not isinstance(name, str) for name in names)
                or len(names) != len(set(names))
                or any(name not in self.RESOURCE_USAGE_CGROUP_NAMES for name in names)):
            raise resource_control.ResourceControlError(
                'Cgroup names must be a non-empty unique subset of the '
                'configured ZBS cgroups')

        serial_number = read_physical_server_serial_number()
        if not serial_number:
            raise resource_control.ResourceControlError('Physical server serial number is unavailable')

        rsp = ResourceUsageRsp()
        rsp.physicalServerSerialNumber = serial_number
        rsp.usages = resource_control.ResourceControlManager().inspect_systemd_slices(names)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = PingResponse()

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

        rsp.agentVersion = self.agent_version
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
        dst_pool = cmd.dstPool if cmd.dstPool else logical_pool
        dst_physical_pool = physical_pool if logical_pool == dst_pool else zbsutils.get_physical_pool_name(dst_pool)
        dst_volume_path = dst_pool + "/" + cmd.dstVolume

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
                zbsutils.delete_volume_and_snapshots(dst_pool, cmd.dstVolume)
                raise Exception(
                    'target volume[%s] exception[fileStatus:%d], deleted' % (dst_volume_path, ret.result.fileStatus))
            rsp.size = ret.result.fileLength
            rsp.installPath = zbsutils.CBD_VOLUME_PATH.format(dst_physical_pool, dst_pool, cmd.dstVolume)

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

        if not zbsutils.is_volume_exist(logical_pool, volume):
            logger.info("volume[%s/%s] does not exist, skip get clients" % (logical_pool, volume))
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
            _, logical_pool_name, volume_name, _ = zbsutils.parse_cbd_path(install_path)
            if logical_pool_name not in logical_pool_to_install_paths:
                logical_pool_to_install_paths[logical_pool_name] = []
            logical_pool_to_install_paths[logical_pool_name].append(install_path)
            install_path_to_volume_name[install_path] = volume_name

        for logical_pool_name, install_paths in logical_pool_to_install_paths.items():
            o = zbsutils.query_volumes_in_logical_pool(logical_pool_name)
            r = jsonobject.loads(o)
            if r.error.code != 0:
                raise Exception(
                    'cannot found lun infos in logical pool[%s], error[%s]' % (logical_pool_name, r.error.message))
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
                if not cmd.logicalPoolNames or logical_pool.logicalPoolName in cmd.logicalPoolNames:
                    found = True

        if not found:
            raise Exception('cannot found logical pool[%s], you must create it manually' % cmd.logicalPoolNames)

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
    def deploy_vhost(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        hugepage_size = cmd.hugepageSize if cmd.hasattr('hugepageSize') else None
        hugepage_dir = cmd.hugepageDir if cmd.hasattr('hugepageDir') else None
        o = zbsutils.deploy_vhost(cmd.hostIp, cmd.sshPort, cmd.sshUsername, cmd.sshPassword,
                                  hugepage_size=hugepage_size, hugepage_dir=hugepage_dir)
        r = jsonobject.loads(o)
        if not r.success:
            raise Exception('failed to deploy vhost target on host[%s], error[%s]' % (
                cmd.hostIp, r.error.message))
        if not zbsutils.wait_vhost_target_ready(cmd.hostIp, cmd.sshPort, cmd.sshUsername, cmd.sshPassword):
            raise Exception('deployed vhost target on host[%s] but target is not ready' % cmd.hostIp)

        return jsonobject.dumps(rsp)

    @replyerror
    def destroy_vhost(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        o = zbsutils.destroy_vhost(cmd.hostIp, cmd.sshPort, cmd.sshUsername, cmd.sshPassword)
        r = jsonobject.loads(o)
        if not r.success:
            raise Exception('failed to destroy vhost target on host[%s], error[%s]' % (
                cmd.hostIp, r.error.message))

        return jsonobject.dumps(rsp)

    @replyerror
    def create_vhost_bdev(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVhostBdevRsp()

        o = zbsutils.create_vhost_bdev(cmd.hostIp, cmd.sshPort, cmd.sshUsername, cmd.sshPassword,
                                       cmd.logicalPool, cmd.volume, cmd.bdevName)
        r = jsonobject.loads(o)
        if not r.success:
            raise Exception('failed to create vhost bdev[%s] for volume[%s/%s] on host[%s], error[%s]' % (
                cmd.bdevName, cmd.logicalPool, cmd.volume, cmd.hostIp, r.error.message))

        rsp.socketPath = zbsutils.vhost_socket_path(cmd.bdevName)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_vhost_bdev(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        o = zbsutils.delete_vhost_bdev(cmd.hostIp, cmd.sshPort, cmd.sshUsername, cmd.sshPassword,
                                       cmd.bdevName)
        r = jsonobject.loads(o)
        if not r.success:
            raise Exception('failed to delete vhost bdev[%s] on host[%s], error[%s]' % (
                cmd.bdevName, cmd.hostIp, r.error.message))

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

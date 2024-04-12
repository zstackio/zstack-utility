import math
import tempfile

__author__ = 'frank'

import pprint
import traceback
import cephprimarystorage
import urlparse
import rados
import rbd
import Queue
import threading
import simplejson

import zstacklib.utils.daemon as daemon
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.lock as lock
import zstacklib.utils.sizeunit as sizeunit
from zstacklib.utils.ceph import get_mon_addr
from zstacklib.utils.report import *
from zstacklib.utils.bash import *
from zstacklib.utils.rollback import rollback, rollbackable
from zstacklib.utils.plugin import completetask
import os
from zstacklib.utils import shell, iproute
from zstacklib.utils import plugin
from zstacklib.utils import linux
from zstacklib.utils import ceph
from zstacklib.utils import bash
from zstacklib.utils import qemu_img
from zstacklib.utils import traceable_shell
from zstacklib.utils import nbd_client
from zstacklib.utils import thread
from imagestore import ImageStoreClient
from zstacklib.utils.linux import remote_shell_quote
from cephdriver import CephDriver
from thirdpartycephdriver import ThirdpartyCephDriver
from zstacklib.utils.misc import IgnoreError
from distutils.version import LooseVersion

log.configure_log('/var/log/zstack/ceph-primarystorage.log')
logger = log.get_logger(__name__)


class CephPoolCapacity(object):
    def __init__(self, name, available, used, total, replicated_size, security_policy, disk_utilization, related_osds, related_osd_capacity):
        self.name = name
        self.availableCapacity = available
        self.usedCapacity = used
        self.totalCapacity = total
        self.replicatedSize = replicated_size
        self.securityPolicy = security_policy
        self.diskUtilization = round(disk_utilization, 3)
        self.relatedOsds = related_osds
        self.relatedOsdCapacity = related_osd_capacity


class AgentCommand(object):
    def __init__(self):
        pass


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None
        self.poolCapacities = None  # type: list[CephPoolCapacity]
        self.type = None

    def set_err(self, err):
        self.success = False
        self.error = err

class CleanTrashRsp(AgentResponse):
    def __init__(self):
        super(CleanTrashRsp, self).__init__()
        self.pool2TrashResult = {} # type: dict[str,list]


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
        self.manufacturer = None

class DownloadRsp(AgentResponse):
    def __init__(self):
        super(DownloadRsp, self).__init__()
        self.size = None


class CloneRsp(AgentResponse):
    def __init__(self):
        super(CloneRsp, self).__init__()
        self.size = None
        self.actualSize = None
        self.installPath = None


class CpRsp(AgentResponse):
    def __init__(self):
        super(CpRsp, self).__init__()
        self.size = None
        self.actualSize = None
        self.installPath = None

class CreateSnapshotRsp(AgentResponse):
    def __init__(self):
        super(CreateSnapshotRsp, self).__init__()
        self.size = None
        self.actualSize = None
        self.installPath = None

class RollbackSnapshotRsp(AgentResponse):
    def __init__(self):
        super(RollbackSnapshotRsp, self).__init__()
        self.size = None

class GetVolumeSizeRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class GetBatchVolumeSizeRsp(AgentResponse):
    def __init__(self):
        super(GetBatchVolumeSizeRsp, self).__init__()
        self.actualSizes = {}

class GetVolumeWatchersRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeWatchersRsp, self).__init__()
        self.watchers = None

class GetVolumeSnapshotSizeRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSnapshotSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class GetBackingChainRsp(AgentResponse):
    def __init__(self):
        super(GetBackingChainRsp, self).__init__()
        self.totalSize = 0
        self.backingChain = []

class PingRsp(AgentResponse):
    def __init__(self):
        super(PingRsp, self).__init__()
        self.failure = None


class GetFactsRsp(AgentResponse):
    def __init__(self):
        super(GetFactsRsp, self).__init__()
        self.fsid = None
        self.monAddr = None
        self.ipAddresses = None

class ResizeVolumeRsp(AgentResponse):
    def __init__(self):
        super(ResizeVolumeRsp, self).__init__()
        self.size = None


class AccessPathInfo():
    def __init__(self):
        self.accessPathId = None
        self.name = None
        self.accessPathIqn = None
        self.targetCount = 0

class GetAccessPathRsp(AgentResponse):
    def __init__(self):
        super(GetAccessPathRsp, self).__init__()
        self.infos = []


class GetVolumeSnapInfosRsp(AgentResponse):
    def __init__(self):
        super(GetVolumeSnapInfosRsp, self).__init__()
        self.snapInfos = None

class CreateEmptyVolumeRsp(AgentResponse):
    def __init__(self):
        super(CreateEmptyVolumeRsp, self).__init__()
        self.size = 0


class CreateEmptyBlockVolumeRsp(AgentResponse):
    def __init__(self):
        super(CreateEmptyBlockVolumeRsp, self).__init__()
        self.size = 0


class GetDownloadBitsFromKvmHostProgressRsp(AgentResponse):
    def __init__(self):
        super(GetDownloadBitsFromKvmHostProgressRsp, self).__init__()
        self.totalSize = None

class DownloadBitsFromKvmHostRsp(AgentResponse):
    def __init__(self):
        super(DownloadBitsFromKvmHostRsp, self).__init__()
        self.format = None

class DownloadBitsFromNbdRsp(AgentResponse):
    def __init__(self):
        super(DownloadBitsFromNbdRsp, self).__init__()
        self.diskSize = None

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


class RbdImageWriter(object):
    def __init__(self, poolname, imagename, conffile='/etc/ceph/ceph.conf'):
        self.cluster = rados.Rados(conffile=conffile)
        self.poolname = poolname
        self.imagename = imagename
        self.ioctx = None
        self.image = None

    def __enter__(self):
        self.cluster.connect()
        self.ioctx = self.cluster.open_ioctx(self.poolname)
        self.image = rbd.Image(self.ioctx, self.imagename)
        return self.image

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.image:
                self.image.close()
        except:
            pass

        try:
            if self.ioctx:
                self.ioctx.close()
        except:
            pass

        try:
            if self.cluster:
                self.cluster.shutdown()
        except:
            pass


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
    BATCH_GET_VOLUME_SIZE_PATH = "/ceph/primarystorage/batchgetvolumesize"
    GET_VOLUME_WATCHES_PATH = "/ceph/primarystorage/getvolumewatchers"
    GET_VOLUME_SNAPSHOT_SIZE_PATH = "/ceph/primarystorage/getvolumesnapshotsize"
    GET_BACKING_CHAIN_PATH = "/ceph/primarystorage/volume/getbackingchain"
    DELETE_VOLUME_CHAIN_PATH = "/ceph/primarystorage/volume/deletechain"

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
    DOWNLOAD_BITS_FROM_NBD_EXPT_PATH = "/ceph/primarystorage/nbd/download"
    CLAEN_TRASH_PATH = "/ceph/primarystorage/trash/clean"
    CANCEL_DOWNLOAD_BITS_FROM_KVM_HOST_PATH = "/ceph/primarystorage/kvmhost/download/cancel"
    GET_DOWNLOAD_BITS_FROM_KVM_HOST_PROGRESS_PATH = "/ceph/primarystorage/kvmhost/download/progress"
    JOB_CANCEL = "/job/cancel"
    XSKY_GET_BLOCK_VOLUME_ACCESS_PATH = "/xsky/ceph/primarystorage/volume/access/path"
    XSKY_RESIZE_BLOCK_VOLUME = "/xsky/ceph/primarystorage/volume/resize"
    XSKY_CREATE_VOLUME_PATH = "/xsky/ceph/primarystorage/volume/createempty"
    XSKY_DELETE_PATH = "/xsky/ceph/primarystorage/delete"
    XSKY_UPDATE_BLOCK_VOLUME = "/xsky/ceph/primarystorage/volume/update"
    XSKY_UPDATE_BLOCK_VOLUME_SNAPSHOT = "/xsky/ceph/primarystorage/volume/snapshot/update"

    CEPH_CONF_PATH = "/etc/ceph/ceph.conf"

    http_server = http.HttpServer(port=7762)
    http_server.logfile_path = log.get_logfile_path()

    mapping = {
        'ceph': CephDriver,
        'thirdpartyCeph': ThirdpartyCephDriver
    }

    def get_driver(self, cmd):
        if self.is_third_party_ceph(cmd):
            ps_type = 'thirdpartyCeph'
        else:
            ps_type = 'ceph'

        return self.mapping.get(ps_type)(cmd)

    def get_third_party_driver(self, cmd):
        return self.mapping.get('thirdpartyCeph')(cmd)

    def is_third_party_ceph(self, token_object):
        return hasattr(token_object, "token") and token_object.token

    def __init__(self):
        super(CephAgent, self).__init__()
        self._init_third_party_ceph()
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
        self.http_server.register_async_uri(self.BATCH_GET_VOLUME_SIZE_PATH, self.batch_get_volume_size)
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
        self.http_server.register_async_uri(self.GET_BACKING_CHAIN_PATH, self.get_volume_backing_chain)
        self.http_server.register_async_uri(self.DELETE_VOLUME_CHAIN_PATH, self.delete_volume_backing_chain)
        self.http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_KVM_HOST_PATH, self.download_from_kvmhost)
        self.http_server.register_async_uri(self.CANCEL_DOWNLOAD_BITS_FROM_KVM_HOST_PATH, self.cancel_download_from_kvmhost)
        self.http_server.register_async_uri(self.JOB_CANCEL, self.cancel)
        self.http_server.register_async_uri(self.GET_DOWNLOAD_BITS_FROM_KVM_HOST_PROGRESS_PATH, self.get_download_bits_from_kvmhost_progress)
        self.http_server.register_async_uri(self.DOWNLOAD_BITS_FROM_NBD_EXPT_PATH, self.download_from_nbd)
        self.http_server.register_async_uri(self.CLAEN_TRASH_PATH, self.clean_trash)

        self.http_server.register_async_uri(self.XSKY_GET_BLOCK_VOLUME_ACCESS_PATH, self.get_block_volume_access)
        self.http_server.register_async_uri(self.XSKY_RESIZE_BLOCK_VOLUME, self.resize_block_volume)
        self.http_server.register_async_uri(self.XSKY_CREATE_VOLUME_PATH, self.create_block_volume)
        self.http_server.register_async_uri(self.XSKY_DELETE_PATH, self.delete_block_volume)
        self.http_server.register_async_uri(self.XSKY_UPDATE_BLOCK_VOLUME, self.update_block_volume_info)
        self.http_server.register_async_uri(self.XSKY_UPDATE_BLOCK_VOLUME_SNAPSHOT, self.update_block_volume_snapshot)

        self.imagestore_client = ImageStoreClient()

        self.cluster = None
        self.ioctx = {}
        self.op_lock = threading.Lock()

    def get_ioctx(self, pool_name):
        # type: (str) -> rados.Ioctx

        if pool_name in self.ioctx:
            return self.ioctx[pool_name]

        with self.op_lock:
            if not self.cluster:
                self.cluster = rados.Rados(conffile=self.CEPH_CONF_PATH)
                self.cluster.connect()

            self.ioctx[pool_name] = self.cluster.open_ioctx(pool_name)

        return self.ioctx[pool_name]

    def _init_third_party_ceph(self):
        if not ceph.is_xsky():
            return

        o = shell.call('xms-cli --version')
        xms_version = o.split("\n")[0].split("xms-cli Version:")[1].split("_")[1].strip()
        if xms_version and LooseVersion(xms_version) >= LooseVersion('5.2.106.2.230330'):
            return

        regex = 'grep -v 3.10.0-'
        cfg_path = '/etc/init.d/xdc'
        if len(linux.filter_file_lines_by_regex(cfg_path, regex)) != 0:
            return

        command = """sed -i "s/sed '\/^xdc_proxy_feature/uname -r |grep -v 3.10.0- || &/" /etc/init.d/xdc
        systemctl daemon-reload;
        systemctl enable xdc;
        systemctl start xdc
        """
        shell.call(command)

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
        rsp.type = ceph.get_ceph_manufacturer()

        if not df.pools:
            return

        pools = ceph.get_pools_capacity()
        if not pools:
            return

        rsp.poolCapacities = []
        for pool in pools:
            pool_capacity = CephPoolCapacity(pool.pool_name,
                                             pool.available_capacity, pool.used_capacity, pool.pool_total_size,
                                             pool.replicated_size, pool.security_policy, pool.disk_utilization,
                                             pool.get_related_osds(), pool.related_osd_capacity)
            rsp.poolCapacities.append(pool_capacity)

    @in_bash
    def _get_file_actual_size(self, path):
        fast_diff_enabled = shell.run("rbd --format json info %s | grep fast-diff | grep -qv 'fast diff invalid'" % path) == 0

        # if no fast-diff supported and not xsky ceph skip actual size check
        if not fast_diff_enabled and not ceph.is_xsky():
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

        r, size, e = bash.bash_roe("rbd du %s | awk 'END {if(NF==3) {print $3} else {print $4,$5} }' | sed s/[[:space:]]//g" % path, pipe_fail=True)
        if r != 0:
            logger.warn("failed to get actual size of %s, because %s" % (path, e))
            return None

        size = size.strip()
        if not size:
            return None

        return sizeunit.get_size(size)

    def _get_file_size(self, path):
        o = shell.call('rbd --format json info %s' % path)
        o = jsonobject.loads(o)
        return long(o.size_)

    @staticmethod
    def _get_parent(path):
        o = shell.call('rbd --format json info %s' % path)
        o = jsonobject.loads(o)
        return o.parent

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

        linux.qemu_img_resize('rbd:%s/%s' % (pool, image_name), cmd.size, 'raw', cmd.force)
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
        bash_roe('rbd snap purge {{IMAGE_PATH}}')
        bash_errorout('rbd rm {{IMAGE_PATH}}')
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @bash.in_bash
    def clean_trash(self, req):
        rsp = CleanTrashRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if not cmd.pools or not ceph.support_defer_deleting():
            return jsonobject.dumps(rsp)

        force = "--force" if cmd.force else ""
        for pool_name in set(cmd.pools):
            r, o, e = bash_roe("rbd trash list -p %s --format json" % pool_name)
            if r != 0 or o.strip() == '':
                continue

            rsp.pool2TrashResult.update({pool_name: []})
            trash_list = jsonobject.loads(o)
            if len(trash_list) != 0 and isinstance(trash_list[0], str):
                trash_list = [{"id": trash_list[idx], "name": trash_list[idx+1]} for idx in range(0, len(trash_list), 2)]
                trash_list = jsonobject.loads(simplejson.dumps(trash_list))

            for trash in trash_list:
                r, o, e = bash_roe("rbd trash rm %s/%s %s" % (pool_name, trash.id, force))
                if r == 0:
                    rsp.pool2TrashResult.get(pool_name).append(trash.name)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetFactsRsp()

        monmap = bash_o('ceph mon dump -f json')
        rsp.monAddr = get_mon_addr(monmap, "kernel")
        if rsp.monAddr is None:
            rsp.monAddr = get_mon_addr(monmap)

        if not rsp.monAddr:
            raise Exception('cannot find mon address of the mon server[%s]' % cmd.monUuid)

        rsp.fsid = ceph.get_fsid()
        rsp.type = ceph.get_ceph_manufacturer()

        ip_addresses = [chunk.address for chunk in filter(
            lambda x: x.address != '127.0.0.1' and not x.ifname.endswith('zs'), iproute.query_addresses(ip_version=4))]
        rsp.ipAddresses = ip_addresses

        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        monmap = bash_o('ceph mon dump -f json')
        found = False
        for mon in jsonobject.loads(monmap).mons:
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
            bash_r("timeout 60 rados -p '%s' rm '%s'" % (pool, objname))
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
        linux.write_uuids("cephmonps", "cephmonps=%s" % cmd.monUuid)

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
    def batch_get_volume_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetBatchVolumeSizeRsp()

        for uuid, installPath in cmd.volumeUuidInstallPaths.__dict__.items():
            with IgnoreError():
                path = self._normalize_install_path(installPath)
                rsp.actualSizes[uuid] = self._get_file_actual_size(path)

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
        rsp = RollbackSnapshotRsp()
        self._set_capacity_to_response(rsp)

        self.validate_snapshot_rollback(spath, rsp, cmd.capacityThreshold)

        driver = self.get_driver(cmd)
        driver.rollback_snapshot(cmd)
        rsp.size = self._get_file_size(spath)
        return jsonobject.dumps(rsp)

    def validate_snapshot_rollback(self, spath, rsp, threshold=0.9):
        if not threshold or threshold > 0.9:
            threshold = 0.9

        asize = self._get_file_actual_size(spath)
        if asize is None:
            return

        pool_name = spath.split("/")[0]
        for cap in rsp.poolCapacities:
            if cap.name == pool_name and cap.usedCapacity + asize > cap.totalCapacity * threshold:
                raise Exception("In the worst case, The rollback operation will exceed the 90%% capacity of the pool[%s]" % pool_name)

    @staticmethod
    def _wrap_shareable_cmd(cmd, cmd_string):
        if cmd.shareable:
            return cmd_string + " --image-shared"
        return cmd_string

    @replyerror
    def cp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        if cmd.sendCommandUrl:
            Report.url = cmd.sendCommandUrl

        report = Report(cmd.threadContext, cmd.threadContextStack)
        report.processType = "CephCpVolume"
        PFILE = linux.create_temp_file()
        stage = (cmd.threadContext['task-stage'], "10-90")[cmd.threadContext['task-stage'] is None]

        def _get_progress(synced):
            if not Report.url:
                return synced

            logger.debug("getProgress in ceph-agent")
            percent = shell.call("tail -1 %s | grep -o '1\?[0-9]\{1,2\}%%' | tail -1" % PFILE).strip(' \t\n\r%')
            if percent and Report.url:
                report.progress_report(get_exact_percent(percent, stage), "report")
            return synced

        def _get_cp_cmd():
            return "deep cp" if shell.run("rbd help deep cp > /dev/null") == 0 else "cp"

        t_shell = traceable_shell.get_shell(cmd)
        _, _, err = t_shell.bash_progress_1(
            self._wrap_shareable_cmd(cmd, 'rbd %s %s %s 2> %s' % (_get_cp_cmd(), src_path, dst_path, PFILE)),
            _get_progress)

        if os.path.exists(PFILE):
            os.remove(PFILE)

        shell.run('rbd snap purge %s' % dst_path)
        if err:
            shell.run('rbd rm %s' % dst_path)
            raise err

        rsp = CpRsp()
        rsp.size = self._get_file_size(dst_path)
        rsp.installPath = cmd.dstPath
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
        class ImageStoreDownloadDaemon(plugin.TaskDaemon):
            def __init__(self, driver, task_spec):
                super(ImageStoreDownloadDaemon, self).__init__(task_spec, "download image")
                self.task_spec = task_spec
                self.driver = driver

            def _cancel(self):
                traceable_shell.cancel_job_by_api(self.api_id)
                self.driver.do_deletion(self.task_spec, self.task_spec.psInstallPath, True)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        with ImageStoreDownloadDaemon(self.get_driver(cmd), task_spec=cmd):
            return self.imagestore_client.download_imagestore(cmd)

    @replyerror
    def create_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = self._normalize_install_path(cmd.snapshotPath)

        rsp = CreateSnapshotRsp()
        rsp.installPath = cmd.snapshotPath

        do_create = True
        if cmd.skipOnExisting:
            image_name, sp_name = spath.split('@')
            o = shell.call('rbd --format json snap ls %s' % image_name)
            o = jsonobject.loads(o)
            for s in o:
                if s.name_ == sp_name:
                    do_create = False

        if do_create:
            driver = self.get_driver(cmd)
            rsp = driver.create_snapshot(cmd, rsp)
            rsp.actualSize = self._get_file_actual_size(spath)

        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    def _unprotect_snapshot(self, snapshot_path):
        path = self._normalize_install_path(snapshot_path)
        o = shell.call('rbd --format json info %s' % path)
        o = jsonobject.loads(o)
        if not o or o.protected is None or o.protected.lower() != 'true':
            return

        o = bash_o('rbd children %s' % path)
        o = o.strip(' \t\r\n')
        if o:
            raise Exception("the snapshot[%s] is still in used, children: %s" % (snapshot_path, o))

        shell.call('rbd snap unprotect %s' % path)

    @replyerror
    def delete_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._unprotect_snapshot(cmd.snapshotPath)
        driver = self.get_driver(cmd)
        driver.delete_snapshot(cmd)

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
        self._unprotect_snapshot(cmd.snapshotPath)
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
        rsp = CloneRsp()
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)
        src_pool = src_path.split('/')[0]
        dst_pool = dst_path.split('/')[0]

        driver = self.get_driver(cmd)
        rsp = driver.clone_volume(cmd, rsp)

        rsp.size = self._get_file_size(src_path)
        ALIGNMENT_SIZE = 4096.0
        if ceph.is_xsky() and src_pool != dst_pool and rsp.size % ALIGNMENT_SIZE != 0:
            new_size = int(math.ceil(rsp.size / ALIGNMENT_SIZE) * ALIGNMENT_SIZE)
            shell.call("qemu-img resize -f raw rbd:%s %s" % (dst_path, new_size))
            rsp.size = new_size
            logger.info("image size must be an integer multiple of 4KB, now resize it to %s bytes" % new_size)
        self._set_capacity_to_response(rsp)
        rsp.actualSize = self._get_file_actual_size(dst_path)
        return jsonobject.dumps(rsp)

    @replyerror
    def flatten(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        path = self._normalize_install_path(cmd.path)

        if not self._get_parent(path):
            self._set_capacity_to_response(rsp)
            return jsonobject.dumps(AgentResponse())

        p_file = tempfile.mktemp()
        report = Report.from_spec(cmd, "FlattenVolume")

        def _get_percent(synced):
            t = linux.tail_1(p_file, split=b"\r")
            if t:
                for word in t.split():
                    if word.endswith('%'):
                        report.progress_report(get_exact_percent(int(word[:-1]), report.taskStage))
                        break
            return synced

        t_shell = traceable_shell.get_shell(cmd)
        t_shell.bash_progress_1('rbd flatten %s 2> %s' % (path, p_file), _get_percent)
        linux.rm_file_force(p_file)

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

        realname = cmd.poolName
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

        driver = self.get_driver(cmd)
        driver.validate_token(cmd)

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

        rsp.fsid = ceph.get_fsid()
        self._set_capacity_to_response(rsp)

        rsp.manufacturer = ceph.get_ceph_manufacturer()

        return jsonobject.dumps(rsp)

    def _normalize_install_path(self, path):
        return path.replace('ceph://', '')

    def _parse_install_path(self, path):
        return self._normalize_install_path(path).split('/')

    @replyerror
    def create(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateEmptyVolumeRsp()
        driver = self.get_driver(cmd)
        rsp = driver.create_volume(cmd, rsp, agent=self)

        self._set_capacity_to_response(rsp)
        rsp.actualSize = self._get_file_actual_size(self._normalize_install_path(cmd.installPath))
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
            shell.call(self._wrap_shareable_cmd(cmd, 'set -o pipefail; ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s root@%s cat %s | %s rbd import --image-format 2 - %s/%s' % (port, prikey_file, hostname, remote_shell_quote(cmd.backupStorageInstallPath), bandWidth, pool, tmp_image_name)))
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
        if not self._ensure_existing_volume_has_no_snapshot(path):
            return jsonobject.dumps(rsp)

        if self._get_watcher(path):
            rsp.inUse = True
            rsp.success = False
            rsp.error = "unable to delete %s, the volume is in use" % cmd.installPath
            logger.debug("the rbd image[%s] still has watchers, unable to delete" % cmd.installPath)
            return jsonobject.dumps(rsp)

        driver = self.get_driver(cmd)
        driver.do_deletion(cmd, path, defer=True)

        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    def _ensure_existing_volume_has_no_snapshot(self, path):
        try:
            snaps = self._get_snapshots(path)
        except Exception as e:
            if 'No such file or directory' not in str(e):
                raise
            logger.warn('delete %s;encounter %s' % (path, str(e)))
            return False

        if len(snaps) > 0:
            raise Exception('unable to delete %s; the volume still has snapshots' % path)

        return True

    def _get_watcher(self, path):
        watchers_result = shell.call('timeout 10 rbd status %s' % path)
        if watchers_result:
            for watcher in watchers_result.splitlines():
                if "watcher=" in watcher:
                    return watcher
        return None

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
            return r, e

        # compare md5sum of src/dst segments
        src_segment_md5 = self._read_file_content('/tmp/%s_src_md5' % resource_uuid)
        dst_segment_md5 = linux.sshpass_call(dst_mon_addr, dst_mon_passwd, 'cat /tmp/%s_dst_md5' % resource_uuid, dst_mon_user, dst_mon_port)
        if src_segment_md5 != dst_segment_md5:
            err = 'check sum mismatch after migration: %s' % src_install_path
            logger.error(err)
            return -1, err
        return 0, None

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

        ret_code, err = self._migrate_volume_segment(cmd.parentUuid, cmd.resourceUuid, cmd.srcInstallPath,
                                           cmd.dstInstallPath, cmd.dstMonHostname, cmd.dstMonSshUsername,
                                           cmd.dstMonSshPassword, cmd.dstMonSshPort, cmd)
        if ret_code != 0:
            rsp.success = False
            rsp.error = "Failed to migrate volume segment from %s to another, because: %s" % (ceph.get_ceph_manufacturer(), err)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def get_volume_snapinfos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vpath = self._normalize_install_path(cmd.volumePath)
        rsp = GetVolumeSnapInfosRsp()
        rsp.snapInfos = self._get_snapshots(vpath)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @staticmethod
    def _get_snapshots(volume_path):
        ret = shell.call('rbd --format=json snap ls %s' % volume_path)
        return jsonobject.loads(ret)

    @replyerror
    def get_volume_backing_chain(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.volumePath)
        rsp = GetBackingChainRsp()

        parent = self._get_parent(path)
        while parent:
            path = "ceph://%s/%s@%s" % (parent["pool"], parent["image"], parent["snapshot"])
            rsp.backingChain.append(path)
            parent = self._get_parent(path.replace("ceph://", ""))

        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_volume_backing_chain(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        driver = self.get_driver(cmd)
        for path in cmd.installPaths:
            path = self._normalize_install_path(path)
            if "@" in path:
                vol_path = path.split("@")[0]
                shell.run('rbd snap unprotect %s' % path)
                shell.call('rbd snap rm %s' % path)
            else:
                vol_path = path
            self._ensure_existing_volume_has_no_snapshot(vol_path)
            watchers = self._get_watcher(vol_path)
            if watchers:
                raise Exception('volume %s has watchers %s, can not delete it' % (vol_path, watchers))
            driver.do_deletion(cmd, vol_path)

        return jsonobject.dumps(rsp)

    @replyerror
    @completetask
    @rollback
    def download_from_kvmhost(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DownloadBitsFromKvmHostRsp()

        pool, image_name = self._parse_install_path(cmd.primaryStorageInstallPath)

        def validate_task_result_existing(_):
            return shell.run("rbd ls %s | grep -q %s" % (pool, image_name)) == 0

        last_task = self.load_and_save_task(req, rsp, validate_task_result_existing, None)
        if last_task and last_task.agent_pid == os.getpid():
            rsp = self.wait_task_complete(last_task)
            return jsonobject.dumps(rsp)

        self.do_sftp_download(cmd, pool, image_name)
        rsp.format = linux.get_img_fmt("rbd:%s/%s" % (pool, image_name))
        return jsonobject.dumps(rsp)

    @replyerror
    @in_bash
    def cancel_download_from_kvmhost(self, req):
        return self.cancel_sftp_download(req)

    @replyerror
    def cancel(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        return jsonobject.dumps(plugin.cancel_job(cmd, rsp))

    @replyerror
    def get_download_bits_from_kvmhost_progress(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetDownloadBitsFromKvmHostProgressRsp()
        totalSize = 0
        for path in cmd.volumePaths:
            pool, image_name = self._parse_install_path(path)
            path = "%s/tmp-%s" % (pool, image_name)
            if bash_r('rbd info %s' % path) != 0:
                continue
            size = self._get_file_actual_size(path)
            if size is not None:
                totalSize += long(size)

        rsp.totalSize = totalSize
        return jsonobject.dumps(rsp)

    def _nbd2rbd(self, hostname, port, export_name, rbdtarget, bandwidth, report, rsp):

        def write_full(wr, data, offset, nbytes):
            n = 0
            while n < nbytes:
                n += wr.write(data[n:], offset+n)

        def queue_consumer(cq, w, rsp):
            logger.info("xxx: queue consumer started")

            while not rsp.error:
                data, offset, nbytes, is_zero = cq.get(True, 10)
                if offset < 0: # signal end
                    break

                try:
                    if is_zero:
                        w.discard(offset, nbytes)
                    else:
                        write_full(w, data, offset, nbytes)
                except Exception as e:
                    rsp.error = "write error at offset = %d, len = %d" % (offset, nbytes)
                    logger.warn("xxx: write error: %s" % str(e))
                    break


        poolname, imagename = rbdtarget.split('/')
        client = nbd_client.NBDClient()
        client.connect(hostname, port, None, export_name)
        cqueue = Queue.Queue(8)
        offset, disk_size = 0, client.get_block_size()
        last_report_time = time.time()

        try:

            with RbdImageWriter(poolname, imagename) as image:
                if image.size() != disk_size:
                    logger.info('backup volume size %d and current volume size %d mismatch, resizing...' % (disk_size, image.size()))
                    image.resize(disk_size)
                    logger.info('volume resized to %d' % disk_size)

                chunk_size = 1048576
                zero_chunk = '\x00' * chunk_size
                remainder_size = disk_size % chunk_size

                thread.ThreadFacade.run_in_thread(queue_consumer, [cqueue, image, rsp])

                while offset < disk_size:
                    if offset + chunk_size > disk_size:
                        chunk_size, zero_chunk = remainder_size, '\x00' * remainder_size

                    data  = client.read(offset, chunk_size) # client has 'read all' semantic
                    if len(data) != chunk_size:
                        logger.warn("expected chunk size %d, got %d" % (chunk_size, len(data)))

                    cqueue.put((data, offset, chunk_size, data == zero_chunk), True, 10)
                    offset += chunk_size

                    if time.time() > last_report_time + 1:
                        percent = int(round(float(offset) / float(disk_size) * 100))
                        report.progress_report(get_exact_percent(percent, report.taskStage), "report")
                        last_report_time = time.time()

                # signal end
                cqueue.put((b'', -1, 0, False), True, 10)
                logger.info("xxx: all aio requests submitted, size = %d" % offset)
                while not rsp.error and not cqueue.empty():
                    time.sleep(0.1)
                image.flush()
        except Queue.Full:
            rsp.srror = 'rbd write timed out at offset: %d' % offset
        finally:
            logger.info("xxx: bytes written: "+str(offset))

            try: client.close()
            except: pass

        return disk_size

    @replyerror
    def download_from_nbd(self, req):
        rsp = DownloadBitsFromNbdRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        bandwidth = cmd.bandwidth
        nbdexpurl = cmd.nbdExportUrl
        rbdtarget = cmd.primaryStorageInstallPath

        u = urlparse.urlparse(nbdexpurl)
        if u.scheme != 'nbd':
            rsp.error = 'unexpected protocol: %s' % nbdexpurl
            return jsonobject.dumps(rsp)

        rsp.diskSize = self._nbd2rbd(u.hostname, u.port, os.path.basename(u.path), self._normalize_install_path(rbdtarget), bandwidth,
                      Report.from_spec(cmd, "DownFromNbd"), rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def get_block_volume_access(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetAccessPathRsp()
        driver = self.get_third_party_driver(cmd)
        access_paths = driver.get_all_access_path(cmd)

        if cmd.iscsiPath:
            iqn = cmd.iscsiPath.replace('iscsi://', '').split("/")[1]
            for access_path in access_paths:
                if access_path.iqn in iqn:
                    access_path_info = AccessPathInfo()
                    access_path_info.accessPathId = access_path.id
                    access_path_info.name = access_path.name
                    access_path_info.accessPathIqn = access_path.iqn
                    rsp.infos.append(access_path_info)
                    break
        else:
            for access_path in access_paths:
                access_path_info = AccessPathInfo()
                access_path_info.accessPathId = access_path.id
                access_path_info.name = access_path.name
                access_path_info.accessPathIqn = access_path.iqn
                rsp.infos.append(access_path_info)

        for accessInfo in rsp.infos:
            targets = driver.get_targets_by_access_path_id(cmd, accessInfo.accessPathId)
            accessInfo.targetCount = len(targets)
            accessInfo.gatewayIps = [target.gateway_ips for target in targets]

        rsp.infos = sorted(rsp.infos, key=lambda info: info.targetCount, reverse=True)

        return jsonobject.dumps(rsp)

    @replyerror
    def resize_block_volume(self, req):
        rsp = ResizeVolumeRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        driver = self.get_third_party_driver(cmd)
        rsp.size = driver.resize_block_volume(cmd, cmd.xskyBlockVolumeId, cmd.size)
        return jsonobject.dumps(rsp)

    @replyerror
    def create_block_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateEmptyBlockVolumeRsp()
        driver = self.get_third_party_driver(cmd)
        rsp = driver.create_volume(cmd, rsp, agent=self)
        self._set_capacity_to_response(rsp)
        rsp.actualSize = self._get_file_actual_size(self._normalize_install_path(cmd.installPath))
        return jsonobject.dumps(rsp)

    @replyerror
    def delete_block_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        path = self._normalize_install_path(cmd.installPath)

        rsp = AgentResponse()
        if not self._ensure_existing_volume_has_no_snapshot(path):
            return jsonobject.dumps(rsp)

        if self._get_watcher(path):
            rsp.inUse = True
            rsp.success = False
            rsp.error = "unable to delete %s, the volume is in use" % cmd.installPath
            logger.debug("the block volume[%s] still has watchers, unable to delete" % cmd.installPath)
            return jsonobject.dumps(rsp)

        driver = self.get_third_party_driver(cmd)
        driver.do_deletion(cmd, path)
        return jsonobject.dumps(rsp)

    @replyerror
    def update_block_volume_info(self, req):
        rsp = AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        driver = self.get_third_party_driver(cmd)
        driver.update_block_volume_info(cmd, cmd.xskyBlockVolumeId, cmd.name, cmd.description)
        if cmd.burstTotalBw and cmd.burstTotalIops and cmd.maxTotalBw and cmd.maxTotalIops:
            driver.set_block_volume_qos(cmd, cmd.xskyBlockVolumeId, cmd.burstTotalBw, cmd.burstTotalIops, cmd.maxTotalBw,
                                        cmd.maxTotalIops)
        return jsonobject.dumps(rsp)

    @replyerror
    def update_block_volume_snapshot(self, req):
        rsp = AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        driver = self.get_third_party_driver(cmd)
        driver.update_block_volume_snapshot(cmd)
        return jsonobject.dumps(rsp)

class CephDaemon(daemon.Daemon):
    def __init__(self, pidfile, py_process_name):
        super(CephDaemon, self).__init__(pidfile, py_process_name)

    def run(self):
        self.agent = CephAgent()
        self.agent.http_server.start()

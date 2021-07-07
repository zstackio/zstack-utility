from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import qemu_img

logger = log.get_logger(__name__)


class CheckHostStorageConnectionCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CheckHostStorageConnectionCmd, self).__init__()
        self.monUrls = None
        self.hostUuid = None
        self.uuid = None
        self.poolNames = None


class CheckHostStorageConnectionRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckHostStorageConnectionRsp, self).__init__()


class CephStoragePlugin(kvmagent.KvmAgent):
    CHECK_HOST_STORAGE_CONNECTION_PATH = "/ceph/primarystorage/check/host/connection"
    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CHECK_HOST_STORAGE_CONNECTION_PATH, self.check_host_storage_connection)

    @kvmagent.replyerror
    def check_host_storage_connection(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        mon_url = '\;'.join(cmd.monUrls)
        mon_url = mon_url.replace(':', '\\\:')
        rsp = CheckHostStorageConnectionRsp()

        def get_ceph_rbd_args(pool_name):
            if cmd.userKey is None:
                return 'rbd:%s:mon_host=%s' % (get_heartbeat_volume(pool_name, cmd.uuid, cmd.hostUuid), mon_url)
            return 'rbd:%s:id=zstack:key=%s:auth_supported=cephx\;none:mon_host=%s' % (get_heartbeat_volume(pool_name, cmd.uuid, cmd.hostUuid), cmd.userKey, mon_url)

        def heartbeat_file_exists(pool_name):
            touch = shell.ShellCmd('timeout 5 %s %s' %
                    (qemu_img.subcmd('info'), get_ceph_rbd_args(pool_name)))
            touch(False)

            if touch.return_code == 0:
                return True

            logger.warn('cannot query heartbeat image: %s: %s' % (cmd.heartbeatImagePath, touch.stderr))
            return False

        def create_heartbeat_file(pool_name):
            create = shell.ShellCmd('timeout 5 qemu-img create -f raw %s 1' %
                                        get_ceph_rbd_args(pool_name))
            create(False)

            if create.return_code == 0 or "File exists" in create.stderr:
                return True

            logger.warn('cannot create heartbeat image: %s: %s' % (cmd.heartbeatImagePath, create.stderr))
            return False

        def delete_heartbeat_file(pool_name):
            shell.run("timeout 5 rbd rm --id zstack %s -m %s" %
                    (get_heartbeat_volume(pool_name, cmd.uuid, cmd.hostUuid), mon_url))
        
        def get_heartbeat_volume(pool_name, ps_uuid, host_uuid):
            return '%s/ceph-ps-%s-host-hb-%s' % (pool_name, ps_uuid, host_uuid)

        def get_fencer_key(ps_uuid, pool_name):
            return '%s-%s' % (ps_uuid, pool_name)

        if len(cmd.poolNames) == 0:
            return jsonobject.dumps(rsp)

        failed_pools = []
        for pool_name in cmd.poolNames:    
            if heartbeat_file_exists(pool_name) or create_heartbeat_file(pool_name):
                continue

            failed_pools.append(pool_name)

        if len(failed_pools) == 0:
            return jsonobject.dumps(rsp)

        if len(failed_pools) == len(cmd.poolNames):
            rsp.error = "Can not connect to all pools of ceph storage[uuid:%s] from host[uuid:%s]" % (cmd.uuid, cmd.hostUuid)
        else:
            rsp.error = "Can not connect to pools[%s] of ceph storage[uuid:%s] from host[uuid:%s]" % (', '.join(failed_pools) ,cmd.uuid, cmd.hostUuid)

        rsp.success = False
        return jsonobject.dumps(rsp)
    
    def stop(self):
        pass
        
    def configure(self, config):
        self.config = config

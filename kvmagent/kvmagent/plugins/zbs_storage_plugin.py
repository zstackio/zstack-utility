import json
import os.path

from kvmagent import kvmagent
from kvmagent.plugins import zbs_vhost_target
from kvmagent.plugins.zbs_vhost_rpc import ZbsVhostRpc
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import shell



logger = log.get_logger(__name__)


def query_allocated_extents(path):
    output = shell.call("zbs query diff --path %s --format json" % linux.shellquote(path))
    response = json.loads(output.strip())
    if not isinstance(response, dict):
        raise ValueError("invalid zbs query diff response: expected an object")

    error = response.get('error')
    if error:
        if isinstance(error, dict):
            code = error.get('code')
            message = error.get('message') or str(error)
        else:
            code = None
            message = str(error)
        raise RuntimeError("zbs query diff failed for %s: code=%s, message=%s" % (path, code, message))

    extents = response.get('result')
    if not isinstance(extents, list):
        raise ValueError("invalid zbs query diff response: result must be a list")

    result = {}
    for item in extents:
        exists = item.get('exists')
        if not (exists is True or str(exists).lower() == 'true'):
            continue
        start = int(item['offset'])
        length = int(item['length'])
        if start < 0 or length <= 0:
            raise ValueError("invalid zbs query diff extent: offset must be non-negative and length must be positive")
        result[start] = length
    return result


class CheckHostStorageConnectionRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckHostStorageConnectionRsp, self).__init__()


class VhostActivateRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(VhostActivateRsp, self).__init__()
        self.socketPath = None


class VhostTargetHealthRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(VhostTargetHealthRsp, self).__init__()
        self.targetRunning = False


class ZbsStoragePlugin(kvmagent.KvmAgent):
    CHECK_HOST_STORAGE_CONNECTION_PATH = "/zbs/primarystorage/check/host/connection"
    UPDATE_HOST_DEPENDENCY_PATH = "/zbs/primarystorage/host/updatedependency"
    VHOST_TARGET_ENSURE_PATH = "/zbs/primarystorage/vhost/target/ensure"
    VHOST_ACTIVATE_PATH = "/zbs/primarystorage/vhost/activate"
    VHOST_DEACTIVATE_PATH = "/zbs/primarystorage/vhost/deactivate"
    VHOST_RESIZE_PATH = "/zbs/primarystorage/vhost/resize"
    VHOST_TARGET_HEALTH_PATH = "/zbs/primarystorage/vhost/target/health"
    PREPARE_VHOST_TARGET_ENV_PATH = "/zbs/primarystorage/vhost/target/prepareenv"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CHECK_HOST_STORAGE_CONNECTION_PATH, self.check_host_storage_connection)
        http_server.register_async_uri(self.UPDATE_HOST_DEPENDENCY_PATH, self.update_host_dependency)
        http_server.register_async_uri(self.VHOST_TARGET_ENSURE_PATH, self.vhost_target_ensure)
        http_server.register_async_uri(self.VHOST_ACTIVATE_PATH, self.vhost_activate)
        http_server.register_async_uri(self.VHOST_DEACTIVATE_PATH, self.vhost_deactivate)
        http_server.register_async_uri(self.VHOST_RESIZE_PATH, self.vhost_resize)
        http_server.register_async_uri(self.VHOST_TARGET_HEALTH_PATH, self.vhost_target_health)
        http_server.register_async_uri(self.PREPARE_VHOST_TARGET_ENV_PATH, self.prepare_vhost_target_env)

    @kvmagent.replyerror
    @bash.in_bash
    def check_host_storage_connection(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckHostStorageConnectionRsp()

        c = 'timeout 20 qemu-io -c "read 0G 4k" -f cbd {}_zbs_:/etc/zbs/client.conf'.format(cmd.path)
        r, o, e = bash.bash_roe(c)
        if r != 0:
            if linux.catch_bad_alloc_exception(r, e):
                return jsonobject.dumps(rsp)
            rsp.error = "failed to check heartbeat[%s], %s" % (cmd.path, e)
            rsp.success = False
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def update_host_dependency(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckHostStorageConnectionRsp()
        releasever = kvmagent.get_host_yum_release()
        packages = cmd.updatePackages.split(',')
        for package in packages:
            yum_cmd = "export YUM0={};yum --enablerepo=* clean all && " \
                      "(rpm -q {} && yum --disablerepo=* --enablerepo={} update {} -y " \
                      "|| yum --disablerepo=* --enablerepo={} install {} -y)"
            yum_cmd = yum_cmd.format(releasever, package.strip(), cmd.zstackRepo,
                                     package.strip(), cmd.zstackRepo, package.strip())
            if shell.run(yum_cmd) != 0:
                rsp.success = False
                rsp.error = "failed to update zbs host client dependency using: %s" % yum_cmd
            else:
                logger.debug("successfully run: %s" % yum_cmd)

        return jsonobject.dumps(rsp)

    @staticmethod
    def _control_sock(cmd):
        return cmd.controlSock if cmd.controlSock else zbs_vhost_target.DEFAULT_CONTROL_SOCK

    @staticmethod
    def _socket_dir(cmd):
        return cmd.socketDir if cmd.socketDir else zbs_vhost_target.DEFAULT_SOCKET_DIR

    @staticmethod
    def _bdev_file(cmd):
        return "%s_zbs_" % cmd.installPath

    def _ensure_target(self, cmd):
        zbs_vhost_target.ensure_target(
            image=cmd.image,
            cores=cmd.cores,
            socket_dir=self._socket_dir(cmd),
            control_sock=self._control_sock(cmd),
            client_conf=cmd.clientConf if cmd.clientConf else zbs_vhost_target.DEFAULT_CLIENT_CONF,
            hugepage_nr=cmd.hugepageNr if cmd.hugepageNr else zbs_vhost_target.DEFAULT_HUGEPAGE_NR,
            image_tar=cmd.imageTar,
            image_url=cmd.imageUrl,
            core_count=cmd.coreCount if cmd.coreCount else zbs_vhost_target.DEFAULT_CORE_COUNT)

    @kvmagent.replyerror
    def vhost_target_ensure(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckHostStorageConnectionRsp()
        self._ensure_target(cmd)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def vhost_activate(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VhostActivateRsp()

        self._ensure_target(cmd)
        rpc = ZbsVhostRpc(self._control_sock(cmd))

        if rpc.get_bdev(cmd.bdevName) is None:
            rpc.bdev_zbs_create(self._bdev_file(cmd), cmd.bdevName)

        if rpc.get_controller(cmd.controllerName) is None:
            rpc.vhost_create_blk_controller(cmd.controllerName, cmd.bdevName)

        rsp.socketPath = os.path.join(self._socket_dir(cmd), cmd.controllerName)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def vhost_deactivate(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckHostStorageConnectionRsp()

        if not zbs_vhost_target.is_running():
            return jsonobject.dumps(rsp)

        rpc = ZbsVhostRpc(self._control_sock(cmd))
        if rpc.get_controller(cmd.controllerName) is not None:
            rpc.vhost_delete_controller(cmd.controllerName)
        if rpc.get_bdev(cmd.bdevName) is not None:
            rpc.bdev_zbs_delete(cmd.bdevName)

        zbs_vhost_target.reclaim_hugepages()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def vhost_resize(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckHostStorageConnectionRsp()
        rpc = ZbsVhostRpc(self._control_sock(cmd))
        rpc.bdev_zbs_resize(cmd.bdevName, cmd.sizeMib)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def vhost_target_health(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VhostTargetHealthRsp()
        rsp.targetRunning = zbs_vhost_target.target_running(self._control_sock(cmd), cmd.containerName)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def prepare_vhost_target_env(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        zbs_vhost_target.ensure_docker()
        zbs_vhost_target.ensure_2m_hugetlbfs_mount()
        zbs_vhost_target.ensure_free_hugepages(
            cmd.hugepageNr if cmd.hugepageNr else zbs_vhost_target.DEFAULT_VHOST_TARGET_HUGEPAGE_NR)
        return jsonobject.dumps(rsp)


    def stop(self):
        pass

    def configure(self, config=None):
        if config is None:
            config = {}
        self.config = config

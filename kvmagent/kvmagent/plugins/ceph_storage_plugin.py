import os
import uuid as uuidlib

from kvmagent import kvmagent
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


class CephLuksRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CephLuksRsp, self).__init__()
        self.actualSize = None


class CephStoragePlugin(kvmagent.KvmAgent):
    CHECK_HOST_STORAGE_CONNECTION_PATH = "/ceph/primarystorage/check/host/connection"
    LUKS_CLONE_PATH = "/ceph/primarystorage/kvmhost/luksclone"
    LUKS_CREATE_EMPTY_PATH = "/ceph/primarystorage/kvmhost/lukscreateempty"
    LUKS_ENCRYPT_IN_PLACE_PATH = "/ceph/primarystorage/kvmhost/encryptinplace"
    LUKS_RESIZE_PATH = "/ceph/primarystorage/kvmhost/luksresize"

    CEPH_CLIENT_CONF_ROOT = "/var/lib/zstack/ceph"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.CHECK_HOST_STORAGE_CONNECTION_PATH, self.check_host_storage_connection)
        http_server.register_async_uri(self.LUKS_CLONE_PATH, self.luks_clone)
        http_server.register_async_uri(self.LUKS_CREATE_EMPTY_PATH, self.luks_create_empty)
        http_server.register_async_uri(self.LUKS_ENCRYPT_IN_PLACE_PATH, self.luks_encrypt_in_place)
        http_server.register_async_uri(self.LUKS_RESIZE_PATH, self.luks_resize)

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
        
        def get_heartbeat_volume(pool_name, ps_uuid, host_uuid):
            return '%s/ceph-ps-%s-host-hb-%s' % (pool_name, ps_uuid, host_uuid)

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
    
    @staticmethod
    def _rbd_uri(install_path, conf_path, extra=None):
        s = "rbd:%s:conf=%s" % (install_path, conf_path)
        if extra:
            s += ":" + extra
        return s

    @staticmethod
    def _rbd_image_opts(install_path, conf_path):
        image_path = install_path
        snapshot = None
        if "@" in image_path:
            image_path, snapshot = image_path.split("@", 1)
        pool, image = image_path.split("/", 1)
        opts = "file.driver=rbd,file.pool=%s,file.image=%s,file.conf=%s" % (pool, image, conf_path)
        if snapshot:
            opts += ",file.snapshot=%s" % snapshot
        return opts

    def _is_luks_rbd(self, install_path, conf_path):
        # Do not pass the one-shot LUKS secret FIFO here: qemu-img info would
        # consume it before the real convert command. The LUKS header is enough
        # for qemu-img to report the source format without opening the payload.
        try:
            out = shell.call("/usr/bin/qemu-img info %s" % self._rbd_uri(install_path, conf_path))
            return "file format: luks" in out
        except Exception as e:
            logger.warn("failed to probe RBD source format for %s: %s" % (install_path, e))
            return False

    @staticmethod
    def _rbd_actual_size(install_path, conf_path):
        try:
            o = shell.call("rbd --conf %s du %s --format json" % (conf_path, install_path))
            j = jsonobject.loads(o)
            images = getattr(j, "images", None)
            if not images:
                return None
            # rbd du json returns a list; first row is the image itself when no
            # snapshots are queried. Pick the first numeric used_size_ we see.
            for it in images:
                used = getattr(it, "used_size_", None)
                if used is not None:
                    return long(used)
            return None
        except Exception as e:
            logger.warn("failed to read rbd du for %s: %s" % (install_path, e))
            return None

    def _validate_luks_cmd(self, cmd, rsp):
        if not getattr(cmd, "psUuid", None):
            rsp.success = False
            rsp.error = "psUuid is required for LUKS ceph operation on KVM host"
            return None
        if not getattr(cmd, "secFilePath", None):
            rsp.success = False
            rsp.error = "secFilePath is required for LUKS ceph operation on KVM host"
            return None
        # ZStack pushes per-PS ceph.conf + client.zstack.keyring to every
        # attached KVM host under /var/lib/zstack/ceph/<ps>/. We reuse that
        # so LUKS clone on a KVM host can talk to ceph without depending on
        # /etc/ceph/ceph.conf (which may not exist on non-converged hosts).
        conf = os.path.join(self.CEPH_CLIENT_CONF_ROOT, cmd.psUuid, "ceph.conf")
        if not os.path.exists(conf):
            rsp.success = False
            rsp.error = (
                "ceph client config not found on host: %s. "
                "Re-attach the primary storage to this host." % conf
            )
            return None
        return conf

    @kvmagent.replyerror
    def luks_clone(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CephLuksRsp()
        conf = self._validate_luks_cmd(cmd, rsp)
        if conf is None:
            return jsonobject.dumps(rsp)
        sec = cmd.secFilePath
        src_path = cmd.srcPath.replace("ceph://", "")
        dst_path = cmd.dstPath.replace("ceph://", "")
        try:
            if self._is_luks_rbd(src_path, conf):
                src_arg = (
                    "--image-opts driver=luks,key-secret=luks_sec,%s" % self._rbd_image_opts(src_path, conf)
                )
            else:
                src_arg = "-f raw %s" % self._rbd_uri(src_path, conf)

            shell.call(
                "/usr/bin/qemu-img convert "
                "--object secret,id=luks_sec,format=raw,file=%s "
                "-m 16 -W %s -O luks -o key-secret=luks_sec %s" % (
                    sec,
                    src_arg,
                    self._rbd_uri(dst_path, conf, "rbd_cache=false:rbd_concurrent_management_ops=20"),
                )
            )
            virtual_size = getattr(cmd, "virtualSizeForLuksClone", None)
            if virtual_size:
                dst_pool, dst_image = dst_path.split("/", 1)
                shell.call(
                    "/usr/bin/qemu-img resize "
                    "--object secret,id=luks_sec,format=raw,file=%s "
                    "--image-opts driver=luks,key-secret=luks_sec,"
                    "file.driver=rbd,file.pool=%s,file.image=%s,file.conf=%s %s" % (
                        sec, dst_pool, dst_image, conf, virtual_size,
                    )
                )
        finally:
            linux.rm_file_force(sec)

        rsp.actualSize = self._rbd_actual_size(dst_path, conf)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def luks_create_empty(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CephLuksRsp()
        conf = self._validate_luks_cmd(cmd, rsp)
        if conf is None:
            return jsonobject.dumps(rsp)
        sec = cmd.secFilePath
        install_path = cmd.installPath.replace("ceph://", "")
        try:
            shell.call(
                "/usr/bin/qemu-img create "
                "--object secret,id=luks_sec,format=raw,file=%s "
                "-f luks -o key-secret=luks_sec %s %s" % (
                    sec, self._rbd_uri(install_path, conf), cmd.size,
                )
            )
        finally:
            linux.rm_file_force(sec)
        rsp.actualSize = self._rbd_actual_size(install_path, conf)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def luks_resize(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CephLuksRsp()
        conf = self._validate_luks_cmd(cmd, rsp)
        if conf is None:
            return jsonobject.dumps(rsp)
        sec = cmd.secFilePath
        install_path = cmd.installPath.replace("ceph://", "")
        try:
            if not self._is_luks_rbd(install_path, conf):
                rsp.success = False
                rsp.error = "RBD image is not LUKS formatted: %s" % cmd.installPath
                return jsonobject.dumps(rsp)

            virtual_size = getattr(cmd, "virtualSize", None)
            pool, image = install_path.split("/", 1)
            if virtual_size:
                shell.call(
                    "/usr/bin/qemu-img resize "
                    "--object secret,id=luks_sec,format=raw,file=%s "
                    "--image-opts driver=luks,key-secret=luks_sec,"
                    "file.driver=rbd,file.pool=%s,file.image=%s,file.conf=%s %s" % (
                        sec, pool, image, conf, virtual_size,
                    )
                )
            else:
                shell.call(
                    "/usr/bin/qemu-img info "
                    "--object secret,id=luks_sec,format=raw,file=%s "
                    "--image-opts driver=luks,key-secret=luks_sec,"
                    "file.driver=rbd,file.pool=%s,file.image=%s,file.conf=%s" % (
                        sec, pool, image, conf,
                    )
                )
        finally:
            linux.rm_file_force(sec)

        rsp.actualSize = self._rbd_actual_size(install_path, conf)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def luks_encrypt_in_place(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CephLuksRsp()
        conf = self._validate_luks_cmd(cmd, rsp)
        if conf is None:
            return jsonobject.dumps(rsp)
        sec = cmd.secFilePath
        install_path = cmd.installPath.replace("ceph://", "")
        tmp_path = "%s-encrypting-%s" % (install_path, uuidlib.uuid4().hex[:8])
        old_path = "%s-plain-%s" % (install_path, uuidlib.uuid4().hex[:8])
        moved_original = False
        rbd_prefix = "rbd --conf %s" % conf
        try:
            shell.call(
                "/usr/bin/qemu-img convert "
                "--object secret,id=luks_sec,format=raw,file=%s "
                "-m 16 -W -O luks -o key-secret=luks_sec %s %s" % (
                    sec,
                    self._rbd_uri(install_path, conf),
                    self._rbd_uri(tmp_path, conf, "rbd_cache=false:rbd_concurrent_management_ops=20"),
                )
            )
            shell.call("%s mv %s %s" % (rbd_prefix, install_path, old_path))
            moved_original = True
            try:
                shell.call("%s mv %s %s" % (rbd_prefix, tmp_path, install_path))
            except Exception:
                shell.call("%s mv %s %s" % (rbd_prefix, old_path, install_path))
                moved_original = False
                raise
            shell.call("%s rm %s" % (rbd_prefix, old_path))
            moved_original = False
        finally:
            if shell.run("%s info %s" % (rbd_prefix, tmp_path)) == 0:
                shell.run("%s rm %s" % (rbd_prefix, tmp_path))
            if moved_original:
                shell.run("%s mv %s %s" % (rbd_prefix, old_path, install_path))
            linux.rm_file_force(sec)

        rsp.actualSize = self._rbd_actual_size(install_path, conf)
        return jsonobject.dumps(rsp)

    def stop(self):
        pass
        
    def configure(self, config):
        self.config = config

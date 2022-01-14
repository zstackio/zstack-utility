import zstacklib.utils.sizeunit as sizeunit

from zstacklib.utils import ceph
import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils.bash import *
import rbd

logger = log.get_logger(__name__)


class CephDriver(object):
    def __init__(self, *args, **kwargs):
        super(CephDriver, self).__init__()

    def _wrap_shareable_cmd(self, cmd, cmd_string):
        if cmd.shareable:
            return cmd_string + " --image-shared"
        return cmd_string

    def _normalize_install_path(self, path):
        return path.replace('ceph://', '')

    def _get_file_size(self, path):
        o = shell.call('rbd --format json info %s' % path)
        o = jsonobject.loads(o)
        return long(o.size_)

    def clone_volume(self, cmd, rsp):
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        shell.call('rbd clone %s %s' % (src_path, dst_path))
        return rsp

    def create_volume(self, cmd, rsp, agent=None):
        path = self._normalize_install_path(cmd.installPath)
        rsp.size = cmd.size

        if cmd.skipIfExisting and shell.run("rbd info %s" % path) == 0:
            return rsp

        if ceph.is_xsky():
            # do NOT round to MB
            call_string = 'rbd create --size %dB --image-format 2 %s' % (cmd.size, path)
            call_string = self._wrap_shareable_cmd(cmd, call_string)
            shell.call(call_string)
        else:
            pool, image = path.split('/')
            ioctx = agent.get_ioctx(pool)
            rbd_inst = rbd.RBD()
            try:
                rbd_inst.create(ioctx, image, cmd.size)
            except Exception as e:
                logger.debug("caught an exception[%s] when creating volume, try again now" % str(e))
                size_M = sizeunit.Byte.toMegaByte(cmd.size) + 1
                call_string = 'rbd create --size %s --image-format 2 %s' % (size_M, path)
                call_string = self._wrap_shareable_cmd(cmd, call_string)
                shell.call(call_string)
                rsp.size = sizeunit.MegaByte.toByte(size_M)

        return rsp

    @linux.retry(times=30, sleep_time=5)
    def do_deletion(self, cmd):
        path = self._normalize_install_path(cmd.installPath)

        shell.call('rbd rm %s' % path)

    def create_snapshot(self, cmd, rsp):
        spath = self._normalize_install_path(cmd.snapshotPath)

        o = shell.ShellCmd('rbd snap create %s' % spath)
        o(False)
        if o.return_code != 0:
            shell.run("rbd snap rm %s" % spath)
            o.raise_error()

        rsp.size = self._get_file_size(spath)
        return rsp

    def delete_snapshot(self, cmd):
        spath = self._normalize_install_path(cmd.snapshotPath)
        shell.call('rbd snap rm %s' % spath)

    def validate_token(self, cmd):
        pass

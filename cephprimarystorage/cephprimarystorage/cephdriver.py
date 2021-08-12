__author__ = 'yingzhe.hu'

import zstacklib.utils.sizeunit as sizeunit
from zstacklib.utils import ceph
from zstacklib.utils.bash import *

log.configure_log('/var/log/zstack/ceph-primarystorage.log')
logger = log.get_logger(__name__)
from cephprimarystorage import cephagent


class CephDriver(cephagent.CephAgent):
    def __init__(self, *args, **kwargs):
        super(CephDriver, self).__init__()

    def clone_volume(self, cmd, rsp):
        src_path = self._normalize_install_path(cmd.srcPath)
        dst_path = self._normalize_install_path(cmd.dstPath)

        shell.call('rbd clone %s %s' % (src_path, dst_path))
        return rsp

    def create_volume(self, cmd, rsp):
        path = self._normalize_install_path(cmd.installPath)

        if ceph.is_xsky():
            # do NOT round to MB
            call_string = 'rbd create --size %dB --image-format 2 %s' % (cmd.size, path)
            rsp.size = cmd.size
        else:
            size_M = sizeunit.Byte.toMegaByte(cmd.size) + 1
            call_string = 'rbd create --size %s --image-format 2 %s' % (size_M, path)
            rsp.size = cmd.size + sizeunit.MegaByte.toByte(1)

        call_string = self._wrap_shareable_cmd(cmd, call_string)

        skip_cmd = "rbd info %s ||" % path if cmd.skipIfExisting else ""
        shell.call(skip_cmd + call_string)
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


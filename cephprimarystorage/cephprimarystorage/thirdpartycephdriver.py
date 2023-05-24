from zstacklib.utils.bash import *
from zstacklib.utils.thirdparty_ceph import RbdDeviceOperator
import cephdriver

logger = log.get_logger(__name__)


class ThirdpartyCephDriver(cephdriver.CephDriver):
    def __init__(self, *args, **kwargs):
        super(ThirdpartyCephDriver, self).__init__()

    def clone_volume(self, cmd, rsp):
        volume_name = RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).copy_volume(cmd.srcPath, cmd.dstPath)
        rsp.installPath = volume_name
        return rsp

    def create_volume(self, cmd, rsp, agent=None):
        path = self._normalize_install_path(cmd.installPath)
        array = path.split("/")
        pool_uuid = array[0]
        image_uuid = array[1]

        rsp.size = cmd.size
        if cmd.skipIfExisting and shell.run("rbd info %s" % path) == 0:
            rsp.installPath = RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).search_volume_name(image_uuid)
            return rsp

        volume_name = RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).create_empty_volume(pool_uuid, image_uuid,
                                                                                                 cmd.size)
        rsp.installPath = volume_name
        return rsp

    @linux.retry(times=30, sleep_time=5)
    def do_deletion(self, cmd, path):
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).delete_empty_volume(path)

    def create_snapshot(self, cmd, rsp):
        spath = self._normalize_install_path(cmd.snapshotPath)
        path_name = spath.split("/")[1]
        volume_name = path_name.split("@")[0]
        snap_name = path_name.split("@")[1]

        snapshop_name = RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).create_snapshot(volume_name, snap_name)
        dpath = spath.split("@")[0] + '@' + snapshop_name
        rsp.size = self._get_file_size(dpath)
        rsp.installPath = "ceph://" + dpath
        return rsp

    def delete_snapshot(self, cmd):
        spath = self._normalize_install_path(cmd.snapshotPath)
        snap_name = spath.split("@")[1]
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).delete_snapshot(snap_name)

    def validate_token(self, cmd):
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).validate_token()


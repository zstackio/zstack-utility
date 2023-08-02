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
        image_uuid = cmd.name

        rsp.size = cmd.size
        if cmd.skipIfExisting and shell.run("rbd info %s" % path) == 0:
            rsp.installPath = RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).search_volume_name(image_uuid)
            return rsp

        created_block_volume = RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).create_empty_volume(pool_uuid,
                                                                                                          image_uuid,
                                                                                                          cmd.size,
                                                                                                          cmd.description,
                                                                                                          cmd.maxTotalBw,
                                                                                                          cmd.burstTotalIops,
                                                                                                          cmd.burstTotalBw,
                                                                                                          cmd.maxTotalIops)
        rsp.installPath = created_block_volume.volume_name
        rsp.xskyStatus = created_block_volume.status
        rsp.xskyBlockVolumeId = created_block_volume.id
        return rsp

    @linux.retry(times=30, sleep_time=5)
    def do_deletion(self, cmd, path):
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).delete_empty_volume(path)

    def create_snapshot(self, cmd, rsp):
        spath = self._normalize_install_path(cmd.snapshotPath)
        path_name = spath.split("/")[1]
        volume_name = path_name.split("@")[0]
        snapshot_name = RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).create_snapshot(volume_name, cmd.name)
        # update snapshot description
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).update_block_volume_snapshot(snapshot_name, cmd.name,
                                                                                            cmd.description)
        dpath = spath.split("@")[0] + '@' + snapshot_name
        rsp.size = self._get_file_size(dpath)
        rsp.installPath = "ceph://" + dpath
        return rsp

    def delete_snapshot(self, cmd):
        spath = self._normalize_install_path(cmd.snapshotPath)
        snap_name = spath.split("@")[1]
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).delete_snapshot(snap_name)

    def validate_token(self, cmd):
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).validate_token()

    def rollback_snapshot(self, cmd):
        spath = self._normalize_install_path(cmd.snapshotPath)
        path_name = spath.split("/")[1]
        volume_name = path_name.split("@")[0]
        snapshot_name = path_name.split("@")[1]
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).rollback_snapshot(volume_name, snapshot_name)

    def set_block_volume_qos(self, cmd, block_volume_id, burstTotalBw, burstTotalIops, maxTotalBw, maxTotalIops):
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).set_volume_qos(block_volume_id, maxTotalBw, maxTotalIops,
                                                                              burstTotalBw, burstTotalIops)

    def resize_block_volume(self, cmd, block_volume_id, size):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).resize_block_volume(block_volume_id, size)

    def update_block_volume_info(self, cmd, block_volume_id, name, description):
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).update_volume_info(block_volume_id, name, description)

    def get_block_volume_by_id(self, cmd, block_volume_id):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).get_volume_by_id(block_volume_id)

    def get_block_volume_by_name(self, cmd, block_volume_name):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).get_volume_by_name(block_volume_name)

    def get_targets_by_access_path_id(self, cmd, access_path_id):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).get_targets_by_access_path_id(access_path_id)

    def get_all_access_path(self, cmd):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).get_all_access_path()

    def update_block_volume_snapshot(self, cmd):
        spath = self._normalize_install_path(cmd.snapshotPath)
        snapshot_name = spath.split("@")[1]
        RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).update_block_volume_snapshot(snapshot_name, cmd.name,
                                                                                            cmd.description)

    def check_client_ip_exist_client_group(self, cmd, client_ip):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).check_client_ip_exist_client_group(client_ip)

    def create_client_group(self, cmd, client_ip):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).create_client_group(client_ip)

    def get_mapping_groups(self, cmd, access_path_id, client_group_id):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).get_mapping_groups(access_path_id,
                                                                                         client_group_id)

    def create_mapping_group(self, cmd, access_path_id, client_group_id, volume_name):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).create_mapping_group(access_path_id,
                                                                                           client_group_id,
                                                                                           volume_name)

    def attach_volume_to_mapping_group(self, cmd, mapping_group_id, block_volume_id):
        return RbdDeviceOperator(cmd.monIp, cmd.token, cmd.tpTimeout).attach_volume_to_mapping_group(mapping_group_id,
                                                                                                     block_volume_id)

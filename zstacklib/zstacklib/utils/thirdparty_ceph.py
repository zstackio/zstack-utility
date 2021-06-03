import time
import uuid

from func_timeout import func_set_timeout
from zstacklib.utils.xms_client import ApiClient, Configuration
from zstacklib.utils.xms_client.api import BlockVolumesApi
from zstacklib.utils.xms_client.api import AccessPathsApi
from zstacklib.utils.xms_client.api import TargetsApi
from zstacklib.utils.xms_client.api import MappingGroupsApi
from zstacklib.utils.xms_client.api import BlockSnapshotsApi
from zstacklib.utils.xms_client.api import PoolsApi
from zstacklib.utils.xms_client.api import HostsApi
from zstacklib.utils.xms_client.api import ClientGroupsApi
from zstacklib.utils.xms_client.rest import ApiException

from zstacklib.utils import shell
from zstacklib.utils import log

logger = log.get_logger(__name__)
TIME_OUT = 1800


class RbdDeviceOperator(object):
    """ A tool class to operate rbd device for xsky
    """

    def __init__(self):
        super

    def connect(self, token_list, instance_obj, volume_name, timeout):
        global TIME_OUT
        TIME_OUT = timeout * 60

        provision_ip = instance_obj.provision_ip
        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        logger.debug("############  1 provision_ip is : %s" % provision_ip)
        conf = self.prepare_token(token, host_ip)
        hosts_api = HostsApi(conf)
        targets_api = TargetsApi(conf)
        access_paths_api = AccessPathsApi(conf)
        mapping_groups_api = MappingGroupsApi(conf)
        block_volumes_api = BlockVolumesApi(conf)
        client_group_api = ClientGroupsApi(conf)
        logger.debug("############  2")

        def _connect():
            logger.debug("############  3")
            created_access_path_id = None
            created_mapping_group_id = None
            created_target_id = None
            created_client_group_id = None

            gateway_host_id = hosts_api.list_hosts(q=host_ip).hosts[0].id

            try:
                if instance_obj.customIqn:
                    logger.debug("x2 custom iqn : %s " % instance_obj.customIqn)
                    created_target_iqn = instance_obj.customIqn

                    targets = targets_api.list_targets(q=host_ip).targets
                    for tar in targets:
                        if tar.iqn == instance_obj.customIqn:
                            logger.debug("tar.iqn == custom_iqn")
                            logger.debug(tar)
                            logger.debug(instance_obj.customIqn)
                            created_access_path_id = tar.access_path.id
                    if created_access_path_id is None:
                        logger.debug("created_access_path_id is none")
                        created_client_group_id = _create_client_group(host_ip, provision_ip)
                        created_access_path_id = _create_access_path()
                        created_target = _create_target(gateway_host_id, created_access_path_id, )
                        created_target_id = created_target.id
                        created_target_iqn = created_target.iqn

                else:
                    logger.debug("x2  gateway_host_id is : %s ,  provision_ip is : %s" % (gateway_host_id, provision_ip))
                    created_client_group_id = _create_client_group(host_ip, provision_ip)
                    logger.debug("x2 has no iqn  ")
                    created_access_path_id = _create_access_path()
                    self.print_logger(host_ip, "create access path", volume_name)

                    created_target = _create_target(gateway_host_id, created_access_path_id)
                    self.print_logger(host_ip, "create target", volume_name)
                    created_target_id = created_target.id
                    created_target_iqn = created_target.iqn
                    logger.debug(
                        "x2 has no iqn  created_access_path_id:%s, created_target_id:%s, created_target_iqn:%s" %
                        (created_access_path_id, created_target_id, created_target_iqn))
                created_mapping_group_id = _create_mapping_group(created_client_group_id, created_access_path_id)
                self.print_logger(host_ip, "create mapping group ", volume_name)

            except ApiException as e:
                if created_access_path_id:
                    if created_target_id:
                        self.delete_target(token, created_target_id, gateway_host_id, created_access_path_id, host_ip)
                        self.print_logger(host_ip, "rollback create target ", volume_name)
                    if created_mapping_group_id:
                        self.delete_mapping_group(token, created_mapping_group_id, host_ip)
                        self.print_logger(host_ip, "rollback create mapping group ", volume_name)

                    if access_paths_api.get_access_path(created_access_path_id).access_path.block_volume_num == 0:
                        self.delete_access_path(token, created_access_path_id, host_ip)
                        self.print_logger(host_ip, "rollback create access path", volume_name)

                if created_client_group_id and client_group_api.get_client_group(
                        created_client_group_id).client_group.access_path_num == 0:
                    self.delete_client_group(token, created_client_group_id, host_ip)
                    self.print_logger(host_ip, "rollback create client group", volume_name)

                logger.debug(e)
                raise e

            return created_target_iqn

        def _create_client_group(gateway_ip, provision_ip):
            # get client_group code list
            client_groups = client_group_api.list_client_groups().client_groups
            for client_group in client_groups:
                codes = []
                for client in client_group.clients:
                    codes = codes + [client.code]
                if gateway_ip in codes and provision_ip in codes:
                    return client_group.id
                elif gateway_ip in codes:
                    update_client_group(client_group.id, client_group.clients, provision_ip)
                elif provision_ip in codes:
                    update_client_group(client_group.id, client_group.clients, gateway_ip)

            api_body = {"client_group": {"name": "client_group-" + instance_obj.uuid,
                                         "clients": [{"code": gateway_ip}, {"code": provision_ip}],
                                         "type": "iSCSI"}}
            created_client_group_id = client_group_api.create_client_group(api_body).client_group.id

            self._retry_until(_is_client_group_status_active, created_client_group_id)
            return created_client_group_id

        def update_client_group(client_group_id, clients, client_code):
            api_body = {"client_group": {"clients": clients + [{"code": client_code}]}}
            client_group_api.update_client_group(client_group_id, api_body)
            self._retry_until(_is_client_group_status_active, client_group_id)
            return client_group_id

        def _create_access_path():
            check_name = "access_path-" + instance_obj.uuid
            if len(access_paths_api.list_access_paths(q=check_name).access_paths) != 0:
                for i in access_paths_api.list_access_paths(q=check_name).access_paths:
                    if i.name == check_name:
                        return i.id

            api_body = {"access_path": {"name": "access_path-" + instance_obj.uuid,
                                        "type": "iSCSI"}}
            created_access_path_id = access_paths_api.create_access_path(api_body).access_path.id
            self._retry_until(_is_access_path_status_active, created_access_path_id)

            return created_access_path_id

        def _create_mapping_group(created_client_group_id, created_access_path_id):
            block_volume_id = block_volumes_api.list_block_volumes(q=volume_name).block_volumes[0].id
            api_body = {"mapping_group": {"access_path_id": created_access_path_id,
                                          "block_volume_ids": [block_volume_id],
                                          "client_group_id": created_client_group_id}}
            created_mapping_group_id = mapping_groups_api.create_mapping_group(api_body).mapping_group.id
            self._retry_until(_is_created_mapping_group_status_active, created_mapping_group_id)
            return created_mapping_group_id

        def _create_target(host_id, created_access_path_id):
            api_body = {"target": {"access_path_id": created_access_path_id,
                                   "host_id": host_id}}
            created_target = targets_api.create_target(api_body).target
            self._retry_until(_is_created_target_active, host_id, created_access_path_id)
            return created_target

        def _is_client_group_status_active(client_group_id):
            return client_group_api.get_client_group(
                client_group_id).client_group.status == "active"

        def _is_created_mapping_group_status_active(mapping_group_id):
            return mapping_groups_api.get_mapping_group(
                mapping_group_id).mapping_group.status == "active"

        def _is_access_path_status_active(created_access_path_id):
            return access_paths_api.get_access_path(
                created_access_path_id).access_path.status == "active"

        def _is_created_target_active(host_id, access_path_id):
            return targets_api.list_targets(host_id=host_id,
                                            access_path_id=access_path_id
                                            ).targets[0].status == "active"

        created_target_iqn = _connect()
        return created_target_iqn

    def disconnect(self, token_list, iqn, timeout):
        global TIME_OUT
        TIME_OUT = timeout * 60

        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        conf = self.prepare_token(token, host_ip)
        targets_api = TargetsApi(conf)
        access_paths_api = AccessPathsApi(conf)
        mapping_groups_api = MappingGroupsApi(conf)
        client_group_api = ClientGroupsApi(conf)

        def _disconnect():
            # step 1: delete target, mapping group, access path
            deleted_host_id = None
            deleted_access_path_id = None
            deleted_target_id = None
            deleted_mapping_group_id = None
            deleted_client_group_id = None

            targets = targets_api.list_targets(q=host_ip).targets
            for tar in targets:
                if tar.iqn == iqn:
                    deleted_access_path_id = tar.access_path.id
                    deleted_target_id = tar.id
                    deleted_host_id = tar.host.id

            if deleted_target_id is not None:
                self.delete_target(token, deleted_target_id, deleted_host_id, deleted_access_path_id, host_ip)
                self.print_logger(host_ip, "delete target", iqn)

            if deleted_access_path_id is not None:
                deleted_mapping_group = mapping_groups_api.list_mapping_groups(
                    access_path_id=deleted_access_path_id).mapping_groups[0]
                deleted_mapping_group_id = deleted_mapping_group.id

            if deleted_mapping_group_id is not None:
                if deleted_mapping_group.client_group:
                    deleted_client_group_id = deleted_mapping_group.client_group.id
                self.delete_mapping_group(token, deleted_mapping_group_id, host_ip)
                self.print_logger(host_ip, "delete mapping group", iqn)

            if deleted_access_path_id and access_paths_api.get_access_path(
                    deleted_access_path_id).access_path.block_volume_num == 0:
                self.delete_access_path(token, deleted_access_path_id, host_ip)
                self.print_logger(host_ip, "delete access path", iqn)

            if deleted_client_group_id is not None and client_group_api.get_client_group(
                    deleted_client_group_id).client_group.access_path_num == 0:
                self.delete_client_group(token, deleted_client_group_id, host_ip)
                self.print_logger(host_ip, "delete client group", iqn)

        _disconnect()

    def create_empty_volume(self, token_list, pool_uuid, size, timeout):
        global TIME_OUT
        TIME_OUT = timeout * 60

        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]
        logger.debug("x2 token: %s, host_ip: %s" % (token, host_ip))

        conf = self.prepare_token(token, host_ip)
        pools_api = PoolsApi(conf)
        block_volumes_api = BlockVolumesApi(conf)

        block_uuid = str(uuid.uuid4())
        pool_id = pools_api.list_pools(q=pool_uuid).pools[0].id
        api_body = {
            "block_volume": {"crc_check": False,
                             "pool_id": pool_id,
                             "name": pool_uuid + "-" + block_uuid,
                             "flattened": False,
                             "size": size}}
        created_block_volume = block_volumes_api.create_block_volume(api_body).block_volume
        created_block_volume_id = created_block_volume.id
        created_block_volume_name = created_block_volume.volume_name
        self._retry_until(self.is_block_volume_status_active, token, created_block_volume_id, host_ip)

        return created_block_volume_name

    def copy_volume(self, token, srcPath, dstPath, timeout):
        global TIME_OUT
        TIME_OUT = timeout * 60

        src_path = self._normalize_install_path(srcPath)
        dst_path = self._normalize_install_path(dstPath)
        array = src_path.split("/")
        pool_name = array[0]
        image_uuid = array[1].split('@')[0]

        token_list = token
        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        v_name = dst_path.split("/")[1]
        logger.debug("x2 token: %s, host_ip: %s" % (token, host_ip))

        conf = self.prepare_token(token, host_ip)
        pools_api = PoolsApi(conf)
        block_volumes_api = BlockVolumesApi(conf)
        block_snapshots_api = BlockSnapshotsApi(conf)

        def _copy():
            volume_name = None
            created_block_snapshot_id = None
            created_block_volume_id = None

            pool_id = pools_api.list_pools(q=pool_name).pools[0].id

            try:
                created_block_snapshot_id = _create_block_snapshot(image_uuid)
                self.print_logger(host_ip, "create block snapshot", image_uuid)

                created_block_volume = _create_block_volume(created_block_snapshot_id, pool_id, v_name)
                self.print_logger(host_ip, "create block volume", image_uuid)

                if created_block_volume:
                    created_block_volume_id = created_block_volume.id
                    volume_name = created_block_volume.volume_name

            except ApiException as e:
                if created_block_volume_id:
                    self.delete_block_volume(token, created_block_volume_id, host_ip)
                    self.print_logger(host_ip, "rollback create block volume", image_uuid)
                if created_block_snapshot_id:
                    self.delete_block_snapshot(token, created_block_snapshot_id, host_ip)
                    self.print_logger(host_ip, "rollback create block snapshot", image_uuid)
                logger.error(e)
                raise e

            return volume_name

        def _create_block_snapshot(image_uuid):
            check_name = image_uuid + "-" + token
            if len(block_snapshots_api.list_block_snapshots(q=check_name).block_snapshots) != 0:
                for i in block_snapshots_api.list_block_snapshots(q=check_name).block_snapshots:
                    if i.name == check_name:
                        return i.id

            hosting_block_volume_id = block_volumes_api.list_block_volumes(
                q=image_uuid).block_volumes[0].id

            api_body = {"block_snapshot": {"block_volume_id": hosting_block_volume_id,
                                           "name": image_uuid + "-" + token}}
            block_snapshot_id = block_snapshots_api.create_block_snapshot(api_body).block_snapshot.id
            self._retry_until(_is_block_snapshot_status_active, block_snapshot_id)

            return block_snapshot_id

        def _create_block_volume(block_snapshot_id, pool_id, volume_name):
            if len(block_volumes_api.list_block_volumes(name=volume_name).block_volumes) != 0:
                created_block_volume = block_volumes_api.list_block_volumes(name=volume_name).block_volumes[0]
                return created_block_volume

            api_body = {
                "block_volume": {"block_snapshot_id": block_snapshot_id,
                                 "pool_id": pool_id,
                                 "name": volume_name,
                                 "crc_check": False,
                                 "flattened": False,
                                 "performance_priority": 0}}
            created_block_volume = block_volumes_api.create_block_volume(api_body).block_volume
            created_block_volume_id = created_block_volume.id
            self._retry_until(_is_block_volume_status_active, created_block_volume_id)

            return created_block_volume

        def _is_block_snapshot_status_active(block_snapshot_id):
            return block_snapshots_api.get_block_snapshot(
                block_snapshot_id).block_snapshot.status == "active"

        def _is_block_volume_status_active(block_volume_id):
            return block_volumes_api.get_block_volume(
                block_volume_id).block_volume.status == "active"

        volume_name = _copy()
        return volume_name

    def delete_empty_volume(self, token, installPath, timeout):
        global TIME_OUT

        TIME_OUT = timeout * 60

        path = self._normalize_install_path(installPath)
        array = path.split("/")
        volume_uuid = array[1]

        token_list = token
        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        logger.debug("delete volume_uuid: %s" % volume_uuid)

        conf = self.prepare_token(token, host_ip)
        block_volumes_api = BlockVolumesApi(conf)
        block_volume = block_volumes_api.list_block_volumes(q=volume_uuid).block_volumes

        if len(block_volume) > 0:
            block_volume_id = block_volume[0].id
            self.delete_block_volume(token, block_volume_id, host_ip)
            self.print_logger(host_ip, "delete block volume", volume_uuid)

    def delete_target(self, token, target_id, host_id, access_path_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        targets_api = TargetsApi(conf)

        targets_api.delete_target(target_id, force=True)
        self._retry_until(self.is_block_target_status_deleted, token, host_id, access_path_id, host_ip)

    def delete_mapping_group(self, token, mapping_group_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        mapping_groups_api = MappingGroupsApi(conf)

        mapping_groups_api.delete_mapping_group(mapping_group_id, force=True)
        self._retry_until(self.is_mapping_group_status_deleted, token, mapping_group_id, host_ip)

    def delete_access_path(self, token, access_path_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        access_paths_api = AccessPathsApi(conf)

        access_paths_api.delete_access_path(access_path_id)
        self._retry_until(self.is_access_path_status_deleted, token, access_path_id, host_ip)

    def delete_client_group(self, token, client_group_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        client_group_api = ClientGroupsApi(conf)

        client_group_api.delete_client_group(client_group_id)
        self._retry_until(self.is_client_group_status_deleted, token, client_group_id, host_ip)

    def delete_block_snapshot(self, token, block_snapshot_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        block_snapshots_api = BlockSnapshotsApi(conf)

        block_snapshots_api.delete_block_snapshot(block_snapshot_id)
        self._retry_until(self.is_block_snapshot_status_deleted, token, block_snapshot_id, host_ip)

    def delete_block_volume(self, token, block_volume_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        block_volumes_api = BlockVolumesApi(conf)

        block_volumes_api.delete_block_volume(block_volume_id, bypass_trash=True)
        self._retry_until(self.is_block_volume_status_deleted, token, block_volume_id, host_ip)

    def is_block_volume_status_active(self, token, block_volume_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        block_volumes_api = BlockVolumesApi(conf)

        return block_volumes_api.get_block_volume(
            block_volume_id).block_volume.status == "active"

    def is_block_target_status_deleted(self, token, host_id, access_path_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        targets_api = TargetsApi(conf)

        return len(targets_api.list_targets(host_id=host_id,
                                        access_path_id=access_path_id
                                        ).targets) == 0

    def is_client_group_status_deleted(self, token, client_group_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        client_group_api = ClientGroupsApi(conf)

        try:
            client_group_api.get_client_group(client_group_id)
        except ApiException:
            return True
        return False

    def is_mapping_group_status_deleted(self, token, mapping_group_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        mapping_groups_api = MappingGroupsApi(conf)

        try:
            mapping_groups_api.get_mapping_group(mapping_group_id)
        except ApiException:
            return True
        return False

    def is_access_path_status_deleted(self, token, access_path_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        access_paths_api = AccessPathsApi(conf)

        try:
            access_paths_api.get_access_path(access_path_id)
        except ApiException:
            return True
        return False

    def is_block_snapshot_status_deleted(self, token, block_snapshot_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        block_snapshots_api = BlockSnapshotsApi(conf)

        try:
            block_snapshots_api.get_block_snapshot(block_snapshot_id)
        except ApiException:
            return True
        return False

    def is_block_volume_status_deleted(self, token, block_volume_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        block_volumes_api = BlockVolumesApi(conf)

        try:
            block_volumes_api.get_block_volume(block_volume_id)
        except ApiException:
            return True
        return False

    def is_third_party_ceph(self, token_object):
        if hasattr(token_object, "token"):
            return token_object.token and self.is_xdc_config_exist()
        return False

    @staticmethod
    def prepare_token(token, host_ip):
        conf = Configuration()
        conf.host = "http://" + host_ip + ":8056/v1"

        api_conf = ApiClient(conf, cookie="XMS_AUTH_TOKEN=%s" % token)
        return api_conf

    @func_set_timeout(timeout=TIME_OUT)
    def _retry_until(self, func, *args, **kwargs):
        """check api status"""
        while True:
            time.sleep(1)
            if func(*args, **kwargs):
                break

    @staticmethod
    def is_xdc_config_exist():
        return not shell.call("awk -F '=' '/^xdc_proxy_feature/{print $2;exit}' /etc/xdc/xdc.conf").strip() == "true"

    @staticmethod
    def _normalize_install_path( path):
        return path.replace('ceph://', '')

    @staticmethod
    def _get_mon_ip_token( token):
        used_ip = token.split("?")[0].split(":")[0]
        used_token = token.split("?")[1].replace('token=', '').strip()
        uesd_list = [used_ip, used_token]
        return uesd_list

    @staticmethod
    def print_logger(host_ip, action, iqn):
        logger.debug("gateway node %s %s successfully, from : %s ." % (host_ip, action, iqn))


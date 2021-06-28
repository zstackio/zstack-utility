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

from zstacklib.utils import log

logger = log.get_logger(__name__)
TIME_OUT = 1800


class RbdDeviceOperator(object):
    """ A tool class to operate rbd device for xsky
    """

    def __init__(self):
        super

    def prepare(self, instance_obj, volume_obj):
        """
        prepare client group, access path, target for volumes
        """
        token_list = volume_obj.token
        volume_uuid = volume_obj.uuid
        timeout = volume_obj.tpTimeout

        global TIME_OUT
        TIME_OUT = timeout * 60

        provision_ip = instance_obj.provision_ip
        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        logger.debug("############  1 provision_ip is : %s" % provision_ip)
        logger.debug("########## host_ip is %s:  token is : %s" % (host_ip, token))
        conf = self.prepare_token(token, host_ip)
        hosts_api = HostsApi(conf)
        targets_api = TargetsApi(conf)
        access_paths_api = AccessPathsApi(conf)
        client_group_api = ClientGroupsApi(conf)
        logger.debug("############  2")

        def _prepare():
            logger.debug("############  3")
            created_access_path_id = None
            created_target_id = None
            created_client_group_id = None

            gateway_host_id = hosts_api.list_hosts(q=host_ip).hosts[0].id

            try:
                if instance_obj.customIqn:
                    logger.debug("x2 custom iqn : %s " % instance_obj.customIqn)
                    created_target_iqn = instance_obj.customIqn

                    targets = targets_api.list_targets(q=host_ip).targets
                    for tar in targets:
                        if tar.iqn == instance_obj.customIqn and tar.access_path.id:
                            created_access_path_id = tar.access_path.id
                            created_client_group_id = _create_client_group(host_ip, provision_ip)
                            self.print_logger(host_ip, "create client_group ", volume_uuid)
                            return created_target_iqn

                        created_client_group_id = _create_client_group(host_ip, provision_ip)
                        self.print_logger(host_ip, "create client_group ", volume_uuid)
                        created_access_path_id = _create_access_path()
                        self.print_logger(host_ip, "create access_path ", volume_uuid)
                        created_target = _create_target(gateway_host_id, created_access_path_id)
                        self.print_logger(host_ip, "create target ", volume_uuid)
                        created_target_id = created_target.id
                        created_target_iqn = created_target.iqn
                        return created_target_iqn

                logger.debug("############### 4 no target ")
                created_client_group_id = _create_client_group(host_ip, provision_ip)
                self.print_logger(host_ip, "create client_group ", volume_uuid)
                created_access_path_id = _create_access_path()
                self.print_logger(host_ip, "create access_path ", volume_uuid)
                created_target = _create_target(gateway_host_id, created_access_path_id)
                self.print_logger(host_ip, "create target ", volume_uuid)
                created_target_id = created_target.id
                created_target_iqn = created_target.iqn
                return created_target_iqn

            except ApiException as e:
                if created_access_path_id and created_target_id and access_paths_api.get_access_path(
                        created_access_path_id).access_path.block_volume_num == 0:
                    self.delete_target(token, created_target_id, gateway_host_id, created_access_path_id, host_ip)
                    self.print_logger(host_ip, "rollback create target ", volume_uuid)

                    self.delete_access_path(token, created_access_path_id, host_ip)
                    self.print_logger(host_ip, "rollback create access path", volume_uuid)

                if created_client_group_id and client_group_api.get_client_group(
                        created_client_group_id).client_group.access_path_num == 0:
                    self.delete_client_group(token, created_client_group_id, host_ip)
                    self.print_logger(host_ip, "rollback create client group", volume_uuid)

                logger.debug(e)
                raise e

        def _create_client_group(gateway_ip, provision_ip):
            """
            prepare client group, access path, target for volumes
            """
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

        def _create_target(host_id, created_access_path_id):
            api_body = {"target": {"access_path_id": created_access_path_id,
                                   "host_id": host_id}}
            created_target = targets_api.create_target(api_body).target
            self._retry_until(_is_created_target_active, host_id, created_access_path_id)
            return created_target

        def _is_client_group_status_active(client_group_id):
            return client_group_api.get_client_group(
                client_group_id).client_group.status == "active"

        def _is_access_path_status_active(created_access_path_id):
            return access_paths_api.get_access_path(
                created_access_path_id).access_path.status == "active"

        def _is_created_target_active(host_id, access_path_id):
            return targets_api.list_targets(host_id=host_id,
                                            access_path_id=access_path_id
                                            ).targets[0].status == "active"

        created_iqn = _prepare()
        logger.debug("######## return iqn is %s" % created_iqn)
        return created_iqn

    def connect(self, instance_obj, volume_obj):
        """
        create mapping group to establish a connection
        """
        token_list = volume_obj.token
        volume_uuid = volume_obj.uuid
        timeout = volume_obj.tpTimeout
        provision_ip = instance_obj.provision_ip
        dst_path = self._normalize_install_path(volume_obj.path)
        volume_name = dst_path.split("/")[1]

        global TIME_OUT
        TIME_OUT = timeout * 60

        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        logger.debug("############  1 provision_ip is : %s" % provision_ip)
        conf = self.prepare_token(token, host_ip)
        access_paths_api = AccessPathsApi(conf)
        mapping_groups_api = MappingGroupsApi(conf)
        block_volumes_api = BlockVolumesApi(conf)
        client_group_api = ClientGroupsApi(conf)

        def _connect():
            created_access_path_id = None
            created_mapping_group_root_id = None
            created_mapping_group_data_id = None
            client_group_id = None

            try:
                client_groups = client_group_api.list_client_groups().client_groups
                for client_group in client_groups:
                    codes = [client.code for client in client_group.clients]
                    if host_ip in codes and provision_ip in codes:
                        client_group_id = client_group.id

                check_name = "access_path-" + instance_obj.uuid
                if len(access_paths_api.list_access_paths(q=check_name).access_paths) != 0:
                    for i in access_paths_api.list_access_paths(q=check_name).access_paths:
                        if i.name == check_name:
                            created_access_path_id = i.id

                mapping_groups = mapping_groups_api.list_mapping_groups(access_path_id=created_access_path_id,
                                                                        client_group_id=client_group_id).mapping_groups
                if len(mapping_groups) == 0:
                    created_mapping_group_root_id = _create_mapping_group(client_group_id, created_access_path_id)
                    self.print_logger(host_ip, "create mapping group ", volume_uuid)
                else:
                    _mapping_group_add_volumes(mapping_groups)

            except ApiException as e:
                if created_mapping_group_root_id:
                    self.delete_mapping_group(token, created_mapping_group_root_id, host_ip)
                    self.print_logger(host_ip, "rollback create mapping group ", volume_uuid)
                if created_mapping_group_data_id:
                    self.mapping_group_delete_volumes(token, mapping_groups, volume_name, host_ip)
                logger.debug(e)
                raise e

        def _create_mapping_group(created_client_group_id, created_access_path_id):
            block_volume_id = block_volumes_api.list_block_volumes(q=volume_name).block_volumes[0].id
            api_body = {"mapping_group": {"access_path_id": created_access_path_id,
                                          "block_volume_ids": [block_volume_id],
                                          "client_group_id": created_client_group_id}}
            created_mapping_group_id = mapping_groups_api.create_mapping_group(api_body).mapping_group.id
            self._retry_until(_is_created_mapping_group_status_active, created_mapping_group_id)
            return created_mapping_group_id

        def _mapping_group_add_volumes(mapping_groups):
            block_volume_id = block_volumes_api.list_block_volumes(q=volume_name).block_volumes[0].id
            created_mapping_group_data_id = mapping_groups[0].id
            api_body = {"block_volume_ids": [block_volume_id]}
            created_mapping_group_data_id = mapping_groups_api.add_volumes(created_mapping_group_data_id,
                                                                           api_body).mapping_group.id
            self._retry_until(_is_created_mapping_group_status_active, created_mapping_group_data_id)
            return created_mapping_group_data_id

        def _is_created_mapping_group_status_active(mapping_group_id):
            return mapping_groups_api.get_mapping_group(
                mapping_group_id).mapping_group.status == "active"

        _connect()

    def disconnect(self, instance_obj, volume_obj):
        token_list = volume_obj.token
        iqn = instance_obj.customIqn
        timeout = volume_obj.tpTimeout

        global TIME_OUT
        TIME_OUT = timeout * 60

        dst_path = self._normalize_install_path(volume_obj.path)
        volume_name = dst_path.split("/")[1]
        provision_ip = instance_obj.provision_ip
        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        conf = self.prepare_token(token, host_ip)
        targets_api = TargetsApi(conf)
        mapping_groups_api = MappingGroupsApi(conf)
        client_group_api = ClientGroupsApi(conf)

        def _disconnect():
            deleted_access_path_id = None
            deleted_mapping_group_id = None
            client_group_id = None

            targets = targets_api.list_targets(q=host_ip).targets
            for tar in targets:
                if tar.iqn == iqn:
                    deleted_access_path_id = tar.access_path.id

            client_groups = client_group_api.list_client_groups().client_groups
            for client_group in client_groups:
                codes = [client.code for client in client_group.clients]
                if host_ip in codes and provision_ip in codes:
                    client_group_id = client_group.id

            if deleted_access_path_id is not None and client_group_id is not None:
                mapping_groups = mapping_groups_api.list_mapping_groups(access_path_id=deleted_access_path_id,
                                                                        client_group_id=client_group_id).mapping_groups
                deleted_mapping_group_id = mapping_groups[0].id
                self.mapping_group_delete_volumes(token, mapping_groups, volume_name, host_ip)

            if client_group_id is not None and client_group_api.get_client_group(
                    client_group_id).client_group.block_volume_num <= 1:
                self.delete_mapping_group(token, deleted_mapping_group_id, host_ip)
                self.print_logger(host_ip, "delete mapping group", iqn)

        _disconnect()

    def destory(self, instance_obj, volume_obj):
        token_list = volume_obj.token
        iqn = instance_obj.customIqn
        timeout = volume_obj.tpTimeout

        global TIME_OUT
        TIME_OUT = timeout * 60

        provision_ip = instance_obj.provision_ip
        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        conf = self.prepare_token(token, host_ip)
        targets_api = TargetsApi(conf)
        access_paths_api = AccessPathsApi(conf)
        client_group_api = ClientGroupsApi(conf)

        def _destory():
            """
            delete target, access path， client group
            """
            deleted_host_id = None
            deleted_access_path_id = None
            deleted_target_id = None
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

            # if access path does not have volumes, delete
            if deleted_access_path_id and access_paths_api.get_access_path(
                    deleted_access_path_id).access_path.block_volume_num == 0 and access_paths_api.get_access_path(
                    deleted_access_path_id).access_path.client_group_num == 0:
                self.delete_access_path(token, deleted_access_path_id, host_ip)
                self.print_logger(host_ip, "delete access path", iqn)

            client_groups = client_group_api.list_client_groups().client_groups
            for client_group in client_groups:
                codes = [client.code for client in client_group.clients]
                if host_ip in codes and provision_ip in codes and len(codes) == 2:
                    deleted_client_group_id = client_group.id

            if deleted_client_group_id is not None and client_group_api.get_client_group(
                    deleted_client_group_id).client_group.access_path_num == 0:
                self.delete_client_group(token, deleted_client_group_id, host_ip)
                self.print_logger(host_ip, "delete client group", iqn)

        _destory()

    def create_empty_volume(self, token_list, pool_uuid, image_uuid, size, timeout):
        global TIME_OUT
        TIME_OUT = timeout * 60

        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]
        logger.debug("x2 token: %s, host_ip: %s" % (token, host_ip))

        conf = self.prepare_token(token, host_ip)
        pools_api = PoolsApi(conf)
        block_volumes_api = BlockVolumesApi(conf)

        pool_id = pools_api.list_pools(q=pool_uuid).pools[0].id
        api_body = {
            "block_volume": {"crc_check": False,
                             "pool_id": pool_id,
                             "name": image_uuid,
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
        volume_name = dst_path.split("/")[1]
        array = src_path.split("/")
        pool_name = array[0]
        image_uuid = array[1].split('@')[0]

        token_list = token
        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        logger.debug("x2 token: %s, host_ip: %s   v_name is %s" % (token, host_ip, volume_name))

        conf = self.prepare_token(token, host_ip)
        pools_api = PoolsApi(conf)
        block_volumes_api = BlockVolumesApi(conf)
        block_snapshots_api = BlockSnapshotsApi(conf)

        def _copy():
            created_volume_name = None
            created_block_snapshot_id = None
            created_block_volume_id = None
            block_snapshot_exist = False

            pool_id = pools_api.list_pools(q=pool_name).pools[0].id

            try:
                check_name = image_uuid + "-" + token
                if len(block_snapshots_api.list_block_snapshots(q=check_name).block_snapshots) != 0:
                    for i in block_snapshots_api.list_block_snapshots(q=check_name).block_snapshots:
                        if i.name == check_name:
                            created_block_snapshot_id = i.id
                            block_snapshot_exist = True
                if created_block_snapshot_id is None:
                    created_block_snapshot_id = _create_block_snapshot(image_uuid)
                    self.print_logger(host_ip, "create block snapshot", image_uuid)

                created_block_volume = _create_block_volume(created_block_snapshot_id, pool_id, volume_name)
                self.print_logger(host_ip, "create block volume", image_uuid)

                if created_block_volume:
                    created_block_volume_id = created_block_volume.id
                    created_volume_name = created_block_volume.volume_name

            except ApiException as e:
                if created_block_volume_id:
                    self.delete_block_volume(token, created_block_volume_id, host_ip)
                    self.print_logger(host_ip, "rollback create block volume", image_uuid)
                if created_block_snapshot_id and block_snapshot_exist == False:
                    self.delete_block_snapshot(token, created_block_snapshot_id, host_ip)
                    self.print_logger(host_ip, "rollback create block snapshot", image_uuid)
                logger.error(e)
                raise e

            return created_volume_name

        def _create_block_snapshot(image_uuid):
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

        created_volume_name = _copy()
        return created_volume_name

    def delete_empty_volume(self, token, installPath, timeout):
        global TIME_OUT

        TIME_OUT = timeout * 60

        path = self._normalize_install_path(installPath)
        array = path.split("/")
        volume_name = array[1]

        token_list = token
        used_list = self._get_mon_ip_token(token_list)
        host_ip = used_list[0]
        token = used_list[1]

        logger.debug("delete volume_uuid: %s" % volume_name)

        conf = self.prepare_token(token, host_ip)
        block_volumes_api = BlockVolumesApi(conf)
        block_volume = block_volumes_api.list_block_volumes(q=volume_name).block_volumes

        if len(block_volume) > 0:
            block_volume_id = block_volume[0].id
            self.delete_block_volume(token, block_volume_id, host_ip)
            self.print_logger(host_ip, "delete block volume", volume_name)

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

    def mapping_group_delete_volumes(self, token, mapping_groups, volume_name, host_ip):
        conf = self.prepare_token(token, host_ip)
        mapping_groups_api = MappingGroupsApi(conf)
        block_volumes_api = BlockVolumesApi(conf)

        block_volume_id = block_volumes_api.list_block_volumes(q=volume_name).block_volumes[0].id
        created_mapping_group_data_id = mapping_groups[0].id
        api_body = {"block_volume_ids": [block_volume_id]}
        created_mapping_group_data_id = mapping_groups_api.remove_volumes(created_mapping_group_data_id,
                                                                          api_body).mapping_group.id
        self._retry_until(self.is_created_mapping_group_status_active, token, created_mapping_group_data_id, host_ip)
        return created_mapping_group_data_id

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

    def is_created_mapping_group_status_active(self, token, mapping_group_id, host_ip):
        conf = self.prepare_token(token, host_ip)
        mapping_groups_api = MappingGroupsApi(conf)

        return mapping_groups_api.get_mapping_group(
            mapping_group_id).mapping_group.status == "active"

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

    @staticmethod
    def is_third_party_ceph(token_object):
        return hasattr(token_object, "token") and token_object.token

    @staticmethod
    def prepare_token(token, host_ip):
        conf = Configuration()
        conf.host = "http://" + host_ip + ":8056/v1"

        api_conf = ApiClient(conf, cookie="XMS_AUTH_TOKEN=%s" % token)
        return api_conf

    @func_set_timeout(timeout=TIME_OUT)
    def _retry_until(self, func, *args, **kwargs):
        """
        check api status
        """
        while True:
            time.sleep(1)
            if func(*args, **kwargs):
                break

    @staticmethod
    def _normalize_install_path(path):
        return path.replace('ceph://', '')

    @staticmethod
    def _get_mon_ip_token(token):
        used_ip = token.split("?")[0].split(":")[0]
        used_token = token.split("?")[1].replace('token=', '').strip()
        uesd_list = [used_ip, used_token]
        return uesd_list

    @staticmethod
    def print_logger(host_ip, action, iqn):
        logger.debug("gateway node %s %s successfully, from : %s ." % (host_ip, action, iqn))

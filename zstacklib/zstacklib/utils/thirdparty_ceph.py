# coding=utf-8
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
from zstacklib.utils import linux

log.configure_log('/var/log/zstack/ceph-primarystorage.log')
logger = log.get_logger(__name__)
TIME_OUT = 1800


class RbdDeviceOperator(object):
    """ A tool class to operate rbd device for xsky
    """

    def __init__(self, monIp, token, timeout):
        self.monIp = monIp
        self.token = token
        self.timeout = timeout * 60
        self.conf = self.prepare_token(self.token, self.monIp)
        self.hosts_api = HostsApi(self.conf)
        self.pools_api = PoolsApi(self.conf)
        self.targets_api = TargetsApi(self.conf)
        self.access_paths_api = AccessPathsApi(self.conf)
        self.client_group_api = ClientGroupsApi(self.conf)
        self.mapping_groups_api = MappingGroupsApi(self.conf)
        self.block_volumes_api = BlockVolumesApi(self.conf)
        self.block_snapshots_api = BlockSnapshotsApi(self.conf)

    def prepare(self, instance_obj, volume_obj, snat_ip):
        """
        prepare client group, access path, target for volumes
        """
        global TIME_OUT
        TIME_OUT = self.timeout

        dst_path = self._normalize_install_path(volume_obj.path)
        volume_name = dst_path.split("/")[1]
        logger.debug("########## host_ip is %s:  token is : %s" % (self.monIp, self.token))

        if volume_obj.type != 'Root':
            raise Exception("instance %s cannot find root volume" % instance_obj.uuid)

        def _prepare():
            created_target_id = None
            created_access_path_id = None
            created_client_group_id = None

            gateway_host = self.hosts_api.list_hosts(q=self.monIp).hosts[0]
            if not gateway_host:
                raise Exception("host %s cannot be find " % self.monIp)
            gateway_host_id = gateway_host.id

            try:
                created_client_group_id = _create_client_group()

                if instance_obj.customIqn:
                    logger.debug("x2 custom iqn : %s " % instance_obj.customIqn)
                    created_target_iqn = instance_obj.customIqn

                    targets = self.targets_api.list_targets(q=self.monIp).targets
                    for tar in targets:
                        if tar.iqn == instance_obj.customIqn and tar.access_path.id:
                            created_access_path_id = tar.access_path.id
                            return created_target_iqn

                logger.debug("############### 4 no target ")
                created_access_path_id = _create_access_path()
                created_target = _create_target(gateway_host_id, created_access_path_id)
                created_target_id = created_target.id
                created_target_iqn = created_target.iqn

                # create mapping group
                mapping_groups = self.mapping_groups_api.list_mapping_groups(access_path_id=created_access_path_id,
                                                                        client_group_id=created_client_group_id).mapping_groups
                if len(mapping_groups) == 0:
                    _create_mapping_group(created_client_group_id, created_access_path_id)

                return created_target_iqn

            except ApiException as e:
                logger.debug("start rollback prepare resource")
                if created_access_path_id and created_target_id and self.access_paths_api.get_access_path(
                        created_access_path_id).access_path.block_volume_num == 0:
                    self.delete_target(created_target_id, gateway_host_id, created_access_path_id)
                    self.delete_access_path(created_access_path_id)

                if _check_client_group_need_rollback(created_client_group_id):
                    self.delete_client_group(created_client_group_id)

                logger.debug(e)
                raise e

        def _create_mapping_group(created_client_group_id, created_access_path_id):
            block_volume = self.block_volumes_api.list_block_volumes(q=volume_name).block_volumes[0]
            if not block_volume:
                raise Exception("block volume %s cannot be find by list api" % volume_name)
            block_volume_id = block_volume.id

            api_body = {"mapping_group": {"access_path_id": created_access_path_id,
                                          "block_volume_ids": [block_volume_id],
                                          "client_group_id": created_client_group_id}}
            created_mapping_group_id = self.mapping_groups_api.create_mapping_group(api_body).mapping_group.id
            self._retry_until(_is_created_mapping_group_status_active, created_mapping_group_id)
            logger.debug("successfully create mapping group from access path[id : %s] and block volume[name : %s]" % (
                created_access_path_id, block_volume.name))
            return created_mapping_group_id

        def _create_client_group():
            """
            prepare client group, access path, target for volumes
            """
            client_name = "client_group-" + snat_ip
            client_groups = self.client_group_api.list_client_groups().client_groups

            for client_group in client_groups:
                if client_group.name == client_name and any(snat_ip == client.code for client in client_group.clients):
                    logger.debug(
                        "ccccccc client_group.id is %s, client_group.name is %s" % (client_group.id, client_group.name))
                    return client_group.id

            api_body = {"client_group": {"name": "client_group-" + snat_ip,
                                         "clients": [{"code": snat_ip}],
                                         "type": "iSCSI"}}
            created_client_group_id = self.client_group_api.create_client_group(api_body).client_group.id
            self._retry_until(_is_client_group_status_active, created_client_group_id)
            logger.debug("successfully create client group[name : client_group-%s ]" % snat_ip)
            return created_client_group_id

        def _check_client_group_need_rollback(client_group_id):
            if not client_group_id:
                return False

            client_group = self.client_group_api.get_client_group(client_group_id).client_group
            return client_group.name == "client_group-" + snat_ip and client_group.access_path_num == 0

        def _create_access_path():
            check_name = "name.raw:access_path-" + instance_obj.uuid
            access_paths = self.access_paths_api.list_access_paths(q=check_name).access_paths
            if len(access_paths) != 0 and access_paths[0].status == 'active':
                return access_paths[0].id

            api_body = {"access_path": {"name": "access_path-" + instance_obj.uuid,
                                        "type": "iSCSI"}}
            created_access_path_id = self.access_paths_api.create_access_path(api_body).access_path.id
            self._retry_until(_is_access_path_status_active, created_access_path_id)
            logger.debug("successfully create access path [access_path-%s]" % instance_obj.uuid)

            return created_access_path_id

        def _create_target(host_id, created_access_path_id):
            api_body = {"target": {"access_path_id": created_access_path_id,
                                   "host_id": host_id}}
            created_target = self.targets_api.create_target(api_body).target
            self._retry_until(_is_created_target_active, host_id, created_access_path_id)
            logger.debug("successfully create target from host[id : %s] and access path[id : %s]" % (
                host_id, created_access_path_id))
            return created_target

        def _is_created_mapping_group_status_active(mapping_group_id):
            return self.mapping_groups_api.get_mapping_group(
                mapping_group_id).mapping_group.status == "active"

        def _is_client_group_status_active(client_group_id):
            return self.client_group_api.get_client_group(
                client_group_id).client_group.status == "active"

        def _is_access_path_status_active(created_access_path_id):
            return self.access_paths_api.get_access_path(
                created_access_path_id).access_path.status == "active"

        def _is_created_target_active(host_id, access_path_id):
            return self.targets_api.list_targets(host_id=host_id,
                                            access_path_id=access_path_id
                                            ).targets[0].status == "active"

        created_iqn = _prepare()
        logger.debug("######## return iqn is %s" % created_iqn)
        return created_iqn

    def connect(self, instance_obj, volume_obj):
        """
        create mapping group to establish a connection
        """
        global TIME_OUT
        TIME_OUT = self.timeout
        provision_ip = instance_obj.provision_ip
        dst_path = self._normalize_install_path(volume_obj.path)
        volume_name = dst_path.split("/")[1]
        snat_ip = linux.find_route_interface_ip_by_destination_ip(self.monIp)

        def _connect():
            created_access_path_id = None
            created_mapping_group_root_id = None
            created_mapping_group_data_id = None
            exist_client_group_id = None
            created_client_group_id = None
            updated = False

            try:
                client_groups = self.client_group_api.list_client_groups().client_groups
                for client_group in client_groups:
                    if not client_group.name == "client_group-" + snat_ip:
                        continue
                    codes = set(client.code for client in client_group.clients)
                    if snat_ip in codes and provision_ip in codes:
                        logger.debug("ccccc snat_ip in codes and provision_ip in codes")
                        exist_client_group_id = client_group.id
                        created_client_group_id = client_group.id
                    elif provision_ip in codes:
                        logger.debug("ccccc elif provision_ip in codes")
                        _update_client_group_delete_code(created_client_group_id, provision_ip)
                    elif snat_ip in codes:
                        logger.debug("ccccc elif snat_ip in codes")
                        _update_client_group_add_code(client_group.id, client_group.clients, provision_ip)
                        created_client_group_id = client_group.id
                        updated = True
                        logger.debug("cccccc 1")

                if volume_obj.type == 'Root':
                    return

                check_name = "name.raw:access_path-" + instance_obj.uuid
                access_paths = self.access_paths_api.list_access_paths(q=check_name).access_paths
                if len(access_paths) != 0:
                    created_access_path_id = access_paths[0].id

                block_volume = self.block_volumes_api.list_block_volumes(q=volume_name).block_volumes[0]
                logger.debug("#### %s" % block_volume)
                if block_volume.access_path:
                    if block_volume.access_path.id == created_access_path_id:
                        return

                mapping_groups = self.mapping_groups_api.list_mapping_groups(access_path_id=created_access_path_id,
                                                                        client_group_id=created_client_group_id).mapping_groups
                if len(mapping_groups) < 1:
                    raise Exception("mapping group cannot be find by access path[id : %s] and client group[id : %s]" % (
                        created_access_path_id, created_client_group_id))

                created_mapping_group_data_id = _mapping_group_add_volumes(mapping_groups)
                logger.debug("cccccc connect _mapping_group_add_volumes")

            except ApiException as e:
                logger.debug("start rollback connect volume")
                if updated:
                    _update_client_group_delete_code(created_client_group_id, provision_ip)
                if created_mapping_group_root_id and not exist_client_group_id:
                    self.delete_mapping_group(created_mapping_group_root_id)
                if created_mapping_group_data_id:
                    self.mapping_group_delete_volumes(created_mapping_group_data_id, volume_name,
                                                      created_access_path_id)
                logger.debug(e)
                raise e

        def _update_client_group_add_code(client_group_id, clients, client_code):
            api_body = {"client_group": {"clients": clients + [{"code": client_code}]}}
            self.client_group_api.update_client_group(client_group_id, api_body)
            self._retry_until(_is_client_group_status_active, client_group_id)
            logger.debug(
                "successfully update client group[id :%s] to add code[code : %s]" % (client_group_id, client_code))
            return client_group_id

        def _update_client_group_delete_code(client_group_id, provision_ip):
            clients = self.client_group_api.get_client_group(client_group_id).client_group.clients
            new_clients = [client for client in clients if client.code != provision_ip]

            api_body = {"client_group": {"clients": new_clients}}
            self.client_group_api.update_client_group(client_group_id, api_body)
            self._retry_until(_is_client_group_status_active, client_group_id)
            logger.debug(
                "successfully update client group[id :%s] to delete code[code : %s]" % (client_group_id, provision_ip))
            return client_group_id

        def _mapping_group_add_volumes(mapping_groups):
            block_volume = self.block_volumes_api.list_block_volumes(q=volume_name).block_volumes[0]
            if not block_volume:
                raise Exception("block volume[name : %s] cannot be find " % volume_name)
            block_volume_id = block_volume.id

            created_mapping_group_data_id = mapping_groups[0].id
            api_body = {"block_volume_ids": [block_volume_id]}
            logger.debug("#### %s" % block_volume_id)
            created_mapping_group_data_id = self.mapping_groups_api.add_volumes(created_mapping_group_data_id,
                                                                           api_body).mapping_group.id
            self._retry_until(_is_created_mapping_group_status_active, created_mapping_group_data_id)
            logger.debug("successfully update mapping group[id :%s] to add volume[name : %s]" % (
                created_mapping_group_data_id, block_volume.name))
            return created_mapping_group_data_id

        def _is_client_group_status_active(client_group_id):
            return self.client_group_api.get_client_group(
                client_group_id).client_group.status == "active"

        def _is_created_mapping_group_status_active(mapping_group_id):
            return self.mapping_groups_api.get_mapping_group(
                mapping_group_id).mapping_group.status == "active"

        _connect()

    def disconnect(self, instance_obj, volume_obj):
        iqn = instance_obj.customIqn
        provision_ip = instance_obj.provision_ip

        global TIME_OUT
        TIME_OUT = self.timeout

        dst_path = self._normalize_install_path(volume_obj.path)
        volume_name = dst_path.split("/")[1]
        snat_ip = linux.find_route_interface_ip_by_destination_ip(self.monIp)

        def _disconnect():
            deleted_access_path_id = None
            update_client_group = None
            client_group_id = None

            targets = self.targets_api.list_targets(q=self.monIp).targets
            for tar in targets:
                if tar.iqn == iqn:
                    deleted_access_path_id = tar.access_path.id

            client_groups = self.client_group_api.list_client_groups().client_groups
            for client_group in client_groups:
                if any(snat_ip == client.code for client in client_group.clients):
                    update_client_group = client_group
                    client_group_id = client_group.id

            if not client_group_id:
                return

            if deleted_access_path_id:
                mapping_groups = self.mapping_groups_api.list_mapping_groups(access_path_id=deleted_access_path_id,
                                                                        client_group_id=client_group_id).mapping_groups
                if len(mapping_groups) < 1:
                    raise Exception("mapping group cannot be find by access path[id : %s] and client group[id : %s]" % (
                        deleted_access_path_id, client_group_id))

                deleted_mapping_group_id = mapping_groups[0].id
                logger.debug("cccccc disconnect mapping_group_delete_volumes")
                self.mapping_group_delete_volumes(deleted_mapping_group_id, volume_name, deleted_access_path_id)

            if any(provision_ip == client.code for client in update_client_group.clients):
                _update_client_group_delete_code(client_group_id, provision_ip)

        def _update_client_group_delete_code(client_group_id, provision_ip):
            clients = self.client_group_api.get_client_group(client_group_id).client_group.clients
            new_clients = [client for client in clients if client.code != provision_ip]

            api_body = {"client_group": {"clients": new_clients}}
            self.client_group_api.update_client_group(client_group_id, api_body)
            self._retry_until(_is_client_group_status_active, client_group_id)
            logger.debug(
                "successfully update client group[id :%s] to delete code[code : %s]" % (client_group_id, provision_ip))
            return client_group_id

        def _is_client_group_status_active(client_group_id):
            return self.client_group_api.get_client_group(
                client_group_id).client_group.status == "active"

        _disconnect()

    def destory(self, instance_obj):
        global TIME_OUT
        TIME_OUT = self.timeout

        iqn = instance_obj.customIqn
        snat_ip = linux.find_route_interface_ip_by_destination_ip(self.monIp)

        def _destory():
            """
            delete target, access path， client group
            """
            deleted_host_id = None
            deleted_access_path_id = None
            deleted_target_id = None
            deleted_client_group_id = None

            client_groups = self.client_group_api.list_client_groups().client_groups
            for client_group in client_groups:
                if any(snat_ip == client.code for client in client_group.clients):
                    deleted_client_group_id = client_group.id

            targets = self.targets_api.list_targets(q=self.monIp).targets
            for tar in targets:
                if tar.iqn == iqn:
                    deleted_access_path_id = tar.access_path.id
                    deleted_target_id = tar.id
                    deleted_host_id = tar.host.id

            if deleted_access_path_id and deleted_client_group_id:
                mapping_groups = self.mapping_groups_api.list_mapping_groups(access_path_id=deleted_access_path_id,
                                                                        client_group_id=deleted_client_group_id).mapping_groups
                if len(mapping_groups) < 1:
                    raise Exception("mapping group cannot be find by access path[id : %s] and client group[id : %s]" % (
                        deleted_access_path_id, deleted_client_group_id))

                deleted_mapping_group_id = mapping_groups[0].id
                self.delete_mapping_group(deleted_mapping_group_id)

            if deleted_target_id:
                self.delete_target(deleted_target_id, deleted_host_id, deleted_access_path_id)

            # if access path does not have volumes, delete
            if _check_access_path_related_resources(deleted_access_path_id):
                self.delete_access_path(deleted_access_path_id)

            if _check_client_group_related_resources(deleted_client_group_id):
                self.delete_client_group(deleted_client_group_id)

        def _check_client_group_related_resources(client_group_id):
            if not client_group_id:
                return False

            client_group = self.client_group_api.get_client_group(client_group_id).client_group
            return client_group.access_path_num == 0 and len(client_group.clients) <= 1

        def _check_access_path_related_resources(access_path_id):
            if not access_path_id:
                return False

            access_path = self.access_paths_api.get_access_path(access_path_id).access_path
            return access_path.block_volume_num == 0 and access_path.client_group_num == 0

        _destory()

    def create_empty_volume(self, pool_uuid, image_uuid, size):
        global TIME_OUT
        TIME_OUT = self.timeout

        logger.debug("x2 token: %s, host_ip: %s" % (self.token, self.monIp))

        pool = self.pools_api.list_pools(q=pool_uuid).pools[0]
        if not pool:
            raise Exception("pool[name : %s] cannot be find " % pool_uuid)
        pool_id = pool.id

        api_body = {
            "block_volume": {"crc_check": False,
                             "pool_id": pool_id,
                             "name": image_uuid,
                             "flattened": False,
                             "size": size}}
        created_block_volume = self.block_volumes_api.create_block_volume(api_body).block_volume
        created_block_volume_id = created_block_volume.id
        created_block_volume_name = created_block_volume.volume_name
        self._retry_until(self.is_block_volume_status_active, created_block_volume_id)
        return created_block_volume_name

    def copy_volume(self, srcPath, dstPath):
        global TIME_OUT
        TIME_OUT = self.timeout

        src_path = self._normalize_install_path(srcPath)
        dst_path = self._normalize_install_path(dstPath)
        volume_name = dst_path.split("/")[1]
        array = src_path.split("/")
        pool_name = array[0]
        image_uuid = array[1].split('@')[0]
        logger.debug("x2 token: %s, host_ip: %s   v_name is %s" % (self.token, self.monIp, volume_name))

        def _copy():
            created_volume_name = None
            created_block_snapshot_id = None
            created_block_volume_id = None
            block_snapshot_exist = False

            pool = self.pools_api.list_pools(q=pool_name).pools[0]
            if not pool:
                raise Exception("pool[name : %s] cannot be find " % pool_name)
            pool_id = pool.id

            try:
                snapshot_name = array[1].split('@')[1]
                if len(self.block_snapshots_api.list_block_snapshots(q=snapshot_name).block_snapshots) != 0:
                    for i in self.block_snapshots_api.list_block_snapshots(q=snapshot_name).block_snapshots:
                        if i.snap_name == snapshot_name:
                            created_block_snapshot_id = i.id
                            block_snapshot_exist = True
                if created_block_snapshot_id is None:
                    _uuid = str(uuid.uuid4()).replace('-', '')
                    snap_name = image_uuid + "-" + _uuid
                    created_block_snapshot = self.create_block_snapshot(image_uuid, snap_name)
                    created_block_snapshot_id = created_block_snapshot.id

                created_block_volume = _create_block_volume(created_block_snapshot_id, pool_id, volume_name)

                if created_block_volume:
                    created_block_volume_id = created_block_volume.id
                    created_volume_name = created_block_volume.volume_name

            except ApiException as e:
                logger.debug("start rollback copy volume")
                if created_block_volume_id:
                    self.delete_block_volume(created_block_volume_id)
                if created_block_snapshot_id and block_snapshot_exist == False:
                    self.delete_block_snapshot(created_block_snapshot_id)
                logger.error(e)
                raise e

            return created_volume_name

        def _create_block_volume(block_snapshot_id, pool_id, volume_name):
            if len(self.block_volumes_api.list_block_volumes(name=volume_name).block_volumes) != 0:
                created_block_volume = self.block_volumes_api.list_block_volumes(name=volume_name).block_volumes[0]
                if created_block_volume:
                    return created_block_volume

            api_body = {
                "block_volume": {"block_snapshot_id": block_snapshot_id,
                                 "pool_id": pool_id,
                                 "name": volume_name,
                                 "crc_check": False,
                                 "flattened": False,
                                 "performance_priority": 0}}
            created_block_volume = self.block_volumes_api.create_block_volume(api_body).block_volume
            created_block_volume_id = created_block_volume.id
            self._retry_until(_is_block_volume_status_active, created_block_volume_id)

            return created_block_volume

        def _is_block_volume_status_active(block_volume_id):
            return self.block_volumes_api.get_block_volume(
                block_volume_id).block_volume.status == "active"

        created_volume_name = _copy()
        return created_volume_name

    def delete_empty_volume(self, installPath):
        global TIME_OUT
        TIME_OUT = self.timeout

        path = self._normalize_install_path(installPath)
        array = path.split("/")
        volume_name = array[1]

        logger.debug("delete volume_uuid: %s" % volume_name)
        block_volume = self.block_volumes_api.list_block_volumes(q=volume_name).block_volumes

        if len(block_volume) > 0:
            block_volume_id = block_volume[0].id
            self.delete_block_volume(block_volume_id)

    def create_snapshot(self, image_uuid, snap_name):
        global TIME_OUT
        TIME_OUT = self.timeout
        block_snapshot = None

        try:
            block_snapshot = self.create_block_snapshot(image_uuid, snap_name)
        except ApiException as e:
            logger.debug("start rollback create snapshot [name : %s]" % image_uuid)
            if block_snapshot:
                self.delete_block_snapshot(block_snapshot.id)
            logger.error(e)
            raise e

        return block_snapshot.snap_name

    def delete_snapshot(self, image_uuid):
        global TIME_OUT
        TIME_OUT = self.timeout
        block_snapshot_id = None

        block_snapshots = self.block_snapshots_api.list_block_snapshots(q=image_uuid).block_snapshots
        if len(block_snapshots) != 0:
            for i in block_snapshots:
                if i.snap_name == image_uuid:
                    block_snapshot_id = i.id

        if block_snapshot_id is None:
            raise Exception("hosting block snapshot[name : %s] cannot be find " % image_uuid)

        self.delete_block_snapshot(block_snapshot_id)

    def create_block_snapshot(self, image_uuid, snap_name):
        hosting_block_volume = self.block_volumes_api.list_block_volumes(
            q=image_uuid).block_volumes[0]

        if not hosting_block_volume:
            raise Exception("hosting block volume[name : %s] cannot be find " % image_uuid)

        api_body = {"block_snapshot": {"block_volume_id": hosting_block_volume.id,
                                       "name": snap_name}}
        block_snapshot = self.block_snapshots_api.create_block_snapshot(api_body).block_snapshot
        block_snapshot_id = block_snapshot.id
        self._retry_until(self.is_block_snapshot_status_active, block_snapshot_id)
        logger.debug("successfully create block snapshot : %s" % block_snapshot.name)

        return block_snapshot

    def delete_target(self, target_id, host_id, access_path_id):
        self.targets_api.delete_target(target_id, force=True)
        self._retry_until(self.is_block_target_status_deleted, host_id, access_path_id)
        logger.debug("successfully delete target from host %s" % self.monIp)

    def delete_mapping_group(self, mapping_group_id):
        self.mapping_groups_api.delete_mapping_group(mapping_group_id, force=True)
        self._retry_until(self.is_mapping_group_status_deleted, mapping_group_id)
        logger.debug("successfully delete mapping group from host %s" % self.monIp)

    def mapping_group_delete_volumes(self, mapping_group_id, volume_name, access_path_id):
        deleted = True
        if len(self.block_volumes_api.list_block_volumes(q=volume_name).block_volumes) == 0:
            return

        block_volume = self.block_volumes_api.list_block_volumes(q=volume_name).block_volumes[0]
        if block_volume.access_path:
            logger.debug('####%s' % block_volume.access_path)
            if block_volume.access_path.id == access_path_id:
                deleted = False

        if deleted:
            return

        api_body = {"block_volume_ids": [block_volume.id]}
        created_mapping_group_data_id = self.mapping_groups_api.remove_volumes(mapping_group_id,
                                                                          api_body, force=True).mapping_group.id
        self._retry_until(self.is_created_mapping_group_status_active, created_mapping_group_data_id)
        logger.debug("successfully delete block volume[name : %s] from mapping group[id : %s]" % (
            block_volume.name, mapping_group_id))
        return created_mapping_group_data_id

    def delete_access_path(self, access_path_id):
        self.access_paths_api.delete_access_path(access_path_id)
        self._retry_until(self.is_access_path_status_deleted, access_path_id)
        logger.debug("successfully delete access path from host[ip : %s]" % self.monIp)

    def delete_client_group(self, client_group_id):
        self.client_group_api.delete_client_group(client_group_id)
        self._retry_until(self.is_client_group_status_deleted, client_group_id)
        logger.debug("successfully delete client group from host[ip : %s]" % self.monIp)

    def delete_block_snapshot(self, block_snapshot_id):
        self.block_snapshots_api.delete_block_snapshot(block_snapshot_id)
        self._retry_until(self.is_block_snapshot_status_deleted, block_snapshot_id)
        logger.debug("successfully delete block snapshot from host[ip : %s]" % self.monIp)

    def delete_block_volume(self, block_volume_id):
        self.block_volumes_api.delete_block_volume(block_volume_id, bypass_trash=True)
        self._retry_until(self.is_block_volume_status_deleted, block_volume_id)
        logger.debug("successfully delete block volume from host[ip : %s]" % self.monIp)

    def is_created_mapping_group_status_active(self, mapping_group_id):
        return self.mapping_groups_api.get_mapping_group(
            mapping_group_id).mapping_group.status == "active"

    def is_block_volume_status_active(self, block_volume_id):
        return self.block_volumes_api.get_block_volume(
            block_volume_id).block_volume.status == "active"

    def is_block_snapshot_status_active(self, block_snapshot_id):
        return self.block_snapshots_api.get_block_snapshot(
            block_snapshot_id).block_snapshot.status == "active"

    def is_block_target_status_deleted(self, host_id, access_path_id):
        return len(self.targets_api.list_targets(host_id=host_id,
                                            access_path_id=access_path_id
                                            ).targets) == 0

    def is_client_group_status_deleted(self, client_group_id):
        try:
            self.client_group_api.get_client_group(client_group_id)
        except ApiException:
            return True
        return False

    def is_mapping_group_status_deleted(self, mapping_group_id):
        try:
            self.mapping_groups_api.get_mapping_group(mapping_group_id)
        except ApiException:
            return True
        return False

    def is_access_path_status_deleted(self, access_path_id):
        try:
            self.access_paths_api.get_access_path(access_path_id)
        except ApiException:
            return True
        return False

    def is_block_snapshot_status_deleted(self, block_snapshot_id):
        try:
            self.block_snapshots_api.get_block_snapshot(block_snapshot_id)
        except ApiException:
            return True
        return False

    def is_block_volume_status_deleted(self, block_volume_id):
        try:
            self.block_volumes_api.get_block_volume(block_volume_id)
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

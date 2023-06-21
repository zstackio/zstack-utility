# -*- coding:UTF-8 -*-
from zstacklib.utils.thirdparty_ceph import RbdDeviceOperator

# 创建 RbdDeviceOperator 类实例
operator = RbdDeviceOperator('172.25.13.208', 'bf6b3616f1cb422ca4fabb8d6485f956', timeout=10)

# 调用 create_volume 方法创建卷
pool_uuid = 'pool-301a905df3a445e99a85d6fce2a1ee2f'
image_uuid = 'imageName'
size = 1024  # 单位为 MiB
bm_ip = "172.25.12.97"

gateway_host = operator.hosts_api.list_hosts(q=operator.monIp).hosts[0]
if not gateway_host:
    print("host %s cannot be find", operator.monIp)
    exit(1)
gateway_host_id = gateway_host.id
print("gateway_host_id is :", gateway_host_id)

# 创建空盘
create_volume_name = operator.create_empty_volume(pool_uuid, image_uuid, size)
print('volume mane is:', create_volume_name)
#
block_volume = operator.block_volumes_api.list_block_volumes(q=create_volume_name).block_volumes[0]
if not block_volume:
    print("Block volume %s cannot be find by list api" % create_volume_name)
    exit(1)
block_volume_id = block_volume.id
print("block_volume_id is", block_volume_id)

# 客户创建访问路径
created_access_path_id = operator.create_access_path(bm_ip)
print("created_access_path_id is :", created_access_path_id)

# 客户挂载网关节点
created_target = operator.create_target(gateway_host_id, created_access_path_id)
created_target_id = created_target.id
created_target_iqn = created_target.iqn
print("created_target_id is :", created_target.id)
print("created_target_iqn is :", created_target.iqn)

# 创建客户端组，并绑定客户端IP（裸金属实例Ip）
client_group_id = operator.check_client_ip_exist_client_group(bm_ip)
print("client_group_id is :", client_group_id)
if not client_group_id:
    client_group_id = operator.create_client_group(bm_ip)
    print("created_client_group_id is :", client_group_id)

# 判断对应的访问路径和客户端组的映射是否存在，不存在映射则创建映射，反之则把盘加到对应映射里面。
mapping_groups = operator.mapping_groups_api.list_mapping_groups(access_path_id=created_access_path_id,
                                                                 client_group_id=client_group_id).mapping_groups
if len(mapping_groups) == 0:
    operator.create_mapping_group(client_group_id, created_access_path_id, create_volume_name)
    print("create_mapping_group successful")
    exit(0)

print("successful create volume !!!!!!!!")


mapping_groups = operator.mapping_groups_api.list_mapping_groups(access_path_id=5,client_group_id=5).mapping_groups
print("mapping_groups[0] is", mapping_groups[0].id)
# 删除访问路径中盘和客户端组的映射, 删除后, 平台上需要等待三分钟删除操作才会执行结束。
exist_mapping_group_id = operator.remove_volumes_from_mapping_group(mapping_groups[0].id, [block_volume_id])
print("exist_mapping_group_id is :", exist_mapping_group_id)

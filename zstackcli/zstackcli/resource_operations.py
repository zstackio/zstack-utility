'''
 resource API wrapper

@author: Youyk
'''

import os
import sys
import traceback
import time

import apibinding.api_actions as api_actions
import apibinding.inventory as inventory
import account_operations

#Define default get resource method. default is using searchAPI, it can also be ListAPI.
SEARCH_RESOURCE_METHOD = 'search'
LIST_RESOURCE_METHOD = 'list'
GET_RESOURCE_METHOD_BY_GET = 'get'
#GET_RESOURCE_METHOD = SEARCH_RESOURCE_METHOD
GET_RESOURCE_METHOD = LIST_RESOURCE_METHOD

BACKUP_STORAGE = 'BackupStorage'
SFTP_BACKUP_STORAGE = 'SftpBackupStorage'
ZONE = 'Zone'
CLUSTER = 'Cluster'
PRIMARY_STORAGE = 'PrimaryStorage'
L2_NETWORK = 'L2Network'
L2_VLAN_NETWORK = 'L2VlanNetwork'
L3_NETWORK = 'L3Network'
INSTANCE_OFFERING = 'InstanceOffering'
IMAGE = 'Image'
VOLUME = 'Volume'
VM_INSTANCE = 'VmInstance'
IP_RANGE = 'IpRange'
HOST = 'Host'
NETWORK_SERVICE_PROVIDER = 'NetworkServiceProvider'
NETWORK_SERVICE_PROVIDER_L3_REF = 'NetworkServiceProviderL3Ref'
APPLIANCE_VM = 'ApplianceVm'
DISK_OFFERING = 'DiskOffering'
ACCOUNT = 'Account'
PRIMARY_STORAGE = 'PrimaryStorage'
SECURITY_GROUP = 'SecurityGroup'
SECURITY_GROUP_RULE = 'SecurityGroupRule'
VM_SECURITY_GROUP = 'VmSecurityGroup'
VM_NIC = 'VmNic'
PORT_FORWARDING = 'PortForwarding'
MANAGEMENT_NODE = 'ManagementNode'
EIP = 'Eip'
VIP = 'Vip'
IP_CAPACITY = 'IpCapacity'
VR_OFFERING = 'VirtualRouterOffering'
SYSTEM_TAG = 'SystemTag'
USER_TAG = 'UserTag'
VOLUME_SNAPSHOT_TREE = 'VolumeSnapshotTree'
VOLUME_SNAPSHOT = 'VolumeSnapshot'

def find_item_by_uuid(inventories, uuid):
    for item in inventories:
        if item.uuid == uuid:
            #test_util.test_logger("Item found by UUID: %s" % uuid)
            return [item]
    #test_util.test_logger("Not found item with UUID: %s" % uuid)
    return None

def find_item_by_name(inventories, name):
    for item in inventories:
        if item.name == name:
            #test_util.test_logger("Item found by name: %s" % name)
            return [item]
    #test_util.test_logger("Not found item with name: %s" % name)
    return None

#Using List API
def list_resource(resource, session_uuid=None, uuid=None, name=None):
    '''
        Return: list by list API.
    '''
    if resource == BACKUP_STORAGE:
        action = api_actions.ListBackupStorageAction()
    elif resource == ZONE:
        action = api_actions.ListZonesAction()
    elif resource == PRIMARY_STORAGE:
        action = api_actions.ListPrimaryStorageAction()
    elif resource == L2_NETWORK:
        action = api_actions.ListL2NetworkAction()
    elif resource == L2_VLAN_NETWORK:
        action = api_actions.ListL2VlanNetworkAction()
    elif resource == CLUSTER:
        action = api_actions.ListClusterAction()
    elif resource == L3_NETWORK:
        action = api_actions.ListL3NetworkAction()
    elif resource == INSTANCE_OFFERING:
        action = api_actions.ListInstanceOfferingAction()
    elif resource == IMAGE:
        action = api_actions.ListImageAction()
    elif resource == VOLUME:
        action = api_actions.ListVolumeAction()
    elif resource == VM_INSTANCE:
        action = api_actions.ListVmInstanceAction()
    elif resource == IP_RANGE:
        action = api_actions.ListIpRangeAction()
    elif resource == HOST:
        action = api_actions.ListHostAction()
    elif resource == NETWORK_SERVICE_PROVIDER:
        action = api_actions.ListNetworkServiceProviderAction()
    elif resource == APPLIANCE_VM:
        action = api_actions.ListApplianceVmAction()
    elif resource == DISK_OFFERING:
        action = api_actions.ListDiskOfferingAction()
    elif resource == ACCOUNT:
        action = api_actions.ListAccountAction()
    elif resource == PRIMARY_STORAGE:
        action = api_actions.ListPrimaryStorageAction()
    elif resource == SECURITY_GROUP:
        action = api_actions.ListSecurityGroupAction()
    elif resource == VM_SECURITY_GROUP:
        action = api_actions.ListVmNicInSecurityGroupAction()
    elif resource == VM_NIC:
        action = api_actions.ListVmNicAction()
    elif resource == PORT_FORWARDING:
        action = api_actions.ListPortForwardingRuleAction()
    elif resource == MANAGEMENT_NODE:
        action = api_actions.ListManagementNodeAction()

    ret = account_operations.execute_action_with_session(action, session_uuid)

    if uuid:
        return find_item_by_uuid(ret, uuid)

    if name:
        return find_item_by_name(ret, name)

    return ret

#Using Search API
def search_resource(resource, session_uuid, uuid=None, name=None):
    '''
        Return: list by search
        This API was depricated. 
    '''
    if resource == BACKUP_STORAGE:
        action = api_actions.SearchBackupStorageAction()
    elif resource == ZONE:
        action = api_actions.SearchZoneAction()
    elif resource == PRIMARY_STORAGE:
        action = api_actions.SearchPrimaryStorageAction()
    elif resource == L2_NETWORK:
        action = api_actions.SearchL2NetworkAction()
    elif resource == L2_VLAN_NETWORK:
        action = api_actions.SearchL2VlanNetworkAction()
    elif resource == CLUSTER:
        action = api_actions.SearchClusterAction()
    elif resource == L3_NETWORK:
        action = api_actions.SearchL3NetworkAction()
    elif resource == INSTANCE_OFFERING:
        action = api_actions.SearchInstanceOfferingAction()
    elif resource == IMAGE:
        action = api_actions.SearchImageAction()
    elif resource == VOLUME:
        action = api_actions.SearchVolumeAction()
    elif resource == VM_INSTANCE:
        action = api_actions.SearchVmInstanceAction()
    elif resource == IP_RANGE:
        action = api_actions.SearchIpRangeAction()
    elif resource == HOST:
        action = api_actions.SearchHostAction()
    elif resource == NETWORK_SERVICE_PROVIDER:
        action = api_actions.SearchNetworkServiceProviderAction()
    elif resource == APPLIANCE_VM:
        action = api_actions.SearchApplianceVmAction()
    elif resource == DISK_OFFERING:
        action = api_actions.SearchDiskOfferingAction()
    elif resource == ACCOUNT:
        action = api_actions.SearchAccountAction()
    elif resource == PRIMARY_STORAGE:
        action = api_actions.SearchPrimaryStorageAction()
    #elif resource == SECURITY_GROUP:
    #    action = api_actions.SearchSecurityGroupAction()
    #elif resource == VM_SECURITY_GROUP:
    #    action = api_actions.SearchVmNicInSecurityGroupAction()

    action.sessionUuid = session_uuid
    action.nameOpValueTriples = []

    if uuid:
        t = inventory.NOVTriple()
        t.name = 'uuid'
        t.op = inventory.AND_EQ
        t.val = uuid
        action.nameOpValueTriples.append(t)

    if name:
        t = inventory.NOVTriple()
        t.name = 'name'
        t.op = inventory.AND_EQ
        t.val = name
        action.nameOpValueTriples.append(t)

    # the time delay is because of elastic search iventory will delay 0.5s after original data was created in database.
    time.sleep(0.3)
    ret = action.run()
    return ret

def get_resource_by_get(resource, session_uuid, uuid):
    '''
        Return a list by get API.
    '''
    if resource == BACKUP_STORAGE:
        action = api_actions.GetBackupStorageAction()
    elif resource == ZONE:
        action = api_actions.GetZoneAction()
    elif resource == PRIMARY_STORAGE:
        action = api_actions.GetPrimaryStorageAction()
    elif resource == L2_NETWORK:
        action = api_actions.GetL2NetworkAction()
    elif resource == L2_VLAN_NETWORK:
        action = api_actions.GetL2VlanNetworkAction()
    elif resource == CLUSTER:
        action = api_actions.GetClusterAction()
    elif resource == L3_NETWORK:
        action = api_actions.GetL3NetworkAction()
    elif resource == INSTANCE_OFFERING:
        action = api_actions.GetInstanceOfferingAction()
    elif resource == IMAGE:
        action = api_actions.GetImageAction()
    elif resource == VOLUME:
        action = api_actions.GetVolumeAction()
    elif resource == VM_INSTANCE:
        action = api_actions.GetVmInstanceAction()
    elif resource == IP_RANGE:
        action = api_actions.GetIpRangeAction()
    elif resource == HOST:
        action = api_actions.GetHostAction()
    elif resource == NETWORK_SERVICE_PROVIDER:
        action = api_actions.GetNetworkServiceProviderAction()
    elif resource == APPLIANCE_VM:
        action = api_actions.GetApplianceVmAction()
    elif resource == DISK_OFFERING:
        action = api_actions.GetDiskOfferingAction()
    elif resource == ACCOUNT:
        action = api_actions.GetAccountAction()
    elif resource == PRIMARY_STORAGE:
        action = api_actions.GetPrimaryStorageAction()
    elif resource == VR_OFFERING:
        action = api_actions.GetVirtualRouterOfferingAction()
    #elif resource == SECURITY_GROUP:
    #    action = api_actions.GetSecurityGroupAction()
    #elif resource == VM_SECURITY_GROUP:
    #    action = api_actions.GetVmNicInSecurityGroupAction()

    action.uuid = uuid

    ret = account_operations.execute_action_with_session(action, session_uuid)

    return ret

def gen_query_conditions(name, op, value, conditions=[]):
    new_conditions = [{'name': name, 'op': op, 'value': value}]
    new_conditions.extend(conditions)
    return new_conditions

def _gen_query_action(resource):
    if resource == BACKUP_STORAGE:
        action = api_actions.QueryBackupStorageAction()
    elif resource == SFTP_BACKUP_STORAGE:
        action = api_actions.QuerySftpBackupStorageAction()
    elif resource == ZONE:
        action = api_actions.QueryZoneAction()
    elif resource == PRIMARY_STORAGE:
        action = api_actions.QueryPrimaryStorageAction()
    elif resource == L2_NETWORK:
        action = api_actions.QueryL2NetworkAction()
    elif resource == L2_VLAN_NETWORK:
        action = api_actions.QueryL2VlanNetworkAction()
    elif resource == CLUSTER:
        action = api_actions.QueryClusterAction()
    elif resource == L3_NETWORK:
        action = api_actions.QueryL3NetworkAction()
    elif resource == INSTANCE_OFFERING:
        action = api_actions.QueryInstanceOfferingAction()
    elif resource == IMAGE:
        action = api_actions.QueryImageAction()
    elif resource == VOLUME:
        action = api_actions.QueryVolumeAction()
    elif resource == VM_INSTANCE:
        action = api_actions.QueryVmInstanceAction()
    elif resource == IP_RANGE:
        action = api_actions.QueryIpRangeAction()
    elif resource == HOST:
        action = api_actions.QueryHostAction()
    elif resource == NETWORK_SERVICE_PROVIDER:
        action = api_actions.QueryNetworkServiceProviderAction()
    elif resource == NETWORK_SERVICE_PROVIDER_L3_REF:
        action = api_actions.QueryNetworkServiceL3NetworkRefAction()
    elif resource == APPLIANCE_VM:
        action = api_actions.QueryApplianceVmAction()
    elif resource == DISK_OFFERING:
        action = api_actions.QueryDiskOfferingAction()
    elif resource == ACCOUNT:
        action = api_actions.QueryAccountAction()
    elif resource == PRIMARY_STORAGE:
        action = api_actions.QueryPrimaryStorageAction()
    elif resource == SECURITY_GROUP:
        action = api_actions.QuerySecurityGroupAction()
    elif resource == SECURITY_GROUP_RULE:
        action = api_actions.QuerySecurityGroupRuleAction()
    elif resource == VM_SECURITY_GROUP:
        action = api_actions.QueryVmNicInSecurityGroupAction()
    elif resource == VM_NIC:
        action = api_actions.QueryVmNicAction()
    elif resource == PORT_FORWARDING:
        action = api_actions.QueryPortForwardingRuleAction()
    elif resource == MANAGEMENT_NODE:
        action = api_actions.QueryManagementNodeAction()
    elif resource == EIP:
        action = api_actions.QueryEipAction()
    elif resource == VIP:
        action = api_actions.QueryVipAction()
    elif resource == VR_OFFERING:
        action = api_actions.QueryVirtualRouterOfferingAction()
    elif resource == SYSTEM_TAG:
        action = api_actions.QuerySystemTagAction()
    elif resource == USER_TAG:
        action = api_actions.QueryUserTagAction()
    elif resource == VOLUME_SNAPSHOT_TREE:
        action = api_actions.QueryVolumeSnapshotTreeAction()
    elif resource == VOLUME_SNAPSHOT:
        action = api_actions.QueryVolumeSnapshotAction()

    return action

def query_resource(resource, conditions = [], session_uuid=None, count='false'):
    '''
    Call Query API and return all matched resource.

    conditions could be generated by gen_query_conditions()

    If session_uuid is missing, we will create one for you and only live in 
        this API.
    '''
    action = _gen_query_action(resource)
    action.conditions = conditions
    ret = account_operations.execute_action_with_session(action, session_uuid)
    return ret

def query_resource_count(resource, conditions = [], session_uuid=None):
    '''
    Call Query API to return the matched resource count
    When count=true, it will only return the number of matched resource
    '''
    action = _gen_query_action(resource)
    action.conditions = conditions
    action.count='true'
    account_operations.execute_action_with_session(action, session_uuid)
    return action.reply.total

def query_resource_with_num(resource, conditions = [], session_uuid=None, \
        start=0, limit=1000):
    '''
    Query matched resource and return required numbers. 
    '''
    action = _gen_query_action(resource)
    action.conditions = conditions
    action.start = start
    action.limit = limit
    ret = account_operations.execute_action_with_session(action, session_uuid)
    return ret

def query_resource_fields(resource, conditions = [], session_uuid=None, \
        fields=[], start=0, limit=1000):
    '''
    Query matched resource by returning required fields and required numbers. 
    '''
    action = _gen_query_action(resource)
    action.conditions = conditions
    action.start = start
    action.limit = limit
    action.fields = fields
    ret = account_operations.execute_action_with_session(action, session_uuid)
    return ret

def get_resource(resource, session_uuid=None, uuid=None, name=None):
    if uuid:
        cond = gen_query_conditions('uuid', '=', uuid)
    elif name:
        cond = gen_query_conditions('name', '=', name)
    else:
        cond = gen_query_conditions('uuid', '!=', 'NULL')

    return query_resource(resource, cond, session_uuid)

    #if GET_RESOURCE_METHOD == LIST_RESOURCE_METHOD:
    #    return list_resource(resource, session_uuid, uuid=uuid, name=name)
    #elif GET_RESOURCE_METHOD == GET_RESOURCE_METHOD_BY_GET:
    #    if not uuid:
    #        raise Exception('Get_Resource function error, uuid can not be None')
    #    return get_resource_by_get(resource, session_uuid, uuid=uuid)
    #else:
    #    return search_resource(resource, session_uuid, uuid=uuid, name=name)

def safely_get_resource(res_name, cond = [], session_uuid = None, \
        fields = None, limit = 100):
    res_count = query_resource_count(res_name, cond, session_uuid)
    res_list = []
    if res_count <= limit:
        res_list = query_resource_fields(res_name, cond, session_uuid, fields)
    else:
        curr_count = 0 
        while curr_count <= res_count:
            curr_list = query_resource_with_num(res_name, cond, \
                    session_uuid, fields, start=current_count, limit = limit)
            res_list.extend(curr_list)
            curr_count += limit

    return res_list


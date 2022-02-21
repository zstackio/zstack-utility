'''
Based on ZStack sdk by @author: SyZhao

To list all VMs' disk usage, including all volumes and snapshots.
Only fit for local storage. 
@author: yyk

This sdk provides a prototype to invoke zstack sdk.

Usage:
    1. Install ZStack Enterprise.
    2. Execute CLI to go to zstackcli mode: 
        source /var/lib/zstack/virtualenv/zstackcli/bin/activate
    3. Run the demo script to create a zone in zstack.
        python ./zs_api_sdk.py

The python sdk interfaces are wrapped inside zs_api_sdk.py, 
user can refer to the script to customize their own expected scripts.
'''

import time
import os
import sys
import traceback
import hashlib

import zstacklib.utils.log as log

# comment out next line to print detail zstack cli http command to screen.
log.configure_log('/var/log/zstack/zstack-sdk.log', log_to_console=False)

import apibinding.api_actions as api_actions
from apibinding import api
import xml.etree.cElementTree as etree
import apibinding.inventory as inventory

zstack_server_ip = os.environ['ZS_SERVER_IP']
user_name = 'admin'
user_password = 'password'
# provide host uuid, will list all VMs' disk usage and acutal size.
host_uuid = 'e9e245b5089b4d9cb5c20bfd0da370fa'


# Must keep.
def sync_call(apiCmd, session_uuid):
    api_instance = api.Api(host=zstack_server_ip, port='8080')
    if session_uuid:
        api_instance.set_session_to_api_message(apiCmd, session_uuid)
    (name, reply) = api_instance.sync_call(apiCmd, )
    if not reply.success: raise api.ApiError("Sync call at %s: [%s] meets error: %s." % (
        zstack_server_ip, apiCmd.__class__.__name__, api.error_code_to_string(reply.error)))
    # print("[Sync call at %s]: [%s] Success" % (zstack_server_ip, apiCmd.__class__.__name__))
    return reply


# Must keep.
def async_call(apiCmd, session_uuid):
    api_instance = api.Api(host=zstack_server_ip, port='8080')
    api_instance.set_session_to_api_message(apiCmd, session_uuid)
    (name, event) = api_instance.async_call_wait_for_complete(apiCmd)
    time.sleep(1)
    if not event.success: raise api.ApiError("Async call at %s: [%s] meets error: %s." % (
        zstack_server_ip, apiCmd.__class__.__name__, api.error_code_to_string(reply.error)))
    # print("[Async call at %s]: [%s] Success" % (zstack_server_ip, apiCmd.__class__.__name__))
    return event


# Must keep.
def login_as_admin():
    accountName = user_name
    password = user_password
    return login_by_account(accountName, password)


# Must keep.
#tag::login_by_account[]
def login_by_account(name, password, timeout=60000):
    login = api_actions.LogInByAccountAction()
    login.accountName = name
    # Login API will use encrypted password string.
    login.password = hashlib.sha512(password).hexdigest()
    login.timeout = timeout
    session_uuid = async_call(login, None).inventory.uuid
    return session_uuid
#end::login_by_account[]


# logout must be called after session isn't needed.
# Must keep.
#tag::logout[]
def logout(session_uuid):
    logout = api_actions.LogOutAction()
    logout.timeout = 60000
    logout.sessionUuid = session_uuid
    async_call(logout, session_uuid)
#end::logout[]


# Must keep.
def execute_action_with_session(action, session_uuid, async=True):
    if session_uuid:
        action.sessionUuid = session_uuid
        if async:
            evt = async_call(action, session_uuid)
        else:
            evt = sync_call(action, session_uuid)
    else:
        session_uuid = login_as_admin()
        try:
            action.sessionUuid = session_uuid
            if async:
                evt = async_call(action, session_uuid)
            else:
                evt = sync_call(action, session_uuid)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            raise e
        finally:
            # New login must be logout. If the active login session
            # exceed the limit, no account login is allowed.
            # The default active logined session limit is  500.
            logout(session_uuid)

    return evt


# All actions are defined in api_actions.
def create_zone(session_uuid=None):
    action = api_actions.CreateZoneAction()
    action.timeout = 30000
    action.name = "zone_test"
    action.description = "This is zone for testing"
    evt = execute_action_with_session(action, session_uuid)
    print 'Add Zone [uuid:] %s [name:] %s' % (evt.inventory.uuid, action.name)
    # The execution result might be signle item, like inventory.
    # Or the execution result might be a list, like inventories(e.g. Query API).
    return evt.inventory


# All Query API need conditions. This help to generate common conditions.
# The op including: =, >, <, in, not in, like etc.
def gen_query_conditions(name, op, value, conditions=[]):
    new_conditions = [{'name': name, 'op': op, 'value': value}]
    new_conditions.extend(conditions)
    return new_conditions

#tag::query_zone[]
def query_zone(conditions=[], session_uuid=None):
    action = api_actions.QueryZoneAction()
    action.timeout = 3000
    action.conditions = conditions
    evt = execute_action_with_session(action, session_uuid)
    print 'Zone infomation: %s ' % evt.inventories
    return evt.inventories
#end::query_zone[]


# All query APIs need conditions.
def get_host(conditions=[], session_uuid=None):
    action = api_actions.QueryHostAction()
    action.conditions = conditions
    evt = execute_action_with_session(action, session_uuid)
    return evt.inventories


def query_vm_by_host(host_uuid, conditions=[], session_uuid=None):
    action = api_actions.QueryVmInstanceAction()
    action.conditions = gen_query_conditions('hostUuid', '=', host_uuid, conditions)
    evt = execute_action_with_session(action, session_uuid)
    return evt.inventories


def query_vm_by_last_host(host_uuid, conditions=[], session_uuid=None):
    action = api_actions.QueryVmInstanceAction()
    action.conditions = gen_query_conditions('lastHostUuid', '=', host_uuid, conditions)
    evt = execute_action_with_session(action, session_uuid)
    return evt.inventories


def get_vm_volume(vm_uuid, session_uuid=None):
    action = api_actions.QueryVolumeAction()
    action.conditions = gen_query_conditions('vmInstanceUuid', '=', vm_uuid)
    evt = execute_action_with_session(action, session_uuid)
    return evt.inventories


def get_volume_snapshot(volume_uuid, session_uuid=None):
    action = api_actions.QueryVolumeSnapshotAction()
    action.conditions = gen_query_conditions('volumeUuid', '=', volume_uuid)
    evt = execute_action_with_session(action, session_uuid)
    return evt.inventories


def get_snapshot_list_by_host(host_uuid, session_uuid=None):
    action = api_actions.QueryVolumeSnapshotAction()
    action.conditions = gen_query_conditions('volume.localStorageHostRef.hostUuid', '=', host_uuid)
    evt = execute_action_with_session(action, session_uuid)
    return evt.inventories


def get_volume_snapshot_size(volume_uuid, session_uuid=None):
    sp_list = get_volume_snapshot(volume_uuid, session_uuid)
    sp_size = 0
    for sp in sp_list:
        sp_size = sp.size + sp_size

    return sp_size


def sync_volume_size(volume_uuid, session_uuid=None):
    action = api_actions.SyncVolumeSizeAction()
    action.uuid = volume_uuid
    try:
        evt = execute_action_with_session(action, session_uuid)
    except:
        print "volume sync error: %s!!!" % volume_uuid
        print "volume sync error: %s!!!" % volume_uuid
        print "volume sync error: %s!!!" % volume_uuid

    return evt.inventory


# The quick calculation only use few ZStack API.
# If the query result are huge, this way will cause query API fail.
# VM disk space = The sum of all vm volumes size and vm volume snapshots size
# VM disk actual size = The sum of all vm volumes action size
# ZStack primary storage availabe capacity is related with VM disk space.
def get_vm_disk_usage(vm, sp_list):
    vm_disk_size = 0
    vm_disk_actual_size = 0
    for volume in vm.allVolumes:
        # volume action size might need resync. This is costing.
        # volume = sync_volume_size(volume.uuid, session_uuid)
        vm_disk_size += volume.size
        vm_disk_actual_size += volume.actualSize
        for sp in sp_list:
            if sp.volumeUuid == volume.uuid:
                vm_disk_size += sp.size

    return vm_disk_size, vm_disk_actual_size


def list_top_vm_disk_usage(host_uuid, session_uuid):
    vm_disk_usage_dict = {}
    vm_disk_usage_dict_reverse = {}
    vm_disk_usage_asc_list = []
    vm_disk_actual_size_dict = {}
    vm_list = query_vm_by_host(host_uuid, session_uuid=session_uuid)
    stopped_vm_conditions = gen_query_conditions('state', '=', 'Stopped')
    vm_list.extend(query_vm_by_last_host(host_uuid, stopped_vm_conditions,
                                         session_uuid=session_uuid))
    sp_list = get_snapshot_list_by_host(host_uuid, session_uuid=session_uuid)

    for vm in vm_list:
        vm_disk_usage_dict[vm] = get_vm_disk_usage(vm, sp_list)

    for vm, size in vm_disk_usage_dict.iteritems():
        if size[0] in vm_disk_usage_asc_list:
            size2 = size[0] + 1
            while size2 in vm_disk_usage_asc_list:
                size2 += 1
        else:
            size2 = size[0]
        vm_disk_usage_asc_list.append(size2)
        vm_disk_usage_dict_reverse[size2] = vm
        vm_disk_actual_size_dict[size2] = size[1]

    vm_disk_usage_asc_list.sort(reverse=True)
    print '\n\nHost: %s disk usage:' % host_uuid
    print '-' * 80
    print 'Size\t| Actual Size\t| VM:'
    for size in vm_disk_usage_asc_list:
        vm = vm_disk_usage_dict_reverse[size]
        print '%dGB\t| %dGB\t\t| %s:%s' % (size / 1024 / 1024 / 1024,
                                           vm_disk_actual_size_dict[size] / 1024 / 1024 / 1024,
                                           vm.name, vm.uuid)


if __name__ == '__main__':
    session_uuid = login_as_admin()
    list_top_vm_disk_usage(host_uuid, session_uuid)
    logout(session_uuid)

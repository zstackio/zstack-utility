from kvmagent.test.utils import pytest_utils
from zstacklib.test.utils import env, misc
from zstacklib.utils import jsonobject, xmlobject, bash, linux
from kvmagent.plugins.ha_plugin import HaPlugin
from kvmagent.test.utils import vm_utils, network_utils, volume_utils, pytest_utils

HA_PLUGIN = None  # type:HaPlugin


def init_ha_plugin():
    global HA_PLUGIN
    if HA_PLUGIN is not None:
        return HA_PLUGIN

    HA_PLUGIN = HaPlugin()
    return HA_PLUGIN


@misc.return_jsonobject()
def file_system_check_vmstate(interval, times, primaryStorageUuid, targetHostUuid, storageCheckerTimeout, mountPath):
    return HA_PLUGIN.file_system_check_vmstate(misc.make_a_request({
        "interval": interval,
        "times": times,
        "primaryStorageUuid": primaryStorageUuid,
        "targetHostUuid": targetHostUuid,
        "storageCheckerTimeout": storageCheckerTimeout,
        "mountPath": mountPath
    }))


@misc.return_jsonobject()
def ceph_host_heartbeat_check(interval, times, primaryStorageUuid, targetHostUuid, storageCheckerTimeout, poolNames,
                              manufacturer):
    return HA_PLUGIN.ceph_host_heartbeat_check(misc.make_a_request({
        "interval": interval,
        "times": times,
        "primaryStorageUuid": primaryStorageUuid,
        "targetHostUuid": targetHostUuid,
        "storageCheckerTimeout": storageCheckerTimeout,
        "poolNames": poolNames,
        "manufacturer": manufacturer
    }))


@misc.return_jsonobject()
def sanlock_scan_host(interval, times, hostIds):
    return HA_PLUGIN.sanlock_scan_host(misc.make_a_request({
        "interval": interval,
        "times": times,
        "hostIds": hostIds
    }))


@misc.return_jsonobject()
def setup_sharedblock_self_fencer(vgUuid, hostUuid, provisioning, addons, primaryStorageUuid,
                                  interval, maxAttempts, storageCheckerTimeout, strategy, fencers,
                                  fail_if_no_path='true', checkIo='true'):
    return HA_PLUGIN.setup_sharedblock_self_fencer(misc.make_a_request({
        "vgUuid": vgUuid,
        "hostUuid": hostUuid,
        "provisioning": provisioning,
        "addons": addons,
        "primaryStorageUuid": primaryStorageUuid,
        "interval": interval,
        "maxAttempts": maxAttempts,
        "storageCheckerTimeout": storageCheckerTimeout,
        "strategy": strategy,
        "fail_if_no_path": fail_if_no_path,
        "checkIo": checkIo,
        "fencers": fencers
    }))

@misc.return_jsonobject()
def setup_self_fencer(hostUuid, interval, maxAttempts, mountPaths, uuids, urls, mountedByZStack,
                      mountOptions, storageCheckerTimeout, strategy, fencers):
    return HA_PLUGIN.setup_self_fencer(misc.make_a_request({
        "hostUuid": hostUuid,
        "interval": interval,
        "maxAttempts": maxAttempts,
        "mountPaths": mountPaths,
        "uuids": uuids,
        "urls": urls,
        "mountedByZStack": mountedByZStack,
        "mountOptions": mountOptions,
        "storageCheckerTimeout": storageCheckerTimeout,
        "strategy": strategy,
        "fencers": fencers
    }))

@misc.return_jsonobject()
def file_system_check_vmstate(interval, times, primaryStorageUuid, targetHostUuid, storageCheckerTimeout, mountPath):
    return HA_PLUGIN.file_system_check_vmstate(misc.make_a_request({
        "interval": interval,
        "times": times,
        "primaryStorageUuid": primaryStorageUuid,
        "targetHostUuid": targetHostUuid,
        "storageCheckerTimeout": storageCheckerTimeout,
        "mountPath": mountPath
    }))

@misc.return_jsonobject()
def sharedblock_check_vmstate(host_uuid, storage_check_timeout, interval, max_attempts, ps_uuid):
    return HA_PLUGIN.sharedblock_check_vmstate(misc.make_a_request({
        "hostUuid": host_uuid,
        "storageCheckerTimeout": storage_check_timeout,
        "interval": interval,
        "times": max_attempts,
        "psUuid": ps_uuid
    }))


@misc.return_jsonobject()
def add_vm_fencer_rule_to_host(allowFencerName, allVmUuids, blockFencerName, blockVmUuids):
    return HA_PLUGIN.add_vm_fencer_rule_to_host(misc.make_a_request({
        "allowRules": [{"fencerName": allowFencerName, "vmUuids": allVmUuids}],
        "blockRules": [{"fencerName": blockFencerName, "vmUuids": blockVmUuids}]
    }))

@misc.return_jsonobject()
def remove_vm_fencer_rule_from_host(allowFencerName, allVmUuids, blockFencerName, blockVmUuids):
    return HA_PLUGIN.remove_vm_fencer_rule_from_host(misc.make_a_request({
        "allowRules": [{"fencerName": allowFencerName, "vmUuids": allVmUuids}],
        "blockRules": [{"fencerName": blockFencerName, "vmUuids": blockVmUuids}]
    }))

@misc.return_jsonobject()
def get_vm_fencer_rule():
    return HA_PLUGIN.get_vm_fencer_rule(misc.make_a_request({}))
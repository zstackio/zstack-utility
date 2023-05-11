from zstacklib.test.utils import env, misc
from zstacklib.utils import linux, jsonobject, bash
from kvmagent.plugins import shared_block_plugin

SHAREBLOCK_PLUGIN = None


def init_shareblock_plugin():
    global SHAREBLOCK_PLUGIN
    if SHAREBLOCK_PLUGIN is not None:
        return SHAREBLOCK_PLUGIN

    SHAREBLOCK_PLUGIN = shared_block_plugin.SharedBlockPlugin()
    return SHAREBLOCK_PLUGIN


@misc.return_jsonobject()
def shareblock_connect(sharedBlockUuids=None, allSharedBlockUuids=None, vgUuid=None,hostId=None,hostUuid=None, forceWipe=True):
    return SHAREBLOCK_PLUGIN.connect(misc.make_a_request({
        "sharedBlockUuids":sharedBlockUuids, # [], ls /dev/disk/by-id -l|grep scsi
        "allSharedBlockUuids":allSharedBlockUuids,
        "vgUuid": vgUuid ,# random uuid
        "hostId":hostId,
        "hostUuid": hostUuid,
        "forceWipe": forceWipe,
        "primaryStorageUuid":vgUuid
    }))

@misc.return_jsonobject()
def shareblock_disconnect(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.disconnect(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def shareblock_create_root_volume(templatePathInCache=None, installPath=None, volumeUuid=None, vgUuid=None, hostUuid=None, primaryStorageUuid=None):
    return SHAREBLOCK_PLUGIN.create_root_volume(misc.make_a_request({
        "templatePathInCache": templatePathInCache ,# random uuid
        "installPath": installPath,
        "volumeUuid":volumeUuid,
        "vgUuid": vgUuid,
        "hostUuid": hostUuid,
        "primaryStorageUuid": primaryStorageUuid
    }))

@misc.return_jsonobject()
def shareblock_create_data_volume_with_backing(templatePathInCache=None, installPath=None, volumeUuid=None, vgUuid=None, hostUuid=None, primaryStorageUuid=None):
    return SHAREBLOCK_PLUGIN.create_data_volume_with_backing(misc.make_a_request({
        "templatePathInCache": templatePathInCache ,# random uuid
        "installPath": installPath,
        "volumeUuid":volumeUuid,
        "vgUuid": vgUuid,
        "hostUuid": hostUuid,
        "primaryStorageUuid": primaryStorageUuid
    }))

@misc.return_jsonobject()
def shareblock_delete_bits(path=None, vgUuid=None, hostUuid=None, primaryStorageUuid=None):
    return SHAREBLOCK_PLUGIN.delete_bits(misc.make_a_request({
        "path": path ,# random uuid
        "vgUuid": vgUuid,
        "hostUuid":hostUuid,
        "primaryStorageUuid":primaryStorageUuid
    }))

@misc.return_jsonobject()
def shareblock_create_template_from_volume(volumePath=None, installPath=None, sharedVolume=False, hostUuid=None, vgUuid=None):
    return SHAREBLOCK_PLUGIN.create_template_from_volume(misc.make_a_request({
        "volumePath": volumePath,
        "installPath": installPath,
        "sharedVolume":sharedVolume,
        "hostUuid":hostUuid,
        "vgUuid": vgUuid
    }))

@misc.return_jsonobject()
def shareblock_create_image_cache_from_volume(volumePath=None, installPath=None, sharedVolume=False, hostUuid=None, vgUuid=None):
    return SHAREBLOCK_PLUGIN.create_image_cache_from_volume(misc.make_a_request({
        "volumePath": volumePath,
        "installPath": installPath,
        "sharedVolume":sharedVolume,
        "hostUuid":hostUuid,
        "vgUuid": vgUuid
    }))

# todo: sftp

@misc.return_jsonobject()
def shareblock_revert_volume_from_snapshot(snapshotInstallPath=None, installPath=None, vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.revert_volume_from_snapshot(misc.make_a_request({
        "snapshotInstallPath": snapshotInstallPath ,# random uuid
        "installPath": installPath,
        "vgUuid": vgUuid,
        "hostUuid": hostUuid
    }))

# todo
@misc.return_jsonobject()
def shareblock_merge_snapshot(snapshotInstallPath=None, workspaceInstallPath=None, vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.merge_snapshot(misc.make_a_request({
        "snapshotInstallPath": snapshotInstallPath ,# random uuid
        "workspaceInstallPath": workspaceInstallPath,
        "vgUuid": vgUuid,
        "hostUuid": hostUuid
    }))

#todo
@misc.return_jsonobject()
def shareblock_extend_merge_target():
    return SHAREBLOCK_PLUGIN.extend_merge_target(misc.make_a_request({
    }))

#todo
@misc.return_jsonobject()
def shareblock_offline_merge_snapshots():
    return SHAREBLOCK_PLUGIN.offline_merge_snapshots(misc.make_a_request({
    }))

@misc.return_jsonobject()
def shareblock_create_empty_volume(installPath=None, backingFile=None,size=None, volumeUuid=None, hostUuid=None, vgUuid=None, kvmHostAddons={}):
    return SHAREBLOCK_PLUGIN.create_empty_volume(misc.make_a_request({
        "installPath": installPath ,# vguuid/volumeuuid
        "backingFile": backingFile,
        "size": size,
        "volumeUuid": volumeUuid,
        "hostUuid":hostUuid,
        "vgUuid":vgUuid,
        "kvmHostAddons":kvmHostAddons
    }))

@misc.return_jsonobject()
def shareblock_convert_image_to_volume(primaryStorageInstallPath=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.convert_image_to_volume(misc.make_a_request({
        "primaryStorageInstallPath": primaryStorageInstallPath ,# random uuid
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def shareblock_check_bits(path=None, vgUuid=None):
    return SHAREBLOCK_PLUGIN.check_bits(misc.make_a_request({
        "path": path ,# random uuid
        "vgUuid": vgUuid
    }))

@misc.return_jsonobject()
def shareblock_resize_volume(installPath=None, size=None, force=True):
    return SHAREBLOCK_PLUGIN.resize_volume(misc.make_a_request({
        "installPath": installPath ,# random uuid
        "size": size,
        "force": force
    }))

@misc.return_jsonobject()
def shareblock_active_lv(vgUuid=None, installPath=None, lockType=None, recursive=False, killProcess=None):
    return SHAREBLOCK_PLUGIN.active_lv(misc.make_a_request({
        "vgUuid": vgUuid ,
        "installPath": installPath,
        "lockType":lockType,
        "recursive": recursive,
        "killProcess":killProcess
    }))

@misc.return_jsonobject()
def shareblock_get_volume_size(vgUuid=None, installPath=None):
    return SHAREBLOCK_PLUGIN.get_volume_size(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "installPath": installPath
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_add_disk(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.add_disk(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_migrate_volumes(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.migrate_volumes(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_get_block_devices(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.get_block_devices(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_download_from_kvmhost(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.download_from_kvmhost(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_cancel_download_from_kvmhost(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.cancel_download_from_kvmhost(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_get_backing_chain(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.get_backing_chain(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

# todo add case
@misc.return_jsonobject()
def shareblock_convert_volume_provisioning(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.convert_volume_provisioning(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_config_filter(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.config_filter(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_convert_volume_format(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.convert_volume_format(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_get_download_bits_from_kvmhost_progress(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.get_download_bits_from_kvmhost_progress(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_shrink_snapshot(vgUuid=None, hostUuid=None):
    return SHAREBLOCK_PLUGIN.shrink_snapshot(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def shareblock_get_qcow2_hashvalue(installPath=None):
    return SHAREBLOCK_PLUGIN.get_qcow2_hashvalue(misc.make_a_request({
        "installPath": installPath
    }))

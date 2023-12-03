from zstacklib.test.utils import env, misc
from zstacklib.utils import linux, jsonobject, bash
from kvmagent.plugins import shared_block_plugin

SHAREDBLOCK_PLUGIN = None


def get_sharedblock_plugin():
    # type: () -> (shared_block_plugin.SharedBlockPlugin)
    global SHAREDBLOCK_PLUGIN
    if SHAREDBLOCK_PLUGIN is None:
        SHAREDBLOCK_PLUGIN = shared_block_plugin.SharedBlockPlugin()

    return SHAREDBLOCK_PLUGIN

@misc.return_jsonobject()
def sharedblock_ping(vgUuid):
    return get_sharedblock_plugin().ping(misc.make_a_request({
        "vgUuid":vgUuid
    }))

@misc.return_jsonobject()
def shareblock_connect(sharedBlockUuids=None, allSharedBlockUuids=None, vgUuid=None,hostId=None,hostUuid=None, forceWipe=True, isFirst=True):
    return get_sharedblock_plugin().connect(misc.make_a_request({
        "sharedBlockUuids":sharedBlockUuids, # [], ls /dev/disk/by-id -l|grep scsi
        "allSharedBlockUuids":allSharedBlockUuids,
        "vgUuid": vgUuid ,# random uuid
        "hostId":hostId,
        "hostUuid": hostUuid,
        "forceWipe": forceWipe,
        "primaryStorageUuid":vgUuid,
        "isFirst":isFirst
    }))

@misc.return_jsonobject()
def shareblock_disconnect(vgUuid=None, hostUuid=None):
    return get_sharedblock_plugin().disconnect(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def shareblock_create_root_volume(templatePathInCache=None, installPath=None, volumeUuid=None, vgUuid=None, hostUuid=None, primaryStorageUuid=None):
    return get_sharedblock_plugin().create_root_volume(misc.make_a_request({
        "templatePathInCache": templatePathInCache ,# random uuid
        "installPath": installPath,
        "volumeUuid":volumeUuid,
        "vgUuid": vgUuid,
        "hostUuid": hostUuid,
        "primaryStorageUuid": primaryStorageUuid
    }))

@misc.return_jsonobject()
def shareblock_create_data_volume_with_backing(templatePathInCache=None, installPath=None, volumeUuid=None, vgUuid=None, hostUuid=None, primaryStorageUuid=None):
    return get_sharedblock_plugin().create_data_volume_with_backing(misc.make_a_request({
        "templatePathInCache": templatePathInCache ,# random uuid
        "installPath": installPath,
        "volumeUuid":volumeUuid,
        "vgUuid": vgUuid,
        "hostUuid": hostUuid,
        "primaryStorageUuid": primaryStorageUuid
    }))

@misc.return_jsonobject()
def shareblock_delete_bits(path=None, vgUuid=None, hostUuid=None, primaryStorageUuid=None):
    return get_sharedblock_plugin().delete_bits(misc.make_a_request({
        "path": path ,# random uuid
        "vgUuid": vgUuid,
        "hostUuid":hostUuid,
        "primaryStorageUuid":primaryStorageUuid
    }))

@misc.return_jsonobject()
def shareblock_create_template_from_volume(volumePath=None, installPath=None, sharedVolume=False, hostUuid=None, vgUuid=None, addons={},
                                           provisioning=None):
    return get_sharedblock_plugin().create_template_from_volume(misc.make_a_request({
        "volumePath": volumePath,
        "installPath": installPath,
        "sharedVolume":sharedVolume,
        "hostUuid":hostUuid,
        "vgUuid": vgUuid,
        "addons":addons,
        "provisioning":provisioning
    }))

@misc.return_jsonobject()
def shareblock_create_image_cache_from_volume(volumePath=None, installPath=None, sharedVolume=False, hostUuid=None, vgUuid=None):
    return get_sharedblock_plugin().create_image_cache_from_volume(misc.make_a_request({
        "volumePath": volumePath,
        "installPath": installPath,
        "sharedVolume":sharedVolume,
        "hostUuid":hostUuid,
        "vgUuid": vgUuid
    }))

@misc.return_jsonobject()
def sharedblock_upload_to_sftp(primaryStorageInstallPath=None, backupStorageInstallPath=None, hostname=None, username=None, sshKey=None, sshPort=None):
    return get_sharedblock_plugin().upload_to_sftp(misc.make_a_request({
        "primaryStorageInstallPath": primaryStorageInstallPath,
        "backupStorageInstallPath": backupStorageInstallPath,
        "hostname":hostname,
        "username":username,
        "sshKey": sshKey,
        "sshPort":sshPort
    }))

@misc.return_jsonobject()
def sharedblock_download_from_sftp(primaryStorageInstallPath=None, backupStorageInstallPath=None, hostname=None, username=None, sshKey=None, sshPort=None, vgUuid=None):
    return get_sharedblock_plugin().download_from_sftp(misc.make_a_request({
        "primaryStorageInstallPath": primaryStorageInstallPath,
        "backupStorageInstallPath": backupStorageInstallPath,
        "hostname":hostname,
        "username":username,
        "sshKey": sshKey,
        "sshPort":sshPort,
        "vgUuid":vgUuid,
        "primaryStorageUuid":vgUuid
    }))

@misc.return_jsonobject()
def shareblock_revert_volume_from_snapshot(snapshotInstallPath=None, installPath=None, vgUuid=None, hostUuid=None):
    return get_sharedblock_plugin().revert_volume_from_snapshot(misc.make_a_request({
        "snapshotInstallPath": snapshotInstallPath ,# random uuid
        "installPath": installPath,
        "vgUuid": vgUuid,
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def sharedblock_merge_snapshot(snapshotInstallPath=None, workspaceInstallPath=None, vgUuid=None, hostUuid=None):
    return get_sharedblock_plugin().merge_snapshot(misc.make_a_request({
        "snapshotInstallPath": snapshotInstallPath ,# random uuid
        "workspaceInstallPath": workspaceInstallPath,
        "vgUuid": vgUuid,
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def sharedblock_extend_merge_target(fullRebase=False, srcPath=None, destPath=None, volumeUuid=None, vgUuid=None):
    return get_sharedblock_plugin().extend_merge_target(misc.make_a_request({
        "fullRebase": fullRebase,
        "srcPath": srcPath,
        "destPath": destPath,
        "volumeUuid": volumeUuid,
        "vgUuid": vgUuid
    }))

@misc.return_jsonobject()
def sharedblock_offline_merge_snapshots(fullRebase=False, srcPath=None, destPath=None, volumeUuid=None, vgUuid=None):
    return get_sharedblock_plugin().offline_merge_snapshots(misc.make_a_request({
        "fullRebase": fullRebase,
        "srcPath": srcPath,
        "destPath": destPath,
        "volumeUuid": volumeUuid,
        "vgUuid": vgUuid
    }))

@misc.return_jsonobject()
def shareblock_create_empty_volume(installPath=None, backingFile=None,size=None, volumeUuid=None, hostUuid=None, vgUuid=None, kvmHostAddons={},taskContext={}):
    return get_sharedblock_plugin().create_empty_volume(misc.make_a_request({
        "installPath": installPath ,# vguuid/volumeuuid
        "backingFile": backingFile,
        "size": size,
        "volumeUuid": volumeUuid,
        "hostUuid":hostUuid,
        "vgUuid":vgUuid,
        "kvmHostAddons":kvmHostAddons,
        "taskContext":taskContext
    }))

@misc.return_jsonobject()
def shareblock_convert_image_to_volume(primaryStorageInstallPath=None, hostUuid=None):
    return get_sharedblock_plugin().convert_image_to_volume(misc.make_a_request({
        "primaryStorageInstallPath": primaryStorageInstallPath ,# random uuid
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def sharedblock_check_bits(path=None, vgUuid=None):
    return get_sharedblock_plugin().check_bits(misc.make_a_request({
        "path": path ,# random uuid
        "vgUuid": vgUuid
    }))

@misc.return_jsonobject()
def sharedblock_resize_volume(installPath=None, size=None, force=False):
    return get_sharedblock_plugin().resize_volume(misc.make_a_request({
        "installPath": installPath ,# random uuid
        "size": size,
        "force": force
    }))

@misc.return_jsonobject()
def sharedblock_active_lv(vgUuid=None, installPath=None, lockType=None, recursive=False, killProcess=None):
    return get_sharedblock_plugin().active_lv(misc.make_a_request({
        "vgUuid": vgUuid ,
        "installPath": installPath,
        "lockType":lockType,
        "recursive": recursive,
        "killProcess":killProcess
    }))

@misc.return_jsonobject()
def sharedblock_get_volume_size(vgUuid=None, installPath=None):
    return get_sharedblock_plugin().get_volume_size(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "installPath": installPath
    }))

@misc.return_jsonobject()
def sharedblock_batch_get_volume_size(vgUuid=None, volumeUuidInstallPaths={}):
    return get_sharedblock_plugin().batch_get_volume_size(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "volumeUuidInstallPaths": volumeUuidInstallPaths
    }))

@misc.return_jsonobject()
def sharedblock_add_disk(vgUuid=None, hostUuid=None, diskUuid=None, allSharedBlockUuids=[], forceWipe=None):
    return get_sharedblock_plugin().add_disk(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "diskUuid":diskUuid,
        "allSharedBlockUuids":allSharedBlockUuids,
        "forceWipe":forceWipe
    }))

@misc.return_jsonobject()
def sharedblock_migrate_volumes(vgUuid=None, hostUuid=None, migrateVolumeStructs=None, provisioning=None, volumePath=None, addons={}):
    return get_sharedblock_plugin().migrate_volumes(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "migrateVolumeStructs":migrateVolumeStructs,
        "provisioning":provisioning,
        "addons":addons,
        "volumePath":volumePath
    }))

@misc.return_jsonobject()
def shareblock_get_block_devices(vgUuid=None, hostUuid=None):
    return get_sharedblock_plugin().get_block_devices(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def sharedblock_check_disks(rescan_scsi=True, rescan=True, sharedBlockUuids=[], vgUuid=None, failIfNoPath=True, hostUuid=None):
    return get_sharedblock_plugin().check_disks(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "rescan_scsi":rescan_scsi,
        "rescan":rescan,
        "sharedBlockUuids":sharedBlockUuids,
        "failIfNoPath":failIfNoPath
    }))

@misc.return_jsonobject()
def sharedblock_download_from_kvmhost(primaryStorageInstallPath=None, backupStorageInstallPath=None, hostname=None, username=None,
                                      sshKey=None, sshPort=None, vgUuid=None, lockType=None):
    return get_sharedblock_plugin().download_from_kvmhost(misc.make_a_request({
        "primaryStorageInstallPath": primaryStorageInstallPath,
        "backupStorageInstallPath": backupStorageInstallPath,
        "hostname":hostname,
        "username":username,
        "sshKey": sshKey,
        "sshPort":sshPort,
        "vgUuid":vgUuid,
        "primaryStorageUuid":vgUuid,
        "lockType":lockType
    }))

#todo add case
@misc.return_jsonobject()
def shareblock_cancel_download_from_kvmhost(vgUuid=None, hostUuid=None):
    return get_sharedblock_plugin().cancel_download_from_kvmhost(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid
    }))

@misc.return_jsonobject()
def shareblock_get_backing_chain(vgUuid=None, hostUuid=None, volumeUuid=None, installPath=None, containSelf=None):
    return get_sharedblock_plugin().get_backing_chain(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "containSelf":containSelf,
        "volumeUuid":volumeUuid,
        "installPath":installPath
    }))

@misc.return_jsonobject()
def sharedblock_convert_volume_provisioning(vgUuid=None, hostUuid=None, volumeUuid=None, installPath=None, provisioningStrategy=None, addons={}):
    return get_sharedblock_plugin().convert_volume_provisioning(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "volumeUuid":volumeUuid,
        "installPath":installPath,
        "provisioningStrategy":provisioningStrategy,
        "addons":addons
    }))

@misc.return_jsonobject()
def sharedblock_config_filter(vgUuid=None, hostUuid=None, allSharedBlockUuids=[]):
    return get_sharedblock_plugin().config_filter(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "allSharedBlockUuids":allSharedBlockUuids
    }))

@misc.return_jsonobject()
def sharedblock_convert_volume_format(vgUuid=None, hostUuid=None, dstFormat=None, installPath=None):
    return get_sharedblock_plugin().convert_volume_format(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "dstFormat":dstFormat,
        "installPath":installPath
    }))

@misc.return_jsonobject()
def shareblock_get_download_bits_from_kvmhost_progress(vgUuid=None, hostUuid=None, volumePaths=[]):
    return get_sharedblock_plugin().get_download_bits_from_kvmhost_progress(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "volumePaths":volumePaths
    }))

@misc.return_jsonobject()
def sharedblock_shrink_snapshot(vgUuid=None, hostUuid=None, installPath=None,kvmHostAddons={}):
    return get_sharedblock_plugin().shrink_snapshot(misc.make_a_request({
        "vgUuid": vgUuid ,# random uuid
        "hostUuid": hostUuid,
        "installPath":installPath,
        "kvmHostAddons":kvmHostAddons
    }))

@misc.return_jsonobject()
def shareblock_get_qcow2_hashvalue(installPath=None):
    return get_sharedblock_plugin().get_qcow2_hashvalue(misc.make_a_request({
        "installPath": installPath
    }))

@misc.return_jsonobject()
def sharedblock_check_lock(vgUuids=[]):
    return get_sharedblock_plugin().check_vg_state(misc.make_a_request({
        "vgUuids": vgUuids
    }))

@misc.return_jsonobject()
def sharedblock_estimate_template(volumePath, vgUuid=None, hostUuid=None):
    return get_sharedblock_plugin().estimate_template(misc.make_a_request({
        "vgUuid": vgUuid,
        "hostUuid":hostUuid,
        "volumePath":volumePath
    }))

from zstacklib.test.utils import misc
from kvmagent.plugins.nfs_primarystorage_plugin import NfsPrimaryStoragePlugin

NFS_PLUGIN = None # type:NfsPrimaryStoragePlugin

def init_nfs_plugin():
    global NFS_PLUGIN
    if NFS_PLUGIN is not None:
        return NFS_PLUGIN

    NFS_PLUGIN = NfsPrimaryStoragePlugin()
    NFS_PLUGIN.mount_path = {}
    return NFS_PLUGIN

@misc.return_jsonobject()
def mount(url, mountPath, options, uuid):
    return NFS_PLUGIN.mount(misc.make_a_request({
        "url": url,
        "mountPath": mountPath,
        "options": options,
        "uuid": uuid
    }))

@misc.return_jsonobject()
def create_root_volume_from_template(templatePathInCache, timeout, virtualSize, installUrl, name,
                                     volumeUuid, uuid, primaryStorageUuid, kvmHostAddons,
                                     accountUuid="36c27e8ff05c4780bf6d2fa65700f22e"):
    return NFS_PLUGIN.create_root_volume_from_template(misc.make_a_request({
        "templatePathInCache": templatePathInCache,
        "timeout": timeout,
        "virtualSize": virtualSize,
        "installUrl": installUrl,
        "accountUuid": accountUuid,
        "name": name,
        "volumeUuid": volumeUuid,
        "uuid": uuid,
        "primaryStorageUuid": primaryStorageUuid,
        "kvmHostAddons": kvmHostAddons
    }))

@misc.return_jsonobject()
def migrate_bits(srcFolderPath, dstFolderPath, independentPath=False, filtPaths=[], isMounted=True, volumeInstallPath=None, options=None,
                 url=None, mountPath=None, kvmHostAddons={"qcow2Options":""}):

    return NFS_PLUGIN.migrate_bits(misc.make_a_request({
        "srcFolderPath": srcFolderPath,
        "dstFolderPath": dstFolderPath,
        "independentPath": independentPath,
        "filtPaths": filtPaths,
        "isMounted": isMounted,
        "volumeInstallPath": volumeInstallPath,
        "options": options,
        "url": url,
        "mountPath": mountPath,
        "kvmHostAddons":kvmHostAddons
    }))


@misc.return_jsonobject()
def get_volume_base_image(volumeInstallPath, volumeInstallDir, imageCacheDir, volumeUuid):
    return NFS_PLUGIN.get_volume_base_image_path(misc.make_a_request({
        "volumeInstallPath": volumeInstallPath,
        "volumeInstallDir": volumeInstallDir,
        "imageCacheDir": imageCacheDir,
        "volumeUuid": volumeUuid
    }))

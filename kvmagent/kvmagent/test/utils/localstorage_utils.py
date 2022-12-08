from zstacklib.test.utils import env, misc
from zstacklib.utils import linux, jsonobject, bash
from kvmagent.plugins import localstorage

LOCALSTORAGE_PLUGIN = None


def init_localstorage_plugin():
    global LOCALSTORAGE_PLUGIN
    if LOCALSTORAGE_PLUGIN is not None:
        return LOCALSTORAGE_PLUGIN

    LOCALSTORAGE_PLUGIN = localstorage.LocalStoragePlugin()
    return LOCALSTORAGE_PLUGIN


@misc.return_jsonobject()
def localstorage_init(path=None, initFilePath=None):
    return LOCALSTORAGE_PLUGIN.init(misc.make_a_request({
        "path":path,
        "initFilePath":initFilePath
    }))

@misc.return_jsonobject()
def get_physical_capacity(storagePath):
    return LOCALSTORAGE_PLUGIN.get_physical_capacity(misc.make_a_request({
        "storagePath":storagePath
    }))

@misc.return_jsonobject()
def create_empty_volume(installUrl=None, backingFile=None, size=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.create_empty_volume(misc.make_a_request({
        "installUrl" : installUrl,
        "backingFile" : backingFile,
        "size" : size,
        "storagePath": storagePath
    }))

@misc.return_jsonobject()
def create_folder(installUrl=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.create_folder(misc.make_a_request({
        "installUrl":installUrl,
        "storagePath" : storagePath
    }))

@misc.return_jsonobject()
def create_root_volume_from_template(templatePathInCache=None, installUrl=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.create_root_volume_from_template(misc.make_a_request({
        "templatePathInCache":templatePathInCache,
        "installUrl":installUrl,
        "storagePath": storagePath
    }))

@misc.return_jsonobject()
def create_volume_with_backing(templatePathInCache=None, installPath=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.create_volume_with_backing(misc.make_a_request({
        "templatePathInCache":templatePathInCache,
        "installPath":installPath,
        "storagePath":storagePath
    }))

@misc.return_jsonobject()
def deleteImage(path=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.delete(misc.make_a_request({
        "path":path,
        "storagePath":storagePath
    }))


@misc.return_jsonobject()
def deleteDir(path=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.deletedir(misc.make_a_request({
        "path":path,
        "storagePath":storagePath
    }))

# sftp or imagestore


# snapshot
@misc.return_jsonobject()
def revert_snapshot(snapshotInstallPath=None):
    return LOCALSTORAGE_PLUGIN.revert_snapshot(misc.make_a_request({
        "snapshotInstallPath":snapshotInstallPath
    }))

@misc.return_jsonobject()
def reinit_image(imagePath=None, volumePath=None):
    return LOCALSTORAGE_PLUGIN.reinit_image(misc.make_a_request({
        "imagePath":imagePath, # src_image
        "volumePath":volumePath # dst_image
    }))

@misc.return_jsonobject()
def merge_snapshot(workspaceInstallPath=None, snapshotInstallPath=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.merge_snapshot(misc.make_a_request({
        "snapshotInstallPath":snapshotInstallPath, # src_image
        "workspaceInstallPath":workspaceInstallPath, # dst_image
        "storagePath":storagePath
    }))


# todo
@misc.return_jsonobject()
def merge_and_rebase_snapshot(workspaceInstallPath=None, snapshotInstallPaths=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.merge_and_rebase_snapshot(misc.make_a_request({
        "snapshotInstallPaths":snapshotInstallPaths, # src_image
        "workspaceInstallPath":workspaceInstallPath, # dst_image
        "storagePath":storagePath
    }))

# todo, not fullRebase
@misc.return_jsonobject()
def offline_merge_snapshot(srcPath=None, destPath=None, storagePath=None, fullRebase=True):
    return LOCALSTORAGE_PLUGIN.offline_merge_snapshot(misc.make_a_request({
        "srcPath":srcPath, # src_image
        "destPath":destPath, # dst_image
        "storagePath":storagePath,
        "fullRebase" : fullRebase
    }))

@misc.return_jsonobject()
def create_template_from_volume(installPath=None, volumePath=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.create_template_from_volume(misc.make_a_request({
        "volumePath":volumePath, # src_image
        "installPath":installPath, # dst_image
        "storagePath":storagePath
    }))

@misc.return_jsonobject()
def check_bits(path=None):
    return LOCALSTORAGE_PLUGIN.check_bits(misc.make_a_request({
        "path":path
    }))

# todo
@misc.return_jsonobject()
def rebase_root_volume_to_backing_file(backingFilePath=None, rootVolumePath=None):
    return LOCALSTORAGE_PLUGIN.rebase_root_volume_to_backing_file(misc.make_a_request({
        "backingFilePath":backingFilePath,
        "rootVolumePath": rootVolumePath
    }))
#todo
@misc.return_jsonobject()
def verify_backing_file_chain(snapshots=None):
    return LOCALSTORAGE_PLUGIN.verify_backing_file_chain(misc.make_a_request({
        "snapshots":snapshots
    }))

#todo
@misc.return_jsonobject()
def rebase_backing_files(snapshots=None):
    return LOCALSTORAGE_PLUGIN.rebase_backing_files(misc.make_a_request({
        "snapshots":snapshots
    }))

# copy_bits_to_remote get_md5 check_md5

@misc.return_jsonobject()
def get_backing_file_path(path=None):
    return LOCALSTORAGE_PLUGIN.get_backing_file_path(misc.make_a_request({
        "path":path
    }))


@misc.return_jsonobject()
def get_volume_size(installPath):
    return LOCALSTORAGE_PLUGIN.get_volume_size(misc.make_a_request({
        "installPath" :installPath
    }))

# todo
@misc.return_jsonobject()
def get_volume_base_image_path(volumeInstallDir=None, volumeUuid=None, imageCacheDir=None):
    return LOCALSTORAGE_PLUGIN.get_volume_base_image_path(misc.make_a_request({
        "volumeInstallDir":volumeInstallDir,
        "volumeUuid":volumeUuid,
        "imageCacheDir": imageCacheDir
    }))

@misc.return_jsonobject()
def get_qcow2_reference(searchingDir=None, path=None, imageCacheDir=None):
    return LOCALSTORAGE_PLUGIN.get_qcow2_reference(misc.make_a_request({
        "searchingDir":searchingDir,
        "path":path
    }))

# depend imagestore so must init kvmagent and start plugin
@misc.return_jsonobject()
def convert_qcow2_to_raw(srcPath=None):
    return LOCALSTORAGE_PLUGIN.convert_qcow2_to_raw(misc.make_a_request({
        "srcPath":srcPath
    }))

@misc.return_jsonobject()
def resize_volume(installPath=None, size=None, force=None):
    return LOCALSTORAGE_PLUGIN.resize_volume(misc.make_a_request({
        "installPath":installPath,
        "size": size,
        "force": force
    }))

@misc.return_jsonobject()
def hardlink_volume(srcDir=None, dstDir=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.hardlink_volume(misc.make_a_request({
        "srcDir":srcDir,
        "dstDir": dstDir,
        "storagePath": storagePath
    }))

@misc.return_jsonobject()
def check_initialized_file(filePath=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.check_initialized_file(misc.make_a_request({
        "filePath":filePath,
        "storagePath": storagePath
    }))

@misc.return_jsonobject()
def create_initialized_file(filePath=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.create_initialized_file(misc.make_a_request({
        "filePath":filePath,
        "storagePath": storagePath
    }))
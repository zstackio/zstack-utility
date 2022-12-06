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
def create_volume_with_backing(templatePathInCache=None, installUrl=None, storagePath=None):
    return LOCALSTORAGE_PLUGIN.create_volume_with_backing(misc.make_a_request({
        "templatePathInCache":templatePathInCache,
        "installUrl":installUrl,
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
    return LOCALSTORAGE_PLUGIN.delete(misc.make_a_request({
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

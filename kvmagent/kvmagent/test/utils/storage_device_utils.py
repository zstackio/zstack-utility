from zstacklib.test.utils import env, misc
from zstacklib.utils import linux, jsonobject, bash
from kvmagent.plugins import storage_device

STORAGEDEVICE_PLUGIN = None


def init_storagedevice_plugin():
    global STORAGEDEVICE_PLUGIN
    if STORAGEDEVICE_PLUGIN is not None:
        return STORAGEDEVICE_PLUGIN

    STORAGEDEVICE_PLUGIN = storage_device.StorageDevicePlugin()
    return STORAGEDEVICE_PLUGIN


@misc.return_jsonobject()
def iscsi_login(iscsiServerIp=None, iscsiServerPort=None):
    return STORAGEDEVICE_PLUGIN.iscsi_login(misc.make_a_request({
        "iscsiServerIp":iscsiServerIp,
        "iscsiServerPort":iscsiServerPort
    }))

@misc.return_jsonobject()
def iscsi_logout(iscsiServerIp=None, iscsiServerPort=None):
        return STORAGEDEVICE_PLUGIN.iscsi_logout(misc.make_a_request({
        "iscsiServerIp":iscsiServerIp,
        "iscsiServerPort":iscsiServerPort
    }))


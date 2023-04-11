import os

from zstacklib.test.utils import env
from zstacklib.utils import uuidhelper, linux, xmlobject

if not os.path.isdir(env.VOLUME_DIR):
    os.makedirs(env.VOLUME_DIR)

attach_volume_body = {
    "volume": {
        "installPath": None,  # must fill
        "deviceId": 1,
        "deviceType": "file",
        "volumeUuid": None,  # must fill
        "useVirtio": True,
        "useVirtioSCSI": False,
        "shareable": False,
        "cacheMode": "none",
        "wwn": "0x000f6c46e4c236bf",
        "bootOrder": 0,
        "physicalBlockSize": 0,
        "type": "Data",
        "format": "qcow2",
        "primaryStorageType": "LocalStorage"
    },
    "vmInstanceUuid": None,  # must fill
    "addons": {
        "attachedDataVolumes": []
    },
    "kvmHostAddons": {
        "qcow2Options": " -o cluster_size=2097152 "
    }
}


attach_shareblock_volume_body = {
    "volume": {
        "installPath": None,  # must fill
        "deviceId": 1,
        "deviceType": "file",
        "volumeUuid": None,  # must fill
        "useVirtio": True,
        "useVirtioSCSI": False,
        "shareable": False,
        "cacheMode": "none",
        "wwn": "0x000f6c46e4c236bf",
        "bootOrder": 0,
        "physicalBlockSize": 0,
        "type": "Data",
        "format": "qcow2",
        "primaryStorageType": "SharedBlock"
    },
    "vmInstanceUuid": None,  # must fill
    "addons": {
        "attachedDataVolumes": []
    }
}

start_vm_sharedblock_data_vol = {
        "installPath": None,  # must fill
        "deviceId": 1,
        "deviceType": "file",
        "volumeUuid": None,  # must fill
        "useVirtio": True,
        "useVirtioSCSI": False,
        "shareable": False,
        "cacheMode": "none",
        "wwn": "0x000f6c46e4c236bf",
        "bootOrder": 0,
        "physicalBlockSize": 0,
        "type": "Data",
        "format": "qcow2",
        "primaryStorageType": "SharedBlock"
    }


def create_empty_volume(size=134217728):  # 128M
    # type: (long) -> (str, str)

    """
    :param size: volume size in bytes
    :return: (volume_uuid, install_path)
    """

    vol_uuid = uuidhelper.uuid()
    vol_path = os.path.join(env.VOLUME_DIR, '%s.qcow2' % vol_uuid)
    linux.qcow2_create(vol_path, size)
    return vol_uuid, vol_path


def find_volume_in_vm_xml_by_path(vm_xmlobject, vol_path):
    # type: (xmlobject.XmlObject, str) -> xmlobject.XmlObject

    for vol in vm_xmlobject.devices.get_child_node_as_list('disk'):
        if vol.source.file_ == vol_path:
            return vol

    return None

def find_volume_controller_by_vol(vm_xml, controller_index):
    for controller in vm_xml.devices.get_child_node_as_list("controller"):
        if controller_index == controller.index_:
            return controller
    return None
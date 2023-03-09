import os

from zstacklib.test.utils import env

if not os.path.isdir(env.SNAPSHOT_DIR):
    os.makedirs(env.SNAPSHOT_DIR)

take_snapshot_cmd_body = {
    "vmUuid": None,  # must fill
    "volumeUuid": None,  # must fill
    "volume": {
        "installPath": None,  # must fill
        "deviceId": 0,
        "deviceType": "file",
        "volumeUuid": None,  # must fill
        "useVirtio": True,
        "useVirtioSCSI": False,
        "shareable": False,
        "cacheMode": "none",
        "wwn": "0x000fb964dbc7a10a",
        "bootOrder": 0,
        "physicalBlockSize": 0,
        "type": "Root",
        "format": "qcow2",
        "primaryStorageType": "LocalStorage"
    },
    "installPath": None,  # must fill
    "online": True,
    "fullSnapshot": False,
    "volumeInstallPath": None,  # must fill
    "isBaremetal2InstanceOnlineSnapshot": False,
    "kvmHostAddons": {
        "qcow2Options": " -o cluster_size=2097152 "
    }
}

merge_snapshot_cmd_body = {
    "vmUuid": None,  # must fill
    "volume": {
        "installPath": None,  # must fill
        "deviceId": 0,
        "deviceType": "file",
        "volumeUuid": None,  # must fill
        "useVirtio": True,
        "useVirtioSCSI": False,
        "shareable": False,
        "cacheMode": "none",
        "wwn": "0x000fb964dbc7a10a",
        "bootOrder": 0,
        "physicalBlockSize": 0,
        "type": "Root",
        "format": "qcow2",
        "primaryStorageType": "LocalStorage"
    },
    "srcPath": None,  # must fill
    "destPath": None,  # must fill
    "fullRebase": True,
    "kvmHostAddons": {
        "qcow2Options": " -o cluster_size=2097152 "
    }
}

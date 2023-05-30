import copy

import snapshot_utils
import volume_utils
import platform
from kvmagent.plugins.vm_plugin import VmPlugin, get_machineType
from kvmagent.test.utils import pytest_utils
from zstacklib.test.utils import env, misc
from zstacklib.utils import jsonobject, xmlobject, bash, linux

def get_videoType():
    if platform.machine() == 'aarch64':
        return "virtio"
    else:
        return "cirrus"
    
def get_useNuma():
    if platform.machine() == 'aarch64':
        return False
    else:
        return True
    
def get_bootMode():
    if platform.machine() == 'aarch64':
        return "UEFI"
    else:
        return "Legacy"
    
    
startVmCmdBody = {
    "vmInstanceUuid": "0b42630f37d8417480eced62ad89719f",
    "vmInternalId": 1,
    "vmName": "vm-for-ut",
    "imagePlatform": "Linux",
    "imageArchitecture": platform.machine(),
    "memory": 67108864,  # 64M
    # "memory": 16384,  # 64M
    "maxMemory": 134217728,  # 128M
    "maxVcpuNum": 128,
    "cpuNum": 1,
    "cpuSpeed": 0,
    "socketNum": None,
    "cpuOnSocket": None,
    "threadsPerCore": None,
    "bootDev": ["hd"],
    "rootVolume": {
        "installPath": env.VM_IMAGE_PATH,
        "deviceId": 0,
        "deviceType": "file",
        "volumeUuid": "d387b4534faf4553a50a8a632cf12e35",
        "useVirtio": True,
        "useVirtioSCSI": False,
        "shareable": False,
        "cacheMode": "none",
        "wwn": "0x000fb964dbc7a10a",
        "bootOrder": 1,
        "physicalBlockSize": 0
    },
    "bootIso": [],
    "cdRoms": [],
    "dataVolumes": [],
    "cacheVolumes": [],
    "nics": [{
        "mac": "fa:62:4a:61:6c:00",
        "bridgeName": "br_%s" % env.DEFAULT_ETH_INTERFACE_NAME,
        "physicalInterface": env.DEFAULT_ETH_INTERFACE_NAME,
        "uuid": "8f9ef2e5061a4b28b5f79ff24ab0c0ce",
        "nicInternalName": "vnic1.0",
        "deviceId": 0,
        "useVirtio": True,
        "bootOrder": 0,
        "mtu": 1500,
        "driverType": "virtio",
        "vHostAddOn": {
            "queueNum": 1
        }
    }],
    "timeout": 300,
    "addons": {
        "channel": {
            "socketPath": "/var/lib/libvirt/qemu/0b42630f37d8417480eced62ad89719f",
            "targetName": "org.qemu.guest_agent.0"
        },
        "usbDevice": []
    },
    "instanceOfferingOnlineChange": False,
    "nestedVirtualization": "none",
    "hostManagementIp": "10.0.245.48",
    "clock": "utc",
    "useNuma": get_useNuma(),
    "useBootMenu": True,
    "createPaused": False,
    "kvmHiddenState": False,
    "vmPortOff": False,
    "emulateHyperV": False,
    "additionalQmp": True,
    "isApplianceVm": False,
    "systemSerialNumber": "4f3e9046-776d-4095-8edd-909523ede46d",
    "bootMode": get_bootMode(),
    "fromForeignHypervisor": False,
    "machineType": get_machineType("pc"),
    "useHugePage": False,
    "chassisAssetTag": "www.zstack.io",
    "priorityConfigStruct": {
        "vmUuid": "0b42630f37d8417480eced62ad89719f",
        "cpuShares": 512,
        "oomScoreAdj": 0
    },
    "coloPrimary": False,
    "coloSecondary": False,
    "consoleLogToFile": False,
    "useColoBinary": False,
    "consoleMode": "vnc",
    "MemAccess": "private",
    "videoType": get_videoType(),
    "spiceStreamingMode": "off",
    "VDIMonitorNumber": 1,
    "pciePortNums": 0,
    "predefinedPciBridgeNum": 0,
    "kvmHostAddons": {
        "qcow2Options": " -o cluster_size=2097152 "
    },
    "x2apic": True
}

migrate_vm_cmd_body = {
    'vmUuid': None,  # must fill
    'destHostIp': None,  # must fill
    'srcHostIp': None,  # must fill
    'useNuma': False,
    'migrateFromDestination': False,
    'autoConverge': False,
    'xbzrle': False,
    'storageMigrationPolicy': 'FullCopy'
}

attach_vm_nic_body = {
    "vmUuid": None,
    "nic": {
        "mac":None,
        "bridgeName":None,
        "physicalInterface":None,
        "uuid":None,
        "nicInternalName":None,
        "deviceId":None,
        "metaData":32,
        "useVirtio":True,
        "bootOrder":0,
        "mtu":1500,
        "driverType":"virtio",
        "type":"VNIC",
        "vlanId":None,
        "vHostAddOn": {
            "queueNum" : 1,
            "rxBufferSize" : 256,
            "txBufferSize" :256
        }
    }

}

start_vm_data_vol = {
    "primaryStorageType": "LocalStorage",
    "volumeUuid": None,   # must fill
    "installPath": None,  # must fill
    "useVirtio": True,
    "format": "qcow2",
    "cacheMode": "none",
    "useVirtioSCSI": False,
    "deviceType": "file",
    "deviceId": 1,
    "bootOrder": 0,
    "physicalBlockSize": 0,
    "shareable": False,
    "wwn": "0x000f6c46e4c236bf",
    "type": "Data",
    "controllerIndex": 0,
    "ioThreadId": 0
}

volume_iothread_pin_body = {
    "vmUuid": None,
    "ioThreadId": None,
    "pin": None
}


VM_PLUGIN = None  # type: VmPlugin


def init_vm_plugin():
    global VM_PLUGIN
    if VM_PLUGIN is not None:
        return VM_PLUGIN

    VM_PLUGIN = VmPlugin()
    VM_PLUGIN.configure()
    VM_PLUGIN.start()

    return VM_PLUGIN


def create_startvm_body_jsonobject():
    # type: () -> jsonobject.JsonObject

    return jsonobject.loads(jsonobject.dumps(startVmCmdBody))

def create_startvm_body_jsonobject_with_volume_multi_queues(vol_uuid, vol_install_path):
    # type: () -> jsonobject.JsonObject
    body = copy.deepcopy(startVmCmdBody)
    data_vol = copy.deepcopy(start_vm_data_vol)
    data_vol["volumeUuid"] = vol_uuid
    data_vol["resourceUuid"] = vol_uuid
    data_vol["installPath"] = vol_install_path
    data_vol["multiQueues"] = "1"
    body["dataVolumes"] = [data_vol]
    return jsonobject.loads(jsonobject.dumps(body))


def create_startvm_body_jsonobject_with_volume_iothread(vol_uuid, vol_install_path, iothread_id, pin):
    body = copy.deepcopy(startVmCmdBody)
    data_vol = copy.deepcopy(start_vm_data_vol)
    data_vol["volumeUuid"] = vol_uuid
    data_vol["resourceUuid"] = vol_uuid
    data_vol["installPath"] = vol_install_path
    data_vol["ioThreadId"] = iothread_id
    body["addons"]["ioThreadNum"] = 1
    body["addons"]["ioThreadPins"] = [{"ioThreadId": iothread_id, "pin": pin, "volumeUuid": vol_uuid}]
    body["dataVolumes"] = [data_vol]
    return jsonobject.loads(jsonobject.dumps(body))


def build_virtio_scsi_vol_body_with_iothreadpin(vol_uuid, vol_path, iothread_id, pin, controller_index):
    data_vol = copy.deepcopy(start_vm_data_vol)
    data_vol["volumeUuid"] = vol_uuid
    data_vol["resourceUuid"] = vol_uuid
    data_vol["installPath"] = vol_path
    data_vol["ioThreadId"] = iothread_id
    data_vol["controllerIndex"] = controller_index
    data_vol["ioThreadPin"] = pin
    data_vol["useVirtioSCSI"] = True
    return data_vol, {"ioThreadId": iothread_id, "pin": pin, "volumeUuid": vol_uuid}


def build_shared_block_vol_body_with_iothread(vol_uuid, vol_path, iothread_id, pin):
    body = copy.deepcopy(volume_utils.start_vm_sharedblock_data_vol)
    body["ioThreadId"] = iothread_id
    body["ioThreadPin"] = pin
    body["resourceUuid"] = vol_uuid
    body["installPath"] = vol_path
    body["volumeUuid"] = vol_uuid
    return body, {"ioThreadId": iothread_id, "pin": pin, "volumeUuid": vol_uuid}



def build_virtio_scsi_shared_block_vol_body_with_iothread(vol_uuid, vol_path, iothread_id, pin, controller_index):
    body = copy.deepcopy(volume_utils.start_vm_sharedblock_data_vol)
    body["ioThreadId"] = iothread_id
    body["ioThreadPin"] = pin
    body["resourceUuid"] = vol_uuid
    body["installPath"] = vol_path
    body["volumeUuid"] = vol_uuid
    body["useVirtioSCSI"] = True
    body["controllerIndex"] = controller_index
    return body, {"ioThreadId": iothread_id, "pin": pin, "volumeUuid": vol_uuid}


def build_virtio_vol_with_iothreadpin(vol_uuid, vol_path, iothread_id, pin):
    data_vol = copy.deepcopy(start_vm_data_vol)
    data_vol["volumeUuid"] = vol_uuid
    data_vol["resourceUuid"] = vol_uuid
    data_vol["installPath"] = vol_path
    data_vol["ioThreadId"] = iothread_id
    data_vol["ioThreadPin"] = pin
    return data_vol, {"ioThreadId": iothread_id, "pin": pin, "volumeUuid": vol_uuid}


def create_vm_with_vols(vols_body, iothread_pin_structs):
    body = copy.deepcopy(startVmCmdBody)
    body["addons"]["ioThreadNum"] = len(iothread_pin_structs)
    body["addons"]["ioThreadPins"] = iothread_pin_structs
    body["dataVolumes"] = vols_body
    return jsonobject.loads(jsonobject.dumps(body))


def create_startvm_body_jsonobject_with_virtio_scsi_volume_iothread(vol_uuid, vol_install_path, iothread_id, pin, controller_index):
    body = copy.deepcopy(startVmCmdBody)
    data_vol = copy.deepcopy(start_vm_data_vol)
    data_vol["volumeUuid"] = vol_uuid
    data_vol["resourceUuid"] = vol_uuid
    data_vol["installPath"] = vol_install_path
    data_vol["ioThreadId"] = iothread_id
    data_vol["controllerIndex"] = controller_index
    data_vol["useVirtioSCSI"] = True
    body["addons"]["ioThreadNum"] = 1
    body["addons"]["ioThreadPins"] = [{"ioThreadId": iothread_id, "pin": pin, "volumeUuid": vol_uuid}]
    body["dataVolumes"] = [data_vol]
    return jsonobject.loads(jsonobject.dumps(body))


def create_vm(startvm_body):
    return VM_PLUGIN.start_vm(misc.make_a_request(startvm_body))


def stop_vm(vm_uuid, type='cold', timeout=5):
    # type: (str, str, int) -> None

    return VM_PLUGIN.stop_vm(misc.make_a_request({
        'uuid': vm_uuid,
        'type': type,
        'timeout': timeout
    }))


def destroy_vm(vm_uuid):
    # type: (str) -> None

    return VM_PLUGIN.destroy_vm(misc.make_a_request({
        'uuid': vm_uuid
    }))


def pause_vm(vm_uuid, timeout=5):
    # type: (str, int) -> None

    return VM_PLUGIN.pause_vm(misc.make_a_request({
        'uuid': vm_uuid,
        'timeout': timeout
    }))


def resume_vm(vm_uuid, timeout=5):
    # type: (str, int) -> None

    return VM_PLUGIN.resume_vm(misc.make_a_request({
        'uuid': vm_uuid,
        'timeout': timeout
    }))


def get_vm_xmlobject_from_virsh_dump(vm_uuid):
    # type: (str) -> xmlobject.XmlObject

    xml = bash.bash_o('virsh dumpxml %s' % vm_uuid)
    return xmlobject.loads(xml)


def online_change_cpumem(vm_uuid, cpu_num, mem_size):
    # type: (str, int, int) -> None

    return VM_PLUGIN.online_change_cpumem(misc.make_a_request({
        'vmUuid': vm_uuid,
        'cpuNum': cpu_num,
        'memorySize': mem_size
    }))

def online_increase_cpu(vm_uuid, cpu_num):
    # type: (str, int) -> None

    return VM_PLUGIN.online_increase_cpu(misc.make_a_request({
        'vmUuid': vm_uuid,
        'cpuNum': cpu_num
    }))


def online_increase_mem(vm_uuid, mem_size):
    # type: (str, long) -> None

    return VM_PLUGIN.online_increase_mem(misc.make_a_request({
        'vmUuid': vm_uuid,
        'memorySize': mem_size
    }))


def get_cpu_xml():
    # type: () -> None

    return VM_PLUGIN.get_cpu_xml(misc.make_a_request({}))


def compare_cpu_function(cpuXml):
    # type: (String) -> None

    return VM_PLUGIN.compare_cpu_function(misc.make_a_request({
        'cpuXml': cpuXml
    }))


@misc.return_jsonobject()
def get_vnc_port(vm_uuid):
    # type: (str) -> jsonobject

    return VM_PLUGIN.get_console_port(misc.make_a_request({
        'vmUuid': vm_uuid
    }))


@misc.return_jsonobject()
def vm_sync():
    # type: () -> jsonobject

    return VM_PLUGIN.vm_sync(misc.make_a_request({}))


@misc.return_jsonobject()
def attach_volume_to_vm(vm_uuid, vol_uuid, vol_path):
    # type: (str, str, str) -> (jsonobject, jsonobject)

    body = jsonobject.loads(jsonobject.dumps(volume_utils.attach_volume_body))
    body.volume.installPath = vol_path
    body.vmInstanceUuid = vm_uuid
    body.volume.volumeUuid = vol_uuid

    return VM_PLUGIN.attach_data_volume(misc.make_a_request(body.to_dict())), body.volume


@misc.return_jsonobject()
def attach_multi_queues_volume_to_vm(vm_uuid, vol_uuid, vol_path):
    # type: (str, str, str) -> (jsonobject, jsonobject)
    body = copy.deepcopy(volume_utils.attach_volume_body)
    body["volume"]["multiQueues"] = "1"
    body = jsonobject.loads(jsonobject.dumps(body))
    body.volume.installPath = vol_path
    body.vmInstanceUuid = vm_uuid
    body.volume.volumeUuid = vol_uuid

    return VM_PLUGIN.attach_data_volume(misc.make_a_request(body.to_dict())), body.volume


@misc.return_jsonobject()
def attach_iothreadpin_volume_to_vm(vm_uuid, vol_uuid, vol_path, iothread, pin):
    # type: (str, str, str) -> (jsonobject, jsonobject)
    body = copy.deepcopy(volume_utils.attach_volume_body)
    body["volume"]["ioThreadId"] = iothread
    body["volume"]["ioThreadPin"] = pin

    body = jsonobject.loads(jsonobject.dumps(body))
    body.volume.installPath = vol_path
    body.vmInstanceUuid = vm_uuid
    body.volume.volumeUuid = vol_uuid

    return VM_PLUGIN.attach_data_volume(misc.make_a_request(body.to_dict())), body.volume


@misc.return_jsonobject()
def attach_virtio_scsi_iothread_volume_to_vm(vm_uuid, vol_uuid, vol_path, iothread, pin):
    # type: (str, str, str) -> (jsonobject, jsonobject)
    body = copy.deepcopy(volume_utils.attach_volume_body)
    body["volume"]["ioThreadId"] = iothread
    body["volume"]["ioThreadPin"] = pin
    body["volume"]["useVirtioSCSI"] = True
    body = jsonobject.loads(jsonobject.dumps(body))
    body.volume.installPath = vol_path
    body.vmInstanceUuid = vm_uuid
    body.volume.volumeUuid = vol_uuid


    return VM_PLUGIN.attach_data_volume(misc.make_a_request(body.to_dict())), body.volume


@misc.return_jsonobject()
def attach_virtio_scsi_iothread_shareblock_volume_to_vm(vm_uuid, vol_uuid, vol_path, iothread, pin):
    # type: (str, str, str) -> (jsonobject, jsonobject)
    body = copy.deepcopy(volume_utils.attach_shareblock_volume_body)
    body["volume"]["ioThreadId"] = iothread
    body["volume"]["ioThreadPin"] = pin
    body["volume"]["useVirtioSCSI"] = True
    body["vmInstanceUuid"] = vm_uuid
    body["volume"]["resourceUuid"] = vol_uuid
    body["volume"]["installPath"] = vol_path
    body["volume"]["volumeUuid"] = vol_uuid
    body = jsonobject.loads(jsonobject.dumps(body))
    return VM_PLUGIN.attach_data_volume(misc.make_a_request(body.to_dict())), body.volume


@misc.return_jsonobject()
def attach_iothread_shareblock_volume_to_vm(vm_uuid, vol_uuid, vol_path, iothread, pin):
    # type: (str, str, str) -> (jsonobject, jsonobject)
    body = copy.deepcopy(volume_utils.attach_shareblock_volume_body)
    body["volume"]["ioThreadId"] = iothread
    body["volume"]["ioThreadPin"] = pin
    body["vmInstanceUuid"] = vm_uuid
    body["volume"]["resourceUuid"] = vol_uuid
    body["volume"]["installPath"] = vol_path
    body["volume"]["volumeUuid"] = vol_uuid
    body = jsonobject.loads(jsonobject.dumps(body))
    return VM_PLUGIN.attach_data_volume(misc.make_a_request(body.to_dict())), body.volume


@misc.return_jsonobject()
def attach_multi_queues_shareblock_volume_to_vm(vm_uuid, vol_uuid, vol_path):
    # type: (str, str, str) -> (jsonobject, jsonobject)
    body = copy.deepcopy(volume_utils.attach_shareblock_volume_body)
    body["volume"]["multiQueues"] = "1"
    body["vmInstanceUuid"] = vm_uuid
    body["volume"]["resourceUuid"] = vol_uuid
    body["volume"]["installPath"] = vol_path
    body["volume"]["volumeUuid"] = vol_uuid
    body = jsonobject.loads(jsonobject.dumps(body))
    return VM_PLUGIN.attach_data_volume(misc.make_a_request(body.to_dict())), body.volume


@misc.return_jsonobject()
def detach_volume_from_vm(vm_uuid, volume):
    # type: (str, jsonobject) -> jsonobject

    return VM_PLUGIN.detach_data_volume(misc.make_a_request({
        'volume': volume,
        'vmInstanceUuid': vm_uuid
    }))


@misc.return_jsonobject()
def check_volume(vm_uuid, volumes):
    # type: (str, list[jsonobject.JsonObject]) -> jsonobject

    return VM_PLUGIN.check_volume(misc.make_a_request({
        'uuid': vm_uuid,
        'volumes': volumes
    }))


@misc.return_jsonobject()
def take_snapshot(vm_uuid, vol_uuid, vol_path, snapshot_path):
    # type: (str, str, str, str) -> jsonobject.JsonObject

    cmd = jsonobject.from_dict(snapshot_utils.take_snapshot_cmd_body)
    cmd.vmUuid = vm_uuid
    cmd.volumeUuid = vol_uuid
    cmd.volume.installPath = vol_path
    cmd.volume.volumeUuid = vol_uuid
    cmd.installPath = snapshot_path
    cmd.volumeInstallPath = vol_path

    return VM_PLUGIN.take_volume_snapshot(misc.make_a_request(cmd.to_dict()))


@misc.return_jsonobject()
def merge_snapshots(vm_uuid, vol_path, snapshot_path):
    # type: (str, str, str) -> jsonobject.JsonObject

    cmd = jsonobject.from_dict(snapshot_utils.merge_snapshot_cmd_body)
    cmd.vmUuid = vm_uuid
    cmd.volume.installPath = vol_path
    cmd.srcPath = snapshot_path
    cmd.destPath = vol_path

    return VM_PLUGIN.merge_snapshot_to_volume(misc.make_a_request(cmd.to_dict()))


@misc.return_jsonobject()
def migrate_vm(vm_uuid, src_ip, dst_ip):
    # type: (str, str, str) -> jsonobject.JsonObject

    cmd = jsonobject.from_dict(migrate_vm_cmd_body)
    cmd.vmUuid = vm_uuid
    cmd.destHostIp = dst_ip
    cmd.srcHostIp = src_ip
    cmd.destHostManagementIp = dst_ip

    return VM_PLUGIN.migrate_vm(misc.make_a_request(cmd.to_dict()))

@misc.return_jsonobject()
def attach_vm_nic(cmd=None):
    # type: (str, str, str) -> jsonobject.JsonObject

    return VM_PLUGIN.attach_nic(misc.make_a_request(cmd.to_dict()))
@misc.return_jsonobject()
def detach_vm_nic(cmd=None):
    # type: (str, str, str) -> jsonobject.JsonObject

    return VM_PLUGIN.attach_nic(misc.make_a_request(cmd.to_dict()))


@misc.return_jsonobject()
def set_iothread_pin(vm_uuid, iothread, pin):
    # type: (str, int, str) -> jsonobject.JsonObject

    body = copy.deepcopy(volume_iothread_pin_body)
    body["vmUuid"] = vm_uuid
    body["ioThreadId"] = iothread
    body["pin"] = pin
    cmd = jsonobject.from_dict(body)
    return VM_PLUGIN.set_iothread_pin(misc.make_a_request(cmd.to_dict()))


@misc.return_jsonobject()
def del_iothread_pin(vm_uuid, iothread):
    # type: (str, int, str) -> jsonobject.JsonObject

    body = copy.deepcopy(volume_iothread_pin_body)
    body["vmUuid"] = vm_uuid
    body["ioThreadId"] = iothread
    cmd = jsonobject.from_dict(body)
    return VM_PLUGIN.del_iothread_pin(misc.make_a_request(cmd.to_dict()))


@misc.return_jsonobject()
def get_iothread_pin(vm_uuid, iothread, pin):
    # type: (str, int, str) -> jsonobject.JsonObject

    body = copy.deepcopy(volume_iothread_pin_body)
    body["vmUuid"] = vm_uuid
    cmd = jsonobject.from_dict(body)
    return VM_PLUGIN.get_iothread_pin(misc.make_a_request(cmd.to_dict()))


@misc.return_jsonobject()
def set_vm_scsi_controller(vm_uuid, iothread):
    # type: (str, int, str) -> jsonobject.JsonObject

    body = copy.deepcopy(volume_iothread_pin_body)
    body["vmUuid"] = vm_uuid
    body["ioThreadId"] = iothread
    cmd = jsonobject.from_dict(body)
    return VM_PLUGIN.set_scsi_controller(misc.make_a_request(cmd.to_dict()))


@misc.return_jsonobject()
def del_vm_scsi_controller(vm_uuid, iothread):
    # type: (str, int, str) -> jsonobject.JsonObject

    body = copy.deepcopy(volume_iothread_pin_body)
    body["vmUuid"] = vm_uuid
    body["ioThreadId"] = iothread
    cmd = jsonobject.from_dict(body)
    return VM_PLUGIN.del_scsi_controller(misc.make_a_request(cmd.to_dict()))


class VmPluginTestStub(pytest_utils.PytestExtension):
    def _destroy_vm(self, vm_uuid):
        destroy_vm(vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        assert not pid, 'vm[%s] vm still running' % vm_uuid

    def _create_vm(self):
        vm = create_startvm_body_jsonobject()
        create_vm(vm)
        vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        assert pid, 'cannot find pid of vm[%s]' % vm_uuid
        return vm_uuid, vm

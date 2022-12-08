import snapshot_utils
import volume_utils
from kvmagent.plugins.vm_plugin import VmPlugin
from kvmagent.test.utils import pytest_utils
from zstacklib.test.utils import env, misc
from zstacklib.utils import jsonobject, xmlobject, bash, linux

startVmCmdBody = {
    "vmInstanceUuid": "0b42630f37d8417480eced62ad89719f",
    "vmInternalId": 1,
    "vmName": "vm-for-ut",
    "imagePlatform": "Linux",
    "imageArchitecture": "x86_64",
    "memory": 67108864,  # 64M
    # "memory": 16384,  # 64M
    "maxMemory": 134217728,  # 128M
    "cpuNum": 1,
    "cpuSpeed": 0,
    "socketNum": 1,
    "cpuOnSocket": 1,
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
    "useNuma": True,
    "useBootMenu": True,
    "createPaused": False,
    "kvmHiddenState": False,
    "vmPortOff": False,
    "emulateHyperV": False,
    "additionalQmp": True,
    "isApplianceVm": False,
    "systemSerialNumber": "4f3e9046-776d-4095-8edd-909523ede46d",
    "bootMode": "Legacy",
    "fromForeignHypervisor": False,
    "machineType": "pc",
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
    "videoType": "cirrus",
    "spiceStreamingMode": "off",
    "VDIMonitorNumber": 1,
    "kvmHostAddons": {
        "qcow2Options": " -o cluster_size=2097152 "
    }
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

    return VM_PLUGIN.migrate_vm(misc.make_a_request(cmd.to_dict()))


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

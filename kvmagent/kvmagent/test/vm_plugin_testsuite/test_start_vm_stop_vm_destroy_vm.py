import pytest

from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils, volume_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from zstacklib.utils import linux
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmLifeCycle(TestCase, vm_utils.VmPluginTestStub):
    vm_uuid = ""

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH,
        vm_plugin.VmPlugin.KVM_STOP_VM_PATH,
        vm_plugin.VmPlugin.KVM_DESTROY_VM_PATH,
    ])
    @pytest.mark.run(order=1)
    @pytest_utils.ztest_decorater
    def test_start_vm(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm_utils.create_vm(vm)
        TestVmLifeCycle.vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(TestVmLifeCycle.vm_uuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % TestVmLifeCycle.vm_uuid)

    @pytest.mark.run(order=2)
    @pytest_utils.ztest_decorater
    def test_stop_vm(self):
        vm_utils.stop_vm(TestVmLifeCycle.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(TestVmLifeCycle.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % TestVmLifeCycle.vm_uuid)

    @pytest.mark.run(order=3)
    @pytest_utils.ztest_decorater
    def test_destroy_vm(self):
        vm_utils.destroy_vm(TestVmLifeCycle.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(TestVmLifeCycle.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % TestVmLifeCycle.vm_uuid)

    @pytest.mark.run(order=4)
    @pytest_utils.ztest_decorater
    def test_start_uefi_iso_with_data_volume(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.machineType = 'q35'
        vm.rootVolume.useVirtio = False

        vol_uuid, vol_path = volume_utils.create_empty_volume()

        iso = {
            "bootOrder": 0,
            "imageUuid": vol_uuid,
            "isEmpty": False,
            "deviceId": 0,
            "resourceUuid": vol_uuid,
            "path": vol_path,
            # "deviceAddress":
            #     {
            #         "bus": "0",
            #         "controller": "0",
            #         "type": "drive",
            #         "target": "0",
            #         "unit": "1"
            #     }
        }

        vm.cdRoms = [iso]

        vol_uuid1, vol_path1 = volume_utils.create_empty_volume()
        volume1 = {
            "resourceUuid": vol_uuid1,
            "primaryStorageType": "NFS",
            "volumeUuid": vol_uuid1,
            "installPath": vol_path1,
            "useVirtio": False,
            "format": "qcow2",
            "ioThreadId": 0,
            "cacheMode": "none",
            "useVirtioSCSI": False,
            "deviceType": "file",
            "deviceId": 3,
            "bootOrder": 0,
            "physicalBlockSize": 0,
            "shareable": False,
            "controllerIndex": 0,
            "wwn": "0x000f9d3e8f07f623",
            "type": "Data"
        }

        vol_uuid2, vol_path2 = volume_utils.create_empty_volume()
        volume2 = {
            "resourceUuid": vol_uuid2,
            "primaryStorageType": "NFS",
            "volumeUuid": vol_uuid2,
            "installPath": vol_path2,
            "useVirtio": False,
            "format": "qcow2",
            "ioThreadId": 0,
            "cacheMode": "none",
            "useVirtioSCSI": False,
            "deviceType": "file",
            "deviceId": 4,
            "bootOrder": 0,
            "physicalBlockSize": 0,
            "shareable": False,
            "controllerIndex": 0,
            "wwn": "0x000f9d3e8f07f623",
            "type": "Data"
        }

        vm.dataVolumes = [volume1, volume2]
        vm_utils.create_vm(vm)
        TestVmLifeCycle.vm_uuid = vm.vmInstanceUuid

        r, output = bash.bash_ro("virsh dumpxml %s" % vm.vmInstanceUuid)
        self.assertEqual(r, 0, "failed to dumpxml of vm %s" % vm.vmInstanceUuid)

        if 'virt-6.2' in output:
            sata_disk_list_alias = ['sata0']
        else:
            sata_disk_list_alias = ['sata0-0-0', 'sata0-0-0', 'sata0-0-4', 'sata0-0-5']

        for alias in sata_disk_list_alias:
            self.assertIn(alias, output, "failed to find %s in dumpxml output, vm xml dump %s" % (alias, output))

from kvmagent.test.utils.stub import *
from kvmagent.test.utils import vm_utils, network_utils, volume_utils, pytest_utils
from zstacklib.utils import linux, sizeunit, bash
from zstacklib.test.utils import misc
from kvmagent.plugins import vm_plugin
import pytest

init_kvmagent()
vm_utils.init_vm_plugin()


__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmPlugin(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_ATTACH_VOLUME,
        vm_plugin.VmPlugin.KVM_DETACH_VOLUME,
        vm_plugin.VmPlugin.KVM_VM_CHECK_VOLUME_PATH,
    ])


    @pytest_utils.ztest_decorater
    def test_attach_check_detach_volume(self):
        vm_uuid, vm = self._create_vm()

        vol_uuid, vol_path = volume_utils.create_empty_volume()
        _, vol = vm_utils.attach_volume_to_vm(vm_uuid, vol_uuid, vol_path)

        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, vol_path)
        self.assertIsNotNone(vol_xml)

        rsp = vm_utils.check_volume(vm_uuid, [vol])
        self.assertTrue(rsp.success)

        vm_utils.detach_volume_from_vm(vm_uuid, vol)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, vol_path)
        self.assertIsNone(vol_xml)

        rsp = vm_utils.check_volume(vm_uuid, [vol])
        self.assertFalse(rsp.success)

        self._destroy_vm(vm_uuid)

import pytest

from kvmagent.test.utils import vm_utils, network_utils, volume_utils, pytest_utils
from kvmagent.test.utils.stub import *
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestVolume(TestCase, vm_utils.VmPluginTestStub):
    vm_uuid = ""
    vol = None
    vol_path = ""

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest.mark.run(order=1)
    @pytest_utils.ztest_decorater
    def test_attach_volume_to_vm(self):
        TestVolume.vm_uuid, vm = self._create_vm()
        vol_uuid, vol_path = volume_utils.create_empty_volume()
        _, TestVolume.vol = vm_utils.attach_volume_to_vm(TestVolume.vm_uuid, vol_uuid, vol_path)

        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(TestVolume.vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, vol_path)
        self.assertIsNotNone(vol_xml)

    @pytest.mark.run(order=2)
    @pytest_utils.ztest_decorater
    def test_check_volume(self):
        rsp = vm_utils.check_volume(TestVolume.vm_uuid, [TestVolume.vol])
        self.assertTrue(rsp.success)

    @pytest.mark.run(order=3)
    @pytest_utils.ztest_decorater
    def test_detach_volume_from_vm(self):
        rsp = vm_utils.detach_volume_from_vm(TestVolume.vm_uuid, TestVolume.vol)
        self.assertTrue(rsp.success)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(TestVolume.vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, TestVolume.vol_path)
        self.assertIsNone(vol_xml)

        rsp = vm_utils.check_volume(TestVolume.vm_uuid, [TestVolume.vol])
        self.assertFalse(rsp.success)

        self._destroy_vm(TestVolume.vm_uuid)

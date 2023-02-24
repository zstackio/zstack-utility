import pytest

from kvmagent.test.utils import vm_utils, network_utils, volume_utils, pytest_utils
from kvmagent.test.utils.stub import *
from unittest import TestCase
from zstacklib.utils import linux
from zstacklib.utils import log

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}

logger = log.get_logger(__name__)


class TestVolumeWithMultiQueues(TestCase, vm_utils.VmPluginTestStub):
    vm_uuid = ""
    vol = None
    vol_path = ""
    vol_uuid = ""

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_attach_volume_to_vm(self):
        logger.info("run test: attach volume to vm with multiQueues")
        TestVolumeWithMultiQueues.vm_uuid, vm = self._create_vm()
        TestVolumeWithMultiQueues.vol_uuid, TestVolumeWithMultiQueues.vol_path = volume_utils.create_empty_volume()
        _, TestVolumeWithMultiQueues.vol = vm_utils.attach_multi_queues_volume_to_vm(TestVolumeWithMultiQueues.vm_uuid,
                                                                                     TestVolumeWithMultiQueues.vol_uuid,
                                                                                     TestVolumeWithMultiQueues.vol_path)

        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(TestVolumeWithMultiQueues.vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, TestVolumeWithMultiQueues.vol_path)
        self.assertIsNotNone(vol_xml, "Attached Vol xml is null")
        self.assertIsNotNone(vol_xml.driver, "Attached Vol's xml has no driver")
        self.assertIsNotNone(vol_xml.driver.queues_, "Attached Vol's driver has no multi queues")
        self.assertEqual(vol_xml.driver.queues_, "1",
                         "unexpected vol multi queues[1], actual is %s" % vol_xml.driver.queues_)

        logger.info("run test: check attached volume multiQueues")
        rsp = vm_utils.check_volume(TestVolumeWithMultiQueues.vm_uuid, [TestVolumeWithMultiQueues.vol])
        self.assertTrue(rsp.success)

        logger.info("run test: stop vm with multiQueues data volume")
        vm_utils.stop_vm(TestVolumeWithMultiQueues.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(TestVolumeWithMultiQueues.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % TestVolumeWithMultiQueues.vm_uuid)

        logger.info("run test: start vm with multiQueues data volume")
        vm = vm_utils.create_startvm_body_jsonobject_with_volume_multi_queues(TestVolumeWithMultiQueues.vol_uuid,
                                                                              TestVolumeWithMultiQueues.vol_path)
        vm_utils.create_vm(vm)
        TestVolumeWithMultiQueues.vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(TestVolumeWithMultiQueues.vm_uuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % TestVolumeWithMultiQueues.vm_uuid)

        logger.info("run test: check attached volume multiQueues after restart vm")
        rsp = vm_utils.check_volume(TestVolumeWithMultiQueues.vm_uuid, [TestVolumeWithMultiQueues.vol])
        self.assertTrue(rsp.success)

        logger.info("run test: detach data volume with multiQueues")
        rsp = vm_utils.detach_volume_from_vm(TestVolumeWithMultiQueues.vm_uuid, TestVolumeWithMultiQueues.vol)
        self.assertTrue(rsp.success)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(TestVolumeWithMultiQueues.vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, TestVolumeWithMultiQueues.vol_path)
        self.assertIsNone(vol_xml)

        logger.info("run test: check vm xml after detach data volume")
        rsp = vm_utils.check_volume(TestVolumeWithMultiQueues.vm_uuid, [TestVolumeWithMultiQueues.vol])
        self.assertFalse(rsp.success)

        logger.info("clean test env: destroy vm")
        vm_utils.destroy_vm(TestVolumeWithMultiQueues.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(TestVolumeWithMultiQueues.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % TestVolumeWithMultiQueues.vm_uuid)

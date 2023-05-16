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


class TestVolumeWithIoThreadPin(TestCase, vm_utils.VmPluginTestStub):
    vm_uuid = ""
    vol = None
    vol_path = ""
    vol_uuid = ""
    iothread_id = None
    iothread_pin = None

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest.mark.run(order=1)
    @pytest_utils.ztest_decorater
    def test_virtio_volum(self):
        logger.info("run test: attach volume to vm with iothreadpin")
        self.vm_uuid, vm = self._create_vm()
        self.vol_uuid, self.vol_path = volume_utils.create_empty_volume()
        self.iothread_id = 2
        self.iothread_pin = "0,1,0-1,^0"
        print("resource info: {} {}".format(self.vm_uuid, self.vol_uuid))
        _, self.vol = vm_utils.attach_iothreadpin_volume_to_vm(self.vm_uuid,
                                                               self.vol_uuid,
                                                               self.vol_path,
                                                               self.iothread_id,
                                                               self.iothread_pin)
        self.check_volume_iothread_pin(self.vm_uuid, self.vol_path, self.iothread_id)

        logger.info("run test: check attached volume iothreadpin")
        rsp = vm_utils.check_volume(self.vm_uuid, [self.vol])
        self.assertTrue(rsp.success)

        logger.info("run test: stop vm with iothreadpin data volume")
        vm_utils.stop_vm(self.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(self.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % self.vm_uuid)

        logger.info("run test: start vm with iothreadpin data volume")
        vm = vm_utils.create_startvm_body_jsonobject_with_volume_iothread(self.vol_uuid,
                                                                          self.vol_path,
                                                                          self.iothread_id,
                                                                          self.iothread_pin)
        vm_utils.create_vm(vm)
        self.vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(self.vm_uuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % self.vm_uuid)
        self.check_volume_iothread_pin(self.vm_uuid, self.vol_path, self.iothread_id)

        logger.info("run test: check attached volume iothreadpin after restart vm")
        rsp = vm_utils.check_volume(self.vm_uuid, [self.vol])
        self.assertTrue(rsp.success)

        logger.info("run test: check attached volume iothreadpin after set iothread pin changed")
        self.iothread_pin = "0"
        vm_utils.set_iothread_pin(self.vm_uuid, self.iothread_id, self.iothread_pin)

        logger.info("run test: detach data volume with iothreadpin")
        rsp = vm_utils.detach_volume_from_vm(self.vm_uuid, self.vol)
        self.assertTrue(rsp.success)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(self.vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, self.vol_path)
        self.assertIsNone(vol_xml)

        vm_utils.del_iothread_pin(self.vm_uuid, self.iothread_id)

        logger.info("run test: check vm xml after detach data volume")
        rsp = vm_utils.check_volume(self.vm_uuid, [self.vol])
        self.assertFalse(rsp.success)

        logger.info("clean test env: destroy vm")
        vm_utils.destroy_vm(self.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(self.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % self.vm_uuid)

    def check_volume_iothread_pin(self, vm_uuid, vol_path, iothread_id):
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, vol_path)
        self.assertIsNotNone(vol_xml, "Attached Vol xml is null")
        self.assertIsNotNone(vol_xml.driver, "Attached Vol's xml has no driver")
        self.assertIsNotNone(vol_xml.driver.iothread_, "Attached Vol's driver has no iothread config")
        self.assertEqual(vol_xml.driver.iothread_, str(iothread_id),
                         "unexpected vol iothreadid[%s], actual is %s" % (
                             str(iothread_id), vol_xml.driver.iothread_))

    def check_virtio_scsi_volume_config(self,  vm_uuid, vol_path, iothread_id):
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, vol_path)
        self.assertIsNotNone(vol_xml, "Attached Vol xml is null")
        controller = volume_utils.find_volume_controller_by_vol(xml, vol_xml.address.controller_)
        self.assertIsNotNone(controller, "Attached Virtio-SCSI Vol controller xml is null")
        self.assertIsNotNone(controller.driver, "Attached Virtio-SCSI Vol's controller xml has no driver")
        self.assertIsNotNone(controller.driver.iothread_,
                             "Attached Virtio-SCSI Vol's controller driver has no iothread config")
        self.assertEqual(controller.driver.iothread_, str(iothread_id),
                         "unexpected vol's controller iothreadid[%s], actual is %s" % (
                             str(iothread_id), controller.driver.iothread_))

    @pytest.mark.run(order=2)
    @pytest_utils.ztest_decorater
    def test_virtio_scsi_volume(self):
        logger.info("run test: create vm then attach virtio-scsi data volume with iothreadpin")
        self.vm_uuid, vm = self._create_vm()
        self.vol_uuid, self.vol_path = volume_utils.create_empty_volume()
        self.iothread_id = 2
        self.iothread_pin = "0,1,0-1,^0"
        _, self.vol = vm_utils.attach_virtio_scsi_iothread_volume_to_vm(self.vm_uuid,
                                                                        self.vol_uuid,
                                                                        self.vol_path,
                                                                        self.iothread_id,
                                                                        self.iothread_pin)
        self.check_virtio_scsi_volume_config(self.vm_uuid, self.vol_path, self.iothread_id)
        rsp = vm_utils.check_volume(self.vm_uuid, [self.vol])
        self.assertTrue(rsp.success)

        logger.info("run test:stop vm")
        vm_utils.stop_vm(self.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(self.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % self.vm_uuid)

        logger.info("run test: restart vm with virtio-scsi data volume that has iothreadpin")
        controller_index = "1"
        vm = vm_utils.create_startvm_body_jsonobject_with_virtio_scsi_volume_iothread(self.vol_uuid,
                                                                                      self.vol_path,
                                                                                      self.iothread_id,
                                                                                      self.iothread_pin,
                                                                                      controller_index)
        vm_utils.create_vm(vm)
        self.vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(self.vm_uuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % self.vm_uuid)
        self.check_virtio_scsi_volume_config(self.vm_uuid, self.vol_path, self.iothread_id)
        rsp = vm_utils.check_volume(self.vm_uuid, [self.vol])
        self.assertTrue(rsp.success)

        logger.info("run test: detach virtio-scsi data volume with iothreadpin")
        rsp = vm_utils.detach_volume_from_vm(self.vm_uuid, self.vol)
        self.assertTrue(rsp.success)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(self.vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, self.vol_path)
        self.assertIsNone(vol_xml)

        vm_utils.del_vm_scsi_controller(self.vm_uuid, self.iothread_id)
        vm_utils.del_iothread_pin(self.vm_uuid, self.iothread_id)

        logger.info("run test: check vm xml after detach data volume")
        rsp = vm_utils.check_volume(self.vm_uuid, [self.vol])
        self.assertFalse(rsp.success)

        logger.info("clean test env: destroy vm")
        vm_utils.destroy_vm(self.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(self.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % self.vm_uuid)

    @pytest.mark.run(order=3)
    @pytest_utils.ztest_decorater
    def test_virtio_and_virtio_scsi_data_volume_with_iothreadpin(self):
        virtio_vol_iothread_id = 1
        virtio_vol_iothread_pin = "0"
        virtio_vol_uuid, virtio_vol_path = volume_utils.create_empty_volume()

        virtio_scsi_vol_iothread_id = 2
        virtio_scsi_vol_iothread_pin = "1"
        virtio_scsi_vol_uuid, virtio_scsi_vol_path = volume_utils.create_empty_volume()

        vm_uuid, vm = self._create_vm()



        _, virtio_vol = vm_utils.attach_iothreadpin_volume_to_vm(vm_uuid,
                                                                 virtio_vol_uuid,
                                                                 virtio_vol_path,
                                                                 virtio_vol_iothread_id,
                                                                 virtio_vol_iothread_pin)
        _, virtio_scsi_vol = vm_utils.attach_virtio_scsi_iothread_volume_to_vm(vm_uuid,
                                                                               virtio_scsi_vol_uuid,
                                                                               virtio_scsi_vol_path,
                                                                               virtio_scsi_vol_iothread_id,
                                                                               virtio_scsi_vol_iothread_pin)

        rsp = vm_utils.check_volume(vm_uuid, [virtio_vol, virtio_scsi_vol])
        self.assertTrue(rsp.success)
        self.check_volume_iothread_pin(vm_uuid, virtio_vol_path, virtio_vol_iothread_id)
        self.check_virtio_scsi_volume_config(vm_uuid, virtio_scsi_vol_path, virtio_scsi_vol_iothread_id)

        vm_utils.stop_vm(vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % vm_uuid)

        controller_index = "2"
        virtio_vol_body, virtio_pin = vm_utils.build_virtio_vol_with_iothreadpin(virtio_vol_uuid, virtio_vol_path, virtio_vol_iothread_id, virtio_vol_iothread_pin)
        virtio_scsi_vol_body, virtio_scsi_pin = vm_utils.build_virtio_scsi_vol_body_with_iothreadpin(virtio_scsi_vol_uuid, virtio_scsi_vol_path, virtio_scsi_vol_iothread_id, virtio_scsi_vol_iothread_pin, controller_index)

        vm = vm_utils.create_vm_with_vols([virtio_vol_body, virtio_scsi_vol_body], [virtio_pin, virtio_scsi_pin])
        vm_utils.create_vm(vm)
        self.vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm_uuid)

        rsp = vm_utils.check_volume(vm_uuid, [virtio_vol, virtio_scsi_vol])
        self.assertTrue(rsp.success)
        self.check_volume_iothread_pin(vm_uuid, virtio_vol_path, virtio_vol_iothread_id)
        self.check_virtio_scsi_volume_config(vm_uuid, virtio_scsi_vol_path, virtio_scsi_vol_iothread_id)

        rsp = vm_utils.detach_volume_from_vm(vm_uuid, virtio_vol)
        self.assertTrue(rsp.success)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, virtio_vol_path)
        self.assertIsNone(vol_xml)

        rsp = vm_utils.detach_volume_from_vm(vm_uuid, virtio_scsi_vol)
        self.assertTrue(rsp.success)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, virtio_scsi_vol_path)
        self.assertIsNone(vol_xml)

        vm_utils.del_vm_scsi_controller(vm_uuid, virtio_scsi_vol_iothread_id)
        vm_utils.del_iothread_pin(vm_uuid, virtio_scsi_vol_iothread_id)
        vm_utils.del_iothread_pin(vm_uuid, virtio_vol_iothread_id)

        rsp = vm_utils.check_volume(vm_uuid, [virtio_vol, virtio_scsi_vol])
        self.assertFalse(rsp.success)

        vm_utils.destroy_vm(vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % vm_uuid)


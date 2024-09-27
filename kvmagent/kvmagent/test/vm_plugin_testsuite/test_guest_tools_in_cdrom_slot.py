import os
import pytest
import shutil
import tempfile
import time

from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, volume_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from zstacklib.utils import jsonobject, xmlobject
from unittest import TestCase

init_kvmagent()
plugin = vm_utils.init_vm_plugin()
context = {}

__ENV_SETUP__ = {
    'self': {}
}

def error_message(message):
    return '%s, context: %s' % (message, context)

class TestGuestToolsInRandomCdromSlot(TestCase, vm_utils.VmPluginTestStub):

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.ATTACH_GUEST_TOOLS_ISO_TO_VM_PATH,
        vm_plugin.VmPlugin.DETACH_GUEST_TOOLS_ISO_FROM_VM_PATH,
    ])

    @pytest.mark.run(order=1)
    @pytest_utils.ztest_decorater
    def test_detach_guest_tools(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm_uuid = vm.vmInstanceUuid

        cd_rom0 = {
            "deviceId": 0,
            "isEmpty": True,
            "bootOrder": 0,
            "resourceUuid": "896554f185214da49648a7eef97c8674"
        }
        vm.cdRoms.append(jsonobject.loads(jsonobject.dumps(cd_rom0)))

        cd_rom1 = {
            "deviceId": 1,
            "isEmpty": True,
            "bootOrder": 0,
            "resourceUuid": "04ed9863b6c148fea9b38ba71b9076b6"
        }
        vm.cdRoms.append(jsonobject.loads(jsonobject.dumps(cd_rom1)))

        cd_rom2 = {
            "deviceId": 2,
            "isEmpty": True,
            "bootOrder": 0,
            "resourceUuid": "04ed9863b6c148fea9b38ba71b9076b6"
        }
        vm.cdRoms.append(jsonobject.loads(jsonobject.dumps(cd_rom2)))

        vm_utils.create_vm(vm)

        # assume vm has 3 cdroms (every cdrom slots are empty)
        vm_instance = vm_plugin.get_vm_by_uuid_no_retry(vm_uuid) # type: vm_plugin.Vm
        self.assertIsNotNone(vm_instance)
        context['vm_instance'] = vm_instance.domain_xml

        self.assertIsNotNone(vm_instance)
        domain_xmlobject = xmlobject.loads(vm_instance.domain_xml)
        self.assertIsNotNone(domain_xmlobject)
        self.assertIsNotNone(domain_xmlobject.devices)
        self.assertTrue(type(domain_xmlobject.devices.disk) == list)

        disks = domain_xmlobject.devices.disk # type: list
        cdrom_disks = filter(lambda disk: disk.device_ == 'cdrom', disks)
        self.assertEqual(3, len(cdrom_disks))
        self.assertFalse(
                cdrom_disks[0].hasattr('source') and cdrom_disks[0].source.hasattr('file_'),
                error_message("expect cdrom 0 is empty"))
        self.assertFalse(
                cdrom_disks[1].hasattr('source') and cdrom_disks[1].source.hasattr('file_'),
                error_message("expect cdrom 1 is empty"))
        self.assertFalse(
                cdrom_disks[2].hasattr('source') and cdrom_disks[1].source.hasattr('file_'),
                error_message("expect cdrom 2 is empty"))

        # generate a empty iso file to mock linux guest tools
        # create temp file
        temp_dir = tempfile.mkdtemp()
        os.mkdir(os.path.join(temp_dir, 'empty_dir'))

        # generate iso file, and rename it to guest tools iso file
        # Note: libvirt do not support raw type file as ISO file, and system do not have genisoimage command
        # so we need to generate iso file by python code
        arr = volume_utils.generate_empty_iso_array()
        with open(os.path.join(temp_dir, 'empty.iso'), 'wb') as f:
            arr.tofile(f)
        os.makedirs(vm_plugin.GUEST_TOOLS_DIRECTORY)
        os.rename(os.path.join(temp_dir, 'empty.iso'), vm_plugin.GUEST_TOOLS_ISO_LINUX_PATH)
        shutil.copy(vm_plugin.GUEST_TOOLS_ISO_LINUX_PATH, vm_plugin.GUEST_TOOLS_ISO_PATH)
        context['iso_size'] = os.path.getsize(vm_plugin.GUEST_TOOLS_ISO_LINUX_PATH)

        # just sleep 5s for vm booting
        time.sleep(5)

        def test_attach(request_map):
            context['vm_instance_after_attach'] = None
            context['vm_instance_after_detach'] = None
            context['request_map'] = request_map

            device_id = request_map['cdromDeviceId'] # type: int
            rsp_json = plugin.attach_guest_tools_iso_to_vm(misc.make_a_request(request_map))
            rsp = jsonobject.loads(rsp_json)
            self.assertTrue(rsp.success, error_message("failed to attach guest tools iso to vm: %s" % rsp.error))

            time.sleep(1)
            vm_instance.refresh()
            context['vm_instance_after_attach'] = vm_instance.domain_xml

            self.assertIsNotNone(vm_instance)
            domain_xmlobject = xmlobject.loads(vm_instance.domain_xml)
            self.assertIsNotNone(domain_xmlobject)
            self.assertIsNotNone(domain_xmlobject.devices)
            self.assertTrue(type(domain_xmlobject.devices.disk) == list)
            disks = domain_xmlobject.devices.disk # type: list
            cdrom_disks = filter(lambda disk: disk.device_ == 'cdrom', disks)
            self.assertEqual(3, len(cdrom_disks))
            self.assertTrue(
                    cdrom_disks[device_id].hasattr('source') and cdrom_disks[device_id].source.hasattr('file_'),
                    error_message("expect cdrom %d is not empty" % device_id))

            for id, item in enumerate(cdrom_disks):
                if id != device_id:
                    self.assertFalse(
                            item.hasattr('source') and item.source.hasattr('file_'),
                            error_message("expect cdrom %d is empty" % id))
        
        def test_detach():
            rsp_json = plugin.detach_guest_tools_iso_from_vm(misc.make_a_request({
                'vmInstanceUuid': vm_uuid
            }))
            rsp = jsonobject.loads(rsp_json)
            self.assertTrue(rsp.success, error_message("failed to detach guest tools iso from vm: %s" % rsp.error))

            time.sleep(1)
            vm_instance.refresh()
            context['vm_instance_after_detach'] = vm_instance.domain_xml

            self.assertIsNotNone(vm_instance)
            domain_xmlobject = xmlobject.loads(vm_instance.domain_xml)
            self.assertIsNotNone(domain_xmlobject)
            self.assertIsNotNone(domain_xmlobject.devices)
            self.assertTrue(type(domain_xmlobject.devices.disk) == list)

            disks = domain_xmlobject.devices.disk # type: list
            cdrom_disks = filter(lambda disk: disk.device_ == 'cdrom', disks)
            self.assertEqual(3, len(cdrom_disks))
            self.assertFalse(
                    cdrom_disks[0].hasattr('source') and cdrom_disks[0].source.hasattr('file_'),
                    error_message("expect cdrom 0 is empty"))
            self.assertFalse(
                    cdrom_disks[1].hasattr('source') and cdrom_disks[1].source.hasattr('file_'),
                    error_message("expect cdrom 1 is empty"))
            self.assertFalse(
                    cdrom_disks[2].hasattr('source') and cdrom_disks[2].source.hasattr('file_'),
                    error_message("expect cdrom 2 is empty"))

        # test 1: platform=Windows
        test_attach({
            'vmInstanceUuid': vm_uuid,
            'needTempDisk': True,
            'cdromDeviceId': 0,
            'platform': 'Windows'
        })
        test_detach()

        test_attach({
            'vmInstanceUuid': vm_uuid,
            'needTempDisk': True,
            'cdromDeviceId': 1,
            'platform': 'Windows'
        })
        test_detach()

        # test 2: platform=Linux
        test_attach({
            'vmInstanceUuid': vm_uuid,
            'needTempDisk': False,
            'cdromDeviceId': 0,
            'platform': 'Linux'
        })
        test_detach()

        test_attach({
            'vmInstanceUuid': vm_uuid,
            'needTempDisk': False,
            'cdromDeviceId': 2,
            'platform': 'Linux'
        })
        test_detach()

        # test 3: detach twice
        test_detach()

if __name__ == "__main__":
    unittest.main()

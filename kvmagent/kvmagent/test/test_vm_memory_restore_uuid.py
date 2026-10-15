import unittest
import xml.etree.ElementTree as etree

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import uuidhelper, xmlobject


class TestMemoryRestoreUuid(unittest.TestCase):
    SAVED_UUID = '66fe4db0-01f0-4831-abaa-6d183a67cfa2'
    NEW_UUID = '0126c027-1e50-4503-a974-73ed95302079'

    def setUp(self):
        self.original_decorator = vm_plugin.LibvirtAutoReconnect
        self.calls = []
        self.vm_id = '0300020002000346'
        self.saved_xml = '<domain><name>%s</name><uuid>%s</uuid></domain>' % (self.vm_id, self.SAVED_UUID)
        self.read_error = None
        self.restore_error = None
        test = self

        class Connection(object):
            def saveImageGetXMLDesc(self, path, flags):
                test.calls.append(('read', path, flags))
                if test.read_error:
                    raise test.read_error
                return test.saved_xml

            def restoreFlags(self, path, xml):
                test.calls.append(('restore', path, xml))
                if test.restore_error:
                    raise test.restore_error

        connection = Connection()
        vm_plugin.LibvirtAutoReconnect = lambda func: lambda: func(connection)

    def tearDown(self):
        vm_plugin.LibvirtAutoReconnect = self.original_decorator

    def make_vm(self, vm_id=None, domain_uuid=None):
        vm = vm_plugin.Vm()
        vm.uuid = vm_id or self.vm_id
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
          <name>%s</name><uuid>%s</uuid><memory>1048576</memory>
          <devices><disk type="block"><source dev="/dev/current/restored-root"/></disk></devices>
          <qemu:commandline><qemu:arg value="-no-user-config"/></qemu:commandline>
        </domain>''' % (vm.uuid, domain_uuid or self.NEW_UUID)
        vm.domain_xmlobject = xmlobject.loads(vm.domain_xml)
        return vm

    def test_existing_short_id_snapshot_keeps_saved_uuid_and_current_devices(self):
        vm = self.make_vm()
        before = etree.fromstring(vm.domain_xml)
        vm.restore('/tmp/existing-memory-save')
        self.assertEqual(self.calls[0], ('read', '/tmp/existing-memory-save', 0))
        restored = etree.fromstring(self.calls[1][2])
        self.assertEqual(restored.findtext('uuid'), self.SAVED_UUID)
        self.assertEqual(vm.domain_xmlobject.uuid.text_, self.SAVED_UUID)
        before.remove(before.find('uuid'))
        restored.remove(restored.find('uuid'))
        self.assertEqual(etree.tostring(before), etree.tostring(restored))

    def test_32_character_vm_id_is_compatible(self):
        vm_id = '66fe4db001f04831abaa6d183a67cfa2'
        self.saved_xml = '<domain><name>%s</name><uuid>%s</uuid></domain>' % (vm_id, self.SAVED_UUID)
        vm = self.make_vm(vm_id, uuidhelper.get_full_uuid(vm_id))
        vm.restore('/tmp/standard-memory-save')
        self.assertEqual(etree.fromstring(self.calls[1][2]).findtext('uuid'), self.SAVED_UUID)

    def test_multiple_new_xml_uuids_restore_the_same_old_snapshot(self):
        for unused in range(2):
            vm = self.make_vm(domain_uuid=uuidhelper.get_full_uuid(self.vm_id))
            vm.restore('/tmp/existing-memory-save')
            self.assertEqual(etree.fromstring(self.calls[-1][2]).findtext('uuid'), self.SAVED_UUID)

    def test_snapshot_of_another_vm_is_rejected_before_restore(self):
        self.saved_xml = self.saved_xml.replace(self.vm_id, '0300020002000999')
        self.assertRaises(kvmagent.KvmError, self.make_vm().restore, '/tmp/wrong-vm')
        self.assertEqual(len(self.calls), 1)

    def test_missing_saved_uuid_is_rejected_before_restore(self):
        self.saved_xml = '<domain><name>%s</name></domain>' % self.vm_id
        self.assertRaises(kvmagent.KvmError, self.make_vm().restore, '/tmp/missing-uuid')
        self.assertEqual(len(self.calls), 1)

    def test_saved_image_read_failure_propagates_without_restore(self):
        self.read_error = RuntimeError('save image unavailable')
        self.assertRaises(RuntimeError, self.make_vm().restore, '/tmp/missing-save')
        self.assertEqual(len(self.calls), 1)

    def test_libvirt_restore_failure_is_not_hidden(self):
        self.restore_error = RuntimeError('restore failed')
        self.assertRaises(RuntimeError, self.make_vm().restore, '/tmp/memory-save')
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()

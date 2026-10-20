import ast
import copy
import os
import unittest
from xml.etree import ElementTree as etree
from unittest.mock import Mock


class TestMemorySnapshotXmlPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vm_plugin_path = os.environ.get('VM_PLUGIN_SOURCE') or os.path.join(
            os.path.dirname(__file__), '..', 'plugins', 'vm_plugin.py')
        with open(vm_plugin_path, 'r') as f:
            cls.source = f.read()
        cls.tree = ast.parse(cls.source)
        cls.vm = cls._load_vm_xml_patch_helpers()

    @classmethod
    def _load_vm_xml_patch_helpers(cls):
        functions = {}
        for node in ast.walk(cls.tree):
            if isinstance(node, ast.ClassDef) and node.name == 'Vm':
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name in (
                            'restore', '_disk_identity', '_disk_matches',
                            '_reorder_disk_xml_by_saved_image',
                            '_patch_disk_xml_order_from_saved_image'):
                        copied = copy.deepcopy(item)
                        functions[item.name] = copied
        cls.conn = Mock()
        cls.logger = Mock()
        namespace = {
            'etree': etree,
            'logger': cls.logger,
            'LibvirtAutoReconnect': lambda fn: lambda *args: fn(cls.conn, *args),
        }
        vm_class = ast.ClassDef(name='Vm', bases=[], keywords=[],
                                body=list(functions.values()), decorator_list=[])
        module = ast.Module(body=[vm_class], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, '<vm_plugin_xml_patch_helpers>', 'exec'), namespace)
        return namespace['Vm']

    def setUp(self):
        self.conn.reset_mock(side_effect=True)
        self.logger.reset_mock()

    @staticmethod
    def xml(disks):
        return '<domain><name>test-vm</name><devices>' + ''.join(disks) + '</devices></domain>'

    @staticmethod
    def disk(device, target, serial=None, bus='scsi'):
        return ("<disk device='%s'><target dev='%s' bus='%s'/>%s</disk>" %
                (device, target, bus, '<serial>%s</serial>' % serial if serial else ''))

    def restore(self, current, saved):
        self.conn.saveImageGetXMLDesc.return_value = saved
        expected = [d.get('device') for d in etree.fromstring(saved).findall('devices/disk')]

        def restore_flags(path, xml):
            actual = [d.get('device') for d in etree.fromstring(xml).findall('devices/disk')]
            self.assertEqual(expected, actual, 'Target disk device disk does not match source cdrom')

        self.conn.restoreFlags.side_effect = restore_flags
        vm = self.vm()
        vm.domain_xml = current
        vm._patch_cpu_xml_from_saved_image = Mock()
        vm.restore('/snapshot')
        self.conn.restoreFlags.assert_called_once_with('/snapshot', vm.domain_xml)
        self.conn.defineXML.assert_called_once_with(vm.domain_xml)
        return vm.domain_xml

    def test_restore_calls_disk_order_patch_before_libvirt_restore(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == 'Vm':
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == 'restore':
                        calls = []
                        for call_node in ast.walk(item):
                            if isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Attribute):
                                calls.append((call_node.func.attr, call_node.lineno))
                        patch_lines = [line for name, line in calls if name == '_patch_disk_xml_order_from_saved_image']
                        restore_lines = [line for name, line in calls if name == 'restoreFlags']
                        self.assertTrue(patch_lines, 'restore must patch disk XML order from saved image')
                        self.assertTrue(restore_lines, 'restore must call libvirt restoreFlags')
                        self.assertLess(min(patch_lines), min(restore_lines),
                                        'disk XML order must be patched before restoreFlags')
                        return

        self.fail('Vm.restore not found')

    def test_reorder_disk_xml_by_saved_image_keeps_hotplug_order(self):
        current_xml = """
<domain>
  <devices>
    <disk type='file' device='disk'>
      <target dev='vda' bus='virtio'/>
      <serial>root-volume</serial>
    </disk>
    <disk type='block' device='disk'>
      <target dev='sdb' bus='scsi'/>
      <serial>hotplug-volume</serial>
    </disk>
    <interface type='bridge'/>
    <disk type='file' device='cdrom'>
      <target dev='hda' bus='ide'/>
      <serial>cdrom-0</serial>
    </disk>
  </devices>
</domain>
"""
        saved_xml = """
<domain>
  <devices>
    <disk type='file' device='disk'>
      <target dev='vda' bus='virtio'/>
      <serial>root-volume</serial>
    </disk>
    <disk type='file' device='cdrom'>
      <target dev='hda' bus='ide'/>
      <serial>cdrom-0</serial>
    </disk>
    <disk type='block' device='disk'>
      <target dev='sdb' bus='scsi'/>
      <serial>hotplug-volume</serial>
    </disk>
  </devices>
</domain>
"""

        reordered_xml = self.vm._reorder_disk_xml_by_saved_image(current_xml, saved_xml)
        disks = etree.fromstring(reordered_xml).find('devices').findall('disk')

        self.assertEqual(['root-volume', 'cdrom-0', 'hotplug-volume'],
                         [disk.findtext('serial') for disk in disks])
        self.assertEqual(['disk', 'cdrom', 'disk'],
                         [disk.get('device') for disk in disks])

    def test_restore_hotplug_disk_order(self):
        root = self.disk('disk', 'vda', 'root', 'virtio')
        data = self.disk('disk', 'sdb', 'data')
        cdrom = self.disk('cdrom', 'hda', 'cdrom', 'ide')
        self.restore(self.xml([root, data, cdrom]), self.xml([root, cdrom, data]))

    def test_restore_cdrom_without_saved_serial(self):
        root = self.disk('disk', 'vda', 'root', 'virtio')
        data = self.disk('disk', 'sdb', 'data')
        current_cdrom = self.disk('cdrom', 'hda', 'cdrom', 'ide')
        saved_cdrom = self.disk('cdrom', 'hda', bus='ide')
        self.restore(self.xml([root, data, current_cdrom]), self.xml([root, saved_cdrom, data]))

    def test_multiple_disks_and_cdroms_keep_device_contents(self):
        disks = [self.disk('disk', 'vda', 'root'), self.disk('disk', 'sdb', 'data1'),
                 self.disk('disk', 'sdc', 'data2'), self.disk('cdrom', 'sdd', 'cd1'),
                 self.disk('cdrom', 'sde', 'cd2')]
        current = self.xml(disks)
        saved = self.xml([disks[i] for i in [0, 3, 1, 4, 2]])
        patched = self.vm._reorder_disk_xml_by_saved_image(current, saved)
        self.assertEqual([etree.tostring(d) for d in etree.fromstring(saved).findall('devices/disk')],
                         [etree.tostring(d) for d in etree.fromstring(patched).findall('devices/disk')])

    def test_disk_without_serial_matches_source(self):
        root = "<disk device='disk'><source file='/root'/></disk>"
        data = "<disk device='disk'><source dev='/data'/></disk>"
        cdrom = "<disk device='cdrom'><source file='/iso'/></disk>"
        saved = self.xml([root, cdrom, data])
        patched = self.vm._reorder_disk_xml_by_saved_image(self.xml([root, data, cdrom]), saved)
        self.assertEqual([d.get('device') for d in etree.fromstring(saved).findall('devices/disk')],
                         [d.get('device') for d in etree.fromstring(patched).findall('devices/disk')])

    def test_different_nonempty_serials_do_not_match_by_target(self):
        current = self.xml([self.disk('disk', 'vda', 'root'), self.disk('disk', 'sdb', 'new')])
        saved = self.xml([self.disk('disk', 'sdb', 'old'), self.disk('disk', 'vda', 'other-root')])
        self.assertEqual(current, self.vm._reorder_disk_xml_by_saved_image(current, saved))

    def test_unmatched_disks_keep_relative_order(self):
        root = self.disk('disk', 'vda', 'root')
        extra1 = self.disk('disk', 'sdb', 'extra1')
        extra2 = self.disk('disk', 'sdc', 'extra2')
        cdrom = self.disk('cdrom', 'sdd', 'cdrom')
        patched = self.vm._reorder_disk_xml_by_saved_image(self.xml([root, extra1, extra2, cdrom]),
                                                         self.xml([root, cdrom]))
        self.assertEqual(['root', 'cdrom', 'extra1', 'extra2'],
                         [d.findtext('serial') for d in etree.fromstring(patched).findall('devices/disk')])

    def test_read_error_keeps_original_xml_and_restore_error(self):
        vm = self.vm()
        vm.domain_xml = self.xml([self.disk('disk', 'vda', 'root')])
        original = vm.domain_xml
        vm._patch_cpu_xml_from_saved_image = Mock()
        self.conn.saveImageGetXMLDesc.side_effect = RuntimeError('read failed')
        self.conn.restoreFlags.side_effect = RuntimeError('original restore error')
        with self.assertRaisesRegex(RuntimeError, 'original restore error'):
            vm.restore('/snapshot')
        self.assertEqual(original, vm.domain_xml)
        self.conn.defineXML.assert_called_once_with(original)

    def test_malformed_saved_xml_keeps_original(self):
        vm = self.vm()
        vm.domain_xml = self.xml([self.disk('disk', 'vda', 'root')])
        original = vm.domain_xml
        self.conn.saveImageGetXMLDesc.return_value = '<domain>'
        vm._patch_disk_xml_order_from_saved_image('/snapshot')
        self.assertEqual(original, vm.domain_xml)

    def test_missing_devices_and_single_disk_are_unchanged(self):
        for current in ['<domain/>', self.xml([self.disk('disk', 'vda', 'root')])]:
            self.assertEqual(current, self.vm._reorder_disk_xml_by_saved_image(current, '<domain/>'))


if __name__ == '__main__':
    unittest.main()

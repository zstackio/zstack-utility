import ast
import copy
import os
import unittest
from xml.etree import ElementTree as etree
from unittest.mock import Mock


class TestMemorySnapshotCpuXmlPatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = os.environ.get('VM_PLUGIN_SOURCE') or os.path.join(
            os.path.dirname(__file__), '..', 'plugins', 'vm_plugin.py')
        with open(source_path) as source:
            tree = ast.parse(source.read())
        methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'Vm':
                methods = [copy.deepcopy(method) for method in node.body
                           if isinstance(method, ast.FunctionDef) and method.name in
                           ('restore', '_patch_cpu_xml_from_saved_image')]
                break
        cls.conn = Mock()
        cls.logger = Mock()
        namespace = {
            'etree': etree,
            'logger': cls.logger,
            'LibvirtAutoReconnect': lambda fn: lambda *args: fn(cls.conn, *args),
        }
        vm_class = ast.ClassDef(name='Vm', bases=[], keywords=[],
                                body=methods, decorator_list=[])
        module = ast.Module(body=[vm_class], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, '<vm_plugin_cpu_xml_patch>', 'exec'), namespace)
        cls.vm = namespace['Vm']

    def setUp(self):
        self.conn.reset_mock(side_effect=True)
        self.logger.reset_mock()

    @staticmethod
    def xml(cpu):
        return ('<domain><name>snapshot-vm</name><uuid>vm-uuid</uuid>' + cpu +
                "<devices><disk device='disk'><source file='/current-volume'/></disk>"
                '</devices></domain>')

    @staticmethod
    def saved_cpu():
        return ("<cpu mode='custom' check='full'><model>Broadwell</model>"
                "<feature policy='require' name='ssse3'/></cpu>")

    def restore(self, current_cpu, saved_cpu):
        current_xml = self.xml(current_cpu)
        saved_xml = self.xml(saved_cpu)
        self.conn.saveImageGetXMLDesc.return_value = saved_xml

        def restore_flags(path, xml):
            expected = etree.fromstring(saved_xml).find('cpu')
            actual = etree.fromstring(xml).find('cpu')
            self.assertEqual(expected.get('mode') or 'custom', actual.get('mode') or 'custom')
            self.assertEqual(expected.get('check') or 'none', actual.get('check') or 'none',
                             'Target CPU check none does not match source full')
            self.assertEqual(expected.findtext('model'), actual.findtext('model'))
            self.assertEqual([feature.attrib for feature in expected.findall('feature')],
                             [feature.attrib for feature in actual.findall('feature')])

        self.conn.restoreFlags.side_effect = restore_flags
        vm = self.vm()
        vm.domain_xml = current_xml
        vm._patch_disk_xml_order_from_saved_image = Mock()
        vm.restore('/snapshot')
        self.conn.defineXML.assert_called_once_with(vm.domain_xml)
        self.conn.restoreFlags.assert_called_once_with('/snapshot', vm.domain_xml)
        self.assertEqual(['saveImageGetXMLDesc', 'defineXML', 'restoreFlags'],
                         [call[0] for call in self.conn.mock_calls])
        self.assertEqual('/current-volume',
                         etree.fromstring(vm.domain_xml).find('devices/disk/source').get('file'))
        return etree.fromstring(vm.domain_xml).find('cpu')

    def test_restore_implicit_custom_cpu_check(self):
        cpu = self.restore('<cpu/>', self.saved_cpu())
        self.assertEqual('full', cpu.get('check'))

    def test_restore_explicit_custom_cpu_check(self):
        self.restore("<cpu mode='custom' check='none'><model>Broadwell</model></cpu>",
                     self.saved_cpu())

    def test_restore_custom_model_and_features(self):
        self.restore("<cpu mode='custom'><model>Broadwell</model>"
                     "<feature policy='optional' name='ssse3'/></cpu>", self.saved_cpu())

    def test_restore_host_model_still_uses_saved_cpu(self):
        self.restore("<cpu mode='host-model'/>", self.saved_cpu())

    def test_saved_topology_and_numa_take_precedence(self):
        current = ("<cpu mode='custom'><topology sockets='1' cores='2' threads='1'/>"
                   "<numa><cell id='0' cpus='0-1' memory='1024'/></numa></cpu>")
        saved = self.saved_cpu().replace('</cpu>',
                    "<topology sockets='2' cores='1' threads='1'/>"
                    "<numa><cell id='0' cpus='0-1' memory='2048'/></numa></cpu>")
        cpu = self.restore(current, saved)
        self.assertEqual('2', cpu.find('topology').get('sockets'))
        self.assertEqual('2048', cpu.find('numa/cell').get('memory'))

    def test_agent_topology_and_numa_are_preserved_when_missing_in_saved_cpu(self):
        current = ("<cpu mode='custom'><topology sockets='1' cores='2' threads='1'/>"
                   "<numa><cell id='0' cpus='0-1' memory='1024'/></numa></cpu>")
        cpu = self.restore(current, self.saved_cpu())
        self.assertEqual('2', cpu.find('topology').get('cores'))
        self.assertEqual('1024', cpu.find('numa/cell').get('memory'))

    def test_other_cpu_modes_are_unchanged(self):
        for mode in ('host-passthrough', 'maximum'):
            vm = self.vm()
            vm.domain_xml = self.xml("<cpu mode='%s'/>" % mode)
            original = vm.domain_xml
            vm._patch_cpu_xml_from_saved_image('/snapshot')
            self.assertEqual(original, vm.domain_xml)
        self.conn.saveImageGetXMLDesc.assert_not_called()

    def test_custom_cpu_does_not_use_incompatible_saved_mode_or_weaker_check(self):
        for saved in ("<cpu mode='host-passthrough'/>",
                      "<cpu mode='custom' check='none'/>",
                      "<cpu mode='custom' check='partial'/>", '<cpu/>'):
            vm = self.vm()
            vm.domain_xml = self.xml("<cpu mode='custom' check='full'/>")
            original = vm.domain_xml
            self.conn.saveImageGetXMLDesc.return_value = self.xml(saved)
            vm._patch_cpu_xml_from_saved_image('/snapshot')
            self.assertEqual(original, vm.domain_xml)

    def test_missing_or_malformed_saved_cpu_keeps_original(self):
        for saved in (self.xml(''), '<domain>'):
            vm = self.vm()
            vm.domain_xml = self.xml("<cpu mode='host-model'/>")
            original = vm.domain_xml
            self.conn.saveImageGetXMLDesc.return_value = saved
            vm._patch_cpu_xml_from_saved_image('/snapshot')
            self.assertEqual(original, vm.domain_xml)

    def test_missing_current_cpu_keeps_original(self):
        vm = self.vm()
        vm.domain_xml = self.xml('')
        original = vm.domain_xml
        vm._patch_cpu_xml_from_saved_image('/snapshot')
        self.assertEqual(original, vm.domain_xml)
        self.conn.saveImageGetXMLDesc.assert_not_called()

    def test_saved_xml_read_failure_preserves_restore_error(self):
        vm = self.vm()
        vm.domain_xml = self.xml("<cpu mode='host-model'/>")
        vm._patch_disk_xml_order_from_saved_image = Mock()
        original = vm.domain_xml
        self.conn.saveImageGetXMLDesc.side_effect = RuntimeError('read failed')
        self.conn.restoreFlags.side_effect = RuntimeError('original restore error')
        with self.assertRaisesRegex(RuntimeError, 'original restore error'):
            vm.restore('/snapshot')
        self.assertEqual(original, vm.domain_xml)
        self.conn.defineXML.assert_called_once_with(original)


if __name__ == '__main__':
    unittest.main()

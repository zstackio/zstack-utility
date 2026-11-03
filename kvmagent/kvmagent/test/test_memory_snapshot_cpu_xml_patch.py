import ast
import copy
import os
import types
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
                           ('restore', '_patch_cpu_xml_from_saved_image', '_patch_xml_from_saved_image',
                            '_patch_cpu_from_saved_image', '_patch_vcpus_from_saved_image',
                            '_patch_memory_devices_from_saved_image')]
                break
        cls.conn = Mock()
        cls.logger = Mock()
        namespace = {
            'etree': etree,
            'logger': cls.logger,
            'kvmagent': types.SimpleNamespace(KvmError=RuntimeError),
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
            self.conn.saveImageGetXMLDesc.return_value = self.xml("<cpu mode='%s'/>" % mode)
            vm._patch_xml_from_saved_image('/snapshot')
            self.assertEqual(original, vm.domain_xml)

    def test_custom_cpu_does_not_use_incompatible_saved_mode_or_weaker_check(self):
        for saved in ("<cpu mode='host-passthrough'/>",
                      "<cpu mode='custom' check='none'/>",
                      "<cpu mode='custom' check='partial'/>", '<cpu/>'):
            vm = self.vm()
            vm.domain_xml = self.xml("<cpu mode='custom' check='full'/>")
            original = vm.domain_xml
            self.conn.saveImageGetXMLDesc.return_value = self.xml(saved)
            vm._patch_xml_from_saved_image('/snapshot')
            self.assertEqual(original, vm.domain_xml)

    def test_missing_or_malformed_saved_cpu_keeps_original(self):
        for saved in (self.xml(''), '<domain>'):
            vm = self.vm()
            vm.domain_xml = self.xml("<cpu mode='host-model'/>")
            original = vm.domain_xml
            self.conn.saveImageGetXMLDesc.return_value = saved
            vm._patch_xml_from_saved_image('/snapshot')
            self.assertEqual(original, vm.domain_xml)

    def test_missing_current_cpu_keeps_original(self):
        vm = self.vm()
        vm.domain_xml = self.xml('')
        original = vm.domain_xml
        self.conn.saveImageGetXMLDesc.return_value = self.xml('')
        vm._patch_xml_from_saved_image('/snapshot')
        self.assertEqual(original, vm.domain_xml)

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

    def test_restore_hotplug_layout_in_all_cpu_modes(self):
        vcpus = ("<vcpus><vcpu id='0' enabled='yes' order='2'/>"
                 "<vcpu id='1' enabled='yes' order='1'/></vcpus>")
        memory_devices = (
            "<memory model='dimm'><target><size unit='KiB'>512</size><node>0</node></target>"
            "<address type='dimm' slot='0' base='0x100000000'/></memory>"
            "<memory model='dimm'><target><size unit='KiB'>512</size><node>1</node></target>"
            "<address type='dimm' slot='1' base='0x200000000'/></memory>")
        for mode in ('host-passthrough', 'host-model', 'custom', 'maximum'):
            with self.subTest(mode=mode):
                self.conn.reset_mock(side_effect=True)
                cpu = ("<cpu mode='%s'><numa>"
                       "<cell id='0' cpus='0' memory='1024' unit='KiB'/>"
                       "<cell id='1' cpus='1' memory='1024' unit='KiB'/>"
                       "</numa></cpu>" % mode)
                current = self.xml(cpu).replace('<cpu', "<vcpu>2</vcpu><cpu", 1)
                saved = current.replace("memory='1024'", "memory='512'")
                saved = saved.replace('</vcpu>', '</vcpu>' + vcpus, 1)
                saved = saved.replace('</devices>', memory_devices + '</devices>')
                saved = saved.replace('/current-volume', '/old-host-volume')
                if mode in ('host-model', 'custom'):
                    saved = saved.replace("<cpu mode='%s'>" % mode,
                                          "<cpu mode='custom' check='full'>")
                self.conn.saveImageGetXMLDesc.return_value = saved
                vm = self.vm()
                vm.domain_xml = current
                vm._patch_disk_xml_order_from_saved_image = Mock()
                vm.restore('/snapshot')
                expected, actual = etree.fromstring(saved), etree.fromstring(vm.domain_xml)
                for path in ('cpu/numa', 'vcpus'):
                    self.assertIsNotNone(actual.find(path), 'missing saved ' + path)
                    self.assertEqual(etree.tostring(expected.find(path)),
                                     etree.tostring(actual.find(path)))
                self.assertEqual([etree.tostring(d) for d in expected.findall('devices/memory')],
                                 [etree.tostring(d) for d in actual.findall('devices/memory')])
                self.assertEqual('/current-volume', actual.find('devices/disk/source').get('file'))
                self.conn.defineXML.assert_called_once_with(vm.domain_xml)
                self.conn.restoreFlags.assert_called_once_with('/snapshot', vm.domain_xml)

    def test_cpu_only_hotplug_restores_vcpu_enable_order(self):
        current = self.xml("<cpu mode='host-passthrough'/>")
        saved = current.replace('<devices>', "<vcpus><vcpu id='0' order='2'/>"
                                "<vcpu id='1' order='1'/></vcpus><devices>")
        self.conn.saveImageGetXMLDesc.return_value = saved
        vm = self.vm()
        vm.domain_xml = current
        vm._patch_disk_xml_order_from_saved_image = Mock()
        vm.restore('/snapshot')
        self.assertEqual(['2', '1'], [v.get('order') for v in
                                    etree.fromstring(vm.domain_xml).findall('vcpus/vcpu')])

    def test_no_hotplug_keeps_original_xml_bytes(self):
        current = self.xml("<cpu mode='host-passthrough'><numa>"
                           "<cell id='0' cpus='0-1' memory='1024'/></numa></cpu>")
        self.conn.saveImageGetXMLDesc.return_value = current
        vm = self.vm()
        vm.domain_xml = current
        vm._patch_disk_xml_order_from_saved_image = Mock()
        vm.restore('/snapshot')
        self.assertEqual(current, vm.domain_xml)

    def test_custom_vcpus_use_saved_enable_order(self):
        current_vcpus = "<vcpus>" + ''.join(
            "<vcpu id='%s' enabled='yes' order='%s'/>" % (i, i + 1)
            for i in range(4)) + '</vcpus>'
        current = self.xml("<cpu mode='host-passthrough'/>").replace(
            '<devices>', current_vcpus + '<devices>')
        saved = current.replace("id='2' enabled='yes' order='3'", "id='2' enabled='yes' order='4'")
        saved = saved.replace("id='3' enabled='yes' order='4'", "id='3' enabled='yes' order='3'")
        self.conn.saveImageGetXMLDesc.return_value = saved
        vm = self.vm()
        vm.domain_xml = current
        vm._patch_disk_xml_order_from_saved_image = Mock()
        vm.restore('/snapshot')
        restored_xml = self.conn.restoreFlags.call_args[0][1]
        self.assertEqual(['1', '2', '4', '3'], [v.get('order') for v in
                         etree.fromstring(restored_xml).findall('vcpus/vcpu')])

        self.conn.saveImageGetXMLDesc.return_value = current
        vm.domain_xml = current
        vm.restore('/snapshot')
        self.assertEqual(current, vm.domain_xml)

    def test_restore_saved_numa_distances_when_cells_match(self):
        for mode in ('host-passthrough', 'custom', 'maximum'):
            with self.subTest(mode=mode):
                current = self.xml("<cpu mode='%s'><numa>"
                                   "<cell id='0' cpus='0' memory='1024'>"
                                   "<distances><sibling id='0' value='10'/>"
                                   "<sibling id='1' value='20'/></distances></cell>"
                                   "<cell id='1' cpus='1' memory='1024'>"
                                   "<distances><sibling id='0' value='20'/>"
                                   "<sibling id='1' value='10'/></distances></cell>"
                                   "</numa></cpu>" % mode)
                saved = current.replace("value='20'", "value='40'")
                self.conn.saveImageGetXMLDesc.return_value = saved
                vm = self.vm()
                vm.domain_xml = current
                vm._patch_disk_xml_order_from_saved_image = Mock()
                vm.restore('/snapshot')
                restored = etree.fromstring(self.conn.restoreFlags.call_args[0][1])
                self.assertEqual(['10', '40', '40', '10'],
                                 [node.get('value') for node in restored.findall('cpu/numa/cell/distances/sibling')])

    def test_equal_numa_subtrees_preserve_original_xml(self):
        current = self.xml("<cpu mode='host-passthrough'><numa>"
                           "<cell id='0' cpus='0' memory='1024'>"
                           "<distances><sibling id='0' value='10'/></distances>"
                           "</cell></numa></cpu>")
        saved = current.replace("id='0' cpus='0' memory='1024'",
                                "memory='1024' cpus='0' id='0'")
        saved = saved.replace('<distances>', '\n<distances>\n').replace('</distances>', '\n</distances>\n')
        self.conn.saveImageGetXMLDesc.return_value = saved
        vm = self.vm()
        vm.domain_xml = current
        vm._patch_disk_xml_order_from_saved_image = Mock()
        vm.restore('/snapshot')
        self.assertEqual(current, vm.domain_xml)

    def test_restore_rejects_saved_vcpus_exceeding_configured_capacity(self):
        current = self.xml("<vcpu current='2'>2</vcpu><cpu mode='host-passthrough'/>")
        saved_vcpus = ('<vcpus>' + ''.join(
            "<vcpu id='%d' enabled='%s' hotpluggable='%s'/>" %
            (i, 'yes' if i < 2 else 'no', 'no' if i == 0 else 'yes')
            for i in range(4)) + '</vcpus>')
        saved = current.replace("current='2'>2</vcpu>", "current='2'>4</vcpu>" + saved_vcpus)
        self.conn.saveImageGetXMLDesc.return_value = saved
        vm = self.vm()
        vm.domain_xml = current
        vm._patch_disk_xml_order_from_saved_image = Mock()
        with self.assertRaisesRegex(RuntimeError, r'vCPU id\[2\].*capacity\[2\]'):
            vm.restore('/snapshot')
        self.conn.defineXML.assert_not_called()
        self.conn.restoreFlags.assert_not_called()
        self.assertEqual('2', etree.fromstring(vm.domain_xml).findtext('vcpu'))

    def test_hotplug_memory_devices_replace_existing_devices(self):
        current = self.xml("<cpu mode='host-passthrough'/>").replace(
            '</devices>', "<memory model='dimm'><address slot='9'/></memory>"
            "<memory model='virtio-mem'/></devices>")
        saved = current.replace("model='dimm'", "model='nvdimm'").replace("slot='9'", "slot='1'")
        self.conn.saveImageGetXMLDesc.return_value = saved
        vm = self.vm()
        vm.domain_xml = current
        vm._patch_disk_xml_order_from_saved_image = Mock()
        vm.restore('/snapshot')
        devices = etree.fromstring(vm.domain_xml).findall('devices/memory')
        self.assertEqual(['virtio-mem', 'nvdimm'], [d.get('model') for d in devices])
        self.assertEqual('1', devices[1].find('address').get('slot'))

    def test_restore_nvdimm_preserves_saved_volatile_memory_size(self):
        current = self.xml("<currentMemory unit='k'>393216</currentMemory>"
                           "<cpu mode='host-passthrough'><numa>"
                           "<cell id='0' cpus='0' memory='393216' unit='KiB'/>"
                           "</numa></cpu>")
        saved = current.replace("unit='k'>393216", "unit='KiB'>262144")
        saved = saved.replace("memory='393216'", "memory='262144'")
        saved = saved.replace('</devices>', "<memory model='nvdimm'>"
                              "<source><path>/nvdimm</path></source>"
                              "<target><size unit='KiB'>131072</size><node>0</node>"
                              "<label><size unit='KiB'>128</size></label></target>"
                              "<address type='dimm' slot='0'/></memory></devices>")
        self.conn.saveImageGetXMLDesc.return_value = saved
        vm = self.vm()
        vm.domain_xml = current
        vm._patch_disk_xml_order_from_saved_image = Mock()
        vm.restore('/snapshot')
        restored = etree.fromstring(self.conn.restoreFlags.call_args[0][1])
        self.assertEqual('262144', restored.findtext('currentMemory'),
                         'NVDIMM capacity must not be added to volatile current memory')
        self.assertEqual('KiB', restored.find('currentMemory').get('unit'))
        self.assertEqual('/current-volume', restored.find('devices/disk/source').get('file'))
        self.conn.defineXML.assert_called_once_with(vm.domain_xml)

    def test_restore_dimm_after_numa_is_disabled(self):
        for mode in ('host-model', 'host-passthrough', 'custom'):
            for configured_max in (None, '2097152'):
                with self.subTest(mode=mode, configured_max=configured_max):
                    self.conn.reset_mock(side_effect=True)
                    current = self.xml("<memory unit='KiB'>524288</memory>"
                                       "<currentMemory unit='KiB'>524288</currentMemory>"
                                       "<cpu mode='%s'/>" % mode)
                    if configured_max:
                        current = current.replace('<memory ', "<maxMemory slots='32' unit='KiB'>"
                                                  + configured_max + '</maxMemory><memory ', 1)
                    saved = self.xml("<maxMemory slots='64' unit='KiB'>4194304</maxMemory>"
                                     "<currentMemory unit='KiB'>524288</currentMemory>"
                                     "<cpu mode='%s'><numa><cell id='0' cpus='0-1'"
                                     " memory='262144' unit='KiB'/></numa></cpu>" % mode)
                    saved = saved.replace('</devices>', "<memory model='dimm'>"
                                          "<target><size unit='KiB'>262144</size><node>0</node>"
                                          "</target><address type='dimm' slot='0'/></memory></devices>")
                    self.conn.saveImageGetXMLDesc.return_value = saved
                    vm = self.vm()
                    vm.domain_xml = current
                    vm._patch_disk_xml_order_from_saved_image = Mock()
                    vm.restore('/snapshot')
                    restored = etree.fromstring(vm.domain_xml)
                    self.assertEqual(configured_max or '4194304', restored.findtext('maxMemory'))
                    self.assertEqual('32' if configured_max else '64', restored.find('maxMemory').get('slots'))
                    self.assertIsNotNone(restored.find('cpu/numa/cell'))
                    self.assertEqual('262144', restored.find('cpu/numa/cell').get('memory'))
                    self.assertEqual('/current-volume', restored.find('devices/disk/source').get('file'))

    def test_restore_checks_numa_cpu_capacity_without_vcpu_table(self):
        for cpus, maximum, rejected in [('0-127', 1, True), ('0,2-3', 3, True),
                                         ('0-3, ^3', 3, False), ('0-3,^1-3', 1, False), ('0', 1, False)]:
            with self.subTest(cpus=cpus, maximum=maximum):
                self.conn.reset_mock(side_effect=True)
                current = self.xml("<vcpu>%d</vcpu><cpu mode='host-passthrough'><numa>"
                                   "<cell id='0' cpus='%s' memory='262144'/></numa></cpu>" % (maximum, cpus))
                self.conn.saveImageGetXMLDesc.return_value = current
                vm = self.vm()
                vm.domain_xml = current
                vm._patch_disk_xml_order_from_saved_image = Mock()
                if rejected:
                    with self.assertRaisesRegex(RuntimeError, r'NUMA CPU id.*outside configured capacity'):
                        vm.restore('/snapshot')
                    self.conn.defineXML.assert_not_called()
                    self.conn.restoreFlags.assert_not_called()
                else:
                    vm.restore('/snapshot')
                    self.conn.restoreFlags.assert_called_once()
                self.assertEqual(str(maximum), etree.fromstring(vm.domain_xml).findtext('vcpu'))


if __name__ == '__main__':
    unittest.main()

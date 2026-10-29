import unittest
import xml.etree.ElementTree as etree
import mock

from kvmagent.plugins import vm_plugin


class TestMemorySnapshotRestore(unittest.TestCase):
    class FakeConnection(object):
        def __init__(self, saved_xml):
            self.saved_xml = saved_xml

        def saveImageGetXMLDesc(self, path, flags):
            return self.saved_xml

    def test_legacy_virtio_blk_discard_only_supports_i440fx_machine_types(self):
        self.assertTrue(vm_plugin.is_i440fx_machine_type('pc'))
        self.assertTrue(vm_plugin.is_i440fx_machine_type('pc-i440fx-rhel7.6.0'))
        self.assertFalse(vm_plugin.is_i440fx_machine_type('pc-q35-rhel8.6.0'))
        self.assertFalse(vm_plugin.is_i440fx_machine_type('q35'))

    def test_remove_discard_commandline_for_old_i440fx_snapshot(self):
        vm = vm_plugin.Vm()
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
            <os><type machine="pc-i440fx-rhel7.6.0">hvm</type></os>
            <qemu:commandline>
                <qemu:arg value="-qmp"/>
            </qemu:commandline>
            <qemu:commandline>
                <qemu:arg value="-global"/>
                <qemu:arg value="virtio-blk-pci.discard=on"/>
            </qemu:commandline>
        </domain>'''

        with mock.patch.object(vm_plugin.LibvirtAutoReconnect, 'conn', self.FakeConnection('<domain/>')):
            vm._remove_legacy_virtio_blk_discard_if_absent_in_saved_image('/tmp/snapshot')

        namespace = '{http://libvirt.org/schemas/domain/qemu/1.0}'
        commandlines = etree.fromstring(vm.domain_xml).findall('%scommandline' % namespace)
        self.assertEqual(1, len(commandlines))
        values = [arg.get('value') for commandline in commandlines
                  for arg in commandline.findall('%sarg' % namespace)]
        self.assertEqual(['-qmp'], values)

    def test_remove_all_discard_pairs_but_preserve_other_parameters(self):
        vm = vm_plugin.Vm()
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
            <os><type machine="pc">hvm</type></os>
            <qemu:commandline>
                <qemu:arg value="-global"/>
                <qemu:arg value="virtio-blk-pci.discard=on"/>
                <qemu:arg value="-global"/>
                <qemu:arg value="virtio-blk-pci.write-zeroes=on"/>
            </qemu:commandline>
            <qemu:commandline>
                <qemu:arg value="-global"/>
                <qemu:arg value="virtio-blk-pci.discard=on"/>
                <qemu:env name="EXAMPLE" value="keep"/>
            </qemu:commandline>
        </domain>'''
        with mock.patch.object(vm_plugin.LibvirtAutoReconnect, 'conn', self.FakeConnection('<domain/>')):
            vm._remove_legacy_virtio_blk_discard_if_absent_in_saved_image('/tmp/snapshot')

        namespace = '{http://libvirt.org/schemas/domain/qemu/1.0}'
        root = etree.fromstring(vm.domain_xml)
        values = [arg.get('value') for arg in root.findall('.//%sarg' % namespace)]
        self.assertEqual(['-global', 'virtio-blk-pci.write-zeroes=on'], values)
        self.assertEqual('keep', root.find('.//%senv' % namespace).get('value'))

    def test_keep_discard_commandline_for_new_i440fx_snapshot(self):
        vm = vm_plugin.Vm()
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
            <os><type machine="pc-i440fx-rhel7.6.0">hvm</type></os>
            <qemu:commandline>
                <qemu:arg value="-global"/>
                <qemu:arg value="virtio-blk-pci.discard=on"/>
            </qemu:commandline>
        </domain>'''

        saved_xml = vm.domain_xml.replace('<qemu:commandline>',
            '<qemu:commandline><qemu:arg value="-qmp"/></qemu:commandline><qemu:commandline>')
        with mock.patch.object(vm_plugin.LibvirtAutoReconnect, 'conn', self.FakeConnection(saved_xml)):
            vm._remove_legacy_virtio_blk_discard_if_absent_in_saved_image('/tmp/snapshot')

        namespace = '{http://libvirt.org/schemas/domain/qemu/1.0}'
        commandline = etree.fromstring(vm.domain_xml).find('%scommandline' % namespace)
        values = [arg.get('value') for arg in commandline.findall('%sarg' % namespace)]
        self.assertEqual(['-global', 'virtio-blk-pci.discard=on'], values)

    def test_keep_discard_commandline_for_q35_snapshot(self):
        vm = vm_plugin.Vm()
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
            <os><type machine="pc-q35-rhel8.6.0">hvm</type></os>
            <qemu:commandline>
                <qemu:arg value="-global"/>
                <qemu:arg value="virtio-blk-pci.discard=on"/>
            </qemu:commandline>
        </domain>'''

        vm._remove_legacy_virtio_blk_discard_if_absent_in_saved_image('/tmp/snapshot')

        namespace = '{http://libvirt.org/schemas/domain/qemu/1.0}'
        commandline = etree.fromstring(vm.domain_xml).find('%scommandline' % namespace)
        values = [arg.get('value') for arg in commandline.findall('%sarg' % namespace)]
        self.assertEqual(['-global', 'virtio-blk-pci.discard=on'], values)

import unittest
import xml.etree.ElementTree as etree
from unittest import mock

from kvmagent.plugins import vm_plugin


class TestMemorySnapshotRestore(unittest.TestCase):
    class FakeConnection(object):
        def __init__(self, saved_xml):
            self.saved_xml = saved_xml

        def saveImageGetXMLDesc(self, path, flags):
            return self.saved_xml

    def test_i440fx_only_includes_pc_machine_types(self):
        self.assertTrue(vm_plugin.is_i440fx_machine_type('pc'))
        self.assertTrue(vm_plugin.is_i440fx_machine_type('pc-i440fx-rhel7.6.0'))
        self.assertFalse(vm_plugin.is_i440fx_machine_type('pc-q35-rhel8.6.0'))

    def test_old_i440fx_snapshot_removes_discard_from_all_commandlines(self):
        vm = vm_plugin.Vm()
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
            <os><type machine="pc-i440fx-rhel7.6.0">hvm</type></os>
            <qemu:commandline><qemu:arg value="-qmp"/></qemu:commandline>
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
        self.assertEqual(['-qmp', '-global', 'virtio-blk-pci.write-zeroes=on'], values)
        self.assertEqual('keep', root.find('.//%senv' % namespace).get('value'))

    def test_new_i440fx_snapshot_keeps_discard_in_later_commandline(self):
        vm = vm_plugin.Vm()
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
            <os><type machine="pc">hvm</type></os>
            <qemu:commandline><qemu:arg value="-qmp"/></qemu:commandline>
            <qemu:commandline><qemu:arg value="-global"/><qemu:arg value="virtio-blk-pci.discard=on"/></qemu:commandline>
        </domain>'''
        saved_xml = vm.domain_xml

        with mock.patch.object(vm_plugin.LibvirtAutoReconnect, 'conn', self.FakeConnection(saved_xml)):
            vm._remove_legacy_virtio_blk_discard_if_absent_in_saved_image('/tmp/snapshot')

        self.assertEqual(saved_xml, vm.domain_xml)

    def test_q35_snapshot_does_not_change_discard(self):
        vm = vm_plugin.Vm()
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
            <os><type machine="pc-q35-rhel8.6.0">hvm</type></os>
            <qemu:commandline><qemu:arg value="-global"/><qemu:arg value="virtio-blk-pci.discard=on"/></qemu:commandline>
        </domain>'''
        original_xml = vm.domain_xml

        vm._remove_legacy_virtio_blk_discard_if_absent_in_saved_image('/tmp/snapshot')

        self.assertEqual(original_xml, vm.domain_xml)

    def test_invalid_saved_xml_does_not_silently_restore_with_discard(self):
        vm = vm_plugin.Vm()
        vm.domain_xml = '''<domain xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0">
            <os><type machine="pc">hvm</type></os>
            <qemu:commandline><qemu:arg value="-global"/><qemu:arg value="virtio-blk-pci.discard=on"/></qemu:commandline>
        </domain>'''

        with mock.patch.object(vm_plugin.LibvirtAutoReconnect, 'conn', self.FakeConnection('<domain')):
            with self.assertRaises(etree.ParseError):
                vm._remove_legacy_virtio_blk_discard_if_absent_in_saved_image('/tmp/snapshot')

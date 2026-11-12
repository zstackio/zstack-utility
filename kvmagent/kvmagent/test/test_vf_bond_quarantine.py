"""Quarantine release evidence must fail closed and never alter host devices."""
import ast
import errno
import os
from pathlib import Path
import re
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

source = Path(__file__).resolve().parents[1] / 'plugins/vf_bond_cleanup.py'
tree = ast.parse(source.read_text())
tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
ctx = dict(os=os, re=re, errno=errno, ET=ET, libvirt=types.SimpleNamespace(VIR_DOMAIN_XML_INACTIVE=2),
           vm_plugin=types.SimpleNamespace(LibvirtAutoReconnect=lambda f: f),
           linux=types.SimpleNamespace(find_vm_process_by_uuid=lambda _: ''))
exec(compile(tree, str(source), 'exec'), ctx)


class CleanupEvidenceTest(unittest.TestCase):
    device = dict(uuid='a' * 32, pciAddress='0000:17:10.1', vmUuid='b' * 32)

    def check(self, used=None, opened=None, process='', group=True):
        with patch.dict(ctx, domain_devices=lambda: used or set(), open_vfio_groups=lambda: opened or set(),
                        linux=types.SimpleNamespace(find_vm_process_by_uuid=lambda _: process)), \
                patch.object(os.path, 'islink', return_value=group), \
                patch.object(os.path, 'realpath', return_value='/sys/kernel/iommu_groups/4'):
            return ctx['check_devices']([self.device])

    def test_only_complete_unoccupied_evidence_releases(self):
        self.assertEqual({self.device['uuid']: self.device['pciAddress']}, self.check()['safeDevices'])
        for kwargs, reason in [({'process': 'qemu'}, 'OwnerProcessPresent'),
                               ({'used': {self.device['pciAddress']}}, 'DomainReferencesDevice'),
                               ({'opened': {'/dev/vfio/4'}}, 'VfioGroupInUse'),
                               ({'opened': {'/dev/iommu'}}, 'UnsupportedVfioDescriptor'),
                               ({'group': False}, 'IommuGroupUnavailable')]:
            answer = self.check(**kwargs)
            self.assertFalse(answer['safeDevices'])
            self.assertEqual(reason, answer['blockedDevices'][self.device['uuid']])

    def test_inspection_error_does_not_return_partial_success(self):
        for stage in ['domain_devices', 'open_vfio_groups']:
            with patch.dict(ctx, domain_devices=lambda: set(), open_vfio_groups=lambda: set()):
                with patch.dict(ctx, {stage: lambda: (_ for _ in ()).throw(OSError('unavailable'))}):
                    with self.assertRaises(OSError): ctx['check_devices']([self.device])

    def test_all_domain_definitions_and_both_pci_representations_are_checked(self):
        xml = '<domain><devices><interface type="hostdev"><source><address domain="0x0" bus="0x17" slot="0x10" function="0x1"/></source></interface><hostdev type="pci"><source><address domain="0x0" bus="0x18" slot="0x10" function="0x2"/></source></hostdev></devices></domain>'
        conn = types.SimpleNamespace(listAllDomains=lambda flags: [types.SimpleNamespace(
            isPersistent=lambda: True, XMLDesc=lambda flags: xml.replace('0x17', '0x19') if flags == 2 else xml)])
        self.assertEqual({'0000:17:10.1', '0000:19:10.1', '0000:18:10.2'}, ctx['domain_devices'](conn))

    def test_proc_permission_error_is_not_absence(self):
        def listing(path):
            if path == '/proc': return ['1']
            raise OSError(errno.EACCES, 'denied')
        with patch.object(os, 'listdir', side_effect=listing):
            with self.assertRaises(OSError): ctx['open_vfio_groups']()

    def test_non_pci_hostdevs_do_not_block_vf_recovery(self):
        xml = '''<domain><devices>
          <hostdev type="usb"><source><address bus="23" device="2"/></source></hostdev>
          <hostdev type="mdev"><source><address uuid="12345678-1234-1234-1234-123456789abc"/></source></hostdev>
          <interface type="hostdev"><source><address type="pci" domain="0x0" bus="0x18" slot="0x10" function="0x1"/></source></interface>
        </devices></domain>'''
        conn = types.SimpleNamespace(listAllDomains=lambda flags: [types.SimpleNamespace(
            isPersistent=lambda: True, XMLDesc=lambda flags: xml)])
        used = ctx['domain_devices'](conn)
        self.assertEqual({'0000:18:10.1'}, used)
        self.device = dict(self.device, pciAddress='0000:17:00.0')
        self.assertEqual({self.device['uuid']: self.device['pciAddress']}, self.check(used=used)['safeDevices'])

    def test_exited_process_during_scan_is_safe(self):
        def listing(path):
            if path == '/proc': return ['1']
            raise OSError(errno.ENOENT, 'exited')
        with patch.object(os, 'listdir', side_effect=listing):
            self.assertFalse(ctx['open_vfio_groups']())


if __name__ == '__main__': unittest.main()

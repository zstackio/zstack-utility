import os
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from xml.etree import ElementTree as etree

from kvmagent.crypto import vm_xml
from kvmagent.crypto import qemu_volume as volume


class VolumeCryptoXmlTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.key = os.path.join(self.directory.name, 'key')
        with open(self.key, 'wb') as stream:
            stream.write(b'same-key-for-all-encrypted-layers')

    def _path(self, name):
        return os.path.join(self.directory.name, name)

    def _disk(self, path):
        disk = etree.Element('disk', type='file', device='disk')
        etree.SubElement(disk, 'driver', name='qemu', type='qcow2')
        etree.SubElement(disk, 'source', file=path)
        return disk

    @unittest.skipUnless(os.path.exists(volume.QEMU_IMG), 'qemu-img is required')
    def test_plain_leaf_over_encrypted_backing_references_secret_only_on_backing(self):
        backing = self._path('backing.qcow2')
        leaf = self._path('leaf.qcow2')
        volume.create_encrypted_qcow2(backing, 16 * 1024 * 1024, self.key)
        subprocess.check_call([volume.QEMU_IMG, 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', backing, leaf])
        disk = vm_xml.apply_volume_encryption(self._disk(leaf),
                                        SimpleNamespace(installPath=leaf, luksSecretUuid='luks-uuid'), 'file')
        self.assertIsNone(disk.find('encryption'))
        self.assertEqual('luks-uuid', disk.find('backingStore/source/encryption/secret').get('uuid'))
        self.assertIsNone(disk.find('source/encryption'))

    @unittest.skipUnless(os.path.exists(volume.QEMU_IMG), 'qemu-img is required')
    def test_missing_uuid_for_encrypted_backing_is_rejected(self):
        backing = self._path('backing.qcow2')
        leaf = self._path('leaf.qcow2')
        volume.create_encrypted_qcow2(backing, 16 * 1024 * 1024, self.key)
        subprocess.check_call([volume.QEMU_IMG, 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', backing, leaf])
        with self.assertRaisesRegex(ValueError, 'LUKS secret UUID'):
            vm_xml.apply_volume_encryption(self._disk(leaf), SimpleNamespace(installPath=leaf), 'file')

    def test_ceph_auth_and_volume_secret_are_distinct(self):
        disk = etree.Element('disk', type='network', device='disk')
        auth = etree.SubElement(disk, 'auth', username='zstack')
        etree.SubElement(auth, 'secret', type='ceph', uuid='ceph-uuid')
        etree.SubElement(disk, 'source', protocol='rbd', name='pool/volume')
        with patch.object(vm_xml.ceph, 'is_encrypted', return_value=True) as query_format:
            vm_xml.apply_volume_encryption(disk, SimpleNamespace(
                luksSecretUuid='luks-uuid', primaryStorageUuid='ps-uuid',
                installPath='ceph://pool/volume'), 'ceph')
        query_format.assert_called_once_with('ceph://pool/volume', 'ps-uuid')
        self.assertEqual('ceph-uuid', disk.find('auth/secret').get('uuid'))
        self.assertEqual('luks-uuid', disk.find('source/encryption/secret').get('uuid'))

    def test_ceph_encryption_rejects_plain_target(self):
        disk = etree.Element('disk', type='network', device='disk')
        etree.SubElement(disk, 'source', protocol='rbd', name='pool/volume')
        with patch.object(vm_xml.ceph, 'is_encrypted', return_value=False):
            with self.assertRaisesRegex(ValueError, 'unencrypted'):
                vm_xml.apply_volume_encryption(disk, SimpleNamespace(
                    luksSecretUuid='luks-uuid', primaryStorageUuid='ps-uuid',
                    installPath='ceph://pool/volume'), 'ceph')

    def test_cbd_xml_uses_public_storage_format_query(self):
        disk = etree.Element('disk', type='network', device='disk')
        etree.SubElement(disk, 'source', protocol='cbd', name='pool/volume')
        with patch.object(vm_xml.zbs, 'is_encrypted', return_value=True) as query_format:
            vm_xml.apply_volume_encryption(disk, SimpleNamespace(
                luksSecretUuid='luks-uuid', installPath='cbd:pool/volume'), 'cbd')
        query_format.assert_called_once_with('cbd:pool/volume')
        self.assertEqual('luks-uuid', disk.find('source/encryption/secret').get('uuid'))

    def test_vhost_rejects_encrypted_volume(self):
        with self.assertRaisesRegex(ValueError, 'vhost'):
            vm_xml.apply_volume_encryption(etree.Element('disk'),
                                     SimpleNamespace(luksSecretUuid='luks-uuid'), 'vhost')


if __name__ == '__main__':
    unittest.main()

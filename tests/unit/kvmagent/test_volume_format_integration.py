import unittest
from types import SimpleNamespace
from unittest import mock
from xml.etree import ElementTree as etree

from kvmagent.crypto import vm_xml, volume_request
from kvmagent.crypto.file_volume.driver import LuksFileVolumeDriver
from kvmagent.crypto.shared_block.driver import LuksSharedBlockVolumeDriver
from kvmagent.plugins import volume_crypto_plugin
from kvmagent.volume import disk_xml, driver_factory, driver_registry
from kvmagent.volume.plain_file_driver import PlainFileVolumeDriver
from kvmagent.volume.plain_shared_block_driver import PlainSharedBlockVolumeDriver


class VolumeFormatIntegrationTest(unittest.TestCase):
    def setUp(self):
        for registry in (driver_registry._driver_registrations, disk_xml._disk_xml_extensions):
            patcher = mock.patch.dict(registry, {}, clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.plugin = volume_crypto_plugin.VolumeCryptoPlugin()
        self.plugin.configure()

    def test_repeated_configuration_keeps_one_matching_provider(self):
        self.plugin.configure()
        self.assertIsInstance(driver_factory.get_file_driver(SimpleNamespace(encryptedDek='wrapped')), LuksFileVolumeDriver)
        self.assertIsInstance(driver_factory.get_shared_block_driver(SimpleNamespace(encryptedDek='wrapped')),
                              LuksSharedBlockVolumeDriver)
        self.assertIs(type(driver_factory.get_file_driver(SimpleNamespace())), PlainFileVolumeDriver)
        self.assertIs(type(driver_factory.get_shared_block_driver(SimpleNamespace())), PlainSharedBlockVolumeDriver)

    def test_storage_drivers_share_one_request_selection_contract(self):
        for storage_type in ('file', 'sharedblock'):
            predicate, _ = driver_registry._driver_registrations[storage_type]['luks']
            self.assertIs(predicate, volume_request.should_use_luks_driver)

    def test_missing_disk_xml_registration_rejects_instead_of_skipping_validation(self):
        with mock.patch.dict(disk_xml._disk_xml_extensions, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'extensions are not configured'):
                disk_xml.apply_extensions(etree.Element('disk'), SimpleNamespace(installPath='/volume'), 'file')

    def test_incomplete_crypto_request_cannot_fall_back_to_plain_format(self):
        for get_driver in (driver_factory.get_file_driver, driver_factory.get_shared_block_driver):
            with self.assertRaisesRegex(ValueError, 'encryptedDek'):
                get_driver(SimpleNamespace(encrypted=True))

    def test_plugin_owns_all_existing_crypto_uris_once(self):
        server = mock.Mock()
        with mock.patch.object(volume_crypto_plugin.kvmagent, 'get_http_server', return_value=server):
            self.plugin.start()
        routes = [call.args[0] for call in server.register_async_uri.call_args_list]
        self.assertEqual(9, len(routes))
        self.assertEqual(len(routes), len(set(routes)))
        for prefix in ('localstorage', 'nfsprimarystorage', 'sharedblock'):
            self.assertIn('/%s/volume/encryptinplace' % prefix, routes)
        for prefix in ('ceph', 'zbs'):
            for operation in ('lukscreateempty', 'luksclone', 'encryptinplace'):
                self.assertIn('/%s/primarystorage/kvmhost/%s' % (prefix, operation), routes)

    def test_xml_validation_still_detects_unmarked_encrypted_backing(self):
        disk = etree.Element('disk')
        volume = SimpleNamespace(installPath='/plain-top')
        layers = [('/plain-top', 'qcow2', False), ('/encrypted-base', 'qcow2', True)]
        with mock.patch.object(vm_xml, '_file_chain', return_value=iter(layers)):
            with self.assertRaisesRegex(ValueError, 'LUKS secret UUID'):
                disk_xml.apply_extensions(disk, volume, 'file')

    def test_plain_xml_keeps_identical_content_after_registered_validation(self):
        disk = etree.Element('disk', type='file')
        etree.SubElement(disk, 'source', file='/plain')
        original = etree.tostring(disk)
        with mock.patch.object(vm_xml, '_file_chain', return_value=iter([('/plain', 'qcow2', False)])):
            self.assertIs(disk, disk_xml.apply_extensions(disk, SimpleNamespace(installPath='/plain'), 'file'))
        self.assertEqual(original, etree.tostring(disk))

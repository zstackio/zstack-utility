import json
import os
import shlex
import unittest
from types import SimpleNamespace
from unittest import mock
from xml.etree import ElementTree as etree

from kvmagent.crypto import vm_xml, volume_request
from kvmagent.crypto.file_volume.driver import LuksFileVolumeDriver
from kvmagent.crypto.shared_block.driver import LuksSharedBlockVolumeDriver
from kvmagent.plugins import volume_crypto_plugin
from kvmagent.volume import disk_xml, driver_factory, driver_registry, imagestore_commands
from kvmagent.volume.plain_file_driver import PlainFileVolumeDriver
from kvmagent.volume.plain_shared_block_driver import PlainSharedBlockVolumeDriver


class VolumeFormatIntegrationTest(unittest.TestCase):
    def setUp(self):
        for registry in (driver_registry._driver_registrations, disk_xml._disk_xml_extensions, imagestore_commands._command_extensions):
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

    def test_missing_imagestore_registration_cannot_execute_plain_commands(self):
        contexts = [imagestore_commands.prepare_image_add_command('zstcli add'),
                    imagestore_commands.prepare_volume_backup_command('zstcli backup', None, 0),
                    imagestore_commands.prepare_batch_backup_command('zstcli batbak -args old', None, [], [])]
        with mock.patch.dict(imagestore_commands._command_extensions, {}, clear=True):
            for context in contexts:
                with self.assertRaisesRegex(RuntimeError, 'extensions are not configured'):
                    with context:
                        self.fail('unregistered command must not execute')

    def test_incomplete_crypto_request_cannot_fall_back_to_plain_format(self):
        for get_driver in (driver_factory.get_file_driver, driver_factory.get_shared_block_driver):
            with self.assertRaisesRegex(ValueError, 'encryptedDek'):
                get_driver(SimpleNamespace(encrypted=True))

    def test_plugin_owns_all_existing_crypto_uris_once(self):
        server = mock.Mock()
        with mock.patch.object(volume_crypto_plugin.kvmagent, 'get_http_server', return_value=server):
            self.plugin.start()
        routes = [call.args[0] for call in server.register_async_uri.call_args_list]
        self.assertEqual(11, len(routes))
        self.assertEqual(len(routes), len(set(routes)))
        for prefix in ('localstorage', 'nfsprimarystorage', 'sharedblock'):
            self.assertIn('/%s/volume/encryptinplace' % prefix, routes)
        for prefix in ('ceph', 'zbs'):
            for operation in ('lukscreateempty', 'luksclone', 'encryptinplace',
                              'imagestore/encrypteddownload'):
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

    def test_backup_parent_uses_device_zero_spec_and_deletes_secret_file_after_failure(self):
        addons = {'VolumeBackupEncryption': {'specs': [
            {'deviceId': 0, 'encrypted': True, 'encryptedDek': 'wrapped-key'}]}}
        with self.assertRaisesRegex(RuntimeError, 'command failed'):
            with imagestore_commands.prepare_image_add_command('zstcli add', addons, 0) as command:
                args = shlex.split(command)
                path = args[args.index('-encryption-json-file') + 1]
                self.assertEqual(0o600, os.stat(path).st_mode & 0o777)
                with open(path) as stream:
                    self.assertEqual('wrapped-key', json.load(stream)['encryptedDek'])
                raise RuntimeError('command failed')
        self.assertFalse(os.path.exists(path))

    def test_mixed_backup_retains_per_disk_spec_and_plain_command_is_unchanged(self):
        addons = {'VolumeBackupEncryption': {'specs': [
            {'deviceId': 1, 'encrypted': True, 'encryptedDek': 'wrapped-key'}]}}
        args = [('a', 'full', 'drive-a', 0), ('b', 'top', 'drive-b', 0)]
        with imagestore_commands.prepare_batch_backup_command('zstcli batbak -args old', addons, args, [0, 1]) as command:
            words = shlex.split(command)
            path = words[words.index('-args-json-file') + 1]
            with open(path) as stream:
                payload = json.load(stream)['backups']
            self.assertNotIn('encryption', payload[0])
            self.assertEqual('wrapped-key', payload[1]['encryption']['encryptedDek'])
        self.assertFalse(os.path.exists(path))
        with imagestore_commands.prepare_image_add_command('zstcli add', addons, 0) as command:
            self.assertEqual('zstcli add', command)

    def test_registered_add_rejects_missing_key_before_plain_command(self):
        addons = {'ImageStoreEncryption': {'encrypted': True}}
        with self.assertRaisesRegex(ValueError, 'encryptedDek'):
            with imagestore_commands.prepare_image_add_command('zstcli add', addons):
                self.fail('must not execute plaintext command')

import unittest
from types import SimpleNamespace
from unittest import mock

from kvmagent.crypto import volume_request
from kvmagent.volume import driver_factory, driver_registry


class VolumeFormatRegistryTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(driver_registry._driver_registrations, {}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.plain = mock.Mock(name='plain')
        self.luks = mock.Mock(name='luks')
        for driver_name in ('PlainFileVolumeDriver', 'PlainSharedBlockVolumeDriver'):
            patcher = mock.patch.object(driver_factory, driver_name, self.plain)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_plain_and_luks_requests_use_only_the_selected_factory(self):
        driver_registry.register_driver('file', 'luks', volume_request.should_use_luks_driver, self.luks)
        cmd = SimpleNamespace()
        self.assertIs(self.plain.return_value, driver_factory.get_file_driver(cmd))
        self.luks.assert_not_called()
        cmd.encryptedDek = 'wrapped'
        self.assertIs(self.luks.return_value, driver_factory.get_file_driver(cmd))
        self.luks.assert_called_once_with(cmd)
        self.plain.assert_called_once_with(cmd)

    def test_invalid_key_request_cannot_fall_back_to_plain_writes(self):
        driver_registry.register_driver('file', 'luks', volume_request.should_use_luks_driver, self.luks)
        with self.assertRaisesRegex(ValueError, 'encryptedDek'):
            driver_factory.get_file_driver(SimpleNamespace(encrypted=True))
        self.plain.assert_not_called()
        self.luks.assert_not_called()

    def test_provider_names_are_idempotent_but_cannot_be_overwritten(self):
        driver_registry.register_driver('file', 'luks', volume_request.should_use_luks_driver, self.luks)
        driver_registry.register_driver('file', 'luks', volume_request.should_use_luks_driver, self.luks)
        with self.assertRaisesRegex(ValueError, 'already registered'):
            driver_registry.register_driver('file', 'luks', volume_request.should_use_luks_driver, self.plain)

    def test_ambiguous_formats_fail_before_either_factory_runs(self):
        driver_registry.register_driver('file', 'luks', volume_request.should_use_luks_driver, self.luks)
        driver_registry.register_driver('file', 'another', volume_request.should_use_luks_driver, self.plain)
        with self.assertRaisesRegex(ValueError, 'multiple'):
            driver_factory.get_file_driver(SimpleNamespace(encryptedDek='wrapped'))
        self.plain.assert_not_called()
        self.luks.assert_not_called()

    def test_storage_providers_do_not_leak_across_backends(self):
        driver_registry.register_driver('sharedblock', 'luks', volume_request.should_use_luks_driver, self.luks)
        with self.assertRaisesRegex(RuntimeError, 'not configured'):
            driver_factory.get_file_driver(SimpleNamespace(encryptedDek='wrapped'))
        self.luks.assert_not_called()
        self.plain.assert_not_called()

    def test_missing_plugin_registration_cannot_silently_select_plaintext(self):
        for get_driver in (driver_factory.get_file_driver, driver_factory.get_shared_block_driver):
            for cmd in (SimpleNamespace(), SimpleNamespace(encryptedDek='wrapped')):
                with self.assertRaisesRegex(RuntimeError, 'not configured'):
                    get_driver(cmd)
        self.plain.assert_not_called()


if __name__ == '__main__':
    unittest.main()

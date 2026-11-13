import json
import os
import shlex
import unittest

from kvmagent.crypto.imagestore_extension import ImageStoreEncryptionExtension


class VolumeCryptoImageStoreTest(unittest.TestCase):
    def test_batch_backup_uses_per_device_specs_and_removes_secret_file(self):
        wrapped = 'd3JhcHBlZA=='
        addons = {'VolumeBackupEncryption': {'specs': [
            {'deviceId': 1, 'encrypted': True, 'encryptedDek': wrapped, 'keyVersion': '1'}]}}
        args = [('a', 'full', 'drive-a', 0), ('b', 'top', 'drive-b', 10)]
        with ImageStoreEncryptionExtension.prepare_batch_backup_command(
                'zstcli batbak -args a:full:drive-a:0:b:top:drive-b:10', addons, args, [0, 1]) as command:
            self.assertIn('-args-json-file', command)
            self.assertIn('-secret-channel-provider', command)
            path = shlex.split(command)[shlex.split(command).index('-args-json-file') + 1]
            self.assertEqual(0o600, os.stat(path).st_mode & 0o777)
            with open(path) as stream:
                payload = json.load(stream)
            self.assertNotIn('encryption', payload['backups'][0])
            self.assertEqual(wrapped, payload['backups'][1]['encryption']['encryptedDek'])
        self.assertFalse(os.path.exists(path))

    def test_missing_wrapped_key_does_not_run_plain_add(self):
        addons = {'ImageStoreEncryption': {'encrypted': True}}
        with self.assertRaisesRegex(ValueError, 'encryptedDek'):
            with ImageStoreEncryptionExtension.prepare_image_add_command('zstcli add', addons, None):
                pass

    def test_plain_command_keeps_original_text(self):
        with ImageStoreEncryptionExtension.prepare_image_add_command('zstcli add', None, None) as command:
            self.assertEqual('zstcli add', command)

    def test_pull_and_single_backup_keep_encryption_payload(self):
        spec = dict(encrypted=True, encryptedDek='d3JhcHBlZA==', keyProviderUuid='provider',
                    keyVersion=1, cipher='luks')
        addons = {'VolumeBackupEncryption': {'specs': [dict(spec, deviceId=0)]}}
        contexts = (
            ImageStoreEncryptionExtension.prepare_image_pull_command('zstcli pull', {'ImageStoreEncryption': spec}),
            ImageStoreEncryptionExtension.prepare_volume_backup_command('zstcli backup', addons, 0),
        )
        for context in contexts:
            with context as command:
                words = shlex.split(command)
                path = words[words.index('-encryption-json-file') + 1]
                self.assertIn('-secret-channel-provider', words)
                with open(path) as stream:
                    self.assertEqual(spec, json.load(stream))
            self.assertFalse(os.path.exists(path))

    def test_pull_rejects_invalid_encryption_spec(self):
        addons = {'ImageStoreEncryption': dict(encrypted=True, encryptedDek='d3JhcHBlZA==',
                                               keyProviderUuid='provider', keyVersion='1', cipher='luks')}
        with self.assertRaisesRegex(ValueError, 'keyVersion'):
            with ImageStoreEncryptionExtension.prepare_image_pull_command('zstcli pull', addons):
                self.fail('invalid encryption spec must stop the command')


if __name__ == '__main__':
    unittest.main()

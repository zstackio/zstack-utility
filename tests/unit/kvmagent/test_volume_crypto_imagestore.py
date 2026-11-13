import json
import os
import shlex
import unittest

from kvmagent.crypto import imagestore


class VolumeCryptoImageStoreTest(unittest.TestCase):
    def test_batch_backup_uses_per_device_specs_and_removes_secret_file(self):
        wrapped = 'd3JhcHBlZA=='
        addons = {'VolumeBackupEncryption': {'specs': [
            {'deviceId': 1, 'encrypted': True, 'encryptedDek': wrapped, 'keyVersion': '1'}]}}
        args = [('a', 'full', 'drive-a', 0), ('b', 'top', 'drive-b', 10)]
        context = {'kind': 'batch-backup', 'addons': addons, 'args': args, 'deviceIds': [0, 1]}
        with imagestore.prepare_command(context, 'zstcli batbak -args a:full:drive-a:0:b:top:drive-b:10') as command:
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
        context = {'kind': 'add', 'addons': {'ImageStoreEncryption': {'encrypted': True}}}
        with self.assertRaisesRegex(ValueError, 'encryptedDek'):
            with imagestore.prepare_command(context, 'zstcli add'):
                pass

    def test_plain_command_keeps_original_text(self):
        with imagestore.prepare_command({'kind': 'add'}, 'zstcli add') as command:
            self.assertEqual('zstcli add', command)


if __name__ == '__main__':
    unittest.main()

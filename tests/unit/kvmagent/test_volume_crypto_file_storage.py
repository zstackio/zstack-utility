import os
import logging
import tempfile
import unittest
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

from kvmagent.crypto.file_volume import operations as file_storage
from kvmagent.crypto import qemu_volume as volume
from kvmagent.crypto import http_error


class FileStorageCryptoTest(unittest.TestCase):
    @unittest.skipUnless(os.path.exists('/usr/bin/qemu-img'), 'qemu-img is required')
    def test_local_empty_volume_uses_crypto_handler_and_reports_format(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, 'volume.qcow2')
            secret_file = os.path.join(directory, 'secret')
            with open(secret_file, 'wb') as stream:
                stream.write(b'volume-passphrase')
            cmd = SimpleNamespace(encryptedDek='wrapped', volumeFormat='qcow2',
                                  installUrl=target, size=8 * 1024 * 1024,
                                  backingFile=None, kvmHostAddons=None)

            @contextmanager
            def channel(_):
                yield secret_file

            with mock.patch.object(file_storage.secret, 'luks_secret_channel', channel):
                actual_encrypted = file_storage.create_empty(cmd)

            self.assertTrue(actual_encrypted)
            self.assertTrue(volume.is_luks_encrypted_image(target))

    def test_encrypted_raw_request_rejects_before_plain_create(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, 'volume.raw')
            cmd = SimpleNamespace(encryptedDek='wrapped', volumeFormat='raw',
                                  installUrl=target, size=8 * 1024 * 1024, backingFile=None)
            with self.assertRaisesRegex(ValueError, 'qcow2'):
                file_storage.create_empty(cmd)
            self.assertFalse(os.path.exists(target))

    @unittest.skipUnless(os.path.exists('/usr/bin/qemu-img'), 'qemu-img is required')
    def test_derived_volume_uses_crypto_path_and_keeps_template_plain(self):
        with tempfile.TemporaryDirectory() as directory:
            template = os.path.join(directory, 'template.qcow2')
            target = os.path.join(directory, 'volume.qcow2')
            secret_file = os.path.join(directory, 'secret')
            subprocess.check_call(['/usr/bin/qemu-img', 'create', '-f', 'qcow2', template, '8M'])
            with open(secret_file, 'wb') as stream:
                stream.write(b'volume-passphrase')
            cmd = SimpleNamespace(encryptedDek='wrapped', templatePathInCache=template,
                                  installUrl=target, virtualSize=8 * 1024 * 1024,
                                  kvmHostAddons=None)

            @contextmanager
            def channel(_):
                yield secret_file

            with mock.patch.object(file_storage.secret, 'luks_secret_channel', channel):
                actual_encrypted = file_storage.create_with_backing(cmd, template, target)
            self.assertTrue(actual_encrypted)
            self.assertFalse(volume.is_luks_encrypted_image(template))
            self.assertTrue(volume.is_luks_encrypted_image(target))

    @unittest.skipUnless(all(os.path.exists(tool) for tool in (volume.QEMU_IMG, volume.QEMU_IO)),
                         'QEMU tools are required')
    def test_encrypt_in_place_verifies_before_replacing_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'source.qcow2')
            key = os.path.join(directory, 'key')
            subprocess.check_call([volume.QEMU_IMG, 'create', '-f', 'qcow2', source, '4M'])
            with open(key, 'wb') as stream:
                stream.write(b'local-in-place-fixture')
            os.chmod(key, 0o600)

            @contextmanager
            def channel(_):
                yield key

            verify = volume.verify_luks_open

            def verify_before_publish(path, provider):
                self.assertNotEqual(source, path)
                self.assertFalse(volume.is_luks_encrypted_image(source))
                verify(path, provider)

            with mock.patch.object(file_storage.secret, 'luks_secret_channel', channel), \
                    mock.patch.object(volume, 'verify_luks_open', side_effect=verify_before_publish) as check:
                self.assertTrue(file_storage.encrypt_in_place(
                    SimpleNamespace(installPath=source, encryptedDek='synthetic')))
            check.assert_called_once()
            self.assertTrue(volume.is_luks_encrypted_image(source))
            verify(source, key)

    def test_encrypt_in_place_rejects_missing_key_without_touching_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'source.raw')
            with open(source, 'wb') as stream:
                stream.write(b'original data')
            with self.assertRaisesRegex(ValueError, 'encryptedDek'):
                file_storage.encrypt_in_place(SimpleNamespace(installPath=source, encryptedDek=None))
            with open(source, 'rb') as stream:
                self.assertEqual(b'original data', stream.read())

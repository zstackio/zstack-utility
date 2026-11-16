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

    @unittest.skipUnless(os.path.exists('/usr/bin/qemu-img'), 'qemu-img is required')
    def test_conversion_rejects_existing_target_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'source.qcow2')
            target = os.path.join(directory, 'target.qcow2')
            subprocess.check_call(['/usr/bin/qemu-img', 'create', '-f', 'qcow2', source, '8M'])
            with open(target, 'wb') as stream:
                stream.write(b'owned data')
            item = SimpleNamespace(resourceUuid='volume', sourceInstallPath=source,
                                   targetInstallPath=target, targetBackingInstallPath=None)
            cmd = SimpleNamespace(targetEncrypted=True, encryptedDek='wrapped', items=[item])
            with self.assertRaises(FileExistsError):
                file_storage.convert_items(cmd)
            with open(target, 'rb') as stream:
                self.assertEqual(b'owned data', stream.read())

    @unittest.skipUnless(os.path.exists('/usr/bin/qemu-img'), 'qemu-img is required')
    def test_conversion_moves_original_to_trash_before_reusing_install_path(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'volume.qcow2')
            trash = os.path.join(directory, 'volume.trash.qcow2')
            secret_file = os.path.join(directory, 'secret')
            subprocess.check_call(['/usr/bin/qemu-img', 'create', '-f', 'qcow2', source, '8M'])
            with open(secret_file, 'wb') as stream:
                stream.write(b'volume-passphrase')
            item = SimpleNamespace(resourceUuid='volume', sourceInstallPath=source,
                                   targetInstallPath=source, sourceTrashInstallPath=trash,
                                   targetBackingInstallPath=None)

            @contextmanager
            def channel(_):
                yield secret_file

            with mock.patch.object(file_storage.secret, 'luks_secret_channel', channel):
                sizes = file_storage.convert_items(SimpleNamespace(
                    targetEncrypted=True, encryptedDek='wrapped', items=[item]))
            self.assertGreater(sizes['volume'], 0)
            self.assertTrue(volume.is_luks_encrypted_image(source))
            self.assertFalse(volume.is_luks_encrypted_image(trash))

    def test_backing_chain_conversion_resets_temporary_backing_to_final_path(self):
        with tempfile.TemporaryDirectory() as directory:
            base = os.path.join(directory, 'base.qcow2')
            child = os.path.join(directory, 'child.qcow2')
            for path in (base, child):
                with open(path, 'wb') as stream:
                    stream.write(b'plain-source')
            items = [SimpleNamespace(resourceUuid='base', sourceInstallPath=base,
                                     targetInstallPath=base, sourceTrashInstallPath=base + '.trash',
                                     targetBackingInstallPath=None),
                     SimpleNamespace(resourceUuid='child', sourceInstallPath=child,
                                     targetInstallPath=child, sourceTrashInstallPath=child + '.trash',
                                     targetBackingInstallPath=base)]
            calls = []

            def convert(source, target, encrypted, provider, backing):
                calls.append((source, target, backing))
                with open(target, 'wb') as stream:
                    stream.write(b'encrypted-target')

            @contextmanager
            def channel(_):
                yield '/tmp/secret'

            with mock.patch.object(file_storage.qemu_volume, 'convert_qcow2_encryption', side_effect=convert):
                with mock.patch.object(file_storage.qemu_volume, 'is_luks_encrypted_image', return_value=True):
                    with mock.patch.object(file_storage.qemu_volume, 'verify_luks_open'):
                        with mock.patch.object(file_storage.qemu_volume, 'rebase_no_check_with_secret') as rebase:
                            with mock.patch.object(file_storage.secret, 'luks_secret_channel', channel):
                                file_storage.convert_items(SimpleNamespace(
                                    targetEncrypted=True, encryptedDek='wrapped', items=items))
            self.assertEqual(calls[0][1], calls[1][2])
            rebase.assert_called_once()
            self.assertEqual(base, rebase.call_args.args[0])
            self.assertTrue(os.path.exists(base))
            self.assertTrue(os.path.exists(child + '.trash'))

    def test_conversion_failure_removes_only_new_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            sources = [os.path.join(directory, 'source%d.qcow2' % index) for index in range(2)]
            targets = [os.path.join(directory, 'target%d.qcow2' % index) for index in range(2)]
            for source in sources:
                with open(source, 'wb') as stream:
                    stream.write(b'original source')
            items = [SimpleNamespace(resourceUuid=str(index), sourceInstallPath=sources[index],
                                     targetInstallPath=targets[index], targetBackingInstallPath=None)
                     for index in range(2)]
            cmd = SimpleNamespace(targetEncrypted=True, encryptedDek='wrapped', items=items)

            @contextmanager
            def channel(_):
                yield '/tmp/unused-secret'

            def convert(source, target, encrypted, secret_file, backing):
                if source == sources[1]:
                    raise RuntimeError('second item failed')
                with open(target, 'wb') as stream:
                    stream.write(b'created by this conversion')

            with mock.patch.object(file_storage.secret, 'luks_secret_channel', channel):
                with mock.patch.object(file_storage.qemu_volume, 'convert_qcow2_encryption', side_effect=convert):
                    with mock.patch.object(file_storage.qemu_volume, 'is_luks_encrypted_image', return_value=True):
                        with mock.patch.object(file_storage.qemu_volume, 'verify_luks_open'):
                            with self.assertRaisesRegex(RuntimeError, 'second item failed'):
                                file_storage.convert_items(cmd)
            for source in sources:
                with open(source, 'rb') as stream:
                    self.assertEqual(b'original source', stream.read())
            self.assertTrue(all(not os.path.exists(target) for target in targets))

    def test_conversion_rollback_continues_after_cleanup_or_restore_failure(self):
        for stage in ('target_unlink', 'temporary_unlink', 'restore_link', 'trash_unlink', 'concurrent', 'missing_trash'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                sources = [os.path.join(directory, 'source%d' % index) for index in range(3)]
                trash = [path + '.trash' for path in sources]
                for path in sources:
                    with open(path, 'wb') as stream:
                        stream.write(b'original-source')
                items = [SimpleNamespace(resourceUuid=str(index), sourceInstallPath=path,
                                         targetInstallPath=path, sourceTrashInstallPath=trash[index],
                                         targetBackingInstallPath=None)
                         for index, path in enumerate(sources)]
                cmd = SimpleNamespace(targetEncrypted=True, encryptedDek='wrapped', items=items)
                business = RuntimeError('wrapped /tmp/sensitive-channel publish failed')
                cleanup = OSError('wrapped /tmp/sensitive-channel cleanup failed')
                real_link, real_unlink = os.link, os.unlink
                temporary = []
                rolling_back = False

                def convert(source, target, *args):
                    temporary.append(target)
                    with open(target, 'xb') as stream:
                        stream.write(b'encrypted-output')

                def link(source, target):
                    nonlocal rolling_back
                    if source in temporary and target == sources[2]:
                        rolling_back = True
                        if stage == 'concurrent':
                            with open(target, 'xb') as stream:
                                stream.write(b'other-owner')
                        if stage == 'missing_trash':
                            real_unlink(trash[2])
                        raise business
                    if stage == 'restore_link' and source == trash[2]:
                        raise cleanup
                    real_link(source, target)

                def unlink(path):
                    if rolling_back and ((stage == 'target_unlink' and path == sources[0]) or
                                         (stage == 'temporary_unlink' and path == temporary[2]) or
                                         (stage == 'trash_unlink' and path == trash[2])):
                        raise cleanup
                    real_unlink(path)

                with mock.patch.object(volume, 'convert_qcow2_encryption', side_effect=convert), \
                        mock.patch.object(volume, 'is_luks_encrypted_image', return_value=True), \
                        mock.patch.object(volume, 'verify_luks_open'), \
                        mock.patch.object(os, 'link', side_effect=link), \
                        mock.patch.object(os, 'unlink', side_effect=unlink), \
                        mock.patch.object(file_storage, 'logger', logging.getLogger(file_storage.__name__), create=True), \
                        mock.patch.object(http_error, 'logger', logging.getLogger(file_storage.__name__)), \
                        mock.patch.object(logging.getLogger(file_storage.__name__), 'error') as logs:
                    with self.assertRaises(RuntimeError) as raised:
                        file_storage.convert_items(cmd)
                    self.assertIs(business, raised.exception)
                for index, path in enumerate(sources):
                    if stage in ('restore_link', 'missing_trash') and index == 2:
                        self.assertFalse(os.path.exists(path))
                    else:
                        expected = b'encrypted-output' if stage == 'target_unlink' and index == 0 else (
                            b'other-owner' if stage == 'concurrent' and index == 2 else b'original-source')
                        with open(path, 'rb') as stream:
                            self.assertEqual(expected, stream.read())
                    retained = (stage == 'target_unlink' and index == 0 or
                                stage in ('restore_link', 'trash_unlink', 'concurrent') and index == 2)
                    self.assertEqual(retained, os.path.exists(trash[index]))
                    if retained:
                        with open(trash[index], 'rb') as stream:
                            self.assertEqual(b'original-source', stream.read())
                        self.assertIn(trash[index], str(logs.call_args_list))
                self.assertEqual(stage == 'temporary_unlink', os.path.exists(temporary[2]))
                if stage == 'temporary_unlink':
                    self.assertIn(temporary[2], str(logs.call_args_list))
                if stage == 'missing_trash':
                    self.assertIn(trash[2], str(logs.call_args_list))
                    self.assertIn('FileNotFoundError', str(logs.call_args_list))
                self.assertTrue(logs.called)
                self.assertNotIn('wrapped', str(logs.call_args_list))
                self.assertNotIn('/tmp/sensitive-channel', str(logs.call_args_list))

    def test_batch_publication_and_source_move_cleanup_preserve_outcome(self):
        for stage in ('published_cleanup', 'source_unlink'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                source = os.path.join(directory, 'source')
                trash = source + '.trash'
                with open(source, 'wb') as stream:
                    stream.write(b'original')
                item = SimpleNamespace(resourceUuid='volume', sourceInstallPath=source,
                                       targetInstallPath=source, sourceTrashInstallPath=trash,
                                       targetBackingInstallPath=None)
                failure = OSError('injected unlink failure')
                temporary = []
                real_unlink = os.unlink

                def convert(src, dst, *args):
                    temporary.append(dst)
                    with open(dst, 'xb') as stream:
                        stream.write(b'encrypted')

                def unlink(path):
                    if path == (source if stage == 'source_unlink' else temporary[0]):
                        raise failure
                    real_unlink(path)

                with mock.patch.object(volume, 'convert_qcow2_encryption', side_effect=convert), \
                        mock.patch.object(volume, 'is_luks_encrypted_image', return_value=True), \
                        mock.patch.object(volume, 'verify_luks_open'), \
                        mock.patch.object(os, 'unlink', side_effect=unlink):
                    cmd = SimpleNamespace(items=[item], targetEncrypted=True, encryptedDek='wrapped')
                    if stage == 'source_unlink':
                        with self.assertRaises(OSError) as raised:
                            file_storage.convert_items(cmd)
                        self.assertIs(failure, raised.exception)
                    else:
                        self.assertEqual({'volume': len(b'encrypted')}, file_storage.convert_items(cmd))
                with open(source, 'rb') as stream:
                    self.assertEqual(b'original' if stage == 'source_unlink' else b'encrypted', stream.read())
                self.assertEqual(stage == 'published_cleanup', os.path.exists(trash))
                self.assertEqual(stage == 'published_cleanup', os.path.exists(temporary[0]))

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

    def test_snapshot_template_uses_crypto_without_plain_fallback(self):
        cmd = SimpleNamespace(encryptedDek='wrapped')

        @contextmanager
        def channel(_):
            yield '/tmp/one-shot-secret'

        def create_file(source, target, secret_file):
            with open(target, 'xb') as stream:
                stream.write(b'encrypted-template')

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(file_storage.secret, 'luks_secret_channel', channel):
            target = os.path.join(directory, 'template.qcow2')
            with mock.patch.object(file_storage.qemu_volume, 'create_encrypted_template',
                                   side_effect=create_file) as create:
                with mock.patch.object(file_storage.qemu_volume, 'verify_luks_open'):
                    actual = file_storage.create_template(cmd, '/source', target)
            self.assertTrue(actual)
            create.assert_called_once()
            self.assertEqual('/source', create.call_args.args[0])
            self.assertEqual(directory, os.path.dirname(create.call_args.args[1]))
            self.assertEqual('/tmp/one-shot-secret', create.call_args.args[2])
            with open(target, 'rb') as stream:
                self.assertEqual(b'encrypted-template', stream.read())

    def test_new_targets_are_published_only_after_verification(self):
        for operation, helper in ((file_storage.clone, 'clone_encrypted_qcow2'),
                                  (file_storage.create_template, 'create_encrypted_template')):
            for stage in ('target_key', 'source_key', 'existing', 'concurrent'):
                with self.subTest(operation=operation.__name__, stage=stage), \
                        tempfile.TemporaryDirectory() as directory:
                    source = os.path.join(directory, 'source.qcow2')
                    target = os.path.join(directory, 'target.qcow2')
                    with open(source, 'wb') as stream:
                        stream.write(b'original-source')
                    if stage == 'existing':
                        with open(target, 'wb') as stream:
                            stream.write(b'other-owner')
                    failure = RuntimeError('wrong key')

                    def create_file(source_path, output, secret_file, **kwargs):
                        with open(output, 'xb') as stream:
                            stream.write(b'encrypted-output')
                        if stage == 'concurrent' and output != target:
                            with open(target, 'xb') as stream:
                                stream.write(b'other-owner')

                    def verify(path, provider):
                        if (stage == 'source_key' and path == source or
                                stage == 'target_key' and path != source):
                            raise failure

                    with mock.patch.object(file_storage.secret, 'luks_secret_channel') as channel, \
                            mock.patch.object(volume, helper, side_effect=create_file) as create, \
                            mock.patch.object(volume, 'verify_luks_open', side_effect=verify) as verify_open:
                        channel.return_value.__enter__.return_value = '/tmp/one-shot-secret'
                        cmd = SimpleNamespace(encryptedDek='wrapped')
                        expected = FileExistsError if stage in ('existing', 'concurrent') else RuntimeError
                        with self.assertRaises(expected) as raised:
                            operation(cmd, source, target)
                        if stage in ('source_key', 'target_key'):
                            self.assertIs(failure, raised.exception)
                            self.assertEqual(['source.qcow2'], os.listdir(directory))
                        else:
                            with open(target, 'rb') as stream:
                                self.assertEqual(b'other-owner', stream.read())
                            self.assertEqual(['source.qcow2', 'target.qcow2'], sorted(os.listdir(directory)))
                        if stage in ('source_key', 'existing'):
                            create.assert_not_called()
                        if stage == 'existing':
                            verify_open.assert_not_called()
                        if stage == 'target_key':
                            verify_open.side_effect = None
                            self.assertTrue(operation(cmd, source, target))
                            self.assertEqual(['source.qcow2', 'target.qcow2'], sorted(os.listdir(directory)))
                            with open(target, 'rb') as stream:
                                self.assertEqual(b'encrypted-output', stream.read())
                    with open(source, 'rb') as stream:
                        self.assertEqual(b'original-source', stream.read())

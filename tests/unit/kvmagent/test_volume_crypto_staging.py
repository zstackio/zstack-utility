import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from kvmagent.crypto import http_error, qemu_volume as volume


class VolumeStagingTest(unittest.TestCase):
    def test_published_images_survive_temporary_unlink_failure(self):
        for operation in ('create', 'convert', 'template'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                source, target = Path(directory) / 'source', Path(directory) / 'target'
                source.write_bytes(b'original-source')
                temporary = []

                def run(command, **kwargs):
                    path = command[-2] if command[1] == 'create' else command[-1]
                    Path(path).write_bytes(b'encrypted-output')
                    temporary.append(path)

                with mock.patch.object(volume, 'run_checked', side_effect=run), \
                        mock.patch.object(volume, '_source_image_options', return_value=None), \
                        mock.patch.object(volume, 'is_luks_encrypted_image', side_effect=lambda path: path != str(source)), \
                        mock.patch.object(volume, 'verify_luks_open'), \
                        mock.patch.object(volume.subprocess, 'check_output', return_value=b'{"format":"qcow2"}'), \
                        mock.patch.object(os, 'unlink', side_effect=OSError('wrapped /tmp/secret cleanup failed')), \
                        mock.patch.object(volume, 'logger', logging.getLogger(volume.__name__)), \
                        mock.patch.object(http_error, 'logger', logging.getLogger(volume.__name__)), \
                        mock.patch.object(logging.getLogger(volume.__name__), 'error') as logs:
                    if operation == 'create':
                        volume.create_encrypted_qcow2(str(target), 4096, '/tmp/secret')
                    elif operation == 'convert':
                        volume.convert_qcow2_encryption(str(source), str(target), volume.EncryptionMode.LUKS, '/tmp/secret')
                    else:
                        volume.create_encrypted_template(str(source), str(target), '/tmp/secret')
                self.assertEqual(b'encrypted-output', target.read_bytes())
                self.assertEqual(b'original-source', source.read_bytes())
                self.assertTrue(os.path.samefile(target, temporary[0]))
                self.assertIn(temporary[0], str(logs.call_args_list))
                self.assertNotIn('wrapped', str(logs.call_args_list))
                self.assertNotIn('/tmp/secret', str(logs.call_args_list))

    def test_stage_preserves_body_error_when_cleanup_also_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            failure = RuntimeError('original operation failed')
            with mock.patch.object(os, 'unlink', side_effect=OSError('cleanup failed')):
                with self.assertRaises(RuntimeError) as raised:
                    with volume.staged_file(str(target)) as temporary:
                        Path(temporary).write_bytes(b'partial-output')
                        raise failure
            self.assertIs(failure, raised.exception)
            self.assertFalse(target.exists())
            self.assertEqual(b'partial-output', Path(temporary).read_bytes())

    def test_stage_never_overwrites_existing_or_concurrent_target(self):
        for kind in ('existing', 'dangling_symlink', 'concurrent'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'target'
                if kind == 'existing':
                    target.write_bytes(b'other-owner')
                elif kind == 'dangling_symlink':
                    target.symlink_to('missing-source')
                with self.assertRaises(FileExistsError):
                    with volume.staged_file(str(target)) as temporary:
                        self.assertEqual('concurrent', kind)
                        self.assertEqual(directory, os.path.dirname(temporary))
                        Path(temporary).write_bytes(b'new-output')
                        target.write_bytes(b'other-owner')
                if kind == 'dangling_symlink':
                    self.assertEqual('missing-source', os.readlink(target))
                else:
                    self.assertEqual(b'other-owner', target.read_bytes())
                self.assertEqual(['target'], os.listdir(directory))

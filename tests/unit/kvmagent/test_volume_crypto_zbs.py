import logging
import os
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import mock

from kvmagent.crypto import http_error
from kvmagent.crypto.zbs import operations as zbs


class ZbsCryptoTest(unittest.TestCase):
    def test_initialize_cleanup_preserves_business_failure_and_logs_safely(self):
        real_unlink = os.unlink
        for stage in ('cryptsetup', 'convert', 'success'):
            with self.subTest(stage=stage):
                business_error = RuntimeError('wrapped /tmp/one-shot-secret')
                cleanup_error = OSError('wrapped /tmp/one-shot-secret')
                commands = []

                def run(command):
                    commands.append(command)
                    if stage == 'cryptsetup' or (stage == 'convert' and command[1] == 'convert'):
                        raise business_error

                try:
                    with mock.patch.object(zbs.secret, 'luks_secret_channel',
                                           return_value=nullcontext('/tmp/one-shot-secret')), \
                            mock.patch.object(zbs, 'run_checked', side_effect=run), \
                            mock.patch.object(zbs, '_verify') as verify, \
                            mock.patch.object(zbs.os, 'unlink', side_effect=cleanup_error) as unlink, \
                            mock.patch.object(http_error, 'logger', logging.getLogger('zbs-initialize-test')), \
                            self.assertLogs('zbs-initialize-test', level='ERROR') as logs:
                        with self.assertRaises(Exception) as raised:
                            zbs._initialize('cbd:physical/logical/volume', 4096, 'wrapped')
                        self.assertIs(cleanup_error if stage == 'success' else business_error, raised.exception)
                        unlink.assert_called_once_with(commands[0][-1])
                        verify.assert_not_called()
                    self.assertIn('stage=temporary_file_cleanup', '\n'.join(logs.output))
                    self.assertNotIn('wrapped', '\n'.join(logs.output))
                    self.assertNotIn('/tmp/one-shot-secret', '\n'.join(logs.output))
                finally:
                    if commands and os.path.exists(commands[0][-1]):
                        real_unlink(commands[0][-1])

    def test_public_format_query_preserves_luks_detection(self):
        for image_format in ('luks', 'raw'):
            with self.subTest(image_format=image_format):
                with mock.patch.object(zbs, '_info', return_value={'format': image_format}) as info:
                    self.assertEqual(image_format == 'luks',
                                     zbs.is_encrypted('cbd:physical/logical/volume'))
                info.assert_called_once_with('cbd:physical/logical/volume')

    def test_public_format_query_rejects_vhost_before_qemu_probe(self):
        with mock.patch.object(zbs, 'check_output') as probe:
            with self.assertRaisesRegex(ValueError, 'CBD'):
                zbs.is_encrypted('/var/run/zbs/vhost-volume.sock')
        probe.assert_not_called()

    def test_vhost_path_is_rejected_before_any_write(self):
        with self.assertRaisesRegex(ValueError, 'CBD'):
            zbs._path('/var/run/zbs/vhost-volume.sock')
        with self.assertRaisesRegex(ValueError, 'CBD'):
            zbs._path('cbd:pool/logical/volume@snapshot')

    def test_create_formats_local_luks1_header_then_copies_to_precreated_cbd(self):
        cmd = SimpleNamespace(installPath='cbd:physical/logical/volume',
                              size=8 * 1024 * 1024, encryptedDek='wrapped')
        with mock.patch.object(zbs.lock, 'NamedLock', return_value=nullcontext(), create=True), \
                mock.patch.object(zbs, '_qemu_info', return_value={'format': 'raw'}), \
                mock.patch.object(zbs.secret, 'luks_secret_channel') as channel:
            channel.return_value.__enter__.return_value = '/tmp/one-shot-secret'
            with mock.patch.object(zbs, 'run_checked') as call:
                with mock.patch.object(zbs, '_verify', return_value=4096):
                    self.assertEqual(4096, zbs.create_empty(cmd))
        commands = [item.args[0] for item in call.call_args_list]
        self.assertEqual('/usr/sbin/cryptsetup', commands[0][0])
        self.assertIn('--align-payload=16384', commands[0])
        self.assertIn('/tmp/one-shot-secret', commands[0])
        self.assertIn('cbd:physical/logical/volume_zbs_:/etc/zbs/client.conf', commands[1])
        self.assertNotIn('wrapped', str(commands))
        self.assertFalse(os.path.exists(commands[0][-1]))

    def test_clone_reads_resolved_snapshot_into_separate_target(self):
        cmd = SimpleNamespace(srcPath='cbd:physical/logical/source@17',
                              dstPath='cbd:physical/logical/target', encryptedDek='wrapped')
        source = 'cbd:physical/logical/source@17_zbs_:/etc/zbs/client.conf'
        target = 'cbd:physical/logical/target_zbs_:/etc/zbs/client.conf'
        for image_format in ('raw', 'luks'):
            with self.subTest(image_format=image_format):
                with mock.patch.object(zbs, 'check_output',
                                       return_value='{"format":"%s","virtual-size":4096}' % image_format) as probe, \
                        mock.patch.object(zbs, 'run_checked') as convert, \
                        mock.patch.object(zbs, '_initialize') as initialize, \
                        mock.patch.object(zbs, '_verify', return_value=1024), \
                        mock.patch.object(zbs.secret, 'luks_secret_channel') as channel:
                    channel.return_value.__enter__.return_value = '/tmp/secret'
                    self.assertEqual(1024, zbs.clone(cmd))

                self.assertEqual(source, probe.call_args_list[0].args[0][-1])
                self.assertIn(source, convert.call_args.args[0])
                if image_format == 'raw':
                    initialize.assert_called_once_with(cmd.dstPath, 4096, cmd.encryptedDek)
                    self.assertIn('file.filename=%s' % target, convert.call_args.args[0][-1])
                else:
                    initialize.assert_not_called()
                    self.assertEqual(target, convert.call_args.args[0][-1])
                    self.assertIn('file.filename=%s' % source, probe.call_args_list[2].args[0][-1])

    def test_clone_rejects_unresolved_source_and_any_snapshot_target(self):
        with mock.patch.object(zbs, 'check_output') as probe:
            for source, target in (('source@snapshot-name', 'target'), ('source', 'target@17')):
                with self.subTest(source=source, target=target):
                    cmd = SimpleNamespace(srcPath='cbd:physical/logical/' + source,
                                          dstPath='cbd:physical/logical/' + target, encryptedDek='wrapped')
                    with self.assertRaisesRegex(ValueError, 'CBD volume path'):
                        zbs.clone(cmd)
            with self.assertRaisesRegex(ValueError, 'CBD volume path'):
                zbs.is_encrypted('cbd:physical/logical/source@17')
        probe.assert_not_called()

if __name__ == '__main__':
    unittest.main()

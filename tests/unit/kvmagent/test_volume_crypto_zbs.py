import logging
import os
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import mock

from kvmagent.crypto import http_error
from kvmagent.crypto.zbs import http as zbs_http
from kvmagent.crypto.zbs import operations as zbs
from zstacklib.utils import http, jsonobject


class ZbsCryptoTest(unittest.TestCase):
    def test_initialize_cleanup_preserves_business_failure_and_logs_safely(self):
        real_unlink = os.unlink
        for stage in ('cryptsetup', 'convert', 'success'):
            with self.subTest(stage=stage):
                business_error = RuntimeError('wrapped /tmp/one-shot-secret')
                cleanup_error = OSError('wrapped /tmp/one-shot-secret')
                commands = []

                def run(command, **kwargs):
                    commands.append(command)
                    if stage == 'cryptsetup' or (stage == 'convert' and command[1] == 'convert'):
                        raise business_error

                try:
                    with tempfile.NamedTemporaryFile() as key_file, \
                            mock.patch.object(zbs.secret, 'luks_secret_channel',
                                              return_value=nullcontext(key_file.name)), \
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
        key = b'binary\nkey\x00suffix'

        def run(command, **kwargs):
            if command[1] == '-q':
                self.assertEqual(key, kwargs['stdin'].read())

        with tempfile.NamedTemporaryFile() as key_file, \
                mock.patch.object(zbs.lock, 'NamedLock', return_value=nullcontext(), create=True), \
                mock.patch.object(zbs, '_qemu_info', return_value={'format': 'raw'}), \
                mock.patch.object(zbs.secret, 'luks_secret_channel',
                                  return_value=nullcontext(key_file.name)), \
                mock.patch.object(zbs, 'run_checked', side_effect=run) as call, \
                mock.patch.object(zbs, '_verify', return_value=4096):
            key_file.write(key)
            key_file.flush()
            self.assertEqual(4096, zbs.create_empty(cmd))
            commands = [item.args[0] for item in call.call_args_list]
            self.assertNotIn(key_file.name, commands[0])

        self.assertEqual('/usr/sbin/cryptsetup', commands[0][0])
        self.assertIn('--align-payload=16384', commands[0])
        self.assertEqual(['--key-file', '-'], commands[0][-3:-1])
        self.assertIn('cbd:physical/logical/volume_zbs_:/etc/zbs/client.conf', commands[1])
        self.assertNotIn('wrapped', str(commands))
        self.assertTrue(call.call_args_list[0].kwargs['stdin'].closed)
        self.assertFalse(os.path.exists(commands[0][-1]))

    def test_missing_secret_channel_does_not_leak_path_in_create_response(self):
        cmd = SimpleNamespace(installPath='cbd:physical/logical/volume', size=4096, encryptedDek='wrapped')
        with tempfile.TemporaryDirectory() as workspace:
            missing_path = os.path.join(workspace, 'missing-channel')
            with mock.patch.object(zbs.lock, 'NamedLock', return_value=nullcontext(), create=True), \
                    mock.patch.object(zbs, '_qemu_info', return_value={'format': 'raw'}), \
                    mock.patch.object(zbs.secret, 'prepare_luks_secret_material_channel', return_value=missing_path), \
                    mock.patch.object(zbs, 'run_checked') as run:
                rsp = zbs_http.create({http.REQUEST_BODY: jsonobject.dumps(cmd.__dict__)})
        self.assertFalse(jsonobject.loads(rsp).success)
        self.assertNotIn(missing_path, rsp)
        run.assert_not_called()

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

    def test_decrypt_reads_luks_source_into_precreated_plain_target(self):
        cmd = SimpleNamespace(installPath='cbd:physical/logical/source',
                              targetInstallPath='cbd:physical/logical/target',
                              targetEncrypted=False, encryptedDek='wrapped')
        with mock.patch.object(zbs, '_encrypted', return_value=True):
            with mock.patch.object(zbs.secret, 'luks_secret_channel') as channel:
                channel.return_value.__enter__.return_value = '/tmp/one-shot-secret'
                with mock.patch.object(zbs, 'run_checked') as call:
                    with mock.patch.object(zbs, '_verify', return_value=8192):
                        self.assertEqual(8192, zbs.convert(cmd))
        command = call.call_args.args[0]
        self.assertIn('--image-opts', command)
        self.assertIn('-O', command)
        self.assertEqual('raw', command[command.index('-O') + 1])
        self.assertIn('cbd:physical/logical/target_zbs_:/etc/zbs/client.conf', command)


    def test_encrypted_nbd_chain_download_closes_qsd_and_removes_workspace(self):
        cmd = SimpleNamespace(primaryStorageInstallPath='cbd:physical/logical/target',
                              backupStorageHostname='imagestore', backupStorageNbdPort=10809,
                              backupStorageNbdExportNames=['base', 'leaf'],
                              encryptedDek='wrapped', sourceEncrypted=True)
        real_exists = os.path.exists
        with mock.patch.object(zbs, '_verify', return_value=4096):
            with mock.patch.object(zbs.secret, 'luks_secret_channel') as channel:
                channel.return_value.__enter__.return_value = '/tmp/one-shot-secret'
                with mock.patch.object(zbs.subprocess, 'Popen') as popen:
                    popen.return_value.poll.return_value = None
                    with mock.patch.object(zbs.os.path, 'exists',
                                           side_effect=lambda path: path.endswith('source.sock') or real_exists(path)):
                        with mock.patch.object(zbs, 'run_checked') as call:
                            self.assertEqual(4096, zbs.download_encrypted_imagestore(cmd))
        daemon_command = popen.call_args.args[0]
        self.assertIn('secret,id=luks_sec,format=raw,file=/tmp/one-shot-secret', daemon_command)
        self.assertEqual(2, daemon_command.count('--blockdev') // 2)
        target_command = call.call_args.args[0]
        self.assertIn('--target-image-opts', target_command)
        self.assertIn('nbd+unix:///top?socket=', ' '.join(target_command))
        popen.return_value.terminate.assert_called_once()
        workspace = daemon_command[-3].split('addr.path=')[1]
        self.assertFalse(real_exists(os.path.dirname(workspace)))

    def test_nbd_teardown_preserves_business_errors_and_unreaped_workspace(self):
        cmd = SimpleNamespace(primaryStorageInstallPath='cbd:physical/logical/target',
                              backupStorageHostname='imagestore', backupStorageNbdPort=10809,
                              backupStorageNbdExportNames=['leaf'], encryptedDek='wrapped')
        real_rmtree = zbs.shutil.rmtree
        for body in ('success', 'convert', 'verify'):
            for stage in ('normal', 'timeout', 'terminate', 'wait', 'kill', 'final_wait', 'final_timeout', 'rmtree', 'poll'):
                with self.subTest(body=body, stage=stage), \
                        mock.patch.object(zbs, '_verify', return_value=4096) as verify, \
                        mock.patch.object(zbs.secret, 'luks_secret_channel') as channel, \
                        mock.patch.object(zbs.subprocess, 'Popen') as popen, \
                        mock.patch.object(zbs, 'run_checked') as convert, \
                        mock.patch.object(zbs.shutil, 'rmtree', side_effect=real_rmtree) as remove, \
                        mock.patch.object(zbs, 'logger', logging.getLogger(zbs.__name__)), \
                        mock.patch.object(http_error, 'logger', logging.getLogger(zbs.__name__)):
                    channel.return_value.__enter__.return_value = '/tmp/sensitive-channel'
                    process = popen.return_value
                    process.poll.return_value = None
                    process.pid = 12345
                    failure = OSError('wrapped /tmp/sensitive-channel cleanup failed')
                    business = RuntimeError('wrapped /tmp/sensitive-channel business failed')
                    timeout = zbs.subprocess.TimeoutExpired(['qemu-storage-daemon', 'wrapped', '/tmp/sensitive-channel'], 10)
                    if stage == 'final_timeout':
                        failure = timeout
                    if stage in ('timeout', 'terminate', 'kill', 'final_wait', 'final_timeout'):
                        process.wait.side_effect = [timeout, failure if stage in ('final_wait', 'final_timeout') else 0]
                    if stage == 'wait':
                        process.wait.side_effect = [failure, 0]
                    if stage in ('terminate', 'kill', 'poll'):
                        getattr(process, stage).side_effect = failure
                    if stage == 'rmtree':
                        remove.side_effect = failure
                    if body == 'convert':
                        convert.side_effect = business
                    elif body == 'verify':
                        verify.side_effect = [4096, business]
                    workspaces = []

                    def launch(command, stdout, **kwargs):
                        workspace = os.path.dirname(stdout.name)
                        workspaces.append(workspace)
                        self.addCleanup(real_rmtree, workspace, ignore_errors=True)
                        stdout.write('QSD diagnostic output')
                        with open(os.path.join(workspace, 'source.sock'), 'w'):
                            pass
                        return process

                    popen.side_effect = launch
                    expected = business if body != 'success' else (
                        None if stage in ('normal', 'timeout') else failure)
                    with mock.patch.object(logging.getLogger(zbs.__name__), 'error') as logs:
                        if expected is None:
                            self.assertEqual(4096, zbs.download_encrypted_imagestore(cmd))
                        else:
                            with self.assertRaises(type(expected)) as raised:
                                zbs.download_encrypted_imagestore(cmd)
                            self.assertIs(expected, raised.exception)
                    retained = stage in ('final_wait', 'final_timeout', 'rmtree')
                    self.assertEqual(retained, os.path.exists(workspaces[0]))
                    if retained:
                        self.assertTrue(os.path.exists(os.path.join(workspaces[0], 'qsd.log')))
                    for call in process.wait.call_args_list:
                        self.assertEqual(mock.call(timeout=10), call)
                    if stage in ('timeout', 'terminate', 'wait', 'kill', 'final_wait', 'final_timeout'):
                        process.kill.assert_called_once_with()
                        self.assertEqual(2, process.wait.call_count)
                    if stage not in ('normal', 'timeout'):
                        self.assertTrue(logs.called)
                    messages = str(logs.call_args_list)
                    self.assertNotIn('wrapped', messages)
                    self.assertNotIn('/tmp/sensitive-channel', messages)
                    if stage in ('final_wait', 'final_timeout'):
                        self.assertIn(workspaces[0], messages)
                        self.assertIn('12345', messages)

    def test_nbd_startup_failure_is_diagnosed_before_workspace_cleanup(self):
        cmd = SimpleNamespace(primaryStorageInstallPath='cbd:physical/logical/target',
                              backupStorageHostname='imagestore', backupStorageNbdPort=10809,
                              backupStorageNbdExportNames=['leaf'],
                              encryptedDek='wrapped', sourceEncrypted=True)
        cases = (
            (b'Invalid password, cannot unlock any keyslot', 1, 'qsd_startup', 'source_key_rejected'),
            (b'Failed to connect to host: Connection refused', 2, 'qsd_startup', 'source_nbd_connection_failed'),
            (b'Image is not in qcow2 format', 3, 'qsd_startup', 'source_not_qcow2'),
            (b'Unrecognized error', 4, 'qsd_startup', 'unknown'),
            (b'', None, 'qsd_startup_timeout', 'unknown'),
        )
        for diagnostic, returncode, stage, reason in cases:
            with self.subTest(stage=stage, reason=reason), \
                    mock.patch.object(zbs, 'logger', logging.getLogger(zbs.__name__)), \
                    mock.patch.object(zbs, '_verify'), mock.patch.object(zbs.time, 'sleep'), \
                    mock.patch.object(zbs.secret, 'luks_secret_channel') as channel, \
                    mock.patch.object(zbs.subprocess, 'Popen') as popen, \
                    mock.patch.object(zbs, 'run_checked') as convert:
                channel.return_value.__enter__.return_value = '/tmp/sensitive-channel'
                popen.return_value.poll.return_value = returncode
                workspaces = []

                def launch(command, stdout, **kwargs):
                    stdout.write('x' * 4096 + ' /tmp/sensitive-channel wrapped: ' + diagnostic.decode())
                    workspaces.append(os.path.dirname(stdout.name))
                    return popen.return_value

                popen.side_effect = launch
                with self.assertLogs(zbs.__name__, level='ERROR') as logs:
                    rsp = jsonobject.loads(zbs_http.encrypted_download({http.REQUEST_BODY: jsonobject.dumps(vars(cmd))}))
                self.assertFalse(rsp.success)
                for message in (logs.output[0], rsp.error):
                    self.assertIn(stage, message)
                    self.assertIn('returncode=%s' % returncode, message)
                    self.assertIn('reason=%s' % reason, message)
                    self.assertNotIn('/tmp/sensitive-channel', message)
                    self.assertNotIn('wrapped', message)
                    self.assertNotIn('Connection refused', message)
                self.assertFalse(os.path.exists(workspaces[0]))
                convert.assert_not_called()


if __name__ == '__main__':
    unittest.main()

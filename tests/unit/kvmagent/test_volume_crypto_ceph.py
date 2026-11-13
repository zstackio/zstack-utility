import json
import logging
import subprocess
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import mock

from kvmagent.crypto.ceph import operations as ceph
from kvmagent.crypto import http_error
from kvmagent.crypto.volume_request import EncryptionMode


class CephCryptoTest(unittest.TestCase):
    def setUp(self):
        client_conf = mock.patch.object(
            ceph.ceph_utils, 'get_ceph_client_conf',
            side_effect=lambda ps_uuid, manufacturer: (None, None,
                                                        None if manufacturer == 'xsky' else 'client.zstack'))
        client_conf.start()
        self.addCleanup(client_conf.stop)

    def test_in_place_plaintext_cleanup_sets_the_completion_boundary(self):
        cmd = SimpleNamespace(installPath='ceph://pool/target', encryptedDek='wrapped')
        source = 'pool/target'
        backup = source + '-luks-original'
        for outcome in ('deleted', 'deleted_but_reply_lost', 'delete_failed', 'restore_failed'):
            with self.subTest(outcome=outcome), \
                    mock.patch.object(ceph.lock, 'NamedLock', return_value=nullcontext(), create=True), \
                    mock.patch.multiple(ceph, _config=mock.DEFAULT, _info=mock.DEFAULT, _convert=mock.DEFAULT,
                                        _rbd_exists=mock.DEFAULT, _rbd_rename=mock.DEFAULT,
                                        _rbd_remove=mock.DEFAULT, _verified_state=mock.DEFAULT) as backend:
                images = {source: 'raw'}
                backend['_info'].side_effect = lambda name, _: {'format': images[name]}
                backend['_rbd_exists'].side_effect = lambda name, _: name in images
                backend['_convert'].side_effect = lambda _, dest, *args: images.update({dest: 'luks'})

                def rename(old, new, _):
                    self.assertNotIn(new, images)
                    if old == backup and outcome == 'restore_failed':
                        raise subprocess.CalledProcessError(5, ['rbd', 'mv'])
                    images[new] = images.pop(old)

                def remove(name, _):
                    if name != backup or outcome in ('deleted', 'deleted_but_reply_lost'):
                        del images[name]
                    if name == backup and outcome != 'deleted':
                        raise subprocess.CalledProcessError(5, ['rbd', 'rm'])

                backend['_rbd_rename'].side_effect = rename
                backend['_rbd_remove'].side_effect = remove
                if outcome in ('deleted', 'deleted_but_reply_lost'):
                    self.assertEqual(cmd.installPath, ceph.encrypt_in_place(cmd))
                    self.assertEqual(cmd.installPath, ceph.encrypt_in_place(cmd))
                    backend['_verified_state'].assert_called_once_with(source, mock.ANY, EncryptionMode.LUKS, cmd.encryptedDek)
                    backend['_convert'].assert_called_once()
                    self.assertEqual({source: 'luks'}, images)
                else:
                    with self.assertRaises(subprocess.CalledProcessError):
                        ceph.encrypt_in_place(cmd)
                    if outcome == 'delete_failed':
                        self.assertEqual({source: 'raw'}, images)
                    else:
                        self.assertEqual({source: 'luks', backup: 'raw'}, images)
                        with self.assertRaisesRegex(RuntimeError, 'backup already exists'):
                            ceph.encrypt_in_place(cmd)
                        backend['_convert'].assert_called_once()

    def test_rbd_probe_distinguishes_missing_image_from_permission_error(self):
        with mock.patch.object(ceph, '_rbd_command', return_value=['rbd', 'info', 'pool/image']), \
                mock.patch.object(ceph.subprocess, 'run') as run:
            run.return_value = subprocess.CompletedProcess(['rbd'], 2, stderr=b'No such file or directory')
            self.assertFalse(ceph._rbd_exists('pool/image', 'config'))
            run.return_value = subprocess.CompletedProcess(['rbd'], 13, stderr=b'Permission denied')
            with self.assertRaises(subprocess.CalledProcessError):
                ceph._rbd_exists('pool/image', 'config')

    def test_losing_publish_does_not_remove_the_concurrent_rbd(self):
        cmd = SimpleNamespace(installPath='ceph://pool/target', srcPath='ceph://pool/source',
                              dstPath='ceph://pool/target', size=8 * 1024 * 1024, encryptedDek='wrapped')
        for operation in (ceph.create_empty, ceph.clone):
            with self.subTest(operation=operation.__name__), mock.patch.multiple(ceph, _config=mock.DEFAULT,
                    _uri=mock.DEFAULT, _rbd_exists=mock.DEFAULT, _rbd_rename=mock.DEFAULT,
                    _rbd_remove=mock.DEFAULT, _info=mock.DEFAULT, _verified_state=mock.DEFAULT) as backend:
                target = 'pool/target'
                images = {'pool/source': 'template'}
                backend['_uri'].side_effect = lambda image, config: image
                backend['_rbd_exists'].side_effect = lambda image, config: image in images
                backend['_rbd_remove'].side_effect = lambda image, config: images.pop(image)
                backend['_info'].return_value = {'format': 'raw'}

                def write(command):
                    image = command[-2] if command[1] == 'create' else command[-1]
                    images[target] = 'other request'
                    if image == target:
                        raise FileExistsError(target)
                    images[image] = 'this request'

                def publish(source, destination, config):
                    self.assertEqual(target, destination)
                    self.assertEqual('this request', images[source])
                    raise FileExistsError(destination)

                backend['_rbd_rename'].side_effect = publish
                with mock.patch.object(ceph.secret, 'luks_secret_channel', return_value=nullcontext('/tmp/test-secret')), \
                     mock.patch.object(ceph, 'run_checked', side_effect=write):
                    with self.assertRaises(FileExistsError):
                        operation(cmd)
                self.assertEqual({'pool/source': 'template', target: 'other request'}, images)

    def test_encrypted_clone_passes_snapshot_as_rbd_option(self):
        cmd = SimpleNamespace(psUuid='ps-uuid', srcPath='ceph://pool/source@snap',
                              dstPath='ceph://pool/target', encryptedDek='test-envelope')
        with mock.patch.object(ceph, '_config', return_value='/etc/ceph.conf'):
            with mock.patch.object(ceph, '_username', return_value='client.zstack'):
                with mock.patch.object(ceph, '_rbd_exists', return_value=False):
                    with mock.patch.object(ceph, '_info', side_effect=[{'format': 'luks'}, {'format': 'luks'}]):
                        with mock.patch.object(ceph.secret, 'luks_secret_channel') as channel:
                            channel.return_value.__enter__.return_value = '/tmp/test-secret'
                            with mock.patch.object(ceph, 'run_checked') as convert:
                                with mock.patch.object(ceph.subprocess, 'check_output', return_value=b'[]'):
                                    self.assertTrue(ceph.clone(cmd))
        args, publish = [call.args[0] for call in convert.call_args_list]
        self.assertEqual(['mv', args[-1].split(':')[1], 'pool/target'], publish[-3:])
        self.assertEqual('driver=luks,key-secret=luks_sec,file.driver=rbd,file.pool=pool,'
                         'file.image=source,file.snapshot=snap,file.conf=/etc/ceph.conf,file.user=zstack',
                         args[args.index('--image-opts') + 1])

    def test_ceph_image_options_without_snapshot_remain_unchanged(self):
        with mock.patch.object(ceph, '_username', return_value=None):
            self.assertEqual('driver=luks,key-secret=luks_sec,file.driver=rbd,file.pool=pool,'
                             'file.image=source,file.conf=/etc/ceph.conf',
                             ceph._image_options('pool/source', '/etc/ceph.conf'))

    def test_public_format_query_keeps_storage_config_before_image_probe(self):
        for image_format in ('luks', 'raw'):
            with self.subTest(image_format=image_format):
                events = []

                def config(cmd):
                    events.append(('config', cmd.psUuid))
                    return '/etc/ceph.conf'

                def image_path(install_path):
                    events.append(('path', install_path))
                    return 'pool/disk'

                def info(image, config_path):
                    events.append(('info', image, config_path))
                    return {'format': image_format}

                with mock.patch.object(ceph, '_config', side_effect=config):
                    with mock.patch.object(ceph, '_image_path', side_effect=image_path):
                        with mock.patch.object(ceph, '_info', side_effect=info):
                            self.assertEqual(image_format == 'luks',
                                             ceph.is_encrypted('ceph://pool/disk', 'ps-uuid'))
                self.assertEqual([('config', 'ps-uuid'), ('path', 'ceph://pool/disk'),
                                  ('info', 'pool/disk', '/etc/ceph.conf')], events)

    def test_public_format_query_rejects_missing_storage_before_probe(self):
        with mock.patch.object(ceph, '_info') as info:
            with self.assertRaisesRegex(ValueError, 'psUuid'):
                ceph.is_encrypted('ceph://pool/disk', None)
        info.assert_not_called()

    def test_ceph_commands_use_existing_client_identity(self):
        with mock.patch.object(ceph.ceph_utils, 'get_ceph_manufacturer', return_value='open-source'):
            self.assertIn(':id=zstack:conf=', ceph._uri('pool/disk', '/var/lib/zstack/ceph/ps/ceph.conf'))
            self.assertIn('file.user=zstack', ceph._image_options('pool/disk', '/var/lib/zstack/ceph/ps/ceph.conf'))
            self.assertEqual(['--id', 'zstack'], ceph._rbd_command('/var/lib/zstack/ceph/ps/ceph.conf')[3:])
        with mock.patch.object(ceph.ceph_utils, 'get_ceph_manufacturer', return_value='xsky'):
            self.assertNotIn(':id=', ceph._uri('pool/disk', '/var/lib/zstack/ceph/ps/ceph.conf'))

    def test_failed_clone_conversion_removes_only_new_target(self):
        cmd = SimpleNamespace(srcPath='ceph://pool/source', dstPath='ceph://pool/target', encryptedDek='wrapped')
        with mock.patch.object(ceph, '_config', return_value='/etc/ceph.conf'), \
             mock.patch.object(ceph, '_rbd_exists', side_effect=[False, True]):
            with mock.patch.object(ceph, '_info', return_value={'format': 'raw'}):
                with mock.patch.object(ceph.secret, 'luks_secret_channel') as channel:
                    channel.return_value.__enter__.return_value = '/tmp/secret'
                    with mock.patch.object(ceph, 'run_checked', side_effect=RuntimeError('convert failed')):
                        with mock.patch.object(ceph, '_rbd_remove') as remove:
                            with self.assertRaisesRegex(RuntimeError, 'convert failed'):
                                ceph.clone(cmd)
        remove.assert_called_once()
        self.assertTrue(remove.call_args.args[0].startswith('pool/target-converting-'))

    def test_failed_conversion_format_verification_removes_new_target(self):
        cmd = SimpleNamespace(srcPath='ceph://pool/source', dstPath='ceph://pool/target', encryptedDek='wrapped')
        with mock.patch.object(ceph, '_config', return_value='/etc/ceph.conf'), \
             mock.patch.object(ceph, '_rbd_exists', side_effect=[False, True]):
            with mock.patch.object(ceph, '_info', return_value={'format': 'raw'}):
                with mock.patch.object(ceph.secret, 'luks_secret_channel') as channel:
                    channel.return_value.__enter__.return_value = '/tmp/secret'
                    with mock.patch.object(ceph, 'run_checked') as convert:
                        with mock.patch.object(ceph, '_rbd_remove') as remove:
                            with self.assertRaisesRegex(RuntimeError, 'format verification failed'):
                                ceph.clone(cmd)
        convert.assert_called_once()
        remove.assert_called_once_with(convert.call_args.args[0][-1].split(':')[1], '/etc/ceph.conf')

    def test_failed_create_key_verification_removes_new_target(self):
        cmd = SimpleNamespace(psUuid='ps-uuid', installPath='ceph://pool/target',
                              size=8 * 1024 * 1024, encryptedDek='wrapped')
        with mock.patch.object(ceph.os.path, 'isfile', return_value=True):
            with mock.patch.object(ceph, '_rbd_exists', side_effect=[False, True]):
                with mock.patch.object(ceph, '_info', return_value={'format': 'luks'}):
                    with mock.patch.object(ceph.secret, 'luks_secret_channel') as channel:
                        channel.return_value.__enter__.return_value = '/tmp/secret'
                        with mock.patch.object(ceph, 'run_checked') as create:
                            with mock.patch.object(ceph.subprocess, 'check_output', side_effect=RuntimeError('key verification failed')):
                                with mock.patch.object(ceph, '_rbd_remove') as remove:
                                    with self.assertRaisesRegex(RuntimeError, 'key verification failed'):
                                        ceph.create_empty(cmd)
        create.assert_called_once()
        remove.assert_called_once_with(create.call_args.args[0][-2].split(':')[1], mock.ANY)

    def test_failed_clone_resize_cleans_the_staged_image_without_publishing(self):
        cmd = SimpleNamespace(srcPath='ceph://pool/source', dstPath='ceph://pool/target', encryptedDek='wrapped',
                              virtualSizeForLuksClone=16 * 1024 * 1024)
        with mock.patch.multiple(ceph, _config=mock.DEFAULT, _rbd_exists=mock.DEFAULT, _convert=mock.DEFAULT,
                                 _resize=mock.DEFAULT, _rbd_rename=mock.DEFAULT, _rbd_remove=mock.DEFAULT) as backend:
            backend['_config'].return_value = '/etc/ceph.conf'
            backend['_rbd_exists'].side_effect = [False, True]
            backend['_resize'].side_effect = RuntimeError('resize failed')
            with self.assertRaisesRegex(RuntimeError, 'resize failed'):
                ceph.clone(cmd)

        staged_image = backend['_convert'].call_args.args[1]
        backend['_resize'].assert_called_once_with(staged_image, '/etc/ceph.conf', cmd.virtualSizeForLuksClone, 'wrapped')
        backend['_rbd_remove'].assert_called_once_with(staged_image, '/etc/ceph.conf')
        backend['_rbd_rename'].assert_not_called()

    def test_stage_cleanup_failure_reports_owned_rbd_and_preserves_original_error(self):
        error = RuntimeError('private business detail')
        with mock.patch.object(ceph, '_rbd_exists', return_value=True), \
                mock.patch.object(ceph, '_rbd_remove', side_effect=OSError('private cleanup detail')) as remove, \
                mock.patch.object(http_error, 'logger', logging.getLogger('ceph-stage-test')), \
                self.assertLogs('ceph-stage-test', level='ERROR') as logs:
            with self.assertRaises(RuntimeError) as caught:
                with ceph._stage_rbd('pool/target', '/etc/ceph.conf') as temporary:
                    raise error

        self.assertIs(error, caught.exception)
        remove.assert_called_once_with(temporary, '/etc/ceph.conf')
        diagnostic, = logs.output
        for detail in ('rollback_unresolved', 'pool/target', temporary, '/etc/ceph.conf'):
            self.assertIn(detail, diagnostic)
        self.assertNotIn('private cleanup detail', diagnostic)

    def test_existing_target_is_never_removed(self):
        with mock.patch.object(ceph, '_rbd_exists', return_value=True):
            with mock.patch.object(ceph, '_rbd_remove') as remove:
                with mock.patch.object(ceph, 'run_checked') as write:
                    with mock.patch.object(ceph.os.path, 'isfile', return_value=True):
                        with self.assertRaises(FileExistsError):
                            ceph.clone(SimpleNamespace(psUuid='ps-uuid', srcPath='ceph://pool/source',
                                                       dstPath='ceph://pool/target', encryptedDek='wrapped'))
                        with self.assertRaises(FileExistsError):
                            ceph.create_empty(SimpleNamespace(
                                psUuid='ps-uuid', installPath='ceph://pool/target',
                                size=8 * 1024 * 1024, encryptedDek='wrapped'))
        write.assert_not_called()
        remove.assert_not_called()

    def test_missing_ceph_config_fails_before_any_qemu_write(self):
        cmd = SimpleNamespace(psUuid='ps-uuid', installPath='ceph://pool/target',
                              size=8 * 1024 * 1024, encryptedDek='wrapped')
        with mock.patch.object(ceph.os.path, 'isfile', return_value=False):
            with mock.patch.object(ceph, 'run_checked') as call:
                with self.assertRaises(FileNotFoundError):
                    ceph.create_empty(cmd)
        call.assert_not_called()

    def test_source_equal_target_is_rejected_before_qemu_write(self):
        with mock.patch.object(ceph, '_config'), mock.patch.object(ceph, 'run_checked') as call:
            with self.assertRaisesRegex(ValueError, 'must differ'):
                ceph.clone(SimpleNamespace(srcPath='ceph://pool/same', dstPath='ceph://pool/same'))
        call.assert_not_called()

    def test_failed_publish_restores_original_rbd_name(self):
        renamed = []

        def rename(source, target, config):
            renamed.append((source, target))
            if source.startswith('pool/target-converting-'):
                raise RuntimeError('publish failed')

        with mock.patch.object(ceph, '_rbd_exists', return_value=False):
            with mock.patch.object(ceph, '_convert', return_value=True):
                with mock.patch.object(ceph, '_rbd_rename', side_effect=rename):
                    with self.assertRaisesRegex(RuntimeError, 'publish failed'):
                        ceph._publish_conversion('pool/source', 'pool/target', 'pool/trash',
                                                 '/etc/ceph.conf', EncryptionMode.LUKS,
                                                 'wrapped', EncryptionMode.PLAIN)
        self.assertEqual(('pool/source', 'pool/trash'), renamed[0])
        self.assertEqual(('pool/trash', 'pool/source'), renamed[-1])

    def test_failed_conversion_restore_preserves_publish_error_and_original_in_trash(self):
        images = {'pool/source': 'original data'}
        publish_error = RuntimeError('wrapped /tmp/one-shot-secret')
        restore_error = OSError('wrapped /tmp/one-shot-secret')
        removed = []

        def rename(source, target, config):
            if source.startswith('pool/target-converting-'):
                images[target] = 'concurrent target'
                raise publish_error
            if source == 'pool/trash':
                raise restore_error
            self.assertNotIn(target, images)
            images[target] = images.pop(source)

        def remove(image, config):
            removed.append(image)
            del images[image]

        with mock.patch.object(ceph, '_rbd_exists', side_effect=lambda image, _: image in images), \
                mock.patch.object(ceph, '_convert',
                                  side_effect=lambda source, target, *args: images.update({target: 'converted'})), \
                mock.patch.object(ceph, '_rbd_rename', side_effect=rename), \
                mock.patch.object(ceph, '_rbd_remove', side_effect=remove), \
                mock.patch.object(ceph, 'logger', logging.getLogger('ceph-restore-test')), \
                mock.patch.object(http_error, 'logger', logging.getLogger('ceph-restore-test')), \
                self.assertLogs('ceph-restore-test', level='ERROR') as logs:
            with self.assertRaises(RuntimeError) as raised:
                ceph._publish_conversion('pool/source', 'pool/target', 'pool/trash',
                                         '/etc/ceph.conf', EncryptionMode.LUKS,
                                         'wrapped', EncryptionMode.PLAIN)
            self.assertIs(publish_error, raised.exception)
        self.assertEqual({'pool/trash': 'original data', 'pool/target': 'concurrent target'}, images)
        self.assertEqual(1, len(removed))
        self.assertTrue(removed[0].startswith('pool/target-converting-'))
        log_text = '\n'.join(logs.output)
        for path in ('pool/source', 'pool/trash', 'pool/target', removed[0]):
            self.assertIn(path, log_text)
        self.assertNotIn('wrapped', log_text)
        self.assertNotIn('/tmp/one-shot-secret', log_text)

    def test_encrypted_download_removes_both_json_files_after_failure(self):
        cmd = SimpleNamespace(psUuid='ps-uuid', primaryStorageInstallPath='ceph://pool/target',
                              backupStorageInstallPath='zstore://name/id', hostname='imagestore',
                              encryptedDek='wrapped', sourceEncrypted=True)
        client = mock.Mock(ZSTORE_CLI_BIN='/usr/bin/zstcli', ZSTORE_DEF_PORT=8000)
        client._parse_image_reference.return_value = ('name', 'id')
        client._build_registry_url.return_value = 'imagestore:8000'
        paths = []

        def fail_pull(command, env):
            paths.extend([command[command.index(flag) + 1] for flag in
                          ('-target-encryption-json-file', '-encryption-json-file')])
            for path in paths:
                with open(path) as stream:
                    self.assertIn('wrapped', stream.read())
            self.assertNotIn('wrapped', ' '.join(command))
            raise subprocess.CalledProcessError(1, command)

        with mock.patch.object(ceph.os.path, 'isfile', return_value=True), \
                mock.patch.object(ceph, '_rbd_exists', return_value=False):
            with mock.patch.object(ceph, 'run_checked', side_effect=fail_pull):
                with self.assertRaises(subprocess.CalledProcessError):
                    ceph.download_encrypted_imagestore(cmd, client)
        self.assertEqual(2, len(paths))
        self.assertTrue(all(not ceph.os.path.exists(path) for path in paths))

    def test_download_publishes_only_verified_image_and_cleans_owned_resources(self):
        unlink = ceph.os.unlink
        for source_encrypted in (False, True):
            for outcome in ('success', 'pull_failed', 'json_cleanup_failed', 'pull_and_cleanup_failed', 'format_failed',
                            'key_failed', 'existing', 'concurrent'):
                with self.subTest(source_encrypted=source_encrypted, outcome=outcome), \
                        mock.patch.multiple(ceph, _config=mock.DEFAULT, _rbd_exists=mock.DEFAULT,
                                            _rbd_remove=mock.DEFAULT, _rbd_rename=mock.DEFAULT,
                                            _info=mock.DEFAULT) as backend:
                    cmd = SimpleNamespace(primaryStorageInstallPath='ceph://pool/target',
                                          backupStorageInstallPath='zstore://name/id', hostname='imagestore',
                                          encryptedDek='wrapped', sourceEncrypted=source_encrypted,
                                          keyProviderUuid='provider', keyVersion=1, cipher='luks',
                                          concurrency=3)
                    original_cmd = vars(cmd).copy()
                    target = 'pool/target'
                    images = {'pool/source': 'source data'}
                    if outcome == 'existing':
                        images[target] = 'other request'
                    paths, verified = [], []
                    client = mock.Mock(ZSTORE_CLI_BIN='/usr/bin/zstcli', ZSTORE_DEF_PORT=8000)
                    client._parse_image_reference.return_value = ('name', 'id')
                    client._build_registry_url.return_value = 'imagestore:8000'
                    backend['_config'].return_value = '/etc/ceph.conf'
                    backend['_rbd_exists'].side_effect = lambda name, _: name in images
                    backend['_rbd_remove'].side_effect = lambda name, _: images.pop(name)
                    backend['_info'].side_effect = lambda name, _: {'format': images[name]}

                    cleanup_failed = outcome in ('json_cleanup_failed', 'pull_and_cleanup_failed')
                    succeeds = outcome in ('success', 'json_cleanup_failed')
                    pull_error = RuntimeError('pull interrupted after write')

                    def remove(path):
                        if cleanup_failed and path in paths:
                            raise PermissionError('wrapped ' + path)
                        unlink(path)

                    def pull(command, env):
                        install_path = command[command.index('-installpath') + 1]
                        self.assertTrue(install_path.startswith('ceph://pool/target-converting-'))
                        self.assertEqual('ceph://pool/target', cmd.primaryStorageInstallPath)
                        self.assertIn('-concurrency=3', command)
                        self.assertEqual('name:id', command[-1])
                        self.assertEqual('imagestore:8000', command[command.index('-url') + 1])
                        self.assertEqual(ceph.imagestore.KEY_AGENT_PROVIDER,
                                         command[command.index('-secret-channel-provider') + 1])
                        self.assertEqual('/etc/ceph.conf', env['CEPH_CONF'])
                        self.assertEqual('--conf /etc/ceph.conf', env['CEPH_ARGS'])
                        flags = ['-target-encryption-json-file']
                        if source_encrypted:
                            flags.append('-encryption-json-file')
                        else:
                            self.assertNotIn('-encryption-json-file', command)
                        for flag in flags:
                            path = command[command.index(flag) + 1]
                            paths.append(path)
                            if cleanup_failed:
                                self.addCleanup(unlink, path)
                            with open(path) as stream:
                                self.assertEqual(dict(encrypted=True, encryptedDek='wrapped',
                                                      keyProviderUuid='provider', keyVersion=1,
                                                      cipher='luks'), json.load(stream))
                        self.assertNotIn('wrapped', ' '.join(command))
                        images[ceph._image_path(install_path)] = 'raw' if outcome == 'format_failed' else 'luks'
                        if outcome in ('pull_failed', 'pull_and_cleanup_failed'):
                            raise pull_error

                    def check_key(command, **kwargs):
                        self.assertEqual('map', command[1])
                        options = dict(item.split('=', 1) for item in command[-1].split(','))
                        staged = options['file.pool'] + '/' + options['file.image']
                        self.assertEqual('luks', images[staged])
                        if outcome == 'key_failed':
                            raise RuntimeError('key verification failed')
                        verified.append(staged)
                        if outcome == 'concurrent':
                            images[target] = 'other request'
                        return b'[]'

                    def publish(staged, destination, _):
                        self.assertEqual([staged], verified)
                        self.assertEqual(target, destination)
                        if destination in images:
                            raise FileExistsError(destination)
                        images[destination] = images.pop(staged)

                    backend['_rbd_rename'].side_effect = publish
                    diagnostics = logging.getLogger('ceph-download-cleanup-test')
                    capture = self.assertLogs(diagnostics, level='ERROR') if cleanup_failed else nullcontext()
                    with capture as logs, \
                            mock.patch.object(http_error, 'logger', diagnostics), \
                            mock.patch.object(ceph.os, 'unlink', side_effect=remove), \
                            mock.patch.object(ceph, 'run_checked', side_effect=pull) as write, \
                            mock.patch.object(ceph.subprocess, 'check_output', side_effect=check_key), \
                            mock.patch.object(ceph.secret, 'luks_secret_channel',
                                              return_value=nullcontext('/tmp/secret')):
                        if succeeds:
                            self.assertTrue(ceph.download_encrypted_imagestore(cmd, client))
                        else:
                            error = FileExistsError if outcome in ('existing', 'concurrent') else RuntimeError
                            with self.assertRaises(error) as failure:
                                ceph.download_encrypted_imagestore(cmd, client)
                            if outcome in ('pull_failed', 'pull_and_cleanup_failed'):
                                self.assertIs(pull_error, failure.exception)
                    expected = {'pool/source': 'source data'}
                    if succeeds:
                        expected[target] = 'luks'
                    elif outcome in ('existing', 'concurrent'):
                        expected[target] = 'other request'
                    self.assertEqual(expected, images)
                    self.assertEqual(original_cmd, vars(cmd))
                    self.assertTrue(all(ceph.os.path.exists(path) == cleanup_failed for path in paths))
                    if cleanup_failed:
                        self.assertEqual(len(paths), sum('stage=unlink_sensitive_file' in row for row in logs.output))
                        self.assertNotIn('wrapped', '\n'.join(logs.output))
                        for path in paths:
                            self.assertNotIn(path, '\n'.join(logs.output))
                    if outcome == 'existing':
                        write.assert_not_called()
                        backend['_rbd_remove'].assert_not_called()
                    else:
                        self.assertEqual(2 if source_encrypted else 1, len(paths))


if __name__ == '__main__':
    unittest.main()

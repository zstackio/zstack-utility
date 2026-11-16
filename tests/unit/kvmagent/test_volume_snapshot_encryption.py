import os
import logging
import pytest
import ast
from pathlib import Path
import tempfile
import subprocess
import shutil
import hashlib
from contextlib import contextmanager, nullcontext
import unittest
from types import SimpleNamespace as NS
from unittest import mock
from xml.etree import ElementTree as ET

from zstacklib.utils import jsonobject

try:
    from kvmagent.volume import snapshots
    from kvmagent.crypto.snapshots import LuksSnapshot
except ImportError:
    snapshots = None
    LuksSnapshot = None


class SnapshotEncryptionTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(snapshots, 'snapshot execution seam is missing')
        self.registry = mock.patch.dict(snapshots._snapshot_extensions, {}, clear=True)
        self.registry.start()
        self.addCleanup(self.registry.stop)
        snapshots.register_extension('luks', LuksSnapshot)
        metadata = mock.patch('kvmagent.crypto.snapshots._image_info', return_value={'format': 'qcow2', 'encrypted': True})
        self.metadata_patcher = metadata
        metadata.start()
        self.addCleanup(metadata.stop)

    def test_plain_full_and_delta_keep_original_helpers(self):
        cmd = NS()
        with mock.patch.object(LuksSnapshot, 'matches', return_value=False):
            operation = snapshots.get_snapshot(cmd, '/source')
        with mock.patch.object(snapshots.linux, 'create_template') as full, \
                mock.patch.object(snapshots.linux, 'qcow2_clone_with_cmd') as delta:
            operation.create_full('/source', '/snapshot')
            operation.create_delta('/snapshot', '/new')
        full.assert_called_once_with('/source', '/snapshot')
        delta.assert_called_once_with('/snapshot', '/new', cmd)

    def test_group_job_never_inherits_another_disks_key(self):
        outer = jsonobject.loads('{"encryptedDek":"wrong-outer","kvmHostAddons":"options","virtualSize":1024}')
        job = jsonobject.loads('{"encryptedDek":"per-disk"}')
        cmd = snapshots.command_for_job(outer, job)
        self.assertEqual('per-disk', cmd.encryptedDek)
        self.assertEqual('options', cmd.kvmHostAddons)
        self.assertIsNone(job.kvmHostAddons)
        self.assertNotIn('encryptedDek', vars(snapshots.command_for_job(outer, jsonobject.JsonObject())))

    def test_missing_offline_key_is_rejected_before_write(self):
        operation = LuksSnapshot(NS(volume=NS(encrypted=True)), '/source')
        with mock.patch('kvmagent.crypto.snapshots.file_operations.create_template') as create:
            with self.assertRaisesRegex(ValueError, 'encryptedDek'):
                operation.create_full('/source', '/target')
        create.assert_not_called()

    def test_full_and_delta_use_each_disks_existing_crypto_operations(self):
        operation = LuksSnapshot(NS(encryptedDek='per-disk'), '/source')
        with mock.patch('kvmagent.crypto.snapshots.file_operations.create_template') as full, \
                mock.patch('kvmagent.crypto.snapshots.file_operations.create_with_backing') as delta, \
                mock.patch('kvmagent.crypto.snapshots.os.link'):
            operation.create_full('/source', '/snapshot')
            operation.create_delta('/snapshot', '/new')
        self.assertEqual('per-disk', full.call_args.args[0].encryptedDek)
        self.assertEqual('per-disk', delta.call_args.args[0].encryptedDek)

    def test_snapshot_xml_uses_new_source_and_does_not_add_backing_store(self):
        operation = LuksSnapshot(NS(), '/old')
        source = ET.Element('source', file='/new')
        operation.add_source_encryption(source, NS(luksSecretUuid='host-secret'))
        self.assertEqual('host-secret', source.find('encryption/secret').get('uuid'))
        self.assertIsNone(source.find('backingStore'))

    def test_live_missing_uuid_rejected_before_layer_creation(self):
        operation = LuksSnapshot(NS(encryptedDek='per-disk'), '/old')
        with mock.patch.object(operation, 'create_delta') as create:
            with self.assertRaisesRegex(ValueError, 'luksSecretUuid'):
                operation.prepare_live('/new', NS(), 'file')
        create.assert_not_called()

    def test_uuid_only_live_does_not_request_dek_or_export_secret(self):
        operation = LuksSnapshot(NS(), '/old')
        with mock.patch.object(operation, 'create_delta') as create, \
                mock.patch('kvmagent.crypto.snapshots.os.path.exists', return_value=False):
            operation.prepare_live('/new', NS(luksSecretUuid='host-secret'), 'file')
        create.assert_not_called()
        self.assertFalse(operation.should_reuse_target('/new'))

    def test_verification_failure_removes_only_new_file_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, 'new')
            operation = LuksSnapshot(NS(encryptedDek='per-disk'), '/source')
            def fail(*args):
                open(args[-1], 'w').close()
                raise RuntimeError('verification failed')
            with mock.patch('kvmagent.crypto.snapshots.file_operations.create_template', side_effect=fail):
                with self.assertRaisesRegex(RuntimeError, 'verification failed'):
                    operation.create_full('/source', target)
            self.assertFalse(os.path.exists(target))

    def test_uuid_only_empty_block_target_requests_format_creation(self):
        operation = LuksSnapshot(NS(), '/dev/vg/old')
        with mock.patch('kvmagent.crypto.snapshots.os.path.exists', return_value=True), \
                mock.patch('kvmagent.crypto.snapshots._image_info', return_value={'format': 'raw'}):
            operation.prepare_live('/dev/vg/new', NS(luksSecretUuid='uuid'), 'block')
            self.assertFalse(operation.should_reuse_target('/dev/vg/new'))

    def test_failed_second_step_cleans_only_offline_files_created_here(self):
        operation = mock.Mock()
        operation.create_delta.side_effect = RuntimeError('clone failed')
        with mock.patch.object(snapshots, 'get_snapshot', return_value=operation):
            with self.assertRaisesRegex(RuntimeError, 'clone failed'):
                snapshots.take_offline_snapshot(NS(), '/old', '/snapshot', '/new', snapshots.SnapshotMode.FULL)
        operation.cleanup_offline.assert_called_once_with()

    def test_publish_race_never_deletes_an_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, 'target')
            operation = LuksSnapshot(NS(encryptedDek='per-disk'), '/source')
            def create(cmd, source, temporary):
                open(temporary, 'w').close()
                with open(target, 'w') as stream:
                    stream.write('another request')
            with mock.patch('kvmagent.crypto.snapshots.file_operations.create_template', side_effect=create):
                with self.assertRaises(FileExistsError):
                    operation.create_full('/source', target)
            with open(target) as stream:
                self.assertEqual('another request', stream.read())

    def test_vm_snapshot_entries_use_the_snapshot_seam(self):
        path = Path(__file__).parents[3] / 'kvmagent/kvmagent/plugins/vm_plugin.py'
        tree = ast.parse(path.read_text())
        for class_name, name in [('Vm', 'take_volume_snapshot'), ('Vm', 'take_live_volumes_delta_snapshots'),
                                 ('VmPlugin', 'take_volume_snapshot'), ('VmPlugin', 'take_volumes_snapshots')]:
            cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
            method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
            calls = [node.func for node in ast.walk(method) if isinstance(node, ast.Call)]
            self.assertTrue(any(isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name)
                                and call.value.id == 'volume_snapshots' for call in calls),
                            '%s.%s must use the per-volume snapshot execution seam' % (class_name, name))
            self.assertFalse(any(isinstance(call, ast.Attribute) and isinstance(call.value, ast.Name)
                                 and call.value.id == 'linux' and call.attr in ('create_template', 'qcow2_clone_with_cmd')
                                 for call in calls), 'snapshot writes cannot bypass per-disk encryption selection')

    def test_wrong_host_secret_rejected_before_precreating_layer(self):
        operation = LuksSnapshot(NS(encryptedDek='per-disk'), '/old')
        domain = "<domain><devices><disk><source file='/old'><encryption format='luks'><secret uuid='current'/></encryption></source><target dev='vda'/></disk></devices></domain>"
        with self.assertRaisesRegex(ValueError, 'current volume'):
            operation.validate_live_source(domain, 'vda', NS(luksSecretUuid='wrong'))

    def test_live_format_reads_use_force_share_and_never_open_active_disk_with_qemu_io(self):
        self.metadata_patcher.stop()
        operation = LuksSnapshot(NS(encryptedDek='per-disk'), '/old')
        with mock.patch('kvmagent.crypto.snapshots.subprocess.check_output', return_value=b'{"format":"qcow2","encrypted":true}') as info, \
                mock.patch('kvmagent.crypto.snapshots.qemu_volume.verify_luks_open') as probe:
            operation.verify_live('/new', lambda path: True)
        self.assertIn('-U', info.call_args.args[0])
        probe.assert_not_called()

    def _single_live_method(self, method_name='take_volume_snapshot'):
        path = Path(__file__).parents[3] / 'kvmagent/kvmagent/plugins/vm_plugin.py'
        tree = ast.parse(path.read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Vm')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == method_name)
        method.decorator_list = []
        class LibvirtError(Exception):
            pass
        libvirt = NS(libvirtError=LibvirtError, VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY=1,
                     VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA=2, VIR_DOMAIN_SNAPSHOT_CREATE_REUSE_EXT=4,
                     VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC=8)
        def element(parent, name, value=None, attrib=None):
            return ET.SubElement(parent, name, attrib or {})
        namespace = dict(volume_snapshots=snapshots, os=os, etree=ET, e=element,
                         block_device_use_block_type=lambda: False, logger=mock.Mock(), libvirt=libvirt,
                         linux=NS(wait_callback_success=lambda callback, path, timeout: bool(callback(path)),
                                  get_exception_stacktrace=lambda: 'libvirt failure'),
                         VmPlugin=NS(get_source_file_by_disk=lambda disk: getattr(disk, 'source_path', '/old'),
                                     active_volume_if_need=lambda path: None, _get_snapshot_size=lambda path: 1),
                         VolumeSnapshotResultStruct=lambda uuid, source, target, size, memory: NS(
                             volumeUuid=uuid, previousInstallPath=source, installPath=target, size=size, memory=memory),
                         time=NS(sleep=lambda seconds: None),
                         Vm=NS(ensure_delta_snapshot_not_exceed=lambda path: None), kvmagent=NS(KvmError=RuntimeError))
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
        return namespace[method_name], LibvirtError

    def test_real_single_live_method_switches_uuid_only_layer_and_recovers_false_error(self):
        method, error = self._single_live_method()
        for libvirt_error in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                target = os.path.join(directory, 'new')
                active = []
                domain = mock.Mock()
                def switch(xml, flags):
                    source = ET.fromstring(xml).find('./disks/disk/source')
                    self.assertEqual('host-secret', source.find('encryption/secret').get('uuid'))
                    self.assertFalse(flags & 4)
                    active.append(source.get('file'))
                    if libvirt_error:
                        raise error('reported after switch')
                domain.snapshotCreateXML.side_effect = switch
                vm = NS(uuid='vm', domain=domain, _get_target_disk=lambda volume: (NS(type_='file'), 'vda'),
                        _get_backfile_chain=lambda path: [], refresh=lambda: None,
                        _check_target_disk_existing_by_path=lambda path, refresh=True: path in active,
                        domain_xmlobject=NS(devices=NS(get_child_node_as_list=lambda name: [])),
                        domain_xml="<domain><devices><disk><source file='/old'><encryption><secret uuid='host-secret'/></encryption></source><target dev='vda'/></disk></devices></domain>")
                volume = NS(deviceId=0, luksSecretUuid='host-secret')
                with mock.patch('kvmagent.crypto.snapshots._image_info', return_value={'format': 'qcow2', 'encrypted': True}), \
                        mock.patch('kvmagent.crypto.snapshots.secret.luks_secret_channel') as material:
                    self.assertEqual(('/old', target), method(vm, NS(volume=volume), volume, target))
                material.assert_not_called()
                domain.snapshotCreateXML.assert_called_once()

    def test_real_group_method_preserves_partial_switch_and_libvirt_owned_targets(self):
        method, error = self._single_live_method('take_live_volumes_delta_snapshots')
        with tempfile.TemporaryDirectory() as directory:
            plain = os.path.join(directory, 'plain')
            encrypted = os.path.join(directory, 'encrypted')
            active = []
            jobs = [NS(live=True, full=False, memory=False, volumeUuid='plain', installPath=plain,
                       virtualSize=None, kvmHostAddons=None, volume=NS(deviceId=0)),
                    NS(live=True, full=False, memory=False, volumeUuid='encrypted', installPath=encrypted,
                       encryptedDek='wrapped', volume=NS(deviceId=1, luksSecretUuid='host-secret'))]
            def switch(xml, flags):
                disks = ET.fromstring(xml).findall('./disks/disk')
                self.assertEqual(2, len(disks))
                self.assertFalse(flags & 4)
                self.assertTrue(flags & 8)
                self.assertIsNone(disks[0].find('source/encryption'))
                self.assertEqual('host-secret', disks[1].find('source/encryption/secret').get('uuid'))
                open(plain, 'w').close()
                open(encrypted, 'w').close()
                active.append(encrypted)
                raise error('only second disk switched')
            vm = NS(uuid='vm', refresh=lambda: None, domain=NS(snapshotCreateXML=switch),
                    _get_target_disk=lambda volume: (NS(type_='file', source_path='/old-%s' % volume.deviceId),
                                                      'vd%s' % volume.deviceId),
                    _check_target_disk_existing_by_path=lambda path, refresh=True: path in active,
                    domain_xmlobject=NS(devices=NS(get_child_node_as_list=lambda name: [])),
                    domain_xml="<domain><devices><disk><source file='/old-0'/><target dev='vd0'/></disk><disk><source file='/old-1'><encryption><secret uuid='host-secret'/></encryption></source><target dev='vd1'/></disk></devices></domain>")
            def image_info(path):
                return {'format': 'qcow2', 'virtual-size': 1024, 'encrypted': path != '/old-0'}
            def plain_clone(source, target, cmd):
                open(target, 'w').close()
            def create_encrypted(command):
                open(command[-2], 'w').close()
            with mock.patch('kvmagent.crypto.snapshots._image_info', side_effect=image_info), \
                    mock.patch('kvmagent.crypto.snapshots.secret.luks_secret_channel', side_effect=AssertionError('online must not request key material')), \
                    mock.patch('kvmagent.crypto.snapshots.subprocess.check_call', side_effect=create_encrypted), \
                    mock.patch.object(snapshots.linux, 'qcow2_clone_with_cmd', side_effect=plain_clone):
                results = method(vm, jobs)
            self.assertEqual(['encrypted'], [result.volumeUuid for result in results])
            self.assertTrue(os.path.exists(plain))
            self.assertTrue(os.path.exists(encrypted))

    def test_snapshot_target_cannot_alias_its_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, 'source')
            alias = os.path.join(directory, 'alias')
            open(source, 'w').close()
            os.symlink(source, alias)
            operation = LuksSnapshot(NS(), source)
            with self.assertRaisesRegex(ValueError, 'different'):
                operation.prepare_live(alias, NS(luksSecretUuid='uuid'), 'file')
            with self.assertRaisesRegex(ValueError, 'different'):
                snapshots.take_offline_snapshot(NS(encryptedDek='key'), source, '/unused', alias, snapshots.SnapshotMode.DELTA)

    def test_live_block_target_requires_raw_reserved_lv(self):
        operation = LuksSnapshot(NS(), '/dev/vg/source')
        with mock.patch('kvmagent.crypto.snapshots.os.path.exists', return_value=True), \
                mock.patch('kvmagent.crypto.snapshots._image_info', return_value={'format': 'qcow2'}):
            with self.assertRaises(FileExistsError):
                operation.prepare_live('/dev/vg/previous-qcow2', NS(luksSecretUuid='uuid'), 'block')

    def test_offline_sharedblock_checks_key_before_extending_and_never_uses_file_transaction(self):
        operation = LuksSnapshot(NS(encryptedDek='wrong'), '/dev/vg/source')
        with mock.patch('kvmagent.crypto.snapshots.lvm.RecursiveOperateLv', return_value=mock.MagicMock()), \
                mock.patch('kvmagent.crypto.snapshots.lvm.OperateLv', return_value=mock.MagicMock()), \
                mock.patch('kvmagent.crypto.snapshots.qemu_volume.verify_luks_open', side_effect=RuntimeError('wrong key')), \
                mock.patch('kvmagent.crypto.snapshots.lvm.extend_lv') as extend, \
                mock.patch('kvmagent.crypto.snapshots.file_operations.create_template') as file_write:
            with self.assertRaisesRegex(RuntimeError, 'wrong key'):
                operation.create_full('/dev/vg/source', '/dev/vg/target')
        extend.assert_not_called()
        file_write.assert_not_called()

    def test_plain_top_with_encrypted_history_is_not_silently_reencrypted(self):
        operation = LuksSnapshot(NS(encryptedDek='wrapped', volume=NS(encrypted=False)), '/plain-top')
        with mock.patch('kvmagent.crypto.snapshots._image_info', return_value={'format': 'qcow2'}), \
                mock.patch('kvmagent.crypto.snapshots.file_operations.create_template') as create:
            with self.assertRaisesRegex(ValueError, 'top layer'):
                operation.create_full('/plain-top', '/new')
        create.assert_not_called()

    def test_volume_flag_conflict_with_encrypted_top_is_rejected(self):
        operation = LuksSnapshot(NS(encryptedDek='wrapped', volume=NS(encrypted=False)), '/encrypted')
        with mock.patch('kvmagent.crypto.snapshots._image_info', return_value={'format': 'qcow2', 'encrypted': True}), \
                mock.patch('kvmagent.crypto.snapshots.file_operations.create_template') as create:
            with self.assertRaisesRegex(ValueError, 'encryption state'):
                operation.create_full('/encrypted', '/new')
        create.assert_not_called()

    def test_plain_network_snapshot_does_not_inspect_local_image_headers(self):
        with mock.patch('kvmagent.crypto.snapshots._image_info') as info:
            self.assertFalse(LuksSnapshot.matches(NS(), 'ceph://pool/image'))
        info.assert_not_called()

    def test_sharedblock_source_header_is_checked_inside_activation_context(self):
        active = []
        @contextmanager
        def activated(*args, **kwargs):
            active.append(True)
            yield
            active.pop()
        def info(path):
            if path == '/dev/vg/source':
                self.assertTrue(active, 'inactive source must be activated before reading its header')
                return {'format': 'qcow2', 'encrypted': True}
            return {'format': 'raw'}
        operation = LuksSnapshot(NS(encryptedDek='per-disk'), '/dev/vg/source')
        with mock.patch('kvmagent.crypto.snapshots._image_info', side_effect=info), \
                mock.patch('kvmagent.crypto.snapshots.lvm.RecursiveOperateLv', side_effect=activated), \
                mock.patch('kvmagent.crypto.snapshots.lvm.OperateLv', return_value=mock.MagicMock()), \
                mock.patch('kvmagent.crypto.snapshots.qemu_volume.verify_luks_open', return_value=True), \
                mock.patch('kvmagent.crypto.snapshots.linux.qcow2_virtualsize', return_value=1024), \
                mock.patch('kvmagent.crypto.snapshots.lvm.extend_lv') as extend, \
                mock.patch('kvmagent.crypto.snapshots.block_operations.create_template') as create:
            operation.create_full('/dev/vg/source', '/dev/vg/target')
        create.assert_called_once_with(operation.cmd, '/dev/vg/source', '/dev/vg/target')
        extend.assert_called_once()

    def test_plain_existing_target_is_not_claimed_for_cleanup(self):
        with tempfile.NamedTemporaryFile() as target:
            operation = LuksSnapshot(NS(encryptedDek='per-disk'), '/source')
            with mock.patch('kvmagent.crypto.snapshots.file_operations.create_template') as create:
                with self.assertRaises(FileExistsError):
                    operation.create_full('/source', target.name)
            create.assert_not_called()
            self.assertTrue(os.path.exists(target.name))


@unittest.skipUnless(shutil.which('qemu-img') and shutil.which('qemu-io'), 'QEMU tools are required')
class SnapshotQemuExecutionTest(unittest.TestCase):
    def setUp(self):
        from kvmagent.crypto import qemu_volume
        self.qemu = qemu_volume
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.key = os.path.join(self.directory.name, 'synthetic-key')
        with open(self.key, 'wb') as stream:
            stream.write(b'synthetic-snapshot-regression-key')
        self.source = os.path.join(self.directory.name, 'source.qcow2')
        self.qemu.create_encrypted_qcow2(self.source, 16 * 1024 * 1024, self.key)
        self._io(self.source, self.key, 'write -P 0x6d 1048576 4096')
        self.original_hash = self._hash_source()
        registry = mock.patch.dict(snapshots._snapshot_extensions, {'luks': LuksSnapshot}, clear=True)
        registry.start()
        self.addCleanup(registry.stop)
        provider = mock.patch('kvmagent.crypto.snapshots.secret.luks_secret_channel',
                              side_effect=lambda wrapped: nullcontext(self.key))
        provider.start()
        self.addCleanup(provider.stop)

    def _hash_source(self):
        with open(self.source, 'rb') as stream:
            return hashlib.sha256(stream.read()).hexdigest()

    def _io(self, path, key, command):
        options = self.qemu._source_image_options(path)
        subprocess.check_call([self.qemu.QEMU_IO, '--object', 'secret,id=luks_sec,file=%s' % key,
                               '--image-opts', '-c', command, options], stdout=subprocess.DEVNULL)

    def test_offline_full_and_delta_preserve_markers_in_ciphertext_layers(self):
        for mode in snapshots.SnapshotMode:
            snapshot = os.path.join(self.directory.name, 'snapshot-%s' % mode.value)
            target = os.path.join(self.directory.name, 'new-%s' % mode.value)
            backing, _ = snapshots.take_offline_snapshot(NS(encryptedDek='synthetic-wrapped'),
                                                        self.source, snapshot, target, mode)
            self.assertTrue(self.qemu.is_luks_encrypted_image(backing))
            self.assertTrue(self.qemu.is_luks_encrypted_image(target))
            self._io(target, self.key, 'read -P 0x6d 1048576 4096')
            self._io(target, self.key, 'write -P 0x7e 2097152 4096')
            self._io(target, self.key, 'read -P 0x7e 2097152 4096')
            self.assertEqual(self.original_hash, self._hash_source())

    def test_wrong_key_fails_without_publishing_or_modifying_source(self):
        wrong = os.path.join(self.directory.name, 'synthetic-wrong-key')
        with open(wrong, 'wb') as stream:
            stream.write(b'another-synthetic-regression-key')
        target = os.path.join(self.directory.name, 'new-wrong')
        snapshot = os.path.join(self.directory.name, 'snapshot-wrong')
        with mock.patch('kvmagent.crypto.snapshots.secret.luks_secret_channel',
                        side_effect=lambda wrapped: nullcontext(wrong)):
            with self.assertRaises(subprocess.CalledProcessError):
                snapshots.take_offline_snapshot(NS(encryptedDek='synthetic-wrapped'),
                                                self.source, snapshot, target, snapshots.SnapshotMode.FULL)
        self.assertFalse(os.path.exists(snapshot))
        self.assertFalse(os.path.exists(target))
        self.assertFalse(any('.snapshot.' in name for name in os.listdir(self.directory.name)))
        self.assertEqual(self.original_hash, self._hash_source())

    def test_full_snapshot_is_compensated_if_new_current_layer_creation_fails(self):
        snapshot = os.path.join(self.directory.name, 'snapshot-failed-clone')
        target = os.path.join(self.directory.name, 'new-failed-clone')
        with mock.patch('kvmagent.crypto.snapshots.file_operations.create_with_backing',
                        side_effect=RuntimeError('new layer creation failed')):
            with self.assertRaisesRegex(RuntimeError, 'new layer creation failed'):
                snapshots.take_offline_snapshot(NS(encryptedDek='synthetic-wrapped'),
                                                self.source, snapshot, target, snapshots.SnapshotMode.FULL)
        self.assertFalse(os.path.exists(snapshot))
        self.assertFalse(os.path.exists(target))
        self.assertEqual(self.original_hash, self._hash_source())


if __name__ == '__main__':
    unittest.main()


@pytest.mark.parametrize('business_failure', [False, True])
def test_offline_cleanup_continues_and_retains_failed_ownership(tmp_path, monkeypatch, caplog, business_failure):
    from kvmagent.crypto import http_error
    first, second = [str(tmp_path / name) for name in ('first', 'second')]
    for path in (first, second):
        Path(path).write_bytes(b'owned-snapshot')
    operation = LuksSnapshot(NS(), '/source')
    operation.created_paths.update((first, second, str(tmp_path / 'missing')))
    failed_path = next(path for path in operation.created_paths if os.path.exists(path))
    cleanup_error = OSError('private-cleanup-error')
    business_error = RuntimeError('private-business-error')
    attempted = []
    unlink = os.unlink

    def fail_first(path):
        attempted.append(path)
        if path == failed_path:
            raise cleanup_error
        unlink(path)

    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    monkeypatch.setattr(os, 'unlink', fail_first)
    if business_failure:
        monkeypatch.setattr(snapshots, 'get_snapshot', lambda *_: operation)
        monkeypatch.setattr(operation, 'create_delta', mock.Mock(side_effect=business_error))
        with pytest.raises(RuntimeError) as caught:
            snapshots.take_offline_snapshot(NS(), '/source', '/unused', '/target', snapshots.SnapshotMode.DELTA)
        assert caught.value is business_error
    else:
        with pytest.raises(OSError) as caught:
            operation.cleanup_offline()
        assert caught.value is cleanup_error
    assert set(attempted) == {first, second, str(tmp_path / 'missing')}
    assert operation.created_paths == {failed_path}
    assert Path(failed_path).read_bytes() == b'owned-snapshot'
    assert not Path(second if failed_path == first else first).exists()
    assert failed_path in caplog.text and 'stage=cleanup_offline' in caplog.text
    assert caplog.text.count('unresolved_paths=') == 1
    assert 'private-cleanup-error' not in caplog.text and 'private-business-error' not in caplog.text


@pytest.mark.parametrize('full', [False, True])
@pytest.mark.parametrize('create_fails', [False, True])
def test_snapshot_staging_cleanup_preserves_commit_and_creation_error(
        tmp_path, monkeypatch, full, create_fails):
    from kvmagent.crypto import snapshots as encrypted_snapshots
    target = str(tmp_path / 'snapshot')
    operation = LuksSnapshot(NS(encryptedDek='synthetic'), '/source')
    temporary = []
    business_error = RuntimeError('create failed')
    unlink = os.unlink

    def create(cmd, source, path):
        temporary.append(path)
        Path(path).write_bytes(b'snapshot')
        if create_fails:
            raise business_error

    def fail_temporary_cleanup(path):
        if path in temporary:
            raise OSError('cleanup failed')
        unlink(path)

    monkeypatch.setattr(operation, '_validate_source_state', lambda _: None)
    monkeypatch.setattr(encrypted_snapshots.file_operations, 'create_template', create)
    monkeypatch.setattr(encrypted_snapshots.file_operations, 'create_with_backing', create)
    monkeypatch.setattr(os, 'unlink', fail_temporary_cleanup)
    if create_fails:
        with pytest.raises(RuntimeError) as caught:
            operation._create('/source', target, full)
        assert caught.value is business_error
        assert not Path(target).exists()
        assert not operation.created_paths
    else:
        operation._create('/source', target, full)
        assert Path(target).read_bytes() == b'snapshot'
        assert operation.created_paths == {target}

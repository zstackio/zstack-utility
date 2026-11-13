import json
import logging
import subprocess
import sys
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from kvmagent.crypto import http_error, qemu_volume, secret, vm_xml
from kvmagent.crypto.ceph import http as ceph_http
from kvmagent.crypto.ceph import operations as ceph
from kvmagent.crypto.file_volume import http as file_http
from kvmagent.crypto.shared_block import http as block_http
from kvmagent.crypto.shared_block import operations as block
from kvmagent.crypto.zbs import http as zbs_http
from kvmagent.crypto.zbs import operations as zbs


@pytest.mark.parametrize('publish_result', ['status', 'exception', 'success', 'cleanup_failure'])
def test_sharedblock_in_place_cleans_temp_only_when_publish_fails(monkeypatch, caplog, publish_result):
    source = '/dev/vg/source'
    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    publish_error = RuntimeError('rename failed')
    volumes = {source: 'original'}
    cmd = SimpleNamespace(installPath='sharedblock://vg/source', vgUuid='vg',
                          hostUuid='host', encryptedDek='synthetic')

    def rename(temporary, target, *, overwrite):
        assert overwrite and target == source and volumes[temporary] == 'converted'
        if publish_result == 'status':
            return 5, '', 'rename failed'
        if publish_result in ('exception', 'cleanup_failure'):
            raise publish_error
        volumes[target] = volumes.pop(temporary)

    def delete_lv(path, raise_exception=True):
        if publish_result == 'cleanup_failure':
            assert raise_exception
            raise OSError('private cleanup detail')
        volumes.pop(path)

    delete = Mock(side_effect=delete_lv)
    monkeypatch.setattr(block, 'lvm', SimpleNamespace(
        lv_exists=volumes.__contains__, OperateLv=lambda *args, **kw: nullcontext(),
        get_lv_size=lambda _: 4096,
        create_lv_from_cmd=lambda path, *args: volumes.update({path: 'converted'}),
        lv_rename=rename, delete_lv=delete))
    monkeypatch.setattr(block.subprocess, 'check_output', lambda _: b'{"format":"qcow2"}')
    monkeypatch.setattr(qemu_volume, 'is_luks_encrypted_image', lambda path: path != source)
    monkeypatch.setattr(qemu_volume, 'convert_qcow2_encryption_to_block', Mock())
    monkeypatch.setattr(qemu_volume, 'verify_luks_open', Mock())

    if publish_result == 'success':
        assert block.encrypt_in_place(cmd) is True
        assert volumes == {source: 'converted'}
        delete.assert_not_called()
    else:
        with pytest.raises(RuntimeError, match='rename failed') as caught:
            block.encrypt_in_place(cmd)
        temporary = delete.call_args.args[0]
        delete.assert_called_once_with(temporary)
        assert temporary.startswith(source + '-encrypting-')
        if publish_result == 'cleanup_failure':
            assert caught.value is publish_error
            assert volumes == {source: 'original', temporary: 'converted'}
            assert 'rollback_unresolved' in caplog.text and temporary in caplog.text
            assert 'private cleanup detail' not in caplog.text
        else:
            assert volumes == {source: 'original'}


@pytest.mark.parametrize('handler', [ceph_http, file_http, block_http, zbs_http])
def test_crypto_http_reports_safe_diagnostics_and_preserves_response(handler, caplog, monkeypatch):
    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    channel = '/tmp/synthetic-secret-channel'
    envelope = 'synthetic-request-envelope'
    stderr = 'synthetic-private-stderr'

    def backend_failure(_):
        http_error.run_checked([sys.executable, '-c',
                                'import sys; print(sys.argv[1], file=sys.stderr); sys.exit(17)',
                                'No space left on device: ' + stderr + ' ' + channel])

    backend_failure.__name__ = 'encrypt_in_place'
    req = {handler.http.REQUEST_BODY: json.dumps({'encryptedDek': envelope})}
    with patch.object(handler.operations, 'encrypt_in_place', backend_failure):
        result = json.loads(handler.encrypt_in_place(req))

    assert result == {'success': False, 'error': 'CalledProcessError'}
    diagnostic = caplog.text
    assert all(value in diagnostic for value in
               ('encrypt_in_place', 'stage=execute', 'backend_failure', 'CalledProcessError',
                'returncode=17', 'reason=no_space'))
    assert all(value not in diagnostic + str(result) for value in (channel, envelope, stderr))


@pytest.mark.parametrize('argv, stderr, expected', [
    (['/usr/bin/rbd', '--conf', 'private-config', '--id', 'private-client', 'rm', 'private-image'],
     b'image is still being used private-stderr', ('tool=rbd', 'action=rm', 'reason=resource_busy')),
    (['/usr/bin/rbd', '--conf', 'private-config', 'info', 'private-image'],
     'error reading configuration file private-stderr', ('tool=rbd', 'action=info', 'reason=config_error')),
    (['/usr/bin/qemu-img', 'convert', 'private-image'],
     "unrecognized option '--private-stderr'", ('tool=qemu-img', 'action=convert', 'reason=unsupported_option')),
    (['/usr/bin/qemu-img', 'resize', 'private-image'],
     'unmatched failure private-stderr', ('tool=qemu-img', 'action=resize', 'reason=unrecognized_stderr')),
    (['/tmp/private-binary', 'private-action'], None,
     ('tool=unknown', 'action=unknown', 'reason=no_stderr')),
])
def test_crypto_logs_tool_and_action_without_exposing_command_arguments(argv, stderr, expected, caplog, monkeypatch):
    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    http_error.log_failure('crypto_test', 'execute', subprocess.CalledProcessError(1, argv, stderr=stderr))
    assert all(field in caplog.text for field in expected)
    assert 'private-' not in caplog.text


@pytest.mark.parametrize('rows, expected', [
    ([{'name': 'volume', 'used_size': 4096}], 4096),
    ([{'name': 'volume', 'snapshot': 'snap', 'used_size': 4096},
      {'name': 'volume', 'used_size': 8192}], 12288),
    ([{'name': 'volume', 'used_size': 0}], 0),
    ([], None),
])
def test_ceph_actual_size_reads_and_sums_rbd_du_usage(rows, expected):
    with patch.object(ceph, '_config', return_value='/tmp/ceph.conf'), \
         patch.object(ceph, '_rbd_command', return_value=['rbd', 'du']), \
         patch.object(ceph.subprocess, 'check_output', return_value=json.dumps({'images': rows}).encode()):
        assert ceph.actual_size('ceph://pool/volume', SimpleNamespace()) == expected


@pytest.mark.parametrize('failure', [subprocess.CalledProcessError(5, ['rbd', 'synthetic-private-argument']),
                                     ValueError('synthetic-private-json')])
def test_ceph_actual_size_failure_reports_diagnostics_without_changing_unknown_size(failure, caplog, monkeypatch):
    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    with patch.object(ceph, '_config', return_value='/tmp/ceph.conf'), \
         patch.object(ceph, '_rbd_command', return_value=['rbd', 'du']), \
         patch.object(ceph.subprocess, 'check_output', side_effect=failure):
        assert ceph.actual_size('ceph://pool/volume', SimpleNamespace()) is None
    assert 'ceph.actual_size' in caplog.text
    assert 'stage=rbd_du' in caplog.text
    assert type(failure).__name__ in caplog.text
    assert 'synthetic-private' not in caplog.text


@pytest.mark.parametrize('bad_path', ['cbd:pool,invalid/namespace/volume',
                                      'cbd:pool/namespace,invalid/volume',
                                      'cbd:pool/namespace/volume,invalid'])
def test_cbd_clone_rejects_option_separator_before_probing_target(bad_path):
    cmd = SimpleNamespace(srcPath='cbd:pool/namespace/source@17', dstPath=bad_path,
                          encryptedDek='synthetic')
    with patch.object(zbs.subprocess, 'check_output', return_value=b'{"format":"raw","virtual-size":4096}') as probe, \
         patch.object(zbs, '_initialize') as initialize, patch.object(zbs, '_write_plain_to_luks'), \
         patch.object(zbs, '_verify', return_value=4096):
        with pytest.raises(ValueError, match='CBD volume path'):
            zbs.clone(cmd)
    probe.assert_not_called()
    initialize.assert_not_called()


@pytest.mark.parametrize('scenario', ['plain', 'encrypted', 'mixed'])
def test_backing_probes_reuse_metadata_and_preserve_encrypted_layers(scenario):
    layers = {'/top': {'format': 'qcow2'}}
    expected_encryption = [False]
    if scenario == 'encrypted':
        layers['/top']['encrypted'] = True
        expected_encryption = [True]
    elif scenario == 'mixed':
        layers['/top']['full-backing-filename'] = '/encrypted'
        layers['/encrypted'] = {'format': 'qcow2', 'full-backing-filename': '/base',
                                'format-specific': {'data': {'encrypt': {'format': 'luks'}}}}
        layers['/base'] = {'format': 'qcow2'}
        expected_encryption = [False, True, False]

    def metadata(command, **kwargs):
        if '--backing-chain' in command:
            return json.dumps(list(layers.values())).encode()
        return json.dumps(layers[command[-1]]).encode()

    with patch.object(qemu_volume.subprocess, 'check_output', side_effect=metadata) as probe:
        assert [encrypted for _, _, encrypted in vm_xml._file_chain('/top')] == expected_encryption
        assert probe.call_count == 1 and '--backing-chain' in probe.call_args.args[0]
        probe.reset_mock()
        options = qemu_volume._source_image_options('/top')
        assert probe.call_count == 1 and '--backing-chain' in probe.call_args.args[0]
        if scenario == 'mixed':
            assert 'backing.encrypt.key-secret=luks_sec' in options.split(',')
            assert 'encrypt.key-secret=luks_sec' not in options.split(',')
        else:
            assert bool(options) == (scenario == 'encrypted')
        probe.reset_mock()
        backing_format, backing_arg = qemu_volume._backing_argument('/top')
        assert backing_format == 'qcow2'
        assert probe.call_count == 1 and '--backing-chain' in probe.call_args.args[0]
        if scenario == 'plain':
            assert backing_arg == '/top'
        else:
            assert backing_arg.startswith('json:')
            image = json.loads(backing_arg[5:])
            for path, encrypted in zip(layers, expected_encryption):
                assert image['file']['filename'] == path
                assert ('encrypt' in image) == encrypted
                image = image.get('backing')
            assert image is None


@pytest.mark.parametrize('stderr', [
    b'Permission denied', b'Input/output error', b'',
    b"unrecognized option '--backing-chain'",
    b"Parameter 'encrypt.key-secret' is required for cipher",
])
def test_chain_probe_returns_the_batch_failure_without_repeated_queries(stderr):
    error = subprocess.CalledProcessError(1, [qemu_volume.QEMU_IMG, 'info'], stderr=stderr)
    with patch.object(qemu_volume.subprocess, 'check_output', side_effect=error) as probe:
        with pytest.raises(subprocess.CalledProcessError) as exc:
            list(qemu_volume.iter_image_chain('/top'))
    assert exc.value is error
    probe.assert_called_once()


def test_chain_probe_does_not_silently_accept_incomplete_batch_results():
    batch = b'[{"format":"qcow2","full-backing-filename":"/base"}]'
    with patch.object(qemu_volume.subprocess, 'check_output', return_value=batch) as probe:
        with pytest.raises(RuntimeError, match='incomplete'):
            list(qemu_volume.iter_image_chain('/top'))
    probe.assert_called_once()


@pytest.mark.skipif(not all(Path(tool).exists() for tool in (qemu_volume.QEMU_IMG, qemu_volume.QEMU_IO)),
                    reason='QEMU tools are required')
def test_block_conversion_opens_encrypted_target_backing(tmp_path):
    source, backing, target, channel = (str(tmp_path / name) for name in ('source', 'backing', 'target', 'key'))
    Path(channel).write_bytes(b'local-qemu-fixture-key')
    subprocess.check_call([qemu_volume.QEMU_IMG, 'create', '-f', 'qcow2', source, '8M'])
    subprocess.check_call([qemu_volume.QEMU_IO, '-f', 'qcow2', '-c', 'write -P 85 0 512', source])
    qemu_volume.create_encrypted_qcow2(backing, 8 * 1024 * 1024, channel)
    Path(target).touch()
    with patch.object(qemu_volume.stat, 'S_ISBLK', return_value=True):
        qemu_volume.convert_qcow2_encryption_to_block(source, target, qemu_volume.EncryptionMode.LUKS, channel, target_backing=backing)

    metadata = dict(qemu_volume.iter_image_chain(target))
    assert list(metadata) == [target, backing]
    subprocess.check_call([qemu_volume.QEMU_IO, '-r', '--object',
                           'secret,id=luks_sec,format=raw,file=%s' % channel,
                           '--image-opts', '-c', 'read -P 85 0 512', qemu_volume._source_image_options(target)])


@pytest.mark.skipif(not all(Path(tool).exists() for tool in
                           (qemu_volume.QEMU_IMG, qemu_volume.QEMU_IO, '/usr/sbin/cryptsetup')),
                    reason='QEMU and cryptsetup are required')
def test_zbs_create_replay_preserves_luks_header_and_data(tmp_path, monkeypatch):
    target = tmp_path / 'preallocated-target'
    good_key = tmp_path / 'good-key'
    wrong_key = tmp_path / 'wrong-key'
    good_key.write_bytes(b'local-replay-test-key')
    wrong_key.write_bytes(b'different-local-test-key')
    cmd = SimpleNamespace(installPath='cbd:physical/logical/target', size=8 * 1024 * 1024,
                          encryptedDek=str(good_key))
    with target.open('wb') as image:
        image.truncate(cmd.size + zbs.LUKS_PAYLOAD_OFFSET)
    monkeypatch.setattr(zbs, '_path', lambda _: str(target))
    luks_options = zbs._luks_options
    monkeypatch.setattr(zbs, '_luks_options', lambda path: luks_options(path).replace('file.driver=cbd', 'file.driver=file'))
    monkeypatch.setattr(zbs.secret, 'luks_secret_channel', nullcontext)
    with patch('zstacklib.utils.lock.NamedLock', return_value=threading.RLock(), create=True):
        zbs.create_empty(cmd)
        io = [qemu_volume.QEMU_IO, '--object', 'secret,id=luks_sec,format=raw,file=%s' % good_key,
              '--image-opts', 'driver=luks,key-secret=luks_sec,file.filename=%s' % target]
        subprocess.check_call(io + ['-c', 'write -P 85 0 512'])
        zbs.create_empty(cmd)
        subprocess.check_call(io + ['-c', 'read -P 85 0 512'])

        wrong_dek = SimpleNamespace(**dict(vars(cmd), encryptedDek=str(wrong_key)))
        with pytest.raises(subprocess.CalledProcessError):
            zbs.create_empty(wrong_dek)
        larger_size = SimpleNamespace(**dict(vars(cmd), size=cmd.size * 2))
        with pytest.raises(RuntimeError, match='capacity'):
            zbs.create_empty(larger_size)
        subprocess.check_call(io + ['-c', 'read -P 85 0 512'])


@pytest.mark.parametrize('business_fails', [True, False])
def test_sensitive_cleanup_preserves_business_result(tmp_path, monkeypatch, caplog, business_fails):
    private_path = str(tmp_path / 'private-test-channel')
    envelope = 'synthetic-private-envelope'
    error = RuntimeError("operation failed")
    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    monkeypatch.setattr(secret, 'prepare_luks_secret_material_channel', lambda _: private_path)
    manager = secret.luks_secret_channel(envelope)

    def execute():
        with manager:
            if business_fails:
                raise error

    with patch.object(secret.os, 'unlink', side_effect=PermissionError(private_path)) as unlink:
        if business_fails:
            with pytest.raises(RuntimeError) as caught:
                execute()
            assert caught.value is error
        else:
            execute()
        unlink.assert_called_once()
    assert 'stage=unlink_sensitive_file' in caplog.text
    assert private_path not in caplog.text and envelope not in caplog.text
    assert str(unlink.call_args.args[0]) not in caplog.text

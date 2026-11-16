import importlib.util
import json
import logging
import subprocess
import threading
import time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from kvmagent.crypto import http_error, imagestore, qemu_volume, secret, vm_xml
from kvmagent.crypto.ceph import http as ceph_http
from kvmagent.crypto.ceph import operations as ceph
from kvmagent.crypto.file_volume import http as file_http
from kvmagent.crypto.imagestore_extension import ImageStoreEncryptionExtension
from kvmagent.crypto.shared_block import http as block_http
from kvmagent.crypto.shared_block import operations as block
from kvmagent.crypto.zbs import http as zbs_http
from kvmagent.crypto.zbs import operations as zbs


@pytest.mark.parametrize('encrypted_dek', [None, 'synthetic-envelope'])
def test_sharedblock_empty_volume_formats_new_lv(configured_volume_extensions, monkeypatch, encrypted_dek):
    from kvmagent.volume import plain_shared_block_driver

    plugin_path = Path(__file__).parents[3] / 'kvmagent/kvmagent/plugins/shared_block_plugin.py'
    spec = importlib.util.spec_from_file_location('shared_block_create_under_test', plugin_path)
    sharedblock = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sharedblock)
    monkeypatch.setattr(sharedblock, 'time', time, raising=False)
    plugin = sharedblock.SharedBlockPlugin.__new__(sharedblock.SharedBlockPlugin)
    plugin.vgs_path_and_wwid = {}
    path = '/dev/vg/volume'
    size = 1024 * 1024
    create_lv, extend_lv = Mock(), Mock()
    monkeypatch.setattr(sharedblock, 'lvm', SimpleNamespace(
        lv_exists=lambda _: False, create_lv_from_cmd=create_lv, extend_lv=extend_lv,
        OperateLv=lambda *args, **kwargs: nullcontext(), get_vg_size=lambda _: (100, 50),
        get_lun_capacities_from_vg=lambda *args: [], get_lv_size=lambda _: size))
    create_plain, create_luks = Mock(), Mock()
    monkeypatch.setattr(sharedblock, 'linux', SimpleNamespace(qcow2_virtualsize=lambda _: size), raising=False)
    monkeypatch.setattr(plain_shared_block_driver, 'linux', SimpleNamespace(qcow2_create_with_option=create_plain))
    monkeypatch.setattr(block, 'create_empty', create_luks)
    monkeypatch.setattr(plugin, 'calc_qcow2_option', lambda *args: '')
    cmd = dict(installPath='sharedblock://vg/volume', volumeUuid='volume', vgUuid='vg',
               hostUuid='host', size=size, volumeFormat='qcow2', encryptedDek=encrypted_dek)
    response = json.loads(plugin.create_empty_volume({sharedblock.http.REQUEST_BODY: json.dumps(cmd)}))

    assert response['success'], response
    assert create_lv.call_args.args[:2] == (path, size)
    if encrypted_dek:
        extend_lv.assert_called_once_with(path, size + block.LUKS_HEADER_OVERHEAD, skip_if_sufficient=True)
        assert create_luks.call_args.args[1:3] == (path, size)
        create_plain.assert_not_called()
    else:
        extend_lv.assert_not_called()
        create_plain.assert_called_once_with(path, size, '', discard_on_metadata=False)
        create_luks.assert_not_called()


@pytest.mark.parametrize('encrypted_dek, overhead', [(None, 0), ('synthetic-envelope', block.LUKS_HEADER_OVERHEAD)])
@pytest.mark.parametrize('scenario', ['grow', 'force-grow', 'force-shrink', 'resize-failed', 'retain-lv', 'live-shrink'])
def test_sharedblock_restore_resize_uses_selected_driver(configured_volume_extensions, monkeypatch, encrypted_dek,
                                                        overhead, scenario):
    from kvmagent.volume import plain_shared_block_driver

    plugin_path = Path(__file__).parents[3] / 'kvmagent/kvmagent/plugins/shared_block_plugin.py'
    spec = importlib.util.spec_from_file_location('shared_block_resize_under_test', plugin_path)
    sharedblock = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sharedblock)
    plugin = sharedblock.SharedBlockPlugin.__new__(sharedblock.SharedBlockPlugin)
    path = '/dev/vg/volume'
    size = 1024 * 1024
    force = scenario != 'grow'
    live = scenario == 'live-shrink'
    current_capacity = 64 * size if scenario in ('force-shrink', 'resize-failed', 'retain-lv', 'live-shrink') else 0
    image_end = 32 * size if scenario == 'retain-lv' else size
    events = Mock()
    resize_plain = events.resize_plain
    resize_luks = events.resize_luks
    if scenario == 'resize-failed':
        resize_plain.side_effect = resize_luks.side_effect = RuntimeError('resize failed')
    verify = Mock()
    events.get_img_fmt.return_value = 'qcow2'
    linux = SimpleNamespace(get_img_fmt=events.get_img_fmt, qcow2_virtualsize=lambda _: size,
                            qemu_img_resize=resize_plain)
    monkeypatch.setattr(sharedblock, 'linux', linux, raising=False)
    monkeypatch.setattr(plain_shared_block_driver, 'linux', linux)
    monkeypatch.setattr(sharedblock, 'lvm', SimpleNamespace(
        RecursiveOperateLv=lambda *args, **kwargs: nullcontext(), extend_lv_from_cmd=events.extend_lv,
        resize_lv=events.resize_lv, calcLvReservedSize=lambda allocation: allocation + 12 * size))
    lv = Mock()
    lv.seek.return_value = current_capacity
    events.open_lv.side_effect = lambda *_: nullcontext(lv)
    monkeypatch.setattr(sharedblock, 'open', events.open_lv, raising=False)
    monkeypatch.setattr(secret, 'luks_secret_channel', lambda _: nullcontext('synthetic-channel'))
    monkeypatch.setattr(qemu_volume, 'resize_with_secret', resize_luks)
    monkeypatch.setattr(qemu_volume, 'verify_luks_open', verify)
    events.encrypted_end.return_value = image_end
    monkeypatch.setattr(qemu_volume, 'image_end_offset_with_secret', events.encrypted_end)

    cmd = dict(installPath='sharedblock://vg/volume', size=size, encryptedDek=encrypted_dek)
    if force:
        cmd.update(force=force, live=live)
    response = json.loads(plugin.resize_volume({sharedblock.http.REQUEST_BODY: json.dumps(cmd)}))

    if not encrypted_dek:
        expected = ['resize_lv' if force else 'extend_lv', 'get_img_fmt']
        if not live:
            expected.append('resize_plain')
    elif not force:
        expected = ['extend_lv', 'get_img_fmt', 'resize_luks']
    else:
        expected = ['get_img_fmt', 'open_lv'] + {
            'force-grow': ['resize_lv', 'resize_luks'],
            'force-shrink': ['resize_luks', 'encrypted_end', 'resize_lv'],
            'resize-failed': ['resize_luks'],
            'retain-lv': ['resize_luks', 'encrypted_end'],
            'live-shrink': [],
        }[scenario]
    assert [operation for operation, _, _ in events.mock_calls] == expected
    if scenario == 'resize-failed' or (live and encrypted_dek):
        assert not response['success'], response
        return
    assert response['success'], response
    assert response['size'] == size
    if scenario == 'grow':
        assert events.extend_lv.call_args.args[:2] == (path, size + overhead)
    if 'resize_lv' in expected:
        events.resize_lv.assert_called_once_with(path, size + overhead, True)
    if encrypted_dek:
        mode = qemu_volume.ResizeMode.ALLOW_SHRINK if force else qemu_volume.ResizeMode.GROW_ONLY
        resize_luks.assert_called_once_with(path, size, 'synthetic-channel', mode=mode)
        verify.assert_called_once()
        resize_plain.assert_not_called()
    elif not live:
        resize_plain.assert_called_once_with(path, size, 'qcow2', True if force else None)
        resize_luks.assert_not_called()


@pytest.mark.parametrize('mode', list(qemu_volume.ResizeMode))
def test_encrypted_qcow2_resize_passes_shrink_flag_only_when_allowed(monkeypatch, mode):
    resize = Mock()
    monkeypatch.setattr(qemu_volume, 'run_checked', resize)
    monkeypatch.setattr(qemu_volume, '_source_image_options', lambda _: 'driver=qcow2')

    qemu_volume.resize_with_secret('/dev/vg/volume', 1048576, 'synthetic-channel', mode=mode)

    command = resize.call_args.args[0]
    assert ('--shrink' in command) == (mode is qemu_volume.ResizeMode.ALLOW_SHRINK)


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
    monkeypatch.setattr(block, 'check_output', lambda _: b'{"format":"qcow2"}')
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
        raise subprocess.CalledProcessError(
            17, ['/usr/bin/qemu-io', '--object', 'secret,id=luks_sec,file=' + channel],
            stderr='No space left on device: ' + stderr + ' ' + channel)

    backend_failure.__name__ = 'encrypt_in_place'
    req = {handler.http.REQUEST_BODY: json.dumps({'encryptedDek': envelope})}
    with patch.object(handler.operations, 'encrypt_in_place', backend_failure):
        result = json.loads(handler.encrypt_in_place(req))

    assert result == {'success': False, 'error': 'execute: qemu-io failed (exit code 17)'}
    diagnostic = caplog.text
    assert all(value in diagnostic for value in
               ('encrypt_in_place', 'stage=execute', 'backend_failure', 'CalledProcessError',
                'returncode=17', 'tool=qemu-io'))
    assert all(value not in diagnostic + str(result) for value in (channel, envelope, stderr))


@pytest.mark.parametrize('error', [ValueError('invalid request'), FileNotFoundError('missing volume')])
def test_crypto_http_preserves_safe_validation_errors(error):
    assert http_error.response_error('execute', error, (ValueError, FileNotFoundError)) == str(error)


@pytest.mark.parametrize('argv, stderr, expected', [
    (['/usr/bin/rbd', '--conf', 'private-config', '--id', 'private-client', 'rm', 'private-image'],
     b'image is still being used private-stderr', ('tool=rbd', 'action=rm')),
    (['/usr/bin/rbd', '--conf', 'private-config', 'info', 'private-image'],
     'error reading configuration file private-stderr', ('tool=rbd', 'action=info')),
    (['/usr/bin/qemu-img', 'convert', 'private-image'],
     "unrecognized option '--private-stderr'", ('tool=qemu-img', 'action=convert')),
    (['/usr/bin/qemu-img', 'resize', 'private-image'],
     'unmatched failure private-stderr', ('tool=qemu-img', 'action=resize')),
    (['/tmp/private-binary', 'private-action'], None,
     ('tool=unknown', 'action=unknown')),
])
def test_crypto_logs_tool_and_action_without_exposing_command_arguments(argv, stderr, expected, caplog, monkeypatch):
    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    http_error.log_failure('crypto_test', 'execute', subprocess.CalledProcessError(1, argv, stderr=stderr))
    assert all(field in caplog.text for field in expected)
    assert 'private-' not in caplog.text


@pytest.mark.parametrize('failed_tool, action, status, expected', [
    ('qemu-img', 'create', 1, 'qemu-img create failed (exit code 1)'),
    ('qemu-io', '-r', -6, 'qemu-io failed (signal 6)'),
])
def test_encrypted_create_failure_is_safe_before_replyerror(tmp_path, failed_tool, action, status, expected):
    from kvmagent.crypto.file_volume.driver import LuksFileVolumeDriver

    channel = '/tmp/synthetic-secret-channel'
    target = tmp_path / 'target'
    cmd = SimpleNamespace(encryptedDek='synthetic-envelope', installUrl=str(target),
                          volumeFormat='qcow2', size=4096)

    def run(command, **kwargs):
        if command[0].endswith(failed_tool) and command[1] == action:
            raise subprocess.CalledProcessError(status, command, stderr='synthetic-private-stderr')
        Path(command[-2]).touch()

    with patch.object(secret, 'luks_secret_channel', return_value=nullcontext(channel)), \
            patch.object(qemu_volume.subprocess, 'run', side_effect=run), \
            patch.object(qemu_volume, 'is_luks_encrypted_image', return_value=True), \
            patch.object(qemu_volume, '_source_image_options', return_value='synthetic-options'):
        with pytest.raises(subprocess.CalledProcessError) as raised:
            LuksFileVolumeDriver(cmd).create_empty()

    error = raised.value
    assert str(error) == expected
    assert channel not in repr(error)
    assert error.stderr is None and error.__suppress_context__
    assert list(tmp_path.iterdir()) == []


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
    if isinstance(failure, subprocess.CalledProcessError):
        assert 'returncode=5 tool=rbd' in caplog.text
    else:
        assert 'exception=ValueError' in caplog.text
    assert 'synthetic-private' not in caplog.text


@pytest.mark.parametrize('bad_path', ['cbd:pool,invalid/namespace/volume',
                                      'cbd:pool/namespace,invalid/volume',
                                      'cbd:pool/namespace/volume,invalid'])
def test_cbd_clone_rejects_option_separator_before_probing_target(bad_path):
    cmd = SimpleNamespace(srcPath='cbd:pool/namespace/source@17', dstPath=bad_path,
                          encryptedDek='synthetic')
    with patch.object(zbs, 'check_output', return_value=b'{"format":"raw","virtual-size":4096}') as probe, \
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
    assert str(exc.value) == 'qemu-img info failed (exit code 1)'
    assert exc.value.stderr is None
    probe.assert_called_once()


def test_chain_probe_does_not_silently_accept_incomplete_batch_results():
    batch = b'[{"format":"qcow2","full-backing-filename":"/base"}]'
    with patch.object(qemu_volume.subprocess, 'check_output', return_value=batch) as probe:
        with pytest.raises(RuntimeError, match='incomplete'):
            list(qemu_volume.iter_image_chain('/top'))
    probe.assert_called_once()


@pytest.mark.skipif(not all(Path(tool).exists() for tool in (qemu_volume.QEMU_IMG, qemu_volume.QEMU_IO)),
                    reason='QEMU tools are required')
def test_safe_rebase_keeps_data_with_encrypted_backing(tmp_path):
    target, backing, channel = (str(tmp_path / name) for name in ('target', 'backing', 'key'))
    Path(channel).write_bytes(b'local-qemu-fixture-key')
    subprocess.check_call([qemu_volume.QEMU_IMG, 'create', '-f', 'qcow2', target, '8M'])
    subprocess.check_call([qemu_volume.QEMU_IO, '-f', 'qcow2', '-c', 'write -P 85 0 512', target])
    qemu_volume.create_encrypted_qcow2(backing, 8 * 1024 * 1024, channel)

    qemu_volume.safe_rebase_with_secret(backing, target, lambda: nullcontext(channel))

    assert [path for path, _ in qemu_volume.iter_image_chain(target)] == [target, backing]
    subprocess.check_call([qemu_volume.QEMU_IO, '-r', '--object',
                           'secret,id=luks_sec,format=raw,file=%s' % channel,
                           '--image-opts', '-c', 'read -P 85 0 512', qemu_volume._source_image_options(target)])


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


@pytest.mark.skipif(not all(Path(tool).exists() for tool in (qemu_volume.QEMU_IMG, qemu_volume.QEMU_IO)),
                    reason='QEMU tools are required')
@pytest.mark.parametrize('filename', ['standalone.luks', 'standalone,with-comma.luks'])
def test_resize_standalone_luks_keeps_format_and_path(tmp_path, filename):
    target, channel = (str(tmp_path / name) for name in (filename, 'key'))
    Path(channel).write_bytes(b'local-qemu-fixture-key')
    subprocess.check_call([qemu_volume.QEMU_IMG, 'create', '--object',
                           'secret,id=luks_sec,format=raw,file=%s' % channel, '-f', 'luks',
                           '-o', 'key-secret=luks_sec', target, '8M'])

    qemu_volume.resize_with_secret(target, 16 * 1024 * 1024, channel)

    assert qemu_volume.verify_luks_open(target, channel)
    info = dict(qemu_volume.iter_image_chain(target))[target]
    assert info['format'] == 'luks'
    assert info['virtual-size'] == 16 * 1024 * 1024


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
    # Seed the local file directly so replay coverage is independent of CBD initialization options.
    subprocess.check_call(['/usr/sbin/cryptsetup', '-q', 'luksFormat', '--type', 'luks1',
                           '--batch-mode', '--align-payload=%d' % (zbs.LUKS_PAYLOAD_OFFSET // 512),
                           '--key-file', str(good_key), str(target)])
    with patch('zstacklib.utils.lock.NamedLock', return_value=threading.RLock(), create=True), \
            patch.object(zbs, '_initialize') as initialize:
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
        initialize.assert_not_called()


@pytest.mark.parametrize('failure', ['delete_target', 'delete_temporary', 'restore', 'occupied', 'delete_and_restore', 'capacity'])
def test_sharedblock_batch_rollback_keeps_original_error_and_restores_others(monkeypatch, caplog, failure):
    sources = ['/dev/vg/source%d' % index for index in range(3)]
    trash = [path + '_trash' for path in sources]
    volumes = {path: 'original%d' % index for index, path in enumerate(sources)}
    temporary = []
    publish_error = RuntimeError('private-publish-error')
    cleanup_error = RuntimeError('private-cleanup-error')
    delete_calls = []
    items = [SimpleNamespace(resourceUuid=str(index), sourceInstallPath='sharedblock:/'+path[4:],
                             targetInstallPath='sharedblock:/'+path[4:],
                             sourceTrashInstallPath='sharedblock:/'+trash[index][4:])
             for index, path in enumerate(sources)]

    def create(path, *args, **kwargs):
        temporary.append(path)
        volumes[path] = 'converted'

    def rename(source, target, *, overwrite):
        assert not overwrite
        if source in temporary and target == sources[2] and failure != 'capacity':
            if failure == 'occupied':
                volumes[target] = 'unrelated'
            raise publish_error
        if source == trash[2] and failure in ('restore', 'delete_and_restore'):
            raise cleanup_error
        assert target not in volumes
        volumes[target] = volumes.pop(source)
        return 0, '', ''

    def delete(path, raise_exception=True):
        delete_calls.append((path, raise_exception))
        if path not in volumes:
            return
        if ((failure == 'delete_target' and path == sources[0]) or
                (failure in ('delete_temporary', 'delete_and_restore') and path == temporary[2])):
            if raise_exception:
                raise cleanup_error
            return
        volumes.pop(path)

    def read_capacity(vg_uuid):
        assert vg_uuid == 'vg'
        assert all(volumes[path] == 'converted' for path in sources)
        assert all(path in volumes for path in trash)
        raise publish_error

    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    monkeypatch.setattr(block, 'lvm', SimpleNamespace(
        lv_exists=volumes.__contains__, update_pv_allocate_strategy=lambda _: None,
        RecursiveOperateLv=lambda *a, **kw: nullcontext(), OperateLv=lambda *a, **kw: nullcontext(),
        get_lv_size=lambda _: 4096, create_lv_from_absolute_path=create,
        lv_rename=rename, delete_lv=delete, get_vg_size=read_capacity))
    monkeypatch.setattr(qemu_volume, 'convert_qcow2_encryption_to_block', Mock())
    monkeypatch.setattr(qemu_volume, 'verify_luks_open', Mock())
    with pytest.raises(RuntimeError) as caught:
        block.convert_items(SimpleNamespace(targetEncrypted=True, encryptedDek='private-envelope', vgUuid='vg', items=items))
    assert caught.value is publish_error
    assert all(raise_exception for _, raise_exception in delete_calls)
    if failure == 'capacity':
        assert volumes == {source: 'original%d' % index for index, source in enumerate(sources)}
        assert set(dict(delete_calls)) == set(sources)
        return
    assert temporary[2] in dict(delete_calls)
    assert not any(path in dict(delete_calls) for path in temporary[:2])
    unresolved = 0 if failure == 'delete_target' else 2
    for index, source in enumerate(sources):
        if index == unresolved and failure != 'delete_temporary':
            assert volumes[trash[index]] == 'original%d' % index
        else:
            assert volumes[source] == 'original%d' % index
            assert trash[index] not in volumes
    if failure == 'occupied':
        assert volumes[sources[2]] == 'unrelated'
    if failure == 'delete_target':
        assert volumes[sources[0]] == 'converted'
    if failure in ('delete_temporary', 'delete_and_restore'):
        assert volumes[temporary[2]] == 'converted'
    else:
        assert not any(path in volumes for path in temporary)
    summary, = [r.message for r in caplog.records if 'stage=rollback_unresolved=' in r.message]
    if failure == 'delete_and_restore':
        assert all(detail in summary for detail in ('delete_temporary', temporary[2], 'restore_source', trash[2]))
    assert sources[unresolved] in caplog.text and trash[unresolved] in caplog.text
    assert not any(private in caplog.text for private in
                   ('private-publish-error', 'private-cleanup-error', 'private-envelope'))

@pytest.mark.parametrize('artifact', ['secret', 'staged_json', 'command_json'])
@pytest.mark.parametrize('business_fails', [True, False])
def test_sensitive_cleanup_preserves_business_result(tmp_path, monkeypatch, caplog, artifact, business_fails):
    private_path = str(tmp_path / 'private-test-channel')
    envelope = 'synthetic-private-envelope'
    monkeypatch.setattr(http_error, 'logger', logging.getLogger(__name__))
    monkeypatch.setattr(secret, 'prepare_luks_secret_material_channel', lambda _: private_path)
    monkeypatch.setattr(imagestore.tempfile, 'tempdir', str(tmp_path))
    error = RuntimeError('synthetic operation error')

    if artifact == 'secret':
        manager = secret.luks_secret_channel(envelope)
    elif artifact == 'staged_json':
        manager = imagestore.temporary_json({'encryptedDek': envelope})
    else:
        manager = ImageStoreEncryptionExtension.prepare_image_add_command(
            'zstcli add', {'ImageStoreEncryption': {'encryptedDek': envelope}}, None)

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

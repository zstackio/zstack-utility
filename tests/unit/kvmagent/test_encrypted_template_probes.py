import importlib
import json
import os
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from kvmagent.crypto import http_error, qemu_volume, secret
from zstacklib.utils import http, linux


@pytest.fixture
def source(tmp_path):
    if not os.path.exists(qemu_volume.QEMU_IMG):
        pytest.skip('qemu-img is required for the encrypted image probe')
    path = tmp_path / 'encrypted.qcow2'
    key = tmp_path / 'test-key'
    key.write_bytes(b'synthetic probe key')
    tool = qemu_volume.QEMU_IMG
    subprocess.run([tool, 'create', '--object', 'secret,id=key,file=%s' % key, '-f', 'qcow2',
                    '-o', 'encrypt.format=luks,encrypt.key-secret=key,encrypt.iter-time=10',
                    str(path), '32M'], check=True, stdout=subprocess.DEVNULL)
    return path, key.read_bytes()


@pytest.fixture
def probe(monkeypatch, configured_volume_extensions):
    source_plugins = {}
    for name, cls in [('localstorage','LocalStoragePlugin'),
                      ('nfs_primarystorage_plugin','NfsPrimaryStoragePlugin'),
                      ('shared_block_plugin','SharedBlockPlugin')]:
        module = importlib.import_module('kvmagent.plugins.' + name)
        plugin = getattr(module, cls)
        source_plugins[name] = module, plugin.__new__(plugin)
        monkeypatch.setattr(module, 'linux', linux, raising=False)
    def plain_measure(path):
        command = [qemu_volume.QEMU_IMG, 'measure', '-U', '--output=json', '-f', 'qcow2', '-O', 'qcow2', path]
        return int(json.loads(http_error.check_output(command))['required'])

    monkeypatch.setattr(linux, 'qcow2_size_and_actual_size', lambda path: (32 << 20, 0), raising=False)
    monkeypatch.setattr(linux, 'qcow2_get_virtual_size', lambda path: 32 << 20, raising=False)
    monkeypatch.setattr(linux, 'get_img_fmt', lambda path: 'qcow2', raising=False)
    monkeypatch.setattr(linux, 'qcow2_measure_required_size', plain_measure, raising=False)
    shared, _ = source_plugins['shared_block_plugin']
    events = []
    capacities = [40 << 20]

    @contextmanager
    def lock(path, **options):
        events.append(('enter', path, options))
        try:
            yield
        finally:
            events.append(('exit', path, options))

    def resize(path, size, force):
        assert events[-1] == ('close',)
        assert force
        events.append(('resize', path, size))
        capacities[0] = size

    plain_check = Mock(return_value=SimpleNamespace(total_clusters=16, allocated_clusters=1,
                                                    image_end_offset=8 << 20))
    monkeypatch.setattr(shared, 'translate_absolute_path_from_install_path', lambda path: path)
    monkeypatch.setattr(shared, 'lvm', SimpleNamespace(RecursiveOperateLv=lock, get_vg_size=lambda vg: (100, 50),
                        get_lv_size=lambda _: capacities[0], resize_lv=resize))
    monkeypatch.setattr(shared.qemu_img, 'get_check_result', plain_check, raising=False)
    monkeypatch.setattr(shared.qemu_img, 'CheckResult',
                        lambda end, total, errors, allocated, name, fmt: SimpleNamespace(
                            image_end_offset=end, total_clusters=total, allocated_clusters=allocated), raising=False)
    return source_plugins, events, capacities, plain_check


def call(method, **cmd):
    return json.loads(method({http.REQUEST_BODY: json.dumps(cmd)}))


def use_channel(monkeypatch, path, key, events):
    handle = path.parent / 'temporary-channel'
    @contextmanager
    def key_channel(envelope):
        assert envelope == 'synthetic-envelope'
        handle.write_bytes(key)
        events.append(('open',))
        try:
            yield str(handle)
        finally:
            handle.unlink()
            events.append(('close',))
    monkeypatch.setattr(secret, 'luks_secret_channel', key_channel)
    return handle


@pytest.mark.parametrize('plugin_name', ['localstorage', 'nfs_primarystorage_plugin', 'shared_block_plugin'])
def test_estimate_encrypted_template_measures_encrypted_output(probe, source, monkeypatch, plugin_name):
    plugins, events, _, _ = probe
    path, key = source
    _, plugin = plugins[plugin_name]
    channel = use_channel(monkeypatch, path, key, events)
    commands = []
    def inspect(command):
        commands.append(command)
        return http_error.check_output(command)
    monkeypatch.setattr(qemu_volume,'check_output', inspect)
    image = path.read_bytes()

    rsp = call(plugin.estimate_template, volumePath=str(path), encryptedDek='synthetic-envelope')

    assert rsp.get('success', True) and rsp['size'] == 32 << 20
    assert rsp['actualSize'] == json.loads(http_error.check_output([
        qemu_volume.QEMU_IMG, 'measure', '-U', '--output=json', '-O', 'qcow2',
        '-o', 'encrypt.format=luks,encrypt.key-secret=luks_sec', '--object',
        'secret,id=luks_sec,file=%s' % (path.parent/'test-key'), '--image-opts',
        qemu_volume._source_image_options(str(path))]))['required']
    assert [cmd[1] for cmd in commands[:2]] == ['info', 'measure']
    assert '--image-opts' in commands[1] and 'encrypt.format=luks,encrypt.key-secret=luks_sec' in commands[1]
    assert path.read_bytes() == image and not channel.exists()
    assert {f.name for f in path.parent.iterdir()} == {path.name, 'test-key'}
    assert events[1 if plugin_name == 'shared_block_plugin' else 0][0] == 'open'
    if plugin_name == 'shared_block_plugin':
        assert [e[0] for e in events] == ['enter', 'open', 'close', 'exit']
        assert events[0][2]['shared'] is True


@pytest.mark.parametrize('operation', ['estimate_template', 'shrink_snapshot'])
@pytest.mark.parametrize('fault', ['missing', 'wrong', 'tool-error'])
def test_encrypted_probe_failure_closes_channel_without_resizing(probe, source, monkeypatch, operation, fault):
    plugins, events, capacity, plain_check = probe
    shared, plugin = plugins['shared_block_plugin']
    path, _ = source
    if operation == 'shrink_snapshot':
        def unlocked_check(image):
            subprocess.check_output([qemu_volume.QEMU_IMG, 'check', '-U', '--output=json', image],
                                    stderr=subprocess.DEVNULL)
        plain_check.side_effect = unlocked_check
    if fault == 'tool-error':
        def fail_check(command):
            if command[1] != 'info':
                raise http_error.CryptoCommandError(1, [command[0], command[1]])
            return http_error.check_output(command)
        monkeypatch.setattr(qemu_volume,'check_output', fail_check)
    channel = use_channel(monkeypatch, path, b'wrong key', events)
    params = dict(volumePath=str(path), installPath=str(path), vgUuid='vg')
    if fault != 'missing':
        params['encryptedDek'] = 'synthetic-envelope'

    rsp = call(getattr(plugin, operation), **params)

    assert not rsp['success']
    assert events[0][0] == 'enter' and events[-1][0] == 'exit'
    assert all(x[0] != 'resize' for x in events) and capacity[0] == 40 << 20
    if fault != 'missing':
        assert ('close',) in events
    else:
        assert ('open',) not in events
    assert not channel.exists()
    assert 'synthetic-envelope' not in rsp['error'] and str(channel) not in rsp['error']


@pytest.mark.parametrize('fits', [True, False])
def test_encrypted_snapshot_shrinks_only_above_checked_image_end(probe, source, monkeypatch, fits):
    plugins, events, capacity, plain_check = probe
    shared, plugin = plugins['shared_block_plugin']
    path, key = source
    use_channel(monkeypatch, path, key, events)
    checked = []
    def inspect(command):
        output = http_error.check_output(command)
        if command[1] == 'check':
            assert events[0][2]['shared'] is False and events[-1][0] == 'open'
            assert '-U' in command and '--image-opts' in command
            checked.append(json.loads(output)['image-end-offset'])
        return output
    monkeypatch.setattr(qemu_volume,'check_output', inspect)
    if not fits:
        monkeypatch.setattr(shared.linux,'qcow2_get_virtual_size', lambda path: 1)
    rsp = call(plugin.shrink_snapshot, installPath=str(path), vgUuid='vg', encryptedDek='synthetic-envelope')

    assert rsp.get('success', True) and rsp['oldSize'] == 40 << 20
    assert rsp['size'] == capacity[0] == (checked[0] if fits else rsp['oldSize'])
    plain_check.assert_not_called()


def test_plain_snapshot_and_migration_helper_keep_original_bound(probe, monkeypatch):
    plugins, events, capacity, plain_check = probe
    shared, plugin = plugins['shared_block_plugin']
    resize = Mock()
    monkeypatch.setattr(shared.lvm, 'resize_lv', resize)
    monkeypatch.setattr(shared.linux,'qcow2_get_virtual_size', lambda path: 4 << 20)
    channel = Mock(side_effect=AssertionError('ordinary request must not consume a secret channel'))
    monkeypatch.setattr(secret, 'luks_secret_channel', channel)
    assert call(plugin.shrink_snapshot, installPath='/dev/vg/v', vgUuid='vg').get('success', True)
    plugin.shrink_lv_on_qcow2('/dev/vg/v', 1024)
    assert resize.call_count == 2
    assert all(c.args == ('/dev/vg/v', 4 << 20, True) for c in resize.call_args_list)
    assert plain_check.call_count == 2
    channel.assert_not_called()


@pytest.mark.parametrize('plugin_name', ['localstorage', 'nfs_primarystorage_plugin', 'shared_block_plugin'])
def test_plain_estimate_keeps_original_measurement_and_size(probe, monkeypatch, plugin_name):
    plugins, _, _, _ = probe
    _, plugin = plugins[plugin_name]
    measure = Mock(return_value=12345)
    monkeypatch.setattr(linux, 'qcow2_measure_required_size', measure)
    channel = Mock(side_effect=AssertionError('plain estimate must not open a secret channel'))
    monkeypatch.setattr(secret, 'luks_secret_channel', channel)

    rsp = call(plugin.estimate_template, volumePath='/test/volume')

    assert rsp.get('success', True) and rsp['size'] == 32 << 20 and rsp['actualSize'] == 12345
    measure.assert_called_once_with('/test/volume')
    channel.assert_not_called()

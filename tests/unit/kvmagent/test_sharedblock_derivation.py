import json
import importlib
import inspect
import logging
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


for name in ('rados', 'rbd', 'libvirt', 'virtinst'):
    sys.modules.setdefault(name, MagicMock())

plugin_path = Path(__file__).parents[3] / 'kvmagent/kvmagent/plugins/shared_block_plugin.py'
plugin_spec = importlib.util.spec_from_file_location('shared_block_derivation_under_test', plugin_path)
sharedblock = importlib.util.module_from_spec(plugin_spec)
plugin_spec.loader.exec_module(sharedblock)


@pytest.fixture
def handler(monkeypatch):
    plugin = sharedblock.SharedBlockPlugin.__new__(sharedblock.SharedBlockPlugin)
    plugin.vgs_path_and_wwid = {}
    monkeypatch.setattr(sharedblock, 'time', time, raising=False)
    driver = MagicMock()
    driver.required_allocation_size.side_effect = lambda size: size + 8 * 1024 * 1024
    monkeypatch.setattr(sharedblock.driver_factory, 'get_shared_block_driver', lambda cmd: driver)
    monkeypatch.setattr(sharedblock, 'translate_absolute_path_from_install_path', lambda path: '/dev/' + path)
    create_lv = MagicMock()
    lvm = SimpleNamespace(RecursiveOperateLv=lambda *args, **kwargs: nullcontext(),
                          OperateLv=lambda *args, **kwargs: nullcontext(),
                          lv_exists=lambda path: False,
                          update_pv_allocate_strategy=lambda cmd: None,
                          create_lv_from_absolute_path=create_lv,
                          create_lv_from_cmd=MagicMock(),
                          delete_lv=MagicMock(),
                          get_vg_size=lambda vg: (100, 50),
                          get_lv_size=lambda path: 9 * 1024 * 1024,
                          get_lun_capacities_from_vg=lambda vg, paths: [],
                          calcLvReservedSize=lambda size: 1024 * 1024,
                          round_to=lambda size, alignment: size)
    linux = SimpleNamespace(qcow2_size_and_actual_size=lambda path: (200, 100),
                            qcow2_virtualsize=lambda path: 2 * 1024 * 1024 * 1024,
                            qcow2_create_with_backing_file_and_option=MagicMock())
    monkeypatch.setattr(sharedblock, 'lvm', lvm)
    monkeypatch.setattr(sharedblock, 'linux', linux, raising=False)
    monkeypatch.setattr(sharedblock, 'traceable_shell', SimpleNamespace(get_shell=lambda cmd: None))
    monkeypatch.setattr(plugin, 'get_total_required_size', lambda path: 1024 * 1024)
    return plugin, driver, create_lv


def request(**changes):
    command = {'volumePath': 'source', 'installPath': 'target', 'vgUuid': 'vg',
               'hostUuid': 'host', 'sharedVolume': False, 'compareQcow2': False,
               'incremental': False}
    command.update(changes)
    return {sharedblock.http.REQUEST_BODY: json.dumps(command)}


def use_plain_driver(monkeypatch):
    from kvmagent.volume import plain_shared_block_driver

    monkeypatch.setattr(plain_shared_block_driver, 'linux', sharedblock.linux)

    def select_plain_driver(cmd):
        assert not getattr(cmd, 'encryptedDek', None), 'plain derivation must not receive a sealed DEK'
        return plain_shared_block_driver.PlainSharedBlockVolumeDriver(cmd)

    monkeypatch.setattr(sharedblock.driver_factory, 'get_shared_block_driver', select_plain_driver)


@pytest.mark.parametrize('operation', ['create_template_from_volume', 'create_image_cache_from_volume'])
def test_plain_template_and_full_cache_keep_original_allocation_and_qcow2_copy(handler, monkeypatch, operation):
    plugin, encrypted_driver, create_lv = handler
    plain_copy = MagicMock()
    monkeypatch.setattr(sharedblock.linux, 'create_template', plain_copy, raising=False)
    use_plain_driver(monkeypatch)

    result = json.loads(getattr(plugin, operation)(request()))

    assert result['success']
    assert result['size'] == 200 and result['actualSize'] == 100
    assert create_lv.call_args.args[1] == 1024 * 1024
    plain_copy.assert_called_once_with('/dev/source', '/dev/target', shell=None)
    encrypted_driver.create_template.assert_not_called()


def test_encrypted_template_reserves_header_and_uses_luks_driver(handler):
    plugin, driver, create_lv = handler
    result = json.loads(plugin.create_template_from_volume(request(encryptedDek='wrapped')))

    assert result['success']
    assert create_lv.call_args.args[1] == 9 * 1024 * 1024
    driver.create_template.assert_called_once_with('/dev/source', '/dev/target', None)


def test_encrypted_incremental_cache_keeps_encrypted_backing(handler, monkeypatch):
    plugin, driver, create_lv = handler
    monkeypatch.setattr(sharedblock.lvm, 'calcLvReservedSize', lambda size: 1024 * 1024)
    monkeypatch.setattr(sharedblock.lvm, 'round_to', lambda size, alignment: size)
    plain_create = MagicMock()
    monkeypatch.setattr(sharedblock.linux, 'qcow2_create_with_backing_file_and_option', plain_create)

    result = json.loads(plugin.create_image_cache_from_volume(request(incremental=True, encryptedDek='wrapped')))

    assert result['success']
    assert create_lv.call_args.args[1] == 9 * 1024 * 1024
    driver.create_with_backing.assert_called_once_with(
        '/dev/source', '/dev/target', 2 * 1024 * 1024 * 1024, '')
    plain_create.assert_not_called()


def test_encrypted_full_cache_copies_luks_format(handler):
    plugin, driver, create_lv = handler
    result = json.loads(plugin.create_image_cache_from_volume(request(encryptedDek='wrapped')))

    assert result['success']
    assert create_lv.call_args.args[1] == 9 * 1024 * 1024
    driver.create_template.assert_called_once_with('/dev/source', '/dev/target', None)


def test_plain_incremental_cache_keeps_existing_qcow2_path(handler, monkeypatch):
    plugin, driver, create_lv = handler
    use_plain_driver(monkeypatch)
    monkeypatch.setattr(sharedblock.lvm, 'calcLvReservedSize', lambda size: 1024 * 1024)
    monkeypatch.setattr(sharedblock.lvm, 'round_to', lambda size, alignment: size)
    plain_create = MagicMock()
    monkeypatch.setattr(sharedblock.linux, 'qcow2_create_with_backing_file_and_option', plain_create)

    result = json.loads(plugin.create_image_cache_from_volume(request(incremental=True)))

    assert result['success']
    assert create_lv.call_args.args[1] == 1024 * 1024
    plain_create.assert_called_once_with('/dev/source', '/dev/target')
    driver.create_with_backing.assert_not_called()


def test_encrypted_snapshot_reserves_unformatted_lv(handler):
    plugin, driver, _ = handler
    command = request(reserveOnly=True, encryptedDek='wrapped', size=1024 * 1024)
    result = json.loads(inspect.unwrap(plugin.create_empty_volume)(plugin, command))

    assert result['success']
    assert result['size'] == 1024 * 1024
    assert sharedblock.lvm.create_lv_from_cmd.call_args.args[1] == 9 * 1024 * 1024
    driver.create_empty.assert_not_called()
    driver.create_with_backing.assert_not_called()


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_failed_reservation_removes_only_new_lv(handler, monkeypatch, caplog, cleanup_fails):
    plugin, _, _ = handler
    reserved = set()
    error = RuntimeError('capacity failed')
    monkeypatch.setattr(sharedblock, 'logger', logging.getLogger(__name__))
    sharedblock.lvm.create_lv_from_cmd.side_effect = lambda path, *args: reserved.add(path)

    def read_capacity(_):
        assert reserved == {'/dev/target'}
        raise error

    def delete(path):
        if cleanup_fails:
            raise RuntimeError('private cleanup detail')
        reserved.remove(path)

    monkeypatch.setattr(sharedblock.lvm, 'get_vg_size', read_capacity)
    sharedblock.lvm.delete_lv.side_effect = delete
    command = request(reserveOnly=True, encryptedDek='wrapped', size=1024 * 1024)
    with pytest.raises(RuntimeError) as caught:
        inspect.unwrap(plugin.create_empty_volume)(plugin, command)

    assert caught.value is error
    sharedblock.lvm.delete_lv.assert_called_once_with('/dev/target')
    assert reserved == ({'/dev/target'} if cleanup_fails else set())
    if cleanup_fails:
        assert 'rollback left LV path=' in caplog.text and '/dev/target' in caplog.text
    assert 'private cleanup detail' not in caplog.text

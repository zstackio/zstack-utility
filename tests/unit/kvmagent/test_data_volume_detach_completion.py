"""Replay asynchronous disk removal with the legacy retry and polling code."""
import contextlib
import functools
from pathlib import Path
import re
import traceback
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[3]
VM_PLUGIN = ROOT / 'kvmagent/kvmagent/plugins/vm_plugin.py'
LINUX = ROOT / 'zstacklib/zstacklib/utils/linux.py'
MISC = ROOT / 'zstacklib/zstacklib/utils/misc.py'
BUSY = "Hot-unplug failed: guest is busy (power indicator blinking)"


def _function_source(path, name, indent=''):
    match = re.search(
        r'^' + indent + r'def ' + name + r'\(.*?(?=^' + indent + r'(?:def |class |@)|\Z)',
        path.read_text(), re.MULTILINE | re.DOTALL,
    )
    assert match is not None, name
    return match.group(0)


class LibvirtError(Exception):
    @property
    def message(self):
        return str(self)


@pytest.fixture
def detach():
    state = SimpleNamespace(now=0, removed_at=24, rejection=None,
                            persistent=True, config_error=None, config_removals=[])

    def sleep(seconds):
        state.now += seconds

    namespace = {'functools': functools, 'logger': MagicMock(),
                 'time': SimpleNamespace(time=lambda: state.now, sleep=sleep)}
    for path, name in ((LINUX, 'retry'), (LINUX, 'wait_callback_success'),
                       (MISC, 'ignore_exception')):
        exec(compile(_function_source(path, name), str(path), 'exec'), namespace)
    namespace.update({
        'linux': SimpleNamespace(retry=namespace['retry'],
                                 wait_callback_success=namespace['wait_callback_success'],
                                 get_exception_stacktrace=lambda: '',
                                 get_libvirt_version=lambda: '6.0.0'),
        'misc': SimpleNamespace(ignore_exception=contextlib.contextmanager(namespace['ignore_exception'])),
        'libvirt': SimpleNamespace(libvirtError=LibvirtError, VIR_DOMAIN_AFFECT_LIVE=1,
                                  VIR_DOMAIN_AFFECT_CONFIG=2),
        'traceback': traceback,
        'kvmagent': SimpleNamespace(KvmError=RuntimeError),
        'is_libvirt_support_blockdev': lambda version: True,
    })
    methods = ('_detach_data_volume', '_record_volume_detach_timeout',
               '_volume_detach_timed_out', '_clean_timeout_record')
    source = 'class Vm:\n' + ''.join(_function_source(VM_PLUGIN, name, '    ') for name in methods)
    exec(compile(source, str(VM_PLUGIN), 'exec'), namespace)
    vm_class = namespace['Vm']
    vm_class.timeout_detached_vol = set()
    vm = vm_class()
    vm.uuid = 'vm-uuid'
    vm.domain_xml = '<domain/>'
    volume = SimpleNamespace(deviceId=1, deviceType='file', installPath='/data.qcow2',
                             volumeUuid='volume-uuid', useVirtio=True)
    disk = MagicMock()
    disk.dump.return_value = '<disk type="file"><source file="/data.qcow2"/><target dev="vdb"/></disk>'

    def get_disk(*args, **kwargs):
        return (None, None) if state.now >= state.removed_at else (disk, 'vdb')

    attempts = []

    def request_detach(xml, flags):
        if flags == 2:
            assert state.now >= state.removed_at
            state.config_removals.append(xml)
            if state.config_error:
                raise LibvirtError(state.config_error)
            return
        attempts.append(state.now)
        if state.rejection:
            raise LibvirtError(state.rejection)
        if len(attempts) == 1:
            sleep(5)
            return
        raise LibvirtError(BUSY)

    vm._get_target_disk = get_disk
    vm.domain = SimpleNamespace(detachDeviceFlags=request_detach,
                                isPersistent=lambda: state.persistent)
    namespace['get_vm_by_uuid'] = lambda uuid: vm
    state.run = lambda: vm._detach_data_volume(volume)
    state.attempts = attempts
    state.records = vm_class.timeout_detached_vol
    state.logger = namespace['logger']
    return state


def test_removal_during_last_retry_sleep_is_success(detach):
    detach.run()
    assert len(detach.attempts) == 3
    assert detach.now >= detach.removed_at
    assert detach.records == set()
    assert len(detach.config_removals) == 1


def test_device_still_attached_after_retries_is_failure(detach):
    detach.removed_at = float('inf')
    with pytest.raises(RuntimeError, match='guest is busy'):
        detach.run()
    assert len(detach.attempts) == 3
    assert detach.records == {'/data.qcow2-vm-uuid'}
    assert detach.config_removals == []


def test_ordinary_rejection_remains_failure(detach):
    detach.removed_at = float('inf')
    detach.rejection = 'permission denied'
    with pytest.raises(RuntimeError, match='permission denied'):
        detach.run()
    assert len(detach.attempts) == 3
    assert detach.config_removals == []


def test_removal_during_first_poll_needs_no_retry(detach):
    detach.removed_at = 7
    detach.run()
    assert len(detach.attempts) == 1
    assert detach.records == set()
    assert len(detach.config_removals) == 1


def test_config_failure_does_not_fail_completed_live_detach(detach):
    detach.config_error = 'config update failed'
    detach.run()
    assert len(detach.config_removals) == 1
    assert detach.records == set()
    assert any('failed to remove detached volume' in call.args[0]
               for call in detach.logger.warn.call_args_list)


def test_transient_vm_does_not_modify_persistent_config(detach):
    detach.persistent = False
    detach.run()
    assert detach.config_removals == []
    assert detach.records == set()

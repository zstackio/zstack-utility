"""Check failure cleanup by running the real mixed-volume test through unittest."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, call

import pytest


CASE = (Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/test'
        / 'localstorage_testsuite/test_data_volume_with_iothreadpin.py')
MIXED_CASE = 'test_virtio_and_virtio_scsi_data_volume_with_iothreadpin'


@pytest.fixture
def mixed_case():
    tree = ast.parse(CASE.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TestVolumeWithIoThreadPin')
    utils = SimpleNamespace(
        VmPluginTestStub=type('VmPluginTestStub', (), {}),
        attach_iothreadpin_volume_to_vm=MagicMock(return_value=(None, object())),
        attach_virtio_scsi_iothread_volume_to_vm=MagicMock(return_value=(None, object())),
        check_volume=MagicMock(return_value=SimpleNamespace(success=False)),
        destroy_vm=MagicMock(),
    )
    namespace = {
        'TestCase': unittest.TestCase, 'vm_utils': utils,
        'volume_utils': SimpleNamespace(create_empty_volume=MagicMock(return_value=('volume', '/data.qcow2'))),
        'network_utils': MagicMock(), 'logger': MagicMock(),
        'linux': SimpleNamespace(find_vm_pid_by_uuid=MagicMock(return_value=123)),
        'pytest_utils': SimpleNamespace(ztest_decorater=lambda fn: fn),
        'pytest': SimpleNamespace(mark=SimpleNamespace(run=lambda **kwargs: lambda fn: fn)),
    }
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(CASE), 'exec'), namespace)
    case = namespace['TestVolumeWithIoThreadPin'](MIXED_CASE)
    case._create_vm = MagicMock(return_value=('owned-vm', object()))
    return case, namespace


def test_failed_mixed_case_cleans_vm_before_next_case(mixed_case):
    case, namespace = mixed_case
    result = unittest.TestResult()
    case.run(result)
    assert len(result.failures) == 1
    assert result.errors == []
    namespace['vm_utils'].destroy_vm.assert_called_once_with('owned-vm')


def test_cleanup_does_not_destroy_stopped_vm(mixed_case):
    case, namespace = mixed_case
    namespace['linux'].find_vm_pid_by_uuid.return_value = None
    result = unittest.TestResult()
    case.run(result)
    assert len(result.failures) == 1
    assert result.errors == []
    namespace['linux'].find_vm_pid_by_uuid.assert_called_once_with('owned-vm')
    namespace['vm_utils'].destroy_vm.assert_not_called()


def test_cleanup_error_keeps_original_assertion_visible(mixed_case):
    case, namespace = mixed_case
    namespace['vm_utils'].destroy_vm.side_effect = RuntimeError('cleanup unavailable')
    result = unittest.TestResult()
    case.run(result)
    assert len(result.failures) == 1
    assert result.errors == []
    namespace['logger'].warning.assert_called_once()


@pytest.mark.parametrize('success', [True, False])
@pytest.mark.parametrize('remaining_pid', ['123', ''])
def test_cleanup_checks_vm_after_destroy(mixed_case, success, remaining_pid):
    case, namespace = mixed_case
    namespace['vm_utils'].destroy_vm.return_value = json.dumps({
        'success': success, 'error': '' if success else 'destroy timed out',
    })
    pid_lookup = namespace['linux'].find_vm_pid_by_uuid
    pid_lookup.side_effect = ['123', remaining_pid]
    result = unittest.TestResult()

    case.run(result)

    assert len(result.failures) == 1
    assert result.errors == []
    namespace['vm_utils'].destroy_vm.assert_called_once_with('owned-vm')
    assert pid_lookup.call_args_list == [call('owned-vm'), call('owned-vm')]
    if remaining_pid:
        namespace['logger'].warning.assert_called_once_with(
            "tearDown cleanup failed: vm[%s] still running", 'owned-vm')
    else:
        namespace['logger'].warning.assert_not_called()

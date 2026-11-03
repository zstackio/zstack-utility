"""Production-path regression tests for QGA CPU hotplug online."""
import json
from unittest.mock import MagicMock, call, patch
from types import SimpleNamespace

import pytest

from kvmagent.plugins import vm_plugin


def _vcpus(ids, offline=()):
    return [{'logical-id': cpu_id, 'online': cpu_id not in offline} for cpu_id in ids]


def _vm():
    vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
    vm.domain = MagicMock()
    vm.uuid = 'vm-uuid'
    vm._has_smbios_cpu_hotplug = MagicMock(return_value=False)
    return vm


def _qga(get_results, set_results=(), guest_os='Ubuntu 22.04'):
    qga = MagicMock()
    qga.state = vm_plugin.VmQga.QGA_STATE_RUNNING
    qga.os = guest_os
    qga.call_qga_command.side_effect = list(get_results) + list(set_results)
    return qga


def _snapshot(qga, vm=None, arch='x86_64'):
    qga_factory = MagicMock(return_value=qga)
    qga_factory.QGA_STATE_RUNNING = vm_plugin.VmQga.QGA_STATE_RUNNING
    with patch.object(vm_plugin, 'HOST_ARCH', arch), \
            patch.object(vm_plugin, 'VmQga', qga_factory):
        return (vm or _vm())._qga_snapshot_cpu_ids()


def _online(qga, known_ids=range(4), added=2):
    with patch.object(vm_plugin.time, 'sleep') as sleep:
        _vm()._qga_online_hotplugged_cpus((qga, set(known_ids)), added)
    return sleep


def _commands(qga, name):
    return [c for c in qga.call_qga_command.call_args_list if c.args[0] == name]


def test_snapshot_records_current_guest_cpu_ids():
    qga = _qga([_vcpus(range(4), offline=(1,))])
    snapshot = _snapshot(qga)
    assert snapshot == (qga, {0, 1, 2, 3})
    assert len(_commands(qga, 'guest-get-vcpus')) == 1


@pytest.mark.parametrize('arch, guest_os, smbios, qga_state', [
    ('aarch64', 'ubuntu', False, vm_plugin.VmQga.QGA_STATE_RUNNING),
    ('x86_64', 'centos', False, vm_plugin.VmQga.QGA_STATE_RUNNING),
    ('x86_64', 'ubuntu', True, vm_plugin.VmQga.QGA_STATE_RUNNING),
    ('x86_64', 'ubuntu', False, 'stopped'),
])
def test_snapshot_keeps_arch_os_qga_and_smbios_guards(arch, guest_os, smbios, qga_state):
    qga = _qga([_vcpus(range(4))], guest_os=guest_os)
    qga.state = qga_state
    vm = _vm()
    vm._has_smbios_cpu_hotplug.return_value = smbios
    assert _snapshot(qga, vm=vm, arch=arch) is None
    assert not _commands(qga, 'guest-get-vcpus')


@pytest.mark.parametrize('bad_reply', [
    None, {}, 'invalid', [],
    [{'logical-id': '4', 'online': False}],
    [{'logical-id': True, 'online': False}],
    [{'logical-id': 4, 'online': 0}],
])
def test_snapshot_invalid_or_malformed_reply_skips_qga_online(bad_reply):
    assert _snapshot(_qga([bad_reply])) is None


def test_snapshot_qga_errors_are_swallowed():
    assert _snapshot(_qga([RuntimeError('qga unavailable')])) is None
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin, 'VmQga', side_effect=RuntimeError('no qga')):
        assert _vm()._qga_snapshot_cpu_ids() is None


@pytest.mark.parametrize('guest_os', ['Ubuntu 22.04', 'Debian 12'])
def test_waits_for_new_ids_then_onlines_only_new_offline_cpus(guest_os):
    qga = _qga([_vcpus(range(4), offline=(1, 2)), _vcpus(range(5), offline=(1, 2)),
                _vcpus(range(6), offline=(1, 2, 4, 5))], [2], guest_os=guest_os)
    sleep = _online(qga)
    assert len(_commands(qga, 'guest-get-vcpus')) == 3
    assert qga.call_qga_command.call_args_list[-1] == call(
        'guest-set-vcpus', args={'vcpus': [
            {'logical-id': 4, 'online': True}, {'logical-id': 5, 'online': True}]})
    assert sleep.call_count == 2


def test_noncontiguous_new_cpu_ids_are_onlined():
    qga = _qga([_vcpus([0, 1, 2, 3, 8, 9], offline=(8, 9))], [2])
    sleep = _online(qga)
    assert qga.call_qga_command.call_args_list[-1] == call(
        'guest-set-vcpus', args={'vcpus': [
            {'logical-id': 8, 'online': True}, {'logical-id': 9, 'online': True}]})
    assert sleep.call_count == 0


def test_last_enumeration_attempt_can_be_complete():
    qga = _qga([_vcpus(range(4))] * 4 + [_vcpus(range(6), offline=(4, 5))], [2])
    sleep = _online(qga)
    assert len(_commands(qga, 'guest-get-vcpus')) == 5
    assert qga.call_qga_command.call_args_list[-1].args[0] == 'guest-set-vcpus'
    assert sleep.call_count == 4


def test_never_complete_enumeration_is_bounded_to_five_queries():
    qga = _qga([_vcpus(range(5), offline=(4,))] * 5)
    with patch.object(vm_plugin.logger, 'warning') as warning:
        sleep = _online(qga)
    assert len(_commands(qga, 'guest-get-vcpus')) == 5
    assert not _commands(qga, 'guest-set-vcpus')
    assert sleep.call_count == 4
    warning.assert_called_once()


@pytest.mark.parametrize('bad_reply', [
    None, {}, 'invalid',
    [{'logical-id': '4', 'online': False}],
    [{'logical-id': True, 'online': False}],
    [{'logical-id': 4, 'online': 0}],
])
def test_invalid_or_malformed_reply_after_hotplug_exits_without_set(bad_reply):
    qga = _qga([bad_reply])
    _online(qga)
    assert [c.args[0] for c in qga.call_qga_command.call_args_list] == ['guest-get-vcpus']


def test_partial_set_resumes_at_remaining_suffix():
    qga = _qga([_vcpus(range(6), offline=(4, 5))], [1, 1])
    _online(qga)
    sets = [c.kwargs['args']['vcpus'] for c in _commands(qga, 'guest-set-vcpus')]
    assert [[cpu['logical-id'] for cpu in group] for group in sets] == [[4, 5], [5]]


def test_new_cpus_already_online_need_no_set_request():
    qga = _qga([_vcpus(range(6))])
    _online(qga)
    assert [c.args[0] for c in qga.call_qga_command.call_args_list] == ['guest-get-vcpus']


@pytest.mark.parametrize('result', [0, None, True, 3])
def test_invalid_or_zero_set_progress_exits(result):
    qga = _qga([_vcpus(range(6), offline=(4, 5))], [result])
    _online(qga)
    assert len(_commands(qga, 'guest-set-vcpus')) == 1


def test_set_exception_is_swallowed():
    qga = _qga([_vcpus(range(6), offline=(4, 5))], [RuntimeError('qga failed')])
    _online(qga)
    assert len(_commands(qga, 'guest-set-vcpus')) == 1


def test_qga_query_exception_after_hotplug_is_swallowed():
    qga = _qga([RuntimeError('qga unavailable')])
    _online(qga)
    assert [c.args[0] for c in qga.call_qga_command.call_args_list] == ['guest-get-vcpus']


@pytest.mark.parametrize('manufacturer, product, expected', [
    ('Microsoft Corporation', 'Virtual Machine', True),
    ('Other', 'Virtual Machine', False),
    ('Microsoft Corporation', 'Other', False),
])
def test_smbios_auto_online_marker_uses_production_xml_check(manufacturer, product, expected):
    vm = _vm()
    del vm._has_smbios_cpu_hotplug
    entries = [SimpleNamespace(name_='manufacturer', text_=manufacturer),
               SimpleNamespace(name_='product', text_=product)]
    system = MagicMock()
    system.get_child_node_as_list.return_value = entries
    sysinfo = MagicMock()
    sysinfo.get_child_node.return_value = system
    vm.domain_xmlobject = MagicMock()
    vm.domain_xmlobject.get_child_node.return_value = sysinfo
    assert vm._has_smbios_cpu_hotplug() is expected


def _run_handler(handler_name, payload, cpu_nums, snapshot):
    from tests.unit.kvmagent.test_vm_plugin_handlers import _make_req, _make_vm_plugin
    plugin = _make_vm_plugin()
    vm = MagicMock()
    vm.get_cpu_num.side_effect = cpu_nums
    vm.get_memory.return_value = 4096
    vm._qga_snapshot_cpu_ids.return_value = snapshot
    events = MagicMock()
    events.attach_mock(vm.hotplug_mem, 'hotplug_mem')
    events.attach_mock(vm._qga_snapshot_cpu_ids, 'snapshot')
    events.attach_mock(vm.hotplug_cpu, 'hotplug_cpu')
    events.attach_mock(vm._qga_online_hotplugged_cpus, 'online')
    with patch.object(vm_plugin, 'get_vm_by_uuid', side_effect=[vm, vm]):
        result = json.loads(getattr(plugin, handler_name)(_make_req(payload)))
    return result, vm, events


@pytest.mark.parametrize('handler_name, payload', [
    ('online_increase_cpu', {'vmUuid': 'vm-uuid', 'cpuNum': 6}),
    ('online_change_cpumem', {'vmUuid': 'vm-uuid', 'cpuNum': 6, 'memorySize': 4096}),
])
def test_cpu_hotplug_handlers_snapshot_before_hotplug_and_online_after(handler_name, payload):
    snapshot = (MagicMock(), {0, 1, 2, 3})
    result, vm, events = _run_handler(handler_name, payload, [4, 6, 6], snapshot)
    assert result['success'] is True
    assert result['cpuNum'] == 6
    vm._qga_online_hotplugged_cpus.assert_called_once_with(snapshot, 2)
    order = [c for c in events.mock_calls
             if c in (call.hotplug_mem(4096), call.snapshot(), call.hotplug_cpu(6),
                      call.online(snapshot, 2))]
    expected = [call.snapshot(), call.hotplug_cpu(6), call.online(snapshot, 2)]
    if handler_name == 'online_change_cpumem':
        expected = [call.hotplug_mem(4096)] + expected
    assert order == expected


@pytest.mark.parametrize('handler_name, payload', [
    ('online_increase_cpu', {'vmUuid': 'vm-uuid', 'cpuNum': 6}),
    ('online_change_cpumem', {'vmUuid': 'vm-uuid', 'cpuNum': 6, 'memorySize': 4096}),
])
def test_cpu_hotplug_handlers_skip_qga_online_without_snapshot(handler_name, payload):
    result, vm, _ = _run_handler(handler_name, payload, [4, 6, 6], None)
    assert result['success'] is True
    vm.hotplug_cpu.assert_called_once_with(6)
    vm._qga_online_hotplugged_cpus.assert_not_called()


def test_cpu_memory_handler_skips_qga_when_cpu_count_does_not_increase():
    result, vm, events = _run_handler(
        'online_change_cpumem', {'vmUuid': 'vm-uuid', 'cpuNum': 4, 'memorySize': 4096},
        [4, 4], (MagicMock(), {0, 1, 2, 3}))
    assert result['success'] is True
    assert result['cpuNum'] == 4
    assert events.mock_calls.index(call.hotplug_mem(4096)) < events.mock_calls.index(call.hotplug_cpu(4))
    vm._qga_snapshot_cpu_ids.assert_not_called()
    vm._qga_online_hotplugged_cpus.assert_not_called()

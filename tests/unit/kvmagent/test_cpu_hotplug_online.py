"""Production-path regression tests for ZSTAC-90466."""
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


def _run(qga, prev=4, target=6):
    qga_factory = MagicMock(return_value=qga)
    qga_factory.QGA_STATE_RUNNING = vm_plugin.VmQga.QGA_STATE_RUNNING
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin, 'VmQga', qga_factory), \
            patch.object(vm_plugin.time, 'sleep') as sleep:
        _vm()._qga_online_hotplugged_cpus(prev, target)
    return sleep


def _qga(get_results, set_results=(), guest_os='Ubuntu 22.04'):
    qga = MagicMock()
    qga.state = vm_plugin.VmQga.QGA_STATE_RUNNING
    qga.os = guest_os
    qga.call_qga_command.side_effect = list(get_results) + list(set_results)
    return qga


@pytest.mark.parametrize('guest_os', ['Ubuntu 22.04', 'Debian 12'])
def test_waits_for_all_new_ids_then_onlines_only_new_offline_cpus(guest_os):
    qga = _qga([_vcpus(range(4)), _vcpus(range(5)),
                _vcpus(range(7), offline=(1, 2, 4, 5, 6))], [2], guest_os=guest_os)
    sleep = _run(qga)
    assert [c for c in qga.call_qga_command.call_args_list
            if c.args[0] == 'guest-get-vcpus'] == [
                call('guest-get-vcpus'), call('guest-get-vcpus'), call('guest-get-vcpus')]
    assert qga.call_qga_command.call_args_list[-1] == call(
        'guest-set-vcpus', args={'vcpus': [
            {'logical-id': 4, 'online': True}, {'logical-id': 5, 'online': True}]})
    assert sleep.call_count == 2


def test_last_enumeration_attempt_can_be_complete():
    qga = _qga([_vcpus(range(4)), _vcpus(range(4)), _vcpus(range(4)),
                _vcpus(range(4)), _vcpus(range(6), offline=(4, 5))], [2])
    sleep = _run(qga)
    assert sum(c.args[0] == 'guest-get-vcpus'
               for c in qga.call_qga_command.call_args_list) == 5
    assert qga.call_qga_command.call_args_list[-1].args[0] == 'guest-set-vcpus'
    assert sleep.call_count == 4


@pytest.mark.parametrize('bad_reply', [
    None, {}, 'invalid',
    [{'logical-id': '4', 'online': False}],
    [{'logical-id': True, 'online': False}],
    [{'logical-id': 4, 'online': 0}],
])
def test_invalid_or_malformed_get_reply_exits_without_set(bad_reply):
    qga = _qga([bad_reply])
    _run(qga)
    assert [c.args[0] for c in qga.call_qga_command.call_args_list] == ['guest-get-vcpus']


def test_empty_get_reply_retries_until_enumeration_limit():
    qga = _qga([[]] * 5)
    with patch.object(vm_plugin.logger, 'warning') as warning:
        sleep = _run(qga)
    assert sum(c.args[0] == 'guest-get-vcpus'
               for c in qga.call_qga_command.call_args_list) == 5
    assert sleep.call_count == 4
    warning.assert_called_once()


def test_never_complete_enumeration_is_bounded_to_five_queries():
    qga = _qga([_vcpus(range(5))] * 5)
    sleep = _run(qga)
    assert sum(c.args[0] == 'guest-get-vcpus'
               for c in qga.call_qga_command.call_args_list) == 5
    assert sleep.call_count == 4
    assert all(c.args[0] != 'guest-set-vcpus'
               for c in qga.call_qga_command.call_args_list)


def test_partial_set_resumes_at_remaining_suffix():
    qga = _qga([_vcpus(range(6), offline=(4, 5))], [1, 1])
    _run(qga)
    sets = [c.kwargs['args']['vcpus'] for c in qga.call_qga_command.call_args_list
            if c.args[0] == 'guest-set-vcpus']
    assert [[cpu['logical-id'] for cpu in group] for group in sets] == [[4, 5], [5]]


def test_fully_enumerated_online_cpus_need_no_set_request():
    qga = _qga([_vcpus(range(6))])
    _run(qga)
    assert [c.args[0] for c in qga.call_qga_command.call_args_list] == ['guest-get-vcpus']


@pytest.mark.parametrize('result', [0, None, True, 3])
def test_invalid_or_zero_set_progress_exits(result):
    qga = _qga([_vcpus(range(6), offline=(4, 5))], [result])
    _run(qga)
    assert sum(c.args[0] == 'guest-set-vcpus'
               for c in qga.call_qga_command.call_args_list) == 1


def test_set_exception_is_swallowed():
    qga = _qga([_vcpus(range(6), offline=(4, 5))], [RuntimeError('qga failed')])
    _run(qga)
    assert sum(c.args[0] == 'guest-set-vcpus'
               for c in qga.call_qga_command.call_args_list) == 1


def test_qga_query_exception_is_swallowed():
    qga = _qga([RuntimeError('qga unavailable')])
    _run(qga)
    assert [c.args[0] for c in qga.call_qga_command.call_args_list] == ['guest-get-vcpus']


def test_qga_construction_exception_is_swallowed():
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin, 'VmQga', side_effect=RuntimeError('no qga')):
        _vm()._qga_online_hotplugged_cpus(4, 6)


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


@pytest.mark.parametrize('handler_name, payload', [
    ('online_increase_cpu', {'vmUuid': 'vm-uuid', 'cpuNum': 6}),
    ('online_change_cpumem', {'vmUuid': 'vm-uuid', 'cpuNum': 6, 'memorySize': 4096}),
])
def test_cpu_hotplug_handlers_pass_previous_and_target_counts(handler_name, payload):
    from tests.unit.kvmagent.test_vm_plugin_handlers import _make_req, _make_vm_plugin
    plugin = _make_vm_plugin()
    vm = MagicMock()
    vm.get_cpu_num.side_effect = [4, 6, 6]
    vm.get_memory.return_value = 4096
    with patch.object(vm_plugin, 'get_vm_by_uuid', side_effect=[vm, vm]), \
            patch.object(vm, '_qga_online_hotplugged_cpus') as online:
        events = MagicMock()
        events.attach_mock(vm.hotplug_cpu, 'hotplug_cpu')
        events.attach_mock(vm.hotplug_mem, 'hotplug_mem')
        events.attach_mock(online, 'online')
        result = getattr(plugin, handler_name)(_make_req(payload))
    online.assert_called_once_with(4, 6)
    assert json.loads(result)['success'] is True
    assert json.loads(result)['cpuNum'] == 6
    if handler_name == 'online_change_cpumem':
        assert events.mock_calls.index(call.hotplug_mem(4096)) < events.mock_calls.index(call.hotplug_cpu(6))
    assert events.mock_calls.index(call.hotplug_cpu(6)) < events.mock_calls.index(call.online(4, 6))


def test_cpu_memory_handler_skips_qga_when_cpu_count_does_not_increase():
    from tests.unit.kvmagent.test_vm_plugin_handlers import _make_req, _make_vm_plugin
    plugin = _make_vm_plugin()
    vm = MagicMock()
    vm.get_cpu_num.side_effect = [4, 4]
    vm.get_memory.return_value = 4096
    with patch.object(vm_plugin, 'get_vm_by_uuid', side_effect=[vm, vm]), \
            patch.object(vm, '_qga_online_hotplugged_cpus') as online:
        events = MagicMock()
        events.attach_mock(vm.hotplug_mem, 'hotplug_mem')
        events.attach_mock(vm.hotplug_cpu, 'hotplug_cpu')
        result = plugin.online_change_cpumem(_make_req(
            {'vmUuid': 'vm-uuid', 'cpuNum': 4, 'memorySize': 4096}))
    assert json.loads(result)['success'] is True
    assert json.loads(result)['cpuNum'] == 4
    assert events.mock_calls.index(call.hotplug_mem(4096)) < events.mock_calls.index(call.hotplug_cpu(4))
    online.assert_not_called()


@pytest.mark.parametrize('arch, guest_os, smbios, qga_state', [
    ('aarch64', 'ubuntu', False, None),
    ('x86_64', 'centos', False, vm_plugin.VmQga.QGA_STATE_RUNNING),
    ('x86_64', 'ubuntu', True, vm_plugin.VmQga.QGA_STATE_RUNNING),
    ('x86_64', 'ubuntu', False, 'stopped'),
])
def test_existing_arch_os_qga_and_smbios_guards_remain(arch, guest_os, smbios, qga_state):
    qga = _qga([_vcpus(range(6), offline=(4, 5))], [2])
    qga.os = guest_os
    qga.state = qga_state
    vm = _vm()
    vm._has_smbios_cpu_hotplug.return_value = smbios
    qga_factory = MagicMock(return_value=qga)
    qga_factory.QGA_STATE_RUNNING = vm_plugin.VmQga.QGA_STATE_RUNNING
    with patch.object(vm_plugin, 'HOST_ARCH', arch), \
            patch.object(vm_plugin, 'VmQga', qga_factory):
        vm._qga_online_hotplugged_cpus(4, 6)
    assert not any(c.args[0] == 'guest-get-vcpus' for c in qga.call_qga_command.call_args_list)

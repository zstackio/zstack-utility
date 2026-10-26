import json
import hashlib
import io
import os
import re
import subprocess
import time
from pathlib import Path

import pytest
from zstacklib.utils import linux

from kvmagent.plugins import memory_optimization as memory_optimization_module
from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin
from kvmagent.plugins.memory_writeback_backends import probe_writeback_backends as real_probe_writeback_backends
from kvmagent.plugins.memory_writeback_maintenance import build_backend_maintenance_request


HOST = 'host-capacity-reconcile'
OPERATION = 'capacity-only-reconcile'
LOGICAL_BYTES = 1024 * 1024 * 1024
PHYSICAL_BYTES = 512 * 1024 * 1024
OLD_LOGICAL_BYTES = 512 * 1024 * 1024
OLD_PHYSICAL_BYTES = 256 * 1024 * 1024


def test_cold_controller_identity_uses_python2_compatible_bounded_command(
        tmp_path, monkeypatch):
    """The deployed Python 2 subprocess/time APIs must still bound systemctl."""
    plugin = MemoryOptimizationPlugin()
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    identity = {
        'package': 'zstack-zram-5.5.38.19-1.el7.x86_64',
        'unitPath': '/usr/lib/systemd/system/zram-memory.service',
        'unitSha256': 'b' * 64, 'binarySha256': 'c' * 64,
        'pid': 4242, 'processStartTime': '123456', 'bootId': boot_id,
    }
    monkeypatch.setattr(plugin, '_first_use_runtime_identity',
                        lambda template, config: dict(identity))
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    monkeypatch.setattr(plugin, '_controller_process_start_time',
                        lambda pid: '123456')
    # Python 2.7 has neither subprocess.TimeoutExpired nor a timeout keyword
    # for check_output/Popen helpers. Model those exact missing stdlib pieces.
    monkeypatch.delattr(memory_optimization_module.subprocess, 'TimeoutExpired')
    monkeypatch.delattr(memory_optimization_module.time, 'monotonic')
    monkeypatch.setattr(linux, 'monotime', lambda: 1.0)

    def py2_check_output(argv, stderr=None):
        raise AssertionError('bounded controller checks must use Popen/poll')

    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output',
                        py2_check_output)
    outputs = [
        b'Id=zram-memory.service\n'
        b'FragmentPath=/usr/lib/systemd/system/zram-memory.service\n'
        b'DropInPaths=\nMainPID=4242\nActiveState=active\n'
        b'KillMode=process\nRestart=no\nExecStop=\n'
    ]

    class CompletedProcess(object):
        def __init__(self, argv, stdout=None, stderr=None):
            self.returncode = 0

        def poll(self):
            return self.returncode

        def communicate(self):
            return outputs.pop(0), None

    monkeypatch.setattr(memory_optimization_module.subprocess, 'Popen', CompletedProcess)
    actual = plugin._cold_controller_identity(b'template', b'config')
    assert actual is not None
    assert actual['unit'] == 'zram-memory.service'
    assert actual['killMode'] == 'process'
    assert actual['restart'] == 'no'


def test_bounded_command_timeout_uses_compatible_poll_clock(monkeypatch):
    plugin = MemoryOptimizationPlugin()
    monkeypatch.delattr(memory_optimization_module.subprocess, 'TimeoutExpired')
    monkeypatch.delattr(memory_optimization_module.time, 'monotonic')
    clock = [0.0]
    monkeypatch.setattr(linux, 'monotime', lambda: clock[0])
    monkeypatch.setattr(memory_optimization_module.time, 'sleep',
                        lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    processes = []

    class StuckProcess(object):
        def __init__(self, argv, stdout=None, stderr=None):
            self.returncode = None
            self.terminated = False
            self.killed = False
            processes.append(self)

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.killed = True
            self.returncode = -9

        def wait(self):
            return self.returncode

    monkeypatch.setattr(memory_optimization_module.subprocess, 'Popen', StuckProcess)
    with pytest.raises(RuntimeError, match='BOUNDED_COMMAND_TIMEOUT'):
        plugin._bounded_command_output(['systemctl', 'show'], 0.2)
    assert len(processes) == 1
    assert processes[0].terminated is True
    assert processes[0].killed is False


def test_bounded_command_preserves_check_output_failure_bytes(monkeypatch):
    output = b'..5....T. c /etc/zram-memory/config.json\n'

    class FailedProcess(object):
        def __init__(self, argv, stdout=None, stderr=None):
            self.returncode = 1

        def poll(self):
            return self.returncode

        def communicate(self):
            return output, None

    monkeypatch.setattr(memory_optimization_module.subprocess, 'Popen', FailedProcess)
    with pytest.raises(subprocess.CalledProcessError) as error:
        MemoryOptimizationPlugin._bounded_command_output(['rpm', '-V', 'zstack-zram'], 1)
    assert error.value.returncode == 1
    assert error.value.output == output


@pytest.mark.parametrize('capability_error', [False, True])
def test_state_capabilities_identify_agent_readonly_completed_reconcile(
        tmp_path, monkeypatch, capability_error):
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(plugin, '_operation_request', lambda command: command)
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    monkeypatch.setattr(plugin, '_dispatch', lambda action, command: {
        'success': True, 'status': 'Succeeded', 'state': {'host_zram': {}}})
    monkeypatch.setattr(plugin, '_promote_ksm_only_state',
                        lambda result, observer=False: result)
    monkeypatch.setattr(plugin, '_read_ksm_sysfs', lambda name: '0' if name == 'run' else '1')
    monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: '0')
    monkeypatch.setattr(plugin, '_read_native_ksm_config', lambda: {})
    monkeypatch.setattr(plugin, '_native_service_state', lambda unit, expected: 'inactive')
    monkeypatch.setattr(plugin, '_get_active_control', lambda: None)
    monkeypatch.setattr(plugin, '_complete_vm_inventory', lambda vms: (vms or {}, True))
    monkeypatch.setattr(plugin, '_maintenance_proof_for_state', lambda state: None)
    if capability_error:
        def unavailable_capabilities():
            raise RuntimeError('capability read unavailable')
        monkeypatch.setattr(plugin, 'discover_capabilities', unavailable_capabilities)
    else:
        monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
            'supported': True, 'ksm': True, 'zram': False})

    def service_call(action, payload):
        if action == 'tuning-state':
            return {'settings': {}}
        if action == 'capacity-state':
            return {}
        if action == 'backend-state':
            return {}
        if action == 'host-cpu-state':
            return {'efficiency_enabled': False}
        raise AssertionError('unexpected state enrichment read: %s' % action)

    plugin.service_call = service_call
    result = json.loads(plugin.state({'body': json.dumps({'hostUuid': HOST})}))
    if capability_error:
        assert 'readOnlyCompletedReconcile' not in result['capabilities']
        assert 'readOnlyCompletedReconcile' not in result['state']['capabilities']
    else:
        assert result['capabilities']['readOnlyCompletedReconcile'] is True
        assert result['state']['capabilities']['readOnlyCompletedReconcile'] is True


def test_state_preserves_native_pool_blocker_and_native_observation_time(
        tmp_path, monkeypatch):
    plugin = MemoryOptimizationPlugin()
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    assert boot_id
    plugin.configure({'hostUuid': HOST,
                      'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(plugin, '_read_ksm_sysfs', lambda name: '0' if name == 'run' else '1')
    monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: '0')
    monkeypatch.setattr(plugin, '_read_native_ksm_config', lambda: {})
    monkeypatch.setattr(plugin, '_native_service_state', lambda unit, expected: 'inactive')
    monkeypatch.setattr(plugin, '_get_active_control', lambda: None)
    monkeypatch.setattr(plugin, '_complete_vm_inventory', lambda vms: (vms or {}, True))
    monkeypatch.setattr(plugin, '_maintenance_proof_for_state', lambda state: None)
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'zram': True})

    native_observed_at = time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                       time.gmtime(time.time() - 60))
    blocker = 'NO_QUALIFIED_MANAGED_POOL: EXCLUSIVE_ZRAM_ROUTE_REQUIRED'
    snapshot = {
        '_http_status': 200,
        'mode': 'reclaim',
        'resource_authorized': True,
        'observed_at': native_observed_at,
        'host_zram': {
            'quality': 'unavailable',
            'pool_generation': '',
            'device': '',
            'reason': blocker,
            'observed_at': native_observed_at,
        },
        'backend_health': {
            'state': 'UNKNOWN',
            'reason': blocker,
            'new_io_permitted_by_backend_health': False,
            'backoff_until': '0001-01-01T00:00:00Z',
        },
    }
    calls = []

    def service_call(action, payload):
        calls.append(action)
        if action == 'state':
            return dict(snapshot)
        if action == 'tuning-state':
            return {'settings': {}}
        if action == 'capacity-state':
            return {'revision': 5}
        if action == 'backend-state':
            return {'backend_resource': None}
        if action == 'host-cpu-state':
            return {'efficiency_enabled': False}
        raise AssertionError('unexpected state enrichment read: %s' % action)

    plugin.service_call = service_call
    result = json.loads(plugin.state({'body': json.dumps({
        'hostUuid': HOST, 'operationUuid': 'state-observation-1'})}))

    assert result['success'] is True
    assert result['status'] == 'Succeeded'
    assert result['hostUuid'] == HOST
    assert result['bootId'] == boot_id
    assert result['sampleTime'] >= int(time.time() * 1000) - 5000
    assert result['state']['bootId'] == boot_id
    assert result['state']['observed_at'] == native_observed_at
    assert result['state']['host_zram']['reason'] == blocker
    assert result['state']['host_zram']['observed_at'] == native_observed_at
    assert result['state']['backend_health']['state'] == 'UNKNOWN'
    assert result['state']['backend_health']['reason'] == blocker
    assert result['state']['backend_health']['new_io_permitted_by_backend_health'] is False
    assert result['state']['backend_health']['backoff_until'] == '0001-01-01T00:00:00Z'
    assert calls.count('state') == 1
    assert {'tuning-state', 'capacity-state', 'backend-state', 'host-cpu-state'} <= set(calls)


def test_state_service_failure_does_not_become_successful_fresh_observation(
        tmp_path, monkeypatch):
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST,
                      'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(plugin, '_read_ksm_sysfs', lambda name: '0' if name == 'run' else '1')
    monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: '0')
    monkeypatch.setattr(plugin, '_read_native_ksm_config', lambda: {})
    monkeypatch.setattr(plugin, '_native_service_state', lambda unit, expected: 'inactive')
    monkeypatch.setattr(plugin, '_get_active_control', lambda: None)
    monkeypatch.setattr(plugin, '_complete_vm_inventory', lambda vms: (vms or {}, True))
    monkeypatch.setattr(plugin, '_maintenance_proof_for_state', lambda state: None)
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'zram': True})

    def service_call(action, payload):
        if action == 'state':
            return {'_http_status': 503, 'error': 'service unavailable'}
        if action == 'tuning-state':
            return {'settings': {}}
        if action == 'capacity-state':
            return {'revision': 5}
        if action == 'backend-state':
            return {'backend_resource': None}
        if action == 'host-cpu-state':
            return {'efficiency_enabled': False}
        raise AssertionError('unexpected state enrichment read: %s' % action)

    plugin.service_call = service_call
    result = json.loads(plugin.state({'body': json.dumps({
        'hostUuid': HOST, 'operationUuid': 'state-observation-failed'})}))

    assert result['success'] is False
    assert result['status'] == 'Unknown'
    assert result['hostUuid'] == HOST
    assert result['sampleTime'] > 0
    assert 'host_zram' not in result['state']

    calls = []
    original_service_call = plugin.service_call

    def recording_service_call(action, payload):
        calls.append(action)
        return original_service_call(action, payload)

    plugin.service_call = recording_service_call
    wrong_host_result = json.loads(plugin.state({'body': json.dumps({
        'hostUuid': 'other-host', 'operationUuid': 'state-observation-wrong-host'})}))
    assert wrong_host_result['success'] is False
    assert wrong_host_result['status'] == 'Unknown'
    assert 'state' not in calls


def test_first_use_rpm_verification_uses_bounded_output_and_preserves_rpm_v_semantics(
        monkeypatch):
    calls = []

    def bounded(command, timeout):
        calls.append((command, timeout))
        if command[:2] == ['rpm', '-V']:
            error = subprocess.CalledProcessError(1, command)
            error.output = b'..5....T. c /etc/zram-memory/config.json\n'
            raise error
        raise AssertionError('unexpected bounded command')

    monkeypatch.setattr(MemoryOptimizationPlugin, '_bounded_command_output',
                        staticmethod(bounded))
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output',
                        lambda *args, **kwargs: (_ for _ in ()).throw(
                            AssertionError('unbounded check_output is forbidden')))
    config = b'{"managed":true}\n'
    assert MemoryOptimizationPlugin._verify_first_use_rpm_files(config) == hashlib.sha256(
        config).hexdigest()
    assert calls == [(['rpm', '-V', 'zstack-zram'], 30)]

    def unexpected_drift(command, timeout):
        error = subprocess.CalledProcessError(1, command)
        error.output = (b'..5....T. c /etc/zram-memory/config.json\n'
                        b'..5....T. /usr/local/libexec/zram-efficiency\n')
        raise error

    monkeypatch.setattr(MemoryOptimizationPlugin, '_bounded_command_output',
                        staticmethod(unexpected_drift))
    with pytest.raises(RuntimeError, match='FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH'):
        MemoryOptimizationPlugin._verify_first_use_rpm_files(config)


def _configured(logical, physical):
    return {'logical_capacity': {'bytes': logical},
            'physical_memory_limit': {'bytes': physical}}


def _capacity_apply_fixture(tmp_path, zram=None, writeback=None, cpu_enabled=False,
                            capacity_requested=True, include_zram=True,
                            typed_quiescence_rejection=False, monkeypatch=None, native_writeback_enabled=False):
    """Use the real Agent apply/reconcile methods with a typed service boundary."""
    shared = {'revision': 4}
    configured = _configured(OLD_LOGICAL_BYTES, OLD_PHYSICAL_BYTES)
    desired = {'configured': configured, 'basis_host_memory_bytes': 8 * 1024 * 1024 * 1024,
               'logical_resolved_bytes': OLD_LOGICAL_BYTES,
               'physical_resolved_bytes': OLD_PHYSICAL_BYTES}
    service_state = {
        'capacity': {'_http_status': 200, 'revision': shared['revision'],
                     'desired': desired, 'effective_logical_bytes': OLD_LOGICAL_BYTES,
                     'effective_physical_limit_bytes': OLD_PHYSICAL_BYTES,
                     'apply_state': 'APPLIED', 'reason': 'NATIVE_CONFIGURATION_VERIFIED'},
        'cpu': {'_http_status': 200, 'revision': shared['revision'],
                'efficiency_enabled': cpu_enabled,
                'idle_cpu_threshold_percent': 5, 'idle_duration_seconds': 60},
        'tuning': {'_http_status': 200, 'revision': 9,
                   'settings': {'host_floor_bytes': 0, 'metadata_reserve_bytes': 0,
                                'transient_reserve_bytes': 0,
                                'writeback': {'enabled': native_writeback_enabled, 'batch_bytes': 8388608,
                                              'idle_observation_seconds': 10,
                                              'operation_interval_seconds': 5}}},
    }
    calls = []
    apply_attempts = [0]

    def service_call(action, payload):
        calls.append((action, payload))
        if action == 'capacity-state':
            return dict(service_state['capacity'])
        if action == 'host-cpu-state':
            return dict(service_state['cpu'])
        if action == 'tuning-state':
            return dict(service_state['tuning'])
        if action == 'operations':
            return {'_http_status': 200, 'cq': {'C': 0, 'Q': 0}, 'entries': []}
        if action == 'monitor-state':
            return {'_http_status': 200, 'pending_operations': [],
                    'lifecycle': {'paused': False, 'migrationHold': {}}}
        if action == 'capacity':
            shared['revision'] += 1
            # The service keeps a side sent without a unit as its default share.
            configured_now = {
                'logical_capacity': payload['logical_capacity'] or {'percent_of_host': 50},
                'physical_memory_limit': payload['physical_memory_limit'] or {'percent_of_logical': 50}}
            basis = 8 * 1024 * 1024 * 1024

            def resolve(side, denominator):
                if 'bytes' in side:
                    return side['bytes']
                return denominator * side.get('percent_of_host', side.get('percent_of_logical')) // 100 // 4096 * 4096
            logical_now = resolve(configured_now['logical_capacity'], basis)
            physical_side = configured_now['physical_memory_limit']
            physical_now = resolve(physical_side, logical_now if 'percent_of_logical' in physical_side else basis)
            desired_now = {'configured': configured_now,
                           'basis_host_memory_bytes': basis,
                           'logical_resolved_bytes': logical_now,
                           'physical_resolved_bytes': physical_now}
            service_state['capacity'] = {
                '_http_status': 200, 'revision': shared['revision'],
                'desired': desired_now, 'effective_logical_bytes': None,
                'effective_physical_limit_bytes': None,
                'apply_state': 'BLOCKED', 'reason': 'NATIVE_POOL_UNQUALIFIED'}
            service_state['cpu']['revision'] = shared['revision']
            return {'_http_status': 202, 'revision': shared['revision'],
                    'desired': desired_now, 'apply_state': 'BLOCKED',
                    'reason': 'NATIVE_POOL_UNQUALIFIED'}
        if action == 'host-cpu':
            for key, state_key in (
                    ('efficiency_enabled', 'efficiency_enabled'),
                    ('idle_cpu_threshold_percent', 'idle_cpu_threshold_percent'),
                    ('idle_duration_seconds', 'idle_duration_seconds')):
                if payload[key] != service_state['cpu'][state_key]:
                    service_state['cpu'][state_key] = payload[key]
                    shared['revision'] += 1
            service_state['cpu']['revision'] = shared['revision']
            service_state['capacity']['revision'] = shared['revision']
            return {'_http_status': 200, 'revision': shared['revision'],
                    'request_id': payload['request_id'],
                    'efficiency_enabled': payload['efficiency_enabled'],
                    'idle_cpu_threshold_percent': payload['idle_cpu_threshold_percent'],
                    'idle_duration_seconds': payload['idle_duration_seconds']}
        if action == 'apply':
            apply_attempts[0] += 1
            if typed_quiescence_rejection and apply_attempts[0] == 1:
                return {'_http_status': 409,
                        'error': 'TUNING_REQUIRES_QUIESCENT_EXECUTOR'}
            service_state['tuning'] = {
                '_http_status': 200, 'revision': payload['expected_revision'] + 1,
                'request_id': payload['request_id'], 'settings': payload['settings']}
            return dict(service_state['tuning'])
        raise AssertionError('unexpected service action: %s' % action)

    plugin = MemoryOptimizationPlugin(service_call=service_call)
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    if typed_quiescence_rejection:
        assert monkeypatch is not None
        monkeypatch.setattr(memory_optimization_module.linux, 'monotime', lambda: 0.0)
        monkeypatch.setattr(memory_optimization_module.time, 'sleep', lambda seconds: None)
    capacity_policy = ({'logicalCapacityBytes': LOGICAL_BYTES,
                        'ramLimitBytes': PHYSICAL_BYTES} if capacity_requested else {})
    policy = {}
    if include_zram:
        policy['zram'] = dict(capacity_policy, **(zram or {}))
    if writeback is not None:
        policy['writeback'] = writeback
    command = {'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
               'operationUuid': OPERATION, 'desiredRevision': 12, 'policy': policy}
    applied = plugin._normalize_response(
        plugin._apply_service_policy_fail_closed(command), 'apply', command)
    if applied['status'] == 'Succeeded':
        applied['appliedRevision'] = command['desiredRevision']
    assert plugin._record_operation(
        command, 'APPLIED' if applied['status'] == 'Succeeded' else 'UNKNOWN', applied)
    return plugin, service_state, calls, command, applied


def test_typed_quiescence_retry_preserves_disabled_history_receipt(tmp_path, monkeypatch):
    plugin, _, calls, _, applied = _capacity_apply_fixture(
        tmp_path, zram={'enabled': False}, capacity_requested=False,
        typed_quiescence_rejection=True, monkeypatch=monkeypatch)

    assert applied['status'] == 'Succeeded', applied
    assert len([payload for action, payload in calls if action == 'apply']) == 2
    record = _journal(plugin)
    assert plugin._first_use_terminal_service_disable(record)


def _ksm_only_blocked_capacity_fixture(tmp_path, monkeypatch):
    plugin, service_state, calls, _, _ = _capacity_apply_fixture(
        tmp_path, zram={'enabled': False}, capacity_requested=False)
    plugin.KSM_CONF = str(tmp_path / 'ksmtuned.conf')
    plugin.KSM_LOCK = str(tmp_path / 'ksmtuned.lock')
    plugin.socket_path = str(tmp_path / 'memory-service.sock')
    Path(plugin.socket_path).touch()
    native_files = []
    for name in ('ksmtuned', 'ksmctl', 'ksm.service', 'ksmtuned.service'):
        profile_path = tmp_path / name
        profile_path.write_text('test-native-profile-' + name)
        native_files.append(str(profile_path))
    plugin.NATIVE_KSM_FILES = tuple(native_files)
    native = {'run': '1', 'pages_to_scan': '2000', 'sleep_millisecs': '20',
              'use_zero_pages': '0'}
    Path(plugin.KSM_CONF).write_text(memory_optimization_module.render_config(
        '', 11, 2000, plugin._native_sleep_for_policy(20)))
    native_commands = []

    def read_native_ack():
        config = plugin._read_native_ksm_config() or {}
        observed = dict(native)
        observed['configRevision'] = str(config.get('CONFIG_REVISION', ''))
        return observed

    monkeypatch.setattr(plugin, '_read_ksm_ack', read_native_ack)
    monkeypatch.setattr(plugin, '_native_service_state',
                        lambda unit, operation: 'active' if operation == 'active' else 'enabled')
    monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: native['use_zero_pages'])
    monkeypatch.setattr(plugin, '_write_ksm_sysfs',
                        lambda field, value: native.__setitem__(field, value))
    monkeypatch.setattr(plugin, '_read_ksm_sysfs', lambda field: native[field])
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'ksmZeroPages': True,
        'zram': False, 'writeback': False})
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_call',
                        lambda argv: native_commands.append(tuple(argv)))
    prior_command = {'hostUuid': HOST, 'scope': 'Host', 'resourceUuid': HOST,
                     'action': 'apply', 'operationUuid': 'a' * 32,
                     'expectedRevision': 11, 'desiredRevision': 12,
                     'policyMode': 'effective',
                     'policy': {'schemaVersion': 1,
                                'ksm': {'pagesToScan': 2000, 'sleepMillis': 20},
                                'zram': {'enabled': False},
                                'writeback': {'enabled': False}}}
    prior_result = plugin.apply(prior_command)
    assert prior_result['status'] == 'Succeeded', prior_result
    prior = plugin._load_operation(prior_command)
    prior_state = prior['readback']['state']
    prior_sections = prior_state.get('sections', prior_state)
    assert prior['stage'] == 'APPLIED'
    assert prior['requestHash'] == plugin._operation_hash(prior_command)
    assert prior['policyHash'] == plugin._policy_digest(prior_command['policy'])
    assert 'enabled' not in prior['policy']['ksm']
    assert 'zeroPagesEnabled' not in prior['policy']['ksm']
    assert 'capacity' not in prior_sections
    assert isinstance(prior_sections.get('cpu'), dict)
    assert isinstance(prior_sections.get('tuning'), dict)
    ack = prior['readback']['ksmReadback']
    assert ack == {'run': '1', 'configRevision': '12', 'pages_to_scan': '2000',
                   'sleep_millisecs': '20', 'use_zero_pages': '0'}
    assert plugin._get_active_control() == prior_command['operationUuid']
    service_state['capacity'].update({
        '_http_status': 200,
        'desired': {'configured': {
            'logical_capacity': {'percent_of_host': 50},
            'physical_memory_limit': {'percent_of_logical': 50}},
            'basis_host_memory_bytes': 540129357824,
            'logical_resolved_bytes': 270064676864,
            'physical_resolved_bytes': 135032336384},
        'effective_logical_bytes': None,
        'effective_physical_limit_bytes': None,
        'apply_state': 'BLOCKED', 'reason': 'NATIVE_POOL_UNQUALIFIED'})
    command = {'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
               'resourceUuid': HOST, 'operationUuid': 'b' * 32,
               'expectedRevision': prior_command['desiredRevision'],
               'desiredRevision': prior_command['desiredRevision'] + 1,
               'policyMode': 'effective',
               'licensePermit': {'managed': True, 'operationUuid': 'ksm-only-permit',
                                 'expiresAt': int(time.time() * 1000) + 35000,
                                 'validForSeconds': 30},
               'policy': {'schemaVersion': 1, 'ksm': {}}}

    def record_legacy_unknown():
        prior_record = plugin._load_operation(prior_command)
        state = prior_record['readback']['state']
        sections = state.get('sections', state)
        prior_sections = {key: sections[key] for key in ('capacity', 'cpu', 'tuning')
                          if key in sections}
        preflight = {}
        for action, section in (('capacity-state', 'capacity'),
                                ('host-cpu-state', 'cpu'),
                                ('tuning-state', 'tuning')):
            response = plugin.service_call(action, {})
            assert response.get('_http_status') == 200
            assert isinstance(response.get('revision'), int)
            assert not isinstance(response.get('revision'), bool)
            preflight[section] = dict(response)
        assert preflight['capacity']['reason'] == 'NATIVE_POOL_UNQUALIFIED'
        assert preflight['capacity']['desired']
        assert preflight['capacity']['effective_logical_bytes'] is None
        assert preflight['capacity']['effective_physical_limit_bytes'] is None
        assert preflight['cpu']['efficiency_enabled'] is False
        assert preflight['tuning']['settings']['writeback']['enabled'] is False
        mixed = {'operationUuid': command['operationUuid'],
                 'priorOperationUuid': prior_command['operationUuid'],
                 'priorPolicy': dict(prior_record['policy']),
                 'priorState': prior_sections,
                 'preflight': preflight, 'writes': {}, 'writeAttempts': {},
                 'postflight': {}, 'ksmReadback': None,
                 'priorKsmAck': dict(prior_record['readback']['ksmReadback'])}
        evidence = {'success': False, 'status': 'Unknown', 'reason':
                    'MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN',
                    'reasonCode': 'MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN',
                    'operationUuid': command['operationUuid'],
                    'state': {'phase': 'UNKNOWN', 'mixedClearEvidence': mixed}}
        assert evidence['state']['mixedClearEvidence']['priorState'] == prior_sections
        assert not any(key in command for key in ('firstZramUse', 'activationIntent',
                                                   'maintenanceProof'))
        submitted = int(time.time() * 1000) - 10
        assert plugin._record_operation(command, 'UNKNOWN', evidence)
        failed = plugin._load_operation(command)
        assert failed['applyEvidence'] == failed['readback'] == evidence
        assert failed['stage'] == 'UNKNOWN'
        assert 'appliedRevision' not in failed['readback']
        assert plugin._get_active_control() == prior_command['operationUuid']
        return failed, submitted

    return (plugin, service_state, calls, prior_command, ack, native,
            native_commands, command, record_legacy_unknown)


@pytest.mark.parametrize('target', ['pure_ksm_clear', 'retained_ksm_blocked', 'retained_ksm_qualified', 'retained_ksm_missing_sections',
                                    'retained_ksm_missing_state', 'retained_ksm_empty_sections'])
def test_ksm_only_clear_ignores_unqualified_capacity_without_writes(tmp_path, monkeypatch, target):
    """A KSM-only clear is independent of an unrelated capacity block."""
    plugin, service_state, calls, _, ack, native, native_commands, command, _ = \
        _ksm_only_blocked_capacity_fixture(
        tmp_path, monkeypatch)
    if target != 'pure_ksm_clear':
        command['policy']['ksm'] = {'pagesToScan': 2000, 'sleepMillis': 20}
    if target == 'retained_ksm_qualified':
        service_state['capacity'].update(
            apply_state='APPLIED', reason='NATIVE_CONFIGURATION_VERIFIED',
            effective_logical_bytes=OLD_LOGICAL_BYTES,
            effective_physical_limit_bytes=OLD_PHYSICAL_BYTES)
    before_calls = len(calls)
    before_native = dict(native)
    before_native_commands = list(native_commands)
    prior_control = plugin._get_active_control()
    if target in ('retained_ksm_missing_sections', 'retained_ksm_missing_state',
                  'retained_ksm_empty_sections'):
        prior = plugin._load_operation({'operationUuid': prior_control})
        if target == 'retained_ksm_missing_state':
            prior['readback'].pop('state')
        elif target == 'retained_ksm_empty_sections':
            prior['readback']['state']['sections'] = {}
        else:
            prior['readback']['state'].pop('sections')
        prior['applyEvidence'] = json.loads(json.dumps(prior['readback']))
        with open(plugin._operation_path(prior_control), 'w') as stream:
            json.dump(prior, stream, sort_keys=True)
    result = plugin.apply(command)
    if target in ('retained_ksm_blocked', 'retained_ksm_missing_sections',
                  'retained_ksm_missing_state', 'retained_ksm_empty_sections'):
        assert result['status'] == 'Unknown', result
        assert result['reasonCode'] == ('MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN'
                                        if target == 'retained_ksm_blocked' else
                                        'MIXED_CLEAR_PRIOR_SERVICE_JOURNAL_INVALID')
        assert plugin._get_active_control() == prior_control
        assert native == before_native
        assert native_commands == before_native_commands
        assert not [action for action, _ in calls[before_calls:]
                    if action in ('capacity', 'host-cpu', 'apply')]
        return
    # Desired contract: a schema-1 KSM-only clear is independent of an
    # unrelated blocked capacity state and must not enter Go service writes.
    assert result['status'] == 'Succeeded', result
    writes = [action for action, _ in calls[before_calls:]
              if action in ('capacity', 'host-cpu', 'apply')]
    if target == 'pure_ksm_clear':
        assert writes == []
    else:
        assert result['state'].get('ksmOnly') is not True
        assert result['state']['mixedClearEvidence']['complete'] is True
    record = plugin._load_operation(command)
    assert record['stage'] == 'APPLIED'
    assert record['desiredRevision'] == command['desiredRevision']
    assert record['readback']['ksmReadback']['configRevision'] == '13'
    for field in ('run', 'pages_to_scan', 'sleep_millisecs', 'use_zero_pages'):
        assert record['readback']['ksmReadback'][field] == ack[field]
    assert plugin._get_active_control() == command['operationUuid']
    assert native['run'] == before_native['run']
    assert native['pages_to_scan'] == before_native['pages_to_scan']
    assert native['sleep_millisecs'] == before_native['sleep_millisecs']
    assert native['use_zero_pages'] == before_native['use_zero_pages']
    assert plugin._read_ksm_ack()['configRevision'] == '13'
    assert plugin._get_active_control() != prior_control
    assert native_commands[len(before_native_commands):] == [
        ('systemctl', 'restart', plugin.KSM_TUNED_UNIT)]


def test_mixed_capacity_unknown_reconcile_seals_prewrite_without_losing_evidence(
        tmp_path, monkeypatch):
    """A pre-write mixed-clear rejection must be safely sealed as NOT_ISSUED."""
    plugin, _, calls, prior_command, ack, native, native_commands, command, \
        record_legacy_unknown = \
        _ksm_only_blocked_capacity_fixture(tmp_path, monkeypatch)
    operation = command['operationUuid']
    boot_id = plugin._current_boot_id()
    failed, submitted = record_legacy_unknown()
    readback = json.loads(json.dumps(failed['readback']))
    mixed = readback['state']['mixedClearEvidence']
    assert mixed['operationUuid'] == operation
    assert mixed['priorOperationUuid'] == prior_command['operationUuid']
    assert mixed['priorKsmAck'] == ack
    assert mixed['writes'] == mixed['writeAttempts'] == mixed['postflight'] == {}
    assert mixed['ksmReadback'] is None
    before_native = dict(native)
    before_native_commands = list(native_commands)
    before_calls = len(calls)
    prior_record = plugin._load_operation(prior_command)
    prior_path = plugin._operation_path(prior_command['operationUuid'])
    with open(prior_path, 'rb') as stream:
        prior_bytes = stream.read()
    expected_apply_evidence = json.loads(json.dumps(failed['applyEvidence']))
    expected_policy_hash = failed['policyHash']
    expected_request_hash = failed['requestHash']
    with open(plugin._operation_path(operation), 'rb') as stream:
        original_bytes = stream.read()
    query = {'action': 'reconcile', 'scope': 'Host', 'hostUuid': HOST,
             'resourceUuid': HOST, 'operationUuid': operation,
             'desiredRevision': command['desiredRevision'], 'bootId': boot_id,
             'policy': {}, 'taskSubmittedAt': submitted,
             'expectedControlOperationUuid': operation,
             'reconcileAction': 'seal-if-never-issued'}
    sealed = json.loads(plugin.reconcile({'body': json.dumps(query)}))
    assert sealed['status'] == 'Failed', sealed
    assert sealed['reasonCode'] == 'KSM_CLEAR_NOT_ISSUED', sealed
    assert sealed['state']['policyWritesIssued'] is False
    stored = plugin._load_operation(command)
    assert stored['stage'] == 'NOT_ISSUED'
    assert stored['applyEvidence'] == failed['applyEvidence']
    assert sealed['state']['controlOperationUuid'] == prior_command['operationUuid']
    assert stored['readback'] == dict(sealed, state={
        k: v for k, v in sealed['state'].items() if k != 'controlOperationUuid'})
    assert plugin._get_active_control() == prior_command['operationUuid']
    assert stored['policyHash'] == expected_policy_hash
    assert stored['requestHash'] == expected_request_hash
    assert stored['applyEvidence'] == expected_apply_evidence
    assert native == before_native
    assert native_commands == before_native_commands
    assert not any(action in ('capacity', 'host-cpu', 'apply')
                   for action, _ in calls[before_calls:])
    assert plugin._load_operation(prior_command) == prior_record
    assert json.loads(plugin.reconcile({'body': json.dumps(query)})) == sealed
    with open(prior_path, 'rb') as stream:
        assert stream.read() == prior_bytes
    with open(plugin._operation_path(operation), 'rb') as stream:
        assert stream.read() != original_bytes


@pytest.mark.parametrize('tamper', [
    'missing_proof', 'write_evidence', 'write_attempts', 'postflight',
    'ksm_readback', 'prior_ack', 'wrong_boot', 'wrong_revision',
    'wrong_control', 'active_control', 'prior_policy', 'prior_revision',
    'cpu_drift', 'tuning_drift',
])
def test_mixed_capacity_unknown_reconcile_rejects_unproven_checkpoint(
        tmp_path, monkeypatch, tamper):
    """Mixed-clear NOT_ISSUED requires the complete original read-only proof."""
    plugin, service_state, calls, prior_command, _, native, native_commands, command, record_legacy_unknown = \
        _ksm_only_blocked_capacity_fixture(tmp_path, monkeypatch)
    failed, submitted = record_legacy_unknown()
    drifted = json.loads(json.dumps(failed['readback']))
    mixed = drifted['state']['mixedClearEvidence']
    prior_record = plugin._load_operation(prior_command)
    if tamper == 'missing_proof':
        drifted['state'].pop('mixedClearEvidence')
    elif tamper == 'write_evidence':
        mixed['writes'] = {'capacity': {'attempted': True}}
    elif tamper == 'write_attempts':
        mixed['writeAttempts'] = {'apply': {'started': True}}
    elif tamper == 'postflight':
        mixed['postflight'] = {'capacity': {'_http_status': 200}}
    elif tamper == 'ksm_readback':
        mixed['ksmReadback'] = dict(mixed['priorKsmAck'])
    elif tamper == 'prior_ack':
        mixed['priorKsmAck']['configRevision'] = '11'
    elif tamper == 'wrong_boot':
        failed['bootId'] = '0' * 36
    elif tamper == 'wrong_revision':
        failed['desiredRevision'] += 1
    elif tamper == 'wrong_control':
        pass
    elif tamper == 'active_control':
        plugin._set_active_control('c' * 32)
    elif tamper == 'prior_policy':
        prior_record['policy']['ksm']['pagesToScan'] = 1000
        assert plugin._write_operation_record(prior_record)
    elif tamper == 'prior_revision':
        prior_record['desiredRevision'] += 1
        assert plugin._write_operation_record(prior_record)
    elif tamper == 'cpu_drift':
        service_state['cpu']['efficiency_enabled'] = True
    elif tamper == 'tuning_drift':
        service_state['tuning']['settings']['writeback']['enabled'] = True
    if drifted != failed['readback']:
        failed['readback'] = drifted
        failed['applyEvidence'] = drifted
    if tamper in ('missing_proof', 'write_evidence', 'write_attempts', 'postflight',
                  'ksm_readback', 'prior_ack', 'wrong_boot', 'wrong_revision'):
        assert plugin._write_operation_record(failed)
    target_path = plugin._operation_path(command['operationUuid'])
    with open(target_path, 'rb') as stream:
        target_bytes = stream.read()
    before_native = dict(native)
    before_native_commands = list(native_commands)
    before_calls = len(calls)
    query = {'action': 'reconcile', 'scope': 'Host', 'hostUuid': HOST,
             'resourceUuid': HOST, 'operationUuid': command['operationUuid'],
             'desiredRevision': command['desiredRevision'],
             'bootId': plugin._current_boot_id(), 'policy': {},
             'taskSubmittedAt': submitted,
             'expectedControlOperationUuid': ('c' * 32 if tamper == 'wrong_control'
                                              else command['operationUuid']),
             'reconcileAction': 'seal-if-never-issued'}
    observed = json.loads(plugin.reconcile({'body': json.dumps(query)}))
    assert observed['status'] == 'Unknown', observed
    assert plugin._load_operation(command)['stage'] == 'UNKNOWN'
    assert plugin._load_operation(command)['readback'] == failed['readback']
    with open(target_path, 'rb') as stream:
        assert stream.read() == target_bytes
    assert native == before_native
    assert native_commands == before_native_commands
    assert not any(action in ('capacity', 'host-cpu', 'apply')
                   for action, _ in calls[before_calls:])


@pytest.mark.parametrize('scenario', ['quiet_retry', 'unmanaged_writeback', 'mixed_unmanaged_writeback', 'deadline', 'nonbusy_409', 'transport_loss'])
def test_tuning_quiescence_retries_exact_prewrite_rejection_before_cpu_restore(
        tmp_path, monkeypatch, scenario):
    """Only the exact typed pre-write rejection may retry, within a bounded quiet window."""
    cpu = {'_http_status': 200, 'revision': 27, 'efficiency_enabled': True,
           'idle_cpu_threshold_percent': 5, 'idle_duration_seconds': 60}
    settings = {'vm_management': {'mode': 'all_running', 'vm_uuids': []},
                'writeback': {'enabled': True}}
    tuning = {'_http_status': 200, 'revision': 13, 'settings': settings}
    apply_calls = []
    cpu_writes = []
    events = []
    poll_count = [0]
    clock = [0.0]

    def service_call(action, payload):
        events.append(action)
        if action == 'host-cpu-state':
            return dict(cpu)
        if action == 'tuning-state':
            return dict(tuning)
        if action == 'operations':
            poll_count[0] += 1
            busy = scenario == 'deadline' or poll_count[0] == 1
            return {'_http_status': 200, 'cq': {'C': 1 if busy else 0, 'Q': 0}}
        if action == 'monitor-state':
            return {'_http_status': 200,
                    'pending_operations': (['executor'] if
                                           scenario == 'deadline' or poll_count[0] == 1 else []),
                    'lifecycle': {'paused': False, 'migrationHold': {}}}
        if action == 'host-cpu':
            cpu_writes.append({key: payload[key] for key in (
                'expected_revision', 'efficiency_enabled',
                'idle_cpu_threshold_percent', 'idle_duration_seconds')})
            cpu.update(revision=payload['expected_revision'] + 1,
                       efficiency_enabled=payload['efficiency_enabled'],
                       idle_cpu_threshold_percent=payload['idle_cpu_threshold_percent'],
                       idle_duration_seconds=payload['idle_duration_seconds'])
            return dict(cpu, request_id=payload['request_id'])
        if action == 'apply':
            apply_calls.append(dict(payload))
            if scenario == 'transport_loss':
                raise IOError('transport lost after request')
            if scenario == 'nonbusy_409':
                return {'_http_status': 409, 'error': 'REVISION_CONFLICT'}
            if scenario == 'deadline' or (len(apply_calls) == 1 and scenario != 'mixed_unmanaged_writeback'):
                return {'_http_status': 409,
                        'error': 'TUNING_REQUIRES_QUIESCENT_EXECUTOR'}
            tuning.update(revision=tuning['revision'] + 1,
                          settings=payload['settings'])
            return dict(tuning)
        raise AssertionError('unexpected service action: %s' % action)

    plugin = MemoryOptimizationPlugin(service_call=service_call)
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    command = {'hostUuid': HOST, 'resourceUuid': HOST, 'scope': 'Host',
               'action': 'apply', 'operationUuid': 'a' * 32,
               'desiredRevision': 34,
               'communication': {'communicationSeconds': 0.25 if scenario == 'deadline' else 2},
               'policy': {'ksm': {'enabled': True, 'zeroPagesEnabled': True},
                          'zram': {'enabled': True},
                          'writeback': {'enabled': False}}}
    if scenario in ('unmanaged_writeback', 'mixed_unmanaged_writeback'):
        command['policy']['zram']['enabled'] = False
        command['policy'].pop('writeback')
    monkeypatch.setattr(memory_optimization_module.linux, 'monotime',
                        lambda: clock[0])
    monkeypatch.setattr(memory_optimization_module.time, 'sleep',
                        lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    result = (plugin._apply_service_policy(command, receipt_sink={})
              if scenario == 'mixed_unmanaged_writeback' else
              plugin._apply_service_policy_fail_closed(command))
    if scenario == 'mixed_unmanaged_writeback':
        assert result['status'] == 'Succeeded', result
        assert len(apply_calls) == 1
        assert apply_calls[0]['settings']['writeback']['enabled'] is True
        assert [item['efficiency_enabled'] for item in cpu_writes] == [True]
        assert cpu['efficiency_enabled'] is True
        return

    if scenario in ('quiet_retry', 'unmanaged_writeback'):
        assert result['status'] == 'Succeeded', result
        assert len(apply_calls) == 2
        assert apply_calls[0]['request_id'] == apply_calls[1]['request_id']
        assert apply_calls[0]['settings'] == apply_calls[1]['settings']
        assert apply_calls[0]['settings']['writeback']['enabled'] is (scenario == 'unmanaged_writeback')
        assert [item['efficiency_enabled'] for item in cpu_writes] == [False, True]
        assert cpu['efficiency_enabled'] is True
        assert poll_count[0] >= 2
        assert events.index('host-cpu') < events.index('apply')
        assert events.index('apply') < max(i for i, action in enumerate(events)
                                           if action == 'host-cpu')
    else:
        assert result['status'] == 'Unknown', result
        assert len(apply_calls) == 1
        assert len(cpu_writes) == 1 and cpu_writes[0]['efficiency_enabled'] is False
        assert cpu['efficiency_enabled'] is False
        assert 'host-cpu' not in events[events.index('apply') + 1:]
        if scenario == 'deadline':
            assert result['reasonCode'] == 'SERVICE_TUNING_QUIESCENCE_DEADLINE_EXCEEDED'
            assert poll_count[0] > 0
        else:
            assert 'operations' not in events
            assert 'monitor-state' not in events


def test_tuning_quiescence_does_not_retry_vm_shard_apply(tmp_path, monkeypatch):
    """A 409 after an apply with VM shards must not replay its side effects."""
    cpu = {'_http_status': 200, 'revision': 8, 'efficiency_enabled': False,
           'idle_cpu_threshold_percent': 5, 'idle_duration_seconds': 60}
    settings = {'vm_management': {'mode': 'all_running', 'vm_uuids': []},
                'writeback': {'enabled': False}}
    tuning = {'_http_status': 200, 'revision': 3, 'settings': settings}
    apply_calls = []
    events = []

    def service_call(action, payload):
        events.append(action)
        if action == 'host-cpu-state':
            return dict(cpu)
        if action == 'tuning-state':
            return dict(tuning)
        if action == 'apply':
            apply_calls.append(dict(payload))
            # The real local apply transport stages VM shards before its
            # tuning PUT; treat this response as the later typed rejection.
            return {'_http_status': 409,
                    'error': 'TUNING_REQUIRES_QUIESCENT_EXECUTOR'}
        raise AssertionError('unexpected service action: %s' % action)

    plugin = MemoryOptimizationPlugin(service_call=service_call)
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(memory_optimization_module.linux, 'monotime', lambda: 0.0)
    command = {'hostUuid': HOST, 'resourceUuid': HOST, 'scope': 'Host',
               'action': 'apply', 'operationUuid': 'c' * 32,
               'desiredRevision': 35,
               'targetSnapshotGeneration': 'b' * 32,
               'policy': {'zram': {'enabled': True, 'selectionMode': 'list',
                                   'selectedVmUuids': ['d' * 32]}}}

    result = plugin._apply_service_policy_fail_closed(command)

    assert result['status'] == 'Unknown'
    assert len(apply_calls) == 1, result
    assert 'operations' not in events
    assert 'monitor-state' not in events


def _reconcile(plugin):
    return json.loads(plugin.reconcile({'body': json.dumps({
        'hostUuid': HOST, 'operationUuid': OPERATION})}))


def _ksm_capacity_reconcile_fixture(tmp_path, monkeypatch, ksm_only=False,
                                   include_policy_mode=True):
    plugin = MemoryOptimizationPlugin()
    operation_uuid = 'e' * 32
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    ack = {'run': '1', 'configRevision': '159', 'pages_to_scan': '2000',
           'sleep_millisecs': '20', 'use_zero_pages': '1'}
    monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: dict(ack))
    policy = {'schemaVersion': 1,
              'ksm': {'enabled': True, 'pagesToScan': 2000,
                      'sleepMillis': 20, 'zeroPagesEnabled': True}}
    if not ksm_only:
        policy['zram'] = {'enabled': True}
    command = {'hostUuid': HOST, 'scope': 'Host', 'resourceUuid': HOST,
               'action': 'apply', 'operationUuid': operation_uuid,
               'desiredRevision': 159, 'policy': policy}
    if include_policy_mode:
        command['policyMode'] = 'effective'
    initial = {'success': False, 'status': 'Blocked',
               'reasonCode': 'NATIVE_POOL_UNQUALIFIED',
               'operationUuid': operation_uuid,
               'state': {'phase': 'BLOCKED', 'knownBlocked': True},
               'ksmReadback': dict(ack)}
    assert plugin._record_operation(command, 'BLOCKED', initial)
    latest = {'success': False, 'status': 'Blocked',
              'reasonCode': 'NATIVE_POOL_UNQUALIFIED',
              'operationUuid': operation_uuid,
              'state': {'phase': 'BLOCKED', 'knownBlocked': True}}
    assert plugin._update_operation_record(operation_uuid, 'BLOCKED', latest)
    service_state = {'complete': False, 'phase': 'BLOCKED'}
    monkeypatch.setattr(plugin, '_read_policy_state',
                        lambda _command, _policy: dict(service_state))

    def forbidden(*args, **kwargs):
        raise AssertionError('reconcile must not replay a policy write')

    monkeypatch.setattr(plugin, '_apply_ksm_policy', forbidden)
    monkeypatch.setattr(plugin, '_apply_service_policy', forbidden)
    monkeypatch.setattr(plugin, '_write_ksm_sysfs', forbidden)
    return plugin, command, ack, service_state, boot_id


def _ksm_reconcile_request(command, boot_id, **kwargs):
    request = {'action': 'reconcile', 'scope': 'Host', 'hostUuid': HOST,
               'resourceUuid': HOST, 'operationUuid': command['operationUuid'],
               'desiredRevision': command['desiredRevision'], 'bootId': boot_id,
               'policy': {}}
    request.update(kwargs)
    return {'body': json.dumps(request)}


def test_capacity_unknown_reconcile_reuses_original_ksm_proof_without_replay(
        tmp_path, monkeypatch):
    plugin, command, ack, service_state, boot_id = _ksm_capacity_reconcile_fixture(
        tmp_path, monkeypatch)
    original_evidence = plugin._load_operation(command)['applyEvidence']

    first = json.loads(plugin.reconcile(_ksm_reconcile_request(command, boot_id)))

    assert first['status'] == 'Unknown', first
    assert first['reasonCode'] in ('RECONCILE_TARGET_NOT_VERIFIED',
                                   'RECONCILE_READBACK_FAILED')
    assert first.get('ksmReadback') == ack, first
    record = plugin._load_operation(command)
    assert record['stage'] == 'UNKNOWN'
    assert record['applyEvidence'] == original_evidence
    assert record['readback']['ksmReadback'] == ack

    service_state.update(complete=True, phase='POOL_READY',
                         nativeReadback={'logical_capacity_bytes': LOGICAL_BYTES})
    second = json.loads(plugin.reconcile(_ksm_reconcile_request(command, boot_id)))
    assert second['status'] == 'Succeeded', second
    assert second['ksmReadback'] == ack
    assert plugin._load_operation(command)['readback']['ksmReadback'] == ack

    repeated = json.loads(plugin.reconcile(_ksm_reconcile_request(command, boot_id)))
    assert repeated == second
    completed = json.loads(plugin.reconcile(_ksm_reconcile_request(
        command, boot_id, expectedControlOperationUuid=command['operationUuid'],
        reconcileAction='verify-completed')))
    assert completed['status'] == 'Succeeded', completed
    assert completed['ksmReadback'] == ack
    assert plugin._load_operation(command)['applyEvidence'] == original_evidence


@pytest.mark.parametrize('tamper', [
    'missing_original', 'malformed_original', 'stale_original', 'native_drift',
    'malformed_latest', 'conflicting_latest',
])
def test_capacity_unknown_reconcile_rejects_unproven_ksm_ack_without_writes(
        tmp_path, monkeypatch, tamper):
    plugin, command, ack, _, boot_id = _ksm_capacity_reconcile_fixture(tmp_path, monkeypatch)
    record = plugin._load_operation(command)
    if tamper == 'missing_original':
        record['applyEvidence'].pop('ksmReadback')
    elif tamper == 'malformed_original':
        record['applyEvidence']['ksmReadback'].pop('pages_to_scan')
    elif tamper == 'stale_original':
        record['applyEvidence']['ksmReadback']['configRevision'] = '158'
    elif tamper == 'native_drift':
        monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: dict(ack, run='0'))
    elif tamper == 'malformed_latest':
        record['readback']['ksmReadback'] = {'configRevision': '159'}
    elif tamper == 'conflicting_latest':
        record['readback']['ksmReadback'] = dict(ack, pages_to_scan='2001')
    assert plugin._write_operation_record(record)

    result = json.loads(plugin.reconcile(_ksm_reconcile_request(command, boot_id)))

    assert result['status'] == 'Unknown', result
    assert result.get('reason') == 'RECONCILE_KSM_NOT_VERIFIED' or \
        result['reasonCode'] == 'RECONCILE_KSM_NOT_VERIFIED'
    assert plugin._load_operation(command)['stage'] == 'UNKNOWN'


@pytest.mark.parametrize(('ksm_only', 'include_policy_mode'), [
    (True, True), (False, False),
])
def test_ksm_proof_fallback_supports_ksm_only_and_legacy_journals(
        tmp_path, monkeypatch, ksm_only, include_policy_mode):
    plugin, command, ack, service_state, boot_id = _ksm_capacity_reconcile_fixture(
        tmp_path, monkeypatch, ksm_only=ksm_only,
        include_policy_mode=include_policy_mode)
    record = plugin._load_operation(command)
    if not include_policy_mode:
        # Older valid journal records can predate the persisted policyMode field.
        record.pop('policyMode', None)
        assert plugin._write_operation_record(record)
    original_evidence = plugin._load_operation(command)['applyEvidence']
    if ksm_only:
        def unexpected_service_read(*args, **kwargs):
            raise AssertionError('KSM-only reconcile must not require the ZRAM service')
        monkeypatch.setattr(plugin, '_read_policy_state', unexpected_service_read)
    else:
        service_state.update(complete=True, phase='READBACK')

    first = json.loads(plugin.reconcile(_ksm_reconcile_request(command, boot_id)))
    assert first['status'] == 'Succeeded', first
    assert first['ksmReadback'] == ack
    assert plugin._load_operation(command)['applyEvidence'] == original_evidence

    repeated = json.loads(plugin.reconcile(_ksm_reconcile_request(command, boot_id)))
    assert repeated == first

    reloaded = MemoryOptimizationPlugin()
    reloaded.configure({'hostUuid': HOST,
                        'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(reloaded, '_load_host_uuid', lambda: HOST)
    monkeypatch.setattr(reloaded, '_read_ksm_ack', lambda: dict(ack))
    def forbidden_replay(*args, **kwargs):
        raise AssertionError('reconcile must not replay a KSM or service policy write')
    monkeypatch.setattr(reloaded, '_apply_ksm_policy', forbidden_replay)
    monkeypatch.setattr(reloaded, '_write_ksm_sysfs', forbidden_replay)
    monkeypatch.setattr(reloaded, '_apply_service_policy', forbidden_replay)
    if ksm_only:
        monkeypatch.setattr(reloaded, '_read_policy_state', unexpected_service_read)
    else:
        monkeypatch.setattr(reloaded, '_read_policy_state',
                            lambda _command, _policy: dict(service_state))
    after_reload = json.loads(reloaded.reconcile(
        _ksm_reconcile_request(command, boot_id)))
    assert after_reload == first
    stored = reloaded._load_operation(command)
    assert stored['applyEvidence'] == original_evidence
    assert stored['readback']['ksmReadback'] == ack


def _journal(plugin):
    with open(plugin._operation_path(OPERATION), 'r') as stream:
        return json.load(stream)


def _write_journal(plugin, record):
    with open(plugin._operation_path(OPERATION), 'w') as stream:
        json.dump(record, stream, sort_keys=True)


@pytest.mark.parametrize(('original_scope', 'original_resource', 'tamper'), [
    ('Host', HOST, None),
    ('Global', 'global', None),
    ('Cluster', 'c' * 32, None),
    ('Global', 'global', 'scope_mismatch'),
    ('Cluster', 'c' * 32, 'scope_mismatch'),
    ('Global', 'global', 'resource_mismatch'),
    ('Cluster', 'c' * 32, 'resource_mismatch'),
])
def test_verify_completed_returns_only_immutable_current_applied_receipt(
        tmp_path, monkeypatch, original_scope, original_resource, tamper):
    plugin = MemoryOptimizationPlugin()
    operation_uuid = 'verify-completed-operation'
    boot_id = '01234567-89ab-cdef-0123-456789abcdef'
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    monkeypatch.setattr(plugin, '_get_active_control', lambda: operation_uuid)
    original = {
        'success': True, 'status': 'Succeeded', 'operationUuid': operation_uuid,
        'appliedRevision': 17,
        'state': {'phase': 'POOL_READY', 'complete': True,
                  'nativeReadback': {'logical_capacity_bytes': LOGICAL_BYTES}},
    }
    record = {
        'operationUuid': operation_uuid, 'action': 'apply', 'scope': original_scope,
        'hostUuid': HOST, 'resourceUuid': original_resource,
        'bootId': boot_id, 'desiredRevision': 17,
        'requestHash': 'a' * 64, 'stage': 'APPLIED',
        'policy': {'zram': {'enabled': True}}, 'policyMode': 'effective',
        'readback': original,
    }
    os.makedirs(plugin.operation_dir)
    journal_path = tmp_path / 'operations' / (operation_uuid + '.json')
    with open(str(journal_path), 'w') as stream:
        json.dump(record, stream, sort_keys=True)
    before = journal_path.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError('verify-completed must be strictly read-only')

    for method in ('_reconcile_backend_maintenance', '_reconcile_zram_pool',
                   '_reconcile_stock_drain', '_continue_backend_maintenance',
                   '_set_active_control', '_update_operation_record',
                   '_record_operation', '_persist_maintenance_progress'):
        monkeypatch.setattr(plugin, method, forbidden)

    command = {
        'action': 'reconcile', 'scope': original_scope, 'hostUuid': HOST,
        'resourceUuid': original_resource, 'operationUuid': operation_uuid,
        'desiredRevision': 17, 'bootId': boot_id,
        'expectedControlOperationUuid': operation_uuid, 'policy': {},
        'reconcileAction': 'verify-completed'}
    if tamper == 'scope_mismatch':
        command['scope'] = 'Host' if original_scope != 'Host' else 'Global'
        command['resourceUuid'] = HOST if command['scope'] == 'Host' else 'global'
    elif tamper == 'resource_mismatch':
        command['resourceUuid'] = 'd' * 32 if original_scope == 'Cluster' else 'other-global'
    result = json.loads(plugin.reconcile({'body': json.dumps(command)}))
    if tamper is not None:
        assert result['status'] == 'Unknown', result
        assert journal_path.read_bytes() == before
        return
    assert result['status'] == 'Succeeded', result
    assert result['operationUuid'] == operation_uuid
    assert result['hostUuid'] == HOST
    assert result['bootId'] == boot_id
    assert result['appliedRevision'] == 17
    assert result['state'] == original['state']
    assert journal_path.read_bytes() == before


@pytest.mark.parametrize('tamper', [
    'missing', 'not_applied', 'old_boot', 'wrong_host', 'wrong_revision',
    'wrong_receipt_operation', 'malformed_request_hash', 'incomplete_receipt',
    'unsupported_action', 'wrong_scope', 'symlink_operation',
    'wrong_command_host', 'wrong_command_resource', 'wrong_command_control',
    'wrong_command_boot', 'wrong_command_revision',
    'malformed_record_revision', 'malformed_receipt_revision',
])
def test_verify_completed_rejects_unbound_or_incomplete_operation_without_writes(
        tmp_path, monkeypatch, tamper):
    plugin = MemoryOptimizationPlugin()
    operation_uuid = 'verify-completed-negative'
    boot_id = '01234567-89ab-cdef-0123-456789abcdef'
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    os.makedirs(plugin.operation_dir)
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    monkeypatch.setattr(plugin, '_get_active_control', lambda: operation_uuid)
    record = {
        'operationUuid': operation_uuid, 'action': 'apply', 'scope': 'Host',
        'hostUuid': HOST, 'resourceUuid': HOST, 'bootId': boot_id, 'desiredRevision': 17,
        'requestHash': 'a' * 64, 'stage': 'APPLIED',
        'policy': {'zram': {'enabled': True}}, 'policyMode': 'effective',
        'readback': {'success': True, 'status': 'Succeeded',
                     'operationUuid': operation_uuid, 'appliedRevision': 17,
                     'state': {'phase': 'POOL_READY', 'complete': True,
                               'nativeReadback': {'logical_capacity_bytes': LOGICAL_BYTES}}},
    }
    if tamper != 'missing':
        if tamper == 'not_applied':
            record['stage'] = 'UNKNOWN'
        elif tamper == 'old_boot':
            record['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
        elif tamper == 'wrong_host':
            record['hostUuid'] = 'other-host'
        elif tamper == 'wrong_revision':
            record['readback']['appliedRevision'] = 18
        elif tamper == 'wrong_receipt_operation':
            record['readback']['operationUuid'] = 'different-operation'
        elif tamper == 'malformed_request_hash':
            record['requestHash'] = 'not-a-hash'
        elif tamper == 'incomplete_receipt':
            record['readback']['state']['complete'] = False
        elif tamper == 'unsupported_action':
            record['action'] = 'drain'
        elif tamper == 'wrong_scope':
            record['scope'] = 'Cluster'
        elif tamper == 'malformed_record_revision':
            record['desiredRevision'] = 17.0
        elif tamper == 'malformed_receipt_revision':
            record['readback']['appliedRevision'] = 17.0
        path = plugin._operation_path(operation_uuid)
        if tamper == 'symlink_operation':
            target_path = str(tmp_path / 'operation-target.json')
            with open(target_path, 'w') as stream:
                json.dump(record, stream, sort_keys=True)
            os.symlink(target_path, path)
        else:
            with open(path, 'w') as stream:
                json.dump(record, stream, sort_keys=True)

    def forbidden(*args, **kwargs):
        raise AssertionError('verify-completed must not mutate or continue work')

    for method in ('_mark_not_issued', '_reconcile_backend_maintenance',
                   '_reconcile_zram_pool', '_reconcile_stock_drain',
                   '_continue_backend_maintenance', '_set_active_control',
                   '_update_operation_record', '_record_operation',
                   '_persist_maintenance_progress'):
        monkeypatch.setattr(plugin, method, forbidden)
    command = {'action': 'reconcile', 'scope': 'Host', 'hostUuid': HOST,
               'resourceUuid': HOST, 'operationUuid': operation_uuid,
               'desiredRevision': 17, 'bootId': boot_id,
               'expectedControlOperationUuid': operation_uuid, 'policy': {},
               'reconcileAction': 'verify-completed'}
    if tamper == 'wrong_command_host':
        command['hostUuid'] = 'other-host'
    if tamper == 'wrong_command_resource':
        command['resourceUuid'] = 'other-host'
    if tamper == 'wrong_command_control':
        command['expectedControlOperationUuid'] = 'f' * 32
    if tamper == 'wrong_command_boot':
        command['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
    if tamper == 'wrong_command_revision':
        command['desiredRevision'] = 18
    result = json.loads(plugin.reconcile({'body': json.dumps(command)}))
    assert result['status'] == 'Unknown'
    assert result['success'] is False


@pytest.mark.parametrize('operation,tamper', [
    ('clear', None), ('clear', 'same_boot'), ('clear', 'native_drift'),
    ('clear', 'config_drift'), ('clear', 'missing_ack'), ('clear', 'wrong_host'),
    ('clear', 'bad_hash'), ('clear', 'mixed_prior'), ('clear', 'boot_changed'),
    ('clear', 'control_changed'), ('clear', 'host_changed'), ('clear', 'policy_hash'),
    ('seal', None), ('seal', 'bad_hash'), ('seal', 'wrong_boot'),
    ('seal', 'wrong_revision'), ('seal', 'partial_write'), ('seal', 'mixed_target'),
    ('seal', 'policy_hash'), ('seal', 'wrong_expected'), ('seal', 'wrong_scope'),
    ('seal', 'future_time'), ('seal', 'wrong_host'), ('seal', 'intent'),
])
def test_pure_ksm_none_after_reboot_uses_current_proof_and_seals_only_prewrite(
        tmp_path, monkeypatch, operation, tamper):
    plugin = MemoryOptimizationPlugin()
    boot = plugin._current_boot_id()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    plugin.KSM_CONF = str(tmp_path / 'ksmtuned.conf')
    plugin.KSM_LOCK = str(tmp_path / 'ksmtuned.lock')
    current = {'run': '0', 'pages_to_scan': '2000', 'sleep_millisecs': '20',
               'use_zero_pages': '0'}
    old_ack = dict(current, run='1', use_zero_pages='1', configRevision='1')
    old_command = {'action': 'apply', 'scope': 'Host', 'hostUuid': HOST,
                   'resourceUuid': HOST, 'operationUuid': 'a' * 32,
                   'desiredRevision': 1, 'policyMode': 'effective',
                   'policy': {'schemaVersion': 1, 'ksm': {
                       'enabled': True, 'pagesToScan': 2000,
                       'sleepMillis': 20, 'zeroPagesEnabled': True}}}
    assert plugin._record_operation(old_command, 'APPLIED', {
        'success': True, 'status': 'Succeeded', 'appliedRevision': 1,
        'operationUuid': old_command['operationUuid'],
        'state': {'ksmOnly': True, 'source': 'ksmtuned'}, 'ksmReadback': old_ack})
    old = plugin._load_operation(old_command)
    old['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
    if tamper == 'same_boot':
        old['bootId'] = boot
        current.update(run='1', use_zero_pages='1')
    if tamper == 'wrong_host':
        old['hostUuid'] = 'other-host'
    if tamper == 'bad_hash' and operation == 'clear':
        old['requestHash'] = 'bad'
    if tamper == 'policy_hash' and operation == 'clear':
        old['policyHash'] = '0' * 64
    if tamper == 'mixed_prior':
        old['policy']['zram'] = {'enabled': True}
        old['policyHash'] = plugin._policy_digest(old['policy'])
    assert plugin._write_operation_record(old)
    plugin._set_active_control(old_command['operationUuid'])
    old_path = plugin._operation_path(old_command['operationUuid'])
    with open(old_path, 'rb') as stream:
        old_bytes = stream.read()
    with open(plugin.KSM_CONF, 'w') as stream:
        stream.write(memory_optimization_module.render_config('', 1, 2000, 20))
    monkeypatch.setattr(memory_optimization_module, 'native_sleep_msec',
                        lambda interval, total: interval)
    monkeypatch.setattr(plugin, '_native_sleep_for_policy', lambda interval: interval)
    monkeypatch.setattr(plugin, '_verify_native_ksm_profile', lambda: None)
    monkeypatch.setattr(plugin, '_read_ksm_sysfs', lambda field: current[field])
    monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: current['use_zero_pages'])
    monkeypatch.setattr(plugin, '_native_service_state',
                        lambda unit, state: 'inactive' if state == 'active' else 'disabled')
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': False, 'ksm': True, 'ksmZeroPages': True,
        'zram': False, 'writeback': False})
    writes = []
    def write_native(field, value):
        writes.append((field, value))
        current[field] = value
    monkeypatch.setattr(plugin, '_write_ksm_sysfs', write_native)
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_call',
                        lambda argv: writes.append(tuple(argv)))
    def forbidden_service(*args, **kwargs):
        raise AssertionError('pure KSM must not require or write the ZRAM service')
    monkeypatch.setattr(plugin, '_service_request', forbidden_service)
    command = {'action': 'apply', 'scope': 'Host', 'hostUuid': HOST,
               'resourceUuid': HOST, 'operationUuid': 'b' * 32,
               'desiredRevision': 2, 'policyMode': 'effective',
               'policy': {'schemaVersion': 1, 'ksm': {}}}
    if operation == 'clear':
        if tamper == 'native_drift':
            current['pages_to_scan'] = '2001'
        if tamper == 'config_drift':
            with open(plugin.KSM_CONF, 'w') as stream:
                stream.write(memory_optimization_module.render_config('', 3, 2000, 20))
        if tamper == 'missing_ack':
            monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: None)
        if tamper == 'boot_changed':
            def change_boot():
                monkeypatch.setattr(plugin, '_current_boot_id', lambda: 'changed')
            monkeypatch.setattr(plugin, '_verify_native_ksm_profile', change_boot)
        if tamper == 'control_changed':
            monkeypatch.setattr(plugin, '_verify_native_ksm_profile',
                                lambda: plugin._set_active_control('c' * 32))
        if tamper == 'host_changed':
            def change_host():
                monkeypatch.setattr(plugin, '_load_host_uuid', lambda: 'other-host')
            monkeypatch.setattr(plugin, '_verify_native_ksm_profile', change_host)
        result = plugin.apply(command)
        if tamper in (None, 'same_boot'):
            assert result['status'] == 'Succeeded', result
            assert result['ksmReadback']['configRevision'] == '2'
            assert result['ksmReadback']['run'] == current['run']
            assert result['ksmReadback']['use_zero_pages'] == current['use_zero_pages']
            assert not any(item[0] == 'run' for item in writes)
            assert not any(item[0] == 'systemctl' for item in writes)
            assert plugin._load_operation(command)['bootId'] == boot
            assert plugin._get_active_control() == command['operationUuid']
            assert plugin._first_use_terminal_ksm_record(
                plugin._load_operation(command), allow_empty_noop=True)
        else:
            assert result['status'] == 'Unknown', result
            assert writes == []
            assert plugin._get_active_control() == (
                'c' * 32 if tamper == 'control_changed' else old_command['operationUuid'])
    else:
        submitted = int(time.time() * 1000)
        if tamper == 'mixed_target':
            command['policy']['zram'] = {'enabled': True}
        assert plugin._record_operation(command, 'UNKNOWN', {
            'reason': 'KSM_CLEAR_PRIOR_JOURNAL_INVALID'})
        failed = plugin._load_operation(command)
        if tamper == 'bad_hash':
            failed['requestHash'] = 'bad'
        if tamper == 'wrong_boot':
            failed['bootId'] = old['bootId']
        if tamper == 'policy_hash':
            failed['policyHash'] = '0' * 64
        if tamper == 'intent':
            failed['activationIntent'] = {}
        if tamper == 'partial_write':
            failed['applyEvidence']['ksmReadback'] = dict(old_ack)
        assert plugin._write_operation_record(failed)
        query = {'action': 'reconcile', 'scope': 'Host', 'hostUuid': HOST,
                 'resourceUuid': HOST, 'operationUuid': command['operationUuid'],
                 'desiredRevision': 3 if tamper == 'wrong_revision' else 2,
                 'bootId': boot, 'policy': {}, 'taskSubmittedAt': submitted,
                 'expectedControlOperationUuid': command['operationUuid'],
                 'reconcileAction': 'seal-if-never-issued'}
        if tamper == 'wrong_expected':
            query['expectedControlOperationUuid'] = 'c' * 32
        if tamper == 'wrong_scope':
            query['scope'] = 'Cluster'
        if tamper == 'wrong_host':
            query['hostUuid'] = 'other-host'
        if tamper == 'future_time':
            query['taskSubmittedAt'] += 60000
        result = json.loads(plugin.reconcile({'body': json.dumps(query)}))
        if tamper is None:
            assert result['status'] == 'Failed', result
            assert result['reasonCode'] == 'KSM_CLEAR_NOT_ISSUED'
            assert result.get('appliedRevision') is None
            assert result['state']['policyWritesIssued'] is False
            sealed = plugin._load_operation(command)
            assert sealed['stage'] == 'NOT_ISSUED'
            assert sealed['applyEvidence'] == failed['applyEvidence']
            assert sealed['requestHash'] == failed['requestHash']
            assert result['state']['controlOperationUuid'] == (plugin._get_active_control() or '')
            assert json.loads(plugin.reconcile({'body': json.dumps(query)})) == result
            assert plugin.apply(command) == sealed['readback']
        else:
            assert result['status'] == 'Unknown', result
            assert plugin._load_operation(command) == failed
        assert writes == []
        assert plugin._get_active_control() == old_command['operationUuid']
    with open(old_path, 'rb') as stream:
        assert stream.read() == old_bytes


def test_verify_completed_accepts_real_effective_empty_ksm_receipt_read_only(
        tmp_path, monkeypatch):
    plugin = MemoryOptimizationPlugin()
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    ack = {'run': '1', 'configRevision': '3', 'pages_to_scan': '100',
           'sleep_millisecs': '20', 'use_zero_pages': '0'}
    monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: dict(ack))
    monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda command: dict(ack))
    monkeypatch.setattr(plugin, '_get_active_control', lambda: command['operationUuid'])
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'ksmZeroPages': True,
        'zram': True, 'writeback': True})
    command = {'hostUuid': HOST, 'resourceUuid': HOST, 'scope': 'Host', 'action': 'apply',
               'operationUuid': '5' * 32, 'desiredRevision': 3,
               'policyMode': 'effective', 'policy': {'ksm': {}, 'schemaVersion': 1}}
    applied = plugin.apply(command)
    assert applied['success'] is True and applied['status'] == 'Succeeded', applied
    record_path = plugin._operation_path(command['operationUuid'])
    assert plugin._first_use_terminal_ksm_record(
        plugin._load_operation(command), allow_empty_noop=True)
    with open(record_path, 'rb') as stream:
        before = stream.read()

    def forbidden(*args, **kwargs):
        raise AssertionError('verify-completed must not write, reconcile, or replay')

    for method in ('_set_active_control', '_update_operation_record', '_record_operation',
                   '_apply_ksm_policy', '_apply_service_policy',
                   '_persist_maintenance_progress'):
        if hasattr(plugin, method):
            monkeypatch.setattr(plugin, method, forbidden)
    result = json.loads(plugin.reconcile({'body': json.dumps({
        'action': 'reconcile', 'scope': 'Host', 'hostUuid': HOST,
        'resourceUuid': HOST, 'operationUuid': command['operationUuid'],
        'desiredRevision': 3, 'bootId': boot_id,
        'expectedControlOperationUuid': command['operationUuid'], 'policy': {},
        'reconcileAction': 'verify-completed'})}))
    assert result['status'] == 'Succeeded', result
    assert result['state']['ksmOnly'] is True
    assert result['appliedRevision'] == 3
    with open(record_path, 'rb') as stream:
        assert stream.read() == before


@pytest.mark.parametrize('tamper', [None, 'current_receipt_mismatch', 'worker_receipt_mismatch',
                                    'worker_running',
                                    'current_receipt_missing', 'pool_active',
                                    'pending_operation', 'stale_state', 'service_inactive'])
def test_verify_completed_binds_backend_maintenance_to_applied_go_receipt(
        tmp_path, monkeypatch, tamper):
    plugin = MemoryOptimizationPlugin()
    operation_uuid = 'a' * 32
    boot_id = '01234567-89ab-cdef-0123-456789abcdef'
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    os.makedirs(plugin.operation_dir)
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    inventory = _probe_block_inventory(boot_id)
    candidate = inventory['candidates'][0]
    request = build_backend_maintenance_request(inventory, {
        'requestId': operation_uuid, 'candidateId': candidate['identity'],
        'expectedHostBootId': boot_id, 'expectedPoolGeneration': 'none',
        'backendCapacityBytes': candidate['capacityBytes'], 'resetConfirmed': True,
    })
    _, paths = plugin._maintenance_intent_paths(operation_uuid)
    command = {
        'hostUuid': HOST, 'resourceUuid': HOST, 'scope': 'Host', 'action': 'prepareWritebackBackend',
        'operationUuid': operation_uuid, 'desiredRevision': 23, 'policy': {},
        'expectedControlOperationUuid': 'c' * 32,
        'backendPreparation': {'candidateId': candidate['identity'],
                               'expectedHostBootId': boot_id,
                               'expectedPoolGeneration': 'none',
                               'backendCapacityBytes': request['backend_capacity_bytes'],
                               'resetConfirmed': True},
        'maintenanceIntentPath': paths['intentPath'],
    }
    request_hash = plugin._operation_hash(command)
    worker_receipt = {
        'schema': 1, 'request_id': operation_uuid,
        'candidate_id': request['candidate_id'],
        'request_fingerprint': hashlib.sha256(
            json.dumps(request, separators=(',', ':')).encode('utf-8')).hexdigest(),
        'stage': 'AWAITING_SERVICE_READBACK', 'host_boot_id': boot_id,
        'target_identity': request['target_identity'],
        'expected_pool_generation': 'none', 'pool_generation': '',
        'backend_resource_uuid': 'b' * 32,
    }
    receipt = dict(worker_receipt, stage='APPLIED')
    with open(paths['requestPath'], 'w') as stream:
        json.dump(request, stream, sort_keys=True)
    with open(paths['receiptPath'], 'w') as stream:
        json.dump(worker_receipt, stream, sort_keys=True)
    with open(paths['stderrPath'], 'w') as stream:
        stream.write('')
    intent = {'schema': 1, 'operationUuid': operation_uuid, 'hostUuid': HOST,
              'bootId': boot_id, 'requestHash': request_hash,
              'controlOperationUuid': command['expectedControlOperationUuid'],
              'unit': plugin._maintenance_systemd_unit(operation_uuid),
              'requestPath': paths['requestPath'], 'receiptPath': paths['receiptPath'],
              'stderrPath': paths['stderrPath'], 'configPath': plugin.drain_config,
              'workerLaunchAttempted': True}
    with open(paths['intentPath'], 'w') as stream:
        json.dump(intent, stream, sort_keys=True)
    original = {'success': True, 'status': 'Succeeded',
                'operationUuid': operation_uuid,
                'appliedRevision': None,
                'state': {'phase': 'APPLIED', 'writebackReady': False,
                          'maintenance': receipt}}
    with open(plugin._operation_path(operation_uuid), 'w') as stream:
        json.dump({'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
                   'scope': 'Host', 'hostUuid': HOST, 'resourceUuid': HOST, 'bootId': boot_id,
                   'desiredRevision': 23, 'requestHash': request_hash,
                   'expectedControlOperationUuid': command['expectedControlOperationUuid'],
                   'backendPreparation': command['backendPreparation'],
                   'maintenanceIntentPath': paths['intentPath'], 'stage': 'APPLIED',
                   'readback': original}, stream, sort_keys=True)
    monkeypatch.setattr(plugin, '_systemd_worker_exit',
                        lambda unit: (('running', None) if tamper == 'worker_running'
                                      else ('exited', 0)))
    monkeypatch.setattr(plugin, '_get_active_control',
                        lambda: command['expectedControlOperationUuid'])
    monkeypatch.setattr(plugin, '_maintenance_service_state',
                        lambda: 'inactive' if tamper == 'service_inactive' else 'active')

    def service_request(action, args):
        if action != 'state':
            raise AssertionError('verify-completed may only query the current state')
        observed_at = time.time() - (5 if tamper == 'stale_state' else 0)
        pool = {'pool_generation': '', 'device': '', 'quality': 'unavailable',
                'reason': 'NO_QUALIFIED_MANAGED_POOL: no pool'}
        if tamper == 'pool_active':
            pool['pool_generation'] = 'd' * 64
        pending = [{}] if tamper == 'pending_operation' else []
        return {'observed_at': observed_at,
                'host': {'qualified': True, 'safe': True, 'observed_at': observed_at},
                'maintenance_blocks_activation': False,
                'pending_operations': pending, 'host_zram': pool}

    monkeypatch.setattr(plugin, '_service_request', service_request)
    service_checks = []

    def verify_service(host, saved_request, saved_receipt):
        service_checks.append((host, saved_request, saved_receipt))
        return True, None

    monkeypatch.setattr(plugin, '_verify_maintenance_service_readback', verify_service)
    current_receipt = dict(receipt)
    if tamper == 'current_receipt_mismatch':
        current_receipt['stage'] = 'UNKNOWN'
    if tamper == 'worker_receipt_mismatch':
        worker_receipt['request_fingerprint'] = '0' * 64
        with open(paths['receiptPath'], 'w') as stream:
            json.dump(worker_receipt, stream, sort_keys=True)
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt',
                        lambda: ((None, None) if tamper == 'current_receipt_missing' else
                                 (current_receipt, None)))

    def forbidden(*args, **kwargs):
        raise AssertionError('verify-completed must not continue or mutate maintenance')

    for method in ('_continue_backend_maintenance', '_prepare_backend_maintenance',
                   '_reconcile_backend_maintenance', '_set_active_control',
                   '_update_operation_record', '_record_operation',
                   '_persist_maintenance_progress'):
        monkeypatch.setattr(plugin, method, forbidden)
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_call', forbidden)
    before = (tmp_path / 'operations' / (operation_uuid + '.json')).read_bytes()
    result = json.loads(plugin.reconcile({'body': json.dumps({
        'action': 'reconcile', 'scope': 'Host', 'hostUuid': HOST,
        'resourceUuid': HOST, 'operationUuid': operation_uuid,
        'desiredRevision': 23, 'bootId': boot_id,
        'expectedControlOperationUuid': command['expectedControlOperationUuid'],
        'policy': {}, 'reconcileAction': 'verify-completed'})}))
    if tamper is None:
        assert result['status'] == 'Succeeded', result
        assert result['state'] == original['state']
        assert result['appliedRevision'] == 23
        assert result['hostUuid'] == HOST and result['bootId'] == boot_id
        assert service_checks == [(HOST, request, receipt)]
    else:
        assert result['status'] == 'Unknown', result
        assert service_checks == []
    assert (tmp_path / 'operations' / (operation_uuid + '.json')).read_bytes() == before


@pytest.mark.parametrize('tamper', [None, 'old_boot', 'guarded_disable', 'guard_revision', 'ksm',
                                  'unsupported_zero', 'ksm_mismatch',
                                  'unknown', 'missing_receipt', 'cpu_request',
                                  'cpu_revision', 'cpu_target', 'tuning_request',
                                  'tuning_revision', 'tuning_settings', 'writeback_on',
                                  'capacity', 'maintenance', 'policy_hash',
                                  'other_host', 'invalid_boot', 'other_unknown',
                                  'extra_readback', 'extra_record', 'boolean_revision',
                                  'active_service_control'])
def test_first_use_accepts_only_complete_disabled_service_history(
        tmp_path, tamper):
    # Exercise the service-backed apply used by older Agents. A newer Agent
    # may optimize this same disabled target into a KSM-only operation.
    plugin, _, calls, command, applied = _capacity_apply_fixture(
        tmp_path, zram={'enabled': False}, cpu_enabled=tamper in ('guarded_disable', 'guard_revision'),
        capacity_requested=False)
    assert applied['success'] is True and applied['status'] == 'Succeeded', applied
    record = plugin._load_operation(command)
    if tamper in ('ksm', 'unsupported_zero', 'ksm_mismatch'):
        record['policy']['ksm'] = {'enabled': False, 'pagesToScan': 2000,
                                   'sleepMillis': 20, 'zeroPagesEnabled': False}
        record['readback']['ksmReadback'] = {
            'run': '1' if tamper == 'ksm_mismatch' else '0',
            'configRevision': str(command['desiredRevision']),
            'pages_to_scan': '2000', 'sleep_millisecs': '20',
            'use_zero_pages': 'unsupported' if tamper == 'unsupported_zero' else '0'}
        record['policyHash'] = plugin._policy_digest(record['policy'])
        record['requestHash'] = plugin._operation_hash(dict(command, policy=record['policy']))
    assert record['readback']['state']['sectionComplete'] == {'cpu': True, 'tuning': True}
    sections = record['readback']['state']['sections']
    if tamper == 'old_boot':
        record['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
    elif tamper == 'unknown':
        record['stage'] = 'UNKNOWN'
    elif tamper == 'missing_receipt':
        del sections['cpu']
    elif tamper == 'cpu_request':
        sections['cpu']['request_id'] = 'unrelated-cpu'
    elif tamper == 'cpu_revision':
        sections['cpuReadback']['revision'] += 1
    elif tamper == 'cpu_target':
        sections['cpu']['agent_desired_enabled'] = True
    elif tamper == 'guard_revision':
        sections['cpuGuard']['revision'] += 1
        sections['cpuGuardReadback']['revision'] += 1
        sections['cpu']['agent_expected_revision'] += 1
    elif tamper == 'tuning_request':
        sections['tuning']['agent_request_id'] = 'unrelated-tuning'
    elif tamper == 'tuning_revision':
        sections['tuningReadback']['revision'] += 1
    elif tamper == 'tuning_settings':
        sections['tuningReadback']['settings']['host_floor_bytes'] += 1
    elif tamper == 'writeback_on':
        sections['tuning']['settings']['writeback']['enabled'] = True
        sections['tuningReadback']['settings']['writeback']['enabled'] = True
    elif tamper == 'capacity':
        record['policy']['zram']['logicalCapacityBytes'] = LOGICAL_BYTES
        record['policyHash'] = plugin._policy_digest(record['policy'])
    elif tamper == 'maintenance':
        record['maintenanceProof'] = {}
    elif tamper == 'policy_hash':
        record['policyHash'] = '0' * 64
    elif tamper == 'other_host':
        record['hostUuid'] = 'another-host'
    elif tamper == 'invalid_boot':
        record['bootId'] = 'unknown'
    elif tamper == 'extra_readback':
        record['readback']['capacity'] = {'status': 'Succeeded'}
    elif tamper == 'extra_record':
        record['unexpectedControl'] = {}
    elif tamper == 'boolean_revision':
        sections['tuningReadback']['revision'] = True
    # Keep evidence internally consistent for each negative case: rejection
    # must depend on the actual failed contract, not a second stale copy.
    record['applyEvidence'] = json.loads(json.dumps(record['readback']))
    assert plugin._write_operation_record(record)
    if tamper == 'other_unknown':
        other = dict(command, operationUuid='other-operation')
        assert plugin._record_operation(other, 'UNKNOWN', {'status': 'Unknown'})
    if tamper == 'active_service_control':
        plugin._set_active_control(command['operationUuid'])
    before = {path.name: path.read_bytes() for path in (tmp_path / 'operations').iterdir()
              if path.is_file()}
    count = len(calls)
    assert plugin._first_use_local_history_clear(
        {'hostUuid': HOST, 'operationUuid': 'new-first-use'}) is (
        tamper in (None, 'old_boot', 'guarded_disable', 'ksm', 'unsupported_zero'))
    assert len(calls) == count
    assert before == {path.name: path.read_bytes() for path in (tmp_path / 'operations').iterdir()
                      if path.is_file()}


@pytest.mark.parametrize('unsafe', [None, 'stale', 'pending', 'config_changed',
                                  'wrong_boot', 'other_unknown', 'active_service_control'])
def test_service_disable_history_allows_only_readonly_first_use_reconciliation(
        tmp_path, monkeypatch, unsafe):
    plugin, _, _, disabled_command, _ = _capacity_apply_fixture(
        tmp_path, zram={'enabled': False}, capacity_requested=False)
    disabled_path = tmp_path / 'operations' / (disabled_command['operationUuid'] + '.json')
    disabled_bytes = disabled_path.read_bytes()
    ack = {'run': '0', 'configRevision': '13', 'pages_to_scan': '2000',
           'sleep_millisecs': '20', 'use_zero_pages': '0'}
    monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda command: dict(ack))
    monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: dict(ack))
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'ksmZeroPages': True, 'zram': True, 'writeback': True})
    ksm_command = {'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                   'operationUuid': 'ksm-after-disable', 'desiredRevision': 13,
                   'policyMode': 'delta',
                   'policy': {'ksm': {'enabled': False, 'pagesToScan': 2000, 'sleepMillis': 20}}}
    assert plugin.apply(ksm_command)['status'] == 'Succeeded'
    command = {'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
               'operationUuid': 'rejected-first-use', 'desiredRevision': 14,
               'policy': {'zram': {'enabled': True}}}
    assert plugin._record_operation(command, 'UNKNOWN', {'reason': 'FIRST_ZRAM_LOCAL_CONTROL_FENCED'})
    prior = plugin._load_operation(command)
    if unsafe == 'wrong_boot':
        prior['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
        assert plugin._write_operation_record(prior)
    if unsafe == 'other_unknown':
        assert plugin._record_operation(dict(command, operationUuid='unrelated-unknown'),
                                        'UNKNOWN', {'status': 'Unknown'})
    if unsafe == 'active_service_control':
        plugin._set_active_control(disabled_command['operationUuid'])

    config = {'managed': True, 'mode': 'observe', 'resource_authorized': False,
              'initial_efficiency_enabled': False}
    config_path, template_path = tmp_path / 'config.json', tmp_path / 'template.json'
    config_path.write_text(json.dumps(config))
    template_path.write_bytes(config_path.read_bytes())
    if unsafe == 'config_changed':
        config_path.write_text(json.dumps(dict(config, resource_authorized=True)))
    plugin.zram_config_path, plugin.zram_config_template_path = str(config_path), str(template_path)
    monkeypatch.setattr(plugin, '_first_use_runtime_identity', lambda template, current: {})
    native = {
        'mode': 'observe', 'resource_authorized': False,
        'lifecycle': {'schemaVersion': 1, 'abiProfile': 'zram-service-v1',
                      'readbackAllowed': True, 'paused': False, 'activeState': 'compatibility'},
        'maintenance_blocks_activation': False, 'pending_operations': [],
        'host_zram': {'pool_generation': '', 'device': '', 'quality': 'unavailable',
                      'reason': 'NO_QUALIFIED_MANAGED_POOL:first-use'},
        'host': {'qualified': True, 'safe': True, 'observed_at': time.time()},
        'observed_at': time.time(),
    }
    if unsafe == 'stale':
        native['observed_at'] -= 30
    if unsafe == 'pending':
        native['pending_operations'] = [{'operation_id': 'still-running'}]
    reads = []

    def service_read(action, payload):
        assert action in ('state', 'host-cpu-state'), 'reconciliation must not replay writes'
        reads.append(action)
        return native if action == 'state' else {'efficiency_enabled': False}

    monkeypatch.setattr(plugin, '_service_request', service_read)
    query = {'hostUuid': HOST, 'operationUuid': command['operationUuid']}
    result = plugin._reconcile_first_zram_admission(query, prior)
    after = plugin._load_operation(query)
    assert disabled_path.read_bytes() == disabled_bytes
    assert after['requestHash'] == prior['requestHash']
    assert after['applyEvidence'] == prior['applyEvidence']
    assert after['policy'] == prior['policy']
    assert json.loads(config_path.read_text()) == (
        dict(config, resource_authorized=True) if unsafe == 'config_changed' else config)
    if unsafe:
        assert result['status'] == 'Unknown'
        assert after == prior
    else:
        assert result['status'] == 'Failed'
        assert result['reasonCode'] == 'FIRST_ZRAM_ADMISSION_NOT_ISSUED'
        assert result['state']['policyWritesIssued'] is False
        assert after['stage'] == 'NOT_ISSUED'
        count = len(reads)
        assert plugin._reconcile_first_zram_admission(query, after) == result
        assert len(reads) == count
        # Nothing was issued: the reply names the control the Agent still holds.
        replied = json.loads(plugin.reconcile({'body': json.dumps(query)}))
        assert replied['state'] == dict(result['state'], controlOperationUuid='ksm-after-disable')
        assert plugin._load_operation(query) == after
        plugin._set_active_control(None)
        replied = json.loads(plugin.reconcile({'body': json.dumps(query)}))
        assert replied['state'] == dict(result['state'], controlOperationUuid='')
        os.remove(plugin.active_control_path)
        os.mkdir(plugin.active_control_path)
        replied = json.loads(plugin.reconcile({'body': json.dumps(query)}))
        assert replied['state'] == result['state'], 'an unreadable control is omitted'
        os.rmdir(plugin.active_control_path)
        replied = json.loads(plugin.reconcile({'body': json.dumps(query)}))
        assert replied['state'] == dict(result['state'], controlOperationUuid='')


@pytest.mark.parametrize('tamper', [None, 'reason', 'policy_hash', 'intent', 'revision',
                                    'pending', 'cpu_enabled', 'stale_service_state'])
def test_only_exact_prewrite_rejections_enter_readonly_admission_reconcile(
        tmp_path, monkeypatch, tamper):
    reason = 'FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE'
    policy = {'zram': {'enabled': True}}
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    command = {'hostUuid': HOST, 'scope': 'Host', 'resourceUuid': HOST,
               'action': 'apply', 'operationUuid': 'e' * 32,
               'desiredRevision': 15, 'policyMode': 'effective', 'policy': policy}
    task_submitted_at = int(time.time() * 1000)
    assert plugin._record_operation(command, 'UNKNOWN', {'reason': reason})
    record = plugin._load_operation(command)
    if tamper == 'reason':
        record['readback'] = {'reason': 'UNRELATED_FAILURE'}
    elif tamper == 'policy_hash':
        record['policyHash'] = '0' * 64
    elif tamper == 'intent':
        record['activationIntent'] = {}
    elif tamper == 'revision':
        record['desiredRevision'] += 1
    if tamper is not None:
        assert plugin._write_operation_record(record)

    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    config = {'managed': True, 'mode': 'observe', 'resource_authorized': False,
              'state_dir': str(state_dir), 'device': '/dev/zram0',
              'initial_efficiency_enabled': False}
    config_path, template_path = tmp_path / 'config.json', tmp_path / 'template.json'
    config_path.write_text(json.dumps(config))
    template_path.write_bytes(config_path.read_bytes())
    plugin.zram_config_path, plugin.zram_config_template_path = str(config_path), str(template_path)
    plugin.drain_config = str(config_path)
    monkeypatch.setattr(plugin, '_first_use_runtime_identity', lambda template, current: {})
    native = {
        'mode': 'observe', 'resource_authorized': False,
        'lifecycle': {'schemaVersion': 1, 'abiProfile': 'zram-service-v1',
                      'readbackAllowed': True, 'paused': False, 'activeState': 'compatibility'},
        'maintenance_blocks_activation': False, 'pending_operations': [],
        'host_zram': {'pool_generation': '', 'device': '', 'quality': 'unavailable',
                      'reason': 'NO_QUALIFIED_MANAGED_POOL:first-use'},
        # The original prewrite rejection is specifically caused by unavailable
        # host safety observations. No-pool proof must still establish that no
        # execution occurred without treating missing PSI as a successful new apply.
        'host': {'qualified': False, 'safe': False, 'observed_at': time.time()},
        'observed_at': time.time(),
    }
    if tamper == 'pending':
        native['pending_operations'] = [{'operation_uuid': 'f' * 32}]
    elif tamper == 'stale_service_state':
        native['observed_at'] = time.time() - 10
    reads = []
    writes = []
    real_open = open

    def native_open(path, mode='r', *args, **kwargs):
        native_values = {
            '/proc/swaps': 'Filename Type Size Used Priority\n',
            '/sys/block/zram0/disksize': '0\n',
            '/sys/block/zram0/mm_stat': '0 0 0 0 0 0 0 0\n',
            '/sys/block/zram0/backing_dev': 'none\n',
        }
        if str(path) in native_values:
            return io.StringIO(native_values[str(path)])
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr('builtins.open', native_open)

    def service_call(action, payload):
        if action in ('state', 'host-cpu-state'):
            reads.append(action)
            if action == 'state':
                return native
            return {'efficiency_enabled': tamper == 'cpu_enabled'}
        writes.append(action)
        return {'success': True}

    monkeypatch.setattr(plugin, '_service_request', service_call)
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'ksmZeroPages': True, 'zram': True, 'writeback': True})
    ksm_writes = []
    monkeypatch.setattr(plugin, '_apply_ksm_policy',
                        lambda requested: ksm_writes.append(requested) or {})
    before = plugin._load_operation(command)
    # Match MemoryOptimizationManager's reconcile wire: policy is deliberately
    # empty; the Agent must validate against the immutable original journal.
    reconcile_command = {
        'hostUuid': HOST, 'scope': command['scope'], 'resourceUuid': command['resourceUuid'],
        'action': 'reconcile', 'operationUuid': command['operationUuid'],
        'desiredRevision': command['desiredRevision'], 'policy': {},
        'reconcileAction': 'seal-if-never-issued',
        'taskSubmittedAt': task_submitted_at, 'bootId': before['bootId'],
    }
    result = json.loads(plugin.reconcile({'body': json.dumps(reconcile_command)}))
    after = plugin._load_operation(command)

    if tamper is None:
        assert result['status'] == 'Failed'
        assert result['reasonCode'] == 'FIRST_ZRAM_ADMISSION_NOT_ISSUED'
        assert result['state']['policyWritesIssued'] is False
        assert after['stage'] == 'NOT_ISSUED'
        assert after['requestHash'] == before['requestHash']
        assert after['policy'] == before['policy']
        assert after['applyEvidence'] == before['applyEvidence']
        assert after['action'] == before['action']
        assert after['scope'] == before['scope']
        assert after['resourceUuid'] == before['resourceUuid']
        assert after['desiredRevision'] == before['desiredRevision']
        assert after['bootId'] == before['bootId']
        assert not writes and not ksm_writes
        read_count = len(reads)
        assert json.loads(plugin.reconcile({'body': json.dumps(reconcile_command)})) == result
        assert len(reads) == read_count
        mismatched_wire = dict(reconcile_command,
                               desiredRevision=reconcile_command['desiredRevision'] + 1)
        assert json.loads(plugin.reconcile({'body': json.dumps(mismatched_wire)}))['status'] == 'Unknown'
        assert plugin._load_operation(command) == after
        assert result['state']['controlOperationUuid'] == (plugin._get_active_control() or '')
        replay = plugin.apply(command)
        assert replay == after['readback']
        assert plugin._load_operation(command) == after
        assert not writes and not ksm_writes
    else:
        assert result['status'] == 'Unknown'
        assert after == before
        assert not writes and not ksm_writes


def test_writeback_only_disable_is_completed_nonactive_first_use_history(tmp_path):
    """A real writeback-only delta is safe history, not a generic Host write."""
    plugin, _, _, command, result = _capacity_apply_fixture(
        tmp_path, writeback={'enabled': False}, capacity_requested=False,
        include_zram=False)
    record = _journal(plugin)
    assert command['policy'] == {'writeback': {'enabled': False}}
    assert result['status'] == 'Succeeded'
    assert record['stage'] == 'APPLIED'
    assert record['readback']['state']['phase'] == 'READBACK'
    assert plugin._first_use_terminal_service_disable(record) is True
    assert plugin._first_use_local_history_clear({
        'hostUuid': HOST, 'operationUuid': '1' * 32}) is True


def test_capacity_only_blocker_reconciles_blocked_without_cpu_put_or_replay(tmp_path):
    plugin, state, calls, _, applied = _capacity_apply_fixture(tmp_path)
    assert applied['status'] == 'Draining'
    sections = applied['state']['sections']
    assert sections['cpuBefore']['efficiency_enabled'] is False
    assert 'cpu' not in sections
    assert sections['capacity']['_http_status'] == 202
    assert sections['capacityReadback']['reason'] == 'NATIVE_POOL_UNQUALIFIED'
    assert not [action for action, _ in calls if action == 'host-cpu']

    recorded_apply_evidence = _journal(plugin)['applyEvidence']
    before_reconcile = len(calls)
    result = _reconcile(plugin)

    assert result['status'] == 'Blocked'
    assert result['reasonCode'] == 'NATIVE_POOL_UNQUALIFIED'
    assert result['state']['knownBlocked'] is True
    assert _journal(plugin)['applyEvidence'] == recorded_apply_evidence
    reconcile_actions = [action for action, _ in calls[before_reconcile:]]
    assert reconcile_actions
    assert set(reconcile_actions) <= {'capacity-state', 'host-cpu-state', 'tuning-state'}
    assert not [action for action in reconcile_actions
                if action in ('capacity', 'host-cpu', 'apply')]
    assert state['capacity']['reason'] == 'NATIVE_POOL_UNQUALIFIED'


@pytest.mark.parametrize('tamper', [None, 'wrong_boot', 'wrong_target', 'wrong_receipt',
                                    'wrong_operation_hash', 'non_backend_config',
                                    'expanded_runtime_config', 'missing_config_before',
                                    'snapshot_extra_field', 'snapshot_duplicate_key',
                                    'snapshot_nonfinite', 'current_duplicate_key',
                                    'current_nonfinite',
                                    'archive_manifest_mismatch', 'template_control_changed',
                                    'template_omitted_control_added',
                                    'snapshot_type_mismatch', 'no_controller_stop',
                                    'malformed_controller_stop',
                                    'unfinished_history', 'config_changed_before_cas',
                                    'multiple_preparations', 'corrupt_historical_preparation',
                                    'ordinary_registration', 'ksm_history',
                                    'ksm_before_prepare',
                                    'ksm_before_and_after_prepare',
                                    'active_prepared_backend_ksm',
                                    'active_prepared_backend_ksm_wrong_resource',
                                    'active_prepared_backend_ksm_wrong_capacity',
                                    'active_prepared_backend_ksm_wrong_boot',
                                    'active_prepared_backend_ksm_enabled',
                                    'active_prepared_backend_ksm_clear',
                                    'active_prepared_backend_ksm_clear_config_drift',
                                    'active_prepared_backend_ksm_clear_seal_config_drift',
                                    'active_prior_preparation_ksm',
                                    'active_prior_preparation_wrong_uuid',
                                    'active_prior_preparation_wrong_capacity',
                                    'active_prior_preparation_wrong_boot',
                                    'active_prior_preparation_enabled',
                                    'active_prior_preparation_bad_current_receipt',
                                    'prepared_backend_observation_reconcile',
                                    'prepared_backend_observation_bad_receipt_reconcile',
                                    'non_ksm_after_ksm_prepare',
                                    'late_host_uuid',
                                    'host_uuid_switch_during_proof'])
def test_cold_prepared_backend_can_be_followed_by_first_zram_enable(
        tmp_path, monkeypatch, tamper):
    """A verified first backend preparation must not strand the first enable."""
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    assert boot_id
    preparation_id = 'a' * 32
    resource_uuid = 'c' * 32
    state_dir = tmp_path / 'state'
    (state_dir / 'backend-maintenance').mkdir(parents=True)
    operation_dir = tmp_path / 'operations'
    maintenance_dir = operation_dir / 'backend-maintenance'
    maintenance_dir.mkdir(parents=True)
    config_path = tmp_path / 'config.json'
    template_path = tmp_path / 'config-template.json'
    # Match the shipped config shape. Use the production inventory/request
    # builder to construct the cold preparation proof.
    factory = {
        'version': 2, 'mode': 'observe', 'managed': True,
        'resource_authorized': False, 'initial_efficiency_enabled': False,
        'vm_selection': 'all_running', 'vm_uuids': [], 'state_dir': str(state_dir),
        'monitor_socket': '/run/zram-efficiency-admission/monitor.sock',
        'control_socket': '/run/zram-efficiency-admission/control.sock',
        'device': '/dev/zram0', 'internal_rule': {}, 'budget': {},
    }
    if tamper == 'template_omitted_control_added':
        factory.pop('managed')
    template_bytes = (json.dumps(factory, sort_keys=True, indent=2) + '\n').encode('utf-8')
    # OpenRuntime expands the shipped sparse config before Go persists
    # config.before.json. Keep the typed snapshot and current config equal
    # except for the backend set by this request.
    runtime_before = dict(factory)
    if tamper == 'template_omitted_control_added':
        # An omitted template field must not be introduced by the Go snapshot
        # and then treated as an authorized control value.
        runtime_before['managed'] = True
    runtime_before.update({
        'algorithm_preference': ['lzo'],
        'startup_observation_seconds': 60,
        'discovery_interval_seconds': 60,
        'discovery_timeout_seconds': 30,
        'vm_list_ttl_seconds': 120,
        'vm_identity_request_bytes': 1048576,
        'internal_rule': {
            'cpu_only': True, 'cpu_fraction': 0.05,
            'memory_change_bytes_per_second': 0,
            'io_bytes_per_second': 0, 'idle_seconds': 60,
            'cooldown_seconds': 0, 'step_bytes': 0,
            'require_external_data': False,
        },
        'budget': {
            'pool_bytes': 1073741824,
            'allocator_limit_bytes': 536870912,
            'host_floor_bytes': 0, 'metadata_reserve_bytes': 0,
            'transient_reserve_bytes': 0, 'step_limit_bytes': 0,
            'host_bytes_per_minute': 0, 'vm_bytes_per_minute': 0,
        },
    })
    inventory = _probe_block_inventory(boot_id)
    candidate_id = inventory['candidates'][0]['identity']
    request = build_backend_maintenance_request(inventory, {
        'requestId': preparation_id, 'candidateId': candidate_id,
        'expectedHostBootId': boot_id, 'expectedPoolGeneration': 'none',
        'backendCapacityBytes': inventory['candidates'][0]['capacityBytes'],
        'resetConfirmed': True,
    })
    if tamper in ('multiple_preparations', 'active_prior_preparation_ksm',
                  'active_prior_preparation_wrong_uuid',
                  'active_prior_preparation_wrong_capacity',
                  'active_prior_preparation_wrong_boot',
                  'active_prior_preparation_enabled',
                  'active_prior_preparation_bad_current_receipt'):
        runtime_before['backend'] = {
            'device': request['backend']['device'],
            'minimum_filesystem_free_bytes':
                request['backend']['minimum_filesystem_free_bytes'],
        }
    prepared_config = dict(runtime_before, backend={
        'device': request['backend']['device'],
        'minimum_filesystem_free_bytes': request['backend']['minimum_filesystem_free_bytes'],
    })
    config_path.write_bytes((json.dumps(prepared_config, sort_keys=True, indent=2) + '\n').encode('utf-8'))
    template_path.write_bytes(template_bytes)
    request_fingerprint = hashlib.sha256(
        json.dumps(request, separators=(',', ':')).encode('utf-8')).hexdigest()
    archive_path = state_dir / 'backend-maintenance' / preparation_id / 'pre-reset-archive'
    archive_path.mkdir(parents=True)
    archive_config_path = archive_path / 'config.json'
    archive_source_config = dict(factory)
    if 'backend' in runtime_before:
        archive_source_config['backend'] = dict(runtime_before['backend'])
    archive_source_bytes = (json.dumps(
        archive_source_config, sort_keys=True, indent=2) + '\n').encode('utf-8')
    archive_config_path.write_bytes(archive_source_bytes)
    archive_config_digest = hashlib.sha256(archive_source_bytes).hexdigest()
    with open(archive_path / 'manifest.json', 'w') as stream:
        json.dump({'config.json': archive_config_digest,
                   'target_device': request['backend']['device']}, stream, sort_keys=True)
    maintenance_receipt = {
        'schema': 1, 'request_id': preparation_id, 'candidate_id': candidate_id,
        'request_fingerprint': request_fingerprint, 'stage': 'APPLIED',
        'started_at': '2026-10-16T00:00:00Z', 'updated_at': '2026-10-16T00:00:01Z',
        'host_boot_id': boot_id, 'target_identity': request['target_identity'],
        'reset_attempted': False,
        'backend_resource_uuid': resource_uuid,
        'archive': str(archive_path),
    }
    with open(state_dir / 'backend-maintenance' / 'current.json', 'w') as stream:
        json.dump(maintenance_receipt, stream, sort_keys=True)
    paths = {
        'requestPath': str(maintenance_dir / (preparation_id + '.request.json')),
        'receiptPath': str(maintenance_dir / (preparation_id + '.receipt.json')),
        'stderrPath': str(maintenance_dir / (preparation_id + '.stderr')),
        'intentPath': str(maintenance_dir / (preparation_id + '.intent.json')),
    }
    with open(paths['requestPath'], 'w') as stream:
        json.dump(request, stream, sort_keys=True)
    # The Go worker's immutable receipt predates final service readback. The
    # operation journal and Go current.json carry the later APPLIED receipt.
    worker_receipt = dict(maintenance_receipt,
                          stage='AWAITING_SERVICE_READBACK',
                          updated_at='2026-10-16T00:00:00Z',
                          archive='prepared-backend.tar')
    maintenance_receipt['archive'] = str(archive_path)
    worker_receipt['archive'] = str(archive_path)
    with open(paths['receiptPath'], 'w') as stream:
        json.dump(worker_receipt, stream, sort_keys=True)
    with open(paths['stderrPath'], 'w') as stream:
        stream.write('')
    plugin = MemoryOptimizationPlugin()
    plugin_config = {'operationDir': str(operation_dir)}
    if tamper not in ('late_host_uuid', 'host_uuid_switch_during_proof'):
        plugin_config['hostUuid'] = HOST
    plugin.configure(plugin_config)
    if tamper in ('late_host_uuid', 'host_uuid_switch_during_proof'):
        # KvmRESTService config is shared with HostPlugin; connect fills this
        # identity after plugin.configure({}) during normal startup.
        plugin.config[memory_optimization_module.kvmagent.HOST_UUID] = HOST
    plugin.zram_config_path = str(config_path)
    plugin.zram_config_template_path = str(template_path)
    plugin.drain_config = str(config_path)
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    ksm_before_prepare = None
    if tamper in ('ksm_before_prepare', 'ksm_before_and_after_prepare',
                  'non_ksm_after_ksm_prepare'):
        ksm_readback = {'run': '1', 'configRevision': '3',
                        'pages_to_scan': '100', 'sleep_millisecs': '20',
                        'use_zero_pages': '0'}
        ksm_before_prepare = {
            'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
            'operationUuid': '3' * 32, 'desiredRevision': 3,
            'policyMode': 'delta',
            'policy': {'ksm': {'enabled': True, 'pagesToScan': 100,
                               'sleepMillis': 20, 'zeroPagesEnabled': False}},
        }
        monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
            'supported': True, 'ksm': True, 'ksmZeroPages': True,
            'zram': True, 'writeback': True})
        monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda value: ksm_readback)
        monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: ksm_readback)
        ksm_result = plugin.apply(ksm_before_prepare)
        assert ksm_result['success'] is True, ksm_result
        assert plugin._get_active_control() == ksm_before_prepare['operationUuid']
    preparation_command = {
        'hostUuid': HOST, 'scope': 'Host', 'action': 'prepareWritebackBackend',
        'operationUuid': preparation_id, 'desiredRevision': 1, 'policy': {},
        'expectedControlOperationUuid': (
            ksm_before_prepare['operationUuid'] if ksm_before_prepare else None),
        'backendPreparation': {'candidateId': candidate_id,
                               'expectedHostBootId': boot_id,
                               'expectedPoolGeneration': 'none',
                               'backendCapacityBytes': request['backend_capacity_bytes'],
                               'resetConfirmed': True},
        'maintenanceIntentPath': paths['intentPath'],
    }
    preparation_hash = plugin._operation_hash(preparation_command)
    with open(paths['intentPath'], 'w') as stream:
        json.dump({
            'schema': 1, 'operationUuid': preparation_id, 'hostUuid': HOST,
            'bootId': boot_id, 'requestHash': preparation_hash,
            'unit': 'zstack-memory-backend-maintenance-' + preparation_id,
            'requestPath': paths['requestPath'], 'receiptPath': paths['receiptPath'],
            'stderrPath': paths['stderrPath'], 'configPath': str(config_path),
            'controlOperationUuid': (ksm_before_prepare['operationUuid']
                                     if ksm_before_prepare else None),
            'workerLaunchAttempted': True,
        }, stream, sort_keys=True)
    assert plugin._record_operation(preparation_command, 'PREPARING')
    applied_result = plugin._maintenance_result(
        preparation_command, 'Succeeded', 'APPLIED', receipt=maintenance_receipt)
    assert plugin._update_operation_record(preparation_id, 'APPLIED', applied_result)
    # The Go worker's pre-change typed RuntimeConfig is request-scoped. The
    # stop identity binds the original raw config copied to the archive.
    before_path = state_dir / 'backend-maintenance' / preparation_id / 'config.before.json'
    with open(before_path, 'w') as stream:
        json.dump(runtime_before, stream, sort_keys=True)
    saved = plugin._load_operation(preparation_command)
    if tamper == 'no_controller_stop':
        # A controller that was already inactive needs no synthetic stop
        # proof; the request-scoped Go snapshot and archive remain authoritative.
        saved.pop('maintenanceProgress', None)
    else:
        saved['maintenanceProgress'] = {'controllerStop': {'identity': {
            'sourceConfigSha256': archive_config_digest,
            'templateSha256': hashlib.sha256(template_bytes).hexdigest(),
        }}}
        if tamper == 'malformed_controller_stop':
            saved['maintenanceProgress']['controllerStop'] = None
    assert plugin._write_operation_record(saved)
    if tamper == 'missing_config_before':
        before_path.unlink()
    elif tamper == 'snapshot_extra_field':
        snapshot = json.loads(before_path.read_text())
        snapshot['unexpected'] = True
        before_path.write_text(json.dumps(snapshot, sort_keys=True))
    elif tamper == 'snapshot_duplicate_key':
        before_path.write_text(before_path.read_text().replace(
            '"version": 2', '"version": 2, "version": 2'))
    elif tamper == 'snapshot_nonfinite':
        before_path.write_text(before_path.read_text().replace('0.05', 'NaN'))
    elif tamper == 'current_duplicate_key':
        config_path.write_bytes(config_path.read_bytes().replace(
            b'"version": 2', b'"version": 2, "version": 2'))
    elif tamper == 'current_nonfinite':
        config_path.write_bytes(config_path.read_bytes().replace(b'0.05', b'Infinity'))
    elif tamper == 'archive_manifest_mismatch':
        with open(archive_path / 'manifest.json', 'w') as stream:
            json.dump({'config.json': '0' * 64,
                       'target_device': request['backend']['device']}, stream, sort_keys=True)
    elif tamper == 'template_control_changed':
        archived = dict(factory, device='/dev/zram9')
        archived_bytes = (json.dumps(archived, sort_keys=True, indent=2) + '\n').encode('utf-8')
        archive_config_path.write_bytes(archived_bytes)
        archive_digest = hashlib.sha256(archived_bytes).hexdigest()
        with open(archive_path / 'manifest.json', 'w') as stream:
            json.dump({'config.json': archive_digest,
                       'target_device': request['backend']['device']}, stream, sort_keys=True)
        saved = plugin._load_operation(preparation_command)
        saved['maintenanceProgress']['controllerStop']['identity'][
            'sourceConfigSha256'] = archive_digest
        assert plugin._write_operation_record(saved)
    elif tamper == 'snapshot_type_mismatch':
        snapshot = json.loads(before_path.read_text())
        snapshot['version'] = True
        before_path.write_text(json.dumps(snapshot, sort_keys=True))

    if tamper in ('multiple_preparations', 'corrupt_historical_preparation',
                  'active_prior_preparation_ksm',
                  'active_prior_preparation_wrong_uuid',
                  'active_prior_preparation_wrong_capacity',
                  'active_prior_preparation_wrong_boot',
                  'active_prior_preparation_enabled',
                  'active_prior_preparation_bad_current_receipt'):
        # Keep an earlier, independently completed preparation in history.
        # Its target may differ from the latest current receipt; only the
        # latest preparation is bound to today's config/backend state.
        old_id = 'b' * 32
        old_request = dict(request, request_id=old_id)
        old_fingerprint = hashlib.sha256(
            json.dumps(old_request, separators=(',', ':')).encode('utf-8')).hexdigest()
        old_receipt = dict(maintenance_receipt, request_id=old_id,
                           candidate_id=old_request['candidate_id'],
                           request_fingerprint=old_fingerprint,
                           backend_resource_uuid='d' * 32)
        old_archive = state_dir / 'backend-maintenance' / old_id / 'pre-reset-archive'
        old_archive.mkdir(parents=True)
        old_receipt['archive'] = str(old_archive)
        (old_archive / 'config.json').write_bytes(template_bytes)
        with open(old_archive / 'manifest.json', 'w') as stream:
            json.dump({'config.json': hashlib.sha256(template_bytes).hexdigest(),
                       'target_device': old_request['backend']['device']},
                      stream, sort_keys=True)
        old_worker_receipt = dict(old_receipt,
                                  stage='AWAITING_SERVICE_READBACK',
                                  updated_at='2026-10-16T00:00:00Z')
        old_paths = {
            'requestPath': str(maintenance_dir / (old_id + '.request.json')),
            'receiptPath': str(maintenance_dir / (old_id + '.receipt.json')),
            'stderrPath': str(maintenance_dir / (old_id + '.stderr')),
            'intentPath': str(maintenance_dir / (old_id + '.intent.json')),
        }
        with open(old_paths['requestPath'], 'w') as stream:
            json.dump(old_request, stream, sort_keys=True)
        with open(old_paths['receiptPath'], 'w') as stream:
            json.dump(old_worker_receipt, stream, sort_keys=True)
        with open(old_paths['stderrPath'], 'w') as stream:
            stream.write('')
        old_command = dict(preparation_command, operationUuid=old_id,
                           maintenanceIntentPath=old_paths['intentPath'])
        old_hash = plugin._operation_hash(old_command)
        with open(old_paths['intentPath'], 'w') as stream:
            json.dump({
                'schema': 1, 'operationUuid': old_id, 'hostUuid': HOST,
                'bootId': boot_id, 'requestHash': old_hash,
                'unit': 'zstack-memory-backend-maintenance-' + old_id,
                'requestPath': old_paths['requestPath'],
                'receiptPath': old_paths['receiptPath'],
                'stderrPath': old_paths['stderrPath'], 'configPath': str(config_path),
                'controlOperationUuid': None, 'workerLaunchAttempted': True,
            }, stream, sort_keys=True)
        assert plugin._record_operation(old_command, 'PREPARING')
        old_result = plugin._maintenance_result(
            old_command, 'Succeeded', 'APPLIED', receipt=old_receipt)
        assert plugin._update_operation_record(old_id, 'APPLIED', old_result)
        if tamper in ('multiple_preparations', 'active_prior_preparation_ksm',
                      'active_prior_preparation_wrong_uuid',
                      'active_prior_preparation_wrong_capacity',
                      'active_prior_preparation_wrong_boot',
                      'active_prior_preparation_enabled',
                      'active_prior_preparation_bad_current_receipt'):
            archived_files = {
                'backend-maintenance-current.json': old_receipt,
                'backend-ownership.json': {
                    'version': 1, 'generation': 'd' * 32,
                    'configured': {
                        'device': old_request['backend']['device'],
                        'minimum_filesystem_free_bytes':
                            old_request['backend']['minimum_filesystem_free_bytes'],
                    },
                    'identity': old_receipt['target_identity'],
                    'claimed_at': '2026-10-16T00:00:00Z',
                },
                'backend-settings.json': {
                    'revision': 1, 'desired': old_request['backend'],
                    'apply_state': 'APPLIED', 'request_id': old_id,
                    'request_fingerprint': old_fingerprint,
                },
            }
            manifest_path = archive_path / 'manifest.json'
            with open(manifest_path, 'r') as stream:
                manifest = json.load(stream)
            for name, value in archived_files.items():
                path = archive_path / name
                with open(path, 'w') as stream:
                    json.dump(value, stream, sort_keys=True)
                manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            with open(manifest_path, 'w') as stream:
                json.dump(manifest, stream, sort_keys=True)
        if tamper == 'corrupt_historical_preparation':
            unfinished = plugin._maintenance_result(
                old_command, 'Draining', 'EXECUTOR_RUNNING')
            assert plugin._update_operation_record(old_id, 'DRAINING', unfinished)

    command = {
        'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
        'operationUuid': '1' * 32, 'desiredRevision': 1,
        'policyMode': 'delta', 'policy': {'zram': {
            'enabled': True, 'logicalCapacityBytes': LOGICAL_BYTES,
            'ramLimitBytes': PHYSICAL_BYTES}},
    }
    if tamper in ('prepared_backend_observation_reconcile',
                  'prepared_backend_observation_bad_receipt_reconcile'):
        # Match an ordinary pre-write ZRAM-only request while keeping test
        # identities synthetic. The prepared-B proof is separate
        # completed history, not part of this apply policy.
        command.update({'operationUuid': '8' * 32, 'desiredRevision': 17,
                        'resourceUuid': HOST})
        command['policy'] = {
            'schemaVersion': 1,
            'zram': {'enabled': True, 'logicalCapacityBytes': LOGICAL_BYTES,
                     'ramLimitBytes': PHYSICAL_BYTES},
        }
    if tamper not in (None, 'corrupt_historical_preparation', 'ordinary_registration', 'ksm_history', 'ksm_before_prepare',
                      'ksm_before_and_after_prepare', 'active_prepared_backend_ksm',
                      'active_prepared_backend_ksm_wrong_resource',
                      'active_prepared_backend_ksm_wrong_capacity',
                      'active_prepared_backend_ksm_wrong_boot',
                      'active_prepared_backend_ksm_enabled',
                      'active_prepared_backend_ksm_clear',
                      'active_prepared_backend_ksm_clear_config_drift',
                      'active_prepared_backend_ksm_clear_seal_config_drift',
                      'active_prior_preparation_ksm',
                      'active_prior_preparation_wrong_uuid',
                      'active_prior_preparation_wrong_capacity',
                      'active_prior_preparation_wrong_boot',
                      'active_prior_preparation_enabled',
                      'active_prior_preparation_bad_current_receipt',
                      'prepared_backend_observation_reconcile',
                      'prepared_backend_observation_bad_receipt_reconcile',
                      'non_ksm_after_ksm_prepare'):
        assert plugin._record_operation(command, 'PREPARING')
    state_reads = [0]

    def native_state(mode, authorized):
        now = time.time()
        return {
            'mode': mode, 'resource_authorized': authorized,
            'lifecycle': {'schemaVersion': 1, 'abiProfile': 'zram-service-v1',
                          'readbackAllowed': True, 'paused': False,
                          'activeState': 'compatibility'},
            'maintenance_blocks_activation': False, 'pending_operations': [],
            'host_zram': {'pool_generation': '', 'device': '', 'quality': 'unavailable',
                          'reason': 'NO_QUALIFIED_MANAGED_POOL:first-use'},
            'host': {'qualified': True, 'safe': True, 'observed_at': now},
            'host_cpu': {'efficiency_enabled': False, 'revision': 1},
            'observed_at': now,
        }

    live_receipt = dict(maintenance_receipt)
    if tamper == 'wrong_boot':
        live_receipt['host_boot_id'] = 'fedcba98-7654-3210-fedc-ba9876543210'
    elif tamper == 'wrong_target':
        live_receipt['target_identity'] = dict(request['target_identity'], node_inode=1001)
    elif tamper == 'wrong_receipt':
        live_receipt['stage'] = 'AWAITING_SERVICE_READBACK'
    elif tamper == 'active_prior_preparation_bad_current_receipt':
        live_receipt['stage'] = 'FAILED_REQUIRES_REVIEW'
    elif tamper == 'wrong_operation_hash':
        with open(paths['intentPath'], 'r') as stream:
            intent = json.load(stream)
        intent['requestHash'] = '0' * 64
        with open(paths['intentPath'], 'w') as stream:
            json.dump(intent, stream, sort_keys=True)
    elif tamper == 'non_backend_config':
        prepared_config['mode'] = 'reclaim'
        config_path.write_bytes((json.dumps(prepared_config, sort_keys=True, indent=2) + '\n').encode('utf-8'))
    elif tamper == 'unfinished_history':
        unfinished = plugin._maintenance_result(
            preparation_command, 'Draining', 'EXECUTOR_RUNNING')
        assert plugin._update_operation_record(preparation_id, 'DRAINING', unfinished)

    backend_observed_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    service_backend = {
        'claimed': True, 'identity_qualified': True,
        'ownership_generation': resource_uuid,
        'effective': {'observed_at': backend_observed_at,
                      'identity': _owned_backend_identity(boot_id)},
        'backend_resource': {
            'resource_uuid': resource_uuid, 'fingerprint': 'a' * 64,
            'state': 'PREPARED', 'active': False,
            'capacity_bytes': request['backend_capacity_bytes'],
            'observed_at': backend_observed_at,
        },
    }
    service_detail = {
        'claimed': True, 'identity_qualified': True,
        'ownership_generation': resource_uuid,
        'configured': {'device': '/dev/vdb'},
        'effective': {'observed_at': service_backend['effective']['observed_at'],
                      'identity': _owned_backend_identity(boot_id)},
    }
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt',
                        lambda: (live_receipt, None))
    monkeypatch.setattr(plugin, '_systemd_worker_exit',
                        lambda unit: ('exited', 0))
    def readonly_query(action, payload):
        if action == 'host-cpu-state':
            return {'efficiency_enabled': False}
        return service_backend if action == 'backend-state' else service_detail

    monkeypatch.setattr(plugin, '_readonly_query', readonly_query)
    monkeypatch.setattr(
        memory_optimization_module, 'probe_writeback_backends',
        lambda host_uuid, backend, config: _probe_block_inventory(
            boot_id, service_backend=backend, service_config=config))

    # An already-completed prep journal is not the current apply operation.
    # Keep the two operation IDs distinct while proving the existing history
    # fence admits this exact, receipt-bound preparation.
    if tamper == 'host_uuid_switch_during_proof':
        completed_evidence = plugin._completed_backend_preparation_evidence

        def switch_host_after_completed_proof(*args, **kwargs):
            result = completed_evidence(*args, **kwargs)
            plugin.config[memory_optimization_module.kvmagent.HOST_UUID] = 'f' * 32
            return result

        monkeypatch.setattr(plugin, '_completed_backend_preparation_evidence',
                            switch_host_after_completed_proof)
        with pytest.raises(RuntimeError, match='FIRST_ZRAM_BACKEND_PREPARATION_UNPROVEN'):
            plugin._first_use_backend_preparation_proof(prepared_config, factory)
        return

    if tamper in (None, 'expanded_runtime_config', 'multiple_preparations',
                  'no_controller_stop', 'late_host_uuid'):
        backend_preparation = plugin._first_use_backend_preparation_proof(
            prepared_config, factory)
        assert plugin._record_operation(command, 'PREPARING')
        original_listdir = os.listdir

        def ordered_operation_history(path):
            if path == str(operation_dir):
                # The directory entry must not change which journal ID is
                # considered the current apply operation.
                names = original_listdir(path)
                return sorted(names, key=lambda name: 0 if name == 'backend-maintenance' else 1)
            return original_listdir(path)

        monkeypatch.setattr(memory_optimization_module.os, 'listdir', ordered_operation_history)
        assert plugin._first_use_local_history_clear(
            command, backend_preparation=backend_preparation)
        os.unlink(plugin._operation_path(command['operationUuid']))

    def service_call(action, payload):
        if action == 'state':
            state_reads[0] += 1
            return native_state('observe' if state_reads[0] == 1 else 'reclaim',
                                state_reads[0] != 1)
        if action == 'host-cpu-state':
            return {'efficiency_enabled': False, 'revision': 1}
        if action == 'capacity-state':
            return {'revision': 1}
        if action == 'tuning-state':
            if tamper == 'config_changed_before_cas':
                changed_config = dict(prepared_config, unexpected=True)
                config_path.write_bytes((json.dumps(
                    changed_config, sort_keys=True, indent=2) + '\n').encode('utf-8'))
            return {'revision': 1}
        if action == 'backend-maintenance':
            return live_receipt
        raise AssertionError('unexpected service request: %s' % action)

    plugin.service_call = service_call
    runtime_processes = [100, 101]
    real_open = open
    real_readlink = os.readlink

    def runtime_bounded_output(args, timeout_seconds):
        assert timeout_seconds in (5, 30)
        if args[:2] == ['systemctl', 'show']:
            pid = runtime_processes.pop(0)
            return ('FragmentPath=/usr/lib/systemd/system/zram-memory.service\n'
                    'DropInPaths=\nMainPID=%s\nActiveState=active\n' % pid).encode('utf-8')
        if args[:2] == ['rpm', '-V']:
            raise subprocess.CalledProcessError(
                1, args, output=b'..5....T. c /etc/zram-memory/config.json\n')
        if args[:2] == ['rpm', '-q']:
            return b'zstack-zram-1.0.0-1.el8.x86_64\n'
        if args[:2] == ['rpm', '-qf']:
            return b'zstack-zram\n'
        raise AssertionError('unexpected runtime command: %r' % (args,))

    def runtime_open(path, mode='r', *args, **kwargs):
        path = str(path)
        native_values = {
            '/proc/swaps': 'Filename Type Size Used Priority\n',
            '/sys/block/zram0/disksize': '0\n',
            '/sys/block/zram0/mm_stat': '0 0 0 0 0 0 0 0\n',
            '/sys/block/zram0/backing_dev': 'none\n',
        }
        if path in native_values:
            return io.StringIO(native_values[path])
        match = re.match(r'^/proc/(100|101)/stat$', path)
        if match:
            pid = match.group(1)
            fields = ['S'] + ['0'] * 18 + [('1000' if pid == '100' else '2000')]
            return io.StringIO('%s (zram-efficiency) %s' % (pid, ' '.join(fields)))
        if path in ('/usr/lib/systemd/system/zram-memory.service',
                    '/usr/local/libexec/zram-efficiency'):
            data = (b'test systemd unit\n' if 'systemd' in path else b'test executable\n')
            return io.BytesIO(data) if 'b' in mode else io.StringIO(data.decode('utf-8'))
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(MemoryOptimizationPlugin, '_bounded_command_output',
                        staticmethod(runtime_bounded_output))
    monkeypatch.setattr(memory_optimization_module.os, 'readlink',
                        lambda path: '/usr/local/libexec/zram-efficiency'
                        if path in ('/proc/100/exe', '/proc/101/exe') else real_readlink(path))
    monkeypatch.setattr('builtins.open', runtime_open)
    restarts = []
    monkeypatch.setattr(plugin, '_bounded_controller_restart', lambda: restarts.append(True))
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'ksmZeroPages': True,
        'zram': True, 'writeback': True})
    service_policy_calls = []
    monkeypatch.setattr(plugin, '_apply_service_policy', lambda value: (
        service_policy_calls.append(value) or
        {'success': True, 'status': 'Succeeded', 'state': {'phase': 'APPLIED'}}))

    config_bytes_before_apply = config_path.read_bytes()
    if tamper == 'late_host_uuid':
        # Exercise the public inventory route after the standard connect
        # handshake. This reaches the real no-pool decorator and preparation
        # proof, rather than testing only the first-use apply helper.
        plugin.active_control_path = str(tmp_path / 'active-control')
        monkeypatch.setattr(plugin, '_service_unit_stopped', lambda: True)
        monkeypatch.setattr(plugin, '_zram_pool_preparation_eligibility', lambda host_uuid: {
            'hostUuid': host_uuid, 'bootId': boot_id, 'poolGeneration': 'none',
            'controlOperationUuid': None, 'canPrepareZramPool': False,
            'zramPoolPreparationReasons': ['MEMORY_SERVICE_NOT_STOPPED'],
            'zramPoolPreparationQuality': 'Ineligible',
            'zramPoolPreparationObservedAt': '2026-10-17T00:00:00Z',
        })
        inventory_response = json.loads(plugin.writeback_backends({
            'body': json.dumps({'hostUuid': HOST})}))
        assert inventory_response['success'] is True, inventory_response
        assert inventory_response['status'] == 'Succeeded', inventory_response
        assert inventory_response['state']['poolGeneration'] == 'none', inventory_response

    if tamper in (None, 'expanded_runtime_config', 'multiple_preparations',
                  'no_controller_stop',
                  'prepared_backend_observation_reconcile',
                  'prepared_backend_observation_bad_receipt_reconcile',
                  'late_host_uuid',
                  'corrupt_historical_preparation',
                  'ordinary_registration', 'ksm_history', 'ksm_before_prepare',
                  'ksm_before_and_after_prepare', 'active_prepared_backend_ksm',
                  'active_prepared_backend_ksm_wrong_resource',
                  'active_prepared_backend_ksm_wrong_capacity',
                  'active_prepared_backend_ksm_wrong_boot',
                  'active_prepared_backend_ksm_enabled',
                  'active_prepared_backend_ksm_clear',
                  'active_prepared_backend_ksm_clear_config_drift',
                  'active_prepared_backend_ksm_clear_seal_config_drift',
                  'active_prior_preparation_ksm',
                  'active_prior_preparation_wrong_uuid',
                  'active_prior_preparation_wrong_capacity',
                  'active_prior_preparation_wrong_boot',
                  'active_prior_preparation_enabled',
                  'active_prior_preparation_bad_current_receipt',
                  'non_ksm_after_ksm_prepare'):
        if tamper == 'ordinary_registration':
            registration = {
                'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                'operationUuid': '2' * 32, 'desiredRevision': 2,
                'policyMode': 'delta',
                'policy': {'writeback': {
                    'enabled': False, 'backendResourceUuid': resource_uuid,
                    'backendCapacityBytes': request['backend_capacity_bytes']}},
            }
            registration_result = plugin.apply(registration)
            assert registration_result['success'] is True
            assert plugin._load_operation(registration)['stage'] == 'APPLIED'
        elif tamper in ('ksm_history', 'ksm_before_and_after_prepare'):
            revision = 4 if tamper == 'ksm_before_and_after_prepare' else 3
            pages_to_scan = 200 if tamper == 'ksm_before_and_after_prepare' else 100
            sleep_millisecs = 40 if tamper == 'ksm_before_and_after_prepare' else 20
            ksm_readback = {'run': '1', 'configRevision': str(revision),
                            'pages_to_scan': str(pages_to_scan),
                            'sleep_millisecs': str(sleep_millisecs),
                            'use_zero_pages': '1' if revision == 4 else '0'}
            ksm_command = {
                'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                'operationUuid': str(revision) * 32, 'desiredRevision': revision,
                'policyMode': 'delta',
                'policy': {'ksm': {'enabled': True, 'pagesToScan': pages_to_scan,
                                   'sleepMillis': sleep_millisecs,
                                   'zeroPagesEnabled': revision == 4}},
            }
            monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda value: ksm_readback)
            monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: ksm_readback)
            ksm_result = plugin.apply(ksm_command)
            assert ksm_result['success'] is True, ksm_result
            assert plugin._load_operation(ksm_command)['stage'] == 'APPLIED'
            assert plugin._get_active_control() == ksm_command['operationUuid']
        elif tamper in ('active_prepared_backend_ksm',
                        'active_prepared_backend_ksm_wrong_resource',
                        'active_prepared_backend_ksm_wrong_capacity',
                        'active_prepared_backend_ksm_wrong_boot',
                        'active_prepared_backend_ksm_enabled',
                        'active_prepared_backend_ksm_clear',
                        'active_prepared_backend_ksm_clear_config_drift',
                        'active_prepared_backend_ksm_clear_seal_config_drift',
                        'active_prior_preparation_ksm',
                        'active_prior_preparation_wrong_uuid',
                        'active_prior_preparation_wrong_capacity',
                        'active_prior_preparation_wrong_boot',
                        'active_prior_preparation_enabled',
                        'active_prior_preparation_bad_current_receipt'):
            # Effective KSM applies retain the prepared writeback target as
            # disabled metadata in the active control record.
            ksm_readback = {'run': '1', 'configRevision': '4',
                            'pages_to_scan': '200', 'sleep_millisecs': '40',
                            'use_zero_pages': '0'}
            monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda value: ksm_readback)
            monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: ksm_readback)
            active_backend_uuid = ('e' * 32 if
                                   tamper in ('active_prepared_backend_ksm_wrong_resource',
                                              'active_prior_preparation_wrong_uuid')
                                   else 'd' * 32 if tamper.startswith('active_prior_preparation_')
                                   else resource_uuid)
            active_capacity = (request['backend_capacity_bytes'] + 1 if
                               tamper in ('active_prepared_backend_ksm_wrong_capacity',
                                          'active_prior_preparation_wrong_capacity')
                               else request['backend_capacity_bytes'])
            active_ksm_policy = ({} if tamper.startswith('active_prior_preparation_') else {
                'enabled': True, 'pagesToScan': 200,
                'sleepMillis': 40, 'zeroPagesEnabled': False})
            if tamper in ('active_prepared_backend_ksm_clear',
                          'active_prepared_backend_ksm_clear_config_drift',
                          'active_prepared_backend_ksm_clear_seal_config_drift'):
                active_ksm_policy = {'zeroPagesEnabled': False}
            active_writeback_enabled = False
            ksm_command = {
                'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                'operationUuid': '6' * 32, 'desiredRevision': 4,
                'policyMode': 'effective',
                'policy': {
                    'schemaVersion': 1,
                    'ksm': active_ksm_policy,
                    'writeback': {
                        'enabled': active_writeback_enabled,
                        'backendResourceUuid': active_backend_uuid,
                        'backendCapacityBytes': active_capacity},
                },
            }
            ksm_result = plugin.apply(ksm_command)
            assert ksm_result['success'] is True and ksm_result['status'] == 'Succeeded', ksm_result
            active_record = plugin._load_operation(ksm_command)
            if tamper in ('active_prepared_backend_ksm_enabled',
                          'active_prior_preparation_enabled'):
                active_record['policy']['writeback']['enabled'] = True
                active_record['policyHash'] = plugin._policy_digest(active_record['policy'])
                assert plugin._write_operation_record(active_record)
            if tamper in ('active_prepared_backend_ksm_wrong_boot',
                          'active_prior_preparation_wrong_boot'):
                active_record['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
                assert plugin._write_operation_record(active_record)
            assert active_record['readback']['state']['ksmOnly'] is True
            assert active_record['policy']['writeback']['enabled'] is (
                tamper in ('active_prepared_backend_ksm_enabled',
                           'active_prior_preparation_enabled'))
            assert plugin._get_active_control() == ksm_command['operationUuid']
            if tamper == 'active_prepared_backend_ksm':
                preparation_record = plugin._load_operation(preparation_command)
                preparation_evidence = plugin._completed_backend_preparation_evidence(
                    preparation_id, preparation_record, HOST, boot_id)
                assert preparation_evidence is not None
                assert active_record.get('policyHash') == plugin._policy_digest(
                    active_record['policy']), (active_record.get('policyHash'),
                                                plugin._policy_digest(active_record['policy']))
                assert plugin._first_use_backend_bound_ksm_record(
                    active_record,
                    {preparation_id: preparation_record},
                    expected_boot=boot_id, expected_operation=ksm_command['operationUuid'],
                    expected_resource_uuid=resource_uuid,
                    expected_capacity=request['backend_capacity_bytes']) is True, (
                        active_record.get('policy'), active_record.get('policyHash'),
                        active_record.get('readback'), preparation_evidence.get('receipt'),
                        preparation_evidence.get('request'))
            if tamper.startswith('active_prior_preparation_'):
                preparation_command['expectedControlOperationUuid'] = ksm_command['operationUuid']
                saved_preparation = plugin._load_operation(preparation_command)
                saved_preparation['expectedControlOperationUuid'] = ksm_command['operationUuid']
                saved_preparation['requestHash'] = plugin._operation_hash(preparation_command)
                assert plugin._write_operation_record(saved_preparation)
                with open(paths['intentPath'], 'r') as stream:
                    saved_intent = json.load(stream)
                saved_intent['controlOperationUuid'] = ksm_command['operationUuid']
                saved_intent['requestHash'] = saved_preparation['requestHash']
                with open(paths['intentPath'], 'w') as stream:
                    json.dump(saved_intent, stream, sort_keys=True)
        elif tamper == 'non_ksm_after_ksm_prepare':
            registration = {
                'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                'operationUuid': '2' * 32, 'desiredRevision': 2,
                'policyMode': 'delta',
                'policy': {'writeback': {
                    'enabled': False, 'backendResourceUuid': resource_uuid,
                    'backendCapacityBytes': request['backend_capacity_bytes']}},
            }
            registration_result = plugin.apply(registration)
            assert registration_result['success'] is True, registration_result
            assert plugin._get_active_control() == registration['operationUuid']
        if tamper in ('active_prepared_backend_ksm',
                      'active_prepared_backend_ksm_clear',
                      'active_prepared_backend_ksm_clear_config_drift'):
            # Exercise the real no-pool admission and inventory decorator with
            # the prepared-backend KSM active record, not only the proof helper.
            monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: 'active')
            inventory = plugin._fresh_backend_maintenance_inventory(HOST)
            assert inventory['poolGeneration'] == 'none', inventory
            assert plugin._first_use_no_pool_verified() is True
            if tamper in ('active_prepared_backend_ksm_clear',
                          'active_prepared_backend_ksm_clear_config_drift'):
                clear_command = {
                    'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                    'operationUuid': '7' * 32, 'desiredRevision': 5,
                    'policyMode': 'effective',
                    'policy': {'schemaVersion': 1, 'ksm': {}, 'writeback': {
                        'enabled': False,
                        'backendResourceUuid': resource_uuid,
                        'backendCapacityBytes': request['backend_capacity_bytes'],
                    }},
                }

                # Exercise the real clear path and its managed-config identity
                # check. Stub only native/service leaves so drift is rejected
                # before any KSM write or restart.
                monkeypatch.delattr(plugin, '_apply_ksm_policy')
                expected_config = {
                    'CONFIG_REVISION': 4, 'KSM_NPAGES_MIN': 200,
                    'KSM_NPAGES_MAX': 200, 'KSM_NPAGES_BOOST': 0,
                    'KSM_NPAGES_DECAY': 0, 'KSM_SLEEP_MSEC': 40,
                    'KSM_THRES_COEF': 100, 'KSM_THRES_CONST': 2048,
                }
                config_identity = dict(expected_config)
                if tamper in ('active_prepared_backend_ksm_clear_config_drift',
                              'active_prepared_backend_ksm_clear_seal_config_drift'):
                    config_identity['CONFIG_REVISION'] = 3
                monkeypatch.setattr(plugin, '_managed_ksm_config_identity',
                                    lambda: dict(config_identity))
                monkeypatch.setattr(plugin, '_native_sleep_for_policy', lambda value: value)
                monkeypatch.setattr(plugin, '_verify_native_ksm_profile', lambda: None)
                monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: '0')
                monkeypatch.setattr(plugin, '_native_service_state',
                                    lambda unit, state: 'active' if state == 'active' else 'enabled')
                native_writes = []
                published = []
                monkeypatch.setattr(plugin, '_publish_ksm_config',
                                    lambda content: (published.append(content), native_writes.append('config')))
                monkeypatch.setattr(plugin, '_write_ksm_sysfs',
                                    lambda name, value: native_writes.append((name, value)))
                monkeypatch.setattr(memory_optimization_module.subprocess, 'check_call',
                                    lambda argv: native_writes.append(tuple(argv)))
                updated_ack = dict(ksm_readback, configRevision='5')
                monkeypatch.setattr(plugin, '_read_ksm_ack',
                                    lambda: updated_ack if published else dict(ksm_readback))

                if tamper == 'active_prepared_backend_ksm_clear_config_drift':
                    # Check the ordinary clear before introducing the separate
                    # rejected-operation journal used by the seal scenario.
                    drift_result = plugin.apply(clear_command)
                    assert drift_result['success'] is False, drift_result
                    assert drift_result['status'] == 'Unknown', drift_result
                    assert drift_result['reasonCode'] == 'KSM_CLEAR_CONFIG_ACK_MISMATCH'
                    assert native_writes == [] and not published
                    assert plugin._get_active_control() == ksm_command['operationUuid']
                    return

                # Seal the real pre-write KSM-clear rejection while the
                # active control still has zeroPagesEnabled=false and the
                # prepared B binding. This matches the reported active state; the
                # second seal below additionally covers the later empty KSM
                # control after the ordinary clear succeeds.
                active_rejected = {
                    'hostUuid': HOST, 'scope': 'Host', 'resourceUuid': HOST,
                    'action': 'apply', 'operationUuid': '9' * 32,
                    'desiredRevision': 5, 'policyMode': 'effective',
                    'policy': {'schemaVersion': 1, 'ksm': {}, 'writeback': {
                        'enabled': False,
                        'backendResourceUuid': resource_uuid,
                        'backendCapacityBytes': request['backend_capacity_bytes'],
                    }},
                }
                active_submitted_at = int(time.time() * 1000)
                assert plugin._record_operation(active_rejected, 'UNKNOWN', {
                    'reason': 'KSM_CLEAR_PRIOR_JOURNAL_INVALID'})
                active_before = plugin._load_operation(active_rejected)
                assert ksm_command['policy']['ksm'] == {'zeroPagesEnabled': False}
                assert plugin._get_active_control() == ksm_command['operationUuid']
                state_reads[0] = 0
                active_reconcile = {
                    'hostUuid': HOST, 'scope': 'Host', 'resourceUuid': HOST,
                    'action': 'reconcile', 'operationUuid': active_rejected['operationUuid'],
                    'desiredRevision': active_rejected['desiredRevision'], 'policy': {},
                    'expectedControlOperationUuid': active_rejected['operationUuid'],
                    'reconcileAction': 'seal-if-never-issued',
                    'taskSubmittedAt': active_submitted_at, 'bootId': boot_id,
                }
                active_result = json.loads(plugin.reconcile({
                    'body': json.dumps(active_reconcile)}))
                active_after = plugin._load_operation(active_rejected)
                if tamper == 'active_prepared_backend_ksm_clear_seal_config_drift':
                    # A stale managed block cannot prove ownership for sealing
                    # the rejection either; preserve the original Unknown.
                    assert active_result['status'] == 'Unknown', active_result
                    assert active_result['reasonCode'] == 'FIRST_ZRAM_LOCAL_CONTROL_FENCED'
                    assert active_after == active_before
                    assert native_writes == [] and not published
                    assert service_policy_calls == []
                    return
                assert active_result['status'] == 'Failed', active_result
                assert active_result['reasonCode'] == 'FIRST_ZRAM_ADMISSION_NOT_ISSUED'
                assert active_after['stage'] == 'NOT_ISSUED'
                assert active_after['policy'] == active_before['policy']
                assert active_after['applyEvidence'] == active_before['applyEvidence']
                assert plugin._get_active_control() == ksm_command['operationUuid']
                assert native_writes == [] and not published
                assert service_policy_calls == []
                active_read_count = state_reads[0]
                assert json.loads(plugin.reconcile({
                    'body': json.dumps(active_reconcile)})) == dict(
                        active_result, state=dict(active_result['state'],
                                                  controlOperationUuid=ksm_command['operationUuid']))
                assert state_reads[0] == active_read_count
                assert plugin.apply(active_rejected) == active_after['readback']
                assert plugin._load_operation(active_rejected) == active_after
                assert plugin._get_active_control() == ksm_command['operationUuid']
                assert native_writes == [] and not published

                clear_result = plugin.apply(clear_command)
                assert clear_result['success'] is True, clear_result
                assert clear_result['status'] == 'Succeeded', clear_result
                assert plugin._load_operation(clear_command)['stage'] == 'APPLIED'
                assert plugin._get_active_control() == clear_command['operationUuid']
                assert published and native_writes
                assert service_policy_calls == []
                # The successful clear advanced the actual managed block and
                # its KSM receipt together; keep the subsequent readonly seal
                # observation consistent with that post-write state.
                config_identity['CONFIG_REVISION'] = 5
                with open(config_path, 'r') as stream:
                    assert json.load(stream)['backend'] == prepared_config['backend']
                # A later ordinary clear can be rejected before any KSM write
                # even though the active control retains the prepared B
                # binding. Reconcile that exact journal through the public
                # handler and require the complete existing preparation/ACK
                # proof; this is not a generic unknown-operation shortcut.
                rejected_command = {
                    'hostUuid': HOST, 'scope': 'Host', 'resourceUuid': HOST,
                    'action': 'apply', 'operationUuid': '8' * 32,
                    'desiredRevision': 15, 'policyMode': 'effective',
                    'policy': {'schemaVersion': 1, 'ksm': {}, 'writeback': {
                        'enabled': False,
                        'backendResourceUuid': resource_uuid,
                        'backendCapacityBytes': request['backend_capacity_bytes'],
                    }},
                }
                rejected_submitted_at = int(time.time() * 1000)
                assert plugin._record_operation(rejected_command, 'UNKNOWN', {
                    'reason': 'KSM_CLEAR_PRIOR_JOURNAL_INVALID'})
                rejected_before = plugin._load_operation(rejected_command)
                state_reads[0] = 0
                reconcile_reads = []

                def reconcile_service(action, payload):
                    reconcile_reads.append(action)
                    if action == 'state':
                        return native_state('observe', False)
                    if action == 'host-cpu-state':
                        return {'efficiency_enabled': False, 'revision': 1}
                    raise AssertionError('prewrite reconciliation issued %s' % action)

                plugin.service_call = reconcile_service
                rejected_reconcile = {
                    'hostUuid': HOST, 'scope': rejected_command['scope'],
                    'resourceUuid': rejected_command['resourceUuid'],
                    'action': 'reconcile', 'operationUuid': rejected_command['operationUuid'],
                    'desiredRevision': rejected_command['desiredRevision'], 'policy': {},
                    'expectedControlOperationUuid': rejected_command['operationUuid'],
                    'reconcileAction': 'seal-if-never-issued',
                    'taskSubmittedAt': rejected_submitted_at, 'bootId': boot_id,
                }
                rejected_result = json.loads(plugin.reconcile({
                    'body': json.dumps(rejected_reconcile)}))
                rejected_after = plugin._load_operation(rejected_command)
                assert rejected_result['status'] == 'Failed', rejected_result
                assert rejected_result['reasonCode'] == 'FIRST_ZRAM_ADMISSION_NOT_ISSUED'
                assert rejected_result['state']['policyWritesIssued'] is False
                assert rejected_result['state']['controlOperationUuid'] == clear_command['operationUuid']
                assert rejected_after['stage'] == 'NOT_ISSUED'
                assert rejected_after['requestHash'] == rejected_before['requestHash']
                assert rejected_after['policy'] == rejected_before['policy']
                assert rejected_after['applyEvidence'] == rejected_before['applyEvidence']
                assert plugin._get_active_control() == clear_command['operationUuid']
                with open(config_path, 'r') as stream:
                    assert json.load(stream)['backend'] == prepared_config['backend']
                assert len(reconcile_reads) == 2
                read_count = len(reconcile_reads)
                assert json.loads(plugin.reconcile({
                    'body': json.dumps(rejected_reconcile)})) == rejected_result
                assert len(reconcile_reads) == read_count
                write_count = len(native_writes)
                publish_count = len(published)
                assert service_policy_calls == []

                replay_result = plugin.apply(rejected_command)
                assert replay_result == rejected_after['readback']
                assert plugin._load_operation(rejected_command) == rejected_after
                assert plugin._get_active_control() == clear_command['operationUuid']
                assert len(native_writes) == write_count
                assert len(published) == publish_count
                assert service_policy_calls == []
                return
        if (isinstance(tamper, str) and
                tamper.startswith('active_prior_preparation_')):
            expected = tamper == 'active_prior_preparation_ksm'
            try:
                verified_no_pool = plugin._first_use_no_pool_verified()
            except RuntimeError as exc:
                assert str(exc) == 'FIRST_ZRAM_BACKEND_PREPARATION_UNPROVEN'
                verified_no_pool = False
            assert verified_no_pool is expected
            no_pool = {
                'host_zram': {'pool_generation': '', 'device': '',
                              'quality': 'unavailable',
                              'reason': 'NO_QUALIFIED_MANAGED_POOL:first-use'},
                'backend_resource': service_backend['backend_resource'],
            }
            def readonly_query(action, payload):
                if action == 'host-cpu-state':
                    return {'efficiency_enabled': False, 'revision': 1}
                if action == 'backend-state':
                    return no_pool
                return service_detail

            monkeypatch.setattr(plugin, '_readonly_query', readonly_query)
            monkeypatch.setattr(plugin, '_service_unit_stopped', lambda: True)
            monkeypatch.setattr(plugin, '_zram_pool_preparation_eligibility', lambda host_uuid: {
                'hostUuid': host_uuid, 'bootId': boot_id, 'poolGeneration': 'none',
                'controlOperationUuid': active_record['operationUuid'],
                'canPrepareZramPool': False,
                'zramPoolPreparationReasons': ['MEMORY_SERVICE_NOT_STOPPED'],
                'zramPoolPreparationQuality': 'Ineligible',
                'zramPoolPreparationObservedAt': '2026-10-17T00:00:00Z',
            })
            monkeypatch.setattr(
                memory_optimization_module, 'probe_writeback_backends',
                lambda host_uuid, backend, config: _probe_block_inventory(
                    boot_id, service_backend=backend, service_config=config))
            inventory_result = json.loads(plugin.writeback_backends({
                'body': json.dumps({'hostUuid': HOST})}))
            if expected:
                assert inventory_result['success'] is True, inventory_result
                assert inventory_result['state']['poolGeneration'] == 'none'
            else:
                assert inventory_result['success'] is False, inventory_result
                assert inventory_result['status'] == 'Unknown', inventory_result
                assert inventory_result['reason'] == 'FIRST_ZRAM_BACKEND_PREPARATION_UNPROVEN'
                assert inventory_result['state'] == {}
            return
        if tamper in ('prepared_backend_observation_reconcile',
                      'prepared_backend_observation_bad_receipt_reconcile'):
            # Exercise the normal public reconcile wire for a same-boot
            # pre-write UNKNOWN while the complete prepared-B proof remains
            # available. Reconcile may seal only the exact valid proof; it
            # must not replay the original apply or mutate config/device state.
            if tamper == 'prepared_backend_observation_bad_receipt_reconcile':
                live_receipt['stage'] = 'FAILED_REQUIRES_REVIEW'
            submitted_at = int(time.time() * 1000) - 1000
            assert plugin._record_operation(command, 'UNKNOWN', {
                'reason': 'FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE'})
            before = plugin._load_operation(command)
            config_before_seal = config_path.read_bytes()
            active_before_seal = plugin._get_active_control()
            reconcile_command = {
                'hostUuid': HOST, 'scope': 'Host', 'resourceUuid': HOST,
                'action': 'reconcile', 'operationUuid': command['operationUuid'],
                'desiredRevision': command['desiredRevision'], 'policy': {},
                'reconcileAction': 'seal-if-never-issued',
                'taskSubmittedAt': submitted_at, 'bootId': boot_id,
            }
            state_reads[0] = 0
            result = json.loads(plugin.reconcile({'body': json.dumps(reconcile_command)}))
            after = plugin._load_operation(command)
            assert config_path.read_bytes() == config_before_seal
            assert plugin._get_active_control() == active_before_seal
            assert not restarts and not service_policy_calls
            if tamper == 'prepared_backend_observation_bad_receipt_reconcile':
                assert result['status'] == 'Unknown', result
                assert after == before
            else:
                assert result['status'] == 'Failed', result
                assert result['reasonCode'] == 'FIRST_ZRAM_ADMISSION_NOT_ISSUED', result
                assert result['state']['policyWritesIssued'] is False
                assert after['stage'] == 'NOT_ISSUED'
                assert after['policy'] == before['policy']
                assert after['policyHash'] == before['policyHash']
                assert after['requestHash'] == before['requestHash']
                assert after['applyEvidence'] == before['applyEvidence']
                reads_before_replay = state_reads[0]
                assert json.loads(plugin.reconcile({
                    'body': json.dumps(reconcile_command)})) == result
                assert state_reads[0] == reads_before_replay
                assert result['state']['controlOperationUuid'] == (plugin._get_active_control() or '')
                assert plugin.apply(command) == after['readback']
                assert plugin._load_operation(command) == after
            return
        result = plugin.apply(command)
        if tamper in ('ordinary_registration', 'non_ksm_after_ksm_prepare',
                      'active_prepared_backend_ksm_wrong_resource',
                      'active_prepared_backend_ksm_wrong_capacity',
                      'active_prepared_backend_ksm_wrong_boot',
                      'active_prepared_backend_ksm_enabled'):
            assert result['success'] is False and result['status'] == 'Unknown', result
            assert result['reasonCode'] == 'FIRST_ZRAM_BACKEND_PREPARATION_UNPROVEN'
            assert config_path.read_bytes() == config_bytes_before_apply
            assert restarts == []
            return
        if tamper == 'corrupt_historical_preparation':
            assert result['success'] is False and result['status'] == 'Unknown', result
            assert result['reasonCode'] == 'FIRST_ZRAM_LOCAL_CONTROL_FENCED'
            assert config_path.read_bytes() == (json.dumps(
                prepared_config, sort_keys=True, indent=2) + '\n').encode('utf-8')
            assert restarts == []
            return
        assert result['success'] is True and result['status'] == 'Succeeded', result
        assert plugin._load_operation(command)['stage'] == 'APPLIED'
        if tamper == 'late_host_uuid':
            assert plugin._load_operation(command)['firstZramUse']['hostUuid'] == HOST
        assert len(service_policy_calls) == 1
    elif tamper == 'non_backend_config':
        with pytest.raises(memory_optimization_module.FirstZramConfigRejected,
                           match='FIRST_ZRAM_CONFIG_NOT_FACTORY'):
            plugin._prepare_first_zram_use(command)
        assert restarts == []
        # A config past factory mode, such as an admitted first use waiting
        # for its pool, is no no-pool proof; the inventory stays readable.
        assert plugin._first_use_no_pool_verified() is False
        inventory = json.loads(plugin.writeback_backends({'body': json.dumps({'hostUuid': HOST})}))
        assert inventory['success'] is True, inventory
        assert inventory['state']['canPrepare'] is False
        return
    else:
        expected_reason = ('FIRST_ZRAM_CONFIG_READBACK_MISMATCH'
                           if tamper == 'config_changed_before_cas'
                           else 'FIRST_ZRAM_BACKEND_PREPARATION_UNPROVEN')
        with pytest.raises(RuntimeError, match=expected_reason):
            plugin._prepare_first_zram_use(command)
        if tamper != 'config_changed_before_cas':
            assert config_path.read_bytes() == config_bytes_before_apply
        else:
            assert json.loads(config_path.read_text())['unexpected'] is True
        assert restarts == []
        return
    with open(config_path, 'r') as stream:
        activated_config = json.load(stream)
    assert activated_config['backend'] == prepared_config['backend']
    assert activated_config['mode'] == 'reclaim'
    assert activated_config['resource_authorized'] is True
    assert restarts == [True]


@pytest.mark.parametrize('zram,writeback,cpu_enabled,native_writeback_enabled', [
    ({'enabled': False}, None, False, False),
    ({'cpuThresholdPercent': 5}, None, False, False),
    ({}, {'enabled': False}, False, False),
    ({'enabled': True}, None, False, False),
    ({}, None, True, False),
    ({'enabled': False}, None, True, True),
])
def test_explicit_cpu_policy_or_guard_requires_its_real_cpu_receipt(
        tmp_path, zram, writeback, cpu_enabled, native_writeback_enabled):
    plugin, state, calls, _, applied = _capacity_apply_fixture(
        tmp_path, zram=zram, writeback=writeback, cpu_enabled=cpu_enabled,
        native_writeback_enabled=native_writeback_enabled)
    assert [payload for action, payload in calls if action == 'host-cpu']
    if native_writeback_enabled:
        assert state['tuning']['settings']['writeback']['enabled'] is True
        assert state['cpu']['efficiency_enabled'] is True
    record = _journal(plugin)
    sections = record['applyEvidence']['state']['sections']
    assert 'cpu' in sections
    if cpu_enabled:
        assert 'cpuGuard' in sections
    result = _reconcile(plugin)
    # Valid CPU evidence remains subject to the same strict capacity proof.
    assert result['status'] == 'Blocked', result

    sections.pop('cpu')
    _write_journal(plugin, record)
    missing_receipt = _reconcile(plugin)
    assert missing_receipt['status'] == 'Unknown'


@pytest.mark.parametrize('corruption', [
    'capacity_receipt_missing', 'wrong_operation_identity', 'different_boot',
    'capacity_receipt_revision', 'capacity_current_revision', 'cpu_current_revision',
    'cpu_current_value', 'tuning_current_revision', 'cpu_readback_missing',
    'cpu_section_incomplete', 'tuning_section_incomplete',
    'cpu_before_revision', 'cpu_original_revision', 'cpu_original_value',
    'unexpected_cpu_receipt', 'unexpected_guard',
])
def test_capacity_blocker_requires_current_operation_bound_readback(
        tmp_path, corruption):
    plugin, state, _, _, applied = _capacity_apply_fixture(tmp_path)
    assert applied['status'] == 'Draining'
    record = _journal(plugin)
    sections = record['applyEvidence']['state']['sections']
    if corruption == 'capacity_receipt_missing':
        sections.pop('capacity')
    elif corruption == 'wrong_operation_identity':
        record['applyEvidence']['operationUuid'] = 'another-operation'
    elif corruption == 'different_boot':
        record['bootId'] = 'different-boot'
    elif corruption == 'capacity_receipt_revision':
        sections['capacityReadback']['revision'] += 1
    elif corruption == 'capacity_current_revision':
        state['capacity']['revision'] += 1
    elif corruption == 'cpu_current_revision':
        state['cpu']['revision'] += 1
    elif corruption == 'cpu_current_value':
        state['cpu']['efficiency_enabled'] = True
    elif corruption == 'tuning_current_revision':
        state['tuning']['revision'] += 1
    elif corruption == 'cpu_readback_missing':
        sections.pop('cpuReadback')
    elif corruption == 'cpu_section_incomplete':
        record['applyEvidence']['state'].setdefault('sectionComplete', {}).pop('cpu', None)
    elif corruption == 'tuning_section_incomplete':
        record['applyEvidence']['state'].setdefault('sectionComplete', {}).pop('tuning', None)
    elif corruption == 'cpu_before_revision':
        sections['cpuBefore']['revision'] += 1
    elif corruption == 'cpu_original_revision':
        sections['cpuReadback']['revision'] += 1
    elif corruption == 'cpu_original_value':
        sections['cpuReadback']['idle_cpu_threshold_percent'] += 1
    elif corruption == 'unexpected_cpu_receipt':
        sections['cpu'] = None
    elif corruption == 'unexpected_guard':
        sections['cpuGuard'] = sections['cpuReadback'].copy()
    _write_journal(plugin, record)

    result = _reconcile(plugin)
    assert result['status'] == 'Unknown', (corruption, result)


def _owned_backend_identity(boot_id):
    return {
        'boot_id': boot_id, 'canonical_device': '/dev/vdb', 'rdev': 64769,
        'node_inode': 12345, 'sysfs_inode': 54321,
        'capacity_bytes': 1024 * 1024 * 1024,
    }


class _WritebackProbeFilesystem(object):
    def __init__(self, boot_id, holders=()):
        self.boot_id = boot_id
        self.holders = list(holders)
        self.sysfs_path = '/sys/devices/pci0000:00/block/vdb'

    def read(self, path):
        values = {
            '/proc/sys/kernel/random/boot_id': self.boot_id,
            '/proc/self/mountinfo': '',
            '/proc/swaps': 'Filename Type Size Used Priority\n',
        }
        if path not in values:
            raise IOError(path)
        return values[path]

    def listdir(self, path):
        if path == '/dev/disk/by-id':
            return ['scsi-BACKEND-SERIAL123']
        if path == os.path.join(self.sysfs_path, 'holders'):
            return list(self.holders)
        if path == os.path.join(self.sysfs_path, 'slaves'):
            return []
        raise IOError(path)

    def realpath(self, path):
        if path == '/dev/disk/by-id/scsi-BACKEND-SERIAL123':
            return '/dev/vdb'
        if path == '/sys/dev/block/8:1':
            return self.sysfs_path
        return path

    def stat(self, path):
        if path == '/dev/vdb':
            return type('Stat', (), {'st_rdev': 64769, 'st_ino': 12345})()
        if path == self.sysfs_path:
            return type('Stat', (), {'st_ino': 54321})()
        raise IOError(path)

    def exists(self, path):
        return False


def _probe_block_inventory(boot_id, holders=(), service_backend=None, service_config=None):
    filesystem = _WritebackProbeFilesystem(boot_id, holders)

    def runner(argv, timeout=5):
        if argv[0] == 'lsblk':
            row = {'NAME': '/dev/vdb', 'KNAME': 'vdb', 'TYPE': 'disk',
                   'SIZE': 1024 * 1024 * 1024, 'MAJ:MIN': '8:1',
                   'SERIAL': 'SERIAL123', 'TRAN': 'virtio', 'RO': False, 'RM': False}
            return {'returncode': 0,
                    'stdout': json.dumps({'blockdevices': [row]}), 'stderr': ''}
        if argv[0] == 'blkid':
            return {'returncode': 2, 'stdout': '', 'stderr': ''}
        raise AssertionError('unexpected probe command: %s' % argv)

    return real_probe_writeback_backends(
        HOST, service_backend=service_backend, service_config=service_config,
        runner=runner, filesystem=filesystem)


@pytest.mark.parametrize('history', ['trusted_ksm', 'stale_ksm', 'wrong_boot_ksm',
                                    'cleared_ksm', 'cleared_ksm_reboot',
                                    'cleared_ksm_missing_ack', 'cleared_ksm_missing_boot',
                                    'cleared_ksm_unknown', 'cleared_ksm_mixed',
                                    'cleared_ksm_delta', 'cleared_ksm_extra_policy',
                                    'cleared_ksm_readback_uuid', 'cleared_ksm_invalid_boot',
                                    'cleared_ksm_schema_v1', 'cleared_ksm_schema_v2',
                                    'cleared_ksm_schema_bool', 'cleared_ksm_schema_float',
                                    'active_service_disable',
                                    'active_service_disable_previous_boot',
                                    'active_service_disable_cpu_mismatch',
                                    'active_service_disable_tuning_mismatch',
                                    'ordinary_host', 'unknown', 'old_zram'])
def test_cold_backend_inventory_requires_complete_proof_for_active_ksm_control(
        tmp_path, monkeypatch, history):
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    assert boot_id
    operation_dir = tmp_path / 'operations'
    operation_dir.mkdir()
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps({
        'state_dir': str(state_dir), 'device': '/dev/zram0',
        'initial_efficiency_enabled': False, 'backend': {},
    }))
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainConfig': str(config_path)})
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    live_ksm_ack = {'run': '1', 'configRevision': '3', 'pages_to_scan': '100',
                    'sleep_millisecs': '20', 'use_zero_pages': '0'}
    monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: dict(live_ksm_ack))
    monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda command: {
        'run': '1', 'configRevision': '3', 'pages_to_scan': '100',
        'sleep_millisecs': '20', 'use_zero_pages': '0'})
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'ksmZeroPages': True,
        'zram': True, 'writeback': True})
    if history in ('trusted_ksm', 'stale_ksm', 'wrong_boot_ksm') or history.startswith('cleared_ksm'):
        ksm_command = {
            'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
            'operationUuid': '3' * 32, 'desiredRevision': 3,
            'policyMode': 'delta',
            'policy': {'ksm': {'enabled': True, 'pagesToScan': 100,
                               'sleepMillis': 20, 'zeroPagesEnabled': False}},
        }
        result = plugin.apply(ksm_command)
        assert result['success'] is True and result['status'] == 'Succeeded', result
        if history == 'stale_ksm':
            live_ksm_ack['pages_to_scan'] = '101'
        elif history == 'wrong_boot_ksm':
            record = plugin._load_operation(ksm_command)
            record['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
            assert plugin._write_operation_record(record)
        elif history.startswith('cleared_ksm'):
            # Exercise the existing effective empty-target apply, not a
            # hand-written claim that an arbitrary old operation was safe.
            ksm_command = dict(ksm_command, operationUuid='5' * 32,
                               policyMode='effective', policy={'ksm': {}})
            if history == 'cleared_ksm_schema_v1':
                ksm_command['policy']['schemaVersion'] = 1
            result = plugin.apply(ksm_command)
            assert result['success'] is True and result['status'] == 'Succeeded', result
            record = plugin._load_operation(ksm_command)
            assert record['readback']['state']['ksmOnly'] is True
            live_ksm_ack['pages_to_scan'] = '101'
            if history == 'cleared_ksm_reboot':
                boot_id = 'fedcba98-7654-3210-fedc-ba9876543210'
            elif history == 'cleared_ksm_missing_ack':
                del record['readback']['ksmReadback']['pages_to_scan']
            elif history == 'cleared_ksm_missing_boot':
                del record['bootId']
            elif history == 'cleared_ksm_unknown':
                record['stage'] = 'UNKNOWN'
            elif history == 'cleared_ksm_mixed':
                record['policy']['zram'] = {'enabled': True}
            elif history == 'cleared_ksm_delta':
                record['policyMode'] = 'delta'
            elif history == 'cleared_ksm_extra_policy':
                record['policy']['unexpected'] = {}
            elif history == 'cleared_ksm_readback_uuid':
                record['readback']['operationUuid'] = '6' * 32
            elif history == 'cleared_ksm_invalid_boot':
                record['bootId'] = 'not-a-boot-id'
            elif history == 'cleared_ksm_schema_v2':
                record['policy']['schemaVersion'] = 2
            elif history == 'cleared_ksm_schema_bool':
                record['policy']['schemaVersion'] = True
            elif history == 'cleared_ksm_schema_float':
                record['policy']['schemaVersion'] = 1.0
            assert plugin._write_operation_record(record)
    elif history.startswith('active_service_disable'):
        disabled_plugin, _, _, _, disabled_result = _capacity_apply_fixture(
            tmp_path / 'disabled-service', writeback={'enabled': False},
            capacity_requested=False, include_zram=False)
        assert disabled_result['status'] == 'Succeeded', disabled_result
        disabled_record = _journal(disabled_plugin)
        if history == 'active_service_disable_previous_boot':
            disabled_record['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
        assert plugin._write_operation_record(disabled_record)
        plugin._set_active_control(disabled_record['operationUuid'])
        sections = disabled_record['readback']['state']['sections']
        cpu_readback = plugin._strict_service_success(
            'host-cpu-state', sections['cpuReadback'])
        tuning_readback = plugin._strict_service_success(
            'tuning-state', sections['tuningReadback'])
        if history == 'active_service_disable_cpu_mismatch':
            cpu_readback = dict(cpu_readback, efficiency_enabled=True)
        elif history == 'active_service_disable_tuning_mismatch':
            tuning_readback = dict(tuning_readback, settings={'writeback': {'enabled': True}})
        monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: 'active')
        monkeypatch.setattr(plugin, '_service_request', lambda action, payload:
                            cpu_readback if action == 'host-cpu-state' else tuning_readback)
    else:
        operation_uuid = '4' * 32
        policy = ({'zram': {'enabled': True}} if history == 'old_zram' else
                  {'zram': {'enabled': False}})
        command = {
            'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
            'operationUuid': operation_uuid, 'desiredRevision': 4,
            'policyMode': 'delta', 'policy': policy,
        }
        status_value = 'Unknown' if history == 'unknown' else 'Succeeded'
        readback = {'success': status_value == 'Succeeded', 'status': status_value,
                    'operationUuid': operation_uuid, 'appliedRevision': 4,
                    'state': {'phase': 'UNKNOWN' if status_value == 'Unknown' else 'APPLIED'}}
        assert plugin._record_operation(
            command, 'UNKNOWN' if status_value == 'Unknown' else 'APPLIED', readback)
        if history in ('ordinary_host', 'unknown'):
            plugin._set_active_control(operation_uuid)

    real_open = open

    native_values = {
        '/proc/swaps': 'Filename Type Size Used Priority\n',
        '/sys/block/zram0/disksize': '0\n',
        '/sys/block/zram0/mm_stat': '0 0 0 0 0 0 0 0\n',
        '/sys/block/zram0/backing_dev': 'none\n',
    }

    def first_use_open(path, mode='r', *args, **kwargs):
        if path in native_values:
            return io.StringIO(native_values[path])
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr('builtins.open', first_use_open)
    monkeypatch.setattr(plugin, '_service_unit_stopped', lambda: True)
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt', lambda: (None, None))
    status = {'host_zram': {
        'pool_generation': '', 'device': '', 'quality': 'unavailable',
        'reason': 'NO_QUALIFIED_MANAGED_POOL:first-use'},
        'backend_resource': None}
    detail = {'claimed': False, 'identity_qualified': False,
              'configured': {}, 'effective': {}}
    monkeypatch.setattr(plugin, '_readonly_query', lambda action, payload:
                        status if action == 'backend-state' else detail)
    monkeypatch.setattr(
        memory_optimization_module, 'probe_writeback_backends',
        lambda host_uuid, backend, config: _probe_block_inventory(
            boot_id, service_backend=backend, service_config=config))

    before = {path.name: path.read_bytes() for path in operation_dir.iterdir()
              if path.is_file()}
    inventory = plugin._fresh_backend_maintenance_inventory(HOST)
    assert before == {path.name: path.read_bytes() for path in operation_dir.iterdir()
                      if path.is_file()}
    if history in ('trusted_ksm', 'cleared_ksm', 'cleared_ksm_reboot',
                    'cleared_ksm_schema_v1', 'active_service_disable',
                    'active_service_disable_previous_boot'):
        assert plugin._first_use_no_pool_verified() is True
        if history.startswith('active_service_disable'):
            assert inventory['controlOperationUuid'] == disabled_record['operationUuid']
        else:
            assert inventory['controlOperationUuid'] == ksm_command['operationUuid']
        assert inventory['poolGeneration'] == 'none'
        assert inventory['canPrepare'] is True, inventory['preparationReasons']
        candidate = inventory['candidates'][0]
        assert candidate['eligible'] is True
        assert candidate['state'] == 'NEEDS_OFFLINE_PREPARATION'
        native_values['/sys/block/zram0/disksize'] = '4096\n'
        assert plugin._first_use_no_pool_verified() is False
        native_values['/sys/block/zram0/disksize'] = '0\n'
        backend_state = state_dir / 'backend-maintenance'
        backend_state.mkdir()
        with open(str(backend_state / 'current.json'), 'w') as stream:
            json.dump({'stage': 'FAILED_REQUIRES_REVIEW'}, stream)
        assert plugin._first_use_no_pool_verified() is False
        (backend_state / 'current.json').unlink()
        backend_state.rmdir()
        (state_dir / 'maintenance').mkdir()
        assert plugin._first_use_no_pool_verified() is False
    else:
        assert plugin._first_use_no_pool_verified() is False
        assert inventory['poolGeneration'] is None
        assert inventory['canPrepare'] is False


@pytest.mark.parametrize('progress', [None, [], 'malformed', {},
                                      {'controllerStop': []},
                                      {'controllerStop': None}])
def test_active_service_disable_rejects_malformed_stop_progress_without_exception(
        tmp_path, monkeypatch, progress):
    plugin, _, _, disabled_command, result = _capacity_apply_fixture(
        tmp_path / 'disabled-service', writeback={'enabled': False},
        capacity_requested=False, include_zram=False)
    assert result['status'] == 'Succeeded'
    record = plugin._load_operation(disabled_command)
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    command = {'hostUuid': HOST, 'scope': 'Host', 'action': 'prepareWritebackBackend',
               'operationUuid': 'f' * 32, 'desiredRevision': 4, 'policy': {}}
    current = {'hostUuid': HOST, 'bootId': boot_id, 'action': 'prepareWritebackBackend',
               'stage': 'PREPARING', 'requestHash': plugin._operation_hash(command),
               'operationUuid': command['operationUuid'],
               'maintenanceProgress': progress}
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    monkeypatch.setattr(plugin, '_load_operation', lambda value: current)
    monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: 'inactive')
    monkeypatch.setattr(plugin, '_first_use_terminal_service_disable', lambda *args: True)
    assert plugin._first_use_active_service_disable_safe(record, command) is False


@pytest.mark.parametrize('bad_readback', [None, [], 'malformed'])
def test_completed_backend_preparation_rejects_malformed_readback_without_exception(
        tmp_path, monkeypatch, bad_readback):
    operation_dir = tmp_path / 'operations'
    operation_dir.mkdir()
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir)})
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    operation_uuid = 'f' * 32
    record = {
        'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
        'scope': 'Host', 'stage': 'APPLIED', 'hostUuid': HOST, 'bootId': boot_id,
        'requestHash': 'a' * 64,
        'maintenanceIntentPath': os.path.join(
            str(operation_dir), 'backend-maintenance', operation_uuid + '.intent.json'),
        'readback': bad_readback,
    }
    assert plugin._write_operation_record(record)
    assert plugin._completed_backend_preparation_evidence(
        operation_uuid, record, HOST, boot_id) is None


@pytest.mark.parametrize('outcome', ['stopped', 'active_writeback_disable',
                                    'active_writeback_disable_after_completed_prepare',
                                    'active_writeback_disable_after_service_disable_prepare',
                                    'active_writeback_disable_after_old_boot_ksm_prepare',
                                    'active_writeback_disable_after_empty_ksm_prepare',
                                    'active_writeback_disable_cpu_drift',
                                    'active_writeback_disable_tuning_drift',
                                    'active_writeback_disable_previous_boot',
                                    'active_writeback_disable_missing_proof',
                                    'cleared_ksm_reboot',
                                    'identity_changed', 'timeout', 'crash_after_stop',
                                    'stale_before_signal',
                                    'candidate_changed_after_stop',
                                    'worker_failed_restore',
                                    'worker_failed_restore_lowercase_error',
                                    'worker_failed_restore_timeout',
                                    'worker_failed_restore_config_changed',
                                    'worker_failed_restore_mismatched_current',
                                    'worker_failed_restore_unknown_worker',
                                    'unsafe_history', 'unsafe_native', 'ineligible_candidate'])
def test_cold_backend_prepare_stops_verified_active_controller_before_worker(
        tmp_path, monkeypatch, outcome):
    worker_failed = outcome.startswith('worker_failed_restore')
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    assert boot_id
    operation_dir = tmp_path / 'operations'
    operation_dir.mkdir()
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps({
        'state_dir': str(state_dir), 'device': '/dev/zram0',
        'initial_efficiency_enabled': False, 'backend': {},
    }))
    template_path = tmp_path / 'config-template.json'
    template_path.write_text(config_path.read_text())
    drain_binary = tmp_path / 'zram-efficiency'
    drain_binary.write_text('test binary boundary')
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainConfig': str(config_path),
                      'drainBinary': str(drain_binary)})
    plugin.zram_config_path = str(config_path)
    plugin.zram_config_template_path = str(template_path)
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    stopped = [False]
    safe_state = {
        'mode': 'observe', 'resource_authorized': False,
        'lifecycle': {'schemaVersion': 1, 'abiProfile': 'zram-service-v1',
                      'readbackAllowed': True, 'paused': False,
                      'activeState': 'compatibility'},
        'maintenance_blocks_activation': False, 'pending_operations': [],
        'host_zram': {'pool_generation': '', 'device': '', 'quality': 'unavailable',
                      'reason': 'NO_QUALIFIED_MANAGED_POOL:first-use'},
        'host': {'qualified': True, 'safe': True, 'observed_at': time.time()},
        'observed_at': time.time(),
    }
    disabled_service_state = {}
    stopped_socket_queries = []
    def service_request(action, payload):
        if stopped[0] and action in ('state', 'host-cpu-state', 'tuning-state'):
            raise IOError('the stopped service socket is unavailable')
        if action == 'host-cpu-state' and disabled_service_state:
            return dict(disabled_service_state['cpu'])
        if action == 'tuning-state' and disabled_service_state:
            return dict(disabled_service_state['tuning'])
        return {'efficiency_enabled': False} if action == 'host-cpu-state' else dict(safe_state)

    monkeypatch.setattr(plugin, '_service_request', service_request)
    monkeypatch.setattr(plugin, '_maintenance_service_state',
                        lambda: 'inactive' if stopped[0] else 'active')
    identities = [
        {'package': 'zstack-zram-5.5.38.19-1.el7.x86_64',
         'unitPath': '/usr/lib/systemd/system/zram-memory.service',
         'unitSha256': 'b' * 64, 'binarySha256': 'c' * 64,
         'pid': 4242, 'processStartTime': '123456', 'bootId': boot_id,
         'unit': 'zram-memory.service', 'fragmentPath': '/usr/lib/systemd/system/zram-memory.service',
         'killMode': 'process', 'restart': 'no',
         'templateSha256': hashlib.sha256(template_path.read_bytes()).hexdigest(),
         'sourceConfigSha256': hashlib.sha256(config_path.read_bytes()).hexdigest()},
    ]
    if outcome == 'identity_changed':
        identities.append(dict(identities[0], pid=4343, processStartTime='234567'))
    else:
        identities.append(dict(identities[0]))
    monkeypatch.setattr(plugin, '_cold_controller_identity',
                        lambda template, config: identities.pop(0))
    real_no_pool_verified = plugin._first_use_no_pool_verified
    monkeypatch.setattr(plugin, '_first_use_no_pool_verified',
                        lambda command=None, **kwargs: (False if outcome == 'unsafe_history' else
                                                       real_no_pool_verified(command, **kwargs)))
    real_state_safe = plugin._first_use_state_safe
    monkeypatch.setattr(plugin, '_first_use_state_safe',
                        lambda native, **kwargs: (False if outcome == 'unsafe_native' else
                                                  real_state_safe(native, **kwargs)))

    inventory = _probe_block_inventory(boot_id)
    inventory.update({'hostUuid': HOST, 'bootId': boot_id,
                      'poolGeneration': 'none', 'canPrepare': True,
                      'preparationReasons': []})
    if outcome == 'ineligible_candidate':
        inventory['canPrepare'] = False
        inventory['preparationReasons'] = ['NO_ELIGIBLE_WRITEBACK_CANDIDATE']
    candidate_id = inventory['candidates'][0]['identity']
    command = {
        'hostUuid': HOST, 'scope': 'Host', 'action': 'prepareWritebackBackend',
        'operationUuid': 'a' * 32, 'desiredRevision': 7, 'policy': {},
        'backendPreparation': {
            'candidateId': candidate_id, 'expectedHostBootId': boot_id,
            'expectedPoolGeneration': 'none',
            'backendCapacityBytes': inventory['candidates'][0]['capacityBytes'],
            'resetConfirmed': True,
        },
    }
    if outcome.startswith('active_writeback_disable'):
        disabled_plugin, _, _, disabled_command, disabled_result = _capacity_apply_fixture(
            tmp_path / 'active-disabled-service', writeback={'enabled': False},
            capacity_requested=False, include_zram=False)
        assert disabled_result['status'] == 'Succeeded', disabled_result
        disabled_record = disabled_plugin._load_operation(disabled_command)
        if outcome == 'active_writeback_disable_previous_boot':
            disabled_record['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
        elif outcome == 'active_writeback_disable_missing_proof':
            disabled_record['readback']['state']['sections'].pop('tuningReadback')
            disabled_record['applyEvidence'] = json.loads(
                json.dumps(disabled_record['readback']))
        assert plugin._write_operation_record(disabled_record)
        disabled_service_state['record'] = disabled_record
        sections = disabled_record['readback']['state']['sections']
        disabled_service_state['cpu'] = plugin._strict_service_success(
            'host-cpu-state', sections['cpuReadback'])
        if 'tuningReadback' in sections:
            disabled_service_state['tuning'] = plugin._strict_service_success(
                'tuning-state', sections['tuningReadback'])
        if outcome == 'active_writeback_disable_cpu_drift':
            disabled_service_state['cpu']['efficiency_enabled'] = True
        elif outcome == 'active_writeback_disable_tuning_drift':
            disabled_service_state['tuning']['settings']['writeback']['enabled'] = True
        if outcome in ('active_writeback_disable_after_completed_prepare',
                       'active_writeback_disable_after_service_disable_prepare',
                       'active_writeback_disable_after_old_boot_ksm_prepare',
                       'active_writeback_disable_after_empty_ksm_prepare'):
            # A is a real completed preparation with its own worker/final
            # receipts and Go current record. c19 then becomes active control;
            # B must validate A while active, stop once, and use the bound
            # durable proof after the service socket has disappeared.
            old_operation, old_resource = 'd' * 32, 'e' * 32
            historical_control_uuid = disabled_record['operationUuid']
            if outcome == 'active_writeback_disable_after_old_boot_ksm_prepare':
                old_boot = 'f0a6ca92-1234-4234-8234-123456789abc'
                old_ack = {'run': '1', 'configRevision': '3', 'pages_to_scan': '2000',
                           'sleep_millisecs': '20', 'use_zero_pages': '0'}
                monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda request: dict(old_ack))
                monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: dict(old_ack))
                monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
                    'supported': True, 'ksm': True, 'ksmZeroPages': True,
                    'zram': True, 'writeback': True})
                old_control_command = {
                    'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                    'operationUuid': '1' * 32, 'desiredRevision': 3,
                    'policyMode': 'delta', 'policy': {'ksm': {
                        'enabled': True, 'pagesToScan': 2000,
                        'sleepMillis': 20, 'zeroPagesEnabled': False}},
                }
                assert plugin.apply(old_control_command)['status'] == 'Succeeded'
                historical_control_uuid = old_control_command['operationUuid']
                old_control_record = plugin._load_operation(old_control_command)
                old_control_record['bootId'] = old_boot
                assert plugin._write_operation_record(old_control_record)
                assert plugin._load_operation(old_control_command)['bootId'] == old_boot
            if outcome == 'active_writeback_disable_after_empty_ksm_prepare':
                old_ack = {'run': '1', 'configRevision': '3', 'pages_to_scan': '2000',
                           'sleep_millisecs': '20', 'use_zero_pages': '0'}
                monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda request: dict(old_ack))
                monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: dict(old_ack))
                monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
                    'supported': True, 'ksm': True, 'ksmZeroPages': True,
                    'zram': True, 'writeback': True})
                old_control_command = {
                    'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                    'operationUuid': '2' * 32, 'desiredRevision': 3,
                    'policyMode': 'delta', 'policy': {'ksm': {
                        'enabled': True, 'pagesToScan': 2000,
                        'sleepMillis': 20, 'zeroPagesEnabled': False}},
                }
                assert plugin.apply(old_control_command)['status'] == 'Succeeded'
                old_control_command.update(
                    operationUuid='3' * 32, desiredRevision=3, policyMode='effective',
                    policy={'ksm': {}, 'schemaVersion': 1})
                assert plugin.apply(old_control_command)['status'] == 'Succeeded'
                old_clear_record = plugin._load_operation(old_control_command)
                old_clear_record['bootId'] = 'f0a6ca92-1234-4234-8234-123456789abc'
                assert plugin._write_operation_record(old_clear_record)
                historical_control_uuid = old_control_command['operationUuid']
                # The old ACK is intentionally no longer the current KSM value;
                # an explicit empty effective KSM target is a completed clear, not
                # authority to reinstate that previous setting.
                old_ack['pages_to_scan'] = '100'
            old_request = build_backend_maintenance_request(inventory, {
                'requestId': old_operation, 'candidateId': candidate_id,
                'expectedHostBootId': boot_id, 'expectedPoolGeneration': 'none',
                'backendCapacityBytes': inventory['candidates'][0]['capacityBytes'],
                'resetConfirmed': True,
            })
            old_template = {
                'version': 2, 'mode': 'observe', 'managed': True,
                'resource_authorized': False, 'initial_efficiency_enabled': False,
                'vm_selection': 'all_running', 'vm_uuids': [], 'state_dir': str(state_dir),
                'monitor_socket': '/run/zram-efficiency-admission/monitor.sock',
                'control_socket': '/run/zram-efficiency-admission/control.sock',
                'device': '/dev/zram0', 'internal_rule': {}, 'budget': {},
            }
            template_path.write_text(json.dumps(old_template, sort_keys=True, indent=2) + '\n')
            old_config = dict(old_template, backend={
                'device': old_request['backend']['device'],
                'minimum_filesystem_free_bytes':
                    old_request['backend']['minimum_filesystem_free_bytes'],
            })
            config_path.write_text(json.dumps(old_config, sort_keys=True, indent=2) + '\n')
            for old_identity in identities:
                old_identity['sourceConfigSha256'] = hashlib.sha256(
                    config_path.read_bytes()).hexdigest()
            old_paths = plugin._maintenance_intent_paths(old_operation)[1]
            old_request_dir = state_dir / 'backend-maintenance' / old_operation
            old_archive_dir = old_request_dir / 'pre-reset-archive'
            old_archive_dir.mkdir(parents=True)
            # Match Go's completed-preparation evidence layout: the pre-change
            # runtime config and archived raw config are both the factory
            # template; the current config differs only by the prepared backend.
            old_config_before = template_path.read_bytes()
            (old_request_dir / 'config.before.json').write_bytes(old_config_before)
            (old_archive_dir / 'config.json').write_bytes(old_config_before)
            archive_config_sha256 = hashlib.sha256(old_config_before).hexdigest()
            with open(str(old_archive_dir / 'manifest.json'), 'w') as stream:
                json.dump({'config.json': archive_config_sha256}, stream, sort_keys=True)
            old_receipt = {
                'schema': 1, 'request_id': old_operation,
                'candidate_id': old_request['candidate_id'],
                'request_fingerprint': hashlib.sha256(json.dumps(
                    old_request, separators=(',', ':')).encode('utf-8')).hexdigest(),
                'started_at': '2026-10-17T00:00:00Z',
                'updated_at': '2026-10-17T00:00:01Z', 'host_boot_id': boot_id,
                'target_identity': old_request['target_identity'],
                'backend_resource_uuid': old_resource, 'reset_attempted': False,
                'archive': str(old_archive_dir),
                'stage': 'APPLIED',
            }
            old_worker = dict(old_receipt, stage='AWAITING_SERVICE_READBACK')
            for path, value in ((old_paths['requestPath'], old_request),
                                (old_paths['receiptPath'], old_worker)):
                with open(path, 'w') as stream:
                    json.dump(value, stream, sort_keys=True)
            with open(old_paths['stderrPath'], 'w') as stream:
                stream.write('')
            old_command = {
                'hostUuid': HOST, 'scope': 'Host', 'action': 'prepareWritebackBackend',
                'operationUuid': old_operation, 'desiredRevision': 6, 'policy': {},
                'expectedControlOperationUuid': (
                    historical_control_uuid
                    if outcome in ('active_writeback_disable_after_service_disable_prepare',
                                   'active_writeback_disable_after_old_boot_ksm_prepare',
                                   'active_writeback_disable_after_empty_ksm_prepare')
                    else None),
                'backendPreparation': {
                    'candidateId': candidate_id, 'expectedHostBootId': boot_id,
                    'expectedPoolGeneration': 'none',
                    'backendCapacityBytes': old_request['backend_capacity_bytes'],
                    'resetConfirmed': True,
                }, 'maintenanceIntentPath': old_paths['intentPath'],
            }
            old_hash = plugin._operation_hash(old_command)
            with open(old_paths['intentPath'], 'w') as stream:
                json.dump({
                    'schema': 1, 'operationUuid': old_operation, 'hostUuid': HOST,
                    'bootId': boot_id, 'requestHash': old_hash,
                    'unit': plugin._maintenance_systemd_unit(old_operation),
                    'requestPath': old_paths['requestPath'],
                    'receiptPath': old_paths['receiptPath'],
                    'stderrPath': old_paths['stderrPath'], 'configPath': str(config_path),
                'controlOperationUuid': (
                    historical_control_uuid
                    if outcome in ('active_writeback_disable_after_service_disable_prepare',
                                   'active_writeback_disable_after_old_boot_ksm_prepare',
                                   'active_writeback_disable_after_empty_ksm_prepare')
                    else None),
                'workerLaunchAttempted': True,
                }, stream, sort_keys=True)
            assert plugin._record_operation(old_command, 'PREPARING')
            old_result = plugin._maintenance_result(
                old_command, 'Succeeded', 'APPLIED', receipt=old_receipt)
            assert plugin._update_operation_record(old_operation, 'APPLIED', old_result)
            backend_state = state_dir / 'backend-maintenance'
            backend_state.mkdir(exist_ok=True)
            with open(str(backend_state / 'current.json'), 'w') as stream:
                json.dump(old_receipt, stream, sort_keys=True)
            monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt',
                                lambda: (old_receipt, None))
            monkeypatch.setattr(plugin, '_systemd_worker_exit', lambda unit: ('exited', 0))
            live_backend = {'backend_resource': {
                'resource_uuid': old_resource, 'fingerprint': 'a' * 64,
                'state': 'PREPARED', 'active': False,
                'capacity_bytes': old_request['backend_capacity_bytes'],
            }}
            live_detail = {
                'claimed': True, 'identity_qualified': True,
                'ownership_generation': old_resource,
                'effective': {'identity': {
                    key: old_request['target_identity'][key]
                    for key in ('boot_id', 'canonical_device', 'rdev', 'node_inode',
                                'sysfs_inode', 'capacity_bytes')},
                    'observed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())},
                'configured': {},
            }
            def old_service_read(action, payload):
                stopped_socket_queries.append((stopped[0], action))
                if stopped[0]:
                    raise IOError('the stopped service socket is unavailable')
                if action == 'host-cpu-state':
                    return {'efficiency_enabled': False}
                if action == 'backend-state':
                    return live_backend
                if action == 'backend-view':
                    return live_detail
                raise AssertionError('unexpected read-only query: %s' % action)
            monkeypatch.setattr(plugin, '_readonly_query', old_service_read)
            def probe_for_completed_prepare(host_uuid, service_backend=None, service_config=None):
                if service_backend and service_backend.get('backend_resource'):
                    return {'hostUuid': host_uuid, 'bootId': boot_id,
                            'candidates': [{'resourceUuid': old_resource,
                                'state': 'PREPARED', 'writebackReady': True,
                                'eligible': True}]}
                return _probe_block_inventory(
                    boot_id, service_backend=service_backend, service_config=service_config)

            monkeypatch.setattr(memory_optimization_module, 'probe_writeback_backends',
                                probe_for_completed_prepare)
            plugin._set_active_control(
                historical_control_uuid if outcome == 'active_writeback_disable_after_empty_ksm_prepare'
                else disabled_record['operationUuid'])
    if outcome in ('active_writeback_disable_after_completed_prepare',
                   'active_writeback_disable_after_service_disable_prepare',
                   'active_writeback_disable_after_old_boot_ksm_prepare',
                   'active_writeback_disable_after_empty_ksm_prepare'):
        real_fresh_inventory = plugin._fresh_backend_maintenance_inventory
        inventory_calls = [0]
        post_stop_inventory = []
        post_stop_records = []

        def actual_post_stop_inventory(host_uuid, command=None, **kwargs):
            inventory_calls[0] += 1
            if inventory_calls[0] == 1:
                return inventory
            assert stopped[0] is True
            post_stop_records.append(plugin._load_operation(command))
            fresh = real_fresh_inventory(host_uuid, command=command, **kwargs)
            post_stop_inventory.append(fresh)
            return fresh

        monkeypatch.setattr(plugin, '_fresh_backend_maintenance_inventory',
                            actual_post_stop_inventory)
    else:
        monkeypatch.setattr(plugin, '_fresh_backend_maintenance_inventory',
                            lambda host_uuid, **kwargs: inventory)
    real_time = memory_optimization_module.time.time
    clock_offset = [0]
    if outcome in ('crash_after_stop', 'stale_before_signal'):
        monkeypatch.setattr(memory_optimization_module.time, 'time',
                            lambda: real_time() + clock_offset[0])
    if outcome in ('crash_after_stop', 'candidate_changed_after_stop'):
        inventory_calls = [0]

        def fail_once_after_stop(host_uuid, **kwargs):
            inventory_calls[0] += 1
            if inventory_calls[0] == 2 and outcome == 'crash_after_stop':
                # A process restart/reconcile can exceed the three-second
                # native sample TTL while the daemon socket is unavailable.
                clock_offset[0] += 5
                raise ValueError('simulated continuation gap')
            if outcome == 'candidate_changed_after_stop' and inventory_calls[0] >= 2:
                return dict(inventory, candidates=[])
            return inventory

        monkeypatch.setattr(plugin, '_fresh_backend_maintenance_inventory', fail_once_after_stop)
    receipt_holder = [None]
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt', lambda: (None, None))
    if outcome in ('active_writeback_disable_after_completed_prepare',
                   'active_writeback_disable_after_service_disable_prepare',
                   'active_writeback_disable_after_old_boot_ksm_prepare',
                   'active_writeback_disable_after_empty_ksm_prepare'):
        monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt',
                            lambda: (old_receipt, None))
        monkeypatch.setattr(plugin, '_systemd_worker_exit', lambda unit: ('exited', 0))
    signals = []

    def send_signal(pid, sig):
        signals.append((pid, sig))
        stopped[0] = True

    monkeypatch.setattr(memory_optimization_module.os, 'kill', send_signal)
    monotonic_clock = [0.0]
    monkeypatch.setattr(linux, 'monotime', lambda: monotonic_clock[0])
    active_checks = [0]
    systemd_timeouts = []

    def systemd_output(argv):
        if argv[:3] != ['systemctl', 'show', 'zram-memory.service']:
            raise AssertionError('unexpected command: %r' % (argv,))
        if outcome == 'timeout':
            main_pid, active_state, sub_state = '4242', 'active', 'running'
        elif stopped[0]:
            main_pid, active_state, sub_state = '0', 'inactive', 'dead'
        else:
            main_pid, active_state, sub_state = '4242', 'active', 'running'
        active_checks[0] += 1
        if outcome == 'stale_before_signal':
            clock_offset[0] += 4
        return ('Id=zram-memory.service\nFragmentPath=/usr/lib/systemd/system/zram-memory.service\n'
                'DropInPaths=\nMainPID=%s\nActiveState=%s\nSubState=%s\n'
                'KillMode=process\nRestart=no\n' %
                (main_pid, active_state, sub_state)).encode('utf-8')

    if outcome == 'timeout':
        clocks = [0.0]

        def advance_monotonic():
            clocks[0] += 1
            return clocks[0]

        monkeypatch.setattr(linux, 'monotime', advance_monotonic)
        monkeypatch.setattr(memory_optimization_module.time, 'sleep', lambda seconds: None)
    real_open = open

    def native_open(path, mode='r', *args, **kwargs):
        values = {
            '/proc/swaps': 'Filename Type Size Used Priority\n',
            '/sys/block/zram0/disksize': '0\n',
            '/sys/block/zram0/mm_stat': '0 0 0 0 0 0 0 0\n',
            '/sys/block/zram0/backing_dev': 'none\n',
            '/proc/4242/stat': '4242 (zram-efficiency) S 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 123456\n',
        }
        if path in values and not (path == '/proc/4242/stat' and stopped[0]):
            return io.StringIO(values[path])
        if path == '/proc/4242/stat' and stopped[0]:
            raise IOError(path)
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr('builtins.open', native_open)
    original_exists = os.path.exists
    monkeypatch.setattr(memory_optimization_module.os.path, 'exists',
                        lambda path: False if path == '/proc/4242/stat' and stopped[0]
                        else original_exists(path))
    launches = []

    def launch(argv, **kwargs):
        launches.append(argv)
        if argv[:2] == ['systemctl', 'start']:
            if outcome == 'worker_failed_restore_timeout':
                raise RuntimeError('BOUNDED_COMMAND_TIMEOUT')
            stopped[0] = False

    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_call', launch)

    def bounded_command(argv, timeout_seconds):
        if argv[:2] == ['systemctl', 'show']:
            systemd_timeouts.append(timeout_seconds)
            return systemd_output(argv)
        if argv[:2] == ['systemctl', 'start']:
            return launch(argv, timeout=timeout_seconds)
        raise AssertionError('unexpected bounded command: %r' % (argv,))

    monkeypatch.setattr(plugin, '_bounded_command_output', bounded_command)
    with open(plugin.active_control_path, 'wb') as stream:
        stream.write(b'')
    if outcome.startswith('active_writeback_disable'):
        plugin._set_active_control(
            historical_control_uuid
            if outcome == 'active_writeback_disable_after_empty_ksm_prepare'
            else disabled_service_state['record']['operationUuid'])
        if outcome in ('active_writeback_disable', 'active_writeback_disable_previous_boot'):
            assert plugin._first_use_no_pool_verified(command) is True
    old_ksm_files = {}
    if outcome == 'cleared_ksm_reboot':
        monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
            'supported': True, 'ksm': True, 'ksmZeroPages': True,
            'zram': True, 'writeback': True})
        old_ack = {'run': '1', 'configRevision': '3', 'pages_to_scan': '2000',
                   'sleep_millisecs': '20', 'use_zero_pages': '0'}
        monkeypatch.setattr(plugin, '_apply_ksm_policy', lambda request: dict(old_ack))
        monkeypatch.setattr(plugin, '_read_ksm_ack', lambda: dict(old_ack))
        current_boot = boot_id
        boot_id = 'fedcba98-7654-3210-fedc-ba9876543210'
        ksm_command = {
            'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
            'operationUuid': '3' * 32, 'desiredRevision': 3,
            'policyMode': 'delta', 'policy': {'ksm': {
                'enabled': True, 'pagesToScan': 2000,
                'sleepMillis': 20, 'zeroPagesEnabled': False}},
        }
        assert plugin.apply(ksm_command)['status'] == 'Succeeded'
        ksm_command.update(operationUuid='5' * 32, policyMode='effective',
                           policy={'ksm': {}, 'schemaVersion': 1})
        assert plugin.apply(ksm_command)['status'] == 'Succeeded'
        boot_id = current_boot
        old_ack['pages_to_scan'] = '100'
        inventory['controlOperationUuid'] = ksm_command['operationUuid']
        old_ksm_files = {path: path.read_bytes() for path in operation_dir.glob('*.json')}
    active_control_before = open(plugin.active_control_path, 'rb').read()
    if outcome in ('active_writeback_disable_after_completed_prepare',
                   'active_writeback_disable_after_service_disable_prepare',
                   'active_writeback_disable_after_old_boot_ksm_prepare',
                   'active_writeback_disable_after_empty_ksm_prepare'):
        assert plugin._first_use_no_pool_verified() is True
    bindings_path = os.path.join(operation_dir, 'vm-bindings')
    os.mkdir(bindings_path)
    binding_path = os.path.join(bindings_path, '1' * 32 + '.json')
    with open(binding_path, 'wb') as stream:
        stream.write(json.dumps({
            'resourceUuid': '1' * 32, 'expectedInstanceGeneration': 'generation-1',
            'participation': 'allow', 'operationUuid': '2' * 32, 'updatedAt': 1,
        }, sort_keys=True).encode('utf-8'))
    bindings_before = open(binding_path, 'rb').read()

    result = plugin._prepare_backend_maintenance(command)
    if outcome in ('active_writeback_disable_after_completed_prepare',
                   'active_writeback_disable_after_service_disable_prepare',
                   'active_writeback_disable_after_old_boot_ksm_prepare',
                   'active_writeback_disable_after_empty_ksm_prepare'):
        assert result['status'] == 'Draining', (result, plugin._load_operation(command))
        assert signals == [(4242, 15)]
        assert len(launches) == 1 and launches[0][0] == 'systemd-run'
        assert stopped[0] is True
        # The post-stop inventory must be fetched via the real decorator. Its
        # service queries are genuinely unavailable once the controller exits;
        # eligibility comes from the saved stop-bound proof plus fresh offline
        # candidate probing, not a mocked live readback.
        assert inventory_calls[0] >= 2
        assert len(post_stop_inventory) == 1
        assert post_stop_inventory[0]['poolGeneration'] == 'none'
        assert 'POOL_GENERATION_UNKNOWN' not in post_stop_inventory[0]['preparationReasons']
        assert post_stop_inventory[0]['canPrepare'] is True
        assert post_stop_records[0]['maintenanceProgress']['controllerStop']['continuationReady'] is True
        assert (True, 'backend-state') in stopped_socket_queries
        return
    if outcome in ('active_writeback_disable', 'active_writeback_disable_previous_boot'):
        assert result['status'] == 'Draining', result
    elif (outcome.startswith('active_writeback_disable_') and
          outcome not in ('active_writeback_disable_after_completed_prepare',
                          'active_writeback_disable_after_service_disable_prepare',
                          'active_writeback_disable_after_old_boot_ksm_prepare',
                          'active_writeback_disable_after_empty_ksm_prepare')):
        assert result['status'] in ('Failed', 'Unknown'), result
        assert signals == []
        assert launches == []
        assert systemd_timeouts == []
        return

    if outcome in ('stopped', 'active_writeback_disable', 'active_writeback_disable_previous_boot',
                   'cleared_ksm_reboot') or worker_failed or outcome in (
            'timeout', 'crash_after_stop', 'stale_before_signal',
            'candidate_changed_after_stop'):
        assert systemd_timeouts and systemd_timeouts[0] == 5
        assert all(isinstance(value, (int, float)) and value <= 5
                   for value in systemd_timeouts)
    else:
        assert systemd_timeouts == []
    if outcome == 'timeout':
        assert len(systemd_timeouts) > 2
        assert all(value <= 1 for value in systemd_timeouts[1:])

    if outcome in ('stopped', 'active_writeback_disable', 'active_writeback_disable_previous_boot',
                   'cleared_ksm_reboot') or worker_failed:
        assert result['status'] == 'Draining', result
        assert signals == [(4242, 15)]
        assert len(launches) == 1 and launches[0][0] == 'systemd-run'
        assert not any(argv[:2] == ['systemctl', 'stop'] for argv in launches)
        record = plugin._load_operation(command)
        assert record['maintenanceProgress']['controllerStop']['identity']['pid'] == 4242
        assert record['maintenanceProgress']['controllerStop']['attempted'] is True
        _, maintenance_paths = plugin._maintenance_intent_paths(
            command['operationUuid'], create=False)
        request_path = maintenance_paths['requestPath']
        with open(request_path, 'r') as stream:
            request = json.load(stream)
        receipt_holder[0] = {
            'schema': 1,
            'request_id': request['request_id'], 'candidate_id': request['candidate_id'],
            'request_fingerprint': 'd' * 64,
            'started_at': '2026-10-16T12:00:00Z',
            'updated_at': '2026-10-16T12:01:00Z',
            'host_boot_id': boot_id, 'target_identity': request['target_identity'],
            'backend_resource_uuid': 'e' * 32, 'reset_attempted': False,
            'stage': 'AWAITING_SERVICE_READBACK',
        }
        if worker_failed:
            receipt_holder[0]['stage'] = 'FAILED_REQUIRES_REVIEW'
            receipt_holder[0]['reason'] = (
                'open /dev/vdb: permission denied'
                if outcome == 'worker_failed_restore_lowercase_error' else
                'BACKEND_MAINTENANCE_PREPARE_FAILED')
        for path in (maintenance_paths['stderrPath'], maintenance_paths['receiptPath']):
            with open(path, 'wb') as stream:
                if path == maintenance_paths['receiptPath']:
                    stream.write(json.dumps(receipt_holder[0], sort_keys=True).encode('utf-8'))
                elif worker_failed:
                    stream.write(json.dumps({
                        'error': receipt_holder[0]['reason'],
                    }, sort_keys=True).encode('utf-8'))
        if worker_failed:
            # Go persists FAILED_REQUIRES_REVIEW to current.json and retains
            # the maintenance fence before its CLI exits with status 1.
            maintenance_state = state_dir / 'backend-maintenance'
            maintenance_state.mkdir()
            current_receipt = dict(receipt_holder[0])
            if outcome == 'worker_failed_restore_mismatched_current':
                current_receipt['request_id'] = 'f' * 32
            with open(str(maintenance_state / 'current.json'), 'wb') as stream:
                stream.write(json.dumps(current_receipt, sort_keys=True).encode('utf-8'))
            (state_dir / 'maintenance').mkdir()
        monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt',
                            lambda: (receipt_holder[0], None))
        monkeypatch.setattr(plugin, '_systemd_worker_exit', lambda unit: (
            ('unknown', None) if outcome == 'worker_failed_restore_unknown_worker' else
            ('exited', 1 if worker_failed else 0)))
        service_states = (['inactive', 'inactive', 'inactive']
                          if outcome == 'worker_failed_restore_timeout' else
                          ['inactive', 'active', 'active', 'active', 'active']
                          if outcome in ('worker_failed_restore',
                                         'worker_failed_restore_lowercase_error') else ['inactive', 'active'])
        monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: service_states.pop(0))
        monkeypatch.setattr(plugin, '_read_maintenance_config',
                            lambda: ({'initial_efficiency_enabled': False}, str(state_dir), '/dev/zram0'))
        monkeypatch.setattr(plugin, '_verify_maintenance_service_readback',
                            lambda *args: (True, None))
        monkeypatch.setattr(plugin, '_host_optimization_disabled', lambda: (True, None))
        if worker_failed:
            stopped[0] = True
            monkeypatch.setattr(plugin, '_first_use_runtime_identity',
                                lambda template, config: {'bootId': boot_id})
            if outcome != 'worker_failed_restore_config_changed':
                reconcile_command = dict(
                    command, maintenanceIntentPath=plugin._maintenance_intent_paths(
                        command['operationUuid'], create=False)[1]['intentPath'])
                assert real_no_pool_verified(
                    reconcile_command, failed_backend_record=record,
                    failed_backend_receipt=receipt_holder[0]) is False
        original_service_request = plugin._service_request

        def finalize_service_request(action, payload):
            if action == 'backend-maintenance-finalize':
                receipt_holder[0]['stage'] = 'APPLIED'
                return {}
            if action == 'host-cpu-state' and worker_failed:
                return {'efficiency_enabled': False}
            if action == 'state' and outcome in (
                    'worker_failed_restore', 'worker_failed_restore_lowercase_error',
                    'worker_failed_restore_timeout',
                    'worker_failed_restore_config_changed'):
                # Go's failed-maintenance runtime keeps the fence active and
                # reports MAINTENANCE_BLOCKS_ACTIVATION; preserve those bytes.
                failed_state = dict(safe_state)
                failed_state['maintenance_blocks_activation'] = True
                failed_state['reason'] = 'MAINTENANCE_BLOCKS_ACTIVATION'
                failed_state['host_zram'] = dict(safe_state['host_zram'])
                failed_state['host_zram']['reason'] = (
                    'NO_QUALIFIED_MANAGED_POOL: MAINTENANCE_BLOCKS_ACTIVATION')
                return failed_state
            return original_service_request(action, payload)

        monkeypatch.setattr(plugin, '_service_request', finalize_service_request)
        if outcome == 'worker_failed_restore_config_changed':
            config_path.write_text(json.dumps({
                'state_dir': str(state_dir), 'device': '/dev/zram0',
                'initial_efficiency_enabled': False, 'backend': {'changed': True},
            }))
        result = plugin._reconcile_backend_maintenance(command, record)
        if outcome in ('stopped', 'active_writeback_disable', 'active_writeback_disable_previous_boot',
                       'cleared_ksm_reboot'):
            assert result['status'] == 'Succeeded', result
            assert receipt_holder[0]['stage'] == 'APPLIED'
            assert launches[-1] == ['systemctl', 'start', plugin.MANAGED_ZRAM_UNIT]
            assert len(launches) == 2
            assert open(plugin.active_control_path, 'rb').read() == active_control_before
            assert open(binding_path, 'rb').read() == bindings_before
            assert all(path.read_bytes() == content for path, content in old_ksm_files.items())
        elif outcome in ('worker_failed_restore', 'worker_failed_restore_lowercase_error'):
            failed_state = finalize_service_request('state', {})
            failed_state['host_cpu'] = finalize_service_request('host-cpu-state', {})
            assert real_state_safe(failed_state) is False
            assert real_state_safe(
                failed_state, allow_failed_backend_maintenance=True) is True
            wrong_failed_reason = dict(failed_state, reason='SOME_OTHER_MAINTENANCE')
            assert real_state_safe(
                wrong_failed_reason, allow_failed_backend_maintenance=True) is False
            assert result['status'] == 'Failed', result
            assert result['reasonCode'] == (
                'BACKEND_MAINTENANCE_UNKNOWN'
                if outcome == 'worker_failed_restore_lowercase_error' else
                'BACKEND_MAINTENANCE_PREPARE_FAILED')
            persisted = plugin._load_operation(command)
            assert persisted['stage'] == 'FAILED_REQUIRES_REVIEW'
            progress = persisted['maintenanceProgress']
            assert progress['serviceStartAttempted'] is True
            assert progress['serviceRestored'] is True
            reconcile_command = dict(
                command, maintenanceIntentPath=plugin._maintenance_intent_paths(
                    command['operationUuid'], create=False)[1]['intentPath'])
            assert real_no_pool_verified(
                reconcile_command, failed_backend_record=persisted,
                failed_backend_receipt=receipt_holder[0]) is True
            unbound_record = json.loads(json.dumps(persisted))
            unbound_record['maintenanceProgress']['controllerStop']['bootId'] = (
                'fedcba98-7654-3210-fedc-ba9876543210')
            assert real_no_pool_verified(
                reconcile_command, failed_backend_record=unbound_record,
                failed_backend_receipt=receipt_holder[0]) is False
            assert failed_state['maintenance_blocks_activation'] is True
            assert failed_state['reason'] == 'MAINTENANCE_BLOCKS_ACTIVATION'
            assert failed_state['host_zram']['reason'] == (
                'NO_QUALIFIED_MANAGED_POOL: MAINTENANCE_BLOCKS_ACTIVATION')
            assert launches[-1] == ['systemctl', 'start', plugin.MANAGED_ZRAM_UNIT]
            assert len(launches) == 2
            result_again = plugin._reconcile_backend_maintenance(command, plugin._load_operation(command))
            assert result_again['status'] == 'Failed'
            assert result_again['reasonCode'] == (
                'BACKEND_MAINTENANCE_UNKNOWN'
                if outcome == 'worker_failed_restore_lowercase_error' else
                'BACKEND_MAINTENANCE_PREPARE_FAILED')
            assert len(launches) == 2
            assert open(plugin.active_control_path, 'rb').read() == active_control_before
            assert open(binding_path, 'rb').read() == bindings_before
        elif outcome == 'worker_failed_restore_config_changed':
            assert result['status'] == 'Failed', result
            assert result['reasonCode'] == 'BACKEND_MAINTENANCE_PREPARE_FAILED'
            assert len(launches) == 1 and launches[0][0] == 'systemd-run'
            assert 'serviceStartAttempted' not in plugin._load_operation(command)['maintenanceProgress']
        elif outcome == 'worker_failed_restore_mismatched_current':
            assert result['status'] == 'Failed', result
            assert result['reasonCode'] == 'BACKEND_MAINTENANCE_PREPARE_FAILED'
            assert len(launches) == 1 and launches[0][0] == 'systemd-run'
            assert 'serviceStartAttempted' not in plugin._load_operation(command)['maintenanceProgress']
        elif outcome == 'worker_failed_restore_unknown_worker':
            assert result['status'] == 'Unknown', result
            assert result['reasonCode'] == 'BACKEND_MAINTENANCE_WORKER_STATE_UNKNOWN'
            assert len(launches) == 1 and launches[0][0] == 'systemd-run'
        else:
            assert result['status'] == 'Unknown', result
            assert result['reasonCode'] == 'COLD_CONTROLLER_RESTORE_UNRESOLVED'
            assert plugin._load_operation(command)['maintenanceProgress']['serviceStartAttempted'] is True
            assert launches[-1] == ['systemctl', 'start', plugin.MANAGED_ZRAM_UNIT]
            assert len(launches) == 2
            result_again = plugin._reconcile_backend_maintenance(command, plugin._load_operation(command))
            assert result_again['status'] == 'Unknown'
            assert result_again['reasonCode'] == 'COLD_CONTROLLER_RESTORE_UNRESOLVED'
            assert len(launches) == 2
            persisted = plugin._load_operation(command)
            assert persisted['stage'] == 'UNKNOWN'
            assert persisted['readback']['state']['maintenance'] == receipt_holder[0]
            assert plugin._has_unresolved_operation_journal() is True
    elif outcome == 'identity_changed':
        assert result['status'] == 'Unknown', result
        assert signals == []
        assert launches == []
    elif outcome == 'timeout':
        assert result['status'] == 'Unknown', result
        assert signals == [(4242, 15)]
        assert launches == []
        record = plugin._load_operation(command)
        assert record['maintenanceProgress']['controllerStop']['attempted'] is True
        # Apply is idempotent and explicit reconciliation is query-only while
        # the original process is still present; neither may signal again.
        assert plugin._prepare_backend_maintenance(command) == result
        reconciled = plugin._reconcile_backend_maintenance(command, record)
        assert reconciled['status'] == 'Unknown'
        assert signals == [(4242, 15)]
        assert launches == []
        stopped[0] = True
        later = plugin._reconcile_backend_maintenance(command, record)
        assert later['status'] == 'Unknown'
        assert later['reasonCode'] == 'COLD_CONTROLLER_STOP_UNRESOLVED'
        assert signals == [(4242, 15)]
        assert launches == []
    elif outcome == 'stale_before_signal':
        assert result['status'] == 'Unknown', result
        assert result['reasonCode'] == 'COLD_CONTROLLER_NATIVE_STATE_STALE'
        assert signals == []
        assert launches == []
        progress = plugin._load_operation(command)['maintenanceProgress']['controllerStop']
        assert progress['attempted'] is True
        assert progress['workerLaunchAttempted'] is False
    elif outcome == 'candidate_changed_after_stop':
        assert result['status'] == 'Unknown', result
        assert result['reasonCode'] == 'WRITEBACK_CANDIDATE_NOT_UNIQUE'
        assert signals == [(4242, 15)]
        assert launches == []
        record = plugin._load_operation(command)
        stop = record['maintenanceProgress']['controllerStop']
        assert stop['completed'] is True and stop['continuationReady'] is True
        assert stop['workerLaunchAttempted'] is False
        later = plugin._reconcile_backend_maintenance(command, record)
        assert later['status'] == 'Unknown'
        assert signals == [(4242, 15)]
        assert launches == []
    else:
        if outcome in ('unsafe_history', 'unsafe_native', 'ineligible_candidate'):
            assert result['status'] == 'Failed', result
            assert signals == []
            assert launches == []
        else:
            assert outcome == 'crash_after_stop'
            assert result['status'] == 'Unknown', result
            assert signals == [(4242, 15)]
            assert launches == []
            prior = plugin._load_operation(command)
            assert prior['stage'] == 'UNKNOWN'
            stopped_proof = prior['maintenanceProgress']['controllerStop']
            assert real_time() + clock_offset[0] - stopped_proof['nativeStateCheckedAt'] > 3
            continued = plugin._reconcile_backend_maintenance(command, prior)
            assert continued['status'] == 'Draining', continued
            assert signals == [(4242, 15)]
            assert len(launches) == 1 and launches[0][0] == 'systemd-run'
            assert inventory_calls[0] == 3


def test_cold_stop_unknown_excludes_only_its_exact_operation_from_first_use_history(
        tmp_path, monkeypatch):
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    operation_dir = tmp_path / 'operations'
    operation_dir.mkdir()
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps({'state_dir': str(state_dir), 'device': '/dev/zram0'}))
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainConfig': str(config_path)})
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    command = {'hostUuid': HOST, 'scope': 'Host', 'action': 'prepareWritebackBackend',
               'operationUuid': 'b' * 32, 'desiredRevision': 3, 'policy': {},
               'backendPreparation': {'candidateId': 'candidate:' + 'c' * 64,
                                      'expectedHostBootId': boot_id,
                                      'expectedPoolGeneration': 'none',
                                      'backendCapacityBytes': 8192, 'resetConfirmed': True},
               'maintenanceIntentPath': str(operation_dir / 'backend-maintenance' /
                                            ('b' * 32 + '.intent.json'))}
    assert plugin._record_operation(command, 'PREPARING',
                                    plugin._maintenance_result(command, 'Draining', 'STOPPING'))
    request_hash = plugin._operation_hash(command)
    progress = {'controllerStop': {'attempted': True, 'workerLaunchAttempted': False,
                                   'completed': True, 'continuationReady': True,
                                   'hostUuid': HOST, 'bootId': boot_id,
                                   'requestHash': request_hash,
                                   'identity': {'pid': 4242, 'bootId': boot_id,
                                                'processStartTime': '123456',
                                                'unit': plugin.MANAGED_ZRAM_UNIT,
                                                'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                                                'unitSha256': 'a' * 64, 'binarySha256': 'b' * 64,
                                                'templateSha256': 'c' * 64,
                                                'sourceConfigSha256': 'd' * 64,
                                                'killMode': 'process', 'restart': 'no'}}}
    progress['controllerStop']['request'] = {
        'request_id': command['operationUuid'], 'expected_host_boot_id': boot_id,
        'expected_pool_generation': 'none',
        'target_identity': {'boot_id': boot_id}}
    progress['controllerStop']['nativeState'] = {
        'mode': 'observe', 'resource_authorized': False,
        'lifecycle': {'schemaVersion': 1, 'abiProfile': 'zram-service-v1',
                      'readbackAllowed': True, 'paused': False,
                      'activeState': 'compatibility'},
        'maintenance_blocks_activation': False, 'pending_operations': [],
        'host_zram': {'pool_generation': '', 'device': '', 'quality': 'unavailable',
                      'reason': 'NO_QUALIFIED_MANAGED_POOL:first-use'},
        'host': {'qualified': True, 'safe': True, 'observed_at': time.time()},
        'host_cpu': {'efficiency_enabled': False}, 'observed_at': time.time(),
    }
    assert plugin._persist_maintenance_progress(
        command['operationUuid'], 'UNKNOWN',
        plugin._maintenance_result(command, 'Unknown', 'STOP_UNRESOLVED'), progress)
    assert plugin._first_use_local_history_clear(command) is True

    other = dict(command, operationUuid='d' * 32)
    assert plugin._record_operation(other, 'UNKNOWN',
                                    plugin._maintenance_result(other, 'Unknown', 'UNRESOLVED'))
    assert plugin._first_use_local_history_clear(command) is False


@pytest.mark.parametrize('start_outcome', ['started', 'timeout'])
def test_backend_prepare_continuation_starts_controller_once_and_keeps_control_state(
        tmp_path, monkeypatch, start_outcome):
    boot_id = MemoryOptimizationPlugin._current_boot_id()
    operation_dir = tmp_path / 'operations'
    operation_dir.mkdir()
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps({'state_dir': str(state_dir), 'device': '/dev/zram0',
                                      'initial_efficiency_enabled': False}))
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainConfig': str(config_path)})
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    inventory = _probe_block_inventory(boot_id)
    candidate = inventory['candidates'][0]
    request = build_backend_maintenance_request(inventory, {
        'requestId': 'e' * 32, 'candidateId': candidate['identity'],
        'expectedHostBootId': boot_id, 'expectedPoolGeneration': 'none',
        'backendCapacityBytes': candidate['capacityBytes'], 'resetConfirmed': True})
    command = {'hostUuid': HOST, 'scope': 'Host', 'action': 'prepareWritebackBackend',
               'operationUuid': 'e' * 32, 'desiredRevision': 7, 'policy': {},
               'backendPreparation': {'candidateId': candidate['identity'],
                                      'expectedHostBootId': boot_id,
                                      'expectedPoolGeneration': 'none',
                                      'backendCapacityBytes': candidate['capacityBytes'],
                                      'resetConfirmed': True}}
    command['maintenanceIntentPath'] = str(operation_dir / 'backend-maintenance' /
                                           ('e' * 32 + '.intent.json'))
    pending = plugin._maintenance_result(command, 'Draining', 'EXECUTOR_RUNNING')
    assert plugin._record_operation(command, 'DRAINING', pending)
    prior = plugin._load_operation(command)
    receipt = {'request_id': request['request_id'], 'candidate_id': request['candidate_id'],
               'host_boot_id': boot_id, 'target_identity': request['target_identity'],
               'pool_generation': None, 'backend_resource_uuid': 'f' * 32,
               'stage': 'AWAITING_SERVICE_READBACK'}
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt',
                        lambda: (receipt, None))
    states = ['inactive', 'inactive', 'inactive'] if start_outcome == 'timeout' else ['inactive', 'active']
    monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: states.pop(0))
    monkeypatch.setattr(plugin, '_read_maintenance_config',
                        lambda: ({'initial_efficiency_enabled': False}, str(state_dir), '/dev/zram0'))
    monkeypatch.setattr(plugin, '_verify_maintenance_service_readback', lambda *args: (True, None))
    monkeypatch.setattr(plugin, '_host_optimization_disabled', lambda: (True, None))

    def service_request(action, payload):
        if action == 'backend-maintenance-finalize':
            receipt['stage'] = 'APPLIED'
        return {}

    monkeypatch.setattr(plugin, '_service_request', service_request)
    launches = []

    def start(argv, timeout_seconds):
        assert timeout_seconds == 30
        launches.append(argv)
        if start_outcome == 'timeout':
            raise RuntimeError('BOUNDED_COMMAND_TIMEOUT')

    monkeypatch.setattr(plugin, '_bounded_command_output', start)
    control_path = plugin.active_control_path
    plugin._set_active_control('a' * 32)
    control_before = open(control_path, 'rb').read()
    bindings_path = os.path.join(operation_dir, 'vm-bindings')
    with open(bindings_path, 'wb') as stream:
        stream.write(b'unchanged-vm-binding-evidence')
    bindings_before = open(bindings_path, 'rb').read()

    result = plugin._continue_backend_maintenance(command, prior, request, receipt)
    assert launches == [['systemctl', 'start', plugin.MANAGED_ZRAM_UNIT]]
    assert open(control_path, 'rb').read() == control_before
    assert open(bindings_path, 'rb').read() == bindings_before
    if start_outcome == 'started':
        assert result['status'] == 'Succeeded', result
        receipt['stage'] = 'APPLIED'
        again = plugin._continue_backend_maintenance(command, plugin._load_operation(command),
                                                     request, receipt)
        assert again['status'] == 'Succeeded'
        assert len(launches) == 1
    else:
        assert result['status'] == 'Unknown', result
        progress = plugin._load_operation(command)['maintenanceProgress']
        assert progress['serviceStartAttempted'] is True
        again = plugin._continue_backend_maintenance(command, plugin._load_operation(command),
                                                     request, receipt)
        assert again['status'] == 'Unknown'
        assert len(launches) == 1


def _active_owned_backend_inventory(boot_id):
    observed_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    service_backend = {
        'claimed': True, 'identity_qualified': True,
        'ownership_generation': '0123456789abcdef0123456789abcdef',
        'effective': {'observed_at': observed_at,
                      'identity': _owned_backend_identity(boot_id)},
        'backend_resource': {
            'resource_uuid': '0123456789abcdef0123456789abcdef',
            'fingerprint': 'a' * 64, 'state': 'ACTIVE', 'active': True,
            'capacity_bytes': 1024 * 1024 * 1024, 'observed_at': observed_at,
        },
    }
    inventory = _probe_block_inventory(
        boot_id, service_backend=service_backend,
        service_config={'configured': {'device': '/dev/vdb'}})
    assert len(inventory['candidates']) == 1
    return inventory


def _drained_owner_proof(host_uuid, operation_uuid, boot_id, pool_generation, device):
    candidate = _active_owned_backend_inventory(boot_id)['candidates'][0]
    return {
        'schemaVersion': 1, 'hostUuid': host_uuid,
        'controlOperationUuid': operation_uuid,
        'resourceUuid': candidate['resourceUuid'],
        'fingerprint': candidate['fingerprint'],
        'ownershipGeneration': candidate['resourceUuid'],
        'bootId': boot_id, 'poolGeneration': pool_generation,
        'zramDevice': device, 'candidateIdentity': candidate['identity'],
        'candidateState': candidate['state'],
        'capacityBytes': candidate['capacityBytes'],
        'stableIdentity': candidate['stableIdentity'],
        'observedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }


def test_stock_drain_persists_pre_stop_backend_owner_in_existing_intent(
        tmp_path, monkeypatch):
    boot_id = '01234567-89ab-cdef-0123-456789abcdef'
    pool_generation = 'b' * 64
    native_device = '/dev/zram0'
    backend_inventory = _active_owned_backend_inventory(boot_id)
    stable = backend_inventory['candidates'][0]['stableIdentity']
    drain_binary = tmp_path / 'zram-efficiency'
    drain_config = tmp_path / 'config.json'
    drain_binary.write_text('fixture')
    drain_config.write_text('{}')
    plugin = MemoryOptimizationPlugin()
    operation_dir = tmp_path / 'operations'
    operation_dir.mkdir()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainDir': str(tmp_path / 'drain'),
                      'drainBinary': str(drain_binary),
                      'drainConfig': str(drain_config)})
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)

    def service_request(action, payload):
        if action == 'state':
            return {'host_zram': {'pool_generation': pool_generation,
                                  'device': native_device}}
        if action == 'host-cpu-state':
            return {'revision': 7, 'efficiency_enabled': False}
        raise AssertionError('unexpected native request: %s' % action)

    monkeypatch.setattr(plugin, '_service_request', service_request)
    status = {
        'host_zram': {'pool_generation': pool_generation, 'device': native_device},
        'backend_resource': {
            'resource_uuid': '0123456789abcdef0123456789abcdef',
            'fingerprint': 'a' * 64, 'state': 'ACTIVE', 'active': True,
            'capacity_bytes': 1024 * 1024 * 1024,
            'observed_at': backend_inventory['observedAt'],
        },
    }
    detail = {
        'claimed': True, 'identity_qualified': True,
        'ownership_generation': '0123456789abcdef0123456789abcdef',
        'configured': {'device': '/dev/vdb'},
        'effective': {'observed_at': backend_inventory['observedAt'],
                      'identity': _owned_backend_identity(boot_id)},
    }
    monkeypatch.setattr(plugin, '_readonly_query', lambda action, payload:
                        status if action == 'backend-state' else detail)
    monkeypatch.setattr(
        memory_optimization_module, 'probe_writeback_backends',
        lambda host_uuid, backend, config: _probe_block_inventory(
            boot_id, service_backend=backend, service_config=config))
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_call', lambda argv: 0)
    command = {'hostUuid': HOST, 'operationUuid': 'stock-drain-owner-proof', 'action': 'drain'}

    drain_state = plugin._prepare_stock_drain(command)
    assert drain_state.get('backendOwnerProof') == {
        'schemaVersion': 1,
        'hostUuid': HOST,
        'controlOperationUuid': command['operationUuid'],
        'resourceUuid': '0123456789abcdef0123456789abcdef',
        'fingerprint': 'a' * 64,
        'ownershipGeneration': '0123456789abcdef0123456789abcdef',
        'bootId': boot_id,
        'poolGeneration': pool_generation,
        'zramDevice': native_device,
        'candidateIdentity': 'a' * 64,
        'candidateState': 'ACTIVE',
        'capacityBytes': 1024 * 1024 * 1024,
        'stableIdentity': stable,
        'observedAt': backend_inventory['observedAt'],
    }

    drain_command = dict(command, **drain_state)
    plugin._start_stock_drain(drain_command)
    with open(tmp_path / 'operations' / 'stock-drain-owner-proof.drain-intent.json') as stream:
        intent = json.load(stream)
    assert intent['backendOwnerProof'] == drain_state['backendOwnerProof']


@pytest.mark.parametrize('observation', ['unavailable', 'not_active', 'pool_changed'])
def test_stock_drain_keeps_ordinary_path_without_proven_active_backend(
        tmp_path, monkeypatch, observation):
    boot_id = '01234567-89ab-cdef-0123-456789abcdef'
    pool_generation = 'b' * 64
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)

    def service_request(action, payload):
        if action == 'state':
            return {'host_zram': {'pool_generation': pool_generation, 'device': '/dev/zram0'}}
        if action == 'host-cpu-state':
            return {'revision': 7, 'efficiency_enabled': False}
        raise AssertionError('unexpected native request: %s' % action)

    monkeypatch.setattr(plugin, '_service_request', service_request)
    status = {
        'host_zram': {'pool_generation': pool_generation, 'device': '/dev/zram0'},
        'backend_resource': {
            'resource_uuid': '0123456789abcdef0123456789abcdef',
            'fingerprint': 'a' * 64, 'state': 'ACTIVE', 'active': True,
            'observed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        },
    }
    detail = {
        'claimed': True, 'identity_qualified': True,
        'ownership_generation': '0123456789abcdef0123456789abcdef',
        'configured': {'device': '/dev/vdb'},
        'effective': {'identity': _owned_backend_identity(boot_id)},
    }

    def readonly_query(action, payload):
        if observation == 'unavailable':
            raise IOError('backend view unavailable')
        if action == 'backend-state':
            result = dict(status)
            if observation == 'pool_changed':
                result['host_zram'] = {'pool_generation': 'c' * 64, 'device': '/dev/zram0'}
            if observation == 'not_active':
                result['backend_resource'] = dict(status['backend_resource'], state='PREPARED', active=False)
            return result
        return detail

    monkeypatch.setattr(plugin, '_readonly_query', readonly_query)
    command = {'hostUuid': HOST, 'operationUuid': 'ordinary-drain-without-owner-proof',
               'action': 'drain', 'backendOwnerProof': {'forged': True}}
    result = plugin._prepare_stock_drain(command)
    assert result['poolGeneration'] == pool_generation
    assert result['device'] == '/dev/zram0'
    assert result['backendOwnerProof'] is None


@pytest.mark.parametrize('corruption', [
    'none', 'missing', 'wrong_control', 'wrong_host', 'wrong_boot', 'wrong_pool',
])
def test_stock_drain_reconcile_returns_only_exact_durable_owner_proof(
        tmp_path, monkeypatch, corruption):
    with open('/proc/sys/kernel/random/boot_id') as stream:
        boot_id = stream.read().strip()
    pool_generation = 'b' * 64
    operation_uuid = 'drain-reconcile-owner-proof'
    device = '/dev/zram0'
    plugin = MemoryOptimizationPlugin()
    drain_dir = tmp_path / 'drain'
    operation_dir = tmp_path / 'operations'
    config_path = tmp_path / 'drain-config.json'
    config_path.write_text('{}')
    binary_path = tmp_path / 'zram-efficiency'
    binary_path.write_text('fixture')
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainDir': str(drain_dir), 'drainConfig': str(config_path),
                      'drainBinary': str(binary_path)})
    plugin._set_active_control(operation_uuid)
    receipt_path = drain_dir / (operation_uuid + '.receipt.json')
    intent_path = operation_dir / (operation_uuid + '.drain-intent.json')
    receipt = {'pool_generation': pool_generation, 'device': device,
               'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
               'active': False, 'reset_performed': False}
    receipt_path.parent.mkdir()
    with open(receipt_path, 'w') as stream:
        json.dump(receipt, stream)
    proof = _drained_owner_proof(HOST, operation_uuid, boot_id, pool_generation, device)
    if corruption == 'wrong_control':
        proof['controlOperationUuid'] = 'another-drain'
    elif corruption == 'wrong_host':
        proof['hostUuid'] = 'another-host'
    elif corruption == 'wrong_boot':
        proof['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
    elif corruption == 'wrong_pool':
        proof['poolGeneration'] = 'd' * 64
    intent = {'operationUuid': operation_uuid, 'bootId': boot_id,
              'poolGeneration': pool_generation, 'device': device,
              'unit': 'zstack-memory-drain-' + operation_uuid,
              'receiptPath': str(receipt_path),
              'stderrPath': str(drain_dir / (operation_uuid + '.stderr')),
              'configPath': plugin.drain_config}
    if corruption != 'missing':
        intent['backendOwnerProof'] = proof
    with open(intent_path, 'w') as stream:
        json.dump(intent, stream)
    command = {'hostUuid': HOST, 'operationUuid': operation_uuid, 'action': 'drain'}
    assert plugin._record_operation(command, 'DRAINING', {
        'success': True, 'status': 'Draining', 'operationUuid': operation_uuid})
    prior = plugin._load_operation(command)
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output',
                        lambda argv, **kwargs: json.dumps(receipt).encode('utf-8'))

    result = plugin._reconcile_stock_drain(command, prior)

    assert result['status'] == 'Succeeded'
    expected = corruption == 'none'
    assert ('backendOwnerProof' in result['state']) is expected
    record = plugin._load_operation(command)
    assert ('backendOwnerProof' in record['readback']['state']) is expected
    if expected:
        assert result['state']['backendOwnerProof'] == proof


def test_stock_drain_reconcile_retries_proof_readback_from_durable_intent(
        tmp_path, monkeypatch):
    with open('/proc/sys/kernel/random/boot_id') as stream:
        boot_id = stream.read().strip()
    pool_generation = 'b' * 64
    operation_uuid = 'drain-proof-readback-retry'
    device = '/dev/zram0'
    plugin = MemoryOptimizationPlugin()
    drain_dir = tmp_path / 'drain'
    operation_dir = tmp_path / 'operations'
    config_path = tmp_path / 'drain-config.json'
    config_path.write_text('{}')
    binary_path = tmp_path / 'zram-efficiency'
    binary_path.write_text('fixture')
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainDir': str(drain_dir), 'drainConfig': str(config_path),
                      'drainBinary': str(binary_path)})
    plugin._set_active_control(operation_uuid)
    receipt_path = drain_dir / (operation_uuid + '.receipt.json')
    intent_path = operation_dir / (operation_uuid + '.drain-intent.json')
    receipt = {'pool_generation': pool_generation, 'device': device,
               'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
               'active': False, 'reset_performed': False}
    receipt_path.parent.mkdir()
    with open(receipt_path, 'w') as stream:
        json.dump(receipt, stream)
    proof = _drained_owner_proof(HOST, operation_uuid, boot_id, pool_generation, device)
    intent = {'operationUuid': operation_uuid, 'bootId': boot_id,
              'poolGeneration': pool_generation, 'device': device,
              'unit': 'zstack-memory-drain-' + operation_uuid,
              'receiptPath': str(receipt_path),
              'stderrPath': str(drain_dir / (operation_uuid + '.stderr')),
              'configPath': plugin.drain_config, 'backendOwnerProof': proof}
    with open(intent_path, 'w') as stream:
        json.dump(intent, stream)
    intent_bytes = intent_path.read_bytes()
    command = {'hostUuid': HOST, 'operationUuid': operation_uuid, 'action': 'drain'}
    assert plugin._record_operation(command, 'DRAINING', {
        'success': True, 'status': 'Draining', 'operationUuid': operation_uuid})
    prior = plugin._load_operation(command)
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    native_checks = []

    def native_check(argv, **kwargs):
        native_checks.append(argv)
        return json.dumps(receipt).encode('utf-8')

    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output', native_check)
    original_update = plugin._update_operation_record
    updates = []

    def fail_second_update(operation, stage, result):
        updates.append(result)
        if len(updates) == 2:
            return False
        return original_update(operation, stage, result)

    monkeypatch.setattr(plugin, '_update_operation_record', fail_second_update)
    first = plugin._reconcile_stock_drain(command, prior)
    assert first['status'] == 'Succeeded'
    assert 'backendOwnerProof' not in first['state']
    first_record = plugin._load_operation(command)
    assert first_record['stage'] == 'APPLIED'
    assert 'backendOwnerProof' not in first_record['readback']['state']
    assert intent_path.read_bytes() == intent_bytes

    monkeypatch.setattr(plugin, '_update_operation_record', original_update)
    retry = plugin._reconcile_stock_drain(command, first_record)
    assert retry['status'] == 'Succeeded'
    assert retry['state']['backendOwnerProof'] == proof
    retry_record = plugin._load_operation(command)
    assert retry_record['stage'] == 'APPLIED'
    assert retry_record['readback']['state']['backendOwnerProof'] == proof
    assert intent_path.read_bytes() == intent_bytes
    assert len(native_checks) == 2


@pytest.mark.parametrize('tamper', [
    'none', 'missing_proof', 'wrong_control', 'wrong_pool', 'wrong_boot',
    'wrong_owner', 'wrong_stable_identity', 'candidate_mismatch', 'wrong_zram_device',
    'wrong_holder', 'extra_holder', 'other_candidate_reason', 'candidate_id_mismatch',
    'candidate_has_resource_uuid',
    'symlink_intent', 'symlink_control', 'unknown_journal',
])
def test_drained_backend_holder_is_eligible_only_from_same_control_owner_proof(
        tmp_path, monkeypatch, tamper):
    boot_id = '01234567-89ab-cdef-0123-456789abcdef'
    pool_generation = 'b' * 64
    operation_uuid = 'drained-backend-owner-proof'
    identity = {
        'boot_id': boot_id, 'canonical_device': '/dev/vdb', 'rdev': 64769,
        'node_inode': 12345, 'sysfs_inode': 54321,
        'capacity_bytes': 1024 * 1024 * 1024,
    }
    active_inventory = _active_owned_backend_inventory(boot_id)
    active_candidate = active_inventory['candidates'][0]
    proof = {
        'schemaVersion': 1, 'hostUuid': HOST,
        'controlOperationUuid': operation_uuid,
        'resourceUuid': active_candidate['resourceUuid'],
        'fingerprint': active_candidate['fingerprint'],
        'ownershipGeneration': '0123456789abcdef0123456789abcdef', 'bootId': boot_id,
        'poolGeneration': pool_generation, 'zramDevice': '/dev/zram0',
        'candidateIdentity': active_candidate['identity'], 'candidateState': 'ACTIVE',
        'capacityBytes': active_candidate['capacityBytes'],
        'stableIdentity': active_candidate['stableIdentity'],
        'observedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    if tamper == 'wrong_control':
        proof['controlOperationUuid'] = 'other-drain-operation'
    elif tamper == 'wrong_pool':
        proof['poolGeneration'] = 'd' * 64
    elif tamper == 'wrong_boot':
        proof['bootId'] = 'fedcba98-7654-3210-fedc-ba9876543210'
        proof['stableIdentity']['bootId'] = proof['bootId']
    elif tamper == 'wrong_owner':
        proof['ownershipGeneration'] = 'fedcba9876543210fedcba9876543210'
    elif tamper == 'wrong_stable_identity':
        proof['stableIdentity']['nodeInode'] += 1
    elif tamper == 'wrong_zram_device':
        proof['zramDevice'] = '/dev/zram1'
    plugin = MemoryOptimizationPlugin()
    operation_dir = tmp_path / 'operations'
    drain_dir = tmp_path / 'drain'
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainDir': str(drain_dir)})
    plugin._set_active_control(operation_uuid)
    receipt_path = drain_dir / (operation_uuid + '.receipt.json')
    receipt_path.parent.mkdir()
    with open(receipt_path, 'w') as stream:
        json.dump({'pool_generation': pool_generation,
                   'device': '/dev/zram0',
                   'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
                   'active': False, 'reset_performed': False}, stream)
    intent = {'operationUuid': operation_uuid, 'bootId': boot_id,
              'poolGeneration': pool_generation, 'device': '/dev/zram0',
              'unit': 'zstack-memory-drain-' + operation_uuid,
              'receiptPath': str(receipt_path), 'configPath': plugin.drain_config,
              'stderrPath': str(drain_dir / (operation_uuid + '.stderr')),
              'backendOwnerProof': proof}
    if tamper == 'missing_proof':
        intent.pop('backendOwnerProof')
    intent_path = operation_dir / (operation_uuid + '.drain-intent.json')
    if tamper == 'symlink_intent':
        intent_target = operation_dir / 'drain-intent-target.json'
        with open(intent_target, 'w') as stream:
            json.dump(intent, stream)
        os.symlink(str(intent_target), str(intent_path))
    else:
        with open(intent_path, 'w') as stream:
            json.dump(intent, stream)
    plugin._write_operation_record({
        'operationUuid': operation_uuid, 'action': 'drain',
        'stage': 'UNKNOWN' if tamper == 'unknown_journal' else 'APPLIED',
        'bootId': boot_id, 'hostUuid': HOST, 'readback': {'status': 'Succeeded'},
    })
    if tamper == 'symlink_control':
        control_target = tmp_path / 'active-control-target'
        control_target.write_text(operation_uuid)
        os.unlink(plugin.active_control_path)
        os.symlink(str(control_target), plugin.active_control_path)
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot_id)
    monkeypatch.setattr(plugin, '_service_unit_stopped', lambda: True)
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt',
                        lambda: ({'stage': 'NOT_STARTED'}, None))
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output',
                        lambda argv: json.dumps({
                            'pool_generation': pool_generation,
                            'device': '/dev/zram0',
                            'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
                            'active': False, 'reset_performed': False,
                        }).encode('utf-8'))
    candidate = _probe_block_inventory(boot_id, holders=['zram0'])['candidates'][0]
    if tamper == 'candidate_mismatch':
        candidate['stableIdentity']['nodeInode'] += 1
    if tamper == 'other_candidate_reason':
        candidate['reasons'].append('SERIAL_IDENTITY_MISSING')
    if tamper == 'candidate_id_mismatch':
        candidate['identity'] = 'candidate:' + ('d' * 64)
    if tamper == 'candidate_has_resource_uuid':
        candidate['resourceUuid'] = proof['resourceUuid']
    holders_path = os.path.join(candidate['stableIdentity']['sysfsPath'], 'holders')
    expected_holder = '/sys/devices/virtual/block/zram0'
    realpath = os.path.realpath
    listdir = os.listdir

    def test_realpath(path):
        if path == '/sys/class/block/zram0':
            return expected_holder
        if path == os.path.join(holders_path, 'zram0'):
            return expected_holder
        return realpath(path)

    def test_listdir(path):
        if path == holders_path:
            if tamper == 'wrong_holder':
                return ['dm-0']
            if tamper == 'extra_holder':
                return ['zram0', 'dm-0']
            return ['zram0']
        return listdir(path)

    monkeypatch.setattr(memory_optimization_module.os.path, 'realpath', test_realpath)
    monkeypatch.setattr(memory_optimization_module.os, 'listdir', test_listdir)
    monkeypatch.setattr(
        memory_optimization_module, 'probe_writeback_backends',
        lambda *args, **kwargs: {
            'hostUuid': HOST, 'bootId': boot_id,
            'status': 'AVAILABLE', 'candidates': [dict(candidate)],
            'reasons': [],
        })
    monkeypatch.setattr(plugin, '_readonly_query',
                        lambda action, payload: (_ for _ in ()).throw(IOError('service stopped')))
    response = json.loads(plugin.writeback_backends({'body': json.dumps({'hostUuid': HOST})}))
    assert response['success'] is True
    assert response['state']['controlOperationUuid'] == operation_uuid
    expected = tamper == 'none'
    assert response['state']['canPrepare'] is expected
    prepared = response['state']['candidates'][0]
    assert prepared['eligible'] is expected
    if expected:
        assert prepared['state'] == 'NEEDS_OFFLINE_PREPARATION'
        assert prepared['reasons'] == ['NEEDS_OFFLINE_PREPARATION']
    else:
        assert prepared['state'] == 'INELIGIBLE'
        assert prepared['reasons'] == sorted(
            ['ACTIVE_BLOCK_HOLDERS'] +
            (['SERIAL_IDENTITY_MISSING'] if tamper == 'other_candidate_reason' else []))


def test_zram_budget_operations_require_known_accounting_capability():
    command = {'policy': {'zram': {'enabled': True}}}

    with pytest.raises(ValueError, match='UNSUPPORTED_HOST_CAPABILITY:zram'):
        MemoryOptimizationPlugin._validate_requested_capabilities(command, {
            'zram': True,
            'zramDriver': {'applicable': True, 'accountingSupported': False},
        })


def test_ksm_remains_available_when_zram_accounting_schema_is_unknown():
    command = {'policy': {'ksm': {'enabled': True}}}

    MemoryOptimizationPlugin._validate_requested_capabilities(command, {
        'ksm': True, 'zram': True,
        'zramDriver': {'applicable': True, 'accountingSupported': False},
    })


@pytest.mark.parametrize('psi', [True, False])
def test_agent_keeps_base_zram_and_ksm_capabilities_when_optional_abi_is_missing(
        monkeypatch, psi):
    plugin = MemoryOptimizationPlugin()
    plugin.socket_path = '/run/zram-efficiency-admission/control.sock'
    kernel = '6.6.104-006.1.pro.ali6000.alnx4.x86_64'
    monkeypatch.setattr(memory_optimization_module.platform, 'machine',
                        lambda: 'x86_64')
    monkeypatch.setattr(memory_optimization_module.platform, 'release',
                        lambda: kernel)
    monkeypatch.setattr(memory_optimization_module.os, 'sysconf',
                        lambda name: 4096)
    real_open = open

    def read_os_release(path, *args, **kwargs):
        if path == '/etc/os-release':
            import io
            return io.StringIO('ID=alinux\nVERSION_ID="4.0"\n')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', read_os_release)
    available = {
        '/run/zram-efficiency-admission/control.sock',
        '/sys/kernel/mm/ksm/run',
        '/sys/kernel/mm/ksm/pages_to_scan',
        '/sys/kernel/mm/ksm/sleep_millisecs',
        '/sys/block/zram0/mm_stat',
        '/sys/fs/cgroup/cgroup.controllers',
        '/sys/fs/cgroup/memory.reclaim',
    }
    if psi:
        available.update(('/proc/pressure/memory', '/proc/pressure/io'))
    monkeypatch.setattr(memory_optimization_module.os.path, 'exists',
                        lambda path: path in available)
    monkeypatch.setattr(plugin, 'service_call', lambda action, payload: {
        'abiProfile': 'zram-service-v1', 'schemaVersion': 1,
        'reclaim_qualification': {
            'kernel': kernel, 'architecture': 'amd64', 'page_size_bytes': 4096,
            'supported': True,
        },
    })
    monkeypatch.setattr(plugin, 'installed_reclaim_candidate',
                        lambda release, running_kernel: None)
    monkeypatch.setattr(memory_optimization_module.zram_driver, 'inspect',
                        lambda **kwargs: {
                            'supported': True, 'reasonCode': 'SUPPORTED',
                            'accountingSupported': False,
                            'writebackSupported': False,
                        })

    capabilities = plugin.discover_capabilities()

    assert capabilities['supported'] is True
    assert capabilities['ksm'] is True
    assert capabilities['zram'] is psi
    assert capabilities['zramReasonCode'] == ('SUPPORTED' if psi else 'HOST_PSI_UNAVAILABLE')
    assert capabilities['zramDriver']['accountingSupported'] is False
    assert capabilities['writeback'] is False


def test_single_side_capacity_update_keeps_current_other_side(monkeypatch):
    plugin = MemoryOptimizationPlugin()
    monkeypatch.setattr(plugin, 'service_call', lambda action, body: {
        'desired': {'logical_resolved_bytes': OLD_LOGICAL_BYTES,
                    'physical_resolved_bytes': OLD_PHYSICAL_BYTES}})
    logical_only = {'policy': {'zram': {'logicalCapacityBytes': LOGICAL_BYTES}}}
    physical_only = {'policy': {'zram': {'ramLimitBytes': PHYSICAL_BYTES}}}

    plugin._fill_resolved_capacity_defaults(logical_only)
    plugin._fill_resolved_capacity_defaults(physical_only)

    assert logical_only['policy']['zram'] == {
        'logicalCapacityBytes': LOGICAL_BYTES, 'ramLimitBytes': OLD_PHYSICAL_BYTES}
    assert physical_only['policy']['zram'] == {
        'logicalCapacityBytes': OLD_LOGICAL_BYTES, 'ramLimitBytes': PHYSICAL_BYTES}


@pytest.mark.parametrize(('policy', 'reason', 'clear'), [
    ({'ksm': {'enabled': True, 'sleepMillis': 25}}, 'KSM_SLEEP_UNREPRESENTABLE', True),
    ({'schemaVersion': 1, 'ksm': {'zeroPagesEnabled': True}}, 'KSM_ZERO_PAGES_UNSUPPORTED', True),
    ({'ksm': {'enabled': True}}, 'KSM_NATIVE_SERVICE_STATE_UNKNOWN', False),
    ({'ksm': {'enabled': True}, 'zram': {'enabled': True}}, 'KSM_SLEEP_UNREPRESENTABLE', False),
])
def test_first_use_accepts_only_prewrite_ksm_rejection_history(tmp_path, policy, reason, clear):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    rejected = {'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
                'operationUuid': OPERATION, 'desiredRevision': 3, 'policy': policy}
    assert plugin._record_operation(rejected, 'REJECTED', {'reason': reason})

    assert plugin._first_use_local_history_clear(
        {'hostUuid': HOST, 'operationUuid': '1' * 32}) is clear


def _drained_reboot_fixture(tmp_path, monkeypatch, record_boot, current_boot='boot-after-reboot'):
    drain, generation = 'd' * 32, 'c' * 64
    ops, state = tmp_path / 'operations', tmp_path / 'state'
    ops.mkdir()
    archive = state / 'drained-pool-archives' / generation
    archive.mkdir(parents=True)
    (archive / 'manifest.json').write_text(json.dumps({
        'schema': 1, 'pool_generation': generation,
        'files': ['stock-pool.json', 'zram-ownership.json', 'maintenance']}))
    receipt = tmp_path / 'drain-receipt.json'
    receipt.write_text(json.dumps({'pool_generation': generation, 'device': '/dev/zram0',
                                   'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
                                   'active': False, 'reset_performed': False}))
    (ops / ('%s.json' % drain)).write_text(json.dumps({
        'operationUuid': drain, 'action': 'drain', 'stage': 'APPLIED',
        'bootId': record_boot, 'hostUuid': HOST}))
    (ops / ('%s.drain-intent.json' % drain)).write_text(json.dumps({
        'operationUuid': drain, 'poolGeneration': generation, 'receiptPath': str(receipt),
        'bootId': record_boot}))
    (ops / 'active-control').write_text(drain)
    config = tmp_path / 'zram-config.json'
    config.write_text(json.dumps({'state_dir': str(state)}))
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(ops), 'drainConfig': str(config)})
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: current_boot)
    real_open = open

    def native_open(path, *args, **kwargs):
        if path == '/proc/swaps':
            return io.StringIO('Filename Type Size Used Priority\n')
        if path == '/sys/block/zram0/mm_stat':
            return io.StringIO('0 0 0 0 0 0 0 0 0\n')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', native_open)
    proof = {'maintenanceReady': True, 'maintenanceArchived': True, 'activeOperations': 0,
             'drainOperationUuid': drain, 'oldPoolGeneration': generation,
             'readyForInitialization': True, 'originalDeviceInactive': True,
             'oldPoolOwnershipAbsent': True, 'poolOwnedByService': False}
    blank = {'pending_operations': None, 'host_zram': {
        'pool_generation': '', 'device': '', 'quality': 'unavailable',
        'reason': 'NO_QUALIFIED_MANAGED_POOL: VM_INVENTORY_UNQUALIFIED'}}
    return plugin, proof, blank


@pytest.mark.parametrize('record_boot', ['boot-after-reboot', 'boot-before-reboot'])
def test_drained_blank_device_recovers_in_the_drain_boot_or_after_reboot(tmp_path, monkeypatch, record_boot):
    plugin, proof, blank = _drained_reboot_fixture(tmp_path, monkeypatch, record_boot)
    assert plugin._maintenance_recovery_proof({'maintenanceProof': proof}, live_state=blank) is True


def test_drain_from_a_previous_boot_never_proves_a_live_replacement_pool(tmp_path, monkeypatch):
    plugin, proof, _ = _drained_reboot_fixture(tmp_path, monkeypatch, 'boot-before-reboot')
    replacement = 'e' * 64
    proof.update({'newPoolGeneration': replacement, 'poolOwnedByService': True})
    live = {'pending_operations': [], 'host_zram': {'pool_generation': replacement}}
    assert plugin._maintenance_recovery_proof({'maintenanceProof': proof}, live_state=live) is False


def test_activation_after_reboot_reads_the_service_receipt_of_a_previous_boot_drain(tmp_path, monkeypatch):
    plugin, proof, _ = _drained_reboot_fixture(tmp_path, monkeypatch, 'boot-before-reboot')
    drain, operation = 'd' * 32, 'a' * 32
    request = {'request_id': 'f' * 32, 'expected_control_operation_uuid': drain,
               'expected_host_boot_id': 'boot-after-reboot', 'expected_pool_generation': proof['oldPoolGeneration']}
    intent = {'operationUuid': operation, 'hostUuid': HOST, 'bootId': 'boot-after-reboot',
              'expectedControlOperationUuid': drain, 'proof': proof, 'request': request,
              'proofFingerprint': hashlib.sha256(json.dumps(
                  proof, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()}
    queried = []
    monkeypatch.setattr(plugin, '_service_request', lambda action, payload: queried.append(action) or {})
    _, reason, _ = plugin._maintenance_activation_observation({'operationUuid': operation}, intent)
    assert reason != 'MAINTENANCE_ACTIVATION_DRAIN_HISTORY_UNQUALIFIED'
    assert 'lifecycle-activation-state' in queried


def test_records_of_a_previous_host_identity_do_not_fence_first_zram(tmp_path):
    """A Host deleted and re-added in the cloud keeps the Agent journals of its old UUID."""
    old_host, old_control = 'f' * 32, 'b' * 32
    ops = tmp_path / 'memory-optimization' / 'operations'
    ops.mkdir(parents=True)
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(ops)})
    (ops / ('%s.json' % old_control)).write_text(json.dumps({
        'operationUuid': old_control, 'hostUuid': old_host, 'action': 'apply', 'stage': 'APPLIED',
        'policy': {'ksm': {'enabled': True}, 'zram': {'enabled': False}}}))
    (ops / ('%s.drain-intent.json' % old_control)).write_text(json.dumps({'operationUuid': old_control}))
    (ops / 'active-control').write_text(old_control)
    command = {'hostUuid': HOST, 'operationUuid': '1' * 32}
    assert plugin._first_use_local_history_clear(command) is False

    plugin._archive_foreign_host_history()

    assert sorted(os.listdir(str(ops))) == []
    archived = list((tmp_path / 'memory-optimization' / 'foreign-host-operations').iterdir())
    assert len(archived) == 1
    assert sorted(os.listdir(str(archived[0]))) == sorted([
        '%s.json' % old_control, '%s.drain-intent.json' % old_control, 'active-control'])
    assert plugin._first_use_local_history_clear(command) is True


def test_state_does_not_confirm_a_revision_of_a_previous_host_identity(tmp_path):
    ops = tmp_path / 'operations'
    ops.mkdir()
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(ops)})
    old_control = 'b' * 32
    record = {'operationUuid': old_control, 'hostUuid': 'f' * 32, 'action': 'apply', 'stage': 'APPLIED',
              'bootId': plugin._current_boot_id(), 'desiredRevision': 1}
    (ops / ('%s.json' % old_control)).write_text(json.dumps(record))
    (ops / 'active-control').write_text(old_control)
    result = plugin._enrich_state({'success': True, 'status': 'Succeeded', 'state': {}})
    assert 'appliedRevision' not in result and 'lastConfirmedOperationUuid' not in result
    record['hostUuid'] = HOST
    (ops / ('%s.json' % old_control)).write_text(json.dumps(record))
    result = plugin._enrich_state({'success': True, 'status': 'Succeeded', 'state': {}})
    assert result['appliedRevision'] == 1 and result['lastConfirmedOperationUuid'] == old_control


def test_current_host_records_stay_in_place(tmp_path):
    ops = tmp_path / 'operations'
    ops.mkdir()
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(ops)})
    record = {'operationUuid': 'a' * 32, 'hostUuid': HOST, 'action': 'apply', 'stage': 'UNKNOWN'}
    (ops / ('%s.json' % ('a' * 32))).write_text(json.dumps(record))
    plugin._archive_foreign_host_history()
    assert os.listdir(str(ops)) == ['%s.json' % ('a' * 32)]


def _running_drained_preparation(tmp_path, monkeypatch, full_check_reasons):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    for name in ('drain_binary', 'drain_config'):
        path = tmp_path / name
        path.write_text('')
        setattr(plugin, name, str(path))
    running, commands = [True], []

    def systemctl(command, timeout):
        commands.append(command[:2])
        running[0] = command[1] == 'start'
        return ''

    monkeypatch.setattr(plugin, '_service_unit_stopped', lambda: not running[0])
    monkeypatch.setattr(plugin, '_bounded_command_output', systemctl)
    monkeypatch.setattr(plugin, '_zram_pool_preparation_eligibility', lambda host, control=None: (
        {'canPrepareZramPool': True} if running[0] else
        {'canPrepareZramPool': False, 'zramPoolPreparationReasons': full_check_reasons}))
    command = {'hostUuid': HOST, 'operationUuid': 'a' * 32, 'action': 'prepareZramPool', 'scope': 'Host',
               'expectedControlOperationUuid': 'd' * 32,
               'poolPreparation': {'expectedHostBootId': plugin._current_boot_id(),
                                   'expectedPoolGeneration': 'c' * 64, 'resetConfirmed': True}}
    return plugin, command, running, commands


def test_preparation_stops_a_drained_service_and_restarts_it_if_it_cannot_reset(tmp_path, monkeypatch):
    plugin, command, running, commands = _running_drained_preparation(
        tmp_path, monkeypatch, ['DRAIN_PROOF_UNAVAILABLE'])
    result = plugin._prepare_zram_pool(command)
    assert result['status'] == 'Failed' and result['reasonCode'] == 'DRAIN_PROOF_UNAVAILABLE', result
    assert commands == [['systemctl', 'stop'], ['systemctl', 'start']]
    assert running[0] is True


def test_preparation_leaves_the_service_running_when_the_drain_is_not_proven(tmp_path, monkeypatch):
    plugin, command, running, commands = _running_drained_preparation(tmp_path, monkeypatch, [])
    monkeypatch.setattr(plugin, '_zram_pool_preparation_eligibility', lambda host, control=None: {
        'canPrepareZramPool': False, 'zramPoolPreparationReasons': ['OPERATION_JOURNAL_UNRESOLVED']})
    result = plugin._prepare_zram_pool(command)
    assert result['reasonCode'] == 'OPERATION_JOURNAL_UNRESOLVED', result
    assert commands == [] and running[0] is True


@pytest.mark.parametrize('quiescent', [True, False])
def test_running_drained_service_does_not_block_preparation_eligibility(tmp_path, monkeypatch, quiescent):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    native_checks = []
    monkeypatch.setattr(plugin, '_get_active_control', lambda: 'd' * 32)
    monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: 'active')
    monkeypatch.setattr(plugin, '_drained_service_quiescent', lambda: quiescent)
    monkeypatch.setattr(plugin, '_drained_pool_generation', lambda host, control, native_check=True: (
        native_checks.append(native_check) or 'c' * 64))
    reasons = plugin._zram_pool_preparation_eligibility(HOST)['zramPoolPreparationReasons']
    assert native_checks == [False]
    assert 'DRAIN_PROOF_UNAVAILABLE' not in reasons
    assert ('MEMORY_SERVICE_NOT_STOPPED' in reasons) is not quiescent


@pytest.mark.parametrize('reason,status', [('MAINTENANCE_ACTIVATION_POOL_STARTING', 'Draining'),
                                           ('MAINTENANCE_ACTIVATION_HOST_SETTLING', 'Draining'),
                                           ('MAINTENANCE_ACTIVATION_POOL_NOT_READY', 'Unknown')])
def test_activation_waiting_for_service_startup_stays_in_progress(tmp_path, monkeypatch, reason, status):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(plugin, '_maintenance_activation_observation', lambda command, intent: (False, reason, {}))
    result = plugin._finish_maintenance_activation({'operationUuid': 'a' * 32}, {}, wait=False)
    assert result['status'] == status and result['reasonCode'] == reason
    assert result['success'] is (status == 'Draining'), 'MN treats only a successful Draining reply as in progress'
    prior = {'action': 'apply', 'hostUuid': HOST, 'bootId': plugin._current_boot_id(), 'activationIntent': {}}
    result = plugin._reconcile_maintenance_activation({'operationUuid': 'a' * 32}, prior)
    assert result['status'] == status and result['reasonCode'] == reason


@pytest.mark.parametrize('receipt_generation,blocked', [('e' * 64, False), ('c' * 64, True)])
def test_preparation_receipt_of_an_earlier_drain_cycle_does_not_block(tmp_path, monkeypatch,
                                                                      receipt_generation, blocked):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    monkeypatch.setattr(plugin, '_get_active_control', lambda: 'd' * 32)
    monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: 'inactive')
    monkeypatch.setattr(plugin, '_drained_pool_generation', lambda host, control, native_check=True: 'c' * 64)
    monkeypatch.setattr(plugin, '_read_zram_pool_preparation_receipt', lambda: (
        {'stage': 'APPLIED', 'pool_generation': receipt_generation}, None))
    state = tmp_path / 'state'
    (state / 'policies').mkdir(parents=True)
    (state / 'policies' / 'policies.json').write_text(json.dumps({'host': {'efficiency_enabled': False}}))
    monkeypatch.setattr(plugin, '_read_maintenance_config', lambda: (
        {'initial_efficiency_enabled': False}, str(state), '/dev/zram0'))
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt', lambda: ({'stage': 'NOT_STARTED'}, None))
    reasons = plugin._zram_pool_preparation_eligibility(HOST)['zramPoolPreparationReasons']
    assert 'ZRAM_POOL_PREPARATION_EVIDENCE_UNKNOWN' not in reasons
    assert ('ZRAM_POOL_PREPARATION_ALREADY_REQUESTED' in reasons) is blocked


@pytest.mark.parametrize('service_state,native_check', [('active', False), ('inactive', True)])
def test_inventory_reports_the_drained_pool_while_the_service_runs(tmp_path, monkeypatch,
                                                                    service_state, native_check):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    checks = []
    monkeypatch.setattr(plugin, '_get_active_control', lambda: 'd' * 32)
    monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: service_state)
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt', lambda: ({'stage': 'NOT_STARTED'}, None))
    monkeypatch.setattr(plugin, '_drained_pool_generation', lambda host, control, native_check=True: (
        checks.append(native_check) or 'c' * 64))
    inventory = plugin._decorate_backend_maintenance_inventory(
        {'candidates': []}, {'host_zram': {'pool_generation': ''}}, {'hostUuid': HOST})
    assert inventory['poolGeneration'] == 'c' * 64
    assert checks and set(checks) == {native_check}


def test_activation_waits_for_a_safe_sample_from_a_restarted_service(tmp_path, monkeypatch):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
    plugin.maintenance_activation_poll_interval = 0
    samples = [{'host': {'qualified': False, 'safe': False}},
               {'host': {'qualified': True, 'safe': False}},
               {'host': {'qualified': True, 'safe': True}}]
    seen = []

    def state(action, payload):
        seen.append(action)
        return samples[min(len(seen), len(samples)) - 1]

    monkeypatch.setattr(plugin, '_service_request', state)
    ttls = []
    monkeypatch.setattr(plugin, '_native_observation_is_fresh', lambda value, ttl, now=None: ttls.append(ttl) or True)
    assert plugin._await_safe_host_sample() is True
    assert ttls and max(ttls) <= 1, 'the sample must stay current until the service reads it'

    assert seen == ['state', 'state', 'state']
    plugin.maintenance_activation_host_wait = 0
    samples[:] = [{'host': {'qualified': True, 'safe': False}}]
    assert plugin._await_safe_host_sample() is False


def _drain_reconcile_fixture(tmp_path, monkeypatch):
    with open('/proc/sys/kernel/random/boot_id') as stream:
        boot_id = stream.read().strip()
    operation_uuid, pool_generation, device = 'drain-concurrent-poll', 'b' * 64, '/dev/zram0'
    plugin = MemoryOptimizationPlugin()
    drain_dir, operation_dir = tmp_path / 'drain', tmp_path / 'operations'
    config_path, binary_path = tmp_path / 'drain-config.json', tmp_path / 'zram-efficiency'
    config_path.write_text('{}')
    binary_path.write_text('fixture')
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operation_dir),
                      'drainDir': str(drain_dir), 'drainConfig': str(config_path),
                      'drainBinary': str(binary_path)})
    receipt_path = drain_dir / (operation_uuid + '.receipt.json')
    receipt = {'pool_generation': pool_generation, 'device': device,
               'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED', 'active': False, 'reset_performed': False}
    receipt_path.parent.mkdir()
    receipt_path.write_text(json.dumps(receipt))
    operation_dir.mkdir(exist_ok=True)
    (operation_dir / (operation_uuid + '.drain-intent.json')).write_text(json.dumps({
        'operationUuid': operation_uuid, 'bootId': boot_id, 'poolGeneration': pool_generation,
        'device': device, 'unit': 'zstack-memory-drain-' + operation_uuid,
        'receiptPath': str(receipt_path), 'configPath': plugin.drain_config}))
    command = {'hostUuid': HOST, 'operationUuid': operation_uuid, 'action': 'drain'}
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    return plugin, command, receipt


def _busy_drain_check(argv, **kwargs):
    raise subprocess.CalledProcessError(
        1, argv, output=b'{"error":"state directory already in use: resource temporarily unavailable"}')


def test_drain_check_blocked_by_a_concurrent_poll_stays_in_progress(tmp_path, monkeypatch):
    plugin, command, _ = _drain_reconcile_fixture(tmp_path, monkeypatch)
    assert plugin._record_operation(command, 'DRAINING', {
        'success': True, 'status': 'Draining', 'operationUuid': command['operationUuid']})
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output', _busy_drain_check)
    result = plugin._reconcile_stock_drain(command, plugin._load_operation(command))
    assert result['status'] == 'Draining' and result['success'] is True, result
    assert plugin._load_operation(command)['stage'] == 'DRAINING'


def test_failed_recheck_never_downgrades_a_confirmed_drain(tmp_path, monkeypatch):
    plugin, command, receipt = _drain_reconcile_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output',
                        lambda argv, **kwargs: json.dumps(receipt).encode('utf-8'))
    assert plugin._record_operation(command, 'DRAINING', {
        'success': True, 'status': 'Draining', 'operationUuid': command['operationUuid']})
    confirmed = plugin._reconcile_stock_drain(command, plugin._load_operation(command))
    assert confirmed['status'] == 'Succeeded'
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output', _busy_drain_check)
    again = plugin._reconcile_stock_drain(command, plugin._load_operation(command))
    assert again['status'] == 'Succeeded', again
    assert plugin._load_operation(command)['stage'] == 'APPLIED'


@pytest.mark.parametrize('case,expected', [
    ('starting', 'MAINTENANCE_ACTIVATION_POOL_STARTING'),
    ('pool_ready_host_unsafe', 'MAINTENANCE_ACTIVATION_HOST_SETTLING'),
    ('pool_ready_host_unqualified', 'MAINTENANCE_ACTIVATION_HOST_SETTLING'),
    ('old_pool_host_unsafe', None),
    ('pending_host_unsafe', None),
    ('paused', None),
])
def test_activation_waits_only_for_transient_service_states(case, expected):
    old, new = 'a' * 64, 'b' * 64
    lifecycle = {'paused': False}
    pool = {'pool_generation': new, 'quality': 'native_host_device', 'reason': None}
    host = {'qualified': True, 'safe': False}
    native = {'maintenance_blocks_activation': False}
    pending = []
    if case == 'starting':
        pool = {'pool_generation': '', 'quality': 'unavailable',
                'reason': MemoryOptimizationPlugin.POOL_STARTUP_OBSERVATION_REASON}
    if case == 'pool_ready_host_unqualified':
        host = {'qualified': False, 'safe': False}
    if case == 'old_pool_host_unsafe':
        pool['pool_generation'] = old
    if case == 'pending_host_unsafe':
        pending = [{'reason': 'FIXTURE'}]
    if case == 'paused':
        lifecycle = {'paused': True}
    assert MemoryOptimizationPlugin._activation_settling_reason(
        lifecycle, pool, host, native, pending, old) == expected


def test_concurrent_drain_poll_waits_for_the_one_holding_the_control_lock(tmp_path, monkeypatch):
    plugin, command, _ = _drain_reconcile_fixture(tmp_path, monkeypatch)
    assert plugin._record_operation(command, 'DRAINING', {
        'success': True, 'status': 'Draining', 'operationUuid': command['operationUuid']})
    checks = []
    monkeypatch.setattr(memory_optimization_module.subprocess, 'check_output',
                        lambda argv, **kwargs: checks.append(argv) or b'{}')
    holder = plugin._acquire_host_control_lock()
    try:
        result = plugin._reconcile_stock_drain(command, plugin._load_operation(command))
    finally:
        plugin._release_operation(holder)
    assert result['status'] == 'Draining' and result['reasonCode'] == 'DRAIN_RECONCILE_LOCK_BUSY'
    assert checks == [] and plugin._load_operation(command)['stage'] == 'DRAINING'


@pytest.mark.parametrize('prior_ksm,blocked', [({}, False), ({'enabled': True}, True)])
def test_running_ksm_blocks_pool_preparation_only_when_the_drain_controlled_it(
        tmp_path, monkeypatch, prior_ksm, blocked):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    ops = tmp_path / 'operations'
    ops.mkdir()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(ops)})
    drain, prior = 'd' * 32, 'c' * 32
    (ops / ('%s.json' % prior)).write_text(json.dumps({
        'operationUuid': prior, 'hostUuid': HOST, 'action': 'apply', 'stage': 'APPLIED',
        'policy': {'schemaVersion': 1, 'ksm': prior_ksm, 'zram': {'enabled': True}}}))
    (ops / ('%s.json' % drain)).write_text(json.dumps({
        'operationUuid': drain, 'hostUuid': HOST, 'action': 'drain', 'stage': 'APPLIED',
        'expectedControlOperationUuid': prior, 'policy': {}}))
    monkeypatch.setattr(plugin, '_get_active_control', lambda: drain)
    monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: 'inactive')
    monkeypatch.setattr(plugin, '_drained_pool_generation', lambda host, control, native_check=True: 'e' * 64)
    monkeypatch.setattr(plugin, '_read_zram_pool_preparation_receipt', lambda: ({'stage': 'NOT_STARTED'}, None))
    monkeypatch.setattr(plugin, '_read_backend_maintenance_receipt', lambda: ({'stage': 'NOT_STARTED'}, None))
    state = tmp_path / 'state'
    (state / 'policies').mkdir(parents=True)
    (state / 'policies' / 'policies.json').write_text(json.dumps({'host': {'efficiency_enabled': False}}))
    monkeypatch.setattr(plugin, '_read_maintenance_config', lambda: (
        {'initial_efficiency_enabled': False}, str(state), '/dev/zram0'))
    real_open = open

    def ksm_running(path, *args, **kwargs):
        if path == '/sys/kernel/mm/ksm/run':
            return io.StringIO('1\n')
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr('builtins.open', ksm_running)
    reasons = plugin._zram_pool_preparation_eligibility(HOST)['zramPoolPreparationReasons']
    assert 'ZRAM_POOL_PREPARATION_EVIDENCE_UNKNOWN' not in reasons
    assert ('KSM_NOT_DISABLED' in reasons) is blocked


def test_default_capacity_side_is_resolved_by_service(tmp_path):
    plugin, _, calls, command, applied = _capacity_apply_fixture(
        tmp_path, zram={'ramLimitBytes': None})
    capacity_writes = [payload for action, payload in calls if action == 'capacity']

    assert len(capacity_writes) == 1
    assert capacity_writes[0]['logical_capacity'] == {'bytes': LOGICAL_BYTES}
    assert capacity_writes[0]['physical_memory_limit'] == {}
    assert applied['status'] == 'Draining', applied
    assert command['policy']['zram']['ramLimitBytes'] == PHYSICAL_BYTES
    result = _reconcile(plugin)
    assert result['status'] == 'Blocked', result
    assert result['reasonCode'] == 'NATIVE_POOL_UNQUALIFIED'


def test_default_capacity_sides_keep_the_request_hash_after_resolution():
    plugin = MemoryOptimizationPlugin()
    command = {'operationUuid': OPERATION, 'defaultCapacitySides': ['ramLimitBytes'],
               'policy': {'zram': {'enabled': True, 'logicalCapacityBytes': LOGICAL_BYTES}}}

    plugin._restore_default_capacity_sides(command)
    assert command['policy']['zram']['ramLimitBytes'] is None
    requested = plugin._operation_hash(command)
    MemoryOptimizationPlugin._adopt_default_capacity(command['policy']['zram'], {
        'desired': {'logical_resolved_bytes': LOGICAL_BYTES,
                    'physical_resolved_bytes': PHYSICAL_BYTES}})

    assert command['policy']['zram']['ramLimitBytes'] == PHYSICAL_BYTES
    assert plugin._operation_hash(command) == requested
    with pytest.raises(ValueError):
        plugin._restore_default_capacity_sides({'defaultCapacitySides': ['enabled'],
                                                'policy': {'zram': {}}})


@pytest.mark.parametrize('pause_controlled_ksm,chain_intact', [(True, True), (False, True), (True, False)])
def test_pause_and_drain_after_resume_use_the_resumed_apply(tmp_path, monkeypatch,
                                                            pause_controlled_ksm, chain_intact):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    ops = tmp_path / 'operations'
    ops.mkdir()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(ops)})
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    boot = MemoryOptimizationPlugin._current_boot_id()
    apply_uuid = 'a' * 32
    records = [{'operationUuid': apply_uuid, 'action': 'apply', 'stage': 'APPLIED', 'hostUuid': HOST,
                'bootId': boot, 'policy': {'schemaVersion': 1, 'ksm': {'enabled': True}}}]
    control = apply_uuid
    # Two pause/resume rounds: the second pause is fenced on the first resume.
    for pause_uuid, resume_uuid in (('b' * 32, 'c' * 32), ('d' * 32, 'e' * 32)):
        pause_state = {'phase': 'PAUSED'}
        if pause_controlled_ksm:
            pause_state['ksmLifecycle'] = {'controlOperationUuid': control, 'runBeforePause': '1',
                                           'ksmWasActive': True, 'ksmtunedWasActive': False}
        records.append({'operationUuid': pause_uuid, 'action': 'pause', 'stage': 'APPLIED',
                        'hostUuid': HOST, 'bootId': boot, 'expectedControlOperationUuid': control,
                        'readback': {'status': 'Succeeded', 'state': pause_state}})
        records.append({'operationUuid': resume_uuid, 'action': 'resume', 'stage': 'APPLIED',
                        'hostUuid': HOST, 'bootId': boot, 'expectedControlOperationUuid': pause_uuid,
                        'policy': {}})
        control = resume_uuid
    for record in records if chain_intact else records[1:]:
        (ops / ('%s.json' % record['operationUuid'])).write_text(json.dumps(record))
    monkeypatch.setattr(plugin, '_get_active_control', lambda: control)
    cleared = []
    monkeypatch.setattr(plugin, '_managed_ksm_clear_ack',
                        lambda require_ksm_only=False, control_uuid=None: cleared.append(control_uuid))

    command = {'expectedControlOperationUuid': control}
    if not chain_intact:
        with pytest.raises(ValueError, match='KSM_CONTROL_OPERATION_UNKNOWN'):
            plugin._validate_maintenance_control_before_effects(command)
        with pytest.raises(RuntimeError, match='KSM_CONTROL_OPERATION_UNKNOWN'):
            plugin._control_managed_ksm('drain', command)
        return
    plugin._validate_maintenance_control_before_effects(command)
    for action in ('pause', 'drain'):
        assert plugin._control_managed_ksm(action, command) is None
    assert cleared == ([apply_uuid, apply_uuid] if pause_controlled_ksm else [])
    assert plugin._ksm_owner_apply(records[-1]) == (records[0] if pause_controlled_ksm else None)


def _control_journal_plugin(tmp_path, monkeypatch, records, active, boot='new-boot'):
    plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
    ops = tmp_path / 'operations'
    ops.mkdir()
    plugin.configure({'hostUuid': HOST, 'operationDir': str(ops)})
    monkeypatch.setattr(plugin, '_load_host_uuid', lambda: HOST)
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: boot)
    for record in records:
        (ops / ('%s.json' % record['operationUuid'])).write_text(json.dumps(record))
    (ops / 'active-control').write_text(active)
    plugin.active_control_path = str(ops / 'active-control')
    return plugin


def _reconcile_operation(plugin, operation_uuid, **extra):
    command = dict({'hostUuid': HOST, 'operationUuid': operation_uuid, 'action': 'reconcile',
                    'scope': 'Host', 'resourceUuid': HOST, 'policy': {}}, **extra)
    return json.loads(plugin.reconcile({'body': json.dumps(command)}))


@pytest.mark.parametrize('boot,active,status', [
    ('old-boot', 'd' * 32, 'Failed'), ('new-boot', 'd' * 32, 'Failed'), ('new-boot', 'e' * 32, 'Unknown')])
def test_drained_activation_without_intent_is_rejected_while_the_drain_holds_control(
        tmp_path, monkeypatch, boot, active, status):
    activation, drain = 'a' * 32, 'd' * 32
    plugin = _control_journal_plugin(tmp_path, monkeypatch, [
        {'operationUuid': activation, 'action': 'apply', 'stage': 'UNKNOWN', 'hostUuid': HOST,
         'bootId': 'old-boot', 'expectedControlOperationUuid': drain,
         'maintenanceProof': {'drainOperationUuid': drain, 'maintenanceReady': True},
         'policy': {'schemaVersion': 1, 'zram': {'enabled': True}}}], active, boot)

    result = _reconcile_operation(plugin, activation)

    assert result['status'] == status, result
    if status == 'Failed':
        assert result['state']['activationRejected'] is True
        assert plugin._load_operation({'operationUuid': activation})['stage'] == 'REJECTED'
        assert _reconcile_operation(plugin, activation) == result
    else:
        assert result['reasonCode'] == 'MAINTENANCE_ACTIVATION_CONTROL_MISMATCH'
    assert plugin._get_active_control() == active


@pytest.mark.parametrize('stage,active,status,control_after', [
    ('DRAINING', 'd' * 32, 'Failed', 'p' * 32),
    ('PREPARING', 'p' * 32, 'Failed', 'p' * 32),
    ('DRAINING', 'e' * 32, 'Unknown', 'e' * 32)])
def test_drain_interrupted_by_reboot_returns_control_to_the_prior_apply(
        tmp_path, monkeypatch, stage, active, status, control_after):
    drain, prior = 'd' * 32, 'p' * 32
    plugin = _control_journal_plugin(tmp_path, monkeypatch, [
        {'operationUuid': drain, 'action': 'drain', 'stage': stage, 'hostUuid': HOST,
         'bootId': 'old-boot', 'expectedControlOperationUuid': prior, 'policy': {}}], active)

    result = _reconcile_operation(plugin, drain)

    assert result['status'] == status, result
    assert result['reasonCode'] == ('DRAIN_INTERRUPTED_BY_REBOOT' if status == 'Failed'
                                    else 'DRAIN_CONTROL_MISMATCH')
    assert plugin._get_active_control() == control_after
    if status == 'Failed':
        assert _reconcile_operation(plugin, drain) == result


def test_drain_completed_before_reboot_keeps_its_receipt(tmp_path, monkeypatch):
    drain = 'd' * 32
    receipt = {'success': True, 'status': 'Succeeded', 'operationUuid': drain,
               'state': {'phase': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED'}}
    plugin = _control_journal_plugin(tmp_path, monkeypatch, [
        {'operationUuid': drain, 'action': 'drain', 'stage': 'APPLIED', 'hostUuid': HOST,
         'bootId': 'old-boot', 'expectedControlOperationUuid': 'p' * 32, 'policy': {},
         'readback': receipt}], drain)

    assert _reconcile_operation(plugin, drain) == receipt
    assert plugin._get_active_control() == drain


def test_unrecorded_operation_from_before_the_reboot_is_sealed_as_never_issued(tmp_path, monkeypatch):
    plugin = _control_journal_plugin(tmp_path, monkeypatch, [], 'p' * 32)
    monkeypatch.setattr(plugin, '_boot_epoch_millis', lambda: 2000000)

    result = _reconcile_operation(plugin, 'd' * 32, reconcileAction='seal-if-never-issued',
                                  bootId='new-boot', taskSubmittedAt=1000000)

    assert result['status'] == 'Failed', result
    assert result['reasonCode'] == 'OPERATION_NEVER_ISSUED'


@pytest.mark.parametrize('intent,active,status', [
    (False, 'd' * 32, 'Failed'), (True, 'd' * 32, 'Unknown'), (False, 'e' * 32, 'Unknown')])
def test_drained_apply_failing_before_activation_intent_is_rejected_at_once(
        tmp_path, monkeypatch, intent, active, status):
    activation, drain = 'a' * 32, 'd' * 32
    record = {'operationUuid': activation, 'action': 'apply', 'stage': 'PREPARING', 'hostUuid': HOST,
              'bootId': 'new-boot', 'expectedControlOperationUuid': drain}
    if intent:
        record['activationIntent'] = {'operationUuid': activation}
    plugin = _control_journal_plugin(tmp_path, monkeypatch, [record], active)
    unknown = {'success': False, 'status': 'Unknown', 'reasonCode': 'SERVICE_CAPACITY_TARGET_NOT_VERIFIED',
               'state': {'phase': 'UNKNOWN'}, 'operationUuid': activation}

    result = plugin._unissued_activation_rejection(
        {'operationUuid': activation, 'expectedControlOperationUuid': drain}, unknown)

    assert result['status'] == status
    if status == 'Failed':
        assert result['state']['activationRejected'] is True
        assert result['reasonCode'] == 'SERVICE_CAPACITY_TARGET_NOT_VERIFIED'
    else:
        assert result is unknown


def test_rebooted_drain_reconcile_finishes_a_control_return_cut_short(tmp_path, monkeypatch):
    drain, prior = 'd' * 32, 'p' * 32
    rejected = {'success': False, 'status': 'Failed', 'reasonCode': 'DRAIN_INTERRUPTED_BY_REBOOT',
                'state': {'phase': 'FAILED'}, 'operationUuid': drain}
    plugin = _control_journal_plugin(tmp_path, monkeypatch, [
        {'operationUuid': drain, 'action': 'drain', 'stage': 'REJECTED', 'hostUuid': HOST,
         'bootId': 'old-boot', 'expectedControlOperationUuid': prior, 'policy': {},
         'readback': rejected}], drain)

    assert _reconcile_operation(plugin, drain) == rejected
    assert plugin._get_active_control() == prior


@pytest.mark.parametrize('action', ['drain', 'apply'])
def test_reboot_and_activation_reconcile_ignore_another_hosts_receipt(tmp_path, monkeypatch, action):
    operation, drain = ('d' * 32 if action == 'drain' else 'a' * 32), 'd' * 32
    receipt = {'success': False, 'status': 'Failed', 'reasonCode': 'FOREIGN', 'operationUuid': operation,
               'state': {'phase': 'FAILED', 'activationRejected': True}}
    record = {'operationUuid': operation, 'action': action, 'stage': 'REJECTED', 'hostUuid': 'other-host',
              'bootId': 'old-boot', 'expectedControlOperationUuid': 'p' * 32 if action == 'drain' else drain,
              'policy': {}, 'readback': receipt}
    if action == 'apply':
        record['maintenanceProof'] = {'drainOperationUuid': drain}
    plugin = _control_journal_plugin(tmp_path, monkeypatch, [record], drain)

    result = _reconcile_operation(plugin, operation)

    assert result['status'] == 'Unknown', result
    assert result != receipt


@pytest.mark.parametrize('action', ['drain', 'apply'])
def test_reboot_and_activation_reconcile_wait_for_the_host_control_lock(tmp_path, monkeypatch, action):
    operation, drain = ('d' * 32 if action == 'drain' else 'a' * 32), 'd' * 32
    record = {'operationUuid': operation, 'action': action, 'stage': 'PREPARING', 'hostUuid': HOST,
              'bootId': 'old-boot', 'expectedControlOperationUuid': 'p' * 32 if action == 'drain' else drain,
              'policy': {}}
    if action == 'apply':
        record['maintenanceProof'] = {'drainOperationUuid': drain}
    plugin = _control_journal_plugin(tmp_path, monkeypatch, [record], 'p' * 32 if action == 'drain' else drain)
    held = plugin._acquire_host_control_lock()
    try:
        result = _reconcile_operation(plugin, operation)
    finally:
        plugin._release_operation(held)

    assert result['status'] == 'Draining', result
    assert result['reasonCode'] == 'RECONCILE_LOCK_BUSY'
    assert plugin._load_operation({'operationUuid': operation})['stage'] == 'PREPARING'

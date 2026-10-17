import json
import hashlib
import io
import os
import re
import subprocess
import time

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
                            capacity_requested=True, include_zram=True):
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
                                'writeback': {'enabled': False, 'batch_bytes': 8388608,
                                              'idle_observation_seconds': 10,
                                              'operation_interval_seconds': 5}}},
    }
    calls = []

    def service_call(action, payload):
        calls.append((action, payload))
        if action == 'capacity-state':
            return dict(service_state['capacity'])
        if action == 'host-cpu-state':
            return dict(service_state['cpu'])
        if action == 'tuning-state':
            return dict(service_state['tuning'])
        if action == 'capacity':
            shared['revision'] += 1
            configured_now = _configured(LOGICAL_BYTES, PHYSICAL_BYTES)
            desired_now = {'configured': configured_now,
                           'basis_host_memory_bytes': 8 * 1024 * 1024 * 1024,
                           'logical_resolved_bytes': LOGICAL_BYTES,
                           'physical_resolved_bytes': PHYSICAL_BYTES}
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
            service_state['tuning'] = {
                '_http_status': 200, 'revision': payload['expected_revision'],
                'request_id': payload['request_id'], 'settings': payload['settings']}
            return dict(service_state['tuning'])
        raise AssertionError('unexpected service action: %s' % action)

    plugin = MemoryOptimizationPlugin(service_call=service_call)
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations')})
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


def _reconcile(plugin):
    return json.loads(plugin.reconcile({'body': json.dumps({
        'hostUuid': HOST, 'operationUuid': OPERATION})}))


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
                                    'active_prior_preparation_ksm',
                                    'active_prior_preparation_wrong_uuid',
                                    'active_prior_preparation_wrong_capacity',
                                    'active_prior_preparation_wrong_boot',
                                    'active_prior_preparation_enabled',
                                    'active_prior_preparation_bad_current_receipt',
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
    if tamper not in (None, 'corrupt_historical_preparation', 'ordinary_registration', 'ksm_history', 'ksm_before_prepare',
                      'ksm_before_and_after_prepare', 'active_prepared_backend_ksm',
                      'active_prepared_backend_ksm_wrong_resource',
                      'active_prepared_backend_ksm_wrong_capacity',
                      'active_prepared_backend_ksm_wrong_boot',
                      'active_prepared_backend_ksm_enabled',
                      'active_prior_preparation_ksm',
                      'active_prior_preparation_wrong_uuid',
                      'active_prior_preparation_wrong_capacity',
                      'active_prior_preparation_wrong_boot',
                      'active_prior_preparation_enabled',
                      'active_prior_preparation_bad_current_receipt',
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
                  'late_host_uuid',
                  'corrupt_historical_preparation',
                  'ordinary_registration', 'ksm_history', 'ksm_before_prepare',
                  'ksm_before_and_after_prepare', 'active_prepared_backend_ksm',
                  'active_prepared_backend_ksm_wrong_resource',
                  'active_prepared_backend_ksm_wrong_capacity',
                  'active_prepared_backend_ksm_wrong_boot',
                  'active_prepared_backend_ksm_enabled',
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
        if tamper == 'active_prepared_backend_ksm':
            # Exercise the real no-pool admission and inventory decorator with
            # the prepared-backend KSM active record, not only the proof helper.
            monkeypatch.setattr(plugin, '_maintenance_service_state', lambda: 'active')
            inventory = plugin._fresh_backend_maintenance_inventory(HOST)
            assert inventory['poolGeneration'] == 'none', inventory
            assert plugin._first_use_no_pool_verified() is True
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


@pytest.mark.parametrize('zram,writeback,cpu_enabled', [
    ({'enabled': False}, None, False),
    ({'cpuThresholdPercent': 5}, None, False),
    ({}, {'enabled': False}, False),
    ({'enabled': True}, None, False),
    ({}, None, True),
])
def test_explicit_cpu_policy_or_guard_requires_its_real_cpu_receipt(
        tmp_path, zram, writeback, cpu_enabled):
    plugin, _, calls, _, applied = _capacity_apply_fixture(
        tmp_path, zram=zram, writeback=writeback, cpu_enabled=cpu_enabled)
    assert [payload for action, payload in calls if action == 'host-cpu']
    record = _journal(plugin)
    sections = record['applyEvidence']['state']['sections']
    assert 'cpu' in sections
    if cpu_enabled:
        assert 'cpuGuard' in sections
    result = _reconcile(plugin)
    # Valid CPU evidence remains subject to the same strict capacity proof.
    assert result['status'] == 'Blocked'

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
                                    'active_service_disable_wrong_boot',
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
        if history == 'active_service_disable_wrong_boot':
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
                    'cleared_ksm_schema_v1', 'active_service_disable'):
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
                                    'active_writeback_disable_wrong_boot',
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
        if outcome == 'active_writeback_disable_wrong_boot':
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
        if outcome == 'active_writeback_disable':
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
    if outcome == 'active_writeback_disable':
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

    if outcome in ('stopped', 'active_writeback_disable', 'cleared_ksm_reboot') or worker_failed or outcome in (
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

    if outcome in ('stopped', 'active_writeback_disable', 'cleared_ksm_reboot') or worker_failed:
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
        if outcome in ('stopped', 'active_writeback_disable', 'cleared_ksm_reboot'):
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
                        lambda argv: json.dumps(receipt).encode('utf-8'))

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

    def native_check(argv):
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

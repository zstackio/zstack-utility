import json

import pytest

from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin


HOST = 'host-capacity-reconcile'
OPERATION = 'capacity-only-reconcile'
LOGICAL_BYTES = 1024 * 1024 * 1024
PHYSICAL_BYTES = 512 * 1024 * 1024
OLD_LOGICAL_BYTES = 512 * 1024 * 1024
OLD_PHYSICAL_BYTES = 256 * 1024 * 1024


def _configured(logical, physical):
    return {'logical_capacity': {'bytes': logical},
            'physical_memory_limit': {'bytes': physical}}


def _capacity_apply_fixture(tmp_path, zram=None, writeback=None, cpu_enabled=False):
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
    policy = {'zram': dict({'logicalCapacityBytes': LOGICAL_BYTES,
                            'ramLimitBytes': PHYSICAL_BYTES}, **(zram or {}))}
    if writeback is not None:
        policy['writeback'] = writeback
    command = {'hostUuid': HOST, 'scope': 'Host', 'action': 'apply',
               'operationUuid': OPERATION, 'desiredRevision': 12, 'policy': policy}
    applied = plugin._normalize_response(
        plugin._apply_service_policy_fail_closed(command), 'apply', command)
    assert plugin._record_operation(command, 'UNKNOWN', applied)
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

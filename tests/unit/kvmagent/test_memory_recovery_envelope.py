"""Exercise the standard KVM JSON envelope at the recovery HTTP handler."""
import json
import os
import re
import time
from unittest.mock import Mock

import pytest

from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin


@pytest.fixture
def recovery(tmp_path):
    service = Mock(side_effect=AssertionError('Unqualified recovery must not call the service'))
    plugin = MemoryOptimizationPlugin(service_call=service)
    plugin.configure({'hostUuid': '1' * 32, 'operationDir': str(tmp_path)})
    command = {
        'hostUuid': '1' * 32, 'resourceUuid': '1' * 32, 'scope': 'Host',
        'action': 'recoverUncertain', 'operationUuid': '2' * 32,
        'expectedControlOperationUuid': '3' * 32, 'desiredRevision': 9,
        'targetSnapshotGeneration': 'policy-9', 'expectedInstanceGeneration': None,
        'communication': {'requestBytes': 1048576, 'responseBytes': 1048576,
                          'communicationSeconds': 60},
        'policy': {}, 'recovery': {'expectedHostBootId': plugin._current_boot_id(),
                                  'expectedPoolGeneration': 'a' * 64, 'confirmed': True},
    }
    return plugin, command, service


@pytest.mark.parametrize('addons', [None, {}, {'qcow2Options': ' -o cluster_size=2097152 '}])
def test_standard_kvm_envelope_reaches_existing_proof_checks(recovery, addons):
    plugin, command, service = recovery
    if addons is not None:
        command['kvmHostAddons'] = addons
    request = {'body': json.dumps(command)}
    response = json.loads(plugin.apply_request(request))
    # Accepting transport metadata must not skip the original-operation proof.
    assert response['reasonCode'] == 'RECOVERY_OLD_POLICY_UNQUALIFIED'
    assert response['status'] == 'Failed'
    assert response['state']['phase'] == 'RECOVERY_NOT_ISSUED'
    record = plugin._load_operation(command)
    assert record['stage'] == 'REJECTED'
    parsed = plugin._request_body(request)
    if addons is not None:
        assert parsed['kvmHostAddons'] == addons
    assert record['requestHash'] == plugin._operation_hash(parsed)
    assert plugin._get_active_control() is None
    assert json.loads(plugin.apply_request({'body': json.dumps(command)})) == response
    service.assert_not_called()


@pytest.mark.parametrize('invalid', ['top-level', 'recovery', 'identity'])
def test_standard_addons_do_not_allow_invalid_recovery_fields(recovery, invalid):
    plugin, command, service = recovery
    command['kvmHostAddons'] = {'qcow2Options': ' -o cluster_size=2097152 '}
    if invalid == 'top-level':
        command['unexpected'] = True
    elif invalid == 'recovery':
        command['recovery']['unexpected'] = True
    else:
        command['expectedControlOperationUuid'] = 'not-an-operation'
    response = json.loads(plugin.apply_request({'body': json.dumps(command)}))
    assert response['reasonCode'] == 'RECOVERY_REQUEST_INVALID'
    assert plugin._load_operation(command) is None
    assert plugin._get_active_control() is None
    service.assert_not_called()


@pytest.fixture
def rejected_recovery(recovery):
    plugin, original, service = recovery
    anchor = dict(original, operationUuid='4' * 32, action='apply',
                  desiredRevision=8, policy={'zram': {'enabled': True}})
    assert plugin._record_operation(anchor, 'APPLIED', {'success': True, 'status': 'Succeeded'})
    plugin._set_active_control(anchor['operationUuid'])
    old = dict(anchor, operationUuid='3' * 32, desiredRevision=9)
    assert plugin._record_operation(old, 'UNKNOWN', {'success': False, 'status': 'Unknown'})
    query = dict(original, action='reconcile',
                 reconcileAction='seal-rejected-recovery', classification='RECOVERY_REQUEST_INVALID',
                 recoveryRequestHash='b' * 64, bootId=plugin._current_boot_id(),
                 taskSubmittedAt=int(time.time() * 1000))
    live = {'_http_status': 200, 'pending_operations': [],
            'host_zram': {'pool_generation': 'a' * 64}}
    operations = {'_http_status': 200, 'cq': {'C': 0, 'Q': 0}}

    def readonly(action, payload):
        if action == 'monitor-state':
            return live
        if action == 'operations':
            return operations
        raise AssertionError('Recovery rejection must not issue a write: ' + action)
    service.side_effect = readonly
    return plugin, original, query, service, live, operations


@pytest.mark.parametrize('defect', [None, 'empty-delta', 'changed-delta', 'wrong-type',
                                   'unknown-field', 'missing-proof', 'changed-proof',
                                   'same-boot', 'wrong-control', 'unresolved',
                                   'float-delta', 'numeric-target', 'implicit-zero'])
def test_previous_boot_scan_delta_requires_complete_matching_native_proof(recovery, defect):
    plugin, command, service = recovery
    old = dict(command, action='apply', operationUuid='4' * 32, desiredRevision=8,
               policyMode='delta', policy={'ksm': {'pagesToScan': 2000, 'sleepMillis': 20}})
    ack = {'run': '0', 'configRevision': '8', 'pages_to_scan': '2000',
           'sleep_millisecs': '20', 'use_zero_pages': '0'}
    assert plugin._record_operation(old, 'APPLIED', {
        'success': True, 'status': 'Succeeded', 'appliedRevision': 8, 'ksmReadback': ack})
    saved = plugin._load_operation(old)
    saved['bootId'] = 'previous-boot'
    command.update(action='apply', policyMode='delta', confirmedKsmReconnect=True,
                   reconnectObservationBootId=plugin._current_boot_id(),
                   expectedControlOperationUuid=old['operationUuid'],
                   policy={'ksm': {'enabled': False, 'pagesToScan': 2000, 'sleepMillis': 20}})
    if defect == 'empty-delta':
        saved['policy']['ksm'] = {}
    elif defect == 'changed-delta':
        saved['policy']['ksm']['pagesToScan'] = 2500
    elif defect == 'wrong-type':
        saved['policy']['ksm']['enabled'] = 0
    elif defect == 'float-delta':
        saved['policy']['ksm']['pagesToScan'] = 2000.0
    elif defect == 'numeric-target':
        command['policy']['ksm']['enabled'] = 0
    elif defect == 'implicit-zero':
        command['policy']['ksm']['zeroPagesEnabled'] = False
    elif defect == 'unknown-field':
        saved['policy']['ksm']['unrecognized'] = 1
    elif defect == 'missing-proof':
        del saved['readback']['ksmReadback']['run']
    elif defect == 'changed-proof':
        saved['readback']['ksmReadback']['run'] = '1'
    elif defect == 'same-boot':
        saved['bootId'] = plugin._current_boot_id()
    elif defect == 'unresolved':
        assert plugin._record_operation(dict(old, operationUuid='5' * 32), 'UNKNOWN')
    saved['policyHash'] = plugin._policy_digest(saved['policy'])
    assert plugin._write_operation_record(saved)
    plugin._set_active_control('6' * 32 if defect == 'wrong-control' else old['operationUuid'])
    before = plugin._load_operation(old)
    result = plugin._validate_confirmed_ksm_reconnect(command)
    assert result == (None if defect is None else 'KSM_RECONNECT_PROOF_UNQUALIFIED')
    assert plugin._load_operation(old) == before
    assert plugin._load_operation(command) is None
    service.assert_not_called()


def test_rejected_recovery_seals_only_child_and_blocks_original_id_replay(rejected_recovery):
    plugin, original, query, service, _, _ = rejected_recovery
    old = plugin._load_operation({'operationUuid': '3' * 32})
    result = json.loads(plugin.reconcile({'body': json.dumps(query)}))
    assert result['status'] == 'Failed'
    assert result['state']['phase'] == 'RECOVERY_NOT_ISSUED'
    assert plugin._load_operation(original)['stage'] == 'REJECTED'
    assert plugin._load_operation({'operationUuid': '3' * 32}) == old
    assert plugin._get_active_control() == '4' * 32
    service.reset_mock()
    # Simulate restart and a lost reply: the durable rejection remains enough
    # to answer the query, but never authorizes the original write to run.
    restarted = MemoryOptimizationPlugin(service_call=service)
    restarted.configure({'hostUuid': '1' * 32, 'operationDir': plugin.operation_dir})
    repeated = dict(query)
    repeated.pop('classification')
    repeated.pop('reconcileAction')
    assert json.loads(restarted.reconcile({'body': json.dumps(repeated)})) == result
    assert json.loads(restarted.apply_request({'body': json.dumps(original)}))['status'] == 'Unknown'
    service.assert_not_called()


def test_recovery_rejection_boolean_schema_is_not_an_integer_version(rejected_recovery):
    plugin, original, query, service, _, _ = rejected_recovery
    result = json.loads(plugin.reconcile({'body': json.dumps(query)}))
    assert result['status'] == 'Failed'
    result['state']['recoveryRejectionProof']['schemaVersion'] = True
    assert plugin._update_operation_record(original['operationUuid'], 'REJECTED', result)
    before = plugin._load_operation(original)
    service.reset_mock()
    assert json.loads(plugin.reconcile({'body': json.dumps(query)}))['status'] == 'Unknown'
    assert plugin._load_operation(original) == before
    assert plugin._get_active_control() == '4' * 32
    service.assert_not_called()


@pytest.mark.parametrize('invalid', ['no-proof', 'boot', 'host', 'hash', 'old-journal',
                                    'control', 'inflight', 'pending', 'generation', 'journal', 'lock',
                                    'preboot', 'future', 'wrong-recovery-boot', 'revision'])
def test_rejected_recovery_missing_or_conflicting_evidence_stays_unknown(rejected_recovery, invalid):
    plugin, original, query, service, live, operations = rejected_recovery
    held = None
    if invalid == 'no-proof':
        query.pop('classification')
    elif invalid == 'boot':
        query['bootId'] = 'other-boot'
    elif invalid == 'host':
        query['hostUuid'] = '5' * 32
    elif invalid == 'hash':
        query['recoveryRequestHash'] = ''
    elif invalid == 'old-journal':
        plugin._update_operation_record('3' * 32, 'APPLIED', {'status': 'Succeeded'})
    elif invalid == 'control':
        plugin._set_active_control(original['operationUuid'])
    elif invalid == 'inflight':
        operations['cq']['Q'] = 1
    elif invalid == 'pending':
        live['pending_operations'] = ['operation']
    elif invalid == 'generation':
        live['host_zram']['pool_generation'] = 'c' * 64
    elif invalid == 'journal':
        assert plugin._record_operation(original, 'PREPARING')
    elif invalid == 'lock':
        held = plugin._acquire_host_control_lock()
    elif invalid == 'preboot':
        query['taskSubmittedAt'] = plugin._boot_epoch_millis() - 1
    elif invalid == 'future':
        query['taskSubmittedAt'] += 60000
    elif invalid == 'wrong-recovery-boot':
        query['recovery']['expectedHostBootId'] = 'other-boot'
    elif invalid == 'revision':
        query['desiredRevision'] = True
    before = plugin._load_operation(original)
    try:
        result = json.loads(plugin.reconcile({'body': json.dumps(query)}))
    finally:
        plugin._release_operation(held)
    assert result['status'] == 'Unknown'
    assert plugin._load_operation(original) == before


def test_recovery_seal_journal_failure_does_not_claim_not_issued(rejected_recovery, monkeypatch):
    plugin, original, query, service, _, _ = rejected_recovery
    monkeypatch.setattr(plugin, '_record_operation', lambda *args: False)
    result = json.loads(plugin.reconcile({'body': json.dumps(query)}))
    assert result['status'] == 'Unknown'
    assert result['reasonCode'] == 'RECOVERY_REJECTION_JOURNAL_UNAVAILABLE'
    assert plugin._load_operation(original) is None
    assert plugin._get_active_control() == '4' * 32


@pytest.mark.parametrize('linked', ['active-control', 'original', 'anchor'])
def test_recovery_seal_rejects_linked_proof_before_service_calls(rejected_recovery, linked):
    plugin, original, query, service, _, _ = rejected_recovery
    path = (plugin.active_control_path if linked == 'active-control' else
            plugin._operation_path(('3' if linked == 'original' else '4') * 32))
    target = path + '.saved'
    os.rename(path, target)
    os.symlink(target, path)
    with open(target, 'rb') as stream:
        saved = stream.read()
    old = plugin._load_operation({'operationUuid': '3' * 32})
    anchor = plugin._load_operation({'operationUuid': '4' * 32})

    result = json.loads(plugin.reconcile({'body': json.dumps(query)}))

    assert result['status'] == 'Unknown', result
    assert plugin._load_operation(original) is None
    assert plugin._load_operation({'operationUuid': '3' * 32}) == old
    assert plugin._load_operation({'operationUuid': '4' * 32}) == anchor
    assert plugin._get_active_control() == '4' * 32
    assert os.path.islink(path)
    with open(target, 'rb') as stream:
        assert stream.read() == saved
    service.assert_not_called()


@pytest.fixture
def ksm_reconnect(recovery, monkeypatch, tmp_path, request):
    plugin, _, service = recovery
    enabled, zero_supported = getattr(request, 'param', (False, True))
    ksm = {'enabled': enabled, 'pagesToScan': 2500, 'sleepMillis': 40}
    if zero_supported:
        ksm['zeroPagesEnabled'] = True
    old = {'hostUuid': '1' * 32, 'scope': 'Host', 'action': 'apply',
           'operationUuid': '4' * 32, 'desiredRevision': 8,
           'policy': {'schemaVersion': 1, 'ksm': ksm}}
    proof = {'run': '1' if enabled else '0', 'configRevision': '8', 'pages_to_scan': '2500',
             'sleep_millisecs': '40', 'use_zero_pages': '1' if zero_supported else 'unsupported'}
    assert plugin._record_operation(old, 'APPLIED', {
        'success': True, 'status': 'Succeeded', 'appliedRevision': 8, 'ksmReadback': proof})
    record = plugin._load_operation(old)
    record['bootId'] = 'previous-boot'
    with open(plugin._operation_path(old['operationUuid']), 'w') as stream:
        json.dump(record, stream)
    plugin._set_active_control(old['operationUuid'])
    command = dict(old, operationUuid='2' * 32, desiredRevision=9, policyMode='delta',
                   confirmedKsmReconnect=True, reconnectObservationBootId=plugin._current_boot_id(),
                   expectedControlOperationUuid=old['operationUuid'])
    native = {'run': '0', 'pages_to_scan': '100', 'sleep_millisecs': '20',
              'use_zero_pages': '0' if zero_supported else 'unsupported'}
    config_path = tmp_path / 'ksmtuned.conf'
    plugin.KSM_CONF = str(config_path)
    calls = []

    def publish(content):
        config_path.write_text(content)

    def ack():
        value = dict(native)
        value['configRevision'] = re.search(r'^# CONFIG_REVISION=(\d+)',
                                            config_path.read_text(), re.M).group(1)
        return value

    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {'supported': True, 'ksm': True,
                                                                 'ksmZeroPages': zero_supported})
    monkeypatch.setattr(plugin, '_verify_native_ksm_profile', lambda: None)
    monkeypatch.setattr(plugin, '_native_service_state',
                        lambda unit, kind: 'inactive' if kind == 'active' else 'disabled')
    monkeypatch.setattr(plugin, '_publish_ksm_config', publish)
    monkeypatch.setattr(plugin, '_write_ksm_sysfs', lambda key, value: native.update({key: value}))
    monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: native['use_zero_pages'])
    monkeypatch.setattr(plugin, '_read_ksm_ack', ack)
    monkeypatch.setattr('kvmagent.plugins.memory_optimization.subprocess.check_call',
                        lambda args: calls.append(args))
    return plugin, command, service, native, config_path, calls, record


@pytest.mark.parametrize('ksm_reconnect', [(False, True), (True, True), (False, False)], indirect=True)
def test_reconnect_restores_proven_ksm_only_and_preserves_enabled_intent(ksm_reconnect):
    plugin, command, service, native, config_path, calls, old = ksm_reconnect
    result = plugin.apply(command)
    assert result['status'] == 'Succeeded', result
    expected = dict(old['readback']['ksmReadback'], configRevision='9')
    assert result['ksmReadback'] == expected
    assert native['run'] == expected['run']
    if command['policy']['ksm']['enabled']:
        assert all(args[1] in ('start', 'enable') for args in calls)
    else:
        assert all(args[1] in ('stop', 'disable') for args in calls)
    assert plugin._load_operation({'operationUuid': '4' * 32}) == old
    assert plugin._get_active_control() == command['operationUuid']
    assert plugin._load_operation(command)['stage'] == 'APPLIED'
    before = list(calls)
    assert plugin.apply(command) == result
    assert calls == before
    service.assert_not_called()


@pytest.mark.parametrize('ksm_reconnect', [(False, False), (True, False)], indirect=True)
def test_scan_only_old_delta_restores_full_native_target_without_zero_capability(ksm_reconnect):
    plugin, command, service, native, _, _, old = ksm_reconnect
    old['policy'] = {'ksm': {key: value for key, value in old['policy']['ksm'].items()
                           if key in ('pagesToScan', 'sleepMillis')}}
    old['policyHash'] = plugin._policy_digest(old['policy'])
    assert plugin._write_operation_record(old)
    result = plugin.apply(command)
    assert result['status'] == 'Succeeded', result
    assert result['ksmReadback'] == dict(old['readback']['ksmReadback'], configRevision='9')
    assert native['run'] == ('1' if command['policy']['ksm']['enabled'] else '0')
    assert native['pages_to_scan'] == '2500'
    assert native['use_zero_pages'] == 'unsupported'
    assert plugin._load_operation({'operationUuid': old['operationUuid']}) == old
    assert plugin._get_active_control() == command['operationUuid']
    service.assert_not_called()


@pytest.mark.parametrize('invalid', ['marker', 'boot', 'same-boot', 'control', 'missing-enabled',
                                    'new-value', 'new-zram', 'policy-hash', 'receipt', 'lock',
                                    'unknown', 'recovering', 'activating'])
def test_reconnect_unproven_target_has_no_native_or_journal_writes(ksm_reconnect, invalid):
    plugin, command, service, native, config_path, calls, old = ksm_reconnect
    old_path = plugin._operation_path('4' * 32)
    held = None
    if invalid == 'marker':
        command['confirmedKsmReconnect'] = 'true'
    elif invalid == 'boot':
        command['reconnectObservationBootId'] = 'another-boot'
    elif invalid == 'same-boot':
        old['bootId'] = plugin._current_boot_id()
    elif invalid == 'control':
        plugin._set_active_control('5' * 32)
    elif invalid == 'missing-enabled':
        command['policy']['ksm'].pop('enabled')
    elif invalid == 'new-value':
        command['policy']['ksm']['pagesToScan'] = 5000
    elif invalid == 'new-zram':
        command['policy']['zram'] = {'cpuThresholdPercent': 5}
    elif invalid == 'policy-hash':
        old['policyHash'] = 'f' * 64
    elif invalid == 'receipt':
        old['readback']['ksmReadback']['pages_to_scan'] = '100'
    elif invalid == 'lock':
        held = plugin._acquire_host_control_lock()
    else:
        assert plugin._record_operation(dict(command, operationUuid='6' * 32), invalid.upper())
    with open(old_path, 'w') as stream:
        json.dump(old, stream)
    before = dict(native)
    try:
        result = plugin.apply(command)
    finally:
        plugin._release_operation(held)
    assert result['status'] == 'Unknown', (invalid, result)
    assert plugin._load_operation(command) is None
    assert plugin._load_operation({'operationUuid': '4' * 32}) == old
    assert not config_path.exists()
    assert native == before
    assert calls == []
    service.assert_not_called()


@pytest.fixture
def final_cpu_gate_recovery(tmp_path):
    host, original_uuid, anchor_uuid, recovery_uuid = ('1' * 32, '2' * 32,
                                                        '3' * 32, '4' * 32)
    plugin = MemoryOptimizationPlugin()
    plugin.configure({'hostUuid': host, 'operationDir': str(tmp_path)})
    boot = plugin._current_boot_id()
    generation = 'a' * 64
    anchor = {'hostUuid': host, 'scope': 'Host', 'action': 'apply',
              'operationUuid': anchor_uuid, 'desiredRevision': 8,
              'policy': {'schemaVersion': 1, 'zram': {'enabled': False}}}
    assert plugin._record_operation(anchor, 'APPLIED', {
        'success': True, 'status': 'Succeeded', 'appliedRevision': 8})
    plugin._set_active_control(anchor_uuid)

    original = {'hostUuid': host, 'scope': 'Host', 'action': 'apply',
                'operationUuid': original_uuid, 'desiredRevision': 9,
                'policyMode': 'delta', 'policy': {'schemaVersion': 1,
                    'writeback': {'backendResourceUuid': '5' * 32,
                                  'backendCapacityBytes': 4 << 30}}}
    before = {'_http_status': 200, 'revision': 12, 'efficiency_enabled': True,
              'idle_cpu_threshold_percent': 5, 'idle_duration_seconds': 60}
    cpu = dict(before, revision=13, efficiency_enabled=False)
    guard = dict(cpu, request_id=original_uuid + '-cpu-hold')
    tuning = {'_http_status': 200, 'revision': 6,
              'settings': {'writeback': {'enabled': False},
                           'vm_management': {'mode': 'all_running', 'vm_uuids': []}}}
    evidence = {'success': False, 'status': 'Unknown', 'state': {
        'phase': 'UNKNOWN', 'lastStep': 'tuning_target_readback',
        'sequence': ['cpu_guard_written', 'cpu_guard_verified_off', 'tuning_apply_returned'],
        'notAttempted': ['remainingPolicyWrites', 'finalCpuGate'],
        'sections': {'cpuBefore': before, 'cpuGuard': guard,
                     'cpuGuardReadback': dict(cpu),
                     'tuning': dict(tuning, agent_request_id=original_uuid + '-tuning'),
                     'tuningReadback': dict(tuning), 'cpuReadback': None}}}
    assert plugin._record_operation(original, 'UNKNOWN', evidence)

    recovery = {'hostUuid': host, 'resourceUuid': host, 'scope': 'Host',
                'action': 'recoverUncertain', 'operationUuid': recovery_uuid,
                'expectedControlOperationUuid': original_uuid, 'desiredRevision': 9,
                'policy': {}, 'recovery': {'expectedHostBootId': boot,
                    'expectedPoolGeneration': generation, 'confirmed': True}}
    cpu_current = dict(cpu)
    calls = []
    drain_launches = []

    def service(action, payload):
        calls.append((action, dict(payload)))
        if action == 'host-cpu-state':
            return dict(cpu_current)
        if action == 'tuning-state':
            return dict(tuning)
        if action == 'monitor-state':
            return {'_http_status': 200, 'pending_operations': [],
                    'lifecycle': {'paused': False, 'migrationHold': {}},
                    'host_zram': {'pool_generation': generation}}
        if action == 'operations':
            return {'_http_status': 200, 'cq': {'C': 0, 'Q': 0}, 'entries': []}
        if action == 'host-cpu':
            if payload.get('request_id') == original_uuid + '-cpu':
                cpu_current.update(revision=14, efficiency_enabled=True)
                return dict(cpu_current, request_id=original_uuid + '-cpu')
            if payload.get('request_id') == '5' * 32 + '-drain-disable':
                cpu_current.update(revision=15, efficiency_enabled=False)
                return dict(cpu_current, request_id=payload['request_id'])
            raise AssertionError('Unexpected host CPU request: %r' % payload)
        if action == 'lifecycle-pause':
            return {'_http_status': 200, 'success': True, 'status': 'Succeeded',
                    'paused': payload.get('action') != 'resume', 'migrationHold': {}}
        if action == 'state':
            return {'_http_status': 200, 'host_zram': {
                'pool_generation': generation, 'device': '/dev/zram1'}}
        raise AssertionError('Unexpected service action: %s' % action)

    plugin.service_call = service
    plugin._start_stock_drain = lambda command: drain_launches.append(dict(command)) or {
        'unit': 'zstack-memory-drain-' + command['operationUuid'],
        'receiptPath': '/tmp/receipt.json'}
    return {'plugin': plugin, 'host': host, 'boot': boot, 'generation': generation,
            'original': original, 'anchor': anchor, 'recovery': recovery,
            'cpu': cpu_current, 'calls': calls, 'drainLaunches': drain_launches}


def _finish_final_cpu_recovery(fixture):
    plugin = fixture['plugin']
    result = plugin.apply(fixture['recovery'])
    assert result['success'] is True, result
    assert result['state']['phase'] == 'POLICY_RECOVERED'
    assert plugin._get_active_control() == fixture['recovery']['operationUuid']
    return result


def _drain_from_final_cpu_recovery(fixture):
    recovery = fixture['recovery']
    return {'hostUuid': fixture['host'], 'resourceUuid': fixture['host'],
            'scope': 'Host', 'action': 'drain', 'operationUuid': '5' * 32,
            'expectedControlOperationUuid': recovery['operationUuid'],
            'desiredRevision': recovery['desiredRevision'], 'policy': {}}


def test_successful_final_cpu_gate_recovery_allows_normal_pause_and_drain(final_cpu_gate_recovery, monkeypatch):
    fixture = final_cpu_gate_recovery
    plugin = fixture['plugin']
    _finish_final_cpu_recovery(fixture)
    original_path = plugin._operation_path(fixture['original']['operationUuid'])
    anchor_path = plugin._operation_path(fixture['anchor']['operationUuid'])
    with open(original_path, 'rb') as stream:
        original_bytes = stream.read()
    with open(anchor_path, 'rb') as stream:
        anchor_bytes = stream.read()
    fixture['calls'][:] = []
    ksm_native_writes = []
    monkeypatch.setattr(plugin, '_write_ksm_sysfs', lambda key, value: ksm_native_writes.append((key, value)))
    monkeypatch.setattr('kvmagent.plugins.memory_optimization.subprocess.check_call',
                        lambda args: ksm_native_writes.append(tuple(args)))

    drain_command = _drain_from_final_cpu_recovery(fixture)
    drain_command['desiredRevision'] += 1  # Control tasks may carry a newer task revision; proof binds internally.
    result = plugin.apply(drain_command)

    assert result['status'] == 'Draining', result
    assert [action for action, _ in fixture['calls']][:2] == ['lifecycle-pause', 'state']
    assert any(action == 'host-cpu' for action, _ in fixture['calls'])
    assert fixture['drainLaunches'] and fixture['drainLaunches'][0]['device'] == '/dev/zram1'
    assert plugin._get_active_control() == '5' * 32
    assert plugin._load_operation(fixture['original'])['stage'] == 'UNKNOWN'
    assert ksm_native_writes == []
    with open(original_path, 'rb') as stream:
        assert stream.read() == original_bytes
    with open(anchor_path, 'rb') as stream:
        assert stream.read() == anchor_bytes


def test_successful_final_cpu_gate_recovery_allows_normal_pause_and_resume(final_cpu_gate_recovery, monkeypatch):
    fixture = final_cpu_gate_recovery
    plugin = fixture['plugin']
    _finish_final_cpu_recovery(fixture)
    original_path = plugin._operation_path(fixture['original']['operationUuid'])
    with open(original_path, 'rb') as stream:
        original_bytes = stream.read()
    fixture['calls'][:] = []
    ksm_writes = []
    monkeypatch.setattr(plugin, '_write_ksm_sysfs', lambda key, value: ksm_writes.append((key, value)))
    monkeypatch.setattr('kvmagent.plugins.memory_optimization.subprocess.check_call',
                        lambda args: ksm_writes.append(tuple(args)))
    command = _drain_from_final_cpu_recovery(fixture)
    command.update(action='pause', operationUuid='6' * 32)

    result = plugin.apply(command)

    assert result['status'] == 'Succeeded', result
    assert [action for action, _ in fixture['calls']] == ['lifecycle-pause']
    assert plugin._get_active_control() == command['operationUuid']
    resume = dict(command, action='resume', operationUuid='7' * 32,
                  expectedControlOperationUuid=command['operationUuid'])
    result = plugin.apply(resume)
    assert result['status'] == 'Succeeded', result
    assert result['state']['phase'] == 'RESUMED'
    assert [action for action, _ in fixture['calls']] == ['lifecycle-pause', 'lifecycle-pause']
    assert fixture['calls'][-1][1]['action'] == 'resume'
    assert plugin._get_active_control() == resume['operationUuid']
    assert ksm_writes == []
    with open(original_path, 'rb') as stream:
        assert stream.read() == original_bytes


def test_missing_active_final_cpu_recovery_journal_is_rejected_before_pause_or_cpu_write(
        final_cpu_gate_recovery):
    fixture = final_cpu_gate_recovery
    plugin = fixture['plugin']
    _finish_final_cpu_recovery(fixture)
    original_path = plugin._operation_path(fixture['original']['operationUuid'])
    anchor_path = plugin._operation_path(fixture['anchor']['operationUuid'])
    with open(original_path, 'rb') as stream:
        original_bytes = stream.read()
    with open(anchor_path, 'rb') as stream:
        anchor_bytes = stream.read()
    recovery_path = plugin._operation_path(fixture['recovery']['operationUuid'])
    os.unlink(recovery_path)
    cpu_before = dict(fixture['cpu'])
    fixture['calls'][:] = []

    result = plugin.apply(_drain_from_final_cpu_recovery(fixture))

    assert result['status'] == 'Failed', result
    assert fixture['calls'] == []
    assert fixture['drainLaunches'] == []
    assert fixture['cpu'] == cpu_before
    assert plugin._get_active_control() == fixture['recovery']['operationUuid']
    for path, expected in ((original_path, original_bytes), (anchor_path, anchor_bytes)):
        with open(path, 'rb') as stream:
            assert stream.read() == expected


def test_symlinked_final_cpu_anchor_is_rejected_before_pause_or_cpu_write(final_cpu_gate_recovery):
    fixture = final_cpu_gate_recovery
    plugin = fixture['plugin']
    _finish_final_cpu_recovery(fixture)
    anchor_path = plugin._operation_path(fixture['anchor']['operationUuid'])
    os.unlink(anchor_path)
    os.symlink(plugin._operation_path(fixture['original']['operationUuid']), anchor_path)
    cpu_before = dict(fixture['cpu'])
    fixture['calls'][:] = []

    result = plugin.apply(_drain_from_final_cpu_recovery(fixture))

    assert result['status'] == 'Failed', result
    assert fixture['calls'] == []
    assert fixture['drainLaunches'] == []
    assert fixture['cpu'] == cpu_before


def test_symlinked_active_control_is_rejected_before_maintenance(final_cpu_gate_recovery):
    fixture = final_cpu_gate_recovery
    plugin = fixture['plugin']
    _finish_final_cpu_recovery(fixture)
    target = plugin.active_control_path + '.saved'
    os.rename(plugin.active_control_path, target)
    os.symlink(target, plugin.active_control_path)
    with open(target, 'rb') as stream:
        active_bytes = stream.read()
    recovery_before = plugin._load_operation(fixture['recovery'])
    cpu_before = dict(fixture['cpu'])
    fixture['calls'][:] = []

    result = plugin.apply(_drain_from_final_cpu_recovery(fixture))

    assert result['status'] == 'Failed', result
    assert fixture['calls'] == []
    assert fixture['drainLaunches'] == []
    assert fixture['cpu'] == cpu_before
    assert os.path.islink(plugin.active_control_path)
    with open(target, 'rb') as stream:
        assert stream.read() == active_bytes
    assert plugin._load_operation(fixture['recovery']) == recovery_before


@pytest.mark.parametrize('defect', ['boot', 'control', 'journal-hash', 'cpu-receipt',
                                    'original-ksm', 'anchor-ksm', 'request-hash'])
def test_unqualified_final_cpu_recovery_is_rejected_before_pause_or_native_write(
        final_cpu_gate_recovery, defect):
    fixture = final_cpu_gate_recovery
    plugin = fixture['plugin']
    _finish_final_cpu_recovery(fixture)
    recovery_record = plugin._load_operation(fixture['recovery'])
    original_record = plugin._load_operation(fixture['original'])
    anchor_record = plugin._load_operation(fixture['anchor'])
    if defect == 'boot':
        recovery_record['bootId'] = 'previous-boot'
        assert plugin._write_operation_record(recovery_record)
    elif defect == 'control':
        plugin._set_active_control(fixture['anchor']['operationUuid'])
    elif defect == 'journal-hash':
        original_record['readback']['state']['lastStep'] = 'changed-after-recovery'
        assert plugin._write_operation_record(original_record)
    elif defect == 'cpu-receipt':
        del recovery_record['recoveryIntent']['cpuReceipt']
        assert plugin._write_operation_record(recovery_record)
    elif defect == 'original-ksm':
        original_record['readback']['ksmReadback'] = {'run': '0'}
        recovery_record['recoveryIntent']['originalJournalHash'] = plugin._operation_hash(original_record)
        assert plugin._write_operation_record(original_record)
        recovery_result = recovery_record['readback']
        recovery_result['state']['recoveryProof']['originalPolicyHash'] = original_record['policyHash']
        assert plugin._write_operation_record(recovery_record)
    elif defect == 'anchor-ksm':
        anchor_record['policy']['ksm'] = {'enabled': True, 'pagesToScan': 1000}
        anchor_record['readback']['ksmReadback'] = {'run': '1'}
        assert plugin._write_operation_record(anchor_record)
    elif defect == 'request-hash':
        recovery_record['requestHash'] = 1
        assert plugin._write_operation_record(recovery_record)

    original_path = plugin._operation_path(fixture['original']['operationUuid'])
    anchor_path = plugin._operation_path(fixture['anchor']['operationUuid'])
    recovery_path = plugin._operation_path(fixture['recovery']['operationUuid'])
    with open(original_path, 'rb') as stream:
        original_bytes = stream.read()
    with open(anchor_path, 'rb') as stream:
        anchor_bytes = stream.read()
    with open(recovery_path, 'rb') as stream:
        recovery_bytes = stream.read()
    active_before = plugin._get_active_control()
    cpu_before = dict(fixture['cpu'])
    fixture['calls'][:] = []

    result = plugin.apply(_drain_from_final_cpu_recovery(fixture))

    assert result['status'] in ('Failed', 'Unknown'), result
    assert fixture['calls'] == []
    assert fixture['drainLaunches'] == []
    assert fixture['cpu'] == cpu_before
    assert plugin._get_active_control() == active_before
    assert plugin._load_operation(fixture['original'])['stage'] == 'UNKNOWN'
    for path, expected in ((original_path, original_bytes), (anchor_path, anchor_bytes),
                           (recovery_path, recovery_bytes)):
        with open(path, 'rb') as stream:
            assert stream.read() == expected

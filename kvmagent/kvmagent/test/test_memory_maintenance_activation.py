"""Focused lifecycle handoff tests independent of the broad Agent suite."""
import os
import hashlib
import json
import shutil
import tempfile
import time
import unittest

from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin


class TestDrainedApplyActivation(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='memory-activation-')
        self.addCleanup(shutil.rmtree, self.directory)
        self.plugin = MemoryOptimizationPlugin(service_call=lambda *args: {})
        self.plugin.configure({'hostUuid': 'host-1', 'operationDir': self.directory,
                               'socketPath': os.path.join(self.directory, 'zram.sock')})
        # These lifecycle tests start from a previously authorized product
        # configuration.  The exact vendor observe template and first-use
        # transition are covered in test_memory_optimization's dedicated
        # first-use pipeline tests.
        config_directory = os.path.join(self.directory, 'zram-config')
        os.makedirs(config_directory)
        self.plugin.zram_config_path = os.path.join(config_directory, 'config.json')
        self.plugin.zram_config_template_path = os.path.join(config_directory, 'vendor-config.json')
        authorized_config = {'version': 2, 'mode': 'reclaim', 'managed': True,
                             'resource_authorized': True,
                             'initial_efficiency_enabled': False}
        config_bytes = json.dumps(authorized_config, sort_keys=True).encode('utf-8')
        vendor_template = dict(authorized_config, mode='observe', resource_authorized=False)
        template_bytes = json.dumps(vendor_template, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        with open(self.plugin.zram_config_path, 'wb') as stream:
            stream.write(config_bytes)
        with open(self.plugin.zram_config_template_path, 'wb') as stream:
            stream.write(template_bytes)
        self.drain = {'hostUuid': 'host-1', 'operationUuid': 'drain-1',
                      'scope': 'Host', 'action': 'drain', 'desiredRevision': 4}
        self.assertTrue(self.plugin._record_operation(
            self.drain, 'APPLIED', {'success': True, 'status': 'Succeeded'}))
        self.plugin._set_active_control('drain-1')

    def _apply_command(self, operation='apply-1'):
        return {'hostUuid': 'host-1', 'operationUuid': operation, 'scope': 'Host',
                'action': 'apply', 'expectedControlOperationUuid': 'drain-1',
                'maintenanceProof': {'schemaVersion': 1, 'drainOperationUuid': 'drain-1',
                                     'oldPoolGeneration': 'old-generation'},
                'expectedRevision': 4, 'desiredRevision': 5,
                'policy': {'zram': {'enabled': True, 'logicalCapacityBytes': 1 << 30},
                           'writeback': {'enabled': False}}}

    def _prepare_apply_mocks(self, pool_readback):
        plugin = self.plugin
        plugin._maintenance_recovery_proof = lambda *_a, **_k: True
        plugin.discover_capabilities = lambda: {'supported': True}
        plugin._requires_new_optimization = lambda _command: False
        plugin._validate_requested_capabilities = lambda *_args: None
        plugin._fill_resolved_capacity_defaults = lambda _command: None
        plugin._validate_policy = lambda _policy: None
        plugin._validate_backend_resource = lambda _command: None
        plugin._apply_ksm_policy = lambda _command: None
        plugin._apply_service_policy = lambda _command: {
            'success': True, 'status': 'Succeeded',
            'state': {'pool': pool_readback}}
        plugin._read_policy_state = lambda *_args: {'complete': True}

        def service_request(action, command):
            if action == 'lifecycle-activate-maintenance':
                return {'success': True, 'receipt': {'stage': 'UNPAUSED'}}
            if action == 'lifecycle-activation-state':
                request = plugin._load_operation({'operationUuid': 'apply-1'})['activationIntent']['request']
                wire_request = {
                    'request_id': request['request_id'],
                    'expected_control_operation_uuid': request['expected_control_operation_uuid'],
                    'expected_host_boot_id': request['expected_host_boot_id'],
                    'expected_pool_generation': request['expected_pool_generation']}
                request_json = json.dumps(wire_request, separators=(',', ':')).encode('utf-8')
                return {'receipt': {
                    'request_id': request['request_id'],
                    'request_fingerprint': hashlib.sha256(request_json).hexdigest(),
                    'expected_control_operation_uuid': 'drain-1',
                    'host_boot_id': plugin._current_boot_id(),
                    'pool_generation': 'old-generation', 'stage': 'INTENT_DURABLE'},
                    'lifecycle': {'paused': False, 'migrationHold': None},
                    'unpaused_observed': True}
            if action == 'state':
                return {'host_zram': ({'pool_generation': 'new-generation',
                                       'quality': 'native_host_device'}
                                      if pool_readback is not None else {}),
                        'observed_at': time.time(),
                        'host': {'qualified': True, 'safe': True,
                                 'observed_at': time.time()},
                        'pending_operations': [], 'maintenance_blocks_activation': False}
            raise AssertionError('unexpected service call: %s' % action)

        plugin._service_request = service_request
        plugin.maintenance_activation_timeout = 0.03
        plugin.maintenance_activation_poll_interval = 0.001

    def test_configured_but_missing_pool_is_not_success(self):
        # RED: current apply trusts policy write readback alone and marks this
        # operation Succeeded without opening lifecycle or proving a pool.
        self._prepare_apply_mocks(None)
        result = self.plugin.apply(self._apply_command())
        self.assertNotEqual('Succeeded', result.get('status'))
        self.assertEqual('drain-1', self.plugin._get_active_control())

    def test_ready_pool_is_required_before_drain_anchor_changes(self):
        self._prepare_apply_mocks({'generation': 'pool-1', 'state': 'READY'})
        result = self.plugin.apply(self._apply_command())
        self.assertEqual('Succeeded', result.get('status'), result)
        self.assertEqual('apply-1', self.plugin._get_active_control())

    def _prepare_rejected_activation(self, lost_response=False, mismatch=False):
        self._prepare_apply_mocks(None)
        original = self.plugin._service_request
        calls = []

        def rejected(action, command):
            calls.append(action)
            if action == 'lifecycle-activation-state':
                value = original(action, command)
                value['receipt'].update(schema=1, stage='REJECTED',
                                        reason_code='MAINTENANCE_ACTIVATION_NATIVE_NOT_READY')
                if mismatch:
                    value['receipt']['request_fingerprint'] = 'wrong'
                value['lifecycle']['paused'] = True
                value['unpaused_observed'] = False
                return value
            if action == 'lifecycle-activate-maintenance':
                if lost_response:
                    raise IOError('response lost after persisted rejection')
                value = rejected('lifecycle-activation-state', {})
                value.update(_http_status=409, error='MAINTENANCE_ACTIVATION_NATIVE_NOT_READY')
                return value
            return original(action, command)

        # Exercise the real HTTP status handling, not only a mocked wrapper.
        del self.plugin._service_request
        self.plugin.service_call = rejected
        return calls

    def test_explicit_activation_rejection_is_failed_not_permanent_unknown(self):
        calls = self._prepare_rejected_activation()
        result = self.plugin.apply(self._apply_command())
        self.assertEqual('Failed', result.get('status'), result)
        self.assertEqual('MAINTENANCE_ACTIVATION_NATIVE_NOT_READY', result.get('reasonCode'))
        self.assertEqual('REJECTED', self.plugin._load_operation({'operationUuid': 'apply-1'})['stage'])
        self.assertEqual('drain-1', self.plugin._get_active_control())
        self.assertEqual(1, calls.count('lifecycle-activate-maintenance'))
        again = self.plugin.apply(self._apply_command())
        self.assertEqual('Failed', again.get('status'), again)
        self.assertEqual(1, calls.count('lifecycle-activate-maintenance'))

    def test_lost_rejection_response_reconciles_terminal_without_reposting(self):
        calls = self._prepare_rejected_activation(lost_response=True)
        result = self.plugin.apply(self._apply_command())
        self.assertEqual('Unknown', result.get('status'))
        prior = self.plugin._load_operation({'operationUuid': 'apply-1'})
        result = self.plugin._reconcile_maintenance_activation({'operationUuid': 'apply-1'}, prior)
        self.assertEqual('Failed', result.get('status'), result)
        self.assertEqual('REJECTED', self.plugin._load_operation({'operationUuid': 'apply-1'})['stage'])
        self.assertEqual('drain-1', self.plugin._get_active_control())
        self.assertEqual(1, calls.count('lifecycle-activate-maintenance'))

    def test_mismatched_rejection_remains_unknown(self):
        calls = self._prepare_rejected_activation(mismatch=True)
        result = self.plugin.apply(self._apply_command())
        self.assertEqual('Unknown', result.get('status'), result)
        self.assertEqual('ACTIVATING', self.plugin._load_operation({'operationUuid': 'apply-1'})['stage'])
        self.assertEqual('drain-1', self.plugin._get_active_control())
        self.assertEqual(1, calls.count('lifecycle-activate-maintenance'))

    def test_rejection_journal_failure_does_not_report_terminal(self):
        self._prepare_rejected_activation()
        self.plugin._update_operation_record = lambda *_args: False
        result = self.plugin.apply(self._apply_command())
        self.assertEqual('Unknown', result.get('status'), result)
        self.assertEqual('OPERATION_JOURNAL_UNAVAILABLE', result.get('reasonCode'))
        self.assertEqual('drain-1', self.plugin._get_active_control())

    def test_http_conflict_without_rejection_receipt_is_still_unknown(self):
        calls = self._prepare_rejected_activation()
        previous = self.plugin.service_call

        def uncertain(action, command):
            if action == 'lifecycle-activate-maintenance':
                calls.append(action)
                return {'_http_status': 409, 'error': 'MAINTENANCE_ACTIVATION_INTENT_UNCERTAIN',
                        'receipt': {}}
            return previous(action, command)

        self.plugin.service_call = uncertain
        result = self.plugin.apply(self._apply_command())
        self.assertEqual('Unknown', result.get('status'), result)
        self.assertEqual('ACTIVATING', self.plugin._load_operation({'operationUuid': 'apply-1'})['stage'])
        self.assertEqual(1, calls.count('lifecycle-activate-maintenance'))

    def test_invalid_maintenance_proof_keeps_drain_fence(self):
        self._prepare_apply_mocks({'generation': 'pool-1', 'state': 'READY'})
        self.plugin._maintenance_recovery_proof = lambda *_a, **_k: False
        result = self.plugin.apply(self._apply_command())
        self.assertNotEqual('Succeeded', result.get('status'))
        self.assertEqual('drain-1', self.plugin._get_active_control())

    def test_changed_proof_after_policy_write_prevents_activation(self):
        self._prepare_apply_mocks({'generation': 'pool-1', 'state': 'READY'})
        checks = []

        def proof_check(*_args, **_kwargs):
            checks.append(True)
            return len(checks) < 3

        self.plugin._maintenance_recovery_proof = proof_check
        calls = []
        self.plugin._service_request = lambda action, _command: calls.append(action) or {}
        result = self.plugin.apply(self._apply_command())
        self.assertNotEqual('Succeeded', result.get('status'))
        self.assertEqual(3, len(checks))
        self.assertEqual(['state'], calls)
        self.assertEqual('drain-1', self.plugin._get_active_control())

    def test_successful_pause_is_not_maintenance_activation_authority(self):
        pause = {'hostUuid': 'host-1', 'operationUuid': 'pause-1',
                 'scope': 'Host', 'action': 'pause', 'desiredRevision': 4}
        self.assertTrue(self.plugin._record_operation(
            pause, 'APPLIED', {'success': True, 'status': 'Succeeded'}))
        self.plugin._set_active_control('pause-1')
        self._prepare_apply_mocks({'generation': 'pool-1', 'state': 'READY'})
        result = self.plugin.apply(self._apply_command())
        self.assertNotEqual('Succeeded', result.get('status'))
        self.assertEqual('pause-1', self.plugin._get_active_control())

    def test_fence_change_before_activation_does_not_post_or_advance(self):
        self._prepare_apply_mocks({'generation': 'pool-1', 'state': 'READY'})
        original = self.plugin._apply_service_policy

        def change_fence(command):
            result = original(command)
            self.plugin._set_active_control('newer-control')
            return result

        self.plugin._apply_service_policy = change_fence
        calls = []
        self.plugin._service_request = lambda action, _command: calls.append(action) or {}
        result = self.plugin.apply(self._apply_command())
        self.assertNotEqual('Succeeded', result.get('status'))
        self.assertNotIn('lifecycle-activate-maintenance', calls)
        self.assertEqual('newer-control', self.plugin._get_active_control())

    def test_timeout_is_reconciled_read_only_without_second_activation(self):
        self._prepare_apply_mocks({'generation': 'pool-1', 'state': 'READY'})
        self.plugin.maintenance_activation_timeout = 0
        calls = []

        def no_ready_state(action, _command):
            calls.append(action)
            if action == 'lifecycle-activate-maintenance':
                return {'success': True}
            if action == 'lifecycle-activation-state':
                return {'receipt': {'stage': 'INTENT_DURABLE'},
                        'lifecycle': {'paused': False}}
            if action == 'state':
                return {'host_zram': {}, 'host': {'qualified': True, 'safe': True},
                        'pending_operations': [],
                        'maintenance_blocks_activation': False}
            raise AssertionError(action)

        self.plugin._service_request = no_ready_state
        result = self.plugin.apply(self._apply_command())
        self.assertEqual('Unknown', result.get('status'))
        self.assertEqual(1, calls.count('lifecycle-activate-maintenance'))
        before = list(calls)
        reconciled = json.loads(self.plugin.reconcile({'body': json.dumps(
            {'operationUuid': 'apply-1'})}))
        self.assertEqual('Unknown', reconciled.get('status'))
        self.assertEqual(1, calls.count('lifecycle-activate-maintenance'))
        self.assertEqual('drain-1', self.plugin._get_active_control())
        self.assertGreater(len(calls), len(before))

    def test_drained_apply_without_durable_intent_cannot_reconcile_from_config(self):
        self._prepare_apply_mocks({'generation': 'pool-1', 'state': 'READY'})
        self.plugin._persist_maintenance_activation_intent = lambda *_args: None
        calls = []
        self.plugin._service_request = lambda action, _command: calls.append(action) or {}
        result = self.plugin.apply(self._apply_command())
        self.assertEqual('Unknown', result.get('status'))
        before = list(calls)
        reconciled = json.loads(self.plugin.reconcile({'body': json.dumps(
            {'operationUuid': 'apply-1'})}))
        self.assertEqual('Unknown', reconciled.get('status'))
        self.assertEqual('MAINTENANCE_ACTIVATION_INTENT_REQUIRED',
                         reconciled.get('reasonCode'))
        self.assertEqual(before, calls, 'reconcile must not infer readiness from config or reissue')
        self.assertEqual('drain-1', self.plugin._get_active_control())

    def test_native_qualification_requires_fresh_timestamps(self):
        now = time.time()
        for value in (None, now - 20, now + 0.01, 'not-a-time', float('nan'), float('inf')):
            self.assertFalse(self.plugin._native_observation_is_fresh(value, 3, now))
        self.assertTrue(self.plugin._native_observation_is_fresh(now - 1, 3, now))
        for ttl in (float('nan'), float('inf'), float('-inf'), -1, True):
            self.assertFalse(self.plugin._native_observation_is_fresh(now - 1, ttl, now))
        for value in ('nan', 'inf', '-inf'):
            self.assertFalse(self.plugin._native_observation_is_fresh(value, 3, now))
        timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.123456789+00:00',
                                  time.gmtime(now - 1))
        self.assertTrue(self.plugin._native_observation_is_fresh(timestamp, 3, now))
        z_timestamp = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(now - 1)) + '.123456789Z'
        self.assertTrue(self.plugin._native_observation_is_fresh(z_timestamp, 3, now))
        for value in (z_timestamp.replace('Z', '+99:99'),
                      z_timestamp.replace('Z', '+12:60'),
                      z_timestamp.replace('Z', '+1:00'),
                      z_timestamp.replace('Z', 'Zx')):
            self.assertFalse(self.plugin._native_observation_is_fresh(value, 3, now))

    def test_capacity_only_pending_requires_exact_desired_and_other_sections(self):
        command = self._apply_command()
        command['policy']['zram']['ramLimitBytes'] = 1 << 29
        service_states = {
            # Mirror CapacityStatus's real Go JSON: desired contains both the
            # configured native shape and the resolved-byte projections.
            'capacity-state': {'_http_status': 200, 'revision': 2,
                               'apply_state': 'PENDING_MAINTENANCE',
                               'desired': {
                                   'configured': {
                                       'logical_capacity': {'bytes': 1 << 30},
                                       'physical_memory_limit': {'bytes': 1 << 29}},
                                   'logical_resolved_bytes': 1 << 30,
                                   'physical_resolved_bytes': 1 << 29}},
            # Host CPU state is a strict success envelope and reports all
            # three values consumed by _read_policy_state.
            'host-cpu-state': {'_http_status': 200, 'revision': 2,
                               'efficiency_enabled': True,
                               'idle_cpu_threshold_percent': 80,
                               'idle_duration_seconds': 60},
            'tuning-state': {'_http_status': 200, 'revision': 1,
                             'settings': {'writeback': {'enabled': False}}},
        }
        self.plugin.service_call = lambda action, _payload: service_states[action]
        self.assertEqual({'configured': {
            'logical_capacity': {'bytes': 1 << 30},
            'physical_memory_limit': {'bytes': 1 << 29}},
            'logical_resolved_bytes': 1 << 30,
            'physical_resolved_bytes': 1 << 29},
            service_states['capacity-state']['desired'])
        self.assertEqual(200, service_states['host-cpu-state']['_http_status'])
        self.assertIn('idle_cpu_threshold_percent', service_states['host-cpu-state'])
        self.assertIn('idle_duration_seconds', service_states['host-cpu-state'])
        result = {'status': 'Draining', 'asyncSections': ['capacity']}
        readback = self.plugin._maintenance_policy_intent_readback(command, result)
        self.assertTrue(readback['complete'], readback)
        self.assertTrue(readback['capacityDesiredNotEffective'])

        service_states['capacity-state'].update(
            {'apply_state': 'BLOCKED', 'reason': 'NATIVE_POOL_UNQUALIFIED'})
        readback = self.plugin._maintenance_policy_intent_readback(command, result)
        self.assertTrue(readback['complete'], readback)
        service_states['capacity-state']['reason'] = 'OTHER_BLOCK'
        readback = self.plugin._maintenance_policy_intent_readback(command, result)
        self.assertFalse(readback['complete'], readback)
        service_states['capacity-state'].update(
            {'apply_state': 'PENDING_MAINTENANCE', 'reason': ''})

        service_states['capacity-state']['desired']['logical_resolved_bytes'] = 7
        readback = self.plugin._maintenance_policy_intent_readback(command, result)
        self.assertFalse(readback['complete'], readback)
        service_states['capacity-state']['desired']['logical_resolved_bytes'] = 1 << 30
        service_states['host-cpu-state']['efficiency_enabled'] = False
        readback = self.plugin._maintenance_policy_intent_readback(command, result)
        self.assertFalse(readback['complete'], readback)
        service_states['capacity-state']['desired']['logical_resolved_bytes'] = 1 << 30
        service_states['host-cpu-state']['efficiency_enabled'] = True
        readback = self.plugin._maintenance_policy_intent_readback(
            command, {'status': 'Draining', 'asyncSections': ['tuning']})
        self.assertFalse(readback['complete'], readback)

    def test_service_apply_identifies_capacity_only_202(self):
        command = self._apply_command()
        command['policy']['zram']['ramLimitBytes'] = 1 << 29
        from kvmagent.test.test_memory_optimization import TestMemoryOptimizationPlugin
        service, calls = TestMemoryOptimizationPlugin()._strict_policy_service(
            capacity_status=202, initial_cpu_enabled=True)
        self.plugin.service_call = service
        applied = self.plugin._apply_service_policy(command)
        self.assertEqual('Draining', applied['status'], applied)
        self.assertEqual(['capacity'], applied['asyncSections'])
        sections = applied['state']['sections']
        # The 202 CapacityStatus has no native request_id; the Agent's
        # durable local receipt binds it. Both writes use the service's
        # shared expected_revision CAS field.
        self.assertEqual(202, sections['capacity']['_http_status'])
        self.assertNotIn('request_id', sections['capacity'])
        self.assertEqual('apply-1-capacity', sections['capacity']['agent_request_id'])
        self.assertEqual(sections['capacity']['revision'],
                         sections['capacityReadback']['revision'])
        cpu_receipt = sections['cpu']
        self.assertEqual('apply-1-cpu', cpu_receipt['request_id'])
        self.assertEqual(sections['capacity']['revision'],
                         cpu_receipt['agent_expected_revision'])
        self.assertEqual(cpu_receipt['revision'], sections['cpuReadback']['revision'])
        tuning_receipt = sections['tuning']
        self.assertNotIn('request_id', tuning_receipt)
        self.assertEqual('apply-1-tuning', tuning_receipt['agent_request_id'])
        actions = [action for action, _payload in calls]
        self.assertLess(actions.index('host-cpu'), actions.index('capacity'))
        self.assertLess(actions.index('capacity'), actions.index('apply'))
        self.assertLess(actions.index('apply'), len(actions) - 1 - actions[::-1].index('host-cpu'))
        cpu_writes = [payload for action, payload in calls if action == 'host-cpu']
        capacity_write = next(payload for action, payload in calls if action == 'capacity')
        self.assertEqual([1, 3], [payload['expected_revision'] for payload in cpu_writes])
        self.assertEqual(2, capacity_write['expected_revision'])

if __name__ == '__main__':
    unittest.main()

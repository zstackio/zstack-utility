"""Memory optimization policy_apply behavior tests.

Migrated from the legacy Agent test module; all methods remain discovered by pytest.
"""

from tests.unit.kvmagent.memory_optimization_test_support import *
from tests.unit.kvmagent.memory_optimization_test_support import _OMIT_POLICY_MODE
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.kvmagent]

class TestMemoryOptimizationPolicyApply(MemoryOptimizationTestBase):
    def test_apply_user_config_rejection_is_durable_failed_and_idempotent(self):
        from unittest.mock import patch
        plugin, command = self._prepare_first_use_apply_test()
        with patch.object(plugin, '_first_use_runtime_identity',
                          side_effect=AssertionError('edited config has no runtime authorization')), \
             patch.object(plugin, '_bounded_controller_restart',
                          side_effect=AssertionError('edited config must not restart')), \
             patch.object(plugin, '_apply_ksm_policy',
                          side_effect=AssertionError('rejected request must not write KSM')), \
             patch.object(plugin, '_apply_service_policy',
                          side_effect=AssertionError('rejected request must not write ZRAM')):
            result = plugin.apply(command)
            self.assertFalse(result['success'])
            self.assertEqual('Failed', result['status'])
            self.assertEqual('FIRST_ZRAM_CONFIG_NOT_FACTORY', result['reasonCode'])
            persisted = plugin._load_operation(command)
            self.assertEqual('REJECTED', persisted['stage'])
            self.assertEqual(result, persisted['readback'])
            self.assertEqual(result, plugin.apply(command))
    def test_apply_prewrite_rejection_journal_failure_falls_back_to_unknown(self):
        from unittest.mock import patch
        plugin, command = self._prepare_first_use_apply_test()
        record_operation = plugin._record_operation

        def fail_terminal_rejection(target, stage, result=None):
            if stage == 'REJECTED':
                return False
            return record_operation(target, stage, result)

        with patch.object(plugin, '_record_operation', side_effect=fail_terminal_rejection), \
             patch.object(plugin, '_bounded_controller_restart',
                          side_effect=AssertionError('edited config must not restart')):
            result = plugin.apply(command)
        self.assertFalse(result['success'])
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('OPERATION_JOURNAL_UNAVAILABLE', result['reasonCode'])
        self.assertEqual('PREPARING', plugin._load_operation(command)['stage'])
    def test_apply_restart_unknown_reconciles_after_agent_reconstruction_without_replay(self):
        from unittest.mock import patch
        plugin, command, state, _template = self._first_use_fixture()
        # apply owns PREPARING creation; remove the direct-helper fixture record.
        os.unlink(plugin._operation_path(command['operationUuid']))
        identity = {'package': 'zstack-zram-1-1',
                    'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                    'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                    'templateSha256': hashlib.sha256(
                        open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
                    'pid': 111, 'processStartTime': '4', 'bootId': plugin._current_boot_id()}
        plugin.discover_capabilities = lambda: {'supported': True, 'reasonCode': 'SUPPORTED',
                                                 'ksm': True, 'ksmZeroPages': True,
                                                 'zram': True, 'writeback': True}
        for name in ('_validate_requested_capabilities', '_validate_policy',
                     '_validate_backend_resource'):
            setattr(plugin, name, lambda *args, **kwargs: None)
        plugin._fill_resolved_capacity_defaults = lambda command: command
        plugin._validate_cold_ksm_partial_fence = lambda command: None
        plugin._host_control_blocks_policy = lambda command: False
        plugin._first_use_prior_fence_clear = lambda operation_uuid: True
        observe = dict(state)
        plugin.service_call = lambda action, payload: (
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else
            observe if action == 'state' else
            {'revision': 1} if action == 'capacity-state' else
            {'revision': 2} if action == 'tuning-state' else {})
        with patch.object(plugin, '_first_use_runtime_identity', return_value=identity), \
             patch.object(plugin, '_bounded_controller_restart',
                          side_effect=RuntimeError('FIRST_ZRAM_RESTART_RESULT_UNKNOWN')):
            response = plugin.apply(command)
        self.assertEqual('Unknown', response['status'])
        self.assertEqual('UNKNOWN', plugin._load_operation(command)['stage'])
        self.assertNotIn('policySubmissionStarted',
                         plugin._load_operation(command)['firstZramUse'])

        # A new Agent object performs only readback reconciliation. The
        # restart already authorized the safe local config, but no product
        # policy operation was issued and the old request is terminally Failed.
        restarted = MemoryOptimizationPlugin()
        restarted.configure({'hostUuid': 'host-1', 'operationDir': plugin.operation_dir})
        restarted.zram_config_path = plugin.zram_config_path
        restarted.zram_config_template_path = plugin.zram_config_template_path
        post = dict(state, mode='reclaim', resource_authorized=True)
        restarted.service_call = lambda action, payload: (
            post if action == 'state' else
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else
            {'revision': 1} if action == 'capacity-state' else
            {'revision': 2} if action == 'tuning-state' else {})
        request = {memory_optimization.http.REQUEST_BODY: json.dumps(command)}
        with patch.object(restarted, '_first_use_runtime_identity', return_value=identity):
            reconciled = json.loads(restarted.reconcile(request))
        self.assertEqual('Failed', reconciled['status'])
        self.assertEqual('FIRST_ZRAM_POLICY_NOT_ISSUED', reconciled['reasonCode'])
        self.assertEqual('REJECTED', restarted._load_operation(command)['stage'])
        with patch.object(restarted, '_prepare_first_zram_use',
                          side_effect=AssertionError('must not replay the old operation')):
            replay = restarted.apply(command)
        self.assertEqual('Failed', replay['status'])
        self.assertEqual('REJECTED', restarted._load_operation(command)['stage'])
    def test_host_lifecycle_rejects_vm_and_unknown_scope_without_native_calls(self):
        for scope in ('VM', 'vm', 'unknown', None):
            for action in ('pause', 'drain', 'resume', 'release'):
                with self.subTest(scope=scope, action=action):
                    plugin, unused, command = self._rejected_resume_fixture()
                    with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                            patch.object(plugin, '_service_request') as native, \
                            patch.object(plugin, '_control_managed_ksm') as ksm:
                        result = plugin.apply({'hostUuid': 'host-1', 'scope': scope,
                            'action': action, 'operationUuid': 'invalid-scope-' + action,
                            'desiredRevision': 7, 'resourceUuid': 'vm-1',
                            'expectedInstanceGeneration': 'generation-1',
                            'expectedControlOperationUuid': 'drain-before-resume'})
                    self.assertEqual('Failed', result['status'], result)
                    self.assertEqual('HOST_CONTROL_SCOPE_REQUIRED', result['reason'])
                    native.assert_not_called()
                    ksm.assert_not_called()
                    self.assertEqual('drain-before-resume', plugin._get_active_control())
    def test_systemd_worker_exit_requires_trusted_pid_and_exit_evidence(self):
        plugin = MemoryOptimizationPlugin()
        def show(values):
            output = '\n'.join('%s=%s' % item for item in values.items())
            with patch.object(subprocess, 'check_output', return_value=output):
                return plugin._systemd_worker_exit('memory-test.service')

        exited = {'ActiveState': 'failed', 'SubState': 'failed', 'ExecMainCode': '1',
                  'ExecMainStatus': '1', 'MainPID': '0', 'ControlPID': '0'}
        # systemd reports failed units with inactive/dead on some releases.
        exited['ActiveState'], exited['SubState'] = 'inactive', 'dead'
        self.assertEqual(('exited', 1), show(exited))
        self.assertEqual(('unknown', None), show(dict(exited, MainPID='42')))
        self.assertEqual(('unknown', None), show(dict(exited, ControlPID='7')))
        self.assertEqual(('unknown', None), show(dict(exited, MainPID='')))
        self.assertEqual(('running', None), show(dict(exited, ActiveState='active',
                                                       SubState='running', MainPID='42')))
    def test_offline_service_does_not_make_writeback_device_prepared(self):
        def offline(*args):
            raise RuntimeError('offline')
        plugin = MemoryOptimizationPlugin(service_call=offline)
        plugin.host_uuid = 'host-1'
        with patch.object(plugin, '_request_body', return_value={'hostUuid': 'host-1'}), \
             patch.object(plugin, '_reply', side_effect=lambda result: result), \
             patch.object(memory_optimization, 'probe_writeback_backends', return_value={
                 'hostUuid': 'host-1', 'status': 'AVAILABLE', 'candidates': []}) as probe:
            result = plugin.writeback_backends({})
        self.assertEqual('PARTIAL', result['state']['status'])
        self.assertEqual({}, probe.call_args[0][1])
        self.assertIn('BACKEND_SERVICE_OBSERVATION_UNAVAILABLE', result['state']['reasons'])
    def test_installed_candidate_is_only_a_restart_hint_with_both_artifacts(self):
        candidate = '4.18.0-553.162.1.memopt1.el8.x86_64'
        with patch.object(os.path, 'isfile', return_value=True), patch.object(os.path, 'isdir', return_value=True):
            self.assertEqual(candidate, MemoryOptimizationPlugin.installed_reclaim_candidate('h84r', '3.10.0-old'))
            self.assertIsNone(MemoryOptimizationPlugin.installed_reclaim_candidate('h84r', candidate))
            self.assertIsNone(MemoryOptimizationPlugin.installed_reclaim_candidate('kylinV10', '4.19.0'))
        with patch.object(os.path, 'isfile', return_value=True), patch.object(os.path, 'isdir', return_value=False):
            self.assertIsNone(MemoryOptimizationPlugin.installed_reclaim_candidate('h84r', '3.10.0-old'))
    def test_readback_efficiency_switch_is_not_inferred_from_pool_or_desired_policy(self):
        for value, expected in (({'efficiency_enabled': True}, True),
                                ({'efficiency_enabled': False}, False), ({}, None)):
            plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: value if action == 'host-cpu-state' else {})
            with patch.object(plugin, '_libvirt_vm_generations', return_value=({}, True)), \
                 patch.object(memory_optimization.kvmagent, 'metric_collectors', []), \
                 patch.object(plugin, 'discover_capabilities', return_value={'ksm': True}), \
                 patch.object(subprocess, 'check_output', return_value=b'run=1\npages_to_scan=1250\nsleep_millisecs=10\n'):
                observed = plugin._enrich_state({'state': {}})['state']['actual']['zram']
            self.assertIs(expected, observed.get('efficiencyEnabled'))
            if expected is None:
                self.assertTrue(any(item['operation'] == 'host-cpu-state' for item in observed['errors']))
    def test_complete_inventory_is_independent_of_reclaim_selection(self):
        calls = []
        def service(action, payload):
            calls.append((action, payload))
            return {'identities': {'vm-1': {'uuid': 'vm-1',
                                            'instance_generation': 'native-1'}},
                    'unavailable': {'vm-2': 'VM_IDENTITY_UNAVAILABLE'}}
        plugin = MemoryOptimizationPlugin(service_call=service)
        with patch.object(plugin, '_libvirt_vm_generations', return_value=(
                {'vm-1': {'instanceGeneration': 'vm-1:42'}, 'vm-2': {}}, True)):
            inventory, complete = plugin._complete_vm_inventory({
                'stale-vm': {'instanceGeneration': 'old'},
                'vm-2': {'instanceGeneration': 'stale-2'}})
        self.assertTrue(complete)
        self.assertEqual({'vm-1', 'vm-2'}, set(inventory))
        self.assertEqual('native-1', inventory['vm-1']['instanceGeneration'])
        self.assertNotIn('instanceGeneration', inventory['vm-2'])
        self.assertEqual('VM_IDENTITY_UNAVAILABLE', inventory['vm-2']['identityReason'])
        self.assertEqual('vm-identities', calls[0][0])
    def test_identifiers_cannot_escape_journal_or_binding_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = MemoryOptimizationPlugin()
            plugin.configure({'operationDir': directory, 'vmBindingDir': directory})
            for identifier in ('../escape', '/tmp/escape', 'a/b', 'a.b', 'a b', '', None, 1):
                command = {'hostUuid': 'host-1', 'operationUuid': identifier}
                with self.assertRaises(ValueError):
                    plugin._operation_request(command)
                self.assertFalse(plugin._record_operation(command, 'REJECTED'))
                with self.assertRaises(ValueError):
                    plugin._vm_binding_path(identifier)
            self.assertEqual([], os.listdir(directory))
    def test_zero_merge_is_independent_of_zero_counter_on_kylin(self):
        import io
        self.capability_patch.stop()
        plugin = MemoryOptimizationPlugin()
        present = {'run', 'pages_to_scan', 'sleep_millisecs', 'use_zero_pages'}
        with patch('builtins.open', return_value=io.StringIO('ID=kylin\nVERSION_ID=V10\n')), \
                patch.object(memory_optimization.platform, 'machine', return_value='x86_64'), \
                patch.object(memory_optimization.platform, 'release', return_value='4.19.90-89.46.v2401.ky10.x86_64'), \
                patch.object(memory_optimization.os, 'sysconf', return_value=4096), \
                patch.object(memory_optimization.os.path, 'exists', side_effect=lambda p: p.startswith('/sys/kernel/mm/ksm/') and p.rsplit('/', 1)[1] in present):
            capabilities = plugin.discover_capabilities()
        self.assertTrue(capabilities['ksm'])
        self.assertTrue(capabilities['ksmZeroPages'])
        self.assertFalse(capabilities['ksmZeroPagesCounter'])
        self.assertFalse(capabilities['zram'])
    def test_preview_reads_resolved_capacity_defaults_without_side_effect(self):
        calls = []
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: calls.append(action) or (
            {'settings': {}} if action == 'tuning-state' else {
                'desired': {'logical_resolved_bytes': 8192,
                            'physical_resolved_bytes': 4096}}))
        plugin.configure({'hostUuid': 'host-1'})
        result = json.loads(plugin.preview({'body': json.dumps({
            'hostUuid': 'host-1', 'operationUuid': 'preview-1'})}))
        self.assertTrue(result['success'])
        self.assertEqual(8192, result['state']['policyDefaults']['zram']['logicalCapacityBytes'])
        self.assertEqual(4096, result['state']['policyDefaults']['zram']['ramLimitBytes'])
        self.assertEqual(['tuning-state', 'capacity-state'], calls)
    def test_vm_policy_maps_to_real_efficiency_endpoint_contract(self):
        payload = MemoryOptimizationPlugin._service_payload(
            'apply', {'operationUuid': 'op-vm', 'expectedRevision': 2,
                      'scope': 'vm', 'resourceUuid': 'vm-1',
                      'expectedInstanceGeneration': 'gen-7',
                      'participation': 'inherit'})
        self.assertEqual('gen-7', payload['expected_instance_generation'])
        self.assertEqual('auto', payload['mode'])
        self.assertIsNone(payload['cpu_rule'])
        self.assertNotIn('ttl_seconds', payload)
    def test_vm_allow_uses_durable_auto_without_short_ttl(self):
        payload = MemoryOptimizationPlugin._service_payload(
            'apply', {'operationUuid': 'op-vm-allow', 'expectedRevision': 2,
                      'scope': 'vm', 'resourceUuid': 'vm-1',
                      'expectedInstanceGeneration': 'gen-7',
                      'participation': 'allow'})
        self.assertEqual('auto', payload['mode'])
        self.assertNotIn('ttl_seconds', payload)
    def test_vm_deny_is_license_free_but_mixed_host_policy_is_rejected(self):
        operation_dir = tempfile.mkdtemp(prefix='vm-deny-license-')
        calls = []
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload:
                calls.append((action, payload)) or
                ({'revision': 0} if action == 'vm-policy-state' else
                 {'status': 'Succeeded'}))
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'):
            result = plugin.apply({'action': 'apply', 'scope': 'vm',
                                   'hostUuid': 'host-1', 'operationUuid': 'vm-deny-no-license',
                                   'resourceUuid': 'vm-1',
                                   'expectedInstanceGeneration': 'gen-1',
                                   'participation': 'deny', 'policy': {}})
        self.assertTrue(result['success'], result)
        self.assertEqual(['vm-policy-state', 'vm-policy'], [x[0] for x in calls])
        mixed = plugin.apply({'action': 'apply', 'scope': 'vm',
                              'hostUuid': 'host-1', 'operationUuid': 'vm-deny-mixed',
                              'resourceUuid': 'vm-1',
                              'expectedInstanceGeneration': 'gen-1',
                              'participation': 'deny',
                              'policy': {'participation': 'deny',
                                         'zram': {'enabled': True}}})
        self.assertFalse(mixed['success'])
        self.assertEqual('Failed', mixed['status'])
    def test_zram_capacity_and_cpu_fields_map_to_real_service_abis(self):
        command = {'operationUuid': 'op-zram', 'expectedRevision': 3,
                   'policy': {'zram': {'enabled': True,
                                       'logicalCapacityBytes': 8 * 1024 * 1024,
                                       'ramLimitBytes': 4 * 1024 * 1024,
                                       'cpuThresholdPercent': 70,
                                       'cpuHoldSeconds': 45}}}
        capacity = MemoryOptimizationPlugin._service_payload('capacity', command)
        cpu = MemoryOptimizationPlugin._service_payload('host-cpu', command)
        self.assertEqual(8 * 1024 * 1024, capacity['logical_capacity']['bytes'])
        self.assertEqual(4 * 1024 * 1024, capacity['physical_memory_limit']['bytes'])
        self.assertEqual(70, cpu['idle_cpu_threshold_percent'])
        self.assertEqual(45, cpu['idle_duration_seconds'])
    def test_cpu_update_preserves_native_rule_when_only_switch_changes(self):
        for percent in (5, 80):
            command = {'operationUuid': 'enable-existing',
                       'nativeCpuState': {'revision': 7, 'efficiency_enabled': False,
                                          'idle_cpu_threshold_percent': percent,
                                          'idle_duration_seconds': 120},
                       'policy': {'zram': {'enabled': True}}}
            payload = MemoryOptimizationPlugin._service_payload('host-cpu', command)
            self.assertTrue(payload['efficiency_enabled'])
            self.assertEqual(percent, payload['idle_cpu_threshold_percent'])
            self.assertEqual(120, payload['idle_duration_seconds'])
    def test_cpu_rule_only_update_does_not_disable_existing_reclaim(self):
        command = {'operationUuid': 'cpu-rule-only',
                   'nativeCpuState': {'revision': 7, 'efficiency_enabled': True,
                                      'idle_cpu_threshold_percent': 5,
                                      'idle_duration_seconds': 60},
                   'policy': {'zram': {'cpuThresholdPercent': 8}}}
        payload = MemoryOptimizationPlugin._service_payload('host-cpu', command)
        self.assertTrue(payload['efficiency_enabled'])
        self.assertEqual(8, payload['idle_cpu_threshold_percent'])
    def test_zero_startup_isolation_and_filesystem_reserve_are_valid(self):
        policy = {'zram': {'startupObservationSeconds': 0, 'timeoutIsolationSlots': 0},
                  'writeback': {'filesystemReserveBytes': 0}}
        MemoryOptimizationPlugin._validate_policy(policy)
        payload = MemoryOptimizationPlugin._service_payload('apply', {
            'operationUuid': 'explicit-zero-controls', 'policy': policy})
        self.assertEqual(0, payload['settings']['startup_observation_seconds'])
        self.assertEqual(0, payload['settings']['timeout_isolation_slots'])
        self.assertEqual(0, payload['settings']['writeback']['filesystem_reserve_bytes'])
    def test_zram_advanced_policy_maps_selection_guards_sampling_and_reclaim_defaults(self):
        payload = MemoryOptimizationPlugin._service_payload('apply', {
            'operationUuid': 'op-advanced-zram', 'expectedRevision': 4,
            'policy': {'zram': {
                'selectionMode': 'list', 'selectedVmUuids': ['vm-1'],
                'discoveryIntervalSeconds': 61, 'hostCpuGuardEnabled': False,
                'hostMemoryPsiThresholdPercent': 0.2,
                'reclaimBatchBytes': 128 * 1024 * 1024,
                'concurrency': 3, 'timeoutIsolationSlots': 11,
                'algorithm': 'lzo'}}})
        settings = payload['settings']
        self.assertEqual('list', settings['vm_management']['mode'])
        self.assertEqual(['vm-1'], settings['vm_management']['vm_uuids'])
        self.assertEqual(61, settings['discovery_interval_seconds'])
        self.assertFalse(settings['host_cpu_guard_enabled'])
        self.assertEqual(0.2, settings['host_memory_psi_threshold_percent'])
        self.assertEqual(128 * 1024 * 1024, settings['reclaim_batch_bytes'])
        self.assertEqual(3, settings['reclaim_concurrency'])
        self.assertEqual(11, settings['timeout_isolation_slots'])
        self.assertEqual('lzo', settings['algorithm'])
        self.assertEqual(50, settings['host_cpu_threshold_percent'])
    def test_tuning_concurrency_updates_legacy_alias_together(self):
        command = {'policy': {'zram': {'concurrency': 2}}}
        state = {'settings': {'concurrency': 1, 'reclaim_concurrency': 1,
                              'writeback': {}}}
        MemoryOptimizationPlugin._merge_tuning_settings(command, state)
        settings = command['nativeSettings']
        self.assertEqual(2, settings['concurrency'])
        self.assertEqual(2, settings['reclaim_concurrency'])
    def test_writeback_advanced_policy_maps_slow_progress_and_budget_fields(self):
        payload = MemoryOptimizationPlugin._service_payload('apply', {
            'operationUuid': 'op-advanced-wb', 'expectedRevision': 5,
            'policy': {'writeback': {
                'slowOperationSeconds': 61, 'noProgressLimit': 4,
                'backoffSeconds': 62, 'ioErrorBackoffSeconds': 63,
                'metadataBudgetBytes': 1024, 'filesystemReserveBytes': 2048}}})
        wb = payload['settings']['writeback']
        self.assertEqual(61, wb['slow_operation_seconds'])
        self.assertEqual(4, wb['no_progress_limit'])
        self.assertEqual(62, wb['backoff_seconds'])
        self.assertEqual(63, wb['io_error_backoff_seconds'])
        self.assertEqual(1024, wb['metadata_budget_bytes'])
        self.assertEqual(2048, wb['filesystem_reserve_bytes'])
    def test_advanced_policy_validation_rejects_untyped_or_out_of_range_fields(self):
        invalid = [
            {'zram': {'selectionMode': 'everything'}},
            {'zram': {'selectedVmUuids': ['vm-1', 7]}},
            {'zram': {'hostMemoryPsiThresholdPercent': float('nan')}},
            {'zram': {'hostIoPsiThresholdPercent': True}},
            {'zram': {'reclaimBatchBytes': 0}},
            {'zram': {'algorithm': 7}},
            {'writeback': {'noProgressLimit': 0}},
            {'writeback': {'metadataBudgetBytes': 1.5}},
        ]
        for policy in invalid:
            with self.assertRaises(ValueError, msg=repr(policy)):
                MemoryOptimizationPlugin._validate_policy(policy)
    def test_advanced_policy_preserves_fractional_psi_and_explicit_false_zero(self):
        policy = {'zram': {
            'hostCpuGuardEnabled': False,
            'hostMemoryPsiGuardEnabled': False,
            'hostMemoryPsiThresholdPercent': 0.1,
            'hostFloorBytes': 0,
        }}
        MemoryOptimizationPlugin._validate_policy(policy)
        payload = MemoryOptimizationPlugin._service_payload(
            'apply', {'operationUuid': 'op-explicit-values', 'policy': policy})
        settings = payload['settings']
        self.assertFalse(settings['host_cpu_guard_enabled'])
        self.assertFalse(settings['host_memory_psi_guard_enabled'])
        self.assertEqual(0.1, settings['host_memory_psi_threshold_percent'])
        self.assertEqual(0, settings['host_floor_bytes'])
    def test_writeback_disable_does_not_require_backend_service_or_device(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: self.fail('unexpected service query'))
        plugin._validate_backend_resource({'policy': {'writeback': {'enabled': False}}})
    def test_preview_uses_same_backend_validation_path_as_apply(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {
            'desired': {'logical_resolved_bytes': WRITEBACK_CAPACITY,
                        'physical_resolved_bytes': WRITEBACK_CAPACITY // 2}}
            if action == 'capacity-state' else {})
        plugin.host_uuid = 'host-1'
        command = {'hostUuid': 'host-1', 'operationUuid': 'preview-wb',
                   'policy': {'writeback': {'enabled': True,
                                             'backendResourceUuid': WRITEBACK_RESOURCE_UUID}}}
        with patch.object(plugin, '_validate_backend_resource') as validate, \
             patch.object(plugin, 'discover_capabilities', return_value={'zram': True}), \
             patch.object(plugin, '_reply', side_effect=lambda result: result):
            result = plugin.preview({'body': json.dumps(command)})
        self.assertTrue(result['success'])
        validate.assert_called_once_with(command)
    def test_prepared_backend_observation_must_be_present_fresh_and_not_future(self):
        cases = (
            (None, 'BACKEND_RESOURCE_TIMESTAMP_UNKNOWN'),
            ('not-a-timestamp', 'BACKEND_RESOURCE_TIMESTAMP_UNKNOWN'),
            ('2099-01-01T00:00:00Z', 'BACKEND_RESOURCE_TIMESTAMP_FUTURE'),
            (time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 120)),
             'BACKEND_RESOURCE_STALE'),
        )
        for observed_at, expected in cases:
            with self.subTest(observed_at=observed_at):
                status, detail = writeback_service_views(observed_at)
                if observed_at is None:
                    status['backend_resource']['observed_at'] = None
                plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
                                                  status if action == 'backend-state' else detail)
                plugin.host_uuid = 'host-1'
                command = {'hostUuid': 'host-1', 'policy': {'writeback': {
                    'enabled': True, 'backendResourceUuid': WRITEBACK_RESOURCE_UUID}}}
                with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                     patch.object(memory_optimization, 'probe_writeback_backends') as probe:
                    with self.assertRaisesRegex(ValueError, expected):
                        plugin._validate_backend_resource(command)
                probe.assert_not_called()
    def test_backend_status_host_and_ownership_fields_must_match(self):
        cases = (
            ('resource_uuid', 'c' * 32, 'BACKEND_RESOURCE_NOT_ACTIVE'),
            ('state', 'UNKNOWN', 'BACKEND_RESOURCE_NOT_ACTIVE'),
        )
        for field, value, expected in cases:
            with self.subTest(field=field):
                status, detail = writeback_service_views()
                status['backend_resource'][field] = value
                plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
                                                  status if action == 'backend-state' else detail)
                plugin.host_uuid = 'host-1'
                command = {'hostUuid': 'host-1', 'policy': {'writeback': {
                    'enabled': True, 'backendResourceUuid': WRITEBACK_RESOURCE_UUID}}}
                with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                     patch.object(memory_optimization, 'probe_writeback_backends') as probe:
                    with self.assertRaisesRegex(ValueError, expected):
                        plugin._validate_backend_resource(command)
                probe.assert_not_called()

        status, detail = writeback_service_views()
        detail['ownership_generation'] = 'c' * 32
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
                                          status if action == 'backend-state' else detail)
        plugin.host_uuid = 'host-1'
        command = {'hostUuid': 'host-1', 'policy': {'writeback': {
            'enabled': True, 'backendResourceUuid': WRITEBACK_RESOURCE_UUID}}}
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
             patch.object(memory_optimization, 'probe_writeback_backends') as probe:
            with self.assertRaisesRegex(ValueError, 'BACKEND_RESOURCE_OWNERSHIP_MISMATCH'):
                plugin._validate_backend_resource(command)
        probe.assert_not_called()
    def test_libvirt_fallback_exposes_running_vm_generation(self):
        class Domain(object):
            def isActive(self): return True
            def UUIDString(self): return 'vm-1'
            def ID(self): return 42
        class Conn(object):
            def listAllDomains(self, flags): return [Domain()]
            def close(self): pass
        class Libvirt(object):
            def openReadOnly(self, uri): return Conn()
        with patch.dict(sys.modules, {'libvirt': Libvirt()}):
            generations, complete = MemoryOptimizationPlugin._libvirt_vm_generations()
        self.assertTrue(complete)
        self.assertEqual('vm-1:42', generations['vm-1']['instanceGeneration'])
    def test_vm_revoke_old_or_missing_generation_is_idempotent_without_go(self):
        binding_dir = tempfile.mkdtemp(prefix='vm-binding-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': binding_dir,
                          'vmBindingDir': binding_dir})
        response = json.loads(plugin.vm_efficiency({'body': json.dumps({
            'hostUuid': 'host-1', 'operationUuid': 'revoke-old',
            'resourceUuid': 'vm-1', 'expectedInstanceGeneration': 'old',
            'action': 'revoke'})}))
        self.assertTrue(response['success'], response)
        self.assertEqual('REVOKED', response['state']['phase'])
    def test_vm_revoke_is_local_cleanup_regardless_of_legacy_permit_or_generation(self):
        binding_dir = tempfile.mkdtemp(prefix='vm-revoke-local-')
        calls = []
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload:
                calls.append((action, payload)) or {'status': 'Succeeded'})
        plugin.configure({'hostUuid': 'host-1', 'operationDir': binding_dir,
                          'vmBindingDir': binding_dir})
        plugin._save_vm_binding({'resourceUuid': 'vm-same',
                                 'expectedInstanceGeneration': 'same',
                                 'operationUuid': 'prior-bind',
                                 'participation': 'allow'})
        cases = [
            {'resourceUuid': 'vm-same', 'expectedInstanceGeneration': 'same',
             'licensePermit': {'managed': True, 'validForSeconds': 30}},
            {'resourceUuid': 'vm-old', 'expectedInstanceGeneration': 'old',
             'licensePermit': {'managed': True, 'validForSeconds': 30}},
            {'resourceUuid': 'vm-missing', 'expectedInstanceGeneration': 'missing'},
        ]
        for index, values in enumerate(cases):
            command = {'hostUuid': 'host-1', 'operationUuid': 'revoke-local-%d' % index,
                       'action': 'revoke'}
            command.update(values)
            response = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
            self.assertTrue(response['success'])
            self.assertEqual('REVOKED', response['state']['phase'])
        self.assertEqual([], calls)
    def test_writeback_default_is_off_but_enabled_requires_backend(self):
        MemoryOptimizationPlugin._validate_policy(
            {'zram': {'enabled': False}, 'writeback': {'enabled': False}})
        with self.assertRaises(ValueError):
            MemoryOptimizationPlugin._validate_policy(
                {'writeback': {'enabled': True}})
    def test_migration_hold_revokes_control_without_license(self):
        path = os.path.join(tempfile.mkdtemp(prefix='memory-hold-'), 'active')
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {'status': 'Succeeded'})
        plugin.configure({'hostUuid': 'host-1', 'operationDir': os.path.dirname(path), 'activeControlPath': path})
        plugin._set_active_control('apply-1')
        result = plugin._dispatch('migration-hold', {
            'hostUuid': 'host-1', 'operationUuid': 'hold-1',
            'holdAction': 'acquire', 'poolGeneration': 'pool-1'})
        self.assertEqual('Succeeded', result['status'])
        self.assertEqual('apply-1', open(path).read())
        plugin._dispatch('migration-hold', {'hostUuid': 'host-1', 'operationUuid': 'hold-1b',
                                            'holdAction': 'release', 'poolGeneration': 'pool-1'})
    def test_uninitialized_pool_snapshot_is_explicit_only(self):
        self.assertTrue(MemoryOptimizationPlugin._is_uninitialized_pool_snapshot({
            'pool_generation': '', 'device': '', 'quality': 'unavailable',
            'reason': 'NO_QUALIFIED_MANAGED_POOL: EXCLUSIVE_ZRAM_ROUTE_REQUIRED'}))
        self.assertFalse(MemoryOptimizationPlugin._is_uninitialized_pool_snapshot({
            'pool_generation': '', 'device': '/dev/zram0', 'quality': 'unavailable',
            'reason': 'NO_QUALIFIED_MANAGED_POOL: EXCLUSIVE_ZRAM_ROUTE_REQUIRED'}))
    def test_not_sent_reconcile_persists_tombstone_and_blocks_late_apply(self):
        root = tempfile.mkdtemp(prefix='memory-not-sent-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root})
        command = {'operationUuid': 'not-sent-1', 'hostUuid': 'host-1',
                   'admissionConnected': False, 'classification': 'NOT_SENT',
                   'reconcileAction': 'seal-if-never-issued',
                   'submittedAt': plugin._boot_epoch_millis() + 1000,
                   'bootId': plugin._current_boot_id()}
        result = plugin._mark_not_issued(command)
        self.assertEqual('OPERATION_NEVER_ISSUED', result['reasonCode'])
        self.assertEqual('NOT_ISSUED', json.load(open(os.path.join(root, 'not-sent-1.json')))['stage'])
        self.assertEqual(result, plugin.apply(dict(command, action='apply')))
        self.assertEqual(result, plugin.apply(dict(command, action='drain')))
        self.assertEqual(result, plugin._mark_not_issued(command))
    def test_not_sent_reconcile_rejects_missing_boot_time_lock_and_persist(self):
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': tempfile.mkdtemp(prefix='memory-not-sent-')})
        base = {'operationUuid': 'not-sent-2', 'hostUuid': 'host-1',
                'admissionConnected': False, 'classification': 'NOT_SENT',
                'reconcileAction': 'seal-if-never-issued',
                'submittedAt': plugin._boot_epoch_millis() + 1000,
                'bootId': plugin._current_boot_id()}
        self.assertEqual('NOT_SENT_SUBMISSION_TIME_UNVERIFIED',
                         plugin._mark_not_issued(dict(base, submittedAt=0))['reasonCode'])
        self.assertEqual('NOT_SENT_SUBMISSION_TIME_FUTURE',
                         plugin._mark_not_issued(dict(base, submittedAt=int(time.time() * 1000) + 60000))['reasonCode'])
        with patch.object(plugin, '_acquire_host_control_lock', side_effect=IOError('busy')):
            self.assertEqual('OPERATION_CONCURRENT', plugin._mark_not_issued(base)['reasonCode'])
        with patch.object(plugin, '_record_operation', return_value=False):
            self.assertEqual('OPERATION_JOURNAL_UNAVAILABLE', plugin._mark_not_issued(
                dict(base, operationUuid='not-sent-3'))['reasonCode'])
        corrupt = os.path.join(plugin.operation_dir, 'not-sent-4.json')
        with open(corrupt, 'w') as stream:
            stream.write('{not-json')
        self.assertEqual('OPERATION_JOURNAL_UNAVAILABLE', plugin._mark_not_issued(
            dict(base, operationUuid='not-sent-4'))['reasonCode'])
    def test_apply_request_runs_real_agent_to_service_policy_chain(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-apply-chain-')
        service, calls = self._strict_policy_service()
        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        with patch.object(plugin, '_apply_ksm_policy', return_value={'run': '1'}):
            response = json.loads(plugin.apply_request({'body': json.dumps({
                'action': 'apply', 'hostUuid': 'host-1',
                'operationUuid': 'apply-chain-1', 'desiredRevision': 12,
                'licensePermit': {'managed': True,
                                  'operationUuid': 'managed-host-1',
                                  'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                'policy': {'ksm': {'enabled': True},
                           'zram': {'enabled': True,
                                    'logicalCapacityBytes': 8192,
                                    'ramLimitBytes': 4096}}})}))
        self.assertTrue(response['success'], response)
        self.assertEqual(12, response['appliedRevision'])
        action_names = [item[0] for item in calls]
        self.assertLess(action_names.index('host-cpu-state'), action_names.index('capacity'))
        self.assertLess(action_names.index('capacity'), action_names.index('apply'))
        self.assertLess(action_names.index('apply'), action_names.index('host-cpu'))
        self.assertNotIn('ksm', calls[action_names.index('apply')][1])
    def test_apply_fills_omitted_global_capacity_from_resolved_service_default(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-default-capacity-')
        service, calls = self._strict_policy_service()
        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        command = {'action': 'apply', 'hostUuid': 'host-1',
                'operationUuid': 'default-capacity-1', 'desiredRevision': 14,
                'licensePermit': {'managed': True,
                                  'operationUuid': 'managed-host-1',
                                  'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                'policy': {'zram': {'enabled': True}}}
        with patch.object(plugin, '_apply_ksm_policy', return_value={}):
            result = plugin.apply(command)
        self.assertTrue(result['success'], result)
        self.assertEqual(16384, command['policy']['zram']['logicalCapacityBytes'])
        self.assertEqual(8192, command['policy']['zram']['ramLimitBytes'])
        self.assertIn('capacity-state', [item[0] for item in calls])
    def test_explicit_zram_disable_calls_service_when_pool_service_exists(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-disable-')
        calls = []
        cpu_state = {'revision': 1, 'efficiency_enabled': False,
                     'idle_cpu_threshold_percent': 80, 'idle_duration_seconds': 60}
        tuning_state = {'revision': 1, 'settings': {'writeback': {}}}
        def service(action, payload):
            calls.append(action)
            if action == 'tuning-state':
                return dict(tuning_state, _http_status=200)
            if action == 'host-cpu-state':
                return dict(cpu_state, _http_status=200)
            if action == 'host-cpu':
                cpu_state.update({'revision': cpu_state['revision'] + 1,
                                  'efficiency_enabled': payload['efficiency_enabled'],
                                  'idle_cpu_threshold_percent': payload['idle_cpu_threshold_percent'],
                                  'idle_duration_seconds': payload['idle_duration_seconds']})
                return dict(cpu_state, request_id=payload['request_id'], _http_status=200)
            if action == 'apply':
                tuning_state.update({'revision': tuning_state['revision'] + 1,
                                     'settings': payload['settings']})
                return dict(tuning_state, _http_status=200)
            return {'status': 'Succeeded'}
        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'socketPath': os.path.join(operation_dir, 'control.sock')})
        open(plugin.socket_path, 'w').close()
        plugin._apply_ksm_policy = lambda command: {}
        response = plugin.apply({
            'hostUuid': 'host-1', 'operationUuid': 'op-disable', 'desiredRevision': 11,
            'licensePermit': {'managed': True, 'operationUuid': 'managed-host-1', 'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
            'policy': {'ksm': {'enabled': False}, 'zram': {'enabled': False},
                       'writeback': {'enabled': False}}})
        self.assertTrue(response['success'], response)
        self.assertIn('host-cpu', calls)
    def test_operation_uuid_is_idempotent_and_reuses_readback(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-idempotent-')
        calls = []
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: self.fail('service must not be called'))
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        plugin._apply_ksm_policy = lambda command: calls.append(command['operationUuid']) or {'configRevision': '8'}
        command = {'hostUuid': 'host-1', 'operationUuid': 'op-idempotent', 'desiredRevision': 8,
                   'licensePermit': {'managed': True, 'operationUuid': 'managed-host-1', 'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': False}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        first = plugin.apply(command)
        second = plugin.apply(command)
        self.assertTrue(first['success'])
        self.assertEqual(first, second)
        self.assertEqual(['op-idempotent'], calls)
    def test_preparing_journal_is_unknown_after_restart_not_replayed(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-restart-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        command = {'hostUuid': 'host-1', 'operationUuid': 'op-restart', 'desiredRevision': 9,
                   'licensePermit': {'managed': True, 'operationUuid': 'managed-host-1', 'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': False}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        plugin._record_operation(command, 'PREPARING')
        response = plugin.apply(command)
        self.assertFalse(response['success'])
        self.assertEqual('OPERATION_RECONCILE_REQUIRED', response['reasonCode'])
    def test_reconcile_reads_back_and_closes_preparing_journal(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-reconcile-')
        def readback(action, payload):
            if action == 'host-cpu-state':
                return {'_http_status': 200, 'revision': 1, 'efficiency_enabled': False,
                        'idle_cpu_threshold_percent': 80,
                        'idle_duration_seconds': 60}
            if action == 'tuning-state':
                return {'revision': 0, 'settings': {
                    'host_floor_bytes': 0, 'metadata_reserve_bytes': 0,
                    'transient_reserve_bytes': 0,
                    'writeback': {'enabled': False,
                                  'batch_bytes': 8 * 1024 * 1024,
                                  'idle_observation_seconds': 10,
                                  'operation_interval_seconds': 5}}}
            return {}
        plugin = MemoryOptimizationPlugin(service_call=readback)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        command = {'hostUuid': 'host-1', 'operationUuid': 'op-reconcile', 'desiredRevision': 10,
                   'licensePermit': {'managed': True, 'operationUuid': 'managed-host-1', 'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': False}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        plugin._record_operation(command, 'PREPARING')
        with patch.object(plugin, '_ksm_readback_matches', return_value=True):
            response = json.loads(plugin.reconcile({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'op-reconcile'})}))
        self.assertTrue(response['success'])
        self.assertEqual(10, response['appliedRevision'])
        with open(os.path.join(operation_dir, 'op-reconcile.json')) as stream:
            self.assertEqual('APPLIED', json.load(stream)['stage'])
    def test_reconcile_reports_known_native_capacity_blocked_and_recovers_read_only(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-capacity-blocked-')
        plugin, reconcile, current, calls = self._capacity_blocked_reconcile_fixture(operation_dir)

        blocked = reconcile()

        self.assertFalse(blocked['success'])
        self.assertEqual('Blocked', blocked['status'])
        # jsonobject.dumps omits None-valued keys on the wire; missing is the
        # Agent's null/not-applied representation for this field.
        self.assertIsNone(blocked.get('appliedRevision'))
        self.assertEqual('BLOCKED', blocked['state']['phase'])
        self.assertIs(blocked['state']['knownBlocked'], True)
        self.assertEqual([{'section': 'capacity', 'code': 'NATIVE_POOL_UNQUALIFIED'}],
                         blocked['blockers'])
        self.assertFalse(blocked['state']['sectionComplete']['capacity'])
        self.assertTrue(blocked['state']['sectionComplete']['cpu'])
        self.assertTrue(blocked['state']['sectionComplete']['tuning'])
        self.assertEqual(['capacity-state', 'host-cpu-state', 'tuning-state'],
                         [action for action, _ in calls])
        with open(os.path.join(operation_dir, 'op-capacity-blocked.json')) as stream:
            journal = json.load(stream)
        self.assertEqual('BLOCKED', journal['stage'])
        self.assertEqual(202, journal['applyEvidence']['state']['sections'][
            'capacity']['_http_status'])

        current.update({'effective_logical_bytes': 1024,
                        'effective_physical_limit_bytes': 256,
                        'apply_state': 'APPLIED',
                        'reason': 'NATIVE_CONFIGURATION_VERIFIED'})
        recovered = reconcile()

        self.assertTrue(recovered['success'])
        self.assertEqual('Succeeded', recovered['status'])
        self.assertEqual(7, recovered['appliedRevision'])
        self.assertEqual(6, len(calls))
        self.assertTrue(all(action.endswith('-state') for action, _ in calls))
        with open(os.path.join(operation_dir, 'op-capacity-blocked.json')) as stream:
            journal = json.load(stream)
        self.assertEqual('APPLIED', journal['stage'])
        self.assertEqual(202, journal['applyEvidence']['state']['sections'][
            'capacity']['_http_status'])
    def test_reconcile_keeps_capacity_result_unknown_without_original_receipt(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-capacity-no-receipt-')
        plugin, reconcile, _, calls = self._capacity_blocked_reconcile_fixture(
            operation_dir, include_receipt=False)

        response = reconcile()

        self.assertFalse(response['success'])
        self.assertEqual('Unknown', response['status'])
        self.assertNotIn('knownBlocked', response.get('state', {}))
        self.assertEqual(3, len(calls))
        with open(os.path.join(operation_dir, 'op-capacity-blocked.json')) as stream:
            self.assertEqual('UNKNOWN', json.load(stream)['stage'])
    def test_reconcile_does_not_guess_capacity_blocker_from_free_text_or_revision_drift(self):
        cases = (
            ('free-text', {'apply_state': 'BLOCKED', 'reason': 'NO_QUALIFIED_MANAGED_POOL'}),
            ('revision-drift', {'apply_state': 'BLOCKED', 'reason': 'NATIVE_POOL_UNQUALIFIED',
                                'revision': 7}),
        )
        for name, changes in cases:
            with self.subTest(name=name):
                operation_dir = tempfile.mkdtemp(prefix='memory-ops-capacity-%s-' % name)
                current = {'_http_status': 200, 'revision': 5,
                           'desired': {'configured': {
                               'logical_capacity': {'bytes': 1024},
                               'physical_memory_limit': {'bytes': 256}}},
                           'effective_logical_bytes': None,
                           'effective_physical_limit_bytes': None,
                           'apply_state': 'BLOCKED',
                           'reason': 'NATIVE_POOL_UNQUALIFIED'}
                current.update(changes)
                _, reconcile, _, calls = self._capacity_blocked_reconcile_fixture(
                    operation_dir, capacity_state=current)

                response = reconcile()

                self.assertFalse(response['success'])
                self.assertEqual('Unknown', response['status'])
                self.assertNotIn('knownBlocked', response.get('state', {}))
                self.assertEqual(3, len(calls))
    def test_reconcile_requires_capacity_cpu_receipt_chain_for_known_blocked(self):
        mutations = (
            ('wrong-capacity-request', lambda state: state['sections']['capacity'].__setitem__(
                'agent_request_id', 'other-operation-capacity')),
            ('missing-capacity-request-binding', lambda state: state['sections']['capacity'].pop(
                'agent_request_id')),
            ('native-capacity-request-conflict', lambda state: state['sections']['capacity'].__setitem__(
                'request_id', 'other-operation-capacity')),
            ('missing-capacity-request', lambda state: state['sections']['capacity'].pop(
                'agent_request_id')),
            ('missing-capacity-revision', lambda state: state['sections']['capacity'].pop(
                'agent_expected_revision')),
            ('pre-cpu-capacity-revision-drift', lambda state: state['sections'][
                'capacityReadback'].__setitem__('revision', 4)),
            ('pre-cpu-capacity-target-drift', lambda state: state['sections'][
                'capacityReadback']['desired']['configured']['logical_capacity'].__setitem__(
                    'bytes', 2048)),
            ('wrong-cpu-request', lambda state: state['sections']['cpu'].__setitem__(
                'request_id', 'other-operation-cpu')),
            ('cpu-cas-after-unrelated-writer', lambda state: state['sections']['cpu'].__setitem__(
                'agent_expected_revision', 6)),
            ('cpu-not-written', lambda state: state['sections'].pop('cpu')),
            ('cpu-readback-revision-drift', lambda state: state['sections'][
                'cpuReadback'].__setitem__('revision', 5)),
            ('cpu-section-incomplete', lambda state: state['sectionComplete'].__setitem__(
                'cpu', False)),
            ('cpu-threshold-wrong', lambda state: state['sections']['cpuReadback'].__setitem__(
                'idle_cpu_threshold_percent', 99)),
            ('cpu-duration-wrong', lambda state: state['sections']['cpuReadback'].__setitem__(
                'idle_duration_seconds', 61)),
            ('missing-tuning-request-binding', lambda state: state['sections']['tuning'].pop(
                'request_id')),
            ('wrong-tuning-request-binding', lambda state: state['sections']['tuning'].__setitem__(
                'request_id', 'other-operation-tuning')),
        )
        for name, mutate in mutations:
            with self.subTest(name=name):
                operation_dir = tempfile.mkdtemp(prefix='memory-ops-capacity-proof-%s-' % name)
                plugin, reconcile, _, calls = self._capacity_blocked_reconcile_fixture(operation_dir)
                path = os.path.join(operation_dir, 'op-capacity-blocked.json')
                with open(path) as stream:
                    journal = json.load(stream)
                mutate(journal['applyEvidence']['state'])
                with open(path, 'w') as stream:
                    json.dump(journal, stream)

                response = reconcile()

                self.assertEqual('Unknown', response['status'], response)
                self.assertNotIn('knownBlocked', response.get('state', {}))
                self.assertEqual(['capacity-state', 'host-cpu-state', 'tuning-state'],
                                 [action for action, _ in calls])
                with open(path) as stream:
                    self.assertEqual('UNKNOWN', json.load(stream)['stage'])
    def test_reconcile_accepts_exact_operation_bound_cpu_revision_without_arithmetic(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-capacity-opaque-revisions-')
        plugin, reconcile, current, _ = self._capacity_blocked_reconcile_fixture(operation_dir)
        # Revisions are opaque tokens: require final capacity and CPU state to
        # equal this operation's CPU receipt, not a computed N+1.
        current['revision'] = 91
        observed_cpu = {'_http_status': 200, 'revision': 91,
                        'efficiency_enabled': True,
                        'idle_cpu_threshold_percent': 5,
                        'idle_duration_seconds': 60}
        original = plugin.service_call
        def service(action, payload):
            if action == 'host-cpu-state':
                return observed_cpu
            return original(action, payload)
        plugin.service_call = service
        path = os.path.join(operation_dir, 'op-capacity-blocked.json')
        with open(path) as stream:
            journal = json.load(stream)
        journal['applyEvidence']['state']['sections']['cpu']['revision'] = 91
        journal['applyEvidence']['state']['sections']['cpu']['agent_expected_revision'] = 5
        journal['applyEvidence']['state']['sections']['cpuReadback']['revision'] = 91
        with open(path, 'w') as stream:
            json.dump(journal, stream)

        response = reconcile()

        self.assertEqual('Blocked', response['status'], response)
        self.assertEqual('BLOCKED', response['state']['phase'])
    def test_capacity_only_target_uses_persisted_preoperation_cpu_baseline(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-capacity-only-cpu-baseline-')
        plugin, reconcile, _, _ = self._capacity_blocked_reconcile_fixture(operation_dir)
        path = os.path.join(operation_dir, 'op-capacity-blocked.json')
        with open(path) as stream:
            journal = json.load(stream)
        evidence = journal['applyEvidence']['state']
        journal['policy']['zram'].pop('enabled')
        journal['policyHash'] = plugin._policy_digest(journal['policy'])
        evidence['sections']['cpuBefore']['efficiency_enabled'] = True
        evidence['sections']['cpu']['agent_desired_enabled'] = True
        evidence['sections']['cpu']['efficiency_enabled'] = True
        evidence['sections']['cpuReadback']['efficiency_enabled'] = True
        with open(path, 'w') as stream:
            json.dump(journal, stream)

        response = reconcile()

        self.assertEqual('Blocked', response['status'], response)
        self.assertEqual('NATIVE_POOL_UNQUALIFIED', response['blockers'][0]['code'])
    def test_r2_delta_parameter_only_and_explicit_zram_disable_reach_service(self):
        cases = (
            ('parameter-only', {'zram': {'cpuThresholdPercent': 40},
                                'writeback': {'enabled': False}}, False),
            ('explicit-disable', {'zram': {'enabled': False},
                                  'writeback': {'enabled': False}}, True),
        )
        for name, policy, needs_socket in cases:
            with self.subTest(delta=name):
                root = tempfile.mkdtemp(prefix='r2-delta-service-%s-' % name)
                plugin, initial, service_writes, native_ack, native_command, native_conf = \
                    self._r2_mixed_delta_fixture(root, name)
                if needs_socket:
                    Path(plugin.socket_path).touch()
                command = self._r2_command(initial, 'r2-delta-service-' + name,
                                           policy, mode='delta')
                self._assert_r2_delta_does_not_touch_ksm(
                    plugin, command, service_writes, native_ack, native_command, native_conf)
    def test_r2_invalid_policy_mode_is_rejected_before_native_or_service_side_effects(self):
        invalid_modes = (None, True, 7, [], {}, 'DELTA', 'unknown')
        for index, mode in enumerate(invalid_modes):
            with self.subTest(policyMode=mode):
                root = tempfile.mkdtemp(prefix='r2-invalid-policy-mode-')
                plugin, initial, service_writes, native_ack, native_command, native_conf = \
                    self._r2_mixed_delta_fixture(root, 'invalid-mode-%s' % index)
                command = self._r2_command(initial, 'r2-invalid-mode-%s' % index, {
                    'ksm': {'pagesToScan': 701},
                    'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                             'ramLimitBytes': 4096},
                    'writeback': {'enabled': False}}, mode=mode)
                writes_before = len(service_writes)
                ack_before = dict(native_ack)
                with patch.object(subprocess, 'check_output', side_effect=native_command):
                    result = plugin.apply(command)
                violations = []
                if result.get('status') != 'Failed' or 'policyMode' not in (result.get('reason') or ''):
                    violations.append('invalid mode was not rejected: %r' % result)
                if writes_before != len(service_writes):
                    violations.append('service side effect occurred')
                if ack_before != native_ack:
                    violations.append('native KSM ACK changed')
                if native_conf != Path(plugin.KSM_CONF).read_bytes():
                    violations.append('native KSM config changed')
                self.assertEqual([], violations)
    def test_r2_mode_is_journaled_retry_is_stable_and_mode_reuse_preserves_original_proof(self):
        root = tempfile.mkdtemp(prefix='r2-policy-mode-replay-')
        plugin, initial, service_writes, native_ack, native_command, _ = \
            self._r2_mixed_delta_fixture(root, 'mode-replay')
        command = self._r2_command(initial, 'r2-mode-replay', {
            'ksm': {'pagesToScan': 701},
            'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096},
            'writeback': {'enabled': False}}, mode='delta')
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            first = plugin.apply(command)
        self.assertTrue(first.get('success'), first)
        record_path = os.path.join(plugin.operation_dir, command['operationUuid'] + '.json')
        original_record = json.load(open(record_path))
        original_hash = original_record.get('requestHash')

        writes_after_first = len(service_writes)
        native_after_first = dict(native_ack)
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            replay = plugin.apply(command)
        self.assertEqual(first, replay)
        self.assertEqual(writes_after_first, len(service_writes))
        self.assertEqual(native_after_first, native_ack)

        changed_mode = dict(command, policyMode='effective')
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            conflict = plugin.apply(changed_mode)
        after_conflict = json.load(open(record_path))
        violations = []
        if original_record.get('policyMode') != 'delta':
            violations.append('successful journal does not persist delta mode')
        if replay != first:
            violations.append('exact retry changed its response')
        if conflict.get('status') == 'Succeeded' or 'OPERATION_UUID_REUSE' not in (
                (conflict.get('reason') or '') + (conflict.get('reasonCode') or '')):
            violations.append('same UUID with changed mode was not rejected: %r' % conflict)
        if original_hash != after_conflict.get('requestHash'):
            violations.append('rejected mode drift overwrote the original request hash')
        if after_conflict.get('policyMode') != 'delta':
            violations.append('rejected mode drift relabeled the original mode')
        if original_record.get('readback') != after_conflict.get('readback'):
            violations.append('rejected mode drift overwrote the original successful proof')
        if writes_after_first != len(service_writes):
            violations.append('retry or conflict repeated a Go service write')
        if native_after_first != native_ack:
            violations.append('retry or conflict touched native KSM')
        self.assertEqual([], violations)
    def test_r2_legacy_mode_absence_is_effective_behavior_and_exact_replay(self):
        root = tempfile.mkdtemp(prefix='r2-legacy-mode-absence-')
        plugin, initial, service_writes, native_ack, native_command, _ = \
            self._r2_mixed_delta_fixture(root, 'legacy-mode')
        command = self._r2_command(initial, 'r2-legacy-effective', {
            'ksm': {'enabled': True, 'pagesToScan': 601,
                    'sleepMillis': 30, 'zeroPagesEnabled': False},
            'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096},
            'writeback': {'enabled': False}}, mode=_OMIT_POLICY_MODE)
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            first = plugin.apply(command)
        self.assertTrue(first.get('success'), first)
        record_path = os.path.join(plugin.operation_dir, command['operationUuid'] + '.json')
        record = json.load(open(record_path))
        writes_after = len(service_writes)
        ack_after = dict(native_ack)
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            replay = plugin.apply(command)
        violations = []
        if first.get('status') != 'Succeeded':
            violations.append('legacy missing-mode command did not use effective behavior')
        if record.get('policyMode') != 'effective':
            violations.append('legacy journal did not persist normalized effective mode')
        if first != replay:
            violations.append('exact legacy replay changed its response')
        if writes_after != len(service_writes):
            violations.append('exact legacy replay repeated service work')
        if ack_after != native_ack:
            violations.append('exact legacy replay changed native KSM ACK')
        self.assertEqual([], violations)
    def test_r3_mixed_clear_with_untrusted_go_preflight_has_no_native_or_service_write(self):
        root = tempfile.mkdtemp(prefix='r3-mixed-clear-untrusted-go-')
        plugin, initial, service_writes, native_ack, native_command, native_conf = \
            self._r2_mixed_delta_fixture(root, 'untrusted-go-preflight')
        service_calls = []
        original_service_call = plugin.service_call

        def recording_service_call(action, payload):
            service_calls.append((action, dict(payload or {})))
            if action == 'capacity-state':
                return {'_http_status': 503, 'error': 'injected untrusted preflight'}
            return original_service_call(action, payload)

        plugin.service_call = recording_service_call
        clear = self._r2_command(initial, 'r3-untrusted-go-clear', {
            'ksm': {}, 'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                                'ramLimitBytes': 4096, 'cpuThresholdPercent': 40},
            'writeback': {'enabled': False}}, mode='effective', revision=2)
        before_ack = dict(native_ack)
        before_writes = len(service_writes)
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(clear)
        actions = [action for action, _ in service_calls]
        self.assertEqual('Unknown', result.get('status'), result)
        self.assertTrue(any(action in actions for action in
                            ('capacity-state', 'host-cpu-state', 'tuning-state')),
                        'untrusted Go prior state was not actually preflighted: %r' % actions)
        self.assertEqual(before_ack, native_ack, 'native KSM changed despite untrusted Go state')
        self.assertEqual(before_writes, len(service_writes), 'Go write despite untrusted preflight')
        self.assertEqual(native_conf, Path(plugin.KSM_CONF).read_bytes())
        record = json.load(open(os.path.join(root, clear['operationUuid'] + '.json')))
        self.assertEqual('UNKNOWN', record.get('stage'))
        self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
    def test_r3_effective_mixed_clear_with_explicit_zram_disable_reaches_service(self):
        root = tempfile.mkdtemp(prefix='r3-mixed-clear-disable-')
        plugin, events, native_ack, _, _, native_command = \
            self._r3_stateful_mixed_fixture(root, 'disable')
        Path(plugin.socket_path).touch()
        result, record, trace = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-disable-clear', 2,
            {'enabled': False})
        actions = [entry[1] for entry in trace if entry[0] == 'go']
        self.assertEqual('Succeeded', result.get('status'), result)
        self.assertEqual('2', native_ack.get('configRevision'))
        self.assertTrue((record.get('readback') or {}).get('ksmReadback'), record)
        self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
        self.assertIn('host-cpu', actions)
        self.assertIn('apply', actions)
    def test_r3_effective_mixed_clear_with_parameter_only_zram_reaches_service(self):
        root = tempfile.mkdtemp(prefix='r3-mixed-clear-parameter-only-')
        plugin, events, native_ack, _, _, native_command = \
            self._r3_stateful_mixed_fixture(root, 'parameter-only')
        result, record, trace = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-parameter-only-clear', 2,
            {'cpuThresholdPercent': 35})
        actions = [entry[1] for entry in trace if entry[0] == 'go']
        self.assertEqual('Succeeded', result.get('status'), result)
        self.assertEqual('2', native_ack.get('configRevision'))
        self.assertTrue((record.get('readback') or {}).get('ksmReadback'), record)
        self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
        self.assertIn('host-cpu', actions)
        self.assertIn('apply', actions)
    def test_r3_effective_mixed_clear_with_tuning_only_zram_reaches_service(self):
        root = tempfile.mkdtemp(prefix='r3-mixed-clear-tuning-only-')
        plugin, events, native_ack, _, _, native_command = \
            self._r3_stateful_mixed_fixture(root, 'tuning-only')
        result, record, trace = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-tuning-only-clear', 2,
            {'operationIntervalSeconds': 3}, writeback={})
        actions = [entry[1] for entry in trace if entry[0] == 'go']
        self.assertEqual('Succeeded', result.get('status'), result)
        self.assertEqual('2', native_ack.get('configRevision'))
        self.assertTrue((record.get('readback') or {}).get('ksmReadback'), record)
        self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
        self.assertIn('apply', actions)
        self.assertNotIn('capacity', actions)
        self.assertNotIn('host-cpu', actions)
    def test_r3_consecutive_mixed_clears_keep_proof_bounded(self):
        root = tempfile.mkdtemp(prefix='r3-mixed-clear-bounded-proof-')
        plugin, events, native_ack, _, _, native_command = \
            self._r3_stateful_mixed_fixture(root, 'bounded-proof')
        policy = {'enabled': True, 'logicalCapacityBytes': 8192,
                  'ramLimitBytes': 4096, 'cpuThresholdPercent': 40}
        first, first_record, _ = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-bounded-clear-1', 2, policy)
        self.assertEqual('Succeeded', first.get('status'), first)
        self.assertEqual('2', native_ack.get('configRevision'))
        second, second_record, _ = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-bounded-clear-2', 3, policy)
        self.assertEqual('Succeeded', second.get('status'), second)
        self.assertEqual('3', native_ack.get('configRevision'))
        evidence1 = ((first_record.get('readback') or {}).get('state') or {}).get(
            'mixedClearEvidence')
        evidence2 = ((second_record.get('readback') or {}).get('state') or {}).get(
            'mixedClearEvidence')
        self.assertIsInstance(evidence1, dict)
        self.assertIsInstance(evidence2, dict)
        self.assertEqual('r3-bounded-clear-1', evidence2.get('priorOperationUuid'))
        prior_state = evidence2.get('priorState') or {}
        self.assertTrue(prior_state)
        self.assertTrue(set(prior_state).issubset(
            {'capacity', 'cpu', 'tuning', 'hostPolicyRevision'}), prior_state)
        self.assertNotIn('mixedClearEvidence', prior_state)
        self.assertNotIn('mixedClearEvidence', prior_state.get('state', {}))
    def test_r3_consecutive_tuning_only_clears_use_current_bounded_receipts(self):
        root = tempfile.mkdtemp(prefix='r3-tuning-only-clear-twice-')
        plugin, events, native_ack, _, _, native_command = \
            self._r3_stateful_mixed_fixture(root, 'tuning-only-twice')
        first, first_record, _ = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-tuning-clear-first', 2,
            {'operationIntervalSeconds': 3}, writeback={})
        self.assertEqual('Succeeded', first.get('status'), first)
        self.assertEqual('2', native_ack.get('configRevision'))
        second, second_record, _ = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-tuning-clear-second', 3,
            {'operationIntervalSeconds': 4}, writeback={})
        self.assertEqual('Succeeded', second.get('status'), second)
        self.assertEqual('3', native_ack.get('configRevision'))
        evidence1 = ((first_record.get('readback') or {}).get('state') or {}).get(
            'mixedClearEvidence')
        evidence2 = ((second_record.get('readback') or {}).get('state') or {}).get(
            'mixedClearEvidence')
        self.assertIsInstance(evidence1, dict)
        self.assertIsInstance(evidence2, dict)
        self.assertEqual('r3-tuning-clear-first', evidence2.get('priorOperationUuid'))
        prior_state = evidence2.get('priorState') or {}
        self.assertEqual({'hostPolicyRevision', 'tuning'}, set(prior_state))
        self.assertIsInstance(prior_state.get('hostPolicyRevision'), int)
        self.assertNotIn('mixedClearEvidence', prior_state)
    def test_r3_tuning_only_clear_rejects_corrupted_current_mixed_evidence(self):
        mutations = ('incomplete', 'wrong-operation', 'float-cpu-revision')
        for mutation in mutations:
            with self.subTest(evidence=mutation):
                root = tempfile.mkdtemp(prefix='r3-tuning-only-corrupt-evidence-')
                plugin, events, native_ack, _, _, native_command = \
                    self._r3_stateful_mixed_fixture(root, 'corrupt-' + mutation)
                first, first_record, _ = self._r3_apply_effective_clear(
                    plugin, root, events, native_command,
                    'r3-corrupt-evidence-first-' + mutation, 2,
                    {'operationIntervalSeconds': 3}, writeback={})
                self.assertEqual('Succeeded', first.get('status'), first)
                first_state = (first_record.get('readback') or {}).get('state') or {}
                evidence = first_state.get('mixedClearEvidence') or {}
                self.assertNotIn('capacity', evidence.get('writes') or {}, evidence)
                self.assertNotIn('host-cpu', evidence.get('writes') or {}, evidence)
                self.assertTrue(evidence.get('complete'), evidence)
                self.assertEqual('r3-corrupt-evidence-first-' + mutation,
                                 evidence.get('operationUuid'), evidence)
                postflight = evidence.get('postflight') or {}
                capacity_revision = (postflight.get('capacity') or {}).get('revision')
                cpu_revision = (postflight.get('cpu') or {}).get('revision')
                self.assertIsInstance(capacity_revision, int, evidence)
                self.assertEqual(capacity_revision, cpu_revision, evidence)

                first_path = os.path.join(root,
                                          'r3-corrupt-evidence-first-' + mutation + '.json')
                saved = json.load(open(first_path))
                saved_evidence = saved['readback']['state']['mixedClearEvidence']
                if mutation == 'incomplete':
                    saved_evidence['complete'] = False
                elif mutation == 'wrong-operation':
                    saved_evidence['operationUuid'] = 'different-operation-uuid'
                else:
                    saved_evidence['postflight']['cpu']['revision'] = float(capacity_revision)
                with open(first_path, 'w') as stream:
                    json.dump(saved, stream, sort_keys=True)
                    stream.write('\n')

                before_ack = dict(native_ack)
                before_conf = Path(plugin.KSM_CONF).read_bytes()
                second, second_record, trace = self._r3_apply_effective_clear(
                    plugin, root, events, native_command,
                    'r3-corrupt-evidence-second-' + mutation, 3,
                    {'operationIntervalSeconds': 4}, writeback={})
                self.assertEqual('Unknown', second.get('status'), second)
                self.assertEqual('UNKNOWN', second_record.get('stage'), second_record)
                self.assertEqual(before_ack, native_ack,
                                 'corrupt current mixed proof changed native KSM')
                self.assertEqual(before_conf, Path(plugin.KSM_CONF).read_bytes(),
                                 'corrupt current mixed proof changed KSM config')
                actions = [entry[1] for entry in trace if entry[0] == 'go']
                self.assertFalse(set(actions).intersection({'capacity', 'host-cpu', 'apply'}),
                                 actions)
    def test_r3_parameter_only_clear_rejects_malformed_applied_capacity_before_writes(self):
        mutations = ('missing-logical', 'missing-physical',
                     'boolean-logical', 'boolean-physical')
        for mutation in mutations:
            with self.subTest(capacity=mutation):
                root = tempfile.mkdtemp(prefix='r3-parameter-only-malformed-capacity-')
                plugin, events, native_ack, service_state, _, native_command = \
                    self._r3_stateful_mixed_fixture(root, 'malformed-' + mutation)
                first, first_record, _ = self._r3_apply_effective_clear(
                    plugin, root, events, native_command,
                    'r3-malformed-capacity-first-' + mutation, 2,
                    {'cpuThresholdPercent': 35}, writeback={'enabled': False})
                self.assertEqual('Succeeded', first.get('status'), first)
                first_evidence = (((first_record.get('readback') or {}).get('state') or {})
                                  .get('mixedClearEvidence') or {})
                writes = first_evidence.get('writes') or {}
                self.assertNotIn('capacity', writes, first_evidence)
                self.assertIn('host-cpu', writes, first_evidence)
                self.assertIn('apply', writes, first_evidence)
                self.assertTrue(service_state['host-cpu-state']['efficiency_enabled'])
                self.assertEqual('APPLIED', service_state['capacity-state']['apply_state'])

                capacity = service_state['capacity-state']
                if mutation == 'missing-logical':
                    capacity.pop('effective_logical_bytes')
                elif mutation == 'missing-physical':
                    capacity.pop('effective_physical_limit_bytes')
                elif mutation == 'boolean-logical':
                    capacity['effective_logical_bytes'] = True
                else:
                    capacity['effective_physical_limit_bytes'] = False

                before_ack = dict(native_ack)
                before_conf = Path(plugin.KSM_CONF).read_bytes()
                second, second_record, trace = self._r3_apply_effective_clear(
                    plugin, root, events, native_command,
                    'r3-malformed-capacity-second-' + mutation, 3,
                    {'cpuThresholdPercent': 35}, writeback={'enabled': False})
                self.assertEqual('Unknown', second.get('status'), second)
                self.assertEqual('UNKNOWN', second_record.get('stage'), second_record)
                self.assertEqual(before_ack, native_ack,
                                 'malformed APPLIED capacity changed native KSM')
                self.assertEqual(before_conf, Path(plugin.KSM_CONF).read_bytes(),
                                 'malformed APPLIED capacity changed KSM config')
                actions = [entry[1] for entry in trace if entry[0] == 'go']
                self.assertFalse(set(actions).intersection({'capacity', 'host-cpu', 'apply'}),
                                 actions)
    def test_r3_mixed_clear_rejects_mismatched_prior_cpu_receipt_request_id(self):
        root = tempfile.mkdtemp(prefix='r3-prior-cpu-request-id-mismatch-')
        plugin, events, native_ack, _, _, native_command = \
            self._r3_stateful_mixed_fixture(root, 'cpu-receipt-mismatch')
        prior_path = os.path.join(root, 'r3-fixture-cpu-receipt-mismatch.json')
        prior = json.load(open(prior_path))
        prior['readback']['state']['sections']['cpu']['request_id'] = 'different-operation-cpu'
        with open(prior_path, 'w') as stream:
            json.dump(prior, stream, sort_keys=True)
            stream.write('\n')
        events.clear()
        result, record, trace = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-bad-prior-cpu-receipt', 2,
            {'enabled': True, 'logicalCapacityBytes': 8192,
             'ramLimitBytes': 4096, 'cpuThresholdPercent': 40})
        self.assertEqual('Unknown', result.get('status'), result)
        self.assertEqual('1', native_ack.get('configRevision'))
        actions = [entry[1] for entry in trace if entry[0] == 'go']
        self.assertFalse(set(actions).intersection({'capacity', 'host-cpu', 'apply'}), actions)
        self.assertEqual('UNKNOWN', record.get('stage'))
        self.assertNotIn('ksmReadback', record.get('readback') or {})
    def test_r3_mixed_clear_preflight_bad_gets_fail_before_any_write(self):
        cases = (
            ('missing-idle-duration', 'host-cpu-state', 'missing_idle_duration'),
            ('missing-enabled', 'host-cpu-state', 'missing_efficiency_enabled'),
            ('unknown-status', 'capacity-state', 'status_unknown'),
            ('unknown-phase', 'host-cpu-state', 'phase_unknown'),
            ('error-envelope', 'capacity-state', 'error_envelope'),
            ('false-success', 'tuning-state', 'success_false'),
            ('float-http-status', 'capacity-state', 'float_http_status'),
            ('boolean-revision', 'tuning-state', 'bool_revision'))
        for name, action, kind in cases:
            with self.subTest(fault=name):
                root = tempfile.mkdtemp(prefix='r3-preflight-fault-')
                plugin, events, native_ack, _, faults, native_command = \
                    self._r3_stateful_mixed_fixture(root, name)
                faults.update({'get_when': 'preflight', 'get_action': action,
                               'get_kind': kind})
                result, record, trace = self._r3_apply_effective_clear(
                    plugin, root, events, native_command, 'r3-preflight-' + name, 2,
                    {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096, 'cpuThresholdPercent': 40})
                self.assertEqual('Unknown', result.get('status'), result)
                self.assertEqual('1', native_ack.get('configRevision'))
                actions = [entry[1] for entry in trace if entry[0] == 'go']
                self.assertIn(action, actions)
                self.assertFalse(set(actions).intersection({'capacity', 'host-cpu', 'apply'}), actions)
                self.assertEqual('UNKNOWN', record.get('stage'))
                self.assertNotIn('ksmReadback', record.get('readback') or {})
                self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
    def test_r3_mixed_clear_postflight_bad_get_retains_ack_and_write_receipts(self):
        cases = (
            ('stale-host-revision', 'capacity-state', 'stale_revision'),
            ('unknown-status', 'host-cpu-state', 'status_unknown'),
            ('unknown-phase', 'host-cpu-state', 'phase_unknown'),
            ('error-envelope', 'capacity-state', 'error_envelope'),
            ('false-success', 'tuning-state', 'success_false'),
            ('float-http-status', 'capacity-state', 'float_http_status'),
            ('boolean-revision', 'tuning-state', 'bool_revision'),
            ('wrong-capacity', 'capacity-state', 'wrong_capacity'))
        for name, action, kind in cases:
            with self.subTest(fault=name):
                root = tempfile.mkdtemp(prefix='r3-postflight-fault-')
                plugin, events, native_ack, _, faults, native_command = \
                    self._r3_stateful_mixed_fixture(root, name)
                faults.update({'get_when': 'postflight', 'get_action': action,
                               'get_kind': kind})
                result, record, trace = self._r3_apply_effective_clear(
                    plugin, root, events, native_command, 'r3-postflight-' + name, 2,
                    {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096, 'cpuThresholdPercent': 40})
                self.assertEqual('Unknown', result.get('status'), result)
                self.assertEqual('2', native_ack.get('configRevision'))
                self.assertEqual('UNKNOWN', record.get('stage'))
                readback = record.get('readback') or {}
                self.assertTrue(readback.get('ksmReadback'), readback)
                self.assertNotIn('ksmOnly', (readback.get('state') or {}))
                evidence = ((readback.get('state') or {}).get('mixedClearEvidence') or {})
                writes = evidence.get('writes') or {}
                self.assertTrue(any(key in writes for key in ('capacity', 'host-cpu', 'apply')),
                                evidence)
                self.assertFalse(evidence.get('complete') is True, evidence)
                actions = [entry[1] for entry in trace if entry[0] == 'go']
                self.assertIn(action, actions)
    def test_r3_effective_mixed_clear_go_put_failure_after_native_ack_stays_unknown(self):
        for mode in ('http-error', 'transport-timeout'):
            with self.subTest(failure=mode):
                root = tempfile.mkdtemp(prefix='r3-mixed-clear-post-ack-failure-')
                plugin, events, native_ack, _, faults, native_command = \
                    self._r3_stateful_mixed_fixture(root, mode)
                if mode == 'http-error':
                    faults['fail_action'] = 'host-cpu'
                else:
                    faults['raise_action'] = 'host-cpu'
                result, record, trace = self._r3_apply_effective_clear(
                    plugin, root, events, native_command, 'r3-post-ack-' + mode, 2,
                    {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096, 'cpuThresholdPercent': 40})
                self.assertEqual('Unknown', result.get('status'), result)
                self.assertEqual('2', native_ack.get('configRevision'),
                                 'native KSM should have ACKed before Go PUT failure')
                self.assertEqual('UNKNOWN', record.get('stage'))
                self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
                names = [entry[1] for entry in trace if entry[0] == 'go']
                self.assertIn('capacity', names)
                self.assertIn('host-cpu', names,
                              'journal must distinguish attempted host-cpu write from omitted section')
                readback = record.get('readback') or {}
                self.assertTrue(readback.get('ksmReadback'), readback)
                evidence = ((readback.get('state') or {}).get('mixedClearEvidence') or {})
                self.assertIn('capacity', evidence.get('writes') or {})
                attempts = evidence.get('writeAttempts') or {}
                self.assertIn('host-cpu', attempts,
                              'unknown CPU result must be durable as attempted, not absent')
                self.assertIn(str(attempts['host-cpu']).upper(),
                              ('UNKNOWN', 'ATTEMPTED', 'RESULT_UNKNOWN'))
    def test_r3_native_ack_missing_zero_pages_or_unreadable_never_reaches_go(self):
        for failure in ('omit-zero-pages', 'readback-error-after-write'):
            with self.subTest(native_ack=failure):
                root = tempfile.mkdtemp(prefix='r3-native-ack-incomplete-')
                plugin, events, native_ack, _, faults, native_command = \
                    self._r3_stateful_mixed_fixture(root, failure)
                faults['native_ack_fault'] = failure
                result, record, trace = self._r3_apply_effective_clear(
                    plugin, root, events, native_command, 'r3-native-ack-' + failure, 2,
                    {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096, 'cpuThresholdPercent': 40})
                self.assertEqual('Unknown', result.get('status'), result)
                expected_revision = 1 if failure == 'omit-zero-pages' else 2
                # The omitted-attribute fault runs before any KSM write; the
                # readback-error fault is injected only after the native config
                # has advanced, but neither permits a Go mutation.
                self.assertEqual(expected_revision,
                                 plugin._read_native_ksm_config().get('CONFIG_REVISION'))
                self.assertEqual('UNKNOWN', record.get('stage'))
                readback = record.get('readback') or {}
                self.assertNotIn('ksmReadback', readback,
                                 'missing/unreadable native evidence must not be fabricated')
                self.assertNotIn('ksmOnly', (readback.get('state') or {}))
                actions = [entry[1] for entry in trace if entry[0] == 'go']
                self.assertFalse(set(actions).intersection({'capacity', 'host-cpu', 'apply'}),
                                 actions)
    def test_r3_active_zram_with_unconfigured_capacity_fails_closed(self):
        root = tempfile.mkdtemp(prefix='r3-active-unconfigured-capacity-clear-')
        plugin, events, native_ack, service_state, _, native_command = \
            self._r3_stateful_mixed_fixture(root, 'active-unconfigured-capacity')
        cap = service_state['capacity-state']
        cap.update({'desired': None, 'effective_logical_bytes': None,
                    'effective_physical_limit_bytes': None,
                    'apply_state': 'BLOCKED', 'reason': 'CAPACITY_NOT_CONFIGURED'})
        before_ack = dict(native_ack)
        result, record, trace = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-active-unconfigured-clear', 2,
            {'enabled': True, 'logicalCapacityBytes': 8192,
             'ramLimitBytes': 4096, 'cpuThresholdPercent': 40})
        self.assertEqual('Unknown', result.get('status'), result)
        self.assertEqual(before_ack, native_ack)
        actions = [entry[1] for entry in trace if entry[0] == 'go']
        self.assertFalse(set(actions).intersection({'capacity', 'host-cpu', 'apply'}), actions)
        self.assertEqual('UNKNOWN', record.get('stage'))
        self.assertNotIn('ksmReadback', record.get('readback') or {})
        self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
    def test_managed_native_config_clear_advances_complete_native_ack(self):
        root = tempfile.mkdtemp(prefix='managed-marker-clear-ksm-')
        plugin, initial, _, _, _ = self._managed_clear_fixture(root, 91, enabled=False)
        self.assertEqual({'run': '0', 'configRevision': '91', 'pages_to_scan': '600',
                          'sleep_millisecs': '30', 'use_zero_pages': '0'},
                         plugin._read_ksm_ack())
        with open(plugin.KSM_CONF) as stream:
            from kvmagent.plugins.memory_optimization_ksm_native import managed_config_values
            identity = managed_config_values(stream.read())
        self.assertEqual({'CONFIG_REVISION': 91, 'KSM_NPAGES_MIN': 600,
                          'KSM_NPAGES_MAX': 600, 'KSM_NPAGES_BOOST': 0,
                          'KSM_NPAGES_DECAY': 0, 'KSM_SLEEP_MSEC': 177,
                          'KSM_THRES_COEF': 100, 'KSM_THRES_CONST': 2048}, identity)

        cleared = self._clear_managed_policy(initial, 'managed-marker-clear-after')
        result = plugin.apply(cleared)
        self.assertTrue(result['success'])
        self.assertEqual('Succeeded', result['status'])
        self.assertEqual('92', plugin._read_ksm_ack().get('configRevision'))
        with open(os.path.join(root, cleared['operationUuid'] + '.json')) as stream:
            record = json.load(stream)
        proof = record['readback']['ksmReadback']
        self.assertEqual({'run': '0', 'configRevision': '92', 'pages_to_scan': '600',
                          'sleep_millisecs': '30', 'use_zero_pages': '0'},
                         {key: proof[key] for key in ('run', 'configRevision', 'pages_to_scan',
                                                      'sleep_millisecs', 'use_zero_pages')})
    def test_second_clear_with_new_request_and_revision_continues_full_empty_policy_proof(self):
        """A prior successful clear itself is managed proof for the next clear."""
        root = tempfile.mkdtemp(prefix='managed-marker-clear-twice-')
        plugin, initial, _, _, _ = self._managed_clear_fixture(
            root, revision=121, enabled=False)
        first_clear = self._clear_managed_policy(initial, 'managed-clear-first-request')
        first_result = plugin.apply(first_clear)
        self.assertTrue(first_result['success'])
        self.assertEqual('122', plugin._read_ksm_ack()['configRevision'])
        first_path = os.path.join(root, first_clear['operationUuid'] + '.json')
        with open(first_path) as stream:
            first_record = json.load(stream)
        first_request_hash = first_record['requestHash']
        self.assertEqual({}, first_record['policy']['ksm'])
        self.assertEqual('122', first_record['readback']['ksmReadback']['configRevision'])

        second_clear = {'hostUuid': 'host-1', 'operationUuid': 'managed-clear-second-request',
                        'expectedRevision': 122, 'desiredRevision': 123,
                        'licensePermit': {'managed': True, 'operationUuid': 'permit-123',
                            'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                        'policy': {'ksm': {}, 'zram': {'enabled': False},
                                   'writeback': {'enabled': False}}}
        second_result = plugin.apply(second_clear)
        self.assertTrue(second_result['success'],
                        'complete current proof from the prior empty-KSM clear may advance one revision')
        self.assertEqual('Succeeded', second_result['status'])
        self.assertEqual('123', plugin._read_ksm_ack()['configRevision'])
        with open(os.path.join(root, second_clear['operationUuid'] + '.json')) as stream:
            second_record = json.load(stream)
        self.assertEqual('123', second_record['readback']['ksmReadback']['configRevision'])
        with open(first_path) as stream:
            replayed_first = json.load(stream)
        self.assertEqual(first_request_hash, replayed_first['requestHash'],
                         'advancing the second clear must not mutate the first request identity')
    def test_global_and_cluster_managed_journals_can_clear_but_vm_scope_cannot(self):
        cases = (('Global', 'global', True), ('Cluster', 'cluster-1', True),
                 ('VM', 'vm-1', False))
        for index, (scope, resource_uuid, should_succeed) in enumerate(cases):
            with self.subTest(scope=scope, resourceUuid=resource_uuid):
                root = tempfile.mkdtemp(prefix='managed-clear-scope-%s-' % scope.lower())
                prior_scope = 'Host' if scope == 'VM' else scope
                prior_resource = 'host-1' if scope == 'VM' else resource_uuid
                plugin, initial, _, _, _ = self._managed_clear_fixture(
                    root, revision=141 + index * 2, enabled=False, scope=prior_scope,
                    resource_uuid=prior_resource)
                if scope == 'VM':
                    prior_path = os.path.join(root, initial['operationUuid'] + '.json')
                    with open(prior_path) as stream:
                        prior_record = json.load(stream)
                    prior_record['scope'] = 'VM'
                    prior_record['resourceUuid'] = resource_uuid
                    with open(prior_path, 'w') as stream:
                        json.dump(prior_record, stream)
                clear = self._clear_managed_policy(initial,
                    'managed-clear-scope-' + scope.lower())
                if scope == 'VM':
                    clear['scope'] = 'Host'
                result = plugin.apply(clear)
                if should_succeed:
                    self.assertTrue(result['success'],
                        '%s scope journal from the real manager should prove host-owned KSM' % scope)
                    self.assertEqual('Succeeded', result['status'])
                    self.assertEqual(str(initial['desiredRevision'] + 1),
                                     plugin._read_ksm_ack()['configRevision'])
                else:
                    self.assertFalse(result.get('success'),
                        'VM-scoped journal must not be accepted as host KSM ownership proof')
                    self.assertEqual(str(initial['desiredRevision']),
                                     plugin._read_ksm_ack()['configRevision'])
    def test_clear_does_not_treat_missing_current_boot_id_as_same_boot_proof(self):
        for index, missing_boot in enumerate((None, '')):
            with self.subTest(current_boot_id=missing_boot):
                root = tempfile.mkdtemp(prefix='managed-marker-clear-no-boot-id-')
                plugin, initial, _, _, prior_path = self._managed_clear_fixture(
                    root, revision=131 + index, enabled=False)
                with open(prior_path) as stream:
                    prior = json.load(stream)
                prior['bootId'] = missing_boot
                with open(prior_path, 'w') as stream:
                    json.dump(prior, stream)

                cleared = self._clear_managed_policy(initial,
                    'managed-clear-no-boot-id-%s' % index)
                with patch.object(plugin, '_current_boot_id', return_value=missing_boot):
                    result = plugin.apply(cleared)
                with open(os.path.join(root, cleared['operationUuid'] + '.json')) as stream:
                    record = json.load(stream)
                self.assertFalse(result.get('success'),
                    'an absent/blank boot ID is not current-boot evidence')
                self.assertNotEqual('Succeeded', result.get('status'))
                self.assertNotEqual('APPLIED', record.get('stage'))
                self.assertEqual(str(initial['desiredRevision']),
                                 plugin._read_ksm_ack()['configRevision'])
    def test_empty_clear_promotion_rejects_missing_or_invalid_zero_page_readback(self):
        for mutation, value in (('missing', None), ('invalid', 'not-a-bit')):
            with self.subTest(use_zero_pages=mutation):
                root = tempfile.mkdtemp(prefix='clear-zero-readback-%s-' % mutation)
                plugin, initial, _, _, _ = self._managed_clear_fixture(
                    root, 111 if mutation == 'missing' else 112, enabled=False)
                cleared = self._clear_managed_policy(initial, 'clear-zero-proof-' + mutation)
                result = plugin.apply(cleared)
                self.assertTrue(result['success'])

                def unavailable_service(action, payload):
                    raise OSError(errno.ENOENT, 'isolated fixture has no Go service socket')
                plugin.service_call = unavailable_service
                native = plugin._test_native_ksm_simulator
                if value is None:
                    native.sysfs.pop('use_zero_pages', None)
                else:
                    native.sysfs['use_zero_pages'] = value
                observed = json.loads(plugin.state({'body': json.dumps({
                    'hostUuid': 'host-1', 'operationUuid': 'clear-zero-observe-' + mutation})}))
                self.assertEqual('Unknown', observed['status'])
                self.assertFalse(observed['state']['safeToRemove'])
    def test_vm_unknown_reconcile_does_not_read_host_or_replace_owner(self):
        root = tempfile.mkdtemp(prefix='vm-reconcile-')
        calls = []
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
                                          calls.append(action) or
                                          {'mode': 'deny', 'instance_generation': 'other'})
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root})
        command = {'hostUuid': 'host-1', 'scope': 'vm',
                   'resourceUuid': 'vm-1', 'expectedInstanceGeneration': 'gen-1',
                   'participation': 'deny', 'operationUuid': 'vm-unknown',
                   'desiredRevision': 1, 'policy': {'participation': 'deny'}}
        plugin._record_operation(command, 'PREPARING')
        plugin._set_active_control('host-owner')
        result = json.loads(plugin.reconcile({'body': json.dumps({
            'hostUuid': 'host-1', 'operationUuid': 'vm-unknown'})}))
        self.assertEqual('Unknown', result['status'])
        self.assertEqual(['vm-policy-state'], calls)
        self.assertEqual('host-owner', plugin._get_active_control())
    def test_applied_journal_from_previous_boot_is_not_success(self):
        root = tempfile.mkdtemp(prefix='boot-reconcile-')
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: self.fail('must not call service'))
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root})
        command = {'hostUuid': 'host-1', 'operationUuid': 'old-boot',
                   'desiredRevision': 3, 'policy': {'ksm': {'enabled': True}}}
        plugin._record_operation(command, 'APPLIED', {'success': True, 'status': 'Succeeded'})
        path = os.path.join(root, 'old-boot.json')
        with open(path) as stream:
            record = json.load(stream)
        record['bootId'] = 'different-boot'
        with open(path, 'w') as stream:
            json.dump(record, stream)
        result = json.loads(plugin.reconcile({'body': json.dumps({
            'hostUuid': 'host-1', 'operationUuid': 'old-boot'})}))
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('OPERATION_BOOT_CHANGED', result['reasonCode'])
    def test_zram_configuration_does_not_dispatch_product_lease(self):
        """ZRAM config is executed by the Agent without a license lease RPC."""
        root = tempfile.mkdtemp(prefix='zram-no-lease-')
        calls = []

        def service_call(action, payload):
            calls.append(action)
            return {'status': 'Succeeded'}

        plugin = MemoryOptimizationPlugin(service_call=service_call)
        plugin.configure({'hostUuid': 'host-1234567890', 'operationDir': root})
        # This test covers a previously authorized standard install.  Fresh
        # observe-mode bootstrap is exercised by _first_use_fixture above.
        config_directory = os.path.join(root, 'zram-config')
        os.makedirs(config_directory)
        plugin.zram_config_path = os.path.join(config_directory, 'config.json')
        plugin.zram_config_template_path = os.path.join(config_directory, 'vendor-config.json')
        vendor_template = {'version': 2, 'mode': 'observe', 'managed': True,
                           'resource_authorized': False,
                           'initial_efficiency_enabled': False}
        template_bytes = json.dumps(vendor_template, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        with open(plugin.zram_config_path, 'wb') as stream:
            stream.write(template_bytes)
        with open(plugin.zram_config_template_path, 'wb') as stream:
            stream.write(template_bytes)
        command = {
            'action': 'apply', 'scope': 'host',
            'hostUuid': 'host-1234567890',
            'operationUuid': 'zram-config-no-lease',
            'expectedRevision': 8, 'desiredRevision': 9,
            'policy': {'zram': {'enabled': True,
                                'logicalCapacityBytes': 8 * 1024 * 1024,
                                'ramLimitBytes': 4 * 1024 * 1024},
                       'writeback': {'enabled': False}}}
        # Model the one-time standard first-enable transition: the installed
        # vendor template remains observe while the current config becomes
        # authorized reclaim. The new revision below must use the ordinary
        # policy path without changing either file or restarting the service.
        plugin._write_first_use_config(command)
        with patch.object(plugin, 'discover_capabilities', return_value={
                'supported': True, 'ksm': True, 'ksmZeroPages': True,
                'zram': True, 'writeback': True}), \
                patch.object(plugin, '_apply_ksm_policy', return_value={}), \
                patch.object(plugin, '_bounded_controller_restart',
                             side_effect=AssertionError('authorized policy must not restart controller')), \
                patch.object(plugin, '_apply_service_policy', return_value={
                    'status': 'Succeeded'}) as apply_service:
            current_before = open(plugin.zram_config_path, 'rb').read()
            template_before = open(plugin.zram_config_template_path, 'rb').read()
            result = plugin.apply(command)
        self.assertTrue(result['success'], result)
        self.assertEqual('Succeeded', result['status'])
        self.assertNotIn('lease', calls)
        apply_service.assert_called_once_with(command)
        self.assertEqual(current_before, open(plugin.zram_config_path, 'rb').read())
        self.assertEqual(template_before, open(plugin.zram_config_template_path, 'rb').read())
    def test_service_cpu_apply_preserves_native_thresholds_when_only_enabling_zram(self):
        """Enabling ZRAM alone must not reset an existing CPU idle rule."""
        calls = []
        cpu_state = {'revision': 9, 'efficiency_enabled': False,
                     'idle_cpu_threshold_percent': 80, 'idle_duration_seconds': 60}
        tuning_state = {'revision': 11, 'settings': {
            'required_available_bytes': 0, 'host_floor_bytes': 0,
            'metadata_reserve_bytes': 0, 'transient_reserve_bytes': 0,
            'writeback': {'enabled': False,
                          'batch_bytes': 64 * 1024 * 1024,
                          'idle_observation_seconds': 10,
                          'operation_interval_seconds': 2}}}

        def service_call(action, payload):
            calls.append((action, payload))
            if action == 'host-cpu-state':
                return dict(cpu_state, _http_status=200)
            if action == 'tuning-state':
                return dict(tuning_state, _http_status=200)
            if action == 'host-cpu':
                cpu_state.update({'revision': cpu_state['revision'] + 1,
                                  'efficiency_enabled': payload['efficiency_enabled'],
                                  'idle_cpu_threshold_percent': payload['idle_cpu_threshold_percent'],
                                  'idle_duration_seconds': payload['idle_duration_seconds']})
                return dict(cpu_state, request_id=payload['request_id'], _http_status=200)
            if action == 'apply':
                tuning_state.update({'revision': tuning_state['revision'] + 1,
                                     'settings': payload['settings']})
                return dict(tuning_state, _http_status=200)
            return {'status': 'Succeeded'}

        plugin = MemoryOptimizationPlugin(service_call=service_call)
        result = plugin._apply_service_policy({
            'operationUuid': 'cpu-preserve-enable-only',
            'policy': {'zram': {'enabled': True},
                       'writeback': {'enabled': False}}})
        self.assertEqual('Succeeded', result['status'])
        cpu = next(payload for action, payload in calls if action == 'host-cpu')
        self.assertTrue(cpu['efficiency_enabled'])
        self.assertEqual(80, cpu['idle_cpu_threshold_percent'])
        self.assertEqual(60, cpu['idle_duration_seconds'])
    def test_vm_binding_journal_failure_returns_unknown_after_native_success(self):
        root = tempfile.mkdtemp(prefix='vm-binding-failure-')
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
                                          {'revision': 0} if action == 'vm-policy-state'
                                          else {'status': 'Succeeded'})
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root})
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_save_vm_binding', side_effect=IOError('disk full')):
            response = json.loads(plugin.vm_efficiency({'body': json.dumps({
                'action': 'bind', 'hostUuid': 'host-1', 'operationUuid': 'bind-fail',
                'resourceUuid': 'vm-1', 'expectedInstanceGeneration': 'gen-1',
                'participation': 'allow',
                'licensePermit': {'managed': True,
                                  'operationUuid': 'managed-host-1',
                                  'validForSeconds': 30,
                                  'expiresAt': int(time.time() * 1000) + 30000}})}))
        self.assertFalse(response['success'])
        self.assertEqual('VM_BINDING_JOURNAL_UNAVAILABLE', response['reasonCode'])
    def test_service_error_is_unknown_not_success(self):
        def timeout(*args, **kwargs):
            raise ServiceTimeout()

        plugin = MemoryOptimizationPlugin(service_call=timeout)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': tempfile.mkdtemp(prefix='memory-ops-')})
        response = plugin.apply({'hostUuid': 'host-1', 'operationUuid': 'op-1',
                                 'licensePermit': {'managed': True,
                                                   'operationUuid': 'managed-host-1',
                                                   'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                                 'policy': {'writeback': {'enabled': True,
                                                          'backendResourceUuid': 'backend-1',
                                                          'backendPlan': {'file_path': '/var/lib/zram-wb',
                                                                           'size_bytes': 1048576,
                                                                           'minimum_filesystem_free_bytes': 1073741824,
                                                                           'exclusive': True}}}})
        self.assertFalse(response['success'])
        self.assertEqual('UNKNOWN', response['state']['phase'])
    @pytest.mark.privileged
    def test_actual_go_cli_accepts_the_python_builder_request_contract(self):
        binary = os.environ.get('ZRAM_EFFICIENCY_TEST_BINARY')
        if not binary or not os.path.isfile(binary):
            self.skipTest('set ZRAM_EFFICIENCY_TEST_BINARY to the current compiled Go CLI')
        request = memory_optimization.build_backend_maintenance_request(
            self._maintenance_inventory(), {
                'requestId': 'go-contract-1',
                'candidateId': 'candidate:' + WRITEBACK_FINGERPRINT,
                'expectedHostBootId': WRITEBACK_BOOT_ID,
                'expectedPoolGeneration': 'none',
                'backendCapacityBytes': WRITEBACK_CAPACITY,
                'resetConfirmed': True,
            })
        temp_root = tempfile.mkdtemp(prefix='memory-go-contract-')
        missing_config = os.path.join(temp_root, 'guaranteed-missing-config.json')
        try:
            command = [binary, '--config', missing_config, '--prepare-backend-maintenance']
            self.assertEqual(0, os.geteuid(),
                             'run the explicit --privileged test group under sudo -n')
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(json.dumps(request).encode('utf-8'), timeout=20)
            output = (stdout + stderr).decode('utf-8', 'replace')
            self.assertNotEqual(0, process.returncode)
            self.assertIn('no such file or directory', output.lower())
            self.assertNotIn('BACKEND_MAINTENANCE_CANDIDATE_ID_REQUIRED', output)
            self.assertNotIn('BACKEND_MAINTENANCE_TARGET_IDENTITY_REQUIRED', output)
        finally:
            try:
                os.rmdir(temp_root)
            except OSError:
                pass
    def test_local_service_budgets_are_configurable_without_vm_count_cap(self):
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'requestBytes': 2048, 'responseBytes': 4096,
                          'communicationSeconds': 30})
        self.assertEqual(2048, plugin.request_bytes)
        self.assertEqual(4096, plugin.response_bytes)
        self.assertEqual(30, plugin.communication_seconds)
        with self.assertRaises(IOError):
            plugin._call_local_service('state', {'large': 'x' * 4096})
        with self.assertRaises(ValueError):
            plugin.configure({'requestBytes': 0})
        with self.assertRaises(ValueError):
            plugin.configure({'responseBytes': 1.5})
    def test_large_vm_policy_is_staged_and_committed_before_tuning(self):
        calls = []

        class Response(object):
            def __init__(self, body):
                self.status, self.body = 200, body
            def read(self, _limit):
                return self.body

        class Connection(object):
            def __init__(self, path, timeout):
                self.path = None
            def request(self, method, path, body=None, headers=None):
                self.path = path
                calls.append((method, path, json.loads(body) if body else None))
            def getresponse(self):
                if self.path == '/v1/vm-management':
                    return Response(json.dumps({'settings': {'revision': 4}}).encode('utf-8'))
                return Response(b'{"status":"Succeeded"}')
            def close(self):
                pass

        plugin = MemoryOptimizationPlugin()
        plugin.configure({'socketPath': '/tmp/memory-service.sock', 'requestBytes': 4096})
        with patch.object(memory_optimization, '_UnixHTTPConnection', Connection):
            result = plugin._call_local_service('apply', {
                'request_id': 'op-1', 'expected_revision': 5,
                '_target_snapshot_generation': 'policy-5',
                'settings': {'vm_management': {
                    'mode': 'list', 'vm_uuids': ['vm-%04d' % i for i in range(600)]}}})
        self.assertEqual(200, result['_http_status'])
        shard_paths = [item[1] for item in calls if '/v1/vm-management/shard/' in item[1]]
        self.assertEqual(4, len(shard_paths))  # three stage chunks and one commit
        self.assertEqual('/v1/zram/tuning', calls[-1][1])
        self.assertEqual([], calls[-1][2]['settings']['vm_management']['vm_uuids'])
    def test_host_policy_quiesces_before_capacity_and_restores_after_exact_vm_readback(self):
        result, calls, plugin, _active_path = self._run_fail_closed_apply_with_vm_shards()
        self.assertTrue(result['success'], result)
        self.assertEqual('Succeeded', result['status'])
        stage = next(i for i, (_method, path, _body) in enumerate(calls)
                     if path.endswith('/shard/stage'))
        commit = next(i for i, (_method, path, _body) in enumerate(calls)
                      if path.endswith('/shard/commit'))
        capacity = next(i for i, (method, path, _body) in enumerate(calls)
                        if method == 'PUT' and path == '/v1/zram/config')
        tuning = max(i for i, (method, path, _body) in enumerate(calls)
                     if method == 'PUT' and path == '/v1/zram/tuning')
        cpu_writes = [(i, body) for i, (method, path, body) in enumerate(calls)
                      if method == 'PUT' and path == '/v1/efficiency/policy']
        self.assertEqual(2, len(cpu_writes))
        self.assertFalse(cpu_writes[0][1]['efficiency_enabled'])
        self.assertTrue(cpu_writes[1][1]['efficiency_enabled'])
        self.assertLess(cpu_writes[0][0], capacity)
        self.assertLess(capacity, stage)
        self.assertLess(stage, commit)
        self.assertLess(commit, tuning)
        self.assertLess(tuning, cpu_writes[1][0])
        self.assertEqual('ffffffffffffffffffffffffffffffff', plugin._get_active_control())
    def test_host_policy_stage_or_commit_failure_never_reenables_cpu_gate(self):
        for failure, expected in (('stage', 'VM_SHARD_STAGE_FAILED'),
                                  ('commit', 'VM_SHARD_COMMIT_FAILED'),
                                  ('commit_lost', 'MEMORY_RESULT_UNKNOWN')):
            with self.subTest(failure=failure):
                result, calls, plugin, active_path = self._run_fail_closed_apply_with_vm_shards(failure)
                self.assertFalse(result['success'], result)
                self.assertEqual('Unknown', result['status'])
                self.assertEqual(expected, result['reasonCode'])
                cpu_writes = [body for method, path, body in calls
                              if method == 'PUT' and path == '/v1/efficiency/policy']
                self.assertEqual(1, len(cpu_writes), calls)
                self.assertFalse(cpu_writes[0]['efficiency_enabled'])
                self.assertFalse(any(method == 'PUT' and path == '/v1/zram/tuning'
                                     for method, path, _body in calls))
                self.assertEqual('prior-control', plugin._get_active_control())
                with open(active_path, 'r') as stream:
                    self.assertEqual('prior-control', stream.read())

"""Memory optimization maintenance behavior tests.

Migrated from the legacy Agent test module; all methods remain discovered by pytest.
"""

from tests.unit.kvmagent.memory_optimization_test_support import *
from tests.unit.kvmagent.memory_optimization_test_support import _OMIT_POLICY_MODE
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.kvmagent]

class TestMemoryOptimizationMaintenance(MemoryOptimizationTestBase):
    def test_backend_maintenance_exit_error_accepts_only_safe_codes(self):
        plugin = MemoryOptimizationPlugin()
        path = tempfile.mktemp(prefix='memory-maintenance-stderr-')
        try:
            with open(path, 'w') as stream:
                json.dump({'error': 'BACKEND_MAINTENANCE_TARGET_NOT_EXCLUSIVE: BACKEND_ALREADY_ATTACHED'}, stream)
            self.assertEqual(('BACKEND_MAINTENANCE_TARGET_NOT_EXCLUSIVE', 'BACKEND_ALREADY_ATTACHED'),
                             plugin._backend_maintenance_exit_error(path))
            with open(path, 'w') as stream:
                json.dump({'error': 'arbitrary secret/path'}, stream)
            self.assertEqual(('BACKEND_MAINTENANCE_EXECUTOR_FAILED', None),
                             plugin._backend_maintenance_exit_error(path))
            os.unlink(path)
            self.assertEqual(('BACKEND_MAINTENANCE_EXECUTOR_FAILED', None),
                             plugin._backend_maintenance_exit_error(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)
    def test_backend_maintenance_request_checks_host_boot_and_pool_generation(self):
        plugin = MemoryOptimizationPlugin()
        command = {
            'action': 'prepareWritebackBackend', 'scope': 'Host',
            'hostUuid': 'host-1', 'operationUuid': 'maintenance-1',
            'backendPreparation': {
                'candidateId': 'candidate:' + WRITEBACK_FINGERPRINT,
                'expectedHostBootId': WRITEBACK_BOOT_ID,
                'expectedPoolGeneration': 'none',
                'backendCapacityBytes': WRITEBACK_CAPACITY,
                'resetConfirmed': True,
            },
        }
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID):
            request = plugin._backend_preparation_request(command, self._maintenance_inventory())
            self.assertEqual('maintenance-1', request['request_id'])
            self.assertEqual(WRITEBACK_DEVICE, request['backend']['device'])

            bad_inventory = self._maintenance_inventory(hostUuid='host-2')
            with self.assertRaisesRegex(ValueError, 'BACKEND_RESOURCE_HOST_MISMATCH'):
                plugin._backend_preparation_request(command, bad_inventory)

            bad_boot = dict(command)
            bad_boot['backendPreparation'] = dict(command['backendPreparation'])
            bad_boot['backendPreparation']['expectedHostBootId'] = 'stale-boot'
            with self.assertRaisesRegex(ValueError, 'BACKEND_MAINTENANCE_BOOT_ID_MISMATCH'):
                plugin._backend_preparation_request(bad_boot, self._maintenance_inventory())

            bad_generation = dict(command)
            bad_generation['backendPreparation'] = dict(command['backendPreparation'])
            bad_generation['backendPreparation']['expectedPoolGeneration'] = 'f' * 64
            with self.assertRaisesRegex(ValueError, 'BACKEND_MAINTENANCE_POOL_GENERATION_MISMATCH'):
                plugin._backend_preparation_request(bad_generation, self._maintenance_inventory())
    def test_backend_maintenance_rejects_unconfirmed_bad_capacity_and_candidate(self):
        plugin = MemoryOptimizationPlugin()
        command = {
            'action': 'prepareWritebackBackend', 'scope': 'Host',
            'hostUuid': 'host-1', 'operationUuid': 'maintenance-2',
            'backendPreparation': {
                'candidateId': 'candidate:' + WRITEBACK_FINGERPRINT,
                'expectedHostBootId': WRITEBACK_BOOT_ID,
                'expectedPoolGeneration': 'none',
                'backendCapacityBytes': WRITEBACK_CAPACITY,
                'resetConfirmed': True,
            },
        }
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID):
            for field, value, reason in (
                    ('resetConfirmed', False, 'BACKEND_MAINTENANCE_CONFIRMATION_REQUIRED'),
                    ('backendCapacityBytes', WRITEBACK_CAPACITY - 1,
                     'BACKEND_MAINTENANCE_CAPACITY_REQUIRED'),
                    ('candidateId', 'candidate:' + 'c' * 64,
                     'WRITEBACK_CANDIDATE_NOT_UNIQUE')):
                bad = dict(command)
                bad['backendPreparation'] = dict(command['backendPreparation'])
                bad['backendPreparation'][field] = value
                with self.assertRaisesRegex(ValueError, reason):
                    plugin._backend_preparation_request(bad, self._maintenance_inventory())

            bad = dict(command)
            bad['backendPreparation'] = dict(command['backendPreparation'])
            bad['backendPreparation']['extra'] = 'not-allowed'
            with self.assertRaisesRegex(ValueError, 'MEMORY_BACKEND_PREPARATION_INVALID'):
                plugin._backend_preparation_request(bad, self._maintenance_inventory())
    def test_backend_maintenance_apply_does_not_relaunch_same_nonce(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-replay-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        command = {
            'action': 'prepareWritebackBackend', 'scope': 'Host',
            'hostUuid': 'host-1', 'operationUuid': 'maintenance-replay-1',
            'backendPreparation': {
                'candidateId': 'candidate:' + WRITEBACK_FINGERPRINT,
                'expectedHostBootId': WRITEBACK_BOOT_ID,
                'expectedPoolGeneration': 'none',
                'backendCapacityBytes': WRITEBACK_CAPACITY,
                'resetConfirmed': True,
            },
        }
        journal_command = dict(command)
        journal_command['maintenanceIntentPath'] = os.path.join(
            operation_dir, 'backend-maintenance', 'maintenance-replay-1.intent.json')
        expected = {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'BACKEND_MAINTENANCE_EXECUTOR_UNKNOWN',
                    'operationUuid': 'maintenance-replay-1'}
        self.assertTrue(plugin._record_operation(journal_command, 'UNKNOWN', expected))
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(subprocess, 'check_call') as launch, \
                patch.object(plugin, '_acquire_host_control_lock') as acquire:
            result = plugin._prepare_backend_maintenance(command)
        self.assertEqual(expected, result)
        launch.assert_not_called()
        acquire.assert_not_called()
    def test_zram_pool_eligibility_reads_canonical_persisted_host_policy(self):
        # Exercise the real eligibility reader against the Go policy-store
        # JSON shape; mocking eligibility itself hides cross-language ABI drift.
        plugin = MemoryOptimizationPlugin()
        state_dir = tempfile.mkdtemp(prefix='memory-cold-pool-policy-')
        self.addCleanup(shutil.rmtree, state_dir)
        os.mkdir(os.path.join(state_dir, 'policies'))
        policy_path = os.path.join(state_dir, 'policies', 'policies.json')
        ksm_path = os.path.join(state_dir, 'ksm-run')
        with open(ksm_path, 'w') as stream:
            stream.write('0\n')
        real_open = open

        def read_native_or_policy(path, *args, **kwargs):
            if path == '/sys/kernel/mm/ksm/run':
                path = ksm_path
            return real_open(path, *args, **kwargs)

        cases = [
            ({'efficiency_enabled': False, 'revision': 44,
              'last_request_id': 'completed-drain-disable'}, True),
            ({'enabled': False}, False),
            ({}, False),
            ({'efficiency_enabled': None}, False),
            ({'efficiency_enabled': 0}, False),
            ({'efficiency_enabled': 'false'}, False),
            ({'efficiency_enabled': True, 'enabled': False}, False),
        ]
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                patch.object(plugin, '_get_active_control', return_value='drain-anchor-1'), \
                patch.object(plugin, '_drained_pool_generation', return_value='a' * 64), \
                patch.object(plugin, '_maintenance_service_state', return_value='inactive'), \
                patch.object(plugin, '_has_unresolved_operation_journal', return_value=False), \
                patch.object(plugin, '_read_maintenance_config', return_value=(
                    {'initial_efficiency_enabled': False}, state_dir, '/dev/zram0')), \
                patch.object(plugin, '_read_backend_maintenance_receipt', return_value=(None, None)), \
                patch.object(plugin, '_read_zram_pool_preparation_receipt', return_value=(None, None)), \
                patch.object(memory_optimization, 'open', side_effect=read_native_or_policy, create=True):
            for host_policy, expected in cases:
                with self.subTest(host_policy=host_policy):
                    with real_open(policy_path, 'w') as stream:
                        json.dump({'host': host_policy, 'vms': {}}, stream)
                    result = plugin._zram_pool_preparation_eligibility('host-1', 'drain-anchor-1')
                    self.assertEqual(expected, result['canPrepareZramPool'], result)
                    self.assertEqual([] if expected else ['HOST_MEMORY_OPTIMIZATION_NOT_DISABLED'],
                                     result['zramPoolPreparationReasons'])
    def test_zram_pool_eligibility_overlay_preserves_writeback_identity(self):
        plugin = MemoryOptimizationPlugin()
        command = {'hostUuid': 'host-1'}
        base = {'bootId': 'boot-current', 'poolGeneration': 'f' * 64,
                'controlOperationUuid': 'writeback-control', 'candidates': []}
        cases = [
            # Normal host without a completed drain: cold snapshot is unknown,
            # but must not erase the live writeback pool identity.
            (dict(base), {'bootId': 'boot-current', 'poolGeneration': None,
                          'controlOperationUuid': None, 'canPrepareZramPool': False,
                          'zramPoolPreparationReasons': ['DRAIN_PROOF_UNKNOWN'],
                          'zramPoolPreparationQuality': 'Unknown',
                          'zramPoolPreparationObservedAt': 123}, False),
            # First-use's explicit none remains a writeback inventory value;
            # cold pool prep is still forbidden (this feature is drained-pool only).
            ({'bootId': 'boot-current', 'poolGeneration': 'none',
              'controlOperationUuid': None, 'candidates': []},
             {'bootId': 'boot-current', 'poolGeneration': 'none',
              'controlOperationUuid': None, 'canPrepareZramPool': False,
              'zramPoolPreparationReasons': ['FIRST_USE_NOT_SUPPORTED'],
              'zramPoolPreparationQuality': 'Ineligible',
              'zramPoolPreparationObservedAt': 456}, False),
            # Even when a cold snapshot says eligible, disagreement with the
            # independently sourced writeback identity must fail closed.
            (dict(base), {'bootId': 'boot-current', 'poolGeneration': 'a' * 64,
                          'controlOperationUuid': 'drain-anchor', 'canPrepareZramPool': True,
                          'zramPoolPreparationReasons': [],
                          'zramPoolPreparationQuality': 'Fresh',
                          'zramPoolPreparationObservedAt': 789}, False),
        ]
        for original, snapshot, expected in cases:
            with self.subTest(snapshot=snapshot), \
                    patch.object(plugin, '_zram_pool_preparation_eligibility', return_value=snapshot):
                inventory = dict(original)
                result = plugin._decorate_zram_pool_preparation_inventory(inventory, command)
                self.assertIs(result, inventory)
                for key in ('bootId', 'poolGeneration', 'controlOperationUuid'):
                    self.assertEqual(original.get(key), result.get(key), key)
                self.assertEqual(expected, result['canPrepareZramPool'])
    def test_zram_pool_preparation_launches_once_and_reconcile_only_observes_worker(self):
        operation_dir = tempfile.mkdtemp(prefix='zram-pool-prepare-')
        self.addCleanup(lambda: __import__('shutil').rmtree(operation_dir, ignore_errors=True))
        binary = os.path.join(operation_dir, 'zram-efficiency')
        config = os.path.join(operation_dir, 'config.json')
        open(binary, 'w').close(); open(config, 'w').close()
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'drainBinary': binary, 'drainConfig': config})
        boot_id = plugin._current_boot_id()
        command = {'action': 'prepareZramPool', 'scope': 'Host', 'hostUuid': 'host-1',
                   'operationUuid': 'pool-prepare-launch-1', 'policy': {},
                   'expectedControlOperationUuid': 'drain-anchor-1',
                   'poolPreparation': {'expectedHostBootId': boot_id,
                                       'expectedPoolGeneration': 'b' * 64,
                                       'resetConfirmed': True}}
        snapshot = {'hostUuid': 'host-1', 'bootId': boot_id,
                    'poolGeneration': 'b' * 64, 'controlOperationUuid': 'drain-anchor-1',
                    'canPrepareZramPool': True, 'zramPoolPreparationReasons': []}
        # Pool preparation uses the explicit stopped-unit check, distinct from
        # maintenance worker's managed-service state readback.
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=boot_id), \
                patch.object(plugin, '_service_unit_stopped', return_value=True), \
                patch.object(plugin, '_zram_pool_preparation_eligibility', return_value=snapshot), \
                patch.object(subprocess, 'check_call') as launch:
            first = plugin._prepare_zram_pool(command)
            replay = plugin._prepare_zram_pool(command)
            self.assertEqual('Draining', first['status'])
            self.assertEqual(first, replay)
            self.assertEqual(1, launch.call_count)
            self.assertIn('--prepare-zram-pool', launch.call_args[0][0])
            prior = plugin._load_operation({'operationUuid': command['operationUuid']})
            with patch.object(plugin, '_systemd_worker_exit', return_value=('running', None)), \
                    patch.object(plugin, '_read_zram_pool_preparation_receipt') as readback:
                pending = plugin._reconcile_zram_pool({'operationUuid': command['operationUuid']}, prior)
                self.assertEqual('Draining', pending['status'], pending)
                self.assertEqual('EXECUTOR_RUNNING', pending['state']['phase'])
                readback.assert_not_called()
            self.assertEqual(1, launch.call_count)
    def test_zram_pool_continuation_starts_disabled_service_once_then_finalizes(self):
        operation_dir = tempfile.mkdtemp(prefix='zram-pool-continue-')
        self.addCleanup(lambda: __import__('shutil').rmtree(operation_dir, ignore_errors=True))
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        boot_id = plugin._current_boot_id()
        command = {'action': 'prepareZramPool', 'scope': 'Host', 'hostUuid': 'host-1',
                   'operationUuid': 'pool-continue-1', 'policy': {},
                   'expectedControlOperationUuid': 'drain-anchor-1',
                   'poolPreparation': {'expectedHostBootId': boot_id,
                                       'expectedPoolGeneration': 'd' * 64,
                                       'resetConfirmed': True}}
        command['poolMaintenanceIntentPath'] = os.path.join(
            operation_dir, 'zram-pool-maintenance', 'pool-continue-1.intent.json')
        self.assertTrue(plugin._record_operation(command, 'DRAINING',
            plugin._maintenance_result(command, 'Draining', 'EXECUTOR_RUNNING')))
        prior = plugin._load_operation({'operationUuid': command['operationUuid']})
        snapshot = {'hostUuid': 'host-1', 'bootId': boot_id,
                    'poolGeneration': 'd' * 64, 'controlOperationUuid': 'drain-anchor-1',
                    'canPrepareZramPool': True}
        with patch.object(plugin, '_current_boot_id', return_value=boot_id):
            request = plugin._zram_pool_preparation_request(command, snapshot)
        receipt_fields = {'request_id': command['operationUuid'],
                          'request_fingerprint': request['_request_fingerprint'],
                          'expected_control_operation_uuid': 'drain-anchor-1',
                          'host_boot_id': boot_id, 'pool_generation': 'd' * 64}
        awaiting = dict(receipt_fields, stage='AWAITING_SERVICE_READBACK')
        applied = dict(receipt_fields, stage='APPLIED')
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=boot_id), \
                patch.object(plugin, '_read_zram_pool_preparation_receipt',
                             side_effect=[(awaiting, None), (applied, None), (applied, None)]), \
                patch.object(plugin, '_maintenance_service_state', side_effect=['inactive', 'active']), \
                patch.object(plugin, '_read_maintenance_config',
                             return_value=({'initial_efficiency_enabled': False}, operation_dir, '/dev/zram0')), \
                patch.object(plugin, '_host_optimization_disabled', return_value=(True, None)), \
                patch.object(plugin, '_readonly_query', side_effect=[
                    {'host_zram': {'quality': 'unavailable',
                                   'reason': 'NO_QUALIFIED_MANAGED_POOL:prepared'},
                     'maintenance_blocks_activation': True},
                    {'efficiency_enabled': False}]), \
                patch.object(plugin, '_service_request', return_value={'stage': 'APPLIED'}) as service, \
                patch.object(subprocess, 'check_call') as start:
            result = plugin._continue_zram_pool_preparation(command, prior, request, awaiting)
            self.assertEqual('Succeeded', result['status'], result)
            self.assertFalse(result['state']['writebackReady'])
            self.assertEqual(1, start.call_count)
            self.assertEqual(['systemctl', 'start', plugin.MANAGED_ZRAM_UNIT], start.call_args[0][0])
            self.assertEqual('zram-pool-maintenance-finalize', service.call_args[0][0])
            # An APPLIED retry is read-only and cannot restart or enable anything.
            prior = plugin._load_operation({'operationUuid': command['operationUuid']})
            result = plugin._continue_zram_pool_preparation(command, prior, request, applied)
            self.assertEqual('Succeeded', result['status'])
            self.assertEqual(1, start.call_count)
    def test_zram_pool_finalizing_receipt_retries_finalize_without_reset_or_restart(self):
        operation_dir = tempfile.mkdtemp(prefix='zram-pool-finalizing-')
        self.addCleanup(lambda: __import__('shutil').rmtree(operation_dir, ignore_errors=True))
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        boot_id = plugin._current_boot_id()
        command = {'action': 'prepareZramPool', 'scope': 'Host', 'hostUuid': 'host-1',
                   'operationUuid': 'pool-finalizing-1', 'policy': {},
                   'expectedControlOperationUuid': 'drain-anchor-1',
                   'poolPreparation': {'expectedHostBootId': boot_id,
                                       'expectedPoolGeneration': '9' * 64,
                                       'resetConfirmed': True}}
        command['poolMaintenanceIntentPath'] = os.path.join(
            operation_dir, 'zram-pool-maintenance', 'pool-finalizing-1.intent.json')
        plugin._record_operation(command, 'FINALIZE_REQUESTED',
            plugin._maintenance_result(command, 'Draining', 'FINALIZE_REQUESTED'))
        prior = plugin._load_operation({'operationUuid': command['operationUuid']})
        snapshot = {'hostUuid': 'host-1', 'bootId': boot_id,
                    'poolGeneration': '9' * 64, 'controlOperationUuid': 'drain-anchor-1',
                    'canPrepareZramPool': True}
        with patch.object(plugin, '_current_boot_id', return_value=boot_id):
            request = plugin._zram_pool_preparation_request(command, snapshot)
        fields = {'request_id': command['operationUuid'],
                  'request_fingerprint': request['_request_fingerprint'],
                  'expected_control_operation_uuid': 'drain-anchor-1',
                  'host_boot_id': boot_id, 'pool_generation': '9' * 64}
        finalizing = dict(fields, stage='FINALIZING')
        applied = dict(fields, stage='APPLIED')
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=boot_id), \
                patch.object(plugin, '_read_zram_pool_preparation_receipt',
                             side_effect=[(finalizing, None), (applied, None)]), \
                patch.object(plugin, '_maintenance_service_state', return_value='active'), \
                patch.object(plugin, '_host_optimization_disabled', return_value=(True, None)), \
                patch.object(plugin, '_readonly_query', side_effect=[
                    {'host_zram': {'quality': 'unavailable',
                                   'reason': 'NO_QUALIFIED_MANAGED_POOL:prepared'},
                     'maintenance_blocks_activation': True},
                    {'efficiency_enabled': False}]), \
                patch.object(plugin, '_service_request', return_value={'stage': 'APPLIED'}) as finalize, \
                patch.object(subprocess, 'check_call') as start:
            result = plugin._continue_zram_pool_preparation(command, prior, request, finalizing)
        self.assertEqual('Succeeded', result['status'], result)
        finalize.assert_called_once_with('zram-pool-maintenance-finalize', {'requestId': command['operationUuid']})
        start.assert_not_called()
    def test_backend_maintenance_reconcile_keeps_live_worker_pending_readonly(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-reconcile-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-live-1'
        boot_id = WRITEBACK_BOOT_ID
        directory, paths = plugin._maintenance_intent_paths(operation_uuid)
        target = {'boot_id': boot_id, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'b' * 64}
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': boot_id, 'expected_pool_generation': 'none',
                   'backend_capacity_bytes': WRITEBACK_CAPACITY, 'target_identity': target,
                   'reset_confirmed': True}
        receipt_value = {'request_id': operation_uuid, 'candidate_id': request['candidate_id'],
                         'host_boot_id': boot_id, 'target_identity': target,
                         'stage': 'AWAITING_SERVICE_READBACK'}
        with open(paths['requestPath'], 'w') as stream:
            json.dump(request, stream)
        prior = {
            'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
            'hostUuid': 'host-1', 'bootId': boot_id,
            'requestHash': 'a' * 64,
            'maintenanceIntentPath': paths['intentPath'],
        }
        intent = {
            'schema': 1, 'operationUuid': operation_uuid, 'hostUuid': 'host-1',
            'bootId': boot_id, 'requestHash': prior['requestHash'],
            'unit': plugin._maintenance_systemd_unit(operation_uuid),
            'requestPath': paths['requestPath'], 'receiptPath': paths['receiptPath'],
            'stderrPath': paths['stderrPath'], 'configPath': plugin.drain_config,
            'workerLaunchAttempted': True,
        }
        with open(paths['intentPath'], 'w') as stream:
            json.dump(intent, stream)
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=boot_id), \
                patch.object(plugin, '_systemd_worker_exit', return_value=('running', None)), \
                patch.object(plugin, '_read_backend_maintenance_receipt') as receipt:
            result = plugin._reconcile_backend_maintenance(
                {'operationUuid': operation_uuid}, prior)
        self.assertEqual('Draining', result['status'])
        self.assertEqual('EXECUTOR_RUNNING', result['state']['phase'])
        self.assertFalse(result['state']['writebackReady'])
        receipt.assert_not_called()
    def test_backend_maintenance_receipt_matches_go_block_identity_default(self):
        # Captured Go BackendFingerprint serialization includes direct_io=false;
        # requests persisted by the previous Agent omit this bool zero value.
        target = {'boot_id': WRITEBACK_BOOT_ID, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'b' * 64}
        request = {'request_id': 'maintenance-compat-1',
                   'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': WRITEBACK_BOOT_ID,
                   'expected_pool_generation': 'a' * 64, 'target_identity': target}
        receipt = {'request_id': request['request_id'], 'candidate_id': request['candidate_id'],
                   'host_boot_id': WRITEBACK_BOOT_ID, 'pool_generation': 'a' * 64,
                   'target_identity': dict(target, direct_io=False),
                   'stage': 'AWAITING_SERVICE_READBACK'}
        matches = MemoryOptimizationPlugin._maintenance_receipt_matches_request
        self.assertTrue(matches(receipt, request, WRITEBACK_BOOT_ID))
        self.assertNotIn('direct_io', request['target_identity'])
        for invalid in (True, None, 0, 'false'):
            changed = dict(receipt, target_identity=dict(target, direct_io=invalid))
            self.assertFalse(matches(changed, request, WRITEBACK_BOOT_ID), repr(invalid))
        for key in target:
            changed = dict(receipt, target_identity=dict(receipt['target_identity']))
            changed['target_identity'][key] = 'changed'
            self.assertFalse(matches(changed, request, WRITEBACK_BOOT_ID), key)
        changed = dict(receipt, target_identity=dict(receipt['target_identity'], unknown_field=False))
        self.assertFalse(matches(changed, request, WRITEBACK_BOOT_ID))
        for key in ('request_id', 'candidate_id', 'host_boot_id', 'pool_generation'):
            changed = dict(receipt)
            changed[key] = 'changed'
            self.assertFalse(matches(changed, request, WRITEBACK_BOOT_ID), key)
    def test_backend_maintenance_reconcile_after_worker_exit_only_reads_receipt(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-readback-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-readback-1'
        boot_id = WRITEBACK_BOOT_ID
        _, paths = plugin._maintenance_intent_paths(operation_uuid)
        target = {'boot_id': boot_id, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'b' * 64}
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': boot_id, 'expected_pool_generation': 'none',
                   'backend_capacity_bytes': WRITEBACK_CAPACITY, 'target_identity': target,
                   'reset_confirmed': True}
        receipt_value = {'request_id': operation_uuid, 'candidate_id': request['candidate_id'],
                         'host_boot_id': boot_id, 'target_identity': dict(target, direct_io=False),
                         'stage': 'AWAITING_SERVICE_READBACK'}
        with open(paths['requestPath'], 'w') as stream:
            json.dump(request, stream)
        prior = {
            'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
            'hostUuid': 'host-1', 'bootId': boot_id,
            'requestHash': 'b' * 64, 'maintenanceIntentPath': paths['intentPath'],
        }
        with open(paths['intentPath'], 'w') as stream:
            json.dump({
                'operationUuid': operation_uuid, 'hostUuid': 'host-1', 'bootId': boot_id,
                'requestHash': prior['requestHash'],
                'unit': plugin._maintenance_systemd_unit(operation_uuid),
                'requestPath': paths['requestPath'], 'receiptPath': paths['receiptPath'],
                'stderrPath': paths['stderrPath'], 'configPath': plugin.drain_config,
                'workerLaunchAttempted': True,
            }, stream)
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=boot_id), \
                patch.object(plugin, '_systemd_worker_exit', return_value=('exited', 0)), \
                patch.object(plugin, '_read_backend_maintenance_receipt',
                             return_value=(receipt_value, None)), \
                patch.object(plugin, '_continue_backend_maintenance', return_value={
                    'success': True, 'status': 'Draining',
                    'state': {'phase': 'SERVICE_STARTING'}}) as continuation, \
                patch.object(subprocess, 'check_call') as launch:
            result = plugin._reconcile_backend_maintenance(
                {'operationUuid': operation_uuid}, prior)
        self.assertEqual('Draining', result['status'])
        self.assertEqual('SERVICE_STARTING', result['state']['phase'])
        continuation.assert_called_once()
        launch.assert_not_called()
    def test_backend_maintenance_failed_worker_is_review_required_without_replay(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-failed-worker-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-failed-1'
        boot_id = WRITEBACK_BOOT_ID
        _, paths = plugin._maintenance_intent_paths(operation_uuid)
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': boot_id, 'expected_pool_generation': 'none',
                   'backend_capacity_bytes': WRITEBACK_CAPACITY,
                   'target_identity': {'boot_id': boot_id, 'canonical_device': WRITEBACK_DEVICE,
                       'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                       'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'b' * 64},
                   'reset_confirmed': True}
        with open(paths['requestPath'], 'w') as stream:
            json.dump(request, stream)
        prior = {'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
                 'hostUuid': 'host-1', 'bootId': boot_id, 'requestHash': 'c' * 64,
                 'maintenanceIntentPath': paths['intentPath']}
        with open(paths['intentPath'], 'w') as stream:
            json.dump({'operationUuid': operation_uuid, 'hostUuid': 'host-1', 'bootId': boot_id,
                       'requestHash': prior['requestHash'],
                       'unit': plugin._maintenance_systemd_unit(operation_uuid),
                       'requestPath': paths['requestPath'], 'receiptPath': paths['receiptPath'],
                       'stderrPath': paths['stderrPath'], 'configPath': plugin.drain_config,
                       'workerLaunchAttempted': True}, stream)
        with open(paths['stderrPath'], 'w') as stream:
            json.dump({'error': 'BACKEND_MAINTENANCE_TARGET_NOT_EXCLUSIVE: BACKEND_ALREADY_ATTACHED'}, stream)
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=boot_id), \
                patch.object(plugin, '_systemd_worker_exit', return_value=('exited', 1)), \
                patch.object(plugin, '_continue_backend_maintenance') as continuation, \
                patch.object(plugin, '_update_operation_record') as update:
            result = plugin._reconcile_backend_maintenance({'operationUuid': operation_uuid}, prior)
        self.assertEqual('Failed', result['status'])
        self.assertEqual('FAILED_REQUIRES_REVIEW', result['state']['phase'])
        self.assertEqual('BACKEND_MAINTENANCE_TARGET_NOT_EXCLUSIVE', result['reasonCode'])
        self.assertEqual('BACKEND_ALREADY_ATTACHED', result['failureDetail'])
        update.assert_called_once_with(operation_uuid, 'FAILED_REQUIRES_REVIEW', result)
        continuation.assert_not_called()
    def test_backend_maintenance_continuation_starts_once_verifies_and_finalizes(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-finalize-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-finalize-1'
        target = {'boot_id': WRITEBACK_BOOT_ID, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'c' * 64}
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': WRITEBACK_BOOT_ID,
                   'expected_pool_generation': 'none',
                   'backend_capacity_bytes': WRITEBACK_CAPACITY,
                   'target_identity': target}
        pending_receipt = {'request_id': operation_uuid, 'candidate_id': request['candidate_id'],
                           'host_boot_id': WRITEBACK_BOOT_ID, 'target_identity': target,
                           'stage': 'AWAITING_SERVICE_READBACK',
                           'backend_resource_uuid': 'd' * 32}
        applied_receipt = dict(pending_receipt, stage='APPLIED')
        prior = {'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
                 'maintenanceProgress': {}, 'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
                 'requestHash': 'f' * 64,
                 'maintenanceIntentPath': os.path.join(operation_dir, 'backend-maintenance',
                                                       operation_uuid + '.intent.json')}
        journal = dict(prior)
        command = {'operationUuid': operation_uuid}
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_maintenance_service_state', side_effect=['inactive', 'active']), \
                patch.object(plugin, '_read_maintenance_config', return_value=({}, operation_dir, '/dev/zram0')), \
                patch.object(subprocess, 'check_call') as start, \
                patch.object(plugin, '_verify_maintenance_service_readback', return_value=(True, None)), \
                patch.object(plugin, '_read_backend_maintenance_receipt',
                             side_effect=[(pending_receipt, None), (applied_receipt, None)]), \
                patch.object(plugin, '_load_operation', return_value=journal), \
                patch.object(plugin, '_service_request', return_value=applied_receipt) as finalize, \
                patch.object(plugin, '_host_optimization_disabled', return_value=(True, None)), \
                patch.object(plugin, '_persist_maintenance_progress', return_value=True):
            result = plugin._continue_backend_maintenance(command, prior, request, pending_receipt)
        self.assertEqual('Succeeded', result['status'])
        self.assertEqual('APPLIED', result['state']['phase'])
        start.assert_called_once_with(['systemctl', 'start', plugin.MANAGED_ZRAM_UNIT], timeout=30)
        finalize.assert_called_once_with('backend-maintenance-finalize', {'requestId': operation_uuid})
    def test_backend_maintenance_does_not_finalize_when_service_readback_is_not_ready(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-not-ready-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-not-ready-1'
        target = {'boot_id': WRITEBACK_BOOT_ID, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': '9' * 64}
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': WRITEBACK_BOOT_ID,
                   'expected_pool_generation': 'none',
                   'backend_capacity_bytes': WRITEBACK_CAPACITY,
                   'target_identity': target}
        receipt = {'request_id': operation_uuid, 'candidate_id': request['candidate_id'],
                   'host_boot_id': WRITEBACK_BOOT_ID, 'target_identity': target,
                   'stage': 'AWAITING_SERVICE_READBACK'}
        prior = {'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
                 'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
                 'requestHash': 'f' * 64,
                 'maintenanceIntentPath': os.path.join(operation_dir, 'backend-maintenance',
                                                       operation_uuid + '.intent.json'),
                 'maintenanceProgress': {}}
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_load_operation', return_value=prior), \
                patch.object(plugin, '_maintenance_service_state', return_value='active'), \
                patch.object(plugin, '_read_backend_maintenance_receipt', return_value=(receipt, None)), \
                patch.object(plugin, '_verify_maintenance_service_readback',
                             return_value=(False, 'HOST_MEMORY_OPTIMIZATION_NOT_DISABLED')), \
                patch.object(plugin, '_persist_maintenance_progress', return_value=True), \
                patch.object(plugin, '_service_request') as finalize:
            result = plugin._continue_backend_maintenance(
                {'operationUuid': operation_uuid}, prior, request, receipt)
        self.assertEqual('Draining', result['status'])
        self.assertEqual('SERVICE_READBACK_PENDING', result['state']['phase'])
        finalize.assert_not_called()
    def test_backend_maintenance_applied_receipt_still_requires_disabled_policy_readback(self):
        operation_uuid = 'maintenance-applied-policy-1'
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-applied-policy-')
        target = {'boot_id': WRITEBACK_BOOT_ID, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'a' * 64}
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': WRITEBACK_BOOT_ID,
                   'expected_pool_generation': 'none', 'target_identity': target}
        receipt = {'request_id': operation_uuid, 'candidate_id': request['candidate_id'],
                   'host_boot_id': WRITEBACK_BOOT_ID, 'target_identity': target, 'stage': 'APPLIED'}
        plugin = MemoryOptimizationPlugin()
        prior = {'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
                 'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
                 'requestHash': 'f' * 64,
                 'maintenanceIntentPath': os.path.join(operation_dir, 'backend-maintenance',
                                                       operation_uuid + '.intent.json')}
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                patch.object(plugin, '_acquire_host_control_lock', return_value=object()), \
                patch.object(plugin, '_release_operation'), \
                patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_load_operation', return_value=prior), \
                patch.object(plugin, '_read_backend_maintenance_receipt', return_value=(receipt, None)), \
                patch.object(plugin, '_host_optimization_disabled',
                             return_value=(False, 'HOST_MEMORY_OPTIMIZATION_NOT_DISABLED')):
            result = plugin._continue_backend_maintenance(
                {'operationUuid': operation_uuid}, prior, request, receipt)
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('HOST_POLICY_READBACK_UNKNOWN', result['state']['phase'])
    def test_backend_maintenance_wont_start_service_with_implicit_enable_config(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-enable-config-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-enable-config-1'
        target = {'boot_id': WRITEBACK_BOOT_ID, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'a' * 64}
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': WRITEBACK_BOOT_ID,
                   'expected_pool_generation': 'none', 'target_identity': target}
        receipt = {'request_id': operation_uuid, 'candidate_id': request['candidate_id'],
                   'host_boot_id': WRITEBACK_BOOT_ID, 'target_identity': target,
                   'stage': 'AWAITING_SERVICE_READBACK'}
        prior = {'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
                 'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
                 'requestHash': 'f' * 64,
                 'maintenanceIntentPath': os.path.join(operation_dir, 'backend-maintenance',
                                                       operation_uuid + '.intent.json'),
                 'maintenanceProgress': {}}
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_load_operation', return_value=prior), \
                patch.object(plugin, '_maintenance_service_state', return_value='inactive'), \
                patch.object(plugin, '_read_maintenance_config',
                             return_value=({'initial_efficiency_enabled': True}, operation_dir, '/dev/zram0')), \
                patch.object(plugin, '_read_backend_maintenance_receipt', return_value=(receipt, None)), \
                patch.object(subprocess, 'check_call') as start:
            result = plugin._continue_backend_maintenance(
                {'operationUuid': operation_uuid}, prior, request, receipt)
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('SERVICE_CONFIG_NOT_DISABLED', result['state']['phase'])
        start.assert_not_called()
    def test_backend_maintenance_active_service_is_not_restarted(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-active-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-active-1'
        target = {'boot_id': WRITEBACK_BOOT_ID, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'e' * 64}
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': WRITEBACK_BOOT_ID,
                   'expected_pool_generation': 'none',
                   'backend_capacity_bytes': WRITEBACK_CAPACITY,
                   'target_identity': target}
        receipt = {'request_id': operation_uuid, 'candidate_id': request['candidate_id'],
                   'host_boot_id': WRITEBACK_BOOT_ID, 'target_identity': target,
                   'stage': 'AWAITING_SERVICE_READBACK'}
        prior = {'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
                 'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
                 'requestHash': 'f' * 64,
                 'maintenanceIntentPath': os.path.join(operation_dir, 'backend-maintenance',
                                                       operation_uuid + '.intent.json'),
                 'maintenanceProgress': {}}
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_load_operation', return_value=prior), \
                patch.object(plugin, '_maintenance_service_state', return_value='active'), \
                patch.object(plugin, '_verify_maintenance_service_readback', return_value=(True, None)), \
                patch.object(plugin, '_read_backend_maintenance_receipt',
                             side_effect=[(receipt, None), (dict(receipt, stage='APPLIED'), None)]), \
                patch.object(plugin, '_service_request', return_value={}), \
                patch.object(plugin, '_host_optimization_disabled', return_value=(True, None)), \
                patch.object(plugin, '_persist_maintenance_progress', return_value=True), \
                patch.object(subprocess, 'check_call') as start:
            result = plugin._continue_backend_maintenance(
                {'operationUuid': operation_uuid}, prior, request, receipt)
        self.assertEqual('Succeeded', result['status'])
        start.assert_not_called()
    def test_backend_maintenance_reconcile_rejects_corrupt_or_unknown_journal_without_launch(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-corrupt-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-corrupt-1'
        with open(os.path.join(operation_dir, operation_uuid + '.json'), 'w') as stream:
            stream.write('{corrupt')
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_service_unit_stopped', return_value=True), \
                patch.object(subprocess, 'check_call') as launch:
            result = plugin._prepare_backend_maintenance({
                'action': 'prepareWritebackBackend', 'scope': 'Host',
                'hostUuid': 'host-1', 'operationUuid': operation_uuid,
            })
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('OPERATION_JOURNAL_UNAVAILABLE', result['reasonCode'])
        launch.assert_not_called()
    def test_backend_maintenance_finalize_maps_to_real_service_contract(self):
        self.assertEqual({'request_id': 'maintenance-finalize-2'},
            MemoryOptimizationPlugin._service_payload(
                'backend-maintenance-finalize', {'requestId': 'maintenance-finalize-2'}))
    def test_cold_ksm_local_fence_checks_external_backend_maintenance_marker(self):
        root = tempfile.mkdtemp(prefix='state-ksm-partial-maintenance-marker-')
        operation_dir = os.path.join(root, 'operations')
        state_dir = os.path.join(root, 'state')
        os.mkdir(operation_dir); os.mkdir(state_dir)
        config_path = os.path.join(root, 'config.json')
        with open(config_path, 'w') as stream:
            json.dump({'state_dir': state_dir, 'device': '/dev/zram0'}, stream)
        plugin = self._ksm_only_state_plugin(operation_dir)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'drainConfig': config_path})
        self.assertTrue(plugin._cold_ksm_local_fence_clear())
        marker_dir = os.path.join(state_dir, 'backend-maintenance')
        os.mkdir(marker_dir)
        with open(os.path.join(marker_dir, 'current.json'), 'w') as stream:
            stream.write('{"status":"running"}')
        self.assertFalse(plugin._cold_ksm_local_fence_clear(),
                         'the Go maintenance marker is outside operationDir but still authoritative')
    def test_cold_ksm_partial_flag_cannot_admit_mixed_or_maintenance_actions(self):
        root = tempfile.mkdtemp(prefix='apply-ksm-partial-shape-')
        plugin = self._ksm_only_state_plugin(root)
        base = {'action': 'apply', 'scope': 'Host', 'hostUuid': 'host-1',
                'operationUuid': 'first-ksm', 'requiresKsmNativePartialFence': True,
                'ksmNativeObservationBootId': plugin._current_boot_id(),
                'ksmNativeObservationSampleTime': int(time.time() * 1000),
                'policy': {'ksm': {'enabled': True}}}
        self.assertTrue(plugin._cold_ksm_local_fence_clear())
        self.assertIsNone(plugin._validate_cold_ksm_partial_fence(base))
        mixed = copy.deepcopy(base)
        mixed['policy']['zram'] = {'enabled': True}
        self.assertEqual('LOCAL_CONTROL_FENCE_UNKNOWN', plugin._validate_cold_ksm_partial_fence(mixed))
        maintenance = copy.deepcopy(base)
        maintenance['action'] = 'prepareWritebackBackend'
        self.assertEqual('LOCAL_CONTROL_FENCE_UNKNOWN', plugin._validate_cold_ksm_partial_fence(maintenance))
    def test_backend_maintenance_finalize_uses_real_unix_socket_route(self):
        path = tempfile.mktemp(prefix='memory-maintenance-', suffix='.sock')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(1)
        observed = []

        def serve_once():
            conn, _ = listener.accept()
            request = b''
            while b'\r\n\r\n' not in request:
                request += conn.recv(4096)
            header, body = request.split(b'\r\n\r\n', 1)
            size = next((int(line.split(b':', 1)[1]) for line in header.split(b'\r\n')
                         if line.lower().startswith(b'content-length:')), 0)
            while len(body) < size:
                body += conn.recv(size - len(body))
            observed.append((header.split(b'\r\n', 1)[0], json.loads(body.decode('utf-8'))))
            payload = json.dumps({'data': {'stage': 'APPLIED'}}).encode('utf-8')
            conn.sendall(('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                          'Content-Length: %d\r\nConnection: close\r\n\r\n' % len(payload)).encode('ascii') + payload)
            conn.close()

        thread = threading.Thread(target=serve_once)
        thread.daemon = True
        thread.start()
        try:
            plugin = MemoryOptimizationPlugin()
            plugin.configure({'socketPath': path})
            result = plugin._service_request(
                'backend-maintenance-finalize', {'requestId': 'maintenance-finalize-2'})
            self.assertEqual('APPLIED', result['stage'])
            self.assertEqual((b'POST /v1/backend-maintenance/finalize HTTP/1.1',
                              {'request_id': 'maintenance-finalize-2'}), observed[0])
        finally:
            thread.join(2)
            listener.close()
            if os.path.exists(path):
                os.unlink(path)
    def test_zram_pool_finalize_uses_real_unix_socket_route(self):
        path = tempfile.mktemp(prefix='memory-pool-maintenance-', suffix='.sock')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path); listener.listen(1)
        observed = []
        def serve_once():
            conn, _ = listener.accept(); request = b''
            while b'\r\n\r\n' not in request: request += conn.recv(4096)
            header, body = request.split(b'\r\n\r\n', 1)
            size = next((int(line.split(b':', 1)[1]) for line in header.split(b'\r\n')
                         if line.lower().startswith(b'content-length:')), 0)
            while len(body) < size: body += conn.recv(size - len(body))
            observed.append((header.split(b'\r\n', 1)[0], json.loads(body.decode('utf-8'))))
            payload = json.dumps({'data': {'stage': 'APPLIED'}}).encode('utf-8')
            conn.sendall(('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                          'Content-Length: %d\r\nConnection: close\r\n\r\n' % len(payload)).encode('ascii') + payload)
            conn.close()
        thread = threading.Thread(target=serve_once); thread.daemon = True; thread.start()
        try:
            plugin = MemoryOptimizationPlugin(); plugin.configure({'socketPath': path})
            result = plugin._service_request('zram-pool-maintenance-finalize', {'requestId': 'pool-finalize-2'})
            self.assertEqual('APPLIED', result['stage'])
            self.assertEqual((b'POST /v1/zram-pool-maintenance/finalize HTTP/1.1',
                              {'request_id': 'pool-finalize-2'}), observed[0])
        finally:
            thread.join(2); listener.close()
            if os.path.exists(path): os.unlink(path)
    @pytest.mark.privileged
    def test_actual_go_cli_accepts_python_zram_pool_request_contract(self):
        binary = os.environ.get('ZRAM_EFFICIENCY_TEST_BINARY')
        if not binary or not os.path.isfile(binary):
            self.skipTest('set ZRAM_EFFICIENCY_TEST_BINARY to the current compiled Go CLI')
        command = {'action': 'prepareZramPool', 'scope': 'Host', 'hostUuid': 'host-1',
                   'operationUuid': 'pool-go-contract-1', 'policy': {},
                   'expectedControlOperationUuid': 'drain-anchor-1',
                   'poolPreparation': {'expectedHostBootId': WRITEBACK_BOOT_ID,
                                       'expectedPoolGeneration': 'c' * 64,
                                       'resetConfirmed': True}}
        snapshot = {'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
                    'poolGeneration': 'c' * 64, 'controlOperationUuid': 'drain-anchor-1',
                    'canPrepareZramPool': True}
        plugin = MemoryOptimizationPlugin()
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID):
            request = plugin._zram_pool_preparation_request(command, snapshot)
        wire_request = {key: value for key, value in request.items() if key != '_request_fingerprint'}
        temp_root = tempfile.mkdtemp(prefix='memory-zram-pool-go-contract-')
        missing_config = os.path.join(temp_root, 'guaranteed-missing-config.json')
        try:
            process = subprocess.Popen([binary, '--config', missing_config, '--prepare-zram-pool'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(json.dumps(wire_request, separators=(',', ':')).encode('utf-8'))
            # The guaranteed absent config proves strict JSON decoding accepted
            # the Python wire request, then safely fails with ENOENT before any
            # device mutation. The CLI reports the OS error, not the path name.
            self.assertNotEqual(0, process.returncode)
            self.assertEqual({'error': 'no such file or directory'}, json.loads(stderr))
            self.assertNotIn(b'ZRAM_POOL_PREPARATION_CONFIRMATION_REQUIRED', stderr)

            # A malformed extra key must be rejected by the strict decoder
            # before configuration loading; this catches accidental permissive
            # decoding without relying on the missing-config error above.
            unknown_field_request = dict(wire_request, unexpectedContractField=True)
            process = subprocess.Popen([binary, '--config', missing_config, '--prepare-zram-pool'],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            _stdout, unknown_field_stderr = process.communicate(
                json.dumps(unknown_field_request, separators=(',', ':')).encode('utf-8'))
            self.assertNotEqual(0, process.returncode)
            self.assertIn('unknown field', json.loads(unknown_field_stderr)['error'].lower())
        finally:
            __import__('shutil').rmtree(temp_root, ignore_errors=True)

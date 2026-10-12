"""Memory optimization drain_recovery behavior tests.

Migrated from the legacy Agent test module; all methods remain discovered by pytest.
"""

from tests.unit.kvmagent.memory_optimization_test_support import *
from tests.unit.kvmagent.memory_optimization_test_support import _OMIT_POLICY_MODE
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.kvmagent]

class TestMemoryOptimizationDrainRecovery(MemoryOptimizationTestBase):
    def test_rejected_resume_reconcile_proves_retained_fence_without_rewriting_history(self):
        plugin, directory, command = self._rejected_resume_fixture()
        before = {name: open(os.path.join(directory, name), 'rb').read()
                  for name in ('active-control', 'drain-before-resume.json', 'rejected-resume.json')}
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'):
            for unused in range(2):
                result = json.loads(plugin.reconcile({'body': json.dumps(command)}))
                self.assertTrue(result['success'], result)
                self.assertEqual('CONTROL_NOT_ISSUED', result['state']['phase'])
                proof = result['state']['controlFenceProof']
                self.assertEqual('drain-before-resume', proof['controlOperationUuid'])
                self.assertEqual('rejected-resume', proof['rejectedOperationUuid'])
                self.assertEqual('drain', proof['controlAction'])
                self.assertEqual(plugin._current_boot_id(), proof['bootId'])
        for name, expected in before.items():
            with open(os.path.join(directory, name), 'rb') as stream:
                self.assertEqual(expected, stream.read(), name)
    def test_rejected_resume_reconcile_rejects_missing_changed_or_unproven_evidence(self):
        mutations = [
            ('rejected-resume.json', 'stage', 'UNKNOWN'),
            ('rejected-resume.json', 'action', 'pause'),
            ('rejected-resume.json', 'hostUuid', 'foreign'),
            ('rejected-resume.json', 'bootId', 'old-boot'),
            ('rejected-resume.json', 'readback', {'reason': 'OTHER_ERROR'}),
            ('rejected-resume.json', 'expectedControlOperationUuid', 'other-control'),
            ('drain-before-resume.json', 'stage', 'DRAINING'),
            ('drain-before-resume.json', 'action', 'apply'),
            ('drain-before-resume.json', 'hostUuid', 'foreign'),
            ('drain-before-resume.json', 'bootId', 'old-boot'),
            ('drain-before-resume.json', 'readback', {'success': False, 'status': 'Unknown'}),
        ]
        for filename, key, value in mutations:
            with self.subTest(filename=filename, key=key):
                plugin, directory, command = self._rejected_resume_fixture()
                path = os.path.join(directory, filename)
                with open(path) as stream:
                    record = json.load(stream)
                record[key] = value
                with open(path, 'w') as stream:
                    json.dump(record, stream)
                with patch.object(plugin, '_load_host_uuid', return_value='host-1'):
                    result = json.loads(plugin.reconcile({'body': json.dumps(command)}))
                self.assertFalse(result['success'], result)
                self.assertEqual('Unknown', result['status'])
                self.assertNotIn('controlFenceProof', result.get('state', {}))
                self.assertEqual('drain-before-resume', plugin._get_active_control())
                with open(path) as stream:
                    self.assertEqual(record, json.load(stream), 'verification must not modify evidence')
    def test_rejected_resume_reconcile_rejects_newer_control_or_concurrent_writer(self):
        for mode in ('changed-command', 'changed-active', 'busy', 'missing', 'symlink'):
            with self.subTest(mode=mode):
                plugin, directory, command = self._rejected_resume_fixture()
                if mode == 'changed-command':
                    command['expectedControlOperationUuid'] = 'different-control'
                if mode == 'changed-active':
                    plugin._set_active_control('new-control')
                anchor_path = os.path.join(directory, 'drain-before-resume.json')
                if mode == 'missing':
                    os.unlink(anchor_path)
                if mode == 'symlink':
                    os.rename(anchor_path, anchor_path + '.other')
                    os.symlink(anchor_path + '.other', anchor_path)
                lock = plugin._acquire_host_control_lock() if mode == 'busy' else None
                try:
                    with patch.object(plugin, '_load_host_uuid', return_value='host-1'):
                        result = json.loads(plugin.reconcile({'body': json.dumps(command)}))
                    self.assertFalse(result['success'], result)
                    self.assertEqual('Unknown', result['status'])
                    self.assertNotIn('controlFenceProof', result.get('state', {}))
                finally:
                    plugin._release_operation(lock)
    def test_resume_rechecks_fence_after_acquiring_writer_lock(self):
        plugin, directory, command = self._rejected_resume_fixture()
        pause = {'operationUuid': 'pause-before-race', 'action': 'pause',
                 'hostUuid': 'host-1', 'scope': 'Host', 'desiredRevision': 7}
        plugin._record_operation(pause, 'APPLIED', {'success': True, 'status': 'Succeeded'})
        plugin._set_active_control(pause['operationUuid'])

        def claim_after_new_control(unused):
            lock = plugin._acquire_host_control_lock()
            # A newer control completed between the optimistic check and lock.
            plugin._set_active_control('newer-control')
            return lock, True

        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_claim_operation', side_effect=claim_after_new_control), \
                patch.object(plugin, '_service_request') as native, \
                patch.object(plugin, '_control_managed_ksm') as ksm:
            result = plugin.apply({'hostUuid': 'host-1', 'scope': 'Host', 'action': 'resume',
                'operationUuid': 'resume-race', 'desiredRevision': 7,
                'expectedControlOperationUuid': pause['operationUuid']})
        self.assertEqual('Failed', result['status'], result)
        self.assertEqual('CONTROL_OPERATION_FENCED', result['reason'])
        native.assert_not_called()
        ksm.assert_not_called()
        self.assertEqual('newer-control', plugin._get_active_control())
    def test_backend_maintenance_uncertain_launch_is_one_shot_and_keeps_drain_fence(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-launch-')
        binary = os.path.join(operation_dir, 'zram-efficiency')
        config = os.path.join(operation_dir, 'config.json')
        open(binary, 'w').close()
        open(config, 'w').close()
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'drainBinary': binary, 'drainConfig': config})
        command = {
            'action': 'prepareWritebackBackend', 'scope': 'Host',
            'hostUuid': 'host-1', 'operationUuid': 'maintenance-launch-1',
            'backendPreparation': {
                'candidateId': 'candidate:' + WRITEBACK_FINGERPRINT,
                'expectedHostBootId': WRITEBACK_BOOT_ID,
                'expectedPoolGeneration': 'none',
                'backendCapacityBytes': WRITEBACK_CAPACITY,
                'resetConfirmed': True,
            },
        }
        # Backend maintenance checks the managed service state API.
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                patch.object(plugin, '_maintenance_service_state', return_value='inactive'), \
                patch.object(plugin, '_fresh_backend_maintenance_inventory',
                             return_value=self._maintenance_inventory()), \
                patch.object(plugin, '_backend_preparation_request',
                             return_value={'request_id': 'maintenance-launch-1'}), \
                patch.object(plugin, '_get_active_control', return_value='drain-anchor-1'), \
                patch.object(subprocess, 'check_call', side_effect=OSError('launch response lost')) as launch:
            first = plugin._prepare_backend_maintenance(command)
            replay = plugin._prepare_backend_maintenance(command)
        self.assertEqual('Unknown', first['status'])
        self.assertEqual('Unknown', replay['status'])
        self.assertEqual(1, launch.call_count)
        with open(os.path.join(operation_dir, 'backend-maintenance',
                               'maintenance-launch-1.intent.json'), 'r') as stream:
            intent = json.load(stream)
        self.assertEqual('drain-anchor-1', intent['controlOperationUuid'])
        self.assertTrue(intent['workerLaunchAttempted'])
    def test_zram_pool_preparation_request_is_bound_to_existing_drain_and_boot(self):
        plugin = MemoryOptimizationPlugin()
        operation_uuid = 'pool-prepare-contract-1'
        generation = 'a' * 64
        command = {'action': 'prepareZramPool', 'scope': 'Host', 'hostUuid': 'host-1',
                   'operationUuid': operation_uuid, 'policy': {},
                   'expectedControlOperationUuid': 'drain-anchor-1',
                   'poolPreparation': {'expectedHostBootId': WRITEBACK_BOOT_ID,
                                       'expectedPoolGeneration': generation,
                                       'resetConfirmed': True}}
        snapshot = {'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
                    'poolGeneration': generation, 'controlOperationUuid': 'drain-anchor-1',
                    'canPrepareZramPool': True}
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID):
            request = plugin._zram_pool_preparation_request(command, snapshot)
            self.assertEqual(operation_uuid, request['request_id'])
            self.assertEqual('drain-anchor-1', request['expected_control_operation_uuid'])
            self.assertEqual(64, len(request['_request_fingerprint']))
            for mutation in (
                    {'expectedPoolGeneration': 'none'},
                    {'expectedHostBootId': 'stale-boot'},
                    {'resetConfirmed': False}):
                bad = dict(command)
                bad['poolPreparation'] = dict(command['poolPreparation'])
                bad['poolPreparation'].update(mutation)
                with self.assertRaises(ValueError):
                    plugin._zram_pool_preparation_request(bad, snapshot)
            with self.assertRaises(ValueError):
                plugin._zram_pool_preparation_request(command,
                    dict(snapshot, controlOperationUuid='another-drain'))
    def test_zram_pool_uncertain_service_start_is_observed_not_replayed(self):
        operation_dir = tempfile.mkdtemp(prefix='zram-pool-start-unknown-')
        self.addCleanup(lambda: __import__('shutil').rmtree(operation_dir, ignore_errors=True))
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        boot_id = plugin._current_boot_id()
        command = {'action': 'prepareZramPool', 'scope': 'Host', 'hostUuid': 'host-1',
                   'operationUuid': 'pool-start-unknown-1', 'policy': {},
                   'expectedControlOperationUuid': 'drain-anchor-1',
                   'poolPreparation': {'expectedHostBootId': boot_id,
                                       'expectedPoolGeneration': 'e' * 64,
                                       'resetConfirmed': True}}
        command['poolMaintenanceIntentPath'] = os.path.join(
            operation_dir, 'zram-pool-maintenance', 'pool-start-unknown-1.intent.json')
        plugin._record_operation(command, 'SERVICE_START_UNKNOWN',
            plugin._maintenance_result(command, 'Unknown', 'SERVICE_START_UNKNOWN'))
        prior = plugin._load_operation({'operationUuid': command['operationUuid']})
        prior['maintenanceProgress'] = {'serviceStartAttempted': True,
                                        'serviceUnit': plugin.MANAGED_ZRAM_UNIT}
        plugin._atomic_json(plugin._operation_path(command['operationUuid']), prior)
        snapshot = {'hostUuid': 'host-1', 'bootId': boot_id,
                    'poolGeneration': 'e' * 64, 'controlOperationUuid': 'drain-anchor-1',
                    'canPrepareZramPool': True}
        with patch.object(plugin, '_current_boot_id', return_value=boot_id):
            request = plugin._zram_pool_preparation_request(command, snapshot)
        receipt = {'request_id': command['operationUuid'],
                   'request_fingerprint': request['_request_fingerprint'],
                   'expected_control_operation_uuid': 'drain-anchor-1',
                   'host_boot_id': boot_id, 'pool_generation': 'e' * 64,
                   'stage': 'AWAITING_SERVICE_READBACK'}
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_current_boot_id', return_value=boot_id), \
                patch.object(plugin, '_read_zram_pool_preparation_receipt', return_value=(receipt, None)), \
                patch.object(plugin, '_maintenance_service_state', return_value='inactive'), \
                patch.object(subprocess, 'check_call') as start:
            result = plugin._continue_zram_pool_preparation(command, prior, request, receipt)
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('ZRAM_POOL_SERVICE_START_UNRESOLVED', result['reasonCode'], result)
        start.assert_not_called()
    def test_backend_maintenance_uncertain_start_is_not_replayed(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-backend-maintenance-start-unknown-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        operation_uuid = 'maintenance-start-unknown-1'
        target = {'boot_id': WRITEBACK_BOOT_ID, 'canonical_device': WRITEBACK_DEVICE,
                  'rdev': 64784, 'node_inode': 101, 'sysfs_inode': 303,
                  'capacity_bytes': WRITEBACK_CAPACITY, 'stack_sha256': 'f' * 64}
        request = {'request_id': operation_uuid, 'candidate_id': 'candidate:' + WRITEBACK_FINGERPRINT,
                   'expected_host_boot_id': WRITEBACK_BOOT_ID,
                   'expected_pool_generation': 'none', 'target_identity': target}
        receipt = {'request_id': operation_uuid, 'candidate_id': request['candidate_id'],
                   'host_boot_id': WRITEBACK_BOOT_ID, 'target_identity': target,
                   'stage': 'AWAITING_SERVICE_READBACK'}
        # `prior` is an unlocked snapshot. The durable journal has a newer
        # start-attempt marker written by another reconcile under the lock.
        prior = {'operationUuid': operation_uuid, 'action': 'prepareWritebackBackend',
                 'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
                 'requestHash': 'f' * 64,
                 'maintenanceIntentPath': os.path.join(operation_dir, 'backend-maintenance',
                                                       operation_uuid + '.intent.json'),
                 'maintenanceProgress': {}}
        current = dict(prior, maintenanceProgress={'serviceStartAttempted': True})
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(plugin, '_load_operation', return_value=current), \
                patch.object(plugin, '_maintenance_service_state', return_value='inactive'), \
                patch.object(plugin, '_read_backend_maintenance_receipt', return_value=(receipt, None)), \
                patch.object(plugin, '_persist_maintenance_progress', return_value=True), \
                patch.object(subprocess, 'check_call') as start:
            result = plugin._continue_backend_maintenance(
                {'operationUuid': operation_uuid}, prior, request, receipt)
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('SERVICE_START_UNRESOLVED', result['state']['phase'])
        start.assert_not_called()
    def test_http_success_with_async_draining_state_is_accepted_and_structured(self):
        response = MemoryOptimizationPlugin._normalize_response(
            {'_http_status': 200, 'state': {'phase': 'DRAINING'}}, 'apply',
            {'operationUuid': 'op-drain'})
        self.assertEqual('Draining', response['status'])
        self.assertTrue(response['success'], response)
        self.assertEqual({'phase': 'DRAINING'}, response['state'])
        response = MemoryOptimizationPlugin._normalize_response(
            {'_http_status': 202, 'status': 'DRAINING', 'state': 'DRAINING'},
            'apply', {'operationUuid': 'op-drain-2'})
        self.assertEqual('Draining', response['status'])
        self.assertIsInstance(response['state'], dict)
        response = MemoryOptimizationPlugin._normalize_response(
            {'paused': True, 'activeState': 'paused', '_http_status': 200},
            'lifecycle-pause', {'operationUuid': 'op-pause-raw'})
        self.assertEqual('Succeeded', response['status'])
        self.assertTrue(response['success'])
        self.assertTrue(response['state']['paused'])
        self.assertEqual('paused', response['state']['activeState'])
    def test_resume_ack_timestamp_is_after_managed_ksm_transition(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-resume-sample-')
        calls = []
        transition_completed_at = []

        def service(action, payload):
            calls.append((action, payload))
            if action == 'lifecycle-pause':
                paused = payload.get('lifecycleAction') == 'pause'
                return {'_http_status': 200, 'success': True, 'status': 'Succeeded', 'paused': paused,
                        'activeState': 'paused' if paused else 'active',
                        'desiredRevision': 4, 'readbackAllowed': True}
            return {'_http_status': 200, 'success': True, 'status': 'Succeeded'}

        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})

        def managed_ksm(action, command):
            if action == 'resume':
                time.sleep(0.01)
                transition_completed_at.append(int(time.time() * 1000))

        with patch.object(plugin, '_control_managed_ksm', side_effect=managed_ksm):
            pause = plugin.apply({'action': 'pause', 'hostUuid': 'host-1',
                                  'operationUuid': 'pause-sample-1'})
            resume = plugin.apply({'action': 'resume', 'hostUuid': 'host-1',
                                   'operationUuid': 'resume-sample-1',
                                   'expectedControlOperationUuid': 'pause-sample-1'})

        self.assertTrue(pause['success'])
        self.assertTrue(resume['success'])
        self.assertEqual('RESUMED', resume['state']['phase'])
        self.assertGreaterEqual(resume['sampleTime'], transition_completed_at[0])
    def test_apply_request_drain_is_async_and_license_free(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-drain-')
        calls = []
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload:
                calls.append((action, payload)) or
                ({'host_zram': {'pool_generation': 'pool-7', 'device': '/dev/zram0'}}
                 if action == 'state' else
                 {'revision': 0, 'efficiency_enabled': False,
                  'idle_cpu_threshold_percent': 80,
                  'idle_duration_seconds': 60}
                 if action == 'host-cpu-state' else
                 {'revision': 0, 'efficiency_enabled': False,
                  'idle_cpu_threshold_percent': 80,
                  'idle_duration_seconds': 60}
                 if action.endswith('-state') else
                 {'status': 'Succeeded'}))
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        with patch.object(plugin, '_apply_ksm_policy') as ksm, \
                patch.object(plugin, '_start_stock_drain', return_value={
                    'pid': 123, 'receiptPath': os.path.join(operation_dir, 'receipt.json')}):
            response = json.loads(plugin.apply_request({'body': json.dumps({
                'action': 'drain', 'hostUuid': 'host-1',
                'operationUuid': 'drain-1', 'poolGeneration': 'pool-7'})}))
        self.assertTrue(response['success'])
        self.assertEqual('Draining', response['status'])
        self.assertIsNone(response.get('appliedRevision'))
        self.assertEqual(['lifecycle-pause', 'state', 'host-cpu-state'],
                         [item[0] for item in calls])
        ksm.assert_not_called()
    def test_drain_reconcile_reads_receipt_without_restarting_executor(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-drain-reconcile-')
        calls = []
        def service(action, payload):
            calls.append(action)
            if action == 'lifecycle-pause':
                return {'status': 'Succeeded'}
            if action == 'state':
                return {'host_zram': {'pool_generation': 'pool-1', 'device': '/dev/zram0'}}
            if action == 'host-cpu-state':
                return {'revision': 0, 'efficiency_enabled': False,
                        'idle_cpu_threshold_percent': 80,
                        'idle_duration_seconds': 60}
            raise AssertionError(action)
        plugin = MemoryOptimizationPlugin(service_call=service)
        binary = os.path.join(operation_dir, 'binary')
        config = os.path.join(operation_dir, 'config')
        open(binary, 'w').close()
        open(config, 'w').close()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'drainDir': operation_dir, 'drainBinary': binary, 'drainConfig': config})
        command = {'action': 'drain', 'hostUuid': 'host-1',
                   'operationUuid': 'drain-reconcile-1', 'poolGeneration': 'pool-1'}
        receipt_path = os.path.join(operation_dir, 'drain-reconcile-1.receipt.json')
        with patch.object(subprocess, 'check_call'):
            first = plugin.apply(command)
        self.assertEqual('Draining', first['status'])
        self.assertEqual(['lifecycle-pause', 'state', 'host-cpu-state'], calls)
        # A duplicate request returns the durable state; it cannot submit a
        # second native drain operation.
        self.assertEqual('Draining', plugin.apply(command)['status'])
        self.assertEqual(3, len(calls))
        receipt = {'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
                   'active': False, 'reset_performed': False,
                   'pool_generation': 'pool-1', 'device': '/dev/zram0'}
        with open(receipt_path, 'w') as stream:
            json.dump(receipt, stream)
        with patch.object(subprocess, 'check_output', return_value=json.dumps(receipt).encode()):
            reconciled = json.loads(plugin.reconcile({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'drain-reconcile-1'})}))
        self.assertTrue(reconciled['success'])
        self.assertEqual('Succeeded', reconciled['status'])
        self.assertEqual(3, len(calls))
    def test_drain_reconcile_keeps_live_executor_pending(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-drain-pending-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'drainDir': operation_dir,
                          'drainConfig': os.path.join(operation_dir, 'config')})
        operation_uuid = 'drain-pending-1'
        boot = plugin._current_boot_id()
        prior = {'operationUuid': operation_uuid, 'action': 'drain',
                 'bootId': boot, 'hostUuid': 'host-1'}
        with open(os.path.join(operation_dir, '%s.drain-intent.json' % operation_uuid), 'w') as stream:
            json.dump({'operationUuid': operation_uuid, 'bootId': boot,
                       'poolGeneration': 'pool-1', 'device': '/dev/zram0',
                       'unit': 'zstack-memory-drain-%s' % operation_uuid,
                       'receiptPath': os.path.join(operation_dir, '%s.receipt.json' % operation_uuid),
                       'configPath': os.path.join(operation_dir, 'config')}, stream)
        with patch.object(plugin, '_load_host_uuid', return_value='host-1'), \
                patch.object(subprocess, 'check_output', return_value=b'active\n'):
            result = plugin._reconcile_stock_drain(
                {'operationUuid': operation_uuid}, prior)
        self.assertTrue(result['success'])
        self.assertEqual('Draining', result['status'])
        self.assertEqual('DRAINING', result['state']['phase'])
    def test_resume_requires_same_boot_completed_pause_not_drain(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-control-resume-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        plugin._set_active_control('drain-1')
        plugin._record_operation({'operationUuid': 'drain-1', 'action': 'drain',
                                  'hostUuid': 'host-1'}, 'DRAINING', {'status': 'Draining'})
        self.assertIsNone(plugin._resume_control_record())
        plugin._set_active_control('pause-1')
        plugin._record_operation({'operationUuid': 'pause-1', 'action': 'pause',
                                  'hostUuid': 'host-1'}, 'APPLIED', {'status': 'Succeeded'})
        self.assertEqual('pause-1', plugin._resume_control_record()['operationUuid'])
    def test_completed_drain_requires_verified_release_archive_and_new_pool(self):
        root = tempfile.mkdtemp(prefix='memory-maintenance-proof-')
        state_dir = os.path.join(root, 'service-state')
        old_generation = 'a' * 64
        new_generation = 'b' * 64
        archive = os.path.join(state_dir, 'drained-pool-archives', old_generation)
        os.makedirs(archive)
        with open(os.path.join(archive, 'manifest.json'), 'w') as stream:
            json.dump({'schema': 1, 'pool_generation': old_generation,
                       'files': ['stock-pool.json', 'zram-ownership.json', 'maintenance']}, stream)
        config = os.path.join(root, 'config.json')
        with open(config, 'w') as stream:
            json.dump({'state_dir': state_dir}, stream)
        operation = 'drain-maintenance-proof'
        drain_dir = os.path.join(root, 'drain')
        os.makedirs(drain_dir)
        receipt_path = os.path.join(drain_dir, operation + '.receipt.json')
        with open(receipt_path, 'w') as stream:
            json.dump({'pool_generation': old_generation, 'device': '/dev/zram0',
                       'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
                       'active': False, 'reset_performed': False}, stream)
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
            {'host_zram': {'pool_generation': new_generation, 'device': '/dev/zram0'},
             'pending_operations': []} if action == 'state' else {'status': 'Succeeded'})
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root,
                          'drainDir': drain_dir, 'drainConfig': config})
        boot = plugin._current_boot_id()
        with open(os.path.join(root, operation + '.drain-intent.json'), 'w') as stream:
            json.dump({'operationUuid': operation, 'bootId': boot,
                       'poolGeneration': old_generation, 'device': '/dev/zram0',
                       'receiptPath': receipt_path}, stream)
        plugin._record_operation({'operationUuid': operation, 'action': 'drain',
                                  'hostUuid': 'host-1'}, 'APPLIED', {'status': 'Succeeded'})
        plugin._set_active_control(operation)
        generated = plugin._maintenance_proof_for_state(
            {'host_zram': {'pool_generation': new_generation}, 'pending_operations': []})
        self.assertEqual(new_generation, generated['newPoolGeneration'])
        self.assertTrue(generated['maintenanceArchived'])
        self.assertEqual(0, generated['activeOperations'])
        proof = {'maintenanceReady': True, 'drainOperationUuid': operation,
                 'oldPoolGeneration': old_generation, 'newPoolGeneration': new_generation,
                 'maintenanceArchived': True, 'activeOperations': 0,
                 'poolOwnedByService': True, 'readyForInitialization': False,
                 'originalDeviceInactive': True, 'oldPoolOwnershipAbsent': True}
        for pending in (None, []):
            self.assertTrue(plugin._maintenance_recovery_proof(
                {'maintenanceProof': proof},
                live_state={'host_zram': {'pool_generation': new_generation},
                            'pending_operations': pending}))
        self.assertFalse(plugin._maintenance_recovery_proof(
            {'maintenanceProof': proof},
            live_state={'host_zram': {'pool_generation': new_generation},
                        'pending_operations': [{'id': 'in-flight'}]}))
        self.assertFalse(plugin._maintenance_recovery_proof(
            {'maintenanceProof': proof},
            live_state={'host_zram': {'pool_generation': new_generation}}))
        self.assertTrue(plugin._maintenance_recovery_proof({'maintenanceProof': proof}))
        self.assertFalse(plugin._host_control_blocks_policy({'maintenanceProof': proof}))
        proof['newPoolGeneration'] = old_generation
        self.assertTrue(plugin._host_control_blocks_policy({'maintenanceProof': proof}))
    def test_completed_drain_accepts_verified_archived_observed_receipt(self):
        root = tempfile.mkdtemp(prefix='memory-maintenance-archive-receipt-')
        state_dir = os.path.join(root, 'service-state')
        old_generation = 'c' * 64
        new_generation = 'd' * 64
        archive = os.path.join(state_dir, 'drained-pool-archives', old_generation)
        observed_dir = os.path.join(archive, 'maintenance', 'executor-1')
        os.makedirs(observed_dir)
        with open(os.path.join(archive, 'manifest.json'), 'w') as stream:
            json.dump({'schema': 1, 'pool_generation': old_generation,
                       'files': ['stock-pool.json', 'zram-ownership.json', 'maintenance']}, stream)
        with open(os.path.join(observed_dir, 'observed.json'), 'w') as stream:
            json.dump({'pool_generation': old_generation, 'device': '/dev/zram0',
                       'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
                       'active': False, 'reset_performed': False}, stream)
        config = os.path.join(root, 'config.json')
        with open(config, 'w') as stream:
            json.dump({'state_dir': state_dir}, stream)
        operation = 'drain-archived-receipt'
        drain_dir = os.path.join(root, 'drain')
        os.makedirs(drain_dir)
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root,
                          'drainDir': drain_dir, 'drainConfig': config})
        boot = plugin._current_boot_id()
        with open(os.path.join(root, operation + '.drain-intent.json'), 'w') as stream:
            json.dump({'operationUuid': operation, 'bootId': boot,
                       'poolGeneration': old_generation, 'device': '/dev/zram0',
                       'receiptPath': os.path.join(drain_dir, operation + '.receipt.json')}, stream)
        plugin._record_operation({'operationUuid': operation, 'action': 'drain',
                                  'hostUuid': 'host-1'}, 'APPLIED', {'status': 'Succeeded'})
        plugin._set_active_control(operation)
        proof = {'maintenanceReady': True, 'drainOperationUuid': operation,
                 'oldPoolGeneration': old_generation, 'newPoolGeneration': new_generation,
                 'maintenanceArchived': True, 'activeOperations': 0,
                 'poolOwnedByService': True, 'readyForInitialization': False,
                 'originalDeviceInactive': True, 'oldPoolOwnershipAbsent': True}
        self.assertTrue(plugin._maintenance_recovery_proof(
            {'maintenanceProof': proof},
            live_state={'host_zram': {'pool_generation': new_generation},
                        'pending_operations': None}))
    def test_empty_pool_recovery_proof_reads_archive_and_releases_drain_fence(self):
        from io import StringIO

        root = tempfile.mkdtemp(prefix='memory-empty-pool-proof-')
        state_dir = os.path.join(root, 'service-state')
        old_generation = 'e' * 64
        archive = os.path.join(state_dir, 'drained-pool-archives', old_generation)
        observed_dir = os.path.join(archive, 'maintenance', 'executor-1')
        os.makedirs(observed_dir)
        with open(os.path.join(archive, 'manifest.json'), 'w') as stream:
            json.dump({'schema': 1, 'pool_generation': old_generation,
                       'files': ['stock-pool.json', 'zram-ownership.json', 'maintenance']}, stream)
        observed_path = os.path.join(observed_dir, 'observed.json')
        observed = {'pool_generation': old_generation, 'device': '/dev/zram0',
                    'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
                    'active': False, 'reset_performed': False}
        with open(observed_path, 'w') as stream:
            json.dump(observed, stream)
        config = os.path.join(root, 'config.json')
        with open(config, 'w') as stream:
            json.dump({'state_dir': state_dir}, stream)
        operation = 'drain-empty-pool-proof'
        drain_dir = os.path.join(root, 'drain')
        os.makedirs(drain_dir)
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root,
                          'drainDir': drain_dir, 'drainConfig': config})
        boot = plugin._current_boot_id()
        with open(os.path.join(root, operation + '.drain-intent.json'), 'w') as stream:
            json.dump({'operationUuid': operation, 'bootId': boot,
                       'poolGeneration': old_generation, 'device': '/dev/zram0',
                       'receiptPath': os.path.join(drain_dir, operation + '.receipt.json')}, stream)
        plugin._record_operation({'operationUuid': operation, 'action': 'drain',
                                  'hostUuid': 'host-1'}, 'APPLIED', {'status': 'Succeeded'})
        plugin._set_active_control(operation)
        state = {'host_zram': {'pool_generation': '', 'device': '',
                               'quality': 'unavailable',
                               'reason': 'NO_QUALIFIED_MANAGED_POOL: EXCLUSIVE_ZRAM_ROUTE_REQUIRED'},
                 'pending_operations': None}
        plugin.service_call = lambda action, payload: state

        real_open = open
        def open_readback(path, *args, **kwargs):
            if path == '/proc/swaps':
                return StringIO('Filename\tType\tSize\tUsed\tPriority\n')
            if path == '/sys/block/zram0/mm_stat':
                return StringIO('0 0 0 0 0 0 0 0 0 0')
            return real_open(path, *args, **kwargs)

        with patch('builtins.open', side_effect=open_readback):
            proof = plugin._maintenance_proof_for_state(state)
        self.assertIsNotNone(proof)
        self.assertTrue(plugin._is_uninitialized_pool_snapshot(state['host_zram']))
        with patch('builtins.open', side_effect=open_readback):
            self.assertFalse(plugin._host_control_blocks_policy({'maintenanceProof': proof}))

        # A writeback-enabled old pool archives its quiescent schedule too.
        # Reproduce the real Go manifest, not only the no-backend 3-file shape.
        manifest_path = os.path.join(archive, 'manifest.json')
        manifest = {'schema': 1, 'pool_generation': old_generation,
                    'files': ['stock-pool.json', 'zram-ownership.json', 'maintenance',
                              'writeback-schedule.json']}
        schedule = {'version': 1, 'pool_generation': old_generation,
                    'backend_generation': 'b' * 32, 'active_id': '', 'active_action': ''}
        with open(manifest_path, 'w') as stream:
            json.dump(manifest, stream)
        with open(os.path.join(archive, 'stock-pool.json'), 'w') as stream:
            json.dump({'userspace_ownership_generation': old_generation,
                       'backend': {'generation': 'b' * 32}}, stream)
        schedule_path = os.path.join(archive, 'writeback-schedule.json')
        with open(schedule_path, 'w') as stream:
            json.dump(schedule, stream)
        with patch('builtins.open', side_effect=open_readback):
            proof = plugin._maintenance_proof_for_state(state)
            self.assertIsNotNone(proof)
            self.assertFalse(plugin._host_control_blocks_policy({'maintenanceProof': proof}))
        for changes in ({'active_id': 'i' * 32}, {'active_action': 'writeback'},
                        {'pool_generation': 'f' * 64}, {'backend_generation': 'c' * 32},
                        {'version': 2}, {'version': True}, {'active_id': None}):
            with open(schedule_path, 'w') as stream:
                json.dump(dict(schedule, **changes), stream)
            with patch('builtins.open', side_effect=open_readback):
                self.assertIsNone(plugin._maintenance_proof_for_state(state))
        os.unlink(schedule_path)
        with patch('builtins.open', side_effect=open_readback):
            self.assertIsNone(plugin._maintenance_proof_for_state(state))
        with open(manifest_path, 'w') as stream:
            json.dump(dict(manifest, files=manifest['files'][:3]), stream)

        for invalid_files in (manifest['files'] + ['unknown.json'],
                              manifest['files'][:2], manifest['files'] + ['maintenance']):
            with open(manifest_path, 'w') as stream:
                json.dump(dict(manifest, files=invalid_files), stream)
            with patch('builtins.open', side_effect=open_readback):
                self.assertIsNone(plugin._maintenance_proof_for_state(state))
        with open(manifest_path, 'w') as stream:
            json.dump(dict(manifest, files=manifest['files'][:3]), stream)

        for invalid_state in (
                {'host_zram': state['host_zram']},
                {'host_zram': state['host_zram'], 'pending_operations': [{'id': 'in-flight'}]},
                {'host_zram': dict(state['host_zram'], device='/dev/zram0'),
                 'pending_operations': None}):
            with patch('builtins.open', side_effect=open_readback):
                self.assertIsNone(plugin._maintenance_proof_for_state(invalid_state))

        with open(observed_path, 'w') as stream:
            json.dump(dict(observed, pool_generation='f' * 64), stream)
        with patch('builtins.open', side_effect=open_readback):
            self.assertIsNone(plugin._maintenance_proof_for_state(state))
        with open(observed_path, 'w') as stream:
            json.dump(dict(observed, active=True), stream)
        with patch('builtins.open', side_effect=open_readback):
            self.assertIsNone(plugin._maintenance_proof_for_state(state))
    def test_completed_apply_retry_returns_receipt_before_drain_proof(self):
        root = tempfile.mkdtemp(prefix='memory-maintenance-retry-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root})
        command = {'action': 'apply', 'hostUuid': 'host-1',
                   'operationUuid': 'apply-after-maintenance',
                   'policy': {'zram': {'enabled': False}, 'writeback': {'enabled': False}}}
        receipt = {'success': True, 'status': 'Succeeded',
                   'state': {'phase': 'APPLIED'}, 'operationUuid': command['operationUuid']}
        plugin._record_operation(command, 'APPLIED', receipt)
        plugin._set_active_control('completed-drain')
        self.assertEqual(receipt, plugin.apply(command))
    def test_stock_drain_uses_fixed_managed_unit_and_cli_config(self):
        root = tempfile.mkdtemp(prefix='stock-drain-launch-')
        binary = os.path.join(root, 'zram-efficiency')
        config = os.path.join(root, 'config.json')
        open(binary, 'w').close()
        open(config, 'w').close()
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'operationDir': root, 'drainDir': os.path.join(root, 'drain'),
                          'drainBinary': binary, 'drainConfig': config,
                          'drainUnit': 'zram-efficiency.service'})
        with patch.object(subprocess, 'check_call') as stop:
            result = plugin._start_stock_drain({'operationUuid': 'stock-drain-1',
                                                'poolGeneration': 'pool-1',
                                                'device': '/dev/zram0'})
        self.assertEqual(['systemctl', 'stop', 'zram-efficiency.service'], stop.call_args_list[0][0][0])
        launch = stop.call_args_list[1][0][0]
        self.assertIn('systemd-run', launch)
        self.assertEqual([binary, '--config', config, '--drain'], launch[-4:])
        self.assertTrue(result['unit'].startswith('zstack-memory-drain-'))
    def test_apply_request_keeps_async_service_response_as_draining(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-apply-async-')
        service, calls = self._strict_policy_service(capacity_status=202)
        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        with patch.object(plugin, '_apply_ksm_policy', return_value={}):
            response = json.loads(plugin.apply_request({'body': json.dumps({
                'action': 'apply', 'hostUuid': 'host-1',
                'operationUuid': 'apply-async-1', 'desiredRevision': 13,
                'licensePermit': {'managed': True,
                                  'operationUuid': 'managed-host-1',
                                  'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                'policy': {'ksm': {'enabled': True},
                           'zram': {'enabled': True,
                                    'logicalCapacityBytes': 8192,
                                    'ramLimitBytes': 4096}}})}))
        self.assertTrue(response['success'], response)
        self.assertEqual('Draining', response['status'])
        self.assertIsNone(response.get('appliedRevision'))
        self.assertNotEqual('apply-async-1', plugin._get_active_control())
    def test_reachable_observer_never_promotes_uncertain_mixed_or_drifted_ksm(self):
        for defect in ('unknown', 'failed', 'paused', 'hold', 'pending', 'pool',
                       'authorized', 'mode', 'stale-boot', 'native-drift', 'mixed', 'wrong-control'):
            with self.subTest(defect=defect):
                root = tempfile.mkdtemp(prefix='state-ksm-observer-negative-')
                plugin = self._ksm_only_state_plugin(root)
                command = {'hostUuid': 'host-1', 'operationUuid': 'observer-ksm',
                           'desiredRevision': 22, 'policy': {'ksm': {'enabled': True}}}
                if defect == 'mixed': command['policy']['zram'] = {'enabled': True}
                plugin._set_active_control(command['operationUuid'])
                plugin._record_operation(command, 'APPLIED', {'success': True,
                    'status': 'Succeeded', 'state': {'ksmOnly': True}})
                snapshot = {'success': True, 'status': 'Succeeded', 'state': {
                    'mode': 'observe', 'resource_authorized': False,
                    'lifecycle': {'activeState': 'compatibility', 'paused': False},
                    'host_zram': {'quality': 'unavailable', 'device': '', 'pool_generation': ''}}}
                state = snapshot['state']
                if defect == 'unknown': snapshot['status'] = 'Unknown'; snapshot['success'] = False
                if defect == 'failed': snapshot['success'] = False
                if defect == 'paused': state['lifecycle']['paused'] = True
                if defect == 'hold': state['lifecycle']['migrationHold'] = {}
                if defect == 'pending': state['pending_operations'] = ['pending']
                if defect == 'pool': state['host_zram']['pool_generation'] = 'live-pool'
                if defect == 'authorized': state['resource_authorized'] = True
                if defect == 'mode': state['mode'] = 'reclaim'
                if defect == 'wrong-control': plugin._set_active_control('another-control')
                if defect == 'stale-boot':
                    path = os.path.join(root, command['operationUuid'] + '.json')
                    with open(path) as stream: record = json.load(stream)
                    record['bootId'] = 'old-boot'
                    with open(path, 'w') as stream: json.dump(record, stream)
                native = ('run=%s\nconfigRevision=22\npages_to_scan=2000\n'
                          'sleep_millisecs=20\nuse_zero_pages=0\n' %
                          ('0' if defect == 'native-drift' else '1')).encode('ascii')
                with patch.object(plugin, '_dispatch', return_value=snapshot), \
                        patch.object(subprocess, 'check_output', return_value=native):
                    response = json.loads(plugin.state({'body': json.dumps({
                        'hostUuid': 'host-1', 'operationUuid': 'observation'})}))
                self.assertNotIn('ksmOnly', response['state'])
    def test_uncertain_recovery_reconcile_is_read_only_and_keeps_original_journal(self):
        directory = tempfile.mkdtemp(prefix='memory-recovery-reconcile-')
        self.addCleanup(shutil.rmtree, directory)
        active_path = os.path.join(directory, 'active-control')
        drain_uuid = '9' * 32
        with open(active_path, 'w') as stream:
            stream.write(drain_uuid)
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': directory,
                          'activeControlPath': active_path})
        old_uuid, recovery_uuid = 'a' * 32, 'b' * 32
        old_path = plugin._operation_path(old_uuid)
        old_bytes = json.dumps({'operationUuid': old_uuid, 'stage': 'ACTIVATING',
                                'action': 'apply', 'hostUuid': 'host-1'}).encode('utf-8')
        with open(old_path, 'wb') as stream:
            stream.write(old_bytes)
        intent = {'recoveryOperationUuid': recovery_uuid,
                  'unresolvedOperationUuid': old_uuid, 'hostUuid': 'host-1',
                  'expectedBootId': plugin._current_boot_id(),
                  'expectedPoolGeneration': 'c' * 64,
                  'drainControlOperationUuid': drain_uuid,
                  'oldActivationRequestId': 'd' * 32,
                  'oldActivationFingerprint': 'e' * 64,
                  'requestId': recovery_uuid,
                  'priorActiveControl': drain_uuid,
                  'maintenanceProof': {'oldPoolGeneration': 'c' * 64,
                      'maintenanceReady': True, 'maintenanceArchived': True,
                      'executorExited': True, 'activeOperations': 0,
                      'readyForInitialization': True, 'originalDeviceInactive': True,
                      'oldPoolOwnershipAbsent': True, 'drainOperationUuid': drain_uuid}}
        recovery_record = {'operationUuid': recovery_uuid, 'action': 'recoverUncertain',
                           'stage': 'RECOVERING', 'hostUuid': 'host-1',
                           'bootId': plugin._current_boot_id(), 'recoveryIntent': intent}
        with open(plugin._operation_path(recovery_uuid), 'w') as stream:
            json.dump(recovery_record, stream)
        retired = {'schema': 1, 'requestId': recovery_uuid,
                   'oldActivationRequestId': 'd' * 32,
                   'oldActivationFingerprint': 'e' * 64,
                   'drainControlOperationUuid': drain_uuid,
                   'bootId': plugin._current_boot_id(), 'poolGeneration': 'c' * 64,
                   'reason': 'USER_CONFIRMED_UNCERTAIN_RECOVERY', 'stage': 'RETIRED',
                   'nativeObserved': 'ZERO_INACTIVE_NO_BACKING', '_http_status': 200}
        calls = []
        def service_call(action, payload):
            calls.append(action)
            if action == 'lifecycle-activation-retirement-state':
                return retired
            if action == 'monitor-state':
                return {'active_operations': 0, 'pending_operations': [],
                        'lifecycle': {'paused': True, 'migrationHold': {}},
                        '_http_status': 200}
            raise AssertionError('reconcile must not issue mutation: %s' % action)
        plugin.service_call = service_call
        command = {'hostUuid': 'host-1', 'operationUuid': recovery_uuid}
        prior = plugin._load_operation(command)
        with patch.object(plugin, '_maintenance_recovery_proof', return_value=True):
            result = plugin._reconcile_uncertain_recovery(command, prior)
        self.assertTrue(result['success'], result)
        self.assertEqual('UNCERTAIN_RECOVERED', result['state']['phase'])
        self.assertIsNone(result['appliedRevision'])
        self.assertEqual(drain_uuid, plugin._get_active_control())
        self.assertEqual(['lifecycle-activation-retirement-state', 'monitor-state'], calls)
        with open(old_path, 'rb') as stream:
            self.assertEqual(old_bytes, stream.read())
    def test_uncertain_recovery_reconcile_without_receipt_stays_unknown(self):
        directory = tempfile.mkdtemp(prefix='memory-recovery-unknown-')
        self.addCleanup(shutil.rmtree, directory)
        active_path = os.path.join(directory, 'active-control')
        drain_uuid = '9' * 32
        with open(active_path, 'w') as stream:
            stream.write(drain_uuid)
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': directory,
                          'activeControlPath': active_path})
        op_uuid = 'b' * 32
        intent = {'recoveryOperationUuid': op_uuid, 'hostUuid': 'host-1',
                  'expectedBootId': plugin._current_boot_id(), 'requestId': 'f' * 32,
                  'oldActivationRequestId': 'd' * 32}
        prior = {'action': 'recoverUncertain', 'hostUuid': 'host-1',
                 'bootId': plugin._current_boot_id(), 'recoveryIntent': intent}
        plugin.service_call = lambda _action, _payload: {
            'success': False, 'error': 'not found', '_http_status': 404}
        result = plugin._reconcile_uncertain_recovery(
            {'hostUuid': 'host-1', 'operationUuid': op_uuid}, prior)
        self.assertFalse(result['success'])
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('RECOVERY_RETIREMENT_OBSERVATION_UNKNOWN', result['reasonCode'])
        self.assertEqual(drain_uuid, plugin._get_active_control())
    def test_uncertain_recovery_retirement_uses_control_post_and_monitor_get_routes(self):
        connections = []
        class Response(object):
            status = 200
            def read(self, _limit):
                return b'{"stage":"RETIRED"}'
        class Connection(object):
            def __init__(self, socket_path, timeout):
                self.socket_path, self.timeout = socket_path, timeout
                self.method, self.path, self.body = None, None, None
                connections.append(self)
            def request(self, method, path, body=None, headers=None):
                self.method, self.path, self.body = method, path, body
            def getresponse(self):
                return Response()
            def close(self):
                pass
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'socketPath': '/run/zram/control.sock',
                          'monitorSocketPath': '/run/zram/monitor.sock'})
        with patch.object(memory_optimization, '_UnixHTTPConnection', Connection):
            plugin._call_local_service('lifecycle-activation-retirement', {'requestId': 'new'})
            plugin._call_local_service('lifecycle-activation-retirement-state', {
                'oldActivationRequestId': 'a' * 32, 'requestId': 'b' * 32})
        self.assertEqual('/run/zram/control.sock', connections[0].socket_path)
        self.assertEqual('POST', connections[0].method)
        self.assertEqual('/v1/maintenance/activation-retirements', connections[0].path)
        self.assertEqual('/run/zram/monitor.sock', connections[1].socket_path)
        self.assertEqual('GET', connections[1].method)
        self.assertEqual('/v1/maintenance/activation-retirements/%s?requestId=%s' % (
            'a' * 32, 'b' * 32), connections[1].path)
    def test_uncertain_recovery_accepts_only_typed_missing_activation_receipt(self):
        absent = MemoryOptimizationPlugin._activation_receipt_absent
        self.assertTrue(absent({'_http_status': 404,
                                'error': 'MAINTENANCE_ACTIVATION_NOT_FOUND'}))
        self.assertTrue(absent({'_http_status': 200, 'receipt': None}))
        self.assertFalse(absent({'_http_status': 404, 'error': 'NOT_FOUND'}))
        self.assertFalse(absent({'_http_status': 503,
                                 'error': 'MAINTENANCE_ACTIVATION_NOT_FOUND'}))
        self.assertFalse(absent({'_http_status': 200}))
        self.assertFalse(absent({'_http_status': 200, 'receipt': {}}))
        self.assertFalse(absent({'_http_status': 404,
                                 'error': 'MAINTENANCE_ACTIVATION_NOT_FOUND',
                                 'receipt': {'stage': 'APPLIED'}}))
    def test_activation_status_service_request_passes_only_typed_absence(self):
        plugin = MemoryOptimizationPlugin()
        command = {'requestId': 'a' * 32}
        plugin.service_call = lambda action, payload: {
            '_http_status': 404, 'error': 'MAINTENANCE_ACTIVATION_NOT_FOUND'}
        result = plugin._service_request('lifecycle-activation-state', command)
        self.assertTrue(plugin._activation_receipt_absent(result))

        for response in (
                {'_http_status': 404, 'error': 'NOT_FOUND'},
                {'_http_status': 500, 'error': 'MAINTENANCE_ACTIVATION_NOT_FOUND'},
                {'_http_status': 404, 'error': 'MAINTENANCE_ACTIVATION_NOT_FOUND',
                 'receipt': {'stage': 'APPLIED'}}):
            plugin.service_call = lambda action, payload, response=response: response
            with self.assertRaises(RuntimeError):
                plugin._service_request('lifecycle-activation-state', command)

        plugin.service_call = lambda action, payload: {
            '_http_status': 404, 'error': 'MAINTENANCE_ACTIVATION_NOT_FOUND'}
        with self.assertRaises(RuntimeError):
            plugin._service_request('lifecycle-activation-retirement-state', command)
    def test_activation_status_transport_accepts_agent_camel_case_request_id(self):
        connections = []
        class Response(object):
            status = 404
            def read(self, _limit):
                return b'{"error":"MAINTENANCE_ACTIVATION_NOT_FOUND"}'
        class Connection(object):
            def __init__(self, socket_path, timeout):
                self.socket_path, self.timeout = socket_path, timeout
                self.method, self.path = None, None
                connections.append(self)
            def request(self, method, path, body=None, headers=None):
                self.method, self.path = method, path
            def getresponse(self):
                return Response()
            def close(self):
                pass
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'socketPath': '/run/zram/control.sock'})
        with patch.object(memory_optimization, '_UnixHTTPConnection', Connection):
            result = plugin._call_local_service('lifecycle-activation-state', {
                'requestId': 'a' * 32})
        self.assertEqual('GET', connections[0].method)
        self.assertEqual('/v1/lifecycle/maintenance-activation?request_id=%s' % ('a' * 32),
                         connections[0].path)
        self.assertTrue(plugin._activation_receipt_absent(result))
    def test_uncertain_recovery_posts_once_and_preserves_original_unknown_journal(self):
        plugin, command, evidence, calls, old_path, old_bytes = self._uncertain_recovery_fixture()
        with patch.object(plugin, '_validate_uncertain_activation', return_value=(evidence, None)), \
                patch.object(plugin, '_maintenance_recovery_proof', return_value=True):
            result = json.loads(plugin.apply_request({'body': json.dumps(command)}))
        self.assertTrue(result['success'], result)
        self.assertEqual('UNCERTAIN_RECOVERED', result['state']['phase'])
        self.assertEqual(plugin._current_boot_id(), result['bootId'])
        self.assertEqual('9' * 32, result['state']['lastConfirmedOperationUuid'])
        self.assertEqual(plugin._current_boot_id(), result['state']['bootId'])
        self.assertTrue(result['state']['maintenanceProof']['maintenanceReady'])
        self.assertTrue(result['state']['maintenanceProof']['maintenanceArchived'])
        self.assertTrue(result['state']['maintenanceProof']['executorExited'])
        self.assertEqual('9' * 32,
                         result['state']['maintenanceProof']['drainOperationUuid'])
        self.assertEqual(command['operationUuid'], calls[0][1]['requestId'])
        self.assertEqual('Unknown', result['state']['recoveryProof']['originalOutcome'])
        self.assertEqual('9' * 32, plugin._get_active_control())
        self.assertEqual(['lifecycle-activation-retirement', 'monitor-state'],
                         [action for action, _payload in calls])
        with open(old_path, 'rb') as stream:
            self.assertEqual(old_bytes, stream.read())
        record = plugin._load_operation(command)
        self.assertEqual('APPLIED', record['stage'])
        self.assertEqual('recoverUncertain', record['action'])
        calls_before_replay = list(calls)
        replay = json.loads(plugin.apply_request({'body': json.dumps(command)}))
        self.assertTrue(replay['success'], replay)
        self.assertEqual(calls_before_replay, calls, 'same recovery request repeated Go mutation')
        changed = json.loads(json.dumps(command))
        changed['recovery']['expectedPoolGeneration'] = 'd' * 64
        refused = json.loads(plugin.apply_request({'body': json.dumps(changed)}))
        self.assertFalse(refused['success'])
        self.assertEqual(calls_before_replay, calls,
                         'same operation UUID with a changed request hash caused a Go mutation')
    def test_uncertain_recovery_lost_post_response_does_not_release_old_control(self):
        plugin, command, evidence, calls, old_path, old_bytes = self._uncertain_recovery_fixture(
            post_fails=True)
        with patch.object(plugin, '_validate_uncertain_activation', return_value=(evidence, None)):
            result = plugin.apply(command)
        self.assertFalse(result['success'])
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('RECOVERY_RETIREMENT_RESULT_UNKNOWN', result['reasonCode'])
        self.assertEqual('9' * 32, plugin._get_active_control())
        self.assertEqual(['lifecycle-activation-retirement'],
                         [action for action, _payload in calls])
        calls_before_retry = list(calls)
        retry = plugin.apply(command)
        self.assertEqual('Unknown', retry['status'])
        self.assertEqual(calls_before_retry, calls, 'RECOVERING retry repeated Go mutation')
        with open(old_path, 'rb') as stream:
            self.assertEqual(old_bytes, stream.read())
    def test_uncertain_recovery_reconcile_completes_after_fence_advanced_journal_failure(self):
        plugin, command, evidence, calls, old_path, old_bytes = \
            self._uncertain_recovery_fixture(prior_active_old=True)
        original_update = plugin._update_operation_record
        def fail_applied_once(operation_uuid, stage, result=None):
            if stage == 'APPLIED':
                return False
            return original_update(operation_uuid, stage, result)
        with patch.object(plugin, '_validate_uncertain_activation', return_value=(evidence, None)), \
                patch.object(plugin, '_maintenance_recovery_proof', return_value=True), \
                patch.object(plugin, '_update_operation_record', side_effect=fail_applied_once):
            first = plugin.apply(command)
        self.assertEqual('Unknown', first['status'])
        self.assertEqual('9' * 32, plugin._get_active_control())
        self.assertEqual(['lifecycle-activation-retirement', 'monitor-state'],
                         [action for action, _payload in calls])
        prior = plugin._load_operation(command)
        with patch.object(plugin, '_maintenance_recovery_proof', return_value=True):
            result = plugin._reconcile_uncertain_recovery(command, prior)
        self.assertTrue(result['success'], result)
        self.assertEqual('UNCERTAIN_RECOVERED', result['state']['phase'])
        self.assertEqual('9' * 32, plugin._get_active_control())
        self.assertEqual(['lifecycle-activation-retirement', 'monitor-state',
                          'lifecycle-activation-retirement-state', 'monitor-state'],
                         [action for action, _payload in calls])
        with open(old_path, 'rb') as stream:
            self.assertEqual(old_bytes, stream.read())
    def test_uncertain_recovery_rejects_nonhost_scope_and_unknown_fields(self):
        for mutate in (
                lambda command: command.update({'scope': 'VM'}),
                lambda command: command['recovery'].update({'unexpected': True}),
                lambda command: command.update({'unexpected': True})):
            with self.subTest(mutate=mutate):
                plugin, command, _evidence, calls, _old_path, _old_bytes = \
                    self._uncertain_recovery_fixture()
                mutate(command)
                with patch.object(plugin, '_validate_uncertain_activation',
                                  side_effect=AssertionError('must reject before evidence reads')):
                    result = plugin.apply(command)
                self.assertFalse(result['success'])
                self.assertEqual('RECOVERY_REQUEST_INVALID', result['reasonCode'])
                self.assertEqual([], calls)
    def test_uncertain_recovery_preflight_rejection_is_durable_and_read_only(self):
        plugin, command, _evidence, calls, old_path, old_bytes = \
            self._uncertain_recovery_fixture()
        with patch.object(plugin, '_validate_uncertain_activation',
                          return_value=(None, 'RECOVERY_OLD_ACTIVATION_UNQUALIFIED')):
            result = plugin.apply(command)
        self.assertFalse(result['success'])
        self.assertEqual('Failed', result['status'])
        self.assertEqual('RECOVERY_OLD_ACTIVATION_UNQUALIFIED', result['reasonCode'])
        self.assertIsNone(result.get('appliedRevision'))
        self.assertEqual('RECOVERY_NOT_ISSUED', result['state']['phase'])
        proof = result['state']['recoveryRejectionProof']
        self.assertEqual(command['operationUuid'], proof['recoveryOperationUuid'])
        self.assertEqual(command['expectedControlOperationUuid'],
                         proof['unresolvedOperationUuid'])
        self.assertEqual(command['recovery']['drainControlOperationUuid'],
                         proof['drainControlOperationUuid'])
        self.assertEqual(command['recovery']['expectedPoolGeneration'],
                         proof['expectedPoolGeneration'])
        self.assertTrue(proof['notIssued'])
        self.assertEqual([], calls, 'preflight rejection must not call Go retirement')
        prior = plugin._load_operation(command)
        self.assertEqual('REJECTED', prior['stage'])
        self.assertNotIn('recoveryIntent', prior)
        with patch.object(plugin, '_service_request',
                          side_effect=AssertionError('reconcile must be read-only')):
            reconciled = plugin._reconcile_uncertain_recovery(command, prior)
        self.assertEqual(result, reconciled)
        replay = plugin.apply(command)
        self.assertEqual(result, replay)
        self.assertEqual([], calls)
        with open(old_path, 'rb') as stream:
            self.assertEqual(old_bytes, stream.read())
    def test_uncertain_recovery_rejection_journal_failure_stays_unknown(self):
        plugin, command, _evidence, calls, old_path, old_bytes = \
            self._uncertain_recovery_fixture()
        original_record = plugin._record_operation
        def fail_rejection(operation, stage, result=None):
            if stage == 'REJECTED':
                return False
            return original_record(operation, stage, result)
        with patch.object(plugin, '_validate_uncertain_activation',
                          return_value=(None, 'RECOVERY_OLD_ACTIVATION_UNQUALIFIED')), \
                patch.object(plugin, '_record_operation', side_effect=fail_rejection):
            result = plugin.apply(command)
        self.assertFalse(result['success'])
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('RECOVERY_REJECTION_JOURNAL_UNAVAILABLE', result['reasonCode'])
        self.assertEqual('PREPARING', plugin._load_operation(command)['stage'])
        self.assertEqual([], calls)
        with open(old_path, 'rb') as stream:
            self.assertEqual(old_bytes, stream.read())

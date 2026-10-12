"""Memory optimization first_use behavior tests.

Migrated from the legacy Agent test module; all methods remain discovered by pytest.
"""

from tests.unit.kvmagent.memory_optimization_test_support import *
from tests.unit.kvmagent.memory_optimization_test_support import _OMIT_POLICY_MODE
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.kvmagent]

class TestMemoryOptimizationFirstUse(MemoryOptimizationTestBase):
    def test_first_zram_enable_accepts_exact_factory_controller_and_fresh_current_boot(self):
        from unittest.mock import patch
        plugin, command, state, _template = self._first_use_fixture()
        responses = [dict(state), dict(state, mode='reclaim', resource_authorized=True)]
        plugin.service_call = lambda action, payload: (
            responses.pop(0) if action == 'state' else
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else
            {'revision': 1} if action == 'capacity-state' else
            {'revision': 2} if action == 'tuning-state' else {})
        identity = {'package': 'zstack-zram-1-1',
                    'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                    'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                    'templateSha256': hashlib.sha256(
                        open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
                    'pid': 111, 'processStartTime': '4', 'bootId': plugin._current_boot_id()}
        restarted_identity = dict(identity, pid=112, processStartTime='5')
        with patch.object(plugin, '_first_use_runtime_identity',
                          side_effect=[identity, restarted_identity]), \
             patch.object(plugin, '_bounded_controller_restart') as restart:
            self.assertTrue(plugin._prepare_first_zram_use(command))
        restart.assert_called_once_with()
        with open(plugin.zram_config_path) as stream:
            config = json.load(stream)
        self.assertEqual('reclaim', config['mode'])
        self.assertIs(config['resource_authorized'], True)
        self.assertIs(config['initial_efficiency_enabled'], False)
        record = plugin._load_operation(command)
        self.assertEqual('FIRST_USE_AUTHORIZING', record['stage'])
        self.assertEqual(plugin._current_boot_id(), record['firstZramUse']['bootId'])
        self.assertEqual(plugin._operation_hash(command), record['firstZramUse']['requestHash'])
        self.assertTrue(plugin._mark_first_zram_policy_started(command))
        self.assertIs(plugin._load_operation(command)['firstZramUse']['policySubmissionStarted'], True)
    def test_first_zram_enable_after_factory_install_reboot_uses_new_boot_observation(self):
        from unittest.mock import patch
        plugin, command, state, _template = self._first_use_fixture()
        prior_install_boot = plugin._current_boot_id()
        post_install_boot = '12345678-1234-1234-1234-123456789abc'
        self.assertNotEqual(prior_install_boot, post_install_boot)
        plugin._current_boot_id = lambda: post_install_boot
        record = plugin._load_operation(command)
        record['bootId'] = post_install_boot
        self.assertTrue(plugin._write_operation_record(record))
        responses = [dict(state), dict(state, mode='reclaim', resource_authorized=True)]
        plugin.service_call = lambda action, payload: (
            responses.pop(0) if action == 'state' else
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else
            {'revision': 1} if action == 'capacity-state' else
            {'revision': 2} if action == 'tuning-state' else {})
        runtime = {'package': 'zstack-zram-1-1',
                   'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                   'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                   'templateSha256': hashlib.sha256(
                       open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
                   'pid': 211, 'processStartTime': '8', 'bootId': post_install_boot}
        with patch.object(plugin, '_first_use_runtime_identity',
                          side_effect=[runtime, dict(runtime, pid=212, processStartTime='9')]), \
             patch.object(plugin, '_bounded_controller_restart') as restart:
            self.assertTrue(plugin._prepare_first_zram_use(command))
        restart.assert_called_once_with()
        self.assertEqual(post_install_boot,
                         plugin._load_operation(command)['firstZramUse']['bootId'])
    def test_first_zram_enable_rejects_user_modified_factory_config(self):
        plugin, command, _state, _template = self._first_use_fixture()
        with open(plugin.zram_config_path, 'rb') as stream:
            changed = json.loads(stream.read().decode('utf-8'))
        changed['device'] = '/dev/zram7'
        modified = json.dumps(changed, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        with open(plugin.zram_config_path, 'wb') as stream:
            stream.write(modified)
        before = open(plugin.zram_config_path, 'rb').read()
        with patch.object(plugin, '_first_use_runtime_identity',
                          side_effect=AssertionError('runtime must not authorize edited config')), \
             patch.object(plugin, '_bounded_controller_restart') as restart:
            with self.assertRaises(memory_optimization.FirstZramConfigRejected):
                plugin._prepare_first_zram_use(command)
        restart.assert_not_called()
        self.assertEqual(before, open(plugin.zram_config_path, 'rb').read())
    def test_apply_missing_first_use_config_remains_unknown_not_rejected(self):
        plugin, command = self._prepare_first_use_apply_test(missing_config=True)
        result = plugin.apply(command)
        self.assertFalse(result['success'])
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('FIRST_ZRAM_CONFIG_READ_UNKNOWN', result['reasonCode'])
        self.assertEqual('UNKNOWN', plugin._load_operation(command)['stage'])
    def test_apply_config_change_after_durable_first_use_stage_remains_unknown(self):
        from unittest.mock import patch
        plugin, command, state, _template = self._first_use_fixture()
        os.unlink(plugin._operation_path(command['operationUuid']))
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'ksm': True,
            'ksmZeroPages': True, 'zram': True, 'writeback': True}
        plugin._validate_cold_ksm_partial_fence = lambda _command: None
        plugin.service_call = lambda action, _payload: (
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else
            dict(state) if action == 'state' else
            {'revision': 1} if action == 'capacity-state' else
            {'revision': 2} if action == 'tuning-state' else {})
        identity = {'package': 'zstack-zram-1-1',
                    'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                    'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                    'templateSha256': hashlib.sha256(
                        open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
                    'pid': 111, 'processStartTime': '4',
                    'bootId': plugin._current_boot_id()}
        write_config = plugin._write_first_use_config

        def concurrent_change(target):
            with open(plugin.zram_config_path, 'rb') as stream:
                changed = json.loads(stream.read().decode('utf-8'))
            changed['device'] = '/dev/zram7'
            with open(plugin.zram_config_path, 'wb') as stream:
                stream.write(json.dumps(changed, sort_keys=True, indent=2).encode('utf-8') + b'\n')
            return write_config(target)

        with patch.object(plugin, '_first_use_runtime_identity', return_value=identity), \
                patch.object(plugin, '_write_first_use_config', side_effect=concurrent_change), \
                patch.object(plugin, '_bounded_controller_restart',
                             side_effect=AssertionError('config race must not restart controller')), \
                patch.object(plugin, '_apply_ksm_policy',
                             side_effect=AssertionError('unknown first-use must not write KSM')), \
                patch.object(plugin, '_apply_service_policy',
                             side_effect=AssertionError('unknown first-use must not write policy')):
            result = plugin.apply(command)

        self.assertFalse(result['success'])
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('FIRST_ZRAM_CONFIG_READBACK_MISMATCH', result['reasonCode'])
        persisted = plugin._load_operation(command)
        self.assertEqual('UNKNOWN', persisted['stage'])
        self.assertIsInstance(persisted.get('firstZramUse'), dict)
        self.assertEqual(hashlib.sha256(
            open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
            persisted['firstZramUse']['templateSha256'])
        self.assertIsNotNone(persisted['firstZramUse'].get('expectedConfigSha256'))
        self.assertEqual(plugin._operation_hash(command),
                         persisted['firstZramUse']['requestHash'])
    def test_first_zram_enable_rejects_host_cpu_enabled_before_any_config_write(self):
        from unittest.mock import patch
        plugin, command, state, _template = self._first_use_fixture()
        before = open(plugin.zram_config_path, 'rb').read()
        calls = []
        def service(action, payload):
            calls.append(action)
            if action == 'host-cpu-state':
                return {'efficiency_enabled': True, 'revision': 7}
            if action == 'state':
                return state
            return {'revision': 1}
        plugin.service_call = service
        with patch.object(plugin, '_first_use_runtime_identity', return_value={
                'package': 'zstack-zram-1-1',
                'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                'templateSha256': hashlib.sha256(
                    open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
                'pid': 111, 'processStartTime': '4', 'bootId': plugin._current_boot_id()}), \
             patch.object(plugin, '_bounded_controller_restart') as restart:
            with self.assertRaisesRegex(RuntimeError, 'FIRST_ZRAM_HOST_POLICY_NOT_DISABLED'):
                plugin._prepare_first_zram_use(command)
        restart.assert_not_called()
        self.assertEqual(before, open(plugin.zram_config_path, 'rb').read())
        self.assertEqual(['host-cpu-state'], calls)
    def test_first_zram_enable_allows_terminal_ksm_only_history_but_unknown_fences(self):
        from unittest.mock import patch
        plugin, command, _state, _template = self._first_use_fixture()
        os.unlink(plugin._operation_path(command['operationUuid']))
        ksm_runtime_dir = os.path.dirname(plugin.operation_dir)
        plugin.KSM_CONF = os.path.join(ksm_runtime_dir, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(ksm_runtime_dir, 'ksm.writer.lock')
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'kylinV10',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': False, 'zramReasonCode': 'ABI_INCOMPLETE', 'service': False,
        }
        ksm = {'hostUuid': 'host-1', 'scope': 'Host', 'operationUuid': '2' * 32,
               'desiredRevision': 4,
               'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                  'sleepMillis': 20, 'zeroPagesEnabled': True},
                          'zram': {'enabled': False},
                          'writeback': {'enabled': False}}}
        result = plugin.apply(ksm)
        self.assertTrue(result['success'])
        prior = plugin._load_operation(ksm)
        self.assertTrue(plugin._first_use_terminal_ksm_record(prior))
        # Installation can precede a host reboot. A durable, completed KSM
        # history remains historical evidence, while the active-control
        # entry must still match the live native acknowledgment on this boot.
        post_reboot_boot = '12345678-1234-1234-1234-123456789abc'
        plugin._current_boot_id = lambda: post_reboot_boot
        self.assertTrue(plugin._first_use_terminal_ksm_record(prior))
        self.assertTrue(plugin._record_operation(command, 'PREPARING'))
        self.assertEqual(ksm['desiredRevision'],
                         int(plugin._read_ksm_ack()['configRevision']))
        self.assertTrue(plugin._first_use_local_history_clear(command))
        plugin._test_native_ksm_simulator.sysfs['run'] = '0'
        self.assertFalse(plugin._first_use_local_history_clear(command))
        prior_policy = copy.deepcopy(prior['policy'])
        prior['policy']['zram']['logicalCapacityBytes'] = 8192
        self.assertFalse(plugin._first_use_terminal_ksm_record(prior))
        prior['policy'] = prior_policy
        unknown = {'hostUuid': 'host-1', 'operationUuid': '3' * 32}
        self.assertTrue(plugin._record_operation(unknown, 'UNKNOWN', {'status': 'Unknown'}))
        self.assertFalse(plugin._first_use_local_history_clear(command))
    def test_first_zram_enable_rejects_stale_observation_without_config_mutation(self):
        from unittest.mock import patch
        plugin, command, state, _template = self._first_use_fixture()
        before = open(plugin.zram_config_path, 'rb').read()
        state['observed_at'] = time.time() - 30
        state['host']['observed_at'] = time.time() - 30
        plugin.service_call = lambda action, payload: (
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else state)
        with patch.object(plugin, '_first_use_runtime_identity', return_value={
                'package': 'zstack-zram-1-1',
                'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                'pid': 111, 'processStartTime': '4', 'bootId': plugin._current_boot_id()}), \
             patch.object(plugin, '_bounded_controller_restart') as restart:
            with self.assertRaisesRegex(RuntimeError, 'FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE'):
                plugin._prepare_first_zram_use(command)
        restart.assert_not_called()
        self.assertEqual(before, open(plugin.zram_config_path, 'rb').read())
    def test_first_zram_enable_accepts_go_omitted_hold_and_null_pending_only(self):
        plugin, command, state, _template = self._first_use_fixture()
        state['host_cpu'] = {'efficiency_enabled': False, 'revision': 0}
        self.assertTrue(plugin._first_use_state_safe(state))
        self.assertTrue(plugin._first_use_state_safe(dict(state, pending_operations=[])))
        for bad in (
                dict(state, pending_operations=[{'id': 'unknown'}]),
                dict(state, pending_operations='null'),
                dict(state, lifecycle={'paused': False, 'activeState': 'compatibility',
                                       'schemaVersion': 1, 'abiProfile': 'zram-service-v1',
                                       'readbackAllowed': True, 'migrationHold': {}}),
                dict(state, lifecycle={'paused': False, 'activeState': 'migration_hold',
                                       'schemaVersion': 1, 'abiProfile': 'zram-service-v1',
                                       'readbackAllowed': True,
                                       'migrationHold': {'operation_id': 'old'}}),
                dict(state, lifecycle={'paused': False, 'activeState': 'compatibility',
                                       'schemaVersion': 1, 'abiProfile': 'other',
                                       'readbackAllowed': True}),
                dict(state, maintenance_blocks_activation=None),
                dict(state, host_cpu={'efficiency_enabled': True, 'revision': 0})):
            self.assertFalse(plugin._first_use_state_safe(bad))
        omitted_pending = dict(state)
        omitted_pending.pop('pending_operations')
        self.assertFalse(plugin._first_use_state_safe(omitted_pending))
    def test_first_use_rpm_verification_allows_only_generated_config_drift(self):
        from unittest.mock import patch
        import subprocess
        config = b'{"mode":"reclaim"}\n'
        with patch.object(subprocess, 'check_output', return_value=b'') as verify:
            self.assertEqual(hashlib.sha256(config).hexdigest(),
                             MemoryOptimizationPlugin._verify_first_use_rpm_files(config))
        verify.assert_called_once_with(['rpm', '-V', 'zstack-zram'], stderr=subprocess.STDOUT)
        expected_line = (b'S.5....T. c /etc/zram-memory/config.json\n')
        with patch.object(subprocess, 'check_output', side_effect=subprocess.CalledProcessError(
                1, ['rpm', '-V', 'zstack-zram'], output=expected_line)) as verify:
            MemoryOptimizationPlugin._verify_first_use_rpm_files(config)
        verify.assert_called_once_with(['rpm', '-V', 'zstack-zram'], stderr=subprocess.STDOUT)
        for return_code, output in (
                (1, b'S.5....T. c /etc/zram-memory/config.json\n/usr/bin/rpm: warning\n'),
                (1, b'S.5....T. c /usr/local/libexec/zram-efficiency\n'),
                (1, b'M.5....T. c /etc/zram-memory/config.json\n'),
                (2, b'S.5....T. c /etc/zram-memory/config.json\n')):
            with patch.object(subprocess, 'check_output', side_effect=subprocess.CalledProcessError(
                    return_code, ['rpm', '-V', 'zstack-zram'], output=output)):
                with self.assertRaisesRegex(RuntimeError,
                                            'FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH'):
                    MemoryOptimizationPlugin._verify_first_use_rpm_files(config)
        with patch.object(subprocess, 'check_output',
                          return_value=b'S.5....T.  /usr/local/libexec/zram-efficiency\n'):
            with self.assertRaisesRegex(RuntimeError, 'FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH'):
                MemoryOptimizationPlugin._verify_first_use_rpm_files(config)
    def test_first_use_restart_timeout_reaps_only_its_systemctl_process(self):
        from unittest.mock import patch
        class StuckSystemctl(object):
            def __init__(self, *args, **kwargs):
                self.returncode = None
                self.terminated = False
                self.killed = False
                self.waited = False
            def poll(self):
                return self.returncode
            def terminate(self):
                self.terminated = True
                self.returncode = -15
            def kill(self):
                self.killed = True
                self.returncode = -9
            def wait(self):
                self.waited = True
                return self.returncode
        process = StuckSystemctl()
        with patch.object(memory_optimization.subprocess, 'Popen', return_value=process) as popen:
            with self.assertRaisesRegex(RuntimeError, 'FIRST_ZRAM_RESTART_RESULT_UNKNOWN'):
                MemoryOptimizationPlugin._bounded_controller_restart(timeout_seconds=0)
        popen.assert_called_once_with(['systemctl', 'restart', 'zram-memory.service'],
                                      stdout=memory_optimization.subprocess.PIPE,
                                      stderr=memory_optimization.subprocess.PIPE)
        self.assertTrue(process.terminated)
        self.assertFalse(process.killed)
        self.assertTrue(process.waited)
    def test_first_use_reconcile_reports_configured_but_policy_not_issued_terminally(self):
        from unittest.mock import patch
        plugin, command, state, template = self._first_use_fixture()
        target = dict(template, mode='reclaim', resource_authorized=True)
        raw = json.dumps(target, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        with open(plugin.zram_config_path, 'wb') as stream:
            stream.write(raw)
        identity = {'package': 'zstack-zram-1-1',
                    'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                    'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                    'templateSha256': hashlib.sha256(
                        open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
                    'pid': 201, 'processStartTime': '9',
                    'bootId': plugin._current_boot_id()}
        ksm_ack = {'run': '0', 'configRevision': '1', 'pages_to_scan': '1250',
                   'sleep_millisecs': '10', 'use_zero_pages': '0'}
        record = plugin._load_operation(command)
        record['stage'] = plugin.FIRST_USE_AUTHORIZING_STAGE
        record['firstZramUse'] = {
            'hostUuid': 'host-1', 'bootId': plugin._current_boot_id(),
            'requestHash': plugin._operation_hash(command),
            'expectedConfigSha256': hashlib.sha256(raw).hexdigest(),
            'runtimeIdentity': identity,
            'baseline': {'capacityRevision': 1, 'cpuRevision': 0,
                         'tuningRevision': 2, 'ksmRequested': True,
                         'ksmReadback': ksm_ack, 'activeControl': ''},
        }
        self.assertTrue(plugin._write_operation_record(record))
        record = plugin._load_operation(command)
        native = dict(state, mode='reclaim', resource_authorized=True)
        plugin.service_call = lambda action, payload: (
            native if action == 'state' else
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else
            {'revision': 1} if action == 'capacity-state' else
            {'revision': 2} if action == 'tuning-state' else {})
        with patch.object(plugin, '_first_use_runtime_identity', return_value=identity), \
             patch.object(plugin, '_read_ksm_ack', return_value=ksm_ack):
            result = plugin._reconcile_first_zram_use(command, record)
        self.assertEqual('Failed', result['status'], result)
        self.assertEqual('FIRST_ZRAM_POLICY_NOT_ISSUED', result['reasonCode'])
        self.assertIs(result['firstUse']['configAuthorized'], True)
        self.assertIs(result['firstUse']['controllerRestartVerified'], True)
        self.assertIs(result['firstUse']['policyWritesIssued'], False)
        self.assertEqual('REJECTED', plugin._load_operation(command)['stage'])
    def test_first_use_reconcile_accepts_manager_wire_and_poll_observation_changes(self):
        from unittest.mock import patch
        plugin, command, state, template = self._first_use_fixture()
        target = dict(template, mode='reclaim', resource_authorized=True)
        raw = json.dumps(target, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        with open(plugin.zram_config_path, 'wb') as stream:
            stream.write(raw)
        identity = {'package': 'zstack-zram-1-1',
                    'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                    'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                    'templateSha256': hashlib.sha256(
                        open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
                    'pid': 211, 'processStartTime': '8',
                    'bootId': plugin._current_boot_id()}
        record = plugin._load_operation(command)
        record.update({'stage': plugin.FIRST_USE_AUTHORIZING_STAGE,
                       'firstZramUse': {
                           'hostUuid': 'host-1', 'bootId': plugin._current_boot_id(),
                           'requestHash': plugin._operation_hash(command),
                           'expectedConfigSha256': hashlib.sha256(raw).hexdigest(),
                           'runtimeIdentity': identity,
                           'baseline': {'capacityRevision': 1, 'cpuRevision': 0,
                                        'tuningRevision': 2, 'ksmRequested': False,
                                        'activeControl': ''}}})
        self.assertTrue(plugin._write_operation_record(record))
        original_apply_record = plugin._load_operation(command)
        native = dict(state, mode='reclaim', resource_authorized=True)
        plugin.service_call = lambda action, _payload: (
            native if action == 'state' else
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else
            {'revision': 1} if action == 'capacity-state' else
            {'revision': 2} if action == 'tuning-state' else {})

        def manager_reconcile(task_submitted_at, observed_boot_id):
            request = dict(command)
            request.update({'action': 'reconcile', 'policy': {},
                            'desiredRevision': task_submitted_at + 1,
                            'reconcileAction': 'seal-if-never-issued',
                            'taskSubmittedAt': task_submitted_at,
                            'bootId': observed_boot_id,
                            'sampleTime': task_submitted_at + 20})
            return request

        with patch.object(plugin, '_first_use_runtime_identity', return_value=identity):
            first_result = plugin._reconcile_first_zram_use(
                manager_reconcile(100, 'observed-boot-a'), original_apply_record)
            self.assertEqual('Failed', first_result['status'], first_result)
            terminal_bytes = open(plugin._operation_path(command['operationUuid']), 'rb').read()
            polled_result = plugin._reconcile_first_zram_use(
                manager_reconcile(200, 'observed-boot-b'), original_apply_record)

        self.assertEqual(first_result, polled_result)
        self.assertEqual('FIRST_ZRAM_POLICY_NOT_ISSUED', polled_result['reasonCode'])
        self.assertEqual(terminal_bytes,
                         open(plugin._operation_path(command['operationUuid']), 'rb').read())
    def test_first_use_reconcile_never_retires_policy_submission_unknown(self):
        plugin, command, _state, _template = self._first_use_fixture()
        record = plugin._load_operation(command)
        record['stage'] = 'UNKNOWN'
        record['firstZramUse'] = {'hostUuid': 'host-1',
                                  'bootId': plugin._current_boot_id(),
                                  'requestHash': plugin._operation_hash(command),
                                  'policySubmissionStarted': True}
        self.assertTrue(plugin._write_operation_record(record))
        record = plugin._load_operation(command)
        result = plugin._reconcile_first_zram_use(command, record)
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('FIRST_ZRAM_POLICY_OUTCOME_UNKNOWN', result['reasonCode'], result)
        self.assertEqual('UNKNOWN', plugin._load_operation(command)['stage'])
    def test_first_use_reconcile_returns_newer_applied_receipt_after_lock(self):
        from unittest.mock import patch
        plugin, command, _state, _template = self._first_use_fixture()
        prior = plugin._load_operation(command)
        prior['stage'] = plugin.FIRST_USE_AUTHORIZING_STAGE
        prior['firstZramUse'] = {
            'hostUuid': 'host-1', 'bootId': plugin._current_boot_id(),
            'requestHash': plugin._operation_hash(command),
            'expectedConfigSha256': 'a' * 64,
            'policySubmissionStarted': False}
        self.assertTrue(plugin._write_operation_record(prior))
        stale = copy.deepcopy(plugin._load_operation(command))
        acquire = plugin._acquire_host_control_lock
        readback = {'success': True, 'status': 'Succeeded', 'appliedRevision': 1}

        def writer_completes_before_reconcile_lock():
            lock = acquire()
            advanced = plugin._load_operation(command)
            advanced.update({'stage': 'APPLIED', 'readback': readback,
                             'applyEvidence': {'submitted': True}})
            self.assertTrue(plugin._write_operation_record(advanced))
            return lock

        with patch.object(plugin, '_acquire_host_control_lock',
                          side_effect=writer_completes_before_reconcile_lock):
            result = plugin._reconcile_first_zram_use(command, stale)
        self.assertEqual(readback, result)
        persisted = plugin._load_operation(command)
        self.assertEqual('APPLIED', persisted['stage'])
        self.assertEqual(readback, persisted['readback'])
        self.assertEqual({'submitted': True}, persisted['applyEvidence'])
    def test_first_use_reconcile_lock_busy_does_not_mutate_journal(self):
        from unittest.mock import patch
        plugin, command, _state, _template = self._first_use_fixture()
        prior = plugin._load_operation(command)
        prior['stage'] = plugin.FIRST_USE_AUTHORIZING_STAGE
        prior['firstZramUse'] = {
            'hostUuid': 'host-1', 'bootId': plugin._current_boot_id(),
            'requestHash': plugin._operation_hash(command),
            'policySubmissionStarted': False}
        self.assertTrue(plugin._write_operation_record(prior))
        stale = plugin._load_operation(command)
        before = open(plugin._operation_path(command['operationUuid']), 'rb').read()
        with patch.object(plugin, '_acquire_host_control_lock',
                          side_effect=IOError('writer already owns host lock')):
            result = plugin._reconcile_first_zram_use(command, stale)
        self.assertEqual('Unknown', result['status'])
        self.assertEqual(before, open(plugin._operation_path(command['operationUuid']), 'rb').read())
    def test_first_use_reconcile_terminal_receipt_keeps_same_boot_fence(self):
        from unittest.mock import patch
        plugin, command, _state, _template = self._first_use_fixture()
        prior = plugin._load_operation(command)
        prior['stage'] = plugin.FIRST_USE_AUTHORIZING_STAGE
        prior['firstZramUse'] = {
            'hostUuid': 'host-1', 'bootId': plugin._current_boot_id(),
            'requestHash': plugin._operation_hash(command),
            'policySubmissionStarted': False}
        self.assertTrue(plugin._write_operation_record(prior))
        stale = plugin._load_operation(command)
        acquire = plugin._acquire_host_control_lock

        def completed_after_reboot():
            lock = acquire()
            advanced = plugin._load_operation(command)
            advanced.update({'stage': 'APPLIED', 'bootId': 'previous-boot',
                             'readback': {'success': True, 'status': 'Succeeded'}})
            self.assertTrue(plugin._write_operation_record(advanced))
            return lock

        with patch.object(plugin, '_acquire_host_control_lock', side_effect=completed_after_reboot):
            result = plugin._reconcile_first_zram_use(command, stale)
        self.assertEqual('Unknown', result['status'])
        persisted = plugin._load_operation(command)
        self.assertEqual('APPLIED', persisted['stage'])
        self.assertEqual('previous-boot', persisted['bootId'])
    def test_first_use_reconcile_wrong_host_does_not_return_other_host_terminal(self):
        from unittest.mock import patch
        plugin, original_command, _state, _template = self._first_use_fixture()
        prior = plugin._load_operation(original_command)
        prior['stage'] = plugin.FIRST_USE_AUTHORIZING_STAGE
        prior['firstZramUse'] = {
            'hostUuid': 'host-1', 'bootId': plugin._current_boot_id(),
            'requestHash': plugin._operation_hash(original_command),
            'policySubmissionStarted': False}
        self.assertTrue(plugin._write_operation_record(prior))
        stale = plugin._load_operation(original_command)
        command = dict(original_command, hostUuid='other-host', action='reconcile', policy={})
        acquire = plugin._acquire_host_control_lock
        terminal_bytes = []
        readback = {'success': True, 'status': 'Succeeded', 'appliedRevision': 1}

        def writer_completes_before_reconcile_lock():
            lock = acquire()
            advanced = plugin._load_operation(original_command)
            advanced.update({'stage': 'APPLIED', 'readback': readback,
                             'applyEvidence': {'submitted': True}})
            self.assertTrue(plugin._write_operation_record(advanced))
            terminal_bytes.append(open(
                plugin._operation_path(original_command['operationUuid']), 'rb').read())
            return lock

        with patch.object(plugin, '_acquire_host_control_lock',
                          side_effect=writer_completes_before_reconcile_lock):
            result = plugin._reconcile_first_zram_use(command, stale)
        self.assertEqual('Unknown', result['status'])
        self.assertEqual('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN', result['reasonCode'])
        self.assertEqual(terminal_bytes[0], open(
            plugin._operation_path(original_command['operationUuid']), 'rb').read())
        self.assertEqual(readback, plugin._load_operation(original_command)['readback'])
    def test_first_use_reconcile_preserves_newer_policy_started_phase(self):
        from unittest.mock import patch
        plugin, command, _state, _template = self._first_use_fixture()
        prior = plugin._load_operation(command)
        prior['stage'] = plugin.FIRST_USE_AUTHORIZING_STAGE
        prior['firstZramUse'] = {
            'hostUuid': 'host-1', 'bootId': plugin._current_boot_id(),
            'requestHash': plugin._operation_hash(command),
            'expectedConfigSha256': 'a' * 64,
            'policySubmissionStarted': False}
        self.assertTrue(plugin._write_operation_record(prior))
        stale = copy.deepcopy(plugin._load_operation(command))
        acquire = plugin._acquire_host_control_lock

        def original_writer_advances_to_policy_started():
            lock = acquire()
            advanced = plugin._load_operation(command)
            advanced['firstZramUse']['policySubmissionStarted'] = True
            advanced['firstZramUse']['policySubmissionAt'] = 123
            self.assertTrue(plugin._write_operation_record(advanced))
            return lock

        with patch.object(plugin, '_acquire_host_control_lock',
                          side_effect=original_writer_advances_to_policy_started):
            result = plugin._reconcile_first_zram_use(command, stale)
        self.assertEqual('Unknown', result['status'])
        persisted_bytes = open(plugin._operation_path(command['operationUuid']), 'rb').read()
        persisted = json.loads(persisted_bytes.decode('utf-8'))
        self.assertEqual('FIRST_USE_AUTHORIZING', persisted['stage'])
        self.assertIs(persisted['firstZramUse']['policySubmissionStarted'], True)
        self.assertEqual(123, persisted['firstZramUse']['policySubmissionAt'])
    def test_first_use_reconcile_identity_check_never_overwrites_concurrent_apply_receipt(self):
        from unittest.mock import patch
        plugin, command, _state, template = self._first_use_fixture()
        config = dict(template, mode='reclaim', resource_authorized=True)
        config_bytes = json.dumps(config, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        with open(plugin.zram_config_path, 'wb') as stream:
            stream.write(config_bytes)
        identity = {'package': 'zstack-zram-1-1',
                    'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                    'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                    'templateSha256': hashlib.sha256(
                        open(plugin.zram_config_template_path, 'rb').read()).hexdigest(),
                    'pid': 311, 'processStartTime': '12',
                    'bootId': plugin._current_boot_id()}
        stale = plugin._load_operation(command)
        stale['stage'] = 'UNKNOWN'
        stale['firstZramUse'] = {
            'hostUuid': 'host-1', 'bootId': plugin._current_boot_id(),
            'requestHash': plugin._operation_hash(command),
            'expectedConfigSha256': hashlib.sha256(config_bytes).hexdigest(),
            'runtimeIdentity': identity, 'policySubmissionStarted': True}
        self.assertTrue(plugin._write_operation_record(stale))
        stale_snapshot = copy.deepcopy(stale)

        # Model the original writer completing after reconcile loaded its
        # UNKNOWN snapshot but before the read-only runtime identity check.
        advanced = copy.deepcopy(stale)
        advanced.update({'stage': 'APPLIED', 'readback': {
            'success': True, 'status': 'Succeeded', 'appliedRevision': 1},
            'applyEvidence': {'capacity': {'revision': 3},
                              'tuning': {'revision': 4},
                              'submittedAt': 123}})
        self.assertTrue(plugin._write_operation_record(advanced))
        expected = open(plugin._operation_path(command['operationUuid']), 'rb').read()
        with patch.object(plugin, '_first_use_runtime_identity', return_value=identity):
            self.assertTrue(plugin._verify_first_use_runtime_for_policy_reconcile(stale_snapshot))
        self.assertEqual(expected, open(plugin._operation_path(command['operationUuid']), 'rb').read())
        persisted = plugin._load_operation(command)
        self.assertEqual('APPLIED', persisted['stage'])
        self.assertIn('applyEvidence', persisted)
    def test_apply_exception_after_first_use_marker_preserves_receipt_and_reconciles_read_only(self):
        from unittest.mock import patch
        plugin, command, state, _template = self._first_use_fixture()
        os.unlink(plugin._operation_path(command['operationUuid']))
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
        post = dict(state, mode='reclaim', resource_authorized=True)
        state_responses = [dict(state), post]
        plugin.service_call = lambda action, payload: (
            {'efficiency_enabled': False, 'revision': 0} if action == 'host-cpu-state' else
            state_responses.pop(0) if action == 'state' else
            {'revision': 1} if action == 'capacity-state' else
            {'revision': 2} if action == 'tuning-state' else {})
        template_sha = hashlib.sha256(open(plugin.zram_config_template_path, 'rb').read()).hexdigest()
        initial = {'package': 'zstack-zram-1-1',
                   'unitPath': '/usr/lib/systemd/system/zram-memory.service',
                   'unitSha256': 'u' * 64, 'binarySha256': 'b' * 64,
                   'templateSha256': template_sha,
                   'pid': 111, 'processStartTime': '4', 'bootId': plugin._current_boot_id()}
        activated = dict(initial, pid=112, processStartTime='5')
        with patch.object(plugin, '_first_use_runtime_identity',
                          side_effect=[initial, activated]), \
             patch.object(plugin, '_bounded_controller_restart'), \
             patch.object(plugin, '_apply_service_policy',
                          side_effect=RuntimeError('SERVICE_APPLY_RESULT_UNKNOWN')):
            response = plugin.apply(command)
        self.assertEqual('Unknown', response['status'])
        failed_record = plugin._load_operation(command)
        self.assertEqual('UNKNOWN', failed_record['stage'])
        receipt = failed_record['firstZramUse']
        self.assertIs(receipt['policySubmissionStarted'], True)
        self.assertEqual(hashlib.sha256(
            open(plugin.zram_config_path, 'rb').read()).hexdigest(),
            receipt['expectedConfigSha256'])
        self.assertEqual(activated, receipt['activatedIdentity'])

        # A reconstructed Agent may run only the ordinary readback reconciler
        # after verifying the exact first-use runtime identity. It must not
        # re-enter the policy writer or discard the immutable authorization
        # receipt while changing the operation stage/readback.
        restarted = MemoryOptimizationPlugin()
        restarted.configure({'hostUuid': 'host-1', 'operationDir': plugin.operation_dir})
        restarted.zram_config_path = plugin.zram_config_path
        restarted.zram_config_template_path = plugin.zram_config_template_path
        restarted._load_host_uuid = lambda: 'host-1'
        restarted._current_boot_id = lambda: receipt['bootId']
        with patch.object(restarted, '_first_use_runtime_identity', return_value=activated), \
             patch.object(restarted, '_read_policy_state', return_value={
                 'complete': True, 'phase': 'READBACK'}), \
             patch.object(restarted, '_capacity_apply_evidence', return_value={
                 'verified': True}), \
             patch.object(restarted, '_apply_service_policy',
                          side_effect=AssertionError('reconcile must never replay policy writes')):
            readback = json.loads(restarted.reconcile({
                memory_optimization.http.REQUEST_BODY: json.dumps(command)}))
        self.assertEqual('Succeeded', readback['status'])
        final_record = restarted._load_operation(command)
        self.assertEqual('APPLIED', final_record['stage'])
        self.assertEqual(receipt, final_record['firstZramUse'])
    def test_non_enable_and_vm_requests_do_not_trigger_first_use(self):
        plugin, command, _state, _template = self._first_use_fixture()
        self.assertFalse(plugin._first_zram_enable_requested(dict(command, scope='VM')))
        disabled = dict(command, policy={'zram': {'enabled': False}})
        self.assertFalse(plugin._prepare_first_zram_use(disabled))
        ksm_only = dict(command, policy={'ksm': {'enabled': True}})
        self.assertFalse(plugin._prepare_first_zram_use(ksm_only))
    def test_backend_maintenance_unknown_pool_never_becomes_first_use_none(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: {})
        plugin.host_uuid = 'host-1'
        inventory = self._maintenance_inventory()
        with patch.object(plugin, '_read_backend_maintenance_receipt',
                          return_value=(None, 'unavailable')), \
                patch.object(plugin, '_service_unit_stopped', return_value=True), \
                patch.object(plugin, '_first_use_no_pool_verified', return_value=False), \
                patch.object(plugin, '_has_unresolved_operation_journal', return_value=False), \
                patch.object(plugin, '_get_active_control', return_value=None):
            result = plugin._decorate_backend_maintenance_inventory(
                inventory, None, {'hostUuid': 'host-1'}, 'service unavailable')
        self.assertIsNone(result['poolGeneration'])
        self.assertFalse(result['canPrepare'])
        self.assertIn('POOL_GENERATION_UNKNOWN', result['preparationReasons'])
        self.assertIn('BACKEND_MAINTENANCE_STATUS_UNKNOWN', result['preparationReasons'])
    def test_backend_maintenance_first_use_requires_explicit_local_no_pool_proof(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: {})
        plugin.host_uuid = 'host-1'
        inventory = self._maintenance_inventory()
        with patch.object(plugin, '_read_backend_maintenance_receipt',
                          return_value=({'stage': 'NOT_STARTED'}, None)), \
                patch.object(plugin, '_service_unit_stopped', return_value=True), \
                patch.object(plugin, '_first_use_no_pool_verified', return_value=True), \
                patch.object(plugin, '_has_unresolved_operation_journal', return_value=False), \
                patch.object(plugin, '_get_active_control', return_value=None):
            result = plugin._decorate_backend_maintenance_inventory(
                inventory, None, {'hostUuid': 'host-1'})
        self.assertEqual('none', result['poolGeneration'])
        self.assertTrue(result['canPrepare'])
        self.assertEqual([], result['preparationReasons'])

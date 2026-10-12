from unittest import TestCase
import copy
import json
import hashlib
import os
import errno
import socket
import subprocess
import shutil
import tempfile
import threading
import subprocess
import time
import sys
from pathlib import Path
try:
    from mock import patch
except ImportError:
    from unittest.mock import patch

from kvmagent.plugins import memory_optimization
from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin

WRITEBACK_RESOURCE_UUID = 'a' * 32
WRITEBACK_FINGERPRINT = 'b' * 64
WRITEBACK_BOOT_ID = 'test-boot-id'
WRITEBACK_DEVICE = '/dev/vdb'
WRITEBACK_CAPACITY = 20 * 1024 * 1024 * 1024
_OMIT_POLICY_MODE = object()


def writeback_service_views(observed_at=None):
    if observed_at is None:
        observed_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time()))
    status = {'backend_resource': {
        'resource_uuid': WRITEBACK_RESOURCE_UUID,
        'capacity_bytes': WRITEBACK_CAPACITY,
        'fingerprint': WRITEBACK_FINGERPRINT,
        'state': 'PREPARED', 'active': False, 'observed_at': observed_at,
    }}
    detail = {
        'configured': {'device': WRITEBACK_DEVICE},
        'claimed': True,
        'identity_qualified': True,
        'ownership_generation': WRITEBACK_RESOURCE_UUID,
        'effective': {'identity': {
            'boot_id': WRITEBACK_BOOT_ID,
            'canonical_device': WRITEBACK_DEVICE,
            'rdev': 64784,
            'node_inode': 101,
            'sysfs_inode': 303,
            'capacity_bytes': WRITEBACK_CAPACITY,
        }},
    }
    return status, detail


def writeback_probe_inventory(candidate_changes=None, host_uuid='host-1', boot_id=WRITEBACK_BOOT_ID):
    candidate = {
        'resourceUuid': WRITEBACK_RESOURCE_UUID,
        'fingerprint': WRITEBACK_FINGERPRINT,
        'identity': WRITEBACK_FINGERPRINT,
        'state': 'PREPARED',
        'eligible': True,
        'writebackReady': True,
        'capacityBytes': WRITEBACK_CAPACITY,
        'hostBootId': WRITEBACK_BOOT_ID,
        'type': 'block',
        'device': WRITEBACK_DEVICE,
        'stableIdentity': {
            'bootId': WRITEBACK_BOOT_ID,
            'device': WRITEBACK_DEVICE,
            'capacityBytes': WRITEBACK_CAPACITY,
            'sysfsInode': '303',
        },
        'reasons': [],
    }
    candidate.update(candidate_changes or {})
    return {'hostUuid': host_uuid, 'bootId': boot_id, 'status': 'AVAILABLE',
            'candidates': [candidate], 'reasons': []}


class ServiceTimeout(Exception):
    pass


class TestMemoryOptimizationPlugin(TestCase):
    def _first_use_fixture(self, state=None):
        directory = tempfile.mkdtemp(prefix='first-zram-use-')
        self.addCleanup(shutil.rmtree, directory)
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
        operation_directory = os.path.join(directory, 'operations')
        os.makedirs(operation_directory)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_directory})
        config_directory = os.path.join(directory, 'etc-config')
        os.makedirs(config_directory)
        plugin.zram_config_path = os.path.join(config_directory, 'config.json')
        plugin.zram_config_template_path = os.path.join(config_directory, 'vendor-config.json')
        template = {
            'version': 2, 'mode': 'observe', 'managed': True,
            'resource_authorized': False, 'initial_efficiency_enabled': False,
            'vm_selection': 'all_running', 'vm_uuids': [],
            'state_dir': '/var/lib/zram-efficiency',
            'monitor_socket': '/run/zram-efficiency-admission/monitor.sock',
            'control_socket': '/run/zram-efficiency-admission/control.sock',
            'device': '/dev/zram0', 'internal_rule': {}, 'budget': {},
        }
        raw = json.dumps(template, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        with open(plugin.zram_config_path, 'wb') as stream:
            stream.write(raw)
        with open(plugin.zram_config_template_path, 'wb') as stream:
            stream.write(raw)
        with open(plugin.active_control_path, 'w') as stream:
            stream.write('')
        command = {'hostUuid': 'host-1', 'scope': 'Host', 'operationUuid': '1' * 32,
                   'desiredRevision': 1, 'policy': {'zram': {'enabled': True,
                   'logicalCapacityBytes': 8192, 'ramLimitBytes': 4096}}}
        plugin._record_operation(command, 'PREPARING')
        now = time.time()
        pool = {'pool_generation': '', 'device': '', 'quality': 'unavailable',
                'reason': 'NO_QUALIFIED_MANAGED_POOL:HOST_POLICY_DISABLED'}
        base = {'mode': 'observe', 'resource_authorized': False,
                'observed_at': now, 'host': {'observed_at': now,
                'qualified': True, 'safe': True},
                # Exact Go wire shape: nil MigrationHold is omitted and an
                # empty []PendingOperation is JSON null, not [] or absent.
                'lifecycle': {'schemaVersion': 1, 'abiProfile': 'zram-service-v1',
                              'activeState': 'compatibility', 'desiredRevision': 0,
                              'readbackAllowed': True, 'paused': False},
                'maintenance_blocks_activation': False, 'pending_operations': None,
                'host_zram': pool}
        if state:
            base.update(state)
        return plugin, command, base, template

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
        from unittest.mock import patch
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

    def _prepare_first_use_apply_test(self, missing_config=False):
        plugin, command, _state, _template = self._first_use_fixture()
        # The helper seeds a PREPARING record for direct-method tests; this
        # apply-level path must let apply create its own initial receipt.
        os.unlink(plugin._operation_path(command['operationUuid']))
        if missing_config:
            os.unlink(plugin.zram_config_path)
        else:
            with open(plugin.zram_config_path, 'rb') as stream:
                changed = json.loads(stream.read().decode('utf-8'))
            changed['device'] = '/dev/zram7'
            with open(plugin.zram_config_path, 'wb') as stream:
                stream.write(json.dumps(changed, sort_keys=True, indent=2).encode('utf-8') + b'\n')
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'ksm': True,
            'ksmZeroPages': True, 'zram': True, 'writeback': True}
        plugin._validate_cold_ksm_partial_fence = lambda _command: None
        return plugin, command

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
        plugin.KSM_SCRIPT = os.path.join(ksm_runtime_dir, 'ksmtuned-zstack')
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'kylinV10',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': False, 'zramReasonCode': 'ABI_INCOMPLETE', 'service': False,
        }
        plugin._prepare_managed_ksm_ownership = lambda: None
        ksm = {'hostUuid': 'host-1', 'scope': 'Host', 'operationUuid': '2' * 32,
               'desiredRevision': 4,
               'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                  'sleepMillis': 20, 'zeroPagesEnabled': True},
                          'zram': {'enabled': False},
                          'writeback': {'enabled': False}}}
        native = b'run=1\nconfigRevision=4\npages_to_scan=2000\n' \
                 b'sleep_millisecs=20\nuse_zero_pages=1\n'
        ksm_ack = {'run': '1', 'configRevision': '4', 'pages_to_scan': '2000',
                   'sleep_millisecs': '20', 'use_zero_pages': '1'}
        with patch.object(subprocess, 'check_output', return_value=native):
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
        with patch.object(plugin, '_read_ksm_ack', return_value=ksm_ack):
            self.assertTrue(plugin._first_use_local_history_clear(command))
        with patch.object(plugin, '_read_ksm_ack', return_value=dict(ksm_ack, run='0')):
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

    def _strict_policy_service(self, capacity_status=200, initial_cpu_enabled=False):
        calls = []
        # The Go policy store uses one host revision for both capacity and
        # CPU. Tuning has its own revision domain.
        host_revision = [1]
        capacity = {'revision': host_revision[0], 'desired': {
            'configured': {'logical_capacity': {'bytes': 8192},
                           'physical_memory_limit': {'bytes': 4096}},
            'logical_resolved_bytes': 16384, 'physical_resolved_bytes': 8192},
            'effective_logical_bytes': 8192, 'effective_physical_limit_bytes': 4096,
            'apply_state': 'APPLIED', 'reason': 'NATIVE_CONFIGURATION_VERIFIED'}
        cpu = {'revision': host_revision[0], 'efficiency_enabled': initial_cpu_enabled,
               'idle_cpu_threshold_percent': 80, 'idle_duration_seconds': 60}
        tuning = {'revision': 1, 'settings': {
            'vm_management': {'revision': 0, 'mode': 'all_running', 'vm_uuids': []},
            'writeback': {'enabled': False}}}

        def response(action, value, status=200):
            return dict(copy.deepcopy(value), status='Succeeded', _http_status=status)

        def service(action, payload):
            calls.append((action, payload))
            if action == 'capacity-state':
                capacity['revision'] = host_revision[0]
                return response(action, capacity)
            if action == 'host-cpu-state':
                cpu['revision'] = host_revision[0]
                return response(action, cpu)
            if action == 'tuning-state':
                return response(action, tuning)
            if action == 'capacity':
                if payload.get('expected_revision') != host_revision[0]:
                    return response(action, {'error': 'REVISION_CONFLICT'}, 409)
                host_revision[0] += 1
                capacity['revision'] = host_revision[0]
                capacity['desired']['configured'] = {
                    'logical_capacity': {'bytes': payload['logical_capacity']['bytes']},
                    'physical_memory_limit': {'bytes': payload['physical_memory_limit']['bytes']}}
                capacity['desired']['logical_resolved_bytes'] = payload['logical_capacity']['bytes']
                capacity['desired']['physical_resolved_bytes'] = payload['physical_memory_limit']['bytes']
                if capacity_status == 202:
                    capacity.update({'apply_state': 'BLOCKED',
                                     'reason': 'NATIVE_POOL_UNQUALIFIED'})
                else:
                    capacity.update({'apply_state': 'APPLIED',
                                     'reason': 'NATIVE_CONFIGURATION_VERIFIED'})
                    capacity['effective_logical_bytes'] = capacity['desired']['configured'][
                        'logical_capacity']['bytes']
                    capacity['effective_physical_limit_bytes'] = capacity['desired']['configured'][
                        'physical_memory_limit']['bytes']
                # CapacityStatus has no request_id in the Go ABI; Agent binds
                # the response to the request in its durable local receipt.
                return response(action, capacity, capacity_status)
            if action == 'host-cpu':
                if payload.get('expected_revision') != host_revision[0]:
                    return response(action, {'error': 'REVISION_CONFLICT'}, 409)
                host_revision[0] += 1
                cpu.update({'revision': host_revision[0],
                            'efficiency_enabled': payload['efficiency_enabled'],
                            'idle_cpu_threshold_percent': payload['idle_cpu_threshold_percent'],
                            'idle_duration_seconds': payload['idle_duration_seconds']})
                return response(action, dict(cpu, request_id=payload['request_id']))
            if action == 'apply':
                if payload.get('expected_revision') != tuning['revision']:
                    return response(action, {'error': 'REVISION_CONFLICT'}, 409)
                tuning.update({'revision': tuning['revision'] + 1,
                               'settings': payload['settings']})
                # The synchronous tuning response also omits request_id;
                # Agent records its own durable request binding.
                return response(action, tuning)
            return response(action, {'revision': 0})
        return service, calls

    def _rejected_resume_fixture(self):
        directory = tempfile.mkdtemp(prefix='memory-rejected-resume-')
        self.addCleanup(shutil.rmtree, directory)
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: self.fail('native call forbidden'))
        plugin.configure({'hostUuid': 'host-1', 'operationDir': directory})
        anchor = {'operationUuid': 'drain-before-resume', 'action': 'drain',
                  'hostUuid': 'host-1', 'scope': 'Host', 'desiredRevision': 7}
        rejected = {'operationUuid': 'rejected-resume', 'action': 'resume',
                    'hostUuid': 'host-1', 'scope': 'Host', 'desiredRevision': 7,
                    'expectedControlOperationUuid': anchor['operationUuid']}
        self.assertTrue(plugin._record_operation(anchor, 'APPLIED',
                        {'success': True, 'status': 'Succeeded'}))
        self.assertTrue(plugin._record_operation(rejected, 'REJECTED',
                        {'reason': 'CONTROL_OPERATION_FENCED'}))
        plugin._set_active_control(anchor['operationUuid'])
        command = {'hostUuid': 'host-1', 'operationUuid': rejected['operationUuid'],
                   'reconcileAction': 'verify-rejected-resume',
                   'expectedControlOperationUuid': anchor['operationUuid']}
        return plugin, directory, command

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

    def _maintenance_inventory(self, **changes):
        now = time.time()
        stable = {
            'bootId': WRITEBACK_BOOT_ID,
            'device': WRITEBACK_DEVICE,
            'majorMinor': '252:16',
            'capacityBytes': WRITEBACK_CAPACITY,
            'sysfsPath': '/sys/devices/pci0000:00/virtio3/block/vdb',
            'sysfsInode': '303',
            'rdev': 64784,
            'nodeInode': 101,
        }
        candidate = {
            'identity': 'candidate:' + WRITEBACK_FINGERPRINT,
            'type': 'block', 'eligible': True,
            'state': 'NEEDS_OFFLINE_PREPARATION', 'writebackReady': False,
            'capacityBytes': WRITEBACK_CAPACITY, 'hostBootId': WRITEBACK_BOOT_ID,
            'stableIdentity': stable,
        }
        inventory = {
            'hostUuid': 'host-1', 'bootId': WRITEBACK_BOOT_ID,
            'observedAt': now, 'poolGeneration': 'none', 'canPrepare': True,
            'candidates': [candidate], 'preparationReasons': [],
        }
        inventory.update(changes)
        return inventory

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

    def test_writeback_candidates_merge_readonly_resource_and_identity_snapshots(self):
        calls = []
        def service(action, command):
            calls.append(action)
            if action == 'backend-state':
                return {'backend_resource': {'resource_uuid': 'owned-resource'}}
            return {'configured': {'device': '/dev/vdb'}, 'identity_qualified': True,
                    'ownership_generation': 'owned-resource', 'effective': {'identity': {'boot_id': 'boot'}}}
        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.host_uuid = 'host-1'
        command = {'hostUuid': 'host-1'}
        with patch.object(plugin, '_request_body', return_value=command), \
             patch.object(plugin, '_reply', side_effect=lambda result: result), \
             patch.object(memory_optimization, 'probe_writeback_backends', return_value={
                 'hostUuid': 'host-1', 'status': 'AVAILABLE', 'candidates': []}) as probe:
            result = plugin.writeback_backends({})
        self.assertTrue(result['success'])
        self.assertEqual(['backend-state', 'backend-view'], calls)
        self.assertEqual('owned-resource', probe.call_args[0][1]['backend_resource']['resource_uuid'])
        self.assertEqual({'device': '/dev/vdb'}, probe.call_args[0][2])

    def test_writeback_discovery_does_not_use_another_hosts_identity(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: self.fail('must not query service'))
        plugin.host_uuid = 'host-1'
        with patch.object(plugin, '_request_body', return_value={'hostUuid': 'host-2'}), \
             patch.object(plugin, '_reply', side_effect=lambda result: result), \
             patch.object(memory_optimization, 'probe_writeback_backends') as probe:
            result = plugin.writeback_backends({})
        self.assertFalse(result['success'])
        self.assertEqual('HOST_IDENTITY_UNKNOWN', result['reason'])
        probe.assert_not_called()

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

    def test_ksm_validation_matches_native_representable_bounds(self):
        for bad in ({'sleepMillis': 1}, {'sleepMillis': 9}, {'sleepMillis': 1 << 32},
                    {'pagesToScan': 1 << 32}, {'enabled': 'true'}, {'zeroPagesEnabled': 1}):
            with self.assertRaises(ValueError):
                MemoryOptimizationPlugin._validate_policy({'ksm': bad})
        MemoryOptimizationPlugin._validate_policy({'ksm': {'sleepMillis': 10, 'pagesToScan': (1 << 32) - 1}})

    def test_state_does_not_bypass_prometheus_for_presentation_metrics(self):
        def collect_memory_optimization_statistics():
            self.fail('Control state must not collect presentation metrics directly')
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: {})
        with patch.object(memory_optimization.kvmagent, 'metric_collectors',
                          [collect_memory_optimization_statistics]), \
             patch.object(plugin, '_libvirt_vm_generations', return_value=({}, True)):
            result = plugin._enrich_state({'savings': {'sampleTime': 123},
                                           'state': {'savings': {'sampleTime': 123}}})
        self.assertNotIn('savings', result)
        self.assertNotIn('savings', result['state'])

    def test_native_canonical_identity_matches_product_uuid_without_changing_generation(self):
        compact = '03d98313faa24670a0944b10da8d1ac2'
        canonical = '03d98313-faa2-4670-a094-4b10da8d1ac2'
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: {
            'identities': {canonical: {'uuid': canonical, 'instance_generation': 'opaque-fence',
                                       'start_time': 18446744073709551615}}})
        with patch.object(plugin, '_libvirt_vm_generations', return_value=({compact: {}}, True)):
            inventory, complete = plugin._complete_vm_inventory({})
        self.assertTrue(complete)
        self.assertEqual('opaque-fence', inventory[compact]['instanceGeneration'])
        self.assertEqual('18446744073709551615', inventory[compact]['identity']['start_time'])

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

    def test_identity_failure_is_present_unknown_not_absence_or_old_generation(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: {})
        with patch.object(plugin, '_libvirt_vm_generations', return_value=(
                {'vm-1': {'instanceGeneration': 'vm-1:42'}}, True)):
            inventory, complete = plugin._complete_vm_inventory({})
        self.assertTrue(complete)
        self.assertIn('vm-1', inventory)
        self.assertNotIn('instanceGeneration', inventory['vm-1'])
        with patch.object(plugin, '_libvirt_vm_generations', return_value=({}, False)):
            inventory, complete = plugin._complete_vm_inventory({'vm-1': {}})
        self.assertFalse(complete)
        self.assertIn('vm-1', inventory)

    def test_identity_batches_use_byte_budget_without_vm_count_limit(self):
        calls = []
        def service(action, payload):
            self.assertEqual('vm-identities', action)
            self.assertLessEqual(len(json.dumps(payload).encode('utf-8')), 250)
            calls.append(payload['vm_uuids'])
            return {'identities': dict((key, {'uuid': key,
                                              'instance_generation': 'native-' + key})
                                       for key in payload['vm_uuids'])}
        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.request_bytes = 250
        ids = dict(('vm-%s' % index, {}) for index in range(1025))
        with patch.object(plugin, '_libvirt_vm_generations', return_value=(ids, True)):
            inventory, complete = plugin._complete_vm_inventory({})
        self.assertTrue(complete)
        self.assertEqual(1025, len(inventory))
        self.assertEqual(1025, sum(len(batch) for batch in calls))
        self.assertTrue(all(value.get('instanceGeneration') for value in inventory.values()))

    def test_partial_ksm_update_preserves_existing_other_fields_and_disabled_state(self):
        plugin = MemoryOptimizationPlugin()
        with tempfile.TemporaryDirectory() as directory:
            plugin.KSM_CONF = os.path.join(directory, 'ksmtuned.conf')
            with open(plugin.KSM_CONF, 'w') as stream:
                stream.write('CONFIG_REVISION=2\nKSM_PAGES_TO_SCAN=1250\n'
                             'KSM_SLEEP_MILLISECS=10\nKSM_ZERO_PAGES=1\n')
            published = []
            before = b'run=0\nconfigRevision=2\nuse_zero_pages=1\npages_to_scan=1250\nsleep_millisecs=10\n'
            after = b'run=0\nconfigRevision=3\nuse_zero_pages=1\npages_to_scan=1300\nsleep_millisecs=10\n'
            calls = []
            def output(args):
                calls.append(args)
                return after if published else before
            with patch.object(plugin, '_publish_ksm_config', side_effect=published.append), \
                 patch.object(plugin, '_prepare_managed_ksm_ownership'), \
                 patch.object(subprocess, 'check_output', side_effect=output):
                plugin._apply_ksm_policy({'desiredRevision': 3,
                                         'policy': {'ksm': {'pagesToScan': 1300}}})
            self.assertIn('KSM_PAGES_TO_SCAN=1300', published[0])
            self.assertIn('KSM_SLEEP_MILLISECS=10', published[0])
            self.assertIn('KSM_ZERO_PAGES=1', published[0])
            self.assertIn(['systemctl', 'enable', plugin.MANAGED_KSM_UNIT], calls)
            self.assertIn(['systemctl', 'start', plugin.MANAGED_KSM_UNIT], calls)
            self.assertNotIn(['systemctl', 'stop', plugin.MANAGED_KSM_UNIT], calls)
            self.assertNotIn(['systemctl', 'disable', plugin.MANAGED_KSM_UNIT], calls)

    def test_ksm_policy_rejects_removed_strategy_fields(self):
        plugin = MemoryOptimizationPlugin()
        for field, value in (('mode', 'Active'),
                             ('profileVersion', 'active-v1'),
                             ('cpuBudgetPercent', 20)):
            with self.assertRaises(ValueError, msg=field):
                plugin._validate_policy({'ksm': {field: value}})

    def test_ksm_policy_accepts_only_four_public_fields(self):
        plugin = MemoryOptimizationPlugin()
        plugin._validate_policy({'ksm': {
            'enabled': True,
            'zeroPagesEnabled': True,
            'pagesToScan': 2000,
            'sleepMillis': 20,
        }})

    def test_ksm_apply_maps_four_fields_without_cpu_feedback_or_mode(self):
        plugin = MemoryOptimizationPlugin()
        plugin.KSM_CONF = '/tmp/ksm-test.conf'
        command = {'operationUuid': 'ksm-four-fields', 'desiredRevision': 7,
                   'policy': {'ksm': {'enabled': True,
                                      'zeroPagesEnabled': True,
                                      'pagesToScan': 2000,
                                      'sleepMillis': 20}}}
        published = []
        with patch.object(plugin, '_publish_ksm_config',
                          side_effect=lambda content: published.append(content)), \
             patch.object(plugin, '_prepare_managed_ksm_ownership'), \
             patch.object(subprocess, 'check_output',
                          return_value=b'run=1\nconfigRevision=7\n'
                                        b'use_zero_pages=1\npages_to_scan=2000\nsleep_millisecs=20\n'):
            plugin._apply_ksm_policy(command)
        self.assertEqual(1, len(published))
        self.assertIn('KSM_PAGES_TO_SCAN=2000', published[0])
        self.assertIn('KSM_SLEEP_MILLISECS=20', published[0])
        self.assertIn('KSM_ZERO_PAGES=1', published[0])
        self.assertNotIn('KSM_CPU_BUDGET_PERCENT', published[0])

    def test_ksm_ownership_snapshots_then_masks_both_native_writers(self):
        plugin = MemoryOptimizationPlugin()
        with tempfile.TemporaryDirectory() as directory:
            plugin.KSM_SCRIPT = os.path.join(directory, 'wrapper')
            plugin.KSM_SNAPSHOT = os.path.join(directory, 'legacy.state')
            with open(plugin.KSM_SNAPSHOT, 'w') as stream:
                stream.write('schema=2\n'
                             'native_ksm_present=1\nnative_ksm_enabled=enabled\n'
                             'native_ksm_active=inactive\n'
                             'native_ksmtuned_present=1\nnative_ksmtuned_enabled=static\n'
                             'native_ksmtuned_active=active\n')
            calls = []
            enabled_reads = {'ksm.service': 0, 'ksmtuned.service': 0}
            def command(args, **kwargs):
                calls.append(args)
                if args[:2] == ['systemctl', 'is-enabled']:
                    unit = args[-1]
                    enabled_reads[unit] += 1
                    if enabled_reads[unit] > 1:
                        return b'masked'
                    return b'enabled' if unit == 'ksm.service' else b'static'
                if args[:2] == ['systemctl', 'is-active']:
                    return b'inactive'
                return b''
            with patch.object(subprocess, 'check_output', side_effect=command):
                plugin._prepare_managed_ksm_ownership()
            self.assertEqual([[plugin.KSM_SCRIPT, 'takeover'],
                              ['systemctl', 'is-enabled', 'ksm.service'],
                              ['systemctl', 'mask', 'ksm.service'],
                              ['systemctl', 'is-enabled', 'ksm.service'],
                              ['systemctl', 'is-active', 'ksm.service'],
                              ['systemctl', 'is-enabled', 'ksmtuned.service'],
                              ['systemctl', 'mask', 'ksmtuned.service'],
                              ['systemctl', 'is-enabled', 'ksmtuned.service'],
                              ['systemctl', 'is-active', 'ksmtuned.service'],
                              ['systemctl', 'daemon-reload']], calls)

    def test_ksm_ownership_preserves_native_preexisting_mask(self):
        plugin = MemoryOptimizationPlugin()
        with tempfile.TemporaryDirectory() as directory:
            plugin.KSM_SCRIPT = os.path.join(directory, 'wrapper')
            plugin.KSM_SNAPSHOT = os.path.join(directory, 'legacy.state')
            with open(plugin.KSM_SNAPSHOT, 'w') as stream:
                stream.write('schema=2\n'
                             'native_ksm_present=1\nnative_ksm_enabled=masked\n'
                             'native_ksm_active=inactive\n'
                             'native_ksmtuned_present=0\nnative_ksmtuned_enabled=not-found\n'
                             'native_ksmtuned_active=not-found\n')
            calls = []
            def command(args, **kwargs):
                calls.append(args)
                if args[:2] == ['systemctl', 'show']:
                    return b'LoadState=not-found'
                if args[:2] == ['systemctl', 'is-enabled']:
                    return b'masked'
                if args[:2] == ['systemctl', 'is-active']:
                    return b'inactive'
                return b''
            with patch.object(subprocess, 'check_output', side_effect=command):
                plugin._prepare_managed_ksm_ownership()
            self.assertEqual([[plugin.KSM_SCRIPT, 'takeover'],
                              ['systemctl', 'is-enabled', 'ksm.service'],
                              ['systemctl', 'is-enabled', 'ksm.service'],
                              ['systemctl', 'is-active', 'ksm.service'],
                              ['systemctl', 'show', '-p', 'LoadState', 'ksmtuned.service'],
                              ['systemctl', 'daemon-reload']], calls)

    def test_ksm_ownership_fails_closed_on_native_readback_mismatch(self):
        plugin = MemoryOptimizationPlugin()
        with tempfile.TemporaryDirectory() as directory:
            plugin.KSM_SCRIPT = os.path.join(directory, 'wrapper')
            plugin.KSM_SNAPSHOT = os.path.join(directory, 'legacy.state')
            with open(plugin.KSM_SNAPSHOT, 'w') as stream:
                stream.write('schema=2\n'
                             'native_ksm_present=1\nnative_ksm_enabled=enabled\n'
                             'native_ksm_active=inactive\n'
                             'native_ksmtuned_present=0\nnative_ksmtuned_enabled=not-found\n'
                             'native_ksmtuned_active=not-found\n')
            enabled_reads = [0]
            def command(args, **kwargs):
                if args[:2] == ['systemctl', 'is-enabled']:
                    enabled_reads[0] += 1
                    return b'enabled' if enabled_reads[0] == 1 else b'masked'
                if args[:2] == ['systemctl', 'is-active']:
                    return b'active'
                return b''
            with patch.object(subprocess, 'check_output', side_effect=command):
                with self.assertRaisesRegex(ValueError,
                                            'KSM_NATIVE_UNIT_READBACK_MISMATCH:ksm.service:is-active:inactive:active'):
                    plugin._prepare_managed_ksm_ownership()

    def test_ksm_ownership_mask_conflict_is_precise_and_keeps_snapshot(self):
        plugin = MemoryOptimizationPlugin()
        with tempfile.TemporaryDirectory() as directory:
            plugin.KSM_SCRIPT = os.path.join(directory, 'wrapper')
            plugin.KSM_SNAPSHOT = os.path.join(directory, 'legacy.state')
            with open(plugin.KSM_SNAPSHOT, 'w') as stream:
                stream.write('schema=2\n'
                             'native_ksm_present=1\nnative_ksm_enabled=enabled\n'
                             'native_ksm_active=active\n'
                             'native_ksmtuned_present=0\nnative_ksmtuned_enabled=not-found\n'
                             'native_ksmtuned_active=not-found\n')
            def command(args, **kwargs):
                if args[:2] == ['systemctl', 'show']:
                    return b'LoadState=not-found'
                if args[:2] == ['systemctl', 'is-enabled']:
                    return b'enabled'
                if args == ['systemctl', 'mask', 'ksm.service']:
                    raise subprocess.CalledProcessError(1, args, output=b'File exists')
                return b''
            with patch.object(subprocess, 'check_output', side_effect=command):
                with self.assertRaisesRegex(ValueError,
                                            'KSM_NATIVE_UNIT_MASK_CONFLICT:ksm.service:File exists'):
                    plugin._prepare_managed_ksm_ownership()
            self.assertTrue(os.path.isfile(plugin.KSM_SNAPSHOT))

    def test_ksm_ownership_rejects_unit_that_appears_after_snapshot(self):
        plugin = MemoryOptimizationPlugin()
        with tempfile.TemporaryDirectory() as directory:
            plugin.KSM_SCRIPT = os.path.join(directory, 'wrapper')
            plugin.KSM_SNAPSHOT = os.path.join(directory, 'legacy.state')
            with open(plugin.KSM_SNAPSHOT, 'w') as stream:
                stream.write('schema=2\n'
                             'native_ksm_present=0\nnative_ksm_enabled=not-found\n'
                             'native_ksm_active=not-found\n'
                             'native_ksmtuned_present=0\nnative_ksmtuned_enabled=not-found\n'
                             'native_ksmtuned_active=not-found\n')
            calls = []
            def command(args, **kwargs):
                calls.append(args)
                if args[:2] == ['systemctl', 'show']:
                    return b'LoadState=loaded'
                return b''
            with patch.object(subprocess, 'check_output', side_effect=command):
                with self.assertRaisesRegex(ValueError,
                                            'KSM_NATIVE_UNIT_READBACK_MISMATCH:ksm.service:LoadState:not-found:loaded'):
                    plugin._prepare_managed_ksm_ownership()
            self.assertEqual([[plugin.KSM_SCRIPT, 'takeover'],
                              ['systemctl', 'show', '-p', 'LoadState', 'ksm.service']], calls)

    def test_release_facts_accept_helix_without_internal_release_label(self):
        identify = MemoryOptimizationPlugin.host_release_from_os_release
        for version in ('8.4', '8.4r'):
            facts = 'ID="helix"\nVERSION_ID="%s"\nVERSION="%s (Green Obsidian)"' % (version, version)
            self.assertEqual('h84r', identify(facts))
            self.assertEqual('unknown', identify(facts.replace('helix', 'rocky') + '\n# h84r'))
        self.assertEqual('unknown', identify('ID=rocky\nVERSION_ID=8.4\nZSTACK_RELEASE=h84r'))
        self.assertEqual('unknown', identify('ID=helix\nVERSION_ID=7.9\nVERSION="Green Obsidian"'))
        self.assertEqual('unknown', identify('ID=helix\nVERSION_ID="8.4'))

    def test_release_facts_accept_qualified_alinux4_and_kylin_v10(self):
        identify = MemoryOptimizationPlugin.host_release_from_os_release
        self.assertEqual('alinux4', identify('ID=alinux\nVERSION_ID="4"\n'))
        self.assertEqual('kylinV10', identify('ID=kylin\nVERSION_ID="V10"\n'))
        self.assertEqual('unknown', identify('ID=alinux\nVERSION_ID="3"\n'))

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

    def setUp(self):
        # These tests exercise policy flow on the test workstation, not its
        # host ABI.  Unsupported-host behavior is covered explicitly below.
        self.capability_patch = patch.object(
            MemoryOptimizationPlugin, 'discover_capabilities',
            return_value={'supported': True, 'reasonCode': 'SUPPORTED',
                          'ksm': True, 'ksmZeroPages': True,
                          'zram': True, 'writeback': True})
        self.capability_patch.start()
        self.addCleanup(self.capability_patch.stop)
        self.ksm_engine_dir = tempfile.mkdtemp(prefix='ksm-engine-')
        self.addCleanup(lambda: __import__('shutil').rmtree(self.ksm_engine_dir,
                                                            ignore_errors=True))
        engine_source = os.path.abspath(os.path.join(os.path.dirname(__file__),
            '../../ansible/memory-optimization/ksmtuned/upstream-src-ksmtuned.sh.in'))
        self.ksm_engine = os.path.join(self.ksm_engine_dir, 'ksmtuned-upstream')
        __import__('shutil').copyfile(engine_source, self.ksm_engine)
        os.chmod(self.ksm_engine, 0o755)

    def test_capability_rejects_unknown_os_or_non_4k_hosts(self):
        plugin = MemoryOptimizationPlugin()

        unsupported = plugin.capabilities_from_facts(
            release='rl84', arch='x86_64', page_size=4096,
            kernel='4.18.0-553.162.1', module_loaded=True,
            service_ready=True)
        self.assertFalse(unsupported['supported'])
        self.assertEqual('UNSUPPORTED_OS_RELEASE', unsupported['reasonCode'])

        unsupported_page = plugin.capabilities_from_facts(
            release='h84r', arch='x86_64', page_size=65536,
            kernel='4.18.0-553.162.1', module_loaded=True,
            service_ready=True)
        self.assertFalse(unsupported_page['supported'])
        self.assertEqual('UNSUPPORTED_PAGE_SIZE', unsupported_page['reasonCode'])

    def test_capability_matrix_accepts_supported_x86_releases_and_gates_zram(self):
        for release in ('h84r', 'alinux4', 'kylinV10'):
            result = MemoryOptimizationPlugin.capabilities_from_facts(
                release=release, arch='x86_64', page_size=4096,
                kernel='6.6.102', module_loaded=True, service_ready=True,
                interfaces={'ksm_run': True, 'ksm_pages_to_scan': True,
                            'ksm_sleep_millisecs': True, 'zram_mm_stat': True,
                            'cgroupv2': True, 'memory_reclaim': True,
                            'zram_writeback': True})
            self.assertTrue(result['supported'])
            self.assertTrue(result['zram'])
        gated = MemoryOptimizationPlugin.capabilities_from_facts(
            release='alinux4', arch='x86_64', page_size=4096,
            kernel='6.6.102', module_loaded=True, service_ready=True,
            interfaces={'ksm_run': True, 'ksm_pages_to_scan': True,
                        'ksm_sleep_millisecs': True, 'zram_mm_stat': True,
                        'cgroupv2': False, 'memory_reclaim': False})
        self.assertTrue(gated['supported'])
        self.assertFalse(gated['zram'])
        self.assertFalse(MemoryOptimizationPlugin.capabilities_from_facts(
            'alinux4', 'aarch64', 4096, '6.6', True, True)['supported'])

    def test_host_uuid_comes_from_existing_connect_handshake(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {'status': 'Succeeded'})
        shared_config = {}
        plugin.configure(shared_config)
        shared_config[memory_optimization.kvmagent.HOST_UUID] = 'connected-host'
        self.assertEqual('connected-host', plugin._load_host_uuid())

    def test_capability_requires_verified_kernel_and_service(self):
        plugin = MemoryOptimizationPlugin()
        result = plugin.capabilities_from_facts(
            release='h84r', arch='x86_64', page_size=4096,
            kernel='unknown', module_loaded=False, service_ready=False)
        self.assertFalse(result['supported'])
        self.assertEqual('CAPABILITY_UNKNOWN', result['reasonCode'])

    def test_capability_rejects_incomplete_kernel_abi(self):
        result = MemoryOptimizationPlugin.capabilities_from_facts(
            release='h84r', arch='x86_64', page_size=4096,
            kernel='4.18.0-553.162.1', module_loaded=True, service_ready=True,
            interfaces={'ksm_run': True, 'ksm_pages_to_scan': True,
                        'ksm_sleep_millisecs': True, 'zram_mm_stat': False})
        self.assertFalse(result['supported'])
        self.assertEqual('ABI_INCOMPLETE', result['reasonCode'])

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

    def test_service_payload_does_not_send_ksm_to_zram_service(self):
        payload = MemoryOptimizationPlugin._service_payload(
            'apply', {'operationUuid': 'op-1', 'expectedRevision': 2,
                      'policy': {'ksm': {'enabled': True, 'pagesToScan': 500},
                                 'zram': {'hostFloorBytes': 123},
                                 'writeback': {'enabled': False}}})
        self.assertNotIn('ksm', payload)
        self.assertEqual(123, payload['settings']['host_floor_bytes'])

    def test_backend_maintenance_finalize_maps_to_real_service_contract(self):
        self.assertEqual({'request_id': 'maintenance-finalize-2'},
            MemoryOptimizationPlugin._service_payload(
                'backend-maintenance-finalize', {'requestId': 'maintenance-finalize-2'}))

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

    def test_vm_efficiency_handler_reaches_service_instead_of_ksm_only_shortcut(self):
        operation_dir = tempfile.mkdtemp(prefix='vm-efficiency-')
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
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'vmBindingDir': operation_dir})
        response = json.loads(plugin.vm_efficiency({'body': json.dumps({
            'action': 'bind', 'hostUuid': 'host-1', 'operationUuid': 'vm-bind-1',
            'resourceUuid': 'vm-1', 'expectedInstanceGeneration': 'gen-1',
            'participation': 'allow',
            'desiredRevision': 3,
            'licensePermit': {'managed': True,
                              'operationUuid': 'managed-host-1',
                              'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30}})}))
        self.assertTrue(response['success'])
        self.assertEqual(['vm-policy-state', 'vm-policy'], [item[0] for item in calls])
        self.assertEqual('vm-1', calls[1][1]['_resource_uuid'])
        self.assertEqual('gen-1', calls[1][1]['expected_instance_generation'])

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

    def test_prepared_backend_requires_both_raw_service_views_and_live_identity_probe(self):
        status, detail = writeback_service_views()
        calls = []

        def service(action, payload):
            calls.append((action, payload))
            return status if action == 'backend-state' else detail

        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.host_uuid = 'host-1'
        command = {'hostUuid': 'host-1', 'policy': {'writeback': {
            'enabled': True, 'backendResourceUuid': WRITEBACK_RESOURCE_UUID,
            'backendCapacityBytes': WRITEBACK_CAPACITY}}}
        inventory = writeback_probe_inventory()
        with patch.object(memory_optimization, 'probe_writeback_backends',
                          return_value=inventory) as probe, \
             patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID):
            plugin._validate_backend_resource(command)
        self.assertEqual(['backend-state', 'backend-view'], [item[0] for item in calls])
        self.assertEqual({'hostUuid': 'host-1'}, calls[0][1])
        self.assertEqual(status['backend_resource'],
                         probe.call_args[0][1]['backend_resource'])
        self.assertEqual(detail['configured'], probe.call_args[0][2])
        self.assertEqual('host-1', probe.call_args[0][0])
        self.assertEqual(WRITEBACK_BOOT_ID, probe.call_args[0][1]['effective']['identity']['boot_id'])

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

    def test_backend_service_failure_and_unqualified_identity_fail_closed(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: (_ for _ in ()).throw(RuntimeError('offline')))
        plugin.host_uuid = 'host-1'
        command = {'hostUuid': 'host-1', 'policy': {'writeback': {
            'enabled': True, 'backendResourceUuid': WRITEBACK_RESOURCE_UUID}}}
        # Read-only backend preflight transport failure is an unknown
        # observation, not a definitive policy rejection. Actual data-plane
        # request errors are classified independently after this check.
        with self.assertRaisesRegex(RuntimeError, 'BACKEND_SERVICE_OBSERVATION_UNAVAILABLE'):
            plugin._validate_backend_resource(command)

        status, detail = writeback_service_views()
        detail['identity_qualified'] = False
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
                                          status if action == 'backend-state' else detail)
        plugin.host_uuid = 'host-1'
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
             patch.object(memory_optimization, 'probe_writeback_backends') as probe:
            with self.assertRaisesRegex(ValueError, 'BACKEND_RESOURCE_IDENTITY_UNQUALIFIED'):
                plugin._validate_backend_resource(command)
        probe.assert_not_called()

        status, detail = writeback_service_views()
        detail['effective']['identity']['boot_id'] = 'previous-boot'
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
                                          status if action == 'backend-state' else detail)
        plugin.host_uuid = 'host-1'
        with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
             patch.object(memory_optimization, 'probe_writeback_backends') as probe:
            with self.assertRaisesRegex(ValueError, 'BACKEND_RESOURCE_BOOT_ID_MISMATCH'):
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

    def test_backend_probe_must_return_same_host_boot_resource_capacity_fingerprint_and_identity(self):
        cases = (
            ({'hostUuid': 'other-host'}, 'BACKEND_RESOURCE_HOST_MISMATCH'),
            ({'bootId': 'other-boot'}, 'BACKEND_RESOURCE_BOOT_ID_MISMATCH'),
            ({'eligible': False, 'reasons': ['SYSTEM_OR_MOUNTED_DEVICE']},
             'SYSTEM_OR_MOUNTED_DEVICE'),
            ({'writebackReady': False}, 'BACKEND_RESOURCE_NOT_ACTIVE'),
            ({'fingerprint': 'c' * 64, 'identity': 'c' * 64},
             'BACKEND_RESOURCE_FINGERPRINT_MISMATCH'),
            ({'capacityBytes': WRITEBACK_CAPACITY + 1}, 'BACKEND_CAPACITY_MISMATCH'),
            ({'device': '/dev/vdc'}, 'BACKEND_RESOURCE_IDENTITY_MISMATCH'),
            ({'stableIdentity': {'bootId': WRITEBACK_BOOT_ID, 'device': WRITEBACK_DEVICE,
                                 'capacityBytes': WRITEBACK_CAPACITY, 'sysfsInode': '999'}},
             'BACKEND_RESOURCE_IDENTITY_MISMATCH'),
        )
        for changes, expected in cases:
            with self.subTest(changes=changes):
                status, detail = writeback_service_views()
                plugin = MemoryOptimizationPlugin(service_call=lambda action, payload:
                                                  status if action == 'backend-state' else detail)
                plugin.host_uuid = 'host-1'
                inventory = writeback_probe_inventory()
                inventory.update({key: value for key, value in changes.items()
                                  if key in ('hostUuid', 'bootId')})
                inventory['candidates'][0].update({key: value for key, value in changes.items()
                                                   if key not in ('hostUuid', 'bootId')})
                command = {'hostUuid': 'host-1', 'policy': {'writeback': {
                    'enabled': True, 'backendResourceUuid': WRITEBACK_RESOURCE_UUID}}}
                with patch.object(plugin, '_current_boot_id', return_value=WRITEBACK_BOOT_ID), \
                     patch.object(memory_optimization, 'probe_writeback_backends',
                                  return_value=inventory):
                    with self.assertRaisesRegex(ValueError, expected):
                        plugin._validate_backend_resource(command)

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

    def test_apply_request_pause_is_license_free_and_does_not_start_ksm(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-pause-')
        calls = []
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload:
                calls.append((action, payload)) or
                ({'status': 'Succeeded', 'schemaVersion': 1,
                  'abiProfile': 'zram-service-v1', 'activeState': 'paused',
                  'desiredRevision': 4, 'readbackAllowed': True, 'paused': True}
                 if action == 'lifecycle-pause' else
                ({'revision': 0, 'settings': {'writeback': {}}}
                 if action == 'tuning-state' else
                 {'revision': 0, 'efficiency_enabled': False,
                  'idle_cpu_threshold_percent': 80,
                  'idle_duration_seconds': 60}
                 if action.endswith('-state') else
                 {'status': 'Succeeded'})))
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        with patch.object(plugin, '_apply_ksm_policy') as ksm:
            response = json.loads(plugin.apply_request({'body': json.dumps({
                'action': 'pause', 'hostUuid': 'host-1',
                'operationUuid': 'pause-1', 'poolGeneration': 'pool-7'})}))
        self.assertTrue(response['success'])
        self.assertEqual('Succeeded', response['status'])
        self.assertEqual(['lifecycle-pause'], [item[0] for item in calls])
        ksm.assert_not_called()
        self.assertEqual('pause', calls[0][1]['action'])
        self.assertEqual('PAUSED', response['state']['phase'])
        self.assertTrue(response['state']['lifecycle']['paused'])

    def test_resume_ack_timestamp_is_after_managed_ksm_transition(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-resume-sample-')
        calls = []
        transition_completed_at = []

        def service(action, payload):
            calls.append((action, payload))
            if action == 'lifecycle-pause':
                paused = payload.get('lifecycleAction') == 'pause'
                return {'status': 'Succeeded', 'paused': paused,
                        'activeState': 'paused' if paused else 'active',
                        'desiredRevision': 4, 'readbackAllowed': True}
            return {'status': 'Succeeded'}

        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})

        def managed_ksm(action):
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

    def test_uninitialized_pool_snapshot_is_explicit_only(self):
        self.assertTrue(MemoryOptimizationPlugin._is_uninitialized_pool_snapshot({
            'pool_generation': '', 'device': '', 'quality': 'unavailable',
            'reason': 'NO_QUALIFIED_MANAGED_POOL: EXCLUSIVE_ZRAM_ROUTE_REQUIRED'}))
        self.assertFalse(MemoryOptimizationPlugin._is_uninitialized_pool_snapshot({
            'pool_generation': '', 'device': '/dev/zram0', 'quality': 'unavailable',
            'reason': 'NO_QUALIFIED_MANAGED_POOL: EXCLUSIVE_ZRAM_ROUTE_REQUIRED'}))

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

    def test_ksm_only_resume_starts_writer_without_go_socket(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ksm-resume-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        marker = plugin.MANAGED_KSM_MARKER
        plugin.MANAGED_KSM_MARKER = os.path.join(operation_dir, 'marker')
        open(plugin.MANAGED_KSM_MARKER, 'w').close()
        plugin._set_active_control('pause-ksm')
        plugin._record_operation({'operationUuid': 'pause-ksm', 'action': 'pause',
                                  'hostUuid': 'host-1'}, 'APPLIED',
                                 {'status': 'Succeeded', 'state': {'ksmOnly': True}})
        with patch.object(subprocess, 'check_call') as start:
            plugin._control_managed_ksm('resume')
        self.assertEqual(['systemctl', 'start', plugin.MANAGED_KSM_UNIT],
                         start.call_args[0][0])
        plugin.MANAGED_KSM_MARKER = marker

    def test_resume_refuses_unknown_persisted_ksm_state(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ksm-unknown-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        plugin.MANAGED_KSM_MARKER = os.path.join(operation_dir, 'marker')
        plugin.KSM_CONF = os.path.join(operation_dir, 'missing.conf')
        open(plugin.MANAGED_KSM_MARKER, 'w').close()
        with self.assertRaisesRegex(ValueError, 'KSM_PERSISTED_STATE_UNKNOWN'):
            plugin._control_managed_ksm('resume')

    def test_resume_keeps_managed_owner_running_when_ksm_scanning_is_disabled(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ksm-disabled-resume-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        plugin.MANAGED_KSM_MARKER = os.path.join(operation_dir, 'marker')
        plugin.KSM_CONF = os.path.join(operation_dir, 'ksmtuned.conf')
        with open(plugin.MANAGED_KSM_MARKER, 'w'):
            pass
        with open(plugin.KSM_CONF, 'w') as stream:
            stream.write('CONFIG_REVISION=4\nKSM_ENABLED=0\n')
        with patch.object(subprocess, 'check_call') as call:
            plugin._control_managed_ksm('resume')
        self.assertEqual([['systemctl', 'start', plugin.MANAGED_KSM_UNIT]],
                         [item[0][0] for item in call.call_args_list])

    def test_pause_stops_managed_writer_without_releasing_native_masks(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ksm-pause-owner-')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        plugin.MANAGED_KSM_MARKER = os.path.join(operation_dir, 'marker')
        with open(plugin.MANAGED_KSM_MARKER, 'w'):
            pass
        with patch.object(subprocess, 'check_call') as call:
            plugin._control_managed_ksm('pause')
        self.assertEqual([['systemctl', 'stop', plugin.MANAGED_KSM_UNIT]],
                         [item[0][0] for item in call.call_args_list])
        self.assertFalse(any('ksm.service' in item[0][0] or
                             'ksmtuned.service' in item[0][0]
                             for item in call.call_args_list))
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

    def test_new_optimization_is_rejected_before_ksm_or_service_side_effect(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-unsupported-')
        calls = []
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload:
                calls.append((action, payload)) or {'status': 'Succeeded'})
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        with patch.object(plugin, 'discover_capabilities', return_value={
                'supported': False, 'reasonCode': 'UNSUPPORTED_OS_RELEASE'}), \
                patch.object(plugin, '_apply_ksm_policy') as ksm:
            response = plugin.apply({'action': 'apply', 'hostUuid': 'host-1',
                'operationUuid': 'unsupported-1',
                'licensePermit': {'managed': True,
                                  'operationUuid': 'managed-host-1',
                                  'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                'policy': {'ksm': {'enabled': True}}})
        self.assertFalse(response['success'])
        self.assertEqual('UNSUPPORTED_HOST_CAPABILITY:UNSUPPORTED_OS_RELEASE',
                         response['reason'])
        self.assertEqual([], calls)
        ksm.assert_not_called()
    def test_ksm_only_persists_product_revision_without_zram_service(self):
        operation_dir = tempfile.mkdtemp(prefix='memory-ops-')
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: self.fail('zram service must not be called'))
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        plugin._apply_ksm_policy = lambda command: {'configRevision': '7'}
        response = plugin.apply({
            'hostUuid': 'host-1', 'operationUuid': 'op-ksm', 'desiredRevision': 7,
            'licensePermit': {'managed': True, 'operationUuid': 'managed-host-1', 'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
            'policy': {'ksm': {'enabled': False}, 'zram': {'enabled': False},
                       'writeback': {'enabled': False}}})
        self.assertTrue(response['success'])
        self.assertEqual(7, response['appliedRevision'])
        with open(os.path.join(operation_dir, 'op-ksm.json')) as stream:
            record = json.load(stream)
        self.assertEqual(7, record['desiredRevision'])
        self.assertEqual('APPLIED', record['stage'])

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

    def _capacity_blocked_reconcile_fixture(self, operation_dir, capacity_state=None,
                                            include_receipt=True):
        operation_uuid = 'op-capacity-blocked'
        policy = {'zram': {'enabled': True, 'logicalCapacityBytes': 1024,
                           'ramLimitBytes': 256}}
        configured = {'logical_capacity': {'bytes': 1024},
                      'physical_memory_limit': {'bytes': 256}}
        desired = {'configured': configured, 'basis_host_memory_bytes': 4096,
                   'logical_resolved_bytes': 1024, 'physical_resolved_bytes': 256}
        current = capacity_state or {
            # Host capacity and CPU sections share the service Host revision.
            # The initial capacity PUT is revision 5; this operation's final
            # CPU PUT advances it to revision 6.
            '_http_status': 200, 'revision': 6, 'desired': desired,
            'effective_logical_bytes': None, 'effective_physical_limit_bytes': None,
            'apply_state': 'BLOCKED', 'reason': 'NATIVE_POOL_UNQUALIFIED'}
        observed_cpu = {'_http_status': 200, 'revision': 6,
                        'efficiency_enabled': True,
                        'idle_cpu_threshold_percent': 5,
                        'idle_duration_seconds': 60}
        observed_tuning = {'_http_status': 200, 'revision': 2, 'settings': {}}
        calls = []

        def service(action, payload):
            calls.append((action, payload))
            if action == 'capacity-state':
                return current
            if action == 'host-cpu-state':
                return observed_cpu
            if action == 'tuning-state':
                return observed_tuning
            self.fail('reconcile must be read-only, unexpected service action: %s' % action)

        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir})
        apply_evidence = {
            'operationUuid': operation_uuid, 'success': True, 'status': 'Draining',
            'state': {'sections': {
                'cpuBefore': {'_http_status': 200, 'revision': 0,
                              'efficiency_enabled': False,
                              'idle_cpu_threshold_percent': 5,
                              'idle_duration_seconds': 60},
                'capacity': {'_http_status': 202, 'revision': 5, 'desired': desired,
                             'agent_request_id': operation_uuid + '-capacity',
                             'agent_expected_revision': 4},
                'capacityReadback': {'_http_status': 200, 'revision': 5,
                                     'desired': desired, 'apply_state': 'BLOCKED',
                                     'reason': 'NATIVE_POOL_UNQUALIFIED'},
                'cpu': {'_http_status': 200, 'revision': 6,
                        'efficiency_enabled': True,
                        'idle_cpu_threshold_percent': 5,
                        'idle_duration_seconds': 60,
                        'request_id': operation_uuid + '-cpu',
                        'agent_expected_revision': 5,
                        'agent_desired_enabled': True,
                        'agent_desired_threshold_percent': 5,
                        'agent_desired_duration_seconds': 60},
                'cpuReadback': {'_http_status': 200, 'revision': 6,
                                'efficiency_enabled': True,
                                'idle_cpu_threshold_percent': 5,
                                'idle_duration_seconds': 60},
                'tuning': {'_http_status': 200, 'revision': 2,
                           'request_id': operation_uuid + '-tuning'},
            }, 'sectionComplete': {'cpu': True}},
        }
        command = {'hostUuid': 'host-1', 'operationUuid': operation_uuid,
                   'desiredRevision': 7, 'policy': policy}
        if include_receipt:
            plugin._record_operation(command, 'UNKNOWN', apply_evidence)
        else:
            plugin._record_operation(command, 'UNKNOWN', {
                'operationUuid': operation_uuid, 'success': False,
                'status': 'Unknown', 'state': {'phase': 'UNKNOWN'}})
        response = lambda: json.loads(plugin.reconcile({'body': json.dumps({
            'hostUuid': 'host-1', 'operationUuid': operation_uuid})}))
        return plugin, response, current, calls

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

    def test_state_normalizes_runtime_vm_binding_fields_for_management_node(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {
            'identities': {'vm-1': {'uuid': 'vm-1', 'instance_generation': 'instance-7'}}})
        plugin.configure({'hostUuid': 'host-1'})
        result = {'status': 'Succeeded', 'state': {
            'vms': {'vm-1': {'instanceGeneration': 'instance-7',
                             'binding_generation': 'instance-7',
                             'binding_mode': 'auto'}}}}
        with patch.object(plugin, '_libvirt_vm_generations', return_value=({'vm-1': {}}, True)):
            enriched = plugin._enrich_state(result)
        vm = enriched['state']['vms']['vm-1']
        self.assertEqual('instance-7', vm['bindingGeneration'])
        self.assertEqual('auto', vm['bindingMode'])

    def _ksm_only_state_plugin(self, operation_dir):
        """Build the no-Go-socket fixture used by the Kylin KSM-only contract."""
        def unavailable(*args, **kwargs):
            raise RuntimeError('zram service unavailable')
        plugin = MemoryOptimizationPlugin(service_call=unavailable)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'socketPath': os.path.join(operation_dir, 'missing.sock')})
        plugin._libvirt_vm_generations = lambda: ({}, True)
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'kylinV10',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': False, 'zramReasonCode': 'ABI_INCOMPLETE', 'service': False,
        }
        # These state/journal tests intentionally mock only the KSM sysfs
        # control path; ownership orchestration has dedicated unit tests.
        plugin._prepare_managed_ksm_ownership = lambda: None
        return plugin

    def test_state_recovers_current_boot_ksm_only_after_go_socket_failure(self):
        """Kylin KSM remains observable when the optional Go service is absent."""
        root = tempfile.mkdtemp(prefix='state-ksm-only-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.service_call = plugin._call_local_service
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-state-1',
                   'desiredRevision': 17,
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                      'sleepMillis': 20, 'zeroPagesEnabled': True},
                              'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        plugin._set_active_control('ksm-state-1')
        plugin._record_operation(command, 'APPLIED',
                                 {'success': True, 'status': 'Succeeded',
                                  'state': {'ksmOnly': True}})
        with patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(subprocess, 'check_output', return_value=(
                    b'run=1\npages_to_scan=2000\nsleep_millisecs=20\nuse_zero_pages=1\n')):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'ksm-state-1'})}))
        self.assertEqual('Succeeded', response['status'])
        self.assertTrue(response['success'])
        self.assertEqual(17, response['appliedRevision'])
        self.assertTrue(response['state'].get('ksmOnly'))
        self.assertFalse(response['state']['safeToRemove'])
        self.assertNotIn('reason', response)
        self.assertEqual('ABI_INCOMPLETE', response['capabilities']['zramReasonCode'])
        readback.assert_called_once_with(command['policy']['ksm'], 17)

    def test_ksm_fallback_does_not_mask_invalid_identity_or_unrelated_failures(self):
        cases = (
            ('wrong-host', {'hostUuid': 'host-2', 'operationUuid': 'state-observation'}, 'host-1',
             OSError(errno.ENOENT, 'missing service socket')),
            ('unknown-host-identity', {'hostUuid': 'host-1', 'operationUuid': 'state-observation'},
             None, OSError(errno.ENOENT, 'missing service socket')),
            ('invalid-command', {'hostUuid': 'host-1'}, 'host-1',
             OSError(errno.ENOENT, 'missing service socket')),
            ('invalid-json-shape', ['not', 'an', 'object'], 'host-1',
             OSError(errno.ENOENT, 'missing service socket')),
            ('unrelated-error', {'hostUuid': 'host-1', 'operationUuid': 'state-observation'},
             'host-1', RuntimeError('state handler bug')),
            ('bad-http-payload', {'hostUuid': 'host-1', 'operationUuid': 'state-observation'},
             'host-1', ValueError('invalid JSON response')),
            ('unrelated-os-error', {'hostUuid': 'host-1', 'operationUuid': 'state-observation'},
             'host-1', OSError(errno.EINVAL, 'not a socket outage')),
        )
        for name, body, host_uuid, dispatch_error in cases:
            with self.subTest(name=name):
                root = tempfile.mkdtemp(prefix='state-ksm-no-false-promotion-')
                plugin = self._ksm_only_state_plugin(root)
                command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-policy',
                           'desiredRevision': 17,
                           'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000},
                                      'zram': {'enabled': False},
                                      'writeback': {'enabled': False}}}
                plugin._set_active_control(command['operationUuid'])
                plugin._record_operation(command, 'APPLIED', {
                    'success': True, 'status': 'Succeeded',
                    'state': {'ksmOnly': True}})
                with patch.object(plugin, '_load_host_uuid', return_value=host_uuid), \
                        patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                        patch.object(plugin, '_dispatch', side_effect=dispatch_error) as dispatch, \
                        patch.object(subprocess, 'check_output', return_value=(
                            b'run=1\nconfigRevision=17\npages_to_scan=2000\n')):
                    response = json.loads(plugin.state({'body': json.dumps(body)}))
                self.assertNotEqual('Succeeded', response.get('status'), name)
                if response.get('status') == 'Unknown':
                    self.assertFalse(response['success'], name)
                    self.assertFalse(response['state']['safeToRemove'], name)
                readback.assert_not_called()
                if name in ('wrong-host', 'unknown-host-identity', 'invalid-command',
                            'invalid-json-shape'):
                    dispatch.assert_not_called()
                else:
                    dispatch.assert_called_once()

    def test_ksm_fallback_does_not_mask_http_error_response(self):
        root = tempfile.mkdtemp(prefix='state-ksm-http-error-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-policy',
                   'desiredRevision': 17,
                   'policy': {'ksm': {'enabled': True}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        plugin._set_active_control(command['operationUuid'])
        plugin._record_operation(command, 'APPLIED', {
            'success': True, 'status': 'Succeeded', 'state': {'ksmOnly': True}})
        error_response = {'success': False, 'status': 'Unknown', 'state': {},
                          'reason': 'service returned HTTP 503', '_http_status': 503}
        with patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(plugin, '_dispatch', return_value=error_response), \
                patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        readback.assert_not_called()

    def test_real_ksm_only_apply_journal_then_fresh_state_query(self):
        """Exercise apply/journal/active-control/state without shortcut mocks."""
        root = tempfile.mkdtemp(prefix='real-ksm-roundtrip-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.service_call = plugin._call_local_service
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        command = {'hostUuid': 'host-1', 'operationUuid': 'real-ksm-1',
                   'desiredRevision': 31,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-1',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                      'sleepMillis': 20, 'zeroPagesEnabled': True},
                              'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        native = b'run=1\nconfigRevision=31\npages_to_scan=2000\n' \
                 b'sleep_millisecs=20\nuse_zero_pages=1\n'
        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start'] or argv[:2] == ['systemctl', 'enable']:
                return b''
            if argv[:2] == ['systemctl', 'stop'] or argv[:2] == ['systemctl', 'disable']:
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                return native
            raise AssertionError('unexpected native command: %r' % (argv,))
        with patch.object(plugin, 'discover_capabilities', return_value={
                'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'kylinV10',
                'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
                'zram': False, 'zramReasonCode': 'ABI_INCOMPLETE', 'service': False}), \
                patch.object(subprocess, 'check_output', side_effect=native_command):
            first = plugin.apply(command)
            second = plugin.apply(command)
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'fresh-state-1'})}))
        self.assertTrue(first['success'])
        self.assertEqual('Succeeded', first['status'])
        self.assertEqual(first, second)
        self.assertEqual('APPLIED', json.load(open(os.path.join(root, 'real-ksm-1.json')))['stage'])
        self.assertEqual('Succeeded', response['status'])
        self.assertTrue(response['success'])
        self.assertEqual(31, response['appliedRevision'])
        self.assertFalse(response['state']['safeToRemove'])

    def _real_applied_ksm_fixture(self, root, revision=41):
        plugin = self._ksm_only_state_plugin(root)
        plugin.service_call = plugin._call_local_service
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        command = {'hostUuid': 'host-1', 'operationUuid': 'real-fixture-%s' % revision,
                   'desiredRevision': revision,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-%s' % revision,
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                      'sleepMillis': 20, 'zeroPagesEnabled': True},
                              'zram': {'enabled': False}, 'writeback': {'enabled': False}}}
        native = ('run=1\nconfigRevision=%d\npages_to_scan=2000\n'
                  'sleep_millisecs=20\nuse_zero_pages=1\n' % revision).encode('ascii')
        with patch.object(subprocess, 'check_output', return_value=native):
            result = plugin.apply(command)
        self.assertTrue(result['success'])
        path = os.path.join(root, command['operationUuid'] + '.json')
        with open(path) as stream:
            record = json.load(stream)
        self.assertIs(True, record['readback']['state'].get('ksmOnly'))
        with patch.object(subprocess, 'check_output', return_value=native):
            observed = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Succeeded', observed['status'])
        return plugin, command, path

    def _managed_clear_fixture(self, root, revision=91, enabled=False, scope=None,
                               resource_uuid=None):
        """Create managed marker + full config + independent native writer receipt."""
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        plugin.MANAGED_KSM_MARKER = os.path.join(root, 'managed-ksm-controller')
        native_ack = {}

        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                with open(plugin.KSM_CONF) as stream:
                    config = dict(line.rstrip().split('=', 1) for line in stream if '=' in line)
                native_ack.update({'run': '1' if config['KSM_ENABLED'] == '1' else '0',
                    'configRevision': config['CONFIG_REVISION'],
                    'pages_to_scan': config['KSM_PAGES_TO_SCAN'],
                    'sleep_millisecs': config['KSM_SLEEP_MILLISECS'],
                    'use_zero_pages': config['KSM_ZERO_PAGES']})
                return b''
            if argv[:2] in (['systemctl', 'enable'], ['systemctl', 'stop'], ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                return ''.join('%s=%s\n' % item for item in native_ack.items()).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        initial = {'hostUuid': 'host-1', 'operationUuid': 'managed-marker-before-%s' % revision,
                   'desiredRevision': revision,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-%s' % revision,
                       'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': enabled, 'pagesToScan': 600,
                       'sleepMillis': 30, 'zeroPagesEnabled': False},
                       'zram': {'enabled': False}, 'writeback': {'enabled': False}}}
        if scope is not None:
            initial['scope'] = scope
        if resource_uuid is not None:
            initial['resourceUuid'] = resource_uuid
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(initial)
        self.assertTrue(result['success'])
        with open(plugin.MANAGED_KSM_MARKER, 'w') as stream:
            pass  # The real ownership marker is an empty, durable presence file.
        operation_path = os.path.join(root, initial['operationUuid'] + '.json')
        return plugin, initial, native_ack, native_command, operation_path

    def _clear_managed_policy(self, initial, operation_uuid):
        command = {'hostUuid': 'host-1', 'operationUuid': operation_uuid,
                'expectedRevision': initial['desiredRevision'],
                'desiredRevision': initial['desiredRevision'] + 1,
                'licensePermit': {'managed': True,
                    'operationUuid': 'permit-%s' % (initial['desiredRevision'] + 1),
                    'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                'policy': {'ksm': {}, 'zram': {'enabled': False},
                           'writeback': {'enabled': False}}}
        for key in ('scope', 'resourceUuid'):
            if key in initial:
                command[key] = initial[key]
        return command

    def _r2_mixed_delta_fixture(self, root, operation_suffix='r2'):
        """A real mixed-policy Agent journal with independent KSM writer ACK."""
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: service(action, payload))
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root,
                          'socketPath': os.path.join(root, 'service.sock')})
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        plugin.MANAGED_KSM_MARKER = os.path.join(root, 'managed-ksm-controller')
        service_writes = []
        native_ack = {}
        service_state = {
            'capacity-state': {'revision': 1, 'effective_logical_bytes': 8192,
                'effective_physical_limit_bytes': 4096, 'apply_state': 'APPLIED',
                'desired': {'configured': {'logical_capacity': {'bytes': 8192},
                    'physical_memory_limit': {'bytes': 4096}}}},
            'host-cpu-state': {'revision': 1, 'efficiency_enabled': False,
                'idle_cpu_threshold_percent': 80, 'idle_duration_seconds': 60},
            'tuning-state': {'revision': 1, 'settings': {'writeback': {'enabled': False}}},
        }

        def service(action, payload):
            if action == 'capacity-state':
                return dict(service_state[action], _http_status=200)
            if action == 'host-cpu-state':
                return dict(service_state[action], _http_status=200)
            if action == 'tuning-state':
                return dict(service_state[action], _http_status=200)
            if action == 'capacity':
                service_writes.append((action, payload))
                state = service_state['capacity-state']
                state.update({'revision': state['revision'] + 1,
                    'effective_logical_bytes': payload['logical_capacity']['bytes'],
                    'effective_physical_limit_bytes': payload['physical_memory_limit']['bytes'],
                    'desired': {'configured': {
                        'logical_capacity': {'bytes': payload['logical_capacity']['bytes']},
                        'physical_memory_limit': {
                            'bytes': payload['physical_memory_limit']['bytes']}}},
                    'apply_state': 'APPLIED'})
                service_state['host-cpu-state']['revision'] = state['revision']
                return dict(state, request_id=payload['request_id'], _http_status=200)
            if action == 'host-cpu':
                service_writes.append((action, payload))
                cpu = service_state['host-cpu-state']
                cpu.update({'revision': cpu['revision'] + 1,
                    'efficiency_enabled': payload['efficiency_enabled'],
                    'idle_cpu_threshold_percent': payload['idle_cpu_threshold_percent'],
                    'idle_duration_seconds': payload['idle_duration_seconds']})
                service_state['capacity-state']['revision'] = cpu['revision']
                return {'revision': cpu['revision'], 'request_id': payload['request_id'],
                        'efficiency_enabled': cpu['efficiency_enabled'], '_http_status': 200}
            if action == 'apply':
                service_writes.append((action, payload))
                tuning = service_state['tuning-state']
                tuning.update({'revision': tuning['revision'] + 1,
                               'settings': payload['settings']})
                return dict(tuning, request_id=payload['request_id'], _http_status=200)
            service_writes.append((action, payload))
            return {'success': True, 'status': 'Succeeded',
                    'state': {'phase': 'APPLIED'}, 'revision': len(service_writes)}

        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'h84r',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': True, 'service': True,
        }

        def prepare_managed_ksm():
            Path(plugin.MANAGED_KSM_MARKER).touch()

        plugin._prepare_managed_ksm_ownership = prepare_managed_ksm

        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                with open(plugin.KSM_CONF) as stream:
                    config = dict(line.rstrip().split('=', 1) for line in stream if '=' in line)
                native_ack.update({
                    'run': '1' if config['KSM_ENABLED'] == '1' else '0',
                    'configRevision': config['CONFIG_REVISION'],
                    'pages_to_scan': config['KSM_PAGES_TO_SCAN'],
                    'sleep_millisecs': config['KSM_SLEEP_MILLISECS'],
                    'use_zero_pages': config['KSM_ZERO_PAGES'],
                })
                return b''
            if argv[:2] in (['systemctl', 'enable'], ['systemctl', 'stop'],
                            ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                return ''.join('%s=%s\n' % item for item in native_ack.items()).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        initial = {
            'hostUuid': 'host-1', 'operationUuid': 'r2-mixed-initial-' + operation_suffix,
            'desiredRevision': 1,
            'licensePermit': {'managed': True, 'operationUuid': 'r2-permit-1',
                              'expiresAt': int(time.time() * 1000) + 35000,
                              'validForSeconds': 30},
            'policy': {
                'ksm': {'enabled': True, 'pagesToScan': 600,
                        'sleepMillis': 30, 'zeroPagesEnabled': False},
                'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                         'ramLimitBytes': 4096, 'cpuThresholdPercent': 5},
                'writeback': {'enabled': False},
            },
        }
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            applied = plugin.apply(initial)
        self.assertTrue(applied.get('success'), applied)
        self.assertEqual('Succeeded', applied.get('status'))
        with open(os.path.join(root, initial['operationUuid'] + '.json')) as stream:
            initial_record = json.load(stream)
        self.assertEqual('APPLIED', initial_record.get('stage'))
        self.assertNotIn('ksmOnly', (initial_record.get('readback') or {}).get('state') or {})
        self.assertEqual('1', native_ack.get('configRevision'))
        native_conf = Path(plugin.KSM_CONF).read_bytes()
        return plugin, initial, service_writes, native_ack, native_command, native_conf

    def _r2_command(self, initial, operation_uuid, policy, mode='delta', revision=2):
        command = {
            'hostUuid': 'host-1', 'operationUuid': operation_uuid,
            'expectedRevision': revision - 1, 'desiredRevision': revision,
            'policy': policy,
            'licensePermit': {'managed': True, 'operationUuid': 'r2-permit-%s' % revision,
                              'expiresAt': int(time.time() * 1000) + 35000,
                              'validForSeconds': 30},
        }
        if mode is not _OMIT_POLICY_MODE:
            command['policyMode'] = mode
        return command

    def _assert_r2_delta_does_not_touch_ksm(self, plugin, command, service_writes,
                                            native_ack, native_command, native_conf):
        before_ack = dict(native_ack)
        before_writes = len(service_writes)
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(command)
        violations = []
        if result.get('success') is not True or result.get('status') != 'Succeeded':
            violations.append('update did not succeed: %r' % result)
        if len(service_writes) <= before_writes:
            violations.append('Go service write was not reached')
        if before_ack != native_ack:
            violations.append('native KSM ack changed: %r' % native_ack)
        if native_conf != Path(plugin.KSM_CONF).read_bytes():
            violations.append('native KSM config was rewritten')
        with open(os.path.join(plugin.operation_dir, command['operationUuid'] + '.json')) as stream:
            record = json.load(stream)
        readback = record.get('readback') or {}
        if record.get('stage') != 'APPLIED':
            violations.append('journal stage is %r' % record.get('stage'))
        if 'ksmReadback' in readback:
            violations.append('journal contains unexpected KSM readback')
        if 'ksmOnly' in (readback.get('state') or {}):
            violations.append('journal fabricated KSM-only proof')
        if record.get('policyMode') != 'delta':
            violations.append('journal policyMode is %r' % record.get('policyMode'))
        self.assertEqual([], violations)
        return result, record

    def test_r2_delta_empty_ksm_shapes_service_write_without_ksm_proof(self):
        for shape in ('empty', 'omitted', 'null'):
            with self.subTest(ksm_shape=shape):
                root = tempfile.mkdtemp(prefix='r2-delta-empty-ksm-%s-' % shape)
                plugin, initial, service_writes, native_ack, native_command, native_conf = \
                    self._r2_mixed_delta_fixture(root, 'empty-' + shape)
                policy = {'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                                   'ramLimitBytes': 4096, 'cpuThresholdPercent': 40},
                          'writeback': {'enabled': False}}
                if shape == 'empty':
                    policy['ksm'] = {}
                elif shape == 'null':
                    policy['ksm'] = None
                command = self._r2_command(initial, 'r2-delta-empty-' + shape,
                                           policy, mode='delta')
                result, record = self._assert_r2_delta_does_not_touch_ksm(
                    plugin, command, service_writes, native_ack, native_command, native_conf)
                self.assertEqual(2, result.get('appliedRevision'))
                self.assertNotIn('ksmReadback', record.get('readback') or {})

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

    def test_r2_delta_nonempty_partial_ksm_uses_native_ack_and_service(self):
        root = tempfile.mkdtemp(prefix='r2-delta-partial-ksm-')
        plugin, initial, service_writes, native_ack, native_command, native_conf = \
            self._r2_mixed_delta_fixture(root, 'partial-ksm')
        command = self._r2_command(initial, 'r2-delta-partial-ksm', {
            'ksm': {'pagesToScan': 777},
            'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096},
            'writeback': {'enabled': False}}, mode='delta')
        writes_before = len(service_writes)
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(command)
        self.assertTrue(result.get('success'), result)
        self.assertEqual('Succeeded', result.get('status'))
        self.assertGreater(len(service_writes), writes_before)
        self.assertEqual({'run': '1', 'configRevision': '2', 'pages_to_scan': '777',
                          'sleep_millisecs': '30', 'use_zero_pages': '0'}, native_ack)
        self.assertNotEqual(native_conf, Path(plugin.KSM_CONF).read_bytes())
        record = json.load(open(os.path.join(plugin.operation_dir,
                                              command['operationUuid'] + '.json')))
        self.assertEqual('delta', record.get('policyMode'))
        self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})

    def test_r2_effective_empty_ksm_keeps_strict_mixed_clear_gate_and_legacy_default(self):
        for mode in ('effective', _OMIT_POLICY_MODE):
            with self.subTest(policyMode='omitted' if mode is _OMIT_POLICY_MODE else mode):
                root = tempfile.mkdtemp(prefix='r2-effective-mixed-empty-')
                plugin, initial, service_writes, native_ack, native_command, native_conf = \
                    self._r2_mixed_delta_fixture(root,
                        'effective-legacy' if mode is _OMIT_POLICY_MODE else 'effective-explicit')
                suffix = 'legacy' if mode is _OMIT_POLICY_MODE else 'explicit'
                command = self._r2_command(initial, 'r2-effective-mixed-' + suffix, {
                    'ksm': {}, 'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                                        'ramLimitBytes': 4096},
                    'writeback': {'enabled': False}}, mode=mode)
                writes_before = len(service_writes)
                ack_before = dict(native_ack)
                with patch.object(subprocess, 'check_output', side_effect=native_command):
                    result = plugin.apply(command)
                self.assertEqual('Succeeded', result.get('status'), result)
                self.assertGreater(len(service_writes), writes_before)
                self.assertEqual('2', native_ack.get('configRevision'))
                for field in ('run', 'pages_to_scan', 'sleep_millisecs', 'use_zero_pages'):
                    self.assertEqual(ack_before[field], native_ack.get(field))
                self.assertNotEqual(native_conf, Path(plugin.KSM_CONF).read_bytes())

    def test_r2_valid_ksm_only_clear_remains_available_in_effective_and_legacy_mode(self):
        for index, mode in enumerate(('effective', _OMIT_POLICY_MODE)):
            with self.subTest(policyMode='omitted' if mode is _OMIT_POLICY_MODE else mode):
                root = tempfile.mkdtemp(prefix='r2-effective-ksm-only-clear-')
                plugin, initial, native_ack, native_command, _ = self._managed_clear_fixture(
                    root, revision=161 + index * 2, enabled=False)
                command = self._clear_managed_policy(initial, 'r2-valid-ksm-clear-%s' % index)
                if mode is not _OMIT_POLICY_MODE:
                    command['policyMode'] = mode
                with patch.object(subprocess, 'check_output', side_effect=native_command):
                    result = plugin.apply(command)
                self.assertTrue(result.get('success'), result)
                self.assertEqual('Succeeded', result.get('status'))
                self.assertEqual(str(initial['desiredRevision'] + 1),
                                 native_ack.get('configRevision'))
                record = json.load(open(os.path.join(root, command['operationUuid'] + '.json')))
                self.assertIs(True, (record.get('readback') or {}).get('state', {}).get('ksmOnly'))

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

    def _r3_stateful_mixed_fixture(self, root, suffix='shared'):
        """Create a mixed policy using independent native and formal-ABI Go actors."""
        events, native_ack, faults = [], {}, {}
        service_state = {
            'capacity-state': {'revision': 7, 'effective_logical_bytes': 8192,
                               'effective_physical_limit_bytes': 4096, 'apply_state': 'APPLIED',
                               'desired': {'configured': {
                                   'logical_capacity': {'bytes': 8192},
                                   'physical_memory_limit': {'bytes': 4096}}}},
            'host-cpu-state': {'revision': 7, 'efficiency_enabled': True,
                               'idle_cpu_threshold_percent': 40, 'idle_duration_seconds': 60},
            'tuning-state': {'revision': 9, 'settings': {
                'vm_management': {'mode': 'all_running', 'vm_uuids': []},
                'discovery_interval_seconds': 60, 'discovery_timeout_seconds': 10,
                'discovery_ttl_seconds': 10, 'host_sample_interval_seconds': 1,
                'host_sample_ttl_seconds': 10, 'vm_sample_interval_seconds': 1,
                'vm_sample_ttl_seconds': 10, 'writeback': {'enabled': False}}}}

        def service(action, payload):
            events.append(('go', action, dict(payload or {})))
            if action in service_state:
                response = dict(service_state[action], _http_status=200)
                get_when = faults.get('get_when')
                get_action = faults.get('get_action')
                should_mutate = (action == get_action and
                                 ((get_when == 'preflight' and
                                   not faults.get('_writes_started')) or
                                  (get_when == 'postflight' and
                                   faults.get('_all_writes_done'))))
                if should_mutate:
                    kind = faults.get('get_kind')
                    if kind == 'missing_idle_duration':
                        response.pop('idle_duration_seconds', None)
                    elif kind == 'missing_efficiency_enabled':
                        response.pop('efficiency_enabled', None)
                    elif kind == 'status_unknown':
                        response['status'] = 'Unknown'
                    elif kind == 'error_envelope':
                        response['error'] = 'injected HTTP 200 error envelope'
                    elif kind == 'success_false':
                        response['success'] = False
                    elif kind == 'phase_unknown':
                        response['state'] = {'phase': 'UNKNOWN'}
                    elif kind == 'float_http_status':
                        response['_http_status'] = 200.0
                    elif kind == 'bool_revision':
                        response['revision'] = True
                    elif kind == 'stale_revision':
                        response['revision'] -= 1
                    elif kind == 'wrong_capacity':
                        response['effective_logical_bytes'] += 1
                return response
            if action == 'capacity':
                faults['_writes_started'] = True
                expected = payload['expected_revision']
                if expected != service_state['capacity-state']['revision']:
                    return {'_http_status': 409, 'error': 'REVISION_CONFLICT'}
                next_revision = expected + 1
                service_state['capacity-state'].update({
                    'revision': next_revision,
                    'effective_logical_bytes': payload['logical_capacity']['bytes'],
                    'effective_physical_limit_bytes': payload['physical_memory_limit']['bytes'],
                    'desired': {'configured': {
                        'logical_capacity': {'bytes': payload['logical_capacity']['bytes']},
                        'physical_memory_limit': {
                            'bytes': payload['physical_memory_limit']['bytes']}}},
                    'apply_state': 'APPLIED'})
                service_state['host-cpu-state']['revision'] = next_revision
                return dict(service_state['capacity-state'], request_id=payload['request_id'],
                            _http_status=200)
            if action == 'host-cpu':
                faults['_writes_started'] = True
                if faults.get('fail_action') == action:
                    return {'_http_status': 500, 'success': False,
                            'error': 'injected service PUT failure'}
                if faults.get('raise_action') == action:
                    raise OSError('injected control-socket timeout')
                cpu = service_state['host-cpu-state']
                expected = payload['expected_revision']
                if expected != cpu['revision']:
                    return {'_http_status': 409, 'error': 'REVISION_CONFLICT'}
                cpu.update({'revision': expected + 1,
                            'efficiency_enabled': payload['efficiency_enabled'],
                            'idle_cpu_threshold_percent': payload['idle_cpu_threshold_percent'],
                            'idle_duration_seconds': payload['idle_duration_seconds']})
                service_state['capacity-state']['revision'] = cpu['revision']
                return {'revision': cpu['revision'], 'request_id': payload['request_id'],
                        'efficiency_enabled': cpu['efficiency_enabled'],
                        '_http_status': 200}
            if action == 'apply':
                faults['_writes_started'] = True
                tune = service_state['tuning-state']
                if payload['expected_revision'] != tune['revision']:
                    return {'_http_status': 409, 'error': 'REVISION_CONFLICT'}
                tune['revision'] += 1
                tune['settings'] = payload['settings']
                faults['_all_writes_done'] = True
                return dict(tune, _http_status=200)
            raise AssertionError('unexpected service action: %s' % action)

        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin._r3_test_faults = faults
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root,
                          'socketPath': os.path.join(root, 'service.sock')})
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        plugin.MANAGED_KSM_MARKER = os.path.join(root, 'managed-ksm-controller')
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'h84r',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': True, 'service': True}
        plugin._prepare_managed_ksm_ownership = lambda: Path(plugin.MANAGED_KSM_MARKER).touch()

        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                config = dict(line.rstrip().split('=', 1) for line in
                              Path(plugin.KSM_CONF).read_text().splitlines() if '=' in line)
                native_ack.update({
                    'run': '1' if config['KSM_ENABLED'] == '1' else '0',
                    'configRevision': config['CONFIG_REVISION'],
                    'pages_to_scan': config['KSM_PAGES_TO_SCAN'],
                    'sleep_millisecs': config['KSM_SLEEP_MILLISECS'],
                    'use_zero_pages': config['KSM_ZERO_PAGES']})
                if faults.get('native_ack_fault') == 'omit-zero-pages':
                    native_ack.pop('use_zero_pages', None)
                events.append(('native-ack', dict(native_ack)))
                return b''
            if argv[:2] in (['systemctl', 'enable'], ['systemctl', 'stop'],
                            ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                config = dict(line.rstrip().split('=', 1) for line in
                              Path(plugin.KSM_CONF).read_text().splitlines() if '=' in line)
                if (faults.get('native_ack_fault') == 'readback-error-after-write' and
                        config.get('CONFIG_REVISION') != '1'):
                    raise OSError('injected native ACK query failure')
                return ''.join('%s=%s\n' % item for item in native_ack.items()).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        operation = 'r3-fixture-' + suffix
        initial = {'hostUuid': 'host-1', 'operationUuid': operation, 'desiredRevision': 1,
                   'licensePermit': {'managed': True, 'operationUuid': operation + '-permit',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 600,
                                      'sleepMillis': 30, 'zeroPagesEnabled': False},
                              'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                                       'ramLimitBytes': 4096, 'cpuThresholdPercent': 40},
                              'writeback': {'enabled': False}}}
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(initial)
        self.assertEqual('Succeeded', result.get('status'), result)
        record = json.load(open(os.path.join(root, operation + '.json')))
        self.assertTrue((record.get('readback') or {}).get('ksmReadback'), record)
        self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
        self.assertEqual('1', native_ack.get('configRevision'))
        return plugin, events, native_ack, service_state, faults, native_command

    def _r3_apply_effective_clear(self, plugin, root, events, native_command,
                                  operation, revision, zram, writeback=None):
        events.clear()
        faults = getattr(plugin, '_r3_test_faults', None)
        if isinstance(faults, dict):
            faults['_writes_started'] = False
            faults['_all_writes_done'] = False
        command = {'hostUuid': 'host-1', 'operationUuid': operation,
                   'expectedRevision': revision - 1, 'desiredRevision': revision,
                   'policyMode': 'effective',
                   'licensePermit': {'managed': True, 'operationUuid': operation + '-permit',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {}, 'zram': zram,
                              'writeback': ({'enabled': False} if writeback is None
                                            else writeback)}}
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(command)
        record = json.load(open(os.path.join(root, operation + '.json')))
        return result, record, list(events)

    def test_r3_effective_mixed_clear_requires_trusted_service_readback_and_preserves_ksm(self):
        """A mixed APPLIED journal owns KSM, but is not a KSM-only fallback."""
        root = tempfile.mkdtemp(prefix='r3-effective-mixed-clear-')
        events = []
        native_ack = {}
        faults = {}
        service_state = {
            'capacity-state': {'revision': 7, 'effective_logical_bytes': 8192,
                               'effective_physical_limit_bytes': 4096,
                               'apply_state': 'APPLIED',
                               'desired': {'configured': {
                                   'logical_capacity': {'bytes': 8192},
                                   'physical_memory_limit': {'bytes': 4096}}}},
            'host-cpu-state': {'revision': 7, 'efficiency_enabled': True,
                               'idle_cpu_threshold_percent': 40,
                               'idle_duration_seconds': 60},
            'tuning-state': {'revision': 9, 'settings': {
                'vm_management': {'mode': 'all_running', 'vm_uuids': []},
                'discovery_interval_seconds': 60,
                'discovery_timeout_seconds': 10, 'discovery_ttl_seconds': 10,
                'host_sample_interval_seconds': 1, 'host_sample_ttl_seconds': 10,
                'vm_sample_interval_seconds': 1, 'vm_sample_ttl_seconds': 10,
                'writeback': {'enabled': False}}},
        }

        def service(action, payload):
            events.append(('go', action, dict(payload or {})))
            if action in service_state:
                return dict(service_state[action], _http_status=200)
            if action == 'capacity':
                expected = payload['expected_revision']
                if expected != service_state['capacity-state']['revision']:
                    return {'_http_status': 409, 'error': 'REVISION_CONFLICT'}
                next_revision = expected + 1
                service_state['capacity-state'].update({
                    'revision': next_revision,
                    'effective_logical_bytes': payload['logical_capacity']['bytes'],
                    'effective_physical_limit_bytes': payload['physical_memory_limit']['bytes'],
                    'desired': {'configured': {
                        'logical_capacity': {'bytes': payload['logical_capacity']['bytes']},
                        'physical_memory_limit': {
                            'bytes': payload['physical_memory_limit']['bytes']}}},
                    'apply_state': 'APPLIED'})
                service_state['host-cpu-state']['revision'] = next_revision
                return dict(service_state['capacity-state'], _http_status=200)
            if action == 'host-cpu':
                if faults.get('fail_action') == action:
                    return {'_http_status': 500, 'success': False,
                            'error': 'injected service PUT failure'}
                cpu = service_state['host-cpu-state']
                expected = payload['expected_revision']
                if expected != cpu['revision']:
                    return {'_http_status': 409, 'error': 'REVISION_CONFLICT'}
                cpu.update({'revision': expected + 1,
                            'efficiency_enabled': payload['efficiency_enabled'],
                            'idle_cpu_threshold_percent': payload['idle_cpu_threshold_percent'],
                            'idle_duration_seconds': payload['idle_duration_seconds']})
                service_state['capacity-state']['revision'] = cpu['revision']
                return {'revision': cpu['revision'], 'request_id': payload['request_id'],
                        'efficiency_enabled': cpu['efficiency_enabled'],
                        '_http_status': 200}
            if action == 'apply':
                if payload['expected_revision'] != service_state['tuning-state']['revision']:
                    return {'_http_status': 409, 'error': 'REVISION_CONFLICT'}
                service_state['tuning-state']['revision'] += 1
                service_state['tuning-state']['settings'] = payload['settings']
                return dict(service_state['tuning-state'], _http_status=200)
            raise AssertionError('unexpected Go service action: %s' % action)

        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': root,
                          'socketPath': os.path.join(root, 'service.sock')})
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        plugin.MANAGED_KSM_MARKER = os.path.join(root, 'managed-ksm-controller')
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'h84r',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': True, 'service': True}
        plugin._prepare_managed_ksm_ownership = lambda: Path(plugin.MANAGED_KSM_MARKER).touch()

        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                config = dict(line.rstrip().split('=', 1) for line in
                              Path(plugin.KSM_CONF).read_text().splitlines() if '=' in line)
                native_ack.update({
                    'run': '1' if config['KSM_ENABLED'] == '1' else '0',
                    'configRevision': config['CONFIG_REVISION'],
                    'pages_to_scan': config['KSM_PAGES_TO_SCAN'],
                    'sleep_millisecs': config['KSM_SLEEP_MILLISECS'],
                    'use_zero_pages': config['KSM_ZERO_PAGES']})
                events.append(('native-ack', dict(native_ack)))
                return b''
            if argv[:2] in (['systemctl', 'enable'], ['systemctl', 'stop'],
                            ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                return ''.join('%s=%s\n' % item for item in native_ack.items()).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        policy = {
            'ksm': {'enabled': True, 'pagesToScan': 600,
                    'sleepMillis': 30, 'zeroPagesEnabled': False},
            'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096, 'cpuThresholdPercent': 40},
            'writeback': {'enabled': False}}
        initial = {'hostUuid': 'host-1', 'operationUuid': 'r3-mixed-initial',
                   'desiredRevision': 1,
                   'licensePermit': {'managed': True, 'operationUuid': 'r3-permit-1',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': policy}
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            initial_result = plugin.apply(initial)
        self.assertEqual('Succeeded', initial_result.get('status'), initial_result)
        initial_record = json.load(open(os.path.join(root, 'r3-mixed-initial.json')))
        initial_readback = initial_record.get('readback') or {}
        self.assertTrue(initial_readback.get('ksmReadback'), initial_readback)
        self.assertNotIn('ksmOnly', initial_readback.get('state') or {})
        self.assertEqual('1', native_ack.get('configRevision'))

        events.clear()
        clear = {'hostUuid': 'host-1', 'operationUuid': 'r3-mixed-clear',
                 'expectedRevision': 1, 'desiredRevision': 2, 'policyMode': 'effective',
                 'licensePermit': {'managed': True, 'operationUuid': 'r3-permit-2',
                                   'expiresAt': int(time.time() * 1000) + 35000,
                                   'validForSeconds': 30},
                 'policy': {'ksm': {},
                            'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                                     'ramLimitBytes': 4096, 'cpuThresholdPercent': 40},
                            'writeback': {'enabled': False}}}
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(clear)
        violations = []
        if result.get('status') != 'Succeeded':
            violations.append('effective mixed clear did not succeed: %r' % result)
        if native_ack.get('configRevision') != '2':
            violations.append('clear did not advance native ACK: %r' % native_ack)
        if {key: native_ack.get(key) for key in
                ('run', 'pages_to_scan', 'sleep_millisecs', 'use_zero_pages')} != {
                    'run': '1', 'pages_to_scan': '600',
                    'sleep_millisecs': '30', 'use_zero_pages': '0'}:
            violations.append('clear did not preserve all four effective KSM values')
        actions = [entry[1] for entry in events if entry[0] == 'go']
        if not all(action in actions for action in
                   ('capacity-state', 'host-cpu-state', 'tuning-state')):
            violations.append('Go preflight did not read all service sections: %r' % actions)
        if not any(entry[0] == 'native-ack' for entry in events):
            violations.append('native KSM writer did not ACK the clear')
        if not all(action in actions for action in ('capacity', 'host-cpu', 'apply')):
            violations.append('Go service did not receive all policy writes: %r' % actions)
        ack_index = next((i for i, entry in enumerate(events) if entry[0] == 'native-ack'), None)
        if ack_index is not None and any(
                next((i for i, entry in enumerate(events)
                      if entry[0] == 'go' and entry[1] == action), ack_index + 1) > ack_index
                for action in ('capacity-state', 'host-cpu-state', 'tuning-state')):
            violations.append('native KSM write preceded Go preflight')
        last_put = max((i for i, entry in enumerate(events)
                        if entry[0] == 'go' and entry[1] in ('capacity', 'host-cpu', 'apply')),
                       default=-1)
        if last_put >= 0:
            for action in ('capacity-state', 'host-cpu-state', 'tuning-state'):
                if not any(i > last_put and entry[0] == 'go' and entry[1] == action
                           for i, entry in enumerate(events)):
                    violations.append('missing post-write GET for %s' % action)
        record = json.load(open(os.path.join(root, 'r3-mixed-clear.json')))
        if record.get('stage') != 'APPLIED':
            violations.append('clear journal stage is %r' % record.get('stage'))
        clear_readback = record.get('readback') or {}
        if not clear_readback.get('ksmReadback'):
            violations.append('clear journal lacks native KSM readback')
        capacity_receipt = (clear_readback.get('state') or {}).get('capacity')
        if (not isinstance(capacity_receipt, dict) or
                capacity_receipt.get('effective_logical_bytes') != 8192 or
                capacity_receipt.get('effective_physical_limit_bytes') != 4096 or
                capacity_receipt.get('apply_state') != 'APPLIED'):
            violations.append('clear journal lacks successful capacity receipt: %r' %
                              capacity_receipt)
        if 'ksmOnly' in (clear_readback.get('state') or {}):
            violations.append('mixed clear fabricated KSM-only proof')
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
                self.assertEqual('2', native_ack.get('configRevision'))
                self.assertEqual('UNKNOWN', record.get('stage'))
                readback = record.get('readback') or {}
                self.assertNotIn('ksmReadback', readback,
                                 'missing/unreadable native evidence must not be fabricated')
                self.assertNotIn('ksmOnly', (readback.get('state') or {}))
                actions = [entry[1] for entry in trace if entry[0] == 'go']
                self.assertFalse(set(actions).intersection({'capacity', 'host-cpu', 'apply'}),
                                 actions)

    def test_r3_delta_current_journal_without_ksm_proof_does_not_scan_history_for_clear(self):
        root = tempfile.mkdtemp(prefix='r3-delta-no-ksm-history-scan-')
        plugin, initial, service_writes, native_ack, native_command, native_conf = \
            self._r2_mixed_delta_fixture(root, 'delta-no-history')
        delta = self._r2_command(initial, 'r3-sparse-delta-current', {
            'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                     'ramLimitBytes': 4096, 'cpuThresholdPercent': 40},
            'writeback': {'enabled': False}}, mode='delta', revision=2)
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            delta_result = plugin.apply(delta)
        self.assertEqual('Succeeded', delta_result.get('status'), delta_result)
        current_record = json.load(open(os.path.join(root, delta['operationUuid'] + '.json')))
        self.assertNotIn('ksmReadback', current_record.get('readback') or {})
        self.assertNotIn('ksmOnly', (current_record.get('readback') or {}).get('state') or {})
        before_ack = dict(native_ack)
        before_writes = len(service_writes)
        clear = self._r2_command(initial, 'r3-clear-after-sparse-delta', {
            'ksm': {}, 'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                                'ramLimitBytes': 4096, 'cpuThresholdPercent': 40},
            'writeback': {'enabled': False}}, mode='effective', revision=3)
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            clear_result = plugin.apply(clear)
        self.assertEqual('Unknown', clear_result.get('status'), clear_result)
        self.assertEqual(before_ack, native_ack, 'clear searched an older KSM proof and wrote native')
        self.assertEqual(before_writes, len(service_writes), 'unsafe clear reached Go writes')
        self.assertEqual(native_conf, Path(plugin.KSM_CONF).read_bytes())
        clear_record = json.load(open(os.path.join(root, clear['operationUuid'] + '.json')))
        self.assertEqual('UNKNOWN', clear_record.get('stage'))
        self.assertNotIn('ksmReadback', clear_record.get('readback') or {})
        self.assertNotIn('ksmOnly', (clear_record.get('readback') or {}).get('state') or {})

    def test_r3_active_mixed_journal_is_never_promoted_to_ksm_only(self):
        root = tempfile.mkdtemp(prefix='r3-mixed-not-ksm-only-')
        plugin, _, _, _, _, _ = self._r2_mixed_delta_fixture(root, 'never-promote')
        result = {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                  'reasonCode': 'SERVICE_UNAVAILABLE'}
        promoted = plugin._promote_ksm_only_state(result)
        self.assertIs(result, promoted)
        self.assertEqual('Unknown', promoted.get('status'))
        self.assertNotIn('ksmOnly', promoted.get('state') or {})

    def _r3_disabled_unconfigured_prior(self, root, suffix, writeback_enabled=False):
        plugin, events, native_ack, service_state, _, native_command = \
            self._r3_stateful_mixed_fixture(root, 'disabled-unconfigured-' + suffix)
        Path(plugin.socket_path).touch()
        cap = service_state['capacity-state']
        cap.update({'desired': None, 'effective_logical_bytes': None,
                    'effective_physical_limit_bytes': None,
                    'apply_state': 'BLOCKED', 'reason': 'CAPACITY_NOT_CONFIGURED'})
        operation = 'r3-disabled-unconfigured-prior-' + suffix
        prior_command = {'hostUuid': 'host-1',
                         'operationUuid': operation,
                         'expectedRevision': 1, 'desiredRevision': 2,
                         'policyMode': 'effective',
                         'licensePermit': {'managed': True,
                                           'operationUuid': operation + '-permit',
                                           'expiresAt': int(time.time() * 1000) + 35000,
                                           'validForSeconds': 30},
                         'policy': {'ksm': {'enabled': True, 'pagesToScan': 600,
                                            'sleepMillis': 30, 'zeroPagesEnabled': False},
                                    'zram': {'enabled': False},
                                    'writeback': {'enabled': writeback_enabled}}}
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            established = plugin.apply(prior_command)
        self.assertEqual('Succeeded', established.get('status'), established)
        prior_record = json.load(open(os.path.join(root, operation + '.json')))
        prior_state = (prior_record.get('readback') or {}).get('state') or {}
        self.assertNotIn('capacity', prior_state)
        self.assertNotIn('ksmOnly', prior_state)
        self.assertIs(writeback_enabled, service_state['host-cpu-state']['efficiency_enabled'])
        return plugin, events, native_ack, service_state, native_command

    def test_r3_disabled_unmanaged_unconfigured_capacity_can_clear_ksm_without_capacity_put(self):
        root = tempfile.mkdtemp(prefix='r3-disabled-unconfigured-capacity-clear-')
        plugin, events, native_ack, _, native_command = \
            self._r3_disabled_unconfigured_prior(root, 'positive')
        events.clear()
        result, record, trace = self._r3_apply_effective_clear(
            plugin, root, events, native_command, 'r3-disabled-unconfigured-clear', 3,
            {'enabled': False})
        self.assertEqual('Succeeded', result.get('status'), result)
        self.assertEqual('3', native_ack.get('configRevision'))
        self.assertTrue((record.get('readback') or {}).get('ksmReadback'), record)
        self.assertNotIn('ksmOnly', (record.get('readback') or {}).get('state') or {})
        actions = [entry[1] for entry in trace if entry[0] == 'go']
        self.assertNotIn('capacity', actions, actions)
        self.assertNotIn('capacity', ((record.get('readback') or {}).get('state') or {}))

    def test_r3_unconfigured_capacity_clear_requires_exact_disabled_state(self):
        cases = (
            ('unknown-capacity-state', 'capacity_unknown'),
            ('other-block-reason', 'capacity_reason'),
            ('configured-capacity-fields', 'capacity_configured'),
            ('cpu-active', 'cpu_active'),
            ('writeback-active-drift', 'writeback_active_drift'),
        )
        for suffix, mutation in cases:
            with self.subTest(case=suffix):
                root = tempfile.mkdtemp(prefix='r3-unconfigured-capacity-negative-')
                plugin, events, native_ack, service_state, native_command = \
                    self._r3_disabled_unconfigured_prior(root, suffix)
                cap = service_state['capacity-state']
                if mutation == 'capacity_unknown':
                    cap['apply_state'] = 'UNKNOWN'
                elif mutation == 'capacity_reason':
                    cap['reason'] = 'CAPACITY_UNAVAILABLE'
                elif mutation == 'capacity_configured':
                    cap.update({'desired': {'logical_capacity_bytes': 8192},
                                'effective_logical_bytes': 8192,
                                'effective_physical_limit_bytes': 4096})
                elif mutation == 'cpu_active':
                    service_state['host-cpu-state']['efficiency_enabled'] = True
                elif mutation == 'writeback_active_drift':
                    service_state['tuning-state']['settings']['writeback']['enabled'] = True
                before_ack = dict(native_ack)
                before_conf = Path(plugin.KSM_CONF).read_bytes()
                result, record, trace = self._r3_apply_effective_clear(
                    plugin, root, events, native_command,
                    'r3-unconfigured-capacity-negative-' + suffix, 3, {'enabled': False})
                self.assertEqual('Unknown', result.get('status'), result)
                self.assertEqual('UNKNOWN', record.get('stage'), record)
                self.assertEqual(before_ack, native_ack, 'untrusted preflight wrote native KSM')
                self.assertEqual(before_conf, Path(plugin.KSM_CONF).read_bytes(),
                                 'untrusted preflight changed KSM config')
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

    def test_managed_marker_and_full_config_clear_advances_complete_native_ack(self):
        root = tempfile.mkdtemp(prefix='managed-marker-clear-ksm-')
        plugin, initial, native_ack, native_command, _ = self._managed_clear_fixture(root, 91, enabled=False)
        self.assertEqual({'run': '0', 'configRevision': '91', 'pages_to_scan': '600',
                          'sleep_millisecs': '30', 'use_zero_pages': '0'}, native_ack)
        with open(plugin.KSM_CONF) as stream:
            identity = dict(line.rstrip().split('=', 1) for line in stream if '=' in line)
        self.assertEqual({'CONFIG_REVISION': '91', 'KSM_ENABLED': '0',
                          'KSM_PAGES_TO_SCAN': '600', 'KSM_SLEEP_MILLISECS': '30',
                          'KSM_ZERO_PAGES': '0'}, identity)

        cleared = self._clear_managed_policy(initial, 'managed-marker-clear-after')
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(cleared)
        self.assertTrue(result['success'])
        self.assertEqual('Succeeded', result['status'])
        self.assertEqual('92', native_ack.get('configRevision'))
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
        plugin, initial, native_ack, native_command, _ = self._managed_clear_fixture(
            root, revision=121, enabled=False)
        first_clear = self._clear_managed_policy(initial, 'managed-clear-first-request')
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            first_result = plugin.apply(first_clear)
        self.assertTrue(first_result['success'])
        self.assertEqual('122', native_ack['configRevision'])
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
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            second_result = plugin.apply(second_clear)
        self.assertTrue(second_result['success'],
                        'complete current proof from the prior empty-KSM clear may advance one revision')
        self.assertEqual('Succeeded', second_result['status'])
        self.assertEqual('123', native_ack['configRevision'])
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
                plugin, initial, native_ack, native_command, _ = self._managed_clear_fixture(
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
                with patch.object(subprocess, 'check_output', side_effect=native_command):
                    result = plugin.apply(clear)
                if should_succeed:
                    self.assertTrue(result['success'],
                        '%s scope journal from the real manager should prove host-owned KSM' % scope)
                    self.assertEqual('Succeeded', result['status'])
                    self.assertEqual(str(initial['desiredRevision'] + 1),
                                     native_ack['configRevision'])
                else:
                    self.assertFalse(result.get('success'),
                        'VM-scoped journal must not be accepted as host KSM ownership proof')
                    self.assertEqual(str(initial['desiredRevision']),
                                     native_ack['configRevision'])

    def test_clear_does_not_treat_missing_current_boot_id_as_same_boot_proof(self):
        for index, missing_boot in enumerate((None, '')):
            with self.subTest(current_boot_id=missing_boot):
                root = tempfile.mkdtemp(prefix='managed-marker-clear-no-boot-id-')
                plugin, initial, native_ack, native_command, prior_path = self._managed_clear_fixture(
                    root, revision=131 + index, enabled=False)
                with open(prior_path) as stream:
                    prior = json.load(stream)
                prior['bootId'] = missing_boot
                with open(prior_path, 'w') as stream:
                    json.dump(prior, stream)

                cleared = self._clear_managed_policy(initial,
                    'managed-clear-no-boot-id-%s' % index)
                with patch.object(plugin, '_current_boot_id', return_value=missing_boot), \
                        patch.object(subprocess, 'check_output', side_effect=native_command):
                    result = plugin.apply(cleared)
                with open(os.path.join(root, cleared['operationUuid'] + '.json')) as stream:
                    record = json.load(stream)
                self.assertFalse(result.get('success'),
                    'an absent/blank boot ID is not current-boot evidence')
                self.assertNotEqual('Succeeded', result.get('status'))
                self.assertNotEqual('APPLIED', record.get('stage'))
                self.assertEqual(str(initial['desiredRevision']),
                                 native_ack['configRevision'])

    def test_clear_identity_config_parser_does_not_change_legacy_partial_apply_semantics(self):
        """Identity fields added for sparse clear must not steer ordinary partial KSM updates."""
        root = tempfile.mkdtemp(prefix='legacy-partial-ksm-config-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        with open(plugin.KSM_CONF, 'w') as stream:
            stream.write('CONFIG_REVISION=4\nKSM_ENABLED=0\nKSM_PAGES_TO_SCAN=100\n'
                         'KSM_SLEEP_MILLISECS=20\nKSM_ZERO_PAGES=0\n')
        native_ack = {'run': '1', 'configRevision': '4', 'pages_to_scan': '100',
                      'sleep_millisecs': '20', 'use_zero_pages': '0'}

        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                with open(plugin.KSM_CONF) as stream:
                    config = dict(line.rstrip().split('=', 1) for line in stream if '=' in line)
                native_ack.update({'run': '1' if config['KSM_ENABLED'] == '1' else '0',
                    'configRevision': config['CONFIG_REVISION'],
                    'pages_to_scan': config['KSM_PAGES_TO_SCAN'],
                    'sleep_millisecs': config['KSM_SLEEP_MILLISECS'],
                    'use_zero_pages': config['KSM_ZERO_PAGES']})
                return b''
            if argv[:2] in (['systemctl', 'enable'], ['systemctl', 'stop'], ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                return ''.join('%s=%s\n' % item for item in native_ack.items()).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        command = {'hostUuid': 'host-1', 'operationUuid': 'legacy-partial-ksm',
                   'expectedRevision': 4, 'desiredRevision': 5,
                   'licensePermit': {'managed': True, 'operationUuid': 'legacy-permit',
                       'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                   'policy': {'ksm': {'pagesToScan': 200}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            result = plugin.apply(command)
        self.assertTrue(result['success'])
        # Legacy sparse update has no enabled value: preserve the observed
        # native run state. The clear-only identity parser must not reinterpret
        # the persisted KSM_ENABLED line for this unrelated policy path.
        self.assertEqual('1', result['ksmReadback']['run'])

    def test_marker_alone_does_not_accept_invalid_prior_ksm_journal_as_clear_ownership(self):
        cases = ('old-boot', 'pending', 'mixed', 'malformed-zram-string',
                 'malformed-zram-number', 'malformed-writeback-string',
                 'malformed-writeback-number', 'corrupt', 'missing-ksmOnly')
        for index, mutation in enumerate(cases):
            with self.subTest(prior_journal=mutation):
                root = tempfile.mkdtemp(prefix='managed-marker-invalid-journal-')
                plugin, initial, native_ack, native_command, path = self._managed_clear_fixture(
                    root, 101 + index, enabled=False)
                if mutation == 'corrupt':
                    with open(path, 'w') as stream:
                        stream.write('{corrupt')
                else:
                    with open(path) as stream:
                        record = json.load(stream)
                    if mutation == 'old-boot':
                        record['bootId'] = 'stale-boot-id'
                    elif mutation == 'pending':
                        record['stage'] = 'PREPARING'
                    elif mutation == 'mixed':
                        record['policy']['zram']['enabled'] = True
                    elif mutation == 'malformed-zram-string':
                        record['policy']['zram']['enabled'] = 'false'
                    elif mutation == 'malformed-zram-number':
                        record['policy']['zram']['enabled'] = 1
                    elif mutation == 'malformed-writeback-string':
                        record['policy']['writeback']['enabled'] = 'false'
                    elif mutation == 'malformed-writeback-number':
                        record['policy']['writeback']['enabled'] = 1
                    elif mutation == 'missing-ksmOnly':
                        record['readback']['state'].pop('ksmOnly', None)
                    with open(path, 'w') as stream:
                        json.dump(record, stream)

                cleared = self._clear_managed_policy(initial,
                    'managed-marker-invalid-after-%s' % mutation)
                with patch.object(subprocess, 'check_output', side_effect=native_command):
                    result = plugin.apply(cleared)
                with open(os.path.join(root, cleared['operationUuid'] + '.json')) as stream:
                    result_record = json.load(stream)
                self.assertFalse(result.get('success'),
                    'a marker cannot bypass invalid current-boot KSM-only journal evidence')
                self.assertNotEqual('Succeeded', result.get('status'))
                self.assertNotEqual('APPLIED', result_record.get('stage'))
                self.assertEqual(str(initial['desiredRevision']), native_ack.get('configRevision'))

    def test_empty_clear_promotion_rejects_missing_or_invalid_zero_page_readback(self):
        for mutation, value in (('missing', None), ('invalid', 'not-a-bit')):
            with self.subTest(use_zero_pages=mutation):
                root = tempfile.mkdtemp(prefix='clear-zero-readback-%s-' % mutation)
                plugin, initial, native_ack, native_command, _ = self._managed_clear_fixture(
                    root, 111 if mutation == 'missing' else 112, enabled=False)
                cleared = self._clear_managed_policy(initial, 'clear-zero-proof-' + mutation)
                with patch.object(subprocess, 'check_output', side_effect=native_command):
                    result = plugin.apply(cleared)
                self.assertTrue(result['success'])

                def unavailable_service(action, payload):
                    raise OSError(errno.ENOENT, 'isolated fixture has no Go service socket')
                plugin.service_call = unavailable_service
                if value is None:
                    native_ack.pop('use_zero_pages', None)
                else:
                    native_ack['use_zero_pages'] = value
                with patch.object(subprocess, 'check_output', side_effect=native_command):
                    observed = json.loads(plugin.state({'body': json.dumps({
                        'hostUuid': 'host-1', 'operationUuid': 'clear-zero-observe-' + mutation})}))
                self.assertEqual('Unknown', observed['status'])
                self.assertFalse(observed['state']['safeToRemove'])

    def test_clear_final_ksm_override_never_journals_unacknowledged_revision(self):
        """Clearing a final managed KSM override advances only on native writer ack."""
        root = tempfile.mkdtemp(prefix='real-clear-final-ksm-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.service_call = plugin._call_local_service
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')

        native_ack = {}

        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                # Model the sole writer as an independent actor: it reads the
                # published config on service start and advances its own ack.
                with open(plugin.KSM_CONF) as stream:
                    config = dict(line.rstrip().split('=', 1) for line in stream if '=' in line)
                native_ack.update({
                    'run': '1' if config['KSM_ENABLED'] == '1' else '0',
                    'configRevision': config['CONFIG_REVISION'],
                    'pages_to_scan': config['KSM_PAGES_TO_SCAN'],
                    'sleep_millisecs': config['KSM_SLEEP_MILLISECS'],
                    'use_zero_pages': config['KSM_ZERO_PAGES']})
                return b''
            if argv[:2] in (['systemctl', 'enable'], ['systemctl', 'stop'], ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                return ''.join('%s=%s\n' % item for item in native_ack.items()).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        initial = {'hostUuid': 'host-1', 'operationUuid': 'clear-final-before',
                   'desiredRevision': 41,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-41',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': False, 'pagesToScan': 100,
                                      'sleepMillis': 20, 'zeroPagesEnabled': False},
                              'zram': {'enabled': False}, 'writeback': {'enabled': False}}}
        cleared = {'hostUuid': 'host-1', 'operationUuid': 'clear-final-after',
                   'expectedRevision': 41, 'desiredRevision': 42,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-42',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   # MN's sparse plan has no KSM member after the last local
                   # override is removed and there is no inherited KSM field.
                   'policy': {'ksm': {}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            first = plugin.apply(initial)
            self.assertTrue(first['success'])
            self.assertEqual(41, first['appliedRevision'])
            response = plugin.apply(cleared)

        with open(os.path.join(root, 'clear-final-after.json')) as stream:
            record = json.load(stream)
        with self.subTest(proof='clear must be APPLIED only after revisioned native readback'):
            self.assertTrue(response.get('success'))
            self.assertEqual('Succeeded', response.get('status'))
            self.assertEqual('42', native_ack.get('configRevision'),
                             'APPLIED revision must come from the sole writer, not the requested revision')
            self.assertEqual({'run': '0', 'configRevision': '42', 'pages_to_scan': '100',
                              'sleep_millisecs': '20', 'use_zero_pages': '0'}, native_ack)
            self.assertEqual(42, record.get('readback', {}).get('appliedRevision'))
            self.assertIs(True, record.get('readback', {}).get('state', {}).get('ksmOnly'))
        request_hash = record.get('requestHash')
        for _ in range(3):
            self.assertEqual(response, plugin.apply(cleared), 'same operation UUID remains idempotent')
        with open(os.path.join(root, 'clear-final-after.json')) as stream:
            replay_record = json.load(stream)
        self.assertEqual(request_hash, replay_record.get('requestHash'),
                         'resolved readback must not rewrite the original request identity')

        def unavailable_service(action, payload):
            raise OSError(errno.ENOENT, 'isolated fixture has no Go service socket')
        plugin.service_call = unavailable_service
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            observed = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'clear-final-state'})}))
            self.assertEqual('Succeeded', observed['status'])
            self.assertEqual(42, observed['appliedRevision'])
            self.assertIs(True, observed['state'].get('ksmOnly'))

            # The empty request policy must not erase the resolved native
            # proof: current-boot identity alone cannot hide parameter drift.
            stable = dict(native_ack)
            for field, wrong in (('run', '1'), ('pages_to_scan', '101'),
                                 ('sleep_millisecs', '21'), ('use_zero_pages', '1')):
                with self.subTest(field=field):
                    native_ack.update(stable)
                    native_ack[field] = wrong
                    drifted = json.loads(plugin.state({'body': json.dumps({
                        'hostUuid': 'host-1', 'operationUuid': 'clear-final-drift-' + field})}))
                    self.assertEqual('Unknown', drifted['status'])
                    self.assertFalse(drifted['state']['safeToRemove'])
            native_ack.update(stable)

    def test_clear_child_override_with_inherited_ksm_applies_inherited_values(self):
        """A non-empty inherited KSM target still goes through native revisioned apply."""
        root = tempfile.mkdtemp(prefix='real-clear-inherited-ksm-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')

        def native_command(argv, *args, **kwargs):
            if argv[:2] in (['systemctl', 'start'], ['systemctl', 'enable'],
                            ['systemctl', 'stop'], ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                with open(plugin.KSM_CONF) as stream:
                    config = dict(line.rstrip().split('=', 1) for line in stream if '=' in line)
                return ('run=%d\nconfigRevision=%s\npages_to_scan=%s\n'
                        'sleep_millisecs=%s\nuse_zero_pages=%s\n' % (
                            int(config['KSM_ENABLED']), config['CONFIG_REVISION'],
                            config['KSM_PAGES_TO_SCAN'], config['KSM_SLEEP_MILLISECS'],
                            config['KSM_ZERO_PAGES'])).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        command = {'hostUuid': 'host-1', 'operationUuid': 'clear-inherited-ksm',
                   'desiredRevision': 51,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-51',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': False, 'pagesToScan': 333,
                                      'sleepMillis': 25, 'zeroPagesEnabled': False},
                              'zram': {'enabled': False}, 'writeback': {'enabled': False}}}
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            response = plugin.apply(command)
        self.assertTrue(response['success'])
        self.assertEqual('Succeeded', response['status'])
        self.assertEqual(51, response['appliedRevision'])
        self.assertEqual({'run': '0', 'configRevision': '51', 'pages_to_scan': '333',
                          'sleep_millisecs': '25', 'use_zero_pages': '0'},
                         {key: response['ksmReadback'][key] for key in
                          ('run', 'configRevision', 'pages_to_scan', 'sleep_millisecs', 'use_zero_pages')})

    def test_clear_empty_ksm_target_preserves_existing_enabled_native_values(self):
        root = tempfile.mkdtemp(prefix='real-clear-on-ksm-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        native_ack = {}

        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                with open(plugin.KSM_CONF) as stream:
                    config = dict(line.rstrip().split('=', 1) for line in stream if '=' in line)
                native_ack.update({'run': '1' if config['KSM_ENABLED'] == '1' else '0',
                    'configRevision': config['CONFIG_REVISION'],
                    'pages_to_scan': config['KSM_PAGES_TO_SCAN'],
                    'sleep_millisecs': config['KSM_SLEEP_MILLISECS'],
                    'use_zero_pages': config['KSM_ZERO_PAGES']})
                return b''
            if argv[:2] in (['systemctl', 'enable'], ['systemctl', 'stop'], ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                return ''.join('%s=%s\n' % item for item in native_ack.items()).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        def command(operation, revision, ksm):
            return {'hostUuid': 'host-1', 'operationUuid': operation,
                    'desiredRevision': revision,
                    'licensePermit': {'managed': True, 'operationUuid': 'permit-%s' % revision,
                        'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                    'policy': {'ksm': ksm, 'zram': {'enabled': False},
                               'writeback': {'enabled': False}}}

        initial = command('clear-on-before', 71,
                          {'enabled': True, 'pagesToScan': 444, 'sleepMillis': 35,
                           'zeroPagesEnabled': True})
        cleared = command('clear-on-after', 72, {})
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            self.assertTrue(plugin.apply(initial)['success'])
            response = plugin.apply(cleared)
        self.assertTrue(response.get('success'))
        self.assertEqual('Succeeded', response.get('status'))
        self.assertEqual({'run': '1', 'configRevision': '72', 'pages_to_scan': '444',
                          'sleep_millisecs': '35', 'use_zero_pages': '1'}, native_ack)

    def test_empty_ksm_target_does_not_take_over_unmanaged_native_controller(self):
        root = tempfile.mkdtemp(prefix='real-empty-unmanaged-ksm-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        command = {'hostUuid': 'host-1', 'operationUuid': 'empty-unmanaged-ksm',
                   'desiredRevision': 61,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-61',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        with patch.object(plugin, '_prepare_managed_ksm_ownership', wraps=plugin._prepare_managed_ksm_ownership) as takeover, \
                patch.object(subprocess, 'check_output', side_effect=AssertionError('unmanaged KSM must not be touched')):
            response = plugin.apply(command)
        self.assertTrue(response['success'])
        self.assertFalse(takeover.called)
        self.assertFalse(os.path.exists(plugin.KSM_CONF))
        with open(os.path.join(root, 'empty-unmanaged-ksm.json')) as stream:
            record = json.load(stream)
        self.assertIsNot(True, record.get('readback', {}).get('state', {}).get('ksmOnly'))

    def test_clear_empty_ksm_target_with_stale_writer_ack_is_not_applied(self):
        root = tempfile.mkdtemp(prefix='real-clear-stale-ack-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = os.path.join(root, 'ksmtuned-zstack')
        plugin.ksm_apply_timeout = 0
        native_ack = {}
        hold_ack = [False]

        def native_command(argv, *args, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                if not hold_ack[0]:
                    with open(plugin.KSM_CONF) as stream:
                        config = dict(line.rstrip().split('=', 1) for line in stream if '=' in line)
                    native_ack.update({'run': '0', 'configRevision': config['CONFIG_REVISION'],
                        'pages_to_scan': config['KSM_PAGES_TO_SCAN'],
                        'sleep_millisecs': config['KSM_SLEEP_MILLISECS'],
                        'use_zero_pages': config['KSM_ZERO_PAGES']})
                return b''
            if argv[:2] in (['systemctl', 'enable'], ['systemctl', 'stop'], ['systemctl', 'disable']):
                return b''
            if argv and argv[0] == plugin.KSM_SCRIPT:
                return ''.join('%s=%s\n' % item for item in native_ack.items()).encode('ascii')
            raise AssertionError('unexpected native command: %r' % (argv,))

        def command(operation, revision, ksm):
            return {'hostUuid': 'host-1', 'operationUuid': operation,
                    'desiredRevision': revision,
                    'licensePermit': {'managed': True, 'operationUuid': 'permit-%s' % revision,
                        'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                    'policy': {'ksm': ksm, 'zram': {'enabled': False},
                               'writeback': {'enabled': False}}}

        with patch.object(subprocess, 'check_output', side_effect=native_command):
            first = plugin.apply(command('clear-stale-before', 81,
                {'enabled': False, 'pagesToScan': 555, 'sleepMillis': 40,
                 'zeroPagesEnabled': False}))
            self.assertTrue(first['success'])
            hold_ack[0] = True
            response = plugin.apply(command('clear-stale-after', 82, {}))
        with open(os.path.join(root, 'clear-stale-after.json')) as stream:
            record = json.load(stream)
        with self.subTest(ack='stale'):
            self.assertFalse(response.get('success'), 'requested revision is not writer acknowledgement')
            self.assertNotEqual('Succeeded', response.get('status'))
            self.assertNotEqual('APPLIED', record.get('stage'))
            self.assertEqual('81', native_ack.get('configRevision'))

        hold_ack[0] = False
        with patch.object(subprocess, 'check_output', side_effect=native_command):
            baseline = plugin.apply(command('clear-missing-before', 83,
                {'enabled': False, 'pagesToScan': 556, 'sleepMillis': 40,
                 'zeroPagesEnabled': False}))
            self.assertTrue(baseline['success'])
            native_ack.clear()
            missing = plugin.apply(command('clear-missing-after', 84, {}))
        with open(os.path.join(root, 'clear-missing-after.json')) as stream:
            missing_record = json.load(stream)
        with self.subTest(ack='missing'):
            self.assertFalse(missing.get('success'), 'missing native receipt cannot be inferred from config')
            self.assertNotEqual('Succeeded', missing.get('status'))
            self.assertNotEqual('APPLIED', missing_record.get('stage'))

    def test_real_ksm_fallback_rejects_current_and_record_empty_boot(self):
        root = tempfile.mkdtemp(prefix='real-empty-boot-')
        plugin, command, path = self._real_applied_ksm_fixture(root, 42)
        with open(path) as stream:
            record = json.load(stream)
        for boot in (None, ''):
            with self.subTest(boot=boot):
                record['bootId'] = boot
                with open(path, 'w') as stream:
                    json.dump(record, stream)
                with patch.object(plugin, '_current_boot_id', return_value=boot), \
                        patch.object(subprocess, 'check_output', return_value=(
                            b'run=1\nconfigRevision=42\npages_to_scan=2000\n'
                            b'sleep_millisecs=20\nuse_zero_pages=1\n')):
                    response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
                self.assertEqual('Unknown', response['status'])
                self.assertFalse(response['state']['safeToRemove'])

    def test_real_ksm_fallback_rejects_record_not_matching_active_control(self):
        root = tempfile.mkdtemp(prefix='real-active-mismatch-')
        plugin, command, path = self._real_applied_ksm_fixture(root, 43)
        with open(path) as stream:
            record = json.load(stream)
        record['operationUuid'] = 'other-operation'
        with open(path, 'w') as stream:
            json.dump(record, stream)
        with patch.object(subprocess, 'check_output', return_value=(
                b'run=1\nconfigRevision=43\npages_to_scan=2000\n'
                b'sleep_millisecs=20\nuse_zero_pages=1\n')):
            response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['state']['safeToRemove'])

    def test_real_ksm_fallback_rejects_malformed_readback_state_and_revision(self):
        for mutation in ('none', 'list', 'string', 'state-list', 'marker-int', 'marker-string', 'bool-revision'):
            with self.subTest(mutation=mutation):
                root = tempfile.mkdtemp(prefix='real-malformed-%s-' % mutation)
                plugin, command, path = self._real_applied_ksm_fixture(root, 44)
                with open(path) as stream:
                    record = json.load(stream)
                if mutation == 'none': record['readback'] = None
                elif mutation == 'list': record['readback'] = []
                elif mutation == 'string': record['readback'] = 'Succeeded'
                elif mutation == 'state-list': record['readback']['state'] = []
                elif mutation == 'marker-int': record['readback']['state']['ksmOnly'] = 1
                elif mutation == 'marker-string': record['readback']['state']['ksmOnly'] = 'true'
                else: record['desiredRevision'] = True
                with open(path, 'w') as stream:
                    json.dump(record, stream)
                # A corrupt bool must be rejected before probing native values;
                # the True string intentionally matches this corrupt receipt.
                revision = 'True' if mutation == 'bool-revision' else '44'
                native = ('run=1\nconfigRevision=%s\npages_to_scan=2000\n'
                          'sleep_millisecs=20\nuse_zero_pages=1\n' % revision).encode('ascii')
                with patch.object(subprocess, 'check_output', return_value=native):
                    response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
                self.assertIsInstance(response, dict, mutation)
                self.assertEqual('Unknown', response.get('status'), mutation)
                self.assertFalse(response['state']['safeToRemove'], mutation)

    def test_real_ksm_fallback_probes_native_drift_after_valid_journal(self):
        root = tempfile.mkdtemp(prefix='real-native-drift-')
        plugin, command, path = self._real_applied_ksm_fixture(root, 45)
        actual = {'run': '1', 'configRevision': '45', 'pages_to_scan': '2000',
                  'sleep_millisecs': '20', 'use_zero_pages': '1'}
        for field, wrong in [('run', '0'), ('configRevision', '44'), ('pages_to_scan', '1'),
                             ('sleep_millisecs', '99'), ('use_zero_pages', '0')]:
            with self.subTest(field=field):
                values = dict(actual); values[field] = wrong
                native = ''.join('%s=%s\n' % item for item in values.items()).encode('ascii')
                with patch.object(plugin, '_ksm_readback_matches', wraps=plugin._ksm_readback_matches) as probe, \
                        patch.object(subprocess, 'check_output', return_value=native):
                    response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
                self.assertEqual('Unknown', response['status'])
                self.assertFalse(response['state']['safeToRemove'])
                probe.assert_called_once()

    def test_ksm_fallback_rejects_empty_current_boot_evidence(self):
        root = tempfile.mkdtemp(prefix='state-ksm-empty-boot-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-empty-boot',
                   'desiredRevision': 32, 'policy': {'ksm': {'enabled': True}}}
        with patch.object(plugin, '_current_boot_id', return_value=None), \
                patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
            plugin._set_active_control(command['operationUuid'])
            plugin._record_operation(command, 'APPLIED', {'status': 'Succeeded'})
            response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['state']['safeToRemove'])
        readback.assert_not_called()

    def test_ksm_fallback_rejects_journal_different_from_active_control(self):
        root = tempfile.mkdtemp(prefix='state-ksm-active-mismatch-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-journal-a',
                   'desiredRevision': 33, 'policy': {'ksm': {'enabled': True}}}
        plugin._set_active_control('ksm-active-b')
        plugin._record_operation(command, 'APPLIED', {'status': 'Succeeded'})
        with patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
            response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['state']['safeToRemove'])
        readback.assert_not_called()

    def test_ksm_fallback_rejects_malformed_readback_and_ksm_only_coercions(self):
        for malformed in (None, [], 'Succeeded'):
            for marker in (1, 'true'):
                root = tempfile.mkdtemp(prefix='state-ksm-malformed-')
                plugin = self._ksm_only_state_plugin(root)
                command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-malformed',
                           'desiredRevision': 34,
                           'policy': {'ksm': {'enabled': True}}}
                plugin._set_active_control(command['operationUuid'])
                plugin._record_operation(command, 'APPLIED', malformed)
                path = os.path.join(root, command['operationUuid'] + '.json')
                with open(path) as stream:
                    record = json.load(stream)
                if isinstance(record.get('readback'), dict):
                    record['readback']['state'] = {'ksmOnly': marker}
                with open(path, 'w') as stream:
                    json.dump(record, stream)
                with patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                        patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                        patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
                    response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
                self.assertFalse(isinstance(response, dict) and response.get('success') is True)
                if isinstance(response, dict) and isinstance(response.get('state'), dict):
                    self.assertFalse(response['state'].get('safeToRemove', False))
                readback.assert_not_called()

    def test_real_ksm_apply_rejects_boolean_revision(self):
        for key in ('desiredRevision', 'expectedRevision'):
            for value in (True, False):
                with self.subTest(key=key, value=value):
                    root = tempfile.mkdtemp(prefix='real-ksm-bool-revision-')
                    plugin = self._ksm_only_state_plugin(root)
                    command = {'hostUuid': 'host-1',
                               'operationUuid': 'ksm-bool-revision-%s-%s' % (key, value),
                               key: value,
                               'policy': {'ksm': {'enabled': True}, 'zram': {'enabled': False}}}
                    with patch.object(plugin, 'discover_capabilities') as discover, \
                            patch.object(subprocess, 'check_output') as native:
                        response = plugin.apply(command)
                    self.assertFalse(response['success'])
                    self.assertEqual('INVALID_POLICY_REVISION:%s' % key,
                                     response.get('reason'))
                    self.assertEqual('INVALID_POLICY', response.get('reasonCode'))
                    discover.assert_not_called()
                    native.assert_not_called()

    def test_ksm_fallback_checks_real_native_revision_and_parameter_drift(self):
        root = tempfile.mkdtemp(prefix='state-ksm-native-drift-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-native-drift',
                   'desiredRevision': 35, 'policy': {'ksm': {
                       'enabled': True, 'pagesToScan': 2000, 'sleepMillis': 20,
                       'zeroPagesEnabled': True}}}
        plugin._set_active_control(command['operationUuid'])
        plugin._record_operation(command, 'APPLIED',
                                 {'status': 'Succeeded', 'state': {'source': 'ksmtuned'}})
        with patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=(
                    b'run=1\nconfigRevision=34\npages_to_scan=1\n'
                    b'sleep_millisecs=99\nuse_zero_pages=0\n')):
            response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        self.assertFalse(response['state']['safeToRemove'])

    def test_real_mixed_zram_policy_does_not_persist_ksm_only_marker(self):
        root = tempfile.mkdtemp(prefix='real-mixed-memory-')
        _plugin, _events, _native_ack, _service_state, _faults, _native_command = \
            self._r3_stateful_mixed_fixture(root, 'real-mixed')
        # The helper above exercises a successful, fully acknowledged mixed
        # KSM+ZRAM apply against stateful capacity/CPU/tuning service records.
        record = json.load(open(os.path.join(root, 'r3-fixture-real-mixed.json')))
        self.assertEqual('APPLIED', record.get('stage'))
        self.assertTrue((record.get('readback') or {}).get('success'))
        self.assertNotIn('ksmOnly', ((record.get('readback') or {}).get('state') or {}))
        with open(os.path.join(root, 'r3-fixture-real-mixed.json')) as stream:
            journal = json.load(stream)
        self.assertNotIn('ksmOnly', (journal.get('readback') or {}).get('state') or {})

    def test_reachable_observer_preserves_current_ksm_only_proof_on_and_off(self):
        for enabled in (True, False):
            root = tempfile.mkdtemp(prefix='state-ksm-observer-')
            plugin = self._ksm_only_state_plugin(root)
            command = {'hostUuid': 'host-1', 'operationUuid': 'observer-ksm',
                       'desiredRevision': 22, 'policy': {'ksm': {
                           'enabled': enabled, 'pagesToScan': 2000,
                           'sleepMillis': 20, 'zeroPagesEnabled': False}}}
            plugin._set_active_control(command['operationUuid'])
            plugin._record_operation(command, 'APPLIED', {'success': True,
                'status': 'Succeeded', 'state': {'ksmOnly': True}})
            snapshot = {'success': True, 'status': 'Succeeded', 'state': {
                'mode': 'observe', 'resource_authorized': False,
                'lifecycle': {'activeState': 'compatibility', 'paused': False},
                'host_zram': {'quality': 'unavailable', 'device': '', 'pool_generation': ''}}}
            native = ('run=%s\nconfigRevision=22\npages_to_scan=2000\n'
                      'sleep_millisecs=20\nuse_zero_pages=0\n' % ('1' if enabled else '0')).encode('ascii')
            with patch.object(plugin, '_dispatch', return_value=snapshot), \
                    patch.object(subprocess, 'check_output', return_value=native):
                response = json.loads(plugin.state({'body': json.dumps({
                    'hostUuid': 'host-1', 'operationUuid': 'observation'})}))
            self.assertTrue(response['state'].get('ksmOnly'))
            self.assertEqual('Succeeded', response['status'])
            self.assertEqual('compatibility', response['state']['lifecycle']['activeState'])
            self.assertEqual('unavailable', response['state']['host_zram']['quality'])
            self.assertEqual(command['operationUuid'], response['state']['lastConfirmedOperationUuid'])
            self.assertEqual(enabled, response['state']['actual']['ksm']['enabled'])
            self.assertFalse(response['state']['safeToRemove'])

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

    def test_state_observation_uuid_does_not_mask_active_ksm_journal(self):
        """Periodic MN observations use a fresh UUID, not the policy UUID."""
        root = tempfile.mkdtemp(prefix='state-ksm-observation-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-policy-1',
                   'desiredRevision': 22,
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                      'sleepMillis': 20, 'zeroPagesEnabled': True},
                              'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        plugin._set_active_control('ksm-policy-1')
        plugin._record_operation(command, 'APPLIED',
                                 {'success': True, 'status': 'Succeeded',
                                  'state': {'ksmOnly': True}})
        with patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=(
                    b'run=1\npages_to_scan=2000\nsleep_millisecs=20\nuse_zero_pages=1\n')):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1',
                'operationUuid': 'fresh-observation-uuid'})}))
        self.assertEqual('Succeeded', response['status'])
        self.assertTrue(response['success'])
        self.assertEqual(22, response['appliedRevision'])
        self.assertTrue(response['state'].get('ksmOnly'))
        readback.assert_called_once_with(command['policy']['ksm'], 22)

    def test_state_does_not_promote_applied_ksm_journal_without_active_control(self):
        """A durable journal alone is not proof of current host ownership."""
        root = tempfile.mkdtemp(prefix='state-ksm-no-control-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'orphaned-policy-1',
                   'desiredRevision': 23,
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000},
                              'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        plugin._record_operation(command, 'APPLIED',
                                 {'success': True, 'status': 'Succeeded',
                                  'state': {'ksmOnly': True}})
        with patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1',
                'operationUuid': 'orphaned-policy-1'})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        self.assertFalse(response['state']['safeToRemove'])
        readback.assert_not_called()

    def test_state_keeps_unknown_for_stale_ksm_journal_after_go_socket_failure(self):
        root = tempfile.mkdtemp(prefix='state-ksm-stale-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-state-stale',
                   'desiredRevision': 18,
                   'policy': {'ksm': {'enabled': True}, 'zram': {'enabled': False}}}
        plugin._set_active_control(command['operationUuid'])
        plugin._record_operation(command, 'APPLIED',
                                 {'success': True, 'status': 'Succeeded',
                                  'state': {'ksmOnly': True}})
        path = os.path.join(root, command['operationUuid'] + '.json')
        with open(path) as stream:
            record = json.load(stream)
        record['bootId'] = 'different-boot'
        with open(path, 'w') as stream:
            json.dump(record, stream)
        with patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': command['operationUuid']})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        self.assertFalse(response['state']['safeToRemove'])
        readback.assert_not_called()

    def test_state_keeps_unknown_and_not_removable_without_ksm_journal(self):
        root = tempfile.mkdtemp(prefix='state-ksm-no-journal-')
        plugin = self._ksm_only_state_plugin(root)
        with patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1'})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        self.assertFalse(response['state']['safeToRemove'])

    def test_cold_ksm_native_read_is_marked_partial_without_claiming_control_success(self):
        root = tempfile.mkdtemp(prefix='state-ksm-partial-no-journal-')
        plugin = self._ksm_only_state_plugin(root)
        with patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=(
                    b'run=1\npages_to_scan=1250\nsleep_millisecs=10\nuse_zero_pages=0\n')):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'partial-state-1'})}))

        self.assertEqual('KSM_NATIVE_PARTIAL', response.get('observationKind'))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        self.assertNotIn('appliedRevision', response)
        self.assertTrue(response['coldKsmAdmissionReady'])
        self.assertEqual('LOCAL_CONTROL_FENCE_CLEAR', response['coldKsmAdmissionReason'])
        self.assertFalse(response['state']['safeToRemove'])
        self.assertNotIn('ksmOnly', response['state'])
        self.assertEqual({'enabled': True, 'zeroPagesEnabled': False,
                          'pagesToScan': 1250, 'sleepMillis': 10},
                         response['state']['actual']['ksm'])

    def test_cold_ksm_partial_admission_refuses_old_local_unknown_even_with_empty_database(self):
        root = tempfile.mkdtemp(prefix='state-ksm-partial-local-unknown-')
        plugin = self._ksm_only_state_plugin(root)
        old = {'hostUuid': 'host-1', 'operationUuid': 'old-local-unknown',
               'desiredRevision': 7, 'policy': {'ksm': {'enabled': True}}}
        plugin._record_operation(old, 'UNKNOWN', {'success': False, 'status': 'Unknown'})
        with patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=(
                    b'run=1\npages_to_scan=1250\nsleep_millisecs=10\nuse_zero_pages=0\n')):
            observation = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'partial-state-local-unknown'})}))

        self.assertEqual('KSM_NATIVE_PARTIAL', observation.get('observationKind'))
        self.assertEqual('Unknown', observation['status'])
        self.assertFalse(observation['success'])
        self.assertFalse(observation.get('coldKsmAdmissionReady'))
        self.assertEqual('LOCAL_CONTROL_FENCE_UNKNOWN', observation.get('coldKsmAdmissionReason'))

        command = {'action': 'apply', 'hostUuid': 'host-1', 'operationUuid': 'new-ksm-request',
                   'desiredRevision': 8, 'requiresKsmNativePartialFence': True,
                   'policy': {'ksm': {'enabled': True}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        with patch.object(plugin, 'discover_capabilities', return_value={
                'supported': True, 'reasonCode': 'SUPPORTED', 'ksm': True,
                'ksmZeroPages': False, 'zram': False, 'writeback': False}), \
                patch.object(subprocess, 'check_output') as native:
            applied = plugin.apply(command)
        self.assertFalse(applied['success'])
        self.assertEqual('Unknown', applied['status'])
        self.assertEqual('LOCAL_CONTROL_FENCE_UNKNOWN', applied.get('reasonCode'))
        native.assert_not_called()

    def test_cold_ksm_apply_rechecks_local_journal_after_database_admission(self):
        root = tempfile.mkdtemp(prefix='apply-ksm-partial-local-unknown-')
        plugin = self._ksm_only_state_plugin(root)
        old = {'hostUuid': 'host-1', 'operationUuid': 'old-local-unknown',
               'desiredRevision': 7, 'policy': {'ksm': {'enabled': True}}}
        plugin._record_operation(old, 'UNKNOWN', {'success': False, 'status': 'Unknown'})
        command = {'action': 'apply', 'scope': 'Host', 'resourceUuid': 'host-1',
                   'hostUuid': 'host-1', 'operationUuid': 'new-ksm-request',
                   'desiredRevision': 8, 'requiresKsmNativePartialFence': True,
                   'ksmNativeObservationBootId': plugin._current_boot_id(),
                   'ksmNativeObservationSampleTime': int(time.time() * 1000),
                   'policy': {'ksm': {'enabled': True}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        with patch.object(plugin, 'discover_capabilities', return_value={
                'supported': True, 'reasonCode': 'SUPPORTED', 'ksm': True,
                'ksmZeroPages': False, 'zram': False, 'writeback': False}), \
                patch.object(subprocess, 'check_output') as native:
            applied = plugin.apply(command)
        self.assertFalse(applied['success'])
        self.assertEqual('Unknown', applied['status'])
        self.assertEqual('LOCAL_CONTROL_FENCE_UNKNOWN', applied.get('reasonCode'))
        self.assertFalse(os.path.exists(os.path.join(root, 'new-ksm-request.json')))
        native.assert_not_called()

    def test_cold_ksm_guard_accepts_each_configuration_origin(self):
        for scope in ('Host', 'Cluster', 'Global'):
            root = tempfile.mkdtemp(prefix='cold-ksm-origin-')
            plugin = self._ksm_only_state_plugin(root)
            command = {'action': 'apply', 'scope': scope, 'hostUuid': 'host-1',
                       'resourceUuid': {'Host': 'host-1', 'Cluster': 'cluster-1',
                                        'Global': 'global'}[scope],
                       'operationUuid': 'new-ksm-request', 'desiredRevision': 8,
                       'requiresKsmNativePartialFence': True,
                       'ksmNativeObservationBootId': plugin._current_boot_id(),
                       'ksmNativeObservationSampleTime': int(time.time() * 1000),
                       'policy': {'ksm': {'enabled': True}}}
            wire = json.loads(json.dumps(command))
            self.assertIs(type(wire['ksmNativeObservationSampleTime']), int)
            self.assertIsNone(plugin._validate_cold_ksm_partial_fence(wire), scope)

    def test_cold_ksm_guard_rejects_invalid_evidence_for_every_configuration_origin(self):
        for scope in ('Host', 'Cluster', 'Global'):
            for defect in ('expired', 'new_boot', 'float', 'boolean', 'missing', 'local_unknown'):
                root = tempfile.mkdtemp(prefix='cold-ksm-reject-')
                plugin = self._ksm_only_state_plugin(root)
                command = {'action': 'apply', 'scope': scope, 'hostUuid': 'host-1',
                           'resourceUuid': {'Host': 'host-1', 'Cluster': 'cluster-1',
                                            'Global': 'global'}[scope],
                           'operationUuid': 'new-ksm-request', 'desiredRevision': 8,
                           'requiresKsmNativePartialFence': True,
                           'ksmNativeObservationBootId': plugin._current_boot_id(),
                           'ksmNativeObservationSampleTime': int(time.time() * 1000),
                           'policy': {'ksm': {'enabled': True}}}
                if defect == 'expired':
                    command['ksmNativeObservationSampleTime'] -= 300001
                elif defect == 'new_boot':
                    command['ksmNativeObservationBootId'] = 'old-boot'
                elif defect == 'float':
                    command['ksmNativeObservationSampleTime'] = float(command['ksmNativeObservationSampleTime'])
                elif defect == 'boolean':
                    command['ksmNativeObservationSampleTime'] = True
                elif defect == 'missing':
                    del command['ksmNativeObservationSampleTime']
                elif defect == 'local_unknown':
                    plugin._record_operation({'hostUuid': 'host-1', 'operationUuid': 'ordinary-unknown',
                                              'policy': {'ksm': {'enabled': True}}},
                                             'UNKNOWN', {'success': False, 'status': 'Unknown'})
                with patch.object(plugin, 'discover_capabilities', return_value={
                        'supported': True, 'reasonCode': 'SUPPORTED', 'ksm': True,
                        'ksmZeroPages': False, 'zram': False, 'writeback': False}), \
                        patch.object(subprocess, 'check_output') as native:
                    result = plugin.apply(json.loads(json.dumps(command)))
                self.assertEqual('Unknown', result['status'], (scope, defect))
                self.assertEqual('LOCAL_CONTROL_FENCE_UNKNOWN', result.get('reasonCode'), (scope, defect))
                self.assertFalse(os.path.exists(os.path.join(root, 'new-ksm-request.json')))
                native.assert_not_called()

    def test_cold_ksm_local_fence_requires_empty_active_control_and_terminal_records(self):
        root = tempfile.mkdtemp(prefix='state-ksm-partial-local-fence-')
        plugin = self._ksm_only_state_plugin(root)
        self.assertTrue(plugin._cold_ksm_local_fence_clear())
        unknown = {'hostUuid': 'host-1', 'operationUuid': 'other-request',
                   'policy': {'ksm': {'enabled': True}}}
        plugin._record_operation(unknown, 'PREPARING')
        self.assertFalse(plugin._cold_ksm_local_fence_clear(),
                         'another UUID in PREPARING is still a local executor fence')
        plugin._record_operation(unknown, 'APPLIED', {'success': True, 'status': 'Succeeded'})
        self.assertTrue(plugin._cold_ksm_local_fence_clear())
        plugin._set_active_control('unknown-control')
        self.assertFalse(plugin._cold_ksm_local_fence_clear(),
                         'a non-empty active-control reference is never interpreted as empty')

        os.unlink(plugin.active_control_path)
        lock_path = os.path.join(root, '.host-control.flock')
        os.unlink(lock_path)
        target = os.path.join(root, 'outside-lock-target')
        with open(target, 'w') as stream:
            stream.write('untouched')
        os.symlink(target, lock_path)
        self.assertFalse(plugin._cold_ksm_local_fence_clear(),
                         'a symlinked writer lock cannot establish a local safety fence')
        with open(target, 'r') as stream:
            self.assertEqual('untouched', stream.read())

    def test_cold_ksm_local_fence_does_not_skip_nested_control_journals(self):
        root = tempfile.mkdtemp(prefix='state-ksm-partial-nested-fence-')
        plugin = self._ksm_only_state_plugin(root)
        drain_dir = os.path.join(root, 'drain')
        os.mkdir(drain_dir)
        with open(os.path.join(drain_dir, 'drain.receipt.json'), 'w') as stream:
            stream.write('{"stage":"DRAINING"}')
        self.assertFalse(plugin._cold_ksm_local_fence_clear(),
                         'a nested drain receipt must not be skipped when Go is unavailable')
        os.unlink(os.path.join(drain_dir, 'drain.receipt.json'))

        maintenance_dir = os.path.join(root, 'backend-maintenance')
        os.mkdir(maintenance_dir)
        with open(os.path.join(maintenance_dir, 'maintenance.intent.json'), 'w') as stream:
            stream.write('{"stage":"PREPARING"}')
        self.assertFalse(plugin._cold_ksm_local_fence_clear(),
                         'a nested maintenance intent must remain a fence')
        os.unlink(os.path.join(maintenance_dir, 'maintenance.intent.json'))

        vm_dir = os.path.join(root, 'vm-bindings')
        os.mkdir(vm_dir)
        with open(os.path.join(vm_dir, 'a' * 32 + '.json'), 'w') as stream:
            json.dump({'resourceUuid': 'a' * 32, 'expectedInstanceGeneration': 'instance-1',
                       'participation': 'allow', 'operationUuid': 'b' * 32,
                       'updatedAt': 123}, stream)
        self.assertTrue(plugin._cold_ksm_local_fence_clear(),
                        'a well-formed durable VM binding is not an in-flight task')
        with open(os.path.join(vm_dir, '.binding-temporary'), 'w') as stream:
            stream.write('{}')
        self.assertFalse(plugin._cold_ksm_local_fence_clear(),
                         'an in-progress VM binding write must fail closed')

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

    def test_non_enoent_service_failure_does_not_emit_partial_ksm_observation(self):
        root = tempfile.mkdtemp(prefix='state-ksm-partial-eio-')
        plugin = self._ksm_only_state_plugin(root)
        with patch.object(plugin, '_dispatch', side_effect=socket.error(errno.EIO, 'service failure')), \
                patch.object(subprocess, 'check_output', return_value=(
                    b'run=1\npages_to_scan=1250\nsleep_millisecs=10\nuse_zero_pages=0\n')):
            response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1'})}))
        self.assertNotEqual('KSM_NATIVE_PARTIAL', response.get('observationKind'))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])

    def test_state_keeps_unknown_when_current_ksm_journal_native_readback_drifts(self):
        root = tempfile.mkdtemp(prefix='state-ksm-drift-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-state-drift',
                   'desiredRevision': 19,
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000},
                              'zram': {'enabled': False}}}
        plugin._set_active_control(command['operationUuid'])
        plugin._record_operation(command, 'APPLIED',
                                 {'success': True, 'status': 'Succeeded',
                                  'state': {'ksmOnly': True}})
        with patch.object(plugin, '_ksm_readback_matches', return_value=False) as readback, \
                patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=b'run=0\npages_to_scan=1\n'):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': command['operationUuid']})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        self.assertFalse(response['state']['safeToRemove'])
        readback.assert_called_once_with(command['policy']['ksm'], 19)

    def test_state_recovers_current_boot_disabled_ksm_policy_only(self):
        root = tempfile.mkdtemp(prefix='state-ksm-disabled-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-state-disabled',
                   'desiredRevision': 20,
                   'policy': {'ksm': {'enabled': False, 'pagesToScan': 2000},
                              'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        plugin._set_active_control(command['operationUuid'])
        plugin._record_operation(command, 'APPLIED',
                                 {'success': True, 'status': 'Succeeded',
                                  'state': {'ksmOnly': True}})
        with patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=b'run=0\npages_to_scan=2000\n'):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': command['operationUuid']})}))
        self.assertEqual('Succeeded', response['status'])
        self.assertTrue(response['success'])
        self.assertEqual(20, response['appliedRevision'])
        self.assertFalse(response['state']['safeToRemove'])
        readback.assert_called_once_with(command['policy']['ksm'], 20)

    def test_state_does_not_promote_ksm_evidence_while_pending_receipt_exists(self):
        root = tempfile.mkdtemp(prefix='state-ksm-pending-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-state-pending',
                   'desiredRevision': 21,
                   'policy': {'ksm': {'enabled': True}, 'zram': {'enabled': False}}}
        plugin._set_active_control(command['operationUuid'])
        plugin._record_operation(command, 'APPLIED',
                                 {'success': True, 'status': 'Succeeded',
                                  'state': {'ksmOnly': True}})
        pending = {'success': False, 'status': 'Unknown',
                   'state': {'pending_operations': ['receipt-1']},
                   'reason': 'pending'}
        with patch.object(plugin, '_ksm_readback_matches', return_value=True), \
                patch.object(plugin, '_dispatch', return_value=pending), \
                patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': command['operationUuid']})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        self.assertFalse(response['state']['safeToRemove'])

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

    def test_ksm_status_empty_or_old_revision_is_not_success(self):
        root = tempfile.mkdtemp(prefix='ksm-readback-')
        plugin = MemoryOptimizationPlugin()
        plugin.ksm_apply_timeout = 0
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LEASE = os.path.join(root, 'ksm.lease')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        command = {'desiredRevision': 9, 'operationUuid': 'ksm-readback',
                   'licensePermit': {'validForSeconds': 30,
                                     'operationUuid': 'managed-host-1',
                                     'expiresAt': int(time.time() * 1000) + 30000},
                   'policy': {'ksm': {'enabled': True}}}
        with patch.object(plugin, '_prepare_managed_ksm_ownership'), \
                patch.object(subprocess, 'check_output', side_effect=[b'', b'', b'', b'']):
            with self.assertRaises(RuntimeError):
                plugin._apply_ksm_policy(command)
        with patch.object(plugin, '_prepare_managed_ksm_ownership'), \
                patch.object(subprocess, 'check_output', side_effect=[b'', b'', b'',
                                                                      b'configRevision=8\nrun=1\n']):
            with self.assertRaises(RuntimeError):
                plugin._apply_ksm_policy(command)

    def test_ksm_configuration_does_not_require_product_license_permit(self):
        """Agent configuration is not a commercial-license enforcement point.

        The management node has already authorized this configuration request.
        KVM Agent must accept it without a short-lived licensePermit or a
        host-service lease, while retaining host identity and operation CAS.
        """
        root = tempfile.mkdtemp(prefix='ksm-no-permit-')
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload: {'status': 'Succeeded'})
        plugin.configure({'hostUuid': 'host-1234567890', 'operationDir': root})
        command = {
            'action': 'apply', 'scope': 'host',
            'hostUuid': 'host-1234567890',
            'operationUuid': 'ksm-config-no-permit',
            'expectedRevision': 6, 'desiredRevision': 7,
            'policy': {'ksm': {'enabled': True,
                               'zeroPagesEnabled': True}}}
        with patch.object(plugin, 'discover_capabilities', return_value={
                'supported': True, 'ksm': True, 'ksmZeroPages': True,
                'zram': True, 'writeback': True}), \
                patch.object(plugin, '_apply_ksm_policy', return_value={
                    'configRevision': '7', 'run': '1'} ) as apply_ksm:
            result = plugin.apply(command)
        self.assertTrue(result['success'], result)
        self.assertEqual('Succeeded', result['status'])
        apply_ksm.assert_called_once_with(command)
        with open(os.path.join(root, 'ksm-config-no-permit.json')) as stream:
            journal = json.load(stream)
        self.assertEqual('host-1234567890', journal['hostUuid'])
        self.assertEqual(7, journal['desiredRevision'])

    def test_explicit_ksm_disable_without_permit_preserves_identity_and_revision(self):
        """An explicit disable remains an ordinary CAS-protected operation."""
        root = tempfile.mkdtemp(prefix='ksm-disable-no-permit-')
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload: {'status': 'Succeeded'})
        plugin.configure({'hostUuid': 'host-1234567890', 'operationDir': root})
        command = {
            'action': 'apply', 'scope': 'host',
            'hostUuid': 'host-1234567890',
            'operationUuid': 'ksm-disable-no-permit',
            'expectedRevision': 7, 'desiredRevision': 8,
            'policy': {'ksm': {'enabled': False,
                               'zeroPagesEnabled': False}}}
        with patch.object(plugin, 'discover_capabilities', return_value={
                'supported': True, 'ksm': True, 'ksmZeroPages': True,
                'zram': True, 'writeback': True}), \
                patch.object(plugin, '_apply_ksm_policy', return_value={
                    'configRevision': '8', 'run': '0'}) as apply_ksm:
            result = plugin.apply(command)
        self.assertTrue(result['success'], result)
        self.assertEqual('Succeeded', result['status'])
        apply_ksm.assert_called_once_with(command)
        with open(os.path.join(root, 'ksm-disable-no-permit.json')) as stream:
            journal = json.load(stream)
        self.assertEqual('host-1234567890', journal['hostUuid'])
        self.assertEqual(8, journal['desiredRevision'])

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
    def test_ksm_tuning_only_preserves_native_run_state_before_any_write(self):
        """Tuning-only policies preserve native run=0/1 and fail closed if unknown."""
        def make_plugin(enabled=None):
            root = tempfile.mkdtemp(prefix='ksm-preserve-run-')
            plugin = self._ksm_only_state_plugin(root)
            plugin.ksm_apply_timeout = 0
            plugin.KSM_SCRIPT = '/test/ksmtuned-zstack'
            policy = {'pagesToScan': 1250, 'sleepMillis': 60,
                      'zeroPagesEnabled': True}
            if enabled is not None:
                policy['enabled'] = enabled
            command = {'desiredRevision': 23, 'policy': {'ksm': policy}}
            return plugin, command

        for native_run in ('0', '1'):
            with self.subTest(native_run=native_run):
                plugin, command = make_plugin()
                published = []
                calls = []

                def check_output(argv, **kwargs):
                    calls.append(list(argv))
                    if argv == [plugin.KSM_SCRIPT, 'status']:
                        if len([call for call in calls
                                if call == [plugin.KSM_SCRIPT, 'status']]) == 1:
                            return ('run=%s\n' % native_run).encode('ascii')
                        config = dict(line.split('=', 1) for line in published[0].splitlines())
                        return ('run=%s\nconfigRevision=%s\npages_to_scan=%s\n'
                                'sleep_millisecs=%s\nuse_zero_pages=%s\n' %
                                (config['KSM_ENABLED'], config['CONFIG_REVISION'],
                                 config['KSM_PAGES_TO_SCAN'], config['KSM_SLEEP_MILLISECS'],
                                 config['KSM_ZERO_PAGES'])).encode('ascii')
                    return b''

                with patch.object(plugin, '_existing_ksm_config', return_value={}), \
                        patch.object(plugin, '_prepare_managed_ksm_ownership') as prepare, \
                        patch.object(plugin, '_publish_ksm_config',
                                     side_effect=lambda content: published.append(content)), \
                        patch.object(subprocess, 'check_output', side_effect=check_output):
                    plugin._apply_ksm_policy(command)

                self.assertEqual(native_run, dict(line.split('=', 1)
                                                  for line in published[0].splitlines())['KSM_ENABLED'])
                self.assertEqual([plugin.KSM_SCRIPT, 'status'], calls[0])
                first_mutation = next(i for i, call in enumerate(calls)
                                      if call and call[0] == 'systemctl')
                self.assertGreater(first_mutation, 0)
                prepare.assert_called_once_with()

        unknown_results = (
            ('empty', b''),
            ('invalid-run', b'run=2\n'),
            ('command-failed', subprocess.CalledProcessError(1, 'ksmtuned-zstack status')),
            ('io-failed', OSError('status read failed')),
        )
        for label, result in unknown_results:
            with self.subTest(unknown=label):
                plugin, command = make_plugin()
                calls = []
                def fail_or_return(argv, **kwargs):
                    calls.append(list(argv))
                    if isinstance(result, BaseException):
                        raise result
                    return result

                with patch.object(plugin, '_existing_ksm_config', return_value={}), \
                        patch.object(plugin, '_prepare_managed_ksm_ownership') as prepare, \
                        patch.object(plugin, '_publish_ksm_config') as publish, \
                        patch.object(subprocess, 'check_output',
                                     side_effect=fail_or_return):
                    with self.assertRaisesRegex(ValueError, 'KSM_EXISTING_RUN_STATE_UNKNOWN'):
                        plugin._apply_ksm_policy(command)

                self.assertEqual([[plugin.KSM_SCRIPT, 'status']], calls)
                prepare.assert_not_called()
                publish.assert_not_called()

        for explicit in (True, False):
            with self.subTest(explicit_enabled=explicit):
                plugin, command = make_plugin(enabled=explicit)
                published = []
                calls = []

                def check_explicit(argv, **kwargs):
                    calls.append(list(argv))
                    if argv == [plugin.KSM_SCRIPT, 'status']:
                        config = dict(line.split('=', 1) for line in published[0].splitlines())
                        return ('run=%s\nconfigRevision=%s\npages_to_scan=%s\n'
                                'sleep_millisecs=%s\nuse_zero_pages=%s\n' %
                                (config['KSM_ENABLED'], config['CONFIG_REVISION'],
                                 config['KSM_PAGES_TO_SCAN'], config['KSM_SLEEP_MILLISECS'],
                                 config['KSM_ZERO_PAGES'])).encode('ascii')
                    return b''

                with patch.object(plugin, '_existing_ksm_config', return_value={}), \
                        patch.object(plugin, '_prepare_managed_ksm_ownership'), \
                        patch.object(plugin, '_publish_ksm_config',
                                     side_effect=lambda content: published.append(content)), \
                        patch.object(subprocess, 'check_output', side_effect=check_explicit):
                    plugin._apply_ksm_policy(command)

                config = dict(line.split('=', 1) for line in published[0].splitlines())
                self.assertEqual('1' if explicit else '0', config['KSM_ENABLED'])
                self.assertNotEqual([plugin.KSM_SCRIPT, 'status'], calls[0])

        for existing_enabled in (0, 1):
            with self.subTest(existing_enabled=existing_enabled):
                plugin, command = make_plugin()
                published = []
                calls = []

                def check_existing(argv, **kwargs):
                    calls.append(list(argv))
                    if argv == [plugin.KSM_SCRIPT, 'status']:
                        config = dict(line.split('=', 1) for line in published[0].splitlines())
                        return ('run=%s\nconfigRevision=%s\npages_to_scan=%s\n'
                                'sleep_millisecs=%s\nuse_zero_pages=%s\n' %
                                (config['KSM_ENABLED'], config['CONFIG_REVISION'],
                                 config['KSM_PAGES_TO_SCAN'], config['KSM_SLEEP_MILLISECS'],
                                 config['KSM_ZERO_PAGES'])).encode('ascii')
                    return b''

                with patch.object(plugin, '_existing_ksm_config',
                                  return_value={'KSM_ENABLED': existing_enabled}), \
                        patch.object(plugin, '_prepare_managed_ksm_ownership'), \
                        patch.object(plugin, '_publish_ksm_config',
                                     side_effect=lambda content: published.append(content)), \
                        patch.object(subprocess, 'check_output', side_effect=check_existing):
                    plugin._apply_ksm_policy(command)

                config = dict(line.split('=', 1) for line in published[0].splitlines())
                self.assertEqual(str(existing_enabled), config['KSM_ENABLED'])
                self.assertNotEqual([plugin.KSM_SCRIPT, 'status'], calls[0])

        plugin, command = make_plugin()
        command['policy']['ksm'] = {}
        with patch.object(plugin, '_managed_ksm_clear_ack', return_value=None), \
                patch.object(plugin, '_prepare_managed_ksm_ownership') as prepare, \
                patch.object(plugin, '_publish_ksm_config') as publish, \
                patch.object(subprocess, 'check_output') as check_output:
            plugin._apply_ksm_policy(command)
        prepare.assert_not_called()
        publish.assert_not_called()
        check_output.assert_not_called()

    def test_service_cpu_apply_preserves_native_cpu_state_shape(self):
        calls = []
        cpu_state = {'revision': 4, 'efficiency_enabled': False,
                     'idle_cpu_threshold_percent': 80, 'idle_duration_seconds': 60}
        tuning_state = {'revision': 6, 'settings': {
            'required_available_bytes': 0, 'host_floor_bytes': 0,
            'metadata_reserve_bytes': 0, 'transient_reserve_bytes': 0,
            'writeback': {'enabled': False,
                          'batch_bytes': 64 * 1024 * 1024,
                          'idle_observation_seconds': 0,
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
        command = {'operationUuid': 'cpu-shape-1', 'expectedRevision': 6,
                   'policy': {'zram': {'enabled': True,
                                       'cpuThresholdPercent': 5,
                                       'cpuHoldSeconds': 80},
                              'writeback': {'enabled': False}}}
        result = plugin._apply_service_policy(command)
        self.assertEqual('Succeeded', result['status'])
        cpu = next(payload for action, payload in calls if action == 'host-cpu')
        self.assertEqual(4, cpu['expected_revision'])
        self.assertTrue(cpu['efficiency_enabled'])
        self.assertEqual(5, cpu['idle_cpu_threshold_percent'])
        self.assertEqual(80, cpu['idle_duration_seconds'])

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

    def test_ksmtuned_keeps_applied_policy_after_time_advance_and_restart(self):
        """An expired/missing product lease must not hand KSM back to legacy."""
        root = tempfile.mkdtemp(prefix='ksm-persistent-policy-')
        for name, value in (('run', '0'), ('pages_to_scan', '1'),
                            ('sleep_millisecs', '10'), ('use_zero_pages', '0')):
            with open(os.path.join(root, name), 'w') as stream:
                stream.write(value)
        conf = os.path.join(root, 'ksmtuned.conf')
        with open(conf, 'w') as stream:
            stream.write('CONFIG_REVISION=3\nKSM_ENABLED=1\nKSM_PAGES_TO_SCAN=500\n'
                         'KSM_SLEEP_MILLISECS=10\nKSM_ZERO_PAGES=1\n')
        bindir = tempfile.mkdtemp(prefix='fake-systemctl-persistent-')
        fake = os.path.join(bindir, 'systemctl')
        with open(fake, 'w') as stream:
            stream.write('#!/bin/sh\n'
                         'case "$1" in\n'
                         '  is-enabled) echo enabled;;\n'
                         '  is-active) echo inactive;;\n'
                         'esac\nexit 0\n')
        os.chmod(fake, 0o755)
        script = os.path.join(os.path.dirname(__file__),
                              '../../ansible/memory-optimization/ksmtuned/ksmtuned-zstack')
        env = dict(os.environ)
        env.update({'PATH': bindir + ':' + env.get('PATH', ''),
                    'KSMTUNED_KSM_ROOT': root, 'KSMTUNED_CONF': conf,
                    # Deliberately point at a non-existent lease: policy
                    # persistence must not depend on an Agent renewal.
                    'KSMTUNED_LEASE': os.path.join(root, 'missing.lease'),
                    'KSMTUNED_MARKER': os.path.join(root, 'marker'),
                    'KSMTUNED_LOCK': os.path.join(root, 'lock'),
                    'KSMTUNED_SNAPSHOT': os.path.join(root, 'snapshot'),
                    'KSMTUNED_APPLIED': os.path.join(root, 'applied'),
                    'KSMTUNED_ENGINE': self.ksm_engine,
                    'KSMTUNED_RUNTIME_DIR': os.path.join(root, 'runtime'),
                    'KSMTUNED_MEMINFO': '/proc/meminfo',
                    'KSMTUNED_CONTROL_INTERVAL': '0.05'})
        for _ in range(2):
            process = subprocess.Popen([script, 'run'], env=env)
            try:
                time.sleep(0.35)
            finally:
                process.terminate()
                process.wait()
            self.assertEqual('1', open(os.path.join(root, 'run')).read().strip())
            self.assertTrue(os.path.exists(os.path.join(root, 'marker')))
    def test_ksm_start_without_matching_status_is_not_success(self):
        root = tempfile.mkdtemp(prefix='ksm-start-')
        plugin = MemoryOptimizationPlugin()
        plugin.ksm_apply_timeout = 0
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LEASE = os.path.join(root, 'ksm.lease')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        command = {'desiredRevision': 10, 'operationUuid': 'ksm-start',
                   'licensePermit': {'validForSeconds': 30,
                                     'operationUuid': 'managed-host-1',
                                     'expiresAt': int(time.time() * 1000) + 30000},
                   'policy': {'ksm': {'enabled': True}}}
        with patch.object(plugin, '_prepare_managed_ksm_ownership'), \
                patch.object(subprocess, 'check_output', side_effect=[b'', b'',
                                                                      b'', b'configRevision=9\nrun=1\n']):
            with self.assertRaises(RuntimeError):
                plugin._apply_ksm_policy(command)

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

    def test_ksmtuned_expired_legacy_lease_does_not_stop_applied_ksm(self):
        root = tempfile.mkdtemp(prefix='ksm-root-')
        for name, value in (('run', '1'), ('pages_to_scan', '1250'),
                            ('sleep_millisecs', '10'), ('use_zero_pages', '0')):
            with open(os.path.join(root, name), 'w') as stream:
                stream.write(value)
        conf = os.path.join(root, 'ksmtuned.conf')
        lease = os.path.join(root, 'ksm.lease')
        marker = os.path.join(root, 'owner')
        with open(conf, 'w') as stream:
            stream.write('CONFIG_REVISION=1\nKSM_PAGES_TO_SCAN=500\n'
                         'KSM_SLEEP_MILLISECS=10\nKSM_ZERO_PAGES=1\n')
        with open(lease, 'w') as stream:
            stream.write('owner=expired\nexpires=1\nrevision=1\n')
        with open(marker, 'w') as stream:
            stream.write('ksmtuned\n')
        script = os.path.join(os.path.dirname(__file__), '../../ansible/memory-optimization/ksmtuned/ksmtuned-zstack')
        env = dict(os.environ)
        env.update({'KSMTUNED_KSM_ROOT': root, 'KSMTUNED_CONF': conf,
                    'KSMTUNED_ENGINE': self.ksm_engine,
                    'KSMTUNED_RUNTIME_DIR': os.path.join(root, 'runtime'),
                    'KSMTUNED_MEMINFO': '/proc/meminfo',
                    'KSMTUNED_LEASE': lease, 'KSMTUNED_MARKER': marker,
                    'KSMTUNED_LOCK': os.path.join(root, 'writer.lock')})
        process = subprocess.Popen([script, 'run'], env=env)
        try:
            time.sleep(0.35)
        finally:
            process.terminate()
            process.wait()
        self.assertEqual('1', open(os.path.join(root, 'run')).read().strip())
        self.assertTrue(os.path.exists(marker))

    def test_legacy_mode_only_reads_existing_ksm_state(self):
        plugin = MemoryOptimizationPlugin()
        plugin.KSM_SCRIPT = '/does/not/exist'
        with patch.object(subprocess, 'check_output', return_value=b'run=1\npages_to_scan=321\n') as run:
            result = plugin._ksm_readback_matches({'enabled': True}, 1)
        self.assertFalse(result)
        run.assert_called_once_with(['/does/not/exist', 'status'])

    def test_active_ksm_starts_managed_writer_unit(self):
        root = tempfile.mkdtemp(prefix='managed-ksm-')
        plugin = MemoryOptimizationPlugin()
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LEASE = os.path.join(root, 'ksm.lease')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        plugin.KSM_SCRIPT = '/usr/libexec/zstack/ksmtuned-zstack'
        command = {'desiredRevision': 3,
                   'licensePermit': {'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30,
                                     'operationUuid': 'managed-host-1'},
                   'operationUuid': 'apply-ksm-unit',
                   'policy': {'ksm': {'enabled': True}}}
        with patch.object(plugin, '_prepare_managed_ksm_ownership'), \
             patch.object(subprocess, 'check_output',
                          side_effect=[b'', b'',
                                       b'configRevision=3\nrun=1\n'
                                       b'pages_to_scan=2000\nsleep_millisecs=20\n']) as run:
            plugin._apply_ksm_policy(command)
        self.assertEqual(['systemctl', 'enable', 'zstack-ksmtuned.service'],
                         run.call_args_list[0][0][0])
        self.assertEqual(['systemctl', 'start', 'zstack-ksmtuned.service'],
                         run.call_args_list[1][0][0])
        self.assertEqual([plugin.KSM_SCRIPT, 'status'],
                         run.call_args_list[2][0][0])

    def test_explicit_legacy_resume_preserves_disabled_legacy_service(self):
        root = tempfile.mkdtemp(prefix='ksm-disabled-')
        for name, value in (('run', '1'), ('pages_to_scan', '1250'),
                            ('sleep_millisecs', '10'), ('use_zero_pages', '0')):
            with open(os.path.join(root, name), 'w') as stream:
                stream.write(value)
        conf = os.path.join(root, 'ksmtuned.conf')
        lease = os.path.join(root, 'ksm.lease')
        marker = os.path.join(root, 'owner')
        snapshot = os.path.join(root, 'snapshot')
        with open(conf, 'w') as stream:
            stream.write('CONFIG_REVISION=1\nKSM_PAGES_TO_SCAN=500\nKSM_SLEEP_MILLISECS=10\n')
        with open(lease, 'w') as stream:
            stream.write('owner=expired\nexpires=1\nrevision=1\n')
        with open(snapshot, 'w') as stream:
            stream.write('enabled=disabled\nactive=inactive\nrun=1\n'
                         'pages_to_scan=1250\nsleep_millisecs=10\nuse_zero_pages=0\n')
        with open(marker, 'w') as stream:
            stream.write('ksmtuned\n')
        bindir = tempfile.mkdtemp(prefix='fake-systemctl-')
        calls = os.path.join(root, 'systemctl.calls')
        fake = os.path.join(bindir, 'systemctl')
        with open(fake, 'w') as stream:
            stream.write('#!/bin/bash\necho "$@" >> "%s"\n' % calls)
            stream.write('unit="${@: -1}"\n')
            stream.write('case "$1" in\n')
            stream.write('  show) if [ "$unit" = ksmtuned.service ]; then echo LoadState=loaded; else echo LoadState=not-found; fi ;;\n')
            stream.write('  is-enabled) if [ "$unit" = ksmtuned.service ]; then echo disabled; else echo not-found; fi ;;\n')
            stream.write('  is-active) if [ "$unit" = ksmtuned.service ]; then echo inactive; else echo not-found; fi ;;\n')
            stream.write('  stop|disable|unmask|daemon-reload) exit 0 ;;\n')
            stream.write('  *) exit 0 ;;\nesac\n')
        os.chmod(fake, 0o755)
        fake_id = os.path.join(bindir, 'id')
        with open(fake_id, 'w') as stream:
            stream.write('#!/bin/sh\necho 0\n')
        os.chmod(fake_id, 0o755)
        script = os.path.join(os.path.dirname(__file__), '../../ansible/memory-optimization/ksmtuned/ksmtuned-zstack')
        env = dict(os.environ)
        env.update({'PATH': bindir + ':' + env.get('PATH', ''),
                    'KSMTUNED_KSM_ROOT': root, 'KSMTUNED_CONF': conf,
                    'KSMTUNED_LEASE': lease, 'KSMTUNED_MARKER': marker,
                    'KSMTUNED_SNAPSHOT': snapshot,
                    'KSMTUNED_LOCK': os.path.join(root, 'writer.lock')})
        # Legacy handoff remains an explicit user operation; it is no longer
        # triggered by a missing or expired product-license lease.
        try:
            subprocess.check_output([script, 'legacy-resume'], env=env,
                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            self.fail('legacy-resume failed: %s' % exc.output)
        with open(calls) as stream:
            recorded = stream.read()
        self.assertIn('stop zstack-ksmtuned.service', recorded)
        self.assertIn('disable zstack-ksmtuned.service', recorded)
        self.assertIn('unmask ksmtuned.service', recorded)
        self.assertNotIn('start ksmtuned.service', recorded)
        self.assertFalse(os.path.exists(marker))

    def test_ksmd_budget_uses_single_core_cpu_seconds(self):
        script = os.path.join(os.path.dirname(__file__), '../../ansible/memory-optimization/ksmtuned/ksmtuned-zstack')
        with self.assertRaises(subprocess.CalledProcessError):
            subprocess.check_output([script, 'cpu-percent', '100', '150', '100'])

    def test_ksmtuned_run_reloads_revision_and_static_policy(self):
        root = tempfile.mkdtemp(prefix='ksm-dynamic-')
        for name, value in (('run', '1'), ('pages_to_scan', '10'),
                            ('sleep_millisecs', '10'), ('use_zero_pages', '0')):
            with open(os.path.join(root, name), 'w') as stream:
                stream.write(value)
        conf = os.path.join(root, 'ksmtuned.conf')
        lease = os.path.join(root, 'ksm.lease')
        with open(conf, 'w') as stream:
            stream.write('CONFIG_REVISION=1\nKSM_PAGES_TO_SCAN=10\n'
                         'KSM_SLEEP_MILLISECS=10\nKSM_ZERO_PAGES=0\n')
        with open(lease, 'w') as stream:
            stream.write('owner=dynamic\nexpires=%d\nrevision=1\n' % (int(time.time()) + 10))
        script = os.path.join(os.path.dirname(__file__), '../../ansible/memory-optimization/ksmtuned/ksmtuned-zstack')
        env = dict(os.environ)
        env.update({'KSMTUNED_KSM_ROOT': root, 'KSMTUNED_CONF': conf,
                    'KSMTUNED_ENGINE': self.ksm_engine,
                    'KSMTUNED_RUNTIME_DIR': os.path.join(root, 'runtime'),
                    'KSMTUNED_MEMINFO': '/proc/meminfo',
                    'KSMTUNED_LEASE': lease, 'KSMTUNED_MARKER': os.path.join(root, 'marker'),
                    'KSMTUNED_LOCK': os.path.join(root, 'lock'),
                    'KSMTUNED_SNAPSHOT': os.path.join(root, 'snapshot'),
                    'KSMTUNED_CONTROL_INTERVAL': '0.05'})
        process = subprocess.Popen([script, 'run'], env=env)
        try:
            time.sleep(0.2)
            with open(conf, 'w') as stream:
                stream.write('CONFIG_REVISION=2\nKSM_PAGES_TO_SCAN=10\n'
                             'KSM_SLEEP_MILLISECS=22\nKSM_ZERO_PAGES=1\n')
            with open(lease, 'w') as stream:
                stream.write('owner=dynamic\nexpires=%d\nrevision=2\n' % (int(time.time()) + 10))
            time.sleep(1.3)
        finally:
            process.terminate()
            process.wait()
        self.assertEqual('22', open(os.path.join(root, 'sleep_millisecs')).read().strip())
        self.assertEqual('1', open(os.path.join(root, 'use_zero_pages')).read().strip())

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

    def test_local_service_uses_http_over_unix_socket_and_normalizes_response(self):
        path = tempfile.mktemp(prefix='memory-optimization-', suffix='.sock')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(1)

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
            self.assertTrue(request.startswith(b'GET /v1/status HTTP/1.1'))
            body = json.dumps({'status': 'Succeeded', 'state': {'revision': 3}}).encode('utf-8')
            conn.sendall(('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                          'Content-Length: %d\r\nConnection: close\r\n\r\n' % len(body)).encode('ascii') + body)
            conn.close()

        thread = threading.Thread(target=serve_once)
        thread.daemon = True
        thread.start()
        try:
            plugin = MemoryOptimizationPlugin()
            plugin.configure({'hostUuid': 'host-1', 'socketPath': path})
            response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'op-1'})}))
            self.assertEqual('Succeeded', response['status'])
            self.assertEqual('op-1', response['operationUuid'])
        finally:
            thread.join(2)
            listener.close()
            if os.path.exists(path):
                os.unlink(path)

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
            # The CLI deliberately checks privilege before reading its config.
            # Use non-interactive sudo when available so the test reaches the
            # strict request decoder and then fails only on the absent config.
            if os.geteuid() != 0:
                sudo = shutil.which('sudo')
                if sudo:
                    command = [sudo, '-n'] + command
                else:
                    self.skipTest('root or non-interactive sudo is required to reach Go request decoder')
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

    def test_local_service_uses_per_request_communication_budget_and_query_contract(self):
        calls = []

        class Response(object):
            status = 200
            def read(self, _limit):
                return b'{"status":"Succeeded"}'

        class Connection(object):
            def __init__(self, path, timeout):
                calls.append(('init', path, timeout))
            def request(self, method, path, body=None, headers=None):
                calls.append(('request', method, path, body))
            def getresponse(self):
                return Response()
            def close(self):
                pass

        plugin = MemoryOptimizationPlugin()
        plugin.configure({'socketPath': '/tmp/memory-service.sock'})
        with patch.object(memory_optimization, '_UnixHTTPConnection', Connection):
            plugin._call_local_service('apply', {
                'operationUuid': 'op-1', 'communication': {
                    'requestBytes': 4096, 'responseBytes': 8192,
                    'communicationSeconds': 7}, 'request_id': 'op-1'})
            plugin._call_local_service('state', {
                'hostUuid': 'host-1', 'communication': {
                    'requestBytes': 4096, 'responseBytes': 8192,
                    'communicationSeconds': 3}})
        self.assertEqual(('init', '/tmp/memory-service.sock', 7), calls[0])
        self.assertEqual(('init', '/tmp/memory-service.sock', 3), calls[2])
        self.assertEqual('/v1/zram/tuning', calls[1][2])
        self.assertEqual('/v1/status', calls[3][2])

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

    def _run_fail_closed_apply_with_vm_shards(self, shard_failure=None):
        calls = []
        cap = {'revision': 5, 'desired': {'configured': {
            'logical_capacity': {'bytes': 8192},
            'physical_memory_limit': {'bytes': 4096}}},
            'effective_logical_bytes': 8192, 'effective_physical_limit_bytes': 4096,
            'apply_state': 'APPLIED', 'reason': 'NATIVE_CONFIGURATION_VERIFIED'}
        cpu = {'revision': 7, 'efficiency_enabled': True,
               'idle_cpu_threshold_percent': 5, 'idle_duration_seconds': 60}
        vm_settings = {'revision': 4, 'mode': 'all_running', 'vm_uuids': []}
        tuning_settings = {'vm_management': vm_settings, 'writeback': {'enabled': False}}
        tuning = {'revision': 10, 'settings': tuning_settings}

        class Response(object):
            def __init__(self, status, body):
                self.status, self.body = status, json.dumps(body).encode('utf-8')
            def read(self, _limit):
                return self.body

        class Connection(object):
            def __init__(self, _path, timeout):
                self.timeout, self.method, self.path, self.body = timeout, None, None, None
            def request(self, method, path, body=None, headers=None):
                self.method, self.path = method, path
                self.body = json.loads(body) if body else {}
                calls.append((method, path, self.body))
            def getresponse(self):
                if self.path == '/v1/zram/config' and self.method == 'GET':
                    return Response(200, cap)
                if self.path == '/v1/efficiency/policy' and self.method == 'GET':
                    return Response(200, cpu)
                if self.path == '/v1/zram/tuning' and self.method == 'GET':
                    return Response(200, tuning)
                if self.path == '/v1/vm-management':
                    return Response(200, {'settings': vm_settings})
                if self.path == '/v1/efficiency/policy' and self.method == 'PUT':
                    cpu.update({'revision': cpu['revision'] + 1,
                                'efficiency_enabled': self.body['efficiency_enabled'],
                                'idle_cpu_threshold_percent': self.body['idle_cpu_threshold_percent'],
                                'idle_duration_seconds': self.body['idle_duration_seconds']})
                    return Response(200, dict(cpu, request_id=self.body['request_id']))
                if self.path == '/v1/zram/config' and self.method == 'PUT':
                    cap['revision'] += 1
                    return Response(200, dict(cap, request_id=self.body['request_id']))
                if self.path.endswith('/shard/stage'):
                    if shard_failure == 'stage':
                        return Response(409, {'error': 'stage rejected'})
                    return Response(200, {'status': 'Succeeded'})
                if self.path.endswith('/shard/commit'):
                    if shard_failure in ('commit', 'commit_lost'):
                        vm_settings.update({'revision': 5, 'mode': 'list',
                                            'vm_uuids': ['a' * 32]})
                        if shard_failure == 'commit_lost':
                            raise IOError('simulated lost commit response')
                        return Response(409, {'error': 'commit rejected'})
                    vm_settings.update({'revision': 5, 'mode': 'list',
                                        'vm_uuids': ['a' * 32]})
                    return Response(200, {'status': 'Succeeded'})
                if self.path.endswith('/shard/cancel'):
                    return Response(200, {'status': 'Cancelled'})
                if self.path == '/v1/zram/tuning' and self.method == 'PUT':
                    submitted = self.body['settings']
                    for key, value in submitted.items():
                        if key != 'vm_management':
                            tuning_settings[key] = value
                    tuning_settings['vm_management'] = dict(vm_settings)
                    tuning.update({'revision': 11})
                    return Response(200, dict(tuning, request_id=self.body['request_id']))
                raise AssertionError('unexpected request %s %s' % (self.method, self.path))
            def close(self):
                pass

        directory = tempfile.mkdtemp(prefix='memory-fail-closed-sequence-')
        self.addCleanup(shutil.rmtree, directory)
        config_directory = os.path.join(directory, 'zram-config')
        os.makedirs(config_directory)
        active_path = os.path.join(directory, 'active-control')
        with open(active_path, 'w') as stream:
            stream.write('prior-control')
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'socketPath': '/tmp/memory-service.sock',
                          'operationDir': directory, 'activeControlPath': active_path})
        plugin.zram_config_path = os.path.join(config_directory, 'config.json')
        plugin.zram_config_template_path = os.path.join(config_directory, 'vendor-config.json')
        authorized_config = {'version': 2, 'mode': 'reclaim', 'managed': True,
                             'resource_authorized': True,
                             'initial_efficiency_enabled': False}
        config_bytes = json.dumps(authorized_config, sort_keys=True).encode('utf-8')
        vendor_template = dict(authorized_config, mode='observe', resource_authorized=False)
        template_bytes = json.dumps(vendor_template, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        with open(plugin.zram_config_path, 'wb') as stream:
            stream.write(config_bytes)
        with open(plugin.zram_config_template_path, 'wb') as stream:
            stream.write(template_bytes)
        command = {'hostUuid': 'host-1', 'scope': 'Host', 'operationUuid': 'f' * 32,
                   'desiredRevision': 9, 'targetSnapshotGeneration': 'snapshot-9',
                   'policy': {'zram': {'enabled': True, 'logicalCapacityBytes': 8192,
                                       'ramLimitBytes': 4096, 'selectionMode': 'list',
                                       'selectedVmUuids': ['a' * 32]},
                              'writeback': {'enabled': False}}}
        with patch.object(memory_optimization, '_UnixHTTPConnection', Connection), \
                patch.object(plugin, 'discover_capabilities', return_value={
                    'supported': True, 'zram': True, 'writeback': True}), \
                patch.object(plugin, '_apply_ksm_policy', return_value=None):
            result = plugin.apply(command)
        return result, calls, plugin, active_path

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

    def test_wrapped_known_blocked_response_keeps_structured_state_and_null_revision(self):
        plugin = MemoryOptimizationPlugin()
        command = {'hostUuid': 'host-1', 'operationUuid': 'blocked-op'}
        blocked = {'success': False, 'status': 'Blocked', 'appliedRevision': None,
                   'reasonCode': 'NATIVE_POOL_UNQUALIFIED',
                   'blockers': [{'section': 'capacity', 'code': 'NATIVE_POOL_UNQUALIFIED'}],
                   'state': {'phase': 'BLOCKED', 'knownBlocked': True,
                             'blockers': [{'section': 'capacity',
                                           'code': 'NATIVE_POOL_UNQUALIFIED'}]}}
        with patch.object(plugin, 'apply', return_value=blocked):
            response = json.loads(plugin.apply_request({'body': json.dumps(command)}))
        self.assertEqual('Blocked', response['status'])
        self.assertFalse(response['success'])
        # jsonobject omits null-valued fields on the wire; Java's contract
        # treats omission as null for Blocked and must not infer Failed.
        self.assertIsNone(response.get('appliedRevision'))
        self.assertTrue(response['state']['knownBlocked'])
        self.assertEqual('NATIVE_POOL_UNQUALIFIED', response['blockers'][0]['code'])

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

    def _uncertain_recovery_fixture(self, post_fails=False, prior_active_old=False):
        directory = tempfile.mkdtemp(prefix='memory-recovery-apply-')
        self.addCleanup(shutil.rmtree, directory)
        active_path = os.path.join(directory, 'active-control')
        drain_uuid = '9' * 32
        old_uuid, new_uuid = 'a' * 32, 'b' * 32
        with open(active_path, 'w') as stream:
            stream.write(old_uuid if prior_active_old else drain_uuid)
        plugin = MemoryOptimizationPlugin()
        plugin.configure({'hostUuid': 'host-1', 'operationDir': directory,
                          'activeControlPath': active_path})
        old_path = plugin._operation_path(old_uuid)
        old_bytes = json.dumps({'operationUuid': old_uuid, 'stage': 'ACTIVATING',
                                'action': 'apply', 'hostUuid': 'host-1'}).encode('utf-8')
        with open(old_path, 'wb') as stream:
            stream.write(old_bytes)
        generation = 'c' * 64
        proof = {'maintenanceReady': True, 'maintenanceArchived': True,
                 'activeOperations': 0, 'oldPoolGeneration': generation,
                 'newPoolGeneration': None, 'readyForInitialization': True,
                 'originalDeviceInactive': True, 'oldPoolOwnershipAbsent': True,
                 'drainOperationUuid': drain_uuid, 'executorExited': True}
        request = {'request_id': 'd' * 32,
                   'expected_control_operation_uuid': drain_uuid,
                   'expected_host_boot_id': plugin._current_boot_id(),
                   'expected_pool_generation': generation}
        evidence = {'proof': proof, 'request': request,
                    'fingerprint': 'e' * 64}
        receipt = {'schema': 1, 'requestId': None,
                   'oldActivationRequestId': request['request_id'],
                   'oldActivationFingerprint': 'e' * 64,
                   'drainControlOperationUuid': drain_uuid,
                   'bootId': plugin._current_boot_id(), 'poolGeneration': generation,
                   'reason': 'USER_CONFIRMED_UNCERTAIN_RECOVERY', 'stage': 'RETIRED',
                   'nativeObserved': 'ZERO_INACTIVE_NO_BACKING', '_http_status': 200}
        calls = []
        def service_call(action, payload):
            calls.append((action, payload))
            if action == 'lifecycle-activation-retirement':
                if post_fails:
                    raise IOError('simulated lost POST response')
                receipt['requestId'] = payload['requestId']
                return receipt
            if action == 'monitor-state':
                return {'active_operations': 0, 'pending_operations': [],
                        'lifecycle': {'paused': True, 'migrationHold': {}},
                        '_http_status': 200}
            if action == 'lifecycle-activation-retirement-state':
                return receipt
            raise AssertionError('unexpected service action %s' % action)
        plugin.service_call = service_call
        command = {'hostUuid': 'host-1', 'scope': 'Host', 'action': 'recoverUncertain',
                   'resourceUuid': 'host-1', 'desiredRevision': 24,
                   'targetSnapshotGeneration': 'policy-24',
                   'expectedInstanceGeneration': None,
                   'communication': {'requestBytes': 1048576, 'responseBytes': 16777216,
                                     'communicationSeconds': 30},
                   'operationUuid': new_uuid, 'expectedControlOperationUuid': old_uuid,
                   'policy': {},
                   'recovery': {'expectedHostBootId': plugin._current_boot_id(),
                                'expectedPoolGeneration': generation,
                                'drainControlOperationUuid': drain_uuid, 'confirmed': True}}
        return plugin, command, evidence, calls, old_path, old_bytes

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

    def test_readonly_accounting_and_operations_queries_preserve_report_and_filters(self):
        calls = []
        report = {'schema_version': 2, 'quality': 'atomic_inventory_identity_checked',
                  'vms': {}, 'inventory': {'schema_version': 2}}
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload:
                calls.append((action, payload)) or (report if action == 'accounting' else {'items': []}))
        plugin.configure({'hostUuid': 'host-1'})
        accounting = json.loads(plugin.accounting({'body': json.dumps({
            'hostUuid': 'host-1', 'vmUuid': 'vm-1',
            'communication': {'requestBytes': 1024, 'responseBytes': 4096,
                              'communicationSeconds': 30}})}))
        operations = json.loads(plugin.operations({
            'body': json.dumps({
                'hostUuid': 'host-1', 'operationId': 'op-1', 'start': 0,
                'limit': 100, 'status': 'APPLIED'})
        }))
        self.assertEqual(report, accounting['state'])
        self.assertEqual([], operations['state']['items'])
        self.assertEqual('accounting', calls[0][0])
        self.assertEqual('operations', calls[1][0])

    def test_readonly_queries_reject_identity_mismatch_without_service_call(self):
        calls = []
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: calls.append(args))
        plugin.configure({'hostUuid': 'host-1'})
        response = json.loads(plugin.accounting({'body': json.dumps({'hostUuid': 'other'})}))
        self.assertFalse(response['success'])
        self.assertEqual([], calls)

    def test_accounting_uint64_identity_is_exact_decimal_string_on_wire(self):
        large = 15704573862423239137
        report = {'inventory': {'pool_generation': large, 'sequence': 477777,
                                'owners': [{'cgroup_id': large}]},
                  'vms': {'vm-1': {'identity': {'cgroup_inode': large},
                                    'metrics': {'ram_payload_bytes': 8192}}}}
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: report)
        plugin.configure({'hostUuid': 'host-1'})
        reply = json.loads(plugin.accounting({'body': '{"hostUuid":"host-1"}'}))
        state = reply['state']
        self.assertEqual(str(large), state['inventory']['pool_generation'])
        self.assertEqual('477777', state['inventory']['sequence'])
        self.assertEqual(str(large), state['inventory']['owners'][0]['cgroup_id'])
        self.assertEqual(str(large), state['vms']['vm-1']['identity']['cgroup_inode'])
        self.assertEqual(8192, state['vms']['vm-1']['metrics']['ram_payload_bytes'])
        self.assertEqual(large, report['inventory']['pool_generation'])

    def test_accounting_rejects_already_rounded_identity(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: {
            'inventory': {'pool_generation': float(15704573862423239137)}})
        plugin.configure({'hostUuid': 'host-1'})
        reply = json.loads(plugin.accounting({'body': '{"hostUuid":"host-1"}'}))
        self.assertFalse(reply['success'])
        self.assertIn('INVALID_ACCOUNTING_IDENTITY', reply['reason'])

    def test_accounting_identity_numeric_boundary_and_canonical_format(self):
        convert = memory_optimization._accounting_wire_identity
        for invalid in (True, -1, 1 << 64, '01', '1\n', '1.0', '1e9'):
            with self.assertRaises(ValueError):
                convert({'sequence': invalid})
        self.assertEqual({'sequence': '18446744073709551615'},
                         convert({'sequence': (1 << 64) - 1}))
        self.assertEqual({'sequence': '0'}, convert({'sequence': '0'}))

    def test_readonly_service_http_failure_cannot_become_success(self):
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload: {'success': True, '_http_status': 500})
        plugin.configure({'hostUuid': 'host-1'})
        for method, body_key in ((plugin.accounting, 'hostUuid'),
                                 (plugin.operations, 'hostUuid')):
            response = json.loads(method({'body': json.dumps({body_key: 'host-1'})}))
            self.assertFalse(response['success'])
            self.assertEqual('Unknown', response['status'])

    def test_local_service_decodes_chunked_large_json_response(self):
        path = tempfile.mktemp(prefix='memory-optimization-chunked-', suffix='.sock')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(1)
        payload = json.dumps({'status': 'Succeeded', 'state': {
            'vms': {'vm-%04d' % i: {'reason': 'x' * 64} for i in range(80)}}}).encode('utf-8')

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
            first, second = payload[:len(payload) // 2], payload[len(payload) // 2:]
            header = ('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                      'Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n').encode('ascii')
            conn.sendall(header)
            for chunk in (first, second):
                conn.sendall(('%x\r\n' % len(chunk)).encode('ascii') + chunk + b'\r\n')
            conn.sendall(b'0\r\n\r\n')
            conn.close()

        thread = threading.Thread(target=serve_once)
        thread.daemon = True
        thread.start()
        try:
            plugin = MemoryOptimizationPlugin()
            plugin.configure({'socketPath': path})
            result = plugin._call_local_service('state', {})
            self.assertEqual('Succeeded', result['status'])
            self.assertEqual(80, len(result['state']['vms']))
        finally:
            thread.join(2)
            listener.close()
            if os.path.exists(path):
                os.unlink(path)

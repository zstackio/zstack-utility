"""Exercise production admission methods against real on-disk journal fixtures.

AST extraction avoids importing the daemon/OS compatibility mocks; only Host
identity and native KSM readback are boundary substitutes. No Host is contacted.
"""
import ast
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/memory_optimization.py'
METHODS = {'_valid_identifier', '_ksm_proof_policy', '_ksm_proof_matches',
           '_ksm_only_disabled_service_sections', '_first_use_terminal_ksm_record',
           '_first_use_terminal_vm_binding', '_first_use_local_history_clear',
           '_cold_ksm_vm_bindings_valid', '_first_zram_enable_requested',
           '_first_use_admission_rejected', '_first_use_admission_not_issued',
           '_reconcile_first_zram_admission', '_write_operation_record', 'reconcile'}


def subject_type():
    tree = ast.parse(SOURCE.read_text())
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MemoryOptimizationPlugin')
    original.bases = []
    original.decorator_list = []
    original.body = [n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in METHODS]
    module = ast.Module(body=[original], type_ignores=[])
    scope = {'os': os, 'json': json, 're': re, 'time': time, 'tempfile': tempfile,
             'STRING_TYPES': (str,), 'INTEGER_TYPES': (int,),
             'kvmagent': SimpleNamespace(replyerror=lambda method: method)}
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), 'exec'), scope)
    return scope['MemoryOptimizationPlugin']


class FirstZramHistoryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='first-zram-history-')
        self.addCleanup(self.directory.cleanup)
        self.plugin = subject_type()()
        self.plugin.operation_dir = self.directory.name
        self.plugin.active_control_path = str(Path(self.directory.name) / 'active-control')
        self.plugin._load_host_uuid = lambda: 'host-1'
        self.plugin._operation_hash = lambda command: 'a' * 64
        self.plugin._load_operation = lambda command: json.loads(
            (Path(self.directory.name) / (command['operationUuid'] + '.json')).read_text())
        self.plugin._request_body = lambda request: request
        self.plugin._reply = lambda value: value
        self.ack = {'run': '1', 'configRevision': '4', 'pages_to_scan': '2000',
                    'sleep_millisecs': '20', 'use_zero_pages': '1'}
        self.plugin._read_ksm_ack = lambda: dict(self.ack)
        self.command = {'operationUuid': '1' * 32}
        self.put({'operationUuid': '1' * 32, 'stage': 'PREPARING', 'requestHash': 'a' * 64})
        self.active = self.ksm_record('2' * 32, 4)
        self.put(self.active)
        Path(self.plugin.active_control_path).write_text('2' * 32)

    def ksm_record(self, op, revision):
        proof = dict(self.ack, configRevision=str(revision))
        return {'operationUuid': op, 'hostUuid': 'host-1', 'scope': 'Host', 'stage': 'APPLIED',
                'action': 'apply', 'desiredRevision': revision, 'requestHash': 'b' * 64,
                'policy': {'schemaVersion': 1, 'ksm': {'enabled': True}},
                'readback': {'success': True, 'status': 'Succeeded', 'appliedRevision': revision,
                             'state': {'ksmOnly': True}, 'ksmReadback': proof}}

    def binding(self):
        return {'operationUuid': '3' * 32, 'hostUuid': 'host-1', 'scope': 'vm', 'stage': 'APPLIED',
                'action': 'bind', 'resourceUuid': '4' * 32, 'requestHash': 'c' * 64,
                'expectedInstanceGeneration': 'd' * 64, 'participation': 'inherit',
                'readback': {'success': True, 'status': 'Succeeded', 'operationUuid': '3' * 32,
                             'request_id': '3' * 32, 'revision': 2}}

    def put(self, record, filename=None):
        (Path(self.directory.name) / ((filename or record['operationUuid']) + '.json')).write_text(json.dumps(record))

    def clear(self):
        return self.plugin._first_use_local_history_clear(self.command)

    def test_completed_ksm_only_baseline(self):
        self.assertTrue(self.clear())

    def test_completed_vm_bind_does_not_fence_host_first_use(self):
        self.put(self.binding())
        self.assertTrue(self.clear())

    def test_completed_vm_binding_readonly_reconcile_proof(self):
        record = self.binding()
        record['readback'] = {'success': True, 'status': 'Succeeded',
                              'operationUuid': record['operationUuid'],
                              'state': {'phase': 'VM_READBACK', 'complete': True,
                                        'service': {'revision': 2, 'mode': 'auto',
                                                    'instance_generation': 'd' * 64}}}
        self.put(record)
        self.assertTrue(self.clear())
        for field, value in [('mode', 'deny'), ('instance_generation', 'old'),
                             ('revision', True)]:
            changed = copy.deepcopy(record)
            changed['readback']['state']['service'][field] = value
            self.put(changed)
            self.assertFalse(self.clear(), field)

    def test_all_supported_vm_participations_are_terminal_vm_only(self):
        for mode in ('inherit', 'allow', 'deny', 'auto'):
            record = self.binding()
            record['participation'] = mode
            self.put(record)
            self.assertTrue(self.clear(), mode)

    def test_completed_empty_ksm_noop_is_accepted_only_as_nonactive_history(self):
        old = self.ksm_record('5' * 32, 2)
        old['policy']['ksm'] = {}
        self.put(old)
        self.assertTrue(self.clear())
        Path(self.plugin.active_control_path).write_text('5' * 32)
        self.assertFalse(self.clear())

    def test_vm_binding_and_empty_ksm_noop_history_together(self):
        self.put(self.binding())
        old = self.ksm_record('5' * 32, 2)
        old['policy']['ksm'] = {}
        self.put(old)
        self.assertTrue(self.clear())

    def test_unfinished_and_unknown_bindings_remain_fenced(self):
        for stage in ['PREPARING', 'UNKNOWN', 'ACTIVATING', 'REJECTED']:
            record = self.binding()
            record['stage'] = stage
            self.put(record)
            self.assertFalse(self.clear(), stage)

    def test_binding_readback_must_match_operation(self):
        for key, value in [('success', False), ('status', 'Unknown'), ('operationUuid', '6' * 32),
                           ('request_id', '6' * 32), ('revision', True), ('revision', -1)]:
            record = self.binding()
            record['readback'][key] = value
            self.put(record)
            self.assertFalse(self.clear(), key)

    def test_vm_record_cannot_smuggle_host_writer(self):
        for field, value in [('action', 'apply'), ('scope', 'Host'), ('hostUuid', 'another-host'),
                             ('policy', {'ksm': {'enabled': True}}), ('participation', 'unknown'),
                             ('requestHash', 'bad'), ('resourceUuid', '../escape'),
                             ('expectedInstanceGeneration', ''), ('firstZramUse', {}),
                             ('activationIntent', {}), ('maintenanceProof', {}),
                             ('expectedControlOperationUuid', '2' * 32)]:
            record = self.binding()
            record[field] = value
            self.put(record)
            self.assertFalse(self.clear(), field)

    def test_binding_cannot_be_host_active_control(self):
        self.put(self.binding())
        Path(self.plugin.active_control_path).write_text('3' * 32)
        self.assertFalse(self.clear())

    def test_filename_identity_is_bound(self):
        self.put(self.ksm_record('5' * 32, 2), filename='6' * 32)
        self.assertFalse(self.clear())

    def test_empty_ksm_without_native_proof_still_fenced(self):
        old = self.ksm_record('5' * 32, 2)
        old['policy']['ksm'] = {}
        del old['readback']['ksmReadback']
        self.put(old)
        self.assertFalse(self.clear())

    def test_actual_active_ksm_readback_required(self):
        self.ack['run'] = '0'
        self.assertFalse(self.clear())

    def test_applied_host_pause_and_zram_policy_remain_fenced(self):
        for change in [{'action': 'pause'}, {'policy': {'ksm': {}, 'zram': {'enabled': True}}}]:
            old = self.ksm_record('5' * 32, 2)
            old.update(change)
            self.put(old)
            self.assertFalse(self.clear())

    def rejection_fixture(self):
        config_dir = tempfile.TemporaryDirectory(prefix='first-zram-admission-config-')
        self.addCleanup(config_dir.cleanup)
        self.plugin.zram_config_path = str(Path(config_dir.name) / 'config.json')
        self.plugin.zram_config_template_path = str(Path(config_dir.name) / 'vendor.json')
        config = json.dumps({'managed': True, 'mode': 'observe', 'resource_authorized': False,
                             'initial_efficiency_enabled': False})
        Path(self.plugin.zram_config_path).write_text(config)
        Path(self.plugin.zram_config_template_path).write_text(config)
        self.command['hostUuid'] = 'host-1'
        record = {'operationUuid': self.command['operationUuid'], 'hostUuid': 'host-1',
                  'bootId': 'boot-1', 'scope': 'Host', 'action': 'apply', 'desiredRevision': 5,
                  'stage': 'UNKNOWN', 'requestHash': 'a' * 64,
                  'policy': {'ksm': {'enabled': False}, 'zram': {'enabled': True}},
                  'applyEvidence': {'reason': 'FIRST_ZRAM_LOCAL_CONTROL_FENCED'},
                  'readback': {'reason': 'FIRST_ZRAM_LOCAL_CONTROL_FENCED'}}
        self.put(record)
        self.plugin._current_boot_id = lambda: 'boot-1'
        self.plugin._acquire_host_control_lock = Mock(return_value=object())
        self.plugin._release_operation = Mock()
        self.plugin._first_use_runtime_identity = Mock(return_value={'verified': True})
        self.plugin._first_use_state_safe = Mock(return_value=True)
        self.plugin._service_request = Mock(side_effect=lambda action, payload: {
            'state': {'pending_operations': None},
            'host-cpu-state': {'efficiency_enabled': False}}[action])
        return record

    def reconcile_rejection(self, prior):
        return self.plugin._reconcile_first_zram_admission(self.command, prior)

    def test_readonly_reconcile_retires_only_pre_authorization_rejection(self):
        prior = self.rejection_fixture()
        self.put(self.binding())
        config_before = Path(self.plugin.zram_config_path).read_bytes()
        active_before = Path(self.plugin.active_control_path).read_bytes()
        result = self.reconcile_rejection(prior)
        self.assertEqual('Failed', result['status'])
        self.assertEqual('FIRST_ZRAM_ADMISSION_NOT_ISSUED', result['reasonCode'])
        actual = self.plugin._load_operation(self.command)
        self.assertEqual('NOT_ISSUED', actual['stage'])
        for key in ('requestHash', 'applyEvidence', 'policy', 'desiredRevision', 'bootId'):
            self.assertEqual(prior[key], actual[key], key)
        self.assertEqual(config_before, Path(self.plugin.zram_config_path).read_bytes())
        self.assertEqual(active_before, Path(self.plugin.active_control_path).read_bytes())
        self.assertEqual(['state', 'host-cpu-state'], [c.args[0] for c in self.plugin._service_request.call_args_list])
        self.assertTrue(self.plugin._first_use_admission_not_issued(actual))
        self.assertEqual(result, self.reconcile_rejection(actual))
        self.assertEqual(2, self.plugin._service_request.call_count)
        new_command = {'operationUuid': '7' * 32, 'hostUuid': 'host-1'}
        self.put({'operationUuid': '7' * 32, 'stage': 'PREPARING', 'requestHash': 'a' * 64})
        self.assertTrue(self.plugin._first_use_local_history_clear(new_command))

    def test_existing_reconcile_endpoint_routes_rejection_and_terminal_poll(self):
        self.rejection_fixture()
        result = self.plugin.reconcile(self.command)
        self.assertEqual('FIRST_ZRAM_ADMISSION_NOT_ISSUED', result['reasonCode'])
        self.assertEqual(result, self.plugin.reconcile(self.command))
        self.assertEqual(2, self.plugin._service_request.call_count)

    def assert_unknown_unchanged(self, prior):
        original = (Path(self.directory.name) / (prior['operationUuid'] + '.json')).read_bytes()
        result = self.reconcile_rejection(prior)
        self.assertEqual('Unknown', result['status'])
        self.assertEqual(original, (Path(self.directory.name) / (prior['operationUuid'] + '.json')).read_bytes())
        return result

    def test_reconcile_rejects_different_boot_or_host(self):
        prior = self.rejection_fixture()
        self.plugin._current_boot_id = lambda: 'new-boot'
        self.assert_unknown_unchanged(prior)
        self.plugin._current_boot_id = lambda: 'boot-1'
        self.command['hostUuid'] = 'different-host'
        self.assert_unknown_unchanged(prior)
        self.plugin._service_request.assert_not_called()

    def test_reconcile_does_not_retire_policy_or_authorization_intent(self):
        for change in ({'firstZramUse': {'policySubmissionStarted': False}},
                       {'firstZramUse': {'policySubmissionStarted': True}},
                       {'activationIntent': {}}, {'maintenanceProof': {}},
                       {'applyEvidence': {'reason': 'SERVICE_TIMEOUT'}},
                       {'applyEvidence': {'reason': 'FIRST_ZRAM_LOCAL_CONTROL_FENCED', 'receipt': {}}},
                       {'bootId': None}, {'policy': {'zram': []}}):
            prior = self.rejection_fixture()
            prior.update(change)
            self.put(prior)
            self.assert_unknown_unchanged(prior)
            self.plugin._service_request.assert_not_called()

    def test_reconcile_requires_unchanged_snapshot_under_lock(self):
        prior = self.rejection_fixture()
        changed = dict(prior, stage='APPLIED')
        self.put(changed)
        self.assert_unknown_unchanged(prior)
        self.plugin._service_request.assert_not_called()

    def test_reconcile_lock_contention_never_mutates_record(self):
        prior = self.rejection_fixture()
        self.plugin._acquire_host_control_lock.side_effect = OSError('busy')
        self.assert_unknown_unchanged(prior)
        self.plugin._service_request.assert_not_called()

    def test_reconcile_native_or_factory_drift_keeps_unknown(self):
        prior = self.rejection_fixture()
        self.plugin._first_use_state_safe.return_value = False
        self.assert_unknown_unchanged(prior)
        self.plugin._first_use_state_safe.return_value = True
        Path(self.plugin.zram_config_path).write_text('{}')
        self.assert_unknown_unchanged(prior)

    def test_reconcile_another_unknown_is_not_ignored(self):
        prior = self.rejection_fixture()
        other = self.binding()
        other['stage'] = 'UNKNOWN'
        self.put(other)
        self.assert_unknown_unchanged(prior)

    def test_reconcile_failed_persistence_keeps_unknown(self):
        prior = self.rejection_fixture()
        self.plugin._write_operation_record = Mock(return_value=False)
        result = self.assert_unknown_unchanged(prior)
        self.assertEqual('FIRST_ZRAM_RECONCILE_JOURNAL_UNAVAILABLE', result['reasonCode'])

    def test_retired_admission_requires_bound_receipt(self):
        prior = self.rejection_fixture()
        self.reconcile_rejection(prior)
        retired = self.plugin._load_operation(self.command)
        retired['readback']['state']['requestHash'] = 'b' * 64
        self.assertFalse(self.plugin._first_use_admission_not_issued(retired))


if __name__ == '__main__':
    unittest.main(verbosity=2)

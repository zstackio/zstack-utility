# -*- coding: utf-8 -*-
"""First finite-capacity+enabled apply over the real Go Unix HTTP ABI."""
import json
import os
import shutil
import tempfile
import unittest
import uuid

from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin


SOCKET = os.environ.get('MEMORY_OPTIMIZATION_SOCKET')
@unittest.skipUnless(SOCKET and os.path.exists(SOCKET) and
                     os.environ.get('MEMORY_OPTIMIZATION_CAPACITY_REVISION_FIXTURE') == '1',
                     'requires isolated Go capacity/revision Unix fixture')
class TestCapacityCPURevisionUnix(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='memory-capacity-cpu-unix-')
        self.addCleanup(shutil.rmtree, self.root)
        self.host = 'fixture-host-' + uuid.uuid4().hex
        self.plugin = MemoryOptimizationPlugin()
        self.plugin.configure({'socketPath': SOCKET, 'hostUuid': self.host,
                               'operationDir': self.root,
                               'vmBindingDir': os.path.join(self.root, 'vms')})
        self.assertEqual(self.plugin.service_call.__func__,
                         self.plugin._call_local_service.__func__)

    def _write_evidence(self, case_name, case):
        path = os.environ.get('MEMORY_OPTIMIZATION_CAPACITY_REVISION_EVIDENCE')
        if not path:
            return
        evidence = {'schemaVersion': 1, 'cases': {}}
        if os.path.exists(path):
            with open(path) as stream:
                evidence = json.load(stream)
        evidence.setdefault('cases', {})[case_name] = case
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, 'w') as stream:
            json.dump(evidence, stream, sort_keys=True, indent=2)

    def test_first_finite_capacity_and_enable_reconciles_blocked_across_cpu_revision(self):
        """A 202 capacity response remains provably blocked after this op's CPU PUT.

        The Go fixture uses the production Runtime.Handler and persistent Host
        PolicyStore. It has no initialized pool; only Unix HTTP policy APIs are
        active, so this cannot touch a native ZRAM device or swap.
        """
        operation = 'e' * 32
        command = {'action': 'apply', 'scope': 'Host', 'hostUuid': self.host,
                   'operationUuid': operation, 'desiredRevision': 29,
                   'policy': {'zram': {'enabled': True,
                                       'logicalCapacityBytes': 1 << 30,
                                       'ramLimitBytes': 1 << 29,
                                       'cpuThresholdPercent': 50,
                                       'cpuHoldSeconds': 60},
                              'writeback': {'enabled': False}}}
        before_capacity = self.plugin.service_call('capacity-state', {})
        before_cpu = self.plugin.service_call('host-cpu-state', {})
        calls = []
        service_call = self.plugin.service_call
        def recorded_call(action, payload):
            response = service_call(action, payload)
            calls.append({'action': action, 'request': payload, 'response': response})
            return response
        self.plugin.service_call = recorded_call
        apply = self.plugin._apply_service_policy_fail_closed(command)
        self.assertEqual('Draining', apply.get('status'), apply)
        self.assertEqual(['capacity'], apply.get('asyncSections'), apply)
        sections = apply['state']['sections']
        capacity = sections['capacity']
        self.assertEqual(202, capacity.get('_http_status'), capacity)
        capacity_put_index = next(index for index, row in enumerate(calls)
                                  if row['action'] == 'capacity')
        capacity_put = calls[capacity_put_index]
        prewrite_capacity_reads = [row for row in calls[:capacity_put_index]
                                   if row['action'] == 'capacity-state']
        self.assertTrue(prewrite_capacity_reads)
        self.assertEqual(operation + '-capacity', capacity_put['request'].get('request_id'))
        self.assertEqual(prewrite_capacity_reads[-1]['response']['revision'],
                         capacity_put['request']['expected_revision'])
        capacity_before_cpu = sections['capacityReadback']
        cpu_receipt = sections['cpu']
        cpu_readback = sections['cpuReadback']
        self.assertEqual(capacity['revision'], capacity_before_cpu['revision'])
        self.assertEqual('BLOCKED', capacity_before_cpu.get('apply_state'))
        self.assertEqual('NATIVE_POOL_UNQUALIFIED', capacity_before_cpu.get('reason'))
        self.assertEqual(operation + '-cpu', cpu_receipt.get('request_id'))
        cpu_put = next(row for row in calls if row['action'] == 'host-cpu' and
                       row['request'].get('request_id') == operation + '-cpu')
        self.assertEqual(capacity['revision'], cpu_put['request']['expected_revision'])
        self.assertTrue(cpu_receipt.get('efficiency_enabled'))
        self.assertEqual(cpu_receipt['revision'], cpu_readback['revision'])
        self.assertNotEqual(capacity['revision'], cpu_receipt['revision'])

        normalized_apply = self.plugin._normalize_response(apply, 'apply', command)
        self.assertTrue(self.plugin._record_operation(command, 'UNKNOWN', normalized_apply))
        reconcile = json.loads(self.plugin.reconcile({'body': json.dumps(
            {'hostUuid': self.host, 'operationUuid': operation})}))
        self.assertEqual('Blocked', reconcile.get('status'), reconcile)
        # Local provenance is asserted after the behavioral result so the
        # same test demonstrates the pre-fix red as Unknown, not a fixture
        # mismatch caused by fields introduced by this patch.
        apply_evidence = self.plugin._load_operation(command)['applyEvidence']
        bound_sections = apply_evidence['state']['sections']
        self.assertEqual(operation + '-capacity', bound_sections['capacity']['agent_request_id'])
        self.assertEqual(operation + '-tuning', bound_sections['tuning']['agent_request_id'])
        self.assertEqual(capacity['revision'], bound_sections['cpu']['agent_expected_revision'])
        self.assertEqual('NATIVE_POOL_UNQUALIFIED', reconcile['blockers'][0]['code'])
        final_sections = reconcile['state']['sections']
        self.assertEqual(cpu_receipt['revision'], final_sections['capacity']['revision'])
        self.assertEqual(cpu_receipt['revision'], final_sections['cpu']['revision'])
        self.assertEqual('BLOCKED', final_sections['capacity']['apply_state'])
        self.assertEqual('NATIVE_POOL_UNQUALIFIED', final_sections['capacity']['reason'])
        self.assertEqual(1 << 30, final_sections['capacity']['desired']['configured'][
            'logical_capacity']['bytes'])
        self.assertEqual(1 << 29, final_sections['capacity']['desired']['configured'][
            'physical_memory_limit']['bytes'])
        record = self.plugin._load_operation(command)
        self.assertEqual('BLOCKED', record.get('stage'))
        evidence = record['applyEvidence']['state']['sections']
        self.assertEqual(capacity['revision'], evidence['capacity']['revision'])
        self.assertEqual(cpu_receipt['revision'], evidence['cpu']['revision'])
        self._write_evidence(
            'first_finite_capacity_and_enable_reconciles_blocked_across_cpu_revision', {
                'passed': True,
                'capacityHttpStatus': capacity.get('_http_status'),
                'capacityApplyStateBeforeCpu': capacity_before_cpu.get('apply_state'),
                'capacityReasonBeforeCpu': capacity_before_cpu.get('reason'),
                'capacityReceiptRevision': capacity.get('revision'),
                'capacityExpectedRevision': capacity_put['request'].get('expected_revision'),
                'capacityPreCpuReadbackRevision': capacity_before_cpu.get('revision'),
                'cpuPutExpectedRevision': cpu_put['request'].get('expected_revision'),
                'cpuReceiptRevision': cpu_receipt.get('revision'),
                'cpuReadbackRevision': cpu_readback.get('revision'),
                'finalCapacityRevision': final_sections['capacity'].get('revision'),
                'reconcileStatus': reconcile.get('status'),
                'sectionCompleteCpu': apply['state'].get('sectionComplete', {}).get('cpu'),
                'cpuEnabledRequested': True,
                'cpuThresholdRequested': 50,
                'cpuHoldRequested': 60,
                'cpuEnabledReadback': final_sections['cpu'].get('efficiency_enabled'),
                'cpuThresholdReadback': final_sections['cpu'].get(
                    'idle_cpu_threshold_percent'),
                'cpuHoldReadback': final_sections['cpu'].get('idle_duration_seconds'),
                'httpTrace': calls,
            })
        print('CAPACITY_CPU_REVISION_UNIX_EVIDENCE=' + json.dumps({
            'beforeCapacityRevision': before_capacity['revision'],
            'beforeCpuRevision': before_cpu['revision'],
            'capacity202Revision': capacity['revision'],
            'capacityRequestId': capacity['agent_request_id'],
            'capacityExpectedRevision': capacity['agent_expected_revision'],
            'capacityReadbackBeforeCpuRevision': capacity_before_cpu['revision'],
            'finalCpuRequestId': cpu_receipt['request_id'],
            'finalCpuExpectedRevision': cpu_receipt['agent_expected_revision'],
            'finalCpuReceiptRevision': cpu_receipt['revision'],
            'currentCapacityRevision': final_sections['capacity']['revision'],
            'reconcileStatus': reconcile['status'],
            'reason': final_sections['capacity']['reason'],
            'httpTrace': [{'action': row['action'],
                           'requestId': row['request'].get('request_id'),
                           'expectedRevision': row['request'].get('expected_revision'),
                           'httpStatus': row['response'].get('_http_status'),
                           'revision': row['response'].get('revision'),
                           'applyState': row['response'].get('apply_state')}
                          for row in calls if row['action'] in (
                              'capacity', 'capacity-state', 'host-cpu', 'host-cpu-state')],
        }, sort_keys=True))

    def test_intervening_external_cpu_write_keeps_capacity_result_unknown(self):
        operation = 'f' * 32
        command = {'action': 'apply', 'scope': 'Host', 'hostUuid': self.host,
                   'operationUuid': operation, 'desiredRevision': 30,
                   'policy': {'zram': {'enabled': True,
                                       'logicalCapacityBytes': 2 << 30,
                                       'ramLimitBytes': 1 << 30,
                                       'cpuThresholdPercent': 50,
                                       'cpuHoldSeconds': 60},
                              'writeback': {'enabled': False}}}
        service_call = self.plugin.service_call
        calls = []
        capacity_written = [False]
        injected = [False]

        def interleaving_call(action, payload):
            response = service_call(action, payload)
            calls.append({'action': action, 'request': payload, 'response': response})
            if action == 'capacity':
                capacity_written[0] = response.get('_http_status') == 202
            elif action == 'host-cpu-state' and capacity_written[0] and not injected[0]:
                # Simulate a distinct writer after the Agent observed the
                # pre-CPU state but before its final CPU PUT. Preserve enabled
                # state and change only the native CPU threshold.
                injected[0] = True
                external = {'request_id': 'external-cpu-writer',
                            'expected_revision': response['revision'],
                            'efficiency_enabled': response['efficiency_enabled'],
                            'idle_cpu_threshold_percent': 49,
                            'idle_duration_seconds': response['idle_duration_seconds']}
                external_response = service_call('host-cpu', external)
                calls.append({'action': 'external-host-cpu', 'request': external,
                              'response': external_response})
            return response

        self.plugin.service_call = interleaving_call
        result = self.plugin._apply_service_policy_fail_closed(command)
        self.assertTrue(injected[0], calls)
        self.assertEqual('Unknown', result.get('status'), result)
        normalized_result = self.plugin._normalize_response(result, 'apply', command)
        self.assertTrue(self.plugin._record_operation(command, 'UNKNOWN', normalized_result))
        reconciled = json.loads(self.plugin.reconcile({'body': json.dumps(
            {'hostUuid': self.host, 'operationUuid': operation})}))
        self.assertEqual('Unknown', reconciled.get('status'), reconciled)
        self.assertNotIn('knownBlocked', reconciled.get('state', {}))
        record = self.plugin._load_operation(command)
        self.assertEqual('UNKNOWN', record.get('stage'))
        self.assertTrue(any(row['action'] == 'external-host-cpu' and
                            row['response'].get('_http_status') == 200 for row in calls), calls)
        self.assertFalse(any(row['action'] == 'host-cpu' and
                             row['request'].get('request_id') == operation + '-cpu' and
                             row['response'].get('_http_status') == 200
                             for row in calls), calls)
        external_row = next(row for row in calls if row['action'] == 'external-host-cpu')
        agent_cpu_attempt = next(row for row in calls if row['action'] == 'host-cpu' and
                                 row['request'].get('request_id') == operation + '-cpu')
        self._write_evidence(
            'intervening_external_cpu_write_keeps_capacity_result_unknown', {
                'passed': True,
                'externalCpuWriteHttpStatus': external_row['response'].get('_http_status'),
                'externalCpuThreshold': external_row['response'].get(
                    'idle_cpu_threshold_percent'),
                'cpuPutAttempted': True,
                'cpuPutAccepted': agent_cpu_attempt['response'].get('_http_status') == 200,
                'cpuPutHttpStatus': agent_cpu_attempt['response'].get('_http_status'),
                'agentApplyStatus': result.get('status'),
                'reconcileStatus': reconciled.get('status'),
                'reasonCode': result.get('reasonCode'),
                'httpTrace': calls,
            })
        print('CAPACITY_CPU_EXTERNAL_WRITER_UNIX_EVIDENCE=' + json.dumps({
            'capacity202Revision': record['applyEvidence']['state']['sections'][
                'capacity']['revision'],
            'externalCpuExpectedRevision': next(
                row['request']['expected_revision'] for row in calls
                if row['action'] == 'external-host-cpu'),
            'externalCpuReceiptRevision': next(
                row['response']['revision'] for row in calls
                if row['action'] == 'external-host-cpu'),
            'agentApplyStatus': result['status'],
            'reconcileStatus': reconciled['status'],
            'reasonCode': result.get('reasonCode')}, sort_keys=True))


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""Cross-process Agent -> Go maintenance activation over the real Unix ABI."""
import os
import json
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin

import pytest

pytestmark = pytest.mark.integration


SOCKET = os.environ.get('MEMORY_OPTIMIZATION_SOCKET')
HOST = 'fixture-host'
DRAIN = 'c' * 32
OLD_GENERATION = 'a' * 64


@unittest.skipUnless(SOCKET and os.path.exists(SOCKET) and
                     os.environ.get('MEMORY_OPTIMIZATION_MAINTENANCE_FIXTURE') == '1',
                     'requires isolated Go maintenance Unix fixture')
class TestMaintenanceActivationUnix(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='memory-maintenance-unix-')
        self.addCleanup(shutil.rmtree, self.root)
        self.plugin = MemoryOptimizationPlugin()
        self.plugin.configure({'socketPath': SOCKET, 'hostUuid': HOST,
                               'operationDir': self.root,
                               'vmBindingDir': os.path.join(self.root, 'vms')})
        self.assertEqual(self.plugin.service_call.__func__,
                         self.plugin._call_local_service.__func__)

    def test_apply_activates_real_runtime_and_advances_fence_only_after_ready(self):
        drain = {'hostUuid': HOST, 'operationUuid': DRAIN, 'scope': 'Host',
                 'action': 'drain', 'desiredRevision': 1}
        self.assertTrue(self.plugin._record_operation(
            drain, 'APPLIED', {'success': True, 'status': 'Succeeded'}))
        self.plugin._set_active_control(DRAIN)
        operation = 'd' * 32
        proof = {'schemaVersion': 1, 'maintenanceReady': True,
                 'maintenanceArchived': True, 'activeOperations': 0,
                 'drainOperationUuid': DRAIN,
                 'oldPoolGeneration': OLD_GENERATION,
                 'readyForInitialization': True,
                 'originalDeviceInactive': True,
                 'oldPoolOwnershipAbsent': True}
        command = {'action': 'apply', 'scope': 'Host', 'hostUuid': HOST,
                   'operationUuid': operation, 'desiredRevision': 2,
                   'expectedControlOperationUuid': DRAIN,
                   'maintenanceProof': proof,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-fixture',
                                     'validForSeconds': 60,
                                     'expiresAt': int(time.time() * 1000) + 65000},
                   'policy': {'zram': {'enabled': True,
                                       'logicalCapacityBytes': 1 << 30,
                                       'ramLimitBytes': 1 << 29,
                                       'cpuThresholdPercent': 80,
                                       'cpuHoldSeconds': 60},
                              'writeback': {'enabled': False}}}
        calls = []
        service_call = self.plugin.service_call
        def recorded_call(action, payload):
            calls.append((action, payload))
            response = service_call(action, payload)
            if (os.environ.get('MEMORY_OPTIMIZATION_ACTIVATION_LOST_RESPONSE') == '1' and
                    action == 'lifecycle-activate-maintenance'):
                raise IOError('fixture discarded real service POST response')
            return response

        self.plugin.service_call = recorded_call
        with patch.object(self.plugin, 'discover_capabilities', return_value={
                'supported': True, 'ksm': True, 'zram': True,
                'writeback': True, 'ksmZeroPages': True}), \
                patch.object(self.plugin, '_requires_new_optimization', return_value=True), \
                patch.object(self.plugin, '_validate_requested_capabilities'), \
                patch.object(self.plugin, '_fill_resolved_capacity_defaults'), \
                patch.object(self.plugin, '_validate_policy'), \
                patch.object(self.plugin, '_validate_backend_resource'), \
                patch.object(self.plugin, '_maintenance_recovery_proof', return_value=True), \
                patch.object(self.plugin, '_apply_ksm_policy', return_value={}):
            result = self.plugin.apply(command)
        if os.environ.get('MEMORY_OPTIMIZATION_ACTIVATION_REJECTION') == '1':
            if os.environ.get('MEMORY_OPTIMIZATION_ACTIVATION_LOST_RESPONSE') == '1':
                self.assertEqual('Unknown', result.get('status'), result)
                result = json.loads(self.plugin.reconcile({'body': json.dumps(
                    {'hostUuid': HOST, 'operationUuid': operation})}))
            self.assertEqual('Failed', result.get('status'), result)
            self.assertEqual('MAINTENANCE_ACTIVATION_NATIVE_RESET_NOT_CONFIRMED', result.get('reasonCode'))
            self.assertEqual(DRAIN, self.plugin._get_active_control())
            self.assertEqual(1, len([entry for entry in calls if entry[0] == 'lifecycle-activate-maintenance']))
            record = self.plugin._load_operation({'operationUuid': operation})
            self.assertEqual('REJECTED', record['stage'])
            activation = self.plugin._service_request('lifecycle-activation-state', {
                'requestId': record['activationIntent']['request']['request_id']})
            self.assertEqual('REJECTED', activation['receipt']['stage'])
            self.assertTrue(activation['lifecycle']['paused'])
            self.assertFalse(activation['unpaused_observed'])
            return
        self.assertEqual('Succeeded', result.get('status'),
                         {'result': result, 'calls': calls,
                          'operation': self.plugin._load_operation({'operationUuid': operation})})
        self.assertEqual(operation, self.plugin._get_active_control())
        self.assertEqual(1, len([entry for entry in calls
                                 if entry[0] == 'lifecycle-activate-maintenance']))
        self.assertGreaterEqual(len([entry for entry in calls
                                     if entry[0] == 'lifecycle-activation-state']), 1)
        status = service_call('state', {})
        self.assertFalse(status['lifecycle']['paused'], status)
        self.assertNotEqual(OLD_GENERATION,
                            status['host_zram']['pool_generation'], status)
        self.assertEqual('native_host_device', status['host_zram']['quality'], status)
        record = self.plugin._load_operation({'operationUuid': operation})
        self.assertEqual('APPLIED', record['stage'])
        activation = self.plugin._service_request(
            'lifecycle-activation-state',
            {'requestId': record['activationIntent']['request']['request_id']})
        self.assertEqual('UNPAUSED', activation['receipt']['stage'], activation)

if __name__ == '__main__':
    unittest.main()

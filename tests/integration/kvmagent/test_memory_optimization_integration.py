# -*- coding: utf-8 -*-
"""Cross-process Agent -> zram-memory Unix HTTP integration checks.

The test is intentionally opt-in.  U4's isolated Runtime.Handler fixture
exports ``MEMORY_OPTIMIZATION_SOCKET`` (and optionally
``MEMORY_OPTIMIZATION_HOST_UUID``/``MEMORY_OPTIMIZATION_VM_UUID``).  Without
that fixture this file is skipped; ordinary Agent UT must never contact a
host service or mutate host memory.
"""
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin

import pytest

pytestmark = pytest.mark.integration


SOCKET = os.environ.get('MEMORY_OPTIMIZATION_SOCKET')


@unittest.skipUnless(SOCKET and os.path.exists(SOCKET),
                     'requires U4 Runtime.Handler Unix fixture')
class TestMemoryOptimizationAgentUnixIntegration(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='memory-optimization-integration-')
        self.host = os.environ.get('MEMORY_OPTIMIZATION_HOST_UUID', 'fixture-host')
        self.vm = os.environ.get('MEMORY_OPTIMIZATION_VM_UUID', 'fixture-vm')
        self.plugin = MemoryOptimizationPlugin()
        self.plugin.configure({'socketPath': SOCKET, 'hostUuid': self.host,
                               'operationDir': self.root,
                               'vmBindingDir': os.path.join(self.root, 'vms')})
        # This suite must exercise the production Unix transport.  Individual
        # policy tests may patch capability discovery, but never service_call.
        self.assertIs(self.plugin.service_call.__self__, self.plugin)
        self.assertEqual(self.plugin.service_call.__func__,
                         self.plugin._call_local_service.__func__)

    def _command(self, operation, policy, **extra):
        command = {'action': 'apply', 'scope': 'host', 'hostUuid': self.host,
                   'operationUuid': operation, 'desiredRevision': 1,
                   'licensePermit': self._permit(),
                   'policy': policy}
        command.update(extra)
        return command

    def _permit(self):
        return {'managed': True,
                'operationUuid': 'managed-' + self.host,
                'validForSeconds': 60,
                'expiresAt': int(time.time() * 1000) + 65000}

    def test_real_service_kernel_capability_read_has_no_policy_side_effect(self):
        before = self.plugin.service_call('host-cpu-state', {})
        caps = self.plugin.service_call('capabilities', {})
        self.assertEqual('zram-service-v1', caps['abiProfile'])
        self.assertIsInstance(caps['reclaim_qualification']['supported'], bool)
        self.assertTrue(caps['reclaim_qualification']['reason_code'])
        self.assertEqual(before, self.plugin.service_call('host-cpu-state', {}))

    def test_host_apply_reads_revision_then_updates_each_native_section(self):
        """Exercise real Unix HTTP, section GET/CAS and readback."""
        policy = json.loads(os.environ.get(
            'MEMORY_OPTIMIZATION_POLICY',
            '{"zram":{"enabled":true},'
            '"writeback":{"enabled":false}}'))
        # The real Agent contract requires explicit capacity when enabling
        # ZRAM; using fixture-sized values keeps this test independent of a
        # host's physical-memory formula.
        policy.setdefault('zram', {}).setdefault('logicalCapacityBytes', 64 * 1024 ** 3)
        policy.setdefault('zram', {}).setdefault('ramLimitBytes', 32 * 1024 ** 3)
        calls = []
        real_service_call = self.plugin.service_call
        self.plugin.service_call = lambda action, payload: (
            calls.append(action), real_service_call(action, payload))[1]
        with patch.object(self.plugin, '_load_host_uuid', return_value=self.host), \
                patch.object(self.plugin, 'discover_capabilities', return_value={
                    'supported': True, 'ksm': True, 'zram': True,
                    'writeback': True, 'ksmZeroPages': True}), \
                patch.object(self.plugin, '_apply_ksm_policy', return_value={}):
            result = self.plugin.apply(self._command('integration-host-apply', policy))
        self.assertIn(result.get('status'), ('Succeeded', 'Draining'))
        self.assertNotEqual('Unknown', result.get('status'))
        self.assertNotIn('lease', calls)
        self.assertLess(calls.index('capacity-state'), calls.index('capacity'))
        self.assertLess(calls.index('host-cpu-state'), calls.index('host-cpu'))
        self.assertLess(calls.index('tuning-state'), calls.index('apply'))
        if result.get('status') == 'Succeeded':
            self.assertEqual(1, result.get('appliedRevision'))

    def test_vm_deny_and_allow_use_real_vm_revision_endpoint(self):
        with patch.object(self.plugin, '_load_host_uuid', return_value=self.host), \
                patch.object(self.plugin, 'discover_capabilities', return_value={
                    'supported': True, 'ksm': True, 'zram': True,
                    'writeback': True, 'ksmZeroPages': True}):
            for operation, participation in (('integration-vm-deny', 'deny'),
                                              ('integration-vm-allow', 'allow')):
                result = self.plugin.apply({
                    'action': 'apply', 'scope': 'vm', 'hostUuid': self.host,
                    'operationUuid': operation, 'desiredRevision': 1,
                    'resourceUuid': self.vm,
                    'expectedInstanceGeneration': os.environ.get(
                        'MEMORY_OPTIMIZATION_VM_GENERATION', 'fixture-generation'),
                    'participation': participation,
                    'licensePermit': self._permit(),
                    'policy': {'participation': participation}})
                self.assertTrue(result.get('success'), result)
                self.assertEqual('Succeeded', result.get('status'), result)
                state = self.plugin.service_call(
                    'vm-policy-state', {'_resource_uuid': self.vm})
                self.assertEqual(participation if participation == 'deny' else 'auto',
                                 state.get('mode'), state)
                self.assertEqual(os.environ['MEMORY_OPTIMIZATION_VM_GENERATION'],
                                 state.get('instance_generation'), state)

    def test_vm_rejects_wrong_generation_but_ignores_expired_permit(self):
        base = {
            'action': 'apply', 'scope': 'vm', 'hostUuid': self.host,
            'desiredRevision': 1, 'resourceUuid': self.vm,
            'expectedInstanceGeneration': 'stale-generation',
            'participation': 'deny', 'policy': {'participation': 'deny'},
            'operationUuid': 'integration-vm-stale', 'licensePermit': self._permit(),
        }
        with patch.object(self.plugin, '_load_host_uuid', return_value=self.host), \
                patch.object(self.plugin, 'discover_capabilities', return_value={
                    'supported': True, 'ksm': True, 'zram': True,
                    'writeback': True, 'ksmZeroPages': True}):
            stale = self.plugin.apply(base)
            self.assertFalse(stale.get('success'), stale)
            self.assertIn(stale.get('status'), ('Failed', 'Unknown'), stale)
            expired = dict(base)
            expired['operationUuid'] = 'integration-vm-expired'
            expired['expectedInstanceGeneration'] = os.environ['MEMORY_OPTIMIZATION_VM_GENERATION']
            expired['participation'] = 'auto'
            expired['policy'] = {'participation': 'auto'}
            expired['licensePermit'] = dict(self._permit(), expiresAt=int(time.time() * 1000) - 1)
            accepted = self.plugin.apply(expired)
            self.assertTrue(accepted.get('success'), accepted)
            self.assertEqual('Succeeded', accepted.get('status'), accepted)

    def test_pause_is_safe_without_permit_and_reconcile_unknown_is_not_success(self):
        with patch.object(self.plugin, '_load_host_uuid', return_value=self.host):
            paused = self.plugin.apply({
                'action': 'pause', 'scope': 'host', 'hostUuid': self.host,
                'operationUuid': 'integration-pause-no-permit',
                'desiredRevision': 1})
            self.assertTrue(paused.get('success'), paused)
            self.assertEqual('Succeeded', paused.get('status'), paused)
            lifecycle = paused.get('state', {}).get('lifecycle', paused)
            self.assertTrue(lifecycle.get('paused'), paused)
            self.assertEqual('paused', lifecycle.get('activeState'), paused)
            resumed = self.plugin.apply({
                'action': 'resume', 'scope': 'host', 'hostUuid': self.host,
                'operationUuid': 'integration-resume', 'desiredRevision': 1,
                'expectedControlOperationUuid': 'integration-pause-no-permit'})
            self.assertTrue(resumed.get('success'), resumed)
            self.assertEqual('Succeeded', resumed.get('status'), resumed)
            resumed_lifecycle = resumed.get('state', {}).get('lifecycle', resumed)
            self.assertFalse(resumed_lifecycle.get('paused'), resumed)
            self.assertEqual('compatibility', resumed_lifecycle.get('activeState'), resumed)
            # Repeated read-only GETs must return a lifecycle snapshot and
            # must not renew or otherwise mutate the pause/resume state.
            first = self.plugin.service_call('state', {})
            second = self.plugin.service_call('state', {})
            self.assertEqual(first.get('lifecycle'), second.get('lifecycle'))
            self.assertFalse(second.get('lifecycle', {}).get('paused'), second)
            reconciled = json.loads(self.plugin.reconcile({'body': json.dumps({
                'operationUuid': 'integration-operation-does-not-exist'})})
            )
            self.assertFalse(reconciled.get('success'), reconciled)
            self.assertEqual('Unknown', reconciled.get('status'), reconciled)

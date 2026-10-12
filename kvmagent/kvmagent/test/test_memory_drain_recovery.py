"""Durable drain recovery with fake systemd/native readback, no real swapoff."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import sys
from unittest import TestCase
try:
    from mock import patch
except ImportError:
    from unittest.mock import patch
from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin


class TestDrainRecovery(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mem-drain-recovery-')
        self.addCleanup(shutil.rmtree, self.root)
        self.config = {'hostUuid': 'host', 'operationDir': self.root,
                       'drainDir': self.root, 'drainConfig': self.root + '/config',
                       'drainBinary': self.root + '/binary'}
        for name in ('config', 'binary'):
            with open(self.root + '/' + name, 'w'):
                pass
        self.plugin = self.new_plugin()
        self.command = {'operationUuid': 'drain-op', 'hostUuid': 'host', 'action': 'drain',
                        'poolGeneration': 'pool-a', 'device': '/dev/zram0'}
        self.receipt = {'state': 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED',
                        'active': False, 'reset_performed': False,
                        'pool_generation': 'pool-a', 'device': '/dev/zram0'}
        self.plugin._record_operation(self.command, 'PREPARING')

    def new_plugin(self):
        plugin = MemoryOptimizationPlugin()
        plugin.configure(self.config)
        return plugin

    def prepare(self):
        with patch.object(subprocess, 'check_call'):
            self.plugin._start_stock_drain(self.command)

    def reconcile(self, plugin=None):
        plugin = plugin or self.plugin
        return json.loads(plugin.reconcile({'body': json.dumps({
            'hostUuid': 'host', 'operationUuid': 'drain-op'})}))

    def write_receipt(self, receipt=None):
        with open(self.root + '/drain-op.receipt.json', 'w') as stream:
            json.dump(self.receipt if receipt is None else receipt, stream)

    def test_intent_failure_prevents_stop_and_executor_launch(self):
        with patch('os.rename', side_effect=IOError('disk full')), \
                patch.object(subprocess, 'check_call') as call:
            with self.assertRaises(IOError):
                self.plugin._start_stock_drain(self.command)
        call.assert_not_called()

    def test_pending_survives_multiple_queries_and_agent_restart(self):
        self.prepare()
        with patch.object(subprocess, 'check_output', return_value=b'activating\n'), \
                patch.object(subprocess, 'check_call') as start:
            for plugin in (self.plugin, self.new_plugin(), self.new_plugin()):
                result = self.reconcile(plugin)
                self.assertEqual('DRAIN_RECEIPT_PENDING', result['reasonCode'])
                self.assertEqual('DRAINING', result['state']['phase'])
            start.assert_not_called()
        self.write_receipt()
        with patch.object(subprocess, 'check_output', return_value=json.dumps(self.receipt).encode()) as check:
            self.assertEqual('Succeeded', self.reconcile(self.new_plugin())['status'])
            self.assertEqual('--drain-check', check.call_args[0][0][-1])

    def test_bad_receipt_never_succeeds_or_launches_native_check(self):
        self.prepare()
        for changes in ({'device': '/dev/zram1'}, {'pool_generation': 'pool-b'},
                        {'active': True}, {'reset_performed': None}, {'reset_performed': True}):
            self.write_receipt(dict(self.receipt, **changes))
            with patch.object(subprocess, 'check_output') as check:
                self.assertEqual('Unknown', self.reconcile()['status'])
                check.assert_not_called()

    def test_fresh_native_check_is_mandatory_and_must_match(self):
        self.prepare()
        self.write_receipt()
        for changes in ({'device': '/dev/zram1'}, {'pool_generation': 'pool-b'},
                        {'active': True}, {'reset_performed': None}):
            with patch.object(subprocess, 'check_output', return_value=json.dumps(
                    dict(self.receipt, **changes)).encode()):
                self.assertEqual('DRAIN_CHECK_UNVERIFIED', self.reconcile()['reasonCode'])
        with patch.object(subprocess, 'check_output', side_effect=OSError('missing binary')):
            self.assertEqual('Unknown', self.reconcile()['status'])

    def test_cross_boot_never_reuses_receipt(self):
        self.prepare()
        self.write_receipt()
        with patch.object(self.plugin, '_current_boot_id', return_value='another-boot'), \
                patch.object(subprocess, 'check_output') as check:
            self.assertEqual('OPERATION_BOOT_CHANGED', self.reconcile()['reasonCode'])
            check.assert_not_called()

    def test_native_disable_requires_actual_readback(self):
        responses = iter([
            {'host_zram': {'pool_generation': 'pool-a', 'device': '/dev/zram0'}},
            {'revision': 1, 'efficiency_enabled': True}, {'success': True},
            {'revision': 2, 'efficiency_enabled': True}])
        self.plugin._service_request = lambda *args: next(responses)
        with self.assertRaises(RuntimeError):
            self.plugin._prepare_stock_drain(self.command)

    def test_platform_drain_freezes_current_pool_when_request_has_no_pool_field(self):
        responses = iter([
            {'host_zram': {'pool_generation': 'pool-a', 'device': '/dev/zram0'}},
            {'revision': 1, 'efficiency_enabled': False}])
        self.plugin._service_request = lambda *args: next(responses)
        self.assertEqual({'poolGeneration': 'pool-a', 'device': '/dev/zram0'},
                         self.plugin._prepare_stock_drain({'operationUuid': 'drain-op'}))

    def test_control_lock_is_released_on_process_death_without_replaying_intent(self):
        lock_path = self.root + '/.host-control.flock'
        subprocess.check_call([sys.executable, '-c',
            'import os,fcntl,sys; f=open(sys.argv[1],"a"); '
            'fcntl.flock(f,fcntl.LOCK_EX); os._exit(0)', lock_path])
        outcome, claimed = self.plugin._claim_operation(self.command)
        self.assertFalse(claimed)
        self.assertEqual('OPERATION_RECONCILE_REQUIRED', outcome['reasonCode'])
        other = {'hostUuid': 'host', 'operationUuid': 'new-op'}
        lock, claimed = self.plugin._claim_operation(other)
        self.assertTrue(claimed)
        try:
            concurrent, accepted = self.new_plugin()._claim_operation({
                'hostUuid': 'host', 'operationUuid': 'concurrent'})
            self.assertFalse(accepted)
            self.assertIsNone(concurrent)
        finally:
            self.plugin._release_operation(lock)

    def ksm_only(self):
        command = {'hostUuid': 'host', 'operationUuid': 'ksm-op', 'desiredRevision': 1,
                   'policy': {'ksm': {'mode': 'Active'}, 'zram': {'enabled': False}}}
        self.plugin._record_operation(command, 'APPLIED', {'status': 'Succeeded'})
        self.plugin._set_active_control('ksm-op')
        return command

    def test_pause_stops_ksm_even_when_optional_go_is_unreachable(self):
        self.ksm_only()
        with patch.object(self.plugin, '_control_managed_ksm') as control, \
                patch.object(self.plugin, 'service_call', side_effect=IOError('not installed')) as go:
            self.plugin.socket_path = self.root + '/absent.sock'
            result = self.plugin.apply({'action': 'pause', 'hostUuid': 'host', 'operationUuid': 'pause-ksm'})
            self.assertEqual('Succeeded', result['status'])
            control.assert_called_once_with('pause')
            go.assert_not_called()

    def test_reconcile_does_not_return_cached_applied_revision_after_ksm_drift(self):
        command = self.ksm_only()
        with patch.object(subprocess, 'check_output', return_value=b'configRevision=1\nrun=0\n'):
            result = json.loads(self.plugin.reconcile({'body': json.dumps({
                'hostUuid': 'host', 'operationUuid': command['operationUuid']})}))
            self.assertEqual('Unknown', result['status'])
            self.assertFalse(result['success'])

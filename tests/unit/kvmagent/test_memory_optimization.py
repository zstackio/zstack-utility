"""Converge the host to the desired memory optimisation through a fake service."""
import errno
import json
import os
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from kvmagent.plugins import memory_optimization as module
from kvmagent.plugins import memory_optimization_ksm_native as ksm_native
from kvmagent.plugins.memory_optimization import Converging, MemoryOptimizationPlugin, Rejected
from kvmagent.plugins import memory_writeback_backends as backends
from kvmagent.plugins import memory_writeback_maintenance as maintenance
from kvmagent.plugins import memory_swap_disks

HOST = '1' * 32
POOL = 'a' * 64
OPERATION = '0123456789abcdef' * 2


class FakeService(object):
    """The ZRAM service's idempotent API, as the Agent sees it."""

    def __init__(self):
        self.calls = []
        self.vm_policy = {}
        self.pool = POOL
        self.paused = False
        self.maintenance = False
        self.efficiency = False
        self.capacity = {'logical_capacity': {}, 'physical_memory_limit': {}}
        self.capacity_state = 'APPLIED'
        self.capacity_reason = None
        self.writeback = False
        self.receipts = {'pool': {'stage': 'NOT_STARTED'}, 'backend': {'stage': 'NOT_STARTED'}}
        self.activation_error = None
        self.hold_error = None
        self.activated = set()
        self.pool_reason = 'NO_QUALIFIED_MANAGED_POOL: VM_INVENTORY_EMPTY'

    def __call__(self, action, payload):
        self.calls.append((action, dict(payload)))
        if action == 'status':
            return {'host_zram': {'pool_generation': self.pool, 'reason': None if self.pool else self.pool_reason},
                    'mode': 'reclaim',
                    'lifecycle': {'paused': self.paused}, 'maintenance_blocks_activation': self.maintenance,
                    'pending_operations': None, 'backend_resource': {}}
        if action == 'host-cpu-state':
            return {'efficiency_enabled': self.efficiency, 'idle_cpu_threshold_percent': 5,
                    'idle_duration_seconds': 60}
        if action == 'host-cpu':
            self.efficiency = payload['efficiency_enabled']
            return {'revision': 1}
        if action == 'capacity-state':
            return {'desired': {'configured': dict(self.capacity)}, 'apply_state': self.capacity_state,
                    'reason': self.capacity_reason}
        if action == 'capacity':
            self.capacity = {'logical_capacity': payload['logical_capacity'],
                             'physical_memory_limit': payload['physical_memory_limit']}
            if self.pool:
                self.capacity_state = 'PENDING_MAINTENANCE'
            return {'_http_status': 202 if self.pool else 200}
        if action == 'tuning-state':
            return {'settings': {'host_floor_bytes': 0, 'writeback': {'enabled': self.writeback, 'batch_bytes': 1}}}
        if action == 'tuning':
            self.writeback = payload['settings']['writeback']['enabled']
            return {}
        if action == 'lifecycle-pause':
            self.paused = payload['action'] == 'pause'
            return {'paused': self.paused}
        if action == 'lifecycle-activate-maintenance':
            if self.activation_error:
                return {'_http_status': 409, 'error': self.activation_error}
            if self.writeback:
                return {'_http_status': 409, 'error': 'MAINTENANCE_ACTIVATION_WRITEBACK_MUST_REMAIN_DISABLED'}
            if payload['request_id'] in self.activated:
                # One activation per preparation: a repeated one answers its receipt and changes nothing.
                return {'receipt': {'stage': 'UNPAUSED'}}
            prepared = self.receipts['pool']
            # Like the service: a completed pool preparation of this generation must be named exactly;
            # a backend one is checked by its own identity.
            if prepared.get('stage') == 'APPLIED' and prepared.get('pool_generation') == payload['expected_pool_generation'] \
                    and prepared.get('expected_control_operation_uuid') != payload['expected_control_operation_uuid']:
                # The service activates only the exact preparation it recorded.
                return {'_http_status': 409, 'error': 'MAINTENANCE_ACTIVATION_PREPARATION_MISMATCH'}
            self.activated.add(payload['request_id'])
            self.paused = False
            return {'receipt': {'stage': 'UNPAUSED'}}
        if action in ('zram-pool-maintenance-finalize', 'backend-maintenance-finalize'):
            kind = 'pool' if action.startswith('zram') else 'backend'
            self.receipts[kind] = dict(self.receipts[kind], stage='APPLIED')
            self.maintenance = False
            return self.receipts[kind]
        if action == 'migration-hold' and self.hold_error:
            return {'_http_status': 409, 'error': self.hold_error}
        if action == 'vm-policy':
            self.vm_policy[payload['_resource']] = {'mode': payload['mode'], 'instance_generation': payload['expected_instance_generation']}
        if action == 'vm-policy-state':
            return self.vm_policy[payload['_resource']]
        if action in ('vm-policy', 'migration-hold', 'accounting', 'backend-view'):
            return {'claimed': True}
        raise AssertionError('unexpected service call %s' % action)

    def actions(self):
        return [action for action, _ in self.calls if not action.endswith('-state') and action != 'status']


@pytest.fixture
def host(tmp_path, monkeypatch):
    service = FakeService()
    plugin = MemoryOptimizationPlugin(service_call=service)
    plugin.configure({'hostUuid': HOST, 'operationDir': str(tmp_path / 'operations'),
                      'zramConfig': str(tmp_path / 'config.json')})
    (tmp_path / 'config.json').write_text(json.dumps({'managed': True, 'mode': 'reclaim',
                                                      'resource_authorized': True, 'device': '/dev/zram0'}))
    world = {'unit': 'active', 'drained': None, 'executors': {}, 'started': [], 'never_used': False}
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {'supported': True, 'ksm': True, 'zram': True})
    monkeypatch.setattr(plugin, '_managed_service_installed', lambda: True)
    monkeypatch.setattr(plugin, '_managed_service_never_used', lambda: world['never_used'])
    monkeypatch.setattr(plugin, '_service_available', lambda: world['unit'] == 'active')
    monkeypatch.setattr(plugin, '_service_unit_state', lambda: world['unit'])
    monkeypatch.setattr(plugin, '_drain_check', lambda: world['drained'])
    monkeypatch.setattr(plugin, '_executor_state',
                        lambda unit: world['executors'].get(unit, ('absent', None)))
    monkeypatch.setattr(plugin, '_observe', lambda: {})
    monkeypatch.setattr(plugin, '_converge_ksm', lambda ksm, control: world.setdefault('ksm', []).append((ksm, control)))
    monkeypatch.setattr(plugin, '_receipt', lambda kind: dict(service.receipts[kind]))
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: 'boot')
    monkeypatch.setattr(plugin, '_zram_device_reset', lambda: world.get('zram_reset', True), raising=False)
    (tmp_path / 'swappiness').write_text('60\n')
    monkeypatch.setattr(plugin, 'SWAPPINESS_PATH', str(tmp_path / 'swappiness'))

    def run_executor(unit, argument, request=None):
        world['started'].append((unit, argument, request))
        world['executors'][unit] = ('running', None)
    monkeypatch.setattr(plugin, '_run_executor', run_executor)

    def command(argv, timeout):
        if argv[:2] == ['systemctl', 'stop']:
            world['unit'] = 'inactive'
        if argv[:2] == ['systemctl', 'start']:
            world['unit'] = 'active'
        if argv[:2] == ['systemctl', 'reset-failed']:
            world['executors'].pop(argv[2], None)
        return ''
    monkeypatch.setattr(plugin, '_bounded_command_output', staticmethod(command))
    return plugin, service, world


def desired(control='active', zram=True, logical=None, writeback=False, ksm=None):
    return {'control': control, 'ksm': {'enabled': ksm},
            'zram': {'enabled': zram, 'logicalCapacityBytes': logical, 'ramLimitBytes': None},
            'writeback': {'enabled': writeback}}


def apply(plugin, generation, want):
    return plugin.apply({'hostUuid': HOST, 'generation': generation, 'desired': want})


def test_invalid_requests_are_rejected_without_side_effects(host):
    plugin, service, world = host
    assert apply(plugin, 1, {'control': 'sideways'})['reasonCode'] == 'INVALID_DESIRED_CONFIGURATION'
    assert plugin.apply({'hostUuid': 'other', 'generation': 1, 'desired': desired()})['reasonCode'] == 'HOST_IDENTITY_UNKNOWN'
    assert apply(plugin, True, desired())['reasonCode'] == 'INVALID_GENERATION'
    assert apply(plugin, 1, desired(logical=4097))['reasonCode'] == 'INVALID_DESIRED_CONFIGURATION'
    assert apply(plugin, 1, desired(ksm=1))['reasonCode'] == 'INVALID_DESIRED_CONFIGURATION'
    assert apply(plugin, 1, desired(zram=0))['reasonCode'] == 'INVALID_DESIRED_CONFIGURATION'
    assert service.actions() == [] and plugin._applied_generation() is None


@pytest.mark.parametrize('memtotal_kb', [7000000, 8 << 20, 64 << 20])
def test_ksm_sleep_is_the_nearest_the_vendor_script_can_reach(memtotal_kb):
    native = ksm_native.native_sleep_msec(20, memtotal_kb)
    assert max(10, native * ksm_native.SLEEP_BASE_KB // memtotal_kb) in (20, 21)


@pytest.mark.parametrize('zero', [None, False])
def test_unmanaged_ksm_takes_out_only_the_block_the_agent_added(host, tmp_path, monkeypatch, zero):
    plugin, service, world = host
    conf = tmp_path / 'ksmtuned.conf'
    conf.write_text(ksm_native.render_config('KSM_MONITOR_INTERVAL=60\n', 1, 2000, 20))
    monkeypatch.setattr(plugin, 'KSM_CONF', str(conf))
    monkeypatch.setattr(plugin, 'KSM_LOCK', str(tmp_path / 'lock' / 'ksm.lock'))
    monkeypatch.setattr(plugin, 'NATIVE_KSM_FILES', [str(conf)])
    monkeypatch.setattr(plugin, '_native_service_state', lambda unit, default: 'active')
    monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: '1')
    written, commands = [], []
    monkeypatch.setattr(plugin, '_write_ksm_sysfs', lambda name, value: written.append((name, value)))
    monkeypatch.setattr(module.subprocess, 'check_call', lambda argv: commands.append(argv))
    # Zero pages may still be managed; the ksmtuned settings belong to KSM itself.
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': zero}, 'active')
    assert conf.read_text() == 'KSM_MONITOR_INTERVAL=60\n'
    assert written == ([] if zero is None else [('use_zero_pages', '0')])
    # A running ksmtuned reads its settings only when it starts; it keeps running.
    assert commands == [['systemctl', 'restart', plugin.KSM_TUNED_UNIT]]
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': zero}, 'active')
    assert len(commands) == 1


@pytest.mark.parametrize('tuned', ['activating', 'deactivating', None])
def test_unmanaged_ksm_keeps_the_block_until_ksmtuned_settles(host, tmp_path, monkeypatch, tuned):
    plugin, service, world = host
    conf = tmp_path / 'ksmtuned.conf'
    managed = ksm_native.render_config('KSM_MONITOR_INTERVAL=60\n', 1, 2000, 20)
    conf.write_text(managed)
    monkeypatch.setattr(plugin, 'KSM_CONF', str(conf))
    monkeypatch.setattr(plugin, 'KSM_LOCK', str(tmp_path / 'lock' / 'ksm.lock'))
    states = {'tuned': tuned}
    monkeypatch.setattr(plugin, '_native_service_state', lambda unit, default: states['tuned'])
    commands = []
    monkeypatch.setattr(module.subprocess, 'check_call', lambda argv: commands.append(argv))
    # Without a settled state the restart could be missed, and the block would be gone for the next try.
    with pytest.raises(Converging):
        MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    assert conf.read_text() == managed and commands == []
    states['tuned'] = 'active'
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    assert conf.read_text() == 'KSM_MONITOR_INTERVAL=60\n'
    assert commands == [['systemctl', 'restart', plugin.KSM_TUNED_UNIT]]


def test_unmanaged_ksm_restarts_ksmtuned_again_after_a_failed_restart(host, tmp_path, monkeypatch):
    plugin, service, world = host
    conf = tmp_path / 'ksmtuned.conf'
    conf.write_text(ksm_native.render_config('KSM_MONITOR_INTERVAL=60\n', 1, 2000, 20))
    monkeypatch.setattr(plugin, 'KSM_CONF', str(conf))
    monkeypatch.setattr(plugin, 'KSM_LOCK', str(tmp_path / 'lock' / 'ksm.lock'))
    monkeypatch.setattr(plugin, '_native_service_state', lambda unit, default: 'active')
    commands = []

    def restart(argv):
        commands.append(argv)
        if len(commands) == 1:
            raise module.subprocess.CalledProcessError(1, argv)
    monkeypatch.setattr(module.subprocess, 'check_call', restart)
    with pytest.raises(module.subprocess.CalledProcessError):
        MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    # The block is already gone; the next pass still restarts the ksmtuned that kept the old settings.
    assert conf.read_text() == 'KSM_MONITOR_INTERVAL=60\n'
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    assert commands == [['systemctl', 'restart', plugin.KSM_TUNED_UNIT]] * 2


def test_unmanaged_ksm_keeps_restarting_a_ksmtuned_left_failed_until_it_runs(host, tmp_path, monkeypatch):
    plugin, service, world = host
    conf = tmp_path / 'ksmtuned.conf'
    conf.write_text(ksm_native.render_config('KSM_MONITOR_INTERVAL=60\n', 1, 2000, 20))
    monkeypatch.setattr(plugin, 'KSM_CONF', str(conf))
    monkeypatch.setattr(plugin, 'KSM_LOCK', str(tmp_path / 'lock' / 'ksm.lock'))
    record = tmp_path / 'lock' / plugin.KSM_TUNED_RESTART
    states = {'tuned': 'active', 'starts': False}
    monkeypatch.setattr(plugin, '_native_service_state', lambda unit, default: states['tuned'])
    commands = []

    def restart(argv):
        commands.append(argv)
        # A restart whose start fails leaves ksmtuned failed.
        states['tuned'] = 'active' if states['starts'] else 'failed'
        if not states['starts']:
            raise module.subprocess.CalledProcessError(1, argv)
    monkeypatch.setattr(module.subprocess, 'check_call', restart)
    for _ in range(2):
        with pytest.raises(module.subprocess.CalledProcessError):
            MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
        assert record.exists(), 'the restart is still owed while ksmtuned is %s' % states['tuned']
    states['starts'] = True
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    assert states['tuned'] == 'active' and not record.exists()
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    assert commands == [['systemctl', 'restart', plugin.KSM_TUNED_UNIT]] * 3


def test_a_disabled_ksm_drops_a_restart_still_owed_and_ksmtuned_stays_stopped(host, tmp_path, monkeypatch):
    plugin, service, world = host
    conf = tmp_path / 'ksmtuned.conf'
    conf.write_text(ksm_native.render_config('KSM_MONITOR_INTERVAL=60\n', 1, 2000, 20))
    monkeypatch.setattr(plugin, 'KSM_CONF', str(conf))
    monkeypatch.setattr(plugin, 'KSM_LOCK', str(tmp_path / 'lock' / 'ksm.lock'))
    monkeypatch.setattr(plugin, 'NATIVE_KSM_FILES', [str(conf)])
    monkeypatch.setattr(plugin, '_read_ksm_zero_pages', lambda: 'unsupported')
    monkeypatch.setattr(plugin, '_read_ksm_sysfs', lambda name: '0')
    monkeypatch.setattr(plugin, '_write_ksm_sysfs', lambda name, value: None)
    record = tmp_path / 'lock' / plugin.KSM_TUNED_RESTART
    states = {'tuned': 'active'}
    monkeypatch.setattr(plugin, '_native_service_state', lambda unit, default: states['tuned'])
    commands = []

    def systemctl(argv):
        commands.append(argv)
        if argv[1] == 'restart':
            states['tuned'] = 'failed'
            raise module.subprocess.CalledProcessError(1, argv)
        if argv[1] == 'stop' and argv[2] == plugin.KSM_TUNED_UNIT:
            states['tuned'] = 'inactive'
    monkeypatch.setattr(module.subprocess, 'check_call', systemctl)
    with pytest.raises(module.subprocess.CalledProcessError):
        MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    assert record.exists()
    # Turning KSM off stops ksmtuned on purpose; the restart owed from the release no longer applies.
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': False, 'zeroPagesEnabled': None}, 'active')
    assert not record.exists(), 'an explicit stop cancels the restart still owed'
    del commands[:]
    MemoryOptimizationPlugin._converge_ksm(plugin, {'enabled': None, 'zeroPagesEnabled': None}, 'active')
    assert commands == [] and states['tuned'] == 'inactive', 'unmanaged KSM keeps the stopped ksmtuned stopped'


@pytest.mark.parametrize('writeback, running', [(None, False), (False, False), (False, True)])
def test_unmanaged_zram_leaves_reclaim_as_it_is(host, writeback, running):
    plugin, service, world = host
    service.efficiency, service.writeback = True, running
    # none on the MN: like an unmanaged KSM, the running state stays as it is; writeback off is its own switch.
    result = apply(plugin, 9, desired(zram=None, writeback=writeback))
    assert result['status'] == 'Succeeded', result
    assert service.efficiency is True and service.writeback is False
    if not running:
        assert 'host-cpu' not in service.actions()


def test_a_busy_host_answers_in_progress_within_the_callers_budget(host):
    plugin, service, world = host
    budget = {'communication': {'communicationSeconds': 1}}
    with plugin._host_lock():
        started = time.time()
        result = plugin.apply(dict(budget, hostUuid=HOST, generation=3, desired=desired()))
        hold = json.loads(plugin.migration_hold({module.http.REQUEST_BODY: json.dumps(dict(
            budget, hostUuid=HOST, operationUuid='m' * 32, resourceUuid='v' * 32, holdAction='acquire',
            poolGeneration=POOL))}))
    assert time.time() - started < 5
    assert result['status'] == 'Converging' and result['reasonCode'] == 'HOST_OPERATION_IN_PROGRESS'
    # The MN retries a hold that is in progress instead of recording it unknown.
    assert hold['status'] == 'Converging' and hold['reasonCode'] == 'HOST_OPERATION_IN_PROGRESS', hold


@pytest.mark.parametrize('error, status, retry', [('MIGRATION_HOLD_WAITING_FOR_IN_FLIGHT', 'Converging', 1),
                                                  ('POOL_GENERATION_MISMATCH', 'Failed', None)])
def test_a_hold_waiting_for_a_running_reclaim_is_retried_soon(host, error, status, retry):
    plugin, service, world = host
    service.hold_error = error
    hold = json.loads(plugin.migration_hold({module.http.REQUEST_BODY: json.dumps(dict(
        hostUuid=HOST, operationUuid='m' * 32, resourceUuid='v' * 32, holdAction='acquire', poolGeneration=POOL))}))
    assert (hold['status'], hold['reasonCode'], hold.get('retryAfterSeconds')) == (status, error, retry), hold


def test_an_older_generation_is_rejected_while_a_newer_one_converges(host):
    plugin, service, world = host
    world['unit'] = 'starting'
    assert apply(plugin, 11, desired())['reasonCode'] == 'SERVICE_STARTING'
    world['unit'] = 'active'
    stale = apply(plugin, 10, desired(zram=False))
    assert stale['reasonCode'] == 'STALE_GENERATION'
    # The Host names the generation it took, so a sender whose record restarted (a re-added Host) numbers above it.
    assert stale['acceptedGeneration'] == 11 and stale['appliedGeneration'] is None
    assert apply(plugin, 11, desired())['status'] == 'Succeeded'


def test_an_older_generation_is_rejected_without_changes(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_managed_service_installed', lambda: False)
    assert apply(plugin, 4, desired(zram=None, ksm=True))['status'] == 'Succeeded'
    stale = apply(plugin, 3, desired(zram=None, ksm=False))
    assert stale['status'] == 'Failed' and stale['reasonCode'] == 'STALE_GENERATION'
    assert stale['appliedGeneration'] == 4 and stale['acceptedGeneration'] == 4
    # A Host that recorded no accepted generation (an earlier Agent) still names the one it applied.
    os.remove(os.path.join(plugin.operation_dir, 'accepted-generation'))
    assert apply(plugin, 3, desired(zram=None, ksm=False))['acceptedGeneration'] == 4
    assert world['ksm'] == [({'enabled': True, 'zeroPagesEnabled': None}, 'active')]
    assert apply(plugin, 4, desired(zram=None, ksm=True))['status'] == 'Succeeded'


def test_ksm_only_host_needs_no_zram_service(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_managed_service_installed', lambda: False)
    result = apply(plugin, 3, desired(zram=None, ksm=True))
    assert result['status'] == 'Succeeded' and result['appliedGeneration'] == 3
    assert world['ksm'] == [({'enabled': True, 'zeroPagesEnabled': None}, 'active')]
    assert service.calls == []


def test_enabling_zram_writes_capacity_tuning_then_opens_reclaim(host):
    plugin, service, world = host
    service.pool = None
    result = apply(plugin, 5, desired(logical=8 << 30, writeback=True))
    assert result['status'] == 'Converging' and result['reasonCode'] == 'WAITING_FOR_POOL'
    assert service.actions() == ['capacity', 'tuning', 'host-cpu']
    assert service.efficiency is True and service.writeback is True
    assert service.capacity['logical_capacity'] == {'bytes': 8 << 30}


@pytest.mark.parametrize('current, expected', [('0\n', '60'), ('30\n', '30\n')])
def test_zram_needs_a_swappiness_above_zero(host, tmp_path, monkeypatch, current, expected):
    plugin, service, world = host
    swappiness, conf = tmp_path / 'swappiness', tmp_path / '99-zstack-zram.conf'
    swappiness.write_text(current)
    monkeypatch.setattr(plugin, 'SWAPPINESS_PATH', str(swappiness))
    monkeypatch.setattr(plugin, 'SWAPPINESS_CONF', str(conf))
    assert apply(plugin, 3, desired())['status'] == 'Succeeded'
    assert swappiness.read_text() == expected
    # A value above zero is the administrator's; only a zero is raised and kept across reboots.
    assert conf.exists() is (current == '0\n')


def test_resending_the_applied_configuration_changes_nothing(host):
    plugin, service, world = host
    service.efficiency, service.writeback = True, True
    service.capacity = {'logical_capacity': {'bytes': 8 << 30}, 'physical_memory_limit': {}}
    result = apply(plugin, 6, desired(logical=8 << 30, writeback=True))
    assert result['status'] == 'Succeeded' and service.actions() == []


def test_an_unset_capacity_matches_the_service_default_without_rewriting_it(host):
    plugin, service, world = host
    service.efficiency = True
    service.capacity = {'logical_capacity': {'percent_of_host': 50.0},
                        'physical_memory_limit': {'percent_of_logical': 100.0}}
    result = apply(plugin, 6, desired())
    assert result['status'] == 'Succeeded' and service.actions() == []
    assert world['started'] == []


def test_a_pool_on_the_earlier_default_ram_limit_keeps_it(host):
    plugin, service, world = host
    service.efficiency = True
    # The service stores its default as percentages; the earlier one limited the RAM to half the logical capacity.
    service.capacity = {'logical_capacity': {'percent_of_host': 50.0},
                        'physical_memory_limit': {'percent_of_logical': 50.0}}
    result = apply(plugin, 6, desired())
    # An unset capacity still matches it: the pool is not drained and rebuilt unasked.
    assert result['status'] == 'Succeeded' and service.actions() == []
    assert world['started'] == []


def test_a_drained_host_with_its_service_stopped_rebuilds_instead_of_rejecting(host, monkeypatch):
    plugin, service, world = host
    world['unit'] = 'inactive'
    world['drained'] = {'state': MemoryOptimizationPlugin.DRAINED, 'pool_generation': POOL}
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'zram': False, 'zramReasonCode': 'SERVICE_RECLAIM_CAPABILITY_UNKNOWN',
        'interfaces': {'cgroupv2': True, 'memory_reclaim': True}})
    result = apply(plugin, 7, desired())
    assert result['status'] == 'Converging', result
    assert world['started'][0][1] == '--prepare-zram-pool'


def test_an_unknown_capability_without_reclaim_interfaces_leaves_zram_unmanaged(host, monkeypatch):
    plugin, service, world = host
    world['unit'] = 'inactive'
    world['drained'] = {'state': MemoryOptimizationPlugin.DRAINED, 'pool_generation': POOL}
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'zram': False, 'zramReasonCode': 'SERVICE_RECLAIM_CAPABILITY_UNKNOWN',
        'interfaces': {'cgroupv2': True, 'memory_reclaim': False}})
    assert apply(plugin, 7, desired())['status'] == 'Succeeded'
    assert world['started'] == []


def test_a_running_service_with_an_unrecognized_capability_answer_is_left_unmanaged(host, monkeypatch):
    plugin, service, world = host
    # Only a stopped service is asked again after it starts; a running one answered and was not understood.
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'zram': False, 'zramReasonCode': 'SERVICE_RECLAIM_CAPABILITY_UNKNOWN',
        'service': True, 'interfaces': {'cgroupv2': True, 'memory_reclaim': True}})
    result = apply(plugin, 8, desired(writeback=True))
    assert result['status'] == 'Succeeded', result
    assert service.actions() == []


@pytest.mark.parametrize('capabilities, ksm', [
    ({'supported': True, 'ksm': True, 'zram': False, 'zramReasonCode': 'UNSUPPORTED_RECLAIM_KERNEL'}, True),
    ({'supported': False, 'ksm': False, 'zram': False, 'zramReasonCode': 'UNSUPPORTED_OS_RELEASE'}, None)])
def test_what_the_host_cannot_run_is_left_unmanaged_without_failing(host, monkeypatch, capabilities, ksm):
    plugin, service, world = host
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: capabilities)
    # A new cloud enables both by default; a Host without them must not fail and raise alarms.
    result = apply(plugin, 8, desired(ksm=True, writeback=True))
    assert result['status'] == 'Succeeded', result
    assert service.actions() == []
    assert world['ksm'] == [({'enabled': ksm, 'zeroPagesEnabled': None}, 'active')]


def test_a_new_capacity_for_a_live_pool_drains_it_for_rebuild(host):
    plugin, service, world = host
    service.efficiency = True
    result = apply(plugin, 7, desired(logical=8 << 30))
    assert result['status'] == 'Converging' and result['reasonCode'] == 'DRAINING'
    # Reclaim stops before the capacity write, and the drain pauses and stops the service.
    actions = service.actions()
    assert actions[:2] == ['host-cpu', 'capacity'] and 'lifecycle-pause' in actions
    assert world['unit'] == 'inactive' and world['started'][0][:2] == ('zstack-memory-drain-7', '--drain')
    assert result['appliedGeneration'] is None


def test_a_pool_reconciling_unknown_operations_is_not_drained(host):
    plugin, service, world = host
    service.efficiency = True
    service.capacity = {'logical_capacity': {'percent_of_host': 50.0},
                        'physical_memory_limit': {'percent_of_logical': 100.0}}
    service.capacity_state, service.capacity_reason = 'RECONCILING', 'UNKNOWN_OPERATION_REQUIRES_RECONCILIATION'
    result = apply(plugin, 7, desired())
    # The running service reconciles them itself; a drain is refused until then.
    assert result['status'] == 'Converging'
    assert result['reasonCode'] == 'UNKNOWN_OPERATION_REQUIRES_RECONCILIATION'
    assert world['unit'] == 'active' and world['started'] == [] and service.actions() == []
    service.capacity_state, service.capacity_reason = 'APPLIED', None
    assert apply(plugin, 7, desired())['status'] == 'Succeeded'


def test_first_enable_authorizes_the_packaged_config_then_waits_for_the_pool(host, tmp_path):
    plugin, service, world = host
    (tmp_path / 'config.json').write_text(json.dumps({'managed': True, 'mode': 'observe',
                                                      'resource_authorized': False}))
    service.pool = None
    first = apply(plugin, 1, desired())
    assert first['status'] == 'Converging' and first['reasonCode'] == 'SERVICE_STARTING'
    config = json.loads((tmp_path / 'config.json').read_text())
    assert config['mode'] == 'reclaim' and config['resource_authorized'] is True
    second = apply(plugin, 1, desired())
    assert second['status'] == 'Converging' and second['reasonCode'] == 'WAITING_FOR_POOL'
    assert second['retryAfterSeconds'] == MemoryOptimizationPlugin.WAIT_RETRY_SECONDS
    assert service.efficiency is True
    service.pool = POOL
    assert apply(plugin, 1, desired())['status'] == 'Succeeded'


def test_a_pool_is_not_drained_while_a_vm_is_migrating(host, monkeypatch):
    plugin, service, world = host
    original = plugin.service_call
    holds = [{'operation_id': OPERATION, 'pool_generation': POOL}]
    def native(action, payload):
        result = original(action, payload)
        if action == 'status':
            result = dict(result, lifecycle=dict(result.get('lifecycle') or {}, migrationHolds=list(holds)))
        return result
    monkeypatch.setattr(plugin, 'service_call', native)
    result = apply(plugin, 7, desired(control='drained'))
    assert result['status'] == 'Converging' and result['reasonCode'] == 'MIGRATION_IN_PROGRESS'
    assert world['unit'] == 'active' and world['started'] == []
    assert 'lifecycle-pause' not in service.actions()
    del holds[:]
    result = apply(plugin, 7, desired(control='drained'))
    assert result['reasonCode'] == 'DRAINING'


def test_drain_runs_once_and_completes_from_the_native_check(host):
    plugin, service, world = host
    service.efficiency = True
    first = apply(plugin, 9, desired(control='drained'))
    assert first['reasonCode'] == 'DRAINING' and len(world['started']) == 1
    assert service.paused is True and service.efficiency is False
    assert world['ksm'][-1][1] == 'drained'
    assert apply(plugin, 9, desired(control='drained'))['reasonCode'] == 'DRAINING'
    assert len(world['started']) == 1
    world['executors']['zstack-memory-drain-9'] = ('exited', 0)
    world['drained'] = {'state': MemoryOptimizationPlugin.DRAINED, 'pool_generation': POOL}
    assert apply(plugin, 9, desired(control='drained'))['status'] == 'Succeeded'
    # A drained host stays drained while paused or with ZRAM off.
    assert apply(plugin, 10, desired(control='paused'))['status'] == 'Succeeded'
    assert apply(plugin, 11, desired(zram=False))['status'] == 'Succeeded'
    assert len(world['started']) == 1


def test_a_failed_drain_reports_the_service_reason(host, monkeypatch):
    plugin, service, world = host
    world['executors']['zstack-memory-drain-9'] = ('exited', 1)
    monkeypatch.setattr(plugin, '_executor_error', lambda unit, default: 'DRAIN_RESERVE_UNQUALIFIED')
    result = apply(plugin, 9, desired(control='drained'))
    assert result['status'] == 'Failed' and result['reasonCode'] == 'DRAIN_RESERVE_UNQUALIFIED'
    # The failed step is cleared, so a resend of the same generation tries it again.
    assert apply(plugin, 9, desired(control='drained'))['reasonCode'] == 'DRAINING'
    assert world['started'][-1][:2] == ('zstack-memory-drain-9', '--drain')


def test_a_drain_waits_for_the_service_to_stop_before_it_starts(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_bounded_command_output', staticmethod(lambda argv, timeout: ''))
    world['unit'] = 'active'
    result = apply(plugin, 9, desired(control='drained'))
    assert result['reasonCode'] == 'SERVICE_STOPPING' and world['started'] == []


def test_a_drain_with_no_pool_holds_the_running_service_paused(host, monkeypatch):
    plugin, service, world = host
    # A reboot emptied the RAM-only pool, and with no VM running the service opens none.
    service.pool, service.efficiency = None, True
    record = {'kept': True}
    monkeypatch.setattr(plugin, '_no_recorded_pool', lambda: not record['kept'])
    # A pool still recorded may be one the service has not opened yet: it is not taken as none.
    assert apply(plugin, 24, desired(control='drained'))['reasonCode'] == 'DRAIN_POOL_IDENTITY_UNKNOWN'
    record['kept'] = False
    assert apply(plugin, 24, desired(control='drained'))['status'] == 'Succeeded'
    # Nothing to withdraw: held paused so that no pool forms, with the service left running.
    assert service.paused is True and service.efficiency is False
    assert world['unit'] == 'active' and world['started'] == []
    # Resume lifts the hold; the pool opens once a VM runs.
    assert apply(plugin, 25, desired())['reasonCode'] == 'WAITING_FOR_POOL'
    assert service.paused is False


def test_resume_after_drain_prepares_finalizes_and_activates_the_pool(host):
    plugin, service, world = host
    world['unit'], service.paused = 'inactive', True
    world['drained'] = {'state': MemoryOptimizationPlugin.DRAINED, 'pool_generation': POOL}
    first = apply(plugin, 12, desired())
    assert first['reasonCode'] == 'POOL_PREPARING'
    unit, argument, request = world['started'][0]
    assert (unit, argument) == ('zstack-memory-zram-pool-12', '--prepare-zram-pool')
    assert request['request_id'] == 'pool-12-' + POOL[:16] and request['expected_pool_generation'] == POOL
    # The executor reset the pool and recorded it; the service starts paused, behind its fence.
    world['executors'][unit] = ('exited', 0)
    service.receipts['pool'] = {'stage': 'AWAITING_SERVICE_READBACK', 'request_id': request['request_id'],
                                'expected_control_operation_uuid': request['expected_control_operation_uuid'],
                                'pool_generation': POOL, 'host_boot_id': 'boot'}
    service.pool, service.maintenance = None, True
    world['drained'] = None
    second = apply(plugin, 12, desired())
    assert world['unit'] == 'active' and service.receipts['pool']['stage'] == 'APPLIED'
    activation = [payload for action, payload in service.calls if action == 'lifecycle-activate-maintenance']
    assert activation and activation[0]['request_id'] == 'activate-' + request['request_id']
    assert activation[0]['expected_control_operation_uuid'] == request['expected_control_operation_uuid']
    assert service.paused is False and service.efficiency is True
    assert second['reasonCode'] == 'WAITING_FOR_POOL'
    service.pool = POOL
    assert apply(plugin, 12, desired())['status'] == 'Succeeded'


def test_a_rebuilt_pool_waits_paused_while_zram_is_off(host):
    plugin, service, world = host
    service.pool, service.paused = None, True
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-9-' + POOL[:16], 'pool_generation': POOL,
                                'expected_control_operation_uuid': 'pool-9-' + POOL[:16]}
    # KSM only: the pool is not wanted, so it is neither activated nor resumed and the configuration succeeds.
    result = apply(plugin, 9, desired(zram=False, ksm=True))
    assert result['status'] == 'Succeeded', result
    assert 'lifecycle-activate-maintenance' not in service.actions()
    assert ('lifecycle-pause', {'action': 'resume'}) not in service.calls
    assert service.paused is True
    # ZRAM on again opens the rebuilt pool through the service's activation.
    apply(plugin, 10, desired(zram=True, ksm=True))
    activation = [payload for action, payload in service.calls if action == 'lifecycle-activate-maintenance']
    assert activation and activation[-1]['request_id'] == 'activate-pool-9-' + POOL[:16]
    assert service.paused is False


def test_activation_names_the_preparation_of_the_current_drain(host, tmp_path):
    plugin, service, world = host
    service.pool, service.paused = None, True
    # Each kind keeps its latest receipt; the other kind's may be of an earlier drain cycle.
    service.receipts['backend'] = {'stage': 'APPLIED', 'request_id': 'backend-3-x', 'pool_generation': 'b' * 64}
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-9-' + POOL[:16], 'pool_generation': POOL,
                                'expected_control_operation_uuid': 'pool-9-' + POOL[:16]}
    apply(plugin, 9, desired())
    activation = [payload for action, payload in service.calls if action == 'lifecycle-activate-maintenance']
    assert activation[-1]['expected_pool_generation'] == POOL
    assert activation[-1]['request_id'] == 'activate-pool-9-' + POOL[:16]
    # A Host with a backend rebuilt its pool by preparing the backend, even after an earlier RAM-only rebuild.
    config = json.loads((tmp_path / 'config.json').read_text())
    config['backend'] = {'device': '/dev/vdb'}
    (tmp_path / 'config.json').write_text(json.dumps(config))
    service.calls[:] = []
    service.paused = True
    service.receipts['backend'] = {'stage': 'APPLIED', 'request_id': 'backend-24-x', 'pool_generation': 'b' * 64}
    apply(plugin, 10, desired())
    activation = [payload for action, payload in service.calls if action == 'lifecycle-activate-maintenance']
    assert activation[-1]['expected_pool_generation'] == 'b' * 64
    assert activation[-1]['request_id'] == 'activate-backend-24-x'
    assert service.paused is False


def test_a_writeback_host_activates_its_rebuilt_pool_before_writeback_is_on_again(host):
    plugin, service, world = host
    service.pool, service.paused, service.writeback = None, True, True
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-19-' + POOL[:16], 'pool_generation': POOL,
                                'expected_control_operation_uuid': 'pool-19-' + POOL[:16]}
    # The service keeps writeback as tuned before the drain, and activates only with it off.
    first = apply(plugin, 19, desired(writeback=True))
    assert first['reasonCode'] == 'WAITING_FOR_POOL', first
    assert service.paused is False and service.writeback is False
    service.pool = POOL
    assert apply(plugin, 19, desired(writeback=True))['status'] == 'Succeeded'
    assert service.writeback is True and service.efficiency is True


def test_a_service_started_over_a_drained_pool_rebuilds_the_pool(host):
    plugin, service, world = host
    # Started by hand after the drain: paused behind the drain fence, with an earlier cycle's receipt.
    service.pool, service.paused, service.maintenance = None, True, True
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-23-' + 'e' * 16, 'pool_generation': 'e' * 64,
                                'expected_control_operation_uuid': 'pool-23-' + 'e' * 16}
    service.activated.add('activate-pool-23-' + 'e' * 16)
    world['drained'] = {'state': MemoryOptimizationPlugin.DRAINED, 'pool_generation': POOL}
    result = apply(plugin, 30, desired())
    assert result['reasonCode'] == 'POOL_PREPARING', result
    assert world['unit'] == 'inactive'
    assert world['started'][-1][:2] == ('zstack-memory-zram-pool-30', '--prepare-zram-pool')
    assert world['started'][-1][2]['expected_pool_generation'] == POOL


def test_a_backend_prepared_without_a_pool_resumes_and_waits_for_the_pool(host):
    plugin, service, world = host
    service.pool, service.paused = None, True
    service.receipts['backend'] = {'stage': 'APPLIED', 'request_id': 'backend-35-x'}
    result = apply(plugin, 35, desired(writeback=True))
    assert result['reasonCode'] == 'WAITING_FOR_POOL', result
    assert service.paused is False
    assert not [action for action, payload in service.calls if action == 'lifecycle-activate-maintenance']


def test_a_preparation_of_an_earlier_boot_is_not_activated_again(host):
    plugin, service, world = host
    service.pool, service.paused = None, True
    # Activated in the boot that prepared it; a reboot emptied its device and the service
    # activates only preparations of the current boot.
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-54-x', 'pool_generation': POOL,
                                'host_boot_id': 'earlier-boot'}
    result = apply(plugin, 61, desired())
    assert result['reasonCode'] == 'WAITING_FOR_POOL', result
    assert service.paused is False
    assert 'lifecycle-activate-maintenance' not in service.actions()


@pytest.mark.parametrize('reason, expected', [
    ('NO_QUALIFIED_MANAGED_POOL: VM_INVENTORY_EMPTY', 'WAITING_FOR_POOL'),
    ('NO_QUALIFIED_MANAGED_POOL: open /var/lib/zram-efficiency/stock-pool.json: no such file', 'WAITING_FOR_POOL'),
    ('NO_QUALIFIED_MANAGED_POOL: EXCLUSIVE_ZRAM_ROUTE_REQUIRED: /dev/dm-1', 'WAITING_FOR_POOL: EXCLUSIVE_ZRAM_ROUTE_REQUIRED')])
def test_waiting_for_the_pool_names_what_blocks_it(host, reason, expected):
    plugin, service, world = host
    service.pool, service.pool_reason = None, reason
    assert apply(plugin, 35, desired())['reasonCode'] == expected


@pytest.mark.parametrize('error, retry', [('MAINTENANCE_ACTIVATION_NATIVE_NOT_READY', 5),
                                          ('MAINTENANCE_ACTIVATION_VM_INVENTORY_NOT_READY', 30)])
def test_an_activation_waiting_for_the_service_to_settle_is_converging(host, error, retry):
    plugin, service, world = host
    service.pool, service.paused = None, True
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-9-' + POOL[:16], 'pool_generation': POOL,
                                'expected_control_operation_uuid': 'pool-9-' + POOL[:16]}
    service.activation_error = error
    result = apply(plugin, 9, desired())
    assert (result['status'], result['reasonCode'], result['retryAfterSeconds']) == ('Converging', error, retry)
    assert service.paused is True


def test_a_rejected_activation_keeps_the_pool_drained(host):
    plugin, service, world = host
    service.paused, service.pool = True, None
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-12', 'pool_generation': POOL}
    service.activation_error = 'MAINTENANCE_ACTIVATION_PREPARATION_MISMATCH'
    result = apply(plugin, 13, desired())
    assert result['status'] == 'Failed' and result['reasonCode'] == 'MAINTENANCE_ACTIVATION_PREPARATION_MISMATCH'
    assert service.paused is True


def test_ordinary_pause_and_resume_use_the_lifecycle_gate(host):
    plugin, service, world = host
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'older-cycle', 'pool_generation': 'b' * 64}
    assert apply(plugin, 14, desired(control='paused'))['status'] == 'Succeeded' and service.paused
    assert world['ksm'][-1][1] == 'paused'
    assert apply(plugin, 15, desired())['status'] == 'Succeeded' and not service.paused
    assert 'lifecycle-activate-maintenance' not in service.actions()


def test_a_maintenance_needing_review_is_reported_not_retried(host):
    plugin, service, world = host
    service.receipts['backend'] = {'stage': 'FAILED_REQUIRES_REVIEW', 'reason': 'BACKEND_TARGET_CHANGED'}
    result = apply(plugin, 16, desired())
    assert result['status'] == 'Failed' and result['reasonCode'] == 'BACKEND_TARGET_CHANGED'
    assert world['started'] == []


def test_zram_reports_the_first_missing_host_precondition(host, monkeypatch):
    plugin, service, world = host
    world['unit'] = 'inactive'
    present = set(['/sys/kernel/mm/ksm/run', '/sys/kernel/mm/ksm/pages_to_scan', '/sys/kernel/mm/ksm/sleep_millisecs'])
    monkeypatch.setattr(module.os.path, 'exists', lambda path: path in present)
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(plugin, 'host_release_from_os_release', lambda text: 'h84r')
    monkeypatch.setattr(plugin, 'installed_reclaim_candidate', lambda release, kernel: None)
    # cgroup v1 without PSI or a loaded zram: the cgroup is what to fix first.
    capabilities = MemoryOptimizationPlugin.discover_capabilities(plugin)
    assert capabilities['zram'] is False and capabilities['zramReasonCode'] == 'UNSUPPORTED_CGROUP_MEMORY'
    present.update(['/sys/fs/cgroup/cgroup.controllers', '/sys/fs/cgroup/memory.reclaim'])
    assert MemoryOptimizationPlugin.discover_capabilities(plugin)['zramReasonCode'] == 'HOST_PSI_UNAVAILABLE'


def test_vm_bind_sets_the_instance_policy_and_revoke_changes_nothing(host):
    plugin, service, world = host
    request = {'body': json.dumps({'hostUuid': HOST, 'action': 'bind', 'resourceUuid': 'b' * 32,
                                   'expectedInstanceGeneration': 'g1', 'participation': 'deny',
                                   'operationUuid': 'c' * 32})}
    reply = json.loads(plugin.vm_efficiency(request))
    assert reply['status'] == 'Succeeded'
    assert service.calls[-2] == ('vm-policy', {'expected_instance_generation': 'g1', 'mode': 'deny',
                                              'cpu_rule': None, '_resource': 'b' * 32})
    revoke = {'body': json.dumps({'hostUuid': HOST, 'action': 'revoke', 'resourceUuid': 'b' * 32})}
    assert json.loads(plugin.vm_efficiency(revoke))['status'] == 'Succeeded'
    assert service.calls[-1] == ('vm-policy-state', {'_resource': 'b' * 32})
    assert len(service.calls) == 2


def _reboot_reclaim_host(plugin, service, world, monkeypatch, capacity, receipt_device='/dev/vdb',
                         serial='disk-a', recorded='disk-a'):
    world['unit'] = 'failed'
    monkeypatch.setattr(plugin, '_drain_check', lambda: {
        'error': 'BACKEND_RECLAIM_REQUIRED_AFTER_REBOOT: earlier boot claim'})
    monkeypatch.setattr(plugin, '_read_service_config', lambda: {'backend': {'device': '/dev/vdb'}})
    if recorded:
        # Recorded while the disk was this Host's active backend in the earlier boot.
        plugin._remember_backend_identity({'candidates': [{'device': '/dev/vdb', 'state': 'ACTIVE', 'stableIdentity': {
            'serial': recorded, 'wwn': '', 'byIdPath': '/dev/disk/by-id/virtio-' + recorded}}]})
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: '6315d9da-c7cd-4b6c-9d80-c58617c8eabb')
    service.receipts['backend'] = {'stage': 'APPLIED', 'request_id': 'backend-3-x',
                                   'candidate_id': 'candidate:' + 'c' * 64,
                                   'target_identity': {'canonical_device': receipt_device, 'capacity_bytes': 1 << 30}}
    scans = world.setdefault('scans', [])
    monkeypatch.setattr(plugin, '_writeback_inventory', lambda host_uuid: scans.append(host_uuid) or {
        'canPrepare': True, 'candidates': [{'identity': 'candidate:' + 'd' * 64, 'device': '/dev/vdb',
                                            'state': 'NEEDS_OFFLINE_PREPARATION', 'capacityBytes': capacity, 'stableIdentity': {
                                                'serial': serial, 'wwn': '',
                                                'byIdPath': '/dev/disk/by-id/virtio-' + serial}}]})
    built = []
    monkeypatch.setattr(module, 'build_backend_maintenance_request',
                        lambda inventory, preparation: built.append(preparation) or {'request_id': preparation['requestId']})
    return built


def test_a_stopped_service_is_not_started_while_an_executor_holds_its_state(host):
    plugin, service, world = host
    world['unit'] = 'failed'
    # A preparation executor finishing after a reboot still holds the service state.
    world['drained'] = {'error': 'state directory already in use: resource temporarily unavailable'}
    result = apply(plugin, 7, desired())
    assert result['status'] == 'Converging' and result['reasonCode'] == 'HOST_OPERATION_IN_PROGRESS', result
    assert world['unit'] == 'failed'
    world['drained'] = None
    apply(plugin, 7, desired())
    assert world['unit'] == 'active'


def test_a_rebooted_writeback_host_prepares_the_same_disk_again(host, monkeypatch):
    plugin, service, world = host
    built = _reboot_reclaim_host(plugin, service, world, monkeypatch, 1 << 30)
    result = apply(plugin, 7, desired(writeback=True))
    assert result['status'] == 'Converging' and result['reasonCode'] == 'BACKEND_PREPARING', result
    assert built[0]['candidateId'] == 'candidate:' + 'd' * 64
    assert built[0]['backendCapacityBytes'] == 1 << 30
    assert built[0]['expectedPoolGeneration'] == 'none'
    assert built[0]['expectedHostBootId'] == '6315d9da-c7cd-4b6c-9d80-c58617c8eabb'
    assert world['started'][0][:2] == ('zstack-memory-backend-backend-7-6315d9dac7cd4b6c',
                                       '--prepare-backend-maintenance')
    # A resend while the executor runs does not scan the disks again.
    assert apply(plugin, 7, desired(writeback=True))['reasonCode'] == 'BACKEND_PREPARING'
    assert len(world['scans']) == 1


def test_a_preparation_left_unfinished_by_a_reboot_is_prepared_again(host, monkeypatch):
    plugin, service, world = host
    built = _reboot_reclaim_host(plugin, service, world, monkeypatch, 1 << 30)
    service.receipts['backend'].update(stage='AWAITING_SERVICE_READBACK', request_id='backend-6-x',
                                       host_boot_id='ee9d1165-923d-46e3-9077-a94bbbd11dfb')
    result = apply(plugin, 7, desired(writeback=True))
    assert result['reasonCode'] == 'BACKEND_PREPARING', result
    assert built and world['started'][0][1] == '--prepare-backend-maintenance'


def test_observing_a_stopped_service_waits_for_no_running_apply(host):
    plugin, service, world = host
    world['drained'] = {'state': MemoryOptimizationPlugin.DRAINED}
    assert plugin._observed_control('inactive', {}) == 'drained'
    with plugin._host_lock():
        # The service's state lock may be in use by the apply; report, do not collide.
        world['drained'] = None
        assert plugin._observed_control('inactive', {}) == 'unknown'


@pytest.mark.parametrize('receipt_boot, can_prepare', [('boot', False), ('earlier-boot', True)])
def test_only_an_unfinished_preparation_of_this_boot_blocks_a_new_one(host, monkeypatch, receipt_boot, can_prepare):
    plugin, service, world = host
    world['unit'] = 'failed'
    world['drained'] = {'error': 'BACKEND_RECLAIM_REQUIRED_AFTER_REBOOT'}
    service.receipts['backend'] = {'stage': 'AWAITING_SERVICE_READBACK', 'host_boot_id': receipt_boot}
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: None)
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'candidates': [{'device': '/dev/vdb', 'state': 'NEEDS_OFFLINE_PREPARATION'}]})
    inventory = plugin._writeback_inventory(HOST)
    assert inventory['canPrepare'] is can_prepare, inventory['preparationReasons']


@pytest.mark.parametrize('drained, record, generation', [({'error': 'state directory already in use'}, 'kept', None),
                                                         (None, 'kept', None),
                                                         ({'error': 'state directory already in use'}, 'unreadable', None),
                                                         ({'error': 'state directory already in use'}, 'relative', None),
                                                         ({'error': 'state directory already in use'}, 'absent', 'none')])
def test_a_stopped_service_has_no_pool_only_when_none_is_recorded(host, tmp_path, monkeypatch,
                                                                  drained, record, generation):
    plugin, service, world = host
    world['unit'], world['drained'] = 'inactive', drained
    state = tmp_path / 'state'
    state.mkdir()
    if record == 'kept':
        (state / 'stock-pool.json').write_text(json.dumps({'generation': POOL}))
    if record == 'unreadable':
        def lstat(path, real=os.lstat):
            if str(path).startswith(str(state)):
                raise OSError(errno.EACCES, 'Permission denied', path)
            return real(path)
        monkeypatch.setattr(module.os, 'lstat', lstat)
    state_dir = 'memory-state' if record == 'relative' else str(state)
    (tmp_path / 'config.json').write_text(json.dumps({'managed': True, 'mode': 'reclaim', 'resource_authorized': True,
                                                      'device': '/dev/zram0', 'state_dir': state_dir}))
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: None)
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'candidates': [{'device': '/dev/vdb', 'state': 'NEEDS_OFFLINE_PREPARATION'}]})
    inventory = plugin._writeback_inventory(HOST)
    assert inventory['poolGeneration'] == generation, inventory
    assert inventory['canPrepare'] is (generation == 'none'), inventory['preparationReasons']


def test_only_a_possible_candidate_is_probed_for_signatures():
    from kvmagent.plugins import memory_writeback_backends as backends
    volumes = [{'name': '/dev/mapper/vg-lv%d' % i, 'kname': 'dm-%d' % i, 'type': 'lvm', 'size': 1 << 30,
                'maj:min': '253:%d' % i} for i in range(300)]
    lsblk = {'blockdevices': [{'name': '/dev/vdb', 'kname': 'vdb', 'type': 'disk', 'size': 1 << 30,
                               'maj:min': '252:16', 'serial': 'disk-a', 'tran': 'virtio',
                               'children': [{'name': '/dev/vdb1', 'kname': 'vdb1', 'type': 'part',
                                             'maj:min': '252:17', 'size': 1 << 29}]}] + volumes}
    probed = []

    def runner(argv, timeout=5):
        if argv[0] == 'lsblk':
            return {'returncode': 0, 'stdout': json.dumps(lsblk), 'stderr': ''}
        if argv[0] == 'blkid':
            probed.append(argv[-1])
        return {'returncode': 2, 'stdout': '', 'stderr': ''}

    class Filesystem(object):
        def read(self, path):
            if path == '/proc/sys/kernel/random/boot_id':
                return 'boot'
            raise IOError(2, path)

        def exists(self, path):
            return False

        def listdir(self, path):
            if path == '/dev/disk/by-id':
                return ['virtio-disk-a-part1']
            raise OSError(2, path)

        def realpath(self, path):
            return '/dev/vdb1' if path == '/dev/disk/by-id/virtio-disk-a-part1' else path

        def stat(self, path):
            raise OSError(2, path)

        lstat = stat
    result = backends.probe_writeback_backends(HOST, runner=runner, filesystem=Filesystem())
    partition = next(c for c in result['candidates'] if c['device'] == '/dev/vdb1')
    assert partition['byIdPath'] == '/dev/disk/by-id/virtio-disk-a-part1'
    # 300 logical volumes are ineligible anyway; a signature probe each would outlast the MN call.
    assert len([path for path in probed if path.startswith('/dev/mapper/')]) == 0


def test_the_active_backend_disk_is_recorded_by_its_persistent_identity(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: '/dev/vdb')
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'candidates': [{'device': '/dev/vdb', 'state': 'ACTIVE', 'stableIdentity': {
            'serial': 'disk-a', 'wwn': '', 'byIdPath': '/dev/disk/by-id/virtio-disk-a', 'rdev': 64784}}]})
    plugin._writeback_inventory(HOST)
    assert plugin._backend_identity() == {'device': '/dev/vdb', 'serial': 'disk-a', 'wwn': '',
                                          'byIdPath': '/dev/disk/by-id/virtio-disk-a'}


def test_an_identity_that_cannot_be_recorded_is_a_reason_of_the_inventory(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: '/dev/vdb')
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'reasons': [], 'candidates': [{'device': '/dev/vdb', 'state': 'ACTIVE', 'stableIdentity': {
            'serial': 'disk-a', 'wwn': '', 'byIdPath': '/dev/disk/by-id/virtio-disk-a'}}]})

    def full(*args, **kwargs):
        raise OSError(28, 'No space left on device')
    monkeypatch.setattr(plugin, '_atomic_write', full)
    inventory = plugin._writeback_inventory(HOST)
    # The query still answers; a reboot cannot reclaim the disk without the record.
    assert inventory['candidates'][0]['state'] == 'ACTIVE'
    assert 'BACKEND_IDENTITY_NOT_RECORDED' in inventory['reasons']
    assert plugin._backend_identity() == {}


@pytest.mark.parametrize('configured, serial', [(None, 'disk-a'), ('/dev/vdc', 'disk-a'), ('/dev/vdb', '')])
def test_an_active_disk_left_without_its_identity_is_a_reason_of_the_inventory(host, monkeypatch, configured, serial):
    plugin, service, world = host
    # The configured device cannot be read or is another disk, or the disk has no persistent identifier.
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: configured)
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'reasons': [], 'candidates': [{'device': '/dev/vdb', 'state': 'ACTIVE', 'stableIdentity': {
            'serial': serial, 'wwn': '', 'byIdPath': ''}}]})
    inventory = plugin._writeback_inventory(HOST)
    assert 'BACKEND_IDENTITY_NOT_RECORDED' in inventory['reasons']
    assert plugin._backend_identity() == {}


@pytest.mark.parametrize('serial, recorded', [('disk-b', 'disk-a'), ('disk-a', None)])
def test_a_rebooted_host_resets_only_the_disk_it_recorded(host, monkeypatch, serial, recorded):
    plugin, service, world = host
    # Another blank disk of the same size under the same name, or a disk never seen as the backend.
    _reboot_reclaim_host(plugin, service, world, monkeypatch, 1 << 30, serial=serial, recorded=recorded)
    result = apply(plugin, 7, desired(writeback=True))
    assert result['status'] == 'Failed' and result['reasonCode'] == 'REBOOT_BACKEND_NOT_ELIGIBLE'
    assert world['started'] == []


def test_a_rebooted_host_with_unmanaged_writeback_prepares_its_disk_again(host, monkeypatch):
    plugin, service, world = host
    _reboot_reclaim_host(plugin, service, world, monkeypatch, 1 << 30)
    assert apply(plugin, 7, desired(writeback=None))['reasonCode'] == 'BACKEND_PREPARING'
    assert world['started'][0][1] == '--prepare-backend-maintenance'


def test_a_rebooted_host_without_writeback_runs_without_its_backend(host, tmp_path, monkeypatch):
    plugin, service, world = host
    _reboot_reclaim_host(plugin, service, world, monkeypatch, 1 << 30)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'managed': True, 'mode': 'reclaim', 'resource_authorized': True,
                                  'device': '/dev/zram0', 'backend': {'device': '/dev/vdb'}}))
    monkeypatch.setattr(plugin, '_read_service_config', MemoryOptimizationPlugin._read_service_config.__get__(plugin))
    apply(plugin, 7, desired(writeback=False))
    assert 'backend' not in json.loads(config.read_text())
    assert world['started'] == [] and world['unit'] == 'active'
    assert plugin._backend_identity() == {}


@pytest.mark.parametrize('capacity, receipt_device', [(2 << 30, '/dev/vdb'), (1 << 30, '/dev/vdc')])
def test_a_rebooted_host_whose_disk_changed_is_not_prepared(host, monkeypatch, capacity, receipt_device):
    plugin, service, world = host
    _reboot_reclaim_host(plugin, service, world, monkeypatch, capacity, receipt_device)
    result = apply(plugin, 7, desired(writeback=True))
    assert result['status'] == 'Failed' and result['reasonCode'] == 'REBOOT_BACKEND_NOT_ELIGIBLE'
    assert world['started'] == []


def test_writeback_preparation_derives_its_request_and_completes_on_resend(host, monkeypatch):
    plugin, service, world = host
    world['unit'] = 'inactive'
    world['drained'] = {'state': MemoryOptimizationPlugin.DRAINED, 'pool_generation': POOL}
    monkeypatch.setattr(plugin, '_writeback_inventory', lambda host_uuid: {
        'canPrepare': True, 'poolGeneration': POOL,
        'candidates': [{'device': '/dev/vdb', 'state': 'PREPARED', 'resourceUuid': 'f' * 32}]})
    built = []
    monkeypatch.setattr(module, 'build_backend_maintenance_request',
                        lambda inventory, preparation: built.append(preparation) or {'request_id': preparation['requestId']})
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 20, 'candidateId': 'candidate:' + 'd' * 64,
               'operationUuid': OPERATION,
               'expectedHostBootId': 'boot', 'expectedPoolGeneration': POOL, 'backendCapacityBytes': 1 << 30,
               'resetConfirmed': True}
    def prepare():
        return json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))

    first = prepare()
    assert first['status'] == 'Converging' and first['reasonCode'] == 'BACKEND_PREPARING'
    request_id = 'backend-20-' + OPERATION[:16]
    assert built[0]['requestId'] == request_id
    assert world['started'][0][:2] == ('zstack-memory-backend-' + request_id, '--prepare-backend-maintenance')
    assert prepare()['reasonCode'] == 'BACKEND_PREPARING'
    service.receipts['backend'] = applied_backend_receipt(request_id)
    done = prepare()
    assert done['status'] == 'Succeeded' and done['state']['maintenance']['backend_resource_uuid'] == 'f' * 32
    assert len(world['started']) == 1


def test_an_apply_request_that_is_not_json_is_answered_as_failed(host):
    plugin, service, world = host
    result = json.loads(plugin.apply_request({module.http.REQUEST_BODY: '{broken'}))
    assert result['success'] is False, result


def applied_backend_receipt(request_id, **changes):
    receipt = {'stage': 'APPLIED', 'request_id': request_id, 'pool_generation': POOL,
               'backend_resource_uuid': 'f' * 32, 'candidate_id': 'candidate:' + 'd' * 64, 'host_boot_id': 'boot',
               'target_identity': {'canonical_device': '/dev/vdb', 'capacity_bytes': 1 << 30}}
    receipt.update(changes)
    return receipt


@pytest.mark.parametrize('changes, request_changes', [
    ({'host_boot_id': 'earlier-boot'}, {}),
    ({'target_identity': {'canonical_device': '/dev/vdb', 'capacity_bytes': 2 << 30}}, {}),
    ({'candidate_id': 'candidate:' + 'e' * 48 + 'd' * 16}, {}),
    ({'pool_generation': 'e' * 64}, {}),
    ({}, {'resetConfirmed': False})])
def test_an_applied_preparation_answers_only_the_same_request(host, changes, request_changes):
    plugin, service, world = host
    request_id = 'backend-20-' + OPERATION[:16]
    service.receipts['backend'] = applied_backend_receipt(request_id, **changes)
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 20, 'candidateId': 'candidate:' + 'd' * 64,
               'operationUuid': OPERATION,
               'expectedHostBootId': 'boot', 'expectedPoolGeneration': POOL, 'backendCapacityBytes': 1 << 30,
               'resetConfirmed': True}
    command.update(request_changes)
    # The same request id on another boot, disk, capacity or pool, or unconfirmed, is not this request's success.
    result = json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))
    assert result['status'] == 'Failed' and result['reasonCode'] == 'BACKEND_MAINTENANCE_REQUEST_CONFLICT', result
    assert world['started'] == []


def test_an_applied_preparation_without_the_boot_it_was_made_on_is_refused(host):
    plugin, service, world = host
    service.receipts['backend'] = applied_backend_receipt('backend-20-' + OPERATION[:16])
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 20, 'candidateId': 'candidate:' + 'd' * 64,
               'operationUuid': OPERATION, 'expectedPoolGeneration': POOL, 'backendCapacityBytes': 1 << 30,
               'resetConfirmed': True}
    # The management node always names the boot; a request without it is not completed with the current one.
    result = json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))
    assert result['status'] == 'Failed' and result['reasonCode'] == 'BACKEND_MAINTENANCE_CONFIRMATION_REQUIRED', result
    assert world['started'] == []


def test_a_new_preparation_of_the_same_disk_is_its_own_request(host, monkeypatch):
    plugin, service, world = host
    # An earlier preparation of the disk succeeded under the same generation, with a pool since released.
    service.receipts['backend'] = applied_backend_receipt('backend-20-' + 'f' * 16)
    world['unit'] = 'inactive'
    monkeypatch.setattr(plugin, '_writeback_inventory', lambda host_uuid: {
        'canPrepare': True, 'poolGeneration': 'none',
        'candidates': [{'identity': 'candidate:' + 'd' * 64, 'device': '/dev/vdb',
                        'state': 'NEEDS_OFFLINE_PREPARATION'}]})
    monkeypatch.setattr(module, 'build_backend_maintenance_request',
                        lambda inventory, preparation: {'request_id': preparation['requestId']})
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 20, 'candidateId': 'candidate:' + 'd' * 64,
               'operationUuid': OPERATION, 'expectedHostBootId': 'boot', 'expectedPoolGeneration': 'none',
               'backendCapacityBytes': 1 << 30, 'resetConfirmed': True}
    result = json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))
    assert result['status'] == 'Converging' and result['reasonCode'] == 'BACKEND_PREPARING', result
    assert world['started'][0][0] == 'zstack-memory-backend-backend-20-' + OPERATION[:16]


def test_a_preparation_without_its_operation_is_refused(host):
    plugin, service, world = host
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 20, 'candidateId': 'candidate:' + 'd' * 64,
               'expectedHostBootId': 'boot', 'expectedPoolGeneration': 'none', 'backendCapacityBytes': 1 << 30,
               'resetConfirmed': True}
    result = json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))
    assert result['status'] == 'Failed' and result['reasonCode'] == 'INVALID_OPERATION_UUID', result
    assert world['started'] == []


@pytest.mark.parametrize('candidates', [[], [{'device': '/dev/vdb', 'state': 'DISCONNECTED'}],
                                        # The same disk prepared again by another maintenance is another resource.
                                        [{'device': '/dev/vdb', 'state': 'PREPARED', 'resourceUuid': 'e' * 32}]])
def test_an_applied_preparation_whose_disk_is_no_longer_the_backend_fails(host, monkeypatch, candidates):
    plugin, service, world = host
    request_id = 'backend-20-' + OPERATION[:16]
    service.receipts['backend'] = applied_backend_receipt(request_id)
    monkeypatch.setattr(plugin, '_writeback_inventory', lambda host_uuid: {'candidates': candidates})
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 20, 'candidateId': 'candidate:' + 'd' * 64,
               'operationUuid': OPERATION,
               'expectedHostBootId': 'boot', 'expectedPoolGeneration': POOL, 'backendCapacityBytes': 1 << 30,
               'resetConfirmed': True}
    # The earlier success does not hold once its disk is gone or no longer prepared.
    result = json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))
    assert result['status'] == 'Failed' and result['reasonCode'] == 'BACKEND_NOT_CURRENT', result
    assert world['started'] == []


def test_a_host_without_a_pool_stops_its_service_to_prepare_a_backend(host, monkeypatch):
    plugin, service, world = host
    service.pool, service.efficiency = None, True
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: None)
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'candidates': [{'identity': 'candidate:' + 'd' * 64, 'device': '/dev/vdb',
                        'state': 'NEEDS_OFFLINE_PREPARATION'}]})
    monkeypatch.setattr(module, 'build_backend_maintenance_request',
                        lambda inventory, preparation: {'request_id': preparation['requestId']})
    inventory = plugin._writeback_inventory(HOST)
    assert inventory['canPrepare'] is True and inventory['poolGeneration'] == 'none', inventory
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 4, 'candidateId': 'candidate:' + 'd' * 64,
               'operationUuid': OPERATION,
               'expectedHostBootId': 'boot', 'expectedPoolGeneration': 'none', 'backendCapacityBytes': 1 << 30,
               'resetConfirmed': True}
    result = json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))
    assert result['status'] == 'Converging' and result['reasonCode'] == 'BACKEND_PREPARING', result
    # Stopped like a drain: paused, and the host policy off as the readback requires.
    assert world['unit'] == 'inactive' and service.paused is True and service.efficiency is False
    assert world['started'][0][1] == '--prepare-backend-maintenance'


@pytest.mark.parametrize('native, zram_reset, reason', [
    # The released pool's device keeps its size until a reboot; the first use refuses it.
    (None, False, 'BACKEND_MAINTENANCE_FIRST_USE_NOT_EMPTY'),
    # The prepared disk came back under another device in this boot.
    ({'error': 'BACKEND_NOT_READY: BACKEND_IDENTITY_CHANGED_REQUIRES_MAINTENANCE'}, True,
     'PREPARED_BACKEND_IDENTITY_MISMATCH')])
def test_a_stopped_host_without_a_pool_says_why_it_cannot_prepare(host, monkeypatch, native, zram_reset, reason):
    plugin, service, world = host
    world.update({'unit': 'inactive', 'drained': native, 'zram_reset': zram_reset})
    monkeypatch.setattr(plugin, '_no_recorded_pool', lambda: True)
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: None)
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'candidates': [{'identity': 'candidate:' + 'd' * 64, 'device': '/dev/vdb',
                        'state': 'NEEDS_OFFLINE_PREPARATION'}]})
    inventory = plugin._writeback_inventory(HOST)
    assert inventory['poolGeneration'] == 'none' and inventory['canPrepare'] is False, inventory
    assert inventory['preparationReasons'] == [reason], inventory


@pytest.mark.parametrize('disksize, mm_stat, backing, swaps, reset', [
    ('0', '0 0 0 0 0 0 0 0 0', 'none', '', True),
    ('2978701312', '4096 74 12288 0 12288 0 0 0 0', 'none', '', False),
    ('0', '0 0 0 1073741824 0 0 0 0 0', 'none', '', False),
    ('0', '0 0 0 0 0 0 0 0 0', '/dev/vdb', '', False),
    ('0', '0 0 0 0 0 0 0 0 0', 'none', '/dev/zram0 partition 0 0 100\n', False)])
def test_the_zram_device_is_reset_only_without_size_limit_backing_or_swap(host, tmp_path, monkeypatch,
                                                                          disksize, mm_stat, backing, swaps, reset):
    plugin, service, world = host
    block = tmp_path / 'block' / 'zram0'
    block.mkdir(parents=True)
    (block / 'disksize').write_text(disksize + '\n')
    (block / 'mm_stat').write_text(mm_stat + '\n')
    (block / 'backing_dev').write_text(backing + '\n')
    (tmp_path / 'swaps').write_text('Filename\tType\tSize\tUsed\tPriority\n' + swaps)
    monkeypatch.setattr(plugin, 'SYS_BLOCK_PATH', str(tmp_path / 'block'))
    monkeypatch.setattr(plugin, 'PROC_SWAPS_PATH', str(tmp_path / 'swaps'))
    assert MemoryOptimizationPlugin._zram_device_reset(plugin) is reset


def test_an_earlier_agent_journal_is_moved_aside_on_start(tmp_path):
    operations = tmp_path / 'operations'
    (operations / 'drain').mkdir(parents=True)
    (operations / ('e' * 32 + '.json')).write_text('{}')
    (operations / 'active-control').write_text('e' * 32)
    (operations / 'applied-generation').write_text('4\n')
    (operations / '.host-control.flock').write_text('')
    plugin = MemoryOptimizationPlugin(service_call=FakeService())
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operations)})
    plugin._retire_legacy_records()
    assert sorted(os.listdir(str(operations))) == ['.host-control.flock', 'applied-generation']
    legacy = [path for path in os.listdir(str(tmp_path)) if path.startswith('operations-legacy-')]
    assert len(legacy) == 1
    assert sorted(os.listdir(str(tmp_path / legacy[0]))) == sorted(['drain', 'e' * 32 + '.json', 'active-control'])
    assert plugin._applied_generation() == 4


def test_a_journal_that_cannot_be_moved_aside_does_not_stop_the_agent(tmp_path, monkeypatch):
    operations = tmp_path / 'operations'
    operations.mkdir()
    (operations / 'active-control').write_text('e' * 32)
    plugin = MemoryOptimizationPlugin(service_call=FakeService())
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operations)})

    def refuse(source, target):
        raise OSError(30, 'Read-only file system')
    monkeypatch.setattr(module.shutil, 'move', refuse)
    plugin._retire_legacy_records()


@pytest.mark.parametrize('state, can_back, prepared', [
    ('NEEDS_OFFLINE_PREPARATION', True, False), ('PREPARED', True, True), ('ACTIVE', True, True),
    ('INELIGIBLE', False, False), ('DISCONNECTED', False, False), ('IDENTITY_MISMATCH', False, False)])
def test_a_candidate_state_alone_decides_whether_it_backs_writeback(state, can_back, prepared):
    candidate = {'device': '/dev/vdb', 'state': state}
    assert backends.eligible(candidate) is can_back
    assert backends.writeback_ready(candidate) is prepared
    if state == 'NEEDS_OFFLINE_PREPARATION':
        return
    inventory = {'observedAt': time.time(), 'candidates': [dict(candidate, identity='candidate:x', type='block')]}
    with pytest.raises(ValueError) as rejected:
        maintenance._canonical_candidate(inventory, 'candidate:x')
    assert str(rejected.value) == 'WRITEBACK_CANDIDATE_NOT_PREPARABLE'


def test_a_unit_systemd_cannot_report_is_unknown_and_logged(host, monkeypatch):
    plugin, service, world = host
    logger = Mock()
    monkeypatch.setattr(module, 'logger', logger)

    def timeout(argv, seconds):
        raise RuntimeError('BOUNDED_COMMAND_TIMEOUT')
    monkeypatch.setattr(plugin, '_bounded_command_output', staticmethod(timeout))
    assert MemoryOptimizationPlugin._service_unit_state(plugin) == 'unknown'
    assert 'BOUNDED_COMMAND_TIMEOUT' in logger.error.call_args[0][0]


def test_libvirt_that_cannot_be_reached_leaves_the_vm_inventory_incomplete(host, monkeypatch):
    plugin, service, world = host
    logger = Mock()
    monkeypatch.setattr(module, 'logger', logger)

    def refused(uri):
        raise Exception('Failed to connect socket to /var/run/libvirt/libvirt-sock-ro')
    monkeypatch.setitem(sys.modules, 'libvirt', SimpleNamespace(openReadOnly=refused))
    assert plugin._complete_vm_inventory({}) == ({}, False)
    assert 'libvirt-sock-ro' in logger.error.call_args[0][0]


def test_an_unreadable_backend_service_is_reported_and_logged_but_a_bug_is_not_hidden(host, monkeypatch):
    plugin, service, world = host
    logger = Mock()
    monkeypatch.setattr(module, 'logger', logger)
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: None)
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'candidates': [{'device': '/dev/vdb', 'state': 'NEEDS_OFFLINE_PREPARATION'}]})
    failure = [IOError('memory service socket closed')]

    def call(action, payload):
        if action == 'backend-view':
            raise failure[0]
        return service(action, payload)
    monkeypatch.setattr(plugin, 'service_call', call)
    inventory = plugin._writeback_inventory(HOST)
    assert 'BACKEND_SERVICE_OBSERVATION_UNAVAILABLE' in inventory['reasons']
    assert 'socket closed' in logger.error.call_args[0][0]

    failure[0] = KeyError('a bug in the agent')
    with pytest.raises(KeyError):
        plugin._writeback_inventory(HOST)


def test_a_service_switch_is_named_not_a_bare_boolean(host):
    plugin, service, world = host
    cpu = {'efficiency_enabled': True}
    plugin._set_efficiency(cpu, module.EfficiencyMode.DISABLED)
    assert cpu['efficiency_enabled'] is False and service.efficiency is False
    calls = len(service.calls)
    for wrong in (True, False, 'enabled', 'disabled', module.WritebackMode.ENABLED):
        with pytest.raises(ValueError):
            plugin._set_efficiency(cpu, wrong)
    for wrong in (True, False, 'enabled', 'disabled', module.EfficiencyMode.ENABLED):
        with pytest.raises(ValueError):
            plugin._set_writeback(wrong)
    assert len(service.calls) == calls, 'a refused switch changes nothing on the service'
    assert cpu['efficiency_enabled'] is False
class FakeSwapDisks(object):
    def __init__(self, refuse=None):
        self.calls, self.refuse = [], refuse

    def inventory(self):
        self.calls.append(('inventory',))
        return {'status': 'NOT_CONFIGURED'}

    def prepare(self, candidate_id, overwrite):
        self.calls.append(('prepare', candidate_id, overwrite))
        if self.refuse:
            raise memory_swap_disks.Rejected(self.refuse, {'devices': ['/dev/zram0']})
        return {'status': 'ACTIVE'}

    def disable(self):
        self.calls.append(('disable',))
        return {'status': 'NOT_CONFIGURED'}


def swap_disk_request(plugin, **command):
    command.setdefault('hostUuid', HOST)
    return json.loads(plugin.swap_disks({module.http.REQUEST_BODY: json.dumps(command)}))


@pytest.mark.parametrize('command,call,status', [
    ({}, ('inventory',), 'NOT_CONFIGURED'),
    ({'action': 'prepare', 'candidateId': 'candidate:x', 'overwrite': True}, ('prepare', 'candidate:x', True), 'ACTIVE'),
    ({'action': 'prepare', 'candidateId': 'candidate:x', 'overwrite': 'yes'}, ('prepare', 'candidate:x', False), 'ACTIVE'),
    ({'action': 'disable'}, ('disable',), 'NOT_CONFIGURED'),
])
def test_swap_disk_requests_reach_the_swap_disk_with_the_zram_service_stopped(host, monkeypatch, command, call, status):
    plugin, _, world = host
    world['unit'] = 'inactive'
    disks = FakeSwapDisks()
    monkeypatch.setattr(plugin, '_swap_disk_manager', lambda host_uuid: disks)
    result = swap_disk_request(plugin, **command)
    assert result['success'] is True and result['state']['status'] == status and disks.calls == [call]
    if not command:
        assert 'swapDevices' not in result['state']


@pytest.mark.parametrize('swap_devices', [None, '', '/dev/nvme0n1p1|partition|1024|-2'])
def test_swap_disk_mutations_report_the_latest_swap_devices(host, monkeypatch, swap_devices):
    host_plugin = SimpleNamespace(get_swap_devices=lambda: swap_devices)
    monkeypatch.setitem(sys.modules, 'kvmagent.plugins.host_plugin', host_plugin)
    plugin, _, world = host
    world['unit'] = 'inactive'
    disks = FakeSwapDisks()
    monkeypatch.setattr(plugin, '_swap_disk_manager', lambda host_uuid: disks)

    result = swap_disk_request(plugin, action='disable')

    assert result['success'] is True and result['status'] == 'Succeeded'
    assert result['state'].get('swapDevices') == swap_devices
    assert disks.calls == [('disable',)]


def test_swap_device_collection_failure_does_not_fail_a_completed_disk_operation(host, monkeypatch):
    host_plugin = SimpleNamespace(get_swap_devices=lambda: (_ for _ in ()).throw(IOError('proc swaps unavailable')))
    monkeypatch.setitem(sys.modules, 'kvmagent.plugins.host_plugin', host_plugin)
    plugin, _, world = host
    world['unit'] = 'inactive'
    monkeypatch.setattr(plugin, '_swap_disk_manager', lambda host_uuid: FakeSwapDisks())

    result = swap_disk_request(plugin, action='disable')

    assert result['success'] is True and result['status'] == 'Succeeded'
    assert result['state'].get('swapDevices') is None


def test_a_swap_disk_is_not_prepared_while_the_zram_service_runs(host, monkeypatch):
    plugin, _, world = host
    disks = FakeSwapDisks()
    monkeypatch.setattr(plugin, '_swap_disk_manager', lambda host_uuid: disks)
    result = swap_disk_request(plugin, action='prepare', candidateId='candidate:x')
    assert result['success'] is False and result['reasonCode'] == 'MEMORY_SERVICE_NOT_STOPPED' and disks.calls == []


def test_a_refused_swap_disk_change_reports_its_reason_and_details(host, monkeypatch):
    plugin, _, world = host
    world['unit'] = 'failed'
    monkeypatch.setattr(plugin, '_swap_disk_manager', lambda host_uuid: FakeSwapDisks('OTHER_SWAP_ACTIVE'))
    result = swap_disk_request(plugin, action='prepare', candidateId='candidate:x')
    assert (result['success'], result['reasonCode'], result['details']) == (False, 'OTHER_SWAP_ACTIVE', {'devices': ['/dev/zram0']})


def test_a_swap_disk_request_for_another_host_or_action_is_refused(host, monkeypatch):
    plugin, _, _ = host
    disks = FakeSwapDisks()
    monkeypatch.setattr(plugin, '_swap_disk_manager', lambda host_uuid: disks)
    assert swap_disk_request(plugin, hostUuid='f' * 32)['reasonCode'] == 'HOST_IDENTITY_UNKNOWN'
    assert swap_disk_request(plugin, action='format')['reasonCode'] == 'INVALID_SWAP_DISK_ACTION'
    assert disks.calls == []


@pytest.mark.parametrize('backend,configured,unit,expected', [
    ('swap', False, 'active', 'SWAP_DISK_NOT_CONFIGURED'),
    ('swap', True, 'unknown', 'MEMORY_SERVICE_NOT_STOPPED'),
    ('swap', True, 'inactive', 'Succeeded'),
    ('zram', True, 'inactive', 'SWAP_DISK_ALREADY_CONFIGURED'),
])
def test_changing_the_backend_preserves_the_previous_disk(host, monkeypatch, backend, configured, unit, expected):
    plugin, service, world = host
    world['unit'] = unit
    disks = FakeSwapDisks()
    disks.current = lambda: {'reasons': []} if configured else None
    def restore():
        if configured:
            disks.calls.append(('restore',))
        return configured
    disks.restore = restore
    monkeypatch.setattr(plugin, '_swap_disk_manager', lambda host_uuid: disks)
    want = desired(zram=None)
    want['reclaim'] = {'backend': backend}
    reply = apply(plugin, 1, want)
    assert reply.get('reasonCode', reply['status']) == expected
    assert disks.calls == ([('restore',)] if expected == 'Succeeded' else [])
    assert service.actions() == []


@pytest.mark.parametrize('pool,recorded,reset,maintenance,reasons,expected', [
    (None, False, True, False, [], 'Succeeded'),
    (POOL, False, True, False, [], 'MEMORY_SERVICE_NOT_STOPPED'),
    (None, True, True, False, [], 'MEMORY_SERVICE_NOT_STOPPED'),
    (None, False, False, False, [], 'MEMORY_SERVICE_NOT_STOPPED'),
    (None, False, True, True, [], 'HOST_OPERATION_IN_PROGRESS'),
    (None, False, True, False, ['SWAP_DISK_IDENTITY_MISMATCH'], 'SWAP_DISK_IDENTITY_MISMATCH'),
])
def test_swap_policy_after_boot_only_stops_an_empty_service(host, monkeypatch, pool, recorded, reset,
                                                          maintenance, reasons, expected):
    plugin, service, world = host
    service.pool, service.maintenance = pool, maintenance
    world['zram_reset'] = reset
    monkeypatch.setattr(plugin, '_no_recorded_pool', lambda: not recorded)
    disks = FakeSwapDisks()
    disks.current = lambda: {'reasons': reasons}
    restored = []
    def restore():
        restored.append(world['unit'])
        return True
    disks.restore = restore
    monkeypatch.setattr(plugin, '_swap_disk_manager', lambda host_uuid: disks)
    want = desired(zram=False)
    want['reclaim'] = {'backend': 'swap'}

    reply = apply(plugin, 1, want)

    assert reply.get('reasonCode', reply['status']) == expected
    if expected == 'Succeeded':
        assert restored == ['inactive']
        assert service.paused
    else:
        assert world['unit'] == 'active' and restored == [] and not service.paused


def test_the_swap_disk_record_is_kept_when_the_agent_starts(tmp_path):
    operations = tmp_path / 'operations'
    operations.mkdir()
    (operations / 'swap-disk').write_text('{}')
    plugin = MemoryOptimizationPlugin(service_call=FakeService())
    plugin.configure({'hostUuid': HOST, 'operationDir': str(operations)})
    plugin._retire_legacy_records()
    assert os.listdir(str(operations)) == ['swap-disk']


def test_the_swap_disk_keeps_the_configured_writeback_disk_reserved(host, tmp_path):
    plugin, _, _ = host
    config = json.loads((tmp_path / 'config.json').read_text())
    config['backend'] = {'device': '/dev/nvme0n1'}
    (tmp_path / 'config.json').write_text(json.dumps(config))
    disks = plugin._swap_disk_manager(HOST)
    assert disks.writeback_device == '/dev/nvme0n1'
    assert disks.record_path == str(tmp_path / 'operations' / 'swap-disk')




@pytest.fixture
def direct_host(host, tmp_path, monkeypatch):
    import libvirt
    import stat
    from zstacklib.utils import qmp
    plugin, service, world = host
    world.update(boot='boot', daemon=901, active=True,
                 xml="<capabilities><host><migration_features><live/>"
                     "<zstack_swap_direct version='1'/></migration_features></host></capabilities>",
                 parameters={'x-swap-direct-type': -1, 'x-swap-direct-zobj': True},
                 qemu_caps=[{'capability': 'x-swap-direct', 'state': False}])
    vm = '3' * 32
    emulator, running = tmp_path / 'qemu', tmp_path / 'running-qemu'
    emulator.write_bytes(b'prototype'); running.write_bytes(b'prototype')
    paths = {'/proc/902/exe': str(running)}
    for pid in (901, 902, 903):
        path = tmp_path / ('stat-%d' % pid)
        path.write_text('%d (worker (qemu)) ' % pid + ' '.join(['0'] * 19 + ['55']))
        paths['/proc/%d/stat' % pid] = str(path)
    original_open, original_stat, original_lstat = open, os.stat, os.lstat
    monkeypatch.setattr(module, 'open', lambda path, *args, **kwargs:
                        original_open(paths.get(str(path), path), *args, **kwargs), raising=False)
    monkeypatch.setattr(module.os, 'stat', lambda path, *args, **kwargs:
                        original_stat(paths.get(str(path), path), *args, **kwargs))
    monkeypatch.setattr(module.os, 'lstat', lambda path, *args, **kwargs:
                        SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=65024, st_ino=1)
                        if path == '/dev/zram0' else original_lstat(path, *args, **kwargs))
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(module.linux, 'get_libvirtd_pid', lambda: world['daemon'], raising=False)
    monkeypatch.setattr(module.linux, 'get_vm_pid', lambda name: 902 if name == vm else None, raising=False)
    monkeypatch.setattr(plugin, '_current_boot_id', lambda: world['boot'])
    domain = SimpleNamespace(UUIDString=lambda: vm, isActive=lambda: world['active'],
                             XMLDesc=lambda flags: '<domain><devices><emulator>%s</emulator></devices></domain>' % emulator)
    connection = SimpleNamespace(getCapabilities=Mock(side_effect=lambda: world['xml']),
                                 listAllDomains=lambda flags: [domain], close=Mock())
    monkeypatch.setattr(libvirt, 'openReadOnly', Mock(return_value=connection), raising=False)
    query = Mock(side_effect=lambda name, command, **kwargs:
                 world['parameters'] if command == 'query-migrate-parameters' else world['qemu_caps'])
    monkeypatch.setattr(qmp, 'execute_qmp_command', query, raising=False)
    kernel = Mock()
    monkeypatch.setattr(plugin, '_swap_direct_kernel_abi', kernel)
    monkeypatch.setattr(plugin, '_swap_direct_preflight', Mock(side_effect=AssertionError('no migration preflight')))
    monkeypatch.setattr(plugin, '_probe_swap_type', Mock(side_effect=AssertionError('no pageout probe')))
    state = {'bootId': 'boot', 'zram': {'poolGeneration': POOL,
                                      'pool': {'pool_generation': POOL, 'device': '/dev/zram0'}}}
    return plugin, service, world, state, connection, query, kernel, emulator, running, paths


def test_swap_direct_host_gate_is_cached_by_boot_pool_and_daemon_without_side_effects(direct_host):
    plugin, service, world, state, conn, query, kernel, _, _, paths = direct_host
    world['xml'] = '<capabilities><host><migration_features><live/></migration_features></host></capabilities>'
    before = list(service.calls)
    first = plugin._swap_direct_capability(state)
    cache = plugin._swap_direct_capability_cache
    assert first['supported'] is False
    assert first['reasonCode'] == 'SWAP_DIRECT_LIBVIRT_CAPABILITY_UNCONFIRMED'
    first['supported'] = True
    assert plugin._swap_direct_capability(state)['supported'] is False
    assert plugin._swap_direct_capability_cache is cache
    assert conn.getCapabilities.call_count == 1
    state['bootId'] = world['boot'] = 'new-boot'
    assert plugin._swap_direct_capability(state)['bootId'] == 'new-boot'
    assert conn.getCapabilities.call_count == 2
    state['zram']['poolGeneration'] = state['zram']['pool']['pool_generation'] = 'new-pool'
    assert plugin._swap_direct_capability(state)['poolGeneration'] == 'new-pool'
    assert conn.getCapabilities.call_count == 3
    world['daemon'] = 903
    plugin._swap_direct_capability(state)
    assert conn.getCapabilities.call_count == 4
    state['zram'].pop('poolGeneration')
    assert plugin._swap_direct_capability(state)['reasonCode'] == 'SWAP_DIRECT_MANAGED_POOL_REQUIRED'
    state.pop('bootId')
    assert plugin._swap_direct_capability(state)['reasonCode'] == 'SWAP_DIRECT_HOST_IDENTITY_UNKNOWN'
    assert service.calls == before
    query.assert_not_called(); kernel.assert_not_called()
    plugin._swap_direct_preflight.assert_not_called(); plugin._probe_swap_type.assert_not_called()


@pytest.mark.parametrize('change', ['boot', 'pool', 'daemon-pid', 'daemon-start', 'qemu-start', 'binary'])
def test_swap_direct_positive_cache_requires_current_process_and_binary_evidence(direct_host, change):
    plugin, service, world, state, conn, query, kernel, emulator, running, paths = direct_host
    first = plugin._swap_direct_capability(state)
    assert first['supported'] is True
    first['supported'] = False
    assert plugin._swap_direct_capability(state)['supported'] is True
    assert (conn.getCapabilities.call_count, kernel.call_count, query.call_count) == (1, 1, 2)
    if change == 'boot':
        state['bootId'] = world['boot'] = 'new-boot'
    elif change == 'pool':
        state['zram']['poolGeneration'] = state['zram']['pool']['pool_generation'] = 'new-pool'
    elif change == 'daemon-pid':
        world['daemon'] = 903
    elif change in ('daemon-start', 'qemu-start'):
        pid = 901 if change == 'daemon-start' else 902
        with open(paths['/proc/%d/stat' % pid], 'w') as stream:
            stream.write('%d (qemu) ' % pid + ' '.join(['0'] * 19 + ['66']))
    else:
        emulator.write_bytes(b'replaced prototype'); running.write_bytes(b'replaced prototype')
    assert plugin._swap_direct_capability(state)['supported'] is True
    xml_reads = 1 if change in ('qemu-start', 'binary') else 2
    assert (conn.getCapabilities.call_count, kernel.call_count, query.call_count) == (xml_reads, 2, 4)
    assert all(call.args[1] in ('query-migrate-parameters', 'query-migrate-capabilities') for call in query.call_args_list)
    assert service.calls == []


@pytest.mark.parametrize('xml', [
    '<capabilities><host><migration_features><zstack_swap_direct version="2"/></migration_features></host></capabilities>',
    '<capabilities><host><migration_features><zstack_swap_direct version="1"/><zstack_swap_direct version="1"/></migration_features></host></capabilities>',
    '<capabilities><host><zstack_swap_direct version="1"/></host></capabilities>',
    '<capabilities><host><migration_features><zstack_swap_direct/></migration_features></host></capabilities>',
    '<capabilities><host><migration_features><zstack_swap_direct version="1"><extra/></zstack_swap_direct></migration_features></host></capabilities>',
    '<capabilities><host/><host><migration_features><zstack_swap_direct version="1"/></migration_features></host></capabilities>',
    '<broken'])
def test_swap_direct_unproven_libvirt_never_reaches_kernel_or_qemu(direct_host, xml):
    plugin, _, world, state, _, query, kernel, _, _, _ = direct_host
    world['xml'] = xml
    result = plugin._swap_direct_capability(state)
    assert result['supported'] is False and result['reasonCode']
    kernel.assert_not_called(); query.assert_not_called()


def test_swap_direct_libvirt_failure_and_restart_are_not_permanent_negative_evidence(direct_host):
    plugin, _, world, state, conn, _, _, _, _, paths = direct_host
    conn.getCapabilities.side_effect = IOError('temporarily unavailable')
    assert plugin._swap_direct_capability(state)['supported'] is False
    assert plugin._swap_direct_capability_cache is None
    def restart():
        with open(paths['/proc/901/stat'], 'w') as stream:
            stream.write('901 (libvirtd) ' + ' '.join(['0'] * 19 + ['77']))
        return world['xml']
    conn.getCapabilities.side_effect = restart
    assert plugin._swap_direct_capability(state)['reasonCode'] == 'SWAP_DIRECT_LIBVIRT_IDENTITY_CHANGED'
    assert plugin._swap_direct_capability_cache is None
    conn.getCapabilities.side_effect = lambda: world['xml']
    assert plugin._swap_direct_capability(state)['supported'] is True


@pytest.mark.parametrize('missing', ['no-vm', 'qemu-protocol', 'executable-match', 'kernel'])
def test_swap_direct_marker_does_not_replace_kernel_or_running_qemu_proof(direct_host, missing):
    plugin, _, world, state, conn, query, kernel, emulator, running, paths = direct_host
    if missing == 'no-vm':
        world['active'] = False
    elif missing == 'qemu-protocol':
        world['parameters'] = {}
    elif missing == 'executable-match':
        emulator.write_bytes(b'unmatched installed binary')
    else:
        kernel.side_effect = OSError(errno.ENOTTY, 'unsupported')
    assert plugin._swap_direct_capability(state)['supported'] is False
    if missing == 'kernel':
        assert plugin._swap_direct_capability(state)['supported'] is False
        assert kernel.call_count == 1
        query.assert_not_called()
        state['zram']['poolGeneration'] = state['zram']['pool']['pool_generation'] = 'reloaded-pool'
        kernel.side_effect = None
    else:
        assert plugin._swap_direct_capability_cache is None
        # The same QEMUs and executables are not asked or hashed again at the next observation.
        asked = query.call_count
        assert plugin._swap_direct_capability(state)['reasonCode'] == 'SWAP_DIRECT_RUNNING_QEMU_PROTOCOL_UNCONFIRMED'
        assert query.call_count == asked
        world['active'] = True
        world['parameters'] = {'x-swap-direct-type': -1, 'x-swap-direct-zobj': True}
        emulator.write_bytes(b'prototype')
        if missing == 'qemu-protocol':
            # A QEMU that speaks the protocol is another process: the VM was started again.
            with open(paths['/proc/902/stat'], 'w') as stream:
                stream.write('902 (worker (qemu)) ' + ' '.join(['0'] * 19 + ['56']))
    assert plugin._swap_direct_capability(state)['supported'] is True
    assert conn.getCapabilities.call_count == (2 if missing == 'kernel' else 1)


def test_swap_direct_busy_qemu_is_asked_again_at_the_next_observation(direct_host):
    # A QEMU that cannot answer now (an incoming migration holds its monitor) is not remembered as unproven.
    plugin, _, world, state, conn, query, kernel, emulator, running, paths = direct_host
    world['parameters'] = None
    assert plugin._swap_direct_capability(state)['reasonCode'] == 'SWAP_DIRECT_RUNNING_QEMU_BUSY'
    assert plugin._swap_direct_unproven_cache is None
    asked = query.call_count
    assert plugin._swap_direct_capability(state)['reasonCode'] == 'SWAP_DIRECT_RUNNING_QEMU_BUSY'
    assert query.call_count > asked
    world['parameters'] = {'x-swap-direct-type': -1, 'x-swap-direct-zobj': True}
    assert plugin._swap_direct_capability(state)['supported'] is True


def test_host_observation_publishes_negative_direct_gate_without_preflight(direct_host, monkeypatch):
    plugin, service, world, _, _, _, _, _, _, _ = direct_host
    world['xml'] = '<capabilities><host/></capabilities>'
    monkeypatch.setattr(plugin, '_observe_ksm', lambda: {})
    monkeypatch.setattr(plugin, '_complete_vm_inventory', lambda native: ({}, True))
    state = MemoryOptimizationPlugin._observe(plugin)
    capability = state['capabilities']['swapDirect']
    assert capability == {'supported': False, 'reasonCode': 'SWAP_DIRECT_LIBVIRT_CAPABILITY_UNCONFIRMED',
                          'bootId': state['bootId'], 'poolGeneration': state['zram']['poolGeneration']}
    assert 'migration-hold' not in service.actions()
    plugin._swap_direct_preflight.assert_not_called()


@pytest.mark.parametrize('changed', ['pool', 'daemon-missing'])
def test_swap_direct_lost_host_identity_invalidates_a_positive_cache(direct_host, changed):
    plugin, _, world, state, conn, query, kernel, _, _, _ = direct_host
    assert plugin._swap_direct_capability(state)['supported'] is True
    if changed == 'pool':
        state['zram']['pool']['pool_generation'] = 'mismatched-native-pool'
    else:
        world['daemon'] = None
    assert plugin._swap_direct_capability(state)['supported'] is False
    assert plugin._swap_direct_capability_cache is None
    assert (conn.getCapabilities.call_count, query.call_count, kernel.call_count) == (1, 2, 1)


def test_swap_direct_disappeared_probe_is_rediscovered_in_the_same_observation(direct_host):
    plugin, _, world, state, conn, query, kernel, _, _, paths = direct_host
    assert plugin._swap_direct_capability(state)['supported'] is True
    os.unlink(paths['/proc/902/stat'])
    world['active'] = False
    result = plugin._swap_direct_capability(state)
    assert result['supported'] is False
    assert result['reasonCode'] == 'SWAP_DIRECT_RUNNING_QEMU_PROTOCOL_UNCONFIRMED'
    assert plugin._swap_direct_capability_cache is None
    assert conn.getCapabilities.call_count == 1


def test_swap_direct_rechecks_identity_and_forwards_different_local_types(host, monkeypatch):
    plugin, service, world = host
    source = {'hostUuid': HOST, 'bootId': 'boot', 'poolGeneration': POOL, 'instanceGeneration': 'vm-generation',
              'device': 0, 'rdev': '65024', 'swapType': 3, 'compressor': 'lzo-rle', 'qemuSha256': 'qemu-hash',
              'backendIdentity': {'rdev': '66048'}, 'supported': True}
    destination = dict(source, hostUuid='2' * 32, swapType=7, device=1, rdev='65025')
    request = {'operationUuid': OPERATION, 'source': source, 'destination': destination}
    monkeypatch.setattr(plugin, '_swap_direct_preflight', lambda query, state, **kwargs: dict(source))
    params = plugin.prepare_swap_direct('3' * 32, request)
    assert params['x-swap-direct-source-type'] == 3
    assert params['x-swap-direct-dest-type'] == 7
    assert params['x-swap-direct-dest-rdev'] == 65025
    # Java generic maps may round-trip small, exact integral values as doubles.
    destination['swapType'] = 7.0
    assert plugin.prepare_swap_direct('3' * 32, request)['x-swap-direct-dest-type'] == 7
    monkeypatch.setattr(plugin, '_swap_direct_preflight', lambda query, state, **kwargs: dict(source, poolGeneration='new-pool'))
    with pytest.raises(Rejected, match='PREPARED_IDENTITY_CHANGED:poolGeneration'):
        plugin.prepare_swap_direct('3' * 32, request)


@pytest.mark.parametrize('held', [False, True])
def test_swap_direct_missing_hold_or_host_proof_does_not_probe_or_touch_devices(host, monkeypatch, held):
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_swap_direct_capability', lambda state: {'supported': False, 'reasonCode': 'SWAP_DIRECT_LIBVIRT_CAPABILITY_UNCONFIRMED'})
    probe = Mock(side_effect=AssertionError('must not probe without hold'))
    monkeypatch.setattr(plugin, '_probe_swap_type', probe)
    monkeypatch.setattr(module.platform, 'machine', lambda: 'x86_64')
    if held:
        status = {'host_zram': {'pool_generation': POOL},
                  'lifecycle': {'migrationHolds': [{'operation_id': OPERATION, 'pool_generation': POOL}]}}
        monkeypatch.setattr(plugin, '_service', lambda action: status)
    reason = 'LIBVIRT_CAPABILITY_UNCONFIRMED' if held else 'MIGRATION_HOLD_MISSING'
    with pytest.raises(Rejected, match=reason):
        plugin._swap_direct_preflight({'operationUuid': OPERATION, 'poolGeneration': POOL},
                                      {'bootId': 'boot', 'zram': {'poolGeneration': POOL}})
    probe.assert_not_called()


@pytest.mark.parametrize('original, used, expected', [
    (32 << 20, 1 << 20, 1 << 30),            # too little in the pool to tell: the whole size
    (8 << 30, 2400 << 20, 375 << 20),        # 0.29 of the data, plus a quarter
    (8 << 30, 8 << 30, 1 << 30),             # never more than the pages themselves
])
def test_swap_direct_cold_pool_bytes_follow_the_source_pool(host, original, used, expected):
    plugin, service, world = host
    assert plugin._swap_direct_cold_pool_bytes(1 << 30, [original, 0, used, 0]) == expected


def test_swap_direct_rejects_fractional_or_boolean_swap_type(host, monkeypatch):
    plugin, service, world = host
    source = {'hostUuid': HOST, 'supported': True, 'device': 0, 'rdev': '65024', 'swapType': 3, 'compressor': 'lzo'}
    monkeypatch.setattr(plugin, '_swap_direct_preflight', lambda query, state, **kwargs: dict(source))
    for value in (True, 1.25, -1, 32):
        request = {'operationUuid': OPERATION, 'source': source, 'destination': dict(source, swapType=value)}
        with pytest.raises(Rejected, match='INVALID_DEVICE_IDENTITY'):
            plugin.prepare_swap_direct('3' * 32, request)


@pytest.mark.parametrize('exhausted', ['ram', 'slots', 'pool', 'backend', 'no_disk_written_back', None, 'no_disk',
                                       'pool_fits_estimate', 'pool_without_estimate', 'estimate_too_big'])
def test_swap_direct_capacity_is_checked_before_opening_the_device(host, tmp_path, monkeypatch, exhausted):
    import io
    import stat
    plugin, service, world = host
    gib = 1 << 30
    no_disk = exhausted in ('no_disk', 'no_disk_written_back')
    monkeypatch.setattr(plugin, '_swap_direct_capability', lambda state: {'supported': True})
    status = {'host_zram': {'pool_generation': POOL, 'device': '/dev/zram0',
                          'backend': {} if no_disk else {'identity': {'boot_id': 'boot', 'capacity_bytes': gib}}},
              'lifecycle': {'migrationHolds': [{'operation_id': OPERATION, 'pool_generation': POOL}]}}
    monkeypatch.setattr(plugin, '_service', lambda action: status)
    swaps = tmp_path / 'swaps'
    swaps.write_text('Filename Type Size Used Priority\n/dev/zram0 partition %d %d 100\n' %
                     (gib // 1024, (gib - 4096) // 1024 if exhausted == 'slots' else 0))
    monkeypatch.setattr(plugin, 'PROC_SWAPS_PATH', str(swaps))
    monkeypatch.setattr(plugin, 'SYS_BLOCK_PATH', str(tmp_path))
    sysfs = tmp_path / 'zram0'; sysfs.mkdir()
    (sysfs / 'comp_algorithm').write_text('[lzo] lzo-rle')
    (sysfs / 'backing_dev').write_text('none' if no_disk else 'nvme0n1')
    # the estimate cases leave room for gib // 16: less than the cold pages, more than they need compressed
    used = gib if exhausted == 'pool' else gib - gib // 16 if exhausted in ('pool_fits_estimate', 'pool_without_estimate') else 0
    (sysfs / 'mm_stat').write_text('0 0 %d %d' % (used, gib))
    if not no_disk:
        (sysfs / 'bd_stat').write_text('%d 0 0' % (gib // 4096 - 1 if exhausted == 'backend' else 0))
    original_stat = os.lstat
    monkeypatch.setattr(module.os, 'lstat', lambda path: SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=65024, st_ino=1)
                        if path == '/dev/zram0' else original_stat(path))
    original_open = open
    monkeypatch.setattr(module, 'open', lambda path, *args, **kwargs:
                        io.StringIO('MemAvailable: %d kB\n' % (0 if exhausted == 'ram' else 2 * gib // 1024))
                        if path == '/proc/meminfo' else original_open(path, *args, **kwargs), raising=False)
    device = Mock(side_effect=RuntimeError('capacity accepted before device open'))
    monkeypatch.setattr(module, '_Descriptor', device)
    command = {'operationUuid': OPERATION, 'poolGeneration': POOL, 'swapDirectSource': False,
               'swapDirectMemoryBytes': str(gib), 'swapDirectColdBytes': str(gib // 8)}
    if exhausted == 'pool_fits_estimate':
        command['swapDirectColdPoolBytes'] = str(gib // 32)
    if exhausted == 'estimate_too_big':
        command['swapDirectColdPoolBytes'] = str(gib // 4)
    if exhausted == 'estimate_too_big':
        with pytest.raises(Rejected, match='SWAP_DIRECT_CAPACITY_UNKNOWN'):
            plugin._swap_direct_preflight(command, {'bootId': 'boot'})
        device.assert_not_called()
    elif exhausted == 'no_disk_written_back':
        # Written-back pages need a writeback disk on the destination.
        command['swapDirectWritebackPages'] = '3'
        with pytest.raises(Rejected, match='DESTINATION_WRITEBACK_REQUIRED'):
            plugin._swap_direct_preflight(command, {'bootId': 'boot'})
        device.assert_not_called()
    elif exhausted and exhausted not in ('no_disk', 'pool_fits_estimate'):
        with pytest.raises(Rejected, match='DESTINATION_CAPACITY_INSUFFICIENT'):
            plugin._swap_direct_preflight(command, {'bootId': 'boot'})
        device.assert_not_called()
    else:
        import contextlib
        import struct
        import errno
        device.side_effect = None
        device.return_value = contextlib.nullcontext(7)
        original_fstat = os.fstat
        # only the fake device descriptor: the test runner reads its own files too
        monkeypatch.setattr(module.os, 'fstat', lambda fd: SimpleNamespace(st_rdev=65024) if fd == 7 else original_fstat(fd))
        operations = []
        def check_empty_ioctl(fd, operation, batch, mutate):
            objs, nr, done, compressor = struct.unpack('=QII32s', batch)
            assert (fd, objs, nr, done, mutate) == (7, 0, 0, 0, True)
            # GET fills the selected compressor; PUT must reuse that buffer.
            if operation == 0xc0305aa0:
                batch[:] = struct.pack('=QII32s', 0, 0, 0, b'lzo')
            elif compressor.rstrip(b'\0') != b'lzo':
                raise OSError(errno.EPROTO, 'compressor mismatch')
            operations.append(operation)
            return 0
        monkeypatch.setattr(module.fcntl, 'ioctl', check_empty_ioctl)
        monkeypatch.setattr(plugin, '_probe_swap_type', Mock(side_effect=RuntimeError('ABI accepted before probe')))
        with pytest.raises(RuntimeError, match='ABI accepted before probe'):
            plugin._swap_direct_preflight(command, {'bootId': 'boot'})
        device.assert_called_once()
        assert operations == [0xc0305aa0, 0xc0305aa1]


@pytest.mark.parametrize('output, expected', [('3\n', 3), ('MADVISE_FAILED\n', 'SWAP_DIRECT_PROBE_MADVISE_FAILED'),
                                              ('NOT_SWAPPED\n', 'SWAP_DIRECT_PROBE_NOT_SWAPPED'), ('', 'SWAP_DIRECT_PROBE_NOT_SWAPPED')])
def test_swap_type_probe_runs_outside_the_agent_cgroup(host, monkeypatch, output, expected):
    # The agent may be kept out of swap, so the probe page is paged out by a child in the root cgroup.
    plugin, service, world = host
    calls = []
    monkeypatch.setattr(type(plugin), '_bounded_command_output',
                        staticmethod(lambda command, timeout: calls.append(command) or output))
    if isinstance(expected, int):
        assert plugin._probe_swap_type() == expected
    else:
        with pytest.raises(Rejected, match=expected):
            plugin._probe_swap_type()
    assert 'echo $$ > /sys/fs/cgroup/cgroup.procs' in calls[0][2]
    assert calls[0][3:] == [module.sys.executable, plugin.SWAP_TYPE_PROBE]


@pytest.mark.parametrize('changed, expected', [(False, 1), (True, 0)])
def test_swap_direct_backing_estimate_counts_only_unchanged_native_wb_pages(host, tmp_path, monkeypatch, changed, expected):
    import ctypes
    import struct
    plugin, service, world = host
    proc = tmp_path / 'proc'
    root = proc / '123'
    root.mkdir(parents=True)
    (root / 'stat').write_text('123 (qemu) ' + ' '.join(['S'] + ['0'] * 18 + ['321']))
    (root / 'maps').write_text('1000-5000 rw-p 00000000 00:00 0 \n')
    # native written back, native compressed, resident, other swap type
    entries = [(1 << 62) | (9 << 5) | 3, (1 << 62) | (10 << 5) | 3, 1 << 63, (1 << 62) | (11 << 5) | 4]
    (root / 'pagemap').write_bytes(struct.pack('=5Q', 0, *entries))
    device = tmp_path / 'zram0'
    device.write_bytes(b'')
    def get_objects(fd, command, batch, mutate):
        assert command == 0xc0305aa0
        address, count, _, comp = struct.unpack('=QII32s', batch)
        objs = (ctypes.c_char * (40 * count)).from_address(address)
        for i in range(count):
            obj = list(struct.unpack_from('=QQQIIiI', objs, i * 40))
            assert obj[0] in (9, 10)
            obj[5] = -errno.EAGAIN if obj[0] == 9 else 0
            struct.pack_into('=QQQIIiI', objs, i * 40, *obj)
        batch[:] = struct.pack('=QII32s', address, count, count, comp)
        if changed:
            entries[0] = 1 << 63
            (root / 'pagemap').write_bytes(struct.pack('=5Q', 0, *entries))
    monkeypatch.setattr(module.fcntl, 'ioctl', get_objects)
    pages, quality = plugin._swap_direct_backing_pages(123, 16384, str(device), 0, 3, str(proc))
    assert (pages, quality) == (expected, 'native_get_pagemap')
    (root / 'maps').write_text('1000-5000 rw-p 00000000 00:00 0 \n6000-a000 rw-p 00000000 00:00 0 \n')
    assert plugin._swap_direct_backing_pages(123, 16384, str(device), 0, 3, str(proc)) == (0, 'guest_mapping_unconfirmed')


def test_swap_direct_quota_is_forwarded_only_through_existing_hold_write(host):
    plugin, service, world = host
    hold = json.loads(plugin.migration_hold({module.http.REQUEST_BODY: json.dumps(dict(
        hostUuid=HOST, operationUuid=OPERATION, resourceUuid='v' * 32, holdAction='acquire',
        poolGeneration=POOL, writebackPages='625004'))}))
    assert hold['status'] == 'Succeeded'
    payload = next(payload for action, payload in service.calls if action == 'migration-hold')
    assert payload['writeback_pages'] == 625004


@pytest.mark.parametrize('action, pages', [('acquire', None), ('acquire', '0'), ('release', None), ('release', '625004')])
def test_an_ordinary_migration_hold_is_understood_by_a_service_without_the_quota_field(host, action, pages):
    # The phase-one service rejects a request with a field it does not know.
    plugin, service, world = host
    command = dict(hostUuid=HOST, operationUuid=OPERATION, resourceUuid='v' * 32, holdAction=action, poolGeneration=POOL)
    if pages is not None:
        command['writebackPages'] = pages
    hold = json.loads(plugin.migration_hold({module.http.REQUEST_BODY: json.dumps(command)}))
    assert hold['status'] == 'Succeeded'
    payload = [payload for name, payload in service.calls if name == 'migration-hold'][-1]
    assert set(payload) == {'action', 'operation_id', 'pool_generation'}


@pytest.mark.parametrize('xml, refused', [
    ('<domain><memoryBacking><nosharepages/></memoryBacking></domain>', False),
    ('<domain><memoryBacking><source type="anonymous"/><access mode="private"/></memoryBacking></domain>', False),
    ('<domain><memoryBacking><hugepages/></memoryBacking></domain>', True),
    ('<domain><memoryBacking><source type="memfd"/><access mode="shared"/></memoryBacking></domain>', True),
    ('<domain><memoryBacking><source type="file"/></memoryBacking></domain>', True),
    ('<domain><cpu><numa><cell id="0" memAccess="shared"/></numa></cpu></domain>', True),
    ('<domain><devices><memory model="nvdimm"/></devices></domain>', True),
])
def test_swap_direct_refuses_guest_memory_that_qemu_would_reject(xml, refused):
    # Refused in the preflight, such a VM migrates the ordinary way instead of failing in QEMU.
    domain = SimpleNamespace(XMLDesc=lambda flags: xml)
    if refused:
        with pytest.raises(Rejected, match='SWAP_DIRECT_GUEST_MEMORY_UNSUPPORTED'):
            MemoryOptimizationPlugin._swap_direct_guest_memory(domain)
    else:
        MemoryOptimizationPlugin._swap_direct_guest_memory(domain)


@pytest.fixture
def runtime_ksm(host, monkeypatch):
    plugin, service, world = host
    from zstacklib.utils import qmp
    vm = 'b' * 32
    command = {'hostUuid': HOST, 'resourceUuid': vm, 'action': 'set-ksm',
               'expectedInstanceGeneration': 'g1', 'operationUuid': OPERATION, 'ksmEnabled': False}
    merges = {'/objects/guest-node0': True, '/objects/guest-node1': True}
    calls = []
    def native(action, payload):
        calls.append((action, dict(payload)))
        if action == 'vm-identities':
            return {'identities': {vm: {'uuid': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'instance_generation': 'g1', 'pid': 1234, 'start_time': 55}}}
        if action == 'ksm-recovery':
            return {}
        if action == 'status':
            return {'lifecycle': {}}
        raise AssertionError(action)
    def monitor(vm_uuid, action, **args):
        assert vm_uuid == vm
        calls.append((action, args))
        if action == 'qom-set':
            merges[args['path']] = args['value']
            return {}
        if action == 'qom-get':
            return merges[args['path']]
        raise AssertionError(action)
    monkeypatch.setattr(plugin, 'service_call', native)
    monkeypatch.setattr(qmp, 'execute_qmp_command', monitor, raising=False)
    monkeypatch.setattr(plugin, '_vm_ksm_backend', lambda value: {
        'pid': 1234, 'startTime': '55', 'domainId': 7, 'liveNoSharePages': False,
        'backends': [{'path': path, 'merge': enabled} for path, enabled in sorted(merges.items())]})
    monkeypatch.setattr(plugin, '_vm_ksm_headroom', lambda *args: {
        'availableBytes': 8 * 1024 ** 3, 'requiredBytes': 6 * 1024 ** 3})
    monkeypatch.setattr(plugin, '_mem_available', lambda: 8 * 1024 ** 3)
    return plugin, command, merges, calls


def test_runtime_ksm_disables_all_actual_backends_and_arms_durable_recovery(runtime_ksm):
    plugin, command, merges, calls = runtime_ksm
    result = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert result['success'] and result['state']['applied']
    assert list(merges.values()) == [False, False]
    operations = [payload['action'] for action, payload in calls if action == 'ksm-recovery']
    assert operations == ['prepare-ksm-recovery', 'activate-ksm-recovery']
    assert next(i for i, x in enumerate(calls) if x[0] == 'ksm-recovery') < next(i for i, x in enumerate(calls) if x[0] == 'qom-set')
    calls[:] = []
    command['ksmEnabled'] = True
    result = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert result['success'] and list(merges.values()) == [True, True]
    assert not any(action == 'ksm-recovery' for action, _ in calls)


def test_runtime_ksm_headroom_refusal_and_preflight_have_no_side_effects(runtime_ksm, monkeypatch):
    plugin, command, merges, calls = runtime_ksm
    monkeypatch.setattr(plugin, '_vm_ksm_headroom', lambda *args, **kwargs: {'availableBytes': 6, 'requiredBytes': 6})
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert not reply['success'] and reply['reasonCode'].startswith('KSM_UNMERGE_INSUFFICIENT_MEMORY')
    assert all(merges.values())
    assert not any(action in ('qom-set', 'ksm-recovery') for action, _ in calls)
    # Memory taken while the estimate ran is seen again under the Host lock.
    monkeypatch.setattr(plugin, '_vm_ksm_headroom', lambda *args, **kwargs: {
        'availableBytes': 8 * 1024 ** 3, 'requiredBytes': 6 * 1024 ** 3})
    monkeypatch.setattr(plugin, '_mem_available', lambda: 5 * 1024 ** 3)
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert not reply['success'] and reply['reasonCode'].startswith('KSM_UNMERGE_INSUFFICIENT_MEMORY')
    assert all(merges.values())
    assert not any(action in ('qom-set', 'ksm-recovery') for action, _ in calls)


def test_runtime_ksm_refuses_an_unmerge_that_would_stop_the_guest_too_long(runtime_ksm, monkeypatch):
    plugin, command, merges, calls = runtime_ksm
    gib = 1024 ** 3
    asked = []
    def headroom(pid, start_time, count_merged=False):
        asked.append(count_merged)
        if not count_merged:
            # the mapping bound alone: 64 GiB of mergeable memory, nothing counted
            return {'ksmBytes': None, 'unmergeUpperBoundBytes': 64 * gib,
                    'availableBytes': 200 * gib, 'requiredBytes': 100 * gib}
        return {'ksmBytes': merged[0], 'zeroPageBytes': 0, 'unmergeUpperBoundBytes': merged[0],
                'availableBytes': 200 * gib, 'requiredBytes': merged[0] * 3 // 2 + 4 * gib}
    monkeypatch.setattr(plugin, '_vm_ksm_headroom', headroom)
    monkeypatch.setattr(plugin, '_mem_available', lambda: 200 * gib)
    merged = [24 * gib]
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert not reply['success'] and reply['reasonCode'].startswith('KSM_UNMERGE_PAUSE_TOO_LONG')
    assert asked == [False, True] and all(merges.values())
    assert not any(action in ('qom-set', 'ksm-recovery') for action, _ in calls)
    merged[0] = 2 * gib
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert reply['success'] and list(merges.values()) == [False, False]


def test_runtime_ksm_unsupported_and_stale_instance_are_not_applied(runtime_ksm, monkeypatch):
    plugin, command, merges, calls = runtime_ksm
    command['expectedInstanceGeneration'] = 'old'
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert reply['reasonCode'] == 'INSTANCE_GENERATION_CONFLICT'
    command['expectedInstanceGeneration'] = 'g1'
    def unsupported(vm):
        raise Rejected('KSM_RUNTIME_UNSUPPORTED_NEXT_START')
    monkeypatch.setattr(plugin, '_vm_ksm_backend', unsupported)
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert not reply['success'] and reply['reasonCode'] == 'KSM_RUNTIME_UNSUPPORTED_NEXT_START'
    assert not any(action in ('qom-set', 'ksm-recovery') for action, _ in calls)


def test_runtime_ksm_preflight_rejects_another_vm_recovery_before_configuration_save(runtime_ksm, monkeypatch):
    plugin, command, merges, calls = runtime_ksm
    original = plugin.service_call
    active = {'phase': 'Active', 'vm_uuid': 'a' * 32, 'instance_generation': 'g-other',
              'operation_id': '2' * 32}
    monkeypatch.setattr(plugin, 'service_call', lambda action, payload:
                        {'lifecycle': {'ksmRecovery': active}} if action == 'status' else original(action, payload))
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert not reply['success'] and reply['reasonCode'] == 'KSM_RECOVERY_HOST_BUSY'
    assert all(merges.values())
    assert not any(action in ('qom-set', 'ksm-recovery') for action, _ in calls)
    # Turning sharing back on for the instance that owns the recovery cancels it.
    active.update(vm_uuid=command['resourceUuid'], instance_generation='g1')
    for path in merges: merges[path] = False
    command['ksmEnabled'] = True
    assert json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))['success']
    assert all(merges.values())
    assert ('ksm-recovery', {'action': 'restore-ksm-recovery', 'operation_id': active['operation_id'],
                             'reason': 'cancelled'}) in calls


def test_runtime_ksm_failure_restores_tuning_and_agent_lifecycle_retries(runtime_ksm, monkeypatch):
    plugin, command, merges, calls = runtime_ksm
    from zstacklib.utils import qmp
    def fail(*args, **kwargs):
        raise IOError('monitor disconnected')
    monkeypatch.setattr(qmp, 'execute_qmp_command', fail, raising=False)
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert not reply['success']
    actions = [payload['action'] for action, payload in calls if action == 'ksm-recovery']
    assert actions == ['prepare-ksm-recovery', 'restore-ksm-recovery']
    plugin._restore_ksm_tuning('agent-startup')
    plugin.stop()
    assert calls[-2:] == [('ksm-recovery', {'action': 'restore-ksm-recovery', 'reason': 'agent-startup'}),
                         ('ksm-recovery', {'action': 'restore-ksm-recovery', 'reason': 'agent-stop'})]


def test_agent_http_shutdown_restores_temporary_ksm_tuning(host, monkeypatch):
    plugin, service, world = host
    engine = Mock()
    monkeypatch.setattr(module.cherrypy, 'engine', engine)
    monkeypatch.setattr(module.kvmagent, 'get_http_server', lambda: Mock())
    calls = []
    monkeypatch.setattr(plugin, '_service', lambda action, payload: calls.append((action, payload)))
    plugin.start()
    event, handler = engine.subscribe.call_args.args
    assert event == 'stop'
    handler()
    assert calls == [
        ('ksm-recovery', {'action': 'restore-ksm-recovery', 'reason': 'agent-startup'}),
        ('ksm-recovery', {'action': 'restore-ksm-recovery', 'reason': 'agent-stop'})]


@pytest.mark.parametrize('alias', [False, True])
def test_vm_ksm_headroom_uses_only_mergeable_present_ksm_and_zero_pages(tmp_path, monkeypatch, alias):
    import struct
    monkeypatch.setattr(module.linux, 'monotime', time.monotonic, raising=False)
    proc = tmp_path
    root = proc / '1234'
    root.mkdir()
    (root / 'smaps').write_text('00001000-00005000 rw-p 00000000 00:00 0\nRss: 8 kB\nVmFlags: rd wr mg\n'
                               '00005000-00006000 rw-p 00000000 00:00 0\nVmFlags: rd wr\n')
    entries = [0, (1 << 63) | 1, (1 << 63) | 2, (1 << 63) | (1 if alias else 3), (1 << 62) | 4, (1 << 63) | 4]
    (root / 'pagemap').write_bytes(struct.pack('=6Q', *entries))
    flags = [0] * 1024
    flags[1], flags[2], flags[4] = 1 << 21, 1 << 24, 1 << 21
    (proc / 'kpageflags').write_bytes(struct.pack('=1024Q', *flags))
    (root / 'stat').write_text('1234 (qemu) ' + ' '.join(['0'] * 19 + ['55']))
    # The VMA bound exceeds available, but the counted KSM/zero pages fit.
    (proc / 'meminfo').write_text('MemAvailable: 4194324 kB\n')
    result = MemoryOptimizationPlugin._vm_ksm_headroom(1234, '55', str(proc))
    assert result['ksmBytes'] == (2 if alias else 1) * 4096
    assert result['zeroPageBytes'] == 4096
    assert result['requiredBytes'] == 4 * 1024 ** 3 + (18432 if alias else 12288)
    assert result['requiredBytes'] < result['availableBytes'] == 4 * 1024 ** 3 + 20 * 1024
    with pytest.raises(Rejected, match='INSTANCE_GENERATION_CONFLICT'):
        MemoryOptimizationPlugin._vm_ksm_headroom(1234, '54', str(proc))


def test_vm_ksm_headroom_fast_bound_covers_zero_mappings_without_page_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(module.linux, 'monotime', time.monotonic, raising=False)
    root = tmp_path / '1234'; root.mkdir()
    # Zero-page mappings can have zero RSS; all 16GiB must remain in the bound.
    # A further 32GiB nonmergeable mapping does not contribute.
    (root / 'smaps').write_text('00000000-400000000 rw-p 00000000 00:00 0\nRss: 0 kB\nVmFlags: rd wr mg\n'
                               '400000000-c00000000 rw-p 00000000 00:00 0\nRss: 33554432 kB\nVmFlags: rd wr\n')
    (root / 'stat').write_text('1234 (qemu) ' + ' '.join(['0'] * 19 + ['55']))
    (tmp_path / 'meminfo').write_text('MemAvailable: 67108864 kB\n')
    # There is deliberately no pagemap or kpageflags: opening either would fail.
    result = MemoryOptimizationPlugin._vm_ksm_headroom(1234, '55', str(tmp_path))
    assert result['unmergeUpperBoundBytes'] == 16 * 1024 ** 3
    assert result['requiredBytes'] == 28 * 1024 ** 3
    assert result['ksmBytes'] is None and result['zeroPageBytes'] is None
    with pytest.raises(Rejected, match='INSTANCE_GENERATION_CONFLICT'):
        MemoryOptimizationPlugin._vm_ksm_headroom(1234, '54', str(tmp_path))


@pytest.mark.parametrize('memory_bytes,budget', [(4 << 30, 20), (16 << 30, 32),
                                                  (64 << 30, 120), (1024 << 30, 120), (32 << 20, 20)])
def test_vm_ksm_headroom_scan_timeout_reports_completed_pages(tmp_path, monkeypatch, runtime_ksm, memory_bytes, budget):
    root = tmp_path / '1234'; root.mkdir()
    (root / 'smaps').write_text('00000000-%x rw-p 00000000 00:00 0\nVmFlags: rd wr mg\n' % memory_bytes)
    (root / 'stat').write_text('1234 (qemu) ' + ' '.join(['0'] * 19 + ['55']))
    (tmp_path / 'meminfo').write_text('MemAvailable: 0 kB\n')
    (root / 'pagemap').write_bytes(b'\0' * (8192 * 8))
    (tmp_path / 'kpageflags').write_bytes(b'')
    clock = iter([0, 1, budget + 1])
    monkeypatch.setattr(module.linux, 'monotime', lambda: next(clock), raising=False)
    with pytest.raises(Rejected, match='KSM_UNMERGE_ESTIMATE_TIMEOUT') as caught:
        MemoryOptimizationPlugin._vm_ksm_headroom(1234, '55', str(tmp_path))
    assert str(caught.value) == caught.value.reason == 'KSM_UNMERGE_ESTIMATE_TIMEOUT'
    assert 'scanned=8192/%d pages' % (memory_bytes // 4096) in caught.value.details
    assert 'budget=%ds' % budget in caught.value.details
    assert '%' in caught.value.details
    plugin, command, merges, calls = runtime_ksm
    monkeypatch.setattr(module.linux, 'monotime', time.monotonic, raising=False)
    monkeypatch.setattr(plugin, '_vm_ksm_headroom', Mock(side_effect=caught.value))
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert reply['success'] is False and reply['status'] == 'Failed'
    assert reply['reasonCode'] == 'KSM_UNMERGE_ESTIMATE_TIMEOUT'
    assert reply['reason'] == caught.value.details
    assert all(merges.values())
    assert not any(action in ('qom-set', 'ksm-recovery') for action, _ in calls)


def test_runtime_ksm_scan_budget_does_not_extend_host_lock_wait(runtime_ksm, monkeypatch):
    from contextlib import contextmanager
    plugin, command, merges, calls = runtime_ksm
    waits = []
    @contextmanager
    def locked(wait):
        waits.append(wait)
        yield
    monkeypatch.setattr(plugin, '_host_lock', locked)
    command['communication'] = {'communicationSeconds': 180}
    result = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert result['success']
    assert waits == [15]


@pytest.mark.parametrize('replacement,unsupported', [(False, False), (True, False), (False, True), (True, True)])
def test_vm_readback_only_queries_target_and_rejects_replaced_identity(host, monkeypatch, replacement, unsupported):
    plugin, service, world = host
    vm = 'b' * 32
    identity = {'uuid': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                'instance_generation': 'g1', 'pid': 1234, 'start_time': 55}
    calls = []

    def native(action, payload):
        calls.append((action, payload))
        if action == 'vm-policy-state':
            assert payload == {'_resource': vm}
            return {'identity': identity, 'binding_generation': 'g1', 'binding_mode': 'deny'}
        if action == 'vm-identities':
            assert payload == {'vm_uuids': [vm]}
            return {'identities': {vm: dict(identity, instance_generation='g2' if replacement else 'g1')}}
        raise AssertionError('unexpected full-host observation: ' + action)

    def backend(value):
        assert value == vm
        if unsupported:
            raise Rejected('KSM_RUNTIME_UNSUPPORTED_NEXT_START')
        return {'pid': 1234, 'startTime': '55', 'liveNoSharePages': True,
                'backends': [{'path': '/objects/guest-node0', 'merge': False}]}

    monkeypatch.setattr(plugin, 'service_call', native)
    monkeypatch.setattr(plugin, '_observe', Mock(side_effect=AssertionError('full host observation')))
    monkeypatch.setattr(plugin, '_vm_ksm_backend', backend)
    result = plugin.state({module.http.REQUEST_BODY: json.dumps(
        {'hostUuid': HOST, 'resourceUuid': vm, 'vmMemoryState': True})})
    if isinstance(result, str):
        result = json.loads(result)
    state = result['state']
    plugin._observe.assert_not_called()
    if replacement:
        assert 'vms' not in state
        assert state['vmMemoryState']['reasonCode'] == 'VM_MEMORY_STATE_UNKNOWN'
    else:
        assert set(state['vms']) == {vm}
        assert state['vms'][vm] == {'instanceGeneration': 'g1', 'binding_generation': 'g1', 'binding_mode': 'deny'}
        assert state['vmMemoryState']['supported'] is not unsupported
    assert len(calls) == 2


def test_a_binding_reads_one_vm_identity_without_observing_the_host(host, monkeypatch):
    plugin, service, world = host
    vm = 'b' * 32
    calls = []
    def native(action, payload):
        calls.append(action)
        assert (action, payload) == ('vm-identities', {'vm_uuids': [vm]})
        return {'identities': {vm: {'uuid': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'instance_generation': 'g1'}}}
    monkeypatch.setattr(plugin, 'service_call', native)
    monkeypatch.setattr(plugin, '_observe', Mock(side_effect=AssertionError('full host observation')))
    result = json.loads(plugin.state({module.http.REQUEST_BODY: json.dumps(
        {'hostUuid': HOST, 'resourceUuid': vm, 'vmIdentity': True})}))
    assert result['state'] == {'vms': {vm: {'instanceGeneration': 'g1'}}}
    assert calls == ['vm-identities']


def test_page_sharing_on_a_host_without_the_service_takes_effect_at_the_next_start(host, monkeypatch):
    # Other operating systems and architectures have no service; the setting must still be saved.
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_service_available', lambda: False)
    monkeypatch.setattr(plugin, 'service_call', Mock(side_effect=AssertionError('no service to call')))
    monkeypatch.setattr(plugin, '_observe', Mock(side_effect=AssertionError('full host observation')))
    result = json.loads(plugin.state({module.http.REQUEST_BODY: json.dumps(
        {'hostUuid': HOST, 'resourceUuid': 'b' * 32, 'vmMemoryState': True})}))
    assert result['success']
    assert result['state']['vmMemoryState'] == {'supported': False, 'reasonCode': 'KSM_RUNTIME_UNSUPPORTED_NEXT_START'}


def test_runtime_ksm_discovers_backend_names_and_requires_merge_capability(host, monkeypatch, tmp_path):
    import builtins
    from zstacklib.utils import qmp
    import libvirt
    plugin, service, world = host
    path = tmp_path / 'stat'
    path.write_text('1234 (qemu) ' + ' '.join(['0'] * 19 + ['55']))
    real_open = builtins.open
    monkeypatch.setattr(builtins, 'open', lambda p, *a, **kw: real_open(path if p == '/proc/1234/stat' else p, *a, **kw))
    domain = SimpleNamespace(isActive=lambda: True, ID=lambda: 7, XMLDesc=lambda flags: '<domain><memoryBacking><nosharepages/></memoryBacking></domain>')
    conn = SimpleNamespace(lookupByUUIDString=lambda uuid: domain, close=lambda: None)
    monkeypatch.setattr(libvirt, 'openReadOnly', lambda uri: conn, raising=False)
    monkeypatch.setattr(module.linux, 'get_vm_pid', lambda uuid: 1234, raising=False)
    supported = [True]
    def monitor(vm, action, **args):
        if action == 'query-memdev': return [{'id': 'node-42', 'size': 8192}]
        if action == 'qom-list' and args['path'] == '/objects': return [{'name': 'node-42', 'type': 'child<memory-backend-ram>'}]
        if action == 'qom-list': return [{'name': 'merge', 'type': 'bool'}] if supported[0] else []
        if action == 'qom-get':
            assert args['path'] == '/objects/node-42'
            return False
        raise AssertionError('read-only discovery attempted ' + action)
    monkeypatch.setattr(qmp, 'execute_qmp_command', monitor, raising=False)
    proof = plugin._vm_ksm_backend('b' * 32)
    assert proof['backends'] == [{'path': '/objects/node-42', 'merge': False}]
    assert proof['liveNoSharePages'] and proof['startTime'] == '55'
    supported[0] = False
    with pytest.raises(Rejected, match='KSM_RUNTIME_UNSUPPORTED_NEXT_START'):
        plugin._vm_ksm_backend('b' * 32)


def test_vm_reclaim_readback_cannot_claim_a_replaced_instance(host, monkeypatch):
    plugin, service, world = host
    def changed(action, payload):
        result = service(action, payload)
        if action == 'vm-policy-state': return dict(result, instance_generation='replacement')
        return result
    monkeypatch.setattr(plugin, 'service_call', changed)
    command = {'hostUuid': HOST, 'action': 'bind', 'resourceUuid': 'b' * 32,
               'expectedInstanceGeneration': 'g1', 'participation': 'deny'}
    reply = json.loads(plugin.vm_efficiency({'body': json.dumps(command)}))
    assert not reply['success'] and reply['reasonCode'] == 'VM_POLICY_READBACK_MISMATCH'



@pytest.mark.parametrize('interval', [300, 301, 600, 86400])
def test_hot_memory_period_uses_seconds(host, interval):
    plugin, _, _ = host
    want = desired()
    want['hotMemory'] = {'enabled': True, 'interval': interval}
    assert plugin._desired(want)['hotMemory']['interval'] == interval


@pytest.mark.parametrize('interval', [True, 299, 86401, 600.5, '600'])
def test_invalid_hot_memory_period_has_no_side_effect(host, interval):
    plugin, service, world = host
    want = desired()
    want['hotMemory'] = {'enabled': True, 'interval': interval}
    assert apply(plugin, 1, want)['reasonCode'] == 'INVALID_DESIRED_CONFIGURATION'
    assert not service.calls


def test_hot_memory_lifecycle_is_independent_and_idempotent(host, tmp_path, monkeypatch):
    plugin, service, world = host
    config = tmp_path / 'hotmem.json'
    config.write_text('{"interval_seconds":600}')
    monkeypatch.setattr(plugin, 'HOT_MEMORY_CONFIG', str(config))
    unit = {'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'disabled'}
    calls = []
    monkeypatch.setattr(plugin, '_unit_properties', lambda name, *keys: dict(unit))

    def run(argv, timeout):
        calls.append(argv)
        if argv[1] == 'enable':
            unit.update(ActiveState='active', SubState='running', UnitFileState='enabled')
        elif argv[1] == 'disable':
            unit.update(ActiveState='inactive', SubState='dead', UnitFileState='disabled')
    monkeypatch.setattr(plugin, '_bounded_command_output', run)
    monkeypatch.setattr(plugin, '_managed_service_installed', lambda: False)
    want = desired(control='paused', zram=False)
    want['hotMemory'] = {'enabled': True, 'interval': 600}
    assert apply(plugin, 1, want)['status'] == 'Succeeded'
    assert calls == [['systemctl', 'enable', '--now', plugin.MANAGED_HOT_MEMORY_UNIT]]
    assert not service.calls
    calls[:] = []
    assert apply(plugin, 2, want)['status'] == 'Succeeded'
    assert not calls
    want['hotMemory']['interval'] = 900
    assert apply(plugin, 3, want)['status'] == 'Succeeded'
    assert json.loads(config.read_text()) == {'interval_seconds': 900}
    assert calls == [['systemctl', 'restart', plugin.MANAGED_HOT_MEMORY_UNIT]]
    calls[:] = []
    want['hotMemory']['enabled'] = False
    assert apply(plugin, 4, want)['status'] == 'Succeeded'
    assert calls == [['systemctl', 'disable', '--now', plugin.MANAGED_HOT_MEMORY_UNIT]]
    assert not service.calls


@pytest.mark.parametrize('starting, state, expected', [
    (True, {'ActiveState': 'activating', 'SubState': 'start'}, Converging),
    (True, {'ActiveState': 'active', 'SubState': 'running'}, None),
    (True, {'ActiveState': 'failed', 'SubState': 'failed'}, Rejected),
    (False, {'ActiveState': 'deactivating', 'SubState': 'stop'}, Converging),
    (False, {'ActiveState': 'inactive', 'SubState': 'dead'}, None),
    (False, {'ActiveState': 'active', 'SubState': 'running'}, Rejected),
])
def test_hot_memory_command_timeout_uses_current_unit_state(host, monkeypatch, starting, state, expected):
    plugin, _, _ = host
    monkeypatch.setattr(plugin, '_bounded_command_output',
                        lambda *args: (_ for _ in ()).throw(RuntimeError('BOUNDED_COMMAND_TIMEOUT')))
    monkeypatch.setattr(plugin, '_unit_properties', lambda *args: dict(state))
    if expected is None:
        plugin._run_hot_memory_command(['systemctl', 'enable', '--now', plugin.MANAGED_HOT_MEMORY_UNIT],
                                       plugin.MANAGED_HOT_MEMORY_UNIT, starting)
    else:
        reason = ('HOT_MEMORY_SERVICE_STARTING' if starting else 'HOT_MEMORY_SERVICE_STOPPING')
        if expected is Rejected:
            reason = ('HOT_MEMORY_SERVICE_START_FAILED' if starting else 'HOT_MEMORY_SERVICE_STOP_FAILED')
        with pytest.raises(expected, match=reason):
            plugin._run_hot_memory_command(['systemctl', 'enable', '--now', plugin.MANAGED_HOT_MEMORY_UNIT],
                                           plugin.MANAGED_HOT_MEMORY_UNIT, starting)


@pytest.mark.parametrize('properties, expected', [
    ({'LoadState': 'not-found', 'ActiveState': 'inactive'}, 'absent'),
    ({'LoadState': 'loaded', 'ActiveState': 'active'}, 'active'),
    ({'LoadState': 'loaded', 'ActiveState': 'failed'}, 'failed'),
    ({'LoadState': 'masked'}, 'unknown'),
    ({}, 'unknown'),
])
def test_hot_memory_service_observation(host, monkeypatch, properties, expected):
    plugin, _, _ = host
    monkeypatch.setattr(plugin, '_unit_properties', lambda *args: properties)
    monkeypatch.setattr(plugin, '_observe_ksm', lambda: {})
    monkeypatch.setattr(plugin, '_libvirt_vm_generations', lambda: ({}, True))
    assert MemoryOptimizationPlugin._observe(plugin)['hotMemory']['serviceState'] == expected


def test_missing_hotmem_package_does_not_block_default_off(host, monkeypatch):
    plugin, _, _ = host
    monkeypatch.setattr(plugin, '_unit_properties', lambda *args: {'LoadState': 'not-found'})
    plugin._converge_hot_memory({'enabled': False})
    with pytest.raises(Rejected, match='HOT_MEMORY_SERVICE_NOT_INSTALLED'):
        plugin._converge_hot_memory({'enabled': True})


@pytest.mark.parametrize('error, status', [
    (Rejected('HOT_MEMORY_SERVICE_NOT_INSTALLED'), 'Failed'),
    (Converging('HOT_MEMORY_SERVICE_STARTING'), 'Converging'),
    (OSError('start failed'), 'Failed')])
def test_hot_memory_failure_does_not_block_ksm_or_zram(host, monkeypatch, error, status):
    plugin, service, world = host
    def fail(_):
        raise error
    monkeypatch.setattr(plugin, '_converge_hot_memory', fail)
    want = desired(ksm=True)
    want['hotMemory'] = {'enabled': True, 'interval': 600}
    result = apply(plugin, 1, want)
    # An observer that is not installed or does not start is reported, and the generation is
    # applied: KSM and ZRAM have converged. One still starting is asked again, as before.
    if status == 'Failed':
        assert result['status'] == 'Succeeded' and result['appliedGeneration'] == 1
    else:
        assert result['status'] == 'Converging' and result['appliedGeneration'] is None
    assert world['ksm'] and 'host-cpu' in service.actions() and service.efficiency
    assert result['state']['hotMemory']['status'] == status
    assert result['state']['hotMemory']['reasonCode'].startswith('HOT_MEMORY_')


@pytest.mark.parametrize('state', [{}, {'LoadState': 'masked'}, {'LoadState': 'not-found', 'ActiveState': 'active'}])
def test_hot_memory_off_needs_no_installed_or_readable_observer(host, monkeypatch, state):
    plugin, _, _ = host
    commands = []
    monkeypatch.setattr(plugin, '_unit_properties', lambda *args: dict(state))
    monkeypatch.setattr(plugin, '_bounded_command_output', lambda argv, timeout: commands.append(argv) or '')
    plugin._converge_hot_memory({'enabled': False})
    # only an observer left running after its package was removed is stopped
    assert commands == ([['systemctl', 'stop', 'zstack-hotmem.service']] if state.get('ActiveState') == 'active' else [])
    with pytest.raises(Rejected, match='HOT_MEMORY_SERVICE_'):
        plugin._converge_hot_memory({'enabled': True})


@pytest.mark.parametrize('hot_error', [False, True])
def test_zram_pending_does_not_hide_hot_memory_result(host, monkeypatch, hot_error):
    plugin, service, world = host
    world['unit'] = 'starting'
    calls = []
    def converge_hot(desired):
        calls.append(desired)
        if hot_error:
            raise Rejected('HOT_MEMORY_SERVICE_NOT_INSTALLED')
    monkeypatch.setattr(plugin, '_converge_hot_memory', converge_hot)
    want = desired()
    want['hotMemory'] = {'enabled': True, 'interval': 600}
    result = apply(plugin, 1, want)
    assert result['status'] == 'Converging' and result['reasonCode'] == 'SERVICE_STARTING'
    assert result['state']['hotMemory']['status'] == ('Failed' if hot_error else 'Succeeded')
    assert calls == [want['hotMemory']]
    assert result['appliedGeneration'] is None

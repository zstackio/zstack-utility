"""Converge the host to the desired memory optimisation through a fake service."""
import json
import os
import time

import pytest

from kvmagent.plugins import memory_optimization as module
from kvmagent.plugins import memory_optimization_ksm_native as ksm_native
from kvmagent.plugins.memory_optimization import Converging, MemoryOptimizationPlugin, Rejected

HOST = '1' * 32
POOL = 'a' * 64


class FakeService(object):
    """The ZRAM service's idempotent API, as the Agent sees it."""

    def __init__(self):
        self.calls = []
        self.pool = POOL
        self.paused = False
        self.maintenance = False
        self.efficiency = False
        self.capacity = {'logical_capacity': {}, 'physical_memory_limit': {}}
        self.capacity_state = 'APPLIED'
        self.writeback = False
        self.receipts = {'pool': {'stage': 'NOT_STARTED'}, 'backend': {'stage': 'NOT_STARTED'}}
        self.activation_error = None
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
            return {'desired': {'configured': dict(self.capacity)}, 'apply_state': self.capacity_state}
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
            prepared = self.receipts['pool']
            # Like the service: a completed pool preparation must be named exactly; a backend one is
            # checked by its own identity.
            if prepared.get('stage') == 'APPLIED' and \
                    prepared.get('expected_control_operation_uuid') != payload['expected_control_operation_uuid']:
                # The service activates only the exact preparation it recorded.
                return {'_http_status': 409, 'error': 'MAINTENANCE_ACTIVATION_PREPARATION_MISMATCH'}
            self.paused = False
            return {'receipt': {'stage': 'UNPAUSED'}}
        if action in ('zram-pool-maintenance-finalize', 'backend-maintenance-finalize'):
            kind = 'pool' if action.startswith('zram') else 'backend'
            self.receipts[kind] = dict(self.receipts[kind], stage='APPLIED')
            self.maintenance = False
            return self.receipts[kind]
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


def test_an_older_generation_is_rejected_while_a_newer_one_converges(host):
    plugin, service, world = host
    world['unit'] = 'starting'
    assert apply(plugin, 11, desired())['reasonCode'] == 'SERVICE_STARTING'
    world['unit'] = 'active'
    assert apply(plugin, 10, desired(zram=False))['reasonCode'] == 'STALE_GENERATION'
    assert apply(plugin, 11, desired())['status'] == 'Succeeded'


def test_an_older_generation_is_rejected_without_changes(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_managed_service_installed', lambda: False)
    assert apply(plugin, 4, desired(zram=None, ksm=True))['status'] == 'Succeeded'
    stale = apply(plugin, 3, desired(zram=None, ksm=False))
    assert stale['status'] == 'Failed' and stale['reasonCode'] == 'STALE_GENERATION'
    assert stale['appliedGeneration'] == 4
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
                        'physical_memory_limit': {'percent_of_logical': 50.0}}
    result = apply(plugin, 6, desired())
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


def test_activation_names_the_preparation_the_service_activates(host):
    plugin, service, world = host
    service.pool, service.paused = None, True
    service.receipts['backend'] = {'stage': 'APPLIED', 'request_id': 'backend-3-x', 'pool_generation': 'b' * 64}
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-9-' + POOL[:16], 'pool_generation': POOL,
                                'expected_control_operation_uuid': 'pool-9-' + POOL[:16]}
    apply(plugin, 9, desired())
    activation = [payload for action, payload in service.calls if action == 'lifecycle-activate-maintenance']
    assert activation[-1]['expected_pool_generation'] == POOL
    assert activation[-1]['request_id'] == 'activate-pool-9-' + POOL[:16]
    # Without a completed pool preparation the backend preparation is activated.
    service.calls[:] = []
    service.paused = True
    service.receipts['pool'] = {'stage': 'NOT_STARTED'}
    apply(plugin, 10, desired())
    activation = [payload for action, payload in service.calls if action == 'lifecycle-activate-maintenance']
    assert activation[-1]['expected_pool_generation'] == 'b' * 64
    assert activation[-1]['request_id'] == 'activate-backend-3-x'
    assert service.paused is False


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


def test_an_activation_waiting_for_the_service_to_settle_is_converging(host):
    plugin, service, world = host
    service.pool, service.paused = None, True
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-9-' + POOL[:16], 'pool_generation': POOL,
                                'expected_control_operation_uuid': 'pool-9-' + POOL[:16]}
    service.activation_error = 'MAINTENANCE_ACTIVATION_NATIVE_NOT_READY'
    result = apply(plugin, 9, desired())
    assert result['status'] == 'Converging' and result['reasonCode'] == 'MAINTENANCE_ACTIVATION_NATIVE_NOT_READY'


def test_a_rejected_activation_keeps_the_pool_drained(host):
    plugin, service, world = host
    service.paused, service.pool = True, None
    service.receipts['pool'] = {'stage': 'APPLIED', 'request_id': 'pool-12', 'pool_generation': POOL}
    service.activation_error = 'MAINTENANCE_ACTIVATION_VM_INVENTORY_NOT_READY'
    result = apply(plugin, 13, desired())
    assert result['status'] == 'Failed' and result['reasonCode'] == 'MAINTENANCE_ACTIVATION_VM_INVENTORY_NOT_READY'
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
    assert service.calls[-1] == ('vm-policy', {'expected_instance_generation': 'g1', 'mode': 'deny',
                                              'cpu_rule': None, '_resource': 'b' * 32})
    revoke = {'body': json.dumps({'hostUuid': HOST, 'action': 'revoke', 'resourceUuid': 'b' * 32})}
    assert json.loads(plugin.vm_efficiency(revoke))['status'] == 'Succeeded'
    assert len(service.calls) == 1


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
                                            'eligible': True, 'capacityBytes': capacity, 'stableIdentity': {
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
        'candidates': [{'device': '/dev/vdb', 'eligible': True, 'state': 'NEEDS_OFFLINE_PREPARATION'}]})
    inventory = plugin._writeback_inventory(HOST)
    assert inventory['canPrepare'] is can_prepare, inventory['preparationReasons']


def test_only_a_possible_candidate_is_probed_for_signatures():
    from kvmagent.plugins import memory_writeback_backends as backends
    volumes = [{'name': '/dev/mapper/vg-lv%d' % i, 'kname': 'dm-%d' % i, 'type': 'lvm', 'size': 1 << 30,
                'maj:min': '253:%d' % i} for i in range(300)]
    lsblk = {'blockdevices': [{'name': '/dev/vdb', 'kname': 'vdb', 'type': 'disk', 'size': 1 << 30,
                               'maj:min': '252:16', 'serial': 'disk-a', 'tran': 'virtio'}] + volumes}
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
            raise OSError(2, path)

        def realpath(self, path):
            return path

        def stat(self, path):
            raise OSError(2, path)

        lstat = stat
    backends.probe_writeback_backends(HOST, runner=runner, filesystem=Filesystem())
    # 300 logical volumes are ineligible anyway; a signature probe each would outlast the MN call.
    assert len([path for path in probed if path.startswith('/dev/mapper/')]) == 0


def test_the_active_backend_disk_is_recorded_by_its_persistent_identity(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: '/dev/vdb')
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'candidates': [{'device': '/dev/vdb', 'state': 'ACTIVE', 'eligible': True, 'stableIdentity': {
            'serial': 'disk-a', 'wwn': '', 'byIdPath': '/dev/disk/by-id/virtio-disk-a', 'rdev': 64784}}]})
    plugin._writeback_inventory(HOST)
    assert plugin._backend_identity() == {'device': '/dev/vdb', 'serial': 'disk-a', 'wwn': '',
                                          'byIdPath': '/dev/disk/by-id/virtio-disk-a'}


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
    monkeypatch.setattr(plugin, '_writeback_inventory',
                        lambda host_uuid: {'canPrepare': True, 'poolGeneration': POOL})
    built = []
    monkeypatch.setattr(module, 'build_backend_maintenance_request',
                        lambda inventory, preparation: built.append(preparation) or {'request_id': preparation['requestId']})
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 20, 'candidateId': 'candidate:' + 'd' * 64,
               'expectedHostBootId': 'boot', 'expectedPoolGeneration': POOL, 'backendCapacityBytes': 1 << 30,
               'resetConfirmed': True}
    def prepare():
        return json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))

    first = prepare()
    assert first['status'] == 'Converging' and first['reasonCode'] == 'BACKEND_PREPARING'
    request_id = 'backend-20-' + 'd' * 16
    assert built[0]['requestId'] == request_id
    assert world['started'][0][:2] == ('zstack-memory-backend-' + request_id, '--prepare-backend-maintenance')
    assert prepare()['reasonCode'] == 'BACKEND_PREPARING'
    service.receipts['backend'] = {'stage': 'APPLIED', 'request_id': request_id, 'pool_generation': POOL,
                                   'backend_resource_uuid': 'f' * 32}
    done = prepare()
    assert done['status'] == 'Succeeded' and done['state']['maintenance']['backend_resource_uuid'] == 'f' * 32
    assert len(world['started']) == 1


def test_a_host_without_a_pool_stops_its_service_to_prepare_a_backend(host, monkeypatch):
    plugin, service, world = host
    service.pool, service.efficiency = None, True
    monkeypatch.setattr(plugin, '_previous_backend_device', lambda: None)
    monkeypatch.setattr(module, 'probe_writeback_backends', lambda host_uuid, backend, config: {
        'candidates': [{'identity': 'candidate:' + 'd' * 64, 'device': '/dev/vdb', 'eligible': True,
                        'state': 'NEEDS_OFFLINE_PREPARATION'}]})
    monkeypatch.setattr(module, 'build_backend_maintenance_request',
                        lambda inventory, preparation: {'request_id': preparation['requestId']})
    inventory = plugin._writeback_inventory(HOST)
    assert inventory['canPrepare'] is True and inventory['poolGeneration'] == 'none', inventory
    command = {'hostUuid': HOST, 'action': 'prepare', 'generation': 4, 'candidateId': 'candidate:' + 'd' * 64,
               'expectedHostBootId': 'boot', 'expectedPoolGeneration': 'none', 'backendCapacityBytes': 1 << 30,
               'resetConfirmed': True}
    result = json.loads(plugin.writeback_backends({module.http.REQUEST_BODY: json.dumps(command)}))
    assert result['status'] == 'Converging' and result['reasonCode'] == 'BACKEND_PREPARING', result
    # Stopped like a drain: paused, and the host policy off as the readback requires.
    assert world['unit'] == 'inactive' and service.paused is True and service.efficiency is False
    assert world['started'][0][1] == '--prepare-backend-maintenance'


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

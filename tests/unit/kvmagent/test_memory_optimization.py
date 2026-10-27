"""Converge the host to the desired memory optimisation through a fake service."""
import json
import os

import pytest

from kvmagent.plugins import memory_optimization as module
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

    def __call__(self, action, payload):
        self.calls.append((action, dict(payload)))
        if action == 'status':
            return {'host_zram': {'pool_generation': self.pool}, 'mode': 'reclaim',
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

    def run_executor(unit, argument, request=None):
        world['started'].append((unit, argument, request))
        world['executors'][unit] = ('running', None)
    monkeypatch.setattr(plugin, '_run_executor', run_executor)

    def command(argv, timeout):
        if argv[:2] == ['systemctl', 'stop']:
            world['unit'] = 'inactive'
        if argv[:2] == ['systemctl', 'start']:
            world['unit'] = 'active'
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
    assert service.actions() == [] and plugin._applied_generation() is None


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


def test_an_unknown_capability_without_reclaim_interfaces_is_rejected(host, monkeypatch):
    plugin, service, world = host
    world['unit'] = 'inactive'
    world['drained'] = {'state': MemoryOptimizationPlugin.DRAINED, 'pool_generation': POOL}
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'zram': False, 'zramReasonCode': 'SERVICE_RECLAIM_CAPABILITY_UNKNOWN',
        'interfaces': {'cgroupv2': True, 'memory_reclaim': False}})
    assert apply(plugin, 7, desired())['reasonCode'] == 'SERVICE_RECLAIM_CAPABILITY_UNKNOWN'
    assert world['started'] == []


def test_an_unsupported_kernel_is_still_rejected(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, 'discover_capabilities', lambda: {
        'supported': True, 'ksm': True, 'zram': False, 'zramReasonCode': 'UNSUPPORTED_RECLAIM_KERNEL'})
    assert apply(plugin, 8, desired())['reasonCode'] == 'UNSUPPORTED_RECLAIM_KERNEL'
    assert service.calls == []


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
                                'pool_generation': POOL, 'host_boot_id': 'boot'}
    service.pool, service.maintenance = None, True
    world['drained'] = None
    second = apply(plugin, 12, desired())
    assert world['unit'] == 'active' and service.receipts['pool']['stage'] == 'APPLIED'
    activation = [payload for action, payload in service.calls if action == 'lifecycle-activate-maintenance']
    assert activation and activation[0]['request_id'] == 'activate-12-' + POOL[:16]
    assert service.paused is False and service.efficiency is True
    assert second['reasonCode'] == 'WAITING_FOR_POOL'
    service.pool = POOL
    assert apply(plugin, 12, desired())['status'] == 'Succeeded'


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


def test_unsupported_zram_is_rejected_before_any_change(host, monkeypatch):
    plugin, service, world = host
    monkeypatch.setattr(plugin, 'discover_capabilities',
                        lambda: {'supported': True, 'ksm': True, 'zram': False, 'zramReasonCode': 'HOST_PSI_UNAVAILABLE'})
    result = apply(plugin, 17, desired())
    assert result['reasonCode'] == 'HOST_PSI_UNAVAILABLE' and service.actions() == []


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

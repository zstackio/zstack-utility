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
from kvmagent.plugins import memory_optimization_ksm_native

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


class _NativeKsmSimulator(object):
    """Small sysfs/config/systemd model for Agent-level KSM tests."""
    _units = ('ksm.service', 'ksmtuned.service')

    def __init__(self, plugin, active=False, enabled=False):
        self.plugin = plugin
        self.sysfs = {'run': '1' if active else '0', 'pages_to_scan': '1250',
                      'sleep_millisecs': '10', 'use_zero_pages': '0'}
        self.ack = dict(self.sysfs)
        self.ack['configRevision'] = None
        self.services = {unit: {'active': 'active' if active else 'inactive',
                                'enabled': 'enabled' if enabled else 'disabled'}
                         for unit in self._units}

    def matches(self, argv):
        return (isinstance(argv, (tuple, list)) and len(argv) >= 3 and
                argv[0] == 'systemctl' and argv[-1] in self._units)

    def service_state(self, unit, operation):
        if unit not in self.services or operation not in ('active', 'enabled'):
            return None
        return self.services[unit][operation]

    def read_sysfs(self, name):
        if name not in self.sysfs:
            raise ValueError('unknown KSM sysfs attribute: %s' % name)
        return self.sysfs[name]

    def write_sysfs(self, name, value):
        if name not in self.sysfs:
            raise ValueError('unknown KSM sysfs attribute: %s' % name)
        self.sysfs[name] = value
        self.ack[name] = value

    def _read_config(self):
        try:
            with open(self.plugin.KSM_CONF, 'r') as stream:
                values = memory_optimization_ksm_native.managed_config_values(stream.read())
        except IOError:
            return None
        return values

    def _ack_config(self):
        config = self._read_config()
        if not config:
            return
        self.sysfs['pages_to_scan'] = str(config['KSM_NPAGES_MAX'])
        with open('/proc/meminfo', 'r') as stream:
            memtotal_kb = memory_optimization_ksm_native.parse_memtotal_kb(stream.read())
        sleep = config['KSM_SLEEP_MSEC']
        self.sysfs['sleep_millisecs'] = str(max(
            10, sleep * memory_optimization_ksm_native.SLEEP_BASE_KB // memtotal_kb))
        self.ack.update(self.sysfs)
        self.ack['configRevision'] = str(config['CONFIG_REVISION'])

    def command(self, argv):
        action = argv[1]
        targets = argv[2:]
        for unit in targets:
            if unit not in self.services:
                raise AssertionError('unexpected systemd unit: %s' % unit)
            if action == 'enable':
                self.services[unit]['enabled'] = 'enabled'
            elif action == 'disable':
                self.services[unit]['enabled'] = 'disabled'
            elif action in ('start', 'restart'):
                self.services[unit]['active'] = 'active'
                if unit == 'ksm.service':
                    self.sysfs['run'] = '1'
                elif unit == 'ksmtuned.service':
                    self._ack_config()
            elif action == 'stop':
                self.services[unit]['active'] = 'inactive'
                if unit == 'ksm.service':
                    self.sysfs['run'] = '0'
            else:
                raise AssertionError('unexpected systemctl action: %s' % action)
            self.ack.update(self.sysfs)
        return 0




class MemoryOptimizationTestBase(TestCase):
    def setUp(self):
        super(MemoryOptimizationTestBase, self).setUp()
        self._native_ksm_simulators = []
        self._native_ksm_check_call = patch.object(
            subprocess, 'check_call', side_effect=self._dispatch_native_ksm_command)
        self._native_ksm_check_call.start()
        self.addCleanup(self._native_ksm_check_call.stop)

    def _dispatch_native_ksm_command(self, argv, *args, **kwargs):
        for simulator in reversed(self._native_ksm_simulators):
            if simulator.matches(argv):
                return simulator.command(argv)
        raise AssertionError('unexpected unmocked privileged command: %r' % (argv,))

    def _native_ksm_test_adapter(self, plugin, active=False, enabled=False):
        """Use native config/sysfs/service readback, never a wrapper status CLI."""
        if not hasattr(self, '_native_ksm_simulators'):
            self._native_ksm_simulators = []
            self._native_ksm_check_call = patch.object(
                subprocess, 'check_call', side_effect=self._dispatch_native_ksm_command)
            self._native_ksm_check_call.start()
            self.addCleanup(self._native_ksm_check_call.stop)
        if not hasattr(self, '_native_ksm_profile_patch'):
            self._native_ksm_profile_patch = patch.object(
                MemoryOptimizationPlugin, '_verify_native_ksm_profile',
                lambda _plugin: None)
            self._native_ksm_profile_patch.start()
            self.addCleanup(self._native_ksm_profile_patch.stop)
        simulator = _NativeKsmSimulator(plugin, active=active, enabled=enabled)
        self._native_ksm_simulators.append(simulator)
        plugin._verify_native_ksm_profile = lambda: None
        if getattr(plugin, 'KSM_LOCK', None) == MemoryOptimizationPlugin.KSM_LOCK:
            plugin.KSM_LOCK = os.path.join(plugin.operation_dir, 'ksm.writer.lock')
        plugin._native_service_state = simulator.service_state
        plugin._read_ksm_sysfs = simulator.read_sysfs
        plugin._write_ksm_sysfs = simulator.write_sysfs
        plugin._test_native_ksm_simulator = simulator
        return simulator

    def _first_use_fixture(self, state=None):
        directory = tempfile.mkdtemp(prefix='first-zram-use-')
        self.addCleanup(shutil.rmtree, directory)
        plugin = MemoryOptimizationPlugin(service_call=lambda action, payload: {})
        operation_directory = os.path.join(directory, 'operations')
        os.makedirs(operation_directory)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_directory})
        plugin.KSM_CONF = os.path.join(directory, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(directory, 'ksm.writer.lock')
        # Partial cold-host observations must use the same native sysfs path
        # as production; this adapter does not turn the Unknown control reply
        # into a successful operation receipt.
        self._native_ksm_test_adapter(plugin)
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
    def setUp(self):
        # These tests exercise policy flow on the test workstation, not its
        # host ABI.  Unsupported-host behavior is covered explicitly below.
        # The real KVM REST service calls configure() before exposing handlers.
        # Many historical isolated tests instantiate the plugin directly, so
        # give those instances the same empty-config lifecycle by default.
        original_init = MemoryOptimizationPlugin.__init__

        def initialize_configured_plugin(plugin, *args, **kwargs):
            original_init(plugin, *args, **kwargs)
            if not hasattr(plugin, 'config'):
                plugin.configure({})

        self.plugin_init_patch = patch.object(
            MemoryOptimizationPlugin, '__init__', initialize_configured_plugin)
        self.plugin_init_patch.start()
        self.addCleanup(self.plugin_init_patch.stop)
        self.capability_patch = patch.object(
            MemoryOptimizationPlugin, 'discover_capabilities',
            return_value={'supported': True, 'reasonCode': 'SUPPORTED',
                          'ksm': True, 'ksmZeroPages': True,
                          'zram': True, 'writeback': True})
        self.capability_patch.start()
        self.addCleanup(self.capability_patch.stop)
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
    def _ksm_only_state_plugin(self, operation_dir):
        """Build the no-Go-socket fixture used by the Kylin KSM-only contract."""
        def unavailable(*args, **kwargs):
            raise RuntimeError('zram service unavailable')
        plugin = MemoryOptimizationPlugin(service_call=unavailable)
        plugin.configure({'hostUuid': 'host-1', 'operationDir': operation_dir,
                          'socketPath': os.path.join(operation_dir, 'missing.sock')})
        plugin.KSM_CONF = os.path.join(operation_dir, 'ksmtuned.conf')
        plugin._libvirt_vm_generations = lambda: ({}, True)
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'kylinV10',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': False, 'zramReasonCode': 'ABI_INCOMPLETE', 'service': False,
        }
        self._native_ksm_test_adapter(plugin)
        return plugin
    def _real_applied_ksm_fixture(self, root, revision=41):
        plugin = self._ksm_only_state_plugin(root)
        plugin.service_call = plugin._call_local_service
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        command = {'hostUuid': 'host-1', 'operationUuid': 'real-fixture-%s' % revision,
                   'desiredRevision': revision,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-%s' % revision,
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                      'sleepMillis': 20, 'zeroPagesEnabled': True},
                              'zram': {'enabled': False}, 'writeback': {'enabled': False}}}
        plugin._test_native_ksm_simulator.sysfs['run'] = '0'
        result = plugin.apply(command)
        self.assertTrue(result['success'])
        path = os.path.join(root, command['operationUuid'] + '.json')
        with open(path) as stream:
            record = json.load(stream)
        self.assertIs(True, record['readback']['state'].get('ksmOnly'))
        observed = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Succeeded', observed['status'])
        return plugin, command, path
    def _managed_clear_fixture(self, root, revision=91, enabled=False, scope=None,
                               resource_uuid=None):
        """Create a current managed native KSM journal and sysfs/config readback."""
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        native = plugin._test_native_ksm_simulator

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
        result = plugin.apply(initial)
        self.assertTrue(result['success'])
        operation_path = os.path.join(root, initial['operationUuid'] + '.json')
        return plugin, initial, native.ack, native.command, operation_path
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
        native = self._native_ksm_test_adapter(plugin)
        service_writes = []
        native_ack = native.ack
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

        # Legacy call sites in retained tests still bracket apply() with a
        # check_output patch. Native KSM state itself is read from the simulator
        # through the production readback methods above.
        native_command = lambda *args, **kwargs: b''

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
        native = self._native_ksm_test_adapter(plugin)
        native_ack = native.ack
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'h84r',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': True, 'service': True}
        original_readback = plugin._read_ksm_ack

        def native_readback():
            config = plugin._read_native_ksm_config()
            if faults.get('native_ack_fault') == 'omit-zero-pages':
                events.append(('native-ack', None))
                return None
            if (faults.get('native_ack_fault') == 'readback-error-after-write' and
                    config and config.get('CONFIG_REVISION') != 1):
                events.append(('native-ack', None))
                return None
            ack = original_readback()
            events.append(('native-ack', dict(ack) if ack else None))
            return ack

        plugin._read_ksm_ack = native_readback
        plugin.ksm_apply_timeout = 0
        native_command = lambda *args, **kwargs: b''

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

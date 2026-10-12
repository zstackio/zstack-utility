"""Memory optimization state_capability behavior tests.

Migrated from the legacy Agent test module; all methods remain discovered by pytest.
"""

from tests.unit.kvmagent.memory_optimization_test_support import *
from tests.unit.kvmagent.memory_optimization_test_support import _OMIT_POLICY_MODE
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.kvmagent]

class TestMemoryOptimizationStateCapability(MemoryOptimizationTestBase):
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
        with tempfile.TemporaryDirectory() as directory:
            plugin = self._ksm_only_state_plugin(directory)
            plugin.KSM_CONF = os.path.join(directory, 'ksmtuned.conf')
            plugin.KSM_LOCK = os.path.join(directory, 'ksm.writer.lock')
            with open(plugin.KSM_CONF, 'w') as stream:
                stream.write('CUSTOM_VENDOR_OPTION=preserve-me\n')
            simulator = plugin._test_native_ksm_simulator
            simulator.sysfs.update({'run': '0', 'pages_to_scan': '1250',
                                    'sleep_millisecs': '10', 'use_zero_pages': '1'})
            simulator.ack.update(simulator.sysfs)

            result = plugin._apply_ksm_policy({'desiredRevision': 3,
                                               'policy': {'ksm': {'enabled': False,
                                                                  'pagesToScan': 1300,
                                                                  'sleepMillis': 10,
                                                                  'zeroPagesEnabled': True}}})

            self.assertEqual('run=0', 'run=' + simulator.sysfs['run'])
            self.assertEqual('1300', simulator.sysfs['pages_to_scan'])
            self.assertEqual('10', simulator.sysfs['sleep_millisecs'])
            self.assertEqual('1', simulator.sysfs['use_zero_pages'])
            self.assertEqual('3', plugin._read_ksm_ack()['configRevision'])
            with open(plugin.KSM_CONF) as stream:
                self.assertIn('CUSTOM_VENDOR_OPTION=preserve-me', stream.read())
            self.assertTrue(all(state['active'] == 'inactive' and state['enabled'] == 'disabled'
                                for state in simulator.services.values()))
            self.assertFalse(result.get('controlApplied', False),
                             'parameter write is not an enable/start success')
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
    def test_service_payload_does_not_send_ksm_to_zram_service(self):
        payload = MemoryOptimizationPlugin._service_payload(
            'apply', {'operationUuid': 'op-1', 'expectedRevision': 2,
                      'policy': {'ksm': {'enabled': True, 'pagesToScan': 500},
                                 'zram': {'hostFloorBytes': 123},
                                 'writeback': {'enabled': False}}})
        self.assertNotIn('ksm', payload)
        self.assertEqual(123, payload['settings']['host_floor_bytes'])
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
        self.assertTrue(response['success'], response)
        self.assertEqual(['vm-policy-state', 'vm-policy'], [item[0] for item in calls])
        self.assertEqual('vm-1', calls[1][1]['_resource_uuid'])
        self.assertEqual('gen-1', calls[1][1]['expected_instance_generation'])
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
                          'sleep_millisecs': '20', 'use_zero_pages': '0'}, native_ack)
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
                                 plugin._read_ksm_ack().get('configRevision'))
                record = json.load(open(os.path.join(root, command['operationUuid'] + '.json')))
                self.assertIs(True, (record.get('readback') or {}).get('state', {}).get('ksmOnly'))
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
        native = self._native_ksm_test_adapter(plugin)
        native_ack = native.ack
        plugin.discover_capabilities = lambda: {
            'supported': True, 'reasonCode': 'SUPPORTED', 'release': 'h84r',
            'ksm': True, 'ksmZeroPages': True, 'ksmZeroPagesCounter': False,
            'zram': True, 'service': True}
        read_native_ack = plugin._read_ksm_ack
        def readback_with_event():
            ack = read_native_ack()
            events.append(('native-ack', dict(ack) if ack else None))
            return ack
        plugin._read_ksm_ack = readback_with_event
        publish_native_config = plugin._publish_ksm_config
        def publish_with_event(content):
            events.append(('native-write', content))
            return publish_native_config(content)
        plugin._publish_ksm_config = publish_with_event
        native_command = lambda *args, **kwargs: b''

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
        write_index = next((i for i, entry in enumerate(events) if entry[0] == 'native-write'), None)
        if write_index is None:
            violations.append('native KSM config was not written')
        elif any(
                next((i for i, entry in enumerate(events)
                      if entry[0] == 'go' and entry[1] == action), write_index + 1) > write_index
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
    def test_partial_native_ksm_update_preserves_customer_config_and_run_state(self):
        """A sparse update adds the managed block without erasing native config."""
        root = tempfile.mkdtemp(prefix='legacy-partial-ksm-config-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        native = self._native_ksm_test_adapter(plugin, active=True, enabled=True)
        customer_config = '# locally managed native settings\nCUSTOM_VENDOR_OPTION=enabled\n'
        with open(plugin.KSM_CONF, 'w') as stream:
            stream.write(customer_config)

        command = {'hostUuid': 'host-1', 'operationUuid': 'legacy-partial-ksm',
                   'expectedRevision': 4, 'desiredRevision': 5,
                   'licensePermit': {'managed': True, 'operationUuid': 'legacy-permit',
                       'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                   'policy': {'ksm': {'pagesToScan': 200}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        result = plugin.apply(command)
        self.assertTrue(result['success'], result)
        # A missing enabled value preserves the active native writer while
        # publishing only the managed policy block.
        self.assertEqual('1', result['ksmReadback']['run'])
        self.assertEqual('5', native.ack.get('configRevision'))
        with open(plugin.KSM_CONF) as stream:
            self.assertIn(customer_config, stream.read())
    def test_invalid_prior_ksm_journal_cannot_authorize_sparse_clear(self):
        cases = ('old-boot', 'pending', 'mixed', 'malformed-zram-string',
                 'malformed-zram-number', 'malformed-writeback-string',
                 'malformed-writeback-number', 'corrupt', 'missing-ksmOnly')
        for index, mutation in enumerate(cases):
            with self.subTest(prior_journal=mutation):
                root = tempfile.mkdtemp(prefix='managed-marker-invalid-journal-')
                plugin, initial, native_ack, native_command, path = self._managed_clear_fixture(
                    root, 101 + index, enabled=True)
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
                before_config = Path(plugin.KSM_CONF).read_bytes()
                result = plugin.apply(cleared)
                with open(os.path.join(root, cleared['operationUuid'] + '.json')) as stream:
                    result_record = json.load(stream)
                self.assertFalse(result.get('success'),
                    'invalid current-boot KSM-only journal evidence must fence clear')
                self.assertNotEqual('Succeeded', result.get('status'))
                self.assertNotEqual('APPLIED', result_record.get('stage'))
                self.assertEqual(str(initial['desiredRevision']), native_ack.get('configRevision'))
                self.assertEqual(before_config, Path(plugin.KSM_CONF).read_bytes())
    def test_clear_final_ksm_override_never_journals_unacknowledged_revision(self):
        """Clearing a final managed KSM override advances only on native writer ack."""
        root = tempfile.mkdtemp(prefix='real-clear-final-ksm-')
        plugin, initial, _, _, _ = self._managed_clear_fixture(
            root, revision=41, enabled=False)
        cleared = self._clear_managed_policy(initial, 'clear-final-after')
        response = plugin.apply(cleared)
        with open(os.path.join(root, 'clear-final-after.json')) as stream:
            record = json.load(stream)
        with self.subTest(proof='clear must be APPLIED only after revisioned native readback'):
            self.assertTrue(response.get('success'), response)
            self.assertEqual('Succeeded', response.get('status'))
            self.assertEqual('42', plugin._read_ksm_ack().get('configRevision'),
                             'APPLIED revision must come from the sole writer, not the requested revision')
            self.assertEqual({'run': '0', 'configRevision': '42', 'pages_to_scan': '600',
                              'sleep_millisecs': '30', 'use_zero_pages': '0'},
                             plugin._read_ksm_ack())
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
        observed = json.loads(plugin.state({'body': json.dumps({
            'hostUuid': 'host-1', 'operationUuid': 'clear-final-state'})}))
        self.assertEqual('Succeeded', observed['status'])
        self.assertEqual(42, observed['appliedRevision'])
        self.assertIs(True, observed['state'].get('ksmOnly'))

        # The empty request policy must not erase the resolved native proof:
        # current-boot identity alone cannot hide parameter drift.
        stable = dict(plugin._read_ksm_ack())
        for field, wrong in (('run', '1'), ('pages_to_scan', '101'),
                             ('sleep_millisecs', '21'), ('use_zero_pages', '1'),
                             ('configRevision', '41')):
            with self.subTest(field=field):
                if field == 'configRevision':
                    text = Path(plugin.KSM_CONF).read_text()
                    Path(plugin.KSM_CONF).write_text(text.replace(
                        '# CONFIG_REVISION=42', '# CONFIG_REVISION=' + wrong))
                else:
                    plugin._test_native_ksm_simulator.sysfs[field] = wrong
                drifted = json.loads(plugin.state({'body': json.dumps({
                    'hostUuid': 'host-1', 'operationUuid': 'clear-final-drift-' + field})}))
                self.assertEqual('Unknown', drifted['status'])
                self.assertFalse(drifted['state']['safeToRemove'])
                if field == 'configRevision':
                    text = Path(plugin.KSM_CONF).read_text()
                    Path(plugin.KSM_CONF).write_text(text.replace(
                        '# CONFIG_REVISION=' + wrong, '# CONFIG_REVISION=42'))
                else:
                    plugin._test_native_ksm_simulator.sysfs[field] = stable[field]
    def test_clear_child_override_with_inherited_ksm_applies_inherited_values(self):
        """A non-empty inherited KSM target still goes through native revisioned apply."""
        root = tempfile.mkdtemp(prefix='real-clear-inherited-ksm-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        self._native_ksm_test_adapter(plugin)

        command = {'hostUuid': 'host-1', 'operationUuid': 'clear-inherited-ksm',
                   'desiredRevision': 51,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-51',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {'enabled': False, 'pagesToScan': 333,
                                      'sleepMillis': 25, 'zeroPagesEnabled': False},
                              'zram': {'enabled': False}, 'writeback': {'enabled': False}}}
        response = plugin.apply(command)
        self.assertTrue(response['success'], response)
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
        native = self._native_ksm_test_adapter(plugin)
        native_ack = native.ack

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
        first = plugin.apply(initial)
        self.assertTrue(first['success'], first)
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
        native = self._native_ksm_test_adapter(plugin)
        command = {'hostUuid': 'host-1', 'operationUuid': 'empty-unmanaged-ksm',
                   'desiredRevision': 61,
                   'licensePermit': {'managed': True, 'operationUuid': 'permit-61',
                                     'expiresAt': int(time.time() * 1000) + 35000,
                                     'validForSeconds': 30},
                   'policy': {'ksm': {}, 'zram': {'enabled': False},
                              'writeback': {'enabled': False}}}
        response = plugin.apply(command)
        self.assertTrue(response['success'])
        self.assertEqual({'ksm.service': {'active': 'inactive', 'enabled': 'disabled'},
                          'ksmtuned.service': {'active': 'inactive', 'enabled': 'disabled'}},
                         native.services)
        self.assertFalse(os.path.exists(plugin.KSM_CONF))
        with open(os.path.join(root, 'empty-unmanaged-ksm.json')) as stream:
            record = json.load(stream)
        self.assertIsNot(True, record.get('readback', {}).get('state', {}).get('ksmOnly'))
    def test_clear_empty_ksm_target_with_stale_writer_ack_is_not_applied(self):
        root = tempfile.mkdtemp(prefix='real-clear-stale-ack-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        native = self._native_ksm_test_adapter(plugin)
        plugin.ksm_apply_timeout = 0
        read_native_ack = plugin._read_ksm_ack
        stale_ack = [None]
        missing_ack = [False]

        def controlled_ack():
            current = read_native_ack()
            if missing_ack[0]:
                return None
            return dict(stale_ack[0]) if stale_ack[0] is not None else current

        plugin._read_ksm_ack = controlled_ack

        def command(operation, revision, ksm):
            return {'hostUuid': 'host-1', 'operationUuid': operation,
                    'desiredRevision': revision,
                    'licensePermit': {'managed': True, 'operationUuid': 'permit-%s' % revision,
                        'expiresAt': int(time.time() * 1000) + 35000, 'validForSeconds': 30},
                    'policy': {'ksm': ksm, 'zram': {'enabled': False},
                               'writeback': {'enabled': False}}}

        first = plugin.apply(command('clear-stale-before', 81,
            {'enabled': False, 'pagesToScan': 555, 'sleepMillis': 40,
             'zeroPagesEnabled': False}))
        self.assertTrue(first['success'], first)
        stale_ack[0] = dict(read_native_ack())
        response = plugin.apply(command('clear-stale-after', 82, {}))
        with open(os.path.join(root, 'clear-stale-after.json')) as stream:
            record = json.load(stream)
        with self.subTest(ack='stale'):
            self.assertFalse(response.get('success'), 'requested revision is not writer acknowledgement')
            self.assertNotEqual('Succeeded', response.get('status'))
            self.assertNotEqual('APPLIED', record.get('stage'))
            self.assertEqual(82, plugin._read_native_ksm_config().get('CONFIG_REVISION'),
                             'the simulated writer advanced but the read path returned stale data')

        stale_ack[0] = None
        baseline = plugin.apply(command('clear-missing-before', 83,
            {'enabled': False, 'pagesToScan': 556, 'sleepMillis': 40,
             'zeroPagesEnabled': False}))
        self.assertTrue(baseline['success'], baseline)
        missing_ack[0] = True
        missing = plugin.apply(command('clear-missing-after', 84, {}))
        with open(os.path.join(root, 'clear-missing-after.json')) as stream:
            missing_record = json.load(stream)
        with self.subTest(ack='missing'):
            self.assertFalse(missing.get('success'), 'missing native receipt cannot be inferred from config')
            self.assertNotEqual('Succeeded', missing.get('status'))
            self.assertNotEqual('APPLIED', missing_record.get('stage'))
            self.assertEqual(83, plugin._read_native_ksm_config().get('CONFIG_REVISION'),
                             'missing prior readback must fence before any config write')
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
        simulator = plugin._test_native_ksm_simulator
        actual = dict(plugin._read_ksm_ack())
        for field, wrong in [('run', '0'), ('configRevision', '44'), ('pages_to_scan', '1'),
                             ('sleep_millisecs', '99'), ('use_zero_pages', '0')]:
            with self.subTest(field=field):
                if field == 'configRevision':
                    text = Path(plugin.KSM_CONF).read_text()
                    Path(plugin.KSM_CONF).write_text(text.replace(
                        '# CONFIG_REVISION=45', '# CONFIG_REVISION=' + wrong))
                else:
                    simulator.sysfs[field] = wrong
                response = json.loads(plugin.state({'body': json.dumps({
                    'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
                self.assertEqual('Unknown', response['status'])
                self.assertFalse(response['state']['safeToRemove'])
                if field == 'configRevision':
                    text = Path(plugin.KSM_CONF).read_text()
                    Path(plugin.KSM_CONF).write_text(text.replace(
                        '# CONFIG_REVISION=' + wrong, '# CONFIG_REVISION=45'))
                else:
                    simulator.sysfs[field] = actual[field]
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
            plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
            plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
            plugin.service_call = plugin._call_local_service
            command = {'hostUuid': 'host-1', 'operationUuid': 'observer-ksm',
                       'desiredRevision': 22,
                       'licensePermit': {'managed': True, 'operationUuid': 'permit-observer',
                                         'expiresAt': int(time.time() * 1000) + 35000,
                                         'validForSeconds': 30},
                       'policy': {'ksm': {
                           'enabled': enabled, 'pagesToScan': 2000,
                           'sleepMillis': 20, 'zeroPagesEnabled': False},
                           'zram': {'enabled': False}, 'writeback': {'enabled': False}}}
            applied = plugin.apply(command)
            self.assertTrue(applied.get('success'), applied)
            self.assertEqual('Succeeded', applied.get('status'))
            snapshot = {'success': True, 'status': 'Succeeded', 'state': {
                'mode': 'observe', 'resource_authorized': False,
                'lifecycle': {'activeState': 'compatibility', 'paused': False},
                'host_zram': {'quality': 'unavailable', 'device': '', 'pool_generation': ''}}}
            with patch.object(plugin, '_dispatch', return_value=snapshot):
                response = json.loads(plugin.state({'body': json.dumps({
                    'hostUuid': 'host-1', 'operationUuid': 'observation'})}))
            self.assertTrue(response['state'].get('ksmOnly'))
            self.assertEqual('Succeeded', response['status'])
            self.assertEqual('compatibility', response['state']['lifecycle']['activeState'])
            self.assertEqual('unavailable', response['state']['host_zram']['quality'])
            self.assertEqual(command['operationUuid'], response['state']['lastConfirmedOperationUuid'])
            self.assertEqual(enabled, response['state']['actual']['ksm']['enabled'])
            self.assertFalse(response['state']['safeToRemove'])
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
                                  'state': {'ksmOnly': True},
                                  'ksmReadback': {'run': '1', 'configRevision': '22',
                                                  'pages_to_scan': '2000',
                                                  'sleep_millisecs': '20',
                                                  'use_zero_pages': '1'}})
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
        readback.assert_called_once_with(command['policy']['ksm'], 22,
                                         {'run': '1', 'configRevision': '22',
                                          'pages_to_scan': '2000',
                                          'sleep_millisecs': '20',
                                          'use_zero_pages': '1'})
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
        native = plugin._test_native_ksm_simulator
        native.sysfs.update({'run': '1', 'pages_to_scan': '1250',
                             'sleep_millisecs': '10', 'use_zero_pages': '0'})
        for state in native.services.values():
            state.update({'active': 'active', 'enabled': 'enabled'})
        with patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')):
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
        self.assertEqual({'enabled': True, 'scanning': True, 'pagesToScan': 1250,
                          'sleepMillis': 10, 'zeroPagesEnabled': False},
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
        readback.assert_called_once_with(command['policy']['ksm'], 19, None)
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
        readback.assert_called_once_with(command['policy']['ksm'], 20, None)
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
    def test_ksm_status_empty_or_old_revision_is_not_success(self):
        root = tempfile.mkdtemp(prefix='ksm-readback-')
        plugin = self._ksm_only_state_plugin(root)
        plugin.ksm_apply_timeout = 0
        plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
        plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
        command = {'desiredRevision': 9, 'operationUuid': 'ksm-readback',
                   'policy': {'ksm': {'enabled': True, 'pagesToScan': 1300,
                                      'sleepMillis': 25, 'zeroPagesEnabled': False}}}
        with patch.object(plugin, '_read_ksm_ack', return_value=None):
            with self.assertRaises(RuntimeError):
                plugin._apply_ksm_policy(command)
        stale = {'run': '1', 'configRevision': '8', 'pages_to_scan': '1300',
                 'sleep_millisecs': '25', 'use_zero_pages': '0'}
        with patch.object(plugin, '_read_ksm_ack', return_value=stale):
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
    def test_ksm_tuning_only_preserves_native_run_state_before_any_write(self):
        """Native sysfs writes tune KSM without changing an inactive run state."""
        for native_run in ('0', '1'):
            with self.subTest(native_run=native_run):
                root = tempfile.mkdtemp(prefix='native-ksm-preserve-run-')
                plugin = self._ksm_only_state_plugin(root)
                simulator = plugin._test_native_ksm_simulator
                plugin.KSM_CONF = os.path.join(root, 'ksmtuned.conf')
                plugin.KSM_LOCK = os.path.join(root, 'ksm.writer.lock')
                plugin.ksm_apply_timeout = 0
                simulator.sysfs.update({'run': native_run, 'pages_to_scan': '1250',
                                        'sleep_millisecs': '10', 'use_zero_pages': '0'})
                for unit_state in simulator.services.values():
                    unit_state['active'] = 'active' if native_run == '1' else 'inactive'
                command = {'hostUuid': 'host-1', 'operationUuid': 'native-tune-%s' % native_run,
                           'desiredRevision': 23,
                           'policy': {'ksm': {'pagesToScan': 1777,
                                              'sleepMillis': 25,
                                              'zeroPagesEnabled': True}}}
                before_services = copy.deepcopy(simulator.services)
                result = plugin._apply_ksm_policy(command)
                self.assertEqual(native_run, result['run'])
                self.assertEqual('23', result['configRevision'])
                self.assertEqual('1777', result['pages_to_scan'])
                self.assertEqual('25', result['sleep_millisecs'])
                self.assertEqual('1', result['use_zero_pages'])
                self.assertEqual(before_services, simulator.services,
                                 'tuning-only must not start, stop, enable, or disable services')

        root = tempfile.mkdtemp(prefix='native-ksm-unknown-service-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'native-tune-unknown',
                   'desiredRevision': 24,
                   'policy': {'ksm': {'pagesToScan': 1777, 'sleepMillis': 25}}}
        with patch.object(plugin, '_native_service_state', return_value=None), \
                patch.object(plugin, '_publish_ksm_config') as publish:
            with self.assertRaisesRegex(ValueError, 'KSM_NATIVE_SERVICE_STATE_UNKNOWN'):
                plugin._apply_ksm_policy(command)
        publish.assert_not_called()

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

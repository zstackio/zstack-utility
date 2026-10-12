import json
from unittest import TestCase
try:
    from mock import patch
except ImportError:
    from unittest.mock import patch

from kvmagent.plugins import prometheus


def qualified_vm(vm_uuid, metrics, cgroup_inode=101, start_time=22,
                 quality='source_memcg_inventory'):
    return {'quality': quality, 'identity': {
        'uuid': vm_uuid, 'host_boot_id': 'fixture-boot',
        'instance_generation': 'instance-1', 'cgroup_inode': cgroup_inode,
        'start_time': start_time}, 'metrics': metrics}


def find_vm_sample(families, name, vm_uuid):
    return next(sample for family in families for sample in family.samples
                if sample.name == name and sample.labels.get('vm_uuid') == vm_uuid)


class TestCollectMemoryOptimization(TestCase):
    def test_vm_sample_time_is_service_observation_not_scrape_time(self):
        report = {'schema_version': 2, 'observed_at': '2026-10-07T00:00:00.123456789Z',
                  'quality': 'atomic_inventory_identity_checked',
                  'host_boot_id': 'fixture-boot', 'device': '/dev/zram0',
                  'inventory': {'schema_version': 2, 'pool_generation': 3}, 'vms': {
                      'vm-1': qualified_vm('vm-1', {
                          'ram_original_bytes': 4096, 'ram_payload_bytes': 32,
                          'backend_committed_original_bytes': 0})}}
        families = prometheus.collect_memory_optimization_vm_accounting(report)
        self.assertAlmostEqual(1791331200.123456,
            find_vm_sample(families, 'host_zram_vm_sample_timestamp_seconds', 'vm-1').value,
            places=5)
        identity = find_vm_sample(families, 'host_zram_vm_identity_info', 'vm-1')
        self.assertEqual('fixture-boot', identity.labels['host_boot_id'])
        self.assertEqual('3', identity.labels['pool_generation'])
        self.assertEqual('instance-1', identity.labels['instance_generation'])
        report['observed_at'] = 'invalid'
        samples = [s.name for f in prometheus.collect_memory_optimization_vm_accounting(report) for s in f.samples]
        self.assertNotIn('host_zram_vm_sample_timestamp_seconds', samples)

    def test_vm_sample_time_accepts_rfc3339_offsets_without_fabricating_invalid_time(self):
        cases = (
            ('2026-10-07T00:00:00.123456789Z', 1791331200.1234567),
            ('2026-10-07T08:00:00.123456789+08:00', 1791331200.1234567),
            ('2026-10-06T18:30:00.5-05:30', 1791331200.5),
        )
        for observed_at, expected in cases:
            actual = prometheus._memory_observation_seconds(observed_at)
            self.assertAlmostEqual(expected, actual, places=5,
                                   msg='unexpected timestamp: %s' % observed_at)
        for observed_at in ('2026-10-07T00:00:00+99:00',
                            '2026-10-07T00:00:00+08:60',
                            '2026-10-07T00:00:00.123456789',
                            'not-a-time'):
            self.assertIsNone(prometheus._memory_observation_seconds(observed_at),
                              msg='invalid timestamp accepted: %s' % observed_at)

    def test_periodic_collector_reads_accounting_endpoint_without_manual_report_argument(self):
        report = {
            'schema_version': 2, 'observed_at': '2026-10-07T00:00:00Z',
            'quality': 'atomic_inventory_identity_checked',
            'host_boot_id': 'fixture-boot', 'device': '/dev/zram0',
            'inventory': {'schema_version': 2, 'pool_generation': 3, 'sequence': 4,
                          'tracking_requested_bytes': 8},
            'vms': {'vm-1': qualified_vm('vm-1', {
                'ram_original_bytes': 100, 'ram_payload_bytes': 40,
                'backend_committed_original_bytes': 0})},
            'total': {'ram_original_bytes': 100, 'ram_payload_bytes': 40},
        }

        class Response(object):
            status = 200
            def read(self, _limit):
                return json.dumps(report).encode('utf-8')

        class Connection(object):
            def __init__(self, path, timeout):
                self.path, self.timeout = path, timeout
                self.request_args = None
            def request(self, *args, **kwargs):
                self.request_args = (args, kwargs)
            def getresponse(self):
                return Response()
            def close(self):
                pass

        with patch.object(prometheus, '_MemoryServiceUnixHTTPConnection', Connection):
            families = prometheus.collect_memory_optimization_statistics()
        samples = {(sample.name, tuple(sorted(sample.labels.items()))): sample.value
                   for family in families for sample in family.samples}
        vm_sample = find_vm_sample(families, 'host_zram_vm_ram_original_bytes', 'vm-1')
        self.assertEqual(100, vm_sample.value)
        self.assertNotIn('memory_source', vm_sample.labels)
        self.assertEqual(8, samples[('host_zram_tracking_metadata_bytes',
                                     (('kind', 'reported_total'),))])
        self.assertEqual(3, samples[('host_zram_accounting_generation', ())])
        self.assertEqual(4, samples[('host_zram_accounting_sequence', ())])

    def test_abi2_service_report_exports_identity_qualified_vm_and_tracking_metrics(self):
        report = {
            'schema_version': 2,
            'observed_at': '2026-10-07T00:00:00Z',
            'quality': 'partial_vm_attribution',
            'host_boot_id': 'fixture-boot', 'device': '/dev/zram0',
            'inventory': {
                'schema_version': 2, 'pool_generation': 17, 'sequence': 9,
                'tracking_requested_bytes': 100,
                'persistent_metadata_bytes': 40,
                'dynamic_metadata_bytes': 60,
            },
            'vms': {
                'vm-good': qualified_vm('vm-good', {
                    'ram_original_bytes': 700, 'ram_payload_bytes': 200,
                    'backend_committed_original_bytes': 100},
                    quality='partial_unattributed_present'),
                'vm-unknown': qualified_vm('vm-unknown', None,
                                           quality='instance_unconfirmed'),
            },
            'total': {'ram_original_bytes': 1000, 'ram_payload_bytes': 300,
                      'backend_committed_original_bytes': 100},
        }
        families = prometheus.collect_memory_optimization_vm_accounting(report)
        samples = {(sample.name, tuple(sorted(sample.labels.items()))): sample.value
                   for family in families for sample in family.samples}
        self.assertEqual(700, find_vm_sample(
            families, 'host_zram_vm_ram_original_bytes', 'vm-good').value)
        self.assertEqual(200, find_vm_sample(
            families, 'host_zram_vm_payload_bytes', 'vm-good').value)
        for name in ('host_zram_vm_ram_original_bytes',
                     'host_zram_vm_payload_bytes',
                     'host_zram_vm_backend_original_bytes',
                     'host_zram_vm_sample_timestamp_seconds',
                     'host_zram_vm_identity_info'):
            self.assertEqual(find_vm_sample(
                families, 'host_zram_vm_ram_original_bytes', 'vm-good').labels,
                find_vm_sample(families, name, 'vm-good').labels)
        self.assertNotIn('vm-unknown', [sample.labels.get('vm_uuid')
                                       for family in families for sample in family.samples
                                       if sample.name == 'host_zram_vm_payload_bytes'])
        self.assertEqual(40, samples[('host_zram_tracking_metadata_bytes', (('kind', 'persistent'),))])
        self.assertEqual(60, samples[('host_zram_tracking_metadata_bytes', (('kind', 'dynamic'),))])
        self.assertNotIn(('host_zram_accounting_saved_bytes', ()), samples)

    def test_abi1_or_unavailable_report_is_explicit_and_never_filled_with_zero(self):
        families = prometheus.collect_memory_optimization_vm_accounting({
            'schema_version': 1, 'quality': 'unsupported', 'vms': {
                'vm-1': {'metrics': {'ram_payload_bytes': 0}}}})
        samples = {(sample.name, tuple(sorted(sample.labels.items()))): sample.value
                   for family in families for sample in family.samples}
        self.assertNotIn(('host_zram_vm_payload_bytes', (('vm_uuid', 'vm-1'),)), samples)
        self.assertIn(('host_zram_accounting_sample_info',
                       (('quality', 'unsupported'), ('schema_version', '1'))), samples)

    def test_accounting_sample_info_has_stable_labels_and_numeric_watermarks(self):
        families = prometheus.collect_memory_optimization_vm_accounting({
            'schema_version': 2, 'quality': 'ok',
            'inventory': {'schema_version': 2, 'pool_generation': 9, 'sequence': 101},
            'vms': {}})
        samples = {(sample.name, tuple(sorted(sample.labels.items()))): sample.value
                   for family in families for sample in family.samples}
        self.assertEqual(9, samples[('host_zram_accounting_generation', ())])
        self.assertEqual(101, samples[('host_zram_accounting_sequence', ())])
        self.assertIn(('host_zram_accounting_sample_info',
                       (('quality', 'ok'), ('schema_version', '2'))), samples)

    def owned_pool_values(self):
        # StockPool embeds Go's DeviceIdentity without JSON field tags. Keep
        # the actual on-disk casing, including fields unused by the collector.
        pool = {
            'identity': {
                'BootID': 'boot-one', 'Device': '/dev/zram0',
                'NodeInode': 1477089, 'NodeFS': 6, 'Rdev': 64256,
                'SysInode': 63985, 'SysFS': 21, 'DiskSize': 33677889536,
                'MemoryLimit': 8419471360, 'Algorithm': 'lzo',
            },
            'userspace_ownership_generation': 'a' * 64,
            'swap_uuid': 'f0f85875-188f-42c1-b5b0-02f838145643',
            'marker_sha256': 'b' * 64,
        }
        return {
            '/proc/sys/kernel/random/boot_id': 'boot-one',
            '/etc/zram-memory/config.json': '{"state_dir":"/owned"}',
            '/owned/stock-pool.json': json.dumps(pool),
            '/sys/block/zram0/disksize': '33677889536',
            '/sys/block/zram0/mm_stat': '81920 32768 40960 0 0 0 0',
            '/sys/kernel/mm/ksm/pages_sharing': '2',
            '/sys/kernel/mm/ksm/ksm_zero_pages': '3',
        }

    def test_real_stock_pool_record_exports_generation_and_savings(self):
        values = self.owned_pool_values()
        with patch.object(prometheus, 'PAGE_SIZE', 4096), \
                patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')), \
                patch.object(prometheus.os, 'listdir', return_value=['zram0']):
            epoch = prometheus._memory_optimization_epoch(['zram0'])
            families = prometheus.collect_memory_optimization_statistics()
        self.assertIsNotNone(epoch)
        self.assertEqual(epoch, int(float(epoch)))
        samples = {(s.name, tuple(sorted(s.labels.items()))): s.value
                   for f in families for s in f.samples}
        self.assertEqual(epoch, samples[('host_memory_optimization_generation', ())])
        self.assertEqual(8192, samples[('host_ksm_ordinary_saved_bytes', ())])
        self.assertEqual(12288, samples[('host_ksm_zero_saved_bytes', ())])
        self.assertEqual(40960, samples[('host_zram_saved_estimate_bytes', ())])
        self.assertEqual(61440, samples[('host_memory_saved_estimate_bytes', (('mechanism', 'total'),))])

    def test_device_field_compatibility_preserves_epoch(self):
        values = self.owned_pool_values()
        pool = json.loads(values['/owned/stock-pool.json'])
        with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
            real_epoch = prometheus._memory_optimization_epoch(['zram0'])
            self.assertIsNotNone(real_epoch)
            pool['identity']['device'] = pool['identity'].pop('Device')
            values['/owned/stock-pool.json'] = json.dumps(pool)
            self.assertEqual(real_epoch, prometheus._memory_optimization_epoch(['zram0']))
            pool['identity']['Device'] = pool['identity']['device']
            values['/owned/stock-pool.json'] = json.dumps(pool)
            self.assertEqual(real_epoch, prometheus._memory_optimization_epoch(['zram0']))

    def test_invalid_or_conflicting_pool_device_cannot_acquire_epoch(self):
        values = self.owned_pool_values()
        pool = json.loads(values['/owned/stock-pool.json'])
        identities = [None, [], 'invalid', {}, {'Device': None},
                      {'Device': ['/dev/zram0']}, {'Device': '/dev/zram1'},
                      {'Device': '/dev/zram0', 'device': '/dev/zram1'},
                      {'Device': None, 'device': '/dev/zram0'},
                      {'Device': '/dev/zram0', 'device': None}]
        with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
            for identity in identities:
                with self.subTest(identity=identity):
                    pool['identity'] = identity
                    values['/owned/stock-pool.json'] = json.dumps(pool)
                    self.assertIsNone(prometheus._memory_optimization_epoch(['zram0']))
            values['/owned/stock-pool.json'] = '{invalid'
            self.assertIsNone(prometheus._memory_optimization_epoch(['zram0']))

    def test_real_pool_epoch_changes_on_boot_or_rebuild_not_stats(self):
        values = self.owned_pool_values()
        pool = json.loads(values['/owned/stock-pool.json'])
        with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
            before = prometheus._memory_optimization_epoch(['zram0'])
            self.assertIsNotNone(before)
            values['/sys/block/zram0/mm_stat'] = '0 0 0 0 0 0 0'
            self.assertEqual(before, prometheus._memory_optimization_epoch(['zram0']))
            pool['userspace_ownership_generation'] = 'c' * 64
            values['/owned/stock-pool.json'] = json.dumps(pool)
            rebuilt = prometheus._memory_optimization_epoch(['zram0'])
            self.assertNotEqual(before, rebuilt)
            values['/proc/sys/kernel/random/boot_id'] = 'boot-two'
            self.assertNotEqual(rebuilt, prometheus._memory_optimization_epoch(['zram0']))
            values['/sys/block/zram1/disksize'] = '4096'
            self.assertIsNone(prometheus._memory_optimization_epoch(['zram0', 'zram1']))

    def test_real_pool_rebuild_during_scrape_withholds_incoherent_savings(self):
        values = self.owned_pool_values()
        pool = json.loads(values['/owned/stock-pool.json'])

        def read_file(path):
            if path.endswith('/mm_stat'):
                pool['userspace_ownership_generation'] = 'c' * 64
                values['/owned/stock-pool.json'] = json.dumps(pool)
            return values.get(path, '')

        with patch.object(prometheus.linux, 'read_file', side_effect=read_file), \
                patch.object(prometheus.os, 'listdir', return_value=['zram0']):
            families = prometheus.collect_memory_optimization_statistics()
        samples = {(s.name, tuple(sorted(s.labels.items()))): s.value
                   for f in families for s in f.samples}
        self.assertNotIn(('host_memory_optimization_generation', ()), samples)
        self.assertNotIn(('host_zram_saved_estimate_bytes', ()), samples)
        self.assertNotIn(('host_memory_saved_estimate_bytes', (('mechanism', 'total'),)), samples)
        self.assertEqual(0, samples[('host_memory_optimization_metric_quality',
                                     (('metric', 'total'), ('quality', 'epoch_changed')))])

    def test_missing_metrics_are_not_exported_as_zero(self):
        prometheus.PAGE_SIZE = 4096
        values = {
            '/sys/kernel/mm/ksm/pages_sharing': '10\n',
            '/sys/kernel/mm/ksm/ksm_zero_pages': '',
            '/sys/block/zram0/mm_stat': '100 40 50 0 0 0 0 0 0\n',
        }

        def read_file(path):
            return values.get(path, '')

        with patch.object(prometheus.linux, 'read_file', side_effect=read_file), patch.object(prometheus.os, 'listdir', return_value=['zram0']):
            families = prometheus.collect_memory_optimization_statistics()

        samples = {}
        for family in families:
            for sample in family.samples:
                samples[(sample.name, tuple(sorted(sample.labels.items())))] = sample.value

        self.assertEqual(40960, samples[('host_ksm_ordinary_saved_bytes', ())])
        self.assertNotIn(('host_ksm_zero_saved_bytes', ()), samples)

    def test_negative_ksm_counter_withholds_only_invalid_component_and_totals(self):
        for bad_counter, bad_mechanism, valid_mechanism, valid_bytes in (
                ('ksm_zero_pages', 'ksm_zero', 'ksm_ordinary', 8192),
                ('pages_sharing', 'ksm_ordinary', 'ksm_zero', 12288)):
            with self.subTest(counter=bad_counter):
                values = self.owned_pool_values()
                # The subtotal can stay positive even when a constituent is
                # invalid. Validate each native page counter before adding.
                values['/sys/kernel/mm/ksm/' + bad_counter] = '-1\n'
                with patch.object(prometheus, 'PAGE_SIZE', 4096), \
                        patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')), \
                        patch.object(prometheus.os, 'listdir', return_value=['zram0']):
                    families = prometheus.collect_memory_optimization_statistics()
                samples = {(s.name, tuple(sorted(s.labels.items()))): s.value
                           for f in families for s in f.samples}
                self.assertNotIn(('host_' + bad_mechanism + '_saved_bytes', ()), samples)
                self.assertEqual(valid_bytes, samples[('host_' + valid_mechanism + '_saved_bytes', ())])
                self.assertEqual(40960, samples[('host_zram_saved_estimate_bytes', ())])
                for mechanism in (bad_mechanism, 'ksm_total', 'total'):
                    self.assertNotIn(('host_memory_saved_estimate_bytes', (('mechanism', mechanism),)), samples)
                self.assertNotIn(('host_memory_optimization_metric_quality',
                                  (('metric', bad_mechanism), ('quality', 'observed'))), samples)
                for mechanism in ('ksm_total', 'total'):
                    self.assertEqual(0, samples[('host_memory_optimization_metric_quality',
                                                (('metric', mechanism), ('quality', 'partial')))])

    def test_zero_ksm_counters_are_valid_observations(self):
        values = self.owned_pool_values()
        values['/sys/kernel/mm/ksm/pages_sharing'] = '0\n'
        values['/sys/kernel/mm/ksm/ksm_zero_pages'] = '0\n'
        with patch.object(prometheus, 'PAGE_SIZE', 4096), \
                patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')), \
                patch.object(prometheus.os, 'listdir', return_value=['zram0']):
            families = prometheus.collect_memory_optimization_statistics()
        samples = {(s.name, tuple(sorted(s.labels.items()))): s.value
                   for f in families for s in f.samples}
        for mechanism in ('ksm_ordinary', 'ksm_zero', 'ksm_total'):
            self.assertEqual(0, samples[('host_memory_saved_estimate_bytes', (('mechanism', mechanism),))])
            self.assertEqual(1, samples[('host_memory_optimization_metric_quality',
                                        (('metric', mechanism), ('quality', 'observed')))])
        self.assertEqual(40960, samples[('host_memory_saved_estimate_bytes', (('mechanism', 'total'),))])

    def test_negative_zram_saving_is_preserved(self):
        prometheus.PAGE_SIZE = 4096
        values = {
            '/sys/kernel/mm/ksm/pages_sharing': '0\n',
            '/sys/kernel/mm/ksm/ksm_zero_pages': '0\n',
            '/sys/block/zram0/mm_stat': '100 80 120 0 0 0 0 0 0\n',
        }

        with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')), patch.object(prometheus.os, 'listdir', return_value=['zram0']):
            families = prometheus.collect_memory_optimization_statistics()

        samples = {(sample.name, tuple(sorted(sample.labels.items()))): sample.value
                   for family in families for sample in family.samples}
        self.assertEqual(-20, samples[('host_zram_saved_estimate_bytes', ())])

    def test_no_zram_still_exports_legacy_ksm_and_marks_partial(self):
        prometheus.PAGE_SIZE = 4096
        values = {
            '/sys/kernel/mm/ksm/pages_sharing': '2\n',
            '/sys/kernel/mm/ksm/ksm_zero_pages': '3\n',
            '/sys/kernel/mm/ksm/full_scans': '7\n',
            '/sys/block/zram0/mm_stat': '',
        }
        with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')), patch.object(prometheus.os, 'listdir', return_value=[]):
            families = prometheus.collect_memory_optimization_statistics()
        samples = {(sample.name, tuple(sorted(sample.labels.items()))): sample.value
                   for family in families for sample in family.samples}
        self.assertEqual(8192, samples[('host_ksm_ordinary_saved_bytes', ())])
        self.assertEqual(12288, samples[('host_ksm_zero_saved_bytes', ())])
        self.assertEqual(20480, samples[('host_memory_saved_estimate_bytes', (('mechanism', 'ksm_total'),))])

    def test_partial_zram_devices_do_not_export_total(self):
        prometheus.PAGE_SIZE = 4096
        values = {
            '/sys/kernel/mm/ksm/pages_sharing': '1\n',
            '/sys/kernel/mm/ksm/ksm_zero_pages': '1\n',
            '/sys/block/zram0/mm_stat': '100 40 50 0 0 0 0 0 0\n',
            '/sys/block/zram1/mm_stat': '',
        }
        with patch.object(prometheus.os, 'listdir', return_value=['zram0', 'zram1']):
            with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
                families = prometheus.collect_memory_optimization_statistics()
        samples = {(sample.name, tuple(sorted(sample.labels.items()))): sample.value
                   for family in families for sample in family.samples}
        self.assertEqual(0, samples[('host_memory_optimization_metric_quality',
                                     (('metric', 'zram'), ('quality', 'partial')))])
        self.assertNotIn(('host_memory_saved_estimate_bytes', (('mechanism', 'total'),)), samples)

    def test_device_inventory_failure_is_unknown_not_disabled_zero(self):
        values = {'/sys/kernel/mm/ksm/pages_sharing': '1', '/sys/kernel/mm/ksm/ksm_zero_pages': '1'}
        with patch.object(prometheus.os, 'listdir', side_effect=OSError('unreadable')), patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
            families = prometheus.collect_memory_optimization_statistics()
        samples = {(s.name, tuple(sorted(s.labels.items()))): s.value for f in families for s in f.samples}
        self.assertNotIn(('host_memory_saved_estimate_bytes', (('mechanism', 'total'),)), samples)
        self.assertNotIn(('host_zram_saved_estimate_bytes', ()), samples)

    def test_epoch_uses_boot_and_owned_pool_not_ksm_scan_count(self):
        values = {'/proc/sys/kernel/random/boot_id': 'boot-one', '/etc/zram-memory/config.json': '{"state_dir":"/owned"}',
                  '/sys/block/zram0/disksize': '4096', '/sys/block/zram1/disksize': '4096',
                  '/owned/stock-pool.json': '{"userspace_ownership_generation":"pool-one","identity":{"device":"/dev/zram0"}}'}
        with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
            before = prometheus._memory_optimization_epoch(['zram0'])
            values['/sys/kernel/mm/ksm/full_scans'] = '9999'
            self.assertEqual(before, prometheus._memory_optimization_epoch(['zram0']))
            values['/owned/stock-pool.json'] = '{"userspace_ownership_generation":"pool-two","identity":{"device":"/dev/zram0"}}'
            self.assertNotEqual(before, prometheus._memory_optimization_epoch(['zram0']))
            self.assertIsNone(prometheus._memory_optimization_epoch(['zram0', 'zram1']))

    def test_uninitialized_device_uses_boot_epoch_without_inventing_pool_ownership(self):
        values = {'/proc/sys/kernel/random/boot_id': 'boot-one', '/sys/block/zram0/disksize': '0'}
        with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
            self.assertEqual(prometheus._memory_optimization_epoch([]), prometheus._memory_optimization_epoch(['zram0']))
            values['/sys/block/zram0/disksize'] = '4096'
            self.assertIsNone(prometheus._memory_optimization_epoch(['zram0']))
            values['/sys/block/zram0/disksize'] = ''
            self.assertIsNone(prometheus._memory_optimization_epoch(['zram0']))

    def test_empty_device_scrape_exports_a_real_generation(self):
        values = {'/proc/sys/kernel/random/boot_id': 'boot-one', '/sys/block/zram0/disksize': '0',
                  '/sys/block/zram0/mm_stat': '0 0 0 0 0 0 0', '/sys/kernel/mm/ksm/pages_sharing': '0',
                  '/sys/kernel/mm/ksm/ksm_zero_pages': '0'}
        with patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')), patch.object(prometheus.os, 'listdir', return_value=['zram0']):
            families = prometheus.collect_memory_optimization_statistics()
        samples = {s.name: s.value for f in families for s in f.samples}
        self.assertIn('host_memory_optimization_generation', samples)

    def test_writeback_split_uses_same_abi2_inventory_and_does_not_use_io_counters(self):
        values = {
            '/proc/sys/kernel/mm/ksm/pages_sharing': '0',
            '/sys/kernel/mm/ksm/pages_sharing': '0',
            '/sys/kernel/mm/ksm/ksm_zero_pages': '0',
            '/sys/block/zram0/mm_stat': '1000 400 600 0 0 0 0',
        }
        report = {
            'schema_version': 2,
            'inventory': {'schema_version': 2},
            'total': {'backend_committed_original_bytes': 200},
            'vms': {},
        }
        with patch.object(prometheus.os, 'listdir', return_value=['zram0']), \
                patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
            families = prometheus.collect_memory_optimization_statistics(report)
        samples = {(s.name, tuple(sorted(s.labels.items()))): s.value
                   for f in families for s in f.samples}
        self.assertEqual(400, samples[('host_zram_saved_estimate_bytes', ())])
        self.assertEqual(400 - 200, samples[('host_zram_ordinary_saved_bytes', ())])
        self.assertEqual(200, samples[('host_zram_writeback_saved_bytes', ())])
        self.assertEqual(400 - 200,
                         samples[('host_memory_saved_estimate_bytes', (('mechanism', 'zram_ordinary'),))])
        self.assertEqual(200,
                         samples[('host_memory_saved_estimate_bytes', (('mechanism', 'zram_writeback'),))])

    def test_writeback_split_is_missing_when_inventory_is_absent_but_legacy_total_survives(self):
        values = {
            '/sys/kernel/mm/ksm/pages_sharing': '0',
            '/sys/kernel/mm/ksm/ksm_zero_pages': '0',
            '/sys/block/zram0/mm_stat': '1000 400 600 0 0 0 0',
        }
        with patch.object(prometheus.os, 'listdir', return_value=['zram0']), \
                patch.object(prometheus.linux, 'read_file', side_effect=lambda p: values.get(p, '')):
            families = prometheus.collect_memory_optimization_statistics({})
        samples = {(s.name, tuple(sorted(s.labels.items()))): s.value
                   for f in families for s in f.samples}
        self.assertIn(('host_zram_saved_estimate_bytes', ()), samples)
        self.assertNotIn(('host_zram_ordinary_saved_bytes', ()), samples)
        self.assertNotIn(('host_zram_writeback_saved_bytes', ()), samples)

    def test_per_vm_saved_bytes_is_signed_mechanism_delta(self):
        report = {
            'schema_version': 2, 'observed_at': '2026-10-07T00:00:00Z',
            'quality': 'atomic_inventory_identity_checked',
            'host_boot_id': 'fixture-boot', 'device': '/dev/zram0',
            'inventory': {'schema_version': 2, 'pool_generation': 7},
            'vms': {'vm-1': qualified_vm('vm-1', {
                'ram_original_bytes': 100, 'ram_payload_bytes': 140,
                'backend_committed_original_bytes': 20})},
        }
        families = prometheus.collect_memory_optimization_vm_accounting(report)
        samples = {(s.name, tuple(sorted(s.labels.items()))): s.value
                   for f in families for s in f.samples}
        self.assertEqual(-20, find_vm_sample(
            families, 'host_zram_vm_saved_bytes', 'vm-1').value)

    def test_uint64_identity_is_preserved_as_a_string_label(self):
        largest = 18446744073709551615
        report = {
            'schema_version': 2, 'observed_at': '2026-10-07T00:00:00Z',
            'quality': 'atomic_inventory_identity_checked',
            'host_boot_id': 'fixture-boot', 'device': '/dev/zram0',
            'inventory': {'schema_version': 2, 'pool_generation': 7},
            'vms': {'vm-1': qualified_vm('vm-1', {
                'ram_original_bytes': 100, 'ram_payload_bytes': 40,
                'backend_committed_original_bytes': 0}, cgroup_inode=largest,
                start_time=largest)},
        }
        families = prometheus.collect_memory_optimization_vm_accounting(report)
        sample = find_vm_sample(families, 'host_zram_vm_identity_info', 'vm-1')
        self.assertEqual(str(largest), sample.labels['cgroup_inode'])
        self.assertEqual(str(largest), sample.labels['start_time'])

    def test_memory_textfile_has_source_label_and_stable_vm_identity_on_every_series(self):
        report = {
            'schema_version': 2, 'observed_at': '2026-10-07T00:00:00Z',
            'quality': 'atomic_inventory_identity_checked',
            'host_boot_id': 'fixture-boot', 'device': '/dev/zram0',
            'inventory': {'schema_version': 2, 'pool_generation': 7},
            'vms': {'vm-1': qualified_vm('vm-1', {
                'ram_original_bytes': 100, 'ram_payload_bytes': 40,
                'backend_committed_original_bytes': 0})},
        }
        payload = prometheus._memory_textfile_payload(
            prometheus.collect_memory_optimization_vm_accounting(report))
        text = payload.decode('utf-8')
        for metric in ('host_zram_vm_ram_original_bytes',
                       'host_zram_vm_payload_bytes',
                       'host_zram_vm_backend_original_bytes',
                       'host_zram_vm_sample_timestamp_seconds',
                       'host_zram_vm_accounting_quality',
                       'host_zram_vm_identity_info'):
            self.assertIn(metric + '{', text)
        self.assertIn('memory_source="node_exporter"', text)
        self.assertIn('cgroup_inode="101"', text)
        self.assertIn('instance_generation="instance-1"', text)

    def test_node_exporter_textfile_argument_is_idempotent_and_removes_conflicts(self):
        original = ('--no-collector.cpufreq --collector.textfile.directory=/old/path '
                    '--no-collector.textfile')
        once = prometheus._node_exporter_textfile_arguments(original)
        twice = prometheus._node_exporter_textfile_arguments(once)
        expected = '--collector.textfile.directory=%s' % prometheus.MEMORY_TEXTFILE_DIRECTORY
        self.assertEqual(once, twice)
        self.assertEqual(1, once.count('--collector.textfile.directory='))
        self.assertNotIn('--no-collector.textfile', once)
        self.assertIn('--no-collector.cpufreq', once)
        self.assertTrue(once.endswith(expected))

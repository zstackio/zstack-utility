import os
import tempfile
import threading
from unittest import TestCase

try:
    from mock import patch
except ImportError:
    from unittest.mock import patch

from prometheus_client.core import GaugeMetricFamily

from kvmagent.plugins import prometheus


class TestMemoryTextfileExport(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='memory-textfile-')
        self.addCleanup(self.temp.cleanup)

    def test_atomic_replacement_never_leaves_partial_concurrent_content(self):
        directory = self.temp.name
        payloads = [letter.encode('ascii') * (1024 * 128) for letter in ('a', 'b')]
        threads = [threading.Thread(
            target=prometheus._atomic_write_memory_textfile,
            args=(directory, 'snapshot.prom', payload)) for payload in payloads]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        with open(os.path.join(directory, 'snapshot.prom'), 'rb') as stream:
            actual = stream.read()
        self.assertIn(actual, payloads)
        self.assertEqual([], [name for name in os.listdir(directory)
                              if name.startswith('.snapshot.prom-')])

    def test_collection_failure_does_not_replace_last_sample(self):
        path = os.path.join(self.temp.name, prometheus.MEMORY_TEXTFILE)
        old_snapshot = b'old-host-sample\nold-vm-sample\n'
        with open(path, 'wb') as stream:
            stream.write(old_snapshot)

        with patch.object(prometheus, 'collect_memory_optimization_statistics',
                          side_effect=IOError('source unavailable')):
            with self.assertRaises(IOError):
                prometheus.publish_memory_optimization_textfiles(self.temp.name)

        with open(path, 'rb') as stream:
            self.assertEqual(old_snapshot, stream.read())

    def test_vm_source_failure_keeps_original_vm_timestamp_and_rewrites_host(self):
        host_info = GaugeMetricFamily(
            'host_zram_accounting_sample_info', 'accounting source state',
            labels=['schema_version', 'quality'])
        host_info.add_metric(['unknown', 'unavailable'], 1)
        host_sample = GaugeMetricFamily('host_memory_sample', 'host snapshot')
        host_sample.add_metric([], 10)
        vm_sample = GaugeMetricFamily('host_zram_vm_saved_bytes', 'VM snapshot',
                                      labels=['vm_uuid', 'instance_generation'])
        vm_sample.add_metric(['vm-a', 'old-generation'], 99)
        path = os.path.join(self.temp.name, prometheus.MEMORY_TEXTFILE)
        old_vm_sample = (
            b'# HELP host_zram_vm_saved_bytes VM snapshot\n'
            b'# TYPE host_zram_vm_saved_bytes gauge\n'
            b'host_zram_vm_saved_bytes{vm_uuid="vm-a",instance_generation="old-generation"} 99.0\n')
        with open(path, 'wb') as stream:
            stream.write(b'old-host-sample\n' + old_vm_sample)

        with patch.object(prometheus, 'collect_memory_optimization_statistics',
                          return_value=[host_info, host_sample, vm_sample]):
            prometheus.publish_memory_optimization_textfiles(self.temp.name)

        with open(path, 'rb') as stream:
            text = stream.read().decode('utf-8')
        self.assertIn('host_zram_vm_saved_bytes{vm_uuid="vm-a",instance_generation="old-generation"} 99.0', text)
        host_text = text
        self.assertIn('host_memory_sample{memory_source="node_exporter"} 10.0', host_text)

    def test_valid_accounting_report_replaces_vm_file_with_source_and_identity(self):
        host_info = GaugeMetricFamily(
            'host_zram_accounting_sample_info', 'accounting source state',
            labels=['schema_version', 'quality'])
        host_info.add_metric(['2', 'atomic_inventory_identity_checked'], 1)
        vm_sample = GaugeMetricFamily(
            'host_zram_vm_saved_bytes', 'VM snapshot',
            labels=['vm_uuid', 'host_boot_id', 'device', 'pool_generation',
                    'instance_generation', 'cgroup_inode', 'start_time'])
        vm_sample.add_metric(['vm-a', 'boot-a', '/dev/zram0', '9', 'generation-a',
                              '18446744073709551615', '42'], 99)
        with patch.object(prometheus, 'collect_memory_optimization_statistics',
                          return_value=[host_info, vm_sample]):
            prometheus.publish_memory_optimization_textfiles(self.temp.name)

        path = os.path.join(self.temp.name, prometheus.MEMORY_TEXTFILE)
        with open(path, 'rb') as stream:
            text = stream.read().decode('utf-8')
        self.assertIn('memory_source="node_exporter"', text)
        self.assertIn('cgroup_inode="18446744073709551615"', text)
        self.assertIn('instance_generation="generation-a"', text)

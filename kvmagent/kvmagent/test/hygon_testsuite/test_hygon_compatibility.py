"""Hygon regression tests without a running KVM host.

Run with Python 2.7 and mock, prometheus_client, simplejson, and typing:
    python -m unittest discover -s kvmagent/kvmagent/test/hygon_testsuite -v
"""
import importlib
import json
import logging
import os
import sys
import types
import unittest

import mock
from prometheus_client.core import GaugeMetricFamily


def identity(func):
    return func


def unexpected_command(*args, **kwargs):
    raise AssertionError("unexpected host command: %r" % (args,))


def module(name, **attrs):
    result = types.ModuleType(name)
    result.__dict__.update(attrs)
    return result


def load_source_modules():
    # Import complete production modules. Stub only host/infrastructure
    # dependencies, retaining real response serialization and metric objects.
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
    boundaries = {}
    for name, path in [
            ('kvmagent', 'kvmagent/kvmagent'),
            ('kvmagent.plugins', 'kvmagent/kvmagent/plugins'),
            ('zstacklib', 'zstacklib/zstacklib'),
            ('zstacklib.utils', 'zstacklib/zstacklib/utils')]:
        boundaries[name] = module(name, __path__=[os.path.join(root, path)])

    for name in ['lvm', 'ceph', 'iproute', 'sizeunit', 'xmlobject', 'ovs', 'misc']:
        full_name = 'zstacklib.utils.' + name
        boundaries[full_name] = module(full_name)
    for name in ['yaml', 'pyudev', 'psutil']:
        boundaries[name] = module(name)

    log = module('zstacklib.utils.log', get_logger=logging.getLogger,
                 get_logfile_path=lambda: '', sensitive_fields=lambda *args: identity)
    boundaries.update({
        'zstacklib.utils.log': log,
        'zstacklib.utils.plugin': module('zstacklib.utils.plugin', Plugin=object),
        'zstacklib.utils.daemon': module('zstacklib.utils.daemon', Daemon=object),
        'zstacklib.utils.http': module('zstacklib.utils.http', REQUEST_BODY='body',
                                      HttpServer=type('HttpServer', (object,), {})),
        'zstacklib.utils.linux': module('zstacklib.utils.linux', HOST_ARCH='x86_64',
                                       is_virtual_machine=lambda: False,
                                       read_file_lines=unexpected_command),
        'zstacklib.utils.qemu': module('zstacklib.utils.qemu', get_path=lambda: '/usr/bin/qemu-kvm'),
        'zstacklib.utils.lock': module('zstacklib.utils.lock', lock=lambda *args: identity,
                                      file_lock=lambda *args: identity),
        'zstacklib.utils.thread': module('zstacklib.utils.thread', AsyncThread=identity),
        'zstacklib.utils.iptables': module('zstacklib.utils.iptables', get_iptables_cmd=lambda: 'iptables'),
        'zstacklib.utils.ebtables': module('zstacklib.utils.ebtables', get_ebtables_cmd=lambda: 'ebtables'),
        'zstacklib.utils.shell': module('zstacklib.utils.shell', run=unexpected_command,
                                       run_without_log=unexpected_command),
        'zstacklib.utils.ip': module('zstacklib.utils.ip', get_nic_supported_max_speed=unexpected_command,
                                    get_nic_driver_type=unexpected_command,
                                    get_host_physicl_nics=unexpected_command),
        'zstacklib.utils.report': module('zstacklib.utils.report', Report=object),
        'zstacklib.utils.misc': module('zstacklib.utils.misc', isMiniHost=lambda: False,
                                      isHyperConvergedHost=lambda: False),
        'kvmagent.plugins.vm_plugin': module('kvmagent.plugins.vm_plugin', LibvirtAutoReconnect=identity),
        'kvmagent.plugins.imagestore': module('kvmagent.plugins.imagestore', ImageStoreClient=object),
        'zstacklib.utils.bash': module('zstacklib.utils.bash', in_bash=identity,
                                      bash_roe=unexpected_command, bash_ro=unexpected_command,
                                      bash_r=unexpected_command, bash_o=lambda *args: '',
                                      log=log, json=json),
    })
    source_names = ['zstacklib.utils.jsonobject', 'zstacklib.utils.gpu',
                    'zstacklib.utils.pci', 'kvmagent.kvmagent',
                    'kvmagent.plugins.host_plugin', 'kvmagent.plugins.prometheus']
    for name, stub in boundaries.items():
        parent, _, attribute = name.rpartition('.')
        if parent in boundaries:
            setattr(boundaries[parent], attribute, stub)
    with mock.patch.dict(sys.modules, boundaries):
        for name in source_names:
            sys.modules.pop(name, None)
        loaded = [importlib.import_module(name) for name in source_names]
    return loaded


class TestHygonCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jsonobject, cls.gpu, cls.pci, cls.agent, cls.host, cls.prometheus = load_source_modules()

    def setUp(self):
        self.prometheus.gpu_devices = {'HY': set()}
        self.prometheus.hw_status_abnormal_list_record['gpu'] = set()
        with mock.patch.object(self.host.shell, 'run', return_value=1):
            self.plugin = self.host.HostPlugin()

    def collect(self, fields):
        card = {'Serial Number': 'K100-001', 'PCI Bus': '0000:AB:00.0',
                'Average Graphics Package Power (W)': '120',
                'Temperature (Sensor junction) (C)': 45}
        card.update(fields)
        return self.collect_cards({'card0': card})[0]

    def collect_cards(self, cards):
        pci_commands = []
        def command(cmd):
            if cmd.startswith('lspci '):
                pci_commands.append(cmd)
                return 0, 'Co-processor: Haiguang Device (rev 01)'
            self.assertEqual(cmd, 'hy-smi --showuse --showmemuse  --showpower --showtemp --showserial --showbus --json')
            self.assertNotIn('--showfan', cmd)
            return 0, json.dumps(cards)

        with mock.patch.object(self.prometheus.shell, 'run_without_log', return_value=0), \
                mock.patch.object(self.prometheus, 'bash_ro', side_effect=command):
            metrics = self.prometheus.collect_hy_gpu_status()
        for metric in metrics:
            self.assertIsInstance(metric, GaugeMetricFamily)
        return dict((metric.name, metric.samples) for metric in metrics), pci_commands

    def live_card(self, address):
        return {'PCI Bus': address, 'Serial Number': 'TRYQ160016040601',
                'Average Graphics Package Power (W)': '136.0',
                'Temperature (Sensor junction) (C)': '75.0',
                'HCU use (%)': '0.0', 'HCU memory use (%)': '0',
                'Available memory size (MiB)': '65497',
                'Max Graphics Package Power (W)': '350.0'}

    def test_live_pci_address_formats(self):
        for address in ['0000:3f:00.0', '00000000:3F:00.0',
                        '0000:3f:00.0 --> SN: TRYQ160016040601',
                        ' \t0000:3F:00.0 --> SN: TRYQ160016040601 \n']:
            metrics, commands = self.collect_cards({'card0': self.live_card(address)})
            for samples in metrics.values():
                for sample in samples:
                    self.assertEqual(sample[1]['pci_device_address'], '0000:3f:00.0')
            self.assertEqual(metrics['host_gpu_utilization'][0][2], 0.0)
            self.assertEqual(metrics['host_gpu_memory_utilization'][0][2], 0.0)
            self.assertEqual(metrics['host_gpu_power_draw'][0][2], 136.0)
            self.assertEqual(metrics['host_gpu_temperature'][0][2], 75.0)
            self.assertEqual(metrics['host_gpu_fan_speed'], [])
            self.assertEqual(commands, ['lspci -s 0000:3f:00.0'])
            self.assertEqual(self.prometheus.gpu_devices['HY'],
                             set([('0000:3f:00.0', 'TRYQ160016040601')]))
            addon = self.gpu.parse_hy_gpu_output(json.dumps({'card0': self.live_card(address)}))
            self.assertEqual(addon, [{'pciAddress': '0000:3f:00.0', 'memory': '65497 MiB',
                                      'power': '350.0', 'serialNumber': 'TRYQ160016040601'}])

    def test_invalid_pci_addresses_skip_only_the_bad_card(self):
        invalid = [None, 42, '', '--help', 'prefix 0000:3f:00.0',
                   '0000:3f:20.0', '0000:3f:00.8', '00010000:3f:00.0',
                   '0000:3f:00.0 --> invalid', '0000:3f:00.0; echo unsafe']
        cards = [self.live_card(address) for address in invalid]
        missing = self.live_card(None)
        del missing['PCI Bus']
        cards.append(missing)
        for invalid_card in cards:
            healthy = self.live_card('0000:3f:00.0')
            metrics, commands = self.collect_cards({'card0': invalid_card, 'card1': healthy})
            self.assertEqual(len(metrics['host_gpu_utilization']), 1)
            self.assertEqual(commands, ['lspci -s 0000:3f:00.0'])
            self.assertEqual(self.prometheus.gpu_devices['HY'],
                             set([('0000:3f:00.0', 'TRYQ160016040601')]))
            addon = self.gpu.parse_hy_gpu_output(json.dumps({'card0': invalid_card, 'card1': healthy}))
            self.assertEqual(len(addon), 1)
            self.assertEqual(addon[0]['pciAddress'], '0000:3f:00.0')

    def test_non_dictionary_card_data_does_not_hide_healthy_cards(self):
        healthy = self.live_card('0000:3f:00.0')
        expected = [{'pciAddress': '0000:3f:00.0', 'memory': '65497 MiB',
                     'power': '350.0', 'serialNumber': 'TRYQ160016040601'}]
        for invalid_card in [None, False, 42, 3.5, 'invalid', [], ['invalid']]:
            # Cover both layouts independently of Python 2 dict iteration order.
            for cards in [{'card0': invalid_card, 'card1': healthy},
                          {'card0': healthy, 'card1': invalid_card}]:
                addon = self.gpu.parse_hy_gpu_output(json.dumps(cards))
                self.assertEqual(addon, expected, cards)

    def test_non_dictionary_card_data_does_not_hide_healthy_metrics(self):
        healthy = self.live_card('0000:3f:00.0')
        healthy.update({'HCU use (%)': '65', 'HCU memory use (%)': '25'})
        for invalid_card in [None, False, 42, 3.5, 'invalid', [], ['invalid']]:
            for cards in [{'card0': invalid_card, 'card1': healthy},
                          {'card0': healthy, 'card1': invalid_card}]:
                self.prometheus.gpu_devices = {'HY': set()}
                metrics, commands = self.collect_cards(cards)
                for name, expected in [('host_gpu_utilization', 65.0),
                                       ('host_gpu_memory_utilization', 25.0),
                                       ('host_gpu_power_draw', 136.0),
                                       ('host_gpu_temperature', 75.0),
                                       ('host_gpu_status', 1)]:
                    self.assertEqual(len(metrics[name]), 1, cards)
                    self.assertEqual(metrics[name][0][2], expected, cards)
                    self.assertEqual(metrics[name][0][1]['pci_device_address'],
                                     '0000:3f:00.0')
                self.assertEqual(commands, ['lspci -s 0000:3f:00.0'])
                self.assertEqual(self.prometheus.gpu_devices['HY'],
                                 set([('0000:3f:00.0', 'TRYQ160016040601')]))

    def assert_utilization(self, fields, utilization, memory):
        metrics = self.collect(fields)
        for metric, expected in [('host_gpu_utilization', utilization),
                                 ('host_gpu_memory_utilization', memory)]:
            self.assertEqual(len(metrics[metric]), 1, (fields, metric, metrics[metric]))
            self.assertEqual(metrics[metric][0][2], expected, fields)
            self.assertEqual(metrics[metric][0][1]['pci_device_address'], '0000:ab:00.0')
        self.assertEqual(metrics['host_gpu_power_draw'][0][2], 120)
        self.assertEqual(metrics['host_gpu_temperature'][0][2], 45)
        self.assertEqual(metrics['host_gpu_status'][0][2], 1)
        self.assertEqual(metrics['host_gpu_power_draw'][0][1]['gpu_serial'], 'K100-001')

    def test_dcu_values_including_numeric_zero(self):
        for value in [0, 0.0, '0', 35, '35.5']:
            self.assert_utilization({'DCU use (%)': value, 'DCU memory use (%)': value},
                                    float(value), float(value))

    def test_hcu_values_including_numeric_zero(self):
        for value in [0, 0.0, '0', 35, '35.5']:
            self.assert_utilization({'HCU use (%)': value, 'HCU memory use (%)': value},
                                    float(value), float(value))

    def test_dcu_zero_takes_precedence_over_hcu(self):
        self.assert_utilization({'DCU use (%)': 0, 'DCU memory use (%)': 0.0,
                                 'HCU use (%)': 42, 'HCU memory use (%)': 43}, 0, 0)

    def test_empty_dcu_values_fall_back_to_hcu(self):
        for value in [None, '']:
            self.assert_utilization({'DCU use (%)': value, 'DCU memory use (%)': value,
                                     'HCU use (%)': 42, 'HCU memory use (%)': 43}, 42, 43)

    def test_missing_or_na_metrics_do_not_hide_other_metrics(self):
        for fields in [{}, {'DCU use (%)': 'N/A', 'DCU memory use (%)': 'N/A',
                           'Fan speed (%)': 'N/A'}]:
            metrics = self.collect(fields)
            self.assertEqual(metrics['host_gpu_utilization'], [])
            self.assertEqual(metrics['host_gpu_memory_utilization'], [])
            self.assertEqual(metrics['host_gpu_fan_speed'], [])
            self.assertEqual(metrics['host_gpu_power_draw'][0][2], 120)

    def test_supported_fan_value(self):
        metrics = self.collect({'Fan speed (%)': 35})
        self.assertEqual(metrics['host_gpu_fan_speed'][0][2], 35)

    def test_missing_hy_smi_and_failed_collection(self):
        with mock.patch.object(self.prometheus.shell, 'run_without_log', return_value=1), \
                mock.patch.object(self.prometheus, 'bash_ro') as command:
            metrics = self.prometheus.collect_hy_gpu_status()
            self.assertTrue(all(not metric.samples for metric in metrics))
            command.assert_not_called()
        with mock.patch.object(self.prometheus.shell, 'run_without_log', return_value=0), \
                mock.patch.object(self.prometheus, 'bash_ro', return_value=(1, 'unsupported query')):
            metrics = self.prometheus.collect_hy_gpu_status()
            self.assertTrue(all(not metric.samples for metric in metrics))

    def classify(self, vendor, pci_class='Co-processor [0b40]', config=None):
        output = 'Slot:\t0000:81:00.0\nClass:\t%s\nVendor:\t%s\nDevice:\tDevice [6200]\n' % (pci_class, vendor)
        response = self.host.GetPciDevicesResponse()
        with mock.patch.object(self.host, 'bash_roe', return_value=(0, output, '')) as command, \
                mock.patch.object(self.host.linux, 'read_file_lines', return_value=config or []), \
                mock.patch.object(self.plugin, '_collect_gpu_addoninfo'), \
                mock.patch.object(self.plugin, '_get_vfio_mdev_info', return_value=False), \
                mock.patch.object(self.plugin, '_get_sriov_info', return_value=False), \
                mock.patch.object(self.pci, 'get_pci_resources', return_value={}):
            self.plugin._collect_format_pci_device_info(response)
            command.assert_called_once_with('lspci -Dmmnnv')
        self.assertTrue(response.success)
        self.assertEqual(len(response.pciDevicesInfo), 1)
        return response.pciDevicesInfo[0]

    def test_k100_numeric_and_named_vendor(self):
        for vendor in ['Device [1d94]', 'Haiguang [1d94]']:
            device = self.classify(vendor)
            self.assertEqual(device.vendor, 'Haiguang')
            self.assertEqual(device.vendorId, '1d94')
            self.assertEqual(device.type, 'GPU_Co_Processor')
            self.assertTrue(self.pci.is_gpu(device.type))

    def test_unknown_coprocessor_is_generic(self):
        device = self.classify('Device [1234]')
        self.assertEqual(device.type, 'Generic')
        self.assertNotEqual(device.vendor, 'Haiguang')
        self.assertFalse(self.pci.is_gpu(device.type))

    def test_unrelated_processing_accelerator_mapping_preserves_k100_type(self):
        device = self.classify('Device [1d94]', config=['Processing accelerators: Custom accelerator'])
        self.assertEqual(device.type, 'GPU_Co_Processor')

    def test_unrelated_mapping_preserves_unknown_vendor_type(self):
        device = self.classify('Device [1234]', config=['Processing accelerators: Custom accelerator'])
        self.assertEqual(device.type, 'Generic')

    def test_matching_class_mapping_and_existing_gpu_classes(self):
        device = self.classify('Device [1d94]', 'Custom coprocessor [0b40]',
                               ['Co-processor: Custom coprocessor'])
        self.assertEqual(device.type, 'GPU_Co_Processor')
        device = self.classify('Device [1234]', 'Custom accelerator [1200]',
                               ['Processing accelerators: Custom accelerator'])
        self.assertEqual(device.type, 'GPU_Processing_Accelerators')
        for pci_class, expected in [('3D controller [0302]', 'GPU_3D_Controller'),
                                    ('VGA compatible controller [0300]', 'GPU_Video_Controller')]:
            self.assertEqual(self.classify('Haiguang [1d94]', pci_class).type, expected)

    def reload(self, vendor, result):
        request = {self.host.http.REQUEST_BODY: json.dumps({'pciDeviceAddress': '0000:81:00.0', 'vendor': vendor})}
        with mock.patch.object(self.host, 'bash_roe', return_value=result) as command:
            response = self.jsonobject.loads(self.plugin.reload_device_driver_on_host(request))
        return response, command

    def test_driver_reload_success_without_showbus_guard(self):
        response, command = self.reload('Haiguang', (0, 'loaded', ''))
        self.assertTrue(response.success)
        self.assertEqual(response.error, '')
        command.assert_called_once_with('hy-smi --unloaddriver && hy-smi --loaddriver')

    def test_driver_reload_failures(self):
        for code in [1, 127]:
            response, command = self.reload('Haiguang', (code, 'unload failed', 'driver error'))
            self.assertFalse(response.success)
            self.assertIn('0000:81:00.0', response.error)
            self.assertIn('unload failed', response.error)
            self.assertIn('driver error', response.error)
            command.assert_called_once_with('hy-smi --unloaddriver && hy-smi --loaddriver')

    def test_non_haiguang_driver_reload_remains_noop(self):
        response, command = self.reload('NVIDIA', (0, '', ''))
        self.assertTrue(response.success)
        command.assert_not_called()


if __name__ == '__main__':
    unittest.main()

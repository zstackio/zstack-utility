# -*- coding: utf-8 -*-

import json
import os
import unittest

import jsonschema

from zstacklib.gpu_runtime_inventory import (
    RuntimeInventoryError,
    build_unsupported_runtime_inventory,
    build_nvidia_runtime_inventory,
    get_nvidia_runtime_inventory_cmd,
    get_nvidia_topology_cmd,
    parse_nvidia_runtime_query_output,
    runtime_inventory_to_legacy_pci_devices,
)


class TestRuntimeInventory(unittest.TestCase):

    def setUp(self):
        self.fixture_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        self.contract_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            '..', '..', '..', '..', '..',
            'baremetal-runtime-agent', 'contracts'))

    def test_nvidia_runtime_commands_are_available_without_vendor_plugins(self):
        self.assertEqual(
            'nvidia-smi --query-gpu=gpu_uuid,gpu_bus_id,memory.total,'
            'power.limit,gpu_serial,driver_version,name,index '
            '--format=csv,noheader',
            get_nvidia_runtime_inventory_cmd())
        self.assertEqual('nvidia-smi topo -m', get_nvidia_topology_cmd())

    def test_build_nvidia_runtime_inventory_matches_frozen_fixture(self):
        with open(os.path.join(self.fixture_dir, 'nvidia-runtime-query.txt'), 'r') as stream:
            query_output = stream.read()
        with open(os.path.join(self.fixture_dir, 'nvidia-topology.txt'), 'r') as stream:
            topology_output = stream.read()
        with open(os.path.join(
                self.contract_dir,
                'fixtures',
                'nvidia-dual-gpu',
                'gpu-inventory.valid.json'), 'r') as stream:
            expected = json.load(stream)
        with open(os.path.join(self.contract_dir, 'gpu-inventory-v1.schema.json'), 'r') as stream:
            schema = json.load(stream)

        inventory = build_nvidia_runtime_inventory(
            target_uuid='bm2-instance-001',
            observation_generation=42,
            observed_at='2026-08-14T02:00:00Z',
            valid_until='2026-08-14T02:02:00Z',
            collector_version='5.5.32',
            boot_id='11111111-2222-3333-4444-555555555555',
            query_output=query_output,
            topology_output=topology_output,
            pci_device_facts={
                '0000:3b:00.0': {
                    'vendorId': '10de',
                    'deviceId': '20b2',
                    'subsystemVendorId': '10de',
                    'subsystemDeviceId': '1533',
                    'iommuGroup': 61,
                    'numaNode': 0,
                    'dedicatedDeviceNodes': [
                        {'path': '/dev/nvidia0', 'major': 195, 'minor': 0}
                    ],
                    'sharedDeviceNodes': [
                        {'path': '/dev/nvidiactl', 'major': 195, 'minor': 255},
                        {'path': '/dev/nvidia-uvm', 'major': 511, 'minor': 0}
                    ],
                    'driverLoaded': True,
                    'driverReady': True,
                    'extensions': {'migMode': 'Disabled'}
                },
                '0000:af:00.0': {
                    'vendorId': '10de',
                    'deviceId': '20b2',
                    'subsystemVendorId': '10de',
                    'subsystemDeviceId': '1533',
                    'iommuGroup': 122,
                    'numaNode': 1,
                    'dedicatedDeviceNodes': [
                        {'path': '/dev/nvidia1', 'major': 195, 'minor': 1}
                    ],
                    'sharedDeviceNodes': [
                        {'path': '/dev/nvidiactl', 'major': 195, 'minor': 255},
                        {'path': '/dev/nvidia-uvm', 'major': 511, 'minor': 0}
                    ],
                    'driverLoaded': True,
                    'driverReady': True,
                    'extensions': {'migMode': 'Disabled'}
                }
            },
            gpu_specs={
                'GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee': {
                    'uuid': 'gpu-spec-a100-80g',
                    'name': 'A100 80GB'
                },
                'GPU-ffffffff-1111-2222-3333-444444444444': {
                    'uuid': 'gpu-spec-a100-80g',
                    'name': 'A100 80GB'
                }
            })

        jsonschema.validate(inventory, schema)
        self.assertEqual(expected, inventory)
        self.assertEqual('VendorCli', inventory['topology']['source'])
        self.assertEqual('Succeeded', inventory['source']['probes'][0]['status'])
        self.assertEqual('550.54.15', inventory['source']['probes'][0]['version'])
        legacy_devices = runtime_inventory_to_legacy_pci_devices(inventory)
        addon_info = legacy_devices[0]['addonInfo']
        self.assertEqual('400.0 W', addon_info['power'])
        self.assertEqual(42, addon_info['inventoryGeneration'])
        self.assertEqual(True, addon_info['driverReady'])
        self.assertEqual('550.54.15', addon_info['driverVersion'])
        self.assertEqual(
            'nvidia:GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
            addon_info['hardwareId'])
        self.assertEqual(
            {'kind': 'VendorUuid', 'value': 'GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'},
            json.loads(addon_info['authoritativeIdentity']))
        self.assertEqual(
            [{'path': '/dev/nvidia0', 'major': 195, 'minor': 0}],
            json.loads(addon_info['dedicatedDeviceNodes']))
        self.assertEqual(
            [
                {'path': '/dev/nvidiactl', 'major': 195, 'minor': 255},
                {'path': '/dev/nvidia-uvm', 'major': 511, 'minor': 0}
            ],
            json.loads(addon_info['sharedDeviceNodes']))
        self.assertEqual(0, addon_info['numaNode'])
        self.assertEqual('Complete', addon_info['topologyStatus'])
        self.assertEqual('VendorCli', addon_info['topologySource'])
        self.assertEqual('2026-08-14T02:00:00Z', addon_info['topologyObservedAt'])
        self.assertEqual('2026-08-14T02:02:00Z', addon_info['topologyValidUntil'])
        self.assertEqual(
            inventory['devices'][0]['visibility'],
            json.loads(addon_info['visibility']))
        persisted_topology = json.loads(
            addon_info['topology'])
        self.assertEqual(inventory['topology'], persisted_topology)
        self.assertTrue(persisted_topology['links'])

    def test_build_unsupported_runtime_inventory_is_explicit_and_empty(self):
        with open(os.path.join(self.contract_dir, 'gpu-inventory-v1.schema.json'), 'r') as stream:
            schema = json.load(stream)

        inventory = build_unsupported_runtime_inventory(
            target_uuid='inspection:192.168.0.10:623',
            observation_generation=43,
            observed_at='2026-08-14T03:00:00Z',
            valid_until='2026-08-14T03:02:00Z',
            collector_version='5.5.32',
            boot_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
            vendor_names=['MetaX'],
            reason='MetaX runtime inventory is unsupported until hardware qualification closes')

        jsonschema.validate(inventory, schema)
        self.assertEqual([], inventory['devices'])
        self.assertEqual('Unavailable', inventory['topology']['status'])
        self.assertEqual('None', inventory['topology']['source'])
        self.assertIn('MetaX', inventory['topology']['reason'])
        self.assertEqual(
            'Unavailable',
            inventory['source']['probes'][0]['status'])
        self.assertEqual(
            'PciDb',
            inventory['source']['probes'][1]['kind'])
        self.assertIn(
            'MetaX',
            inventory['source']['probes'][1]['message'])
        self.assertEqual(
            [],
            runtime_inventory_to_legacy_pci_devices(inventory))

    def test_parse_nvidia_runtime_query_rejects_missing_gpu_uuid(self):
        broken_output = (
            '0000:3B:00.0, 81920 MiB, 400.00 W, 1322519087621, 550.54.15, '
            'NVIDIA A100-SXM4-80GB, 0')
        self.assertRaises(
            RuntimeInventoryError,
            parse_nvidia_runtime_query_output,
            broken_output)


if __name__ == '__main__':
    unittest.main()

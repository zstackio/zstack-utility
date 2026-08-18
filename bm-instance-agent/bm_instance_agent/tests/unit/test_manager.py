import json
try:
    from unittest import mock
except ImportError:
    import mock

from bm_instance_agent import exception as bm_exception
from bm_instance_agent import manager
from bm_instance_agent.systems import base as driver_base
from bm_instance_agent.tests import base
from bm_instance_agent.tests.unit import fake


class TestManager(base.TestCase):

    def test_build_push_gateway_url_brackets_ipv6_host(self):
        self.assertEqual(
            'http://[2001:db8::20]:9092',
            manager.AgentManager.build_push_gateway_url('2001:db8::20'))
        self.assertEqual(
            'http://192.168.1.10:9092',
            manager.AgentManager.build_push_gateway_url('192.168.1.10'))

    @mock.patch('bm_instance_agent.systems.base.SystemDriverBase.ping')
    @mock.patch('bm_instance_agent.systems.base.SystemDriverBase.'
                'update_password')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    def test_ping_bm_uuid_not_corrent(self,
                                      mock_driv,
                                      mock_driv_update_password,
                                      mock_ping):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_driv_update_password.return_value = None
        mock_ping.return_value = None

        mgmt = manager.AgentManager()
        mgmt.ping(fake.BM_INSTANCE1)
        self.assertRaises(bm_exception.BmInstanceUuidConflict,
                          mgmt.update_password,
                          fake.BM_INSTANCE2,
                          'username',
                          'newPassword')
        manager.DRIVER = None

    @mock.patch('os.name', 'posix')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_centos_system(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = 'centos'
        mock_major.return_value = '8'
        mock_cpuinfo.return_value = fake.CPUINFO_X86

        mgmt = manager.AgentManager()
        self.assertEqual('centos', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('os.name', 'posix')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_centos_v7_x86(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = 'centos'
        mock_major.return_value = '7'
        mock_cpuinfo.return_value = fake.CPUINFO_X86

        mgmt = manager.AgentManager()
        self.assertEqual('centos_v7_x86', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('os.name', 'posix')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_centos_v7_arm(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = 'centos'
        mock_major.return_value = '7'
        mock_cpuinfo.return_value = fake.CPUINFO_ARM

        mgmt = manager.AgentManager()
        self.assertEqual('centos_v7_arm', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('os.name', 'posix')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_linux(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = 'ubuntu'
        mock_major.return_value = '18'
        mock_cpuinfo.return_value = fake.CPUINFO_X86

        mgmt = manager.AgentManager()
        self.assertEqual('linux', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('os.name', 'nt')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_windows_system(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = ''
        mock_major.return_value = ''
        mock_cpuinfo.return_value = fake.CPUINFO_X86

        mgmt = manager.AgentManager()
        self.assertEqual('windows', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    def test_inspect_exposes_gpu_inventory_and_legacy_addon_fields(self, mock_load_driver):
        mock_load_driver.return_value = driver_base.SystemDriverBase()
        mgmt = manager.AgentManager()
        gpu_inventory = {
            'schemaVersion': '1.0.0',
            'targetUuid': 'inspection:192.168.0.10:623',
            'observationGeneration': 42,
            'observedAt': '2026-08-14T02:00:00Z',
            'validUntil': '2026-08-14T02:02:00Z',
            'source': {
                'collector': 'zstack-utility',
                'collectorVersion': '5.5.32',
                'bootId': '11111111-2222-3333-4444-555555555555',
                'probes': []
            },
            'devices': [{
                'hardwareId': 'nvidia:GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                'identity': {
                    'kind': 'VendorUuid',
                    'value': 'GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
                },
                'vendor': 'NVIDIA',
                'model': 'NVIDIA A100-SXM4-80GB',
                'driver': {
                    'loaded': True,
                    'ready': True,
                    'version': '550.54.15',
                    'reason': None
                },
                'pci': {
                    'address': '0000:3b:00.0',
                    'vendorId': '10de',
                    'deviceId': '20b2',
                    'subsystemVendorId': '10de',
                    'subsystemDeviceId': '1533',
                    'iommuGroup': 61
                },
                'memoryBytes': 85899345920,
                'numaNode': 0,
                'dedicatedDeviceNodes': [
                    {'path': '/dev/nvidia0', 'major': 195, 'minor': 0}
                ],
                'sharedDeviceNodes': [
                    {'path': '/dev/nvidiactl', 'major': 195, 'minor': 255}
                ],
                'visibility': {
                    'CUDA_VISIBLE_DEVICES': 'GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
                }
            }],
            'topology': {
                'status': 'Complete',
                'observedAt': '2026-08-14T02:00:00Z',
                'validUntil': '2026-08-14T02:02:00Z',
                'source': 'VendorCli',
                'links': [{
                    'fromHardwareId': 'nvidia:GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                    'toHardwareId': 'nvidia:GPU-bbbbbbbb-cccc-dddd-eeee-ffffffffffff',
                    'kind': 'NvLink',
                    'direction': 'Bidirectional'
                }],
                'reason': None
            }
        }

        with mock.patch.object(mgmt, '_get_basic_info', return_value={'cpuNum': 64}), \
                mock.patch.object(mgmt, '_get_nic_info', return_value=[]), \
                mock.patch.object(mgmt, '_get_disk_info', return_value=[]), \
                mock.patch.object(mgmt, '_get_gpu_inventory', return_value=gpu_inventory), \
                mock.patch.object(mgmt, '_get_pci_info', return_value=[]):
            result = mgmt.inspect('eno1', '192.168.0.10', 623)

        hardware_info = json.loads(result['hardwareInfo'])
        self.assertEqual(gpu_inventory, hardware_info['gpuInventory'])
        addon_info = hardware_info['pciDevices'][0]['addonInfo']
        self.assertEqual(True, addon_info['driverReady'])
        self.assertEqual('550.54.15', addon_info['driverVersion'])
        self.assertEqual(
            'nvidia:GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
            addon_info['hardwareId'])
        self.assertEqual(42, addon_info['inventoryGeneration'])
        self.assertEqual(0, addon_info['numaNode'])
        self.assertEqual(
            {'kind': 'VendorUuid', 'value': 'GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'},
            json.loads(addon_info['authoritativeIdentity']))
        self.assertEqual(
            [{'path': '/dev/nvidia0', 'major': 195, 'minor': 0}],
            json.loads(addon_info['dedicatedDeviceNodes']))
        self.assertEqual(
            [{'path': '/dev/nvidiactl', 'major': 195, 'minor': 255}],
            json.loads(addon_info['sharedDeviceNodes']))
        self.assertEqual('Complete', addon_info['topologyStatus'])
        self.assertEqual('VendorCli', addon_info['topologySource'])
        self.assertEqual('2026-08-14T02:00:00Z', addon_info['topologyObservedAt'])
        self.assertEqual('2026-08-14T02:02:00Z', addon_info['topologyValidUntil'])
        self.assertEqual(
            {'CUDA_VISIBLE_DEVICES': 'GPU-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'},
            json.loads(addon_info['visibility']))

    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    def test_inspect_keeps_legacy_pci_devices_for_unsupported_gpu_inventory(self, mock_load_driver):
        mock_load_driver.return_value = driver_base.SystemDriverBase()
        mgmt = manager.AgentManager()
        unsupported_inventory = {
            'schemaVersion': '1.0.0',
            'targetUuid': 'inspection:192.168.0.10:623',
            'observationGeneration': 43,
            'observedAt': '2026-08-14T03:00:00Z',
            'validUntil': '2026-08-14T03:02:00Z',
            'source': {
                'collector': 'zstack-utility',
                'collectorVersion': '5.5.32',
                'bootId': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                'probes': [
                    {'name': 'vendor-runtime-query', 'kind': 'VendorCli', 'status': 'Unavailable'}
                ]
            },
            'devices': [],
            'topology': {
                'status': 'Unavailable',
                'observedAt': '2026-08-14T03:00:00Z',
                'validUntil': '2026-08-14T03:02:00Z',
                'source': 'None',
                'links': [],
                'reason': 'runtime inventory is unsupported for detected GPU vendors: MetaX'
            }
        }
        legacy_pci_devices = [{
            'name': 'MetaX_MTT_S80',
            'description': 'Processing accelerators: MetaX MTT S80',
            'vendorId': '1d1d',
            'vendor': 'MetaX',
            'deviceId': '1001',
            'device': 'MetaX MTT S80',
            'subVendorId': '',
            'subDeviceId': '',
            'pciDeviceAddress': '0000:65:00.0',
            'iommuGroup': '',
            'type': 'GPU_Processing_Accelerators',
            'addonInfo': {}
        }]

        with mock.patch.object(mgmt, '_get_basic_info', return_value={'cpuNum': 64}), \
                mock.patch.object(mgmt, '_get_nic_info', return_value=[]), \
                mock.patch.object(mgmt, '_get_disk_info', return_value=[]), \
                mock.patch.object(mgmt, '_get_gpu_inventory', return_value=unsupported_inventory), \
                mock.patch.object(mgmt, '_get_pci_info', return_value=legacy_pci_devices):
            result = mgmt.inspect('eno1', '192.168.0.10', 623)

        hardware_info = json.loads(result['hardwareInfo'])
        self.assertEqual(unsupported_inventory, hardware_info['gpuInventory'])
        self.assertEqual(legacy_pci_devices, hardware_info['pciDevices'])

    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    def test_get_gpu_inventory_returns_explicit_unsupported_inventory_for_metax(self, mock_load_driver):
        mock_load_driver.return_value = driver_base.SystemDriverBase()
        mgmt = manager.AgentManager()

        def fake_shell_cmd(command, *args, **kwargs):
            if command == 'which nvidia-smi':
                return 1, '', 'not found'
            if command == 'lspci -Dmmnn':
                return 0, (
                    'Slot:\t0000:65:00.0\n'
                    'Class:\tProcessing accelerators [1200]\n'
                    'Vendor:\tMetaX Corporation [1d1d]\n'
                    'Device:\tMetaX MTT S80 [1001]\n'
                ), ''
            return 1, '', 'unsupported command'

        with mock.patch('bm_instance_agent.manager.bm_utils.shell_cmd',
                        side_effect=fake_shell_cmd):
            inventory = mgmt._get_gpu_inventory('192.168.0.10', 623)

        self.assertEqual([], inventory['devices'])
        self.assertEqual('Unavailable', inventory['topology']['status'])
        self.assertEqual('None', inventory['topology']['source'])
        self.assertIn('MetaX', inventory['topology']['reason'])
        self.assertEqual('Unavailable', inventory['source']['probes'][0]['status'])
        self.assertEqual('PciDb', inventory['source']['probes'][1]['kind'])
        self.assertIn('MetaX', inventory['source']['probes'][1]['message'])

import json
import pytest
from mock import patch, MagicMock
from zstacklib.utils import jsonobject
from kvmagent.plugins import vm_plugin


@pytest.mark.skipif(vm_plugin.HOST_ARCH != "x86_64", reason="CPU vendor probing is x86-only")
class TestCpuVendorProbe(object):
    def _build_start_cmd(self, use_numa=False):
        cmd_dict = {
            'vmInstanceUuid': 'vm-uuid',
            'vmName': 'vm-name',
            'accountUuid': 'acct-uuid',
            'vmInternalId': 101,
            'hostManagementIp': '10.0.0.1',
            'useNuma': use_numa,
            'machineType': 'q35',
            'bootMode': 'UEFI',
            'imagePlatform': 'other',
            'architecture': None,
            'memory': 1024 * 1024,
            'cpuNum': 4,
            'maxVcpuNum': 8,
            'socketNum': 2,
            'cpuOnSocket': 2,
            'threadsPerCore': 1,
            'nestedVirtualization': 'host-model',
            'vmCpuModel': 'Icelake-Server',
            'vmCpuVendorId': 'GenuineIntel',
            'cpuHypervisorFeature': False,
            'x2apic': False,
            'kvmHiddenState': True,
            'vmPortOff': True,
            'emulateHyperV': True,
            'hypervClock': True,
            'vendorId': 'zstack',
            'MemAccess': 'shared',
            'useHugePage': True,
            'noSharePages': True,
            'useBootMenu': True,
            'bootMenuSplashTimeout': 5,
            'systemSerialNumber': 'SERIAL',
            'chassisAssetTag': 'ASSET',
            'oemStrings': ['oem1', 'oem2'],
            'clock': 'localtime',
            'clockTrack': None,
            'consolePassword': 'secret',
            'consoleMode': 'spice',
            'spiceChannels': ['main'],
            'spiceStreamingMode': 'filter',
            'videoType': 'qxl',
            'VDIMonitorNumber': 2,
            'qxlMemory': {'ram': 65536, 'vram': 65536, 'vgamem': 16384},
            'soundType': None,
            'suspendToDisk': True,
            'suspendToRam': False,
            'additionalQmp': True,
            'qemu64BitPciMmioSetup': True,
            'useColoBinary': False,
            'coloPrimary': False,
            'coloSecondary': False,
            'isApplianceVm': False,
            'pciePortNums': 2,
            'predefinedPciBridgeNum': 1,
            'memBalloon': {
                'deviceAddress': {
                    'domain': '0x0000',
                    'bus': '0x00',
                    'slot': '0x04',
                    'function': '0x0',
                }
            },
            'rootVolume': {
                'deviceId': 0,
                'deviceType': 'file',
                'installPath': '/path/root.qcow2',
                'cacheMode': 'none',
                'useVirtio': True,
                'useVirtioSCSI': False,
                'volumeUuid': 'vol-root',
                'wwn': 'wwn-root',
                'shareable': False,
                'multiQueues': '4',
                'ioThreadId': 2,
                'bootOrder': 1,
            },
            'dataVolumes': [
                {
                    'deviceId': 1,
                    'deviceType': 'file',
                    'installPath': '/path/data1.qcow2',
                    'cacheMode': 'none',
                    'useVirtio': False,
                    'useVirtioSCSI': False,
                    'volumeUuid': 'vol-data1',
                    'shareable': True,
                },
                {
                    'deviceId': 2,
                    'deviceType': 'ceph',
                    'installPath': 'ceph://pool/vol2',
                    'useVirtio': True,
                    'useVirtioSCSI': True,
                    'volumeUuid': 'vol-data2',
                    'wwn': 'wwn-data2',
                    'secretUuid': 'ceph-secret',
                    'monInfo': [{'hostname': '10.0.0.2', 'port': 6789}],
                    'physicalBlockSize': 4096,
                    'shareable': True,
                },
                {
                    'deviceId': 3,
                    'deviceType': 'block',
                    'installPath': '/dev/sdb',
                    'useVirtio': True,
                    'useVirtioSCSI': False,
                    'volumeUuid': 'vol-data3',
                    'cacheMode': 'none',
                },
            ],
            'cacheVolumes': [],
            'cdRoms': [
                {
                    'deviceId': 0,
                    'isEmpty': True,
                    'bootOrder': 1,
                    'resourceUuid': 'cdrom-0',
                    'path': '',
                },
                {
                    'deviceId': 1,
                    'isEmpty': False,
                    'path': 'ceph://pool/iso',
                    'resourceUuid': 'cdrom-1',
                    'secretUuid': 'iso-secret',
                    'monInfo': [{'hostname': '10.0.0.3', 'port': 6789}],
                },
                {
                    'deviceId': 2,
                    'isEmpty': False,
                    'protocol': 'vhost',
                    'path': '/var/run/vhost.iso',
                    'resourceUuid': 'cdrom-2',
                },
            ],
            'nics': [
                {
                    'uuid': 'nic-1',
                    'type': 'VNIC',
                    'mac': '00:11:22:33:44:55',
                    'mtu': 1500,
                    'bridgeName': 'br0',
                    'nicInternalName': 'vnic101.0',
                    'cleanTraffic': True,
                    'ips': ['192.168.0.10'],
                    'useVirtio': True,
                    'driverType': 'virtio',
                    'vHostAddOn': {'queueNum': 2, 'rxBufferSize': 512, 'txBufferSize': 256},
                    'bootOrder': 1,
                    'state': 'disable',
                    'pci': {'type': 'pci', 'domain': '0x0000', 'bus': '0x00', 'slot': '0x03', 'function': '0x0'},
                },
                {
                    'uuid': 'nic-2',
                    'type': 'VF',
                    'mac': '00:11:22:33:44:66',
                    'mtu': 1500,
                    'bridgeName': 'br1',
                    'nicInternalName': 'vnic101.1',
                    'useVirtio': False,
                    'vHostAddOn': {'queueNum': 1, 'rxBufferSize': 1024, 'txBufferSize': 1024},
                    'pciDeviceAddress': '0000:00:05.0',
                },
                {
                    'uuid': 'nic-3',
                    'type': 'TFVNIC',
                    'mac': '00:11:22:33:44:77',
                    'mtu': 1500,
                    'nicInternalName': 'vnic101.2',
                    'l2NetworkUuid': 'l2-uuid',
                    'ipForTf': '10.0.0.10',
                },
            ],
            'addons': {
                'noConsole': False,
                'onCrash': 'preserve',
                'ioThreadNum': 1,
                'ioThreadPins': [{'ioThreadId': 1, 'pin': '0-3'}],
                'cpuPinning': [{'vCpu': 0, 'pCpuSet': '0'}],
                'emulatorPinning': '0-3',
                'qemuCommandLine': ['-smp', '2'],
                'qemuPath': None,
                'vhostSrcPath': None,
                'brMode': None,
                'useDataPlane': False,
                'VolumeQos': {'vol-root': {'totalBandwidth': 1024, 'totalIops': 100}},
                'NativeAio': False,
                'NicQos': {'nic-1': {'outboundBandwidth': 1024 * 8 * 1024, 'inboundBandwidth': 2048 * 8 * 1024}},
                'channel': {'socketPath': '/tmp/chan.sock', 'targetName': 'org.zstack.channel.0'},
                'channel_vr': {'socketPath': '/tmp/chan-vr.sock', 'targetName': 'org.zstack.vr.0'},
                'ceph_secret_key': None,
                'ceph_secret_uuid': None,
                'pciDevice': ['0000:00:01.0,'],
                'mdevDevice': ['11111111-1111-1111-1111-111111111111'],
                'storageDevice': [],
                'usbDevice': ['1:2:1d6b:0002:2.0:PassThrough:1234:127.0.0.1'],
                'panicIsa': True,
                'panicHyperv': True,
                'systemVirtioDriverDeviceType': None,
                'FIXED_CDROMS': None,
                'loaderRom': None,
                'userDefinedXmlHookScript': None,
                'userDefinedXml': None,
                'hygonMdevDevice': None,
                'l3mapping': None,
            },
        }
        addons = cmd_dict['addons']
        if use_numa:
            if isinstance(addons, dict):
                addons['numaNodes'] = []
        else:
            if isinstance(addons, dict):
                addons['numaNodes'] = [
                    {'nodeID': 0, 'hostNodeID': 0, 'cpus': '0-3', 'memorySize': 1024 * 1024, 'distance': [10, 20]}
                ]
        return jsonobject.loads(json.dumps(cmd_dict))

    def _build_start_vm_xml(self, cmd, bash_roe=None):
        with patch.object(vm_plugin.ovs, 'OvsDpdkSupportVnic', []), \
                patch.object(vm_plugin.linux, 'get_img_fmt', return_value='qcow2'), \
                patch.object(vm_plugin.pci, 'need_config_pcimmio', return_value=True), \
                patch.object(vm_plugin.pci, 'get_bars_max_addressable_memory', return_value=256), \
                patch.object(vm_plugin.linux, 'get_cpu_model', return_value=('GenuineIntel', 'Intel')), \
                patch.object(vm_plugin, 'is_hv_freq_supported', return_value=True), \
                patch.object(vm_plugin, 'is_hv_synic_supported', return_value=True), \
                patch.object(vm_plugin, 'is_ioapic_supported', return_value=True), \
                patch.object(vm_plugin, 'is_spice_tls', return_value=0), \
                patch.object(vm_plugin, 'is_spiceport_driver_supported', return_value=True), \
                patch.object(vm_plugin, 'notify_vrouter'), \
                patch.object(vm_plugin.VmPlugin, 'clean_vm_firmware_flash'), \
                patch.object(vm_plugin.bash, 'bash_roe', bash_roe or MagicMock(return_value=(0, '', ''))), \
                patch.object(vm_plugin.linux, 'VmUsbManager', return_value=MagicMock(request_slot=MagicMock(return_value=1))), \
                patch.object(vm_plugin.uuidhelper, 'to_full_uuid', side_effect=lambda value: value), \
                patch('os.path.exists', return_value=True):
            return vm_plugin.Vm.from_StartVmCmd(cmd).domain_xml

    def test_zstac_88044_cpu_vendor_probe_excludes_hostdev_only_from_probe_xml(self):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.nestedVirtualization = 'host-passthrough'
        cmd.vmCpuVendorId = 'AuthenticAMD'
        probe_xmls = []

        def capture_cpu_probe(command, *_args, **_kwargs):
            if 'domxml-to-native' not in command:
                return 0, '', ''
            probe_path = command.split('--xml ', 1)[1].split(' ', 1)[0]
            with open(probe_path) as probe_file:
                probe_xmls.append(probe_file.read())
            return 0, 'host,migratable=on', ''

        xml_str = self._build_start_vm_xml(
            cmd,
            MagicMock(side_effect=capture_cpu_probe),
        )

        assert len(probe_xmls) == 1
        probe_root = vm_plugin.etree.fromstring(probe_xmls[0])
        assert probe_root.findall("./devices/interface[@type='hostdev']") == []
        assert probe_root.findall('./devices/hostdev') == []
        assert probe_root.find("./devices/interface[@type='bridge']") is not None
        assert probe_root.find('./cpu/topology') is not None
        assert probe_root.find('./os/type').get('machine') == 'q35'

        final_root = vm_plugin.etree.fromstring(xml_str)
        vf_interfaces = final_root.findall("./devices/interface[@type='hostdev']")
        assert len(vf_interfaces) == 1
        primary_vf = next(
            interface
            for interface in vf_interfaces
            if interface.find('mac').get('address') == '00:11:22:33:44:66'
        )
        assert primary_vf.get('managed') == 'yes'
        assert primary_vf.find('driver').get('name') == 'vfio'
        vf_address = primary_vf.find('./source/address')
        assert vf_address.attrib == {
            'type': 'pci',
            'domain': '0x0000',
            'bus': '0x00',
            'slot': '0x05',
            'function': '0x0',
        }
        assert len(final_root.findall('./devices/hostdev')) == 3
        assert 'host,migratable=on,vendor=AuthenticAMD' in xml_str

    def test_zstac_88044_cpu_vendor_probe_keeps_none_mode_fallback(self):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.nestedVirtualization = 'none'
        cmd.vmCpuVendorId = 'AuthenticAMD'
        probe_xmls = []

        def fail_cpu_probe(command, *_args, **_kwargs):
            if 'domxml-to-native' not in command:
                return 0, '', ''
            probe_path = command.split('--xml ', 1)[1].split(' ', 1)[0]
            with open(probe_path) as probe_file:
                probe_xmls.append(probe_file.read())
            return 1, '', 'conversion failed'

        xml_str = self._build_start_vm_xml(
            cmd,
            MagicMock(side_effect=fail_cpu_probe),
        )

        assert len(probe_xmls) == 1
        probe_root = vm_plugin.etree.fromstring(probe_xmls[0])
        assert probe_root.findall("./devices/interface[@type='hostdev']") == []
        assert probe_root.findall('./devices/hostdev') == []
        assert 'qemu64,vendor=AuthenticAMD' in xml_str

    def test_zstac_88044_cpu_vendor_probe_keeps_normal_interface(self):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.nestedVirtualization = 'host-passthrough'
        cmd.vmCpuVendorId = 'AuthenticAMD'
        cmd.nics = [cmd.nics[0]]
        cmd.addons.pciDevice = []
        cmd.addons.mdevDevice = []
        cmd.addons.usbDevice = []
        probe_xmls = []

        def capture_cpu_probe(command, *_args, **_kwargs):
            if 'domxml-to-native' not in command:
                return 0, '', ''
            probe_path = command.split('--xml ', 1)[1].split(' ', 1)[0]
            with open(probe_path) as probe_file:
                probe_xmls.append(probe_file.read())
            return 0, 'host,migratable=on', ''

        xml_str = self._build_start_vm_xml(
            cmd,
            MagicMock(side_effect=capture_cpu_probe),
        )

        probe_root = vm_plugin.etree.fromstring(probe_xmls[0])
        final_root = vm_plugin.etree.fromstring(xml_str)
        assert len(probe_root.findall("./devices/interface[@type='bridge']")) == 1
        assert len(final_root.findall("./devices/interface[@type='bridge']")) == 1
        assert 'host,migratable=on,vendor=AuthenticAMD' in xml_str

    @pytest.mark.parametrize('cpu_mode', ['host-model', 'custom'])
    def test_zstac_88044_model_cpu_modes_do_not_use_native_probe(self, cpu_mode):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.nestedVirtualization = cpu_mode
        cmd.vmCpuVendorId = 'AuthenticAMD'
        bash_roe = MagicMock(return_value=(0, '', ''))

        xml_str = self._build_start_vm_xml(cmd, bash_roe)

        assert all(
            'domxml-to-native' not in call[0][0]
            for call in bash_roe.call_args_list
        )
        root = vm_plugin.etree.fromstring(xml_str)
        assert root.find('./cpu/model').get('vendor_id') == 'AuthenticAMD'

    @pytest.mark.parametrize('vendor_id', [None, 'None'])
    def test_zstac_88044_missing_cpu_vendor_does_not_use_native_probe(self, vendor_id):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.nestedVirtualization = 'host-passthrough'
        cmd.vmCpuVendorId = vendor_id
        bash_roe = MagicMock(return_value=(0, '', ''))

        xml_str = self._build_start_vm_xml(cmd, bash_roe)

        assert all(
            'domxml-to-native' not in call[0][0]
            for call in bash_roe.call_args_list
        )
        assert 'vendor=' not in xml_str


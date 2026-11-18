# -*- coding: utf-8 -*-
"""Exercise the real XML builder; this does not certify guest/host support."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

with patch("platform.freedesktop_os_release", return_value={"ID": "centos", "VERSION_ID": "7"}):
    from kvmagent.plugins import vm_plugin


def nic(backend, driver):
    return SimpleNamespace(
        type=backend, driverType=driver, useVirtio=False,
        pciDeviceAddress=None, srcPath=None, mac='fa:16:3e:00:00:01',
        nicInternalName='vnic1.0', mtu=1500, state='enable',
        physicalInterface='eth0', vlanId=None, bridgeName='br_eth0',
        pci=None, cleanTraffic=False, bootOrder=None,
        vHostAddOn=SimpleNamespace(queueNum=1, rxBufferSize=None, txBufferSize=None))


@pytest.mark.parametrize('backend,interface_type', [('VNIC', 'bridge'), ('TFVNIC', 'ethernet'), ('MACVLAN', 'direct')])
@pytest.mark.parametrize('driver', ['virtio', 'e1000', 'rtl8139', 'pcnet'])
@pytest.mark.parametrize('with_devices', [False, True])
def test_emulated_backend_preserves_explicit_model(backend, interface_type, driver, with_devices):
    devices = vm_plugin.etree.Element('devices') if with_devices else None
    if devices is not None:
        vm_plugin.etree.SubElement(devices, 'disk')  # a non-empty parent, as at VM startup
    xml = vm_plugin.Vm._build_interface_xml(nic(backend, driver), devices, action='Update')
    assert xml.get('type') == interface_type
    assert xml.find('model').get('type') == driver


@pytest.mark.parametrize('backend', ['dpdkvhostuserclient', 'vDPA', 'VNIC'])
def test_vhost_backend_preserves_virtio(backend):
    xml = vm_plugin.Vm._build_interface_xml(nic(backend, 'virtio'), vhostSrcPath='/tmp/test.sock', action='Update')
    assert xml.get('type') == 'vhostuser'
    assert xml.find('model').get('type') == 'virtio'


def test_hostdev_has_no_emulated_model():
    device = nic('VF', None)
    device.pciDeviceAddress = '0000:01:00.0'
    xml = vm_plugin.Vm._build_interface_xml(device, action='Update')
    assert xml.get('type') == 'hostdev'
    assert xml.find('model') is None
    assert xml.find('driver').get('name') == 'vfio'


def test_zstac_90099_attach_sriov_bond_syncs_vf_mac_and_slave_alias():
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock
    from zstacklib.utils import jsonobject

    xmlobject_path = Path(__file__).resolve().parents[3] / 'zstacklib' / 'zstacklib' / 'utils' / 'xmlobject.py'
    spec = importlib.util.spec_from_file_location('_real_xmlobject', str(xmlobject_path))
    real_xmlobject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real_xmlobject)

    domain_xml = "<domain type='kvm'><name>vr</name><uuid>22222222222222222222222222222222</uuid><devices></devices></domain>"
    vm = vm_plugin.Vm()
    vm.uuid = '22222222222222222222222222222222'
    vm.state = vm_plugin.Vm.VM_STATE_RUNNING
    vm.domain_xml = domain_xml
    vm.domain_xmlobject = real_xmlobject.loads(domain_xml)
    vm.refresh = lambda: None
    vm.domain = MagicMock()
    vm._has_qemu_commandline_devices = lambda: False

    cmd = jsonobject.loads(jsonobject.dumps({
        'vmUuid': vm.uuid,
        'addons': None,
        'nic': {
            'uuid': 'bond-vf-uuid',
            'mac': 'fa:16:3e:88:99:aa',
            'nicInternalName': 'vnic10.2',
            'type': 'VF',
            'pciDeviceAddress': '0000:3b:02.0',
            'extraPciDeviceAddresses': ['0000:af:02.0'],
            'isolated': False,
            'cleanTraffic': False,
        }
    }))

    bash_calls = []
    pf_map = {'0000:3b:02.0': 'enp59s0f0', '0000:af:02.0': 'enp175s0f0'}
    vf_idx_map = {'0000:3b:02.0': 0, '0000:af:02.0': 1}
    with patch('kvmagent.plugins.vm_plugin.linux.wait_callback_success', return_value=True), \
         patch('kvmagent.plugins.vm_plugin.linux.get_pf_name_by_vf_pci_address', side_effect=lambda p: pf_map.get(p)), \
         patch('kvmagent.plugins.vm_plugin.linux.get_vf_index_by_pci_address', side_effect=lambda p: vf_idx_map.get(p)), \
         patch('kvmagent.plugins.vm_plugin.bash.bash_roe', side_effect=lambda c: (bash_calls.append(c) or 0, '', '')):
        vm._attach_nic(cmd)

    assert bash_calls == [
        'ip link set enp59s0f0 vf 0 mac fa:16:3e:88:99:aa',
        'ip link set enp175s0f0 vf 1 mac fa:16:3e:88:99:aa',
    ]
    assert vm.domain.attachDeviceFlags.call_count == 2
    primary_xml = vm_plugin.etree.fromstring(vm.domain.attachDeviceFlags.call_args_list[0][0][0])
    slave_xml = vm_plugin.etree.fromstring(vm.domain.attachDeviceFlags.call_args_list[1][0][0])
    assert primary_xml.find('alias').get('name') == 'net2'
    assert slave_xml.find('alias').get('name') == 'net2-slave1'


def test_zstac_89956_reboot_reapplies_hostdev_vf_macs_before_start():
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace

    xmlobject_path = Path(__file__).resolve().parents[3] / 'zstacklib' / 'zstacklib' / 'utils' / 'xmlobject.py'
    spec = importlib.util.spec_from_file_location('_real_xmlobject', str(xmlobject_path))
    real_xmlobject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real_xmlobject)

    domain_xml = """
    <domain type='kvm'>
      <name>vr-sriov</name>
      <uuid>33333333333333333333333333333333</uuid>
      <os><type>hvm</type><boot dev='hd'/></os>
      <devices>
        <interface type='bridge'>
          <mac address='fa:16:3e:00:00:01'/>
          <source bridge='br_eth0'/>
          <target dev='vnic9.0'/>
        </interface>
        <interface type='hostdev' managed='yes'>
          <mac address='fa:16:3e:77:88:99'/>
          <source><address type='pci' domain='0x0000' bus='0x3b' slot='0x02' function='0x0'/></source>
        </interface>
        <interface type='hostdev' managed='yes'>
          <mac address='fa:16:3e:77:88:99'/>
          <source><address type='pci' domain='0x0000' bus='0xaf' slot='0x02' function='0x0'/></source>
        </interface>
      </devices>
    </domain>
    """.strip()

    vm = vm_plugin.Vm()
    vm.uuid = '33333333333333333333333333333333'
    vm.domain_xml = domain_xml
    vm.domain_xmlobject = real_xmlobject.loads(domain_xml)

    events = []
    vm.stop = lambda timeout=None: events.append('stop')
    vm.start = lambda timeout=None: events.append('start')

    pf_map = {'0000:3b:02.0': 'enp59s0f0', '0000:af:02.0': 'enp175s0f0'}
    vf_idx_map = {'0000:3b:02.0': 0, '0000:af:02.0': 1}
    cmd = SimpleNamespace(timeout=60, bootDev=['hd'])

    with patch.object(vm_plugin, 'xmlobject', real_xmlobject), \
         patch('kvmagent.plugins.vm_plugin.linux.get_pf_name_by_vf_pci_address', side_effect=lambda p: pf_map.get(p)), \
         patch('kvmagent.plugins.vm_plugin.linux.get_vf_index_by_pci_address', side_effect=lambda p: vf_idx_map.get(p)), \
         patch('kvmagent.plugins.vm_plugin.bash.bash_roe', side_effect=lambda c: (events.append(c) or 0, '', '')):
        vm.reboot(cmd)

    assert events == [
        'stop',
        'ip link set enp59s0f0 vf 0 mac fa:16:3e:77:88:99',
        'ip link set enp175s0f0 vf 1 mac fa:16:3e:77:88:99',
        'start',
    ]


def test_same_mac_multi_nic_device_info_update_and_detach():
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock
    from zstacklib.utils import jsonobject

    xmlobject_path = Path(__file__).resolve().parents[3] / 'zstacklib' / 'zstacklib' / 'utils' / 'xmlobject.py'
    spec = importlib.util.spec_from_file_location('_real_xmlobject', str(xmlobject_path))
    real_xmlobject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real_xmlobject)

    domain_xml = """
    <domain type='kvm'>
      <name>vm-same-mac</name>
      <uuid>11111111111111111111111111111111</uuid>
      <devices>
        <interface type='bridge'>
          <mac address='fa:11:22:33:44:55'/>
          <source bridge='br_eth0'/>
          <target dev='vnic1.0'/>
          <model type='virtio'/>
          <mtu size='1500'/>
          <alias name='net0'/>
          <address type='pci' domain='0x0000' bus='0x00' slot='0x03' function='0x0'/>
        </interface>
        <interface type='bridge'>
          <mac address='fa:11:22:33:44:55'/>
          <source bridge='br_eth1'/>
          <target dev='vnic1.1'/>
          <model type='virtio'/>
          <mtu size='9000'/>
          <alias name='net1'/>
          <address type='pci' domain='0x0000' bus='0x00' slot='0x04' function='0x0'/>
        </interface>
        <interface type='hostdev' managed='yes'>
          <mac address='fa:11:22:33:44:55'/>
          <source>
            <address type='pci' domain='0x0000' bus='0x3b' slot='0x02' function='0x1'/>
          </source>
          <alias name='net2'/>
          <address type='pci' domain='0x0000' bus='0x00' slot='0x05' function='0x0'/>
        </interface>
      </devices>
    </domain>
    """
    vm = vm_plugin.Vm()
    vm.uuid = '11111111111111111111111111111111'
    vm.state = vm_plugin.Vm.VM_STATE_RUNNING
    vm.domain_xml = domain_xml.strip()
    vm.domain_xmlobject = real_xmlobject.loads(domain_xml.strip())
    vm.refresh = lambda: None
    vm.domain = MagicMock()

    plugin = vm_plugin.VmPlugin.__new__(vm_plugin.VmPlugin)
    plugin.config = {}
    with patch('kvmagent.plugins.vm_plugin.get_vm_by_uuid', return_value=vm):
        nic_infos, _, _ = plugin.get_vm_device_info(vm.uuid)
    assert len(nic_infos) == 3
    assert nic_infos[0].nicInternalName == 'vnic1.0'
    assert nic_infos[0].deviceAddress.slot == '0x03'
    assert nic_infos[1].nicInternalName == 'vnic1.1'
    assert nic_infos[1].deviceAddress.slot == '0x04'
    assert nic_infos[2].nicInternalName is None
    assert nic_infos[2].pciDeviceAddress == '0000:3b:02.1'
    assert nic_infos[2].deviceAddress.slot == '0x05'

    nic1 = jsonobject.loads(jsonobject.dumps({
        'uuid': 'nic-1-uuid',
        'mac': 'fa:11:22:33:44:55',
        'nicInternalName': 'vnic1.1',
        'bridgeName': 'br_eth1',
        'driverType': 'virtio',
        'mtu': 1500,
        'type': 'VNIC',
        'state': 'disable',
        'cleanTraffic': False,
        'isolated': False,
        'vHostAddOn': {'queueNum': 1}
    }))
    update_cmd = jsonobject.JsonObject()
    update_cmd.nics = [nic1]
    update_cmd.addons = None
    with patch('kvmagent.plugins.vm_plugin.linux.wait_callback_success', return_value=True):
        vm._update_nic(update_cmd)
    updated_xml = vm.domain.updateDeviceFlags.call_args[0][0]
    updated_root = vm_plugin.etree.fromstring(updated_xml)
    assert updated_root.find('target').get('dev') == 'vnic1.1'
    assert updated_root.find('address').get('slot') == '0x04'
    assert updated_root.find('mtu').get('size') == '9000'
    assert updated_root.find('link').get('state') == 'down'

    nic1_detach = jsonobject.loads(jsonobject.dumps({
        'uuid': 'nic-1-uuid',
        'mac': 'fa:11:22:33:44:55',
        'nicInternalName': 'vnic1.1',
        'bridgeName': 'br_eth1',
        'driverType': 'virtio',
        'mtu': 9000,
        'type': 'VNIC',
        'cleanTraffic': False,
        'isolated': False,
        'vHostAddOn': {'queueNum': 1}
    }))
    detach_cmd = jsonobject.JsonObject()
    detach_cmd.nic = nic1_detach
    detach_cmd.addons = None
    vm.libvirt = MagicMock()
    vm.libvirt.libvirtError = Exception
    with patch('kvmagent.plugins.vm_plugin.linux.wait_callback_success', return_value=True):
        vm._detach_nic(detach_cmd)
    detached_xml = vm.domain.detachDeviceFlags.call_args[0][0]
    detached_root = vm_plugin.etree.fromstring(detached_xml)
    assert detached_root.find('target').get('dev') == 'vnic1.1'
    assert detached_root.find('address').get('slot') == '0x04'

    attach_req_body = jsonobject.dumps({
        'vmUuid': vm.uuid,
        'nic': {
            'uuid': 'nic-1-uuid',
            'mac': 'fa:11:22:33:44:55',
            'nicInternalName': 'vnic1.1',
            'bridgeName': 'br_eth1',
            'driverType': 'virtio',
            'type': 'VNIC',
        }
    })
    vm.attach_nic = MagicMock()
    with patch('kvmagent.plugins.vm_plugin.get_vm_by_uuid', return_value=vm):
        attach_rsp = jsonobject.loads(plugin.attach_nic({vm_plugin.http.REQUEST_BODY: attach_req_body}))
    assert len(attach_rsp.virtualDeviceInfoList) == 1
    assert attach_rsp.virtualDeviceInfoList[0].resourceUuid == 'nic-1-uuid'
    assert attach_rsp.virtualDeviceInfoList[0].deviceAddress.slot == '0x04'

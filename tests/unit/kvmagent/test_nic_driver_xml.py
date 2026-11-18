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

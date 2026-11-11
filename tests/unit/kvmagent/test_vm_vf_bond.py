"""Dual-VF identity and partial hotplug failure regression tests."""
import copy
from unittest.mock import MagicMock

import pytest
from lxml import etree
from kvmagent.plugins import vm_plugin as plugin
from zstacklib.utils import jsonobject


@pytest.fixture
def bond(monkeypatch):
    vm = plugin.Vm.__new__(plugin.Vm)
    vm.uuid = "test-vm"
    vm.state = plugin.Vm.VM_STATE_RUNNING
    vm.domain = MagicMock()
    attached = set()
    commands = []
    vm._vf_device_xml = lambda address: address if address in attached else None
    vm._interface_cmd_to_xml = lambda cmd, **kwargs: commands.append((cmd, kwargs)) or cmd.nic.pciDeviceAddress
    vm.domain.attachDeviceFlags.side_effect = lambda address, flags: attached.add(address)
    vm.domain.detachDeviceFlags.side_effect = lambda address, flags: attached.discard(address)
    monkeypatch.setattr(plugin.linux, 'wait_callback_success', lambda callback, **kwargs: callback(None), raising=False)
    cmd = jsonobject.loads('{"nic":{"type":"VF","uuid":"0123456789abcdef0123456789abcdef","pciDeviceAddress":"0000:17:10.0","extraPciDeviceAddresses":["0000:17:10.7"],"nicInternalName":"vnic1.1","pci":{"slot":"0x08"},"secondaryPci":{"slot":"0x09"}}}')
    return vm, cmd, attached, commands


def test_attach_pair_separate_alias_and_guest_address(bond):
    vm, cmd, attached, commands = bond
    vm._attach_vf_bond(cmd)
    assert attached == {'0000:17:10.0', '0000:17:10.7'}
    assert commands[1][1]['alias_name'] == 'ua-net1-slave1'
    assert commands[1][0].nic.pci.slot == '0x09'
    assert cmd.nic.pci.slot == '0x08'
    vm._attach_vf_bond(cmd)
    assert len(commands) == 2


def test_second_attach_failure_compensates_first(bond):
    vm, cmd, attached, _ = bond
    def attach(address, flags):
        if address.endswith('.7'):
            raise RuntimeError('second VF rejected')
        attached.add(address)
    vm.domain.attachDeviceFlags.side_effect = attach
    with pytest.raises(RuntimeError, match='second VF'):
        vm._attach_vf_bond(cmd)
    assert not attached


def test_compensation_does_not_remove_preexisting_device(bond):
    vm, cmd, attached, _ = bond
    attached.add(cmd.nic.pciDeviceAddress)
    vm.domain.attachDeviceFlags.side_effect = RuntimeError('rejected')
    with pytest.raises(RuntimeError):
        vm._attach_vf_bond(cmd)
    assert attached == {cmd.nic.pciDeviceAddress}


def test_detach_residual_device_is_failure(bond):
    vm, cmd, attached, _ = bond
    attached.add(cmd.nic.pciDeviceAddress)
    vm.domain.detachDeviceFlags.side_effect = None
    with pytest.raises(Exception, match='still attached'):
        vm._detach_vf_device(cmd.nic.pciDeviceAddress)


def test_alias_without_internal_name(bond):
    vm, cmd, _, commands = bond
    cmd.nic.nicInternalName = None
    vm._attach_vf_bond(cmd)
    assert commands[1][1]['alias_name'] == 'ua-net0-slave1'


def test_reject_same_host_pci(bond):
    vm, cmd, attached, commands = bond
    cmd.nic.extraPciDeviceAddresses = [cmd.nic.pciDeviceAddress]
    with pytest.raises(Exception, match='two different'):
        vm._attach_vf_bond(cmd)
    assert not attached and not commands


def test_hostdev_xml_preserves_guest_address():
    nic = jsonobject.loads('{"type":"VF","mac":"fa:00:00:00:00:01","pciDeviceAddress":"0000:17:10.7","nicInternalName":"vnic1.1","pci":{"type":"pci","domain":"0x0000","bus":"0x00","slot":"0x09","function":"0x0"}}')
    xml = plugin.Vm._build_interface_xml(nic, alias_name='ua-net1-slave1')
    assert xml.find('source/address').get('slot') == '0x10'
    assert xml.find('address').get('slot') == '0x09'
    assert xml.find('alias').get('name') == 'ua-net1-slave1'


def test_detach_preserves_request_error_on_timeout(bond, monkeypatch):
    vm, cmd, attached, _ = bond
    class LibvirtError(Exception):
        pass
    monkeypatch.setattr(plugin.libvirt, 'libvirtError', LibvirtError, raising=False)
    attached.add(cmd.nic.pciDeviceAddress)
    vm.domain.detachDeviceFlags.side_effect = LibvirtError('already in the process of unplug')
    with pytest.raises(Exception, match='already in the process of unplug') as error:
        vm._detach_vf_device(cmd.nic.pciDeviceAddress)
    assert 'test-vm' in str(error.value)
    assert cmd.nic.pciDeviceAddress in str(error.value)
    assert attached == {cmd.nic.pciDeviceAddress}


def test_detach_request_error_still_accepts_observed_removal(bond, monkeypatch):
    vm, cmd, attached, _ = bond
    class LibvirtError(Exception):
        pass
    monkeypatch.setattr(plugin.libvirt, 'libvirtError', LibvirtError, raising=False)
    attached.add(cmd.nic.pciDeviceAddress)
    vm.domain.detachDeviceFlags.side_effect = LibvirtError('reply lost')
    def observe(callback, **kwargs):
        attached.clear()
        return callback(None)
    monkeypatch.setattr(plugin.linux, 'wait_callback_success', observe)
    vm._detach_vf_device(cmd.nic.pciDeviceAddress)

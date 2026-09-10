from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

import pytest

from kvmagent.plugins import vm_plugin


GIB = 1024 ** 3


@pytest.fixture(autouse=True)
def libvirt_error(monkeypatch):
    monkeypatch.setattr(vm_plugin.libvirt, 'libvirtError', type('LibvirtError', (Exception,), {}))


def make_vm(models, slots='16'):
    vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
    vm.uuid = 'vm-memory-slots'
    vm.get_memory = MagicMock(return_value=4 * GIB)
    root = ET.Element('domain')
    maximum = ET.SubElement(root, 'maxMemory', unit='KiB')
    maximum.text = str(64 * GIB // 1024)
    if slots is not None:
        maximum.set('slots', slots)
    devices = ET.SubElement(root, 'devices')
    for model in models:
        ET.SubElement(devices, 'memory', model=model)
    ET.SubElement(devices, 'disk')
    vm.domain = MagicMock()
    vm.domain.XMLDesc.return_value = ET.tostring(root, encoding='unicode')
    return vm


@pytest.mark.parametrize('models', [
    ['dimm'] * 16,
    ['dimm'] * 15 + ['nvdimm'],
])
def test_exhausted_slots_fail_before_attach(models):
    vm = make_vm(models)
    with pytest.raises(vm_plugin.kvmagent.KvmError, match='16/16.*stop and start'):
        vm.hotplug_mem(5 * GIB)
    vm.domain.attachDeviceFlags.assert_not_called()
    vm.domain.XMLDesc.assert_called_once_with(0)


def test_last_dimm_slot_is_available_with_other_device_models():
    vm = make_vm(['dimm'] * 15 + ['virtio-mem'])
    vm.hotplug_mem(5 * GIB)
    xml, flags = vm.domain.attachDeviceFlags.call_args.args
    assert ET.fromstring(xml).find('target/size').text == str(GIB // 1024)
    assert flags == (vm_plugin.libvirt.VIR_DOMAIN_AFFECT_LIVE |
                     vm_plugin.libvirt.VIR_DOMAIN_AFFECT_CONFIG)


@pytest.mark.parametrize('used', [16, 63])
def test_expanded_domain_can_hotplug_beyond_sixteen_times(used):
    vm = make_vm(['dimm'] * used, slots='64')
    vm.hotplug_mem(5 * GIB)
    vm.domain.attachDeviceFlags.assert_called_once()


def test_expanded_domain_rejects_the_sixty_fifth_device():
    vm = make_vm(['dimm'] * 64, slots='64')
    with pytest.raises(vm_plugin.kvmagent.KvmError, match='64/64.*stop and start'):
        vm.hotplug_mem(5 * GIB)
    vm.domain.attachDeviceFlags.assert_not_called()


def test_no_memory_change_does_not_probe_or_attach():
    vm = make_vm(['dimm'] * 16)
    vm.hotplug_mem(4 * GIB)
    vm.domain.XMLDesc.assert_not_called()
    vm.domain.attachDeviceFlags.assert_not_called()


def test_missing_slot_limit_keeps_libvirt_validation():
    vm = make_vm(['dimm'] * 16, slots=None)
    vm.hotplug_mem(5 * GIB)
    vm.domain.attachDeviceFlags.assert_called_once()


@pytest.mark.parametrize('error, expected', [
    ('internal error: no free memory device slot available', 'stop and start'),
    ('cannot set up guest memory', 'No enough physical memory'),
    ("would exceed domain's maxMemory config", 'Instance Offering'),
    ('unrelated libvirt failure', 'unrelated libvirt failure'),
])
def test_attach_errors_remain_actionable(error, expected):
    vm = make_vm(['dimm'] * 15)
    vm.domain.attachDeviceFlags.side_effect = vm_plugin.libvirt.libvirtError(error)
    with pytest.raises(vm_plugin.kvmagent.KvmError, match=expected):
        vm.hotplug_mem(5 * GIB)

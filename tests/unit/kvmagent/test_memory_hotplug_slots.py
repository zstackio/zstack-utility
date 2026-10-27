import re
import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

import pytest


PATH = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/vm_plugin.py'
GIB = 1024 ** 3
KvmError = type('KvmError', (Exception,), {})
LibvirtError = type('LibvirtError', (Exception,), {})
LIBVIRT = SimpleNamespace(libvirtError=LibvirtError, VIR_DOMAIN_AFFECT_LIVE=1, VIR_DOMAIN_AFFECT_CONFIG=2)


def production_function(name, namespace, indent):
    pattern = r'^%sdef %s\(.*?(?=^%s(?:def |@)|\Z)' % (indent, name, indent)
    source = re.search(pattern, PATH.read_text(), re.M | re.S).group(0)
    exec(compile(textwrap.dedent(source), str(PATH), 'exec'), namespace)
    return namespace[name]


def make_vm(models, slots='16'):
    root = ET.Element('domain')
    maximum = ET.SubElement(root, 'maxMemory', unit='KiB')
    if slots is not None:
        maximum.set('slots', slots)
    devices = ET.SubElement(root, 'devices')
    for model in models:
        ET.SubElement(devices, 'memory', model=model)
    vm = SimpleNamespace(uuid='vm-memory-slots', get_memory=lambda: 4 * GIB, domain=MagicMock())
    vm.domain.XMLDesc.return_value = ET.tostring(root, encoding='unicode')
    namespace = dict(etree=ET, logger=MagicMock(), libvirt=LIBVIRT, kvmagent=SimpleNamespace(KvmError=KvmError))
    hotplug = production_function('hotplug_mem', namespace, '    ')
    vm.hotplug_mem = lambda size: hotplug(vm, size)
    return vm


@pytest.mark.parametrize('slots,models', [('16', ['dimm'] * 16), ('16', ['dimm'] * 15 + ['nvdimm']), ('64', ['dimm'] * 64)])
def test_exhausted_slots_fail_before_attach(slots, models):
    vm = make_vm(models, slots)
    with pytest.raises(KvmError, match=slots + '/' + slots + '.*stop and start'):
        vm.hotplug_mem(5 * GIB)
    vm.domain.attachDeviceFlags.assert_not_called()


@pytest.mark.parametrize('used', [16, 63])
def test_expanded_domain_can_hotplug_beyond_sixteen_times(used):
    vm = make_vm(['dimm'] * used, '64')
    vm.hotplug_mem(5 * GIB)
    xml, flags = vm.domain.attachDeviceFlags.call_args.args
    assert ET.fromstring(xml).find('target/size').text == str(GIB // 1024)
    assert flags == 3


def test_virtio_mem_does_not_consume_a_dimm_slot():
    vm = make_vm(['dimm'] * 15 + ['virtio-mem'])
    vm.hotplug_mem(5 * GIB)
    vm.domain.attachDeviceFlags.assert_called_once()


def test_no_change_does_not_probe_or_attach():
    vm = make_vm(['dimm'] * 16)
    vm.hotplug_mem(4 * GIB)
    vm.domain.XMLDesc.assert_not_called()
    vm.domain.attachDeviceFlags.assert_not_called()


def test_missing_slot_limit_keeps_libvirt_validation():
    vm = make_vm(['dimm'] * 16, slots=None)
    vm.hotplug_mem(5 * GIB)
    vm.domain.attachDeviceFlags.assert_called_once()


@pytest.mark.parametrize('error,expected', [('no free memory device slot available', 'stop and start'),
    ('cannot set up guest memory', 'No enough physical memory'),
    ("would exceed domain's maxMemory config", 'Instance Offering'), ('unrelated', 'unrelated')])
def test_attach_errors_remain_actionable(error, expected):
    vm = make_vm(['dimm'] * 15)
    vm.domain.attachDeviceFlags.side_effect = LibvirtError(error)
    with pytest.raises(KvmError, match=expected):
        vm.hotplug_mem(5 * GIB)


@pytest.mark.parametrize('use_numa', [True, False])
def test_production_memory_xml_preserves_maximum_and_expands_numa_slots(use_numa):
    root = ET.Element('domain')
    maximum = 64 * GIB // 1024
    def element(parent, name, value, attrib):
        node = ET.SubElement(parent, name, attrib)
        node.text = value
    namespace = dict(elements={'root': root}, cmd=SimpleNamespace(memory=4 * GIB),
                     use_numa=use_numa, MAX_MEMORY=maximum, e=element)
    production_function('make_memory', namespace, '        ')()
    if use_numa:
        assert root.find('maxMemory').get('slots') == '64'
        assert root.find('maxMemory').text == str(maximum)
    else:
        assert root.find('maxMemory') is None
        assert float(root.find('memory').text) == 4 * GIB // 1024
    assert float(root.find('currentMemory').text) == 4 * GIB // 1024

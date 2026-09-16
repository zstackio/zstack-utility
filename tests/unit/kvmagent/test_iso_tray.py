import importlib.util
import json
import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

import pytest

from kvmagent.plugins import vm_plugin


@pytest.fixture(autouse=True)
def real_xmlobject(monkeypatch):
    for name in ('xmlobject', 'qmp'):
        path = Path(__file__).resolve().parents[3] / ('zstacklib/zstacklib/utils/%s.py' % name)
        spec = importlib.util.spec_from_file_location('iso_tray_' + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(vm_plugin, name, module)
    vm_plugin.qmp.QEMU_VERSION = '6.2.0'
    return vm_plugin.xmlobject


@pytest.mark.parametrize('bus,machine,arch', [
    ('ide', 'pc-i440fx-rhel7.6.0', 'x86_64'),
    ('sata', 'pc-q35-rhel8.6.0', 'x86_64'),
    ('scsi', 'virt', 'aarch64'),
])
def test_repeated_iso_changes_open_only_target_tray(monkeypatch, real_xmlobject, bus, machine, arch):
    xmlobject = real_xmlobject
    monkeypatch.setattr(vm_plugin, 'HOST_ARCH', arch)
    monkeypatch.setattr(vm_plugin, 'get_libvirt_major_version', lambda: 8)
    monkeypatch.setattr(vm_plugin, 'get_volume_actual_installpath', lambda path: path)
    monkeypatch.setattr(vm_plugin.libvirt, 'libvirtError', type('LibvirtError', (Exception,), {}))
    root = ET.fromstring('<domain><os><type machine="%s"/></os><devices/></domain>' % machine)
    disks, blocks = [], []
    for index, letter in enumerate(vm_plugin.Vm.ISO_DEVICE_LETTERS):
        dev = vm_plugin.Vm._get_iso_target_dev(letter)
        alias = '%s0-0-%s%d' % (bus, '0-' if bus == 'scsi' else '', index + 1)
        disk = ET.SubElement(root.find('devices'), 'disk', device='cdrom', type='file')
        ET.SubElement(disk, 'target', dev=dev, bus=bus)
        ET.SubElement(disk, 'alias', name=alias)
        ET.SubElement(disk, 'address', type='drive', controller='0', bus='0', target='0', unit=str(index + 1))
        disks.append(disk)
        blocks.append({'qdev': alias, 'tray_open': False})
    vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
    vm.uuid = 'vm-iso-tray'
    vm.domain = MagicMock()
    vm.domain.XMLDesc.side_effect = lambda flags: ET.tostring(root, encoding='unicode')
    vm.domain_xmlobject = xmlobject.loads(vm.domain.XMLDesc(0))
    monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', lambda uuid: vm)
    monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success', lambda check, *args: check(None))

    def monitor_command(command):
        args = shlex.split(command)
        assert args[:3] == ['virsh', 'qemu-monitor-command', vm.uuid]
        command = json.loads(args[3])
        if command['execute'] == 'query-block':
            return 0, json.dumps({'return': blocks}), ''
        assert command['execute'] == 'blockdev-open-tray'
        selected = [block for block in blocks if block['qdev'] == command['arguments']['id']]
        assert len(selected) == 1
        selected[0]['tray_open'] = True
        return 0, '{"return": {}, "id": "libvirt-909"}', ''

    transport = MagicMock(side_effect=monitor_command)
    monkeypatch.setattr(vm_plugin.qmp.bash, 'bash_roe', transport)

    def update_medium(xml, flags):
        requested = ET.fromstring(xml)
        index = next(i for i, disk in enumerate(disks)
                     if disk.find('target').get('dev') == requested.find('target').get('dev'))
        assert [block['tray_open'] for block in blocks] == [i == index for i in range(3)]
        disk = disks[index]
        if disk.find('source') is not None:
            disk.remove(disk.find('source'))
        if requested.find('source') is not None:
            disk.append(requested.find('source'))
        blocks[index]['tray_open'] = False
        vm.domain_xmlobject = xmlobject.loads(vm.domain.XMLDesc(0))

    vm.domain.updateDeviceFlags.side_effect = update_medium
    for _ in range(2):
        for action in ('attach_iso', 'detach_iso'):
            for index in range(3):
                iso = SimpleNamespace(deviceId=index, path='/test.iso', isEmpty=False, protocol=None)
                getattr(vm, action)(SimpleNamespace(vmUuid=vm.uuid, deviceId=index, iso=iso))
    assert transport.call_count == 24
    assert vm.domain.updateDeviceFlags.call_count == 12


@pytest.mark.parametrize('disks', [
    '', '<disk device="disk"><target dev="hdc"/></disk>',
    '<disk device="cdrom"/>', '<disk device="cdrom"><target dev="hdd"/></disk>',
    '<disk device="cdrom"><target dev="hdc"/></disk>',
])
def test_missing_cdrom_alias_is_skipped(disks):
    assert vm_plugin.find_domain_cdrom_alias_name(
        '<domain><devices>%s</devices></domain>' % disks, 'hdc') is None


@pytest.mark.parametrize('alias,blocks', [
    (None, [{'qdev': 'ide0-0-1', 'tray_open': False}]),
    ('ide0-0-1', []),
    ('ide0-0-1', [{'qdev': 'ide0-0-2', 'tray_open': False}]),
    ('ide0-0-1', [{'qdev': 'ide0-0-1'}]),
    ('ide0-0-1', [{'tray_open': False}]),
])
def test_unidentified_tray_does_not_open_other_devices(monkeypatch, alias, blocks):
    query = MagicMock(return_value=blocks)
    command = MagicMock()
    monkeypatch.setattr(vm_plugin, 'get_vm_blocks', query)
    monkeypatch.setattr(vm_plugin.qmp.bash, 'bash_roe', command)
    vm_plugin.Vm.__new__(vm_plugin.Vm).open_cdrom_tray('vm-iso-tray', alias)
    command.assert_not_called()
    if alias is None:
        query.assert_not_called()


@pytest.mark.parametrize('response', [
    (1, '', 'open-tray failed'),
    (0, '{"error": {"class": "DeviceNotFound", "desc": "Device not found"}}', ''),
])
def test_qmp_failure_keeps_existing_libvirt_fallback(monkeypatch, response):
    query = MagicMock(side_effect=RuntimeError('query-block failed'))
    command = MagicMock(return_value=response)
    monkeypatch.setattr(vm_plugin, 'get_vm_blocks', query)
    monkeypatch.setattr(vm_plugin.qmp.bash, 'bash_roe', command)
    vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
    vm.open_cdrom_tray('vm-iso-tray', 'ide0-0-1')
    command.assert_not_called()
    query.side_effect = None
    query.return_value = [{'qdev': 'ide0-0-1', 'tray_open': False}]
    vm.open_cdrom_tray('vm-iso-tray', 'ide0-0-1')
    command.assert_called_once()

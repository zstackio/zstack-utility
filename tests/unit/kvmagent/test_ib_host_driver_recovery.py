# -*- coding: utf-8 -*-
"""Check Host driver evidence without touching real hardware."""
import errno
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kvmagent.plugins import vm_plugin
from zstacklib.utils import http

# The shared harness stubs pci; load its real sysfs reader in isolation.
_pci_path = Path(__file__).parents[3] / "zstacklib/zstacklib/utils/pci.py"
_pci_spec = importlib.util.spec_from_file_location("pci_driver_recovery_test", _pci_path)
pci = importlib.util.module_from_spec(_pci_spec)
_pci_spec.loader.exec_module(pci)


def make_pci_request(address='0000:18:00.0', device_type='IB_Controller'):
    """Return an Agent request without sending it; let JSON encoding errors propagate."""
    body = {'pciDeviceAddress': address, 'type': device_type}
    return {http.REQUEST_BODY: json.dumps(body), http.REQUEST_HEADER: {}}


@pytest.mark.parametrize('driver', ['mlx5_core', 'mlx4_core', 'vfio-pci'])
def test_read_bound_driver_from_sysfs(driver):
    """Expect the bound driver name; return None or fail an assertion on mismatch."""
    with patch.object(pci.os.path, 'isdir', return_value=True), \
            patch.object(pci.os, 'readlink', return_value='../../../../bus/pci/drivers/' + driver) as link:
        assert pci.get_bound_driver('0000:18:00.0') == driver
        link.assert_called_once_with('/sys/bus/pci/devices/0000:18:00.0/driver')


def test_existing_unbound_device_has_no_driver():
    """Expect None for an unbound device; return None or fail the assertion."""
    with patch.object(pci.os.path, 'isdir', return_value=True), \
            patch.object(pci.os, 'readlink', side_effect=OSError(errno.ENOENT, 'no driver')):
        assert pci.get_bound_driver('0000:18:00.0') is None


@pytest.mark.parametrize('missing_device', [True, False])
def test_missing_device_and_unreadable_driver_are_errors(missing_device):
    """Require read errors to propagate; return None or fail if no error is raised."""
    with patch.object(pci.os.path, 'isdir', return_value=not missing_device), \
            patch.object(pci.os, 'readlink', side_effect=OSError(errno.EACCES, 'permission denied')):
        with pytest.raises(IOError):
            pci.get_bound_driver('0000:18:00.0')


def test_device_disappearing_during_read_is_not_an_unbound_device():
    """Require an error for a disappearing device; return None or fail the check."""
    with patch.object(pci.os.path, 'isdir', side_effect=[True, False]), \
            patch.object(pci.os, 'readlink', side_effect=OSError(errno.ENOENT, 'gone')):
        with pytest.raises(IOError):
            pci.get_bound_driver('0000:18:00.0')


@pytest.mark.parametrize('address', [
    '../../driver', '0000:18:00.0/driver', 'prefix0000:18:00.0',
    '10000000:18:00.0', '10000:18:00.0', '0000:100:00.0',
    '0000:18:20.0', '0000:18:00.8', '0000:18:00.-1', '', None,
])
def test_invalid_pci_address_is_rejected(address):
    """Reject the entire invalid address before accessing another device's sysfs."""
    with patch.object(pci.os.path, 'isdir') as isdir, \
            patch.object(pci.os, 'readlink') as readlink:
        with pytest.raises(ValueError, match='invalid PCI address'):
            pci.get_bound_driver(address)
        isdir.assert_not_called()
        readlink.assert_not_called()


@pytest.mark.parametrize('address, expected', [
    ('18:00.0', '0000:18:00.0'),
    ('00000000:18:00.0', '0000:18:00.0'),
    ('0x0000:0x18:0x00.0x0', '0000:18:00.0'),
    ('0000:18:00.0X7', '0000:18:00.7'),
    ('0000FFFF:FF:1F.7', 'ffff:ff:1f.7'),
])
def test_supported_pci_address_forms(address, expected):
    """Keep supported address forms and query the exact requested device."""
    with patch.object(pci.os.path, 'isdir', return_value=True), \
            patch.object(pci.os, 'readlink', return_value='../drivers/mlx5_core') as link:
        assert pci.get_bound_driver(address) == 'mlx5_core'
        link.assert_called_once_with('/sys/bus/pci/devices/' + expected + '/driver')


def test_query_reports_invalid_address_without_reading_sysfs():
    """Return an Agent failure for malformed input without reading a device."""
    plugin = vm_plugin.VmPlugin.__new__(vm_plugin.VmPlugin)
    with patch.object(vm_plugin.pci, 'get_bound_driver', side_effect=pci.get_bound_driver), \
            patch.object(pci.os.path, 'isdir') as isdir:
        response = json.loads(plugin.get_ib_device_driver(make_pci_request('0000:18:00.0/driver')))
        assert response['success'] is False
        assert 'invalid PCI address' in response['error']
        isdir.assert_not_called()


@pytest.mark.parametrize('driver', ['mlx5_core', 'vfio-pci', None])
def test_query_returns_current_driver_without_changing_it(driver):
    """Expect driver JSON and no shell command; return None or fail an assertion."""
    plugin = vm_plugin.VmPlugin.__new__(vm_plugin.VmPlugin)
    with patch.object(vm_plugin.pci, 'get_bound_driver', return_value=driver), \
            patch.object(vm_plugin.bash, 'bash_roe') as command:
        response = json.loads(plugin.get_ib_device_driver(make_pci_request()))
        assert response['success'] is True
        assert response.get('driver') == driver
        command.assert_not_called()


def test_query_reports_read_failure():
    """Expect a failed response with read details; return None or fail an assertion."""
    plugin = vm_plugin.VmPlugin.__new__(vm_plugin.VmPlugin)
    with patch.object(vm_plugin.pci, 'get_bound_driver', side_effect=IOError('device missing')):
        response = json.loads(plugin.get_ib_device_driver(make_pci_request()))
        assert response['success'] is False
        assert 'device missing' in response['error']


@pytest.mark.parametrize('device_type', ['IB_Controller', 'GPU_Video_Controller', 'Ethernet_Controller', None])
def test_original_detach_protocol_is_unchanged(device_type):
    """Expect the old detach response and no driver query; return None or fail checks."""
    plugin = vm_plugin.VmPlugin.__new__(vm_plugin.VmPlugin)
    with patch.object(vm_plugin.os.path, 'exists', return_value=False), \
            patch.object(vm_plugin, 'check_device_in_use'), \
            patch.object(vm_plugin.pci, 'get_bound_driver') as read, \
            patch.object(vm_plugin.bash, 'bash_roe', return_value=(0, '', '')):
        response = json.loads(plugin.detach_pci_device_from_host(make_pci_request(device_type=device_type)))
        assert response['success'] is True
        assert 'hostDriver' not in response
        read.assert_not_called()

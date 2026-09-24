from unittest.mock import MagicMock

import pytest

from tests.unit.zstacklib.real_linux import load_real_linux


linux = load_real_linux()


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_check_interface_configuration_exist_checks_ifcfg_first(monkeypatch):
    ifcfg_path = '/etc/sysconfig/network-scripts/ifcfg-eth0.100'
    monkeypatch.setattr(
        linux.os.path, 'exists', MagicMock(side_effect=lambda path: path == ifcfg_path))
    monkeypatch.setattr(
        linux.os.path, 'isdir',
        MagicMock(side_effect=AssertionError('keyfile directory should not be read')))

    assert linux.check_interface_configuration_exist(['eth0.100']) == ['eth0.100']


def test_check_interface_configuration_exist_parses_keyfiles(tmp_path, monkeypatch):
    keyfile_dir = tmp_path / 'system-connections'
    _write(
        keyfile_dir / 'vlan-eth0.100.nmconnection',
        '[connection]\n'
        'id=vlan-eth0.100\n'
        'type=vlan\n'
        'interface-name=eth0.100\n')
    _write(
        keyfile_dir / 'arbitrary-name.nmconnection',
        '[connection]\n'
        'id=customer-vlan\n'
        'type=vlan\n'
        '\n[vlan]\n'
        'parent=eth0\n'
        'id=200\n')
    monkeypatch.setattr(linux, 'NM_KEYFILE_DIRS', (str(keyfile_dir),))
    monkeypatch.setattr(linux.os.path, 'exists', MagicMock(return_value=False))

    result = linux.check_interface_configuration_exist(
        ['eth0.100', 'eth0.200', 'eth0.300'])

    assert result == ['eth0.100', 'eth0.200']


def test_update_bridge_interface_configuration_keeps_original_profile_guard(
        monkeypatch):
    monkeypatch.setattr(linux, 'check_bridge_with_interface', MagicMock())
    profile_check = MagicMock(return_value=['eth0.100'])
    monkeypatch.setattr(linux, 'check_interface_configuration_exist', profile_check)
    monkeypatch.setattr(linux, 'ip_link_set_net_device_nomaster', MagicMock())
    monkeypatch.setattr(linux, 'ip_link_set_net_device_master', MagicMock())

    with pytest.raises(Exception, match=r'static config files.*eth0.100'):
        linux.update_bridge_interface_configuration(
            'eth0.100', 'eth0.200', 'br0', 'l2-uuid')

    profile_check.assert_called_once_with(['eth0.200', 'eth0.100'])
    linux.ip_link_set_net_device_nomaster.assert_not_called()
    linux.ip_link_set_net_device_master.assert_not_called()

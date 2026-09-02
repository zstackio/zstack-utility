import sys
import types
import unittest
from unittest import mock


# The root zstacklib conftest mocks zstacklib.utils.linux before collection.
# Remove that mock and provide a netaddr stub so the real linux module can be imported
# while the other optional runtime modules remain mocked by conftest.
sys.modules.pop('zstacklib.utils.linux', None)
_netaddr = types.ModuleType('netaddr')
sys.modules['netaddr'] = _netaddr
_simplejson = types.ModuleType('simplejson')
_simplejson.dumps = mock.MagicMock(return_value='{}')
sys.modules['simplejson'] = _simplejson
_xxhash = types.ModuleType('xxhash')
sys.modules['xxhash'] = _xxhash

from zstacklib.utils import linux


class TestLinuxRouteIpv6(unittest.TestCase):

    def test_is_network_ip_using_detects_global_ipv6(self):
        def fake_shell_call(cmd, *args, **kwargs):
            if 'ip -4 addr show' in cmd:
                return 'inet 172.24.247.243/16 scope global zsn1\n'
            if 'ip -6 addr show' in cmd:
                self.assertIn('grep -v "inet6 fe80:"', cmd)
                return 'inet6 fd11:5:5:29::49:9074/64 scope global\n'
            return ''

        with mock.patch.object(linux, 'is_network_device_existing', return_value=True), \
                mock.patch.object(linux.shell, 'call', side_effect=fake_shell_call):
            self.assertTrue(linux.is_network_ip_using('zsn1'))

    def test_is_network_ip_using_ignores_ipv6_link_local_only(self):
        def fake_shell_call(cmd, *args, **kwargs):
            if 'ip -4 addr show' in cmd:
                return ''
            if 'ip -6 addr show' in cmd:
                self.assertIn('grep -v "inet6 fe80:"', cmd)
                return ''
            return ''

        with mock.patch.object(linux, 'is_network_device_existing', return_value=True), \
                mock.patch.object(linux.shell, 'call', side_effect=fake_shell_call):
            self.assertFalse(linux.is_network_ip_using('zsn1'))

    def test_delete_novlan_bridge_restores_ipv6_route_info(self):
        route_info = {
            'ipv4_addresses': [],
            'ipv6_addresses': ['fd11:5:5:29::49:9074/64'],
            'routes': [],
            'routes6': ['default via fd11:5:5:29::1 dev br_zsn1'],
            'direct_routes6': [],
            'connected_routes6': [],
        }
        shell_calls = []

        def fake_shell_call(cmd, *args, **kwargs):
            shell_calls.append(cmd)
            return ''

        with mock.patch.object(linux, 'is_network_device_existing', return_value=True), \
                mock.patch.object(linux, 'is_network_ip_using', return_value=True), \
                mock.patch.object(linux, 'is_vif_on_bridge', return_value=True), \
                mock.patch.object(linux, 'delete_bridge') as mock_delete, \
                mock.patch.object(linux, '_get_dev_route_info', return_value=route_info) as mock_get, \
                mock.patch.object(linux, '_restore_dev_route') as mock_restore, \
                mock.patch.object(linux.shell, 'call', side_effect=fake_shell_call):
            linux.delete_novlan_bridge('br_zsn1', 'zsn1')

        mock_get.assert_called_once_with('br_zsn1')
        mock_delete.assert_called_once_with('br_zsn1')
        mock_restore.assert_called_once_with('zsn1', route_info)
        self.assertIn('ip link set zsn1 up', shell_calls)


if __name__ == '__main__':
    unittest.main()

import unittest
from unittest.mock import patch

from zstacklib.utils import linux


class TestIpv6RouteRestore(unittest.TestCase):
    def test_restore_ipv6_route_drops_runtime_expiration(self):
        route_info = {
            'ipv4_addresses': [],
            'ipv6_addresses': [],
            'routes': [],
            'direct_routes6': [],
            'routes6': [
                'default via fe80::1 dev zsn1 proto ra metric 1024 '
                'expires 172sec hoplimit 64 pref medium'
            ],
        }

        with patch.object(linux.shell, 'call') as call:
            linux._restore_dev_route('br_zsn1', route_info)

        call.assert_called_once_with(
            'ip -6 route add default via fe80::1 dev br_zsn1 '
            'proto ra metric 1024 hoplimit 64 pref medium'
        )

    def test_build_ipv6_route_keeps_only_supported_values(self):
        route = (
            'default via fe80::1 dev zsn1 proto ra metric 1024 '
            'expires 172sec hoplimit 64 pref medium'
        )

        self.assertEqual(
            linux._build_ipv6_route(route, 'br_zsn1'),
            'default via fe80::1 dev br_zsn1 proto ra metric 1024 '
            'hoplimit 64 pref medium'
        )

    def test_restore_ipv6_route_keeps_routes_without_expiration(self):
        route_info = {
            'ipv4_addresses': [],
            'ipv6_addresses': [],
            'routes': [],
            'direct_routes6': [
                '2001:db8:1::/64 dev zsn1 proto kernel expires 172sec'
            ],
            'routes6': [],
        }

        with patch.object(linux.shell, 'call') as call:
            linux._restore_dev_route('br_zsn1', route_info)

        call.assert_called_once_with(
            'ip -6 route add 2001:db8:1::/64 dev br_zsn1 proto kernel'
        )

    @patch.object(linux, 'is_network_device_existing', return_value=True)
    @patch.object(linux, 'is_vif_on_bridge', return_value=True)
    @patch.object(linux, 'delete_bridge')
    @patch.object(linux, '_get_dev_route_info')
    @patch.object(linux, '_restore_dev_route')
    @patch.object(linux.shell, 'call')
    def test_delete_novlan_bridge_restores_ipv6_route_info(
            self, shell_call, restore_route, get_route_info, delete_bridge, is_vif, is_existing):
        route_info = {
            'ipv4_addresses': [],
            'ipv6_addresses': ['2001:db8::10/64'],
            'routes': [],
            'direct_routes6': [],
            'routes6': [],
        }
        get_route_info.return_value = route_info

        linux.delete_novlan_bridge('br_zsn1', 'zsn1')

        delete_bridge.assert_called_once_with('br_zsn1')
        restore_route.assert_called_once_with('zsn1', route_info)


if __name__ == '__main__':
    unittest.main()

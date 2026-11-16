import unittest

import mock

from kvmagent.plugins import mevoco


class FakeNetnsShell(object):
    def __init__(self, mac):
        self.mac = mac
        self.deleted_links = []

    def get_mac(self, link_name):
        return self.mac

    def del_link(self, link_name):
        self.deleted_links.append(link_name)


class TestUserdataVethPair(unittest.TestCase):
    def _run(self, outer_exist, inner_exist):
        shell = FakeNetnsShell('fa:16:3e:00:00:01' if inner_exist else None)
        patches = [
            mock.patch.object(mevoco.linux, 'is_network_device_existing', return_value=outer_exist),
            mock.patch.object(mevoco.iproute, 'IpNetnsShell', return_value=shell),
            mock.patch.object(mevoco.iproute, 'delete_link_no_error'),
            mock.patch.object(mevoco.iproute, 'add_link'),
            mock.patch.object(mevoco.iproute, 'set_link_attribute'),
        ]
        started = [p.start() for p in patches]
        try:
            mevoco.ensure_userdata_veth_pair('ns0', 'ud_outer9', 'ud_inner9', 65500)
            return shell, started[2], started[3], started[4]
        finally:
            for p in reversed(patches):
                p.stop()

    def test_keep_complete_pair(self):
        shell, delete_link, add_link, set_link_attribute = self._run(True, True)

        self.assertEqual([], shell.deleted_links)
        self.assertEqual(0, delete_link.call_count)
        self.assertEqual(0, add_link.call_count)
        self.assertEqual(0, set_link_attribute.call_count)

    def test_create_missing_pair(self):
        shell, delete_link, add_link, set_link_attribute = self._run(False, False)

        self.assertEqual([], shell.deleted_links)
        self.assertEqual(0, delete_link.call_count)
        add_link.assert_called_once_with('ud_outer9', 'veth', peer='ud_inner9')
        self.assertEqual(2, set_link_attribute.call_count)

    def test_recreate_when_outer_left_without_inner(self):
        shell, delete_link, add_link, set_link_attribute = self._run(True, False)

        self.assertEqual([], shell.deleted_links)
        delete_link.assert_called_once_with('ud_outer9')
        add_link.assert_called_once_with('ud_outer9', 'veth', peer='ud_inner9')
        self.assertEqual(2, set_link_attribute.call_count)

    def test_recreate_when_inner_left_without_outer(self):
        shell, delete_link, add_link, set_link_attribute = self._run(False, True)

        self.assertEqual(['ud_inner9'], shell.deleted_links)
        self.assertEqual(0, delete_link.call_count)
        add_link.assert_called_once_with('ud_outer9', 'veth', peer='ud_inner9')
        self.assertEqual(2, set_link_attribute.call_count)


class StatefulFakeNetnsShell(object):
    @staticmethod
    def list_netns():
        return ['br_eth0_l3uuid']

    def __init__(self, ip4=None, userdata_ip=None, mac='fa:16:3e:00:00:09'):
        self.ip4 = ip4
        self.ip6 = None
        self.userdata_ip = userdata_ip
        self.mac = mac
        self.link_up_calls = []

    def add_netns(self, ns_id):
        pass

    def get_ip_address(self, ip_version, link_name):
        if link_name and link_name.startswith('ud_inner'):
            return '169.254.64.2' if ip_version == 4 else None
        return self.ip4 if ip_version == 4 else self.ip6

    def get_userdata_ip_address(self, link_name):
        return self.userdata_ip

    def get_mac(self, link_name):
        return self.mac

    def get_link_name_by_ip(self, address, ip_version):
        if ip_version == 4 and self.ip4 == address:
            return 'inner0'
        return None

    def flush_ip_address(self, link_name):
        self.ip4 = None
        self.ip6 = None
        self.userdata_ip = None

    def add_ip_address(self, address, prefix, link_name):
        if link_name and link_name.startswith('ud_inner'):
            return
        if address == '169.254.169.254':
            self.userdata_ip = address
        else:
            self.ip4 = address

    def del_ip_address(self, address, link_name):
        if address == self.ip4:
            self.ip4 = None
        elif address == self.userdata_ip:
            self.userdata_ip = None

    def set_link_up(self, link_name):
        self.link_up_calls.append(link_name)


class TestDhcpUserdataRouteLifecycle(unittest.TestCase):
    def test_enable_disable_reenable_dhcp_route_lifecycle(self):
        shell = StatefulFakeNetnsShell(ip4='192.168.100.10', userdata_ip='169.254.169.254')
        bash_r_calls = []
        bash_err_calls = []

        ns_env = mevoco.DhcpNameSpaceEnv('br_eth0', 'br_eth0_l3uuid')
        ns_env.infra_env.near_vm_inner = 'inner0'
        ns_env.infra_env.prepare_dev = mock.MagicMock()
        ns_env._del_bridge_fdb_entry_for_inner_dev = mock.MagicMock()
        ns_env._del_dhcp4_tables = mock.MagicMock()
        ns_env._del_dhcp6_tables = mock.MagicMock()
        ns_env._prepare_dhcp4_iptables = mock.MagicMock()
        ns_env._add_bridge_fdb_entry_for_inner_dev = mock.MagicMock()

        with mock.patch.object(mevoco.iproute, 'IpNetnsShell', return_value=shell), \
             mock.patch.object(mevoco, 'write_file_if_changed', return_value=False), \
             mock.patch.object(mevoco, 'Template', return_value=mock.MagicMock(render=lambda *_: '')), \
             mock.patch.object(mevoco, 'bash_r', side_effect=lambda cmd: bash_r_calls.append(cmd) or 0), \
             mock.patch.object(mevoco, 'bash_errorout', side_effect=lambda cmd: bash_err_calls.append(cmd) or ''):
            # 1. Disable DHCP while Userdata (169.254.169.254) remains active:
            #    keep bridge FDB and add dev-only default route for metadata return traffic.
            ns_env.disable()
            self.assertIsNone(shell.ip4)
            self.assertEqual('169.254.169.254', shell.userdata_ip)
            self.assertEqual(0, ns_env._del_bridge_fdb_entry_for_inner_dev.call_count)
            self.assertIn('ip netns exec br_eth0_l3uuid ip -4 route replace default dev inner0', bash_err_calls)

            # 2. Re-enable DHCP via DhcpNameSpaceEnv._add_dhcp_ip_if_not_exist:
            #    restore subnet IP and remove dev-only default route.
            bash_r_calls.clear()
            bash_err_calls.clear()
            ns_env.dhcp_server_ip = '192.168.100.10'
            ns_env.dhcp_netmask = '255.255.255.0'
            with mock.patch.object(mevoco.linux, 'netmask_to_cidr', return_value=24):
                ns_env.enable()
            self.assertEqual('192.168.100.10', shell.ip4)
            self.assertEqual('169.254.169.254', shell.userdata_ip)
            self.assertTrue(any(
                'ip netns exec br_eth0_l3uuid ip -4 route del default dev inner0' in cmd
                for cmd in bash_r_calls
            ))
            self.assertEqual([], bash_err_calls)

            # 3. Disable DHCP when NO Userdata IP exists: remove FDB and do not add default route.
            shell.ip4 = '192.168.100.10'
            shell.userdata_ip = None
            bash_r_calls.clear()
            bash_err_calls.clear()
            ns_env.disable()
            self.assertEqual(1, ns_env._del_bridge_fdb_entry_for_inner_dev.call_count)
            self.assertEqual([], bash_err_calls)

    def test_dhcp_env_prepare_removes_stale_default_route(self):
        shell = StatefulFakeNetnsShell(ip4=None, userdata_ip='169.254.169.254')
        bash_r_calls = []

        dhcp_env = mevoco.DhcpEnv()
        dhcp_env.bridge_name = 'br_eth0'
        dhcp_env.vlan_id = None
        dhcp_env.dhcp_server_ip = '192.168.100.10'
        dhcp_env.dhcp_netmask = '255.255.255.0'
        dhcp_env.namespace_name = 'br_eth0_l3uuid'

        with mock.patch.object(mevoco.iproute, 'IpNetnsShell', side_effect=lambda *a, **kw: shell), \
             mock.patch.object(mevoco.iproute.IpNetnsShell, 'list_netns', return_value=['br_eth0_l3uuid']), \
             mock.patch.object(mevoco.ip, 'get_namespace_id', return_value='0'), \
             mock.patch.object(mevoco.linux, 'netmask_to_cidr', return_value=24), \
             mock.patch.object(mevoco.linux, 'is_network_device_existing', return_value=True), \
             mock.patch.object(mevoco.iproute, 'add_namespace_no_error'), \
             mock.patch.object(mevoco.iproute, 'set_link_up'), \
             mock.patch.object(mevoco.iproute, 'add_fdb_entry'), \
             mock.patch.object(mevoco.ovs, 'getOvsCtl', side_effect=mevoco.OvsError('no ovs')), \
             mock.patch.object(mevoco, 'write_file_if_changed', return_value=False), \
             mock.patch.object(mevoco, 'Template', return_value=mock.MagicMock(render=lambda *_: '')), \
             mock.patch.object(mevoco, 'bash_r', side_effect=lambda cmd: bash_r_calls.append(cmd) or 0), \
             mock.patch.object(mevoco, 'bash_roe', return_value=(0, 'eth0\n', '')), \
             mock.patch.object(mevoco, 'bash_errorout', return_value=''):
            dhcp_env.prepare()

        self.assertEqual('192.168.100.10', shell.ip4)
        self.assertEqual('169.254.169.254', shell.userdata_ip)
        self.assertTrue(any(
            'ip netns exec br_eth0_l3uuid ip -4 route del default dev inner0' in cmd
            for cmd in bash_r_calls
        ))

    def test_apply_userdata_xtables_syncs_default_route_with_and_without_dhcp(self):
        from zstacklib.utils import jsonobject

        plugin = mevoco.Mevoco.__new__(mevoco.Mevoco)
        plugin.config = {}
        plugin.userData_vms = {}
        plugin.work_userdata_iptables = mock.MagicMock()
        plugin.apply_zwatch_vm_agent = mock.MagicMock()

        # Case 1: DHCP disabled (no dhcpServerIp, no ip4 on inner0), even when ud_inner0 route exists
        shell_no_dhcp = StatefulFakeNetnsShell(ip4=None, userdata_ip=None)
        bash_r_calls = []
        bash_err_calls = []
        to_no_dhcp = jsonobject.loads(jsonobject.dumps({
            'bridgeName': 'br_eth0',
            'namespaceName': 'br_eth0_l3uuid',
            'vlanId': None,
            'l3NetworkUuid': 'l3uuid',
            'vmIp': '192.168.100.50',
            'netmask': '255.255.255.0',
            'port': 80,
        }))

        def _fake_prepare(self_env):
            self_env.inner_dev = 'inner0'
            self_env.outer_dev = 'outer0'

        with mock.patch.object(mevoco.UserDataEnv, 'prepare', _fake_prepare), \
             mock.patch.object(mevoco.iproute, 'IpNetnsShell', return_value=shell_no_dhcp), \
             mock.patch.object(mevoco.ip, 'get_namespace_id', return_value='0'), \
             mock.patch.object(mevoco, 'ensure_userdata_veth_pair'), \
             mock.patch.object(mevoco.linux, 'is_network_device_existing', return_value=True), \
             mock.patch.object(mevoco.iproute, 'set_link_up'), \
             mock.patch.object(mevoco.iproute, 'add_address_no_error'), \
             mock.patch.object(mevoco, 'get_phy_dev_from_bridge_name', return_value='eth0'), \
             mock.patch.object(mevoco.ip, 'IpAddress', return_value=mock.MagicMock(toCidr=lambda _: '192.168.100.50/24')), \
             mock.patch.object(mevoco.ip, 'removeZeroFromMacAddress', return_value='fa:16:3e:0:0:9'), \
             mock.patch.object(mevoco, 'write_file_if_changed', return_value=False), \
             mock.patch.object(mevoco, 'Template', return_value=mock.MagicMock(render=lambda *_: '')), \
             mock.patch.object(mevoco, 'bash_r', side_effect=lambda cmd: bash_r_calls.append(cmd) or 0), \
             mock.patch.object(mevoco, 'bash_o', return_value=''), \
             mock.patch.object(mevoco, 'bash_errorout', side_effect=lambda cmd: bash_err_calls.append(cmd) or ''):
            plugin._apply_userdata_xtables(to_no_dhcp)

        self.assertEqual('169.254.169.254', shell_no_dhcp.userdata_ip)
        self.assertIn('ip netns exec br_eth0_l3uuid ip -4 route replace default dev inner0', bash_err_calls)

        # Case 2: DHCP enabled (dhcpServerIp provided), deletes stale default dev inner0
        shell_with_dhcp = StatefulFakeNetnsShell(ip4='192.168.100.10', userdata_ip='169.254.169.254')
        bash_r_calls.clear()
        bash_err_calls.clear()
        to_with_dhcp = jsonobject.loads(jsonobject.dumps({
            'bridgeName': 'br_eth0',
            'namespaceName': 'br_eth0_l3uuid',
            'vlanId': None,
            'l3NetworkUuid': 'l3uuid',
            'dhcpServerIp': '192.168.100.10',
            'vmIp': '192.168.100.50',
            'netmask': '255.255.255.0',
            'port': 80,
        }))
        with mock.patch.object(mevoco.iproute, 'IpNetnsShell', return_value=shell_with_dhcp), \
             mock.patch.object(mevoco.ip, 'get_namespace_id', return_value='0'), \
             mock.patch.object(mevoco, 'ensure_userdata_veth_pair'), \
             mock.patch.object(mevoco.linux, 'is_network_device_existing', return_value=True), \
             mock.patch.object(mevoco.iproute, 'set_link_up'), \
             mock.patch.object(mevoco.iproute, 'add_address_no_error'), \
             mock.patch.object(mevoco, 'get_phy_dev_from_bridge_name', return_value='eth0'), \
             mock.patch.object(mevoco.ip, 'IpAddress', return_value=mock.MagicMock(toCidr=lambda _: '192.168.100.50/24')), \
             mock.patch.object(mevoco.ip, 'removeZeroFromMacAddress', return_value='fa:16:3e:0:0:9'), \
             mock.patch.object(mevoco, 'write_file_if_changed', return_value=False), \
             mock.patch.object(mevoco, 'Template', return_value=mock.MagicMock(render=lambda *_: '')), \
             mock.patch.object(mevoco, 'bash_r', side_effect=lambda cmd: bash_r_calls.append(cmd) or 0), \
             mock.patch.object(mevoco, 'bash_o', return_value=''), \
             mock.patch.object(mevoco, 'bash_errorout', side_effect=lambda cmd: bash_err_calls.append(cmd) or ''):
            plugin._apply_userdata_xtables(to_with_dhcp)

        self.assertTrue(any(
            'ip netns exec br_eth0_l3uuid ip -4 route del default dev inner0' in cmd
            for cmd in bash_r_calls
        ))
        self.assertNotIn('ip netns exec br_eth0_l3uuid ip -4 route replace default dev inner0', bash_err_calls)


if __name__ == "__main__":
    unittest.main()

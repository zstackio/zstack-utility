import unittest
import mock

from kvmagent.plugins.deip import Eip


def _make_eip(ipVersion=4):
    eip = mock.MagicMock()
    eip.nicName = "vnic1.0"
    eip.eipUuid = "abcdef123456789"
    eip.publicBridgeName = "br_eth0"
    eip.vmBridgeName = "br_eth1"
    eip.vip = "192.168.1.100"
    eip.vipNetmask = "255.255.255.0"
    eip.vipGateway = "192.168.1.1"
    eip.vipPrefixLen = 64
    eip.nicGateway = "10.0.0.1"
    eip.nicNetmask = "255.255.255.0"
    eip.nicPrefixLen = 24
    eip.nicIp = "10.0.0.100"
    eip.nicMac = "00:0c:29:aa:bb:cc"
    eip.vmUuid = "vm-uuid-1234"
    eip.vipUuid = "vip-uuid-5678"
    eip.ipVersion = ipVersion
    eip.addfdb = False
    eip.physicalNic = "eth0"
    eip.skipArpCheck = True
    return eip


# EIP_UUID[-9:] = '123456789'
# PUB_ODEV = '123456789_eo', PUB_IDEV = '123456789_ei'
# PRI_ODEV = '123456789_o',  PRI_IDEV = '123456789_i'
# NIC_NAME = 'vnic1.0'


def _make_fake_process(executed_cmds):
    """Create a fake shell.get_process that captures resolved commands."""

    def fake_get_process(cmd_path, pipe=True):
        proc = mock.MagicMock()

        def communicate(cmd_str):
            executed_cmds.append(cmd_str)
            # ip link show -> return a MAC for GATEWAY_MAC resolution
            if "ip link show" in cmd_str and "awk" in cmd_str:
                proc.returncode = 0
                return ("    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n", "")
            # ip -o -f inet addr show -> return a CIDR for perf monitor
            if "ip -o -f inet addr show" in cmd_str:
                proc.returncode = 0
                return (
                    "2: eth0    inet 10.0.0.100/24 brd 10.0.0.255 scope global eth0\n",
                    "",
                )
            # ip -o -f inet6 addr show
            if "ip -o -f inet6 addr show" in cmd_str:
                proc.returncode = 0
                return ("2: eth0    inet6 fd00::100/64 scope global\n", "")
            # ebtables -L ... --Lx -> return empty (no existing jump rules to old chains)
            if "--Lx" in cmd_str:
                proc.returncode = 0
                return ("", "")
            # default: success with empty output
            proc.returncode = 0
            return ("", "")

        proc.communicate = communicate
        proc.returncode = 0
        return proc

    return fake_get_process


# Patches common to all apply_eip tests
_APPLY_PATCHES = [
    mock.patch("kvmagent.plugins.deip.EBTABLES_CMD", "ebtables"),
    mock.patch("kvmagent.plugins.deip.IPTABLES_CMD", "iptables"),
    mock.patch("kvmagent.plugins.deip.IP6TABLES_CMD", "ip6tables"),
    mock.patch(
        "kvmagent.plugins.deip.ip.removeZeroFromMacAddress",
        return_value="0:c:29:aa:bb:cc",
    ),
]


class _ApplyEipTestBase(unittest.TestCase):
    """Base class that sets up mocks and runs apply_eip, capturing all shell commands."""

    IP_VERSION = 4  # override in subclass for v6

    def setUp(self):
        self.executed_cmds = []

        # Start common patches
        self._patchers = [p for p in _APPLY_PATCHES]
        self._patchers.append(
            mock.patch(
                "zstacklib.utils.shell.get_process",
                side_effect=_make_fake_process(self.executed_cmds),
            )
        )
        for p in self._patchers:
            p.start()

        # Mock iproute
        self.patcher_iproute = mock.patch("kvmagent.plugins.deip.iproute")
        self.mock_iproute = self.patcher_iproute.start()
        self.mock_iproute.IpNetnsShell.list_netns.return_value = []
        self.mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
            None  # force create
        )

        # Mock linux
        self.patcher_linux = mock.patch("kvmagent.plugins.deip.linux")
        self.mock_linux = self.patcher_linux.start()
        self.mock_linux.is_network_device_existing.return_value = False
        self.mock_linux.netmask_to_cidr.return_value = 24
        self.mock_linux.MAX_MTU_OF_VNIC = 65000

        # Mock file_lock (fcntl not available on all platforms, and lock file may not exist)
        self.patcher_fcntl = mock.patch(
            "kvmagent.plugins.deip.lock.file_lock", lambda name, **kw: lambda f: f
        )
        self.patcher_fcntl.start()

        # Mock lock.lock (threading lock, harmless but mock for safety)
        self.patcher_lock = mock.patch(
            "kvmagent.plugins.deip.lock.lock", lambda name="default": lambda f: f
        )
        self.patcher_lock.start()

        # Run apply_eip
        eip = _make_eip(ipVersion=self.IP_VERSION)
        eip_cmd = Eip()
        eip_cmd.apply_eip(eip)

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        self.patcher_iproute.stop()
        self.patcher_linux.stop()
        self.patcher_fcntl.stop()
        self.patcher_lock.stop()

    def _has_cmd(self, pattern):
        return any(pattern in cmd for cmd in self.executed_cmds)

    def _cmds_matching(self, pattern):
        return [cmd for cmd in self.executed_cmds if pattern in cmd]


# ---------------------------------------------------------------------------
# Test: eip- prefix on chain names
# ---------------------------------------------------------------------------
class TestApplyEipChainNames(_ApplyEipTestBase):
    def test_gateway_arp_chain_uses_eip_prefix(self):
        """set_gateway_arp_if_needed should create chain 'eip-vnic1.0-gw'."""
        self.assertTrue(
            self._has_cmd("eip-vnic1.0-gw"),
            "Expected 'eip-vnic1.0-gw' in commands:\n"
            + "\n".join(self._cmds_matching("vnic1.0")),
        )

    def test_block_arp_chains_use_eip_prefix(self):
        """Block ARP chains should have eip- prefix."""
        self.assertTrue(
            self._has_cmd("eip-123456789_o-arp"),
            "Expected 'eip-123456789_o-arp' (PRI_ODEV)",
        )
        self.assertTrue(
            self._has_cmd("eip-123456789_eo-arp"),
            "Expected 'eip-123456789_eo-arp' (PUB_ODEV)",
        )
        self.assertTrue(
            self._has_cmd("eip-vnic1.0-arp"), "Expected 'eip-vnic1.0-arp' (NIC_NAME)"
        )

    def test_pri_odev_filter_chain_uses_eip_prefix(self):
        """add_filter_to_prevent_namespace_arp_request should use 'eip-123456789_o-gw'."""
        self.assertTrue(
            self._has_cmd("eip-123456789_o-gw"),
            "Expected 'eip-123456789_o-gw' (PRI_ODEV filter chain)",
        )


class TestApplyEipPostroutingOrder(_ApplyEipTestBase):
    def test_postrouting_arp_jumps_are_inserted_at_head(self):
        expected = [
            "-I POSTROUTING -p ARP -o vnic1.0 -j eip-vnic1.0-arp",
            "-I POSTROUTING -p ARP -o 123456789_o -j eip-123456789_o-arp",
            "-I POSTROUTING -p ARP -o 123456789_eo -j eip-123456789_eo-arp",
        ]

        for rule in expected:
            self.assertTrue(
                self._has_cmd(rule),
                "Expected POSTROUTING ARP jump at head: %s" % rule,
            )

    def test_postrouting_arp_jumps_try_to_reorder_existing_rules(self):
        expected = [
            "-D POSTROUTING -p ARP -o vnic1.0 -j eip-vnic1.0-arp",
            "-D POSTROUTING -p ARP -o 123456789_o -j eip-123456789_o-arp",
            "-D POSTROUTING -p ARP -o 123456789_eo -j eip-123456789_eo-arp",
        ]

        for rule in expected:
            self.assertTrue(
                self._has_cmd(rule),
                "Expected POSTROUTING ARP jump reorder path: %s" % rule,
            )


# ---------------------------------------------------------------------------
# Test: ARP rules (arpreply source check, Reply DROP, gratuitous ARP)
# ---------------------------------------------------------------------------
class TestApplyEipArpRules(_ApplyEipTestBase):
    def test_arpreply_no_source_mac_check(self):
        """arpreply rule in set_gateway_arp_if_needed should NOT include --arp-mac-src (VM may have internal bridge)."""
        arpreply_cmds = [c for c in self.executed_cmds if 'arpreply' in c and 'eip-vnic1.0-gw' in c]
        mac_src_cmds = [c for c in arpreply_cmds if '--arp-mac-src' in c]
        self.assertEqual(
            len(mac_src_cmds), 0,
            "arpreply rule should NOT have --arp-mac-src, got:\n" + "\n".join(arpreply_cmds),
        )

    def test_arpreply_no_source_ip_check(self):
        """arpreply rule in set_gateway_arp_if_needed should NOT include --arp-ip-src (VM may have VIP)."""
        arpreply_cmds = [c for c in self.executed_cmds if 'arpreply' in c and 'eip-vnic1.0-gw' in c]
        ip_src_cmds = [c for c in arpreply_cmds if '--arp-ip-src' in c]
        self.assertEqual(
            len(ip_src_cmds), 0,
            "arpreply rule should NOT have --arp-ip-src, got:\n" + "\n".join(arpreply_cmds),
        )

    def test_arp_reply_drop_rules_for_nic_name_chain(self):
        """NIC_NAME arp chain should have ARP Reply DROP rules with gateway MAC check."""
        reply_drop_cmds = [
            c
            for c in self.executed_cmds
            if "--arp-op Reply" in c and "-j DROP" in c and "10.0.0.1" in c
        ]
        self.assertTrue(
            len(reply_drop_cmds) > 0,
            "Expected ARP Reply DROP rule for NIC_GATEWAY 10.0.0.1",
        )

    def test_pri_odev_chain_dnat_rule(self):
        """PRI_ODEV filter chain should dnat namespace gateway ARP to VM MAC (unicast)."""
        dnat_cmds = [
            c
            for c in self.executed_cmds
            if "dnat" in c and "10.0.0.1" in c and "eip-123456789_o-gw" in c
        ]
        self.assertTrue(
            len(dnat_cmds) > 0,
            "Expected dnat rule for NIC_GATEWAY in PRI_ODEV chain, got:\n"
            + "\n".join(self._cmds_matching("eip-123456789_o-gw")),
        )

    def test_pri_odev_chain_catchall_drop(self):
        """PRI_ODEV filter chain should have a catchall ARP DROP (after dnat)."""
        drop_cmds = [
            c
            for c in self.executed_cmds
            if "eip-123456789_o-gw" in c and "-p ARP -j DROP" in c
        ]
        self.assertTrue(
            len(drop_cmds) > 0,
            "Expected catchall '-p ARP -j DROP' in PRI_ODEV chain",
        )

    def test_pri_odev_chain_no_blanket_request_drop(self):
        """PRI_ODEV chain should NOT have blanket '--arp-op Request -j DROP' (blocks gratuitous ARP)."""
        blanket_req_drop = [
            c
            for c in self.executed_cmds
            if "eip-123456789_o-gw" in c and "--arp-op Request" in c and "-j DROP" in c
        ]
        self.assertEqual(
            len(blanket_req_drop), 0,
            "PRI_ODEV chain should NOT have blanket Request DROP, got:\n"
            + "\n".join(blanket_req_drop),
        )

    def test_gratuitous_arp_sent_after_ebtables(self):
        """After set_gateway_arp_if_needed, a gratuitous ARP should be sent via PRI_IDEV."""
        garp_cmds = [
            c
            for c in self.executed_cmds
            if "arping" in c and "-U" in c and "123456789_i" in c and "10.0.0.1" in c
        ]
        self.assertTrue(
            len(garp_cmds) > 0, "Expected 'arping -q -U ... -I 123456789_i 10.0.0.1'"
        )

    def test_gratuitous_arp_after_gateway_arp_setup(self):
        """Gratuitous ARP command should appear AFTER the eip-vnic1.0-gw chain setup."""
        gw_chain_idx = None
        garp_idx = None
        for i, cmd in enumerate(self.executed_cmds):
            if "eip-vnic1.0-gw" in cmd and gw_chain_idx is None:
                gw_chain_idx = i
            if "arping" in cmd and "-U" in cmd and "123456789_i" in cmd:
                garp_idx = i
        self.assertIsNotNone(gw_chain_idx, "Gateway ARP chain setup not found")
        self.assertIsNotNone(garp_idx, "Gratuitous ARP command not found")
        self.assertGreater(
            garp_idx,
            gw_chain_idx,
            "Gratuitous ARP should come after gateway chain setup",
        )


# ---------------------------------------------------------------------------
# Test: Legacy chain cleanup during apply
# ---------------------------------------------------------------------------
class TestApplyEipLegacyCleanup(_ApplyEipTestBase):
    def test_legacy_gw_chain_cleanup(self):
        """After setting eip-vnic1.0-gw, should attempt to check/delete old 'vnic1.0-gw'."""
        # delete_ebtables_chain_if_exists checks if old chain exists
        legacy_cmds = [
            c for c in self.executed_cmds if "vnic1.0-gw" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_cmds) > 0,
            "Expected cleanup attempt for legacy chain 'vnic1.0-gw'",
        )

    def test_legacy_block_arp_chain_cleanup(self):
        """Should attempt to clean up old {DEV}-arp chains (without eip- prefix)."""
        # PRI_ODEV-arp = 123456789_o-arp
        legacy_pri = [
            c for c in self.executed_cmds if "123456789_o-arp" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_pri) > 0, "Expected cleanup for legacy '123456789_o-arp'"
        )
        # PUB_ODEV-arp = 123456789_eo-arp
        legacy_pub = [
            c for c in self.executed_cmds if "123456789_eo-arp" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_pub) > 0, "Expected cleanup for legacy '123456789_eo-arp'"
        )
        # NIC_NAME-arp = vnic1.0-arp
        legacy_nic = [
            c for c in self.executed_cmds if "vnic1.0-arp" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_nic) > 0, "Expected cleanup for legacy 'vnic1.0-arp'"
        )

    def test_legacy_pri_odev_gw_cleanup(self):
        """add_filter_to_prevent_namespace_arp_request should clean old '{PRI_ODEV}-gw'."""
        legacy_cmds = [
            c for c in self.executed_cmds if "123456789_o-gw" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_cmds) > 0, "Expected cleanup for legacy '123456789_o-gw'"
        )


# ---------------------------------------------------------------------------
# Test: IPv6 apply path
# ---------------------------------------------------------------------------
class TestApplyEipV6ChainNames(_ApplyEipTestBase):
    IP_VERSION = 6

    def test_v6_gateway_chain_uses_eip_prefix(self):
        """set_gateway_arp_if_needed_v6 should create chain 'eip-vnic1.0-gw'."""
        self.assertTrue(
            self._has_cmd("eip-vnic1.0-gw"), "Expected 'eip-vnic1.0-gw' in IPv6 path"
        )

    def test_v6_legacy_gw_chain_cleanup(self):
        """IPv6 path should clean up old 'vnic1.0-gw' chain."""
        legacy_cmds = [
            c for c in self.executed_cmds if "vnic1.0-gw" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_cmds) > 0,
            "Expected cleanup for legacy 'vnic1.0-gw' in IPv6 path",
        )


# ---------------------------------------------------------------------------
# Test: delete path legacy cleanup
# ---------------------------------------------------------------------------
class _DeleteEipTestBase(unittest.TestCase):
    """Base for delete_eip_with_ns tests."""

    IP_VERSION = 4

    def setUp(self):
        self.executed_cmds = []

        self._patchers = [p for p in _APPLY_PATCHES]
        self._patchers.append(
            mock.patch(
                "zstacklib.utils.shell.get_process",
                side_effect=_make_fake_process(self.executed_cmds),
            )
        )
        for p in self._patchers:
            p.start()

        self.patcher_iproute = mock.patch("kvmagent.plugins.deip.iproute")
        self.mock_iproute = self.patcher_iproute.start()

        self.patcher_linux = mock.patch("kvmagent.plugins.deip.linux")
        self.mock_linux = self.patcher_linux.start()
        self.mock_linux.is_network_device_existing.return_value = False

        self.patcher_fcntl = mock.patch(
            "kvmagent.plugins.deip.lock.file_lock", lambda name, **kw: lambda f: f
        )
        self.patcher_fcntl.start()

        self.patcher_lock = mock.patch(
            "kvmagent.plugins.deip.lock.lock", lambda name="default": lambda f: f
        )
        self.patcher_lock.start()

        eip_cmd = Eip()
        eip_cmd.delete_eip_with_ns(
            ns="br_eth0_192_168_1_100",
            eip_uuid="abcdef123456789",
            version=self.IP_VERSION,
            nic_name="vnic1.0",
        )

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        self.patcher_iproute.stop()
        self.patcher_linux.stop()
        self.patcher_fcntl.stop()
        self.patcher_lock.stop()

    def _has_cmd(self, pattern):
        return any(pattern in cmd for cmd in self.executed_cmds)

    def _cmds_matching(self, pattern):
        return [cmd for cmd in self.executed_cmds if pattern in cmd]


class TestDeleteArpRulesLegacyCleanup(_DeleteEipTestBase):
    IP_VERSION = 4

    def test_delete_uses_eip_prefix_chain_names(self):
        """delete_arp_rules should reference eip- prefixed chain names."""
        self.assertTrue(
            self._has_cmd("eip-vnic1.0-gw"), "Expected 'eip-vnic1.0-gw' in delete path"
        )
        self.assertTrue(
            self._has_cmd("eip-123456789_o-gw"),
            "Expected 'eip-123456789_o-gw' in delete path",
        )

    def test_delete_cleans_legacy_gw_chain(self):
        """delete_arp_rules should clean up old 'vnic1.0-gw' chain."""
        legacy_cmds = [
            c for c in self.executed_cmds if "vnic1.0-gw" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_cmds) > 0,
            "Expected cleanup for legacy 'vnic1.0-gw' in delete path",
        )

    def test_delete_cleans_legacy_pri_odev_gw(self):
        """delete_arp_rules should clean up old '{PRI_ODEV}-gw' chain."""
        legacy_cmds = [
            c for c in self.executed_cmds if "123456789_o-gw" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_cmds) > 0,
            "Expected cleanup for legacy '123456789_o-gw' in delete path",
        )

    def test_delete_cleans_legacy_block_arp_chains(self):
        """delete_arp_rules should clean up old {DEV}-arp chains."""
        for dev in ["123456789_o", "123456789_eo", "vnic1.0"]:
            pattern = "%s-arp" % dev
            legacy = [c for c in self.executed_cmds if pattern in c and "eip-" not in c]
            self.assertTrue(
                len(legacy) > 0, "Expected cleanup for legacy '%s'" % pattern
            )


class TestDeleteIpv6RulesLegacyCleanup(_DeleteEipTestBase):
    IP_VERSION = 6

    def test_delete_v6_uses_eip_prefix(self):
        """delete_ipv6_rules should reference eip- prefixed chain name."""
        self.assertTrue(
            self._has_cmd("eip-vnic1.0-gw"),
            "Expected 'eip-vnic1.0-gw' in IPv6 delete path",
        )

    def test_delete_v6_cleans_legacy_gw_chain(self):
        """delete_ipv6_rules should clean up old 'vnic1.0-gw' chain."""
        legacy_cmds = [
            c for c in self.executed_cmds if "vnic1.0-gw" in c and "eip-" not in c
        ]
        self.assertTrue(
            len(legacy_cmds) > 0,
            "Expected cleanup for legacy 'vnic1.0-gw' in IPv6 delete path",
        )


if __name__ == "__main__":
    unittest.main()

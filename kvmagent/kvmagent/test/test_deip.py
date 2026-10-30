import sys
import unittest
import mock
try:
    from types import SimpleNamespace
except ImportError:
    class SimpleNamespace(object):
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

from kvmagent.plugins.deip import DEip, Eip


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
    if ipVersion == 6:
        eip.vip = "fd00:1::100"
        eip.vipGateway = "fd00:1::1"
        eip.nicGateway = "fd00:2::1"
        eip.nicIp = "fd00:2::100"
    return eip


# EIP_UUID[-9:] = '123456789'
# PUB_ODEV = '123456789_eo', PUB_IDEV = '123456789_ei'
# PRI_ODEV = '123456789_o',  PRI_IDEV = '123456789_i'
# NIC_NAME = 'vnic1.0'


def _make_fake_process(executed_cmds):
    """Create a fake shell.get_process that captures resolved commands."""

    def fake_get_process(*args, **kwargs):
        cmd_path = args[0] if args else kwargs.get("cmd_path")
        proc = mock.MagicMock()

        def communicate(*args, **kwargs):
            command = args[0] if args else cmd_path
            if isinstance(command, bytes):
                command = command.decode()
            executed_cmds.append(command)
            # ip link show -> return a MAC for GATEWAY_MAC resolution
            if "ip link show" in command and "awk" in command:
                proc.returncode = 0
                return (b"    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff\n", b"")
            # ip -o -f inet addr show -> return a CIDR for perf monitor
            if "ip -o -f inet addr show" in command:
                proc.returncode = 0
                return (b"10.0.0.100/24\n", b"")
            # ip -o -f inet6 addr show
            if "ip -o -f inet6 addr show" in command:
                proc.returncode = 0
                return (b"fd00:2::100/64\n", b"")
            if "ip -o -4 addr show dev" in command:
                proc.returncode = 0
                return (b"10.0.0.1\n", b"")
            if "brctl show" in command or "route | grep -w default" in command:
                proc.returncode = 1
                return ("", "")
            # ebtables -L ... --Lx -> return empty (no existing jump rules to old chains)
            if "--Lx" in command:
                proc.returncode = 0
                return ("", "")
            # default: success with empty output
            proc.returncode = 0
            return ("", "")

        proc.communicate = communicate
        proc.returncode = 0
        return proc

    return fake_get_process


def _apply_patchers():
    return [
        mock.patch("kvmagent.plugins.deip.EBTABLES_CMD", "ebtables", create=True),
        mock.patch("kvmagent.plugins.deip.IPTABLES_CMD", "iptables", create=True),
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
        self._patchers = _apply_patchers()
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

        # Exercise the handler with its actual decorators; external commands are mocked.
        eip = _make_eip(ipVersion=self.IP_VERSION)
        eip_cmd = Eip()
        self._apply_eip(eip_cmd, eip)

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        self.patcher_iproute.stop()
        self.patcher_linux.stop()

    def _has_cmd(self, pattern):
        return any(pattern in cmd for cmd in self.executed_cmds)

    def _cmds_matching(self, pattern):
        return [cmd for cmd in self.executed_cmds if pattern in cmd]

    def _call_method(self, obj, method_name, *args, **kwargs):
        method = getattr(type(obj), method_name)
        method(obj, *args, **kwargs)

    def _apply_eip(self, eip_cmd, eip):
        self._call_method(eip_cmd, "apply_eip", eip)


class TestZSTAC86874PrepareEip(_ApplyEipTestBase):
    def _apply_eip(self, eip_cmd, eip):
        self._call_method(eip_cmd, "apply_eip", eip, False)

    def test_interface_alias_keeps_existing_schema(self):
        aliases = [
            call[1]["alias"]
            for call in self.mock_iproute.set_link_attribute.call_args_list
            if "alias" in call[1]
        ]
        self.assertTrue(aliases)
        self.assertFalse(any("vip_gateway:" in alias for alias in aliases))

    def test_public_outer_interface_stays_disabled_during_prepare(self):
        namespace = self.mock_iproute.IpNetnsShell.return_value
        self.assertIn(mock.call("123456789_ei"), namespace.set_link_up.call_args_list)
        self.assertNotIn(
            mock.call("123456789_eo"),
            self.mock_iproute.set_link_up.call_args_list,
        )
        self.mock_iproute.set_link_down.assert_called_with("123456789_eo")
        route_index = next(
            i for i, cmd in enumerate(self.executed_cmds)
            if "route add default via 192.168.1.1" in cmd
        )
        bridge_index = next(
            i for i, cmd in enumerate(self.executed_cmds)
            if "brctl addif br_eth0 123456789_eo" in cmd
        )
        self.assertLess(route_index, bridge_index)

    def test_repeated_prepare_disables_existing_public_outer_interface_first(self):
        self.mock_linux.is_network_device_existing.return_value = True
        self.mock_iproute.reset_mock()
        del self.executed_cmds[:]

        self._call_method(Eip(), "apply_eip", _make_eip(), False)

        self.mock_iproute.set_link_down.assert_any_call("123456789_eo")
        self.assertNotIn(
            mock.call("123456789_eo"),
            self.mock_iproute.set_link_up.call_args_list,
        )

    def test_does_not_announce_public_vip(self):
        self.assertFalse(
            self._has_cmd("arping -q -A"),
            "Passive prepare must not announce the public VIP",
        )

    def test_does_not_announce_private_gateway(self):
        self.assertFalse(
            self._has_cmd("arping -q -U"),
            "Passive prepare must not change the VM gateway MAC cache",
        )


class TestZSTAC86874EipPublicInterfaceState(unittest.TestCase):
    def setUp(self):
        self.eip = _make_eip()
        self.executed_cmds = []
        self.iproute_patcher = mock.patch("kvmagent.plugins.deip.iproute")
        self.mock_iproute = self.iproute_patcher.start()
        self.linux_patcher = mock.patch("kvmagent.plugins.deip.linux")
        self.mock_linux = self.linux_patcher.start()
        self.mock_linux.is_network_device_existing.return_value = True
        self.process_patcher = mock.patch(
            "zstacklib.utils.shell.get_process",
            side_effect=_make_fake_process(self.executed_cmds),
        )
        self.process_patcher.start()

    def tearDown(self):
        self.process_patcher.stop()
        self.linux_patcher.stop()
        self.iproute_patcher.stop()

    def test_enable_is_idempotent_and_announces_vip(self):
        self.mock_iproute.IpNetnsShell.list_netns.return_value = [
            "br_eth0_192_168_1_100"
        ]
        self.mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
            "aa:bb:cc:dd:ee:ff"
        )

        Eip().set_eip_public_interface_state(self.eip, True)

        self.mock_iproute.set_link_up.assert_called_once_with("123456789_eo")
        self.mock_iproute.IpNetnsShell.return_value.set_link_up.assert_not_called()
        self.assertTrue(any("arping -q -A" in cmd for cmd in self.executed_cmds))
        self.assertTrue(any("arping -q -U" in cmd for cmd in self.executed_cmds))
        self.assertTrue(
            any(
                "route add default via 192.168.1.1" in cmd
                for cmd in self.executed_cmds
            )
        )

    def test_public_and_private_announcements_run_in_parallel_and_wait(self):
        self.mock_iproute.IpNetnsShell.list_netns.return_value = [
            "br_eth0_192_168_1_100"
        ]
        self.mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
            "aa:bb:cc:dd:ee:ff"
        )

        Eip().set_eip_public_interface_state(self.eip, True)

        announce_commands = [
            command for command in self.executed_cmds
            if "arping -q -A" in command and "arping -q -U" in command
        ]
        self.assertEqual(1, len(announce_commands))
        self.assertIn(" & ", announce_commands[0])
        self.assertTrue(announce_commands[0].endswith(" & wait"))

    def test_disable_missing_namespace_is_idempotent(self):
        self.mock_iproute.IpNetnsShell.list_netns.return_value = []

        Eip().set_eip_public_interface_state(self.eip, False)

        self.assertFalse(
            any("ip link set 123456789_ei down" in cmd for cmd in self.executed_cmds)
        )

    def test_enable_missing_namespace_fails(self):
        self.mock_iproute.IpNetnsShell.list_netns.return_value = []

        with self.assertRaisesRegexp(Exception, "cannot find EIP namespace"):
            Eip().set_eip_public_interface_state(self.eip, True)

    def test_enable_incomplete_namespace_fails_before_public_interface_is_up(self):
        self.mock_iproute.IpNetnsShell.list_netns.return_value = [
            "br_eth0_192_168_1_100"
        ]
        self.mock_iproute.IpNetnsShell.return_value.get_mac.side_effect = [
            "aa:bb:cc:dd:ee:ff",
            None,
        ]

        with self.assertRaisesRegexp(Exception, "cannot find EIP private interface"):
            Eip().set_eip_public_interface_state(self.eip, True)

        self.mock_iproute.IpNetnsShell.return_value.set_link_up.assert_not_called()

    def test_ipv6_enable_configures_neighbor_notify_and_waits_for_dad(self):
        self.eip = _make_eip(6)
        self.mock_iproute.IpNetnsShell.list_netns.return_value = [
            "br_eth0_fd00:1::100"
        ]
        self.mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
            "aa:bb:cc:dd:ee:ff"
        )
        self.mock_linux.wait_callback_success.return_value = True

        Eip().set_eip_public_interface_state(self.eip, True)

        self.assertTrue(any(
            "sysctl -w net.ipv6.conf.123456789_ei.ndisc_notify=1" in cmd
            for cmd in self.executed_cmds
        ))
        self.mock_iproute.set_link_up.assert_called_once_with("123456789_eo")
        self.mock_linux.wait_callback_success.assert_called_once()

    def test_ipv6_enable_fails_when_dad_does_not_finish(self):
        self.eip = _make_eip(6)
        self.mock_iproute.IpNetnsShell.list_netns.return_value = [
            "br_eth0_fd00:1::100"
        ]
        self.mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
            "aa:bb:cc:dd:ee:ff"
        )
        self.mock_linux.wait_callback_success.return_value = False

        with self.assertRaisesRegexp(Exception, "DAD"):
            Eip().set_eip_public_interface_state(self.eip, True)


class TestZSTAC86874EipMigrationEvent(unittest.TestCase):
    def setUp(self):
        self.libvirt = SimpleNamespace(
            VIR_DOMAIN_EVENT_STARTED=2,
            VIR_DOMAIN_EVENT_STARTED_MIGRATED=1,
            VIR_DOMAIN_EVENT_RESUMED=4,
            VIR_DOMAIN_EVENT_RESUMED_MIGRATED=1,
            VIR_DOMAIN_EVENT_STOPPED=5,
            VIR_DOMAIN_EVENT_STOPPED_MIGRATED=3,
            VIR_DOMAIN_RUNNING=1,
            VIR_DOMAIN_PAUSED=3,
        )
        self.plugin = DEip()
        self.domain = mock.MagicMock()
        self.domain.name.return_value = "vm-uuid-1234"

    def _dispatch(self, event, detail, domain_state=None):
        if domain_state is not None:
            self.domain.state.return_value = (domain_state, 0)
        with mock.patch.dict(sys.modules, {"libvirt": self.libvirt}):
            with mock.patch(
                "kvmagent.plugins.deip.thread.ThreadFacade.run_in_thread"
            ) as run_in_thread:
                self.plugin._on_vm_lifecycle_event(
                    None, self.domain, event, detail, None
                )
                return run_in_thread

    def test_source_stopped_migrated_disables_eip(self):
        run_in_thread = self._dispatch(
            self.libvirt.VIR_DOMAIN_EVENT_STOPPED,
            self.libvirt.VIR_DOMAIN_EVENT_STOPPED_MIGRATED,
        )

        run_in_thread.assert_called_once_with(
            self.plugin._set_eips_public_interface_state_by_vm_uuid,
            ("vm-uuid-1234", False),
        )

    def test_destination_resumed_migrated_enables_eip(self):
        run_in_thread = self._dispatch(
            self.libvirt.VIR_DOMAIN_EVENT_RESUMED,
            self.libvirt.VIR_DOMAIN_EVENT_RESUMED_MIGRATED,
        )

        run_in_thread.assert_called_once_with(
            self.plugin._set_eips_public_interface_state_by_vm_uuid,
            ("vm-uuid-1234", True),
        )

    def test_started_migrated_only_enables_running_domain(self):
        paused = self._dispatch(
            self.libvirt.VIR_DOMAIN_EVENT_STARTED,
            self.libvirt.VIR_DOMAIN_EVENT_STARTED_MIGRATED,
            self.libvirt.VIR_DOMAIN_PAUSED,
        )
        paused.assert_not_called()

        running = self._dispatch(
            self.libvirt.VIR_DOMAIN_EVENT_STARTED,
            self.libvirt.VIR_DOMAIN_EVENT_STARTED_MIGRATED,
            self.libvirt.VIR_DOMAIN_RUNNING,
        )
        running.assert_called_once()

    def test_unrelated_event_is_ignored(self):
        run_in_thread = self._dispatch(
            self.libvirt.VIR_DOMAIN_EVENT_STOPPED,
            0,
        )

        run_in_thread.assert_not_called()

    def test_parser_ignores_transitional_gateway_metadata(self):
        alias = (
            "eip:abcdef123456789,eip_addr:192.168.1.100,"
            "vnic:vnic1.0,vnic_ip:10.0.0.100,"
            "vm:vm-uuid-1234,vip:vip-uuid-5678,"
            "vip_gateway:192.168.1.1"
        )

        parsed = Eip().parse_eip_string(alias)

        self.assertEqual(7, len(parsed))
        self.assertEqual("vip-uuid-5678", parsed[1])

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_alias_metadata_recovers_all_eips_for_vm(self, bash_o):
        alias = (
            "eip:abcdef123456789,eip_addr:192.168.1.100,"
            "vnic:vnic1.0,vnic_ip:10.0.0.100,"
            "vm:vm-uuid-1234,vip:vip-uuid-5678"
        )
        bash_o.return_value = "1: dev0 alias %s\n2: dev1 alias %s" % (alias, alias)

        with mock.patch.object(Eip, "find_namespace_name_by_ip",
                               return_value="br_eth0_192_168_1_100"):
            with mock.patch.object(Eip, "set_public_interface_state") as set_state:
                with mock.patch.object(Eip, "announce_public_interface") as announce:
                    with mock.patch(
                        "kvmagent.plugins.deip.thread.ThreadFacade.run_in_thread"
                    ) as run_in_thread:
                        self.plugin._set_eips_public_interface_state_by_vm_uuid(
                            "vm-uuid-1234", True
                        )

        set_state.assert_called_once_with(
            "br_eth0_192_168_1_100",
            "abcdef123456789",
            "192.168.1.100",
            4,
            True,
            False,
            announce=False,
        )
        run_in_thread.assert_called_once()
        self.assertEqual(
            (("br_eth0_192_168_1_100", "abcdef123456789", "192.168.1.100", 4),),
            run_in_thread.call_args.kwargs["args"],
        )

    def test_all_eips_switch_before_parallel_announcement(self):
        first = _make_eip()
        second = _make_eip()
        second.eipUuid = "abcdef987654321"
        second.vip = "192.168.1.101"
        calls = []

        with mock.patch.object(
            Eip,
            "set_eip_public_interface_state",
            side_effect=lambda eip, active, announce=True: calls.append(
                ("switch", eip.eipUuid, active, announce)
            ) or True,
        ):
            with mock.patch(
                "kvmagent.plugins.deip.thread.ThreadFacade.run_in_thread",
                side_effect=lambda func, args, kwargs: (
                    calls.append(("announce", args[0][1])) or mock.MagicMock()
                ),
            ):
                self.plugin._set_eips_public_interface_state([first, second], True)

        self.assertEqual(
            ["switch", "switch", "announce", "announce"],
            [call[0] for call in calls],
        )

    def test_batch_enable_waits_and_propagates_announcement_failure(self):
        eip_cmd = mock.MagicMock()
        eip_cmd.announce_public_interface.side_effect = Exception("DAD failed")

        def run_worker(worker, args, kwargs):
            worker(*args, **kwargs)
            thread = mock.MagicMock()
            return thread

        with mock.patch(
            "kvmagent.plugins.deip.thread.ThreadFacade.run_in_thread",
            side_effect=run_worker,
        ):
            with self.assertRaisesRegexp(Exception, "DAD failed"):
                self.plugin._announce_public_interfaces(
                    eip_cmd,
                    [("namespace", "eip-uuid", "fd00::10", 6)],
                )

    def test_batch_enable_returns_all_eips_to_passive_on_announcement_failure(self):
        eip = _make_eip(6)

        with mock.patch.object(
            Eip,
            "set_eip_public_interface_state",
            side_effect=[True, True],
        ) as set_state:
            with mock.patch.object(
                self.plugin,
                "_announce_public_interfaces",
                side_effect=Exception("DAD failed"),
            ):
                with self.assertRaisesRegexp(Exception, "DAD failed"):
                    self.plugin._set_eips_public_interface_state([eip], True)

        self.assertEqual(
            [mock.call(eip, True, announce=False),
             mock.call(eip, False, announce=False)],
            set_state.call_args_list,
        )

    def test_batch_enable_returns_current_eip_to_passive_on_switch_failure(self):
        eip = _make_eip()

        with mock.patch.object(
            Eip,
            "set_eip_public_interface_state",
            side_effect=[Exception("route setup failed"), True],
        ) as set_state:
            with self.assertRaisesRegexp(Exception, "route setup failed"):
                self.plugin._set_eips_public_interface_state([eip], True)

        self.assertEqual(
            [mock.call(eip, True, announce=False),
             mock.call(eip, False, announce=False)],
            set_state.call_args_list,
        )

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_lifecycle_enable_returns_current_eip_to_passive_on_switch_failure(
            self, bash_o):
        bash_o.return_value = (
            "eip:abcdef123456789,eip_addr:192.168.1.100,"
            "vnic:vnic1.0,vnic_ip:10.0.0.100,"
            "vm:vm-uuid-1234,vip:vip-uuid-5678"
        )

        with mock.patch.object(
            Eip,
            "find_namespace_name_by_ip",
            return_value="br_eth0_192_168_1_100",
        ):
            with mock.patch.object(
                Eip,
                "set_public_interface_state",
                side_effect=[Exception("route setup failed"), True],
            ) as set_state:
                with self.assertRaisesRegexp(Exception, "route setup failed"):
                    self.plugin._set_eips_public_interface_state_by_vm_uuid(
                        "vm-uuid-1234", True
                    )

        self.assertEqual(
            [
                mock.call(
                    "br_eth0_192_168_1_100",
                    "abcdef123456789",
                    "192.168.1.100",
                    4,
                    True,
                    False,
                    announce=False,
                ),
                mock.call(
                    "br_eth0_192_168_1_100",
                    "abcdef123456789",
                    "192.168.1.100",
                    4,
                    False,
                    False,
                    announce=False,
                ),
            ],
            set_state.call_args_list,
        )


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

    def test_prerouting_ipv4_gateway_jump_try_to_reorder_existing_rule(self):
        expected = [
            "-D PREROUTING -p ARP -i vnic1.0 -j eip-vnic1.0-gw",
            "-I PREROUTING -p ARP -i vnic1.0 -j eip-vnic1.0-gw",
        ]

        for rule in expected:
            self.assertTrue(
                self._has_cmd(rule),
                "Expected IPv4 PREROUTING gateway jump reorder path: %s" % rule,
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

    def test_v6_prerouting_gateway_jump_try_to_reorder_existing_rule(self):
        expected = [
            "-D PREROUTING -i vnic1.0 -j eip-vnic1.0-gw",
            "-I PREROUTING -i vnic1.0 -j eip-vnic1.0-gw",
        ]

        for rule in expected:
            self.assertTrue(
                self._has_cmd(rule),
                "Expected IPv6 PREROUTING gateway jump reorder path: %s" % rule,
            )


# ---------------------------------------------------------------------------
# Test: delete path legacy cleanup
# ---------------------------------------------------------------------------
class _DeleteEipTestBase(unittest.TestCase):
    """Base for delete_eip_with_ns tests."""

    IP_VERSION = 4

    def setUp(self):
        self.executed_cmds = []

        self._patchers = _apply_patchers()
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
        self.mock_iproute.IpNetnsShell.list_netns.return_value = [
            "br_eth0_192_168_1_100"
        ]

        self.patcher_linux = mock.patch("kvmagent.plugins.deip.linux")
        self.mock_linux = self.patcher_linux.start()
        self.mock_linux.is_network_device_existing.return_value = False

        eip_cmd = Eip()
        self._call_method(
            eip_cmd,
            "delete_eip_with_ns",
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

    def _has_cmd(self, pattern):
        return any(pattern in cmd for cmd in self.executed_cmds)

    def _cmds_matching(self, pattern):
        return [cmd for cmd in self.executed_cmds if pattern in cmd]

    def _call_method(self, obj, method_name, *args, **kwargs):
        method = getattr(type(obj), method_name)
        method(obj, *args, **kwargs)


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


class TestDeleteEipWithMissingNamespace(unittest.TestCase):
    def _call_delete_eip_with_ns(self, del_netns_side_effect=None):
        patchers = [
            mock.patch("kvmagent.plugins.deip.iproute"),
            mock.patch("kvmagent.plugins.deip.linux"),
            mock.patch("zstacklib.utils.shell.get_process"),
            mock.patch("kvmagent.plugins.deip.lock.NamedLock"),
            mock.patch("kvmagent.plugins.deip.lock.FileLock"),
        ]
        mocks = [patcher.start() for patcher in patchers]
        mock_iproute, mock_linux, mock_get_process = mocks[:3]
        try:
            mock_linux.is_network_device_existing.return_value = False
            mock_get_process.side_effect = _make_fake_process([])
            mock_iproute.IpNetnsShell.return_value.del_netns.side_effect = (
                del_netns_side_effect
            )

            eip_cmd = Eip()
            method = type(eip_cmd).delete_eip_with_ns
            try:
                method(
                    eip_cmd,
                    ns="br_eth0_192_168_1_100",
                    eip_uuid="abcdef123456789",
                    version=4,
                    nic_name="vnic1.0",
                )
            finally:
                mock_iproute.IpNetnsShell.return_value.del_netns.assert_called_once_with()
        finally:
            for patcher in patchers:
                patcher.stop()

    def test_missing_namespace_is_idempotent(self):
        self._call_delete_eip_with_ns(
            del_netns_side_effect=Exception(
                'Cannot remove namespace file "/run/netns/br_eth0_192_168_1_100": '
                "No such file or directory"
            )
        )

    def test_missing_namespace_exception_is_idempotent(self):
        self._call_delete_eip_with_ns(
            del_netns_side_effect=Exception(
                "Network namespace : br_eth0_192_168_1_100 could not be found."
            )
        )

    def test_unexpected_namespace_delete_error_is_raised(self):
        delete_error = Exception(
            'Cannot remove namespace file "/run/netns/br_eth0_192_168_1_100": '
            "Permission denied"
        )
        with self.assertRaisesRegexp(Exception, "Permission denied") as raised:
            self._call_delete_eip_with_ns(del_netns_side_effect=delete_error)
        self.assertIs(raised.exception, delete_error)


if __name__ == "__main__":
    unittest.main()

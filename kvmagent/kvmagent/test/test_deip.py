import inspect
import sys
import unittest
import mock
try:
    from types import SimpleNamespace
except ImportError:
    class SimpleNamespace(object):
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

if not hasattr(inspect, "unwrap"):
    inspect.unwrap = lambda func: getattr(func, "__wrapped__", func)
if not hasattr(unittest.TestCase, "assertCountEqual"):
    unittest.TestCase.assertCountEqual = unittest.TestCase.assertItemsEqual
if not hasattr(unittest.TestCase, "assertRaisesRegex"):
    unittest.TestCase.assertRaisesRegex = unittest.TestCase.assertRaisesRegexp

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

    def test_none_namespace_cleans_outer_devs_and_arp_rules(self):
        executed_cmds = []
        patchers = _apply_patchers() + [
            mock.patch("kvmagent.plugins.deip.iproute"),
            mock.patch("kvmagent.plugins.deip.linux"),
            mock.patch(
                "zstacklib.utils.shell.get_process",
                side_effect=_make_fake_process(executed_cmds),
            ),
        ]
        started = [p.start() for p in patchers]
        mock_iproute = started[-3]
        mock_linux = started[-2]
        try:
            mock_linux.is_network_device_existing.return_value = True
            eip_cmd = Eip()
            inspect.unwrap(type(eip_cmd).delete_eip_with_ns)(
                eip_cmd,
                ns=None,
                eip_uuid="abcdef123456789",
                version=4,
                nic_name="vnic1.0",
            )
            mock_iproute.IpNetnsShell.assert_not_called()
            self.assertIn(
                mock.call("123456789_eo"),
                mock_iproute.delete_link_no_error.call_args_list,
            )
            self.assertIn(
                mock.call("123456789_o"),
                mock_iproute.delete_link_no_error.call_args_list,
            )
            self.assertTrue(any("-F eip-vnic1.0-gw" in c for c in executed_cmds))
            self.assertTrue(any("-X eip-vnic1.0-gw" in c for c in executed_cmds))
        finally:
            for p in patchers:
                p.stop()


class TestZSTAC91420SyncEip(unittest.TestCase):
    def setUp(self):
        self.plugin = DEip()

    def _alias(self, eip_uuid, vip, nic_name="vnic1.0", nic_ip="10.0.0.100",
               vm_uuid="vm1234", vip_uuid="vip5678"):
        return (
            "eip:%s,eip_addr:%s,vnic:%s,vnic_ip:%s,vm:%s,vip:%s"
            % (eip_uuid, vip, nic_name, nic_ip, vm_uuid, vip_uuid)
        )

    def test_sync_uri_is_registered(self):
        self.assertEqual("/flatnetworkprovider/eip/sync", DEip.SYNC_EIP_PATH)
        http_server = mock.MagicMock()
        with mock.patch("kvmagent.plugins.deip.kvmagent.get_http_server",
                        return_value=http_server):
            with mock.patch.object(self.plugin, "_register_vm_lifecycle_hook"):
                self.plugin.start()

        http_server.register_async_uri.assert_any_call(
            DEip.SYNC_EIP_PATH, self.plugin.sync_eips
        )

    @staticmethod
    def _healthy_ebtables_nat_output(eip_uuid="abcdef111111111", nic_name="vnic1.0"):
        suffix = eip_uuid[-9:]
        pub_odev = "%s_eo" % suffix
        pri_odev = "%s_o" % suffix
        chains = [
            "eip-%s-gw" % nic_name,
            "eip-%s-gw" % pri_odev,
            "eip-%s-arp" % pri_odev,
            "eip-%s-arp" % pub_odev,
            "eip-%s-arp" % nic_name,
        ]
        lines = [
            "Bridge table: nat",
            "Bridge chain: PREROUTING, entries: 2, policy: ACCEPT",
            "-p ARP -i %s -j eip-%s-gw" % (nic_name, nic_name),
            "-p ARP -i %s -j eip-%s-gw" % (pri_odev, pri_odev),
            "Bridge chain: POSTROUTING, entries: 3, policy: ACCEPT",
            "-p ARP -o %s -j eip-%s-arp" % (pri_odev, pri_odev),
            "-p ARP -o %s -j eip-%s-arp" % (pub_odev, pub_odev),
            "-p ARP -o %s -j eip-%s-arp" % (nic_name, nic_name),
        ]
        for chain in chains:
            lines.append("Bridge chain: %s, entries: 1, policy: RETURN" % chain)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _healthy_ns_rules_output(eip):
        suffix = eip.eipUuid[-9:]
        pub_idev = "%s_ei" % suffix
        pri_idev = "%s_i" % suffix
        ip_version = int(getattr(eip, "ipVersion", 4))
        vip = eip.vip
        nic_ip = eip.nicIp
        if ip_version == 4:
            host_prefix = 32
            dnat_chain = "DNAT-%s" % vip
            snat_chain = "SNAT-%s" % vip
            fwd_chain = "FWD-%s" % vip
        else:
            host_prefix = 128
            dnat_chain = "EIP6-DNAT-%s" % suffix
            snat_chain = "EIP6-SNAT-%s" % suffix
            fwd_chain = "EIP6-FWD-%s" % suffix
        return "\n".join([
            "*nat",
            ":PREROUTING ACCEPT [0:0]",
            ":POSTROUTING ACCEPT [0:0]",
            ":%s - [0:0]" % dnat_chain,
            ":%s - [0:0]" % snat_chain,
            "-A PREROUTING -d %s/%d -j %s" % (vip, host_prefix, dnat_chain),
            "-A POSTROUTING -s %s/%d -j %s" % (nic_ip, host_prefix, snat_chain),
            "-A %s -j DNAT --to-destination %s" % (dnat_chain, nic_ip),
            "-A %s -j SNAT --to-source %s" % (snat_chain, vip),
            "COMMIT",
            "*filter",
            ":FORWARD ACCEPT [0:0]",
            ":%s - [0:0]" % fwd_chain,
            "-A FORWARD -i %s -o %s -j %s" % (pri_idev, pub_idev, fwd_chain),
            "-A FORWARD -i %s -o %s -j %s" % (pub_idev, pri_idev, fwd_chain),
            "-A %s -j ACCEPT" % fwd_chain,
            "COMMIT",
            "",
        ])

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_sync_prunes_multiple_orphan_eips_including_same_vm_and_missing_netns(
            self, bash_o):
        alias1 = self._alias("abcdef111111111", "11.168.100.10", "vnic1.0",
                             "10.0.0.10", "vm1111", "vip1111")
        alias2 = self._alias("abcdef222222222", "11.168.100.11", "vnic1.1",
                             "10.0.0.11", "vm1111", "vip2222")
        bash_o.return_value = (
            "10: 111111111_eo@if9: <BROADCAST> alias %s\n"
            "11: 222222222_o@if12: <BROADCAST> alias %s\n"
            % (alias1, alias2)
        )

        with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute:
            mock_iproute.IpNetnsShell.list_netns.return_value = [
                "br_eth0_11_168_100_10"
            ]
            with mock.patch.object(Eip, "delete_orphan_fdb_if_needed") as del_fdb:
                with mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
                    inspect.unwrap(DEip._sync_eips)(self.plugin, [], [], 0)

        self.assertEqual(2, del_fdb.call_count)
        self.assertCountEqual(
            [
                mock.call("br_eth0_11_168_100_10", "abcdef111111111", 4, "vnic1.0"),
                mock.call(None, "abcdef222222222", 4, "vnic1.1"),
            ],
            del_eip.call_args_list,
        )

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_sync_protects_in_flight_and_recently_applied_eips(self, bash_o):
        inflight_alias = self._alias("abcdef111111111", "11.168.100.10", "vnic1.0")
        recent_alias = self._alias("abcdef222222222", "11.168.100.11", "vnic2.0")
        bash_o.return_value = (
            "10: 111111111_eo alias %s\n11: 222222222_eo alias %s\n"
            % (inflight_alias, recent_alias)
        )

        recent_eip = _make_eip()
        recent_eip.eipUuid = "abcdef222222222"
        recent_eip.vip = "11.168.100.11"

        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=100.0):
            with mock.patch.object(Eip, "apply_eip"):
                inspect.unwrap(DEip._apply_eips)(self.plugin, [recent_eip])

        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=115.0):
            with mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
                inspect.unwrap(DEip._sync_eips)(
                    self.plugin, [], ["abcdef111111111"], 30
                )
                del_eip.assert_not_called()

        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=135.0):
            with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute:
                mock_iproute.IpNetnsShell.list_netns.return_value = [
                    "br_eth0_11_168_100_11"
                ]
                with mock.patch.object(Eip, "delete_orphan_fdb_if_needed"):
                    with mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
                        inspect.unwrap(DEip._sync_eips)(
                            self.plugin, [], ["abcdef111111111"], 30
                        )
                        del_eip.assert_called_once_with(
                            "br_eth0_11_168_100_11", "abcdef222222222", 4, "vnic2.0"
                        )

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_sync_skips_healthy_expected_eip_and_applies_missing_expected_eip(
            self, bash_o):
        healthy = _make_eip()
        healthy.eipUuid = "abcdef111111111"
        healthy.vip = "192.168.1.100"

        passive = _make_eip()
        passive.eipUuid = "abcdef333333333"
        passive.vip = "192.168.1.102"
        passive.vipUuid = "vip-passive"

        missing = _make_eip()
        missing.eipUuid = "abcdef222222222"
        missing.vip = "192.168.1.101"

        bash_o.return_value = (
            "10: 111111111_eo alias %s\n11: 333333333_eo alias %s\n"
            % (
                self._alias(healthy.eipUuid, healthy.vip, healthy.nicName),
                self._alias(passive.eipUuid, passive.vip, passive.nicName),
            )
        )

        nat_out = self._healthy_ebtables_nat_output(healthy.eipUuid, healthy.nicName)
        healthy_ns_rules = self._healthy_ns_rules_output(healthy)

        def fake_bash_ro(cmd):
            if "iptables-save" in cmd:
                return (0, healthy_ns_rules)
            return (0, nat_out)

        with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute, \
                mock.patch("kvmagent.plugins.deip.linux") as mock_linux, \
                mock.patch("kvmagent.plugins.deip.get_ebtables_cmd",
                           return_value="ebtables"), \
                mock.patch("kvmagent.plugins.deip.bash_ro",
                           side_effect=fake_bash_ro):
            mock_iproute.IpNetnsShell.list_netns.return_value = [
                "br_eth0_192_168_1_100",
                "br_eth0_192_168_1_102",
            ]
            mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
                "aa:bb:cc:dd:ee:ff"
            )
            mock_linux.is_network_device_up.side_effect = (
                lambda dev: dev in ("111111111_eo", "111111111_o", "333333333_o")
            )
            with mock.patch.object(Eip, "apply_eip") as apply_eip:
                with mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
                    applied_vips, errors = inspect.unwrap(DEip._sync_eips)(
                        self.plugin, [healthy, passive, missing], [], 30
                    )

        del_eip.assert_not_called()
        self.assertEqual([mock.call(passive), mock.call(missing)], apply_eip.call_args_list)
        self.assertEqual([passive.vipUuid, missing.vipUuid], applied_vips)
        self.assertEqual([], errors)

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_sync_reapplies_expected_eip_when_dnat_rule_missing(self, bash_o):
        degraded = _make_eip()
        degraded.eipUuid = "abcdef111111111"
        degraded.vip = "192.168.1.100"
        degraded.vipUuid = "vip-missing-dnat"

        bash_o.return_value = "10: 111111111_eo alias %s\n" % self._alias(
            degraded.eipUuid, degraded.vip, degraded.nicName
        )
        nat_out = self._healthy_ebtables_nat_output(degraded.eipUuid, degraded.nicName)
        missing_dnat_rules = self._healthy_ns_rules_output(degraded).replace(
            "-A DNAT-192.168.1.100 -j DNAT --to-destination 10.0.0.100\n", ""
        )

        def fake_bash_ro(cmd):
            if "iptables-save" in cmd:
                return (0, missing_dnat_rules)
            return (0, nat_out)

        with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute, \
                mock.patch("kvmagent.plugins.deip.linux") as mock_linux, \
                mock.patch("kvmagent.plugins.deip.get_ebtables_cmd",
                           return_value="ebtables"), \
                mock.patch("kvmagent.plugins.deip.bash_ro",
                           side_effect=fake_bash_ro):
            mock_iproute.IpNetnsShell.list_netns.return_value = [
                "br_eth0_192_168_1_100"
            ]
            mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
                "aa:bb:cc:dd:ee:ff"
            )
            mock_linux.is_network_device_up.return_value = True
            with mock.patch.object(Eip, "apply_eip") as apply_eip:
                with mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
                    applied_vips, errors = inspect.unwrap(DEip._sync_eips)(
                        self.plugin, [degraded], [], 30
                    )

        del_eip.assert_not_called()
        apply_eip.assert_called_once_with(degraded)
        self.assertEqual([degraded.vipUuid], applied_vips)
        self.assertEqual([], errors)

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_delete_eips_clears_grace_window_for_failed_delete(self, bash_o):
        alias = self._alias("abcdef333333333", "11.168.100.12", "vnic3.0")
        bash_o.return_value = "12: 333333333_eo alias %s\n" % alias

        eip = _make_eip()
        eip.eipUuid = "abcdef333333333"
        eip.vip = "11.168.100.12"

        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=100.0):
            with mock.patch.object(Eip, "apply_eip"):
                inspect.unwrap(DEip._apply_eips)(self.plugin, [eip])

        with mock.patch.object(Eip, "delete_eip", side_effect=Exception("boom")):
            with self.assertRaisesRegex(Exception, "boom"):
                inspect.unwrap(DEip._delete_eips)(self.plugin, [eip])

        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=105.0):
            with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute:
                mock_iproute.IpNetnsShell.list_netns.return_value = [
                    "br_eth0_11_168_100_12"
                ]
                with mock.patch.object(Eip, "delete_orphan_fdb_if_needed"):
                    with mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
                        inspect.unwrap(DEip._sync_eips)(self.plugin, [], [], 30)
                        del_eip.assert_called_once_with(
                            "br_eth0_11_168_100_12", "abcdef333333333", 4, "vnic3.0"
                        )

    def test_sync_http_handler_parses_request_and_defaults_grace_seconds(self):
        from zstacklib.utils import http, jsonobject

        with mock.patch.object(self.plugin, "_sync_eips",
                               return_value=(["vip-reapplied"], [])) as sync_mock:
            raw = self.plugin.sync_eips({
                http.REQUEST_BODY: '{"eips": [], "inFlightEipUuids": ["u1"]}'
            })
            rsp = jsonobject.loads(raw)
            self.assertTrue(rsp.success)
            self.assertEqual(["vip-reapplied"], rsp.appliedVipUuids)
            sync_mock.assert_called_once_with(
                [], ["u1"], DEip.DEFAULT_SYNC_GRACE_SECONDS
            )

        with mock.patch.object(
                self.plugin, "_sync_eips",
                return_value=(["vip-partial"], ["apply failed"])) as sync_mock:
            raw = self.plugin.sync_eips({
                http.REQUEST_BODY: '{"eips": [], "inFlightEipUuids": [], "graceSeconds": 0}'
            })
            rsp = jsonobject.loads(raw)
            self.assertFalse(rsp.success)
            self.assertEqual("apply failed", rsp.error)
            self.assertEqual(["vip-partial"], rsp.appliedVipUuids)
            sync_mock.assert_called_once_with([], [], 0)

    def test_delete_orphan_fdb_if_needed_removes_self_fdb_entry(self):
        with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute:
            with mock.patch("kvmagent.plugins.deip.bash_roe",
                            return_value=(0, "eth1\n", "")):
                mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
                    "aa:bb:cc:11:22:33"
                )
                eip_cmd = Eip()
                inspect.unwrap(Eip.delete_orphan_fdb_if_needed)(
                    eip_cmd, "br_eth0_11_168_100_10", "abcdef123456789"
                )
                mock_iproute.del_fdb_entry.assert_called_once_with(
                    "eth1", "aa:bb:cc:11:22:33"
                )

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_enable_eips_refreshes_grace_window_after_long_migration(self, bash_o):
        alias = self._alias("abcdef444444444", "11.168.100.14", "vnic4.0")
        bash_o.return_value = "13: 444444444_eo alias %s\n" % alias

        eip = _make_eip()
        eip.eipUuid = "abcdef444444444"
        eip.vip = "11.168.100.14"

        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=10.0):
            with mock.patch.object(Eip, "apply_eip"):
                inspect.unwrap(DEip._prepare_eips)(self.plugin, [eip])

        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=70.0):
            with mock.patch.object(Eip, "set_eip_public_interface_state", return_value=True):
                with mock.patch.object(self.plugin, "_announce_public_interfaces"):
                    self.plugin._set_eips_public_interface_state([eip], True)

        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=80.0):
            with mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
                inspect.unwrap(DEip._sync_eips)(self.plugin, [], [], 30)
                del_eip.assert_not_called()

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_find_namespace_requires_underscore_boundary_and_rejects_ambiguity(
            self, bash_o):
        eip_cmd = Eip()
        with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute:
            mock_iproute.IpNetnsShell.list_netns.return_value = [
                "br_eth0_110_0_0_1",
                "br_eth0_2001:db8::1",
                "br_eth0_10_0_0_2",
                "br_eth1_10_0_0_2",
            ]
            self.assertIsNone(eip_cmd.find_namespace_name_by_ip("10.0.0.1", 4))
            self.assertIsNone(eip_cmd.find_namespace_name_by_ip("::1", 6))
            self.assertIsNone(eip_cmd.find_namespace_name_by_ip("10.0.0.2", 4))
            self.assertEqual(
                "br_eth0_110_0_0_1",
                eip_cmd.find_namespace_name_by_ip("110.0.0.1", 4),
            )

        orphan_suffix = self._alias("abcdef555555555", "10.0.0.1", "vnic5.0")
        orphan_ambig = self._alias("abcdef666666666", "10.0.0.2", "vnic6.0")
        orphan_shared = self._alias("abcdef777777777", "10.0.0.3", "vnic7.0")
        active_shared = _make_eip()
        active_shared.eipUuid = "abcdef888888888"
        active_shared.vip = "10.0.0.3"
        active_shared.publicBridgeName = "br_eth0"

        bash_o.return_value = (
            "10: 555555555_eo alias %s\n"
            "11: 666666666_eo alias %s\n"
            "12: 777777777_eo alias %s\n"
            % (orphan_suffix, orphan_ambig, orphan_shared)
        )
        nat_out = self._healthy_ebtables_nat_output(
            active_shared.eipUuid, active_shared.nicName
        )
        shared_ns_rules = self._healthy_ns_rules_output(active_shared)

        def fake_bash_ro(cmd):
            if "iptables-save" in cmd:
                return (0, shared_ns_rules)
            return (0, nat_out)

        with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute, \
                mock.patch("kvmagent.plugins.deip.linux") as mock_linux, \
                mock.patch("kvmagent.plugins.deip.get_ebtables_cmd",
                           return_value="ebtables"), \
                mock.patch("kvmagent.plugins.deip.bash_ro",
                           side_effect=fake_bash_ro), \
                mock.patch.object(Eip, "delete_orphan_fdb_if_needed") as del_fdb, \
                mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
            mock_iproute.IpNetnsShell.list_netns.return_value = [
                "br_eth0_110_0_0_1",
                "br_eth0_10_0_0_2",
                "br_eth1_10_0_0_2",
                "br_eth0_10_0_0_3",
            ]
            mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
                "aa:bb:cc:dd:ee:ff"
            )
            mock_linux.is_network_device_up.return_value = True
            inspect.unwrap(DEip._sync_eips)(
                self.plugin, [active_shared], [], 0
            )

        self.assertCountEqual(
            [
                mock.call(None, "abcdef555555555", 4, "vnic5.0"),
                mock.call(None, "abcdef777777777", 4, "vnic7.0"),
            ],
            del_eip.call_args_list,
        )
        self.assertEqual([mock.call(None, "abcdef555555555"),
                          mock.call(None, "abcdef777777777")],
                         del_fdb.call_args_list)

    @mock.patch("kvmagent.plugins.deip.bash_o")
    def test_batch_apply_refreshes_grace_on_completion_and_failed_apply_is_not_shielded(
            self, bash_o):
        eip1 = _make_eip()
        eip1.eipUuid = "abcdef111111111"
        eip1.vip = "11.168.100.21"
        eip2 = _make_eip()
        eip2.eipUuid = "abcdef222222222"
        eip2.vip = "11.168.100.22"
        eip_fail = _make_eip()
        eip_fail.eipUuid = "abcdef999999999"
        eip_fail.vip = "11.168.100.29"

        # Batch of 2 EIPs finishes at t=50.0 (started at t=10.0 -> 40s batch)
        clock = iter([10.0, 50.0, 50.0])
        with mock.patch("kvmagent.plugins.deip.time.monotonic",
                        side_effect=lambda: next(clock)):
            with mock.patch.object(Eip, "apply_eip"):
                inspect.unwrap(DEip._apply_eips)(self.plugin, [eip1, eip2])

        bash_o.return_value = (
            "10: 111111111_eo alias %s\n"
            "11: 222222222_eo alias %s\n"
            % (
                self._alias(eip1.eipUuid, eip1.vip, "vnic1.0"),
                self._alias(eip2.eipUuid, eip2.vip, "vnic2.0"),
            )
        )
        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=70.0):
            with mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
                inspect.unwrap(DEip._sync_eips)(self.plugin, [], [], 30)
                del_eip.assert_not_called()

        # Failed apply_eip does not leave EIP shielded in _recent_applied_eips
        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=100.0):
            with mock.patch.object(Eip, "apply_eip",
                                   side_effect=Exception("arping duplicate")):
                with self.assertRaisesRegex(Exception, "arping duplicate"):
                    inspect.unwrap(DEip._apply_eips)(self.plugin, [eip_fail])

        bash_o.return_value = "12: 999999999_eo alias %s\n" % self._alias(
            eip_fail.eipUuid, eip_fail.vip, "vnic9.0"
        )
        with mock.patch("kvmagent.plugins.deip.time.monotonic", return_value=101.0), \
                mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute, \
                mock.patch.object(Eip, "delete_orphan_fdb_if_needed"), \
                mock.patch.object(Eip, "delete_eip_with_ns") as del_eip:
            mock_iproute.IpNetnsShell.list_netns.return_value = [
                "br_eth0_11_168_100_29"
            ]
            inspect.unwrap(DEip._sync_eips)(self.plugin, [], [], 30)
            del_eip.assert_called_once_with(
                "br_eth0_11_168_100_29", "abcdef999999999", 4, "vnic9.0"
            )

    def test_is_eip_present_detects_missing_ebtables_and_vf_fdb_entries(self):
        eip = _make_eip()
        eip.eipUuid = "abcdef111111111"
        eip.vip = "192.168.1.100"
        eip.nicName = "vnic1.0"
        eip.addfdb = True
        eip.physicalNic = "eth0"

        eip_cmd = Eip()
        existing_netns = {"br_eth0_192_168_1_100"}
        full_nat = self._healthy_ebtables_nat_output(eip.eipUuid, eip.nicName)
        missing_arp_nat = full_nat.replace("-p ARP -o vnic1.0 -j eip-vnic1.0-arp\n", "")
        good_fdb = "aa:bb:cc:dd:ee:ff dev eth0 self permanent\n"
        missing_fdb = "aa:bb:cc:dd:ee:ff dev eth1 self permanent\n"
        healthy_ns_rules = self._healthy_ns_rules_output(eip)

        with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute, \
                mock.patch("kvmagent.plugins.deip.linux") as mock_linux:
            mock_linux.is_network_device_up.return_value = True
            mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
                "aa:bb:cc:dd:ee:ff"
            )
            self.assertFalse(
                eip_cmd.is_eip_present(
                    eip, existing_netns, missing_arp_nat, good_fdb, healthy_ns_rules
                )
            )
            self.assertFalse(
                eip_cmd.is_eip_present(
                    eip, existing_netns, full_nat, missing_fdb, healthy_ns_rules
                )
            )
            self.assertTrue(
                eip_cmd.is_eip_present(
                    eip, existing_netns, full_nat, good_fdb, healthy_ns_rules
                )
            )

    def test_is_eip_present_detects_missing_namespace_nat_rules(self):
        eip = _make_eip()
        eip.eipUuid = "abcdef111111111"
        eip.vip = "192.168.1.100"
        eip.nicName = "vnic1.0"

        eip_v6 = _make_eip(ipVersion=6)
        eip_v6.eipUuid = "abcdef111111111"
        eip_v6.nicName = "vnic1.0"

        eip_cmd = Eip()
        existing_netns = {"br_eth0_192_168_1_100", "br_eth0_fd00:1::100"}
        full_nat = self._healthy_ebtables_nat_output(eip.eipUuid, eip.nicName)
        full_ns_rules = self._healthy_ns_rules_output(eip)
        missing_dnat = full_ns_rules.replace(
            "-A DNAT-192.168.1.100 -j DNAT --to-destination 10.0.0.100\n", ""
        )
        missing_snat = full_ns_rules.replace(
            "-A SNAT-192.168.1.100 -j SNAT --to-source 192.168.1.100\n", ""
        )
        missing_fwd = full_ns_rules.replace(
            "-A FORWARD -i 111111111_i -o 111111111_ei -j FWD-192.168.1.100\n", ""
        )

        v6_nat = "\n".join([
            "Bridge table: nat",
            "Bridge chain: PREROUTING, entries: 1, policy: ACCEPT",
            "-i vnic1.0 -j eip-vnic1.0-gw",
            "Bridge chain: eip-vnic1.0-gw, entries: 1, policy: RETURN",
            "",
        ])
        full_v6_ns_rules = self._healthy_ns_rules_output(eip_v6)
        missing_v6_dnat = full_v6_ns_rules.replace(
            "-A EIP6-DNAT-111111111 -j DNAT --to-destination fd00:2::100\n", ""
        )

        with mock.patch("kvmagent.plugins.deip.iproute") as mock_iproute, \
                mock.patch("kvmagent.plugins.deip.linux") as mock_linux:
            mock_linux.is_network_device_up.return_value = True
            mock_iproute.IpNetnsShell.return_value.get_mac.return_value = (
                "aa:bb:cc:dd:ee:ff"
            )
            self.assertFalse(
                eip_cmd.is_eip_present(eip, existing_netns, full_nat, None, missing_dnat)
            )
            self.assertFalse(
                eip_cmd.is_eip_present(eip, existing_netns, full_nat, None, missing_snat)
            )
            self.assertFalse(
                eip_cmd.is_eip_present(eip, existing_netns, full_nat, None, missing_fwd)
            )
            self.assertFalse(
                eip_cmd.is_eip_present(eip_v6, existing_netns, v6_nat, None, missing_v6_dnat)
            )
            self.assertTrue(
                eip_cmd.is_eip_present(eip_v6, existing_netns, v6_nat, None, full_v6_ns_rules)
            )


if __name__ == "__main__":
    unittest.main()

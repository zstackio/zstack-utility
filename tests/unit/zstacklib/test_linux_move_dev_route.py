from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock


def _load_linux_module():
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root / "zstacklib"))
    sys.modules.setdefault("simplejson", json)
    sys.modules.setdefault("netaddr", MagicMock())
    sys.modules.setdefault("xxhash", MagicMock())
    sys.modules.setdefault("zstacklib.utils.thread", MagicMock())
    sys.modules.setdefault("zstacklib.utils.qemu_img", MagicMock())
    sys.modules.setdefault("zstacklib.utils.lock", MagicMock())
    sys.modules.setdefault("zstacklib.utils.xmlobject", MagicMock())
    sys.modules.setdefault("zstacklib.utils.shell", MagicMock())
    sys.modules.setdefault("zstacklib.utils.iproute", MagicMock())
    sys.modules.setdefault("zstacklib.utils.network_ipv6", MagicMock())
    log_module = types.ModuleType("zstacklib.utils.log")
    log_module.get_logger = MagicMock(return_value=MagicMock())
    sys.modules.setdefault("zstacklib.utils.log", log_module)

    linux_path = repo_root / "zstacklib" / "zstacklib" / "utils" / "linux.py"
    spec = importlib.util.spec_from_file_location("linux_move_dev_route_under_test", linux_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_move_dev_route_moves_ipv6_address_and_routes():
    linux = _load_linux_module()
    calls = []

    def shell_call(cmd, exception=True):
        calls.append((cmd, exception))
        if cmd == 'ip addr show dev ens4 | grep "inet "':
            return ""
        if cmd == 'ip addr show dev ens4 | grep "inet6 " | grep -v " scope link"':
            return "    inet6 2026:3:3:1::4b:3364/64 scope global noprefixroute\n"
        if cmd == "ip route show dev ens4 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens4 | grep via | sed 's/onlink//g'":
            return "default via 2026:3:3:1::1 proto static metric 101\n"
        if cmd == "ip -6 route show dev ens4 proto kernel | grep -v '^fe80::' | sed 's/onlink//g'":
            return "2026:3:3:1::/64 proto kernel metric 101 pref medium\n"
        if cmd == 'ip addr show dev br_ens4 | grep "inet6 2026:3:3:1::4b:3364/64"':
            return ""
        return ""

    linux.shell.call = MagicMock(side_effect=shell_call)

    linux.move_dev_route("ens4", "br_ens4")

    assert ("ip -6 route del default via 2026:3:3:1::1 proto static metric 101", True) in calls
    assert ("ip addr del 2026:3:3:1::4b:3364/64 dev ens4", False) in calls
    assert ("ip -6 route del 2026:3:3:1::/64 dev ens4 proto kernel metric 101 pref medium", False) in calls
    assert ("ip addr add 2026:3:3:1::4b:3364/64 dev br_ens4", True) in calls
    assert ("ip -6 route replace default via 2026:3:3:1::1 dev br_ens4 proto static metric 101", True) in calls


def test_move_dev_route_moves_ipv6_direct_static_route():
    linux = _load_linux_module()
    calls = []

    def shell_call(cmd, exception=True):
        calls.append((cmd, exception))
        if cmd == 'ip addr show dev ens4 | grep "inet "':
            return ""
        if cmd == 'ip addr show dev ens4 | grep "inet6 " | grep -v " scope link"':
            return "    inet6 fd00:5:5:28::62:d0e5/128 scope global noprefixroute\n"
        if cmd == "ip route show dev ens4 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens4 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens4 | grep -v via | grep -v ' proto kernel ' | grep -v '^fe80::' | sed 's/onlink//g'":
            return "fd00:5:5:28::/64 proto static metric 101 pref medium\n"
        if cmd == "ip -6 route show dev ens4 proto kernel | grep -v '^fe80::' | sed 's/onlink//g'":
            return "fd00:5:5:28::62:d0e5 proto kernel metric 101 pref medium\n"
        if cmd == 'ip addr show dev br_ens4 | grep "inet6 fd00:5:5:28::62:d0e5/128"':
            return ""
        return ""

    linux.shell.call = MagicMock(side_effect=shell_call)

    linux.move_dev_route("ens4", "br_ens4")

    assert ("ip -6 route del fd00:5:5:28::/64 dev ens4 proto static metric 101 pref medium", True) in calls
    assert ("ip addr del fd00:5:5:28::62:d0e5/128 dev ens4", False) in calls
    assert ("ip addr add fd00:5:5:28::62:d0e5/128 dev br_ens4", True) in calls
    assert ("ip -6 route replace fd00:5:5:28::/64 dev br_ens4 proto static metric 101 pref medium", True) in calls


def test_move_dev_route_restores_ipv6_gateway_route_before_default_route():
    linux = _load_linux_module()
    calls = []

    def shell_call(cmd, exception=True):
        calls.append((cmd, exception))
        if cmd == 'ip addr show dev ens3 | grep "inet "':
            return "    inet 172.26.115.202/16 scope global noprefixroute ens3\n"
        if cmd == 'ip addr show dev ens3 | grep "inet6 " | grep -v " scope link"':
            return "    inet6 2026:6:3:1::100/64 scope global noprefixroute\n"
        if cmd == "ip route show dev ens3 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens3 | grep via | sed 's/onlink//g'":
            return "default via 2026:6:2:1::1 dev ens3 proto static metric 100\n"
        if cmd == "ip -6 route show dev ens3 | grep -v via | grep -v ' proto kernel ' | grep -v '^fe80::' | sed 's/onlink//g'":
            return "2026:6:2:1::1 dev ens3 proto static metric 100 pref medium\n"
        if cmd == "ip -6 route show dev ens3 proto kernel | grep -v '^fe80::' | sed 's/onlink//g'":
            return "2026:6:3:1::/64 proto kernel metric 100 pref medium\n"
        if cmd == 'ip addr show dev br_ens3 | grep "inet 172.26.115.202/16"':
            return ""
        if cmd == 'ip addr show dev br_ens3 | grep "inet6 2026:6:3:1::100/64"':
            return ""
        return ""

    linux.shell.call = MagicMock(side_effect=shell_call)

    linux.move_dev_route("ens3", "br_ens3")

    direct_route = "ip -6 route replace 2026:6:2:1::1 dev br_ens3 proto static metric 100 pref medium"
    default_route = "ip -6 route replace default via 2026:6:2:1::1 dev br_ens3 proto static metric 100"

    assert (direct_route, True) in calls
    assert (default_route, True) in calls
    assert calls.index((direct_route, True)) < calls.index((default_route, True))


def test_move_dev_route_restores_ipv4_routes_on_bridge():
    linux = _load_linux_module()
    calls = []

    def shell_call(cmd, exception=True):
        calls.append((cmd, exception))
        if cmd == 'ip addr show dev ens3 | grep "inet "':
            return "    inet 172.26.115.202/16 scope global noprefixroute ens3\n"
        if cmd == 'ip addr show dev ens3 | grep "inet6 " | grep -v " scope link"':
            return ""
        if cmd == "ip route show dev ens3 | grep via | sed 's/onlink//g'":
            return "\n".join([
                "default via 172.26.0.1 proto static metric 100",
                "169.254.169.254 via 172.26.115.192 proto static",
            ])
        if cmd == "ip -6 route show dev ens3 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens3 proto kernel | grep -v '^fe80::' | sed 's/onlink//g'":
            return ""
        if cmd == 'ip addr show dev br_ens3 | grep "inet 172.26.115.202/16"':
            return ""
        return ""

    linux.shell.call = MagicMock(side_effect=shell_call)

    linux.move_dev_route("ens3", "br_ens3")

    assert ("ip route replace default via 172.26.0.1 dev br_ens3 proto static metric 100", True) in calls
    assert ("ip route replace 169.254.169.254 via 172.26.115.192 dev br_ens3 proto static", True) in calls


def test_move_dev_route_ignores_missing_source_ipv6_address():
    linux = _load_linux_module()
    calls = []

    def shell_call(cmd, exception=True):
        calls.append((cmd, exception))
        if cmd == 'ip addr show dev ens3 | grep "inet "':
            return ""
        if cmd == 'ip addr show dev ens3 | grep "inet6 " | grep -v " scope link"':
            return "    inet6 2026:6:3:1::100/64 scope global noprefixroute\n"
        if cmd == "ip route show dev ens3 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens3 | grep via | sed 's/onlink//g'":
            return "default via 2026:6:2:1::1 dev ens3 proto static metric 100\n"
        if cmd == "ip -6 route show dev ens3 | grep -v via | grep -v ' proto kernel ' | grep -v '^fe80::' | sed 's/onlink//g'":
            return "2026:6:2:1::1 dev ens3 proto static metric 100 pref medium\n"
        if cmd == "ip -6 route show dev ens3 proto kernel | grep -v '^fe80::' | sed 's/onlink//g'":
            return "2026:6:3:1::/64 proto kernel metric 100 pref medium\n"
        if cmd == 'ip addr show dev br_ens3 | grep "inet6 2026:6:3:1::100/64"':
            return ""
        return ""

    linux.shell.call = MagicMock(side_effect=shell_call)

    linux.move_dev_route("ens3", "br_ens3")

    assert ("ip addr del 2026:6:3:1::100/64 dev ens3", False) in calls
    assert ("ip addr add 2026:6:3:1::100/64 dev br_ens3", True) in calls
    assert ("ip -6 route del 2026:6:3:1::/64 dev ens3 proto kernel metric 100 pref medium", False) in calls
    assert ("ip -6 route replace 2026:6:2:1::1 dev br_ens3 proto static metric 100 pref medium", True) in calls
    assert ("ip -6 route replace default via 2026:6:2:1::1 dev br_ens3 proto static metric 100", True) in calls


def test_zstac_87140_restore_existing_ipv6_ra_default_route_without_eexist():
    linux = _load_linux_module()
    calls = []
    route = "default via fe80::1 proto ra metric 1024 expires 1799sec pref medium"
    add_cmd = "ip -6 route add default via fe80::1 dev br_zsn0 proto ra metric 1024 expires 1799sec pref medium"
    replace_cmd = "ip -6 route replace default via fe80::1 dev br_zsn0 proto ra metric 1024 expires 1799sec pref medium"

    def shell_call(cmd, exception=True):
        calls.append((cmd, exception))
        if cmd == add_cmd:
            raise RuntimeError("RTNETLINK answers: File exists")
        return ""

    linux.shell.call = MagicMock(side_effect=shell_call)
    linux._restore_dev_route("br_zsn0", {
        "ipv4_addresses": [],
        "ipv6_addresses": [],
        "routes": [],
        "routes6": [route],
        "direct_routes6": [],
        "connected_routes6": [],
    })

    assert (replace_cmd, True) in calls
    assert (add_cmd, True) not in calls


def test_move_dev_route_migrates_resolved_dns_to_bridge():
    linux = _load_linux_module()
    calls = []

    def shell_call(cmd, exception=True):
        calls.append((cmd, exception))
        if cmd == 'ip addr show dev ens3 | grep "inet "':
            return "    inet 172.26.115.202/16 scope global noprefixroute ens3\n"
        if cmd == 'ip addr show dev ens3 | grep "inet6 " | grep -v " scope link"':
            return ""
        if cmd == "ip route show dev ens3 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens3 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens3 | grep -v via | grep -v ' proto kernel ' | grep -v '^fe80::' | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev ens3 proto kernel | grep -v '^fe80::' | sed 's/onlink//g'":
            return ""
        if cmd == 'ip addr show dev br_ens3 | grep "inet 172.26.115.202/16"':
            return ""
        if cmd == 'LC_ALL=C resolvectl dns ens3':
            return "Link 2 (ens3): 223.5.5.5 8.8.8.8"
        if cmd == 'LC_ALL=C resolvectl dns br_ens3':
            return "Link 3 (br_ens3):"
        return ""

    original_exists = linux.os.path.exists
    try:
        linux.os.path.exists = MagicMock(return_value=True)
        linux.shell.call = MagicMock(side_effect=shell_call)

        linux.move_dev_route("ens3", "br_ens3")

        assert ('LC_ALL=C resolvectl dns br_ens3 223.5.5.5 8.8.8.8', True) in calls
        assert ('LC_ALL=C resolvectl domain br_ens3 "~."', True) in calls
    finally:
        linux.os.path.exists = original_exists


def test_create_bridge_snapshots_routes_before_enslave():
    linux = _load_linux_module()
    calls = []
    enslaved = {"value": False}

    def shell_call(cmd, exception=True):
        calls.append((cmd, exception))
        if cmd == 'ip addr show dev eth0 | grep "inet "':
            return ""
        if cmd == 'ip addr show dev eth0 | grep "inet6 " | grep -v " scope link"':
            return "" if enslaved["value"] else "    inet6 fd00:5:5:28::79:d283/64 scope global noprefixroute\n"
        if cmd == "ip route show dev eth0 | grep via | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev eth0 | grep via | sed 's/onlink//g'":
            return "" if enslaved["value"] else "default via fd00:5:5:28::1 proto static metric 101\n"
        if cmd == "ip -6 route show dev eth0 | grep -v via | grep -v ' proto kernel ' | grep -v '^fe80::' | sed 's/onlink//g'":
            return ""
        if cmd == "ip -6 route show dev eth0 proto kernel | grep -v '^fe80::' | sed 's/onlink//g'":
            return "" if enslaved["value"] else "fd00:5:5:28::/64 proto kernel metric 101 pref medium\n"
        if cmd == 'ip addr show dev br_eth0 | grep "inet6 fd00:5:5:28::79:d283/64"':
            return ""
        return ""

    def set_master(interface, bridge):
        calls.append(("enslave", interface, bridge))
        enslaved["value"] = True

    original_is_network_device_existing = linux.is_network_device_existing
    original_is_bridge = linux.is_bridge
    original_find_bridge = linux.find_bridge_having_physical_interface
    original_set_master = linux.ip_link_set_net_device_master
    original_migrate_dns = linux._migrate_resolved_dns
    try:
        linux.shell.call = MagicMock(side_effect=shell_call)
        linux.is_network_device_existing = MagicMock(return_value=True)
        linux.is_bridge = MagicMock(return_value=False)
        linux.find_bridge_having_physical_interface = MagicMock(return_value=None)
        linux.ip_link_set_net_device_master = MagicMock(side_effect=set_master)
        linux._migrate_resolved_dns = MagicMock()

        linux.create_bridge("br_eth0", "eth0")

        snapshot_call = ('ip addr show dev eth0 | grep "inet6 " | grep -v " scope link"', False)
        assert calls.index(snapshot_call) < calls.index(("enslave", "eth0", "br_eth0"))
        assert ("ip addr add fd00:5:5:28::79:d283/64 dev br_eth0", True) in calls
        assert ("ip -6 route replace default via fd00:5:5:28::1 dev br_eth0 proto static metric 101", True) in calls
    finally:
        linux.is_network_device_existing = original_is_network_device_existing
        linux.is_bridge = original_is_bridge
        linux.find_bridge_having_physical_interface = original_find_bridge
        linux.ip_link_set_net_device_master = original_set_master
        linux._migrate_resolved_dns = original_migrate_dns


def test_tcp_port_is_free_closes_probe_sockets_on_failure():
    linux = _load_linux_module()

    class FakeSocket(object):
        def __init__(self):
            self.closed = False

        def setsockopt(self, *_args):
            pass

        def close(self):
            self.closed = True

    ipv6_socket = FakeSocket()
    ipv4_socket = FakeSocket()
    original_socket = linux.socket.socket
    original_bind_dual_stack = linux.network_ipv6.bind_dual_stack_probe_socket
    original_bind_ipv4 = linux.network_ipv6.bind_ipv4_probe_socket
    try:
        linux.socket.socket = MagicMock(side_effect=[ipv6_socket, ipv4_socket])
        linux.network_ipv6.bind_dual_stack_probe_socket = MagicMock(
            side_effect=linux.socket.error("ipv6 bind failed")
        )
        linux.network_ipv6.bind_ipv4_probe_socket = MagicMock(
            side_effect=linux.socket.error("ipv4 bind failed")
        )

        assert not linux.tcp_port_is_free(4900)
        assert ipv6_socket.closed
        assert ipv4_socket.closed
    finally:
        linux.socket.socket = original_socket
        linux.network_ipv6.bind_dual_stack_probe_socket = original_bind_dual_stack
        linux.network_ipv6.bind_ipv4_probe_socket = original_bind_ipv4

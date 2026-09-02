# -*- coding: utf-8 -*-
import importlib.util
import socket
from pathlib import Path

from zstacklib.utils import network_ipv6
from tests.unit.zstacklib.real_linux import load_real_linux

TEST_IPV4_ADDRESS = '192.168.10.10'
TEST_IPV6_ADDRESS = '2001:db8::10'
TEST_HOSTNAME = 'zstack-mn.example.com'
TEST_PORT = 7070
TEST_POOL_SIZE = '32'
TEST_CEPH_PORT = 6789
TEST_IP_ADDR_OUTPUT = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN qlen 1000
    inet 127.0.0.1/8 scope host lo
    inet6 ::1/128 scope host
2: ens3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP qlen 1000
    inet 172.24.194.186/20 brd 172.24.207.255 scope global ens3
    inet6 fd00:172:24:249::186/64 scope global
    inet6 fe80::a359:8e69:9e:4e5a/64 scope link
3: ens4: <BROADCAST,MULTICAST> mtu 1500 state DOWN qlen 1000
    inet6 fd00:172:24:249::187/64 scope global
"""

linux = load_real_linux()


def load_real_ceph_utils():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / 'zstacklib' / 'zstacklib' / 'utils' / 'ceph.py'
    spec = importlib.util.spec_from_file_location('zstacklib_utils_ceph_under_test', str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ceph_utils = load_real_ceph_utils()


def _format_ssh_target(user, hostname):
    return '%s@%s' % (user, network_ipv6.format_url_host(hostname))


def _is_port_available(port):
    try:
        s = linux.socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            network_ipv6.bind_dual_stack_probe_socket(s, port)
            return True
        finally:
            s.close()
    except (socket.error, OSError):
        try:
            s = linux.socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                network_ipv6.bind_ipv4_probe_socket(s, port)
                return True
            finally:
                s.close()
        except (socket.error, OSError):
            return False

if hasattr(linux.format_ssh_target, 'side_effect'):
    linux.format_ssh_target.side_effect = _format_ssh_target
if hasattr(linux.is_port_available, 'side_effect'):
    linux.is_port_available.side_effect = _is_port_available
if hasattr(ceph_utils.linux.is_valid_address, 'side_effect'):
    ceph_utils.linux.is_valid_address.side_effect = linux.is_valid_address


class FakeAddress(object):
    def __init__(self, address, ifname):
        self.address = address
        self.ifname = ifname


class FakeSocket(object):
    def __init__(self):
        self.options = []
        self.bind_address = None

    def setsockopt(self, level, option, value):
        self.options.append((level, option, value))

    def bind(self, address):
        self.bind_address = address


class FakeIpRoute(object):
    def __init__(self):
        self.versions = []

    def query_addresses(self, ip_version=None):
        self.versions.append(ip_version)
        return {
            4: [
                FakeAddress('127.0.0.1', 'lo'),
                FakeAddress('192.168.10.10', 'eth0'),
                FakeAddress('192.168.20.10', 'eth1zs'),
            ],
            6: [
                FakeAddress('::1', 'lo'),
                FakeAddress('fe80::1', 'eth0'),
                FakeAddress('2001:db8::10', 'eth0'),
                FakeAddress('2001:db8::20', 'eth2zs'),
            ],
        }[ip_version]


def test_format_url_host_wraps_ipv6_only_once():
    assert network_ipv6.format_url_host(TEST_IPV4_ADDRESS) == TEST_IPV4_ADDRESS
    assert network_ipv6.format_url_host(TEST_IPV6_ADDRESS) == '[2001:db8::10]'
    assert network_ipv6.format_url_host('[2001:db8::10]') == '[2001:db8::10]'
    assert network_ipv6.format_url_host(None) is None


def test_format_host_port_wraps_ipv6_only_once():
    assert network_ipv6.format_host_port(TEST_IPV4_ADDRESS, TEST_PORT) == '192.168.10.10:7070'
    assert network_ipv6.format_host_port(TEST_IPV6_ADDRESS, TEST_PORT) == '[2001:db8::10]:7070'
    assert network_ipv6.format_host_port('[2001:db8::10]', TEST_PORT) == '[2001:db8::10]:7070'


def test_format_ssh_target_wraps_ipv6_only_once():
    assert linux.format_ssh_target('root', TEST_IPV4_ADDRESS) == 'root@192.168.10.10'
    assert linux.format_ssh_target('root', TEST_IPV6_ADDRESS) == 'root@[2001:db8::10]'
    assert linux.format_ssh_target('root', TEST_HOSTNAME) == 'root@zstack-mn.example.com'


def test_extract_url_host_supports_ipv4_ipv6_and_hostnames():
    assert network_ipv6.extract_url_host('http://192.168.10.10:8080/callback') == TEST_IPV4_ADDRESS
    assert network_ipv6.extract_url_host('http://[2001:db8::10]:8080/callback') == TEST_IPV6_ADDRESS
    assert network_ipv6.extract_url_host('http://zstack-mn.example.com:8080/callback') == TEST_HOSTNAME


def test_get_agent_bind_ip_defaults_to_dual_stack_and_allows_override():
    assert network_ipv6.get_agent_bind_ip({}) == network_ipv6.DUAL_STACK_BIND_ADDRESS
    assert network_ipv6.get_agent_bind_ip({network_ipv6.AGENT_BIND_IP_ENV: '0.0.0.0'}) == '0.0.0.0'
    assert network_ipv6.get_agent_bind_ip({network_ipv6.AGENT_BIND_IP_ENV: TEST_IPV6_ADDRESS}) == TEST_IPV6_ADDRESS


def test_get_socket_family_uses_ipv6_for_literal_ipv6_only():
    assert network_ipv6.get_socket_family(TEST_IPV6_ADDRESS) == socket.AF_INET6
    assert network_ipv6.get_socket_family(TEST_IPV4_ADDRESS) == socket.AF_INET
    assert network_ipv6.get_socket_family(TEST_HOSTNAME) == socket.AF_INET


def test_create_tcp_socket_for_host_uses_matching_address_family():
    created = []
    original_socket = network_ipv6.socket.socket

    def fake_socket(family, sock_type):
        created.append((family, sock_type))
        return FakeSocket()

    network_ipv6.socket.socket = fake_socket
    try:
        network_ipv6.create_tcp_socket_for_host(TEST_IPV6_ADDRESS)
        network_ipv6.create_tcp_socket_for_host(TEST_HOSTNAME)
    finally:
        network_ipv6.socket.socket = original_socket

    assert created == [
        (socket.AF_INET6, socket.SOCK_STREAM),
        (socket.AF_INET, socket.SOCK_STREAM),
    ]


def test_bind_dual_stack_probe_socket_disables_ipv6_only_and_binds_any_address():
    fake_socket = FakeSocket()

    network_ipv6.bind_dual_stack_probe_socket(fake_socket, TEST_PORT)

    assert fake_socket.options == [
        (socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, network_ipv6.IPV6_V6ONLY_DISABLED)
    ]
    assert fake_socket.bind_address == (network_ipv6.DUAL_STACK_BIND_ADDRESS, TEST_PORT)


def test_bind_ipv4_probe_socket_uses_ipv4_any_address():
    fake_socket = FakeSocket()

    network_ipv6.bind_ipv4_probe_socket(fake_socket, TEST_PORT)

    assert fake_socket.bind_address == (network_ipv6.IPV4_BIND_ADDRESS, TEST_PORT)


def test_is_port_available_falls_back_to_ipv4_after_ipv6_bind_error(monkeypatch):
    created_families = []

    class ProbeSocket(FakeSocket):
        def __init__(self, family, socket_type):
            super(ProbeSocket, self).__init__()
            created_families.append((family, socket_type))

        def close(self):
            pass

    monkeypatch.setattr(linux.socket, 'socket', ProbeSocket)
    monkeypatch.setattr(linux, 'is_port_available', _is_port_available)
    monkeypatch.setattr(
        network_ipv6,
        'bind_dual_stack_probe_socket',
        lambda sock, port: (_ for _ in ()).throw(OSError('ipv6 disabled')),
    )
    monkeypatch.setattr(network_ipv6, 'bind_ipv4_probe_socket', lambda sock, port: None)

    assert linux.is_port_available(TEST_PORT)
    assert created_families == [
        (socket.AF_INET6, socket.SOCK_STREAM),
        (socket.AF_INET, socket.SOCK_STREAM),
    ]


def test_build_cherrypy_socket_config_defaults_to_dual_stack_and_reads_env():
    assert network_ipv6.build_cherrypy_socket_config(TEST_PORT, {}) == {
        network_ipv6.CHERRYPY_SOCKET_HOST_KEY: network_ipv6.DUAL_STACK_BIND_ADDRESS,
        network_ipv6.CHERRYPY_SOCKET_PORT_KEY: TEST_PORT,
        network_ipv6.CHERRYPY_THREAD_POOL_KEY: int(network_ipv6.DEFAULT_AGENT_THREAD_POOL),
    }
    assert network_ipv6.build_cherrypy_socket_config(
        TEST_PORT,
        {
            network_ipv6.AGENT_BIND_IP_ENV: TEST_IPV6_ADDRESS,
            network_ipv6.POOLSIZE_ENV: TEST_POOL_SIZE,
        },
    ) == {
        network_ipv6.CHERRYPY_SOCKET_HOST_KEY: TEST_IPV6_ADDRESS,
        network_ipv6.CHERRYPY_SOCKET_PORT_KEY: TEST_PORT,
        network_ipv6.CHERRYPY_THREAD_POOL_KEY: int(TEST_POOL_SIZE),
    }


def test_extract_route_source_address_accepts_ipv4_and_ipv6_src_tokens():
    assert network_ipv6.extract_route_source_address(
        '10.0.0.1 via 10.0.0.254 dev eth0 src 10.0.0.10 uid 0'
    ) == '10.0.0.10'
    assert network_ipv6.extract_route_source_address(
        '2001:db8::1 from :: dev eth0 src 2001:db8::10 metric 100'
    ) == TEST_IPV6_ADDRESS
    assert network_ipv6.extract_route_source_address(
        '2001:db8::1 from :: dev eth0 src not-an-ip metric 100'
    ) is None
    assert network_ipv6.extract_route_source_address('default via 10.0.0.1 dev eth0') is None


def test_reportable_agent_address_filter_rejects_loopback_link_local_and_zs():
    assert not network_ipv6.is_reportable_agent_address('127.0.0.1', 'lo')
    assert not network_ipv6.is_reportable_agent_address('::1', 'lo')
    assert not network_ipv6.is_reportable_agent_address('fe80::1', 'eth0')
    assert not network_ipv6.is_reportable_agent_address('192.168.10.10', 'eth0zs')
    assert network_ipv6.is_reportable_agent_address('192.168.10.10', 'eth0')
    assert network_ipv6.is_reportable_agent_address('2001:db8::10', 'eth0')


def test_collect_reportable_agent_addresses_queries_ipv4_and_ipv6():
    fake_iproute = FakeIpRoute()

    addresses = network_ipv6.collect_reportable_agent_addresses(fake_iproute)

    assert fake_iproute.versions == [4, 6]
    assert addresses == ['192.168.10.10', '2001:db8::10']


def test_extract_ceph_mon_host_supports_ipv4_ipv6_and_addrvec_prefixes():
    assert ceph_utils.extract_mon_host('%s:%s/0' % (TEST_IPV4_ADDRESS, TEST_CEPH_PORT)) == TEST_IPV4_ADDRESS
    assert ceph_utils.extract_mon_host('[%s]:%s/0' % (TEST_IPV6_ADDRESS, TEST_CEPH_PORT)) == TEST_IPV6_ADDRESS
    assert ceph_utils.extract_mon_host('v2:[%s]:3300/0' % TEST_IPV6_ADDRESS) == TEST_IPV6_ADDRESS
    assert ceph_utils.extract_mon_host('v1:%s:%s/0' % (TEST_IPV6_ADDRESS, TEST_CEPH_PORT)) == TEST_IPV6_ADDRESS
    assert ceph_utils.extract_mon_host(TEST_IPV6_ADDRESS) == TEST_IPV6_ADDRESS


def test_get_ceph_mon_addr_uses_ipv6_local_route(monkeypatch):
    commands = []
    monmap = '{"mons":[{"addr":"[%s]:%s/0"}]}' % (TEST_IPV6_ADDRESS, TEST_CEPH_PORT)

    def fake_bash_r(cmd):
        commands.append(cmd)
        return 0

    monkeypatch.setattr(ceph_utils, 'bash_r', fake_bash_r)

    assert ceph_utils.get_mon_addr(monmap, ceph_utils.ROUTE_PROTOCOL_KERNEL) == TEST_IPV6_ADDRESS
    assert commands == [
        "ip -6 route get '%s' | grep -E '^local[[:space:]]' > /dev/null" % TEST_IPV6_ADDRESS
    ]


def test_get_ceph_mon_addr_rejects_nonlocal_ipv6_route(monkeypatch):
    commands = []
    monmap = '{"mons":[{"addr":"[%s]:%s/0"}]}' % (TEST_IPV6_ADDRESS, TEST_CEPH_PORT)

    def fake_bash_r(cmd):
        commands.append(cmd)
        return 1

    monkeypatch.setattr(ceph_utils, 'bash_r', fake_bash_r)

    assert ceph_utils.get_mon_addr(monmap, ceph_utils.ROUTE_PROTOCOL_KERNEL) is None
    assert commands == [
        "ip -6 route get '%s' | grep -E '^local[[:space:]]' > /dev/null" % TEST_IPV6_ADDRESS
    ]


def test_get_ceph_mon_addr_skips_invalid_address_before_shell_execution(monkeypatch):
    commands = []
    invalid_address = "2001:db8::1'; echo injected"
    monmap = '{"mons":[{"addr":"[%s]:%s/0"},{"addr":"[%s]:%s/0"}]}' % (
        invalid_address,
        TEST_CEPH_PORT,
        TEST_IPV6_ADDRESS,
        TEST_CEPH_PORT,
    )

    def fake_bash_r(cmd):
        commands.append(cmd)
        return 0

    monkeypatch.setattr(ceph_utils, 'bash_r', fake_bash_r)

    assert ceph_utils.get_mon_addr(monmap, ceph_utils.ROUTE_PROTOCOL_KERNEL) == TEST_IPV6_ADDRESS
    assert commands == [
        "ip -6 route get '%s' | grep -E '^local[[:space:]]' > /dev/null" % TEST_IPV6_ADDRESS
    ]


def test_get_ceph_mon_addr_keeps_ipv6_static_route_fallback(monkeypatch):
    commands = []
    monmap = '{"mons":[{"addr":"[%s]:%s/0"}]}' % (TEST_IPV6_ADDRESS, TEST_CEPH_PORT)

    def fake_bash_r(cmd):
        commands.append(cmd)
        return 0

    monkeypatch.setattr(ceph_utils, 'bash_r', fake_bash_r)

    assert ceph_utils.get_mon_addr(monmap) == TEST_IPV6_ADDRESS
    assert commands == [
        "ip -6 route | grep -w '%s' > /dev/null" % TEST_IPV6_ADDRESS
    ]


def test_get_ceph_mon_addr_keeps_ipv4_route_table(monkeypatch):
    commands = []
    monmap = '{"mons":[{"addr":"%s:%s/0"}]}' % (TEST_IPV4_ADDRESS, TEST_CEPH_PORT)

    def fake_bash_r(cmd):
        commands.append(cmd)
        return 0

    monkeypatch.setattr(ceph_utils, 'bash_r', fake_bash_r)

    assert ceph_utils.get_mon_addr(monmap, ceph_utils.ROUTE_PROTOCOL_KERNEL) == TEST_IPV4_ADDRESS
    assert commands == [
        'ip route | grep -w "proto kernel" | grep -w \'%s\' > /dev/null' % TEST_IPV4_ADDRESS
    ]


def test_get_nics_by_cidr_matches_ipv6_addresses(monkeypatch):
    monkeypatch.setattr(linux.shell, 'call', lambda cmd: TEST_IP_ADDR_OUTPUT)

    assert linux.get_nics_by_cidr('fd00:172:24:249::/64') == [
        {'ens3': 'fd00:172:24:249::186'}
    ]
    assert linux.get_nics_by_cidr('172.24.192.0/20') == [
        {'ens3': '172.24.194.186'}
    ]

__author__ = 'frank'

import functools

from kvmagent import kvmagent
from kvmagent.plugins import network_plugin
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import iptables
from zstacklib.utils import iproute
from zstacklib.utils import ebtables
from zstacklib.utils import ovs
from zstacklib.utils import lock
from zstacklib.utils.bash import *
from zstacklib.utils import ip
from zstacklib.utils import thread
import os.path
import re
import email
import tempfile
import io as c
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
import struct
import socket
import platform
import time

from zstacklib.utils.ovs import OvsError

logger = log.get_logger(__name__)


def write_file_if_changed(path, content, mode=None, encoding=None):
    open_kwargs = {'encoding': encoding} if encoding is not None else {}
    if os.path.exists(path):
        try:
            with open(path, 'r', **open_kwargs) as fd:
                if fd.read() == content:
                    return False
        except UnicodeDecodeError:
            pass

    with open(path, 'w', **open_kwargs) as fd:
        fd.write(content)
    if mode is not None:
        os.chmod(path, mode)
    return True


@functools.lru_cache(maxsize=1)
def get_ebtables_cmd():
    return ebtables.get_ebtables_cmd()


@functools.lru_cache(maxsize=1)
def get_iptables_cmd():
    return iptables.get_iptables_cmd()


IP6TABLES_CMD = iptables.get_ip6tables_cmd()
HOST_ARCH = platform.machine()
DHCPV6_DUID_UUID_PREFIX = '00:04'
UUID_HEX_LENGTH = 32


def make_dhcpv6_duid_uuid(vm_uuid):
    if not vm_uuid:
        return None

    uuid_hex = vm_uuid.replace('-', '').lower()
    if len(uuid_hex) != UUID_HEX_LENGTH or not re.match('^[0-9a-f]+$', uuid_hex):
        return None

    return DHCPV6_DUID_UUID_PREFIX + ':' + ':'.join(uuid_hex[i:i + 2] for i in range(0, UUID_HEX_LENGTH, 2))


class NamespaceInfraEnv(object):
    """
        +------------------+
        |       VM         |
        |                  |                +--------------------------------------------------+
        |      +---+       |                |                                                  |
        +------|---|-------+                |                                                  |
               |   |                        |                                                  |
               +-|-+                        |                       HOST-NETWORK               |
                 |                          |     +---------------------------------------+    |
    +----------+-|-+--------------+         |     |                                       |    |
    |                             |         |     |           169.254.64.1                |    |
    |                             |         |     |                                       |    |
    |        br_03b0306_2346      |         |     |           br_conn_all_ns              |    |
    |        vm_bridge            |         |     |           host_bridge                 |    |
    +--------+-------------+------+         |     +----+-------------+--------------------+    |
             |near_vm_outer|                |          |near_host_outer|                       |
             +------|------+                |          +------|--------+                       |
                    |                       |                 |                                |
                    |                       +-----------------|--------------------------------+
                    |                                         |
      +-----+-------------------+-------------------+---------------------+-------+
      |     |  near_vm_inner    |                   |    near_host_inner  |       |
      |     |                   |                   |                     |       |
      |     |  169.254.169.254  |                   |    169.254.169.24   |       |
      |     |                   |                   +---------------------+       |
      |     |  192.168.1.3(dhcp)|                                                 |
      |     +-------------------+                                                 |
      |                             NAMESPACE                                     |
      +---------------------------------------------------------------------------+
    """
    CONNECT_ALL_NETNS_BR_NAME = "br_conn_all_ns"
    CONNECT_ALL_NETNS_BR_OUTER_IP = "169.254.64.1"
    CONNECT_ALL_NETNS_BR_INNER_IP = "169.254.64.2"
    IP_MASK_BIT = 18

    def __init__(self, vm_bridge_name, namespace_name):
        self.vm_bridge_name = vm_bridge_name
        self.host_bridge_name = self.CONNECT_ALL_NETNS_BR_NAME
        self.namespace_name = namespace_name
        self.namespace_id = ip.get_namespace_id(self.namespace_name)
        self.near_vm_outer = "outer%s" % self.namespace_id
        self.near_vm_inner = "inner%s" % self.namespace_id
        self.near_host_outer = "ud_outer%s" % self.namespace_id
        self.near_host_inner = "ud_inner%s" % self.namespace_id

        self.ns_new_created = False


    @lock.lock('namespace_infra_env')
    @in_bash
    def prepare_dev(self):
        logger.debug('use id[%s] for the namespace[%s]' % (self.namespace_id, self.namespace_name))

        self._create_namespace_if_not_exist()
        self._create_host_bridge_if_not_exist()
        self._add_host_bridge_ip_if_not_exist()
        self._create_link_pair_to_br_and_ns(self.vm_bridge_name, self.near_vm_inner, self.near_vm_outer)
        self._create_link_pair_to_br_and_ns(self.host_bridge_name, self.near_host_inner, self.near_host_outer)
        self._add_near_host_inner_ip_if_not_exist()
        self._add_near_vm_inner_ip_if_not_exist()
        self._set_namespace_attribute()

    @lock.lock('namespace_infra_env')
    @in_bash
    @lock.file_lock('/run/xtables.lock')
    def add_ip_eb_tables(self, l3_network_uuid, ip_addr, netmask):
        DEV = self.near_vm_inner
        NS_NAME = self.namespace_name
        CIDR = ip.IpAddress(ip_addr).toCidr(netmask)
        self._add_vm_route_if_not_exist(CIDR)

        # set ebtables
        BR_NAME = self.vm_bridge_name
        ETH_NAME = get_phy_dev_from_bridge_name(BR_NAME)

        MAC = iproute.IpNetnsShell(NS_NAME).get_mac(DEV)
        CHAIN_NAME = "USERDATA-%s" % BR_NAME
        EBCHAIN_NAME = get_ebtables_userdata_chain_name(BR_NAME, l3_network_uuid)

        ret = bash_r(get_ebtables_cmd() + ' -t nat -L {{EBCHAIN_NAME}} >/dev/null 2>&1')
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -t nat -N {{EBCHAIN_NAME}}')

        if bash_r(get_ebtables_cmd() + " -t nat -L PREROUTING | grep -E -- '(--logical-in|-i) {{BR_NAME}} -j {{EBCHAIN_NAME}}'") != 0:
            # try --logical-in first; fall back to -i for kernels (e.g. alinux4 >= 6.6.102-5.3) that reject `meta ibrname`
            if bash_r(get_ebtables_cmd() + ' -t nat -I PREROUTING --logical-in {{BR_NAME}} -j {{EBCHAIN_NAME}}') != 0:
                bash_errorout(get_ebtables_cmd() + ' -t nat -I PREROUTING -i {{BR_NAME}} -j {{EBCHAIN_NAME}}')

        # ebtables has a bug that will eliminate 0 in MAC, for example, aa:bb:0c will become aa:bb:c
        macAddr = ip.removeZeroFromMacAddress(MAC)
        RULE = "-p IPv4 --ip-src %s --ip-dst 169.254.169.254 -j dnat --to-dst %s --dnat-target ACCEPT" % (CIDR, macAddr)
        ret = bash_r(get_ebtables_cmd() + " -t nat -L {{EBCHAIN_NAME}} | grep -- '{{RULE}}' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -t nat -I {{EBCHAIN_NAME}} {{RULE}}')

        ret = bash_r(
            get_ebtables_cmd() + " -t nat -L {{EBCHAIN_NAME}} | grep -- '--arp-ip-dst %s' > /dev/null" % self.CONNECT_ALL_NETNS_BR_OUTER_IP)
        if ret != 0:
            bash_errorout(
                get_ebtables_cmd() + ' -t nat -I {{EBCHAIN_NAME}}  -p arp  --arp-ip-dst %s -j DROP' % self.CONNECT_ALL_NETNS_BR_OUTER_IP)

        ret = bash_r(get_ebtables_cmd() + " -t nat -L {{EBCHAIN_NAME}} | grep -- '-j RETURN' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -t nat -A {{EBCHAIN_NAME}} -j RETURN')

        ret = bash_r(get_ebtables_cmd() + ' -L {{EBCHAIN_NAME}} >/dev/null 2>&1')
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -N {{EBCHAIN_NAME}}')

        ret = bash_r(
            get_ebtables_cmd() + " -L FORWARD | grep -- '-p ARP --arp-ip-dst 169.254.169.254 -j {{EBCHAIN_NAME}}' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -I FORWARD -p ARP --arp-ip-dst 169.254.169.254 -j {{EBCHAIN_NAME}}')

        ret = bash_r(get_ebtables_cmd() + " -L {{EBCHAIN_NAME}} | grep -- '-i {{ETH_NAME}} -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -I {{EBCHAIN_NAME}} -i {{ETH_NAME}} -j DROP')

        ret = bash_r(get_ebtables_cmd() + " -L {{EBCHAIN_NAME}} | grep -- '-o {{ETH_NAME}} -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -I {{EBCHAIN_NAME}} -o {{ETH_NAME}} -j DROP')

        ret = bash_r("ebtables-save | grep '\-A {{EBCHAIN_NAME}} -j RETURN'")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -A {{EBCHAIN_NAME}} -j RETURN')

    @lock.lock('namespace_infra_env')
    @lock.file_lock('/run/xtables.lock')
    @in_bash
    def del_ip_eb_tables(self, l3_network_uuid):
        BR_NAME = self.vm_bridge_name
        CHAIN_NAME = get_ebtables_userdata_chain_name(BR_NAME, l3_network_uuid)

        cmds = []
        o = bash_o("ebtables-save | grep {{CHAIN_NAME}} | grep -- -A")
        o = o.strip()
        if o:
            for l in o.split("\n"):
                # we don't distinguish if the rule is in filter table or nat table
                # but try both. The wrong table will silently fail
                cmds.append(get_ebtables_cmd() + " -t filter %s" % l.replace("-A", "-D"))
                cmds.append(get_ebtables_cmd() + " -t nat %s" % l.replace("-A", "-D"))

        if bash_r("ebtables-save | grep :{{CHAIN_NAME}}") == 0:
            cmds.append(get_ebtables_cmd() + " -t filter -X %s" % CHAIN_NAME)
            cmds.append(get_ebtables_cmd() + " -t nat -X %s" % CHAIN_NAME)

        if len(cmds) > 0:
            bash_r("\n".join(cmds))

    @lock.lock('namespace_infra_env')
    @in_bash
    def delete_dev(self):
        if self.namespace_name not in iproute.IpNetnsShell.list_netns():
            return
        iproute.IpNetnsShell(self.namespace_name).del_link(self.near_vm_inner)
        iproute.delete_link_no_error(self.near_vm_outer)
        iproute.IpNetnsShell(self.namespace_name).del_link(self.near_host_inner)
        iproute.delete_link_no_error(self.near_host_outer)
        iproute.IpNetnsShell(self.namespace_name).del_netns()

    def _create_namespace_if_not_exist(self):
        netns = iproute.IpNetnsShell.list_netns()
        if self.namespace_name not in netns:
            iproute.IpNetnsShell(self.namespace_name).add_netns(self.namespace_id)
            self.ns_new_created = True
        else:
            self.ns_new_created = False

    def _create_link_pair_to_br_and_ns(self, bridge_name, inner_name, outer_name):
        self._cleanup_orphan_link_if_exist(inner_name, outer_name)
        self._create_link_pair(inner_name, outer_name)
        if self._is_using_ovs(bridge_name):
            self._add_link_to_ovs(bridge_name, outer_name)
            self._set_link_attribute_for_ovs(inner_name)
        else:
            self._add_link_to_bridge(bridge_name, outer_name)
        self._add_link_to_namespace(inner_name)
        iproute.IpNetnsShell(self.namespace_name).set_link_up(inner_name)

    def _create_host_bridge_if_not_exist(self):
        bridge_name = self.CONNECT_ALL_NETNS_BR_NAME
        if not linux.is_network_device_existing(bridge_name):
            shell.call("brctl addbr %s" % bridge_name)
            shell.call("brctl stp %s off" % bridge_name)
            shell.call("brctl setfd %s 0" % bridge_name)
            iproute.set_link_up(bridge_name)

    def _add_host_bridge_ip_if_not_exist(self):
        bridge_name = self.CONNECT_ALL_NETNS_BR_NAME
        ip = self.CONNECT_ALL_NETNS_BR_OUTER_IP
        mask_bit = self.IP_MASK_BIT
        addr = iproute.query_addresses(ifname=bridge_name, address=ip, prefixlen=mask_bit)
        if not addr:
            iproute.add_address(ip, mask_bit, 4, bridge_name)

    def _set_namespace_attribute(self):
        # dhcp namespace should not add ipv6 address based on router advertisement
        NAMESPACE_NAME = self.namespace_name
        LINK_NAME = self.near_vm_inner
        bash_roe("ip netns exec {{NAMESPACE_NAME}} sysctl -w net.ipv6.conf.all.accept_ra=0")
        bash_roe("ip netns exec {{NAMESPACE_NAME}} sysctl -w net.ipv6.conf.{{LINK_NAME}}.accept_ra=0")

    def _add_near_host_inner_ip_if_not_exist(self):
        ns_id = self.namespace_id
        ns = self.namespace_name
        dev = self.near_host_inner
        mask_bit = self.IP_MASK_BIT
        if int(ns_id) > 16381:
            # 169.254.64.1/18 The maximum available ip is only 16381 (exclude 169.254.64.1)
            # It is impossible to configure tens of thousands of networks on host
            raise Exception('add ip addr fail, namespace id exceeds limit')
        ip2int = struct.unpack('!L', socket.inet_aton(self.CONNECT_ALL_NETNS_BR_INNER_IP))[0]
        userdata_br_inner_dev_ip = socket.inet_ntoa(struct.pack('!L', ip2int + int(ns_id)))
        addr = iproute.IpNetnsShell(ns).get_ip_address(4, dev)
        if addr is None:
            iproute.IpNetnsShell(ns).add_ip_address(userdata_br_inner_dev_ip, mask_bit, dev)

    def _cleanup_orphan_link_if_exist(self, inner_name, outer_name):
        mac = iproute.IpNetnsShell(self.namespace_name).get_mac(inner_name)
        if mac is None:
            iproute.delete_link_no_error(outer_name)

    def _create_link_pair(self, inner_name, outer_name):
        outer_exist = linux.is_network_device_existing(outer_name)
        ret = bash_r('ip netns exec {} ip link show | grep {} > /dev/null'.format(self.namespace_name, inner_name))
        inner_exist = (ret == 0)
        if not outer_exist or not inner_exist:
            if outer_exist:
                iproute.delete_link_no_error(outer_name)
            elif inner_exist:
                iproute.IpNetnsShell(self.namespace_name).del_link(inner_name)
            iproute.add_link(outer_name, 'veth', peer=inner_name)
            iproute.set_link_attribute(inner_name, mtu=linux.MAX_MTU_OF_VNIC)
            iproute.set_link_attribute(outer_name, mtu=linux.MAX_MTU_OF_VNIC)
        iproute.set_link_up(outer_name)

    @staticmethod
    def _add_link_to_bridge(bridge_name, link_name):
        BR_NAME = bridge_name
        LINK_NAME = link_name
        ret = bash_r('brctl show {{BR_NAME}} | grep -w {{LINK_NAME}} > /dev/null')
        if ret != 0:
            bash_errorout('brctl addif {{BR_NAME}} {{LINK_NAME}}')

    @staticmethod
    def _add_link_to_ovs(bridge_name, link_name):
        try:
            ovs_ctl = ovs.getOvsCtl(with_dpdk=True)
            ovs_ctl.addOuterToBridge(bridge_name, link_name)
        except OvsError as err:
            logger.error("Get ovs ctl failed. {}".format(err))

    def _set_link_attribute_for_ovs(self, link_name):
        NAMESPACE_NAME = self.namespace_name
        LINK_NAME = link_name
        bash_errorout('ip netns exec {{NAMESPACE_NAME}} ethtool -K {{LINK_NAME}} tx off')

    def _add_link_to_namespace(self, link_name):
        mac = iproute.IpNetnsShell(self.namespace_name).get_mac(link_name)
        if mac is None:
            iproute.IpNetnsShell(self.namespace_name).add_link(link_name)

    def _add_near_vm_inner_ip_if_not_exist(self):
        ns = self.namespace_name
        dev = self.near_vm_inner
        addr = iproute.IpNetnsShell(ns).get_userdata_ip_address(dev)
        if addr is None:
            iproute.IpNetnsShell(ns).add_ip_address('169.254.169.254', 32, dev)

    @staticmethod
    def _is_using_ovs(bridge_name):
        BR_NAME = bridge_name
        ret = bash_r('brctl show | grep -w {{BR_NAME}} > /dev/null')
        if ret == 0:
            return False

        try:
            logger.debug("Network use ovs attach")
            ovs_ctl = ovs.getOvsCtl(with_dpdk=True)
            if BR_NAME in ovs_ctl.listBrs():
                return True
        except OvsError as err:
            logger.error("Get ovs ctl failed. {}".format(err))

    @in_bash
    def _add_vm_route_if_not_exist(self, cidr):
        NS_NAME = self.namespace_name
        CIDR = cidr
        DEV = self.near_vm_inner
        _, o = bash_ro('ip netns exec {{NS_NAME}} ip r | wc -l')
        if int(o) == 1:
            bash_errorout('ip netns exec {{NS_NAME}} ip r add {{CIDR}} dev {{DEV}}')


class UserNameSpaceEnv(object):

    def __init__(self, bridge_name, namespace_name):
        self.bridge_name = bridge_name
        self.namespace_name = namespace_name
        self.infra_env = NamespaceInfraEnv(bridge_name, namespace_name)

    def prepare(self, l3_network_uuid, ip_addr, netmask):
        self.infra_env.prepare_dev()
        self.infra_env.add_ip_eb_tables(l3_network_uuid, ip_addr, netmask)

    def delete(self, l3_network_uuid):
        self.infra_env.del_ip_eb_tables(l3_network_uuid)
        self.infra_env.delete_dev()


class DhcpNameSpaceEnv(object):
    DHCP6_STATEFUL = "Stateful-DHCP"
    DHCP6_STATELESS = "Stateless-DHCP"

    def __init__(self, bridge_name, namespace_name):
        self.bridge_name = bridge_name
        self.dhcp_server_ip = None
        self.dhcp_server6_ip = None
        self.dhcp_netmask = None
        self.namespace_name = namespace_name
        self.ipVersion = 0
        self.prefixLen = 0
        self.addressMode = self.DHCP6_STATEFUL
        self.infra_env = NamespaceInfraEnv(self.bridge_name, self.namespace_name)

    @lock.file_lock('/run/xtables.lock')
    @in_bash
    def prepare(self):
        self.infra_env.prepare_dev()
        self._prepare_ip_iptables_ebtables_fdb()

    def delete(self):
        # delete ip, iptables, ebtables, etc
        self._del_bridge_fdb_entry_for_inner_dev()
        self._del_dhcp4_tables()
        self._del_dhcp6_tables()
        self.infra_env.delete_dev()

    def enable(self):
        # add ip, iptables, ebtables, start dnsmasq, etc
        self.infra_env.prepare_dev()
        self._prepare_ip_iptables_ebtables_fdb()

    def disable(self):
        # delete ip, iptables, ebtables, stop dnsmasq, etc
        self._del_bridge_fdb_entry_for_inner_dev()
        self._del_dhcp4_tables()
        self._del_dhcp6_tables()
        self._del_dhcp_ip_if_exist()

    def get_dhcp_ip(self):
        dev = self.infra_env.near_vm_inner
        return iproute.IpNetnsShell(self.namespace_name).get_ip_address(4, dev)

    def get_dhcp6_ip(self):
        dev = self.infra_env.near_vm_inner
        dhcp6_ip = iproute.IpNetnsShell(self.namespace_name).get_ip_address(6, dev)
        return dhcp6_ip

    @lock.file_lock('/run/xtables.lock')
    def clean_dhcp4_iptables(self):
        self._del_dhcp4_tables()

    @lock.file_lock('/run/xtables.lock')
    def clean_dhcp6_iptables(self):
        self._del_dhcp6_tables()

    @in_bash
    def _prepare_ip_iptables_ebtables_fdb(self):
        NAMESPACE_NAME = self.namespace_name
        BR_NAME = self.bridge_name
        DHCP_IP = self.dhcp_server_ip
        DHCP6_IP = self.dhcp_server6_ip
        DHCP_NETMASK = self.dhcp_netmask
        PREFIX_LEN = None
        if DHCP_NETMASK is not None:
            PREFIX_LEN = linux.netmask_to_cidr(DHCP_NETMASK)
        PREFIX6_LEN = self.prefixLen
        BR_PHY_DEV = get_phy_dev_from_bridge_name(self.bridge_name)
        DHCP_DEV = self.infra_env.near_vm_inner
        if DHCP_IP is not None:
            CHAIN_NAME = getDhcpEbtableChainName(DHCP_IP)
        elif DHCP6_IP is not None:
            CHAIN_NAME = getDhcpEbtableChainName(DHCP6_IP)

        if (DHCP_IP is None and DHCP6_IP is None) or (PREFIX_LEN is None and PREFIX6_LEN is None):
            logger.debug(
                "no dhcp ip[{{DHCP_IP}}] or netmask[{{DHCP_NETMASK}}] for {{DHCP_DEV}} in {{NAMESPACE_NAME}}, skip ebtables/iptables config")
            return

        self._add_dhcp_ip_if_not_exist(DHCP_IP, PREFIX_LEN, DHCP6_IP, PREFIX6_LEN, DHCP_DEV)

        if DHCP_IP is not None:
            self._prepare_dhcp4_iptables()
            self._add_bridge_fdb_entry_for_inner_dev(DHCP_DEV)

        if DHCP6_IP is not None:
            is_dual_stack = DHCP_IP is not None
            self._prepare_dhcp6_iptables(DHCP6_IP, is_dual_stack)

    @staticmethod
    @in_bash
    def _prepare_dhcp4_iptables():
        ret = bash_r(get_ebtables_cmd() + ' -L {{CHAIN_NAME}} > /dev/null 2>&1')
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -N {{CHAIN_NAME}}')

        ret = bash_r(get_ebtables_cmd() + " -L FORWARD | grep -- '-j {{CHAIN_NAME}}' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -A FORWARD -j {{CHAIN_NAME}}')

        ret = bash_r(
            get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p ARP -o {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(
                get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p ARP -o {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP')

        ret = bash_r(
            get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p ARP -i {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(
                get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p ARP -i {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP')

        ret = bash_r(
            get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p ARP -o {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(
                get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p ARP -o {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP')

        ret = bash_r(
            get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p ARP -i {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(
                get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p ARP -i {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP')

        ret = bash_r(
            get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p IPv4 -o {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(
                get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p IPv4 -o {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP')

        ret = bash_r(
            get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p IPv4 -i {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(
                get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p IPv4 -i {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP')

        ret = bash_r("ebtables-save | grep -- '-A {{CHAIN_NAME}} -j RETURN'")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -A {{CHAIN_NAME}} -j RETURN')

        # Note(WeiW): fix dhcp checksum, see more at #982
        if HOST_ARCH == 'mips64el':
            return
        ret = bash_r("iptables-save | grep -- '-p udp -m udp --dport 68 -j CHECKSUM --checksum-fill'")
        if ret != 0:
            bash_errorout(
                '%s -t mangle -A POSTROUTING -p udp -m udp --dport 68 -j CHECKSUM --checksum-fill' % get_iptables_cmd())

    @staticmethod
    @in_bash
    def _prepare_dhcp6_iptables(dhcp6_ip, is_dual_stack=True):
        def _add_ebtables_rule6(rule_search, rule_add=None):
            if rule_add is None:
                rule_add = rule_search

            search_cmd_no_mask = get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '{{rule_search}}' > /dev/null"
            ret = bash_r(search_cmd_no_mask)

            if ret != 0:
                search_cmd_with_mask = get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '{{rule_add}}' > /dev/null"
                ret = bash_r(search_cmd_with_mask)
            if ret != 0:
                add_cmd = get_ebtables_cmd() + ' -I {{CHAIN_NAME}} {{rule_add}}'
                bash_errorout(add_cmd)

        serverip = ip.Ipv6Address(dhcp6_ip)
        ns_multicast_address = serverip.get_solicited_node_multicast_address()
        ns_multicast_address_mask = ns_multicast_address + "/ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"

        if not is_dual_stack:
            ret = bash_r(get_ebtables_cmd() + ' -L {{CHAIN_NAME}} > /dev/null 2>&1')
            if ret != 0:
                bash_errorout(get_ebtables_cmd() + ' -N {{CHAIN_NAME}}')

            ret = bash_r(get_ebtables_cmd() + ' -F {{CHAIN_NAME}} > /dev/null 2>&1')
            ret = bash_r(get_ebtables_cmd() + " -L FORWARD | grep -- '-j {{CHAIN_NAME}}' > /dev/null")
            if ret != 0:
                bash_errorout(get_ebtables_cmd() + ' -I FORWARD -j {{CHAIN_NAME}}')

        ns_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
        ns_rule_add = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address_mask}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
        _add_ebtables_rule6(ns_rule_o, ns_rule_add)

        ns_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
        ns_rule_add = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address_mask}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
        _add_ebtables_rule6(ns_rule_o, ns_rule_add)

        ns_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
        ns_rule_add = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address_mask}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
        _add_ebtables_rule6(ns_rule_i, ns_rule_add)

        ns_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
        ns_rule_add = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address_mask}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
        _add_ebtables_rule6(ns_rule_i, ns_rule_add)

        # prevent ns for dhcp server from upstream network
        dhcpv6_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-proto udp --ip6-sport 546:547 -j DROP"
        _add_ebtables_rule6(dhcpv6_rule_o)

        dhcpv6_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-proto udp --ip6-sport 546:547 -j DROP"
        _add_ebtables_rule6(dhcpv6_rule_i)

        ret = bash_r("ebtables-save | grep -- '-A {{CHAIN_NAME}} -j RETURN'")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -A {{CHAIN_NAME}} -j RETURN')

            # Note(WeiW): fix dhcp checksum, see more at #982
            ret = bash_r("ip6tables-save | grep -- '-p udp -m udp --dport 546 -j CHECKSUM --checksum-fill'")
            if ret != 0:
                bash_errorout(
                    '%s -t mangle -A POSTROUTING -p udp -m udp --dport 546 -j CHECKSUM --checksum-fill' % IP6TABLES_CMD)

    @in_bash
    def _add_dhcp_ip_if_not_exist(self, dhcp_ip, prefix_len, dhcp6_ip, prefix6_len, dev):
        ns = self.namespace_name
        ip4 = iproute.IpNetnsShell(ns).get_ip_address(4, dev)
        ip6 = iproute.IpNetnsShell(ns).get_ip_address(6, dev)
        if ((ip4 is None or ip4 != dhcp_ip) and prefix_len is not None) \
                or ((ip6 is None or ip6 != dhcp6_ip) and prefix6_len is not None):
            iproute.IpNetnsShell(ns).flush_ip_address(dev)
            if dhcp_ip is not None:
                iproute.IpNetnsShell(ns).add_ip_address(dhcp_ip, prefix_len, dev)
                iproute.IpNetnsShell(ns).add_ip_address("169.254.169.254", 32, dev)
            if dhcp6_ip is not None:
                iproute.IpNetnsShell(ns).add_ip_address(dhcp6_ip, prefix6_len, dev)

        if dhcp6_ip is not None:
            mac = iproute.IpNetnsShell(ns).get_mac(dev)
            link_local = ip.get_link_local_address(mac)
            old_link_local = iproute.IpNetnsShell(ns).get_link_local6_address(dev)
            if old_link_local is None:
                iproute.IpNetnsShell(ns).add_ip_address(link_local, 64, dev)

        iproute.IpNetnsShell(ns).set_link_up(dev)

    @in_bash
    def _del_dhcp_ip_if_exist(self):
        ns = self.namespace_name
        dev = self.infra_env.near_vm_inner
        ip4 = iproute.IpNetnsShell(ns).get_ip_address(4, dev)
        ip6 = iproute.IpNetnsShell(ns).get_ip_address(6, dev)
        if ip4:
            iproute.IpNetnsShell(ns).del_ip_address(ip4, dev)
        if ip6:
            iproute.IpNetnsShell(ns).del_ip_address(ip6, dev)

    @in_bash
    def _add_bridge_fdb_entry_for_inner_dev(self, dev):
        # to apply userdata service to vf nics, we need to add bridge fdb to allow vf <-> innerX
        # get pf name for inner dev
        r, PHY_DEV, e = bash_roe(
            "brctl show {{BR_NAME}} | grep -w {{BR_NAME}} | head -n 1 | awk '{ print $NF }' | { read name; echo ${name%%.*}; }")
        if r != 0:
            logger.error("cannot get physical interface name from bridge " + self.bridge_name)
            return
        PHY_DEV = PHY_DEV.strip()

        # get mac address of inner dev
        DHCP_DEV_MAC = iproute.IpNetnsShell(self.namespace_name).get_mac(dev)

        # add bridge fdb entry for inner dev
        iproute.add_fdb_entry(PHY_DEV, DHCP_DEV_MAC)

    @in_bash
    def _del_dhcp4_tables(self):
        ns = self.namespace_name
        dev = self.infra_env.near_vm_inner
        dhcp_ip = iproute.IpNetnsShell(ns).get_ip_address(4, dev)
        if dhcp_ip is not None:
            CHAIN_NAME = getDhcpEbtableChainName(dhcp_ip)
            o = bash_o("ebtables-save | grep {{CHAIN_NAME}} | grep -- -A")
            o = o.strip()
            if o:
                cmds = []
                for l in o.split("\n"):
                    cmds.append(get_ebtables_cmd() + " %s" % l.replace("-A", "-D"))
                bash_r("\n".join(cmds))

            ret = bash_r("ebtables-save | grep '\-A {{CHAIN_NAME}} -j RETURN'")
            if ret != 0:
                bash_r(get_ebtables_cmd() + ' -D {{CHAIN_NAME}} -j RETURN')

            ret = bash_r("ebtables-save | grep '\-A FORWARD -j {{CHAIN_NAME}}'")
            if ret != 0:
                bash_r(get_ebtables_cmd() + ' -D FORWARD -j {{CHAIN_NAME}}')
                bash_r(get_ebtables_cmd() + ' -X {{CHAIN_NAME}}')

    @in_bash
    def _del_dhcp6_tables(self):
        items = self.namespace_name.split('_')
        l3_uuid = items[-1]
        DHCP6_CHAIN_NAME = "ZSTACK-DHCP6-%s" % l3_uuid[0:9]  # this case is for old version dhcp6 namespace

        o = bash_o("ebtables-save | grep {{DHCP6_CHAIN_NAME}} | grep -- -A")
        o = o.strip()
        if o:
            cmds = []
            for l in o.split("\n"):
                cmds.append(get_ebtables_cmd() + " %s" % l.replace("-A", "-D"))
            bash_r("\n".join(cmds))

        ret = bash_r("ebtables-save | grep '\-A {{DHCP6_CHAIN_NAME}} -j RETURN'")
        if ret != 0:
            bash_r(get_ebtables_cmd() + ' -D {{DHCP6_CHAIN_NAME}} -j RETURN')

        ret = bash_r("ebtables-save | grep '\-A FORWARD -j {{DHCP6_CHAIN_NAME}}'")
        if ret != 0:
            bash_r(get_ebtables_cmd() + ' -D FORWARD -j {{DHCP6_CHAIN_NAME}}')
            bash_r(get_ebtables_cmd() + ' -X {{DHCP6_CHAIN_NAME}}')

    @in_bash
    def _del_bridge_fdb_entry_for_inner_dev(self):
        BR_NAME = self.bridge_name
        NAMESPACE_NAME = self.namespace_name

        # get pf name for inner dev
        r, PHY_DEV, e = bash_roe(
            "brctl show {{BR_NAME}} | grep -w {{BR_NAME}} | head -n 1 | awk '{ print $NF }' | { read name; echo ${name%%.*}; }")
        if r != 0:
            logger.error("cannot get physical interface name from bridge " + BR_NAME)
            return
        PHY_DEV = PHY_DEV.strip()
        # get mac address of inner dev
        DHCP_DEV_MAC = iproute.IpNetnsShell(NAMESPACE_NAME).get_mac(self.infra_env.near_vm_inner)
        iproute.del_fdb_entry(PHY_DEV, DHCP_DEV_MAC)

class ApplyDhcpRsp(kvmagent.AgentResponse):
    pass

class ReleaseDhcpRsp(kvmagent.AgentResponse):
    pass

class PrepareDhcpRsp(kvmagent.AgentResponse):
    pass

class ApplyUserdataRsp(kvmagent.AgentResponse):
    pass

class ReleaseUserdataRsp(kvmagent.AgentResponse):
    pass

class ConnectRsp(kvmagent.AgentResponse):
    pass

class ResetGatewayRsp(kvmagent.AgentResponse):
    pass

class DeleteNamespaceRsp(kvmagent.AgentResponse):
    pass

class ArpingRsp(kvmagent.AgentResponse):
    def __init__(self):
        self.result = {}

class SetForwardDnsCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SetForwardDnsCmd, self).__init__()
        self.dns = None
        self.mac = None
        self.bridgeName = None
        self.nameSpace = None
        self.wrongDns = None

class SetForwardDnsRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(SetForwardDnsRsp, self).__init__()


class RemoveForwardDnsCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(RemoveForwardDnsCmd, self).__init__()
        self.dns = None
        self.mac = None
        self.bridgeName = None
        self.nameSpace = None

class RemoveForwardDnsRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(RemoveForwardDnsRsp, self).__init__()

def get_phy_dev_from_bridge_name(bridge_name, vlan_id=None):
    phy_dev = ""

    if vlan_id:
        if vlan_id.startswith("vlan"):
            vlan_number = vlan_id.replace("vlan", "")
            phy_nic = linux.get_bridge_phy_nic_name_from_alias(bridge_name)
            if not phy_nic:
                phy_dev = bridge_name.replace('br_', '', 1) + "." + vlan_number
            else:
                if "." in phy_nic:
                    phy_nic = phy_nic.rsplit('.', 1)[0]
                phy_dev = "%s.%s" % (phy_nic, vlan_number)
        elif vlan_id.startswith("vxlan"):
            vxlan_number = vlan_id.replace("vxlan", "")
            phy_dev = "vxlan" + vxlan_number
    else:
        # for vlan, BR_NAME is "br_eth0_100", vlan sub interface: eth0.100,
        # for vxlan, BR_NAME is "br_vx_7863", vxlan sub interface vxlan7863"
        phy_dev = bridge_name.replace('br_', '', 1)
        if phy_dev[:2] == "vx":
            phy_dev = phy_dev.replace("vx", "vxlan").replace("_", "")
        else:
            phy_nic = linux.get_bridge_phy_nic_name_from_alias(bridge_name)
            if not phy_nic:
                phy_dev = phy_dev.replace("_", ".")
            else:
                phy_dev = re.sub(r"^.*_", "%s." % phy_nic, phy_dev)

    return phy_dev

def get_l3_uuid(namespace):
    items = namespace.split('_')
    return items[-1]

def getDhcpEbtableChainName(dhcpIp):
    if ":" in dhcpIp: #ipv6 address
        return "ZSTACK-DHCP-%s" % dhcpIp[0:9]
    else:
        return "ZSTACK-%s" % dhcpIp


def get_ebtables_userdata_chain_name(br_name, l3_network_uuid):
    # Note: In ebtables v1.8 and above, the maximum allowed length for certain string fields
    # (e.g., --comment, --set-mark, custom chain names) is limited to 28 characters.
    if is_ebtables_nf_tables():
        max_chain_name_len = 28
        prefix = "UD"
        uuid_len = 8
        separator_len = 2  # two '-' characters
        max_br_len = max_chain_name_len - len(prefix) - separator_len - uuid_len
        return "%s-%s-%s" % (prefix, br_name[-max_br_len:], l3_network_uuid[:uuid_len])
    else:
        return "USERDATA-%s-%s" % (br_name[-12:], l3_network_uuid[:8])

def is_ebtables_nf_tables():
    r, o, e = bash_roe(get_ebtables_cmd() + ' --version')
    if r != 0:
        raise Exception('Failed to get ebtables version')
    return "nf_tables" in o


def ensure_userdata_veth_pair(namespace_name, outer_dev, inner_dev, mtu):
    outer_exist = linux.is_network_device_existing(outer_dev)
    ns_shell = iproute.IpNetnsShell(namespace_name)
    inner_exist = ns_shell.get_mac(inner_dev) is not None

    if outer_exist != inner_exist:
        if outer_exist:
            iproute.delete_link_no_error(outer_dev)
        if inner_exist:
            ns_shell.del_link(inner_dev)
        outer_exist = False
        inner_exist = False

    if not outer_exist and not inner_exist:
        iproute.add_link(outer_dev, 'veth', peer=inner_dev)
        iproute.set_link_attribute(outer_dev, mtu=mtu)
        iproute.set_link_attribute(inner_dev, mtu=mtu)


class UserDataEnv(object):
    def __init__(self, bridge_name, namespace_name, vlan_id):
        self.bridge_name = bridge_name
        self.namespace_name = namespace_name
        self.vlan_id = vlan_id
        self.outer_dev = None
        self.inner_dev = None

    @lock.lock('prepare_dhcp_namespace')
    @lock.file_lock('/run/xtables.lock')
    @in_bash
    def prepare(self):
        NAMESPACE_NAME = self.namespace_name
        NAMESPACE_ID = ip.get_namespace_id(self.namespace_name)

        logger.debug('use id[%s] for the namespace[%s]' % (NAMESPACE_ID, NAMESPACE_NAME))

        BR_NAME = self.bridge_name
        VLAN_ID = self.vlan_id
        BR_PHY_DEV = get_phy_dev_from_bridge_name(self.bridge_name, self.vlan_id)
        OUTER_DEV = "outer%s" % NAMESPACE_ID
        INNER_DEV = "inner%s" % NAMESPACE_ID
        MAX_MTU = linux.MAX_MTU_OF_VNIC

        netns = iproute.IpNetnsShell.list_netns()
        if NAMESPACE_NAME not in netns:
            iproute.IpNetnsShell(NAMESPACE_NAME).add_netns(NAMESPACE_ID)

        # in case the namespace deleted and the orphan outer link leaves in the system,
        # deleting the orphan link and recreate it
        mac = iproute.IpNetnsShell(NAMESPACE_NAME).get_mac(INNER_DEV)
        if mac is None:
            iproute.delete_link_no_error(OUTER_DEV)

        if not linux.is_network_device_existing(OUTER_DEV):
            iproute.add_link(OUTER_DEV, 'veth', peer=INNER_DEV)
            iproute.set_link_attribute(INNER_DEV, mtu=MAX_MTU)
            iproute.set_link_attribute(OUTER_DEV, mtu=MAX_MTU)

        iproute.set_link_up(OUTER_DEV)

        ret = bash_r('brctl show {{BR_NAME}} | grep -w {{OUTER_DEV}} > /dev/null')
        if ret != 0:
            bash_errorout('brctl addif {{BR_NAME}} {{OUTER_DEV}}')

        mac = iproute.IpNetnsShell(NAMESPACE_NAME).get_mac(INNER_DEV)
        if mac is None:
            iproute.IpNetnsShell(NAMESPACE_NAME).add_link(INNER_DEV)

        iproute.IpNetnsShell(NAMESPACE_NAME).set_link_up(INNER_DEV)
        self.inner_dev = INNER_DEV
        self.outer_dev = OUTER_DEV

class DhcpEnv(object):
    DHCP6_STATEFUL = "Stateful-DHCP"
    DHCP6_STATELESS = "Stateless-DHCP"

    def __init__(self):
        self.bridge_name = None
        self.vlan_id = None
        self.dhcp_server_ip = None
        self.dhcp_server6_ip = None
        self.dhcp_netmask = None
        self.namespace_name = None
        self.ipVersion = 0
        self.prefixLen = 0
        self.addressMode = self.DHCP6_STATEFUL

    @lock.lock('prepare_dhcp_namespace')
    @lock.file_lock('/run/xtables.lock')
    @in_bash
    def prepare(self):
        def _prepare_dhcp4_iptables():
            ret = bash_r(get_ebtables_cmd() + ' -L {{CHAIN_NAME}} > /dev/null 2>&1')
            if ret != 0:
                bash_errorout(get_ebtables_cmd() + ' -N {{CHAIN_NAME}}')

            ret = bash_r(get_ebtables_cmd() + " -L FORWARD | grep -- '-j {{CHAIN_NAME}}' > /dev/null")
            if ret != 0:
                bash_errorout(get_ebtables_cmd() + ' -A FORWARD -j {{CHAIN_NAME}}')

            ret = bash_r(
                get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p ARP -o {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP' > /dev/null")
            if ret != 0:
                bash_errorout(
                    get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p ARP -o {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP')

            ret = bash_r(
                get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p ARP -i {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP' > /dev/null")
            if ret != 0:
                bash_errorout(
                    get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p ARP -i {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP')

            ret = bash_r(
                get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p ARP -o {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP' > /dev/null")
            if ret != 0:
                bash_errorout(
                    get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p ARP -o {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP')

            ret = bash_r(
                get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p ARP -i {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP' > /dev/null")
            if ret != 0:
                bash_errorout(
                    get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p ARP -i {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP')

            ret = bash_r(
                get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p IPv4 -o {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP' > /dev/null")
            if ret != 0:
                bash_errorout(
                    get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p IPv4 -o {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP')

            ret = bash_r(
                get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '-p IPv4 -i {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP' > /dev/null")
            if ret != 0:
                bash_errorout(
                    get_ebtables_cmd() + ' -I {{CHAIN_NAME}} -p IPv4 -i {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP')

            ret = bash_r("ebtables-save | grep -- '-A {{CHAIN_NAME}} -j RETURN'")
            if ret != 0:
                bash_errorout(get_ebtables_cmd() + ' -A {{CHAIN_NAME}} -j RETURN')

            # Note(WeiW): fix dhcp checksum, see more at #982
            if HOST_ARCH == 'mips64el':
                return
            ret = bash_r("iptables-save | grep -- '-p udp -m udp --dport 68 -j CHECKSUM --checksum-fill'")
            if ret != 0:
                bash_errorout(
                    '%s -t mangle -A POSTROUTING -p udp -m udp --dport 68 -j CHECKSUM --checksum-fill' % get_iptables_cmd())

        def _add_ebtables_rule6(rule_search, rule_add=None):
            if rule_add is None:
                rule_add = rule_search

            search_cmd_no_mask = get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '{{rule_search}}' > /dev/null"
            ret = bash_r(search_cmd_no_mask)

            if ret != 0:
                search_cmd_with_mask = get_ebtables_cmd() + " -L {{CHAIN_NAME}} | grep -- '{{rule_add}}' > /dev/null"
                ret = bash_r(search_cmd_with_mask)
            if ret != 0:
                add_cmd = get_ebtables_cmd() + ' -I {{CHAIN_NAME}} {{rule_add}}'
                bash_errorout(add_cmd)

        def _prepare_dhcp6_iptables(dualStack=True):
            serverip = ip.Ipv6Address(DHCP6_IP)
            ns_multicast_address = serverip.get_solicited_node_multicast_address()
            ns_multicast_address_mask = ns_multicast_address + "/ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"
            if not dualStack:
                ret = bash_r(get_ebtables_cmd() + ' -L {{CHAIN_NAME}} > /dev/null 2>&1')
                if ret != 0:
                    bash_errorout(get_ebtables_cmd() + ' -N {{CHAIN_NAME}}')

                ret = bash_r(get_ebtables_cmd() + ' -F {{CHAIN_NAME}} > /dev/null 2>&1')

                ret = bash_r(get_ebtables_cmd() + " -L FORWARD | grep -- '-j {{CHAIN_NAME}}' > /dev/null")
                if ret != 0:
                    bash_errorout(get_ebtables_cmd() + ' -A FORWARD -j {{CHAIN_NAME}}')

            ns_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
            ns_rule_add = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address_mask}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
            _add_ebtables_rule6(ns_rule_o, ns_rule_add)

            na_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
            ns_rule_add = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address_mask}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
            _add_ebtables_rule6(na_rule_o, ns_rule_add)

            ns_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
            ns_rule_add = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address_mask}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
            _add_ebtables_rule6(ns_rule_i, ns_rule_add)

            na_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
            ns_rule_add = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address_mask}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
            _add_ebtables_rule6(na_rule_i, ns_rule_add)

            # prevent ns for dhcp server from upstream network
            dhcpv6_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-proto udp --ip6-sport 546:547 -j DROP"
            _add_ebtables_rule6(dhcpv6_rule_o)

            dhcpv6_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-proto udp --ip6-sport 546:547 -j DROP"
            _add_ebtables_rule6(dhcpv6_rule_i)

            ret = bash_r("ebtables-save | grep -- '-A {{CHAIN_NAME}} -j RETURN'")
            if ret != 0:
                bash_errorout(get_ebtables_cmd() + ' -A {{CHAIN_NAME}} -j RETURN')

            # Note(WeiW): fix dhcp checksum, see more at #982
            ret = bash_r("ip6tables-save | grep -- '-p udp -m udp --dport 546 -j CHECKSUM --checksum-fill'")
            if ret != 0:
                bash_errorout(
                    '%s -t mangle -A POSTROUTING -p udp -m udp --dport 546 -j CHECKSUM --checksum-fill' % IP6TABLES_CMD)

        NAMESPACE_NAME = self.namespace_name
        NAMESPACE_ID = ip.get_namespace_id(self.namespace_name)

        logger.debug('use id[%s] for the namespace[%s]' % (NAMESPACE_ID, NAMESPACE_NAME))

        BR_NAME = self.bridge_name
        # VLAN_ID sample: vlan100, vxlan200
        VLAN_ID = self.vlan_id
        DHCP_IP = self.dhcp_server_ip
        DHCP6_IP = self.dhcp_server6_ip
        DHCP_NETMASK = self.dhcp_netmask
        PREFIX_LEN = None
        if DHCP_NETMASK is not None:
            PREFIX_LEN = linux.netmask_to_cidr(DHCP_NETMASK)
        PREFIX6_LEN = self.prefixLen
        ADDRESS_MODE = self.addressMode
        BR_PHY_DEV = get_phy_dev_from_bridge_name(self.bridge_name, VLAN_ID)
        OUTER_DEV = "outer%s" % NAMESPACE_ID
        INNER_DEV = "inner%s" % NAMESPACE_ID
        if DHCP_IP is not None:
            CHAIN_NAME = getDhcpEbtableChainName(DHCP_IP)
        elif DHCP6_IP is not None:
            CHAIN_NAME = getDhcpEbtableChainName(DHCP6_IP)

        MAX_MTU = linux.MAX_MTU_OF_VNIC

        netns = iproute.IpNetnsShell.list_netns()
        if NAMESPACE_NAME not in netns:
            iproute.IpNetnsShell(NAMESPACE_NAME).add_netns(NAMESPACE_ID)

        # in case the namespace deleted and the orphan outer link leaves in the system,
        # deleting the orphan link and recreate it
        mac = iproute.IpNetnsShell(NAMESPACE_NAME).get_mac(INNER_DEV)
        if mac is None:
            iproute.delete_link_no_error(OUTER_DEV)

        if not linux.is_network_device_existing(OUTER_DEV):
            iproute.add_link(OUTER_DEV, 'veth', peer=INNER_DEV)
            iproute.set_link_attribute(INNER_DEV, mtu=MAX_MTU)
            iproute.set_link_attribute(OUTER_DEV, mtu=MAX_MTU)

        iproute.set_link_up(OUTER_DEV)

        dhcpForOvs = False
        try:
            ret = bash_r('brctl show | grep -w {{BR_NAME}} > /dev/null')

            if ret != 0:
                logger.debug("Network use ovs attach")
                ovsctl = ovs.getOvsCtl(with_dpdk=True)
                if BR_NAME in ovsctl.listBrs():
                    dhcpForOvs = True
                    ovsctl.addOuterToBridge(BR_NAME, OUTER_DEV)
            else:
                logger.debug("Network use linux-bridge attach")
                ret = bash_r('brctl show {{BR_NAME}} | grep -w {{OUTER_DEV}} > /dev/null')
                if ret != 0:
                    bash_errorout('brctl addif {{BR_NAME}} {{OUTER_DEV}}')

                bash_errorout("bridge link set dev {{OUTER_DEV}} learning on")
        except OvsError as err:
            logger.error("Get ovsctl failed. {}".format(err))

        mac = iproute.IpNetnsShell(NAMESPACE_NAME).get_mac(INNER_DEV)
        if mac is None:
            iproute.IpNetnsShell(NAMESPACE_NAME).add_link(INNER_DEV)

        if dhcpForOvs:
            # close inner tx checksum
            bash_errorout('ip netns exec {{NAMESPACE_NAME}} ethtool -K {{INNER_DEV}} tx off')

        #dhcp namespace should not add ipv6 address based on router advertisement
        bash_roe("ip netns exec {{NAMESPACE_NAME}} sysctl -w net.ipv6.conf.all.accept_ra=0")
        bash_roe("ip netns exec {{NAMESPACE_NAME}} sysctl -w net.ipv6.conf.{{INNER_DEV}}.accept_ra=0")

        ip4 = iproute.IpNetnsShell(NAMESPACE_NAME).get_ip_address(4, INNER_DEV)
        ip6 = iproute.IpNetnsShell(NAMESPACE_NAME).get_ip_address(6, INNER_DEV)
        if ((ip4 is None or ip4 != DHCP_IP) and PREFIX_LEN is not None) \
                or ((ip6 is None or ip6 != DHCP6_IP) and PREFIX6_LEN is not None):
            iproute.IpNetnsShell(NAMESPACE_NAME).flush_ip_address(INNER_DEV)
            if DHCP_IP is not None:
                iproute.IpNetnsShell(NAMESPACE_NAME).add_ip_address(DHCP_IP, PREFIX_LEN, INNER_DEV)
                iproute.IpNetnsShell(NAMESPACE_NAME).add_ip_address("169.254.169.254", 32, INNER_DEV)
            if DHCP6_IP is not None:
                iproute.IpNetnsShell(NAMESPACE_NAME).add_ip_address(DHCP6_IP, PREFIX6_LEN, INNER_DEV)

        if DHCP6_IP is not None:
            mac = iproute.IpNetnsShell(NAMESPACE_NAME).get_mac(INNER_DEV)
            link_local = ip.get_link_local_address(mac)
            old_link_local = iproute.IpNetnsShell(NAMESPACE_NAME).get_link_local6_address(INNER_DEV)
            if old_link_local is None:
                iproute.IpNetnsShell(NAMESPACE_NAME).add_ip_address(link_local, 64, INNER_DEV)

        iproute.IpNetnsShell(NAMESPACE_NAME).set_link_up(INNER_DEV)

        if (DHCP_IP is None and DHCP6_IP is None) or (PREFIX_LEN is None and PREFIX6_LEN is None):
            logger.debug("no dhcp ip[{{DHCP_IP}}] or netmask[{{DHCP_NETMASK}}] for {{INNER_DEV}} in {{NAMESPACE_NAME}}, skip ebtables/iptables config")
            return

        # to apply userdata service to vf nics, we need to add bridge fdb to allow vf <-> innerX
        def _add_bridge_fdb_entry_for_inner_dev():
            # get pf name for inner dev
            r, PHY_DEV, e = bash_roe("brctl show {{BR_NAME}} | grep -w {{BR_NAME}} | head -n 1 | awk '{ print $NF }' | { read name; echo ${name%%.*}; }")
            if r != 0:
                logger.error("cannot get physical interface name from bridge " + BR_NAME)
                return
            PHY_DEV = PHY_DEV.strip()

            # get mac address of inner dev
            INNER_MAC = iproute.IpNetnsShell(NAMESPACE_NAME).get_mac(INNER_DEV)

            # add bridge fdb entry for inner dev
            iproute.add_fdb_entry(PHY_DEV, INNER_MAC)

        if DHCP_IP or DHCP6_IP:
            _add_bridge_fdb_entry_for_inner_dev()

        if DHCP_IP is not None:
            _prepare_dhcp4_iptables()

        if DHCP6_IP is not None:
            _prepare_dhcp6_iptables(DHCP_IP is not None)


class Mevoco(kvmagent.KvmAgent):
    APPLY_DHCP_PATH = "/flatnetworkprovider/dhcp/apply"
    BATCH_APPLY_DHCP_PATH = "/flatnetworkprovider/dhcp/batchApply"
    PREPARE_DHCP_PATH = "/flatnetworkprovider/dhcp/prepare"
    BATCH_PREPARE_DHCP_PATH = "/flatnetworkprovider/dhcp/batchPrepare"
    RELEASE_DHCP_PATH = "/flatnetworkprovider/dhcp/release"
    DHCP_CONNECT_PATH = "/flatnetworkprovider/dhcp/connect"
    RESET_DEFAULT_GATEWAY_PATH = "/flatnetworkprovider/dhcp/resetDefaultGateway"
    APPLY_USER_DATA = "/flatnetworkprovider/userdata/apply"
    RELEASE_USER_DATA = "/flatnetworkprovider/userdata/release"
    BATCH_APPLY_USER_DATA = "/flatnetworkprovider/userdata/batchapply"
    DHCP_DELETE_NAMESPACE_PATH = "/flatnetworkprovider/dhcp/deletenamespace"
    DHCP_FLUSH_NAMESPACE_PATH = "/flatnetworkprovider/dhcp/flush"
    ARPING_NAMESPACE_PATH = "/flatnetworkprovider/arping"
    CLEANUP_USER_DATA = "/flatnetworkprovider/userdata/cleanup"
    SET_DNS_FORWARD_PATH = '/dns/forward/set'
    REMOVE_DNS_FORWARD_PATH = '/dns/forward/remove'


    DNSMASQ_CONF_FOLDER = "/var/lib/zstack/dnsmasq/"
    DNSMASQ_LOG_LOGROTATE_PATH = "/etc/logrotate.d/dnsmasq"

    USERDATA_ROOT = "/var/lib/zstack/userdata/"

    CONNECT_ALL_NETNS_BR_NAME = "br_conn_all_ns"
    CONNECT_ALL_NETNS_BR_OUTER_IP = "169.254.64.1"
    CONNECT_ALL_NETNS_BR_INNER_IP = "169.254.64.2"
    IP_MASK_BIT = 18

    KVM_HOST_AGENT_PORT = "7070"
    KVM_HOST_PUSHGATEWAY_PORT = "9092"

    def __init__(self):
        self.signal_count = 0
        self.userData_vms = {}

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.DHCP_CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.APPLY_DHCP_PATH, self.apply_dhcp)
        http_server.register_async_uri(self.BATCH_APPLY_DHCP_PATH, self.batch_apply_dhcp)
        http_server.register_async_uri(self.BATCH_APPLY_USER_DATA, self.batch_apply_userdata)
        http_server.register_async_uri(self.RELEASE_DHCP_PATH, self.release_dhcp)
        http_server.register_async_uri(self.PREPARE_DHCP_PATH, self.prepare_dhcp)
        http_server.register_async_uri(self.BATCH_PREPARE_DHCP_PATH, self.batch_prepare_dhcp)
        http_server.register_async_uri(self.APPLY_USER_DATA, self.apply_userdata)
        http_server.register_async_uri(self.RELEASE_USER_DATA, self.release_userdata)
        http_server.register_async_uri(self.RESET_DEFAULT_GATEWAY_PATH, self.reset_default_gateway)
        http_server.register_async_uri(self.DHCP_DELETE_NAMESPACE_PATH, self.delete_dhcp_namespace)
        http_server.register_async_uri(self.DHCP_FLUSH_NAMESPACE_PATH, self.flush_dhcp_namespace)
        http_server.register_async_uri(self.ARPING_NAMESPACE_PATH, self.arping_dhcp_namespace)
        http_server.register_async_uri(self.CLEANUP_USER_DATA, self.cleanup_userdata)
        http_server.register_async_uri(self.SET_DNS_FORWARD_PATH, self.setup_dns_forward)
        http_server.register_async_uri(self.REMOVE_DNS_FORWARD_PATH, self.remove_dns_forward)
        self.register_dnsmasq_logRotate()

    def stop(self):
        pass

    @lock.lock('dnsmasq')
    @kvmagent.replyerror
    def remove_dns_forward(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RemoveForwardDnsRsp()

        conf_file_path, dhcp_path, dns_path, option_path, _ = self._make_conf_path(cmd.nameSpace)
        self._remove_dns_forward(cmd.mac, option_path)
        self._restart_dnsmasq(cmd.nameSpace, conf_file_path)

        return jsonobject.dumps(rsp)

    def _remove_dns_forward(self, mac, option_path):
        TAG = mac.replace(':', '')
        OPTION = option_path

        bash_errorout('''\
sed -i '/{{TAG}},/d' {{OPTION}};
sed -i '/^$/d' {{OPTION}};
''')


    @lock.lock('dnsmasq')
    @kvmagent.replyerror
    def setup_dns_forward(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetForwardDnsRsp()

        self._apply_dns_forward(cmd)

        return jsonobject.dumps(rsp)

    def _apply_dns_forward(self, cmd):
        conf_file_path, dhcp_path, dns_path, option_path, log_path = self._make_conf_path(cmd.nameSpace)

        TAG = cmd.mac.replace(':', '')
        OPTION = option_path
        DNS = cmd.wrongDns

        for dns in cmd.wrongDns:
            DNS = dns
            bash_errorout('''\
            sed -i '/{{TAG}},option:dns-server,{{DNS}}/d' {{OPTION}};
            sed -i '/^$/d' {{OPTION}};
            ''')

        DNS = cmd.dns
        option_conf = '''\
tag:{{TAG}},option:dns-server,{{DNS}}

'''
        tmpt = Template(option_conf)
        option_conf = tmpt.render({'TAG': TAG, 'DNS': DNS})
        mode = 'a+'
        with open(option_path, mode) as fd:
            fd.write(option_conf)

        self._restart_dnsmasq(cmd.nameSpace, conf_file_path)

    @in_bash
    def _delete_dhcp(self, namespace):
        outer = "outer%s" % ip.get_namespace_id(namespace)
        self._delete_dhcp4(namespace)
        self._delete_dhcp6(namespace)
        bash_r("ps aux | grep -v grep | grep -w dnsmasq | grep -w %s | awk '{printf $2}' | xargs -r kill -9" % namespace)
        # delete inner dev
        bash_r("ip netns exec %s ip link del inner%s" % (namespace, ip.get_namespace_id(namespace)))
        bash_r("ip netns exec %s ip link del ud_inner%s" % (namespace, ip.get_namespace_id(namespace)))
        bash_r(
            "ip netns | grep -w %s | grep -v grep | awk '{print $1}' | xargs -r ip netns del %s" % (namespace, namespace))


    @in_bash
    def _delete_ebtables_chain_by_name(self, chain_name):
        if not chain_name:
            return
        o = bash_o("ebtables-save | grep {{chain_name}} | grep -- -A")
        o = o.strip()
        if o:
            cmds = []
            for l in o.split("\n"):
                cmds.append(get_ebtables_cmd() + " %s" % l.replace("-A", "-D"))

            bash_r("\n".join(cmds))

        ret = bash_r("ebtables-save | grep '\-A {{chain_name}} -j RETURN'")
        if ret != 0:
            bash_r(get_ebtables_cmd() + ' -D {{chain_name}} -j RETURN')

        ret = bash_r("ebtables-save | grep '\-A FORWARD -j {{chain_name}}'")
        if ret != 0:
            bash_r(get_ebtables_cmd() + ' -D FORWARD -j {{chain_name}}')
            bash_r(get_ebtables_cmd() + ' -X {{chain_name}}')

    @in_bash
    def _delete_dhcp6(self, namspace):
        items = namspace.split('_')
        l3_uuid = items[-1]
        OLD_DHCP6_CHAIN_NAME = "ZSTACK-DHCP6-%s" % l3_uuid[0:9]  #this case is for old version dhcp6 namespace
        self._delete_ebtables_chain_by_name(OLD_DHCP6_CHAIN_NAME)

        ns_id = iproute.IpNetnsShell.get_netns_id(namspace)
        INNER_DEV = "inner" + ns_id
        dhcp6_ip = iproute.IpNetnsShell(namspace).get_ip_address(6, INNER_DEV)
        if dhcp6_ip:
            NEW_DHCP6_CHAIN_NAME = getDhcpEbtableChainName(dhcp6_ip)
            self._delete_ebtables_chain_by_name(NEW_DHCP6_CHAIN_NAME)

    @in_bash
    def _delete_dhcp4(self, namspace):
        ns_id = iproute.IpNetnsShell.get_netns_id(namspace)
        INNER_DEV = "inner" + ns_id
        dhcp_ip = iproute.IpNetnsShell(namspace).get_ip_address(4, INNER_DEV)

        if dhcp_ip is not None:
            CHAIN_NAME = getDhcpEbtableChainName(dhcp_ip)
            self._delete_ebtables_chain_by_name(CHAIN_NAME)

    @in_bash
    def _del_bridge_fdb_entry_for_inner_dev(self, cmd):
        BR_NAME = cmd.bridgeName
        NAMESPACE_NAME = cmd.namespaceName
        ns_id = iproute.IpNetnsShell.get_netns_id(NAMESPACE_NAME)
        INNER_DEV = "inner" + ns_id

        # get pf name for inner dev
        r, PHY_DEV, e = bash_roe(
            "brctl show {{BR_NAME}} | grep -w {{BR_NAME}} | head -n 1 | awk '{ print $NF }' | { read name; echo ${name%%.*}; }")
        if r != 0:
            logger.error("cannot get physical interface name from bridge " + BR_NAME)
            return
        PHY_DEV = PHY_DEV.strip()

        # get mac address of inner dev
        INNER_MAC = iproute.IpNetnsShell(NAMESPACE_NAME).get_mac(INNER_DEV)

        iproute.del_fdb_entry(PHY_DEV, INNER_MAC)

    @kvmagent.replyerror
    @in_bash
    def delete_dhcp_namespace(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._del_bridge_fdb_entry_for_inner_dev(cmd)
        self._delete_dhcp(cmd.namespaceName)

        return jsonobject.dumps(DeleteNamespaceRsp())

    @kvmagent.replyerror
    @in_bash
    def flush_dhcp_namespace(self, req):
        # kill dnsmasq, but will not delete the namespace
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        ns = DhcpNameSpaceEnv(cmd.bridgeName, cmd.namespaceName)
        ns.disable()

        return jsonobject.dumps(DeleteNamespaceRsp())

    #@thread.AsyncThread
    def __do_arping_namepsace(self, ns, ip):
        macs = []
        r, o, e = bash_roe(
            "ip netns exec %s arping -I %s -w 1 -c 3 -D %s | grep 'Unicast reply from'"
            % (ns.namespace_name, ns.near_vm_inner, ip))
        if r != 0:
            return macs

        # parse result
        # example: Unicast reply from 172.25.19.33 [AC:1F:6B:EE:87:B2]  0.641ms
        lines = o.split("\r\n")
        for l in lines:
            items = l.split(" ")
            mac = items[4].strip('[').strip(']')
            macs.append(mac)

        return macs

    @kvmagent.replyerror
    @in_bash
    def arping_dhcp_namespace(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        #get namespace
        ns = NamespaceInfraEnv(cmd.bridgeName, cmd.namespaceName)
        ns.prepare_dev()

        #TODO: to be simple, current only 1 ip address is detected
        macs = self.__do_arping_namepsace(ns, cmd.targetIps[0])

        if ns.ns_new_created:
            ns.delete_dev()

        rsp = ArpingRsp()
        rsp.result[cmd.targetIps[0]] = macs
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def restore_ebtables_chain_except_kvmagent(self):
        class EbtablesRules(object):
            default_tables = ["nat", "filter", "broute"]
            default_rules = {"nat": "*nat\n:PREROUTING ACCEPT\n:OUTPUT ACCEPT\n:POSTROUTING ACCEPT\n",
                             "filter": "*filter\n:INPUT ACCEPT\n:FORWARD ACCEPT\n:OUTPUT ACCEPT\n",
                             "broute": "*broute\n:BROUTING ACCEPT"}

            @in_bash
            def __init__(self):
                self.raw_text = bash_o("ebtables-save").strip().splitlines()
                self.tables = {}
                self.chain_names = {}
                for table in EbtablesRules.default_tables:
                    self.tables[table] = self._get_table(table)  # type: dict[str, list]
                    self.chain_names[table] = self._get_chain_names(table)  # type: dict[str, list]

            def _get_table(self, table):
                result = []
                is_table = False

                if table not in EbtablesRules.default_tables:
                    raise Exception('invalid ebtables table %s' % table)

                for line in self.raw_text:
                    if len(line) < 1:
                        continue
                    if "*"+table in line:
                        is_table = True
                    elif line[0] == "*":
                        is_table = False

                    if is_table:
                        result.append(line)

                return result

            def _get_chain_names(self, table):
                result = []
                for line in self.tables[table]:
                    if line[0] == ':':
                        result.append(line.split(" ")[0].strip(":"))

                return result

            def _get_related_chain_names(self, table, keyword):
                # type: (str, str) -> list[str]
                result = []
                for name in self.chain_names[table]:
                    if keyword in name:
                        result.append(name)

                for line in self.tables[table]:
                    if line[0] == ':':
                        continue
                    if len(list([x for x in result if '-A %s ' % x in line])) < 1:
                        continue
                    jump_chain = self._get_jump_chain_name_from_cmd(table, line)
                    if jump_chain:
                        result.extend(self._get_related_chain_names(table, jump_chain))

                return list(set(result))

            def _get_jump_chain_name_from_cmd(self, table, cmd):
                jump = cmd.split(" -j ")[1]
                if jump in self.chain_names[table]:
                    return jump
                return None

            def _get_related_top_chain_names(self, table, pattern):
                # type: (str, str) -> list[str]
                result = []
                for name in self.chain_names[table]:
                    if re.search(pattern, name):
                        result.append(name)
                return list(set(result))

            def _get_related_table_rules(self, table, keywords):
                # type: (str, list) -> list[str]
                result = []
                related_chains = []
                for keyword in list(set(keywords)):
                    related_chains.extend(self._get_related_chain_names(table, keyword))
                for line in self.tables[table]:
                    if len(list([x for x in related_chains if x in line])) > 0:
                        result.append(line)

                default_rules = EbtablesRules.default_rules[table]
                r = default_rules.splitlines()
                r.extend(result)
                return r

            def get_related_rules_re(self, patterns):
                # type: (dict[str, list]) -> list[str]
                result = []
                if not set(patterns.keys()).issubset(EbtablesRules.default_tables):
                    raise Exception('invalid parameter table %s' % list(patterns.keys()))

                for key, value in list(patterns.items()):
                    keywords = []
                    for pattern in value:
                        keywords.extend(self._get_related_top_chain_names(key, pattern))
                    if len(keywords) > 0:
                        result.extend(self._get_related_table_rules(key, keywords))

                return result

        logger.debug("start clean ebtables...")
        ebtables_obj = EbtablesRules()
        fd, path = tempfile.mkstemp(".ebtables.dump")
        #ZSTAC-24684 restore the rule created by libvirt & zsn
        patterns={"nat":["libvirt","(^z|^s)[0-9]*_","^eip-"], "filter":["(^z|^s)[0-9]*_|^vr"]}
        restore_data = "\n".join(ebtables_obj.get_related_rules_re(patterns)) + "\n"
        logger.debug("restore ebtables: %s" % restore_data)
        with os.fdopen(fd, 'w') as fs:
            fs.write(restore_data)
        bash_o("ebtables-restore < %s" % path)
        os.remove(path)
        logger.debug("clean ebtables successfully")

    @kvmagent.replyerror
    def connect(self, req):
        #shell.call(get_ebtables_cmd() + ' -F')
        # shell.call(get_ebtables_cmd() + ' -t nat -F')
        # this is workaround, for anti-spoofing & distributed virtual routing feature, there is no good way to proccess this reconnect-host case,
        # it's just keep the ebtables rules from libvirt & zsn and remove others when reconnect hosts
        self.restore_ebtables_chain_except_kvmagent()
        return jsonobject.dumps(ConnectRsp())

    @kvmagent.replyerror
    @in_bash
    def cleanup_userdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        BR_NAME = cmd.bridgeName
        CHAIN_NAME = get_ebtables_userdata_chain_name(BR_NAME, cmd.l3NetworkUuid)

        cmds = []
        o = bash_o("ebtables-save | grep {{CHAIN_NAME}} | grep -- -A")
        o = o.strip()
        if o:
            for l in o.split("\n"):
                # we don't distinguish if the rule is in filter table or nat table
                # but try both. The wrong table will silently fail
                cmds.append(get_ebtables_cmd() + " -t filter %s" % l.replace("-A", "-D"))
                cmds.append(get_ebtables_cmd() + " -t nat %s" % l.replace("-A", "-D"))

        if bash_r("ebtables-save | grep :{{CHAIN_NAME}}") == 0:
            cmds.append(get_ebtables_cmd() + " -t filter -X %s" % CHAIN_NAME)
            cmds.append(get_ebtables_cmd() + " -t nat -X %s" % CHAIN_NAME)

        if len(cmds) > 0:
            bash_r("\n".join(cmds))

        bash_errorout("pkill -9 -f 'lighttpd.*/userdata/{{BR_NAME}}.*_%s' || true" % cmd.l3NetworkUuid)

        html_folder = os.path.join(self.USERDATA_ROOT, cmd.namespaceName)
        linux.rm_dir_force(html_folder)

        if cmd.l3NetworkUuid in self.userData_vms:
            del self.userData_vms[cmd.l3NetworkUuid]

        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    @lock.lock('lighttpd')
    def batch_apply_userdata(self, req):
        started_at = time.time()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        namespaces = {}
        for u in cmd.userdata:
            if u.l3NetworkUuid in self.userData_vms:
                if u.vmIp not in self.userData_vms[u.l3NetworkUuid]:
                    self.userData_vms[u.l3NetworkUuid].append(u.vmIp)
            else:
                self.userData_vms[u.l3NetworkUuid] = [u.vmIp]

            if u.namespaceName not in namespaces:
                namespaces[u.namespaceName] = u
            else:
                if namespaces[u.namespaceName].dhcpServerIp != u.dhcpServerIp:
                    raise Exception('same namespace [%s] but has different dhcpServerIp: %s, %s ' % (
                        u.namespaceName, namespaces[u.namespaceName].dhcpServerIp, u.dhcpServerIp))
                if namespaces[u.namespaceName].bridgeName != u.bridgeName:
                    raise Exception('same namespace [%s] but has different bridgeName: %s, %s ' % (
                    u.namespaceName, namespaces[u.namespaceName].bridgeName, u.bridgeName))
                if namespaces[u.namespaceName].port != u.port:
                    raise Exception('same namespace [%s] but has different port: %s, %s ' % (
                    u.namespaceName, namespaces[u.namespaceName].port, u.port))

        restart_required = {}
        xtables_started_at = time.time()
        for n in list(namespaces.values()):
            restart_required[n.namespaceName] = self._apply_userdata_xtables(n)

        vmdata_started_at = time.time()
        for u in cmd.userdata:
            self._apply_userdata_vmdata(u)

        lighttpd_started_at = time.time()
        for n in list(namespaces.values()):
            self._apply_userdata_restart_httpd(n, restart_required.get(n.namespaceName, True))

        logger.debug('batch apply userdata done, vm count: %s, namespace count: %s, xtables: %.3fs, vmdata: %.3fs, lighttpd: %.3fs, total: %.3fs' % (
            len(cmd.userdata), len(namespaces), vmdata_started_at - xtables_started_at,
            lighttpd_started_at - vmdata_started_at, time.time() - lighttpd_started_at, time.time() - started_at))

        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    @lock.lock('lighttpd')
    def apply_userdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        restart_required = self._apply_userdata_xtables(cmd.userdata)
        self._apply_userdata_vmdata(cmd.userdata)
        self._apply_userdata_restart_httpd(cmd.userdata, restart_required)
        return jsonobject.dumps(ApplyUserdataRsp())

    @in_bash
    @lock.lock('prepare_dhcp_namespace')
    @lock.file_lock('/run/xtables.lock')
    def _apply_userdata_xtables(self, to):
        def create_default_userdata(http_root):
            root = os.path.join(http_root, "zstack-default")
            meta_root = os.path.join(root, 'meta-data')
            if not os.path.exists(meta_root):
                linux.mkdir(meta_root)

            index_file_path = os.path.join(meta_root, 'index.html')
            write_file_if_changed(index_file_path, '')

        def prepare_br_connect_ns(ns, ns_inner_dev, ns_outer_dev):
            bridge_name = self.CONNECT_ALL_NETNS_BR_NAME

            if not linux.is_network_device_existing(bridge_name):
                shell.call("brctl addbr %s" % bridge_name)
                shell.call("brctl stp %s off" % bridge_name)
                shell.call("brctl setfd %s 0" % bridge_name)
                iproute.add_address(self.CONNECT_ALL_NETNS_BR_OUTER_IP, self.IP_MASK_BIT, 4, bridge_name)
                iproute.set_link_up(bridge_name)

            addrs = iproute.query_addresses(ifname=bridge_name, address=self.CONNECT_ALL_NETNS_BR_OUTER_IP, prefixlen=self.IP_MASK_BIT)
            if not addrs:
                iproute.add_address(self.CONNECT_ALL_NETNS_BR_OUTER_IP, self.IP_MASK_BIT, 4, bridge_name)

            #"ip link add %s type veth peer name %s", max length of second parameter is 15 characters
            userdata_br_outer_dev = "ud_" + ns_outer_dev
            userdata_br_inner_dev = "ud_" + ns_inner_dev
            MAX_MTU = linux.MAX_MTU_OF_VNIC

            ensure_userdata_veth_pair(ns, userdata_br_outer_dev, userdata_br_inner_dev, MAX_MTU)

            iproute.set_link_up(userdata_br_outer_dev)

            ret = bash_r('brctl show %s | grep -w %s > /dev/null' % (bridge_name, userdata_br_outer_dev))
            if ret != 0:
                bash_errorout('brctl addif %s %s' % (bridge_name, userdata_br_outer_dev))

            mac = iproute.IpNetnsShell(ns).get_mac(userdata_br_inner_dev)
            if mac is None:
                iproute.IpNetnsShell(ns).add_link(userdata_br_inner_dev)

            ns_id = ns_inner_dev[5:]
            if int(ns_id) > 16381:
                # 169.254.64.1/18 The maximum available ip is only 16381 (exclude 169.254.64.1)
                # It is impossible to configure tens of thousands of networks on host
                raise Exception('add ip addr fail, namespace id exceeds limit')
            ip2int = struct.unpack('!L', socket.inet_aton(self.CONNECT_ALL_NETNS_BR_INNER_IP))[0]
            userdata_br_inner_dev_ip = socket.inet_ntoa(struct.pack('!L', ip2int + int(ns_id)))
            addr = iproute.IpNetnsShell(ns).get_ip_address(4, userdata_br_inner_dev)
            if addr is None:
                iproute.IpNetnsShell(ns).add_ip_address(userdata_br_inner_dev_ip, self.IP_MASK_BIT, userdata_br_inner_dev)

            iproute.IpNetnsShell(ns).set_link_up(userdata_br_inner_dev)

        p = UserDataEnv(to.bridgeName, to.namespaceName, to.vlanId)
        INNER_DEV = None
        DHCP_IP = None
        NS_NAME = to.namespaceName

        if not to.hasattr("dhcpServerIp"):
            p.prepare()
            INNER_DEV = p.inner_dev
        else:
            DHCP_IP = to.dhcpServerIp
            INNER_DEV = iproute.IpNetnsShell(NS_NAME).get_link_name_by_ip(DHCP_IP, 4)
        if not INNER_DEV:
            p.prepare()
            INNER_DEV = p.inner_dev
        if not INNER_DEV:
            raise Exception('cannot find device for the DHCP IP[%s]' % DHCP_IP)

        outer_dev = p.outer_dev if(p.outer_dev != None) else ("outer" + INNER_DEV[5:])
        prepare_br_connect_ns(NS_NAME, INNER_DEV, outer_dev)

        addr = iproute.IpNetnsShell(NS_NAME).get_userdata_ip_address(INNER_DEV)
        if addr is None:
            iproute.IpNetnsShell(NS_NAME).add_ip_address('169.254.169.254', 32, INNER_DEV)

        r, o = bash_ro('ip netns exec {{NS_NAME}} ip r | wc -l')
        if not to.hasattr("dhcpServerIp") and int(o) == 0:
            bash_errorout('ip netns exec {{NS_NAME}} ip r add default dev {{INNER_DEV}}')

        # set ebtables
        BR_NAME = to.bridgeName
        VLAN_ID = to.vlanId
        ETH_NAME = get_phy_dev_from_bridge_name(BR_NAME, VLAN_ID)

        MAC = iproute.IpNetnsShell(NS_NAME).get_mac(INNER_DEV)
        CHAIN_NAME = "USERDATA-%s" % BR_NAME
        EBCHAIN_NAME = get_ebtables_userdata_chain_name(BR_NAME, to.l3NetworkUuid)

        ret = bash_r(get_ebtables_cmd() + ' -t nat -L {{EBCHAIN_NAME}} >/dev/null 2>&1')
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -t nat -N {{EBCHAIN_NAME}}')

        if bash_r(get_ebtables_cmd() + " -t nat -L PREROUTING | grep -E -- '(--logical-in|-i) {{BR_NAME}} -j {{EBCHAIN_NAME}}'") != 0:
            # try --logical-in first; fall back to -i for kernels (e.g. alinux4 >= 6.6.102-5.3) that reject `meta ibrname`
            if bash_r(get_ebtables_cmd() + ' -t nat -I PREROUTING --logical-in {{BR_NAME}} -j {{EBCHAIN_NAME}}') != 0:
                bash_errorout(get_ebtables_cmd() + ' -t nat -I PREROUTING -i {{BR_NAME}} -j {{EBCHAIN_NAME}}')

        # ebtables has a bug that will eliminate 0 in MAC, for example, aa:bb:0c will become aa:bb:c
        cidr = ip.IpAddress(to.vmIp).toCidr(to.netmask)
        macAddr = ip.removeZeroFromMacAddress(MAC)
        RULE = "-p IPv4 --ip-src %s --ip-dst 169.254.169.254 -j dnat --to-dst %s --dnat-target ACCEPT" % (cidr, macAddr)
        ret = bash_r(get_ebtables_cmd() + " -t nat -L {{EBCHAIN_NAME}} | grep -- '{{RULE}}' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -t nat -I {{EBCHAIN_NAME}} {{RULE}}')

        ret = bash_r(get_ebtables_cmd() + " -t nat -L {{EBCHAIN_NAME}} | grep -- '--arp-ip-dst %s' > /dev/null" % self.CONNECT_ALL_NETNS_BR_OUTER_IP)
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -t nat -I {{EBCHAIN_NAME}}  -p arp  --arp-ip-dst %s -j DROP' % self.CONNECT_ALL_NETNS_BR_OUTER_IP)

        ret = bash_r(get_ebtables_cmd() + " -t nat -L {{EBCHAIN_NAME}} | grep -- '-j RETURN' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -t nat -A {{EBCHAIN_NAME}} -j RETURN')

        ret = bash_r(get_ebtables_cmd() + ' -L {{EBCHAIN_NAME}} >/dev/null 2>&1')
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -N {{EBCHAIN_NAME}}')

        ret = bash_r(get_ebtables_cmd() + " -L FORWARD | grep -- '-p ARP --arp-ip-dst 169.254.169.254 -j {{EBCHAIN_NAME}}' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -I FORWARD -p ARP --arp-ip-dst 169.254.169.254 -j {{EBCHAIN_NAME}}')

        ret = bash_r(get_ebtables_cmd() + " -L {{EBCHAIN_NAME}} | grep -- '-i {{ETH_NAME}} -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -I {{EBCHAIN_NAME}} -i {{ETH_NAME}} -j DROP')

        ret = bash_r(get_ebtables_cmd() + " -L {{EBCHAIN_NAME}} | grep -- '-o {{ETH_NAME}} -j DROP' > /dev/null")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -I {{EBCHAIN_NAME}} -o {{ETH_NAME}} -j DROP')

        ret = bash_r("ebtables-save | grep '\-A {{EBCHAIN_NAME}} -j RETURN'")
        if ret != 0:
            bash_errorout(get_ebtables_cmd() + ' -A {{EBCHAIN_NAME}} -j RETURN')

        self.work_userdata_iptables(CHAIN_NAME, to)

        conf_folder = os.path.join(self.USERDATA_ROOT, to.namespaceName)
        if not os.path.exists(conf_folder):
            linux.mkdir(conf_folder)

        conf_path = os.path.join(conf_folder, 'lighttpd.conf')
        http_root = os.path.join(conf_folder, 'html')

        if to.l3NetworkUuid in self.userData_vms:
            if to.vmIp not in self.userData_vms[to.l3NetworkUuid]:
                self.userData_vms[to.l3NetworkUuid].append(to.vmIp)
        else:
            self.userData_vms[to.l3NetworkUuid] = [to.vmIp]

        if to.l3NetworkUuid in self.userData_vms:
            userdata_vm_ips = self.userData_vms[to.l3NetworkUuid]
        else:
            userdata_vm_ips = []

        conf = '''\
server.document-root = "{{http_root}}"

server.port = {{port}}
server.bind = "169.254.169.254"
server.max-worker=1
dir-listing.activate = "enable"
index-file.names = ( "index.html" )

server.modules += ("mod_proxy", "mod_rewrite", "mod_access", "mod_accesslog",)
accesslog.filename = "/var/log/lighttpd/lighttpd_access.log"
server.errorlog = "/var/log/lighttpd/lighttpd_error.log"

$HTTP["remoteip"] =~ "^(.*)$" {
    $HTTP["url"] =~ "^/metrics/job" {
        proxy.server = ( "" =>
           ( ( "host" => "{{pushgateway_ip}}", "port" => {{pushgateway_port}} ) )
        )
    } else $HTTP["url"] =~ "^/host" {
        proxy.server = ( "" =>
           ( ( "host" => "{{kvmagent_ip}}", "port" => {{kvmagent_port}} ) )
        )
{% for ip in userdata_vm_ips -%}
    } else $HTTP["remoteip"] == "{{ip}}" {
        url.rewrite-once = (
            "^/zwatch-vm-agent.linux-amd64.bin$" => "/zwatch-vm-agent",
            "^/zwatch-vm-agent.freebsd-amd64.bin$" => "/zwatch-vm-agent_freebsd_amd64",
            "^/zwatch-vm-agent.linux-aarch64.bin$" => "/zwatch-vm-agent_aarch64",
            "^/zwatch-vm-agent.linux-mips64el.bin$" => "/collectd_exporter_mips64el",
            "^/zwatch-vm-agent.linux-loongarch64.bin$" => "/collectd_exporter_loongarch64",
            "^/agent-tools-update.sh$" => "/vm-tools.sh",
            "^/.*/meta-data/(.+)$" => "/{{ip}}/meta-data/$1",
            "^/.*/meta-data$" => "/{{ip}}/meta-data",
            "^/.*/meta-data/$" => "/{{ip}}/meta-data/",
            "^/.*/user-data$" => "/{{ip}}/user-data",
            "^/.*/user_data$" => "/{{ip}}/user_data",
            "^/.*/meta_data.json$" => "/{{ip}}/meta_data.json",
            "^/.*/password$" => "/{{ip}}/password",
            "^/.*/$" => "/{{ip}}/$1",
            "^/$" => "{{ip}}/$1"
        )
        dir-listing.activate = "enable"
{% endfor -%}
    } else $HTTP["remoteip"] =~ "^(.*)$" {
        url.rewrite-once = (
            "^/zwatch-vm-agent.linux-amd64.bin$" => "/zwatch-vm-agent",
            "^/zwatch-vm-agent.freebsd-amd64.bin$" => "/zwatch-vm-agent_freebsd_amd64",
            "^/zwatch-vm-agent.linux-aarch64.bin$" => "/zwatch-vm-agent_aarch64",
            "^/zwatch-vm-agent.linux-mips64el.bin$" => "/collectd_exporter_mips64el",
            "^/zwatch-vm-agent.linux-loongarch64.bin$" => "/collectd_exporter_loongarch64",
            "^/agent-tools-update.sh$" => "/vm-tools.sh",
            "^/.*/meta-data/(.+)$" => "../zstack-default/meta-data/$1",
            "^/.*/meta-data$" => "../zstack-default/meta-data",
            "^/.*/meta-data/$" => "../zstack-default/meta-data/",
            "^/.*/user-data$" => "../zstack-default/user-data",
            "^/.*/user_data$" => "../zstack-default/user_data",
            "^/.*/meta_data.json$" => "../zstack-default/meta_data.json",
            "^/.*/password$" => "../zstack-default/password",
            "^/.*/$" => "../zstack-default/$1"
        )
        dir-listing.activate = "enable"
    }
}

mimetype.assign = (
  ".html" => "text/html",
  ".txt" => "text/plain",
  ".jpg" => "image/jpeg",
  ".png" => "image/png"
)'''

        tmpt = Template(conf)
        conf = tmpt.render({
            'http_root': http_root,
            'port': to.port,
            'pushgateway_ip' : self.CONNECT_ALL_NETNS_BR_OUTER_IP,
            'pushgateway_port' : self.KVM_HOST_PUSHGATEWAY_PORT,
            'kvmagent_ip' : self.CONNECT_ALL_NETNS_BR_OUTER_IP,
            'kvmagent_port' : self.KVM_HOST_AGENT_PORT,
            'userdata_vm_ips': userdata_vm_ips
        })

        linux.mkdir(http_root, 0o777)

        conf_changed = write_file_if_changed(conf_path, conf)

        create_default_userdata(http_root)
        self.apply_zwatch_vm_agent(http_root)
        return conf_changed

    def apply_zwatch_vm_agent(self, http_root):
        agent_file_source_path = "/var/lib/zstack/kvm/zwatch-vm-agent"
        freebsd_agent_file_source_path = "/var/lib/zstack/kvm/zwatch-vm-agent_freebsd_amd64"
        if not os.path.exists(agent_file_source_path):
            logger.error("Can't find file %s" % agent_file_source_path)
            return

        if HOST_ARCH == 'x86_64' and not os.path.exists(freebsd_agent_file_source_path):
            logger.error("Can't find file %s" % freebsd_agent_file_source_path)
            return

        agent_file_target_path = os.path.join(http_root, "zwatch-vm-agent")
        if not os.path.exists(agent_file_target_path):
            bash_r("ln -s %s %s" % (agent_file_source_path, agent_file_target_path))
        elif not os.path.islink(agent_file_target_path):
            linux.rm_file_force(agent_file_target_path)
            bash_r("ln -s %s %s" % (agent_file_source_path, agent_file_target_path))

        freebsd_agent_file_target_path = os.path.join(http_root, "zwatch-vm-agent_freebsd_amd64")
        if not os.path.exists(freebsd_agent_file_target_path):
            bash_r("ln -s %s %s" % (freebsd_agent_file_source_path, freebsd_agent_file_target_path))
        elif not os.path.islink(freebsd_agent_file_target_path):
            linux.rm_file_force(freebsd_agent_file_target_path)
            bash_r("ln -s %s %s" % (freebsd_agent_file_source_path, freebsd_agent_file_target_path))

        tool_sh_file_path = "/var/lib/zstack/kvm/vm-tools.sh"
        if not os.path.exists(tool_sh_file_path):
            logger.error("Can't find file %s" % tool_sh_file_path)
            return
        target_tool_sh_file_path = os.path.join(http_root, "vm-tools.sh")
        if not os.path.exists(target_tool_sh_file_path):
            bash_r("ln -s %s %s" % (tool_sh_file_path, target_tool_sh_file_path))
        elif not os.path.islink(target_tool_sh_file_path):
            linux.rm_file_force(target_tool_sh_file_path)
            bash_r("ln -s %s %s" % (tool_sh_file_path, target_tool_sh_file_path))

        version_file_path = "/var/lib/zstack/kvm/agent_version"
        if not os.path.exists(version_file_path):
            logger.error("Can't find file %s" % version_file_path)
            return
        target_version_file_path = os.path.join(http_root, "agent_version")
        if not os.path.exists(target_version_file_path):
            bash_r("ln -s %s %s" % (version_file_path, target_version_file_path))
        elif not os.path.islink(target_version_file_path):
            linux.rm_file_force(target_version_file_path)
            bash_r("ln -s %s %s" % (version_file_path, target_version_file_path))

    class FieldMapper:
        def __init__(self, field_map):
            self.field_map = field_map

        def get_file_name(self, field_name):
            return self.field_map.get(field_name, field_name)

    class NetworkInterfaceHandler:
        def __init__(self, meta_root, network_interfaces):
            self.meta_root = meta_root
            self.network_interfaces = network_interfaces
            # network mapping to fileName
            self.nic_field_mapper = Mevoco.FieldMapper({
                'macAddress': 'mac',
                'gateway': 'gateway',
                'netmask': 'netmask',
                'ip': 'primary-ip-address',
                'vpcCidrBlock': 'vpc-cidr-block',
                'vSwitchCidrBlock': 'vswitch-cidr-block',
            })

        def write_network_interface_files(self):
            macs_root = os.path.join(self.meta_root, 'network', 'interfaces', 'macs')
            if not os.path.exists(macs_root):
                linux.mkdir(macs_root)

            # macs/index.html
            mac_index_file_path = os.path.join(macs_root, 'index.html')
            mac_index = ''
            for nic in self.network_interfaces:
                mac_index += nic.macAddress + '\n'
            write_file_if_changed(mac_index_file_path, mac_index)

            # write value to file for each nic
            for nic in self.network_interfaces:
                mac_dir = os.path.join(macs_root, nic.macAddress)
                if not os.path.exists(mac_dir):
                    linux.mkdir(mac_dir)

                for attr, file_name in self.nic_field_mapper.field_map.items():
                    if hasattr(nic, attr) and getattr(nic, attr):
                        file_path = os.path.join(mac_dir, file_name)
                        write_file_if_changed(file_path, getattr(nic, attr))
                mac_index = os.path.join(mac_dir, 'index.html')
                index_content = ''
                for attr, file_name in self.nic_field_mapper.field_map.items():
                    if hasattr(nic, attr) and getattr(nic, attr):
                        index_content += file_name + '\n'
                write_file_if_changed(mac_index, index_content)

    def _write_metadata_files(self, meta_root, to):
        field_mapper = self.FieldMapper({
            'vmUuid': 'instance-id',
            'vmHostname': 'local-hostname',
            'regionName': 'region-id',
            'mac': 'mac',
            'dnsServersIp': 'dns-conf/',
            'vpcId': 'vpc-id',
            'vmIp': 'private-ipv4',
        })

        # index.html
        index_file_path = os.path.join(meta_root, 'index.html')
        index_content = ''
        for field in ['vmUuid', 'vmHostname', 'regionName', 'mac', 'vpcId', 'dnsServersIp']:
            value = getattr(to.metadata, field, None)
            if value:
                index_content += field_mapper.get_file_name(field) + '\n'
        if to.vmIp:
            index_content += 'private-ipv4\n'
        if to.networkInterfaces:
            index_content += 'network/\n'
        write_file_if_changed(index_file_path, index_content)

        # write value to single file
        for field in ['vmUuid', 'vmHostname', 'regionName', 'vpcId', 'mac']:
            value = getattr(to.metadata, field, None)
            if value:
                file_path = os.path.join(meta_root, field_mapper.get_file_name(field))
                write_file_if_changed(file_path, value)

        # private-ipv4
        if to.vmIp:
            vm_ip_file_path = os.path.join(meta_root, 'private-ipv4')
            write_file_if_changed(vm_ip_file_path, to.vmIp)

        # dns-conf/nameservers
        if to.metadata.dnsServersIp:
            dns_conf_dir = os.path.join(meta_root, 'dns-conf')
            if not os.path.exists(dns_conf_dir):
                linux.mkdir(dns_conf_dir)
            nameservers_file_path = os.path.join(dns_conf_dir, 'nameservers')
            write_file_if_changed(nameservers_file_path, to.metadata.dnsServersIp)
            dns_conf_index_path = os.path.join(dns_conf_dir, 'index.html')
            write_file_if_changed(dns_conf_index_path, 'nameservers\n')
        if to.networkInterfaces:
            network_root = os.path.join(meta_root, 'network')
            if not os.path.exists(network_root):
                linux.mkdir(network_root)
            network_index = os.path.join(network_root, 'index.html')
            write_file_if_changed(network_index, 'interfaces/\n')
            interfaces_root = os.path.join(network_root, 'interfaces')
            if not os.path.exists(interfaces_root):
                linux.mkdir(interfaces_root)
            interfaces_index = os.path.join(interfaces_root, 'index.html')
            write_file_if_changed(interfaces_index, 'macs/\n')

        # network/interfaces/macs
        if to.networkInterfaces:
            handler = self.NetworkInterfaceHandler(meta_root, to.networkInterfaces)
            handler.write_network_interface_files()

    @in_bash
    def _apply_userdata_vmdata(self, to):
        def packUserdata(userdataList):
            if len(userdataList) == 1:
                return userdataList[0]

            combined_message = MIMEMultipart()
            for userdata in userdataList:
                userdata = userdata.strip()
                msg = email.message_from_file(c.StringIO(userdata))
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    combined_message.attach(part)

            return combined_message.__str__()

        conf_folder = os.path.join(self.USERDATA_ROOT, to.namespaceName)
        http_root = os.path.join(conf_folder, 'html')
        meta_data_json = '''\
{
    "uuid": "{{vmInstanceUuid}}"
}'''
        tmpt = Template(meta_data_json)
        conf = tmpt.render({
            'vmInstanceUuid': to.metadata.vmUuid
        })

        root = os.path.join(http_root, to.vmIp)
        meta_root = os.path.join(root, 'meta-data')
        if not os.path.exists(meta_root):
            linux.mkdir(meta_root)

        self._write_metadata_files(meta_root, to)

        if to.userdataList:
            userdata_content = packUserdata(to.userdataList)
            userdata_file_path = os.path.join(root, 'user-data')
            write_file_if_changed(userdata_file_path, userdata_content, encoding='utf-8')

            windows_meta_data_json_path = os.path.join(root, 'meta_data.json')
            write_file_if_changed(windows_meta_data_json_path, conf)

            windows_userdata_file_path = os.path.join(root, 'user_data')
            write_file_if_changed(windows_userdata_file_path, userdata_content, encoding='utf-8')

            windows_meta_data_password = os.path.join(root, 'password')
            write_file_if_changed(windows_meta_data_password, '')

        if to.agentConfig:
            pvpanic_file_path = os.path.join(meta_root, 'pvpanic')
            write_file_if_changed(pvpanic_file_path, to.agentConfig.pvpanic if to.agentConfig.pvpanic else 'disable')

    @in_bash
    def _apply_userdata_restart_httpd(self, to, restart_required=True):
        def check(_):
            pid = linux.find_process_by_cmdline([conf_path])
            return pid is not None

        conf_folder = os.path.join(self.USERDATA_ROOT, to.namespaceName)
        conf_path = os.path.join(conf_folder, 'lighttpd.conf')
        pids = linux.find_all_process_by_cmdline([conf_path])
        if pids and not restart_required:
            return

        for pid in pids:
            linux.kill_process(pid)

        pids = linux.find_all_process_by_cmdline([conf_path])
        if pids:
            logger.warn('lighttpd process is still running, pid: %s' % pids)

        linux.mkdir('/var/log/lighttpd', 0o750)
        #restart lighttpd to load new configration
        try:
            shell.call('ip netns exec %s lighttpd -f %s' % (to.namespaceName, conf_path))
        except Exception as e:
            if "Address already in use" in str(e):
                logger.warn('lighttpd process is already running')
                try:
                    netstat = shell.call('ip netns exec %s netstat -anp | grep lighttpd' % to.namespaceName, exception=False)
                    logger.debug('lighttpd process is already running, netstat: %s' % netstat)
                except Exception as e:
                    logger.warn('failed to check lighttpd process: %s' % str(e))
            else:
                logger.warn('failed to start lighttpd: %s' % str(e))

        if not linux.wait_callback_success(check, None, 5):
            raise Exception('lighttpd[conf-file:%s] is not running after being started %s seconds' % (conf_path, 5))

    @in_bash
    @lock.file_lock('/run/xtables.lock')
    def work_userdata_iptables(self, CHAIN_NAME, to):
        # DNAT port 80
        PORT = to.port
        PORT_CHAIN_NAME = "UD-PORT-%s" % PORT
        nat_rules = str(bash_errorout("iptables-save -t nat") or "")
        # delete old chains not matching our port
        old_chains = []
        for line in nat_rules.splitlines():
            if line.startswith(":UD-PORT-"):
                old_chains.append(line.split()[0][1:])
        for OLD_CHAIN in old_chains:
            if OLD_CHAIN and OLD_CHAIN != PORT_CHAIN_NAME:
                if '-j %s' % OLD_CHAIN in nat_rules:
                    bash_r('%s -t nat -D PREROUTING -j {{OLD_CHAIN}}' % get_iptables_cmd())

                bash_errorout('%s -t nat -F {{OLD_CHAIN}}' % get_iptables_cmd())
                bash_errorout('%s -t nat -X {{OLD_CHAIN}}' % get_iptables_cmd())
        if ":%s " % PORT_CHAIN_NAME not in nat_rules:
            self.bash_ignore_exist_for_ipt('%s -t nat -N {{PORT_CHAIN_NAME}}' % get_iptables_cmd())
        if '-A PREROUTING -j %s' % PORT_CHAIN_NAME not in nat_rules:
            self.bash_ignore_exist_for_ipt('%s -t nat -I PREROUTING -j {{PORT_CHAIN_NAME}}' % get_iptables_cmd())
        dnat_rule = '-A %s -d 169.254.169.254/32 -p tcp -j DNAT --to-destination :%s' % (PORT_CHAIN_NAME, PORT)
        if dnat_rule not in nat_rules:
            self.bash_ignore_exist_for_ipt(
                '%s -t nat -A {{PORT_CHAIN_NAME}} -d 169.254.169.254/32 -p tcp -j DNAT --to-destination :{{PORT}}' % get_iptables_cmd())

    @staticmethod
    def bash_ignore_exist_for_ipt(cmd):
        r, o, e = bash_roe(cmd)
        if r == 0:
            return
        elif r == 1 and "iptables: Chain already exists." in e:
            return
        else:
            raise BashError('failed to execute bash[%s], return code: %s, stdout: %s, stderr: %s' % (cmd, r, o, e))

    @kvmagent.replyerror
    def release_userdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        html_folder = os.path.join(self.USERDATA_ROOT, cmd.namespaceName, 'html', cmd.vmIp)
        linux.rm_dir_force(html_folder)
        l3Uuid = get_l3_uuid(cmd.namespaceName)
        if l3Uuid in self.userData_vms and cmd.vmIp in self.userData_vms[l3Uuid]:
            self.userData_vms[l3Uuid].remove(cmd.vmIp)
        return jsonobject.dumps(ReleaseUserdataRsp())

    def _make_conf_path(self, namespace_name):
        folder = os.path.join(self.DNSMASQ_CONF_FOLDER, namespace_name)
        if not os.path.exists(folder):
            linux.mkdir(folder)

        # the conf is created at the initializing time
        conf = os.path.join(folder, 'dnsmasq.conf')

        dhcp = os.path.join(folder, 'hosts.dhcp')
        if not os.path.exists(dhcp):
            linux.touch_file(dhcp)

        dns = os.path.join(folder, 'hosts.dns')
        if not os.path.exists(dns):
            linux.touch_file(dns)

        option = os.path.join(folder, 'hosts.option')
        if not os.path.exists(option):
            linux.touch_file(option)

        log = os.path.join(folder, 'dnsmasq.log')
        if not os.path.exists(log):
            linux.touch_file(log)

        self._make_dnsmasq_logrotate_conf()
        return conf, dhcp, dns, option, log

    def _make_dnsmasq_logrotate_conf(self):
        if not os.path.exists(self.DNSMASQ_LOG_LOGROTATE_PATH):
            content = """/var/lib/zstack/dnsmasq/*/dnsmasq.log {
        rotate 10
        missingok
        copytruncate
        size 30M
        compress
}"""
            with open(self.DNSMASQ_LOG_LOGROTATE_PATH, 'w') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(self.DNSMASQ_LOG_LOGROTATE_PATH, 0o644)

    @lock.lock('prepare_dhcp')
    @kvmagent.replyerror
    def prepare_dhcp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        p = DhcpEnv()
        p.bridge_name = cmd.bridgeName
        p.vlan_id = cmd.vlanId
        p.dhcp_server_ip = cmd.dhcpServerIp
        p.dhcp_server6_ip = cmd.dhcp6ServerIp
        p.dhcp_netmask = cmd.dhcpNetmask
        p.namespace_name = cmd.namespaceName
        p.ipVersion = cmd.ipVersion
        p.prefixLen = cmd.prefixLen
        p.addressMode = cmd.addressMode

        dhcpServerIpChanged = False
        dhcp6ServerIpChanged = False
        INNER_DEV = "inner" + iproute.IpNetnsShell.get_netns_id(cmd.namespaceName)
        old_dhcp_ip = iproute.IpNetnsShell(cmd.namespaceName).get_ip_address(4, INNER_DEV)
        if old_dhcp_ip is not None and old_dhcp_ip != cmd.dhcpServerIp:
            dhcpServerIpChanged = True

        old_dhcp6_ip = iproute.IpNetnsShell(cmd.namespaceName).get_ip_address(6, INNER_DEV)
        if old_dhcp6_ip is not None and old_dhcp6_ip != cmd.dhcp6ServerIp:
            dhcp6ServerIpChanged = True

        if dhcpServerIpChanged or dhcp6ServerIpChanged:
            self._delete_dhcp(cmd.namespaceName)

        p.prepare()

        return jsonobject.dumps(PrepareDhcpRsp())

    @lock.lock('prepare_dhcp')
    @kvmagent.replyerror
    def batch_prepare_dhcp(self, req):
        started_at = time.time()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        for info in cmd.dhcpInfos:
            p = DhcpEnv()
            p.bridge_name = info.bridgeName
            p.vlan_id = info.vlanId
            p.dhcp_server_ip = info.dhcpServerIp
            p.dhcp_server6_ip = info.dhcp6ServerIp
            p.dhcp_netmask = info.dhcpNetmask
            p.namespace_name = info.namespaceName
            p.ipVersion = info.ipVersion
            p.prefixLen = info.prefixLen
            p.addressMode = info.addressMode

            NAMESPACE_ID = ip.get_namespace_id(p.namespace_name)
            INNER_DEV = "inner%s" % NAMESPACE_ID

            old_dhcp_ip = iproute.IpNetnsShell(info.namespaceName).get_ip_address(4, INNER_DEV)
            if old_dhcp_ip is not None and old_dhcp_ip != info.dhcpServerIp:
                self._delete_dhcp4(info.namespaceName)

            old_dhcp6_ip = iproute.IpNetnsShell(info.namespaceName).get_ip_address(6, INNER_DEV)
            if old_dhcp6_ip is not None and old_dhcp6_ip != info.dhcp6ServerIp:
                self._delete_dhcp6(info.namespaceName)

            p.prepare()

        logger.debug('batch prepare dhcp done, namespace count: %s, total: %.3fs' % (len(cmd.dhcpInfos), time.time() - started_at))
        return jsonobject.dumps(PrepareDhcpRsp())

    @lock.lock('dnsmasq')
    @kvmagent.replyerror
    def reset_default_gateway(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        if cmd.namespaceNameOfGatewayToRemove and cmd.macOfGatewayToRemove and cmd.gatewayToRemove:
            conf_file_path, _, _, option_path, _ = self._make_conf_path(cmd.namespaceNameOfGatewayToRemove)
            mac_to_remove = cmd.macOfGatewayToRemove.replace(':', '')

            def is_line_to_delete(line):
                return cmd.gatewayToRemove in line and mac_to_remove in line and 'router' in line

            linux.delete_lines_from_file(option_path, is_line_to_delete)
            self._refresh_dnsmasq(cmd.namespaceNameOfGatewayToRemove, conf_file_path)

        if cmd.namespaceNameOfGatewayToAdd and cmd.macOfGatewayToAdd and cmd.gatewayToAdd:
            conf_file_path, _, _, option_path, _ = self._make_conf_path(cmd.namespaceNameOfGatewayToAdd)
            option = 'tag:%s,option:router,%s\n' % (cmd.macOfGatewayToAdd.replace(':', ''), cmd.gatewayToAdd)
            with open(option_path, 'a+') as fd:
                fd.write(option)

            self._refresh_dnsmasq(cmd.namespaceNameOfGatewayToAdd, conf_file_path)

        return jsonobject.dumps(ResetGatewayRsp())

    @lock.lock('dnsmasq')
    @kvmagent.replyerror
    def apply_dhcp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        namespace_dhcp = {}
        for d in cmd.dhcp:
            lst = namespace_dhcp.get(d.namespaceName)
            if not lst:
                lst = []
                namespace_dhcp[d.namespaceName] = lst
            lst.append(d)

        self.do_apply_dhcp(namespace_dhcp, cmd.rebuild)
        rsp = ApplyDhcpRsp()
        return jsonobject.dumps(rsp)


    @lock.lock('dnsmasq')
    @kvmagent.replyerror
    def batch_apply_dhcp(self, req):
        started_at = time.time()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        namespace_dhcp = {}
        dhcp_count = 0

        for info in cmd.dhcpInfos:
            for d in info.dhcp:
                dhcp_count += 1
                lst = namespace_dhcp.get(d.namespaceName)
                if not lst:
                    lst = []
                    namespace_dhcp[d.namespaceName] = lst
                lst.append(d)

        self.do_apply_dhcp(namespace_dhcp, cmd.rebuild)
        logger.debug('batch apply dhcp done, dhcp count: %s, namespace count: %s, rebuild: %s, total: %.3fs' % (
            dhcp_count, len(namespace_dhcp), cmd.rebuild, time.time() - started_at))
        rsp = ApplyDhcpRsp()
        return jsonobject.dumps(rsp)

    def do_apply_dhcp(self, namespace_dhcp, rebuild):
        @in_bash
        @lock.file_lock('/run/xtables.lock')
        def _add_ebtable_rules_for_vfnics(dhcpInfo):
            DHCPNAMESPACE = dhcpInfo.namespaceName
            dhcp_ip = bash_o(
                "ip netns exec {{DHCPNAMESPACE}} ip add | grep inet | awk '{print $2}' | awk -F '/' '{print $1}' | head -1")
            dhcp_ip = dhcp_ip.strip()

            if dhcp_ip:
                CHAIN_NAME = getDhcpEbtableChainName(dhcp_ip)
                VF_NIC_MAC = ip.removeZeroFromMacAddress(dhcpInfo.mac)

                if bash_r(get_ebtables_cmd() + ' -L ZSTACK-VF-DHCP > /dev/null 2>&1') != 0:
                    bash_errorout(get_ebtables_cmd() + ' -N ZSTACK-VF-DHCP')

                if bash_r(get_ebtables_cmd() + " -L FORWARD | grep -- '-j ZSTACK-VF-DHCP' > /dev/null") != 0:
                    bash_r(get_ebtables_cmd() + ' -I FORWARD -j ZSTACK-VF-DHCP')

                if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-j RETURN' > /dev/null") != 0:
                    bash_r(get_ebtables_cmd() + ' -A ZSTACK-VF-DHCP -j RETURN')

                if dhcpInfo.ipVersion == 4:
                    if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-p IPv4 -s {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT' > /dev/null") != 0:
                        bash_r(get_ebtables_cmd() + ' -I ZSTACK-VF-DHCP -p IPv4 -s {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')

                    if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-p IPv4 -d {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT' > /dev/null") != 0:
                        bash_r(get_ebtables_cmd() + ' -I ZSTACK-VF-DHCP -p IPv4 -d {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')
                elif dhcpInfo.ipVersion == 6:
                    if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-p IPv6 -s {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT' > /dev/null") != 0:
                        bash_r(get_ebtables_cmd() + ' -I ZSTACK-VF-DHCP -p IPv6 -s {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT')

                    if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-p IPv6 -d {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT' > /dev/null") != 0:
                        bash_r(get_ebtables_cmd() + ' -I ZSTACK-VF-DHCP -p IPv6 -d {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT')
                else:
                    if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-p IPv4 -s {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT' > /dev/null") != 0:
                        bash_r(get_ebtables_cmd() + ' -I ZSTACK-VF-DHCP -p IPv4 -s {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')

                    if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-p IPv4 -d {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT' > /dev/null") != 0:
                        bash_r(get_ebtables_cmd() + ' -I ZSTACK-VF-DHCP -p IPv4 -d {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')

                    if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-p IPv6 -s {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT' > /dev/null") != 0:
                        bash_r(get_ebtables_cmd() + ' -I ZSTACK-VF-DHCP -p IPv6 -s {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT')

                    if bash_r(get_ebtables_cmd() + " -L ZSTACK-VF-DHCP | grep -- '-p IPv6 -d {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT' > /dev/null") != 0:
                        bash_r(get_ebtables_cmd() + ' -I ZSTACK-VF-DHCP -p IPv6 -d {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT')

        @in_bash
        def apply(dhcp):
            input_count = len(dhcp)
            render_records, config_keys = self._normalize_dhcp_records(dhcp)
            bridge_name = dhcp[0].bridgeName
            namespace_name = dhcp[0].namespaceName
            conf_file_path, dhcp_path, dns_path, option_path, log_path = self._make_conf_path(namespace_name)

            conf_file = '''\
domain-needed
bogus-priv
no-hosts
addn-hosts={{dns}}
dhcp-option=vendor:MSFT,2,1i
dhcp-lease-max=65535
dhcp-hostsfile={{dhcp}}
dhcp-optsfile={{option}}
log-facility={{log}}
interface={{iface_name}}
except-interface=lo
bind-interfaces
leasefile-ro
{% for g in gateways -%}
dhcp-range={{g}}
{% endfor -%}
'''

            br_num = shell.call("ip netns list-id | grep -w %s | awk '{print $2}'" % namespace_name)
            br_num = br_num.strip()
            if not br_num:
                raise Exception('cannot find the ID for the namespace[%s]' % namespace_name)

            dinfo4 = None
            dinfo6 = None
            for d in render_records:
                if d.ipVersion == 4:
                    dinfo4 = d
                elif d.ipVersion == 6:
                    dinfo6 = d
                elif d.ipVersion == 46:
                    dinfo4 = d
                    # for dual stack nic with slaac ipv6, ipVersion is 46, but no ip6 address
                    if d.ip6 is not None:
                        dinfo6 = d

            ranges = []
            if dinfo4 is not None:
                ranges.append("%s,static" % dinfo4.gateway)
            if dinfo6 is not None:
                dhcp_range = '%s,%s,static,%s,24h' % (dinfo6.firstIp, dinfo6.endIp, dinfo6.prefixLength)
                ra_param = '\nenable-ra' \
                           '\nra-param=inner%s,0,0' % br_num
                ranges.append(dhcp_range + ra_param if dinfo6.enableRa else dhcp_range)

            tmpt = Template(conf_file)
            conf_file = tmpt.render({
                'dns': dns_path,
                'dhcp': dhcp_path,
                'option': option_path,
                'log': log_path,
                'iface_name': 'inner%s' % br_num,
                'gateways': ranges
            })

            restart_dnsmasq = False
            refresh_dnsmasq = False
            if not os.path.exists(conf_file_path) or rebuild:
                restart_dnsmasq = write_file_if_changed(conf_file_path, conf_file)
            else:
                with open(conf_file_path, 'r') as fd:
                    c = fd.read()

                if c != conf_file:
                    logger.debug('dnsmasq configure file for bridge[%s] changed, restart it' % bridge_name)
                    restart_dnsmasq = True
                    write_file_if_changed(conf_file_path, conf_file)
                    logger.debug('wrote dnsmasq configure file for bridge[%s]\n%s' % (bridge_name, conf_file))

            info = []
            for d in render_records:
                dhcp_info = {'tag': d.mac.replace(':', '')}
                dhcp_info.update(d.__dict__)
                dhcp_info['dns'] = ','.join(d.dns)
                if d.dns6 is not None:
                    dnslist = ['[%s]' % dns for dns in d.dns6]
                    dhcp_info['dns6'] = ",".join(dnslist)
                dhcp_info['dhcp6Duid'] = make_dhcpv6_duid_uuid(getattr(d, 'vmUuid', None))
                routes = []
                # add classless-static-route (option 121) for gateway:
                if d.isDefaultL3Network:
                    routes.append(','.join(['0.0.0.0/0', d.gateway]))
                for route in d.hostRoutes:
                    routes.append(','.join([route.prefix, route.nexthop]))
                dhcp_info['routes'] = ','.join(routes)
                dhcp_info['vmMultiGateway'] = d.vmMultiGateway
                address = ""
                if d.ip6 is not None:
                    address="[%s],%s" % (d.ip6, d.ip)
                else:
                    address = "%s" % (d.ip)
                dhcp_info['address'] = address
                info.append(dhcp_info)

            dhcp_conf = '''\
{% for d in dhcp -%}
{% if d.isDefaultL3Network -%}
{{d.mac}},set:{{d.tag}},{{d.address}},{{d.hostname}},infinite
{% if d.ip6 and d.dhcp6Duid -%}
id:{{d.dhcp6Duid}},set:{{d.tag}},[{{d.ip6}}],{{d.hostname}},infinite
{% endif -%}
{% else -%}
{{d.mac}},set:{{d.tag}},{{d.address}},infinite
{% if d.ip6 and d.dhcp6Duid -%}
id:{{d.dhcp6Duid}},set:{{d.tag}},[{{d.ip6}}],infinite
{% endif -%}
{% endif -%}
{% endfor -%}
'''

            tmpt = Template(dhcp_conf)
            dhcp_conf = tmpt.render({'dhcp': info})

            option_conf = '''\
{% for o in options -%}
{% if o.isDefaultL3Network -%}
{% if o.gateway -%}
tag:{{o.tag}},option:router,{{o.gateway}}
{% endif -%}
{% if o.dns -%}
tag:{{o.tag}},option:dns-server,{{o.dns}}
{% endif -%}
{% if o.dns6 -%}
tag:{{o.tag}},option6:dns-server,{{o.dns6}}
{% endif -%}
{% if o.dnsDomain -%}
tag:{{o.tag}},option:domain-name,{{o.dnsDomain}}
{% endif -%}
{% if o.routes -%}
tag:{{o.tag}},option:classless-static-route,{{o.routes}}
tag:{{o.tag}},option:microsoft-249,{{o.routes}}
{% endif -%}
{% else -%}
tag:{{o.tag}},3
tag:{{o.tag}},6
{% if o.vmMultiGateway -%}
{% if o.gateway -%}
tag:{{o.tag}},option:router,{{o.gateway}}
{% endif -%}
{% endif -%}
{% endif -%}
tag:{{o.tag}},option:netmask,{{o.netmask}}
{% if o.mtu -%}
tag:{{o.tag}},option:mtu,{{o.mtu}}
{% endif -%}
{% endfor -%}
    '''
            tmpt = Template(option_conf)
            option_conf = tmpt.render({'options': info})

            hostname_conf = '''\
{% for h in hostnames -%}
{% if h.isDefaultL3Network and h.hostname -%}
{{h.ip}} {{h.hostname}}
{% if h.ip6 -%}
{{h.ip6}} {{h.hostname}}
{% endif -%}
{% endif -%}
{% endfor -%}
    '''
            tmpt = Template(hostname_conf)
            hostname_conf = tmpt.render({'hostnames': info})

            for d in dhcp:
                if d.nicType == "VF":
                    _add_ebtable_rules_for_vfnics(d)

            stats = self._batch_update_configurations(
                dhcp_path=dhcp_path,
                dns_path=dns_path,
                option_path=option_path,
                keys=config_keys,
                dhcp_conf=dhcp_conf,
                dns_conf=hostname_conf,
                option_conf=option_conf,
                rebuild=rebuild,
            )
            if rebuild:
                refresh_dnsmasq = stats['changed_files'] > 0 or refresh_dnsmasq
            else:
                refresh_dnsmasq = True

            self._sync_dnsmasq(namespace_name, conf_file_path, restart_dnsmasq, refresh_dnsmasq)
            logger.debug(
                'batch updated dnsmasq configs, operation: apply, namespace: %s, '
                'input count: %s, deduplicated count: %s, removed dhcp: %s, '
                'removed option: %s, removed dns: %s, changed files: %s' % (
                    namespace_name, input_count, len(render_records),
                    stats['removed_dhcp'], stats['removed_option'],
                    stats['removed_dns'], stats['changed_files']
                )
            )

        @in_bash
        def applyv6(dhcp):
            input_count = len(dhcp)
            render_records, config_keys = self._normalize_dhcp_records(dhcp)
            bridge_name = dhcp[0].bridgeName
            namespace_name = dhcp[0].namespaceName
            dnsDomain = dhcp[0].dnsDomain
            conf_file_path, dhcp_path, dns_path, option_path, log_path = self._make_conf_path(namespace_name)

            conf_file = '''\
domain-needed
bogus-priv
no-hosts
addn-hosts={{dns}}
dhcp-option=vendor:MSFT,2,1i
dhcp-lease-max=65535
dhcp-hostsfile={{dhcp}}
dhcp-optsfile={{option}}
log-facility={{log}}
interface={{iface_name}}
except-interface=lo
bind-interfaces
leasefile-ro
dhcp-range={{range}}
'''

            br_num = shell.call("ip netns list-id | grep -w %s | awk '{print $2}'" % namespace_name)
            br_num = br_num.strip()
            if not br_num:
                raise Exception('cannot find the ID for the namespace[%s]' % namespace_name)

            range_info = render_records[0]
            dhcp_range = '%s,%s,static,%s,24h' % (
                range_info.firstIp,
                range_info.endIp,
                range_info.prefixLength,
            )
            ra_param = '\nenable-ra' \
                       '\nra-param=inner%s,0,0' % br_num

            tmpt = Template(conf_file)
            conf_file = tmpt.render({
                'dns': dns_path,
                'dhcp': dhcp_path,
                'option': option_path,
                'log': log_path,
                'iface_name': 'inner%s' % br_num,
                'range': dhcp_range + ra_param if range_info.enableRa else dhcp_range,
            })

            restart_dnsmasq = False
            refresh_dnsmasq = False
            if not os.path.exists(conf_file_path) or rebuild:
                restart_dnsmasq = write_file_if_changed(conf_file_path, conf_file)
            else:
                with open(conf_file_path, 'r') as fd:
                    c = fd.read()

                if c != conf_file:
                    logger.debug('dnsmasq configure file for bridge[%s] changed, restart it' % bridge_name)
                    restart_dnsmasq = True
                    write_file_if_changed(conf_file_path, conf_file)
                    logger.debug('wrote dnsmasq configure file for bridge[%s]\n%s' % (bridge_name, conf_file))

            info = []
            for d in render_records:
                dhcp_info = {'tag': d.mac.replace(':', '')}
                dhcp_info.update(d.__dict__)
                if d.dns6 is not None:
                    dnslist = ['[%s]' % dns for dns in d.dns6]
                    dhcp_info['dnslist'] = ",".join(dnslist)
                if d.dnsDomain is not None:
                    dhcp_info['domainList'] = ",".join(d.dnsDomain)
                dhcp_info['dhcp6Duid'] = make_dhcpv6_duid_uuid(getattr(d, 'vmUuid', None))
                info.append(dhcp_info)

            dhcp_conf = '''\
{% for d in dhcp -%}
{{d.mac}},set:{{d.tag}},[{{d.ip6}}],{{d.hostname}},infinite
{% if d.dhcp6Duid -%}
id:{{d.dhcp6Duid}},set:{{d.tag}},[{{d.ip6}}],{{d.hostname}},infinite
{% endif -%}
{% endfor -%}
'''

            tmpt = Template(dhcp_conf)
            dhcp_conf = tmpt.render({'dhcp': info})

            # for dhcpv6,  if dns-server is not provided, dnsmasq will use dhcp server as dns-server
            option_conf = '''\
{% for o in options -%}
{% if o.dnslist -%}
tag:{{o.tag}},option6:dns-server,{{o.dnslist}}
{% endif -%}
{% if o.domainList -%}
tag:{{o.tag}},option6:domain-search,{{o.domainList}}
{% endif -%}
{% endfor -%}
'''
            tmpt = Template(option_conf)
            option_conf = tmpt.render({'options': info})

            hostname_conf = '''\
{% for h in hostnames -%}
{% if h.isDefaultL3Network and h.hostname -%}
{{h.ip6}} {{h.hostname}}
{% endif -%}
{% endfor -%}
'''
            tmpt = Template(hostname_conf)
            hostname_conf = tmpt.render({'hostnames': info})

            for d in dhcp:
                if d.nicType == "VF":
                    _add_ebtable_rules_for_vfnics(d)

            stats = self._batch_update_configurations(
                dhcp_path=dhcp_path,
                dns_path=dns_path,
                option_path=option_path,
                keys=config_keys,
                dhcp_conf=dhcp_conf,
                dns_conf=hostname_conf,
                option_conf=option_conf,
                rebuild=rebuild,
            )
            if rebuild:
                refresh_dnsmasq = stats['changed_files'] > 0 or refresh_dnsmasq
            else:
                refresh_dnsmasq = True

            self._sync_dnsmasq(namespace_name, conf_file_path, restart_dnsmasq, refresh_dnsmasq)
            logger.debug(
                'batch updated dnsmasq configs, operation: apply, namespace: %s, '
                'input count: %s, deduplicated count: %s, removed dhcp: %s, '
                'removed option: %s, removed dns: %s, changed files: %s' % (
                    namespace_name, input_count, len(render_records),
                    stats['removed_dhcp'], stats['removed_option'],
                    stats['removed_dns'], stats['changed_files']
                )
            )

        for k, v in namespace_dhcp.items():
            if v[0].ipVersion == 4 or v[0].ipVersion == 46:
                apply(v)
            else:
                applyv6(v)

    def _restart_dnsmasq(self, ns_name, conf_file_path):
        pid = linux.find_process_by_cmdline([conf_file_path])
        if pid:
            linux.kill_process(pid)

        NS_NAME = ns_name
        CONF_FILE = conf_file_path
        #DNSMASQ = bash_errorout('which dnsmasq').strip()
        DNSMASQ_BIN = "/usr/local/zstack/dnsmasq"
        bash_errorout('ip netns exec {{NS_NAME}} {{DNSMASQ_BIN}} --conf-file={{CONF_FILE}} -K')

        def check(_):
            pid = linux.find_process_by_cmdline([conf_file_path])
            return pid is not None

        if not linux.wait_callback_success(check, None, 5):
            raise Exception('dnsmasq[conf-file:%s] is not running after being started %s seconds' % (conf_file_path, 5))

    def _sync_dnsmasq(self, ns_name, conf_file_path, restart_required, refresh_required):
        if restart_required:
            self._restart_dnsmasq(ns_name, conf_file_path)
            return

        pid = linux.find_process_by_cmdline([conf_file_path])
        if not pid:
            self._restart_dnsmasq(ns_name, conf_file_path)
            return

        if refresh_required:
            self._refresh_dnsmasq(ns_name, conf_file_path)

    def _refresh_dnsmasq(self, ns_name, conf_file_path):
        pid = linux.find_process_by_cmdline([conf_file_path])
        if not pid:
            self._restart_dnsmasq(ns_name, conf_file_path)
            return

        if self.signal_count > 50:
            self._restart_dnsmasq(ns_name, conf_file_path)
            self.signal_count = 0
            return

        shell.call('kill -1 %s' % pid)
        self.signal_count += 1

    @staticmethod
    def _normalize_mac_address(mac):
        return mac.strip().lower() if mac else None

    @staticmethod
    def _normalize_dhcp_tag(mac):
        normalized = Mevoco._normalize_mac_address(mac)
        return normalized.replace(':', '') if normalized else None

    @staticmethod
    def _normalize_duid(duid):
        return duid.strip().lower() if duid else None

    @staticmethod
    def _normalize_ip_key(address):
        if not address:
            return None

        candidate = str(address).strip().strip('[]')
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                return family, socket.inet_pton(family, candidate)
            except socket.error:
                pass
        return None

    @staticmethod
    def _normalize_config_lines(lines):
        normalized = [line.rstrip('\r\n') for line in lines if line.strip()]
        return '\n'.join(normalized) + ('\n' if normalized else '')

    @staticmethod
    def _merge_config_content(retained, appended):
        parts = []
        for content in (retained, appended):
            stripped = content.strip()
            if stripped:
                parts.append(stripped)
        return '\n'.join(parts) + ('\n' if parts else '')

    def _normalize_dhcp_records(self, dhcp):
        keys = {
            'macs': set(),
            'tags': set(),
            'ips': set(),
            'duids': set(),
        }

        for record in dhcp:
            mac = self._normalize_mac_address(getattr(record, 'mac', None))
            tag = self._normalize_dhcp_tag(getattr(record, 'mac', None))
            if mac:
                keys['macs'].add(mac)
            if tag:
                keys['tags'].add(tag)

            for field in ('ip', 'ip6'):
                ip_key = self._normalize_ip_key(getattr(record, field, None))
                if ip_key:
                    keys['ips'].add(ip_key)

            duid = self._normalize_duid(getattr(record, 'dhcp6Duid', None))
            if not duid:
                duid = self._normalize_duid(
                    make_dhcpv6_duid_uuid(getattr(record, 'vmUuid', None))
                )
            if duid:
                keys['duids'].add(duid)

        seen = set()
        deduplicated_reversed = []
        for record in reversed(dhcp):
            mac = self._normalize_mac_address(getattr(record, 'mac', None))
            identity = mac if mac else id(record)
            if identity in seen:
                continue
            seen.add(identity)
            deduplicated_reversed.append(record)

        deduplicated_reversed.reverse()
        return deduplicated_reversed, keys

    def _filter_dhcp_config(self, content, keys):
        retained = []
        removed = 0
        stale_ips = set()

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            fields = [field.strip() for field in line.split(',')]
            first = fields[0].lower() if fields else ''
            matched = first in keys['macs']

            if first.startswith('id:') and first[3:] in keys['duids']:
                matched = True

            for field in fields:
                lowered = field.lower()
                if lowered.startswith('set:') and lowered[4:] in keys['tags']:
                    matched = True

                ip_key = self._normalize_ip_key(field)
                if ip_key and ip_key in keys['ips']:
                    matched = True

            if matched:
                removed += 1
                for field in fields:
                    ip_key = self._normalize_ip_key(field)
                    if ip_key:
                        stale_ips.add(ip_key)
            else:
                retained.append(raw_line)

        return self._normalize_config_lines(retained), removed, stale_ips

    def _filter_option_config(self, content, keys):
        retained = []
        removed = 0
        expected_tags = set('tag:%s' % tag for tag in keys['tags'])

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            first = line.split(',', 1)[0].strip().lower()
            if first in expected_tags:
                removed += 1
            else:
                retained.append(raw_line)

        return self._normalize_config_lines(retained), removed

    def _filter_dns_config(self, content, ip_keys):
        retained = []
        removed = 0

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            first = line.split(None, 1)[0]
            if self._normalize_ip_key(first) in ip_keys:
                removed += 1
            else:
                retained.append(raw_line)

        return self._normalize_config_lines(retained), removed

    @staticmethod
    def _replace_config_file(path, content):
        with linux.CrashSafeFileEditor(path) as editor:
            changed = editor.text != content
            editor.text = content
        return changed

    def _batch_update_configurations(self, dhcp_path, dns_path, option_path,
                                     keys, dhcp_conf='', dns_conf='',
                                     option_conf='', rebuild=False):
        with open(dhcp_path, 'r') as fd:
            old_dhcp = fd.read()
        with open(dns_path, 'r') as fd:
            old_dns = fd.read()
        with open(option_path, 'r') as fd:
            old_option = fd.read()

        if rebuild:
            final_dhcp = self._merge_config_content('', dhcp_conf)
            final_dns = self._merge_config_content('', dns_conf)
            final_option = self._merge_config_content('', option_conf)
            removed_dhcp = len([line for line in old_dhcp.splitlines() if line.strip()])
            removed_dns = len([line for line in old_dns.splitlines() if line.strip()])
            removed_option = len([line for line in old_option.splitlines() if line.strip()])
        else:
            retained_dhcp, removed_dhcp, stale_ips = self._filter_dhcp_config(old_dhcp, keys)
            dns_keys = set(keys['ips'])
            dns_keys.update(stale_ips)
            retained_dns, removed_dns = self._filter_dns_config(old_dns, dns_keys)
            retained_option, removed_option = self._filter_option_config(old_option, keys)

            final_dhcp = self._merge_config_content(retained_dhcp, dhcp_conf)
            final_dns = self._merge_config_content(retained_dns, dns_conf)
            final_option = self._merge_config_content(retained_option, option_conf)

        # Keep DHCP last so its stale addresses remain discoverable after a partial failure.
        changed_files = 0
        changed_files += int(self._replace_config_file(dns_path, final_dns))
        changed_files += int(self._replace_config_file(option_path, final_option))
        changed_files += int(self._replace_config_file(dhcp_path, final_dhcp))

        return {
            'removed_dhcp': removed_dhcp,
            'removed_dns': removed_dns,
            'removed_option': removed_option,
            'changed_files': changed_files,
        }

    @lock.lock('dnsmasq')
    @kvmagent.replyerror
    def release_dhcp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        namespace_dhcp = {}
        for d in cmd.dhcp:
            lst = namespace_dhcp.get(d.namespaceName)
            if not lst:
                lst = []
                namespace_dhcp[d.namespaceName] = lst
            lst.append(d)

        @in_bash
        @lock.file_lock('/run/xtables.lock')
        def _remove_ebtable_rules_for_vfnics(dhcpInfo):
            DHCPNAMESPACE = dhcpInfo.namespaceName
            dhcp_ip = bash_o(
                "ip netns exec {{DHCPNAMESPACE}} ip add | grep inet | awk '{print $2}' | awk -F '/' '{print $1}' | head -1")
            dhcp_ip = dhcp_ip.strip()

            if dhcp_ip:
                CHAIN_NAME = getDhcpEbtableChainName(dhcp_ip)
                VF_NIC_MAC = ip.removeZeroFromMacAddress(dhcpInfo.mac)

                if dhcpInfo.ipVersion == 4:
                    bash_r(get_ebtables_cmd() + ' -D ZSTACK-VF-DHCP -p IPv4 -s {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')
                    bash_r(get_ebtables_cmd() + ' -D ZSTACK-VF-DHCP -p IPv4 -d {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')
                elif dhcpInfo.ipVersion == 6:
                    bash_r(get_ebtables_cmd() + ' -D ZSTACK-VF-DHCP -p IPv6 -s {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT')
                    bash_r(get_ebtables_cmd() + ' -D ZSTACK-VF-DHCP -p IPv6 -d {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT')
                else:
                    bash_r(get_ebtables_cmd() + ' -D ZSTACK-VF-DHCP -p IPv4 -s {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')
                    bash_r(get_ebtables_cmd() + ' -D ZSTACK-VF-DHCP -p IPv4 -d {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')
                    bash_r(get_ebtables_cmd() + ' -D ZSTACK-VF-DHCP -p IPv6 -s {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT')
                    bash_r(get_ebtables_cmd() + ' -D ZSTACK-VF-DHCP -p IPv6 -d {{VF_NIC_MAC}} --ip6-proto udp --ip6-sport 546:547 -j ACCEPT')

        @in_bash
        def release(dhcp):
            input_count = len(dhcp)
            render_records, config_keys = self._normalize_dhcp_records(dhcp)

            for d in dhcp:
                if d.nicType == "VF":
                    _remove_ebtable_rules_for_vfnics(d)

            namespace_name = dhcp[0].namespaceName
            conf_file_path, dhcp_path, dns_path, option_path, _ = self._make_conf_path(namespace_name)
            stats = self._batch_update_configurations(
                dhcp_path=dhcp_path,
                dns_path=dns_path,
                option_path=option_path,
                keys=config_keys,
            )
            self._restart_dnsmasq(namespace_name, conf_file_path)
            logger.debug(
                'batch updated dnsmasq configs, operation: release, namespace: %s, '
                'input count: %s, deduplicated count: %s, removed dhcp: %s, '
                'removed option: %s, removed dns: %s, changed files: %s' % (
                    namespace_name, input_count, len(render_records),
                    stats['removed_dhcp'], stats['removed_option'],
                    stats['removed_dns'], stats['changed_files']
                )
            )

        for k, v in namespace_dhcp.items():
            release(v)

        rsp = ReleaseDhcpRsp()
        return jsonobject.dumps(rsp)

    def register_dnsmasq_logRotate(self):
        def dnsmasq_logRotate():
            ret = bash_r("logrotate -vf /etc/logrotate.d/dnsmasq")

            thread.timer(24*3600, dnsmasq_logRotate).start()

        thread.timer(60, dnsmasq_logRotate).start()

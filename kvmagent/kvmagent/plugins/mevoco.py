__author__ = 'frank'

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import iptables
from zstacklib.utils import ebtables
from zstacklib.utils import lock
from zstacklib.utils.bash import *
from zstacklib.utils import ip
import os.path
import re
import email
import tempfile
import cStringIO as c
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
import struct
import socket
import platform

logger = log.get_logger(__name__)
EBTABLES_CMD = ebtables.get_ebtables_cmd()
IPTABLES_CMD = iptables.get_iptables_cmd()
IP6TABLES_CMD = iptables.get_ip6tables_cmd()
HOST_ARCH = platform.machine()

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

def get_phy_dev_from_bridge_name(bridge_name):
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


class UserDataEnv(object):
    def __init__(self, bridge_name, namespace_name):
        self.bridge_name = bridge_name
        self.namespace_name = namespace_name
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
        BR_PHY_DEV = get_phy_dev_from_bridge_name(self.bridge_name)
        OUTER_DEV = "outer%s" % NAMESPACE_ID
        INNER_DEV = "inner%s" % NAMESPACE_ID
        MAX_MTU = linux.MAX_MTU_OF_VNIC

        ret = bash_r('ip netns exec {{NAMESPACE_NAME}} ip link show')
        if ret != 0:
            bash_errorout('ip netns add {{NAMESPACE_NAME}}')
            bash_errorout('ip netns set {{NAMESPACE_NAME}} {{NAMESPACE_ID}}')

        # in case the namespace deleted and the orphan outer link leaves in the system,
        # deleting the orphan link and recreate it
        ret = bash_r('ip netns exec {{NAMESPACE_NAME}} ip link show {{INNER_DEV}} > /dev/null')
        if ret != 0:
            bash_r('ip link del {{OUTER_DEV}} &> /dev/null')

        if not linux.is_network_device_existing(OUTER_DEV):
            bash_errorout('ip link add {{OUTER_DEV}} type veth peer name {{INNER_DEV}}')
            bash_errorout('ip link set mtu {{MAX_MTU}} dev {{INNER_DEV}}')
            bash_errorout('ip link set mtu {{MAX_MTU}} dev {{OUTER_DEV}}')

        bash_errorout('ip link set {{OUTER_DEV}} up')

        ret = bash_r('brctl show {{BR_NAME}} | grep -w {{OUTER_DEV}} > /dev/null')
        if ret != 0:
            bash_errorout('brctl addif {{BR_NAME}} {{OUTER_DEV}}')

        ret = bash_r('ip netns exec {{NAMESPACE_NAME}} ip link show {{INNER_DEV}} > /dev/null')
        if ret != 0:
            bash_errorout('ip link set {{INNER_DEV}} netns {{NAMESPACE_NAME}}')

        bash_errorout('ip netns exec {{NAMESPACE_NAME}} ip link set {{INNER_DEV}} up')
        self.inner_dev = INNER_DEV
        self.outer_dev = OUTER_DEV

class DhcpEnv(object):
    DHCP6_STATEFUL = "Stateful-DHCP"
    DHCP6_STATELESS = "Stateless-DHCP"

    def __init__(self):
        self.bridge_name = None
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
            ret = bash_r(EBTABLES_CMD + ' -L {{CHAIN_NAME}} > /dev/null 2>&1')
            if ret != 0:
                bash_errorout(EBTABLES_CMD + ' -N {{CHAIN_NAME}}')

            ret = bash_r(EBTABLES_CMD + ' -F {{CHAIN_NAME}} > /dev/null 2>&1')

            ret = bash_r(EBTABLES_CMD + ' -L FORWARD | grep -- "-j {{CHAIN_NAME}}" > /dev/null')
            if ret != 0:
                bash_errorout(EBTABLES_CMD + ' -A FORWARD -j {{CHAIN_NAME}}')

            ret = bash_r(
                EBTABLES_CMD + ' -L {{CHAIN_NAME}} | grep -- "-p ARP -o {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP" > /dev/null')
            if ret != 0:
                bash_errorout(
                    EBTABLES_CMD + ' -I {{CHAIN_NAME}} -p ARP -o {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP')

            ret = bash_r(
                EBTABLES_CMD + ' -L {{CHAIN_NAME}} | grep -- "-p ARP -i {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP" > /dev/null')
            if ret != 0:
                bash_errorout(
                    EBTABLES_CMD + ' -I {{CHAIN_NAME}} -p ARP -i {{BR_PHY_DEV}} --arp-ip-dst {{DHCP_IP}} -j DROP')

            ret = bash_r(
                EBTABLES_CMD + ' -L {{CHAIN_NAME}} | grep -- "-p ARP -o {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP" > /dev/null')
            if ret != 0:
                bash_errorout(
                    EBTABLES_CMD + ' -I {{CHAIN_NAME}} -p ARP -o {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP')

            ret = bash_r(
                EBTABLES_CMD + ' -L {{CHAIN_NAME}} | grep -- "-p ARP -i {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP" > /dev/null')
            if ret != 0:
                bash_errorout(
                    EBTABLES_CMD + ' -I {{CHAIN_NAME}} -p ARP -i {{BR_PHY_DEV}} --arp-ip-src {{DHCP_IP}} -j DROP')

            ret = bash_r(
                EBTABLES_CMD + ' -L {{CHAIN_NAME}} | grep -- "-p IPv4 -o {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP" > /dev/null')
            if ret != 0:
                bash_errorout(
                    EBTABLES_CMD + ' -I {{CHAIN_NAME}} -p IPv4 -o {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP')

            ret = bash_r(
                EBTABLES_CMD + ' -L {{CHAIN_NAME}} | grep -- "-p IPv4 -i {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP" > /dev/null')
            if ret != 0:
                bash_errorout(
                    EBTABLES_CMD + ' -I {{CHAIN_NAME}} -p IPv4 -i {{BR_PHY_DEV}} --ip-proto udp --ip-sport 67:68 -j DROP')

            ret = bash_r("ebtables-save | grep -- '-A {{CHAIN_NAME}} -j RETURN'")
            if ret != 0:
                bash_errorout(EBTABLES_CMD + ' -A {{CHAIN_NAME}} -j RETURN')

            # Note(WeiW): fix dhcp checksum, see more at #982
            if HOST_ARCH == 'mips64el':
                return
            ret = bash_r("iptables-save | grep -- '-p udp -m udp --dport 68 -j CHECKSUM --checksum-fill'")
            if ret != 0:
                bash_errorout(
                    '%s -t mangle -A POSTROUTING -p udp -m udp --dport 68 -j CHECKSUM --checksum-fill' % IPTABLES_CMD)

        def _add_ebtables_rule6(rule):
            ret = bash_r(
                EBTABLES_CMD + ' -L {{CHAIN_NAME}} | grep -- {{rule}} > /dev/null')
            if ret != 0:
                bash_errorout(
                    EBTABLES_CMD + ' -I {{CHAIN_NAME}} {{rule}}')

        def _prepare_dhcp6_iptables(dualStack=True):
            serverip = ip.Ipv6Address(DHCP6_IP)
            ns_multicast_address = serverip.get_solicited_node_multicast_address() + "/ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff"

            if not dualStack:
                ret = bash_r(EBTABLES_CMD + ' -L {{CHAIN_NAME}} > /dev/null 2>&1')
                if ret != 0:
                    bash_errorout(EBTABLES_CMD + ' -N {{CHAIN_NAME}}')

                ret = bash_r(EBTABLES_CMD + ' -F {{CHAIN_NAME}} > /dev/null 2>&1')

                ret = bash_r(EBTABLES_CMD + ' -L FORWARD | grep -- "-j {{CHAIN_NAME}}" > /dev/null')
                if ret != 0:
                    bash_errorout(EBTABLES_CMD + ' -I FORWARD -j {{CHAIN_NAME}}')

            ns_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
            _add_ebtables_rule6(ns_rule_o)

            na_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
            _add_ebtables_rule6(na_rule_o)

            ns_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-solicitation -j DROP"
            _add_ebtables_rule6(ns_rule_i)

            na_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-dst {{ns_multicast_address}} --ip6-proto ipv6-icmp --ip6-icmp-type neighbour-advertisement -j DROP"
            _add_ebtables_rule6(na_rule_i)

            # prevent ns for dhcp server from upstream network
            dhcpv6_rule_o = "-p IPv6 -o {{BR_PHY_DEV}} --ip6-proto udp --ip6-sport 546:547 -j DROP"
            _add_ebtables_rule6(dhcpv6_rule_o)

            dhcpv6_rule_i = "-p IPv6 -i {{BR_PHY_DEV}} --ip6-proto udp --ip6-sport 546:547 -j DROP"
            _add_ebtables_rule6(dhcpv6_rule_i)

            ret = bash_r("ebtables-save | grep -- '-A {{CHAIN_NAME}} -j RETURN'")
            if ret != 0:
                bash_errorout(EBTABLES_CMD + ' -A {{CHAIN_NAME}} -j RETURN')

            # Note(WeiW): fix dhcp checksum, see more at #982
            ret = bash_r("ip6tables-save | grep -- '-p udp -m udp --dport 546 -j CHECKSUM --checksum-fill'")
            if ret != 0:
                bash_errorout(
                    '%s -t mangle -A POSTROUTING -p udp -m udp --dport 546 -j CHECKSUM --checksum-fill' % IP6TABLES_CMD)

        NAMESPACE_NAME = self.namespace_name
        NAMESPACE_ID = ip.get_namespace_id(self.namespace_name)

        logger.debug('use id[%s] for the namespace[%s]' % (NAMESPACE_ID, NAMESPACE_NAME))

        BR_NAME = self.bridge_name
        DHCP_IP = self.dhcp_server_ip
        DHCP6_IP = self.dhcp_server6_ip
        DHCP_NETMASK = self.dhcp_netmask
        PREFIX_LEN = None
        if DHCP_NETMASK is not None:
            PREFIX_LEN = linux.netmask_to_cidr(DHCP_NETMASK)
        PREFIX6_LEN = self.prefixLen
        ADDRESS_MODE = self.addressMode
        BR_PHY_DEV = get_phy_dev_from_bridge_name(self.bridge_name)
        OUTER_DEV = "outer%s" % NAMESPACE_ID
        INNER_DEV = "inner%s" % NAMESPACE_ID
        if DHCP_IP is not None:
            CHAIN_NAME = "ZSTACK-%s" % DHCP_IP
        elif DHCP6_IP is not None:
            CHAIN_NAME = "ZSTACK-DHCP-%s" % DHCP6_IP[0:9]

        MAX_MTU = linux.MAX_MTU_OF_VNIC

        ret = bash_r('ip netns exec {{NAMESPACE_NAME}} ip link show')
        if ret != 0:
            bash_errorout('ip netns add {{NAMESPACE_NAME}}')
            bash_errorout('ip netns set {{NAMESPACE_NAME}} {{NAMESPACE_ID}}')

        # in case the namespace deleted and the orphan outer link leaves in the system,
        # deleting the orphan link and recreate it
        ret = bash_r('ip netns exec {{NAMESPACE_NAME}} ip link show {{INNER_DEV}} > /dev/null')
        if ret != 0:
            bash_r('ip link del {{OUTER_DEV}} &> /dev/null')

        if not linux.is_network_device_existing(OUTER_DEV):
            bash_errorout('ip link add {{OUTER_DEV}} type veth peer name {{INNER_DEV}}')
            bash_errorout('ip link set mtu {{MAX_MTU}} dev {{INNER_DEV}}')
            bash_errorout('ip link set mtu {{MAX_MTU}} dev {{OUTER_DEV}}')

        bash_errorout('ip link set {{OUTER_DEV}} up')

        ret = bash_r('brctl show {{BR_NAME}} | grep -w {{OUTER_DEV}} > /dev/null')
        if ret != 0:
            bash_errorout('brctl addif {{BR_NAME}} {{OUTER_DEV}}')

        ret = bash_r('ip netns exec {{NAMESPACE_NAME}} ip link show {{INNER_DEV}} > /dev/null')
        if ret != 0:
            bash_errorout('ip link set {{INNER_DEV}} netns {{NAMESPACE_NAME}}')

        ret = bash_r('ip netns exec {{NAMESPACE_NAME}} ip addr show {{INNER_DEV}} | grep -w {{DHCP_IP}} > /dev/null')
        ret6 = bash_r('ip netns exec {{NAMESPACE_NAME}} ip addr show {{INNER_DEV}} | grep -w {{DHCP6_IP}} > /dev/null')
        if (ret != 0 and PREFIX_LEN != None) or (ret6 != 0 and PREFIX6_LEN != None):
            bash_errorout('ip netns exec {{NAMESPACE_NAME}} ip addr flush dev {{INNER_DEV}}')
            if DHCP_IP is not None:
                bash_errorout('ip netns exec {{NAMESPACE_NAME}} ip addr add {{DHCP_IP}}/{{PREFIX_LEN}} dev {{INNER_DEV}}')
            if DHCP6_IP is not None:
                bash_errorout('ip netns exec {{NAMESPACE_NAME}} ip addr add {{DHCP6_IP}}/{{PREFIX6_LEN}} dev {{INNER_DEV}}')

        if DHCP6_IP is not None:
            mac = bash_o("ip netns exec {{NAMESPACE_NAME}} ip link show {{INNER_DEV}} | grep -w 'link/ether' | awk '{print $2}'")
            link_local = ip.get_link_local_address(mac)
            ret = bash_r('ip netns exec {{NAMESPACE_NAME}} ip add | grep -w {{link_local}} > /dev/null')
            if ret != 0:
                bash_errorout('ip netns exec {{NAMESPACE_NAME}} ip addr add {{link_local}}/64 dev {{INNER_DEV}}')

        bash_errorout('ip netns exec {{NAMESPACE_NAME}} ip link set {{INNER_DEV}} up')

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
            PHY_DEV = PHY_DEV.strip(' \t\n\r')

            # get mac address of inner dev
            r, INNER_MAC, e = bash_roe("ip netns exec {{NAMESPACE_NAME}} ip link show {{INNER_DEV}} | grep -w ether | awk '{print $2}'")
            if r != 0:
                logger.error("cannot get mac address of " + INNER_DEV)
                return
            INNER_MAC = INNER_MAC.strip(' \t\n\r')

            # add bridge fdb entry for inner dev
            if not linux.bridge_fdb_has_self_rule(INNER_MAC, PHY_DEV):
                bash_r('bridge fdb add {{INNER_MAC}} dev {{PHY_DEV}}')

        if DHCP_IP is not None:
            _prepare_dhcp4_iptables()
            _add_bridge_fdb_entry_for_inner_dev()

        if DHCP6_IP is not None:
            _prepare_dhcp6_iptables(DHCP_IP is not None)


class Mevoco(kvmagent.KvmAgent):
    APPLY_DHCP_PATH = "/flatnetworkprovider/dhcp/apply"
    PREPARE_DHCP_PATH = "/flatnetworkprovider/dhcp/prepare"
    RELEASE_DHCP_PATH = "/flatnetworkprovider/dhcp/release"
    DHCP_CONNECT_PATH = "/flatnetworkprovider/dhcp/connect"
    RESET_DEFAULT_GATEWAY_PATH = "/flatnetworkprovider/dhcp/resetDefaultGateway"
    APPLY_USER_DATA = "/flatnetworkprovider/userdata/apply"
    RELEASE_USER_DATA = "/flatnetworkprovider/userdata/release"
    BATCH_APPLY_USER_DATA = "/flatnetworkprovider/userdata/batchapply"
    DHCP_DELETE_NAMESPACE_PATH = "/flatnetworkprovider/dhcp/deletenamespace"
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
        http_server.register_async_uri(self.BATCH_APPLY_USER_DATA, self.batch_apply_userdata)
        http_server.register_async_uri(self.RELEASE_DHCP_PATH, self.release_dhcp)
        http_server.register_async_uri(self.PREPARE_DHCP_PATH, self.prepare_dhcp)
        http_server.register_async_uri(self.APPLY_USER_DATA, self.apply_userdata)
        http_server.register_async_uri(self.RELEASE_USER_DATA, self.release_userdata)
        http_server.register_async_uri(self.RESET_DEFAULT_GATEWAY_PATH, self.reset_default_gateway)
        http_server.register_async_uri(self.DHCP_DELETE_NAMESPACE_PATH, self.delete_dhcp_namespace)
        http_server.register_async_uri(self.CLEANUP_USER_DATA, self.cleanup_userdata)
        http_server.register_async_uri(self.SET_DNS_FORWARD_PATH, self.setup_dns_forward)
        http_server.register_async_uri(self.REMOVE_DNS_FORWARD_PATH, self.remove_dns_forward)

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
    def _delete_dhcp6(self, namspace):
        items = namspace.split('_')
        l3_uuid = items[-1]
        DHCP6_CHAIN_NAME = "ZSTACK-DHCP6-%s" % l3_uuid[0:9]

        o = bash_o("ebtables-save | grep {{DHCP6_CHAIN_NAME}} | grep -- -A")
        o = o.strip(" \t\r\n")
        if o:
            cmds = []
            for l in o.split("\n"):
                cmds.append(EBTABLES_CMD + " %s" % l.replace("-A", "-D"))

            bash_r("\n".join(cmds))

        ret = bash_r("ebtables-save | grep '\-A {{DHCP6_CHAIN_NAME}} -j RETURN'")
        if ret != 0:
            bash_r(EBTABLES_CMD + ' -D {{DHCP6_CHAIN_NAME}} -j RETURN')

        ret = bash_r("ebtables-save | grep '\-A FORWARD -j {{DHCP6_CHAIN_NAME}}'")
        if ret != 0:
            bash_r(EBTABLES_CMD + ' -D FORWARD -j {{DHCP6_CHAIN_NAME}}')
            bash_r(EBTABLES_CMD + ' -X {{DHCP6_CHAIN_NAME}}')

        bash_r("ps aux | grep -v grep | grep -w dnsmasq | grep -w %s | awk '{printf $2}' | xargs -r kill -9" % namspace)
        bash_r(
            "ip netns | grep -w %s | grep -v grep | awk '{print $1}' | xargs -r ip netns del %s" % (namspace, namspace))

    @in_bash
    def _delete_dhcp4(self, namspace):
        dhcp_ip = bash_o("ip netns exec {{namspace}} ip add | grep inet | awk '{print $2}' | awk -F '/' '{print $1}' | head -1")
        dhcp_ip = dhcp_ip.strip(" \t\n\r")

        if dhcp_ip:
            CHAIN_NAME = "ZSTACK-%s" % dhcp_ip

            o = bash_o("ebtables-save | grep {{CHAIN_NAME}} | grep -- -A")
            o = o.strip(" \t\r\n")
            if o:
                cmds = []
                for l in o.split("\n"):
                    cmds.append(EBTABLES_CMD + " %s" % l.replace("-A", "-D"))

                bash_r("\n".join(cmds))

            ret = bash_r("ebtables-save | grep '\-A {{CHAIN_NAME}} -j RETURN'")
            if ret != 0:
                bash_r(EBTABLES_CMD + ' -D {{CHAIN_NAME}} -j RETURN')

            ret = bash_r("ebtables-save | grep '\-A FORWARD -j {{CHAIN_NAME}}'")
            if ret != 0:
                bash_r(EBTABLES_CMD + ' -D FORWARD -j {{CHAIN_NAME}}')
                bash_r(EBTABLES_CMD + ' -X {{CHAIN_NAME}}')

        bash_r("ps aux | grep -v grep | grep -w dnsmasq | grep -w %s | awk '{printf $2}' | xargs -r kill -9" % namspace)
        bash_r(
            "ip netns | grep -w %s | grep -v grep | awk '{print $1}' | xargs -r ip netns del %s" % (namspace, namspace))

    @kvmagent.replyerror
    @in_bash
    def delete_dhcp_namespace(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        # don't care about ip4, ipv6 because namespaces are different for l3 networks
        self._delete_dhcp4(cmd.namespaceName)
        self._delete_dhcp6(cmd.namespaceName)

        return jsonobject.dumps(DeleteNamespaceRsp())

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
                self.raw_text = bash_o("ebtables-save").strip(" \t\r\n").splitlines()
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
                    if len(list(filter(lambda x: '-A %s ' % x in line, result))) < 1:
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
                    if len(list(filter(lambda x: x in line, related_chains))) > 0:
                        result.append(line)

                default_rules = EbtablesRules.default_rules[table]
                r = default_rules.splitlines()
                r.extend(result)
                return r

            def get_related_rules_re(self, patterns):
                # type: (dict[str, list]) -> list[str]
                result = []
                if not set(patterns.keys()).issubset(EbtablesRules.default_tables):
                    raise Exception('invalid parameter table %s' % patterns.keys())

                for key, value in patterns.items():
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
        patterns={"nat":["libvirt","(^z|^s)[0-9]*_"], "filter":["(^z|^s)[0-9]*_"]}
        restore_data = "\n".join(ebtables_obj.get_related_rules_re(patterns)) + "\n"
        logger.debug("restore ebtables: %s" % restore_data)
        with os.fdopen(fd, 'w') as fs:
            fs.write(restore_data)
        bash_o("ebtables-restore < %s" % path)
        os.remove(path)
        logger.debug("clean ebtables successfully")

    @kvmagent.replyerror
    def connect(self, req):
        #shell.call(EBTABLES_CMD + ' -F')
        # shell.call(EBTABLES_CMD + ' -t nat -F')
        # this is workaround, for anti-spoofing & distributed virtual routing feature, there is no good way to proccess this reconnect-host case,
        # it's just keep the ebtables rules from libvirt & zsn and remove others when reconnect hosts
        self.restore_ebtables_chain_except_kvmagent()
        return jsonobject.dumps(ConnectRsp())

    @kvmagent.replyerror
    @in_bash
    def cleanup_userdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        BR_NAME = cmd.bridgeName
        # max length of ebtables chain name is 31
        if (len(BR_NAME) <= 12):
            CHAIN_NAME = "USERDATA-%s-%s" % (BR_NAME, cmd.l3NetworkUuid[0:8])
        else:
            CHAIN_NAME = "USERDATA-%s-%s" % (BR_NAME[len(BR_NAME) - 12: len(BR_NAME)], cmd.l3NetworkUuid[0:8])

        o = bash_o("ebtables-save | grep {{CHAIN_NAME}} | grep -- -A")
        o = o.strip(" \t\r\n")
        if o:
            cmds = []
            for l in o.split("\n"):
                # we don't distinguish if the rule is in filter table or nat table
                # but try both. The wrong table will silently fail
                cmds.append(EBTABLES_CMD + " -t filter %s" % l.replace("-A", "-D"))
                cmds.append(EBTABLES_CMD + " -t nat %s" % l.replace("-A", "-D"))

            cmds.append(EBTABLES_CMD + " -t nat -X %s" % CHAIN_NAME)
            bash_r("\n".join(cmds))

        bash_errorout("pkill -9 -f 'lighttpd.*/userdata/{{BR_NAME}}' || true")

        html_folder = os.path.join(self.USERDATA_ROOT, cmd.namespaceName)
        linux.rm_dir_force(html_folder)

        if self.userData_vms[cmd.l3NetworkUuid] is not None:
            del self.userData_vms[cmd.l3NetworkUuid][:]

        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    def batch_apply_userdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        if cmd.rebuild:
            # kill all lighttpd processes which will be restarted later
            shell.call('pkill -9 lighttpd || true')

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
                    raise Exception('same namespace [%s] but has different dhcpServerIp: %s, %s ' % (
                    u.namespaceName, namespaces[u.namespaceName].bridgeName, u.bridgeName))
                if namespaces[u.namespaceName].port != u.port:
                    raise Exception('same namespace [%s] but has different dhcpServerIp: %s, %s ' % (
                    u.namespaceName, namespaces[u.namespaceName].port, u.port))

        for n in namespaces.values():
            self._apply_userdata_xtables(n)

        for u in cmd.userdata:
            self._apply_userdata_vmdata(u)

        for n in namespaces.values():
            self._apply_userdata_restart_httpd(n)

        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    def apply_userdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._apply_userdata_xtables(cmd.userdata)
        self._apply_userdata_vmdata(cmd.userdata)
        self._apply_userdata_restart_httpd(cmd.userdata)
        return jsonobject.dumps(ApplyUserdataRsp())

    @in_bash
    @lock.file_lock('/run/xtables.lock')
    def _apply_userdata_xtables(self, to):
        def create_default_userdata(http_root):
            root = os.path.join(http_root, "zstack-default")
            meta_root = os.path.join(root, 'meta-data')
            if not os.path.exists(meta_root):
                linux.mkdir(meta_root)

            index_file_path = os.path.join(meta_root, 'index.html')
            with open(index_file_path, 'w') as fd:
                fd.write('')

        def prepare_br_connect_ns(ns, ns_inner_dev, ns_outer_dev):
            bridge_name = self.CONNECT_ALL_NETNS_BR_NAME
            bridge_ip = "%s/%s" % (self.CONNECT_ALL_NETNS_BR_OUTER_IP, self.IP_MASK_BIT)

            if not linux.is_network_device_existing(bridge_name):
                shell.call("brctl addbr %s" % bridge_name)
                shell.call("brctl setfd %s 0" % bridge_name)
                shell.call("brctl stp %s off" % bridge_name)
                shell.call('ip addr add %s dev %s' % (bridge_ip, bridge_name))
                shell.call("ip link set %s up" % bridge_name)

            ret = bash_r('ip addr show %s | grep -w %s > /dev/null' %
                         (bridge_name, bridge_ip))
            if ret != 0:
                bash_errorout('ip addr add %s dev %s' % (bridge_ip, bridge_name))

            #"ip link add %s type veth peer name %s", max length of second parameter is 15 characters
            userdata_br_outer_dev = "ud_" + ns_outer_dev
            userdata_br_inner_dev = "ud_" + ns_inner_dev
            MAX_MTU = linux.MAX_MTU_OF_VNIC

            if not linux.is_network_device_existing(userdata_br_outer_dev):
                bash_errorout('ip link add %s type veth peer name %s' % (userdata_br_outer_dev, userdata_br_inner_dev))
                bash_errorout('ip link set mtu %d dev %s' % (MAX_MTU, userdata_br_outer_dev))
                bash_errorout('ip link set mtu %d dev %s' % (MAX_MTU, userdata_br_inner_dev))

            bash_errorout('ip link set %s up' % userdata_br_outer_dev)

            ret = bash_r('brctl show %s | grep -w %s > /dev/null' % (bridge_name, userdata_br_outer_dev))
            if ret != 0:
                bash_errorout('brctl addif %s %s' % (bridge_name, userdata_br_outer_dev))

            ret = bash_r('ip netns exec %s ip link show %s > /dev/null' % (ns, userdata_br_inner_dev))
            if ret != 0:
                bash_errorout('ip link set %s netns %s' % (userdata_br_inner_dev, ns))

            ns_id = ns_inner_dev[5:]
            if int(ns_id) > 16381:
                # 169.254.64.1/18 The maximum available ip is only 16381 (exclude 169.254.64.1)
                # It is impossible to configure tens of thousands of networks on host
                raise Exception('add ip addr fail, namespace id exceeds limit')
            ip2int = struct.unpack('!L', socket.inet_aton(self.CONNECT_ALL_NETNS_BR_INNER_IP))[0]
            userdata_br_inner_dev_ip = socket.inet_ntoa(struct.pack('!L', ip2int + int(ns_id)))
            ret = bash_r('ip netns exec %s ip addr show %s | grep -w %s > /dev/null' %
                         (ns, userdata_br_inner_dev, userdata_br_inner_dev_ip))
            if ret != 0:
                bash_errorout('ip netns exec %s ip addr add %s/%s dev %s' % (
                    ns, userdata_br_inner_dev_ip, self.IP_MASK_BIT, userdata_br_inner_dev))
            bash_errorout('ip netns exec %s ip link set %s up' % (ns, userdata_br_inner_dev))

        p = UserDataEnv(to.bridgeName, to.namespaceName)
        INNER_DEV = None
        DHCP_IP = None
        NS_NAME = to.namespaceName

        if not to.hasattr("dhcpServerIp"):
            p.prepare()
            INNER_DEV = p.inner_dev
        else:
            DHCP_IP = to.dhcpServerIp
            INNER_DEV = bash_errorout(
                "ip netns exec {{NS_NAME}} ip addr | grep -w {{DHCP_IP}} | awk '{print $NF}'").strip(' \t\r\n')
        if not INNER_DEV:
            p.prepare()
            INNER_DEV = p.inner_dev
        if not INNER_DEV:
            raise Exception('cannot find device for the DHCP IP[%s]' % DHCP_IP)

        outer_dev = p.outer_dev if(p.outer_dev != None) else ("outer" + INNER_DEV[5:])
        prepare_br_connect_ns(NS_NAME, INNER_DEV, outer_dev)

        ret = bash_r('ip netns exec {{NS_NAME}} ip addr | grep 169.254.169.254 > /dev/null')
        if (ret != 0 and INNER_DEV != None):
            bash_errorout('ip netns exec {{NS_NAME}} ip addr add 169.254.169.254 dev {{INNER_DEV}}')

        r, o = bash_ro('ip netns exec {{NS_NAME}} ip r | wc -l')
        if not to.hasattr("dhcpServerIp") and int(o) == 0:
            bash_errorout('ip netns exec {{NS_NAME}} ip r add default dev {{INNER_DEV}}')

        # set ebtables
        BR_NAME = to.bridgeName
        ETH_NAME = get_phy_dev_from_bridge_name(BR_NAME)

        MAC = bash_errorout("ip netns exec {{NS_NAME}} ip link show {{INNER_DEV}} | grep -w ether | awk '{print $2}'").strip(' \t\r\n')
        CHAIN_NAME="USERDATA-%s" % BR_NAME
        # max length of ebtables chain name is 31
        if (len(BR_NAME) <= 12):
            EBCHAIN_NAME = "USERDATA-%s-%s" % (BR_NAME, to.l3NetworkUuid[0:8])
        else:
            EBCHAIN_NAME = "USERDATA-%s-%s" % (BR_NAME[len(BR_NAME) - 12 : len(BR_NAME)], to.l3NetworkUuid[0:8])

        ret = bash_r(EBTABLES_CMD + ' -t nat -L {{EBCHAIN_NAME}} >/dev/null 2>&1')
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -t nat -N {{EBCHAIN_NAME}}')

        if bash_r(EBTABLES_CMD + ' -t nat -L PREROUTING | grep -- "--logical-in {{BR_NAME}} -j {{EBCHAIN_NAME}}"') != 0:
            bash_errorout(EBTABLES_CMD + ' -t nat -I PREROUTING --logical-in {{BR_NAME}} -j {{EBCHAIN_NAME}}')

        # ebtables has a bug that will eliminate 0 in MAC, for example, aa:bb:0c will become aa:bb:c
        cidr = ip.IpAddress(to.vmIp).toCidr(to.netmask)
        RULE = "-p IPv4 --ip-src %s --ip-dst 169.254.169.254 -j dnat --to-dst %s --dnat-target ACCEPT" % (cidr, MAC.replace(":0", ":"))
        ret = bash_r(EBTABLES_CMD + ' -t nat -L {{EBCHAIN_NAME}} | grep -- "{{RULE}}" > /dev/null')
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -t nat -I {{EBCHAIN_NAME}} {{RULE}}')

        ret = bash_r(EBTABLES_CMD + ' -t nat -L {{EBCHAIN_NAME}} | grep -- "--arp-ip-dst %s" > /dev/null' % self.CONNECT_ALL_NETNS_BR_OUTER_IP)
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -t nat -I {{EBCHAIN_NAME}}  -p arp  --arp-ip-dst %s -j DROP' % self.CONNECT_ALL_NETNS_BR_OUTER_IP)

        ret = bash_r(EBTABLES_CMD + ' -t nat -L {{EBCHAIN_NAME}} | grep -- "-j RETURN" > /dev/null')
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -t nat -A {{EBCHAIN_NAME}} -j RETURN')

        ret = bash_r(EBTABLES_CMD + ' -L {{EBCHAIN_NAME}} >/dev/null 2>&1')
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -N {{EBCHAIN_NAME}}')

        ret = bash_r(EBTABLES_CMD + ' -L FORWARD | grep -- "-p ARP --arp-ip-dst 169.254.169.254 -j {{EBCHAIN_NAME}}" > /dev/null')
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -I FORWARD -p ARP --arp-ip-dst 169.254.169.254 -j {{EBCHAIN_NAME}}')

        ret = bash_r(EBTABLES_CMD + ' -L {{EBCHAIN_NAME}} | grep -- "-i {{ETH_NAME}} -j DROP" > /dev/null')
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -I {{EBCHAIN_NAME}} -i {{ETH_NAME}} -j DROP')

        ret = bash_r(EBTABLES_CMD + ' -L {{EBCHAIN_NAME}} | grep -- "-o {{ETH_NAME}} -j DROP" > /dev/null')
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -I {{EBCHAIN_NAME}} -o {{ETH_NAME}} -j DROP')

        ret = bash_r("ebtables-save | grep '\-A {{EBCHAIN_NAME}} -j RETURN'")
        if ret != 0:
            bash_errorout(EBTABLES_CMD + ' -A {{EBCHAIN_NAME}} -j RETURN')

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
            "^/.*/meta-data/(.+)$" => "/{{ip}}/meta-data/$1",
            "^/.*/meta-data$" => "/{{ip}}/meta-data",
            "^/.*/meta-data/$" => "/{{ip}}/meta-data/",
            "^/.*/user-data$" => "/{{ip}}/user-data",
            "^/.*/user_data$" => "/{{ip}}/user_data",
            "^/.*/meta_data.json$" => "/{{ip}}/meta_data.json",
            "^/.*/password$" => "/{{ip}}/password",
            "^/.*/$" => "/{{ip}}/$1"
        )
        dir-listing.activate = "enable"
{% endfor -%}
    } else $HTTP["remoteip"] =~ "^(.*)$" {
        url.rewrite-once = (
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

        linux.mkdir(http_root, 0777)

        if not os.path.exists(conf_path):
            with open(conf_path, 'w') as fd:
                fd.write(conf)
        else:
            with open(conf_path, 'r') as fd:
                current_conf = fd.read()

            if current_conf != conf:
                with open(conf_path, 'w') as fd:
                    fd.write(conf)

        create_default_userdata(http_root)
        self.apply_zwatch_vm_agent(http_root)

    def apply_zwatch_vm_agent(self, http_root):
        agent_file_source_path = "/var/lib/zstack/kvm/zwatch-vm-agent"
        if not os.path.exists(agent_file_source_path):
            logger.error("Can't find file %s" % agent_file_source_path)
            return

        agent_file_target_path = os.path.join(http_root, "zwatch-vm-agent")
        if not os.path.exists(agent_file_target_path):
            bash_r("ln -s %s %s" % (agent_file_source_path, agent_file_target_path))
        elif not os.path.islink(agent_file_target_path):
            linux.rm_file_force(agent_file_target_path)
            bash_r("ln -s %s %s" % (agent_file_source_path, agent_file_target_path))

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

    @in_bash
    @lock.file_lock('/run/xtables.lock')
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

        index_file_path = os.path.join(meta_root, 'index.html')
        with open(index_file_path, 'w') as fd:
            fd.write('instance-id')
            if to.metadata.vmHostname:
                fd.write('\n')
                fd.write('local-hostname')

        instance_id_file_path = os.path.join(meta_root, 'instance-id')
        with open(instance_id_file_path, 'w') as fd:
            fd.write(to.metadata.vmUuid)

        if to.metadata.vmHostname:
            vm_hostname_file_path = os.path.join(meta_root, 'local-hostname')
            with open(vm_hostname_file_path, 'w') as fd:
                fd.write(to.metadata.vmHostname)

        if to.userdataList:
            userdata_file_path = os.path.join(root, 'user-data')
            with open(userdata_file_path, 'w') as fd:
                fd.write(packUserdata(to.userdataList))

            windows_meta_data_json_path = os.path.join(root, 'meta_data.json')
            with open(windows_meta_data_json_path, 'w') as fd:
                fd.write(conf)

            windows_userdata_file_path = os.path.join(root, 'user_data')
            with open(windows_userdata_file_path, 'w') as fd:
                fd.write(packUserdata(to.userdataList))

            windows_meta_data_password = os.path.join(root, 'password')
            with open(windows_meta_data_password, 'w') as fd:
                fd.write('')

    @in_bash
    @lock.lock('lighttpd')
    def _apply_userdata_restart_httpd(self, to):
        def check(_):
            pid = linux.find_process_by_cmdline([conf_path])
            return pid is not None

        conf_folder = os.path.join(self.USERDATA_ROOT, to.namespaceName)
        conf_path = os.path.join(conf_folder, 'lighttpd.conf')
        pid = linux.find_process_by_cmdline([conf_path])
        if pid:
            linux.kill_process(pid)

        linux.mkdir('/var/log/lighttpd', 0o750)
        #restart lighttpd to load new configration
        shell.call('ip netns exec %s lighttpd -f %s' % (to.namespaceName, conf_path))
        if not linux.wait_callback_success(check, None, 5):
            raise Exception('lighttpd[conf-file:%s] is not running after being started %s seconds' % (conf_path, 5))

    @in_bash
    @lock.file_lock('/run/xtables.lock')
    def work_userdata_iptables(self, CHAIN_NAME, to):
        # DNAT port 80
        PORT = to.port
        PORT_CHAIN_NAME = "UD-PORT-%s" % PORT
        # delete old chains not matching our port
        OLD_CHAIN = bash_errorout("iptables-save | awk '/^:UD-PORT-/{print substr($1,2)}'").strip(' \n\r\t')
        if OLD_CHAIN and OLD_CHAIN != CHAIN_NAME:
            ret = bash_r('iptables-save -t nat | grep -- "-j {{OLD_CHAIN}}"')
            if ret == 0:
                bash_r('%s -t nat -D PREROUTING -j {{OLD_CHAIN}}' % IPTABLES_CMD)

            bash_errorout('%s -t nat -F {{OLD_CHAIN}}' % IPTABLES_CMD)
            bash_errorout('%s -t nat -X {{OLD_CHAIN}}' % IPTABLES_CMD)
        ret = bash_r('iptables-save | grep -w ":{{PORT_CHAIN_NAME}}" > /dev/null')
        if ret != 0:
            self.bash_ignore_exist_for_ipt('%s -t nat -N {{PORT_CHAIN_NAME}}' % IPTABLES_CMD)
        ret = bash_r('%s -t nat -L PREROUTING | grep -- "-j {{PORT_CHAIN_NAME}}"' % IPTABLES_CMD)
        if ret != 0:
            self.bash_ignore_exist_for_ipt('%s -t nat -I PREROUTING -j {{PORT_CHAIN_NAME}}' % IPTABLES_CMD)
        ret = bash_r(
            'iptables-save -t nat | grep -- "{{PORT_CHAIN_NAME}} -d 169.254.169.254/32 -p tcp -j DNAT --to-destination :{{PORT}}"')
        if ret != 0:
            self.bash_ignore_exist_for_ipt(
                '%s -t nat -A {{PORT_CHAIN_NAME}} -d 169.254.169.254/32 -p tcp -j DNAT --to-destination :{{PORT}}' % IPTABLES_CMD)

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
        if l3Uuid in self.userData_vms[l3Uuid] and cmd.vmIp in self.userData_vms[l3Uuid]:
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
            os.chmod(self.DNSMASQ_LOG_LOGROTATE_PATH, 0644)

    @in_bash
    def _get_dhcp_server_ip_from_namespace(self, namespace_name):
        '''
        :param namespace_name:
        :return: dhcp server ip address in namespace, or empty string when failed
        # ip netns exec br_eth0_100_a9c8b01132444866a61d4c2ae03230ba ip add
        1: lo: <LOOPBACK> mtu 65536 qdisc noop state DOWN qlen 1
        link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
        13: inner0@if14: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP qlen 1000
        link/ether 16:25:4f:33:6c:32 brd ff:ff:ff:ff:ff:ff link-netnsid 0
        inet 192.168.100.119/24 scope global inner0
        valid_lft forever preferred_lft forever
        inet 169.254.169.254/32 scope global inner1
        valid_lft forever preferred_lft forever
        inet6 fe80::fc34:72ff:fe29:3564/64 scope link
        valid_lft forever preferred_lft forever
        '''
        r, dhcp_ip = bash_ro("ip netns exec {{namespace_name}} ip add | grep -w inet | grep -v 169.254 | awk '{print $2}' | awk -F '/' '{print $1}' | head -1")
        if r != 0:
            return ""
        return dhcp_ip.strip(" \t\r\n")

    @in_bash
    def _get_dhcp6_server_ip_from_namespace(self, namespace_name):
        r, dhcp_ip = bash_ro(
            "ip netns exec {{namespace_name}} ip add | grep -w inet6 | grep -v fe80:: | awk '{print $2}' | awk -F '/' '{print $1}' | head -1")
        if r != 0:
            return ""
        return dhcp_ip.strip(" \t\r\n")

    @lock.lock('prepare_dhcp')
    @kvmagent.replyerror
    def prepare_dhcp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        p = DhcpEnv()
        p.bridge_name = cmd.bridgeName
        p.dhcp_server_ip = cmd.dhcpServerIp
        p.dhcp_server6_ip = cmd.dhcp6ServerIp
        p.dhcp_netmask = cmd.dhcpNetmask
        p.namespace_name = cmd.namespaceName
        p.ipVersion = cmd.ipVersion
        p.prefixLen = cmd.prefixLen
        p.addressMode = cmd.addressMode

        old_dhcp_ip = self._get_dhcp_server_ip_from_namespace(cmd.namespaceName)
        if old_dhcp_ip != "" and old_dhcp_ip != cmd.dhcpServerIp:
            self._delete_dhcp4(cmd.namespaceName)

        old_dhcp6_ip = self._get_dhcp6_server_ip_from_namespace(cmd.namespaceName)
        if old_dhcp6_ip != "" and old_dhcp6_ip != cmd.dhcp6ServerIp:
            self._delete_dhcp6(cmd.namespaceName)

        p.prepare()

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

        @in_bash
        def apply(dhcp):
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
            br_num = br_num.strip(' \t\r\n')
            if not br_num:
                raise Exception('cannot find the ID for the namespace[%s]' % namespace_name)

            dinfo4 = None
            dinfo6 = None
            for d in dhcp:
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
                ranges.append(dinfo6.firstIp + "," + dinfo6.endIp + ",static," + str(dinfo6.prefixLength) + ",24h",)

            tmpt = Template(conf_file)
            conf_file = tmpt.render({
                'dns': dns_path,
                'dhcp': dhcp_path,
                'option': option_path,
                'log': log_path,
                'iface_name': 'inner%s' % br_num,
                'gateways': ranges
            })

            restart_dnsmasq = cmd.rebuild
            if not os.path.exists(conf_file_path) or cmd.rebuild:
                with open(conf_file_path, 'w') as fd:
                    fd.write(conf_file)
            else:
                with open(conf_file_path, 'r') as fd:
                    c = fd.read()

                if c != conf_file:
                    logger.debug('dnsmasq configure file for bridge[%s] changed, restart it' % bridge_name)
                    restart_dnsmasq = True
                    with open(conf_file_path, 'w') as fd:
                        fd.write(conf_file)
                    logger.debug('wrote dnsmasq configure file for bridge[%s]\n%s' % (bridge_name, conf_file))


            info = []
            for d in dhcp:
                dhcp_info = {'tag': d.mac.replace(':', '')}
                dhcp_info.update(d.__dict__)
                dhcp_info['dns'] = ','.join(d.dns)
                if d.dns6 is not None:
                    dnslist = ['[%s]' % dns for dns in d.dns6]
                    dhcp_info['dns6'] = ",".join(dnslist)
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

                if not cmd.rebuild:
                    self._erase_configurations(d.mac, d.ip, dhcp_path, dns_path, option_path)

            dhcp_conf = '''\
{% for d in dhcp -%}
{% if d.isDefaultL3Network -%}
{{d.mac}},set:{{d.tag}},{{d.address}},{{d.hostname}},infinite
{% else -%}
{{d.mac}},set:{{d.tag}},{{d.address}},infinite
{% endif -%}
{% endfor -%}
'''

            tmpt = Template(dhcp_conf)
            dhcp_conf = tmpt.render({'dhcp': info})
            mode = 'a+'
            if cmd.rebuild:
                mode = 'w'

            with open(dhcp_path, mode) as fd:
                fd.write(dhcp_conf)

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

            with open(option_path, mode) as fd:
                fd.write(option_conf)

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

            with open(dns_path, mode) as fd:
                fd.write(hostname_conf)

            if restart_dnsmasq:
                self._restart_dnsmasq(namespace_name, conf_file_path)
            else:
                self._refresh_dnsmasq(namespace_name, conf_file_path)

        @in_bash
        def applyv6(dhcp):
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
            br_num = br_num.strip(' \t\r\n')
            if not br_num:
                raise Exception('cannot find the ID for the namespace[%s]' % namespace_name)

            tmpt = Template(conf_file)
            conf_file = tmpt.render({
                'dns': dns_path,
                'dhcp': dhcp_path,
                'option': option_path,
                'log': log_path,
                'iface_name': 'inner%s' % br_num,
                'range': dhcp[0].firstIp + "," + dhcp[0].endIp + ",static," + str(dhcp[0].prefixLength) + ",24h",
            })

            restart_dnsmasq = cmd.rebuild
            if not os.path.exists(conf_file_path) or cmd.rebuild:
                with open(conf_file_path, 'w') as fd:
                    fd.write(conf_file)
            else:
                with open(conf_file_path, 'r') as fd:
                    c = fd.read()

                if c != conf_file:
                    logger.debug('dnsmasq configure file for bridge[%s] changed, restart it' % bridge_name)
                    restart_dnsmasq = True
                    with open(conf_file_path, 'w') as fd:
                        fd.write(conf_file)
                    logger.debug('wrote dnsmasq configure file for bridge[%s]\n%s' % (bridge_name, conf_file))

            info = []
            for d in dhcp:
                dhcp_info = {'tag': d.mac.replace(':', '')}
                dhcp_info.update(d.__dict__)
                if d.dns6 is not None:
                    dnslist = ['[%s]' % dns for dns in d.dns6]
                    dhcp_info['dnslist'] = ",".join(dnslist)
                if d.dnsDomain is not None:
                    dhcp_info['domainList'] = ",".join(d.dnsDomain)
                info.append(dhcp_info)

                if not cmd.rebuild:
                    self._erase_configurations(d.mac, d.ip, dhcp_path, dns_path, option_path)

            dhcp_conf = '''\
{% for d in dhcp -%}
{{d.mac}},set:{{d.tag}},[{{d.ip6}}],{{d.hostname}},infinite
{% endfor -%}
'''

            tmpt = Template(dhcp_conf)
            dhcp_conf = tmpt.render({'dhcp': info})
            mode = 'a+'
            if cmd.rebuild:
                mode = 'w'

            with open(dhcp_path, mode) as fd:
                fd.write(dhcp_conf)

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

            with open(option_path, mode) as fd:
                fd.write(option_conf)

            hostname_conf = '''\
{% for h in hostnames -%}
{% if h.isDefaultL3Network and h.hostname -%}
{{h.ip6}} {{h.hostname}}
{% endif -%}
{% endfor -%}
'''
            tmpt = Template(hostname_conf)
            hostname_conf = tmpt.render({'hostnames': info})

            with open(dns_path, mode) as fd:
                fd.write(hostname_conf)

            if restart_dnsmasq:
                self._restart_dnsmasq(namespace_name, conf_file_path)
            else:
                self._refresh_dnsmasq(namespace_name, conf_file_path)

        for k, v in namespace_dhcp.iteritems():
            if v[0].ipVersion == 4 or v[0].ipVersion == 46:
                apply(v)
            else:
                applyv6(v)

        rsp = ApplyDhcpRsp()
        return jsonobject.dumps(rsp)

    def _restart_dnsmasq(self, ns_name, conf_file_path):
        pid = linux.find_process_by_cmdline([conf_file_path])
        if pid:
            linux.kill_process(pid)

        NS_NAME = ns_name
        CONF_FILE = conf_file_path
        #DNSMASQ = bash_errorout('which dnsmasq').strip(' \t\r\n')
        DNSMASQ_BIN = "/usr/local/zstack/dnsmasq"
        bash_errorout('ip netns exec {{NS_NAME}} {{DNSMASQ_BIN}} --conf-file={{CONF_FILE}} -K')

        def check(_):
            pid = linux.find_process_by_cmdline([conf_file_path])
            return pid is not None

        if not linux.wait_callback_success(check, None, 5):
            raise Exception('dnsmasq[conf-file:%s] is not running after being started %s seconds' % (conf_file_path, 5))

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

    def _erase_configurations(self, mac, ip, dhcp_path, dns_path, option_path):
        MAC = mac
        TAG = mac.replace(':', '')
        DHCP = dhcp_path
        OPTION = option_path
        IP = ip
        DNS = dns_path

        bash_errorout('''\
sed -i '/{{MAC}},/d' {{DHCP}};
sed -i '/,{{IP}},/d' {{DHCP}};
sed -i '/^$/d' {{DHCP}};
sed -i '/{{TAG}},/d' {{OPTION}};
sed -i '/^$/d' {{OPTION}};
sed -i '/^{{IP}} /d' {{DNS}};
sed -i '/^$/d' {{DNS}}
''')


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
        def release(dhcp):
            for d in dhcp:
                conf_file_path, dhcp_path, dns_path, option_path, _ = self._make_conf_path(d.namespaceName)
                self._erase_configurations(d.mac, d.ip, dhcp_path, dns_path, option_path)
                self._restart_dnsmasq(d.namespaceName, conf_file_path)

        for k, v in namespace_dhcp.iteritems():
            release(v)

        rsp = ReleaseDhcpRsp()
        return jsonobject.dumps(rsp)

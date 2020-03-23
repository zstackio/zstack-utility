from jinja2 import Template

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import ip
from zstacklib.utils import iptables
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import ebtables
from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils.bash import *
from prometheus_client.core import GaugeMetricFamily
import netaddr

logger = log.get_logger(__name__)
EBTABLES_CMD = ebtables.get_ebtables_cmd()
IPTABLES_CMD = iptables.get_iptables_cmd()
IP6TABLES_CMD = iptables.get_ip6tables_cmd()

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


def collect_vip_statistics():
    def parse_eip_string(estr):
        vnic_ip = ip = vip_uuid = None
        ws = estr.split(',')
        for w in ws:
            if w.startswith('eip_addr'):
                ip = w.split(':')[1]
            elif w.startswith('vip'):
                vip_uuid = w.split(':')[1]
            elif w.startswith('vnic_ip'):
                vnic_ip = w.split(':')[1]

        #ipv6 addr has been formatted
        try:
            vipAddr = netaddr.IPAddress(ip)
            version = vipAddr.version
        except Exception as e:
            ip = ipv6TagToIpv6Address(ip)
            version = 6

        try:
            netaddr.IPAddress(vnic_ip)
        except Exception as e:
            vnic_ip = ipv6TagToIpv6Address(vnic_ip)

        return ip, vip_uuid, vnic_ip, version

    def find_namespace_name_by_ip(ipAddr, version):
        if version == 4:
            ns_name_suffix = ipAddr.replace('.', '_')
        else:
            ns_name_suffix = ipAddr

        o = bash_o('ip netns')
        for l in o.split('\n'):
            if ('%s ' % ns_name_suffix) in l:
                # l is like 'br_eth0_172_20_51_136 (id: 3)'
                return l.split()[0]

        return None

    def create_metric(line, ip, vip_uuid, vnic_ip, metrics, version):
        pairs = line.split()
        pkts = pairs[0]
        bs = pairs[1]
        if version == 4:
            src = pairs[7]
            dst = pairs[8]
        else:
            src = pairs[6]
            dst = pairs[7]

        # out traffic
        if src.startswith(vnic_ip):
            g = metrics['zstack_vip_out_bytes']
            g.add_metric([vip_uuid], float(bs))

            g = metrics['zstack_vip_out_packages']
            g.add_metric([vip_uuid], float(pkts))
        # in traffic
        if dst.startswith(vnic_ip):
            g = metrics['zstack_vip_in_bytes']
            g.add_metric([vip_uuid], float(bs))

            g = metrics['zstack_vip_in_packages']
            g.add_metric([vip_uuid], float(pkts))

    def collect(ip, vip_uuid, vnic_ip, version):
        ns_name = find_namespace_name_by_ip(ip, version)
        if not ns_name:
            return []

        CHAIN_NAME = "vip-perf"
        if version == 4:
            o = bash_o("ip netns exec {{ns_name}} iptables -nvxL {{CHAIN_NAME}} | sed '1,2d'")
        else:
            o = bash_o("ip netns exec {{ns_name}} ip6tables -nvxL {{CHAIN_NAME}} | sed '1,2d'")

        for l in o.split('\n'):
            l = l.strip(' \t\r\n')
            if l:
                create_metric(l, ip, vip_uuid, vnic_ip, metrics, version)

    o = bash_o('ip -o -d link')
    words = o.split()
    eip_strings = [w for w in words if w.startswith('eip:')]

    ret = []
    eips = {}
    for estr in eip_strings:
        ip, vip_uuid, vnic_ip, version = parse_eip_string(estr)
        if ip is None:
            logger.warn("no ip field found in %s" % estr)
            continue
        if vip_uuid is None:
            logger.warn("no vip field found in %s" % estr)
            continue
        if vnic_ip is None:
            logger.warn("no vnic_ip field found in %s" % estr)
            continue

        eips[ip] = (vip_uuid, vnic_ip, version)

    VIP_LABEL_NAME = 'VipUUID'
    metrics = {
        'zstack_vip_out_bytes': GaugeMetricFamily('zstack_vip_out_bytes', 'VIP outbound traffic in bytes', labels=[VIP_LABEL_NAME]),
        'zstack_vip_out_packages': GaugeMetricFamily('zstack_vip_out_packages', 'VIP outbound traffic packages', labels=[VIP_LABEL_NAME]),
        'zstack_vip_in_bytes': GaugeMetricFamily('zstack_vip_in_bytes', 'VIP inbound traffic in bytes', labels=[VIP_LABEL_NAME]),
        'zstack_vip_in_packages': GaugeMetricFamily('zstack_vip_in_packages', 'VIP inbound traffic packages', labels=[VIP_LABEL_NAME])
    }

    for ip, (vip_uuid, vnic_ip, version) in eips.items():
        collect(ip, vip_uuid, vnic_ip, version)

    return metrics.values()

kvmagent.register_prometheus_collector(collect_vip_statistics)

class DEip(kvmagent.KvmAgent):

    APPLY_EIP_PATH = "/flatnetworkprovider/eip/apply"
    DELETE_EIP_PATH = "/flatnetworkprovider/eip/delete"
    BATCH_APPLY_EIP_PATH = "/flatnetworkprovider/eip/batchapply"
    BATCH_DELETE_EIP_PATH = "/flatnetworkprovider/eip/batchdelete"

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.APPLY_EIP_PATH, self.apply_eip)
        http_server.register_async_uri(self.BATCH_APPLY_EIP_PATH, self.apply_eips)
        http_server.register_async_uri(self.DELETE_EIP_PATH, self.delete_eip)
        http_server.register_async_uri(self.BATCH_DELETE_EIP_PATH, self.delete_eips)

    def stop(self):
        pass

    @kvmagent.replyerror
    def apply_eip(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._apply_eips([cmd.eip])
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def apply_eips(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._apply_eips(cmd.eips)
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def delete_eips(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._delete_eips(cmd.eips)
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def delete_eip(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._delete_eips([cmd.eip])
        return jsonobject.dumps(AgentRsp())

    @bash.in_bash
    @lock.file_lock('/run/xtables.lock')
    def _delete_eip(self, eip):
        dev_base_name = eip.nicName.replace('vnic', '', 1)
        dev_base_name = dev_base_name.replace(".", "_")

        NIC_NAME = eip.nicName
        CHAIN_NAME = '%s-gw' % NIC_NAME
        NS_NAME = "%s_%s" % (eip.publicBridgeName, eip.vip.replace(".", "_"))
        EIP_UUID = eip.eipUuid[-9:]
        PUB_ODEV = "%s_eo" % (EIP_UUID)
        PRI_ODEV = "%s_o" % (EIP_UUID)

        @bash.in_bash
        def delete_namespace():
            if bash_r('ip netns | grep -w {{NS_NAME}} > /dev/null') == 0:
                bash_errorout('ip netns delete {{NS_NAME}}')

        @bash.in_bash
        def delete_outer_dev():
            if bash_r('ip link | grep -w {{PUB_ODEV}} > /dev/null') == 0:
                bash_r('ip link del {{PUB_ODEV}}')

        @bash.in_bash
        def delete_arp_rules():
            if bash_r(EBTABLES_CMD + ' -t nat -L {{CHAIN_NAME}} >/dev/null 2>&1') == 0:
                RULE = "-i {{NIC_NAME}} -j {{CHAIN_NAME}}"
                if bash_r(EBTABLES_CMD + ' -t nat -L PREROUTING | grep -- "{{RULE}}" > /dev/null') == 0:
                    bash_errorout(EBTABLES_CMD + ' -t nat -D PREROUTING {{RULE}}')

                bash_errorout(EBTABLES_CMD + ' -t nat -F {{CHAIN_NAME}}')
                bash_errorout(EBTABLES_CMD + ' -t nat -X {{CHAIN_NAME}}')

            PRI_ODEV_CHAIN = "{{PRI_ODEV}}-gw"
            if bash_r(EBTABLES_CMD + ' -t nat -L {{PRI_ODEV_CHAIN}} >/dev/null 2>&1') == 0:
                RULE = "-i {{PRI_ODEV}} -j {{PRI_ODEV_CHAIN}}"
                if bash_r(EBTABLES_CMD + ' -t nat -L PREROUTING | grep -- "{{RULE}}" > /dev/null') == 0:
                    bash_errorout(EBTABLES_CMD + ' -t nat -D PREROUTING {{RULE}}')

                bash_errorout(EBTABLES_CMD + ' -t nat -F {{PRI_ODEV_CHAIN}}')
                bash_errorout(EBTABLES_CMD + ' -t nat -X {{PRI_ODEV_CHAIN}}')

            for BLOCK_DEV in [PRI_ODEV, PUB_ODEV, NIC_NAME]:
                BLOCK_CHAIN_NAME = '{{BLOCK_DEV}}-arp'

                if bash_r(EBTABLES_CMD + ' -t nat -L {{BLOCK_CHAIN_NAME}} > /dev/null 2>&1') == 0:
                    RULE = '-p ARP -o {{BLOCK_DEV}} -j {{BLOCK_CHAIN_NAME}}'
                    if bash_r(EBTABLES_CMD + ' -t nat -L POSTROUTING | grep -- "{{RULE}}" > /dev/null') == 0:
                        bash_errorout(EBTABLES_CMD + ' -t nat -D POSTROUTING {{RULE}}')

                    bash_errorout(EBTABLES_CMD + ' -t nat -F {{BLOCK_CHAIN_NAME}}')
                    bash_errorout(EBTABLES_CMD + ' -t nat -X {{BLOCK_CHAIN_NAME}}')

        @bash.in_bash
        def delete_ipv6_rules():
            if bash_r(EBTABLES_CMD + ' -t nat -L {{CHAIN_NAME}} >/dev/null 2>&1') == 0:
                RULE = "-i {{NIC_NAME}} -j {{CHAIN_NAME}}"
                if bash_r(EBTABLES_CMD + ' -t nat -L PREROUTING | grep -- "{{RULE}}" > /dev/null') == 0:
                    bash_errorout(EBTABLES_CMD + ' -t nat -D PREROUTING {{RULE}}')

                bash_errorout(EBTABLES_CMD + ' -t nat -F {{CHAIN_NAME}}')
                bash_errorout(EBTABLES_CMD + ' -t nat -X {{CHAIN_NAME}}')

        delete_namespace()
        delete_outer_dev()
        if int(eip.ipVersion) == 4:
            delete_arp_rules()
        else :
            delete_ipv6_rules()

    @lock.lock('eip')
    def _delete_eips(self, eips):
        for eip in eips:
            self._delete_eip(eip)

    @bash.in_bash
    @lock.file_lock('/run/xtables.lock')
    def _apply_eip(self, eip):
        dev_base_name = eip.nicName.replace('vnic', '', 1)
        dev_base_name = dev_base_name.replace(".", "_")
        PUB_BR = eip.publicBridgeName
        EIP_UUID = eip.eipUuid[-9:]

        OLD_PUB_ODEVS = ["%s_eo" % dev_base_name, "%s_eo_%s" % (dev_base_name, EIP_UUID)]
        OLD_PUB_IDEVS = ["%s_ei" % dev_base_name, "%s_ei_%s" % (dev_base_name, EIP_UUID)]
        OLD_PRI_ODEVS = ["%s_o" % dev_base_name, "%s_o_%s" % (dev_base_name, EIP_UUID)]
        OLD_PRI_IDEVS = ["%s_i" % dev_base_name, "%s_i_%s" % (dev_base_name, EIP_UUID)]

        PUB_ODEV = "%s_eo" % (EIP_UUID)
        PUB_IDEV = "%s_ei" % (EIP_UUID)
        PRI_ODEV = "%s_o" % (EIP_UUID)
        PRI_IDEV = "%s_i" % (EIP_UUID)

        PRI_BR= eip.vmBridgeName
        VIP= eip.vip
        VIP_NETMASK= eip.vipNetmask
        VIP_GW= eip.vipGateway
        NIC_NAME= eip.nicName
        NIC_GATEWAY= eip.nicGateway
        NIC_NETMASK= eip.nicNetmask
        NIC_PREFIXLEN = eip.nicPrefixLen
        NIC_IP= eip.nicIp
        NIC_MAC= eip.nicMac
        NS_NAME = "%s_%s" % (eip.publicBridgeName, eip.vip.replace(".", "_"))

        EBTABLE_CHAIN_NAME= eip.vmBridgeName
        PRI_BR_PHY_DEV= eip.vmBridgeName.replace('br_', '', 1)

        if int(eip.ipVersion) == 4:
            EIP_DESC = "eip:%s,eip_addr:%s,vnic:%s,vnic_ip:%s,vm:%s,vip:%s" % (eip.eipUuid, VIP, eip.nicName, NIC_IP, eip.vmUuid, eip.vipUuid)
        else:
            vip_tag = ipv6AddressToTag(VIP)
            nic_tag = ipv6AddressToTag(NIC_IP)
            EIP_DESC = "eip:%s,eip_addr:%s,vnic:%s,vnic_ip:%s,vm:%s,vip:%s" % (eip.eipUuid, vip_tag, eip.nicName, nic_tag, eip.vmUuid, eip.vipUuid)

        NS = "ip netns exec {{NS_NAME}}"

        # in case the namespace deleted and the orphan outer link leaves in the system,
        # deleting the orphan link and recreate it
        @bash.in_bash
        def delete_orphan_outer_dev(inner_dev, outer_dev):
            if bash_r('ip netns exec {{NS_NAME}} ip link | grep -w {{inner_dev}} > /dev/null') != 0:
                # ignore error
                bash_r('ip link del {{outer_dev}} &> /dev/null')

        @bash.in_bash
        def create_dev_if_needed(outer_dev, outer_dev_desc, inner_dev, inner_dev_desc):
            if bash_r('ip link | grep -w {{outer_dev}} > /dev/null ') != 0:
                bash_errorout('ip link add {{outer_dev}} type veth peer name {{inner_dev}}')
                bash_errorout('ip link set {{outer_dev}} alias {{outer_dev_desc}}')
                bash_errorout('ip link set {{inner_dev}} alias {{inner_dev_desc}}')
                bash_errorout('ip link set mtu %d dev %s' % (linux.MAX_MTU_OF_VNIC, outer_dev))
                bash_errorout('ip link set mtu %d dev %s' % (linux.MAX_MTU_OF_VNIC, inner_dev))

            bash_errorout('ip link set {{outer_dev}} up')

        @bash.in_bash
        def add_dev_to_br_if_needed(bridge, device):
            if bash_r('brctl show {{bridge}} | grep -w {{device}} > /dev/null') != 0:
                bash_errorout('brctl addif {{bridge}} {{device}}')

        def add_dev_namespace_if_needed(device, namespace):
            if bash_r('eval {{NS}} ip link | grep -w {{device}} > /dev/null') != 0:
                bash_errorout('ip link set {{device}} netns {{namespace}}')

        @bash.in_bash
        def set_ip_to_idev_if_needed(device, ipCmd, ip, prefix):
            str = 'eval {{NS}} {{cmd}} addr show {{device}} | grep -w {{ip}} > /dev/null'
            if bash_r('eval {{NS}} {{ipCmd}} addr show {{device}} | grep -w {{ip}} > /dev/null') != 0:
                bash_errorout('eval {{NS}} {{ipCmd}} addr flush dev {{device}}')
                bash_errorout('eval {{NS}} {{ipCmd}} addr add {{ip}}/{{prefix}} dev {{device}}')

            bash_errorout('eval {{NS}} ip link set {{device}} up')

        @bash.in_bash
        def create_iptable_rule_if_needed(iptableCmd, table, rule, at_head=False):
            if bash_r('eval {{NS}} {{iptableCmd}}-save | grep -- "{{rule}}" > /dev/null') != 0:
                if at_head:
                    bash_errorout('eval {{NS}} {{iptableCmd}} -w {{table}} -I {{rule}}')
                else:
                    bash_errorout('eval {{NS}} {{iptableCmd}} -w {{table}} -A {{rule}}')

        @bash.in_bash
        def create_ebtable_rule_if_needed(table, chain, rule, at_head=False):
            if bash_r(EBTABLES_CMD + ' -t {{table}} -L {{chain}} | grep -- "{{rule}}" > /dev/null') != 0:
                if at_head:
                    bash_errorout(EBTABLES_CMD + ' -t {{table}} -I {{chain}} {{rule}}')
                else:
                    bash_errorout(EBTABLES_CMD + ' -t {{table}} -A {{chain}} {{rule}}')

        @bash.in_bash
        def set_eip_rules():
            DNAT_NAME = "DNAT-{{VIP}}"
            if bash_r('eval {{NS}} iptables-save | grep -w ":{{DNAT_NAME}}" > /dev/null') != 0:
                bash_errorout('eval {{NS}} %s -t nat -N {{DNAT_NAME}}' % IPTABLES_CMD)

            create_iptable_rule_if_needed("iptables", "-t nat", 'PREROUTING -d {{VIP}}/32 -j {{DNAT_NAME}}')
            create_iptable_rule_if_needed("iptables", "-t nat", '{{DNAT_NAME}} -j DNAT --to-destination {{NIC_IP}}')

            FWD_NAME = "FWD-{{VIP}}"
            if bash_r('eval {{NS}} iptables-save | grep -w ":{{FWD_NAME}}" > /dev/null') != 0:
                bash_errorout('eval {{NS}} %s -N {{FWD_NAME}}' % IPTABLES_CMD)

            create_iptable_rule_if_needed("iptables", "-t filter", "FORWARD ! -d {{NIC_IP}}/32 -i {{PUB_IDEV}} -j REJECT --reject-with icmp-port-unreachable")
            create_iptable_rule_if_needed("iptables", "-t filter", "FORWARD -i {{PRI_IDEV}} -o {{PUB_IDEV}} -j {{FWD_NAME}}")
            create_iptable_rule_if_needed("iptables", "-t filter", "FORWARD -i {{PUB_IDEV}} -o {{PRI_IDEV}} -j {{FWD_NAME}}")
            create_iptable_rule_if_needed("iptables", "-t filter", "{{FWD_NAME}} -j ACCEPT")

            SNAT_NAME = "SNAT-{{VIP}}"
            if bash_r('eval {{NS}} iptables-save | grep -w ":{{SNAT_NAME}}" > /dev/null ') != 0:
                bash_errorout('eval {{NS}} %s -t nat -N {{SNAT_NAME}}' % IPTABLES_CMD)

            create_iptable_rule_if_needed("iptables", "-t nat", "POSTROUTING -s {{NIC_IP}}/32 -j {{SNAT_NAME}}")
            create_iptable_rule_if_needed("iptables", "-t nat", "{{SNAT_NAME}} -j SNAT --to-source {{VIP}}")

        @bash.in_bash
        def set_eip_rules_v6():
            DNAT_NAME = "EIP6-DNAT-{{EIP_UUID}}"
            if bash_r('eval {{NS}} ip6tables-save | grep -w ":{{DNAT_NAME}}" > /dev/null') != 0:
                bash_errorout('eval {{NS}} %s -t nat -N {{DNAT_NAME}}' % IP6TABLES_CMD)

            create_iptable_rule_if_needed("ip6tables", "-t nat", 'PREROUTING -d {{VIP}}/128 -j {{DNAT_NAME}}')
            create_iptable_rule_if_needed("ip6tables", "-t nat", '{{DNAT_NAME}} -j DNAT --to-destination {{NIC_IP}}')

            FWD_NAME = "EIP6-FWD-{{EIP_UUID}}"
            if bash_r('eval {{NS}} ip6tables-save | grep -w ":{{FWD_NAME}}" > /dev/null') != 0:
                bash_errorout('eval {{NS}} %s -N {{FWD_NAME}}' % IP6TABLES_CMD)

            create_iptable_rule_if_needed("ip6tables", "-t filter", "FORWARD ! -d {{NIC_IP}}/128 -i {{PUB_IDEV}} -j REJECT --reject-with icmp6-addr-unreachable")
            create_iptable_rule_if_needed("ip6tables", "-t filter", "FORWARD -i {{PRI_IDEV}} -o {{PUB_IDEV}} -j {{FWD_NAME}}")
            create_iptable_rule_if_needed("ip6tables", "-t filter", "FORWARD -i {{PUB_IDEV}} -o {{PRI_IDEV}} -j {{FWD_NAME}}")
            create_iptable_rule_if_needed("ip6tables", "-t filter", "{{FWD_NAME}} -j ACCEPT")

            SNAT_NAME = "EIP6-SNAT-{{EIP_UUID}}"
            if bash_r('eval {{NS}} ip6tables-save | grep -w ":{{SNAT_NAME}}" > /dev/null ') != 0:
                bash_errorout('eval {{NS}} %s -t nat -N {{SNAT_NAME}}' % IP6TABLES_CMD)

            create_iptable_rule_if_needed("ip6tables", "-t nat", "POSTROUTING -s {{NIC_IP}}/128 -j {{SNAT_NAME}}")
            create_iptable_rule_if_needed("ip6tables", "-t nat", "{{SNAT_NAME}} -j SNAT --to-source {{VIP}}")

        @bash.in_bash
        def set_default_route_if_needed(ipCmd):
            if bash_r('eval {{NS}} {{ipCmd}} route | grep -w default > /dev/null') != 0:
                bash_errorout('eval {{NS}} {{ipCmd}} route add default via {{VIP_GW}}')

        @bash.in_bash
        def set_gateway_arp_if_needed():
            CHAIN_NAME = "{{NIC_NAME}}-gw"

            if bash_r(EBTABLES_CMD + ' -t nat -L {{CHAIN_NAME}} > /dev/null 2>&1') != 0:
                bash_errorout(EBTABLES_CMD + ' -t nat -N {{CHAIN_NAME}}')

            create_ebtable_rule_if_needed('nat', 'PREROUTING', '-i {{NIC_NAME}} -j {{CHAIN_NAME}}')
            GATEWAY = bash_o("eval {{NS}} ip link | grep -w {{PRI_IDEV}} -A 1 | awk '/link\/ether/{print $2}'").strip()
            if not GATEWAY:
                raise Exception('cannot find the device[%s] in the namespace[%s]' % (PRI_IDEV, NS_NAME))

            create_ebtable_rule_if_needed('nat', CHAIN_NAME, "-p ARP --arp-op Request --arp-ip-dst {{NIC_GATEWAY}} -j arpreply --arpreply-mac {{GATEWAY}}")

            for BLOCK_DEV in [PRI_ODEV, PUB_ODEV]:
                BLOCK_CHAIN_NAME = '{{BLOCK_DEV}}-arp'
                if bash_r(EBTABLES_CMD + ' -t nat -L {{BLOCK_CHAIN_NAME}} > /dev/null 2>&1') != 0:
                    bash_errorout(EBTABLES_CMD + ' -t nat -N {{BLOCK_CHAIN_NAME}}')

                create_ebtable_rule_if_needed('nat', 'POSTROUTING', "-p ARP -o {{BLOCK_DEV}} -j {{BLOCK_CHAIN_NAME}}")
                create_ebtable_rule_if_needed('nat', BLOCK_CHAIN_NAME, "-p ARP -o {{BLOCK_DEV}} --arp-op Request --arp-ip-dst {{NIC_GATEWAY}} --arp-mac-src ! {{NIC_MAC}} -j DROP")

            BLOCK_CHAIN_NAME = '{{NIC_NAME}}-arp'
            if bash_r(EBTABLES_CMD + ' -t nat -L {{BLOCK_CHAIN_NAME}} > /dev/null 2>&1') != 0:
                bash_errorout(EBTABLES_CMD + ' -t nat -N {{BLOCK_CHAIN_NAME}}')

            create_ebtable_rule_if_needed('nat', 'POSTROUTING', "-p ARP -o {{NIC_NAME}} -j {{BLOCK_CHAIN_NAME}}")
            create_ebtable_rule_if_needed('nat', BLOCK_CHAIN_NAME,
                                          "-p ARP -o {{NIC_NAME}} --arp-op Request --arp-ip-src {{NIC_GATEWAY}} --arp-mac-src ! {{GATEWAY}} -j DROP")

        @bash.in_bash
        def set_gateway_arp_if_needed_v6():
            CHAIN_NAME = "{{NIC_NAME}}-gw"

            if bash_r(EBTABLES_CMD + ' -t nat -L {{CHAIN_NAME}} > /dev/null 2>&1') != 0:
                bash_errorout(EBTABLES_CMD + ' -t nat -N {{CHAIN_NAME}}')

            create_ebtable_rule_if_needed('nat', 'PREROUTING', '-i {{NIC_NAME}} -j {{CHAIN_NAME}}', at_head=True)
            GATEWAY = bash_o("eval {{NS}} ip link | grep -w {{PRI_IDEV}} -A 1 | awk '/link\/ether/{print $2}'").strip()
            if not GATEWAY:
                raise Exception('cannot find the device[%s] in the namespace[%s]' % (PRI_IDEV, NS_NAME))

            # this is hack method to direct ipv6 external traffic to this eip namespace
            create_ebtable_rule_if_needed('nat', CHAIN_NAME,
                                          "-p IPv6 --ip6-destination {{NIC_GATEWAY}}/{{NIC_PREFIXLEN}} -j ACCEPT")
            create_ebtable_rule_if_needed('nat', CHAIN_NAME,
                                          "-p IPv6 --ip6-destination fe80::/64 -j ACCEPT")
            create_ebtable_rule_if_needed('nat', CHAIN_NAME,
                                          "-p IPv6 --ip6-destination ff00::/8 -j ACCEPT")
            create_ebtable_rule_if_needed('nat', CHAIN_NAME,
                                          "-p IPv6 -j dnat --to-destination {{GATEWAY}}")

        @bash.in_bash
        def enable_ipv6_forwarding():
            bash_r('eval {{NS}} sysctl -w net.ipv6.conf.all.forwarding=1')

        @bash.in_bash
        def create_perf_monitor():
            o = bash_o("eval {{NS}} ip -o -f inet addr show | awk '/scope global/ {print $4}'")
            cidr = None
            vnic_ip = netaddr.IPAddress(NIC_IP)
            for l in o.split('\n'):
                l = l.strip(' \t\n\r')
                if not l:
                    continue

                nw = netaddr.IPNetwork(l)
                if vnic_ip in nw:
                    cidr = nw.cidr
                    break

            if not cidr:
                raise Exception("cannot find CIDR of vnic ip[%s] in namespace %s" % (NIC_IP, NS_NAME))

            CHAIN_NAME = "vip-perf"
            bash_r("eval {{NS}} %s -N {{CHAIN_NAME}} > /dev/null" % IPTABLES_CMD)
            create_iptable_rule_if_needed("iptables", "-t filter", "FORWARD -s {{NIC_IP}}/32 ! -d {{cidr}} -j {{CHAIN_NAME}}", True)
            create_iptable_rule_if_needed("iptables", "-t filter", "FORWARD ! -s {{cidr}} -d {{NIC_IP}}/32 -j {{CHAIN_NAME}}", True)
            create_iptable_rule_if_needed("iptables", "-t filter", "{{CHAIN_NAME}} -s {{NIC_IP}}/32 -j RETURN")
            create_iptable_rule_if_needed("iptables", "-t filter", "{{CHAIN_NAME}} -d {{NIC_IP}}/32 -j RETURN")

        def create_ipv6_perf_monitor():
            o = bash_o("eval {{NS}} ip -o -f inet6 addr show | awk '/scope global/ {print $4}'")
            cidr = None
            vnic_ip = netaddr.IPAddress(NIC_IP, 6)
            for l in o.split('\n'):
                l = l.strip(' \t\n\r')
                if not l:
                    continue

                nw = netaddr.IPNetwork(l)
                if vnic_ip in nw:
                    cidr = nw.cidr
                    break

            if not cidr:
                raise Exception("cannot find CIDR of vnic ip[%s] in namespace %s" % (NIC_IP, NS_NAME))

            CHAIN_NAME = "vip-perf"
            bash_r("eval {{NS}} %s -N {{CHAIN_NAME}} > /dev/null" % IP6TABLES_CMD)
            create_iptable_rule_if_needed("ip6tables", "-t filter", "FORWARD -s {{NIC_IP}}/128 ! -d {{cidr}} -j {{CHAIN_NAME}}", True)
            create_iptable_rule_if_needed("ip6tables", "-t filter", "FORWARD ! -s {{cidr}} -d {{NIC_IP}}/128 -j {{CHAIN_NAME}}", True)
            create_iptable_rule_if_needed("ip6tables", "-t filter", "{{CHAIN_NAME}} -s {{NIC_IP}}/128 -j RETURN")
            create_iptable_rule_if_needed("ip6tables", "-t filter", "{{CHAIN_NAME}} -d {{NIC_IP}}/128 -j RETURN")

        @bash.in_bash
        def add_filter_to_prevent_namespace_arp_request():
            #add arp neighbor for private ip
            bash_r('ip netns exec {{NS_NAME}} ip neighbor del {{NIC_IP}} dev {{PRI_IDEV}}')
            bash_r('ip netns exec {{NS_NAME}} ip neighbor add {{NIC_IP}} lladdr {{NIC_MAC}} dev {{PRI_IDEV}}')

            #add ebtales to prevent eip namaespace send arp request
            PRI_ODEV_CHAIN = "{{PRI_ODEV}}-gw"

            if bash_r(EBTABLES_CMD + ' -t nat -L {{PRI_ODEV_CHAIN}} > /dev/null 2>&1') != 0:
                bash_errorout(EBTABLES_CMD + ' -t nat -N {{PRI_ODEV_CHAIN}}')

            create_ebtable_rule_if_needed('nat', 'PREROUTING', '-i {{PRI_ODEV}} -j {{PRI_ODEV_CHAIN}}')
            create_ebtable_rule_if_needed('nat', PRI_ODEV_CHAIN,
                                          "-p ARP --arp-op Request --arp-ip-dst {{NIC_IP}} -j arpreply --arpreply-mac {{NIC_MAC}}", True)
            create_ebtable_rule_if_needed('nat', PRI_ODEV_CHAIN, "-p ARP --arp-op Request -j DROP")

        newCreated = False
        if bash_r('eval {{NS}} ip link show > /dev/null') != 0:
            newCreated = True
            bash_errorout('ip netns add {{NS_NAME}}')

        # To be compatibled with old version
        for i in range(len(OLD_PUB_IDEVS)):
            delete_orphan_outer_dev(OLD_PUB_IDEVS[i], OLD_PUB_ODEVS[i])
            delete_orphan_outer_dev(OLD_PRI_IDEVS[i], OLD_PRI_ODEVS[i])

        delete_orphan_outer_dev(PUB_IDEV, PUB_ODEV)
        delete_orphan_outer_dev(PRI_IDEV, PRI_ODEV)

        create_dev_if_needed(PUB_ODEV, EIP_DESC, PUB_IDEV, EIP_DESC)
        create_dev_if_needed(PRI_ODEV, EIP_DESC, PRI_IDEV, EIP_DESC)

        add_dev_to_br_if_needed(PUB_BR, PUB_ODEV)
        add_dev_to_br_if_needed(PRI_BR, PRI_ODEV)

        add_dev_namespace_if_needed(PUB_IDEV, NS_NAME)
        add_dev_namespace_if_needed(PRI_IDEV, NS_NAME)

        if int(eip.ipVersion) == 4:
            bash_r('eval {{NS}} ip link set {{PUB_IDEV}} up')
            if newCreated :
                r, o = bash.bash_ro('eval {{NS}} arping -D -w 1 -c 3 -I {{PUB_IDEV}} {{VIP}}')
                if r != 0 and "Unicast reply from" in o:
                    raise Exception('there are dupicated public [ip:%s] on public network, output: %s' % (VIP, o))

            vipPrefixLen = linux.netmask_to_cidr(VIP_NETMASK)
            set_ip_to_idev_if_needed(PUB_IDEV, "ip", VIP, vipPrefixLen)
            nicPrefixLen = linux.netmask_to_cidr(NIC_NETMASK)
            set_ip_to_idev_if_needed(PRI_IDEV, "ip", NIC_GATEWAY, nicPrefixLen)
            add_filter_to_prevent_namespace_arp_request()

            # ping VIP gateway
            bash_r('eval {{NS}} arping -q -A -w 2.5 -c 3 -I {{PUB_IDEV}} {{VIP}} > /dev/null')
            set_gateway_arp_if_needed()
            set_eip_rules()
            set_default_route_if_needed("ip")
            create_perf_monitor()
        else:
            set_ip_to_idev_if_needed(PUB_IDEV, "ip -6", VIP, eip.vipPrefixLen)
            set_ip_to_idev_if_needed(PRI_IDEV, "ip -6", NIC_GATEWAY, eip.nicPrefixLen)
            set_gateway_arp_if_needed_v6()
            set_eip_rules_v6()
            set_default_route_if_needed("ip -6")
            enable_ipv6_forwarding()
            create_ipv6_perf_monitor()

    @lock.lock('eip')
    def _apply_eips(self, eips):
        for eip in eips:
            self._apply_eip(eip)

def ipv6AddressToTag(ip):
    return ip.replace(":", "-")

def ipv6TagToIpv6Address(tag):
    return tag.replace("-", ":")
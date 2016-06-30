from jinja2 import Template

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils.bash import *

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

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

    @in_bash
    def _delete_eip(self, eip):
        dev_base_name = eip.nicName.replace('vnic', '', 1)
        dev_base_name = dev_base_name.replace(".", "_")

        NS_NAME = "%s_%s" % (eip.publicBridgeName, eip.vip.replace(".", "_"))
        PUB_ODEV = "%s_eo" % dev_base_name
        PRI_ODEV = "%s_o" % dev_base_name
        NIC_NAME = eip.nicName
        CHAIN_NAME = '%s-gw' % NIC_NAME

        def delete_namespace():
            if bash_r('ip netns | grep -w {{NS_NAME}} > /dev/null') == 0:
                bash_errorout('ip netns delete {{NS_NAME}}')

        def delete_outer_dev():
            if bash_r('ip link | grep -w {{PUB_ODEV}} > /dev/null') == 0:
                bash_errorout('ip link del {{PUB_ODEV}}')

        def delete_arp_rules():
            if bash_r('ebtables -t nat -L {{CHAIN_NAME}} >/dev/null 2>&1') == 0:
                RULE = "-i {{NIC_NAME}} -j {{CHAIN_NAME}}"
                if bash_r('ebtables -t nat -L PREROUTING | grep -- "{{RULE}}" > /dev/null') == 0:
                    bash_errorout('ebtables -t nat -D PREROUTING {{RULE}}')

                bash_errorout('ebtables -t nat -F {{CHAIN_NAME}}')
                bash_errorout('ebtables -t nat -X {{CHAIN_NAME}}')

            BLOCK_CHAIN_NAME = '{{PRI_ODEV}}-arp'

            if bash_r('ebtables -t nat -L {{BLOCK_CHAIN_NAME}} > /dev/null 2>&1') == 0:
                RULE = '-p ARP -o {{PRI_ODEV}} -j {{BLOCK_CHAIN_NAME}}'
                if bash_r('ebtables -t nat -L POSTROUTING | grep -- "{{RULE}}" > /dev/null') == 0:
                    bash_errorout('ebtables -t nat -D POSTROUTING {{RULE}}')

                bash_errorout('ebtables -t nat -F {{BLOCK_CHAIN_NAME}}')
                bash_errorout('ebtables -t nat -X {{BLOCK_CHAIN_NAME}}')

        delete_namespace()
        delete_outer_dev()
        delete_arp_rules()

    @lock.lock('eip')
    def _delete_eips(self, eips):
        for eip in eips:
            self._delete_eip(eip)

    @in_bash
    def _apply_eip(self, eip):
        dev_base_name = eip.nicName.replace('vnic', '', 1)
        dev_base_name = dev_base_name.replace(".", "_")

        PUB_BR = eip.publicBridgeName
        PUB_ODEV= "%s_eo" % dev_base_name
        PUB_IDEV= "%s_ei" % dev_base_name
        PRI_ODEV= "%s_o" % dev_base_name
        PRI_IDEV= "%s_i" % dev_base_name
        PRI_BR= eip.vmBridgeName
        VIP= eip.vip
        VIP_NETMASK= eip.vipNetmask
        VIP_GW= eip.vipGateway
        NIC_NAME= eip.nicName
        NIC_GATEWAY= eip.nicGateway
        NIC_NETMASK= eip.nicNetmask
        NIC_IP= eip.nicIp
        NIC_MAC= eip.nicMac
        NS_NAME= "%s_%s" % (eip.publicBridgeName, eip.vip.replace(".", "_"))
        EBTABLE_CHAIN_NAME= eip.vmBridgeName
        PRI_BR_PHY_DEV= eip.vmBridgeName.replace('br_', '', 1)

        NS = "ip netns exec {{NS_NAME}}"

        # in case the namespace deleted and the orphan outer link leaves in the system,
        # deleting the orphan link and recreate it
        def delete_orphan_outer_dev(inner_dev, outer_dev):
            if bash_r('ip netns exec {{NS_NAME}} ip link | grep -w {{inner_dev}} > /dev/null') != 0:
                # ignore error
                bash_r('ip link del {{outer_dev}} &> /dev/null')

        def create_dev_if_needed(outer_dev, inner_dev):
            if bash_r('ip link | grep -w {{outer_dev}} > /dev/null ') != 0:
                bash_errorout('ip link add {{outer_dev}} type veth peer name {{inner_dev}}')

            bash_errorout('ip link set {{outer_dev}} up')

        def add_dev_to_br_if_needed(bridge, device):
            if bash_r('brctl show {{bridge}} | grep -w {{device}} > /dev/null') != 0:
                bash_errorout('brctl addif {{bridge}} {{device}}')

        def add_dev_namespace_if_needed(device, namespace):
            if bash_r('eval {{NS}} ip link | grep -w {{device}} > /dev/null') != 0:
                bash_errorout('ip link set {{device}} netns {{namespace}}')

        def set_ip_to_idev_if_needed(device, ip, netmask):
            if bash_r('eval {{NS}} ip addr show {{device}} | grep -w {{ip}} > /dev/null') != 0:
                bash_errorout('eval {{NS}} ip addr flush dev {{device}}')
                bash_errorout('eval {{NS}} ip addr add {{ip}}/{{netmask}} dev {{device}}')

            bash_errorout('eval {{NS}} ip link set {{device}} up')

        def create_iptable_rule_if_needed(table, rule):
            if bash_r('eval {{NS}} iptables-save | grep -- "{{rule}}" > /dev/null') != 0:
                bash_errorout('eval {{NS}} iptables {{table}} -A {{rule}}')

        def create_ebtable_rule_if_needed(table, chain, rule):
            if bash_r('ebtables -t {{table}} -L {{chain}} | grep -- "{{rule}}" > /dev/null') != 0:
                bash_errorout('ebtables -t {{table}} -A {{chain}} {{rule}}')

        def set_eip_rules():
            DNAT_NAME = "DNAT-{{VIP}}"
            if bash_r('eval {{NS}} iptables-save | grep -w ":{{DNAT_NAME}}" > /dev/null') != 0:
                bash_errorout('eval {{NS}} iptables -t nat -N {{DNAT_NAME}}')

            create_iptable_rule_if_needed("-t nat", 'PREROUTING -d {{VIP}}/32 -j {{DNAT_NAME}}')
            create_iptable_rule_if_needed("-t nat", '{{DNAT_NAME}} -j DNAT --to-destination {{NIC_IP}}')

            FWD_NAME = "FWD-{{VIP}}"
            if bash_r('eval {{NS}} iptables-save | grep -w ":{{FWD_NAME}}" > /dev/null') != 0:
                bash_errorout('eval {{NS}} iptables -N {{FWD_NAME}}')

            create_iptable_rule_if_needed("-t filter", "FORWARD ! -d {{NIC_IP}}/32 -i {{PUB_IDEV}} -j REJECT --reject-with icmp-port-unreachable")
            create_iptable_rule_if_needed("-t filter", "FORWARD -i {{PRI_IDEV}} -o {{PUB_IDEV}} -j {{FWD_NAME}}")
            create_iptable_rule_if_needed("-t filter", "-A FORWARD -i {{PUB_IDEV}} -o {{PRI_IDEV}} -j {{FWD_NAME}}")
            create_iptable_rule_if_needed("-t filter", "-A {{FWD_NAME}} -j ACCEPT")

            NAT_NAME = "SNAT-{{VIP}}"
            if bash_r('eval {{NS}} iptables-save | grep -w ":{{SNAT_NAME}}" > /dev/null ') != 0:
                bash_errorout('eval {{NS}} iptables -t nat -N {{SNAT_NAME}}')

            create_iptable_rule_if_needed("-t nat", "POSTROUTING -s {{NIC_IP}}/32 -j {{SNAT_NAME}}")
            create_iptable_rule_if_needed("-t nat", "-A {{SNAT_NAME}} -j SNAT --to-source {{VIP}}")

        def set_default_route_if_needed():
            if bash_r('eval {{NS}} ip route | grep -w default > /dev/null') != 0:
                bash_errorout('eval {{NS}} ip route add default via {{VIP_GW}}')

        def set_gateway_arp_if_needed():
            CHAIN_NAME = "{{NIC_NAME}}-gw"

            if bash_r('ebtables -t nat -L {{CHAIN_NAME}} > /dev/null 2>&1') != 0:
                bash_errorout('ebtables -t nat -N {{CHAIN_NAME}}')

            create_ebtable_rule_if_needed('nat', 'PREROUTING', '-i {{NIC_NAME}} -j {{CHAIN_NAME}}')
            GATEWAY = bash_o("eval {{NS}} ip link | grep -w {{PRI_IDEV}} -A 1 | awk '/link\/ether/{print $2}'")
            if not GATEWAY:
                raise Exception('cannot find the device[%s] in the namespace[%s]' % (PRI_IDEV, NS_NAME))

            create_ebtable_rule_if_needed('nat', CHAIN_NAME, "-p ARP --arp-op Request --arp-ip-dst {{NIC_GATEWAY}} -j arpreply --arpreply-mac {{GATEWAY}}")

            BLOCK_CHAIN_NAME = '{{PRI_ODEV}}-arp'
            if bash_r('ebtables -t nat -L {{BLOCK_CHAIN_NAME}} > /dev/null 2>&1') != 0:
                bash_errorout('ebtables -t nat -N {{BLOCK_CHAIN_NAME}}')

            create_ebtable_rule_if_needed('nat', 'POSTROUTING', "-p ARP -o {{PRI_ODEV}} -j {{BLOCK_CHAIN_NAME}}")
            create_ebtable_rule_if_needed('nat', BLOCK_CHAIN_NAME, "-p ARP -o {{PRI_ODEV}} --arp-op Request --arp-ip-dst {{NIC_GATEWAY}} --arp-mac-src ! {{NIC_MAC}} -j DROP")

        if bash_r('eval {{NS}} ip link show > /dev/null') != 0:
            bash_errorout('ip netns add {{NS_NAME}}')

        delete_orphan_outer_dev(PUB_IDEV, PUB_ODEV)
        delete_orphan_outer_dev(PRI_IDEV, PRI_ODEV)

        create_dev_if_needed(PUB_ODEV, PUB_IDEV)
        create_dev_if_needed(PRI_ODEV, PRI_IDEV)

        add_dev_to_br_if_needed(PUB_BR, PUB_ODEV)
        add_dev_to_br_if_needed(PRI_BR, PRI_ODEV)

        add_dev_namespace_if_needed(PUB_IDEV, NS_NAME)
        add_dev_namespace_if_needed(PRI_IDEV, NS_NAME)

        set_ip_to_idev_if_needed(PUB_IDEV, VIP, VIP_NETMASK)
        set_ip_to_idev_if_needed(PRI_IDEV, NIC_GATEWAY, NIC_NETMASK)

        # ping VIP gateway
        bash_r('eval {{NS}} arping -q -U -c 1 -I {{PUB_IDEV}} {{VIP_GW}} > /dev/null')

        set_gateway_arp_if_needed()
        set_eip_rules()
        set_default_route_if_needed()

    @lock.lock('eip')
    def _apply_eips(self, eips):
        for eip in eips:
            self._apply_eip(eip)

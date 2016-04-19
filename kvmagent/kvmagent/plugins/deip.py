from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import sizeunit
from zstacklib.utils import linux
from zstacklib.utils import thread
from zstacklib.utils import lock
import os.path
import re
import threading
import time
from jinja2 import Template

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

    @lock.lock('eip')
    def _delete_eips(self, eips):
        delete_eip_cmd = '''
PUB_ODEV={{pub_odev}}
NS_NAME="{{ns_name}}"

exit_on_error() {
    if [ $? -ne 0 ]; then
        echo "error on line $1"
        exit 1
    fi
}

ip netns | grep -w $NS_NAME > /dev/null
if [ $? -eq 0 ]; then
   ip netns delete $NS_NAME
   exit_on_error $LINENO
fi

ip link | grep -w $PUB_ODEV > /dev/null
if [ $? -eq 0 ]; then
    ip link del $PUB_ODEV
    exit_on_error $LINENO
fi

exit 0
'''
        for eip in eips:
            ctx = {
                "pub_odev": "%s_o" % eip.vip.replace(".", ""),
                "ns_name": "%s_%s" % (eip.publicBridgeName, eip.vip.replace(".", "_"))
            }
            ctx.update(eip.__dict__)
            tmpt = Template(delete_eip_cmd)
            cmd = tmpt.render(ctx)
            shell.call(cmd)

    @lock.lock('eip')
    def _apply_eips(self, eips):
        create_eip_cmd = '''
PUB_BR={{publicBridgeName}}
PUB_ODEV={{pub_odev}}
PUB_IDEV={{pub_idev}}
PRI_ODEV={{pri_odev}}
PRI_IDEV={{pri_idev}}
PRI_BR="{{vmBridgeName}}"
VIP="{{vip}}"
VIP_NETMASK="{{vipNetmask}}"
VIP_GW="{{vipGateway}}"
NIC_NAME="{{nicName}}"
NIC_GATEWAY="{{nicGateway}}"
NIC_NETMASK="{{nicNetmask}}"
NIC_IP={{nicIp}}
NS_NAME="{{ns_name}}"
EBTABLE_CHAIN_NAME={{ebtable_chain_name}}
PRI_BR_PHY_DEV={{pri_br_dev}}

NS="ip netns exec $NS_NAME"

exit_on_error() {
    if [ $? -ne 0 ]; then
        echo "error on line $1"
        exit 1
    fi
}

# in case the namespace deleted and the orphan outer link leaves in the system,
# deleting the orphan link and recreate it
delete_orphan_outer_dev() {
    ip netns exec $1 ip link | grep -w $2 > /dev/null
    if [ $? -ne 0 ]; then
        ip link del $3 &> /dev/null
    fi
}

create_dev_if_needed() {
    ip link | grep -w $1 > /dev/null
    if [ $? -ne 0 ]; then
        ip link add $1 type veth peer name $2
        exit_on_error $LINENO
    fi

    ip link set $1 up
    exit_on_error $LINENO
}

add_dev_to_br_if_needed() {
    brctl show $1 | grep -w $2 > /dev/null
    if [ $? -ne 0 ]; then
        brctl addif $1 $2
        exit_on_error $LINENO
    fi
}

add_dev_to_namespace_if_needed() {
    eval $NS ip link | grep -w $1 > /dev/null
    if [ $? -ne 0 ]; then
        ip link set $1 netns $2
        exit_on_error $LINENO
    fi
}

set_ip_to_idev_if_needed() {
    eval $NS ip addr show $1 | grep -w $2 > /dev/null
    if [ $? -ne 0 ]; then
        eval $NS ip addr flush dev $1
        exit_on_error $LINENO
        eval $NS ip addr add $2/$3 dev $1
        exit_on_error $LINENO
    fi

    eval $NS ip link set $1 up
    exit_on_error $LINENO
}

block_arp_for_NIC_GATEWAY() {
    local BR_PHY_DEV=$PRI_BR_PHY_DEV
    if [ x$BR_PHY_DEV == "x" ]; then
       echo "cannot find the physical interface of the bridge $PRI_BR"
       exit 1
    fi

    ebtables-save | grep -w ":$EBTABLE_CHAIN_NAME" > /dev/null
    if [ $? -ne 0 ]; then
        ebtables -N $EBTABLE_CHAIN_NAME
        ebtables -I FORWARD -j $EBTABLE_CHAIN_NAME
    fi

    ebtables-save | grep "$EBTABLE_CHAIN_NAME -p ARP -o $BR_PHY_DEV --arp-ip-dst $NIC_GATEWAY -j DROP" > /dev/null
    if [ $? -ne 0 ]; then
        ebtables -I $EBTABLE_CHAIN_NAME -p ARP -o $BR_PHY_DEV --arp-ip-dst $NIC_GATEWAY -j DROP
        exit_on_error $LINENO
    fi

    ebtables-save | grep "$EBTABLE_CHAIN_NAME -p ARP -i $BR_PHY_DEV --arp-ip-dst $NIC_GATEWAY -j DROP" > /dev/null
    if [ $? -ne 0 ]; then
        ebtables -I $EBTABLE_CHAIN_NAME -p ARP -i $BR_PHY_DEV --arp-ip-dst $NIC_GATEWAY -j DROP
        exit_on_error $LINENO
    fi
}

create_ip_table_rule_if_needed() {
   eval $NS iptables-save | grep -- "$2" > /dev/null
   if [ $? -ne 0 ]; then
       eval $NS iptables $1 $2
       exit_on_error $LINENO
   fi
}

set_eip_rules() {
    DNAT_NAME="DNAT-$VIP"
    eval $NS iptables-save | grep -w ":$DNAT_NAME" > /dev/null
    if [ $? -ne 0 ]; then
        eval $NS iptables -t nat -N $DNAT_NAME
        exit_on_error $LINENO
    fi

    create_ip_table_rule_if_needed "-t nat" "-A PREROUTING -d $VIP/32 -j $DNAT_NAME"
    create_ip_table_rule_if_needed "-t nat" "-A $DNAT_NAME -j DNAT --to-destination $NIC_IP"

    FWD_NAME="FWD-$VIP"
    eval $NS iptables-save | grep -w ":$FWD_NAME" > /dev/null
    if [ $? -ne 0 ]; then
        eval $NS iptables -N $FWD_NAME
        exit_on_error $LINENO
    fi

    create_ip_table_rule_if_needed "-t filter" "-A FORWARD -i $PRI_IDEV -o $PUB_IDEV -j $FWD_NAME"
    create_ip_table_rule_if_needed "-t filter" "-A FORWARD -i $PUB_IDEV -o $PRI_IDEV -j $FWD_NAME"
    create_ip_table_rule_if_needed "-t filter" "-A $FWD_NAME -j ACCEPT"

    SNAT_NAME="SNAT-$VIP"
    eval $NS iptables-save | grep -w ":$SNAT_NAME" > /dev/null
    if [ $? -ne 0 ]; then
        eval $NS iptables -t nat -N $SNAT_NAME
        exit_on_error $LINENO
    fi

    create_ip_table_rule_if_needed "-t nat" "-A POSTROUTING -s $NIC_IP/32 -j $SNAT_NAME"
    create_ip_table_rule_if_needed "-t nat" "-A $SNAT_NAME -j SNAT --to-source $VIP"
}

set_default_route_if_needed() {
    eval $NS ip route | grep -w default > /dev/null
    if [ $? -ne 0 ]; then
        eval $NS ip route add default via $VIP_GW
        exit_on_error $LINENO
    fi
}

eval $NS ip link show
if [ $? -ne 0 ]; then
    ip netns add $NS_NAME
    exit_on_error $LINENO
fi

delete_orphan_outer_dev $NS_NAME $PUB_IDEV $PUB_ODEV
delete_orphan_outer_dev $NS_NAME $PRI_IDEV $PRI_ODEV

create_dev_if_needed $PUB_ODEV $PUB_IDEV
create_dev_if_needed $PRI_ODEV $PRI_IDEV

add_dev_to_br_if_needed $PUB_BR $PUB_ODEV
add_dev_to_br_if_needed $PRI_BR $PRI_ODEV

add_dev_to_namespace_if_needed $PUB_IDEV $NS_NAME
add_dev_to_namespace_if_needed $PRI_IDEV $NS_NAME

set_ip_to_idev_if_needed $PUB_IDEV $VIP $VIP_NETMASK
set_ip_to_idev_if_needed $PRI_IDEV $NIC_GATEWAY $NIC_NETMASK

# ping VIP gateway
eval $NS arping -q -U -c 1 -I $PUB_IDEV $VIP_GW > /dev/null

block_arp_for_NIC_GATEWAY
set_eip_rules
set_default_route_if_needed

exit 0
'''

        for eip in eips:
            ctx = {
                "pub_odev": "%s_o" % eip.vip.replace(".", ""),
                "pub_idev": "%s_i" % eip.vip.replace(".", ""),
                "pri_odev": "%s_o" % eip.nicIp.replace(".", ""),
                "pri_idev": "%s_i" % eip.nicIp.replace(".", ""),
                "pri_br_dev": eip.vmBridgeName.lstrip('br_'),
                "ebtable_chain_name": eip.vmBridgeName,
                "ns_name": "%s_%s" % (eip.publicBridgeName, eip.vip.replace(".", "_"))
            }
            ctx.update(eip.__dict__)
            tmpt = Template(create_eip_cmd)
            cmd = tmpt.render(ctx)
            shell.call(cmd)

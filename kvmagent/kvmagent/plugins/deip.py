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

class DEip(kvmagent.KvmAgent):

    APPLY_EIP_PATH = "/flatnetworkprovider/eip/apply"
    DELETE_EIP_PATH = "/flatnetworkprovider/eip/delete"
    BATCH_APPLY_EIP_PATH = "/flatnetworkprovider/eip/batchapply"
    BATCH_DELETE_EIP_PATH = "/flatnetworkprovider/eip/batchdelete"

    def start(self):
        pass

    def stop(self):
        pass

    def _apply_eips(self, eips):
        create_eip_cmd = '''
PUB_BR={{publicBridgeName}}
OUTER_DEV={{odev}}
INNER_DEV={{idev}}
BR_NAME="{{vmBridgeName}}"
VIP="{{vip}}"
VIP_NETMASK="{{vipNetmask}}"
VIP_GW="{{vipGateway}}"
VM_NIC="{{nicName}}"

exit_on_error() {
    [ $? -ne 0 ] && exit 1
}

exit_on_error_with_msg() {
    [ $? -ne 0 ] && exit 1
    exit 1
}

ip netns exec $BR_NAME ip link show
exit_on_error_with_msg "cannot find the namespace $BR_NAME"

# in case the namespace deleted and the orphan outer link leaves in the system,
# deleting the orphan link and recreate it
ip netns exec $$BR_NAME ip link | grep $INNER_DEV > /dev/null
if [ $? -ne 0 ]; then
   ip link del $OUTER_DEV &> /dev/null
fi

ip link | grep $OUTER_DEV > /dev/null
if [ $? -ne 0 ]; then
    ip link add $OUTER_DEV type veth peer name $INNER_DEV
    exit_on_error
fi

ip link set $OUTER_DEV up
exit_on_error

# add the outter ethdev to the public bridge
brctl show $PUB_BR | grep $OUTER_DEV > /dev/null
if [ $? -ne 0 ]; then
    brctl addif $PUB_BR $OUTER_DEV
    exit_on_error
fi

NS="ip netns exec $BR_NAME"

# add the inner ethdev to the namespace
eval $NS ip link | grep $INNER_DEV > /dev/null
if [ $? -ne 0 ]; then
    ip link set $INNER_DEV netns $BR_NAME
    exit_on_error
fi

# set VIP to the inner dev
eval $NS ip addr show $INNER_DEV | grep $DHCP_IP > /dev/null
if [ $? -ne 0 ]; then
    eval $NS ip addr flush dev $INNER_DEV
    exit_on_error
    eval $NS ip addr add $VIP/$VIP_NETMASK dev $INNER_DEV
    exit_on_error
fi

# set the inner dev up
eval $NS ip link set $INNER_DEV up
exit_on_error

# ping VIP gateway
eval $NS arping -q -U -c 1 -I $INNER_DEV $VIP_GW > /dev/null

DNAT_NAME="DNAT-$VIP"
eval $NS iptables-save | grep "$DNAT_NAME" > /dev/null
if [ $? -ne 0 ]; then
    eval $NS iptables -N $DNAT_NAME
    eval $NS iptables -t nat -I PREROUTING -d $VIP -j $DNAT_NAME
fi

FWD_NAME="FWD-$VIP"
eval $NS iptables-save | grep "$FWD_NAME" > /dev/null
if [ $? -ne 0 ]; then
    eval $NS iptables -N $FWD_NAME
    eval $NS iptables -I PREROUTING -d $VIP -j $DNAT_NAME
fi

exit 0
'''

        for eip in eips:
            ctx = {
                "odev": "%s_o" % eip.vip.replace(".", ""),
                "idev": "%s_i" % eip.vip.replace(".", ""),
            }
            ctx.update(eip.__dict__)
            tmpt = Template(create_eip_cmd)
            cmd = tmpt.render(ctx)
            shell.call(cmd)

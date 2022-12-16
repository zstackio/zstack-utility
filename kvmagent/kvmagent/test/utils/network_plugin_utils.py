from zstacklib.test.utils import env, misc
from zstacklib.utils import linux, jsonobject, bash
from kvmagent.plugins.network_plugin import NetworkPlugin
from common_util import checkParamNotNone

NETWORK_PLUGIN = None


def init_network_plugin():
    global NETWORK_PLUGIN
    if NETWORK_PLUGIN is not None:
        return NETWORK_PLUGIN

    NETWORK_PLUGIN = NetworkPlugin()


checkPhysicalNetworkInterface = {
    "interfaceNames": []
}

def create_request_body_jsonobject(struct=None):
    # type: () -> jsonobject.JsonObject

    return jsonobject.loads(jsonobject.dumps(struct))

@checkParamNotNone
def check_physical_network_interface(interfaces=None):
    return NETWORK_PLUGIN.check_physical_network_interface(
        misc.make_a_request({
            "interfaceNames": interfaces
        })
    )

@checkParamNotNone
def add_interface_to_bridge(physicalInterfaceName=None, bridgeName=None):
    return NETWORK_PLUGIN.add_interface_to_bridge(
        misc.make_a_request({
            "physicalInterfaceName": physicalInterfaceName,
            "bridgeName": bridgeName
        })
    )

@checkParamNotNone
def create_bridge(physicalInterfaceName=None, mtu=None, l2NetworkUuid=None, disableIptables=False, bridgeName=None):
    return NETWORK_PLUGIN.create_bridge(
        misc.make_a_request({
            "physicalInterfaceName": physicalInterfaceName,
            "mtu": mtu,
            "l2NetworkUuid": l2NetworkUuid,
            "disableIptables": disableIptables,
            "bridgeName": bridgeName
        })
    )

@checkParamNotNone
def create_vlan_bridge(physicalInterfaceName=None, mtu=None, l2NetworkUuid=None, disableIptables=False, bridgeName=None, vlan=None, vlanInterfName=None):
    return NETWORK_PLUGIN.create_vlan_bridge(
        misc.make_a_request({
            "physicalInterfaceName": physicalInterfaceName,
            "mtu": mtu,
            "l2NetworkUuid": l2NetworkUuid,
            "disableIptables": disableIptables,
            "bridgeName": bridgeName,
            "vlan": vlan,
            "vlanInterfName": vlanInterfName
        })
    )

@checkParamNotNone
def check_bridge(bridgeName=None, physicalInterfaceName=None):
    return NETWORK_PLUGIN.check_bridge(
        misc.make_a_request({
            "bridgeName": bridgeName,
            "physicalInterfaceName": physicalInterfaceName
        })
    )
@checkParamNotNone
def check_vlan_bridge(bridgeName=None, physicalInterfaceName=None):
    return NETWORK_PLUGIN.check_bridge(
        misc.make_a_request({
            "bridgeName": bridgeName,
            "physicalInterfaceName": physicalInterfaceName
        })
    )

@checkParamNotNone
def check_vxlan_cidr(physicalInterfaceName=None, cidr=None, vtepip=None):
    return NETWORK_PLUGIN.check_vxlan_cidr(
        misc.make_a_request({
            "physicalInterfaceName": physicalInterfaceName,
            "cidr": cidr,
            "vtepip": vtepip
        })
    )

@checkParamNotNone
def create_vxlan_bridge(bridgeName=None, vtepIp=None, vni=None, dstport=None, l2NetworkUuid=None, peers=None,mtu=None):
    return NETWORK_PLUGIN.create_vxlan_bridge(
        misc.make_a_request({
            "bridgeName": bridgeName,
            "vtepIp": vtepIp,
            "vni": vni,
            "dstport": dstport ,
            "l2NetworkUuid": l2NetworkUuid,
            "peers": peers,
            "mtu" :mtu# []string
        })
    )

@checkParamNotNone
def create_vxlan_bridges(bridgeCmds=None):
    return NETWORK_PLUGIN.create_vxlan_bridge(
        misc.make_a_request({
            "bridgeCmds": bridgeCmds
            # "bridgeName": cmd.bridgeName,
            # "vtepIp": cmd.vtepIp,
            # "vni": cmd.vni,
            # "dstport": cmd.dstport,
            # "l2NetworkUuid": cmd.l2NetworkUuid,
            # "peers": cmd.peers,  # []string
            # "bridgeName": cmd.bridgeName
        })
    )

@checkParamNotNone
def delete_vxlan_bridge(bridgeName=None, vtepIp=None, vni=None):
    return NETWORK_PLUGIN.delete_vxlan_bridge(
        misc.make_a_request({
            "bridgeName": bridgeName,
            "vtepIp": vtepIp,
            "vni": vni,
        })
    )

@checkParamNotNone
def populate_vxlan_fdb(peers=None, vni=None):
    return NETWORK_PLUGIN.populate_vxlan_fdb(
        misc.make_a_request({
            "peers": peers, #[] string
            "vni": vni
        })
    )


@checkParamNotNone
def populate_vxlan_fdbs(networkUuids=None, peers=None):
    return NETWORK_PLUGIN.populate_vxlan_fdb(
        misc.make_a_request({
            "networkUuids": networkUuids, #[] string
            "peers": peers
        })
    )

@checkParamNotNone
def set_bridge_router_port(enable=False, nicNames=None):
    return NETWORK_PLUGIN.set_bridge_router_port(
        misc.make_a_request({
            "enable": enable,
            "nicNames": nicNames # []string
        })
    )

@checkParamNotNone
def delete_novlan_bridge(bridgeName=None, physicalInterfaceName=None):
    return NETWORK_PLUGIN.delete_novlan_bridge(
        misc.make_a_request({
            "bridgeName": bridgeName,
            "physicalInterfaceName": physicalInterfaceName
        })
    )

@checkParamNotNone
def delete_vxlan_bridge(vni=None, vtepIp=None, bridgeName=None):
    return NETWORK_PLUGIN.delete_vxlan_bridge(
        misc.make_a_request({
            "vni": vni,
            "vtepIp": vtepIp,
            "bridgeName": bridgeName
        })
    )



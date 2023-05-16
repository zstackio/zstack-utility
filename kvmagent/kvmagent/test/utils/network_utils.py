from zstacklib.test.utils import env, misc
from zstacklib.utils import linux, jsonobject, bash
from kvmagent.plugins import mevoco

MEVOCO_PLUGIN = None  # type: mevoco.Mevoco


def init_mevoco_plugin():
    global MEVOCO_PLUGIN
    if MEVOCO_PLUGIN is not None:
        return MEVOCO_PLUGIN

    MEVOCO_PLUGIN = mevoco.Mevoco()
    MEVOCO_PLUGIN.configure({})
    MEVOCO_PLUGIN.start()


def create_default_bridge_if_not_exist(eth_name=None):
    if eth_name is None:
        eth_name = env.DEFAULT_ETH_INTERFACE_NAME

    br_name = 'br_%s' % eth_name
    linux.create_bridge(br_name, eth_name)
    return br_name


def close_firewall():
    bash.call_with_screen_output('iptables -F')


batch_apply_dhcp_cmd_body = {
    "dhcpInfos": [{
        "dhcp": [{
            "ipVersion": 4,
            "ip": "10.0.1.183",
            "mac": None,  # must fill
            "netmask": "255.255.255.0",
            "gateway": "10.0.1.1",
            "hostname": "10-0-1-183",
            "isDefaultL3Network": True,
            "dns": ["223.5.5.5"],
            "bridgeName": None,  # must fill
            "namespaceName": None,  # must fill
            "l3NetworkUuid": "af332aa8911248e98a54b304335b963a",
            "mtu": 1500,
            "vmMultiGateway": False,
            "hostRoutes": [{
                "prefix": "169.254.169.254/32",
                "nexthop": "10.0.1.210"
            }]
        }],
        "rebuild": False,
        "l3NetworkUuid": "af332aa8911248e98a54b304335b963a"
    }],
    "kvmHostAddons": {
        "qcow2Options": " -o cluster_size=2097152 "
    }
}

batch_prepare_dhcp_cmd_body = {
    "dhcpInfos": [{
        "bridgeName": None,  # must fill
        "dhcpServerIp": "10.0.1.210",
        "dhcpNetmask": "255.255.255.0",
        "namespaceName": None,  # must fill
        "ipVersion": 4
    }],
    "kvmHostAddons": {
        "qcow2Options": " -o cluster_size=2097152 "
    }
}


@misc.return_jsonobject()
def apply_dhcp_by_batch_cmd(vm_mac, bridge_name, namespace_name):
    # type: (str, str, str) -> jsonobject.JsonObject

    cmd = jsonobject.from_dict(batch_apply_dhcp_cmd_body)
    dhcp_info = cmd.dhcpInfos[0].dhcp[0]
    dhcp_info.mac = vm_mac
    dhcp_info.bridgeName = bridge_name
    dhcp_info.namespaceName = namespace_name

    return MEVOCO_PLUGIN.batch_apply_dhcp(misc.make_a_request(cmd.to_dict()))


@misc.return_jsonobject()
def prepare_dhcp_by_batch_cmd(bridge_name, namespace_name):
    # type: (str, str) -> jsonobject.JsonObject

    cmd = jsonobject.from_dict(batch_prepare_dhcp_cmd_body)
    info = cmd.dhcpInfos[0]
    info.bridgeName = bridge_name
    info.namespaceName = namespace_name

    return MEVOCO_PLUGIN.batch_prepare_dhcp(misc.make_a_request(cmd.to_dict()))

@misc.return_jsonobject()
def delete_dhcp(bridge_name, namespace_name):
    # type: (str, str) -> jsonobject.JsonObject

    cmd = jsonobject.from_dict(delete_dhcp_cmd_body)
    cmd.bridgeName = bridge_name
    cmd.namespaceName = namespace_name

    return MEVOCO_PLUGIN.delete_dhcp_namespace(misc.make_a_request(cmd.to_dict()))


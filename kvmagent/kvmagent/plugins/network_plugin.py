'''

@author: frank
'''
import copy
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import lock
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import iproute
from zstacklib.utils import iptables_v2
from zstacklib.utils.bash import *
from zstacklib.utils import ovs
from jinja2 import Template
import os
import traceback
import netaddr
import subprocess
import json

CHECK_PHYSICAL_NETWORK_INTERFACE_PATH = '/network/checkphysicalnetworkinterface'
ADD_INTERFACE_TO_BRIDGE_PATH = '/network/bridge/addif'
CREATE_BONDING_PATH = '/network/bonding/create'
UPDATE_BONDING_PATH = '/network/bonding/update'
DELETE_BONDING_PATH = '/network/bonding/delete'
ATTACH_NIC_TO_BONDING_PATH = '/network/bonding/attachnic'
DETACH_NIC_FROM_BONDING_PATH = '/network/bonding/detachnic'
KVM_CHANGE_LLDP_MODE_PATH = '/network/lldp/changemode'
KVM_GET_LLDP_INFO_PATH = '/network/lldp/get'
KVM_APPLY_LLDP_CONFIG_PATH = '/network/lldp/apply'
KVM_UPDATE_L2VLAN_NETWORK_PATH = "/network/l2vlan/updatebridge"
KVM_UPDATE_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/updatebridge"
KVM_REALIZE_L2NOVLAN_NETWORK_PATH = "/network/l2novlan/createbridge"
KVM_REALIZE_L2VLAN_NETWORK_PATH = "/network/l2vlan/createbridge"
KVM_CHECK_L2NOVLAN_NETWORK_PATH = "/network/l2novlan/checkbridge"
KVM_CHECK_L2VLAN_NETWORK_PATH = "/network/l2vlan/checkbridge"
KVM_CHECK_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/checkcidr"
KVM_REALIZE_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/createbridge"
KVM_REALIZE_L2VXLAN_NETWORKS_PATH = "/network/l2vxlan/createbridges"
KVM_POPULATE_FDB_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/populatefdb"
KVM_POPULATE_FDB_L2VXLAN_NETWORKS_PATH = "/network/l2vxlan/populatefdbs"
KVM_CHECK_MACVLAN_L2VLAN_NETWORK_PATH = "/network/l2vlan/macvlan/checkbridge"
KVM_REALIZE_MACVLAN_L2VLAN_NETWORK_PATH = "/network/l2vlan/macvlan/createbridge"
KVM_DELETE_FDB_L2VXLAN_NETWORKS_PATH = "/network/l2vxlan/deletefdbs"
KVM_SET_BRIDGE_ROUTER_PORT_PATH = "/host/bridge/routerport"
KVM_DELETE_L2NOVLAN_NETWORK_PATH = "/network/l2novlan/deletebridge"
KVM_DELETE_L2VLAN_NETWORK_PATH = "/network/l2vlan/deletebridge"
KVM_DELETE_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/deletebridge"
KVM_DELETE_MACVLAN_L2VLAN_NETWORK_PATH = "/network/l2vlan/macvlan/deletebridge"
KVM_IPSET_ATTACH_NIC_PATH = "/network/ipset/attach"
KVM_IPSET_DETACH_NIC_PATH = "/network/ipset/detach"
KVM_IPSET_SYNC_PATH = "/network/ipset/sync"
VXLAN_DEFAULT_PORT = 8472

PVLAN_ISOLATED_CHAIN = "pvlan-isolated"
PVLAN_ISOLATED_CHAIN_V6 = "pvlan-isolated-v6"
IPV4 = 4
IPV6 = 6

logger = log.get_logger(__name__)


class DeviceNotExistedError(Exception):
    pass


class CheckPhysicalNetworkInterfaceCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CheckPhysicalNetworkInterfaceCmd, self).__init__()
        self.interfaceNames = None


class CheckPhysicalNetworkInterfaceResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckPhysicalNetworkInterfaceResponse, self).__init__()
        self.failedInterfaceNames = None


class CreateBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CreateBridgeCmd, self).__init__()
        self.physicalInterfaceName = None
        self.bridgeName = None
        self.l2NetworkUuid = None
        self.disableIptables = None
        self.mtu = 0


class CreateBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateBridgeResponse, self).__init__()


class CreateVlanBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CreateVlanBridgeCmd, self).__init__()
        self.vlan = None


class CheckVxlanCidrCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CheckVxlanCidrCmd, self).__init__()
        self.vtepIp = None


class CreateVxlanBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CreateVxlanBridgeCmd, self).__init__()
        self.bridgeName = None
        self.vtepIp = None
        self.vni = None
        self.peers = None
        self.dstport = None


class CreateVxlanBridgesCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CreateVxlanBridgesCmd, self).__init__()
        self.bridgeNames = None
        self.vtepIp = None
        self.vnis = None
        self.peers = None


class PopulateVxlanFdbCmd(kvmagent.AgentResponse):
    def __init__(self):
        super(PopulateVxlanFdbCmd, self).__init__()
        self.interf = None
        self.peers = None


class DeleteVxlanFdbCmd(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteVxlanFdbCmd, self).__init__()
        self.interf = None
        self.peers = None


class CheckBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckBridgeResponse, self).__init__()


class CheckVlanBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckVlanBridgeResponse, self).__init__()


class CreateVlanBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateVlanBridgeResponse, self).__init__()


class CheckVxlanCidrResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckVxlanCidrResponse, self).__init__()
        self.vtepIp = None
        self.physicalInterfaceName = None


class CreateVxlanBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateVxlanBridgeResponse, self).__init__()


class CreateVxlanBridgesResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateVxlanBridgesResponse, self).__init__()


class PopulateVxlanFdbResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(PopulateVxlanFdbResponse, self).__init__()


class DeleteVxlanFdbResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteVxlanFdbResponse, self).__init__()


class SetBridgeRouterPortResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SetBridgeRouterPortResponse, self).__init__()


class DeleteBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteBridgeCmd, self).__init__()
        self.physicalInterfaceName = None
        self.bridgeName = None
        self.l2NetworkUuid = None


class DeleteBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteBridgeResponse, self).__init__()


class DeleteVlanBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteVlanBridgeCmd, self).__init__()
        self.vlan = None


class DeleteVlanBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteVlanBridgeResponse, self).__init__()


class DeleteVxlanBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteVxlanBridgeCmd, self).__init__()
        self.bridgeName = None
        self.vtepIp = None
        self.vni = None
        self.peers = None


class DeleteVxlanBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteVxlanBridgeResponse, self).__init__()


class CreateBondingCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CreateBondingCmd, self).__init__()
        self.bondName = None
        self.slaves = None  # type: list[HostNetworkInterfaceStruct]
        self.type = None
        self.mode = None
        self.xmitHashPolicy = None


class CreateBondingResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateBondingResponse, self).__init__()


class UpdateBondingCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(UpdateBondingCmd, self).__init__()
        self.bondName = None
        self.oldSlaves = None  # type: list[HostNetworkInterfaceStruct]
        self.slaves = None  # type: list[HostNetworkInterfaceStruct]
        self.mode = None
        self.xmitHashPolicy = None


class UpdateBondingResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateBondingResponse, self).__init__()


class DeleteBondingCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteBondingCmd, self).__init__()
        self.bondName = None


class DeleteBondingResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteBondingResponse, self).__init__()


class AttachNicToBondCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(AttachNicToBondCmd, self).__init__()
        self.bondName = None
        self.slaves = None  # type: list[HostNetworkInterfaceStruct]


class AttachNicToBondResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(AttachNicToBondResponse, self).__init__()


class DetachNicFromBondCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DetachNicFromBondCmd, self).__init__()
        self.bondName = None
        self.slaves = None  # type: list[HostNetworkInterfaceStruct]


class DetachNicFromBondResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DetachNicFromBondResponse, self).__init__()


class ChangeLldpModeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ChangeLldpModeCmd, self).__init__()
        self.physicalInterfaceNames = None
        self.mode = None

class ChangeLldpModeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ChangeLldpModeResponse, self).__init__()

class GetLldpInfoCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetLldpInfoCmd, self).__init__()
        self.physicalInterfaceName = None

class GetLldpInfoResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetLldpInfoResponse, self).__init__()
        self.lldpInfo = None  # type: HostNetworkInterfaceLldpStruct

class ApplyLldpConfigCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ApplyLldpConfigCmd, self).__init__()
        self.lldpConfig = None # type: list[HostNetworkLldpConfigureStruct]

class ApplyLldpConfigResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ApplyLldpConfigResponse, self).__init__()

class HostNetworkInterfaceLldpStruct(object):
    def __init__(self):
        self.chassisId = None
        self.timeToLive = None
        self.managementAddress = None
        self.systemName = None
        self.systemDescription = None
        self.systemCapabilities = None
        self.portId = None
        self.portDescription = None
        self.vlanId = None
        self.linkAggregation = None
        self.aggregationPortId = None
        self.mtu = None

class HostNetworkLldpConfigStruct(object):
    def __init__(self):
        self.physicalInterfaceName = None
        self.mode = None

class HostNetworkInterfaceStruct(object):
    def __init__(self):
        self.interfaceName = None
        self.speed = None
        self.slaveActive = None
        self.carrierActive = None
        self.mac = None
        self.ipAddresses = None
        self.interfaceType = None
        self.master = None
        self.pciDeviceAddress = None
        self.offloadStatus = None


def del_novlan_bridge(cmd):
    linux.delete_novlan_bridge(cmd.bridgeName, cmd.physicalInterfaceName)
    logger.debug('successfully delete bridge[%s] with physical interface[%s]' % (
        cmd.bridgeName, cmd.physicalInterfaceName))


class NetworkPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    def _ifup_device_if_down(self, device_name):
        state_path = '/sys/class/net/%s/operstate' % device_name

        if not os.path.exists(state_path):
            raise DeviceNotExistedError('cannot find %s' % state_path)

        with open(state_path, 'r') as fd:
            state = fd.read()

        if 'up' in state:
            return

        iproute.set_link_up(device_name)

    def _ifdown_device_if_up(self, device_name):
        state_path = '/sys/class/net/%s/operstate' % device_name

        if not os.path.exists(state_path):
            raise DeviceNotExistedError('cannot find %s' % state_path)

        with open(state_path, 'r') as fd:
            state = fd.read()

        if 'down' in state:
            return

        iproute.set_link_down(device_name)

    def modifySysConfiguration(self, name, old_value, new_value):
        sysconf_path = "/etc/sysctl.conf"
        if not os.path.exists(sysconf_path):
            return False
        all_lines = linux.read_file_lines(sysconf_path)
        old_value_str = str(old_value)
        new_value_str = str(new_value)
        new_str = name + " = " + new_value_str
        for line in all_lines:
            strs = line.strip().split(" = ")
            if len(strs) == 2 and strs[0] == name:
                if strs[1] != new_value_str:
                    line.replace(old_value_str, new_value_str)
                    all_lines = "".join(all_lines)
                    if linux.write_file(sysconf_path, all_lines) == None:
                        return False
                    return True
                else:
                    return True
        all_lines = "".join(all_lines) + new_str + "\n"
        if linux.write_file(sysconf_path, all_lines) == None:
            return False
        return True

    def _configure_bridge(self, disableIptables):
        shell.call('modprobe br_netfilter || true')
        if disableIptables:
            self.modifySysConfiguration("net.bridge.bridge-nf-call-iptables", 1, 0)
            self.modifySysConfiguration("net.bridge.bridge-nf-call-ip6tables", 1, 0)
        else:
            self.modifySysConfiguration("net.bridge.bridge-nf-call-iptables", 0, 1)
            self.modifySysConfiguration("net.bridge.bridge-nf-call-ip6tables", 0, 1)
        linux.write_file('/proc/sys/net/bridge/bridge-nf-call-iptables', '0' if disableIptables else '1')
        linux.write_file('/proc/sys/net/bridge/bridge-nf-call-ip6tables', '0' if disableIptables else '1')
        linux.write_file('/proc/sys/net/bridge/bridge-nf-filter-vlan-tagged', '1')
        linux.write_file('/proc/sys/net/ipv4/conf/default/forwarding', '1')
        linux.write_file('/proc/sys/net/ipv6/conf/default/forwarding', '1')

    def _get_interface_mtu(self, interf):
        try:
            link = iproute.query_link(interf)
            return link.mtu
        except Exception as e:
            logger.debug("get mtu of link: %s failed: %s", interf, str(e))
            return 0

    @in_bash
    def _configure_bridge_mtu(self, bridgeName, interf, mtu=None):
        if mtu is not None:
            try:
                iproute.set_link_attribute(interf, mtu=mtu)
            except Exception as e:
                raise Exception('failed to configure bridge mtu, '
                                'please check if mtu exceeds the maximum value of all vnic mtus and global property, '
                                'the details:%s', str(e))
            # bridge mtu must be bigger than all vnic mtu, so will not change it
            # if bridgeName is not None:
            #    shell.call("ip link set mtu %d dev %s" % (mtu, bridgeName))

    def _configure_bridge_learning(self, bridgeName, interf, learning='on'):
        shell.call("bridge link set dev %s learning %s" % (interf, learning), False)

    def _configure_isolated(self, vlan_interface):
        isolated_br = "isolated_%s" % vlan_interface
        cmd = shell.ShellCmd("ipset list %s" % isolated_br)
        cmd(False)
        if cmd.return_code != 0:
            shell.call("ipset create %s hash:mac" % isolated_br)
        filter_table = iptables_v2.from_iptables_save()
        forward_chain = filter_table.get_chain_by_name(iptables_v2.FORWARD_CHAIN_NAME)
        pvlan_isolated_chain = filter_table.get_chain_by_name(PVLAN_ISOLATED_CHAIN)
        if not pvlan_isolated_chain:
            pvlan_isolated_chain = filter_table.add_chain_if_not_exist(PVLAN_ISOLATED_CHAIN)
            forward_chain.add_rule('-I FORWARD -j %s' % PVLAN_ISOLATED_CHAIN)
        pvlan_isolated_chain.add_rule('-I %s -m physdev --physdev-in %s -m set --match-set %s src -j DROP' % (
            PVLAN_ISOLATED_CHAIN, vlan_interface, isolated_br))
        filter_table.iptables_restore()
        filter_table_v6 = iptables_v2.from_iptables_save(version=IPV6)
        forward_chain_v6 = filter_table_v6.get_chain_by_name(iptables_v2.FORWARD_CHAIN_NAME)
        pvlan_isolated_chain_v6 = filter_table_v6.get_chain_by_name(PVLAN_ISOLATED_CHAIN_V6)
        if not pvlan_isolated_chain_v6:
            pvlan_isolated_chain_v6 = filter_table_v6.add_chain_if_not_exist(PVLAN_ISOLATED_CHAIN_V6)
            forward_chain_v6.add_rule('-I FORWARD -j %s' % PVLAN_ISOLATED_CHAIN_V6)
        pvlan_isolated_chain_v6.add_rule('-I %s -m physdev --physdev-in %s -m set --match-set %s src -j DROP' % (
            PVLAN_ISOLATED_CHAIN_V6, vlan_interface, isolated_br))
        filter_table_v6.iptables_restore()

    def _delete_isolated(self, vlan_interface):
        isolated_br = "isolated_%s" % vlan_interface
        cmd = shell.ShellCmd("ipset list %s" % isolated_br)
        cmd(False)
        if cmd.return_code == 0:
            filter_table = iptables_v2.from_iptables_save()
            pvlan_isolated_chain = filter_table.get_chain_by_name(PVLAN_ISOLATED_CHAIN)
            if pvlan_isolated_chain:
                pvlan_isolated_chain.add_rule('-D %s -m physdev --physdev-in %s -m set --match-set %s src -j DROP' % (
                    PVLAN_ISOLATED_CHAIN, vlan_interface, isolated_br))
                filter_table.iptables_restore()
            filter_table_v6 = iptables_v2.from_iptables_save(version=IPV6)
            pvlan_isolated_chain_6 = filter_table_v6.get_chain_by_name(PVLAN_ISOLATED_CHAIN_V6)
            if pvlan_isolated_chain_6:
                pvlan_isolated_chain_6.add_rule('-D %s -m physdev --physdev-in %s -m set --match-set %s src -j DROP' % (
                    PVLAN_ISOLATED_CHAIN_V6, vlan_interface, isolated_br))
                filter_table_v6.iptables_restore()
            shell.call("ipset destroy %s" % isolated_br)

    def _configure_pvlan_veth(self, pvlan, bridge):
        if "pvlan://" not in pvlan:
            logger.debug("Error: Invalid pvlan format. 'pvlan://' not found.")
            return
        pvlan_id = pvlan.replace("pvlan://", "")
        pvlan_parts = pvlan_id.split("-")
        if len(pvlan_parts) != 2:
            logger.debug("Error: Invalid pvlan format. Expected format: 'primary-secondary'.")
            return
        pvlan_pri = pvlan_parts[0]
        pvlan_sec = pvlan_parts[1]
        if not pvlan_sec:
            logger.debug("Error: Invalid secondary pvlan value.")
            return
        pvlan_type = pvlan_sec[0]
        master_br = bridge.replace(pvlan_sec, pvlan_pri)
        if 'p' in pvlan_type:
            shell.call("ipset create %s hash:mac" % pvlan)
            return
        if 'i' in pvlan_type or 'c' in pvlan_type:
            veth = "v_p%s_%s" % (pvlan_pri, pvlan_sec)
            veth_peer = "v_%s_p%s" % (pvlan_pri, pvlan_sec)
            iproute.add_link(veth, 'veth', peer=veth_peer)
            shell.call("ip link set %s master %s" % (veth, master_br))
            shell.call("ip link set %s master %s" % (veth_peer, bridge))
            self._ifup_device_if_down(veth)
            self._ifup_device_if_down(veth_peer)
            shell.call("ipset create %s hash:mac" % pvlan)
            return
        logger.debug("Error: Unknown pvlan type.")

    @kvmagent.replyerror
    def check_physical_network_interface(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckPhysicalNetworkInterfaceResponse()
        for i in cmd.interfaceNames:
            if not linux.is_network_device_existing(i) and ovs.OvsDpdkCtl.getBondFromFile(i) is None:
                rsp.failedInterfaceNames = [i]
                rsp.success = False
                return jsonobject.dumps(rsp)

        for i in cmd.interfaceNames:
            if ovs.OvsDpdkCtl.getBondFromFile(i) is None:
                self._ifup_device_if_down(i)

        logger.debug(http.path_msg(CHECK_PHYSICAL_NETWORK_INTERFACE_PATH,
                                   'checked physical interfaces: %s' % cmd.interfaceNames))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def add_interface_to_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        oldbr = shell.call("""brctl show | awk '$4 == "%s" {print $1}'""" % cmd.physicalInterfaceName).strip()
        if oldbr == cmd.bridgeName:
            return jsonobject.dumps(rsp)

        if oldbr:
            shell.run("brctl delif %s %s" % (oldbr, cmd.physicalInterfaceName))
        shell.check_run("brctl addif %s %s" % (cmd.bridgeName, cmd.physicalInterfaceName))
        return jsonobject.dumps(rsp)

    def _has_vlan_or_bridge(self, ifname):
        if linux.is_bridge_slave(ifname):
            return True

        vlan_dev_name = '%s.' % ifname
        output = subprocess.check_output(['ip', 'link', 'show', 'type', 'vlan'], universal_newlines=True)
        for line in output.split('\n'):
            if vlan_dev_name in line:
                return True

        return False

    def _add_interface_to_collectd_conf(self, config_file, interface_name):
        with open(config_file, 'r') as f:
            config_lines = f.readlines()

        new_line = 'Interface "{}"\n'.format(interface_name)
        start_index = config_lines.index('<Plugin "interface">\n')
        end_index = config_lines.index('</Plugin>\n', start_index)
        config_lines.insert(end_index, new_line)

        with open(config_file, 'w') as f:
            f.writelines(config_lines)

    def _remove_interface_from_collectd_conf(self, config_file, interface_name):
        with open(config_file, 'r') as f:
            config_lines = f.readlines()

        for i, line in enumerate(config_lines):
            if line.strip() == 'Interface "{}"'.format(interface_name):
                del config_lines[i]
                break

        with open(config_file, 'w') as f:
            f.writelines(config_lines)

    def _restart_collectd(self, config_file):
        cpid = linux.find_process_by_command('collectd', [config_file])
        mpid = linux.find_process_by_command('collectdmon', [config_file])

        if not cpid:
            bash_errorout('collectdmon -- -C %s' % config_file)
        else:
            bash_errorout('kill -TERM %s' % cpid)
            if not mpid:
                bash_errorout('collectdmon -- -C %s' % config_file)
            else:
                bash_errorout('kill -HUP %s' % mpid)

    @lock.lock('bonding')
    @kvmagent.replyerror
    @in_bash
    def create_bonding(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBondingResponse()

        try:
            try:
                for slave in cmd.slaves:
                    if self._has_vlan_or_bridge(slave.interfaceName):
                        raise Exception(slave.interfaceName + ' has a sub-interface or a bridge port')
            except Exception as e:
                rsp.error = 'unable to create bonding[%s], because %s' % (cmd.bondName, str(e))
                rsp.success = False
                return jsonobject.dumps(rsp)

            # zs-bond -c bond1 mode 802.ad xmitHashPolicy layer2+3
            if cmd.xmitHashPolicy is not None:
                shell.call('/usr/local/bin/zs-bond -c %s mode %s xmit_hash_policy %s' % (
                    cmd.bondName, cmd.mode, cmd.xmitHashPolicy))
            else:
                # zs-bond -c bond1 mode active-backup
                shell.call('/usr/local/bin/zs-bond -c %s mode %s' % (cmd.bondName, cmd.mode))

            # take the mtu of the smallest interface as the mtu of the bond
            min_mtu = 1500
            for slave in cmd.slaves:
                mtu = self._get_interface_mtu(slave.interfaceName)
                if mtu < min_mtu:
                    min_mtu = mtu

            # zs-bond -u mtu 1450
            shell.call('/usr/local/bin/zs-bond -u %s mtu %s' % (cmd.bondName, min_mtu))

            # zs-nic-to-bond -a bond2 nic3
            for slave in cmd.slaves:
                shell.call('/usr/local/bin/zs-nic-to-bond -a %s %s' % (cmd.bondName, slave.interfaceName))

            # sync to collectd
            config_file = '/var/lib/zstack/kvm/collectd.conf'
            self._add_interface_to_collectd_conf(config_file, cmd.bondName)
            self._restart_collectd(config_file)
        except Exception as e:
            if "already exists" not in str(e):
                shell.run('/usr/local/bin/zs-bond -d %s' % cmd.bondName)
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create bonding[%s], because %s' % (cmd.bondName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bonding')
    @kvmagent.replyerror
    @in_bash
    def update_bonding(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateBondingResponse()

        oldInterfaces = set(item.interfaceName for item in cmd.oldSlaves)
        newInterfaces = set(item.interfaceName for item in cmd.slaves)
        add_items = list(set(newInterfaces) - set(oldInterfaces))
        reduce_items = list(set(oldInterfaces) - set(newInterfaces))

        try:
            for interface in add_items:
                if self._has_vlan_or_bridge(interface):
                    raise Exception(interface + ' has a sub-interface or a bridge port')

            if cmd.mode is not None or cmd.xmitHashPolicy is not None:
                mode = linux.read_file("/sys/class/net/%s/bonding/mode" % cmd.bondName).strip()
                policy = linux.read_file("/sys/class/net/%s/bonding/xmit_hash_policy" % cmd.bondName).strip()
                if cmd.mode not in mode or cmd.xmitHashPolicy is not None and cmd.xmitHashPolicy not in policy:
                    # zs-bond -u bond1 mode 802.3ad
                    if cmd.xmitHashPolicy is None:
                        shell.call('/usr/local/bin/zs-bond -u %s mode %s' % (cmd.bondName, cmd.mode))
                    else:
                        shell.call('/usr/local/bin/zs-bond -u %s mode %s xmitHashPolicy %s' % (
                            cmd.bondName, cmd.mode, cmd.xmitHashPolicy))

            if add_items != reduce_items:
                # zs-nic-to-bond -a bond2 nic3
                for interface in add_items:
                    shell.call('/usr/local/bin/zs-nic-to-bond -a %s %s' % (cmd.bondName, interface))
                # zs-nic-to-bond -d bond2 nic nic4
                for interface in reduce_items:
                    shell.call('/usr/local/bin/zs-nic-to-bond -d %s %s' % (cmd.bondName, interface))

        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create bonding[%s], because %s' % (cmd.bondName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bonding')
    @kvmagent.replyerror
    @in_bash
    def attach_nic_to_bonding(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AttachNicToBondResponse()

        try:
            for interface in cmd.slaves:
                if self._has_vlan_or_bridge(interface.interfaceName):
                    raise Exception(interface.interfaceName + ' has a sub-interface or a bridge port')
            for interface in cmd.slaves:
                shell.call('/usr/local/bin/zs-nic-to-bond -a %s %s' % (cmd.bondName, interface.interfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to attach nic to bonding[%s], because %s' % (cmd.bondName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @in_bash
    def detach_nic_from_bonding(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DetachNicFromBondResponse()

        try:
            for interface in cmd.slaves:
                shell.call('/usr/local/bin/zs-nic-to-bond -d %s %s' % (cmd.bondName, interface.interfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to detach nic from bonding[%s], because %s' % (cmd.bondName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bonding')
    @kvmagent.replyerror
    @in_bash
    def delete_bonding(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteBondingResponse()

        try:
            if self._has_vlan_or_bridge(cmd.bondName):
                raise Exception(cmd.bondName + ' has a sub-interface or a bridge port')
            else:
                # zs-bond -d bond2
                shell.call('/usr/local/bin/zs-bond -d %s' % cmd.bondName)

            # sync to collectd
            config_file = '/var/lib/zstack/kvm/collectd.conf'
            self._remove_interface_from_collectd_conf(config_file, cmd.bondName)
            self._restart_collectd(config_file)
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to delete bonding[%s], because %s' % (cmd.bondName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @linux.retry(times=3, sleep_time=5)
    def _restart_lldpd(self):
        shell.call('systemctl restart lldpd.service')

    def _init_lldpd(self, config_file):
        r, lspci_output = bash_ro("lspci | grep -i -E 'eth.*X710|eth.*X722|eth.*XL710'")
        lldp_stop_command = "lldp stop\n"

        if r == 0:
            for line in lspci_output.splitlines():
                nic_pci_address = line.split()[0]
                nic_pci_address_path = '/sys/kernel/debug/i40e/0000:%s' % nic_pci_address
                if os.path.exists(nic_pci_address_path):
                    command_file_path = os.path.join(nic_pci_address_path, "command")
                    if not os.path.exists(command_file_path) or lldp_stop_command not in open(command_file_path).read():
                        with open(command_file_path, "a") as command_file:
                            command_file.write(lldp_stop_command)
                else:
                    logger.debug('failed to update x710/x722 nic lldp configure, because directory does not exist: %s' % nic_pci_address_path)

        conf = '''# Configuration from ZStack
configure system hostname 'ZStack-{{NAME}}'
configure lldp status rx-only \n
'''
        tmpt = Template(conf)
        conf = tmpt.render({
            'NAME': linux.get_hostname()
        })

        if not os.path.exists(config_file):
            with open(config_file, 'w') as f:
                f.write(conf)
                self._restart_lldpd()

    def _update_lldp_conf(self, config_file, interface_names, mode):
        with open(config_file, 'r') as f:
            lines = f.readlines()

        for interface_name in interface_names:
            updated_existing_line = False
            for index, line in enumerate(lines):
                if 'configure ports %s lldp status' % interface_name in line:
                    parts = line.split(' ')
                    if len(parts) >= 6:
                        old_mode = parts[5]
                        lines[index] = line.replace('configure ports %s lldp status %s' % (interface_name, old_mode),
                                                    'configure ports %s lldp status %s' % (interface_name, mode))
                        updated_existing_line = True
                        break
            if not updated_existing_line:
                lines.append('configure ports %s lldp status %s \n' % (interface_name, mode))

        with open(config_file, 'w') as f:
            f.writelines(lines)

        self._restart_lldpd()

    @lock.lock('lldp')
    @kvmagent.replyerror
    def change_lldp_mode(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ChangeLldpModeResponse()

        config_file = '/etc/lldpd.d/lldpd.conf'

        try:
            # create and write a new configuration initially
            if not linux.find_process_by_command('lldpd') or not os.path.exists(config_file):
                self._init_lldpd(config_file)

            # subsequently update the configuration file
            self._update_lldp_conf(config_file, cmd.physicalInterfaceNames, cmd.mode.replace('_', '-'))

        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to change lldp mode to [%s], because %s' % (cmd.mode.replace('_', '-'), str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    def _parse_lldp_json(self, json_data, interface_name):
        data_dict = json.loads(json_data)
        interface_data = data_dict.get("lldp", {}).get("interface", {}).get(interface_name, {})

        if not interface_data:
            logger.debug('failed to get lldp info for %s, because no data found for the interface' % interface_name)
            return None

        # Adapted switch: Centec Huawei H3C
        interface_lldp_info = HostNetworkInterfaceLldpStruct()
        # Chassis information
        chassis_data = interface_data.get("chassis", {})
        for chassis_key, chassis_value in chassis_data.items():
            interface_lldp_info.chassisId = chassis_value.get("id", {}).get("value")
            # no mgmt-ip field for H3C
            mgmt_ip = chassis_value.get('mgmt-ip')
            if not mgmt_ip:
                interface_lldp_info.managementAddress = None
            elif isinstance(mgmt_ip, list):
                interface_lldp_info.managementAddress = mgmt_ip[0]
            else:
                interface_lldp_info.managementAddress = mgmt_ip.split(',')[0]
            interface_lldp_info.systemName = chassis_key
            interface_lldp_info.systemDescription = chassis_value.get("descr").replace("\r\n", ";").replace("\n", ";")
            capabilities_enabled_list = [capability.get("type") for capability in
                                         chassis_value.get("capability", []) if capability.get("enabled", False)]
            capabilities_enabled_string = ', '.join(capabilities_enabled_list)
            interface_lldp_info.systemCapabilities = capabilities_enabled_string if capabilities_enabled_list else None

        # Port information
        interface_lldp_info.timeToLive = interface_data.get("port", {}).get("ttl")
        interface_lldp_info.portId = interface_data.get("port", {}).get("id", {}).get("value")
        interface_lldp_info.portDescription = interface_data.get("port", {}).get("descr")
        interface_lldp_info.vlanId = interface_data.get("vlan", {}).get("vlan-id")
        # no aggregation field for H3C
        interface_lldp_info.aggregationPortId = interface_data.get("port", {}).get("aggregation")
        interface_lldp_info.mtu = interface_data.get("port", {}).get("mfs")

        return interface_lldp_info

    @linux.retry_if_unexpected_value(None, times=5, sleep_time=5)
    def _get_interface_lldp(self, interface_name):
        lldpinfo = None
        r, info = bash_ro('lldpctl ports %s -f json' % interface_name)
        if r != 0:
            return lldpinfo

        try:
            lldpinfo = self._parse_lldp_json(info, interface_name)
        except Exception as e:
            raise Exception('parse lldpctl info error: %s' % info)

        return lldpinfo

    @lock.lock('lldp')
    @kvmagent.replyerror
    def get_lldp_info(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetLldpInfoResponse()

        config_file = '/etc/lldpd.d/lldpd.conf'

        try:
            # create and write a new configuration initially
            if not linux.find_process_by_command('lldpd') or not os.path.exists(config_file):
                self._init_lldpd(config_file)

            # subsequently call lldp tool to obtain lldp information
            rsp.lldpInfo = self._get_interface_lldp(cmd.physicalInterfaceName)

        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to get lldp info for [%s], because %s' % (cmd.physicalInterfaceName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)


    @lock.lock('lldp')
    @kvmagent.replyerror
    def apply_lldp_config(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ApplyLldpConfigResponse()

        config_file = '/etc/lldpd.d/lldpd.conf'

        try:
            # create and write a new configuration initially
            if not linux.find_process_by_command('lldpd') or not os.path.exists(config_file):
                self._init_lldpd(config_file)

            # subsequently update the configuration file
            for interfaceConfig in cmd.lldpConfig:
                self._update_lldp_conf(config_file, [interfaceConfig.physicalInterfaceName], interfaceConfig.mode.replace('_', '-'))

        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to apply lldp config, because %s', str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def update_vlan_bridge(self, req):
        rsp = CreateBridgeResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        try:
            self.update_bridge_vlan(cmd, rsp)
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to update vlan bridge[%s], because %s' % (
                cmd.bridgeName, str(e))
            rsp.success = False
        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def update_vxlan_bridge(self, req):
        rsp = CreateBridgeResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        try:
            self.update_bridge_vxlan(cmd, rsp)
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to update vxlan bridge[%s], because %s' % (
                cmd.bridgeName, str(e))
            rsp.success = False
        return jsonobject.dumps(rsp)

    def update_bridge_vxlan(self, cmd, rsp):
        if not cmd.oldVlan or not cmd.newVlan:
            error_msg = 'both oldVlan and newVlan must be provided.'
            logger.warning(error_msg)
            rsp.error = error_msg
            rsp.success = False
            return jsonobject.dumps(rsp)
        new_vxlan_interface = None
        old_vxlan_interface = None
        if cmd.newVlan:
            new_vxlan_interface = 'vxlan%s' % cmd.newVlan
        if cmd.oldVlan:
            old_vxlan_interface = 'vxlan%s' % cmd.oldVlan
        try:
            if cmd.peers:
                linux.delete_vxlan_fdbs([old_vxlan_interface], cmd.peers)
            linux.change_vxlan_interface(cmd.oldVlan, cmd.newVlan)
            linux.update_bridge_interface_configuration(old_vxlan_interface, new_vxlan_interface,
                                                        cmd.bridgeName, cmd.l2NetworkUuid)
            if cmd.peers:
                linux.populate_vxlan_fdbs([new_vxlan_interface], cmd.peers)
            logger.debug('successfully update bridge[%s] vxlan interface from device[%s] to device[%s]'
                % (cmd.bridgeName, cmd.oldVlanInterface, cmd.newVlanInterface))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = ('unable to update bridge[%s] vxlan interface from device[%s] to device[%s], because %s'
                         % (cmd.bridgeName, old_vxlan_interface, new_vxlan_interface, str(e)))
            rsp.success = False
        return jsonobject.dumps(rsp)

    def update_bridge_vlan(self, cmd, rsp):
        self._ifup_device_if_down(cmd.physicalInterfaceName)
        if cmd.newVlan:
            new_vlan_interface = '%s.%s' % (cmd.physicalInterfaceName, cmd.newVlan)
        else:
            new_vlan_interface = '%s' % cmd.physicalInterfaceName
        if cmd.oldVlan:
            old_vlan_interface = '%s.%s' % (cmd.physicalInterfaceName, cmd.oldVlan)
        else:
            old_vlan_interface = '%s' % cmd.physicalInterfaceName
        try:
            if cmd.newVlan:
                linux.create_vlan_eth(cmd.physicalInterfaceName, cmd.newVlan)
            linux.update_bridge_interface_configuration(old_vlan_interface, new_vlan_interface,
                                                        cmd.bridgeName, cmd.l2NetworkUuid)
            # switch to NoVlan Network need keep physical dev ip and route in bridge
            if not cmd.newVlan and cmd.oldVlan:
                linux.move_dev_route(cmd.physicalInterfaceName, cmd.bridgeName)
            # switch to Vlan Network will return bridge ip and route to physical dev
            if cmd.newVlan and not cmd.oldVlan:
                linux.move_dev_route(cmd.bridgeName, cmd.physicalInterfaceName)
            logger.debug('successfully update bridge[%s] vlan interface from device[%s] to device[%s]'
                % (cmd.bridgeName, cmd.oldVlanInterface, cmd.newVlanInterface))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = ('unable to update bridge[%s] vlan interface from device[%s] to device[%s], because %s'
                         % (cmd.bridgeName, old_vlan_interface, new_vlan_interface, str(e)))
            rsp.success = False
        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def create_bridge(self, req):
        rsp = CreateBridgeResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        try:
            self.create_novlan_bridge(cmd, rsp)
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create bridge[%s] from device[%s], because %s' % (
                cmd.bridgeName, cmd.physicalInterfaceName, str(e))
            rsp.success = False
        return jsonobject.dumps(rsp)

    def create_novlan_bridge(self, cmd, rsp):
        self._ifup_device_if_down(cmd.physicalInterfaceName)

        oldMtu = self._get_interface_mtu(cmd.physicalInterfaceName)
        mtu = cmd.mtu
        if oldMtu > cmd.mtu:
            mtu = oldMtu

        try:
            linux.create_bridge(cmd.bridgeName, cmd.physicalInterfaceName)
            linux.set_device_uuid_alias(cmd.physicalInterfaceName, cmd.l2NetworkUuid)
            self._configure_bridge(cmd.disableIptables)
            self._configure_bridge_mtu(cmd.bridgeName, cmd.physicalInterfaceName, mtu)
            self._configure_bridge_learning(cmd.bridgeName, cmd.physicalInterfaceName)
            linux.set_bridge_alias_using_phy_nic_name(cmd.bridgeName, cmd.physicalInterfaceName)
            logger.debug(
                'successfully realize bridge[%s] from device[%s]' % (cmd.bridgeName, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create bridge[%s] from device[%s], because %s' % (
                cmd.bridgeName, cmd.physicalInterfaceName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def create_vlan_bridge(self, req):
        rsp = CreateVlanBridgeResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if cmd.vlan == 0:
            try:
                self.create_novlan_bridge(cmd, rsp)
            except Exception as e:
                logger.warning(traceback.format_exc())
                rsp.error = 'unable to create bridge[%s] from device[%s], because %s' % (
                    cmd.bridgeName, cmd.physicalInterfaceName, str(e))
                rsp.success = False
            return jsonobject.dumps(rsp)

        vlanInterfName = '%s.%s' % (cmd.physicalInterfaceName, cmd.vlan)

        oldMtu = self._get_interface_mtu(vlanInterfName)
        mtu = cmd.mtu
        if oldMtu > cmd.mtu:
            mtu = oldMtu
        pvlan = getattr(cmd, 'pvlan', None)
        isolated = getattr(cmd, 'isolated', False)
        try:
            linux.create_vlan_bridge(cmd.bridgeName, cmd.physicalInterfaceName, cmd.vlan)
            self._configure_bridge(cmd.disableIptables)
            self._configure_bridge_mtu(cmd.bridgeName, vlanInterfName, mtu)
            self._configure_bridge_learning(cmd.bridgeName, vlanInterfName)
            linux.set_bridge_alias_using_phy_nic_name(cmd.bridgeName, cmd.physicalInterfaceName)
            linux.set_device_uuid_alias('%s.%s' % (cmd.physicalInterfaceName, cmd.vlan), cmd.l2NetworkUuid)
            # if pvlan:
            #     self._ifdown_device_if_up(vlanInterfName)
            #     self._configure_pvlan_veth(pvlan, cmd.bridgeName)
            if isolated:
                self._configure_isolated(vlanInterfName)
            logger.debug('successfully realize vlan bridge[name:%s, vlan:%s] from device[%s]' % (
                cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create vlan bridge[name:%s, vlan:%s] from device[%s], because %s' % (
                cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName, str(e))
            rsp.success = False
        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def create_mac_vlan_eth(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVlanBridgeResponse()
        vlanInterfName = '%s.%s' % (cmd.physicalInterfaceName, cmd.vlan)

        oldMtu = self._get_interface_mtu(vlanInterfName)
        mtu = cmd.mtu
        if oldMtu > cmd.mtu:
            mtu = oldMtu
        try:
            linux.create_vlan_eth(cmd.physicalInterfaceName, cmd.vlan)
            linux.set_device_uuid_alias('%s.%s' % (cmd.physicalInterfaceName, cmd.vlan), cmd.l2NetworkUuid)
            logger.debug('successfully realize vlan eth[name:%s, vlan:%s] from device[%s]' % (
                vlanInterfName, cmd.vlan, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create vlan eth[name:%s, vlan:%s] from device[%s], because %s' % (
                vlanInterfName, cmd.vlan, cmd.physicalInterfaceName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def check_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBridgeResponse()
        if not linux.is_bridge(cmd.bridgeName):
            rsp.error = "can not find bridge[%s]" % cmd.bridgeName
            rsp.success = False
        else:
            self._ifup_device_if_down(cmd.physicalInterfaceName)

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def check_vlan_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckVlanBridgeResponse()
        if not linux.is_bridge(cmd.bridgeName):
            rsp.error = "can not find vlan bridge[%s]" % cmd.bridgeName
            rsp.success = False
        else:
            self._ifup_device_if_down(cmd.physicalInterfaceName)

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def check_macvlan_vlan_eth(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckVlanBridgeResponse()
        if not linux.vlan_eth_exists(cmd.physicalInterfaceName, cmd.vlan):
            rsp.error = "can not find vlan network interface[%s] for macvlan" % linux.make_vlan_eth_name(
                cmd.physicalInterfaceName, cmd.vlan)
            rsp.success = False
        else:
            self._ifup_device_if_down(cmd.physicalInterfaceName)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_vxlan_cidr(self, req):

        def filter_vxlan_nics(nics, interf, requireIp):
            valid_nics = []

            if interf:
                for nic in nics:
                    if interf in nic.keys():
                        valid_nics.append(nic)

            if requireIp:
                for nic in nics:
                    if requireIp in nic.values():
                        valid_nics.append(nic)

            return valid_nics

        # Check qualified interface with cidr and interface name, vtepip address (if provided).
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckVxlanCidrResponse()
        rsp.success = False
        interf = cmd.physicalInterfaceName

        nics = linux.get_nics_by_cidr(cmd.cidr)
        temp_nics = filter_vxlan_nics(nics, interf, cmd.vtepip)
        # if there is no valid nic after filter, try all nics match the cidr of vxlan pool
        if len(temp_nics) != 0:
            nics = temp_nics

        temp_ips = [d.values()[0] for d in nics]
        ips = sorted(set(temp_ips), key=temp_ips.index)
        temp_nicnames = [d.keys()[0] for d in nics]
        nicnames = sorted(set(temp_nicnames), key=temp_nicnames.index)

        ''' there are 7 cases:
            1. there is no interface has ip address matched the vxlan or vxpool cidr
            2. the interface name is provided:
                2.1 there is only 1 interface with 1 ip address matched
                2.2 there is only 1 interface with more than 1 ip address matched
                    in this case, we always return the first 1 ip address
                2.3 there are multiple interfaces with ip address matched
            3. the interface name is not provided
                3.1 there is only 1 interface with 1 ip address matched
                3.2 there is only 1 interface with more than 1 ip address matched
                    in this case, we always return the first 1 ip address
                3.3 there are multiple interfaces with ip address matched
            #1, #3.3 will response error
        '''

        if not nicnames:
            # case #1
            rsp.error = "can not find qualify interface for cidr [%s]" % cmd.cidr
            return jsonobject.dumps(rsp)

        if interf:
            # case #2.1 #2.2(if only 1 interface) and case #2.3
            for nic in nicnames:
                if nic == interf:
                    rsp.vtepIp = ips[0]
                    rsp.physicalInterfaceName = nic
                    rsp.success = True
            if rsp.vtepIp is None:
                rsp.error = "no interface both qualify with cidr [%s] and interface name [%s] provided" % (cmd.cidr,
                                                                                                           interf)
            return jsonobject.dumps(rsp)

        if len(nicnames) == 1:
            # case #3.1 #3.2
            rsp.vtepIp = ips[0]
            rsp.physicalInterfaceName = nicnames[0]
            rsp.success = True
        elif len(nicnames) == 2 and linux.is_vif_on_bridge(nicnames[0], nicnames[1]):
            # Note(WeiW): This is a workaround for case of an interface bound to a bridge and have same ip address,
            # see at zstackio/issues#4056, but note this won't make assurance that routing is true
            rsp.vtepIp = ips[0]
            rsp.physicalInterfaceName = nicnames[0]
            rsp.success = True
        elif len(nicnames) == 2 and linux.is_vif_on_bridge(nicnames[1], nicnames[0]):
            # same as above, but with the interface names reversed
            rsp.vtepIp = ips[0]
            rsp.physicalInterfaceName = nicnames[1]
            rsp.success = True
        elif len(nicnames) > 1 and len(ips) == 1:
            # case #3.3
            rsp.error = "the qualified vtep ip bound to multiple interfaces"
        else:
            rsp.error = "multiple interface qualify with cidr [%s] and no interface name provided" % cmd.cidr

        return jsonobject.dumps(rsp)

    def create_single_vxlan_bridge(self, cmd):
        interf = "vxlan" + str(cmd.vni)
        oldMtu = self._get_interface_mtu(interf)
        mtu = cmd.mtu
        if oldMtu > cmd.mtu:
            mtu = oldMtu

        if cmd.dstport == None:
            cmd.dstport = VXLAN_DEFAULT_PORT
        linux.create_vxlan_interface(cmd.vni, cmd.vtepIp, cmd.dstport)

        linux.create_vxlan_bridge(interf, cmd.bridgeName, cmd.peers)
        linux.set_device_uuid_alias(interf, cmd.l2NetworkUuid)
        self._configure_bridge_mtu(cmd.bridgeName, interf, mtu)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def create_vxlan_bridge(self, req):
        # Create VXLAN interface using vtep ip then create bridge
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVxlanBridgeResponse()
        if not (cmd.vni and cmd.vtepIp):
            rsp.error = "vni or vtepip is none"
            rsp.success = False
            return jsonobject.dumps(rsp)

        self.create_single_vxlan_bridge(cmd)

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def create_vxlan_bridges(self, req):
        # Create VXLAN interface using vtep ip then create bridge
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVxlanBridgesResponse()

        for bridgeCmd in cmd.bridgeCmds:
            if not (bridgeCmd.vni and bridgeCmd.vtepIp):
                rsp.error = "vni or vtepip is none"
                rsp.success = False
                return jsonobject.dumps(rsp)

        for bridgeCmd in cmd.bridgeCmds:
            self.create_single_vxlan_bridge(bridgeCmd)

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def delete_vxlan_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVxlanBridgeResponse()
        if not (cmd.vni and cmd.vtepIp):
            rsp.error = "vni or vtepip is none"
            rsp.success = False
            return jsonobject.dumps(rsp)
        try:
            vxlanInterface = "vxlan" + str(cmd.vni)
            linux.delete_vxlan_bridge(cmd.bridgeName, vxlanInterface)
            logger.debug('successfully delete vxlan bridge[name:%s, vni:%s] from vtepIp[%s]' % (
                cmd.bridgeName, cmd.vni, cmd.vtepIp))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'failed to delete vxlan bridge[name:%s, vni:%s] from vtepIp[%s], because %s' % (
                cmd.bridgeName, cmd.vni, cmd.vtepIp, str(e))

        return jsonobject.dumps(rsp)

    def populate_vxlan_fdb(self, req):
        # populate vxlan fdb
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = PopulateVxlanFdbResponse

        interf = "vxlan" + str(cmd.vni)
        rsp.success = linux.populate_vxlan_fdbs([interf], cmd.peers)

        if rsp.success != True:
            rsp.error = "error on populate fdb"

        return jsonobject.dumps(rsp)

    def populate_vxlan_fdbs(self, req):
        # populate vxlan fdb
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = PopulateVxlanFdbResponse

        interfs = linux.get_interfs_from_uuids(cmd.networkUuids)
        if interfs == []:
            rsp.success = True
            return jsonobject.dumps(rsp)

        if linux.populate_vxlan_fdbs(interfs, cmd.peers) == False:
            rsp.success = False
            rsp.error = "error on populate fdb"
            return jsonobject.dumps(rsp)

        rsp.success = True
        return jsonobject.dumps(rsp)

    def delete_vxlan_fdbs(self, req):
        # delete  vxlan fdb
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteVxlanFdbResponse

        interfs = linux.get_interfs_from_uuids(cmd.networkUuids)
        if interfs == []:
            rsp.success = True
            return jsonobject.dumps(rsp)

        if linux.delete_vxlan_fdbs(interfs, cmd.peers) == False:
            rsp.success = False
            rsp.error = "error on delete fdb"
            return jsonobject.dumps(rsp)

        rsp.success = True
        return jsonobject.dumps(rsp)

    def set_bridge_router_port(self, req):
        # set bridge router port:
        # echo "2" > /sys/devices/virtual/net/vnic2.1/brport/multicast_router
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetBridgeRouterPortResponse

        value = '2'
        if cmd.enable == False:
            value = '1'

        for nic in cmd.nicNames:
            linux.write_file("/sys/devices/virtual/net/%s/brport/multicast_router" % nic, value)

        rsp.success = True
        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def delete_novlan_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteBridgeResponse()

        try:
            del_novlan_bridge(cmd)
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'failed to delete bridge[%s] with physical interface[%s], because %s' % (
                cmd.bridgeName, cmd.physicalInterfaceName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def delete_vlan_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteVlanBridgeResponse()

        if cmd.vlan == 0:
            try:
                del_novlan_bridge(cmd)
            except Exception as e:
                logger.warning(traceback.format_exc())
                rsp.error = 'failed to delete bridge[%s] with physical interface[%s], because %s' % (
                    cmd.bridgeName, cmd.physicalInterfaceName, str(e))
                rsp.success = False

            return jsonobject.dumps(rsp)

        vlanInterfName = '%s.%s' % (cmd.physicalInterfaceName, cmd.vlan)

        try:
            linux.delete_vlan_bridge(cmd.bridgeName, vlanInterfName)
            logger.debug('successfully delete vlan bridge[name:%s, vlan:%s] from device[%s]' % (
                cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName))
            self._delete_isolated(vlanInterfName)
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'failed to delete vlan bridge[name:%s, vlan:%s] from device[%s], because %s' % (
                cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def delete_macvlan_vlan_eth(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteVlanBridgeResponse()
        vlanInterfName = '%s.%s' % (cmd.physicalInterfaceName, cmd.vlan)

        try:
            linux.delete_vlan_eth(vlanInterfName)
            logger.debug('successfully delete vlan eth[name:%s, vlan:%s] from device[%s]' % (
                vlanInterfName, cmd.vlan, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'failed to delete vlan eth[name:%s, vlan:%s] from device[%s], because %s' % (
                vlanInterfName, cmd.vlan, cmd.physicalInterfaceName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def create_vxlan_bridge(self, req):
        # Create VXLAN interface using vtep ip then create bridge
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVxlanBridgeResponse()
        if not (cmd.vni and cmd.vtepIp):
            rsp.error = "vni or vtepip is none"
            rsp.success = False
            return jsonobject.dumps(rsp)

        self.create_single_vxlan_bridge(cmd)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def attach_nic_to_ipset_path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        if cmd.l2MacMap:
            l2_mac_dict = cmd.l2MacMap.__dict__
            interface_dict = cmd.interfaceMap.__dict__
            vlan_dict = cmd.vlanMap.__dict__
            for l2, mac_list in l2_mac_dict.items():
                for mac in mac_list:
                    shell.call('ipset add isolated_%s.%s %s'
                               % (interface_dict.get(l2), vlan_dict.get(l2), mac), exception=False)
                logger.debug('attach nic to ipset [l2PhysicalInterface:%s, vlan:%s, macList:%s] success' % (
                    interface_dict.get(l2), vlan_dict.get(l2), mac_list))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_nic_to_ipset_path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        if cmd.l2MacMap:
            l2_mac_dict = cmd.l2MacMap.__dict__
            interface_dict = cmd.interfaceMap.__dict__
            vlan_dict = cmd.vlanMap.__dict__
            for l2, mac_list in l2_mac_dict.items():
                for mac in mac_list:
                    shell.call('ipset del isolated_%s.%s %s'
                               % (interface_dict.get(l2), vlan_dict.get(l2), mac), exception=False)
                logger.debug('detach nic to ipset [l2PhysicalInterface:%s, vlan:%s, macList:%s] success' % (
                    interface_dict.get(l2), vlan_dict.get(l2), mac_list))
            for vnic in cmd.nicList:
                # hot migrate will not update nic info, it necessary to set nic isolated manually after migrate
                iproute.config_link_isolated(vnic)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def sync_ipset_path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        if cmd.l2MacMap:
            l2_mac_dict = cmd.l2MacMap.__dict__
            interface_dict = cmd.interfaceMap.__dict__
            vlan_dict = cmd.vlanMap.__dict__
            for l2, mac_list in l2_mac_dict.items():
                isolated_br = 'isolated_%s.%s' % (interface_dict.get(l2), vlan_dict.get(l2))
                physdev_in = '%s.%s' % (interface_dict.get(l2), vlan_dict.get(l2))
                ipset_list = shell.ShellCmd("ipset list %s" % isolated_br)
                ipset_list(False)
                if ipset_list.return_code == 0:
                    shell.call('iptables -w -D %s -m physdev --physdev-in %s -m set --match-set %s src -j DROP' % (
                        PVLAN_ISOLATED_CHAIN, physdev_in, isolated_br), exception=False)
                    shell.call('ip6tables -w -D %s -m physdev --physdev-in %s -m set --match-set %s src -j DROP' % (
                        PVLAN_ISOLATED_CHAIN_V6, physdev_in, isolated_br), exception=False)
                    shell.call('ipset destroy %s' % isolated_br, exception=False)
                shell.call('ipset create %s hash:mac' % isolated_br)
                shell.call('iptables -w -I %s -m physdev --physdev-in %s -m set --match-set %s src -j DROP' % (
                    PVLAN_ISOLATED_CHAIN, physdev_in, isolated_br))
                shell.call('ip6tables -w -I %s -m physdev --physdev-in %s -m set --match-set %s src -j DROP' % (
                    PVLAN_ISOLATED_CHAIN_V6, physdev_in, isolated_br))
                for mac in mac_list:
                    shell.call('ipset add isolated_%s.%s %s'
                               % (interface_dict.get(l2), vlan_dict.get(l2), mac), exception=False)
                logger.debug('sync host with ipset [l2PhysicalInterface:%s, vlan:%s, macList:%s] success' % (
                    interface_dict.get(l2), vlan_dict.get(l2), mac_list))
        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_sync_uri(CHECK_PHYSICAL_NETWORK_INTERFACE_PATH, self.check_physical_network_interface)
        http_server.register_async_uri(ADD_INTERFACE_TO_BRIDGE_PATH, self.add_interface_to_bridge)
        http_server.register_async_uri(CREATE_BONDING_PATH, self.create_bonding)
        http_server.register_async_uri(UPDATE_BONDING_PATH, self.update_bonding)
        http_server.register_async_uri(DELETE_BONDING_PATH, self.delete_bonding)
        http_server.register_async_uri(ATTACH_NIC_TO_BONDING_PATH, self.attach_nic_to_bonding)
        http_server.register_async_uri(DETACH_NIC_FROM_BONDING_PATH, self.detach_nic_from_bonding)
        http_server.register_async_uri(KVM_CHANGE_LLDP_MODE_PATH, self.change_lldp_mode)
        http_server.register_async_uri(KVM_GET_LLDP_INFO_PATH, self.get_lldp_info)
        http_server.register_async_uri(KVM_APPLY_LLDP_CONFIG_PATH, self.apply_lldp_config)
        http_server.register_async_uri(KVM_UPDATE_L2VLAN_NETWORK_PATH, self.update_vlan_bridge)
        http_server.register_async_uri(KVM_UPDATE_L2VXLAN_NETWORK_PATH, self.update_vxlan_bridge)
        http_server.register_async_uri(KVM_REALIZE_L2NOVLAN_NETWORK_PATH, self.create_bridge)
        http_server.register_async_uri(KVM_REALIZE_L2VLAN_NETWORK_PATH, self.create_vlan_bridge)
        http_server.register_async_uri(KVM_REALIZE_MACVLAN_L2VLAN_NETWORK_PATH, self.create_mac_vlan_eth)
        http_server.register_async_uri(KVM_CHECK_L2NOVLAN_NETWORK_PATH, self.check_bridge)
        http_server.register_async_uri(KVM_CHECK_MACVLAN_L2VLAN_NETWORK_PATH, self.check_macvlan_vlan_eth)
        http_server.register_async_uri(KVM_CHECK_L2VLAN_NETWORK_PATH, self.check_vlan_bridge)
        http_server.register_async_uri(KVM_CHECK_L2VXLAN_NETWORK_PATH, self.check_vxlan_cidr)
        http_server.register_async_uri(KVM_REALIZE_L2VXLAN_NETWORK_PATH, self.create_vxlan_bridge)
        http_server.register_async_uri(KVM_REALIZE_L2VXLAN_NETWORKS_PATH, self.create_vxlan_bridges)
        http_server.register_async_uri(KVM_POPULATE_FDB_L2VXLAN_NETWORK_PATH, self.populate_vxlan_fdb)
        http_server.register_async_uri(KVM_POPULATE_FDB_L2VXLAN_NETWORKS_PATH, self.populate_vxlan_fdbs)
        http_server.register_async_uri(KVM_DELETE_FDB_L2VXLAN_NETWORKS_PATH, self.delete_vxlan_fdbs)
        http_server.register_async_uri(KVM_SET_BRIDGE_ROUTER_PORT_PATH, self.set_bridge_router_port)
        http_server.register_async_uri(KVM_DELETE_L2NOVLAN_NETWORK_PATH, self.delete_novlan_bridge)
        http_server.register_async_uri(KVM_DELETE_L2VLAN_NETWORK_PATH, self.delete_vlan_bridge)
        http_server.register_async_uri(KVM_DELETE_MACVLAN_L2VLAN_NETWORK_PATH, self.delete_macvlan_vlan_eth)
        http_server.register_async_uri(KVM_DELETE_L2VXLAN_NETWORK_PATH, self.delete_vxlan_bridge)
        http_server.register_async_uri(KVM_IPSET_ATTACH_NIC_PATH, self.attach_nic_to_ipset_path)
        http_server.register_async_uri(KVM_IPSET_DETACH_NIC_PATH, self.detach_nic_to_ipset_path)
        http_server.register_async_uri(KVM_IPSET_SYNC_PATH, self.sync_ipset_path)

    def stop(self):
        pass

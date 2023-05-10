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
from zstacklib.utils.bash import *
from zstacklib.utils import ovs
import os
import traceback
import pyroute2
import netaddr

CHECK_PHYSICAL_NETWORK_INTERFACE_PATH = '/network/checkphysicalnetworkinterface'
ADD_INTERFACE_TO_BRIDGE_PATH = '/network/bridge/addif'
CREATE_BONDING_PATH = '/network/bonding/create'
UPDATE_BONDING_PATH = '/network/bonding/update'
DELETE_BONDING_PATH = '/network/bonding/delete'
KVM_REALIZE_L2NOVLAN_NETWORK_PATH = "/network/l2novlan/createbridge"
KVM_REALIZE_L2VLAN_NETWORK_PATH = "/network/l2vlan/createbridge"
KVM_CHECK_L2NOVLAN_NETWORK_PATH = "/network/l2novlan/checkbridge"
KVM_CHECK_L2VLAN_NETWORK_PATH = "/network/l2vlan/checkbridge"
KVM_CHECK_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/checkcidr"
KVM_REALIZE_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/createbridge"
KVM_REALIZE_L2VXLAN_NETWORKS_PATH = "/network/l2vxlan/createbridges"
KVM_POPULATE_FDB_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/populatefdb"
KVM_POPULATE_FDB_L2VXLAN_NETWORKS_PATH = "/network/l2vxlan/populatefdbs"
KVM_SET_BRIDGE_ROUTER_PORT_PATH = "/host/bridge/routerport"
KVM_DELETE_L2NOVLAN_NETWORK_PATH = "/network/l2novlan/deletebridge"
KVM_DELETE_L2VLAN_NETWORK_PATH = "/network/l2vlan/deletebridge"
KVM_DELETE_L2VXLAN_NETWORK_PATH = "/network/l2vxlan/deletebridge"
VXLAN_DEFAULT_PORT = 8472


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

class CreateVxlanBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateVxlanBridgeResponse, self).__init__()

class CreateVxlanBridgesResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateVxlanBridgesResponse, self).__init__()

class PopulateVxlanFdbResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(PopulateVxlanFdbResponse, self).__init__()

class SetBridgeRouterPortResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SetBridgeRouterPortResponse, self).__init__()

class DeleteBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteBridgeCmd, self).__init__()
        self.physicalInterfaceName = None
        self.bridgeName = None

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
        self.oldSlaves = None # type: list[HostNetworkInterfaceStruct]
        self.slaves = None # type: list[HostNetworkInterfaceStruct]
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
            #bridge mtu must be bigger than all vnic mtu, so will not change it
            #if bridgeName is not None:
            #    shell.call("ip link set mtu %d dev %s" % (mtu, bridgeName))

    def _configure_bridge_learning(self, bridgeName, interf, learning='on'):
        shell.call("bridge link set dev %s learning %s" % (interf, learning))

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

        logger.debug(http.path_msg(CHECK_PHYSICAL_NETWORK_INTERFACE_PATH, 'checked physical interfaces: %s' % cmd.interfaceNames))
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
        with pyroute2.IPRoute() as ipr:
            links = ipr.get_links()
            for link in links:
                # Check for vlan interface
                if link.get_attr('IFLA_LINKINFO') and \
                        link.get_attr('IFLA_LINKINFO').get_attr('IFLA_INFO_KIND') == 'vlan' and \
                        link.get_attr('IFLA_IFNAME').startswith(ifname + '.'):
                    return True

                # Check for bridge port
                if link.get_attr('IFLA_LINKINFO') and \
                        link.get_attr('IFLA_LINKINFO').get_attr('IFLA_INFO_KIND') == 'bridge' and \
                        link.get_attr('IFLA_MASTER') and \
                        link.get_attr('IFLA_MASTER') == ipr.link_lookup(ifname)[0]:
                    return True

            return False

    @lock.lock('bonding')
    @kvmagent.replyerror
    @in_bash
    def create_bonding(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBondingResponse()

        try:
            try:
                for slave in cmd.slaves:
                    if self._has_vlan_or_bridge(slave.interfaceName) != 0:
                        raise Exception(slave.interfaceName + ' has a sub-interface or a bridge port')
            except Exception as e:
                rsp.error = 'unable to create bonding[%s], because %s' % (cmd.bondName, str(e))
                rsp.success = False
                return jsonobject.dumps(rsp)

            # zs-bond -c bond1 mode 802.ad xmitHashPolicy layer2+3
            if cmd.xmitHashPolicy is not None:
                shell.call('/usr/local/bin/zs-bond -c %s mode %s xmit_hash_policy %s' % (cmd.bondName, cmd.mode, cmd.xmitHashPolicy))
            else:
                # zs-bond -c bond1 mode active-backup
                shell.call('/usr/local/bin/zs-bond -c %s mode %s' % (cmd.bondName, cmd.mode))

            # zs-nic-to-bond -a bond2 nic3
            for slave in cmd.slaves:
                ret = shell.call('/usr/local/bin/zs-nic-to-bond -a %s %s' % (cmd.bondName, slave.interfaceName))
                if ret == 0:
                    shell.call('/usr/local/bin/zs-bond -d %s' % cmd.bondName)
        except Exception as e:
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
                if self._has_vlan_or_bridge(interface) != 0:
                    raise Exception(interface + ' has a sub-interface or a bridge port')

            if cmd.mode is not None or cmd.xmitHashPolicy is not None:
                mode = linux.read_file("/sys/class/net/%s/bonding/mode" % cmd.bondName)
                policy = linux.read_file("/sys/class/net/%s/bonding/xmit_hash_policy" % cmd.bondName)
                if cmd.mode != mode or cmd.xmitHashPolicy != policy:
                    # zs-bond -u bond1 mode 802.3ad
                    if cmd.xmitHashPolicy is None:
                        shell.call('/usr/local/bin/zs-bond -u %s mode %s' % (cmd.bondName, cmd.mode))
                    else:
                        shell.call('/usr/local/bin/zs-bond -u %s mode %s xmitHashPolicy %s' % (cmd.bondName, cmd.mode, cmd.xmitHashPolicy))

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
    def delete_bonding(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteBondingResponse()

        try:
            if self._has_vlan_or_bridge(cmd.bondName) == 0:
                # zs-bond -d bond2
                shell.call('/usr/local/bin/zs-bond -d %s' % cmd.bondName)
            else:
                raise Exception(cmd.bondName + ' has a sub-interface or a bridge port')

        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to delete bonding[%s], because %s' % (cmd.bondName, str(e))
            rsp.success = False

        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def create_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

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
            logger.debug('successfully realize bridge[%s] from device[%s]' % (cmd.bridgeName, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create bridge[%s] from device[%s], because %s' % (cmd.bridgeName, cmd.physicalInterfaceName, str(e))
            rsp.success = False
            
        return jsonobject.dumps(rsp)

    @lock.lock('bridge')
    @kvmagent.replyerror
    def create_vlan_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVlanBridgeResponse()
        vlanInterfName = '%s.%s' % (cmd.physicalInterfaceName, cmd.vlan)

        oldMtu = self._get_interface_mtu(vlanInterfName)
        mtu = cmd.mtu
        if oldMtu > cmd.mtu:
            mtu = oldMtu
        try:
            linux.create_vlan_bridge(cmd.bridgeName, cmd.physicalInterfaceName, cmd.vlan)
            self._configure_bridge(cmd.disableIptables)
            self._configure_bridge_mtu(cmd.bridgeName, vlanInterfName, mtu)
            self._configure_bridge_learning(cmd.bridgeName, vlanInterfName)
            linux.set_bridge_alias_using_phy_nic_name(cmd.bridgeName, cmd.physicalInterfaceName)
            linux.set_device_uuid_alias('%s.%s' % (cmd.physicalInterfaceName, cmd.vlan), cmd.l2NetworkUuid)
            logger.debug('successfully realize vlan bridge[name:%s, vlan:%s] from device[%s]' % (cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create vlan bridge[name:%s, vlan:%s] from device[%s], because %s' % (cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName, str(e))
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

        ips = set(map(lambda d: d.values()[0], nics))
        nicnames = list(set(map(lambda d: d.keys()[0], nics)))

        ''' there are 4 cases:
            1. there is no interface has ip address matched the vxlan or vxpool cidr
            2. there is only 1 interface with 1 ip address matched
            3. there is only 1 interface with more than 1 ip address matched
               in this case, we always return the first 1 ip address
            4. there has multiple interfaces with ip address matched
            #1, #4 will response error
        '''

        if len(nicnames) == 0:
            # case #1
            rsp.error = "can not find qualify interface for cidr [%s]" % cmd.cidr
        elif len(nicnames) == 1 and interf:
            # case #2 #3
            if nics[0].keys()[0] == interf:
                rsp.vtepIp = nics[0].values()[0]
                rsp.success = True
            else:
                rsp.error = "the interface with cidr [%s] is not the interface [%s] which provided" % (cmd.cidr, interf)
        elif len(nicnames) == 1:
            # case #2 #3
            rsp.vtepIp = nics[0].values()[0]
            rsp.success = True
        elif len(nicnames) > 1 and interf:
            # case #4
            for nic in nics:
                if nic.keys()[0] == interf:
                    rsp.vtepIp = nics[0].values()[0]
                    rsp.success = True
            if rsp.vtepIp == None:
                rsp.error = "no interface both qualify with cidr [%s] and interface name [%s] provided" % (cmd.cidr, interf)
        elif len(nicnames) == 2 and (linux.is_vif_on_bridge(nicnames[0], nicnames[1]) or linux.is_vif_on_bridge(nicnames[1], nicnames[0])):
            # Note(WeiW): This is a work around for case of a interface bound to a bridge and have same ip address,
            # see at zstackio/issues#4056, but note this wont make assurance that routing is true
            rsp.vtepIp = nics[0].values()[0]
            rsp.success = True
        elif len(nicnames) > 1 and len(ips) == 1:
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

        if cmd.dstport == None :
            cmd.dstport = VXLAN_DEFAULT_PORT
        linux.create_vxlan_interface(cmd.vni, cmd.vtepIp,cmd.dstport)

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
            linux.delete_novlan_bridge(cmd.bridgeName, cmd.physicalInterfaceName)
            logger.debug('successfully delete bridge[%s] with physical interface[%s]' % (
            cmd.bridgeName, cmd.physicalInterfaceName))
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
        vlanInterfName = '%s.%s' % (cmd.physicalInterfaceName, cmd.vlan)

        try:
            linux.delete_vlan_bridge(cmd.bridgeName, vlanInterfName)
            logger.debug('successfully delete vlan bridge[name:%s, vlan:%s] from device[%s]' % (
            cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'failed to delete vlan bridge[name:%s, vlan:%s] from device[%s], because %s' % (
                cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName, str(e))
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


    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_sync_uri(CHECK_PHYSICAL_NETWORK_INTERFACE_PATH, self.check_physical_network_interface)
        http_server.register_async_uri(ADD_INTERFACE_TO_BRIDGE_PATH, self.add_interface_to_bridge)
        http_server.register_async_uri(CREATE_BONDING_PATH, self.create_bonding)
        http_server.register_async_uri(UPDATE_BONDING_PATH, self.update_bonding)
        http_server.register_async_uri(DELETE_BONDING_PATH, self.delete_bonding)
        http_server.register_async_uri(KVM_REALIZE_L2NOVLAN_NETWORK_PATH, self.create_bridge)
        http_server.register_async_uri(KVM_REALIZE_L2VLAN_NETWORK_PATH, self.create_vlan_bridge)
        http_server.register_async_uri(KVM_CHECK_L2NOVLAN_NETWORK_PATH, self.check_bridge)
        http_server.register_async_uri(KVM_CHECK_L2VLAN_NETWORK_PATH, self.check_vlan_bridge)
        http_server.register_async_uri(KVM_CHECK_L2VXLAN_NETWORK_PATH, self.check_vxlan_cidr)
        http_server.register_async_uri(KVM_REALIZE_L2VXLAN_NETWORK_PATH, self.create_vxlan_bridge)
        http_server.register_async_uri(KVM_REALIZE_L2VXLAN_NETWORKS_PATH, self.create_vxlan_bridges)
        http_server.register_async_uri(KVM_POPULATE_FDB_L2VXLAN_NETWORK_PATH, self.populate_vxlan_fdb)
        http_server.register_async_uri(KVM_POPULATE_FDB_L2VXLAN_NETWORKS_PATH, self.populate_vxlan_fdbs)
        http_server.register_async_uri(KVM_SET_BRIDGE_ROUTER_PORT_PATH, self.set_bridge_router_port)
	
	http_server.register_async_uri(KVM_DELETE_L2NOVLAN_NETWORK_PATH, self.delete_novlan_bridge)
        http_server.register_async_uri(KVM_DELETE_L2VLAN_NETWORK_PATH, self.delete_vlan_bridge)
        http_server.register_async_uri(KVM_DELETE_L2VXLAN_NETWORK_PATH, self.delete_vxlan_bridge)
    def stop(self):
        pass

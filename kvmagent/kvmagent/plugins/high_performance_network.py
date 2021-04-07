'''

@author: haibiao.xiao
'''

import simplejson
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import ovs
from zstacklib.utils import shell
from zstacklib.utils import http

OVS_DPDK_NET_CHECK_BRIDGE = '/network/ovsdpdk/checkbridge'
OVS_DPDK_NET_CREATE_BRIDGE = '/network/ovsdpdk/createbridge'
OVS_DPDK_NET_GENERATE_VDPA = '/network/ovsdpdk/generatevdpa'
OVS_DPDK_NET_DELETE_VDPA = '/network/ovsdpdk/deletevdpa'

# TODO: Vxlan support

logger = log.get_logger(__name__)


def run_once(func):
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            wrapper.has_run = True
            return func(*args, **kwargs)
    wrapper.has_run = False
    return wrapper


class DeviceNotExistedError(Exception):
    pass


class CheckBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CheckBridgeCmd, self).__init__()
        self.bridgeName = None
        self.physicalInterfaceName = None


class CheckBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckBridgeResponse, self).__init__()


class CreateBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CreateBridgeCmd, self).__init__()
        self.physicalInterfaceName = None
        self.bridgeName = None


class CreateBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateBridgeResponse, self).__init__()

class GenerateVdpaResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GenerateVdpaResponse, self).__init__()
        self.vdpaPaths = None

class HighPerformanceNetworkPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    @run_once
    def _open_hw_offload(self):
        return shell.run("ovs-vsctl set Open_vSwitch . other_config:hw-offload=true")

    @run_once
    def _init_dpdk(self):
        return shell.run(
            "ovs-vsctl --timeout=5 --no-wait set Open_vSwitch . other_config:dpdk-init=true")
    
    @run_once
    def _init_mem(self):
        #TODO: caculater the memory
        return shell.run("ovs-vsctl --no-wait set Open_vSwitch . other_config:dpdk-socket-mem=4096")

    @kvmagent.replyerror
    def create_ovs_bridge(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        # set interface to vflag
        if not ovs.set_vflag(cmd.physicalInterfaceName):
            rsp.success = False
            rsp.error = "interface:{} is not supported to create an vflag.".format(
                cmd.physicalInterfaceName)
            return jsonobject.dumps(rsp)

        ovs.check_ovs_status()

        # bridge already exsit
        if cmd.bridgeName in ovs.get_bridges():
            return jsonobject.dumps(rsp)

        self._init_dpdk()
        self._open_hw_offload()
        self._init_mem()

        # create bridge
        shell.run('ovs-vsctl --timeout=5 add-br {} -- set Bridge {} datapath_type=netdev'.format(
            cmd.bridgeName, cmd.bridgeName))

        # check bridge creation
        if cmd.bridgeName not in ovs.get_bridges():
            rsp.success = False
            rsp.error = "create bridge:{} failed".format(cmd.bridgeName)
            return jsonobject.dumps(rsp)

        # attach bond to bridge
        if cmd.physicalInterfaceName in ovs.get_bridge_ports(cmd.bridgeName):
            return jsonobject.dumps(rsp)

        interfaces = ovs.get_bonds_interfaces([cmd.physicalInterfaceName])

        # add white list
        if not ovs.set_dpdk_white_list(interfaces):
            rsp.success = False
            rsp.error = 'add interfaces of bond:{} to DPDK white list failed'.format(
                cmd.physicalInterfaceName)
            return jsonobject.dumps(rsp)

        # To work with VF-LAG with OVS-DPDK, add the bond master (PF) to the bridge. Note that the first
        # PF on which you run "ip link set <PF> master bond0" becomes the bond master.
        pci_num = ovs.get_interface_pcinum(interfaces[0])

        if (interfaces or pci_num) is None:
            rsp.success = False
            rsp.error = 'bond:{} has no slaves'.format(
                cmd.physicalInterfaceName)
            return jsonobject.dumps(rsp)

        ret = shell.run('ovs-vsctl --timeout=5 add-port {} {} -- set Interface {} type=dpdk options:dpdk-devargs={} options:dpdklsc-interrupt=true'.format(
            cmd.bridgeName, cmd.physicalInterfaceName, cmd.physicalInterfaceName, pci_num))

        if ret != 0:
            rsp.success = False
            rsp.error = 'attach bond:{} to bridge:{} failed'.format(
                cmd.physicalInterfaceName, cmd.bridgeName)
            return jsonobject.dumps(rsp)

        bind_path = '/sys/class/net/{}/device/driver/bind'
        for i in interfaces:
            vf_pci_dict = ovs.get_vfs_dict(i)

            for p in vf_pci_dict:
                ovs.write_sysfs(bind_path.format(i), vf_pci_dict[p], True)

        ovs.restart_ovs()

        ovs.generate_all_vDPA(cmd.bridgeName, cmd.physicalInterfaceName)

        logger.debug(http.path_msg(OVS_DPDK_NET_CREATE_BRIDGE,
                                   'crate bridge:{}'.format(cmd.bridgeName)))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_ovs_bridge(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBridgeResponse()

        ovs.check_ovs_status()

        if cmd.bridgeName not in ovs.get_bridges():
            rsp.success = False
            rsp.error = "can not find bridge:{}".format(cmd.bridgeName)
            return jsonobject.dumps(rsp)

        if cmd.physicalInterfaceName not in ovs.get_bridge_ports(cmd.bridgeName):
            raise DeviceNotExistedError(
                'cannot find {}'.format(cmd.physicalInterfaceName))

        logger.debug(http.path_msg(OVS_DPDK_NET_CHECK_BRIDGE,
                                   'check bridges:{}'.format(cmd.bridgeName)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def generate_vdpa(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateVdpaResponse()

        rsp.vdpaPaths = []
        for nic in cmd.nics:
            rsp.vdpaPaths.append(ovs.get_vDPA(cmd.vmUuid, nic))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_vdpa(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        ovs.free_vDPA(cmd.vmUuid)

        return jsonobject.dumps(rsp)

    def start(self):

        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(
            OVS_DPDK_NET_CHECK_BRIDGE, self.check_ovs_bridge)
        http_server.register_async_uri(
            OVS_DPDK_NET_CREATE_BRIDGE, self.create_ovs_bridge)
        http_server.register_async_uri(
            OVS_DPDK_NET_GENERATE_VDPA, self.generate_vdpa)
        http_server.register_async_uri(
            OVS_DPDK_NET_DELETE_VDPA, self.delete_vdpa)
        # clear ovsdb
        ovs.clear_ovsdb()

    def stop(self):
        pass

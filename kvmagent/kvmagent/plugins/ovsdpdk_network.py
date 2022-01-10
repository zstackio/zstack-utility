'''

@author: haibiao.xiao
'''
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import ovs
from zstacklib.utils import http

OVS_DPDK_NET_CHECK_BRIDGE = '/network/ovsdpdk/checkbridge'
OVS_DPDK_NET_CREATE_BRIDGE = '/network/ovsdpdk/createbridge'
OVS_DPDK_NET_DELETE_BRIDGE = '/network/ovsdpdk/deletebridge'
OVS_DPDK_NET_GENERATE_VDPA = '/network/ovsdpdk/generatevdpa'
OVS_DPDK_NET_DELETE_VDPA = '/network/ovsdpdk/deletevdpa'

# TODO: Vxlan support

logger = log.get_logger(__name__)


class OvsError(Exception):
    '''ovs error'''


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


class DeleteBridgeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteBridgeCmd, self).__init__()
        self.physicalInterfaceName = None
        self.bridgeName = None


class DeleteBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteBridgeResponse, self).__init__()


class GenerateVdpaCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GenerateVdpaCmd, self).__init__()
        self.vmUuid = None
        self.nics = None


class GenerateVdpaResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GenerateVdpaResponse, self).__init__()
        self.vdpaPaths = None


class DeleteVdpaCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteVdpaCmd, self).__init__()
        self.vmUuid = None
        self.nicInternalName = None


class OvsDpdkNetworkPlugin(kvmagent.KvmAgent):
    '''
    High performance Network base on ovs-dpdk and vdpa.
    '''

    @kvmagent.replyerror
    def create_ovs_bridge(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        venv = ovs.OvsVenv()

        if not venv.ready:
            rsp.success = False
            rsp.error = "host can not support ovs"
            return jsonobject.dumps(rsp)

        ovsctl = ovs.OvsCtl(venv)

        if ovsctl.isKernelBond(cmd.physicalInterfaceName):
            rsp.success = False
            rsp.error = "OvsDpdk do not support kernel bond. Please use dpdk bond instead"
            return jsonobject.dumps(rsp)

        # prepare bridge
        if not ovsctl.prepareBridge(cmd.bridgeName, cmd.physicalInterfaceName):
            rsp.success = False
            rsp.error = "create Bridge for interface:{} failed.".format(
                cmd.physicalInterfaceName)
            return jsonobject.dumps(rsp)

        # It will take a long time for ovs-vswitchd to restart,
        # while there has many vDPA configured. never force restart ovs-vswitchd
        ovsctl.startSwitch()

        logger.debug(http.path_msg(OVS_DPDK_NET_CREATE_BRIDGE,
                                   'create bridge:{} success'.format(cmd.bridgeName)))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_ovs_bridge(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBridgeResponse()

        venv = ovs.OvsVenv()

        if not venv.ready:
            rsp.success = False
            rsp.error = "host can not support ovs"
            return jsonobject.dumps(rsp)

        ovsctl = ovs.OvsCtl(venv)

        ovsctl.reconfigOvs()

        if cmd.bridgeName not in ovsctl.listBrs():
            rsp.success = False
            rsp.error = "can not find bridge:{}".format(cmd.bridgeName)
            return jsonobject.dumps(rsp)

        if cmd.physicalInterfaceName not in ovsctl.listPorts(cmd.bridgeName):
            raise OvsError(
                'cannot find {}'.format(cmd.physicalInterfaceName))

        logger.debug(http.path_msg(OVS_DPDK_NET_CHECK_BRIDGE,
                                   'check bridges:{}'.format(cmd.bridgeName)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_ovs_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        venv = ovs.OvsVenv()

        if not venv.ready:
            rsp.success = False
            rsp.error = "host can not support ovs"
            return jsonobject.dumps(rsp)

        ovsctl = ovs.OvsCtl(venv)

        if cmd.bridgeName not in ovsctl.listBrs():
            rsp.success = False
            rsp.error = "no such bridge named:{}.".format(
                cmd.bridgeName)
            return jsonobject.dumps(rsp)

        ovsctl.deleteBr(cmd.bridgeName)

        logger.debug(http.path_msg(OVS_DPDK_NET_CREATE_BRIDGE,
                                   'delete bridge:{} success'.format(cmd.bridgeName)))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def generate_vdpa(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateVdpaResponse()

        venv = ovs.OvsVenv()

        if not venv.ready:
            rsp.success = False
            rsp.error = "host can not support ovs"
            return jsonobject.dumps(rsp)

        ovsctl = ovs.OvsCtl(venv)

        rsp.vdpaPaths = []
        for nic in cmd.nics:
            if nic.type == 'vDPA':
                rsp.vdpaPaths.extend(ovsctl.getVdpa(cmd.vmUuid, nic))

        if rsp.vdpaPaths is None:
            rsp.success = False
            rsp.error = "vDPA resource exhausted."
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_vdpa(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        venv = ovs.OvsVenv()

        if not venv.ready:
            rsp.success = False
            rsp.error = "host can not support ovs"
            return jsonobject.dumps(rsp)

        ovsctl = ovs.OvsCtl(venv)
        if hasattr(cmd, "nicInternalName"):
            ovsctl.freeVdpa(cmd.vmUuid, cmd.nicInternalName)
        else:
            ovsctl.freeVdpa(cmd.vmUuid)

        return jsonobject.dumps(rsp)

    def start(self):

        ovs.OvsCtl().reconfigOvs()

        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(
            OVS_DPDK_NET_CHECK_BRIDGE, self.check_ovs_bridge)
        http_server.register_async_uri(
            OVS_DPDK_NET_CREATE_BRIDGE, self.create_ovs_bridge)
        http_server.register_async_uri(
            OVS_DPDK_NET_DELETE_BRIDGE, self.delete_ovs_bridge)
        http_server.register_async_uri(
            OVS_DPDK_NET_GENERATE_VDPA, self.generate_vdpa)
        http_server.register_async_uri(
            OVS_DPDK_NET_DELETE_VDPA, self.delete_vdpa)

    def stop(self):
        pass

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
OVS_DPDK_NET_GENERATE_VDPA = '/network/ovsdpdk/generatevdpa'
OVS_DPDK_NET_DELETE_VDPA = '/network/ovsdpdk/deletevdpa'

# TODO: Vxlan support

logger = log.get_logger(__name__)
ovsctl = None


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
    High performance Network base on ovs-dpdk and vdpa.
    '''

    @kvmagent.replyerror
    def create_ovs_bridge(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        # prepare vf lag
        if not ovsctl.prepareBridge(cmd.bridgeName, cmd.physicalInterfaceName):
            rsp.success = False
            rsp.error = "interface:{} is not supported to create an vflag.".format(
                cmd.physicalInterfaceName)
            return jsonobject.dumps(rsp)

        ovsctl.startSwitch(True)

        logger.debug(http.path_msg(OVS_DPDK_NET_CREATE_BRIDGE,
                                   'create bridge:{} success'.format(cmd.bridgeName)))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_ovs_bridge(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBridgeResponse()

        if cmd.bridgeName not in ovsctl.listBrs():
            rsp.success = False
            rsp.error = "can not find bridge:{}".format(cmd.bridgeName)
            return jsonobject.dumps(rsp)

        if cmd.physicalInterfaceName not in ovsctl.listPorts(cmd.bridgeName):
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
            rsp.vdpaPaths.append(ovsctl.getVdpa(cmd.vmUuid, nic))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_vdpa(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        ovsctl.freeVdpa(cmd.vmUuid)

        return jsonobject.dumps(rsp)

    def start(self):
        global ovsctl
        ovsctl = ovs.OvsCtl()
        if not ovsctl.initVdpaSupport():
            logger.debug("ovs can not support dpdk.")
            return
        ovsctl.start(True)

        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(
            OVS_DPDK_NET_CHECK_BRIDGE, self.check_ovs_bridge)
        http_server.register_async_uri(
            OVS_DPDK_NET_CREATE_BRIDGE, self.create_ovs_bridge)
        http_server.register_async_uri(
            OVS_DPDK_NET_GENERATE_VDPA, self.generate_vdpa)
        http_server.register_async_uri(
            OVS_DPDK_NET_DELETE_VDPA, self.delete_vdpa)

    def stop(self):
        pass

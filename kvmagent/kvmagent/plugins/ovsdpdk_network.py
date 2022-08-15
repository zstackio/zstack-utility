'''

@author: haibiao.xiao
'''
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import ovs
from zstacklib.utils.ovs import OvsError
from zstacklib.utils import http

OVS_DPDK_NET_CHECK_BRIDGE = '/network/ovsdpdk/checkbridge'
OVS_DPDK_NET_CREATE_BRIDGE = '/network/ovsdpdk/createbridge'
OVS_DPDK_NET_DELETE_BRIDGE = '/network/ovsdpdk/deletebridge'
OVS_DPDK_NET_GENERATE_VDPA = '/network/ovsdpdk/generatevdpa'
OVS_DPDK_NET_DELETE_VDPA = '/network/ovsdpdk/deletevdpa'
OVS_DPDK_NET_GENERATE_DPDKVHOSTUSERCLIENT = '/network/ovsdpdk/addvhostuserclient'
OVS_DPDK_NET_DELETE_DPDKVHOSTUSERCLIENT = '/network/ovsdpdk/deletevhostuserclient'
# TODO: Vxlan support

logger = log.get_logger(__name__)


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


class DeleteVdpaResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteVdpaResponse, self).__init__()


class AddDpdkVhostUserClientCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(AddDpdkVhostUserClientCmd, self).__init__()
        self.vmUuid = None
        self.nics = None


class AddDpdkVhostUserClientResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(AddDpdkVhostUserClientResponse, self).__init__()


class DeleteDpdkVhostUserClientCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteDpdkVhostUserClientCmd, self).__init__()
        self.vmUuid = None
        self.nicInternalName = None


class DeleteDpdkVhostUserClientResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteDpdkVhostUserClientResponse, self).__init__()


class OvsDpdkNetworkPlugin(kvmagent.KvmAgent):
    '''
    High performance Network Plugin.
    '''

    @kvmagent.replyerror
    def create_ovs_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        ovsctl.prepareBridge(cmd.physicalInterfaceName, cmd.bridgeName)

        logger.debug(http.path_msg(OVS_DPDK_NET_CREATE_BRIDGE,
                                   'create bridge:{} success.'.format(cmd.bridgeName)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_ovs_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBridgeResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        ovsctl.reconfigOvs()
        if cmd.bridgeName not in ovsctl.listBrs():
            raise OvsError("can not find bridge:{}".format(cmd.bridgeName))
        if cmd.physicalInterfaceName not in ovsctl.listPorts(cmd.bridgeName):
            raise OvsError('cannot find interface:{}'.format(cmd.physicalInterfaceName))

        logger.debug(http.path_msg(OVS_DPDK_NET_CHECK_BRIDGE,
                                   'check bridges:{} success.'.format(cmd.bridgeName)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_ovs_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        if cmd.bridgeName not in ovsctl.listBrs():
            raise OvsError("no such bridge named:{}.".format(cmd.bridgeName))
        ovsctl.deleteBr(cmd.bridgeName)

        logger.debug(http.path_msg(OVS_DPDK_NET_DELETE_BRIDGE,
                                   'delete bridge:{} success'.format(cmd.bridgeName)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def generate_vdpa(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateVdpaResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        rsp.vdpaPaths = []
        for nic in cmd.nics:
            if nic.type == 'vDPA':
                rsp.vdpaPaths.extend(ovsctl.createNicBackend(cmd.vmUuid, nic))

        logger.debug(http.path_msg(OVS_DPDK_NET_GENERATE_VDPA,
                                   'generate vdpa for vm:{} success'.format(cmd.vmUuid)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_vdpa(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteVdpaResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        if hasattr(cmd, "nicInternalName"):
            ovsctl.destoryNicBackend(cmd.vmUuid, cmd.nicInternalName)
        else:
            ovsctl.destoryNicBackend(cmd.vmUuid)

        logger.debug(http.path_msg(OVS_DPDK_NET_DELETE_VDPA,
                                   'delete vdpa of vm:{} success'.format(cmd.vmUuid)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def add_dpdkvhostuserclient(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AddDpdkVhostUserClientResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        for nic in cmd.nics:
            if nic.type == 'dpdkvhostuserclient':
                ovsctl.createNicBackend(cmd.vmUuid, nic)

        logger.debug(http.path_msg(OVS_DPDK_NET_GENERATE_DPDKVHOSTUSERCLIENT,
                                   'add dpdkvhostuserclient for vm:{} success'.format(cmd.vmUuid)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_dpdkvhostuserclient(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteDpdkVhostUserClientResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        if hasattr(cmd, "nicInternalName"):
            ovsctl.destoryNicBackend(cmd.vmUuid, cmd.nicInternalName)
        else:
            ovsctl.destoryNicBackend(cmd.vmUuid)

        logger.debug(http.path_msg(OVS_DPDK_NET_DELETE_DPDKVHOSTUSERCLIENT,
                                   'delete dpdkvhostuserclient of vm:{} success'.format(cmd.vmUuid)))
        return jsonobject.dumps(rsp)

    def start(self):

        try:
            ovs.getOvsCtl(with_dpdk=True).reconfigOvs()
        except Exception as err:
            logger.warn("Reconfig ovs failed. {}".format(err))

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
        http_server.register_async_uri(
            OVS_DPDK_NET_GENERATE_DPDKVHOSTUSERCLIENT, self.add_dpdkvhostuserclient)
        http_server.register_async_uri(
            OVS_DPDK_NET_DELETE_DPDKVHOSTUSERCLIENT, self.delete_dpdkvhostuserclient)

    def stop(self):
        pass

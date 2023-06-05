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

OVS_DPDK_NET_RESOURCE_CONFIGURE = '/network/ovsdpdk/resource/configure'
OVS_DPDK_NET_SMARTNICS_INIT = '/network/ovsdpdk/smartnics/init'
OVS_DPDK_NET_SMARTNICS_RESTORE='/network/ovsdpdk/smartnics/recover'
OVS_DPDK_NET_SYNC='/network/ovsdpdk/sync'


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


class SmartnicsInitCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SmartnicsInitCmd, self).__init__()
        self.physicalInterfaceName = None
        self.socketMem = None
        #self.virtPartNum = None
        self.reserveSize = None
        self.pageSize = None
        self.reInit = None

class SmartnicsInitResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SmartnicsInitResponse, self).__init__()

class SmartnicsRestoreCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SmartnicsRestoreCmd, self).__init__()
        self.physicalInterfaceName = None

class SmartnicsRestoreResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SmartnicsRestoreResponse, self).__init__()

class ResourceConfigureCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ResourceConfigureCmd, self).__init__()
        self.reserveSize = None
        self.pageSize = None

class ResourceConfigureResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ResourceConfigureResponse, self).__init__()

class DpdkovsSyncCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DpdkovsSyncCmd, self).__init__()
        self.ovsBridgeInfo = None

class DpdkovsSyncResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DpdkovsSyncResponse, self).__init__()

class OvsDpdkNetworkPlugin(kvmagent.KvmAgent):
    '''
    High performance Network Plugin.
    '''

    @kvmagent.replyerror
    def create_ovs_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)

        if not ovsctl.ovs.isOvsProcRunning("ovs-vswitchd"):
            logger.debug(http.path_msg(OVS_DPDK_NET_CREATE_BRIDGE,
                                   'create bridge:{} failed, becauseof ovs-vswitchd not running.'.format(cmd.bridgeName)))
            
            rsp.error = "create bridge failed"
            rsp.success = False
            return jsonobject.dumps(rsp)

        res = ovsctl.prepareBridge(cmd.physicalInterfaceName, cmd.bridgeName)
        if res == -1:
            logger.debug(http.path_msg(OVS_DPDK_NET_CREATE_BRIDGE,
                                   'create bridge:{} failed'.format(cmd.bridgeName)))
            
            rsp.error = "create bridge failed"
            rsp.success = False
            return jsonobject.dumps(rsp)

        logger.debug(http.path_msg(OVS_DPDK_NET_CREATE_BRIDGE,
                                   'create bridge:{} success.'.format(cmd.bridgeName)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_ovs_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBridgeResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        if not ovsctl.ovs.isOvsProcRunning("ovs-vswitchd"):
            logger.debug(http.path_msg(OVS_DPDK_NET_CHECK_BRIDGE,
                                   'check bridge:{} failed, becauseof ovs-vswitchd not running.'.format(cmd.bridgeName)))
            
            rsp.error = "check bridge failed"
            rsp.success = False
            return jsonobject.dumps(rsp)

        if cmd.bridgeName not in ovsctl.listBrs():
            logger.debug(http.path_msg(OVS_DPDK_NET_CHECK_BRIDGE,
                                   'check bridge:{} failed, becauseof bridge not exist'.format(cmd.bridgeName)))

            rsp.error = "check bridge failed"
            rsp.success = False
            return jsonobject.dumps(rsp)
        if cmd.physicalInterfaceName not in ovsctl.listPorts(cmd.bridgeName):
            logger.debug(http.path_msg(OVS_DPDK_NET_CHECK_BRIDGE,
                                   'check bridge failed, becauseof pf nic:{} not exist'.format(cmd.physicalInterfaceName)))

            rsp.error = "check bridge failed"
            rsp.success = False
            return jsonobject.dumps(rsp)

        logger.debug(http.path_msg(OVS_DPDK_NET_CHECK_BRIDGE,
                                   'check bridges:{} success.'.format(cmd.bridgeName)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_ovs_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        if not ovsctl.ovs.isOvsProcRunning("ovs-vswitchd"):
            logger.debug(http.path_msg(OVS_DPDK_NET_DELETE_BRIDGE,
                                   'delete bridge:{} failed, becauseof ovs-vswitchd not running.'.format(cmd.bridgeName)))
            
            rsp.error = "delete bridge failed"
            rsp.success = False
            return jsonobject.dumps(rsp)

        if cmd.bridgeName not in ovsctl.listBrs():
            logger.debug(http.path_msg(OVS_DPDK_NET_DELETE_BRIDGE,
                                   'bridge:{} already delete, no need to do again'.format(cmd.bridgeName)))
            return jsonobject.dumps(rsp)

        try:
            ovsctl.deleteBr(cmd.bridgeName)
        except:
            logger.debug(http.path_msg(OVS_DPDK_NET_DELETE_BRIDGE,
                                   'delete bridge:{} failed'.format(cmd.bridgeName)))
            rsp.error = "delete bridge failed"
            rsp.success = False
            return jsonobject.dumps(rsp)
                   

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
                res = ovsctl.createNicBackend(cmd.vmUuid, nic)
                if res is not None:
                    rsp.vdpaPaths.extend(res)

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


    @kvmagent.replyerror
    def smartnics_restore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SmartnicsRestoreResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        res = ovsctl.smartNicRestore(cmd.physicalInterfaceName)
        if res == -1:
            rsp.error = "smartnics recover failed"
            rsp.success = False

            logger.debug(http.path_msg(OVS_DPDK_NET_SMARTNICS_RESTORE,
                                       'smartnics recover:{} failed.'.format(cmd.physicalInterfaceName)))
            return jsonobject.dumps(rsp)
   
        logger.debug(http.path_msg(OVS_DPDK_NET_SMARTNICS_RESTORE,
                                   'smartnics recover:{} success.'.format(cmd.physicalInterfaceName)))
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def smartnics_init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SmartnicsInitResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        res = ovsctl.smartNicInit(cmd.physicalInterfaceName, cmd.reserveSize, cmd.pageSize, cmd.socketMem, cmd.reInit)
        if res == -1:
            rsp.error = "smartnics init failed"
            rsp.success = False

            logger.debug(http.path_msg(OVS_DPDK_NET_SMARTNICS_INIT,
                                       'smartnics init:{} failed.'.format(cmd.physicalInterfaceName)))
            return jsonobject.dumps(rsp)
   
        logger.debug(http.path_msg(OVS_DPDK_NET_SMARTNICS_INIT,
                                   'smartnics init:{} success.'.format(cmd.physicalInterfaceName)))
        return jsonobject.dumps(rsp)
    
    @kvmagent.replyerror
    def resource_configure(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ResourceConfigureResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        res = ovsctl.resourceConfigure(cmd.reserveSize, cmd.pageSize)
        if res == -1:
            rsp.error = "hugepage config failed"
            rsp.success = False

            logger.debug(http.path_msg(OVS_DPDK_NET_RESOURCE_CONFIGURE,
                                       'resource configure hugepage number:{} failed.'.format(cmd.reserveSize)))
            return jsonobject.dumps(rsp)

        logger.debug(http.path_msg(OVS_DPDK_NET_RESOURCE_CONFIGURE,
                                   'resource configure hugepage number:{} success.'.format(cmd.reserveSize)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def dpdkovs_sync(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DpdkovsSyncResponse()

        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        res = ovsctl.dpdkOvsSync(cmd.ovsBridgeInfo)
        if res == -1:
            rsp.error = "sync bridge and port info failed"
            rsp.success = False

            logger.debug(http.path_msg(OVS_DPDK_NET_SYNC,
                                       'sync bridge info:{} failed.'.format(jsonobject.dumps(cmd))))
            return jsonobject.dumps(rsp)

        logger.debug(http.path_msg(OVS_DPDK_NET_SYNC,
                                   'sync bridge info:{} success.'.format(jsonobject.dumps(cmd))))
        return jsonobject.dumps(rsp)


    def start(self):

        #try:
        #    ovs.getOvsCtl(with_dpdk=True).reconfigOvs()
        #except Exception as err:
        #    logger.warn("Reconfig ovs failed. {}".format(err))

        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(
            OVS_DPDK_NET_RESOURCE_CONFIGURE, self.resource_configure)
        http_server.register_async_uri(
            OVS_DPDK_NET_SMARTNICS_INIT, self.smartnics_init)
        http_server.register_async_uri(
            OVS_DPDK_NET_SMARTNICS_RESTORE, self.smartnics_restore)
        http_server.register_async_uri(
            OVS_DPDK_NET_SYNC, self.dpdkovs_sync)

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

        check_bond_status()

    def stop(self):
        pass

def check_bond_status():
    ovsctl = ovs.getOvsCtl(with_dpdk=True)
    ovsctl.checkBondStatusWapper()




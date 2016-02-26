'''

@author: frank
'''
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import lock
from zstacklib.utils import shell
from zstacklib.utils import linux
import os
import traceback

CHECK_PHYSICAL_NETWORK_INTERFACE_PATH = '/network/checkphysicalnetworkinterface'
KVM_REALIZE_L2NOVLAN_NETWORK_PATH = "/network/l2novlan/createbridge"
KVM_REALIZE_L2VLAN_NETWORK_PATH = "/network/l2vlan/createbridge"
KVM_CHECK_L2NOVLAN_NETWORK_PATH = "/network/l2novlan/checkbridge"
KVM_CHECK_L2VLAN_NETWORK_PATH = "/network/l2vlan/checkbridge"

logger = log.get_logger(__name__)

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

class CreateVlanBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateVlanBridgeResponse, self).__init__()

class CheckBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckBridgeResponse, self).__init__()

class CheckVlanBridgeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckVlanBridgeResponse, self).__init__()


class NetworkPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    def _ifup_device_if_down(self, device_name):
        state_path = '/sys/class/net/%s/operstate' % device_name

        if not os.path.exists(state_path):
            raise Exception('cannot find %s' % state_path)

        with open(state_path, 'r') as fd:
            state = fd.read()

        if 'up' in state:
            return

        shell.call('ip link set %s up' % device_name)

    def _configure_bridge(self):
        shell.call('echo 1 > /proc/sys/net/bridge/bridge-nf-call-iptables')
        shell.call('echo 1 > /proc/sys/net/ipv4/conf/default/forwarding')

    @kvmagent.replyerror
    def check_physical_network_interface(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckPhysicalNetworkInterfaceResponse()
        for i in cmd.interfaceNames:
            shell_cmd = shell.ShellCmd("ip link | grep '%s'" % i)
            shell_cmd(False)
            if shell_cmd.return_code != 0:
                rsp.failedInterfaceNames = [i]
                rsp.success = False
                return jsonobject.dumps(rsp)

        for i in cmd.interfaceNames:
            self._ifup_device_if_down(i)

        logger.debug(http.path_msg(CHECK_PHYSICAL_NETWORK_INTERFACE_PATH, 'checked physical interfaces: %s' % cmd.interfaceNames))
        return jsonobject.dumps(rsp)

    @lock.lock('create_bridge')
    @kvmagent.replyerror
    def create_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateBridgeResponse()

        self._ifup_device_if_down(cmd.physicalInterfaceName)

        if linux.is_vif_on_bridge(cmd.bridgeName, cmd.physicalInterfaceName):
            logger.debug('%s is a bridge device. Interface %s is attached to bridge. No need to create bridge or attach device interface' % (cmd.bridgeName, cmd.physicalInterfaceName))
            self._configure_bridge()
            return jsonobject.dumps(rsp)
        
        try:
            linux.create_bridge(cmd.bridgeName, cmd.physicalInterfaceName)
            self._configure_bridge()
            logger.debug('successfully realize bridge[%s] from device[%s]' % (cmd.bridgeName, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create bridge[%s] from device[%s], because %s' % (cmd.bridgeName, cmd.physicalInterfaceName, str(e))
            rsp.success = False
            
        return jsonobject.dumps(rsp)
    
    @lock.lock('create_bridge')
    @kvmagent.replyerror
    def create_vlan_bridge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVlanBridgeResponse()

        if linux.is_bridge(cmd.bridgeName):
            logger.debug('%s is a bridge device, no need to create bridge' % cmd.bridgeName)
            self._ifup_device_if_down('%s.%s' % (cmd.physicalInterfaceName, cmd.vlan))
            self._configure_bridge()
            return jsonobject.dumps(rsp)
        
        try:
            linux.create_vlan_bridge(cmd.bridgeName, cmd.physicalInterfaceName, cmd.vlan)
            self._configure_bridge()
            logger.debug('successfully realize vlan bridge[name:%s, vlan:%s] from device[%s]' % (cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName))
        except Exception as e:
            logger.warning(traceback.format_exc())
            rsp.error = 'unable to create vlan bridge[name:%s, vlan:%s] from device[%s], because %s' % (cmd.bridgeName, cmd.vlan, cmd.physicalInterfaceName, str(e))
            rsp.success = False
            
        return jsonobject.dumps(rsp)

    @lock.lock('create_bridge')
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

    @lock.lock('create_bridge')
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

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_sync_uri(CHECK_PHYSICAL_NETWORK_INTERFACE_PATH, self.check_physical_network_interface)
        http_server.register_async_uri(KVM_REALIZE_L2NOVLAN_NETWORK_PATH, self.create_bridge)
        http_server.register_async_uri(KVM_REALIZE_L2VLAN_NETWORK_PATH, self.create_vlan_bridge)
        http_server.register_async_uri(KVM_CHECK_L2NOVLAN_NETWORK_PATH, self.check_bridge)
        http_server.register_async_uri(KVM_CHECK_L2VLAN_NETWORK_PATH, self.check_vlan_bridge)

    def stop(self):
        pass

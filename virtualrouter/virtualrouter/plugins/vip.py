'''

@author: frank
'''
from virtualrouter import virtualrouter
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import lock

logger = log.get_logger(__name__)

class VipTO(object):
    def __init__(self):
        self.ip = None
        self.netmask = None
        self.gateway = None
        self.ownerEthernetMac= None

class CreateVipCmd(virtualrouter.AgentCommand):
    def __init__(self):
        super(CreateVipCmd, self).__init__()
        self.vips = None

class CreateVipRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(CreateVipRsp, self).__init__()

class RemoveVipCmd(virtualrouter.AgentCommand):
    def __init__(self):
        super(RemoveVipCmd, self).__init__()
        self.vips = None

class RemoveVipRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(RemoveVipRsp, self).__init__()


class Vip(virtualrouter.VRAgent):
    VR_CREATE_VIP = "/createvip"
    VR_REMOVE_VIP = "/removevip"

    @virtualrouter.replyerror
    @lock.lock('vip')
    def remove_vip(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for vip in cmd.vips:
            linux.delete_vip_by_ip_if_exists(vip.ip)
            logger.debug('removed vip %s' % jsonobject.dumps(vip))
        
        rsp = RemoveVipRsp()
        return jsonobject.dumps(rsp)
    
    @virtualrouter.replyerror
    @lock.lock('vip')
    def create_vip(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for vip in cmd.vips:
            linux.create_vip_if_not_exists(vip.ownerEthernetMac, vip.ip, vip.netmask)
            logger.debug('created vip %s' % jsonobject.dumps(vip))
        
        rsp = CreateVipRsp()
        return jsonobject.dumps(rsp)

    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.VR_CREATE_VIP, self.create_vip)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.VR_REMOVE_VIP, self.remove_vip)
    
    def stop(self):
        pass

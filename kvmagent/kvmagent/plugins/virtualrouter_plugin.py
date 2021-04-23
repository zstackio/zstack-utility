'''

@author: Frank
'''

from kvmagent import kvmagent
from zstacklib.utils import linux
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import shell
from zstacklib.utils import log
import os
import os.path
import tempfile
import shutil
import socket

class BootstrapIsoInfo(object):
    def __init__(self):
        self.managementNicIp = None
        self.managementNicNetmask = None
        self.managementNicGateway = None
        self.managementNicMac = None
        
class CreateVritualRouterBootstrapIsoCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CreateVritualRouterBootstrapIsoCmd, self).__init__()
        self.isoInfo = None
        self.isoPath = None

class CreateVritualRouterBootstrapIsoRsp(kvmagent.AgentCommand): 
    def __init__(self):
        super(CreateVritualRouterBootstrapIsoRsp, self).__init__()
        
class DeleteVirtualRouterBootstrapIsoCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteVirtualRouterBootstrapIsoCmd, self).__init__()
        self.isoPath = None

class DeleteVirtualRouterBootstrapIsoRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteVirtualRouterBootstrapIsoRsp, self).__init__()

class PrepareBootstrapInfoRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(PrepareBootstrapInfoRsp, self).__init__()
        
logger = log.get_logger(__name__)

class VirtualRouterPlugin(kvmagent.KvmAgent):
    VR_KVM_CREATE_BOOTSTRAP_ISO_PATH = "/virtualrouter/createbootstrapiso"
    VR_KVM_DELETE_BOOTSTRAP_ISO_PATH = "/virtualrouter/deletebootstrapiso" 
    VR_KVM_SET_BOOTSTRAP_INFO_PATH = "/appliancevm/setbootstrapinfo"
    
    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.VR_KVM_CREATE_BOOTSTRAP_ISO_PATH, self.create_bootstrap_iso)
        http_server.register_async_uri(self.VR_KVM_DELETE_BOOTSTRAP_ISO_PATH, self.delete_bootstrap_iso)
        http_server.register_async_uri(self.VR_KVM_SET_BOOTSTRAP_INFO_PATH, self.set_bootstrap_info)
    
    def stop(self):
        pass
    
    @kvmagent.replyerror
    def set_bootstrap_info(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        info = jsonobject.dumps(cmd.info, True)
        socket_path = cmd.socketPath
        
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1)
        if cmd.bootStrapInfoTimeout is not None:
            timeout = int(cmd['bootStrapInfoTimeout'])
            s.settimeout(timeout)
        buf_size = s.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        info_len = len(info)
        if info_len < buf_size:
            # as there is no fflush() in python, we have to create a message
            # matching to the socket buffer to force it to send the message immediately
            padding_len = buf_size - info_len
            padding = ' ' * padding_len
            info = '%s%s' % (info, padding)

        try:
            logger.debug('send appliance vm bootstrap info to %s\n%s' % (socket_path, info))
            s.connect(socket_path)
            s.sendall(info)
        finally:
            s.close()
        
        rsp = PrepareBootstrapInfoRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_bootstrap_iso(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        isoinfo = jsonobject.dumps(cmd.isoInfo, True)
        tmpfile = linux.write_to_temp_file(isoinfo)
        isodir = tempfile.mkdtemp()
        try:
            dst = os.path.join(isodir, 'cmdline.json')
            shell.ShellCmd('cp %s %s' % (tmpfile, dst))()
            shell.ShellCmd('/usr/bin/mkisofs -quiet -r -o %s %s' % (cmd.isoPath, isodir))()
            return jsonobject.dumps(CreateVritualRouterBootstrapIsoRsp())
        finally:
            if not isodir:
                shutil.rmtree(isodir)
            if not tmpfile:
                os.remove(tmpfile)
    
    @kvmagent.replyerror
    def delete_bootstrap_iso(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        linux.rm_file_force(cmd.isoPath)
        return jsonobject.dumps(DeleteVirtualRouterBootstrapIsoRsp())

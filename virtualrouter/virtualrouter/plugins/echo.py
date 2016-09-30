'''

@author: Frank
'''
from virtualrouter import virtualrouter
from zstacklib.utils import shell
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

class EchoPlugin(virtualrouter.VRAgent):
    ECHO_PATH = "/echo"
    
    def start(self):
        virtualrouter.VirtualRouter.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        
    def stop(self):
        pass
    
    def echo(self, req):
        logger.debug('get echoed')
        return ""
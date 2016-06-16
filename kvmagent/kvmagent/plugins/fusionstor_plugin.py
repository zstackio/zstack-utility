'''

@author: frank
'''

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import lichbd
from zstacklib.utils import sizeunit
from zstacklib.utils import linux
from zstacklib.utils import thread
import os.path
import re
import threading
import time

logger = log.get_logger(__name__)


class FusionstorPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''
    KVM_FUSIONSTOR_QUERY_PATH = "/fusionstor/query"

    @kvmagent.replyerror
    def fusionstor_query(self, req):
        protocol = lichbd.get_protocol()
        if protocol == 'lichbd':
            lichbd.makesure_qemu_img_with_lichbd()
        elif protocol == 'sheepdog' or protocol == 'nbd':
            pass
        else:
            raise shell.ShellError('Do not supprot protocols, only supprot lichbd, sheepdog and nbd')

        o = shell.call('lich.node --stat 2>/dev/null')
        if 'running' not in o:
            raise shell.ShellError('the lichd process of this node is not running, Please check the lichd service')

        return jsonobject.dumps(kvmagent.AgentResponse())

    def start(self):
        self.host_uuid = None
        
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.KVM_FUSIONSTOR_QUERY_PATH, self.fusionstor_query)

    def stop(self):
        pass

    def configure(self, config):
        self.config = config

'''

@author: Frank
'''

from zstacklib.utils import plugin
from zstacklib.utils import log
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import shell
from zstacklib.utils import daemon
from zstacklib.utils import iptables
import os.path
import traceback
import pprint
import functools

class VRAgent(plugin.Plugin):
    pass

class VirtualRouterError(Exception):
    '''vritual router error'''


logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

class AgentCommand(object):
    def __init__(self):
        pass

class InitRsp(AgentResponse):
    def __init__(self):
        super(InitRsp, self).__init__()

class PingRsp(AgentResponse):
    def __init__(self):
        super(PingRsp, self).__init__()
        self.uuid = None

def replyerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            rsp = AgentResponse()
            rsp.success = False
            rsp.error = str(e)
            logger.warn(err)
            return jsonobject.dumps(rsp)
    return wrap

class VirtualRouter(object):
    http_server = http.HttpServer(port=7272)
    http_server.logfile_path = log.get_logfile_path()
    
    PLUGIN_PATH = "plugin_path"

    INIT_PATH = "/init"
    PING_PATH = "/ping"

    def __init__(self, config={}):
        self.config = config
        plugin_path = self.config.get(self.PLUGIN_PATH, None)
        if not plugin_path:
            plugin_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plugins')
        self.plugin_path = plugin_path
        self.plugin_rgty = plugin.PluginRegistry(self.plugin_path)
        self.init_command = None
        self.uuid = None

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.init_command = cmd
        self.uuid = cmd.uuid;
        return jsonobject.dumps(InitRsp())

    @replyerror
    def ping(self ,req):
        rsp = PingRsp()
        rsp.uuid = self.uuid
        return jsonobject.dumps(rsp)

    def start(self, in_thread=True):
        self.plugin_rgty.configure_plugins(self)
        self.plugin_rgty.start_plugins()

        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)

        if in_thread:
            self.http_server.start_in_thread()
        else:
            self.http_server.start()
            
    
    def stop(self):
        self.plugin_rgty.stop_plugins()
        self.http_server.stop()


class VirutalRouterDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(VirutalRouterDaemon, self).__init__(pidfile)
    
    def run(self):
        self.agent = VirtualRouter()
        self.agent.start(False)
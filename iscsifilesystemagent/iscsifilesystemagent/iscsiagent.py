__author__ = 'frank'

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.log as log
import zstacklib.utils.shell as shell
import zstacklib.utils.iptables as iptables
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.lock as lock
import zstacklib.utils.linux as linux
from zstacklib.utils import plugin
import os
import functools
import traceback
import pprint
import threading

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

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

class IscsiAgent(object):
    http_server = http.HttpServer(port=7760)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.plugin_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'plugins')
        self.plugin_rgty = plugin.PluginRegistry(self.plugin_path)

    def start(self, in_thread=True):
        self.plugin_rgty.configure_plugins(self)
        self.plugin_rgty.start_plugins()
        if in_thread:
            self.http_server.start_in_thread()
        else:
            self.http_server.start()

    def stop(self):
        self.plugin_rgty.stop_plugins()
        self.http_server.stop()



class IscsiDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(IscsiDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = IscsiAgent()
        self.agent.start(in_thread=False)



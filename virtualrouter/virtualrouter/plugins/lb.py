__author__ = 'frank'

from virtualrouter import virtualrouter
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import lock
import zstacklib.utils.iptables as iptables
from zstacklib.utils.rollback import rollback, rollbackable
import zstacklib.utils.shell as shell
from jinja2 import Template


logger = log.get_logger(__name__)

class Lb(virtualrouter.VRAgent):

    REFRESH_LB_PATH = "/lb/refresh"
    DELETE_LB_PATH = "/lb/delete"

    def _make_pid_file_path(self, lbUuid, listenerUuid):
         return '/var/run/haproxy-%s-%s.pid' % (lbUuid, listenerUuid)

    @rollbackable
    def _refresh(self, to):
        conf = '''global
    maxconn {{maxConnection}}
    log 127.0.0.1 local1
    user haproxy
    group haproxy
    daemon

listener {{listenerUuid}}
    mode {{mode}}
    timeout client {{connectionIdleTimeout}}
    timeout server {{connectionIdleTimeout}}
    timeout connect 60s
    balance {{balancerAlgorithm}}
    bind {{vip}}:{{loadBalancerPort}}
    {% for ip in nicIps %}
    server nic-{{ip}} {{ip}}:{{loadBalancerPort}} check port {{checkPort}} inter {{healthCheckInterval}}s rise {{healthyThreshold}} fall {{unhealthyThreshold}}
    {% endfor %}
'''

        pid_file = self._make_pid_file_path(to.lbUuid, to.listenerUuid)
        conf_file = '/etc/haproxy/%s-%s.cfg' % (to.lbUuid, to.listenerUuid)

        context = {}.update(to.__dict__)
        for p in to.parameters:
            k, v = p.split('::')
            context[k] = v
        conf_tmpt = Template(conf)
        conf = conf_tmpt.render(context)
        with open(conf_file, 'w') as fd:
            fd.write(conf)

        shell.call("iptables -I INPUT -d %s -p tcp --dport %s --syn -j DROP && sleep 0.5" % (to.vip, to.loadBalancerPort))
        @rollback
        def _0():
            shell.call("iptables -D INPUT -d %s -p tcp --dport %s --syn -j DROP" % (to.vip, to.loadBalancerPort))
        _0()

        shell.call('haproxy -D -f %s -p %s -sf $(cat %s)' % (conf_file, pid_file, pid_file))
        shell.call("iptables -D INPUT -d %s -p tcp --dport %s --syn -j DROP" % (to.vip, to.loadBalancerPort))


    @virtualrouter.replyerror
    @lock.file_lock('iptables')
    def refresh(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for to in cmd.lbs:
            self._refresh(to)

        rsp = virtualrouter.AgentResponse()
        return jsonobject.dumps(rsp)

    @virtualrouter.replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for listenerUuid in cmd.listenerUuids:
            pid = linux.find_process_by_cmdline([self._make_pid_file_path(cmd.lbUuid, listenerUuid)])
            if pid:
                shell.call('kill %s' % pid)

        rsp = virtualrouter.AgentResponse()
        return jsonobject.dumps(rsp)

    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.REFRESH_LB_PATH, self.refresh)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.DELETE_LB_PATH, self.delete)

    def stop(self):
        pass
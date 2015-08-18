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
import os


logger = log.get_logger(__name__)

class Lb(virtualrouter.VRAgent):

    REFRESH_LB_PATH = "/lb/refresh"
    DELETE_LB_PATH = "/lb/delete"

    def _make_pid_file_path(self, lbUuid, listenerUuid):
        return '/var/run/haproxy-%s-%s.pid' % (lbUuid, listenerUuid)

    def _make_conf_file_path(self, lbuuid, listener_uuid):
        return '/etc/haproxy/%s-%s.cfg' % (lbuuid, listener_uuid)

    def _make_chain_name(self, to):
        return "lb-%s-%s" % (to.vip.replace('.', '-'), to.loadBalancerPort)

    @rollback
    def _refresh(self, to):
        conf = '''global
    maxconn {{maxConnection}}
    log 127.0.0.1 local1
    user haproxy
    group haproxy
    daemon

listen {{listenerUuid}}
    mode {{mode}}
    timeout client {{connectionIdleTimeout}}s
    timeout server {{connectionIdleTimeout}}s
    timeout connect 60s
    balance {{balancerAlgorithm}}
    bind {{vip}}:{{loadBalancerPort}}
    {% for ip in nicIps %}
    server nic-{{ip}} {{ip}}:{{loadBalancerPort}} check port {{checkPort}} inter {{healthCheckInterval}}s rise {{healthyThreshold}} fall {{unhealthyThreshold}}
    {% endfor %}
'''

        pid_file = self._make_pid_file_path(to.lbUuid, to.listenerUuid)
        if not os.path.exists(pid_file):
            shell.call('touch %s' % pid_file)

        @rollbackable
        def _0():
            shell.call('rm -f %s' % pid_file)
        _0()

        conf_file = self._make_conf_file_path(to.lbUuid, to.listenerUuid)

        context = {}
        context.update(to.__dict__)
        for p in to.parameters:
            k, v = p.split('::')
            if k == 'healthCheckTarget':
                check_method, check_port = v.split(':')
                if check_port == 'default':
                    context['checkPort'] = to.instancePort
                else:
                    context['checkPort'] = check_port

            context[k] = v

        conf_tmpt = Template(conf)
        conf = conf_tmpt.render(context)
        with open(conf_file, 'w') as fd:
            fd.write(conf)

        shell.call("iptables -I INPUT -d %s -p tcp --dport %s --syn -j DROP && sleep 0.5" % (to.vip, to.loadBalancerPort))
        @rollbackable
        def _1():
            shell.call("iptables -D INPUT -d %s -p tcp --dport %s --syn -j DROP" % (to.vip, to.loadBalancerPort))
        _1()

        shell.call('haproxy -D -f %s -p %s -sf $(cat %s)' % (conf_file, pid_file, pid_file))
        shell.call("iptables -D INPUT -d %s -p tcp --dport %s --syn -j DROP" % (to.vip, to.loadBalancerPort))

        ipt = iptables.from_iptables_save()
        chain_name = self._make_chain_name(to)
        ipt.add_rule('-A INPUT -d %s/32 -j %s' % (to.vip, chain_name))
        ipt.add_rule('-A %s -p tcp -m tcp --dport %s -j ACCEPT' % (chain_name, to.loadBalancerPort))
        ipt.iptable_restore()


    def _kill_lb(self, to):
        pid_file_path = self._make_pid_file_path(to.lbUuid, to.listenerUuid)

        pid = linux.find_process_by_cmdline([pid_file_path])
        if pid:
            shell.call('kill %s' % pid)

        shell.call('rm -f %s' % pid_file_path)
        shell.call('rm -f %s' % self._make_conf_file_path(to.lbUuid, to.listenerUuid))

        ipt = iptables.from_iptables_save()
        ipt.delete_chain(self._make_chain_name(to))
        ipt.iptable_restore()

    @virtualrouter.replyerror
    @lock.file_lock('iptables')
    def refresh(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for to in cmd.lbs:
            if len(to.nicIps) == 0:
                self._kill_lb(to.lbUuid, to.listenerUuid)
            else:
                self._refresh(to)

        rsp = virtualrouter.AgentResponse()
        return jsonobject.dumps(rsp)

    @virtualrouter.replyerror
    @lock.file_lock('iptables')
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for to in cmd.lbs:
            self._kill_lb(to)

        rsp = virtualrouter.AgentResponse()
        return jsonobject.dumps(rsp)

    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.REFRESH_LB_PATH, self.refresh)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.DELETE_LB_PATH, self.delete)

    def stop(self):
        pass
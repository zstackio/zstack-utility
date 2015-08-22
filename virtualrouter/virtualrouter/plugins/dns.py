'''

@author: Frank
'''
from virtualrouter import virtualrouter
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import lock
import os.path

logger = log.get_logger(__name__)

class DnsInfo(object):
    def __init__(self):
        self.dnsAddress = None
        
class SetDnsCmd(virtualrouter.AgentCommand):
    def __init__(self):
        super(SetDnsCmd, self).__init__()
        self.dns = None

class SetDnsRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(SetDnsRsp, self).__init__()

class RemoveDnsRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(RemoveDnsRsp, self).__init__()
        
class Dns(virtualrouter.VRAgent):
    REMOVE_DNS_PATH = "/removedns";
    SET_DNS_PATH = "/setdns";
    
    DNS_CONF = '/etc/resolv.conf'
    
    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.SET_DNS_PATH, self.set_dns)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.REMOVE_DNS_PATH, self.remove_dns)

    def stop(self):
        pass

    def _readin_dns_conf(self):
        lines = []
        if os.path.exists(self.DNS_CONF):
            with open(self.DNS_CONF, 'r') as fd:
                lines = fd.read().split('\n')
                lines = [l.strip() for l in lines]
        return lines

    def _do_dnsmasq_start(self):
        if linux.is_systemd_enabled():
            cmd = shell.ShellCmd('systemctl start dnsmasq')
        else:
            cmd = shell.ShellCmd('/etc/init.d/dnsmasq start')
        return cmd(False)

    def _refresh_dnsmasq(self):
        dnsmasq_pid = linux.get_pid_by_process_name('dnsmasq')
        if not dnsmasq_pid:
            logger.debug('dnsmasq is not running, try to start it ...')
            output = self._do_dnsmasq_start()
            dnsmasq_pid = linux.get_pid_by_process_name('dnsmasq')
            if not dnsmasq_pid:
                raise virtualrouter.VirtualRouterError('dnsmasq in virtual router is not running, we try to start it but fail, error is %s' % output)

        shell.call('kill -1 %s' % dnsmasq_pid)

    @virtualrouter.replyerror
    @lock.lock('dns')
    @lock.lock('dnsmasq')
    def remove_dns(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        lines = self._readin_dns_conf()

        def is_to_del(dnsline):
            for dns in cmd.dns:
                if dns.dnsAddress in dnsline:
                    return True
            return False

        ret = []
        rewrite = False
        for l in lines:
            if is_to_del(l):
                rewrite = True
                continue
            ret.append(l)

        if rewrite:
            with open(self.DNS_CONF, 'w') as fd:
                fd.write('\n'.join(ret))

        self._refresh_dnsmasq()
        rsp = RemoveDnsRsp()
        return jsonobject.dumps(rsp)

    @virtualrouter.replyerror
    @lock.lock('dns')
    @lock.lock('dnsmasq')
    def set_dns(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        
        lines = self._readin_dns_conf()
        rewrite = False
        for dns_info in cmd.dns:
            dns = 'nameserver %s' % dns_info.dnsAddress
            if dns not in lines:
                lines.append(dns)
                rewrite = True
        
        if rewrite:
            with open(self.DNS_CONF, 'w') as fd:
                fd.write('\n'.join(lines))

        self._refresh_dnsmasq()
        rsp = SetDnsRsp()
        return jsonobject.dumps(rsp)
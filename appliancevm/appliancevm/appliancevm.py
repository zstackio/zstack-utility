__author__ = 'frank'

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.log as log
import zstacklib.utils.shell as shell
import zstacklib.utils.iptables as iptables
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.lock as lock
import zstacklib.utils.linux as linux
import os
import functools
import traceback
import pprint

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

class RefreshFirewallRsp(AgentResponse):
    def __init__(self):
        super(RefreshFirewallRsp, self).__init__()

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

class ApplianceVm(object):
    http_server = http.HttpServer(port=7759)
    http_server.logfile_path = log.get_logfile_path()

    REFRESH_FIREWALL_PATH = "/appliancevm/refreshfirewall"
    ECHO_PATH = "/appliancevm/echo"
    INIT_PATH = "/appliancevm/init"

    @lock.file_lock('iptables')
    def set_default_iptable_rules(self):
        shell.call('iptables --policy INPUT DROP')
        shell.call('iptables --policy FORWARD DROP')

        # NOTE: 22 port of eth0 is opened in /etc/sysconfig/iptables by default
        ipt = iptables.from_iptables_save()
        ipt.add_rule('-A INPUT -m state --state RELATED,ESTABLISHED -j ACCEPT')
        ipt.add_rule('-A INPUT -i lo -j ACCEPT')
        ipt.add_rule('-A INPUT -p icmp -j ACCEPT')
        ipt.add_rule('-A INPUT -j REJECT --reject-with icmp-host-prohibited')
        ipt.add_rule('-A FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT')
        ipt.add_rule('-A POSTROUTING -p udp --dport bootpc -j CHECKSUM --checksum-fill', iptables.IPTables.MANGLE_TABLE_NAME)
        ipt.iptable_restore()

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        upgrade_script_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'upgradescripts')
        list_file = os.path.join(upgrade_script_path, 'scriptlist')

        def upgrade():
            script_names = []
            with open(list_file, 'r') as fd:
                ls = fd.readlines()
                for l in ls:
                    l = l.strip(' \t\r\n')
                    if l:
                        script_names.append(l)

            for s in script_names:
                script = os.path.join(upgrade_script_path, s)
                if not os.path.exists(script):
                    raise Exception('cannot find upgrade script[%s]' % script)

                try:
                    shell.call('bash %s' % script)
                except shell.ShellError as e:
                    raise Exception('failed to execute upgrade script[%s], %s', script, str(e))

        if os.path.exists(list_file):
            upgrade()

        return jsonobject.dumps(AgentResponse())

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @replyerror
    @lock.file_lock('iptables')
    def refresh_rule(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RefreshFirewallRsp()

        ipt = iptables.from_iptables_save()

        # replace bootstrap 22 port rule with a more restricted one that binds to eth0's IP
        ipt.remove_rule('-A INPUT -i eth0 -p tcp -m tcp --dport 22 -j ACCEPT')
        eth0_ip = linux.get_ip_by_nic_name('eth0')
        assert eth0_ip, 'cannot find IP of eth0'
        ipt.add_rule('-A INPUT -d %s/32 -i eth0 -p tcp -m tcp --dport 22 -j ACCEPT' % eth0_ip)

        chain_name = 'appliancevm'
        ipt.delete_chain(chain_name)

        ipt.add_rule('-A INPUT -j %s' % chain_name)
        for to in cmd.rules:
            if to.destIp:
                nic_name = linux.get_nic_name_by_ip(to.destIp)
            else:
                nic_name = linux.get_nic_name_from_alias(linux.get_nic_names_by_mac(to.nicMac))
            r =[]
            if to.protocol == 'all' or to.protocol == 'udp':
                r.append('-A %s' % chain_name)
                if to.sourceIp:
                    r.append('-s %s' % to.sourceIp)
                if to.destIp:
                    r.append('-d %s' % to.destIp)
                r.append('-i %s -p udp -m state --state NEW -m udp --dport %s:%s -j ACCEPT' % (nic_name, to.startPort, to.endPort))
                rule = ' '.join(r)
                ipt.add_rule(rule)
            r = []
            if to.protocol == 'all' or to.protocol == 'tcp':
                r.append('-A %s' % chain_name)
                if to.sourceIp:
                    r.append('-s %s' % to.sourceIp)
                if to.destIp:
                    r.append('-d %s' % to.destIp)
                r.append('-i %s -p tcp -m state --state NEW -m tcp --dport %s:%s -j ACCEPT' % (nic_name, to.startPort, to.endPort))
                rule = ' '.join(r)
                ipt.add_rule(rule)

        ipt.iptable_restore()
        logger.debug('refreshed rules for appliance vm')

        return jsonobject.dumps(rsp)

    def start(self, in_thread=True):
        self.set_default_iptable_rules()

        self.http_server.register_async_uri(self.REFRESH_FIREWALL_PATH, self.refresh_rule)
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)

        if in_thread:
            self.http_server.start_in_thread()
        else:
            self.http_server.start()

    def stop(self):
        self.http_server.stop()

class ApplianceVmDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(ApplianceVmDaemon, self).__init__(pidfile)
        self.agent = ApplianceVm()

    def run(self):
        self.agent.start(False)

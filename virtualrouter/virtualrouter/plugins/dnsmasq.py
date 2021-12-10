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

#TODO: rewrite this module in OO manner using pyparse

class AddDhcpEntryCmd(virtualrouter.AgentCommand):
    def __init__(self):
        super(AddDhcpEntryCmd, self).__init__()
        self.dhcpEntries = None
        self.rebuild = None

class AddDhcpEntryRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(AddDhcpEntryRsp, self).__init__()

class RemoveDhcpEntryCmd(virtualrouter.AgentCommand):
    def __init__(self):
        super(RemoveDhcpEntryCmd, self).__init__()
        self.dhcpEntries = None

class RemoveDhcpEntryRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(RemoveDhcpEntryRsp, self).__init__()

class RewriteDnsRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(RewriteDnsRsp, self).__init__()
        
class DhcpEntry(object):
    def __init__(self):
        self.ip = None
        self.mac = None
        self.hostname = None
        self.netmask = None
        self.gateway = None
        self.tag = None
        self.dns = []
        self.dnsDomain = None
        self.isDefaultL3Network = False
    
    @staticmethod
    def from_dhcp_info(info):
        e = DhcpEntry()
        e.ip = info.ip
        e.mac = info.mac
        e.netmask = info.netmask
        e.isDefaultL3Network = info.isDefaultL3Network
        e.hostname = info.hostname
        if not e.hostname:
            e.hostname = info.ip.replace('.', '-')
            if info.dnsDomain:
                e.hostname = '%s.%s' % (e.hostname, info.dnsDomain)

        e.gateway = info.gateway
        e.dns = info.dns
        e.dnsDomain = info.dnsDomain
        e.tag = e.mac.replace(':', '')
        return e

    def to_host_entry_string(self):
        if self.isDefaultL3Network:
            return '%s %s' % (self.ip, self.hostname)
        else:
            return None

    def to_dhcp_entry_string(self):
        if self.isDefaultL3Network:
            return '%s,set:%s,%s,%s,infinite' % (self.mac, self.tag, self.ip, self.hostname)
        else:
            return '%s,set:%s,%s,,infinite' % (self.mac, self.tag, self.ip)

    def to_dhcp_option_string_list(self):
        opts = []
        if self.isDefaultL3Network:
            if self.gateway:
                opts.append('tag:%s,option:router,%s' % (self.tag, self.gateway))
            if self.dns:
                dns = ','.join(self.dns)
                opts.append('tag:%s,option:dns-server,%s' % (self.tag, dns))
            if self.dnsDomain:
                opts.append('tag:%s,option:domain-name,%s' % (self.tag, self.dnsDomain))
        else:
            opts.append('tag:%s,3' % self.tag)
            opts.append('tag:%s,6' % self.tag)


        opts.append('tag:%s,option:netmask,%s' % (self.tag, self.netmask))

        return opts
        
class Dnsmasq(virtualrouter.VRAgent):
    ADD_DHCP_PATH = "/adddhcp"
    REMOVE_DHCP_PATH = "/removedhcp"

    HOST_DHCP_FILE = "/etc/hosts.dhcp"
    HOST_DHCP_LEASES_FILE = "/etc/hosts.leases"
    HOST_OPTION_FILE = "/etc/hosts.option"
    HOST_DNS_FILE = "/etc/hosts.dns"
    DNSMASQ_CONF_FILE = "/etc/dnsmasq.conf"

    def __init__(self):
        self.signal_count = 0
    
    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.ADD_DHCP_PATH, self.add_dhcp_entry)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.REMOVE_DHCP_PATH, self.remove_dhcp_entry)

        if not os.path.exists(self.HOST_DHCP_FILE):
            shell.ShellCmd('touch %s' % self.HOST_DHCP_FILE)()
        
        if not os.path.exists(self.HOST_OPTION_FILE):
            shell.ShellCmd('touch %s' % self.HOST_OPTION_FILE)()
    
        if not os.path.exists(self.HOST_DHCP_LEASES_FILE):
            shell.ShellCmd('touch %s' % self.HOST_DHCP_LEASES_FILE)()
        
        if not os.path.exists(self.HOST_DNS_FILE):
            shell.ShellCmd('touch %s' % self.HOST_DNS_FILE)()

    def stop(self):
        pass
    
    def _read_current_dhcp_entries(self):
        with open(self.HOST_DHCP_FILE, 'r') as fd:
            lines = fd.read().splitlines()
            return [l for l in lines if l]
        
    def _read_current_option_entries(self):
        with open(self.HOST_OPTION_FILE, 'r') as fd:
            lines = fd.read().splitlines()
            return [l for l in lines if l]

    def _read_current_host_entries(self):
        with open(self.HOST_DNS_FILE, 'r') as fd:
            lines = fd.read().splitlines()
            return [l for l in lines if l]

    def _cleanup_entries_workaround(self, dhcpEntries):
        try:
            for e in dhcpEntries:
                mac2 = e.mac.replace(':', '')
                shell.call("sed -i '/%s/d' %s; \
                        sed -i '/\<%s\>/d' %s; \
                        sed -i '/^$/d' %s; \
                        sed -i '/%s/d' %s; \
                        sed -i '/^$/d' %s; \
                        sed -i '/\<%s\>/d' %s; \
                        sed -i '/^$/d' %s;" \
                           % (e.mac, self.HOST_DHCP_FILE, \
                              e.ip, self.HOST_DHCP_FILE, \
                              self.HOST_DHCP_FILE, \
                              mac2, self.HOST_OPTION_FILE, \
                              self.HOST_OPTION_FILE, \
                              e.ip, self.HOST_DNS_FILE, \
                              self.HOST_DNS_FILE))
            linux.sync_file(self.HOST_DHCP_FILE)
        except virtualrouter.VirtualRouterError as e:
            logger.warn(linux.get_exception_stacktrace())

    def _merge(self, entries):
        ### there are some duplicate entries during adding and result in the dhcp server fail to assign the ip address for vm
        ### I don't find the root cause and add the workaround code.' ZSTAC-15116 miao zhanyong
        #self._cleanup_entries_workaround(entries)
        dhcp_entries = set(self._read_current_dhcp_entries())
        #logger.debug('merge dhcp entries:{0}, total:{1} before'.format(len(entries), len(dhcp_entries)))
        for e in entries:
            dhcp_entries = set(filter((lambda o: o.find(e.ip+',') == -1 and o.find(e.mac) == -1), dhcp_entries))
            dhcp_entries.update([e.to_dhcp_entry_string()])
            #logger.debug('merge dhcp entries:{0} {2}, total:{1}'.format(len(entries), len(dhcp_entries), e.ip))

        with open(self.HOST_DHCP_FILE, 'w') as fd:
            fd.write('\n'.join(dhcp_entries))
        #logger.debug('merge dhcp entries:{0}, total:{1} after'.format(len(entries), len(dhcp_entries)))

        option_entries = set(self._read_current_option_entries())
        for e in entries:
            option_entries = set(filter((lambda o: o.find(e.tag) == -1), option_entries))
            option_entries.update(e.to_dhcp_option_string_list())
        with open(self.HOST_OPTION_FILE, 'w') as fd:
            fd.write('\n'.join(option_entries))

        host_entries = set(self._read_current_host_entries())
        for e in entries:
            if e.to_host_entry_string():
                host_entries = set(filter((lambda o: o.find(e.ip+' ') == -1), host_entries))
                host_entries.update([e.to_host_entry_string()])
        with open(self.HOST_DNS_FILE, 'w') as fd:
            fd.write('\n'.join(host_entries))

    def _rebuild_all(self, entries):
        dhcp_entries = []
        dhcp_options = []
        host_entries = []
        for entry in entries:
            dhcp_entries.append(entry.to_dhcp_entry_string())
            dhcp_options.extend(entry.to_dhcp_option_string_list())
            hostname = entry.to_host_entry_string()
            if hostname:
                host_entries.append(hostname)

        if dhcp_entries:
            with open(self.HOST_DHCP_FILE, 'w') as fd:
                fd.write('\n'.join(dhcp_entries))
        if dhcp_options:
            with open(self.HOST_OPTION_FILE, 'w') as fd:
                fd.write('\n'.join(dhcp_options))
        if host_entries:
            with open(self.HOST_DNS_FILE, 'w') as fd:
                fd.write('\n'.join(host_entries))

    def _refresh_dnsmasq(self):
        dnsmasq_pid = linux.get_pid_by_process_name('dnsmasq')
        if not dnsmasq_pid:
            logger.debug('dnsmasq is not running, try to start it ...')
            output = self._do_dnsmasq_start()
            dnsmasq_pid = linux.get_pid_by_process_name('dnsmasq')
            if not dnsmasq_pid:
                raise virtualrouter.VirtualRouterError('dnsmasq in virtual router is not running, we try to start it but fail, error is %s' % output)

        if self.signal_count > self.config.init_command.restartDnsmasqAfterNumberOfSIGUSER1:
            self._restart_dnsmasq()
            self.signal_count = 0
            return

        shell.call('kill -1 %s' % dnsmasq_pid)
        self.signal_count += 1
        
    def _add_dhcp_range_if_need(self, gateways):
        with open(self.DNSMASQ_CONF_FILE, 'a+') as fd:
            content = fd.read()
            new = []
            for g in gateways:
                entry = 'dhcp-range=%s,static' % g
                if entry not in content:
                    new.append(entry)
            
            if not new:
                return False
            
            fd.write('\n%s'%('\n'.join(new)))
            return True

    def _do_dnsmasq_restart(self):
        if linux.is_systemd_enabled():
            shell.call('systemctl restart dnsmasq')
        else:
            shell.call('/etc/init.d/dnsmasq restart')

    def _do_dnsmasq_start(self):
        if linux.is_systemd_enabled():
            cmd = shell.ShellCmd('systemctl start dnsmasq')
        else:
            cmd = shell.ShellCmd('/etc/init.d/dnsmasq start')
        return cmd(False)

    def _do_dnsmasq_stop(self):
        if linux.is_systemd_enabled():
            cmd = shell.ShellCmd('systemctl stop dnsmasq')
        else:
            cmd = shell.ShellCmd('/etc/init.d/dnsmasq stop')
        return cmd(False)

    def _restart_dnsmasq(self):
        self._do_dnsmasq_restart()
        
        def check_start(_):
            dnsmasq_pid = linux.get_pid_by_process_name('dnsmasq')
            return dnsmasq_pid is not None 

        if not linux.wait_callback_success(check_start, None, 5, 0.5):
            logger.debug('dnsmasq is not running, former start failed, try to start it again ...')
            cmd = self._do_dnsmasq_start()
            
            if cmd.return_code != 0:
                raise virtualrouter.VirtualRouterError('dnsmasq in virtual router is not running, we try to start it but fail, error is %s' % cmd.stdout)

            if not linux.wait_callback_success(check_start, None, 5, 0.5):
                raise virtualrouter.VirtualRouterError('dnsmasq in virtual router is not running, "/etc/init.d/dnsmasq start" returns success, but the process is not running after 5 seconds')

    @lock.lock('dnsmasq')
    @virtualrouter.replyerror
    def remove_dhcp_entry(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RemoveDhcpEntryRsp()
        try:
            for e in cmd.dhcpEntries:
                net_dev = shell.call("ip addr |grep -B 1 -i %s| head -n 1 | awk '{print $2}'" % e.vrNicMac)
                net_dev = net_dev.replace(':', '')
                net_dev = net_dev.strip('\t\r\n ')
                mac2 = e.mac.replace(':', '')

                shell.call("sed -i '/%s/d' %s; \
                        sed -i '/^$/d' %s; \
                        sed -i '/%s/d' %s; \
                        sed -i '/^$/d' %s; \
                        sed -i '/\<%s\>/d' %s; \
                        sed -i '/^$/d' %s; \
                        dhcp_release %s %s %s"\
                        % (e.mac, self.HOST_DHCP_FILE, \
                        self.HOST_DHCP_FILE, \
                        mac2, self.HOST_OPTION_FILE, \
                        self.HOST_OPTION_FILE, \
                        e.ip, self.HOST_DNS_FILE, \
                        self.HOST_DNS_FILE, \
                        net_dev, e.ip, e.mac))
            #logger.debug("remove dhcp entries:%s" % (len(cmd.dhcpEntries)))
            linux.sync_file(self.HOST_DHCP_FILE)
        except virtualrouter.VirtualRouterError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)
            
    @lock.lock('dnsmasq')
    @virtualrouter.replyerror
    def add_dhcp_entry(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        entries = []
        gateways = []
        for e in cmd.dhcpEntries:
            entry = DhcpEntry.from_dhcp_info(e)
            entries.append(entry)
            gateways.append(entry.gateway)
            
        if cmd.rebuild:
            self._rebuild_all(entries)
        else:
            self._merge(entries)
        
        rsp = AddDhcpEntryRsp()
        try:
            if self._add_dhcp_range_if_need(gateways):
                self._restart_dnsmasq()
            else:
                self._refresh_dnsmasq()
        except virtualrouter.VirtualRouterError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False
        
        return jsonobject.dumps(rsp)

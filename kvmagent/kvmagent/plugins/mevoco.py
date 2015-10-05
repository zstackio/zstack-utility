__author__ = 'frank'

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import sizeunit
from zstacklib.utils import linux
from zstacklib.utils import thread
from zstacklib.utils import lock
import os.path
import re
import threading
import time
from jinja2 import Template

logger = log.get_logger(__name__)


class ApplyDhcpRsp(kvmagent.AgentResponse):
    pass


class ReleaseDhcpRsp(kvmagent.AgentResponse):
    pass


class Mevoco(kvmagent.KvmAgent):
    APPLY_DHCP_PATH = "/flatnetworkprovider/dhcp/apply"
    RELEASE_DHCP_PATH = "/flatnetworkprovider/dhcp/release"

    DHCP_FILE = "/var/lib/zstack/dnsmasq/hosts.dhcp"
    DHCP_LEASE_FILE = "/var/lib/zstack/dnsmasq/hosts.leases"
    DHCP_OPTION_FILE = "/var/lib/zstack/dnsmasq/hosts.option"
    DNS_FILE = "/var/lib/zstack/dnsmasq/hosts.dns"
    DNSMASQ_CONF_FOLDER = "/var/lib/zstack/dnsmasq/"

    def __init__(self):
        self.signal_count = 0

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.APPLY_DHCP_PATH, self.apply_dhcp)
        http_server.register_async_uri(self.RELEASE_DHCP_PATH, self.release_dhcp)

    def stop(self):
        pass

    def _make_conf_path(self, bridge_name):
        return os.path.join(self.DNSMASQ_CONF_FOLDER, bridge_name, 'dnsmasq.conf')

    @lock.lock('dnsmasq')
    @kvmagent.replyerror
    def apply_dhcp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        bridge_dhcp = {}
        for d in cmd.dhcp:
            lst = bridge_dhcp.get(d.bridgeName)
            if not lst:
                lst = []
                bridge_dhcp[d.bridgeName] = lst
            lst.append(d)

        def apply(bridge_name, dhcp):
            conf_file_path = self._make_conf_path(bridge_name)

            conf_file = '''\
domain-needed
bogus-priv
no-hosts
addn-hosts={{dns}}
dhcp-option=vendor:MSFT,2,1i
dhcp-lease-max=65535
dhcp-hostsfile={{dhcp}}
dhcp-optsfile={{option}}
log-facility={{log}}
interface={{bridge_name}}
leasefile-ro
{% for g in gateways -%}
dhcp-range={{g}},static
{% endfor -%}
'''
            if not os.path.exists(conf_file_path) or cmd.rebuild:
                folder_path = os.path.dirname(conf_file_path)
                shell.call('mkdir -p %s' % folder_path)
                with open(conf_file_path, 'w') as fd:
                    log_path = os.path.join(folder_path, 'dnsmasq.log')
                    tmpt = Template(conf_file)
                    conf_file = tmpt.render({
                        'dns': self.DNS_FILE,
                        'dhcp': self.DHCP_FILE,
                        'option': self.DHCP_OPTION_FILE,
                        'log': log_path,
                        'bridge_name': bridge_name,
                        'gateways': [d.gateway for d in dhcp if d.gateway]
                    })

                    fd.write(conf_file)

            info = []
            for d in dhcp:
                dhcp_info = {'tag': d.mac.replace(':', '')}
                dhcp_info.update(d.__dict__)
                dhcp_info['dns'] = ','.join(d.dns)
                info.append(dhcp_info)

                if not cmd.rebuild:
                    self._erase_configurations(d.mac, d.ip)

            dhcp_conf = '''\
{% for d in dhcp -%}
{% if d.isDefaultL3Network -%}
{{d.mac}},set:{{d.tag}},{{d.ip}},{{d.hostname}},infinite
{% else -%}
{{d.mac}},set:{{d.tag}},{{d.ip}},infinite
{% endif -%}
{% endfor -%}
'''

            tmpt = Template(dhcp_conf)
            dhcp_conf = tmpt.render({'dhcp': info})
            mode = 'a+'
            if cmd.rebuild:
                mode = 'w'

            with open(self.DHCP_FILE, mode) as fd:
                fd.write(dhcp_conf)

            option_conf = '''\
{% for o in options -%}
{% if o.isDefaultL3Network -%}
{% if o.gateway -%}
tag:{{o.tag}},option:router,{{o.gateway}}
{% endif -%}
{% if o.dns -%}
tag:{{o.tag}},option:dns-server,{{o.dns}}
{% endif -%}
{% if o.dnsDomain -%}
tag:{{o.tag}},option:domain-name,{{o.dnsDomain}}
{% endif -%}
{% else -%}
tag:{{o.tag}},3
tag:{{o.tag}},6
{% endif -%}
tag:{{o.tag}},option:netmask,{{o.netmask}}
{% endfor -%}
    '''
            tmpt = Template(option_conf)
            option_conf = tmpt.render({'options': info})

            with open(self.DHCP_OPTION_FILE, mode) as fd:
                fd.write(option_conf)

            hostname_conf = '''\
{% for h in hostnames -%}
{% if h.isDefaultL3Network and h.hostname -%}
{{h.ip}} {{h.hostname}}
{% endif -%}
{% endfor -%}
    '''
            tmpt = Template(hostname_conf)
            hostname_conf = tmpt.render({'hostnames': info})

            with open(self.DNS_FILE, mode) as fd:
                fd.write(hostname_conf)

            if cmd.rebuild:
                self._restart_dnsmasq(conf_file_path)
            else:
                self._refresh_dnsmasq(conf_file_path)


        for k, v in bridge_dhcp.iteritems():
            apply(k, v)

        rsp = ApplyDhcpRsp()
        return jsonobject.dumps(rsp)

    def _restart_dnsmasq(self, conf_file_path):
        pid = linux.find_process_by_cmdline([conf_file_path])
        if pid:
            linux.kill_process(pid)

        shell.call('/sbin/dnsmasq --conf-file=%s | /usr/sbin/dnsmasq --conf-file=%s' % (conf_file_path, conf_file_path))

        def check(_):
            pid = linux.find_process_by_cmdline([conf_file_path])
            return pid is not None

        if not linux.wait_callback_success(check, None, 5):
            raise Exception('dnsmasq[conf-file:%s] is not running after being started %s seconds' % (conf_file_path, 5))

    def _refresh_dnsmasq(self, conf_file_path):
        pid = linux.find_process_by_cmdline([conf_file_path])
        if not pid:
            self._restart_dnsmasq(conf_file_path)
            return

        if self.signal_count > 50:
            self._restart_dnsmasq(conf_file_path)
            self.signal_count = 0
            return

        shell.call('kill -1 %s' % pid)
        self.signal_count += 1

    def _erase_configurations(self, mac, ip):
        cmd = '''\
sed -i '/{{mac}}/d' {{dhcp}};
sed -i '/^$/d' {{dhcp}};
sed -i '/{{tag}}/d' {{option}};
sed -i '/^$/d' {{option}};
sed -i '/{{ip}}/d' {{dns}};
sed -i '/^$/d' {{dns}}
'''
        tmpt = Template(cmd)
        context = {
            'tag': mac.replace(':', ''),
            'mac': mac,
            'dhcp': self.DHCP_FILE,
            'option': self.DHCP_OPTION_FILE,
            'ip': ip,
            'dns': self.DNS_FILE,
            }

        cmd = tmpt.render(context)
        shell.call(cmd)

    @lock.lock('dnsmasq')
    @kvmagent.replyerror
    def release_dhcp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        bridge_dhcp = {}
        for d in cmd.dhcp:
            lst = bridge_dhcp.get(d.bridgeName)
            if not lst:
                lst = []
                bridge_dhcp[d.bridgeName] = lst
            lst.append(d)

        def release(bridge_name, dhcp):
            conf_file_path = self._make_conf_path(bridge_name)

            for d in dhcp:
                self._erase_configurations(d.mac, d.ip)
                shell.call("dhcp_release %s %s %s" % (bridge_name, d.ip, d.mac))
                self._restart_dnsmasq(conf_file_path)

        for k, v in bridge_dhcp.iteritems():
            release(k, v)

        rsp = ReleaseDhcpRsp()
        return jsonobject.dumps(rsp)

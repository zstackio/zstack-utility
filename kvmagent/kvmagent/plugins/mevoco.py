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

class PrepareDhcpRsp(kvmagent.AgentResponse):
    pass

class ApplyUserdataRsp(kvmagent.AgentResponse):
    pass

class ReleaseUserdataRsp(kvmagent.AgentResponse):
    pass

class DhcpEnv(object):
    def __init__(self):
        self.bridge_name = None
        self.dhcp_server_ip = None
        self.dhcp_netmask = None

    def prepare(self):
        cmd = '''\
BR_NAME={{bridge_name}}
DHCP_IP={{dhcp_server_ip}}
DHCP_NETMASK={{dhcp_netmask}}

BR_NUM=`ip link show $BR_NAME | grep $BR_NAME | cut -d":" -f1`
OUTER_DEV="outer$BR_NUM"
INNER_DEV="inner$BR_NUM"

exit_on_error() {
    [ $? -ne 0 ] && exit 1
}

ip netns list | grep $BR_NAME > /dev/null
if [ $? -ne 0 ]; then
    ip netns add $BR_NAME
    exit_on_error
fi

# in case the namespace deleted and the orphan outer link leaves in the system,
# deleting the orphan link and recreate it
ip netns exec $BR_NAME ip link | grep $INNER_DEV > /dev/null
if [ $? -ne 0 ]; then
   ip link del $OUTER_DEV &> /dev/null
fi

ip link | grep $OUTER_DEV > /dev/null
if [ $? -ne 0 ]; then
    ip link add $OUTER_DEV type veth peer name $INNER_DEV
    exit_on_error
    ip link set $OUTER_DEV up
    exit_on_error
fi

brctl show $BR_NAME | grep $OUTER_DEV > /dev/null
if [ $? -ne 0 ]; then
    brctl addif $BR_NAME $OUTER_DEV
    exit_on_error
fi

ip netns exec $BR_NAME ip link | grep $INNER_DEV > /dev/null
if [ $? -ne 0 ]; then
    ip link set $INNER_DEV netns $BR_NAME
    exit_on_error
fi

ip netns exec $BR_NAME ip addr show $INNER_DEV | grep inet > /dev/null
if [ $? -ne 0 ]; then
    ip netns exec $BR_NAME ip addr add $DHCP_IP/$DHCP_NETMASK dev $INNER_DEV
    ip netns exec $BR_NAME ip link set $INNER_DEV up
    exit_on_error
fi

BR_PHY_DEV=`brctl show $BR_NAME  | grep $BR_NAME | sed 's/\s\s*/ /g' | cut -d' ' -f4`
if [ x$BR_PHY_DEV == "x" ]; then
   echo "cannot find the physical interface of the bridge $BR_NAME"
   exit 1
fi

ebtables-save | grep "FORWARD -p ARP -o $BR_PHY_DEV --arp-ip-dst $DHCP_IP -j DROP" > /dev/null
if [ $? -ne 0 ]; then
    ebtables -I FORWARD -p ARP -o $BR_PHY_DEV --arp-ip-dst $DHCP_IP -j DROP
    exit_on_error
fi

ebtables-save | grep "FORWARD -p IPv4 -o $BR_PHY_DEV --ip-proto udp --ip-sport 67:68 -j DROP" > /dev/null
if [ $? -ne 0 ]; then
    ebtables -I FORWARD -p IPv4 -o $BR_PHY_DEV --ip-proto udp --ip-sport 67:68 -j DROP
    exit_on_error
fi

exit 0
'''
        tmpt = Template(cmd)
        cmd = tmpt.render({
            'bridge_name': self.bridge_name,
            'dhcp_server_ip': self.dhcp_server_ip,
            'dhcp_netmask': self.dhcp_netmask
        })

        shell.call(cmd)

class Mevoco(kvmagent.KvmAgent):
    APPLY_DHCP_PATH = "/flatnetworkprovider/dhcp/apply"
    PREPARE_DHCP_PATH = "/flatnetworkprovider/dhcp/prepare"
    RELEASE_DHCP_PATH = "/flatnetworkprovider/dhcp/release"

    APPLY_USER_DATA = "/flatnetworkprovider/userdata/apply"
    RELEASE_USER_DATA = "/flatnetworkprovider/userdata/release"

    DNSMASQ_CONF_FOLDER = "/var/lib/zstack/dnsmasq/"

    USERDATA_ROOT = "/var/lib/zstack/userdata/"

    def __init__(self):
        self.signal_count = 0

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.APPLY_DHCP_PATH, self.apply_dhcp)
        http_server.register_async_uri(self.RELEASE_DHCP_PATH, self.release_dhcp)
        http_server.register_async_uri(self.PREPARE_DHCP_PATH, self.prepare_dhcp)
        http_server.register_async_uri(self.APPLY_USER_DATA, self.apply_userdata)
        http_server.register_async_uri(self.RELEASE_USER_DATA, self.release_userdata)

    def stop(self):
        pass

    @kvmagent.replyerror
    def apply_userdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        conf_folder = os.path.join(self.USERDATA_ROOT, cmd.bridgeName)
        if not os.path.exists(conf_folder):
            shell.call('mkdir -p %s' % conf_folder)

        conf_path = os.path.join(conf_folder, 'lighttpd.conf')
        http_root = os.path.join(conf_folder, 'html')

        def write_conf():
            conf = '''\
server.document-root = "{{http_root}}"

server.port = 80
server.bind = "{{dhcp_server_ip}}"
dir-listing.activate = "enable"
index-file.names = ( "index.html" )

server.modules += ( "mod_rewrite" )

$HTTP["remoteip"] =~ "^(.*)$" {
    url.rewrite-once = (
        "^/.*/meta-data/(.+)$" => "../%1/meta-data/$1",
        "^/.*/meta-data$" => "../%1/meta-data",
        "^/.*/meta-data/$" => "../%1/meta-data/",
        "^/.*/user-data$" => "../%1/user-data"
    )
}

mimetype.assign = (
  ".html" => "text/html",
  ".txt" => "text/plain",
  ".jpg" => "image/jpeg",
  ".png" => "image/png"
)'''

            tmpt = Template(conf)
            conf = tmpt.render({
                'http_root': http_root,
                'dhcp_server_ip': cmd.dhcpServerIp
            })

            with open(conf_path, 'w') as fd:
                fd.write(conf)

        if not os.path.exists(conf_path):
            write_conf()

        root = os.path.join(http_root, cmd.vmIp)
        meta_root = os.path.join(root, 'meta-data')
        if not os.path.exists(meta_root):
            shell.call('mkdir -p %s' % meta_root)

        index_file_path = os.path.join(meta_root, 'index.html')
        with open(index_file_path, 'w') as fd:
            fd.write('instance-id')

        instance_id_file_path = os.path.join(meta_root, 'instance-id')
        with open(instance_id_file_path, 'w') as fd:
            fd.write(cmd.metadata.vmUuid)

        if not cmd.userdata:
            cmd.userdata = ''

        userdata_file_path = os.path.join(root, 'user-data')
        with open(userdata_file_path, 'w') as fd:
            fd.write(cmd.userdata)

        pid = linux.find_process_by_cmdline([conf_path])
        if not pid:
            shell.call('ip netns exec %s lighttpd -f %s' % (cmd.bridgeName, conf_path))

            def check(_):
                pid = linux.find_process_by_cmdline([conf_path])
                return pid is not None

            if not linux.wait_callback_success(check, None, 5):
                raise Exception('lighttpd[conf-file:%s] is not running after being started %s seconds' % (conf_path, 5))

        return jsonobject.dumps(ApplyUserdataRsp())

    @kvmagent.replyerror
    def release_userdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        html_folder = os.path.join(self.USERDATA_ROOT, cmd.bridgeName, 'html', cmd.vmIp)
        shell.call('rm -rf %s' % html_folder)
        return jsonobject.dumps(ReleaseUserdataRsp())

    def _make_conf_path(self, bridge_name):
        folder = os.path.join(self.DNSMASQ_CONF_FOLDER, bridge_name)
        if not os.path.exists(folder):
            shell.call('mkdir -p %s' % folder)

        # the conf is created at the initializing time
        conf = os.path.join(folder, 'dnsmasq.conf')

        dhcp = os.path.join(folder, 'hosts.dhcp')
        if not os.path.exists(dhcp):
            shell.call('touch %s' % dhcp)

        dns = os.path.join(folder, 'hosts.dns')
        if not os.path.exists(dns):
            shell.call('touch %s' % dns)

        option = os.path.join(folder, 'hosts.option')
        if not os.path.exists(option):
            shell.call('touch %s' % option)

        log = os.path.join(folder, 'dnsmasq.log')
        if not os.path.exists(log):
            shell.call('touch %s' % log)

        return conf, dhcp, dns, option, log

    @lock.lock('prepare_dhcp')
    @kvmagent.replyerror
    def prepare_dhcp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        p = DhcpEnv()
        p.bridge_name = cmd.bridgeName
        p.dhcp_server_ip = cmd.dhcpServerIp
        p.dhcp_netmask = cmd.dhcpNetmask
        p.prepare()

        return jsonobject.dumps(PrepareDhcpRsp())

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
            conf_file_path, dhcp_path, dns_path, option_path, log_path = self._make_conf_path(bridge_name)

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
interface={{iface_name}}
except-interface=lo
bind-interfaces
leasefile-ro
{% for g in gateways -%}
dhcp-range={{g}},static
{% endfor -%}
'''

            br_num = shell.call('ip link show %s | grep %s | cut -d":" -f1' % (bridge_name, bridge_name))
            br_num = br_num.strip('\t\n\r ')
            tmpt = Template(conf_file)
            conf_file = tmpt.render({
                'dns': dns_path,
                'dhcp': dhcp_path,
                'option': option_path,
                'log': log_path,
                'iface_name': 'inner%s' % br_num,
                'gateways': [d.gateway for d in dhcp if d.gateway]
            })

            restart_dnsmasq = cmd.rebuild
            if not os.path.exists(conf_file_path) or cmd.rebuild:
                with open(conf_file_path, 'w') as fd:
                    fd.write(conf_file)
            else:
                if not restart_dnsmasq:
                    with open(conf_file_path, 'r+') as fd:
                        c = fd.read()
                        if c != conf_file:
                            logger.debug('dnsmasq configure file for bridge[%s] changed, restart it' % bridge_name)
                            fd.seek(0)
                            fd.write(conf_file)
                            restart_dnsmasq = True


            info = []
            for d in dhcp:
                dhcp_info = {'tag': d.mac.replace(':', '')}
                dhcp_info.update(d.__dict__)
                dhcp_info['dns'] = ','.join(d.dns)
                info.append(dhcp_info)

                if not cmd.rebuild:
                    self._erase_configurations(d.mac, d.ip, dhcp_path, dns_path, option_path)

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

            with open(dhcp_path, mode) as fd:
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

            with open(option_path, mode) as fd:
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

            with open(dns_path, mode) as fd:
                fd.write(hostname_conf)

            if restart_dnsmasq:
                self._restart_dnsmasq(bridge_name, conf_file_path)
            else:
                self._refresh_dnsmasq(bridge_name, conf_file_path)

        for k, v in bridge_dhcp.iteritems():
            apply(k, v)

        rsp = ApplyDhcpRsp()
        return jsonobject.dumps(rsp)

    def _restart_dnsmasq(self, ns_name, conf_file_path):
        pid = linux.find_process_by_cmdline([conf_file_path])
        if pid:
            linux.kill_process(pid)

        cmd = '''\
ip netns exec {{ns_name}} /sbin/dnsmasq --conf-file={{conf_file}} || ip netns exec {{ns_name}} /usr/sbin/dnsmasq --conf-file={{conf_file}}
'''
        tmpt = Template(cmd)
        cmd = tmpt.render({'ns_name': ns_name, 'conf_file': conf_file_path})
        shell.call(cmd)

        def check(_):
            pid = linux.find_process_by_cmdline([conf_file_path])
            return pid is not None

        if not linux.wait_callback_success(check, None, 5):
            raise Exception('dnsmasq[conf-file:%s] is not running after being started %s seconds' % (conf_file_path, 5))

    def _refresh_dnsmasq(self, ns_name, conf_file_path):
        pid = linux.find_process_by_cmdline([conf_file_path])
        if not pid:
            self._restart_dnsmasq(ns_name, conf_file_path)
            return

        if self.signal_count > 50:
            self._restart_dnsmasq(ns_name, conf_file_path)
            self.signal_count = 0
            return

        shell.call('kill -1 %s' % pid)
        self.signal_count += 1

    def _erase_configurations(self, mac, ip, dhcp_path, dns_path, option_path):
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
            'dhcp': dhcp_path,
            'option': option_path,
            'ip': ip,
            'dns': dns_path,
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
            conf_file_path, dhcp_path, dns_path, option_path, _ = self._make_conf_path(bridge_name)

            for d in dhcp:
                self._erase_configurations(d.mac, d.ip, dhcp_path, dns_path, option_path)
                #shell.call("(which dhcp_release &>/dev/null && dhcp_release %s %s %s) || true" % (bridge_name, d.ip, d.mac))
                self._restart_dnsmasq(bridge_name, conf_file_path)

        for k, v in bridge_dhcp.iteritems():
            release(k, v)

        rsp = ReleaseDhcpRsp()
        return jsonobject.dumps(rsp)

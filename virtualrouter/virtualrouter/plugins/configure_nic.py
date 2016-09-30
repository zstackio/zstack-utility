'''

@author: Frank
'''

from virtualrouter import virtualrouter
from zstacklib.utils import shell
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import iptables

logger = log.get_logger(__name__)

class ConfigureNicRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(ConfigureNicRsp, self).__init__()

class ConfigureNicCmd(virtualrouter.AgentCommand):
    def __init__(self):
        super(ConfigureNicCmd, self).__init__()
        self.nics = None
        
class NicPlugin(virtualrouter.VRAgent):
    CONFIGURE_NIC_PATH = "/configurenic"
    MGMT_NIC_NAME = 'eth0'
    
    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.CONFIGURE_NIC_PATH, self.configure_nic)
    
    def stop(self):
        pass
    
    def _get_nics(self):
        info = shell.ShellCmd('ip link')()
        nics = {}
        infos = info.split('\n')
        lines = []
        for i in infos:
            i = i.strip().strip('\t').strip('\r').strip('\n')
            if i == '':
                continue
            lines.append(i)
            
        i = 0
        while(i < len(lines)):
            l1 = lines[i]
            dev_name = l1.split(':')[1].strip()
            i += 1
            l2 = lines[i]
            mac = l2.split()[1].strip()
            i += 1
            if nics.has_key(mac):
                wrong_dev_name = nics[mac]
                err = 'two nics[%s, %s] has the same mac address[%s], this is not allowed in virtual router' % (dev_name, wrong_dev_name, mac)
                raise virtualrouter.VirtualRouterError(err)
                
            nics[mac] = dev_name
            
        return nics
        
    def _default_iptable_rules(self, nicname):
        in_chain_name = "%s-in" % nicname
        
        ipt = iptables.from_iptables_save()
        ipt.delete_chain(in_chain_name)
        ipt.add_rule('-A INPUT -i %s -j %s' % (nicname, in_chain_name))
        ipt.add_rule('-A %s -m state --state RELATED,ESTABLISHED -j ACCEPT' % in_chain_name)
        ipt.add_rule('-A %s -p udp -m udp --sport 68 --dport 67 -j ACCEPT' % in_chain_name)
        ipt.add_rule('-A %s -p udp -m udp --sport 67 --dport 68 -j ACCEPT' % in_chain_name)
        ipt.add_rule('-A %s -p udp -m udp --dport 53 -j ACCEPT' % in_chain_name)
        ipt.add_rule('-A %s -p icmp -m icmp -j ACCEPT' % in_chain_name)
        ipt.add_rule('-A %s -p tcp -m tcp --dport 22 -m state --state NEW -j ACCEPT' % in_chain_name)
        ipt.add_rule('-A %s -j REJECT --reject-with icmp-host-prohibited' % in_chain_name)
        ipt.iptable_restore()
        
        
    def _configure_nic(self, nic_name, nic):
        cfg_tmpt_no_gateway='''DEVICE="%(nic_name)s"
BOOTPROTO="static"
HWADDR="%(mac)s"
ONBOOT="yes"
TYPE="Ethernet"
IPADDR="%(ip)s"
NETMASK="%(netmask)s"
'''
        info = {
                'nic_name' : nic_name,
                'mac' : nic.mac,
                'ip' : nic.ip,
                'netmask' : nic.netmask,
                }
        
        cfg_path = '/etc/sysconfig/network-scripts/ifcfg-%s' % nic_name
        with open(cfg_path, 'w') as fd:
            fd.write(cfg_tmpt_no_gateway % info)
            
        shell.call('/sbin/ifup %s' % nic_name)
        if nic_name != self.MGMT_NIC_NAME:
            self._default_iptable_rules(nic_name)
    
    @virtualrouter.replyerror
    def configure_nic(self, req):
        rsp = ConfigureNicRsp()
        try:
            nics = self._get_nics() 
        except virtualrouter.VirtualRouterError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False
            return jsonobject.dumps(rsp)
            
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        nics_to_configure = cmd.nics
        for n in nics_to_configure:
            if not nics.has_key(n.mac):
                rsp.error = 'unable to find nic with mac[%s] in virtual router vm' % n.mac
                rsp.success = False
                return jsonobject.dumps(rsp)
        
        for n in nics_to_configure:
            nic_name = nics[n.mac]
            self._configure_nic(nic_name, n)
        
        return jsonobject.dumps(rsp)
        

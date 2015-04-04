'''

@author: frank
'''
from virtualrouter import virtualrouter
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import lock
from zstacklib.utils import iptables

logger = log.get_logger(__name__)

class PortForwardingRuleTO(object):
    def __init__(self):
        self.vipPortStart = None
        self.vipPortEnd = None
        self.privatePortStart = None
        self.privatePortEnd = None
        self.protocolType = None
        self.vipIp = None
        self.privateIp = None
        self.privateMac = None
        self.allowedCidr= None

class CreatePortForwardingRuleRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(CreatePortForwardingRuleRsp, self).__init__()

class RevokePortForwardingRuleRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(RevokePortForwardingRuleRsp, self).__init__()

class SyncPortForwardingRuleRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(SyncPortForwardingRuleRsp, self).__init__()

class PortForwarding(virtualrouter.VRAgent):
    CREATE_PORT_FORWARDING_PATH = "/createportforwarding";
    REVOKE_PORT_FORWARDING_PATH = "/revokeportforwarding";
    SYNC_PORT_FORWARDING_PATH = "/syncportforwarding";

    def _make_name(self, vip_nic_name, to, prefix):
        name = "pf-{0}-{1}-{2}-{3}".format(prefix, vip_nic_name, to.protocolType, to.vipPortStart)
        if len(name) >= 28:
            name = name[0:27]
        return name

    def make_dnat_chain_name(self, vip_nic_name, to):
        return self._make_name(vip_nic_name, to, 'dnat')
    
    def _make_forward_chain_name(self, vip_nic_name, to):
        return self._make_name(vip_nic_name, to, 'fwd')

    def _make_gateway_snat_name(self, vip_nic_name, to):
        return self._make_name(vip_nic_name, to, 'snat-gw')

    def _create_rule(self, iptc, to):
        private_nic_name = linux.get_nic_name_by_mac(to.privateMac)

        vip_nic_name = linux.get_nic_name_by_ip(to.vipIp)

        forward_chain_name = self._make_forward_chain_name(vip_nic_name, to)
        iptc.add_rule('-A FORWARD -i {0} -o {1} -j {2}'.format(vip_nic_name, private_nic_name, forward_chain_name))
        iptc.add_rule('-A FORWARD -i {0} -o {1} -j {2}'.format(private_nic_name, vip_nic_name, forward_chain_name))
        iptc.add_rule('-A %s -j ACCEPT' % forward_chain_name)

        dnat_chain_name = self.make_dnat_chain_name(vip_nic_name, to)

        iptc.add_rule('-A PREROUTING -p {0} -m {0} -d {1} -j {2}'.format(to.protocolType.lower(), to.vipIp, dnat_chain_name), iptc.NAT_TABLE_NAME)
        if to.allowedCidr:
            iptc.add_rule('-A {0} -s {1} -p {2} --dport {3}:{4} -j DNAT --to-destination {5}:{6}-{7}'.format(dnat_chain_name, to.allowedCidr, to.protocolType.lower(), to.vipPortStart, to.vipPortEnd, to.privateIp, to.privatePortStart, to.privatePortEnd), iptc.NAT_TABLE_NAME)
        else:
            iptc.add_rule('-A {0} -p {1} --dport {2}:{3} -j DNAT --to-destination {4}:{5}-{6}'.format(dnat_chain_name, to.protocolType.lower(), to.vipPortStart, to.vipPortEnd, to.privateIp, to.privatePortStart, to.privatePortEnd), iptc.NAT_TABLE_NAME)

        if to.snatInboundTraffic:
            gw_snat_name = self._make_gateway_snat_name(vip_nic_name, to)
            guest_gw_ip = linux.get_ip_by_nic_name(private_nic_name)
            iptc.add_rule('-A POSTROUTING -p {0} --dport {1}:{2} -d {3} -j {4}'.format(to.protocolType.lower(),
                                                                                       to.privatePortStart, to.privatePortEnd,
                                                                                       to.privateIp, gw_snat_name), iptc.NAT_TABLE_NAME, order=998)
            iptc.add_rule('-A {0} -j SNAT --to-source {1}'.format(gw_snat_name, guest_gw_ip), iptc.NAT_TABLE_NAME)

    @virtualrouter.replyerror
    @lock.lock('port_forwarding')
    @lock.file_lock('iptables')
    def create_rule(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreatePortForwardingRuleRsp()

        iptc = iptables.from_iptables_save()
        for to in cmd.rules:
            self._create_rule(iptc, to)
        iptc.iptable_restore()

        return jsonobject.dumps(rsp)
    
    def _revoke_rule(self, iptc, to):
        vip_nic_name = linux.get_nic_name_by_ip(to.vipIp)

        dnat_chain_name = self.make_dnat_chain_name(vip_nic_name, to)
        iptc.delete_chain(dnat_chain_name, iptc.NAT_TABLE_NAME)

        forwarding_chain_name = self._make_forward_chain_name(vip_nic_name, to)
        iptc.delete_chain(forwarding_chain_name)

        gw_snat_chain_name = self._make_gateway_snat_name(vip_nic_name, to)
        iptc.delete_chain(gw_snat_chain_name, iptc.NAT_TABLE_NAME)

    @virtualrouter.replyerror
    @lock.lock('port_forwarding')
    @lock.file_lock('iptables')
    def revoke_rule(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevokePortForwardingRuleRsp()
        iptc = iptables.from_iptables_save()
        for to in cmd.rules:
            self._revoke_rule(iptc, to)
        iptc.iptable_restore()
        return jsonobject.dumps(rsp)

    @virtualrouter.replyerror
    @lock.lock('port_forwarding')
    @lock.file_lock('iptables')
    def sync_rule(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SyncPortForwardingRuleRsp()

        iptc = iptables.from_iptables_save()
        # destroy all port forwarding related chains
        def remove_pf_chain(talble):
            for c in talble.children:
                if c.name.startswith('pf-'):
                    c.delete()

        nat_table = iptc.get_table(iptc.NAT_TABLE_NAME)
        if nat_table:
            remove_pf_chain(nat_table)
        filter_table = iptc.get_table(iptc.FILTER_TABLE_NAME)
        if filter_table:
            remove_pf_chain(filter_table)

        for to in cmd.rules:
            self._create_rule(iptc, to)

        iptc.iptable_restore()

        return jsonobject.dumps(rsp)
    
    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.CREATE_PORT_FORWARDING_PATH, self.create_rule)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.REVOKE_PORT_FORWARDING_PATH, self.revoke_rule)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.SYNC_PORT_FORWARDING_PATH, self.sync_rule)
    
    def stop(self):
        pass
'''

@author: frank
'''
from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import lock
from zstacklib.utils import linux
from zstacklib.utils import iptables
import os.path
import re

logger = log.get_logger(__name__)

class SecurityGroupRuleTO(object):
    def __init__(self):
        self.vmNicInternalName = None
        self.rules = []

class RuleTO(object):
    def __init__(self):
        self.protocol = None
        self.type = None
        self.startPort = None
        self.endPort = None
        self.allowedInternalIpRange = None
        self.allowedCidr = None

class ApplySecurityGroupRuleCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ApplySecurityGroupRuleCmd, self).__init__()
        self.ruleTOs = []

class ApplySecurityGroupRuleResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ApplySecurityGroupRuleResponse, self).__init__()

class RefreshAllRulesOnHostCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(RefreshAllRulesOnHostCmd, self).__init__()
        self.ruleTOs = []

class RefreshAllRulesOnHostResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(RefreshAllRulesOnHostResponse, self).__init__()

class CleanupUnusedRulesOnHostResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CleanupUnusedRulesOnHostResponse, self).__init__()

class SecurityGroupPlugin(kvmagent.KvmAgent):
    
    SECURITY_GROUP_APPLY_RULE_PATH = "/securitygroup/applyrules"
    SECURITY_GROUP_REFRESH_RULE_ON_HOST_PATH = "/securitygroup/refreshrulesonhost"
    SECURITY_GROUP_CLEANUP_UNUSED_RULE_ON_HOST_PATH = "/securitygroup/cleanupunusedrules"
    
    RULE_TYPE_INGRESS = 'Ingress'
    RULE_TYPE_EGRESS = 'Egress'
    PROTOCOL_TCP = 'TCP'
    PROTOCOL_UDP = 'UDP'
    PROTOCOL_ICMP = 'ICMP'

    ACTION_CODE_APPLY_RULE = 'applyRule'
    ACTION_CODE_DELETE_CHAIN = 'deleteChain'

    DEFAULT_POLICY_ACCEPT = 'accept'
    DEFAULT_POLICY_DENY = 'deny'
    
    WORLD_OPEN_CIDR = '0.0.0.0/0'
    
    ZSTACK_DEFAULT_CHAIN = 'sg-default'
    
    def _make_in_chain_name(self, vif_name):
        return '%s-in' % vif_name
    
    def _make_out_chain_name(self, vif_name):
        return '%s-out' % vif_name
    
    def _start_ingress_rule(self, vif_name, in_chain_name):
        return '-A %s -m physdev --physdev-out %s --physdev-is-bridged -j %s' % (self.ZSTACK_DEFAULT_CHAIN, vif_name, in_chain_name)
    
    def _end_ingress_rule(self, in_chain_name):
        return '-A %s -j REJECT --reject-with icmp-host-prohibited' % in_chain_name
    
    def _start_egress_rule(self, vif_name, out_chain_name):
        return '-A %s -m physdev --physdev-in %s --physdev-is-bridged -j %s' % (self.ZSTACK_DEFAULT_CHAIN, vif_name, out_chain_name)
    
    def _end_egress_rule(self, out_chain_name):
        return '-A %s -j DROP' % out_chain_name
        
    def _create_rules_using_iprange_match(self, sto):
        rules = []
        vif_name = sto.vmNicInternalName
        in_chain_name = self._make_in_chain_name(vif_name)
        rules.append(self._start_ingress_rule(vif_name, in_chain_name))
        out_chain_name = self._make_out_chain_name(vif_name)
        rules.append(self._start_egress_rule(vif_name, out_chain_name))

        # rules blocking network sniff
        rules.append('-A %s ! -s %s -j DROP' % (out_chain_name, sto.vmNicIp))
        rules.append('-A %s -m mac ! --mac-source %s -j DROP' % (out_chain_name, sto.vmNicMac))

        def make_ingress_rule(rto):
            if rto.protocol == self.PROTOCOL_ICMP:
                if rto.startPort == -1:
                    icmp_type = 'any'
                else:
                    icmp_type = '%s/%s' % (rto.startPort, rto.endPort)
                    
                tmpt = ' '.join(['-A', in_chain_name, '-p icmp --icmp-type', icmp_type, '-m iprange --src-range %s -j RETURN'])
                cidr_tmpt = ' '.join(['-A', in_chain_name, '-p icmp --icmp-type', icmp_type, '-s %s -j RETURN'])
            else:
                protocol = rto.protocol.lower()
                start_port = rto.startPort
                end_port = rto.endPort
                tmpt = ' '.join(['-A', in_chain_name, '-p', protocol, '-m', protocol, '--dport', '%s:%s' % (start_port, end_port), '-m state --state NEW -m iprange --src-range %s -j RETURN'])
                cidr_tmpt = ' '.join(['-A', in_chain_name, '-p', protocol, '-m', protocol, '--dport', '%s:%s' % (start_port, end_port), '-m state --state NEW -s %s -j RETURN'])
                        
            rule = cidr_tmpt % rto.allowedCidr
            rules.append(rule)
            
            if rto.allowedCidr != self.WORLD_OPEN_CIDR:
                for internal_ip in rto.allowedInternalIpRange:
                    rule = tmpt % internal_ip
                    rules.append(rule)
            
        
        def make_egress_rule(rto):
            if rto.protocol == self.PROTOCOL_ICMP:
                if rto.startPort == -1:
                    icmp_type = 'any'
                else:
                    icmp_type = '%s/%s' % (rto.startPort, rto.endPort)
                    
                tmpt = ' '.join(['-A', out_chain_name, '-p icmp --icmp-type', icmp_type, '-m iprange --dst-range %s -j RETURN'])
                cidr_tmpt = ' '.join(['-A', out_chain_name, '-p icmp --icmp-type', icmp_type, '-d %s -j RETURN'])
            else:
                protocol = rto.protocol.lower()
                start_port = rto.startPort
                end_port = rto.endPort
                tmpt = ' '.join(['-A', out_chain_name, '-p', protocol, '-m', protocol, '--dport', '%s:%s' % (start_port, end_port), '-m state --state NEW -m iprange --dst-range %s -j RETURN'])
                cidr_tmpt = ' '.join(['-A', out_chain_name, '-p', protocol, '-m', protocol, '--dport', '%s:%s' % (start_port, end_port), '-m state --state NEW -d %s -j RETURN'])
                        
            rule = cidr_tmpt % rto.allowedCidr
            rules.append(rule)
            if rto.allowedCidr != self.WORLD_OPEN_CIDR:
                for internal_ip in rto.allowedInternalIpRange:
                    rule = tmpt % internal_ip
                    rules.append(rule)
            
        empty_in_chain = True
        empty_out_chain = True
        for r in sto.rules:
            if r.type == self.RULE_TYPE_INGRESS:
                make_ingress_rule(r)
                empty_in_chain = False
            elif r.type == self.RULE_TYPE_EGRESS:
                make_egress_rule(r)
                empty_out_chain = False
            else:
                assert 0, 'unknown rule type[%s]' % r.type

        if empty_in_chain:
            if sto.ingressDefaultPolicy == self.DEFAULT_POLICY_ACCEPT:
                rules.append('-A %s -j ACCEPT' % in_chain_name)
            elif sto.ingressDefaultPolicy == self.DEFAULT_POLICY_DENY:
                rules.append('-A %s -j REJECT --reject-with icmp-host-prohibited' % in_chain_name)
            else:
                raise Exception('unknown default ingress policy: %s' % sto.ingressDefaultPolicy)
        else:
            rules.append(self._end_ingress_rule(in_chain_name))

        if empty_out_chain:
            if sto.egressDefaultPolicy == self.DEFAULT_POLICY_ACCEPT:
                rules.append('-A %s -j RETURN' % out_chain_name)
            elif sto.ingressDefaultPolicy == self.DEFAULT_POLICY_DENY:
                rules.append('-A %s -j DROP' % out_chain_name)
            else:
                raise Exception('unknown default egress policy: %s' % sto.egressDefaultPolicy)
        else:
            rules.append(self._end_egress_rule(out_chain_name))
        
        return rules
    
    def _create_default_rules(self, ipt):
        ipt.add_rule('-A FORWARD -m physdev  --physdev-is-bridged -j %s' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -m state --state RELATED,ESTABLISHED -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p udp -m physdev  --physdev-is-bridged -m udp --sport 68 --dport 67 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p udp -m physdev  --physdev-is-bridged -m udp --sport 67 --dport 68 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p udp -m physdev  --physdev-is-bridged -m udp --dport 53 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
    
    def _delete_all_chains(self, ipt):
        filter_table = ipt.get_table()
        for c in filter_table.children:
            if c.name.startswith('vnic'):
                logger.debug('delete zstack vnic chain[%s]' % c.name)
                c.delete()
                
        default_chain = ipt.get_chain(self.ZSTACK_DEFAULT_CHAIN)
        if default_chain:
            default_chain.delete()
            logger.debug('deleted default chain')
    
    def _apply_rules_on_vnic_chain(self, ipt, rto):
        self._delete_vnic_chain(ipt, rto.vmNicInternalName)
        
        rules = self._create_rules_using_iprange_match(rto)
        
        for rule in rules:
            ipt.add_rule(rule)
            
    def _delete_vnic_in_chain(self, ipt, nic_name):
        in_chain_name = self._make_in_chain_name(nic_name)
        ipt.delete_chain(in_chain_name)
        ipt.remove_rule(self._start_ingress_rule(nic_name, in_chain_name))
        ipt.remove_rule(self._end_ingress_rule(in_chain_name))
        default_chain = ipt.get_chain(self.ZSTACK_DEFAULT_CHAIN)
        for r in default_chain.children:
            if ipt.is_target_in_rule(r.identity, in_chain_name):
                r.delete()
                
    def _delete_vnic_out_chain(self, ipt, nic_name):
        out_chain_name = self._make_out_chain_name(nic_name)
        ipt.delete_chain(out_chain_name)
        ipt.remove_rule(self._start_egress_rule(nic_name, out_chain_name))
        ipt.remove_rule(self._end_egress_rule(out_chain_name))
        default_chain = ipt.get_chain(self.ZSTACK_DEFAULT_CHAIN)
        for r in default_chain.children:
            if ipt.is_target_in_rule(r.identity, out_chain_name):
                r.delete()
        
    def _delete_vnic_chain(self, ipt, nic_name):
        self._delete_vnic_in_chain(ipt, nic_name)
        self._delete_vnic_out_chain(ipt, nic_name)

    def _cleanup_iptable_chains(self, chain, data):
        if 'vnic' not in chain.name:
            return False

        vnic_name = chain.name.split('-')[0]
        if vnic_name not in data:
            logger.debug('clean up defunct vnic chain[%s]' % chain.name)
            return True
        return False

    def _apply_rules_using_iprange_match(self, cmd, iptable=None):
        if not iptable:
            ipt = iptables.from_iptables_save()
        else:
            ipt = iptable

        self._create_default_rules(ipt)
        
        for rto in cmd.ruleTOs:
            if rto.actionCode == self.ACTION_CODE_DELETE_CHAIN:
                self._delete_vnic_chain(ipt, rto.vmNicInternalName)
            elif rto.actionCode == self.ACTION_CODE_APPLY_RULE:
                self._apply_rules_on_vnic_chain(ipt, rto)
            else:
                raise Exception('unknown action code: %s' % rto.actionCode)


        default_accept_rule = "-A %s -j ACCEPT" % self.ZSTACK_DEFAULT_CHAIN
        ipt.remove_rule(default_accept_rule)
        ipt.add_rule(default_accept_rule)
        self._cleanup_stale_chains(ipt)
        ipt.iptable_restore()
        
    def _refresh_rules_on_host_using_iprange_match(self, cmd):
        ipt = iptables.from_iptables_save()
        self._delete_all_chains(ipt)
        self._apply_rules_using_iprange_match(cmd, ipt)
    
    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def apply_rules(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ApplySecurityGroupRuleResponse()
        try:
            self._apply_rules_using_iprange_match(cmd)
        except iptables.IPTablesError as e:
            err_log = linux.get_exception_stacktrace()
            logger.warn(err_log)
            rsp.error = str(e)
            rsp.success = False
        return jsonobject.dumps(rsp)
    
    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def refresh_rules_on_host(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RefreshAllRulesOnHostResponse()
        try:
            self._refresh_rules_on_host_using_iprange_match(cmd)
        except iptables.IPTablesError as e:
            err_log = linux.get_exception_stacktrace()
            logger.warn(err_log)
            rsp.error = str(e)
            rsp.success = False
        return jsonobject.dumps(rsp)

    def _cleanup_stale_chains(self, ipt):
        all_nics = linux.get_all_ethernet_device_names()
        ipt.cleanup_unused_chain(self._cleanup_iptable_chains, data=all_nics)

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def cleanup_unused_rules_on_host(self, req):
        rsp = CleanupUnusedRulesOnHostResponse()

        ipt = iptables.from_iptables_save()
        self._cleanup_stale_chains(ipt)
        ipt.iptable_restore()

        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.SECURITY_GROUP_CLEANUP_UNUSED_RULE_ON_HOST_PATH, self.cleanup_unused_rules_on_host)
        http_server.register_async_uri(self.SECURITY_GROUP_APPLY_RULE_PATH, self.apply_rules)
        http_server.register_async_uri(self.SECURITY_GROUP_REFRESH_RULE_ON_HOST_PATH, self.refresh_rules_on_host)
        
    def stop(self):
        pass


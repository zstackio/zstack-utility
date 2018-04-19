'''

@author: frank
'''
from zstacklib.utils import ipset

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

class UpdateGroupMemberResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateGroupMemberResponse, self).__init__()

class CheckDefaultSecurityGroupCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CheckDefaultSecurityGroupCmd, self).__init__()

class CheckDefaultSecurityGroupResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckDefaultSecurityGroupResponse, self).__init__()

class SecurityGroupPlugin(kvmagent.KvmAgent):
    
    SECURITY_GROUP_APPLY_RULE_PATH = "/securitygroup/applyrules"
    SECURITY_GROUP_REFRESH_RULE_ON_HOST_PATH = "/securitygroup/refreshrulesonhost"
    SECURITY_GROUP_CLEANUP_UNUSED_RULE_ON_HOST_PATH = "/securitygroup/cleanupunusedrules"
    SECURITY_GROUP_UPDATE_GROUP_MEMBER = "/securitygroup/updategroupmember"
    SECURITY_GROUP_CHECK_DEFAULT_RULES_ON_HOST_PATH = "/securitygroup/checkdefaultrulesonhost"
    
    RULE_TYPE_INGRESS = 'Ingress'
    RULE_TYPE_EGRESS = 'Egress'
    PROTOCOL_TCP = 'TCP'
    PROTOCOL_UDP = 'UDP'
    PROTOCOL_ICMP = 'ICMP'
    PROTOCOL_ALL = 'ALL'

    ACTION_CODE_APPLY_RULE = 'applyRule'
    ACTION_CODE_DELETE_CHAIN = 'deleteChain'
    ACTION_CODE_DELETE_GROUP = 'deleteGroup'
    ACTION_CODE_UPDATE_GROUP_MEMBER = 'updateGroup'

    DEFAULT_POLICY_ACCEPT = 'accept'
    DEFAULT_POLICY_DENY = 'deny'
    DEFAULT_POLICY_DROP = 'drop'

    WORLD_OPEN_CIDR = '0.0.0.0/0'
    
    ZSTACK_DEFAULT_CHAIN = 'sg-default'
    ZSTACK_IPSET_NAME_FORMAT = 'zstack-sg'
    
    def _make_in_chain_name(self, vif_name):
        return '%s-in' % vif_name
    
    def _make_out_chain_name(self, vif_name):
        return '%s-out' % vif_name
    
    def _start_ingress_rule(self, vif_name, in_chain_name):
        return '-A %s -m physdev --physdev-out %s --physdev-is-bridged -j %s' % (self.ZSTACK_DEFAULT_CHAIN, vif_name, in_chain_name)
    
    def _end_ingress_rule(self, in_chain_name, default_policy=DEFAULT_POLICY_DENY):
        if default_policy == self.DEFAULT_POLICY_DENY:
            return '-A %s -j REJECT --reject-with icmp-host-prohibited' % in_chain_name
        else:
            return '-A %s -j DROP' % in_chain_name

    def _start_egress_rule(self, vif_name, out_chain_name):
        return '-A %s -m physdev --physdev-in %s --physdev-is-bridged -j %s' % (self.ZSTACK_DEFAULT_CHAIN, vif_name, out_chain_name)
    
    def _end_egress_rule(self, out_chain_name):
        return '-A %s -j DROP' % out_chain_name

    def _make_security_group_ipset_name(self, uuid):
        # max ipset name is 31 char
        uuid_part = uuid[0:19]
        return '%s-%s' % (self.ZSTACK_IPSET_NAME_FORMAT, uuid_part)

    def _create_rule_from_setting(self, sto, ipset_mn):
        vif_name = sto.vmNicInternalName
        in_chain_name = self._make_in_chain_name(vif_name)
        out_chain_name = self._make_out_chain_name(vif_name)
        empty_in_chain = [True]
        empty_out_chain = [True]

        def make_ingress_rule(rto):
            if rto.protocol == self.PROTOCOL_ICMP:
                if rto.startPort == -1:
                    icmp_type = 'any'
                else:
                    icmp_type = '%s/%s' % (rto.startPort, rto.endPort)

                tmpt = ' '.join(
                    ['-A', in_chain_name, '-p icmp --icmp-type', icmp_type, '-m iprange --src-range %s -j RETURN'])
                cidr_tmpt = ' '.join(['-A', in_chain_name, '-p icmp --icmp-type', icmp_type, '-s %s -j RETURN'])
            elif rto.protocol == self.PROTOCOL_ALL:
                tmpt = ' '.join(
                    ['-A', in_chain_name, '-p all -m state --state NEW -m iprange --src-range %s -j RETURN'])
                cidr_tmpt = ' '.join(
                    ['-A', in_chain_name, '-p all -m state --state NEW -s %s -j RETURN'])
            else:
                protocol = rto.protocol.lower()
                start_port = rto.startPort
                end_port = rto.endPort
                tmpt = ' '.join(
                    ['-A', in_chain_name, '-p', protocol, '-m', protocol, '--dport', '%s:%s' % (start_port, end_port),
                     '-m state --state NEW -m iprange --src-range %s -j RETURN'])
                cidr_tmpt = ' '.join(
                    ['-A', in_chain_name, '-p', protocol, '-m', protocol, '--dport', '%s:%s' % (start_port, end_port),
                     '-m state --state NEW -s %s -j RETURN'])

            rule = cidr_tmpt % rto.allowedCidr
            return rule

        def make_egress_rule(rto):
            if rto.protocol == self.PROTOCOL_ICMP:
                if rto.startPort == -1:
                    icmp_type = 'any'
                else:
                    icmp_type = '%s/%s' % (rto.startPort, rto.endPort)

                tmpt = ' '.join(
                    ['-A', out_chain_name, '-p icmp --icmp-type', icmp_type, '-m iprange --dst-range %s -j RETURN'])
                cidr_tmpt = ' '.join(['-A', out_chain_name, '-p icmp --icmp-type', icmp_type, '-d %s -j RETURN'])
            elif rto.protocol == self.PROTOCOL_ALL:
                tmpt = ' '.join(
                    ['-A', out_chain_name, '-p all -m state --state NEW -m iprange --dst-range %s -j RETURN'])
                cidr_tmpt = ' '.join(
                    ['-A', out_chain_name, '-p all -m state --state NEW -d %s -j RETURN'])
            else:
                protocol = rto.protocol.lower()
                start_port = rto.startPort
                end_port = rto.endPort
                tmpt = ' '.join(
                    ['-A', out_chain_name, '-p', protocol, '-m', protocol, '--dport', '%s:%s' % (start_port, end_port),
                     '-m state --state NEW -m iprange --dst-range %s -j RETURN'])
                cidr_tmpt = ' '.join(
                    ['-A', out_chain_name, '-p', protocol, '-m', protocol, '--dport', '%s:%s' % (start_port, end_port),
                     '-m state --state NEW -d %s -j RETURN'])

            rule = cidr_tmpt % rto.allowedCidr
            return rule

        def create_start_rule():
            starts_rules = []
            starts_rules.append(self._start_ingress_rule(vif_name, in_chain_name))
            starts_rules.append(self._start_egress_rule(vif_name, out_chain_name))
            return starts_rules

        def create_tail_rule():
            tails_rules = []

            if empty_in_chain[0]:
                if sto.ingressDefaultPolicy == self.DEFAULT_POLICY_ACCEPT:
                    tails_rules.append('-A %s -j ACCEPT' % in_chain_name)
                elif sto.ingressDefaultPolicy == self.DEFAULT_POLICY_DENY:
                    tails_rules.append('-A %s -j REJECT --reject-with icmp-host-prohibited' % in_chain_name)
                elif sto.ingressDefaultPolicy == self.DEFAULT_POLICY_DROP:
                    tails_rules.append('-A %s -j DROP' % in_chain_name)
                else:
                    raise Exception('unknown default ingress policy: %s' % sto.ingressDefaultPolicy)
            else:
                tails_rules.append(self._end_ingress_rule(in_chain_name, sto.ingressDefaultPolicy))

            if empty_out_chain[0]:
                if sto.egressDefaultPolicy == self.DEFAULT_POLICY_ACCEPT:
                    tails_rules.append('-A %s -j RETURN' % out_chain_name)
                elif sto.ingressDefaultPolicy == self.DEFAULT_POLICY_DENY:
                    tails_rules.append('-A %s -j DROP' % out_chain_name)
                else:
                    raise Exception('unknown default egress policy: %s' % sto.egressDefaultPolicy)
            else:
                tails_rules.append(self._end_egress_rule(out_chain_name))

            return tails_rules

        def create_group_base_rules():
            group_rules = []

            for r in sto.securityGroupBaseRules:
                set_name = self._make_security_group_ipset_name(r.remoteGroupUuid)
                if r.type == self.RULE_TYPE_INGRESS:
                    rule = make_ingress_rule(r)
                    grule = ' '.join([rule, '-m set --match-set %s src' % set_name])
                    group_rules.append(grule)
                    empty_in_chain[0] = False
                elif r.type == self.RULE_TYPE_EGRESS:
                    rule = make_egress_rule(r)
                    grule = ' '.join([rule, '-m set --match-set %s dst' % set_name])
                    group_rules.append(grule)
                    if r.securityGroupUuid != r.remoteGroupUuid or r.protocol != self.PROTOCOL_ALL or r.allowedCidr != '0.0.0.0/0':
                        empty_out_chain[0] = False
                else:
                    assert 0, 'unknown rule type[%s]' % r.type

                if set_name not in ipset_mn.sets.keys():
                    ipset_mn.create_set(name=set_name, match_ips=r.remoteGroupVmIps)

            return group_rules

        def create_rules_using_iprange_match():
            ip_rules = []

            for r in sto.rules:
                if r.type == self.RULE_TYPE_INGRESS:
                    rule = make_ingress_rule(r)
                    empty_in_chain[0] = False
                elif r.type == self.RULE_TYPE_EGRESS:
                    rule = make_egress_rule(r)
                    empty_out_chain[0] = False
                else:
                    assert 0, 'unknown rule type[%s]' % r.type
                ip_rules.append(rule)

            return ip_rules

        start_rules = create_start_rule()
        group_base_rules = create_group_base_rules()
        ip_base_rules = create_rules_using_iprange_match()
        tail_rules = create_tail_rule()

        rules = []
        rules.extend(start_rules)
        rules.extend(group_base_rules)
        rules.extend(ip_base_rules)
        rules.extend(tail_rules)
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
    
    def _apply_rules_on_vnic_chain(self, ipt, ipset_mn, rto):
        self._delete_vnic_chain(ipt, rto.vmNicInternalName)

        rules = self._create_rule_from_setting(rto, ipset_mn)

        for r in rules:
            ipt.add_rule(r)
            
    def _delete_vnic_in_chain(self, ipt, nic_name):
        in_chain_name = self._make_in_chain_name(nic_name)
        ipt.delete_chain(in_chain_name)
        ipt.remove_rule(self._start_ingress_rule(nic_name, in_chain_name))
        ipt.remove_rule(self._end_ingress_rule(in_chain_name))
        ipt.remove_rule(self._end_ingress_rule(in_chain_name, self.DEFAULT_POLICY_DROP))
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

    def _apply_rules_using_iprange_match(self, cmd, iptable=None, ipset_mn=None):
        if not iptable:
            ipt = iptables.from_iptables_save()
        else:
            ipt = iptable

        if not ipset_mn:
            ips_mn = ipset.IPSetManager()
        else:
            ips_mn = ipset_mn

        self._create_default_rules(ipt)
        
        for rto in cmd.ruleTOs:
            if rto.actionCode == self.ACTION_CODE_DELETE_CHAIN:
                self._delete_vnic_chain(ipt, rto.vmNicInternalName)
            elif rto.actionCode == self.ACTION_CODE_APPLY_RULE:
                self._apply_rules_on_vnic_chain(ipt, ips_mn, rto)
            else:
                raise Exception('unknown action code: %s' % rto.actionCode)

        default_accept_rule = "-A %s -j ACCEPT" % self.ZSTACK_DEFAULT_CHAIN
        ipt.remove_rule(default_accept_rule)
        ipt.add_rule(default_accept_rule)
        self._cleanup_stale_chains(ipt)

        ips_mn.refresh_my_ipsets()
        ipt.iptable_restore()
        used_ipset = ipt.list_used_ipset_name()

        def match_set_name(name):
            return name.startswith(self.ZSTACK_IPSET_NAME_FORMAT)
        ips_mn.cleanup_other_ipset(match_set_name, used_ipset)
        
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
        ips_mn = ipset.IPSetManager()
        self._cleanup_stale_chains(ipt)
        ipt.iptable_restore()

        used_ipset = ipt.list_used_ipset_name()

        def match_set_name(name):
            return name.startswith(self.ZSTACK_IPSET_NAME_FORMAT)

        ips_mn.cleanup_other_ipset(match_set_name, used_ipset)
        return jsonobject.dumps(rsp)

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def update_group_member(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateGroupMemberResponse()

        ips_mn = ipset.IPSetManager()
        ipt = iptables.from_iptables_save()
        to_del_ipset_names = []
        for uto in cmd.updateGroupTOs:
            if uto.actionCode == self.ACTION_CODE_DELETE_GROUP:
                to_del_ipset_names.append(self._make_security_group_ipset_name(uto.securityGroupUuid))
            elif uto.actionCode == self.ACTION_CODE_UPDATE_GROUP_MEMBER:
                set_name = self._make_security_group_ipset_name(uto.securityGroupUuid)
                ips_mn.create_set(name=set_name, match_ips=uto.securityGroupVmIps)

        ips_mn.refresh_my_ipsets()
        if len(to_del_ipset_names) > 0:
            to_del_rules = ipt.list_reference_ipset_rules(to_del_ipset_names)
            for rule in to_del_rules:
                ipt.remove_rule(str(rule))
            ipt.iptable_restore()
            ips_mn.clean_ipsets(to_del_ipset_names)

        return jsonobject.dumps(rsp)

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def check_default_sg_rules(self, req):
        rsp = CheckDefaultSecurityGroupResponse()

        ipt = iptables.from_iptables_save()
        default_chain = ipt.get_chain(self.ZSTACK_DEFAULT_CHAIN)
        if not default_chain:
            self._create_default_rules(ipt)
            ipt.iptable_restore()

        return jsonobject.dumps(rsp)


    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.SECURITY_GROUP_CLEANUP_UNUSED_RULE_ON_HOST_PATH, self.cleanup_unused_rules_on_host)
        http_server.register_async_uri(self.SECURITY_GROUP_APPLY_RULE_PATH, self.apply_rules)
        http_server.register_async_uri(self.SECURITY_GROUP_REFRESH_RULE_ON_HOST_PATH, self.refresh_rules_on_host)
        http_server.register_async_uri(self.SECURITY_GROUP_UPDATE_GROUP_MEMBER, self.update_group_member)
        http_server.register_async_uri(self.SECURITY_GROUP_CHECK_DEFAULT_RULES_ON_HOST_PATH, self.check_default_sg_rules)
        
    def stop(self):
        pass


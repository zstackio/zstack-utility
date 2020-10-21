'''

@author: frank
'''
from zstacklib.utils import ipset

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import bash
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import lock
from zstacklib.utils import linux
from zstacklib.utils import iptables
from zstacklib.utils import misc
import os.path
import re

logger = log.get_logger(__name__)

class SecurityGroupRuleTO(object):
    def __init__(self):
        self.vmNicInternalName = None
        self.rules = []

class RuleTO(object):
    def __init__(self):
        self.ipVersion = 0
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
    WORLD_OPEN_CIDR_IPV6 = '::/0'
    
    ZSTACK_DEFAULT_CHAIN = 'sg-default'
    ZSTACK_IPSET_NAME_FORMAT = 'zstack-sg'
    IPV4 = 4
    IPV6 = 6
    ZSTACK_IPSET_FAMILYS = {4: "inet", 6: "inet6"}
    
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

    def _create_rule_from_setting(self, sto, ipset_mn, ip_version):
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

                if int(rto.ipVersion) == 4:
                    tmpt = ' '.join(
                        ['-A', in_chain_name, "-p icmp --icmp-type", icmp_type, '-m iprange --src-range %s -j RETURN'])
                    cidr_tmpt = ' '.join(['-A', in_chain_name, "-p icmp --icmp-type", icmp_type, '-s %s -j RETURN'])
                else:
                    tmpt = ' '.join(
                        ['-A', in_chain_name, '-p ipv6-icmp -m iprange --src-range %s -j RETURN'])
                    cidr_tmpt = ' '.join(['-A', in_chain_name, "-p ipv6-icmp", '-s %s -j RETURN'])

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

                if int(rto.ipVersion) == 4:
                    tmpt = ' '.join(['-A', out_chain_name, "-p icmp --icmp-type", icmp_type, '-m iprange --dst-range %s -j RETURN'])
                    cidr_tmpt = ' '.join(['-A', out_chain_name, "-p icmp --icmp-type", icmp_type, '-d %s -j RETURN'])
                else:
                    tmpt = ' '.join(
                        ['-A', out_chain_name, "-p ipv6-icmp" , '-m iprange --dst-range %s -j RETURN'])
                    cidr_tmpt = ' '.join(['-A', out_chain_name, "-p ipv6-icmp", '-d %s -j RETURN'])

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
                    if int(sto.ipVersion) == 4:
                        tails_rules.append('-A %s -j REJECT --reject-with icmp-host-prohibited' % in_chain_name)
                    else:
                        tails_rules.append('-A %s -j REJECT --reject-with icmp6-adm-prohibited' % in_chain_name)
                elif sto.ingressDefaultPolicy == self.DEFAULT_POLICY_DROP:
                    tails_rules.append('-A %s -j DROP' % in_chain_name)
                else:
                    raise Exception('unknown default ingress policy: %s' % sto.ingressDefaultPolicy)
            else:
                tails_rules.append(self._end_ingress_rule(in_chain_name, sto.ingressDefaultPolicy))

            if empty_out_chain[0]:
                if sto.egressDefaultPolicy == self.DEFAULT_POLICY_ACCEPT:
                    tails_rules.append('-A %s -j RETURN' % out_chain_name)
                elif sto.egressDefaultPolicy == self.DEFAULT_POLICY_DENY:
                    tails_rules.append('-A %s -j DROP' % out_chain_name)
                else:
                    raise Exception('unknown default egress policy: %s' % sto.egressDefaultPolicy)
            else:
                tails_rules.append(self._end_egress_rule(out_chain_name))

            return tails_rules

        def create_group_base_rules():
            group_rules = []

            for r in sto.securityGroupBaseRules:
                if ip_version != int(r.ipVersion):
                    continue
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
                    if int(r.ipVersion) == 4:
                        if r.securityGroupUuid != r.remoteGroupUuid or r.protocol != self.PROTOCOL_ALL or r.allowedCidr != self.WORLD_OPEN_CIDR:
                            empty_out_chain[0] = False
                    else:
                        if r.securityGroupUuid != r.remoteGroupUuid or r.protocol != self.PROTOCOL_ALL or r.allowedCidr != self.WORLD_OPEN_CIDR_IPV6:
                            empty_out_chain[0] = False
                else:
                    assert 0, 'unknown rule type[%s]' % r.type

                if set_name not in ipset_mn.sets.keys():
                    ipset_mn.create_set(name=set_name, match_ips=r.remoteGroupVmIps, ip_version=self.ZSTACK_IPSET_FAMILYS[ip_version])

            return group_rules

        def create_rules_using_iprange_match():
            ip_rules = []

            for r in sto.rules:
                if ip_version != int(r.ipVersion):
                    continue
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

    def _create_default_rules_ip6(self, ipt):
        ipt.add_rule('-A FORWARD -m physdev  --physdev-is-bridged -j %s' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -m state --state RELATED,ESTABLISHED -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p udp -m physdev  --physdev-is-bridged -m udp --sport 546 --dport 547 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p udp -m physdev  --physdev-is-bridged -m udp --sport 547 --dport 546 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p udp -m physdev  --physdev-is-bridged -m udp --dport 53 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p ipv6-icmp -m physdev --physdev-is-bridged -m icmp6 --icmpv6-type 133 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p ipv6-icmp -m physdev --physdev-is-bridged -m icmp6 --icmpv6-type 134 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p ipv6-icmp -m physdev --physdev-is-bridged -m icmp6 --icmpv6-type 135 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p ipv6-icmp -m physdev --physdev-is-bridged -m icmp6 --icmpv6-type 136 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        ipt.add_rule('-A %s -p ipv6-icmp -m physdev --physdev-is-bridged -m icmp6 --icmpv6-type 137 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)

    @bash.in_bash
    def _delete_all_chains(self, ipt):
        filter_table = ipt.get_table()
        chains = filter_table.children[:]
        for c in chains:
            if c.name.startswith('vnic'):
                logger.debug('delete zstack vnic chain[%s]' % c.name)
                ipt.delete_chain(c.name)
                
        default_chain = ipt.get_chain(self.ZSTACK_DEFAULT_CHAIN)
        if default_chain:
            default_chain.delete()
            logger.debug('deleted default chain')

        ipt.iptable_restore()

    @bash.in_bash
    def _apply_rules_on_vnic_chain(self, ipt, ipset_mn, rto):
        self._delete_vnic_chain(ipt, rto.vmNicInternalName)

        rules = self._create_rule_from_setting(rto, ipset_mn, self.IPV4)

        for r in rules:
            ipt.add_rule(r)

    def _apply_rules_on_vnic_chain_ip6(self, ipt, ipset_mn, rto):
        self._delete_vnic_chain(ipt, rto.vmNicInternalName)

        rules = self._create_rule_from_setting(rto, ipset_mn, self.IPV6)

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

    @bash.in_bash
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

    @misc.ignoreerror

    def _cleanup_conntrack(self, ips=None, ip_version="ipv4"):
        if ips:
            for ip in ips:
                shell.run("conntrack -d %s -f %s -D" % (ip, ip_version))
                logger.debug('clean up conntrack -d %s -D' % ip)
        else:
            shell.run("conntrack -f %s -D" % ip_version)
            logger.debug('clean up conntrack -f %s -D' % ip_version)

    @bash.in_bash
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
            self._cleanup_conntrack(rto.vmNicIp)

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

    def _apply_rules_using_iprange_match_ip6(self, cmd, iptable=None, ipset_mn=None):
        if not iptable:
            ipt = iptables.from_ip6tables_save()
        else:
            ipt = iptable

        if not ipset_mn:
            ips_mn = ipset.IPSetManager()
        else:
            ips_mn = ipset_mn

        self._create_default_rules_ip6(ipt)

        for rto in cmd.ipv6RuleTOs:
            if rto.actionCode == self.ACTION_CODE_DELETE_CHAIN:
                self._delete_vnic_chain(ipt, rto.vmNicInternalName)
            elif rto.actionCode == self.ACTION_CODE_APPLY_RULE:
                self._apply_rules_on_vnic_chain_ip6(ipt, ips_mn, rto)
            else:
                raise Exception('unknown action code: %s' % rto.actionCode)
            self._cleanup_conntrack(rto.vmNicIp, "ipv6")

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

    @bash.in_bash
    def _refresh_rules_on_host_using_iprange_match(self, cmd):
        if cmd.ruleTOs is not None:
            ipt = iptables.from_iptables_save()
            self._delete_all_chains(ipt)
            self._apply_rules_using_iprange_match(cmd, ipt)

        if cmd.ipv6RuleTOs is not None:
            ip6t = iptables.from_ip6tables_save()
            self._delete_all_chains(ip6t)
            self._apply_rules_using_iprange_match_ip6(cmd, ip6t)

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def apply_rules(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ApplySecurityGroupRuleResponse()

        try:
            if cmd.ruleTOs is not None:
                ipt = iptables.from_iptables_save()
                self._apply_rules_using_iprange_match(cmd, ipt)

            if cmd.ipv6RuleTOs is not None:
                ip6t = iptables.from_ip6tables_save()
                self._apply_rules_using_iprange_match_ip6(cmd, ip6t)
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
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CleanupUnusedRulesOnHostResponse()

        ipt = iptables.from_iptables_save()
        ips_mn = ipset.IPSetManager()
        self._cleanup_stale_chains(ipt)
        ipt.iptable_restore()
        used_ipset = ipt.list_used_ipset_name()

        if not cmd.skipIpv6:
            ip6t = iptables.from_ip6tables_save()
            self._cleanup_stale_chains(ip6t)
            ip6t.iptable_restore()
            used_ipset6 = ip6t.list_used_ipset_name()
            for uset in used_ipset6:
                used_ipset.appaned(uset)

        def match_set_name(name):
            return name.startswith(self.ZSTACK_IPSET_NAME_FORMAT)

        ips_mn.cleanup_other_ipset(match_set_name, used_ipset)
        self._cleanup_conntrack()

        return jsonobject.dumps(rsp)

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def update_group_member(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateGroupMemberResponse()

        utos4 = []
        utos6 = []
        for uto in cmd.updateGroupTOs:
            if int(uto.ipVersion) == 4:
                utos4.append(uto)
            else:
                utos6.append(uto)

        ips_mn = ipset.IPSetManager()
        ipt = iptables.from_iptables_save()
        to_del_ipset_names = []
        for uto in utos4:
            if uto.actionCode == self.ACTION_CODE_DELETE_GROUP:
                to_del_ipset_names.append(self._make_security_group_ipset_name(uto.securityGroupUuid))
            elif uto.actionCode == self.ACTION_CODE_UPDATE_GROUP_MEMBER:
                set_name = self._make_security_group_ipset_name(uto.securityGroupUuid)
                ip_version = self.ZSTACK_IPSET_FAMILYS[int(uto.ipVersion)]
                ips_mn.create_set(name=set_name, match_ips=uto.securityGroupVmIps, ip_version=ip_version)

        ips_mn.refresh_my_ipsets()
        if len(to_del_ipset_names) > 0:
            to_del_rules = ipt.list_reference_ipset_rules(to_del_ipset_names)
            for rule in to_del_rules:
                ipt.remove_rule(str(rule))
            ipt.iptable_restore()
            ips_mn.clean_ipsets(to_del_ipset_names)

        ip6s_mn = ipset.IPSetManager()
        ip6t = iptables.from_ip6tables_save()
        to_del_ipset_names = []
        for uto in utos6:
            if uto.actionCode == self.ACTION_CODE_DELETE_GROUP:
                to_del_ipset_names.append(self._make_security_group_ipset_name(uto.securityGroupUuid))
            elif uto.actionCode == self.ACTION_CODE_UPDATE_GROUP_MEMBER:
                set_name = self._make_security_group_ipset_name(uto.securityGroupUuid)
                ip_version = self.ZSTACK_IPSET_FAMILYS[int(uto.ipVersion)]
                ip6s_mn.create_set(name=set_name, match_ips=uto.securityGroupVmIps, ip_version=ip_version)

        ip6s_mn.refresh_my_ipsets()
        if len(to_del_ipset_names) > 0:
            to_del_rules = ip6t.list_reference_ipset_rules(to_del_ipset_names)
            for rule in to_del_rules:
                ip6t.remove_rule(str(rule))
            ip6t.iptable_restore()
            ip6s_mn.clean_ipsets(to_del_ipset_names)

        self._cleanup_conntrack()

        return jsonobject.dumps(rsp)

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def check_default_sg_rules(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckDefaultSecurityGroupResponse()

        ipt = iptables.from_iptables_save()
        default_chain = ipt.get_chain(self.ZSTACK_DEFAULT_CHAIN)
        if not default_chain:
            self._create_default_rules(ipt)
            ipt.iptable_restore()
            self._cleanup_conntrack(ip_version="ipv4")

        if not cmd.skipIpv6:
            ip6t = iptables.from_ip6tables_save()
            default_chain6 = ip6t.get_chain(self.ZSTACK_DEFAULT_CHAIN)
            if not default_chain6:
                self._create_default_rules_ip6(ip6t)
                ip6t.iptable_restore()
                self._cleanup_conntrack(ip_version="ipv6")

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


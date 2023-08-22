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
from zstacklib.utils import iptables_v2 as iptables
from zstacklib.utils import misc
from zstacklib.utils import ip
import os.path
import re

logger = log.get_logger(__name__)


RULE_TYPE_INGRESS = 'Ingress'
RULE_TYPE_EGRESS = 'Egress'
RULE_STATE_ENABLED = 'Enabled'
RULE_STATE_DISABLED = 'Disabled'


class VmNicSecurityTO(object):
    def __init__(self, nicCmd):
        self.name = nicCmd.internalName
        self.uuid = nicCmd.vmNicUuid
        self.mac = nicCmd.mac
        self.ips = nicCmd.vmNicIps
        self.ingress_policy = nicCmd.ingressPolicy
        self.egress_policy = nicCmd.egressPolicy
        self.action_code = nicCmd.actionCode
        self.security_group_refs = self._build_refs(nicCmd.securityGroupRefs)

    def _build_refs(self, refs):
        ref_data = refs.to_dict()
        if not ref_data:
            return []
        sorted_refs = sorted(ref_data.items(), key=lambda x: x[1])
        return [item[0] for item in sorted_refs]


class SecurityGroup(object):
    def __init__(self, uuid=None):
        self.uuid = uuid
        self.update_ipv4 = False
        self.update_ipv6 = False
        self.ingress_rules = []  # type RuleTO
        self.egress_rules = []  # type RuleTO
        self.ip6_ingress_rules = []  # type RuleTO
        self.ip6_egress_rules = []  # type RuleTO

    def add_rule(self, rule):
        rto = RuleTO(rule)
        if rto.version == 4:
            if rto.type == RULE_TYPE_INGRESS:
                self.ingress_rules.append(rto)
            elif rto.type == RULE_TYPE_EGRESS:
                self.egress_rules.append(rto)
        if rto.version == 6:
            if rto.type == RULE_TYPE_INGRESS:
                self.ip6_ingress_rules.append(rto)
            elif rto.type == RULE_TYPE_EGRESS:
                self.ip6_egress_rules.append(rto)

    def set_uuid(self, uuid):
        self.uuid = uuid

    def get_uuid(self):
        return self.uuid

    def get_ingress_rules(self):
        return self.ingress_rules

    def get_egress_rules(self):
        return self.egress_rules

    def get_ip6_ingress_rules(self):
        return self.ip6_ingress_rules

    def get_ip6_egress_rules(self):
        return self.ip6_egress_rules

    def sort_rules(self):
        self.ingress_rules.sort(key=lambda r: r.priority)
        self.egress_rules.sort(key=lambda r: r.priority)
        self.ip6_ingress_rules.sort(key=lambda r: r.priority)
        self.ip6_egress_rules.sort(key=lambda r: r.priority)


class RuleTO(object):
    def __init__(self, ruleTO):
        self.priority = ruleTO.priority
        self.type = ruleTO.type
        self.state = ruleTO.state
        self.version = ruleTO.ipVersion
        self.protocol = ruleTO.protocol
        self.src_ips = ruleTO.srcIpRange
        self.dst_ips = ruleTO.dstIpRange
        self.dst_ports = ruleTO.dstPortRange
        self.action = ruleTO.action
        self.remote_group_uuid = ruleTO.remoteGroupUuid
        self.remote_group_vm_ips = ruleTO.remoteGroupVmIps


class ApplySecurityGroupRuleCmd(kvmagent.AgentCommand):

    def __init__(self):
        super(ApplySecurityGroupRuleCmd, self).__init__()
        self.nics = []  # type VmNicSecurityTO
        self.security_groups = []  # type SecurityGroup

    def _flush_cmd(self):
        self.nics = []
        self.security_groups = []

    def get_security_groups(self):
        return self.security_groups

    def get_nics(self):
        return self.nics

    def get_nic_by_uuid(self, uuid):
        for nic in self.nics:
            if nic.uuid == uuid:
                return nic

    def get_nic_by_name(self, name):
        for nic in self.nics:
            if nic.name == name:
                return nic
        return None

    def get_security_group_by_uuid(self, uuid):

        for sg in self.security_groups:
            if sg.uuid == uuid:
                return sg
        return None

    def parse_cmd(self, cmd):

        self._flush_cmd()

        for nicCmd in cmd.vmNicTOs:
            nic = VmNicSecurityTO(nicCmd)
            self.nics.append(nic)

        rule_dict = cmd.ruleTOs.to_dict()
        rule6_dict = cmd.ip6RuleTOs.to_dict()

        for uuid, rules in rule_dict.items():
            sg = self.get_security_group_by_uuid(uuid)
            if not sg:
                sg = SecurityGroup(uuid)
                self.security_groups.append(sg)
            sg.update_ipv4 = True
            if not rules:
                continue
            for rule in rules:
                sg.add_rule(rule)

        for uuid, ip6rules in rule6_dict.items():
            sg = self.get_security_group_by_uuid(uuid)
            if not sg:
                sg = SecurityGroup(uuid)
                self.security_groups.append(sg)
            sg.update_ipv6 = True
            if not ip6rules:
                continue
            for ip6rule in ip6rules:
                sg.add_rule(ip6rule)

        for sg in self.security_groups:
            sg.sort_rules()


class ApplySecurityGroupRuleResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ApplySecurityGroupRuleResponse, self).__init__()


class RefreshAllRulesOnHostCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(RefreshAllRulesOnHostCmd, self).__init__()
        self.nics = []
        self.security_groups = []


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

    PROTOCOL_TCP = 'TCP'
    PROTOCOL_UDP = 'UDP'
    PROTOCOL_ICMP = 'ICMP'
    PROTOCOL_ALL = 'ALL'

    RULE_ACTION_ACCEPT = 'ACCEPT'
    RULE_ACTION_DROP = 'DROP'
    RULE_ACTION_RETURN = 'RETURN'

    IP_SPLIT = ','
    RANGE_SPLIT = '-'
    PORT_SPLIT = ':'

    NIC_SECURITY_POLICY_DENY = 'DENY'
    NIC_SECURITY_POLICY_ALLOW = 'ALLOW'

    ACTION_CODE_APPLY_CHAIN = "applyChain"
    ACTION_CODE_DELETE_CHAIN = "deleteChain"

    ACTION_CODE_DELETE_GROUP = 'deleteGroup'
    ACTION_CODE_UPDATE_GROUP_MEMBER = 'updateGroup'

    WORLD_OPEN_CIDR = '0.0.0.0/0'
    WORLD_OPEN_CIDR_IPV6 = '::/0'

    ZSTACK_DEFAULT_CHAIN = 'sg-default'
    IPV4 = 4
    IPV6 = 6
    ZSTACK_IPSET_FAMILYS = {4: "inet", 6: "inet6"}
    ZSTACK_IPSET_NAME_FORMAT = {4: "zstack-sg", 6: "zstack-sg6"}

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
    def _create_ipset_and_add_member(self, ipset_mn, ipset_name, ip_version, ips):
        ipset_mn.create_set(name=ipset_name, match_ips=ips, ip_version=self.ZSTACK_IPSET_FAMILYS[ip_version])

    @bash.in_bash
    def _delete_ipsets(self, ipset_mn, ipset_names):
        for ipset_name in ipset_names:
            ipset_mn.delete_set(ipset_name)

    @bash.in_bash
    def _cleanup_unused_chain(self, version):
        all_nics = linux.get_all_ethernet_device_names()

        # delete vnic chain when nic is removed
        filter_table = iptables.from_iptables_save() if version == self.IPV4 else iptables.from_iptables_save(version=self.IPV6)
        sg_default_chain = filter_table.get_chain_by_name(self.ZSTACK_DEFAULT_CHAIN)
        if sg_default_chain:
            for chain in filter_table.get_chains():
                if self._is_vnic_chain_name(chain.name):
                    vnic_name = chain.name.split('-')[0]
                    if vnic_name not in all_nics:
                        logger.debug('clean up defunct vnic chain[%s]' % chain.name)
                        filter_table.delete_chain(chain.name)
                        sg_default_chain.delete_rule_by_target(chain.name)

        filter_table.iptables_restore()

        IPTABLES_CMD = iptables.get_iptables_cmd() if version == self.IPV4 else iptables.get_ip6tables_cmd()
        to_delete_chain = []
        out = bash.bash_o("%s -nvL | grep '^Chain' | sed 's/[()]//g' | awk '{print $2, $3}'" % IPTABLES_CMD).splitlines()
        for o in out:
            chain_ref = o.split()
            if len(chain_ref) != 2:
                continue
            name = chain_ref[0]
            references = chain_ref[1]
            if (self._is_vnic_chain_name(name) or self.is_sg_chain_name(name)) and references == '0':
                to_delete_chain.append(name)
        if to_delete_chain:
            filter_table = iptables.from_iptables_save() if version == self.IPV4 else iptables.from_iptables_save(version=self.IPV6)
            for chain in to_delete_chain:
                filter_table.delete_chain(chain)
            logger.debug('deleted unused chain: %s' % to_delete_chain)
            filter_table.iptables_restore()

    @bash.in_bash
    def _cleanup_unused_ipset(self):
        to_delete = []
        out = bash.bash_o("ipset list | grep -E '^Name|^References' | awk '{print $2}'").splitlines()
        for i in range(0, len(out), 2):
            ipset_ref = out[i:i+2]
            name = ipset_ref[0]
            references = ipset_ref[1]
            if self._is_sg_ipset_name(name) and references == '0':
                to_delete.append(name)
        if to_delete:
            ipset_mn = ipset.IPSetManager()
            logger.debug('deleted unused ipset: %s' % to_delete)
            ipset_mn.clean_ipsets(to_delete)

    @bash.in_bash
    def _delete_all_security_group_chains(self, filter_table, filter6_table):

        ip4_chains = filter_table.get_chains()
        ip6_chains = filter6_table.get_chains()

        for chain in ip4_chains:
            if chain.name.startswith('sg-') or chain.name.startswith('vnic'):
                filter_table.delete_chain(chain.name)
        for chain in ip6_chains:
            if chain.name.startswith('sg-') or chain.name.startswith('vnic'):
                filter6_table.delete_chain(chain.name)

    def _create_sg_default_chain(self, ipt, ip_version):
        if not ipt or not ip_version:
            return
        forward_chain = ipt.add_chain_if_not_exist(iptables.FORWARD_CHAIN_NAME)
        forward_chain.add_rule('-A FORWARD -m physdev --physdev-is-bridged -j %s' % self.ZSTACK_DEFAULT_CHAIN)

        sg_default_chain = ipt.add_chain_if_not_exist(self.ZSTACK_DEFAULT_CHAIN)
        sg_default_chain.flush_chain()
        sg_default_chain.add_default_rule('-A %s -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        sg_default_chain.add_rule('-A %s -m state --state RELATED,ESTABLISHED -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        sg_default_chain.add_rule('-A %s -p udp -m udp --dport 53 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        if ip_version == self.IPV4:
            sg_default_chain.add_rule('-A %s -p udp -m udp --sport 68 --dport 67 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
            sg_default_chain.add_rule('-A %s -p udp -m udp --sport 67 --dport 68 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
        else:
            sg_default_chain.add_rule('-A %s -p udp -m udp --sport 546 --dport 547 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
            sg_default_chain.add_rule('-A %s -p udp -m udp --sport 547 --dport 546 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
            sg_default_chain.add_rule('-A %s -p ipv6-icmp -m icmp6 --icmpv6-type 133 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
            sg_default_chain.add_rule('-A %s -p ipv6-icmp -m icmp6 --icmpv6-type 134 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
            sg_default_chain.add_rule('-A %s -p ipv6-icmp -m icmp6 --icmpv6-type 135 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
            sg_default_chain.add_rule('-A %s -p ipv6-icmp -m icmp6 --icmpv6-type 136 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)
            sg_default_chain.add_rule('-A %s -p ipv6-icmp -m icmp6 --icmpv6-type 137 -j ACCEPT' % self.ZSTACK_DEFAULT_CHAIN)

    def _check_sg_default_rules(self, filter_table, ip_version):
        sg_default_chain = filter_table.get_chain_by_name(self.ZSTACK_DEFAULT_CHAIN)

        if not sg_default_chain:
            self._create_sg_default_chain(filter_table, ip_version)

    def _is_sg_ipset_name(self, name):
        if not name:
            return False
        if name.startswith('zstack-sg') or name.startswith('sg-'):
            return True

    def _is_vnic_chain_name(self, chain_name):
        if not chain_name:
            return False
        if chain_name.startswith('vnic') and (chain_name.endswith('-in') or chain_name.endswith('-out')):
            return True

    def is_sg_chain_name(self, chain_name):
        if not chain_name:
            return False
        if chain_name.startswith('sg-') and (chain_name.endswith('-in') or chain_name.endswith('-out')):
            return True

    def _make_security_group_ipset_name(self, uuid, ip_version):
        # max ipset name is 31 char
        uuid_part = uuid[0:19]
        return '%s-%s' % (self.ZSTACK_IPSET_NAME_FORMAT[ip_version], uuid_part)

    def _make_nic_in_chain_name(self, vif_name):
        return '%s-in' % vif_name

    def _make_nic_out_chain_name(self, vif_name):
        return '%s-out' % vif_name

    def _make_sg_in_chain_name(self, sg_uuid):
        uuid_part = sg_uuid[0:8]
        return 'sg-%s-in' % uuid_part

    def _make_sg_out_chain_name(self, sg_uuid):
        uuid_part = sg_uuid[0:8]
        return 'sg-%s-out' % uuid_part

    def _make_sg_rule_ipset_name(self, sg_uuid, rule_type, priority):
        uuid_part = sg_uuid[0:8]
        if rule_type == RULE_TYPE_INGRESS:
            return 'sg-%s-in-ipset-%s' % (uuid_part, priority)
        else:
            return 'sg-%s-out-ipset-%s' % (uuid_part, priority)

    def _make_sg_rule_comment(self, rule_type, priority):
        return '%s-priority@%s' % (rule_type, priority)

    def _do_make_security_group_rule(self, sg_uuid, ip_version, rto, ipset_mn):
        rule_str = []
        if rto.src_ips:
            if self.IP_SPLIT not in rto.src_ips:
                if self.RANGE_SPLIT in rto.src_ips:
                    rule_str.extend(['-m iprange --src-range', rto.src_ips])
                else:
                    rule_str.extend(['-s', rto.src_ips])
            else:
                ipset_name = self._make_sg_rule_ipset_name(sg_uuid, rto.type, rto.priority)
                ipset_mn.create_set(name=ipset_name, match_ips=rto.src_ips.split(self.IP_SPLIT), ip_version=self.ZSTACK_IPSET_FAMILYS[ip_version])
                rule_str.extend(['-m set --match-set', ipset_name, 'src'])
        if rto.dst_ips:
            if self.IP_SPLIT not in rto.dst_ips:
                if self.RANGE_SPLIT in rto.dst_ips:
                    rule_str.extend(['-m iprange --dst-range', rto.dst_ips])
                else:
                    rule_str.extend(['-d', rto.dst_ips])
            else:
                ipset_name = self._make_sg_rule_ipset_name(sg_uuid, rto.type, rto.priority)
                ipset_mn.create_set(name=ipset_name, match_ips=rto.dst_ips.split(self.IP_SPLIT), ip_version=self.ZSTACK_IPSET_FAMILYS[ip_version])
                rule_str.extend(['-m set --match-set', ipset_name, 'dst'])
        if rto.remote_group_uuid:
            zstack_ipset_name = self._make_security_group_ipset_name(rto.remote_group_uuid, ip_version)
            ipset_mn.create_set(name=zstack_ipset_name, match_ips=rto.remote_group_vm_ips, ip_version=self.ZSTACK_IPSET_FAMILYS[ip_version])
            if rto.type == RULE_TYPE_INGRESS:
                rule_str.extend(['-m state --state NEW', '-m set --match-set', zstack_ipset_name, 'src'])
            else:
                rule_str.extend(['-m state --state NEW', '-m set --match-set', zstack_ipset_name, 'dst'])
        if rto.protocol:
            if rto.protocol == self.PROTOCOL_ICMP:
                if rto.version == self.IPV4:
                    rule_str.append('-p icmp')
                else:
                    rule_str.append('-p ipv6-icmp')
            elif rto.protocol == self.PROTOCOL_TCP:
                rule_str.append('-p tcp -m multiport --dports')
            elif rto.protocol == self.PROTOCOL_UDP:
                rule_str.append('-p udp -m multiport --dports')
        if rto.dst_ports:
            rule_str.append(rto.dst_ports.replace(self.RANGE_SPLIT, self.PORT_SPLIT))

        rule_comment = self._make_sg_rule_comment(rto.type, rto.priority)
        rule_str.extend(['-m comment --comment', rule_comment])

        if rto.action:
            rule_str.extend(['-j', rto.action])

        return rule_str

    @bash.in_bash
    def _do_update_security_group_rules(self, filter_table, filter6_table, ipset_mn, sgs):
        for sg in sgs:
            sg_in_chain_name = self._make_sg_in_chain_name(sg.get_uuid())
            sg_out_chain_name = self._make_sg_out_chain_name(sg.get_uuid())

            if sg.update_ipv4:
                sg_in_chain = filter_table.add_chain(sg_in_chain_name)
                sg_in_chain.flush_chain()
                if sg.get_ingress_rules():
                    sg_in_chain.add_default_rule('-A %s -j RETURN' % sg_in_chain_name)
                    rule_prefix = ['-A', sg_in_chain_name]
                    for ingress_rule in sg.get_ingress_rules():
                        rule_body = self._do_make_security_group_rule(sg.get_uuid(), self.IPV4, ingress_rule, ipset_mn)
                        sg_in_chain.add_rule(' '.join(rule_prefix + rule_body))

                sg_out_chain = filter_table.add_chain(sg_out_chain_name)
                sg_out_chain.flush_chain()
                if sg.get_egress_rules():
                    sg_out_chain.add_default_rule('-A %s -j RETURN' % sg_out_chain_name)
                    rule_prefix = ['-A', sg_out_chain_name]
                    for egress_rule in sg.get_egress_rules():
                        rule_body = self._do_make_security_group_rule(sg.get_uuid(), self.IPV4, egress_rule, ipset_mn)
                        sg_out_chain.add_rule(' '.join(rule_prefix + rule_body))

            if sg.update_ipv6:
                sg_in_chain = filter6_table.add_chain(sg_in_chain_name)
                sg_in_chain.flush_chain()
                if sg.get_ip6_ingress_rules():
                    sg_in_chain.add_default_rule('-A %s -j RETURN' % sg_in_chain_name)
                    rule_prefix = ['-A', sg_in_chain_name]
                    for ingress_ip6_rule in sg.get_ip6_ingress_rules():
                        rule_body = self._do_make_security_group_rule(sg.get_uuid(), self.IPV6, ingress_ip6_rule, ipset_mn)
                        sg_in_chain.add_rule(' '.join(rule_prefix + rule_body))

                sg_out_chain = filter6_table.add_chain(sg_out_chain_name)
                sg_out_chain.flush_chain()
                if sg.get_ip6_egress_rules():
                    sg_out_chain.add_default_rule('-A %s -j RETURN' % sg_out_chain_name)
                    rule_prefix = ['-A', sg_out_chain_name]
                    for egress_ip6_rule in sg.get_ip6_egress_rules():
                        rule_body = self._do_make_security_group_rule(sg.get_uuid(), self.IPV6, egress_ip6_rule, ipset_mn)
                        sg_out_chain.add_rule(' '.join(rule_prefix + rule_body))

    def _delete_vnic_chain(self, filter_table, filter6_table, nic_name):
        in_chain_name = self._make_nic_in_chain_name(nic_name)
        out_chain_name = self._make_nic_out_chain_name(nic_name)

        filter_table.delete_chain(in_chain_name)
        filter_table.delete_chain(out_chain_name)
        filter6_table.delete_chain(in_chain_name)
        filter6_table.delete_chain(out_chain_name)

        sg_default_chain = filter_table.get_chain_by_name(self.ZSTACK_DEFAULT_CHAIN)
        if not sg_default_chain:
            raise Exception('cannot find iptables filter chain[%s]' % self.ZSTACK_DEFAULT_CHAIN)
        sg_default_chain.delete_rule_by_target(in_chain_name)
        sg_default_chain.delete_rule_by_target(out_chain_name)

        sg6_default_chain = filter6_table.get_chain_by_name(self.ZSTACK_DEFAULT_CHAIN)
        if not sg6_default_chain:
            raise Exception('cannot find ip6tables filter chain[%s]' % self.ZSTACK_DEFAULT_CHAIN)
        sg6_default_chain.delete_rule_by_target(in_chain_name)
        sg6_default_chain.delete_rule_by_target(out_chain_name)

    def _do_update_vnic_rules(self, filter_table, filter6_table, nics):
        for nic in nics:
            if nic.action_code == self.ACTION_CODE_DELETE_CHAIN or not nic.security_group_refs:
                self._delete_vnic_chain(filter_table, filter6_table, nic.name)
                continue

            is_ipv4 = False
            is_ipv6 = False
            for addr in nic.ips:
                if ip.is_ipv4(addr):
                    is_ipv4 = True
                else:
                    is_ipv6 = True
            nic_in_chain_name = self._make_nic_in_chain_name(nic.name)
            nic_out_chain_name = self._make_nic_out_chain_name(nic.name)
            nic_in_action = self.RULE_ACTION_RETURN if nic.ingress_policy == self.NIC_SECURITY_POLICY_ALLOW else self.RULE_ACTION_DROP
            nic_out_action = self.RULE_ACTION_RETURN if nic.egress_policy == self.NIC_SECURITY_POLICY_ALLOW else self.RULE_ACTION_DROP

            if is_ipv4:
                sg_default_chain = filter_table.get_chain_by_name(self.ZSTACK_DEFAULT_CHAIN)
                nic_in_chain = filter_table.add_chain(nic_in_chain_name)
                nic_in_chain.flush_chain()
                nic_out_chain = filter_table.add_chain(nic_out_chain_name)
                nic_out_chain.flush_chain()

                for sg_uuid in nic.security_group_refs:
                    nic_in_chain.add_rule('-A %s -j %s' % (nic_in_chain_name, self._make_sg_in_chain_name(sg_uuid)))
                    nic_out_chain.add_rule('-A %s -j %s' % (nic_out_chain_name, self._make_sg_out_chain_name(sg_uuid)))

                nic_in_chain.add_default_rule('-A %s -j %s' % (nic_in_chain_name, nic_in_action))
                nic_out_chain.add_default_rule('-A %s -j %s' % (nic_out_chain_name, nic_out_action))

                #  -A sg-default -m physdev --physdev-out vnic516.0 -j vnic516.0-in
                #  -A sg-default -m physdev --physdev-in vnic516.0 -j vnic516.0-out
                sg_default_chain.add_rule(' '.join(['-A', self.ZSTACK_DEFAULT_CHAIN, '-m physdev --physdev-out', nic.name, '-j', nic_in_chain_name]))
                sg_default_chain.add_rule(' '.join(['-A', self.ZSTACK_DEFAULT_CHAIN, '-m physdev --physdev-in', nic.name, '-j', nic_out_chain_name]))
                self._cleanup_conntrack(nic.ips, "ipv4")
            if is_ipv6:
                sg6_default_chain = filter6_table.get_chain_by_name(self.ZSTACK_DEFAULT_CHAIN)
                nic_in_chain = filter6_table.add_chain(nic_in_chain_name)
                nic_in_chain.flush_chain()
                nic_out_chain = filter6_table.add_chain(nic_out_chain_name)
                nic_out_chain.flush_chain()

                for sg_uuid in nic.security_group_refs:
                    nic_in_chain.add_rule('-A %s -j %s' % (nic_in_chain_name, self._make_sg_in_chain_name(sg_uuid)))
                    nic_out_chain.add_rule('-A %s -j %s' % (nic_out_chain_name, self._make_sg_out_chain_name(sg_uuid)))

                nic_in_chain.add_default_rule('-A %s -j %s' % (nic_in_chain_name, nic_in_action))
                nic_out_chain.add_default_rule('-A %s -j %s' % (nic_out_chain_name, nic_out_action))

                sg6_default_chain.add_rule(' '.join(['-A', self.ZSTACK_DEFAULT_CHAIN, '-m physdev --physdev-out', nic.name, '-j', nic_in_chain_name]))
                sg6_default_chain.add_rule(' '.join(['-A', self.ZSTACK_DEFAULT_CHAIN, '-m physdev --physdev-in', nic.name, '-j', nic_out_chain_name]))
                self._cleanup_conntrack(nic.ips, "ipv6")

    @bash.in_bash
    def _do_apply_security_group_rules(self, cmd, isFlush=False):

        filter_table = iptables.from_iptables_save()
        filter6_table = iptables.from_iptables_save(version=self.IPV6)
        ipset_mn = ipset.IPSetManager()

        if isFlush:
            self._delete_all_security_group_chains(filter_table, filter6_table)

        # check and create sg default rules
        self._check_sg_default_rules(filter_table, self.IPV4)
        self._check_sg_default_rules(filter6_table, self.IPV6)
        # update vnic chain (ipv4 and ipv6)
        self._do_update_vnic_rules(filter_table, filter6_table, cmd.get_nics())
        # update security group chain (ipv4 and ipv6)
        self._do_update_security_group_rules(filter_table, filter6_table, ipset_mn, cmd.get_security_groups())

        ipset_mn.refresh_my_ipsets()
        filter_table.iptables_restore()
        filter6_table.iptables_restore()

        self._cleanup_unused_chain(self.IPV4)
        self._cleanup_unused_chain(self.IPV6)
        self._cleanup_unused_ipset()

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def apply_rules(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ApplySecurityGroupRuleResponse()

        try:
            apply_cmd = ApplySecurityGroupRuleCmd()
            apply_cmd.parse_cmd(cmd)
            self._do_apply_security_group_rules(apply_cmd)
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
            refresh_cmd = ApplySecurityGroupRuleCmd()
            refresh_cmd.parse_cmd(cmd)
            self._do_apply_security_group_rules(refresh_cmd, isFlush=True)
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

        self._cleanup_unused_chain(self.IPV4)
        if cmd.skipIpv6:
            self._cleanup_unused_chain(self.IPV6)

        self._cleanup_unused_ipset()

        self._cleanup_conntrack()

        return jsonobject.dumps(rsp)

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def update_group_member(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateGroupMemberResponse()

        ipset_mn = ipset.IPSetManager()

        to_delete_ipset = []
        for uto in cmd.updateGroupTOs:
            if uto.actionCode == self.ACTION_CODE_DELETE_GROUP:
                to_delete_ipset.append(self._make_security_group_ipset_name(uto.securityGroupUuid, self.IPV4))
                to_delete_ipset.append(self._make_security_group_ipset_name(uto.securityGroupUuid, self.IPV6))
            elif uto.actionCode == self.ACTION_CODE_UPDATE_GROUP_MEMBER:
                ipv4_ipset_name = self._make_security_group_ipset_name(uto.securityGroupUuid, self.IPV4)
                ipv6_ipset_name = self._make_security_group_ipset_name(uto.securityGroupUuid, self.IPV6)
                ipset_mn.create_set(name=ipv4_ipset_name, match_ips=uto.securityGroupVmIps, ip_version=self.ZSTACK_IPSET_FAMILYS[self.IPV4])
                ipset_mn.create_set(name=ipv6_ipset_name, match_ips=uto.securityGroupVmIp6s, ip_version=self.ZSTACK_IPSET_FAMILYS[self.IPV6])
        ipset_mn.refresh_my_ipsets()

        if to_delete_ipset:
            filter_table = iptables.from_iptables_save()
            filter6_table = iptables.from_iptables_save(version=self.IPV6)
            for chain in filter_table.get_chains():
                for rule in chain.rules:
                    if rule.get_ipset_name() and rule.get_ipset_name() in to_delete_ipset:
                        chain.delete_rule(rule.name)
            for chain in filter6_table.get_chains():
                for rule in chain.rules:
                    if rule.get_ipset_name() and rule.get_ipset_name() in to_delete_ipset:
                        chain.delete_rule(rule.name)
            filter_table.iptables_restore()
            filter6_table.iptables_restore()
            ipset_mn.clean_ipsets(to_delete_ipset)

        self._cleanup_conntrack()

        return jsonobject.dumps(rsp)

    @lock.file_lock('/run/xtables.lock')
    @kvmagent.replyerror
    def check_default_sg_rules(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckDefaultSecurityGroupResponse()

        filter_table = iptables.from_iptables_save()
        self._check_sg_default_rules(filter_table, self.IPV4)

        if not cmd.skipIpv6:
            filter6_table = iptables.from_iptables_save(version=self.IPV6)
            self._check_sg_default_rules(filter6_table, self.IPV6)

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

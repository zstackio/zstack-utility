import os
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import ordered_set
from zstacklib.utils.bash import *
from pyparsing import *

logger = log.get_logger(__name__)

_iptablesUseLock = None
_ip6tablesUseLock = None

IPV4 = 4
IPV6 = 6

NAT_TABLE_NAME = 'nat'
FILTER_TABLE_NAME = 'filter'
MANGLE_TABLE_NAME = 'mangle'
SECURITY_TABLE_NAME = 'security'
RAW_TABLE_NAME = 'raw'

FORWARD_CHAIN_NAME = 'FORWARD'

ACCEPT_POLICY = 'ACCEPT'

BUILD_IN_CHAINS_DICT = {
    FILTER_TABLE_NAME: ['INPUT', 'FORWARD', 'OUTPUT'],
    NAT_TABLE_NAME: ['PREROUTING', 'POSTROUTING', 'OUTPUT'],
    MANGLE_TABLE_NAME: ['INPUT', 'OUTPUT', 'FORWARD', 'PREROUTING', 'POSTROUTING'],
    RAW_TABLE_NAME: ['PREROUTING', 'OUTPUT'],
    SECURITY_TABLE_NAME: ['INPUT', 'OUTPUT', 'FORWARD']
}


def get_iptables_cmd(command=None):

    def checkIptablesLock():
        global _iptablesUseLock
        if shell.run("iptables -w -nL > /dev/null") == 0:
            _iptablesUseLock = True
        else:
            _iptablesUseLock = False

    if _iptablesUseLock is None:
        checkIptablesLock()

    if command is None:
        if _iptablesUseLock:
            return "iptables -w"
        return "iptables"
    elif command == "restore":
        if _iptablesUseLock:
            return "iptables-restore -w"
        return "iptables-restore"


def get_ip6tables_cmd(command=None):

    def checkIp6tablesLock():
        global _ip6tablesUseLock
        if shell.run("ip6tables -w -nL > /dev/null") == 0:
            _ip6tablesUseLock = True
        else:
            _ip6tablesUseLock = False

    if _ip6tablesUseLock is None:
        checkIp6tablesLock()

    if command is None:
        if _ip6tablesUseLock:
            return "ip6tables -w"
        return "ip6tables"
    elif command == "restore":
        if _ip6tablesUseLock:
            return "ip6tables-restore -w"
        return "ip6tables-restore"


def from_iptables_save(table=FILTER_TABLE_NAME, version=IPV4):

    return IPTablesTable.from_iptables_save(table, version)


class IPTablesError(Exception):
    '''iptables error'''


class IPTablesParser(object):
    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    def format_to_string(self):
        pass


class IPTabelsRule(IPTablesParser):

    def __init__(self, name):
        super(IPTabelsRule, self).__init__(name)
        self.order = 0
        self.target = None
        self._chain = self._parse_chain(name)

    def __str__(self):
        return self.name

    def _parse_chain(self, name):
        self._chain = self.name.split()[1]

    @property
    def chain(self):
        return self._chain

    def format_to_string(self):
        return self.name

    def get_target(self):
        if '-j' in self.name:
            index = self.name.index('-j')
            self.target = self.name[index + 1]

        return self.target

    def get_ipset_name(self):
        ipset = None
        rs = self.name.split()
        for r in rs:
            if r == '--match-set':
                ipset = rs[rs.index(r) + 1]
                break
        return ipset

    def get_comment(self):
        comment = None
        rs = self.name.split()
        for r in rs:
            if r == '--comment':
                comment = rs[rs.index(r) + 1]
                break
        return comment


class IPTablesChain(IPTablesParser):

    def __init__(self, name, policy=None, counter_num=0, counter_size=0):
        super(IPTablesChain, self).__init__(name)
        self._policy = policy
        self._counter_num = counter_num
        self._counter_size = counter_size
        self._default_rule = None
        self._user_defined_rules = []

    def __str__(self):
        return self.format_to_string()

    @property
    def policy(self):
        return self._policy

    @policy.setter
    def policy(self, policy):
        self._policy = policy

    @property
    def counter_num(self):
        return self._counter_num

    @counter_num.setter
    def counter_num(self, counter_num):
        self._counter_num = counter_num

    @property
    def counter_size(self):
        return self._counter_size

    @counter_size.setter
    def counter_size(self, counter_size):
        self._counter_size = counter_size

    def get_rules(self):
        if self.default_rule is not None:
            return self.user_defined_rules + [self.default_rule]
        return self.user_defined_rules

    @property
    def default_rule(self):
        return self._default_rule

    @default_rule.setter
    def default_rule(self, default_rule):
        self._default_rule = default_rule

    @property
    def user_defined_rules(self):
        return self._user_defined_rules

    @user_defined_rules.setter
    def user_defined_rules(self, rules):
        self._user_defined_rules = rules

    def to_iptables_string(self):
        policy_str = '-' if self.policy is None else self.policy
        chain_name = ":{} {} [{}:{}]".format(self.name, policy_str, self.counter_num, self.counter_size)
        return chain_name

    def format_to_string(self):
        rule_string_list = []
        chain_name = self.to_iptables_string()
        rule_string_list.append(chain_name)
        for r in self.user_defined_rules:
            rule_string_list.append(r.format_to_string())
        if self.default_rule is not None:
            rule_string_list.append(self.default_rule.format_to_string())

        return '\n'.join(rule_string_list)

    def add_default_rule(self, rule):
        _rule = ' '.join(rule.split())
        if _rule.split()[2] != '-j':
            raise IPTablesError("rule:[{}] is not a iptables default rule")

        iptables_rule = IPTabelsRule(_rule)
        self.default_rule = iptables_rule

    def add_rule(self, rule, line_number=-1):
        """add rule for iptables chain

        Args:
            rule (string): iptables rule. eg: '-A INPUT -p icmp -j ACCEPT'
            line_number (int, optional): rule number. Defaults to -1 (append).

        Raises:
            IPTablesError: rule format error
        """
        if not rule:
            return
        chain_name = rule.split()[1]
        if chain_name != self.name:
            raise IPTablesError("rule:[{}] must be in chain[{}]".format(rule, self.name))
        if '-j' not in rule:
            raise IPTablesError("rule:[{}] must have target".format(rule))

        _rule = ' '.join(rule.split())
        for r in self.user_defined_rules:
            if r.name == _rule:
                return

        iptables_rule = IPTabelsRule(_rule)
        # if _rule.split()[2] == '-j':
        #     self.default_rule = iptables_rule
        #     return

        if line_number == -1 or line_number > len(self.user_defined_rules):
            self.user_defined_rules.append(iptables_rule)
        else:
            self.user_defined_rules.insert(line_number - 1, iptables_rule)

    def flush_chain(self):
        self.counter_num = 0
        self.counter_size = 0
        self.user_defined_rules = []
        self.default_rule = None

    def delete_default_rule(self):
        self.default_rule = None

    def delete_rule_by_target(self, target):
        new_rules = []
        for r in self.user_defined_rules:
            if r.get_target() != target:
                new_rules.append(r)
        self.user_defined_rules = new_rules

        if self.default_rule and self.default_rule.get_target() == target:
            self.default_rule = None

    def delete_rule(self, rule):
        rule_str = None
        if isinstance(rule, IPTabelsRule):
            rule_str = rule.name
        else:
            rule_str = rule
        if not rule_str or '-j' not in rule_str:
            return

        new_rules = []
        for r in self.user_defined_rules:
            if r.name != rule_str:
                new_rules.append(r)
        self.user_defined_rules = new_rules

        if self.default_rule and self.default_rule.name == rule_str:
            self.default_rule = None


class IPTablesTable(IPTablesParser):

    def __init__(self, name=FILTER_TABLE_NAME, version=IPV4):
        super(IPTablesTable, self).__init__(name)
        self._parser = None
        # self.name = name
        self._version = version
        self._build_in_chains = []
        self._user_defined_chains = []
        self._build_parser()

    @property
    def version(self):
        return self._version

    @property
    def build_in_chains(self):
        return self._build_in_chains

    @property
    def user_defined_chains(self):
        return self._user_defined_chains

    def __str__(self):
        return self.format_to_string()

    def _build_parser(self):
        table = Literal('*') + Word(alphas)
        table.setParseAction(self._parse_table_action)

        integer = Word(nums).setParseAction(lambda t: int(t[0]))
        chain_name = Word(printables + '.-_+=%$#')
        counters = '[' + integer + ':' + integer + ']'

        # example ":OUTPUT ACCEPT [76:86597]"
        #           ==> [':', 'OUTPUT', 'ACCEPT', '[', 76, ':', 86597, ']']
        chain = Literal(':') + chain_name + Word(printables + '.-_+=%$#') + counters
        chain.setParseAction(self._parse_chain_action)

        comment = Literal('#') + restOfLine

        # example '-A INPUT -p tcp -m comment --comment "zstore.allow.port" -m tcp --dport 8000 -j ACCEPT'
        #           ==> ['-A', 'INPUT', ' -p tcp -m comment --comment "zstore.allow.port" -m tcp --dport 8000 -j ACCEPT']

        rule = Literal('-A') + chain_name + OneOrMore(Word(printables + '.-_+=%$#'))
        rule.setParseAction(self._parse_rule_action)

        commit = Literal('COMMIT')
        commit.setParseAction(self._parse_commit_action)

        self._parser = table | chain | comment | rule | commit

    def _parse_commit_action(self, tokens):
        pass

    def _parse_table_action(self, tokens):
        table_name = tokens[1]
        self.name = table_name

    def _parse_chain_action(self, tokens):
        chain_name = tokens[1]
        policy = None if tokens[2] == '-' else tokens[2]
        counter_num = tokens[4]
        counter_size = tokens[6]
        self.add_chain(chain_name, policy, counter_num, counter_size)

    def _parse_rule_action(self, tokens):
        chain_name = tokens[1]
        chain = self.get_chain_by_name(chain_name)
        if not chain:
            chain = self.add_chain(chain_name)
        chain.add_rule(' '.join(tokens))

    def _sort_build_in_chains(self):
        if self.name not in BUILD_IN_CHAINS_DICT:
            raise IPTablesError('unknown table name: %s' % self.name)

        sorted_list = []
        for chain_name in BUILD_IN_CHAINS_DICT[self.name]:
            for chain in self._build_in_chains:
                if chain.name == chain_name:
                    sorted_list.append(chain)
                    break

        self._build_in_chains = sorted_list

    def format_to_string(self):
        self._sort_build_in_chains()

        table_string_list = []
        chain_string_list = []
        rule_string_list = []

        table_string_list.append('*%s' % self.name)

        for chain in self.get_chains():
            if chain.name not in BUILD_IN_CHAINS_DICT[self.name] and not chain.get_rules():
                continue
            chain_string_list.append(chain.to_iptables_string())
            for r in chain.get_rules():
                rule_string_list.append(r.format_to_string())

        table_string_list.extend(chain_string_list)
        table_string_list.extend(rule_string_list)
        table_string_list.append('COMMIT\n')

        return '\n'.join(table_string_list)

    def _from_iptables_save(self):
        cmd = "/sbin/iptables-save --table={}".format(self.name)
        if self.version == IPV6:
            cmd = "/sbin/ip6tables-save --table={}".format(self.name)

        out = shell.call(cmd)
        for line in out.split('\n'):
            line = line.strip('\n').strip('\r').strip('\t').strip()
            if not line:
                continue
            try:
                self._parser.parseString(line)
            except ParseException as e:
                pass

    @staticmethod
    def from_iptables_save(table=FILTER_TABLE_NAME, version=IPV4):
        ipt = IPTablesTable(table, version)
        ipt._from_iptables_save()
        return ipt

    def iptables_restore(self):
        # if not self.get_chains():
        #     return

        table_str = self.format_to_string()
        f = linux.write_to_temp_file(table_str)

        try:
            if self.version == IPV4:
                shell.call("{} --table={} < {}".format(get_iptables_cmd("restore"), self.name, f))
            else:
                shell.call("{} --table={} --counters < {}".format(get_ip6tables_cmd("restore"), self.name, f))
        except Exception as e:
            res = shell.call('lsof /run/xtables.lock')
            err = '''Failed to apply iptables rules:
shell error description:
%s
result of lsof /run/xtables.lock
%s
iptable rules:
%s
''' % (str(e), str(res), table_str)
            raise IPTablesError(err)
        finally:
            os.remove(f)

    def get_chains(self):
        return self.build_in_chains + self.user_defined_chains

    def get_chain_by_name(self, name):
        for c in self.build_in_chains + self.user_defined_chains:
            if c.name == name:
                return c
        return None

    def _add_chain(self, name, policy=None, counter_num=0, counter_size=0):
        iptables_chain = IPTablesChain(name, policy, counter_num, counter_size)
        if name in BUILD_IN_CHAINS_DICT[self.name]:
            iptables_chain.policy = ACCEPT_POLICY
            self.build_in_chains.append(iptables_chain)
        else:
            self.user_defined_chains.append(iptables_chain)

        return iptables_chain

    def add_chain_if_not_exist(self, name, policy=None, counter_num=0, counter_size=0):
        iptables_chain = self.get_chain_by_name(name)
        if not iptables_chain:
            iptables_chain = self._add_chain(name, policy, counter_num, counter_size)

        return iptables_chain

    def add_chain(self, name, policy=None, counter_num=0, counter_size=0):
        iptables_chain = self.get_chain_by_name(name)
        if not iptables_chain:
            iptables_chain = self._add_chain(name, policy, counter_num, counter_size)

        return iptables_chain

    def delete_chain(self, chain_name):
        for chain in self.build_in_chains:
            if chain.name == chain_name:
                self.build_in_chains.remove(chain)
                return
        for chain in self.user_defined_chains:
            if chain.name == chain_name:
                self.user_defined_chains.remove(chain)
                return

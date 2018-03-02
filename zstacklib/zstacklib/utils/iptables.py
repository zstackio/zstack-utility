'''

@author: frank
'''
import os
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import ordered_set
from pyparsing import *

logger = log.get_logger(__name__)

class IPTablesError(Exception):
    '''iptables error'''
    
class Node(object):
    def __init__(self):
        self.name = None
        self.identity = None
        self.parent = None
        self.children = []
    
    def add_child(self, node):
        self.children.append(node)
        node.parent = self
    
    def get_child_by_name(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None
    
    def get_child_by_identity(self, identity):
        for c in self.children:
            if c.identity == identity:
                return c
        return None
    
    def insert_child_before(self, n1, n2):
        pos = self.children.index(n1)
        self.children.insert(pos-1, n2)
        n2.parent = self
        
    def insert_child_after(self, n1, n2):
        pos = self.children.index(n1)
        self.children.insert(pos+1, n2)
        n2.parent = self
    
    def insert_child_all_after_by_name(self, name, node):
        n = self.search_by_name(name)
        if not n:
            raise ValueError('cannot find node[name:%s]' % name)
        n.parent.insert_child_after(n, node)
        
    def insert_child_all_after_by_identity(self, identity, node):
        n = self.search_by_identity(identity)
        if not n:
            raise ValueError('cannot find node[identity:%s]' % identity)
        n.parent.insert_child_after(n, node)
        
    def insert_child_all_before_by_name(self, name, node):
        n = self.search_by_name(name)
        if not n:
            raise ValueError('cannot find node[name:%s]' % name)
        n.parent.insert_child_before(n, node)
        
    def insert_child_all_before_by_identity(self, identity, node):
        n = self.search_by_identity(identity)
        if not n:
            raise ValueError('cannot find node[identity:%s]' % identity)
        n.parent.insert_child_before(n, node)
    
    def delete_child_by_name(self, name):
        c = self.get_child_by_name(name)
        if c:
            self.children.remove(c)
            c.parent = None
    
    def delete_child_by_identity(self, identity):
        c = self.get_child_by_identity(identity)
        if c:
            self.children.remove(c)
            c.parent = None
    
    def walk(self, callback, data=None):
        def do_walk(node):
            if callback(node, data):
                return node
            
            for n in node.children:
                ret = do_walk(n)
                if ret:
                    return ret
        
        return do_walk(self)
    
    def walk_all(self, callback, data=None):
        ret = []
        def do_walk_all(node):
            if callback(node, data):
                ret.append(node)
                
            for n in node.children:
                do_walk_all(n)
        
        do_walk_all(self)
        return ret
        
    def search_by_name(self, name):
        return self.walk((lambda n, u: n.name == name), None)
    
    def search_by_identity(self, identity):
        return self.walk((lambda n, u: n.identity == identity), None)
    
    def search_all_by_name(self, name):
        return self.walk_all((lambda n, u: n.name == name), None)
    
    def search_all_by_identity(self, identity):
        return self.walk_all((lambda n, u: n.identity == identity), None)
    
    def delete_all_by_name(self, name):
        lst = self.search_all_by_name(name)
        for l in lst:
            l.delete()
    
    def delete_all_by_identity(self, identity):
        lst = self.search_all_by_identity(identity)
        for l in lst:
            l.delete()
    
    def delete(self):
        if self.parent:
            self.parent.children.remove(self)
            self.parent = None
    
    def __str__(self):
        return self.identity

class IPTableTable(Node):
    def __init__(self):
        super(IPTableTable, self).__init__()
        
    def __str__(self):
        # if the chain has been deleted, don't add the its counter
        lst = ['%s' % self.identity]
        for chain in self.children:
            lst.append(chain.counter_str)
            
        for chain in self.children:
            cstr = str(chain)
            if cstr == '':
                continue
            lst.append(cstr)
        lst.append('COMMIT')
        return '\n'.join(lst)

class IPTableChain(Node):
    def __init__(self):
        super(IPTableChain, self).__init__()
        self.counter_str = None
    
    def delete_all_rules(self):
        self.children = []
    
    def __str__(self):
        if not self.children:
            return ''

        rules = []
        for r in self.children:
            rules.append(r)

        def sort(r1, r2):
            return r1.order - r2.order

        rules = sorted(rules, sort, reverse=True)
        lst = ordered_set.OrderedSet()
        for r in rules:
            lst.add(str(r))

        return '\n'.join(lst)

class IPTableRule(Node):
    def __init__(self):
        super(IPTableRule, self).__init__()
        self.order = 0
    
    def __str__(self):
        return self.identity

class IPTables(Node):
    NAT_TABLE_NAME = 'nat'
    FILTER_TABLE_NAME = 'filter'
    MANGLE_TABLE_NAME = 'mangle'
    SECURITY_TABLE_NAME = 'security'
    RAW_TABLE_NAME = 'raw'

    def __init__(self):
        super(IPTables, self).__init__()
        self._parser = None
        self._current_table = None
        self._filter_table = None
        self._nat_table = None
        self._mangle_table = None
        self._raw_table = None
        self._security_table = None
    
    def get_table(self, table_name=FILTER_TABLE_NAME):
        return self.get_child_by_name(table_name)
    
    def get_chain(self, chain_name, table_name=FILTER_TABLE_NAME):
        tbl = self.get_child_by_name(table_name)
        if not tbl:
            return None
        
        return tbl.get_child_by_name(chain_name)
    
    def _create_table_if_not_exists(self, table_name):
        table_name = table_name.strip()
        table_identity = '*%s' % table_name
        table = self.get_child_by_identity(table_identity)
        if not table:
            table = IPTableTable()
            table.identity = table_identity
            table.name = table_name
            table.parent = self
            self.add_child(table)
        self._current_table = table
            
        if table_name == self.NAT_TABLE_NAME:
            self._nat_table = table
        elif table_name == self.FILTER_TABLE_NAME:
            self._filter_table = table
        elif table_name == self.MANGLE_TABLE_NAME:
            self._mangle_table = table
        elif table_name == self.SECURITY_TABLE_NAME:
            self._security_table = table
        elif table_name == self.RAW_TABLE_NAME:
            self._raw_table = table
        else:
            assert 0, 'unknown table name: %s' % table_name
        
    def _parse_table_action(self, tokens):
        table_name = tokens[1]
        self._create_table_if_not_exists(table_name)
    
    def _parse_commit_action(self, tokens):
        self._current_table = None
    
    def _create_chain_if_not_exists(self, chain_name, counter_str=None):
        chain = self._current_table.get_child_by_name(chain_name)
        if not chain:
            chain = IPTableChain()
            chain.parent = self._current_table
            chain.name = chain_name
            chain.identity = chain_name
            if not counter_str:
                counter_str = ':%s - [0:0]' % chain_name
            chain.counter_str = counter_str
            self._current_table.add_child(chain)
        return chain
        
    def _parse_counter_action(self, tokens):
        chain_name = tokens[1]
        prefix = ':%s' % chain_name
        lst = [prefix]
        lst.extend(tokens[2:])
        counter_str = ' '.join(lst)
        self._create_chain_if_not_exists(chain_name, counter_str)
    
    def _add_rule(self, chain_name, rule_identity, order=0):
        chain = self._create_chain_if_not_exists(chain_name)
        rule = IPTableRule()
        rule_identity = self._normalize_rule(rule_identity)
        rule.name = rule_identity
        rule.identity = rule_identity
        rule.parent = chain
        rule.order = order
        chain.add_child(rule)
        
    def _parse_rule_action(self, tokens):
        chain_name = tokens[1]
        self._add_rule(chain_name, ' '.join(tokens))
    
    def _construct_pyparsing(self):
        if self._parser:
            return
        
        table = Literal('*') + Word(alphas)
        table.setParseAction(self._parse_table_action)
        
        chain_name = Word(printables + '.-_+=%$#')
        
        counter = Literal(':') + chain_name + restOfLine
        counter.setParseAction(self._parse_counter_action)
        
        comment = Literal('#') + restOfLine
        
        rule = Literal('-A') + chain_name + restOfLine
        rule.setParseAction(self._parse_rule_action)
        
        commit = Literal('COMMIT')
        commit.setParseAction(self._parse_commit_action)
        
        self._parser = table | counter | comment | rule | commit
        
    @staticmethod
    def find_target_in_rule(rule):
        #TODO: find pyparsing way
        if isinstance(rule, IPTableRule):
            rs = str(rule).split()
        else:
            rs = rule.split()

        target = None
        for r in rs:
            if r == '-j':
                target = rs[rs.index(r) + 1]
                
        return target

    @staticmethod
    def find_ipset_in_rule(rule):
        if isinstance(rule, IPTableRule):
            rs = str(rule).split()
        else:
            rs = rule.split()

        ipset = None
        for r in rs:
            if r == '--match-set':
                ipset = rs[rs.index(r) + 1]
                break
        return ipset
    
    @staticmethod
    def is_target_in_rule(rule, target):
        ret = IPTables.find_target_in_rule(rule)
        return target == ret
        
    @staticmethod
    def find_target_chain_name_in_rule(rule):
        target = IPTables.find_target_in_rule(rule)

        # assume target in upper case are default targets
        if target and target.isupper():
            target = None
            
        return target

    def list_used_ipset_name(self):
        sets_name = []
        rules = self.list_reference_ipset_rules(None)
        for r in rules:
            set_name = self.find_ipset_in_rule(r)
            if set_name not in sets_name:
                sets_name.append(set_name)

        return sets_name

    def list_reference_ipset_rules(self, ipsets=None):
        def walker(rule, data):
            if not isinstance(rule, IPTableRule):
                return False

            if ipsets is not None and self.find_ipset_in_rule(rule) in ipsets:
                return True
            elif ipsets is None and self.find_ipset_in_rule(rule):
                return True

            return False

        rules = self.walk_all(walker, None)
        return rules

        
    def _reset(self):
        self.children = []
        self._current_table = None
        self._nat_table = None
        self._filter_table = None
        self._mangle_table = None
        
    def _from_iptables_save(self, txt):
        self._reset()
        self._construct_pyparsing()
        for l in txt.split('\n'):
            l = l.strip('\n').strip('\r').strip('\t').strip()
            if not l:
                continue
            
            self._parser.parseString(l)
    
    def iptables_save(self):
        out = shell.call('/sbin/iptables-save')
        self._from_iptables_save(out)
    
    def __str__(self):
        lst = []
        for table in self.children:
            lst.append(str(table))
        # iptables-save needs a new line as ending
        lst.append('') 
        return '\n'.join(lst)
    
    def _cleanup_empty_chain(self):
        def _is_chain_not_targeted(chain,table):
            need_deleted = True
            for chain2 in table.children:
                if chain2.children:
                    for rule1 in chain2.children:
                        if IPTables.is_target_in_rule(rule1,chain.name):
                            need_deleted = False
                            break
            return need_deleted
    
        def _clean_chain_having_no_rules():
            chains_to_delete = []
            for t in self.children:
                for c in t.children:
                    if not c.children:
                        if _is_chain_not_targeted(c,t): 
                            chains_to_delete.append(c) 

            empty_chain_names = []
            for c in chains_to_delete:
                if c.name in ['INPUT', 'FORWARD', 'OUTPUT', 'PREROUTING', 'POSTROUTING']:
                    continue

                empty_chain_names.append(c.name)
                c.delete()

            return empty_chain_names
            
        
        def _clean_rule_having_stale_target_chain():
            alive_chain_names = []
            for t in self.children:
                for c in t.children:
                    alive_chain_names.append(c.name)

            def walker(rule, data):
                if not isinstance(rule, IPTableRule):
                    return False
                
                chain_name = self.find_target_chain_name_in_rule(rule.identity)
                if chain_name and (chain_name not in alive_chain_names):
                    return True
                
                return False
                

            return self.walk_all(walker, None)
        
        empty_chain_names = _clean_chain_having_no_rules()
        logger.debug('removed empty chains:%s' % empty_chain_names)
        rules_to_delete = _clean_rule_having_stale_target_chain()
        for r in rules_to_delete:
            logger.debug('delete rule[%s] which has defunct target' % str(r))
            r.delete()

    def _sort_chains(self, sys_chain_names, chains, sort_func):
        all_chains = []
        user_chains = []
        for chain in chains:
            if chain.name in sys_chain_names:
                all_chains.append(chain)
            else:
                user_chains.append(chain)

        user_chains = sorted(user_chains, sort_func)
        all_chains.extend(user_chains)
        return all_chains

    def _sort_chain_in_filter_table(self, sort_func):
        if self._filter_table is None:
            return

        self._filter_table.children = self._sort_chains(['INPUT', 'FORWARD', 'OUTPUT'], self._filter_table.children, sort_func)

    def _sort_chain_in_nat_table(self, sort_func):
        if self._nat_table is None:
            return

        self._nat_table.children = self._sort_chains(['PREROUTING', 'POSTROUTING', 'OUTPUT'], self._nat_table.children, sort_func)

    def _sort_chain_in_mangle_table(self, sort_func):
        if self._mangle_table is None:
            return

        self._mangle_table.children = self._sort_chains(['PREROUTING', 'INPUT', 'FORWARD', 'OUTPUT', 'POSTROUTING'],
                                                        self._mangle_table.children, sort_func)

    def cleanup_unused_chain(self, is_cleanup, table_name=FILTER_TABLE_NAME, data=None):
        table = self.get_child_by_name(table_name)
        if not table:
            return

        sys_chain_names = ['INPUT', 'FORWARD', 'OUTPUT', 'PREROUTING', 'POSTROUTING']
        to_del = []
        for chain in table.children:
            if chain.name in sys_chain_names:
                continue
            if is_cleanup(chain, data):
                to_del.append(chain.name)

        for cname in to_del:
            table.delete_child_by_name(cname)

    def _to_iptables_string(self, marshall_func=None, sort_nat_func=None, sort_filter_func=None, sort_mangle_func=None):
        self._cleanup_empty_chain()

        if sort_filter_func:
            self._sort_chain_in_filter_table(sort_filter_func)
        if sort_mangle_func:
            self._sort_chain_in_mangle_table(sort_mangle_func)
        if sort_nat_func:
            self._sort_chain_in_nat_table(sort_nat_func)

        def make_reject_rule_last(r1, r2):
            if self.is_target_in_rule(r1, 'REJECT'):
                return 1
            if self.is_target_in_rule(r2, 'REJECT'):
                return -1
            return 0

        for c in self._filter_table.children:
            c.children = sorted(c.children, make_reject_rule_last)

        content = str(self)
        if marshall_func:
            content = marshall_func(content)

        return content

    def iptable_restore(self, marshall_func=None, sort_nat_func=None, sort_filter_func=None, sort_mangle_func=None):
        content = self._to_iptables_string(marshall_func, sort_nat_func, sort_filter_func, sort_mangle_func)
        f = linux.write_to_temp_file(content)
        try:
            shell.call('/sbin/iptables-restore < %s' % f)
        except Exception as e:
            err ='''Failed to apply iptables rules:
shell error description:
%s
iptable rules:
%s
''' % (str(e), content)
            raise IPTablesError(err)
        finally:
            os.remove(f)
            
    @staticmethod
    def from_iptables_save():
        ipt = IPTables()
        ipt.iptables_save()
        return ipt
    
    def _normalize_rule(self, rule):
        return ' '.join(rule.strip().split())
    
    def add_rule(self, rule, table_name=FILTER_TABLE_NAME, order=0):
        if table_name not in [self.FILTER_TABLE_NAME, self.NAT_TABLE_NAME, self.MANGLE_TABLE_NAME]:
            raise IPTablesError('unknown table name[%s]' % table_name)
        
        self._create_table_if_not_exists(table_name)
        chain_name = Word(printables + '-_+=%$#')
        rule_p = Literal('-A') + chain_name + restOfLine
        res = rule_p.parseString(rule)
        self._add_rule(res[1], rule, order)
    
    def remove_rule(self, rule_str):
        rule_str = self._normalize_rule(rule_str)
        self.delete_all_by_identity(rule_str)
    
    def search_all_rule(self, rule_str):
        rule_str = self._normalize_rule(rule_str)
        return self.search_all_by_identity(rule_str)
        
    def search_rule(self, rule_str):
        rule_str = self._normalize_rule(rule_str)
        return self.search_by_identity(rule_str)
    
    def delete_chain(self, chain_name, table_name=FILTER_TABLE_NAME):
        table = self.get_child_by_name(table_name)
        if not table:
            return
        table.delete_child_by_name(chain_name)

def from_iptables_save():
    return IPTables.from_iptables_save()

def insert_single_rule_to_filter_table(rule):
    insert_rule = rule.replace('-A', '-I')
    shell.call("/sbin/iptables-save | grep -- '{0}' > /dev/null || iptables {1}".format(rule, insert_rule))

if __name__ == '__main__':
    ipt = IPTables.from_iptables_save()
    rule1 = '-A INPUT -i virbr0 -p udp -m udp --dport 99 -j ACCEPT'
    #rule2 = '-A xxxx -i virbr0 -p udp -m udp --dport 100 -j ACCEPT'
    #ipt.remove_rule(rule1)
    #ipt.add_rule(rule2)
    #ipt.iptable_restore()
    #ipt.delete_chain('INPUT')
    ipt.add_rule(rule1)
    ipt.add_rule(rule1)
    ipt.add_rule(rule1)
    ipt.iptable_restore()
    ipt.iptables_save()
    print ipt

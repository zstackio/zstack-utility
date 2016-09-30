'''

@author: frank
'''

from matches import *
from targets import *
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import xmlobject
from zstacklib.utils import linux
import os

class IPTablesError(Exception):
    '''iptables error'''
    

logger = log.get_logger(__name__)

class Rule(object):
    def __init__(self):
        self.matches = []
        self.target = None
        self.rule_xml_object = None
        self.match_classes = {}
    
    def _parse(self):
        condition_obj = self.rule_xml_object.conditions
        if hasattr(condition_obj, 'match'):
            match_obj = condition_obj.match
            for name, mo in match_obj.get_children_nodes().items():
                match_class = get_match(mo.get_tag())
                if not match_class:
                    raise IPTablesError('unable to find match for <%s/>' % mo.get_tag())
                m = match_class.interpret(mo)
                assert m, 'why does %s return None match???' % match_class.__name__
                self.matches.append(m)
                self.match_classes[match_class.__name__] = m
        
        for name, other in condition_obj.get_children_nodes().items():
            if other.get_tag() == 'match':
                continue
            other_match_class = get_match(other.get_tag())
            if not other_match_class:
                raise IPTablesError('unable to find match for <%s/>' % other.get_tag())
            m = other_match_class.interpret(other)
            assert m, 'why does %s return None match???' % other_match_class.__name__
            self.matches.append(m)
            self.match_classes[other_match_class.__name__] = m
        
        action_objs = self.rule_xml_object.actions
        for name, to in action_objs.get_children_nodes().items():
            target_class = get_target(to.get_tag())
            if not target_class:
                raise IPTablesError('unable to find target for <%s/>' % to.get_tag())
            t = target_class.interpret(to)
            assert t, 'why does %s return None target???' % target_class.__name__
            self.target = t
            break
    
    def add_match(self, m):
        if not isinstance(m, IPTableMatch):
            raise '%s is not subclass of IPTableMatch' % m.__class__.__name__
        
        self.matches.append(m)
    
    def insert_match(self, index, m):
        if not isinstance(m, IPTableMatch):
            raise '%s is not subclass of IPTableMatch' % m.__class__.__name__
        
        self.matches.insert(index, m)
    
    def set_target(self, t):
        if not isinstance(t, IPTableTarget):
            raise '%s is not subclass of IPTableTarget' % t.__class__.__name__
        
        self.target = t
    
    def __str__(self):
        cadidate_matches = []
        if (ProtocolMatch.__name__ in self.match_classes
            and (TcpMatch.__name__ in self.match_classes or
                 UdpMatch.__name__ in self.match_classes or
                 IcmpMatch.__name__ in self.match_classes)):
            for key, value in self.match_classes.items():
                if key == ProtocolMatch.__name__:
                    continue
                cadidate_matches.append(value)
        else:
            cadidate_matches = self.matches
            
        s = []
        for m in cadidate_matches:
            s.append(str(m))
        s.append(str(self.target))
        return ' '.join(s)

class Chain(object):
    def __init__(self):
        self.name = None
        self.chain_xml_object = None
        self.rules = []
        self.policy = None
        self.packet_count = None
        self.byte_count = None
    
    def _parse_rules(self):
        self.name = self.chain_xml_object.name_
        rule_objs = self.chain_xml_object.get_child_node_as_list('rule')
        if not rule_objs:
            return
        
        for ro in rule_objs:
            r = Rule()
            r.rule_xml_object = ro
            r._parse()
            self.rules.append(r)
    
    def add_rule(self, r):
        if not isinstance(r, Rule):
            raise IPTablesError('%s is not instance of Rule' % r.__class__.__name__)
        self.rules.append(r)
    
    def __str__(self):
        s = set()
        for r in self.rules:
            rs = '-A %s %s' % (self.name, str(r))
            s.add(rs)
        return '\n'.join(s)
            
class Table(object):
    def __init__(self):
        self.chains = {}
        self.name = None
        self.table_xml_object = None
    
    def _parse_chains(self):
        self.name = self.table_xml_object.name_
        chain_objs = self.table_xml_object.get_child_node('chain')
        for co in chain_objs:
            c = Chain()
            c.chain_xml_object = co
            c.policy = co.policy__
            c.packet_count = co.get('packet-count_', 0)
            c.byte_count = co.get('byte-count_', 0)
            c._parse_rules()
            self.chains[c.name] = c
    
    def get_chain(self, chainname):
        return self.chains.get(chainname)
    
    def add_chain(self, c):
        if not isinstance(c, Chain):
            raise IPTablesError('%s is not instance of Chain' % c.__class__.__name__)
        
        self.chains[c.name] = c
    
    def __str__(self):
        s = ['*' + self.name]
        for cname, c in self.chains.items():
            if cname in IPTables.BUILTIN_CHAINS:
                s.insert(1, ':%s %s [%s:%s]' % (cname, c.policy, c.packet_count, c.byte_count))
            else:
                s.append(':%s - [%s:%s]' % (cname, c.packet_count, c.byte_count))
        for c in self.chains.values():
            chain_str = str(c)
            if chain_str != '':
                s.append(chain_str)
        s.append('COMMIT')
        return '\n'.join(s)
        
class IPTables(object):
    CMD_APPEND = '--append'
    CMD_DELETE = '--delete'
    CMD_INSERT = '--insert'
    CMD_REPLACE = '--replace'
    CMD_LIST = '--list'
    CMD_LIST_RULES = '--list-rules'
    CMD_FLUSH = '--flush'
    CMD_ZERO = '--zero'
    CMD_NEW_CHAIN = '--new-chain'
    CMD_DELETE_CHAIN = '--delete-chain'
    CMD_POLICY = '--policy'
    CMD_RENAME_CHAIN = '--rename-chain'
    
    TABLE_NAT = 'nat'
    TABLE_MANGLE = 'mangle'
    TABLE_FILTER = 'filter'
    
    CHAIN_INPUT = 'INPUT'
    CHAIN_OUTPUT = 'OUTPUT'
    CHAIN_FORWARD = 'FORWARD'
    CHAIN_PREROUTING = 'PREROUTING'
    CHAIN_POSTROUTING = 'POSTROUTING'
    
    BUILTIN_CHAINS = [CHAIN_INPUT, CHAIN_OUTPUT, CHAIN_FORWARD, CHAIN_PREROUTING, CHAIN_POSTROUTING]
    
    def __init__(self):
        self.tables = {}
    
    def get_chain(self, tablename, chainname):
        t = self.get_table(tablename)
        if not t:
            return None
        return t.get_chain(chainname)
    
    def get_chain_in_filter_table(self, chainname):
        t = self.get_filter_table()
        if t:
            return t.get_chain(chainname)
        else:
            return None
        
    def get_table(self, table_name):
        return self.tables.get(table_name)
        
    def get_nat_table(self):
        return self.get_table(self.TABLE_NAT)
    
    def get_filter_table(self):
        return self.get_table(self.TABLE_FILTER)
    
    def get_mangle_table(self):
        return self.get_table(self.TABLE_FILTER)
    
    def add_rule_to_chain_in_table(self, tblname, chainname, rule):
        tbl = self.get_table(tblname)
        if not tbl:
            tbl = Table()
            tbl.name = tblname
            self.tables[tblname] = tbl
        
        chain = tbl.get_chain(chainname);
        if not chain:
            chain = Chain()
            chain.name = chainname
            tbl.add_chain(chain)
        
        chain.add_rule(rule)
    
    def filter_table_add_rule_to_chain(self, chainname, rule):
        self.add_rule_to_chain_in_table(self.TABLE_FILTER, chainname, rule)
    
    def nat_table_add_rule_to_chain(self, chainname, rule):
        self.add_rule_to_chain_in_table(self.TABLE_NAT, chainname, rule)
        
    def mangle_table_add_rule_to_chain(self, chainname, rule):
        self.add_rule_to_chain_in_table(self.TABLE_MANGLE, chainname, rule)
    
    def filter_table_input_chain_add_rule(self, rule):
        self.filter_table_add_rule_to_chain(self.CHAIN_INPUT, rule)
        
    def filter_table_output_chain_add_rule(self, rule):
        self.filter_table_add_rule_to_chain(self.CHAIN_OUTPUT, rule)
        
    def filter_table_forward_chain_add_rule(self, rule):
        self.filter_table_add_rule_to_chain(self.CHAIN_FORWARD, rule)
    
    def nat_table_prerouting_chain_add_rule(self, rule):
        self.nat_table_add_rule_to_chain(self.CHAIN_PREROUTING, rule)
        
    def nat_table_postrouting_chain_add_rule(self, rule):
        self.nat_table_add_rule_to_chain(self.CHAIN_POSTROUTING, rule)
    
    def __str__(self):
        content = []
        for tbl in self.tables.values():
            content.append(str(tbl))
        ret = '\n'.join(content)
        
        # iptables-save format need a '\n' at end
        return '%s\n' % ret
    
    def apply(self):
        content = str(self)
        self.apply_iptables_save_doc(content)
    
    @staticmethod
    def apply_iptables_save_doc(content):
        f = linux.write_to_temp_file(content)
        try:
            logger.debug('apply iptables:\n %s' % content)
            shell.call('/sbin/iptables-restore < %s' % f)
        finally:
            os.remove(f)
    
    @staticmethod
    def from_iptables_xml():
        output = shell.call('/sbin/iptables-save | /bin/iptables-xml')
        obj = xmlobject.loads(output)
        ret = IPTables()
        
        if not xmlobject.has_element(obj, 'table'):
            return None
        
        for to in obj.table:
            t = Table()
            t.table_xml_object = to
            t._parse_chains()
            ret.tables[t.name] = t
        return ret

def from_iptables_xml():
    return IPTables.from_iptables_xml()

def apply_iptables_save_doc(content):
    IPTables.apply_iptables_save_doc(content)
'''

@author: frank
'''
import sys
import inspect

class MatchError(Exception):
    '''match error'''
    
class IPTableMatch(object):
    def __ne__(self, other):
        return not self.__eq__(other)
    
    @staticmethod
    def interpret(args):
        return None
    
class ProtocolMatch(IPTableMatch):
    tag = 'p'
    
    def __init__(self):
        self.protocol = None
        self.is_invert = False
        
    @staticmethod
    def interpret(xmlobj):
        m = ProtocolMatch()
        m.protocol = xmlobj.text_
        if xmlobj.invert__:
            m.is_invert = True
        return m
    
    def __eq__(self, other):
        if not isinstance(other, ProtocolMatch):
            return False
        
        return other.protocol == self.protocol
    
    def __str__(self):
        if self.is_invert:
            return '! -p %s' % self.protocol
        else:
            return '-p %s' % self.protocol

class SourceMatch(IPTableMatch):
    tag = 's'
    
    def __init__(self):
        self.source_ip = None
        self.is_invert = False
        
    @staticmethod
    def interpret(xmlobj):
        m = SourceMatch()
        m.source_ip = xmlobj.text_
        if xmlobj.invert__:
            m.is_invert = True
        return m
    
    def __eq__(self, other):
        if not isinstance(other, SourceMatch):
            return False
        return self.source_ip == other.source_ip
    
    def __str__(self):
        if self.is_invert:
            return '! -s %s' % self.source_ip
        else:
            return '-s %s' % self.source_ip

class DestMatch(IPTableMatch):
    tag = 'd'
    
    def __init__(self):
        self.dest_ip = None
        self.is_invert = False
        
    @staticmethod
    def interpret(xmlobj):
        m = DestMatch()
        m.dest_ip = xmlobj.text_
        if xmlobj.invert__:
            m.is_invert = True
        return m
    
    def __eq__(self, other):
        if not isinstance(other, DestMatch):
            return False
        return self.dest_ip == other.dest_ip
    
    def __str__(self):
        if self.is_invert:
            return '! -d %s' % self.dest_ip
        else:
            return '-d %s' % self.dest_ip

class InMatch(IPTableMatch):
    tag = 'i'
    
    def __init__(self):
        self.in_interface = None
        self.is_invert = False
        
    @staticmethod
    def interpret(xmlobj):
        m = InMatch()
        m.in_interface = xmlobj.text_
        if xmlobj.invert__:
            m.is_invert = True
        return m
    
    def __eq__(self, other):
        if not isinstance(other, InMatch):
            return False
        return self.in_interface == other.in_interface
    
    def __str__(self):
        if self.is_invert:
            return '! -i %s' % self.in_interface
        else:
            return '-i %s' % self.in_interface

class OutMatch(IPTableMatch):
    tag = 'o'
    
    def __init__(self):
        self.out_interface = None
        self.is_invert = False
        
    @staticmethod
    def interpret(xmlobj):
        m = OutMatch()
        m.out_interface = xmlobj.text_
        if xmlobj.invert__:
            m.is_invert = True
        return m
    
    def __eq__(self, other):
        if not isinstance(other, OutMatch):
            return False
        return self.out_interface == other.out_interface
    
    def __str__(self):
        if self.is_invert:
            return '! -o %s' % self.out_interface
        else:
            return '-o %s' % self.out_interface

class FragmentMatch(IPTableMatch):
    tag = 'f'
    
    def __init__(self):
        self.is_invert = False
    
    @staticmethod
    def interpret(xmlobj):
        m = FragmentMatch()
        if xmlobj.invert__:
            m.is_invert = True
        
    def __eq__(self, other):
        if not isinstance(other, FragmentMatch):
            return False
        return self.is_invert == other.is_invert
    
    def __str__(self):
        if self.is_invert:
            return '! -f'
        else:
            return '-f'

class UdpMatch(IPTableMatch):
    tag = 'udp'
    
    def __init__(self):
        self.sport = None
        self.invert_sport = False
        self.dport = None
        self.invert_dport = False
    
    @staticmethod
    def interpret(xmlobj):
        m = UdpMatch()
        sp = xmlobj.get_child_node('sport')
        if sp:
            m.sport = sp.text_
            if sp.invert__:
                m.invert_sport = True
        dp = xmlobj.get_child_node('dport')
        if dp:
            m.dport = dp.text_
            if dp.invert__:
                m.invert_dport = True
        return m
    
    def __eq__(self, other):
        if not isinstance(other, UdpMatch):
            return False
        
        return (self.sport == other.sport and
                self.dport == other.dport and
                self.invert_sport == other.invert_sport and
                self.invert_dport == other.invert_dport)
    
    def __str__(self):
        s = ['-p udp -m udp']
        if self.sport:
            if self.invert_sport:
                s.append('!')
            s.append('--sport %s' % self.sport)
        if self.dport:
            if self.invert_dport:
                s.append('!')
            s.append('--dport %s' % self.dport)
        return ' '.join(s)
        
class TcpMatch(IPTableMatch):
    tag = 'tcp'
    
    def __init__(self):
        self.sport = None
        self.invert_sport = False
        self.dport = None
        self.invert_dport = False
        self.tcp_flags = None
        self.invert_tcp_flags = False
        self.syn = None
        self.invert_syn = False
        self.tcp_options = None
        self.invert_tcp_options = False
        
    @staticmethod
    def interpret(xmlobj):
        m = TcpMatch()
        sp = xmlobj.get_child_node('sport')
        if sp:
            m.sport = sp.text_
            if sp.invert__:
                m.invert_sport = True
        dp = xmlobj.get_child_node('dport')
        if dp:
            m.dport = dp.text_
            if dp.invert__:
                m.invert_dport = True
        syn = xmlobj.get_child_node('syn')
        if syn:
            m.syn = syn.text_
            if syn.invert__:
                m.invert_syn = True
        flags = xmlobj.get_child_node('tcp-flags')
        if flags:
            m.tcp_flags = flags.text_
            if flags.invert__:
                m.invert_tcp_flags = True
        options = xmlobj.get_child_node('tcp-options') 
        if options:
            m.tcp_options = options.text_
            if options.invert__:
                m.invert_tcp_options = True
                
        return m
    
    def __eq__(self, other):
        if not isinstance(other, TcpMatch):
            return False
        
        return (self.sport == other.sport and
                self.dport == other.dport and
                self.tcp_flags == other.tcp_flags and
                self.tcp_options == other.tcp_options and
                self.syn == other.syn and 
                self.invert_dport == other.invert_dport and
                self.invert_sport == other.invert_sport and
                self.invert_syn == other.invert_syn and
                self.invert_tcp_flags == other.invert_tcp_flags and
                self.invert_tcp_options == other.invert_tcp_options)
    
    def __str__(self):
        s = ['-p tcp -m tcp']
        if self.sport:
            if self.invert_sport:
                s.append('!')
            s.append('--sport %s' % self.sport)
        if self.dport:
            if self.invert_dport:
                s.append('!')
            s.append('--dport %s' % self.dport)
        if self.syn:
            if self.invert_syn:
                s.append('!')
            s.append('--syn %s' % self.syn)
        if self.tcp_flags:
            if self.invert_tcp_flags:
                s.append('!')
            s.append('--tcp-flags %s' % self.tcp_flags)
        if self.tcp_options:
            if self.invert_tcp_options:
                s.append('!')
            s.append('--tcp-options %s' % self.tcp_options)
        return ' '.join(s)

class IcmpMatch(IPTableMatch):
    tag = 'icmp'
    
    def __init__(self):
        self.icmp_type = None
        self.is_invert = False
    
    @staticmethod
    def interpret(xmlobj):
        m = IcmpMatch()
        type = xmlobj.get_child_node('icmp-type')
        if type:
            m.icmp_type = type.text_
            if type.invert__:
                m.is_invert = True
        return m
    
    def __eq__(self, other):
        if not isinstance(other, IcmpMatch):
            return False
        
        return (self.icmp_type == other.icmp_type and self.is_invert == other.is_invert)
    
    def __str__(self):
        if self.is_invert:
            return '! -p icmp -m icmp --icmp-type %s' % self.icmp_type
        else:
            return '-p icmp -m icmp --icmp-type %s' % self.icmp_type

class StateMatch(IPTableMatch):
    tag = 'state'
    
    def __init__(self):
        self.state = None
    
    @staticmethod
    def interpret(xmlobj):
        m = StateMatch()
        m.state = xmlobj.state.text_
        return m
    
    def __eq__(self, other):
        if not isinstance(other, StateMatch):
            return False
        return (self.state == other.state)
    
    def __str__(self):
        return '-m state --state %s' % self.state
        
def get_match(tagname):
    return _match_map.get(tagname)
    
_match_map = {}
def _build_match_map():
    global _match_map
    curr_module = sys.modules[__name__]
    for name, obj in inspect.getmembers(curr_module):
        if inspect.isclass(obj) and issubclass(obj, IPTableMatch):
            if not hasattr(obj, 'tag'):
                continue
            _match_map[obj.tag] = obj

if __name__ != '__main__':
    _build_match_map()
'''

@author: frank
'''
import sys
import inspect

class IPTableTarget(object):
    def __ne__(self, other):
        return not self.__eq__(other)
    
    @staticmethod
    def interpret(args):
        return None

class AcceptTarget(IPTableTarget):
    tag = 'ACCEPT'
    
    def __eq__(self, other):
        return isinstance(other, AcceptTarget)
    
    def __str__(self):
        return '-j ACCEPT'
    
    @staticmethod
    def interpret(xmlobj):
        return AcceptTarget()

class DropTarget(IPTableTarget):
    tag = 'DROP'
    
    def __eq__(self, other):
        return isinstance(other, DropTarget)
    
    def __str__(self):
        return '-j DROP'
    
    @staticmethod
    def interpret(xmlobj):
        return DropTarget()

class MasqueradeTarget(IPTableTarget): 
    tag = 'MASQUERADE'
    
    def  __init__(self):
        self.to_ports = None
        
    def get_start_port(self):
        if not self.to_ports:
            return None
        
        ports = self.to_ports.split('-')
        return ports[0]
    
    def get_end_port(self):
        if not self.to_ports:
            return None
        
        ports = self.to_ports.split('-')
        return ports[-1]
        
    def __eq__(self, other):
        if not isinstance(other, MasqueradeTarget):
            return False
        
        return self.to_ports == other.to_ports
    
    def __str__(self):
        s = ['-j MASQUERADE']
        if self.to_ports:
            s.append('--to-ports')
            s.append(self.to_ports)
        return ' '.join(s)
    
    @staticmethod
    def interpret(xmlobj):
        m = MasqueradeTarget()
        to_ports = xmlobj.get_child_node('to-ports')
        if to_ports:
            m.to_ports = to_ports.text_
        return m
                

class RejectTarget(IPTableTarget):
    tag = 'REJECT'
    
    ICMP_NET_UNREACHABLE = 'icmp-net-unreachable'
    ICMP_HOST_UNREACHABLE = 'icmp-host-unreachable'
    ICMP_PORT_UNREACHABLE = 'icmp-port-unreachable'
    ICMP_PROTO_UNREACHABLE = 'icmp-proto-unreachable'
    ICMP_NET_PROHIBITED = 'icmp-net-prohibited'
    ICMP_HOST_PROHIBITED = 'icmp-host-prohibited'
    TCP_RESET = 'tcp-reset'
    
    def __init__(self):
        self.reject_with = None
    
    def __eq__(self, other):
        if not isinstance(other, RejectTarget):
            return False
        
        return self.reject_with == other.reject_with
    
    def __str__(self):
        s = ['-j REJECT']
        if self.reject_with:
            s.append('--reject-with')
            s.append(self.reject_with)
        return ' '.join(s)
    
    @staticmethod
    def interpret(xmlobj):
        t = RejectTarget()
        rw = xmlobj.get_child_node('reject-with')
        if rw:
            t.reject_with = rw.text_
        return t

class ReturnTarget(IPTableTarget):
    tag = 'RETURN'
    
    def __eq__(self, other):
        return isinstance(other, ReturnTarget)
    
    def __str__(self):
        return '-j RETURN'
    
    @staticmethod
    def interpret(xmlobj):
        t = ReturnTarget()
        return t

class CheckSumTarget(IPTableTarget):
    tag = 'CHECKSUM'
    
    def __eq__(self, other):
        return isinstance(other, CheckSumTarget)
    
    def __str__(self):
        return '-j CHECKSUM --checksum-fill'
    
    @staticmethod
    def interpret(xmlobj):
        return CheckSumTarget()

class SnatTarget(IPTableTarget):
    tag = 'SNAT'
    
    def __init__(self):
        self.to_source = None
        
    def __eq__(self, other):
        if not isinstance(other, SnatTarget):
            return False
        
        return self.to_source == other.to_source
    
    @staticmethod
    def interpret(xmlobj):
        t = SnatTarget()
        ts = xmlobj.get_child_node('to-source')
        t.to_source = ts.text_
        return t
    
    def __str__(self):
        return '-j SNAT --to-source %s' % self.to_source
    
def get_target(tagname):
    return _targets_map.get(tagname)

_targets_map = {}
def _build_targets_map():
    curr_module = sys.modules[__name__]
    global _targets_map
    for name, obj in inspect.getmembers(curr_module):
        if inspect.isclass(obj) and issubclass(obj, IPTableTarget):
            if not hasattr(obj, 'tag'):
                continue
            _targets_map[obj.tag] = obj

if __name__ != '__main__':
    _build_targets_map()
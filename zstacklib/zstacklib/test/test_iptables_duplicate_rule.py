'''

@author: Frank
'''
import unittest
from zstacklib.iptables import iptables

class Test(unittest.TestCase):


    def testName(self):
        iptc = iptables.from_iptables_xml()
        rule = iptables.Rule()
        m = iptables.SourceMatch()
        m.source_ip = '10.0.0.1/255.255.255.0'
        rule.add_match(m)
        t = iptables.SnatTarget()
        t.to_source = '192.168.0.199'
        rule.set_target(t)
        iptc.nat_table_prerouting_chain_add_rule(rule)
        iptc.nat_table_prerouting_chain_add_rule(rule)
        iptc.nat_table_prerouting_chain_add_rule(rule)
        print str(iptc)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
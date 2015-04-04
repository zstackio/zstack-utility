'''

@author: Frank
'''
import unittest
from zstacklib.iptables import iptables


class Test(unittest.TestCase):


    def testName(self):
        iptc = iptables.from_iptables_xml()
        tbl = iptc.get_filter_table()
        c = iptables.Chain()
        c.name = 'testchain'
        r = iptables.Rule()
        m = iptables.TcpMatch()
        m.dport = 10
        m.sport = 1000
        r.add_match(m)
        t = iptables.AcceptTarget()
        r.set_target(t)
        c.add_rule(r)
        r = iptables.Rule()
        m = iptables.IcmpMatch()
        m.icmp_type = 8
        r.add_match(m)
        t = iptables.ReturnTarget()
        r.set_target(t)
        c.add_rule(r)
        tbl.add_chain(c)
        print tbl


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
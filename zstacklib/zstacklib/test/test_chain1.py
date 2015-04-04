'''

@author: Frank
'''
import unittest
from zstacklib.iptables import iptables


class Test(unittest.TestCase):


    def testName(self):
        iptc = iptables.from_iptables_xml()
        c = iptc.get_chain_in_filter_table(iptables.IPTables.CHAIN_INPUT)
        print c
        t = iptc.get_nat_table()
        print t
        print iptc.get_filter_table()


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
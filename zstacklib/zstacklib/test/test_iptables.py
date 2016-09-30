'''

@author: Frank
'''
import unittest
from zstacklib.iptables import iptables

class Test(unittest.TestCase):


    def testName(self):
        iptc = iptables.from_iptables_xml()
        print iptc.get_nat_table()
        print iptc.get_mangle_table()
        print iptc.get_nat_table()


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
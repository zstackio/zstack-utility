'''

@author: Frank
'''
import unittest
from zstacklib.utils import linux


class Test(unittest.TestCase):


    def testName(self):
        linux.create_vlan_bridge('br_eth0.99', 'eth0', 99, '10.5.5.5', '255.255.255.0')


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
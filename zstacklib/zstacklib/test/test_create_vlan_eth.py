'''

@author: Frank
'''
import unittest
from zstacklib.utils import linux


class Test(unittest.TestCase):


    def testName(self):
        linux.create_vlan_eth('eth0', 11, '10.1.1.1', '255.255.255.0')
        linux.create_vlan_eth('eth0', 100, '10.3.3.3', '255.255.255.0')


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
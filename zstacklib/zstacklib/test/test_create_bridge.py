'''

@author: Frank
'''
import unittest
from zstacklib.utils import linux
from zstacklib.utils import shell

class Test(unittest.TestCase):


    def testName(self):
        linux.create_bridge('testbr0', 'ens3')

    def test_bridge_setup_with_stp_on(self):
        bridge_name = 'testbr0'
        shell.call("brctl stp %s on" % bridge_name)

        o = shell.call("brctl show %s | grep yes | awk '{ print $3 }'" % bridge_name).strip('\n')
        self.assertEqual(o, 'yes')

        # create bridge will not fail with stp on
        linux.create_bridge(bridge_name, 'ens3')

        o = shell.call("brctl show %s | grep no | awk '{ print $3 }'" % bridge_name).strip('\n')
        self.assertEqual(o, 'no')


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
'''

@author: frank
'''
import unittest
from zstacklib.utils import linux

class Test(unittest.TestCase):


    def callback(self, percentage, userdata):
        print percentage
        
    def testName(self):
        ret = linux.wget("http://192.168.0.199/volumes/ubuntu1204.qcow2", "/tmp", rename="10G.qcow2", callback=self.callback)
        print "ret: %s" % ret


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
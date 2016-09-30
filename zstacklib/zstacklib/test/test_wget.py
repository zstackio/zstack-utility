'''

@author: frank
'''
import unittest
from zstacklib.utils import linux

class Test(unittest.TestCase):


    def callback(self, percentage, userdata):
        print percentage
        
    def testName(self):
        ret = linux.wget("http://yum.puppetlabs.com/el/6/products/i386/puppetlabs-release-6-6.noarch.rpm", "/tmp", callback=self.callback)
        print "ret: %s" % ret


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
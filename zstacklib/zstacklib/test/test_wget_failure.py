'''

@author: frank
'''
import unittest
from zstacklib.utils import linux

class Test(unittest.TestCase):


    def callback(self, percentage, userdata):
        print(percentage)
        
    @unittest.expectedFailure
    def testName(self):
        ret = linux.wget("http://nothing", "/tmp", callback=self.callback)
        print("ret: %s" % ret)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
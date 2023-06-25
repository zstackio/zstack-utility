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
        linux.wget("http://192.168.200.100/mirror/diskimages/centos79.raw", "/tmp", timeout=5, callback=self.callback)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
'''

@author: frank
'''
import unittest
from zstacklib.utils import linux

class Test(unittest.TestCase):


    def callback(self, percentage, userdata):
        print percentage
        
    def testName(self):
        linux.wget("http://linux.mirrors.es.net/centos/5.8/isos/i386/CentOS-5.8-i386-bin-3of7.iso", "/tmp", timeout=5, callback=self.callback)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
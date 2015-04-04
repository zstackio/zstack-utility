'''

@author: Frank
'''
import unittest
from zstacklib.utils import linux
import os.path

class Test(unittest.TestCase):


    def callback(self, percentage, data):
        print percentage
        
    def testName(self):
        rsa_path = os.path.expanduser("~/.ssh/id_rsa")
        fd = open(rsa_path, 'r')
        rsa = fd.read()
        fd.close()
        linux.sftp_get("root@localhost", rsa, "/home/root/test500M.img", "/tmp/test.img", timeout=300, interval=5, callback=self.callback, callback_data=None)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
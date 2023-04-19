'''

@author: Frank
'''
import unittest
from zstacklib.utils import linux
import os.path

class Test(unittest.TestCase):


    def callback(self, percentage, data):
        print(percentage)


    @unittest.expectedFailure
    def testName(self):
        rsa_path = os.path.expanduser("~/.ssh/id_rsa")
        fd = open(rsa_path, 'r')
        rsa = fd.read()
        fd.close()

        f = open("./sftp_get_test", "a")
        f.write("Now the file has more content!")
        f.close()

        linux.sftp_get("root@localhost", rsa, "./sftp_get_test", "/tmp/sftp_get_test", timeout=300, interval=5, callback=self.callback, callback_data=None)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
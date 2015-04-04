'''

@author: frank
'''
import unittest
import time
from sftpbackupstorage import sftpbackupstorage
from zstacklib.utils import http
from zstacklib.utils import jsonobject

class Test(unittest.TestCase):
    def testName(self):
        server = sftpbackupstorage.SftpBackupStorageAgent()
        server.http_server.start_in_thread()
        time.sleep(2)
        
        cmd = sftpbackupstorage.ConnectCmd()
        cmd.storagePath = "/tmp"
        #url = sftpbackupstorage._build_url_for_test([sftpbackupstorage.SftpBackupStorageAgent.CONNECT_PATH])
        url = 'http://localhost:7171%s' % sftpbackupstorage.SftpBackupStorageAgent.CONNECT_PATH
        print url
        rsp = http.json_dump_post(url, cmd)
        jrsp = jsonobject.loads(rsp)
        print "total: %s, used: %s" % (jrsp.totalBackupStorageSize, jrsp.usedBackupStorageSize)
        
        server.http_server.stop()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
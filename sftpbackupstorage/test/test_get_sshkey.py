'''

@author: Frank
'''
import unittest
import time
from sftpbackupstorage import sftpbackupstorage
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import uuidhelper

class Test(unittest.TestCase):
    CALLBACK_URL = 'http://localhost:%s/testcallback' % sftpbackupstorage.SftpBackupStorageAgent.PORT
    
    def callback(self, req):
        rsp = jsonobject.loads(req[http.REQUEST_BODY])
        print "sshkey: %s" % rsp.sshKey
        

    def testName(self):
        server = sftpbackupstorage.SftpBackupStorageAgent()
        server.http_server.register_sync_uri('/testcallback', self.callback)
        server.http_server.start_in_thread()
        time.sleep(2)
        
        cmd = sftpbackupstorage.GetSshKeyCommand()
        url = 'http://localhost:7171%s' % sftpbackupstorage.SftpBackupStorageAgent.GET_SSHKEY_PATH
        print url
        rsp = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        print "post back"
        time.sleep(5)
        
        server.http_server.stop()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
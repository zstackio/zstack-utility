'''

@author: frank
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
        print "install_url: %s" % rsp.installUrl
        
    def testName(self):
        server = sftpbackupstorage.SftpBackupStorageAgent()
        server.http_server.register_sync_uri('/testcallback', self.callback)
        
        server.http_server.start_in_thread()
        time.sleep(2)
        cmd = sftpbackupstorage.ConnectCmd()
        cmd.storagePath = "/tmp"
        #url = sftpbackupstorage._build_url_for_test([sftpbackupstorage.SftpBackupStorageAgent.CONNECT_PATH])
        url = 'http://localhost:7171%s' % sftpbackupstorage.SftpBackupStorageAgent.CONNECT_PATH
        print url
        rsp = http.json_dump_post(url, cmd)
        
        cmd = sftpbackupstorage.DownloadCmd()
        cmd.accountUuid = uuidhelper.uuid()
        cmd.bits = 64
        cmd.description = "Test"
        cmd.format = sftpbackupstorage.SftpBackupStorageAgent.IMAGE_TEMPLATE
        cmd.guestOsType = "rpm"
        cmd.hypervisorType = "KVM"
        cmd.imageUuid = uuidhelper.uuid()
        cmd.name = "test"
        cmd.timeout = 60
        cmd.url = "http://yum.puppetlabs.com/el/6/products/i386/puppetlabs-release-6-6.noarch.rpm"
        cmd.urlScheme = "http"
        url = 'http://localhost:7171%s' % sftpbackupstorage.SftpBackupStorageAgent.DOWNLOAD_IMAGE_PATH
        print url
        rsp = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        print "post back"
        time.sleep(20)
        
        server.http_server.stop()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
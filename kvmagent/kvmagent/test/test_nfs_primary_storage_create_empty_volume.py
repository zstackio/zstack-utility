'''

@author: Frank
'''
import unittest
import time
import os.path
from kvmagent import kvmagent
from kvmagent.plugins import nfs_primarystorage_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper
from zstacklib.utils import linux

logger = log.get_logger(__name__)

class Test(unittest.TestCase):
    NFS_URL = 'localhost:/home/primary'
    CALLBACK_URL = 'http://localhost:7070/testcallback'
    
    def callback(self, req):
        rsp = jsonobject.loads(req[http.REQUEST_BODY])
        print jsonobject.dumps(rsp, True)
        
    def setUp(self):
        self.service = kvmagent.new_rest_service()
        kvmagent.get_http_server().register_sync_uri('/testcallback', self.callback)
        self.service.start(True)
        time.sleep(1)
        
    def mount(self):
        cmd = nfs_primarystorage_plugin.MountCmd()
        cmd.url = self.NFS_URL
        cmd.mountPath = os.path.join('/mnt', uuidhelper.uuid())
        callurl = kvmagent._build_url_for_test([nfs_primarystorage_plugin.MOUNT_PATH])
        ret = http.json_dump_post(callurl, cmd)
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success, rsp.error)
        self.assertTrue(linux.is_mounted(cmd.url, cmd.mountPath))
        
    def testName(self):
        self.mount()
        cmd = nfs_primarystorage_plugin.CreateEmptyVolumeCmd()
        cmd.accountUuid = uuidhelper.uuid()
        cmd.hypervisorType = 'KVM'
        cmd.installUrl = '/tmp/emptyvolume.qcow2'
        cmd.name = 'testEmptyVolume'
        cmd.size = '1410400256'
        cmd.uuid = uuidhelper.uuid()
        url = kvmagent._build_url_for_test([nfs_primarystorage_plugin.CREATE_EMPTY_VOLUME_PATH])
        rsp = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(5)
        self.service.stop()
        linux.umount_by_url(self.NFS_URL)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
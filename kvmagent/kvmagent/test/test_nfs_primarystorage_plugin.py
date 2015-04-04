'''

@author: frank
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

NFS_URL = 'localhost:/primarystorage'

class TestNfsPrimaryStoragePlugin(unittest.TestCase):

    @classmethod
    def _unmount_all(self):
        linux.umount_by_url(NFS_URL)
        
    @classmethod
    def setUpClass(self):
        self.service = kvmagent.new_rest_service()
        self.service.start()
        time.sleep(1)
        self._unmount_all()

    @classmethod
    def tearDownClass(self):
        self.service.stop()
        
    def test_mount(self):
        cmd = nfs_primarystorage_plugin.MountCmd()
        cmd.url = NFS_URL
        cmd.mountPath = os.path.join('/mnt', uuidhelper.uuid())
        callurl = kvmagent._build_url_for_test([nfs_primarystorage_plugin.MOUNT_PATH])
        ret = http.json_dump_post(callurl, cmd)
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success, rsp.error)
        self.assertTrue(linux.is_mounted(cmd.url, cmd.mountPath))
        return cmd.mountPath

    def test_unmount(self):
        mountPath = self.test_mount()
        cmd = nfs_primarystorage_plugin.UnmountCmd()
        cmd.url = NFS_URL
        cmd.mountPath = mountPath
        callurl = kvmagent._build_url_for_test([nfs_primarystorage_plugin.UNMOUNT_PATH])
        ret = http.json_dump_post(callurl, cmd)
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success, rsp.error)
        self.assertFalse(linux.is_mounted(path=cmd.mountPath))

    def test_mount_failure(self):
        cmd = nfs_primarystorage_plugin.MountCmd()
        cmd.url = 'this_is_a_wrong_path'
        cmd.mountPath = os.path.join('/mnt', uuidhelper.uuid())
        callurl = kvmagent._build_url_for_test([nfs_primarystorage_plugin.MOUNT_PATH])
        ret = http.json_dump_post(callurl, cmd)
        rsp = jsonobject.loads(ret)
        self.assertFalse(rsp.success, rsp.error)
        
    def test_unmount_always_success(self):
        cmd = nfs_primarystorage_plugin.UnmountCmd()
        cmd.url = NFS_URL
        cmd.mountPath = '/not_mounted_path'
        callurl = kvmagent._build_url_for_test([nfs_primarystorage_plugin.UNMOUNT_PATH])
        ret = http.json_dump_post(callurl, cmd)
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success, rsp.error)
        self.assertFalse(linux.is_mounted(path=cmd.mountPath))
                         
if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
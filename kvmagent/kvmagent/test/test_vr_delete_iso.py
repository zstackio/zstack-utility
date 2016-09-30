'''

@author: Frank
'''
import unittest
import time
from kvmagent import kvmagent
from kvmagent.plugins import virtualrouter_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper

class Test(unittest.TestCase):
    CALLBACK_URL = 'http://localhost:7070/testcallback'
    
    def setUp(self):
        self.service = kvmagent.new_rest_service()
        self.service.http_server.register_sync_uri('/testcallback', self.callback)
        self.service.start()
        time.sleep(1)

    def callback(self, req):
        rsp = jsonobject.loads(req[http.REQUEST_BODY])
        print jsonobject.dumps(rsp)
        
    def testName(self):
        url = kvmagent._build_url_for_test([virtualrouter_plugin.VirtualRouterPlugin.VR_KVM_CREATE_BOOTSTRAP_ISO_PATH])
        info = virtualrouter_plugin.BootstrapIsoInfo()
        info.managementNicGateway = "192.168.1.1"
        info.managementNicIp = "192.168.1.10"
        info.managementNicMac = "50:E5:49:C9:65:A3"
        info.managementNicNetmask = "255.255.255.0"
        cmd = virtualrouter_plugin.CreateVritualRouterBootstrapIsoCmd()
        cmd.isoInfo = info
        cmd.isoPath = '/tmp/vr.iso'
        rsp = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(2)
        cmd = virtualrouter_plugin.DeleteVirtualRouterBootstrapIsoCmd()
        cmd.isoPath = '/tmp/vr.iso'
        url = kvmagent._build_url_for_test([virtualrouter_plugin.VirtualRouterPlugin.VR_KVM_DELETE_BOOTSTRAP_ISO_PATH])
        rsp = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(2)
        self.service.stop()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
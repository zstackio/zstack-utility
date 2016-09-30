'''

@author: Frank
'''
import unittest
from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper
from zstacklib.utils import linux
import time

class Test(unittest.TestCase):
    
    CALLBACK_URL = 'http://localhost:7070/testcallback'
    
    def callback(self, req):
        rsp = jsonobject.loads(req[http.REQUEST_BODY])
        print jsonobject.dumps(rsp)
        
    def setUp(self):
        self.service = kvmagent.new_rest_service()
        kvmagent.get_http_server().register_sync_uri('/testcallback', self.callback)
        self.service.start(True)
        time.sleep(1)

    def testName(self):
        cmd = vm_plugin.StartVmCmd()
        cmd.vmName = 'test'
        cmd.vmUuid = uuidhelper.uuid()
        cmd.cpuNum = 2
        cmd.cpuSpeed = 3000
        cmd.memory = 3221225472
        cmd.rootVolumePath = '/home/root/images/volumes/kvmubuntu.img'
        cmd.bootDev = 'hd'
        cmd.timeout = 30
        nic = vm_plugin.NicTO()
        nic.mac = 'fa:33:f8:5f:00:00'
        nic.bridgeName = 'virbr0'
        nic.deviceId = 0
        cmd.nics.append(nic)
        print 'xxxxxxxxxxxxxxxxxxx %s' % cmd.vmUuid
        url = kvmagent._build_url_for_test([vm_plugin.KVM_START_VM_PATH])
        rsp = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(30)
        self.service.stop()


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
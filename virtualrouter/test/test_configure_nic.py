'''

@author: Frank
'''
import unittest

from virtualrouter import virtualrouter
from virtualrouter.plugins import configure_nic
from zstacklib.utils import jsonobject
from zstacklib.utils import uuidhelper
from zstacklib.utils import http
import time

class NicInfo(object):
    def __init__(self):
        self.ip = None
        self.mac = None
        self.gateway = None
        self.netmask = None
        self.isDefaultRoute = None
        
class Test(unittest.TestCase):
    CALLBACK_URL = 'http://localhost:7272/testcallback'
    
    def setUp(self):
        self.service = virtualrouter.VirtualRouter()
        self.service.http_server.register_sync_uri('/testcallback', self.callback)
        self.service.start()
        time.sleep(1)

    def callback(self, req):
        rsp = jsonobject.loads(req[http.REQUEST_BODY])
        print jsonobject.dumps(rsp)
        

    def testName(self):
        cmd = configure_nic.ConfigureNicCmd()
        nic = NicInfo()
        nic.ip = "10.0.0.10"
        nic.mac = "50:e5:49:c9:65:a3"
        nic.gateway = "10.0.0.1"
        nic.netmask = "255.255.255.0"
        nic.isDefaultRoute = False
        cmd.nics = [nic]
        
        rsp = http.json_dump_post('http://localhost:7272/configurenic', cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(10)
        self.service.stop()
        

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
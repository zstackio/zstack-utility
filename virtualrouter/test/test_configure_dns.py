'''

@author: Frank
'''
import unittest

from virtualrouter import virtualrouter
from virtualrouter.plugins import dns
from zstacklib.utils import jsonobject
from zstacklib.utils import uuidhelper
from zstacklib.utils import http
import time

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
        cmd = dns.SetDnsCmd()
        
        info = dns.DnsInfo()
        info.dnsAddress = '72.72.72.72'
        cmd.dns = [info]
        
        rsp = http.json_dump_post('http://localhost:7272/setdns', cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(10)
        self.service.stop()
        

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
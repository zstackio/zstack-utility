'''

@author: Frank
'''
import unittest

from virtualrouter import virtualrouter
from virtualrouter.plugins import dnsmasq
from zstacklib.utils import jsonobject
from zstacklib.utils import uuidhelper
from zstacklib.utils import http
import time

class DhcpInfo(object):
    def __init__(self):
        self.ip = None
        self.mac = None
        self.gateway = None
        self.netmask = None
        self.hostname = None
        self.dns = None
        
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
        cmd = dnsmasq.AddDhcpEntryCmd()
        
        nic = DhcpInfo()
        nic.ip = "10.0.0.10"
        nic.mac = "50:e5:49:c9:65:a3"
        nic.gateway = "10.0.0.1"
        nic.netmask = "255.255.255.0"
        nic.hostname = 'host1'
        nic.dns = ['8.8.8.8', '75.75.75.75']
        
        nic1 = DhcpInfo()
        nic1.ip = "10.0.0.13"
        nic1.mac = "50:e5:49:c9:65:b0"
        nic1.netmask = "255.255.255.0"
        nic1.hostname = 'host2'
        nic1.dns = ['8.8.8.8', '75.75.75.75']
        
        nic2 = DhcpInfo()
        nic2.ip = "10.0.0.12"
        nic2.mac = "50:e5:49:c9:65:b1"
        nic2.netmask = "255.255.255.0"
        nic2.hostname = 'host3'
        
        cmd.dhcpEntries = [nic, nic1, nic2]
        cmd.rebuild = True
        
        rsp = http.json_dump_post('http://localhost:7272/adddhcp', cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(10)
        self.service.stop()
        

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
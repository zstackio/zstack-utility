'''

@author: frank
'''
import unittest
import time
from kvmagent import kvmagent
from kvmagent.plugins import network_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper


logger = log.get_logger(__name__)

class TestNetworkPlugin(unittest.TestCase):
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
        url = kvmagent._build_url_for_test([network_plugin.KVM_REALIZE_L2NOVLAN_NETWORK_PATH])
        logger.debug('calling %s' % url)
        cmd = network_plugin.CreateBridgeCmd()
        cmd.physicalInterfaceName = 'eth0'
        cmd.bridgeName = 'br_eth0'
        rsp = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(2)
        self.service.stop()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
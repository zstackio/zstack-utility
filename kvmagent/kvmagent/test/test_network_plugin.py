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


logger = log.get_logger(__name__)

class TestNetworkPlugin(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.service = kvmagent.new_rest_service()
        self.service.start()
        time.sleep(1)

    @classmethod
    def tearDownClass(self):
        self.service.stop()


    def test_check_physical_network_interface(self):
        url = kvmagent._build_url_for_test([network_plugin.CHECK_PHYSICAL_NETWORK_INTERFACE_PATH])
        logger.debug('calling %s' % url)
        cmd = network_plugin.CheckPhysicalNetworkInterfaceCmd()
        cmd.interfaceNames = ['p5p1']
        ret = http.json_dump_post(url, body=cmd)
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success)
        
    def test_check_physical_network_interface_failure(self):
        url = kvmagent._build_url_for_test([network_plugin.CHECK_PHYSICAL_NETWORK_INTERFACE_PATH])
        logger.debug('calling %s' % url)
        cmd = network_plugin.CheckPhysicalNetworkInterfaceCmd()
        cmd.interfaceNames = ['p5p1', 'abcd']
        ret = http.json_dump_post(url, body=cmd)
        rsp = jsonobject.loads(ret)
        self.assertFalse(rsp.success)
        self.assertTrue('abcd' in rsp.failedInterfaceNames)

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
'''

@author: frank
'''
import unittest
import time
from kvmagent import kvmagent
from kvmagent.plugins import host_plugin
from zstacklib.utils import http
from zstacklib.utils import uuidhelper
from zstacklib.utils import jsonobject
from zstacklib.utils import log


logger = log.get_logger(__name__)

class ConnectCmd(kvmagent.AgentCommand):
    def __init__(self):
        self.hostUuid = uuidhelper.uuid()
        
class HostFactCmd(kvmagent.AgentCommand): pass


        
class TestHostPlugin(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.service = kvmagent.new_rest_service()
        self.service.start()
        time.sleep(1)

    @classmethod
    def tearDownClass(self):
        self.service.stop()


    def test_connect(self):
        url = kvmagent._build_url_for_test([host_plugin.CONNECT_PATH])
        logger.debug('calling %s' % url)
        ret = http.json_dump_post(url, body=ConnectCmd())
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success)
        
    def test_hostfact(self):
        url = kvmagent._build_url_for_test([host_plugin.HOSTFACT_PATH])
        cmd = HostFactCmd()
        ret = http.json_dump_post(url, body=cmd)
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success)
        self.assertEqual(host_plugin._get_cpu_num(), rsp.cpuNum)
        self.assertEqual(host_plugin._get_cpu_speed(), rsp.cpuSpeed)
        self.assertEqual(host_plugin._get_total_memory(), rsp.totalMemory)

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
'''

@author: frank
'''
import unittest
import time
import urllib2
from zstacklib.utils import http
import simplejson


class TestHttpServer(object):
    def return_same(self, arg):
        return simplejson.loads(arg[http.REQUEST_BODY])['value']
        
    def say_hello(self, req):
        return "hello"
        
class Test(unittest.TestCase):
    
    @classmethod
    def setUpClass(self):
        self.server = http.HttpServer() 
        self.test = TestHttpServer()
        self.server.register_sync_uri("/sayhello/hi/", self.test.say_hello)
        self.server.register_sync_uri("/returnsame/", self.test.return_same)
        self.server.start_in_thread()
        time.sleep(2)

    @classmethod
    def tearDownClass(self):
        self.server.stop()

    def test_sync_uri(self):
        req = urllib2.Request("http://localhost:7070/sayhello/hi")
        f = urllib2.urlopen(req)
        rsp = f.read()
        f.close()
        self.assertEqual("hello", rsp)
    
    def test_sync_uri2(self):
        data = {"value":"hello"}
        rsp = http.json_dump_post("http://localhost:7070/returnsame/", data)
        self.assertEqual("hello", rsp)

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
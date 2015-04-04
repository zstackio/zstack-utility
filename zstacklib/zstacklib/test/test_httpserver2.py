'''

@author: frank
'''
import unittest
import time
import uuid
import urllib2
import cherrypy
import logging
import simplejson
from ..utils import http, uuidhelper


BASE_URL = 'http://localhost:7070'

logger = logging.getLogger(__name__)

class AsyncHttpServer(object):
    result = {}
    
    def say_hello(self, req):
        time.sleep(1)
        return simplejson.dumps({'value': 'hello'})
    
    def callback(self, arg):
        headers = arg[http.REQUEST_HEADER]
        task_uuid = headers[http.TASK_UUID]
        if headers.has_key(http.ERROR_CODE):
            print "error:\n%s" % arg[http.REQUEST_BODY]
            return
        
        d = simplejson.loads(arg[http.REQUEST_BODY])
        if self.result[task_uuid] != d['value']:
            raise Exception('expected: %s but got: %s, taskUuid:' % (self.result[task_uuid], d['value'], task_uuid))
    
    def return_same(self, arg):
        return arg[http.REQUEST_BODY]
    
    def return_exception(self, req):
        raise Exception("indeed")
    
    def call(self, path, value):
        uri = '%s/%s' % (BASE_URL, path)
        task_uuid = uuidhelper.UUID.uuid()
        self.result[task_uuid] = value
        http.json_post(uri, headers={http.TASK_UUID:task_uuid})
    
    def call_with_data(self, path, data):
        uri = '%s/%s' % (BASE_URL, path)
        task_uuid = uuidhelper.UUID.uuid()
        self.result[task_uuid] = data
        http.json_post(uri, body=simplejson.dumps({'value':data}), headers={http.TASK_UUID:task_uuid})
    
class TestAsyncHttpServer(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        self.server = http.HttpServer("%s/callback" % BASE_URL)
        self.test = AsyncHttpServer()
        self.server.register_async_uri('/sayhello', self.test.say_hello)
        self.server.register_async_uri('/returnsame', self.test.return_same)
        self.server.register_async_uri('/returnexecption', self.test.return_exception)
        self.server.register_sync_uri('/callback', self.test.callback)
        self.server.start_in_thread()
        time.sleep(2)


    @classmethod
    def tearDownClass(self):
        self.server.stop()


    def test_1(self):
        self.test.call('/sayhello', 'hello')
        time.sleep(2)
        pass
        
    def test_2(self):
        self.test.call_with_data('/returnsame', 'world')
        time.sleep(2)
        
    def test_3(self):
        self.test.call('/returnexecption', 'hello')
        time.sleep(2)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
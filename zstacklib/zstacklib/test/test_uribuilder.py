'''

@author: frank
'''
import unittest
from zstacklib.utils import http

class TestUriBuilder(unittest.TestCase):


    def test_build_url(self):
        url = 'http://localhost:7070/'
        builder = http.UriBuilder(url)
        builder.add_path('/connect')
        builder.add_path('/vm')
        ret = builder.build()
        self.assertEqual('http://localhost:7070/connect/vm/', ret)
        
    def test_build_url2(self):
        ret = http.build_url(('http', 'google.com', '8080', 'search'))
        self.assertEqual('http://google.com:8080/search/', ret)
        
    def test_build_url3(self):
        ret = http.build_url(('http', 'google.com', '8080', '/search/world/'))
        self.assertEqual('http://google.com:8080/search/world/', ret)
        
    def test_build_url4(self):
        url = 'http://localhost/'
        builder = http.UriBuilder(url)
        builder.add_path('/connect')
        builder.add_path('/vm')
        ret = builder.build()
        self.assertEqual('http://localhost:80/connect/vm/', ret)

    def test_build_url5(self):
        url = 'http://localhost/'
        builder = http.UriBuilder(url)
        ret = builder.build()
        self.assertEqual('http://localhost:80/', ret)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
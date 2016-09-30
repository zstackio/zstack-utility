'''

@author: frank
'''
import unittest
import os.path
from apibinding import api


class TestLogin(unittest.TestCase):


    def test_login(self):
        binding = api.Api(os.path.abspath('test/jsontemplates'))
        session = binding.login_as_admin()
        print session

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
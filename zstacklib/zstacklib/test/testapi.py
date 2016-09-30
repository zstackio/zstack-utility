'''

@author: frank
'''
import unittest
from zstacklib.utils import jsonobject


class Test(unittest.TestCase):


    def test_api(self):
        jstr  ='''\
{"org.zstack.header.identity.APILogInEvent": {
  "errorCode": {
    "code": "java.lang.String",
    "description": "java.lang.String",
    "details": "java.lang.String"
  },
  "inventory": {"uuid": "java.lang.String"},
  "isSuccess": "boolean"
}}\
'''
        jobj = jsonobject.loads(jstr)
        print jobj.__dict__
        key = jobj.__dict__.keys()[0]
        print key

if __name__ == "__main__":
    unittest.main()
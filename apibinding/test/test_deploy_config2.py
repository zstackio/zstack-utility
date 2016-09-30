'''

@author: Frank
'''
import unittest
from apibinding import deployer
from zstacklib.utils import jsonobject
import os.path

class Test(unittest.TestCase):


    def testName(self):
        deployer.deploy_from_template("test/TestCreateVm2.xml", "test/TestCreateVm2Tmpt.ini")
            

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
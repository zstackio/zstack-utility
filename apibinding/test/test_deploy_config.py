'''

@author: Frank
'''
import unittest
from apibinding.deployer import deployer
from zstacklib.utils import jsonobject
import os.path

class Test(unittest.TestCase):


    def testName(self):
        p = os.path.abspath('test/TestNewDeployer.xml')
        deployer.deploy(p)
            

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
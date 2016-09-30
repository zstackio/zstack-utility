'''

@author: frank
'''
import unittest
from buildsystem import zstackbuild

class Test(unittest.TestCase):

    def testName(self):
        build = zstackbuild.Build('test/zstack-build.cfg')
        build.main()


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
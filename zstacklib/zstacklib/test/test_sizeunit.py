'''

@author: frank
'''
import unittest
from zstacklib.utils import sizeunit

class TestSizeUnit(unittest.TestCase):


    def test_sizeunit(self):
        self.assertEqual(1024*1024*8, sizeunit.MegaByte.toByte(8))
        self.assertEqual(1024*1024*1024*8, sizeunit.GigaByte.toByte(8))
        self.assertEqual(1024*1024*1024*1024*8, sizeunit.TeraByte.toByte(8))
        self.assertEqual(sizeunit.TeraByte.toByte(8), 1024*1024*1024*1024*8)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
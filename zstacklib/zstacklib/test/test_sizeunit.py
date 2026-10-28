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

    def test_conversions_return_int_not_float(self):
        # 8388608.0 == 8388608 为真，值断言无法发现 int->float 漂移，必须断言类型
        self.assertIsInstance(sizeunit.MegaByte.toByte(8), int)
        self.assertIsInstance(sizeunit.GigaByte.toByte(8), int)
        self.assertIsInstance(sizeunit.TeraByte.toByte(8), int)
        self.assertIsInstance(sizeunit.Byte.toMegaByte(1024*1024*8), int)
        self.assertIsInstance(sizeunit.KiloByte.toByte(8), int)
        self.assertIsInstance(sizeunit.MegaByte.toGigaByte(1024*1024*8), int)
        self.assertIsInstance(sizeunit.Byte.toKiloByte(2048), int)
        self.assertIsInstance(sizeunit.KiloByte.toMegaByte(2048), int)
        self.assertIsInstance(sizeunit.GigaByte.toTeraByte(2048), int)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
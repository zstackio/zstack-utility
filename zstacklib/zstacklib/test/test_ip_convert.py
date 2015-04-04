'''

@author: Frank
'''
from zstacklib.utils import linux
import unittest

class Test(unittest.TestCase):

    def testName(self):
        ip = '255.255.0.0'
        ipi1 = linux.ip_string_to_int(ip)
        print ipi1
        ips = linux.int_to_ip_string(ipi1)
        print ips
        
        ip = '10.1.23.12'
        ipi2 = linux.ip_string_to_int(ip)
        print ipi2
        ips = linux.int_to_ip_string(ipi2)
        print ips
        
        nip = linux.int_to_ip_string(ipi1 & ipi2)
        print nip

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()

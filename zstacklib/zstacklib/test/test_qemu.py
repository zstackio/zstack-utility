'''

@author: Frank
'''
import unittest
from zstacklib.utils import qemu

excepts = {
    '''QEMU emulator version 4.2.0 (qemu-kvm-4.2.0-627.g36ee592.el7)
Copyright (c) 2003-2019 Fabrice Bellard and the QEMU Project developers
''': "4.2.0-627.g36ee592.el7",

    '''QEMU emulator version 2.9.0(qemu-kvm-ev-2.9.0-16.el7_4.11.1)
Copyright (c) 2003-2017 Fabrice Bellard and the QEMU Project developers
''': "2.9.0-16.el7_4.11.1",

    '''qemu-img version 2.6.0 (qemu-kvm-ev-2.6.0-27.1.el7.centos), Copyright (c) 2004-2008 Fabrice Bellard
''': "2.6.0-27.1.el7.centos",

    '''qemu-img version 4.2.0 (qemu-kvm-4.2.0-627.g36ee592.el7)
Copyright (c) 2003-2019 Fabrice Bellard and the QEMU Project developers
''': "4.2.0-627.g36ee592.el7",

    '''qemu-kvm-4.2.0-627.g36ee592.el7
Copyright (c) 2003-2019 Fabrice Bellard and the QEMU Project developers
''': "4.2.0-627.g36ee592.el7",

    "qemu-kvm-4.2.0-627.g36ee592.el7": "4.2.0-627.g36ee592.el7"
}

class Test(unittest.TestCase):

    def testVersion(self):
        for k, v in excepts.items():
            ret = qemu._parse_version(k)
            assert ret == v, "unexcepts result: %s : %s" % (k, ret)

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
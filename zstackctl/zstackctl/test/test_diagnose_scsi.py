#!/usr/bin/env python
# encoding: utf-8

import os
import sys
import unittest
from datetime import datetime
from argparse import ArgumentParser

curr_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.append(os.path.dirname(os.path.dirname(curr_dir)))

class TestError(Exception):
    pass

try:
    import termcolor
except ImportError:
    raise TestError("termcolor module is needed, please install termcolor first(pip install termcolor).")


from zstackctl.trait_parser import *



class DiagnoseTest(unittest.TestCase):

    def setUp(self):
        super(DiagnoseTest, self).setUp()
        time_stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        self.diagnose_log_file = 'scsi-diagnose-test-%s' % time_stamp

    def test_diagnose_scsi(self):
        log_dir = os.path.join(curr_dir, 'resources', 'scsi-diagnose')
        parser = ArgumentParser('test')
        parser.add_argument('--since', default=None)
        parser.add_argument('--daytime', default=5)
        args = parser.parse_args()
        os.environ['DIAGNOSETEST'] = 'true'

        diagnose(log_dir, self.diagnose_log_file, args)
        compare_file_path = os.path.join(curr_dir, 'resources', 'scsi-diagnose', 'scsi-diagnose-log')
        with open(compare_file_path, 'r') as f:
            target = f.readlines()

        with open(self.diagnose_log_file, 'r') as f:
            test_out = f.readlines()

        self.assertEqual(test_out, target)

    def tearDown(self):
        super(DiagnoseTest, self).tearDown()
        os.remove(self.diagnose_log_file)


if __name__ == "__main__":
    unittest.main()

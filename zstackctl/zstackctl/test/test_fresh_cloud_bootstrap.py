import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) )
from zstackctl.fresh_cloud_bootstrap import validate_fresh_cloud_bootstrap


class FreshCloudBootstrapTest(unittest.TestCase):
    def test_only_verified_absent_database_is_accepted(self):
        self.assertTrue(validate_fresh_cloud_bootstrap(False, False, True, False))

    def test_existing_database_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_fresh_cloud_bootstrap(False, False, True, True)

    def test_unverifiable_database_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_fresh_cloud_bootstrap(False, False, False, False)

    def test_drop_and_keep_modes_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_fresh_cloud_bootstrap(True, False, True, False)
        with self.assertRaises(ValueError):
            validate_fresh_cloud_bootstrap(False, True, True, False)


if __name__ == "__main__":
    unittest.main()

from kvmagent.test.utils import pytest_utils
from zstacklib.test.utils import env
from zstacklib.utils import bash
from unittest import TestCase

import os

PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {
    }
}

class TestZStacklibUnittest(TestCase):
    @classmethod
    def setUpClass(cls):
        return

    @pytest_utils.ztest_decorater
    @bash.in_bash
    def test_zstacklib_with_unittest(self):
        r, o, e = bash.bash_roe("cd %s; python -m unittest discover -s %s" % (os.path.join(env.ZSTACK_UTILITY_SOURCE_DIR, 'zstacklib/'), os.path.join(env.ZSTACK_UTILITY_SOURCE_DIR, 'zstacklib/zstacklib/test/')))
        if r == 0:
            return

        self.assertEqual(r, 0, 'zstacklib unittest failed: %s' % (e))

from kvmagent.test.utils import localstorage_utils,pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote,misc
from zstacklib.utils import linux, jsonobject, bash
from unittest import TestCase
import os
localstorage_utils.init_localstorage_plugin()

PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {}
}


## describe: case will manage by ztest
class TestLocalStoragePlugin(TestCase):

    @classmethod
    def setUpClass(cls):
        return
    @pytest_utils.ztest_decorater
    def test_localstorage_init(self):
        rsp = localstorage_utils.localstorage_init(
            "/local_ps"
        )
        self.assertGreater(rsp.totalCapacity, 0, rsp.error)
        self.assertGreater(rsp.availableCapacity, 0, rsp.error)
        self.assertEqual(rsp.localStorageUsedCapacity, 0, rsp.error)

        rsp = localstorage_utils.create_folder(
            installUrl = "/local_ps/test/test/xxxxx.qcow2",
            storagePath = "/local_ps"
        )

        dirname = os.path.dirname("/local_ps/test/test/xxxxx.qcow2")
        self.assertEqual(True, os.path.exists(dirname), "[check] cannot find dirname in host")
        bash.bash_ro("rm -rf /local_ps")
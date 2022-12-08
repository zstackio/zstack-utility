from kvmagent.test.utils import localstorage_utils,pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
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

        rsp = localstorage_utils.create_empty_volume(
            installUrl = "/local_ps/emptyvolume",
            size = 1048576,
            storagePath = "/local_ps"
        )

        existFile =  os.path.exists("/local_ps/emptyvolume")
        self.assertEqual(True, existFile, "[check] cannot find file in host")
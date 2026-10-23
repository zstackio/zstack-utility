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

TEMPLATE_PATH = "/root/.zguest/min-vm.qcow2"
LOCAL_PS_PATH = "/local_ps"


## describe: case will manage by ztest
class TestLocalStoragePlugin(TestCase):

    @classmethod
    def setUpClass(cls):
        return

    def tearDown(self):
        # Always clean up localstorage path to avoid polluting subsequent runs
        bash.bash_ro("rm -rf %s" % LOCAL_PS_PATH)

    @pytest_utils.ztest_decorater
    def test_resize_volume(self):
        if not os.path.exists(TEMPLATE_PATH):
            self.skipTest("Template %s not found on this node, skip" % TEMPLATE_PATH)

        rsp = localstorage_utils.localstorage_init(LOCAL_PS_PATH)
        self.assertGreater(rsp.totalCapacity, 0, rsp.error)
        self.assertGreater(rsp.availableCapacity, 0, rsp.error)

        install_url = os.path.join(LOCAL_PS_PATH, "test/test.qcow2")

        rsp = localstorage_utils.create_root_volume_from_template(
            templatePathInCache=TEMPLATE_PATH,
            installUrl=install_url,
            storagePath=LOCAL_PS_PATH
        )

        self.assertTrue(os.path.exists(install_url), "[check] cannot find rootvolume in host")

        rsp = localstorage_utils.resize_volume(
            installPath=install_url,
            size=5242880,
            force=True
        )

        self.assertEqual(5242880, rsp.size, "[check] cannot resize_volume in host")

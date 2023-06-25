from kvmagent.test.utils import localstorage_utils,pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote,misc
from zstacklib.utils import linux, jsonobject, bash
from unittest import TestCase
import os
import glob
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
    def test_revert_snapshot(self):
        rsp = localstorage_utils.localstorage_init(
            "/local_ps"
        )
        self.assertGreater(rsp.totalCapacity, 0, rsp.error)
        self.assertGreater(rsp.availableCapacity, 0, rsp.error)

        rsp = localstorage_utils.create_root_volume_from_template(
            templatePathInCache = "/root/.zguest/min-vm.qcow2",
            installUrl = "/local_ps/test/test.qcow2",
            storagePath = "/local_ps"
        )

        self.assertEqual(True, os.path.exists("/local_ps/test/test.qcow2"), "[check] cannot find rootvolume in host")

        rsp = localstorage_utils.revert_snapshot(
            snapshotInstallPath="/local_ps/test/test.qcow2"
        )

        files = glob.glob("/local_ps/test/*.qcow2")
        self.assertEqual(len(files), 2, "[check] cannot revert snapshot in host")
        bash.bash_ro("rm -rf /local_ps")


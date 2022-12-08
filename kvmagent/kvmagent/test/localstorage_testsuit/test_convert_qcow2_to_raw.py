from kvmagent.test.utils import localstorage_utils,pytest_utils,vm_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote,misc
from zstacklib.utils import linux, jsonobject, bash
import os
init_kvmagent()
plugin=localstorage_utils.init_localstorage_plugin()
plugin.start()


PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {}
}


## describe: case will manage by ztest
class TestLocalStoragePlugin(TestCase, vm_utils.VmPluginTestStub):

    @classmethod
    def setUpClass(cls):
        return
    @pytest_utils.ztest_decorater
    def test_create_root_volume_from_template(self):
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

        rsp = localstorage_utils.convert_qcow2_to_raw(
            srcPath="/local_ps/test/test.qcow2"
        )

        self.assertEqual(True, os.path.exists("/local_ps/test/test.raw"),
                         "[check] cannot revert qcow2 to raw in host")
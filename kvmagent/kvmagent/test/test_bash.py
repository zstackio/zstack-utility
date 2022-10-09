import logging

from kvmagent.test.utils import vm_utils
from kvmagent.test.utils.stub import *
from zstacklib.utils import bash

init_kvmagent()
vm_utils.init_vm_plugin()
__ENV_SETUP__ = {
    'current': {
    }
}


class TestVmMigration(TestCase, vm_utils.VmPluginTestStub):

    @classmethod
    def setUpClass(cls):
        pass

    def test_something(self):
        current_vm = env.get_test_environment_metadata()
        r, _ = bash.bash_ro('virsh version')
        logging.info("current_vm:", current_vm, "virsh version:", r)

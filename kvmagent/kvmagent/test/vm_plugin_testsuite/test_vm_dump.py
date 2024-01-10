from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from zstacklib.utils import linux
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmPlugin(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_STOP_VM_PATH
    ])
    @pytest_utils.ztest_decorater
    def test_vm_stop_dump(self):
        vm_uuid, vm = self._create_vm()
        linux.rm_dir_force(vm_plugin.VM_CORE_DUMP_DIR)
        linux.mkdir(vm_plugin.VM_CORE_DUMP_DIR)
        rsp = vm_utils.stop_vm(vm_uuid, debug=True)

        vmcore_dump_path = vm_plugin.VM_CORE_DUMP_DIR + "/" + vm_uuid
        self.assertTrue(os.path.exists(vmcore_dump_path), "core dump file not exists")

        dir_size = linux.get_filesystem_folder_size(vm_plugin.VM_CORE_DUMP_DIR)
        self.assertTrue(dir_size > 0, "core dump file %s size is 0" % vmcore_dump_path)
        self.assertTrue(dir_size < 2 * 1024 * 1024 * 1024, "core dump file %s size is too large" % vmcore_dump_path)
        self._destroy_vm(vm_uuid)

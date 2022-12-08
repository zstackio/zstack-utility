from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc

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
        vm_plugin.VmPlugin.KVM_VM_SYNC_PATH
    ])
    @pytest_utils.ztest_decorater
    def test_vm_sync(self):
        vm_uuid, vm = self._create_vm()

        rsp = vm_utils.vm_sync()
        states = rsp.states

        self.assertEqual(1, len(states))
        self.assertEqual(vm_plugin.Vm.VM_STATE_RUNNING, states[vm_uuid])

        self._destroy_vm(vm_uuid)

        rsp = vm_utils.vm_sync()
        states = rsp.states
        self.assertEqual(0, len(states))

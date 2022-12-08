import pytest

from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from zstacklib.utils import linux

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmLifeCycle(TestCase, vm_utils.VmPluginTestStub):
    vm_uuid = ""

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH,
        vm_plugin.VmPlugin.KVM_STOP_VM_PATH,
        vm_plugin.VmPlugin.KVM_DESTROY_VM_PATH,
    ])
    @pytest.mark.run(order=1)
    @pytest_utils.ztest_decorater
    def test_start_vm(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm_utils.create_vm(vm)
        TestVmLifeCycle.vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(TestVmLifeCycle.vm_uuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % TestVmLifeCycle.vm_uuid)

    @pytest.mark.run(order=2)
    @pytest_utils.ztest_decorater
    def test_stop_vm(self):
        vm_utils.stop_vm(TestVmLifeCycle.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(TestVmLifeCycle.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % TestVmLifeCycle.vm_uuid)

    @pytest.mark.run(order=3)
    @pytest_utils.ztest_decorater
    def test_destroy_vm(self):
        vm_utils.destroy_vm(TestVmLifeCycle.vm_uuid)
        pid = linux.find_vm_pid_by_uuid(TestVmLifeCycle.vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % TestVmLifeCycle.vm_uuid)

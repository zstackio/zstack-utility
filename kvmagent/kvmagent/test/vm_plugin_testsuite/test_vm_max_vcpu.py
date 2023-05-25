from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmMaxVcpu(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_set_max_vcpu_to_240(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.maxVcpuNum = 240
        vm.socketNum = 240
        vm.cpuOnSocket = 1
        vm.threadsPerCore = 1
        vm.cpuNum = 1
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro(
            "virsh dumpxml %s | grep vcpu" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<vcpu placement='static' current='1'>240</vcpu>",
                            "vcpu not configured as expected %s" % o)

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_missing_max_vcpu(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.maxVcpuNum = None
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro(
            "virsh dumpxml %s | grep vcpu" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<vcpu placement='static' current='1'>128</vcpu>",
                         "vcpu not configured as expected %s" % o)

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_max_vcpu(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.maxVcpuNum = 128
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro(
            "virsh dumpxml %s | grep vcpu" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<vcpu placement='static' current='1'>128</vcpu>",
                         "vcpu not configured as expected %s" % o)

        self._destroy_vm(vm.vmInstanceUuid)

        vm.maxVcpuNum = 64
        vm.socketNum = 64
        vm.cpuOnSocket = 1
        vm.threadsPerCore = 1
        vm.cpuNum = 2
        vm_utils.create_vm(vm)
        _, o = bash.bash_ro(
            "virsh dumpxml %s | grep vcpu" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<vcpu placement='static' current='2'>64</vcpu>",
                         "vcpu not configured as expected %s" % o)

        self._destroy_vm(vm.vmInstanceUuid)

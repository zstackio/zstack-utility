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


class TestVmCpuModel(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_cpu_host_passthrough_without_numa(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        vm.nestedVirtualization = 'host-passthrough'
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro(
            "virsh dumpxml %s | grep host-passthrough" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<cpu mode='host-passthrough' check='none'/>",
                         "host-passthrough not exists as expected %s" % o)

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_cpu_host_passthrough_with_numa(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = True
        vm.nestedVirtualization = 'host-passthrough'
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro(
            "virsh dumpxml %s | grep host-passthrough" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<cpu mode='host-passthrough' check='none'>",
                         "host-passthrough not exists as expected %s" % o)

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_cpu_host_model_without_numa(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        vm.nestedVirtualization = 'host-model'
        vm_utils.create_vm(vm)

        _, dom_capabilities = bash.bash_ro(
            "virsh domcapabilities --arch x86_64 | grep host-model -A 1 | tail -1")

        _, guest_cpu_capabilities = bash.bash_ro(
            "virsh dumpxml %s | grep model | head -1" % vm.vmInstanceUuid)
        self.assertEqual(dom_capabilities.strip(), guest_cpu_capabilities.strip(
        ), "cpu model should be the same, domcapabilities: %s, guest cpu: %s" % (dom_capabilities, guest_cpu_capabilities))

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_cpu_host_model_with_numa(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = True
        vm.nestedVirtualization = 'host-model'
        vm_utils.create_vm(vm)

        _, dom_capabilities = bash.bash_ro(
            "virsh domcapabilities --arch x86_64 | grep host-model -A 1 | tail -1")

        _, guest_cpu_capabilities = bash.bash_ro(
            "virsh dumpxml %s | grep model | head -1" % vm.vmInstanceUuid)
        self.assertEqual(dom_capabilities.strip(), guest_cpu_capabilities.strip(
        ), "cpu model should be the same, domcapabilities: %s, guest cpu: %s" % (dom_capabilities, guest_cpu_capabilities))

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_cpu_custom_without_numa(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        vm.nestedVirtualization = 'custom'
        vm.vmCpuModel = 'pentium'
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro(
            "virsh dumpxml %s | grep model | grep pentium" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<model fallback='forbid'>pentium</model>",
                         "unexpected cpu model %s" % o.strip())

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_cpu_custom_with_numa(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = True
        vm.nestedVirtualization = 'custom'
        vm.vmCpuModel = 'pentium'
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro(
            "virsh dumpxml %s | grep model | grep pentium" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<model fallback='forbid'>pentium</model>",
                         "unexpected cpu model %s" % o.strip())

        self._destroy_vm(vm.vmInstanceUuid)

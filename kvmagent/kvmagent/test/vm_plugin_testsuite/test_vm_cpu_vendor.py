from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from zstacklib.utils import linux
from unittest import TestCase
import platform

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmCpuVendor(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])

    @pytest_utils.ztest_decorater
    def test_cpu_none_with_specific_vendor(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.nestedVirtualization = 'none'
        vm.vmCpuVendorId = 'AuthenticAMD'
        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm.vmInstanceUuid)

        r, _ = bash.bash_ro(
            "virsh dumpxml %s | grep AuthenticAMD" % vm.vmInstanceUuid)
        
        if platform.machine() == 'aarch64':
            self.assertFalse( r== 0,
                             "missing cpu vendor AuthenticAMD from libvirt xml")
        elif platform.machine() == 'x86_64':
            self.assertTrue(r == 0,
                            "libvirt xml should contain AuthenticAMD")

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_cpu_host_passthrough_with_specific_vendor(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.nestedVirtualization = 'host-passthrough'
        vm.vmCpuVendorId = 'AuthenticAMD'
        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm.vmInstanceUuid)

        r, _ = bash.bash_ro(
            "virsh dumpxml %s | grep AuthenticAMD" % vm.vmInstanceUuid)
        
        if platform.machine() == 'aarch64':
            self.assertFalse( r== 0,
                             "missing cpu vendor AuthenticAMD from libvirt xml")
        elif platform.machine() == 'x86_64':
            self.assertTrue(r == 0,
                            "libvirt xml should contain AuthenticAMD")

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_cpu_host_model_with_specific_vendor(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.nestedVirtualization = 'host-model'
        vm.vmCpuVendorId = 'AuthenticAMD'
        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm.vmInstanceUuid)

        r, _ = bash.bash_ro(
            "virsh dumpxml %s | grep AuthenticAMD" % vm.vmInstanceUuid)
        
        if platform.machine() == 'aarch64':
            self.assertFalse( r== 0,
                             "missing cpu vendor AuthenticAMD from libvirt xml")
        elif platform.machine() == 'x86_64':
            self.assertTrue(r == 0,
                            "libvirt xml should contain AuthenticAMD")

        self._destroy_vm(vm.vmInstanceUuid)

    @pytest_utils.ztest_decorater
    def test_cpu_custom_with_specific_vendor(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.nestedVirtualization = 'custom'
        vm.vmCpuModel = 'pentium'
        vm.vmCpuVendorId = 'AuthenticAMD'
        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm.vmInstanceUuid)

        r, _ = bash.bash_ro(
            "virsh dumpxml %s | grep AuthenticAMD" % vm.vmInstanceUuid)
        
        if platform.machine() == 'aarch64':
            self.assertFalse( r== 0,
                             "missing cpu vendor AuthenticAMD from libvirt xml")
        elif platform.machine() == 'x86_64':
            self.assertTrue(r == 0,
                            "libvirt xml should contain AuthenticAMD")

        self._destroy_vm(vm.vmInstanceUuid)

import mock
from unittest import TestCase

from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import qemu

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestHyperv(TestCase, vm_utils.VmPluginTestStub):
    """
    Test case for using different version of edk2-ovmf
    """

    vm_uuid = None

    @classmethod
    def setUpClass(cls):
        """
        Set up the test class by creating a default bridge if it doesn't exist.
        """
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])
    @pytest_utils.ztest_decorater
    @bash.in_bash
    @mock.patch.object(qemu, 'get_version')
    def test_qemu2_kernel3(self, mock_get_qemu_version):
        mock_get_qemu_version.return_value = '2.12.0'
        vm_plugin.KERNEL_VERSION = '3.10.0-957'
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootMode = "UEFI"
        vm.emulateHyperV = True
        vm.hypervClock = True
        vm.clock = 'localtime'

        vm_utils.create_vm(vm)

        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid,
                         'cannot find pid of vm[%s]' % vm.vmInstanceUuid)
        r, _ = bash.bash_ro(
            'virsh dumpxml %s | grep -q "<stimer state=\'on\'>"' %
            vm.vmInstanceUuid)
        self.assertEqual(r, 1, 'vm is not using new hyperv params')

        self._destroy_vm(vm.vmInstanceUuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])
    @pytest_utils.ztest_decorater
    @bash.in_bash
    @mock.patch.object(qemu, 'get_version')
    def test_qemu2_kernel4(self, mock_get_qemu_version):
        mock_get_qemu_version.return_value = '2.12.0'
        vm_plugin.KERNEL_VERSION = '4.18.0-348'
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootMode = "UEFI"
        vm.emulateHyperV = True
        vm.hypervClock = True
        vm.clock = 'localtime'

        vm_utils.create_vm(vm)

        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid,
                         'cannot find pid of vm[%s]' % vm.vmInstanceUuid)
        r, _ = bash.bash_ro(
            'virsh dumpxml %s | grep -q "<stimer state=\'on\'>"' %
            vm.vmInstanceUuid)
        self.assertEqual(r, 1, 'vm is not using new hyperv params')

        self._destroy_vm(vm.vmInstanceUuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])
    @pytest_utils.ztest_decorater
    @bash.in_bash
    @mock.patch.object(qemu, 'get_version')
    def test_qemu4_kernel3(self, mock_get_qemu_version,):
        mock_get_qemu_version.return_value = '4.2.0'
        vm_plugin.KERNEL_VERSION = '3.10.0-957'
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootMode = "UEFI"
        vm.emulateHyperV = True
        vm.hypervClock = True
        vm.clock = 'localtime'

        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid,
                         'cannot find pid of vm[%s]' % vm.vmInstanceUuid)
        r, _ = bash.bash_ro(
            'virsh dumpxml %s | grep -q "<stimer state=\'on\'>"' %
            vm.vmInstanceUuid)
        self.assertEqual(r, 1, 'vm is not using new hyperv params')

        self._destroy_vm(vm.vmInstanceUuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])
    @pytest_utils.ztest_decorater
    @bash.in_bash
    @mock.patch.object(qemu, 'get_version')
    def test_qemu4_kernel4(self, mock_get_qemu_version):
        mock_get_qemu_version.return_value = '4.2.0'
        vm_plugin.KERNEL_VERSION = '4.18.0-348'
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootMode = "UEFI"
        vm.emulateHyperV = True
        vm.hypervClock = True
        vm.clock = 'localtime'

        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid,
                         'cannot find pid of vm[%s]' % vm.vmInstanceUuid)
        r, _ = bash.bash_ro(
            'virsh dumpxml %s | grep -q "<stimer state=\'on\'"' %
            vm.vmInstanceUuid)
        self.assertEqual(r, 0, 'vm is using new hyperv params')

        self._destroy_vm(vm.vmInstanceUuid)


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


class TestOvmf(TestCase, vm_utils.VmPluginTestStub):
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
    @mock.patch.object(linux, 'get_rpm_version')
    @mock.patch.object(qemu, 'get_version')
    def test_qemu2_edk2_git(self, mock_get_qemu_version, mock_get_rpm_version):
        mock_get_qemu_version.return_value = '2.12.0'
        mock_get_rpm_version.return_value = '20220126gitbb1bba3d77-3'
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootMode = "UEFI"
        vm.emulateHyperV = True

        vm_utils.create_vm(vm)

        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid,
                         'cannot find pid of vm[%s]' % vm.vmInstanceUuid)
        r, _ = bash.bash_ro(
            'virsh dumpxml %s | grep -q "/usr/share/edk2.git"' %
            vm.vmInstanceUuid)
        self.assertEqual(r, 0, 'vm is using edk2.git')

        self._destroy_vm(vm.vmInstanceUuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])
    @pytest_utils.ztest_decorater
    @bash.in_bash
    @mock.patch.object(linux, 'get_rpm_version')
    @mock.patch.object(qemu, 'get_version')
    def test_qemu2_edk2_ovmf(self, mock_get_qemu_version,
                             mock_get_rpm_version):
        mock_get_qemu_version.return_value = '2.12.0'
        mock_get_rpm_version.return_value = '20220126gitbb1bba3d77-4'
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootMode = "UEFI"
        vm.emulateHyperV = True

        vm_utils.create_vm(vm)

        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid,
                         'cannot find pid of vm[%s]' % vm.vmInstanceUuid)
        r, _ = bash.bash_ro(
            'virsh dumpxml %s | grep -q "/usr/share/edk2.git"' %
            vm.vmInstanceUuid)
        self.assertEqual(r, 0, 'vm is using edk2.git')

        self._destroy_vm(vm.vmInstanceUuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])
    @pytest_utils.ztest_decorater
    @bash.in_bash
    @mock.patch.object(linux, 'get_rpm_version')
    @mock.patch.object(qemu, 'get_version')
    def test_qemu4_edk2_git(self, mock_get_qemu_version, mock_get_rpm_version):
        mock_get_qemu_version.return_value = '4.2.0'
        mock_get_rpm_version.return_value = '20220126gitbb1bba3d77-3'
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootMode = "UEFI"
        vm.emulateHyperV = True

        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid,
                         'cannot find pid of vm[%s]' % vm.vmInstanceUuid)
        r, _ = bash.bash_ro(
            'virsh dumpxml %s | grep -q "/usr/share/edk2.git"' %
            vm.vmInstanceUuid)
        self.assertEqual(r, 0, 'vm is using edk2.git')

        self._destroy_vm(vm.vmInstanceUuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])
    @pytest_utils.ztest_decorater
    @bash.in_bash
    @mock.patch.object(linux, 'get_rpm_version')
    @mock.patch.object(qemu, 'get_version')
    def test_qemu4_edk2_ovmf(self, mock_get_qemu_version,
                             mock_get_rpm_version):
        mock_get_qemu_version.return_value = '4.2.0'
        mock_get_rpm_version.return_value = '20220126gitbb1bba3d77-4.el7'
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootMode = "UEFI"
        vm.emulateHyperV = True

        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid,
                         'cannot find pid of vm[%s]' % vm.vmInstanceUuid)
        r, _ = bash.bash_ro(
            'virsh dumpxml %s | grep -q "/usr/share/edk2/ovmf"' %
            vm.vmInstanceUuid)
        self.assertEqual(r, 0, 'vm is using ovmf-edk2')

        self._destroy_vm(vm.vmInstanceUuid)


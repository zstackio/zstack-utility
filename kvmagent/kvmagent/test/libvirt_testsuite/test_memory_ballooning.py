from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from zstacklib.utils import linux
from zstacklib.utils import bash
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}

class TestMemoryBallooning(TestCase, vm_utils.VmPluginTestStub):
    """
    Test case for memory ballooning in a virtual machine using libvirt.
    """

    vm_uuid = None
    vm_original_memory_in_mb = None
    vm_mem = 65536

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
    def test(self):
        """
        Test the memory ballooning functionality.

        Steps:
        1. Check the maximum memory of the libvirt XML.
        2. Shrink the libvirt guest memory.
        3. Check the domain information.
        4. Increase the libvirt guest memory.
        5. Check the domain information.
        6. Destroy the virtual machine.
        """
        self.check_max_memory_of_libvirt_xml()
        self.shrink_libvirt_guest_memory()
        self.check_dominfo()
        self.increase_libvirt_guest_memory()
        self.check_dominfo()

        self._destroy_vm(TestMemoryBallooning.vm_uuid)

    @bash.in_bash
    def check_max_memory_of_libvirt_xml(self):
        """
        Check the maximum memory specified in the libvirt XML.

        This method creates a virtual machine with the specified memory and checks if the maximum memory in the XML
        matches the expected value.
        """
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = True
        vm.mem = 65536

        vm_utils.create_vm(vm)

        TestMemoryBallooning.vm_original_memory_in_mb = vm.memory / 1024 / 1024
        TestMemoryBallooning.vm_uuid = vm.vmInstanceUuid

        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm.vmInstanceUuid)

        r, _ = bash.bash_ro("virsh dumpxml %s | grep 'memory unit' | grep '>65536<'" % vm.vmInstanceUuid)
        self.assertEqual(r, 1, "vm memory is 65536")

    @bash.in_bash
    def shrink_libvirt_guest_memory(self):
        """
        Shrink the memory of the libvirt guest to half of orignal size.

        This method uses the 'virsh setmem' command to shrink the memory of the libvirt guest to half of its original
        memory size. It then checks the used memory and domain memory statistics.
        """
        r, _ = bash.bash_ro("virsh setmem --domain %s --size %dM --current"
                             % (TestMemoryBallooning.vm_uuid,
                                 TestMemoryBallooning.vm_original_memory_in_mb / 2))

        self.assertEqual(r, 0, "virsh setmem shrink failed")
        self.check_used_memory(TestMemoryBallooning.vm_original_memory_in_mb / 2)
        self.check_dommemstat(TestMemoryBallooning.vm_original_memory_in_mb / 2)

    @bash.in_bash
    def increase_libvirt_guest_memory(self):
        """
        Increase the memory of the libvirt guest to orignal memory size.

        This method uses the 'virsh setmem' command to increase the memory of the libvirt guest to its original memory
        size. It then checks the used memory and domain memory statistics.
        """
        r, _ = bash.bash_ro("virsh setmem --domain %s --size %dM --current"
                             % (TestMemoryBallooning.vm_uuid,
                                 TestMemoryBallooning.vm_original_memory_in_mb))

        self.assertEqual(r, 0, "virsh setmem increase failed")
        self.check_used_memory(TestMemoryBallooning.vm_original_memory_in_mb)
        self.check_dommemstat(TestMemoryBallooning.vm_original_memory_in_mb)

    @bash.in_bash
    def check_dominfo(self):
        """
        Check the domain information of the libvirt guest.

        This method uses the 'virsh dominfo' command to retrieve the maximum memory of the libvirt guest and compares it
        with the expected value.
        """
        _, o = bash.bash_ro("virsh dominfo %s | grep 'Max memory' | awk '{print $3}'" % TestMemoryBallooning.vm_uuid)
        self.assertEqual(int(o.strip('\n')), TestMemoryBallooning.vm_original_memory_in_mb * 1024, "dominfo failed, find max memory %s expected %s" % (o, TestMemoryBallooning.vm_original_memory_in_mb * 1024))

    @linux.retry(times=60, sleep_time=1)
    @bash.in_bash
    def check_used_memory(self, current_memory=None):
        """
        Check the used memory of the libvirt guest.

        This method uses the 'virsh dominfo' command to retrieve the used memory of the libvirt guest and compares it
        with the expected value.
        """
        _, o = bash.bash_ro("virsh dominfo %s | grep 'Used memory' | awk '{print $3}'" % TestMemoryBallooning.vm_uuid)
        self.assertEqual(int(o.strip('\n')), current_memory * 1024, "dominfo failed, find used memory %s expected %s" % (o, current_memory * 1024))

    @linux.retry(times=60, sleep_time=1)
    @bash.in_bash
    def check_dommemstat(self, current_memory=None):
        """
        Check the domain memory statistics of the libvirt guest.

        This method uses the 'virsh dommemstat' command to retrieve the actual memory usage of the libvirt guest and
        compares it with the expected value.
        """
        _, o = bash.bash_ro("virsh dommemstat %s | grep 'actual' | awk '{print $2}'" % TestMemoryBallooning.vm_uuid)
        self.assertEqual(int(o.strip('\n')), current_memory * 1024, "dommemstat failed, find used memory %s expected %s" % (o, current_memory * 1024))
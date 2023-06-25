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

    vm_uuid = None
    vm_original_memory_in_mb = None
    vm_mem = 65536

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])

    @pytest_utils.ztest_decorater
    def test(self):
        self.test_check_max_memory_of_libvirt_xml()
        self.test_shrink_libvirt_guest_memory()
        self.check_dominfo()
        self.test_increase_libvirt_guest_memory()
        self.check_dominfo()

        self._destroy_vm(TestMemoryBallooning.vm_uuid)

    @bash.in_bash
    def test_check_max_memory_of_libvirt_xml(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = True
        vm.mem = 65536

        vm_utils.create_vm(vm)

        TestMemoryBallooning.vm_original_memory_in_mb = vm.memory / 1024 / 1024
        TestMemoryBallooning.vm_uuid = vm.vmInstanceUuid

        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm.vmInstanceUuid)

        r, _ = bash.bash_ro("virsh dumpxml %s | grep 'memory unit' | grep '>65536<'" % vm.vmInstanceUuid)
        self.assertEqual(r, 0, "vm memory is 65536")

    @bash.in_bash
    def test_shrink_libvirt_guest_memory(self):
        # virsh setmem --domain $VM --size 1500M --current
        r, _ = bash.bash_ro("virsh setmem --domain %s --size %dM --current"
                             % (TestMemoryBallooning.vm_uuid,
                                 TestMemoryBallooning.vm_original_memory_in_mb / 2))

        self.assertEqual(r, 0, "virsh setmem shrink failed")
        self.check_used_memory(TestMemoryBallooning.vm_original_memory_in_mb / 2)
        self.check_dommemstat(TestMemoryBallooning.vm_original_memory_in_mb / 2)

    @bash.in_bash
    def test_increase_libvirt_guest_memory(self):
        # virsh setmem --domain $VM --size 1500M --current
        r, _ = bash.bash_ro("virsh setmem --domain %s --size %dM --current"
                             % (TestMemoryBallooning.vm_uuid,
                                 TestMemoryBallooning.vm_original_memory_in_mb))

        self.assertEqual(r, 0, "virsh setmem increase failed")
        self.check_used_memory(TestMemoryBallooning.vm_original_memory_in_mb)
        self.check_dommemstat(TestMemoryBallooning.vm_original_memory_in_mb)

    @bash.in_bash
    def check_dominfo(self):
        # virsh dominfo $VM
        _, o = bash.bash_ro("virsh dominfo %s | grep 'Max memory' | awk '{print $3}'" % TestMemoryBallooning.vm_uuid)
        self.assertEqual(int(o.strip('\n')), TestMemoryBallooning.vm_original_memory_in_mb * 1024, "dominfo failed, find max memory %s expected %s" % (o, TestMemoryBallooning.vm_original_memory_in_mb * 1024))

    @linux.retry(times=30, sleep_time=1)
    @bash.in_bash
    def check_used_memory(self, current_memory=None):
        # virsh dommemstat $VM
        _, o = bash.bash_ro("virsh dominfo %s | grep 'Used memory' | awk '{print $3}'" % TestMemoryBallooning.vm_uuid)
        self.assertEqual(int(o.strip('\n')), current_memory * 1024, "dominfo failed, find used memory %s expected %s" % (o, current_memory * 1024))

    @linux.retry(times=30, sleep_time=1)
    @bash.in_bash
    def check_dommemstat(self, current_memory=None):
        # virsh dommemstat $VM
        _, o = bash.bash_ro("virsh dommemstat %s | grep 'actual' | awk '{print $2}'" % TestMemoryBallooning.vm_uuid)
        self.assertEqual(int(o.strip('\n')), current_memory * 1024, "dommemstat failed, find used memory %s expected %s" % (o, current_memory * 1024))
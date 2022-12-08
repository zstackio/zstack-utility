from kvmagent.test.utils.stub import *
from kvmagent.test.utils import vm_utils, network_utils, volume_utils, pytest_utils
from zstacklib.utils import linux, sizeunit, bash
from zstacklib.test.utils import misc
from kvmagent.plugins import vm_plugin

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
        vm_plugin.VmPlugin.KVM_ONLINE_CHANGE_CPUMEM_PATH,
    ])
    @pytest_utils.ztest_decorater
    def test_vm_online_change_cpumem(self):
        vm_uuid, vm = self._create_vm()
        mem_size = vm.memory + 33554432  # increase 32M
        cpu_num = vm.cpuNum + 1  # increase one

        vm_utils.online_change_cpumem(vm_uuid, cpu_num, mem_size)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        n_cpu = int(xml.vcpu.current_)
        m_size = sizeunit.KiloByte.toByte(long(xml.memory.text_))
        self.assertEqual(mem_size, m_size, 'expect memory size[%s] but get %s' % (mem_size, m_size))
        self.assertEqual(cpu_num, n_cpu, 'expect %s vcpu but get %s vcpu' % (n_cpu, cpu_num))

        # clean
        self._destroy_vm(vm_uuid)

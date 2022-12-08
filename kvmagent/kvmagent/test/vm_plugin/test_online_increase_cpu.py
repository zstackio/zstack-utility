from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestOnlineIncreaseCpu(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_vm_online_increase_cpu(self):
        vm_uuid, vm = self._create_vm()
        cpu_num = vm.cpuNum + 1  # increase one

        vm_utils.online_increase_cpu(vm_uuid, cpu_num)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        n_cpu = int(xml.vcpu.current_)
        self.assertEqual(cpu_num, n_cpu, 'expect %s vcpu but get %s vcpu' % (n_cpu, cpu_num))

        self._destroy_vm(vm_uuid)

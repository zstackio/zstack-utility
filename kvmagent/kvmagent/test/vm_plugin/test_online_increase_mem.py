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

    @pytest_utils.ztest_decorater
    def test_vm_online_increase_mem(self):
        vm_uuid, vm = self._create_vm()
        mem_size = vm.memory + 33554432  # increase 32M

        vm_utils.online_increase_mem(vm_uuid, mem_size)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        m_size = sizeunit.KiloByte.toByte(long(xml.memory.text_))
        self.assertEqual(mem_size, m_size, 'expect memory size[%s] but get %s' % (mem_size, m_size))

        self._destroy_vm(vm_uuid)

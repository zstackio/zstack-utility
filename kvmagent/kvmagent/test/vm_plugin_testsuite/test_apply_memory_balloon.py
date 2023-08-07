from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from zstacklib.utils import sizeunit
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestApplyMemoryBalloon(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.APPLY_MEMORY_BALLOON_PATH
    ])
    @pytest_utils.ztest_decorater
    def test_vm_apply_memory_balloon(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        vm_utils.create_vm(vm)
        mem_size = vm.memory - vm.memory * 5 / 100

        vm_utils.apply_memory_balloon([vm.vmInstanceUuid], 'Decrease', 5)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm.vmInstanceUuid)
        m_size = sizeunit.KiloByte.toByte(long(xml.memory.text_))
        self.assertNotEqual(mem_size, m_size, 'expect memory size[%s] but get %s' % (mem_size, m_size))
        self.assertNotEqual(vm.memory, m_size, 'expect memory size[%s] but get %s' % (mem_size, m_size))

        self._destroy_vm(vm.vmInstanceUuid)

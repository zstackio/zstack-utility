from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from unittest import TestCase

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
        vm_plugin.VmPlugin.KVM_GET_CONSOLE_PORT_PATH
    ])
    @pytest_utils.ztest_decorater
    def test_get_console_port(self):
        vm_uuid, vm = self._create_vm()

        rsp = vm_utils.get_vnc_port(vm_uuid)
        self.assertEqual(5900, int(rsp.port), 'vnc port[%s] is not 5900' % rsp.port)

        self._destroy_vm(vm_uuid)

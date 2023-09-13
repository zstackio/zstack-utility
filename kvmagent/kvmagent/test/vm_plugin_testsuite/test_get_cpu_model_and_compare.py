from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from kvmagent.plugins.vm_plugin import VmPlugin
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.test.utils import misc
from zstacklib.test.utils import remote
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()
PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {
    }
}

class TestVmPlugin(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_GET_CPU_XML_PATH,
        vm_plugin.VmPlugin.KVM_COMPARE_CPU_FUNCTION_PATH
    ])
    @pytest_utils.ztest_decorater
    def test_get_cpu_model_and_conpare(self):
        rsp = jsonobject.loads(vm_utils.get_cpu_xml())
        xmlResult, xmlOutput = bash.bash_ro('virsh capabilities | virsh cpu-baseline /dev/stdin')
        _, modelNameOut = linux.get_cpu_model()
        self.assertEqual(rsp.cpuXml.strip('\n\t '), xmlOutput.strip('\n\t '), 'xml is inconsistent')
        self.assertEqual(rsp.cpuModelName, modelNameOut.splitlines()[0], 'cpuModelName is inconsistent')
        compareRsp = jsonobject.loads(vm_utils.compare_cpu_function(rsp.cpuXml))
        self.assertEqual(compareRsp.success, True, 'compareRsp is not true')

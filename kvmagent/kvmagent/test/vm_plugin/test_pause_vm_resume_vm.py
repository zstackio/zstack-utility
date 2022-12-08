from kvmagent.test.utils.stub import *
from kvmagent.test.utils import vm_utils, network_utils, volume_utils, pytest_utils
from zstacklib.utils import linux, sizeunit, bash
from zstacklib.test.utils import misc
from kvmagent.plugins import vm_plugin
import pytest

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
        vm_plugin.VmPlugin.KVM_PAUSE_VM_PATH,
    ])

    @pytest_utils.ztest_decorater
    def test_pause_resume_vm(self):
        vm_uuid, _ = self._create_vm()

        vm_utils.pause_vm(vm_uuid)
        r = bash.bash_r('virsh list --state-paused | grep %s' % vm_uuid)
        self.assertEqual(0, r, 'vm[%s] not paused' % vm_uuid)

        vm_utils.resume_vm(vm_uuid)
        r = bash.bash_r('virsh list | grep %s' % vm_uuid)
        self.assertEqual(0, r, 'vm[%s] not running' % vm_uuid)

        self._destroy_vm(vm_uuid)

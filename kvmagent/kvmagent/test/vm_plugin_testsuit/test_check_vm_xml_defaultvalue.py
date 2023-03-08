import pytest

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


class TestVmXmLDefaultValue(TestCase, vm_utils.VmPluginTestStub):
    vm_uuid = ""

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH
    ])
    @pytest.mark.run(order=1)
    @pytest_utils.ztest_decorater
    def test_check_vm_nic_defultqueuedepth(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.nics[0].vHostAddOn.queueNum = 2
        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm.vmInstanceUuid)

        _, o = bash.bash_ro("virsh dumpxml %s|grep vhost" % vm.vmInstanceUuid)

        containCount=o.count("256")
        self.assertEqual(containCount, 2, "vm xml nic rx(tx)BufferSize not equal 1024")


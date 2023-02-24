import pytest

from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.utils import bash
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestPauseVmResumeVm(TestCase, vm_utils.VmPluginTestStub):
    vm_uuid = ''

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest.mark.run(order=1)
    @pytest_utils.ztest_decorater
    def test_pause_vm(self):
        TestPauseVmResumeVm.vm_uuid, _ = self._create_vm()

        vm_utils.pause_vm(TestPauseVmResumeVm.vm_uuid)
        r = bash.bash_r('virsh list --state-paused | grep %s' % TestPauseVmResumeVm.vm_uuid)
        self.assertEqual(0, r, 'vm[%s] not paused' % TestPauseVmResumeVm.vm_uuid)

    @pytest.mark.run(order=2)
    @pytest_utils.ztest_decorater
    def test_resume_vm(self):
        vm_utils.resume_vm(TestPauseVmResumeVm.vm_uuid)
        r = bash.bash_r('virsh list | grep %s' % TestPauseVmResumeVm.vm_uuid)
        self.assertEqual(0, r, 'vm[%s] not running' % TestPauseVmResumeVm.vm_uuid)

        self._destroy_vm(TestPauseVmResumeVm.vm_uuid)

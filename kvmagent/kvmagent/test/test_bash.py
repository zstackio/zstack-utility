import logging

from kvmagent.test.utils import vm_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.utils import bash
from unittest import TestCase

__ENV_SETUP__ = {
    'self': {
    }
}


class TestBash(TestCase, vm_utils.VmPluginTestStub):

    @classmethod
    def setUpClass(cls):
        pass

    @pytest_utils.ztest_decorater
    def test_bash(self):
        current_vm = env.get_test_environment_metadata()
        r, _ = bash.bash_ro('virsh version')
        logging.info("current_vm:", current_vm, "virsh version:", r)


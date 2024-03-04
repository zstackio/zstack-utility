from kvmagent.test.utils.stub import *
from kvmagent.test.utils import vm_utils
from unittest import TestCase

init_kvmagent()

from kvmagent.plugins import prometheus

__ENV_SETUP__ = {
    'self': {}
}

class TestCollectMemoryOvercommit(TestCase, vm_utils.VmPluginTestStub):

    def test_collect_memory_overcommit_statistics(self):
        # mock prometheus plugin started
        prometheus.PAGE_SIZE = 4096

        # test collect_memory_overcommit_statistics works as expected
        prometheus.collect_memory_overcommit_statistics()
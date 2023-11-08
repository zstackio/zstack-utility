from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from unittest import TestCase
from distutils.version import LooseVersion

import platform

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmMaxVcpu(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()


    @pytest_utils.ztest_decorater
    def test_hv_synic_enabled_with_kernel_newer_than_3_10_0(self):
        hv_features = ["synic", "vpindex", "stimer"]

        vm_plugin.KERNEL_VERSION = "kernel-4.18.0-348.23.1.2.g50e329d.el7.x86_64"
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.emulateHyperV = True
        vm.hypervClock = True
        vm.clock = 'localtime'
        vm_utils.create_vm(vm)

        for feature in hv_features:
            r, _ = bash.bash_ro(
                "virsh dumpxml %s | grep %s" % (vm.vmInstanceUuid, feature))
            self.assertTrue(r == 0, "missing feature %s from xml" % feature)

        self._destroy_vm(vm.vmInstanceUuid)
        vm_plugin.KERNEL_VERSION = platform.release()


    @pytest_utils.ztest_decorater
    def test_hv_synic_disabled_with_kernel_older_than_3_10_0(self):
        hv_features = ["synic", "vpindex", "stimer"]

        vm_plugin.KERNEL_VERSION = "3.10.0-957.27.8.2.g295089a.el7.x86_64"
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.emulateHyperV = True
        vm.hypervClock = True
        vm.clock = 'localtime'
        vm_utils.create_vm(vm)

        for feature in hv_features:
            r, o = bash.bash_ro(
                "virsh dumpxml %s | grep %s" % (vm.vmInstanceUuid, feature))
            self.assertTrue(r == 1, "unexpected feature %s from xml %s" % (feature, o))

        self._destroy_vm(vm.vmInstanceUuid)
        vm_plugin.KERNEL_VERSION = platform.release()


    @pytest_utils.ztest_decorater
    def test_hv_synic_on_current_host(self):
        hv_features = ["synic", "vpindex", "stimer"]

        vm_plugin.KERNEL_VERSION = platform.release()
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.emulateHyperV = True
        vm.hypervClock = True
        vm.clock = 'localtime'
        vm_utils.create_vm(vm)

        for feature in hv_features:
            r, o = bash.bash_ro(
                "virsh dumpxml %s | grep %s" % (vm.vmInstanceUuid, feature))
            
            if LooseVersion(vm_plugin.KERNEL_VERSION) > LooseVersion("3.10.0"):
                self.assertTrue(r == 0, "missing feature %s from xml" % feature)
            else:
                self.assertTrue(r == 1, "unexpected feature %s from xml %s" % (feature, o))

        self._destroy_vm(vm.vmInstanceUuid)
        vm_plugin.KERNEL_VERSION = platform.release()

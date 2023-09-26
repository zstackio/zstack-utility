import libvirt
import pytest

from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from kvmagent import kvmagent
from zstacklib.test.utils import misc
from zstacklib.utils import bash, jsonobject
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmCpuTopology(TestCase, vm_utils.VmPluginTestStub):
    vm_uuid = ""

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH,
        vm_plugin.VmPlugin.KVM_ONLINE_INCREASE_CPU_PATH
    ])

    def test_vm_cpu_topology_not_exits(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro("virsh dumpxml %s | grep topology" % vm.vmInstanceUuid)
        self.assertEqual(o, "", "topology should not exists by default")

        self._destroy_vm(vm.vmInstanceUuid)

    def test_vm_cpu_toplogy_in_xml_as_expected(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        # self.socketNum = None
        # self.cpuOnSocket = None
        # self.threadsPerCore = None
        vm.socketNum = 2
        vm.cpuOnSocket = 1
        vm.threadsPerCore = 1
        vm.cpuNum = 2
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro("virsh dumpxml %s | grep topology" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<topology sockets='2' cores='1' threads='1'/>", "unexpected cpu topology")

        self._destroy_vm(vm.vmInstanceUuid)

    def test_vm_cpu_num_could_less_than_cpu_topology(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        # self.socketNum = None
        # self.cpuOnSocket = None
        # self.threadsPerCore = None
        vm.socketNum = 2
        vm.cpuOnSocket = 1
        vm.threadsPerCore = 1
        vm.cpuNum = 1

        rsp = jsonobject.loads(vm_utils.create_vm(vm))
        assert rsp.success == False
        assert "libvirt error: unsupported configuration: CPU topology doesn't match maximum vcpu count" in str(rsp.error) 

    def test_numa_use_default(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = True
        vm_utils.create_vm(vm)

        _, o = bash.bash_ro("virsh dumpxml %s | grep topology" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<topology sockets='32' cores='4' threads='1'/>", "unexpected numa cpu topology")

        self._destroy_vm(vm.vmInstanceUuid)

    def test_vm_cpu_without_cpu_hot_plug_2(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        vm.socketNum = 2
        vm.cpuOnSocket = 4
        vm.threadsPerCore = 1
        vm.cpuNum = 8
        vm.maxVcpuNum = vm.socketNum * vm.cpuOnSocket * vm.threadsPerCore

        vm_utils.create_vm(vm)

        _, o = bash.bash_ro("virsh dumpxml %s | grep topology" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<topology sockets='2' cores='4' threads='1'/>", "unexpected cpu topology")

        _, o = bash.bash_ro("virsh dumpxml %s | grep 'vcpu placement='" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<vcpu placement='static' current='8'>8</vcpu>", "unexpected cpu after increase vcpu")

        self._destroy_vm(vm.vmInstanceUuid)

    def test_vm_cpu_without_cpu_hot_plug(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = False
        vm.socketNum = 2
        vm.cpuOnSocket = 4
        vm.threadsPerCore = 1
        vm.cpuNum = 1
        vm.maxVcpuNum = vm.socketNum * vm.cpuOnSocket * vm.threadsPerCore

        vm_utils.create_vm(vm)

        _, o = bash.bash_ro("virsh dumpxml %s | grep topology" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<topology sockets='2' cores='4' threads='1'/>", "unexpected cpu topology")

        _, o = bash.bash_ro("virsh dumpxml %s | grep 'vcpu placement='" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<vcpu placement='static' current='1'>8</vcpu>", "unexpected cpu after increase vcpu")

        self._destroy_vm(vm.vmInstanceUuid)

    def test_vm_cpu_hot_plug(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.useNuma = True
        vm.socketNum = 2
        vm.cpuOnSocket = 4
        vm.threadsPerCore = 1
        vm.cpuNum = 1
        vm.maxVcpuNum = vm.socketNum * vm.cpuOnSocket * vm.threadsPerCore

        vm_utils.create_vm(vm)

        _, o = bash.bash_ro("virsh dumpxml %s | grep topology" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<topology sockets='2' cores='4' threads='1'/>", "unexpected cpu topology")

        vm_utils.increase_vm_cpu(vm.vmInstanceUuid, 8)

        _, o = bash.bash_ro("virsh dumpxml %s | grep 'vcpu placement='" % vm.vmInstanceUuid)
        self.assertEqual(o.strip(), "<vcpu placement='static'>8</vcpu>", "unexpected cpu after increase vcpu")

        self._destroy_vm(vm.vmInstanceUuid)



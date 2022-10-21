from kvmagent.test.utils.stub import *
from kvmagent.test.utils import vm_utils, network_utils, volume_utils
from zstacklib.utils import linux, sizeunit, bash
from zstacklib.test.utils import misc
from kvmagent.plugins import vm_plugin

init_kvmagent()
vm_utils.init_vm_plugin()


class TestVmPlugin(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_START_VM_PATH,
        vm_plugin.VmPlugin.KVM_STOP_VM_PATH,
        vm_plugin.VmPlugin.KVM_DESTROY_VM_PATH,
    ])
    def test_vm_lifecycle(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm_utils.create_vm(vm)
        vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm_uuid)

        vm_utils.stop_vm(vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % vm_uuid)

        vm_utils.destroy_vm(vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % vm_uuid)

        # create again and destroy
        vm = vm_utils.create_startvm_body_jsonobject()
        vm_utils.create_vm(vm)
        vm_utils.destroy_vm(vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % vm_uuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_PAUSE_VM_PATH,
        vm_plugin.VmPlugin.KVM_RESUME_VM_PATH,
    ])
    def test_pause_resume_vm(self):
        vm_uuid, _ = self._create_vm()

        vm_utils.pause_vm(vm_uuid)
        r = bash.bash_r('virsh list --state-paused | grep %s' % vm_uuid)
        self.assertEqual(0, r, 'vm[%s] not paused' % vm_uuid)

        vm_utils.resume_vm(vm_uuid)
        r = bash.bash_r('virsh list | grep %s' % vm_uuid)
        self.assertEqual(0, r, 'vm[%s] not running' % vm_uuid)

        self._destroy_vm(vm_uuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_ONLINE_INCREASE_CPU_PATH,
        vm_plugin.VmPlugin.KVM_ONLINE_INCREASE_MEMORY_PATH,
    ])
    def test_change_vm_cpu_mem(self):
        vm_uuid, vm = self._create_vm()

        mem_size = vm.memory + 33554432  # increase 32M
        cpu_num = vm.cpuNum + 1  # increase one cpu

        vm_utils.online_increase_mem(vm_uuid, mem_size)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        m_size = sizeunit.KiloByte.toByte(long(xml.memory.text_))
        self.assertEqual(mem_size, m_size, 'expect memory size[%s] but get %s' % (mem_size, m_size))

        vm_utils.online_increase_cpu(vm_uuid, cpu_num)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        n_cpu = int(xml.vcpu.current_)
        self.assertEqual(cpu_num, n_cpu, 'expect %s vcpu but get %s vcpu' % (n_cpu, cpu_num))

        self._destroy_vm(vm_uuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_GET_CONSOLE_PORT_PATH
    ])
    def test_get_vnc_port(self):
        vm_uuid, vm = self._create_vm()

        rsp = vm_utils.get_vnc_port(vm_uuid)
        self.assertEqual(5900, int(rsp.port), 'vnc port[%s] is not 5900' % rsp.port)

        self._destroy_vm(vm_uuid)

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_VM_SYNC_PATH
    ])
    def test_vm_sync(self):
        vm_uuid, vm = self._create_vm()

        rsp = vm_utils.vm_sync()
        states = rsp.states

        self.assertEqual(1, len(states))
        self.assertEqual(vm_plugin.Vm.VM_STATE_RUNNING, states[vm_uuid])

        self._destroy_vm(vm_uuid)

        rsp = vm_utils.vm_sync()
        states = rsp.states
        self.assertEqual(0, len(states))

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_ATTACH_VOLUME,
        vm_plugin.VmPlugin.KVM_DETACH_VOLUME,
        vm_plugin.VmPlugin.KVM_VM_CHECK_VOLUME_PATH,
    ])
    def test_attach_check_detach_volume(self):
        vm_uuid, vm = self._create_vm()

        vol_uuid, vol_path = volume_utils.create_empty_volume()
        _, vol = vm_utils.attach_volume_to_vm(vm_uuid, vol_uuid, vol_path)

        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, vol_path)
        self.assertIsNotNone(vol_xml)

        rsp = vm_utils.check_volume(vm_uuid, [vol])
        self.assertTrue(rsp.success)

        vm_utils.detach_volume_from_vm(vm_uuid, vol)
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, vol_path)
        self.assertIsNone(vol_xml)

        rsp = vm_utils.check_volume(vm_uuid, [vol])
        self.assertFalse(rsp.success)

        self._destroy_vm(vm_uuid)

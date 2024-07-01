from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import misc
from unittest import TestCase
from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import jsonobject
from zstacklib.utils.libvirt_singleton import LibvirtSingleton
import time
import mock

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
        vm_plugin.VmPlugin.KVM_VM_SYNC_PATH
    ])
    @pytest_utils.ztest_decorater
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

    def hang_virsh(self, cmd, pipe_fail=False):
        if "virsh" in cmd:
            return 1, "virsh hang"

        ret, o, _ = bash.bash_roe(cmd, pipe_fail=pipe_fail)
        return ret, o

    @pytest_utils.ztest_decorater
    def test_vm_sync_when_virsh_hang(self):
        vm_uuid, vm = self._create_vm()

        bash.bash_ro = mock.Mock(side_effect=self.hang_virsh)

        r, _ = bash.bash_ro("virsh list")
        self.assertEqual(1, r)

        rsp = vm_utils.vm_sync()
        states = rsp.states

        self.assertEqual(1, len(states))
        self.assertEqual(vm_plugin.Vm.VM_STATE_RUNNING, states[vm_uuid])

        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        linux.kill_process(pid)
        rsp = vm_utils.vm_sync()
        states = rsp.states
        self.assertEqual(0, len(states))

    @pytest_utils.ztest_decorater
    @bash.in_bash
    def test_vm_sync_when_vm_rebooted(self):
        vm = vm_utils.create_startvm_body_jsonobject()
        vm.bootDev = "cdrom"
        vm.rootVolume.bootOrder = None

        linux.qcow2_create("/root/.zguest/cdrom.qcow2", 1 * 1024 * 1024 * 1024)
        class CdromTO(object):
            def __init__(self):
                self.path = "/root/.zguest/cdrom.qcow2"
                self.deviceId = 0
                self.bootOrder = 1
                self.isEmpty = False
                self.type = None

        vm.cdRoms = [CdromTO()]

        vm_utils.create_vm(vm)
        vm_uuid = vm.vmInstanceUuid

        rsp = vm_utils.vm_sync()
        states = rsp.states

        self.assertEqual(1, len(states))
        self.assertEqual(vm_plugin.Vm.VM_STATE_RUNNING, states[vm_uuid])

        # mock put_vm_state_to_cache to check its called
        with mock.patch.object(vm_plugin, 'get_vm_states_from_cache') as get_vm_states_from_cache:
            rsp = vm_utils.vm_sync()
            states = rsp.states
            self.assertEqual(1, len(states))
            get_vm_states_from_cache.assert_called_once()

        with mock.patch.object(vm_plugin, 'put_vm_state_to_cache') as put_vm_state_to_cache:
            libvirt_singleton = LibvirtSingleton()
            conn = libvirt_singleton.conn
            domain = conn.lookupByName(vm_uuid)
            vm_utils.VM_PLUGIN.config[kvmagent.SEND_COMMAND_URL] = "http://localhost:7070"
            vm_utils.VM_PLUGIN._vm_reboot_event(conn, domain, None)

            # wait for put_vm_state_to_cache called
            for i in range(0, 10):
                try:
                    put_vm_state_to_cache.assert_called_once()
                except AssertionError:
                    time.sleep(1)
                    continue

                if put_vm_state_to_cache.call_args[0][1] == vm_plugin.Vm.VM_STATE_RUNNING:
                    break

            rsp = vm_utils.vm_sync()
            states = rsp.states
            self.assertEqual(1, len(states))
            put_vm_state_to_cache.assert_called_once()

        vm_utils.destroy_vm(vm_uuid)
        # recreate to let vm boot from cdrom again
        vm_utils.create_vm(vm)
        with mock.patch.object(vm_plugin, 'remove_vm_state_from_cache') as remove_vm_state_from_cache:
            libvirt_singleton = LibvirtSingleton()
            conn = libvirt_singleton.conn
            domain = conn.lookupByName(vm_uuid)
            vm_utils.VM_PLUGIN.config[kvmagent.SEND_COMMAND_URL] = "http://localhost:7070"
            vm_utils.VM_PLUGIN._vm_reboot_event(conn, domain, None)

            # wait for remove_vm_state_from_cache called
            for i in range(0, 10):
                try:
                    remove_vm_state_from_cache.assert_called_once()
                except AssertionError:
                    time.sleep(1)
                    continue

                if remove_vm_state_from_cache.call_args[0] == vm_uuid:
                    break

            rsp = vm_utils.vm_sync()
            states = rsp.states
            self.assertEqual(1, len(states))
            remove_vm_state_from_cache.assert_called_once()

        vm_plugin.put_vm_state_to_cache(vm_uuid, vm_plugin.Vm.VM_STATE_RUNNING)
        vm_utils.destroy_vm(vm_uuid)

        rsp = vm_utils.vm_sync()
        states = rsp.states
        self.assertEqual(1, len(states))
        self.assertEqual(vm_plugin.Vm.VM_STATE_RUNNING, states[vm_uuid])

        vm_plugin.remove_vm_state_from_cache(vm_uuid)
        rsp = vm_utils.vm_sync()
        states = rsp.states
        self.assertEqual(0, len(states))
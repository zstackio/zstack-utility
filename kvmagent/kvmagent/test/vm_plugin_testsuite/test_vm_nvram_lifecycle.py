import mock
from unittest import TestCase

from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils
from zstacklib.utils import http
from zstacklib.utils import jsonobject


class TestVmNvramLifecycle(TestCase):
    def test_stop_endpoint_accepts_missing_vm_nics(self):
        plugin = vm_plugin.VmPlugin()
        req = {http.REQUEST_BODY: jsonobject.dumps({
            'uuid': 'test-vm-uuid',
            'type': 'cold',
            'timeout': 5,
            'debug': False,
        })}

        with mock.patch.object(plugin, '_record_operation'), \
                mock.patch.object(plugin, '_stop_vm'):
            rsp = jsonobject.loads(plugin.stop_vm(req))

        self.assertTrue(rsp.success)

    def test_destroy_endpoint_accepts_missing_vm_nics(self):
        plugin = vm_plugin.VmPlugin()
        vm_uuid = 'test-vm-uuid'
        vm = mock.Mock()
        req = {http.REQUEST_BODY: jsonobject.dumps({'uuid': vm_uuid})}

        with mock.patch.object(plugin, '_record_operation'), \
                mock.patch.object(plugin, 'clean_vm_firmware_flash'), \
                mock.patch.object(vm_plugin, 'get_vm_by_uuid', return_value=vm), \
                mock.patch.object(vm_plugin.ovs, 'isVmUseOpenvSwitch', return_value=False):
            rsp = jsonobject.loads(plugin.destroy_vm(req))

        self.assertTrue(rsp.success)
        vm.destroy.assert_called_once_with()

    def test_start_keeps_existing_uefi_nvram(self):
        cmd = vm_utils.create_startvm_body_jsonobject()
        cmd.bootMode = 'UEFI'

        with mock.patch.object(vm_plugin.VmPlugin, 'clean_vm_firmware_flash') as clean_nvram:
            vm = vm_plugin.Vm.from_StartVmCmd(cmd)

        self.assertIn('/var/lib/libvirt/qemu/nvram/%s.fd' % cmd.vmInstanceUuid, vm.domain_xml)
        clean_nvram.assert_not_called()

    def test_start_keeps_nvram_when_cleaning_stale_domain(self):
        plugin = vm_plugin.VmPlugin()
        cmd = vm_utils.create_startvm_body_jsonobject()
        stale_vm = mock.Mock()
        stale_vm.state = vm_plugin.Vm.VM_STATE_SHUTDOWN
        new_vm = mock.Mock()

        with mock.patch.object(vm_plugin, 'get_vm_by_uuid_no_retry', return_value=stale_vm), \
                mock.patch.object(vm_plugin.Vm, 'from_StartVmCmd', return_value=new_vm), \
                mock.patch.object(plugin, '_prepare_ebtables_for_mocbr'):
            plugin._start_vm(cmd)

        stale_vm.stop.assert_called_once_with(strategy='cold')
        stale_vm.destroy.assert_not_called()

    def test_stop_and_destroy_use_different_nvram_flags(self):
        keep_nvram = 1 << 20
        remove_nvram = 1 << 21

        with mock.patch.object(vm_plugin.libvirt, 'VIR_DOMAIN_UNDEFINE_KEEP_NVRAM', keep_nvram, create=True), \
                mock.patch.object(vm_plugin.libvirt, 'VIR_DOMAIN_UNDEFINE_NVRAM', remove_nvram, create=True):
            stop_flags = vm_plugin.Vm._get_undefine_flags(True)
            destroy_flags = vm_plugin.Vm._get_undefine_flags(False)

        self.assertTrue(stop_flags & keep_nvram)
        self.assertFalse(stop_flags & remove_nvram)
        self.assertTrue(destroy_flags & remove_nvram)
        self.assertFalse(destroy_flags & keep_nvram)

    def test_destroy_removes_nvram(self):
        vm = vm_plugin.Vm()
        vm.stop = mock.Mock()

        vm.destroy()

        vm.stop.assert_called_once_with(strategy='cold', keep_nvram=False)

    def test_destroy_endpoint_cleans_nvram_after_vm_was_stopped(self):
        plugin = vm_plugin.VmPlugin()
        vm_uuid = 'test-vm-uuid'
        req = {http.REQUEST_BODY: jsonobject.dumps({'uuid': vm_uuid})}

        with mock.patch.object(plugin, '_record_operation'), \
                mock.patch.object(plugin, 'clean_vm_firmware_flash') as clean_nvram, \
                mock.patch.object(vm_plugin, 'get_vm_by_uuid', return_value=None):
            rsp = jsonobject.loads(plugin.destroy_vm(req))

        self.assertTrue(rsp.success)
        clean_nvram.assert_called_once_with(vm_uuid)

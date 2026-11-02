import ast
import re
import json
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace, MethodType
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'kvmagent/kvmagent/plugins/vm_plugin.py'


def method(name, namespace):
    match = re.search(r'^    def ' + name + r'\(.*?(?=^    (?:def |@)|\Z)',
                      SOURCE.read_text(), re.M | re.S)
    if match is None:
        raise AssertionError('missing method: ' + name)
    exec(compile(ast.parse(textwrap.dedent(match.group())), str(SOURCE), 'exec'), namespace)
    return namespace[name]


class LibvirtError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code

    def get_error_code(self):
        return self.code


class KvmError(Exception):
    pass


class StopCompletionTest(unittest.TestCase):
    def setUp(self):
        self.linux = MagicMock()
        self.linux.wait_callback_success.side_effect = lambda callback, data, **kwargs: callback(data)
        self.ns = {'libvirt': SimpleNamespace(libvirtError=LibvirtError, VIR_ERR_NO_DOMAIN=42),
                   'linux': self.linux, 'logger': MagicMock(),
                   'kvmagent': SimpleNamespace(KvmError=KvmError)}
        self.vm = MagicMock()
        self.vm.uuid = 'test-vm'
        self.vm.VIR_DOMAIN_SHUTOFF = 5
        self.vm.VM_STATE_SHUTDOWN = 'Shutdown'
        self.vm.domain.info.return_value = (4, 0, 0, 0, 0)
        self.vm.domain.isPersistent.return_value = False
        self.vm.domain_xmlobject.devices.get_child_node_as_list.return_value = []
        self.vm.wait_for_state_change.return_value = True
        self.stop = method('stop', self.ns)

    def power_check(self):
        return method('is_powered_off', self.ns)(self.vm)

    def bind_power_check(self):
        self.vm.is_powered_off.side_effect = self.power_check

    def test_shutdown_is_not_powered_off(self):
        self.assertFalse(self.power_check())

    def test_shutoff_and_missing_domain_are_powered_off(self):
        self.vm.domain.info.return_value = (5, 0, 0, 0, 0)
        self.assertTrue(self.power_check())
        self.vm.domain.info.side_effect = LibvirtError('gone', 42)
        self.assertTrue(self.power_check())

    def test_unknown_libvirt_error_is_not_success(self):
        self.vm.domain.info.side_effect = LibvirtError('connection lost')
        with self.assertRaises(LibvirtError):
            self.power_check()

    def test_grace_stop_destroys_domain_still_shutting_down(self):
        self.bind_power_check()
        self.vm.domain.destroy.side_effect = lambda: setattr(
            self.vm.domain.info, 'return_value', (5, 0, 0, 0, 0))
        self.stop(self.vm)
        self.vm.domain.destroy.assert_called_once_with()

    def test_grace_stop_does_not_destroy_powered_off_domain(self):
        self.bind_power_check()
        self.vm.domain.info.return_value = (5, 0, 0, 0, 0)
        self.stop(self.vm)
        self.vm.domain.destroy.assert_not_called()

    def test_failed_destroy_cannot_be_reported_as_stopped(self):
        self.bind_power_check()
        self.vm.domain.destroy.side_effect = LibvirtError('still busy')
        with self.assertRaises(KvmError):
            self.stop(self.vm, strategy='cold')

    def test_transient_undefine_falls_back_to_destroy(self):
        self.bind_power_check()
        self.vm.domain.info.return_value = (5, 0, 0, 0, 0)
        self.vm.domain.isPersistent.return_value = True
        self.vm.domain.undefineFlags.side_effect = LibvirtError('cannot undefine transient domain')
        self.stop(self.vm, strategy='cold')
        self.assertEqual(2, self.vm.domain.destroy.call_count)
        self.vm.domain.undefine.assert_not_called()

    def test_transient_destroy_failure_is_not_success(self):
        self.bind_power_check()
        self.vm.domain.isPersistent.return_value = True
        self.vm.domain.undefineFlags.side_effect = LibvirtError('cannot undefine transient domain')
        self.vm.domain.destroy.side_effect = LibvirtError('device busy')
        with self.assertRaises(KvmError):
            self.stop(self.vm, strategy='soft')

    def test_repeated_stop_succeeds_after_domain_disappears(self):
        self.bind_power_check()
        self.vm.domain.info.side_effect = LibvirtError('gone', 42)
        self.vm.domain.shutdown.side_effect = LibvirtError('gone', 42)
        self.stop(self.vm)
        self.stop(self.vm)
        self.vm.domain.destroy.assert_not_called()

    def test_stop_handler_reports_error_after_cleanup(self):
        vm = MagicMock()
        vm.stop.side_effect = KvmError('stop timed out')
        self.ns.update(get_vm_by_uuid=MagicMock(return_value=vm), ovs=MagicMock(),
                       jsonobject=SimpleNamespace(loads=lambda value: value,
                                                  dumps=lambda value: json.dumps(vars(value))),
                       http=SimpleNamespace(REQUEST_BODY='body'),
                       StopVmResponse=lambda: SimpleNamespace(success=True))
        plugin = MagicMock()
        plugin._stop_vm = MethodType(method('_stop_vm', self.ns), plugin)
        cmd = SimpleNamespace(uuid='test-vm', type='cold', timeout=120, debug=False, vmNics=[])
        result = json.loads(method('stop_vm', self.ns)(plugin, {'body': cmd}))
        self.assertFalse(result['success'])
        self.assertIn('stop timed out', result['error'])
        plugin.kill_vm.assert_called_once_with('test-vm')

    def test_stop_failure_propagates_after_final_cleanup(self):
        vm = MagicMock()
        vm.stop.side_effect = KvmError('stop timed out')
        self.ns.update(get_vm_by_uuid=MagicMock(return_value=vm), ovs=MagicMock())
        plugin = MagicMock()
        cmd = SimpleNamespace(uuid='test-vm', type='cold', timeout=120)
        with self.assertRaisesRegex(KvmError, 'stop timed out'):
            method('_stop_vm', self.ns)(plugin, cmd)
        plugin.kill_vm.assert_called_once_with('test-vm')


if __name__ == '__main__':
    unittest.main()

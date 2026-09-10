import ast
import os
import unittest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
VM_PLUGIN = 'kvmagent/kvmagent/plugins/vm_plugin.py'


def load_definition(path, class_name, namespace, method_name=None):
    with open(os.path.join(REPO_ROOT, path)) as source:
        module = ast.parse(source.read(), filename=path)
    classes = [node for node in module.body if isinstance(node, ast.ClassDef) and node.name == class_name]
    if len(classes) != 1:
        raise AssertionError('expected exactly one class: ' + class_name)
    node = classes[0]
    if method_name:
        methods = [item for item in node.body if isinstance(item, ast.FunctionDef) and item.name == method_name]
        if len(methods) != 1:
            raise AssertionError('expected exactly one method: ' + method_name)
        node = methods[0]
    module.body = [node]
    eval(compile(module, path, 'exec'), namespace)
    return namespace[method_name or class_name]


KvmError = load_definition('kvmagent/kvmagent/kvmagent.py', 'KvmError', {})
ShellError = load_definition('zstacklib/zstacklib/utils/shell.py', 'ShellError', {})


class Boundary(object):
    def __init__(self, **values):
        self.__dict__.update(values)


class LibvirtError(Exception):
    pass


class StartVmRunningTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.pid = '970596'
        self.stale_pid = ''
        self.xml_exists = False
        self.pid_error = None
        self.destroy_error = None
        self.cmd = Boundary(vmInstanceUuid='4519defc71ce4d9ba12b7caeb6891a1e', vmName='test_vm_default_name',
                            memorySnapshotPath=None, addons=None, timeout=60, createPaused=False, nics=[])
        self.old_vm = Boundary(state='Running', get_name=lambda: self.cmd.vmName, destroy=self.destroy)
        self.new_vm = Boundary(start=self.start)
        self.plugin = Boundary(_prepare_ebtables_for_mocbr=lambda cmd: self.events.append(('prepare', cmd)))
        namespace = {
            'get_vm_by_uuid_no_retry': self.lookup,
            'Vm': Boundary(VM_STATE_RUNNING='Running', from_StartVmCmd=self.factory),
            'linux': Boundary(find_vm_pid_by_uuid=self.find_pid, get_vm_pid=self.read_pid_file),
            'libvirt': Boundary(libvirtError=LibvirtError),
            'kvmagent': Boundary(KvmError=KvmError),
            'logger': Boundary(debug=lambda message: None),
            'os': Boundary(path=Boundary(exists=lambda path: self.xml_exists, join=os.path.join)),
            'LIBVIRT_DEFINED_XML_DIR': '/etc/libvirt/qemu/',
            'shell': Boundary(run=lambda cmd: self.events.append(('undefine', cmd))),
        }
        self.start_vm = load_definition(VM_PLUGIN, 'VmPlugin', namespace, '_start_vm')

    def lookup(self, uuid, exception_on_missing):
        self.events.append(('lookup', uuid, exception_on_missing))
        return self.old_vm

    def find_pid(self, uuid):
        self.events.append(('pid', uuid))
        if self.pid_error:
            raise self.pid_error
        return self.pid

    def read_pid_file(self, uuid):
        self.events.append(('pid_file', uuid))
        return self.stale_pid

    def destroy(self):
        self.events.append(('destroy',))
        if self.destroy_error:
            raise self.destroy_error

    def factory(self, cmd):
        self.events.append(('factory', cmd))
        return self.new_vm

    def start(self, timeout, create_paused, wait_console):
        self.events.append(('start', timeout, create_paused, wait_console))

    def run_start(self):
        return self.start_vm(self.plugin, self.cmd)

    def lookup_events(self, check_pid=True):
        events = [('lookup', self.cmd.vmInstanceUuid, False)]
        if check_pid:
            events.append(('pid', self.cmd.vmInstanceUuid))
        return events

    def start_events(self):
        return [('factory', self.cmd), ('prepare', self.cmd), ('start', 60, False, True)]

    def test_running_with_process_is_idempotent(self):
        self.run_start()
        self.assertEqual(self.lookup_events(), self.events)

    def test_running_without_process_cleans_domain_before_starting(self):
        self.pid = ''
        self.run_start()
        self.assertEqual(self.lookup_events() + [('destroy',)] + self.start_events(), self.events)

    def test_stale_pid_file_cannot_suppress_recovery(self):
        self.pid = ''
        self.stale_pid = '970596'
        self.xml_exists = True
        self.run_start()
        expected = [('pid_file', self.cmd.vmInstanceUuid)] + self.lookup_events()
        self.assertEqual(expected + [('destroy',)] + self.start_events(), self.events)

    def test_missing_domain_starts_without_cleanup(self):
        self.old_vm = None
        self.run_start()
        self.assertEqual(self.lookup_events(False) + self.start_events(), self.events)

    def test_non_running_domain_keeps_existing_destroy_path(self):
        self.old_vm.state = 'Shutdown'
        self.run_start()
        self.assertEqual(self.lookup_events(False) + [('destroy',)] + self.start_events(), self.events)

    def test_cleanup_failure_propagates_without_creating_vm(self):
        self.pid = ''
        self.destroy_error = KvmError('domain cleanup timed out')
        with self.assertRaises(KvmError) as raised:
            self.run_start()
        self.assertIs(self.destroy_error, raised.exception)
        self.assertEqual(self.lookup_events() + [('destroy',)], self.events)

    def test_retry_recovers_after_cleanup_failure(self):
        self.pid = ''
        self.destroy_error = KvmError('domain cleanup timed out')
        with self.assertRaises(KvmError):
            self.run_start()
        self.assertEqual(self.lookup_events() + [('destroy',)], self.events)
        self.destroy_error = None
        del self.events[:]
        self.run_start()
        self.assertEqual(self.lookup_events() + [('destroy',)] + self.start_events(), self.events)

    def test_pid_query_error_does_not_authorize_cleanup(self):
        self.pid_error = ShellError('process query failed')
        with self.assertRaises(ShellError) as raised:
            self.run_start()
        self.assertIs(self.pid_error, raised.exception)
        self.assertEqual(self.lookup_events(), self.events)


if __name__ == '__main__':
    unittest.main(verbosity=2)

import ast
import json
import os
import unittest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
VM_PLUGIN = 'kvmagent/kvmagent/plugins/vm_plugin.py'


def load_method(path, class_name, method_name, namespace):
    with open(os.path.join(REPO_ROOT, path)) as source:
        module = ast.parse(source.read(), filename=path)
    owner = [node for node in module.body if isinstance(node, ast.ClassDef) and node.name == class_name][0]
    method = [item for item in owner.body if isinstance(item, ast.FunctionDef) and item.name == method_name][0]
    module.body = [method]
    eval(compile(module, path, 'exec'), namespace)
    return namespace[method_name]


class KvmError(Exception):
    pass


class Boundary(object):
    def __init__(self, **values):
        self.__dict__.update(values)


class VmLifecycleWithoutNicsTest(unittest.TestCase):
    """Directly-destroy and some stop requests carry no vmNics; the domain is already gone by then, so the reply must succeed."""

    def setUp(self):
        self.events = []
        self.vm = Boundary(destroy=lambda: self.events.append('destroy'))
        namespace = {
            'kvmagent': Boundary(replyerror=lambda handler: handler, KvmError=KvmError),
            'jsonobject': Boundary(loads=self.loads, dumps=lambda rsp: rsp),
            'http': Boundary(REQUEST_BODY='body'),
            'DestroyVmResponse': lambda: Boundary(success=True, error=None),
            'StopVmResponse': lambda: Boundary(success=True, error=None),
            'get_vm_by_uuid': lambda uuid, exception_on_missing: self.vm,
            'ovs': Boundary(isVmUseOpenvSwitch=lambda uuid: False),
            'delVnicFromOvsByVmUuidIfExist': lambda uuid: None,
            'notify_vrouter': lambda cmd: self.events.append(('vrouter', cmd)),
            'transform_to_tf_uuid': lambda uuid: 'tf-' + uuid,
            'logger': Boundary(debug=lambda message: None, warn=lambda message: None),
            'linux': Boundary(get_exception_stacktrace=lambda: ''),
        }
        self.destroy_vm = load_method(VM_PLUGIN, 'VmPlugin', 'destroy_vm', namespace)
        self.stop_vm = load_method(VM_PLUGIN, 'VmPlugin', 'stop_vm', namespace)
        self.plugin = Boundary(_record_operation=lambda uuid, op: None, VM_OP_DESTROY='destroy', VM_OP_STOP='stop',
                               _stop_vm=lambda cmd: self.events.append('stop'), _dump=lambda uuid: None)

    def loads(self, body):
        values = json.loads(body)
        nics = values.get('vmNics')
        return Boundary(uuid=values['uuid'], debug=values.get('debug', False),
                        vmNics=None if nics is None else [Boundary(**nic) for nic in nics])

    def run_destroy(self, body):
        return self.destroy_vm(self.plugin, {'body': json.dumps(body)})

    def test_directly_destroy_without_nics_succeeds(self):
        rsp = self.run_destroy({'uuid': '164ca253505549f89350b619c362b114'})
        self.assertTrue(rsp.success)
        self.assertEqual(['destroy'], self.events)

    def test_stop_without_nics_succeeds(self):
        rsp = self.stop_vm(self.plugin, {'body': json.dumps({'uuid': '0b42630f37d8417480eced62ad89719f', 'type': 'cold'})})
        self.assertTrue(rsp.success)
        self.assertEqual(['stop'], self.events)

    def test_tf_nics_still_notify_vrouter(self):
        rsp = self.run_destroy({'uuid': 'a' * 32, 'vmNics': [{'type': 'TFVNIC', 'uuid': 'nic'}, {'type': 'VNIC', 'uuid': 'other'}]})
        self.assertTrue(rsp.success)
        self.assertEqual('destroy', self.events[0])
        self.assertEqual(1, len([event for event in self.events if event[0] == 'vrouter']))


if __name__ == '__main__':
    unittest.main()

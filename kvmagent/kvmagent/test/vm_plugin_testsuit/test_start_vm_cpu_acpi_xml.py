import ast
import imp
import json
import os
import unittest

from zstacklib.utils import jsonobject

if os.environ.get('VM_PLUGIN_UNDER_TEST'):
    vm_plugin = imp.load_source('vm_plugin_under_test', os.environ['VM_PLUGIN_UNDER_TEST'])
else:
    from kvmagent.plugins import vm_plugin

etree = vm_plugin.etree


class FixtureEnvironment(object):
    VM_IMAGE_PATH = '/tmp/test-start-vm.qcow2'
    DEFAULT_ETH_INTERFACE_NAME = 'eth0'


class FakeConnection(object):
    def __init__(self, cells):
        self.cells = cells

    def getCapabilities(self):
        return '<capabilities><host><topology><cells num="%s"/></topology></host></capabilities>' % self.cells


class TestStartVmCpuAcpiXml(unittest.TestCase):
    def setUp(self):
        self.originals = []
        self.addCleanup(self.restore)
        fixture_path = os.path.join(os.path.dirname(__file__), '../utils/vm_utils.py')
        fixture_path = os.environ.get('START_VM_FIXTURE', fixture_path)
        with open(fixture_path) as fixture:
            assignments = ast.parse(fixture.read()).body
        expression = next(node.value for node in assignments
                          if isinstance(node, ast.Assign) and
                          any(isinstance(target, ast.Name) and target.id == 'startVmCmdBody'
                              for target in node.targets))
        self.body = eval(compile(ast.Expression(expression), fixture_path, 'eval'),
                         {'env': FixtureEnvironment})
        self.body.update({'bootMode': 'UEFI', 'machineType': 'virt', 'cpuNum': 2,
                          'maxVcpuNum': 8, 'acpi': True, 'nics': [], 'threadsPerCore': 1,
                          'pciePortNums': 0, 'predefinedPciBridgeNum': 0})
        self.patch(vm_plugin, 'HOST_ARCH', 'aarch64')
        self.patch(vm_plugin, 'DIST_NAME_VERSION', 'unsupported-host-os')
        self.patch(vm_plugin, 'is_virtual_machine', lambda: False)
        self.patch(vm_plugin, 'get_gic_version', lambda cpu: None)
        self.patch(vm_plugin.VmPlugin, 'clean_vm_firmware_flash', staticmethod(lambda cmd: None))
        self.patch(vm_plugin.os.path, 'exists', lambda path: True)
        self.patch(vm_plugin.linux, 'get_img_fmt', lambda path: 'qcow2')
        self.patch(vm_plugin.LibvirtAutoReconnect, 'conn', FakeConnection(1))

    def patch(self, obj, name, value):
        original = obj.__dict__[name] if isinstance(obj, type) else getattr(obj, name)
        self.originals.append((obj, name, original))
        setattr(obj, name, value)

    def restore(self):
        for obj, name, original in reversed(self.originals):
            setattr(obj, name, original)

    def build_xml(self):
        cmd = jsonobject.loads(json.dumps({key: value for key, value in self.body.items()
                                         if value is not None}))
        return etree.fromstring(vm_plugin.Vm.from_StartVmCmd(cmd).domain_xml)

    def test_acpi_on_arm_without_host_whitelist(self):
        assert self.build_xml().find('features/acpi') is not None

    def test_acpi_on_nested_arm(self):
        self.patch(vm_plugin, 'is_virtual_machine', lambda: True)
        assert self.build_xml().find('features/acpi') is not None

    def test_acpi_explicitly_disabled_on_arm(self):
        self.body['acpi'] = False
        assert self.build_xml().find('features/acpi') is None

    def test_acpi_default_enabled_on_x86(self):
        self.patch(vm_plugin, 'HOST_ARCH', 'x86_64')
        self.body['machineType'] = 'pc'
        assert self.build_xml().find('features/acpi') is not None

    def test_acpi_explicitly_disabled_on_x86(self):
        self.patch(vm_plugin, 'HOST_ARCH', 'x86_64')
        self.body.update({'machineType': 'pc', 'acpi': False})
        assert self.build_xml().find('features/acpi') is None

    def test_arm_hotplug_capacity_uses_gic3(self):
        gic = self.build_xml().find('features/gic')
        assert gic is not None and gic.get('version') == '3'

    def test_arm_without_hotplug_capacity_keeps_default_gic(self):
        self.body.update({'maxVcpuNum': 2, 'socketNum': 1, 'cpuOnSocket': 2})
        assert self.build_xml().find('features/gic') is None

    def test_arm_without_acpi_keeps_default_gic(self):
        self.body['acpi'] = False
        assert self.build_xml().find('features/gic') is None

    def test_arm_without_numa_keeps_default_gic(self):
        self.body['useNuma'] = False
        assert self.build_xml().find('features/gic') is None

    def test_arm_legacy_gic2_override_is_preserved(self):
        self.patch(vm_plugin, 'get_gic_version', lambda cpu: 2)
        assert self.build_xml().find('features/gic').get('version') == '2'

    def check_topology(self, nested, maximum, cells, sockets, cores, expected):
        self.patch(vm_plugin, 'is_virtual_machine', lambda: nested)
        self.patch(vm_plugin.LibvirtAutoReconnect, 'conn', FakeConnection(cells))
        self.body.update({'maxVcpuNum': maximum, 'socketNum': sockets, 'cpuOnSocket': cores})
        root = self.build_xml()
        vcpu = root.find('vcpu')
        topology = root.find('cpu/topology')
        assert int(vcpu.text) == expected
        assert int(vcpu.get('current')) == 2
        assert (int(topology.get('sockets')) * int(topology.get('cores')) *
                int(topology.get('threads'))) == expected
        assert root.find('cpu/numa/cell').get('cpus') == '0-%d' % (expected - 1)
        if sockets and maximum == expected:
            assert int(topology.get('sockets')) == sockets
            assert int(topology.get('cores')) == cores

    def test_arm_default_topology(self):
        self.check_topology(False, 8, 1, None, None, 8)

    def test_arm_non_divisible_host_cells(self):
        self.check_topology(False, 8, 3, None, None, 8)

    def test_arm_host_cells_above_maximum(self):
        self.check_topology(False, 8, 16, None, None, 8)

    def test_arm_explicit_topology(self):
        self.check_topology(False, 8, 1, 2, 4, 8)

    def test_nested_arm_maximum_cap(self):
        self.check_topology(True, 128, 1, None, None, 8)

    def test_nested_arm_explicit_topology_cap(self):
        self.check_topology(True, 128, 1, 32, 4, 8)

    def test_nested_arm_smaller_explicit_maximum(self):
        self.check_topology(True, 4, 1, 2, 2, 4)

    def test_nested_arm_current_cpu_above_cap(self):
        self.patch(vm_plugin, 'is_virtual_machine', lambda: True)
        self.body.update({'cpuNum': 16, 'maxVcpuNum': 128})
        with self.assertRaises(vm_plugin.kvmagent.KvmError):
            self.build_xml()


if __name__ == '__main__':
    unittest.main()

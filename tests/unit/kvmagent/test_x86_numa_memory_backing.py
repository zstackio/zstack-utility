import ast
import base64
import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree as ET

import pytest

from kvmagent.plugins import vm_plugin
from tests.unit.kvmagent.test_vm_plugin_handlers import TestVmStartCmdXmlBuild as _XmlBuilder


@pytest.fixture(autouse=True)
def default_emulator_version(monkeypatch):
    monkeypatch.setattr(vm_plugin.qemu, 'get_version_from_exe_file2',
                        lambda *args, **kwargs: vm_plugin.qemu.get_version())


@pytest.mark.parametrize('machine_type', ['pc', 'q35'])
@pytest.mark.parametrize('qemu_version,libvirt_version,use_numa,expected', [
    ('5.0.1', '8.0.0', True, False),
    ('6.2.0', '1.0.5', True, False),
    ('5.1.0', '1.0.6', True, True),
    ('6.2.0', '8.0.0', True, True),
    ('8.2.0', '10.0.0', True, True),
    ('6.2.0', '8.0.0', False, False),
])
def test_x86_numa_memory_backend(machine_type, qemu_version, libvirt_version, use_numa, expected):
    builder = _XmlBuilder()
    cmd = builder._build_start_cmd(use_numa=use_numa)
    cmd.machineType = machine_type
    cmd.MemAccess = 'private'
    cmd.useHugePage = False
    cmd.noSharePages = False
    if not use_numa:
        cmd.addons.numaNodes = []

    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value=qemu_version), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value=libvirt_version):
        root = ET.fromstring(builder._build_start_vm_xml(cmd))

    assert (root.find('./cpu/numa/cell') is not None) is use_numa
    if expected:
        access = root.find('./memoryBacking/access')
        assert access is not None
        assert access.get('mode') == 'private'
        assert root.find('./memoryBacking/source') is None
    else:
        assert root.find('./memoryBacking') is None


@pytest.mark.parametrize('hugepages,access', [(True, 'private'), (False, 'shared'), (True, 'shared')])
@pytest.mark.parametrize('qemu_version', ['5.0.1', '6.2.0'])
def test_x86_numa_preserves_existing_memory_backing(hugepages, access, qemu_version):
    builder = _XmlBuilder()
    cmd = builder._build_start_cmd(use_numa=True)
    cmd.MemAccess = access
    cmd.useHugePage = hugepages
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value=qemu_version), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='8.0.0'):
        root = ET.fromstring(builder._build_start_vm_xml(cmd))

    assert (root.find('./memoryBacking/hugepages') is not None) is hugepages
    accesses = root.findall('./memoryBacking/access')
    assert len(accesses) == (1 if access == 'shared' else 0)
    if access == 'shared':
        assert accesses[0].get('mode') == 'shared'
        assert root.find('./memoryBacking/source').get('type') == 'memfd'


def test_x86_numa_preserves_shared_memory_on_older_libvirt():
    builder = _XmlBuilder()
    cmd = builder._build_start_cmd(use_numa=True)
    cmd.MemAccess = 'shared'
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value='6.2.0'), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='4.9.0'):
        root = ET.fromstring(builder._build_start_vm_xml(cmd))
    assert root.find('./memoryBacking/access').get('mode') == 'shared'
    assert root.find('./memoryBacking/source').get('type') == 'memfd'


@pytest.mark.parametrize('backing', ['', '<memoryBacking><nosharepages/></memoryBacking>'])
def test_x86_reboot_repairs_existing_numa_xml(backing):
    vm = vm_plugin.Vm()
    vm.domain_xml = ('<domain><os><type>hvm</type><boot dev="hd"/></os>'
                     '<cpu><numa><cell id="0" cpus="0" memory="524288"/></numa></cpu>'
                     + backing + '<devices/></domain>')
    vm.domain_xmlobject = MagicMock()
    vm.domain_xmlobject.dump.return_value = vm.domain_xml
    vm.stop = MagicMock()
    vm._wait_for_vm_running = MagicMock()
    connection = MagicMock()

    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value='6.2.0'), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='8.0.0'), \
            patch.object(vm_plugin, 'LibvirtAutoReconnect', side_effect=lambda fn: lambda: fn(connection)):
        vm.reboot(SimpleNamespace(timeout=5, bootDev=['hd']))

    root = ET.fromstring(connection.defineXML.call_args.args[0])
    access = root.find('./memoryBacking/access')
    assert access is not None
    assert access.get('mode') == 'private'
    assert (root.find('./memoryBacking/nosharepages') is not None) is bool(backing)
    connection.defineXML.return_value.createWithFlags.assert_called_once()


@pytest.mark.parametrize('arch,qemu_version,cpu,backing', [
    ('x86_64', '6.2.0', '<cpu/>', ''),
    ('x86_64', '5.0.1', '<cpu><numa><cell/></numa></cpu>', ''),
    ('aarch64', '6.2.0', '<cpu><numa><cell/></numa></cpu>', ''),
    ('x86_64', '6.2.0', '<cpu><numa><cell memAccess="shared"/></numa></cpu>', ''),
    ('x86_64', '6.2.0', '<cpu><numa><cell/></numa></cpu>', '<memoryBacking><access mode="shared"/></memoryBacking>'),
    ('x86_64', '6.2.0', '<cpu><numa><cell/></numa></cpu>', '<memoryBacking><access mode="private"/></memoryBacking>'),
    ('x86_64', '6.2.0', '<cpu><numa><cell/></numa></cpu>', '<memoryBacking><source type="file"/></memoryBacking>'),
    ('x86_64', '6.2.0', '<cpu><numa><cell/></numa></cpu>', '<memoryBacking><hugepages/></memoryBacking>'),
])
def test_x86_start_preserves_existing_memory_contract(arch, qemu_version, cpu, backing):
    root = ET.fromstring('<domain>' + cpu + backing + '<devices/></domain>')
    original = ET.tostring(root)
    with patch.object(vm_plugin, 'HOST_ARCH', arch), \
            patch.object(vm_plugin.qemu, 'get_version', return_value=qemu_version), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='8.0.0'):
        assert not vm_plugin.Vm._ensure_x86_numa_memory_backing(root)
    assert ET.tostring(root) == original


def _vm_from_start_cmd(cmd):
    built = []
    build = vm_plugin.Vm.from_StartVmCmd

    def capture(command):
        vm = build(command)
        built.append(vm)
        return vm

    with patch.object(vm_plugin.Vm, 'from_StartVmCmd', side_effect=capture):
        _XmlBuilder()._build_start_vm_xml(cmd)
    return built[0]


def _user_numa_xml(backing=''):
    return ('<domain><name>vm-uuid</name><uuid>vm-uuid</uuid><vcpu>1</vcpu>'
            '<cpu mode="host-passthrough"><numa>'
            '<cell id="0" cpus="0" memory="524288"/></numa></cpu>'
            + backing + '<devices><emulator>/opt/review-qemu/qemu-system-x86_64</emulator>'
            '</devices></domain>')


def _start_vm(vm, connection):
    with patch.object(vm_plugin, 'LibvirtAutoReconnect', side_effect=lambda fn: lambda: fn(connection)), \
            patch.object(vm, '_wait_for_vm_running'):
        vm.start(wait_console=False)
    return ET.fromstring(connection.defineXML.call_args.args[0])


def test_user_private_backing_cannot_be_removed_to_restore_legacy_snapshot():
    cmd = _XmlBuilder()._build_start_cmd(use_numa=True)
    cmd.MemAccess = 'private'
    cmd.useHugePage = False
    cmd.noSharePages = False
    cmd.memorySnapshotPath = '/owned-snapshot.save'
    cmd.addons.userDefinedXml = base64.b64encode(_user_numa_xml(
        '<memoryBacking><access mode="private"/></memoryBacking>').encode()).decode()
    connection = MagicMock()
    connection.saveImageGetXMLDesc.return_value = _user_numa_xml()
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value='6.2.0'), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='8.0.0'):
        vm = _vm_from_start_cmd(cmd)
        original = vm.domain_xml
        with patch.object(vm_plugin, 'LibvirtAutoReconnect', side_effect=lambda fn: lambda *args: fn(connection, *args)), \
                pytest.raises(vm_plugin.kvmagent.KvmError, match='(?i)memory|backing|snapshot|private'):
            vm.restore(cmd.memorySnapshotPath)
    assert vm.domain_xml == original
    connection.defineXML.assert_not_called()
    connection.restoreFlags.assert_not_called()


@pytest.mark.parametrize('host_version,selected_version,expected', [
    ('4.2.0', '6.2.0', True),
    ('6.2.0', '4.2.0', False),
])
def test_numa_backing_uses_the_selected_emulator(host_version, selected_version, expected):
    cmd = _XmlBuilder()._build_start_cmd(use_numa=True)
    cmd.MemAccess = 'private'
    cmd.useHugePage = False
    cmd.noSharePages = False
    cmd.addons.userDefinedXml = base64.b64encode(_user_numa_xml().encode()).decode()
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value=host_version), \
            patch.object(vm_plugin.qemu, 'get_version_from_exe_file2', return_value=selected_version), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='8.0.0'):
        vm = _vm_from_start_cmd(cmd)
        root = _start_vm(vm, MagicMock())
    assert root.findtext('devices/emulator') == '/opt/review-qemu/qemu-system-x86_64'
    assert (root.find('./memoryBacking/access') is not None) is expected
    if expected:
        assert root.find('./memoryBacking/access').get('mode') == 'private'


@pytest.mark.parametrize('host_version,selected_version,expected', [
    ('4.2.0', '6.2.0', True),
    ('6.2.0', '4.2.0', False),
])
def test_numa_backing_uses_the_final_hook_emulator(host_version, selected_version, expected):
    selected_path = '/opt/review-qemu/qemu-system-x86_64'
    cmd = _XmlBuilder()._build_start_cmd(use_numa=True)
    cmd.MemAccess = 'private'
    cmd.useHugePage = False
    cmd.noSharePages = False
    cmd.addons.userDefinedXmlHookScript = base64.b64encode(b'select-emulator').decode()

    def select_emulator(script, xml):
        assert script == 'select-emulator'
        root = ET.fromstring(xml)
        root.find('devices/emulator').text = selected_path
        return ET.tostring(root, encoding='unicode')

    def emulator_version(path, **kwargs):
        return selected_version if shlex.split(path) == [selected_path] else host_version

    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value=host_version), \
            patch.object(vm_plugin.qemu, 'get_version_from_exe_file2', side_effect=emulator_version), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='8.0.0'), \
            patch.object(vm_plugin.xmlhook, 'get_modified_xml_from_hook', side_effect=select_emulator) as hook:
        vm = _vm_from_start_cmd(cmd)
        root = _start_vm(vm, MagicMock())
    assert root.findtext('devices/emulator') == selected_path
    assert (root.find('./memoryBacking/access') is not None) is expected
    if expected:
        assert root.find('./memoryBacking/access').get('mode') == 'private'
    hook.assert_called_once()


@pytest.mark.parametrize('saved_backing,keep_private', [
    ('', False),
    ('<source type="anonymous"/>', False),
    ('<access mode="private"/>', True),
    ('<source type="anonymous"/><access mode="private"/>', True),
    ('<source type="file"/>', True),
    ('<source type="memfd"/>', True),
    ('<hugepages/>', True),
])
def test_raw_xml_restores_old_and_new_snapshot_backends(saved_backing, keep_private):
    cmd = _XmlBuilder()._build_start_cmd(use_numa=True)
    cmd.MemAccess = 'private'
    cmd.useHugePage = False
    cmd.noSharePages = False
    cmd.memorySnapshotPath = '/owned-snapshot.save'
    cmd.addons.userDefinedXml = base64.b64encode(_user_numa_xml().encode()).decode()
    cmd.addons.userDefinedXmlHookScript = base64.b64encode(b'must-not-run-on-restore').decode()
    connection = MagicMock()
    connection.saveImageGetXMLDesc.return_value = _user_numa_xml(
        '<memoryBacking>%s</memoryBacking>' % saved_backing if saved_backing else ''
    )
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value='6.2.0'), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='8.0.0'), \
            patch.object(vm_plugin.xmlhook, 'get_modified_xml_from_hook') as hook:
        vm = _vm_from_start_cmd(cmd)
        assert ET.fromstring(vm.domain_xml).find('./memoryBacking/access').get('mode') == 'private'
        with patch.object(vm_plugin, 'LibvirtAutoReconnect', side_effect=lambda fn: lambda *args: fn(connection, *args)):
            vm.restore(cmd.memorySnapshotPath)
    restored = ET.fromstring(connection.restoreFlags.call_args.args[1])
    assert (restored.find('./memoryBacking/access') is not None) is keep_private
    if saved_backing == '<source type="anonymous"/>':
        assert restored.find('./memoryBacking/source[@type="anonymous"]') is not None
    connection.defineXML.assert_called_once_with(vm.domain_xml)
    connection.restoreFlags.assert_called_once_with(cmd.memorySnapshotPath, vm.domain_xml)
    hook.assert_not_called()
    assert base64.b64decode(cmd.addons.userDefinedXml).decode() == _user_numa_xml()


def test_hook_emulator_path_is_one_literal_shell_argument():
    selected_path = '/opt/qemu build;echo $marker/qemu-system-x86_64'
    commands = []

    def record_command(command):
        argv = shlex.split(command)
        assert argv == [selected_path, '--version'], 'selected emulator must be one literal shell argument'
        commands.append(argv)
        return 0, 'QEMU emulator version 6.2.0\n', ''

    source = Path(__file__).resolve().parents[3] / 'zstacklib/zstacklib/utils/qemu.py'
    methods = [node for node in ast.parse(source.read_text()).body
               if isinstance(node, ast.FunctionDef) and node.name in
               ('get_version_from_exe_file2', '_parse_version2')]
    namespace = {'bash': SimpleNamespace(bash_roe=record_command), 'logger': MagicMock()}
    module = ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[]))
    exec(compile(module, str(source), 'exec'), namespace)

    cmd = _XmlBuilder()._build_start_cmd(use_numa=True)
    cmd.MemAccess = 'private'
    cmd.useHugePage = False
    cmd.noSharePages = False
    cmd.addons.userDefinedXmlHookScript = base64.b64encode(b'select-emulator').decode()

    def select_emulator(script, xml):
        root = ET.fromstring(xml)
        root.find('devices/emulator').text = selected_path
        return ET.tostring(root, encoding='unicode')

    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin.qemu, 'get_version', return_value='4.2.0'), \
            patch.object(vm_plugin.qemu, 'get_version_from_exe_file2', namespace['get_version_from_exe_file2']), \
            patch.object(vm_plugin, 'get_libvirt_version', return_value='8.0.0'), \
            patch.object(vm_plugin.xmlhook, 'get_modified_xml_from_hook', side_effect=select_emulator):
        vm = _vm_from_start_cmd(cmd)
        root = _start_vm(vm, MagicMock())
    assert root.findtext('devices/emulator') == selected_path
    assert root.find('./memoryBacking/access').get('mode') == 'private'
    assert commands == [[selected_path, '--version']]


@pytest.mark.parametrize('current,saved,expected', [
    ('', '', ''),
    ('<memoryBacking><access mode="private"/></memoryBacking>', '', ''),
    ('<memoryBacking><nosharepages/><access mode="private"/></memoryBacking>', '', '<memoryBacking><nosharepages/></memoryBacking>'),
    ('<memoryBacking><access mode="private"/></memoryBacking>', '<memoryBacking><access mode="private"/></memoryBacking>', '<memoryBacking><access mode="private"/></memoryBacking>'),
    ('<memoryBacking><source type="memfd"/><access mode="shared"/></memoryBacking>', '', '<memoryBacking><source type="memfd"/><access mode="shared"/></memoryBacking>'),
    ('<memoryBacking><hugepages/><access mode="private"/></memoryBacking>', '', '<memoryBacking><hugepages/><access mode="private"/></memoryBacking>'),
    ('<memoryBacking><access mode="private"/></memoryBacking>', '<memoryBacking><source type="file"/></memoryBacking>', '<memoryBacking><access mode="private"/></memoryBacking>'),
])
@pytest.mark.parametrize('arch', ['x86_64', 'aarch64'])
def test_restore_preserves_saved_legacy_ram_backend(current, saved, expected, arch):
    def domain(backing):
        return '<domain><cpu><numa><cell id="0" cpus="0" memory="524288"/></numa></cpu>' + backing + '<devices/></domain>'

    vm = vm_plugin.Vm()
    vm._auto_numa_memory_backing = True
    vm.domain_xml = domain(current)
    vm._patch_disk_xml_order_from_saved_image = MagicMock()
    connection = MagicMock()
    connection.saveImageGetXMLDesc.return_value = domain(saved)
    with patch.object(vm_plugin, 'HOST_ARCH', arch), \
            patch.object(vm_plugin, 'LibvirtAutoReconnect', side_effect=lambda fn: lambda: fn(connection)):
        vm.restore('/owned-snapshot.save')

    restored = ET.fromstring(connection.restoreFlags.call_args.args[1]).find('memoryBacking')
    if arch == 'aarch64':
        expected = current
    if expected:
        assert ET.tostring(restored) == ET.tostring(ET.fromstring(expected))
    else:
        assert restored is None
    connection.defineXML.assert_called_once_with(vm.domain_xml)


def test_restore_does_not_use_changed_backend_when_saved_xml_cannot_be_read():
    vm = vm_plugin.Vm()
    vm._auto_numa_memory_backing = True
    vm.domain_xml = ('<domain><cpu><numa><cell/></numa></cpu>'
                     '<memoryBacking><access mode="private"/></memoryBacking></domain>')
    original = vm.domain_xml
    vm._patch_disk_xml_order_from_saved_image = MagicMock()
    connection = MagicMock()
    connection.saveImageGetXMLDesc.side_effect = OSError('cannot read owned snapshot')
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin, 'LibvirtAutoReconnect', side_effect=lambda fn: lambda: fn(connection)), \
            pytest.raises(OSError, match='cannot read owned snapshot'):
        vm.restore('/owned-snapshot.save')
    assert vm.domain_xml == original
    connection.defineXML.assert_not_called()
    connection.restoreFlags.assert_not_called()


def test_restore_keeps_saved_cpu_layout_and_legacy_ram_backend():
    vm = vm_plugin.Vm()
    vm._auto_numa_memory_backing = True
    vm.domain_xml = ('<domain><vcpu current="2">4</vcpu>'
                     '<vcpus><vcpu id="0" enabled="yes"/><vcpu id="1" enabled="no"/>'
                     '<vcpu id="2" enabled="yes"/><vcpu id="3" enabled="no"/></vcpus>'
                     '<cpu><numa><cell id="0" cpus="0-3" memory="524288"/></numa></cpu>'
                     '<memoryBacking><access mode="private"/></memoryBacking><devices/></domain>')
    saved = (vm.domain_xml.replace('id="1" enabled="no"', 'id="1" enabled="yes"')
             .replace('id="2" enabled="yes"', 'id="2" enabled="no"')
             .replace('<memoryBacking><access mode="private"/></memoryBacking>', ''))
    vm._patch_disk_xml_order_from_saved_image = MagicMock()
    connection = MagicMock()
    connection.saveImageGetXMLDesc.return_value = saved
    with patch.object(vm_plugin, 'HOST_ARCH', 'x86_64'), \
            patch.object(vm_plugin, 'LibvirtAutoReconnect', side_effect=lambda fn: lambda: fn(connection)):
        vm.restore('/owned-snapshot.save')

    restored = ET.fromstring(connection.restoreFlags.call_args.args[1])
    assert restored.find('vcpu').get('current') == '2'
    assert restored.find("./vcpus/vcpu[@id='1']").get('enabled') == 'yes'
    assert restored.find("./vcpus/vcpu[@id='2']").get('enabled') == 'no'
    assert restored.find('./memoryBacking/access') is None

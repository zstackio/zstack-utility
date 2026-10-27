import ast
import fnmatch
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from zstacklib.utils import resource_control


def test_standalone_deployment_contains_backend_modules(tmp_path):
    root = Path(__file__).resolve().parents[3]
    deployment = ast.parse((root / 'imagestorebackupstorage/ansible/imagestorebackupstorage.py').read_text())
    scripts = next(ast.literal_eval(node.iter) for node in ast.walk(deployment)
                   if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                   and node.target.id == 'resource_script')
    build = ET.parse(str(root / 'zstackbuild/projects/zstack-store.xml'))
    includes = [node.attrib['name'] for node in
                build.findall(".//fileset[@dir='${zstacklib.source}/zstacklib/utils']/include")]
    for name in scripts:
        if name != 'resource_control_cli.py':
            assert any(fnmatch.fnmatch(name, pattern) for pattern in includes), 'Missing from build: ' + name
        source = root / ('imagestorebackupstorage/ansible' if name == 'resource_control_cli.py'
                         else 'zstacklib/zstacklib/utils') / name
        shutil.copyfile(str(source), str(tmp_path / name))
    result = subprocess.run([sys.executable, '-S', str(tmp_path / 'resource_control_cli.py'), 'topology'],
                            input='{}', stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                            cwd=str(tmp_path), env=dict(os.environ, PYTHONPATH=''))
    assert result.returncode == 0, 'Standalone Image Store must load the split backends: ' + result.stderr
    assert json.loads(result.stdout)['success'], 'The packaged CLI must run without an installed zstacklib'


def test_deployment_preserves_native_boolean_switch():
    path = Path(__file__).resolve().parents[3] / 'imagestorebackupstorage/ansible/imagestorebackupstorage.py'
    nodes = ast.parse(path.read_text()).body
    assignment = next(node for node in nodes if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'argument_dict' for target in node.targets))
    parser = compile(ast.Expression(assignment.value), str(path), 'eval')
    for enabled in [False, True]:
        args = SimpleNamespace(e=json.dumps({'resource_assignment_enabled': enabled}))
        parsed = eval(parser, {'json': json, 'args': args})
        assert parsed['resource_assignment_enabled'] is enabled, 'Deployment must preserve native booleans'


@pytest.mark.parametrize('version,enabled,client,existing_slice', [
    (2, False, 'false', None), (2, True, 'false', None),
    (1, False, 'false', None), (1, True, 'false', None),
    (2, False, 'true', None), (2, True, 'true', None),
    (2, False, 'false', 'zstack-management.slice'),
])
def test_deployment_prepares_slice_before_start_without_enabling_limits(
        tmp_path, version, enabled, client, existing_slice):
    path = Path(__file__).resolve().parents[3] / 'imagestorebackupstorage/ansible/imagestorebackupstorage.py'
    nodes = ast.parse(path.read_text()).body
    block = next(node for node in nodes if isinstance(node, ast.If)
                 and any(isinstance(child, ast.Name) and child.id == 'resource_assignment_enabled'
                         for child in ast.walk(node)))
    remote = Mock(return_value=version == 2)
    host = SimpleNamespace(distro='rocky')
    namespace = dict(client=client, resource_assignment_enabled=enabled,
                     resource_assignment_slice_name='zstack-imagestore.slice', re=re, shell_quote=shlex.quote,
                     host_info=host, host_post_info=host, RPM_BASED_OS=['rocky'], DEB_BASED_OS=[],
                     run_remote_command=remote)
    exec(compile(ast.Module(body=[block], type_ignores=[]), str(path), 'exec'), namespace)
    probes = [invocation for invocation in remote.call_args_list if invocation.kwargs.get('return_status')]
    if client == 'true' or enabled:
        assert not probes, 'Client deployment and enabled switches must skip version detection'
    else:
        assert probes == [call('test "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs', host, return_status=True)]
    commands = [invocation.args[0] for invocation in remote.call_args_list if not invocation.kwargs]
    assert not any('cgroup2fs' in command or 'cgroup.controllers' in command for command in commands)
    prepares_slice = client != 'true' and (enabled or version == 2)
    assert sum('Slice=' in command for command in commands) == (2 if prepares_slice else 0)
    if client == 'true':
        assert not commands
        return
    if not prepares_slice:
        return

    systemd = tmp_path / 'systemd'
    systemd.mkdir()
    units = ['zstack-imagestorebackupstorage.service', 'bs_collectd_exporter.service']
    for unit in units:
        drop_in = systemd / (unit + '.d') / '50-zstack-resource-assignment.conf'
        if existing_slice:
            drop_in.parent.mkdir(parents=True)
            drop_in.write_text('[Service]\nSlice=%s\n' % existing_slice)
    reload_index = commands.index('systemctl daemon-reload')
    assert reload_index < next(index for index, command in enumerate(commands) if 'systemctl start ' in command)
    for _ in range(2):
        for command in commands[:reload_index]:
            subprocess.check_call(command.replace('/etc/systemd/system', str(systemd)), shell=True)
    for unit in units:
        drop_in = systemd / (unit + '.d') / '50-zstack-resource-assignment.conf'
        assert drop_in.read_text() == '[Service]\nSlice=%s\n' % (existing_slice or 'zstack-imagestore.slice')
    contents = ''.join(file.read_text() for file in systemd.rglob('*') if file.is_file())
    assert not any(setting in contents for setting in ['AllowedCPUs=', 'MemoryMax=', 'MemoryLimit='])


def load_cli(monkeypatch):
    monkeypatch.setitem(sys.modules, 'resource_control', resource_control)
    path = Path(__file__).resolve().parents[3] / 'imagestorebackupstorage/ansible/resource_control_cli.py'
    spec = importlib.util.spec_from_file_location('imagestore_resource_cli', str(path))
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def test_apply_reuses_role_boundary_without_restarting_services(monkeypatch):
    cli = load_cli(monkeypatch)
    manager = Mock()
    manager.apply.return_value = {'synced': False}
    monkeypatch.setattr(cli, 'ResourceControlManager', lambda: manager)
    handles = [{'handleType': 'SYSTEMD_UNIT', 'value': 'zstack-imagestorebackupstorage.service'}]
    command = {'roleType': 'IMAGE_STORE', 'cpuSet': '2-3', 'memory': 2147483648,
               'sliceName': 'zstack-imagestore.slice', 'handles': handles}

    assert cli.execute('apply', command) == {'synced': False}, 'Pending restart must remain unsynced'
    manager.apply.assert_called_once_with('IMAGE_STORE', '2-3', handles, 2147483648, 'zstack-imagestore.slice', 'SHARED')
    manager.restart.assert_not_called()
    manager.release.assert_not_called()


def test_release_removes_all_limits_without_restarting(monkeypatch):
    cli = load_cli(monkeypatch)
    manager = Mock()
    manager.release.return_value = {'synced': True}
    monkeypatch.setattr(cli, 'ResourceControlManager', lambda: manager)
    command = {'roleType': 'IMAGE_STORE', 'sliceName': 'zstack-imagestore.slice', 'handles': []}

    assert cli.execute('release', command)['synced'], 'Release must reuse the idempotent executor'
    manager.release.assert_called_once_with('IMAGE_STORE', [], 'zstack-imagestore.slice')
    manager.restart.assert_not_called()


@pytest.mark.parametrize('action', ['apply', 'release'])
def test_executor_failure_propagates_to_cli_process(action, monkeypatch):
    cli = load_cli(monkeypatch)
    manager = Mock()
    getattr(manager, action).side_effect = resource_control.ResourceControlError('Required service is not active')
    monkeypatch.setattr(cli, 'ResourceControlManager', lambda: manager)
    command = {'roleType': 'IMAGE_STORE', 'sliceName': 'zstack-imagestore.slice', 'handles': []}

    with pytest.raises(resource_control.ResourceControlError, match='Required service is not active'):
        cli.execute(action, command)

    manager.restart.assert_not_called()


def test_topology_keeps_numa_and_smt_groups(monkeypatch):
    cli = load_cli(monkeypatch)
    collect = Mock(return_value={
        '0': {'cpus': ['0', '4', '8'], 'onlineCpus': ['0', '4'], 'coreGroups': [['0', '4']]},
        '2': {'cpus': ['2'], 'onlineCpus': [], 'coreGroups': []},
    })
    monkeypatch.setattr(cli, 'get_cpu_topology', collect)
    result = cli.execute('topology', {})['numa']
    assert result == {'0': {'nodeId': '0', 'onlineCpus': ['0', '4'], 'coreGroups': [['0', '4']]}}, \
        'Reuse shared topology without changing the Image Store response or including offline-only nodes'
    collect.assert_called_once_with()


@pytest.mark.parametrize('action', ['apply', 'release', 'services', 'restart'])
def test_all_service_endpoints_share_validation_before_side_effects(action, monkeypatch):
    cli = load_cli(monkeypatch)
    command = {'roleType': 'IMAGE_STORE', 'sliceName': 'zstack-imagestore.slice', 'handles': []}
    manager = Mock()
    manager.validate_service_command.side_effect = resource_control.ResourceControlError('Invalid service command')
    monkeypatch.setattr(cli, 'ResourceControlManager', lambda: manager)

    with pytest.raises(resource_control.ResourceControlError, match='Invalid service command'):
        cli.execute(action, command)

    assert manager.method_calls == [call.validate_service_command(command['sliceName'], command['handles'])]

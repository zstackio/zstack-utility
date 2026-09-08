import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from zstacklib.utils import resource_control


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

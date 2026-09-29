"""Exercise the port-check handler without loading host-only libvirt plugins."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def handler():
    path = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/ovn.py'
    tree = ast.parse(path.read_text())
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == 'ovn_check_local_port')
    method.decorator_list = []
    module = ast.Module(body=[method], type_ignores=[])
    vsctl = Mock()
    vsctl.getVnicsAndVmUuid.return_value = {}
    vsctl.getVnicsIfaceId.return_value = {}
    bash = Mock()
    bash.bash_r.return_value = 0
    bash.bash_ro.return_value = (0, 'tcp:127.0.0.1:6642')
    scope = dict(VSWITCH_TYPE_ZNS='ZNS', ovn=SimpleNamespace(VsCtl=lambda: vsctl), bash=bash,
                 http=SimpleNamespace(REQUEST_BODY='body'),
                 jsonobject=SimpleNamespace(loads=lambda value: SimpleNamespace(**json.loads(value)),
                                            dumps=lambda value: json.dumps(vars(value))),
                 OvnCheckLocalPortResponse=lambda: SimpleNamespace(success=True, error=''),
                 get_running_vms=Mock(return_value=[]))
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), scope)
    return scope, vsctl, bash


@pytest.mark.parametrize('kind', ['ZNS', 'OvnDpdk', None])
@pytest.mark.parametrize('running', [False, True])
def test_port_check_preserves_service_ownership(handler, kind, running):
    scope, vsctl, bash = handler
    vsctl.isOvsRunning.return_value = running
    request = {} if kind is None else {'vSwitchType': kind}
    result = json.loads(scope['ovn_check_local_port'](None, {'body': json.dumps(request)}))
    if kind == 'ZNS' and not running:
        assert result['success'] is False
        assert 'OVS is not running' in result['error']
        vsctl.getVnicsAndVmUuid.assert_not_called()
        scope['get_running_vms'].assert_not_called()
        bash.bash_r.assert_not_called()
    else:
        assert result['success'] is True
        if running:
            bash.bash_r.assert_not_called()
        else:
            bash.bash_r.assert_called_once_with('systemctl restart openvswitch && systemctl restart ovn-controller')

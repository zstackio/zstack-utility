import ast
import re
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest


@pytest.fixture
def deployment():
    path = Path(__file__).resolve().parents[3] / "kvmagent/ansible/kvm.py"
    tree = ast.parse(path.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "configure_resource_assignment")
    remote = Mock(return_value=True)
    namespace = dict(re=re, shell_quote=shlex.quote, host_post_info=SimpleNamespace(),
                     resource_assignment_enabled="false", resource_assignment_slice_name="zstack-compute.slice",
                     resource_assignment_systemd_units=[], run_remote_command=remote)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return tree, namespace, remote


@pytest.mark.parametrize("version,enabled", [(2, "false"), (2, "true"), (1, "false"), (1, "true")])
def test_first_start_slice_is_independent_of_switch_on_v2(deployment, tmp_path, version, enabled):
    _, namespace, remote = deployment
    namespace["resource_assignment_enabled"] = enabled
    remote.return_value = version == 2
    namespace["configure_resource_assignment"]()
    probes = [invocation for invocation in remote.call_args_list if invocation.kwargs.get("return_status")]
    if enabled == "true":
        assert not probes, "An enabled switch must short-circuit version detection"
    else:
        assert probes == [call('test "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs',
                               namespace["host_post_info"], return_status=True)]
        filesystem = "cgroup2fs" if version == 2 else "tmpfs"
        result = subprocess.run('stat() { printf "%s"; }; %s' % (filesystem, probes[0].args[0]), shell=True)
        assert (result.returncode == 0) == (version == 2)
    commands = [invocation.args[0] for invocation in remote.call_args_list if not invocation.kwargs]
    assert len(commands) == (1 if version == 2 or enabled == "true" else 0)
    calls = tmp_path / "systemctl.calls"
    for command in commands:
        assert "cgroup2fs" not in command and "cgroup.controllers" not in command
        command = command.replace("/etc/systemd/system", str(tmp_path / "systemd"))
        subprocess.check_call('systemctl() { echo "$*" >> %s; }; %s' % (shlex.quote(str(calls)), command), shell=True)

    drop_in = tmp_path / "systemd/zstack-kvmagent.service.d/50-zstack-resource-assignment.conf"
    if version == 2 or enabled == "true":
        assert drop_in.read_text() == "[Service]\nSlice=zstack-compute.slice\n"
        assert calls.read_text().splitlines() == ["stop zstack-kvmagent.service", "daemon-reload"]
    else:
        assert not drop_in.exists()
        assert not calls.exists()


def test_existing_slice_is_preserved_when_switch_is_disabled(deployment, tmp_path):
    _, namespace, remote = deployment
    drop_in = tmp_path / "systemd/zstack-kvmagent.service.d/50-zstack-resource-assignment.conf"
    drop_in.parent.mkdir(parents=True)
    drop_in.write_text("[Service]\nSlice=zstack-mn.slice\n")
    namespace["configure_resource_assignment"]()
    command = remote.call_args.args[0].replace("/etc/systemd/system", str(tmp_path / "systemd"))
    for _ in range(2):
        subprocess.check_call("systemctl() { :; }; " + command, shell=True)
    assert drop_in.read_text() == "[Service]\nSlice=zstack-mn.slice\n"


def test_disabled_v1_returns_before_validating_unused_configuration(deployment):
    _, namespace, remote = deployment
    remote.return_value = False
    namespace["resource_assignment_slice_name"] = "unused-invalid-slice"
    namespace["configure_resource_assignment"]()
    remote.assert_called_once_with('test "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs',
                                   namespace["host_post_info"], return_status=True)


def test_slice_is_configured_before_starting_agent(deployment):
    tree, _, _ = deployment
    calls = [node.value.func.id for node in tree.body if isinstance(node, ast.Expr)
             and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)]
    assert calls.index("configure_resource_assignment") < calls.index("start_kvmagent")

import ast
import json
import os
import runpy
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


SCRIPT = Path(__file__).parents[3] / "zbsprimarystorage" / "ansible" / "zbsp.py"


def test_zbsp_installs_management_callback_probe():
    tree = ast.parse(SCRIPT.read_text())
    assignment = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "install_rpm_list" for target in node.targets)
    )
    packages = set(ast.literal_eval(assignment.value).split())

    assert "nmap" in packages, "MDS callback connectivity checks require nmap"


def capture_mds_commands(monkeypatch, password):
    lib = Mock()
    lib.__all__ = ("HostPostInfo ZstackLibArgs ZstackLib create_log banner get_remote_host_info_obj upgrade_to_helix "
                   "get_host_releasever RPM_BASED_OS file_dir_exist yum_check_package yum_install_package "
                   "set_selinux run_remote_command get_virtualenv_python_version shell_quote").split()
    lib.shell_quote = shlex.quote
    host_info = SimpleNamespace(environment={"LC_ALL": "C"})
    lib.HostPostInfo.return_value = host_info
    lib.upgrade_to_helix.return_value = SimpleNamespace(distro="centos", distro_release="Core", major_version=7)
    lib.RPM_BASED_OS = ["centos"]
    lib.get_virtualenv_python_version.side_effect = StopIteration
    args = dict(host="192.0.2.6", remote_port=2222, remote_user="mds user", remote_pass=password,
                zstack_root="/var/lib/zstack", trusted_host="", yum_server="")
    monkeypatch.setitem(sys.modules, "zstacklib", lib)
    wheels = SCRIPT.parents[2] / "zstackbuild" / "pypi_source" / "pypi"
    monkeypatch.syspath_prepend(str(next(wheels.glob("ansible_core-*.whl"))))
    monkeypatch.setattr(sys, "argv", ["zbsp.py", "-e", repr(args)])
    with pytest.raises(StopIteration):
        runpy.run_path(str(SCRIPT))
    return lib.run_remote_command.call_args_list, args, host_info


@pytest.mark.parametrize("existing", [None, b"", b"keep=existing\n"])
def test_mds_prepares_missing_client_conf_before_self_deploy(monkeypatch, tmp_path, existing):
    calls, _, host_info = capture_mds_commands(monkeypatch, "ordinary")
    commands = [call.args[0] for call in calls]
    prepare, = [call for call in calls if "/etc/zbs/client.conf" in call.args[0]]
    assert prepare.args[1] is host_info
    assert commands.index(prepare.args[0]) < next(i for i, cmd in enumerate(commands) if "client deploy" in cmd)

    config = tmp_path / "zbs" / "client.conf"
    if existing is not None:
        config.parent.mkdir()
        config.write_bytes(existing)
        os.utime(config, (1000, 1000))
    command = prepare.args[0].replace("/etc/zbs", shlex.quote(str(config.parent)))
    subprocess.run(["/bin/sh", "-ec", 'rpm() { test "$*" = "-q libcbd"; }; ' + command], check=True)
    assert config.read_bytes() == (existing or b"")
    if existing is not None:
        assert config.stat().st_mtime == 1000


@pytest.mark.parametrize("password", ["ordinary", "MDS &'$sample\\ {{literal}}", "", None])
def test_mds_client_receives_literal_arguments(monkeypatch, tmp_path, password):
    calls, args, host_info = capture_mds_commands(monkeypatch, password)
    deploy_calls = [call.args for call in calls if "client deploy" in call.args[0]]
    [(command, task_host)] = deploy_calls
    if password:
        assert password not in command
    assert shlex.split(command)[-8:] == ["--host", args["host"], "--port", "2222", "-u", args["remote_user"],
                                        "-p", "$ZBS_MDS_PASSWORD"]
    assert host_info.environment == {"LC_ALL": "C"}
    assert task_host.environment == {"LC_ALL": "C", "ZBS_MDS_PASSWORD": str(password)}
    assert task_host.environment["ZBS_MDS_PASSWORD"].__UNSAFE__
    recorder = tmp_path / "zbsadm"
    recorder.write_text("#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
    recorder.chmod(0o700)
    command = command.replace("/usr/local/bin/zbsadm", shlex.quote(str(recorder)))
    env = dict(os.environ, **task_host.environment)
    result = subprocess.run(["/bin/sh", "-c", command], env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == ["client", "deploy", "--host", args["host"], "--port", "2222",
                                         "-u", args["remote_user"], "-p", str(password)]

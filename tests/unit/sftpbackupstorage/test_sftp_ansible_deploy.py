import os
import runpy
import sys
import types
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).parents[3] / "sftpbackupstorage" / "ansible" / "sftpbackupstorage.py"
VENV_PATH = "/var/lib/zstack/virtualenv/sftpbackupstorage/"
SFTP_ROOT = "/var/lib/zstack/sftpbackupstorage/package"
ZSTACKLIB_SOURCE = "files/zstacklib/zstacklib.tar.gz"
SFTP_SOURCE = "files/sftpbackupstorage/sftpbackupstorage.tar.gz"
IPTABLES_SOURCE = "files/sftpbackupstorage/sftp-iptables"
CLEAR_CACHE = "rm -rf %s/*" % SFTP_ROOT


class FakeRemoteExecutor:
    def __init__(self, py_version="3.11.13", installed=True, iptables_changed=None, install_failure=None):
        self.py_version = py_version
        self.cached = {ZSTACKLIB_SOURCE, SFTP_SOURCE, IPTABLES_SOURCE}
        self.installed = {"zstacklib", "sftpbackupstorage"} if installed else set()
        self.iptables_changed = iptables_changed
        self.install_failure = install_failure
        self.events = []

    def as_module(self):
        module = types.ModuleType("zstacklib")
        module.__dict__.update({
            "os": os,
            "sys": sys,
            "RPM_BASED_OS": ["centos"],
            "DEB_BASED_OS": ["debian"],
            "kylin": [],
            "HostPostInfo": lambda: types.SimpleNamespace(post_label=None),
            "ZstackLibArgs": types.SimpleNamespace,
            "ZstackLib": lambda args: None,
            "CopyArg": types.SimpleNamespace,
            "AgentInstallArg": self.install_args,
            "create_log": lambda path: None,
            "banner": lambda message: None,
            "get_remote_host_info_obj": lambda info: types.SimpleNamespace(
                distro="centos", distro_release="Core", major_version=8),
            "upgrade_to_helix": lambda info, post: info,
            "get_host_releasever": lambda info: "c76",
            "file_dir_exist": lambda path, post: True,
            "run_remote_command": self.command,
            "remote_bin_installed": lambda *args, **kwargs: True,
            "yum_install_package": lambda *args: None,
            "get_virtualenv_python_version": lambda path, post: self.py_version,
            "authorized_key": lambda *args: None,
            "copy": self.copy,
            "agent_install": self.install,
            "handle_ansible_info": lambda message, post, level: self.events.append(("info", message)),
        })
        return module

    @staticmethod
    def install_args(trusted_host, pip_url, venv, init_install):
        return types.SimpleNamespace(virtenv_path=venv, init_install=init_install)

    def command(self, command, post, **kwargs):
        self.events.append(("command", command))
        if command == CLEAR_CACHE:
            self.cached.clear()
        elif command.startswith("rm -rf"):
            assert command == "rm -rf %s" % VENV_PATH
            self.py_version = None
            self.installed.clear()
        elif command.startswith("python3.11 -m venv"):
            self.py_version = "3.11.13"
            self.installed.clear()
        elif "service zstack-sftpbackupstorage stop" in command:
            assert self.installed == {"zstacklib", "sftpbackupstorage"}
        return True

    def copy(self, args, post):
        changed = args.src not in self.cached
        self.cached.add(args.src)
        if args.src == IPTABLES_SOURCE and self.iptables_changed is not None:
            changed = self.iptables_changed
        self.events.append(("copy", args.src, changed))
        return "changed:%s" % changed

    def install(self, args, post):
        assert args.virtenv_path == VENV_PATH
        assert args.agent_root == SFTP_ROOT
        assert args.pkg_name == args.agent_name + ".tar.gz"
        assert args.init_install is False
        self.events.append(("install", args.agent_name))
        if args.agent_name == self.install_failure:
            raise SystemExit(1)
        self.installed.add(args.agent_name)


def run_deploy(remote):
    arguments = {
        "host": "192.0.2.10",
        "host_uuid": "test-host",
        "zstack_root": "/var/lib/zstack",
        "pkg_zstacklib": "zstacklib.tar.gz",
        "pkg_sftpbackupstorage": "sftpbackupstorage.tar.gz",
        "trusted_host": "repo.example.com",
        "pip_url": "https://repo.example.com/simple/",
        "yum_server": "repo.example.com",
        "zstack_repo": "false",
        "chroot_env": "false",
    }
    argv = [str(SCRIPT_PATH), "-i", "inventory", "-e", repr(arguments)]
    with mock.patch.dict(sys.modules, {"zstacklib": remote.as_module()}), mock.patch.object(sys, "argv", argv):
        try:
            runpy.run_path(str(SCRIPT_PATH), run_name="sftp_deploy")
        except SystemExit as error:
            return error.code


def assert_packages_installed_before_restart(remote):
    assert [event for event in remote.events if event[0] == "install"] == [
        ("install", "zstacklib"), ("install", "sftpbackupstorage")]
    restart = next(event for event in remote.events if "service zstack-sftpbackupstorage stop" in event[1])
    assert remote.events.index(("install", "sftpbackupstorage")) < remote.events.index(restart)
    assert remote.installed == {"zstacklib", "sftpbackupstorage"}


def test_recreated_environment_installs_packages_despite_old_cache():
    for version in (None, "2.7.18"):
        remote = FakeRemoteExecutor(py_version=version, installed=False)
        assert run_deploy(remote) == 0
        assert remote.py_version == "3.11.13"
        assert_packages_installed_before_restart(remote)


def test_existing_empty_environment_is_repaired_despite_old_cache():
    remote = FakeRemoteExecutor(installed=False)
    assert run_deploy(remote) == 0
    assert_packages_installed_before_restart(remote)


def test_agent_install_does_not_depend_on_iptables_copy_result():
    remote = FakeRemoteExecutor(iptables_changed=False)
    assert run_deploy(remote) == 0
    assert ("copy", SFTP_SOURCE, True) in remote.events
    assert ("copy", IPTABLES_SOURCE, False) in remote.events
    assert_packages_installed_before_restart(remote)


def test_each_deployment_refreshes_package_cache_before_copy():
    remote = FakeRemoteExecutor()
    for _ in range(2):
        remote.events.clear()
        assert run_deploy(remote) == 0
        first_copy = next(event for event in remote.events if event[0] == "copy")
        assert remote.events.index(("command", CLEAR_CACHE)) < remote.events.index(first_copy)
        assert ("copy", ZSTACKLIB_SOURCE, True) in remote.events
        assert ("copy", SFTP_SOURCE, True) in remote.events
        assert_packages_installed_before_restart(remote)


def test_install_failure_stops_before_service_restart():
    remote = FakeRemoteExecutor(install_failure="sftpbackupstorage")
    assert run_deploy(remote) == 1
    assert not any("service zstack-sftpbackupstorage stop" in event[1] for event in remote.events)
    assert not any(event[0] == "info" and event[1].startswith("SUCC: Deploy") for event in remote.events)

# -*- coding: utf-8 -*-
import sys
import types
import importlib.util
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

_ANSIBLE_SUBMODULES = [
    'libvirt', 'yaml', 'jinja2',
    'ansible', 'ansible.constants', 'ansible.context', 'ansible.executor',
    'ansible.executor.task_queue_manager', 'ansible.module_utils',
    'ansible.module_utils.common', 'ansible.module_utils.common.collections',
    'ansible.inventory', 'ansible.inventory.manager', 'ansible.parsing',
    'ansible.parsing.dataloader', 'ansible.playbook', 'ansible.playbook.play',
    'ansible.plugins', 'ansible.plugins.cache', 'ansible.plugins.cache.memory',
    'ansible.plugins.callback', 'ansible.vars', 'ansible.vars.manager',
    'ansible.plugins.loader',
]


def _load_zstacklib():
    path = os.path.join(os.path.dirname(__file__), '..', 'ansible', 'zstacklib.py')
    spec = importlib.util.spec_from_file_location('zstacklib_under_test', path)
    mod = importlib.util.module_from_spec(spec)
    missing_modules = {
        name: MagicMock()
        for name in _ANSIBLE_SUBMODULES
        if name not in sys.modules
    }
    with patch.dict(sys.modules, missing_modules):
        spec.loader.exec_module(mod)
    return mod


zstacklib = _load_zstacklib()


def test_load_zstacklib_restores_missing_dependencies(monkeypatch):
    module_name = 'ansible.plugins.cache.memory'
    monkeypatch.delitem(sys.modules, module_name, raising=False)

    _load_zstacklib()

    assert module_name not in sys.modules


def _host_info(distro, release, version):
    hi = zstacklib.HostInfo()
    hi.distro = distro
    hi.distro_release = release
    hi.distro_version = version
    return hi


class TestGetHostReleasever:
    def setup_method(self):
        self._orig_mn = zstacklib.get_mn_release
        zstacklib.get_mn_release = lambda: 'h84r'

    def teardown_method(self):
        zstacklib.get_mn_release = self._orig_mn

    @pytest.mark.parametrize(
        "version, releasever",
        [
            ('7.9', 'c79'),
            ('7.6', 'c76'),
            ('7.4', 'c74'),
            ('7.2', 'c74'),
            ('7.1', 'c74'),
        ],
    )
    def test_centos_major_minor_version_maps_to_releasever(
        self, version, releasever
    ):
        hi = _host_info('centos', 'Core', version)
        assert zstacklib.get_host_releasever(hi) == releasever

    def test_centos79_full_build_version_still_maps_to_c79(self):
        hi = _host_info('centos', 'Core', '7.9.2009')
        assert zstacklib.get_host_releasever(hi) == 'c79'

    def test_unknown_distro_falls_back_to_mn_release(self):
        hi = _host_info('centos', 'Core', '6.5')
        assert zstacklib.get_host_releasever(hi) == 'h84r'


def _zstack_lib():
    lib = object.__new__(zstacklib.ZstackLib)
    lib.host_post_info = MagicMock()
    lib.require_python_env = "false"
    lib.distro = "centos"
    lib.distro_version = 7
    lib.zstack_releasever = "c79"
    return lib


def _write_executable(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/sh\n%s\n" % body)
    path.chmod(0o755)


def _use_shell_runner(monkeypatch, directory):
    def run(command, *args, **kwargs):
        env = os.environ.copy()
        env["PATH"] = str(directory)
        result = subprocess.run(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            env=env,
        )
        ok = result.returncode == 0
        if not ok and not kwargs.get("return_status", False):
            raise RuntimeError("remote command failed")
        if kwargs.get("return_output", False):
            return ok, result.stdout
        return ok

    monkeypatch.setattr(zstacklib, "run_remote_command", run)


class TestSelinuxInstallation:
    @pytest.mark.parametrize("repo", ["false", "zstack-mn"])
    @pytest.mark.parametrize("major, candidates", [
        (3, ["python3-libselinux", "libselinux-python3"]),
        (2, ["python2-libselinux", "libselinux-python"]),
    ])
    @pytest.mark.parametrize("installed_index", [0, 1])
    def test_installed_selinux_provider_skips_yum_without_repositories(
        self, monkeypatch, tmp_path, repo, major, candidates, installed_index
    ):
        rpm_calls = tmp_path / "rpm-calls"
        yum_calls = tmp_path / "yum-calls"
        _write_executable(tmp_path, "rpm", 'printf "%s\\n" "$*" >> "%s"; '
                          '[ "$*" = "-q --whatprovides %s" ] || exit 1; '
                          'printf "vendor-selinux-binding-1.0\\n"' % ("%s", rpm_calls, candidates[installed_index]))
        _write_executable(tmp_path, "yum", 'printf "%s\\n" "$*" >> "%s"; exit 1' % ("%s", yum_calls))
        _use_shell_runner(monkeypatch, tmp_path)
        lib = _zstack_lib()
        monkeypatch.setattr(lib, "_get_system_python_major", lambda: major)

        lib._install_selinux(repo)

        assert not yum_calls.exists(), "Installed binding must not require an enabled repository"
        assert rpm_calls.read_text().splitlines() == [
            "-q --whatprovides %s" % package for package in candidates[:installed_index + 1]
        ]

    @pytest.mark.parametrize("major, wrong_binding, candidates", [
        (3, "python2-libselinux", ["python3-libselinux", "libselinux-python3"]),
        (2, "python3-libselinux", ["python2-libselinux", "libselinux-python"]),
    ])
    def test_wrong_python_major_binding_does_not_skip_install(
        self, monkeypatch, tmp_path, major, wrong_binding, candidates
    ):
        calls = tmp_path / "calls"
        _write_executable(tmp_path, "rpm", 'printf "rpm %s\\n" "$*" >> "%s"; '
                          '[ "$*" = "-q --whatprovides %s" ]' % ("%s", calls, wrong_binding))
        _write_executable(tmp_path, "yum", 'printf "yum %s\\n" "$*" >> "%s"' % ("%s", calls))
        _use_shell_runner(monkeypatch, tmp_path)
        lib = _zstack_lib()
        monkeypatch.setattr(lib, "_get_system_python_major", lambda: major)

        lib._install_selinux("false")

        assert calls.read_text().splitlines() == [
            "rpm -q --whatprovides %s" % candidates[0],
            "rpm -q --whatprovides %s" % candidates[1],
            "yum install -y %s" % candidates[0],
        ]

    @pytest.mark.parametrize("output, major", [("3\n", 3), ("2\n", 2)])
    def test_system_python_major_uses_one_remote_command(
        self, monkeypatch, output, major
    ):
        commands = []

        def run(command, *args, **kwargs):
            commands.append(command)
            return True, output

        monkeypatch.setattr(zstacklib, "run_remote_command", run)

        assert _zstack_lib()._get_system_python_major() == major
        assert commands == [
            "python3 -c 'import sys; print(sys.version_info[0])' 2>/dev/null || "
            "python2 -c 'import sys; print(sys.version_info[0])' 2>/dev/null || "
            "python -c 'import sys; print(sys.version_info[0])' 2>/dev/null",
        ]

    def test_unknown_system_python_fails(self, monkeypatch):
        monkeypatch.setattr(
            zstacklib,
            "run_remote_command",
            lambda *args, **kwargs: (True, "unknown"),
        )

        with pytest.raises(Exception, match="system python"):
            _zstack_lib()._get_system_python_major()

    @pytest.mark.parametrize(
        "versions, major, invoked",
        [
            ({"python3": 3, "python2": 2, "python": 2}, 3, ["python3"]),
            ({"python2": 2, "python3.11": 3}, 2, ["python2"]),
            ({"python": 3}, 3, ["python"]),
        ],
    )
    def test_system_python_candidate_fallbacks(
        self, monkeypatch, tmp_path, versions, major, invoked
    ):
        calls = tmp_path / "python-calls"
        for executable, version in versions.items():
            _write_executable(
                tmp_path,
                executable,
                "printf '%s\\n' %s >> '%s'; printf '%s\\n' %s"
                % ("%s", executable, calls, "%s", version),
            )
        _use_shell_runner(monkeypatch, tmp_path)

        assert _zstack_lib()._get_system_python_major() == major
        assert calls.read_text().splitlines() == invoked

    @pytest.mark.parametrize("version", [None, 11])
    def test_system_python_missing_or_invalid_fails(
        self, monkeypatch, tmp_path, version
    ):
        if version is not None:
            _write_executable(tmp_path, "python3", "printf '%s\\n' %s" % ("%s", version))
        _use_shell_runner(monkeypatch, tmp_path)

        with pytest.raises(Exception, match="system python"):
            _zstack_lib()._get_system_python_major()

    def test_python3_only_considers_python3_bindings(self, monkeypatch):
        commands = []
        lib = _zstack_lib()
        monkeypatch.setattr(lib, "_get_system_python_major", lambda: 3)

        def run(command, *args, **kwargs):
            commands.append(command)
            return True

        monkeypatch.setattr(zstacklib, "run_remote_command", run)

        lib._install_selinux("zstack-mn")

        assert commands == [
            "rpm -q --whatprovides python3-libselinux >/dev/null 2>&1 || "
            "rpm -q --whatprovides libselinux-python3 >/dev/null 2>&1 || "
            "yum --disablerepo=* --enablerepo=zstack-mn install -y "
            "python3-libselinux || "
            "yum --disablerepo=* --enablerepo=zstack-mn install -y "
            "libselinux-python3",
        ]
        assert all("import selinux" not in command for command in commands)
        assert all("python2" not in command for command in commands)

    def test_python2_only_considers_python2_bindings(self, monkeypatch):
        commands = []
        lib = _zstack_lib()
        monkeypatch.setattr(lib, "_get_system_python_major", lambda: 2)

        def run(command, *args, **kwargs):
            commands.append(command)
            return True

        monkeypatch.setattr(zstacklib, "run_remote_command", run)

        lib._install_selinux("false")

        assert commands == [
            "rpm -q --whatprovides python2-libselinux >/dev/null 2>&1 || "
            "rpm -q --whatprovides libselinux-python >/dev/null 2>&1 || "
            "yum install -y python2-libselinux || "
            "yum install -y libselinux-python",
        ]
        assert all("import selinux" not in command for command in commands)
        assert all("python3" not in command for command in commands)

    def test_selinux_install_failure_is_not_swallowed(self, monkeypatch):
        commands = []
        lib = _zstack_lib()
        monkeypatch.setattr(lib, "_get_system_python_major", lambda: 3)

        def run(command, *args, **kwargs):
            commands.append(command)
            raise RuntimeError("yum failed")

        monkeypatch.setattr(zstacklib, "run_remote_command", run)

        with pytest.raises(RuntimeError, match="yum failed"):
            lib._install_selinux("false")

        assert commands == [
            "rpm -q --whatprovides python3-libselinux >/dev/null 2>&1 || "
            "rpm -q --whatprovides libselinux-python3 >/dev/null 2>&1 || "
            "yum install -y python3-libselinux || "
            "yum install -y libselinux-python3",
        ]

    @pytest.mark.parametrize("repo", ["false", "zstack-mn"])
    @pytest.mark.parametrize("first_install_fails", [False, True])
    @pytest.mark.parametrize("major, candidates", [
        (3, ["python3-libselinux", "libselinux-python3"]),
        (2, ["python2-libselinux", "libselinux-python"]),
    ])
    def test_selinux_package_candidate_fallbacks(
        self, monkeypatch, tmp_path, major, repo, first_install_fails, candidates
    ):
        calls = tmp_path / "yum-calls"
        failure_cases = candidates[0] if first_install_fails else "__none__"
        _write_executable(tmp_path, "rpm", "exit 1")
        _write_executable(
            tmp_path,
            "yum",
            "for arg do package=$arg; done; "
            "printf '%s\\n' \"$*\" >> '%s'; "
            "case \"$package\" in %s) exit 1;; esac"
            % ("%s", calls, failure_cases),
        )
        _use_shell_runner(monkeypatch, tmp_path)
        lib = _zstack_lib()
        monkeypatch.setattr(lib, "_get_system_python_major", lambda: major)

        lib._install_selinux(repo)

        options = "" if repo == "false" else "--disablerepo=* --enablerepo=zstack-mn "
        installed = candidates if first_install_fails else candidates[:1]
        assert calls.read_text().splitlines() == ["%sinstall -y %s" % (options, package) for package in installed]

    def test_selinux_both_candidates_fail(self, monkeypatch, tmp_path):
        calls = tmp_path / "yum-calls"
        _write_executable(tmp_path, "rpm", "exit 1")
        _write_executable(
            tmp_path,
            "yum",
            "for arg do package=$arg; done; "
            "printf '%s\\n' \"$package\" >> '%s'; exit 1" % ("%s", calls),
        )
        _use_shell_runner(monkeypatch, tmp_path)
        lib = _zstack_lib()
        monkeypatch.setattr(lib, "_get_system_python_major", lambda: 3)

        with pytest.raises(RuntimeError, match="remote command failed"):
            lib._install_selinux("false")

        assert calls.read_text().splitlines() == [
            "python3-libselinux",
            "libselinux-python3",
        ]

    def test_basic_rpm_set_does_not_include_selinux(self):
        assert all(
            "selinux" not in package for package in _zstack_lib()._basic_rpm_set()
        )

    def test_selinux_is_installed_before_basic_packages(self, monkeypatch):
        calls = []
        lib = _zstack_lib()
        monkeypatch.setattr(
            lib, "_install_selinux", lambda repo: calls.append("selinux"), raising=False
        )
        monkeypatch.setattr(
            lib, "_basic_rpm_set", lambda: calls.append("basic") or set()
        )
        monkeypatch.setattr(zstacklib, "batch_yum_install_package", lambda *args: None)

        lib.install_rpm_based_os_requirements("false")

        assert calls == ["selinux", "basic"]

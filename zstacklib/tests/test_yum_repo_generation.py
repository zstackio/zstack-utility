import os
import subprocess
import sys
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch


_ANSIBLE_SUBMODULES = [
    "libvirt", "yaml", "jinja2",
    "ansible", "ansible.constants", "ansible.context", "ansible.executor",
    "ansible.executor.task_queue_manager", "ansible.module_utils",
    "ansible.module_utils.common", "ansible.module_utils.common.collections",
    "ansible.inventory", "ansible.inventory.manager", "ansible.parsing",
    "ansible.parsing.dataloader", "ansible.playbook", "ansible.playbook.play",
    "ansible.plugins", "ansible.plugins.cache", "ansible.plugins.cache.memory",
    "ansible.plugins.callback", "ansible.vars", "ansible.vars.manager",
    "ansible.plugins.loader",
]


def _load_zstacklib():
    path = os.path.join(os.path.dirname(__file__), "..", "ansible", "zstacklib.py")
    spec = importlib.util.spec_from_file_location("zstacklib_under_test", path)
    module = importlib.util.module_from_spec(spec)
    missing_modules = {
        name: MagicMock()
        for name in _ANSIBLE_SUBMODULES
        if name not in sys.modules
    }
    with patch.dict(sys.modules, missing_modules):
        spec.loader.exec_module(module)
    return module


zstacklib = _load_zstacklib()


def _repo_content(section, endpoint):
    return """[%s]
name=%s
baseurl=http://%s/zstack/static/zstack-repo/$basearch/$YUM0/
gpgcheck=0
enabled=0
""" % (section, section, endpoint)


def _write_executable(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/sh\n%s\n" % body)
    path.chmod(0o755)


def _run(command, fake_bin, extra_env=None):
    env = os.environ.copy()
    env["PATH"] = "%s:%s" % (fake_bin, env["PATH"])
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        command,
        shell=True,
        executable="/bin/bash",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        env=env,
    )


def _command(repo_dir, section, endpoint):
    return zstacklib._build_atomic_yum_repo_command(
        str(repo_dir / (section + ".repo")), _repo_content(section, endpoint)
    )


def test_atomic_repo_write_publishes_complete_content_and_metadata(tmp_path):
    repo_dir = tmp_path / "repos"
    fake_bin = tmp_path / "bin"
    repo_dir.mkdir()
    fake_bin.mkdir()

    content = _repo_content("zstack-mn", "192.168.1.10:8080")
    result = _run(
        _command(repo_dir, "zstack-mn", "192.168.1.10:8080"),
        fake_bin,
    )

    repo = repo_dir / "zstack-mn.repo"
    assert result.returncode == 0, result.stderr
    assert repo.read_text() == content
    assert repo.stat().st_mode & 0o777 == 0o644
    assert not list(repo_dir.glob(".zstack-mn.repo.*"))


def test_failure_before_replace_preserves_old_repo_and_cleans_temp(tmp_path):
    repo_dir = tmp_path / "repos"
    fake_bin = tmp_path / "bin"
    repo_dir.mkdir()
    fake_bin.mkdir()
    repo = repo_dir / "zstack-mn.repo"
    repo.write_text("old complete repo\n")
    _write_executable(fake_bin, "sync", "exit 41")

    result = _run(
        _command(repo_dir, "zstack-mn", "192.168.1.10:8080"),
        fake_bin,
    )

    assert result.returncode == 41
    assert repo.read_text() == "old complete repo\n"
    assert not list(repo_dir.glob(".zstack-mn.repo.*"))


def test_term_before_replace_stops_writer_and_cleans_temp(tmp_path):
    repo_dir = tmp_path / "repos"
    fake_bin = tmp_path / "bin"
    repo_dir.mkdir()
    fake_bin.mkdir()
    repo = repo_dir / "zstack-mn.repo"
    repo.write_text("old complete repo\n")
    _write_executable(fake_bin, "sync", 'kill -TERM "$PPID"\nexit 0')

    result = _run(
        _command(repo_dir, "zstack-mn", "192.168.1.10:8080"),
        fake_bin,
    )

    assert result.returncode != 0
    assert repo.read_text() == "old complete repo\n"
    assert not list(repo_dir.glob(".zstack-mn.repo.*"))


def test_directory_sync_failure_is_reported_after_publish(tmp_path):
    repo_dir = tmp_path / "repos"
    fake_bin = tmp_path / "bin"
    repo_dir.mkdir()
    fake_bin.mkdir()
    _write_executable(
        fake_bin,
        "sync",
        '[ "$1" = "$FAIL_SYNC_PATH" ] && exit 42\nexec /usr/bin/sync "$@"',
    )

    result = _run(
        _command(repo_dir, "zstack-mn", "192.168.1.10:8080"),
        fake_bin,
        {"FAIL_SYNC_PATH": str(repo_dir)},
    )

    assert result.returncode == 42
    assert (repo_dir / "zstack-mn.repo").read_text().startswith("[zstack-mn]")
    assert not list(repo_dir.glob(".zstack-mn.repo.*"))


def test_concurrent_writes_publish_one_complete_repo(tmp_path):
    repo_dir = tmp_path / "repos"
    fake_bin = tmp_path / "bin"
    repo_dir.mkdir()
    fake_bin.mkdir()
    endpoints = ["192.168.1.%s:8080" % number for number in range(10, 18)]
    commands = [
        _command(repo_dir, "zstack-mn", endpoint)
        for endpoint in endpoints
    ]

    with ThreadPoolExecutor(max_workers=len(commands)) as executor:
        results = list(executor.map(lambda command: _run(command, fake_bin), commands))

    assert all(result.returncode == 0 for result in results)
    assert (repo_dir / "zstack-mn.repo").read_text() in [
        _repo_content("zstack-mn", endpoint) for endpoint in endpoints
    ]
    assert not list(repo_dir.glob(".zstack-mn.repo.*"))


def test_repo_generators_use_atomic_writer(monkeypatch):
    commands = []
    repos = []
    lib = object.__new__(zstacklib.ZstackLib)
    lib.yum_server = "192.168.1.10:8080"
    lib.host_post_info = MagicMock()
    monkeypatch.setattr(
        zstacklib,
        "_build_atomic_yum_repo_command",
        lambda path, content: repos.append((path, content)) or "write-repo",
    )
    monkeypatch.setattr(
        zstacklib,
        "run_remote_command",
        lambda command, *_args, **_kwargs: commands.append(command) or True,
    )

    lib.generate_mn_yum_repo()
    lib.generate_qemu_kvm_ev_yum_repo()

    assert commands == ["write-repo", "write-repo"]
    assert [repo[0] for repo in repos] == [
        "/etc/yum.repos.d/zstack-mn.repo",
        "/etc/yum.repos.d/qemu-kvm-ev-mn.repo",
    ]
    assert repos[0][1].startswith("[zstack-mn]\n")
    assert repos[1][1].startswith("[qemu-kvm-ev-mn]\n")
    assert "/Extra/qemu-kvm-ev/" in repos[1][1]

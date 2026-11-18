import builtins
import errno
import os
from pathlib import Path
import types

import pytest


SOURCE = Path(__file__).parents[3] / "zstacklib/ansible/zstacklib.py"


class AnsibleError(Exception):
    def __init__(self, message, orig_exc=None):
        super().__init__(message)
        self.orig_exc = orig_exc


def load_ansible_constants(monkeypatch, failure=None):
    original_import = builtins.__import__
    constants = object()

    def import_module(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "ansible.errors":
            return types.SimpleNamespace(AnsibleError=AnsibleError)
        if name == "ansible" and "constants" in fromlist:
            if failure is not None:
                raise failure
            return types.SimpleNamespace(constants=constants)
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_module)
    namespace = {}
    prefix = SOURCE.read_text().split("from ansible import context as ansible_context")[0]
    exec(compile(prefix, str(SOURCE), "exec"), namespace)
    return namespace["ansible_constants"], constants


@pytest.mark.parametrize("blocks,inodes,reason", [
    (0, 400, "disk space exhaustion"),
    (400, 0, "inode exhaustion"),
    (400, 400, "insufficient disk space or inodes"),
])
@pytest.mark.parametrize("wrapped", ["original", "context", "cause", False])
def test_local_tmp_enospc_reports_management_node_and_actual_filesystem(monkeypatch, tmp_path, blocks, inodes, reason, wrapped):
    directory = tmp_path / "configured local tmp"
    directory.mkdir()
    cause = OSError(errno.ENOSPC, "No space left on device", str(directory / "ansible-local-test"))
    failure = AnsibleError("DEFAULT_LOCAL_TMP", orig_exc=cause if wrapped == "original" else None) if wrapped else cause
    if wrapped == "context":
        failure.__context__ = cause
    elif wrapped == "cause":
        failure.__cause__ = cause
    probes = []

    def statvfs(path):
        probes.append(path)
        return types.SimpleNamespace(f_bavail=blocks, f_frsize=1024, f_favail=inodes)

    monkeypatch.setattr(os, "statvfs", statvfs)
    with pytest.raises(AnsibleError) as result:
        load_ansible_constants(monkeypatch, failure)

    message = str(result.value)
    assert "Management node" in message
    assert str(directory) in message
    assert reason in message
    assert "available bytes: %s" % (blocks * 1024) in message
    assert "available inodes: %s" % inodes in message
    assert "df -h" in message and "df -i" in message
    assert result.value.orig_exc is failure
    assert probes == [str(directory)]


@pytest.mark.parametrize("failure", [
    OSError(errno.EACCES, "Permission denied", "/private/ansible-local-test"),
    AnsibleError("invalid Ansible configuration"),
    AnsibleError("Permission denied", orig_exc=OSError(errno.EACCES, "Permission denied")),
    OSError(errno.ENOSPC, "No space left on device"),
])
def test_unrelated_import_errors_are_preserved(monkeypatch, failure):
    with pytest.raises(type(failure)) as result:
        load_ansible_constants(monkeypatch, failure)
    assert result.value is failure


@pytest.mark.parametrize("wrapped", ["original", "context"])
def test_filesystem_probe_failure_preserves_original_error(monkeypatch, tmp_path, wrapped):
    cause = OSError(errno.ENOSPC, "No space left on device", str(tmp_path / "ansible-local-test"))
    failure = AnsibleError("DEFAULT_LOCAL_TMP", orig_exc=cause if wrapped == "original" else None)
    if wrapped == "context":
        failure.__context__ = cause
    original_context = failure.__context__

    def statvfs(path):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(os, "statvfs", statvfs)
    with pytest.raises(AnsibleError) as result:
        load_ansible_constants(monkeypatch, failure)
    assert result.value is failure
    assert result.value.__context__ is original_context


def test_normal_import_keeps_original_constants(monkeypatch):
    actual, expected = load_ansible_constants(monkeypatch)
    assert actual is expected


def test_missing_configured_directory_uses_its_filesystem(monkeypatch, tmp_path):
    directory = tmp_path / "not-created" / "localtmp"
    cause = OSError(errno.ENOSPC, "No space left on device", str(directory))
    failure = AnsibleError("DEFAULT_LOCAL_TMP", orig_exc=cause)
    probes = []

    def statvfs(path):
        probes.append(path)
        return types.SimpleNamespace(f_bavail=0, f_frsize=1024, f_favail=400)

    monkeypatch.setattr(os, "statvfs", statvfs)
    with pytest.raises(AnsibleError) as result:
        load_ansible_constants(monkeypatch, failure)
    assert str(directory.parent) in str(result.value)
    assert probes == [str(tmp_path)]


def test_relative_error_path_is_resolved_without_looping(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cause = OSError(errno.ENOSPC, "No space left on device", "ansible-local-test")
    monkeypatch.setattr(os, "statvfs", lambda path: types.SimpleNamespace(f_bavail=0, f_frsize=1024, f_favail=400))
    with pytest.raises(AnsibleError) as result:
        load_ansible_constants(monkeypatch, cause)
    assert str(tmp_path) in str(result.value)


def test_missing_directory_error_keeps_configured_path_and_decodes_os_filename(monkeypatch, tmp_path):
    directory = tmp_path / "missing" / "configured-localtmp"
    cause = OSError(errno.ENOSPC, "No space left on device", os.fsencode(directory.parent))
    failure = AnsibleError("Unable to create local directories(%s)" % directory)
    failure.__context__ = cause
    monkeypatch.setattr(os, "statvfs", lambda path: types.SimpleNamespace(f_bavail=0, f_frsize=1024, f_favail=400))
    with pytest.raises(AnsibleError) as result:
        load_ansible_constants(monkeypatch, failure)
    assert str(directory.parent) in str(result.value)
    assert "[b'" not in str(result.value)
    assert result.value.orig_exc is failure
    assert str(directory) in str(result.value.orig_exc)


def test_inaccessible_filesystem_root_preserves_original_error(monkeypatch):
    failure = OSError(errno.ENOSPC, "No space left on device", "/tmp/localtmp/ansible-local-test")
    probes = []

    def exists(path):
        probes.append(path)
        assert len(probes) <= 6, "filesystem probing did not stop at the root"
        return False

    monkeypatch.setattr(os.path, "exists", exists)
    with pytest.raises(OSError) as result:
        load_ansible_constants(monkeypatch, failure)
    assert result.value is failure
    assert probes[-1] == "/"

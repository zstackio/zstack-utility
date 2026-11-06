# -*- coding: utf-8 -*-
import base64
import io
import subprocess
import tarfile

import pytest

from kvmagent.plugins.vms import tpm, vm_host_file


VM_UUID = '05607bed-ecba-4553-83b1-5721cc145c44'


@pytest.fixture
def swtpm_root(tmp_path, monkeypatch):
    root = tmp_path / 'swtpm'
    root.mkdir()
    monkeypatch.setattr(tpm, 'SWTPM_BASE', str(root))
    monkeypatch.setattr(vm_host_file, 'ALLOWED_PATH_PREFIXS', [str(root) + '/'])

    def run_tar(command):
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        return process.returncode, stdout.decode(), stderr.decode()

    monkeypatch.setattr(vm_host_file.bash, 'bash_roe', run_tar)
    return root


def read_state(folder):
    request = vm_host_file.VmHostFileTO()
    request.path = str(folder) + '/'
    request.type = 'TpmState'
    return tpm.TpmStateHostFile().read_file(request)


@pytest.mark.parametrize('state_kind', ['missing', 'empty', 'directory'])
def test_directory_without_usable_permall_is_rejected(swtpm_root, state_kind):
    folder = swtpm_root / VM_UUID
    state = folder / 'tpm2' / 'tpm2-00.permall'
    state.parent.mkdir(parents=True)
    control = folder / 'control'
    control.write_bytes(b'keep existing TPM directory')
    if state_kind == 'empty':
        state.write_bytes(b'')
    elif state_kind == 'directory':
        state.mkdir()

    result = read_state(folder)

    assert result.error is not None
    assert 'tpm2-00.permall' in result.error
    assert not result.contentBase64
    assert control.read_bytes() == b'keep existing TPM directory'


@pytest.mark.parametrize('suffix', ['', '.snapshot-backup'])
def test_valid_tpm_state_is_archived(swtpm_root, suffix):
    folder = swtpm_root / (VM_UUID + suffix)
    state = folder / 'tpm2' / 'tpm2-00.permall'
    state.parent.mkdir(parents=True)
    content = b'opaque TPM state bytes'
    state.write_bytes(content)

    result = read_state(folder)

    assert result.error is None
    assert result.fileFormat == vm_host_file.VmHostFileContentFormat.TARBALL_GZIP
    with tarfile.open(fileobj=io.BytesIO(base64.b64decode(result.contentBase64)), mode='r:gz') as archive:
        member = archive.extractfile(folder.name + '/tpm2/tpm2-00.permall')
        assert member.read() == content
    assert state.read_bytes() == content


def test_state_removed_during_archive_read_is_rejected(swtpm_root, monkeypatch):
    folder = swtpm_root / VM_UUID
    state = folder / 'tpm2' / 'tpm2-00.permall'
    state.parent.mkdir(parents=True)
    state.write_bytes(b'original TPM state')
    run_tar = vm_host_file.bash.bash_roe

    def remove_state_before_tar(command):
        state.unlink()
        return run_tar(command)

    monkeypatch.setattr(vm_host_file.bash, 'bash_roe', remove_state_before_tar)

    result = read_state(folder)

    assert result.error is not None
    assert not result.contentBase64
    assert not state.exists()


def test_missing_state_directory_is_reported(swtpm_root):
    folder = swtpm_root / VM_UUID

    result = read_state(folder)

    assert result.error is not None
    assert not result.contentBase64
    assert not folder.exists()


def test_invalid_tpm_state_path_is_rejected(swtpm_root):
    folder = swtpm_root / 'invalid-vm-id'
    folder.mkdir()

    result = read_state(folder)

    assert 'invalid TPM state vm host file path' in result.error
    assert not result.contentBase64

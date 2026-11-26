# -*- coding: utf-8 -*-

import os

import pytest

from kvmagent.plugins.nvram import nvram, nvram_common
from kvmagent.plugins.vms import tpm, vm_host_file

NVRAM_ROOT = '/var/lib/libvirt/qemu/nvram'
VM_UUID = '05607bedecba455383b15721cc145c44'
VM_UUID_WITH_HYPHEN = '05607bed-ecba-4553-83b1-5721cc145c44'


def touch(path):
    with open(path, 'w') as f:
        f.write('x')


def delete_to(path, file_type):
    to = vm_host_file.VmHostFileTO()
    to.path = path
    to.type = file_type
    to.operation = vm_host_file.VmHostFileOperation.DELETE
    return to


@pytest.fixture
def roots(tmp_path, monkeypatch):
    nvram_root = str(tmp_path / 'nvram')
    swtpm_root = str(tmp_path / 'swtpm')
    os.makedirs(nvram_root)
    os.makedirs(swtpm_root)

    to_real = lambda p: p.replace(nvram_root, NVRAM_ROOT)
    to_tmp = lambda p: p.replace(NVRAM_ROOT, nvram_root)
    extract = nvram_common.extract_vm_uuid_from_nvram_vm_host_file_path
    build_fd = nvram_common.build_nvram_vm_host_file_path
    build_token = nvram_common.build_nvram_delete_token_file_path
    monkeypatch.setattr(vm_host_file, 'ALLOWED_PATH_PREFIXS', [nvram_root + '/', swtpm_root + '/'])
    monkeypatch.setattr(tpm, 'SWTPM_BASE', swtpm_root)
    monkeypatch.setattr(nvram_common, 'extract_vm_uuid_from_nvram_vm_host_file_path', lambda p: extract(to_real(p)))
    monkeypatch.setattr(nvram_common, 'build_nvram_vm_host_file_path', lambda u: to_tmp(build_fd(u)))
    monkeypatch.setattr(nvram_common, 'build_nvram_delete_token_file_path', lambda u: to_tmp(build_token(u)))
    return nvram_root, swtpm_root


@pytest.fixture
def nvram_folder(roots):
    folder = os.path.join(roots[0], '%s-host-files' % VM_UUID)
    os.makedirs(folder)
    touch(os.path.join(folder, '%s.fd' % VM_UUID))
    return folder


@pytest.fixture
def tpm_folders(roots):
    folder = os.path.join(roots[1], VM_UUID_WITH_HYPHEN)
    backup_folder = folder + tpm.SNAPSHOT_BACKUP_SUFFIX
    os.makedirs(os.path.join(folder, 'tpm2'))
    os.makedirs(os.path.join(backup_folder, 'tpm2'))
    return folder, backup_folder


def nvram_path(folder):
    return os.path.join(folder, '%s.fd' % VM_UUID)


class TestNvRamHostFileDelete:
    def test_delete_removes_folder_with_delete_token(self, nvram_folder):
        nvram.NvRamHostFile().cleanup(VM_UUID)
        assert os.path.isfile(os.path.join(nvram_folder, 'delete'))

        nvram.NvRamHostFile().write_file(delete_to(nvram_path(nvram_folder), 'NvRam'))

        assert not os.path.exists(nvram_folder)

    def test_delete_removes_snapshot_backup(self, nvram_folder):
        touch(nvram_path(nvram_folder) + '.snapshot-backup')
        touch(os.path.join(nvram_folder, 'delete'))

        nvram.NvRamHostFile().write_file(delete_to(nvram_path(nvram_folder), 'NvRam'))

        assert not os.path.exists(nvram_folder)

    def test_delete_snapshot_backup_keeps_nvram(self, nvram_folder):
        backup_path = nvram_path(nvram_folder) + '.snapshot-backup'
        token_path = os.path.join(nvram_folder, 'delete')
        touch(backup_path)
        touch(token_path)

        nvram.NvRamHostFile().write_file(delete_to(backup_path, 'NvRam'))

        assert not os.path.exists(backup_path)
        assert os.path.isfile(nvram_path(nvram_folder))
        assert os.path.isfile(token_path)

    def test_delete_is_idempotent(self, roots):
        folder = os.path.join(roots[0], '%s-host-files' % VM_UUID)

        nvram.NvRamHostFile().write_file(delete_to(nvram_path(folder), 'NvRam'))

        assert not os.path.exists(folder)


class TestTpmStateHostFileDelete:
    def test_delete_removes_snapshot_backup(self, roots, tpm_folders):
        folder, backup_folder = tpm_folders

        tpm.TpmStateHostFile().write_file(delete_to(folder + '/', 'TpmState'))

        assert not os.path.exists(folder)
        assert not os.path.exists(backup_folder)
        assert os.path.isdir(roots[1])

    def test_delete_keeps_snapshot_backup_when_state_left(self, tpm_folders, monkeypatch):
        folder, backup_folder = tpm_folders
        monkeypatch.setattr(vm_host_file, 'write_vm_host_file', lambda to: None)

        tpm.TpmStateHostFile().write_file(delete_to(folder + '/', 'TpmState'))

        assert os.path.isdir(folder)
        assert os.path.isdir(backup_folder)

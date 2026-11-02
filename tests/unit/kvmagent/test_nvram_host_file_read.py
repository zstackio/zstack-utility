# -*- coding: utf-8 -*-
import base64
import os
import struct

import pytest

from kvmagent.plugins.nvram import nvram, nvram_common
from kvmagent.plugins.vms import vm_host_file


def _var_store(total_size=0x84000):
    header = b'\0' * 32 + struct.pack('<Q', total_size) + b'_FVH' + b'\0' * 16
    return header + b'\xff' * (total_size - len(header))


@pytest.fixture
def nvram_file(tmp_path, monkeypatch):
    monkeypatch.setattr(vm_host_file, 'ALLOWED_PATH_PREFIXS', [str(tmp_path) + '/'])
    monkeypatch.setattr(nvram_common, 'check_nvram_vm_host_file_path_format', lambda path: True)
    return str(tmp_path / 'vm.fd')


def _read(path):
    to = vm_host_file.VmHostFileTO()
    to.path = path
    to.type = 'NvRam'
    return nvram.NvRamHostFile().read_file(to)


def _write(path, data):
    with open(path, 'wb') as fd:
        fd.write(data)


def test_valid_nvram_is_read(nvram_file):
    _write(nvram_file, _var_store(0x2000))

    result = _read(nvram_file)

    assert result.error is None
    assert base64.b64decode(result.contentBase64) == _var_store(0x2000)


@pytest.mark.parametrize('content', [b'x' * 53, _var_store()[:0x1000]], ids=['text', 'truncated'])
def test_corrupted_nvram_is_reported_instead_of_read(nvram_file, content):
    _write(nvram_file, content)

    result = _read(nvram_file)

    assert result.error is not None
    assert 'invalid nvram file' in result.error
    assert not result.contentBase64


def test_missing_nvram_is_reported(nvram_file):
    result = _read(nvram_file)

    assert result.error is not None
    assert not os.path.exists(nvram_file)

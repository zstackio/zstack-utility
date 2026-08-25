import json
import shlex
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_qemu_module():
    bash_module = sys.modules['zstacklib.utils.bash']
    shell_module = sys.modules['zstacklib.utils.shell']

    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / 'zstacklib' / 'zstacklib' / 'utils' / 'qemu.py'
    spec = importlib.util.spec_from_file_location('zstacklib.utils.qemu_bitmap_under_test', str(module_path))
    module = importlib.util.module_from_spec(spec)
    real_exists = os.path.exists
    with patch.object(bash_module, 'bash_roe', return_value=(
            0, 'QEMU emulator version 6.2.0 (qemu-kvm-6.2.0)', '')), \
            patch.object(shell_module, 'call', return_value='6.2.0'), \
            patch('os.path.exists', side_effect=lambda path: (
                    path == '/usr/bin/qemu-system-x86_64' or real_exists(path))):
        spec.loader.exec_module(module)
    return module


qemu = _load_qemu_module()


def test_get_rbd_data_bitmap_splits_offset_extents(monkeypatch):
    monkeypatch.setattr(qemu.linux, 'shellquote', shlex.quote)
    monkeypatch.setattr(
        qemu.shell,
        'call',
        lambda _command: '[{"offset":4096,"length":8192,"exists":"true"}]',
    )

    assert qemu.get_rbd_data_bitmap('pool/image', 4096) == {4096: 4096, 8192: 4096}


def test_get_data_bitmap_does_not_require_allocation_depth(monkeypatch):
    monkeypatch.setattr(qemu, 'get_device_map', lambda _path, _option: json.dumps([
        {'start': 0, 'length': 4096, 'zero': False, 'data': True},
    ]))

    assert qemu.get_data_bitmap('cbd:scratch', 4096, False, True, '-f qcow2') == {0: 4096}


def test_merge_data_bitmaps_unions_adjacent_contained_and_transitive_extents():
    result = qemu.merge_data_bitmaps([
        {0: 10, 30: 10},
        {5: 30, 40: 5},
    ], 16)

    assert result == {0: 16, 16: 16, 32: 13}


def test_merge_data_bitmaps_keeps_disjoint_extents():
    assert qemu.merge_data_bitmaps([{0: 5}, {10: 5}], 16) == {0: 5, 10: 5}

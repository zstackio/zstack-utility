"""The ZRAM RPM installer's recovery record, written in place without leaving a temporary file behind."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / 'kvmagent/scripts/install_memory_optimization_rpm.py'
BOOT_ID = '0f0e0d0c-0b0a-4908-8706-050403020100'


@pytest.fixture
def installer():
    spec = importlib.util.spec_from_file_location('install_memory_optimization_rpm_under_test', str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'proc/sys/kernel/random').mkdir(parents=True)
    (tmp_path / 'proc/sys/kernel/random/boot_id').write_text(BOOT_ID + '\n')
    return tmp_path


def record(root):
    return root / 'var/lib/zstack-zram/rpm-upgrade-recovery.json'


def test_the_recovery_record_is_written_in_place(installer, root):
    data = installer._write_recovery(str(root), {'sha256': 'a' * 64}, {'pid': 1}, 'b' * 64)
    assert data['bootId'] == BOOT_ID
    assert json.loads(record(root).read_text()) == data
    assert [path.name for path in record(root).parent.iterdir()] == [record(root).name]


def test_a_failed_write_leaves_no_temporary_file_and_keeps_the_last_record(installer, root, monkeypatch):
    installer._write_recovery(str(root), {'sha256': 'a' * 64}, {'pid': 1}, 'b' * 64)
    before = record(root).read_text()

    def refuse(*args, **kwargs):
        raise ValueError('record not serializable')
    monkeypatch.setattr(installer.json, 'dump', refuse)
    with pytest.raises(ValueError):
        installer._write_recovery(str(root), {'sha256': 'c' * 64}, {'pid': 2}, 'd' * 64)
    assert record(root).read_text() == before
    assert [path.name for path in record(root).parent.iterdir()] == [record(root).name]

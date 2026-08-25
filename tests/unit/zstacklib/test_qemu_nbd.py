import importlib.util
from pathlib import Path
from unittest.mock import patch


def _load_qemu_nbd_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / 'zstacklib' / 'zstacklib' / 'utils' / 'qemu_nbd.py'
    spec = importlib.util.spec_from_file_location('qemu_nbd_under_test', str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_uses_argv_without_shell_and_preserves_path():
    qemu_nbd = _load_qemu_nbd_module()
    path = "cbd:pool physical/pool/vol$(touch /tmp/not-executed)'quoted"

    with patch.object(qemu_nbd.subprocess, 'Popen') as popen:
        qemu_nbd.export(10888, '-b', '0.0.0.0', '-f', 'qcow2', path, '-x', 'volume-uuid')

    command = popen.call_args.args[0]
    assert command == [
        'qemu-nbd', '-p', '10888', '-b', '0.0.0.0', '-f', 'qcow2', path, '-x', 'volume-uuid',
    ]
    assert popen.call_args.kwargs['shell'] is False

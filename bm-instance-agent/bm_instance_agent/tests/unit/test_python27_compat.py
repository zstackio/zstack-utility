import os
import re
import sys


PHASE2_FILES = (
    'bm-instance-agent/bm_instance_agent/runtime.py',
    'bm-instance-agent/bm_instance_agent/runtime_artifact.py',
    'bm-instance-agent/bm_instance_agent/api/controllers/v2/runtime.py',
    'zstacklib/zstacklib/gpu_runtime_inventory.py',
)


def test_phase2_files_avoid_known_python3_only_syntax():
    repo_root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', '..', '..', '..'))
    forbidden_patterns = (
        re.compile(r'(^|[^A-Za-z0-9_])f["\']'),
        re.compile(r':='),
        re.compile(r'^\s*def\s+[A-Za-z0-9_]+\s*\([^)]*\)\s*->', re.M),
    )

    for relative_path in PHASE2_FILES:
        with open(os.path.join(repo_root, relative_path), 'r') as stream:
            source = stream.read()
        for pattern in forbidden_patterns:
            assert pattern.search(source) is None, (
                '%s uses Python 3-only syntax matching %s'
                % (relative_path, pattern.pattern))


def test_python2_imports_runtime_inventory_without_vendor_plugins():
    if sys.version_info[0] != 2:
        return

    from zstacklib.gpu_runtime_inventory import get_nvidia_topology_cmd
    assert get_nvidia_topology_cmd() == 'nvidia-smi topo -m'
    assert 'zstacklib.gpu' not in sys.modules


def test_python2_manager_does_not_load_vendor_registry():
    if sys.version_info[0] != 2:
        return

    import bm_instance_agent.manager
    assert 'zstacklib.gpu' not in sys.modules

"""Convenience entry point for memory optimization pytest groups.

Default execution is safe and local-only. Build/package integration tests are
opt-in with ``--integration`` because they require Ant and the pinned source
snapshot environment documented in ``tests/README-memory-optimization.md``.
"""
from pathlib import Path
import glob
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
UNIT_PATHS = [
    "tests/unit/installation/test_deploydb.py",
    "zstackctl/zstackctl/test/test_memory_official_upgrade.py",
    "tests/unit/kvmagent/test_memory_optimization_*.py",
    "tests/unit/kvmagent/test_memory_first_zram_history*.py",
    "tests/unit/kvmagent/test_memory_ksm_native*.py",
    "tests/unit/kvmagent/test_install_memory_optimization_rpm.py",
    "tests/unit/zstackbuild/test_prepare_zstack_zram_build_metadata.py",
    "tests/unit/kvmagent/test_memory_drain_recovery.py",
    "tests/unit/kvmagent/test_memory_driver_deployment.py",
    "tests/unit/kvmagent/test_memory_installer_scope.py",
    "tests/unit/kvmagent/test_memory_kernel_capabilities.py",
    "tests/unit/kvmagent/test_memory_maintenance_activation.py",
    "tests/unit/kvmagent/test_memory_plugin_loading.py",
    "tests/unit/kvmagent/test_memory_writeback_backends.py",
    "tests/unit/kvmagent/test_memory_writeback_maintenance.py",
]
INTEGRATION_PATHS = [
    "tests/integration/zstackbuild/test_stage_memory_optimization_rpm.py",
    "tests/integration/zstackbuild/test_zstack_zram_ant.py",
    "tests/integration/kvmagent/test_memory_capacity_cpu_revision_unix.py",
    "tests/integration/kvmagent/test_memory_maintenance_activation_unix.py",
    "tests/integration/kvmagent/test_memory_optimization_integration.py",
]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    integration = "--integration" in argv
    privileged = "--privileged" in argv
    argv = [arg for arg in argv if arg not in ("--integration", "--privileged")]
    configured_paths = INTEGRATION_PATHS if integration else UNIT_PATHS
    paths = []
    for path in configured_paths:
        matches = sorted(glob.glob(str(ROOT / path)))
        if matches:
            paths.extend(matches)
        elif not glob.has_magic(path):
            paths.append(str(ROOT / path))
    marker = ("integration" if integration else
              "privileged and unit" if privileged else
              "not integration and not privileged")
    command = [sys.executable, "-m", "pytest"] + paths + ["-m", marker] + argv
    return subprocess.call(command, cwd=str(ROOT))


if __name__ == "__main__":
    sys.exit(main())

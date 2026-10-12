# Memory optimization test groups

Pure Agent, installer, and metadata tests are part of the normal
pytest discovery tree under `tests/unit/`. The default pytest selection excludes
tests marked `integration`; those require explicit invocation and are not
silently mixed into a local unit run.

Run the safe, unprivileged unit group from the repository root:

```sh
python -m pytest tests/unit/kvmagent/test_memory_optimization_*.py \
  tests/unit/kvmagent/test_memory_first_zram_history*.py \
  tests/unit/kvmagent/test_memory_ksm_native*.py \
  tests/unit/kvmagent/test_install_memory_optimization_rpm.py \
  tests/unit/zstackbuild/test_prepare_zstack_zram_build_metadata.py
```

The convenience entry point is `python tests/run_memory_optimization_unittest.py`.
It forwards extra pytest arguments, for example `-k first_use`.
Two real Go CLI decoder checks are marked `privileged` because the CLI rejects
pool/backend maintenance requests before reading configuration unless run as
root. They are excluded from normal unit runs and test only a guaranteed
missing config (no host config, device, or service is touched). Run explicitly
with a pinned CLI copy and non-interactive elevation:

```sh
sudo -n env ZRAM_EFFICIENCY_TEST_BINARY=/path/to/pinned/zram-efficiency-test \
  python tests/run_memory_optimization_unittest.py --privileged
```

Build/package tests are opt-in:

```sh
ZSTACK_ZRAM_SOURCE=/absolute/path/to/pinned/zstack-utility \
  python tests/run_memory_optimization_unittest.py --integration
```

The build-stage tests read pinned source/build inputs and the Unix-socket tests
require explicitly provisioned isolated Go fixtures. They do not stage files
onto hosts, install packages, start services, or contact a test environment.
Package acceptance must still inspect the actual sdist/WAR contents; passing
pytest alone is not package evidence.

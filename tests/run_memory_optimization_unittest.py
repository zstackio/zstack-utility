"""Run memory Agent UT locally without contacting a Host.

The repository compatibility fixture mocks OS services for Python 3.12.
These tests additionally require the real plugin loader and Prometheus metric
types: silently leaving either mocked would invalidate the assertions.
Run with the development venv that has prometheus_client installed.
"""
import importlib
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest

import prometheus_client.core  # pre-load before the compatibility fixture


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    # The shared Python 3.12 compatibility fixture otherwise replaces this
    # still-present stdlib module with a MagicMock on Python 3.11 as well.
    # PluginRegistry must exercise real module discovery, never that mock.
    if sys.version_info < (3, 12):
        importlib.import_module('imp')
    runpy.run_path(str(root / 'tests/conftest.py'))
    sys.modules.pop('zstacklib.utils.plugin', None)
    utils = sys.modules['zstacklib.utils']
    if hasattr(utils, 'plugin'):
        delattr(utils, 'plugin')
    loader = importlib.import_module('zstacklib.utils.plugin')
    assert str(root) in loader.__file__, 'Production plugin loader required'
    assert hasattr(prometheus_client.core.GaugeMetricFamily, '__mro__'), 'Real metric types required'
    names = sys.argv[1:] or [
        'test_memory_optimization', 'test_memory_drain_recovery',
        'test_memory_maintenance_activation',
        'test_memory_writeback_backends', 'test_memory_writeback_maintenance',
        'test_memory_kernel_capabilities', 'test_memory_plugin_loading',
        'test_memory_ksmtuned_ack',
        'test_memory_installer_scope',
        'prometheus_testsuite.test_collect_memory_optimization',
        'prometheus_testsuite.test_memory_textfile_export',
        'scripts.test_stage_memory_optimization_rpm',
        'scripts.test_install_memory_optimization_rpm',
    ]
    unix_required = any(name == 'test_memory_maintenance_activation_unix'
                       for name in names)
    if unix_required and (os.environ.get('MEMORY_OPTIMIZATION_MAINTENANCE_FIXTURE') != '1' or
                          not os.path.exists(os.environ.get('MEMORY_OPTIMIZATION_SOCKET', ''))):
        raise RuntimeError('maintenance Unix integration requires a live isolated fixture socket')
    module_names = [name if name.startswith('scripts.') else 'kvmagent.test.' + name
                    for name in names]
    suite = unittest.defaultTestLoader.loadTestsFromNames(module_names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    shell_ok = True
    shell_dir = root / 'kvmagent' / 'ansible' / 'memory-optimization' / 'ksmtuned' / 'tests'
    for script in sorted(shell_dir.glob('*.sh')):
        try:
            completed = subprocess.run(['bash', str(script)], cwd=str(root), timeout=60)
        except subprocess.TimeoutExpired:
            print('memory shell test timed out: %s' % script, file=sys.stderr)
            shell_ok = False
            continue
        if completed.returncode != 0:
            print('memory shell test failed (%s): exit %s' %
                  (script, completed.returncode), file=sys.stderr)
            shell_ok = False
    no_required_skips = not unix_required or not result.skipped
    if unix_required and result.skipped:
        print('maintenance Unix integration must not skip: %r' % (result.skipped,), file=sys.stderr)
    return 0 if result.wasSuccessful() and shell_ok and no_required_skips else 1


if __name__ == '__main__':
    sys.exit(main())

"""Exercise the production short-name PluginRegistry, not package imports.

No HTTP server, VM, swap or KSM policy is started. On Python 3.12 only,
the removed imp API is adapted to file loading; PluginRegistry itself and
the plugin modules/handlers are real. Host Python 3.11 uses stdlib imp.
"""
import importlib.util
import json
import os
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch

from kvmagent import kvmagent
from kvmagent import plugins

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.kvmagent]


class TestMemoryPluginLoading(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix='memory-plugin-load-')
        self.addCleanup(self.root.cleanup)
        self.modules = dict(sys.modules)
        self.package_attributes = {name: getattr(plugins, name, None)
                                   for name in ('memory_optimization', 'prometheus')}
        self.collectors = list(kvmagent.metric_collectors)
        self.addCleanup(self.restore_modules)
        repository_root = Path(__file__).resolve().parents[3]
        real_plugin_path = repository_root / 'zstacklib' / 'zstacklib' / 'utils' / 'plugin.py'
        spec = importlib.util.spec_from_file_location('zstacklib.utils.plugin', str(real_plugin_path))
        self.plugin_loader = importlib.util.module_from_spec(spec)
        sys.modules['zstacklib.utils.plugin'] = self.plugin_loader
        spec.loader.exec_module(self.plugin_loader)
        # The shared pytest conftest deliberately substitutes the Agent base
        # class. Keep that test shim, but exercise the actual production
        # registry implementation rather than its MagicMock replacement.
        self.plugin_loader.Plugin = kvmagent.plugin.Plugin
        kvmagent.metric_collectors[:] = []
        for name in ('memory_optimization', 'prometheus',
                     'kvmagent.plugins.memory_optimization', 'kvmagent.plugins.prometheus'):
            sys.modules.pop(name, None)
        for name in self.package_attributes:
            if hasattr(plugins, name):
                delattr(plugins, name)
        # Do not probe/kill any workstation process from KvmAgent.__init__.
        self.recover = patch.object(kvmagent.linux, 'recover_fake_dead')
        self.recover.start()
        self.addCleanup(self.recover.stop)
        if sys.version_info >= (3, 12):
            def find_module(name, paths):
                path = os.path.join(paths[0], name + '.py')
                return open(path), path, ('.py', 'r', 1)

            def load_module(name, stream, path, description):
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                return module

            for name, function in [('find_module', find_module), ('load_module', load_module)]:
                shim = patch.object(self.plugin_loader.imp, name, function)
                shim.start()
                self.addCleanup(shim.stop)
        source = Path(__file__).resolve().parents[3] / 'kvmagent' / 'kvmagent' / 'plugins'
        # Keep this fixture scoped to the target plugin. The production
        # Prometheus plugin imports optional third-party modules intentionally
        # stubbed by root conftest; loading it here would test those stubs, not
        # PluginRegistry behavior.
        os.symlink(str(source / 'memory_optimization.py'),
                   os.path.join(self.root.name, 'memory_optimization.py'))
        self.registry = self.plugin_loader.PluginRegistry(self.root.name)
        self.config = {}
        self.registry.configure_plugins(self.config)
        self.memory = self.registry.get_plugin('MemoryOptimizationPlugin')
        self.memory.service_call = lambda action, payload: {'status': 'Succeeded', 'state': {}}
        self.memory.discover_capabilities = lambda: {'supported': True}
        self.memory._libvirt_vm_generations = lambda: ({}, True)

    def restore_modules(self):
        kvmagent.metric_collectors[:] = self.collectors
        for name, value in self.package_attributes.items():
            if value is not None:
                setattr(plugins, name, value)
            elif hasattr(plugins, name):
                delattr(plugins, name)
        for name in list(sys.modules):
            if name in ('memory_optimization', 'prometheus') or name.startswith('kvmagent.plugins.'):
                if name in self.modules:
                    sys.modules[name] = self.modules[name]
                else:
                    sys.modules.pop(name, None)

    def state(self, host):
        return json.loads(self.memory.state({'body': json.dumps({
            'hostUuid': host, 'operationUuid': 'query-1'})}))

    def test_connect_identity_reaches_registered_handler_and_reconnect_updates_it(self):
        # HostPlugin.configure keeps this shared dict, and /host/connect
        # assigns HOST_UUID to it after the existing MN handshake.
        self.config[kvmagent.HOST_UUID] = 'connected-host'
        self.assertTrue(self.state('connected-host')['success'])
        self.config[kvmagent.HOST_UUID] = 'reconnected-host'
        self.assertTrue(self.state('reconnected-host')['success'])
        self.assertFalse(self.state('connected-host')['success'])

    def test_state_does_not_import_plugins_again_or_register_duplicate_collectors_or_savings(self):
        before = list(kvmagent.metric_collectors)
        names = [f.__name__ for f in before]
        # Memory optimization metrics have one source: node_exporter's
        # textfile collector. They must not be duplicated on Agent port 7069.
        self.assertEqual(0, names.count('collect_memory_optimization_statistics'))
        for unused in range(3):
            result = self.state('unknown-host')
            # Savings are presentation metrics from node_exporter's textfile
            # source; the Agent state endpoint must not be a second source.
            self.assertNotIn('savings', result['state'])
        self.assertEqual(before, kvmagent.metric_collectors)
        self.assertNotIn('kvmagent.plugins.prometheus', sys.modules)

    def test_unconnected_identity_is_not_taken_from_the_request(self):
        self.assertFalse(self.state('request-is-not-authority')['success'])


if __name__ == '__main__':
    unittest.main()

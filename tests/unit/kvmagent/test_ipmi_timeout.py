"""Exercise the BMC probe without importing unrelated host initialization.

Run on Linux with Python 3: python3 -m unittest discover -s tests/unit/kvmagent
"""
import ast
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]


def load_definitions(path, names, namespace):
    # linux.py still contains Python 2-only syntax outside the selected probe.
    source = path.read_text()
    nodes = []
    for name in names:
        match = re.search(r'^(?:def|class) ' + re.escape(name) + r'\b.*?(?=^(?:def|class) |\Z)',
                          source, re.MULTILINE | re.DOTALL)
        assert match is not None
        nodes.append(ast.parse(match.group(0)).body[0])
    assert len(nodes) == len(names)
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


@unittest.skipUnless(os.path.exists('/proc') and shutil.which('timeout'), 'requires Linux and GNU timeout')
class BmcProbeTimeoutTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.logger = MagicMock()
        shell = load_definitions(ROOT / 'zstacklib/zstacklib/utils/shell.py',
                                 ('get_process', 'ShellError', 'ShellCmd'),
                                 {'subprocess': subprocess,
                                  'log': SimpleNamespace(get_logger=lambda _: self.logger)})
        self.probe = load_definitions(ROOT / 'zstacklib/zstacklib/utils/linux.py',
                                     ('is_support_bmc',),
                                     {'shell': SimpleNamespace(**shell), 'logger': self.logger})['is_support_bmc']
        wrapper = self.path / 'timeout'
        wrapper.write_text('''#!/usr/bin/env python3
import os, sys
assert sys.argv[1:4] == ['-k', '5s', '30s']
os.execv(%r, ['timeout', '-k', '0.05s', '0.2s'] + sys.argv[4:])
''' % shutil.which('timeout'))
        ipmi = self.path / 'ipmitool'
        ipmi.write_text('''#!/usr/bin/env python3
import os, signal, sys, time
assert sys.argv[1:] == ['mc', 'info']
if os.environ['BMC_TEST_MODE'] == 'hang':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.alarm(10)
    child = os.fork()
    if child == 0:
        signal.alarm(10)
    with open(os.environ['BMC_TEST_PIDS'], 'a') as stream:
        stream.write(str(os.getpid()) + '\\n')
    while True:
        time.sleep(0.01)
print('Firmware Revision : 1.23')
sys.exit(int(os.environ['BMC_TEST_MODE']))
''')
        wrapper.chmod(0o755)
        ipmi.chmod(0o755)
        environment = patch.dict(os.environ, {'PATH': str(self.path) + os.pathsep + os.environ['PATH'],
                                              'BMC_TEST_MODE': '0',
                                              'BMC_TEST_PIDS': str(self.path / 'pids')})
        environment.start()
        self.addCleanup(environment.stop)

    def test_exit_status_controls_support(self):
        self.assertTrue(self.probe())
        os.environ['BMC_TEST_MODE'] = '1'
        self.assertFalse(self.probe())
        self.logger.warn.assert_not_called()

    def test_hung_probe_is_bounded_and_reaps_children(self):
        os.environ['BMC_TEST_MODE'] = 'hang'
        started = time.monotonic()
        self.assertFalse(self.probe())
        self.assertLess(time.monotonic() - started, 3)
        self.logger.warn.assert_called_once()
        pids = (self.path / 'pids').read_text().splitlines()
        self.assertEqual(len(pids), 2)
        for pid in pids:
            stat = Path('/proc') / pid / 'stat'
            if stat.exists():
                self.assertTrue(stat.read_text().split(') ')[1].startswith('Z '))
        os.environ['BMC_TEST_MODE'] = '0'
        self.assertTrue(self.probe())

    def test_all_timeout_statuses_are_reported_as_probe_failure(self):
        for status in (124, 137, -9):
            with self.subTest(status=status):
                command = MagicMock(return_code=status)
                namespace = load_definitions(ROOT / 'zstacklib/zstacklib/utils/linux.py',
                                             ('is_support_bmc',),
                                             {'shell': SimpleNamespace(ShellCmd=MagicMock(return_value=command)),
                                              'logger': MagicMock()})
                self.assertFalse(namespace['is_support_bmc']())
                namespace['logger'].warn.assert_called_once()

    def test_failed_probe_does_not_stop_collector_registration(self):
        path = ROOT / 'kvmagent/kvmagent/plugins/prometheus.py'
        source = path.read_text()
        start = source.index('\nkvmagent.register_prometheus_collector(') + 1
        registration = source[start:source.index('\nclass ', start)]
        nodes = [node for node in ast.parse(registration).body
                 if isinstance(node, (ast.If, ast.Expr))
                 and 'register_prometheus_collector' in ast.dump(node)]
        for mode, supported in [('hang', False), ('0', True)]:
            with self.subTest(mode=mode):
                os.environ['BMC_TEST_MODE'] = mode
                register = MagicMock()
                namespace = {'kvmagent': SimpleNamespace(register_prometheus_collector=register),
                             'misc': SimpleNamespace(isMiniHost=lambda: False, isHyperConvergedHost=lambda: False),
                             'is_support_bmc': self.probe}
                for node in ast.walk(ast.Module(body=nodes, type_ignores=[])):
                    if isinstance(node, ast.Name) and node.id.startswith('collect_'):
                        namespace[node.id] = node.id
                exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
                registered = [call.args[0] for call in register.call_args_list]
                self.assertEqual('collect_equipment_state_from_ipmi' in registered, supported)
                self.assertIn('collect_raid_state', registered)

    def test_exporter_loop_continues_after_failed_probe(self):
        path = ROOT / 'kvmagent/kvmagent/plugins/prometheus.py'
        source = path.read_text()
        start = source.index('        for cmd in para.cmds:')
        loop_source = source[start:source.index('\n        return jsonobject.dumps(rsp)', start)]
        tree = ast.parse(textwrap.dedent(loop_source))
        loop = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.For) and isinstance(node.iter, ast.Attribute)
                    and node.iter.attr == 'cmds')
        for mode, virtual, supported in [('hang', False, False), ('0', False, True), ('0', True, False)]:
            with self.subTest(mode=mode, virtual=virtual):
                os.environ['BMC_TEST_MODE'] = mode
                start = MagicMock()
                namespace = {'para': SimpleNamespace(cmds=[SimpleNamespace(binaryPath=name)
                                                           for name in ['ipmi_exporter', 'node_exporter']]),
                             'is_virtual_machine': lambda: virtual,
                             'is_support_bmc': self.probe, 'logger': self.logger,
                             'start_ipmi_exporter': start, 'start_exporter': start}
                exec(compile(ast.Module(body=[loop], type_ignores=[]), str(path), 'exec'), namespace)
                self.assertEqual([call.args[0].binaryPath for call in start.call_args_list],
                                 ['ipmi_exporter', 'node_exporter'] if supported else ['node_exporter'])


if __name__ == '__main__':
    unittest.main()

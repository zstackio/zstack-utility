"""Exercise the deploydb entry point without running MySQL or changing a host."""
import argparse
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid


class FreshCloudBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).resolve().parents[1] / 'ctl.py'
        tree = ast.parse(cls.source.read_text())
        cls.command = next(node for node in tree.body
                           if isinstance(node, ast.ClassDef) and node.name == 'DeployDBCmd')

    def run_deploydb(self, fresh=True, exists=False, verified=True, drop=False, keep=False):
        self.calls = []
        self.effects = []
        calls = self.calls

        class ShellCmd:
            def __init__(self, command):
                self.command = command
                self.return_code = 0
                self.stdout = ''
                self.stderr = ''

            def __call__(self, *args):
                calls.append(self.command)
                if 'information_schema.SCHEMATA' in self.command:
                    self.return_code = 0 if verified else 1
                    self.stdout = 'zstack\n' if exists else ''
                elif '-e "use zstack"' in self.command:
                    self.return_code = 0 if exists else 1
                elif self.command.startswith('bash '):
                    self.return_code = 0
                else:
                    raise AssertionError('Unexpected shell command: ' + self.command)

        namespace = {'argparse': argparse, 'ShellCmd': ShellCmd, 'CtlError': RuntimeError,
                     'os': SimpleNamespace(path=SimpleNamespace(join=os.path.join, exists=lambda path: True)),
                     'ctl': SimpleNamespace(zstack_home='/fixture'),
                     'error_if_tool_is_missing': lambda command: None,
                     'format_mysql_host': lambda host: host, 'uuid': uuid,
                     'info': lambda message: None}
        methods = [node for node in self.command.body if isinstance(node, ast.FunctionDef)
                   and node.name in ('install_argparse_arguments', 'run')]
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(self.source), 'exec'), namespace)
        parser = argparse.ArgumentParser()
        instance = SimpleNamespace(DEPLOY_DB_SCRIPT_PATH='deploydb.sh',
                                   ZSTACK_PROPERTY_FILE='zstack.properties',
                                   update_db_config=lambda: self.effects.append('update_db_config'))
        namespace['install_argparse_arguments'](instance, parser)
        argv = ['--no-update']
        if fresh:
            argv.append('--fresh-cloud-bootstrap')
        if drop:
            argv.append('--drop')
        if keep:
            argv.append('--keep-db')
        namespace['run'](instance, parser.parse_args(argv))

    def test_only_verified_absent_database_gets_bootstrap_marker(self):
        self.run_deploydb()
        self.assertIn('information_schema.SCHEMATA', self.calls[0])
        self.assertEqual(['update_db_config'], self.effects)
        self.assertRegex(self.calls[-1], r' fresh-cloud-bootstrap [0-9a-f]{32}$')

    def test_existing_database_is_rejected_before_any_change(self):
        with self.assertRaisesRegex(RuntimeError, 'target zstack database already exists'):
            self.run_deploydb(exists=True)
        self.assertEqual(1, len(self.calls))
        self.assertEqual([], self.effects)

    def test_unverifiable_database_is_rejected_before_any_change(self):
        with self.assertRaisesRegex(RuntimeError, 'target database absence could not be verified'):
            self.run_deploydb(verified=False)
        self.assertEqual(1, len(self.calls))
        self.assertEqual([], self.effects)

    def test_drop_and_keep_modes_are_rejected_before_query(self):
        for mode in ({'drop': True}, {'keep': True}):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(RuntimeError, 'cannot be combined'):
                    self.run_deploydb(**mode)
                self.assertEqual([], self.calls)
                self.assertEqual([], self.effects)

    def test_ordinary_deploy_and_redeploy_do_not_seed_fresh_defaults(self):
        for mode in ({}, {'exists': True, 'keep': True}, {'exists': True, 'drop': True}):
            with self.subTest(mode=mode):
                self.run_deploydb(fresh=False, **mode)
                self.assertFalse(any('information_schema.SCHEMATA' in call for call in self.calls))
                self.assertFalse(any('fresh-cloud-bootstrap' in call for call in self.calls))
                self.assertEqual(['update_db_config'], self.effects)


if __name__ == '__main__':
    unittest.main()

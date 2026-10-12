"""Regression tests for the standard upgrade entry (no database access)."""
import argparse
import ast
import os
import shlex
from pathlib import Path
from types import SimpleNamespace
import unittest


CTL = Path(__file__).resolve().parents[1] / 'ctl.py'


def _class(tree, name):
    return next(node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == name)


def _method(cls, name):
    return next(node for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name == name)


def _execute_method(source, node, namespace):
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(module, str(CTL), 'exec'), namespace)
    return namespace[node.name]


class StandardUpgradeEntryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CTL.read_text()
        cls.tree = ast.parse(cls.source)

    def test_upgrade_db_parser_keeps_standard_switches_without_memory_selector(self):
        node = _method(_class(self.tree, 'UpgradeDbCmd'), 'install_argparse_arguments')
        method = _execute_method(self.source, node, {})
        parser = argparse.ArgumentParser()
        method(object(), parser)
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertTrue({'--force', '--no-backup', '--dry-run', '--precheck-tables',
                         '--update-schema-version'}.issubset(options))
        self.assertNotIn('--memory-migration-cohort', options)

    def test_upgrade_db_keeps_standard_checks_backup_and_flyway_order(self):
        method = _method(_class(self.tree, 'UpgradeDbCmd'), 'run')
        source = ast.get_source_segment(self.source, method)
        self.assertNotIn('memory_migration_cohorts', source)
        self.assertNotIn('_query_memory_schema_history', source)
        expected_order = ('ctl.check_if_management_node_has_stopped(args.force)',
                          'run_mysqlcheck_zstack', 'run_flyway_precheck',
                          'backup_current_database()', 'migrate()')
        positions = [source.index(value) for value in expected_order]
        self.assertEqual(sorted(positions), positions)

    def test_fresh_deploydb_has_no_package_cohort_gate(self):
        method = _method(_class(self.tree, 'DeployDBCmd'), 'run')
        source = ast.get_source_segment(self.source, method)
        self.assertNotIn('inspect_feature_package', source)
        self.assertIn('update_db_config()', source)

    def test_standard_deploydb_create_keep_drop_and_existing_database(self):
        command = _class(self.tree, 'DeployDBCmd')
        for exists, keep, drop, rejected in ((False, False, False, False),
                                             (True, True, False, False),
                                             (True, False, True, False),
                                             (True, False, False, True)):
            with self.subTest(exists=exists, keep=keep, drop=drop):
                calls, effects = [], []

                class ShellCmd:
                    def __init__(self, text):
                        self.text, self.return_code, self.stdout, self.stderr = text, 0, '', ''

                    def __call__(self, *args):
                        calls.append(self.text)
                        if '-e "use zstack"' in self.text:
                            self.return_code = 0 if exists else 1
                        elif self.text.startswith('bash '):
                            self.return_code = 0
                        else:
                            raise AssertionError('Unexpected command: ' + self.text)

                namespace = {
                    'ShellCmd': ShellCmd, 'CtlError': RuntimeError,
                    'os': SimpleNamespace(path=SimpleNamespace(join=os.path.join, exists=lambda path: True)),
                    'ctl': SimpleNamespace(zstack_home='/fixture'),
                    'error_if_tool_is_missing': lambda name: None,
                    'format_mysql_host': lambda host: host, 'info': lambda message: None,
                }
                parser = argparse.ArgumentParser()
                instance = SimpleNamespace(DEPLOY_DB_SCRIPT_PATH='deploydb.sh',
                                           ZSTACK_PROPERTY_FILE='zstack.properties',
                                           update_db_config=lambda: effects.append('update_db_config'))
                _execute_method(self.source, _method(command, 'install_argparse_arguments'), namespace)(instance, parser)
                argv = ['--no-update'] + (['--keep-db'] if keep else []) + (['--drop'] if drop else [])
                execute = _execute_method(self.source, _method(command, 'run'), namespace)
                if rejected:
                    with self.assertRaisesRegex(RuntimeError, 'detected existing zstack database'):
                        execute(instance, parser.parse_args(argv))
                    self.assertEqual(['update_db_config'], effects)
                    self.assertEqual(1, len(calls))
                else:
                    execute(instance, parser.parse_args(argv))
                    self.assertEqual(['update_db_config'], effects)
                    self.assertEqual(1 if keep else 2, len(calls))
                    if not keep:
                        self.assertEqual(['bash', '/fixture/deploydb.sh', 'root', '', 'localhost', '3306', ''],
                                         shlex.split(calls[-1]))

    def test_ctl_has_no_experimental_history_selector(self):
        for token in ('memory_migration_cohorts', '--memory-migration-cohort',
                      'package_cohort'):
            self.assertNotIn(token, self.source)

    def test_ha_parser_and_dispatch_keep_default_upgrade_db_command(self):
        ha = _class(self.tree, 'UpgradeHACmd')
        parser_method = _execute_method(
            self.source, _method(ha, 'install_argparse_arguments'), {})
        parser = argparse.ArgumentParser()
        parser_method(object(), parser)
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertNotIn('--memory-migration-cohort', options)

        run_source = ast.get_source_segment(self.source, _method(ha, 'run'))
        self.assertIn('subprocess.getstatusoutput("zstack-ctl upgrade_db")', run_source)


if __name__ == '__main__':
    unittest.main()

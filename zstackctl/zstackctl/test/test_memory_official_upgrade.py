"""Regression tests for the standard upgrade entry (no database access)."""
import argparse
import ast
from pathlib import Path
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

        calls = []
        namespace = {'subprocess': type('SubprocessStub', (), {
            'getstatusoutput': staticmethod(lambda cmd: calls.append(cmd) or (0, 'ok'))})}
        dispatch = _execute_method(self.source, _method(ha, 'upgrade_database'), namespace)
        self.assertEqual((0, 'ok'), dispatch(object()))
        self.assertEqual(['zstack-ctl upgrade_db'], calls)


if __name__ == '__main__':
    unittest.main()

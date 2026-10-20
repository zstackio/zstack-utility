import argparse
import ast
from datetime import datetime
from pathlib import Path
import shlex
import subprocess
import unittest
from unittest.mock import Mock


class DumpMysqlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[3] / 'zstackctl/zstackctl/ctl.py'
        tree = ast.parse(path.read_text())
        names = {'DumpMysqlCmd', 'shell_quote', 'mysqldump_skip_tables', 'zstone_db_dump_skip_tables'}
        nodes = [node for node in tree.body if getattr(node, 'name', None) in names or
                 isinstance(node, ast.Assign) and any(getattr(target, 'id', None) in names for target in node.targets)]
        cls.namespace = dict(Command=object, ctl=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), cls.namespace)
        cls.command = cls.namespace['DumpMysqlCmd']()
        cls.parser = argparse.ArgumentParser()
        cls.command.install_argparse_arguments(cls.parser)

    def dump_commands(self, arguments, hostname='localhost'):
        shell_cmd = Mock()
        self.namespace.update(os=Mock(), datetime=datetime, ShellCmd=shell_cmd, info=Mock(),
                              error=Mock(side_effect=SystemExit(1)))
        self.namespace['os'].listdir.return_value = []
        self.namespace['ctl'].reset_mock()
        self.namespace['ctl'].get_live_mysql_portal.return_value = (hostname, '3306', 'test', 'test')
        command = self.namespace['DumpMysqlCmd']()
        command.get_db_local_hostname_from_zsha2 = Mock(return_value=None)
        command.is_exist_zstone_db = Mock(return_value=True)
        command.run(self.parser.parse_args(arguments))
        return [shlex.split(dump) for call in shell_cmd.call_args_list
                for dump in call.args[0].split(' | gzip > ', 1)[0][1:-1].replace(' && ', '; ').split('; ')]

    def test_no_parameters_leave_existing_commands_unchanged(self):
        args = self.parser.parse_args([])
        for database in ['zstack', 'zstack_rest', 'zstack_ui', 'zstack_mini', 'keycloak', 'morph', 'zstone']:
            self.assertEqual('mysqldump', self.command._skip_table_data('mysqldump', [database], args.skip_table_data))
        commands = self.dump_commands([])
        self.assertEqual(6, len(commands))
        self.assertEqual(1, sum('-d' in command for command in commands))

    def test_invalid_table_format_fails_before_database_access(self):
        for option in ['--skip-table-data']:
            for table in ['', 'Table', '.Table', 'zstack.', 'zstack..Table', 'zstack.Table.extra',
                          ' .Table', 'zstack. ']:
                with self.subTest(option=option, table=table):
                    with self.assertRaises(SystemExit) as raised:
                        self.dump_commands([option, table])
                    self.assertEqual(1, raised.exception.code)
                    self.assertIn('expected database.table', self.namespace['error'].call_args.args[0])
                    self.namespace['ctl'].get_live_mysql_portal.assert_not_called()
                    self.namespace['ShellCmd'].assert_not_called()

    def test_valid_format_does_not_require_a_known_database_or_table(self):
        commands = self.dump_commands(['--skip-table-data', 'other_db.MissingTable',
                                       '--skip-table-data', 'zstack.MissingTable'])
        self.namespace['error'].assert_not_called()
        self.assertEqual(6, len(commands))
        self.assertIn('--ignore-table=zstack.MissingTable', commands[1])

    def test_multiple_tables_and_duplicates(self):
        commands = self.dump_commands(['--skip-table-data', 'zstack.VmUsageVO', '--skip-table-data',
                                      'zstack.AuditsVO', '--skip-table-data', 'zstack.VmUsageVO',
                                      '--skip-table-data', 'zstack_rest.OtherVO'])
        for table in ['zstack.AuditsVO', 'zstack.VmUsageVO', 'zstack_rest.OtherVO']:
            self.assertEqual(1, commands[1].count('--ignore-table=' + table))

    def test_table_names_are_passed_as_literal_shell_arguments(self):
        for table in ["zstack.T'; id; '", 'zstack.$(id)', 'zstack.T\n', 'zstack.`id`']:
            with self.subTest(table=table):
                command = self.command._skip_table_data('mysqldump', ['zstack'], [table])
                self.assertEqual(['mysqldump', '--ignore-table=' + table],
                                 shlex.split(command.split(' && ', 1)[1]))

    def test_data_exclusion_preserves_schema(self):
        commands = self.dump_commands(['--skip-table-data', 'zstack_ui.T'])
        schema, content = [command for command in commands if 'zstack_ui' in command]
        self.assertIn('-d', schema)
        self.assertNotIn('--ignore-table=zstack_ui.T', schema)
        self.assertNotIn('-d', content)
        self.assertIn('--ignore-table=zstack_ui.T', content)

    def test_main_data_filter_reuses_existing_schema_dump(self):
        defaults = self.namespace['mysqldump_skip_tables']
        for hostname in ['localhost', '192.0.2.1']:
            with self.subTest(hostname=hostname):
                commands = self.dump_commands(['--skip-table-data', 'zstack.Data',
                                               '--skip-table-data', 'zstack_rest.Data'], hostname)
                self.assertEqual(6, len(commands))
                schema, content = commands[:2]
                self.assertIn('-d', schema)
                for option in shlex.split(defaults):
                    self.assertIn(option, content)
                for database in ['zstack', 'zstack_rest']:
                    option = '--ignore-table=%s.Data' % database
                    self.assertNotIn(option, schema)
                    self.assertIn(option, content)
                    self.assertNotIn(option, self.dump_commands([], hostname)[1])
                self.assertEqual(defaults, self.namespace['mysqldump_skip_tables'])

    def test_auxiliary_filter_preserves_data_only_table_schema(self):
        for database in ['zstack_ui', 'zstack_mini', 'keycloak', 'morph', 'zstone']:
            with self.subTest(database=database):
                commands = self.dump_commands(['--skip-table-data', database + '.Data'])
                schema, content = [command for command in commands if database in command]
                self.assertIn('-d', schema)
                self.assertNotIn('--ignore-table=%s.Data' % database, schema)
                self.assertNotIn('-d', content)
                self.assertIn('--ignore-table=%s.Data' % database, content)

    def test_ui_filters_keep_database_dumps_independent(self):
        for hostname in ['localhost', '192.0.2.1']:
            for database in ['zstack_ui', 'zstack_mini']:
                with self.subTest(hostname=hostname, database=database):
                    commands = self.dump_commands(['--skip-table-data', database + '.Data'], hostname)
                    for command in commands:
                        self.assertFalse('zstack_ui' in command and 'zstack_mini' in command)
                    other = 'zstack_mini' if database == 'zstack_ui' else 'zstack_ui'
                    other_commands = [command for command in commands if other in command]
                    self.assertEqual(1, len(other_commands))
                    self.assertNotIn('-d', other_commands[0])
                    self.assertNotIn('--ignore-table=%s.Data' % database, other_commands[0])

    def test_same_table_name_in_another_database_is_not_filtered(self):
        self.assertEqual('mysqldump', self.command._skip_table_data('mysqldump', ['zstack_ui'], {'zstack.Data'}))
        commands = self.dump_commands(['--skip-table-data', 'zstack.Data'])
        self.assertEqual(6, len(commands))
        for command in commands:
            if 'zstack' not in command:
                self.assertNotIn('-d', command)
                self.assertNotIn('--ignore-table=zstack.Data', command)


    def test_schema_failure_skips_filtered_dump(self):
        command = self.command._skip_table_data('dump', ['zstack_ui'], ['zstack_ui.Data'])
        result = subprocess.run(
            'dump() { if [ "$1" = "-d" ]; then return 42; fi; echo data; }; ' + command,
            shell=True, capture_output=True)
        self.assertEqual(42, result.returncode)
        self.assertEqual(b'', result.stdout)


if __name__ == '__main__':
    unittest.main()

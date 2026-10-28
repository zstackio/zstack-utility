import ast
import json
import os
import re
import shlex
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, mock_open, patch


CTL_PATH = Path(__file__).resolve().parents[1] / "ctl.py"
CTL_SOURCE = CTL_PATH.read_text()
CTL_TREE = ast.parse(CTL_SOURCE)


def find_class(name):
    for node in CTL_TREE.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError("cannot find class %s" % name)


def find_method(class_name, method_name):
    for node in find_class(class_name).body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    raise AssertionError("cannot find method %s.%s" % (class_name, method_name))


def has_call_to_attr(node, attr_name):
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr == attr_name:
                return True
    return False


def has_name_call_with_false_arg(node, name):
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if not isinstance(child.func, ast.Name) or child.func.id != name:
            continue
        if len(child.args) == 1 and isinstance(child.args[0], ast.Constant) and child.args[0].value is False:
            return True
    return False


class TestPropertiesIntegrityReport(unittest.TestCase):
    def test_report_waits_for_http_result_and_falls_back_to_db_cleanup(self):
        method = find_method("ConfigureCmd", "_report_property_updated")

        self.assertIn("--connect-timeout 2", CTL_SOURCE)
        self.assertIn("--max-time 10", CTL_SOURCE)
        self.assertTrue(has_call_to_attr(method, "_asdict"))
        self.assertTrue(has_name_call_with_false_arg(method, "report_cmd"))
        self.assertIn("return_code", ast.dump(method))
        self.assertTrue(has_call_to_attr(method, "_delete_property_integrity_records"))

    def test_db_cleanup_targets_only_properties_integrity_records(self):
        method_source = ast.get_source_segment(CTL_SOURCE, find_method("ConfigureCmd", "_delete_property_integrity_records"))

        self.assertIn("FileIntegrityVerificationVO", method_source)
        self.assertIn("nodeType", method_source)
        self.assertIn("hexType", method_source)
        self.assertIn("nodeUuid", method_source)
        self.assertNotIn("path LIKE", method_source)

    def test_configure_use_file_reports_properties_update(self):
        method = find_method("ConfigureCmd", "run")
        use_file_branch = None
        for stmt in method.body:
            if not isinstance(stmt, ast.If):
                continue
            test = stmt.test
            if isinstance(test, ast.Attribute) and test.attr == "use_file":
                use_file_branch = stmt
                break

        self.assertIsNotNone(use_file_branch)
        self.assertTrue(has_call_to_attr(use_file_branch, "_use_file"))
        self.assertTrue(has_call_to_attr(use_file_branch, "_report_property_updated"))

    def test_change_ip_reports_after_config_file_changes(self):
        method = find_method("ChangeIpCmd", "run")
        update_morph_line = None
        report_line = None
        for child in ast.walk(method):
            if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
                continue
            if child.func.attr == "update_family_scoped_properties":
                update_morph_line = child.lineno
            if child.func.attr == "_report_property_updated":
                report_line = child.lineno

        self.assertIsNotNone(update_morph_line)
        self.assertIsNotNone(report_line)
        self.assertGreater(report_line, update_morph_line)


class TestPropertiesIntegrityExecution(unittest.TestCase):
    def setUp(self):
        self.ctl = Mock(properties_file_path="/opt/cloud/WEB-INF/classes/zstack.properties")
        self.ctl.read_property.side_effect = lambda key: {
            "management.server.ip": "2001:db8::10", "managementServerId": "a" * 32,
            "DB.user": "zstack",
        }.get(key)
        self.ctl.get_database_portal.return_value = ([("127.0.0.1", 3306)], "zstack", "secret';&")
        cmd = SimpleNamespace(_asdict=lambda: {"propertiesDigestValue": cmd.propertiesDigestValue, "mnIp": cmd.mnIp})
        self.namespace = dict(Command=object, ctl=self.ctl, re=re, os=os, subprocess=subprocess,
                              CtlError=RuntimeError, PropertyFile=Mock(), simplejson=json,
                              UpdatePropertyCmd=lambda: cmd, file_hex_digest=Mock(return_value="digest"),
                              format_url_host=lambda host: "[%s]" % host if ":" in host else host,
                              ShellCmd=Mock(), logger=Mock(), warn=Mock(), info=Mock())
        self.namespace["PropertyFile"].return_value.read_property.return_value = "a" * 32
        self.namespace["shell_quote"] = lambda value: "'" + value.replace("'", "'\\''") + "'"
        exec(compile(ast.Module(body=[find_class("ConfigureCmd")], type_ignores=[]), str(CTL_PATH), "exec"), self.namespace)
        self.command = self.namespace["ConfigureCmd"]()
        self.ctl.http_call_cmd = 'curl -X POST -H "commandpath:%s" -d \'%s\' --retry 5 "http://%s:%s/zstack/asyncrest/sendcommand"'

    def test_online_report_waits_and_keeps_database_untouched(self):
        report = self.namespace["ShellCmd"].return_value
        report.return_code = 0
        self.command._mysql_cmd = Mock(return_value="b" * 32)
        self.command._delete_property_integrity_records = Mock()
        self.command._report_property_updated()
        sql = self.command._mysql_cmd.call_args.args[0]
        self.assertIn("category='securityMachine'", sql)
        self.assertIn("name='crypto.dataProtect.resourcePoolUuid'", sql)
        report.assert_called_once_with(False)
        self.command._delete_property_integrity_records.assert_not_called()
        command = self.namespace["ShellCmd"].call_args.args[0]
        self.assertIn('http://[2001:db8::10]:8080/', command)
        self.assertIn('"propertiesDigestValue": "digest"', command)
        self.assertIn('--fail', command)
        self.assertIn('--retry 0', command)
        args = shlex.split(command)
        self.assertEqual('2', args[args.index('--connect-timeout') + 1])

    def test_offline_report_uses_database_fallback(self):
        self.namespace["ShellCmd"].return_value.return_code = 7
        self.command._mysql_cmd = Mock(return_value="b" * 32)
        self.command._delete_property_integrity_records = Mock()
        self.command._report_property_updated()
        self.command._delete_property_integrity_records.assert_called_once_with()

    def test_new_installation_without_database_or_node_identity_skips_cleanup(self):
        self.ctl.read_property.side_effect = lambda key: None
        self.namespace["ShellCmd"].return_value.return_code = 7
        self.command._mysql_cmd = Mock(side_effect=RuntimeError("cannot find DB user"))
        with patch.object(os.path, "isfile", return_value=False):
            self.command._report_property_updated()
        self.command._mysql_cmd.assert_not_called()

    def test_default_installation_properties_without_node_identity_skip_reporting(self):
        self.ctl.read_property.side_effect = {"DB.user": "zstack", "DB.url": "jdbc:mysql://localhost:3306"}.get
        self.command._mysql_cmd = Mock(side_effect=FileNotFoundError("mysql"))
        with patch.object(os.path, "isfile", return_value=False):
            self.command._report_property_updated()
        self.command._mysql_cmd.assert_not_called()
        self.namespace["ShellCmd"].assert_not_called()
        self.namespace["file_hex_digest"].assert_not_called()

    def test_reinstallation_template_with_old_node_identity_skips_reporting(self):
        for configured_identity in (None, "a" * 32):
            with self.subTest(configured_identity=configured_identity):
                self.ctl.read_property.side_effect = {
                    "DB.user": "zstack", "DB.password": "", "DB.url": "jdbc:mysql://localhost:3306",
                    "managementServerId": configured_identity,
                }.get
                self.command._mysql_cmd = Mock(side_effect=PermissionError("default credentials cannot access old database"))
                with patch.object(os.path, "isfile", return_value=True):
                    self.command._report_property_updated()
                self.command._mysql_cmd.assert_not_called()
                self.namespace["ShellCmd"].assert_not_called()
                self.namespace["file_hex_digest"].assert_not_called()

    def test_unset_data_protection_pool_skips_reporting_and_cleanup(self):
        for pool_uuid in ("", "None", " None\n"):
            with self.subTest(pool_uuid=pool_uuid):
                self.command._mysql_cmd = Mock(return_value=pool_uuid)
                self.command._delete_property_integrity_records = Mock()
                self.command._report_property_updated()
                self.command._mysql_cmd.assert_called_once()
                self.command._delete_property_integrity_records.assert_not_called()
                self.namespace["ShellCmd"].assert_not_called()
                self.namespace["file_hex_digest"].assert_not_called()

    def test_repeated_installation_rechecks_pool_after_node_initialization(self):
        self.ctl.read_property.side_effect = {"DB.user": "zstack", "management.server.ip": "127.0.0.1"}.get
        self.command._mysql_cmd = Mock(side_effect=["None", "b" * 32])
        self.namespace["ShellCmd"].return_value.return_code = 0
        with patch.object(os.path, "isfile", return_value=False):
            self.command._report_property_updated()
            self.command._mysql_cmd.assert_not_called()
        with patch.object(os.path, "isfile", return_value=True):
            self.command._report_property_updated()
            self.namespace["ShellCmd"].assert_not_called()
            self.command._report_property_updated()
        self.assertEqual(2, self.command._mysql_cmd.call_count)
        self.namespace["ShellCmd"].assert_called_once()

    def test_pool_query_failure_remains_visible_on_initialized_node(self):
        self.command._mysql_cmd = Mock(side_effect=RuntimeError("database unavailable"))
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.command._report_property_updated()
        self.namespace["ShellCmd"].assert_not_called()

    def test_existing_database_or_node_identity_keeps_database_errors(self):
        for properties, persisted in [({"DB.user": "zstack"}, False),
                                      ({"DbFacadeDataSource.user": "zstack"}, False),
                                      ({"managementServerId": "a" * 32}, False),
                                      ({}, True)]:
            with self.subTest(properties=properties, persisted=persisted):
                self.ctl.read_property.side_effect = properties.get
                self.command._mysql_cmd = Mock(side_effect=RuntimeError("database unavailable"))
                with patch.object(os.path, "isfile", return_value=persisted):
                    with self.assertRaisesRegex(RuntimeError, "database unavailable"):
                        self.command._delete_property_integrity_records()
                self.command._mysql_cmd.assert_called_once()

    def test_cleanup_preserves_other_nodes_paths_and_algorithms(self):
        self.command._mysql_cmd = Mock(side_effect=["FileIntegrityVerificationVO", "a" * 32, ""])
        self.command._delete_property_integrity_records()
        sql = self.command._mysql_cmd.call_args.args[0]
        self.assertIn("nodeUuid='" + "a" * 32 + "'", sql)
        self.assertIn("nodeType='managementNode'", sql)
        self.assertIn("hexType='sha256'", sql)
        self.assertIn("path IN (0x" + self.ctl.properties_file_path.encode().hex(), sql)
        self.assertNotIn(" LIKE ", sql)

    def test_absent_table_and_absent_records_skip_cleanup(self):
        for results in ([""], ["FileIntegrityVerificationVO", ""]):
            with self.subTest(results=results):
                self.command._mysql_cmd = Mock(side_effect=results)
                self.command._delete_property_integrity_records()
                self.assertEqual(len(results), self.command._mysql_cmd.call_count)

    def test_persisted_management_server_id_is_used(self):
        self.ctl.read_property.side_effect = lambda key: None
        self.namespace["PropertyFile"].return_value.read_property.return_value = "b" * 32
        self.command._mysql_cmd = Mock(side_effect=["FileIntegrityVerificationVO", "b" * 32, ""])
        with patch.object(os.path, "isfile", return_value=True):
            self.command._delete_property_integrity_records()
        self.assertIn("nodeUuid='" + "b" * 32 + "'", self.command._mysql_cmd.call_args.args[0])

    def test_missing_or_invalid_node_identity_never_deletes(self):
        for identity in (None, "invalid", "x' OR 1=1 --"):
            with self.subTest(identity=identity):
                self.ctl.read_property.side_effect = lambda key: "zstack" if key == "DB.user" else identity
                self.command._mysql_cmd = Mock(side_effect=["FileIntegrityVerificationVO", "a" * 32])
                with patch.object(os.path, "isfile", return_value=False), self.assertRaises(RuntimeError):
                    self.command._delete_property_integrity_records()
                self.assertEqual(2, self.command._mysql_cmd.call_count)

    def test_foreign_configured_identity_never_deletes_peer_records(self):
        self.namespace["PropertyFile"].return_value.read_property.return_value = "b" * 32
        self.command._mysql_cmd = Mock(side_effect=["FileIntegrityVerificationVO", "a" * 32])
        with patch.object(os.path, "isfile", return_value=True), self.assertRaisesRegex(RuntimeError, "differ"):
            self.command._delete_property_integrity_records()
        self.assertEqual(2, self.command._mysql_cmd.call_count)

    def test_database_failure_propagates_without_clearing_records(self):
        self.command._mysql_cmd = Mock(side_effect=RuntimeError("database unavailable"))
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.command._delete_property_integrity_records()
        self.command._mysql_cmd.assert_called_once()

    def test_database_password_stays_out_of_command_and_exception(self):
        with patch.object(subprocess, "check_output", return_value=b"rows") as query:
            self.assertEqual("rows", self.command._mysql_cmd("SELECT 1"))
        args, kwargs = query.call_args
        self.assertNotIn("secret';&", str(args))
        self.assertEqual("secret';&", kwargs["env"]["MYSQL_PWD"])
        self.assertEqual("SELECT 1", args[0][-1])
        self.assertEqual(10, kwargs["timeout"])

    def test_database_failover_tries_the_next_configured_portal(self):
        self.ctl.get_database_portal.return_value = (
            [("127.0.0.2", 3306), ("127.0.0.1", 3307)], "zstack", "secret';&")
        failure = subprocess.TimeoutExpired(["mysql"], 10)
        with patch.object(subprocess, "check_output", side_effect=[failure, b"rows"]) as query:
            self.assertEqual("rows", self.command._mysql_cmd("SELECT 1"))
        calls = [call.args[0] for call in query.call_args_list]
        self.assertEqual(["127.0.0.2", "127.0.0.1"], [args[args.index("--host") + 1] for args in calls])
        self.assertEqual("3307", calls[1][calls[1].index("--port") + 1])

    def test_unavailable_ha_database_vip_uses_local_replica(self):
        vip = '172.24.227.147'
        self.ctl.get_database_portal.return_value = ([(vip, 3306)], 'zstack', 'secret')
        config = mock_open(read_data=json.dumps({'dbvip': vip}))
        failure = subprocess.CalledProcessError(1, ['mysql'])
        with patch.object(os.path, 'isfile', return_value=True), patch('builtins.open', config):
            with patch.object(subprocess, 'check_output', side_effect=[failure, b'rows']) as query:
                self.assertEqual('rows', self.command._mysql_cmd('SELECT 1'))
        calls = [call.args[0] for call in query.call_args_list]
        self.assertEqual([vip, '127.0.0.1'], [args[args.index('--host') + 1] for args in calls])

    def test_custom_database_does_not_use_local_ha_replica(self):
        for host, port in [('192.0.2.50', 3306), ('172.24.227.147', 3307)]:
            with self.subTest(host=host, port=port):
                self.ctl.get_database_portal.return_value = ([(host, port)], 'zstack', 'secret')
                config = mock_open(read_data=json.dumps({'dbvip': '172.24.227.147'}))
                with patch.object(os.path, 'isfile', return_value=True), patch('builtins.open', config):
                    with patch.object(subprocess, 'check_output', side_effect=subprocess.TimeoutExpired(['mysql'], 10)) as query:
                        with self.assertRaises(subprocess.TimeoutExpired):
                            self.command._mysql_cmd('SELECT 1')
                query.assert_called_once()

    def test_database_timeout_propagates_when_all_portals_fail(self):
        with patch.object(subprocess, "check_output", side_effect=subprocess.TimeoutExpired(["mysql"], 10)):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.command._mysql_cmd("SELECT 1")


if __name__ == "__main__":
    unittest.main()

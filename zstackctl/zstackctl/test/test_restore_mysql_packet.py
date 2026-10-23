import ast
from contextlib import contextmanager
import shlex
import gzip
import os
import re
import shutil
import time
import uuid
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parents[1] / "ctl.py"


def packet_process():
    process = MagicMock()
    process.__enter__.return_value = process
    process.stdout.readline.return_value = "1\n"
    return process


def packet_namespace(namespace):
    namespace["subprocess"] = SimpleNamespace(
        Popen=lambda *a, **kw: packet_process(),
        PIPE=subprocess.PIPE,
        DEVNULL=subprocess.DEVNULL,
    )
    namespace.setdefault("CtlError", RuntimeError)
    namespace.setdefault("local_ip_exists", lambda ip: False)
    namespace.setdefault("check_ha", lambda: False)
    return namespace


def packet_helpers(tree):
    return [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name
        in ("mysql_restore_packet_limit", "_mysql_restore_control_target")
    ]


def set_packet_value(command, current):
    conditional = re.search(
        r"IF\(@@GLOBAL.max_allowed_packet=(\d+),(\d+),", command
    )
    if conditional:
        if current[0] == int(conditional.group(1)):
            current[0] = int(conditional.group(2))
    else:
        current[0] = int(command.split("max_allowed_packet=")[1].split("'")[0])


class RestoreMysqlPacketTest(unittest.TestCase):
    def test_packet_control_uses_privileged_local_connection_on_ha_database(
        self,
    ):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        password = "pass';&"
        for local, ha, known in [
            (True, True, True),
            (False, True, True),
            (False, False, True),
            (False, True, False),
        ]:
            with self.subTest(local=local, ha=ha, known=known):
                hostname = "192.0.2.60" if known else "192.0.2.90"
                commands = []
                peer = SimpleNamespace(
                    config={
                        "dbvip": "192.0.2.60",
                        "peerip": "192.0.2.41",
                        "peerport": 2222,
                    },
                    ssh_exec_user="zstack",
                )
                namespace = packet_namespace(
                    dict(
                        contextmanager=contextmanager,
                        shell_quote=shlex.quote,
                        shell=lambda c: commands.append(c) or "4194304",
                        shell_no_pipe=commands.append,
                        local_ip_exists=lambda ip: local,
                        check_ha=lambda: ha,
                        Zsha2Utils=lambda: peer,
                    )
                )
                namespace["subprocess"].Popen = lambda command, **kw: (
                    commands.append(command) or packet_process()
                )
                exec(
                    compile(
                        ast.Module(body=helpers, type_ignores=[]),
                        str(SOURCE),
                        "exec",
                    ),
                    namespace,
                )
                with namespace["mysql_restore_packet_limit"](
                    password, 3307, hostname
                ):
                    pass
                self.assertEqual(3, len(commands))
                for command in commands:
                    argv = shlex.split(command)
                    if ha and not local and known:
                        self.assertIn("ssh", argv)
                        self.assertIn("192.0.2.41", argv)
                        self.assertIn("2222", argv)
                        remote = shlex.split(argv[-1])
                        self.assertEqual(["sudo", "sh", "-c"], remote[:3])
                        argv = shlex.split(remote[3])
                    else:
                        self.assertNotIn("ssh", argv)
                    self.assertIn(
                        "--host=127.0.0.1"
                        if local or (ha and known)
                        else "--host=" + hostname,
                        argv,
                    )
                    self.assertIn("--protocol=tcp", argv)
                    self.assertIn("--password=" + password, argv)
                    self.assertEqual("3307", argv[argv.index("-P") + 1])

    def test_packet_control_preserves_default_socket_and_explicit_loopbacks(
        self,
    ):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        for hostname in (None, "", "localhost", "127.0.0.1", "::1"):
            with self.subTest(hostname=hostname):
                commands = []
                namespace = packet_namespace(
                    dict(
                        contextmanager=contextmanager,
                        shell_quote=shlex.quote,
                        shell=lambda c: commands.append(c) or "4194304",
                        shell_no_pipe=commands.append,
                        local_ip_exists=lambda ip: self.fail(
                            "loopback must not need address discovery"
                        ),
                        check_ha=lambda: self.fail(
                            "local connection must not inspect HA"
                        ),
                    )
                )
                namespace["subprocess"].Popen = lambda command, **kw: (
                    commands.append(command) or packet_process()
                )
                exec(
                    compile(
                        ast.Module(body=helpers, type_ignores=[]),
                        str(SOURCE),
                        "exec",
                    ),
                    namespace,
                )
                with namespace["mysql_restore_packet_limit"](
                    "", 3307, hostname
                ):
                    pass
                for command in commands:
                    argv = shlex.split(command)
                    if hostname:
                        self.assertIn("--host=" + hostname, argv)
                    else:
                        self.assertFalse(
                            any(x.startswith("--host") for x in argv)
                        )
                    if not hostname or hostname == "localhost":
                        self.assertFalse(
                            any(x.startswith("--protocol") for x in argv)
                        )

    def test_restore_control_targets_match_local_imports_and_remote_ui(self):
        tree = ast.parse(SOURCE.read_text())
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "RestoreMysqlCmd"
        )
        run = next(
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "run"
        )
        imports = []
        restorer = MagicMock()
        restorer.is_local_ip.side_effect = lambda host: host == "192.0.2.60"
        process = SimpleNamespace(
            check_call=MagicMock(
                side_effect=subprocess.CalledProcessError(3, "systemctl")
            ),
            CalledProcessError=subprocess.CalledProcessError,
        )
        ctl = SimpleNamespace(
            get_live_mysql_portal=lambda **kw: ("192.0.2.60", 3306, "", ""),
            internal_run=MagicMock(),
        )
        namespace = dict(
            os=os,
            ctl=ctl,
            shell_quote=shlex.quote,
            subprocess=process,
            error_if_tool_is_missing=lambda tool: None,
            check_gunzip_file=lambda path: None,
            RestorerFactory=SimpleNamespace(get_restorer=lambda *a: restorer),
            create_check_mgmt_node_command=lambda: MagicMock(),
            get_mgmt_node_state_from_result=lambda c: False,
            shell_no_pipe=lambda c: None,
            shell_return=lambda c: 1,
            info=lambda m: None,
            warn=lambda m: None,
        )
        exec(
            compile(
                ast.Module(body=[run], type_ignores=[]), str(SOURCE), "exec"
            ),
            namespace,
        )
        obj = SimpleNamespace(
            test_mysql_connection=lambda *a: None,
            restore_database=lambda *a: imports.append(a),
        )
        with tempfile.NamedTemporaryFile() as backup:
            namespace["run"](
                obj,
                SimpleNamespace(
                    from_file=backup.name,
                    mysql_root_password="",
                    ui_mysql_root_password=None,
                    skip_check=False,
                    skip_ui=False,
                ),
            )
        self.assertEqual(
            [None, None, "192.0.2.60"], [args[3] for args in imports]
        )
        for command, _, _, host in imports:
            self.assertEqual(host is not None, "--host 192.0.2.60" in command)
        self.assertEqual(
            "check_restore_mysql", ctl.internal_run.call_args_list[0].args[0]
        )

    def test_packet_scope_in_isolated_mariadb(self):
        docker = shutil.which("docker")
        if (
            not docker
            or subprocess.run(
                [docker, "image", "inspect", "mariadb:10.3"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
        ):
            self.skipTest("requires Docker and the local mariadb:10.3 image")
        name = "zstackctl-packet-test-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as directory:
            try:
                subprocess.run(
                    [
                        docker,
                        "run",
                        "-d",
                        "--rm",
                        "--name",
                        name,
                        "--network",
                        "none",
                        "-e",
                        "MYSQL_ALLOW_EMPTY_PASSWORD=yes",
                        "mariadb:10.3",
                        "--max-allowed-packet=4M",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                wrapper = Path(directory) / "mysql"
                wrapper.write_text(
                    "#!/bin/sh\nexec "
                    + shlex.quote(docker)
                    + " exec -i "
                    + name
                    + ' mysql "$@"\n'
                )
                wrapper.chmod(0o700)
                with patch.dict(
                    os.environ,
                    {"PATH": directory + os.pathsep + os.environ["PATH"]},
                ):
                    for _ in range(60):
                        result = subprocess.run(
                            [
                                "mysql",
                                "-uroot",
                                "--protocol=tcp",
                                "-h127.0.0.1",
                                "-e",
                                "SELECT 1",
                            ],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        if result.returncode == 0:
                            break
                        time.sleep(0.5)
                    else:
                        self.fail("isolated MariaDB did not become ready")

                    def shell(command):
                        return subprocess.check_output(
                            command,
                            shell=True,
                            text=True,
                            stderr=subprocess.STDOUT,
                        )

                    shell('mysql -uroot -e "SET GLOBAL wait_timeout=1"')
                    tree = ast.parse(SOURCE.read_text())
                    helpers = packet_helpers(tree)
                    namespace = dict(
                        contextmanager=contextmanager,
                        subprocess=subprocess,
                        shell=shell,
                        shell_no_pipe=shell,
                        shell_quote=shlex.quote,
                        CtlError=RuntimeError,
                    )
                    exec(
                        compile(
                            ast.Module(body=helpers, type_ignores=[]),
                            str(SOURCE),
                            "exec",
                        ),
                        namespace,
                    )
                    scope = namespace["mysql_restore_packet_limit"]
                    with scope("", 3306, ""):
                        time.sleep(2.5)
                        self.assertEqual(
                            "0",
                            shell(
                                "mysql -uroot -NB -e "
                                '"SELECT IS_FREE_LOCK('
                                "'zstackctl.restore_mysql.packet')\""
                            ).strip(),
                        )
                        with self.assertRaisesRegex(
                            RuntimeError, "packet lock"
                        ):
                            with scope("", 3306, ""):
                                self.fail(
                                    "second scope entered after the "
                                    "database idle timeout"
                                )
                    self.assertEqual(
                        "1",
                        shell(
                            "mysql -uroot -NB -e "
                            '"SELECT IS_FREE_LOCK('
                            "'zstackctl.restore_mysql.packet')\""
                        ).strip(),
                    )
                    self.assertEqual(
                        "4194304",
                        shell(
                            "mysql -uroot -NB -e "
                            '"SELECT @@GLOBAL.max_allowed_packet"'
                        ).strip(),
                    )
                    self.assertEqual(
                        "1",
                        shell(
                            "mysql -uroot -NB -e "
                            '"SELECT @@GLOBAL.wait_timeout"'
                        ).strip(),
                    )
                    for replacement in (8 << 20, 128 << 20, 256 << 20):
                        with self.subTest(before_prepare=replacement):
                            shell(
                                'mysql -uroot -e "SET GLOBAL '
                                'max_allowed_packet=4194304"'
                            )
                            first = [True]

                            def changed_before_prepare(command):
                                if not first[0]:
                                    return shell(command)
                                first[0] = False
                                if "SET GLOBAL max_allowed_packet" in command:
                                    shell(
                                        'mysql -uroot -e "SET GLOBAL '
                                        'max_allowed_packet=%s"' % replacement
                                    )
                                    return shell(command)
                                snapshot = shell(command)
                                shell(
                                    'mysql -uroot -e "SET GLOBAL '
                                    'max_allowed_packet=%s"' % replacement
                                )
                                return snapshot

                            namespace["shell"] = changed_before_prepare
                            with scope("", 3306, ""):
                                self.assertEqual(
                                    str(max(replacement, 128 << 20)),
                                    shell(
                                        "mysql -uroot -NB -e "
                                        '"SELECT @@GLOBAL.max_allowed_packet"'
                                    ).strip(),
                                )
                            self.assertEqual(
                                str(replacement),
                                shell(
                                    "mysql -uroot -NB -e "
                                    '"SELECT @@GLOBAL.max_allowed_packet"'
                                ).strip(),
                            )
                            namespace["shell"] = shell

            finally:
                subprocess.run(
                    [docker, "rm", "-f", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    def test_external_packet_change_before_raise_is_preserved(self):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        for replacement in (8 << 20, 128 << 20, 256 << 20):
            with self.subTest(replacement=replacement):
                current = [4 << 20]

                def prepare(command):
                    snapshot = current[0]
                    current[0] = replacement
                    if "SET GLOBAL max_allowed_packet" in command:
                        snapshot = current[0]
                        current[0] = max(snapshot, 128 << 20)
                    return str(snapshot)

                namespace = packet_namespace(
                    {
                        "shell": prepare,
                        "shell_no_pipe": lambda c: set_packet_value(
                            c, current
                        ),
                        "shell_quote": shlex.quote,
                        "contextmanager": contextmanager,
                    }
                )
                exec(
                    compile(
                        ast.Module(body=helpers, type_ignores=[]),
                        str(SOURCE),
                        "exec",
                    ),
                    namespace,
                )
                with namespace["mysql_restore_packet_limit"]("", 3306, ""):
                    self.assertGreaterEqual(current[0], 128 << 20)
                self.assertEqual(replacement, current[0])

    def test_external_packet_change_is_preserved(self):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        for replacement in (8 << 20, 256 << 20):
            for fails in (False, True):
                with self.subTest(replacement=replacement, fails=fails):
                    current = [4 << 20]

                    def execute(command):
                        set_packet_value(command, current)

                    def prepare(command):
                        snapshot = current[0]
                        current[0] = max(snapshot, 128 << 20)
                        return str(snapshot)

                    namespace = packet_namespace(
                        {
                            "shell": prepare,
                            "shell_no_pipe": execute,
                            "shell_quote": shlex.quote,
                            "contextmanager": contextmanager,
                        }
                    )
                    exec(
                        compile(
                            ast.Module(body=helpers, type_ignores=[]),
                            str(SOURCE),
                            "exec",
                        ),
                        namespace,
                    )
                    try:
                        with namespace["mysql_restore_packet_limit"](
                            "", 3306, ""
                        ):
                            current[0] = replacement
                            if fails:
                                raise ValueError("original SQL failure")
                    except ValueError as e:
                        self.assertTrue(fails)
                        self.assertEqual("original SQL failure", str(e))
                    self.assertEqual(replacement, current[0])

    def test_overlapping_packet_scope_is_rejected_before_import(self):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        held = [False]

        def popen(*args, **kwargs):
            process = packet_process()
            owns = not held[0]
            process.stdout.readline.return_value = "1\n" if owns else "0\n"
            if owns:
                held[0] = True
                process.__exit__.side_effect = lambda *a: held.__setitem__(
                    0, False
                )
            return process

        namespace = packet_namespace(
            {
                "shell": lambda c: "4194304",
                "shell_no_pipe": lambda c: None,
                "shell_quote": shlex.quote,
                "contextmanager": contextmanager,
            }
        )
        namespace["subprocess"].Popen = popen
        exec(
            compile(
                ast.Module(body=helpers, type_ignores=[]), str(SOURCE), "exec"
            ),
            namespace,
        )
        with namespace["mysql_restore_packet_limit"]("", 3306, ""):
            with self.assertRaisesRegex(RuntimeError, "packet.*lock"):
                with namespace["mysql_restore_packet_limit"]("", 3306, ""):
                    self.fail("overlapping operation reached import")
        self.assertFalse(held[0])
        with namespace["mysql_restore_packet_limit"]("", 3306, ""):
            pass

    def test_default_restore_rejects_changed_volume_path_before_deletion(self):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        check_class = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef)
            and n.name == "RestoreMysqlPreCheckCmd"
        )
        restore_class = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "RestoreMysqlCmd"
        )
        run = next(
            n
            for n in restore_class.body
            if isinstance(n, ast.FunctionDef) and n.name == "run"
        )
        current = [4 << 20]
        calls = []
        factory = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "backup.gz"
            with gzip.open(backup, "wt") as output:
                output.write(
                    "INSERT INTO `VolumeEO` "
                    "VALUES ('volume-uuid','volume','old-path');\n"
                )

            def shell(command):
                if command.startswith("mysql "):
                    snapshot = current[0]
                    current[0] = max(snapshot, 128 << 20)
                    return str(snapshot)
                return subprocess.check_output(command, shell=True)

            def set_limit(command):
                calls.append(command)
                set_packet_value(command, current)

            def execute(command):
                self.assertEqual(128 << 20, current[0])
                if "show databases" in command:
                    return 0, "zstack\n", ""
                return (
                    0,
                    "volume-uuid\tvolume\told-path"
                    if "source " in command
                    else "",
                    "",
                )

            def error(message):
                raise ValueError(message)

            namespace = packet_namespace(
                dict(
                    shell=shell,
                    shell_no_pipe=set_limit,
                    Command=object,
                    shell_return_stdout_stderr=execute,
                    shell_quote=shlex.quote,
                    contextmanager=contextmanager,
                    os=os,
                    tempfile=SimpleNamespace(
                        mkstemp=lambda: tempfile.mkstemp(dir=directory)
                    ),
                    CtlError=ValueError,
                    error=error,
                    info=lambda m: None,
                    warn=lambda m: None,
                    error_if_tool_is_missing=lambda tool: None,
                    check_gunzip_file=lambda path: None,
                    RestorerFactory=factory,
                    ctl=SimpleNamespace(
                        get_live_mysql_portal=lambda **kw: (
                            "localhost",
                            3306,
                            "",
                            "",
                        )
                    ),
                )
            )
            exec(
                compile(
                    ast.Module(
                        body=helpers + [check_class, run], type_ignores=[]
                    ),
                    str(SOURCE),
                    "exec",
                ),
                namespace,
            )
            check = namespace["RestoreMysqlPreCheckCmd"].__new__(
                namespace["RestoreMysqlPreCheckCmd"]
            )
            check.check_fail_list = []
            checked = []

            def internal_run(name, args):
                checked.append(name)
                self.assertEqual("check_restore_mysql", name)
                check.run(
                    SimpleNamespace(
                        from_file=str(backup), mysql_root_password=""
                    )
                )

            namespace["ctl"].internal_run = internal_run
            with self.assertRaisesRegex(
                ValueError, "install path.*has been changed"
            ):
                namespace["run"](
                    None,
                    SimpleNamespace(
                        from_file=str(backup),
                        mysql_root_password="",
                        ui_mysql_root_password=None,
                        skip_check=False,
                    ),
                )
            self.assertEqual(["check_restore_mysql"], checked)
            factory.get_restorer.assert_not_called()
            self.assertTrue(all("SET GLOBAL" in command for command in calls))
            self.assertEqual(4 << 20, current[0])
            self.assertEqual([backup], list(Path(directory).iterdir()))

    def test_precheck_preserves_source_error_when_limit_restore_fails(self):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef)
            and n.name == "RestoreMysqlPreCheckCmd"
        )
        method = next(
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "execute_sql"
        )
        warnings = []

        def execute(command):
            if "max_allowed_packet=134217728," in command:
                raise RuntimeError("packet restoration failed")

        namespace = {
            "shell": lambda command: "4194304",
            "shell_no_pipe": execute,
            "shell_return_stdout_stderr": lambda command: (
                1,
                "",
                "original source SQL error",
            ),
            "shell_quote": shlex.quote,
            "contextmanager": contextmanager,
            "CtlError": ValueError,
            "warn": warnings.append,
        }
        exec(
            compile(
                ast.Module(body=helpers + [method], type_ignores=[]),
                str(SOURCE),
                "exec",
            ),
            packet_namespace(namespace),
        )
        obj = SimpleNamespace(hostname="localhost", port=3306)
        with self.assertRaisesRegex(ValueError, "original source SQL error"):
            namespace["execute_sql"](obj, "", "source /tmp/backup.sql")
        self.assertEqual(1, len(warnings))

    def test_precheck_cleans_table_and_file_after_failures(self):
        tree = ast.parse(SOURCE.read_text())
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef)
            and n.name == "RestoreMysqlPreCheckCmd"
        )
        for raises in (False, True):
            with (
                self.subTest(raises=raises),
                tempfile.TemporaryDirectory() as directory,
            ):
                backup = Path(directory) / "backup.gz"
                with gzip.open(str(backup), "wt") as output:
                    output.write("INSERT INTO `VolumeEO` VALUES ('test');\n")
                created = []
                cleaned = []

                def mkstemp():
                    result = tempfile.mkstemp(dir=directory)
                    created.append(result[1])
                    return result

                def execute(password, sql):
                    if sql.startswith("show databases"):
                        return 0, "zstack\n", ""
                    if "source " in sql:
                        if raises:
                            raise RuntimeError("packet setup failed")
                        return 1, "", "invalid source SQL"
                    if "drop table if exists `TempVolumeEO`" in sql:
                        cleaned.append(sql)
                    return 0, "", ""

                def error(message):
                    raise RuntimeError(message)

                namespace = {
                    "Command": object,
                    "os": os,
                    "tempfile": SimpleNamespace(mkstemp=mkstemp),
                    "ctl": SimpleNamespace(
                        get_live_mysql_portal=lambda: (
                            "localhost",
                            3306,
                            "",
                            "",
                        )
                    ),
                    "shell": lambda c: subprocess.check_output(c, shell=True),
                    "error_if_tool_is_missing": lambda tool: None,
                    "CtlError": RuntimeError,
                    "error": error,
                    "info": lambda message: None,
                    "warn": lambda message: None,
                }
                exec(
                    compile(
                        ast.Module(body=[cls], type_ignores=[]),
                        str(SOURCE),
                        "exec",
                    ),
                    namespace,
                )
                check = namespace["RestoreMysqlPreCheckCmd"].__new__(
                    namespace["RestoreMysqlPreCheckCmd"]
                )
                check.execute_sql = execute
                check.check_fail_list = []
                with self.assertRaisesRegex(
                    RuntimeError,
                    "packet setup failed" if raises else "invalid source SQL",
                ):
                    check.run(
                        SimpleNamespace(
                            from_file=str(backup), mysql_root_password=""
                        )
                    )
                self.assertEqual(
                    1,
                    len(cleaned),
                    "precheck must remove TempVolumeEO after a failed source",
                )
                self.assertTrue(
                    created and all(not Path(p).exists() for p in created),
                    "precheck SQL file must be removed",
                )

    def test_restore_failure_preserves_original_sql_error(self):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "RestoreMysqlCmd"
        )
        method = next(
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "restore_database"
        )
        for import_fails in (True, False):
            with self.subTest(import_fails=import_fails):
                warnings = []

                def execute(command):
                    if command == "import database" and import_fails:
                        raise ValueError("original SQL error")
                    if "max_allowed_packet=134217728," in command:
                        raise RuntimeError("packet restore failed")

                namespace = {
                    "shell": lambda command: "4194304",
                    "shell_no_pipe": execute,
                    "shell_quote": shlex.quote,
                    "contextmanager": contextmanager,
                    "warn": warnings.append,
                }
                exec(
                    compile(
                        ast.Module(body=helpers + [method], type_ignores=[]),
                        str(SOURCE),
                        "exec",
                    ),
                    packet_namespace(namespace),
                )
                expected, message = (
                    (ValueError, "original SQL error")
                    if import_fails
                    else (RuntimeError, "packet restore failed")
                )
                with self.assertRaisesRegex(expected, message):
                    namespace["restore_database"](
                        None, "import database", "", 3306, ""
                    )
                self.assertEqual(1 if import_fails else 0, len(warnings))

    def test_precheck_uses_same_limit_and_keeps_source_errors(self):
        tree = ast.parse(SOURCE.read_text())
        helpers = packet_helpers(tree)
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef)
            and n.name == "RestoreMysqlPreCheckCmd"
        )
        method = next(
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "execute_sql"
        )
        current = [4 << 20]

        def set_limit(command):
            set_packet_value(command, current)

        def execute(command):
            self.assertGreaterEqual(current[0], 128 << 20)
            self.assertIn("--abort-source-on-error", command)
            self.assertIn("--max-allowed-packet=1G", command)
            return 1, "", "source failed"

        def prepare(command):
            snapshot = current[0]
            current[0] = max(snapshot, 128 << 20)
            return str(snapshot)

        namespace = {
            "shell": prepare,
            "shell_no_pipe": set_limit,
            "shell_quote": shlex.quote,
            "contextmanager": contextmanager,
            "shell_return_stdout_stderr": execute,
            "CtlError": RuntimeError,
        }
        exec(
            compile(
                ast.Module(body=helpers + [method], type_ignores=[]),
                str(SOURCE),
                "exec",
            ),
            packet_namespace(namespace),
        )
        obj = type("Precheck", (), {"port": 3306, "hostname": "localhost"})()
        with self.assertRaisesRegex(RuntimeError, "source failed"):
            namespace["execute_sql"](obj, "", "source /tmp/backup.sql")
        self.assertEqual(4 << 20, current[0])

    def test_restore_preserves_packet_limit_and_import_result(self):
        tree = ast.parse(SOURCE.read_text())
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "RestoreMysqlCmd"
        )
        methods = [
            n
            for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "restore_database"
        ]
        self.assertTrue(
            methods,
            "restore_mysql does not prepare the server packet limit "
            "before importing",
        )
        for original, import_fails in [
            (4 << 20, False),
            (4 << 20, True),
            (128 << 20, False),
            (256 << 20, False),
        ]:
            with self.subTest(original=original, import_fails=import_fails):
                current = [original]
                calls = []

                def execute(command):
                    calls.append(command)
                    if command == "import database":
                        self.assertGreaterEqual(current[0], 128 << 20)
                        if import_fails:
                            raise RuntimeError("original import failure")
                    else:
                        set_packet_value(command, current)

                helpers = packet_helpers(tree)

                def prepare(command):
                    calls.append(command)
                    snapshot = current[0]
                    current[0] = max(snapshot, 128 << 20)
                    return str(snapshot)

                namespace = {
                    "shell": prepare,
                    "shell_no_pipe": execute,
                    "shell_quote": shlex.quote,
                    "contextmanager": contextmanager,
                }
                module = ast.Module(body=helpers + methods, type_ignores=[])
                exec(
                    compile(module, str(SOURCE), "exec"),
                    packet_namespace(namespace),
                )
                restore = namespace["restore_database"]
                if import_fails:
                    with self.assertRaisesRegex(
                        RuntimeError, "original import failure"
                    ):
                        restore(
                            None,
                            "import database",
                            "pass';&",
                            3307,
                            "192.0.2.1",
                        )
                else:
                    restore(
                        None, "import database", "pass';&", 3307, "192.0.2.1"
                    )
                self.assertEqual(
                    original,
                    current[0],
                    "restore must restore the original global packet limit",
                )
                self.assertEqual(2 if original >= 128 << 20 else 3, len(calls))
                for command in calls:
                    if command != "import database":
                        self.assertIn(shlex.quote("pass';&"), command)
                        self.assertIn("-P 3307", command)
                        self.assertIn("--host=192.0.2.1", command)


if __name__ == "__main__":
    unittest.main()

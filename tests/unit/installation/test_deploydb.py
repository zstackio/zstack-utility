"""Exercise the existing online/offline deploydb shell entry points."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class StandardDeployDbTest(unittest.TestCase):
    def test_installer_create_keep_drop_pass_standard_arguments(self):
        root = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory(prefix="standard-deploydb-") as temporary:
            for name in ("install.sh", "online_install.sh"):
                source = (root / "installation" / name).read_text()
                function = re.search(r"(?ms)^cs_deploy_db\(\)\s*\{\n.*?^\}", source).group(0)
                for drop, keep, expected in (("", "", []), ("y", "", ["--drop"]),
                                              ("", "y", ["--keep-db"])):
                    with self.subTest(installer=name, drop=drop, keep=keep):
                        calls = Path(temporary) / "ctl-arguments"
                        env = os.environ.copy()
                        env.update(NEED_DROP_DB=drop, NEED_KEEP_DB=keep,
                                   MYSQL_NEW_ROOT_PASSWORD="fixture", MYSQL_ROOT_PASSWORD="fixture",
                                   MYSQL_USER_PASSWORD="fixture", MANAGEMENT_IP="127.0.0.1",
                                   ZSTACKCTL_INSTALL_LOG=str(Path(temporary) / "ctl.log"),
                                   ZSTACK_INSTALL_LOG=str(Path(temporary) / "installer.log"),
                                   CALL_LOG=str(calls))
                        stubs = """
traplogger() { :; }
echo_subtitle() { :; }
pass() { :; }
fail() { exit 1; }
zstack-ctl() { printf '%s\\n' "$@" > "$CALL_LOG"; }
"""
                        subprocess.check_call(["bash", "-c", stubs + function + "\ncs_deploy_db"], env=env)
                        arguments = calls.read_text().splitlines()
                        self.assertEqual("deploydb", arguments[0])
                        flags = [argument for argument in arguments
                                 if argument.startswith("--") and "=" not in argument]
                        self.assertEqual(expected, flags)
                        self.assertIn("--root-password=fixture", arguments)
                        self.assertIn("--zstack-password=fixture", arguments)


if __name__ == "__main__":
    unittest.main()

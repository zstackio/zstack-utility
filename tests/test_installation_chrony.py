import re
import subprocess
import tempfile
import unittest
from pathlib import Path


INSTALL_SCRIPT = Path(__file__).parents[1] / "installation" / "install.sh"


def shell_function(source, name):
    match = re.search(rf"(?ms)^{name}\(\) \{{\n.*?^\}}\n", source)
    assert match, f"missing function {name}"
    return match.group(0)


def run_default_config(existing_config="", management_ip4="", management_ip6="2001:db8::10"):
    source = INSTALL_SCRIPT.read_text()
    functions = "\n".join(
        shell_function(source, name)
        for name in ("has_chrony_server_config", "configure_default_chrony_servers")
    )
    script = f"""
{functions}
zstack-ctl() {{
    if [ "$1" = show_configuration ]; then
        printf '%s\\n' "$EXISTING_CONFIG"
    elif [ "$1" = get_configuration ] && [ "$2" = management.server.ip4 ]; then
        printf '%s\\n' "$MOCK_MANAGEMENT_IP4"
    elif [ "$1" = get_configuration ] && [ "$2" = management.server.ip6 ]; then
        printf '%s\\n' "$MOCK_MANAGEMENT_IP6"
    elif [ "$1" = configure ]; then
        printf '%s\\n' "$2"
    fi
}}
MANAGEMENT_IP=192.168.1.10
MANAGEMENT_IP6=
configure_default_chrony_servers
"""
    result = subprocess.run(
        ["bash", "-c", script],
        check=True,
        text=True,
        capture_output=True,
        env={
            "EXISTING_CONFIG": existing_config,
            "MOCK_MANAGEMENT_IP4": management_ip4,
            "MOCK_MANAGEMENT_IP6": management_ip6,
        },
    )
    return result.stdout.splitlines()


def run_explicit_config(existing_config, chrony_server_ip, fail_delete=""):
    source = INSTALL_SCRIPT.read_text()
    function = shell_function(source, "configure_chrony_servers")
    script = f"""
{function}
fail2() {{
    printf '%s\n' "$1" >&2
    exit 1
}}
zstack-ctl() {{
    if [ "$1" = show_configuration ]; then
        cat "$STATE_FILE"
    elif [ "$1" = configure ] && [ "$2" = --delete ]; then
        [ "$3" = "$FAIL_DELETE" ] && return 1
        awk -F= -v key="$3" '$1 != key' "$STATE_FILE" > "$STATE_FILE.tmp"
        mv "$STATE_FILE.tmp" "$STATE_FILE"
    elif [ "$1" = configure ]; then
        key="${{2%%=*}}"
        awk -F= -v key="$key" '$1 != key' "$STATE_FILE" > "$STATE_FILE.tmp"
        mv "$STATE_FILE.tmp" "$STATE_FILE"
        printf '%s\n' "$2" >> "$STATE_FILE"
    fi
}}
CHRONY_SERVER_IP="$MOCK_CHRONY_SERVER_IP"
configure_chrony_servers
cat "$STATE_FILE"
"""
    with tempfile.TemporaryDirectory() as temporary_directory:
        state_file = Path(temporary_directory) / "chrony-state"
        state_file.write_text(existing_config)
        return subprocess.run(
            ["bash", "-c", script],
            check=False,
            text=True,
            capture_output=True,
            env={
                "STATE_FILE": str(state_file),
                "MOCK_CHRONY_SERVER_IP": chrony_server_ip,
                "FAIL_DELETE": fail_delete,
            },
        )


class InstallationChronyTest(unittest.TestCase):
    def test_default_chrony_uses_both_management_families(self):
        self.assertEqual(
            run_default_config(),
            [
                "chrony.serverIp.0=192.168.1.10",
                "chrony.serverIp.1=2001:db8::10",
            ],
        )

    def test_default_chrony_deduplicates_primary_and_ip4(self):
        self.assertEqual(
            run_default_config(management_ip4="192.168.1.10"),
            [
                "chrony.serverIp.0=192.168.1.10",
                "chrony.serverIp.1=2001:db8::10",
            ],
        )

    def test_existing_explicit_chrony_config_is_preserved(self):
        self.assertEqual(run_default_config("chrony.serverIp.7 = 10.0.0.7"), [])

    def test_explicit_chrony_replaces_all_numbered_entries(self):
        result = run_explicit_config(
            "chrony.serverIp.0=192.168.1.10\n"
            "chrony.serverIp.1=2001:db8::10\n"
            "unrelated.property=value\n",
            "10.0.0.10",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            ["unrelated.property=value", "chrony.serverIp.0=10.0.0.10"],
        )

    def test_explicit_chrony_stops_when_stale_entry_cannot_be_deleted(self):
        result = run_explicit_config(
            "chrony.serverIp.0=192.168.1.10\nchrony.serverIp.1=2001:db8::10\n",
            "10.0.0.10",
            fail_delete="chrony.serverIp.1",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Failed to delete chrony.serverIp.1", result.stderr)

    def test_installer_uses_exact_management_ip_lookup(self):
        source = INSTALL_SCRIPT.read_text()
        self.assertNotIn("grep '^[[:space:]]*management.server.ip'", source)
        self.assertNotIn("grep 'management.server.ip'", source)


if __name__ == "__main__":
    unittest.main()

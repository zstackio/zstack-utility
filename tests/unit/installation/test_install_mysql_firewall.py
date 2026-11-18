import json
import shlex
import subprocess
from pathlib import Path


INSTALL_SCRIPT = Path(__file__).resolve().parents[3] / "installation" / "install.sh"


def _shell_function(name):
    lines = INSTALL_SCRIPT.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("%s()" % name))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start:end + 1])


def _run_mysql_firewall(management_ip, saved_rules, zsha2_config=None):
    if zsha2_config is None:
        zsha2 = "zsha2() { return 1; }"
    else:
        config = shlex.quote(json.dumps(zsha2_config))
        zsha2 = f"zsha2() {{ printf '%s\\n' {config}; }}"

    script = """
{is_ipv6_address}
{get_zsha2_db_vip}
{cs_append_iptables}

traplogger() {{ :; }}
echo_subtitle() {{ :; }}
pass() {{ :; }}
service() {{ :; }}
{zsha2}
iptables-save() {{ printf '%s\\n' "$SAVED_RULES"; }}
ip6tables-save() {{ printf '%s\\n' "$SAVED_RULES"; }}
iptables() {{ printf 'iptables %s\\n' "$*" >> "$CALLS"; }}
ip6tables() {{ printf 'ip6tables %s\\n' "$*" >> "$CALLS"; }}

NEED_SET_MN_IP=y
MANAGEMENT_IP={management_ip}
ZSTACK_INSTALL_LOG=/dev/null
SAVED_RULES={saved_rules}
CALLS=`mktemp`
cs_append_iptables >/dev/null
trap - DEBUG
cat "$CALLS"
rm -f "$CALLS"
""".format(
        is_ipv6_address=_shell_function("is_ipv6_address"),
        get_zsha2_db_vip=_shell_function("get_zsha2_db_vip"),
        cs_append_iptables=_shell_function("cs_append_iptables"),
        zsha2=zsha2,
        management_ip=shlex.quote(management_ip),
        saved_rules=shlex.quote(saved_rules),
    )
    return subprocess.run(
        ["bash"], input=script, text=True, capture_output=True, check=True
    ).stdout.splitlines()


def test_zstac_86770_ha_vip_is_allowed_before_mysql_reject():
    calls = _run_mysql_firewall(
        "172.26.110.89",
        "-A INPUT -p tcp -m tcp --dport 3306 -j REJECT",
        {
            "nodeip": "172.26.110.89",
            "peerip": "172.26.108.210",
            "dbvip": "172.26.195.158",
        },
    )

    assert (
        "iptables -I INPUT -p tcp --dport 3306 -d 172.26.195.158 -j ACCEPT"
        in calls
    )
    assert "iptables -A INPUT -p tcp --dport 3306 -j REJECT" not in calls


def test_zstac_86770_existing_ha_vip_rule_is_not_duplicated():
    calls = _run_mysql_firewall(
        "172.26.110.89",
        "\n".join(
            [
                "-A INPUT -p tcp -m tcp --dport 3306 -j REJECT",
                "-A INPUT -d 172.26.110.89/32 -p tcp -m tcp --dport 3306 -j ACCEPT",
                "-A INPUT -d 172.26.195.158/32 -p tcp -m tcp --dport 3306 -j ACCEPT",
                "-A INPUT -d 127.0.0.1/32 -p tcp -m tcp --dport 3306 -j ACCEPT",
            ]
        ),
        {"dbvip": "172.26.195.158"},
    )

    assert calls == []


def test_zstac_86770_non_ha_install_keeps_existing_firewall_behavior():
    calls = _run_mysql_firewall(
        "172.26.110.89",
        "-A INPUT -p tcp -m tcp --dport 3306 -j REJECT",
    )

    assert calls == [
        "iptables -I INPUT -p tcp --dport 3306 -d 172.26.110.89 -j ACCEPT",
        "iptables -I INPUT -p tcp --dport 3306 -d 127.0.0.1 -j ACCEPT",
    ]


def _run_license_server_firewall(saved_rules, has_iptables_service=True, firewalld_active=False):
    script = """
{allow_license_server_firewall_port}

systemctl() {{
    if [ "$1" = "is-active" ] && [ "$3" = "firewalld" ]; then
        [ "{firewalld_active}" = "1" ] && return 0 || return 1
    fi
    if [ "$1" = "list-unit-files" ] && [ "$2" = "iptables.service" ]; then
        [ "{has_iptables_service}" = "1" ] && printf 'iptables.service enabled\\n'
        return 0
    fi
    return 1
}}
firewall-cmd() {{ printf 'firewall-cmd %s\\n' "$*" >> "$CALLS"; return 1; }}
service() {{ printf 'service %s\\n' "$*" >> "$CALLS"; }}
iptables-save() {{ printf '%s\\n' "$SAVED_RULES"; }}
iptables() {{ printf 'iptables %s\\n' "$*" >> "$CALLS"; }}

LICENSE_SERVER_PORT=18201
ZSTACK_INSTALL_LOG=/dev/null
SAVED_RULES={saved_rules}
CALLS=`mktemp`
allow_license_server_firewall_port >/dev/null
cat "$CALLS"
rm -f "$CALLS"
""".format(
        allow_license_server_firewall_port=_shell_function("allow_license_server_firewall_port"),
        saved_rules=shlex.quote(saved_rules),
        has_iptables_service="1" if has_iptables_service else "0",
        firewalld_active="1" if firewalld_active else "0",
    )
    return subprocess.run(
        ["bash"], input=script, text=True, capture_output=True, check=True
    ).stdout.splitlines()


def test_zstac_91565_license_server_opens_18201_and_saves_iptables():
    calls = _run_license_server_firewall(
        "-A INPUT -p tcp -m tcp --dport 8080 -j ACCEPT",
        has_iptables_service=True,
    )
    assert calls == [
        "iptables -I INPUT -p tcp -m tcp --dport 18201 -j ACCEPT",
        "service iptables save",
    ]


def test_zstac_91565_license_server_firewall_is_idempotent():
    calls = _run_license_server_firewall(
        "-A INPUT -p tcp -m tcp --dport 18201 -j ACCEPT",
        has_iptables_service=True,
    )
    assert calls == ["service iptables save"]


def test_zstac_91565_license_server_skips_service_save_when_unit_absent():
    calls = _run_license_server_firewall(
        "",
        has_iptables_service=False,
    )
    assert calls == ["iptables -I INPUT -p tcp -m tcp --dport 18201 -j ACCEPT"]

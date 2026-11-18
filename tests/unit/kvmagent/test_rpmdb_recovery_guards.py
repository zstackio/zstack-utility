"""Run both recovery implementations' shell in an isolated filesystem.

Load only recovery functions to avoid importing Ansible/libvirt services.
Signals and package commands are replaced with recording shell functions.
"""
import ast
import shlex
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(params=[
    "kvmagent/kvmagent/plugins/host_plugin.py",
    "zstacklib/ansible/zstacklib.py",
], ids=["host", "ansible"])
def recovery(request):
    path = Path(__file__).parents[3] / request.param
    tree = ast.parse(path.read_text())
    names = {
        "_parse_package_processes", "_list_package_processes",
        "_package_process_list_command", "_terminate_package_processes",
        "_rpmdb_user_scan_command", "_backup_and_rebuild_rpmdb",
    }
    tree.body = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"RPMDB_REPAIR_STALE_SECONDS": 60}
    exec(compile(tree, str(path), "exec"), namespace)
    commands = []

    def capture(command, *args, **kwargs):
        commands.append(command)
        return (True, "") if kwargs.get("return_output") else None

    namespace["_run_rpmdb_repair_command"] = capture
    namespace["bash_roe"] = lambda command: (commands.append(command) or 0, "", "")

    def command(name, *args):
        arguments = (*args, object()) if "ansible" in request.param else args
        namespace[name](*arguments)
        return commands[-1]

    return namespace, command


def run_shell(command, prefix=""):
    subprocess.run(["bash", "-n"], input=command, text=True, check=True)
    return subprocess.run(["bash", "-c", prefix + command], text=True,
                          capture_output=True, timeout=10)


def write_stat(path, ticks):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("123 (yum worker) " + " ".join(["S"] + ["0"] * 18 + [str(ticks)]))


def test_parse_keeps_start_identity(recovery):
    namespace, _ = recovery
    processes = namespace["_parse_package_processes"]("123 S 120 456 yum yum install foo\n")
    assert processes == [{"pid": 123, "stat": "S", "etimes": 120,
                          "start_ticks": 456, "comm": "yum", "args": "yum install foo"}]
    assert namespace["_parse_package_processes"]("123 S 120 bad yum yum install foo\n") == []


def test_process_snapshot_keeps_identity_and_excludes_own_group(recovery, tmp_path):
    namespace, command = recovery
    proc = tmp_path / "proc"
    write_stat(proc / "123/stat", 456)
    write_stat(proc / "124/stat", 789)
    script = command("_list_package_processes").replace("/proc/", str(proc) + "/")
    result = run_shell(script, """
ps() {
    case "$*" in *'-p '*) echo 999; return ;; esac
    printf '123 1 777 S 120 yum /usr/bin/yum install foo\n'
    printf '124 1 999 S 120 rpm rpm -qa\n'
}
""")
    assert result.returncode == 0, result.stderr
    assert namespace["_parse_package_processes"](result.stdout) == [
        {"pid": 123, "stat": "S", "etimes": 120, "start_ticks": 456,
         "comm": "yum", "args": "/usr/bin/yum install foo"},
    ]


@pytest.mark.parametrize("scenario,expected", [
    ("stale", ["-TERM 123", "-KILL 123"]),
    ("reused_before_term", []),
    ("young", []),
    ("d_state", []),
    ("zombie", []),
    ("other_command", []),
    ("python_yum", ["-TERM 123", "-KILL 123"]),
    ("reused_before_kill", ["-TERM 123"]),
    ("young_before_kill", ["-TERM 123"]),
    ("d_before_kill", ["-TERM 123"]),
    ("other_command_before_kill", ["-TERM 123"]),
    ("survives_kill", ["-TERM 123", "-KILL 123"]),
    ("reused_after_kill", ["-TERM 123", "-KILL 123"]),
])
def test_signals_revalidate_process(recovery, tmp_path, scenario, expected):
    _, command = recovery
    proc = tmp_path / "proc"
    stat = proc / "123/stat"
    write_stat(stat, 789 if scenario == "reused_before_term" else 456)
    info = tmp_path / "info"
    info.write_text({
        "young": "2 S yum /usr/bin/yum install foo",
        "d_state": "120 D yum /usr/bin/yum install foo",
        "zombie": "120 Z yum /usr/bin/yum install foo",
        "other_command": "120 S backup backup-rpm-files",
        "python_yum": "120 S python3 /usr/bin/python3 /usr/bin/yum install foo",
    }.get(scenario, "120 S yum /usr/bin/yum install foo"))
    events = tmp_path / "signals"
    events.touch()
    after_term = ":"
    if scenario == "reused_before_kill":
        after_term = "sed -i 's/456$/789/' " + shlex.quote(str(stat))
    if scenario == "young_before_kill":
        after_term = "printf '2 S yum /usr/bin/yum' > " + shlex.quote(str(info))
    if scenario == "d_before_kill":
        after_term = "printf '120 D yum /usr/bin/yum' > " + shlex.quote(str(info))
    if scenario == "other_command_before_kill":
        after_term = "printf '120 S backup backup-rpm-files' > " + shlex.quote(str(info))
    if scenario == "reused_after_kill":
        after_term = '[ "$1" != 2 ] || sed -i \'s/456$/789/\' ' + shlex.quote(str(stat))
    script = command("_terminate_package_processes", [{"pid": 123, "start_ticks": 456}])
    script = script.replace("/proc/", str(proc) + "/")
    result = run_shell(script, """
ps() { cat %s; }
kill() {
    if [ "$1" = '-0' ]; then
        %s
        ! grep -q '^-KILL ' %s
        return
    fi
    printf '%%s\n' "$*" >> %s
}
sleep() { %s; }
""" % (shlex.quote(str(info)),
           "return 0" if scenario in ("survives_kill", "reused_after_kill") else ":",
           shlex.quote(str(events)),
           shlex.quote(str(events)), after_term))
    assert result.returncode == (2 if scenario == "survives_kill" else 0), result.stdout + result.stderr
    assert events.read_text().splitlines() == expected


@pytest.mark.parametrize("scenario", [
    "idle", "package_before_backup", "package_after_backup",
    "fd_before_backup", "fd_after_backup", "ps_failed", "scan_failed",
    "same_group_package",
])
def test_rebuild_checks_occupancy_twice(recovery, tmp_path, scenario):
    _, command = recovery
    db = tmp_path / "rpmdb"
    db.mkdir()
    (db / "Packages").write_text("rpmdb")
    lock = db / "__db.001"
    lock.write_text("lock")
    proc = tmp_path / "proc"
    fd_dir = proc / "900000001/fd"
    fd_dir.mkdir(parents=True)
    if scenario == "fd_before_backup":
        (fd_dir / "1").symlink_to(db / "Packages")
    busy = tmp_path / "busy"
    if scenario in ("package_before_backup", "same_group_package"):
        busy.touch()
    events = tmp_path / "events"
    events.touch()
    backup_dir = tmp_path / "backups"
    script = command("_backup_and_rebuild_rpmdb")
    script = script.replace("/proc/", str(proc) + "/")
    script = script.replace("/var/lib/zstack/rpmdb-backups", str(backup_dir))
    inject = ":"
    if scenario == "package_after_backup":
        inject = "touch " + shlex.quote(str(busy))
    if scenario == "fd_after_backup":
        inject = "ln -s %s %s" % (shlex.quote(str(db / "__db.001")),
                                      shlex.quote(str(fd_dir / "1")))
    prefix = """
rpm() {
    if [ "$1" = '--eval' ]; then printf '%%s\n' %s; return; fi
    printf '%%s\n' "$*" >> %s
}
ps() {
    case "$*" in *pgid=*'-p '*) echo 999; return ;; esac
    %s
    [ -f %s ] || return 0
    printf '900000001 1 %s S 120 rpm rpm -qa\n'
}
timeout() { shift 3; "$@"; }
tar() { echo backup >> %s; touch "$2"; %s; }
%s
""" % (shlex.quote(str(db)), shlex.quote(str(events)),
           "return 1" if scenario == "ps_failed" else ":",
           shlex.quote(str(busy)), "999" if scenario == "same_group_package" else "777",
           shlex.quote(str(events)), inject,
           "python3() { return 1; }" if scenario == "scan_failed" else "")
    result = run_shell(script, prefix)
    success = scenario in ("idle", "same_group_package")
    assert result.returncode == (0 if success else 2), result.stdout + result.stderr
    assert lock.exists() is not success
    actions = events.read_text().splitlines()
    assert ("--rebuilddb" in actions) is success
    assert ("backup" in actions) is (success or scenario.endswith("after_backup"))
    assert bool(list(backup_dir.glob("*.tar.gz"))) is success

import argparse
import os
import re
import subprocess
import tempfile
import time
import types
from pathlib import Path


def _load_upgrade_commands():
    path = Path(__file__).resolve().parents[3] / 'zstackctl/zstackctl/ctl.py'
    source = path.read_text()
    module = types.ModuleType('upgrade_commands')
    module.__dict__.update(os=os, tempfile=tempfile, time=time, Command=object, CtlError=RuntimeError)
    module.Ctl = type('Ctl', (), {'ZSTACK_UI_DB_MIGRATE': ''})
    module.ctl = types.SimpleNamespace(zstack_home='', USER_ZSTACK_HOME_DIR='', ZSTACK_UI_DB_MIGRATE_SH='',
                                      get_db_url=None, get_ui_db_url=None, get_live_mysql_portal=None,
                                      check_if_management_node_has_stopped=None)
    module.mysql_db_config_script = ':'
    module.mysqldump_skip_tables = ''
    module.info = lambda *args: None
    module.error_if_tool_is_missing = lambda name: None
    module.shell = lambda cmd: subprocess.check_output(cmd, shell=True, text=True)
    module.shell_no_pipe = module.shell
    module.ShellCmd = lambda cmd: lambda: module.shell(cmd)
    for name in ('shell_quote', 'UpgradeDbCmd', 'UpgradeUIDbCmd'):
        match = re.search(r'^(?:def|class) %s\b.*?(?=^(?:def|class) |\Z)' % name, source, re.M | re.S)
        assert match is not None, name
        exec(compile(match.group(0), str(path), 'exec'), module.__dict__)
    return module


ctl = _load_upgrade_commands()


PASSWORD = "Tmp@&1 $x;2 q'u\"\\o`id`"
RECORDER_SCRIPT = """#!/bin/bash
{
    printf 'BEGIN:%s\\n' "$(basename "$0")"
    for arg in "$@"; do
        printf 'ARG:%s\\n' "$arg"
    done
    printf 'END\\n'
} >> "$ZSTAC_ARG_LOG"
"""


def _make_recorder(path):
    path.write_text(RECORDER_SCRIPT)
    path.chmod(0o755)


def _recorded_args(path, command):
    invocations = []
    current = None
    for line in path.read_text().splitlines():
        if line.startswith('BEGIN:'):
            current = {'command': line[6:], 'args': []}
        elif line == 'END':
            invocations.append(current)
            current = None
        elif line.startswith('ARG:'):
            current['args'].append(line[4:])
    return [invocation['args'] for invocation in invocations if invocation['command'] == command]


def _setup_upgrade_environment(monkeypatch, tmp_path, password):
    arg_log = tmp_path / 'args.log'
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    for command in ('mysql', 'mysqldump', 'mysqlcheck'):
        _make_recorder(bin_dir / command)

    zstack_home = tmp_path / 'zstack'
    flyway = zstack_home / 'WEB-INF/classes/tools/flyway-3.2.1/flyway'
    flyway.parent.mkdir(parents=True)
    _make_recorder(flyway)
    (zstack_home / 'WEB-INF/classes/db/upgrade').mkdir(parents=True)

    ui_migrate_dir = tmp_path / 'ui-migrate'
    ui_migrate_dir.mkdir()
    ui_migrate_script = tmp_path / 'ui-migrate.sh'
    _make_recorder(ui_migrate_script)

    monkeypatch.setenv('ZSTAC_ARG_LOG', str(arg_log))
    monkeypatch.setenv('PATH', '%s%s%s' % (bin_dir, os.pathsep, os.environ['PATH']))
    monkeypatch.setenv('x', 'EXPANDED')
    monkeypatch.setattr(ctl, 'info', lambda *args, **kwargs: None)
    monkeypatch.setattr(ctl, 'mysql_db_config_script', ':')
    monkeypatch.setattr(ctl.ctl, 'zstack_home', str(zstack_home))
    monkeypatch.setattr(ctl.ctl, 'USER_ZSTACK_HOME_DIR', str(tmp_path / 'home'))
    monkeypatch.setattr(ctl.ctl, 'ZSTACK_UI_DB_MIGRATE_SH', str(ui_migrate_script))
    monkeypatch.setattr(ctl.Ctl, 'ZSTACK_UI_DB_MIGRATE', str(ui_migrate_dir))
    monkeypatch.setattr(ctl.ctl, 'get_db_url', lambda: 'jdbc:mysql://127.0.0.1:3306/zstack')
    monkeypatch.setattr(ctl.ctl, 'get_ui_db_url', lambda: 'jdbc:mysql://127.0.0.1:3306/zstack_ui')
    monkeypatch.setattr(
        ctl.ctl,
        'get_live_mysql_portal',
        lambda *args, **kwargs: ('127.0.0.1', '3306', 'zstack', password),
    )
    monkeypatch.setattr(ctl.ctl, 'check_if_management_node_has_stopped', lambda force: None)
    return arg_log



def test_upgrade_db_preserves_complex_password_for_every_client(monkeypatch, tmp_path):
    marker = tmp_path / 'injected'
    password = '%s;touch %s' % (PASSWORD, marker)
    arg_log = _setup_upgrade_environment(monkeypatch, tmp_path, password)

    ctl.UpgradeDbCmd.__new__(ctl.UpgradeDbCmd).run(argparse.Namespace(
        force=True,
        no_backup=False,
        dry_run=False,
        update_schema_version=False,
    ))

    assert not marker.exists()
    mysqldump_args = _recorded_args(arg_log, 'mysqldump')
    mysql_args = _recorded_args(arg_log, 'mysql')
    flyway_args = _recorded_args(arg_log, 'flyway')
    assert mysqldump_args
    assert mysql_args
    assert flyway_args
    assert all('-p%s' % password in args for args in mysqldump_args)
    assert all('-p%s' % password in args for args in mysql_args)
    assert all('-password=%s' % password in args for args in flyway_args)


def test_upgrade_ui_db_preserves_complex_password_for_every_client(monkeypatch, tmp_path):
    marker = tmp_path / 'injected'
    password = '%s;touch %s' % (PASSWORD, marker)
    arg_log = _setup_upgrade_environment(monkeypatch, tmp_path, password)

    ctl.UpgradeUIDbCmd.__new__(ctl.UpgradeUIDbCmd).run(argparse.Namespace(
        force=True,
        no_backup=False,
        dry_run=False,
    ))

    assert not marker.exists()
    assert '-p%s' % password in _recorded_args(arg_log, 'mysqldump')[0]
    mysql_args = _recorded_args(arg_log, 'mysql')
    flyway_args = _recorded_args(arg_log, 'flyway')
    assert mysql_args
    assert flyway_args
    assert all('-p%s' % password in args for args in mysql_args)
    assert all('-password=%s' % password in args for args in flyway_args)
    assert password in _recorded_args(arg_log, 'ui-migrate.sh')[0]


def test_empty_password_omits_client_password_options(monkeypatch, tmp_path):
    arg_log = _setup_upgrade_environment(monkeypatch, tmp_path, '')

    ctl.UpgradeDbCmd.__new__(ctl.UpgradeDbCmd).run(argparse.Namespace(
        force=True,
        no_backup=False,
        dry_run=False,
        update_schema_version=False,
    ))
    ctl.UpgradeUIDbCmd.__new__(ctl.UpgradeUIDbCmd).run(argparse.Namespace(
        force=True,
        no_backup=False,
        dry_run=False,
    ))

    mysql_args = _recorded_args(arg_log, 'mysql')
    mysqldump_args = _recorded_args(arg_log, 'mysqldump')
    flyway_args = _recorded_args(arg_log, 'flyway')
    assert mysql_args
    assert mysqldump_args
    assert flyway_args
    mysql_family_args = mysql_args + mysqldump_args
    assert all(not any(arg.startswith('-p') for arg in args) for args in mysql_family_args)
    assert all(not any(arg.startswith('-password=') for arg in args) for args in flyway_args)
    assert 'zstack.ui.password' in _recorded_args(arg_log, 'ui-migrate.sh')[0]

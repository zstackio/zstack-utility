import argparse
import importlib
import json
import os
import sys
import types

def _install_module_stub(name):
    if name in sys.modules:
        return sys.modules[name], False
    try:
        return importlib.import_module(name), False
    except ImportError:
        module = types.ModuleType(name)
        sys.modules[name] = module
        return module, True


simplejson, simplejson_stubbed = _install_module_stub('simplejson')
if simplejson_stubbed:
    simplejson.dumps = json.dumps
    simplejson.loads = json.loads

configobj, configobj_stubbed = _install_module_stub('configobj')
if configobj_stubbed:
    configobj.ConfigObj = dict

termcolor, termcolor_stubbed = _install_module_stub('termcolor')
if termcolor_stubbed:
    termcolor.colored = lambda value, *args, **kwargs: value

yaml, yaml_stubbed = _install_module_stub('yaml')
if yaml_stubbed:
    yaml.load = lambda *args, **kwargs: {}
    yaml.dump = lambda *args, **kwargs: ''

for module_name in ('OpenSSL', 'jinja2'):
    _install_module_stub(module_name)

stubbed_modules = {}
for module_name in ('Crypto', 'Crypto.Cipher', 'Crypto.Cipher.AES', 'Crypto.Util', 'Crypto.Util.py3compat'):
    _, stubbed_modules[module_name] = _install_module_stub(module_name)
if stubbed_modules.get('Crypto.Cipher') or stubbed_modules.get('Crypto.Cipher.AES'):
    sys.modules['Crypto.Cipher'].AES = sys.modules['Crypto.Cipher.AES']
if stubbed_modules.get('Crypto.Util.py3compat'):
    sys.modules['Crypto.Util.py3compat'].__all__ = []

stubbed_modules = {}
for module_name in (
        'cryptography',
        'cryptography.hazmat',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.serialization',
        'cryptography.hazmat.primitives.serialization.pkcs12'):
    _, stubbed_modules[module_name] = _install_module_stub(module_name)
if stubbed_modules.get('cryptography.hazmat.primitives') or stubbed_modules.get(
        'cryptography.hazmat.primitives.serialization'):
    sys.modules['cryptography.hazmat.primitives'].serialization = sys.modules[
        'cryptography.hazmat.primitives.serialization']
if stubbed_modules.get('cryptography.hazmat.primitives.serialization') or stubbed_modules.get(
        'cryptography.hazmat.primitives.serialization.pkcs12'):
    sys.modules['cryptography.hazmat.primitives.serialization'].pkcs12 = sys.modules[
        'cryptography.hazmat.primitives.serialization.pkcs12']

from zstackctl import ctl


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


def test_flyway_precheck_preserves_complex_password(monkeypatch, tmp_path):
    arg_log = tmp_path / 'args.log'
    flyway = tmp_path / 'flyway'
    _make_recorder(flyway)
    monkeypatch.setenv('ZSTAC_ARG_LOG', str(arg_log))
    monkeypatch.setenv('x', 'EXPANDED')
    monkeypatch.setattr(ctl, 'info', lambda *args, **kwargs: None)

    ctl.run_flyway_precheck(
        str(flyway),
        'zstack',
        PASSWORD,
        'jdbc:mysql://127.0.0.1:3306/zstack',
        str(tmp_path / 'upgrade'),
    )

    assert _recorded_args(arg_log, 'flyway')[0] == [
        'info',
        '-outOfOrder=true',
        '-user=zstack',
        '-password=%s' % PASSWORD,
        '-url=jdbc:mysql://127.0.0.1:3306/zstack',
        '-locations=filesystem:%s' % (tmp_path / 'upgrade'),
    ]


def test_mysqlcheck_preserves_complex_password(monkeypatch, tmp_path):
    arg_log = tmp_path / 'args.log'
    mysqlcheck = tmp_path / 'mysqlcheck'
    _make_recorder(mysqlcheck)
    monkeypatch.setenv('ZSTAC_ARG_LOG', str(arg_log))
    monkeypatch.setenv('PATH', '%s%s%s' % (tmp_path, os.pathsep, os.environ['PATH']))
    monkeypatch.setenv('x', 'EXPANDED')

    ctl.run_mysqlcheck_zstack('zstack', PASSWORD, '127.0.0.1', '3306')

    assert _recorded_args(arg_log, 'mysqlcheck')[0] == [
        '-u',
        'zstack',
        '-p%s' % PASSWORD,
        '--host',
        '127.0.0.1',
        '--port',
        '3306',
        'zstack',
    ]


def test_upgrade_db_preserves_complex_password_for_every_client(monkeypatch, tmp_path):
    marker = tmp_path / 'injected'
    password = '%s;touch %s' % (PASSWORD, marker)
    arg_log = _setup_upgrade_environment(monkeypatch, tmp_path, password)

    ctl.UpgradeDbCmd.__new__(ctl.UpgradeDbCmd).run(argparse.Namespace(
        force=True,
        no_backup=False,
        dry_run=False,
        precheck_tables=True,
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
    assert '-p%s' % password in _recorded_args(arg_log, 'mysqlcheck')[0]


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
        precheck_tables=True,
        update_schema_version=False,
    ))
    ctl.UpgradeUIDbCmd.__new__(ctl.UpgradeUIDbCmd).run(argparse.Namespace(
        force=True,
        no_backup=False,
        dry_run=False,
    ))

    mysql_args = _recorded_args(arg_log, 'mysql')
    mysqldump_args = _recorded_args(arg_log, 'mysqldump')
    mysqlcheck_args = _recorded_args(arg_log, 'mysqlcheck')
    flyway_args = _recorded_args(arg_log, 'flyway')
    assert mysql_args
    assert mysqldump_args
    assert mysqlcheck_args
    assert flyway_args
    mysql_family_args = mysql_args + mysqldump_args + mysqlcheck_args
    assert all(not any(arg.startswith('-p') for arg in args) for args in mysql_family_args)
    assert all(not any(arg.startswith('-password=') for arg in args) for args in flyway_args)
    assert 'zstack.ui.password' in _recorded_args(arg_log, 'ui-migrate.sh')[0]

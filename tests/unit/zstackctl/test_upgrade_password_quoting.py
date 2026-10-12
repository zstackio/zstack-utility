import argparse
import importlib
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
import pytest


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


HERE = Path(__file__).resolve().parent
UTILITY = HERE.parents[2]
SOURCE_PACKAGE = UTILITY / 'zstackctl/zstackctl'
SOURCE_CTL = SOURCE_PACKAGE / 'ctl.py'
import zstackctl
if str(SOURCE_PACKAGE) not in zstackctl.__path__:
    zstackctl.__path__.insert(0, str(SOURCE_PACKAGE))
spec = importlib.util.spec_from_file_location('zstackctl.ctl', SOURCE_CTL)
ctl = importlib.util.module_from_spec(spec)
sys.modules['zstackctl.ctl'] = ctl
zstackctl.ctl = ctl
spec.loader.exec_module(ctl)
assert Path(ctl.__file__).resolve() == SOURCE_CTL.resolve()


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
    return [entry['args'] for entry in invocations if entry['command'] == command]


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
    monkeypatch.setattr(ctl.ctl, 'get_live_mysql_portal',
                        lambda *args, **kwargs: ('127.0.0.1', '3306', 'zstack', password))
    monkeypatch.setattr(ctl.ctl, 'check_if_management_node_has_stopped', lambda force: None)
    return arg_log


def test_flyway_precheck_preserves_complex_password(monkeypatch, tmp_path):
    arg_log = tmp_path / 'args.log'
    flyway = tmp_path / 'flyway'
    _make_recorder(flyway)
    monkeypatch.setenv('ZSTAC_ARG_LOG', str(arg_log))
    monkeypatch.setenv('x', 'EXPANDED')
    monkeypatch.setattr(ctl, 'info', lambda *args, **kwargs: None)

    ctl.run_flyway_precheck(str(flyway), 'zstack', PASSWORD,
                            'jdbc:mysql://127.0.0.1:3306/zstack', str(tmp_path / 'upgrade'))
    assert _recorded_args(arg_log, 'flyway')[0] == [
        'info', '-outOfOrder=true', '-user=zstack', '-password=%s' % PASSWORD,
        '-url=jdbc:mysql://127.0.0.1:3306/zstack',
        '-locations=filesystem:%s' % (tmp_path / 'upgrade')]


def test_mysqlcheck_preserves_complex_password(monkeypatch, tmp_path):
    arg_log = tmp_path / 'args.log'
    mysqlcheck = tmp_path / 'mysqlcheck'
    _make_recorder(mysqlcheck)
    monkeypatch.setenv('ZSTAC_ARG_LOG', str(arg_log))
    monkeypatch.setenv('PATH', '%s%s%s' % (tmp_path, os.pathsep, os.environ['PATH']))
    monkeypatch.setenv('x', 'EXPANDED')
    ctl.run_mysqlcheck_zstack('zstack', PASSWORD, '127.0.0.1', '3306')
    assert _recorded_args(arg_log, 'mysqlcheck')[0] == [
        '-u', 'zstack', '-p%s' % PASSWORD, '--host', '127.0.0.1', '--port', '3306', 'zstack']


def test_upgrade_db_preserves_complex_password_for_every_client(monkeypatch, tmp_path):
    marker = tmp_path / 'injected'
    password = '%s;touch %s' % (PASSWORD, marker)
    arg_log = _setup_upgrade_environment(monkeypatch, tmp_path, password)
    ctl.UpgradeDbCmd.__new__(ctl.UpgradeDbCmd).run(argparse.Namespace(
        force=True, no_backup=False, dry_run=False, precheck_tables=True,
        update_schema_version=False))
    assert not marker.exists()
    assert _recorded_args(arg_log, 'mysqldump')
    assert _recorded_args(arg_log, 'mysql')
    assert _recorded_args(arg_log, 'flyway')
    assert all('-p%s' % password in args for args in _recorded_args(arg_log, 'mysqldump'))
    assert all('-p%s' % password in args for args in _recorded_args(arg_log, 'mysql'))
    assert all('-password=%s' % password in args for args in _recorded_args(arg_log, 'flyway'))
    assert '-p%s' % password in _recorded_args(arg_log, 'mysqlcheck')[0]


def test_upgrade_ui_db_preserves_complex_password_for_every_client(monkeypatch, tmp_path):
    marker = tmp_path / 'injected'
    password = '%s;touch %s' % (PASSWORD, marker)
    arg_log = _setup_upgrade_environment(monkeypatch, tmp_path, password)
    ctl.UpgradeUIDbCmd.__new__(ctl.UpgradeUIDbCmd).run(argparse.Namespace(
        force=True, no_backup=False, dry_run=False))
    assert not marker.exists()
    assert '-p%s' % password in _recorded_args(arg_log, 'mysqldump')[0]
    assert all('-p%s' % password in args for args in _recorded_args(arg_log, 'mysql'))
    assert all('-password=%s' % password in args for args in _recorded_args(arg_log, 'flyway'))
    assert password in _recorded_args(arg_log, 'ui-migrate.sh')[0]


def test_empty_password_omits_client_password_options(monkeypatch, tmp_path):
    arg_log = _setup_upgrade_environment(monkeypatch, tmp_path, '')
    ctl.UpgradeDbCmd.__new__(ctl.UpgradeDbCmd).run(argparse.Namespace(
        force=True, no_backup=False, dry_run=False, precheck_tables=True,
        update_schema_version=False))
    ctl.UpgradeUIDbCmd.__new__(ctl.UpgradeUIDbCmd).run(argparse.Namespace(
        force=True, no_backup=False, dry_run=False))
    mysql_args = (_recorded_args(arg_log, 'mysql') + _recorded_args(arg_log, 'mysqldump') +
                  _recorded_args(arg_log, 'mysqlcheck'))
    flyway_args = _recorded_args(arg_log, 'flyway')
    assert mysql_args and flyway_args
    assert all(not any(arg.startswith('-p') for arg in args) for args in mysql_args)
    assert all(not any(arg.startswith('-password=') for arg in args) for args in flyway_args)
    assert 'zstack.ui.password' in _recorded_args(arg_log, 'ui-migrate.sh')[0]


def test_upgrade_db_dry_run_keeps_table_check_and_flyway_precheck(monkeypatch, tmp_path):
    arg_log = _setup_upgrade_environment(monkeypatch, tmp_path, '')
    ctl.UpgradeDbCmd.__new__(ctl.UpgradeDbCmd).run(argparse.Namespace(
        force=True, no_backup=True, dry_run=True, precheck_tables=True,
        update_schema_version=False))
    assert _recorded_args(arg_log, 'mysqlcheck')
    flyway = _recorded_args(arg_log, 'flyway')
    assert len(flyway) == 1 and flyway[0][0] == 'info'
    assert not _recorded_args(arg_log, 'mysqldump')


def test_upgrade_db_cli_keeps_common_flags_without_cohort_argument():
    parser = argparse.ArgumentParser()
    ctl.UpgradeDbCmd.__new__(ctl.UpgradeDbCmd).install_argparse_arguments(parser)
    parsed = parser.parse_args(['--force', '--no-backup', 'true', '--dry-run', '--precheck-tables'])
    assert parsed.force and parsed.no_backup == 'true' and parsed.dry_run and parsed.precheck_tables
    with pytest.raises(SystemExit):
        parser.parse_args(['--memory-migration-cohort', 'legacy-memory-1-to-5'])


def test_upgrade_ha_accepts_standard_installer_and_iso_arguments():
    ha = ctl.UpgradeHACmd.__new__(ctl.UpgradeHACmd)
    parser = argparse.ArgumentParser()
    ha.install_argparse_arguments(parser)
    parser.parse_args(['--zstack-enterprise-installer', '/tmp/enterprise-installer.run',
                       '--iso', '/tmp/zstack.iso'])


def test_ctl_main_help_omits_cohort_selector(monkeypatch, capsys):
    monkeypatch.setattr(ctl.ctl, 'locate_zstack_home',
                        lambda: setattr(ctl.ctl, 'zstack_home', '/tmp/zstackctl-help'))
    monkeypatch.setattr(ctl, 'create_log', lambda *args, **kwargs: None)
    monkeypatch.setattr(ctl, 'shell', lambda *args, **kwargs: None)
    monkeypatch.setattr(ctl.os, 'getuid', lambda: 0)
    monkeypatch.setattr(sys, 'argv', ['zstack-ctl', 'upgrade_db', '--help'])
    with pytest.raises(SystemExit) as result:
        ctl.main()
    assert result.value.code == 0
    output = capsys.readouterr().out
    assert '--memory-migration-cohort' not in output
    for switch in ('--force', '--no-backup', '--dry-run', '--precheck-tables'):
        assert switch in output

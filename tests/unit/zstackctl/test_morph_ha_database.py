import ast
import hashlib
import importlib.util
import io
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
import warnings
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
CTL = ROOT / 'zstackctl/zstackctl/ctl.py'


@pytest.fixture
def config_module():
    path = ROOT / 'zstackctl/zstackctl/morph_config.py'
    spec = importlib.util.spec_from_file_location('morph_config', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def configs(tmp_path):
    application = tmp_path / 'application.yml'
    region = tmp_path / 'region_config.yml'
    application.write_text(yaml.safe_dump({'spring': {'datasource': {
        'url': 'jdbc:mariadb://localhost:3306/morph',
        'username': 'morph', 'password': 'secret'}, 'flyway': {'enabled': True}}}))
    region.write_text(yaml.safe_dump({'extension': {'morphAddress': 'old-vip'},
                                     'cloud': {'region-1': {'url': 'external-region'}}}))
    return application, region


@pytest.mark.parametrize('vip,url', [
    ('172.24.228.228', 'jdbc:mariadb://172.24.228.228:3306/morph'),
    ('2001:db8::10', 'jdbc:mariadb://[2001:db8::10]:3306/morph'),
])
def test_shared_database_override_survives_application_upgrade(config_module, configs, vip, url):
    application, region = configs
    original = application.read_bytes()
    region.chmod(0o640)
    assert config_module.configure_ha_database(str(application), str(region), vip)
    data = yaml.safe_load(region.read_text())
    assert data['spring']['datasource']['url'] == url
    assert data['cloud']['region-1']['url'] == 'external-region'
    assert application.read_bytes() == original
    assert region.stat().st_mode & 0o777 == 0o640
    assert not config_module.configure_ha_database(str(application), str(region), vip)
    assert not list(region.parent.glob('.morph-config-*'))


def test_custom_port_options_and_explicit_flyway_url_share_vip(config_module, configs):
    application, region = configs
    application.write_text(yaml.safe_dump({'spring': {
        'datasource': {'url': 'jdbc:mysql://localhost:13306/morph?useSSL=false'},
        'flyway': {'url': 'jdbc:mysql://127.0.0.1:13306/morph?connectTimeout=5000'}}}))
    config_module.configure_ha_database(str(application), str(region), '172.24.228.228')
    spring = yaml.safe_load(region.read_text())['spring']
    assert spring['datasource']['url'] == 'jdbc:mysql://172.24.228.228:13306/morph?useSSL=false'
    assert spring['flyway']['url'] == 'jdbc:mysql://172.24.228.228:13306/morph?connectTimeout=5000'


@pytest.mark.parametrize('vip,url', [
    ('', 'jdbc:mariadb://localhost:3306/morph'),
    ('invalid-vip', 'jdbc:mariadb://localhost:3306/morph'),
    ('172.24.228.228', 'jdbc:mariadb:replication://node1,node2/morph'),
    ('172.24.228.228', 'jdbc:mariadb://user:secret@localhost/morph'),
    ('172.24.228.228', 'jdbc:mariadb://localhost:bad/morph'),
])
def test_invalid_endpoint_fails_before_configuration_write(config_module, configs, vip, url):
    application, region = configs
    application.write_text(yaml.safe_dump({'spring': {'datasource': {'url': url}}}))
    original = region.read_bytes()
    with pytest.raises(ValueError) as exc:
        config_module.configure_ha_database(str(application), str(region), vip)
    assert 'secret' not in str(exc.value)
    assert region.read_bytes() == original


@pytest.mark.parametrize('source,section', [
    ('application', 'datasource'), ('region', 'datasource'), ('application', 'flyway'),
])
def test_custom_database_endpoint_is_not_silently_replaced(config_module, configs, source, section):
    application, region = configs
    path = application if source == 'application' else region
    data = yaml.safe_load(path.read_text())
    data.setdefault('spring', {}).setdefault(section, {})['url'] = 'jdbc:mysql://db.example.test:3306/morph'
    path.write_text(yaml.safe_dump(data))
    originals = application.read_bytes(), region.read_bytes()
    with pytest.raises(ValueError, match='confirm-morph-db-vip'):
        config_module.configure_ha_database(str(application), str(region), '172.24.228.228')
    assert (application.read_bytes(), region.read_bytes()) == originals
    assert not list(region.parent.glob('.morph-ha-before-*'))


def test_explicit_custom_endpoint_takeover_retains_secure_originals(config_module, configs):
    application, region = configs
    data = yaml.safe_load(region.read_text())
    data['spring'] = {'datasource': {'url': 'jdbc:mysql://db.example.test:13306/morph?useSSL=false'},
                      'flyway': {'url': 'jdbc:mysql://migration.example.test:13306/morph'}}
    region.write_text(yaml.safe_dump(data))
    originals = application.read_bytes(), region.read_bytes()
    assert config_module.configure_ha_database(str(application), str(region), '172.24.228.228',
                                             allow_custom_endpoint=True)
    backups = list(region.parent.glob('.morph-ha-before-*'))
    assert len(backups) == 1
    assert backups[0].stat().st_mode & 0o777 == 0o700
    assert ((backups[0] / application.name).read_bytes(), (backups[0] / region.name).read_bytes()) == originals
    assert yaml.safe_load(region.read_text())['spring']['datasource']['url'] == 'jdbc:mysql://172.24.228.228:13306/morph?useSSL=false'
    assert not config_module.configure_ha_database(str(application), str(region), '172.24.228.228')
    assert list(region.parent.glob('.morph-ha-before-*')) == backups


@pytest.mark.parametrize('host', ['172.24.250.94', '[2001:db8::94]', '127.0.0.2'])
def test_managed_local_endpoints_migrate_without_confirmation(config_module, configs, host):
    application, region = configs
    data = yaml.safe_load(application.read_text())
    data['spring']['datasource']['url'] = 'jdbc:mariadb://%s:3306/morph' % host
    application.write_text(yaml.safe_dump(data))
    assert config_module.configure_ha_database(str(application), str(region), '172.24.228.228',
                                             local_hosts=('172.24.250.94', '2001:db8::94'))


def test_endpoint_check_failure_leaves_originals_and_creates_no_backup(config_module, configs):
    application, region = configs
    originals = application.read_bytes(), region.read_bytes()
    check = Mock(side_effect=RuntimeError('VIP unreachable'))
    with pytest.raises(RuntimeError, match='VIP unreachable'):
        config_module.configure_ha_database(str(application), str(region), '172.24.228.228', check_endpoint=check)
    assert (application.read_bytes(), region.read_bytes()) == originals
    assert not list(region.parent.glob('.morph-ha-before-*'))


def test_distinct_datasource_and_flyway_ports_checked_before_publish(config_module, configs):
    application, region = configs
    data = yaml.safe_load(application.read_text())
    data['spring']['flyway']['url'] = 'jdbc:mysql://localhost:13306/morph'
    application.write_text(yaml.safe_dump(data))
    original = region.read_bytes()
    observed = []
    def check(host, port):
        assert region.read_bytes() == original
        assert not list(region.parent.glob('.morph-ha-before-*'))
        observed.append((host, port))
    config_module.configure_ha_database(str(application), str(region), '172.24.228.228', check_endpoint=check)
    assert observed == [('172.24.228.228', 3306), ('172.24.228.228', 13306)]


@pytest.fixture
def service(tmp_path, config_module):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        tree = ast.parse(CTL.read_text())
    morph = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'MorphService')
    error = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'error')
    wrapper = next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'script_text' for target in node.targets))
    namespace = dict(os=os, time=time, sys=sys, uuid=uuid, socket=MagicMock(), hashlib=hashlib,
                     script_text=wrapper,
                     yaml=yaml, OrderedDict=OrderedDict, ExtraService=object,
                     get_default_ip=lambda: '172.24.250.94',
                     format_url_host=lambda host: '[%s]' % host if ':' in host else host,
                     shell_quote=shlex.quote,
                     configure_ha_database=Mock(return_value=False),
                     validate_database_hosts=config_module.validate_database_hosts if hasattr(config_module, 'validate_database_hosts') else None,
                     snapshot_file=lambda path: Path(path).read_bytes(),
                     restore_file=lambda path, data: Path(path).write_bytes(data),
                     shell_no_pipe=Mock(), info=Mock(), info_and_debug=Mock(), warn=Mock(),
                     colored=lambda message, *args: message,
                     CtlError=RuntimeError)
    exec(compile(ast.Module(body=[error, morph], type_ignores=[]), str(CTL), 'exec'), namespace)
    instance = namespace['MorphService']()
    instance.default_morph_config = str(tmp_path / 'application.yml')
    instance.default_morph_database_config = str(tmp_path / 'region_config.yml')
    instance.default_morph_service_path = str(tmp_path / 'morph.service')
    Path(instance.default_morph_config).write_text('spring:\n  datasource:\n    url: jdbc:mariadb://localhost:3306/morph\n')
    Path(instance.default_morph_database_config).write_text('extension:\n  morphAddress: old-vip\n')
    instance._wait_for_morph = Mock(return_value=True)
    peer = Mock()
    peer.config = {'dbvip': '172.24.228.228', 'nodeip': '172.24.250.94', 'peerip': '172.24.251.5'}
    def execute(command, *args):
        if command.startswith('sha256sum'):
            return hashlib.sha256(Path(instance.default_morph_database_config).read_bytes()).hexdigest()
        if 'tempfile.mkdtemp' in command:
            return str(tmp_path / '.morph-ha-before-test')
        if 'urlsplit' in command:
            return '["localhost"]'
        return ''
    peer.execute_on_peer.side_effect = execute
    instance.zsha2_utils = peer
    return instance, namespace, peer


@pytest.fixture
def peer_files(service, config_module, tmp_path):
    instance, namespace, peer = service
    remote_root = tmp_path / 'peer'
    remote_root.mkdir()
    variable_trap = remote_root / '.unexpected-shell-expansion'
    variable_trap.mkdir()
    application = remote_root / 'application.yml'
    region = remote_root / 'region_config.yml'
    application.write_text('spring:\n  datasource:\n    url: jdbc:mariadb://localhost:3306/morph\npeer: original\n')
    region.write_text('extension:\n  morphAddress: peer-original\n')
    namespace['configure_ha_database'].side_effect = config_module.configure_ha_database
    instance._check_ha_database_endpoint = Mock()
    events = []
    def execute(command, *args):
        events.append(command)
        if command.startswith('systemctl'):
            return ''
        command = command.replace(str(tmp_path), str(remote_root))
        script_path = str(remote_root / ('.ctl-%s.sh' % uuid.uuid4()))
        command = namespace['script_text'] % (script_path, command, script_path, '', script_path)
        result = subprocess.run(['bash', '-c', command], check=True, capture_output=True, text=True,
                                env=dict(os.environ, backup_dir=str(variable_trap)))
        return result.stdout.replace(str(remote_root), str(tmp_path))
    def copy(source, destination):
        if source in (instance.default_morph_config, instance.default_morph_database_config):
            shutil.copy2(source, remote_root / Path(destination).name)
    peer.execute_on_peer.side_effect = execute
    peer.scp_to_peer.side_effect = copy
    return instance, namespace, peer, application, region, events


@pytest.mark.parametrize('with_init', [False, True])
def test_preparation_failure_restores_both_originals_across_init_start(peer_files, with_init):
    instance, namespace, peer, application, region, events = peer_files
    local = Path(instance.default_morph_database_config)
    originals = local.read_bytes(), application.read_bytes(), region.read_bytes()
    if with_init:
        instance.init()
    execute = peer.execute_on_peer.side_effect
    def stop_failure(command, *args):
        if command == 'systemctl stop morph':
            raise RuntimeError('peer stop failed')
        return execute(command, *args)
    peer.execute_on_peer.side_effect = stop_failure
    with pytest.raises(RuntimeError, match='peer stop failed'):
        instance.start(do_init=with_init)
    assert (local.read_bytes(), application.read_bytes(), region.read_bytes()) == originals
    assert not any('start morph' in call.args[0] or 'restart morph' in call.args[0]
                   for call in namespace['shell_no_pipe'].call_args_list)


def test_partial_peer_copy_failure_restores_original_peer_content(peer_files):
    instance, namespace, peer, application, region, events = peer_files
    originals = Path(instance.default_morph_database_config).read_bytes(), region.read_bytes()
    copy = peer.scp_to_peer.side_effect
    def partial_failure(source, destination):
        copy(source, destination)
        raise RuntimeError('copy completed but acknowledgement failed')
    peer.scp_to_peer.side_effect = partial_failure
    with pytest.raises(RuntimeError, match='acknowledgement failed'):
        instance.start()
    assert (Path(instance.default_morph_database_config).read_bytes(), region.read_bytes()) == originals


@pytest.mark.parametrize('with_init', [False, True])
def test_custom_peer_database_is_not_silently_overwritten(peer_files, with_init):
    instance, namespace, peer, application, region, events = peer_files
    region.write_text('spring:\n  datasource:\n    url: jdbc:mysql://external-peer.example.test:3306/morph\n')
    local = Path(instance.default_morph_database_config)
    originals = local.read_bytes(), application.read_bytes(), region.read_bytes()
    with pytest.raises(RuntimeError, match='confirm-morph-db-vip'):
        instance.init() if with_init else instance.start()
    assert (local.read_bytes(), application.read_bytes(), region.read_bytes()) == originals
    peer.scp_to_peer.assert_not_called()


def test_first_initialization_accepts_missing_peer_configs_and_can_restore_absence(peer_files):
    instance, namespace, peer, application, region, events = peer_files
    application.unlink()
    region.unlink()
    instance.init()
    assert application.exists() and region.exists()
    execute = peer.execute_on_peer.side_effect
    def stop_failure(command, *args):
        if command == 'systemctl stop morph':
            raise RuntimeError('peer stop failed')
        return execute(command, *args)
    peer.execute_on_peer.side_effect = stop_failure
    with pytest.raises(RuntimeError, match='peer stop failed'):
        instance.start(do_init=True)
    assert not application.exists() and not region.exists()


@pytest.mark.parametrize('with_init', [False, True])
def test_activation_failure_keeps_shared_database_and_retains_originals(peer_files, with_init):
    instance, namespace, peer, application, region, events = peer_files
    originals = application.read_bytes(), region.read_bytes()
    if with_init:
        instance.init()
    namespace['shell_no_pipe'].side_effect = RuntimeError('local activation failed')
    with pytest.raises(RuntimeError, match='local activation failed'):
        instance.start(do_init=with_init)
    for path in (Path(instance.default_morph_database_config), region):
        assert yaml.safe_load(path.read_text())['spring']['datasource']['url'] == 'jdbc:mariadb://172.24.228.228:3306/morph'
    backups = list(region.parent.glob('.morph-ha-before-*'))
    assert len(backups) == 1
    assert ((backups[0] / application.name).read_bytes(), (backups[0] / region.name).read_bytes()) == originals
    assert events[-1] == 'systemctl start morph'
    assert any('migrations may already have run' in call.args[0] for call in namespace['warn'].call_args_list)


def test_vip_unreachable_is_rejected_before_configuration_or_service_changes(service, config_module):
    instance, namespace, peer = service
    namespace['configure_ha_database'].side_effect = config_module.configure_ha_database
    namespace['socket'].create_connection.side_effect = OSError('unreachable')
    path = Path(instance.default_morph_database_config)
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match='Cannot verify TCP connectivity'):
        instance.start()
    assert path.read_bytes() == original
    namespace['shell_no_pipe'].assert_not_called()
    peer.scp_to_peer.assert_not_called()
    assert not list(path.parent.glob('.morph-ha-before-*'))


def test_endpoint_check_uses_bounded_connections_on_both_nodes(service):
    instance, namespace, peer = service
    instance._check_ha_database_endpoint('2001:db8::10', 13306)
    namespace['socket'].create_connection.assert_called_once_with(('2001:db8::10', 13306), timeout=5)
    command, sudo = peer.execute_on_peer.call_args.args
    assert 'socket.create_connection' in command and '13306' in command and 'timeout=5' in command
    assert sudo is True


def test_init_prepares_both_nodes_without_starting_before_configuration(service):
    instance, namespace, peer = service
    instance.init()
    namespace['configure_ha_database'].assert_called_once()
    commands = [call.args[0] for call in namespace['shell_no_pipe'].call_args_list + peer.execute_on_peer.call_args_list]
    assert not any('systemctl start morph' in command or 'systemctl restart morph' in command for command in commands)
    assert yaml.safe_load(Path(instance.default_morph_database_config).read_text())['extension']['morphAddress'] == peer.config['dbvip']
    assert peer.scp_to_peer.call_args.args == (instance.default_morph_database_config, instance.default_morph_database_config)


def test_init_configuration_failure_does_not_start_either_node(service):
    instance, namespace, peer = service
    namespace['configure_ha_database'].side_effect = ValueError('invalid endpoint')
    with pytest.raises(RuntimeError, match='invalid endpoint'):
        instance.init()
    namespace['shell_no_pipe'].assert_not_called()
    peer.execute_on_peer.assert_not_called()


def test_start_waits_for_each_physical_morph_node(service):
    instance, namespace, peer = service
    instance.start()
    assert instance._wait_for_morph.call_args_list[0].args[0] == 'http://172.24.250.94:4747/actuator/health'
    assert instance._wait_for_morph.call_args_list[1].args[0] == 'http://172.24.251.5:4747/actuator/health'


def test_reinitialization_restarts_running_services_to_apply_database_override(service):
    instance, namespace, peer = service
    instance.start(do_init=True)
    assert namespace['shell_no_pipe'].call_args_list[-1].args[0] == 'systemctl restart morph'
    assert any(call.args[0] == 'systemctl restart morph' for call in peer.execute_on_peer.call_args_list)


def test_single_node_keeps_local_database_configuration(service):
    instance, namespace, peer = service
    instance.zsha2_utils = None
    instance.init()
    instance.start()
    namespace['configure_ha_database'].assert_not_called()
    peer.execute_on_peer.assert_not_called()


def test_reconfigured_local_node_restarts_peer_with_already_matching_file(service):
    instance, namespace, peer = service
    namespace['configure_ha_database'].return_value = True
    instance.start()
    commands = [call.args[0] for call in peer.execute_on_peer.call_args_list]
    assert 'systemctl stop morph' in commands
    assert 'systemctl restart morph' in commands
    assert namespace['shell_no_pipe'].call_args.args[0] == 'systemctl restart morph'


@pytest.mark.parametrize('failure', ['read-config', 'parse-config', 'write-config', 'write-unit'])
def test_local_init_failure_restores_original_configuration(service, config_module, failure):
    instance, namespace, peer = service
    namespace['configure_ha_database'].side_effect = config_module.configure_ha_database
    instance._check_ha_database_endpoint = Mock()
    path = Path(instance.default_morph_database_config)
    original = path.read_bytes()
    def failed_open(filename, mode='r', *args, **kwargs):
        if filename == instance.default_morph_database_config:
            if ((mode == 'r' and failure == 'read-config')
                    or (mode == 'w' and failure == 'write-config')):
                raise OSError('injected configuration I/O failure')
            if mode == 'r' and failure == 'parse-config':
                return io.StringIO('extension: [invalid yaml')
        if filename == instance.default_morph_service_path and failure == 'write-unit':
            raise OSError('injected unit I/O failure')
        return open(filename, mode, *args, **kwargs)
    namespace['open'] = failed_open
    with pytest.raises(RuntimeError):
        instance.init()
    assert path.read_bytes() == original
    assert not hasattr(instance, '_ha_region_snapshot')
    namespace['shell_no_pipe'].assert_not_called()
    peer.scp_to_peer.assert_not_called()


def test_local_health_failure_recovers_stopped_peer_and_reports_failure(service):
    instance, namespace, peer = service
    instance._wait_for_morph.side_effect = RuntimeError('local health failed')
    with pytest.raises(RuntimeError, match='local .* failed'):
        instance.start(do_init=True)
    commands = [call.args[0] for call in peer.execute_on_peer.call_args_list]
    assert commands[-2:] == ['systemctl stop morph', 'systemctl start morph']


def test_peer_restore_failure_does_not_hide_original_local_error(service):
    instance, namespace, peer = service
    namespace['shell_no_pipe'].side_effect = RuntimeError('local start failed')
    digest = hashlib.sha256(Path(instance.default_morph_database_config).read_bytes()).hexdigest()
    peer.execute_on_peer.side_effect = [digest, '', RuntimeError('peer start failed')]
    with pytest.raises(RuntimeError, match='local start failed'):
        instance.start(do_init=True)
    assert 'peer start failed' in namespace['warn'].call_args.args[0]


@pytest.mark.parametrize('response', ['503', RuntimeError('request timed out')])
def test_health_polling_failure_times_out_and_reports_an_exception(service, response):
    instance, namespace, peer = service
    del instance._wait_for_morph
    namespace['time'] = SimpleNamespace(time=Mock(side_effect=[0, 0, 2]), sleep=Mock())
    namespace['shell'] = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
    with pytest.raises(RuntimeError, match='did not become ready'):
        instance._wait_for_morph('http://172.24.250.94:4747/actuator/health', timeout=1)
    namespace['shell'].assert_called_once_with("curl --connect-timeout 5 --max-time 10 -s -o /dev/null -w '%{http_code}' http://172.24.250.94:4747/actuator/health")
    namespace['time'].sleep.assert_called_once_with(5)


def test_health_success_returns_without_sleeping(service):
    instance, namespace, peer = service
    del instance._wait_for_morph
    namespace['time'] = SimpleNamespace(time=Mock(side_effect=[0, 0]), sleep=Mock())
    namespace['shell'] = Mock(return_value='200')
    assert instance._wait_for_morph('http://172.24.250.94:4747/actuator/health', timeout=1)
    namespace['shell'].assert_called_once()
    namespace['time'].sleep.assert_not_called()


@pytest.mark.parametrize('failed_file', ['config', 'jar', 'service_path', 'database_config'])
def test_failed_init_sync_restores_both_configurations(peer_files, failed_file):
    instance, namespace, peer, application, region, events = peer_files
    path = Path(instance.default_morph_database_config)
    originals = path.read_bytes(), application.read_bytes(), region.read_bytes()
    copy = peer.scp_to_peer.side_effect
    def failed_copy(source, destination):
        copy(source, destination)
        if source == getattr(instance, 'default_morph_' + failed_file):
            raise RuntimeError('injected copy failure')
    peer.scp_to_peer.side_effect = failed_copy
    with pytest.raises(RuntimeError, match='injected copy failure'):
        instance.init()
    assert (path.read_bytes(), application.read_bytes(), region.read_bytes()) == originals
    assert not hasattr(instance, '_ha_region_snapshot')
    assert not hasattr(instance, '_ha_peer_backup_directory')
    commands = [call.args[0] for call in namespace['shell_no_pipe'].call_args_list] + events
    assert not any('systemctl start morph' in command or 'systemctl restart morph' in command for command in commands)


@pytest.mark.parametrize('failure', ['start', 'health'])
def test_peer_activation_failure_attempts_recovery_without_stopping_local(service, failure):
    instance, namespace, peer = service
    execute = peer.execute_on_peer.side_effect
    def command(cmd, *args):
        if cmd == 'systemctl restart morph' and failure == 'start':
            raise RuntimeError('peer start failed')
        return execute(cmd, *args)
    peer.execute_on_peer.side_effect = command
    if failure == 'health':
        instance._wait_for_morph.side_effect = [True, RuntimeError('peer health failed')]
    with pytest.raises(RuntimeError, match='peer .* failed'):
        instance.start(do_init=True)
    assert peer.execute_on_peer.call_args.args[0] == 'systemctl start morph'
    assert namespace['shell_no_pipe'].call_args_list[-1].args[0] == 'systemctl restart morph'

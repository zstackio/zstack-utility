import ast
import hashlib
import importlib.util
import os
import time
import warnings
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

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


@pytest.fixture
def service(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        tree = ast.parse(CTL.read_text())
    morph = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'MorphService')
    namespace = dict(os=os, time=time, hashlib=hashlib, yaml=yaml, OrderedDict=OrderedDict, ExtraService=object,
                     get_default_ip=lambda: '172.24.250.94',
                     format_url_host=lambda host: '[%s]' % host if ':' in host else host,
                     shell_quote=lambda value: "'%s'" % value,
                     configure_ha_database=Mock(return_value=False),
                     snapshot_file=lambda path: Path(path).read_bytes(),
                     restore_file=lambda path, data: Path(path).write_bytes(data),
                     shell_no_pipe=Mock(), info=Mock(), info_and_debug=Mock(), warn=Mock(),
                     CtlError=RuntimeError)
    def fail(message):
        raise RuntimeError(message)
    namespace['error'] = fail
    exec(compile(ast.Module(body=[morph], type_ignores=[]), str(CTL), 'exec'), namespace)
    instance = namespace['MorphService']()
    instance.default_morph_config = str(tmp_path / 'application.yml')
    instance.default_morph_database_config = str(tmp_path / 'region_config.yml')
    instance.default_morph_service_path = str(tmp_path / 'morph.service')
    Path(instance.default_morph_database_config).write_text('extension:\n  morphAddress: old-vip\n')
    instance._wait_for_morph = Mock(return_value=True)
    peer = Mock()
    peer.config = {'dbvip': '172.24.228.228', 'nodeip': '172.24.250.94', 'peerip': '172.24.251.5'}
    peer.execute_on_peer.side_effect = lambda command, *args: (
        hashlib.sha256(Path(instance.default_morph_database_config).read_bytes()).hexdigest()
        if command.startswith('sha256sum') else '')
    instance.zsha2_utils = peer
    return instance, namespace, peer


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


def test_peer_preparation_failure_restores_local_config_for_retry(service):
    instance, namespace, peer = service
    path = Path(instance.default_morph_database_config)
    original = path.read_bytes()
    def reconfigure(*args):
        path.write_text('spring:\n  datasource:\n    url: jdbc:mariadb://172.24.228.228/morph\n')
        return True
    namespace['configure_ha_database'].side_effect = reconfigure
    peer.execute_on_peer.side_effect = RuntimeError('peer unavailable')
    with pytest.raises(RuntimeError, match='peer unavailable'):
        instance.start()
    assert path.read_bytes() == original
    namespace['shell_no_pipe'].assert_not_called()


def test_reconfigured_local_node_restarts_peer_with_already_matching_file(service):
    instance, namespace, peer = service
    namespace['configure_ha_database'].return_value = True
    instance.start()
    commands = [call.args[0] for call in peer.execute_on_peer.call_args_list]
    assert 'systemctl stop morph' in commands
    assert 'systemctl restart morph' in commands
    assert namespace['shell_no_pipe'].call_args.args[0] == 'systemctl restart morph'


def test_peer_init_sync_failure_rolls_back_configuration_and_starts_nothing(service):
    instance, namespace, peer = service
    path = Path(instance.default_morph_database_config)
    original = path.read_bytes()
    peer.scp_to_peer.side_effect = RuntimeError('peer copy failed')
    with pytest.raises(RuntimeError, match='peer copy failed'):
        instance.init()
    assert path.read_bytes() == original
    commands = [call.args[0] for call in namespace['shell_no_pipe'].call_args_list]
    assert all('start morph' not in command for command in commands)


@pytest.mark.parametrize('failure', ['start', 'health'])
def test_local_activation_failure_restores_stopped_peer_and_reports_failure(service, failure):
    instance, namespace, peer = service
    if failure == 'start':
        namespace['shell_no_pipe'].side_effect = RuntimeError('local start failed')
    else:
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


def test_failed_jar_sync_does_not_commit_peer_database_configuration(service):
    instance, namespace, peer = service
    path = Path(instance.default_morph_database_config)
    original = path.read_bytes()
    def copy(src, dst):
        if src == instance.default_morph_jar:
            raise RuntimeError('jar copy failed')
    peer.scp_to_peer.side_effect = copy
    with pytest.raises(RuntimeError, match='jar copy failed'):
        instance.init()
    assert path.read_bytes() == original
    assert not any(call.args[0] == instance.default_morph_database_config for call in peer.scp_to_peer.call_args_list)


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

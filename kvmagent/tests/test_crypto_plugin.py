import importlib
import json
import logging
import subprocess
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest


@pytest.fixture
def plugin(monkeypatch):
    for name, attrs in {
        'plugin': {'Plugin': object},
        'daemon': {'Daemon': object},
        'linux': {'HOST_ARCH': 'x86_64', 'recover_fake_dead': lambda _: None},
        'qemu': {},
        'http': {'REQUEST_BODY': 'body', 'HttpServer': Mock},
        'log': {'get_logger': logging.getLogger, 'get_logfile_path': lambda: '/tmp/crypto-test.log'},
    }.items():
        module = types.ModuleType('zstacklib.utils.' + name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, module.__name__, module)
        import zstacklib.utils
        monkeypatch.setattr(zstacklib.utils, name, module, raising=False)
    monkeypatch.setitem(sys.modules, 'simplejson', json)
    for name in ('zstacklib.utils.jsonobject', 'zstacklib.utils.lock', 'kvmagent.kvmagent',
                 'kvmagent.plugins.crypto_plugin'):
        monkeypatch.delitem(sys.modules, name, raising=False)
    module = importlib.import_module('kvmagent.plugins.crypto_plugin')
    return module.CryptoPlugin()


def invoke(handler, **command):
    return json.loads(handler({'body': json.dumps(command)}))


def command(operation='Split'):
    return dict(operation=operation, pciDeviceAddress='0000:b3:00.0',
                pciDeviceAddresses=['0000:b3:00.0'], vfCount=2)


def test_missing_vendor_profile_fails_operations_without_reporting_hardware_success(plugin, monkeypatch, tmp_path):
    health = importlib.import_module('kvmagent.crypto.sansec_health')
    operations = importlib.import_module('kvmagent.crypto.sansec_operations')
    (tmp_path / 'pci').mkdir()
    monkeypatch.setattr(health, 'SYSFS_DEVICES', str(tmp_path / 'pci'))
    monkeypatch.setattr(health, 'CONFIG_PATH', str(tmp_path / 'missing-config'))
    for operation in ('Split', 'Unsplit'):
        result = invoke(plugin.operation, **command(operation))
        assert result['success'] and result['status'] == 'Failed'
        assert result['reason']
    report = invoke(plugin.health, pciDeviceAddresses=['0000:b3:00.0'])
    assert report['success'] and report['devices'][0]['healthStatus'] == 'Unknown'


@pytest.mark.parametrize('operation', ['Split', 'Unsplit'])
def test_dispatch_preserves_outcome(plugin, operation):
    plugin.driver = Mock()
    plugin.driver.submit.return_value = {'status': 'Succeeded', 'vfCounts': {'0000:b3:00.0': 2}}
    result = invoke(plugin.operation, **command(operation))
    assert result['success'] and result['status'] == 'Succeeded' and result['vfCounts'] == {'0000:b3:00.0': 2}
    received = plugin.driver.submit.call_args[0][0]
    assert received.operation == operation and received.pciDeviceAddresses == ['0000:b3:00.0']


@pytest.mark.parametrize('patch', [dict(operation='Reclaim'), dict(vfCount=0), dict(vfCount=True),
                                  dict(pciDeviceAddress='0000:b4:00.0'),
                                  dict(pciDeviceAddresses=['0000:b3:00.0\n']),
                                  dict(pciDeviceAddresses=['0000:b3:00.0; touch /tmp/invalid'])])
def test_invalid_commands_never_reach_vendor(plugin, patch):
    plugin.driver = Mock()
    cmd = command('Split')
    cmd.update(patch)
    assert not invoke(plugin.operation, **cmd)['success']
    plugin.driver.submit.assert_not_called()


def test_newline_in_health_request_never_reaches_vendor(plugin):
    plugin.driver = Mock()
    assert not invoke(plugin.health, pciDeviceAddresses=['0000:b3:00.0\n'])['success']
    plugin.driver.health.assert_not_called()


def test_health_converges_driver_before_collecting(plugin):
    plugin.driver.operations = Mock(is_busy=Mock(return_value=False))
    plugin.driver.detector = Mock(health=Mock(return_value=[dict(pciDeviceAddress='0000:b3:00.0')]))
    assert invoke(plugin.health, pciDeviceAddresses=['0000:b3:00.0'])['success']
    plugin.driver.operations.converge.assert_called_once_with()


def test_health_requires_full_coverage(plugin):
    plugin.driver = Mock()
    report = dict(pciDeviceAddress='0000:b3:00.0', healthStatus='Normal', qualification='Qualified',
                  supportedVfCounts=[2, 4], pollInterval=10, validityPeriod=30, recoveryInterval=20)
    plugin.driver.health.return_value = [report]
    assert invoke(plugin.health, pciDeviceAddresses=['0000:b3:00.0'])['devices'] == [report]
    plugin.driver.health.return_value = []
    assert not invoke(plugin.health, pciDeviceAddresses=['0000:b3:00.0'])['success']


def test_hardware_operations_are_serialized_across_different_pfs(plugin):
    entered, release, second = Event(), Event(), Event()
    plugin.driver = Mock()

    def change_topology(cmd):
        if cmd.pciDeviceAddress == '0000:b3:00.0':
            entered.set()
            assert release.wait(5)
        else:
            second.set()
        return {'status': 'Succeeded'}

    plugin.driver.submit.side_effect = change_topology
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(invoke, plugin.operation, **command())
        assert entered.wait(5)
        cmd = command()
        cmd.update(pciDeviceAddress='0000:b4:00.0', pciDeviceAddresses=['0000:b4:00.0'])
        other = pool.submit(invoke, plugin.operation, **cmd)
        assert not second.wait(0.1), 'The second PF must wait for the host-wide driver lock'
        release.set()
        assert first.result()['success'] and other.result()['success']


def test_confirmed_fault_does_not_require_split_capabilities(plugin):
    plugin.driver = Mock()
    report = dict(pciDeviceAddress='0000:b3:00.0', healthStatus='Fault', reason='confirmed hardware fault')
    plugin.driver.health.return_value = [report]
    assert invoke(plugin.health, pciDeviceAddresses=['0000:b3:00.0'])['devices'] == [report]


def test_unreaped_driver_command_blocks_health_and_resets_failure_samples(plugin, monkeypatch):
    operations = plugin.driver.operations
    module = importlib.import_module('kvmagent.crypto.sansec_operations')
    process = Mock()
    process.communicate.side_effect = subprocess.TimeoutExpired('modprobe', 30)
    process.poll.return_value = None
    monkeypatch.setattr(module.shell, 'get_process', Mock(return_value=process))
    with pytest.raises(RuntimeError, match='timed out'):
        operations.run(['modprobe', '-r', 'swcsm'])
    addresses = ['0000:b3:00.0', '0000:b3:00.1']
    detector = plugin.driver.detector
    detector.failures[addresses[0]] = (2, 0)
    detector.health = Mock(return_value=[dict(pciDeviceAddress=a, healthStatus='Unknown') for a in addresses])
    response = invoke(plugin.health, pciDeviceAddresses=addresses)
    assert response['success'] and len(response['devices']) == len(addresses)
    detector.health.assert_not_called()
    assert all(d['healthStatus'] == 'Unknown' and 'command' in d['reason'] for d in response['devices'])
    assert not detector.failures, 'Driver changes must break consecutive communication-failure samples'
    process.poll.return_value = 0
    assert invoke(plugin.health, pciDeviceAddresses=addresses)['success']
    detector.health.assert_called_once_with(addresses)

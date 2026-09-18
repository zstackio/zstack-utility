import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kvmagent.plugins import host_plugin
from zstacklib.utils import jsonobject


ROOT = Path(__file__).resolve().parents[3]
COLLECTORS = ('collect_ipmi_state', 'collect_equipment_state_from_ipmi', 'collect_equipment_state')


@pytest.mark.parametrize('interval', [0, 60, 255, '10'])
def test_identify_host_preserves_supported_intervals_and_timeout(monkeypatch, interval):
    command = MagicMock()
    monkeypatch.setattr(host_plugin.shell, 'ShellCmd', command)
    req = {host_plugin.http.REQUEST_BODY: json.dumps({'interval': interval})}
    result = host_plugin.HostPlugin.__new__(host_plugin.HostPlugin).identify_host(req)
    assert json.loads(result)['success'] is True
    command.assert_called_once_with('timeout -k 5s 30s ipmitool chassis identify %s' % int(interval))
    command.return_value.assert_called_once_with(True)


@pytest.mark.parametrize('interval', [-1, 256, 1.5, True, None, '10; echo injected', '10\n', 'force', '9' * 10000])
def test_identify_host_rejects_invalid_input_before_starting_command(monkeypatch, interval):
    command = MagicMock()
    monkeypatch.setattr(host_plugin.shell, 'ShellCmd', command)
    req = {host_plugin.http.REQUEST_BODY: json.dumps({'interval': interval})}
    result = host_plugin.HostPlugin.__new__(host_plugin.HostPlugin).identify_host(req)
    assert json.loads(result)['success'] is False
    assert '0 and 255' in json.loads(result)['error']
    command.assert_not_called()


class Metric:
    def __init__(self, name, *args):
        self.name = name
        self.samples = []

    def add_metric(self, labels, value):
        self.samples.append((labels, value))


@pytest.fixture
def hardware(tmp_path, monkeypatch):
    if not sys.platform.startswith('linux'):
        pytest.skip('requires GNU timeout, fork and /proc')
    real_timeout = shutil.which('timeout')
    assert real_timeout, 'GNU timeout is required by the hardware collectors'
    timeout = tmp_path / 'timeout'
    timeout.write_text('''#!/usr/bin/env python3
import os, sys
assert sys.argv[1:3] == ['-k', '5s']
duration = float(sys.argv[3].removesuffix('s'))
assert 0 < duration <= 30
os.execv(%r, ['timeout', '-k', '0.05s', str(duration / 100) + 's'] + sys.argv[4:])
''' % real_timeout)
    ipmitool = tmp_path / 'ipmitool'
    ipmitool.write_text('''#!/usr/bin/env python3
import os, signal, sys, time
with open(os.environ['IPMI_CALLS'], 'a') as stream:
    stream.write(' '.join(sys.argv[1:]) + '\\n')
if os.environ.get('IPMI_HANG') in ('all', sys.argv[1]):
    if not os.environ.get('IPMI_ACCEPT_TERM'):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.alarm(10)
    child = os.fork()
    if child == 0:
        signal.alarm(10)
    with open(os.environ['IPMI_PIDS'], 'a') as stream:
        stream.write(str(os.getpid()) + '\\n')
    print('CPU1 Status | 3Ch | ok | 3.96 | Absent', flush=True)
    while True:
        time.sleep(0.01)
elif sys.argv[1] == 'mc':
    print('Firmware Revision : 1.23')
    sys.exit(int(os.environ.get('IPMI_EXIT', '0')))
elif sys.argv[1] == 'lan':
    if sys.argv[-1] != '2':
        sys.exit(1)
    print('IP Address : 192.0.2.10')
elif sys.argv[2] == 'elist':
    print('CPU1_Temp | 39h | ok | 7.18 | 34 degrees C')
    print('CPU1 Status | 3Ch | ok | 3.96 | Presence detected')
else:
    print('PS1 Status | 3Ch | ok | 3.96 | Presence detected')
''')
    for name in ('hd_ctl', 'sensors'):
        executable = tmp_path / name
        executable.write_text('#!/bin/sh\nexit 1\n')
        executable.chmod(0o755)
    timeout.chmod(0o755)
    ipmitool.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('IPMI_CALLS', str(tmp_path / 'calls'))
    monkeypatch.setenv('IPMI_PIDS', str(tmp_path / 'pids'))
    monkeypatch.setenv('IPMI_HANG', 'all')
    spec = importlib.util.spec_from_file_location('zstacklib.utils.ipmi_test_bash', ROOT / 'zstacklib/zstacklib/utils/bash.py')
    bash = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bash)
    monkeypatch.setattr(bash.shell, 'get_process', lambda cmd, **kwargs: subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
    monkeypatch.setattr(host_plugin, 'bash_roe', bash.bash_roe)
    monkeypatch.setattr(host_plugin.linux, 'monotime', lambda: time.monotonic() * 100)
    return SimpleNamespace(path=tmp_path, bash=bash)


def load_collectors(bash):
    path = ROOT / 'kvmagent/kvmagent/plugins/prometheus.py'
    tree = ast.parse(path.read_text())
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name in COLLECTORS + ('_collect_hardware_command',)]
    clock = SimpleNamespace(time=time.time, monotonic=lambda: time.monotonic() * 100)
    namespace = dict(GaugeMetricFamily=Metric, time=clock, re=re, jsonobject=jsonobject,
                     HARDWARE_COLLECTION_TIMEOUT=30,
                     bash_r=bash.bash_r, bash_ro=bash.bash_ro, get_is_hygon=lambda: False,
                     collect_equipment_state_last_time=None, collect_equipment_state_last_result=None,
                     cpu_status_consecutive_abnormal_count={}, CPU_STATUS_ABNORMAL_ALARM_THRESHOLD=1,
                     send_cpu_status_alarm_to_mn=MagicMock(), remove_cpu_status_abnormal=MagicMock())
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('collector', COLLECTORS)
def test_hung_ipmi_is_bounded_and_partial_output_is_not_a_hardware_alarm(hardware, collector):
    namespace = load_collectors(hardware.bash)
    started = time.monotonic()
    metrics = {metric.name: metric for metric in namespace[collector]()}
    assert time.monotonic() - started < 5
    assert metrics['ipmi_status'].samples[0][1] in (124, 137)
    assert all(not metric.samples for name, metric in metrics.items() if name != 'ipmi_status')
    namespace['send_cpu_status_alarm_to_mn'].assert_not_called()
    assert len((hardware.path / 'calls').read_text().splitlines()) == 1
    assert_probe_processes_stopped(hardware.path)


def assert_probe_processes_stopped(path):
    pids = (path / 'pids').read_text().splitlines()
    assert len(pids) == 2, 'both the hung command and its child must have started'
    for pid in pids:
        stat = Path('/proc') / pid / 'stat'
        deadline = time.monotonic() + 3
        while True:
            try:
                state = stat.read_text().split(') ')[1]
            except (FileNotFoundError, ProcessLookupError):
                break
            if state.startswith('Z '):
                break
            assert time.monotonic() < deadline, 'timed-out child %s is still running' % pid
            time.sleep(0.01)


def test_normal_ipmi_output_preserves_metrics(hardware, monkeypatch):
    monkeypatch.setenv('IPMI_HANG', '')
    namespace = load_collectors(hardware.bash)
    metrics = {metric.name: metric for metric in namespace['collect_equipment_state_from_ipmi']()}
    assert metrics['ipmi_status'].samples == [([], 0)]
    assert metrics['cpu_temperature'].samples == [(['CPU1'], 34.0)]
    assert metrics['cpu_status'].samples == [(['CPU1'], 0)]


def test_exhausted_collection_budget_does_not_start_another_command(hardware):
    namespace = load_collectors(hardware.bash)
    assert namespace['_collect_hardware_command']('ipmitool mc info', 0) == (124, '')
    assert not (hardware.path / 'calls').exists()


@pytest.mark.parametrize('hang, expected_calls, version, address', [
    ('all', ['mc info'], 'unknown', 'None'),
    ('lan', ['mc info', 'lan print 1'], '1.23', 'None'),
    ('', ['mc info', 'lan print 1', 'lan print 2'], '1.23', '192.0.2.10'),
])
def test_host_ipmi_discovery_stops_retrying_on_timeout(hardware, monkeypatch, hang, expected_calls, version, address):
    monkeypatch.setenv('IPMI_HANG', hang)
    rsp = SimpleNamespace()
    started = time.monotonic()
    host_plugin.HostPlugin.__new__(host_plugin.HostPlugin)._collect_ipmi_info(rsp)
    assert time.monotonic() - started < 5
    assert (rsp.bmcVersion, rsp.ipmiAddress) == (version, address)
    assert (hardware.path / 'calls').read_text().splitlines() == expected_calls


def test_slow_ipmi_failures_share_the_discovery_budget(monkeypatch):
    monkeypatch.setattr(host_plugin.linux, 'monotime', MagicMock(side_effect=[100, 100, 125, 130]))
    command = MagicMock(return_value=(1, '', 'BMC failure'))
    monkeypatch.setattr(host_plugin, 'bash_roe', command)
    rsp = SimpleNamespace()
    host_plugin.HostPlugin.__new__(host_plugin.HostPlugin)._collect_ipmi_info(rsp)
    assert [call.args[0] for call in command.call_args_list] == [
        'timeout -k 5s 30.000s ipmitool mc info',
        'timeout -k 5s 5.000s ipmitool lan print 1',
    ]
    assert (rsp.bmcVersion, rsp.ipmiAddress) == ('unknown', 'None')


def test_submillisecond_ipmi_budget_never_disables_timeout(monkeypatch):
    monkeypatch.setattr(host_plugin.linux, 'monotime', MagicMock(side_effect=[100, 129.9999, 130]))
    command = MagicMock(return_value=(1, '', 'BMC failure'))
    monkeypatch.setattr(host_plugin, 'bash_roe', command)
    host_plugin.HostPlugin.__new__(host_plugin.HostPlugin)._collect_ipmi_info(SimpleNamespace())
    command.assert_called_once_with('timeout -k 5s 0.001s ipmitool mc info')


def load_definitions(path, names, namespace):
    # The suite mocks linux/shell globally. Execute the production definitions
    # with real subprocesses, without importing unrelated host initialization.
    tree = ast.parse(path.read_text())
    body = [node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    assert len(body) == len(names)
    for node in body:
        node.decorator_list = []
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), namespace)
    return SimpleNamespace(**namespace)


@pytest.fixture
def bmc_probe():
    logger = MagicMock()
    shell = load_definitions(ROOT / 'zstacklib/zstacklib/utils/shell.py',
                             ('get_process', 'ShellError', 'ShellCmd'),
                             dict(subprocess=subprocess, log=SimpleNamespace(get_logger=lambda _: logger)))
    return load_definitions(ROOT / 'zstacklib/zstacklib/utils/linux.py',
                            ('is_support_bmc',), dict(shell=shell, logger=logger))


@pytest.mark.parametrize('accept_term, return_codes', [('1', (124,)), ('', (137, -9))])
def test_bmc_probe_timeout_reaps_process_group(hardware, bmc_probe, monkeypatch, accept_term, return_codes):
    monkeypatch.setenv('IPMI_ACCEPT_TERM', accept_term)
    commands = []
    shell_cmd = bmc_probe.shell.ShellCmd

    def record_command(command):
        cmd = shell_cmd(command)
        commands.append(cmd)
        return cmd

    monkeypatch.setattr(bmc_probe.shell, 'ShellCmd', record_command)
    started = time.monotonic()
    assert bmc_probe.is_support_bmc() is False
    assert time.monotonic() - started < 5
    assert (hardware.path / 'calls').read_text().splitlines() == ['mc info']
    assert commands[0].return_code in return_codes
    bmc_probe.logger.warn.assert_called_once()
    assert_probe_processes_stopped(hardware.path)


@pytest.mark.parametrize('exit_code, supported', [('0', True), ('1', False)])
def test_bmc_probe_uses_exit_status_even_with_valid_output(hardware, bmc_probe, monkeypatch, exit_code, supported):
    monkeypatch.setenv('IPMI_HANG', '')
    monkeypatch.setenv('IPMI_EXIT', exit_code)
    assert bmc_probe.is_support_bmc() is supported
    bmc_probe.logger.warn.assert_not_called()


def test_bmc_probe_retries_after_timeout(hardware, bmc_probe, monkeypatch):
    assert bmc_probe.is_support_bmc() is False
    assert_probe_processes_stopped(hardware.path)
    monkeypatch.setenv('IPMI_HANG', '')
    assert bmc_probe.is_support_bmc() is True
    assert (hardware.path / 'calls').read_text().splitlines() == ['mc info', 'mc info']


@pytest.mark.parametrize('hang', ['all', ''])
def test_prometheus_module_registration_survives_bmc_probe(hardware, bmc_probe, monkeypatch, hang):
    from kvmagent import kvmagent
    from zstacklib.utils import misc

    monkeypatch.setenv('IPMI_HANG', hang)
    monkeypatch.setattr(host_plugin.linux, 'is_support_bmc', bmc_probe.is_support_bmc)
    monkeypatch.setattr(misc, 'isHyperConvergedHost', lambda: False)
    register = MagicMock()
    monkeypatch.setattr(kvmagent, 'register_prometheus_collector', register)
    spec = importlib.util.spec_from_file_location('ipmi_test_prometheus',
                                                ROOT / 'kvmagent/kvmagent/plugins/prometheus.py')
    module = importlib.util.module_from_spec(spec)
    started = time.monotonic()
    spec.loader.exec_module(module)
    assert time.monotonic() - started < 5
    assert module.is_support_bmc is bmc_probe.is_support_bmc
    registered = [call.args[0].__name__ for call in register.call_args_list]
    assert ('collect_equipment_state_from_ipmi' in registered) is (not hang)
    assert 'collect_raid_state' in registered
    assert (hardware.path / 'calls').read_text().splitlines() == ['mc info']
    if hang:
        assert_probe_processes_stopped(hardware.path)


@pytest.mark.parametrize('hang', ['all', ''])
def test_exporter_start_continues_after_bmc_probe(hardware, bmc_probe, monkeypatch, hang):
    from kvmagent.plugins import prometheus

    monkeypatch.setenv('IPMI_HANG', hang)
    monkeypatch.setattr(prometheus, 'is_support_bmc', bmc_probe.is_support_bmc)
    monkeypatch.setattr(prometheus, 'is_virtual_machine', lambda: False)
    monkeypatch.setattr(prometheus.lock, 'file_lock', lambda *a, **kw: lambda f: f)
    monkeypatch.setattr(prometheus, 'os', SimpleNamespace(
        path=SimpleNamespace(dirname=os.path.dirname, join=os.path.join, exists=lambda _: False),
        listdir=lambda _: [], chmod=MagicMock()))
    monkeypatch.setattr(prometheus.linux, 'write_file', MagicMock())
    monkeypatch.setattr(prometheus.shell, 'run', lambda _: 1)
    start = MagicMock()
    monkeypatch.setattr(prometheus, 'bash_errorout', start)
    req = {prometheus.http.REQUEST_BODY: json.dumps({'cmds': [
        {'binaryPath': str(hardware.path / name), 'startupArguments': ''}
        for name in ('ipmi_exporter', 'node_exporter')
    ]})}
    started = time.monotonic()
    response = prometheus.PrometheusPlugin.__new__(prometheus.PrometheusPlugin).start_prometheus_exporter(req)
    assert time.monotonic() - started < 5
    assert json.loads(response)['success'] is True
    commands = [call.args[0] for call in start.call_args_list]
    assert 'systemctl daemon-reload && systemctl restart node_exporter.service' in commands
    assert ('systemctl daemon-reload && systemctl restart ipmi_exporter.service' in commands) is (not hang)
    if hang:
        assert_probe_processes_stopped(hardware.path)

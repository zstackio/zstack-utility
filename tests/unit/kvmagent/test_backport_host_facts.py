import importlib.util
import json
import re
import shlex
import subprocess
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[3]
HOST = ROOT / 'kvmagent/kvmagent/plugins/host_plugin.py'
PROMETHEUS = ROOT / 'kvmagent/kvmagent/plugins/prometheus.py'


def load_definition(path, name, namespace, indent=''):
    source = path.read_text()
    pattern = r'^%sdef %s\(.*?(?=^%s(?:def |@)|^class |\Z)' % (indent, name, indent)
    match = re.search(pattern, source, re.M | re.S)
    assert match, 'missing production definition: ' + name
    exec(compile(textwrap.dedent(match.group(0)), str(path), 'exec'), namespace)
    return namespace[name]


def run_bash(command, **kwargs):
    result = subprocess.run(command, shell=True, executable='/bin/bash', text=True,
                            capture_output=True, timeout=3)
    return result.returncode, result.stdout, result.stderr


def host_namespace():
    return dict(
        jsonobject=SimpleNamespace(loads=lambda s: SimpleNamespace(**json.loads(s)),
                                   dumps=lambda obj: json.dumps(vars(obj))),
        http=SimpleNamespace(REQUEST_BODY='body'),
        kvmagent=SimpleNamespace(AgentResponse=lambda: SimpleNamespace(success=True)),
        re=re, shell=SimpleNamespace(ShellCmd=MagicMock()), shell_quote=shlex.quote,
        logger=MagicMock(), linux=SimpleNamespace(monotime=time.monotonic),
        IPMI_COMMAND='timeout -k 5s 30s ipmitool', bash_roe=run_bash)


@pytest.mark.parametrize('interval', [0, 60, 255, '10'])
def test_identify_host_uses_a_bounded_command(interval):
    namespace = host_namespace()
    identify = load_definition(HOST, 'identify_host', namespace, '    ')
    response = json.loads(identify(object(), {'body': json.dumps({'interval': interval})}))
    assert response['success'] is True
    namespace['shell'].ShellCmd.assert_called_once_with(
        'timeout -k 5s 30s ipmitool chassis identify %s' % int(interval))


@pytest.mark.parametrize('interval', [-1, 256, 1.5, True, None, '10; echo injected', '10\n', 'force'])
def test_identify_host_rejects_invalid_intervals(interval):
    namespace = host_namespace()
    identify = load_definition(HOST, 'identify_host', namespace, '    ')
    response = json.loads(identify(object(), {'body': json.dumps({'interval': interval})}))
    assert response['success'] is False
    namespace['shell'].ShellCmd.assert_not_called()


@pytest.mark.parametrize('outputs,expected', [
    ([(0, 'Firmware Revision : 1.23', ''), (1, '', 'missing'),
      (0, 'IP Address : 192.0.2.10', '')], ('1.23', '192.0.2.10', 3)),
    ([(124, 'Firmware Revision : partial', '')], ('unknown', 'None', 1)),
    ([(0, 'Firmware Revision : 1.23', ''), (137, 'IP Address : partial', '')], ('1.23', 'None', 2)),
])
def test_ipmi_discovery_discards_partial_output_and_stops_after_timeout(outputs, expected):
    namespace = host_namespace()
    namespace['bash_roe'] = MagicMock(side_effect=outputs)
    collect = load_definition(HOST, '_collect_ipmi_info', namespace, '    ')
    response = SimpleNamespace()
    collect(object(), response)
    assert (response.bmcVersion, response.ipmiAddress, namespace['bash_roe'].call_count) == expected
    assert all(call.args[0].startswith('timeout -k 5s ') for call in namespace['bash_roe'].call_args_list)


def test_ipmi_discovery_shares_one_monotonic_budget():
    namespace = host_namespace()
    namespace['linux'].monotime = MagicMock(side_effect=[100, 100, 125, 130])
    namespace['bash_roe'] = MagicMock(return_value=(1, '', 'failure'))
    collect = load_definition(HOST, '_collect_ipmi_info', namespace, '    ')
    collect(object(), SimpleNamespace())
    assert [call.args[0] for call in namespace['bash_roe'].call_args_list] == [
        'timeout -k 5s 30.000s ipmitool mc info', 'timeout -k 5s 5.000s ipmitool lan print 1']


def test_submillisecond_ipmi_budget_never_disables_timeout():
    namespace = host_namespace()
    namespace['linux'].monotime = MagicMock(side_effect=[100, 129.9999, 130])
    namespace['bash_roe'] = MagicMock(return_value=(1, '', 'failure'))
    collect = load_definition(HOST, '_collect_ipmi_info', namespace, '    ')
    collect(object(), SimpleNamespace())
    namespace['bash_roe'].assert_called_once_with('timeout -k 5s 0.001s ipmitool mc info')


class Metric:
    def __init__(self, name, *args):
        self.name, self.samples = name, []

    def add_metric(self, labels, value):
        self.samples.append((labels, value))


def collector_namespace(command):
    namespace = dict(
        GaugeMetricFamily=Metric, re=re, time=time,
        linux=SimpleNamespace(monotime=time.monotonic),
        HARDWARE_COLLECTION_TIMEOUT=30, bash_ro=command,
        bash_r=lambda cmd: command(cmd)[0],
        collect_equipment_state_last_time=None, collect_equipment_state_last_result=None,
        cpu_status_abnormal_list_record=set(), memory_status_abnormal_list_record=set(),
        fan_status_abnormal_list_record=set(), cpu_status_consecutive_abnormal_count={},
        CPU_STATUS_ABNORMAL_ALARM_THRESHOLD=1, send_cpu_status_alarm_to_mn=MagicMock())
    if 'def _collect_hardware_command(' in PROMETHEUS.read_text():
        load_definition(PROMETHEUS, '_collect_hardware_command', namespace)
    return namespace


@pytest.mark.parametrize('collector', ['collect_ipmi_state', 'collect_physical_cpu_state', 'collect_equipment_state'])
def test_hardware_collectors_bound_every_command_and_drop_partial_results(collector):
    command = MagicMock(return_value=(137, 'partial output'))
    namespace = collector_namespace(command)
    collect = load_definition(PROMETHEUS, collector, namespace)
    metrics = list(collect())
    assert all(call.args[0].startswith('timeout -k 5s ') for call in command.call_args_list)
    assert all(not metric.samples for metric in metrics if metric.name != 'ipmi_status')
    namespace['send_cpu_status_alarm_to_mn'].assert_not_called()


def test_expired_hardware_budget_does_not_launch_a_command():
    command = MagicMock()
    namespace = collector_namespace(command)
    collect = load_definition(PROMETHEUS, '_collect_hardware_command', namespace)
    assert collect('ipmitool mc info', 0) == (124, '')
    command.assert_not_called()


def test_normal_cpu_metrics_keep_temperature_and_health_values():
    command = MagicMock(return_value=(0,
        'CPU1_Temp | 39h | ok | 7.18 | 34 degrees C\n'
        'CPU1 Status | 3Ch | ok | 3.96 | Presence detected'))
    namespace = collector_namespace(command)
    namespace['filter'] = lambda function, values: ''.join(filter(function, values))
    collect = load_definition(PROMETHEUS, 'collect_physical_cpu_state', namespace)
    metrics = {metric.name: metric for metric in collect()}
    assert metrics['cpu_temperature'].samples == [(['CPU1'], 34.0)]
    assert metrics['cpu_status'].samples == [(['CPU1'], 0)]


def test_hardware_timeout_terminates_a_process_that_ignores_term():
    namespace = collector_namespace(lambda cmd, **kwargs: run_bash(cmd)[:2])
    collect = load_definition(PROMETHEUS, '_collect_hardware_command', namespace)
    # Keep the production timeout command; shorten only its kill grace for this test.
    def execute(command, **kwargs):
        return run_bash(command.replace('timeout -k 5s ', 'timeout -k 0.05s '))[:2]
    namespace['bash_ro'] = execute
    started = time.monotonic()
    result, output = collect("bash -c 'trap \"\" TERM; echo partial; while :; do sleep 0.01; done'",
                             time.monotonic() + 0.05)
    assert result in (137, -9)
    assert output.strip() == 'partial'
    assert time.monotonic() - started < 2


@pytest.mark.parametrize('model,frequencies,expected', [
    ('Intel CPU @ 2.10GHz', '3100 MHz\n3100 MHz', '2.10'),
    ('Hygon C86-4G', '2700 MHz\n2700 MHz', '2.70'),
    ('CPU @ 0GHz', '2700 MHz\n2700 MHz', '2.70'),
    ('Hygon', 'Unknown', None), ('Hygon', '2700 MHz\nUnknown', None),
    ('Hygon', '2700 MHz\n3100 MHz', None), ('Hygon', '0 MHz', None),
])
def test_production_x86_fact_uses_static_frequency(model, frequencies, expected):
    source = HOST.read_text()
    fact = re.search(r'^    def fact\(.*?(?=^    (?:def |@)|\Z)', source, re.M | re.S).group(0)
    start = fact.rindex('            host_cpu_info = ')
    end = fact.index('            cpu_cores_per_socket = ', start)
    block = textwrap.dedent(fact[start:end])
    helper = ROOT / 'zstacklib/zstacklib/utils/cpu_frequency.py'
    module = SimpleNamespace()
    if helper.exists():
        spec = importlib.util.spec_from_file_location('cpu_frequency_under_test', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    response = SimpleNamespace()
    shell = SimpleNamespace(call=lambda command, **kwargs: frequencies if command == 'dmidecode -s processor-frequency'
                            else model + '\n3100.000')
    exec(compile(block, str(HOST), 'exec'), dict(rsp=response, shell=shell, re=re, cpu_frequency=module))
    assert response.cpuGHz == expected

"""Exercise the service report check of the writeback split and VM accounting without importing the whole metrics plugin."""
import ast
import calendar
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

NAMES = ('_memory_observation_seconds', '_accounting_report_quality', '_read_memory_optimization_int',
         '_zram_accounting_generation', 'MEMORY_ACCOUNTING_REPORT_MAX_AGE_SECONDS')
SIZES = {}


@pytest.fixture
def quality():
    path = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/prometheus.py'
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in NAMES
             or isinstance(node, ast.Assign) and any(getattr(target, 'id', None) in NAMES for target in node.targets)]
    SIZES.clear(); SIZES['/sys/block/zram0/disksize'] = '8589934592\n'
    SIZES['/proc/zram0_accounting'] = 'zram_accounting 2\nenabled 1\npage_size 4096\ngeneration 7\nsequence 3\n'
    files = lambda p: 'boot-a\n' if p == '/proc/sys/kernel/random/boot_id' else SIZES.get(p)
    linux = SimpleNamespace(read_file=files)
    scope = dict(re=re, calendar=calendar, time=time, os=os, linux=linux)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), scope)
    return scope['_accounting_report_quality']


def report(**changes):
    value = {'schema_version': 2, 'quality': 'partial_vm_attribution', 'host_boot_id': 'boot-a',
             'device': '/dev/zram0', 'observed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             'inventory': {'schema_version': 2, 'pool_generation': 7},
             'total': {'backend_committed_original_bytes': 4096}}
    value.update(changes)
    return value


@pytest.fixture
def observation_seconds():
    path = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/prometheus.py'
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == '_memory_observation_seconds']
    scope = dict(re=re, calendar=calendar, time=time)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), scope)
    return scope['_memory_observation_seconds']


def test_a_report_time_is_read_in_utc(observation_seconds):
    assert observation_seconds('2026-11-05T16:30:59Z') == 1793896259
    assert observation_seconds('2026-11-06T00:30:59.5+08:00') == 1793896259.5


@pytest.mark.parametrize('value', ['2026-11-05T16:30:60Z', '2026-11-05T16:30:61Z', '2026-11-06T00:30:61.5+08:00'])
def test_a_report_time_with_a_leap_second_is_not_a_time(observation_seconds, value):
    # The service never writes second 60 or 61; such a report has no valid time, so it is not current.
    assert observation_seconds(value) is None


def test_a_current_report_of_this_pool_keeps_its_quality(quality):
    assert quality(report(), ['zram0'], time.time()) == 'partial_vm_attribution'


@pytest.mark.parametrize('changes', [
    {'host_boot_id': 'boot-b'},
    {'device': '/dev/zram1'},
    {'observed_at': '2020-01-01T00:00:00Z'},
    {'observed_at': None},
    {'inventory': ['not', 'an', 'object']}])
def test_a_report_of_another_pool_or_time_is_stale(quality, changes):
    # An earlier boot's or device's committed bytes, or a report made too long ago, are not this pool's.
    assert quality(report(**changes), ['zram0'], time.time()) == 'stale'


def test_a_report_that_could_not_be_built_keeps_its_own_quality(quality):
    assert quality(report(quality='unavailable'), ['zram0'], time.time()) == 'unavailable'
    assert quality(None, ['zram0'], time.time()) == 'unavailable'


def test_a_report_of_a_pool_since_reset_is_stale(quality):
    SIZES['/sys/block/zram0/disksize'] = '0\n'
    assert quality(report(), ['zram0'], time.time()) == 'stale'


@pytest.mark.parametrize('header', ['zram_accounting 2\ngeneration 8\n', 'zram_accounting 2\n', None])
def test_a_report_of_an_earlier_pool_on_the_same_device_is_stale(quality, header):
    # A pool rebuilt on the same device within the report's age has a new kernel generation.
    if header is None:
        del SIZES['/proc/zram0_accounting']
    else:
        SIZES['/proc/zram0_accounting'] = header
    assert quality(report(), ['zram0'], time.time()) == 'stale'
    assert quality(report(inventory={'schema_version': 2}), ['zram0'], time.time()) == 'stale'


class GaugeMetricFamily(object):
    def __init__(self, name, documentation, labels=()):
        self.name, self.labels, self.samples = name, labels, []

    def add_metric(self, values, value):
        self.samples.append(SimpleNamespace(name=self.name, labels=dict(zip(self.labels, values)), value=value))


@pytest.fixture
def collect():
    path = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/prometheus.py'
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == 'collect_memory_optimization_statistics']
    reads, accounted = [], []
    state = {'quality': 'partial_vm_attribution'}
    scope = dict(GaugeMetricFamily=GaugeMetricFamily, PAGE_SIZE=4096, time=time, re=re,
                 os=SimpleNamespace(listdir=lambda path: ['zram0']),
                 _read_memory_optimization_int=lambda path: 0,
                 _memory_optimization_epoch=lambda devices: 'epoch-a',
                 _read_zram_saved_bytes=lambda path: reads.pop(0),
                 _accounting_report_quality=lambda value, devices, now: state['quality'],
                 collect_memory_optimization_vm_accounting=lambda value, quality: accounted.append(quality) or [])
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), scope)

    def run(before, after, quality='partial_vm_attribution'):
        reads[:] = [before, after]
        state['quality'] = quality
        del accounted[:]
        samples = [s for family in scope['collect_memory_optimization_statistics'](report()) for s in family.samples]
        value = lambda name, **labels: next((s.value for s in samples if s.name == name and
                                             all(s.labels.get(k) == v for k, v in labels.items())), None)
        value.accounted = list(accounted)
        return value
    return run


def test_a_stable_zram_pool_is_split_by_the_report(collect):
    value = collect(70 << 30, 70 << 30)
    assert value('host_memory_saved_estimate_bytes', mechanism='total') == 70 << 30
    assert value('host_zram_writeback_saved_bytes') == 4096
    assert value('host_zram_ordinary_saved_bytes') == (70 << 30) - 4096


def test_a_zram_pool_that_moved_keeps_its_total_without_the_split(collect):
    # The pool changed between the reads around the report: the split is not this sample's, the native total is.
    value = collect(70 << 30, 71 << 30)
    assert value('host_zram_saved_estimate_bytes') == 71 << 30
    assert value('host_memory_saved_estimate_bytes', mechanism='zram') == 71 << 30
    assert value('host_memory_saved_estimate_bytes', mechanism='total') == 71 << 30
    assert value('host_memory_optimization_metric_quality', metric='zram', quality='observed') == 1
    assert value('host_zram_writeback_saved_bytes') is None and value('host_zram_ordinary_saved_bytes') is None


def test_a_failed_zram_read_gives_no_total(collect):
    value = collect(None, 71 << 30)
    assert value('host_zram_saved_estimate_bytes') is None
    assert value('host_memory_saved_estimate_bytes', mechanism='total') is None
    assert value('host_memory_optimization_metric_quality', metric='zram', quality='partial') == 0


def test_a_stale_report_neither_splits_the_pool_nor_accounts_vms(collect):
    value = collect(70 << 30, 70 << 30, quality='stale')
    assert value('host_zram_saved_estimate_bytes') == 70 << 30
    assert value('host_zram_writeback_saved_bytes') is None and value('host_zram_ordinary_saved_bytes') is None
    assert value.accounted == ['stale'], 'the VM accounting is given the quality of this scrape'
    assert collect(70 << 30, 70 << 30).accounted == ['partial_vm_attribution']


@pytest.fixture
def accounting():
    path = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/prometheus.py'
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in
             ('_memory_observation_seconds', 'collect_memory_optimization_vm_accounting')]
    scope = dict(GaugeMetricFamily=GaugeMetricFamily, re=re, calendar=calendar, time=time)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), scope)

    def run(value, quality):
        samples = [s for family in scope['collect_memory_optimization_vm_accounting'](value, quality)
                   for s in family.samples]
        return lambda name, **labels: [s.value for s in samples if s.name == name and
                                       all(s.labels.get(k) == v for k, v in labels.items())]
    return run


def vm_report(**changes):
    return report(**dict(changes, vms={'vm-1': {
        'quality': 'source_memcg_inventory',
        'identity': {'instance_generation': 'g1', 'host_boot_id': 'boot-a', 'cgroup_inode': 42, 'start_time': 100},
        'metrics': {'ram_original_bytes': 8192, 'ram_payload_bytes': 1024, 'backend_committed_original_bytes': 4096}}}))


def test_a_current_report_accounts_its_vms(accounting):
    value = accounting(vm_report(), 'partial_vm_attribution')
    assert value('host_zram_vm_saved_bytes', vm_uuid='vm-1', host_boot_id='boot-a', pool_generation='7') == [11264]
    assert value('host_zram_accounting_sample_info', quality='partial_vm_attribution') == [1]


def test_a_stale_report_accounts_no_vm(accounting):
    # An earlier boot's or pool's report, or one made too long ago, is shown stale and gives no VM sample.
    value = accounting(vm_report(), 'stale')
    assert value('host_zram_accounting_sample_info', schema_version='2', quality='stale') == [1]
    for name in ('host_zram_vm_saved_bytes', 'host_zram_vm_identity_info', 'host_zram_vm_accounting_quality',
                 'host_zram_vm_sample_timestamp_seconds', 'host_zram_accounting_generation',
                 'host_zram_accounting_sequence', 'host_zram_tracking_metadata_bytes'):
        assert value(name) == [], name


def test_an_incomplete_report_keeps_its_own_quality(accounting):
    value = accounting(vm_report(quality='unavailable'), 'unavailable')
    assert value('host_zram_accounting_sample_info', quality='unavailable') == [1]
    assert value('host_zram_vm_saved_bytes') == []


def test_a_report_of_another_schema_shows_the_quality_of_this_scrape(accounting):
    value = accounting(vm_report(schema_version=1), 'stale')
    assert value('host_zram_accounting_sample_info', schema_version='1', quality='stale') == [1]
    assert value('host_zram_vm_saved_bytes') == []
    assert accounting(None, 'unavailable')('host_zram_accounting_sample_info', schema_version='unknown',
                                           quality='unavailable') == [1]

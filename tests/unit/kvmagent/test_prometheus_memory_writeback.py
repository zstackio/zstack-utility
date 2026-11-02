"""Exercise the writeback split's report check without importing the whole metrics plugin."""
import ast
import calendar
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

NAMES = ('_memory_observation_seconds', '_writeback_report_current', '_read_memory_optimization_int',
         '_zram_accounting_generation', 'MEMORY_ACCOUNTING_REPORT_MAX_AGE_SECONDS')
SIZES = {}


@pytest.fixture
def current():
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
    return scope['_writeback_report_current']


def report(**changes):
    value = {'schema_version': 2, 'quality': 'partial_vm_attribution', 'host_boot_id': 'boot-a',
             'device': '/dev/zram0', 'observed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             'inventory': {'schema_version': 2, 'pool_generation': 7},
             'total': {'backend_committed_original_bytes': 4096}}
    value.update(changes)
    return value


def test_the_writeback_split_uses_a_current_report_of_this_pool(current):
    assert current(report(), ['zram0'], time.time())


@pytest.mark.parametrize('changes', [
    {'host_boot_id': 'boot-b'},
    {'device': '/dev/zram1'},
    {'quality': 'unavailable'},
    {'observed_at': '2020-01-01T00:00:00Z'},
    {'observed_at': None}])
def test_the_writeback_split_ignores_a_report_of_another_pool_or_time(current, changes):
    # An earlier boot's or device's committed bytes, or a report that could not be built, is not this pool's.
    assert not current(report(**changes), ['zram0'], time.time())


def test_the_writeback_split_ignores_a_report_of_a_pool_since_reset(current):
    SIZES['/sys/block/zram0/disksize'] = '0\n'
    assert not current(report(), ['zram0'], time.time())


@pytest.mark.parametrize('accounting', ['zram_accounting 2\ngeneration 8\n', 'zram_accounting 2\n', None])
def test_the_writeback_split_ignores_a_report_of_an_earlier_pool_on_the_same_device(current, accounting):
    # A pool rebuilt on the same device within the report's age has a new kernel generation.
    if accounting is None:
        del SIZES['/proc/zram0_accounting']
    else:
        SIZES['/proc/zram0_accounting'] = accounting
    assert not current(report(), ['zram0'], time.time())
    assert not current(report(inventory={'schema_version': 2}), ['zram0'], time.time())


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
    reads = []
    scope = dict(GaugeMetricFamily=GaugeMetricFamily, PAGE_SIZE=4096, time=time, re=re,
                 os=SimpleNamespace(listdir=lambda path: ['zram0']),
                 _read_memory_optimization_int=lambda path: 0,
                 _memory_optimization_epoch=lambda devices: 'epoch-a',
                 _read_zram_saved_bytes=lambda path: reads.pop(0),
                 _writeback_report_current=lambda value, devices, now: True,
                 collect_memory_optimization_vm_accounting=lambda value: [])
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), scope)

    def run(before, after):
        reads[:] = [before, after]
        samples = [s for family in scope['collect_memory_optimization_statistics'](report()) for s in family.samples]
        return lambda name, **labels: next((s.value for s in samples if s.name == name and
                                            all(s.labels.get(k) == v for k, v in labels.items())), None)
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

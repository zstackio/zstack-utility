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
         'MEMORY_ACCOUNTING_REPORT_MAX_AGE_SECONDS')
SIZES = {}


@pytest.fixture
def current():
    path = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/prometheus.py'
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in NAMES
             or isinstance(node, ast.Assign) and any(getattr(target, 'id', None) in NAMES for target in node.targets)]
    SIZES.clear(); SIZES['/sys/block/zram0/disksize'] = '8589934592\n'
    files = lambda p: 'boot-a\n' if p == '/proc/sys/kernel/random/boot_id' else SIZES.get(p)
    linux = SimpleNamespace(read_file=files)
    scope = dict(re=re, calendar=calendar, time=time, os=os, linux=linux)
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), 'exec'), scope)
    return scope['_writeback_report_current']


def report(**changes):
    value = {'schema_version': 2, 'quality': 'partial_vm_attribution', 'host_boot_id': 'boot-a',
             'device': '/dev/zram0', 'observed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
             'inventory': {'schema_version': 2}, 'total': {'backend_committed_original_bytes': 4096}}
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

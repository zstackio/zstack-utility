import ast
import builtins
import hashlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest

from kvmagent.plugins.memory_optimization_ksm_native import (
    managed_config_values,
    native_sleep_msec,
    render_config,
)
from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin


class NativeKsmConfigTest(unittest.TestCase):
    def test_converts_requested_sleep_to_vendor_config_units(self):
        self.assertEqual(10, native_sleep_msec(20, 8 * 1024 * 1024))

    def test_rejects_sleep_value_not_representable_by_vendor_formula(self):
        with self.assertRaises(ValueError):
            native_sleep_msec(11, 8 * 1024 * 1024)

    def test_preserves_existing_user_config_and_replaces_only_our_block(self):
        original = "# customer comment\nKSM_MONITOR_INTERVAL=60\n"
        sleep = native_sleep_msec(20, 8 * 1024 * 1024)
        first = render_config(original, revision=1, pages_to_scan=2000,
                              native_sleep=sleep)
        second = render_config(first, revision=2, pages_to_scan=3000,
                               native_sleep=sleep)
        self.assertTrue(second.startswith(original))
        self.assertEqual(1, second.count("# BEGIN ZSTACK MEMORY OPTIMIZATION"))
        self.assertEqual(1, second.count("# END ZSTACK MEMORY OPTIMIZATION"))
        self.assertEqual(3000, managed_config_values(second)["KSM_NPAGES_MAX"])

    def test_rejects_duplicate_or_unclosed_managed_blocks(self):
        for content in (
                "# BEGIN ZSTACK MEMORY OPTIMIZATION\n",
                "# BEGIN ZSTACK MEMORY OPTIMIZATION\n"
                "# END ZSTACK MEMORY OPTIMIZATION\n"
                "# BEGIN ZSTACK MEMORY OPTIMIZATION\n"
                "# END ZSTACK MEMORY OPTIMIZATION\n"):
            with self.assertRaises(ValueError):
                render_config(content, revision=1, pages_to_scan=2000,
                              native_sleep=320)

    def test_preserves_unrelated_shell_config_but_rejects_native_override(self):
        user_config = 'KSM_MONITOR_INTERVAL=30\nCUSTOM_KSM_HOOK="/usr/local/bin/a b"\n'
        block = render_config(user_config, revision=1, pages_to_scan=2000,
                              native_sleep=10)
        self.assertTrue(block.startswith(user_config))
        with self.assertRaisesRegex(ValueError, 'KSM_CONFIG_CUSTOM_VALUE_CONFLICT'):
            render_config('KSM_NPAGES_MAX=3000\n', revision=1,
                          pages_to_scan=2000, native_sleep=10)


def _apply_plugin(tmp_path, policy, enabled_state, run):
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    plugin.KSM_CONF = str(tmp_path / 'ksmtuned.conf')
    plugin.ksm_apply_timeout = 0
    plugin._verify_native_ksm_profile = lambda: None
    (tmp_path / 'ksmtuned.conf').write_text('# vendor default\n')
    units = {'ksm.service': enabled_state, 'ksmtuned.service': enabled_state}
    enabled = ('enabled' if enabled_state == 'active' else
               'disabled' if enabled_state == 'inactive' else enabled_state)
    plugin._native_service_state = lambda unit, operation: (
        units[unit] if operation == 'active' else enabled)
    sysfs = {'run': run, 'pages_to_scan': '2000', 'sleep_millisecs': '20',
             'use_zero_pages': '0'}
    plugin._test_sysfs = sysfs
    plugin._read_ksm_sysfs = lambda name: sysfs[name]
    plugin._write_ksm_sysfs = lambda name, value: sysfs.__setitem__(name, value)
    plugin._read_ksm_ack = lambda: dict(sysfs, configRevision='7')
    published = []
    plugin._publish_ksm_config = published.append
    return plugin, published


def test_native_apply_enabled_uses_vendor_units_and_exact_sysfs_ack(tmp_path):
    plugin, published = _apply_plugin(
        tmp_path, {'enabled': True, 'pagesToScan': 2000, 'sleepMillis': 20,
                   'zeroPagesEnabled': True}, 'inactive', '1')
    events = []
    native_writer = plugin._write_ksm_sysfs
    plugin._write_ksm_sysfs = lambda name, value: (
        events.append('sysfs:' + name), native_writer(name, value))[1]

    def systemctl(args):
        events.append('systemctl:' + ' '.join(args[1:]))

    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call') as call:
        call.side_effect = systemctl
        ack = plugin._apply_ksm_policy({'desiredRevision': 7,
                                        'policy': {'ksm': {'enabled': True,
                                                          'pagesToScan': 2000,
                                                          'sleepMillis': 20,
                                                          'zeroPagesEnabled': True}}})
    assert ack['configRevision'] == '7'
    assert 'KSM_NPAGES_MIN=2000' in published[0]
    assert 'KSM_NPAGES_MAX=2000' in published[0]
    assert 'KSM_NPAGES_BOOST=0' in published[0]
    assert 'KSM_NPAGES_DECAY=0' in published[0]
    assert 'KSM_THRES_COEF=100' in published[0]
    assert call.call_args_list == [
        unittest.mock.call(['systemctl', 'enable', 'ksm.service', 'ksmtuned.service']),
        unittest.mock.call(['systemctl', 'start', 'ksm.service']),
        unittest.mock.call(['systemctl', 'start', 'ksmtuned.service']),
    ]
    assert events.index('sysfs:pages_to_scan') < events.index('systemctl:start ksmtuned.service')
    assert events.index('sysfs:sleep_millisecs') < events.index('systemctl:start ksmtuned.service')
    assert plugin._read_ksm_sysfs('pages_to_scan') == '2000'
    assert plugin._read_ksm_sysfs('sleep_millisecs') == '20'


def test_native_profile_variants_match_only_complete_exact_file_sets(tmp_path):
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    first, second = tmp_path / 'vendor', tmp_path / 'ctl'
    first.write_bytes(b'vendor\n')
    second.write_bytes(b'ctl\n')
    plugin.NATIVE_KSM_PROFILE_VARIANTS = (
        {str(first): hashlib.sha256(b'vendor\n').hexdigest(),
         str(second): hashlib.sha256(b'ctl\n').hexdigest()},)
    plugin._verify_native_ksm_profile()
    second.write_bytes(b'unreviewed\n')
    with pytest.raises(ValueError, match='KSM_NATIVE_PROFILE_UNSUPPORTED'):
        plugin._verify_native_ksm_profile()


def test_native_none_preserves_disabled_service_and_low_pressure_run_zero(tmp_path):
    # An inactive native service is never started merely to apply tuning, but
    # independent scan parameters are still applied through the Agent writer.
    plugin, _ = _apply_plugin(tmp_path, {'pagesToScan': 1777, 'sleepMillis': 25,
                                         'zeroPagesEnabled': True},
                              'inactive', '0')
    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call') as call:
        plugin._apply_ksm_policy({'desiredRevision': 7,
                                  'policy': {'ksm': {'pagesToScan': 1777,
                                                    'sleepMillis': 25,
                                                    'zeroPagesEnabled': True}}})
    call.assert_not_called()
    ack = plugin._read_ksm_ack()
    assert ack['run'] == '0'
    assert ack['pages_to_scan'] == '1777'
    assert ack['sleep_millisecs'] == '25'
    assert ack['use_zero_pages'] == '1'

    # run=0 is not inferred as a user-disabled service when ksmtuned is active.
    plugin, _ = _apply_plugin(tmp_path, {'pagesToScan': 2000, 'sleepMillis': 20},
                              'active', '0')
    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call') as call:
        plugin._apply_ksm_policy({'desiredRevision': 7,
                                  'policy': {'ksm': {'pagesToScan': 2000,
                                                    'sleepMillis': 20}}})
    call.assert_called_once_with(['systemctl', 'restart', 'ksmtuned.service'])


def test_native_none_updates_active_tuned_parameters_before_restart(tmp_path):
    plugin, _published = _apply_plugin(
        tmp_path, {'pagesToScan': 1777, 'sleepMillis': 25}, 'active', '0')
    plugin._read_ksm_ack = lambda: dict(plugin._test_sysfs, configRevision='8')
    events = []
    native_writer = plugin._write_ksm_sysfs

    def write_sysfs(name, value):
        events.append('sysfs:' + name + '=' + value)
        native_writer(name, value)

    plugin._write_ksm_sysfs = write_sysfs

    def systemctl(args):
        events.append('systemctl:' + ' '.join(args[1:]))

    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call',
               side_effect=systemctl) as call:
        ack = plugin._apply_ksm_policy({'desiredRevision': 8,
            'policy': {'ksm': {'enabled': None, 'pagesToScan': 1777,
                               'sleepMillis': 25}}})

    assert ack['run'] == '0'
    assert ack['pages_to_scan'] == '1777'
    assert ack['sleep_millisecs'] == '25'
    assert events == ['sysfs:pages_to_scan=1777',
                      'sysfs:sleep_millisecs=25',
                      'systemctl:restart ksmtuned.service']
    call.assert_called_once_with(['systemctl', 'restart', 'ksmtuned.service'])


@pytest.mark.parametrize('service_state', ['active', 'inactive'])
def test_native_false_applies_parameters_without_starting_vendor_services(tmp_path, service_state):
    plugin, _published = _apply_plugin(tmp_path, {'enabled': False}, service_state, '1')
    events = []
    plugin._publish_ksm_config = lambda content: events.append('config')

    def systemctl(args):
        events.append(' '.join(args[1:]))

    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call',
               side_effect=systemctl) as call:
        plugin._apply_ksm_policy({'desiredRevision': 7,
                                  'policy': {'ksm': {'enabled': False,
                                                    'pagesToScan': 333,
                                                    'sleepMillis': 25,
                                                    'zeroPagesEnabled': False}}})
    assert call.call_args_list == [
        unittest.mock.call(['systemctl', 'stop', 'ksmtuned.service']),
        unittest.mock.call(['systemctl', 'stop', 'ksm.service']),
        unittest.mock.call(['systemctl', 'disable', 'ksmtuned.service', 'ksm.service']),
    ]
    assert events.index('stop ksmtuned.service') < events.index('config')
    assert events.index('config') < events.index('disable ksmtuned.service ksm.service')
    assert plugin._read_ksm_sysfs('run') == '0'
    ack = plugin._read_ksm_ack()
    assert ack['run'] == '0'
    assert ack['pages_to_scan'] == '333'
    assert ack['sleep_millisecs'] == '25'
    assert ack['use_zero_pages'] == '0'


def test_disabled_apply_uses_real_sysfs_writer_for_independent_scan_parameters(tmp_path):
    sysfs_root = tmp_path / 'sys' / 'kernel' / 'mm' / 'ksm'
    sysfs_root.mkdir(parents=True)
    for name, value in {'run': '1', 'pages_to_scan': '2000',
                        'sleep_millisecs': '20', 'use_zero_pages': '1'}.items():
        (sysfs_root / name).write_text(value)

    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    plugin.KSM_CONF = str(tmp_path / 'ksmtuned.conf')
    plugin.ksm_apply_timeout = 0
    plugin._verify_native_ksm_profile = lambda: None
    plugin._read_native_ksm_config = lambda: {'CONFIG_REVISION': 8}
    plugin._native_service_state = lambda unit, operation: (
        'active' if operation == 'active' else 'enabled')
    plugin._publish_ksm_config = lambda content: None
    plugin._read_ksm_sysfs = MemoryOptimizationPlugin._read_ksm_sysfs
    plugin._write_ksm_sysfs = MemoryOptimizationPlugin._write_ksm_sysfs

    real_open = builtins.open

    def open_test_sysfs(path, *args, **kwargs):
        prefix = '/sys/kernel/mm/ksm/'
        if isinstance(path, str) and path.startswith(prefix):
            path = str(sysfs_root / path[len(prefix):])
        return real_open(path, *args, **kwargs)

    def systemctl(args):
        if args == ['systemctl', 'stop', 'ksm.service']:
            (sysfs_root / 'run').write_text('0')

    with patch('builtins.open', side_effect=open_test_sysfs), \
            patch('kvmagent.plugins.memory_optimization.subprocess.check_call',
                  side_effect=systemctl):
        ack = plugin._apply_ksm_policy({'desiredRevision': 8,
            'policy': {'ksm': {'enabled': False, 'pagesToScan': 333,
                               'sleepMillis': 25, 'zeroPagesEnabled': False}}})

    assert ack == {'run': '0', 'configRevision': '8', 'pages_to_scan': '333',
                   'sleep_millisecs': '25', 'use_zero_pages': '0'}
    assert (sysfs_root / 'run').read_text() == '0'
    assert (sysfs_root / 'pages_to_scan').read_text() == '333'
    assert (sysfs_root / 'sleep_millisecs').read_text() == '25'
    assert (sysfs_root / 'use_zero_pages').read_text() == '0'


def test_native_apply_rejects_unknown_service_state_before_config_write(tmp_path):
    plugin, published = _apply_plugin(tmp_path, {'enabled': True}, 'unknown', '0')
    with pytest.raises(ValueError, match='KSM_NATIVE_SERVICE_STATE_UNKNOWN'):
        plugin._apply_ksm_policy({'desiredRevision': 7,
                                  'policy': {'ksm': {'enabled': True}}})
    assert published == []


def test_native_apply_rejects_masked_vendor_units_without_takeover(tmp_path):
    plugin, published = _apply_plugin(tmp_path, {'enabled': True}, 'masked', '0')
    with pytest.raises(ValueError, match='KSM_NATIVE_SERVICE_STATE_UNKNOWN'):
        plugin._apply_ksm_policy({'desiredRevision': 7,
                                  'policy': {'ksm': {'enabled': True}}})
    assert published == []


def test_native_readback_keeps_the_existing_five_field_ack_contract():
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    plugin._read_ksm_sysfs = lambda name: {
        'run': '1', 'pages_to_scan': '2000', 'sleep_millisecs': '20',
        'use_zero_pages': '1',
    }[name]
    plugin._read_native_ksm_config = lambda: {'CONFIG_REVISION': 7}

    ack = plugin._read_ksm_ack()

    assert ack == {'run': '1', 'configRevision': '7', 'pages_to_scan': '2000',
                   'sleep_millisecs': '20', 'use_zero_pages': '1'}
    assert plugin._ksm_proof_matches(ack, 7)


def test_native_readback_cannot_prove_a_missing_revision_or_changed_sysfs_value():
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    plugin._read_ksm_sysfs = lambda name: {
        'run': '1', 'pages_to_scan': '2000', 'sleep_millisecs': '20',
        'use_zero_pages': '0',
    }[name]
    plugin._read_native_ksm_config = lambda: None
    assert plugin._read_ksm_ack() is None

    proof = {'run': '1', 'configRevision': '7', 'pages_to_scan': '2000',
             'sleep_millisecs': '20', 'use_zero_pages': '1'}
    plugin._read_native_ksm_config = lambda: {'CONFIG_REVISION': 7}
    assert not plugin._ksm_proof_matches(proof, 7)

def test_zero_page_absence_is_distinct_from_permission_and_malformed_values():
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    plugin._read_ksm_sysfs = lambda name: (_ for _ in ()).throw(
        FileNotFoundError(2, 'missing'))
    assert plugin._read_ksm_zero_pages() == 'unsupported'

    plugin._read_ksm_sysfs = lambda name: (_ for _ in ()).throw(
        PermissionError(13, 'denied'))
    with pytest.raises(PermissionError):
        plugin._read_ksm_zero_pages()

    plugin._read_ksm_sysfs = lambda name: (_ for _ in ()).throw(
        ValueError('KSM_SYSFS_READBACK_INVALID:use_zero_pages'))
    with pytest.raises(ValueError, match='KSM_SYSFS_READBACK_INVALID'):
        plugin._read_ksm_zero_pages()

    plugin._read_ksm_sysfs = lambda name: '2'
    with pytest.raises(ValueError, match='KSM_ZERO_PAGES_READBACK_INVALID'):
        plugin._read_ksm_zero_pages()

    plugin._read_ksm_sysfs = lambda name: {
        'run': '1', 'pages_to_scan': '2000', 'sleep_millisecs': '20'
    }[name] if name != 'use_zero_pages' else (_ for _ in ()).throw(
        FileNotFoundError(2, 'missing'))
    plugin._read_native_ksm_config = lambda: {'CONFIG_REVISION': 7}
    assert plugin._read_ksm_ack() == {
        'run': '1', 'configRevision': '7', 'pages_to_scan': '2000',
        'sleep_millisecs': '20', 'use_zero_pages': 'unsupported'}
    plugin._read_ksm_sysfs = lambda name: {
        'run': '1', 'pages_to_scan': '2000', 'sleep_millisecs': '20'
    }[name] if name != 'use_zero_pages' else (_ for _ in ()).throw(
        PermissionError(13, 'denied'))
    assert plugin._read_ksm_ack() is None


def test_missing_zero_page_interface_does_not_claim_a_false_value_or_accept_true(tmp_path_factory):
    plugin, published = _apply_plugin(tmp_path_factory.mktemp('ksm-unsupported'),
                                      {'enabled': True}, 'active', '1')
    sysfs = {'run': '1', 'configRevision': '7', 'pages_to_scan': '2000',
             'sleep_millisecs': '20', 'use_zero_pages': 'unsupported'}
    writes = []
    plugin._read_ksm_zero_pages = lambda: 'unsupported'
    plugin._read_ksm_ack = lambda: dict(sysfs)
    plugin._write_ksm_sysfs = lambda name, value: writes.append((name, value))

    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call') as call:
        with pytest.raises(ValueError, match='KSM_ZERO_PAGES_UNSUPPORTED'):
            plugin._apply_ksm_policy({'desiredRevision': 7,
                'policy': {'ksm': {'enabled': True, 'zeroPagesEnabled': True}}})
    assert published == []
    assert writes == []
    call.assert_not_called()

    # Explicit false is not misreported as a kernel readback of false; the
    # five-field internal ACK carries the explicit unsupported sentinel.
    plugin, _ = _apply_plugin(tmp_path_factory.mktemp('ksm-unsupported-false'),
                              {'enabled': False}, 'inactive', '0')
    sysfs = {'run': '0', 'configRevision': '7', 'pages_to_scan': '2000',
             'sleep_millisecs': '20', 'use_zero_pages': 'unsupported'}
    writes = []
    plugin._read_ksm_zero_pages = lambda: 'unsupported'
    plugin._read_ksm_ack = lambda: dict(sysfs)
    plugin._write_ksm_sysfs = lambda name, value: writes.append((name, value))
    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call') as call:
        ack = plugin._apply_ksm_policy({'desiredRevision': 7,
            'policy': {'ksm': {'enabled': False, 'zeroPagesEnabled': False}}})
    assert ack['use_zero_pages'] == 'unsupported'
    assert ('use_zero_pages', '0') not in writes
    assert all(name != 'use_zero_pages' for name, _ in writes)
    assert plugin._ksm_readback_matches({'enabled': False, 'zeroPagesEnabled': False}, 7)

    plugin, _ = _apply_plugin(tmp_path_factory.mktemp('ksm-unsupported-omit'),
                              {'enabled': None}, 'inactive', '0')
    sysfs = {'run': '0', 'configRevision': '7', 'pages_to_scan': '2000',
             'sleep_millisecs': '20', 'use_zero_pages': 'unsupported'}
    writes = []
    plugin._read_ksm_zero_pages = lambda: 'unsupported'
    plugin._read_ksm_ack = lambda: dict(sysfs)
    plugin._write_ksm_sysfs = lambda name, value: writes.append((name, value))
    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call') as call:
        ack = plugin._apply_ksm_policy({'desiredRevision': 7,
                                        'policy': {'ksm': {'enabled': None}}})
    assert ack['use_zero_pages'] == 'unsupported'
    assert all(name != 'use_zero_pages' for name, _ in writes)
    call.assert_not_called()


def test_ksm_proof_is_strict_across_zero_page_capability_changes():
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    current = {'run': '1', 'configRevision': '7', 'pages_to_scan': '2000',
               'sleep_millisecs': '20', 'use_zero_pages': 'unsupported'}
    plugin._read_ksm_ack = lambda: dict(current)
    old_full = dict(current, use_zero_pages='0')
    new_unsupported = dict(current)

    assert not plugin._ksm_proof_matches(old_full, 7)
    assert plugin._ksm_proof_matches(new_unsupported, 7)
    assert plugin._ksm_readback_matches(
        {'enabled': True, 'pagesToScan': 2000, 'sleepMillis': 20,
         'zeroPagesEnabled': False}, 7, old_full) is False
    assert plugin._ksm_readback_matches(
        {'enabled': True, 'pagesToScan': 2000, 'sleepMillis': 20,
         'zeroPagesEnabled': False}, 7, new_unsupported)

    current['use_zero_pages'] = '0'
    assert not plugin._ksm_proof_matches(new_unsupported, 7)
    assert not plugin._ksm_readback_matches(
        {'enabled': True, 'pagesToScan': 2000, 'sleepMillis': 20}, 7,
        new_unsupported)


def test_first_use_history_accepts_explicit_false_only_with_unsupported_proof():
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    plugin._load_host_uuid = lambda: 'host-1'
    proof = {'run': '1', 'configRevision': '7', 'pages_to_scan': '2000',
             'sleep_millisecs': '20', 'use_zero_pages': 'unsupported'}
    record = {'stage': 'APPLIED', 'action': 'apply', 'hostUuid': 'host-1',
              'requestHash': 'a' * 64, 'desiredRevision': 7,
              'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                 'sleepMillis': 20, 'zeroPagesEnabled': False}},
              'readback': {'success': True, 'status': 'Succeeded',
                           'appliedRevision': 7, 'ksmReadback': proof,
                           'state': {'ksmOnly': True}}}
    plugin._ksm_only_disabled_service_sections = lambda policy: True
    assert plugin._first_use_terminal_ksm_record(record)
    record['policy']['ksm']['zeroPagesEnabled'] = True
    assert not plugin._first_use_terminal_ksm_record(record)


def test_managed_clear_advances_ordinary_ksm_without_claiming_missing_zero_pages(tmp_path):
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    plugin.KSM_CONF = str(tmp_path / 'ksmtuned.conf')
    plugin.ksm_apply_timeout = 0
    plugin._verify_native_ksm_profile = lambda: None
    plugin._native_service_state = lambda unit, operation: (
        'inactive' if operation == 'active' else 'disabled')
    prior_ack = {'run': '1', 'configRevision': '7', 'pages_to_scan': '2000',
                 'sleep_millisecs': '20', 'use_zero_pages': 'unsupported'}
    current = dict(prior_ack, configRevision='8')
    plugin._read_ksm_zero_pages = lambda: 'unsupported'
    plugin._read_ksm_ack = lambda: dict(current)
    writes = []
    plugin._write_ksm_sysfs = lambda name, value: writes.append((name, value))
    published = []
    plugin._publish_ksm_config = published.append
    (tmp_path / 'ksmtuned.conf').write_text('# vendor default\n')

    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call') as call:
        ack = plugin._apply_ksm_policy(
            {'desiredRevision': 8, 'policy': {}},
            clear_context={'priorKsmAck': prior_ack})

    assert ack['use_zero_pages'] == 'unsupported'
    assert writes == [('pages_to_scan', '2000'), ('sleep_millisecs', '20')]
    assert published
    call.assert_not_called()


def test_state_omits_zero_page_value_when_kernel_interface_is_absent():
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    values = {'run': '1', 'pages_to_scan': '2000', 'sleep_millisecs': '20'}

    def read_sysfs(name):
        if name == 'use_zero_pages':
            raise FileNotFoundError(2, 'missing')
        return values[name]

    plugin._read_ksm_sysfs = read_sysfs
    plugin._read_native_ksm_config = lambda: {'CONFIG_REVISION': 7}
    plugin._native_service_state = lambda unit, operation: (
        'active' if operation == 'active' else 'enabled')
    plugin.service_call = lambda action, command: (
        {'efficiency_enabled': True} if action == 'host-cpu-state' else {})
    plugin._get_active_control = lambda: None
    plugin._maintenance_proof_for_state = lambda state: None
    plugin._complete_vm_inventory = lambda vms: (vms or {}, True)
    plugin.discover_capabilities = lambda: {'ksmZeroPages': False}
    result = plugin._enrich_state({'state': {'vms': {}}})

    actual = result['state']['actual']['ksm']
    assert actual['pagesToScan'] == 2000
    assert actual['sleepMillis'] == 20
    assert 'zeroPagesEnabled' not in actual
    assert 'zeroPagesSupport' not in actual

@pytest.mark.parametrize('setting,expected', [('true', '1'), ('false', '0')])
def test_ansible_connect_switch_yields_to_existing_managed_config(setting, expected):
    source = Path(__file__).resolve().parents[3] / 'kvmagent' / 'ansible' / 'kvm.py'
    tree = ast.parse(source.read_text(), filename=str(source))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'do_ksm_config')
    calls = []
    env = {'isEnableKsm': setting, 'host_post_info': SimpleNamespace(),
           'run_remote_command': lambda *args, **kwargs: calls.append(args)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), env)

    env['do_ksm_config']()

    assert len(calls) == 1
    command = calls[0][0]
    assert "grep -Eq '^# (BEGIN|END) ZSTACK MEMORY OPTIMIZATION$'" in command
    assert '/etc/ksmtuned.conf' in command
    assert 'echo %s > /sys/kernel/mm/ksm/run' % expected in command


def test_ansible_connect_none_does_not_write_run():
    source = Path(__file__).resolve().parents[3] / 'kvmagent' / 'ansible' / 'kvm.py'
    tree = ast.parse(source.read_text(), filename=str(source))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'do_ksm_config')
    calls = []
    env = {'isEnableKsm': 'none', 'host_post_info': SimpleNamespace(),
           'run_remote_command': lambda *args, **kwargs: calls.append(args)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), env)
    env['do_ksm_config']()
    assert calls == []


@pytest.mark.parametrize('zero_value', ['0', 'unsupported'])
def test_native_pause_resume_uses_current_boot_ack_and_never_unmerges(zero_value):
    plugin = MemoryOptimizationPlugin.__new__(MemoryOptimizationPlugin)
    ack = {'run': '1', 'configRevision': '5', 'pages_to_scan': '2000',
           'sleep_millisecs': '20', 'use_zero_pages': zero_value}
    prior = {'operationUuid': 'apply-1', 'action': 'apply', 'stage': 'APPLIED',
             'hostUuid': 'host-1', 'bootId': 'boot-1', 'desiredRevision': 5,
             'policy': {'ksm': {'enabled': True, 'pagesToScan': 2000,
                                'sleepMillis': 20, 'zeroPagesEnabled': False}},
             'readback': {'success': True, 'status': 'Succeeded',
                          'appliedRevision': 5, 'ksmReadback': ack}}
    units = {'ksm.service': 'active', 'ksmtuned.service': 'active'}
    sysfs = dict(ack)
    plugin._get_active_control = lambda: 'apply-1'
    plugin._load_operation = lambda command: prior
    plugin._load_host_uuid = lambda: 'host-1'
    plugin._current_boot_id = lambda: 'boot-1'
    plugin._managed_ksm_clear_ack = lambda require_ksm_only=True: dict(ack)
    plugin._read_ksm_ack = lambda: dict(sysfs)
    plugin._read_ksm_sysfs = lambda name: sysfs[name]
    plugin._native_service_state = lambda unit, operation: (
        units[unit] if operation == 'active' else 'enabled')
    plugin._verify_native_ksm_profile = lambda: None
    writes = []

    def write_sysfs(name, value):
        writes.append((name, value))
        sysfs[name] = value

    plugin._write_ksm_sysfs = write_sysfs
    pause_record = {}
    plugin._resume_control_record = lambda: pause_record

    def systemctl(args):
        if args[1] == 'stop':
            units[args[2]] = 'inactive'
        elif args[1] == 'start':
            units[args[2]] = 'active'

    with patch('kvmagent.plugins.memory_optimization.subprocess.check_call',
               side_effect=systemctl) as call:
        paused = plugin._control_managed_ksm(
            'pause', {'expectedControlOperationUuid': 'apply-1'})
        pause_record.update({
            'operationUuid': 'pause-1', 'action': 'pause', 'stage': 'APPLIED',
            'expectedControlOperationUuid': 'apply-1', 'hostUuid': 'host-1',
            'bootId': 'boot-1', 'readback': {'state': {'ksmLifecycle': paused}}})
        resumed = plugin._control_managed_ksm(
            'resume', {'expectedControlOperationUuid': 'pause-1'})
    assert paused == {'controlOperationUuid': 'apply-1', 'runBeforePause': '1',
                      'ksmWasActive': True, 'ksmtunedWasActive': True}
    assert resumed == {'controlOperationUuid': 'apply-1', 'runRestored': '1',
                       'ksmResumed': True, 'ksmtunedResumed': True}
    assert writes == [('run', '0'), ('run', '1')]
    assert all('run=2' not in str(args) for args, _ in call.call_args_list)


if __name__ == "__main__":
    unittest.main()

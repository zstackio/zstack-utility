import importlib
import json
import logging
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import types
from unittest.mock import Mock

import pytest

ADDRESS = '0000:b3:00.0'
OTHER = '0000:b4:00.0'


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    path = tmp_path_factory.mktemp('sansec-sdk') / 'libswsds-test.so'
    source = Path(__file__).parent / 'fixtures/sansec_sdk.c'
    subprocess.run(['gcc', '-shared', '-fPIC', '-Wall', '-Werror', str(source), '-o', str(path)], check=True)
    return str(path)


@pytest.fixture
def detector(tmp_path, monkeypatch, library):
    log = types.ModuleType('zstacklib.utils.log')
    log.get_logger = logging.getLogger
    monkeypatch.setitem(sys.modules, log.__name__, log)
    import zstacklib.utils
    monkeypatch.setattr(zstacklib.utils, 'log', log, raising=False)
    for name in ('shell', 'lock'):
        monkeypatch.delitem(sys.modules, 'zstacklib.utils.' + name, raising=False)
        monkeypatch.delattr(zstacklib.utils, name, raising=False)
    import kvmagent.crypto
    monkeypatch.delitem(sys.modules, 'kvmagent.crypto.sansec_health', raising=False)
    monkeypatch.delattr(kvmagent.crypto, 'sansec_health', raising=False)
    health = importlib.import_module('kvmagent.crypto.sansec_health')
    sysfs = tmp_path / 'pci'
    pf = sysfs / ADDRESS
    pf.mkdir(parents=True)
    (pf / 'vendor').write_text('0x1ed4')
    (pf / 'device').write_text('0x7011')
    driver = tmp_path / 'drivers/swcsm'
    (driver / 'module').mkdir(parents=True)
    (driver / 'module/version').write_text('test-driver')
    (pf / 'driver').symlink_to(driver)
    config = dict(libraryPath=library, timeout=1, devices={ADDRESS: dict(
        serialNumber='TEST-SERIAL', firmwareVersion='test-firmware', libraryVersion='test-library',
        driverVersion='test-driver', compatible=True, supportedVfCounts=[2],
        pollInterval=2, validityPeriod=10, recoveryInterval=4)})
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(health, 'CONFIG_PATH', str(config_path))
    monkeypatch.setattr(health, 'SYSFS_DEVICES', str(sysfs))
    nodes = tmp_path / 'dev'
    nodes.mkdir()
    (nodes / 'swcsm-pci30-0').symlink_to('/dev/null')
    monkeypatch.setattr(health, 'SDK_DEVICE_GLOB', str(nodes / 'swcsm*'))
    monkeypatch.setenv('SANSEC_TEST_TRACE', str(tmp_path / 'trace'))
    instance = health.SansecHealthDetector()
    instance.test_config = config
    instance.test_path = tmp_path
    instance.test_module = health
    return instance


def report(detector):
    return detector.health([ADDRESS])[0]


def configure(detector):
    (detector.test_path / 'config.json').write_text(json.dumps(detector.test_config))


def failure(monkeypatch, stage, code):
    monkeypatch.setenv('SANSEC_TEST_FAIL', stage)
    monkeypatch.setenv('SANSEC_TEST_CODE', hex(code))


def test_real_ctypes_worker_reads_identity_checks_vector_and_closes_handles(detector):
    result = report(detector)
    assert result['healthStatus'] == 'Normal'
    assert result['qualification'] == 'Qualified' and result['serialNumber'] == 'TEST-SERIAL'
    assert result['firmwareVersion'] == 'test-firmware' and result['supportedVfCounts'] == [2]
    assert (detector.test_path / 'trace').read_text().splitlines() == [
        'open', 'session', 'info', 'firmware', 'library', 'init', 'update', 'final', 'close_session', 'close_device']


@pytest.mark.parametrize('code,expected', [(0x01000004, 'Fault'), (0x01000003, 'Unknown'),
                                         (0x01000007, 'Unknown'), (0x01000009, 'Unknown'), (0xffffffff, 'Unknown')])
def test_only_explicit_hardware_error_is_immediate_fault(detector, monkeypatch, code, expected):
    failure(monkeypatch, 'init', code)
    result = report(detector)
    assert result['healthStatus'] == expected
    assert '0x%08x' % code in result['reason']
    assert (detector.test_path / 'trace').read_text().endswith('close_session\nclose_device\n')


def test_wrong_standard_vector_confirms_fault(detector, monkeypatch):
    monkeypatch.setenv('SANSEC_TEST_BAD_HASH', '1')
    assert report(detector)['healthStatus'] == 'Fault'


@pytest.mark.parametrize('stage,closed', [('open', ''), ('session', 'close_device\n'),
                                        ('info', 'close_session\nclose_device\n')])
def test_failure_before_identity_never_marks_an_arbitrary_pf_fault(detector, monkeypatch, stage, closed):
    failure(monkeypatch, stage, 0x01000004)
    result = report(detector)
    assert result['healthStatus'] == 'Unknown' and result['qualification'] == 'Unverified'
    assert (detector.test_path / 'trace').read_text().endswith(closed)


def test_communication_requires_three_spaced_consecutive_samples(detector, monkeypatch):
    failure(monkeypatch, 'init', 0x01000003)
    clock = Mock(return_value=100)
    monkeypatch.setattr(detector.test_module.time, 'monotonic', clock)
    assert report(detector)['healthStatus'] == 'Unknown'
    assert report(detector)['healthStatus'] == 'Unknown'
    assert detector.failures[ADDRESS][0] == 1, 'Repeated calls within one poll interval must not accelerate HA'
    clock.return_value = 102
    assert report(detector)['healthStatus'] == 'Unknown'
    clock.return_value = 104
    assert report(detector)['healthStatus'] == 'Fault'
    monkeypatch.delenv('SANSEC_TEST_FAIL')
    assert report(detector)['healthStatus'] == 'Normal'
    assert not detector.failures


@pytest.mark.parametrize('interruption', ['collector', 'permission', 'config', 'expired'])
def test_interrupted_or_stale_communication_streak_cannot_trigger_fault(detector, monkeypatch, interruption):
    failure(monkeypatch, 'init', 0x01000003)
    clock = Mock(return_value=100)
    monkeypatch.setattr(detector.test_module.time, 'monotonic', clock)
    report(detector)
    clock.return_value = 102
    report(detector)
    if interruption == 'collector':
        with monkeypatch.context() as context:
            context.setattr(detector, 'probe', Mock(return_value=dict(status='unknown', reason='collector error')))
            assert report(detector)['healthStatus'] == 'Unknown'
    elif interruption == 'permission':
        failure(monkeypatch, 'init', 0x01000007)
        assert report(detector)['healthStatus'] == 'Unknown'
        failure(monkeypatch, 'init', 0x01000003)
    elif interruption == 'config':
        detector.test_config['devices'][ADDRESS]['recoveryInterval'] = 5
        configure(detector)
    clock.return_value = 120 if interruption == 'expired' else 104
    assert report(detector)['healthStatus'] == 'Unknown'
    assert detector.failures[ADDRESS][0] == 1


@pytest.mark.parametrize('stage,attributed', [('open', False), ('init', True), ('close_session', False)])
def test_native_hang_is_bounded_and_only_attributed_operation_counts(detector, monkeypatch, stage, attributed):
    monkeypatch.setenv('SANSEC_TEST_HANG', stage)
    start = time.monotonic()
    result = report(detector)
    assert time.monotonic() - start < 4
    assert result['healthStatus'] == 'Unknown'
    assert bool(detector.failures) is attributed
    assert detector.pending is None, 'Timed-out child must be killed and reaped'


def test_worker_still_exiting_prevents_overlap(detector, monkeypatch):
    process = Mock()
    process.poll.return_value = None
    process.communicate.side_effect = subprocess.TimeoutExpired('worker', 1)
    spawn = Mock(return_value=process)
    monkeypatch.setattr(detector.test_module.shell, 'get_process', spawn)
    assert report(detector)['healthStatus'] == 'Unknown'
    assert detector.pending is not None
    pending_dir = Path(detector.pending[1]).parent
    assert stat.S_IMODE(pending_dir.stat().st_mode) == 0o700
    assert report(detector)['healthStatus'] == 'Unknown'
    assert spawn.call_count == 1
    process.kill.assert_called_once()
    process.poll.return_value = -9
    process.communicate.side_effect = None
    with monkeypatch.context() as context:
        context.setattr(detector.test_module.shell, 'get_process', Mock(side_effect=OSError('cannot spawn')))
        assert report(detector)['healthStatus'] == 'Unknown'
    assert detector.pending is None
    assert not pending_dir.exists(), 'Reaped workers must release the private result directory'


def test_worker_crash_after_identification_is_a_collection_error(detector, monkeypatch):
    monkeypatch.setenv('SANSEC_TEST_CRASH', 'init')
    result = report(detector)
    assert result['healthStatus'] == 'Unknown' and result['qualification'] == 'Unverified'
    assert 'exited with code 17' in result['reason']
    assert not detector.failures


@pytest.mark.parametrize('requested', [[ADDRESS], [ADDRESS, OTHER]])
def test_multiple_sdk_endpoints_cannot_be_disambiguated_by_card_serial(detector, requested):
    path = detector.test_path / 'pci'
    (path / OTHER).symlink_to(path / ADDRESS)
    profile = dict(detector.test_config['devices'][ADDRESS], serialNumber='OTHER-SERIAL')
    detector.test_config['devices'][OTHER] = profile
    configure(detector)
    reports = detector.health(requested)
    assert all(r['healthStatus'] == 'Unknown' and r['qualification'] == 'Unverified' for r in reports)
    assert not (detector.test_path / 'trace').exists(), 'Do not open an arbitrary PF, even if only one PF was requested'


def test_wrong_serial_is_unknown_and_skips_algorithm_test(detector, monkeypatch):
    monkeypatch.setenv('SANSEC_TEST_SERIAL', 'WRONG-SERIAL')
    assert report(detector)['healthStatus'] == 'Unknown'
    assert 'init\n' not in (detector.test_path / 'trace').read_text()


@pytest.mark.parametrize('field', ['firmwareVersion', 'libraryVersion', 'driverVersion'])
def test_version_drift_disables_health_and_compatibility(detector, field):
    detector.test_config['devices'][ADDRESS][field] = 'different-version'
    configure(detector)
    result = report(detector)
    assert result['healthStatus'] == 'Unknown' and result['qualification'] == 'Unverified'


def test_healthy_sdk_does_not_invent_compatibility(detector):
    detector.test_config['devices'][ADDRESS]['compatible'] = False
    configure(detector)
    result = report(detector)
    assert result['healthStatus'] == 'Normal' and result['qualification'] == 'Unverified'


def single_card_functions(detector):
    root = detector.test_path
    (root / 'pci' / ADDRESS / 'sriov_totalvfs').write_text('64')
    for index in range(1, 4):
        function = root / 'pci' / ('0000:b3:00.%s' % index)
        function.mkdir()
        (function / 'vendor').write_text('0x1ed4')
        (function / 'device').write_text('0x7011')
        (function / 'driver').symlink_to(root / 'drivers/swcsm')


def test_one_card_companions_do_not_prevent_primary_health_or_receive_its_result(detector):
    single_card_functions(detector)
    addresses = [ADDRESS, '0000:b3:00.1', '0000:b3:00.2', '0000:b3:00.3']
    reports = detector.health(addresses)
    assert reports[0]['healthStatus'] == 'Normal'
    assert all(r['healthStatus'] == 'Unknown' and r['qualification'] == 'Unverified' for r in reports[1:])
    assert (detector.test_path / 'trace').read_text().splitlines().count('open') == 1


@pytest.mark.parametrize('problem', ['missing_function', 'other_card', 'vf_on_host', 'wrong_id', 'second_sriov_pf'])
def test_ambiguous_card_topology_never_opens_an_arbitrary_sdk_device(detector, problem):
    single_card_functions(detector)
    root = detector.test_path / 'pci'
    companion = root / '0000:b3:00.1'
    if problem == 'missing_function':
        (companion / 'driver').unlink()
    elif problem == 'other_card':
        (root / OTHER).symlink_to(root / ADDRESS)
    elif problem == 'vf_on_host':
        vf = root / '0000:b3:01.0'
        vf.mkdir()
        (vf / 'driver').symlink_to(detector.test_path / 'drivers/swcsm')
        (vf / 'physfn').symlink_to(root / ADDRESS)
    elif problem == 'wrong_id':
        (companion / 'device').write_text('0x1001')
    else:
        (companion / 'sriov_totalvfs').write_text('64')
    assert report(detector)['healthStatus'] == 'Unknown'
    assert not (detector.test_path / 'trace').exists(), 'Ambiguous endpoints must be rejected before SDK access'


@pytest.mark.parametrize('problem', ['missing', 'regular_file', 'multiple'])
def test_sdk_character_device_must_be_unique(detector, problem):
    node = detector.test_path / 'dev/swcsm-pci30-0'
    if problem in ('missing', 'regular_file'):
        node.unlink()
    if problem == 'regular_file':
        node.write_text('not a driver device')
    elif problem == 'multiple':
        (node.parent / 'swcsm-pci30-1').symlink_to('/dev/zero')
    assert report(detector)['healthStatus'] == 'Unknown'
    assert not (detector.test_path / 'trace').exists()


@pytest.mark.parametrize('problem', [None, 'split', 'missing', 'other_card', 'alias', 'other_major', 'regular'])
def test_unsplit_card_nodes_preserve_health_without_accepting_ambiguous_endpoints(detector, monkeypatch, problem):
    single_card_functions(detector)
    pf = detector.test_path / 'pci' / ADDRESS
    (pf / 'sriov_numvfs').write_text('2' if problem == 'split' else '0')
    nodes = detector.test_path / 'dev'
    (nodes / 'swcsm-pci30-0').unlink()
    statuses = {}
    for index in range(4):
        if problem == 'missing' and index == 3:
            continue
        prefix = 'swcsm-pci31' if problem == 'other_card' and index == 3 else 'swcsm-pci30'
        node = nodes / ('%s-%s' % (prefix, index))
        node.touch()
        minor = 0 if problem == 'alias' and index == 3 else index
        major = 114 if problem == 'other_major' and index == 3 else 113
        mode = stat.S_IFREG if problem == 'regular' and index == 3 else stat.S_IFCHR
        statuses[str(node)] = types.SimpleNamespace(st_mode=mode, st_rdev=os.makedev(major, minor))
    real_stat = os.stat
    monkeypatch.setattr(detector.test_module.os, 'stat',
                        lambda path, *a, **kw: statuses.get(str(path)) or real_stat(path, *a, **kw))
    result = report(detector)
    if problem is None:
        assert result['healthStatus'] == 'Normal', 'Unsplit must remain checkable so the same PF can be split again'
    else:
        assert result['healthStatus'] == 'Unknown'
        assert not (detector.test_path / 'trace').exists(), 'Ambiguous nodes must be rejected before opening the SDK'


def test_srcversion_identity_is_explicit_and_drift_prevents_sdk_access(detector):
    module = detector.test_path / 'drivers/swcsm/module'
    (module / 'version').unlink()
    (module / 'srcversion').write_text('VERIFIED-SOURCE-HASH')
    profile = detector.test_config['devices'][ADDRESS]
    profile.update(driverVersionSource='srcversion', driverVersion='VERIFIED-SOURCE-HASH')
    configure(detector)
    assert report(detector)['healthStatus'] == 'Normal'
    trace = (detector.test_path / 'trace').read_text()
    (module / 'srcversion').write_text('DIFFERENT-SOURCE-HASH')
    assert report(detector)['healthStatus'] == 'Unknown'
    assert (detector.test_path / 'trace').read_text() == trace
    profile['driverVersionSource'] = '../srcversion'
    configure(detector)
    assert report(detector)['healthStatus'] == 'Unknown'
    assert (detector.test_path / 'trace').read_text() == trace


@pytest.mark.parametrize('problem', ['missing_config', 'bad_json', 'bad_shape', 'bad_profile', 'missing_library',
                                   'no_symbols', 'no_driver', 'wrong_vendor', 'vf', 'duplicate_serial',
                                   'no_vf_contract'])
def test_installation_and_configuration_errors_are_unknown(detector, problem):
    path = detector.test_path
    if problem == 'missing_config':
        (path / 'config.json').unlink()
    elif problem == 'bad_json':
        (path / 'config.json').write_text('{')
    elif problem == 'bad_shape':
        (path / 'config.json').write_text('{"devices": []}')
    elif problem == 'bad_profile':
        detector.test_config['devices'][ADDRESS] = []
        configure(detector)
    elif problem in ('missing_library', 'no_symbols'):
        library = path / 'absent.so'
        if problem == 'no_symbols':
            library = path / 'empty.so'
            subprocess.run(['gcc', '-shared', '-x', 'c', '-o', str(library), '-'], input=b'int unused;', check=True)
        detector.test_config['libraryPath'] = str(library)
        configure(detector)
    elif problem == 'no_driver':
        (path / 'pci' / ADDRESS / 'driver').unlink()
    elif problem == 'wrong_vendor':
        (path / 'pci' / ADDRESS / 'vendor').write_text('0x10de')
    elif problem == 'vf':
        (path / 'pci' / ADDRESS / 'physfn').symlink_to(path)
    elif problem == 'duplicate_serial':
        detector.test_config['devices'][OTHER] = detector.test_config['devices'][ADDRESS]
        configure(detector)
    elif problem == 'no_vf_contract':
        detector.test_config['devices'][ADDRESS]['supportedVfCounts'] = []
        configure(detector)
    result = report(detector)
    assert result['healthStatus'] == 'Unknown' and result['qualification'] == 'Unverified'


def test_absent_pci_is_fault_but_missing_sysfs_is_unknown(detector, monkeypatch):
    assert detector.health([OTHER])[0]['healthStatus'] == 'Fault'
    monkeypatch.setattr(detector.test_module, 'SYSFS_DEVICES', str(detector.test_path / 'missing'))
    assert report(detector)['healthStatus'] == 'Unknown'


def test_cleanup_failure_does_not_report_normal(detector, monkeypatch):
    failure(monkeypatch, 'close_session', 0x01000003)
    assert report(detector)['healthStatus'] == 'Unknown'
    assert (detector.test_path / 'trace').read_text().endswith('close_session\nclose_device\n')


@pytest.mark.parametrize('field', ['serialNumber', 'firmwareVersion', 'libraryVersion', 'driverVersion',
                                   'compatible', 'pollInterval', 'validityPeriod', 'recoveryInterval',
                                   'supportedVfCounts'])
def test_missing_profile_field_is_reported_without_entering_sdk(detector, field):
    del detector.test_config['devices'][ADDRESS][field]
    configure(detector)
    result = report(detector)
    assert result['healthStatus'] == 'Unknown'
    assert not (detector.test_path / 'trace').exists()


@pytest.mark.parametrize('field', ['libraryPath', 'timeout'])
def test_missing_sdk_config_is_reported_without_entering_sdk(detector, field):
    del detector.test_config[field]
    configure(detector)
    assert report(detector)['healthStatus'] == 'Unknown'
    assert not (detector.test_path / 'trace').exists()


def test_classification_programming_error_is_not_hidden_as_unknown(detector, monkeypatch):
    monkeypatch.setattr(detector, 'classify', Mock(side_effect=KeyError('programming bug')))
    with pytest.raises(KeyError, match='programming bug'):
        report(detector)


def test_interrupted_worker_publication_preserves_last_complete_phase(tmp_path, monkeypatch):
    from zstacklib.utils import sansec_sdk
    path = str(tmp_path / 'result')
    previous = dict(phase='Probing', status='unknown', reason='SDF_HashInit')
    sansec_sdk.write_result(path, previous)

    def interrupted(result, output):
        output.write('{')
        raise OSError('worker interrupted during publication')

    monkeypatch.setattr(sansec_sdk.json, 'dump', interrupted)
    with pytest.raises(OSError):
        sansec_sdk.write_result(path, dict(phase='Closing'))
    assert json.loads(Path(path).read_text()) == previous, 'Timeout classification must read a complete SDK phase'


def test_non_utf8_config_is_a_collection_error_without_entering_sdk(detector):
    (detector.test_path / 'config.json').write_bytes(b'\xff')
    result = report(detector)
    assert result['healthStatus'] == 'Unknown' and 'UTF-8' in result['reason']
    assert not (detector.test_path / 'trace').exists()


def test_worker_result_uses_private_directory_and_cleans_it(detector, monkeypatch):
    spawn = detector.test_module.shell.get_process
    directories = []

    def check_private(args, **kwargs):
        output = Path(args[-1])
        directories.append(output.parent)
        assert stat.S_IMODE(output.parent.stat().st_mode) == 0o700
        assert output.name == 'result'
        return spawn(args, **kwargs)

    monkeypatch.setattr(detector.test_module.shell, 'get_process', check_private)
    assert report(detector)['healthStatus'] == 'Normal'
    assert directories and all(not path.exists() for path in directories)

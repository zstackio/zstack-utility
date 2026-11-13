import importlib
import os
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_sansec_health import ADDRESS, configure, detector, library


def command(operation='Split'):
    return SimpleNamespace(operation=operation, pciDeviceAddress=ADDRESS,
                           pciDeviceAddresses=[ADDRESS], vfCount=2)


@pytest.fixture
def operations(detector, monkeypatch):
    module = importlib.import_module('kvmagent.crypto.sansec_operations')
    monkeypatch.setattr(module, 'sansec_health', detector.test_module)
    root = detector.test_path
    monkeypatch.setattr(module, 'MODULE_CONFIG', str(root / 'modprobe.conf'))
    monkeypatch.setattr(module, 'PROC_ROOT', str(root / 'proc'))
    (root / 'proc').mkdir()
    pf = root / 'pci' / ADDRESS
    (pf / 'sriov_totalvfs').write_text('64')
    (root / 'groups/10').mkdir(parents=True)
    (pf / 'iommu_group').symlink_to(root / 'groups/10')
    detector.test_config['sriov'] = dict(enabled=True, restoreVfnum=-1)
    configure(detector)
    instance = module.SansecOperations(detector)
    configs = [root / 'vendor.conf', root / 'modprobe.conf', root / 'override.conf']
    instance.query = lambda arguments: '\n'.join(p.read_text() for p in configs if p.exists())
    instance.test_module, instance.test_root, instance.calls = module, root, []

    def run(arguments):
        instance.calls.append(arguments)
        if arguments[0] != 'modprobe':
            return ''
        if arguments[1] == '-r':
            assert (root / 'modprobe.conf').read_text().startswith('options swcsm VFnum='), \
                'The desired VFnum must be durable before the driver is unloaded'
            (pf / 'driver').unlink()
            for vf in pf.glob('virtfn*'):
                vf.unlink()
        else:
            (pf / 'driver').symlink_to(root / 'drivers/swcsm')
            effective = instance.effective_vfnum()
            count = int(arguments[2].split('=')[1]) if len(arguments) > 2 else -1 if effective is None else effective
            for index in range(max(0, count)):
                (pf / ('virtfn%s' % index)).symlink_to(root / 'pci' / ('0000:b3:01.%s' % index))
        return ''

    monkeypatch.setattr(instance, 'run', run)
    return instance


def test_split_verifies_topology_persists_vfnum_and_does_not_repeat_driver_calls(operations):
    result = operations.submit(command())
    assert result['status'] == 'Succeeded' and result['vfCounts'] == {ADDRESS: 2}
    assert (operations.test_root / 'modprobe.conf').read_text() == 'options swcsm VFnum=2\n'
    calls = list(operations.calls)
    restarted = operations.test_module.SansecOperations(operations.detector)
    restarted.run, restarted.query = operations.run, operations.query
    assert restarted.submit(command())['status'] == 'Succeeded', 'A retry after agent restart must be idempotent'
    assert operations.calls == calls, 'An applied topology must not reload the driver again'


def test_unsplit_uses_minus_one_and_verifies_zero_vfs(operations):
    pf = operations.test_root / 'pci' / ADDRESS
    (pf / 'virtfn0').symlink_to(pf)
    result = operations.submit(command('Unsplit'))
    assert result['status'] == 'Succeeded' and result['vfCounts'] == {ADDRESS: 0}
    assert operations.calls[-1] == ['modprobe', 'swcsm']
    assert (operations.test_root / 'modprobe.conf').read_text() == 'options swcsm VFnum=-1\n'


def test_split_uses_the_same_explicit_srcversion_identity_as_health(operations):
    module = operations.test_root / 'drivers/swcsm/module'
    (module / 'version').unlink()
    (module / 'srcversion').write_text('VERIFIED-SOURCE-HASH')
    operations.detector.test_config['devices'][ADDRESS].update(
        driverVersionSource='srcversion', driverVersion='VERIFIED-SOURCE-HASH')
    configure(operations.detector)
    assert operations.submit(command())['status'] == 'Succeeded'


@pytest.mark.parametrize('change', ['count', 'profile', 'driver', 'scope', 'health_worker'])
def test_failed_preconditions_never_reload_driver(operations, change):
    cmd = command()
    detector = operations.detector
    if change == 'count':
        cmd.vfCount = 3
    elif change == 'profile':
        detector.test_config['sriov']['enabled'] = False
        configure(detector)
    elif change == 'driver':
        (operations.test_root / 'drivers/swcsm/module/version').write_text('other-version')
    elif change == 'scope':
        cmd.pciDeviceAddresses.append('0000:b4:00.0')
    else:
        detector.pending = (Mock(poll=lambda: None), 'unused')
    result = operations.submit(cmd)
    assert result['status'] == 'Failed' and result['reason']
    assert not any(call[0] == 'modprobe' for call in operations.calls)


def test_module_wide_change_cannot_silently_resplit_another_pf(operations):
    second = operations.test_root / 'pci/0000:b4:00.0'
    second.mkdir()
    for name, value in [('vendor', '0x1ed4'), ('device', '0x7011'), ('sriov_totalvfs', '64')]:
        (second / name).write_text(value)
    cmd = command()
    cmd.pciDeviceAddresses.append(second.name)
    result = operations.submit(cmd)
    assert result['status'] == 'Failed' and 'another PF' in result['reason']
    assert not operations.calls


def test_active_vfio_group_blocks_module_reload(operations):
    fd = operations.test_root / 'proc/123/fd'
    fd.mkdir(parents=True)
    (fd / '5').symlink_to('/dev/vfio/10')
    result = operations.submit(command())
    assert result['status'] == 'Failed' and 'active VFIO' in result['reason']
    assert not operations.calls


def test_active_libvirt_hostdev_blocks_reload_even_without_vfio_fd(operations, monkeypatch):
    outputs = ['a-vm', '<domain><devices><hostdev type="pci"><source><address domain="0x0000" bus="0xb3" '
               'slot="0x00" function="0x0"/></source></hostdev></devices></domain>']
    run = Mock(side_effect=outputs)
    monkeypatch.setattr(operations, 'run', run)
    result = operations.submit(command())
    assert result['status'] == 'Failed' and 'active VM' in result['reason']
    assert run.call_count == 2


@pytest.mark.parametrize('device_type', ['usb', 'scsi'])
def test_unrelated_non_pci_passthrough_does_not_block_sansec_operation(operations, monkeypatch, device_type):
    original = operations.run

    def run(arguments):
        if arguments == ['virsh', 'list', '--uuid']:
            return 'other-vm'
        if arguments == ['virsh', 'dumpxml', 'other-vm']:
            return ('<domain><devices><hostdev type="%s"><source><address bus="1" device="2"/>'
                    '</source></hostdev></devices></domain>') % device_type
        return original(arguments)

    monkeypatch.setattr(operations, 'run', run)
    assert operations.submit(command())['status'] == 'Succeeded'


def test_proc_permission_error_fails_closed(operations, monkeypatch):
    original = operations.test_module.os.listdir
    (operations.test_root / 'proc/123/fd').mkdir(parents=True)

    def unreadable(path):
        if str(path).endswith('/123/fd'):
            raise PermissionError('Cannot inspect process file descriptors')
        return original(path)

    monkeypatch.setattr(operations.test_module.os, 'listdir', unreadable)
    assert operations.submit(command())['status'] == 'Failed'
    assert not operations.calls


def test_interrupted_driver_change_converges_to_the_persisted_target(operations, monkeypatch):
    pf = operations.test_root / 'pci' / ADDRESS
    original = operations.run

    def interrupted(arguments):
        result = original(arguments)
        if arguments == ['modprobe', '-r', 'swcsm']:
            raise operations.test_module.CommandError('interrupted after unload')
        return result

    monkeypatch.setattr(operations, 'run', interrupted)
    assert operations.submit(command())['status'] == 'Unknown'
    assert not (pf / 'driver').exists(), 'The interruption leaves the driver unloaded'
    restarted = operations.test_module.SansecOperations(operations.detector)
    restarted.run, restarted.query = original, operations.query
    restarted.converge()
    assert operations.calls[-1] == ['modprobe', 'swcsm'], 'Convergence loads the effective persisted target'
    assert len(list(pf.glob('virtfn*'))) == 2
    calls = list(operations.calls)
    assert restarted.submit(command())['status'] == 'Succeeded', 'The same request is already satisfied'
    assert operations.calls == calls, 'A satisfied request must not reload the driver'


def test_retry_after_interruption_converges_without_a_separate_recovery(operations, monkeypatch):
    original = operations.run

    def interrupted(arguments):
        result = original(arguments)
        if arguments == ['modprobe', '-r', 'swcsm']:
            raise operations.test_module.CommandError('interrupted after unload')
        return result

    monkeypatch.setattr(operations, 'run', interrupted)
    assert operations.submit(command())['status'] == 'Unknown'
    monkeypatch.setattr(operations, 'run', original)
    assert operations.submit(command())['status'] == 'Succeeded'
    assert len(list((operations.test_root / 'pci' / ADDRESS).glob('virtfn*'))) == 2


def test_convergence_only_follows_the_zstack_module_configuration(operations):
    (operations.test_root / 'pci' / ADDRESS / 'driver').unlink()
    operations.converge()
    assert not operations.calls, 'Without the ZStack VFnum file there is no desired driver state to restore'
    (operations.test_root / 'modprobe.conf').write_text('options swcsm VFnum=2\n')
    operations.converge()
    assert operations.calls == [['modprobe', 'swcsm']], 'The ZStack VFnum file declares the driver must be loaded'


def test_earlier_vendor_vfnum_does_not_take_effect(operations):
    (operations.test_root / 'vendor.conf').write_text('options swcsm VFnum=4\n')
    assert operations.submit(command())['status'] == 'Succeeded'
    assert len(list((operations.test_root / 'pci' / ADDRESS).glob('virtfn*'))) == 2


def test_later_vfnum_override_fails_before_unloading(operations):
    (operations.test_root / 'override.conf').write_text('options swcsm VFnum=4\n')
    result = operations.submit(command())
    assert result['status'] == 'Failed' and 'overrides' in result['reason']
    assert not any(call[0] == 'modprobe' for call in operations.calls), \
        'A VFnum that cannot take effect must not unload the driver'


def test_retry_is_not_success_when_current_topology_or_persistence_disagrees(operations):
    assert operations.submit(command())['status'] == 'Succeeded'
    calls = list(operations.calls)
    config = operations.test_root / 'modprobe.conf'
    config.write_text('options swcsm VFnum=-1\n')
    assert operations.submit(command())['status'] == 'Failed'
    config.write_text('options swcsm VFnum=2\n')
    (operations.test_root / 'pci' / ADDRESS / 'virtfn0').unlink()
    assert operations.submit(command())['status'] == 'Failed'
    assert operations.calls == calls



def test_timed_out_unreaped_command_blocks_following_operations(operations, monkeypatch):
    process = Mock()
    process.communicate.side_effect = subprocess.TimeoutExpired('modprobe', 30)
    process.poll.return_value = None
    monkeypatch.setattr(operations.test_module.shell, 'get_process', Mock(return_value=process))
    with pytest.raises(RuntimeError, match='timed out'):
        operations.test_module.SansecOperations.run(operations, ['modprobe', '-r', 'swcsm'])
    process.kill.assert_called_once()
    assert operations.submit(command())['status'] == 'Failed'
    assert not operations.calls


@pytest.mark.parametrize('attribute', ['vendor', 'device'])
def test_unrelated_device_removal_during_verification_does_not_strand_completed_operation(
        operations, monkeypatch, attribute):
    other = operations.test_root / 'pci/0000:b4:00.0'
    other.mkdir()
    (other / 'vendor').write_text('0x1234')
    (other / 'device').write_text('0x5678')
    original = operations.read

    def read(path):
        if path == str(other / attribute) and len([c for c in operations.calls if c[0] == 'modprobe']) == 2:
            shutil.rmtree(other)
        return original(path)

    monkeypatch.setattr(operations, 'read', read)
    result = operations.submit(command())
    assert result['status'] == 'Succeeded', 'Unrelated hot removal must not leave a completed split Unknown'
    assert operations.submit(command())['status'] == 'Succeeded'


def test_missing_attribute_on_present_device_still_blocks_driver_change(operations):
    (operations.test_root / 'pci' / ADDRESS / 'vendor').unlink()
    result = operations.submit(command())
    assert result['status'] == 'Failed', 'An unreadable present device must not be treated as absent'
    assert not operations.calls


def test_programming_error_in_preparation_is_not_persisted_as_hardware_failure(operations, monkeypatch):
    monkeypatch.setattr(operations, 'prepare', Mock(side_effect=KeyError('programming bug')))
    with pytest.raises(KeyError, match='programming bug'):
        operations.submit(command())
    assert not operations.calls


@pytest.mark.parametrize('address', ['domain="0x0000" bus="broken" slot="0x00" function="0x0"',
                                    'domain="0x0000" bus="0xb3" slot="0x00"'])
def test_unreadable_active_pci_address_fails_before_driver_change(operations, monkeypatch, address):
    xml = '<domain><devices><hostdev type="pci"><source><address %s/></source></hostdev></devices></domain>' % address
    run = Mock(side_effect=['vm', xml])
    monkeypatch.setattr(operations, 'run', run)
    result = operations.submit(command())
    assert result['status'] == 'Failed'
    assert [call.args[0][0] for call in run.call_args_list] == ['virsh', 'virsh']

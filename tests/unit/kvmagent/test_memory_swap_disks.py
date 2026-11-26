import json

import pytest

from kvmagent.plugins import memory_swap_disks as swap

HOST = 'a4157f3ca1214b3183b65f4a9fecfcf3'
DEV = '/dev/nvme0n1'
BY_ID = '/dev/disk/by-id/nvme-INTEL_SSDPE2KX020T8_PHLJ0001'
SIG = '2f1d7c1e-6a1e-4c55-9d1a-1b5d2a7e9c01'


def candidate(device=DEV, by_id=BY_ID, serial='PHLJ0001', reasons=None, state=None, capacity=2 << 40):
    reasons = list(reasons or [])
    return {'identity': 'candidate:' + device, 'type': 'block', 'path': by_id or device, 'device': device,
            'byIdPath': by_id, 'capacityBytes': capacity, 'transport': 'nvme',
            'state': state or ('INELIGIBLE' if reasons else 'NEEDS_OFFLINE_PREPARATION'),
            'reasons': reasons or ['NEEDS_OFFLINE_PREPARATION'],
            'stableIdentity': {'serial': serial, 'wwn': 'eui.0001', 'byIdPath': by_id}}


class Host(object):
    """A host with one swap table, one fstab, block signatures and memory, driven by the commands run."""

    def __init__(self, candidates=None, swaps=None, signatures=None, mem_available_kib=64 << 20):
        self.candidates = candidates if candidates is not None else [candidate()]
        self.swaps = dict(swaps or {})  # device -> used KiB
        self.signatures = dict(signatures or {})  # device -> swap UUID ('' for another signature)
        self.files = {'/etc/fstab': 'UUID=root / xfs defaults 0 0\n'}
        self.queue = '/sys/block/nvme0n1/queue/'
        self.files.update({'/proc/sys/vm/min_free_kbytes': '65536', '/proc/sys/vm/watermark_scale_factor': '10',
                           self.queue + 'scheduler': '[none] mq-deadline', self.queue + 'nr_requests': '128'})
        self.mem_total_kib = 268435456
        self.mem_available_kib = mem_available_kib
        self.links = {BY_ID: DEV}
        self.zram_backing = {}  # zram device name -> backing_dev
        self.commands = []
        self.fail = {}

    def probe(self, host_uuid):
        assert host_uuid == HOST
        return {'status': 'AVAILABLE', 'reasons': [], 'candidates': [dict(c) for c in self.candidates]}

    def listdir(self, path):
        assert path == '/sys/block'
        return sorted(['nvme0n1', 'sda'] + list(self.zram_backing))

    def read(self, path):
        if path.startswith('/sys/block/zram') and path.endswith('/backing_dev'):
            return self.zram_backing[path.split('/')[3]] + '\n'
        if path.startswith('/sys/block/') and path.endswith('/backing_dev'):
            raise IOError(2, 'missing')
        if path == '/proc/swaps':
            rows = ['Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority']
            rows += ['%s partition 1000 %d -2' % (d, used) for d, used in sorted(self.swaps.items())]
            return '\n'.join(rows) + '\n'
        if path == '/proc/meminfo':
            return 'MemTotal: %d kB\nMemAvailable: %d kB\n' % (self.mem_total_kib, self.mem_available_kib)
        if path not in self.files:
            raise IOError(2, 'missing')
        return self.files[path]

    def write(self, path, text):
        self.files[path] = text

    def write_kernel(self, path, value):
        assert path in self.files
        if path.endswith('/scheduler'):
            self.files[path] = '[none] mq-deadline' if value == 'none' else 'none [mq-deadline]'
            self.files[self.queue + 'nr_requests'] = '256'
        else:
            self.files[path] = value

    def remove(self, path):
        self.files.pop(path, None)

    def realpath(self, path):
        if path.startswith('/dev/disk/by-id/') and path not in self.links:
            raise OSError(2, 'missing')
        return self.links.get(path, path)

    def run(self, argv, timeout=5):
        self.commands.append(list(argv))
        name = argv[0]
        if name in self.fail:
            return {'returncode': 1, 'stdout': '', 'stderr': self.fail[name]}
        device = self.links.get(argv[-1], argv[-1])
        if name == 'blkid':
            value = self.signatures.get(device)
            return {'returncode': 0 if value else 2, 'stdout': (value + '\n') if value else '', 'stderr': ''}
        if name == 'wipefs':
            self.signatures.pop(device, None)
        elif name == 'mkswap':
            self.signatures[device] = SIG
        elif name == 'swapon':
            self.swaps[device] = 0
        elif name == 'swapoff':
            self.swaps.pop(device, None)
        return {'returncode': 0, 'stdout': '', 'stderr': ''}


def disks(host, writeback_device=None):
    return swap.SwapDisks(HOST, '/var/lib/zstack/memory-optimization/operations/swap-disk',
                          runner=host.run, filesystem=host, probe=host.probe, writeback_device=writeback_device)


def ran(host, name):
    return [c for c in host.commands if c[0] == name]


def test_a_blank_local_nvme_disk_is_a_candidate_and_nothing_is_configured():
    inventory = disks(Host()).inventory()
    assert inventory['status'] == 'NOT_CONFIGURED' and inventory['canPrepare'] is True
    assert [(c['device'], c['state'], c['serial']) for c in inventory['candidates']] == [(DEV, 'AVAILABLE', 'PHLJ0001')]


@pytest.mark.parametrize('device,reasons,state', [
    ('/dev/sdb', [], 'INELIGIBLE'),
    (DEV, ['SYSTEM_OR_MOUNTED_DEVICE'], 'INELIGIBLE'),
    (DEV, ['EXISTING_FILESYSTEM_OR_PARTITION_SIGNATURE'], 'NEEDS_OVERWRITE_CONFIRMATION'),
    (DEV, ['EXISTING_FILESYSTEM_OR_PARTITION_SIGNATURE', 'SERIAL_IDENTITY_MISSING'], 'INELIGIBLE'),
])
def test_only_a_local_nvme_disk_without_other_risks_can_become_the_swap_disk(device, reasons, state):
    item = disks(Host([candidate(device=device, reasons=reasons)])).inventory()['candidates'][0]
    assert item['state'] == state
    if device == '/dev/sdb':
        assert 'NOT_LOCAL_NVME_DEVICE' in item['reasons']


def test_a_partition_of_a_local_nvme_disk_is_a_candidate():
    item = disks(Host([candidate(device='/dev/nvme0n1p3')])).inventory()['candidates'][0]
    assert item['state'] == 'AVAILABLE'


def test_preparing_formats_and_enables_disk_but_defers_boot_activation_to_agent():
    host = Host()
    result = disks(host).prepare('candidate:' + DEV, overwrite=False)
    assert result['status'] == 'ACTIVE' and result['swapDisk']['uuid'] == SIG
    assert ran(host, 'mkswap') == [['mkswap', '-L', swap.SWAP_LABEL, BY_ID]]
    assert ran(host, 'swapon') == [['swapon', '--discard', BY_ID]]
    assert 'UUID=%s none swap noauto,discard,nofail 0 0 %s' % (SIG, swap.FSTAB_MARK) in host.files['/etc/fstab']
    assert host.files['/etc/fstab'].startswith('UUID=root / xfs defaults 0 0\n')
    record = json.loads(host.files['/var/lib/zstack/memory-optimization/operations/swap-disk'])
    assert record['stage'] == 'ACTIVE' and record['serial'] == 'PHLJ0001' and record['byIdPath'] == BY_ID
    assert not ran(host, 'wipefs')


def test_a_disk_with_data_is_overwritten_only_when_confirmed():
    host = Host([candidate(reasons=['EXISTING_FILESYSTEM_OR_PARTITION_SIGNATURE'])], signatures={DEV: ''})
    with pytest.raises(swap.Rejected) as error:
        disks(host).prepare('candidate:' + DEV, overwrite=False)
    assert error.value.reason == 'OVERWRITE_CONFIRMATION_REQUIRED' and not ran(host, 'mkswap')
    disks(host).prepare('candidate:' + DEV, overwrite=True)
    assert ran(host, 'wipefs') == [['wipefs', '-a', BY_ID]] and ran(host, 'mkswap')


@pytest.mark.parametrize('setup,reason', [
    (lambda h: h.swaps.update({'/dev/zram0': 0}), 'OTHER_SWAP_ACTIVE'),
    (lambda h: setattr(h, 'candidates', [candidate(reasons=['SYSTEM_OR_MOUNTED_DEVICE'])]), 'SWAP_DISK_CANDIDATE_NOT_ELIGIBLE'),
    (lambda h: setattr(h, 'candidates', []), 'SWAP_DISK_CANDIDATE_NOT_FOUND'),
])
def test_preparation_is_refused_before_touching_the_disk(setup, reason):
    host = Host()
    setup(host)
    with pytest.raises(swap.Rejected) as error:
        disks(host).prepare('candidate:' + DEV, overwrite=True)
    assert error.value.reason == reason
    assert not [c for c in host.commands if c[0] in ('wipefs', 'mkswap', 'swapon')]


def test_a_second_disk_is_refused_while_one_is_configured():
    host = Host()
    disks(host).prepare('candidate:' + DEV, overwrite=False)
    host.swaps.clear()
    with pytest.raises(swap.Rejected) as error:
        disks(host).prepare('candidate:' + DEV, overwrite=False)
    assert error.value.reason == 'SWAP_DISK_ALREADY_CONFIGURED'


def active_host():
    host = Host()
    disks(host).prepare('candidate:' + DEV, overwrite=False)
    host.candidates = [candidate(reasons=['SYSTEM_OR_MOUNTED_DEVICE'])]
    host.commands = []
    return host


def test_the_configured_disk_is_reported_active_while_its_signature_is_enabled():
    inventory = disks(active_host()).inventory()
    assert inventory['status'] == 'ACTIVE' and inventory['canPrepare'] is False
    assert inventory['swapDisk']['device'] == DEV and inventory['swapDisk']['reasons'] == []
    assert inventory['candidates'][0]['state'] == 'ACTIVE'


@pytest.mark.parametrize('change,reason', [
    (lambda h: h.swaps.clear(), 'SWAP_DISK_NOT_ENABLED'),
    (lambda h: h.signatures.update({DEV: 'another-uuid'}), 'SWAP_DISK_SIGNATURE_MISMATCH'),
    (lambda h: h.links.clear(), 'SWAP_DISK_NOT_FOUND'),
    (lambda h: h.links.update({BY_ID: '/dev/nvme1n1'}), 'SWAP_DISK_SIGNATURE_MISMATCH'),
])
def test_a_missing_replaced_or_not_enabled_disk_is_a_fault_and_is_never_reformatted(change, reason):
    host = active_host()
    change(host)
    inventory = disks(host).inventory()
    assert inventory['status'] == 'FAULT' and reason in inventory['swapDisk']['reasons']
    assert not [c for c in host.commands if c[0] in ('wipefs', 'mkswap', 'swapon')]


def test_disabling_reads_the_data_back_then_removes_the_boot_entry_and_the_signature():
    host = active_host()
    host.swaps[DEV] = 8 << 20
    result = disks(host).disable()
    assert result['status'] == 'NOT_CONFIGURED'
    assert ran(host, 'swapoff') == [['swapoff', BY_ID]] and ran(host, 'wipefs') == [['wipefs', '-a', '-t', 'swap', BY_ID]]
    assert host.files['/etc/fstab'] == 'UUID=root / xfs defaults 0 0\n'
    assert '/var/lib/zstack/memory-optimization/operations/swap-disk' not in host.files


def test_disabling_is_refused_when_memory_cannot_take_the_swapped_data_back():
    host = active_host()
    host.swaps[DEV] = 40 << 20
    host.mem_available_kib = 30 << 20
    with pytest.raises(swap.Rejected) as error:
        disks(host).disable()
    assert error.value.reason == 'INSUFFICIENT_MEMORY_FOR_SWAPOFF' and not ran(host, 'swapoff')
    assert error.value.details == {'swappedBytes': 40 << 30, 'availableBytes': 30 << 30,
                                   'requiredBytes': (40 << 30) + swap.SWAPOFF_MARGIN_BYTES}


def test_a_replacement_with_the_same_uuid_after_swapoff_keeps_its_signature():
    host = active_host()
    manager = disks(host)
    def replace_after_swapoff(argv, timeout):
        result = host.run(argv, timeout)
        if argv[0] == 'swapoff':
            host.candidates[0]['stableIdentity']['serial'] = 'REPLACEMENT'
        return result
    manager.run = replace_after_swapoff
    with pytest.raises(swap.Rejected) as error:
        manager.disable()
    assert error.value.reason == 'SWAP_DISK_IDENTITY_MISMATCH'
    assert not ran(host, 'wipefs') and manager.record_path in host.files


def test_disabling_does_not_wipe_a_disk_that_no_longer_carries_our_signature():
    host = active_host()
    host.swaps.clear()
    host.signatures[DEV] = 'someone-else'
    disks(host).disable()
    assert not ran(host, 'wipefs') and '/var/lib/zstack/memory-optimization/operations/swap-disk' not in host.files


@pytest.mark.parametrize('state,reason', [
    ('other_active', 'SWAP_DISK_SIGNATURE_MISMATCH'),
    ('duplicate_serial', 'SWAP_DISK_IDENTITY_MISMATCH'),
    ('unrecorded', 'SWAP_DISK_PREPARATION_INCOMPLETE'),
    ('missing', 'SWAP_DISK_NOT_FOUND'),
])
def test_disable_preserves_swap_and_configuration_when_ownership_is_uncertain(state, reason):
    host = active_host()
    manager = disks(host)
    if state == 'other_active':
        host.signatures[DEV] = 'other-swap'
    elif state == 'duplicate_serial':
        host.candidates[0]['reasons'].append('SERIAL_IDENTITY_NOT_UNIQUE')
    elif state == 'unrecorded':
        record = json.loads(host.files[manager.record_path])
        record.update(stage='PREPARING', uuid=None)
        host.files[manager.record_path] = json.dumps(record)
    else:
        host.links.clear()
    before = dict(host.files)
    with pytest.raises(swap.Rejected) as error:
        manager.disable()
    assert error.value.reason == reason
    assert host.files == before and DEV in host.swaps
    assert not ran(host, 'swapoff') and not ran(host, 'wipefs')


def test_an_interrupted_preparation_is_a_fault_that_disable_cleans_up():
    host = Host()
    host.fail['swapon'] = 'swapon failed'
    with pytest.raises(swap.Rejected):
        disks(host).prepare('candidate:' + DEV, overwrite=False)
    inventory = disks(host).inventory()
    assert inventory['status'] == 'FAULT' and 'SWAP_DISK_PREPARATION_INCOMPLETE' in inventory['swapDisk']['reasons']
    host.fail.clear()
    assert disks(host).disable()['status'] == 'NOT_CONFIGURED'
    assert swap.FSTAB_MARK not in host.files['/etc/fstab'] and DEV not in host.signatures


def test_disabling_without_a_swap_disk_succeeds_without_commands():
    host = Host()
    assert disks(host).disable()['status'] == 'NOT_CONFIGURED' and host.commands == []


@pytest.mark.parametrize('device,backing', [(DEV, DEV), ('/dev/nvme0n1p1', DEV), (DEV, '/dev/nvme0n1p2'), (DEV, 'none')])
def test_a_disk_zram_writes_back_to_is_never_a_swap_disk_candidate(device, backing):
    host = Host([candidate(device=device)])
    host.zram_backing = {'zram0': backing}
    item = disks(host).inventory()['candidates'][0]
    if backing == 'none':
        assert item['state'] == 'AVAILABLE'
    else:
        assert item['state'] == 'INELIGIBLE' and 'ZRAM_WRITEBACK_BACKEND' in item['reasons']


def test_the_configured_writeback_disk_stays_reserved_while_zram_is_drained():
    host = Host()
    item = disks(host, writeback_device=DEV).inventory()['candidates'][0]
    assert item['state'] == 'INELIGIBLE' and item['reasons'] == ['WRITEBACK_BACKEND_CONFIGURED']
    with pytest.raises(swap.Rejected) as error:
        disks(host, writeback_device=DEV).prepare('candidate:' + DEV, overwrite=True)
    assert error.value.reason == 'SWAP_DISK_CANDIDATE_NOT_ELIGIBLE' and not ran(host, 'mkswap')

def test_managed_disk_and_foreign_swap_cannot_report_exclusive_activation():
    host = active_host()
    host.swaps['/dev/zram0'] = 0
    state = disks(host).inventory()
    assert state['status'] == 'FAULT' and state['otherSwaps'] == ['/dev/zram0']
    assert state['swapDisk']['reasons'] == ['OTHER_SWAP_ACTIVE']


def test_agent_restores_original_disk_after_rename_and_is_idempotent():
    host = active_host()
    moved = '/dev/nvme3n1'
    host.candidates = [candidate(device=moved, reasons=[swap.SIGNATURE_REASON])]
    host.links[BY_ID] = moved
    host.swaps.clear()
    host.signatures = {moved: SIG}
    host.files['/etc/fstab'] = host.files['/etc/fstab'].replace('noauto,', '')
    disks(host).restore()
    disks(host).restore()
    assert ran(host, 'swapon') == [['swapon', '--discard', BY_ID]]
    assert 'noauto,discard,nofail' in host.files['/etc/fstab']
    assert not ran(host, 'mkswap') and not ran(host, 'wipefs')


@pytest.mark.parametrize('failure,reason', [
    ('cloned_uuid', 'SWAP_DISK_IDENTITY_MISMATCH'),
    ('new_uuid', 'SWAP_DISK_SIGNATURE_MISMATCH'),
    ('missing', 'SWAP_DISK_NOT_FOUND'),
    ('foreign_swap', 'OTHER_SWAP_ACTIVE'),
    ('mounted', 'SWAP_DISK_CANDIDATE_NOT_ELIGIBLE'),
])
def test_agent_refuses_an_unproven_swap_disk_on_boot(failure, reason):
    host = active_host()
    host.swaps.clear()
    host.candidates = [candidate(reasons=[swap.SIGNATURE_REASON])]
    if failure == 'cloned_uuid':
        host.candidates[0]['stableIdentity']['serial'] = 'OTHER-DISK'
    elif failure == 'new_uuid':
        host.signatures[DEV] = 'another-signature'
    elif failure == 'missing':
        host.links.clear()
    elif failure == 'foreign_swap':
        host.swaps['/dev/zram0'] = 0
    else:
        host.candidates[0]['reasons'].append('SYSTEM_OR_MOUNTED_DEVICE')
    with pytest.raises(swap.Rejected) as error:
        disks(host).restore()
    assert error.value.reason == reason
    assert not ran(host, 'swapon') and not ran(host, 'mkswap') and not ran(host, 'wipefs')

@pytest.mark.parametrize('memory_kib,minimum', [(32 << 20, '65536'), (65337320, '1048576'),
                                                (128 << 20, '2097152'), (256 << 20, '3145728')])
def test_swap_tuning_survives_reconnect_and_restores_original_values(memory_kib, minimum):
    host = Host()
    host.mem_total_kib = memory_kib
    manager = disks(host)
    original = dict(host.files)
    manager.prepare('candidate:' + DEV, False)
    assert host.files['/proc/sys/vm/min_free_kbytes'] == minimum
    assert host.files['/proc/sys/vm/watermark_scale_factor'] == '200'
    assert host.files[host.queue + 'scheduler'] == 'none [mq-deadline]'
    assert host.files[host.queue + 'nr_requests'] == '64'
    host.files.update(original)
    assert disks(host).restore()
    assert host.files[host.queue + 'nr_requests'] == '64'
    assert host.files['/proc/sys/vm/min_free_kbytes'] == minimum
    manager.disable()
    assert host.files == original


def test_tuning_restores_only_the_host_after_an_inactive_disk_signature_changes():
    host = active_host()
    host.swaps.clear()
    host.signatures[DEV] = 'new-owner'
    host.files[host.queue + 'nr_requests'] = '72'
    disks(host).disable()
    assert host.files['/proc/sys/vm/watermark_scale_factor'] == '10'
    assert host.files[host.queue + 'nr_requests'] == '72'


def test_failed_tuning_restore_can_be_retried_before_erasing_the_signature():
    host = active_host()
    manager = disks(host)
    del host.files[host.queue + 'nr_requests']
    # Keep scheduler at its original setting so changing it cannot recreate the missing attribute.
    host.files[host.queue + 'scheduler'] = '[none] mq-deadline'
    with pytest.raises(swap.Rejected):
        manager.disable()
    assert host.signatures[DEV] == SIG and manager.record_path in host.files
    host.files[host.queue + 'nr_requests'] = '64'
    manager.disable()
    assert host.files[host.queue + 'nr_requests'] == '128'

def test_managed_partition_tunes_its_parent_queue_and_keeps_higher_watermark():
    host = Host([candidate(device=DEV + 'p1')])
    host.links[BY_ID] = DEV + 'p1'
    host.files['/proc/sys/vm/watermark_scale_factor'] = '350'
    host.files[host.queue + 'nr_requests'] = '96'
    manager = disks(host)
    manager.prepare('candidate:' + DEV + 'p1', False)
    assert host.files[host.queue + 'nr_requests'] == '64'
    assert host.files['/proc/sys/vm/watermark_scale_factor'] == '350'
    host.files['/proc/sys/vm/watermark_scale_factor'] = '450'
    manager.disable()
    assert host.files['/proc/sys/vm/watermark_scale_factor'] == '350'
    assert host.files[host.queue + 'nr_requests'] == '96'


def test_older_managed_disk_restores_swap_without_adopting_host_tuning():
    host = active_host()
    manager = disks(host)
    record = json.loads(host.files[manager.record_path])
    del record['originalTuning']
    host.files[manager.record_path] = json.dumps(record)
    host.files['/proc/sys/vm/watermark_scale_factor'] = '23'
    host.files[host.queue + 'nr_requests'] = '96'
    host.swaps.clear()
    host.candidates = [candidate(reasons=[swap.SIGNATURE_REASON])]
    assert manager.restore() and DEV in host.swaps
    assert manager.restore()
    manager.disable()
    assert host.files[host.queue + 'nr_requests'] == '96'
    assert host.files['/proc/sys/vm/watermark_scale_factor'] == '23'


def test_unreadable_queue_depth_leaves_scheduler_unchanged():
    host = Host()
    del host.files[host.queue + 'nr_requests']
    disks(host).prepare('candidate:' + DEV, False)
    assert DEV in host.swaps and host.files[host.queue + 'scheduler'] == '[none] mq-deadline'
    assert host.files['/proc/sys/vm/watermark_scale_factor'] == '200'

import calendar
import json
import os
import stat
import time
import unittest

from kvmagent.plugins.memory_writeback_backends import _command
from kvmagent.plugins.memory_writeback_backends import probe_writeback_backends


NOW = calendar.timegm(time.strptime('2026-10-08T00:00:00Z', '%Y-%m-%dT%H:%M:%SZ'))
BOOT = 'test-boot-id'
SERIAL = 'dedicated-disk-serial-001'
DEVICE = '/dev/vdb'
BY_ID = '/dev/disk/by-id/virtio-' + SERIAL
SYSFS = '/sys/devices/pci0000:00/virtio3/block/vdb'
MAJOR_MINOR = '252:16'
CAPACITY = 20 * 1024 * 1024 * 1024


class FakeStat(object):
    def __init__(self, mode, ino=200, dev=9, rdev=None, size=0, nlink=1):
        self.st_mode = mode
        self.st_ino = ino
        self.st_dev = dev
        self.st_rdev = rdev if rdev is not None else 0
        self.st_size = size
        self.st_nlink = nlink


class FakeFilesystem(object):
    def __init__(self, boot_id=BOOT, rows=None, sysfs_path=SYSFS):
        self.sysfs_path = sysfs_path
        self.files = {
            '/proc/sys/kernel/random/boot_id': boot_id + '\n',
            '/proc/self/mountinfo': (
                '1 0 8:1 / / rw,relatime - ext4 /dev/root rw\n'),
            '/proc/swaps': 'Filename Type Size Used Priority\n',
        }
        self.links = {BY_ID: DEVICE, DEVICE: DEVICE,
                      '/dev/vdb1': '/dev/vdb1', '/dev/loop0': '/dev/loop0'}
        self.directories = {
            '/dev/disk/by-id': [os.path.basename(BY_ID)],
            self.sysfs_path + '/holders': [], self.sysfs_path + '/slaves': [],
        }
        self.stats = {
            DEVICE: FakeStat(stat.S_IFBLK | 0o600, ino=101, rdev=os.makedev(252, 16),
                             size=CAPACITY),
            self.sysfs_path: FakeStat(stat.S_IFDIR | 0o755, ino=303),
            '/dev/loop0': FakeStat(stat.S_IFBLK | 0o600, ino=404,
                                   rdev=os.makedev(7, 0), size=CAPACITY),
            '/var/lib/zram/writeback.img': FakeStat(
                stat.S_IFREG | 0o600, ino=500, dev=8, size=CAPACITY, nlink=1),
        }
        self.rows = rows if rows is not None else [{
            'name': DEVICE, 'kname': 'vdb', 'type': 'disk', 'size': CAPACITY,
            'maj:min': MAJOR_MINOR, 'tran': 'virtio', 'serial': SERIAL,
            'wwn': None, 'ro': False, 'rm': False,
        }]

    def read(self, path):
        if path not in self.files:
            raise IOError(path)
        return self.files[path]

    def exists(self, path):
        return path in self.stats or path in self.files or path in self.directories

    def listdir(self, path):
        if path not in self.directories:
            raise IOError(path)
        return list(self.directories[path])

    def realpath(self, path):
        if path in self.links:
            return self.links[path]
        if path.startswith('/sys/dev/block/'):
            major_minor = path.rsplit('/', 1)[-1]
            return self.sysfs_path if major_minor == MAJOR_MINOR else '/sys/devices/unknown'
        if path in self.stats:
            return path
        raise IOError(path)

    def stat(self, path):
        if path in self.stats:
            return self.stats[path]
        raise IOError(path)

    def lstat(self, path):
        return self.stat(path)


class ProbeRunner(object):
    def __init__(self, filesystem, signature='none', lsblk_rc=0):
        self.filesystem = filesystem
        self.signature = signature
        self.lsblk_rc = lsblk_rc
        self.calls = []

    def __call__(self, argv, timeout=5):
        self.calls.append((list(argv), timeout))
        if argv[0] == 'lsblk':
            if self.lsblk_rc:
                return {'returncode': self.lsblk_rc, 'stdout': '', 'stderr': 'lsblk failed'}
            return {'returncode': 0,
                    'stdout': json.dumps({'blockdevices': self.filesystem.rows}),
                    'stderr': ''}
        if argv[0] == 'blkid':
            if self.signature == 'none':
                return {'returncode': 2, 'stdout': '', 'stderr': ''}
            if self.signature == 'error':
                return {'returncode': 4, 'stdout': '', 'stderr': 'probe error'}
            return {'returncode': 0, 'stdout': 'TYPE=ext4\nUUID=already-formatted\n',
                    'stderr': ''}
        raise AssertionError('unexpected command: %r' % argv)


class TestProbeRunnerContract(unittest.TestCase):
    def test_internal_type_error_is_propagated_without_retry(self):
        calls = []

        def runner(argv, timeout=5):
            calls.append((list(argv), timeout))
            raise TypeError('runner implementation failed')

        with self.assertRaisesRegex(TypeError, 'runner implementation failed'):
            _command(runner, ['lsblk'], timeout=7)

        self.assertEqual([(['lsblk'], 7)], calls)


def service_backend(fs, state='PREPARED', observed_at='2026-10-08T00:00:00Z',
                    capacity=CAPACITY, identity_changes=None, fingerprint='b' * 64,
                    file_path=None):
    device = '/dev/loop0' if file_path else DEVICE
    dev_stat = fs.stat(device)
    sys_stat = fs.stat(SYSFS) if not file_path else FakeStat(stat.S_IFDIR | 0o755, ino=707)
    identity = {
        'boot_id': BOOT,
        'canonical_device': device,
        'rdev': dev_stat.st_rdev,
        'node_inode': dev_stat.st_ino,
        'sysfs_inode': sys_stat.st_ino,
        'capacity_bytes': capacity,
    }
    if file_path:
        file_stat = fs.stat(file_path)
        identity.update({'file_path': file_path, 'file_inode': file_stat.st_ino,
                         'file_device': file_stat.st_dev, 'file_size': file_stat.st_size,
                         'direct_io': True, 'stack_sha256': 'a' * 64,
                         'file_stack_sha256': 'c' * 64})
    identity.update(identity_changes or {})
    return {
        'backend_resource': {
            'resource_uuid': 'a' * 32, 'capacity_bytes': capacity,
            'fingerprint': fingerprint, 'state': state, 'active': state == 'ACTIVE',
            'observed_at': observed_at,
        },
        'identity_qualified': True,
        'ownership_generation': 'a' * 32,
        'effective': {'identity': identity},
    }


def probe(fs, runner=None, **kwargs):
    return probe_writeback_backends(
        host_uuid='host-uuid', now=NOW, runner=runner or ProbeRunner(fs),
        filesystem=fs, **kwargs)


class TestMemoryWritebackBackendProbe(unittest.TestCase):
    def test_dedicated_local_virtio_disk_is_only_an_offline_preparation_target(self):
        fs = FakeFilesystem()
        result = probe(fs)
        self.assertEqual('host-uuid', result['hostUuid'])
        self.assertEqual(BOOT, result['bootId'])
        self.assertIn('observedAt', result)
        candidate = result['candidates'][0]
        self.assertEqual('AVAILABLE', result['status'])
        self.assertEqual('NEEDS_OFFLINE_PREPARATION', candidate['state'])
        self.assertTrue(candidate['eligible'])
        self.assertFalse(candidate['writebackReady'])
        self.assertIsNone(candidate['resourceUuid'])
        self.assertEqual(BY_ID, candidate['path'])
        self.assertEqual('block', candidate['type'])
        self.assertIn('NEEDS_OFFLINE_PREPARATION', candidate['reasons'])

    def test_system_device_is_not_a_candidate_for_preparation(self):
        fs = FakeFilesystem()
        fs.files['/proc/self/mountinfo'] = (
            '1 0 %s / / rw,relatime - ext4 %s rw\n' % (MAJOR_MINOR, DEVICE))
        candidate = probe(fs)['candidates'][0]
        self.assertFalse(candidate['eligible'])
        self.assertIn('SYSTEM_OR_MOUNTED_DEVICE', candidate['reasons'])

    def test_active_lvm_holders_shared_transport_and_multipath_are_rejected(self):
        cases = (
            ('holder', lambda fs: fs.directories.__setitem__(SYSFS + '/holders', ['dm-0']),
             'ACTIVE_BLOCK_HOLDERS'),
            ('lvm', lambda fs: fs.rows[0].update({'type': 'lvm'}),
             'SHARED_OR_LAYERED_STORAGE'),
            ('iscsi', lambda fs: fs.rows[0].update({'tran': 'iscsi'}),
             'SHARED_OR_LAYERED_STORAGE'),
            ('multipath', lambda fs: fs.rows[0].update({'type': 'mpath', 'tran': 'mpath'}),
             'SHARED_OR_LAYERED_STORAGE'),
        )
        for name, configure, expected in cases:
            with self.subTest(name=name):
                fs = FakeFilesystem()
                configure(fs)
                candidate = probe(fs)['candidates'][0]
                self.assertFalse(candidate['eligible'])
                self.assertIn(expected, candidate['reasons'])

    def test_local_sata_ata_sas_scsi_and_nvme_with_pci_evidence_are_candidates(self):
        for transport in ('sata', 'ata', 'sas', 'scsi', 'nvme', ''):
            with self.subTest(transport=transport):
                fs = FakeFilesystem()
                fs.rows[0]['tran'] = transport
                candidate = probe(fs)['candidates'][0]
                self.assertTrue(candidate['eligible'])
                self.assertEqual('NEEDS_OFFLINE_PREPARATION', candidate['state'])
                self.assertFalse(candidate['writebackReady'])
                self.assertIsNone(candidate['resourceUuid'])

    def test_nvme_controller_pcie_is_local_evidence_when_transport_is_empty(self):
        fs = FakeFilesystem(sysfs_path='/sys/devices/platform/nvme0/nvme0/nvme0n1')
        fs.rows[0]['tran'] = ''
        fs.files['/sys/class/nvme/nvme0/transport'] = 'pcie\n'
        candidate = probe(fs)['candidates'][0]
        self.assertTrue(candidate['eligible'])

    def test_unknown_transport_or_missing_local_topology_is_not_assumed_local(self):
        fs = FakeFilesystem()
        fs.rows[0]['tran'] = 'usb'
        candidate = probe(fs)['candidates'][0]
        self.assertFalse(candidate['eligible'])
        self.assertIn('LOCAL_EXCLUSIVITY_NOT_PROVEN', candidate['reasons'])

        no_topology = FakeFilesystem(sysfs_path='/sys/devices/virtual/block/vdb')
        no_topology.rows[0]['tran'] = ''
        candidate = probe(no_topology)['candidates'][0]
        self.assertFalse(candidate['eligible'])
        self.assertIn('LOCAL_EXCLUSIVITY_NOT_PROVEN', candidate['reasons'])

    def test_fc_iscsi_and_nvme_of_are_rejected_even_with_local_pci_ancestry(self):
        cases = (
            ('fc-transport', 'scsi', '/sys/devices/pci0000:00/host1/rport-1:0-0/target1:0:0/1:0:0:0/block/vdb'),
            ('iscsi-session', 'scsi', '/sys/devices/pci0000:00/host1/session1/target1:0:0/1:0:0:0/block/vdb'),
            ('nvme-tcp', 'nvme-tcp', '/sys/devices/virtual/nvme-fabrics/ctl/nvme0/nvme0n1'),
            ('nvme-rdma', 'nvmeof', '/sys/devices/virtual/nvme-fabrics/ctl/nvme0/nvme0n1'),
            ('nvme-fc', 'nvme-fc', '/sys/devices/virtual/nvme-fabrics/ctl/nvme0/nvme0n1'),
        )
        for label, transport, path in cases:
            with self.subTest(label=label):
                fs = FakeFilesystem(sysfs_path=path)
                fs.rows[0]['tran'] = transport
                candidate = probe(fs)['candidates'][0]
                self.assertFalse(candidate['eligible'])
                self.assertIn('SHARED_OR_LAYERED_STORAGE', candidate['reasons'])

    def test_missing_or_duplicate_serial_and_by_id_are_fail_closed(self):
        no_serial = FakeFilesystem()
        no_serial.rows[0]['serial'] = None
        candidate = probe(no_serial)['candidates'][0]
        self.assertFalse(candidate['eligible'])
        self.assertIn('SERIAL_IDENTITY_MISSING', candidate['reasons'])

        duplicate = FakeFilesystem()
        duplicate_row = dict(duplicate.rows[0])
        duplicate_row.update({'name': '/dev/vdc', 'kname': 'vdc',
                              'maj:min': '252:32'})
        duplicate.rows.append(duplicate_row)
        duplicate.links['/dev/vdc'] = '/dev/vdc'
        duplicate.links['/sys/dev/block/252:32'] = SYSFS + '-vdc'
        duplicate.stats['/dev/vdc'] = FakeStat(
            stat.S_IFBLK | 0o600, ino=102, rdev=os.makedev(252, 32), size=CAPACITY)
        duplicate.stats[SYSFS + '-vdc'] = FakeStat(stat.S_IFDIR | 0o755, ino=304)
        duplicate.directories[SYSFS + '-vdc/holders'] = []
        duplicate.directories[SYSFS + '-vdc/slaves'] = []
        rows = probe(duplicate)['candidates']
        for candidate in rows:
            self.assertFalse(candidate['eligible'])
            self.assertIn('SERIAL_IDENTITY_NOT_UNIQUE', candidate['reasons'])

    def test_existing_signature_and_signature_probe_failure_are_rejected(self):
        fs = FakeFilesystem()
        for signature, expected in (('formatted', 'EXISTING_FILESYSTEM_OR_PARTITION_SIGNATURE'),
                                    ('error', 'SIGNATURE_PROBE_FAILED')):
            with self.subTest(signature=signature):
                candidate = probe(fs, runner=ProbeRunner(fs, signature=signature))['candidates'][0]
                self.assertFalse(candidate['eligible'])
                self.assertIn(expected, candidate['reasons'])

    def test_prepared_resource_reuses_service_uuid_only_when_capacity_and_identity_match(self):
        fs = FakeFilesystem()
        service = service_backend(fs)
        result = probe(fs, service_backend=service,
                       service_config={'device': DEVICE})
        candidate = result['candidates'][0]
        self.assertTrue(candidate['eligible'])
        self.assertTrue(candidate['writebackReady'])
        self.assertEqual('PREPARED', candidate['state'])
        self.assertEqual('a' * 32, candidate['resourceUuid'])
        self.assertEqual('b' * 64, candidate['fingerprint'])
        self.assertEqual(CAPACITY, candidate['capacityBytes'])

    def test_prepared_capacity_mismatch_does_not_reuse_service_uuid(self):
        fs = FakeFilesystem()
        service = service_backend(fs, capacity=CAPACITY + 4096)
        result = probe(fs, service_backend=service,
                       service_config={'device': DEVICE})
        local = next(candidate for candidate in result['candidates']
                     if candidate['type'] == 'block' and candidate['device'] == DEVICE)
        self.assertFalse(local['writebackReady'])
        self.assertEqual('IDENTITY_MISMATCH', local['state'])
        self.assertIsNone(local['resourceUuid'])

    def test_boot_change_invalidates_prepared_resource_and_changes_candidate_fingerprint(self):
        first_fs = FakeFilesystem(boot_id='boot-one')
        first = probe_writeback_backends(host_uuid='host-uuid', now=NOW,
                                         runner=ProbeRunner(first_fs), filesystem=first_fs)
        second_fs = FakeFilesystem(boot_id='boot-two')
        stale_service = service_backend(first_fs)
        second = probe_writeback_backends(host_uuid='host-uuid', now=NOW,
                                          service_backend=stale_service,
                                          service_config={'device': DEVICE},
                                          runner=ProbeRunner(second_fs), filesystem=second_fs)
        self.assertNotEqual(first['candidates'][0]['fingerprint'],
                            second['candidates'][0]['fingerprint'])
        self.assertIn('PREPARED_BACKEND_BOOT_ID_MISMATCH', second['reasons'])
        self.assertIsNone(second['candidates'][0].get('resourceUuid'))

    def test_stale_service_observation_is_not_treated_as_prepared(self):
        fs = FakeFilesystem()
        service = service_backend(fs, observed_at='2026-10-07T23:00:00Z')
        result = probe(fs, service_backend=service,
                       service_config={'device': DEVICE})
        self.assertTrue(result['candidates'][0]['eligible'])
        self.assertFalse(result['candidates'][0]['writebackReady'])
        self.assertIn('PREPARED_BACKEND_EVIDENCE_INVALID', result['reasons'])

    def test_file_backend_is_listed_only_when_service_prepared_identity_matches(self):
        fs = FakeFilesystem()
        fs.rows[0]['type'] = 'loop'
        fs.rows[0]['name'] = '/dev/loop0'
        fs.rows[0]['kname'] = 'loop0'
        fs.rows[0]['maj:min'] = '7:0'
        fs.rows[0]['serial'] = None
        fs.links['/dev/loop0'] = '/dev/loop0'
        fs.links['/sys/dev/block/7:0'] = SYSFS
        fs.stats[SYSFS] = FakeStat(stat.S_IFDIR | 0o755, ino=707)
        fs.stats['/dev/loop0'] = fs.stats['/dev/loop0']
        fs.files['/proc/self/mountinfo'] = '1 0 8:1 / / rw - ext4 /dev/root rw\n'
        service = service_backend(fs, file_path='/var/lib/zram/writeback.img')
        service['effective']['identity'].update({
            'canonical_device': '/dev/loop0', 'rdev': fs.stat('/dev/loop0').st_rdev,
            'node_inode': fs.stat('/dev/loop0').st_ino,
            'sysfs_inode': 707, 'capacity_bytes': CAPACITY,
        })
        result = probe(fs, service_backend=service,
                       service_config={'device': '/dev/loop0',
                                       'file_path': '/var/lib/zram/writeback.img'})
        files = [candidate for candidate in result['candidates']
                 if candidate['type'] == 'file']
        self.assertEqual(1, len(files))
        self.assertTrue(files[0]['writebackReady'])
        self.assertEqual('a' * 32, files[0]['resourceUuid'])
        self.assertEqual('/var/lib/zram/writeback.img', files[0]['path'])

    def test_arbitrary_file_paths_are_never_scanned_or_returned(self):
        fs = FakeFilesystem()
        result = probe(fs)
        self.assertFalse(any(candidate['type'] == 'file'
                             for candidate in result['candidates']))

    def test_missing_prepared_device_is_reported_disconnected(self):
        fs = FakeFilesystem(rows=[])
        service = service_backend(FakeFilesystem())
        result = probe(fs, service_backend=service,
                       service_config={'device': DEVICE})
        self.assertEqual('DISCONNECTED', result['status'])
        self.assertEqual('DISCONNECTED', result['candidates'][0]['state'])
        self.assertEqual('a' * 32, result['candidates'][0]['resourceUuid'])

    def test_unsupported_lsblk_is_reported_without_candidates(self):
        fs = FakeFilesystem()
        result = probe(fs, runner=ProbeRunner(fs, lsblk_rc=127))
        self.assertEqual('UNSUPPORTED', result['status'])
        self.assertEqual([], result['candidates'])
        self.assertIn('LSBLK_UNSUPPORTED_OR_FAILED', result['reasons'])


if __name__ == '__main__':
    unittest.main()

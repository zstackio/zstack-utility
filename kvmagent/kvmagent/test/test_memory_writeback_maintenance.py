import hashlib
import datetime
import time
import unittest

from kvmagent.plugins.memory_writeback_maintenance import (
    build_backend_maintenance_request,
    read_backend_maintenance_status,
)


class MemoryWritebackMaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.boot_id = 'boot-123'
        self.candidate_id = 'candidate:' + 'a' * 64
        self.inventory = {
            'hostUuid': 'host-1',
            'bootId': self.boot_id,
            'observedAt': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            'candidates': [{
                'identity': self.candidate_id,
                'type': 'block',
                'device': '/dev/vdb',
                'capacityBytes': 20 * 1024 ** 3,
                'hostBootId': self.boot_id,
                'eligible': True,
                'writebackReady': False,
                'state': 'NEEDS_OFFLINE_PREPARATION',
                'stableIdentity': {
                    'bootId': self.boot_id,
                    'device': '/dev/vdb',
                    'majorMinor': '252:16',
                    'capacityBytes': 20 * 1024 ** 3,
                    'sysfsPath': '/sys/devices/pci0000:00/0000:00:01.0/virtio1/block/vdb',
                    'sysfsInode': '8910',
                    'rdev': 64528,
                    'nodeInode': 2345,
                },
            }],
        }
        self.preparation = {
            'requestId': '5a6a0d5b-21a0-4466-8205-92f6c4b92f08',
            'candidateId': self.candidate_id,
            'expectedHostBootId': self.boot_id,
            'expectedPoolGeneration': 'none',
            'backendCapacityBytes': 20 * 1024 ** 3,
            'resetConfirmed': True,
        }

    def test_builds_go_request_from_fresh_candidate_identity(self):
        request = build_backend_maintenance_request(self.inventory, self.preparation)
        expected_digest = hashlib.sha256(
            b'252:16:/sys/devices/pci0000:00/0000:00:01.0/virtio1/block/vdb:8910\n'
        ).hexdigest()
        self.assertEqual(self.preparation['requestId'], request['request_id'])
        self.assertEqual(self.candidate_id, request['candidate_id'])
        self.assertEqual('none', request['expected_pool_generation'])
        self.assertEqual('/dev/vdb', request['backend']['device'])
        self.assertEqual(expected_digest, request['target_identity']['stack_sha256'])
        self.assertEqual(64528, request['target_identity']['rdev'])
        self.assertEqual('/dev/vdb', request['target_identity']['canonical_device'])
        self.assertEqual(8910, request['target_identity']['sysfs_inode'])
        self.assertIs(request['target_identity']['direct_io'], False)
        self.assertEqual({'device': '/dev/vdb', 'minimum_filesystem_free_bytes': 0,
                          'exclusive': True},
                         request['backend'])
        self.assertTrue(request['reset_confirmed'])

    def test_rejects_stale_probe(self):
        self.inventory['observedAt'] = datetime.datetime.fromtimestamp(
            time.time() - 91, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        with self.assertRaisesRegex(ValueError, 'WRITEBACK_INVENTORY_STALE'):
            build_backend_maintenance_request(self.inventory, self.preparation)

    def test_rejects_boot_or_capacity_change(self):
        changed = dict(self.preparation, expectedHostBootId='other-boot')
        with self.assertRaisesRegex(ValueError, 'BOOT_ID_MISMATCH'):
            build_backend_maintenance_request(self.inventory, changed)
        changed = dict(self.preparation, backendCapacityBytes=123)
        with self.assertRaisesRegex(ValueError, 'CAPACITY_MISMATCH'):
            build_backend_maintenance_request(self.inventory, changed)

    def test_rejects_ineligible_or_prepared_candidate(self):
        self.inventory['candidates'][0]['eligible'] = False
        with self.assertRaisesRegex(ValueError, 'NOT_PREPARABLE'):
            build_backend_maintenance_request(self.inventory, self.preparation)
        self.inventory['candidates'][0]['eligible'] = True
        self.inventory['candidates'][0]['writebackReady'] = True
        with self.assertRaisesRegex(ValueError, 'NOT_PREPARABLE'):
            build_backend_maintenance_request(self.inventory, self.preparation)

    def test_requires_explicit_reset_confirmation(self):
        changed = dict(self.preparation, resetConfirmed=False)
        with self.assertRaisesRegex(ValueError, 'CONFIRMATION_REQUIRED'):
            build_backend_maintenance_request(self.inventory, changed)

    def test_status_helper_only_reads_status(self):
        class Client:
            def __init__(self):
                self.paths = []

            def get(self, path):
                self.paths.append(path)
                return {'stage': 'AWAITING_SERVICE_READBACK', 'request_id': 'task-1'}

        client = Client()
        status = read_backend_maintenance_status(client)
        self.assertEqual(['/v1/backend-maintenance'], client.paths)
        self.assertEqual('AWAITING_SERVICE_READBACK', status['stage'])


if __name__ == '__main__':
    unittest.main()

'''
Unit tests for TensorFusion plugin components.

Run: python -m pytest kvmagent/kvmagent/test/test_tensorfusion.py -v
'''

import os
import re
import sys
import threading
import time
import types
import unittest

try:
    import builtins
    BUILTINS_MODULE = 'builtins'
except ImportError:
    import __builtin__ as builtins
    BUILTINS_MODULE = '__builtin__'

try:
    from unittest import mock
except ImportError:
    import mock

# ---------------------------------------------------------------------------
# Mock zstacklib modules so tests can run under Python 3 without the full
# zstacklib package (which contains Python 2 syntax).
# ---------------------------------------------------------------------------

_mock_log = types.ModuleType('zstacklib.utils.log')
_mock_logger = mock.MagicMock()
_mock_log.get_logger = mock.MagicMock(return_value=_mock_logger)

_mock_pci = types.ModuleType('zstacklib.utils.pci')


def _normalize_pci_address_for_test(pci_address):
    if not pci_address:
        return None

    addr = str(pci_address).strip()
    if not addr:
        return None

    addr = re.sub(r'0x', '', addr, flags=re.IGNORECASE)
    parts = addr.split(':')
    if len(parts) == 2:
        if '.' not in parts[1]:
            return None
        domain = '0000'
        bus = parts[0]
        bus_slot_func = parts[1]
    elif len(parts) == 3:
        domain = parts[0]
        bus = parts[1]
        bus_slot_func = parts[2]
    else:
        return None

    if '.' not in bus_slot_func:
        return None

    slot, function = bus_slot_func.split('.', 1)

    try:
        domain = format(int(domain, 16), '04x')
        bus = format(int(bus, 16), '02x')
        slot = format(int(slot, 16), '02x')
        function = format(int(function, 16), 'x')
    except ValueError:
        return None

    if len(domain) == 8:
        domain = domain[4:]

    return '%s:%s:%s.%s' % (domain, bus, slot, function)


_mock_pci.normalize_pci_address = _normalize_pci_address_for_test

_mock_nvidia_mod = types.ModuleType('zstacklib.gpu.vendors.nvidia')

class _MockNVIDIA(object):
    @classmethod
    def query_gpu_details(cls):
        return {}

_mock_nvidia_mod.NVIDIA = _MockNVIDIA

for mod_name, mod_obj in [
    ('zstacklib', types.ModuleType('zstacklib')),
    ('zstacklib.utils', types.ModuleType('zstacklib.utils')),
    ('zstacklib.utils.log', _mock_log),
    ('zstacklib.utils.pci', _mock_pci),
    ('zstacklib.gpu', types.ModuleType('zstacklib.gpu')),
    ('zstacklib.gpu.vendors', types.ModuleType('zstacklib.gpu.vendors')),
    ('zstacklib.gpu.vendors.nvidia', _mock_nvidia_mod),
]:
    sys.modules.setdefault(mod_name, mod_obj)

# Now safe to import tensorfusion modules
from kvmagent.plugins.tensorfusion.models import Worker, WorkerCreateRequest, GPUResourceInfo, GPUHardwareInfo
from kvmagent.plugins.tensorfusion.store import StateStore
from kvmagent.plugins.tensorfusion.tracker import ResourceTracker

TEST_LICENSE = 'test-license'
TEST_LICENSE_SIGN = 'test-license-sign'


def _make_worker(device_uuid='dev-001', vm_uuid='vm-001', pci_address='0000:3b:00.0',
                 pid=1234, allocated_memory_mb=1024):
    w = Worker()
    w.device_uuid = device_uuid
    w.vm_uuid = vm_uuid
    w.pci_address = pci_address
    w.pid = pid
    w.cuda_index = 0
    w.protocol = 'shmem'
    w.allocated_memory_mb = allocated_memory_mb
    w.shared_memory_size = allocated_memory_mb * 1024 * 1024
    w.license = TEST_LICENSE
    w.license_sign = TEST_LICENSE_SIGN
    w.enable_log = True
    w.log_level = 'info'
    return w


def _make_gpu_details():
    return {
        '0000:3b:00.0': {
            'cuda_index': 0,
            'pci_address': '0000:3b:00.0',
            'name': 'Tesla T4',
            'total_memory_mb': 16384,
            'driver_version': '535.129.03',
        },
        '0000:86:00.0': {
            'cuda_index': 1,
            'pci_address': '0000:86:00.0',
            'name': 'Tesla T4',
            'total_memory_mb': 16384,
            'driver_version': '535.129.03',
        },
    }


# =============================================================================
# models
# =============================================================================

class TestWorker(unittest.TestCase):

    def test_to_dict(self):
        w = _make_worker()
        d = w.to_dict()
        self.assertEqual(d['deviceUuid'], 'dev-001')
        self.assertEqual(d['vmUuid'], 'vm-001')
        self.assertEqual(d['pid'], 1234)
        self.assertEqual(d['allocatedMemoryMb'], 1024)

    def test_default_values(self):
        w = Worker()
        self.assertIsNone(w.protocol)
        self.assertEqual(w.sm_percent_limit, 0)


class TestWorkerCreateRequest(unittest.TestCase):

    def test_ensure_device_uuid_generates(self):
        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        self.assertIsNone(req.device_uuid)
        req.ensure_device_uuid()
        self.assertIsNotNone(req.device_uuid)
        self.assertTrue(len(req.device_uuid) > 0)

    def test_ensure_device_uuid_preserves(self):
        req = WorkerCreateRequest()
        req.device_uuid = 'my-uuid'
        req.ensure_device_uuid()
        self.assertEqual(req.device_uuid, 'my-uuid')

    def test_shmem_size_default_zero(self):
        req = WorkerCreateRequest()
        self.assertEqual(req.shmem_size, 0)


# =============================================================================
# store
# =============================================================================

class TestStateStore(unittest.TestCase):

    def setUp(self):
        self.store = StateStore()

    def test_add_and_get(self):
        w = _make_worker()
        self.store.add(w)
        self.assertEqual(self.store.get('dev-001').vm_uuid, 'vm-001')
        self.assertTrue(self.store.exists('dev-001'))
        self.assertEqual(self.store.count(), 1)

    def test_remove(self):
        self.store.add(_make_worker())
        self.store.remove('dev-001')
        self.assertIsNone(self.store.get('dev-001'))
        self.assertEqual(self.store.count(), 0)

    def test_list_by_vm(self):
        self.store.add(_make_worker('d1', 'vm-001'))
        self.store.add(_make_worker('d2', 'vm-001'))
        self.store.add(_make_worker('d3', 'vm-002'))
        self.assertEqual(len(self.store.list_by_vm('vm-001')), 2)
        self.assertEqual(len(self.store.list_by_vm('vm-002')), 1)
        self.assertEqual(len(self.store.list_by_vm('vm-999')), 0)

    def test_list_by_gpu(self):
        self.store.add(_make_worker('d1', 'vm-001', '0000:3b:00.0'))
        self.store.add(_make_worker('d2', 'vm-002', '0000:3b:00.0'))
        self.store.add(_make_worker('d3', 'vm-003', '0000:86:00.0'))
        self.assertEqual(len(self.store.list_by_gpu('0000:3b:00.0')), 2)

    @mock.patch('kvmagent.plugins.tensorfusion.store.normalize_pci_address')
    def test_list_by_gpu_normalizes_equivalent_addresses(self, mock_normalize):
        def _normalize(addr):
            mapping = {
                '00000000:3B:00.0': '0000:3b:00.0',
                '0000:3b:00.0': '0000:3b:00.0',
            }
            return mapping.get(addr, addr)

        mock_normalize.side_effect = _normalize
        self.store.add(_make_worker('d1', 'vm-001', '0000:3b:00.0'))
        self.assertEqual(1, len(self.store.list_by_gpu('00000000:3B:00.0')))

    def test_sync(self):
        self.store.add(_make_worker('old', 'vm-old'))
        new_workers = [_make_worker('new1', 'vm-new'), _make_worker('new2', 'vm-new')]
        self.store.sync(new_workers)
        self.assertIsNone(self.store.get('old'))
        self.assertEqual(self.store.count(), 2)

    def test_clear(self):
        self.store.add(_make_worker())
        self.store.clear()
        self.assertEqual(self.store.count(), 0)

    def test_add_requires_device_uuid(self):
        worker = _make_worker()
        worker.device_uuid = None

        with self.assertRaises(ValueError) as ctx:
            self.store.add(worker)

        self.assertIn('worker.device_uuid is required', str(ctx.exception))

    def test_sync_requires_unique_nonempty_device_uuid(self):
        missing_uuid = _make_worker()
        missing_uuid.device_uuid = None
        duplicate_1 = _make_worker('dup')
        duplicate_2 = _make_worker('dup', 'vm-002')

        with self.assertRaises(ValueError) as ctx:
            self.store.sync([missing_uuid])
        self.assertIn('worker.device_uuid is required', str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            self.store.sync([duplicate_1, duplicate_2])
        self.assertIn('duplicate worker.device_uuid: dup', str(ctx.exception))

    def test_set_restarting_updates_expected_worker_only(self):
        worker = _make_worker()
        other = _make_worker(pid=5678)
        self.store.add(worker)

        updated = self.store.set_restarting(worker.device_uuid, True, expected_worker=worker)
        self.assertIs(updated, worker)
        self.assertTrue(worker.restarting)

        self.assertIsNone(self.store.set_restarting(worker.device_uuid, False, expected_worker=other))
        self.assertTrue(worker.restarting)

    def test_replace_updates_expected_worker_only(self):
        worker = _make_worker()
        replacement = _make_worker(pid=5678)
        other = _make_worker(device_uuid='dev-001', pid=9999)
        self.store.add(worker)

        self.assertIs(self.store.replace(replacement, expected_worker=worker), replacement)
        self.assertIs(self.store.get(worker.device_uuid), replacement)

        self.assertIsNone(self.store.replace(other, expected_worker=worker))
        self.assertIs(self.store.get(worker.device_uuid), replacement)


# =============================================================================
# tracker
# =============================================================================

class TestResourceTracker(unittest.TestCase):

    def setUp(self):
        self.gpu_details = _make_gpu_details()
        self.tracker = ResourceTracker(self.gpu_details)

    def test_allocate_and_available(self):
        pci = '0000:3b:00.0'
        self.assertEqual(self.tracker.get_available_memory(pci), 16384)
        self.tracker.allocate(pci, 'dev-001', 4096)
        self.assertEqual(self.tracker.get_available_memory(pci), 12288)

    def test_can_allocate(self):
        pci = '0000:3b:00.0'
        self.assertTrue(self.tracker.can_allocate(pci, 16384))
        self.assertFalse(self.tracker.can_allocate(pci, 16385))
        self.tracker.allocate(pci, 'dev-001', 8192)
        self.assertTrue(self.tracker.can_allocate(pci, 8192))
        self.assertFalse(self.tracker.can_allocate(pci, 8193))

    def test_release(self):
        pci = '0000:3b:00.0'
        self.tracker.allocate(pci, 'dev-001', 4096)
        self.tracker.release(pci, 'dev-001')
        self.assertEqual(self.tracker.get_available_memory(pci), 16384)

    def test_release_nonexistent(self):
        # should not raise
        self.tracker.release('0000:3b:00.0', 'no-such-device')

    def test_rebuild_from_workers(self):
        workers = [
            _make_worker('d1', 'vm-1', '0000:3b:00.0', allocated_memory_mb=2048),
            _make_worker('d2', 'vm-2', '0000:3b:00.0', allocated_memory_mb=4096),
            _make_worker('d3', 'vm-3', '0000:86:00.0', allocated_memory_mb=8192),
        ]
        self.tracker.rebuild_from_workers(workers)
        self.assertEqual(self.tracker.get_available_memory('0000:3b:00.0'), 16384 - 2048 - 4096)
        self.assertEqual(self.tracker.get_available_memory('0000:86:00.0'), 16384 - 8192)

    def test_get_gpu_usage(self):
        pci = '0000:3b:00.0'
        self.tracker.allocate(pci, 'dev-001', 4096)
        usage = self.tracker.get_gpu_usage(pci)
        self.assertEqual(usage.total_memory_mb, 16384)
        self.assertEqual(usage.allocated_memory_mb, 4096)
        self.assertEqual(usage.worker_count, 1)
        self.assertEqual(usage.cuda_index, 0)

    def test_unknown_gpu_defaults_to_zero(self):
        pci = '0000:ff:00.0'
        self.assertEqual(self.tracker.get_available_memory(pci), 0)

    def test_refresh_gpu_details_updates_tracked_gpu_capacity(self):
        tracker = ResourceTracker({})
        tracker.allocate('0000:3b:00.0', 'dev-001', 1024)
        self.assertEqual(-1024, tracker.get_available_memory('0000:3b:00.0'))

        tracker.refresh_gpu_details(_make_gpu_details())
        self.assertEqual(16384 - 1024, tracker.get_available_memory('0000:3b:00.0'))

    @mock.patch('kvmagent.plugins.tensorfusion.tracker.normalize_pci_address')
    def test_normalizes_equivalent_pci_addresses_to_single_gpu(self, mock_normalize):
        def _normalize(addr):
            mapping = {
                '00000000:3B:00.0': '0000:3b:00.0',
                '0000:3b:00.0': '0000:3b:00.0',
            }
            return mapping.get(addr, addr)

        mock_normalize.side_effect = _normalize
        tracker = ResourceTracker({
            '00000000:3B:00.0': {
                'cuda_index': 0,
                'pci_address': '0000:3b:00.0',
                'name': 'Tesla T4',
                'total_memory_mb': 16384,
                'driver_version': '535.129.03',
            }
        })

        tracker.allocate('00000000:3B:00.0', 'dev-001', 4096)
        tracker.allocate('0000:3b:00.0', 'dev-002', 2048)

        self.assertEqual(1, len(tracker._gpus))
        self.assertEqual(16384 - 4096 - 2048, tracker.get_available_memory('0000:3b:00.0'))

        tracker.release('00000000:3B:00.0', 'dev-001')
        self.assertEqual(16384 - 2048, tracker.get_available_memory('0000:3b:00.0'))


# =============================================================================
# service (with mocked executor)
# =============================================================================

class TestTensorFusionService(unittest.TestCase):

    def _mock_executor(self, MockExecutor):
        return MockExecutor.return_value

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_create_and_destroy_worker(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.is_alive.return_value = True

        created_worker = _make_worker()
        mock_executor.start.return_value = created_worker
        mock_executor.stop.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN

        worker = svc.create_worker(req)
        self.assertEqual(worker.device_uuid, 'dev-001')

        result = svc.destroy_worker('dev-001')
        self.assertTrue(result)

        # worker should be gone
        self.assertIsNone(svc.get_worker('dev-001'))

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_insufficient_memory(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 99999  # exceeds 16384
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN

        with self.assertRaises(Exception) as ctx:
            svc.create_worker(req)
        self.assertIn('insufficient GPU memory', str(ctx.exception))

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_create_worker_reuses_existing_live_worker(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        created_worker = _make_worker()
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = created_worker
        mock_executor.is_alive.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN

        first = svc.create_worker(req)
        second = svc.create_worker(req)

        self.assertEqual(first.device_uuid, 'dev-001')
        self.assertIs(first, second)
        self.assertEqual(mock_executor.start.call_count, 1)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_create_worker_serializes_allocation_per_gpu(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.is_alive.return_value = False

        def _start(req):
            time.sleep(0.05)
            return _make_worker(device_uuid=req.device_uuid, vm_uuid=req.vm_uuid,
                                pci_address=req.pci_address, pid=1000 if req.device_uuid == 'dev-001' else 1001,
                                allocated_memory_mb=req.memory_mb)

        mock_executor.start.side_effect = _start

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req1 = WorkerCreateRequest()
        req1.vm_uuid = 'vm-001'
        req1.pci_address = '0000:3b:00.0'
        req1.memory_mb = 10000
        req1.device_uuid = 'dev-001'
        req1.license = TEST_LICENSE
        req1.license_sign = TEST_LICENSE_SIGN

        req2 = WorkerCreateRequest()
        req2.vm_uuid = 'vm-002'
        req2.pci_address = '0000:3b:00.0'
        req2.memory_mb = 10000
        req2.device_uuid = 'dev-002'
        req2.license = TEST_LICENSE
        req2.license_sign = TEST_LICENSE_SIGN

        results = []
        errors = []

        def _create(req):
            try:
                results.append(svc.create_worker(req).device_uuid)
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=_create, args=(req1,))
        t2 = threading.Thread(target=_create, args=(req2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(1, len(results))
        self.assertIn(results[0], ['dev-001', 'dev-002'])
        self.assertEqual(1, len(errors))
        self.assertIn('insufficient GPU memory', errors[0])
        self.assertEqual(1, svc.get_gpu_usage('0000:3b:00.0').worker_count)

    @mock.patch('kvmagent.plugins.tensorfusion.service.normalize_pci_address')
    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_create_worker_reuses_existing_live_worker_with_equivalent_pci(self, MockExecutor, MockNVIDIA, mock_normalize):
        def _normalize(addr):
            mapping = {
                '00000000:3B:00.0': '0000:3b:00.0',
                '0000:3b:00.0': '0000:3b:00.0',
            }
            return mapping.get(addr, addr)

        mock_normalize.side_effect = _normalize
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        created_worker = _make_worker(pci_address='0000:3b:00.0')
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = created_worker
        mock_executor.is_alive.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '00000000:3B:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN

        first = svc.create_worker(req)

        same = WorkerCreateRequest()
        same.vm_uuid = 'vm-001'
        same.pci_address = '0000:3b:00.0'
        same.memory_mb = 1024
        same.device_uuid = 'dev-001'
        same.license = TEST_LICENSE
        same.license_sign = TEST_LICENSE_SIGN

        second = svc.create_worker(same)

        self.assertEqual(first.device_uuid, 'dev-001')
        self.assertIs(first, second)
        self.assertEqual(1, mock_executor.start.call_count)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_create_worker_rejects_conflicting_live_worker(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        created_worker = _make_worker()
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = created_worker
        mock_executor.is_alive.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        svc.create_worker(req)

        conflict = WorkerCreateRequest()
        conflict.vm_uuid = 'vm-001'
        conflict.pci_address = '0000:3b:00.0'
        conflict.memory_mb = 2048
        conflict.device_uuid = 'dev-001'
        conflict.license = TEST_LICENSE
        conflict.license_sign = TEST_LICENSE_SIGN

        with self.assertRaises(Exception) as ctx:
            svc.create_worker(conflict)

        self.assertIn('already exists', str(ctx.exception))
        self.assertEqual(mock_executor.start.call_count, 1)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_create_worker_rejects_live_worker_when_runtime_config_changes(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        created_worker = _make_worker()
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = created_worker
        mock_executor.is_alive.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = 'license-a'
        req.license_sign = 'license-sign-a'
        req.enable_log = True
        req.log_level = 'info'
        svc.create_worker(req)

        changed = WorkerCreateRequest()
        changed.vm_uuid = 'vm-001'
        changed.pci_address = '0000:3b:00.0'
        changed.memory_mb = 1024
        changed.device_uuid = 'dev-001'
        changed.license = 'license-b'
        changed.license_sign = 'license-sign-b'
        changed.enable_log = False
        changed.log_level = 'debug'

        with self.assertRaises(Exception) as ctx:
            svc.create_worker(changed)

        self.assertIn('already exists', str(ctx.exception))
        self.assertEqual(mock_executor.start.call_count, 1)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_destroy_workers_by_vm(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        w1 = _make_worker('d1', 'vm-001', '0000:3b:00.0', 1001, 2048)
        w2 = _make_worker('d2', 'vm-001', '0000:86:00.0', 1002, 4096)

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.side_effect = [w1, w2]
        mock_executor.stop.return_value = True
        mock_executor.is_alive.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        for w, pci, mem in [(w1, '0000:3b:00.0', 2048), (w2, '0000:86:00.0', 4096)]:
            req = WorkerCreateRequest()
            req.vm_uuid = 'vm-001'
            req.pci_address = pci
            req.memory_mb = mem
            req.device_uuid = w.device_uuid
            req.license = TEST_LICENSE
            req.license_sign = TEST_LICENSE_SIGN
            svc.create_worker(req)

        count = svc.destroy_workers_by_vm('vm-001')
        self.assertEqual(count, 2)
        self.assertEqual(len(svc.list_workers()), 0)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_destroy_workers_by_vm_continues_after_failure(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        w1 = _make_worker('d1', 'vm-001', '0000:3b:00.0', 1001, 2048)
        w2 = _make_worker('d2', 'vm-001', '0000:86:00.0', 1002, 4096)

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.side_effect = [w1, w2]
        mock_executor.stop.side_effect = [Exception('kill failed'), True]
        mock_executor.is_alive.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        for w, pci, mem in [(w1, '0000:3b:00.0', 2048), (w2, '0000:86:00.0', 4096)]:
            req = WorkerCreateRequest()
            req.vm_uuid = 'vm-001'
            req.pci_address = pci
            req.memory_mb = mem
            req.device_uuid = w.device_uuid
            req.license = TEST_LICENSE
            req.license_sign = TEST_LICENSE_SIGN
            svc.create_worker(req)

        with self.assertRaises(Exception) as ctx:
            svc.destroy_workers_by_vm('vm-001')

        self.assertIn('d1: kill failed', str(ctx.exception))
        self.assertEqual(mock_executor.stop.call_count, 2)
        self.assertIsNotNone(svc.get_worker('d1'))
        self.assertIsNone(svc.get_worker('d2'))

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_destroy_worker_propagates_stop_failure(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        created_worker = _make_worker()
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = created_worker
        mock_executor.stop.side_effect = Exception('kill failed')
        mock_executor.is_alive.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        svc.create_worker(req)

        with self.assertRaises(Exception) as ctx:
            svc.destroy_worker('dev-001')

        self.assertIn('kill failed', str(ctx.exception))
        self.assertIsNotNone(svc.get_worker('dev-001'))
        self.assertEqual(svc.get_gpu_usage('0000:3b:00.0').allocated_memory_mb, 1024)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_destroy_worker_cleans_up_if_stop_fails_after_process_exit(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        created_worker = _make_worker()
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = created_worker
        mock_executor.stop.side_effect = Exception('cleanup failed')
        mock_executor.is_alive.return_value = False

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        svc.create_worker(req)

        with self.assertRaises(Exception) as ctx:
            svc.destroy_worker('dev-001')

        self.assertIn('cleanup failed', str(ctx.exception))
        self.assertIsNone(svc.get_worker('dev-001'))
        self.assertEqual(svc.get_gpu_usage('0000:3b:00.0').allocated_memory_mb, 0)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_cleanup_dead_workers(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        w = _make_worker()
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = w
        mock_executor.stop.return_value = True
        mock_executor.is_alive.return_value = False  # dead

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        svc.create_worker(req)

        cleaned = svc.cleanup_dead_workers()
        self.assertEqual(cleaned, ['dev-001'])
        self.assertEqual(len(svc.list_workers()), 0)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_get_worker_clears_monitor_state_for_dead_worker(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        w = _make_worker()
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = w
        mock_executor.is_alive.return_value = False

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()
        svc._monitor.clear = mock.MagicMock()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        svc.create_worker(req)

        self.assertIsNone(svc.get_worker('dev-001'))
        svc._monitor.clear.assert_called_once_with('dev-001')

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_cleanup_dead_workers_clears_monitor_state(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        w = _make_worker()
        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.start.return_value = w
        mock_executor.is_alive.return_value = False

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()
        svc._monitor.clear = mock.MagicMock()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        svc.create_worker(req)

        cleaned = svc.cleanup_dead_workers()
        self.assertEqual(cleaned, ['dev-001'])
        svc._monitor.clear.assert_called_once_with('dev-001')

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_service_stop_stops_monitor(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()
        svc._monitor.stop = mock.MagicMock()

        svc.stop()
        svc._monitor.stop.assert_called_once_with()

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_service_initializes_with_empty_gpu_details_when_query_fails(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.side_effect = Exception('nvidia-smi not found')

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        self.assertEqual({}, svc._gpu_details)
        self.assertEqual([], svc.list_workers())

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_create_worker_refreshes_gpu_details_after_initial_query_failure(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.side_effect = [Exception('nvidia-smi not found'), _make_gpu_details()]

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.is_alive.return_value = True
        mock_executor.start.return_value = _make_worker()

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN

        worker = svc.create_worker(req)

        self.assertEqual('dev-001', worker.device_uuid)
        self.assertIn('0000:3b:00.0', svc._gpu_details)
        self.assertEqual(2, MockNVIDIA.query_gpu_details.call_count)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_list_gpu_hardware_refreshes_empty_inventory(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.side_effect = [Exception('nvidia-smi not found'), _make_gpu_details()]

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        gpus = svc.list_gpu_hardware()

        self.assertEqual(2, len(gpus))
        self.assertEqual(2, MockNVIDIA.query_gpu_details.call_count)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_create_worker_requires_license_from_request(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'

        with self.assertRaises(Exception) as ctx:
            svc.create_worker(req)

        self.assertIn('tensor-fusion license is required', str(ctx.exception))
        mock_executor.start.assert_not_called()


class TestProcessExecutor(unittest.TestCase):

    def _import_without_psutil(self, name, *args, **kwargs):
        if name == 'psutil':
            raise ImportError('psutil unavailable')
        return self._real_import(name, *args, **kwargs)

    @mock.patch('kvmagent.plugins.tensorfusion.executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.path.exists', return_value=False)
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.killpg')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.getpgid')
    def test_stop_waits_for_worker_exit(self, mock_getpgid, mock_killpg, _mock_exists, _mock_sleep):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        mock_getpgid.side_effect = [1234, 1234, OSError(3, 'No such process')]
        executor = ProcessExecutor(_make_gpu_details())
        worker = _make_worker(pid=5678)

        self.assertTrue(executor.stop(worker))
        mock_killpg.assert_called_once_with(1234, mock.ANY)
        self.assertEqual(mock_getpgid.call_count, 3)

    @mock.patch('kvmagent.plugins.tensorfusion.executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.path.exists', return_value=False)
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.killpg')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.getpgid')
    def test_stop_reaps_tracked_process(self, mock_getpgid, mock_killpg, _mock_exists, _mock_sleep):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        mock_getpgid.return_value = 1234
        proc = mock.MagicMock()
        proc.pid = 5678
        proc.poll.side_effect = [None, 0]

        executor = ProcessExecutor(_make_gpu_details())
        executor._track_proc(proc)
        worker = _make_worker(pid=5678)

        self.assertTrue(executor.stop(worker))
        proc.wait.assert_called_once_with()
        self.assertIsNone(executor._get_proc(5678))
        mock_killpg.assert_called_once_with(1234, mock.ANY)

    @mock.patch('kvmagent.plugins.tensorfusion.executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.time.time')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.path.exists', return_value=False)
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.killpg')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.getpgid')
    def test_stop_raises_when_worker_does_not_exit(self, mock_getpgid, mock_killpg, _mock_exists, mock_time, _mock_sleep):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        mock_getpgid.return_value = 1234
        mock_time.side_effect = [0, 1, 2, 3, 4, 5, 5, 7]

        executor = ProcessExecutor(_make_gpu_details())
        worker = _make_worker(pid=5678)

        with self.assertRaises(Exception) as ctx:
            executor.stop(worker)

        self.assertIn('did not exit within', str(ctx.exception))
        self.assertEqual([
            mock.call(1234, mock.ANY),
            mock.call(1234, mock.ANY),
        ], mock_killpg.call_args_list)

    def test_start_requires_license_configuration(self):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'

        with mock.patch.dict(os.environ, {}, clear=True):
            executor = ProcessExecutor(_make_gpu_details())
            with self.assertRaises(Exception) as ctx:
                executor.start(req)

        self.assertIn('tensor-fusion license is required', str(ctx.exception))

    @mock.patch('kvmagent.plugins.tensorfusion.executor.subprocess.Popen')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.time.time')
    @mock.patch(BUILTINS_MODULE + '.open', new_callable=mock.mock_open)
    def test_start_polls_process_during_startup_window(self, _mock_open, mock_time, mock_sleep, mock_popen):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        proc = mock.MagicMock()
        proc.poll.side_effect = [None, None, None]
        proc.pid = 4321
        mock_popen.return_value = proc
        mock_time.side_effect = [0, 0.1, 0.2, 3.0]

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN

        executor = ProcessExecutor(_make_gpu_details())
        worker = executor.start(req)

        self.assertEqual(4321, worker.pid)
        self.assertEqual('0000:3b:00.0', mock_popen.call_args.kwargs['env']['TF_PCI_ADDRESS'])
        self.assertEqual(2, proc.poll.call_count)
        self.assertEqual(2, mock_sleep.call_count)

    @mock.patch('kvmagent.plugins.tensorfusion.executor.subprocess.Popen')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.executor.time.time')
    @mock.patch(BUILTINS_MODULE + '.open', new_callable=mock.mock_open)
    def test_start_defaults_enable_log_consistently(self, _mock_open, mock_time, _mock_sleep, mock_popen):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        proc = mock.MagicMock()
        proc.poll.side_effect = [None, None]
        proc.pid = 4321
        mock_popen.return_value = proc
        mock_time.side_effect = [0, 0.1, 3.0]

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        req.enable_log = None

        executor = ProcessExecutor(_make_gpu_details())
        worker = executor.start(req)

        self.assertEqual('1', mock_popen.call_args.kwargs['env']['TF_ENABLE_LOG'])
        self.assertTrue(worker.enable_log)

    @mock.patch('kvmagent.plugins.tensorfusion.executor.os.kill')
    def test_is_alive_fallback_treats_linux_zombie_as_dead(self, mock_kill):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        self._real_import = builtins.__import__
        worker = _make_worker(pid=5678)
        stat_content = '5678 (tensor-fusion-worker) Z 1 2 3 4 5'

        with mock.patch('builtins.__import__', side_effect=self._import_without_psutil):
            with mock.patch(BUILTINS_MODULE + '.open', mock.mock_open(read_data=stat_content)):
                self.assertFalse(ProcessExecutor.is_alive(worker))

        mock_kill.assert_called_once_with(5678, 0)

    def test_scan_running_prefers_pci_address_from_environment(self):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        class _FakeProc(object):
            pid = 4321

            @staticmethod
            def name():
                return 'tensor-fusion-worker'

            @staticmethod
            def cmdline():
                return ['tensor-fusion-worker', '-n', 'shmem', '-m', '/tf_dev-001', '-M', '1024']

            @staticmethod
            def environ():
                return {
                    'TF_DEVICE_UUID': 'dev-001',
                    'VM_UUID': 'vm-001',
                    'TF_PCI_ADDRESS': '0000:3b:00.0',
                    'CUDA_VISIBLE_DEVICES': '7',
                    'TF_LICENSE': TEST_LICENSE,
                    'TF_LICENSE_SIGN': TEST_LICENSE_SIGN,
                }

        fake_psutil = types.ModuleType('psutil')
        fake_psutil.AccessDenied = type('AccessDenied', (Exception,), {})
        fake_psutil.NoSuchProcess = type('NoSuchProcess', (Exception,), {})
        fake_psutil.ZombieProcess = type('ZombieProcess', (Exception,), {})
        fake_psutil.process_iter = lambda: [_FakeProc()]

        with mock.patch.dict(sys.modules, {'psutil': fake_psutil}):
            workers = ProcessExecutor({}).scan_running()

        self.assertEqual(1, len(workers))
        self.assertEqual('0000:3b:00.0', workers[0].pci_address)

    def test_scan_running_skips_worker_when_pci_address_cannot_be_reconstructed(self):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        class _FakeProc(object):
            pid = 4321

            @staticmethod
            def name():
                return 'tensor-fusion-worker'

            @staticmethod
            def cmdline():
                return ['tensor-fusion-worker']

            @staticmethod
            def environ():
                return {
                    'TF_DEVICE_UUID': 'dev-001',
                    'VM_UUID': 'vm-001',
                    'CUDA_VISIBLE_DEVICES': '7',
                }

        fake_psutil = types.ModuleType('psutil')
        fake_psutil.AccessDenied = type('AccessDenied', (Exception,), {})
        fake_psutil.NoSuchProcess = type('NoSuchProcess', (Exception,), {})
        fake_psutil.ZombieProcess = type('ZombieProcess', (Exception,), {})
        fake_psutil.process_iter = lambda: [_FakeProc()]

        with mock.patch.dict(sys.modules, {'psutil': fake_psutil}):
            workers = ProcessExecutor({}).scan_running()

        self.assertEqual([], workers)

    def test_scan_running_skips_worker_when_license_cannot_be_reconstructed(self):
        from kvmagent.plugins.tensorfusion.executor import ProcessExecutor

        class _FakeProc(object):
            pid = 4321

            @staticmethod
            def name():
                return 'tensor-fusion-worker'

            @staticmethod
            def cmdline():
                return ['tensor-fusion-worker', '-n', 'shmem', '-m', '/tf_dev-001', '-M', '1024']

            @staticmethod
            def environ():
                return {
                    'TF_DEVICE_UUID': 'dev-001',
                    'VM_UUID': 'vm-001',
                    'TF_PCI_ADDRESS': '0000:3b:00.0',
                    'CUDA_VISIBLE_DEVICES': '7',
                }

        fake_psutil = types.ModuleType('psutil')
        fake_psutil.AccessDenied = type('AccessDenied', (Exception,), {})
        fake_psutil.NoSuchProcess = type('NoSuchProcess', (Exception,), {})
        fake_psutil.ZombieProcess = type('ZombieProcess', (Exception,), {})
        fake_psutil.process_iter = lambda: [_FakeProc()]

        with mock.patch.dict(sys.modules, {'psutil': fake_psutil}):
            workers = ProcessExecutor({}).scan_running()

        self.assertEqual([], workers)


class TestWorkerRestartMonitor(unittest.TestCase):

    def test_stop_joins_monitor_thread(self):
        from kvmagent.plugins.tensorfusion.monitor import WorkerRestartMonitor

        monitor = WorkerRestartMonitor(StateStore(), mock.MagicMock(), ResourceTracker(_make_gpu_details()))
        with mock.patch.object(monitor, '_check_all', side_effect=lambda: None):
            monitor.start()
            time.sleep(0.01)
            monitor.stop()

        self.assertFalse(monitor._thread.is_alive())

    def test_stop_cancels_pending_restart_backoff(self):
        from kvmagent.plugins.tensorfusion.monitor import WorkerRestartMonitor, CrashState

        store = StateStore()
        tracker = ResourceTracker(_make_gpu_details())
        executor = mock.MagicMock()
        worker = _make_worker()
        store.add(worker)

        monitor = WorkerRestartMonitor(store, executor, tracker)
        with mock.patch.object(CrashState, 'BACKOFF_DELAYS', [30]):
            monitor._handle_dead(worker)
            self.assertTrue(worker.restarting)
            monitor.stop()

        self.assertFalse(worker.restarting)
        executor.start.assert_not_called()
        self.assertEqual({}, monitor._restart_threads)

    def test_restart_skips_stale_worker_replaced_in_store(self):
        from kvmagent.plugins.tensorfusion.monitor import WorkerRestartMonitor

        store = StateStore()
        tracker = ResourceTracker(_make_gpu_details())
        executor = mock.MagicMock()
        old_worker = _make_worker()
        new_worker = _make_worker(pid=4321)
        store.add(old_worker)
        monitor = WorkerRestartMonitor(store, executor, tracker)

        store.set_restarting(old_worker.device_uuid, True, expected_worker=old_worker)
        store.add(new_worker)
        monitor._do_restart(old_worker, 0)

        executor.start.assert_not_called()
        self.assertIs(store.get(old_worker.device_uuid), new_worker)
        self.assertFalse(new_worker.restarting)

    def test_restart_stops_orphan_worker_when_store_entry_removed_during_restart(self):
        from kvmagent.plugins.tensorfusion.monitor import WorkerRestartMonitor

        store = StateStore()
        tracker = ResourceTracker(_make_gpu_details())
        executor = mock.MagicMock()
        worker = _make_worker()
        restarted = _make_worker(pid=4321)
        store.add(worker)
        monitor = WorkerRestartMonitor(store, executor, tracker)

        store.set_restarting(worker.device_uuid, True, expected_worker=worker)

        def _start(_req):
            store.remove(worker.device_uuid)
            return restarted

        executor.start.side_effect = _start

        monitor._do_restart(worker, 0)

        executor.stop.assert_called_once_with(restarted)
        self.assertIsNone(store.get(worker.device_uuid))


if __name__ == '__main__':
    unittest.main()

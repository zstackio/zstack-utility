'''
Unit tests for TensorFusion plugin components.

Run: python -m pytest kvmagent/kvmagent/test/test_tensorfusion.py -v
'''

import errno
import json
import os
import re
import sys
import threading
import time
import types
import unittest
import importlib
from contextlib import contextmanager

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

_mock_operation_gate_mod = types.ModuleType('zstacklib.gpu.operation_gate')


class _MockGPUOperationGate(object):
    @contextmanager
    def critical(self):
        yield


_mock_operation_gate_mod.gpu_operation_gate = _MockGPUOperationGate()

def _build_mock_modules():
    zstacklib_mod = types.ModuleType('zstacklib')
    zstacklib_utils_mod = types.ModuleType('zstacklib.utils')
    zstacklib_gpu_mod = types.ModuleType('zstacklib.gpu')
    zstacklib_gpu_vendors_mod = types.ModuleType('zstacklib.gpu.vendors')
    libvirt_mod = types.ModuleType('libvirt')

    zstacklib_mod.utils = zstacklib_utils_mod
    zstacklib_mod.gpu = zstacklib_gpu_mod
    zstacklib_utils_mod.log = _mock_log
    zstacklib_utils_mod.pci = _mock_pci
    zstacklib_gpu_mod.vendors = zstacklib_gpu_vendors_mod
    zstacklib_gpu_vendors_mod.nvidia = _mock_nvidia_mod

    return {
        'zstacklib': zstacklib_mod,
        'zstacklib.utils': zstacklib_utils_mod,
        'zstacklib.utils.log': _mock_log,
        'zstacklib.utils.pci': _mock_pci,
        'zstacklib.gpu': zstacklib_gpu_mod,
        'zstacklib.gpu.vendors': zstacklib_gpu_vendors_mod,
        'zstacklib.gpu.vendors.nvidia': _mock_nvidia_mod,
        'zstacklib.gpu.operation_gate': _mock_operation_gate_mod,
        'libvirt': libvirt_mod,
    }


def _preload_tensorfusion_modules():
    loaded_modules = {}
    with mock.patch.dict(sys.modules, _build_mock_modules()):
        importlib.import_module('kvmagent.plugins.tensorfusion.models')
        importlib.import_module('kvmagent.plugins.tensorfusion.store')
        importlib.import_module('kvmagent.plugins.tensorfusion.tracker')
        importlib.import_module('kvmagent.plugins.tensorfusion.process_executor')
        importlib.import_module('kvmagent.plugins.tensorfusion.container_executor')
        importlib.import_module('kvmagent.plugins.tensorfusion.monitor')
        importlib.import_module('kvmagent.plugins.tensorfusion.utils')
        importlib.import_module('kvmagent.plugins.tensorfusion.service')
        loaded_modules.update({
            name: module for name, module in sys.modules.items()
            if name == 'kvmagent.plugins.tensorfusion' or
            name.startswith('kvmagent.plugins.tensorfusion.')
        })
    sys.modules.update(loaded_modules)


_preload_tensorfusion_modules()

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


def _new_real_gpu_operation_gate():
    module_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', '..', '..',
        'zstacklib', 'zstacklib', 'gpu', 'operation_gate.py'))
    spec = importlib.util.spec_from_file_location(
        '_tensorfusion_test_operation_gate', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GPUOperationGate()


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
        executor = MockExecutor.return_value
        executor.cleanup_residual_workers_by_vm.return_value = 0
        return executor

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
        mock_executor.cleanup_residual_workers_by_vm.assert_called_once_with(
            'vm-001', known_workers=[])

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
    def test_destroy_workers_by_vm_cleans_residual_processes_when_store_empty(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = self._mock_executor(MockExecutor)
        mock_executor.scan_running.return_value = []
        mock_executor.cleanup_residual_workers_by_vm.return_value = 1

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.initialize()

        count = svc.destroy_workers_by_vm('vm-001')

        self.assertEqual(1, count)
        mock_executor.cleanup_residual_workers_by_vm.assert_called_once_with(
            'vm-001', known_workers=[])

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


class TestTensorFusionGPUOperationGate(unittest.TestCase):

    def _assert_monitoring_blocked(self, gate):
        with gate.monitoring() as acquired:
            self.assertFalse(acquired)

    @contextmanager
    def _service_with_gate(self, executor, gate):
        from kvmagent.plugins.tensorfusion import service as service_module

        with mock.patch.object(service_module, 'gpu_operation_gate', gate), \
                mock.patch.object(service_module.NVIDIA, 'query_gpu_details',
                                  return_value=_make_gpu_details()):
            yield service_module.TensorFusionService(executor=executor)

    def test_destroy_serializes_stop_and_state_finalize(self):
        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()
        worker = _make_worker()
        events = []

        def _record_teardown(name):
            self._assert_monitoring_blocked(gate)
            events.append(name)

        executor.stop.side_effect = lambda _worker: _record_teardown('stop')

        with self._service_with_gate(executor, gate) as service:
            service._store.add(worker)
            service._tracker.allocate(
                worker.pci_address, worker.device_uuid, worker.allocated_memory_mb)
            service._tracker.release = mock.MagicMock(
                side_effect=lambda _pci, _device: _record_teardown('release'))
            self.assertTrue(service.destroy_worker(worker.device_uuid))

        self.assertEqual(['stop', 'release'], events)
        executor.reap_dead.assert_not_called()

    def test_remove_state_preserves_worker_when_reap_reports_running(self):
        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()
        executor.reap_dead.return_value = False
        worker = _make_worker()

        with self._service_with_gate(executor, gate) as service:
            service._store.add(worker)
            service._tracker.allocate(
                worker.pci_address, worker.device_uuid, worker.allocated_memory_mb)
            self.assertIsNone(service._remove_worker_state(worker))

            self.assertIs(worker, service._store.get(worker.device_uuid))
            self.assertEqual(
                worker.allocated_memory_mb,
                service.get_gpu_usage(worker.pci_address).allocated_memory_mb)

    def test_destroy_restores_monitoring_when_reap_rechecks_running(self):
        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()
        executor.stop.side_effect = Exception('stop failed')
        executor.is_alive.return_value = False
        executor.reap_dead.return_value = False
        worker = _make_worker()

        with self._service_with_gate(executor, gate) as service:
            service._store.add(worker)
            service._tracker.allocate(
                worker.pci_address, worker.device_uuid, worker.allocated_memory_mb)
            with self.assertRaises(Exception):
                service.destroy_worker(worker.device_uuid)

            self.assertIs(worker, service._store.get(worker.device_uuid))
            self.assertFalse(worker.restarting)

    def test_start_failure_reconciles_labeled_residual_under_gate(self):
        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()
        executor.start.side_effect = Exception('start failed')
        request = WorkerCreateRequest()
        request.vm_uuid = 'vm-001'

        def _cleanup(vm_uuid, known_workers=None):
            self._assert_monitoring_blocked(gate)
            self.assertEqual('vm-001', vm_uuid)
            self.assertEqual([], known_workers)

        executor.cleanup_residual_workers_by_vm.side_effect = _cleanup

        with self._service_with_gate(executor, gate) as service:
            with self.assertRaises(Exception):
                service._start_worker_runtime(request)

        executor.cleanup_residual_workers_by_vm.assert_called_once_with(
            'vm-001', known_workers=[])

    def test_initialize_and_periodic_orphan_stop_are_serialized(self):
        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()
        initialized_orphan = _make_worker(device_uuid='init-orphan')
        periodic_orphan = _make_worker(device_uuid='periodic-orphan')
        executor.scan_running.side_effect = [[initialized_orphan], [periodic_orphan]]
        stopped = []

        def _stop(worker):
            self._assert_monitoring_blocked(gate)
            stopped.append(worker.device_uuid)

        executor.stop.side_effect = _stop

        with self._service_with_gate(executor, gate) as service, \
                mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running',
                           return_value=False), \
                mock.patch.object(service._monitor, 'start'), \
                mock.patch.object(service, '_start_orphan_scan_timer'):
            service.initialize()
            service._scan_and_cleanup_orphans()

        self.assertEqual(['init-orphan', 'periodic-orphan'], stopped)

    def test_orphan_scan_does_not_remove_replaced_runtime(self):
        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()
        scanned = _make_worker(device_uuid='dev-orphan')
        scanned.container_id = 'old-container-id'
        replacement = _make_worker(device_uuid='dev-orphan', pid=4321)
        replacement.container_id = 'new-container-id'
        executor.scan_running.return_value = [scanned]

        with self._service_with_gate(executor, gate) as service:
            service._store.add(scanned)

            def _replace_during_stop(_worker):
                self._assert_monitoring_blocked(gate)
                service._store.remove(scanned.device_uuid,
                                      expected_worker=scanned)
                service._store.add(replacement)

            executor.stop.side_effect = _replace_during_stop
            with mock.patch(
                    'kvmagent.plugins.tensorfusion.service._is_vm_running',
                    return_value=False):
                service._scan_and_cleanup_orphans()

            self.assertIs(replacement, service._store.get(scanned.device_uuid))
            executor.reap_dead.assert_not_called()

    def test_residual_cleanup_is_serialized(self):
        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()

        def _cleanup(_vm_uuid, known_workers=None):
            self._assert_monitoring_blocked(gate)
            self.assertEqual([], known_workers)
            return 1

        executor.cleanup_residual_workers_by_vm.side_effect = _cleanup

        with self._service_with_gate(executor, gate) as service:
            self.assertEqual(1, service.destroy_workers_by_vm('vm-001'))

    def test_docker_timeout_releases_gate_after_bounded_reap(self):
        import subprocess
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        gate = _new_real_gpu_operation_gate()
        executor = ContainerExecutor(_make_gpu_details())
        proc = mock.MagicMock()
        proc.communicate.side_effect = subprocess.TimeoutExpired(
            ['docker', 'run'], 30)
        proc.kill.side_effect = RuntimeError('kill failed')
        wait_started = threading.Event()
        release_wait = threading.Event()
        wait_timeouts = []
        errors = []

        def _wait(timeout=None):
            wait_timeouts.append(timeout)
            wait_started.set()
            release_wait.wait(1)
            raise subprocess.TimeoutExpired(['docker', 'run'], timeout)

        def _run():
            try:
                with gate.critical():
                    executor._docker(['run'], timeout=30)
            except Exception as e:
                errors.append(e)

        proc.wait.side_effect = _wait
        with mock.patch(
                'kvmagent.plugins.tensorfusion.container_executor.subprocess.Popen',
                return_value=proc):
            thread = threading.Thread(target=_run)
            thread.start()
            self.assertTrue(wait_started.wait(1))
            self._assert_monitoring_blocked(gate)
            release_wait.set()
            thread.join(1)

        self.assertFalse(thread.is_alive())
        self.assertEqual([5], wait_timeouts)
        self.assertEqual(1, len(errors))
        with gate.monitoring() as acquired:
            self.assertTrue(acquired)

    def test_monitor_serializes_reap_and_releases_gate_before_restart(self):
        from kvmagent.plugins.tensorfusion import monitor as monitor_module

        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()
        store = StateStore()
        tracker = mock.MagicMock()
        worker = _make_worker()
        restarted = _make_worker(pid=4321)
        events = []
        store.add(worker)

        def _reap(_worker):
            self._assert_monitoring_blocked(gate)
            events.append('reap')

        def _restart(_worker):
            with gate.monitoring() as acquired:
                self.assertTrue(acquired)
            events.append('restart')
            return restarted

        executor.reap_dead.side_effect = _reap
        monitor = monitor_module.WorkerRestartMonitor(
            store, executor, tracker, restart_worker=_restart)
        store.set_restarting(worker.device_uuid, True, expected_worker=worker)

        with mock.patch.object(monitor_module, 'gpu_operation_gate', gate), \
                mock.patch('kvmagent.plugins.tensorfusion.utils.is_vm_running',
                           return_value=True):
            monitor._do_restart(worker, 0)
            monitor._give_up(worker)

        self.assertEqual(['reap', 'restart', 'reap'], events)
        tracker.release.assert_called_once_with(worker.pci_address, worker.device_uuid)

    def test_monitor_clears_false_crash_episode_when_reap_reports_running(self):
        from kvmagent.plugins.tensorfusion import monitor as monitor_module
        from kvmagent.plugins.tensorfusion.monitor import CrashState

        gate = _new_real_gpu_operation_gate()
        executor = mock.MagicMock()
        executor.reap_dead.return_value = False
        restart = mock.MagicMock()
        store = StateStore()
        tracker = mock.MagicMock()
        worker = _make_worker()
        store.add(worker)
        monitor = monitor_module.WorkerRestartMonitor(
            store, executor, tracker, restart_worker=restart)
        store.set_restarting(worker.device_uuid, True, expected_worker=worker)
        monitor._states[worker.device_uuid] = CrashState()
        monitor._notified_events.add(worker.device_uuid)

        with mock.patch.object(monitor_module, 'gpu_operation_gate', gate), \
                mock.patch('kvmagent.plugins.tensorfusion.utils.is_vm_running',
                           return_value=True):
            monitor._do_restart(worker, 0)
            self.assertIs(worker, store.get(worker.device_uuid))
            self.assertFalse(worker.restarting)
            restart.assert_not_called()
            self.assertNotIn(worker.device_uuid, monitor._states)
            self.assertNotIn(worker.device_uuid, monitor._notified_events)

            store.set_restarting(worker.device_uuid, True, expected_worker=worker)
            monitor._states[worker.device_uuid] = CrashState()
            monitor._notified_events.add(worker.device_uuid)
            self.assertFalse(monitor._give_up(worker))

        self.assertIs(worker, store.get(worker.device_uuid))
        self.assertFalse(worker.restarting)
        self.assertNotIn(worker.device_uuid, monitor._states)
        self.assertNotIn(worker.device_uuid, monitor._notified_events)
        tracker.release.assert_not_called()


class TestContainerExecutor(unittest.TestCase):

    @staticmethod
    def _make_request(protocol='shmem'):
        request = WorkerCreateRequest()
        request.vm_uuid = 'vm-001'
        request.pci_address = '0000:3b:00.0'
        request.memory_mb = 8192
        request.shmem_size = 268435456
        request.license = TEST_LICENSE
        request.license_sign = TEST_LICENSE_SIGN
        request.device_uuid = 'dev-001'
        request.sm_percent_limit = 33
        request.protocol = protocol
        return request

    def test_start_uses_extended_docker_run_timeout(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker_quiet'), \
                mock.patch.object(executor, '_inspect_container', return_value={'State': {'Running': True}}), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove'), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.path.getsize',
                           return_value=268435456), \
                mock.patch.object(executor, '_docker', return_value='container-id') as mock_docker:
            worker = executor.start(self._make_request())

        self.assertEqual('container-id', worker.container_id)
        self.assertEqual(90, mock_docker.call_args[1]['timeout'])
        run_cmd = mock_docker.call_args[0][0]
        docker_env = mock_docker.call_args[1]['env']
        self.assertIn('TF_LICENSE', run_cmd)
        self.assertIn('TF_LICENSE_SIGN', run_cmd)
        self.assertNotIn(TEST_LICENSE, ' '.join(run_cmd))
        self.assertNotIn(TEST_LICENSE_SIGN, ' '.join(run_cmd))
        self.assertEqual(TEST_LICENSE, docker_env['TF_LICENSE'])
        self.assertEqual(TEST_LICENSE_SIGN, docker_env['TF_LICENSE_SIGN'])

    def test_start_waits_for_shared_memory_readiness(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker_quiet'), \
                mock.patch.object(executor, '_inspect_container', return_value={'State': {'Running': True}}), \
                mock.patch.object(executor, '_docker', return_value='container-id'), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove'), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.path.getsize',
                           side_effect=[OSError(), 0, 268435456, 268435456]), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.time.sleep') as mock_sleep:
            worker = executor.start(self._make_request())

        self.assertEqual('/dev/shm/tf_dev-001', worker.shared_memory_path)
        self.assertEqual(2, mock_sleep.call_count)

    def test_start_removes_stale_shared_memory_before_docker_run(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        events = []
        executor = ContainerExecutor(_make_gpu_details())

        def remove_shm(path):
            events.append(('remove_shm', path))

        def docker_run(args, timeout=None, env=None):
            events.append(('docker_run', args[0], timeout, env))
            return 'container-id'

        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker_quiet'), \
                mock.patch.object(executor, '_inspect_container', return_value={'State': {'Running': True}}), \
                mock.patch.object(executor, '_docker', side_effect=docker_run), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove', side_effect=remove_shm), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.path.getsize',
                           return_value=268435456):
            executor.start(self._make_request())

        self.assertEqual(('docker_run', 'rm', None, None), events[0])
        self.assertEqual(('remove_shm', '/dev/shm/tf_dev-001'), events[1])
        self.assertEqual('docker_run', events[2][0])
        self.assertEqual('run', events[2][1])
        self.assertEqual(90, events[2][2])
        self.assertEqual(TEST_LICENSE, events[2][3]['TF_LICENSE'])

    def test_native_start_does_not_wait_for_shared_memory(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker_quiet'), \
                mock.patch.object(executor, '_inspect_container', return_value={'State': {'Running': True}}), \
                mock.patch.object(executor, '_docker', return_value='container-id'), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove'), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.path.getsize') as mock_getsize:
            worker = executor.start(self._make_request(protocol='native'))

        self.assertEqual('native', worker.protocol)
        mock_getsize.assert_not_called()

    def test_shared_memory_timeout_cleans_container_and_file(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        executor.STARTUP_WAIT_SEC = 0
        executor.ROLLBACK_RETRY_WINDOW_SEC = 0
        missing = OSError(2, 'No such file')
        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker_quiet', return_value='') as mock_quiet, \
                mock.patch.object(executor, '_inspect_container', return_value={'State': {'Running': True}}), \
                mock.patch.object(executor, '_docker', return_value='container-id') as mock_docker, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.path.getsize',
                           side_effect=missing), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove',
                           side_effect=[missing, None]) as mock_remove:
            with self.assertRaises(Exception) as ctx:
                executor.start(self._make_request())

        self.assertIn('did not create shared memory', str(ctx.exception))
        self.assertEqual(2, sum(
            1 for call in mock_docker.call_args_list
            if call[0][0] == ['rm', '-f', 'tf-worker-vm-001']))
        mock_quiet.assert_called_once_with(['logs', '--tail', '20', 'tf-worker-vm-001'])
        mock_remove.assert_has_calls([
            mock.call('/dev/shm/tf_dev-001'),
            mock.call('/dev/shm/tf_dev-001'),
        ])

    def test_first_inspect_failure_cleans_container_and_shared_memory(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        executor.ROLLBACK_RETRY_WINDOW_SEC = 0

        def docker_command(args, timeout=None, env=None):
            if args[0] == 'run':
                return 'container-id'
            if args[:2] == ['rm', '-f']:
                return args[2]
            raise AssertionError('unexpected docker command: %s' % args)

        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker_quiet'), \
                mock.patch.object(executor, '_inspect_container', return_value=None), \
                mock.patch.object(executor, '_docker', side_effect=docker_command), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            with self.assertRaises(Exception) as ctx:
                executor.start(self._make_request())

        self.assertIn('inspect failed', str(ctx.exception))
        self.assertEqual([
            mock.call('/dev/shm/tf_dev-001'),
            mock.call('/dev/shm/tf_dev-001'),
        ], mock_remove.call_args_list)

    def test_immediate_exit_cleans_container_and_shared_memory(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        executor.ROLLBACK_RETRY_WINDOW_SEC = 0

        def docker_command(args, timeout=None, env=None):
            if args[0] == 'run':
                return 'container-id'
            if args[:2] == ['rm', '-f']:
                return args[2]
            raise AssertionError('unexpected docker command: %s' % args)

        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker_quiet', return_value='worker failed'), \
                mock.patch.object(executor, '_inspect_container', return_value={
                    'State': {'Running': False, 'ExitCode': 1},
                }), \
                mock.patch.object(executor, '_docker', side_effect=docker_command), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.path.isfile',
                           return_value=False), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            with self.assertRaises(Exception) as ctx:
                executor.start(self._make_request())

        self.assertIn('exited immediately', str(ctx.exception))
        self.assertEqual([
            mock.call('/dev/shm/tf_dev-001'),
            mock.call('/dev/shm/tf_dev-001'),
        ], mock_remove.call_args_list)

    def test_docker_run_failure_cleans_container_and_shared_memory(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        executor.ROLLBACK_RETRY_WINDOW_SEC = 0
        remove_attempts = []

        def docker_command(args, timeout=None, env=None):
            if args[0] == 'run':
                raise Exception('launch rejected %s' % TEST_LICENSE)
            remove_attempts.append(args)
            return args[2]

        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker', side_effect=docker_command), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            with self.assertRaises(Exception) as ctx:
                executor.start(self._make_request())

        self.assertNotIn(TEST_LICENSE, str(ctx.exception))
        self.assertIsNone(ctx.exception.__context__)
        self.assertEqual(2, len(remove_attempts))
        self.assertEqual([
            mock.call('/dev/shm/tf_dev-001'),
            mock.call('/dev/shm/tf_dev-001'),
        ], mock_remove.call_args_list)

    def test_stale_container_removal_failure_blocks_start_and_retains_shared_memory(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker', side_effect=Exception('docker unavailable')) as mock_docker, \
                mock.patch.object(executor, '_inspect_container',
                                  return_value={'State': {'Running': True}}), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            with self.assertRaises(Exception) as ctx:
                executor.start(self._make_request())

        self.assertIn('failed to remove existing worker container', str(ctx.exception))
        mock_docker.assert_called_once_with(['rm', '-f', 'tf-worker-vm-001'])
        mock_remove.assert_not_called()

    def test_failed_start_retains_shared_memory_when_container_may_be_running(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        executor.ROLLBACK_RETRY_WINDOW_SEC = 0
        remove_attempts = []

        def docker_command(args, timeout=None, env=None):
            if args[0] == 'run':
                return 'container-id'
            remove_attempts.append(args)
            if len(remove_attempts) == 1:
                return args[2]
            raise Exception('docker daemon unavailable')

        with mock.patch.object(executor, '_image_exists', return_value=True), \
                mock.patch.object(executor, '_docker_quiet'), \
                mock.patch.object(executor, '_inspect_container',
                                  side_effect=[None, {'State': {'Running': True}}]), \
                mock.patch.object(executor, '_docker', side_effect=docker_command), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            with self.assertRaises(Exception):
                executor.start(self._make_request())

        mock_remove.assert_called_once_with('/dev/shm/tf_dev-001')

    def test_reap_dead_removes_shared_memory(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        worker = _make_worker()
        worker.container_id = 'container-id'
        worker.container_name = 'tf-worker-vm-001'
        worker.shared_memory_path = '/dev/shm/tf_dev-001'
        executor = ContainerExecutor(_make_gpu_details())

        with mock.patch.object(executor, 'is_alive', return_value=False), \
                mock.patch.object(executor, '_docker') as mock_docker, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            executor.reap_dead(worker)

        mock_docker.assert_called_once_with(['rm', '-f', 'container-id'])
        mock_remove.assert_called_once_with('/dev/shm/tf_dev-001')

    def test_stop_raises_and_retains_shared_memory_when_removal_is_unconfirmed(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        worker = _make_worker()
        worker.container_id = 'container-id'
        worker.container_name = 'tf-worker-vm-001'
        worker.shared_memory_path = '/dev/shm/tf_dev-001'
        executor = ContainerExecutor(_make_gpu_details())

        with mock.patch.object(executor, '_docker', side_effect=Exception('docker unavailable')), \
                mock.patch.object(executor, '_inspect_container',
                                  return_value={'State': {'Running': True}}), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            with self.assertRaises(Exception) as ctx:
                executor.stop(worker)

        self.assertIn('failed to remove worker container', str(ctx.exception))
        mock_remove.assert_not_called()

    def test_stop_targets_container_id_before_reusable_name(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        worker = _make_worker()
        worker.container_id = 'old-container-id'
        worker.container_name = 'tf-worker-vm-001'
        worker.shared_memory_path = '/dev/shm/tf_dev-001'
        executor = ContainerExecutor(_make_gpu_details())

        with mock.patch.object(executor, '_docker', return_value='') as mock_docker, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove'):
            executor.stop(worker)

        self.assertEqual([
            mock.call(['stop', '-t', '5', 'old-container-id']),
            mock.call(['rm', '-f', 'old-container-id']),
        ], mock_docker.call_args_list)

    def test_failed_start_retains_shared_memory_when_removal_is_unconfirmed(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        executor = ContainerExecutor(_make_gpu_details())
        executor.ROLLBACK_RETRY_WINDOW_SEC = 1
        now = [10.0]

        def _time():
            return now[0]

        def _sleep(seconds):
            now[0] += seconds

        with mock.patch.object(executor, '_docker',
                               side_effect=Exception('permission denied')) as mock_docker, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.time.time',
                           side_effect=_time), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.time.sleep',
                           side_effect=_sleep) as mock_sleep, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            removed = executor._rollback_failed_start(
                'container-id', '/dev/shm/tf_dev-001')

        self.assertFalse(removed)
        self.assertEqual([
            mock.call(['rm', '-f', 'container-id'], timeout=1),
            mock.call(['rm', '-f', 'container-id'], timeout=1),
            mock.call(['rm', '-f', 'container-id'], timeout=1),
        ], mock_docker.call_args_list)
        self.assertEqual([
            mock.call(0.5),
            mock.call(0.5),
        ], mock_sleep.call_args_list)
        mock_remove.assert_not_called()

    def test_failed_start_rollback_retries_for_delayed_container_creation(self):
        from kvmagent.plugins.tensorfusion.container_executor import (
            ContainerExecutor, DockerCommandError)

        executor = ContainerExecutor(_make_gpu_details())
        executor.ROLLBACK_RETRY_WINDOW_SEC = 1
        now = [10.0]

        def _time():
            return now[0]

        def _sleep(seconds):
            now[0] += seconds

        not_found = DockerCommandError(
            1, 'docker rm -f tf-worker-vm-001',
            'Error: No such container: tf-worker-vm-001')

        with mock.patch.object(
                executor, '_docker',
                side_effect=[not_found, 'tf-worker-vm-001', not_found]) as mock_docker, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.time.time',
                           side_effect=_time), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.time.sleep',
                           side_effect=_sleep) as mock_sleep, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            removed = executor._rollback_failed_start(
                'tf-worker-vm-001', '/dev/shm/tf_dev-001')

        self.assertTrue(removed)
        self.assertEqual([
            mock.call(['rm', '-f', 'tf-worker-vm-001'], timeout=1),
            mock.call(['rm', '-f', 'tf-worker-vm-001'], timeout=1),
            mock.call(['rm', '-f', 'tf-worker-vm-001'], timeout=1),
        ], mock_docker.call_args_list)
        self.assertEqual([
            mock.call(0.5),
            mock.call(0.5),
        ], mock_sleep.call_args_list)
        mock_remove.assert_called_once_with('/dev/shm/tf_dev-001')

    def test_stop_succeeds_when_shared_memory_cleanup_fails(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        worker = _make_worker()
        worker.container_id = 'container-id'
        worker.container_name = 'tf-worker-vm-001'
        worker.shared_memory_path = '/dev/shm/tf_dev-001'
        executor = ContainerExecutor(_make_gpu_details())

        with mock.patch.object(executor, '_docker', return_value='') as mock_docker, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove',
                           side_effect=OSError(errno.EPERM, 'permission denied')) as mock_remove:
            executor.stop(worker)

        self.assertEqual([
            mock.call(['stop', '-t', '5', 'container-id']),
            mock.call(['rm', '-f', 'container-id']),
        ], mock_docker.call_args_list)
        mock_remove.assert_called_once_with('/dev/shm/tf_dev-001')

    def test_reap_dead_preserves_container_that_is_running_again(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        worker = _make_worker()
        worker.container_id = 'container-id'
        worker.container_name = 'tf-worker-vm-001'
        worker.shared_memory_path = '/dev/shm/tf_dev-001'
        executor = ContainerExecutor(_make_gpu_details())

        with mock.patch.object(executor, 'is_alive', return_value=True), \
                mock.patch.object(executor, '_docker') as mock_docker, \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            self.assertFalse(executor.reap_dead(worker))

        mock_docker.assert_not_called()
        mock_remove.assert_not_called()

    def test_reap_dead_uses_deterministic_shared_memory_fallback(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        worker = _make_worker(device_uuid='dev-fallback')
        worker.container_id = 'container-id'
        worker.container_name = 'tf-worker-vm-001'
        worker.shared_memory_path = None
        executor = ContainerExecutor(_make_gpu_details())

        with mock.patch.object(executor, 'is_alive', return_value=False), \
                mock.patch.object(executor, '_docker'), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            self.assertTrue(executor.reap_dead(worker))

        mock_remove.assert_called_once_with('/dev/shm/tf_dev-fallback')

    def test_residual_cleanup_does_not_trust_reused_container_name(self):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        known = _make_worker()
        known.container_id = 'old-container-id'
        known.container_name = 'tf-worker-vm-001'
        executor = ContainerExecutor(_make_gpu_details())

        info = {
            'Id': 'new-container-id',
            'Name': '/tf-worker-vm-001',
            'Config': {'Env': ['TF_DEVICE_UUID=dev-residual']},
        }

        def _docker(args, timeout=None, env=None):
            if args[0:2] == ['ps', '-aq']:
                return 'new-container-id'
            return ''

        with mock.patch.object(executor, '_docker', side_effect=_docker) as mock_docker, \
                mock.patch.object(executor, '_inspect_container', return_value=info), \
                mock.patch('kvmagent.plugins.tensorfusion.container_executor.os.remove') as mock_remove:
            self.assertEqual(
                1, executor.cleanup_residual_workers_by_vm('vm-001', known_workers=[known]))

        self.assertIn(
            mock.call(['rm', '-f', 'new-container-id']), mock_docker.call_args_list)
        mock_remove.assert_called_once_with('/dev/shm/tf_dev-residual')

    def test_command_for_log_masks_license_values(self):
        from kvmagent.plugins.tensorfusion.container_executor import _command_for_log, _redact_sensitive_values

        args = [
            'docker', 'run',
            '-e', 'TF_LICENSE=secret-license',
            '-e', 'TF_LICENSE_SIGN=secret-signature',
            '-e', 'TF_GPU_MEMORY_LIMIT=8192',
            'tf-worker:latest',
        ]
        command = _command_for_log(args)
        stderr = _redact_sensitive_values(
            'invalid secret-license and secret-signature', args)
        overlapping = _redact_sensitive_values(
            'prefix-and-prefix-suffix',
            ['TF_LICENSE=prefix', 'TF_LICENSE_SIGN=prefix-suffix'])

        self.assertNotIn('secret-license', command)
        self.assertNotIn('secret-signature', command)
        self.assertNotIn('secret-license', stderr)
        self.assertNotIn('secret-signature', stderr)
        self.assertEqual('*****-and-*****', overlapping)
        self.assertIn('TF_LICENSE=*****', command)
        self.assertIn('TF_LICENSE_SIGN=*****', command)
        self.assertIn('TF_GPU_MEMORY_LIMIT=8192', command)

    @mock.patch('kvmagent.plugins.tensorfusion.container_executor.subprocess.Popen')
    def test_timeout_error_has_no_sensitive_context(self, mock_popen):
        import subprocess
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        proc = mock_popen.return_value
        proc.communicate.side_effect = subprocess.TimeoutExpired(
            ['docker', 'run', '-e', 'TF_LICENSE'], 30)
        proc.kill.side_effect = RuntimeError('kill failed')
        proc.wait.side_effect = RuntimeError('wait failed')

        executor = ContainerExecutor(_make_gpu_details())
        with self.assertRaises(Exception) as ctx:
            executor._docker(
                ['run', '-e', 'TF_LICENSE'], timeout=30,
                env={'TF_LICENSE': 'secret-license'})

        self.assertNotIn('secret-license', str(ctx.exception))
        self.assertIsNone(ctx.exception.__context__)
        proc.kill.assert_called_once_with()
        proc.wait.assert_called_once_with(timeout=5)
        self.assertNotIn('secret-license', ' '.join(mock_popen.call_args[0][0]))
        self.assertEqual(
            'secret-license', mock_popen.call_args[1]['env']['TF_LICENSE'])

    @mock.patch('kvmagent.plugins.tensorfusion.container_executor.subprocess.Popen')
    def test_nonzero_error_redacts_command_and_stderr(self, mock_popen):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        proc = mock_popen.return_value
        proc.communicate.return_value = (b'', b'invalid secret-license')
        proc.returncode = 1

        executor = ContainerExecutor(_make_gpu_details())
        with self.assertRaises(Exception) as ctx:
            executor._docker(
                ['run', '-e', 'TF_LICENSE'],
                env={'TF_LICENSE': 'secret-license'})

        self.assertNotIn('secret-license', str(ctx.exception))
        self.assertNotIn('secret-license', ' '.join(mock_popen.call_args[0][0]))
        self.assertEqual(
            'secret-license', mock_popen.call_args[1]['env']['TF_LICENSE'])

    @mock.patch('kvmagent.plugins.tensorfusion.container_executor.subprocess.Popen')
    def test_docker_env_does_not_mutate_process_environment(self, mock_popen):
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        proc = mock_popen.return_value
        proc.communicate.return_value = (b'container-id', b'')
        proc.returncode = 0
        executor = ContainerExecutor(_make_gpu_details())

        with mock.patch.dict(os.environ, {'EXISTING': 'unchanged'}, clear=True):
            result = executor._docker(
                ['run', '-e', 'TF_LICENSE', '-e', 'TF_LICENSE_SIGN'],
                env={
                    'TF_LICENSE': 'secret-license',
                    'TF_LICENSE_SIGN': 'secret-signature',
                })
            self.assertEqual({'EXISTING': 'unchanged'}, dict(os.environ))

        self.assertEqual('container-id', result)
        popen_cmd = mock_popen.call_args[0][0]
        popen_env = mock_popen.call_args[1]['env']
        self.assertNotIn('secret-license', ' '.join(popen_cmd))
        self.assertNotIn('secret-signature', ' '.join(popen_cmd))
        self.assertEqual('unchanged', popen_env['EXISTING'])
        self.assertEqual('secret-license', popen_env['TF_LICENSE'])
        self.assertEqual('secret-signature', popen_env['TF_LICENSE_SIGN'])

    @mock.patch('kvmagent.plugins.tensorfusion.container_executor.subprocess.Popen')
    def test_class_timeout_error_has_no_sensitive_context(self, mock_popen):
        import subprocess
        from kvmagent.plugins.tensorfusion.container_executor import ContainerExecutor

        proc = mock_popen.return_value
        proc.communicate.side_effect = subprocess.TimeoutExpired(
            ['docker', 'run', '-e', 'TF_LICENSE'], 30)
        proc.kill.side_effect = RuntimeError('kill failed')
        proc.wait.side_effect = RuntimeError('wait failed')

        with self.assertRaises(Exception) as ctx:
            ContainerExecutor._docker_class(
                ['run', '-e', 'TF_LICENSE'], timeout=30,
                env={'TF_LICENSE': 'secret-license'})

        self.assertNotIn('secret-license', str(ctx.exception))
        self.assertIsNone(ctx.exception.__context__)
        proc.kill.assert_called_once_with()
        proc.wait.assert_called_once_with(timeout=5)


class TestTensorFusionPluginSensitiveLogging(unittest.TestCase):

    def test_create_worker_masks_request_and_error_credentials(self):
        from zstacklib.utils import http, log
        from kvmagent.plugins.tensorfusion import plugin as plugin_module

        body = json.dumps({
            'vmUuid': 'vm-test',
            'pciAddress': '0000:3b:00.0',
            'memoryMb': 8192,
            'shmemSize': 268435456,
            'license': 'secret-license',
            'licenseSign': 'secret-signature',
            'enableLog': False,
            'logLevel': 'error',
            'deviceUuid': 'dev-test',
            'protocol': 'shmem',
            'smPercentLimit': 33,
        })
        masked_request = log.mask_sensitive_field(plugin_module.CreateWorkerCmd(), body)

        tensorfusion_plugin = plugin_module.TensorFusionPlugin()
        tensorfusion_plugin._service = mock.MagicMock()
        tensorfusion_plugin._service.create_worker.side_effect = Exception(
            'failed secret-license / secret-signature')

        with mock.patch.object(plugin_module, 'logger') as mock_logger:
            response = tensorfusion_plugin.create_worker({http.REQUEST_BODY: body})

        warning = mock_logger.warn.call_args[0][0]
        self.assertNotIn('secret-license', masked_request)
        self.assertNotIn('secret-signature', masked_request)
        self.assertNotIn('secret-license', response)
        self.assertNotIn('secret-signature', response)
        self.assertNotIn('secret-license', warning)
        self.assertNotIn('secret-signature', warning)
        self.assertFalse(json.loads(response)['success'])


class TestProcessExecutor(unittest.TestCase):

    def _import_without_psutil(self, name, *args, **kwargs):
        if name == 'psutil':
            raise ImportError('psutil unavailable')
        return self._real_import(name, *args, **kwargs)

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.path.exists', return_value=False)
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.killpg')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.getpgid')
    def test_stop_waits_for_worker_exit(self, mock_getpgid, mock_killpg, _mock_exists, _mock_sleep):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

        mock_getpgid.side_effect = [1234, 1234, OSError(3, 'No such process')]
        executor = ProcessExecutor(_make_gpu_details())
        worker = _make_worker(pid=5678)

        self.assertTrue(executor.stop(worker))
        mock_killpg.assert_called_once_with(1234, mock.ANY)
        self.assertEqual(mock_getpgid.call_count, 3)

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.path.exists', return_value=False)
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.killpg')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.getpgid')
    def test_stop_reaps_tracked_process(self, mock_getpgid, mock_killpg, _mock_exists, _mock_sleep):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

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

    def test_reap_dead_keeps_running_tracked_process(self):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

        proc = mock.MagicMock()
        proc.pid = 5678
        proc.poll.return_value = None
        executor = ProcessExecutor(_make_gpu_details())
        executor._track_proc(proc)

        self.assertFalse(executor.reap_dead(_make_worker(pid=5678)))
        proc.wait.assert_not_called()
        self.assertIs(proc, executor._get_proc(5678))

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.waitpid',
                return_value=(0, 0))
    def test_reap_dead_keeps_running_untracked_child(self, mock_waitpid):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

        executor = ProcessExecutor(_make_gpu_details())

        self.assertFalse(executor.reap_dead(_make_worker(pid=5678)))
        mock_waitpid.assert_called_once_with(5678, os.WNOHANG)

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.waitpid',
                side_effect=OSError(errno.ECHILD, 'not a child'))
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.kill')
    def test_reap_dead_accepts_untracked_zombie(self, mock_kill, mock_waitpid):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

        executor = ProcessExecutor(_make_gpu_details())
        with mock.patch.object(executor, '_is_linux_zombie', return_value=True), \
                mock.patch.object(executor, '_verify_worker_pid') as mock_verify:
            self.assertTrue(executor.reap_dead(_make_worker(pid=5678)))

        mock_waitpid.assert_called_once_with(5678, os.WNOHANG)
        mock_kill.assert_called_once_with(5678, 0)
        mock_verify.assert_not_called()

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.time.time')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.path.exists', return_value=False)
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.killpg')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.getpgid')
    def test_stop_raises_when_worker_does_not_exit(self, mock_getpgid, mock_killpg, _mock_exists, mock_time, _mock_sleep):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

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
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

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

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.subprocess.Popen')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.time.time')
    @mock.patch(BUILTINS_MODULE + '.open', new_callable=mock.mock_open)
    def test_start_polls_process_during_startup_window(self, _mock_open, mock_time, mock_sleep, mock_popen):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

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

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.subprocess.Popen')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.time.sleep')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.time.time')
    @mock.patch(BUILTINS_MODULE + '.open', new_callable=mock.mock_open)
    def test_start_defaults_enable_log_consistently(self, _mock_open, mock_time, _mock_sleep, mock_popen):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

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

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.kill')
    def test_is_alive_fallback_treats_linux_zombie_as_dead(self, mock_kill):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

        self._real_import = builtins.__import__
        worker = _make_worker(pid=5678)
        stat_content = '5678 (tensor-fusion-worker) Z 1 2 3 4 5'

        with mock.patch('builtins.__import__', side_effect=self._import_without_psutil):
            with mock.patch(BUILTINS_MODULE + '.open', mock.mock_open(read_data=stat_content)):
                self.assertFalse(ProcessExecutor.is_alive(worker))

        mock_kill.assert_called_once_with(5678, 0)

    def test_scan_running_prefers_pci_address_from_environment(self):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

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
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

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
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

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

    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.ProcessExecutor._wait_for_exit', return_value=True)
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.path.exists', return_value=False)
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.killpg')
    @mock.patch('kvmagent.plugins.tensorfusion.process_executor.os.getpgid')
    def test_cleanup_residual_workers_by_vm_kills_untracked_process_group_once(self, mock_getpgid, mock_killpg, _mock_exists, _mock_wait):
        from kvmagent.plugins.tensorfusion.process_executor import ProcessExecutor

        class _FakeProc(object):
            def __init__(self, pid, env):
                self.pid = pid
                self._env = env

            @staticmethod
            def name():
                return 'tensor-fusion-worker'

            @staticmethod
            def cmdline():
                return ['tensor-fusion-worker', '-n', 'shmem', '-m', '/tf_dev-001', '-M', '1024']

            def environ(self):
                return self._env

        fake_psutil = types.ModuleType('psutil')
        fake_psutil.AccessDenied = type('AccessDenied', (Exception,), {})
        fake_psutil.NoSuchProcess = type('NoSuchProcess', (Exception,), {})
        fake_psutil.ZombieProcess = type('ZombieProcess', (Exception,), {})
        fake_psutil.process_iter = lambda: [
            _FakeProc(4321, {'VM_UUID': 'vm-001', 'TF_DEVICE_UUID': 'dev-001'}),
            _FakeProc(4322, {'VM_UUID': 'vm-001', 'TF_DEVICE_UUID': 'dev-002'}),
            _FakeProc(5321, {'VM_UUID': 'vm-002', 'TF_DEVICE_UUID': 'dev-003'}),
        ]

        pgids = {
            4321: 9001,
            4322: 9001,
        }

        def _getpgid(pid):
            value = pgids[pid]
            return value

        mock_getpgid.side_effect = _getpgid

        with mock.patch.dict(sys.modules, {'psutil': fake_psutil}):
            executor = ProcessExecutor(_make_gpu_details())
            cleaned = executor.cleanup_residual_workers_by_vm(
                'vm-001', known_workers=[_make_worker(pid=1234)])

        self.assertEqual(1, cleaned)
        mock_killpg.assert_called_once_with(9001, mock.ANY)


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

        with mock.patch('kvmagent.plugins.tensorfusion.utils.is_vm_running', return_value=True):
            monitor._do_restart(worker, 0)

        executor.stop.assert_called_once_with(restarted)
        self.assertIsNone(store.get(worker.device_uuid))


# =============================================================================
# Orphan scan tests
# =============================================================================

class TestOrphanScan(unittest.TestCase):
    """Tests for TensorFusionService._scan_and_cleanup_orphans."""

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_orphan_scan_kills_tracked_worker_whose_vm_is_gone(self, MockExecutor, MockNVIDIA):
        """A tracked worker whose VM is no longer running should be killed."""
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = MockExecutor.return_value
        mock_executor.cleanup_residual_workers_by_vm.return_value = 0
        mock_executor.scan_running.return_value = []
        mock_executor.is_alive.return_value = True
        mock_executor.stop.return_value = True

        created_worker = _make_worker()
        mock_executor.start.return_value = created_worker

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=True):
            svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        svc.create_worker(req)

        # Now simulate VM gone; scan_running still sees the process
        mock_executor.is_alive.return_value = False
        mock_executor.scan_running.return_value = [created_worker]
        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=False):
            svc._scan_and_cleanup_orphans()

        mock_executor.stop.assert_called_with(created_worker)
        # Worker should be removed from state
        self.assertIsNone(svc.get_worker('dev-001'))

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_orphan_scan_keeps_worker_whose_vm_is_running(self, MockExecutor, MockNVIDIA):
        """A tracked worker whose VM is still running should NOT be killed."""
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = MockExecutor.return_value
        mock_executor.cleanup_residual_workers_by_vm.return_value = 0
        mock_executor.scan_running.return_value = []
        mock_executor.is_alive.return_value = True
        mock_executor.stop.return_value = True

        created_worker = _make_worker()
        mock_executor.start.return_value = created_worker

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=True):
            svc.initialize()

        req = WorkerCreateRequest()
        req.vm_uuid = 'vm-001'
        req.pci_address = '0000:3b:00.0'
        req.memory_mb = 1024
        req.device_uuid = 'dev-001'
        req.license = TEST_LICENSE
        req.license_sign = TEST_LICENSE_SIGN
        svc.create_worker(req)

        # VM still running; scan_running sees the process
        mock_executor.scan_running.return_value = [created_worker]
        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=True):
            svc._scan_and_cleanup_orphans()

        # stop should not have been called for cleanup
        self.assertIsNotNone(svc.get_worker('dev-001'))

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_orphan_scan_kills_untracked_worker_whose_vm_is_gone(self, MockExecutor, MockNVIDIA):
        """An untracked worker process (not in StateStore) whose VM is gone should be killed."""
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = MockExecutor.return_value
        mock_executor.cleanup_residual_workers_by_vm.return_value = 0
        mock_executor.is_alive.return_value = True
        mock_executor.stop.return_value = True

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()

        # No tracked workers at init
        mock_executor.scan_running.return_value = []
        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=True):
            svc.initialize()

        # Simulate an untracked worker process discovered during scan
        orphan_worker = _make_worker(device_uuid='orphan-001', vm_uuid='vm-gone', pid=9999)
        mock_executor.scan_running.return_value = [orphan_worker]

        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=False):
            svc._scan_and_cleanup_orphans()

        mock_executor.stop.assert_called_with(orphan_worker)

    def test_orphan_scan_keeps_untracked_worker_when_vm_running_or_unknown(self):
        """Untracked runtimes are not killed without a definitive absent VM."""
        mock_executor = mock.MagicMock()
        orphan_worker = _make_worker(device_uuid='orphan-002', vm_uuid='vm-unknown', pid=8888)
        mock_executor.scan_running.return_value = [orphan_worker]

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService(executor=mock_executor)

        with mock.patch(
                'kvmagent.plugins.tensorfusion.service._is_vm_running',
                side_effect=[True, None]):
            svc._scan_and_cleanup_orphans()
            svc._scan_and_cleanup_orphans()

        mock_executor.stop.assert_not_called()

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_orphan_scan_timer_starts_and_stops(self, MockExecutor, MockNVIDIA):
        """Verify the orphan scan timer thread starts on initialize and stops on stop()."""
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = MockExecutor.return_value
        mock_executor.cleanup_residual_workers_by_vm.return_value = 0
        mock_executor.scan_running.return_value = []

        # Count scan threads before
        before = len([t for t in threading.enumerate() if t.name == 'tf-orphan-scan'])

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        # Use a very short interval for testing
        svc.ORPHAN_SCAN_INTERVAL_SEC = 0.1

        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=True):
            svc.initialize()

        # Check that one more orphan scan thread is running
        after = len([t for t in threading.enumerate() if t.name == 'tf-orphan-scan'])
        self.assertEqual(after, before + 1)

        svc.stop()
        # Give thread time to notice the stop event
        time.sleep(0.3)
        stopped = len([t for t in threading.enumerate() if t.name == 'tf-orphan-scan'])
        self.assertEqual(stopped, before)

    @mock.patch('kvmagent.plugins.tensorfusion.service.NVIDIA')
    @mock.patch('kvmagent.plugins.tensorfusion.service.ProcessExecutor')
    def test_orphan_scan_timer_can_restart_after_stop(self, MockExecutor, MockNVIDIA):
        MockNVIDIA.query_gpu_details.return_value = _make_gpu_details()

        mock_executor = MockExecutor.return_value
        mock_executor.cleanup_residual_workers_by_vm.return_value = 0
        mock_executor.scan_running.return_value = []

        from kvmagent.plugins.tensorfusion.service import TensorFusionService
        svc = TensorFusionService()
        svc.ORPHAN_SCAN_INTERVAL_SEC = 0.1

        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=True):
            svc.initialize()

        first_thread = svc._orphan_scan_thread
        self.assertIsNotNone(first_thread)
        self.assertTrue(first_thread.is_alive())

        svc.stop()
        time.sleep(0.2)
        self.assertFalse(first_thread.is_alive())

        with mock.patch('kvmagent.plugins.tensorfusion.service._is_vm_running', return_value=True):
            svc.initialize()

        second_thread = svc._orphan_scan_thread
        self.assertIsNotNone(second_thread)
        self.assertIsNot(first_thread, second_thread)
        self.assertTrue(second_thread.is_alive())

        svc.stop()


if __name__ == '__main__':
    unittest.main()

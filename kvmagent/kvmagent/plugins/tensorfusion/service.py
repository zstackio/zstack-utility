'''
TensorFusionService - facade that orchestrates all components.

@author: tensorfusion
'''

import threading

from zstacklib.utils import log
from zstacklib.utils.pci import normalize_pci_address
from zstacklib.gpu.vendors.nvidia import NVIDIA

from kvmagent.plugins.tensorfusion.models import WorkerCreateRequest, GPUHardwareInfo
from kvmagent.plugins.tensorfusion.store import StateStore
from kvmagent.plugins.tensorfusion.tracker import ResourceTracker
from kvmagent.plugins.tensorfusion.executor import ProcessExecutor
from kvmagent.plugins.tensorfusion.monitor import WorkerRestartMonitor

logger = log.get_logger(__name__)


from kvmagent.plugins.tensorfusion.utils import is_vm_running  # noqa: F401

DEFAULT_ENABLE_LOG = ProcessExecutor.DEFAULT_ENABLE_LOG
DEFAULT_LOG_LEVEL = ProcessExecutor.DEFAULT_LOG_LEVEL
BYTES_PER_MB = ProcessExecutor.BYTES_PER_MB
DEFAULT_SHMEM_SIZE = ProcessExecutor.SHM_SIZE


class TensorFusionService(object):
    """High-level facade for TensorFusion Worker lifecycle management."""

    def __init__(self, event_notifier=None):
        self._gpu_details = {}
        self._store = StateStore()
        self._tracker = ResourceTracker(self._gpu_details)
        self._executor = ProcessExecutor(self._gpu_details)
        self._monitor = WorkerRestartMonitor(self._store, self._executor, self._tracker,
                                             event_notifier=event_notifier,
                                             restart_worker=self.restart_worker)
        self._create_lock_guard = threading.RLock()
        self._create_locks = {}
        self.refresh_gpu_details()

    def initialize(self):
        """Initialize the service: scan running workers, rebuild state."""
        logger.info('TensorFusionService: initializing')
        running = self._executor.scan_running()

        # Kill orphan workers whose VM is no longer running in libvirt.
        # is_vm_running returns True/False/None; None means libvirt query
        # failed — keep the worker alive to avoid killing healthy processes.
        alive = []
        for w in running:
            vm_state = is_vm_running(w.vm_uuid)
            if vm_state is False:
                logger.warn('TensorFusionService: killing orphan worker %s '
                            '(pid=%d, vm=%s not running)' % (w.device_uuid, w.pid, w.vm_uuid))
                try:
                    self._executor.stop(w)
                except Exception as e:
                    logger.warn('TensorFusionService: failed to stop orphan worker %s: %s' %
                                (w.device_uuid, e))
                    if self._executor.is_alive(w):
                        logger.warn('TensorFusionService: orphan worker %s still alive, keeping in state' %
                                    w.device_uuid)
                        alive.append(w)
            else:
                if vm_state is None:
                    logger.warn('TensorFusionService: cannot check VM %s, keeping worker %s' %
                                (w.vm_uuid, w.device_uuid))
                alive.append(w)

        self._store.sync(alive)
        self._tracker.rebuild_from_workers(alive)
        logger.info('TensorFusionService: initialized with %d running workers '
                     '(%d orphans cleaned)' % (len(alive), len(running) - len(alive)))
        self._monitor.start()

    def stop(self):
        self._monitor.stop()

    def _remove_worker_state(self, worker):
        removed = self._store.remove(worker.device_uuid, expected_worker=worker)
        if removed is None:
            logger.info('TensorFusionService: worker %s changed before state cleanup, skipping stale cleanup' %
                        worker.device_uuid)
            return

        self._monitor.clear(worker.device_uuid)
        self._tracker.release(worker.pci_address, worker.device_uuid)

    @staticmethod
    def _validate_request_license(request):
        if not request.license or not request.license_sign:
            raise Exception('tensor-fusion license is required, provide request.license/request.licenseSign')

    @staticmethod
    def _validate_request_resources(request):
        if request.memory_mb < 0:
            raise Exception('request.memory_mb must be >= 0, got %s' % request.memory_mb)
        if request.shmem_size < 0:
            raise Exception('request.shmem_size must be >= 0, got %s' % request.shmem_size)
        if request.sm_percent_limit < 0:
            raise Exception('request.sm_percent_limit must be >= 0, got %s' % request.sm_percent_limit)

    @staticmethod
    def _normalize_pci_address(pci_address):
        normalized = normalize_pci_address(pci_address)
        return normalized or pci_address

    def refresh_gpu_details(self):
        # type: () -> bool
        try:
            gpu_details = NVIDIA.query_gpu_details()
        except Exception as e:
            logger.warn('TensorFusionService: failed to query GPU details, continuing with current inventory: %s' % e)
            return False

        self._gpu_details.clear()
        self._gpu_details.update(gpu_details)
        self._tracker.refresh_gpu_details(self._gpu_details)
        return True

    def _get_create_lock(self, pci_address):
        with self._create_lock_guard:
            lock = self._create_locks.get(pci_address)
            if lock is None:
                lock = threading.Lock()
                self._create_locks[pci_address] = lock
            return lock

    def create_worker(self, request):
        # type: (WorkerCreateRequest) -> object
        """Create and start a new worker. Returns Worker."""
        request.ensure_device_uuid()
        self._validate_request_license(request)
        self._validate_request_resources(request)
        request.pci_address = self._normalize_pci_address(request.pci_address)
        pci = request.pci_address
        create_lock = self._get_create_lock(pci)
        with create_lock:
            if not self._gpu_details or pci not in self._gpu_details:
                self.refresh_gpu_details()

            existing = self._store.get(request.device_uuid)
            if existing:
                if self._executor.is_alive(existing):
                    if self._is_same_worker_request(existing, request):
                        logger.warn('TensorFusionService: worker %s already running for VM %s, reusing existing process' %
                                    (request.device_uuid, request.vm_uuid))
                        return existing

                    raise Exception('worker %s already exists for vm %s on %s' %
                                    (request.device_uuid, existing.vm_uuid, existing.pci_address))

                self._monitor.clear(request.device_uuid)
                self._tracker.release(existing.pci_address, request.device_uuid)
                self._store.remove(request.device_uuid)

            if not self._tracker.can_allocate(pci, request.memory_mb):
                avail = self._tracker.get_available_memory(pci)
                raise Exception('insufficient GPU memory on %s: requested %dMB, available %dMB' %
                                (pci, request.memory_mb, avail))

            worker = self._executor.start(request)
            try:
                self._store.add(worker)
                self._tracker.allocate(pci, worker.device_uuid, worker.allocated_memory_mb)
            except Exception:
                try:
                    self._executor.stop(worker)
                except Exception as stop_error:
                    logger.warn('TensorFusionService: failed to rollback worker %s after create error: %s' % (
                        request.device_uuid, stop_error))
                try:
                    self._store.remove(worker.device_uuid)
                except Exception as remove_error:
                    logger.warn('TensorFusionService: failed to remove worker %s from state store after create error: %s' % (
                        request.device_uuid, remove_error))
                try:
                    self._tracker.release(pci, worker.device_uuid)
                except Exception as release_error:
                    logger.warn('TensorFusionService: failed to release worker %s tracker allocation after create error: %s' % (
                        request.device_uuid, release_error))
                raise

        logger.info('TensorFusionService: created worker %s on %s for VM %s' %
                     (worker.device_uuid, pci, worker.vm_uuid))
        return worker

    @staticmethod
    def _build_restart_request(worker):
        req = WorkerCreateRequest()
        req.device_uuid = worker.device_uuid
        req.vm_uuid = worker.vm_uuid
        req.pci_address = worker.pci_address
        req.memory_mb = worker.allocated_memory_mb
        req.shmem_size = worker.shared_memory_size
        req.license = worker.license
        req.license_sign = worker.license_sign
        req.enable_log = worker.enable_log
        req.log_level = worker.log_level
        req.protocol = worker.protocol
        req.sm_percent_limit = worker.sm_percent_limit
        return req

    def restart_worker(self, current_worker):
        # type: (object) -> object
        """Restart an existing worker under the service's per-GPU create lock."""
        req = self._build_restart_request(current_worker)
        self._validate_request_license(req)
        self._validate_request_resources(req)
        req.pci_address = self._normalize_pci_address(req.pci_address)
        pci = req.pci_address
        create_lock = self._get_create_lock(pci)
        with create_lock:
            if not self._gpu_details or pci not in self._gpu_details:
                self.refresh_gpu_details()
            if pci not in self._gpu_details:
                raise Exception('GPU %s not found via nvidia-smi' % pci)

            existing = self._store.get(current_worker.device_uuid)
            if existing is not current_worker:
                return None

            new_worker = self._executor.start(req)
            new_worker.restarting = False
            replaced = self._store.replace(new_worker, expected_worker=current_worker)
            if replaced is None:
                try:
                    self._executor.stop(new_worker)
                except Exception as stop_error:
                    logger.warn('TensorFusionService: failed to stop orphan worker %s after restart CAS miss: %s' % (
                        current_worker.device_uuid, stop_error))
                return None

        logger.info('TensorFusionService: restarted worker %s on %s for VM %s (new pid=%d)' % (
            new_worker.device_uuid, pci, new_worker.vm_uuid, new_worker.pid))
        return new_worker

    def _is_same_worker_request(self, worker, request):
        # type: (object, WorkerCreateRequest) -> bool
        expected_protocol = request.protocol or 'shmem'
        expected_shmem_size = request.shmem_size if request.shmem_size > 0 else (
            request.memory_mb * BYTES_PER_MB if request.memory_mb > 0 else DEFAULT_SHMEM_SIZE
        )
        expected_shmem_size = ProcessExecutor._bytes_to_mb(expected_shmem_size) * BYTES_PER_MB
        expected_enable_log = request.enable_log if request.enable_log is not None else DEFAULT_ENABLE_LOG
        expected_log_level = request.log_level or DEFAULT_LOG_LEVEL

        return (
            worker.vm_uuid == request.vm_uuid and
            self._normalize_pci_address(worker.pci_address) == self._normalize_pci_address(request.pci_address) and
            worker.protocol == expected_protocol and
            worker.allocated_memory_mb == request.memory_mb and
            worker.shared_memory_size == expected_shmem_size and
            worker.sm_percent_limit == request.sm_percent_limit and
            worker.license == request.license and
            worker.license_sign == request.license_sign and
            worker.enable_log == expected_enable_log and
            worker.log_level == expected_log_level
        )

    def destroy_worker(self, device_uuid):
        # type: (str) -> bool
        """Stop and remove a worker by device_uuid."""
        worker = self._store.get(device_uuid)
        if not worker:
            logger.warn('TensorFusionService: worker %s not found' % device_uuid)
            return False

        try:
            self._executor.stop(worker)
        except Exception:
            if not self._executor.is_alive(worker):
                self._remove_worker_state(worker)
            raise

        self._remove_worker_state(worker)

        logger.info('TensorFusionService: destroyed worker %s' % device_uuid)
        return True

    def destroy_workers_by_vm(self, vm_uuid):
        # type: (str) -> int
        """Destroy all workers belonging to a VM. Returns count destroyed."""
        workers = self._store.list_by_vm(vm_uuid)
        count = 0
        failures = []
        for w in workers:
            try:
                destroyed = self.destroy_worker(w.device_uuid)
            except Exception as e:
                failures.append('%s: %s' % (w.device_uuid, str(e)))
                continue
            if destroyed:
                count += 1

        if failures:
            raise Exception('failed to destroy some workers for VM %s: %s' %
                            (vm_uuid, '; '.join(failures)))

        logger.info('TensorFusionService: destroyed %d workers for VM %s' % (count, vm_uuid))
        return count

    def get_worker(self, device_uuid):
        """Get a worker by device_uuid with passive health check."""
        worker = self._store.get(device_uuid)
        if worker and not self._executor.is_alive(worker):
            logger.warn('TensorFusionService: worker %s (pid=%d) is dead, cleaning up' %
                        (device_uuid, worker.pid))
            self._remove_worker_state(worker)
            return None
        return worker

    def list_workers(self):
        return self._store.list_all()

    def list_workers_by_vm(self, vm_uuid):
        return self._store.list_by_vm(vm_uuid)

    def list_workers_by_gpu(self, pci_address):
        return self._store.list_by_gpu(pci_address)

    def get_gpu_usage(self, pci_address):
        workers = self._store.list_by_gpu(pci_address)
        return self._tracker.get_gpu_usage(pci_address, workers)

    def get_all_gpu_usage(self):
        all_workers = self._store.list_all()
        by_gpu = {}
        for w in all_workers:
            by_gpu.setdefault(w.pci_address, []).append(w)
        return self._tracker.get_all_gpu_usage(by_gpu)

    def check_worker_health(self, device_uuid):
        # type: (str) -> bool
        worker = self._store.get(device_uuid)
        if not worker:
            return False
        return self._executor.is_alive(worker)

    def cleanup_dead_workers(self):
        # type: () -> list
        """Remove dead workers from state. Returns list of cleaned-up device_uuids."""
        cleaned = []
        for w in self._store.list_all():
            if not self._executor.is_alive(w):
                logger.warn('TensorFusionService: cleaning up dead worker %s (pid=%d)' %
                            (w.device_uuid, w.pid))
                self._remove_worker_state(w)
                cleaned.append(w.device_uuid)
        if cleaned:
            logger.info('TensorFusionService: cleaned up %d dead workers' % len(cleaned))
        return cleaned

    def list_gpu_hardware(self):
        # type: () -> list
        """Return list of GPUHardwareInfo from nvidia-smi data."""
        if not self._gpu_details:
            self.refresh_gpu_details()

        result = []
        for detail in self._gpu_details.values():
            info = GPUHardwareInfo()
            info.pci_address = detail['pci_address']
            info.cuda_index = detail['cuda_index']
            info.name = detail['name']
            info.total_memory_mb = detail['total_memory_mb']
            info.driver_version = detail['driver_version']
            result.append(info)
        return result

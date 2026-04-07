'''
GPU resource quota tracking for TensorFusion.

@author: tensorfusion
'''

import threading

from zstacklib.utils import log
from zstacklib.utils.pci import normalize_pci_address

from kvmagent.plugins.tensorfusion.models import GPUResourceInfo

logger = log.get_logger(__name__)


class GPUAllocation(object):
    """Tracks memory allocations on a single GPU."""

    def __init__(self, pci_address, total_memory_mb):
        self.pci_address = pci_address
        self.total_memory_mb = total_memory_mb
        self.allocations = {}  # {device_uuid: memory_mb}

    @property
    def allocated_memory_mb(self):
        return sum(self.allocations.values())

    @property
    def available_memory_mb(self):
        return self.total_memory_mb - self.allocated_memory_mb

    @property
    def worker_count(self):
        return len(self.allocations)


class ResourceTracker(object):
    """Thread-safe GPU resource quota tracker."""

    def __init__(self, gpu_details):
        """
        Args:
            gpu_details: dict {pci_address: detail_dict} from NVIDIA.query_gpu_details().
        """
        self._gpu_details = {}
        for pci_address, detail in gpu_details.items():
            normalized = self._normalize_pci_address(pci_address)
            self._gpu_details[normalized] = detail
        self._lock = threading.RLock()
        self._gpus = {}  # {pci_address: GPUAllocation}
        self._sync_gpu_allocations_locked()

    @staticmethod
    def _normalize_pci_address(pci_address):
        normalized = normalize_pci_address(pci_address)
        return normalized or pci_address

    def _ensure_gpu(self, pci_address):
        """Ensure a GPUAllocation entry exists for the given GPU."""
        normalized = self._normalize_pci_address(pci_address)
        if normalized not in self._gpus:
            detail = self._gpu_details.get(normalized)
            if detail:
                total = detail['total_memory_mb']
            else:
                logger.warning('ResourceTracker: unknown GPU %s, defaulting total_memory to 0' % normalized)
                total = 0
            self._gpus[normalized] = GPUAllocation(normalized, total)
        return normalized

    def _sync_gpu_allocations_locked(self):
        for pci_address, detail in self._gpu_details.items():
            gpu = self._gpus.get(pci_address)
            if gpu is None:
                self._gpus[pci_address] = GPUAllocation(pci_address, detail['total_memory_mb'])
            else:
                gpu.total_memory_mb = detail['total_memory_mb']

    def refresh_gpu_details(self, gpu_details):
        """Refresh GPU inventory while keeping current allocation state."""
        with self._lock:
            refreshed = {}
            for pci_address, detail in gpu_details.items():
                normalized = self._normalize_pci_address(pci_address)
                refreshed[normalized] = detail

            self._gpu_details = refreshed
            self._sync_gpu_allocations_locked()

    def allocate(self, pci_address, device_uuid, memory_mb):
        with self._lock:
            normalized = self._ensure_gpu(pci_address)
            gpu = self._gpus[normalized]
            gpu.allocations[device_uuid] = memory_mb
            logger.debug('ResourceTracker: allocated %dMB on %s for %s (available: %dMB)' %
                         (memory_mb, normalized, device_uuid, gpu.available_memory_mb))

    def release(self, pci_address, device_uuid):
        with self._lock:
            normalized = self._normalize_pci_address(pci_address)
            gpu = self._gpus.get(normalized)
            if gpu and device_uuid in gpu.allocations:
                freed = gpu.allocations.pop(device_uuid)
                logger.debug('ResourceTracker: released %dMB on %s for %s' %
                             (freed, normalized, device_uuid))

    def can_allocate(self, pci_address, memory_mb):
        # type: (str, int) -> bool
        with self._lock:
            normalized = self._ensure_gpu(pci_address)
            return self._gpus[normalized].available_memory_mb >= memory_mb

    def get_available_memory(self, pci_address):
        # type: (str) -> int
        with self._lock:
            normalized = self._ensure_gpu(pci_address)
            return self._gpus[normalized].available_memory_mb

    def get_gpu_usage(self, pci_address, workers=None):
        # type: (str, list) -> GPUResourceInfo
        """Get resource usage for a specific GPU.

        Args:
            pci_address: GPU PCI address.
            workers: Optional list of Worker objects for this GPU.
        """
        with self._lock:
            normalized = self._ensure_gpu(pci_address)
            gpu = self._gpus[normalized]
            detail = self._gpu_details.get(normalized)
            info = GPUResourceInfo()
            info.pci_address = normalized
            info.cuda_index = detail['cuda_index'] if detail else 0
            info.total_memory_mb = gpu.total_memory_mb
            info.allocated_memory_mb = gpu.allocated_memory_mb
            info.worker_count = gpu.worker_count
            info.workers = workers if workers else []
            return info

    def get_all_gpu_usage(self, workers_by_gpu=None):
        # type: (dict) -> list
        """Get resource usage for all tracked GPUs.

        Args:
            workers_by_gpu: Optional dict {pci_address: [Worker, ...]}
        """
        with self._lock:
            normalized_workers = {}
            if workers_by_gpu:
                for pci_address, workers in workers_by_gpu.items():
                    normalized = self._normalize_pci_address(pci_address)
                    normalized_workers[normalized] = workers

            result = []
            for pci in self._gpus:
                ws = normalized_workers.get(pci, [])
                result.append(self.get_gpu_usage(pci, ws))
            return result

    def rebuild_from_workers(self, workers):
        """Rebuild allocation records from a list of Workers."""
        with self._lock:
            self._gpus.clear()
            for w in workers:
                normalized = self._ensure_gpu(w.pci_address)
                self._gpus[normalized].allocations[w.device_uuid] = w.allocated_memory_mb
            self._sync_gpu_allocations_locked()
            logger.debug('ResourceTracker: rebuilt from %d workers across %d GPUs' %
                         (len(workers), len(self._gpus)))

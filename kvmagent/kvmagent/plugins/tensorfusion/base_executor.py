'''
WorkerExecutor - abstract base for Worker lifecycle management.

Strategy Pattern: ProcessExecutor and ContainerExecutor are parallel
implementations. The caller injects the desired strategy into
TensorFusionService.

@author: tensorfusion
'''


class WorkerExecutor(object):
    """Abstract base class for Worker lifecycle management.

    Subclasses must implement all public methods.
    Shared constants live here to avoid duplication.
    """

    SHM_PREFIX = '/dev/shm/'
    SHM_SIZE_MB = 512
    BYTES_PER_MB = 1024 * 1024
    SHM_SIZE = SHM_SIZE_MB * BYTES_PER_MB
    LOG_DIR = '/var/log/zstack'
    DEFAULT_ENABLE_LOG = True
    DEFAULT_LOG_LEVEL = 'info'

    def __init__(self, gpu_details):
        """
        Args:
            gpu_details: dict {pci_address: detail_dict} from NVIDIA.query_gpu_details().
        """
        self._gpu_details = gpu_details

    def start(self, request):
        """Start a worker. Returns Worker object."""
        raise NotImplementedError

    def stop(self, worker):
        """Stop a running worker."""
        raise NotImplementedError

    def is_alive(self, worker):
        """Check if worker is still alive."""
        raise NotImplementedError

    def scan_running(self):
        """Scan and return list of currently running Worker objects."""
        raise NotImplementedError

    def reap_dead(self, worker):
        """Clean up a dead worker's resources. Return False when cleanup must be deferred."""
        raise NotImplementedError

    def cleanup_residual_workers_by_vm(self, vm_uuid, known_workers=None):
        """Best-effort cleanup for workers missing from StateStore. Returns count cleaned."""
        raise NotImplementedError

    @classmethod
    def _bytes_to_mb(cls, size):
        # type: (int) -> int
        if size <= 0:
            return 0
        return (size + cls.BYTES_PER_MB - 1) // cls.BYTES_PER_MB

    @staticmethod
    def worker_label(worker):
        """Return a human-readable identifier for logging."""
        name = getattr(worker, 'container_name', None)
        if name:
            return 'container=%s' % name
        pid = getattr(worker, 'pid', None)
        if pid is not None:
            return 'pid=%s' % pid
        return 'device=%s' % getattr(worker, 'device_uuid', '?')

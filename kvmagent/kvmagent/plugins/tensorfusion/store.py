'''
Thread-safe in-memory state store for TensorFusion Workers.

@author: tensorfusion
'''

import threading

from zstacklib.utils import log
from zstacklib.utils.pci import normalize_pci_address

logger = log.get_logger(__name__)


class StateStore(object):
    """Thread-safe in-memory store keyed by device_uuid."""

    def __init__(self):
        self._lock = threading.RLock()
        self._workers = {}  # {device_uuid: Worker}

    @staticmethod
    def _require_device_uuid(worker):
        device_uuid = getattr(worker, 'device_uuid', None)
        if not device_uuid:
            raise ValueError('worker.device_uuid is required')
        return device_uuid

    @staticmethod
    def _normalize_pci_address(pci_address):
        normalized = normalize_pci_address(pci_address)
        return normalized or pci_address

    def add(self, worker):
        with self._lock:
            device_uuid = self._require_device_uuid(worker)
            if device_uuid in self._workers:
                raise ValueError('duplicate worker.device_uuid: %s' % device_uuid)
            self._workers[device_uuid] = worker
            logger.debug('StateStore: added worker %s (vm=%s)' % (device_uuid, worker.vm_uuid))

    def replace(self, worker, expected_worker=None):
        with self._lock:
            device_uuid = self._require_device_uuid(worker)
            current = self._workers.get(device_uuid)
            if expected_worker is not None and current is not expected_worker:
                return None

            self._workers[device_uuid] = worker
            logger.debug('StateStore: replaced worker %s (vm=%s)' % (device_uuid, worker.vm_uuid))
            return worker

    def remove(self, device_uuid, expected_worker=None):
        with self._lock:
            current = self._workers.get(device_uuid)
            if expected_worker is not None and current is not expected_worker:
                return None

            w = self._workers.pop(device_uuid, None)
            if w:
                logger.debug('StateStore: removed worker %s' % device_uuid)
            return w

    def get(self, device_uuid):
        with self._lock:
            return self._workers.get(device_uuid)

    def exists(self, device_uuid):
        with self._lock:
            return device_uuid in self._workers

    def set_restarting(self, device_uuid, restarting, expected_worker=None):
        with self._lock:
            worker = self._workers.get(device_uuid)
            if worker is None:
                return None

            if expected_worker is not None and worker is not expected_worker:
                return None

            worker.restarting = restarting
            return worker

    def list_all(self):
        with self._lock:
            return list(self._workers.values())

    def list_by_vm(self, vm_uuid):
        with self._lock:
            return [w for w in self._workers.values() if w.vm_uuid == vm_uuid]

    def list_by_gpu(self, pci_address):
        with self._lock:
            normalized = self._normalize_pci_address(pci_address)
            return [
                w for w in self._workers.values()
                if self._normalize_pci_address(w.pci_address) == normalized
            ]

    def clear(self):
        with self._lock:
            self._workers.clear()

    def sync(self, workers):
        """Replace all stored workers with the given list."""
        with self._lock:
            synced = {}
            for worker in workers:
                device_uuid = self._require_device_uuid(worker)
                if device_uuid in synced:
                    raise ValueError('duplicate worker.device_uuid: %s' % device_uuid)
                synced[device_uuid] = worker
            self._workers = synced
            logger.debug('StateStore: synced %d workers' % len(self._workers))

    def count(self):
        with self._lock:
            return len(self._workers)

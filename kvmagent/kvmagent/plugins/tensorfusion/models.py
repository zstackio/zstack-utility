'''
TensorFusion data models - Python 2/3 compatible

@author: tensorfusion
'''

import uuid


class Worker(object):
    """Represents a running TensorFusion Worker process."""

    def __init__(self):
        self.device_uuid = None
        self.vm_uuid = None
        self.pid = None
        self.pci_address = None
        self.cuda_index = None
        self.protocol = None
        self.allocated_memory_mb = 0
        self.sm_percent_limit = 0
        self.shared_memory_path = None
        self.shared_memory_size = 0
        self.license = None
        self.license_sign = None
        self.enable_log = True
        self.log_level = 'info'
        self.restarting = False

    def to_dict(self):
        return {
            'deviceUuid': self.device_uuid,
            'vmUuid': self.vm_uuid,
            'pid': self.pid,
            'pciAddress': self.pci_address,
            'cudaIndex': self.cuda_index,
            'protocol': self.protocol,
            'allocatedMemoryMb': self.allocated_memory_mb,
            'smPercentLimit': self.sm_percent_limit,
            'sharedMemoryPath': self.shared_memory_path,
            'sharedMemorySize': self.shared_memory_size,
            'enableLog': self.enable_log,
            'logLevel': self.log_level,
            'restarting': self.restarting,
        }


class WorkerCreateRequest(object):
    """Parameters for creating a TensorFusion Worker."""

    def __init__(self):
        self.vm_uuid = None
        self.pci_address = None
        self.memory_mb = 0
        self.shmem_size = 0
        self.license = None
        self.license_sign = None
        self.enable_log = True
        self.log_level = 'info'
        self.device_uuid = None
        self.protocol = 'shmem'
        self.sm_percent_limit = 0

    def ensure_device_uuid(self):
        if not self.device_uuid:
            self.device_uuid = str(uuid.uuid4())


class GPUResourceInfo(object):
    """GPU resource usage snapshot."""

    def __init__(self):
        self.pci_address = None
        self.cuda_index = None
        self.total_memory_mb = 0
        self.allocated_memory_mb = 0
        self.worker_count = 0
        self.workers = []

    def to_dict(self):
        return {
            'pciAddress': self.pci_address,
            'cudaIndex': self.cuda_index,
            'totalMemoryMb': self.total_memory_mb,
            'allocatedMemoryMb': self.allocated_memory_mb,
            'workerCount': self.worker_count,
            'workers': [w.to_dict() for w in self.workers],
        }


class GPUHardwareInfo(object):
    """GPU hardware information from nvidia-smi."""

    def __init__(self):
        self.pci_address = None
        self.cuda_index = None
        self.name = None
        self.total_memory_mb = 0
        self.driver_version = None

    def to_dict(self):
        return {
            'pciAddress': self.pci_address,
            'cudaIndex': self.cuda_index,
            'name': self.name,
            'totalMemoryMb': self.total_memory_mb,
            'driverVersion': self.driver_version,
        }

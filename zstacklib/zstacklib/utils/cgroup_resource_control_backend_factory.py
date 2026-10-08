import os

if __package__:
    from . import resource_control_utils as resource_utils
    from .resource_control_utils import ResourceControlError
    from .cgroup_v1_resource_control_backend import CgroupV1ResourceControlBackend
    from .cgroup_v2_resource_control_backend import CgroupV2ResourceControlBackend
else:
    import resource_control_utils as resource_utils
    from resource_control_utils import ResourceControlError
    from cgroup_v1_resource_control_backend import CgroupV1ResourceControlBackend
    from cgroup_v2_resource_control_backend import CgroupV2ResourceControlBackend


class CgroupResourceControlBackendFactory(object):
    CGROUP_V2_ROOT = '/sys/fs/cgroup'
    CGROUP_V1_ROOT = '/sys/fs/cgroup/cpuset'
    CGROUP_V1_MEMORY_ROOT = '/sys/fs/cgroup/memory'
    CGROUP_V1_CPUACCT_ROOTS = ('/sys/fs/cgroup/cpu,cpuacct', '/sys/fs/cgroup/cpuacct')
    PROC_MOUNTS = '/proc/mounts'

    def cpu(self):
        backend = self.find_cpu()
        if backend is not None:
            return backend
        raise ResourceControlError('No available cpuset controller was found')

    def find_cpu(self):
        for root in self.v2_roots():
            controllers = os.path.join(root, 'cgroup.controllers')
            values = resource_utils.read(controllers).split() if os.path.isfile(controllers) else []
            if 'cpuset' in values or os.path.isfile(os.path.join(root, 'cpuset.cpus.effective')):
                return CgroupV2ResourceControlBackend(root)
        if os.path.isfile(os.path.join(self.CGROUP_V1_ROOT, 'cpuset.cpus')):
            return CgroupV1ResourceControlBackend(self.CGROUP_V1_ROOT)
        return None

    def memory(self):
        backend = self.find_memory()
        if backend is not None:
            return backend
        raise ResourceControlError('No available memory controller was found')

    def find_memory(self):
        for root in self.v2_roots():
            controllers = os.path.join(root, 'cgroup.controllers')
            values = resource_utils.read(controllers).split() if os.path.isfile(controllers) else []
            if ('memory' in values or os.path.isfile(os.path.join(root, 'memory.max'))):
                return CgroupV2ResourceControlBackend(root)
        root_limit = os.path.join(self.CGROUP_V1_MEMORY_ROOT, 'memory.limit_in_bytes')
        if os.path.isfile(root_limit):
            return CgroupV1ResourceControlBackend(self.CGROUP_V1_MEMORY_ROOT)
        return None

    def v2_roots(self):
        roots = []
        if os.path.isfile(os.path.join(self.CGROUP_V2_ROOT, 'cgroup.controllers')):
            roots.append(self.CGROUP_V2_ROOT)
        if not os.path.isfile(self.PROC_MOUNTS):
            return roots
        for line in resource_utils.read(self.PROC_MOUNTS).splitlines():
            fields = line.split()
            if len(fields) < 4 or fields[2] != 'cgroup2':
                continue
            if 'rw' not in fields[3].split(','):
                continue
            root = resource_utils.decode_mount_path(fields[1])
            if root not in roots and os.path.isfile(os.path.join(root, 'cgroup.controllers')):
                roots.append(root)
        return roots

    def cpu_accounting(self):
        return [CgroupV2ResourceControlBackend(root) for root in self.v2_roots()] + self.legacy_cpu_accounting()

    def legacy_cpu_accounting(self):
        return [CgroupV1ResourceControlBackend(root) for root in self.CGROUP_V1_CPUACCT_ROOTS]

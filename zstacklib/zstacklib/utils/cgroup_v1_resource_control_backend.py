import os

if __package__:
    from . import resource_control_utils as resource_utils
    from .cgroup_resource_control_backend import CGROUP_VERSION_V1, CgroupResourceControlBackend, ResourceControlError
else:
    import resource_control_utils as resource_utils
    from cgroup_resource_control_backend import CGROUP_VERSION_V1, CgroupResourceControlBackend, ResourceControlError


class CgroupV1ResourceControlBackend(CgroupResourceControlBackend):
    version = CGROUP_VERSION_V1
    cpu_set_property = None
    memory_limit_property = 'MemoryLimit'
    memory_usage_file = 'memory.usage_in_bytes'

    def supports_subtree_memory_limit(self, target):
        hierarchy = os.path.join(target, 'memory.use_hierarchy')
        return os.path.isfile(hierarchy) and resource_utils.read(hierarchy).strip() == '1'

    def supports_exclusive_cpu_partition(self):
        return False

    def enable_cpu_controller(self, target):
        pass

    def enable_memory_controller(self, target):
        pass

    def require_cpu_target(self, target):
        pass

    def shared_cpu_num(self):
        return None

    def matches_cpu_hierarchy(self, fields):
        return 'cpuset' in fields[1].split(',')

    def apply_exclusive_cpu_set(self, target, desired):
        raise ResourceControlError('Exclusive CPU partitions are not supported by the cgroup backend')

    def release_cpu_set(self, target):
        self._initialize_mems(target)
        self.reset_cpu_set(target, self._parent_cpu_set(target))

    def read_cpu_time(self, relative):
        return self._optional_numeric(os.path.join(self.root, relative, 'cpuacct.usage'))

    def apply_memory(self, memory_target, desired, cpu_target=None):
        managed = self._managed_group(self.root, memory_target)
        root_limit = os.path.join(self.root, 'memory.limit_in_bytes')
        if not os.path.isfile(root_limit):
            raise ResourceControlError('Cgroup v1 memory controller does not expose its root limit')
        if not os.path.isdir(memory_target):
            if managed and desired == 0:
                return 0
            if not managed:
                raise ResourceControlError('Memory controller is unavailable for control group[%s]' % memory_target)
            resource_utils.mkdir(memory_target)
        limit_file = os.path.join(memory_target, 'memory.limit_in_bytes')
        if not os.path.isfile(limit_file):
            raise ResourceControlError('Memory controller is unavailable for control group[%s]' % memory_target)
        if managed and desired > 0:
            self._move_process_file(
                os.path.join(cpu_target, 'cgroup.procs'), os.path.join(memory_target, 'cgroup.procs'))
        value = (resource_utils.read(root_limit).strip() if desired == 0 else str(desired))
        if resource_utils.read(limit_file).strip() != value:
            self._validate_memory_limit_against_usage(os.path.join(memory_target, 'memory.usage_in_bytes'), desired)
            resource_utils.write(limit_file, value)
        if resource_utils.read(limit_file).strip() != value:
            raise ResourceControlError('Control group[%s] did not apply memory limit[%s]' % (memory_target, value))
        if managed and desired == 0:
            self._move_process_file(
                os.path.join(memory_target, 'cgroup.procs'),
                os.path.join(os.path.dirname(memory_target), 'cgroup.procs'))
        return 0 if desired == 0 else self._parse_memory(resource_utils.read(limit_file).strip())

    def initialize_cpus(self, target):
        cpus = os.path.join(target, 'cpuset.cpus')
        if resource_utils.read(cpus).strip():
            return
        resource_utils.write(cpus, self._parent_cpu_set(target))

    def read_memory_limit(self, target):
        root_limit_path = os.path.join(self.root, 'memory.limit_in_bytes')
        if not os.path.isfile(root_limit_path):
            return None
        root_limit = self._parse_memory(resource_utils.read(root_limit_path).strip())
        resource_utils.under_root(self.root, target)
        limits = []
        current = target
        while True:
            path = os.path.join(current, 'memory.limit_in_bytes')
            if os.path.isfile(path):
                limits.append(self._parse_memory(resource_utils.read(path).strip()))
            if current == self.root:
                break
            current = os.path.dirname(current)
            resource_utils.under_root(self.root, current)
        if not limits:
            return None
        effective = min(limits)
        return 0 if effective >= root_limit else effective

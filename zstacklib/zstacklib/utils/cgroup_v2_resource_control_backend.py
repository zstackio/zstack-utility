import os

if __package__:
    from . import resource_control_utils as resource_utils
    from .cgroup_resource_control_backend import CGROUP_VERSION_V2, CgroupResourceControlBackend, ResourceControlError
else:
    import resource_control_utils as resource_utils
    from cgroup_resource_control_backend import CGROUP_VERSION_V2, CgroupResourceControlBackend, ResourceControlError


class CgroupV2ResourceControlBackend(CgroupResourceControlBackend):
    version = CGROUP_VERSION_V2
    cpu_set_property = 'AllowedCPUs'
    memory_limit_property = 'MemoryMax'
    memory_usage_file = 'memory.current'

    def supports_subtree_memory_limit(self, target):
        return True

    def supports_exclusive_cpu_partition(self):
        return True

    def initialize_cpus(self, target):
        pass

    def require_cpu_target(self, target):
        if target is None:
            raise ResourceControlError('The target control group is not active in the cpuset hierarchy')

    def matches_cpu_hierarchy(self, fields):
        return fields[0] == '0'

    def shared_cpu_num(self):
        cpu_set = resource_utils.normalize(resource_utils.read(os.path.join(self.root, 'cpuset.cpus.effective')))
        if not cpu_set:
            raise ResourceControlError('The shared control group has no effective CPU set')
        return resource_utils.count(cpu_set)

    def apply_cpu_set(self, target, desired):
        self._make_partition_member(target)
        return super(CgroupV2ResourceControlBackend, self).apply_cpu_set(target, desired)

    def apply_exclusive_cpu_set(self, target, desired):
        self.enable_cpu_controller(target)
        if not os.path.isfile(os.path.join(target, 'cpuset.cpus.partition')):
            raise ResourceControlError('CPU partition interface is unavailable for control group[%s]' % target)
        super(CgroupV2ResourceControlBackend, self).apply_cpu_set(target, desired)
        self._make_partition_root(target, desired)
        effective = os.path.join(target, 'cpuset.cpus.effective')
        actual = resource_utils.read(effective if os.path.isfile(effective) else os.path.join(target, 'cpuset.cpus'))
        return resource_utils.normalize(actual)

    def release_cpu_set(self, target):
        self._make_partition_member(target)
        self.enable_cpu_controller(target)
        self._initialize_mems(target)
        if self._managed_group(self.root, target):
            self._move_processes_to_parent(target)
            desired = ''
        else:
            desired = self._parent_cpu_set(target)
        self.reset_cpu_set(target, desired)

    def apply_memory(self, memory_target, desired, cpu_target=None):
        managed = self._managed_group(self.root, memory_target)
        if not os.path.isdir(memory_target):
            if managed and desired == 0:
                return 0
            if not managed:
                raise ResourceControlError('Memory controller is unavailable for control group[%s]' % memory_target)
            resource_utils.mkdir(memory_target)
        self._enable_memory_controller(memory_target)
        limit_file = os.path.join(memory_target, 'memory.max')
        if not os.path.isfile(limit_file):
            raise ResourceControlError('Memory controller is unavailable for control group[%s]' % memory_target)
        if (managed and cpu_target != memory_target and desired > 0):
            self._move_process_file(
                os.path.join(cpu_target, 'cgroup.procs'), os.path.join(memory_target, 'cgroup.procs'))
        value = 'max' if desired == 0 else str(desired)
        if resource_utils.read(limit_file).strip() != value:
            self._validate_memory_limit_against_usage(os.path.join(memory_target, 'memory.current'), desired)
            resource_utils.write(limit_file, value)
        actual = resource_utils.read(limit_file).strip()
        if actual != value:
            raise ResourceControlError('Control group[%s] did not apply memory limit[%s]' % (memory_target, value))
        if (managed and cpu_target != memory_target and desired == 0):
            self._move_process_file(
                os.path.join(memory_target, 'cgroup.procs'),
                os.path.join(os.path.dirname(memory_target), 'cgroup.procs'))
        return 0 if actual == 'max' else self._parse_memory(actual)

    def enable_cpu_controller(self, target):
        relative = os.path.relpath(target, self.root)
        current = self.root
        for part in [] if relative == '.' else relative.split(os.sep):
            child = os.path.join(current, part)
            if not os.path.isfile(os.path.join(child, 'cpuset.cpus')):
                control = os.path.join(current, 'cgroup.subtree_control')
                if not os.path.isfile(control):
                    raise ResourceControlError(
                        'Cgroup v2 subtree control is unavailable for control '
                        'group[%s]' % current)
                resource_utils.write(control, '+cpuset')
            current = child

    def _enable_memory_controller(self, target):
        if os.path.isfile(os.path.join(target, 'memory.max')):
            return
        relative = os.path.relpath(target, self.root)
        current = self.root
        for part in [] if relative == '.' else relative.split(os.sep):
            child = os.path.join(current, part)
            if not os.path.isfile(os.path.join(child, 'memory.max')):
                controllers = os.path.join(current, 'cgroup.controllers')
                control = os.path.join(current, 'cgroup.subtree_control')
                if (not os.path.isfile(controllers)
                        or 'memory' not in resource_utils.read(controllers).split()
                        or not os.path.isfile(control)):
                    raise ResourceControlError(
                        'Memory controller cannot be delegated below control group[%s]' % current)
                resource_utils.write(control, '+memory')
            current = child

    def read_cpu_time(self, relative):
        path = os.path.join(self.root, relative, 'cpu.stat')
        if not os.path.isfile(path):
            return None
        for line in resource_utils.read(path).splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0] == 'usage_usec':
                return self._parse_memory(fields[1]) * self.NANOSECONDS_PER_MICROSECOND
        return None

    def read_memory_limit(self, target):
        limits = []
        current = target
        while True:
            path = os.path.join(current, 'memory.max')
            if os.path.isfile(path):
                value = resource_utils.read(path).strip()
                if value != 'max':
                    limits.append(self._parse_memory(value))
            if current == self.root:
                break
            current = os.path.dirname(current)
            resource_utils.under_root(self.root, current)
        return min(limits) if limits else 0

    def _make_partition_root(self, target, desired):
        partition = os.path.join(target, 'cpuset.cpus.partition')
        exclusive = os.path.join(target, 'cpuset.cpus.exclusive')
        if (os.path.isfile(exclusive) and resource_utils.normalize(resource_utils.read(exclusive)) != desired):
            resource_utils.write(exclusive, desired)
        if resource_utils.read(partition).strip() != 'root':
            resource_utils.write(partition, 'root')
        if resource_utils.read(partition).strip() != 'root':
            raise ResourceControlError('Failed to make control group[%s] an exclusive CPU partition' % target)
        effective = os.path.join(target, 'cpuset.cpus.exclusive.effective')
        if (os.path.isfile(effective) and resource_utils.normalize(resource_utils.read(effective)) != desired):
            raise ResourceControlError('Control group[%s] did not apply exclusive CPU set[%s]' % (target, desired))

    def _make_partition_member(self, target):
        partition = os.path.join(target, 'cpuset.cpus.partition')
        if not os.path.isfile(partition):
            return
        if resource_utils.read(partition).strip() != 'member':
            resource_utils.write(partition, 'member')
        if resource_utils.read(partition).strip() != 'member':
            raise ResourceControlError('Failed to return control group[%s] to the shared CPU ' 'partition' % target)
        exclusive = os.path.join(target, 'cpuset.cpus.exclusive')
        if (os.path.isfile(exclusive) and resource_utils.normalize(resource_utils.read(exclusive))):
            resource_utils.write(exclusive, '\n')

import os
import re

if __package__:
    from . import resource_control_utils as resource_utils
    from .resource_control_utils import ResourceControlError
else:
    import resource_control_utils as resource_utils
    from resource_control_utils import ResourceControlError

CGROUP_VERSION_V1 = 1
CGROUP_VERSION_V2 = 2


class CgroupResourceControlBackend(object):
    NANOSECONDS_PER_MICROSECOND = 1000
    PROCESS_MOVE_ATTEMPTS = 3

    def __init__(self, root):
        self.root = root

    def supports_subtree_memory_limit(self, target):
        raise NotImplementedError

    def supports_exclusive_cpu_partition(self):
        raise NotImplementedError

    def enable_cpu_controller(self, target):
        raise NotImplementedError

    def initialize_cpus(self, target):
        raise NotImplementedError

    def require_cpu_target(self, target):
        raise NotImplementedError

    def release_cpu_set(self, target):
        raise NotImplementedError

    def apply_exclusive_cpu_set(self, target, desired):
        raise NotImplementedError

    def apply_memory(self, memory_target, desired, cpu_target=None):
        raise NotImplementedError

    def read_memory_limit(self, target):
        raise NotImplementedError

    def read_cpu_time(self, relative):
        raise NotImplementedError

    def matches_cpu_hierarchy(self, fields):
        raise NotImplementedError

    def shared_cpu_num(self):
        raise NotImplementedError

    def require_subtree_memory_limit(self, target):
        if not self.supports_subtree_memory_limit(target):
            raise ResourceControlError('Subtree memory limits are not supported for control group[%s]' % target)

    def validate_memory_limit(self, target, desired):
        self._validate_memory_limit_against_usage(os.path.join(target, self.memory_usage_file), desired)

    def read_memory_usage(self, target):
        return self._optional_numeric(os.path.join(target, self.memory_usage_file))

    def prepare_cpu_group(self, target):
        self.enable_cpu_controller(target)
        self._initialize_mems(target)
        self.initialize_cpus(target)

    def attach_processes(self, source, target):
        resource_utils.mkdir(target)
        self.prepare_cpu_group(target)
        self._move_processes(os.path.join(source, 'cgroup.procs'), os.path.join(target, 'cgroup.procs'),
                             'Systemd control group process files are unavailable',
                             'Some systemd unit processes could not be moved')

    def reset_cpu_set(self, target, desired):
        cpu_file = os.path.join(target, 'cpuset.cpus')
        if not os.path.isfile(cpu_file):
            raise ResourceControlError('Cpuset controller is unavailable for control group[%s]' % target)
        if resource_utils.normalize(resource_utils.read(cpu_file)) != desired:
            resource_utils.write(cpu_file, desired or '\n')
        if resource_utils.normalize(resource_utils.read(cpu_file)) != desired:
            raise ResourceControlError('Failed to release CPU set from control group[%s]' % target)

    def apply_cpu_set(self, target, desired):
        self.enable_cpu_controller(target)
        self._initialize_mems(target)
        cpu_file = os.path.join(target, 'cpuset.cpus')
        if not os.path.isfile(cpu_file):
            raise ResourceControlError('Cpuset controller is unavailable for control group[%s]' % target)
        configured = resource_utils.normalize(resource_utils.read(cpu_file))
        if configured != desired:
            resource_utils.write(cpu_file, desired)
        effective_file = os.path.join(target, 'cpuset.cpus.effective')
        actual = resource_utils.read(effective_file if os.path.isfile(effective_file) else cpu_file)
        return resource_utils.normalize(actual)

    def read_cpu_set(self, target):
        current = target
        while True:
            for name in ('cpuset.cpus.effective', 'cpuset.cpus'):
                path = os.path.join(current, name)
                if os.path.isfile(path):
                    value = resource_utils.normalize(resource_utils.read(path))
                    if value:
                        return value
            if current == self.root:
                raise ResourceControlError('Control group[%s] and its parents have no effective CPU set' % target)
            current = os.path.dirname(current)
            resource_utils.under_root(self.root, current)

    def process_group(self, pid):
        for line in resource_utils.read('/proc/%s/cgroup' % pid).splitlines():
            fields = line.split(':', 2)
            if len(fields) != 3:
                continue
            if self.matches_cpu_hierarchy(fields):
                target = os.path.normpath(os.path.join(self.root, fields[2].lstrip('/')))
                resource_utils.under_root(self.root, target)
                if os.path.isdir(target):
                    return target
        raise ResourceControlError('No cpuset control group was found for process[%s]' % pid)

    def _process_ids(self, path):
        return [pid for pid in resource_utils.read(path).split() if re.match(r'^[1-9][0-9]*$', pid)]

    def _parse_memory(self, value):
        if not re.match(r'^[0-9]+$', value or ''):
            raise ResourceControlError('Memory value[%s] is not a valid byte count' % value)
        return int(value)

    def _optional_numeric(self, path):
        return self._parse_memory(resource_utils.read(path).strip()) if os.path.isfile(path) else None

    def _optional_limit(self, path):
        if not os.path.isfile(path):
            return None
        value = resource_utils.read(path).strip()
        return 0 if value == 'max' else self._parse_memory(value)

    def _managed_group(self, root, target):
        relative = os.path.relpath(target, root)
        return relative != '.' and relative.split(os.sep, 1)[0].startswith('zstack-role-')

    def _validate_memory_limit_against_usage(self, usage_file, desired):
        if desired == 0:
            return
        current = self._parse_memory(resource_utils.read(usage_file).strip())
        current = max(current, self._resident_memory_usage(os.path.join(os.path.dirname(usage_file), 'cgroup.procs')))
        if desired < current:
            raise ResourceControlError('Memory limit[%s] is below current usage[%s]' % (desired, current))

    def _resident_memory_usage(self, process_file):
        if not os.path.isfile(process_file):
            return 0
        total = 0
        for pid in self._process_ids(process_file):
            status_file = '/proc/%s/status' % pid
            if not os.path.isfile(status_file):
                continue
            status = resource_utils.read(status_file)
            match = re.search(r'^VmRSS:\s+([0-9]+)\s+kB$', status, re.MULTILINE)
            if match:
                total += int(match.group(1)) * resource_utils.KIBIBYTE
        return total

    def _move_process_file(self, source, destination):
        self._move_processes(
            source, destination,
            'Memory controller process files are unavailable',
            'Some processes could not be moved to the memory control group')

    def _move_processes_to_parent(self, target):
        self._move_processes(
            os.path.join(target, 'cgroup.procs'),
            os.path.join(os.path.dirname(target), 'cgroup.procs'),
            'Cpuset controller process files are unavailable',
            'Some processes could not be moved to the parent control group')

    def _move_processes(self, source, destination, unavailable_message, mismatch_message):
        if not os.path.isfile(source) or not os.path.isfile(destination):
            raise ResourceControlError(unavailable_message)
        for _ in range(self.PROCESS_MOVE_ATTEMPTS):
            destination_pids = set(self._process_ids(destination))
            for pid in self._process_ids(source):
                if (pid in destination_pids or not os.path.isdir('/proc/%s' % pid)):
                    continue
                resource_utils.write(destination, pid)

            destination_pids = set(self._process_ids(destination))
            remaining = [
                pid for pid in self._process_ids(source)
                if os.path.isdir('/proc/%s' % pid)
                and pid not in destination_pids
            ]
            if not remaining:
                return
        raise ResourceControlError(mismatch_message)

    def _initialize_mems(self, target):
        mems = os.path.join(target, 'cpuset.mems')
        if not os.path.isfile(mems) or resource_utils.read(mems).strip():
            return
        parent = os.path.dirname(target)
        source = os.path.join(parent, 'cpuset.mems.effective')
        if not os.path.isfile(source):
            source = os.path.join(parent, 'cpuset.mems')
        value = resource_utils.read(source).strip()
        if not value:
            raise ResourceControlError('Control group[%s] has no effective memory node set' % parent)
        resource_utils.write(mems, value)

    def _parent_cpu_set(self, target):
        parent = os.path.dirname(target)
        source = os.path.join(parent, 'cpuset.cpus.effective')
        if not os.path.isfile(source):
            source = os.path.join(parent, 'cpuset.cpus')
        value = resource_utils.normalize(resource_utils.read(source))
        if not value:
            raise ResourceControlError('Parent control group[%s] has no effective CPU set' % parent)
        return value

    def target(self, relative):
        target = os.path.normpath(os.path.join(self.root, relative.lstrip('/')))
        resource_utils.under_root(self.root, target)
        return target

    def existing_target(self, target):
        return target if os.path.isdir(target) else None

    def find_target(self, control_group):
        if not control_group:
            return None
        target = self.target(control_group)
        return self.existing_target(target) if target != self.root else None

    def require_target(self, control_group):
        target = self.find_target(control_group)
        if target is None:
            raise ResourceControlError('Systemd control group[%s] does not exist' % control_group)
        return target

    def contains(self, control_group, target):
        current = self.find_target(control_group)
        return current is not None and self.is_descendant(current, target)

    @staticmethod
    def is_descendant(path, parent):
        return path == parent or path.startswith(parent + os.sep)

    def has_process_file(self, target):
        return os.path.isfile(os.path.join(target, 'cgroup.procs'))

    def has_processes(self, target):
        return (os.path.isdir(target) and self.has_process_file(target)
                and bool(self._process_ids(os.path.join(target, 'cgroup.procs'))))

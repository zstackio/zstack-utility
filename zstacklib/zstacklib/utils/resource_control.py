import glob
import os
import re
from enum import Enum

if __package__:
    from . import resource_control_utils as resource_utils
    from .resource_control_utils import ResourceControlError
    from .systemd_resource_control_utils import SystemdResourceControlUtils
    from .cgroup_resource_control_backend_factory import CgroupResourceControlBackendFactory
else:
    import resource_control_utils as resource_utils
    from resource_control_utils import ResourceControlError
    from systemd_resource_control_utils import SystemdResourceControlUtils
    from cgroup_resource_control_backend_factory import CgroupResourceControlBackendFactory


def _read_cpu_ids(path):
    with open(path) as stream:
        value = stream.read().strip()
    result = set()
    for item in value.split(','):
        if item.startswith('^'):
            result.remove(int(item[1:]))
        elif item:
            bounds = item.split('-')
            result.update(range(int(bounds[0]), int(bounds[-1]) + 1))
    return result


def _get_core_groups(cpus):
    groups = set()
    for cpu in cpus:
        path = '/sys/devices/system/cpu/cpu%s/topology/thread_siblings_list' % cpu
        if not os.path.isfile(path):
            return []
        siblings = tuple(sorted(cpus & _read_cpu_ids(path)))
        if not siblings:
            return []
        groups.add(siblings)
    return [[str(cpu) for cpu in group] for group in sorted(groups)]


def get_cpu_topology():
    online = _read_cpu_ids('/sys/devices/system/cpu/online')
    nodes = glob.glob('/sys/devices/system/node/node[0-9]*')
    result = {}
    for node in nodes or [None]:
        node_id = os.path.basename(node)[4:] if node else '0'
        cpus = _read_cpu_ids(os.path.join(node, 'cpulist')) if node else online
        online_cpus = cpus & online
        result[node_id] = {
            'cpus': [str(cpu) for cpu in sorted(cpus)],
            'onlineCpus': [str(cpu) for cpu in sorted(online_cpus)],
            'coreGroups': _get_core_groups(online_cpus),
        }
    return result


class ServiceState(Enum):
    RUNNING = 'RUNNING'
    INACTIVE = 'INACTIVE'
    NOT_FOUND = 'NOT_FOUND'


class ResourceControlManager(object):
    MAX_SERVICE_HANDLES = 64
    MAX_SERVICE_NAME_TAIL_LENGTH = 63
    OBSERVATION_ROLE = 'OBSERVATION'
    SERVICE_NAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,%s}$' % MAX_SERVICE_NAME_TAIL_LENGTH)

    def __init__(self, backend_factory=None):
        self.systemd = SystemdResourceControlUtils()
        self.backend_factory = backend_factory if backend_factory is not None else CgroupResourceControlBackendFactory()

    @classmethod
    def validate_service_command(cls, slice_name, handles):
        if not isinstance(slice_name, str) or not SystemdResourceControlUtils.SLICE_PATTERN.match(slice_name):
            raise ResourceControlError('SliceName[%s] is not a valid systemd slice' % slice_name)
        if not handles or len(handles) > cls.MAX_SERVICE_HANDLES:
            raise ResourceControlError('Service handles must contain between 1 and %s items' % cls.MAX_SERVICE_HANDLES)
        identities = set()
        for handle in handles:
            handle_type = cls._value(handle, 'handleType')
            value = cls._value(handle, 'value')
            service_name = cls._value(handle, 'serviceName')
            if not isinstance(cls._value(handle, 'optional'), bool):
                raise ResourceControlError('Optional must be a boolean for service[%s]' % service_name)
            if (not isinstance(service_name, str) or not cls.SERVICE_NAME_PATTERN.match(service_name)
                    or not isinstance(cls._value(handle, 'restartable'), bool)):
                raise ResourceControlError('Service handle[%s] has an invalid serviceName or restartable value' % value)
            if handle_type != 'SYSTEMD_UNIT':
                raise ResourceControlError('Resource consumer handle type[%s] is unsupported' % handle_type)
            if not isinstance(value, str) or not SystemdResourceControlUtils.SYSTEMD_UNIT_PATTERN.match(value):
                raise ResourceControlError('Systemd unit handle value[%s] is invalid' % value)
            identity = (handle_type, value)
            if identity in identities:
                raise ResourceControlError('Service handle[%s:%s] is duplicated' % identity)
            identities.add(identity)

    def get_shared_cpu_num(self):
        backend = self.backend_factory.find_cpu()
        return backend.shared_cpu_num() if backend is not None else None

    def apply(self, role_type, cpu_set, handles, memory=None, slice_name=None, isolation_mode='SHARED'):
        isolation_mode = self._isolation_mode(isolation_mode)
        memory = self.validate_memory_limit(memory)
        desired = resource_utils.normalize('' if cpu_set is None else cpu_set)
        if desired:
            desired = self.validate_cpu_set(desired)
        else:
            desired = None
        if isolation_mode == 'EXCLUSIVE' and desired is None:
            raise ResourceControlError('Exclusive isolation requires a CPU set')
        if desired is None and memory is None:
            return {'synced': True}
        backend = self.backend_factory.cpu()
        if isolation_mode == 'EXCLUSIVE' and not backend.supports_exclusive_cpu_partition():
            raise ResourceControlError('Exclusive CPU partitions are not supported by the cgroup backend')
        memory_backend = None
        if memory is not None:
            memory_backend = self.backend_factory.memory()
        if (slice_name and any(self._value(handle, 'handleType') == 'SYSTEMD_UNIT' for handle in handles or [])):
            return self._apply_systemd_slice(
                backend, role_type, slice_name, handles,
                desired, memory, memory_backend, isolation_mode)
        results = []

        for handle in handles or []:
            results.append(self._apply_non_systemd_handle(
                backend, role_type, handle, desired, memory,
                memory_backend, isolation_mode))

        return self._summarize_apply(results)

    def release(self, role_type, handles, slice_name=None):
        backend = self.backend_factory.cpu()
        memory_backend = self.backend_factory.find_memory()
        if (slice_name and any(self._value(handle, 'handleType') == 'SYSTEMD_UNIT' for handle in handles or [])):
            return self._release_systemd_slice(backend, role_type, slice_name, handles, memory_backend)
        results = [
            self._release_non_systemd_handle(backend, role_type, handle, memory_backend)
            for handle in handles or []
        ]
        return self._summarize_release(results)

    def _apply_systemd_slice(
            self, backend, role_type, slice_name, handles,
            desired, desired_memory, memory_backend,
            isolation_mode='SHARED'):
        units = [self._value(handle, 'value') for handle in handles or []
                 if self._value(handle, 'handleType') == 'SYSTEMD_UNIT']
        changed = self.systemd.prune_services(slice_name, units)
        if desired is not None:
            changed = self.systemd.configure_slice(
                slice_name, backend.cpu_set_property, desired, None, desired_memory) or changed
        for handle in handles or []:
            if self._value(handle, 'handleType') != 'SYSTEMD_UNIT':
                continue
            changed = self.systemd.configure_service(self._value(handle, 'value'), slice_name) or changed
        legacy_cpu_results = {}
        slice_target = self._ensure_active_slice_target(backend, slice_name)
        if slice_target is None:
            if isolation_mode == 'EXCLUSIVE':
                raise ResourceControlError(
                    'The configured systemd slice must be active before '
                    'applying exclusive isolation')
            slice_target = None
            if desired is not None:
                for index, handle in enumerate(handles or []):
                    if self._value(handle, 'handleType') != 'SYSTEMD_UNIT':
                        continue
                    if self.systemd.configured_slice(self._value(handle, 'value')) != slice_name:
                        continue
                    legacy_cpu_results[index] = self._apply_non_systemd_handle(
                        backend, role_type, handle, desired,
                        None, None, isolation_mode)
        actual = None
        actual_memory = None
        memory_slice_target = None
        if slice_target is not None and desired is not None:
            actual = (backend.apply_exclusive_cpu_set(slice_target, desired) if isolation_mode == 'EXCLUSIVE'
                      else backend.apply_cpu_set(slice_target, desired))
        if changed:
            self.systemd.reload()
        if desired_memory is not None and memory_backend is not None:
            if desired_memory > 0:
                self._prepare_active_slice_memory(slice_name, desired_memory, memory_backend)
            memory_slice_target = self._active_slice_target(memory_backend, slice_name)
            if memory_slice_target is not None:
                if desired_memory > 0:
                    memory_backend.require_subtree_memory_limit(memory_slice_target)
                actual_memory = memory_backend.apply_memory(memory_slice_target, desired_memory)
            if self.systemd.configure_slice(slice_name, backend.cpu_set_property, desired,
                                           memory_backend.memory_limit_property, desired_memory):
                self.systemd.reload()

        results = []
        for index, handle in enumerate(handles or []):
            if self._value(handle, 'handleType') != 'SYSTEMD_UNIT':
                results.append(self._apply_non_systemd_handle(
                    backend, role_type, handle, desired,
                    desired_memory, memory_backend,
                    isolation_mode))
                continue
            if self.systemd.configured_slice(self._value(handle, 'value')) != slice_name:
                results.append(None)
                continue
            properties = self.systemd.properties(self._value(handle, 'value'))
            optional = self._value(handle, 'optional', False)
            if properties.get('LoadState') == 'not-found':
                if not optional:
                    raise ResourceControlError('Systemd unit[%s] does not exist' % self._value(handle, 'value'))
                results.append(None)
                continue
            if not properties.get('ControlGroup'):
                if desired is None or backend.cpu_set_property is not None:
                    results.append(True)
                else:
                    results.append(None)
                continue
            if legacy_cpu_results:
                cpu_synced = legacy_cpu_results[index]
                if cpu_synced is None:
                    results.append(None)
                    continue
            else:
                current = backend.require_target(properties.get('ControlGroup'))
                if (slice_target is None or not backend.is_descendant(current, slice_target)):
                    results.append(False)
                    continue
                cpu_synced = self._cpu_matches(actual, desired)
            if (desired_memory is not None and memory_slice_target is not None
                    and not memory_backend.contains(
                        properties.get('ControlGroup'),
                        memory_slice_target)):
                results.append(False)
                continue
            results.append(cpu_synced and self._memory_matches(actual_memory, desired_memory))
        return self._summarize_apply(results)

    def _release_systemd_slice(self, backend, role_type, slice_name, handles, memory_backend):
        slice_target = self._active_slice_target(backend, slice_name)
        if slice_target is not None:
            backend.release_cpu_set(slice_target)
        changed = self.systemd.release_slice(slice_name)
        if changed:
            self.systemd.reload()
        if memory_backend is not None:
            memory_target = self._active_slice_target(memory_backend, slice_name)
            if memory_target is not None:
                memory_backend.apply_memory(memory_target, 0)
        if slice_target is None:
            results = [
                self._release_non_systemd_handle(backend, role_type, handle, memory_backend)
                for handle in handles or []
            ]
            return self._summarize_release(results)
        return {'synced': True}

    def _prepare_active_slice_memory(self, slice_name, desired_memory, memory_backend):
        properties = self.systemd.properties(slice_name)
        if properties.get('ActiveState') != 'active':
            return
        memory_target = memory_backend.require_target(properties.get('ControlGroup'))
        memory_backend.require_subtree_memory_limit(memory_target)
        memory_backend.enable_memory_controller(memory_target)
        memory_backend.validate_memory_limit(memory_target, desired_memory)

    def _apply_non_systemd_handle(
            self, backend, role_type, handle, desired,
            desired_memory, memory_backend, isolation_mode):
        target = self._resolve(backend, role_type, handle)
        if target is None:
            return None
        actual = None
        if desired is not None:
            actual = (backend.apply_exclusive_cpu_set(target, desired) if isolation_mode == 'EXCLUSIVE'
                      else backend.apply_cpu_set(target, desired))
        actual_memory = None
        if desired_memory is not None:
            actual_memory = self._apply_memory_limit(backend, target, desired_memory, memory_backend)
        return self._cpu_matches(actual, desired) and self._memory_matches(actual_memory, desired_memory)

    def _release_non_systemd_handle(self, backend, role_type, handle, memory_backend):
        target = self._resolve_for_release(backend, role_type, handle)
        if target is None:
            return None
        backend.release_cpu_set(target)
        actual_memory = 0
        if memory_backend is not None:
            actual_memory = self._apply_memory_limit(backend, target, 0, memory_backend)
        return self._memory_matches(actual_memory, 0)

    def _ensure_active_slice_target(self, backend, slice_name):
        properties = self.systemd.properties(slice_name)
        if properties.get('ActiveState') != 'active':
            self.systemd.start(slice_name)
        return self._active_slice_target(backend, slice_name)

    def _active_slice_target(self, backend, slice_name):
        properties = self.systemd.properties(slice_name)
        if properties.get('ActiveState') != 'active':
            return None
        return backend.find_target(properties.get('ControlGroup'))

    def inspect(self, role_type, handles, slice_name=None):
        backend = self.backend_factory.cpu()
        result = []
        slice_targets = {}
        for handle in handles or []:
            configured_slice = self.systemd.configured_slice(self._value(handle, 'value'))
            if slice_name is not None and configured_slice is not None and configured_slice != slice_name:
                continue
            state, target = self._inspect_target(backend, role_type, handle)
            usage = self._service_usage(handle, state)
            if target is not None:
                usage['restartRequired'] = self._restart_required(
                    backend, role_type, handle, state, target, slice_targets)
                usage.update(self._group_usage(backend, target, handle))
            result.append(usage)
        return result

    def inspect_systemd_slices(self, slice_names):
        handles = [{
            'handleType': 'SYSTEMD_UNIT',
            'value': name,
            'serviceName': name,
            'restartable': False,
        } for name in slice_names or []]
        usages = self.inspect(self.OBSERVATION_ROLE, handles)
        return [{
            'cgroupName': usage.get('serviceName'),
            'cpuSet': usage.get('cpuSet'),
            'cpuTime': usage.get('cpuTime'),
            'memory': usage.get('memory'),
            'memoryLimit': usage.get('memoryLimit'),
        } for usage in usages if usage.get('state') == ServiceState.RUNNING.value]

    def restart(self, slice_name, handles):
        units = []
        for handle in handles or []:
            if (self._value(handle, 'handleType') != 'SYSTEMD_UNIT' or not self._value(handle, 'restartable', False)):
                raise ResourceControlError(
                    'Service[%s] is not a restartable systemd unit' %
                    self._value(handle, 'serviceName'))
            unit = self._value(handle, 'value')
            properties = self.systemd.properties(unit)
            if properties.get('LoadState') == 'not-found':
                raise ResourceControlError('Systemd unit[%s] does not exist' % unit)
            if properties.get('ActiveState') != 'active':
                raise ResourceControlError('Systemd unit[%s] is not active' % unit)
            if self.systemd.configured_slice(unit) != slice_name:
                raise ResourceControlError('Systemd unit[%s] is not configured for slice[%s]' % (unit, slice_name))
            units.append(unit)
        if not units:
            raise ResourceControlError('At least one service handle is required')

        backend = self.backend_factory.cpu()
        slice_target = self._active_slice_target(backend, slice_name)
        backend.require_cpu_target(slice_target)

        for unit in units:
            self.systemd.restart(unit)
            properties = self.systemd.properties(unit)
            if (slice_target is not None
                    and not backend.contains(properties.get('ControlGroup'), slice_target)):
                raise ResourceControlError(
                    'Systemd unit[%s] did not enter slice[%s] after restart' %
                    (unit, slice_name))

    def _service_usage(self, handle, state):
        return {
            'serviceName': self._value(handle, 'serviceName'),
            'restartable': self._value(handle, 'restartable', False),
            'restartRequired': False,
            'state': state.value,
            'cpuSet': None,
            'cpuTime': None,
            'memory': None,
            'memoryLimit': None,
        }

    def _restart_required(self, backend, role_type, handle, state, current, slice_targets):
        if (state != ServiceState.RUNNING or self._value(handle, 'handleType') != 'SYSTEMD_UNIT'):
            return False
        slice_name = self.systemd.configured_slice(self._value(handle, 'value'))
        if slice_name is None:
            return False
        if slice_name not in slice_targets:
            properties = self.systemd.properties(slice_name)
            target = backend.find_target(properties.get('ControlGroup')) \
                if properties.get('ActiveState') == 'active' else None
            slice_targets[slice_name] = target
        target = slice_targets[slice_name]
        in_slice = target is not None and backend.is_descendant(current, target)
        managed = self._managed_unit_group(backend.root, role_type, self._value(handle, 'value'))
        cpu_restart_required = not in_slice and current != managed and not backend.has_processes(managed)
        memory_backend = self.backend_factory.find_memory()
        memory_target = self._active_slice_target(memory_backend, slice_name) if memory_backend is not None else None
        memory_limit = memory_backend.read_memory_limit(memory_target) if memory_target is not None else None
        memory_restart_required = (memory_limit or 0) > 0 and not memory_backend.contains(
            self.systemd.properties(self._value(handle, 'value')).get('ControlGroup'), memory_target)
        return cpu_restart_required or memory_restart_required

    def _inspect_target(self, backend, role_type, handle):
        handle_type = self._value(handle, 'handleType')
        if handle_type == 'SYSTEMD_UNIT':
            properties = self.systemd.properties(self._value(handle, 'value'))
            if properties.get('LoadState') == 'not-found':
                return ServiceState.NOT_FOUND, None
            if properties.get('ActiveState') != 'active':
                return ServiceState.INACTIVE, None
            control_group = properties.get('ControlGroup')
            if control_group:
                target = backend.target(control_group)
                if backend.existing_target(target) is not None:
                    return ServiceState.RUNNING, target
            managed = self._managed_unit_group(backend.root, role_type, self._value(handle, 'value'))
            if backend.has_processes(managed):
                return ServiceState.RUNNING, managed
            main_pid = properties.get('MainPID')
            if main_pid and re.match(r'^[1-9][0-9]*$', main_pid):
                return ServiceState.RUNNING, backend.process_group(main_pid)
            raise ResourceControlError('No control group was found for systemd unit[%s]' % self._value(handle, 'value'))
        raise ResourceControlError('Resource consumer handle type[%s] is unsupported' % handle_type)

    def _group_usage(self, backend, target, handle=None):
        root = backend.root
        cpu_set = backend.read_cpu_set(target)
        relative = os.path.relpath(target, root)
        control_group = None
        if (handle is not None and self._value(handle, 'handleType') == 'SYSTEMD_UNIT'):
            control_group = self.systemd.properties(self._value(handle, 'value')).get('ControlGroup')
        cpu_time = self._cpu_time(relative, control_group)
        memory, memory_limit = self._memory_usage(relative, control_group)
        return {'cpuSet': cpu_set, 'cpuTime': cpu_time, 'memory': memory, 'memoryLimit': memory_limit,}

    def _cpu_time(self, relative, control_group=None):
        if relative not in ('', '.'):
            for backend in self.backend_factory.cpu_accounting():
                value = backend.read_cpu_time(relative)
                if value is not None:
                    return value
        if not control_group:
            return None
        for backend in self.backend_factory.legacy_cpu_accounting():
            value = backend.read_cpu_time(control_group.lstrip('/'))
            if value is not None:
                return value
        return None

    def _memory_usage(self, relative, control_group=None):
        backend = self.backend_factory.find_memory()
        if backend is None:
            return None, None
        target = backend.target(relative)
        if control_group:
            current = backend.target(control_group.lstrip('/'))
            if backend.existing_target(current) is not None:
                target = current
        if backend.existing_target(target) is None:
            return None, None
        return backend.read_memory_usage(target), backend.read_memory_limit(target)

    def validate_cpu_set(self, cpu_set):
        return resource_utils.validate_cpu_set(cpu_set)

    def validate_memory_limit(self, memory_limit):
        if memory_limit is None:
            return None
        if (isinstance(memory_limit, bool)
                or not isinstance(memory_limit, int)
                or memory_limit < 0
                or memory_limit % resource_utils.MEBIBYTE != 0):
            raise ResourceControlError(
                'Memory limit[%s] must be zero or a positive multiple of '
                '1 MiB' % memory_limit)
        return memory_limit

    def _summarize_apply(self, results):
        expected = [result for result in results if result is not None]
        return {'synced': bool(expected) and all(expected)}

    def _summarize_release(self, results):
        return {'synced': all(result for result in results if result is not None)}

    def _cpu_matches(self, actual, desired):
        return desired is None or resource_utils.normalize(actual or '') == desired

    def _memory_matches(self, actual, desired):
        return desired is None or actual == desired or desired == 0 and actual is None

    def _resolve(self, backend, role_type, handle):
        handle_type = self._value(handle, 'handleType')
        if handle_type == 'SYSTEMD_UNIT':
            return self._resolve_systemd(backend, role_type, handle)
        raise ResourceControlError('Resource consumer handle type[%s] is unsupported' % handle_type)

    def _resolve_for_release(self, backend, role_type, handle):
        handle_type = self._value(handle, 'handleType')
        if handle_type == 'SYSTEMD_UNIT':
            return self._resolve_systemd_for_release(backend, role_type, handle)
        raise ResourceControlError('Resource consumer handle type[%s] is unsupported' % handle_type)

    def _resolve_systemd(self, backend, role_type, handle):
        root = backend.root
        unit = self._value(handle, 'value')
        managed_target = self._managed_unit_group(root, role_type, unit)
        properties = self.systemd.properties(unit)
        optional = self._value(handle, 'optional', False)
        if properties.get('LoadState') == 'not-found':
            if optional:
                return None
            raise ResourceControlError('Systemd unit[%s] does not exist' % unit)
        control_group = properties.get('ControlGroup')
        if not control_group:
            return None
        target = backend.target(control_group)
        if target == root:
            raise ResourceControlError('Systemd unit[%s] reported the root control group' % unit)
        if backend.existing_target(target) is not None:
            return target
        return self._resolve_systemd_fallback(backend, handle, control_group, managed_target)

    def _resolve_systemd_for_release(self, backend, role_type, handle):
        root = backend.root
        unit = self._value(handle, 'value')
        managed_target = self._managed_unit_group(root, role_type, unit)
        if backend.existing_target(managed_target) is not None:
            return managed_target
        properties = self.systemd.properties(unit)
        optional = self._value(handle, 'optional', False)
        if properties.get('LoadState') == 'not-found':
            if optional:
                return None
            raise ResourceControlError('Systemd unit[%s] does not exist' % unit)
        control_group = properties.get('ControlGroup')
        if not control_group:
            return None
        target = backend.target(control_group)
        if target == root:
            raise ResourceControlError('Systemd unit[%s] reported the root control group' % unit)
        return backend.existing_target(target)

    def _resolve_systemd_fallback(self, backend, handle, control_group, target):
        optional = self._value(handle, 'optional', False)
        source = self.systemd.legacy_control_group(control_group)
        if not backend.has_process_file(source):
            if optional:
                return None
            raise ResourceControlError('Systemd control group[%s] does not exist' % control_group)
        if not backend.has_processes(source):
            if optional:
                return None
            raise ResourceControlError('Systemd control group[%s] contains no processes' % control_group)

        backend.attach_processes(source, target)
        return target

    def _managed_unit_group(self, root, role_type, unit):
        return os.path.join(root, 'zstack-role-%s-unit-%s' % (self._safe_role(role_type), self._safe_role(unit)))

    def _isolation_mode(self, value):
        mode = 'SHARED' if value is None else value
        if mode not in ('SHARED', 'EXCLUSIVE'):
            raise ResourceControlError('Isolation mode[%s] must be SHARED or EXCLUSIVE' % mode)
        return mode

    def _apply_memory_limit(self, backend, cpu_target, desired, memory_backend):
        relative = os.path.relpath(cpu_target, backend.root)
        memory_target = memory_backend.target(relative)
        return memory_backend.apply_memory(memory_target, desired, cpu_target)

    def _safe_role(self, role_type):
        value = re.sub(r'[^a-zA-Z0-9_.-]', '-', role_type or '')
        if not value:
            raise ResourceControlError('Role type must contain at least one valid path character')
        return value

    @staticmethod
    def _value(source, name, default=None):
        if isinstance(source, dict):
            return source.get(name, default)
        return getattr(source, name, default)

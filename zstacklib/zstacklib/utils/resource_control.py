import os
import re
import stat
import subprocess
import tempfile


class ResourceControlError(Exception):
    pass


class ResourceControlManager(object):
    CGROUP_V2_ROOT = '/sys/fs/cgroup'
    CGROUP_V1_ROOT = '/sys/fs/cgroup/cpuset'
    CGROUP_V1_MEMORY_ROOT = '/sys/fs/cgroup/memory'
    CGROUP_SYSTEMD_V1_ROOT = '/sys/fs/cgroup/systemd'
    CGROUP_V1_CPUACCT_ROOTS = (
        '/sys/fs/cgroup/cpu,cpuacct', '/sys/fs/cgroup/cpuacct')
    PROC_MOUNTS = '/proc/mounts'
    CPU_ONLINE = '/sys/devices/system/cpu/online'
    SYSTEMD_QUERY_TIMEOUT = 5
    MEBIBYTE = 1024 * 1024
    PROCESS_MOVE_ATTEMPTS = 3
    SYSTEMD_UNIT_ROOT = '/etc/systemd/system'
    SYSTEMD_DROP_IN = '50-zstack-resource-assignment.conf'

    def get_shared_cpu_num(self):
        try:
            backend, root = self._backend()
        except ResourceControlError as error:
            if self._reason_code(error) == 'RESOURCE_CONTROL_UNAVAILABLE':
                return None
            raise
        if backend != 'CGROUP_V2_CPUSET':
            return None
        cpu_set = self._normalize(self._read(
            os.path.join(root, 'cpuset.cpus.effective')))
        if not cpu_set:
            raise ResourceControlError('RESOURCE_CONTROL_CPUSET_EMPTY')
        return self._count(cpu_set)

    def apply(self, role_type, cpu_set, handles, operation='APPLY', memory=None,
              slice_name=None):
        enabled = operation != 'RELEASE'
        desired = self.validate_cpu_set(cpu_set, enabled)
        memory = self.validate_memory_limit(memory)
        desired_memory = None if memory is None else memory if enabled else 0
        try:
            backend, root = self._backend()
        except ResourceControlError as error:
            reason = self._reason_code(error)
            if reason == 'RESOURCE_CONTROL_UNAVAILABLE':
                return self._unavailable()
            raise
        memory_backend = None
        memory_root = None
        if memory is not None:
            try:
                memory_backend, memory_root = self._memory_backend()
            except ResourceControlError as error:
                if self._reason_code(error) != 'MEMORY_CONTROLLER_UNAVAILABLE':
                    raise
        if (slice_name
                and any(self._value(handle, 'handleType') == 'SYSTEMD_UNIT'
                        for handle in handles or [])):
            return self._apply_systemd_slice(
                root, backend, role_type, slice_name, handles,
                desired, desired_memory, enabled, memory is not None,
                memory_backend, memory_root)
        results = []

        for handle in handles or []:
            try:
                target = self._resolve(
                    root, backend, role_type, handle, enabled)
            except ResourceControlError:
                results.append(self._result('ERROR', None, None))
                continue
            if target is None:
                results.append(self._result('SKIPPED', None, None))
                continue
            try:
                actual = self._apply_to_group(root, backend, target, desired, enabled)
                actual_memory = None
                if memory is not None:
                    _, actual_memory = self._apply_memory_limit(
                        root, target, desired_memory,
                        memory_backend, memory_root)
                results.append(self._result(
                    'READY' if enabled else 'DISABLED', actual, actual_memory))
            except ResourceControlError:
                results.append(self._result('ERROR', None, None))

        return self._summarize(
            results, 'READY' if enabled else 'DISABLED',
            desired, desired_memory)

    def _apply_systemd_slice(
            self, root, backend, role_type, slice_name, handles,
            desired, desired_memory, enabled, manage_memory,
            memory_backend, memory_root):
        if (enabled and manage_memory and desired_memory
                and memory_backend is not None):
            self._validate_active_slice_memory(
                root, slice_name, desired_memory,
                memory_backend, memory_root)
        changed = self._configure_systemd_slice(
            backend, memory_backend, slice_name, desired, desired_memory,
            enabled, manage_memory)
        for handle in handles or []:
            if self._value(handle, 'handleType') != 'SYSTEMD_UNIT':
                continue
            changed = self._configure_systemd_service(
                handle, slice_name, enabled) or changed
        legacy_cpu_results = {}
        try:
            slice_target = self._active_slice_target(
                root, slice_name, enabled)
        except ResourceControlError as error:
            if (self._reason_code(error)
                    != 'SYSTEMD_CONTROL_GROUP_NOT_FOUND'):
                raise
            slice_target = None
            for index, handle in enumerate(handles or []):
                if self._value(handle, 'handleType') != 'SYSTEMD_UNIT':
                    continue
                legacy_cpu_results[index] = self._apply_non_systemd_handle(
                    root, backend, role_type, handle, desired,
                    None, enabled, False, None, None)
        actual = ''
        actual_memory = None
        memory_slice_target = None
        memory_error = manage_memory and memory_backend is None
        if slice_target is not None:
            actual = self._apply_to_group(
                root, backend, slice_target, desired, enabled)
        if manage_memory and not memory_error:
            try:
                memory_slice_target = self._active_controller_slice_target(
                    memory_root, slice_name)
                if memory_slice_target is not None:
                    _, actual_memory = self._apply_memory_target(
                        memory_backend, memory_root, memory_slice_target,
                        desired_memory, False, None)
            except ResourceControlError:
                memory_error = True
        if changed:
            self._systemctl(['daemon-reload'], 30)

        results = []
        for index, handle in enumerate(handles or []):
            if self._value(handle, 'handleType') != 'SYSTEMD_UNIT':
                results.append(self._apply_non_systemd_handle(
                    root, backend, role_type, handle, desired,
                    desired_memory, enabled, manage_memory,
                    memory_backend, memory_root))
                continue
            properties = self._systemd_properties(
                self._value(handle, 'value'))
            optional = self._value(handle, 'optional', False)
            if properties.get('LoadState') == 'not-found':
                results.append(self._result(
                    'SKIPPED' if optional else 'ERROR', None, None))
                continue
            if properties.get('ActiveState') != 'active':
                results.append(self._result(
                    'SKIPPED' if optional else 'ERROR', None, None))
                continue
            if not enabled:
                if (index in legacy_cpu_results
                        and legacy_cpu_results[index]['state'] != 'DISABLED'):
                    results.append(legacy_cpu_results[index])
                    continue
                if memory_error:
                    results.append(self._result('ERROR', None, None))
                else:
                    results.append(self._result(
                        'DISABLED', '', 0 if manage_memory else None))
                continue
            if legacy_cpu_results:
                cpu_result = legacy_cpu_results[index]
                if cpu_result['state'] in ('ERROR', 'SKIPPED'):
                    results.append(cpu_result)
                    continue
                service_cpu_set = cpu_result['cpuSet']
            else:
                current = self._systemd_target(
                    root, properties.get('ControlGroup'))
                if (slice_target is None
                        or not self._is_descendant(current, slice_target)):
                    results.append(self._result(
                        'PENDING_RESTART', None, None))
                    continue
                service_cpu_set = actual
            if memory_error:
                results.append(self._result('ERROR', None, None))
                continue
            if (manage_memory and memory_slice_target is not None
                    and not self._control_group_in_target(
                        memory_root, properties.get('ControlGroup'),
                        memory_slice_target)):
                results.append(self._result(
                    'PENDING_RESTART', None, None))
                continue
            results.append(self._result(
                'READY', service_cpu_set, actual_memory))
        return self._summarize(
            results, 'READY' if enabled else 'DISABLED',
            desired, desired_memory)

    def _validate_active_slice_memory(
            self, _cpu_root, slice_name, desired_memory,
            memory_backend, memory_root):
        properties = self._systemd_properties(slice_name)
        if properties.get('ActiveState') != 'active':
            return
        memory_target = self._systemd_target(
            memory_root, properties.get('ControlGroup'))
        usage = ('memory.current' if memory_backend == 'CGROUP_V2_MEMORY'
                 else 'memory.usage_in_bytes')
        self._validate_memory_limit_against_usage(
            os.path.join(memory_target, usage), desired_memory)

    def _apply_non_systemd_handle(
            self, root, backend, role_type, handle, desired,
            desired_memory, enabled, manage_memory,
            memory_backend, memory_root):
        try:
            target = self._resolve(
                root, backend, role_type, handle, enabled)
            if target is None:
                return self._result('SKIPPED', None, None)
            actual = self._apply_to_group(
                root, backend, target, desired, enabled)
            actual_memory = None
            if manage_memory:
                _, actual_memory = self._apply_memory_limit(
                    root, target, desired_memory,
                    memory_backend, memory_root)
            return self._result(
                'READY' if enabled else 'DISABLED', actual, actual_memory)
        except ResourceControlError:
            return self._result('ERROR', None, None)

    def _configure_systemd_slice(
            self, cpu_backend, memory_backend, slice_name, cpu_set, memory,
            enabled, manage_memory):
        path = self._drop_in_path(slice_name)
        if not enabled:
            return self._remove_drop_in(path)
        lines = ['[Slice]']
        if cpu_backend == 'CGROUP_V2_CPUSET':
            lines.append('AllowedCPUs=%s' % cpu_set)
        if manage_memory and memory_backend is not None:
            setting = ('MemoryMax' if memory_backend == 'CGROUP_V2_MEMORY'
                       else 'MemoryLimit')
            lines.append('%s=%s' % (setting,
                'infinity' if memory == 0 else memory))
        elif manage_memory and os.path.isfile(path):
            lines.extend(line for line in self._read(path).splitlines()
                         if line.startswith(('MemoryMax=', 'MemoryLimit=')))
        return self._write_drop_in(path, '\n'.join(lines) + '\n')

    def _configure_systemd_service(self, handle, slice_name, enabled):
        path = self._drop_in_path(self._value(handle, 'value'))
        if not enabled:
            return self._remove_drop_in(path)
        return self._write_drop_in(
            path, '[Service]\nSlice=%s\n' % slice_name)

    def _drop_in_path(self, unit):
        return os.path.join(
            self.SYSTEMD_UNIT_ROOT, unit + '.d', self.SYSTEMD_DROP_IN)

    def _write_drop_in(self, path, content):
        if os.path.isfile(path) and self._read(path) == content:
            return False
        directory = os.path.dirname(path)
        try:
            if not os.path.isdir(directory):
                os.makedirs(directory, mode=0o755)
            descriptor, temporary = tempfile.mkstemp(
                prefix='.zstack-resource-', dir=directory)
            try:
                with os.fdopen(descriptor, 'w') as stream:
                    stream.write(content)
                os.chmod(temporary, 0o644)
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return True
        except (IOError, OSError) as error:
            raise ResourceControlError(
                'SYSTEMD_DROP_IN_WRITE_FAILED:%s' % error)

    def _remove_drop_in(self, path):
        if not os.path.exists(path):
            return False
        try:
            os.unlink(path)
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
            return True
        except OSError as error:
            raise ResourceControlError(
                'SYSTEMD_DROP_IN_REMOVE_FAILED:%s' % error)

    def _active_slice_target(self, root, slice_name, enabled):
        properties = self._systemd_properties(slice_name)
        if enabled and properties.get('ActiveState') != 'active':
            self._systemctl(['start', slice_name], 30)
            properties = self._systemd_properties(slice_name)
        if properties.get('ActiveState') != 'active':
            return None
        return self._systemd_target(root, properties.get('ControlGroup'))

    def _active_controller_slice_target(self, root, slice_name):
        properties = self._systemd_properties(slice_name)
        if properties.get('ActiveState') != 'active':
            return None
        return self._systemd_target(root, properties.get('ControlGroup'))

    def _systemd_target(self, root, control_group):
        if not control_group:
            raise ResourceControlError('SYSTEMD_CONTROL_GROUP_MISSING')
        target = os.path.normpath(os.path.join(
            root, control_group.lstrip('/')))
        self._under_root(root, target)
        if target == root or not os.path.isdir(target):
            raise ResourceControlError('SYSTEMD_CONTROL_GROUP_NOT_FOUND')
        return target

    def _is_descendant(self, path, parent):
        return path == parent or path.startswith(parent + os.sep)

    def _control_group_in_target(self, root, control_group, target):
        try:
            current = self._systemd_target(root, control_group)
        except ResourceControlError:
            return False
        return self._is_descendant(current, target)

    def inspect(self, role_type, handles):
        try:
            backend, root = self._backend()
        except ResourceControlError:
            return [self._service_usage(handle, 'UNAVAILABLE')
                    for handle in handles or []]
        result = []
        slice_targets = {}
        for handle in handles or []:
            usage = self._service_usage(handle, 'UNAVAILABLE')
            try:
                state, target = self._inspect_target(
                    root, backend, role_type, handle)
                usage['state'] = state
                if target is not None:
                    usage['restartRequired'] = self._restart_required(
                        root, role_type, handle, state, target,
                        slice_targets)
                    usage.update(self._group_usage(
                        root, backend, target, handle))
            except ResourceControlError:
                pass
            result.append(usage)
        return result

    def inspect_systemd_slices(self, slice_names):
        handles = [{
            'handleType': 'SYSTEMD_UNIT',
            'value': name,
            'serviceName': name,
            'restartable': False,
        } for name in slice_names or []]
        usages = self.inspect('OBSERVATION', handles)
        return [{
            'cgroupName': usage.get('serviceName'),
            'cpuSet': usage.get('cpuSet'),
            'cpuTime': usage.get('cpuTime'),
            'memory': usage.get('memory'),
            'memoryLimit': usage.get('memoryLimit'),
        } for usage in usages if usage.get('state') == 'RUNNING']

    def restart(self, handles):
        units = []
        for handle in handles or []:
            if (self._value(handle, 'handleType') != 'SYSTEMD_UNIT'
                    or not self._value(handle, 'restartable', False)):
                raise ResourceControlError('SERVICE_RESTART_NOT_ALLOWED')
            unit = self._value(handle, 'value')
            properties = self._systemd_properties(unit)
            if properties.get('LoadState') == 'not-found':
                raise ResourceControlError('SYSTEMD_UNIT_NOT_FOUND')
            if properties.get('ActiveState') != 'active':
                raise ResourceControlError('SYSTEMD_UNIT_NOT_ACTIVE')
            units.append(unit)
        if not units:
            raise ResourceControlError('SERVICE_HANDLE_SET_INVALID')
        for unit in units:
            self._systemctl(['stop', unit], 120)
            try:
                self._start_active_unit(unit)
            except ResourceControlError as error:
                try:
                    self._start_active_unit(unit)
                except ResourceControlError as recovery_error:
                    raise ResourceControlError(
                        'SYSTEMD_UNIT_RESTART_FAILED:%s:%s:'
                        'RECOVERY_FAILED:%s' %
                        (unit, error, recovery_error))
                raise ResourceControlError(
                    'SYSTEMD_UNIT_RESTART_FAILED:%s:%s' % (unit, error))

    def _start_active_unit(self, unit):
        self._systemctl(['start', unit], 120)
        if self._systemd_properties(unit).get('ActiveState') != 'active':
            raise ResourceControlError('SYSTEMD_UNIT_NOT_ACTIVE')

    def _service_usage(self, handle, state):
        return {
            'serviceName': self._value(handle, 'serviceName'),
            'restartable': self._value(handle, 'restartable', False),
            'restartRequired': False,
            'state': state,
            'cpuSet': None,
            'cpuTime': None,
            'memory': None,
            'memoryLimit': None,
        }

    def _restart_required(self, root, role_type, handle, state, current,
                          slice_targets):
        if (state != 'RUNNING'
                or self._value(handle, 'handleType') != 'SYSTEMD_UNIT'):
            return False
        slice_name = self._configured_slice(self._value(handle, 'value'))
        if slice_name is None:
            return False
        managed = self._managed_unit_group(
            root, role_type, self._value(handle, 'value'))
        if current == managed or self._group_has_processes(managed):
            return False
        if slice_name not in slice_targets:
            target = None
            try:
                properties = self._systemd_properties(slice_name)
                if properties.get('ActiveState') == 'active':
                    target = self._systemd_target(
                        root, properties.get('ControlGroup'))
            except ResourceControlError:
                pass
            slice_targets[slice_name] = target
        target = slice_targets[slice_name]
        return target is None or not self._is_descendant(current, target)

    def _configured_slice(self, unit):
        path = self._drop_in_path(unit)
        if not os.path.isfile(path):
            return None
        try:
            for line in self._read(path).splitlines():
                value = line.strip()
                if not value.startswith('Slice='):
                    continue
                slice_name = value[len('Slice='):].strip()
                return (slice_name if re.match(
                    r'^[A-Za-z0-9_.@-]+\.slice$', slice_name) else None)
        except ResourceControlError:
            pass
        return None

    def _inspect_target(self, root, backend, role_type, handle):
        handle_type = self._value(handle, 'handleType')
        if handle_type == 'SYSTEMD_UNIT':
            properties = self._systemd_properties(
                self._value(handle, 'value'))
            if properties.get('LoadState') == 'not-found':
                return 'NOT_FOUND', None
            if properties.get('ActiveState') != 'active':
                return 'INACTIVE', None
            control_group = properties.get('ControlGroup')
            if control_group:
                target = os.path.normpath(os.path.join(
                    root, control_group.lstrip('/')))
                self._under_root(root, target)
                if os.path.isdir(target):
                    return 'RUNNING', target
            managed = self._managed_unit_group(
                root, role_type, self._value(handle, 'value'))
            if self._group_has_processes(managed):
                return 'RUNNING', managed
            main_pid = properties.get('MainPID')
            if main_pid and re.match(r'^[1-9][0-9]*$', main_pid):
                return 'RUNNING', self._process_group(
                    root, backend, main_pid)
            raise ResourceControlError('SYSTEMD_CONTROL_GROUP_NOT_FOUND')
        if handle_type == 'OWNER_PID_FILE':
            pid = self._pid_from_handle(handle)
            managed = self._managed_owner_group(root, role_type, handle)
            if self._group_has_processes(managed):
                return 'RUNNING', managed
            if pid is None:
                return 'NOT_FOUND', None
            target = self._process_group(root, backend, pid)
            return 'RUNNING', target
        raise ResourceControlError('HANDLE_TYPE_UNSUPPORTED')

    def _group_has_processes(self, target):
        process_file = os.path.join(target, 'cgroup.procs')
        return (os.path.isdir(target) and os.path.isfile(process_file)
                and bool(self._process_ids(process_file)))

    def _group_usage(self, root, backend, target, handle=None):
        cpu_set = self._effective_cpu_set(root, target)
        relative = os.path.relpath(target, root)
        control_group = None
        if (handle is not None
                and self._value(handle, 'handleType') == 'SYSTEMD_UNIT'):
            control_group = self._systemd_properties(
                self._value(handle, 'value')).get('ControlGroup')
        cpu_time = self._cpu_time(relative, control_group)
        memory, memory_limit = self._memory_usage(
            relative, control_group)
        return {
            'cpuSet': cpu_set,
            'cpuTime': cpu_time,
            'memory': memory,
            'memoryLimit': memory_limit,
        }

    def _effective_cpu_set(self, root, target):
        current = target
        while True:
            for name in ('cpuset.cpus.effective', 'cpuset.cpus'):
                path = os.path.join(current, name)
                if os.path.isfile(path):
                    value = self._normalize(self._read(path))
                    if value:
                        return value
            if current == root:
                raise ResourceControlError('RESOURCE_CONTROL_CPUSET_EMPTY')
            current = os.path.dirname(current)
            self._under_root(root, current)

    def _cpu_time(self, relative, control_group=None):
        if relative not in ('', '.'):
            for root in self._v2_roots():
                value = self._v2_cpu_time(
                    self._controller_target(root, relative))
                if value is not None:
                    return value
            value = self._v1_cpu_time(relative)
            if value is not None:
                return value
        if not control_group:
            return None
        return self._v1_cpu_time(control_group.lstrip('/'))

    def _memory_usage(self, relative, control_group=None):
        try:
            backend, root = self._memory_backend()
        except ResourceControlError as error:
            if self._reason_code(error) == 'MEMORY_CONTROLLER_UNAVAILABLE':
                return None, None
            raise
        target = self._controller_target(root, relative)
        if control_group:
            current = self._controller_target(
                root, control_group.lstrip('/'))
            if os.path.isdir(current):
                target = current
        if not os.path.isdir(target):
            return None, None
        if backend == 'CGROUP_V2_MEMORY':
            return (
                self._optional_numeric(os.path.join(target, 'memory.current')),
                self._effective_v2_memory_limit(root, target))
        return (
            self._optional_numeric(
                os.path.join(target, 'memory.usage_in_bytes')),
            self._effective_v1_memory_limit(root, target))

    def _v2_cpu_time(self, target):
        path = os.path.join(target, 'cpu.stat')
        if not os.path.isfile(path):
            return None
        for line in self._read(path).splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[0] == 'usage_usec':
                return self._parse_memory(fields[1]) * 1000
        return None

    def _v1_cpu_time(self, relative):
        for root in self.CGROUP_V1_CPUACCT_ROOTS:
            path = os.path.join(root, relative, 'cpuacct.usage')
            if os.path.isfile(path):
                return self._parse_memory(self._read(path).strip())
        return None

    def _optional_numeric(self, path):
        return self._parse_memory(self._read(path).strip()) \
            if os.path.isfile(path) else None

    def _optional_limit(self, path):
        if not os.path.isfile(path):
            return None
        value = self._read(path).strip()
        return 0 if value == 'max' else self._parse_memory(value)

    def _effective_v2_memory_limit(self, root, target):
        limits = []
        current = target
        while True:
            path = os.path.join(current, 'memory.max')
            if os.path.isfile(path):
                value = self._read(path).strip()
                if value != 'max':
                    limits.append(self._parse_memory(value))
            if current == root:
                break
            current = os.path.dirname(current)
            self._under_root(root, current)
        return min(limits) if limits else 0

    def _effective_v1_memory_limit(self, root, target):
        root_limit_path = os.path.join(root, 'memory.limit_in_bytes')
        if not os.path.isfile(root_limit_path):
            return None
        root_limit = self._parse_memory(
            self._read(root_limit_path).strip())
        self._under_root(root, target)
        limits = []
        current = target
        while True:
            path = os.path.join(current, 'memory.limit_in_bytes')
            if os.path.isfile(path):
                limits.append(self._parse_memory(self._read(path).strip()))
            if current == root:
                break
            current = os.path.dirname(current)
            self._under_root(root, current)
        if not limits:
            return None
        effective = min(limits)
        return 0 if effective >= root_limit else effective

    def _process_group(self, root, backend, pid):
        for line in self._read('/proc/%s/cgroup' % pid).splitlines():
            fields = line.split(':', 2)
            if len(fields) != 3:
                continue
            if (backend == 'CGROUP_V2_CPUSET' and fields[0] == '0'
                    or backend == 'CGROUP_V1_CPUSET'
                    and 'cpuset' in fields[1].split(',')):
                target = os.path.normpath(os.path.join(
                    root, fields[2].lstrip('/')))
                self._under_root(root, target)
                if os.path.isdir(target):
                    return target
        raise ResourceControlError('PROCESS_CONTROL_GROUP_NOT_FOUND')

    def validate_cpu_set(self, cpu_set, enabled=True):
        try:
            normalized = self._normalize(
                '' if cpu_set is None else cpu_set)
        except (AttributeError, TypeError, ValueError):
            raise ResourceControlError('CPUSET_FORMAT_INVALID')
        if enabled and not normalized:
            raise ResourceControlError('CPUSET_EMPTY')
        if normalized:
            online = self._normalize(self._read(self.CPU_ONLINE))
            if not self._is_subset(normalized, online):
                raise ResourceControlError('CPUSET_OUT_OF_RANGE')
        return normalized if enabled else ''

    def validate_memory_limit(self, memory_limit):
        if memory_limit is None:
            return None
        if (isinstance(memory_limit, bool)
                or not isinstance(memory_limit, int)
                or memory_limit < 0
                or memory_limit % self.MEBIBYTE != 0):
            raise ResourceControlError('MEMORY_LIMIT_INVALID')
        return memory_limit

    def _unavailable(self):
        return {'synced': False}

    def _summarize(
            self, results, required_state, desired_cpu_set, desired_memory):
        expected = 0
        synced = True

        for result in results:
            if result.get('state') == 'SKIPPED':
                continue
            expected += 1
            actual_cpu_set = self._normalize(result.get('cpuSet') or '')
            actual_memory = result.get('memory')
            memory_matches = (desired_memory is None
                              or actual_memory == desired_memory
                              or desired_memory == 0 and actual_memory is None)
            if (result.get('state') != required_state
                    or actual_cpu_set != desired_cpu_set
                    or not memory_matches):
                synced = False
        if required_state == 'READY' and expected == 0:
            synced = False
        return {'synced': synced}

    def _result(self, state, cpu_set, memory):
        return {
            'state': state,
            'cpuSet': cpu_set,
            'memory': memory,
        }

    def _backend(self):
        for root in self._v2_roots():
            controllers = os.path.join(root, 'cgroup.controllers')
            values = self._read(controllers).split()
            if 'cpuset' in values or os.path.isfile(os.path.join(
                    root, 'cpuset.cpus.effective')):
                return 'CGROUP_V2_CPUSET', root
        if os.path.isfile(os.path.join(self.CGROUP_V1_ROOT, 'cpuset.cpus')):
            return 'CGROUP_V1_CPUSET', self.CGROUP_V1_ROOT
        raise ResourceControlError('RESOURCE_CONTROL_UNAVAILABLE')

    def _memory_backend(self):
        for root in self._v2_roots():
            controllers = os.path.join(root, 'cgroup.controllers')
            values = self._read(controllers).split()
            if ('memory' in values
                    or os.path.isfile(os.path.join(root, 'memory.max'))):
                return 'CGROUP_V2_MEMORY', root
        root_limit = os.path.join(
            self.CGROUP_V1_MEMORY_ROOT, 'memory.limit_in_bytes')
        if os.path.isfile(root_limit):
            return 'CGROUP_V1_MEMORY', self.CGROUP_V1_MEMORY_ROOT
        raise ResourceControlError('MEMORY_CONTROLLER_UNAVAILABLE')

    def _controller_target(self, root, relative):
        target = os.path.normpath(os.path.join(root, relative))
        self._under_root(root, target)
        return target

    def _v2_roots(self):
        roots = []
        if os.path.isfile(os.path.join(
                self.CGROUP_V2_ROOT, 'cgroup.controllers')):
            roots.append(self.CGROUP_V2_ROOT)
        if not os.path.isfile(self.PROC_MOUNTS):
            return roots
        for line in self._read(self.PROC_MOUNTS).splitlines():
            fields = line.split()
            if len(fields) < 4 or fields[2] != 'cgroup2':
                continue
            if 'rw' not in fields[3].split(','):
                continue
            root = self._decode_mount_path(fields[1])
            if root not in roots and os.path.isfile(os.path.join(
                    root, 'cgroup.controllers')):
                roots.append(root)
        return roots

    def _resolve(self, root, backend, role_type, handle, enabled):
        handle_type = self._value(handle, 'handleType')
        if handle_type == 'SYSTEMD_UNIT':
            return self._resolve_systemd(
                root, backend, role_type, handle, enabled)
        if handle_type == 'OWNER_PID_FILE':
            return self._resolve_pid_file(
                root, backend, role_type, handle, enabled)
        raise ResourceControlError('HANDLE_TYPE_UNSUPPORTED')

    def _resolve_systemd(self, root, backend, role_type, handle, enabled):
        unit = self._value(handle, 'value')
        managed_target = self._managed_unit_group(root, role_type, unit)
        if not enabled and os.path.isdir(managed_target):
            return managed_target
        properties = self._systemd_properties(unit)
        optional = self._value(handle, 'optional', False)
        if properties.get('LoadState') == 'not-found':
            if optional:
                return None
            raise ResourceControlError('SYSTEMD_UNIT_NOT_FOUND')
        if properties.get('ActiveState') != 'active':
            if not enabled and optional:
                return None
            raise ResourceControlError('SYSTEMD_UNIT_NOT_ACTIVE')
        control_group = properties.get('ControlGroup')
        if not control_group:
            raise ResourceControlError('SYSTEMD_CONTROL_GROUP_MISSING')
        target = os.path.normpath(os.path.join(root, control_group.lstrip('/')))
        self._under_root(root, target)
        if target == root:
            raise ResourceControlError('SYSTEMD_CONTROL_GROUP_INVALID')
        if os.path.isdir(target):
            return target
        return self._resolve_systemd_fallback(
            root, backend, role_type, handle, control_group, optional,
            enabled, managed_target)

    def _resolve_systemd_fallback(
            self, root, backend, role_type, handle, control_group, optional,
            enabled, target):
        if not enabled:
            return None
        source = os.path.normpath(os.path.join(
            self.CGROUP_SYSTEMD_V1_ROOT, control_group.lstrip('/')))
        self._under_root(self.CGROUP_SYSTEMD_V1_ROOT, source)
        process_file = os.path.join(source, 'cgroup.procs')
        if not os.path.isfile(process_file):
            if optional:
                return None
            raise ResourceControlError('SYSTEMD_CONTROL_GROUP_NOT_FOUND')
        pids = [value for value in self._read(process_file).split()
                if re.match(r'^[1-9][0-9]*$', value)]
        if not pids:
            if optional:
                return None
            raise ResourceControlError('SYSTEMD_CONTROL_GROUP_EMPTY')

        self._mkdir(target)
        self._enable_v2_path(root, target, backend)
        self._initialize_mems(root, target, backend)
        self._initialize_cpus(target, backend)
        target_process_file = os.path.join(target, 'cgroup.procs')
        self._move_processes(
            process_file, target_process_file,
            'SYSTEMD_CONTROL_GROUP_NOT_FOUND',
            'SYSTEMD_PROCESS_MOVE_FAILED')
        return target

    def _resolve_pid_file(
            self, root, backend, role_type, handle, enabled):
        target = self._managed_owner_group(root, role_type, handle)
        if not enabled:
            return target if os.path.isdir(target) else None
        pid = self._pid_from_handle(handle)

        self._mkdir(target)
        self._enable_v2_path(root, target, backend)
        self._initialize_mems(root, target, backend)
        self._initialize_cpus(target, backend)
        process_file = os.path.join(target, 'cgroup.procs')
        self._write(process_file, str(pid))
        if str(pid) not in self._process_ids(process_file):
            raise ResourceControlError('PID_PROCESS_MOVE_FAILED')
        return target

    def _pid_from_handle(self, handle):
        pid_file = self._value(handle, 'value')
        expected = self._value(handle, 'expectedCommandToken')
        try:
            info = os.lstat(pid_file)
        except OSError:
            if self._value(handle, 'optional', False):
                return None
            raise ResourceControlError('PID_FILE_NOT_FOUND')
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ResourceControlError('PID_FILE_NOT_REGULAR')
        content = self._read(pid_file).strip()
        if not re.match(r'^[1-9][0-9]*$', content):
            raise ResourceControlError('PID_FILE_FORMAT_INVALID')
        pid = int(content)
        proc_dir = '/proc/%s' % pid
        if not os.path.isdir(proc_dir):
            raise ResourceControlError('PID_NOT_RUNNING')
        process_uid = os.stat(proc_dir).st_uid
        if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise ResourceControlError('PID_FILE_PERMISSION_INVALID')
        if info.st_mtime + 1 < self._process_start_time(pid):
            raise ResourceControlError('PID_FILE_STALE')
        if info.st_uid not in (0, process_uid):
            raise ResourceControlError('PID_FILE_OWNER_MISMATCH')
        if expected and expected not in self._read(os.path.join(proc_dir, 'cmdline')).replace('\x00', ' '):
            raise ResourceControlError('PID_COMMAND_MISMATCH')
        return pid

    def _managed_unit_group(self, root, role_type, unit):
        return os.path.join(
            root, 'zstack-role-%s-unit-%s' % (
                self._safe_role(role_type), self._safe_role(unit)))

    def _managed_owner_group(self, root, role_type, handle):
        identity = (self._value(handle, 'consumerKey')
                    or self._value(handle, 'value'))
        return os.path.join(
            root, 'zstack-role-%s-owner-%s' % (
                self._safe_role(role_type), self._safe_role(identity)))

    def _apply_to_group(self, root, backend, target, desired, enabled):
        self._enable_v2_path(root, target, backend)
        self._initialize_mems(root, target, backend)
        cpu_file = os.path.join(target, 'cpuset.cpus')
        if not os.path.isfile(cpu_file):
            raise ResourceControlError('CPUSET_CONTROLLER_NOT_DELEGATED')
        value = desired
        if not enabled:
            if (backend == 'CGROUP_V2_CPUSET'
                    and self._managed_group(root, target)):
                self._move_processes_to_parent(target)
                value = ''
            else:
                value = self._parent_cpu_set(target, backend)
        configured = self._normalize(self._read(cpu_file))
        if configured != value:
            self._write(cpu_file, '\n' if not value and backend == 'CGROUP_V2_CPUSET' else value)
        if not enabled:
            if self._normalize(self._read(cpu_file)) != value:
                raise ResourceControlError('CPUSET_RELEASE_MISMATCH')
            return ''
        effective_file = os.path.join(target, 'cpuset.cpus.effective')
        actual = self._read(effective_file if os.path.isfile(effective_file) else cpu_file)
        return self._normalize(actual)

    def _apply_memory_limit(
            self, cpu_root, cpu_target, desired,
            memory_backend=None, memory_root=None):
        if memory_backend is None or memory_root is None:
            memory_backend, memory_root = self._memory_backend()
        relative = os.path.relpath(cpu_target, cpu_root)
        memory_target = self._controller_target(memory_root, relative)
        managed = self._managed_group(cpu_root, cpu_target)
        return self._apply_memory_target(
            memory_backend, memory_root, memory_target, desired,
            managed, cpu_target)

    def _apply_memory_target(
            self, memory_backend, memory_root, memory_target, desired,
            managed, cpu_target):
        if memory_backend == 'CGROUP_V2_MEMORY':
            if not os.path.isdir(memory_target):
                if not managed or desired == 0:
                    raise ResourceControlError('MEMORY_CONTROLLER_UNAVAILABLE')
                self._mkdir(memory_target)
            self._enable_v2_memory_path(memory_root, memory_target)
            limit_file = os.path.join(memory_target, 'memory.max')
            if not os.path.isfile(limit_file):
                raise ResourceControlError('MEMORY_CONTROLLER_UNAVAILABLE')
            if (managed and cpu_target != memory_target
                    and desired > 0):
                self._move_process_file(
                    os.path.join(cpu_target, 'cgroup.procs'),
                    os.path.join(memory_target, 'cgroup.procs'))
            value = 'max' if desired == 0 else str(desired)
            if self._read(limit_file).strip() != value:
                self._validate_memory_limit_against_usage(
                    os.path.join(memory_target, 'memory.current'), desired)
                self._write(limit_file, value)
            actual = self._read(limit_file).strip()
            if actual != value:
                raise ResourceControlError('MEMORY_LIMIT_MISMATCH')
            if (managed and cpu_target != memory_target
                    and desired == 0):
                self._move_process_file(
                    os.path.join(memory_target, 'cgroup.procs'),
                    os.path.join(os.path.dirname(memory_target), 'cgroup.procs'))
            return 'CGROUP_V2_MEMORY', 0 if actual == 'max' else self._parse_memory(actual)

        root_limit = os.path.join(memory_root, 'memory.limit_in_bytes')
        if not os.path.isfile(root_limit):
            raise ResourceControlError('MEMORY_CONTROLLER_UNAVAILABLE')
        if not os.path.isdir(memory_target):
            if not managed or desired == 0:
                raise ResourceControlError('MEMORY_CONTROLLER_UNAVAILABLE')
            self._mkdir(memory_target)
        limit_file = os.path.join(memory_target, 'memory.limit_in_bytes')
        if not os.path.isfile(limit_file):
            raise ResourceControlError('MEMORY_CONTROLLER_UNAVAILABLE')
        if managed and desired > 0:
            self._move_process_file(
                os.path.join(cpu_target, 'cgroup.procs'),
                os.path.join(memory_target, 'cgroup.procs'))
        value = (self._read(root_limit).strip()
                 if desired == 0 else str(desired))
        if self._read(limit_file).strip() != value:
            self._validate_memory_limit_against_usage(
                os.path.join(memory_target, 'memory.usage_in_bytes'), desired)
            self._write(limit_file, value)
        if self._read(limit_file).strip() != value:
            raise ResourceControlError('MEMORY_LIMIT_MISMATCH')
        if managed and desired == 0:
            self._move_process_file(
                os.path.join(memory_target, 'cgroup.procs'),
                os.path.join(os.path.dirname(memory_target), 'cgroup.procs'))
        return 'CGROUP_V1_MEMORY', 0 if desired == 0 else self._parse_memory(
            self._read(limit_file).strip())

    def _validate_memory_limit_against_usage(self, usage_file, desired):
        if desired == 0:
            return
        current = self._parse_memory(self._read(usage_file).strip())
        current = max(current, self._resident_memory_usage(
            os.path.join(os.path.dirname(usage_file), 'cgroup.procs')))
        if desired < current:
            raise ResourceControlError('MEMORY_LIMIT_BELOW_CURRENT_USAGE')

    def _resident_memory_usage(self, process_file):
        if not os.path.isfile(process_file):
            return 0
        total = 0
        for pid in self._process_ids(process_file):
            status_file = '/proc/%s/status' % pid
            if not os.path.isfile(status_file):
                continue
            try:
                status = self._read(status_file)
            except ResourceControlError:
                if not os.path.isdir('/proc/%s' % pid):
                    continue
                raise
            match = re.search(r'^VmRSS:\s+([0-9]+)\s+kB$', status, re.MULTILINE)
            if match:
                total += int(match.group(1)) * 1024
        return total

    def _enable_v2_memory_path(self, root, target):
        if os.path.isfile(os.path.join(target, 'memory.max')):
            return
        relative = os.path.relpath(target, root)
        current = root
        for part in [] if relative == '.' else relative.split(os.sep):
            child = os.path.join(current, part)
            if not os.path.isfile(os.path.join(child, 'memory.max')):
                controllers = os.path.join(current, 'cgroup.controllers')
                control = os.path.join(current, 'cgroup.subtree_control')
                if (not os.path.isfile(controllers)
                        or 'memory' not in self._read(controllers).split()
                        or not os.path.isfile(control)):
                    raise ResourceControlError('MEMORY_CONTROLLER_UNAVAILABLE')
                self._write(control, '+memory')
            current = child

    def _move_process_file(self, source, destination):
        self._move_processes(
            source, destination,
            'MEMORY_CONTROLLER_UNAVAILABLE', 'MEMORY_LIMIT_MISMATCH')

    def _move_processes_to_parent(self, target):
        self._move_processes(
            os.path.join(target, 'cgroup.procs'),
            os.path.join(os.path.dirname(target), 'cgroup.procs'),
            'CPUSET_CONTROLLER_NOT_DELEGATED', 'CPUSET_RELEASE_MISMATCH')

    def _move_processes(self, source, destination,
                        unavailable_reason, mismatch_reason):
        if not os.path.isfile(source) or not os.path.isfile(destination):
            raise ResourceControlError(unavailable_reason)
        for _ in range(self.PROCESS_MOVE_ATTEMPTS):
            destination_pids = set(self._process_ids(destination))
            for pid in self._process_ids(source):
                if (pid in destination_pids
                        or not os.path.isdir('/proc/%s' % pid)):
                    continue
                try:
                    self._write(destination, pid)
                except ResourceControlError:
                    if os.path.isdir('/proc/%s' % pid):
                        raise

            destination_pids = set(self._process_ids(destination))
            remaining = [
                pid for pid in self._process_ids(source)
                if os.path.isdir('/proc/%s' % pid)
                and pid not in destination_pids
            ]
            if not remaining:
                return
        raise ResourceControlError(mismatch_reason)

    def _process_ids(self, path):
        return [pid for pid in self._read(path).split()
                if re.match(r'^[1-9][0-9]*$', pid)]

    def _parse_memory(self, value):
        if not re.match(r'^[0-9]+$', value or ''):
            raise ResourceControlError('MEMORY_LIMIT_INVALID')
        return int(value)

    def _managed_group(self, root, target):
        relative = os.path.relpath(target, root)
        return relative != '.' and relative.split(os.sep, 1)[0].startswith(
            'zstack-role-')

    def _enable_v2_path(self, root, target, backend):
        if backend != 'CGROUP_V2_CPUSET':
            return
        relative = os.path.relpath(target, root)
        current = root
        for part in [] if relative == '.' else relative.split(os.sep):
            child = os.path.join(current, part)
            if not os.path.isfile(os.path.join(child, 'cpuset.cpus')):
                control = os.path.join(current, 'cgroup.subtree_control')
                if not os.path.isfile(control):
                    raise ResourceControlError('CGROUP_V2_SUBTREE_CONTROL_MISSING')
                self._write(control, '+cpuset')
            current = child

    def _initialize_mems(self, root, target, backend):
        mems = os.path.join(target, 'cpuset.mems')
        if not os.path.isfile(mems) or self._read(mems).strip():
            return
        parent = os.path.dirname(target)
        source = os.path.join(parent, 'cpuset.mems.effective')
        if not os.path.isfile(source):
            source = os.path.join(parent, 'cpuset.mems')
        value = self._read(source).strip()
        if not value:
            raise ResourceControlError('CPUSET_MEMS_EMPTY')
        self._write(mems, value)

    def _initialize_cpus(self, target, backend):
        if backend != 'CGROUP_V1_CPUSET':
            return
        cpus = os.path.join(target, 'cpuset.cpus')
        if self._read(cpus).strip():
            return
        self._write(cpus, self._parent_cpu_set(target, backend))

    def _parent_cpu_set(self, target, backend):
        parent = os.path.dirname(target)
        source = os.path.join(parent, 'cpuset.cpus.effective')
        if not os.path.isfile(source):
            source = os.path.join(parent, 'cpuset.cpus')
        value = self._normalize(self._read(source))
        if not value:
            raise ResourceControlError('PARENT_CPUSET_EMPTY')
        return value

    def _process_start_time(self, pid):
        boot_time = None
        for line in self._read('/proc/stat').splitlines():
            if line.startswith('btime '):
                try:
                    boot_time = int(line.split()[1])
                except (IndexError, ValueError):
                    raise ResourceControlError('PID_START_TIME_UNAVAILABLE')
                break
        stat_fields = self._read('/proc/%s/stat' % pid)
        command_end = stat_fields.rfind(')')
        if boot_time is None or command_end < 0:
            raise ResourceControlError('PID_START_TIME_UNAVAILABLE')
        fields = stat_fields[command_end + 1:].split()
        if len(fields) <= 19:
            raise ResourceControlError('PID_START_TIME_UNAVAILABLE')
        try:
            start_ticks = int(fields[19])
            clock_ticks = os.sysconf('SC_CLK_TCK')
            if clock_ticks <= 0:
                raise ResourceControlError('PID_START_TIME_UNAVAILABLE')
            return boot_time + float(start_ticks) / clock_ticks
        except (TypeError, ValueError, OSError, ZeroDivisionError):
            raise ResourceControlError('PID_START_TIME_UNAVAILABLE')

    def _systemd_properties(self, unit):
        output = self._systemctl([
            'show', unit, '--property=LoadState',
            '--property=ActiveState', '--property=ControlGroup',
            '--property=MainPID'
        ], self.SYSTEMD_QUERY_TIMEOUT)
        result = {}
        for line in output.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                result[key] = value
        return result

    def _systemctl(self, arguments, timeout):
        try:
            process = subprocess.Popen(
                ['systemctl'] + list(arguments),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as error:
            raise ResourceControlError('SYSTEMD_QUERY_FAILED:%s' % error)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise ResourceControlError('SYSTEMD_QUERY_TIMEOUT')
        if process.returncode != 0:
            raise ResourceControlError('SYSTEMD_QUERY_FAILED:%s' % self._text(stderr).strip())
        return self._text(stdout)

    def _mkdir(self, path):
        try:
            os.makedirs(path)
        except OSError:
            if not os.path.isdir(path):
                raise ResourceControlError('CGROUP_CREATE_FAILED')

    def _read(self, path):
        try:
            with open(path, 'rb') as stream:
                return self._text(stream.read())
        except (IOError, OSError) as error:
            raise ResourceControlError('READ_FAILED:%s:%s' % (path, error))

    def _write(self, path, value):
        try:
            with open(path, 'wb') as stream:
                stream.write(value.encode('ascii'))
        except (IOError, OSError) as error:
            raise ResourceControlError('WRITE_FAILED:%s:%s' % (path, error))

    def _normalize(self, value):
        text = self._text(value).strip()
        if not text:
            return ''
        ranges = []
        for token in text.split(','):
            if re.match(r'^[0-9]+$', token):
                if len(token) > 10:
                    raise ResourceControlError('CPUSET_FORMAT_INVALID')
                cpu = int(token)
                ranges.append((cpu, cpu))
                continue
            match = re.match(r'^([0-9]+)-([0-9]+)$', token)
            if not match or len(match.group(1)) > 10 or len(match.group(2)) > 10:
                raise ResourceControlError('CPUSET_FORMAT_INVALID')
            start = int(match.group(1))
            end = int(match.group(2))
            if start > end:
                raise ResourceControlError('CPUSET_FORMAT_INVALID')
            ranges.append((start, end))

        merged = []
        for start, end in sorted(ranges):
            if not merged or start > merged[-1][1] + 1:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        return ','.join(
            str(start) if start == end else '%s-%s' % (start, end)
            for start, end in merged)

    def _count(self, value):
        count = 0
        for token in self._normalize(value).split(','):
            if '-' not in token:
                count += 1
                continue
            start, end = token.split('-', 1)
            count += int(end) - int(start) + 1
        return count

    def _is_subset(self, candidate, allowed):
        allowed_ranges = self._ranges(allowed)
        allowed_index = 0
        for start, end in self._ranges(candidate):
            while (allowed_index < len(allowed_ranges)
                   and allowed_ranges[allowed_index][1] < start):
                allowed_index += 1
            if (allowed_index >= len(allowed_ranges)
                    or allowed_ranges[allowed_index][0] > start
                    or allowed_ranges[allowed_index][1] < end):
                return False
        return True

    def _ranges(self, value):
        result = []
        for token in self._normalize(value).split(','):
            if '-' in token:
                start, end = token.split('-', 1)
                result.append((int(start), int(end)))
            elif token:
                cpu = int(token)
                result.append((cpu, cpu))
        return result

    def _under_root(self, root, path):
        if path != root and not path.startswith(root + os.sep):
            raise ResourceControlError('CONTROL_GROUP_PATH_INVALID')

    def _safe_role(self, role_type):
        value = re.sub(r'[^a-zA-Z0-9_.-]', '-', role_type or '')
        if not value:
            raise ResourceControlError('ROLE_TYPE_INVALID')
        return value

    def _decode_mount_path(self, value):
        return value.replace('\\040', ' ').replace(
            '\\011', '\t').replace('\\012', '\n').replace('\\134', '\\')

    def _value(self, source, name, default=None):
        if isinstance(source, dict):
            return source.get(name, default)
        return getattr(source, name, default)

    def _text(self, value):
        if isinstance(value, bytes):
            return value.decode('utf-8', 'replace')
        return value

    def _reason_code(self, error):
        message = str(error)
        return message.split(':', 1)[0] if message else 'RESOURCE_CONTROL_ERROR'

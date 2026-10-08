import os
import re
import subprocess
import tempfile

if __package__:
    from . import resource_control_utils as resource_utils
    from .resource_control_utils import ResourceControlError
else:
    import resource_control_utils as resource_utils
    from resource_control_utils import ResourceControlError


class SystemdResourceControlUtils(object):
    CGROUP_SYSTEMD_V1_ROOT = '/sys/fs/cgroup/systemd'
    SYSTEMD_QUERY_TIMEOUT = 5
    SYSTEMD_OPERATION_TIMEOUT = 30
    SERVICE_RESTART_TIMEOUT = 120
    MAX_SYSTEMD_UNIT_NAME_TAIL_LENGTH = 248
    DROP_IN_DIRECTORY_MODE = 0o755
    DROP_IN_FILE_MODE = 0o644
    SYSTEMD_UNIT_ROOT = '/etc/systemd/system'
    SYSTEMD_DROP_IN = '50-zstack-resource-assignment.conf'
    SLICE_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.@:-]{0,%s}\.slice$' % MAX_SYSTEMD_UNIT_NAME_TAIL_LENGTH)
    SYSTEMD_UNIT_PATTERN = re.compile(
        r'^[A-Za-z0-9][A-Za-z0-9_.@:-]{0,%s}\.service$' % MAX_SYSTEMD_UNIT_NAME_TAIL_LENGTH)

    def configure_slice(self, slice_name, cpu_property, cpu_set, memory_property, memory):
        path = self._drop_in_path(slice_name)
        lines = ['[Slice]']
        if cpu_set is not None and cpu_property is not None:
            lines.append('%s=%s' % (cpu_property, cpu_set))
        if memory is not None and memory_property is not None:
            lines.append('%s=%s' % (memory_property, 'infinity' if memory == 0 else memory))
        elif memory is not None and os.path.isfile(path):
            lines.extend(line for line in resource_utils.read(path).splitlines()
                         if line.startswith(('MemoryMax=', 'MemoryLimit=')))
        return self._write_drop_in(path, '\n'.join(lines) + '\n')

    def configure_service(self, unit, slice_name):
        path = self._drop_in_path(unit)
        if os.path.lexists(path):
            return False
        return self._write_drop_in(path, '[Service]\nSlice=%s\n' % slice_name)

    def prune_services(self, slice_name, desired_units):
        if not os.path.isdir(self.SYSTEMD_UNIT_ROOT):
            return False

        changed = False
        directories = os.listdir(self.SYSTEMD_UNIT_ROOT)
        for name in directories:
            if not name.endswith('.d'):
                continue
            directory = os.path.join(self.SYSTEMD_UNIT_ROOT, name)
            if os.path.islink(directory) or not os.path.isdir(directory):
                continue
            path = os.path.join(directory, self.SYSTEMD_DROP_IN)
            if (os.path.islink(path) or not os.path.isfile(path) or self._configured_slice_path(path) != slice_name):
                continue
            unit = name[:-2]
            if unit not in desired_units:
                changed = self._remove_drop_in(path) or changed
        return changed

    def configured_slice(self, unit):
        return self._configured_slice_path(self._drop_in_path(unit))

    def _configured_slice_path(self, path):
        if not os.path.isfile(path):
            return None
        for line in resource_utils.read(path).splitlines():
            value = line.strip()
            if not value.startswith('Slice='):
                continue
            slice_name = value[len('Slice='):].strip()
            return slice_name if self.SLICE_PATTERN.match(slice_name) else None
        return None

    def _drop_in_path(self, unit):
        return os.path.join(self.SYSTEMD_UNIT_ROOT, unit + '.d', self.SYSTEMD_DROP_IN)

    def _write_drop_in(self, path, content):
        if os.path.isfile(path) and resource_utils.read(path) == content:
            return False
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory, mode=self.DROP_IN_DIRECTORY_MODE)
        with tempfile.TemporaryDirectory(prefix='.zstack-resource-', dir=directory) as temporary_directory:
            temporary = os.path.join(temporary_directory, 'drop-in')
            with open(temporary, 'w') as stream:
                stream.write(content)
            os.chmod(temporary, self.DROP_IN_FILE_MODE)
            os.replace(temporary, path)
        return True

    def _remove_drop_in(self, path):
        if not os.path.exists(path):
            return False
        os.unlink(path)
        directory = os.path.dirname(path)
        if os.path.isdir(directory) and not os.listdir(directory):
            os.rmdir(directory)
        return True

    def properties(self, unit):
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
        process = subprocess.run(
            ['systemctl'] + list(arguments), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout)
        if process.returncode != 0:
            raise ResourceControlError('Systemctl failed: %s' % resource_utils.text(process.stderr).strip())
        return resource_utils.text(process.stdout)

    def _start_active_unit(self, unit):
        self._systemctl(['start', unit], self.SERVICE_RESTART_TIMEOUT)
        if self.properties(unit).get('ActiveState') != 'active':
            raise ResourceControlError('Systemd unit[%s] is not active after restart' % unit)

    def release_slice(self, slice_name):
        return self._remove_drop_in(self._drop_in_path(slice_name))

    def reload(self):
        self._systemctl(['daemon-reload'], self.SYSTEMD_OPERATION_TIMEOUT)

    def start(self, unit):
        self._systemctl(['start', unit], self.SYSTEMD_OPERATION_TIMEOUT)

    def restart(self, unit):
        self._systemctl(['stop', unit], self.SERVICE_RESTART_TIMEOUT)
        self._start_active_unit(unit)

    def legacy_control_group(self, control_group):
        target = os.path.normpath(os.path.join(self.CGROUP_SYSTEMD_V1_ROOT, control_group.lstrip('/')))
        resource_utils.under_root(self.CGROUP_SYSTEMD_V1_ROOT, target)
        return target

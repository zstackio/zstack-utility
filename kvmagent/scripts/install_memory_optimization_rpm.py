#!/usr/bin/env python
"""Standard pinned RPM upgrade, preserving policy, pool and worker journals."""
import argparse
import ctypes
import ctypes.util
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time


UNIT_PATH = '/usr/lib/systemd/system/zram-memory.service'
OVERRIDE_PATH = '/etc/systemd/system/zram-memory.service'
RECOVERY_PATH = '/var/lib/zstack-zram/rpm-upgrade-recovery.json'
EXECUTABLE_PATH = '/usr/local/libexec/zram-efficiency'
RUNTIME_BINARY_PATHS = {
    EXECUTABLE_PATH,
    '/usr/local/bin/zram-efficiencyctl',
}
EXPECTED_EXECSTART = 'ExecStart=/usr/local/libexec/zram-efficiency --config /etc/zram-memory/config.json'
EXPECTED_EXECSTARTPRE = ('ExecStartPre=/usr/local/libexec/zstack/'
                         'memory-optimization-bundle/bin/load-zram-module')
SYSTEMD_BUS_NAME = 'org.freedesktop.systemd1'
SYSTEMD_UNIT_OBJECT = '/org/freedesktop/systemd1/unit/zram_2dmemory_2eservice'
SYSTEMD_SERVICE_INTERFACE = 'org.freedesktop.systemd1.Service'
SYSTEMD_EXEC_ACTION_SIGNATURE = 'a(sasbttttuii)'
try:
    STRING_TYPES = (basestring,)
    INTEGER_TYPES = (int, long)
except NameError:
    STRING_TYPES = (str,)
    INTEGER_TYPES = (int,)
try:
    TIMEOUT_ERRORS = (subprocess.TimeoutExpired,)
except AttributeError:
    TIMEOUT_ERRORS = ()

class timespec(ctypes.Structure):
    _fields_ = [('tv_sec', ctypes.c_long), ('tv_nsec', ctypes.c_long)]


CLOCK_MONOTONIC = 1
librt = None
if not hasattr(time, 'monotonic'):
    try:
        libname = ctypes.util.find_library('rt')
        if not libname:
            raise OSError('unable to find librt library')
        librt = ctypes.CDLL(libname, use_errno=True)
    except Exception:
        pass


def _monotonic():
    if hasattr(time, 'monotonic'):
        return time.monotonic()
    if librt is None:
        raise OSError('monotonic clock is unavailable')
    value = timespec()
    if librt.clock_gettime(CLOCK_MONOTONIC, ctypes.byref(value)) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return value.tv_sec + value.tv_nsec / 1e9


def _makedirs(path, mode=0o777):
    try:
        os.makedirs(path, mode)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(path):
            raise


class InstallError(RuntimeError):
    pass


def _hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _path(root, absolute):
    return os.path.join(root, absolute.lstrip('/'))


def _run(argv, runner=subprocess.check_output):
    output = runner(argv, stderr=subprocess.STDOUT, universal_newlines=True)
    return output.strip()


def _version(path, runner=subprocess.check_output):
    try:
        data = json.loads(_run([str(path), '--version'], runner=runner))
    except (ValueError, IOError, OSError, subprocess.CalledProcessError, TypeError) as exc:
        raise InstallError('RUNTIME_VERSION_UNVERIFIABLE')
    if not isinstance(data, dict) or not isinstance(data.get('version'), STRING_TYPES):
        raise InstallError('RUNTIME_VERSION_UNVERIFIABLE')
    return data['version']


def _validate(root, inventory_path, rpm_path):
    try:
        inventory = json.load(open(inventory_path))
    except (IOError, OSError, ValueError):
        raise InstallError('RPM_INVENTORY_INVALID')
    package = inventory.get('package', {})
    if (inventory.get('schemaVersion') != 3 or
            inventory.get('trustModel') != 'content-hash-pinned-not-signed' or
            package.get('name') != 'zstack-zram' or package.get('architecture') != 'x86_64' or
            not re.match(r'[0-9]+(?:\.[0-9]+)*\Z', package.get('version', '')) or
            not re.match(r'[A-Za-z0-9._+~-]+\Z', package.get('release', '')) or
            inventory.get('kernelOrModuleIncluded') is not False or
            inventory.get('configNoreplace') is not True or
            inventory.get('scriptletsEmpty') is not True or
            not re.match(r'[0-9a-f]{64}\Z', inventory.get('systemdUnitSha256', ''))):
        raise InstallError('RPM_INVENTORY_INVALID')
    runtime_binaries = inventory.get('runtimeBinaries')
    if (not isinstance(runtime_binaries, dict) or
            set(runtime_binaries) != RUNTIME_BINARY_PATHS or
            any(not isinstance(item, dict) or
                not isinstance(item.get('bytes'), INTEGER_TYPES) or isinstance(item.get('bytes'), bool) or item['bytes'] <= 0 or
                not re.match(r'[0-9a-f]{64}\Z', item.get('sha256', ''))
                for item in runtime_binaries.values())):
        raise InstallError('RPM_RUNTIME_BINARY_INVENTORY_INVALID')
    rpm = rpm_path
    if os.path.islink(rpm) or not os.path.isfile(rpm) or os.stat(rpm).st_size != package.get('bytes') or \
            _hash(rpm) != package.get('sha256'):
        raise InstallError('RPM_HASH_MISMATCH')
    return inventory


def _active_state(runner):
    try:
        state = _run(['systemctl', 'is-active', 'zram-memory.service'], runner=runner)
    except subprocess.CalledProcessError as exc:
        if exc.returncode not in (3, 4):
            raise InstallError('SERVICE_STATE_UNVERIFIABLE')
        state = (exc.output or '').strip()
    if state == 'active':
        return True
    if state in ('inactive', 'failed', 'unknown'):
        return False
    raise InstallError('SERVICE_TRANSITION_IN_PROGRESS:' + state)


def _installed_identity(runner):
    try:
        return _run(['rpm', '-q', '--qf', '%{VERSION}-%{RELEASE}', 'zstack-zram'], runner=runner)
    except subprocess.CalledProcessError:
        return None


def _systemd_properties(runner):
    output = _run(['systemctl', 'show', '-p', 'FragmentPath', '-p', 'MainPID',
                   '-p', 'DropInPaths', '-p', 'ActiveState',
                   '-p', 'KillMode', '-p', 'Restart', '-p', 'ExecStop', '-p', 'ExecStopPost',
                   'zram-memory.service'], runner=runner)
    properties = {}
    for line in output.splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            properties[key] = value
    return properties


def _require_empty_systemd_exec_action(property_name, runner):
    """Prove an omitted systemctl Exec* property is empty using its typed D-Bus value."""
    if property_name not in ('ExecStop', 'ExecStopPost'):
        raise InstallError('UPGRADE_CONTROLLER_EFFECTIVE_STOP_CONTRACT_UNKNOWN')
    argv = ['busctl', 'get-property', SYSTEMD_BUS_NAME, SYSTEMD_UNIT_OBJECT,
            SYSTEMD_SERVICE_INTERFACE, property_name]
    try:
        output = _run(argv, runner=runner)
    except (IOError, OSError, subprocess.CalledProcessError, TypeError, ValueError) + TIMEOUT_ERRORS as exc:
        raise InstallError('UPGRADE_CONTROLLER_EFFECTIVE_STOP_CONTRACT_UNKNOWN')
    fields = output.split()
    if len(fields) != 2 or fields[0] != SYSTEMD_EXEC_ACTION_SIGNATURE:
        raise InstallError('UPGRADE_CONTROLLER_EFFECTIVE_STOP_CONTRACT_UNKNOWN')
    count = fields[1]
    if not re.match(r'(?:0|[1-9][0-9]*)\Z', count):
        raise InstallError('UPGRADE_CONTROLLER_EFFECTIVE_STOP_CONTRACT_UNKNOWN')
    if count != '0':
        raise InstallError('UPGRADE_CONTROLLER_STOP_CONTRACT_UNSAFE:' + property_name)


def _proc_starttime(root, pid):
    path = os.path.join(root, 'proc', str(pid), 'stat')
    try:
        data = open(path).read()
    except (IOError, OSError):
        raise InstallError('ACTIVE_PROCESS_IDENTITY_UNVERIFIABLE')
    # comm is parenthesized and may contain spaces or ')'; split after its last
    # delimiter. starttime is field 22, i.e. index 19 from field 3 onward.
    _prefix, delimiter, tail = data.rpartition(')')
    fields = tail.split()
    if not delimiter or len(fields) <= 19 or not fields[19].isdigit():
        raise InstallError('ACTIVE_PROCESS_IDENTITY_UNVERIFIABLE')
    return fields[19]


def _runtime_binary_matches(root, path, record):
    binary = _path(root, path)
    try:
        return (not os.path.islink(binary) and os.path.isfile(binary) and
                os.stat(binary).st_size == record['bytes'] and
                _hash(binary) == record['sha256'])
    except (IOError, OSError):
        return False


def _verify_runtime_binaries(root, inventory, expected_version, error_prefix,
                             runner=subprocess.check_output):
    records = inventory['runtimeBinaries']
    if any(not _runtime_binary_matches(root, path, records[path])
           for path in RUNTIME_BINARY_PATHS):
        raise InstallError(error_prefix + ':BINARY_HASH_MISMATCH')
    executable = _path(root, EXECUTABLE_PATH)
    if _version(executable, runner) != expected_version:
        raise InstallError(error_prefix + ':BINARY_VERSION_MISMATCH')


def _verify_active(root, inventory, runner):
    package = inventory['package']
    expected = package['version'] + '-' + package['release']
    if _installed_identity(runner) != expected:
        raise InstallError('MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE_PACKAGE_MISMATCH')
    properties = _systemd_properties(runner)
    if properties.get('DropInPaths', '').strip():
        raise InstallError('MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE_DROPIN_MISMATCH')
    fragment = properties.get('FragmentPath')
    unit = _path(root, UNIT_PATH)
    if fragment != UNIT_PATH or not os.path.isfile(unit) or _hash(unit) != inventory['systemdUnitSha256']:
        raise InstallError('MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE_UNIT_MISMATCH')
    contents = open(unit).read()
    if EXPECTED_EXECSTART not in contents or EXPECTED_EXECSTARTPRE not in contents:
        raise InstallError('MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE_UNIT_CONTENT_MISMATCH')
    _verify_runtime_binaries(root, inventory, expected,
                             'MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE', runner)
    binary = _path(root, EXECUTABLE_PATH)
    if _version(binary, runner) != expected:
        raise InstallError('MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE_BINARY_MISMATCH')
    pid = properties.get('MainPID', '')
    if not pid.isdigit() or int(pid) <= 0:
        raise InstallError('MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE_PID_UNVERIFIABLE')
    proc_exe = os.path.join(root, 'proc', pid, 'exe')
    try:
        started = _proc_starttime(root, pid)
        proc_matches = (os.path.exists(proc_exe) and
                        os.stat(proc_exe).st_size == inventory['runtimeBinaries'][EXECUTABLE_PATH]['bytes'] and
                        _hash(proc_exe) == inventory['runtimeBinaries'][EXECUTABLE_PATH]['sha256'] and
                        _version(proc_exe, runner) == expected)
        started_after = _proc_starttime(root, pid)
    except (IOError, OSError, InstallError):
        raise InstallError('MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE_PROCESS_MISMATCH')
    current_properties = _systemd_properties(runner)
    if (not proc_matches or started != started_after or
            current_properties.get('MainPID') != pid or
            _installed_identity(runner) != expected or
            not _runtime_binary_matches(root, EXECUTABLE_PATH,
                                        inventory['runtimeBinaries'][EXECUTABLE_PATH]) or
            not _active_state(runner)):
        raise InstallError('MEMORY_OPTIMIZATION_MAINTENANCE_REQUIRED:ACTIVE_PROCESS_MISMATCH')


def _factory_observe_config(root):
    """Return true only for the untouched vendor template with no service state.

    This permits a standard install to make the controller observable while
    preserving the RPM's observe-only, unauthorized, efficiency-disabled
    posture. It is deliberately not an authorization to reclaim memory.
    """
    config = _path(root, '/etc/zram-memory/config.json')
    template = _path(root, '/usr/share/zstack-zram/config.json')
    state = _path(root, '/var/lib/zram-efficiency')
    try:
        if (os.path.islink(config) or os.path.islink(template) or
                not os.path.isfile(config) or not os.path.isfile(template)):
            return False
        if _hash(config) != _hash(template):
            return False
        data = json.load(open(config))
        if (not isinstance(data, dict) or data.get('managed') is not True or
                data.get('mode') != 'observe' or
                data.get('resource_authorized') is not False or
                data.get('initial_efficiency_enabled') is not False):
            return False
        # Any pre-existing runtime state is treated as adopted/custom state.
        if os.path.exists(state) and (not os.path.isdir(state) or os.listdir(state)):
            return False
        return True
    except (IOError, OSError, ValueError):
        return False
def _validate_unit_ownership(root, runner):
    """Reject unmanaged unit overrides before any package or process mutation."""
    override = _path(root, OVERRIDE_PATH)
    dropins = set()
    for base in ('/etc/systemd/system', '/run/systemd/system', '/usr/lib/systemd/system'):
        directory = _path(root, base + '/zram-memory.service.d')
        if os.path.islink(directory):
            raise InstallError('UNMANAGED_UNIT_DROPIN_PRESENT')
        if os.path.exists(directory):
            for name in os.listdir(directory):
                if name.endswith('.conf'):
                    dropins.add('/' + os.path.relpath(os.path.join(directory, name), root))
    effective = set(_systemd_properties(runner).get('DropInPaths', '').split())
    dropins |= effective
    if os.path.lexists(override):
        raise InstallError('UNMANAGED_UNIT_OVERRIDE_PRESENT')
    if dropins:
        raise InstallError('UNMANAGED_UNIT_DROPIN_PRESENT')
    properties = _systemd_properties(runner)
    fragment = properties.get('FragmentPath', '')
    installed = _installed_identity(runner)
    unit = _path(root, UNIT_PATH)
    if installed:
        if (fragment != UNIT_PATH or os.path.islink(unit) or not os.path.isfile(unit) or
                _rpm_file_digest(runner, UNIT_PATH) != _hash(unit)):
            raise InstallError('UNMANAGED_UNIT_PACKAGE_OWNERSHIP_UNKNOWN')
    elif fragment or os.path.lexists(unit):
        raise InstallError('UNMANAGED_UNIT_PACKAGE_OWNERSHIP_UNKNOWN')
    return properties, installed


def _sync_path(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rpm_file_digest(runner, path):
    """RPM-owned predecessors must match RPM database bytes, not just version."""
    try:
        lines = _run(['rpm', '-q', '--qf', '[%{FILENAMES}\\t%{FILEDIGESTS}\\n]',
                      'zstack-zram'], runner).splitlines()
    except subprocess.CalledProcessError:
        return None
    matches = [row.split('\t')[1] for row in lines
               if row.startswith(path + '\t') and len(row.split('\t')) == 2]
    if len(matches) == 1 and re.match(r'[0-9a-f]{64}\Z', matches[0]):
        return matches[0]
    return None


def _old_controller_identity(root, runner, properties=None):
    """Read-only qualification before configuration or recovery state changes."""
    properties = properties or _systemd_properties(runner)
    fragment = properties.get('FragmentPath')
    if fragment != UNIT_PATH:
        raise InstallError('UPGRADE_CONTROLLER_UNIT_UNKNOWN')
    unit = _path(root, fragment)
    if os.path.islink(unit) or not os.path.isfile(unit):
        raise InstallError('UPGRADE_CONTROLLER_UNIT_UNKNOWN')
    unit_sha = _hash(unit)
    if _rpm_file_digest(runner, UNIT_PATH) != unit_sha:
        raise InstallError('UPGRADE_CONTROLLER_UNIT_UNKNOWN')
    contents = open(unit).read()
    if ('KillMode=process' not in contents or 'Restart=no' not in contents or
            EXPECTED_EXECSTART not in contents or
            any(line.strip().startswith(('ExecStop=', 'ExecStopPost='))
                for line in contents.splitlines()) or properties.get('DropInPaths', '').strip()):
        raise InstallError('UPGRADE_CONTROLLER_STOP_CONTRACT_UNKNOWN')
    # Disk bytes alone do not prove the already-loaded systemd contract.
    if properties.get('KillMode') != 'process' or properties.get('Restart') != 'no':
        raise InstallError('UPGRADE_CONTROLLER_EFFECTIVE_STOP_CONTRACT_UNKNOWN')
    for property_name in ('ExecStop', 'ExecStopPost'):
        if property_name in properties:
            if properties[property_name] != '':
                raise InstallError('UPGRADE_CONTROLLER_EFFECTIVE_STOP_CONTRACT_UNKNOWN')
        else:
            _require_empty_systemd_exec_action(property_name, runner)
    pid = properties.get('MainPID', '')
    if not pid.isdigit() or int(pid) <= 0:
        raise InstallError('ACTIVE_PROCESS_IDENTITY_UNVERIFIABLE')
    started = _proc_starttime(root, pid)
    executable = _path(root, EXECUTABLE_PATH)
    proc_exe = _path(root, '/proc/' + pid + '/exe')
    if os.path.islink(executable) or not os.path.isfile(executable):
        raise InstallError('UPGRADE_CONTROLLER_BINARY_UNKNOWN')
    digest = _hash(executable)
    if _rpm_file_digest(runner, EXECUTABLE_PATH) != digest:
        raise InstallError('UPGRADE_CONTROLLER_BINARY_UNKNOWN')
    if (_hash(proc_exe) != digest or _proc_starttime(root, pid) != started or
            _systemd_properties(runner).get('MainPID') != pid):
        raise InstallError('ACTIVE_PROCESS_IDENTITY_UNVERIFIABLE')
    return {'pid': int(pid), 'startTime': started, 'sha256': digest}


def _graceful_old_controller_exit(root, runner, timeout=75, sleep=time.sleep,
                                   before_signal=None):
    """Never kill workers, drain swap, rewrite policy, or force a stuck process."""
    identity = _old_controller_identity(root, runner)
    pid, started = str(identity['pid']), identity['startTime']
    if before_signal:
        before_signal(identity)
        if _old_controller_identity(root, runner) != identity:
            raise InstallError('UPGRADE_CONTROLLER_CHANGED_BEFORE_SIGNAL')
    # systemctl stop could SIGKILL after TimeoutStopSec. Signal only the verified
    # main controller and wait; its ordinary shutdown retains the pool/journals.
    _run(['systemctl', 'kill', '--kill-who=main', '--signal=SIGTERM', 'zram-memory.service'], runner)
    deadline = _monotonic() + timeout
    while True:
        proc_stat = _path(root, '/proc/' + pid + '/stat')
        try:
            old_alive = os.path.exists(proc_stat) and _proc_starttime(root, pid) == started
        except InstallError:
            if os.path.exists(proc_stat):
                raise
            old_alive = False
        current = _systemd_properties(runner)
        if not old_alive and current.get('MainPID') == '0':
            try:
                stopped = not _active_state(runner)
            except InstallError as exc:
                # systemd can clear MainPID before it finishes unit cleanup.
                # Only that expected stop transition may consume the remaining
                # deadline; unreadable states or a new start must still fail.
                if str(exc) != 'SERVICE_TRANSITION_IN_PROGRESS:deactivating':
                    raise
                stopped = False
            if stopped:
                return identity
        if current.get('MainPID') not in (pid, '0'):
            raise InstallError('UPGRADE_CONTROLLER_CHANGED_DURING_STOP')
        if _monotonic() >= deadline:
            raise InstallError('UPGRADE_CONTROLLER_EXIT_TIMEOUT_POOL_PRESERVED')
        sleep(0.1)


def _boot_id(root):
    value = open(_path(root, '/proc/sys/kernel/random/boot_id')).read().strip()
    if not re.match(r'[0-9a-f-]{36}\Z', value):
        raise InstallError('UPGRADE_BOOT_ID_UNVERIFIABLE')
    return value


def _read_recovery(root, package):
    path = _path(root, RECOVERY_PATH)
    parent = os.path.dirname(path)
    if os.path.islink(parent) or os.path.islink(path):
        raise InstallError('UPGRADE_RECOVERY_NOT_REGULAR')
    if not os.path.exists(path):
        return None
    metadata = os.stat(path)
    if (not os.path.isfile(path) or metadata.st_size > 4096 or
            metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077):
        raise InstallError('UPGRADE_RECOVERY_NOT_REGULAR')
    try:
        data = json.load(open(path))
        if not isinstance(data, dict) or set(data) != {
                'schemaVersion', 'restart', 'rpmSha256', 'bootId',
                'previousController', 'configSha256'}:
            raise ValueError('unexpected recovery fields')
        previous = data['previousController']
        valid = (type(data['schemaVersion']) in INTEGER_TYPES and not isinstance(data['schemaVersion'], bool) and data['schemaVersion'] == 1 and
                 data['restart'] is True and isinstance(previous, dict) and
                 re.match(r'[0-9a-f-]{36}\Z', data['bootId']) and
                 type(previous['pid']) in INTEGER_TYPES and not isinstance(previous['pid'], bool) and previous['pid'] > 0 and
                 re.match(r'[0-9]+\Z', previous['startTime']) and
                 re.match(r'[0-9a-f]{64}\Z', previous['sha256']) and
                 (data['configSha256'] is None or
                  re.match(r'[0-9a-f]{64}\Z', data['configSha256'])))
        if not valid:
            raise ValueError('invalid recovery record')
    except (ValueError, KeyError, TypeError):
        raise InstallError('UPGRADE_RECOVERY_INVALID')
    if data.get('rpmSha256') != package['sha256']:
        raise InstallError('UPGRADE_RECOVERY_TARGET_MISMATCH')
    return data


def _write_recovery(root, package, controller, config_sha):
    # One bounded, root-private installer receipt; not a new public upgrade
    # state or policy. Persist restart intent before delivering any signal.
    path = _path(root, RECOVERY_PATH)
    data = dict(schemaVersion=1, restart=True, rpmSha256=package['sha256'],
                bootId=_boot_id(root), previousController=controller,
                configSha256=config_sha)
    parent = os.path.dirname(path)
    _makedirs(parent, 0o700)
    if os.path.islink(parent):
        raise InstallError('UPGRADE_RECOVERY_NOT_REGULAR')
    fd, temporary = tempfile.mkstemp(prefix='.rpm-upgrade-', dir=parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, path)
        _sync_path(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return data


def _clear_recovery(root):
    path = _path(root, RECOVERY_PATH)
    if os.path.exists(path):
        os.unlink(path)
        _sync_path(os.path.dirname(path))


def _install_locked(root, inventory_path, rpm_path, runner=subprocess.check_output,
                    installer=None):
    """Install against root; injectable runner/installer support fake-root tests."""
    root = os.path.abspath(root)
    inventory = _validate(root, inventory_path, rpm_path)
    package = inventory['package']
    properties, installed = _validate_unit_ownership(root, runner)
    recovery = _read_recovery(root, package)
    config = _path(root, '/etc/zram-memory/config.json')
    if os.path.islink(config) or (os.path.exists(config) and not os.path.isfile(config)):
        raise InstallError('CONFIG_NOT_REGULAR_FILE')
    config_sha = _hash(config) if os.path.exists(config) else None
    if recovery and config_sha != recovery['configSha256']:
        # A previous product package may have had no config file. The first
        # RPM then creates the exact safe factory observer before a later
        # transaction failure is retried. Accept only that byte-identical
        # factory state; any user-edited replacement remains a hard conflict.
        factory_config_created_by_rpm = (
            recovery.get('configSha256') is None and _factory_observe_config(root))
        if not factory_config_created_by_rpm:
            raise InstallError('UPGRADE_RECOVERY_CONFIG_CHANGED')
    active = _active_state(runner)
    if active:
        if installed == package['version'] + '-' + package['release']:
            _verify_active(root, inventory, runner)
            _clear_recovery(root)
            return {'status': 'IDEMPOTENT_ACTIVE', 'package': package['version'] + '-' + package['release']}
        _old_controller_identity(root, runner, properties)
    elif recovery and recovery['bootId'] == _boot_id(root):
        old = recovery['previousController']
        old_stat = _path(root, '/proc/%d/stat' % old['pid'])
        if os.path.exists(old_stat) and _proc_starttime(root, str(old['pid'])) == old['startTime']:
            raise InstallError('UPGRADE_RECOVERY_OLD_CONTROLLER_STILL_RUNNING')
    config_backup = None
    if os.path.exists(config):
        config_backup = os.path.join(root, 'var/lib/zstack-zram/upgrade-config-archive', _hash(config))
        config_backup_parent = os.path.dirname(config_backup)
        _makedirs(config_backup_parent, 0o700)
        if os.path.islink(config_backup) or (os.path.exists(config_backup) and _hash(config_backup) != _hash(config)):
            raise InstallError('CONFIG_ARCHIVE_CONFLICT')
        if not os.path.exists(config_backup):
            shutil.copy2(config, config_backup)
        _sync_path(config_backup)
        _sync_path(config_backup_parent)
    previous_controller = recovery['previousController'] if recovery else None
    if active:
        previous_controller = _graceful_old_controller_exit(
            root, runner,
            before_signal=lambda identity: _write_recovery(root, package, identity, config_sha))
    try:
        if installer is None:
            if root != os.path.abspath('/'):
                raise InstallError('FAKE_ROOT_INSTALLER_REQUIRED')
            package_manager = None
            for candidate in ('dnf', 'yum'):
                for directory in os.environ.get('PATH', '').split(os.pathsep):
                    executable = os.path.join(directory, candidate)
                    if os.path.isfile(executable) and os.access(executable, os.X_OK):
                        package_manager = candidate
                        break
                if package_manager:
                    break
            rpm_path = os.path.abspath(rpm_path)
            if package_manager == 'dnf':
                _run(['dnf', '-y', '--disablerepo=*', 'install', rpm_path], runner)
            elif package_manager == 'yum':
                _run(['yum', '-y', '--disablerepo=*', 'localinstall', rpm_path], runner)
            else:
                raise InstallError('PACKAGE_MANAGER_UNAVAILABLE')
        else:
            installer(str(root), os.path.abspath(rpm_path))
        # %config(noreplace) preserves RPM-owned configuration. Retain a local
        # backup as well so a failed package transaction cannot lose policy.
        if config_backup and (not os.path.exists(config) or _hash(config) != _hash(config_backup)):
            if os.path.islink(config):
                raise InstallError('CONFIG_CHANGED_TO_SYMLINK')
            shutil.copy2(config_backup, config)
            _sync_path(config)
            _sync_path(os.path.dirname(config))
        if root == os.path.abspath('/'):
            _run(['systemctl', 'daemon-reload'], runner)
        properties = _systemd_properties(runner)
        fragment = properties.get('FragmentPath')
        if properties.get('DropInPaths', '').strip():
            raise InstallError('RPM_UNIT_DROPIN_NOT_MIGRATED')
        unit = _path(root, UNIT_PATH)
        if fragment != UNIT_PATH or not os.path.isfile(unit) or _hash(unit) != inventory['systemdUnitSha256']:
            raise InstallError('RPM_UNIT_NOT_EFFECTIVE')
        contents = open(unit).read()
        if EXPECTED_EXECSTART not in contents or EXPECTED_EXECSTARTPRE not in contents:
            raise InstallError('RPM_UNIT_CONTENT_INVALID')
        if _installed_identity(runner) != package['version'] + '-' + package['release']:
            raise InstallError('RPM_INSTALLED_IDENTITY_MISMATCH')
        expected = package['version'] + '-' + package['release']
        _verify_runtime_binaries(root, inventory, expected, 'RPM', runner)
        if _active_state(runner):
            raise InstallError('RPM_INSTALLER_IMPLICITLY_ACTIVATED_SERVICE')
        # Only the untouched vendor template may start the safe observer.
        observe_bootstrap = (not previous_controller and _factory_observe_config(root))
        if previous_controller:
            _run(['systemctl', 'start', 'zram-memory.service'], runner)
            _verify_active(root, inventory, runner)
        elif observe_bootstrap:
            # Start only the exact package-owned factory configuration. The
            # runtime remains observe-only and cannot reclaim until a normal
            # management apply explicitly authorizes resource use.
            _run(['systemctl', 'enable', 'zram-memory.service'], runner)
            _run(['systemctl', 'start', 'zram-memory.service'], runner)
            _verify_active(root, inventory, runner)
        _clear_recovery(root)
        return {'status': ('UPGRADED_ACTIVE' if previous_controller else
                           'INSTALLED_OBSERVING' if observe_bootstrap else
                           'INSTALLED_INACTIVE'),
                'package': package['version'] + '-' + package['release'],
                'previousController': previous_controller}
    except Exception as failure:
        rollback_failures = []
        try:
            if config_backup:
                if os.path.islink(config) or (os.path.exists(config) and not os.path.isfile(config)):
                    raise InstallError('CONFIG_RESTORE_CONFLICT')
                shutil.copy2(config_backup, config)
                _sync_path(config)
                _sync_path(os.path.dirname(config))
        except (IOError, OSError, InstallError) as exc:
            rollback_failures.append(str(exc))
        if rollback_failures:
            raise InstallError('UPGRADE_ROLLBACK_INCOMPLETE:' + ';'.join(rollback_failures))
        raise


def install(root, inventory_path, rpm_path, runner=subprocess.check_output,
            installer=None):
    # Serialize the complete stop/install/start path across reconnect attempts.
    # This is an installer-local lock, not a new public upgrade state machine.
    _validate(root, inventory_path, rpm_path)
    # Also use the existing Agent mutation lock. Reconnect must not restore a
    # stale config backup over a concurrently submitted control/policy request.
    paths = ('/run/lock/zstack-zram-rpm-upgrade.lock',
             '/var/lib/zstack/memory-optimization/operations/.host-control.flock')
    descriptors = []
    try:
        for absolute in paths:
            lock_path = _path(root, absolute)
            lock_parent = os.path.dirname(lock_path)
            _makedirs(lock_parent)
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            descriptors.append(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise InstallError('RPM_UPGRADE_LOCK_NOT_REGULAR')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError) as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                raise InstallError('RPM_UPGRADE_OR_HOST_CONTROL_ALREADY_RUNNING')
        return _install_locked(root, inventory_path, rpm_path, runner, installer)
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True)
    parser.add_argument('--rpm', required=True)
    args = parser.parse_args()
    print(json.dumps(install('/', args.inventory, args.rpm), sort_keys=True))


if __name__ == '__main__':
    main()

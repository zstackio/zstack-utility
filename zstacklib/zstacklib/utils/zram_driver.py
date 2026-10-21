"""Read-only qualification of the Alinux ZRAM module for the running kernel.

Disk package identity and the loaded module are deliberately separate. This
module never installs, loads, unloads, resets, or drains anything. The module
path and vermagic must match the running kernel. Optional accounting and
writeback interfaces are reported separately from module readiness.
"""
import json
import os
import platform
import re
import shlex
import subprocess


PACKAGE_NAME = 'kmod-zstack-zram'
MODULE_RELATIVE_PATH = 'updates/zstack-zram/zram.ko'
ACCOUNTING_SCHEMA = '2'


def _read(path):
    with open(path, 'r') as stream:
        value = stream.read(65537)
    if len(value) > 65536:
        raise ValueError('DRIVER_OBSERVATION_TOO_LARGE')
    return value.strip()


def _run(argv):
    return subprocess.check_output(argv, stderr=subprocess.DEVNULL,
                                   timeout=5, universal_newlines=True).strip()


def _host_release(read):
    values = {}
    for line in read('/etc/os-release').splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        key, raw = line.split('=', 1)
        words = shlex.split(raw, comments=True)
        if len(words) == 1:
            values[key.strip()] = words[0].lower()
    if (values.get('ID') in ('alinux', 'alinux4') and
            values.get('VERSION_ID', '').split('.')[0] == '4'):
        return 'alinux4'
    return 'other'


def inspect(release=None, architecture=None, kernel=None, read=None, run=None,
            exists=None, realpath=None):
    """Collect current facts only; an unavailable fact can never grant support.

    Dependencies are injectable for tests; production callers use OS facts.
    Non-Alinux Hosts are outside this independent kmod profile (not qualified
    by it). The normal native/Go checks still apply on every platform.
    """
    read, run = read or _read, run or _run
    exists, realpath = exists or os.path.exists, realpath or os.path.realpath
    kernel, architecture = kernel or platform.release(), architecture or platform.machine()
    result = {'applicable': True, 'supported': False, 'reasonCode': 'ZRAM_DRIVER_UNKNOWN',
              'kernel': kernel, 'architecture': architecture, 'disk': {}, 'loaded': {},
              'maintenanceRequired': False, 'safeToLoad': False}
    try:
        release = release or _host_release(read)
        result['release'] = release
        if release != 'alinux4':
            result.update(applicable=False, reasonCode='ZRAM_DRIVER_PROFILE_NOT_APPLICABLE')
            return result
        if architecture != 'x86_64':
            result['reasonCode'] = 'ZRAM_DRIVER_ARCHITECTURE_NOT_SUPPORTED'
            return result
        loaded = result['loaded']
        loaded['present'] = exists('/sys/module/zram')
        if loaded['present']:
            for field in ('version', 'srcversion'):
                try:
                    loaded[field] = read('/sys/module/zram/' + field)
                except (OSError, ValueError):
                    loaded[field] = None

        disk = result['disk']
        for field in ('filename', 'version', 'vermagic', 'srcversion'):
            disk[field] = run(['modinfo', '-k', kernel, '-F', field, 'zram'])
        expected = '/lib/modules/' + kernel + '/' + MODULE_RELATIVE_PATH
        # Resolve /lib -> /usr/lib, but do not accept weak-updates or a module
        # belonging to another kernel merely because modprobe can find it.
        if (not disk['filename'] or realpath(disk['filename']) != realpath(expected)):
            result['reasonCode'] = 'ZRAM_DRIVER_DISK_PATH_MISMATCH'
            return result
        query = run(['rpm', '-qf', '--qf', '%{NAME}\n%{EPOCH}\n%{VERSION}\n%{RELEASE}\n%{ARCH}\n',
                     disk['filename']]).splitlines()
        disk['package'] = query
        if len(query) != 5 or query[0] != PACKAGE_NAME or query[4] != architecture:
            result['reasonCode'] = 'ZRAM_DRIVER_PACKAGE_MISMATCH'
            return result
        epoch = '0' if query[1] in ('', '(none)') else query[1]
        if not epoch.isdigit() or not query[2] or not query[3]:
            result['reasonCode'] = 'ZRAM_DRIVER_PACKAGE_MISMATCH'
            return result
        result['installationPackage'] = '%s-%s:%s-%s.%s' % (
            query[0], epoch, query[2], query[3], query[4])
        # RPM metadata alone does not prove the selected module bytes are
        # still the installed file. Verify the owning package read-only.
        try:
            verification = run(['rpm', '-V', PACKAGE_NAME])
        except subprocess.CalledProcessError as exc:
            # rpm -V returns 1 when package files differ. Other statuses mean
            # that package verification itself could not be observed.
            if exc.returncode != 1:
                raise
            result['reasonCode'] = 'ZRAM_DRIVER_PACKAGE_CONTENT_MISMATCH'
            return result
        if verification:
            result['reasonCode'] = 'ZRAM_DRIVER_PACKAGE_CONTENT_MISMATCH'
            return result
        if (not disk['vermagic'].split() or disk['vermagic'].split()[0] != kernel or
                not disk['version']):
            result['reasonCode'] = 'ZRAM_DRIVER_DISK_ABI_MISMATCH'
            return result
        if not disk['srcversion']:
            result['reasonCode'] = 'ZRAM_DRIVER_DISK_IDENTITY_MISSING'
            return result
        result['safeToLoad'] = not loaded['present']
        if not loaded['present']:
            result['reasonCode'] = 'ZRAM_DRIVER_NOT_LOADED'
            return result
        if not loaded['version'] or not loaded['srcversion']:
            result.update(reasonCode='ZRAM_DRIVER_LOADED_IDENTITY_MISSING',
                          maintenanceRequired=True)
            return result
        if (loaded['version'] != disk['version'] or
                loaded['srcversion'] != disk['srcversion']):
            result.update(reasonCode='ZRAM_DRIVER_UPDATE_REQUIRES_MAINTENANCE',
                          maintenanceRequired=True)
            return result
        if not exists('/sys/block/zram0/disksize'):
            result['missingInterfaces'] = ['disksize']
            result['reasonCode'] = 'ZRAM_DRIVER_ABI_INCOMPLETE'
            return result
        accounting_interfaces = ('mm_stat', 'accounting_layout')
        missing_accounting = [name for name in accounting_interfaces
                              if not exists('/sys/block/zram0/' + name)]
        result['missingAccountingInterfaces'] = missing_accounting
        result['accountingSupported'] = False
        if not missing_accounting:
            try:
                layout = {}
                for line in read('/sys/block/zram0/accounting_layout').splitlines():
                    fields = line.split()
                    if len(fields) != 2:
                        continue
                    if not re.fullmatch(r'[0-9]+', fields[1]):
                        raise ValueError('ZRAM_DRIVER_ACCOUNTING_LAYOUT_INVALID')
                    value = int(fields[1], 10)
                    if value > 18446744073709551615:
                        raise ValueError('ZRAM_DRIVER_ACCOUNTING_LAYOUT_INVALID')
                    layout[fields[0]] = value
                result['accountingSupported'] = (
                    layout.get('schema') == int(ACCOUNTING_SCHEMA) and
                    layout.get('page_size') == 4096 and
                    layout.get('slot_entry_bytes', 0) > 0 and
                    layout.get('owner_entry_bytes', 0) > 0 and
                    layout.get('preallocated_metadata_bytes', 0) > 0)
            except (OSError, ValueError):
                result['accountingSupported'] = False
        writeback_interfaces = ('idle', 'writeback', 'writeback_limit',
                                'writeback_limit_enable', 'bd_stat')
        result['writebackSupported'] = all(
            exists('/sys/block/zram0/' + name) for name in writeback_interfaces)
        result.update(supported=True, reasonCode='SUPPORTED')
    except (OSError, ValueError, subprocess.SubprocessError):
        # Preserve already collected disk/loaded facts, never raw command
        # output or an exception string that might contain unrelated data.
        result.update(supported=False, safeToLoad=False, reasonCode='ZRAM_DRIVER_OBSERVATION_FAILED')
    return result


def main():
    # Host deployment uses diagnostics, not a fatal optional-feature gate.
    # A non-qualified module remains unavailable in Agent capabilities.
    print(json.dumps(inspect(), sort_keys=True))


if __name__ == '__main__':
    main()

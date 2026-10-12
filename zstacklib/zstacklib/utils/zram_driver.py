"""Read-only, exact-release ZRAM driver qualification.

Disk package identity and the loaded module are deliberately separate. This
module never installs, loads, unloads, resets, or drains anything. The release
table is shared by Host deployment diagnostics and Agent capability discovery;
it is not inferred from an accounting schema or a lexicographic comparison.
"""
import json
import os
import platform
import shlex
import subprocess


# This is the new product source/build profile, not the older r4 experiment.
# Publication and target RPM/runtime acceptance are tracked separately.
PROFILES = {
    ('alinux4', 'x86_64', '6.6.102-005.3.pro.ali6000.alnx4.x86_64'): {
        'moduleVersion': '5.5.48.1',
        'moduleSourceVersion': '28E0660C8D6A8636B59CF3C',
        'packageName': 'kmod-zstack-zram',
        'packageVersion': '5.5.48.1',
        'packageRelease': '1.alnx4',
        'moduleRelativePath': 'updates/zstack-zram/zram.ko',
        'accountingSchema': '2',
    },
}


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
        profile = PROFILES.get((release, architecture, kernel))
        if profile is None:
            result['reasonCode'] = 'ZRAM_DRIVER_KERNEL_UNSUPPORTED'
            return result
        result['expectedVersion'] = profile['moduleVersion']
        result['installationPackage'] = '%s-%s-%s.%s' % (
            profile['packageName'], profile['packageVersion'],
            profile['packageRelease'], architecture)
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
        expected = '/lib/modules/' + kernel + '/' + profile['moduleRelativePath']
        # Resolve /lib -> /usr/lib, but do not accept weak-updates or a module
        # belonging to another kernel merely because modprobe can find it.
        if (not disk['filename'] or realpath(disk['filename']) != realpath(expected)):
            result['reasonCode'] = 'ZRAM_DRIVER_DISK_PATH_MISMATCH'
            return result
        query = run(['rpm', '-qf', '--qf', '%{NAME}\n%{VERSION}\n%{RELEASE}\n%{ARCH}\n',
                     disk['filename']]).splitlines()
        disk['package'] = query
        if query != [profile['packageName'], profile['packageVersion'],
                     profile['packageRelease'], architecture]:
            result['reasonCode'] = 'ZRAM_DRIVER_PACKAGE_MISMATCH'
            return result
        # RPM metadata alone does not prove the selected module bytes are
        # still the installed file. Verify the owning package read-only.
        if run(['rpm', '-V', profile['packageName']]):
            result['reasonCode'] = 'ZRAM_DRIVER_PACKAGE_CONTENT_MISMATCH'
            return result
        if (not disk['vermagic'].split() or disk['vermagic'].split()[0] != kernel or
                disk['version'] != profile['moduleVersion']):
            result['reasonCode'] = 'ZRAM_DRIVER_DISK_ABI_MISMATCH'
            return result
        if not disk['srcversion']:
            result['reasonCode'] = 'ZRAM_DRIVER_DISK_IDENTITY_MISSING'
            return result
        if disk['srcversion'] != profile['moduleSourceVersion']:
            result['reasonCode'] = 'ZRAM_DRIVER_DISK_BUILD_MISMATCH'
            return result
        result['safeToLoad'] = not loaded['present']
        if not loaded['present']:
            result['reasonCode'] = 'ZRAM_DRIVER_NOT_LOADED'
            return result
        if not loaded['version'] or not loaded['srcversion']:
            result.update(reasonCode='ZRAM_DRIVER_LOADED_IDENTITY_MISSING',
                          maintenanceRequired=True)
            return result
        if (loaded['version'] != profile['moduleVersion'] or
                loaded['srcversion'] != profile['moduleSourceVersion']):
            result.update(reasonCode='ZRAM_DRIVER_UPDATE_REQUIRES_MAINTENANCE',
                          maintenanceRequired=True)
            return result
        required = ('mm_stat', 'disksize', 'idle', 'writeback', 'writeback_limit',
                    'writeback_limit_enable', 'bd_stat', 'accounting_layout')
        missing = [name for name in required if not exists('/sys/block/zram0/' + name)]
        result['missingInterfaces'] = missing
        if missing:
            result['reasonCode'] = 'ZRAM_DRIVER_ABI_INCOMPLETE'
            return result
        layout = {}
        for line in read('/sys/block/zram0/accounting_layout').splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[0] in layout:
                raise ValueError('ZRAM_DRIVER_ACCOUNTING_LAYOUT_INVALID')
            layout[fields[0]] = fields[1]
        if (layout.get('schema') != profile['accountingSchema'] or
                layout.get('page_size') != '4096'):
            result['reasonCode'] = 'ZRAM_DRIVER_ABI_MISMATCH'
            return result
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

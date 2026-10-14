#!/usr/bin/env python
"""Validate and stage one hash-pinned zstack-zram RPM plus its inventory."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess


REQUIRED_RPM_FILES = {
    '/etc/zram-memory/config.json',
    '/usr/lib/systemd/system/zram-memory.service',
    '/usr/local/libexec/zram-efficiency',
    '/usr/local/bin/zram-efficiencyctl',
    '/usr/local/libexec/zstack-zram/zramctl',
    '/usr/local/libexec/zstack-zram/bootstrap-config',
    '/usr/local/libexec/zstack/memory-optimization-bundle/bin/load-zram-module',
    '/usr/local/libexec/zstack/memory-optimization-bundle/bin/check-qualification',
    '/usr/share/zstack-zram/config.json',
}
PACKAGE_NAME = 'zstack-zram'
INSTALLER_NAME = 'install_memory_optimization_rpm.py'
UNIT_SOURCE_PATH = 'service/packaging/systemd/zram-memory.service'
RUNTIME_BINARIES = {
    '/usr/local/libexec/zram-efficiency',
    '/usr/local/bin/zram-efficiencyctl',
}
try:
    STRING_TYPES = (basestring,)
except NameError:
    STRING_TYPES = (str,)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _rpm_query(rpm, *args):
    return subprocess.check_output(['rpm'] + list(args) + [str(rpm)],
                                   stderr=subprocess.STDOUT, universal_newlines=True)


def _query_package(rpm):
    metadata = _rpm_query(rpm, '-qp', '--qf', '%{NAME}\n%{VERSION}\n%{RELEASE}\n%{ARCH}\n')
    fields = metadata.splitlines()
    if len(fields) != 4:
        raise ValueError('RPM_METADATA_INVALID')
    name, version, release, arch = fields
    file_list = _rpm_query(rpm, '-qpl').splitlines()
    if (len(file_list) != len(set(file_list)) or
            any(not path.startswith('/') or '\r' in path or '\n' in path or
                '..' in path.split('/') for path in file_list)):
        raise ValueError('RPM_FILE_INVENTORY_INVALID')
    files = set(file_list)
    scripts = _rpm_query(rpm, '-qp', '--scripts').strip()
    configfiles = set(_rpm_query(rpm, '-qp', '--configfiles').splitlines())
    flags = _rpm_query(rpm, '-qp', '--qf', '[%{FILENAMES} %{FILEFLAGS:fflags}\n]')
    if _rpm_query(rpm, '-qp', '--qf', '%{FILEDIGESTALGO}\n').strip() != '8':
        raise ValueError('RPM_FILE_SHA256_REQUIRED')
    file_digests = {}
    digest_query = _rpm_query(rpm, '-qp', '--qf', '[%{FILENAMES} %{FILESIZES} %{FILEDIGESTS}\n]')
    for line in digest_query.splitlines():
        fields = line.split()
        if not fields:
            continue
        path = fields[0]
        if path not in RUNTIME_BINARIES:
            continue
        if len(fields) != 3:
            raise ValueError('RPM_FILE_DIGEST_INVENTORY_INVALID')
        _path, size, digest = fields
        if (path in file_digests or not size.isdigit() or
                not re.match(r'[0-9a-f]{64}\Z', digest)):
            raise ValueError('RPM_FILE_DIGEST_INVENTORY_INVALID')
        file_digests[path] = {'bytes': int(size), 'sha256': digest}
    runtime_binaries = {path: file_digests[path] for path in sorted(RUNTIME_BINARIES)
                        if path in file_digests}
    if set(runtime_binaries) != RUNTIME_BINARIES:
        raise ValueError('RPM_RUNTIME_BINARY_DIGEST_MISSING')
    return (name, version, release, arch, files, sorted(file_list), scripts,
            configfiles, flags, runtime_binaries)


def stage(rpm_path, build_manifest_path, output, snapshot_sha, dirty_patch_sha,
          host_profiles, installer_path=None):
    rpm_path = os.path.abspath(rpm_path)
    build_manifest_path = os.path.abspath(build_manifest_path)
    output = os.path.abspath(output)
    if os.path.islink(rpm_path) or not os.path.isfile(rpm_path):
        raise ValueError('RPM_MISSING_OR_SYMLINK')
    if os.path.islink(build_manifest_path) or not os.path.isfile(build_manifest_path):
        raise ValueError('BUILD_MANIFEST_MISSING_OR_SYMLINK')
    if installer_path is None:
        installer_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), INSTALLER_NAME)
    installer_path = os.path.abspath(installer_path)
    if os.path.islink(installer_path) or not os.path.isfile(installer_path):
        raise ValueError('INSTALLER_MISSING_OR_SYMLINK')
    if os.path.lexists(output):
        raise ValueError('OUTPUT_EXISTS')
    if not re.match(r'[0-9a-f]{64}\Z', snapshot_sha or '') or \
            not re.match(r'[0-9a-f]{64}\Z', dirty_patch_sha or ''):
        raise ValueError('SOURCE_PIN_INVALID')
    profiles = sorted(set(host_profiles))
    if not profiles or any(not re.match(r'[a-z0-9][a-z0-9._-]*\Z', p) for p in profiles):
        raise ValueError('HOST_PROFILE_INVALID')

    try:
        build = json.load(open(build_manifest_path))
    except (IOError, OSError, ValueError):
        raise ValueError('BUILD_MANIFEST_INVALID')
    if (build.get('schemaVersion') != 1 or build.get('package') != PACKAGE_NAME or
            build.get('sourceSnapshotSha256') != snapshot_sha or
            build.get('dirtyPatchSha256') != dirty_patch_sha or
            not re.match(r'[0-9a-f]{40}\Z', build.get('sourceRevision', ''))):
        raise ValueError('SOURCE_SNAPSHOT_PIN_MISMATCH')
    unit_records = [item for item in build.get('sourceFiles', [])
                    if item.get('path') == UNIT_SOURCE_PATH]
    if (len(unit_records) != 1 or
            not re.match(r'[0-9a-f]{64}\Z', unit_records[0].get('sha256', ''))):
        raise ValueError('SYSTEMD_UNIT_SOURCE_PIN_MISSING')

    (name, version, release, arch, files, file_list, scripts, configfiles, flags,
     runtime_binaries) = _query_package(rpm_path)
    base_release = build.get('rpmRelease', '')
    release_matches_build = (release == base_release or
                             (isinstance(base_release, STRING_TYPES) and release.startswith(base_release + '.')))
    if (name != PACKAGE_NAME or arch != 'x86_64' or
            build.get('rpmVersion') != version or not release_matches_build):
        raise ValueError('RPM_IDENTITY_OR_ABI_MISMATCH')
    if not REQUIRED_RPM_FILES.issubset(files):
        raise ValueError('RPM_FILE_INVENTORY_INCOMPLETE')
    if any(path.endswith('.ko') or path.startswith('/lib/modules/') or
           path.startswith('/usr/lib/modules/') for path in files):
        raise ValueError('KERNEL_ARTIFACT_FORBIDDEN')
    if scripts:
        raise ValueError('SCRIPTLETS_FORBIDDEN')
    if '/etc/zram-memory/config.json' not in configfiles or \
            not re.search(r'(?m)^/etc/zram-memory/config\.json\s+cn$', flags):
        raise ValueError('CONFIG_NOREPLACE_REQUIRED')

    os.mkdir(output, 0o755)
    staged_rpm = os.path.join(output, os.path.basename(rpm_path))
    shutil.copyfile(rpm_path, staged_rpm)
    os.chmod(staged_rpm, 0o644)
    shutil.copyfile(build_manifest_path, os.path.join(output, 'BUILD-MANIFEST.json'))
    staged_installer = os.path.join(output, INSTALLER_NAME)
    shutil.copyfile(installer_path, staged_installer)
    os.chmod(staged_installer, 0o755)
    package = {
        'name': name, 'version': version, 'release': release, 'architecture': arch,
        'filename': os.path.basename(staged_rpm), 'bytes': os.stat(staged_rpm).st_size,
        'sha256': _sha256(staged_rpm),
    }
    inventory = {
        'schemaVersion': 3,
        'trustModel': 'content-hash-pinned-not-signed',
        'package': package,
        'source': {
            'sourceRevision': build['sourceRevision'],
            'dirtyPatchSha256': dirty_patch_sha,
            'sourceSnapshotSha256': snapshot_sha,
            'buildManifestSha256': _sha256(build_manifest_path),
        },
        'supportedHostProfiles': profiles,
        'requiredFiles': sorted(REQUIRED_RPM_FILES),
        'systemdUnitSha256': unit_records[0]['sha256'],
        'runtimeBinaries': runtime_binaries,
        'installer': {'filename': INSTALLER_NAME,
                      'bytes': os.stat(staged_installer).st_size,
                      'sha256': _sha256(staged_installer)},
        'rpmFiles': file_list,
        'rpmFilesSha256': hashlib.sha256((''.join(path + '\n' for path in file_list)).encode()).hexdigest(),
        'kernelOrModuleIncluded': False,
        'configNoreplace': True,
        'scriptletsEmpty': True,
    }
    open(os.path.join(output, 'rpm-inventory.json'), 'w').write(
        json.dumps(inventory, sort_keys=True, indent=2,
                   separators=(',', ': ')) + '\n')
    return inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rpm')
    parser.add_argument('--rpm-dir')
    parser.add_argument('--build-manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--source-snapshot-sha256', required=True)
    parser.add_argument('--dirty-patch-sha256', required=True)
    parser.add_argument('--host-profiles', required=True)
    parser.add_argument('--installer-script')
    args = parser.parse_args()
    if bool(args.rpm) == bool(args.rpm_dir):
        parser.error('specify exactly one of --rpm or --rpm-dir')
    rpm_path = args.rpm
    if args.rpm_dir:
        candidates = [os.path.join(args.rpm_dir, name)
                      for name in os.listdir(args.rpm_dir)
                      if name.endswith('.rpm') and not name.endswith('.src.rpm')]
        if len(candidates) != 1:
            raise SystemExit('EXPECTED_ONE_BINARY_RPM:%d' % len(candidates))
        rpm_path = str(candidates[0])
    profiles = [profile for profile in args.host_profiles.split(',') if profile]
    result = stage(rpm_path, args.build_manifest, args.output,
                   args.source_snapshot_sha256, args.dirty_patch_sha256,
                   profiles, args.installer_script)
    print(json.dumps({'status': 'STAGED', 'output': os.path.realpath(args.output),
                      'packageSha256': result['package']['sha256']}))


if __name__ == '__main__':
    main()

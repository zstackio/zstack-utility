#!/usr/bin/env python
"""Freeze zstack-zram source and emit the properties for its Ant RPM build."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess

try:
    STRING_TYPES = (basestring,)
    INTEGER_TYPES = (int, long)
except NameError:
    STRING_TYPES = (str,)
    INTEGER_TYPES = (int,)


def _build_environment_id():
    if os.environ.get('ZSTACK_BUILD_ENVIRONMENT_ID', '').strip():
        return os.environ['ZSTACK_BUILD_ENVIRONMENT_ID'].strip()
    go = os.environ.get('GO', '').strip() or 'go'
    go = subprocess.check_output(['sh', '-c', 'command -v "$1"', 'sh', go],
                                 universal_newlines=True).strip()
    components = {
        'osRelease': open('/etc/os-release').read() if os.path.isfile('/etc/os-release') else 'unknown',
        'architecture': platform.machine(),
        'rpm': subprocess.check_output(['rpm', '--version'], universal_newlines=True).strip(),
        'goVersion': subprocess.check_output([go, 'version'], universal_newlines=True).strip(),
        'goBinarySha256': hashlib.sha256(open(go, 'rb').read()).hexdigest(),
    }
    canonical = json.dumps(components, sort_keys=True, separators=(',', ':')).encode()
    return 'sha256:' + hashlib.sha256(canonical).hexdigest()


def _git(root, *args):
    command = ['git', '-C', str(root)]
    command.extend(args)
    with open(os.devnull, 'wb') as devnull:
        return subprocess.check_output(command, stderr=devnull)


def _freeze_source(source, snapshot_dir):
    """Copy one checked-out source tree and pin its tracked inputs."""
    source = os.path.abspath(source)
    snapshot_dir = os.path.abspath(snapshot_dir)
    if os.path.islink(source) or not os.path.isdir(source):
        raise ValueError('CANONICAL_GIT_CHECKOUT_REQUIRED')
    try:
        inside_worktree = _git(source, 'rev-parse', '--is-inside-work-tree').decode().strip()
        git_root = os.path.realpath(_git(source, 'rev-parse', '--show-toplevel').decode().strip())
    except subprocess.CalledProcessError:
        raise ValueError('CANONICAL_GIT_CHECKOUT_REQUIRED')
    if inside_worktree != 'true' or git_root != os.path.realpath(source):
        raise ValueError('CANONICAL_GIT_CHECKOUT_REQUIRED')
    if (os.path.lexists(snapshot_dir) or source == snapshot_dir or
            snapshot_dir.startswith(source.rstrip(os.sep) + os.sep)):
        raise ValueError('ABSENT_EXTERNAL_OUTPUT_REQUIRED')
    if _git(source, 'ls-files', '--others', '--exclude-standard', '-z'):
        raise ValueError('UNTRACKED_SOURCE_INPUT_REFUSED')

    revision = _git(source, 'rev-parse', 'HEAD').decode().strip()
    patch = _git(source, 'diff', '--binary', '--full-index', 'HEAD', '--')
    epoch = int(_git(source, 'show', '-s', '--format=%ct', 'HEAD').decode().strip())
    names = [name.decode() for name in _git(source, 'ls-files', '-z').split(b'\0') if name]
    records = []
    for name in sorted(names):
        relative = name.split('/')
        if (name.startswith('/') or '..' in relative or '.' in relative or
                '' in relative or os.sep.join(relative) != name):
            raise ValueError('SOURCE_PATH_INVALID')
        path = os.path.join(source, *relative)
        if not os.path.exists(path) and not os.path.islink(path):
            continue
        cursor = source
        for component in relative:
            cursor = os.path.join(cursor, component)
            if os.path.islink(cursor):
                raise ValueError('SOURCE_SYMLINK_REFUSED:' + name)
        if not os.path.isfile(path):
            raise ValueError('SOURCE_REGULAR_FILE_REQUIRED:' + name)
        data = open(path, 'rb').read()
        records.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                        'bytes': len(data), 'mode': stat.S_IMODE(os.stat(path).st_mode)})
    required = {'service/go.mod', 'cli/go.mod', 'packaging/build-rpm.sh'}
    if not required.issubset({record['path'] for record in records}):
        raise ValueError('REQUIRED_BUILD_SOURCE_MISSING')

    os.makedirs(snapshot_dir)
    open(os.path.join(snapshot_dir, 'dirty.patch'), 'wb').write(patch)
    for record in records:
        dest = os.path.join(snapshot_dir, 'source', *record['path'].split('/'))
        dest_parent = os.path.dirname(dest)
        if not os.path.isdir(dest_parent):
            os.makedirs(dest_parent)
        shutil.copyfile(os.path.join(source, *record['path'].split('/')), dest)
        os.chmod(dest, record['mode'])
        if hashlib.sha256(open(dest, 'rb').read()).hexdigest() != record['sha256']:
            raise ValueError('SOURCE_CHANGED_DURING_FREEZE:' + record['path'])
    if _git(source, 'diff', '--binary', '--full-index', 'HEAD', '--') != patch:
        raise ValueError('PATCH_CHANGED_DURING_FREEZE')

    manifest = {'schemaVersion': 1, 'sourceRevision': revision,
                'sourceDateEpoch': epoch,
                'dirtyPatchSha256': hashlib.sha256(patch).hexdigest(), 'files': records}
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2,
                                 separators=(',', ': ')) + '\n').encode()
    manifest_path = os.path.join(snapshot_dir, 'SOURCE-SNAPSHOT.json')
    open(manifest_path, 'wb').write(manifest_bytes)
    return os.path.join(snapshot_dir, 'source'), manifest_path, patch


def prepare(source_checkout, snapshot_dir, output, version, release, epoch,
            build_environment_id, host_profiles, target_arch='x86_64'):
    source_checkout = os.path.abspath(source_checkout)
    snapshot_dir = os.path.abspath(snapshot_dir)
    output = os.path.abspath(output)
    if os.path.lexists(output):
        raise ValueError('BUILD_METADATA_OUTPUT_EXISTS')
    if not re.match(r'[0-9]+(?:\.[0-9]+)*\Z', version):
        raise ValueError('RPM_VERSION_INVALID')
    if not re.match(r'[A-Za-z0-9._+]+\Z', release):
        raise ValueError('RPM_RELEASE_INVALID')
    if target_arch != 'x86_64':
        raise ValueError('ZSTACK_ZRAM_TARGET_ARCH_UNSUPPORTED')
    if epoch in ('', None):
        epoch = None
    elif isinstance(epoch, STRING_TYPES) and re.match(r'[0-9]+\Z', epoch):
        epoch = int(epoch)
    elif isinstance(epoch, INTEGER_TYPES) and not isinstance(epoch, bool):
        pass
    else:
        raise ValueError('SOURCE_DATE_EPOCH_INVALID')
    if epoch is not None and epoch <= 0:
        raise ValueError('SOURCE_DATE_EPOCH_INVALID')
    profiles = [value.strip() for value in host_profiles.split(',') if value.strip()]
    if (not profiles or len(profiles) != len(set(profiles)) or
            any(not re.match(r'[a-z0-9][a-z0-9._-]*\Z', value) for value in profiles)):
        raise ValueError('HOST_PROFILE_INVENTORY_INVALID')
    build_environment_id = build_environment_id.strip() or _build_environment_id()

    source, manifest, patch = _freeze_source(source_checkout, snapshot_dir)
    manifest_bytes = open(manifest, 'rb').read()
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    data = json.loads(manifest_bytes)
    if epoch is None:
        epoch = data.get('sourceDateEpoch')
    if not isinstance(epoch, INTEGER_TYPES) or isinstance(epoch, bool) or epoch <= 0:
        raise ValueError('SOURCE_DATE_EPOCH_UNAVAILABLE')
    patch_bytes = patch
    patch_sha = hashlib.sha256(patch_bytes).hexdigest()
    if (data.get('schemaVersion') != 1 or
            not re.match(r'[0-9a-f]{40}\Z', data.get('sourceRevision', '')) or
            data.get('dirtyPatchSha256') != patch_sha):
        raise ValueError('SOURCE_SNAPSHOT_METADATA_INVALID')

    properties = {
        'zstackzram.frozenSource': str(source),
        'zstackzram.sourceSnapshotManifest': str(manifest),
        'zstackzram.sourceSnapshotSha256': digest,
        'zstackzram.sourceRevision': data['sourceRevision'],
        'zstackzram.dirtyPatchSha256': patch_sha,
        'zstackzram.sourceDirty': str(bool(patch_bytes)).lower(),
        'zstackzram.rpm.output': os.path.join(os.path.dirname(output), 'rpm-output'),
        'zstackzram.version': version,
        'zstackzram.release': release,
        'zstackzram.sourceDateEpoch': str(epoch),
        'zstackzram.hostProfiles': ','.join(sorted(profiles)),
        'zstackzram.buildEnvironmentId': build_environment_id,
        'zstackzram.targetArch': target_arch,
        'zstackzram.metadataSchemaVersion': '1',
    }
    output_dir = os.path.dirname(output)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    open(output, 'w').write(''.join('%s=%s\n' % item for item in sorted(properties.items())))
    return properties


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-checkout', required=True)
    parser.add_argument('--snapshot-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--source-date-epoch', default='')
    parser.add_argument('--build-environment-id', default='')
    parser.add_argument('--host-profiles', required=True)
    parser.add_argument('--target-arch', default='x86_64')
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_checkout, args.snapshot_dir, args.output,
                             args.version, args.release, args.source_date_epoch,
                             args.build_environment_id, args.host_profiles,
                             args.target_arch), sort_keys=True))


if __name__ == '__main__':
    main()

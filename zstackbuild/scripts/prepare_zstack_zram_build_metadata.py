#!/usr/bin/env python3
"""Freeze zstack-zram source and emit the properties for its Ant RPM build."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess


def _build_environment_id():
    if os.environ.get('ZSTACK_BUILD_ENVIRONMENT_ID', '').strip():
        return os.environ['ZSTACK_BUILD_ENVIRONMENT_ID'].strip()
    go = subprocess.check_output(['sh', '-c', 'command -v go'], universal_newlines=True).strip()
    components = {
        'osRelease': Path('/etc/os-release').read_text() if Path('/etc/os-release').is_file() else 'unknown',
        'architecture': platform.machine(),
        'rpm': subprocess.check_output(['rpm', '--version'], universal_newlines=True).strip(),
        'goVersion': subprocess.check_output([go, 'version'], universal_newlines=True).strip(),
        'goBinarySha256': hashlib.sha256(Path(go).read_bytes()).hexdigest(),
    }
    canonical = json.dumps(components, sort_keys=True, separators=(',', ':')).encode()
    return 'sha256:' + hashlib.sha256(canonical).hexdigest()


def _git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args],
                                   stderr=subprocess.DEVNULL)


def _freeze_source(source, snapshot_dir):
    """Copy one checked-out source tree and pin its tracked inputs."""
    source = Path(source).absolute()
    snapshot_dir = Path(snapshot_dir).absolute()
    if source.is_symlink() or not source.is_dir():
        raise ValueError('CANONICAL_GIT_CHECKOUT_REQUIRED')
    try:
        inside_worktree = _git(source, 'rev-parse', '--is-inside-work-tree').decode().strip()
        git_root = Path(_git(source, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    except subprocess.CalledProcessError as error:
        raise ValueError('CANONICAL_GIT_CHECKOUT_REQUIRED') from error
    if inside_worktree != 'true' or git_root != source.resolve():
        raise ValueError('CANONICAL_GIT_CHECKOUT_REQUIRED')
    if (snapshot_dir.exists() or snapshot_dir.is_symlink() or source == snapshot_dir or
            source in snapshot_dir.parents):
        raise ValueError('ABSENT_EXTERNAL_OUTPUT_REQUIRED')
    if _git(source, 'ls-files', '--others', '--exclude-standard', '-z'):
        raise ValueError('UNTRACKED_SOURCE_INPUT_REFUSED')

    revision = _git(source, 'rev-parse', 'HEAD').decode().strip()
    patch = _git(source, 'diff', '--binary', '--full-index', 'HEAD', '--')
    epoch = int(_git(source, 'show', '-s', '--format=%ct', 'HEAD').decode().strip())
    names = [name.decode() for name in _git(source, 'ls-files', '-z').split(b'\0') if name]
    records = []
    for name in sorted(names):
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix() != name:
            raise ValueError('SOURCE_PATH_INVALID')
        path = source / name
        if not path.exists() and not path.is_symlink():
            continue
        cursor = source
        for component in relative.parts:
            cursor = cursor / component
            if cursor.is_symlink():
                raise ValueError('SOURCE_SYMLINK_REFUSED:' + name)
        if not path.is_file():
            raise ValueError('SOURCE_REGULAR_FILE_REQUIRED:' + name)
        data = path.read_bytes()
        records.append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(),
                        'bytes': len(data), 'mode': stat.S_IMODE(path.stat().st_mode)})
    required = {'service/go.mod', 'cli/go.mod', 'packaging/build-rpm.sh'}
    if not required.issubset({record['path'] for record in records}):
        raise ValueError('REQUIRED_BUILD_SOURCE_MISSING')

    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / 'dirty.patch').write_bytes(patch)
    for record in records:
        dest = snapshot_dir / 'source' / record['path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / record['path'], dest)
        dest.chmod(record['mode'])
        if hashlib.sha256(dest.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('SOURCE_CHANGED_DURING_FREEZE:' + record['path'])
    if _git(source, 'diff', '--binary', '--full-index', 'HEAD', '--') != patch:
        raise ValueError('PATCH_CHANGED_DURING_FREEZE')

    manifest = {'schemaVersion': 1, 'sourceRevision': revision,
                'sourceDateEpoch': epoch,
                'dirtyPatchSha256': hashlib.sha256(patch).hexdigest(), 'files': records}
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    manifest_path = snapshot_dir / 'SOURCE-SNAPSHOT.json'
    manifest_path.write_bytes(manifest_bytes)
    return snapshot_dir / 'source', manifest_path, patch


def prepare(source_checkout, snapshot_dir, output, version, release, epoch,
            build_environment_id, host_profiles, target_arch='x86_64'):
    source_checkout = Path(source_checkout).absolute()
    snapshot_dir = Path(snapshot_dir).absolute()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('BUILD_METADATA_OUTPUT_EXISTS')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', version):
        raise ValueError('RPM_VERSION_INVALID')
    if not re.fullmatch(r'[A-Za-z0-9._+]+', release):
        raise ValueError('RPM_RELEASE_INVALID')
    if target_arch != 'x86_64':
        raise ValueError('ZSTACK_ZRAM_TARGET_ARCH_UNSUPPORTED')
    if epoch in ('', None):
        epoch = None
    elif isinstance(epoch, str) and re.fullmatch(r'[0-9]+', epoch):
        epoch = int(epoch)
    elif type(epoch) is not int:
        raise ValueError('SOURCE_DATE_EPOCH_INVALID')
    if epoch is not None and epoch <= 0:
        raise ValueError('SOURCE_DATE_EPOCH_INVALID')

    source, manifest, patch = _freeze_source(source_checkout, snapshot_dir)
    manifest_bytes = manifest.read_bytes()
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    data = json.loads(manifest_bytes)
    if epoch is None:
        epoch = data.get('sourceDateEpoch')
    if type(epoch) is not int or epoch <= 0:
        raise ValueError('SOURCE_DATE_EPOCH_UNAVAILABLE')
    build_environment_id = build_environment_id.strip() or _build_environment_id()
    profiles = [value.strip() for value in host_profiles.split(',') if value.strip()]
    if (not profiles or len(profiles) != len(set(profiles)) or
            any(not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', value) for value in profiles)):
        raise ValueError('HOST_PROFILE_INVENTORY_INVALID')
    patch_bytes = patch
    patch_sha = hashlib.sha256(patch_bytes).hexdigest()
    if (data.get('schemaVersion') != 1 or
            not re.fullmatch(r'[0-9a-f]{40}', data.get('sourceRevision', '')) or
            data.get('dirtyPatchSha256') != patch_sha):
        raise ValueError('SOURCE_SNAPSHOT_METADATA_INVALID')

    properties = {
        'zstackzram.frozenSource': str(source),
        'zstackzram.sourceSnapshotManifest': str(manifest),
        'zstackzram.sourceSnapshotSha256': digest,
        'zstackzram.sourceRevision': data['sourceRevision'],
        'zstackzram.dirtyPatchSha256': patch_sha,
        'zstackzram.sourceDirty': str(bool(patch_bytes)).lower(),
        'zstackzram.rpm.output': str(output.parent / 'rpm-output'),
        'zstackzram.version': version,
        'zstackzram.release': release,
        'zstackzram.sourceDateEpoch': str(epoch),
        'zstackzram.hostProfiles': ','.join(sorted(profiles)),
        'zstackzram.buildEnvironmentId': build_environment_id,
        'zstackzram.targetArch': target_arch,
        'zstackzram.metadataSchemaVersion': '1',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join('%s=%s\n' % item for item in sorted(properties.items())))
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

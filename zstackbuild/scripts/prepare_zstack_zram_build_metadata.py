#!/usr/bin/env python3
"""Verify a frozen zstack-zram checkout and emit Ant RPM build properties."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
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


def prepare(source, snapshot_dir, output, version, release, epoch, build_environment_id,
            host_profiles, target_arch='x86_64'):
    source = Path(source).absolute()
    snapshot_dir = Path(snapshot_dir).absolute()
    output = Path(output).absolute()
    manifest = snapshot_dir / 'SOURCE-SNAPSHOT.json'
    patch = snapshot_dir / 'dirty.patch'
    if (source.is_symlink() or not source.is_dir() or snapshot_dir.is_symlink() or
            not snapshot_dir.is_dir() or manifest.is_symlink() or patch.is_symlink() or
            not manifest.is_file() or not patch.is_file()):
        raise ValueError('FROZEN_SOURCE_INPUTS_MISSING_OR_SYMLINK')
    if output.exists() or output.is_symlink():
        raise ValueError('BUILD_METADATA_OUTPUT_EXISTS')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', version):
        raise ValueError('RPM_VERSION_INVALID')
    if not re.fullmatch(r'[A-Za-z0-9._+]+', release):
        raise ValueError('RPM_RELEASE_INVALID')
    manifest_bytes = manifest.read_bytes()
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    data = json.loads(manifest_bytes)
    if target_arch != 'x86_64':
        raise ValueError('ZSTACK_ZRAM_TARGET_ARCH_UNSUPPORTED')
    if not str(epoch).isdigit():
        epoch = data.get('sourceDateEpoch')
    if not isinstance(epoch, int) or epoch <= 0:
        raise ValueError('SOURCE_DATE_EPOCH_UNAVAILABLE')
    build_environment_id = build_environment_id.strip() or _build_environment_id()
    profiles = [value.strip() for value in host_profiles.split(',') if value.strip()]
    if (not profiles or len(profiles) != len(set(profiles)) or
            any(not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', value) for value in profiles)):
        raise ValueError('HOST_PROFILE_INVENTORY_INVALID')
    patch_bytes = patch.read_bytes()
    patch_sha = hashlib.sha256(patch_bytes).hexdigest()
    if (data.get('schemaVersion') != 1 or
            not re.fullmatch(r'[0-9a-f]{40}', data.get('sourceRevision', '')) or
            data.get('dirtyPatchSha256') != patch_sha):
        raise ValueError('SOURCE_SNAPSHOT_METADATA_INVALID')
    verifier = source / 'packaging' / 'verify-source-snapshot.py'
    subprocess.check_call([
        'python3', str(verifier), '--source', str(source), '--manifest', str(manifest),
        '--manifest-sha256', digest, '--source-revision', data['sourceRevision'],
        '--dirty-patch-sha256', patch_sha,
    ], stdout=subprocess.DEVNULL)
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
    parser.add_argument('--source', required=True)
    parser.add_argument('--snapshot-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--source-date-epoch', default='')
    parser.add_argument('--build-environment-id', default='')
    parser.add_argument('--host-profiles', required=True)
    parser.add_argument('--target-arch', default='x86_64')
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.snapshot_dir, args.output, args.version,
                             args.release, args.source_date_epoch,
                             args.build_environment_id, args.host_profiles,
                             args.target_arch), sort_keys=True))


if __name__ == '__main__':
    main()

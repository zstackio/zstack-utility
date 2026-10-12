#!/usr/bin/env python3
"""Create immutable, hash-pinned source input for the standard Ant RPM target."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess


def _git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def freeze(source, output):
    source, output = Path(source).absolute(), Path(output).absolute()
    if source.is_symlink() or not (source / '.git').is_dir():
        raise ValueError('CANONICAL_GIT_CHECKOUT_REQUIRED')
    if output.exists() or output.is_symlink() or source == output or source in output.parents:
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
    output.mkdir(parents=True)
    (output / 'dirty.patch').write_bytes(patch)
    for record in records:
        dest = output / 'source' / record['path']
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
    data = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    (output / 'SOURCE-SNAPSHOT.json').write_bytes(data)
    return {'source': str(output / 'source'), 'manifest': str(output / 'SOURCE-SNAPSHOT.json'),
            'manifestSha256': hashlib.sha256(data).hexdigest(), 'sourceRevision': revision,
            'sourceDateEpoch': epoch, 'dirtyPatchSha256': manifest['dirtyPatchSha256'],
            'sourceDirty': bool(patch), 'files': len(records), 'deployable': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.source, args.output), sort_keys=True))


if __name__ == '__main__':
    main()

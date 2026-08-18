#!/bin/bash

set -euo pipefail

shell_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
repo_root="$(cd "${shell_dir}/.." >/dev/null 2>&1 && pwd)"
test_root="$(mktemp -d)"
trap 'chmod -R u+w "${test_root}" 2>/dev/null || true; rm -rf "${test_root}"' EXIT

artifact_root="${test_root}/artifacts"
mount_point="${test_root}/model-centers/123e4567-e89b-12d3-a456-426614174000"
runtime_root="${test_root}/runtime-home"
service_path="${test_root}/service/zstack-baremetal-runtime-agent.service"

mkdir -p "${artifact_root}" "${mount_point}" "${runtime_root}/releases" "$(dirname "${service_path}")"
printf 'runtime-service\n' > "${service_path}"

export PYTHONPATH="${repo_root}:${PYTHONPATH:-}"
export TEST_ROOT="${test_root}"
export ARTIFACT_ROOT="${artifact_root}"
export MOUNT_POINT="${mount_point}"
export RUNTIME_ROOT="${runtime_root}"
export SERVICE_PATH="${service_path}"

python3 <<'PY'
import hashlib
import io
import json
import os
import tarfile
import uuid

from bm_instance_agent import runtime_artifact


def build_tar(path, members):
    with tarfile.open(path, 'w:gz') as archive:
        for name, payload, member_type, mode in members:
            info = tarfile.TarInfo(name)
            info.type = member_type
            info.mode = mode
            info.uid = 0
            info.gid = 0
            info.uname = ''
            info.gname = ''
            info.size = 0 if info.isdir() else len(payload)
            archive.addfile(info, io.BytesIO(payload) if not info.isdir() else None)


test_root = os.environ['TEST_ROOT']
artifact_root = os.environ['ARTIFACT_ROOT']
mount_point = os.environ['MOUNT_POINT']
runtime_root = os.environ['RUNTIME_ROOT']
service_path = os.environ['SERVICE_PATH']
artifact_uuid = str(uuid.uuid4())
artifact_path = os.path.join(mount_point, artifact_uuid)
build_tar(
    artifact_path,
    [('bin/python', b'#!/bin/sh\nexit 0\n', tarfile.REGTYPE, 0o755),
     ('lib/data.txt', b'data\n', tarfile.REGTYPE, 0o644)])

digest = hashlib.sha256(open(artifact_path, 'rb').read()).hexdigest()
payload = {
    'requestId': 'request-prepare-001',
    'generation': 7,
    'workloadSpec': {
        'allocationUuid': 'allocation-001',
        'runtimeArtifact': {
            'kind': 'CondaPackage',
            'digest': 'sha256:%s' % digest,
            'source': 'model-center:runtime/vllm-0.8.5',
            'localPath': os.path.join(artifact_root, 'sha256-%s' % digest),
            'materialization': {
                'mode': 'ModelCenterArtifact',
                'modelCenterUuid': os.path.basename(mount_point),
                'artifactUuid': artifact_uuid,
                'layout': 'CondaPrefix'
            }
        }
    }
}
mount_facts = {
    'juicefsReadOnlyMounts': [{
        'mountPoint': mount_point,
        'root': '/',
        'mountSource': '/var/lib/zstack/aios/model-centers/%s' % os.path.basename(mount_point),
        'readOnly': True
    }]
}

materializer = runtime_artifact.RuntimeArtifactMaterializer(
    artifact_root=artifact_root,
    owner_uid=None,
    owner_gid=None)
resolved = materializer.resolve_prepare_payload(payload, mount_facts)
calls = []
real_materialize_locked = materializer._materialize_locked


def counted(spec):
    calls.append(spec.digest)
    return real_materialize_locked(spec)


materializer._materialize_locked = counted
path1 = materializer.materialize_spec(resolved)
path2 = materializer.materialize_spec(resolved)
assert path1 == path2
assert calls == ['sha256:%s' % digest]
assert open(os.path.join(path1, '.zstack-artifact-digest')).read().strip() == 'sha256:%s' % digest
assert not os.listdir(os.path.join(runtime_root, 'releases'))
assert open(service_path).read().strip() == 'runtime-service'

bad_uuid = str(uuid.uuid4())
bad_path = os.path.join(mount_point, bad_uuid)
build_tar(
    bad_path,
    [('bad-link', b'', tarfile.SYMTYPE, 0o777)])
bad_digest = hashlib.sha256(open(bad_path, 'rb').read()).hexdigest()
bad_payload = json.loads(json.dumps(payload))
bad_payload['workloadSpec']['runtimeArtifact']['digest'] = 'sha256:%s' % bad_digest
bad_payload['workloadSpec']['runtimeArtifact']['localPath'] = os.path.join(
    artifact_root, 'sha256-%s' % bad_digest)
bad_payload['workloadSpec']['runtimeArtifact']['materialization']['artifactUuid'] = bad_uuid
bad_resolved = materializer.resolve_prepare_payload(bad_payload, mount_facts)
try:
    materializer.materialize_spec(bad_resolved)
    raise AssertionError('unsafe archive should fail')
except runtime_artifact.RuntimeArtifactError as err:
    assert err.code == 'BMR-ARTIFACT-0004'

leftovers = [name for name in os.listdir(artifact_root) if name.startswith('.materializing-')]
assert leftovers == []
assert open(os.path.join(path1, '.zstack-artifact-digest')).read().strip() == 'sha256:%s' % digest
assert not os.listdir(os.path.join(runtime_root, 'releases'))
assert open(service_path).read().strip() == 'runtime-service'
PY

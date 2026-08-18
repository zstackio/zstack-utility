import copy
import hashlib
import io
import os
import shutil
import tarfile
import tempfile
import unittest
import uuid

from bm_instance_agent import runtime_artifact


class TestRuntimeArtifactMaterializer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.artifact_root = os.path.join(self.temp_dir, 'cache')
        self.mount_point = os.path.join(
            self.temp_dir, 'model-centers', str(uuid.uuid4()))
        os.makedirs(self.mount_point)
        self.materializer = runtime_artifact.RuntimeArtifactMaterializer(
            artifact_root=self.artifact_root,
            owner_uid=None,
            owner_gid=None)
        self.model_center_uuid = os.path.basename(self.mount_point)
        self.artifact_uuid = str(uuid.uuid4())
        self.runtime_artifact = None
        self.mount_facts = {
            'juicefsReadOnlyMounts': [{
                'mountPoint': self.mount_point,
                'root': '/',
                'mountSource': '/var/lib/zstack/aios/model-centers/%s'
                               % self.model_center_uuid,
                'readOnly': True
            }]
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_materialize_prepare_payload_rewrites_local_path_from_digest(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\nexit 0\n'}, source='http://evil/?q=$(id)')
        payload = self._payload()

        updated = self.materializer.materialize_prepare_payload(
            copy.deepcopy(payload),
            self.mount_facts)

        expected_path = os.path.join(
            self.artifact_root, 'sha256-%s' % self.runtime_artifact['digest'][7:])
        self.assertEqual(
            expected_path,
            updated['workloadSpec']['runtimeArtifact']['localPath'])
        self.assertTrue(os.path.isdir(expected_path))
        with open(os.path.join(expected_path, '.zstack-artifact-digest'), 'r') as stream:
            self.assertEqual(self.runtime_artifact['digest'], stream.read().strip())

        resolved = self.materializer.resolve_prepare_payload(
            copy.deepcopy(payload),
            self.mount_facts)
        self.assertEqual(
            os.path.join(self.mount_point, self.artifact_uuid),
            resolved.source_path)
        self.assertEqual('http://evil/?q=$(id)', resolved.source_label)

    def test_prepare_payload_without_materialization_is_passthrough(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()
        del payload['workloadSpec']['runtimeArtifact']['materialization']

        updated = self.materializer.materialize_prepare_payload(
            copy.deepcopy(payload),
            self.mount_facts)

        self.assertEqual(payload, updated)

    def test_resolve_requires_exactly_one_readonly_mount(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()

        with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
            self.materializer.resolve_prepare_payload(payload, {'juicefsReadOnlyMounts': []})
        self.assertEqual('BMR-ARTIFACT-0002', ctx.exception.code)

        another_mount = os.path.join(
            self.temp_dir, 'other', self.model_center_uuid)
        os.makedirs(another_mount)
        with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
            self.materializer.resolve_prepare_payload(payload, {
                'juicefsReadOnlyMounts': [
                    self.mount_facts['juicefsReadOnlyMounts'][0],
                    {
                        'mountPoint': another_mount,
                        'root': '/',
                        'mountSource': '/dup/%s' % self.model_center_uuid,
                        'readOnly': True
                    }
                ]
            })
        self.assertEqual('BMR-ARTIFACT-0002', ctx.exception.code)

    def test_resolve_rejects_non_readonly_or_unmounted_mount(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()

        with self.assertRaises(runtime_artifact.RuntimeArtifactError):
            self.materializer.resolve_prepare_payload(payload, {
                'juicefsReadOnlyMounts': [{
                    'mountPoint': self.mount_point,
                    'root': '/',
                    'mountSource': '/x/%s' % self.model_center_uuid,
                    'readOnly': False
                }]
            })

        shutil.rmtree(self.mount_point)
        with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
            self.materializer.resolve_prepare_payload(payload, self.mount_facts)
        self.assertEqual('BMR-ARTIFACT-0002', ctx.exception.code)

    def test_resolve_rejects_unsupported_kind_mode_layout(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()

        for key, value in (
                ('kind', 'OciImage'),
                ('mode', 'LocalPath'),
                ('layout', 'Tarball')):
            invalid = copy.deepcopy(payload)
            if key == 'kind':
                invalid['workloadSpec']['runtimeArtifact']['kind'] = value
            else:
                invalid['workloadSpec']['runtimeArtifact']['materialization'][key] = value
            with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
                self.materializer.resolve_prepare_payload(invalid, self.mount_facts)
            self.assertEqual('BMR-ARTIFACT-0001', ctx.exception.code)

    def test_resolve_rejects_digest_path_mismatch(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()
        payload['workloadSpec']['runtimeArtifact']['localPath'] = '/tmp/evil'

        with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
            self.materializer.resolve_prepare_payload(payload, self.mount_facts)
        self.assertEqual('BMR-ARTIFACT-0001', ctx.exception.code)

    def test_resolve_rejects_uppercase_digest(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()
        payload['workloadSpec']['runtimeArtifact']['digest'] = (
            payload['workloadSpec']['runtimeArtifact']['digest'].upper())

        with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
            self.materializer.resolve_prepare_payload(payload, self.mount_facts)
        self.assertEqual('BMR-ARTIFACT-0001', ctx.exception.code)

    def test_archive_prevalidation_rejects_unsafe_members(self):
        cases = (
            ('../escape', tarfile.REGTYPE),
            ('/absolute', tarfile.REGTYPE),
            ('symlink', tarfile.SYMTYPE),
            ('hardlink', tarfile.LNKTYPE),
            ('fifo', tarfile.FIFOTYPE),
        )
        for name, tar_type in cases:
            self._write_artifact(
                {},
                members=[self._member(name, b'data', tar_type=tar_type)])
            with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
                self.materializer.materialize_prepare_payload(
                    self._payload(),
                    self.mount_facts)
            self.assertEqual('BMR-ARTIFACT-0004', ctx.exception.code)

    def test_archive_prevalidation_rejects_prefix_collisions_before_extract(self):
        self._write_artifact(
            {},
            members=[
                self._member('bin', b'file'),
                self._member('bin/python', b'#!/bin/sh\n'),
            ])

        with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
            self.materializer.materialize_prepare_payload(
                self._payload(),
                self.mount_facts)
        self.assertEqual('BMR-ARTIFACT-0004', ctx.exception.code)

    def test_materialize_rejects_digest_mismatch_before_extract(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()
        payload['workloadSpec']['runtimeArtifact']['digest'] = 'sha256:' + ('0' * 64)
        payload['workloadSpec']['runtimeArtifact']['localPath'] = os.path.join(
            self.artifact_root, 'sha256-%s' % ('0' * 64))

        with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
            self.materializer.materialize_prepare_payload(payload, self.mount_facts)
        self.assertEqual('BMR-ARTIFACT-0003', ctx.exception.code)

    def test_materialize_uses_digest_scoped_cache_hit(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()
        resolved = self.materializer.resolve_prepare_payload(payload, self.mount_facts)
        real_materialize_locked = self.materializer._materialize_locked
        calls = []

        def counted(spec):
            calls.append(spec.digest)
            return real_materialize_locked(spec)

        self.materializer._materialize_locked = counted
        try:
            path1 = self.materializer.materialize_spec(resolved)
            path2 = self.materializer.materialize_spec(resolved)
        finally:
            self.materializer._materialize_locked = real_materialize_locked

        self.assertEqual(path1, path2)
        self.assertEqual([resolved.digest], calls)
        self.assertTrue(os.path.exists(
            os.path.join(self.artifact_root, '.locks',
                         'sha256-%s.lock' % resolved.digest_hex)))

    def test_failure_cleans_only_caller_temp_dir_and_preserves_verified_cache(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()
        resolved = self.materializer.resolve_prepare_payload(payload, self.mount_facts)
        good_path = self.materializer.materialize_spec(resolved)

        second_artifact_uuid = str(uuid.uuid4())
        second_digest = self._write_artifact(
            {'bin/python': b'#!/bin/sh\n'},
            artifact_uuid=second_artifact_uuid)
        second_payload = self._payload(
            artifact_uuid=second_artifact_uuid,
            digest=second_digest)
        second_resolved = self.materializer.resolve_prepare_payload(
            second_payload,
            self.mount_facts)
        real_extract = self.materializer._extract_archive

        def boom(spec, temp_dir):
            with open(os.path.join(temp_dir, 'partial'), 'w') as stream:
                stream.write('partial')
            raise runtime_artifact.RuntimeArtifactError(
                500, 'BMR-ARTIFACT-0006', 'boom', True, 'InstanceAgent')

        self.materializer._extract_archive = boom
        try:
            with self.assertRaises(runtime_artifact.RuntimeArtifactError):
                self.materializer.materialize_spec(second_resolved)
        finally:
            self.materializer._extract_archive = real_extract

        self.assertTrue(os.path.isdir(good_path))
        self.assertFalse(os.path.exists(second_resolved.local_path))
        leftovers = [
            name for name in os.listdir(self.artifact_root)
            if name.startswith('.materializing-')
        ]
        self.assertEqual([], leftovers)

    def test_conflicting_existing_cache_entry_fails_closed(self):
        self._write_artifact({'bin/python': b'#!/bin/sh\n'})
        payload = self._payload()
        resolved = self.materializer.resolve_prepare_payload(payload, self.mount_facts)
        os.makedirs(resolved.local_path)
        with open(os.path.join(resolved.local_path, '.zstack-artifact-digest'), 'w') as stream:
            stream.write('sha256:%s' % ('0' * 64))

        with self.assertRaises(runtime_artifact.RuntimeArtifactError) as ctx:
            self.materializer.materialize_spec(resolved)
        self.assertEqual('BMR-ARTIFACT-0005', ctx.exception.code)

    def _payload(self, artifact_uuid=None, digest=None):
        return {
            'requestId': 'request-prepare-001',
            'generation': 7,
            'workloadSpec': {
                'allocationUuid': 'allocation-001',
                'runtimeArtifact': {
                    'kind': 'CondaPackage',
                    'digest': digest or self.runtime_artifact['digest'],
                    'source': self.runtime_artifact['source'],
                    'localPath': self.runtime_artifact['localPath'],
                    'materialization': {
                        'mode': 'ModelCenterArtifact',
                        'modelCenterUuid': self.model_center_uuid,
                        'artifactUuid': artifact_uuid or self.artifact_uuid,
                        'layout': 'CondaPrefix'
                    }
                }
            }
        }

    def _write_artifact(self, regular_files, source='model-center:runtime/vllm',
                        members=None, artifact_uuid=None):
        artifact_uuid = artifact_uuid or self.artifact_uuid
        artifact_path = os.path.join(self.mount_point, artifact_uuid)
        member_list = members or []
        for name, data in regular_files.items():
            member_list.append(self._member(name, data))

        with tarfile.open(artifact_path, 'w:gz') as archive:
            for member in member_list:
                payload = member.pop('payload', b'')
                info = tarfile.TarInfo(member['name'])
                info.type = member['type']
                info.uid = member.get('uid', 0)
                info.gid = member.get('gid', 0)
                info.uname = member.get('uname', '')
                info.gname = member.get('gname', '')
                info.mode = member.get('mode', 0o644)
                info.linkname = member.get('linkname', '')
                info.size = 0 if info.isdir() else len(payload)
                archive.addfile(info, io.BytesIO(payload) if not info.isdir() else None)

        digest = 'sha256:%s' % self._sha256(artifact_path)
        self.runtime_artifact = {
            'digest': digest,
            'source': source,
            'localPath': os.path.join(
                self.artifact_root, 'sha256-%s' % digest[7:])
        }
        if artifact_uuid == self.artifact_uuid:
            return digest
        return digest

    @staticmethod
    def _member(name, payload, tar_type=tarfile.REGTYPE, mode=0o644):
        return {
            'name': name,
            'payload': payload,
            'type': tar_type,
            'mode': mode,
            'uid': 0,
            'gid': 0,
            'uname': '',
            'gname': '',
        }

    @staticmethod
    def _sha256(path):
        digest = hashlib.sha256()
        with open(path, 'rb') as stream:
            digest.update(stream.read())
        return digest.hexdigest()

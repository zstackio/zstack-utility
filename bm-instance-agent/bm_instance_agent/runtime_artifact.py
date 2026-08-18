# -*- coding: utf-8 -*-

import errno
import fcntl
import hashlib
import os
import shutil
import stat
import tarfile
import tempfile
import uuid


try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)


class RuntimeArtifactError(Exception):

    def __init__(self, status, code, message, retryable=False,
                 owner='Caller', details=None):
        super(RuntimeArtifactError, self).__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.owner = owner
        self.details = details or {}


class RuntimeArtifactSpec(object):

    def __init__(self, digest, digest_hex, local_path, source_path,
                 model_center_uuid, artifact_uuid, source_label):
        self.digest = digest
        self.digest_hex = digest_hex
        self.local_path = local_path
        self.source_path = source_path
        self.model_center_uuid = model_center_uuid
        self.artifact_uuid = artifact_uuid
        self.source_label = source_label


class RuntimeArtifactMaterializer(object):

    ARTIFACT_ROOT = '/var/lib/zstack/baremetal-runtime/artifacts'
    DIGEST_MARKER = '.zstack-artifact-digest'
    LOCK_DIRNAME = '.locks'

    def __init__(self, artifact_root=None, owner_uid=0, owner_gid=0):
        self.artifact_root = artifact_root or self.ARTIFACT_ROOT
        self.owner_uid = owner_uid
        self.owner_gid = owner_gid

    def resolve_prepare_payload(self, payload, mount_facts):
        workload_spec = payload.get('workloadSpec')
        if not isinstance(workload_spec, dict):
            return None

        runtime_artifact = workload_spec.get('runtimeArtifact')
        if runtime_artifact is None:
            return None
        if not isinstance(runtime_artifact, dict):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact must be a json object')

        materialization = runtime_artifact.get('materialization')
        if materialization is None:
            return None
        if not isinstance(materialization, dict):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.materialization must be a json object')

        kind = runtime_artifact.get('kind')
        if kind != 'CondaPackage':
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.kind must be CondaPackage for materialization',
                details={'kind': kind})

        mode = materialization.get('mode')
        if mode != 'ModelCenterArtifact':
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.materialization.mode must be ModelCenterArtifact',
                details={'mode': mode})

        layout = materialization.get('layout')
        if layout != 'CondaPrefix':
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.materialization.layout must be CondaPrefix',
                details={'layout': layout})

        digest_hex = self._normalize_digest(runtime_artifact.get('digest'))
        local_path = self._build_cache_path(digest_hex)
        requested_local_path = runtime_artifact.get('localPath')
        if requested_local_path and requested_local_path != local_path:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.localPath must be derived from runtimeArtifact.digest',
                details={'localPath': requested_local_path,
                         'expectedLocalPath': local_path})

        model_center_uuid = self._normalize_uuid(
            materialization.get('modelCenterUuid'),
            'runtimeArtifact.materialization.modelCenterUuid')
        artifact_uuid = self._normalize_uuid(
            materialization.get('artifactUuid'),
            'runtimeArtifact.materialization.artifactUuid')

        mount = self._resolve_source_mount(model_center_uuid, mount_facts)
        source_path = os.path.join(mount['mountPoint'], artifact_uuid)
        self._validate_source_path(source_path)

        return RuntimeArtifactSpec(
            digest='sha256:%s' % digest_hex,
            digest_hex=digest_hex,
            local_path=local_path,
            source_path=source_path,
            model_center_uuid=model_center_uuid,
            artifact_uuid=artifact_uuid,
            source_label=runtime_artifact.get('source'))

    def materialize_prepare_payload(self, payload, mount_facts):
        spec = self.resolve_prepare_payload(payload, mount_facts)
        if spec is None:
            return payload

        final_path = self.materialize_spec(spec)
        payload['workloadSpec']['runtimeArtifact']['localPath'] = final_path
        return payload

    def materialize_spec(self, spec):
        self._ensure_directory(self.artifact_root, 0o755)
        cache_path = self._validate_cache_entry(spec.local_path, spec.digest)
        if cache_path is not None:
            return cache_path

        lock_path = self._lock_path(spec.digest_hex)
        self._ensure_directory(os.path.dirname(lock_path), 0o755)
        with self._exclusive_lock(lock_path):
            cache_path = self._validate_cache_entry(spec.local_path, spec.digest)
            if cache_path is not None:
                return cache_path
            return self._materialize_locked(spec)

    def _materialize_locked(self, spec):
        temp_dir = tempfile.mkdtemp(
            prefix='.materializing-%s-' % spec.digest_hex[:12],
            dir=self.artifact_root)
        try:
            self._extract_archive(spec, temp_dir)
            marker_path = os.path.join(temp_dir, self.DIGEST_MARKER)
            self._write_marker(marker_path, spec.digest)
            self._finalize_tree_permissions(temp_dir)
            os.rename(temp_dir, spec.local_path)
            temp_dir = None
            return spec.local_path
        except OSError as err:
            if err.errno == errno.EEXIST:
                cache_path = self._validate_cache_entry(spec.local_path, spec.digest)
                if cache_path is not None:
                    return cache_path
            raise RuntimeArtifactError(
                500,
                'BMR-ARTIFACT-0006',
                'runtime artifact materialization failed',
                retryable=True,
                owner='InstanceAgent',
                details={'path': spec.local_path, 'cause': str(err)})
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _extract_archive(self, spec, temp_dir):
        actual_digest = self._sha256_file(spec.source_path)
        if actual_digest != spec.digest_hex:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0003',
                'runtime artifact digest mismatch',
                details={'sourcePath': spec.source_path,
                         'expectedDigest': spec.digest,
                         'actualDigest': 'sha256:%s' % actual_digest})

        try:
            archive = tarfile.open(spec.source_path, 'r:*')
        except (tarfile.TarError, IOError) as err:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0004',
                'runtime artifact archive is unreadable',
                details={'sourcePath': spec.source_path, 'cause': str(err)})

        try:
            members = archive.getmembers()
            normalized_names = self._prevalidate_members(members)
            for member, relative_name in zip(members, normalized_names):
                self._extract_member(archive, member, temp_dir, relative_name)
        finally:
            archive.close()

    def _prevalidate_members(self, members):
        normalized_names = []
        seen = set()
        prefixes = set()
        for member in members:
            relative_name = self._normalize_member_name(member.name)
            normalized_names.append(relative_name)
            if relative_name:
                if relative_name in seen:
                    raise RuntimeArtifactError(
                        400,
                        'BMR-ARTIFACT-0004',
                        'runtime artifact archive contains duplicate members',
                        details={'member': member.name})
                seen.add(relative_name)
                parts = relative_name.split('/')
                current = []
                for part in parts[:-1]:
                    current.append(part)
                    prefix = '/'.join(current)
                    if prefix in seen:
                        raise RuntimeArtifactError(
                            400,
                            'BMR-ARTIFACT-0004',
                            'runtime artifact archive member collides with an existing path',
                            details={'member': member.name})
                if member.isdir():
                    prefixes.add(relative_name)
                elif relative_name in prefixes:
                    raise RuntimeArtifactError(
                        400,
                        'BMR-ARTIFACT-0004',
                        'runtime artifact archive member collides with an existing path',
                        details={'member': member.name})

            if member.issym() or member.islnk():
                raise RuntimeArtifactError(
                    400,
                    'BMR-ARTIFACT-0004',
                    'runtime artifact archive links are not allowed',
                    details={'member': member.name})
            if member.ischr() or member.isblk() or member.isfifo():
                raise RuntimeArtifactError(
                    400,
                    'BMR-ARTIFACT-0004',
                    'runtime artifact archive special files are not allowed',
                    details={'member': member.name})
            if not member.isdir() and not member.isreg():
                raise RuntimeArtifactError(
                    400,
                    'BMR-ARTIFACT-0004',
                    'runtime artifact archive member type is not supported',
                    details={'member': member.name, 'type': member.type})
            if member.mode & (stat.S_ISUID | stat.S_ISGID):
                raise RuntimeArtifactError(
                    400,
                    'BMR-ARTIFACT-0004',
                    'runtime artifact archive setuid/setgid bits are not allowed',
                    details={'member': member.name})
            if member.uid not in (0, None) or member.gid not in (0, None):
                raise RuntimeArtifactError(
                    400,
                    'BMR-ARTIFACT-0004',
                    'runtime artifact archive ownership metadata is not allowed',
                    details={'member': member.name,
                             'uid': member.uid,
                             'gid': member.gid})
            if member.uname not in ('', None, 'root') or member.gname not in ('', None, 'root'):
                raise RuntimeArtifactError(
                    400,
                    'BMR-ARTIFACT-0004',
                    'runtime artifact archive owner names are not allowed',
                    details={'member': member.name,
                             'uname': member.uname,
                             'gname': member.gname})
        return normalized_names

    def _extract_member(self, archive, member, temp_dir, relative_name):
        if not relative_name:
            return

        destination = os.path.join(temp_dir, relative_name)
        parent = os.path.dirname(destination)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)

        if member.isdir():
            if not os.path.isdir(destination):
                os.makedirs(destination)
            return

        if os.path.exists(destination):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0004',
                'runtime artifact archive member collides with an existing path',
                details={'member': member.name})

        source_file = archive.extractfile(member)
        if source_file is None:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0004',
                'runtime artifact archive member cannot be read',
                details={'member': member.name})

        try:
            with open(destination, 'wb') as output:
                shutil.copyfileobj(source_file, output)
        finally:
            source_file.close()

    def _write_marker(self, marker_path, digest):
        with open(marker_path, 'wb') as stream:
            stream.write((digest + '\n').encode('utf-8'))

    def _validate_cache_entry(self, local_path, digest):
        if not os.path.exists(local_path):
            return None
        if os.path.islink(local_path) or not os.path.isdir(local_path):
            raise RuntimeArtifactError(
                409,
                'BMR-ARTIFACT-0005',
                'runtime artifact cache entry is not a directory',
                details={'localPath': local_path})

        marker_path = os.path.join(local_path, self.DIGEST_MARKER)
        if os.path.islink(marker_path) or not os.path.isfile(marker_path):
            raise RuntimeArtifactError(
                409,
                'BMR-ARTIFACT-0005',
                'runtime artifact cache entry is missing its digest marker',
                details={'localPath': local_path})

        with open(marker_path, 'rb') as stream:
            marker = stream.read()
        if not isinstance(marker, str):
            marker = marker.decode('utf-8')
        if marker.strip() != digest:
            raise RuntimeArtifactError(
                409,
                'BMR-ARTIFACT-0005',
                'runtime artifact cache entry digest marker mismatch',
                details={'localPath': local_path,
                         'expectedDigest': digest,
                         'actualDigest': marker.strip()})
        return local_path

    def _resolve_source_mount(self, model_center_uuid, mount_facts):
        if not isinstance(mount_facts, dict):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0002',
                'runtime mount facts are missing')

        matches = []
        for mount in mount_facts.get('juicefsReadOnlyMounts') or []:
            if not isinstance(mount, dict):
                continue
            if not mount.get('readOnly'):
                continue
            if self._mount_matches_model_center(mount, model_center_uuid):
                matches.append(mount)

        if not matches:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0002',
                'runtime artifact source model center is not mounted read-only',
                details={'modelCenterUuid': model_center_uuid})
        if len(matches) != 1:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0002',
                'runtime artifact source model center mount is ambiguous',
                details={'modelCenterUuid': model_center_uuid,
                         'mountPoints': [mount.get('mountPoint') for mount in matches]})

        mount_point = matches[0].get('mountPoint')
        if not isinstance(mount_point, string_types) or not mount_point:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0002',
                'runtime artifact source mount is missing its mount point',
                details={'modelCenterUuid': model_center_uuid})
        if os.path.islink(mount_point) or not os.path.isdir(mount_point):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0002',
                'runtime artifact source mount is not available',
                details={'modelCenterUuid': model_center_uuid,
                         'mountPoint': mount_point})
        return matches[0]

    @staticmethod
    def _mount_matches_model_center(mount, model_center_uuid):
        additive_uuid = mount.get('modelCenterUuid')
        if additive_uuid:
            try:
                return (str(uuid.UUID(additive_uuid)).lower() ==
                        model_center_uuid)
            except (ValueError, TypeError, AttributeError):
                return False

        for key in ('mountPoint', 'root', 'mountSource'):
            value = mount.get(key)
            if not isinstance(value, string_types):
                continue
            for segment in value.split('/'):
                if not segment:
                    continue
                try:
                    if str(uuid.UUID(segment)).lower() == model_center_uuid:
                        return True
                except (ValueError, TypeError, AttributeError):
                    continue
        return False

    @staticmethod
    def _normalize_uuid(value, field_name):
        if not isinstance(value, string_types):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                '%s must be a uuid string' % field_name)
        try:
            return str(uuid.UUID(value)).lower()
        except (ValueError, AttributeError):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                '%s must be a uuid string' % field_name,
                details={field_name: value})

    def _validate_source_path(self, source_path):
        if os.path.islink(source_path) or not os.path.isfile(source_path):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0002',
                'runtime artifact source blob is unavailable',
                details={'sourcePath': source_path})

    def _build_cache_path(self, digest_hex):
        return os.path.join(self.artifact_root, 'sha256-%s' % digest_hex)

    def _lock_path(self, digest_hex):
        return os.path.join(
            self.artifact_root,
            self.LOCK_DIRNAME,
            'sha256-%s.lock' % digest_hex)

    @staticmethod
    def _normalize_digest(value):
        if not isinstance(value, string_types):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.digest must be a sha256 digest string')
        if not value.startswith('sha256:'):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.digest must use sha256',
                details={'digest': value})
        digest_hex = value.split(':', 1)[1]
        if len(digest_hex) != 64:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.digest must contain 64 hex characters',
                details={'digest': value})
        if digest_hex != digest_hex.lower():
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.digest must contain only lowercase hex',
                details={'digest': value})
        try:
            int(digest_hex, 16)
        except ValueError:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0001',
                'runtimeArtifact.digest must contain only lowercase hex',
                details={'digest': value})
        return digest_hex

    @staticmethod
    def _normalize_member_name(name):
        if not isinstance(name, string_types):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0004',
                'runtime artifact archive member name is invalid',
                details={'member': name})
        if '\x00' in name:
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0004',
                'runtime artifact archive member name contains NUL',
                details={'member': name})

        normalized = name.replace('\\', '/')
        if normalized.startswith('/'):
            raise RuntimeArtifactError(
                400,
                'BMR-ARTIFACT-0004',
                'runtime artifact archive member escapes its root',
                details={'member': name})
        while normalized.startswith('./'):
            normalized = normalized[2:]
        normalized = normalized.strip('/')
        if not normalized:
            return ''

        segments = normalized.split('/')
        for segment in segments:
            if segment in ('', '.', '..'):
                raise RuntimeArtifactError(
                    400,
                    'BMR-ARTIFACT-0004',
                    'runtime artifact archive member escapes its root',
                    details={'member': name})
        return '/'.join(segments)

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with open(path, 'rb') as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _ensure_directory(self, path, mode):
        if not os.path.isdir(path):
            os.makedirs(path)
        self._apply_permissions(path, is_dir=True, mode=mode)

    def _finalize_tree_permissions(self, root):
        for current_root, dir_names, file_names in os.walk(root):
            for dir_name in dir_names:
                self._apply_permissions(
                    os.path.join(current_root, dir_name),
                    is_dir=True)
            for file_name in file_names:
                path = os.path.join(current_root, file_name)
                executable = bool(os.stat(path).st_mode & 0o111)
                self._apply_permissions(
                    path,
                    is_dir=False,
                    executable=executable)
        self._apply_permissions(root, is_dir=True)

    def _apply_permissions(self, path, is_dir, executable=False, mode=None):
        self._apply_ownership(path)
        if mode is None:
            if is_dir:
                mode = 0o555
            elif executable:
                mode = 0o555
            else:
                mode = 0o444
        os.chmod(path, mode)

    def _apply_ownership(self, path):
        if self.owner_uid is None and self.owner_gid is None:
            return
        uid = self.owner_uid if self.owner_uid is not None else -1
        gid = self.owner_gid if self.owner_gid is not None else -1
        os.chown(path, uid, gid)

    class _ExclusiveLock(object):

        def __init__(self, path):
            self.path = path
            self.fd = None

        def __enter__(self):
            self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(self.fd, fcntl.LOCK_EX)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            finally:
                os.close(self.fd)

    def _exclusive_lock(self, path):
        return self._ExclusiveLock(path)


__all__ = [
    'RuntimeArtifactError',
    'RuntimeArtifactMaterializer',
    'RuntimeArtifactSpec',
]

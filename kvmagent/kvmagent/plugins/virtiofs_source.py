# Copyright (c) 2025, ZStack, Inc.

import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time

logger = logging.getLogger(__name__)


try:
    basestring
except NameError:
    basestring = str
try:
    long
except NameError:
    long = int


HOST_SOURCE_ROOT = '/var/lib/zstack/aios/virtiofs-sources'
VM_VIEW_ROOT = '/var/lib/zstack/aios/vm-views'
SOURCE_REGISTRY_FILE = os.path.join(HOST_SOURCE_ROOT, '.registry')
MODEL_CENTER_PROVIDER_ROOT = '/var/lib/zstack/aios/provider-mounts/model-centers'
MODEL_CENTER_LOCK_ROOT = '/var/lib/zstack/aios/provider-locks/model-centers'
JUICEFS_CACHE_DIR = '/var/cache/virtiofs/juicefs'
JUICEFS_CANDIDATE_PATHS = (
    '/usr/local/bin/juicefs',
    '/usr/bin/juicefs',
    '/opt/zstack/bin/juicefs',
)
# Local alignment sidecar: strong "v:<shared>" or weak "meta:<size>:<mtime>" from JuiceFS.
CONTENT_VERSION_SIDECAR = '.aios-content-version'
CONTENT_VERSION_STRONG_PREFIX = 'v:'
CONTENT_VERSION_META_PREFIX = 'meta:'


def _ensure_directory(path):
    try:
        os.makedirs(path, 0o755)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(path):
            raise


def get_attr(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        if hasattr(obj, 'hasattr') and obj.hasattr(name):
            return getattr(obj, name)
    except Exception:
        pass
    return getattr(obj, name, default)


def has_attr(obj, name):
    if obj is None:
        return False
    if isinstance(obj, dict):
        return name in obj
    try:
        if hasattr(obj, 'hasattr') and obj.hasattr(name):
            return True
    except Exception:
        pass
    return hasattr(obj, name)


def as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _normalize_root(root):
    root = str(root or '').strip()
    if not root:
        return None
    if not os.path.isabs(root):
        raise Exception('virtiofs source root[%s] must be an absolute path' % root)
    return os.path.realpath(root)


def _append_root(roots, root):
    root = _normalize_root(root)
    if root and root not in roots:
        roots.append(root)


def _split_roots(value):
    roots = []
    for item in as_list(value):
        if item is None:
            continue
        if isinstance(item, basestring):
            parts = item.split(',')
        else:
            parts = [item]
        for part in parts:
            _append_root(roots, part)
    return roots


def source_roots_from_raw(raw, include_vm_view=True):
    roots = []
    for field in ('allowedRoots', 'allowedSourceRoots'):
        for root in _split_roots(get_attr(raw, field)):
            _append_root(roots, root)
    has_explicit_source_root = False
    for field in ('hostSourceRoot', 'sourceRootPath'):
        if not has_attr(raw, field):
            continue
        has_explicit_source_root = True
        root = get_attr(raw, field)
        if root is None or str(root).strip() == '':
            raise Exception('virtiofs %s must not be empty' % field)
        _append_root(roots, root)
    if not has_explicit_source_root:
        _append_root(roots, HOST_SOURCE_ROOT)
    if include_vm_view and not has_explicit_source_root:
        _append_root(roots, VM_VIEW_ROOT)
    return tuple(roots)


def has_source_root_fields(raw):
    for field in ('allowedRoots', 'allowedSourceRoots', 'hostSourceRoot', 'sourceRootPath'):
        if get_attr(raw, field) is not None:
            return True
    return False


def _parse_required_capacity(value):
    if value is None or value == '':
        return None
    try:
        required = int(value)
    except Exception:
        raise Exception('requiredCapacityBytes[%s] must be a number' % value)
    if required < 0:
        raise Exception('requiredCapacityBytes[%s] must not be negative' % value)
    return required


def check_available_capacity(path, required_capacity_bytes):
    if required_capacity_bytes is None or required_capacity_bytes == 0:
        return
    try:
        stat = os.statvfs(path)
        available = stat.f_bavail * stat.f_frsize
    except OSError as exc:
        raise Exception('failed to check virtiofs source capacity for path[%s]: %s' % (path, exc))
    if available < required_capacity_bytes:
        raise Exception('virtiofs source path[%s] available capacity[%s bytes] is less than required capacity[%s bytes]. '
                        'Please move the virtiofs source root to a disk with enough capacity or free host storage space.' % (
                            path, available, required_capacity_bytes))


def statvfs_capacity(path):
    try:
        stat = os.statvfs(path)
    except OSError as exc:
        raise Exception('failed to check virtiofs source root capacity for path[%s]: %s' % (path, exc))
    return {
        'physicalTotalBytes': int(stat.f_blocks * stat.f_frsize),
        'physicalAvailableBytes': int(stat.f_bavail * stat.f_frsize),
    }


def directory_size(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for name in files:
            fpath = os.path.join(root, name)
            try:
                total += os.path.getsize(fpath)
            except OSError:
                pass
    return int(total)


def format_strong_content_version(content_version):
    value = str(content_version or '').strip()
    if not value:
        return None
    if value.startswith(CONTENT_VERSION_STRONG_PREFIX) or value.startswith(CONTENT_VERSION_META_PREFIX):
        return value
    return CONTENT_VERSION_STRONG_PREFIX + value


def format_meta_content_version(size_bytes, source_mtime):
    return '%s%s:%s' % (CONTENT_VERSION_META_PREFIX, int(size_bytes), int(source_mtime))


def read_local_content_version(path):
    sidecar = os.path.join(path, CONTENT_VERSION_SIDECAR)
    if not os.path.isfile(sidecar):
        return None
    try:
        with open(sidecar, 'r') as fd:
            value = fd.read().strip()
        return value or None
    except (IOError, OSError):
        return None


def write_local_content_version(path, content_version):
    value = str(content_version or '').strip()
    if not value:
        return
    sidecar = os.path.join(path, CONTENT_VERSION_SIDECAR)
    tmp = '%s.tmp.%s' % (sidecar, os.getpid())
    try:
        with open(tmp, 'w') as fd:
            fd.write(value)
        os.rename(tmp, sidecar)
    except (IOError, OSError):
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except (IOError, OSError):
            pass
        raise


def is_local_content_aligned(path, expected_version):
    expected = str(expected_version or '').strip()
    if not expected:
        return False
    local = read_local_content_version(path)
    return bool(local) and local == expected


def remote_directory_meta(path):
    if not os.path.exists(path):
        raise Exception('remoteSourcePath[%s] does not exist' % path)
    if not os.path.isdir(path):
        raise Exception('remoteSourcePath[%s] is not a directory' % path)
    return format_meta_content_version(directory_size(path), int(os.path.getmtime(path)))


def cache_entry(source_root, source_path, content_version=None,
                prepare_decision=None, prepare_reason=None, prepare_actions=None):
    root = _normalize_root(source_root)
    path = ensure_under(source_path, root, 'sourcePath', allow_root=False)
    if not os.path.exists(path):
        raise Exception('sourcePath[%s] does not exist' % source_path)
    if not os.path.isdir(path):
        raise Exception('sourcePath[%s] is not a directory' % source_path)
    version = content_version if content_version is not None else read_local_content_version(path)
    entry = {
        'sourcePath': path,
        'sizeBytes': directory_size(path),
        'sourceMtime': int(os.path.getmtime(path)),
        'checksum': None,
        'contentVersion': version,
    }
    if prepare_decision is not None:
        entry['prepareDecision'] = prepare_decision
    if prepare_reason is not None:
        entry['prepareReason'] = prepare_reason
    if prepare_actions is not None:
        entry['prepareActions'] = prepare_actions
    return entry


def _prepare_actions(mounted, copied):
    return 'mount=%s,copy=%s' % (1 if mounted else 0, 1 if copied else 0)


def _log_prepare_decision(decision, reason, expected, local_version, path, model_center_uuid,
                          storage_subdir, actions, entry, elapsed_ms):
    logger.info(
        '[host-model-cache-prepare] decision=%s reason=%s expected=%s local=%s '
        'path=%s mc=%s subdir=%s actions=%s elapsedMs=%s sizeBytes=%s contentVersion=%s' % (
            decision,
            reason,
            expected or 'none',
            local_version or 'none',
            path,
            model_center_uuid,
            storage_subdir,
            actions,
            int(elapsed_ms),
            entry.get('sizeBytes'),
            entry.get('contentVersion') or 'none',
        ))


def _ensure_report_source_root(root):
    if os.path.exists(root):
        if not os.path.isdir(root):
            raise Exception('sourceRoot[%s] is not a directory' % root)
        return root

    if root == _normalize_root(HOST_SOURCE_ROOT):
        _ensure_directory(root)
        return root

    parent = os.path.dirname(root)
    if not parent or not os.path.exists(parent):
        raise Exception('sourceRoot[%s] does not exist' % root)
    if not os.path.isdir(parent):
        raise Exception('sourceRoot[%s] parent[%s] is not a directory' % (root, parent))

    # Reporting is a read-only operation for primary-storage roots.  Capacity
    # belongs to the mounted parent and can be initialized before the cache
    # leaf is created by the first prepare operation.
    return parent


def report_source_root(source_root):
    root = _normalize_root(source_root or HOST_SOURCE_ROOT)
    capacity_root = _ensure_report_source_root(root)

    result = statvfs_capacity(capacity_root)
    result['sourceRoot'] = root
    result['cacheEntries'] = []

    if not os.path.isdir(root):
        return result

    registry = SourceRegistry(os.path.join(root, '.registry')).load()
    for entry in registry.values():
        path = entry.get('path') if isinstance(entry, dict) else None
        if not path:
            continue
        try:
            result['cacheEntries'].append(cache_entry(root, path))
        except Exception:
            pass
    return result


def prepare_host_model_cache(source_root, source_path, required_capacity_bytes=None):
    root = _normalize_root(source_root or HOST_SOURCE_ROOT)
    if not os.path.exists(root):
        raise Exception('sourceRoot[%s] does not exist' % root)
    check_available_capacity(root, required_capacity_bytes)
    return cache_entry(root, source_path)


def _validate_source_id(value, field_name):
    value = str(value or '').strip()
    if not value or not re.match(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$', value):
        raise Exception('invalid %s[%s]' % (field_name, value))
    return value


def _validate_relative_path(value, field_name):
    value = str(value or '').strip()
    if not value or os.path.isabs(value):
        raise Exception('%s[%s] must be a non-empty relative path' % (field_name, value))
    normalized = os.path.normpath(value)
    if normalized == '..' or normalized.startswith('..' + os.sep):
        raise Exception('%s[%s] escapes its source root' % (field_name, value))
    return normalized


def _find_juicefs_binary():
    for path in JUICEFS_CANDIDATE_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise Exception('juicefs binary not found')


def _run_process(args, error_message):
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise Exception('%s, exitCode[%s]' % (error_message, process.returncode))
    return stdout, stderr


def _mount_model_center(storage_url, mount_path, storage_subdir='models'):
    if os.path.ismount(mount_path):
        _unmount_model_center(mount_path)
    if not os.path.exists(mount_path):
        _ensure_directory(mount_path)
    if not os.path.exists(JUICEFS_CACHE_DIR):
        _ensure_directory(JUICEFS_CACHE_DIR)
    juicefs = _find_juicefs_binary()
    _run_process([
        juicefs, 'mount',
        '--read-only', '-d', '--subdir', storage_subdir,
        '--cache-dir', JUICEFS_CACHE_DIR,
        storage_url, mount_path,
    ], 'failed to mount model center')
    for _ in range(20):
        if os.path.ismount(mount_path):
            return
        time.sleep(0.5)
    raise Exception('model center mount did not become ready')


def _unmount_model_center(mount_path):
    if not os.path.ismount(mount_path):
        return
    juicefs = _find_juicefs_binary()
    _run_process([juicefs, 'umount', '--force', mount_path], 'failed to unmount model center')
    if os.path.ismount(mount_path):
        raise Exception('model center mount is still active after unmount')


def prepare_model_center_cache(source_root, source_path, model_center_uuid, storage_url,
                               artifact_relative_path, required_capacity_bytes=None,
                               storage_subdir='models', register_cache=True,
                               content_version=None):
    """Prepare host-local cache from JuiceFS model center.

    Deploy always calls prepare. Local dir existence alone is not a hit:
    - strong contentVersion (v:...) matching local sidecar skips remount
    - otherwise mount JuiceFS and compare weak meta (size+mtime); refresh on mismatch
    """
    started = time.time()
    root = _normalize_root(source_root or HOST_SOURCE_ROOT)
    target = ensure_under(source_path, root, 'sourcePath', allow_root=False)
    model_center_uuid = _validate_source_id(model_center_uuid, 'modelCenterUuid')
    if not storage_url or not str(storage_url).strip():
        raise Exception('storageUrl is required')
    storage_subdir = _validate_relative_path(storage_subdir, 'storageSubdir')
    relative_path = _validate_relative_path(artifact_relative_path, 'artifactRelativePath')
    expected_strong = format_strong_content_version(content_version)
    had_local = os.path.exists(target)
    local_before = read_local_content_version(target) if had_local else None

    if not os.path.exists(root):
        _ensure_directory(root)

    if not os.path.exists(MODEL_CENTER_PROVIDER_ROOT):
        _ensure_directory(MODEL_CENTER_PROVIDER_ROOT)
    if not os.path.exists(MODEL_CENTER_LOCK_ROOT):
        _ensure_directory(MODEL_CENTER_LOCK_ROOT)

    mount_path = os.path.join(MODEL_CENTER_PROVIDER_ROOT, model_center_uuid)
    lock_path = os.path.join(MODEL_CENTER_LOCK_ROOT, model_center_uuid + '.lock')
    lock_fd = open(lock_path, 'a+')
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        if os.path.ismount(mount_path):
            _unmount_model_center(mount_path)

        # Strong-version hit: local sidecar already matches shared truth → skip mount.
        if had_local and expected_strong and is_local_content_aligned(target, expected_strong):
            actions = _prepare_actions(False, False)
            entry = cache_entry(
                root, target, expected_strong,
                'strong_hit', 'strong_match', actions)
            if register_cache:
                _register_model_center_cache(root, target)
            _log_prepare_decision(
                'strong_hit', 'strong_match', expected_strong, local_before,
                target, model_center_uuid, storage_subdir, actions, entry,
                (time.time() - started) * 1000)
            return entry

        aligned_version = None
        decision = None
        reason = None
        copied = False
        try:
            _mount_model_center(str(storage_url).strip(), mount_path, storage_subdir)
            remote_source = ensure_under(
                os.path.join(mount_path, relative_path),
                mount_path,
                'modelRelativePath',
                allow_root=False)
            expected_version = expected_strong or remote_directory_meta(remote_source)

            if os.path.exists(target) and is_local_content_aligned(target, expected_version):
                aligned_version = expected_version
                if expected_strong:
                    decision, reason = 'strong_hit', 'strong_match'
                else:
                    decision, reason = 'meta_hit', 'meta_match'
            else:
                # Never rmtree first: keep usable cache until new copy is ready.
                # Rename old aside → copy into target → drop backup; on failure restore.
                _refresh_model_center_cache_from_remote(
                    target, root, remote_source, mount_path,
                    required_capacity_bytes, expected_version)
                aligned_version = expected_version
                copied = True
                if not had_local:
                    decision, reason = 'cold_copy', 'missing_local'
                elif not local_before:
                    decision, reason = 'refresh', 'no_sidecar'
                elif expected_strong:
                    decision, reason = 'refresh', 'strong_mismatch'
                else:
                    decision, reason = 'refresh', 'meta_mismatch'
        finally:
            _unmount_model_center(mount_path)

        actions = _prepare_actions(True, copied)
        entry = cache_entry(
            root, target, aligned_version,
            decision, reason, actions)
        if register_cache:
            _register_model_center_cache(root, target)
        _log_prepare_decision(
            decision, reason, expected_strong or aligned_version, local_before,
            target, model_center_uuid, storage_subdir, actions, entry,
            (time.time() - started) * 1000)
        return entry
    finally:
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        finally:
            lock_fd.close()


def _refresh_model_center_cache_from_remote(target, root, remote_source, mount_path,
                                           required_capacity_bytes, expected_version):
    """Copy remote into target without dropping usable local cache until success.

    If target exists, rename it to a sibling backup first. On any failure, restore
    the backup so in-use hosts keep a readable path. Backup and new copy coexist
    briefly, so free space must cover one extra full artifact until cleanup.
    """
    backup = None
    if os.path.exists(target):
        if not os.path.isdir(target):
            raise Exception('sourcePath[%s] exists but is not a directory' % target)
        backup = '%s.old.%s.%s' % (target, os.getpid(), int(time.time() * 1000))
        if os.path.exists(backup):
            shutil.rmtree(backup, ignore_errors=True)
        os.rename(target, backup)

    try:
        check_available_capacity(root, required_capacity_bytes)
        prepare_copy_source(
            target,
            (root,),
            remote_source,
            (mount_path,),
            required_capacity_bytes)
        write_local_content_version(target, expected_version)
    except Exception:
        if os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)
        if backup and os.path.exists(backup) and not os.path.exists(target):
            try:
                os.rename(backup, target)
                backup = None
            except (IOError, OSError) as restore_err:
                logger.warning(
                    '[host-model-cache-prepare] failed to restore backup[%s] to target[%s]: %s' % (
                        backup, target, restore_err))
        raise
    if backup and os.path.exists(backup):
        shutil.rmtree(backup, ignore_errors=True)


def cleanup_host_model_cache(source_root, source_path):
    root = _normalize_root(source_root or HOST_SOURCE_ROOT)
    path = ensure_under(source_path, root, 'sourcePath', allow_root=False)
    bytes_reclaimed = 0
    if os.path.exists(path):
        if not os.path.isdir(path):
            raise Exception('sourcePath[%s] is not a directory' % source_path)
        bytes_reclaimed = directory_size(path)
        shutil.rmtree(path)
    # Always drop matching registry entries so "dir gone but Ready remains" cannot persist.
    _unregister_model_center_cache(root, path)
    return {
        'sourcePath': path,
        'bytesReclaimed': bytes_reclaimed,
    }


def _safe_id(value, prefix):
    value = str(value or '').strip()
    value = re.sub(r'[^A-Za-z0-9_.-]', '_', value).strip('._-')
    if value:
        return value[:96]
    return prefix


def _path_id(path):
    digest = hashlib.sha1(os.path.realpath(path).encode('utf-8')).hexdigest()
    return 'source-%s' % digest[:16]


def ensure_under(path, root, field_name, allow_root=True):
    real_root = os.path.realpath(root)
    real_path = os.path.realpath(path)
    if real_path == real_root:
        if allow_root:
            return real_path
        raise Exception('%s[%s] resolves to shared root[%s], not a concrete virtiofs source' % (
            field_name, path, real_root))
    if not real_path.startswith(real_root + os.sep):
        raise Exception('%s[%s] resolves to path[%s] outside allowed virtiofs source directory or VM view directory[%s]' % (
            field_name, path, real_path, root))
    return real_path


def ensure_under_any(path, roots, field_name, allow_root=True):
    root_error = None
    for root in roots:
        try:
            return ensure_under(path, root, field_name, allow_root)
        except Exception as exc:
            if 'not a concrete virtiofs source' in str(exc):
                root_error = exc
            pass
    if root_error:
        raise root_error
    raise Exception('%s[%s] is outside allowed virtiofs source directory or VM view directory[%s]' % (
        field_name, path, ','.join([os.path.realpath(root) for root in roots])))


class SourceCapability(object):
    def __init__(self, migratable=False, snapshotable=False, persistent=True, shared_across_hosts=False):
        self.migratable = migratable
        self.snapshotable = snapshotable
        self.persistent = persistent
        self.sharedAcrossHosts = shared_across_hosts

    def to_dict(self):
        return {
            'migratable': self.migratable,
            'snapshotable': self.snapshotable,
            'persistent': self.persistent,
            'sharedAcrossHosts': self.sharedAcrossHosts,
        }


class SourceSpec(object):
    def __init__(self, source_type='preparedPath', path=None, source_uuid=None,
                 allowed_roots=None, required_capacity_bytes=None,
                 remote_source_path=None, remote_allowed_roots=None):
        self.source_type = source_type or 'preparedPath'
        self.path = path
        self.source_uuid = source_uuid
        self.allowed_roots = allowed_roots
        self.required_capacity_bytes = required_capacity_bytes
        self.remote_source_path = remote_source_path
        self.remote_allowed_roots = remote_allowed_roots

    @staticmethod
    def from_raw(raw):
        if isinstance(raw, SourceSpec):
            return raw
        source_type = get_attr(raw, 'type', get_attr(raw, 'sourceType', 'preparedPath'))
        path = (get_attr(raw, 'path') or get_attr(raw, 'sourcePath') or
                get_attr(raw, 'preparedPath'))
        source_uuid = get_attr(raw, 'sourceUuid', get_attr(raw, 'uuid'))
        required_capacity = _parse_required_capacity(
            get_attr(raw, 'requiredCapacityBytes', get_attr(raw, 'requiredBytes')))
        remote_source_path = get_attr(raw, 'remoteSourcePath')
        remote_allowed_roots = source_roots_from_raw({
            'sourceRootPath': get_attr(raw, 'remoteSourceRootPath')
        }, include_vm_view=False) if get_attr(raw, 'remoteSourceRootPath') else None
        allowed_roots = source_roots_from_raw(raw) if has_source_root_fields(raw) else None
        return SourceSpec(source_type, path, source_uuid, allowed_roots, required_capacity,
                          remote_source_path, remote_allowed_roots)

    @staticmethod
    def from_command(cmd):
        source_spec = get_attr(cmd, 'sourceSpec')
        if source_spec:
            return SourceSpec.from_raw(source_spec)
        return SourceSpec(
            get_attr(cmd, 'sourceType', 'preparedPath'),
            get_attr(cmd, 'sourcePath'),
            get_attr(cmd, 'sourceUuid'),
            source_roots_from_raw(cmd) if has_source_root_fields(cmd) else None,
            _parse_required_capacity(get_attr(cmd, 'requiredCapacityBytes', get_attr(cmd, 'requiredBytes'))),
            get_attr(cmd, 'remoteSourcePath'),
            source_roots_from_raw({
                'sourceRootPath': get_attr(cmd, 'remoteSourceRootPath')
            }, include_vm_view=False) if get_attr(cmd, 'remoteSourceRootPath') else None,
        )


class HostSource(object):
    def __init__(self, source_uuid, source_type, path, capability):
        self.sourceUuid = source_uuid
        self.sourceType = source_type
        self.path = path
        self.capability = capability

    def to_registry_entry(self):
        return {
            'sourceUuid': self.sourceUuid,
            'sourceType': self.sourceType,
            'path': self.path,
            'capability': self.capability.to_dict(),
            'state': 'ready',
        }


class PreparedPathSourceProvider(object):
    source_types = ('preparedPath', 'local')
    allowed_roots = (HOST_SOURCE_ROOT, VM_VIEW_ROOT)

    def can_handle(self, spec):
        return spec.source_type in self.source_types

    def prepare(self, spec):
        if not spec.path:
            raise Exception('sourcePath is required')
        allowed_roots = spec.allowed_roots or self.allowed_roots
        if spec.remote_source_path:
            prepare_copy_source(spec.path, allowed_roots, spec.remote_source_path,
                                spec.remote_allowed_roots or self.allowed_roots,
                                spec.required_capacity_bytes)
        if not os.path.exists(spec.path):
            raise Exception('sourcePath[%s] does not exist' % spec.path)
        if not os.path.isdir(spec.path):
            raise Exception('sourcePath[%s] is not a directory' % spec.path)

        path = ensure_under_any(spec.path, allowed_roots, 'sourcePath', allow_root=False)
        check_available_capacity(path, spec.required_capacity_bytes)
        source_uuid = _safe_id(spec.source_uuid, None) if spec.source_uuid else _path_id(path)
        capability = SourceCapability(
            migratable=False,
            snapshotable=False,
            persistent=True,
            shared_across_hosts=False,
        )
        return HostSource(source_uuid, spec.source_type, path, capability)


def prepare_copy_source(target_path, target_roots, remote_source_path, remote_roots, required_capacity_bytes=None):
    target = ensure_under_any(target_path, target_roots, 'sourcePath', allow_root=False)
    if os.path.exists(target):
        if not os.path.isdir(target):
            raise Exception('sourcePath[%s] exists but is not a directory' % target_path)
        return target

    remote = ensure_under_any(remote_source_path, remote_roots, 'remoteSourcePath', allow_root=False)
    if not os.path.exists(remote):
        raise Exception('remoteSourcePath[%s] does not exist' % remote_source_path)
    if not os.path.isdir(remote):
        raise Exception('remoteSourcePath[%s] is not a directory' % remote_source_path)

    parent = os.path.dirname(target)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, 0o755)
    check_available_capacity(parent, required_capacity_bytes)

    tmp = '%s.tmp.%s.%s' % (target, os.getpid(), int(time.time() * 1000))
    if os.path.exists(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        shutil.copytree(remote, tmp, symlinks=True)
        try:
            os.rename(tmp, target)
        except OSError:
            if os.path.exists(target) and os.path.isdir(target):
                shutil.rmtree(tmp, ignore_errors=True)
                return target
            raise
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return target


class SourceRegistry(object):
    def __init__(self, path=SOURCE_REGISTRY_FILE):
        self.path = path

    def load(self):
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, 'r') as fd:
                data = json.load(fd)
            return data if isinstance(data, dict) else {}
        except (IOError, ValueError):
            return {}

    def save_host_source(self, host_source):
        parent = os.path.dirname(self.path)
        try:
            if parent and not os.path.exists(parent):
                os.makedirs(parent)
            data = self.load()
            data[host_source.sourceUuid] = host_source.to_registry_entry()
            return self._write(data)
        except (IOError, OSError):
            return False

    def remove_by_path(self, source_path):
        """Remove registry entries whose path matches source_path. Keep the file if other entries remain."""
        try:
            real_path = os.path.realpath(source_path)
            data = self.load()
            if not data:
                return True
            remaining = {}
            removed = False
            for key, entry in data.items():
                entry_path = None
                if isinstance(entry, dict):
                    entry_path = entry.get('path')
                if entry_path and os.path.realpath(entry_path) == real_path:
                    removed = True
                    continue
                remaining[key] = entry
            if not removed:
                return True
            return self._write(remaining)
        except (IOError, OSError):
            return False

    def _write(self, data):
        parent = os.path.dirname(self.path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)
        tmp_path = self.path + '.tmp'
        with open(tmp_path, 'w') as fd:
            json.dump(data, fd, indent=2)
        os.rename(tmp_path, self.path)
        return True


def _register_model_center_cache(source_root, source_path):
    source = HostSource(
        _path_id(source_path),
        'juicefsModelCenter',
        source_path,
        SourceCapability(
            migratable=False,
            snapshotable=False,
            persistent=True,
            shared_across_hosts=False,
        ))
    registry = SourceRegistry(os.path.join(source_root, '.registry'))
    lock_fd = open(registry.path + '.lock', 'a+')
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        if not registry.save_host_source(source):
            raise Exception('failed to register prepared model center cache[%s]' % source_path)
    finally:
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        finally:
            lock_fd.close()


def _unregister_model_center_cache(source_root, source_path):
    registry = SourceRegistry(os.path.join(source_root, '.registry'))
    lock_fd = open(registry.path + '.lock', 'a+')
    try:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        if not registry.remove_by_path(source_path):
            raise Exception('failed to unregister model center cache[%s]' % source_path)
    finally:
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        finally:
            lock_fd.close()


class SourceManager(object):
    def __init__(self, providers=None, registry=None):
        self.providers = providers or [PreparedPathSourceProvider()]
        self.registry = registry or SourceRegistry()

    def ensure_ready(self, raw_spec):
        spec = SourceSpec.from_raw(raw_spec)
        for provider in self.providers:
            if provider.can_handle(spec):
                host_source = provider.prepare(spec)
                self.registry.save_host_source(host_source)
                return host_source
        raise Exception('unsupported virtiofs source type[%s]' % spec.source_type)


def ensure_ready(raw_spec):
    return SourceManager().ensure_ready(raw_spec)

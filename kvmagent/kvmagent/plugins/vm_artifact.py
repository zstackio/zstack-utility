import os
import re
import shutil

try:
    from shlex import quote as shell_quote
except ImportError:
    from pipes import quote as shell_quote

import libvirt

from kvmagent.plugins import virtiofs_device
from kvmagent.plugins import virtiofs_source
from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

HOST_SOURCE_ROOT = virtiofs_source.HOST_SOURCE_ROOT
VM_VIEW_ROOT = virtiofs_source.VM_VIEW_ROOT

DEFAULT_VIRTIOFS_CACHE = virtiofs_device.DEFAULT_CACHE_MODE
DEFAULT_VIRTIOFS_QUEUE = virtiofs_device.DEFAULT_QUEUE
DEFAULT_VIRTIOFS_BINARY = virtiofs_device.DEFAULT_BINARY

ADDON_VM_ARTIFACT_VIEWS = 'vmArtifactViews'
BIND_REUSED_EXISTING = 'reused_existing'
BIND_MOUNTED_NEW = 'mounted_new'
BIND_REBOUND_STALE = 'rebound_stale'


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


def get_addon(addons, name, default=None):
    if addons is None:
        return default
    if isinstance(addons, dict):
        return addons.get(name, default)
    try:
        if addons.hasattr(name):
            return getattr(addons, name)
    except Exception:
        pass
    return default


def as_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def source_roots_from_view(view):
    for field in ('allowedRoots', 'allowedSourceRoots', 'hostSourceRoot', 'sourceRootPath'):
        if get_attr(view, field) is not None:
            return virtiofs_source.source_roots_from_raw(view)
    return None


def remote_source_roots_from_view(view):
    remote_root = get_attr(view, 'remoteSourceRootPath')
    if remote_root is None:
        return None
    return virtiofs_source.source_roots_from_raw({'sourceRootPath': remote_root}, include_vm_view=False)


def safe_uuid(value, field_name):
    if not value or not re.match(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$', value):
        raise Exception('invalid %s: %s' % (field_name, value))
    return value


def sanitize_tag(value):
    return virtiofs_device.sanitize_tag(value)


def ensure_under(path, root, field_name):
    real_root = os.path.realpath(root)
    real_path = os.path.realpath(path)
    if real_path != real_root and not real_path.startswith(real_root + os.sep):
        raise Exception('%s[%s] is outside allowed root[%s]' % (field_name, path, root))
    return real_path


def safe_join(root, *paths):
    for p in paths:
        if p is None:
            continue
        if os.path.isabs(str(p)):
            raise Exception('absolute path component is not allowed: %s' % p)

    joined = os.path.join(root, *[str(p) for p in paths if p is not None and str(p) != ''])
    return ensure_under(joined, root, 'path')


def validate_relative_path(path, field_name):
    if path is None or str(path).strip() == '':
        raise Exception('%s cannot be empty' % field_name)
    path = str(path).strip()
    if os.path.isabs(path) or path == '..' or path.startswith('../') or '/../' in path or path.endswith('/..'):
        raise Exception('%s[%s] escapes its root' % (field_name, path))
    return path


def vm_view_root(vm_uuid):
    return safe_join(VM_VIEW_ROOT, safe_uuid(vm_uuid, 'vmInstanceUuid'))


def artifact_source_path(artifact):
    source_path = get_attr(artifact, 'sourcePath')
    if source_path:
        return ensure_under(source_path, HOST_SOURCE_ROOT, 'sourcePath')

    source_root = get_attr(artifact, 'sourceRootPath')
    if not source_root:
        raise Exception('sourcePath or sourceRootPath is required')
    source_root = ensure_under(source_root, HOST_SOURCE_ROOT, 'sourceRootPath')
    install_path = validate_relative_path(get_attr(artifact, 'installPath'), 'installPath')
    return safe_join(source_root, install_path)


def artifact_relative_path(artifact):
    relative_path = get_attr(artifact, 'relativePath')
    if relative_path:
        return validate_relative_path(relative_path, 'relativePath')

    artifact_uuid = get_attr(artifact, 'artifactUuid') or get_attr(artifact, 'uuid') or get_attr(artifact, 'name')
    return sanitize_tag(artifact_uuid)


def make_view_bind_specs(vm_uuid, artifacts):
    root = vm_view_root(vm_uuid)
    specs = []
    for artifact in as_list(artifacts):
        source = artifact_source_path(artifact)
        relative = artifact_relative_path(artifact)
        target = safe_join(root, relative)
        read_only = get_attr(artifact, 'readOnly', True)
        specs.append({
            'sourcePath': source,
            'targetPath': target,
            'relativePath': relative,
            'readOnly': read_only is not False,
            'artifactUuid': get_attr(artifact, 'artifactUuid') or get_attr(artifact, 'uuid'),
            'name': get_attr(artifact, 'name'),
        })
    return root, specs


class VmArtifactViewSpec(object):
    def __init__(self, vm_uuid, tag=None, artifacts=None, source_path=None,
                 cache=None, queue=None, binary_path=None, read_only=True,
                 source_roots=None, required_capacity_bytes=None, remote_source_path=None,
                 remote_source_roots=None):
        self.vm_uuid = safe_uuid(vm_uuid, 'vmInstanceUuid')
        self.tag = sanitize_tag(tag or self.vm_uuid)
        self.artifacts = as_list(artifacts)
        self.source_path = source_path
        self.cache = virtiofs_device.normalize_cache_mode(cache or DEFAULT_VIRTIOFS_CACHE)
        self.queue = virtiofs_device.normalize_queue(queue or DEFAULT_VIRTIOFS_QUEUE)
        self.binary_path = binary_path or DEFAULT_VIRTIOFS_BINARY
        self.read_only = read_only is not False
        self.source_roots = source_roots
        self.required_capacity_bytes = required_capacity_bytes
        self.remote_source_path = remote_source_path
        self.remote_source_roots = remote_source_roots

        if self.artifacts and self.source_path:
            raise Exception('vmArtifactView cannot specify both artifacts and sourcePath')

    @staticmethod
    def from_raw(view):
        vm_uuid = get_attr(view, 'vmInstanceUuid')
        tag = (get_attr(view, 'tag') or get_attr(view, 'mountTag') or
               get_attr(view, 'artifactUuid') or vm_uuid)
        source_path = get_attr(view, 'sourcePath') or get_attr(view, 'viewPath')
        return VmArtifactViewSpec(
            vm_uuid=vm_uuid,
            tag=tag,
            artifacts=get_attr(view, 'artifacts'),
            source_path=source_path,
            cache=get_attr(view, 'cache', DEFAULT_VIRTIOFS_CACHE),
            queue=get_attr(view, 'queue', DEFAULT_VIRTIOFS_QUEUE),
            binary_path=get_attr(view, 'binaryPath', DEFAULT_VIRTIOFS_BINARY),
            read_only=get_attr(view, 'readOnly', True),
            source_roots=source_roots_from_view(view),
            required_capacity_bytes=virtiofs_source._parse_required_capacity(
                get_attr(view, 'requiredCapacityBytes', get_attr(view, 'requiredBytes'))),
            remote_source_path=get_attr(view, 'remoteSourcePath'),
            remote_source_roots=remote_source_roots_from_view(view),
        )

    def resolve_source_path(self):
        if self.artifacts:
            source_path, _ = sync_artifact_view(self.vm_uuid, self.artifacts)
            return source_path
        if self.source_path:
            if self.remote_source_path:
                virtiofs_source.prepare_copy_source(
                    self.source_path,
                    self.source_roots or (HOST_SOURCE_ROOT,),
                    self.remote_source_path,
                    self.remote_source_roots or (HOST_SOURCE_ROOT,),
                    self.required_capacity_bytes)
            try:
                source_path = virtiofs_source.ensure_under_any(
                    self.source_path, self.source_roots or (HOST_SOURCE_ROOT,), 'sourcePath', allow_root=False)
                virtiofs_source.check_available_capacity(source_path, self.required_capacity_bytes)
                return source_path
            except Exception as exc:
                if 'available capacity' in str(exc) or 'failed to check virtiofs source capacity' in str(exc):
                    raise
                return virtiofs_source_path(self.vm_uuid, self.source_path)
        return virtiofs_source_path(self.vm_uuid, self.source_path)

    def to_virtiofs_spec(self):
        # libvirt rejects read-only virtiofs before 11.0.0 ("virtiofs does not
        # yet support read-only mode"), so never emit <readonly/> here; the
        # view contents are already bound read-only on the host by
        # sync_artifact_view/bind_readonly.
        return virtiofs_device.VirtiofsDeviceSpec(
            self.tag,
            self.resolve_source_path(),
            self.cache,
            self.queue,
            self.binary_path,
            False,
            True,
            True,
        )


def normalize_vm_artifact_views(views):
    normalized = []
    for view in as_list(views):
        if isinstance(view, VmArtifactViewSpec):
            normalized.append(view)
        else:
            normalized.append(VmArtifactViewSpec.from_raw(view))
    return normalized


def parse_vm_artifact_views(addons):
    views = get_addon(addons, ADDON_VM_ARTIFACT_VIEWS)
    if not views:
        return []
    return normalize_vm_artifact_views(views)


def _mkdir_for_bind_target(source_path, target_path):
    parent = os.path.dirname(target_path)
    linux.mkdir(parent, 0o755)
    if not os.path.isdir(parent):
        os.makedirs(parent, 0o755)
    if os.path.isfile(source_path):
        if os.path.isdir(target_path) and not os.path.islink(target_path):
            remove_path(target_path)
        if not os.path.exists(target_path):
            with open(target_path, 'a'):
                pass
    else:
        if os.path.exists(target_path) and not os.path.isdir(target_path):
            remove_path(target_path)
        linux.mkdir(target_path, 0o755)
        if not os.path.isdir(target_path):
            os.makedirs(target_path, 0o755)


def bind_readonly(source_path, target_path, read_only=True):
    ensure_under(source_path, HOST_SOURCE_ROOT, 'sourcePath')
    ensure_under(target_path, VM_VIEW_ROOT, 'targetPath')
    if not os.path.exists(source_path):
        raise Exception('sourcePath[%s] does not exist' % source_path)

    status = BIND_REUSED_EXISTING
    real_source = os.path.realpath(source_path)
    if linux.is_mounted(path=target_path):
        current_source = mounted_source(target_path)
        if current_source != real_source:
            if not unmount_if_needed(target_path):
                raise Exception('failed to unmount stale bind target %s' % target_path)
            status = BIND_REBOUND_STALE

    if not linux.is_mounted(path=target_path):
        _mkdir_for_bind_target(source_path, target_path)
        ret = bash.bash_r('mount --bind %s %s' % (shell_quote(source_path), shell_quote(target_path)))
        if ret != 0:
            if unmount_if_needed(target_path):
                remove_path(target_path)
            raise Exception('failed to bind mount %s to %s' % (source_path, target_path))
        if status != BIND_REBOUND_STALE:
            status = BIND_MOUNTED_NEW

    mode = 'ro' if read_only else 'rw'
    ret = bash.bash_r('mount -o remount,bind,%s %s' % (mode, shell_quote(target_path)))
    if ret != 0:
        if status != BIND_REUSED_EXISTING and unmount_if_needed(target_path):
            remove_path(target_path)
        raise Exception('failed to remount %s as %s bind' % (target_path, mode))
    return status


def _mountinfo_target(line):
    parts = line.split(' - ', 1)[0].split()
    return parts[4] if len(parts) > 4 else None


def _decode_mountinfo_path(path):
    if path is None:
        return None
    return path.replace('\\040', ' ').replace('\\011', '\t').replace('\\012', '\n').replace('\\134', '\\')


def _mountinfo_root(line):
    parts = line.split(' - ', 1)[0].split()
    return _decode_mountinfo_path(parts[3]) if len(parts) > 3 else None


def list_mounts_under(root):
    root = os.path.realpath(root)
    mounts = []
    try:
        with open('/proc/self/mountinfo') as fd:
            for line in fd:
                target = _decode_mountinfo_path(_mountinfo_target(line))
                real_target = os.path.realpath(target) if target else None
                if real_target and (real_target == root or real_target.startswith(root + os.sep)):
                    mounts.append(target)
    except IOError:
        return []
    mounts.sort(key=lambda p: len(p), reverse=True)
    return mounts


def mounted_source(path):
    real_path = os.path.realpath(path)
    try:
        with open('/proc/self/mountinfo') as fd:
            for line in fd:
                target = _decode_mountinfo_path(_mountinfo_target(line))
                if target and os.path.realpath(target) == real_path:
                    source = _mountinfo_root(line)
                    return os.path.realpath(source) if source else None
    except IOError:
        return None
    return None


def unmount_if_needed(path):
    if linux.is_mounted(path=path):
        if not linux.umount(path, is_exception=False):
            return False
        if linux.is_mounted(path=path):
            return False
    return True


def _intersects_path(path, candidates):
    real_path = os.path.realpath(path)
    for candidate in candidates:
        candidate = os.path.realpath(candidate)
        if (candidate == real_path or
                candidate.startswith(real_path + os.sep) or
                real_path.startswith(candidate + os.sep)):
            return True
    return False


def _paths_under_deepest_first(root):
    paths = []
    for current, dirs, files in os.walk(root, topdown=False):
        for name in files:
            paths.append(os.path.join(current, name))
        for name in dirs:
            paths.append(os.path.join(current, name))
    paths.sort(key=lambda p: len(os.path.realpath(p)), reverse=True)
    return paths


def remove_path(path):
    ensure_under(path, VM_VIEW_ROOT, 'path')
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except OSError:
            pass


def cleanup_view(vm_uuid, keep_paths=None):
    root = vm_view_root(vm_uuid)
    keep = set([os.path.realpath(p) for p in (keep_paths or [])])
    def should_keep(path):
        real_path = os.path.realpath(path)
        if real_path in keep:
            return True
        for keep_path in keep:
            if keep_path.startswith(real_path + os.sep):
                return True
        return False

    if not os.path.exists(root):
        linux.mkdir(root, 0o755)
        return root

    failed_unmounts = []
    for mount in list_mounts_under(root):
        if not should_keep(mount):
            if not unmount_if_needed(mount):
                failed_unmounts.append(os.path.realpath(mount))

    for path in _paths_under_deepest_first(root):
        if not should_keep(path) and not _intersects_path(path, failed_unmounts):
            remove_path(path)
    return root


def sync_artifact_view(vm_uuid, artifacts):
    root, specs = make_view_bind_specs(vm_uuid, artifacts)
    linux.mkdir(root, 0o755)
    keep_paths = []
    rollback_paths = []
    try:
        for spec in specs:
            status = bind_readonly(spec['sourcePath'], spec['targetPath'], spec['readOnly'])
            keep_paths.append(spec['targetPath'])
            if status != BIND_REUSED_EXISTING:
                rollback_paths.append(spec['targetPath'])
    except Exception:
        for target_path in reversed(rollback_paths):
            if unmount_if_needed(target_path):
                remove_path(target_path)
        raise
    cleanup_view(vm_uuid, keep_paths)
    return root, specs


def virtiofs_source_path(vm_uuid, source_path=None):
    root = vm_view_root(vm_uuid)
    if source_path:
        return ensure_under(source_path, root, 'sourcePath')
    return root


def build_virtiofs_device_xml(vm_uuid, tag, source_path=None, cache=None, queue=None, binary_path=None, readonly=True):
    source_path = virtiofs_source_path(vm_uuid, source_path)
    return virtiofs_device.build_virtiofs_xml(
        tag, source_path, cache, queue, binary_path, readonly, True, True)


def add_virtiofs_devices(devices, views, element_factory):
    for view in normalize_vm_artifact_views(views):
        virtiofs_device.add_filesystem_element(devices, view.to_virtiofs_spec(), element_factory)


def attach_virtiofs(domain, vm_uuid, tag, source_path=None, cache=None, queue=None):
    xml = build_virtiofs_device_xml(vm_uuid, tag, source_path, cache, queue)
    domain.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
    return xml


def detach_virtiofs(domain, domain_xmlobject, tag):
    tag = sanitize_tag(tag)
    for fs in domain_xmlobject.devices.get_child_node_as_list('filesystem'):
        if get_attr(get_attr(fs, 'target'), 'dir_') == tag:
            domain.detachDeviceFlags(fs.dump(), libvirt.VIR_DOMAIN_AFFECT_LIVE)
            return True
    return False

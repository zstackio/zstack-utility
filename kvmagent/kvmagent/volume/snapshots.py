import os
from enum import Enum

from zstacklib.utils import jsonobject, linux


_snapshot_extensions = {}


class SnapshotMode(Enum):
    FULL = 'full'
    DELTA = 'delta'


def register_extension(name, snapshot_class):
    previous = _snapshot_extensions.get(name)
    if previous is not None and previous is not snapshot_class:
        raise ValueError('snapshot extension is already registered: %s' % name)
    _snapshot_extensions[name] = snapshot_class


def get_snapshot(cmd, source):
    if not _snapshot_extensions:
        raise RuntimeError('snapshot extensions are not configured')
    matches = [extension for extension in _snapshot_extensions.values() if extension.matches(cmd, source)]
    if len(matches) > 1:
        raise ValueError('multiple snapshot extensions match the volume')
    return (matches[0] if matches else PlainSnapshot)(cmd, source)


def command_for_job(cmd, job):
    result = jsonobject.JsonObject()
    vars(result).update(vars(job))
    # Host options belong to the batch; key material belongs exclusively to this job.
    for name in ('kvmHostAddons', 'virtualSize'):
        if getattr(result, name, None) is None:
            setattr(result, name, getattr(cmd, name, None))
    return result


def validate_target_path(source, target):
    if os.path.realpath(source) == os.path.realpath(target):
        raise ValueError('snapshot source and target paths must be different')


def take_offline_snapshot(cmd, source, snapshot, target, mode):
    validate_target_path(source, target)
    if mode is SnapshotMode.FULL:
        validate_target_path(source, snapshot)
        validate_target_path(snapshot, target)
    operation = get_snapshot(cmd, source)
    try:
        if mode is SnapshotMode.FULL:
            operation.create_full(source, snapshot)
        backing = snapshot if mode is SnapshotMode.FULL else source
        operation.create_delta(backing, target)
        return backing, target
    except Exception:
        operation.cleanup_offline()
        raise


class PlainSnapshot(object):
    def __init__(self, cmd, source):
        self.cmd = cmd
        self.source = source

    def create_full(self, source, target):
        return linux.create_template(source, target)

    def create_delta(self, source, target):
        return linux.qcow2_clone_with_cmd(source, target, self.cmd)

    def prepare_live(self, target, volume, source_kind):
        validate_target_path(self.source, target)

    def validate_live_source(self, domain_xml, disk_name, volume):
        pass

    def should_reuse_target(self, target):
        return os.path.exists(target)

    def cleanup_offline(self):
        pass

    def add_source_encryption(self, source_xml, volume):
        pass

    def verify_live(self, target, is_used):
        pass

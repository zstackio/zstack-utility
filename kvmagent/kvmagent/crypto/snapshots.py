import os
import sys
import json
import subprocess
from contextlib import ExitStack
from xml.etree import ElementTree as etree

from kvmagent.crypto import qemu_volume, secret
from kvmagent.crypto.http_error import log_failure
from kvmagent.crypto.file_volume import operations as file_operations
from kvmagent.crypto.shared_block import operations as block_operations
from kvmagent.volume.snapshots import SnapshotMode, validate_target_path
from zstacklib.utils import linux, lvm


def _image_info(path):
    return json.loads(subprocess.check_output([qemu_volume.QEMU_IMG, 'info', '-U', '--output=json', path]))


def _encrypted(info):
    encryption = info.get('format-specific', {}).get('data', {}).get('encrypt', {})
    return info.get('encrypted') is True or encryption.get('format') == 'luks'


def _encrypted_chain(path):
    seen = set()
    while path:
        if path in seen:
            raise ValueError('volume backing chain contains a cycle')
        seen.add(path)
        info = _image_info(path)
        if _encrypted(info):
            return True
        path = info.get('full-backing-filename') or info.get('backing-filename')
    return False


class LuksSnapshot(object):
    def __init__(self, cmd, source):
        self.cmd = cmd
        self.source = source
        self.created_paths = set()

    @staticmethod
    def matches(cmd, source):
        volume = getattr(cmd, 'volume', None)
        return bool(getattr(cmd, 'encryptedDek', None) or getattr(cmd, 'encrypted', False)
                    or getattr(volume, 'luksSecretUuid', None) or getattr(volume, 'encrypted', False)
                    or (os.path.isabs(source) and os.path.exists(source) and _encrypted_chain(source)))

    def _require_key(self):
        if not getattr(self.cmd, 'encryptedDek', None):
            raise ValueError('encryptedDek is required for offline or precreated encrypted snapshots')

    def _validate_source_state(self, source, volume=None):
        if not os.path.isabs(source):
            raise ValueError('encrypted snapshots require a file or block source')
        if not _encrypted(_image_info(source)):
            raise ValueError('encrypted snapshot requires an encrypted top layer')
        volume = volume or getattr(self.cmd, 'volume', None) or self.cmd
        if getattr(volume, 'encrypted', None) is False:
            raise ValueError('volume encryption state disagrees with its actual top layer')

    def _create(self, source, target, mode):
        validate_target_path(source, target)
        self._require_key()
        if not os.path.isabs(source):
            raise ValueError('encrypted snapshots require a file or block source')
        if target.startswith('/dev/'):
            # MN reserves these LVs; do not publish or remove them as ordinary files.
            with ExitStack() as stack:
                stack.enter_context(lvm.RecursiveOperateLv(source, shared=True))
                stack.enter_context(lvm.OperateLv(target, shared=False))
                self._validate_source_state(source)
                qemu_volume.verify_luks_open(source, lambda: secret.luks_secret_channel(self.cmd.encryptedDek))
                if _image_info(target)['format'] != 'raw':
                    raise FileExistsError(target)
                size = linux.qcow2_virtualsize(source)
                lvm.extend_lv(target, block_operations.allocation_size(self.cmd, size), skip_if_sufficient=True)
                if mode is SnapshotMode.FULL:
                    return block_operations.create_template(self.cmd, source, target)
                return block_operations.create_with_backing(self.cmd, source, target, size)
        self._validate_source_state(source)
        with qemu_volume.staged_file(target) as temporary:
            if mode is SnapshotMode.FULL:
                file_operations.create_template(self.cmd, source, temporary)
            else:
                file_operations.create_with_backing(self.cmd, source, temporary)
        self.created_paths.add(target)

    def create_full(self, source, target):
        return self._create(source, target, SnapshotMode.FULL)

    def create_delta(self, source, target):
        return self._create(source, target, SnapshotMode.DELTA)

    def validate_live_source(self, domain_xml, disk_name, volume):
        requested = getattr(volume, 'luksSecretUuid', None)
        if not requested:
            raise ValueError('luksSecretUuid is required for live encrypted snapshots')
        disks = etree.fromstring(domain_xml).findall('./devices/disk')
        disk = next((disk for disk in disks if disk.find('target').get('dev') == disk_name), None)
        secrets = set(secret.get('uuid') for secret in disk.findall('.//encryption/secret')) if disk is not None else set()
        if secrets != {requested}:
            raise ValueError('LUKS secret must match the current volume secret')
        self._validate_source_state(self.source, volume)

    def prepare_live(self, target, volume, source_kind):
        validate_target_path(self.source, target)
        if not getattr(volume, 'luksSecretUuid', None):
            raise ValueError('luksSecretUuid is required for live encrypted snapshots')
        if source_kind not in ('file', 'block'):
            raise ValueError('encrypted snapshot source type is unsupported')
        if os.path.exists(target):
            if source_kind != 'block' or _image_info(target)['format'] != 'raw':
                raise FileExistsError(target)
        # Libvirt creates the format in the reserved LV using its Host secret, without REUSE_EXT.

    def should_reuse_target(self, target):
        return False

    def cleanup_offline(self):
        business_error = sys.exc_info()[1]
        cleanup_error = None
        for path in list(self.created_paths):
            try:
                os.unlink(path)
            except FileNotFoundError:
                self.created_paths.remove(path)
            except OSError as error:
                if cleanup_error is None:
                    cleanup_error = error
            else:
                self.created_paths.remove(path)
        if cleanup_error is not None:
            log_failure('snapshot', 'cleanup_offline unresolved_paths=%r' % sorted(self.created_paths), cleanup_error)
            if business_error is None:
                raise cleanup_error

    def add_source_encryption(self, source_xml, volume):
        uuid = getattr(volume, 'luksSecretUuid', None)
        if not uuid:
            raise ValueError('luksSecretUuid is required for live encrypted snapshots')
        encryption = etree.SubElement(source_xml, 'encryption', format='luks')
        etree.SubElement(encryption, 'secret', type='passphrase', uuid=uuid)

    def verify_live(self, target, is_used):
        if not is_used(target):
            raise RuntimeError('live snapshot target is not the active volume')
        if not _encrypted(_image_info(target)):
            raise RuntimeError('live snapshot target is not LUKS encrypted')
        # QEMU has opened this layer using the existing Host secret; never export UUID-only material.

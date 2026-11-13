from kvmagent.crypto import secret
from zstacklib.utils import lvm
from kvmagent.crypto import qemu_volume
from kvmagent.crypto.conversion_rollback import conversion_rollback
from kvmagent.crypto.http_error import check_output, run_checked
from kvmagent.crypto.volume_request import EncryptionMode, should_use_luks_driver
import json
import os
import time
import uuid


LUKS_HEADER_OVERHEAD = 8 * 1024 * 1024


def validate_create_request(cmd):
    encrypted = should_use_luks_driver(cmd)
    if encrypted and getattr(cmd, 'volumeFormat', None) == 'raw':
        raise ValueError('encrypted SharedBlock volume requires qcow2 format')
    return encrypted


def allocation_size(cmd, size):
    return int(size) + (LUKS_HEADER_OVERHEAD if getattr(cmd, 'encryptedDek', None) else 0)


def _verify(cmd, path):
    if path:
        qemu_volume.verify_luks_open(path, lambda: secret.luks_secret_channel(cmd.encryptedDek))


def _with_secret(cmd, source, target, operation):
    _verify(cmd, source)
    with secret.luks_secret_channel(cmd.encryptedDek) as secret_file:
        operation(secret_file)
    _verify(cmd, target)
    return True


def _qcow2_options(options):
    return options[3:].strip() if options.startswith('-o ') else ''


def create_empty(cmd, target, size, backing=None, options=''):
    return _with_secret(cmd, backing, target,
                        lambda secret_file: qemu_volume.create_encrypted_qcow2_block(
                            target, size, secret_file, backing, _qcow2_options(options)))


def create_with_backing(cmd, backing, target, size, options=''):
    return create_empty(cmd, target, size, backing, options)


def _path(install_path):
    if not install_path or not install_path.startswith('sharedblock:/'):
        raise ValueError('SharedBlock install path is required')
    return install_path.replace('sharedblock:/', '/dev', 1)


def _delete_temporary_lv(path):
    if lvm.lv_exists(path):
        lvm.delete_lv(path)


def _replace_lv(temporary, target):
    result = lvm.lv_rename(temporary, target, overwrite=True)
    if result is not None:
        _check_lv_rename(result)


def _check_lv_rename(result):
    status, output, error = result
    if status != 0:
        raise RuntimeError('LV rename failed: %s' % (error or output))


def encrypt_in_place(cmd):
    source = _path(cmd.installPath)
    if not getattr(cmd, 'encryptedDek', None):
        raise ValueError('encryptedDek is required')
    if not lvm.lv_exists(source):
        raise FileNotFoundError(source)
    temporary = '/dev/%s/%s-encrypting-%s' % (
        cmd.vgUuid, os.path.basename(source), uuid.uuid4().hex[:8])
    with lvm.OperateLv(source, shared=False):
        info = json.loads(check_output([qemu_volume.QEMU_IMG, 'info', '--output=json', source]))
        if qemu_volume.is_luks_encrypted_image(source):
            raise ValueError('source is already LUKS encrypted')
        size = int(lvm.get_lv_size(source)) + LUKS_HEADER_OVERHEAD
        with conversion_rollback('sharedblock.encrypt_in_place') as (remove, _):
            lvm.create_lv_from_cmd(temporary, size, cmd,
                                   'zs::sharedblock::volume::%s::%s' % (cmd.hostUuid, time.time()))
            remove('delete_temporary', _delete_temporary_lv, temporary,
                   source=source, temporary=temporary)
            with lvm.OperateLv(temporary, shared=False):
                if info['format'] == 'qcow2':
                    qemu_volume.convert_qcow2_encryption_to_block(
                        source, temporary, target_mode=EncryptionMode.LUKS,
                        secret_file=lambda: secret.luks_secret_channel(cmd.encryptedDek))
                elif info['format'] == 'raw':
                    with secret.luks_secret_channel(cmd.encryptedDek) as secret_file:
                        run_checked([qemu_volume.QEMU_IMG, 'convert', '--object',
                                     'secret,id=luks_sec,format=raw,file=%s' % secret_file,
                                     '-f', 'raw', '-O', 'luks', '-o', 'key-secret=luks_sec',
                                     source, temporary])
                else:
                    raise ValueError('unsupported source format: %s' % info['format'])
                if not qemu_volume.is_luks_encrypted_image(temporary):
                    raise RuntimeError('encrypted target format verification failed')
                qemu_volume.verify_luks_open(
                    temporary, lambda: secret.luks_secret_channel(cmd.encryptedDek))
            _replace_lv(temporary, source)
    return True


def resize(cmd, target, size):
    return _with_secret(cmd, None, target,
                        lambda secret_file: qemu_volume.resize_with_secret(target, size, secret_file))

from kvmagent.crypto import secret
from zstacklib.utils import lvm
from kvmagent.crypto import qemu_volume
from kvmagent.crypto.conversion_rollback import conversion_rollback
from kvmagent.crypto.http_error import check_output, run_checked
from kvmagent.crypto.volume_request import EncryptionMode, should_use_luks_driver
from contextlib import ExitStack
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


def clone(cmd, source, target, size, options=''):
    return create_empty(cmd, target, size, source, options)


def create_with_backing(cmd, backing, target, size, options=''):
    return create_empty(cmd, target, size, backing, options)


def create_template(cmd, source, target):
    _verify(cmd, source)
    qemu_volume.convert_qcow2_encryption_to_block(
        source, target, target_mode=EncryptionMode.LUKS,
        secret_file=lambda: secret.luks_secret_channel(cmd.encryptedDek), policy=qemu_volume.ConversionPolicy.ALLOW_SAME_STATE)
    _verify(cmd, target)
    return True


def safe_rebase(cmd, backing, target):
    _verify(cmd, backing)
    qemu_volume.safe_rebase_with_secret(
        backing, target, lambda: secret.luks_secret_channel(cmd.encryptedDek))
    _verify(cmd, target)
    return True


def rebase(cmd, backing, target):
    return _with_secret(cmd, backing, target,
                        lambda secret_file: qemu_volume.rebase_no_check_with_secret(backing, target, secret_file))


def commit(cmd, top, base):
    return _with_secret(cmd, top, base,
                        lambda secret_file: qemu_volume.commit_with_secret(top, base, secret_file))


def _path(install_path):
    if not install_path or not install_path.startswith('sharedblock:/'):
        raise ValueError('SharedBlock install path is required')
    return install_path.replace('sharedblock:/', '/dev', 1)


def convert_items(cmd):
    target_mode = EncryptionMode.from_target_encrypted(cmd.targetEncrypted)
    if not getattr(cmd, 'encryptedDek', None):
        raise ValueError('encryptedDek is required')
    items = list(cmd.items)
    targets = [_path(item.targetInstallPath) for item in items]
    if len(set(targets)) != len(targets):
        raise ValueError('conversion targets must be unique')
    trash_paths = [_path(item.sourceTrashInstallPath) for item in items
                   if getattr(item, 'sourceTrashInstallPath', None)]
    if len(set(trash_paths)) != len(trash_paths) or set(trash_paths).intersection(targets):
        raise ValueError('conversion trash paths must be unique and distinct from targets')
    converted = []
    converted_targets = {}
    sizes = {}
    with conversion_rollback('sharedblock_convert') as (remove, restore):
        lvm.update_pv_allocate_strategy(cmd)
        for item, target in zip(items, targets):
            source = _path(item.sourceInstallPath)
            backing = _path(item.targetBackingInstallPath) if getattr(item, 'targetBackingInstallPath', None) else None
            effective_backing = converted_targets.get(backing, backing)
            trash = _path(item.sourceTrashInstallPath) if getattr(item, 'sourceTrashInstallPath', None) else None
            if not lvm.lv_exists(source):
                raise FileNotFoundError(source)
            if lvm.lv_exists(target) and not (trash and target == source):
                raise FileExistsError(target)
            if trash and lvm.lv_exists(trash):
                raise FileExistsError(trash)
            temporary = '%s_converted_%s' % (target, uuid.uuid4().hex[:8])
            with ExitStack() as stack:
                stack.enter_context(lvm.RecursiveOperateLv(source, shared=True))
                if effective_backing:
                    stack.enter_context(lvm.RecursiveOperateLv(effective_backing, shared=True))
                requested_size = int(lvm.get_lv_size(source)) + (LUKS_HEADER_OVERHEAD if target_mode is EncryptionMode.LUKS else 0)
                lvm.create_lv_from_absolute_path(temporary, requested_size, exact_size=True)
                remove('delete_temporary', _delete_temporary_lv, temporary,
                       source=source, trash=trash, target=target, temporary=temporary)
                converted.append((source, temporary, target, backing, effective_backing, trash))
                stack.enter_context(lvm.OperateLv(temporary, shared=False, delete_when_exception=True))
                qemu_volume.convert_qcow2_encryption_to_block(
                    source, temporary, target_mode,
                    lambda: secret.luks_secret_channel(cmd.encryptedDek), effective_backing)
                qemu_volume.verify_luks_open(temporary, lambda: secret.luks_secret_channel(cmd.encryptedDek))
            converted_targets[target] = temporary
            sizes[item.resourceUuid] = int(lvm.get_lv_size(temporary))
        for source, temporary, target, _, _, trash in converted:
            if trash:
                _rename_lv(source, trash)
                restore('restore_source', _restore_lv, trash, source,
                        source=source, trash=trash, target=target, temporary=temporary)
        for source, temporary, target, backing, effective_backing, trash in converted:
            if backing and backing != effective_backing:
                with lvm.RecursiveOperateLv(backing, shared=True):
                    with lvm.OperateLv(temporary, shared=False):
                        with secret.luks_secret_channel(cmd.encryptedDek) as channel:
                            qemu_volume.rebase_no_check_with_secret(backing, temporary, channel)
            _rename_lv(temporary, target)
            remove('delete_target', lvm.delete_lv, target,
                   source=source, trash=trash, target=target, temporary=temporary)
        total_capacity, available_capacity = lvm.get_vg_size(cmd.vgUuid)
    return sizes, total_capacity, available_capacity


def _delete_temporary_lv(path):
    if lvm.lv_exists(path):
        lvm.delete_lv(path)


def _restore_lv(trash, source):
    if not lvm.lv_exists(trash):
        raise FileNotFoundError(trash)
    if lvm.lv_exists(source):
        raise FileExistsError(source)
    _rename_lv(trash, source)


def _rename_lv(source, target):
    _check_lv_rename(lvm.lv_rename(source, target, overwrite=False))


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

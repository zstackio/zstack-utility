import os
import uuid

from kvmagent.crypto import secret
from kvmagent.crypto import qemu_volume
from kvmagent.crypto.conversion_rollback import conversion_rollback
from kvmagent.crypto.volume_request import EncryptionMode


def _with_secret(cmd, source, target, operation):
    if source:
        qemu_volume.verify_luks_open(source, lambda: secret.luks_secret_channel(cmd.encryptedDek))
    with secret.luks_secret_channel(cmd.encryptedDek) as secret_file:
        operation(secret_file)
    if target:
        qemu_volume.verify_luks_open(target, lambda: secret.luks_secret_channel(cmd.encryptedDek))
    return True


def _create_with_secret(cmd, source, target, operation):
    with qemu_volume.staged_file(target) as temporary:
        _with_secret(cmd, source, temporary, lambda secret_file: operation(temporary, secret_file))
    return True


def create_template(cmd, source, target):
    return _create_with_secret(cmd, source, target,
                               lambda path, secret_file: qemu_volume.create_encrypted_template(source, path, secret_file))


def clone(cmd, source, target, size=None):
    return _create_with_secret(cmd, source, target,
                               lambda path, secret_file: qemu_volume.clone_encrypted_qcow2(source, path, secret_file, size=size))


def rebase(cmd, backing, target):
    return _with_secret(cmd, backing, target,
                        lambda secret_file: qemu_volume.rebase_no_check_with_secret(backing, target, secret_file))


def safe_rebase(cmd, backing, target):
    qemu_volume.safe_rebase_with_secret(
        backing, target, lambda: secret.luks_secret_channel(cmd.encryptedDek))
    return True


def commit(cmd, top, base):
    return _with_secret(cmd, top, base,
                        lambda secret_file: qemu_volume.commit_with_secret(top, base, secret_file))


def resize(cmd, target, size):
    return _with_secret(cmd, target, target,
                        lambda secret_file: qemu_volume.resize_with_secret(target, size, secret_file))


def _create(cmd, backing, target, size):
    addons = getattr(cmd, 'kvmHostAddons', None)
    options = getattr(addons, 'qcow2Options', '') if addons else ''
    options = (options or '').strip()
    if options.startswith('-o '):
        options = options[3:]
    with qemu_volume.staged_file(target) as temporary:
        if backing:
            qemu_volume.verify_luks_open(backing, lambda: secret.luks_secret_channel(cmd.encryptedDek))
        with secret.luks_secret_channel(cmd.encryptedDek) as secret_file:
            if backing:
                options = ','.join(part for part in options.split(',') if not part.startswith('preallocation='))
                qemu_volume.clone_encrypted_qcow2(backing, temporary, secret_file, options, size)
            else:
                qemu_volume.create_encrypted_qcow2(temporary, size, secret_file, options)
        if not qemu_volume.is_luks_encrypted_image(temporary):
            raise RuntimeError('encrypted target format verification failed')
        qemu_volume.verify_luks_open(temporary, lambda: secret.luks_secret_channel(cmd.encryptedDek))
    return True


def create_empty(cmd):
    if cmd.volumeFormat != 'qcow2':
        raise ValueError('encrypted file volume requires qcow2 format')
    if int(cmd.size) <= 0:
        raise ValueError('encrypted file volume size must be positive')
    return _create(cmd, getattr(cmd, 'backingFile', None), cmd.installUrl, cmd.size)


def create_with_backing(cmd, backing, target):
    return _create(cmd, backing, target, getattr(cmd, 'virtualSize', None))


def convert_items(cmd):
    target_mode = EncryptionMode.from_target_encrypted(cmd.targetEncrypted)
    if not getattr(cmd, 'encryptedDek', None):
        raise ValueError('encryptedDek is required')
    items = list(cmd.items)
    targets = [item.targetInstallPath for item in items]
    if len(set(targets)) != len(targets):
        raise ValueError('conversion targets must be unique')
    trash_paths = [getattr(item, 'sourceTrashInstallPath', None) for item in items]
    trash_paths = [path for path in trash_paths if path]
    if len(set(trash_paths)) != len(trash_paths) or set(trash_paths).intersection(targets):
        raise ValueError('conversion trash paths must be unique and distinct from targets')
    for item in items:
        if not os.path.exists(item.sourceInstallPath):
            raise FileNotFoundError(item.sourceInstallPath)
        trash = getattr(item, 'sourceTrashInstallPath', None)
        if os.path.exists(item.targetInstallPath) and not (trash and item.targetInstallPath == item.sourceInstallPath):
            raise FileExistsError(item.targetInstallPath)
        if trash and os.path.exists(trash):
            raise FileExistsError(trash)

    converted = []
    converted_targets = {}
    sizes = {}
    with conversion_rollback('file_volume.convert_items') as (remove, restore):
        for item in items:
            backing = getattr(item, 'targetBackingInstallPath', None)
            effective_backing = converted_targets.get(backing, backing)
            if effective_backing and not os.path.exists(effective_backing):
                raise FileNotFoundError(effective_backing)
            temporary = '%s.converted.%s' % (item.targetInstallPath, uuid.uuid4().hex)
            remove('remove_temporary', _unlink_if_present, temporary,
                   target=item.targetInstallPath, temporary=temporary)
            converted.append((item, temporary, backing, effective_backing))
            qemu_volume.convert_qcow2_encryption(
                item.sourceInstallPath, temporary, target_mode,
                lambda: secret.luks_secret_channel(cmd.encryptedDek), effective_backing)
            converted_targets[item.targetInstallPath] = temporary
            if qemu_volume.is_luks_encrypted_image(temporary) != (target_mode is EncryptionMode.LUKS):
                raise RuntimeError('converted volume format does not match target encryption state')
            qemu_volume.verify_luks_open(
                temporary, lambda: secret.luks_secret_channel(cmd.encryptedDek))
            sizes[item.resourceUuid] = os.path.getsize(temporary)
        for item in items:
            trash = getattr(item, 'sourceTrashInstallPath', None)
            if trash:
                os.link(item.sourceInstallPath, trash)
                restore('restore_source', _restore_source, trash, item.sourceInstallPath,
                        source=item.sourceInstallPath, trash=trash, target=item.targetInstallPath)
                os.unlink(item.sourceInstallPath)
        for item, temporary, backing, effective_backing in converted:
            if backing and backing != effective_backing:
                with secret.luks_secret_channel(cmd.encryptedDek) as channel:
                    qemu_volume.rebase_no_check_with_secret(backing, temporary, channel)
            os.link(temporary, item.targetInstallPath)
            remove('remove_target', _unlink_if_present, item.targetInstallPath,
                   target=item.targetInstallPath)
    for _, temporary, _, _ in converted:
        qemu_volume.cleanup_temporary_file(temporary)
    return sizes


def _unlink_if_present(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _restore_source(trash, source):
    if not os.path.exists(trash):
        raise FileNotFoundError(trash)
    if os.path.lexists(source):
        if not os.path.samefile(source, trash):
            raise FileExistsError(source)
    else:
        os.link(trash, source)
    os.unlink(trash)


def encrypt_in_place(cmd):
    if not getattr(cmd, 'encryptedDek', None):
        raise ValueError('encryptedDek is required')
    qemu_volume.encrypt_plain_file_in_place(
        cmd.installPath, lambda: secret.luks_secret_channel(cmd.encryptedDek))
    return True

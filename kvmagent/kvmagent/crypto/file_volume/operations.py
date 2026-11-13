from kvmagent.crypto import secret
from kvmagent.crypto import qemu_volume


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


def encrypt_in_place(cmd):
    if not getattr(cmd, 'encryptedDek', None):
        raise ValueError('encryptedDek is required')
    qemu_volume.encrypt_plain_file_in_place(
        cmd.installPath, lambda: secret.luks_secret_channel(cmd.encryptedDek))
    return True

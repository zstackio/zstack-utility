import shlex
from contextlib import contextmanager

from kvmagent.crypto import imagestore, secret


def _get(obj, field, default=None):
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _backup_spec(spec):
    if not _get(spec, 'encrypted', False):
        return None
    wrapped = _get(spec, 'encryptedDek')
    if not wrapped:
        raise ValueError('encryptedDek is required for encrypted backup')
    return {field: _get(spec, field) for field in ('encrypted', 'encryptedDek', 'keyProviderUuid',
                                                  'keyVersion', 'cipher')}


def _pull_spec(spec):
    encrypted = _get(spec, 'encrypted')
    wrapped = _get(spec, 'encryptedDek')
    if not spec or (encrypted is False and not wrapped):
        return None
    if encrypted is not True:
        raise ValueError('encrypted must be true for encrypted ImageStore pull')
    if not wrapped:
        raise ValueError('encryptedDek is required for encrypted ImageStore pull')
    secret.decode_encrypted_dek(wrapped)
    provider = _get(spec, 'keyProviderUuid')
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError('keyProviderUuid is required for encrypted ImageStore pull')
    version = _get(spec, 'keyVersion')
    if type(version) is not int or version <= 0:
        raise ValueError('keyVersion must be a positive integer for encrypted ImageStore pull')
    if _get(spec, 'cipher') != 'luks':
        raise ValueError('cipher must be luks for encrypted ImageStore pull')
    return {field: _get(spec, field) for field in
            ('encrypted', 'encryptedDek', 'keyProviderUuid', 'keyVersion', 'cipher')}


def _backup_specs(addons):
    backup = _get(addons, 'VolumeBackupEncryption', {})
    return _get(backup, 'specs', ()) or ()


class ImageStoreEncryptionExtension(object):
    @staticmethod
    def prepare_image_add_command(command_line, addons, device_id):
        specs = _backup_specs(addons)
        if device_id is None:
            image = _get(addons, 'ImageStoreEncryption', {})
        else:
            # Parent uploads use the backup's disk, including device ID zero.
            image = next((spec for spec in specs
                          if _get(spec, 'deviceId') == device_id and _get(spec, 'encrypted')), None)

        wrapped = _get(image, 'encryptedDek')
        if not wrapped and _get(image, 'encrypted'):
            raise ValueError('encryptedDek is required for encrypted ImageStore add')
        if device_id is None and not wrapped and any(_get(spec, 'encrypted', False) for spec in specs):
            raise ValueError('unsupported encrypted ImageStore operation')

        content = {'encrypted': True, 'encryptedDek': wrapped} if wrapped else None
        return imagestore.with_encryption_json(command_line, content)

    @staticmethod
    def prepare_image_pull_command(command_line, addons):
        return imagestore.with_encryption_json(command_line, _pull_spec(_get(addons, 'ImageStoreEncryption', {})))

    @staticmethod
    def prepare_volume_backup_command(command_line, addons, device_id):
        disk_spec = next((spec for spec in _backup_specs(addons) if _get(spec, 'deviceId') == device_id), None)
        return imagestore.with_encryption_json(command_line, _backup_spec(disk_spec))

    @staticmethod
    @contextmanager
    def prepare_batch_backup_command(command_line, addons, backup_args, device_ids):
        specs = _backup_specs(addons)
        if not any(_get(spec, 'encrypted', False) for spec in specs):
            yield command_line
            return

        by_device = {_get(spec, 'deviceId'): spec for spec in specs}
        backups = []
        for device_id, arg in zip(device_ids or (), backup_args):
            item = dict(zip(('bitmap', 'mode', 'drive', 'speed'), arg))
            encryption = _backup_spec(by_device.get(device_id))
            if encryption:
                item['encryption'] = encryption
            backups.append(item)
        if len(backups) != len(backup_args):
            raise ValueError('backup device IDs do not match backup arguments')
        prefix, separator, _ = command_line.rpartition(' -args ')
        if not separator:
            raise ValueError('zstcli batch backup args are missing')
        with imagestore.temporary_json({'backups': backups}) as path:
            yield '%s -args-json-file %s -secret-channel-provider %s' % (
                prefix, shlex.quote(path), imagestore.KEY_AGENT_PROVIDER)

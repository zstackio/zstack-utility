import json
import os
import shlex
import tempfile
from contextlib import contextmanager
from enum import Enum

from kvmagent.crypto import secret


KEY_AGENT_PROVIDER = 'unix:///var/run/key-agent/key-agent.sock'


class CleanupPolicy(Enum):
    REQUIRED = 'required'
    BEST_EFFORT = 'best-effort'


def _get(obj, field, default=None):
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _spec(spec):
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


@contextmanager
def temporary_json(content, *, cleanup=CleanupPolicy.REQUIRED):
    descriptor, path = tempfile.mkstemp(prefix='zstcli-encryption-', suffix='.json')
    completed = False
    try:
        with os.fdopen(descriptor, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(content, stream)
        yield path
        completed = True
    finally:
        removed = secret.remove_sensitive_file(path, 'imagestore.temporary_json')
        if completed and cleanup is CleanupPolicy.REQUIRED and not removed:
            raise RuntimeError('failed to remove temporary ImageStore encryption metadata')


def backup_encryption_spec(addons, device_id):
    backup = _get(addons, 'VolumeBackupEncryption', {})
    for spec in _get(backup, 'specs', ()) or ():
        if _get(spec, 'deviceId') == device_id and _get(spec, 'encrypted'):
            return {field: _get(spec, field) for field in
                    ('encrypted', 'encryptedDek', 'keyProviderUuid', 'keyVersion', 'cipher')}
    return None


@contextmanager
def prepare_command(context, command):
    addons = _get(context, 'addons', {}) or {}
    image = _get(addons, 'ImageStoreEncryption', {}) or {}
    backup = _get(addons, 'VolumeBackupEncryption', {}) or {}
    specs = _get(backup, 'specs', ()) or ()
    kind = _get(context, 'kind')
    content = None
    if kind == 'pull':
        content = _pull_spec(image)
    elif kind == 'add' and (_get(image, 'encryptedDek') or _get(image, 'encrypted')):
        if not _get(image, 'encryptedDek'):
            raise ValueError('encryptedDek is required for encrypted ImageStore add')
        content = {'encrypted': True, 'encryptedDek': _get(image, 'encryptedDek')}
    elif kind == 'batch-backup' and any(_get(spec, 'encrypted', False) for spec in specs):
        by_device = {_get(spec, 'deviceId'): spec for spec in specs}
        args = _get(context, 'args', ())
        device_ids = _get(context, 'deviceIds', ())
        backups = []
        for device_id, arg in zip(device_ids, args):
            item = dict(zip(('bitmap', 'mode', 'drive', 'speed'), arg))
            encryption_spec = _spec(by_device.get(device_id))
            if encryption_spec:
                item['encryption'] = encryption_spec
            backups.append(item)
        if len(backups) != len(args):
            raise ValueError('backup device IDs do not match backup arguments')
        content = {'backups': backups}
    elif kind == 'single-backup':
        for spec in specs:
            if _get(spec, 'deviceId') == _get(context, 'deviceId'):
                content = _spec(spec)
                break
    elif _get(image, 'encryptedDek') or _get(image, 'encrypted') or any(_get(spec, 'encrypted', False) for spec in specs):
        raise ValueError('unsupported encrypted ImageStore operation')

    if content is None:
        yield command
        return

    with temporary_json(content, cleanup=CleanupPolicy.BEST_EFFORT) as path:
        quoted = shlex.quote(path)
        if kind == 'batch-backup':
            prefix, separator, _ = command.rpartition(' -args ')
            if not separator:
                raise ValueError('zstcli batch backup args are missing')
            command = '%s -args-json-file %s -secret-channel-provider %s' % (prefix, quoted, KEY_AGENT_PROVIDER)
        else:
            command += ' -encryption-json-file %s -secret-channel-provider %s' % (quoted, KEY_AGENT_PROVIDER)
        yield command

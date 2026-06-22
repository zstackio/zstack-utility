def get_luks_secret_uuid(volume, allow_legacy_secret=True):
    secret_uuid = getattr(volume, 'luksSecretUuid', None)
    if not secret_uuid and allow_legacy_secret and getattr(volume, 'deviceType', None) != 'ceph':
        secret_uuid = getattr(volume, 'secretUuid', None)
    return secret_uuid


def add_luks_encryption(element_factory, parent, volume, allow_legacy_secret=True):
    secret_uuid = get_luks_secret_uuid(volume, allow_legacy_secret)
    if secret_uuid:
        enc = element_factory(parent, 'encryption', None, {'format': 'luks'})
        element_factory(enc, 'secret', None, {'type': 'passphrase', 'uuid': secret_uuid})

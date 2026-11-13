from enum import Enum


class EncryptionMode(Enum):
    PLAIN = 'plain'
    LUKS = 'luks'

    @classmethod
    def from_target_encrypted(cls, value):
        if not isinstance(value, bool):
            raise ValueError('targetEncrypted must be a boolean')
        return cls.LUKS if value else cls.PLAIN


def should_use_luks_driver(cmd):
    # A source may need its DEK even when the requested target is plaintext.
    encrypted_dek = getattr(cmd, 'encryptedDek', None)
    encrypted = bool(getattr(cmd, 'encrypted', False) or getattr(cmd, 'targetEncrypted', False))
    if encrypted_dek is None and not encrypted:
        return False
    if not encrypted_dek:
        raise ValueError('encryptedDek is required')
    return True

from xml.etree import ElementTree as etree

from kvmagent.crypto.ceph import operations as ceph
from kvmagent.crypto.zbs import operations as zbs
from kvmagent.crypto.qemu_volume import is_luks_image_info, iter_image_chain


def _secret(parent, secret_uuid):
    encryption_element = etree.SubElement(parent, 'encryption', format='luks')
    etree.SubElement(encryption_element, 'secret', type='passphrase', uuid=secret_uuid)


def _file_chain(path):
    for path, info in iter_image_chain(path):
        yield path, info['format'], is_luks_image_info(info)


def apply_volume_encryption(disk, volume, source_kind):
    secret_uuid = getattr(volume, 'luksSecretUuid', None)
    if source_kind == 'vhost':
        if secret_uuid or getattr(volume, 'encrypted', False):
            raise ValueError('vhost does not support encrypted volumes')
        return disk

    if source_kind in ('file', 'block'):
        layers = list(_file_chain(volume.installPath))
        encrypted_layers = any(layer[2] for layer in layers)
        if encrypted_layers and not secret_uuid:
            raise ValueError('LUKS secret UUID is required for encrypted volume chain')
        if secret_uuid and not encrypted_layers:
            raise ValueError('LUKS secret UUID provided for unencrypted volume chain')
        if getattr(volume, 'encrypted', False) and not encrypted_layers:
            raise ValueError('volume is marked encrypted but its format is plaintext')
        if not encrypted_layers:
            return disk
        source = disk.find('source')
        if len(layers) == 1:
            _secret(source, secret_uuid)
            return disk
        # Attach the LUKS secret only to encrypted layers in a mixed backing chain.
        if layers[0][2]:
            _secret(source, secret_uuid)
        backing = disk
        source_attribute = 'file' if source_kind == 'file' else 'dev'
        for path, image_format, encrypted in layers[1:]:
            backing = etree.SubElement(backing, 'backingStore', type=source_kind)
            etree.SubElement(backing, 'format', type=image_format)
            backing_source = etree.SubElement(backing, 'source', **{source_attribute: path})
            if encrypted:
                _secret(backing_source, secret_uuid)
        etree.SubElement(backing, 'backingStore')
        return disk

    if source_kind in ('ceph', 'cbd'):
        if getattr(volume, 'encrypted', False) and not secret_uuid:
            raise ValueError('LUKS secret UUID is required for encrypted volume')
        if not secret_uuid:
            return disk
        if source_kind == 'ceph':
            ps_uuid = getattr(volume, 'primaryStorageUuid', None)
            if not ps_uuid:
                raise ValueError('primaryStorageUuid is required for encrypted Ceph volume')
            actual = ceph.is_encrypted(volume.installPath, ps_uuid)
        else:
            actual = zbs.is_encrypted(volume.installPath)
        if not actual:
            raise ValueError('LUKS secret UUID provided for unencrypted volume')
        _secret(disk.find('source'), secret_uuid)
        return disk
    if secret_uuid:
        raise ValueError('encrypted volume protocol is unsupported: %s' % source_kind)
    return disk

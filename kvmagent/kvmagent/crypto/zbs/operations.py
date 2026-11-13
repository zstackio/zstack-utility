import json
import os
import tempfile
import sys
from contextlib import contextmanager
from enum import Enum

from kvmagent.crypto import secret
from kvmagent.crypto.http_error import check_output, log_failure, run_checked
from kvmagent.crypto.qemu_volume import QEMU_IMG
from kvmagent.crypto.volume_request import EncryptionMode
from zstacklib.utils import lock, log


CBD_CONFIG = '/etc/zbs/client.conf'
LUKS_PAYLOAD_OFFSET = 8 * 1024 * 1024
CBD_RESIZE_ALIGNMENT = 1024 * 1024
logger = log.get_logger(__name__)


class PathRole(Enum):
    VOLUME = 'volume'
    SNAPSHOT_SOURCE = 'snapshot-source'


def _path(install_path, *, role=PathRole.VOLUME):
    if not install_path:
        raise ValueError('CBD install path is required')
    if install_path.startswith('cbd:'):
        path = install_path[4:]
    else:
        path = install_path
    volume_path, separator, seq_num = path.partition('@')
    parts = volume_path.split('/')
    if len(parts) != 3 or not all(parts) or ',' in volume_path or (
            separator and not (role is PathRole.SNAPSHOT_SOURCE and seq_num.isascii() and seq_num.isdecimal())):
        raise ValueError('encrypted ZBS operation requires a CBD volume path')
    return 'cbd:%s_zbs_:%s' % (path, CBD_CONFIG)


def _qemu_info(path, *options):
    return json.loads(check_output([QEMU_IMG, 'info', '--output=json', *options, path]))


def _raw_info(install_path):
    return _qemu_info(_path(install_path), '-f', 'raw')


def _info(install_path):
    return _qemu_info(_path(install_path))


def _encrypted(install_path):
    return _info(install_path)['format'] == 'luks'


def is_encrypted(install_path):
    return _encrypted(install_path)


def _luks_options(path):
    return 'driver=luks,key-secret=luks_sec,file.driver=cbd,file.filename=%s' % path


def _open_info(install_path, encrypted_dek):
    with secret.luks_secret_channel(encrypted_dek) as secret_file:
        return json.loads(check_output([
            QEMU_IMG, 'info', '--output=json', '--object',
            'secret,id=luks_sec,format=raw,file=%s' % secret_file,
            '--image-opts', _luks_options(_path(install_path))]))


def _verify(install_path, mode, encrypted_dek=None):
    return _verify_qemu_path(_path(install_path), mode, encrypted_dek)


def _verify_qemu_path(path, mode, encrypted_dek):
    encrypted = mode is EncryptionMode.LUKS
    if (_qemu_info(path)['format'] == 'luks') != encrypted:
        raise RuntimeError('CBD target encryption format verification failed')
    if encrypted:
        if not encrypted_dek:
            raise ValueError('encryptedDek is required')
        with secret.luks_secret_channel(encrypted_dek) as secret_file:
            check_output([QEMU_IMG, 'map', '--output=json', '--object',
                          'secret,id=luks_sec,format=raw,file=%s' % secret_file,
                          '--image-opts', _luks_options(path)])
    return int(_qemu_info(path, '-f', 'raw').get('actual-size') or 0)


@contextmanager
def _temporary_luks_image():
    temporary = tempfile.NamedTemporaryFile(prefix='zbs-luks-', suffix='.img', delete=False)
    try:
        temporary.close()
        yield temporary.name
    finally:
        failed = sys.exc_info()[0] is not None
        try:
            os.unlink(temporary.name)
        except OSError as error:
            log_failure('zbs._initialize', 'temporary_file_cleanup', error)
            if not failed:
                raise


def _initialize(install_path, size, encrypted_dek):
    if int(size) <= 0 or not encrypted_dek:
        raise ValueError('positive size and encryptedDek are required')
    with _temporary_luks_image() as temporary:
        os.truncate(temporary, int(size) + LUKS_PAYLOAD_OFFSET)
        with secret.luks_secret_channel(encrypted_dek) as secret_file:
            run_checked(['/usr/sbin/cryptsetup', '-q', 'luksFormat', '--type', 'luks1',
                         '--batch-mode', '--align-payload=%d' % (LUKS_PAYLOAD_OFFSET // 512),
                         '--key-file', secret_file, temporary])
        run_checked([QEMU_IMG, 'convert', '-n', '--target-is-zero', '-S', '4k',
                     '-m', '16', '-W', '-f', 'raw', temporary,
                     '-O', 'raw', _path(install_path)])
    return _verify(install_path, EncryptionMode.LUKS, encrypted_dek=encrypted_dek)


def _write_plain_to_luks(source_path, target, encrypted_dek):
    with secret.luks_secret_channel(encrypted_dek) as secret_file:
        run_checked([QEMU_IMG, 'convert', '-n', '--target-image-opts',
                     '--object', 'secret,id=luks_sec,format=raw,file=%s' % secret_file,
                     '-m', '16', '-W', '-f', 'raw', source_path, _luks_options(_path(target))])
    return _verify(target, EncryptionMode.LUKS, encrypted_dek=encrypted_dek)


def _copy_luks(source_path, target, encrypted_dek):
    _verify_qemu_path(source_path, EncryptionMode.LUKS, encrypted_dek=encrypted_dek)
    run_checked([QEMU_IMG, 'convert', '-n', '-m', '16', '-W', '-f', 'raw',
                 source_path, '-O', 'raw', _path(target)])
    return _verify(target, EncryptionMode.LUKS, encrypted_dek=encrypted_dek)


def _resize_raw(install_path, size):
    aligned = ((int(size) + CBD_RESIZE_ALIGNMENT - 1) // CBD_RESIZE_ALIGNMENT) * CBD_RESIZE_ALIGNMENT
    if int(_raw_info(install_path)['virtual-size']) < aligned:
        run_checked([QEMU_IMG, 'resize', '-f', 'raw', _path(install_path), str(aligned)])


def _resize_luks(install_path, size, encrypted_dek):
    requested = int(size)
    if requested <= 0 or not encrypted_dek:
        raise ValueError('positive virtualSize and encryptedDek are required')
    _verify(install_path, EncryptionMode.LUKS, encrypted_dek=encrypted_dek)
    current = int(_open_info(install_path, encrypted_dek)['virtual-size'])
    if current >= requested:
        return
    _resize_raw(install_path, int(_raw_info(install_path)['virtual-size']) + requested - current)
    current = int(_open_info(install_path, encrypted_dek)['virtual-size'])
    if current < requested:
        with secret.luks_secret_channel(encrypted_dek) as secret_file:
            run_checked([QEMU_IMG, 'resize', '--object',
                         'secret,id=luks_sec,format=raw,file=%s' % secret_file,
                         '--image-opts', _luks_options(_path(install_path)), str(requested)])
    _verify(install_path, EncryptionMode.LUKS, encrypted_dek=encrypted_dek)


def create_empty(cmd):
    path = _path(cmd.installPath)
    size = int(cmd.size)
    if size <= 0 or not cmd.encryptedDek:
        raise ValueError('positive size and encryptedDek are required')
    with lock.NamedLock('zbs-luks-create-' + path):
        image_format = _qemu_info(path)['format']
        if image_format == 'luks':
            if int(_open_info(cmd.installPath, cmd.encryptedDek)['virtual-size']) < size:
                raise RuntimeError('existing LUKS volume capacity is smaller than requested')
            return _verify(cmd.installPath, EncryptionMode.LUKS, encrypted_dek=cmd.encryptedDek)
        if image_format != 'raw':
            raise RuntimeError('unexpected format for a preallocated CBD volume')
        # MN allocates a fresh CBD volume for each create attempt.
        return _initialize(cmd.installPath, size, cmd.encryptedDek)


def clone(cmd):
    source_path, target = _path(cmd.srcPath, role=PathRole.SNAPSHOT_SOURCE), cmd.dstPath
    if source_path == _path(target):
        raise ValueError('source and target CBD paths must differ')
    if _qemu_info(source_path)['format'] == 'luks':
        _copy_luks(source_path, target, cmd.encryptedDek)
    else:
        size = int(getattr(cmd, 'virtualSizeForLuksClone', None) or _qemu_info(source_path, '-f', 'raw')['virtual-size'])
        _initialize(target, size, cmd.encryptedDek)
        _write_plain_to_luks(source_path, target, cmd.encryptedDek)
    if getattr(cmd, 'virtualSizeForLuksClone', None):
        _resize_luks(target, cmd.virtualSizeForLuksClone, cmd.encryptedDek)
    return _verify(target, EncryptionMode.LUKS, encrypted_dek=cmd.encryptedDek)


def encrypt_in_place(cmd):
    source, target = cmd.installPath, cmd.targetInstallPath
    if _path(source) == _path(target):
        raise ValueError('source and target CBD paths must differ')
    if _encrypted(source):
        raise ValueError('source is already LUKS encrypted')
    size = int(_raw_info(source)['virtual-size'])
    _initialize(target, size, cmd.encryptedDek)
    _write_plain_to_luks(_path(source), target, cmd.encryptedDek)
    return target, _verify(target, EncryptionMode.LUKS, encrypted_dek=cmd.encryptedDek)

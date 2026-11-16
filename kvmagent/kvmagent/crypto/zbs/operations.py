import json
import os
import subprocess
import tempfile
import time
import shutil
import sys
from contextlib import contextmanager, nullcontext
from enum import Enum
from urllib.parse import quote

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


def convert(cmd):
    target_mode = EncryptionMode.from_target_encrypted(cmd.targetEncrypted)
    source, target = cmd.installPath, cmd.targetInstallPath
    if _path(source) == _path(target):
        raise ValueError('source and target CBD paths must differ')
    if _encrypted(source) == (target_mode is EncryptionMode.LUKS):
        raise ValueError('source and target encryption states are identical')
    if target_mode is EncryptionMode.LUKS:
        size = int(cmd.virtualSize)
        _initialize(target, size, cmd.encryptedDek)
        _write_plain_to_luks(_path(source), target, cmd.encryptedDek)
    else:
        with secret.luks_secret_channel(cmd.encryptedDek) as secret_file:
            run_checked([QEMU_IMG, 'convert', '-n', '--object',
                         'secret,id=luks_sec,format=raw,file=%s' % secret_file,
                         '--image-opts', _luks_options(_path(source)), '-O', 'raw', _path(target)])
    return _verify(target, target_mode, cmd.encryptedDek)


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


def resize(cmd):
    _resize_luks(cmd.installPath, cmd.virtualSize, cmd.encryptedDek)
    return _verify(cmd.installPath, EncryptionMode.LUKS, encrypted_dek=cmd.encryptedDek)


def _log_qsd_start_failure(stage, returncode):
    logger.error('crypto operation=zbs.download_encrypted_imagestore stage=%s returncode=%s tool=qemu-storage-daemon',
                 stage, returncode)


def _cleanup_qsd(process, workspace):
    failure = None
    stopped = process is None
    if process is not None:
        try:
            stopped = process.poll() is not None
        except Exception as error:
            log_failure('zbs.download_encrypted_imagestore', 'qsd_poll', error)
            failure = error
        if not stopped:
            for action in ('terminate', 'kill'):
                try:
                    getattr(process, action)()
                except Exception as error:
                    log_failure('zbs.download_encrypted_imagestore', 'qsd_' + action, error)
                    failure = failure or error
                try:
                    process.wait(timeout=10)
                    stopped = True
                    break
                except Exception as error:
                    if action == 'terminate' and isinstance(error, subprocess.TimeoutExpired):
                        continue
                    log_failure('zbs.download_encrypted_imagestore', 'qsd_' + action + '_wait', error)
                    failure = failure or error
    if stopped:
        try:
            shutil.rmtree(workspace)
        except Exception as error:
            log_failure('zbs.download_encrypted_imagestore', 'qsd_workspace_cleanup', error)
            failure = failure or error
    else:
        logger.error('crypto operation=zbs.download_encrypted_imagestore stage=qsd_unreaped pid=%s workspace=%s',
                     process.pid, workspace)
    if failure is not None:
        raise failure


@contextmanager
def _imagestore_nbd_source(host, port, exports, source_envelope):
    workspace = tempfile.mkdtemp(prefix='zbs-imagestore-nbd-')
    socket_path = os.path.join(workspace, 'source.sock')
    qsd_log_path = os.path.join(workspace, 'qsd.log')
    process = None
    try:
        secret_context = secret.luks_secret_channel(source_envelope) if source_envelope else nullcontext()
        with secret_context as source_secret:
            command = ['/usr/bin/qemu-storage-daemon']
            if source_secret:
                command.extend(['--object', 'secret,id=luks_sec,format=raw,file=%s' % source_secret])
            backing = None
            for index in reversed(range(len(exports))):
                nbd_node = 'source-nbd-%d' % index
                qcow_node = 'source-qcow2-%d' % index
                command.extend(['--blockdev', json.dumps({
                    'driver': 'nbd', 'node-name': nbd_node,
                    'server': {'type': 'inet', 'host': str(host), 'port': str(port)},
                    'export': str(exports[index]), 'read-only': True}, separators=(',', ':'))])
                qcow_options = {'driver': 'qcow2', 'node-name': qcow_node,
                                'file': nbd_node, 'backing': backing, 'read-only': True}
                if source_secret:
                    qcow_options['encrypt'] = {'format': 'luks', 'key-secret': 'luks_sec'}
                command.extend(['--blockdev', json.dumps(qcow_options, separators=(',', ':'))])
                backing = qcow_node
            command.extend(['--nbd-server', 'addr.type=unix,addr.path=%s' % socket_path,
                            '--export', json.dumps({'type': 'nbd', 'id': 'logical-top',
                                                    'node-name': backing, 'name': 'top',
                                                    'writable': False}, separators=(',', ':'))])
            with open(qsd_log_path, 'w') as qsd_log:
                process = subprocess.Popen(command, stdout=qsd_log, stderr=subprocess.STDOUT,
                                           close_fds=True)
            for _ in range(100):
                if os.path.exists(socket_path):
                    break
                returncode = process.poll()
                if returncode is not None:
                    _log_qsd_start_failure('qsd_startup', returncode)
                    raise RuntimeError('ImageStore NBD source failed to start')
                time.sleep(0.1)
            else:
                _log_qsd_start_failure('qsd_startup_timeout', process.poll())
                raise RuntimeError('ImageStore NBD source timed out')

        yield 'nbd+unix:///top?socket=%s' % quote(socket_path, safe='/')
    finally:
        failed = sys.exc_info()[0] is not None
        try:
            _cleanup_qsd(process, workspace)
        except Exception:
            if not failed:
                raise


def download_encrypted_imagestore(cmd):
    target = cmd.primaryStorageInstallPath
    _path(target)
    if not getattr(cmd, 'encryptedDek', None):
        raise ValueError('encryptedDek is required')
    host = getattr(cmd, 'backupStorageHostname', None)
    port = int(getattr(cmd, 'backupStorageNbdPort', 0) or 0)
    exports = list(getattr(cmd, 'backupStorageNbdExportNames', ()) or ())
    if not host or port <= 0 or not exports:
        raise ValueError('ImageStore NBD source is required')
    _verify(target, EncryptionMode.LUKS, encrypted_dek=cmd.encryptedDek)

    source_envelope = cmd.encryptedDek if getattr(cmd, 'sourceEncrypted', False) else None
    with _imagestore_nbd_source(host, port, exports, source_envelope) as source_uri:
        with secret.luks_secret_channel(cmd.encryptedDek) as target_secret:
            run_checked([QEMU_IMG, 'convert', '-n', '--target-image-opts',
                         '--object', 'secret,id=luks_sec,format=raw,file=%s' % target_secret,
                         '-m', '16', '-W', '-f', 'raw', source_uri, _luks_options(_path(target))])
        return _verify(target, EncryptionMode.LUKS, encrypted_dek=cmd.encryptedDek)

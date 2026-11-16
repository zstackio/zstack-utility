import json
import os
import subprocess
import stat
import uuid
from contextlib import contextmanager, nullcontext
from enum import Enum

from kvmagent.crypto.http_error import check_output, log_failure, run_checked
from kvmagent.crypto.volume_request import EncryptionMode
from zstacklib.utils import log


QEMU_IMG = '/usr/bin/qemu-img'
QEMU_IO = '/usr/bin/qemu-io'
logger = log.get_logger(__name__)


class ConversionPolicy(Enum):
    REQUIRE_STATE_CHANGE = 'require-state-change'
    ALLOW_SAME_STATE = 'allow-same-state'


def cleanup_temporary_file(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError as error:
        logger.error('Crypto temporary file cleanup requires recovery: path=%r', path)
        log_failure('qemu_volume.cleanup_temporary_file', 'unlink', error)


@contextmanager
def staged_file(target):
    if os.path.lexists(target):
        raise FileExistsError(target)
    temporary = '%s.creating.%s' % (target, uuid.uuid4().hex)
    try:
        yield temporary
        os.link(temporary, target)
    finally:
        cleanup_temporary_file(temporary)


def _file_option(path):
    return 'file.filename=' + path.replace(',', ',,')


def is_luks_encrypted_image(path):
    info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', path]))
    return is_luks_image_info(info)


def is_luks_image_info(info):
    if info.get('encrypted') is True:
        return True
    encryption_info = info.get('format-specific', {}).get('data', {}).get('encrypt')
    return bool(isinstance(encryption_info, dict) and encryption_info.get('format') == 'luks')


def verify_luks_open(path, secret_file_or_provider):
    options = _source_image_options(path)
    if not options:
        return False
    # map can abort on unaligned backing chains; probe only key usability.
    with _secret_context(secret_file_or_provider) as channel:
        run_checked([QEMU_IO, '-r', '--object',
                     'secret,id=luks_sec,format=raw,file=%s' % channel,
                     '--image-opts', '-c', 'read -q 0 512', options], stdout=subprocess.DEVNULL)
    return True


def create_encrypted_qcow2(path, size, secret_file, options=''):
    _create_encrypted_qcow2(path, size, secret_file, options)


def clone_encrypted_qcow2(backing, path, secret_file, options='', size=None):
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', backing]))
    _create_encrypted_qcow2(path, size or info['virtual-size'], secret_file, options, backing, info['format'])


def _create_encrypted_qcow2(path, size, secret_file, options, backing=None, backing_format=None):
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    with staged_file(path) as target:
        command = [QEMU_IMG, 'create', '--object',
                   'secret,id=luks_sec,format=raw,file=%s' % secret_file]
        if backing:
            command.extend(['-u', '-F', backing_format, '-b', backing])
        command.extend(['-f', 'qcow2', '-o',
                   'encrypt.format=luks,encrypt.key-secret=luks_sec' + (',' + options if options else ''),
                   target, str(size)])
        run_checked(command)
        if not is_luks_encrypted_image(target):
            raise RuntimeError('created volume is not LUKS encrypted')
        os.chmod(target, 0o660)


def convert_qcow2_encryption(source, target, target_mode, secret_file, target_backing=None):
    target_encrypted = target_mode is EncryptionMode.LUKS
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    with staged_file(target) as temporary:
        source_encrypted = is_luks_encrypted_image(source)
        if source_encrypted == target_encrypted:
            raise ValueError('source and target encryption states are identical')

        command = [QEMU_IMG, 'convert', '-m', '16', '-W']
        image_options = _source_image_options(source)
        if image_options:
            command.extend(['--image-opts', image_options])
        else:
            command.extend(['-f', 'qcow2', source])
        command.extend(['-O', 'qcow2'])
        if target_encrypted:
            command.extend(['-o', 'encrypt.format=luks,encrypt.key-secret=luks_sec'])
        backing_needs_reset = False
        if target_backing:
            backing_format, backing_arg = _backing_argument(target_backing)
            backing_needs_reset = backing_arg != target_backing
            command.extend(['-F', backing_format, '-B', backing_arg])
        command.append(temporary)
        with _secret_context(secret_file) as channel:
            secret = 'secret,id=luks_sec,format=raw,file=%s' % channel
            run_checked(command[:2] + ['--object', secret] + command[2:])
        if is_luks_encrypted_image(temporary) != target_encrypted:
            raise RuntimeError('converted volume format does not match target encryption state')
        if backing_needs_reset:
            with _secret_context(secret_file) as channel:
                reset = [QEMU_IMG, 'rebase', '-u', '--object',
                         'secret,id=luks_sec,format=raw,file=%s' % channel,
                         '-F', backing_format, '-b', target_backing]
                if target_encrypted:
                    reset.extend(['--image-opts', 'driver=qcow2,encrypt.key-secret=luks_sec,' + _file_option(temporary)])
                else:
                    reset.append(temporary)
                run_checked(reset)
        verify_luks_open(temporary, secret_file)
        os.chmod(temporary, 0o660)


def iter_image_chain(path):
    if not path:
        return
    layers = iter(json.loads(check_output(
        [QEMU_IMG, 'info', '--output=json', '--backing-chain', path])))
    seen = set()
    while path:
        if path in seen:
            raise ValueError('volume backing chain contains a cycle')
        seen.add(path)
        info = next(layers, None)
        if info is None:
            raise RuntimeError('QEMU returned incomplete backing chain metadata')
        yield path, info
        path = info.get('full-backing-filename') or info.get('backing-filename')


def _source_image_options(path):
    options = []
    prefix = ''
    encrypted = False
    for path, info in iter_image_chain(path):
        options.extend(['%sdriver=%s' % (prefix, info['format']), prefix + _file_option(path)])
        if is_luks_image_info(info):
            key_field = 'key-secret' if info['format'] == 'luks' else 'encrypt.key-secret'
            options.append('%s%s=luks_sec' % (prefix, key_field))
            encrypted = True
        prefix += 'backing.'
    return ','.join(options) if encrypted else None


def _backing_argument(path):
    layers = list(iter_image_chain(path))
    backing_format = layers[0][1]['format']
    if not any(is_luks_image_info(info) for _, info in layers):
        return backing_format, path

    backing = None
    for filename, info in reversed(layers):
        options = {'driver': info['format'], 'file': {'driver': 'file', 'filename': filename}}
        if is_luks_image_info(info):
            if info['format'] == 'luks':
                options['key-secret'] = 'luks_sec'
            else:
                options['encrypt'] = {'key-secret': 'luks_sec'}
        if backing is not None:
            options['backing'] = backing
        backing = options
    return backing_format, 'json:' + json.dumps(backing, separators=(',', ':'))


def encrypt_plain_file_in_place(path, secret_file):
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', path]))
    if is_luks_encrypted_image(path):
        raise ValueError('source is already LUKS encrypted')
    temporary = '%s.encrypting.%s' % (path, uuid.uuid4().hex)
    try:
        if info['format'] == 'qcow2':
            convert_qcow2_encryption(path, temporary, EncryptionMode.LUKS, secret_file)
        elif info['format'] == 'raw':
            with _secret_context(secret_file) as channel:
                run_checked([
                    QEMU_IMG, 'convert', '--object',
                    'secret,id=luks_sec,format=raw,file=%s' % channel,
                    '-f', 'raw', '-O', 'luks', '-o', 'key-secret=luks_sec', path, temporary])
            # Conversion and verification use separate QEMU processes and fresh channels.
            verify_luks_open(temporary, secret_file)
        else:
            raise ValueError('unsupported source format: %s' % info['format'])
        if not is_luks_encrypted_image(temporary):
            raise RuntimeError('encrypted target format verification failed')
        os.chmod(temporary, 0o660)
        os.replace(temporary, path)
    finally:
        cleanup_temporary_file(temporary)


def create_encrypted_qcow2_block(path, size, secret_file, backing=None, options=''):
    if not stat.S_ISBLK(os.stat(path).st_mode):
        raise ValueError('target must be a precreated block device')
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    command = [QEMU_IMG, 'create', '--object',
               'secret,id=luks_sec,format=raw,file=%s' % secret_file]
    if backing:
        backing_info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', backing]))
        command.extend(['-u', '-F', backing_info['format'], '-b', backing])
    command.extend(['-f', 'qcow2', '-o',
                    'encrypt.format=luks,encrypt.key-secret=luks_sec' + (',' + options if options else ''),
                    path, str(size)])
    run_checked(command)
    if not is_luks_encrypted_image(path):
        raise RuntimeError('created block volume is not LUKS encrypted')


def convert_qcow2_encryption_to_block(source, target, target_mode, secret_file, target_backing=None,
                                     *, policy=ConversionPolicy.REQUIRE_STATE_CHANGE):
    target_encrypted = target_mode is EncryptionMode.LUKS
    if not stat.S_ISBLK(os.stat(target).st_mode):
        raise ValueError('target must be a precreated block device')
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    if (is_luks_encrypted_image(source) == target_encrypted and
            policy is ConversionPolicy.REQUIRE_STATE_CHANGE):
        raise ValueError('source and target encryption states are identical')
    info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', source]))
    create = [QEMU_IMG, 'create']
    if target_backing:
        backing_info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', target_backing]))
        create.extend(['-u', '-F', backing_info['format'], '-b', target_backing])
    create.extend(['-f', 'qcow2'])
    if target_encrypted:
        create.extend(['-o', 'encrypt.format=luks,encrypt.key-secret=luks_sec'])
    create.extend([target, str(info['virtual-size'])])
    with _secret_context(secret_file) as channel:
        run_checked(create[:2] + ['--object',
            'secret,id=luks_sec,format=raw,file=%s' % channel] + create[2:])

    command = [QEMU_IMG, 'convert', '-n', '-m', '16', '-W']
    source_options = _source_image_options(source)
    if source_options:
        command.extend(['--image-opts', source_options])
    else:
        command.extend(['-f', info['format'], source])
    target_options = 'driver=qcow2,' + _file_option(target)
    if target_encrypted:
        target_options += ',encrypt.key-secret=luks_sec'
    if target_backing:
        target_options = _source_image_options(target) or target_options
    command.extend(['--target-image-opts', target_options])
    with _secret_context(secret_file) as channel:
        run_checked(command[:2] + ['--object',
            'secret,id=luks_sec,format=raw,file=%s' % channel] + command[2:])
    if is_luks_encrypted_image(target) != target_encrypted:
        raise RuntimeError('converted block volume format does not match target encryption state')
    verify_luks_open(target, secret_file)


def create_encrypted_template(source, target, secret_file):
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    with staged_file(target) as temporary:
        command = [QEMU_IMG, 'convert', '--object',
                   'secret,id=luks_sec,format=raw,file=%s' % secret_file]
        source_options = _source_image_options(source)
        if source_options:
            command.extend(['--image-opts', source_options])
        else:
            info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', source]))
            command.extend(['-f', info['format'], source])
        command.extend(['-O', 'qcow2', '-o', 'encrypt.format=luks,encrypt.key-secret=luks_sec', temporary])
        run_checked(command)
        if not is_luks_encrypted_image(temporary):
            raise RuntimeError('created template is not LUKS encrypted')
        os.chmod(temporary, 0o660)


def rebase_no_check_with_secret(backing, target, secret_file, *, backing_format=None):
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    if backing_format is None:
        info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', backing]))
        backing_format = info['format']
    command = [QEMU_IMG, 'rebase', '-u', '--object',
               'secret,id=luks_sec,format=raw,file=%s' % secret_file,
               '-F', backing_format, '-b', backing]
    if is_luks_encrypted_image(target):
        command.extend(['--image-opts', 'driver=qcow2,encrypt.key-secret=luks_sec,' + _file_option(target)])
    else:
        command.append(target)
    run_checked(command)


def commit_with_secret(top, base, secret_file):
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    command = [QEMU_IMG, 'commit', '--object',
               'secret,id=luks_sec,format=raw,file=%s' % secret_file]
    info = json.loads(check_output([QEMU_IMG, 'info', '--output=json', top]))
    current_backing = info.get('full-backing-filename') or info.get('backing-filename')
    if current_backing != base:
        command.extend(['-b', base])
    source_options = _source_image_options(top)
    if source_options:
        command.extend(['--image-opts', source_options])
    else:
        command.append(top)
    run_checked(command)


def resize_with_secret(target, size, secret_file):
    if not secret_file:
        raise ValueError('LUKS secret file is required')
    command = [QEMU_IMG, 'resize', '--object',
               'secret,id=luks_sec,format=raw,file=%s' % secret_file]
    image_options = _source_image_options(target)
    if image_options:
        command.extend(['--image-opts', image_options])
    else:
        command.extend(['-f', 'qcow2', target])
    command.append(str(size))
    run_checked(command)


def _secret_context(secret_file_or_provider):
    return secret_file_or_provider() if callable(secret_file_or_provider) else nullcontext(secret_file_or_provider)


def safe_rebase_with_secret(backing, target, secret_file_provider):
    if not backing or not secret_file_provider:
        raise ValueError('backing and LUKS secret provider are required')
    backing_format, backing_arg = _backing_argument(backing)
    command = [QEMU_IMG, 'rebase', '-F', backing_format, '-b', backing_arg]
    source_options = _source_image_options(target)
    if source_options:
        command.extend(['--image-opts', source_options])
    else:
        command.append(target)
    with _secret_context(secret_file_provider) as channel:
        run_checked(command[:2] + ['--object',
            'secret,id=luks_sec,format=raw,file=%s' % channel] + command[2:])
    if backing_arg != backing:
        with _secret_context(secret_file_provider) as channel:
            rebase_no_check_with_secret(backing, target, channel, backing_format=backing_format)
    verify_luks_open(target, secret_file_provider)

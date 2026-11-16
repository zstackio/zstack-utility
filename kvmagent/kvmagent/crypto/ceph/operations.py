import errno
import json
import os
import subprocess
import uuid
from contextlib import contextmanager
from types import SimpleNamespace

from kvmagent.crypto import secret
from kvmagent.crypto import imagestore
from kvmagent.crypto.conversion_rollback import conversion_rollback
from kvmagent.crypto.http_error import check_output, log_failure, run_checked
from zstacklib.utils import lock, log
from zstacklib.utils import ceph as ceph_utils
from kvmagent.crypto.qemu_volume import QEMU_IMG
from kvmagent.crypto.volume_request import EncryptionMode


CEPH_CLIENT_CONF_ROOT = '/var/lib/zstack/ceph'
logger = log.get_logger(__name__)


def _image_path(install_path):
    if not install_path or not install_path.startswith('ceph://'):
        raise ValueError('Ceph install path is required')
    image = install_path[len('ceph://'):]
    if '/' not in image:
        raise ValueError('Ceph install path must contain pool and image')
    return image


def _config(cmd):
    ps_uuid = getattr(cmd, 'psUuid', None)
    if not ps_uuid or os.path.basename(ps_uuid) != ps_uuid:
        raise ValueError('psUuid is required for Ceph LUKS operation')
    path = os.path.join(CEPH_CLIENT_CONF_ROOT, ps_uuid, 'ceph.conf')
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return path


def _uri(image, config):
    username = _username(config)
    identity = ':id=%s' % username.split('.')[-1] if username else ''
    return 'rbd:%s%s:conf=%s' % (image, identity, config)


def _username(config):
    ps_uuid = os.path.basename(os.path.dirname(config))
    _, _, username = ceph_utils.get_ceph_client_conf(ps_uuid, ceph_utils.get_ceph_manufacturer())
    return username


def _rbd_command(config, *args):
    command = ['/usr/bin/rbd', '--conf', config]
    username = _username(config)
    if username:
        command.extend(['--id', username.split('.')[-1]])
    return command + list(args)


def _image_options(image, config):
    pool, name = image.split('/', 1)
    name, separator, snapshot = name.partition('@')
    options = 'driver=luks,key-secret=luks_sec,file.driver=rbd,file.pool=%s,file.image=%s' % (pool, name)
    if separator:
        options += ',file.snapshot=%s' % snapshot
    options += ',file.conf=%s' % config
    username = _username(config)
    return options + (',file.user=%s' % username.split('.')[-1] if username else '')


def _info(image, config):
    return json.loads(check_output([QEMU_IMG, 'info', '--output=json', _uri(image, config)]))


def is_encrypted(install_path, primary_storage_uuid):
    config = _config(SimpleNamespace(psUuid=primary_storage_uuid))
    return _info(_image_path(install_path), config)['format'] == 'luks'


def _rbd_exists(image, config):
    result = subprocess.run(_rbd_command(config, 'info', image),
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode == errno.ENOENT:
        return False
    result.check_returncode()
    return True


def _rbd_rename(source, target, config):
    # RBD rejects an existing destination, including one created during staging.
    run_checked(_rbd_command(config, 'mv', source, target))


def _rbd_remove(image, config):
    run_checked(_rbd_command(config, 'rm', image))


def actual_size(install_path, cmd):
    config = _config(cmd)
    image = _image_path(install_path)
    try:
        usage = json.loads(check_output(
            _rbd_command(config, 'du', image, '--format', 'json')))
        sizes = [int(item['used_size']) for item in usage.get('images', ())]
        return sum(sizes) if sizes else None
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        log_failure('ceph.actual_size', 'rbd_du', error)
        return None


def _source_args(image, config, source_mode):
    if source_mode is EncryptionMode.LUKS:
        return ['--image-opts', _image_options(image, config)]
    return ['-f', 'raw', _uri(image, config)]


def _verified_state(image, config, target_mode, encrypted_dek=None):
    actual = _info(image, config)['format'] == 'luks'
    if actual != (target_mode is EncryptionMode.LUKS):
        raise RuntimeError('RBD target encryption format verification failed')
    if target_mode is EncryptionMode.LUKS:
        if not encrypted_dek:
            raise ValueError('encryptedDek is required')
        with secret.luks_secret_channel(encrypted_dek) as secret_file:
            check_output([QEMU_IMG, 'map', '--output=json', '--object',
                          'secret,id=luks_sec,format=raw,file=%s' % secret_file,
                          '--image-opts', _image_options(image, config)])
    return actual


def _staged_image_path(target):
    if '@' in target:
        raise ValueError('RBD target must be an active image path')
    return '%s-converting-%s' % (target, uuid.uuid4().hex)


def _remove_staged_image(image, config):
    if _rbd_exists(image, config):
        _rbd_remove(image, config)


@contextmanager
def _stage_rbd(target, config):
    staged_image = _staged_image_path(target)
    with conversion_rollback('ceph.stage_rbd') as (remove, _):
        remove('remove_temporary_image', _remove_staged_image, staged_image, config,
               target=target, temporary=staged_image, config=config)
        yield staged_image


def _source_mode(source, config):
    return EncryptionMode.LUKS if _info(source, config)['format'] == 'luks' else EncryptionMode.PLAIN


def _convert(source, staged_image, config, target_mode, encrypted_dek, source_mode=None):
    if not encrypted_dek:
        raise ValueError('encryptedDek is required')
    if source_mode is None:
        source_mode = _source_mode(source, config)
    with secret.luks_secret_channel(encrypted_dek) as secret_file:
        command = [QEMU_IMG, 'convert', '--object',
                   'secret,id=luks_sec,format=raw,file=%s' % secret_file, '-m', '16', '-W']
        command.extend(_source_args(source, config, source_mode))
        command.extend(['-O', 'luks' if target_mode is EncryptionMode.LUKS else 'raw'])
        if target_mode is EncryptionMode.LUKS:
            command.extend(['-o', 'key-secret=luks_sec'])
        command.append(_uri(staged_image, config))
        run_checked(command)
    _verified_state(staged_image, config, target_mode, encrypted_dek)


def create_empty(cmd):
    config = _config(cmd)
    image = _image_path(cmd.installPath)
    size = int(cmd.size)
    if size <= 0 or not getattr(cmd, 'encryptedDek', None):
        raise ValueError('positive size and encryptedDek are required')
    if _rbd_exists(image, config):
        raise FileExistsError(image)
    with _stage_rbd(image, config) as staged_image:
        with secret.luks_secret_channel(cmd.encryptedDek) as secret_file:
            run_checked([QEMU_IMG, 'create', '--object',
                         'secret,id=luks_sec,format=raw,file=%s' % secret_file,
                         '-f', 'luks', '-o', 'key-secret=luks_sec', _uri(staged_image, config), str(size)])
        _verified_state(staged_image, config, EncryptionMode.LUKS, cmd.encryptedDek)
        _rbd_rename(staged_image, image, config)
    return True


def clone(cmd):
    config = _config(cmd)
    source = _image_path(cmd.srcPath)
    target = _image_path(cmd.dstPath)
    if source == target:
        raise ValueError('source and target RBD paths must differ')
    if _rbd_exists(target, config):
        raise FileExistsError(target)
    with _stage_rbd(target, config) as staged_image:
        _convert(source, staged_image, config, EncryptionMode.LUKS, cmd.encryptedDek)
        size = getattr(cmd, 'virtualSizeForLuksClone', None)
        if size:
            _resize(staged_image, config, size, cmd.encryptedDek)
        _rbd_rename(staged_image, target, config)
    return True


def convert(cmd):
    target_mode = EncryptionMode.from_target_encrypted(cmd.targetEncrypted)
    config = _config(cmd)
    source = _image_path(cmd.installPath)
    target = _image_path(cmd.targetInstallPath)
    source_mode = _source_mode(source, config)
    if source_mode is target_mode:
        raise ValueError('source and target encryption states are identical')
    trash_path = getattr(cmd, 'sourceTrashInstallPath', None)
    trash = _image_path(trash_path) if trash_path else '%s-trash-%s' % (source, uuid.uuid4().hex[:8])
    _publish_conversion(source, target, trash, config, target_mode=target_mode,
                        encrypted_dek=cmd.encryptedDek, source_mode=source_mode,
                        virtual_size=getattr(cmd, 'virtualSize', None))
    return cmd.targetEncrypted


def encrypt_in_place(cmd):
    config = _config(cmd)
    source = _image_path(cmd.installPath)
    if '@' in source:
        raise ValueError('RBD conversion requires an active image path')
    backup = source + '-luks-original'
    with lock.NamedLock('ceph-encrypt-' + source):
        if _source_mode(source, config) is EncryptionMode.LUKS:
            if _rbd_exists(backup, config):
                logger.error('Ceph encryption has an unresolved backup image %r for %r', backup, source)
                raise RuntimeError('Ceph encryption backup already exists')
            _verified_state(source, config, EncryptionMode.LUKS, cmd.encryptedDek)
            return cmd.installPath
        _publish_conversion(source, source, backup, config, target_mode=EncryptionMode.LUKS,
                            encrypted_dek=cmd.encryptedDek, source_mode=EncryptionMode.PLAIN)
        try:
            _rbd_remove(backup, config)
        except (OSError, subprocess.CalledProcessError) as error:
            log_failure('ceph.encrypt_in_place', 'remove_plaintext_backup', error)
            if _rbd_exists(backup, config):
                _restore_plain_rbd(source, backup, config)
                raise
    return cmd.installPath


def _restore_plain_rbd(source, backup, config):
    encrypted_copy = '%s-rollback-%s' % (source, uuid.uuid4().hex)
    try:
        _rbd_rename(source, encrypted_copy, config)
        try:
            _rbd_rename(backup, source, config)
        except (OSError, subprocess.CalledProcessError):
            _rbd_rename(encrypted_copy, source, config)
            raise
    except (OSError, subprocess.CalledProcessError) as error:
        logger.error('Ceph encryption rollback requires recovery: source=%r backup=%r encrypted_copy=%r',
                     source, backup, encrypted_copy)
        log_failure('ceph.encrypt_in_place', 'restore_plaintext_backup', error)
        return
    try:
        _rbd_remove(encrypted_copy, config)
    except (OSError, subprocess.CalledProcessError) as error:
        logger.error('Ceph encryption rollback left an encrypted copy %r', encrypted_copy)
        log_failure('ceph.encrypt_in_place', 'remove_rolled_back_image', error)


def _publish_conversion(source, target, trash, config, target_mode, encrypted_dek,
                        source_mode, virtual_size=None):
    if '@' in source or '@' in target or '@' in trash:
        raise ValueError('RBD conversion requires active image paths')
    if _rbd_exists(trash, config) or (target != source and _rbd_exists(target, config)):
        raise FileExistsError('RBD conversion destination already exists')
    staged_image = _staged_image_path(target)
    resources = dict(source=source, trash=trash, temporary=staged_image, target=target)
    with conversion_rollback('ceph._publish_conversion') as (_, undo):
        undo('remove_temporary_image', _remove_staged_image, staged_image, config, **resources)
        _convert(source, staged_image, config, target_mode, encrypted_dek, source_mode)
        if target_mode is EncryptionMode.LUKS and virtual_size:
            _resize(staged_image, config, virtual_size, encrypted_dek)
        _rbd_rename(source, trash, config)
        undo('restore_original_image', _rbd_rename, trash, source, config, **resources)
        _rbd_rename(staged_image, target, config)


def _resize(image, config, size, encrypted_dek):
    if int(size) <= 0 or not encrypted_dek:
        raise ValueError('positive virtualSize and encryptedDek are required')
    _verified_state(image, config, EncryptionMode.LUKS, encrypted_dek)
    with secret.luks_secret_channel(encrypted_dek) as secret_file:
        run_checked([QEMU_IMG, 'resize', '--object',
                     'secret,id=luks_sec,format=raw,file=%s' % secret_file,
                     '--image-opts', _image_options(image, config), str(size)])
    _verified_state(image, config, EncryptionMode.LUKS, encrypted_dek)


def resize(cmd):
    config = _config(cmd)
    _resize(_image_path(cmd.installPath), config, cmd.virtualSize, cmd.encryptedDek)
    return True


def download_encrypted_imagestore(cmd, client):
    config = _config(cmd)
    image = _image_path(cmd.primaryStorageInstallPath)
    if not getattr(cmd, 'encryptedDek', None):
        raise ValueError('encryptedDek is required')
    if not getattr(cmd, 'hostname', None):
        raise ValueError('hostname is required')
    if _rbd_exists(image, config):
        raise FileExistsError(image)
    client._check_zstore_cli()
    name, image_id = client._parse_image_reference(cmd.backupStorageInstallPath)
    encryption_spec = {field: getattr(cmd, field, None) for field in
                       ('encryptedDek', 'keyProviderUuid', 'keyVersion', 'cipher')}
    encryption_spec['encrypted'] = True
    with _stage_rbd(image, config) as staged_image:
        with imagestore.temporary_json(encryption_spec) as target_file:
            command = [client.ZSTORE_CLI_BIN, '-rootca',
                       '/var/lib/zstack/imagestorebackupstorage/package/certs/ca.pem',
                       '-url', client._build_registry_url(cmd.hostname), 'pull',
                       '-target-encryption-json-file', target_file,
                       '-secret-channel-provider', imagestore.KEY_AGENT_PROVIDER]
            if getattr(cmd, 'sourceEncrypted', False):
                with imagestore.temporary_json(encryption_spec) as source_file:
                    source_command = command + ['-encryption-json-file', source_file]
                    _run_pull(source_command, cmd, name, image_id, config, 'ceph://' + staged_image)
            else:
                _run_pull(command, cmd, name, image_id, config, 'ceph://' + staged_image)
        _verified_state(staged_image, config, EncryptionMode.LUKS, cmd.encryptedDek)
        _rbd_rename(staged_image, image, config)
    return True


def _run_pull(command, cmd, name, image_id, config, install_path):
    concurrency = getattr(cmd, 'concurrency', None)
    if concurrency and int(concurrency) > 1:
        command.extend(['-concurrency=%d' % int(concurrency)])
    command.extend(['-installpath', install_path, '%s:%s' % (name, image_id)])
    environment = os.environ.copy()
    environment['CEPH_CONF'] = config
    environment['CEPH_ARGS'] = '--conf %s' % config
    run_checked(command, env=environment)

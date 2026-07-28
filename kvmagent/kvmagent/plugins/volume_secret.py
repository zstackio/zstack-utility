import base64
import contextlib
import os
import re

from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

KEY_AGENT_UNIX_SOCKET = 'unix:///var/run/key-agent/key-agent.sock'
KEY_AGENT_SOCKET_PATH = '/var/run/key-agent/key-agent.sock'
VOLUME_BACKUP_ENCRYPTION_ADDON = 'VolumeBackupEncryption'
VOLUME_BACKUP_ENCRYPTION_SPECS = 'specs'

try:
    import grpc
    from kvmagent.keyagent import key_agent_pb2
    from kvmagent.keyagent import key_agent_pb2_grpc
    KEY_AGENT_GRPC_AVAILABLE = True
except Exception:
    KEY_AGENT_GRPC_AVAILABLE = False


def _decode_encrypted_dek(encrypted_dek_b64):
    if not encrypted_dek_b64:
        raise Exception('encryptedDek is required')

    normalized = str(encrypted_dek_b64).strip()
    if not re.match(r'^[A-Za-z0-9+/]+={0,2}$', normalized) or len(normalized) % 4 != 0:
        raise Exception('encryptedDek must be valid base64')

    encrypted_dek = base64.b64decode(normalized)
    encoded = base64.b64encode(encrypted_dek)
    if not isinstance(encoded, str):
        encoded = encoded.decode('ascii')
    if encoded.rstrip('=') != normalized.rstrip('='):
        raise Exception('encryptedDek must be canonical base64')
    return encrypted_dek


def _get_value(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return obj[key]
    except Exception:
        return getattr(obj, key, default)


def _volume_backup_spec_to_json(spec):
    if not spec or not _get_value(spec, 'encrypted', False):
        return None

    return {
        'encrypted': True,
        'encryptedDek': _get_value(spec, 'encryptedDek'),
        'keyProviderUuid': _get_value(spec, 'keyProviderUuid'),
        'keyVersion': _get_value(spec, 'keyVersion'),
        'cipher': _get_value(spec, 'cipher'),
    }


def _volume_backup_specs(addons):
    addon = _get_value(addons, VOLUME_BACKUP_ENCRYPTION_ADDON)
    return _get_value(addon, VOLUME_BACKUP_ENCRYPTION_SPECS, []) or []


def get_volume_backup_encryption_spec(addons, device_id):
    for spec in _volume_backup_specs(addons):
        if _get_value(spec, 'deviceId') == device_id:
            return _volume_backup_spec_to_json(spec)
    return None


def make_backup_args_option(cmdstr, args, addons, device_ids, write_json_temp_file, key_agent_provider):
    specs = _volume_backup_specs(addons)
    specs_by_device_id = {
        _get_value(spec, 'deviceId'): spec for spec in specs
    }

    if not any(_volume_backup_spec_to_json(spec) for spec in specs_by_device_id.values()):
        return cmdstr, None

    backups = []
    for idx, arg in enumerate(args):
        item = {
            'bitmap': arg[0],
            'mode': arg[1],
            'drive': arg[2],
            'speed': arg[3],
        }

        device_id = device_ids[idx] if idx < len(device_ids) else None
        spec_json = _volume_backup_spec_to_json(specs_by_device_id.get(device_id))
        if spec_json:
            item['encryption'] = spec_json
        backups.append(item)

    args_file = write_json_temp_file({'backups': backups})
    args_option = '-args-json-file %s -secret-channel-provider %s' % (
        args_file, key_agent_provider)
    backup_cmdstr = re.sub(r' -args [^ ]+$', ' %s' % args_option, cmdstr)
    if backup_cmdstr == cmdstr:
        raise Exception('failed to replace zstcli backup args option')
    return backup_cmdstr, args_file


def prepare_luks_secret_material_channel(encrypted_dek_b64):
    if not KEY_AGENT_GRPC_AVAILABLE:
        raise Exception('key_agent grpc not available')
    if not os.path.exists(KEY_AGENT_SOCKET_PATH):
        raise Exception('key-agent socket not found')

    encrypted_dek = _decode_encrypted_dek(encrypted_dek_b64)
    channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
    try:
        stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
        req = key_agent_pb2.PrepareLuksSecretMaterialChannelRequest(encrypted_dek=encrypted_dek)
        resp = stub.PrepareLuksSecretMaterialChannel(req, timeout=60)
        path = getattr(resp, 'channel_path', None) if resp else None
        path = str(path).strip() if path else ''
        if not path:
            raise Exception('key-agent PrepareLuksSecretMaterialChannel returned empty channel_path')
        return path
    except grpc.RpcError as e:
        details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
        logger.debug('key-agent PrepareLuksSecretMaterialChannel gRPC error: %s' % details)
        raise Exception(details or str(e))
    finally:
        channel.close()


def make_luks_secret_file(encrypted_dek_b64):
    """Create a one-shot FIFO for a single qemu-img operation.
    The caller passes the returned path to a *_with_secret function,
    which deletes it in its own finally block."""
    return prepare_luks_secret_material_channel(encrypted_dek_b64)


def nbd_target_image_options(nbd_host, nbd_port, export_name, encrypted):
    options = [
        'driver=qcow2',
        'file.driver=nbd',
        'file.server.type=inet',
        'file.server.host=%s' % nbd_host,
        'file.server.port=%s' % nbd_port,
        'file.export=%s' % export_name,
    ]
    if encrypted:
        options.extend([
            'encrypt.format=luks',
            'encrypt.key-secret=target_luks_sec',
        ])
    return ','.join(options)


def target_secret_option(secret_file):
    return '--object secret,id=target_luks_sec,format=raw,file=%s' % linux.shellquote(secret_file)


@contextlib.contextmanager
def luks_secret_channel(encrypted_dek_b64):
    if not encrypted_dek_b64:
        yield None
        return

    channel_path = prepare_luks_secret_material_channel(encrypted_dek_b64)
    try:
        yield channel_path
    finally:
        linux.rm_file_force(channel_path)

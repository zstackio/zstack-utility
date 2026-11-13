import base64
import binascii
import contextlib
import os

from kvmagent.crypto.http_error import log_failure


KEY_AGENT_SOCKET_PATH = '/var/run/key-agent/key-agent.sock'


def decode_encrypted_dek(value):
    if not value:
        raise ValueError('encryptedDek is required')
    try:
        encoded = value.encode('ascii') if isinstance(value, str) else value
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error, TypeError):
        raise ValueError('encryptedDek must be valid base64')
    if base64.b64encode(decoded) != encoded:
        raise ValueError('encryptedDek must be canonical base64')
    return decoded


def prepare_luks_secret_material_channel(encrypted_dek):
    if not os.path.exists(KEY_AGENT_SOCKET_PATH):
        raise RuntimeError('key-agent socket not found')
    try:
        import grpc
        from kvmagent.keyagent import key_agent_pb2, key_agent_pb2_grpc
    except ImportError:
        raise RuntimeError('key-agent grpc is unavailable')

    with grpc.insecure_channel('unix://' + KEY_AGENT_SOCKET_PATH) as channel:
        stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
        request = key_agent_pb2.PrepareLuksSecretMaterialChannelRequest(
            encrypted_dek=decode_encrypted_dek(encrypted_dek))
        try:
            response = stub.PrepareLuksSecretMaterialChannel(request, timeout=60)
        except grpc.RpcError:
            raise RuntimeError('key-agent failed to prepare volume secret') from None
        if not response.channel_path:
            raise RuntimeError('key-agent returned empty secret channel')
        return response.channel_path


def remove_sensitive_file(path, operation):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError as error:
        log_failure(operation, 'unlink_sensitive_file', error)
        return False
    return True


@contextlib.contextmanager
def luks_secret_channel(encrypted_dek):
    path = prepare_luks_secret_material_channel(encrypted_dek)
    try:
        yield path
    finally:
        remove_sensitive_file(path, 'key_agent.secret_channel')

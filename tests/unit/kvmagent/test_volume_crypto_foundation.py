import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from kvmagent.crypto import secret, volume_request


class VolumeRequestTest(unittest.TestCase):
    def test_plain_file_request_uses_original_path(self):
        self.assertFalse(volume_request.should_use_luks_driver(type('Command', (), {'encrypted': False})()))

    def test_wrapped_key_selects_file_crypto(self):
        self.assertTrue(volume_request.should_use_luks_driver(type('Command', (), {'encryptedDek': 'wrapped'})()))

    def test_missing_key_fails_before_plain_file_write(self):
        with self.assertRaisesRegex(ValueError, 'encryptedDek'):
            volume_request.should_use_luks_driver(type('Command', (), {'encrypted': True})())

class VolumeSecretTest(unittest.TestCase):
    def test_invalid_wrapped_key_is_rejected_before_key_agent(self):
        with self.assertRaisesRegex(ValueError, 'base64'):
            secret.decode_encrypted_dek('not base64!')

    def test_key_agent_connection_released_and_rpc_error_sanitized(self):
        class RpcError(Exception):
            pass

        connection = mock.MagicMock()
        channel = connection.__enter__.return_value
        rpc = mock.Mock()
        grpc = SimpleNamespace(insecure_channel=mock.Mock(return_value=connection), RpcError=RpcError)
        generated = {
            'grpc': grpc,
            'kvmagent.keyagent.key_agent_pb2': SimpleNamespace(
                PrepareLuksSecretMaterialChannelRequest=SimpleNamespace),
            'kvmagent.keyagent.key_agent_pb2_grpc': SimpleNamespace(
                KeyAgentServiceStub=mock.Mock(return_value=SimpleNamespace(
                    PrepareLuksSecretMaterialChannel=rpc))),
        }
        with mock.patch.dict(sys.modules, generated), mock.patch.object(secret.os.path, 'exists', return_value=True):
            rpc.return_value = SimpleNamespace(channel_path='/tmp/test-channel')
            self.assertEqual('/tmp/test-channel', secret.prepare_luks_secret_material_channel('d3JhcHBlZA=='))
            rpc.side_effect = RpcError('private RPC detail')
            with self.assertRaisesRegex(RuntimeError, '^key-agent failed to prepare volume secret$'):
                secret.prepare_luks_secret_material_channel('d3JhcHBlZA==')
        self.assertEqual(2, connection.__exit__.call_count)
        generated['kvmagent.keyagent.key_agent_pb2_grpc'].KeyAgentServiceStub.assert_called_with(channel)

    def test_secret_channel_is_removed_after_failed_format_operation(self):
        with mock.patch.object(secret, 'prepare_luks_secret_material_channel', return_value='/tmp/one-shot-secret'):
            with mock.patch.object(secret.os, 'unlink') as unlink:
                with self.assertRaisesRegex(RuntimeError, 'format failure'):
                    with secret.luks_secret_channel('d3JhcHBlZA==') as path:
                        self.assertEqual('/tmp/one-shot-secret', path)
                        raise RuntimeError('format failure')
        unlink.assert_called_once_with('/tmp/one-shot-secret')


if __name__ == '__main__':
    unittest.main()

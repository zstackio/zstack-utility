# -*- coding: utf-8 -*-
from unittest.mock import MagicMock, patch

from zstacklib.utils import http, jsonobject
from kvmagent.plugins import virtualrouter_plugin


def test_zstac_89819_set_bootstrap_info_retries_transient_socket_error():
    plugin = virtualrouter_plugin.VirtualRouterPlugin()
    attempts = []
    sent_payloads = []

    def _make_sock(*_args, **_kwargs):
        idx = len(attempts)
        attempts.append(idx)
        sock = MagicMock()
        sock.getsockopt.return_value = 64
        if idx == 0:
            sock.connect.side_effect = ConnectionRefusedError('socket not ready')
        else:
            sock.sendall.side_effect = lambda data: sent_payloads.append(data)
        return sock

    req = {
        http.REQUEST_BODY: jsonobject.dumps({
            'socketPath': '/var/lib/libvirt/qemu/vr.sock',
            'bootStrapInfoTimeout': 5,
            'info': {'vyosPassword': 'pw'},
        })
    }

    with patch.object(virtualrouter_plugin.socket, 'socket', side_effect=_make_sock), \
         patch.object(virtualrouter_plugin.time, 'sleep'):
        rsp = jsonobject.loads(plugin.set_bootstrap_info(req))

    assert rsp.success is True
    assert len(attempts) == 2
    assert len(sent_payloads) == 1
    assert len(sent_payloads[0]) % 64 == 0
    assert b'"vyosPassword": "pw"' in sent_payloads[0] or b'"vyosPassword":"pw"' in sent_payloads[0]

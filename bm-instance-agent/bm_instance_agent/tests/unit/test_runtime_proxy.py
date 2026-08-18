import os
import shutil
import socket
import stat
import tempfile
import threading
import time
import unittest
import json

from bm_instance_agent import runtime


class _UnixSocketResponder(threading.Thread):

    def __init__(self, socket_path, raw_response):
        super(_UnixSocketResponder, self).__init__()
        self.socket_path = socket_path
        self.raw_response = raw_response
        self.daemon = True
        self.error = None
        self.request_bytes = None

    def run(self):
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
            server.bind(self.socket_path)
            server.listen(1)
            conn, _ = server.accept()
            try:
                conn.settimeout(1)
                self.request_bytes = self._read_request(conn)
                try:
                    conn.sendall(self.raw_response)
                except socket.error as err:
                    if getattr(err, 'errno', None) != 32:
                        raise
            finally:
                conn.close()
        except Exception as err:
            self.error = err
        finally:
            server.close()

    @staticmethod
    def _read_request(conn):
        chunks = []
        headers = None
        content_length = 0
        while True:
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                return b''.join(chunks)
            if not chunk:
                break
            chunks.append(chunk)
            data = b''.join(chunks)
            if headers is None and b'\r\n\r\n' in data:
                headers, body = data.split(b'\r\n\r\n', 1)
                for line in headers.split(b'\r\n'):
                    if line.lower().startswith(b'content-length:'):
                        content_length = int(line.split(b':', 1)[1].strip())
                        break
                if len(body) >= content_length:
                    return data
            elif headers is not None:
                body = data.split(b'\r\n\r\n', 1)[1]
                if len(body) >= content_length:
                    return data
        return b''.join(chunks)


class _FakeHttpResponse(object):

    def __init__(self, body, content_length=None):
        self._body = body
        self._content_length = content_length

    def getheader(self, name):
        if name.lower() == 'content-length' and self._content_length is not None:
            return str(self._content_length)
        return None

    def read(self, amount=None):
        if amount is None:
            return self._body
        return self._body[:amount]

    def close(self):
        return None


class TestRuntimeProxy(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.socket_path = os.path.join(self.temp_dir, 'runtime.sock')
        self.mountinfo_path = os.path.join(self.temp_dir, 'mountinfo')
        self.responders = []
        self.manager = runtime.RuntimeManager(
            socket_path=self.socket_path,
            connect_timeout=1,
            read_timeout=1,
            require_root_ownership=False)
        self.manager.MOUNTINFO_PATH = self.mountinfo_path
        with open(self.mountinfo_path, 'w') as stream:
            stream.write('')

    def tearDown(self):
        for responder in self.responders:
            responder.join(1)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_capabilities_returns_json_body(self):
        self._write_mountinfo(
            '36 24 0:32 /models /zstack-runtime/model ro,relatime - fuse.juicefs juicefs ro\n')
        responder = self._start_server(
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'Content-Length: 64\r\n\r\n'
            b'{"apiVersion":"1.0.0","supportedWorkloadSpecVersions":["1.1.0"]}')

        status, body = self.manager.get_capabilities()

        self.assertEqual(200, status)
        self.assertEqual('1.0.0', body['apiVersion'])
        self.assertEqual(['1.1.0'], body['supportedWorkloadSpecVersions'])
        self._assert_responder_completed(responder)

    def test_inspect_allocation_preserves_frozen_response_shape(self):
        body = b'{"allocationUuid":"allocation-001","generation":7}'
        self._write_mountinfo(
            '36 24 0:32 /model\\040space /zstack-runtime/model\\040space ro,relatime - fuse.juicefs JuiceFS ro\n')
        responder = self._start_server(
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'Content-Length: %d\r\n\r\n%s' % (len(body), body))

        status, body = self.manager.inspect_allocation('allocation-001')

        self.assertEqual(200, status)
        self.assertEqual('allocation-001', body['allocationUuid'])
        self.assertEqual(7, body['generation'])
        self.assertNotIn('instanceMountFacts', body)
        self._assert_responder_completed(responder)

    def test_mount_source_name_does_not_impersonate_juicefs(self):
        self._write_mountinfo(
            '36 24 0:32 /models /zstack-runtime/model ro,relatime - ext4 juicefs-backup ro\n')

        self.assertEqual(
            [], self.manager.get_runtime_mount_facts()['juicefsReadOnlyMounts'])

    def test_runtime_error_passthrough(self):
        error_body = {
            'code': 'BMR-GENERATION-0001',
            'message': 'generation 6 is older than local generation 7',
            'retryable': False,
            'owner': 'ControlPlane',
            'requestId': 'request-start-stale',
            'details': {'requestedGeneration': 6, 'localGeneration': 7},
            'observedAt': '2026-08-14T02:01:00Z'
        }
        raw_error_body = json.dumps(error_body, separators=(',', ':')).encode('utf-8')
        responder = self._start_server(
            b'HTTP/1.1 409 Conflict\r\n'
            b'Content-Type: application/json\r\n'
            b'Content-Length: %d\r\n\r\n%s' % (len(raw_error_body), raw_error_body))

        status, body = self.manager.start_allocation(
            'allocation-001',
            {'requestId': 'request-start-stale', 'generation': 6})

        self.assertEqual(409, status)
        self.assertEqual(error_body, body)
        self._assert_responder_completed(responder)

    def test_invalid_json_response_maps_to_proxy_error(self):
        response = _FakeHttpResponse(b'not-json', content_length=8)

        self.assertRaises(
            runtime.RuntimeProxyError,
            self.manager._read_response_body,
            response,
            'request-invalid-json')

    def test_oversized_response_maps_to_proxy_error(self):
        oversized = b'a' * (self.manager.MAX_RESPONSE_BYTES + 1)
        responder = self._start_server(
            b'HTTP/1.1 200 OK\r\n'
            b'Content-Type: application/json\r\n'
            b'Content-Length: %d\r\n\r\n%s' % (len(oversized), oversized))

        self.assertRaises(runtime.RuntimeProxyError, self.manager.get_capabilities)
        self._assert_responder_completed(responder)

    def test_request_size_limit_uses_request_error_code(self):
        response_body = (
            b'{"requestId":"request-prepare-001","allocationUuid":"allocation-001",'
            b'"generation":7,"phase":"Prepared","changed":true,'
            b'"observedAt":"2026-08-14T02:00:00Z"}')
        responder = self._start_server(
            b'HTTP/1.1 201 Created\r\n'
            b'Content-Type: application/json\r\n'
            b'Content-Length: %d\r\n\r\n%s' % (len(response_body), response_body))
        payload = {
            'requestId': 'request-prepare-001',
            'generation': 7,
            'workloadSpec': {'allocationUuid': 'allocation-001', 'generation': 7}
        }

        status, body = self.manager.prepare_allocation('allocation-001', payload)

        self.assertEqual(201, status)
        self.assertEqual(7, body['generation'])
        self.assertTrue(responder.request_bytes.startswith(
            b'PUT /v1/allocations/allocation-001/prepare HTTP/1.1\r\n'))
        request_payload = json.loads(
            responder.request_bytes.split(b'\r\n\r\n', 1)[1].decode('utf-8'))
        self.assertEqual(payload, request_payload)
        self._assert_responder_completed(responder)

        payload = {'blob': 'a' * (self.manager.MAX_REQUEST_BYTES + 1)}

        try:
            self.manager.reconcile(payload)
            self.fail('expected RuntimeProxyError')
        except runtime.RuntimeProxyError as err:
            self.assertEqual('BMR-REQUEST-0002', err.code)
            self.assertEqual(413, err.status)

    def test_symlink_socket_path_is_rejected_before_connect(self):
        target_path = os.path.join(self.temp_dir, 'real.sock')
        with open(target_path, 'w') as stream:
            stream.write('not-a-socket')
        os.symlink(target_path, self.socket_path)

        try:
            self.manager.get_capabilities()
            self.fail('expected RuntimeProxyError')
        except runtime.RuntimeProxyError as err:
            self.assertEqual('BMR-PROXY-0001', err.code)
            self.assertIn('not a unix socket', err.message)

    def test_regular_file_socket_path_is_rejected_before_connect(self):
        with open(self.socket_path, 'w') as stream:
            stream.write('not-a-socket')

        try:
            self.manager.get_capabilities()
            self.fail('expected RuntimeProxyError')
        except runtime.RuntimeProxyError as err:
            self.assertEqual('BMR-PROXY-0001', err.code)
            self.assertIn('not a unix socket', err.message)

    def test_group_writable_socket_directory_is_rejected(self):
        class _RootOwnedGroupWritablePath(object):
            st_uid = 0
            st_mode = stat.S_IFDIR | 0o770

        real_lstat = runtime.os.lstat
        runtime.os.lstat = lambda path: _RootOwnedGroupWritablePath()
        try:
            try:
                self.manager._validate_root_owned_path(self.temp_dir, 'request-1')
                self.fail('expected RuntimeProxyError')
            except runtime.RuntimeProxyError as err:
                self.assertEqual('BMR-PROXY-0001', err.code)
                self.assertIn('group/world-writable', err.message)
        finally:
            runtime.os.lstat = real_lstat

    def test_non_directory_parent_is_rejected_before_connect(self):
        manager = runtime.RuntimeManager(
            socket_path=os.path.join(self.temp_dir, 'nested', 'runtime.sock'),
            connect_timeout=1,
            read_timeout=1,
            require_root_ownership=False)
        with open(os.path.join(self.temp_dir, 'nested'), 'w') as stream:
            stream.write('not-a-dir')

        try:
            manager.get_capabilities()
            self.fail('expected RuntimeProxyError')
        except runtime.RuntimeProxyError as err:
            self.assertEqual('BMR-PROXY-0001', err.code)
            self.assertIn('directory is invalid', err.message)

    def _start_server(self, raw_response):
        responder = _UnixSocketResponder(self.socket_path, raw_response)
        responder.start()
        self.responders.append(responder)
        deadline = time.time() + 1
        while time.time() < deadline:
            if os.path.exists(self.socket_path):
                break
            time.sleep(0.01)
        return responder

    def _write_mountinfo(self, content):
        with open(self.mountinfo_path, 'w') as stream:
            stream.write(content)

    def _assert_responder_completed(self, responder):
        responder.join(1)
        self.assertFalse(responder.is_alive())
        self.assertIsNone(responder.error)

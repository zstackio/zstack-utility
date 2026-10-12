"""Memory optimization wire_transport behavior tests.

Migrated from the legacy Agent test module; all methods remain discovered by pytest.
"""

from tests.unit.kvmagent.memory_optimization_test_support import *
from tests.unit.kvmagent.memory_optimization_test_support import _OMIT_POLICY_MODE
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.kvmagent]

class TestMemoryOptimizationWireTransport(MemoryOptimizationTestBase):
    def test_writeback_candidates_merge_readonly_resource_and_identity_snapshots(self):
        calls = []
        def service(action, command):
            calls.append(action)
            if action == 'backend-state':
                return {'backend_resource': {'resource_uuid': 'owned-resource'}}
            return {'configured': {'device': '/dev/vdb'}, 'identity_qualified': True,
                    'ownership_generation': 'owned-resource', 'effective': {'identity': {'boot_id': 'boot'}}}
        plugin = MemoryOptimizationPlugin(service_call=service)
        plugin.host_uuid = 'host-1'
        command = {'hostUuid': 'host-1'}
        with patch.object(plugin, '_request_body', return_value=command), \
             patch.object(plugin, '_reply', side_effect=lambda result: result), \
             patch.object(memory_optimization, 'probe_writeback_backends', return_value={
                 'hostUuid': 'host-1', 'status': 'AVAILABLE', 'candidates': []}) as probe:
            result = plugin.writeback_backends({})
        self.assertTrue(result['success'])
        self.assertEqual(['backend-state', 'backend-view'], calls)
        self.assertEqual('owned-resource', probe.call_args[0][1]['backend_resource']['resource_uuid'])
        self.assertEqual({'device': '/dev/vdb'}, probe.call_args[0][2])
    def test_state_recovers_current_boot_ksm_only_after_go_socket_failure(self):
        """Kylin KSM remains observable when the optional Go service is absent."""
        root = tempfile.mkdtemp(prefix='state-ksm-only-')
        plugin, command, _path = self._real_applied_ksm_fixture(root, 17)
        plugin.service_call = lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError(errno.ENOENT, 'optional Go service is absent'))
        response = json.loads(plugin.state({'body': json.dumps({
            'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Succeeded', response['status'])
        self.assertTrue(response['success'])
        self.assertEqual(17, response['appliedRevision'])
        self.assertTrue(response['state'].get('ksmOnly'))
        self.assertFalse(response['state']['safeToRemove'])
        self.assertNotIn('reason', response)
        self.assertEqual('ABI_INCOMPLETE', response['capabilities']['zramReasonCode'])
    def test_ksm_fallback_does_not_mask_http_error_response(self):
        root = tempfile.mkdtemp(prefix='state-ksm-http-error-')
        plugin, _command, _path = self._real_applied_ksm_fixture(root, 18)
        error_response = {'success': False, 'status': 'Unknown', 'state': {},
                          'reason': 'service returned HTTP 503', '_http_status': 503}
        with patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(plugin, '_dispatch', return_value=error_response):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': 'state-observation'})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        readback.assert_not_called()
    def test_real_ksm_only_apply_journal_then_fresh_state_query(self):
        """Exercise apply/journal/active-control/state without shortcut mocks."""
        root = tempfile.mkdtemp(prefix='real-ksm-roundtrip-')
        plugin, command, path = self._real_applied_ksm_fixture(root, 31)
        first = plugin.apply(command)
        second = plugin.apply(command)
        plugin.service_call = lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError(errno.ENOENT, 'optional Go service is absent'))
        response = json.loads(plugin.state({'body': json.dumps({
            'hostUuid': 'host-1', 'operationUuid': 'fresh-state-1'})}))
        self.assertTrue(first['success'])
        self.assertEqual('Succeeded', first['status'])
        self.assertEqual(first, second)
        self.assertEqual('APPLIED', json.load(open(path))['stage'])
        self.assertEqual('Succeeded', response['status'])
        self.assertTrue(response['success'])
        self.assertEqual(31, response['appliedRevision'])
        self.assertFalse(response['state']['safeToRemove'])
    def test_state_keeps_unknown_for_stale_ksm_journal_after_go_socket_failure(self):
        root = tempfile.mkdtemp(prefix='state-ksm-stale-')
        plugin = self._ksm_only_state_plugin(root)
        command = {'hostUuid': 'host-1', 'operationUuid': 'ksm-state-stale',
                   'desiredRevision': 18,
                   'policy': {'ksm': {'enabled': True}, 'zram': {'enabled': False}}}
        plugin._set_active_control(command['operationUuid'])
        plugin._record_operation(command, 'APPLIED',
                                 {'success': True, 'status': 'Succeeded',
                                  'state': {'ksmOnly': True}})
        path = os.path.join(root, command['operationUuid'] + '.json')
        with open(path) as stream:
            record = json.load(stream)
        record['bootId'] = 'different-boot'
        with open(path, 'w') as stream:
            json.dump(record, stream)
        with patch.object(plugin, '_ksm_readback_matches', return_value=True) as readback, \
                patch.object(plugin, '_dispatch', side_effect=socket.error(errno.ENOENT, 'missing socket')), \
                patch.object(subprocess, 'check_output', return_value=b'run=1\n'):
            response = json.loads(plugin.state({'body': json.dumps({
                'hostUuid': 'host-1', 'operationUuid': command['operationUuid']})}))
        self.assertEqual('Unknown', response['status'])
        self.assertFalse(response['success'])
        self.assertFalse(response['state']['safeToRemove'])
        readback.assert_not_called()
    def test_local_service_uses_http_over_unix_socket_and_normalizes_response(self):
        path = tempfile.mktemp(prefix='memory-optimization-', suffix='.sock')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(1)

        def serve_once():
            conn, _ = listener.accept()
            request = b''
            while b'\r\n\r\n' not in request:
                request += conn.recv(4096)
            header, body = request.split(b'\r\n\r\n', 1)
            size = next((int(line.split(b':', 1)[1]) for line in header.split(b'\r\n')
                         if line.lower().startswith(b'content-length:')), 0)
            while len(body) < size:
                body += conn.recv(size - len(body))
            self.assertTrue(request.startswith(b'GET /v1/status HTTP/1.1'))
            body = json.dumps({'status': 'Succeeded', 'state': {'revision': 3}}).encode('utf-8')
            conn.sendall(('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                          'Content-Length: %d\r\nConnection: close\r\n\r\n' % len(body)).encode('ascii') + body)
            conn.close()

        thread = threading.Thread(target=serve_once)
        thread.daemon = True
        thread.start()
        try:
            plugin = MemoryOptimizationPlugin()
            plugin.configure({'hostUuid': 'host-1', 'socketPath': path})
            response = json.loads(plugin.state({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'op-1'})}))
            self.assertEqual('Succeeded', response['status'])
            self.assertEqual('op-1', response['operationUuid'])
        finally:
            thread.join(2)
            listener.close()
            if os.path.exists(path):
                os.unlink(path)
    def test_local_service_uses_per_request_communication_budget_and_query_contract(self):
        calls = []

        class Response(object):
            status = 200
            def read(self, _limit):
                return b'{"status":"Succeeded"}'

        class Connection(object):
            def __init__(self, path, timeout):
                calls.append(('init', path, timeout))
            def request(self, method, path, body=None, headers=None):
                calls.append(('request', method, path, body))
            def getresponse(self):
                return Response()
            def close(self):
                pass

        plugin = MemoryOptimizationPlugin()
        plugin.configure({'socketPath': '/tmp/memory-service.sock'})
        with patch.object(memory_optimization, '_UnixHTTPConnection', Connection):
            plugin._call_local_service('apply', {
                'operationUuid': 'op-1', 'communication': {
                    'requestBytes': 4096, 'responseBytes': 8192,
                    'communicationSeconds': 7}, 'request_id': 'op-1'})
            plugin._call_local_service('state', {
                'hostUuid': 'host-1', 'communication': {
                    'requestBytes': 4096, 'responseBytes': 8192,
                    'communicationSeconds': 3}})
        self.assertEqual(('init', '/tmp/memory-service.sock', 7), calls[0])
        self.assertEqual(('init', '/tmp/memory-service.sock', 3), calls[2])
        self.assertEqual('/v1/zram/tuning', calls[1][2])
        self.assertEqual('/v1/status', calls[3][2])
    def test_readonly_accounting_and_operations_queries_preserve_report_and_filters(self):
        calls = []
        report = {'schema_version': 2, 'quality': 'atomic_inventory_identity_checked',
                  'vms': {}, 'inventory': {'schema_version': 2}}
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload:
                calls.append((action, payload)) or (report if action == 'accounting' else {'items': []}))
        plugin.configure({'hostUuid': 'host-1'})
        accounting = json.loads(plugin.accounting({'body': json.dumps({
            'hostUuid': 'host-1', 'vmUuid': 'vm-1',
            'communication': {'requestBytes': 1024, 'responseBytes': 4096,
                              'communicationSeconds': 30}})}))
        operations = json.loads(plugin.operations({
            'body': json.dumps({
                'hostUuid': 'host-1', 'operationId': 'op-1', 'start': 0,
                'limit': 100, 'status': 'APPLIED'})
        }))
        self.assertEqual(report, accounting['state'])
        self.assertEqual([], operations['state']['items'])
        self.assertEqual('accounting', calls[0][0])
        self.assertEqual('operations', calls[1][0])
    def test_readonly_queries_reject_identity_mismatch_without_service_call(self):
        calls = []
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: calls.append(args))
        plugin.configure({'hostUuid': 'host-1'})
        response = json.loads(plugin.accounting({'body': json.dumps({'hostUuid': 'other'})}))
        self.assertFalse(response['success'])
        self.assertEqual([], calls)
    def test_accounting_uint64_identity_is_exact_decimal_string_on_wire(self):
        large = 15704573862423239137
        report = {'inventory': {'pool_generation': large, 'sequence': 477777,
                                'owners': [{'cgroup_id': large}]},
                  'vms': {'vm-1': {'identity': {'cgroup_inode': large},
                                    'metrics': {'ram_payload_bytes': 8192}}}}
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: report)
        plugin.configure({'hostUuid': 'host-1'})
        reply = json.loads(plugin.accounting({'body': '{"hostUuid":"host-1"}'}))
        state = reply['state']
        self.assertEqual(str(large), state['inventory']['pool_generation'])
        self.assertEqual('477777', state['inventory']['sequence'])
        self.assertEqual(str(large), state['inventory']['owners'][0]['cgroup_id'])
        self.assertEqual(str(large), state['vms']['vm-1']['identity']['cgroup_inode'])
        self.assertEqual(8192, state['vms']['vm-1']['metrics']['ram_payload_bytes'])
        self.assertEqual(large, report['inventory']['pool_generation'])
    def test_accounting_rejects_already_rounded_identity(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: {
            'inventory': {'pool_generation': float(15704573862423239137)}})
        plugin.configure({'hostUuid': 'host-1'})
        reply = json.loads(plugin.accounting({'body': '{"hostUuid":"host-1"}'}))
        self.assertFalse(reply['success'])
        self.assertIn('INVALID_ACCOUNTING_IDENTITY', reply['reason'])
    def test_accounting_identity_numeric_boundary_and_canonical_format(self):
        convert = memory_optimization._accounting_wire_identity
        for invalid in (True, -1, 1 << 64, '01', '1\n', '1.0', '1e9'):
            with self.assertRaises(ValueError):
                convert({'sequence': invalid})
        self.assertEqual({'sequence': '18446744073709551615'},
                         convert({'sequence': (1 << 64) - 1}))
        self.assertEqual({'sequence': '0'}, convert({'sequence': '0'}))
    def test_readonly_service_http_failure_cannot_become_success(self):
        plugin = MemoryOptimizationPlugin(
            service_call=lambda action, payload: {'success': True, '_http_status': 500})
        plugin.configure({'hostUuid': 'host-1'})
        for method, body_key in ((plugin.accounting, 'hostUuid'),
                                 (plugin.operations, 'hostUuid')):
            response = json.loads(method({'body': json.dumps({body_key: 'host-1'})}))
            self.assertFalse(response['success'])
            self.assertEqual('Unknown', response['status'])
    def test_local_service_decodes_chunked_large_json_response(self):
        path = tempfile.mktemp(prefix='memory-optimization-chunked-', suffix='.sock')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(1)
        payload = json.dumps({'status': 'Succeeded', 'state': {
            'vms': {'vm-%04d' % i: {'reason': 'x' * 64} for i in range(80)}}}).encode('utf-8')

        def serve_once():
            conn, _ = listener.accept()
            request = b''
            while b'\r\n\r\n' not in request:
                request += conn.recv(4096)
            header, body = request.split(b'\r\n\r\n', 1)
            size = next((int(line.split(b':', 1)[1]) for line in header.split(b'\r\n')
                         if line.lower().startswith(b'content-length:')), 0)
            while len(body) < size:
                body += conn.recv(size - len(body))
            first, second = payload[:len(payload) // 2], payload[len(payload) // 2:]
            header = ('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                      'Transfer-Encoding: chunked\r\nConnection: close\r\n\r\n').encode('ascii')
            conn.sendall(header)
            for chunk in (first, second):
                conn.sendall(('%x\r\n' % len(chunk)).encode('ascii') + chunk + b'\r\n')
            conn.sendall(b'0\r\n\r\n')
            conn.close()

        thread = threading.Thread(target=serve_once)
        thread.daemon = True
        thread.start()
        try:
            plugin = MemoryOptimizationPlugin()
            plugin.configure({'socketPath': path})
            result = plugin._call_local_service('state', {})
            self.assertEqual('Succeeded', result['status'])
            self.assertEqual(80, len(result['state']['vms']))
        finally:
            thread.join(2)
            listener.close()
            if os.path.exists(path):
                os.unlink(path)

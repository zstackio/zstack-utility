import base64
import hashlib
import json

import pytest

from kvmagent.plugins import hccn_bootstrap as bootstrap


def test_host_capability_has_no_vm_dependency():
    def no_lookup(_):
        raise AssertionError('host probe must not look up a VM')
    result = bootstrap.dispatch(json.dumps({'hccnBootstrap': {
        'schemaVersion': 1, 'operation': 'capability', 'capabilityScope': 'host'}}), no_lookup)
    assert result['success'] is True
    assert result['hccnBootstrap']['exitCode'] is None
    assert result['hccnBootstrap']['result']['releaseProbeVersion'] == 1
    assert set(result['hccnBootstrap']['result']['operations']) == set(bootstrap.OPERATIONS)


@pytest.mark.parametrize('wire', [
    {'schemaVersion': True, 'operation': 'capability', 'capabilityScope': 'host'},
    {'schemaVersion': 2, 'operation': 'capability', 'capabilityScope': 'host'},
    {'schemaVersion': 1, 'operation': 'seal'},
    {'schemaVersion': 1, 'operation': 'gate'},
    {'schemaVersion': 1, 'operation': 'capability'},
    {'schemaVersion': 1, 'operation': 'capability', 'capabilityScope': 'host', 'path': '/tmp/x'},
])
def test_unsupported_never_executes_or_falls_back(wire):
    assert bootstrap.dispatch(json.dumps({'hccnBootstrap': wire}), lambda _: pytest.fail('VM lookup'))['success'] is False


def test_duplicate_keys_are_not_overwritten():
    raw = '{"hccnBootstrap":{"schemaVersion":1,"schemaVersion":1,"operation":"capability","capabilityScope":"host"}}'
    assert bootstrap.dispatch(raw, lambda _: pytest.fail('VM lookup'))['success'] is False


VM = 'a' * 32
BOOT = '11111111-2222-3333-4444-555555555555'


def context():
    return dict(schemaVersion=1, groupUuid='1' * 32, instanceUuid='2' * 32,
                vmUuid=VM, attemptId='3' * 32, epoch=1, bootId=BOOT, nodeRank=0, nnodes=2)


class Domain:
    def name(self):
        return VM

    def UUIDString(self):
        return 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

    def ID(self):
        return 7

    def isActive(self):
        return True


class RawQga:
    def __init__(self):
        self.calls = []
        self.files = {name: (name + '\n').encode() + b'\xff\xfe' for name in bootstrap.PROTECTED}
        self.artifact = {'architecture': 'aarch64', 'files': {
            name: hashlib.sha256(raw).hexdigest() for name, raw in self.files.items()}}
        self.marker = dict(self.artifact, schemaVersion=1, required=True, vendor='huawei', mode='distributed')
        self.handles = {}
        self.read_override = None
        self.close_error = False
        self.status_override = None
        self.result_override = None
        self.exec_error = False
        self.exit_code = 0

    def qemuAgentCommand(self, domain, raw, timeout, flags):
        command = json.loads(raw)
        self.calls.append(command)
        assert 0 < timeout <= 3
        operation, args = command['execute'], command['arguments']
        if operation == 'guest-file-open':
            assert args['mode'] == 'r'
            name = args['path'].removeprefix(bootstrap.APP_DIR + '/')
            assert name in bootstrap.PROTECTED + (bootstrap.MARKER,)
            data = json.dumps(self.marker).encode() if name == bootstrap.MARKER else self.files[name]
            handle = len(self.calls)
            self.handles[handle] = data
            value = handle
        elif operation == 'guest-file-read':
            if self.read_override is not None:
                value = self.read_override
            else:
                data = self.handles[args['handle']]
                block, rest = data[:args['count']], data[args['count']:]
                self.handles[args['handle']] = rest
                value = {'count': len(block), 'eof': not rest,
                         'buf-b64': base64.b64encode(block).decode()}
        elif operation == 'guest-file-close':
            if self.close_error:
                raise RuntimeError('close failed first cause')
            del self.handles[args['handle']]
            value = {}
        elif operation == 'guest-exec':
            if self.exec_error:
                raise RuntimeError('libvirt failure args[%s]' % raw)
            assert args['path'] == '/usr/bin/python3'
            assert args['arg'][0] == bootstrap.APP_DIR + '/aios_hccn_bootstrap.py'
            assert args['arg'][2:] == ['--timeout', '900']
            assert args['capture-output'] is True
            assert args['env'] == ['PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                                   'PYTHONDONTWRITEBYTECODE=1']
            op = args['arg'][1]
            if op == 'capability':
                assert 'input-data' not in args
                self.result = dict(self.artifact, success=True, schemaVersion=1, required=True,
                                   bootId=BOOT, operations=list(bootstrap.OPERATIONS[1:]) + ['gate', 'seal'])
            else:
                payload = json.loads(base64.b64decode(args['input-data']))
                self.result = dict(success=True, schemaVersion=1,
                                   context={k: payload[k] for k in bootstrap.CONTEXT}, phase='pending')
                if op in ('abort', 'quiesce'):
                    self.result.update(phase='aborted', quiesced=True)
                if op in ('release', 'activate'):
                    self.result.update(phase='released', activated=True)
            if self.result_override is not None:
                self.result = self.result_override
            value = {'pid': 102}
        elif operation == 'guest-exec-status':
            assert args == {'pid': 102}
            value = self.status_override if self.status_override is not None else {
                'exited': True, 'exitcode': self.exit_code,
                'out-data': base64.b64encode(json.dumps(self.result).encode()).decode(), 'err-data': ''}
        else:
            raise AssertionError('unexpected QGA command: %s' % operation)
        return json.dumps({'return': value})

    def count(self, operation):
        return sum(call['execute'] == operation for call in self.calls)


@pytest.fixture
def raw_qga(monkeypatch):
    import sys
    qga = RawQga()
    monkeypatch.setitem(sys.modules, 'libvirt_qemu', qga)
    return qga


def request(qga, operation='begin', **changes):
    wire = dict(schemaVersion=1, operation=operation, expectedArtifact=qga.artifact)
    if operation == 'capability':
        wire['capabilityScope'] = 'guest'
    else:
        wire['payload'] = context()
    wire.update(changes)
    return json.dumps(dict(vmUuid=VM, vendors=['Huawei'], hccnBootstrap=wire))


def test_raw_bytes_sha_and_original_stdin_reach_fixed_cli(raw_qga):
    raw = request(raw_qga)
    result = bootstrap.dispatch(raw, lambda _: Domain())
    assert result['success'] is True, result
    assert result['hccnBootstrap']['result']['context'] == context()
    assert result['hccnBootstrap']['exitCode'] == 0
    assert raw_qga.count('guest-file-open') == raw_qga.count('guest-file-close') == 6
    assert raw_qga.count('guest-exec') == raw_qga.count('guest-exec-status') == 1
    commands = [c['execute'] for c in raw_qga.calls]
    assert commands.index('guest-exec') > max(i for i, op in enumerate(commands) if op == 'guest-file-close')
    assert not raw_qga.handles


@pytest.mark.parametrize('number', ['1e400', '-1e400'])
@pytest.mark.parametrize('nested', [False, True])
def test_overflow_guest_json_returns_serializable_failure(raw_qga, number, nested):
    extra = '{"items":[' + number + ']}' if nested else number
    stdout = (json.dumps(dict(success=True, schemaVersion=1, context=context(), phase='pending'))[:-1]
              + ',"extra":' + extra + '}').encode()
    raw_qga.status_override = dict(exited=True, exitcode=0,
                                  **{'out-data': base64.b64encode(stdout).decode(), 'err-data': ''})

    response = bootstrap.dispatch(request(raw_qga), lambda _: Domain())

    assert response['success'] is False
    envelope = response['hccnBootstrap']
    assert envelope['operation'] == 'begin'
    assert envelope['exitCode'] == 0
    assert envelope['result'] is None
    assert envelope['errorCount'] == len(envelope['errors']) == 1
    assert 'non-finite JSON' in envelope['errors'][0]['reason']
    assert response['error'] == envelope['errors'][0]['reason']
    assert json.loads(bootstrap.serialize_response(response)) == response
    assert raw_qga.count('guest-exec') == raw_qga.count('guest-exec-status') == 1


@pytest.mark.parametrize('number', ['1.7976931348623157e308', '-1.7976931348623157e308', '1e-400'])
def test_finite_guest_json_remains_successful(raw_qga, number):
    stdout = (json.dumps(dict(success=True, schemaVersion=1, context=context(), phase='pending'))[:-1]
              + ',"extra":{"items":[' + number + ']}}').encode()
    raw_qga.status_override = dict(exited=True, exitcode=0,
                                  **{'out-data': base64.b64encode(stdout).decode(), 'err-data': ''})

    response = bootstrap.dispatch(request(raw_qga), lambda _: Domain())

    assert response['success'] is True
    assert response['hccnBootstrap']['result']['extra']['items'] == [float(number)]
    assert response['hccnBootstrap']['errorCount'] == 0
    assert json.loads(bootstrap.serialize_response(response)) == response


def test_guest_capability_obtains_first_boot_without_existing_context(raw_qga):
    result = bootstrap.dispatch(request(raw_qga, 'capability'), lambda _: Domain())
    assert result['success'] is True, result
    assert result['hccnBootstrap']['result']['bootId'] == BOOT
    assert 'context' not in result['hccnBootstrap']['result']


@pytest.mark.parametrize('mutation', ['sha', 'required', 'marker_arch', 'marker_files'])
def test_bad_artifact_never_runs_even_stop(raw_qga, mutation):
    if mutation == 'sha':
        raw_qga.files['start.sh'] += b'tamper'
    elif mutation == 'required':
        raw_qga.marker['required'] = False
    elif mutation == 'marker_arch':
        raw_qga.marker['architecture'] = 'x86_64'
    else:
        raw_qga.marker['files'] = {}
    result = bootstrap.dispatch(request(raw_qga, 'abort'), lambda _: Domain())
    assert result['success'] is False
    assert raw_qga.count('guest-exec') == 0
    assert not raw_qga.handles


@pytest.mark.parametrize('reply', [
    {'count': 1, 'eof': True, 'buf-b64': '!!!!'},
    {'count': 2, 'eof': True, 'buf-b64': 'YQ=='},
    {'count': True, 'eof': True, 'buf-b64': 'YQ=='},
    {'count': 0, 'eof': False, 'buf-b64': ''},
    {'count': 0, 'eof': 1, 'buf-b64': ''},
    {'count': 65537, 'eof': True, 'buf-b64': ''},
])
def test_invalid_read_fails_and_closes_handle(raw_qga, reply):
    raw_qga.read_override = reply
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert raw_qga.count('guest-exec') == 0
    assert raw_qga.count('guest-file-close') == 1
    assert not raw_qga.handles


def test_read_and_close_failure_preserve_both_causes(raw_qga):
    raw_qga.read_override = {'count': 1, 'eof': True, 'buf-b64': ''}
    raw_qga.close_error = True
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['errorCount'] == 2
    assert result['hccnBootstrap']['errors'][0]['reason'] == 'QGA file read count mismatch'
    assert 'close failed first cause' in result['hccnBootstrap']['errors'][1]['reason']
    assert raw_qga.count('guest-exec') == 0


def test_partial_reads_preserve_non_utf8_bytes(raw_qga):
    data = b'\xff' * 131073
    raw_qga.files['start.sh'] = data
    raw_qga.artifact['files']['start.sh'] = hashlib.sha256(data).hexdigest()
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is True, result
    assert raw_qga.count('guest-file-read') == 8


@pytest.mark.parametrize('status', [
    {'exited': True, 'exitcode': 0, 'out-data': 'e30=', 'out-truncated': True},
    {'exited': True, 'signal': 9},
    {'exited': True, 'exitcode': True},
    {'exited': 1, 'exitcode': 0},
    {'exited': True, 'exitcode': 0, 'out-data': base64.b64encode(b'{"success":true').decode()},
    {'exited': True, 'exitcode': 0, 'out-data': '!!!!'},
])
def test_unproven_terminal_result_is_failure_with_no_resend(raw_qga, status):
    raw_qga.status_override = status
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['result'] is None
    assert raw_qga.count('guest-exec') == 1


def test_all_guest_causes_and_real_exit_code_survive(raw_qga):
    errors = [dict(stage='link', reason='link down original'), dict(stage='peer', reason='peer unreachable original')]
    raw_qga.result_override = dict(success=False, schemaVersion=1, errorCount=2, errors=errors)
    raw_qga.exit_code = 1
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['errors'] == errors
    assert result['hccnBootstrap']['errorCount'] == 2
    assert result['hccnBootstrap']['exitCode'] == 1
    assert result['error'] == errors[0]['reason']


def test_wrong_context_cannot_be_accepted(raw_qga):
    wrong = dict(context(), epoch=2)
    raw_qga.result_override = dict(success=True, schemaVersion=1, context=wrong, phase='pending')
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['exitCode'] == 0


def test_stop_does_not_require_gpu_ip_or_qmp(raw_qga, monkeypatch):
    monkeypatch.setattr(bootstrap.pci, 'get_strict_pci_passthrough_observation',
                        lambda _: pytest.fail('stop must not require healthy QMP'), raising=False)
    result = bootstrap.dispatch(request(raw_qga, 'abort', expectedGpuDevices=[{'serialNumber': ''}]), lambda _: Domain())
    assert result['success'] is True, result
    assert result['hccnBootstrap']['result']['quiesced'] is True


def test_unknown_process_deadline_does_not_resend(raw_qga, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(bootstrap.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(bootstrap.time, 'sleep', lambda _: clock.__setitem__(0, clock[0] + 1000))
    raw_qga.status_override = {'exited': False}
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['exitCode'] is None
    assert raw_qga.count('guest-exec') == 1


def test_libvirt_exception_does_not_disclose_stdin(raw_qga):
    raw_qga.exec_error = True
    payload = dict(context(), serviceYamlBase64=base64.b64encode(b'password: private-value').decode(),
                   configSha256=hashlib.sha256(b'password: private-value').hexdigest(), verificationDigest='a' * 64)
    raw = request(raw_qga, 'publish', payload=payload)
    result = bootstrap.dispatch(raw, lambda _: Domain())
    assert result['success'] is False
    text = json.dumps(result)
    assert 'private-value' not in text
    assert payload['serviceYamlBase64'] not in text
    assert 'libvirt failure' in text


@pytest.fixture
def actual_pci(monkeypatch):
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).parents[3] / 'zstacklib/zstacklib/utils/pci.py'
    spec = importlib.util.spec_from_file_location('zstacklib.utils._hccn_real_pci', str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(bootstrap, 'pci', module)
    return module


def pci_xml():
    rows = []
    for index, (host, guest) in enumerate(((0x42, 0x95), (0x43, 0x97), (0x44, 0x96))):
        rows.append('''<hostdev type="pci"><source><address domain="0x0000" bus="0x%02x" slot="0x00" function="0x0"/></source>
          <alias name="hostdev%s"/><address type="pci" domain="0x0000" bus="0x%02x" slot="0x00" function="0x0"/></hostdev>''' % (host, index, guest))
    return '<domain><devices>%s</devices></domain>' % ''.join(rows)


class PciDomain(Domain):
    def XMLDesc(self):
        return pci_xml()


def qmp_output():
    return '\n'.join('Bus %s, device 0, function 0:\n  id "hostdev%s"' % (bus, index)
                     for index, bus in enumerate((0x95, 0x97, 0x96)))


def devices():
    return [dict(npuId=npu, serialNumber='card-%s' % npu, guestPciAddress=bdf,
                 address='172.20.9.%s' % (10 + i), netmask='255.255.0.0', linkStatus='UP')
            for i, (npu, bdf) in enumerate(((4, '0000:97:00.0'), (7, '0000:95:00.0')))]


def snapshot_request(qga, op='snapshot'):
    return request(qga, op, expectedGpuDevices=[{'hostPciAddress': '0000:42:00.0'},
                                              {'hostPciAddress': '0000:43:00.0'}],
                   expectedNonGpuPciAddresses=['0000:44:00.0'])


def snapshot_result(qga):
    qga.result_override = dict(success=True, schemaVersion=1, context=context(), devices=devices())


def test_snapshot_uses_real_mapping_for_reordered_ids_and_non_gpu_dependency(raw_qga, actual_pci, monkeypatch):
    calls = []
    def query(vm_uuid, timeout=None):
        assert timeout == 5
        calls.append(vm_uuid)
        return 0, qmp_output(), ''
    monkeypatch.setattr(actual_pci, '_query_pci_info_by_qmp', query)
    snapshot_result(raw_qga)
    result = bootstrap.dispatch(snapshot_request(raw_qga), lambda _: PciDomain())
    assert result['success'] is True, result
    assert [d['hostPciAddress'] for d in result['hccnBootstrap']['devices']] == ['0000:43:00.0', '0000:42:00.0']
    assert [d['npuId'] for d in result['hccnBootstrap']['devices']] == [4, 7]
    assert all('hostPciAddress' not in d for d in result['hccnBootstrap']['result']['devices'])
    assert len(calls) == 2
    assert {c['execute'] for c in raw_qga.calls} == {'guest-file-open', 'guest-file-read', 'guest-file-close', 'guest-exec', 'guest-exec-status'}


@pytest.mark.parametrize('bad', ['missing', 'extra', 'duplicate_guest', 'duplicate_sn', 'empty_sn', 'bad_ip', 'duplicate_ip', 'bad_mask', 'bool_npu'])
def test_guest_set_is_exact_and_never_inferred_from_board_count(raw_qga, actual_pci, monkeypatch, bad):
    monkeypatch.setattr(actual_pci, '_query_pci_info_by_qmp', lambda _, timeout=None: (0, qmp_output(), ''))
    snapshot_result(raw_qga)
    ds = raw_qga.result_override['devices']
    if bad == 'missing':
        ds.pop()
    elif bad == 'extra':
        ds.append(dict(ds[0], guestPciAddress='0000:96:00.0', serialNumber='third', address='172.20.9.15'))
    elif bad == 'duplicate_guest':
        ds[1]['guestPciAddress'] = ds[0]['guestPciAddress']
    elif bad == 'duplicate_sn':
        ds[1]['serialNumber'] = ds[0]['serialNumber']
    elif bad == 'empty_sn':
        ds[0]['serialNumber'] = ''
    elif bad == 'bad_ip':
        ds[0]['address'] = '999.1.2.3'
    elif bad == 'duplicate_ip':
        ds[1]['address'] = ds[0]['address']
    elif bad == 'bad_mask':
        ds[0]['netmask'] = '255.0.255.0'
    else:
        ds[0]['npuId'] = True
    result = bootstrap.dispatch(snapshot_request(raw_qga), lambda _: PciDomain())
    assert result['success'] is False
    assert result['hccnBootstrap']['result'] is None


def test_only_explicit_fresh_native_sn_can_be_hard_assertion(raw_qga, actual_pci, monkeypatch):
    monkeypatch.setattr(actual_pci, '_query_pci_info_by_qmp', lambda _, timeout=None: (0, qmp_output(), ''))
    snapshot_result(raw_qga)
    raw = json.loads(snapshot_request(raw_qga))
    raw['hccnBootstrap']['expectedGpuDevices'][0]['serialNumber'] = 'trusted-but-conflicting'
    result = bootstrap.dispatch(json.dumps(raw), lambda _: PciDomain())
    assert result['success'] is False
    assert 'SN conflicts' in result['error']


def test_partial_qmp_fails_before_helper_and_never_stitches_observations(raw_qga, actual_pci, monkeypatch):
    calls = []
    def query(_, timeout=None):
        assert timeout == 5
        calls.append(1)
        return 0, 'Bus 149, device 0, function 0:\n id "hostdev0"', ''
    monkeypatch.setattr(actual_pci, '_query_pci_info_by_qmp', query)
    result = bootstrap.dispatch(snapshot_request(raw_qga), lambda _: PciDomain())
    assert result['success'] is False
    assert len(calls) == 1
    assert raw_qga.count('guest-exec') == 0


def test_visible_runtime_change_rejects_result(raw_qga, actual_pci, monkeypatch):
    monkeypatch.setattr(actual_pci, '_query_pci_info_by_qmp', lambda _, timeout=None: (0, qmp_output(), ''))
    snapshot_result(raw_qga)
    class Changed(PciDomain):
        def ID(self):
            return 8
    domains = iter([PciDomain(), Changed()])
    result = bootstrap.dispatch(snapshot_request(raw_qga), lambda _: next(domains))
    assert result['success'] is False
    assert 'runtime changed' in result['error']


def test_visible_alias_guest_reordering_rejects_result(raw_qga, actual_pci, monkeypatch):
    count = [0]
    def query(_, timeout=None):
        assert timeout == 5
        count[0] += 1
        output = qmp_output() if count[0] == 1 else qmp_output().replace('Bus 149', 'Bus 150')
        return 0, output, ''
    monkeypatch.setattr(actual_pci, '_query_pci_info_by_qmp', query)
    snapshot_result(raw_qga)
    result = bootstrap.dispatch(snapshot_request(raw_qga), lambda _: PciDomain())
    assert result['success'] is False
    assert 'guest address' in result['error']


def test_original_qga_class_methods_are_exercised_at_libvirt_boundary(raw_qga):
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).parents[3] / 'zstacklib/zstacklib/utils/qga.py'
    spec = importlib.util.spec_from_file_location('zstacklib.utils._hccn_real_qga', str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    qga = module.VmQga.__new__(module.VmQga)
    qga.domain, qga.supported_commands = Domain(), {}
    args = {'path': '/usr/bin/python3', 'arg': [bootstrap.APP_DIR + '/aios_hccn_bootstrap.py', 'capability', '--timeout', '900'],
            'capture-output': True, 'env': ['PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'PYTHONDONTWRITEBYTECODE=1']}
    assert qga.guest_exec(args) == {'pid': 102}
    status = qga.guest_exec_status(102)
    assert status['exitcode'] == 0
    assert json.loads(status['out-data'])['bootId'] == BOOT


@pytest.mark.parametrize('op', ['release', 'activate', 'publish'])
def test_missing_operation_specific_payload_is_rejected_before_exec(raw_qga, op):
    result = bootstrap.dispatch(request(raw_qga, op), lambda _: Domain())
    assert result['success'] is False
    assert raw_qga.count('guest-exec') == 0


def test_truncated_guest_error_keeps_reported_count_and_real_rc(raw_qga):
    original = dict(stage='output', reason='guest error collection exceeds limit')
    raw_qga.result_override = dict(success=False, schemaVersion=1, errorCount=123, errors=[original], truncated=True)
    raw_qga.exit_code = 1
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['exitCode'] == 1
    assert result['hccnBootstrap']['errorCount'] == 123
    assert result['hccnBootstrap']['errors'] == [original]
    assert result['hccnBootstrap']['truncated'] is True


def test_guest_payload_version_boolean_is_not_accepted_in_response(raw_qga):
    wrong = dict(context(), epoch=True)
    raw_qga.result_override = dict(success=True, schemaVersion=1, context=wrong, phase='pending')
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False


def test_malformed_stdout_preserves_real_exit_code_and_bounded_output(raw_qga):
    raw_qga.status_override = {'exited': True, 'exitcode': 2, 'out-data': base64.b64encode(b'bad stdout original').decode(),
                               'err-data': base64.b64encode(b'usage error original').decode()}
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['exitCode'] == 2
    error = result['hccnBootstrap']['errors'][0]
    assert error['stdout'] == 'bad stdout original'
    assert error['stderr'] == 'usage error original'


def test_qga_base64_wire_overhead_does_not_shrink_valid_guest_json_limit(raw_qga):
    reason = 'x' * 800000
    raw_qga.result_override = dict(success=False, schemaVersion=1, errorCount=1,
                                   errors=[dict(stage='peer', reason=reason)])
    raw_qga.exit_code = 1
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['exitCode'] == 1
    assert result['hccnBootstrap']['errors'][0]['reason'] == reason
    assert len(bootstrap.serialize_response(result).encode()) <= bootstrap.LIMIT


def test_guest_file_total_size_limit_closes_handle(raw_qga):
    raw_qga.files['start.sh'] = b'x' * (bootstrap.LIMIT + 1)
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert 'size limit' in result['error']
    assert raw_qga.count('guest-exec') == 0
    assert not raw_qga.handles


@pytest.mark.parametrize('field,value', [('out-truncated', 'false'), ('err-truncated', 1)])
def test_qga_terminal_flags_must_be_real_booleans(raw_qga, field, value):
    body = dict(success=True, schemaVersion=1, context=context(), phase='pending')
    status = dict(exited=True, exitcode=0, **{'out-data': base64.b64encode(json.dumps(body).encode()).decode()})
    status[field] = value
    raw_qga.status_override = status
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['exitCode'] == 0


def test_oversized_stdout_is_explicitly_truncated(raw_qga):
    raw_qga.status_override = {'exited': True, 'exitcode': 0,
                               'out-data': base64.b64encode(b'x' * (bootstrap.LIMIT + 1)).decode()}
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert result['hccnBootstrap']['exitCode'] == 0
    assert result['hccnBootstrap']['truncated'] is True


def test_standard_qga_error_retains_original_class_description_and_command(monkeypatch):
    import sys
    import time
    import types
    description = 'guest-exec has been disabled by the administrator'
    fake = types.SimpleNamespace(qemuAgentCommand=lambda *args: json.dumps({
        'error': {'class': 'CommandNotFound', 'desc': description}}))
    monkeypatch.setitem(sys.modules, 'libvirt_qemu', fake)
    with pytest.raises(bootstrap.BootstrapError) as failure:
        bootstrap.GuestTransport(object()).call('guest-exec', {}, time.monotonic() + 3)
    assert failure.value.errors[0]['reason'] == description
    assert failure.value.errors[0]['qgaErrorClass'] == 'CommandNotFound'
    assert failure.value.errors[0]['command'] == 'guest-exec'


def test_standard_qga_error_redacts_encoded_and_decoded_stdin(monkeypatch):
    import sys
    import time
    import types
    private = json.dumps({'serviceYamlBase64': 'sensitive-yaml-value'})
    encoded = base64.b64encode(private.encode()).decode()
    description = 'invalid stdin: %s / %s' % (encoded, private)
    fake = types.SimpleNamespace(qemuAgentCommand=lambda *args: json.dumps({
        'error': {'class': 'GenericError', 'desc': description}}))
    monkeypatch.setitem(sys.modules, 'libvirt_qemu', fake)
    with pytest.raises(bootstrap.BootstrapError) as failure:
        bootstrap.GuestTransport(object()).call('guest-exec', {'input-data': encoded}, time.monotonic() + 3)
    assert failure.value.errors[0]['reason'].startswith('invalid stdin:')
    assert 'sensitive-yaml-value' not in str(failure.value.errors)
    assert encoded not in str(failure.value.errors)


def test_outer_limit_retains_known_error_count_and_first_cause(raw_qga):
    first = 'peer-first-original: ' + 'x' * 1044800
    raw_qga.result_override = dict(success=False, schemaVersion=1, errorCount=2,
        errors=[dict(stage='peer', reason=first), dict(stage='peer', reason='second peer failure')])
    assert len(json.dumps(raw_qga.result_override).encode()) < bootstrap.LIMIT
    raw_qga.exit_code = 1
    result = bootstrap.dispatch(request(raw_qga), lambda _: Domain())
    assert result['success'] is False
    assert len(bootstrap.serialize_response(result).encode()) <= bootstrap.LIMIT
    assert result['hccnBootstrap']['exitCode'] == 1
    assert result['hccnBootstrap']['truncated'] is True
    assert result['hccnBootstrap']['errorCount'] == 2
    assert result['hccnBootstrap']['errors'][0]['reason'].startswith('peer-first-original: ')
    assert result['hccnBootstrap']['errors'][1]['reason'] == 'second peer failure'

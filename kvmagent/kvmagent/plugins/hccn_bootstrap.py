import base64
import hashlib
import ipaddress
import json
import math
import re
import time
import uuid


from zstacklib.utils import pci


OPERATIONS = ('capability', 'begin', 'quiesce', 'snapshot', 'verify', 'publish',
              'release', 'activate', 'abort')
PROTECTED = ('start.sh', 'arm_vm_start.sh', 'distributed_start.sh',
             'aios_hccn_bootstrap.py', 'aios_hccn_config.py')
APP_DIR = '/home/jupyter/llama-factory_0.9.5'
MARKER = 'hccn-bootstrap.required.json'
LIMIT = 1048576
CONTEXT = ('schemaVersion', 'groupUuid', 'instanceUuid', 'vmUuid', 'attemptId',
           'epoch', 'bootId', 'nodeRank', 'nnodes')
HEX32 = re.compile(r'^[0-9a-f]{32}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')


class BootstrapError(Exception):
    def __init__(self, reason, stage='protocol', **details):
        super(BootstrapError, self).__init__(reason)
        self.errors = [dict(stage=stage, reason=reason, **details)]
        self.exit_code = None
        self.truncated = False
        self.error_count = None


def _require(condition, reason, stage='protocol'):
    if not condition:
        raise BootstrapError(reason, stage)


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, 'duplicate JSON key: %s' % key)
        result[key] = value
    return result


def parse_json(raw, limit=LIMIT):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    _require(isinstance(raw, bytes), 'JSON must be UTF-8 bytes or text')
    if len(raw) > limit:
        error = BootstrapError('JSON exceeds size limit')
        error.truncated = True
        raise error
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite JSON')))
    except (ValueError, UnicodeError) as exc:
        raise BootstrapError('invalid complete JSON: %s' % exc)


def serialize_response(response):
    # jsonobject omits None; strict wire requires explicit unknown/null values.
    return json.dumps(response, allow_nan=False, separators=(',', ':'))


def has_request(raw):
    try:
        return isinstance(json.loads(raw), dict) and 'hccnBootstrap' in json.loads(raw)
    except (ValueError, TypeError):
        return False


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _boot(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _context(payload):
    _require(isinstance(payload, dict), 'payload must be an object')
    _require(type(payload.get('schemaVersion')) is int and payload['schemaVersion'] == 1,
             'unsupported payload schemaVersion')
    for name in ('groupUuid', 'instanceUuid', 'vmUuid', 'attemptId'):
        _require(isinstance(payload.get(name), str) and HEX32.fullmatch(payload[name]),
                 'invalid context %s' % name)
    _require(_boot(payload.get('bootId')), 'invalid context bootId')
    _require(_integer(payload.get('epoch'), 1, 2 ** 63 - 1), 'invalid context epoch')
    _require(_integer(payload.get('nnodes'), 2, 2 ** 31 - 1), 'invalid context nnodes')
    _require(_integer(payload.get('nodeRank'), 0, payload['nnodes'] - 1), 'invalid context nodeRank')
    return {key: payload[key] for key in CONTEXT}



def _validate_payload(operation, payload):
    _context(payload)
    extras = {'verify': {'devices', 'peers'},
              'publish': {'verificationDigest', 'serviceYamlBase64', 'configSha256'},
              'release': {'configSha256'}, 'activate': {'configSha256'}}.get(operation, set())
    _require(set(payload) == set(CONTEXT).union(extras), 'missing or unknown operation payload fields')
    for key in extras.intersection({'verificationDigest', 'configSha256'}):
        _require(isinstance(payload[key], str) and SHA256.fullmatch(payload[key]), 'invalid payload ' + key)
    if operation == 'publish':
        content = _decode(payload['serviceYamlBase64'])
        _require(hashlib.sha256(content).hexdigest() == payload['configSha256'], 'published YAML SHA mismatch')
    if operation == 'verify':
        devices, peers = payload['devices'], payload['peers']
        _require(isinstance(devices, list) and devices and isinstance(peers, list), 'invalid verify devices/peers')
        for device in devices:
            _require(isinstance(device, dict) and set(device) == {'serialNumber', 'guestPciAddress', 'address', 'netmask'},
                     'invalid verify device schema')
            _require(isinstance(device['serialNumber'], str) and bool(device['serialNumber'].strip()), 'empty verify device SN')
            pci.normalize_strict_pci_address(device['guestPciAddress'])
            ipaddress.IPv4Address(device['address'])
            ipaddress.IPv4Network('0.0.0.0/' + device['netmask'])
        ranks = set()
        for peer in peers:
            _require(isinstance(peer, dict) and set(peer) == {'nodeRank', 'addresses'} and
                     _integer(peer['nodeRank'], 0, payload['nnodes'] - 1) and peer['nodeRank'] != payload['nodeRank'] and
                     peer['nodeRank'] not in ranks and isinstance(peer['addresses'], list) and peer['addresses'],
                     'invalid verify peer schema/rank')
            ranks.add(peer['nodeRank'])
            for address in peer['addresses']:
                _require(isinstance(address, str), 'invalid peer address')
                ipaddress.IPv4Address(address)
        _require(len(ranks) == payload['nnodes'] - 1, 'incomplete verify peer ranks')


def _artifact(value):
    _require(isinstance(value, dict) and set(value) == {'architecture', 'files'}, 'invalid expectedArtifact')
    _require(value['architecture'] in ('x86_64', 'aarch64'), 'invalid artifact architecture')
    files = value['files']
    _require(isinstance(files, dict) and set(files) == set(PROTECTED), 'artifact requires exactly five protected files')
    _require(all(isinstance(v, str) and SHA256.fullmatch(v) for v in files.values()), 'invalid artifact SHA256')


def _decode(value, limit=LIMIT):
    _require(isinstance(value, str), 'invalid base64 type')
    if len(value) > 4 * ((limit + 2) // 3):
        error = BootstrapError('base64 output exceeds size limit', 'transport')
        error.truncated = True
        raise error
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise BootstrapError('invalid base64: %s' % exc)
    if len(raw) > limit:
        error = BootstrapError('decoded output exceeds size limit', 'transport')
        error.truncated = True
        raise error
    _require(base64.b64encode(raw).decode('ascii') == value, 'noncanonical base64')
    return raw



def _redact_guest_error(reason, raw_request, arguments):
    reason = reason.replace(raw_request, '<QGA request redacted>')
    encoded = arguments.get('input-data')
    if encoded:
        reason = reason.replace(encoded, '<stdin redacted>')
        try:
            text = base64.b64decode(encoded).decode('utf-8')
            reason = reason.replace(text, '<stdin redacted>')
            reason = reason.replace(json.dumps(text)[1:-1], '<stdin redacted>')
        except (ValueError, UnicodeError):
            pass
    return reason[:4096]


class GuestTransport(object):
    def __init__(self, domain):
        self.domain = domain
        self.exit_code = None

    def call(self, operation, arguments, deadline):
        import libvirt_qemu
        remaining = deadline - time.monotonic()
        _require(remaining > 0, 'QGA deadline exceeded', 'transport')
        request = {'execute': operation, 'arguments': arguments}
        raw_request = json.dumps(request, separators=(',', ':'))
        try:
            response = libvirt_qemu.qemuAgentCommand(
                self.domain, raw_request, max(1, min(3, int(math.ceil(remaining)))), 0)
        except Exception as exc:
            raise BootstrapError(_redact_guest_error(str(exc), raw_request, arguments), 'transport')
        _require(time.monotonic() <= deadline, 'QGA deadline exceeded', 'transport')
        parsed = parse_json(response, 4 * ((LIMIT + 2) // 3) + 4096)
        if isinstance(parsed, dict) and set(parsed) == {'error'}:
            error = parsed['error']
            _require(isinstance(error, dict) and isinstance(error.get('class'), str) and
                     isinstance(error.get('desc'), str), 'invalid QGA error object', 'transport')
            raise BootstrapError(_redact_guest_error(error['desc'], raw_request, arguments), 'transport',
                                 qgaErrorClass=_redact_guest_error(error['class'], raw_request, arguments),
                                 command=operation)
        _require(isinstance(parsed, dict) and set(parsed) == {'return'}, 'QGA missing successful return', 'transport')
        return parsed['return']

    def read_file(self, name, deadline):
        _require(name in PROTECTED + (MARKER,), 'guest file is not allowed', 'artifact')
        handle = self.call('guest-file-open', {'path': APP_DIR + '/' + name, 'mode': 'r'}, deadline)
        _require(_integer(handle, 0, 2 ** 63 - 1), 'invalid QGA file handle', 'artifact')
        chunks, size, primary = [], 0, None
        try:
            while True:
                reply = self.call('guest-file-read', {'handle': handle, 'count': 65536}, deadline)
                _require(isinstance(reply, dict) and type(reply.get('eof')) is bool and
                         _integer(reply.get('count'), 0, 65536), 'invalid QGA read count/eof', 'artifact')
                raw = _decode(reply.get('buf-b64'), 65536)
                _require(len(raw) == reply['count'], 'QGA file read count mismatch', 'artifact')
                size += len(raw)
                _require(size <= LIMIT, 'guest artifact exceeds size limit', 'artifact')
                chunks.append(raw)
                if reply['eof']:
                    break
                _require(bool(raw), 'QGA file read made no progress', 'artifact')
        except BootstrapError as exc:
            primary = exc
        finally:
            try:
                # Closing a handle remains attempted after the read budget expires.
                self.call('guest-file-close', {'handle': handle}, max(deadline, time.monotonic() + 0.01))
            except BootstrapError as exc:
                if primary:
                    primary.errors.extend(exc.errors)
                else:
                    primary = exc
        if primary:
            raise primary
        return b''.join(chunks)

    def execute(self, operation, payload):
        args = {'path': '/usr/bin/python3',
                'arg': [APP_DIR + '/aios_hccn_bootstrap.py', operation, '--timeout', '900'],
                'capture-output': True,
                'env': ['PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                        'PYTHONDONTWRITEBYTECODE=1']}
        if payload is not None:
            stdin = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode('utf-8')
            _require(len(stdin) <= LIMIT, 'stdin exceeds size limit')
            args['input-data'] = base64.b64encode(stdin).decode('ascii')
        deadline = time.monotonic() + 915
        started = self.call('guest-exec', args, deadline)
        _require(isinstance(started, dict) and _integer(started.get('pid'), 1, 2 ** 63 - 1),
                 'QGA did not return a real process pid', 'transport')
        while True:
            status = self.call('guest-exec-status', {'pid': started['pid']}, deadline)
            _require(isinstance(status, dict) and type(status.get('exited')) is bool,
                     'QGA process terminal state missing', 'transport')
            if status['exited']:
                break
            _require(time.monotonic() < deadline, 'guest process terminal state unknown', 'transport')
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        rc = status.get('exitcode')
        self.exit_code = rc if type(rc) is int else None
        stdout = _decode(status.get('out-data', ''))
        stderr = _decode(status.get('err-data', ''))
        if len(stdout) + len(stderr) > LIMIT:
            error = BootstrapError('guest combined output exceeds size limit', 'transport')
            error.truncated = True
            raise error
        _require(all(type(status[key]) is bool for key in ('out-truncated', 'err-truncated') if key in status),
                 'QGA truncated flags must be booleans', 'transport')
        if (status.get('out-truncated') is True or status.get('err-truncated') is True or
                'signal' in status or type(rc) is not int):
            error = BootstrapError('guest output truncated or process exit is not proven', 'transport',
                                   signal=status.get('signal'), stdout=stdout[:4096].decode('utf-8', 'replace'),
                                   stderr=stderr[:4096].decode('utf-8', 'replace'))
            error.exit_code = rc if type(rc) is int else None
            error.truncated = bool(status.get('out-truncated') or status.get('err-truncated'))
            raise error
        try:
            result = parse_json(stdout)
        except BootstrapError as error:
            error.exit_code = rc
            error.errors[0].update(stdout=stdout[:4096].decode('utf-8', 'replace'),
                                   stderr=stderr[:4096].decode('utf-8', 'replace'))
            raise
        _require(isinstance(result, dict), 'guest result is not an object')
        if rc != 0 or result.get('success') is not True:
            error = BootstrapError('guest operation failed', 'guest', exitCode=rc,
                                   stdout=stdout[:4096].decode('utf-8', 'replace'),
                                   stderr=stderr[:4096].decode('utf-8', 'replace'))
            if (type(result.get('schemaVersion')) is int and result['schemaVersion'] == 1 and
                    _integer(result.get('errorCount'), 1, LIMIT) and
                    isinstance(result.get('errors'), list) and result['errors'] and
                    (result['errorCount'] == len(result['errors']) or
                     (result.get('truncated') is True and result['errorCount'] >= len(result['errors']))) and
                    all(isinstance(e, dict) and isinstance(e.get('reason'), str) for e in result['errors'])):
                error.errors = result['errors']
                error.error_count = result['errorCount']
            error.exit_code = rc
            error.truncated = result.get('truncated') is True
            raise error
        _require(type(result.get('schemaVersion')) is int and result['schemaVersion'] == 1,
                 'unsupported guest result schemaVersion')
        return rc, result


def read_guest_artifact(transport, expected):
    deadline = time.monotonic() + 30
    for name in PROTECTED:
        actual = hashlib.sha256(transport.read_file(name, deadline)).hexdigest()
        _require(actual == expected['files'][name], 'protected file SHA mismatch: %s' % name, 'artifact')
    marker = parse_json(transport.read_file(MARKER, deadline))
    _require(isinstance(marker, dict) and type(marker.get('schemaVersion')) is int and
             marker['schemaVersion'] == 1 and marker.get('required') is True and
             marker.get('architecture') == expected['architecture'] and marker.get('vendor') == 'huawei' and
             marker.get('mode') == 'distributed' and marker.get('files') == expected['files'],
             'required marker does not match selected strict artifact', 'artifact')


def _domain_identity(lookup, vm_uuid):
    domain = lookup(vm_uuid)
    _require(domain is not None and domain.isActive(), 'VM is not active', 'identity')
    _require(domain.name() == vm_uuid and uuid.UUID(domain.UUIDString()).hex == vm_uuid,
             'domain UUID/name does not match requested VM', 'identity')
    runtime = domain.ID()
    _require(_integer(runtime, 0, 2 ** 31 - 1), 'invalid active runtime ID', 'identity')
    return domain, (domain.name(), domain.UUIDString(), runtime)


def _device_sets(wire):
    gpu_devices = wire.get('expectedGpuDevices')
    non_gpu = wire.get('expectedNonGpuPciAddresses')
    _require(isinstance(gpu_devices, list) and gpu_devices and isinstance(non_gpu, list),
             'snapshot/verify requires actual GPU and non-GPU allocation sets', 'identity')
    gpus = {}
    for item in gpu_devices:
        _require(isinstance(item, dict) and {'hostPciAddress'} <= set(item) <= {'hostPciAddress', 'serialNumber'},
                 'invalid expected GPU device', 'identity')
        address = pci.normalize_strict_pci_address(item['hostPciAddress'])
        _require(address not in gpus, 'duplicate expected host GPU BDF', 'identity')
        if 'serialNumber' in item:
            _require(isinstance(item['serialNumber'], str) and bool(item['serialNumber'].strip()), 'invalid expected SN')
        gpus[address] = item
    others = [pci.normalize_strict_pci_address(value) for value in non_gpu]
    _require(len(others) == len(set(others)) and not set(others).intersection(gpus), 'duplicate/conflicting PCI sets')
    return gpus, set(others)


def _mapped_devices(result, observation, expected, non_gpu):
    mapping = {item['guestPciAddress']: item['hostPciAddress'] for item in observation['devices']}
    _require(set(mapping.values()) == set(expected).union(non_gpu), 'domain/QMP differs from actual allocation', 'identity')
    devices = result.get('devices')
    _require(isinstance(devices, list) and devices, 'guest device set is empty', 'identity')
    hosts, guests, serials, output = set(), set(), set(), []
    for item in devices:
        _require(isinstance(item, dict) and _integer(item.get('npuId'), 0, 2 ** 31 - 1), 'invalid guest npuId')
        guest = pci.normalize_strict_pci_address(item.get('guestPciAddress'))
        serial = item.get('serialNumber')
        _require(isinstance(serial, str) and bool(serial.strip()) and serial not in serials, 'empty/duplicate guest SN')
        host = mapping.get(guest)
        _require(host in expected and host not in hosts and guest not in guests,
                 'guest GPU is missing/extra/duplicate or maps to non-GPU', 'identity')
        _require(expected[host].get('serialNumber', serial) == serial, 'freshNative SN conflicts with guest', 'identity')
        try:
            address = ipaddress.IPv4Address(item['address'])
            network = ipaddress.IPv4Network('0.0.0.0/' + item['netmask'])
            _require(str(address) == item['address'] and str(network.netmask) == item['netmask'], 'noncanonical GPU IP/netmask')
        except (KeyError, ValueError, TypeError):
            raise BootstrapError('invalid guest GPU IP/netmask', 'identity')
        _require(item.get('linkStatus') in ('UP', 'DOWN', 'UNKNOWN'), 'invalid guest linkStatus')
        hosts.add(host); guests.add(guest); serials.add(serial)
        output.append(dict(item, hostPciAddress=host))
    _require(hosts == set(expected), 'guest GPU set does not equal actual allocation', 'identity')
    _require(len({item['address'] for item in output}) == len(output), 'duplicate guest GPU IP', 'identity')
    return output


def _validate_result(operation, result, payload, artifact):
    if operation == 'capability':
        _require(result.get('required') is True and result.get('files') == artifact['files'] and
                 result.get('architecture') == artifact['architecture'] and _boot(result.get('bootId')) and
                 isinstance(result.get('operations'), list) and
                 set(OPERATIONS[1:]).issubset(result['operations']), 'guest strict capability does not match artifact')
        return
    _require(_context(result.get('context')) == _context(payload) and set(result['context']) == set(CONTEXT),
             'guest context does not match request', 'identity')
    if operation in ('begin', 'quiesce', 'abort', 'publish', 'release', 'activate'):
        _require(result.get('phase') in ('pending', 'verified', 'released', 'aborted'), 'invalid guest phase')
    if operation == 'begin':
        _require(result['phase'] == 'pending', 'begin did not acknowledge pending')
    if operation in ('release', 'activate'):
        _require(result['phase'] == 'released', 'release/activate did not acknowledge released')
    if operation == 'abort':
        _require(result['phase'] == 'aborted', 'abort did not acknowledge aborted')
    if operation in ('abort', 'quiesce'):
        _require(result.get('quiesced') is True or result['phase'] == 'aborted', 'safe stop not acknowledged')
    if operation == 'activate':
        _require(result.get('activated') is True, 'activation not acknowledged')
    if operation == 'verify':
        _require(isinstance(result.get('verificationDigest'), str) and SHA256.fullmatch(result['verificationDigest']),
                 'invalid verification digest')
    if operation == 'publish':
        _require(result.get('configSha256') == payload.get('configSha256') and
                 isinstance(result.get('configSha256'), str) and SHA256.fullmatch(result['configSha256']) and
                 result['phase'] == 'verified', 'publish configuration digest/phase mismatch')


def dispatch(raw_request, lookup_domain):
    envelope = {'schemaVersion': 1, 'operation': None, 'exitCode': None,
                'result': None, 'errorCount': 0, 'errors': []}
    response = {'success': False, 'error': '', 'gpuInfos': [], 'hccnBootstrap': envelope}
    transport = None
    try:
        request = parse_json(raw_request)
        _require(isinstance(request, dict) and isinstance(request.get('hccnBootstrap'), dict), 'strict request must be an object')
        wire = request['hccnBootstrap']
        operation = wire.get('operation')
        envelope['operation'] = operation if operation in OPERATIONS else None
        _require(type(wire.get('schemaVersion')) is int and wire['schemaVersion'] == 1, 'unsupported strict schemaVersion')
        _require(operation in OPERATIONS, 'unsupported strict operation')
        _require(not set(wire).difference({'schemaVersion', 'operation', 'capabilityScope', 'payload',
                 'expectedArtifact', 'expectedGpuDevices', 'expectedNonGpuPciAddresses'}), 'unknown strict request field')
        if operation == 'capability':
            scope = wire.get('capabilityScope')
            _require(scope in ('host', 'guest') and 'payload' not in wire, 'invalid capability scope/payload')
            envelope['capabilityScope'] = scope
            if scope == 'host':
                _require(set(wire) == {'schemaVersion', 'operation', 'capabilityScope'}, 'host probe has guest fields')
                envelope['result'] = {'schemaVersion': 1, 'success': True,
                                      'operations': list(OPERATIONS), 'releaseProbeVersion': 1}
                response['success'] = True
                return response
        else:
            _require('capabilityScope' not in wire, 'capabilityScope only applies to capability')
        payload = None if operation == 'capability' else wire.get('payload')
        if payload is not None or operation != 'capability':
            _validate_payload(operation, payload)
        vm_uuid = request.get('vmUuid')
        _require(isinstance(vm_uuid, str) and HEX32.fullmatch(vm_uuid) and request.get('vendors') == ['Huawei'],
                 'strict guest requires actual VM UUID and Huawei vendor')
        _require(payload is None or payload['vmUuid'] == vm_uuid, 'payload VM UUID mismatch')
        artifact = wire.get('expectedArtifact')
        _artifact(artifact)
        expected, non_gpu, before = None, None, None
        domain, identity = _domain_identity(lookup_domain, vm_uuid)
        if operation in ('snapshot', 'verify'):
            expected, non_gpu = _device_sets(wire)
            before = pci.get_strict_pci_passthrough_observation(domain)
        transport = GuestTransport(domain)
        read_guest_artifact(transport, artifact)
        envelope['exitCode'], result = transport.execute(operation, payload)
        _validate_result(operation, result, payload, artifact)
        current, current_identity = _domain_identity(lookup_domain, vm_uuid)
        _require(identity == current_identity, 'active VM runtime changed during operation', 'identity')
        if before is not None:
            after = pci.get_strict_pci_passthrough_observation(current)
            _require(before == after, 'PCI domain/QMP observation changed during operation', 'identity')
            envelope['devices'] = _mapped_devices(result, after, expected, non_gpu)
        envelope['result'] = result
        response['success'] = True
    except Exception as exc:
        error = exc if isinstance(exc, BootstrapError) else BootstrapError(str(exc)[:4096], 'identity')
        envelope['result'] = None
        envelope['errors'] = error.errors
        envelope['errorCount'] = error.error_count if error.error_count is not None else len(error.errors)
        if error.exit_code is not None:
            envelope['exitCode'] = error.exit_code
        elif transport is not None and transport.exit_code is not None:
            envelope['exitCode'] = transport.exit_code
        if error.truncated:
            envelope['truncated'] = True
        response['error'] = str(error.errors[0].get('reason', 'strict bootstrap failed'))[:4096]
    encoded = json.dumps(response, allow_nan=False).encode('utf-8')
    if len(encoded) > LIMIT:
        response['success'] = False
        envelope.update(result=None, truncated=True)
        envelope.pop('devices', None)
        if not envelope['errors']:
            envelope.update(errorCount=1, errors=[{'stage': 'transport', 'reason': 'strict response exceeds size limit'}])
        bounded, used = [], 0
        for error in envelope['errors']:
            item = {'reason': error['reason'][:4096]}
            for key, value in error.items():
                if key == 'reason' or len(key) > 128:
                    continue
                if isinstance(value, str):
                    value = value[:4096]
                elif len(serialize_response(value).encode('utf-8')) > 4096:
                    value = '<diagnostic truncated>'
                candidate = dict(item, **{key: value})
                if len(serialize_response(candidate).encode('utf-8')) <= 8192:
                    item = candidate
            size = len(serialize_response(item).encode('utf-8'))
            if bounded and used + size > 65536:
                break
            bounded.append(item)
            used += size
        envelope['errors'] = bounded
        response['error'] = bounded[0]['reason']
    return response

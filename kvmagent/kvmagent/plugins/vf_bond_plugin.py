"""UserVM guest bond coordination. Device delivery stays in vm_plugin."""
import os
import json
import re
import uuid
import time
import xml.etree.ElementTree as ET
from kvmagent import kvmagent
from kvmagent.plugins.vm_config import get_virt_domain
from zstacklib.utils import http, jsonobject, log, pci, qmp
from zstacklib.utils.qga import VmQga

PATH = '/vm/guesttools/vfbond'
SCRIPT = '/usr/local/zstack/zs-tools/guest_network.py'
MIGRATION_CAPABILITY_PATH = '/host/vfbond/migration-capability'
CHECK_CLEANUP_PATH = '/host/vfbond/checkcleanup'
LIVE_MIGRATION_CAPABILITY = 'vfBondLiveMigration'
logger = log.get_logger(__name__)


class Request(object):
    PROBE = 'probe'
    INSPECT = 'inspect'
    STATUS = 'status'
    CANCEL = 'cancel'
    EXECUTE = 'execute'
    OBSERVATIONS = (PROBE, INSPECT)


class Operation(object):
    RECONCILE = 'reconcile'
    MIGRATION = 'migration'
    PORTS = 'ports'


class Support(object):
    SUPPORTED = 'Supported'
    UNSUPPORTED = 'Unsupported'
    UNKNOWN = 'Unknown'


class ConfigState(object):
    CHECKING = 'Checking'
    SUCCEEDED = 'Succeeded'
    FAILED = 'Failed'


class Target(object):
    MEMBERS = 'members'
    DEFAULT_PEERS = 'defaultPeers'
    RESOLVE_GUEST_PCI = 'resolveGuestPci'
    TEMPORARY_PCI = 'temporaryPci'
    TEMPORARY_TARGET = 'temporaryTarget'


class MigrationStage(object):
    CHECK = 'check'
    PREPARE = 'prepare'
    TRANSIT = 'transit'
    RECONNECT = 'reconnect'
    FINISH = 'finish'


def transport_failure_reason(action, submitted):
    if action in Request.OBSERVATIONS:
        return 'ObservationUnavailable'
    if action == Request.EXECUTE and not submitted:
        return 'RequestNotSubmitted'
    return 'OperationUncertain'


def bdf(node):
    return '%04x:%02x:%02x.%x' % tuple(int(node.get(k, '0'), 0) for k in ('domain', 'bus', 'slot', 'function'))


def guest_pci_view(vm, xml):
    """Return a guest-address view of the live NICs without changing libvirt XML."""
    root = ET.fromstring(xml)
    os_type = root.find('./os/type')
    if os_type is None or 'q35' not in os_type.get('machine', ''):
        return xml, {}
    from kvmagent.plugins.vm_plugin import VmPlugin
    buses = qmp.execute_qmp_command(vm, 'query-pci')
    mapping = {}
    for dev in root.findall('./devices/interface') + root.findall('./devices/hostdev'):
        addr = dev.find('address')
        if addr is None or addr.get('type') != 'pci':
            continue
        alias = dev.find('alias')
        if alias is None:
            raise ValueError('PCI device alias unavailable')
        for bus in buses:
            device = VmPlugin._find_pci_device(bus.get('devices', []), alias.get('name'))
            if device is not None:
                break
        else:
            device = None
        if device is None:
            raise ValueError('PCI device not enumerated: ' + alias.get('name'))
        mapping[bdf(addr)] = pci.fmt_pci_address(device)
        for field in ('domain', 'bus', 'slot', 'function'):
            addr.set(field, hex(device.get(field, 0)))
    return ET.tostring(root), mapping


def guest_target(target, mapping):
    def members(item):
        return [mapping[p] for p in item[Target.MEMBERS]]
    resolved = dict(target)
    if Target.MEMBERS in target:
        resolved[Target.MEMBERS] = members(target)
    if Target.DEFAULT_PEERS in target:
        peers = []
        for peer in target[Target.DEFAULT_PEERS]:
            item = dict(peer, guestPci=mapping[peer['guestPci']])
            if Target.MEMBERS in peer:
                item[Target.MEMBERS] = members(peer)
            peers.append(item)
        resolved[Target.DEFAULT_PEERS] = peers
    return resolved


def delivered(xml, target):
    """Validate the two actual hostdevs, not merely their persisted MN addresses."""
    root = ET.fromstring(xml)
    devices = list(root.findall('./devices/hostdev'))
    devices += [d for d in root.findall('./devices/interface') if d.get('type') == 'hostdev']
    found = []
    host_members = set(p if p.count(':') == 2 else '0000:' + p for p in target['hostMembers'])
    for dev in devices:
        addr = dev.find('address')
        source = dev.find('./source/address')
        mac = dev.find('mac')
        if source is not None and bdf(source) in host_members:
            if addr is None or (mac is not None and mac.get('address') != target['mac']):
                return False
            found.append((bdf(addr), bdf(source)))
    return (len(found) == 2 and len(set(x[1] for x in found)) == 2
            and set(x[0] for x in found) == set(target[Target.MEMBERS])
            and set(x[1] for x in found) == host_members)



def ordinary_devices(xml):
    found = {}
    for dev in ET.fromstring(xml).findall('./devices/interface'):
        mac, addr = dev.find('mac'), dev.find('address')
        if mac is not None and addr is not None and addr.get('type') == 'pci':
            key = mac.get('address')
            found[key] = None if key in found else bdf(addr)
    return found


def migration_vfs_absent(xml, target):
    root = ET.fromstring(xml)
    devices = list(root.findall('./devices/hostdev'))
    devices += [d for d in root.findall('./devices/interface') if d.get('type') == 'hostdev']
    host_members = set(p if p.count(':') == 2 else '0000:' + p for p in target['hostMembers'])
    return not any(d.find('./source/address') is not None and
                   bdf(d.find('./source/address')) in host_members for d in devices)


def migration_temporary_pci(xml, operation):
    target = operation.get('target') or {}
    found = []
    for dev in ET.fromstring(xml).findall('./devices/interface'):
        tap, mac, model, addr = (dev.find(n) for n in ('target', 'mac', 'model', 'address'))
        if (dev.get('type') == 'bridge' and tap is not None and
                tap.get('dev') == operation.get(Target.TEMPORARY_TARGET) and mac is not None and
                mac.get('address') == target.get('mac') and model is not None and
                model.get('type') == 'virtio' and addr is not None and addr.get('type') == 'pci'):
            found.append(bdf(addr))
    if len(found) > 1:
        raise ValueError('ambiguous migration bridge')
    return found[0] if found else None


class VfBondPlugin(kvmagent.KvmAgent):
    @kvmagent.replyerror
    def migration_capability(self, req):
        return json.dumps(dict(success=True, capabilities=[LIVE_MIGRATION_CAPABILITY]))

    @kvmagent.replyerror
    def reconcile(self, req):
        cmd = json.loads(req[http.REQUEST_BODY])
        for key in ('vmUuid', 'operationId'):
            if not re.match(r'^[a-f0-9]{32}$', cmd.get(key, '')):
                raise ValueError('invalid ' + key)
        return json.dumps(self.run_command(cmd))

    def run_command(self, cmd):
        started = time.monotonic()
        result = self._run_command(cmd)
        known = ('Ready WaitingForTools WaitingForQga WaitingForVm WaitingForDevices Unsupported '
                 'OperationBusy OperationUncertain RequestNotSubmitted ObservationUnavailable GuestBootChanged ReceiptIdentityMismatch').split()
        code = re.split(r'[:;\s]', result.get('reason', ''), 1)[0]
        result.setdefault('reasonCode', code if code in known else 'UnknownReason')
        diagnostics = result.setdefault('diagnostics', {})
        if not isinstance(diagnostics, dict):
            diagnostics = result['diagnostics'] = {}
        diagnostics['host'] = dict(node=os.uname()[1], observedAt=int(time.time()*1000), action=cmd['action'],
                                   phase=result.pop('_phase', 'admission'), durationMs=int((time.monotonic()-started)*1000),
                                   state=result['state'], reason=result['reason'])
        diagnostics['host']['stages'] = result.pop('_stages', [])
        execution = result.pop('_guestExecution', None)
        if execution is not None:
            diagnostics['host']['guestExecution'] = execution
        # Persistable transport summary excludes host identity and device details.
        diagnostics['transport'] = {key: diagnostics['host'][key] for key in
                                    ('observedAt', 'action', 'phase', 'durationMs', 'state', 'reason')}
        diagnostics['transport']['layer'] = 'host'
        if execution is not None:
            diagnostics['transport']['guestExecution'] = {key: execution[key] for key in
                                                         ('exitCode', 'stdoutBytes', 'stderrBytes')}
        logger.debug('guest-network vm=%s nic=%s operationId=%s bootId=%s action=%s phase=%s durationMs=%s state=%s reason=%s' % (
            cmd['vmUuid'], (cmd.get('operation') or {}).get('nicUuid'), cmd['operationId'],
            cmd.get('bootId'), cmd['action'], diagnostics['host']['phase'], diagnostics['host']['durationMs'],
            result['state'], result['reason']))
        return result

    def _run_command(self, cmd):
        vm = cmd['vmUuid']; action = cmd['action']
        base = dict(success=True, protocolVersion=3, operationId=cmd['operationId'],
                    state=ConfigState.CHECKING, reason='WaitingForTools', support=Support.UNKNOWN, completed=False)
        phase_started = time.monotonic()
        def phase(name):
            base['_phase'] = name
            base.setdefault('_stages', []).append(dict(phase=name, at=int(time.time()*1000),
                elapsedMs=int((time.monotonic()-phase_started)*1000)))
        phase('admission')
        param = None
        submitted = False
        try:
            if action not in (Request.PROBE, Request.INSPECT, Request.STATUS, Request.CANCEL, Request.EXECUTE):
                base.update(state=ConfigState.FAILED, reason='UnsupportedAction', support=Support.UNSUPPORTED)
                return base
            phase('domainCheck')
            domain = get_virt_domain(vm)
            if domain is None or not domain.isActive():
                base['reason'] = 'WaitingForVm'
                return base
            phase('qgaCheck')
            qga = VmQga(domain)
            if qga.state != VmQga.QGA_STATE_RUNNING:
                base['reason'] = 'WaitingForQga'
                return base
            phase('toolCheck')
            code, _, _ = qga.guest_exec_command('/usr/bin/test', ['-s', '/usr/local/zstack/guesttools'], retry=3)
            if code != 0:
                return base
            code, _, _ = qga.guest_exec_command('/usr/bin/test', ['-f', SCRIPT], retry=3)
            if code == 1:
                base.update(state=ConfigState.FAILED, reason='Unsupported: GuestTools network protocol missing', support=Support.UNSUPPORTED)
                return base
            if code != 0:
                raise ValueError('guest protocol file check failed (exitCode=%s)' % code)
            op = cmd.get('operation') or {}
            if action in Request.OBSERVATIONS or (action == Request.EXECUTE and op.get('action') in (Operation.RECONCILE, Operation.MIGRATION, Operation.PORTS)):
                xml, mapping = guest_pci_view(vm, domain.XMLDesc(0))
                resolved = None
                if mapping and (op.get(Target.RESOLVE_GUEST_PCI) or (action == Request.EXECUTE and op.get('action') == Operation.PORTS)):
                    try:
                        resolved = guest_target(op['target'], mapping)
                    except KeyError:
                        base['reason'] = 'WaitingForDevices'
                        return base
                    cmd = dict(cmd, operation=dict(op, target=resolved))
            if action == Request.EXECUTE:
                phase('deviceIdentity')
                op = cmd['operation']
                if op['action'] == Operation.RECONCILE and not delivered(xml, op['target']):
                    base['reason'] = 'WaitingForDevices'
                    return base
                if op['action'] == Operation.MIGRATION:
                    stage = op.get('migrationStage')
                    temporary = migration_temporary_pci(xml, op)
                    if (stage in (MigrationStage.CHECK, MigrationStage.PREPARE, MigrationStage.RECONNECT, MigrationStage.FINISH) and not delivered(xml, op['target']) or
                            stage == MigrationStage.TRANSIT and not migration_vfs_absent(xml, op['target']) or
                            stage in (MigrationStage.PREPARE, MigrationStage.TRANSIT) and not temporary or
                            stage == MigrationStage.FINISH and temporary or
                            temporary != op.get(Target.TEMPORARY_PCI)):
                        base['reason'] = 'WaitingForDevices'
                        return base
                if op['action'] == Operation.PORTS:
                    devices = ordinary_devices(xml)
                    if any(not isinstance(p.get('guestPci'), str) or
                           not re.fullmatch(r'[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]', p['guestPci']) or
                           not devices.get(p.get('mac')) or devices[p['mac']] != p['guestPci']
                           for p in op['target']['ports']):
                        base['reason'] = 'WaitingForDevices'
                        return base
            phase('guestRequest')
            param = '/usr/local/zstack/guest-network-request-' + uuid.uuid4().hex + '.json'
            guest_cmd = dict(cmd)
            payload = json.dumps(guest_cmd)
            if qga.guest_file_write(param, payload) != len(payload.encode('utf-8')):
                raise ValueError('incomplete guest request')
            # An exception from guest-exec can occur after QGA accepted it.
            submitted = True
            code, stdout, stderr = qga.guest_exec_python(SCRIPT, [param], retry=130 if action == Request.EXECUTE else 5)
            phase('guestResponse')
            base['_guestExecution'] = dict(exitCode=code, stdoutBytes=len((stdout or '').encode('utf-8')),
                                           stderrBytes=len((stderr or '').encode('utf-8')), stderr=(stderr or '')[:2048])
            # Missing output is not evidence of an unsupported protocol. In
            # particular, guest-exec may report no exitcode after a signal.
            if code != 0:
                raise ValueError('guest process did not exit successfully (exitCode=%s)' % code)
            if not stdout or not stdout.strip():
                raise ValueError('empty guest response')
            if len(stdout) > 1024*1024:
                raise ValueError('guest response exceeds diagnostic size limit')
            answer = json.loads(stdout)
            if not isinstance(answer, dict):
                raise ValueError('guest response must be a JSON object')
            version = answer.get('protocolVersion')
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise ValueError('guest response has no valid protocol version')
            if version != 3:
                base.update(state=ConfigState.FAILED, reason='Unsupported: GuestTools network protocol 3 required', support=Support.UNSUPPORTED)
                return base
            if answer.get('operationId') != cmd['operationId'] or answer.get('state') not in (ConfigState.CHECKING, ConfigState.SUCCEEDED, ConfigState.FAILED):
                raise ValueError('invalid guest response identity or state')
            if not isinstance(answer.get('reason'), str) or answer.get('support') not in (Support.SUPPORTED, Support.UNSUPPORTED, Support.UNKNOWN):
                raise ValueError('invalid guest response reason or support')
            if 'completed' in answer and not isinstance(answer['completed'], bool):
                raise ValueError('invalid guest completion evidence')
            diagnostics = answer.get('diagnostics')
            if not isinstance(diagnostics, dict):
                answer['diagnostics'] = dict(missingReason='InvalidDiagnostics' if diagnostics is not None else 'NotProvided')
            # Only protocol fields may cross the guest/host evidence boundary.
            guest_fields = ('protocolVersion', 'operationId', 'bootId', 'state', 'reason', 'reasonCode',
                            'support', 'completed', 'diagnostics', 'capabilities', 'target',
                            'originalIdentity', 'identityMissingReason', 'recoveryRequired',
                            'recoveryNicUuid', 'failure', 'recovery')
            base.update((key, answer[key]) for key in guest_fields if key in answer)
            if action == Request.INSPECT and answer.get('support') == Support.SUPPORTED and not isinstance(diagnostics, dict):
                # Older tools can configure networks but do not implement
                # inspection. Preserve admission errors such as OperationBusy;
                # they legitimately have no collected diagnostic payload.
                base.pop('reasonCode', None)
                base.update(state=ConfigState.CHECKING, support=Support.UNKNOWN,
                            reason='ObservationUnavailable: GuestTools diagnostics extension missing')
            if action in Request.OBSERVATIONS:
                base['devices'] = ordinary_devices(xml)
                if resolved is not None:
                    base['target'] = resolved
                if (cmd.get('operation') or {}).get(Target.TEMPORARY_TARGET):
                    base[Target.TEMPORARY_PCI] = migration_temporary_pci(xml, cmd['operation'])
            return base
        except Exception as ex:
            reason = transport_failure_reason(action, submitted)
            base.pop('reasonCode', None)
            base.update(state=ConfigState.CHECKING, support=Support.UNKNOWN, completed=False, reason=reason + ': ' + str(ex)[:2048])
            return base
        finally:
            # Host evidence must never be overwritten by fields in a guest response.
            if action == Request.EXECUTE:
                base['requestSubmitted'] = submitted
            else:
                base.pop('requestSubmitted', None)
            if param is not None:
                try:
                    code, _, _ = qga.guest_exec_command('/usr/bin/rm', ['-f', param], retry=3)
                    if code != 0:
                        raise ValueError('request cleanup exitCode=%s' % code)
                except Exception as ex:
                    if not isinstance(base.get('diagnostics'), dict):
                        base['diagnostics'] = {}
                    base['diagnostics']['requestCleanup'] = dict(state='Failed', reason=str(ex)[:512])

    @kvmagent.replyerror
    def check_cleanup(self, req):
        from kvmagent.plugins.vf_bond_cleanup import check_devices
        return json.dumps(check_devices(json.loads(req[http.REQUEST_BODY])['devices']))

    def start(self):
        kvmagent.get_http_server().register_async_uri(MIGRATION_CAPABILITY_PATH, self.migration_capability)
        kvmagent.get_http_server().register_async_uri(CHECK_CLEANUP_PATH, self.check_cleanup)
        kvmagent.get_http_server().register_async_uri(PATH, self.reconcile)

    def stop(self):
        pass

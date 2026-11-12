"""UserVM guest bond coordination. Device delivery stays in vm_plugin."""
import os
import json
import re
import uuid
import time
import xml.etree.ElementTree as ET
from kvmagent import kvmagent
from kvmagent.plugins.vm_config import get_virt_domain
from zstacklib.utils import http, jsonobject, log
from zstacklib.utils.qga import VmQga

PATH = '/vm/guesttools/vfbond'
SCRIPT = '/usr/local/zstack/zs-tools/guest_network.py'
logger = log.get_logger(__name__)


def bdf(node):
    return '%04x:%02x:%02x.%x' % tuple(int(node.get(k, '0'), 0) for k in ('domain', 'bus', 'slot', 'function'))


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
            and set(x[0] for x in found) == set(target['members'])
            and set(x[1] for x in found) == host_members)



def ordinary_devices(xml):
    found = {}
    for dev in ET.fromstring(xml).findall('./devices/interface'):
        mac, addr = dev.find('mac'), dev.find('address')
        if mac is not None and addr is not None and addr.get('type') == 'pci':
            key = mac.get('address')
            found[key] = None if key in found else bdf(addr)
    return found


class VfBondPlugin(kvmagent.KvmAgent):
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
                    state='Checking', reason='WaitingForTools', support='Unknown', completed=False)
        phase_started = time.monotonic()
        def phase(name):
            base['_phase'] = name
            base.setdefault('_stages', []).append(dict(phase=name, at=int(time.time()*1000),
                elapsedMs=int((time.monotonic()-phase_started)*1000)))
        phase('admission')
        param = None
        submitted = False
        try:
            if action not in ('probe', 'inspect', 'status', 'cancel', 'execute'):
                base.update(state='Failed', reason='UnsupportedAction', support='Unsupported')
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
                base.update(state='Failed', reason='Unsupported: GuestTools network protocol missing', support='Unsupported')
                return base
            if code != 0:
                raise ValueError('guest protocol file check failed (exitCode=%s)' % code)
            if action == 'execute':
                phase('deviceIdentity')
                op = cmd['operation']
                if op['action'] == 'reconcile' and not delivered(domain.XMLDesc(0), op['target']):
                    base['reason'] = 'WaitingForDevices'
                    return base
                if op['action'] == 'ports':
                    devices = ordinary_devices(domain.XMLDesc(0))
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
            code, stdout, stderr = qga.guest_exec_python(SCRIPT, [param], retry=130 if action == 'execute' else 5)
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
                base.update(state='Failed', reason='Unsupported: GuestTools network protocol 3 required', support='Unsupported')
                return base
            if answer.get('operationId') != cmd['operationId'] or answer.get('state') not in ('Checking', 'Succeeded', 'Failed'):
                raise ValueError('invalid guest response identity or state')
            if not isinstance(answer.get('reason'), str) or answer.get('support') not in ('Supported', 'Unsupported', 'Unknown'):
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
            if action == 'inspect' and answer.get('support') == 'Supported' and not isinstance(diagnostics, dict):
                # Older tools can configure networks but do not implement
                # inspection. Preserve admission errors such as OperationBusy;
                # they legitimately have no collected diagnostic payload.
                base.pop('reasonCode', None)
                base.update(state='Checking', support='Unknown',
                            reason='ObservationUnavailable: GuestTools diagnostics extension missing')
            if action in ('probe', 'inspect'):
                base['devices'] = ordinary_devices(domain.XMLDesc(0))
            return base
        except Exception as ex:
            reason = 'ObservationUnavailable' if action in ('probe', 'inspect') else (
                'RequestNotSubmitted' if action == 'execute' and not submitted else 'OperationUncertain')
            base.pop('reasonCode', None)
            base.update(state='Checking', support='Unknown', completed=False, reason=reason + ': ' + str(ex)[:2048])
            return base
        finally:
            # Host evidence must never be overwritten by fields in a guest response.
            if action == 'execute':
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
        kvmagent.get_http_server().register_async_uri('/host/vfbond/checkcleanup', self.check_cleanup)
        kvmagent.get_http_server().register_async_uri(PATH, self.reconcile)

    def stop(self):
        pass

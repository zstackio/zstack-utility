"""Host transport tests: identity, bounded QGA and no persistent permits."""
import ast,json,os,types,unittest,uuid,time,logging,re
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
source=(Path(__file__).resolve().parents[1]/'plugins/vf_bond_plugin.py').read_text()
tree=ast.parse(source)
tree.body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]
ctx=dict(time=time,logger=logging.getLogger(__name__),os=os,json=json,uuid=uuid,re=re,ET=ET,
         kvmagent=types.SimpleNamespace(KvmAgent=object,replyerror=lambda f:f),get_virt_domain=lambda _:None,
         SCRIPT='guest_network.py')
exec(compile(tree,'host-transport','exec'),ctx)

class HostNetworkTransportTest(unittest.TestCase):
 def setUp(self):
  self.cmd=dict(vmUuid='a'*32,operationId='b'*32,bootId='boot-one',action='probe',operation={'action':'reconcile','target':{}})
  self.plugin=ctx['VfBondPlugin']()
 def runaction(self,action):self.cmd['action']=action;return self.plugin.run_command(self.cmd)
 def qga(self,version=3,timeout=False,response=None,raw=None,script_code=0):
  command=self.cmd
  class Qga:
   QGA_STATE_RUNNING='running'
   state='running'
   def __init__(self,domain):pass
   def guest_exec_command(self,*args,**kwargs):
    return (script_code if args[1]==['-f',ctx['SCRIPT']] else 0),'',''
   def guest_file_write(self,path,payload):return len(payload.encode('utf-8'))
   def guest_exec_python(self,*args,**kwargs):
    if timeout:raise TimeoutError('guest-exec-status timed out')
    if raw is not None:return raw
    answer=dict(protocolVersion=version,operationId=command['operationId'],state='Succeeded',support='Supported',reason='VerifiedManual',diagnostics={})
    answer.update(response or {})
    return 0,json.dumps(answer),''
  return Qga
 def env(self,**kwargs):
  data={'VmQga':self.qga(),'get_virt_domain':lambda _:types.SimpleNamespace(isActive=lambda:True,XMLDesc=lambda _: '<domain/>')}
  data.update(kwargs);return patch.dict(ctx,data)
 def test_legacy_authorization_actions_rejected(self):
  for action in ('grant','fence','settle'):
   self.assertEqual('UnsupportedAction',self.runaction(action)['reason'])
 def test_inspect_has_partial_host_evidence_without_permits(self):
  answer=self.runaction('inspect');self.assertEqual('WaitingForVm',answer['reason'])
  self.assertNotIn('hostGate',answer['diagnostics'])
  self.assertEqual(['admission','domainCheck'],[s['phase'] for s in answer['diagnostics']['host']['stages']])
  self.assertNotIn('node',answer['diagnostics']['transport'])
 def test_old_protocol_requires_upgrade(self):
  with self.env(VmQga=self.qga(version=2)):
   answer=self.runaction('probe')
  self.assertEqual('Unsupported',answer['support']);self.assertIn('protocol 3 required',answer['reason'])
 def test_inspect_preserves_guest_lock_contention(self):
  with self.env(VmQga=self.qga(response=dict(state='Checking',support='Unknown',reason='OperationBusy',diagnostics=None))):
   answer=self.runaction('inspect')
  self.assertEqual('OperationBusy',answer['reason']);self.assertEqual('Unknown',answer['support'])
  self.assertEqual('OperationBusy',answer['diagnostics']['host']['reason'])
 def test_supported_inspect_still_requires_diagnostic_evidence(self):
  with self.env(VmQga=self.qga(response=dict(diagnostics=None,reasonCode='Ready'))):answer=self.runaction('inspect')
  self.assertTrue(answer['reason'].startswith('ObservationUnavailable'));self.assertEqual('Unknown',answer['support'])
  self.assertEqual('ObservationUnavailable',answer['reasonCode'])
 def test_host_observation_error_replaces_guest_reason_code(self):
  def unavailable(_):raise RuntimeError('domain XML unavailable')
  domain=types.SimpleNamespace(isActive=lambda:True,XMLDesc=unavailable)
  for action in ('probe','inspect'):
   with self.subTest(action=action),self.env(VmQga=self.qga(response=dict(reasonCode='Ready')),get_virt_domain=lambda _:domain):
    answer=self.runaction(action)
    self.assertEqual('ObservationUnavailable',answer['reasonCode'])
    self.assertTrue(answer['reason'].startswith('ObservationUnavailable:'))
    self.assertEqual('Checking',answer['state']);self.assertEqual('Unknown',answer['support'])
    self.assertFalse(answer['completed'])
 def test_execute_checks_actual_devices(self):
  with self.env(delivered=lambda *args:False):
   answer=self.runaction('execute')
  self.assertEqual('WaitingForDevices',answer['reason']);self.assertFalse(answer['completed'])
 def test_execute_needs_no_host_grant(self):
  with self.env(delivered=lambda *args:True):answer=self.runaction('execute')
  self.assertEqual('Succeeded',answer['state'])
 def test_qga_timeout_is_not_completion(self):
  with self.env(VmQga=self.qga(timeout=True),delivered=lambda *args:True):answer=self.runaction('execute')
  self.assertTrue(answer['reason'].startswith('OperationUncertain'));self.assertFalse(answer['completed'])
 def test_status_reads_without_revalidating_removed_devices(self):
  def wrong(*args):raise AssertionError('status must not use old target devices')
  with self.env(delivered=wrong):answer=self.runaction('status')
  self.assertEqual('Succeeded',answer['state'])
 def test_cancel_does_not_require_old_devices(self):
  def wrong(*args):raise AssertionError('cancel must not validate removed target devices')
  with self.env(delivered=wrong,VmQga=self.qga(response=dict(reason='OperationCancelled',state='Checking',completed=True))):answer=self.runaction('cancel')
  self.assertTrue(answer['completed']);self.assertEqual('OperationCancelled',answer['reason'])
 def test_cancel_timeout_is_not_completion(self):
  with self.env(VmQga=self.qga(timeout=True)):answer=self.runaction('cancel')
  self.assertFalse(answer['completed']);self.assertTrue(answer['reason'].startswith('OperationUncertain'))
 def test_qga_unavailable_does_not_claim_unsupported(self):
  qga=self.qga();qga.state='stopped'
  with self.env(VmQga=qga):answer=self.runaction('probe')
  self.assertEqual('WaitingForQga',answer['reason']);self.assertEqual('Unknown',answer['support'])

 def test_empty_output_is_unknown_for_every_action(self):
  for action in ('probe','inspect','status','cancel','execute'):
   for raw in [(0,None,''),(0,'',''),(0,' \n',''),(None,None,''),(137,'','terminated')]:
    with self.subTest(action=action,raw=raw),self.env(VmQga=self.qga(raw=raw),delivered=lambda *args:True):
     answer=self.runaction(action)
     self.assertEqual('Unknown',answer['support']);self.assertEqual('Checking',answer['state']);self.assertFalse(answer['completed'])
     prefix='ObservationUnavailable:' if action in ('probe','inspect') else 'OperationUncertain:'
     self.assertTrue(answer['reason'].startswith(prefix),answer)
 def test_malformed_or_missing_protocol_is_not_unsupported(self):
  for output in ('{}','null','[]','not json','{"protocolVersion":null}','{"protocolVersion":true}','{"protocolVersion":"2"}'):
   with self.subTest(output=output),self.env(VmQga=self.qga(raw=(0,output,''))):
    answer=self.runaction('probe');self.assertEqual('Unknown',answer['support']);self.assertFalse(answer['completed'])
 def test_failed_or_unknown_exit_cannot_confirm_any_protocol(self):
  for code in (1,None):
   for version in (2,3):
    with self.subTest(code=code,version=version),self.env(VmQga=self.qga(raw=(code,json.dumps(dict(protocolVersion=version)),''))):
     answer=self.runaction('cancel');self.assertEqual('Unknown',answer['support']);self.assertFalse(answer['completed'])
 def test_execution_evidence_keeps_stderr_out_of_persisted_summary(self):
  with self.env(VmQga=self.qga(raw=(137,'','private diagnostic')),delivered=lambda *args:True):answer=self.runaction('execute')
  execution=answer['diagnostics']['host']['guestExecution']
  self.assertEqual(137,execution['exitCode']);self.assertEqual(0,execution['stdoutBytes']);self.assertEqual('private diagnostic',execution['stderr'])
  summary=answer['diagnostics']['transport']['guestExecution'];self.assertEqual(137,summary['exitCode']);self.assertNotIn('stderr',summary)
  self.assertNotIn('private diagnostic',answer['reason'])
 def test_explicit_guest_unsupported_is_preserved(self):
  with self.env(VmQga=self.qga(response=dict(state='Failed',support='Unsupported',reason='UnsupportedOS'))):answer=self.runaction('probe')
  self.assertEqual('Unsupported',answer['support']);self.assertEqual('UnsupportedOS',answer['reason'])
 def test_protocol_file_absence_and_check_failure_are_distinct(self):
  for code in (1,2,None):
   with self.subTest(code=code),self.env(VmQga=self.qga(script_code=code)):
    answer=self.runaction('probe');self.assertEqual('Unsupported' if code==1 else 'Unknown',answer['support'])

 def test_invalid_optional_diagnostics_does_not_destroy_result(self):
  for action in ('probe','inspect','status','cancel','execute'):
   for value in (None,[],1,'bad'):
    with self.subTest(action=action,value=value),self.env(VmQga=self.qga(response=dict(diagnostics=value)),delivered=lambda *a:True):
     answer=self.runaction(action)
     self.assertIsInstance(answer['diagnostics'],dict)
     self.assertEqual('Checking' if action=='inspect' else 'Succeeded',answer['state'])
     self.assertIn('host',answer['diagnostics'])
 def test_invalid_reason_is_structured_unknown(self):
  for action in ('probe','inspect','status','cancel','execute'):
   with self.subTest(action=action),self.env(VmQga=self.qga(response=dict(reason=None,completed=True)),delivered=lambda *a:True):
    answer=self.runaction(action)
    self.assertEqual('Checking',answer['state']);self.assertEqual('Unknown',answer['support'])
    self.assertFalse(answer['completed']);self.assertIsInstance(answer['reason'],str)
 def test_error_paths_cleanup_without_claiming_completion(self):
  for kwargs in (dict(raw=(0,'','')),dict(raw=(0,'bad json','')),dict(version=2),dict(timeout=True),dict()):
   calls=[];base=self.qga(**kwargs)
   class Qga(base):
    def guest_exec_command(self,path,args,**kw):
     calls.append(path);return super().guest_exec_command(path,args,**kw)
   with self.subTest(kwargs=kwargs),self.env(VmQga=Qga,delivered=lambda *a:True):
    answer=self.runaction('execute')
   self.assertIn('/usr/bin/rm',calls);self.assertTrue(answer['requestSubmitted'])
   self.assertFalse(answer['completed'])
 def test_short_write_closes_only_the_unsubmitted_attempt(self):
  calls=[];base=self.qga()
  class Qga(base):
   def guest_file_write(self,*a,**k):return 0
   def guest_exec_python(self,*a,**k):raise AssertionError('must not submit')
   def guest_exec_command(self,path,args,**kw):calls.append(path);return super().guest_exec_command(path,args,**kw)
  with self.env(VmQga=Qga,delivered=lambda *a:True):answer=self.runaction('execute')
  self.assertFalse(answer['requestSubmitted']);self.assertTrue(answer['reason'].startswith('RequestNotSubmitted:'))
  self.assertFalse(answer['completed']);self.assertIn('/usr/bin/rm',calls)
 def test_guest_cannot_claim_host_did_not_submit(self):
  with self.env(VmQga=self.qga(response=dict(requestSubmitted=False)),delivered=lambda *a:True):answer=self.runaction('execute')
  self.assertTrue(answer['requestSubmitted'])
 def test_guest_cannot_overwrite_host_response_evidence(self):
  forged = dict(_guestExecution={}, _phase='forged', _stages=['forged'], success=False,
                error='forged', requestSubmitted=False, devices={'forged': '0000:00:01.0'},
                diagnostics=dict(host={'phase': 'forged'}, transport={'layer': 'forged'}))
  for action in ('probe', 'inspect', 'status', 'cancel', 'execute'):
   with self.subTest(action=action), self.env(VmQga=self.qga(response=forged), delivered=lambda *a:True):
    answer = self.runaction(action)
    self.assertTrue(answer['success'])
    self.assertNotIn('error', answer)
    host = answer['diagnostics']['host']
    self.assertEqual('guestResponse', host['phase'])
    self.assertEqual('admission', host['stages'][0]['phase'])
    self.assertEqual('guestResponse', host['stages'][-1]['phase'])
    self.assertEqual(0, host['guestExecution']['exitCode'])
    self.assertGreater(host['guestExecution']['stdoutBytes'], 0)
    self.assertEqual(0, host['guestExecution']['stderrBytes'])
    self.assertEqual('host', answer['diagnostics']['transport']['layer'])
    self.assertEqual(0, answer['diagnostics']['transport']['guestExecution']['exitCode'])
    self.assertFalse(any(key.startswith('_') for key in answer))
    if action == 'execute':
     self.assertTrue(answer['requestSubmitted'])
    else:
     self.assertNotIn('requestSubmitted', answer)
    if action in ('probe', 'inspect'):
     self.assertEqual({}, answer['devices'])
    else:
     self.assertNotIn('devices', answer)
 def test_guest_protocol_identity_and_recovery_fields_are_preserved(self):
  fields = dict(protocolVersion=3, operationId=self.cmd['operationId'], bootId='boot-one',
                state='Failed', reason='RecoveryRequired', reasonCode='RecoveryRequired',
                support='Supported', completed=True, recoveryRequired=True, recoveryNicUuid='c'*32,
                originalIdentity=dict(vmUuid=self.cmd['vmUuid'], bootId='boot-one', operationId=self.cmd['operationId']),
                identityMissingReason=None, target=dict(members=['0000:00:03.0', '0000:00:04.0']),
                capabilities=['standardNetworkModel', 'cancelPendingOperation'],
                failure=dict(code='ApplyFailed'), recovery=dict(action='rollback', succeeded=False))
  for action in ('probe', 'inspect', 'status', 'cancel', 'execute'):
   with self.subTest(action=action), self.env(VmQga=self.qga(response=fields), delivered=lambda *a:True):
    answer = self.runaction(action)
    for key, value in fields.items():
     self.assertEqual(value, answer[key], key)
 def test_cleanup_error_keeps_result_and_evidence(self):
  base=self.qga()
  class Qga(base):
   def guest_exec_command(self,path,args,**kw):
    if path=='/usr/bin/rm':raise TimeoutError('cleanup unavailable')
    return super().guest_exec_command(path,args,**kw)
  with self.env(VmQga=Qga,delivered=lambda *a:True):answer=self.runaction('execute')
  self.assertEqual('Succeeded',answer['state']);self.assertEqual('Failed',answer['diagnostics']['requestCleanup']['state'])
 def test_ordinary_device_gate_requires_both_identities(self):
  mac='00:11:22:33:44:55';pci='0000:00:03.0'
  for devices,expected,passed in [({},None,False),({mac:None},None,False),({},pci,False),({mac:pci},None,False),({mac:pci},'invalid',False),({mac:pci},'0000:00:04.0',False),({mac:pci},pci,True)]:
   self.cmd['operation']=dict(action='ports',target=dict(ports=[dict(mac=mac,guestPci=expected)]))
   with self.subTest(devices=devices,expected=expected),self.env(ordinary_devices=lambda *a:devices):answer=self.runaction('execute')
   self.assertEqual(passed,answer['requestSubmitted']);self.assertEqual('Succeeded' if passed else 'Checking',answer['state'])

if __name__=='__main__':unittest.main()

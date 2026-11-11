import ast,types,json,logging,traceback,pprint,functools,unittest
from unittest.mock import Mock
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def node(path,name,owner=None):
 tree=ast.parse(path.read_text());body=tree.body
 if owner:body=next(x for x in body if isinstance(x,ast.ClassDef) and x.name==owner).body
 return next(x for x in body if isinstance(x,(ast.FunctionDef,ast.ClassDef)) and x.name==name)
ctx=dict(functools=functools,traceback=traceback,pprint=pprint,logger=logging.getLogger('review'),
 jsonobject=types.SimpleNamespace(loads=lambda s:json.loads(s,object_hook=lambda d:types.SimpleNamespace(**d)),dumps=lambda o:json.dumps(vars(o))))
for n in ['AgentResponse','replyerror']:
 exec(compile(ast.Module(body=[node(root/'kvmagent.py',n)],type_ignores=[]),'actual-response-code','exec'),ctx)
ctx['kvmagent']=types.SimpleNamespace(AgentResponse=ctx['AgentResponse'],replyerror=ctx['replyerror']);ctx['http']=types.SimpleNamespace(REQUEST_BODY='body')
exec(compile(ast.Module(body=[node(root/'plugins/vm_plugin.py','AttachNicResponse'),node(root/'plugins/vm_plugin.py','attach_nic','VmPlugin')],type_ignores=[]),'actual-attach-code','exec'),ctx)

exec(compile(ast.Module(body=[node(root/'plugins/vm_plugin.py','stop_vm','VmPlugin')],type_ignores=[]),'actual-stop-code','exec'),ctx)
ctx['StopVmResponse']=ctx['AgentResponse'];ctx['kvmagent'].KvmError=RuntimeError

class CleanupTest(unittest.TestCase):
 def test_residual_check_failure_is_conservative(self):
  for residual in (False,True,RuntimeError('libvirt refresh unavailable')):
   vm=Mock();vm.attach_nic.side_effect=RuntimeError('original attachment failure')
   if isinstance(residual,Exception):vm._vf_device_xml.side_effect=residual
   else:vm._vf_device_xml.return_value='<hostdev/>' if residual else None
   ctx['get_vm_by_uuid']=lambda _:vm
   req={'body':json.dumps({'vmUuid':'a'*32,'nic':{'type':'VF','pciDeviceAddress':'0000:01:01.0','extraPciDeviceAddresses':['0000:02:01.0']}})}
   reply=json.loads(ctx['attach_nic'](None,req))
   self.assertFalse(reply['success']);self.assertEqual(residual is not False,reply['vfBondCleanupRequired'])
   self.assertIn('original attachment failure',reply['error'])
   if isinstance(residual,Exception):self.assertIn('libvirt refresh unavailable',reply['error'])
 def test_stop_checks_all_users_and_fails_if_process_survives(self):
  for process in ('nobody 123 qemu-system-x86_64',''):
   linux=Mock();linux.find_vm_process_by_uuid.return_value=process
   linux.wait_callback_success.side_effect=lambda callback,arg,**kw:callback(arg)
   ctx['linux']=linux
   req={'body':json.dumps({'uuid':'a'*32,'debug':False,'vmNics':[]})}
   reply=json.loads(ctx['stop_vm'](Mock(),req))
   self.assertEqual(not bool(process),reply['success'])
   linux.find_vm_process_by_uuid.assert_called_once_with('a'*32)
   linux.find_vm_pid_by_uuid.assert_not_called()

if __name__=='__main__':unittest.main()

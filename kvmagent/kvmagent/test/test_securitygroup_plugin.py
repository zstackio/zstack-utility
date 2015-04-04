'''

@author: frank
'''
import unittest
import time
from kvmagent import kvmagent
from kvmagent.plugins import securitygroup_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper


logger = log.get_logger(__name__)

#class TestSecurityGroupPlugin(unittest.TestCase):
class TestSecurityGroupPlugin(object):
    CALLBACK_URL = 'http://localhost:7070/testcallback'
    
    def callback(self, req):
        rsp = jsonobject.loads(req[http.REQUEST_BODY])
        print jsonobject.dumps(rsp)
        
    def setUp(self):
        self.service = kvmagent.new_rest_service()
        kvmagent.get_http_server().register_sync_uri('/testcallback', self.callback)
        self.service.start(True)
        time.sleep(1)


    def test_apply_rules(self):
        url = kvmagent._build_url_for_test([securitygroup_plugin.SecurityGroupPlugin.SECURITY_GROUP_APPLY_RULE_PATH])
        sto = securitygroup_plugin.SecurityGroupRuleTO()
        sto.vmNicInternalName = 'v1.0'
        rto = securitygroup_plugin.RuleTO()
        rto.allowedCidr = '192.168.100.1/24'
        rto.allowedInternalIpRange = ['10.1.1.1-10.1.1.10', '10.1.1.111']
        rto.endPort = 100
        rto.startPort = 20
        rto.protocol = securitygroup_plugin.SecurityGroupPlugin.PROTOCOL_TCP
        rto.type = securitygroup_plugin.SecurityGroupPlugin.RULE_TYPE_INGRESS
        sto.rules.append(rto)
        
        rto = securitygroup_plugin.RuleTO()
        rto.allowedCidr = '0.0.0.0/0'
        rto.allowedInternalIpRange = ['10.1.1.1-10.1.1.10', '10.1.1.111']
        rto.endPort = 55
        rto.startPort = 1
        rto.protocol = securitygroup_plugin.SecurityGroupPlugin.PROTOCOL_UDP
        rto.type = securitygroup_plugin.SecurityGroupPlugin.RULE_TYPE_EGRESS
        sto.rules.append(rto)
        
        rto = securitygroup_plugin.RuleTO()
        rto.allowedCidr = '1.1.1.1/24'
        rto.allowedInternalIpRange = ['10.1.1.1-10.1.1.10', '10.1.1.111']
        rto.endPort = -1
        rto.startPort = -1
        rto.protocol = securitygroup_plugin.SecurityGroupPlugin.PROTOCOL_ICMP
        rto.type = securitygroup_plugin.SecurityGroupPlugin.RULE_TYPE_INGRESS
        sto.rules.append(rto)
        
        cmd = securitygroup_plugin.ApplySecurityGroupRuleCmd()
        cmd.ruleTOs.append(sto)
        
        logger.debug('calling %s' % url)
        rsp = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        time.sleep(1)
        self.service.stop()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    #unittest.main()
    t = TestSecurityGroupPlugin()
    t.setUp()
    t.test_apply_rules()
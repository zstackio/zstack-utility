from kvmagent.test.utils.stub import *
from kvmagent.test.utils import network_utils, vm_utils
from kvmagent.test.mevoco_plugin_testsuite.mevoco_plugin_teststub import MevocoPluginTestStub
from zstacklib.utils import linux
from zstacklib.test.utils import misc
from unittest import TestCase
from zstacklib.utils.bash import *
from kvmagent.plugins import mevoco

init_kvmagent()
network_utils.init_mevoco_plugin()

__ENV_SETUP__ = {
    'self': {}
}


class TestNetwork(TestCase, MevocoPluginTestStub):
    bridge_name = None

    @classmethod
    def setUpClass(cls):
        cls.bridge_name = network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        mevoco.Mevoco.DHCP_DELETE_NAMESPACE_PATH,
    ])
    def test_batch_apply_dhcp(self):
        mac = "fa:b2:41:0a:16:00"
        ns_name = '%s_test_batch_apply_dhcp' % self.bridge_name

        rsp = network_utils.prepare_dhcp_by_batch_cmd(self.bridge_name, ns_name)
        self.assertTrue(rsp.success)

        rsp = network_utils.apply_dhcp_by_batch_cmd(mac, self.bridge_name, ns_name)
        self.assertTrue(rsp.success)

        pid = linux.find_process_by_cmdline(['dnsmasq', ns_name])
        self.assertIsNotNone(pid)

        dhcp_host_file = os.path.join('/var/lib/zstack/dnsmasq/', ns_name, 'hosts.dhcp')
        dhcp_option_file = os.path.join('/var/lib/zstack/dnsmasq/', ns_name, 'hosts.option')

        # TODO: we can do better check here
        # TODO: for example, check the exact format or get a dhcp tool to send a real DHCP request
        with open(dhcp_host_file, 'r') as fd:
            c = fd.read()
            self.assertTrue(mac in c)

        with open(dhcp_option_file, 'r') as fd:
            c = fd.read()
            self.assertTrue(mac.replace(':', '') in c)

        network_utils.delete_dhcp(self.bridge_name, ns_name)

        r = bash_r(
            "ip netns | grep -w %s | grep -v grep" % ns_name)
        self.assertEqual(r, 1, "namespace not delete")
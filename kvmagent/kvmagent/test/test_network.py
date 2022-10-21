from kvmagent.test.utils.stub import *
from kvmagent.test.utils import network_utils, vm_utils
from zstacklib.utils import linux
from zstacklib.test.utils import misc

init_kvmagent()
network_utils.init_mevoco_plugin()

from kvmagent.plugins import mevoco

__ENV_SETUP__ = {
    'current': {}
}


class TestNetwork(TestCase, vm_utils.VmPluginTestStub):
    bridge_name = None

    @classmethod
    def setUpClass(cls):
        cls.bridge_name = network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        mevoco.Mevoco.BATCH_PREPARE_DHCP_PATH,
        mevoco.Mevoco.BATCH_APPLY_DHCP_PATH,
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

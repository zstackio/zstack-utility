from kvmagent.test.utils import network_plugin_utils,pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from unittest import TestCase

network_plugin_utils.init_network_plugin()

PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {}
}


## describe: case will manage by ztest
class TestPhysicalNetworkInterface(TestCase):

    @classmethod
    def setUpClass(cls):
        return
    @pytest_utils.ztest_decorater
    def test_check_physical_network_interface(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        rsp = network_plugin_utils.check_physical_network_interface([interF])
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when check physical network interface")

    @pytest_utils.ztest_decorater
    def test_check_physical_network_interface_no_exsit(self):
        rsp = network_plugin_utils.check_physical_network_interface(["xxxxx"])
        rspO = jsonobject.loads(rsp)
        self.assertEqual(False, rspO.success, "Error happen when check physical network interface")





from kvmagent.test.utils import network_plugin_utils,pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc
from zstacklib.utils import iproute

network_plugin_utils.init_network_plugin()

PKG_NAME = __name__


__ENV_SETUP__ = {
    'self': {}
}

global_br_name=""
global_interface=""
global_l2_uuid=misc.uuid()

## describe: case will manage by ztest
class TestVxlanNetworkApi(TestCase):

    @classmethod
    def setUpClass(cls):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        global global_interface
        global_interface = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        return

    @pytest_utils.ztest_decorater
    def test_check_vxlan_cidr(self):
        global global_interface
        r, o = bash.bash_ro(
            "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}' | sed 's/ //g'" % global_interface)
        cidr = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        r, o = bash.bash_ro(
            "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % global_interface)
        vtepIp = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        rsp =network_plugin_utils.check_vxlan_cidr(
            global_interface, cidr, vtepIp
        )
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, rspO.error)

    @pytest_utils.ztest_decorater
    def test_populate_vxlan_cidr(self):
        global global_interface
        global global_l2_uuid
        global global_br_name

        br_name = "br_" + global_interface
        global_br_name = br_name

        r, o = bash.bash_ro(
            "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % global_interface)
        vtepIp = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        rsp = network_plugin_utils.create_vxlan_bridge(
            bridgeName=br_name,
            vtepIp=vtepIp,
            vni=1000,
            l2NetworkUuid=global_l2_uuid,
            peers=["192.168.100.250"],
            mtu=1400)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, rspO.error)



        # check in host
        isExsit = iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge not create on host")
        vxlanInterFIsExsit = iproute.is_device_ifname_exists("vxlan1000")
        self.assertTrue(vxlanInterFIsExsit, "[check] vxlan interface not create on host")

        # populate vxlan cidr
        rsp = network_plugin_utils.populate_vxlan_fdb(
            peers=["192.168.100.15", "192.168.100.56"],
            vni="1000"
        )
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, rspO.error)

        # check in host
        r,_ = bash.bash_ro('bridge fdb|grep vxlan1000|grep dst|grep 192.168.100.15')
        self.assertEqual(0, r, "[check] host not add fdb entry")
        r, _ = bash.bash_ro('bridge fdb|grep vxlan1000|grep dst|grep 192.168.100.56')
        self.assertEqual(0, r, "[check] host not add fdb entry")
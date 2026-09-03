from kvmagent.test.utils import network_plugin_utils,pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc
from zstacklib.utils import iproute
from unittest import TestCase

network_plugin_utils.init_network_plugin()

PKG_NAME = __name__


__ENV_SETUP__ = {
    'self': {}
}

## describe: case will manage by ztest
class TestBridgeApi(TestCase):

    @classmethod
    def setUpClass(cls):
        return

    @pytest_utils.ztest_decorater
    def test_create_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        br_name = "br_" + interF
        rsp = network_plugin_utils.create_bridge(
            physicalInterfaceName=interF,
            l2NetworkUuid=misc.uuid(),
            disableIptables=True,
            bridgeName=br_name)
        self.addCleanup(
            network_plugin_utils.delete_novlan_bridge,
            bridgeName=br_name,
            physicalInterfaceName=interF)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when create bridge")

        # check if create bridge in host
        isExsit = iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge not create on host")

        self.check_novlan_interface(br_name, interF)

    @pytest_utils.ztest_decorater
    def test_d_add_if_to_bridge(self):
        bridge_interface = "bri" + misc.uuid()[:8]
        interF = "phy" + misc.uuid()[:8]
        br_name = "br" + misc.uuid()[:8]
        iproute.add_link(bridge_interface, "dummy")
        self.addCleanup(iproute.delete_link, bridge_interface)
        iproute.add_link(interF, "dummy")
        self.addCleanup(iproute.delete_link, interF)
        rsp = network_plugin_utils.create_bridge(
            physicalInterfaceName=bridge_interface,
            l2NetworkUuid=misc.uuid(),
            disableIptables=True,
            bridgeName=br_name)
        self.addCleanup(
            network_plugin_utils.delete_novlan_bridge,
            bridgeName=br_name,
            physicalInterfaceName=interF)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when create bridge")
        linux.ip_link_set_net_device_nomaster(bridge_interface)

        rsp = network_plugin_utils.add_interface_to_bridge(
            bridgeName=br_name,
            physicalInterfaceName=interF)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when check physical network interface")
        self.assertTrue(
            linux.is_vif_on_bridge(br_name, interF),
            "[check] physical network interface not added to bridge")

    @pytest_utils.ztest_decorater
    def test_create_vlan_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        vlan_id = 1
        br_name = "br_" + interF + "_" + str(vlan_id)

        rsp = network_plugin_utils.create_vlan_bridge(
            bridgeName=br_name,
            vlan= vlan_id,
            l2NetworkUuid= misc.uuid(),
            disableIptables= True,
            physicalInterfaceName=interF)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when create bridge")

        # check in host
        isExsit = iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge not create on host")
        ## check if vlan interface exsit
        vlanInterFIsExsit = iproute.is_device_ifname_exists(interF+".1")
        self.assertTrue(vlanInterFIsExsit, "[check] vlan interface not create on host")

        # check with api
        self.check_vlan_interface(br_name, interF)


    def test_create_vxlan_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        vniId = 1000
        br_name = "br_" + interF + "_" + str(vniId)

        r, o = bash.bash_ro("ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % interF)
        vtepIp = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        rsp = network_plugin_utils.create_vxlan_bridge(
            bridgeName=br_name,
            vtepIp= vtepIp,
            vni = vniId,
            l2NetworkUuid= misc.uuid(),
            peers= ["192.168.100.250"],
            mtu=1400)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when create bridge")

        # check in host
        isExsit = iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge not create on host")
        ## check if vlan interface exsit

        # clean bridge

    def check_novlan_interface(self,bridgeName=None, physicalInterfaceName=None):
        network_plugin_utils.check_bridge(
            bridgeName = bridgeName,
            physicalInterfaceName = physicalInterfaceName
        )

    def check_vlan_interface(self,bridgeName=None, physicalInterfaceName=None):
        network_plugin_utils.check_vlan_bridge(
            bridgeName = bridgeName,
            physicalInterfaceName = physicalInterfaceName
        )


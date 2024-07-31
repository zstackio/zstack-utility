import time

from kvmagent.test.utils import network_plugin_utils, pytest_utils
from zstacklib.utils import jsonobject, bash
from zstacklib.test.utils import misc
from zstacklib.utils import iproute
from zstacklib.utils import netconfig
from unittest import TestCase

network_plugin_utils.init_network_plugin()

PKG_NAME = __name__


__ENV_SETUP__ = {
    'self': {}
}

global_br_name=""

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
        global global_br_name
        global_br_name = br_name
        rsp = network_plugin_utils.create_bridge(
            physicalInterfaceName=interF,
            l2NetworkUuid=misc.uuid(),
            disableIptables=True,
            bridgeName=br_name)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when create bridge")

        # check if create bridge in host
        isExsit = iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge not create on host")

        self.check_novlan_bridge(br_name, interF)
        # clean bridge, not compatible with Kylin yet
        if netconfig.use_network_manager():
            return

        network_plugin_utils.delete_vlan_bridge(bridgeName=br_name, physicalInterfaceName=interF)
        isExsit = not iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge exist on host")


    @pytest_utils.ztest_decorater
    def test_add_if_to_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==2{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        # physical interface from configuration
        rsp = network_plugin_utils.add_interface_to_bridge(
            bridgeName=global_br_name,
            physicalInterfaceName=interF)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when add interface to bridge")

    @pytest_utils.ztest_decorater
    def test_create_vlan_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        vlan_id = 1
        vlan_interF = "%s.%s" % (interF, vlan_id)
        br_name = "br_%s_%s" % (interF, vlan_id)

        rsp = network_plugin_utils.create_vlan_bridge(
            bridgeName=br_name,
            vlan=vlan_id,
            l2NetworkUuid=misc.uuid(),
            disableIptables=True,
            physicalInterfaceName=interF)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when create bridge")

        # check in host
        isExsit = iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge not create on host")
        # check if vlan interface exist
        vlanInterFIsExsit = iproute.is_device_ifname_exists(vlan_interF)
        self.assertTrue(vlanInterFIsExsit, "[check] vlan interface not create on host")

        # check with api
        self.check_vlan_bridge(br_name, interF)

        # clean bridge
        if netconfig.use_network_manager():
            return

        network_plugin_utils.delete_vlan_bridge(bridgeName=br_name, physicalInterfaceName=interF, vlan=vlan_id)
        isExsit = not iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge exist on host")
        vlanInterFIsExsit = not iproute.is_device_ifname_exists(vlan_interF)
        self.assertTrue(vlanInterFIsExsit, "[check] vlan interface exist on host")

    def test_create_vxlan_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        vni = 1000
        br_name = "br_vx_%s" % vni

        if netconfig.use_network_manager():
            interF = global_br_name

        r, o = bash.bash_ro("ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % interF)
        vtepIp = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        rsp = network_plugin_utils.create_vxlan_bridge(
            bridgeName=br_name,
            vtepIp=vtepIp,
            vni=vni,
            l2NetworkUuid=misc.uuid(),
            peers=["192.168.100.250"],
            mtu=1400)
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when create bridge")

        # check in host
        isExsit = iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge not create on host")

    def check_novlan_bridge(self, bridgeName=None, physicalInterfaceName=None):
        network_plugin_utils.check_bridge(
            bridgeName = bridgeName,
            physicalInterfaceName = physicalInterfaceName
        )

    def check_vlan_bridge(self, bridgeName=None, physicalInterfaceName=None):
        network_plugin_utils.check_vlan_bridge(
            bridgeName = bridgeName,
            physicalInterfaceName = physicalInterfaceName
        )

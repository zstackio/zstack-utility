import pytest

from kvmagent.test.utils import network_plugin_utils, pytest_utils
from zstacklib.utils import jsonobject, bash
from zstacklib.test.utils import misc
from zstacklib.utils import iproute
from unittest import TestCase

network_plugin_utils.init_network_plugin()

PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {}
}

global_vlan_id = None


## describe: case will manage by ztest
class TestBridgeApi(TestCase):

    @classmethod
    def setUpClass(cls):
        return

    @pytest.mark.run(order=1)
    @pytest_utils.ztest_decorater
    def test_01_create_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        br_name = "br_" + interF
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

    @pytest.mark.run(order=2)
    @pytest_utils.ztest_decorater
    def test_create_vlan_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        global global_vlan_id
        global_vlan_id = 1
        vlan_interF = "%s.%s" % (interF, global_vlan_id)
        br_name = "br_%s_%s" % (interF, global_vlan_id)

        rsp = network_plugin_utils.create_vlan_bridge(
            bridgeName=br_name,
            vlan=global_vlan_id,
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

    @pytest.mark.run(order=3)
    @pytest_utils.ztest_decorater
    def test_batch_update_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        br_name = "br_" + interF
        vlan_br_name = "br_%s_%s" % (interF, global_vlan_id)
        bonding_name = "bond0"
        new_bonding = {
            "bondName": bonding_name,
            "slaves": [{
                "interfaceName": interF
            }],
            "type": "LinuxBonding",
            "mode": "active-backup"
        }
        bridge_params = [{
                "bridgeName": br_name,
                "vlanId": 0,
                "l2NetworkUuid": misc.uuid(),
            },
            {
                "bridgeName": vlan_br_name,
                "vlanId": global_vlan_id,
                "l2NetworkUuid": misc.uuid(),
            }]
        rsp = network_plugin_utils.batch_update_bridge(
            old_physical_interface=interF,
            new_bonding=new_bonding,
            bridge_params=bridge_params
        )
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when batch update bridge")
        # check if bonding exist
        bonding_exist = iproute.is_device_ifname_exists(bonding_name)
        self.assertTrue(bonding_exist, "[check] bonding not create on host")

        rsp = network_plugin_utils.batch_update_bridge(
            old_bonding_name=bonding_name,
            new_physical_interface=interF,
            bridge_params=bridge_params
        )
        rspO = jsonobject.loads(rsp)
        self.assertEqual(True, rspO.success, "Error happen when batch update bridge")
        # check if bonding not exist
        bonding_not_exist = not iproute.is_device_ifname_exists(bonding_name)
        self.assertTrue(bonding_not_exist, "[check] bonding not delete on host")

    @pytest.mark.run(order=4)
    @pytest_utils.ztest_decorater
    def test_delete_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        br_name = "br_" + interF

        network_plugin_utils.delete_vlan_bridge(bridgeName=br_name, physicalInterfaceName=interF)
        isExsit = not iproute.is_device_ifname_exists(br_name)
        self.assertTrue(isExsit, "[check] bridge exist on host")

        vlan_interF = "%s.%s" % (interF, global_vlan_id)
        vlan_br_name = "br_%s_%s" % (interF, global_vlan_id)
        network_plugin_utils.delete_vlan_bridge(bridgeName=vlan_br_name, physicalInterfaceName=interF,
                                                vlan=global_vlan_id)
        isExsit = not iproute.is_device_ifname_exists(vlan_br_name)
        self.assertTrue(isExsit, "[check] bridge exist on host")
        vlanInterFIsExsit = not iproute.is_device_ifname_exists(vlan_interF)
        self.assertTrue(vlanInterFIsExsit, "[check] vlan interface exist on host")

    @pytest.mark.run(order=5)
    @pytest_utils.ztest_decorater
    def test_create_vxlan_bridge(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        vni = 1000
        br_name = "br_vx_%s" % vni

        r, o = bash.bash_ro(
            "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % interF)
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
            bridgeName=bridgeName,
            physicalInterfaceName=physicalInterfaceName
        )

    def check_vlan_bridge(self, bridgeName=None, physicalInterfaceName=None):
        network_plugin_utils.check_vlan_bridge(
            bridgeName=bridgeName,
            physicalInterfaceName=physicalInterfaceName
        )

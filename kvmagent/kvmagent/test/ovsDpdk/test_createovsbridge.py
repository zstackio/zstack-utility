import unittest
from kvmagent.plugins import network_plugin
from kvmagent.plugins import vm_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper
from kvmagent.plugins import ovsdpdk_network
from zstacklib.utils import linux
from zstacklib.utils import jsonobject
from zstacklib.utils import bash
import time
import pytest

ofed_not_exsit = True


class Test():

    def __init__(self):
        ret, o = bash.bash_ro("lspci |grep -i eth|grep -i Mellanox")
        self.phyIf =

    @classmethod
    def setup_class(self):
        ret,_ = bash.bash_ro("ofed_info -l")
        if ret == 0:
            ofed_not_exsit = False
        else:
            return

        ret, _ = bash.bash_ro("lspci |grep -i eth|grep -i Mellanox")
        if ret == 0:
            ofed_not_exsit = False
        else:
            return


        self.NET_PLUGIN = network_plugin.NetworkPlugin()
        self.NET_PLUGIN.configure()

        self.DPDK_PLUGIN = ovsdpdk_network.OvsDpdkNetworkPlugin()
        self.DPDK_PLUGIN.configure()

    @pytest.mark.skipif(ofed_not_exsit==False, reason=None)
    def test_dpdkl2_CheckPhysicalNetworkInterface(self):
        cmd = network_plugin.CheckPhysicalNetworkInterfaceCmd()
        cmd.interfaceNames = ["eno1"]
        print 'check ovs bond0 %s' % cmd.interfaceNames


        self.NET_PLUGIN.check_physical_network_interface(({"body": jsonobject.dumps(cmd)}))
        return

    #@pytest.mark.skipif(ofed_not_exsit==False, reason=None)
    @pytest.mark.skip(reason=None)
    def test_checkOvsBridge(self):
        #start vm will check bridge
        cmd = ovsdpdk_network.CheckBridgeCmd()
        cmd.bridgeName = "br_ovsBond2"
        cmd.physicalInterfaceName = "ovsBond2"

        self.DPDK_PLUGIN.check_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    @pytest.mark.skip(reason=None)
    def test_createOvsBridge_one(self):
        cmd = ovsdpdk_network.CreateBridgeCmd()
        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"

        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

    @pytest.mark.skip(reason=None)
    def test_createOvsBridge_idempotence(self):
        cmd = ovsdpdk_network.CreateBridgeCmd()
        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"

        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        _, pid_for_test_createOvsBridge_idempotence = bash.bash_ro(
            "ps -ef|grep -i ovs-vswitchd.pid|grep -v 'grep'|awk '{print $2}'")

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"

        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))
        _, pid_for_test_createOvsBridge_idempotence2 = bash.bash_ro(
            "ps -ef|grep -i ovs-vswitchd.pid|grep -v 'grep'|awk '{print $2}'")

        print "pid1 %s" % pid_for_test_createOvsBridge_idempotence
        print "pid2 %s" % pid_for_test_createOvsBridge_idempotence2

        assert pid_for_test_createOvsBridge_idempotence == pid_for_test_createOvsBridge_idempotence2

    def test_createSameOvsBridge_tentimes(self):
        cmd = ovsdpdk_network.CreateBridgeCmd()
        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"
        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))




    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    @pytest.mark.skip(reason=None)
    def test_deleteOvsBridge(self):
        cmd = ovsdpdk_network.DeleteBridgeCmd()
        cmd.bridgeName = "br_ovsBond2"


        self.DPDK_PLUGIN.delete_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

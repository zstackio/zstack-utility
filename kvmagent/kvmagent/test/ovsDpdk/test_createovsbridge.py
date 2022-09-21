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
from zstacklib.utils import thread
import time
import pytest

ofed_not_exsit = True


class Test():

    @classmethod
    def setup_class(self):

        self.NET_PLUGIN = network_plugin.NetworkPlugin()
        self.DPDK_PLUGIN = ovsdpdk_network.OvsDpdkNetworkPlugin()

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

    @pytest.mark.skip(reason=None)
    def test_createSameOvsBridge_tentimes(self):
        def createSameOvsBridge(cmd):
            self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        threads = []
        for i in range(1,10):
            cmd = ovsdpdk_network.CreateBridgeCmd()
            cmd.bridgeName = "br_enp101s0f0"
            cmd.physicalInterfaceName = "enp101s0f0"

            threads.append(thread.ThreadFacade.run_in_thread(createSameOvsBridge, [cmd]))
        for t in threads:
            t.join()

    @pytest.mark.skip(reason=None)
    def test_createDifferentOvsBridge_tentimes(self):
        def createDifferentOvsBridge(cmd):
            self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        threads = []
        for i in range(1,10):
            cmd = ovsdpdk_network.CreateBridgeCmd()
            cmd.bridgeName = "br_enp101s0f0"
            cmd.physicalInterfaceName = "enp101s0f0"
            if i == 2:
                cmd.bridgeName = "br_enp101s0f1"
                cmd.physicalInterfaceName = "enp101s0f1"

            threads.append(thread.ThreadFacade.run_in_thread(createDifferentOvsBridge, [cmd]))
        for t in threads:
            t.join()

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    @pytest.mark.skip(reason=None)
    def test_deleteOvsBridge(self):
        def deleteDifferentOvsBridge(cmd):
            self.DPDK_PLUGIN.delete_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        threads = []
        for i in range(1,10):
            cmd = ovsdpdk_network.DeleteBridgeCmd()
            cmd.bridgeName = "br_enp101s0f0"
            if i == 2:
                cmd.bridgeName = "br_enp101s0f1"
            threads.append(thread.ThreadFacade.run_in_thread(deleteDifferentOvsBridge, [cmd]))
        for t in threads:
            t.join()

    def test_createSameOvsBridge_50times(self):
        def createSameOvsBridge(cmd):
            self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        time_start = time.time()
        threads = []
        for i in range(1,50):
            cmd = ovsdpdk_network.CreateBridgeCmd()
            cmd.bridgeName = "br_enp101s0f0"
            cmd.physicalInterfaceName = "enp101s0f0"

            threads.append(thread.ThreadFacade.run_in_thread(createSameOvsBridge, [cmd]))
        for t in threads:
            t.join()
        time_end = time.time()
        time_cost = time_end - time_start
        query_fast = True
        if time_cost > 10:
            query_fast = False
        assert  query_fast == True

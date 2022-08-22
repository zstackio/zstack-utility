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


class Test():
    ofed_not_exsit = True
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

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    @pytest.mark.skip(reason=None)
    def test_dpdkl2_CheckPhysicalNetworkInterface(self):
        cmd = network_plugin.CheckPhysicalNetworkInterfaceCmd()
        cmd.interfaceNames = ["eno1"]
        print 'check ovs bond0 %s' % cmd.interfaceNames


        self.NET_PLUGIN.check_physical_network_interface(({"body": jsonobject.dumps(cmd)}))
        return

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    @pytest.mark.skip(reason=None)
    def test_checkOvsBridge(self):
        #start vm will check bridge
        cmd = ovsdpdk_network.CheckBridgeCmd()
        cmd.bridgeName = "br_ovsBond2"
        cmd.physicalInterfaceName = "ovsBond2"

        self.DPDK_PLUGIN.check_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    @pytest.mark.skip(reason=None)
    def test_createOvsBridge(self):
        cmd = ovsdpdk_network.CreateBridgeCmd()
        cmd.bridgeName = "br_ovsBond2"
        cmd.physicalInterfaceName = "ovsBond2"

        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    @pytest.mark.skip(reason=None)
    def test_deleteOvsBridge(self):
        cmd = ovsdpdk_network.DeleteBridgeCmd()
        cmd.bridgeName = "br_ovsBond2"


        self.DPDK_PLUGIN.delete_ovs_bridge(({"body": jsonobject.dumps(cmd)}))


    # test vm migrate
    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    def test_generatevdpa(self):
        cmd = ovsdpdk_network.GenerateVdpaCmd()
        nics = vm_plugin.NicTO()
        # interface info
        nics.mac = "fa:46:e3:1b:ab:01"
        # last step create the ovs bridge
        nics.bridgeName = "br_enp101s0f0"
        nics.uuid = "886203c1c7dd4628881970841df121d"
        nics.nicInternalName = "vnic389.0"
        nics.deviceId = 2
        nics.useVirtio = True
        nics.bootOrder = 0
        nics.mtu = 1500
        nics.type = "vDPA"
        nics.vHostAddOn = vHostAddOn()
        nics.physicalInterface = "enp101s0f0"
        nics.pciDeviceAddress = "0000:65:00.4"

        cmd.nics = [nics]
        cmd.vmUuid = "229lka53b2bd404ebae63d69c255555"

        self.DPDK_PLUGIN.generate_vdpa(({"body": jsonobject.dumps(cmd)}))

    def test_deletevdpa(self):
        cmd = ovsdpdk_network.DeleteVdpaCmd()
        cmd.vmUuid = "229lka53b2bd404ebae63d69c255555"
        cmd.nicInternalName = "vnic389.0"

        self.DPDK_PLUGIN.delete_vdpa(({"body": jsonobject.dumps(cmd)}))

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    def test_createVdpaNic(self):
        return

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    def test_preparedhcp(self):
        return

    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    def test_deletedhcp(self):
        return

class vHostAddOn():
    def __init__(self):
        self.queueNum = None

class Volume():

    def __init__(self):
        self.installPath = None
        self.deviceType = None
        self.volumeUuid = None
        self.useVirtio = None
        self.useVirtioSCSI = None
        self.shareable = None
        self.cacheMode = None
        self.wwn = None
        self.bootOrder = None
        self.physicalBlockSize = None

class Addon():
    def __init__(self):
        self.channel = None
        self.numaNodes = None


class PriorityConfigStruct():
    def __init__(self):
        self.vmUuid = None
        self.cpuShares = None
        self.oomScoreAdj = None
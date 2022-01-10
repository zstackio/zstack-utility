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
from zstacklib.utils import shell
from zstacklib.utils import thread
import time
import pytest


class Test():
    @classmethod
    def setup_class(self):
        ret,_ = bash.bash_ro("ofed_info -l")
        if ret != 0:
            return
        ## todo: run this case by auto, not set parm Manually
        self.pf = "enp101s0f0"
        self.vfs = []

        self.NET_PLUGIN = network_plugin.NetworkPlugin()
        self.NET_PLUGIN.configure()

        self.DPDK_PLUGIN = ovsdpdk_network.OvsDpdkNetworkPlugin()
        self.DPDK_PLUGIN.configure()

    def test_createOvsBridge(self):
        cmd = ovsdpdk_network.CreateBridgeCmd()
        cmd.bridgeName = "br_" + self.pf
        cmd.physicalInterfaceName = self.pf

        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

    # test vm migrate
    #@pytest.mark.skipif(condition=ofed_not_exsit, reason=None)
    def test_batchGeneratevdpa(self):

        def generatevdpa(cmd):
            self.DPDK_PLUGIN.generate_vdpa(({"body": jsonobject.dumps(cmd)}))

        vfs = self.get_vf()
        print vfs
        threads = []
        for idx, vf in enumerate(vfs, start=0):
            cmd = ovsdpdk_network.GenerateVdpaCmd()
            nics = vm_plugin.NicTO()
            # interface info
            nics.mac = "fa:46:e3:1b:ab:01"
            # last step create the ovs bridge
            nics.bridgeName = "br_" + self.pf
            nics.uuid = "886203c1c7dd4628881970841df121" + str(idx)
            nics.nicInternalName = "vnic389." + str(idx)
            nics.deviceId = 2
            nics.useVirtio = True
            nics.bootOrder = 0
            nics.mtu = 1500
            nics.type = "vDPA"
            nics.vHostAddOn = vHostAddOn()
            nics.physicalInterface = self.pf
            nics.pciDeviceAddress = "0000:" + vf.strip()
            cmd.nics = [nics]
            cmd.vmUuid = "229lka53b2bd404ebae63d69c255555"

            threads.append(thread.ThreadFacade.run_in_thread(generatevdpa, [cmd]))
        for t in threads:
            t.join()
        return nics

    @pytest.mark.skip( reason=None)
    def test_deletevdpa(self):
        cmd = ovsdpdk_network.DeleteVdpaCmd()
        cmd.vmUuid = "229lka53b2bd404ebae63d69c255555"
        cmd.nicInternalName = "vnic389.0"

        self.DPDK_PLUGIN.delete_vdpa(({"body": jsonobject.dumps(cmd)}))

    def get_vf(self):
        try:
            ret = shell.call("lspci |grep -i eth|grep 'Virtual Function'|awk '{print $1}'")
        except shell.ShellError as err:
            return []
        else:
            return ret.strip().splitlines()
class vHostAddOn():
    def __init__(self):
        self.queueNum = None
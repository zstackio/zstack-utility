import unittest
from kvmagent import kvmagent
from kvmagent.plugins import host_plugin
from kvmagent.plugins import network_plugin
from kvmagent.plugins import vm_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper
from kvmagent.plugins import ovsdpdk_network
from zstacklib.utils import linux
from zstacklib.utils import jsonobject

import time
CALLBACK_URL = 'http://localhost:7070/testcallback'
def asyncPost(path, cmd):
    url = kvmagent._build_url_for_test([network_plugin.CHECK_PHYSICAL_NETWORK_INTERFACE_PATH])
    ret = http.json_dump_post(url, cmd,headers={http.TASK_UUID: uuidhelper.uuid(), http.CALLBACK_URI: CALLBACK_URL})
    rsp = jsonobject.loads(ret)
    return rsp

class Test(unittest.TestCase):
    CALLBACK_URL = 'http://localhost:7070/testcallback'

    def setUp(self):
        #check env is ready


        self.service = kvmagent.new_rest_service()
        kvmagent.get_http_server().register_sync_uri('/testcallback', self.callback)
        self.service.start(True)
        time.sleep(10)



    def tearDown(self):
        self.service.stop()


    def test_dpdkl2_CheckPhysicalNetworkInterface(self):
        cmd = network_plugin.CheckPhysicalNetworkInterfaceCmd()
        cmd.interfaceNames = ["ovs-bond0"]
        print 'check ovs bond0 %s' % cmd.interfaceNames
        url = kvmagent._build_url_for_test([network_plugin.CHECK_PHYSICAL_NETWORK_INTERFACE_PATH])
        ret = http.json_dump_post(url, cmd, headers={http.TASK_UUID:uuidhelper.uuid(), http.CALLBACK_URI:self.CALLBACK_URL})
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success)
        time.sleep(30)

    def test_checkOvsBridge(self):
        #start vm will check bridge
        cmd = ovsdpdk_network.CheckBridgeCmd()
        cmd.bridgeName = "br_ovsBond2"
        cmd.physicalInterfaceName = "ovsBond2"
        rsp = asyncPost(ovsdpdk_network.OVS_DPDK_NET_CHECK_BRIDGE, cmd)
        self.assertFalse(rsp.success)
        time.sleep(5)

    def test_createOvsBridge(self):
        cmd = ovsdpdk_network.CreateBridgeCmd()
        cmd.bridgeName = "br_ovsBond2"
        cmd.physicalInterfaceName = "ovsBond2"

        asyncPost(ovsdpdk_network.OVS_DPDK_NET_CREATE_BRIDGE, cmd)
        time.sleep(30)
        return

    def test_startVmL2Dpdk(self):
        cmd = vm_plugin.StartVmCmd()
        cmd.vmName = 'test'
        cmd.vmUuid = uuidhelper.uuid()
        cmd.cpuNum = 2
        cmd.cpuSpeed = 3000
        cmd.memory = 2147483648
        cmd.maxMemory = 67027107840
        cmd.socketNum = 1
        cmd.cpuOnSocket = 2
        cmd.rootVolume.installPath = ""
        cmd.rootVolume.deviceId
        cmd.rootVolume.deviceType
        cmd.rootVolume.volumeUuid
        cmd.rootVolume.useVirtio = True
        cmd.rootVolume.useVirtioSCSI = False
        cmd.rootVolume.shareable = False
        cmd.rootVolume.cacheMode = "none"
        cmd.rootVolume.wwn = "0x000f2517a55862a9"
        cmd.rootVolume.bootOrder = 1
        cmd.rootVolume.physicalBlockSize = 0


        # interface info
        cmd.nics[0].mac = "fa:46:e8:1b:ab:00"
        #last step create the ovs bridge
        cmd.nics[0].bridgeName = "br_ovsBond2"
        cmd.nics[0].physicalInterface = "ovsBond2"
        cmd.nics[0].uuid = "9f5b03c1c7dd462cbf91970841df121d"
        cmd.nics[0].nicInternalName = "vnic391.0"
        cmd.nics[0].deviceId = 0
        cmd.nics[0].useVirtio = True
        cmd.nics[0].bootOrder = 0
        cmd.nics[0].mtu = 1500
        cmd.nics[0].type = "vDPA"

        cmd.timeout = 300

        cmd.addons.channel.socketPath = "/var/lib/libvirt/qemu/365242a14243442b9a22d8b00af82ac5"



        print
        'xxxxxxxxxxxxxxxxxxx %s' % cmd.vmUuid
        url = kvmagent._build_url_for_test([vm_plugin.KVM_START_VM_PATH])
        rsp = http.json_dump_post(url, cmd,
                                  headers={http.TASK_UUID: uuidhelper.uuid(), http.CALLBACK_URI: self.CALLBACK_URL})
        time.sleep(30)
        self.service.stop()
        return

    # test vm migrate
    def test_generatevdpa(self):
        return

    def test_createVdpaNic(self):
        return

    def test_preparedhcp(self):
        return

    def test_deletedhcp(self):
        return

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
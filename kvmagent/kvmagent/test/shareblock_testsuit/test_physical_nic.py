import time
from kvmagent.test.shareblock_testsuit.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import shareblock_utils,pytest_utils,storage_device_utils, vm_utils, ha_utils, network_utils
from unittest import TestCase
from zstacklib.test.utils import misc,env
from zstacklib.utils import jsonobject, xmlobject, bash, linux, log
import pytest

PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init':['bash ./createiSCSIStroage.sh'],
        'timeout': 1800
    }
}

global hostUuid
global vgUuid

class TestPhysicalnic(TestCase,SharedBlockPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_physical_nic_down(self):
        rsp = SharedBlockPluginTestStub().login()
        self.assertEqual(rsp.success, True, "iscsiadm login failed")

        global hostUuid
        hostUuid = misc.uuid()

        global vgUuid
        vgUuid = misc.uuid()

        rsp, blockUuid = SharedBlockPluginTestStub().connect(hostUuid, vgUuid)
        self.assertEqual(rsp.success, True, "share block connect failed")

        imageUuid = misc.uuid()
        # download image to shareblock
        print('lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(
            imageUuid, vgUuid))
        r, o = bash.bash_ro(
            'lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(
                imageUuid, vgUuid))
        self.assertEqual(0, r, "create lv failed, because {}".format(o))

        r, o = bash.bash_ro("cp /root/.zguest/min-vm.qcow2 /dev/{}/{}".format(vgUuid, imageUuid))
        self.assertEqual(0, r, "cp image failed, because {}".format(o))

        # create volume
        # test disconnect shareblock
        volumeUuid = misc.uuid()
        rsp = shareblock_utils.shareblock_create_root_volume(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid, imageUuid),
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            volumeUuid=volumeUuid,
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=blockUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        r, o = bash.bash_ro("lvs --nolocking -t |grep %s" % volumeUuid)
        self.assertEqual(0, r, "create volume fail in host")

        bash.bash_r("lvchange -ay -K /dev/{}/{}".format(vgUuid, volumeUuid))

        startVmCmdBody = {
            "vmInstanceUuid": "0b42630f37d8417480eced62ad89719f",
            "vmInternalId": 1,
            "vmName": "vm-for-ut",
            "imagePlatform": "Linux",
            "imageArchitecture": "x86_64",
            "memory": 67108864,  # 64M
            # "memory": 16384,  # 64M
            "maxMemory": 134217728,  # 128M
            "cpuNum": 1,
            "cpuSpeed": 0,
            "socketNum": 1,
            "cpuOnSocket": 1,
            "bootDev": ["hd"],
            "rootVolume": {
                "installPath": "/dev/{}/{}".format(vgUuid, volumeUuid),
                "deviceId": 0,
                "deviceType": "file",
                "volumeUuid": "d387b4534faf4553a50a8a632cf12e35",
                "useVirtio": True,
                "useVirtioSCSI": False,
                "shareable": False,
                "cacheMode": "none",
                "wwn": "0x000fb964dbc7a10a",
                "bootOrder": 1,
                "physicalBlockSize": 0
            },
            "bootIso": [],
            "cdRoms": [],
            "dataVolumes": [],
            "cacheVolumes": [],
            "nics": [{
                "mac": "fa:62:4a:61:6c:00",
                "bridgeName": "br_%s" % env.DEFAULT_ETH_INTERFACE_NAME,
                "physicalInterface": env.DEFAULT_ETH_INTERFACE_NAME,
                "uuid": "8f9ef2e5061a4b28b5f79ff24ab0c0ce",
                "nicInternalName": "vnic1.0",
                "deviceId": 0,
                "useVirtio": True,
                "bootOrder": 0,
                "mtu": 1500,
                "driverType": "virtio",
                "vHostAddOn": {
                    "queueNum": 1
                }
            }],
            "timeout": 300,
            "addons": {
                "channel": {
                    "socketPath": "/var/lib/libvirt/qemu/0b42630f37d8417480eced62ad89719f",
                    "targetName": "org.qemu.guest_agent.0"
                },
                "usbDevice": []
            },
            "instanceOfferingOnlineChange": False,
            "nestedVirtualization": "none",
            "hostManagementIp": "10.0.245.48",
            "clock": "utc",
            "useNuma": True,
            "useBootMenu": True,
            "createPaused": False,
            "kvmHiddenState": False,
            "vmPortOff": False,
            "emulateHyperV": False,
            "additionalQmp": True,
            "isApplianceVm": False,
            "systemSerialNumber": "4f3e9046-776d-4095-8edd-909523ede46d",
            "bootMode": "Legacy",
            "fromForeignHypervisor": False,
            "machineType": "pc",
            "useHugePage": False,
            "chassisAssetTag": "www.zstack.io",
            "priorityConfigStruct": {
                "vmUuid": "0b42630f37d8417480eced62ad89719f",
                "cpuShares": 512,
                "oomScoreAdj": 0
            },
            "coloPrimary": False,
            "coloSecondary": False,
            "consoleLogToFile": False,
            "useColoBinary": False,
            "consoleMode": "vnc",
            "MemAccess": "private",
            "videoType": "cirrus",
            "spiceStreamingMode": "off",
            "VDIMonitorNumber": 1,
            "kvmHostAddons": {
                "qcow2Options": " -o cluster_size=2097152 "
            }
        }

        vm = jsonobject.loads(jsonobject.dumps(startVmCmdBody))
        vm_utils.create_vm(vm)
        pid = linux.find_vm_pid_by_uuid(vm.vmInstanceUuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm.vmInstanceUuid)

        addons = {"qcow2Options": " -o cluster_size=2097152 "}
        rsp = ha_utils.setup_sharedblock_self_fencer(vgUuid, hostUuid, "None", addons, "None", 1, 1, 5, "Force",
                                                     ["hostBusinessNic"])

        r, o = bash.bash_ro("ip link set ens3 down")
        self.assertEqual(0, r)
        time.sleep(10)

        r, o = bash.bash_ro("virsh list")
        self.assertEqual(0, r)
        assert len(o) == 0

        
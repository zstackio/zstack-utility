import time

from kvmagent.plugins import ha_plugin
from kvmagent.test.nfs_testsuit.test_ha_plugin_testsub import NfsPluginTestStub
from kvmagent.test.shareblock_testsuit.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import ha_utils,pytest_utils,storage_device_utils, vm_utils, nfs_plugin_utils, network_utils
from unittest import TestCase
from zstacklib.test.utils import misc,env
from zstacklib.utils import jsonobject, xmlobject, bash, linux, log, shell
import pytest


PKG_NAME = __name__

logger = log.get_logger(__name__)

# must create nfs stroage before run test

__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init':['bash ./createNFSStroage.sh']
    }
}

global hostUuid
global vgUuid
global primaryStorageUuid

class TestHaNfsPlugin(TestCase, NfsPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_ha_in_nfs(self):
        global hostUuid
        hostUuid = misc.uuid()

        volumeUuid = misc.uuid()

        global vgUuid
        primaryStorageUuid = misc.uuid()

        imageUuid = misc.uuid()

        url = NfsPluginTestStub().mount(primaryStorageUuid)

        image_path = "/opt/zstack/nfsprimarystorage/prim-{}/imagecache/template/{}/".format(primaryStorageUuid, imageUuid)
        shell.call('mkdir -p %s' % image_path)

        installUrl = "/opt/zstack/nfsprimarystorage/prim-{}/rootVolumes/acct-36c27e8ff05c4780bf6d2fa65700f22e/vol-{}/{}.qcow2"\
            .format(primaryStorageUuid, volumeUuid, volumeUuid)

        r, o = bash.bash_ro("cp /root/.zguest/min-vm.qcow2 {}".format(image_path))
        self.assertEqual(0, r, "cp image failed, because {}".format(o))

        kvmHostAddons = {"qcow2Options":" -o cluster_size=2097152 "}
        rsp = nfs_plugin_utils.create_root_volume_from_template(image_path + "min-vm.qcow2", 0, 0, installUrl, "test",
                                                          volumeUuid, primaryStorageUuid, primaryStorageUuid, kvmHostAddons)

        self.assertEqual(True, rsp.success, rsp.error)

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
                "installPath": "{}".format(installUrl),
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
        mountPath = "/opt/zstack/nfsprimarystorage/prim-{}/".format(primaryStorageUuid)
        mountPaths = [mountPath]
        uuids = [primaryStorageUuid]
        urls = [url]
        mountedByZStack = [False]
        rsp = ha_utils.setup_self_fencer(hostUuid, 1, 2, mountPaths, uuids, urls, mountedByZStack, [""], 5, "Force")
        self.assertEqual(True, rsp.success)

        time.sleep(20)
        self.check_record_vm_uuids_exists(1, 1, primaryStorageUuid, hostUuid, 1, mountPath, vm.vmInstanceUuid)

        r, o = bash.bash_ro("virsh destroy %s" % vm.vmInstanceUuid)
        self.assertEqual(0, r)
        time.sleep(20)
        self.check_record_vm_uuids_not_exists(1, 1, primaryStorageUuid, hostUuid, 1, mountPath, vm.vmInstanceUuid)




    @pytest.mark.flaky(reruns=3)
    def check_record_vm_uuids_exists(self, interval, times, primaryStorageUuid, targetHostUuid,
                                     storageCheckerTimeout, mountPath, vm_uuid):
        rsp = ha_utils.file_system_check_vmstate(interval, times, primaryStorageUuid, targetHostUuid,
                                     storageCheckerTimeout, mountPath)
        assert vm_uuid in rsp.vmUuids

    @pytest.mark.flaky(reruns=3)
    def check_record_vm_uuids_not_exists(self, interval, times, primaryStorageUuid, targetHostUuid,
                                     storageCheckerTimeout, mountPath, vm_uuid):
        rsp = ha_utils.file_system_check_vmstate(interval, times, primaryStorageUuid, targetHostUuid,
                                                 storageCheckerTimeout, mountPath)
        assert vm_uuid not in rsp.vmUuids


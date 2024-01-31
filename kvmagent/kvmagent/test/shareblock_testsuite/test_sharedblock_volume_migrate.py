from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash, lvm, linux
from unittest import TestCase
from zstacklib.test.utils import misc,env
import pytest


storage_device_utils.init_storagedevice_plugin()

PKG_NAME = __name__

# must create iSCSI stroage before run test
__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/threeDiskVm.xml',
        'init':['bash ./createTwoLunsIscsiStorage.sh']
    }
}

hostUuid = "8b12f74e6a834c5fa90304b8ea54b1dd"
hostId = 24
vgUuid = "36b02490bb944233b0b01990a450ba83"
vg2Uuid = "ee09b7986bbc4a1f85f439b168c3aee7"

## describe: case will manage by ztest
class TestSharedBlockPlugin(TestCase, SharedBlockPluginTestStub):

    @classmethod
    def setUpClass(cls):
        pass
    @pytest_utils.ztest_decorater
    def test_sharedblock_volume_migrate(self):
        self_vm = env.get_vm_metadata('self')
        rsp = storage_device_utils.iscsi_login(
            self_vm.ip,"3260"
        )
        self.assertEqual(rsp.success, True, rsp.error)

        # test connect shareblock
        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi|awk -F '-' '{print $2}'")
        blockUuids = o.strip().splitlines()

        rsp = self.connect([blockUuids[0]], blockUuids, vgUuid, hostUuid, hostId, forceWipe=True)
        self.assertEqual(True, rsp.success, rsp.error)
        o = bash.bash_o("vgs")
        self.assertEqual(True, rsp.success, o)

        rsp = self.connect([blockUuids[1]], blockUuids, vg2Uuid, hostUuid, hostId, forceWipe=True)
        self.assertEqual(True, rsp.success, rsp.error)

        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=1048576*100,
            hostUuid=hostUuid,
            vgUuid=vgUuid,
        )
        self.assertEqual(True, rsp.success, rsp.error)

        snaphostUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_data_volume_with_backing(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            installPath="sharedblock://{}/{}".format(vgUuid,snaphostUuid),
            volumeUuid=snaphostUuid,
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)
        rsp = sharedblock_utils.sharedblock_estimate_template("sharedblock://{}/{}".format(vgUuid,snaphostUuid))
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(True, rsp.size is not None, rsp.error)
        self.assertEqual(True, rsp.actualSize is not None, rsp.error)
        self.assertEqual(True, rsp.size > rsp.actualSize, rsp.error)

        rsp = sharedblock_utils.sharedblock_migrate_volumes(
            vgUuid,
            hostUuid,
            migrateVolumeStructs=[
                {
                    "volumeUuid" : volumeUuid,
                    "snapshotUuid" : None,
                    "currentInstallPath" : "sharedblock://{}/{}".format(vgUuid,snaphostUuid),
                    "targetInstallPath" : "sharedblock://{}/{}".format(vg2Uuid,snaphostUuid),
                    "safeMode" : False,
                    "compareQcow2" : True,
                    "skipIfExisting" : False
                },
                {
                    "volumeUuid" : volumeUuid,
                    "snapshotUuid" : snaphostUuid,
                    "currentInstallPath" : "sharedblock://{}/{}".format(vgUuid,volumeUuid),
                    "targetInstallPath" : "sharedblock://{}/{}".format(vg2Uuid,volumeUuid),
                    "safeMode" : False,
                    "compareQcow2" : True,
                    "skipIfExisting" : False
                }
            ],
            provisioning=lvm.VolumeProvisioningStrategy.ThickProvisioning,
            volumePath="sharedblock://{}/{}".format(vgUuid,snaphostUuid),
            kvmHostAddons={"qcow2Options":" -o cluster_size=2097152 "}
        )
        self.assertEqual(True, lvm.lv_exists("/dev/%s/%s" % (vg2Uuid, volumeUuid)))
        self.assertEqual(True, lvm.lv_exists("/dev/%s/%s" % (vg2Uuid, snaphostUuid)))
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(str(lvm.calcLvReservedSize(1048576*100)), lvm.get_lv_size("/dev/%s/%s" % (vg2Uuid, snaphostUuid)))
        self.assertEqual(str(lvm.calcLvReservedSize(1048576*100)), lvm.get_lv_size("/dev/%s/%s" % (vg2Uuid, volumeUuid)))

        # test migrate back
        rsp = sharedblock_utils.sharedblock_migrate_volumes(
            vgUuid,
            hostUuid,
            migrateVolumeStructs=[
                {
                    "volumeUuid" : volumeUuid,
                    "snapshotUuid" : None,
                    "currentInstallPath" : "sharedblock://{}/{}".format(vg2Uuid,snaphostUuid),
                    "targetInstallPath" : "sharedblock://{}/{}".format(vgUuid,snaphostUuid),
                    "safeMode" : False,
                    "compareQcow2" : True,
                    "skipIfExisting" : False
                },
                {
                    "volumeUuid" : volumeUuid,
                    "snapshotUuid" : snaphostUuid,
                    "currentInstallPath" : "sharedblock://{}/{}".format(vg2Uuid,volumeUuid),
                    "targetInstallPath" : "sharedblock://{}/{}".format(vgUuid,volumeUuid),
                    "safeMode" : False,
                    "compareQcow2" : True,
                    "skipIfExisting" : False
                }
            ],
            provisioning=lvm.VolumeProvisioningStrategy.ThinProvisioning,
            volumePath="sharedblock://{}/{}".format(vg2Uuid,snaphostUuid),
            addons={"thinProvisioningInitializeSize":5368709120},
            kvmHostAddons={"qcow2Options":" -o cluster_size=2097152 "}
        )
        self.assertEqual(True, lvm.lv_exists("/dev/%s/%s" % (vgUuid, volumeUuid)))
        self.assertEqual(True, lvm.lv_exists("/dev/%s/%s" % (vgUuid, snaphostUuid)))

        self.assertEqual(False, rsp.success, rsp.error)
        r, o , e = bash.bash_roe("lvremove -y /dev/%s/%s" % (vgUuid, volumeUuid))
        self.assertEqual(r, 0, str(e))
        r, o , e = bash.bash_roe("lvremove -y /dev/%s/%s" % (vgUuid, snaphostUuid))
        self.assertEqual(r, 0, str(e))

        rsp = sharedblock_utils.sharedblock_migrate_volumes(
            vgUuid,
            hostUuid,
            migrateVolumeStructs=[
                {
                    "volumeUuid" : volumeUuid,
                    "snapshotUuid" : None,
                    "currentInstallPath" : "sharedblock://{}/{}".format(vg2Uuid,snaphostUuid),
                    "targetInstallPath" : "sharedblock://{}/{}".format(vgUuid,snaphostUuid),
                    "safeMode" : False,
                    "compareQcow2" : True,
                    "skipIfExisting" : False
                },
                {
                    "volumeUuid" : volumeUuid,
                    "snapshotUuid" : snaphostUuid,
                    "currentInstallPath" : "sharedblock://{}/{}".format(vg2Uuid,volumeUuid),
                    "targetInstallPath" : "sharedblock://{}/{}".format(vgUuid,volumeUuid),
                    "safeMode" : False,
                    "compareQcow2" : True,
                    "skipIfExisting" : False
                }
            ],
            provisioning=lvm.VolumeProvisioningStrategy.ThinProvisioning,
            volumePath="sharedblock://{}/{}".format(vg2Uuid,snaphostUuid),
            addons={"thinProvisioningInitializeSize":5368709120},
            kvmHostAddons={"qcow2Options":" -o cluster_size=2097152 "}
        )


        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(lvm.lv_is_active("/dev/{}/{}".format(vg2Uuid,volumeUuid)), False)
        self.assertEqual(lvm.lv_is_active("/dev/{}/{}".format(vg2Uuid,snaphostUuid)), False)

        # test skipIfExisting not deactive
        rsp = sharedblock_utils.sharedblock_migrate_volumes(
            vgUuid,
            hostUuid,
            migrateVolumeStructs=[
                {
                    "volumeUuid" : volumeUuid,
                    "snapshotUuid" : None,
                    "currentInstallPath" : "sharedblock://{}/{}".format(vgUuid,snaphostUuid),
                    "targetInstallPath" : "sharedblock://{}/{}".format(vg2Uuid,snaphostUuid),
                    "safeMode" : False,
                    "compareQcow2" : False, # backing file different
                    "skipIfExisting" : True
                },
                {
                    "volumeUuid" : volumeUuid,
                    "snapshotUuid" : snaphostUuid,
                    "currentInstallPath" : "sharedblock://{}/{}".format(vgUuid,volumeUuid),
                    "targetInstallPath" : "sharedblock://{}/{}".format(vg2Uuid,volumeUuid),
                    "safeMode" : False,
                    "compareQcow2" : False, # backing file different
                    "skipIfExisting" : True
                }
            ],
            volumePath="sharedblock://{}/{}".format(vgUuid,snaphostUuid),
            kvmHostAddons={"qcow2Options":" -o cluster_size=2097152 "}
        )

        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(lvm.lv_is_active("/dev/{}/{}".format(vg2Uuid,volumeUuid)), True)
        self.assertEqual(lvm.lv_is_active("/dev/{}/{}".format(vg2Uuid,snaphostUuid)), True)

        self.assertEqual(True, lvm.lv_exists("/dev/%s/%s" % (vgUuid, volumeUuid)))
        self.assertEqual(True, lvm.lv_exists("/dev/%s/%s" % (vgUuid, snaphostUuid)))
        self.assertGreaterEqual(str(lvm.calcLvReservedSize(1048576*100)), lvm.get_lv_size("/dev/%s/%s" % (vgUuid, snaphostUuid)))
        # snapshot makes no change
        self.assertEqual(str(lvm.calcLvReservedSize(1048576*100)), lvm.get_lv_size("/dev/%s/%s" % (vgUuid, volumeUuid)))

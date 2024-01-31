# coding=utf-8
from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash, lvm, jsonobject
from unittest import TestCase
from zstacklib.test.utils import misc,env


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
    def test_sharedblock_check_lock(self):
        self_vm = env.get_vm_metadata('self')
        rsp = storage_device_utils.iscsi_login(
            self_vm.ip,"3260"
        )
        self.assertEqual(rsp.success, True, rsp.error)

        # test connect shareblock
        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi|awk -F '-' '{print $2}'")
        blockUuids = o.strip().splitlines()

        rsp = self.connect(blockUuids[0 : 1], blockUuids, vgUuid, hostUuid, hostId, forceWipe=True)
        self.assertEqual(True, rsp.success, rsp.error)
        o = bash.bash_o("vgs")
        self.assertEqual(True, rsp.success, o)

        rsp = self.connect(blockUuids[1 : 2], blockUuids, vg2Uuid, hostUuid, hostId, forceWipe=True)
        self.assertEqual(True, rsp.success, rsp.error)

        # normal
        rsp = sharedblock_utils.sharedblock_check_lock(
            vgUuids=[vgUuid, vg2Uuid],
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(0, len(rsp.failedVgs), rsp.failedVgs.__dict__)

        # vg without a lock
        lvm.drop_vg_lock(vgUuid)

        rsp = sharedblock_utils.sharedblock_check_lock(
            vgUuids=[vgUuid, vg2Uuid],
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(1, len(rsp.failedVgs), rsp.failedVgs.__dict__)
        self.assertEqual(rsp.failedVgs.hasattr(vgUuid), True, rsp.failedVgs.__dict__)

        rsp = self.connect(blockUuids[0 : 1], blockUuids, vgUuid, hostUuid, hostId, forceWipe=False)
        self.assertEqual(True, rsp.success, rsp.error)

        # If there is no lv, restarting lvmlockd may not restore vg lock（lvm 2.03.11）
        bash.bash_errorout("lvcreate --size 10M --name test-1 %s" % vgUuid)
        bash.bash_errorout("lvcreate --size 10M --name test-1 %s" % vg2Uuid)

        # kill lvmlockd
        lvm.stop_lvmlockd()
        rsp = sharedblock_utils.sharedblock_check_lock(
            vgUuids=[vgUuid, vg2Uuid],
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(rsp.failedVgs.hasattr(vgUuid), True, str(rsp.failedVgs))
        self.assertEqual(rsp.failedVgs.hasattr(vg2Uuid), True, str(rsp.failedVgs))

        self.assertEqual(True, lvm.lv_is_active("/dev/%s/test-1" % vgUuid))
        type = lvm.get_lv_locking_type("/dev/%s/test-1" % vgUuid)
        self.assertEqual(True, type == lvm.LvmlockdLockType.NULL)

        rsp = self.connect(blockUuids[0 : 1], blockUuids, vgUuid, hostUuid, hostId, forceWipe=False)
        self.assertEqual(True, rsp.success, rsp.error)
        rsp = self.connect(blockUuids[1 : 2], blockUuids, vg2Uuid, hostUuid, hostId, forceWipe=False)
        self.assertEqual(True, rsp.success, rsp.error)
        bash.bash_errorout("lvcreate --size 10M %s" % vgUuid)
        bash.bash_errorout("lvcreate --size 10M %s" % vg2Uuid)



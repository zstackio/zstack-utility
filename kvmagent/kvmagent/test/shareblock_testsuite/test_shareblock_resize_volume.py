from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash,lvm
from unittest import TestCase
from zstacklib.test.utils import misc,env
import pytest


storage_device_utils.init_storagedevice_plugin()

PKG_NAME = __name__

# must create iSCSI stroage before run test
__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init':['bash ./createiSCSIStroage.sh']
    }
}

hostUuid = "8b12f74e6a834c5fa90304b8ea54b1dd"
hostId = 24
vgUuid = "36b02490bb944233b0b01990a450ba83"

## describe: case will manage by ztest
class TestSharedBlockPlugin(TestCase, SharedBlockPluginTestStub):

    @classmethod
    def setUpClass(cls):
        pass
    @pytest_utils.ztest_decorater
    def test_sharedblock_resize_volume(self):
        self_vm = env.get_vm_metadata('self')
        rsp = storage_device_utils.iscsi_login(
            self_vm.ip,"3260"
        )
        self.assertEqual(rsp.success, True, "iscsiadm login failed")

        # test connect shareblock
        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi|awk -F '-' '{print $2}'")
        blockUuid = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        rsp = self.connect([blockUuid], [blockUuid], vgUuid, hostUuid, hostId, forceWipe=True)
        self.assertEqual(True, rsp.success, rsp.error)

        # create volume
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=1048576,
            hostUuid=hostUuid,
            vgUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(int(lvm.get_lv_size("/dev/{}/{}".format(vgUuid, volumeUuid))), 1048576*4 + 12*1024**2)

        r, o = bash.bash_ro("lvs --nolocking -t |grep %s" % volumeUuid)
        self.assertEqual(0, r, "create empty volume fail in host")

        # extend lv
        rsp = sharedblock_utils.sharedblock_resize_volume(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            size=1048576*8
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(int(lvm.get_lv_size("/dev/{}/{}".format(vgUuid, volumeUuid))), 1048576*8 + 12*1024**2)
        self.assertEqual(1048576*8, rsp.size, rsp.error)

        # no change
        rsp = sharedblock_utils.sharedblock_resize_volume(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            size=1048576*8,
            force=False
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(int(lvm.get_lv_size("/dev/{}/{}".format(vgUuid, volumeUuid))), 1048576*8 + 12*1024**2)
        self.assertEqual(1048576*8, rsp.size, rsp.error)

        # shrink lv failed
        rsp = sharedblock_utils.sharedblock_resize_volume(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            size=1048576*4,
            force=False
        )
        self.assertEqual(False, rsp.success, rsp.error)
        self.assertEqual(int(lvm.get_lv_size("/dev/{}/{}".format(vgUuid, volumeUuid))), 1048576*8 + 12*1024**2)

        # shrink lv successfully
        rsp = sharedblock_utils.sharedblock_resize_volume(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            size=1048576*4,
            force=True
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(int(lvm.get_lv_size("/dev/{}/{}".format(vgUuid, volumeUuid))), 1048576*4 + 12*1024**2)
        self.assertEqual(1048576*4, rsp.size, rsp.error)
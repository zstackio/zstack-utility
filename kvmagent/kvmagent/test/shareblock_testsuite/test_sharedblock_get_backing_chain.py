from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash
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
    def test_sharedblock_get_backing_chain(self):
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

        all_volume = []
        all_volume.append(misc.uuid())
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,all_volume[0]),
            volumeUuid=all_volume[0],
            size=1048576*4,
            hostUuid=hostUuid,
            vgUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        all_volume.append(misc.uuid())
        rsp = sharedblock_utils.shareblock_create_data_volume_with_backing(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid,all_volume[0]),
            installPath="sharedblock://{}/{}".format(vgUuid,all_volume[1]),
            volumeUuid=all_volume[1],
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        all_volume.append(misc.uuid())
        rsp = sharedblock_utils.shareblock_create_data_volume_with_backing(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid,all_volume[1]),
            installPath="sharedblock://{}/{}".format(vgUuid,all_volume[2]),
            volumeUuid=all_volume[2],
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        rsp = sharedblock_utils.shareblock_get_backing_chain(vgUuid, hostUuid, all_volume[2],
                                                             "sharedblock://{}/{}".format(vgUuid,all_volume[2]), True)
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(3, len(rsp.backingChain), rsp.error)
        self.assertEqual(1048576*16*3, rsp.totalSize, rsp.error)
        for v in all_volume:
            self.assertEqual("/dev/%s/%s" % (vgUuid, v) in rsp.backingChain, True)

        rsp = sharedblock_utils.shareblock_get_backing_chain(vgUuid, hostUuid, all_volume[2],
                                                             "sharedblock://{}/{}".format(vgUuid,all_volume[2]), False)
        all_volume.pop(2)
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(2, len(rsp.backingChain), rsp.error)
        self.assertEqual(1048576*16*2, rsp.totalSize, rsp.error)
        for v in all_volume:
            self.assertEqual("/dev/%s/%s" % (vgUuid, v) in rsp.backingChain, True)
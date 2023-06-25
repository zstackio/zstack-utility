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
    def test_sharedblock_batch_get_volume_size(self):
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

        volumeUuid2 = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid2),
            volumeUuid=volumeUuid2,
            size=1048576*5,
            hostUuid=hostUuid,
            vgUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        volumeUuid3 = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid3),
            volumeUuid=volumeUuid3,
            size=1048576*10,
            hostUuid=hostUuid,
            vgUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        # test get volume size
        rsp = sharedblock_utils.sharedblock_batch_get_volume_size(
            volumeUuidInstallPaths={volumeUuid:"sharedblock://{}/{}".format(vgUuid, volumeUuid),
                                    volumeUuid2:"sharedblock://{}/{}".format(vgUuid, volumeUuid2),
                                    volumeUuid3:"sharedblock://{}/{}".format(vgUuid, volumeUuid3)
                                    },
            vgUuid=vgUuid
        )

        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(rsp.actualSizes[volumeUuid], str(16 * 1024**2), rsp.error)
        self.assertEqual(rsp.actualSizes[volumeUuid2], str(20 * 1024**2), rsp.error)
        self.assertEqual(rsp.actualSizes[volumeUuid3], str(24 * 1024**2), rsp.error)
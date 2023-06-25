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
    def test_sharedblock_delete_bits(self):
        iscsi_server = env.get_vm_metadata('self')
        rsp = storage_device_utils.iscsi_login(
            iscsi_server.ip,"3260"
        )
        self.assertEqual(rsp.success, True, "iscsiadm login failed")

        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi|awk -F '-' '{print $2}'")
        blockUuid = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        rsp = self.connect([blockUuid], [blockUuid], vgUuid, hostUuid, hostId, forceWipe=True)
        self.assertEqual(True, rsp.success, rsp.error)

        imageUuid=misc.uuid()
        # download image to shareblock
        print("debug")
        print ('lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(imageUuid, vgUuid))
        r,o = bash.bash_ro('lvcreate -asy --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(imageUuid, vgUuid))
        self.assertEqual(0, r, "create lv failed, because {}".format(o))
        r,o = bash.bash_ro('lvcreate -asy --wipesignatures y --size 4M --name {}_meta {}'.format(imageUuid, vgUuid))
        self.assertEqual(0, r, "create lv failed, because {}".format(o))

        # create volume
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_data_volume_with_backing(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid, imageUuid),
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            volumeUuid=volumeUuid,
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        r, o = bash.bash_ro("lvs --nolocking -t |grep %s" % volumeUuid)
        self.assertEqual(0, r, "create volume fail in host")

        # test delete
        rsp = sharedblock_utils.shareblock_delete_bits(
            path="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        r, o = bash.bash_ro("lvs --nolocking -t |grep %s" % volumeUuid)
        self.assertEqual(1, r, "delete volume fail in host")

        with open('/dev/{}/{}'.format(vgUuid, imageUuid), 'r') as fd:
            rsp = sharedblock_utils.shareblock_delete_bits(
                path="sharedblock://{}/{}".format(vgUuid, imageUuid),
                vgUuid=vgUuid,
                hostUuid=hostUuid,
                primaryStorageUuid=vgUuid
            )
            self.assertEqual(False, rsp.success, rsp.error)

        rsp = sharedblock_utils.shareblock_delete_bits(
                path="sharedblock://{}/{}".format(vgUuid, imageUuid),
                vgUuid=vgUuid,
                hostUuid=hostUuid,
                primaryStorageUuid=vgUuid
            )
        self.assertEqual(True, rsp.success, rsp.error)
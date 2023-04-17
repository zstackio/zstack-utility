import os
from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash, linux
from unittest import TestCase
from zstacklib.test.utils import misc,env


storage_device_utils.init_storagedevice_plugin()

PKG_NAME = __name__

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
    def test_sharedblock_extend_merge_target(self):
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

        imageUuid=misc.uuid()
        r,o = bash.bash_ro('lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(imageUuid, vgUuid))
        self.assertEqual(0, r, "create lv failed, because {}".format(o))

        r, o = bash.bash_ro("cp /root/.zguest/min-vm.qcow2 /dev/{}/{}".format(vgUuid, imageUuid))
        self.assertEqual(0, r, "cp image failed, because {}".format(o))

        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_root_volume(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid,imageUuid),
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        rsp = sharedblock_utils.sharedblock_extend_merge_target(destPath="sharedblock://{}/{}".format(vgUuid,volumeUuid), vgUuid=vgUuid)
        self.assertEqual(True, rsp.success, rsp.error)




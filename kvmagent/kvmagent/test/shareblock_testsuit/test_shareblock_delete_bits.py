from kvmagent.test.shareblock_testsuit.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import shareblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash
from unittest import TestCase
from zstacklib.test.utils import misc,env
import pytest

shareblock_utils.init_shareblock_plugin()
storage_device_utils.init_storagedevice_plugin()

PKG_NAME = __name__

# must create iSCSI stroage before run test
__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init':['bash ./createiSCSIStroage.sh']
    }
}

global hostUuid
global vgUuid

## describe: case will manage by ztest
class TestShareBlockPlugin(TestCase, SharedBlockPluginTestStub):

    @classmethod
    def setUpClass(cls):
        pass
    @pytest_utils.ztest_decorater
    def test_shareblock_delete_bits(self):
        r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        r, o = bash.bash_ro(
            "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % interF)
        interf_ip = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        # iqn
        r, o = bash.bash_ro("cat /etc/target/saveconfig.json|grep iqn|awk '{print $2}'")
        iqn = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        # login
        rsp = storage_device_utils.iscsi_login(
            interf_ip,"3260"
        )
        self.assertEqual(rsp.success, True, "iscsiadm login failed")

        global hostUuid
        hostUuid = misc.uuid()

        global vgUuid
        vgUuid = misc.uuid()
        # get block uuid
        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi|awk -F '-' '{print $2}'")
        blockUuid = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        print(blockUuid)
        rsp = shareblock_utils.shareblock_connect(
            sharedBlockUuids=[blockUuid],
            allSharedBlockUuids=[blockUuid],
            vgUuid=vgUuid,
            hostId=50,
            hostUuid=hostUuid
        )
        imageUuid=misc.uuid()
        # download image to shareblock
        print("debug")
        print ('lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(imageUuid, vgUuid))
        r,o = bash.bash_ro('lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(imageUuid, vgUuid))
        self.assertEqual(0, r, "create lv failed, because {}".format(o))

        # create volume
        volumeUuid = misc.uuid()
        rsp = shareblock_utils.shareblock_create_data_volume_with_backing(
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
        rsp = shareblock_utils.shareblock_delete_bits(
            path="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        r, o = bash.bash_ro("lvs --nolocking -t |grep %s" % volumeUuid)
        self.assertEqual(1, r, "delete volume fail in host")

        self.logout(vgUuid, hostUuid)
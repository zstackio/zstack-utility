from kvmagent.test.utils import shareblock_utils,pytest_utils,storage_device_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc,env
from unittest import TestCase

shareblock_utils.init_shareblock_plugin()
storage_device_utils.init_storagedevice_plugin()

PKG_NAME = __name__

__ENV_SETUP__ = {
    # must create iSCSI stroage
    #'self': {"qcow":"/"}
    'self': {
    }
}

global hostUuid
global vgUuid

## describe: case will manage by ztest
class TestShareBlockPlugin(TestCase):

    @classmethod
    def setUpClass(cls):
        pass
    @pytest_utils.ztest_decorater
    def test_shareblock_active_lv(self):
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

        # create volume
        volumeUuid = misc.uuid()
        rsp = shareblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=1048576,
            hostUuid=hostUuid,
            vgUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        r, o = bash.bash_ro("lvs --nolocking -t |grep %s" % volumeUuid)
        self.assertEqual(0, r, "create empty volume fail in host")

        rsp = shareblock_utils.shareblock_active_lv(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            vgUuid=vgUuid,
            lockType=2
        )

        self.assertEqual(True, rsp.success, rsp.error)
        r, o = bash.bash_ro("lsblk |grep %s" % volumeUuid)
        self.assertEqual(0, r, "[check] active volume fail in host")


        # # test disconnect shareblock
        # self.assertEqual(True, rsp.success, rsp.error)
        # rsp = shareblock_utils.shareblock_disconnect(
        #     vgUuid=vgUuid,
        #     hostUuid=hostUuid
        # )
        #
        # self.assertEqual(True, rsp.success, rsp.error)
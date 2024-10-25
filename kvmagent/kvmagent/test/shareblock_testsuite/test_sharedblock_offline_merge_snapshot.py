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
    def test_sharedblock_offline_merge_snapshot(self):
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
        size = os.stat("/root/.zguest/min-vm.qcow2").st_size
        ecmd = 'lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size {}b --name {} {}'.format(size, imageUuid, vgUuid)
        print(ecmd)
        bash.bash_errorout(ecmd)
        bash.bash_errorout("cp /root/.zguest/min-vm.qcow2 /dev/%s/%s" % (vgUuid, imageUuid))

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

        volumeUuid2 = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_root_volume(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid2),
            volumeUuid=volumeUuid2,
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        bash.bash_r("lvchange -aey %s" % "/dev/{}/{}".format(vgUuid,volumeUuid2))
        vsize = int(linux.qcow2_get_virtual_size("/dev/{}/{}".format(vgUuid,volumeUuid2)))
        rsp = sharedblock_utils.sharedblock_resize_volume("sharedblock://{}/{}".format(vgUuid,volumeUuid2), vsize+1*1024**3)
        self.assertEqual(True, rsp.success, rsp.error)

        rsp = sharedblock_utils.sharedblock_offline_merge_snapshots(
            fullRebase=False,
            srcPath="sharedblock://{}/{}".format(vgUuid,imageUuid),
            destPath="sharedblock://{}/{}".format(vgUuid,volumeUuid2),
            volumeUuid=volumeUuid,
            vgUuid=vgUuid
        )

        self.assertEqual(True, rsp.success, rsp.error)
        bash.bash_r("lvchange -aey /dev/{}/{}".format(vgUuid, volumeUuid2))
        self.assertEqual(imageUuid in linux.qcow2_get_backing_file("/dev/{}/{}".format(vgUuid, volumeUuid2)), True)

        rsp = sharedblock_utils.sharedblock_offline_merge_snapshots(
            fullRebase=True,
            srcPath="sharedblock://{}/{}".format(vgUuid,"xxxxxxxxxx"),
            destPath="sharedblock://{}/{}".format(vgUuid,volumeUuid2),
            volumeUuid=volumeUuid2,
            vgUuid=vgUuid
        )

        self.assertEqual(True, rsp.success, rsp.error)
        bash.bash_r("lvchange -aey /dev/{}/{}".format(vgUuid, volumeUuid2))
        self.assertEqual(linux.qcow2_get_backing_file("/dev/{}/{}".format(vgUuid, volumeUuid)), "")


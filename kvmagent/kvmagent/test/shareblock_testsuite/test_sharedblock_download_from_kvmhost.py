from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash, lvm
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
    def test_sharedblock_download_from_kvmhost(self):
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

        volume_uuid=misc.uuid()
        rsp = sharedblock_utils.sharedblock_download_from_kvmhost(
            primaryStorageInstallPath="sharedblock://{}/{}".format(vgUuid, volume_uuid),
            backupStorageInstallPath="/root/.zguest/min-vm.qcow2",
            hostname=self_vm.ip,
            username="root",
            sshKey=env.get_private_key(),
            sshPort=22,
            vgUuid=vgUuid,
            lockType=1
        )


        self.assertEqual(True, rsp.success, rsp.error)
        bash.bash_r("lvchange -aey /dev/{}/{}".format(vgUuid, volume_uuid))
        r = bash.bash_r("qemu-img compare %s %s" % ("/dev/{}/{}".format(vgUuid, volume_uuid), "/root/.zguest/min-vm.qcow2"))
        self.assertEqual(0, r)

        rsp = sharedblock_utils.shareblock_get_download_bits_from_kvmhost_progress(vgUuid, hostUuid, ["sharedblock://{}/{}".format(vgUuid, volume_uuid)])
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertNotEqual(0 ,rsp.totalSize)
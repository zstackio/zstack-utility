from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
import threading
import time
from zstacklib.utils import bash, lvm
from unittest import TestCase
from zstacklib.test.utils import misc,env
import mock


storage_device_utils.init_storagedevice_plugin()
PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init':['bash ./createiSCSIStroage.sh'],
        'timeout': 1800
    }
}

hostUuid = "8b12f74e6a834c5fa90304b8ea54b1dd"
hostId = 24
vgUuid = "36b02490bb944233b0b01990a450ba83"

## describe: case will manage by ztest
class TestSharedBlockPlugin(TestCase,SharedBlockPluginTestStub):

    @classmethod
    def setUpClass(cls):
        pass
    @pytest_utils.ztest_decorater
    def test_shareblock_active_lv(self):
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

        r, o = bash.bash_ro("lvs --nolocking -t |grep %s" % volumeUuid)
        self.assertEqual(0, r, "create empty volume fail in host")
        # ex
        rsp = sharedblock_utils.sharedblock_active_lv(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            vgUuid=vgUuid,
            lockType=2
        )

        self.assertEqual(True, rsp.success, rsp.error)
        r, o = bash.bash_ro("lsblk |grep %s" % volumeUuid)
        self.assertEqual(0, r, "[check] active volume fail in host")
        self.assertEqual(2, lvm.get_lv_locking_type("/dev/{}/{}".format(vgUuid, volumeUuid)))

        # sh
        rsp = sharedblock_utils.sharedblock_active_lv(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            vgUuid=vgUuid,
            lockType=1
        )
        self.assertEqual(True, rsp.success, rsp.error)
        r, o = bash.bash_ro("lsblk |grep %s" % volumeUuid)
        self.assertEqual(0, r, "[check] active volume fail in host")
        self.assertEqual(1, lvm.get_lv_locking_type("/dev/{}/{}".format(vgUuid, volumeUuid)))

        # un when in use
        def openLv(path, timeout):
            def f():
                with open(path, 'r') as fd:
                    time.sleep(timeout)
            threading.Thread(target=f).start()

        openLv("/dev/{}/{}".format(vgUuid, volumeUuid), 40)
        rsp = sharedblock_utils.sharedblock_active_lv(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            vgUuid=vgUuid,
            lockType=0
        )
        self.assertEqual(False, rsp.success, rsp.error)
        self.assertEqual(True, rsp.inUse, rsp.error)
        self.assertNotEqual(None, rsp.error, rsp.error)
        r, o = bash.bash_ro("lsblk |grep %s" % volumeUuid)
        self.assertEqual(0, r, "[check] active volume fail in host")
        self.assertEqual(1, lvm.get_lv_locking_type("/dev/{}/{}".format(vgUuid, volumeUuid)))

        # un with killProcess=True
        rsp = sharedblock_utils.sharedblock_active_lv(
            installPath="sharedblock://{}/{}".format(vgUuid, volumeUuid),
            vgUuid=vgUuid,
            lockType=0,
            killProcess=True
        )

        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(None, rsp.inUse, rsp.error)
        time.sleep(40)
        r = bash.bash_r("lvchange -an /dev/{}/{}".format(vgUuid, volumeUuid))
        self.assertEqual(0, r)

        # activate backing file
        top = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_data_volume_with_backing(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            installPath="sharedblock://{}/{}".format(vgUuid,top),
            volumeUuid=top,
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)
        rsp = sharedblock_utils.sharedblock_active_lv(
            installPath="sharedblock://{}/{}".format(vgUuid, top),
            vgUuid=vgUuid,
            lockType=2,
            recursive=True
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(1, lvm.get_lv_locking_type("/dev/{}/{}".format(vgUuid, volumeUuid)))
        self.assertEqual(2, lvm.get_lv_locking_type("/dev/{}/{}".format(vgUuid, top)))
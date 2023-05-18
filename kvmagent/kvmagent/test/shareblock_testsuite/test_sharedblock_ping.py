import thread
import time
import threading

from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash, lvm
from unittest import TestCase
import mock
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

class TestSharedBlockPlugin(TestCase, SharedBlockPluginTestStub):
    @classmethod
    def setUpClass(cls):
        pass

    @pytest_utils.ztest_decorater
    def test_sharedblock_ping(self):
        iscsi_server = env.get_vm_metadata('self')

        # login
        rsp = storage_device_utils.iscsi_login(
            iscsi_server.ip,"3260"
        )
        self.assertEqual(rsp.success, True, "iscsiadm login failed")

        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi|awk -F '-' '{print $2}'")
        blockUuid = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        rsp = self.connect([blockUuid], [blockUuid], vgUuid, hostUuid, hostId, forceWipe=True)
        self.assertEqual(rsp.success, True, "connect sharedblock failed")

        # test ping sblk
        vg_size, vg_free = lvm.get_vg_size(vgUuid)
        self.assertEqual(vg_size != 0 and vg_free != 0, True)

        rsp = sharedblock_utils.sharedblock_ping(vgUuid)
        self.assertEqual(rsp.success, True)
        self.assertEqual(rsp.totalCapacity, vg_size)
        self.assertEqual(rsp.availableCapacity, vg_free)

        lvm.get_vg_size = mock.Mock(return_value=(str(10*1024**3), str(10*1024**3)))

        # test result cache
        rsp = sharedblock_utils.sharedblock_ping(vgUuid)
        self.assertEqual(rsp.totalCapacity, vg_size)
        self.assertEqual(rsp.availableCapacity, vg_free)

        time.sleep(61)
        rsp = sharedblock_utils.sharedblock_ping(vgUuid)
        self.assertEqual(rsp.totalCapacity, str(10*1024**3))
        self.assertEqual(rsp.availableCapacity, str(10*1024**3))

        # test ping once when vgs hung
        hung = True
        def get_vg_size():
            while hung:
                time.sleep(1)
            return str(10*1024**3), str(10*1024**3)
        lvm.get_vg_size = mock.Mock(side_effect=get_vg_size)

        time.sleep(61)
        threading.Thread(target=sharedblock_utils.sharedblock_ping, args=(vgUuid))

        time.sleep(1)
        rsp = sharedblock_utils.sharedblock_ping(vgUuid)
        self.assertEqual(rsp.totalCapacity, None)
        self.assertEqual(rsp.availableCapacity, None)
        hung = False





from kvmagent.test.utils import pytest_utils,storage_device_utils
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc,env
from unittest import TestCase
from kvmagent.test.storage_device_testsuite.storage_device_teststub import StorageDevicePluginTestStub

storage_device_utils.init_storagedevice_plugin()

PKG_NAME = __name__

# must create iSCSI stroage before run test
__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init':['bash ../shareblock_testsuite/createiSCSIStroage.sh']
    }
}
global hostUuid
global vgUuid


## describe: case will manage by ztest
class TestSharedBlockPlugin(TestCase, StorageDevicePluginTestStub):

    @classmethod
    def setUpClass(cls):
        return
    @pytest_utils.ztest_decorater
    def test_iscsi_login(self):
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

        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi")
        self.assertEqual(r, 0, "[check] login to iscsi failed")

        self.logout(interf_ip,"3260")


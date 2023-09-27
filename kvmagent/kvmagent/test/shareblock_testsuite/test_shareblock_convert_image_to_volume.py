import os

from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash
from unittest import TestCase
from zstacklib.test.utils import misc,env
import pytest


storage_device_utils.init_storagedevice_plugin()

PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init':['bash ./createiSCSIStroage.sh']
    }
}

global hostUuid
global vgUuid

## describe: case will manage by ztest
class TestSharedBlockPlugin(TestCase,SharedBlockPluginTestStub):

    @classmethod
    def setUpClass(cls):
        pass
    @pytest_utils.ztest_decorater
    def test_shareblock_covert_image_to_volume(self):
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
        rsp = sharedblock_utils.shareblock_connect(
            sharedBlockUuids=[blockUuid],
            allSharedBlockUuids=[blockUuid],
            vgUuid=vgUuid,
            hostId=50,
            hostUuid=hostUuid
        )

        r, o = bash.bash_ro("lsblk")
        #self.assertEqual(True, rsp.success, rsp.error + o)

        imageUuid=misc.uuid()
        # download image to shareblock
        size = os.stat("/root/.zguest/min-vm.qcow2").st_size
        ecmd = 'lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size {}b --name {} {}'.format(size, imageUuid, vgUuid)
        print(ecmd)
        bash.bash_errorout(ecmd)
        bash.bash_errorout("cp /root/.zguest/min-vm.qcow2 /dev/%s/%s" % (vgUuid, imageUuid))

        # create volume
        # test disconnect shareblock
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_convert_image_to_volume(
            primaryStorageInstallPath="sharedblock://{}/{}".format(vgUuid,imageUuid),
            hostUuid=hostUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)
        #todo: check tag changed

        self.disconnect(vgUuid, hostUuid)
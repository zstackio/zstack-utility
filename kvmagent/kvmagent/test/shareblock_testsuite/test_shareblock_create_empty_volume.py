import json
import os
import mock
import time


from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from zstacklib.utils import bash,lvm,jsonobject
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

global hostUuid
global vgUuid

## describe: case will manage by ztest
class TestShareBlockPlugin(TestCase, SharedBlockPluginTestStub):

    @classmethod
    def setUpClass(cls):
        pass
    @pytest_utils.ztest_decorater
    def test_shareblock_create_empty_volume(self):
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
        imageUuid=misc.uuid()
        # download image to shareblock
        size = os.stat("/root/.zguest/min-vm.qcow2").st_size
        ecmd = 'lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size {}b --name {} {}'.format(size, imageUuid, vgUuid)
        print(ecmd)
        bash.bash_errorout(ecmd)
        bash.bash_errorout("cp /root/.zguest/min-vm.qcow2 /dev/%s/%s" % (vgUuid, imageUuid))

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

        # size=10M
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=10485760,
            hostUuid=hostUuid,
            vgUuid=vgUuid,
            kvmHostAddons={"qcow2Options":" -o cluster_size=2097152  -o preallocation=metadata"}
        )
        self.assertEqual(True, rsp.success, rsp.error)

        bash.bash_errorout("lvchange -aey %s" % "/dev/{}/{}".format(vgUuid,volumeUuid))
        o = bash.bash_o("qemu-img map %s --output=json" % "/dev/{}/{}".format(vgUuid,volumeUuid))
        o = json.loads(o.strip())
        self.assertEqual(2, len(o))
        self.assertEqual(10485760-2097152, o[1].get("length"))
        self.assertEqual(False, o[1].get("data"))

        # size=1G
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=1024**3,
            hostUuid=hostUuid,
            vgUuid=vgUuid,
            kvmHostAddons={"qcow2Options":" -o cluster_size=2097152  -o preallocation=metadata"}
        )
        self.assertEqual(True, rsp.success, rsp.error)

        bash.bash_errorout("lvchange -aey %s" % "/dev/{}/{}".format(vgUuid,volumeUuid))
        o = bash.bash_o("qemu-img map %s --output=json" % "/dev/{}/{}".format(vgUuid,volumeUuid))
        o = json.loads(o.strip())
        self.assertEqual(2, len(o))
        self.assertEqual(1024**3-2097152, o[1].get("length"))
        self.assertEqual(False, o[1].get("data"))

        # size=3.1G
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=3326083072,
            hostUuid=hostUuid,
            vgUuid=vgUuid,
            kvmHostAddons={"qcow2Options":" -o cluster_size=2097152  -o preallocation=metadata"}
        )
        self.assertEqual(True, rsp.success, rsp.error)

        bash.bash_errorout("lvchange -aey %s" % "/dev/{}/{}".format(vgUuid,volumeUuid))
        o = bash.bash_o("qemu-img map %s --output=json" % "/dev/{}/{}".format(vgUuid,volumeUuid))
        o = json.loads(o.strip())
        self.assertEqual(2, len(o))
        self.assertEqual(3326083072-2097152, o[1].get("length"))
        self.assertEqual(False, o[1].get("data"))

        # test create lv task timeout
        create_time = 61
        def slow_create_lv(path, size, tag="zs::sharedblock::volume", lock=True, exact_size=False, pe_ranges=None):
            time.sleep(create_time)
            bash.bash_errorout("lvcreate --size 24M --name %s %s" % (volumeUuid, vgUuid))

        lvm.create_lv_from_absolute_path = mock.Mock(side_effect=slow_create_lv)
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=1048576,
            hostUuid=hostUuid,
            vgUuid=vgUuid,
            taskContext={"__messagetimeout__":"70000","__messagedeadline__":"9698656265904"}
        )
        self.assertEqual(False, rsp.success, rsp.error)
        self.assertEqual("create lv timeout, timeout" in rsp.error, True)
        self.assertEqual(False, lvm.lv_exists("/dev/{}/{}".format(vgUuid,volumeUuid)))

        # test create lv task no timeout
        create_time = 50
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=1048576,
            hostUuid=hostUuid,
            vgUuid=vgUuid,
            taskContext={"__messagetimeout__":"62000","__messagedeadline__":"9698656265904"}
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(True, lvm.lv_exists("/dev/{}/{}".format(vgUuid,volumeUuid)))

        create_time = 1
        volumeUuid = misc.uuid()
        rsp = sharedblock_utils.shareblock_create_empty_volume(
            installPath="sharedblock://{}/{}".format(vgUuid,volumeUuid),
            volumeUuid=volumeUuid,
            size=1048576,
            hostUuid=hostUuid,
            vgUuid=vgUuid,
            taskContext={"__messagetimeout__":"62000","__messagedeadline__":"9698656265904"}
        )
        self.assertEqual(True, rsp.success, rsp.error)
        self.assertEqual(True, lvm.lv_exists("/dev/{}/{}".format(vgUuid,volumeUuid)))

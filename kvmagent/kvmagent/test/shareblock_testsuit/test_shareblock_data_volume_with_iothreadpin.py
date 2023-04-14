import pytest
from unittest import TestCase
from kvmagent.test.utils.stub import init_kvmagent
from kvmagent.test.shareblock_testsuit.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import shareblock_utils, pytest_utils, storage_device_utils, vm_utils, volume_utils, \
    network_utils
from zstacklib.test.utils import misc
from zstacklib.utils import bash, linux
from zstacklib.utils import log


shareblock_utils.init_shareblock_plugin()
storage_device_utils.init_storagedevice_plugin()
init_kvmagent()
vm_utils.init_vm_plugin()


PKG_NAME = __name__
logger = log.get_logger(__name__)

__ENV_SETUP__ = {
    'self': {
        'xml': 'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init': ['bash ./createiSCSIStroage.sh']
    }
}

global hostUuid
global vgUuid


## describe: case will manage by ztest
class TestShareBlockVolumeWithIoThreadPin(TestCase, SharedBlockPluginTestStub):

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_sahreblock_create_data_volume_with_iothread(self):
        r, o = bash.bash_ro("ip -4 a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        r, o = bash.bash_ro(
            "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % interF)
        interf_ip = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        # iqn
        r, o = bash.bash_ro("cat /etc/target/saveconfig.json|grep iqn|awk '{print $2}'")
        iqn = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        # login
        rsp = storage_device_utils.iscsi_login(
            interf_ip, "3260"
        )
        self.assertEqual(rsp.success, True, "iscsiadm login failed")

        global hostUuid
        hostUuid = misc.uuid()
        logger.info("host uuid: %s" % hostUuid)
        global vgUuid
        vgUuid = misc.uuid()
        logger.info("vg uuid: %s" % vgUuid)
        # get block uuid
        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi|awk -F '-' '{print $2}'")
        blockUuid = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        logger.info("block uuid: %s" % blockUuid)
        rsp = shareblock_utils.shareblock_connect(
            sharedBlockUuids=[blockUuid],
            allSharedBlockUuids=[blockUuid],
            vgUuid=vgUuid,
            hostId=50,
            hostUuid=hostUuid
        )
        imageUuid = misc.uuid()
        logger.info("image uuid: %s" % imageUuid)
        # download image to shareblock

        logger.info(
            'lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(
                imageUuid, vgUuid))
        r, o = bash.bash_ro(
            'lvcreate -ay --wipesignatures y --addtag zs::sharedblock::image --size 7995392b --name {} {}'.format(
                imageUuid, vgUuid))
        self.assertEqual(0, r, "create lv failed, because {}".format(o))

        r, o = bash.bash_ro("cp /root/.zguest/min-vm.qcow2 /dev/%s" % imageUuid)
        self.assertEqual(0, r, "cp image failed, because {}".format(o))

        # create volume
        # test disconnect shareblock
        volumeUuid = misc.uuid()
        logger.info("volume uuid: %s" % volumeUuid)
        vol_path = "sharedblock://{}/{}".format(vgUuid, volumeUuid)
        logger.info("vol path: %s" % vol_path)
        rsp = shareblock_utils.shareblock_create_data_volume_with_backing(
            templatePathInCache="sharedblock://{}/{}".format(vgUuid, imageUuid),
            installPath=vol_path,
            volumeUuid=volumeUuid,
            vgUuid=vgUuid,
            hostUuid=hostUuid,
            primaryStorageUuid=vgUuid
        )
        self.assertEqual(True, rsp.success, rsp.error)

        r, o = bash.bash_ro("lvs --nolocking -t |grep %s" % volumeUuid)
        self.assertEqual(0, r, "create volume fail in host")

        # volumeUuid = "a8d8dec96869406c90d1a0e536082214"
        # vol_path = "sharedblock://faee3b36503e4a40b9dbc3dad742eae2/a8d8dec96869406c90d1a0e536082214"

        vm = vm_utils.create_startvm_body_jsonobject()
        vm_utils.create_vm(vm)
        vm_uuid = vm.vmInstanceUuid
        logger.info("vm uuid: %s" % vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        assert pid, 'cannot find pid of vm[%s]' % vm_uuid

        install_path = "/dev/%s/%s" % (vgUuid, imageUuid)

        iothread_id = 1
        iothread_pin = "0"
        _, vol = vm_utils.attach_iothread_shareblock_volume_to_vm(vm_uuid, volumeUuid, install_path, iothread_id, iothread_pin)

        rsp = vm_utils.check_volume(vm_uuid, [vol])
        self.assertTrue(rsp.success)
        self.check_volume_iothread_pin(vm_uuid, install_path, iothread_id)

        vm_utils.stop_vm(vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % vm_uuid)

        vol_body, pin_struct = vm_utils.build_shared_block_vol_body_with_iothread(volumeUuid, install_path, iothread_id, iothread_pin)
        vm = vm_utils.create_vm_with_vols([vol_body], [pin_struct])
        vm_utils.create_vm(vm)
        self.vm_uuid = vm.vmInstanceUuid
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertFalse(not pid, 'cannot find pid of vm[%s]' % vm_uuid)

        rsp = vm_utils.check_volume(vm_uuid, [vol])
        self.assertTrue(rsp.success)
        self.check_volume_iothread_pin(vm_uuid, install_path, iothread_id)

        logger.info("clean test env: destroy vm")
        vm_utils.destroy_vm(vm_uuid)
        pid = linux.find_vm_pid_by_uuid(vm_uuid)
        self.assertTrue(not pid, 'vm[%s] vm still running' % vm_uuid)

        self.logout(vgUuid, hostUuid)

    def check_volume_iothread_pin(self, vm_uuid, vol_path, iothread_id):
        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        vol_xml = volume_utils.find_volume_in_vm_xml_by_path(xml, vol_path)
        self.assertIsNotNone(vol_xml, "Attached Vol xml is null")
        self.assertIsNotNone(vol_xml.driver, "Attached Vol's xml has no driver")
        self.assertIsNotNone(vol_xml.driver.iothread_, "Attached Vol's driver has no iothread config")
        self.assertEqual(vol_xml.driver.iothread_, str(iothread_id),
                         "unexpected vol iothreadid[%s], actual is %s" % (
                             str(iothread_id), vol_xml.driver.iothread_))



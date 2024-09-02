import os.path
import time

from kvmagent.test.nfs_testsuit.test_ha_plugin_testsub import NfsPluginTestStub
from kvmagent.test.utils import ha_utils,pytest_utils, vm_utils, nfs_plugin_utils, network_utils
from unittest import TestCase
from zstacklib.test.utils import misc,env
from zstacklib.utils import jsonobject, bash, linux, log, shell
import pytest


PKG_NAME = __name__

logger = log.get_logger(__name__)

# must create nfs stroage before run test

__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml',
        'init':['bash ./createNFSStroage.sh']
    }
}

global hostUuid
global vgUuid
global primaryStorageUuid

class TestHaNfsPlugin(TestCase, NfsPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_nfs_migrate_bits(self):
        global hostUuid
        hostUuid = misc.uuid()

        volumeUuid = misc.uuid()

        global vgUuid
        primaryStorageUuid = misc.uuid()

        imageUuid = misc.uuid()

        url = NfsPluginTestStub().mount(primaryStorageUuid)
        dstPsDir = "/tmp/nfs-storage/"
        linux.mkdir(dstPsDir)

        cache_dir = "/opt/zstack/nfsprimarystorage/prim-{}/imagecache".format(primaryStorageUuid)
        image_path = "{}/template/{}/".format(cache_dir, imageUuid)
        shell.call('mkdir -p %s' % image_path)

        installUrl = "/opt/zstack/nfsprimarystorage/prim-{}/rootVolumes/acct-36c27e8ff05c4780bf6d2fa65700f22e/vol-{}/{}.qcow2" \
            .format(primaryStorageUuid, volumeUuid, volumeUuid)

        r, o = bash.bash_ro("cp /root/.zguest/min-vm.qcow2 {}".format(image_path))
        self.assertEqual(0, r, "cp image failed, because {}".format(o))

        kvmHostAddons = {"qcow2Options":" -o cluster_size=2097152 "}
        rsp = nfs_plugin_utils.create_root_volume_from_template(image_path + "min-vm.qcow2", 100*1024**2, 0, installUrl, "test",
                                                                volumeUuid, primaryStorageUuid, primaryStorageUuid, kvmHostAddons)

        self.assertEqual(True, rsp.success, rsp.error)

        rsp = nfs_plugin_utils.get_volume_base_image(installUrl, os.path.dirname(installUrl),
                                                     os.path.dirname(image_path), volumeUuid)
        self.assertEqual(image_path + "min-vm.qcow2", rsp.path, "found wrong base image %s" % rsp.path)
        self.assertEqual([], rsp.otherPaths, "found wrong base images %s" % rsp.otherPaths)

        linux.qcow2_fill(10*1024**2, 20*1024**2, installUrl)
        srcPath = "/opt/zstack/nfsprimarystorage/prim-{}/rootVolumes/acct-36c27e8ff05c4780bf6d2fa65700f22e/vol-{}/".format(primaryStorageUuid, volumeUuid)
        rsp = nfs_plugin_utils.migrate_bits(srcPath, dstPsDir, volumeInstallPath=installUrl)
        self.assertEqual(True, rsp.success, rsp.error)
        shell.call("qemu-img compare %s %s/%s.qcow2" % (installUrl, dstPsDir, volumeUuid))
        self.assertEqual(image_path + "min-vm.qcow2", linux.qcow2_get_backing_file(installUrl))

        shell.call("qemu-img resize %s +3G" % (image_path + "min-vm.qcow2"))
        kvmHostAddons = {"qcow2Options":" -o cluster_size=2097152 -o preallocation=falloc "}
        srcPath = "/opt/zstack/nfsprimarystorage/prim-{}/imagecache/template/{}/".format(primaryStorageUuid, imageUuid)
        rsp = nfs_plugin_utils.migrate_bits(srcPath, dstPsDir, volumeInstallPath=image_path + "min-vm.qcow2", kvmHostAddons=kvmHostAddons)
        self.assertEqual(True, rsp.success, rsp.error)
        shell.call("qemu-img compare %s %s/%s" % (image_path + "min-vm.qcow2", dstPsDir, "min-vm.qcow2"))
        virtual_size, actualSize = linux.qcow2_size_and_actual_size(dstPsDir + "min-vm.qcow2")
        self.assertGreaterEqual(actualSize, virtual_size)








from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import env, misc
from zstacklib.utils import uuidhelper
from kvmagent.plugins import vm_plugin
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()


__ENV_SETUP__ = {
    'self': {}
}


class TestSnapshots(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @misc.test_for(handlers=[
        vm_plugin.VmPlugin.KVM_TAKE_VOLUME_SNAPSHOT_PATH,
        vm_plugin.VmPlugin.KVM_MERGE_SNAPSHOT_PATH,
    ])
    @pytest_utils.ztest_decorater
    def test_snapshot_operations(self):
        vm_uuid, vm = self._create_vm()

        xml = vm_utils.get_vm_xmlobject_from_virsh_dump(vm_uuid)
        disk = xml.devices.disk[0]

        vol_path = disk.source.file_
        vol_uuid = os.path.basename(vol_path).split('.')[0]
        snapshot_path = os.path.join(env.SNAPSHOT_DIR, '%s.qcow2' % uuidhelper.uuid())

        vm_utils.take_snapshot(vm_uuid, vol_uuid, vol_path, snapshot_path)
        self.assertTrue(os.path.isfile(snapshot_path))

        new_vol_path = snapshot_path
        new_snapshot_path = vol_path

        rsp = vm_utils.merge_snapshots(vm_uuid, new_vol_path, new_snapshot_path)
        self.assertFalse(rsp.success)
        # merge will not delete the snapshot
        self.assertTrue(os.path.isfile(new_snapshot_path))

        self._destroy_vm(vm_uuid)

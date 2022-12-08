from kvmagent.test.utils.stub import *
from kvmagent.test.utils import vm_utils, network_utils, volume_utils, pytest_utils
from zstacklib.utils import jsonobject, xmlobject, bash, linux
from zstacklib.test.utils import misc,env
from kvmagent.plugins import vm_plugin
init_kvmagent()
vm_utils.init_vm_plugin()


__ENV_SETUP__ = {
    'self': {
    }
}


class TestVmPlugin(TestCase, vm_utils.VmPluginTestStub):
    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test_attach_vm_nic(self):
        vm_uuid, _ = self._create_vm()

        cmd = jsonobject.from_dict(vm_utils.attach_vm_nic_body)
        cmd.vmUuid = vm_uuid
        cmd.nic.mac = "fa:04:93:d1:2c:01"
        cmd.nic.bridgeName = "br_" + env.DEFAULT_ETH_INTERFACE_NAME
        cmd.nic.physicalInterface = env.DEFAULT_ETH_INTERFACE_NAME
        cmd.nic.uuid = misc.uuid()
        cmd.nic.nicInternalName = "vnic16099.1"
        cmd.nic.deviceId = 1
        cmd.nic.metaData = 32
        cmd.nic.useVirtio =True
        cmd.nic.bootOrder = 0
        cmd.nic.driverType = 1500
        cmd.nic.type = "VNIC"
        cmd.nic.vlanId = -1

        rsp = vm_utils.attach_vm_nic(cmd)
        self.assertEqual(True, rsp.success, rsp.error)


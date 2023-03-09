import time

from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import bash
from unittest import TestCase


init_kvmagent()
vm_utils.init_vm_plugin()


PKG_NAME = __name__

__ENV_SETUP__ = {
    'migrate-vm': {},
    'self': {}
}


def migrate_vm_run():
    network_utils.create_default_bridge_if_not_exist()
    network_utils.close_firewall()
    os._exit(0)


class TestVmMigration(TestCase, vm_utils.VmPluginTestStub):

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()
        cls.vm1 = env.get_vm_metadata('migrate-vm')
        remote.setup_remote_machine(cls.vm1.ip, PKG_NAME, migrate_vm_run.__name__)

    @pytest_utils.ztest_decorater
    def test_something(self):
        time.sleep(10)
        vm_uuid, _ = self._create_vm()
        current_vm = env.get_test_environment_metadata()
        r, _ = bash.bash_ro('virsh list | grep %s' % vm_uuid)
        self.assertEqual(0, r, 'vm[%s]not running[%s]' % (vm_uuid, current_vm.ip))
        out2 = vm_utils.migrate_vm(vm_uuid, current_vm.ip, self.vm1.ip)
        out = vm_utils.migrate_vm(vm_uuid, current_vm.ip, self.vm1.ip)
        oo = out.to_dict()
        r, _ = bash.bash_ro('virsh list | grep %s' % vm_uuid)
        self.assertNotEqual(0, r, oo)
        self.assertNotEqual(0, r, 'vm[%s] is still running on current host[%s],out{oo}' % (vm_uuid, current_vm.ip))
        r, _, _ = remote.ssh_run(self.vm1.ip, 'virsh list | grep %s' % vm_uuid)
        self.assertEqual(0, r, 'vm[%s] is not running on the target host[%s]' % (vm_uuid, self.vm1.ip))

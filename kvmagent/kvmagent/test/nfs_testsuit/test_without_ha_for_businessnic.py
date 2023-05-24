from kvmagent.test.nfs_testsuit.test_ha_plugin_testsub import NfsPluginTestStub
from kvmagent.test.utils import ha_utils,pytest_utils
from unittest import TestCase
from zstacklib.test.utils import misc
from zstacklib.utils import log

PKG_NAME = __name__

logger = log.get_logger(__name__)

# must create nfs stroage before run test

__ENV_SETUP__ = {
    'self': {
        'xml':'http://smb.zstack.io/mirror/ztest/xml/twoDiskVm.xml'
    }
}


class WithoutHaForBusinessNic(TestCase, NfsPluginTestStub):
    @classmethod
    def setUpClass(cls):
        pass

    @pytest_utils.ztest_decorater
    def test_without_ha_for_business_nic(self):
        vm_uuid1 = misc.uuid()
        vm_uuid2 = misc.uuid()
        vm_uuid3 = misc.uuid()
        vm_uuid4 = misc.uuid()
        vm_uuid5 = misc.uuid()
        
        vm_uuids = []
        vm_uuids.append(vm_uuid1)
        vm_uuids.append(vm_uuid2)
        vm_uuids.append(vm_uuid3)
        vm_uuids.append(vm_uuid4)
        vm_uuids.append(vm_uuid5)

        ha_utils.add_vm_fencer_rule_to_host("hostStorageState", [vm_uuid1, vm_uuid2], "hostBusinessNic", [vm_uuid3, vm_uuid4])
        rsp = ha_utils.get_vm_fencer_rule()
        logger.debug("===========allowRules:%s, blockRules:%s" % (rsp.allowRules, rsp.blockRules))

        assert vm_uuid1 in rsp.allowRules["hostStorageState"]
        assert vm_uuid2 in rsp.allowRules["hostStorageState"]
        assert len(rsp.allowRules["hostStorageState"]) == 2
        assert vm_uuid3 in rsp.blockRules['hostBusinessNic']
        assert vm_uuid4 in rsp.blockRules['hostBusinessNic']
        assert len(rsp.blockRules["hostBusinessNic"]) == 2

        ha_utils.remove_vm_fencer_rule_from_host("hostStorageState", [vm_uuid1], "hostBusinessNic", [vm_uuid4])
        rsp = ha_utils.get_vm_fencer_rule()

        assert vm_uuid1 not in rsp.allowRules["hostStorageState"]
        assert vm_uuid2 in rsp.allowRules["hostStorageState"]
        assert len(rsp.allowRules["hostStorageState"]) == 1
        assert vm_uuid3 in rsp.blockRules['hostBusinessNic']
        assert vm_uuid4 not in rsp.blockRules['hostBusinessNic']
        assert len(rsp.blockRules["hostBusinessNic"]) == 1

        bridge_nic = self.find_nic_from_bridage("br_zsn0")
        assert bridge_nic == 'zsn0'

        bridge_nic = self.find_nic_from_bridage("br_zsn0.1000")
        assert bridge_nic == 'zsn0'

        bridge_nic = self.find_nic_from_bridage("zsn0")
        assert bridge_nic == 'zsn0'

        bridge_nic = self.find_nic_from_bridage("")
        assert bridge_nic is None


    def find_nic_from_bridage(self, bridge_nic):
        if len(bridge_nic) == 0:
            return None

        if '_' in bridge_nic:
            bridge_nic = bridge_nic.split('_')[1]

        if '.' in bridge_nic:
            bridge_nic = bridge_nic.split('.')[0]

        if len(bridge_nic) == 0:
            return None

        return bridge_nic.strip()



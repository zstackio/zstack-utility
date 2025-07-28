import os
import time

import mock

from kvmagent.test.shareblock_testsuite.shared_block_plugin_teststub import SharedBlockPluginTestStub
from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils,ha_utils
from zstacklib.utils import bash, http, jsonobject, linux, sanlock, lvm
from unittest import TestCase
from zstacklib.test.utils import misc,env
from kvmagent.plugins.ha_plugin import HaPlugin
from kvmagent.kvmagent import SEND_COMMAND_URL, HOST_UUID
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


## describe: case will manage by ztest
class TestSharedBlockPlugin(TestCase, SharedBlockPluginTestStub):
    @classmethod
    def setUpClass(cls):
        cls.zsblk_agent_heart_result = "success"
        cls.zsblk_agent_heart_code = 0

        cls.origin_json_dump_get = http.json_dump_get
        cls.origin_json_dump_post = http.json_dump_post
        # 1 means storage is good, 2 means storage is failed, -1 means no way to check.
        cls.condition_dict = {1: "success", 0: "fail", -1:"no_way"}
        cls.fencer_result_dict = {1: "trigger", 0:"no_trigger"}
        cls.sanlock_io_timeout = 5
        cls.interval = 5
        cls.management_network_ok = True
        cls.fencer_triggered = 0
        cls.disk1_wwid = None
        cls.disk1_dev = None

    def mock_zsblk_agent(self):
        def mock_func(uri, body=None, headers={}, fail_soon=False, print_curl=False):
            if "zsblk-agent/vg/heartbeat/status" in uri:
                if self.zsblk_agent_heart_result == "success":
                    result = {vgUuid: {"lastCheck": linux.get_current_timestamp(), "lastSuccess": linux.get_current_timestamp(), "code": 0, "error": ""}}
                elif self.zsblk_agent_heart_result == "fail":
                    result = {vgUuid: {"lastCheck": linux.get_current_timestamp(), "lastSuccess": 1, "code": -2, "error": "heartbeat failed"}}
                else:
                    result = {}
                return jsonobject.dumps(result)
            return self.origin_json_dump_get(uri, body, headers, fail_soon, print_curl)
        http.json_dump_get = mock.Mock(side_effect=mock_func)


    def mock_management_work(self):
        def mock_func(uri, body=None, headers={}, fail_soon=False, print_curl=False):
            if "/kvm/reportselffencerstatechanged" in headers.values():
                if self.management_network_ok:
                    return ""
                else:
                    raise Exception("cannot report self fencer state changed.")

            return self.origin_json_dump_post(uri, body, headers, fail_soon, print_curl)
        http.json_dump_post = mock.Mock(side_effect=mock_func)


    def mock_fencer_fire(self):
        def mock_func(vgUuid):
            self.fencer_triggered = 1
            return []
        lvm.get_running_vm_root_volume_on_vg = mock.Mock(side_effect=mock_func)


    def connnect_storage(self):
        bash.bash_errorout("echo 'running' > /sys/class/block/%s/device/state" % self.disk1_dev)
        rsp = self.connect([self.disk1_wwid], self.disk1_wwid, vgUuid, hostUuid, hostId, forceWipe=True, ioTimeout=self.sanlock_io_timeout)
        self.assertEqual(True, rsp.success, rsp.error)

    def disconnect_storage(self):
        bash.bash_errorout("echo 'offline' > /sys/class/block/%s/device/state" % self.disk1_dev)

    def run_fencer_case(self, sanlock_con, zsblk_con, expect_result):
        print("test case: sanlock %s , zsblk %s, expect %s\n" % (sanlock_con, zsblk_con, expect_result))
        self.fencer_triggered = 0
        if sanlock_con == "fail":
            self.disconnect_storage()
        elif sanlock_con == "no_way":
            bash.bash_errorout("lvmlockctl -r %s" % vgUuid)

        self.zsblk_agent_heart_result = zsblk_con

        # use real sanlock io timeout, zsblk-agent will fail quickly.
        check_timeout = sanlock.calc_id_renewal_fail_seconds(self.sanlock_io_timeout) - self.sanlock_io_timeout + 2 * self.sanlock_io_timeout
        while check_timeout > 0:
            if self.fencer_triggered:
                break
            time.sleep(5)
            check_timeout -= 5
        self.assertEqual(expect_result, self.fencer_result_dict[self.fencer_triggered], "the result did not meet expectations, expect %s actual %s, sanlock %s, zsblk %s"
                         % (expect_result, self.fencer_result_dict[self.fencer_triggered], sanlock_con, zsblk_con))


    @pytest_utils.ztest_decorater
    def test_sharedblock_ha(self):
        iscsi_server = env.get_vm_metadata('self')
        if not iscsi_server.ip:
            r, o = bash.bash_ro("ip a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
            interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

            r, o = bash.bash_ro(
                "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % interF)
            iscsi_server.ip = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        rsp = storage_device_utils.iscsi_login(
            iscsi_server.ip,"3260"
        )
        self.assertEqual(True, rsp.success, rsp.error)
        dev = bash.bash_o('basename "$(readlink -f /dev/disk/by-id/scsi-* | head -n 1)"').strip()
        self.assertEqual(True, dev.startswith("sd"), dev)
        self.disk1_dev = dev
        wwid = bash.bash_o('ls /dev/disk/by-id/scsi-* | head -n 1').strip().split("scsi-")[1]
        self.disk1_wwid = wwid

        # restart lvmlockd and sanlock for updating sanlock io timeout
        bash.bash_r("pkill -9 lvmlockd")
        bash.bash_r("pkill -9 sanlock")
        self.connnect_storage()

        self.mock_zsblk_agent()
        self.mock_management_work()
        self.mock_fencer_fire()
        HaPlugin.config = {SEND_COMMAND_URL: "xx", HOST_UUID:"yy"}

        addons = {"qcow2Options":" -o cluster_size=2097152 "}
        rsp = ha_utils.setup_sharedblock_self_fencer(vgUuid, hostUuid, "None", addons, vgUuid, self.interval, 3, self.sanlock_io_timeout, "Force", ["hostStorageState"])
        self.assertEqual(True, rsp.success, rsp.error)

        self.management_network_ok = False
        self.connnect_storage()
        self.zsblk_agent_heart_result = "success"
        self.run_fencer_case("no_way", "no_way", "trigger")

        self.management_network_ok = True
        expect_result = {} # type: dict[int, dict[int, int]]
        expect_result[1] = {1: 0, 0: 0, -1:0}
        expect_result[0] = {1: 1, 0: 1, -1:1}
        expect_result[-1] = {1: 0, 0: 1, -1:0}

        for sanlk_con in [1, 0, -1]:
            for zsblk_con in [1, 0, -1]:
                self.connnect_storage()
                self.zsblk_agent_heart_result = "success"
                time.sleep(self.sanlock_io_timeout + 1) # wait vg recovered
                self.run_fencer_case(self.condition_dict[sanlk_con], self.condition_dict[zsblk_con],
                                     self.fencer_result_dict[expect_result[sanlk_con][zsblk_con]])


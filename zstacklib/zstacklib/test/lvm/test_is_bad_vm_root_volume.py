'''

@author: zaifeng.wang
'''

import mock
import unittest
import zstacklib
from zstacklib.utils import lvm
from zstacklib.utils import bash


class Test(unittest.TestCase):

    def test_function_is_bad_vm_root_volume(self):
        def test_function_works_or_not(expect_is_bad_volume):
            is_bad_volume = lvm.is_bad_vm_root_volume("/dev/0af3ac2a9388489d8dcb0f3bf89f1af1/84c16257085b40de9823dc79d8de18f7")
            self.assertEqual(is_bad_volume, expect_is_bad_volume)

        lv_bad_output = [all_dep_missing_one_mpath_pv_lv, all_dep_offline_one_mpath_pv_lv, one_pv_blocked_one_pv_lv,
                         some_dep_offline_one_mpath_pv_lv, some_dep_offline_two_mpath_pv_lv,
                         one_pv_offline_two_mpath_pv_lv, one_pv_offline_two_pv_lv]

        lv_good_output = [all_dep_running_one_mpath_pv_lv]

        for o in lv_bad_output:
            bash.bash_ro = mock.Mock(return_value=(0, o))
            test_function_works_or_not(True)

        for o in lv_good_output:
            bash.bash_ro = mock.Mock(return_value=(0, o))
            test_function_works_or_not(False)

        bash.bash_ro = mock.Mock(return_value=(-1, ""))
        test_function_works_or_not(True)


volume_not_exist = ""

all_dep_running_one_mpath_pv_lv = '''NAME TYPE STATE
eff09a57d7854231b8200b7f83e3adb4-da3d8ec624ea412ebf1ea2bf54cd0d58 lvm running
mpatha mpath running
sda disk running
sdb disk running'''

some_dep_offline_one_mpath_pv_lv = '''NAME TYPE STATE
eff09a57d7854231b8200b7f83e3adb4-da3d8ec624ea412ebf1ea2bf54cd0d58 lvm running
mpatha mpath running
sda disk transport-offline
sdb disk running'''

all_dep_offline_one_mpath_pv_lv = '''NAME TYPE STATE
eff09a57d7854231b8200b7f83e3adb4-da3d8ec624ea412ebf1ea2bf54cd0d58 lvm running
mpatha mpath running
sda disk transport-offline
sdb disk transport-offline'''

some_dep_offline_two_mpath_pv_lv = '''NAME TYPE STATE
cf1e9c4f3d674f159505c234c3e5356b-e7b20bbcad9f4e1499259e5b8ec0eccd lvm running
36000d31000e568000000000000000103 mpath running
sdaj disk running
sdao disk running
36000d31000e568000000000000000112 mpath running
sdbg disk running
sdax disk transport-offline'''

one_pv_offline_two_mpath_pv_lv = '''NAME TYPE STATE
cf1e9c4f3d674f159505c234c3e5356b-e7b20bbcad9f4e1499259e5b8ec0eccd lvm running
36000d31000e568000000000000000103 mpath running
sdaj disk running
sdao disk running
36000d31000e568000000000000000112 mpath running
sdbg disk transport-offline
sdax disk transport-offline'''


one_pv_offline_two_pv_lv = '''NAME TYPE STATE
cf1e9c4f3d674f159505c234c3e5356b-e7b20bbcad9f4e1499259e5b8ec0eccd lvm running
sdaj disk transport-offline
sdao disk running'''

one_pv_blocked_one_pv_lv = '''NAME TYPE STATE
cf1e9c4f3d674f159505c234c3e5356b-e7b20bbcad9f4e1499259e5b8ec0eccd lvm running
sdaj disk blocked'''

all_dep_missing_one_mpath_pv_lv = '''NAME TYPE STATE
cf1e9c4f3d674f159505c234c3e5356b-e7b20bbcad9f4e1499259e5b8ec0eccd lvm running
36000d31000e568000000000000000103 mpath running'''


if __name__ == "__main__":
    unittest.main()

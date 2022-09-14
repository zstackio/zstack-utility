
import os
import time
import unittest

import zstacklib.utils.ip as ip
from zstacklib.utils import jsonobject
from kvmagent.plugins import host_plugin

class Test(unittest.TestCase):


    def test_1_query_smart_nic_pcis(self):
        # because 1 smart-nic has 2 ports
        has_at_least_two_pcis = True

        nic_pcis = ip.get_smart_nic_pcis()
        if len(nic_pcis) < 2:
            has_at_least_two_pcis = False

        self.assertEqual(has_at_least_two_pcis, True)
        print("=======test1-done=========")


    def test_2_query_smart_nic_interfaces(self):
        # need split at least 1 vf to meet this requirement
        has_at_least_three_interfaces = True

        nic_interfaces = ip.get_smart_nic_interfaces()
        if len(nic_interfaces) < 3:
            has_at_least_three_interfaces = False

        self.assertEqual(has_at_least_three_interfaces, True)
        print("=======test2-done=========")


    def test_3_query_smart_nic_representors(self):
        '''
        Notice:

            in test 2 -> query_smart_nic_interfaces(), one of the
            requirement is  "has no less than 3 interfaces"

            3 interfaces = 2 physical-interface + 1 representor
            so if test 2 pass, test 3 assumed "at least 1 representor"
        '''
        has_at_least_one_representor = True

        nic_representors = ip.get_smart_nic_representors()
        if len(nic_representors) < 1:
            has_at_least_one_representor = False

        self.assertEqual(has_at_least_one_representor, True)

        def get_number_vfs():
            fd = os.popen("lspci | grep Virtual | wc -l", "r")
            num_vfs = int(fd.read())
            fd.close
            return num_vfs
        self.assertEqual(get_number_vfs(), len(nic_representors))
        print("=======test3-done=========")


    def test_4_query_host_physicl_nics(self):
        physicl_nics_not_include_vfs = True

        nic_representors = ip.get_smart_nic_representors()
        physical_nics = ip.get_host_physicl_nics()

        for nic_representor in nic_representors:
            for physical_nic in physical_nics:
                if physical_nic == nic_representor:
                    physicl_nics_not_include_vfs = False
        
        self.assertEqual(physicl_nics_not_include_vfs, True)
        print("=======test4-done=========")



if __name__ == "__main__":
    unittest.main()


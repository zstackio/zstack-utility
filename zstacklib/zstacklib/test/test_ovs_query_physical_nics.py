
import os
import time
import unittest
import mock

import zstacklib.utils.ip as ip
from zstacklib.utils import qemu

qemu.get_path = mock.Mock(return_value="/usr/bin/qemu-system-x86_64")

from kvmagent.plugins import prometheus

class Test(unittest.TestCase):

    @unittest.skipIf(len(ip.get_smart_nic_pcis()) == 0, "no smart-nic found")
    def test_1_query_smart_nic_pcis(self):
        # because 1 smart-nic has 2 ports
        has_at_least_two_pcis = True

        nic_pcis = ip.get_smart_nic_pcis()
        if len(nic_pcis) < 2:
            has_at_least_two_pcis = False

        self.assertEqual(has_at_least_two_pcis, True)
        print("=======test1-done=========")

    @unittest.skipIf(len(ip.get_smart_nic_pcis()) == 0, "no smart-nic found")
    def test_2_query_smart_nic_interfaces(self):
        # need split at least 1 vf to meet this requirement
        has_at_least_three_interfaces = True

        nic_interfaces = ip.get_smart_nics_interfaces()
        if len(nic_interfaces) < 3:
            has_at_least_three_interfaces = False

        self.assertEqual(has_at_least_three_interfaces, True)
        print("=======test2-done=========")

    @unittest.skipIf(len(ip.get_smart_nic_pcis()) == 0, "no smart-nic found")
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
        
        def get_smart_nic_representor_interfaces_number():
            fd = os.popen("lspci -D -m | grep Mellanox | grep -v Virtual | awk {'print $1}' | xargs -I {} ls /sys/bus/pci/devices/{}/net | grep _ | wc -l", "r")
            num_rep_ifs = int(fd.read())
            fd.close
            return num_rep_ifs

        self.assertEqual(get_smart_nic_representor_interfaces_number(), len(nic_representors))
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


    def test_5_query_smart_nic_interfaces_when_driver_not_installed(self):
        def is_ofed_installed():
            return False
            fd = os.popen("ofed_info -n", "r")
            ofed_version = fd.read()
            if "." in ofed_version:
                return True
            return False

        def has_CX5_card():
            fd = os.popen("lspci | grep ConnectX-5 | wc -l", "r")
            num_CX5 = int(fd.read())
            if num_CX5 > 0:
                return True
            return False

        def get_smart_nic_interfaces_number():
            counter = 0
            smart_nics_interfaces = ip.get_smart_nics_interfaces()
            for i in smart_nics_interfaces:
                for j in i:
                    counter = counter + 1
            return counter

        # mock /sys/bus/pci/devices/$pci/net not exist
        not_exist_pcis = ['0000:18:88.8', '0000:16:66.6']

        nic_interfaces = ip.get_smart_nics_interfaces(not_exist_pcis)
        self.assertEqual(len(nic_interfaces), 0)

        if not is_ofed_installed() and has_CX5_card():
            self.assertNotEqual(get_smart_nic_interfaces_number(), len(ip.get_smart_nic_representors()))
        print("=======test5-done=========")


    def test_6_is_prometheus_collect_nics_performance_good(self):
        def get_number_interfaces():
            fd = os.popen("find /sys/class/net -type l -not -lname '*virtual*' | wc -l", "r")
            num_interfaces = int(fd.read())
            fd.close
            return num_interfaces

        # query time cost
        time_start = time.time()
        prometheus.collect_physical_network_interface_state()
        time_end = time.time()
        time_cost = time_end - time_start

        # query interface number
        num_interfaces = get_number_interfaces()

        # judge performance
        is_performance_good = True
        if num_interfaces < 512:
            ''' prometheus can handle <= 512 interfaces in 0.5 second '''
            expect_time_cost = 0.5
        else:
            ''' prometheus can handle 1000 interfaces in 1 second '''
            expect_time_cost = float(num_interfaces)/1000
        print("time-cost = %s" % (str(time_cost)))
        print("expect time-cost = %s" % (str(expect_time_cost)))
        if time_cost > expect_time_cost:
            is_performance_good = False
        self.assertEqual(is_performance_good, True)
        print("=======test6-done=========")


if __name__ == "__main__":
    unittest.main()


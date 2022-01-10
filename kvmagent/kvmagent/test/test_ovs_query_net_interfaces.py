
import os
import time
import unittest

import zstacklib.utils.ip as ip
from zstacklib.utils import jsonobject
from kvmagent.plugins import host_plugin

class Test(unittest.TestCase):


    def test_1_has_many_nics_and_vfs(self):
        # has more than 100 nics
        many_nics = True
        net_interfaces = ip.get_host_physicl_nics()
        if len(net_interfaces) < 100:
            many_nics = False
        self.assertEqual(many_nics, True)
        # has more than 100 vfs
        def get_number_vfs():
            fd = os.popen("lspci | grep Virtual | wc -l", "r")
            num_vfs = int(fd.read())
            fd.close
            return num_vfs
        many_vfs = True
        num_vfs = get_number_vfs()
        if num_vfs < 100:
            many_vfs = False
        self.assertEqual(many_vfs, True)
        '''
        Notice:

            more than 100 vfs need to be manually configured

            because this operation need reboot to take effect,
            it can't be done by using this test-script

            step 1: enable mst
            mst start
            ls /dev/mst/

            step 2: change number of vfs
            mlxconfig -d /dev/mst/mt4125_pciconf0 set SRIOV_EN=1 NUM_OF_VFS=64
            mlxconfig -d /dev/mst/mt4125_pciconf0.1 set SRIOV_EN=1 NUM_OF_VFS=64

            step 3: reboot host to take effect
            reboot

            step 4: query number of vfs
            mlxconfig -d /dev/mst/mt4125_pciconf0 q | grep NUM_OF_VFS
            mlxconfig -d /dev/mst/mt4125_pciconf0.1 q | grep NUM_OF_VFS
        '''
        print("=======test1-done=========")


    def test_2_fast_get_host_network_facts(self):
        # init plugin()
        plugin = host_plugin.HostPlugin()
        # check back json result
        time_start = time.time()
        response_json = plugin.get_host_network_facts(None)
        time_end = time.time()
        print("get_host_network_facts() rsp: %s" % (response_json))
        response_object = jsonobject.loads(response_json)
        self.assertEqual(response_object.success, True)
        # check if get_host_network_facts() is fast
        query_fast = True
        time_cost = time_end - time_start
        if time_cost > 0.8:
            query_fast = False
        self.assertEqual(query_fast, True)
        '''
        Notice:

            0.8s is long enough to query nics with
            4 pfs with 128 vfs after optimization

            nomally it takes only 0.3s ~ 0.4s

            also, test2 is not enough to prove that it's always fast
            because these nic-info from get_host_network_facts() can
            be loaded from cache, so we need test3
        '''
        print("=======test2-done=========")


    def test_3_fast_get_host_networking_interfaces(self):
        # init plugin()
        plugin = host_plugin.HostPlugin()
        # start query
        time_start = time.time()
        nics = plugin.get_host_networking_interfaces()
        time_end = time.time()
        # check if get_host_networking_interfaces() is fast
        query_fast = True
        time_cost = time_end - time_start
        print(time_cost)
        if time_cost > 0.8:
            query_fast = False
        self.assertEqual(query_fast, True)
        print("=======test3-done=========")


if __name__ == "__main__":
    unittest.main()


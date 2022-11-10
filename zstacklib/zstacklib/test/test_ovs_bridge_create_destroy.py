
import os
import unittest
from zstacklib.utils import jsonobject
from kvmagent.plugins import ovsdpdk_network


class OvsCommand():
    def __init__(self):
        self.bridgeName = None
        self.physicalInterfaceName = None


class Test(unittest.TestCase):

    def test_1_create_ovs_bridge(self):
        def get_vswitch_pid():
            fd = os.popen("pgrep ovs-vswitchd", "r")
            vswitch_pid = int(fd.read())
            fd.close
            return vswitch_pid

        def get_create_ovs_bridge_command():
            create_ovs_bridge_command = OvsCommand()
            create_ovs_bridge_command.bridgeName = "br_enp23s0f0"
            create_ovs_bridge_command.physicalInterfaceName = "enp23s0f0"
            return create_ovs_bridge_command
        # init plugin()
        vswitch_pid_before = get_vswitch_pid()
        plugin = ovsdpdk_network.OvsDpdkNetworkPlugin()
        # prepare json command
        command = get_create_ovs_bridge_command()
        request_json = ({"body": jsonobject.dumps(command)})
        # check back json result
        response_json = plugin.create_ovs_bridge(request_json)
        print("create_ovs_bridge() rsp: %s" % (response_json))
        response_object = jsonobject.loads(response_json)
        self.assertEqual(response_object.success, True)
        # check if vSwitch restarted
        vswitch_pid_after = get_vswitch_pid()
        self.assertNotEqual(vswitch_pid_before, vswitch_pid_after)
        print("================")


    def test_2_create_duplicate_ovs_bridge(self):
        def get_vswitch_pid():
            fd = os.popen("pgrep ovs-vswitchd", "r")
            vswitch_pid = int(fd.read())
            fd.close
            return vswitch_pid

        def get_create_ovs_bridge_command():
            create_ovs_bridge_command = OvsCommand()
            create_ovs_bridge_command.bridgeName = "br_enp23s0f0"
            create_ovs_bridge_command.physicalInterfaceName = "enp23s0f0"
            return create_ovs_bridge_command
        # init plugin()
        vswitch_pid_before = get_vswitch_pid()
        plugin = ovsdpdk_network.OvsDpdkNetworkPlugin()
        # prepare json command
        command = get_create_ovs_bridge_command()
        request_json = ({"body": jsonobject.dumps(command)})
        # check back json result
        response_json = plugin.create_ovs_bridge(request_json)
        print("create_ovs_bridge() rsp: %s" % (response_json))
        response_object = jsonobject.loads(response_json)
        self.assertEqual(response_object.success, True)
        # check if vSwitch restarted
        vswitch_pid_after = get_vswitch_pid()
        self.assertEqual(vswitch_pid_before, vswitch_pid_after)
        print("================")


    def test_3_delete_ovs_bridge(self):
        def get_delete_ovs_bridge_command():
            delete_ovs_bridge_command = OvsCommand()
            delete_ovs_bridge_command.bridgeName = "br_enp23s0f0"
            delete_ovs_bridge_command.physicalInterfaceName = "enp23s0f0"
            return delete_ovs_bridge_command
        # init plugin()
        plugin = ovsdpdk_network.OvsDpdkNetworkPlugin()
        # prepare json command
        command = get_delete_ovs_bridge_command()
        request_json = ({"body": jsonobject.dumps(command)})
        # check back json result
        response_json = plugin.delete_ovs_bridge(request_json)
        print("delete_ovs_bridge() rsp: %s" % (response_json))
        response_object = jsonobject.loads(response_json)
        self.assertEqual(response_object.success, True)
        print("================")


if __name__ == "__main__":
    unittest.main()

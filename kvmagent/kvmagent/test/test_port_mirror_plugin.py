import json
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
for p in (os.path.join(ROOT, "zstacklib"), os.path.join(ROOT, "kvmagent")):
    if p not in sys.path:
        sys.path.insert(0, p)

if "simplejson" not in sys.modules:
    sys.modules["simplejson"] = json

for mod_name in (
    "concurrentlog_handler",
    "progress_report",
    "pickledb",
    "netaddr",
    "xxhash",
    "libvirt",
    "pyroute2",
    "pyroute2.netns",
    "pyroute2.netlink",
    "pyroute2.netlink.exceptions",
    "pyroute2.netlink.rtnl",
    "pyroute2.netlink.rtnl.ifinfmsg",
    "cherrypy",
    "imp",
):
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

from zstacklib.utils import iproute
from zstacklib.utils import jsonobject
from zstacklib.network.ip import link as ip_link
from kvmagent.plugins import port_mirror_plugin


class TestPortMirrorGretapMtu(unittest.TestCase):
    def test_warp_gre_link_param_forwards_mtu_and_pmtudisc(self):
        kwargs = {
            "local": "10.0.0.1",
            "remote": "10.0.0.2",
            "ttl": 255,
            "key": 7,
            "pmtudisc": 0,
            "mtu": 1500,
        }
        utils_params = iproute._warp_gre_link_param(kwargs)
        self.assertEqual(utils_params.get("mtu"), 1500)
        self.assertEqual(utils_params.get("gre_pmtudisc"), 0)

        link_params = ip_link._wrap_gre_link_param(kwargs)
        self.assertEqual(link_params.get("mtu"), 1500)
        self.assertEqual(link_params.get("gre_pmtudisc"), 0)

    def test_apply_mirror_session_creates_gretap_with_nic_mtu_and_nopmtudisc(self):
        plugin = port_mirror_plugin.PortMirrorPlugin()
        cmd = {
            "isLocal": False,
            "tunnel": {
                "dev": "br_eth1",
                "localIp": "10.0.0.1",
                "remoteIp": "10.0.0.2",
                "prefix": 24,
                "key": 12,
                "uuid": "uuid:s1 src/dst:h1/h2 l3Uuid:l3",
            },
            "mirror": {
                "type": "Bidirection",
                "snic": "vnic10.0",
                "dnic": "vnic20.0",
                "bridge": "br_eth0",
                "mName": "10.0",
            },
        }
        req = {port_mirror_plugin.http.REQUEST_BODY: jsonobject.dumps(cmd)}

        with patch.object(port_mirror_plugin.iproute, "query_addresses_by_ip", return_value=["exists"]), \
             patch.object(port_mirror_plugin.iproute, "is_device_ifname_exists", return_value=False), \
             patch.object(port_mirror_plugin.iproute, "add_link") as mock_add_link, \
             patch.object(port_mirror_plugin.iproute, "set_link_up"), \
             patch.object(port_mirror_plugin.iproute, "set_link_attribute"), \
             patch.object(plugin, "_del_if"), \
             patch.object(plugin, "_set_mirror_src_config"), \
             patch.object(plugin, "_set_mirror_dst_config"), \
             patch.object(plugin, "_set_redirect_config"):
            plugin.apply_mirror_session(req)
            mock_add_link.assert_called_once_with(
                "send10.0",
                "gretap",
                remote="10.0.0.2",
                local="10.0.0.1",
                ttl=255,
                key=12,
                pmtudisc=0,
                mtu=1500,
            )

            mock_add_link.reset_mock()
            plugin.apply_mirror_session_dest(req)
            mock_add_link.assert_called_once_with(
                "recv10.0",
                "gretap",
                remote="10.0.0.2",
                local="10.0.0.1",
                ttl=255,
                key=12,
                pmtudisc=0,
                mtu=1500,
            )

    def test_apply_mirror_session_honors_jumbo_source_nic_mtu(self):
        plugin = port_mirror_plugin.PortMirrorPlugin()
        cmd = {
            "isLocal": False,
            "tunnel": {
                "dev": "br_eth1",
                "localIp": "10.0.0.1",
                "remoteIp": "10.0.0.2",
                "prefix": 24,
                "key": 13,
                "uuid": "uuid:s2 src/dst:h1/h2 l3Uuid:l3",
            },
            "mirror": {
                "type": "Egress",
                "snic": "vnic90.0",
                "dnic": "vnic91.0",
                "bridge": "br_eth0",
                "mName": "90.0",
            },
        }
        req = {port_mirror_plugin.http.REQUEST_BODY: jsonobject.dumps(cmd)}

        with patch.object(port_mirror_plugin.iproute, "query_addresses_by_ip", return_value=["exists"]), \
             patch.object(port_mirror_plugin.iproute, "is_device_ifname_exists", return_value=False), \
             patch.object(port_mirror_plugin.iproute, "add_link") as mock_add_link, \
             patch.object(port_mirror_plugin.iproute, "set_link_up"), \
             patch.object(port_mirror_plugin.iproute, "set_link_attribute"), \
             patch.object(plugin, "_del_if"), \
             patch.object(plugin, "_set_mirror_src_config"), \
             patch.object(plugin, "_get_interface_mtu", return_value=9000):
            plugin.apply_mirror_session(req)
            self.assertEqual(mock_add_link.call_args[1]["mtu"], 9000)
            self.assertEqual(mock_add_link.call_args[1]["pmtudisc"], 0)


if __name__ == "__main__":
    unittest.main()

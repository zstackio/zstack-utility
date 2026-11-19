import json
import os
import sys
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

from zstacklib.utils import jsonobject
from kvmagent.plugins import port_mirror_plugin


class TestPortMirrorReleaseMissingEndpoint(unittest.TestCase):
    def _build_release_req(self, snic="vnic10.0", dnic="vnic20.0", bridge="br_eth0", is_local=False):
        cmd = {
            "isLocal": is_local,
            "tunnel": {
                "dev": "br_eth1",
                "localIp": "10.0.0.2",
                "remoteIp": "10.0.0.1",
                "prefix": 24,
                "key": 12,
                "uuid": "uuid:s1 src/dst:h1/h2 l3Uuid:l3",
            },
            "mirror": {
                "type": "Bidirection",
                "snic": snic,
                "dnic": dnic,
                "bridge": bridge,
                "mName": "10.0",
            },
        }
        return {port_mirror_plugin.http.REQUEST_BODY: jsonobject.dumps(cmd)}

    def test_release_dest_skips_missing_dnic_and_deletes_gre_device(self):
        plugin = port_mirror_plugin.PortMirrorPlugin()
        req = self._build_release_req(dnic="vnic20.0", bridge="br_eth0")

        with patch.object(plugin, "_clear_redirect_config") as mock_clear_redirect, \
             patch.object(plugin, "_delete_gre_device") as mock_del_gre, \
             patch.object(port_mirror_plugin.iproute, "is_device_ifname_exists", return_value=False), \
             patch.object(port_mirror_plugin.iproute, "set_link_attribute") as mock_set_attr:
            rsp = jsonobject.loads(plugin.release_mirror_session_dest(req))
            self.assertTrue(rsp.success)
            mock_clear_redirect.assert_called_once_with("recv10.0", "vnic20.0")
            mock_set_attr.assert_not_called()
            mock_del_gre.assert_called_once()

    def test_release_dest_restores_existing_dnic_to_bridge(self):
        plugin = port_mirror_plugin.PortMirrorPlugin()
        req = self._build_release_req(dnic="vnic20.0", bridge="br_eth0")

        with patch.object(plugin, "_clear_redirect_config"), \
             patch.object(plugin, "_delete_gre_device") as mock_del_gre, \
             patch.object(port_mirror_plugin.iproute, "is_device_ifname_exists", return_value=True), \
             patch.object(port_mirror_plugin.iproute, "set_link_attribute") as mock_set_attr:
            rsp = jsonobject.loads(plugin.release_mirror_session_dest(req))
            self.assertTrue(rsp.success)
            mock_set_attr.assert_called_once_with("vnic20.0", master="br_eth0")
            mock_del_gre.assert_called_once()

    def test_release_source_tolerates_none_snic_and_deletes_gre_device(self):
        plugin = port_mirror_plugin.PortMirrorPlugin()
        req = self._build_release_req(snic=None, dnic="vnic20.0")

        with patch.object(port_mirror_plugin.shell, "ShellCmd") as mock_shell_cmd, \
             patch.object(plugin, "_delete_gre_device") as mock_del_gre:
            rsp = jsonobject.loads(plugin.release_mirror_session(req))
            self.assertTrue(rsp.success)
            mock_shell_cmd.assert_not_called()
            mock_del_gre.assert_called_once()


if __name__ == "__main__":
    unittest.main()

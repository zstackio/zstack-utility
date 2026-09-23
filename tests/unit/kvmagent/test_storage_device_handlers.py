# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from zstacklib.utils import http
from kvmagent.plugins import storage_device


def _make_req(body_dict=None):
    return {
        http.REQUEST_BODY: json.dumps(body_dict or {}),
        http.REQUEST_HEADER: {},
    }


def _make_plugin():
    return storage_device.StorageDevicePlugin.__new__(storage_device.StorageDevicePlugin)


@pytest.mark.kvmagent
class TestStorageDeviceIscsiLogin:
    @pytest.mark.parametrize("requested, alternate, cidr", [
        ("172.24.189.236", "10.0.3.252", "10.0.0.0/22"),
        ("fd00:5:5:28::7f:42a4", "fd66:6:6:6:1:1:1:4c35", "fd66:6:6:6::/64"),
    ])
    def test_iscsi_login_preserves_requested_portal(self, monkeypatch, requested, alternate, cidr):
        plugin = _make_plugin()
        plugin.clean_iscsi_cache_configuration = MagicMock()
        plugin.get_iqn_login_timeout = MagicMock(return_value=10)
        plugin.trigger_events_for_block = MagicMock()

        requested_portal = "[%s]:3260" % requested if ":" in requested else "%s:3260" % requested
        alternate_portal = "[%s]:3260" % alternate if ":" in alternate else "%s:3260" % alternate
        discovery = "\n".join([
            requested_portal + ",1 iqn.2018-06.org.19172disk1",
            alternate_portal + ",1 iqn.2018-06.org.19172disk1",
        ])

        login_commands = []

        def bash_roe(cmd):
            if "discovery" in cmd:
                return 0, discovery, ""
            if "--login" in cmd:
                login_commands.append(cmd)
                return 0, "", ""
            return 0, "", ""

        def bash_o(cmd):
            if "iscsiadm -m session | grep" in cmd:
                return "[1]"
            if "Host Number:" in cmd:
                return "1"
            return ""

        monkeypatch.setattr(storage_device.bash, "bash_roe", MagicMock(side_effect=bash_roe))
        monkeypatch.setattr(storage_device.bash, "bash_o", MagicMock(side_effect=bash_o))
        monkeypatch.setattr(storage_device.bash, "bash_ro", MagicMock(return_value=(1, "")))
        monkeypatch.setattr(storage_device.bash, "bash_r", MagicMock(return_value=1))
        monkeypatch.setattr(storage_device.shell, "run", MagicMock(return_value=0))
        monkeypatch.setattr(storage_device.os.path, "exists", MagicMock(return_value=False))
        monkeypatch.setattr(storage_device.os, "listdir", MagicMock(return_value=[]))
        monkeypatch.setattr(storage_device.linux, "set_fail_if_no_path", MagicMock())

        req = _make_req({
            "iscsiServerIp": requested,
            "iscsiServerPort": "3260",
            "dataNetworkCidr": cidr,
            "iscsiTargets": [],
        })

        result = plugin.iscsi_login(req)
        rsp = json.loads(result)

        assert rsp["success"] is True
        assert login_commands
        assert len(login_commands) == 1
        assert "-p '%s'" % requested_portal in login_commands[0]
        plugin.clean_iscsi_cache_configuration.assert_called_once_with(
            "/var/lib/iscsi/nodes", requested, "3260")

        second = _make_req({
            "iscsiServerIp": alternate,
            "iscsiServerPort": "3260",
            "dataNetworkCidr": cidr,
            "iscsiTargets": [],
        })
        assert json.loads(plugin.iscsi_login(second))["success"] is True
        assert len(login_commands) == 2
        assert "-p '%s'" % alternate_portal in login_commands[1]
        assert login_commands[0] != login_commands[1]

    def test_iscsi_login_discovers_requested_portal_after_cache_cleanup(self, monkeypatch):
        plugin = _make_plugin()
        operations = []
        plugin.clean_iscsi_cache_configuration = MagicMock(side_effect=lambda *args: operations.append("cleanup"))
        plugin.get_iqn_login_timeout = MagicMock(return_value=10)
        plugin.trigger_events_for_block = MagicMock()

        discovery = "\n".join([
            "[fd00:5:5:28::7f:42a4]:3260,1 iqn.2018-06.org.19172disk1",
            "[fd66:6:6:6:1:1:1:4c35]:3260,1 iqn.2018-06.org.19172disk1",
        ])

        discovery_commands = []
        login_commands = []

        def bash_roe(cmd):
            if "discovery" in cmd:
                operations.append("discovery")
                discovery_commands.append(cmd)
                return 0, discovery, ""
            if "--login" in cmd:
                login_commands.append(cmd)
                return 0, "", ""
            return 0, "", ""

        def bash_o(cmd):
            if "iscsiadm -m session | grep" in cmd:
                return "[1]"
            if "Host Number:" in cmd:
                return "1"
            return ""

        monkeypatch.setattr(storage_device.bash, "bash_roe", MagicMock(side_effect=bash_roe))
        monkeypatch.setattr(storage_device.bash, "bash_o", MagicMock(side_effect=bash_o))
        monkeypatch.setattr(storage_device.bash, "bash_ro", MagicMock(return_value=(1, "")))
        monkeypatch.setattr(storage_device.bash, "bash_r", MagicMock(return_value=1))
        monkeypatch.setattr(storage_device.shell, "run", MagicMock(return_value=0))
        monkeypatch.setattr(storage_device.os.path, "exists", MagicMock(return_value=False))
        monkeypatch.setattr(storage_device.os, "listdir", MagicMock(return_value=[]))
        monkeypatch.setattr(storage_device.linux, "set_fail_if_no_path", MagicMock())

        req = _make_req({
            "iscsiServerIp": "fd00:5:5:28::7f:42a4",
            "iscsiServerPort": "3260",
            "dataNetworkCidr": "fd66:6:6:6::/64",
            "iscsiTargets": ["iqn.2018-06.org.19172disk1"],
        })

        result = plugin.iscsi_login(req)
        rsp = json.loads(result)

        assert rsp["success"] is True
        assert operations == ["cleanup", "discovery"]
        assert len(discovery_commands) == 1
        assert "--portal '[fd00:5:5:28::7f:42a4]:3260'" in discovery_commands[0]
        assert login_commands
        assert "-p '[fd00:5:5:28::7f:42a4]:3260'" in login_commands[0]

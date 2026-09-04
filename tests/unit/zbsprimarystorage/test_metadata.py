import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from zstacklib.utils import http
from zbsprimarystorage import zbsagent


def test_reads_physical_server_serial_number_from_sysfs():
    serial_file = mock_open(read_data="  PS-SN-001\n")
    with patch.object(zbsagent, "_physical_server_serial_number", None), \
            patch.object(zbsagent.os.path, "isfile", return_value=True), \
            patch("builtins.open", serial_file), \
            patch.object(zbsagent.shell, "call") as shell_call:
        assert zbsagent.read_physical_server_serial_number() == "PS-SN-001"
        assert zbsagent.read_physical_server_serial_number() == "PS-SN-001"
    serial_file.assert_called_once_with('/sys/class/dmi/id/product_serial')
    shell_call.assert_not_called()


def test_falls_back_to_dmidecode_for_physical_server_serial_number():
    with patch.object(zbsagent, "_physical_server_serial_number", None), \
            patch.object(zbsagent.os.path, "isfile", return_value=False), \
            patch.object(zbsagent.shell, "call", return_value="PS-SN-002\n"):
        assert zbsagent.read_physical_server_serial_number() == "PS-SN-002"


def test_sync_metadata_reports_physical_server_serial_number():
    agent = zbsagent.ZbsAgent.__new__(zbsagent.ZbsAgent)
    address = MagicMock()
    address.address = "10.0.0.10"
    mds_status = json.dumps({"result": [{"externalAddr": "10.0.0.10:10200"}], "error": {"message": ""}})
    request = {http.REQUEST_BODY: json.dumps({"addr": "10.0.0.10", "agentVersion": "5.5.38"})}

    with patch.object(zbsagent.zbsutils, "query_mds_status_info", return_value=mds_status), \
            patch.object(zbsagent.iproute, "query_addresses", return_value=[address]), \
            patch.object(zbsagent.zbsutils, "is_support_get_volume_clients", return_value=True), \
            patch.object(zbsagent, "read_physical_server_serial_number", return_value="PS-SN-001"):
        response = json.loads(agent.sync_metadata(request))

    assert response["success"] is True
    assert response["externalAddr"] == "10.0.0.10:10200"
    assert response["physicalServerSerialNumber"] == "PS-SN-001"


def test_resource_usage_is_read_only_and_reports_machine_identity():
    agent = zbsagent.ZbsAgent.__new__(zbsagent.ZbsAgent)
    manager = MagicMock()
    manager.inspect_systemd_slices.return_value = [{
        "cgroupName": "zstone.cs.slice",
        "cpuSet": "8-15",
        "cpuTime": 1000,
        "memory": 4096,
        "memoryLimit": 8192,
    }]
    request = {
        http.REQUEST_BODY: json.dumps({
            "cgroupNames": [
                "zstone.share.slice",
                "zstone.cs.slice",
                "zstone.vhost.slice",
            ],
        })
    }

    with patch.object(zbsagent, "read_physical_server_serial_number", return_value="PS-SN-001"), \
            patch.object(zbsagent.resource_control, "ResourceControlManager", return_value=manager):
        response = json.loads(agent.get_resource_usage(request))

    assert response["success"] is True
    assert response["physicalServerSerialNumber"] == "PS-SN-001"
    assert response["usages"][0]["cgroupName"] == "zstone.cs.slice"
    manager.inspect_systemd_slices.assert_called_once_with([
        "zstone.share.slice",
        "zstone.cs.slice",
        "zstone.vhost.slice",
    ])
    manager.apply.assert_not_called()
    manager.restart.assert_not_called()


def test_resource_usage_rejects_non_zbs_cgroups():
    agent = zbsagent.ZbsAgent.__new__(zbsagent.ZbsAgent)
    manager = MagicMock()
    request = {http.REQUEST_BODY: json.dumps({"cgroupNames": ["../../sys/fs/cgroup"]})}

    with patch.object(zbsagent.resource_control, "ResourceControlManager", return_value=manager):
        response = json.loads(agent.get_resource_usage(request))

    assert response["success"] is False
    assert "non-empty unique subset" in response["error"]
    manager.inspect_systemd_slices.assert_not_called()


@pytest.mark.parametrize("invalid_name", [{}, ["zstone.cs.slice"]])
def test_resource_usage_rejects_non_string_cgroup_names(invalid_name):
    agent = zbsagent.ZbsAgent.__new__(zbsagent.ZbsAgent)
    manager = MagicMock()
    request = {http.REQUEST_BODY: json.dumps({"cgroupNames": [invalid_name]})}

    with patch.object(zbsagent.resource_control, "ResourceControlManager", return_value=manager):
        response = json.loads(agent.get_resource_usage(request))

    assert response["success"] is False
    assert "non-empty unique subset" in response["error"]
    manager.inspect_systemd_slices.assert_not_called()

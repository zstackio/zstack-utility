# -*- coding: utf-8 -*-
import json
from unittest.mock import MagicMock, patch

from kvmagent.plugins import vm_config
from zstacklib.utils import http


def test_guest_huawei_collection_merges_summary_before_pci_mapping():
    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    plugin.map_pci_addresses_in_gpu_info = MagicMock(
        side_effect=lambda infos, _: infos)

    qga = MagicMock()
    qga.guest_exec_cmd_no_exitcode.side_effect = [
        "/usr/bin/npu-smi",
        "NPU ID : 2",
        "PCIe Bus Info : 0000:95:00.0",
        "summary",
    ]
    board_infos = [{"pciAddress": "0000:95:00.0"}]
    merged_infos = [
        {"pciAddress": "0000:95:00.0", "chipId": "0"},
        {"pciAddress": "0000:97:00.0", "chipId": "1"},
    ]

    with patch.object(vm_config.gpu, "get_huawei_gpu_npu_id_cmd",
                      return_value="npu-smi info -l") as npu_id_cmd, \
            patch.object(vm_config.gpu, "get_huawei_npu_id",
                         return_value=["2"]), \
            patch.object(vm_config.gpu, "get_huawei_gpu_basic_info_cmd",
                         return_value="board") as basic_info_cmd, \
            patch.object(vm_config.gpu,
                         "parse_huawei_gpu_output_by_npu_id",
                         return_value=board_infos), \
            patch.object(vm_config.gpu, "merge_huawei_gpu_chip_infos",
                         return_value=merged_infos) as merge:
        result = plugin.get_vm_hauwei_gpu_info_by_guesttool(qga)

    merge.assert_called_once_with(
        [{"pciAddress": "0000:95:00.0", "npuId": "2"}], "summary")
    assert qga.guest_exec_cmd_no_exitcode.call_args_list[0].args == (
        "command -v npu-smi",)
    assert qga.guest_exec_cmd_no_exitcode.call_args_list[-1].args == (
        "/usr/bin/npu-smi info",)
    npu_id_cmd.assert_called_once_with("/usr/bin/npu-smi", False)
    basic_info_cmd.assert_called_once_with(
        "2", iswindows=False, npu_smi_path="/usr/bin/npu-smi")
    assert result == merged_infos


def test_guest_huawei_collection_keeps_board_data_when_summary_fails():
    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    plugin.map_pci_addresses_in_gpu_info = MagicMock(
        side_effect=lambda infos, _: infos)

    qga = MagicMock()
    qga.guest_exec_cmd_no_exitcode.side_effect = [
        "/usr/bin/npu-smi",
        "NPU ID : 1",
        "PCIe Bus Info : 0000:C2:00.0",
        None,
    ]
    board_infos = [{"pciAddress": "0000:c2:00.0"}]

    with patch.object(vm_config.gpu, "get_huawei_gpu_npu_id_cmd",
                      return_value="npu-smi info -l"), \
            patch.object(vm_config.gpu, "get_huawei_npu_id",
                         return_value=["1"]), \
            patch.object(vm_config.gpu, "get_huawei_gpu_basic_info_cmd",
                         return_value="board"), \
            patch.object(vm_config.gpu,
                         "parse_huawei_gpu_output_by_npu_id",
                         return_value=board_infos), \
            patch.object(vm_config.gpu, "merge_huawei_gpu_chip_infos") \
            as merge:
        result = plugin.get_vm_hauwei_gpu_info_by_guesttool(qga)

    merge.assert_not_called()
    assert result == [{"pciAddress": "0000:c2:00.0", "npuId": "1"}]


def test_vm_gpu_info_sync_returns_both_910c_chips():
    """The VM sync API exposes both host PCI devices from real guest output."""
    board_output = """
Serial Number : BOARD002
PCIe Bus Info : 0000:95:00.0
Total DDR Capacity(MB) : 131072
"""
    summary_output = """
| 2     Ascend910           | OK            | 163.1                |
| 0     4                   | 0000:95:00.0  | 0 / 0  2909 / 65536 |
| 2     Ascend910           | OK            | 160.8                |
| 1     5                   | 0000:97:00.0  | 0 / 0  2882 / 65536 |
"""

    domain = MagicMock()
    domain.name.return_value = "vm-uuid"
    domain.isActive.return_value = True
    qga = MagicMock()
    qga.domain = domain
    qga.state = "Running"
    qga.os = "centos"
    qga.os_version = "7"

    def guest_command(command):
        if command == "npu-smi info -l":
            return "NPU ID : 2"
        if command == "command -v npu-smi":
            return "/usr/bin/npu-smi"
        if command == "/usr/bin/npu-smi info":
            return summary_output
        if command == "board-2":
            return board_output
        if command.startswith("lspci -s "):
            return "Huawei Technologies Device d802"
        raise AssertionError("unexpected guest command: %s" % command)

    qga.guest_exec_cmd_no_exitcode.side_effect = guest_command
    request = {
        http.REQUEST_BODY: json.dumps({
            "vmUuid": "vm-uuid",
            "vendors": ["Huawei"],
        })
    }
    pci_mapping = {
        "0000:95:00.0": "0000:42:00.0",
        "0000:97:00.0": "0000:43:00.0",
    }
    merged_infos = [
        {
            "pciAddress": "0000:95:00.0",
            "memory": "65536 MB",
            "npuId": "2",
            "chipId": "0",
            "physicalId": "4",
        },
        {
            "pciAddress": "0000:97:00.0",
            "memory": "65536 MB",
            "npuId": "2",
            "chipId": "1",
            "physicalId": "5",
        },
    ]

    class TestVendorEnum(object):
        NVIDIA = "NVIDIA"
        AMD = "AMD"
        HAIGUANG = "Haiguang"
        HUAWEI = "Huawei"
        TIANSHU = "TianShu"
        ENFLAME = "Enflame"
        ALIBABA = "Alibaba"
        KUNLUNXIN = "Kunlunxin"

    class QgaFactory(object):
        QGA_STATE_RUNNING = "Running"

        def __new__(cls, _domain):
            return qga

    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    with patch.object(vm_config, "get_virt_domain", return_value=domain), \
            patch.object(vm_config, "VmQga", QgaFactory), \
            patch.object(vm_config, "VendorEnum", TestVendorEnum), \
            patch.object(vm_config.VmConfigPlugin,
                         "VM_CONFIG_SYNC_OS_VERSION_SUPPORT",
                         {"centos": ("7",)}), \
            patch.object(vm_config.gpu, "get_huawei_gpu_npu_id_cmd",
                         return_value="npu-smi info -l"), \
            patch.object(vm_config.gpu, "get_huawei_npu_id",
                         return_value=["2"]), \
            patch.object(vm_config.gpu, "get_huawei_gpu_basic_info_cmd",
                         return_value="board-2"), \
            patch.object(vm_config.gpu,
                         "parse_huawei_gpu_output_by_npu_id",
                         return_value=[{
                             "pciAddress": "0000:95:00.0",
                             "memory": "131072 MB",
                         }]), \
            patch.object(vm_config.gpu, "merge_huawei_gpu_chip_infos",
                         return_value=merged_infos), \
            patch.object(vm_config.pci, "get_pci_passthrough_mapping",
                         return_value=pci_mapping):
        response = json.loads(plugin.vm_gpu_info_sync(request))

    assert response["success"] is True
    assert [item["pciAddress"] for item in response["gpuInfos"]] == [
        "0000:42:00.0", "0000:43:00.0"]
    assert [item["memory"] for item in response["gpuInfos"]] == [
        "65536 MB", "65536 MB"]
    assert [item["physicalId"] for item in response["gpuInfos"]] == [
        "4", "5"]
    assert all(item["isDriverLoaded"] for item in response["gpuInfos"])

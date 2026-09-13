# -*- coding: utf-8 -*-
import sys
import types
from unittest.mock import MagicMock, patch


def _install_import_stubs():
    oslo_concurrency = types.ModuleType("oslo_concurrency")
    oslo_concurrency.processutils = MagicMock()
    sys.modules.setdefault("oslo_concurrency", oslo_concurrency)

    oslo_log = types.ModuleType("oslo_log")
    oslo_log.log = MagicMock()
    sys.modules.setdefault("oslo_log", oslo_log)

    stevedore = types.ModuleType("stevedore")
    stevedore.driver = MagicMock()
    sys.modules.setdefault("stevedore", stevedore)

    sys.modules.setdefault(
        "bm_instance_agent.common.utils", MagicMock())
    sys.modules.setdefault(
        "zstacklib.utils.network_ipv6", MagicMock())


_install_import_stubs()

from bm_instance_agent import manager


def test_baremetal_huawei_parser_does_not_return_empty_device():
    assert manager.gpu.parse_huawei_gpu_output_by_npu_id(
        "summary command failed") == []


def test_baremetal_huawei_collection_uses_summary_and_matched_npu_id():
    shared_gpu = types.ModuleType("zstacklib.utils.gpu")
    shared_gpu.merge_huawei_gpu_chip_infos = MagicMock(return_value=[
        {
            "pciAddress": "0000:95:00.0",
            "npuId": "2",
            "chipId": "0",
            "physicalId": "4",
        },
        {
            "pciAddress": "0000:97:00.0",
            "memory": "65536 MB",
            "serialNumber": "BOARD002",
            "npuId": "2",
            "chipId": "1",
            "physicalId": "5",
        },
    ])

    commands = []

    def execute(command, _):
        commands.append(command)
        if command == "which npu-smi":
            return 0, "", ""
        if command == "list":
            return 0, "NPU ID : 2", ""
        if command == "board-2":
            return 0, "board", ""
        if command == "npu-smi info":
            return 0, "summary", ""
        if command == "product-2":
            return 0, "Product Type : Ascend 910C", ""
        raise AssertionError("unexpected command: %s" % command)

    agent = manager.AgentManager.__new__(manager.AgentManager)
    with patch.dict(sys.modules, {"zstacklib.utils.gpu": shared_gpu}), \
            patch.object(manager.bm_utils, "shell_cmd", side_effect=execute), \
            patch.object(manager.gpu, "get_huawei_gpu_npu_id_cmd",
                         return_value="list"), \
            patch.object(manager.gpu, "get_huawei_npu_id",
                         return_value=["2"]), \
            patch.object(manager.gpu, "get_huawei_gpu_basic_info_cmd",
                         side_effect=lambda npu_id: "board-%s" % npu_id), \
            patch.object(manager.gpu, "parse_huawei_gpu_output_by_npu_id",
                         return_value=[{
                             "pciAddress": "0000:95:00.0",
                             "serialNumber": "BOARD002",
                         }]), \
            patch.object(manager.gpu, "get_huawei_gpu_product_name_cmd",
                         side_effect=lambda npu_id: "product-%s" % npu_id), \
            patch.object(manager.gpu, "get_huawei_product_type",
                         return_value="Ascend 910C"):
        result = agent._collect_huawei_gpu_info("00000000:97:00.0")

    shared_gpu.merge_huawei_gpu_chip_infos.assert_called_once_with(
        [{
            "pciAddress": "0000:95:00.0",
            "serialNumber": "BOARD002",
            "npuId": "2",
        }],
        "summary")
    assert "npu-smi info" in commands
    assert "product-2" in commands
    assert result == {
        "memory": "65536 MB",
        "power": None,
        "serialNumber": "BOARD002",
        "isDriverLoaded": True,
        "device": "-",
        "name": "Ascend 910C",
    }


def test_baremetal_pci_inspection_returns_both_910c_chips():
    """The Baremetal PCI seam enriches both physical PCI devices."""
    lspci_output = """\
Slot: 00000000:95:00.0
Class: Processing accelerators [1200]
Vendor: Huawei Technologies Co., Ltd. [19e5]
Device: Device d802 [d802]
SVendor: Huawei Technologies Co., Ltd. [19e5]
SDevice: Device d802 [d802]

Slot: 00000000:97:00.0
Class: Processing accelerators [1200]
Vendor: Huawei Technologies Co., Ltd. [19e5]
Device: Device d802 [d802]
SVendor: Huawei Technologies Co., Ltd. [19e5]
SDevice: Device d802 [d802]
"""
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
    shared_gpu = types.ModuleType("zstacklib.utils.gpu")
    shared_gpu.merge_huawei_gpu_chip_infos = MagicMock(return_value=[
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
    ])

    def execute(command, _errorout=False):
        if command == "lspci -Dmmnnv":
            return 0, lspci_output, ""
        if command == "which npu-smi":
            return 0, "/usr/bin/npu-smi", ""
        if command == "npu-smi info -l":
            return 0, "NPU ID : 2", ""
        if "info -t board -i 2;" in command:
            return 0, board_output, ""
        if command == "npu-smi info":
            return 0, summary_output, ""
        if command == "npu-smi info -t product -i 2":
            return 0, "Product Type : Ascend 910C", ""
        raise AssertionError("unexpected command: %s" % command)

    agent = manager.AgentManager.__new__(manager.AgentManager)
    with patch.dict(sys.modules, {"zstacklib.utils.gpu": shared_gpu}), \
            patch.object(manager.bm_utils, "shell_cmd", side_effect=execute), \
            patch.object(manager.os.path, "realpath",
                         return_value="/sys/kernel/iommu_groups/7"):
        devices = agent._get_pci_info()

    by_pci = {device["pciDeviceAddress"]: device for device in devices}
    assert set(by_pci) == {
        "00000000:95:00.0", "00000000:97:00.0"}
    assert by_pci["00000000:95:00.0"]["addonInfo"]["memory"] == \
        "65536 MB"
    assert by_pci["00000000:97:00.0"]["addonInfo"]["memory"] == \
        "65536 MB"
    assert by_pci["00000000:95:00.0"]["name"] == "Ascend 910C"
    assert by_pci["00000000:97:00.0"]["name"] == "Ascend 910C"

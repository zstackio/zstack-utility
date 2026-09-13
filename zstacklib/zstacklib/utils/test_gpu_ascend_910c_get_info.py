# -*- coding: utf-8 -*-
import unittest

try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch

from zstacklib.gpu.base import GPUInfo, VendorEnum
from zstacklib.gpu.vendors.huawei import Huawei
from zstacklib.utils import gpu


BASIC_INFO_OUTPUT = """
Serial Number : BOARD002
PCIe Bus Info : 0000:95:00.0
HBM Capacity(MB) : 65536
Chip ID : 0
HBM Capacity(MB) : 65536
Chip ID : 1
NPU Real-time Power(W) : 163.1
Chip ID : 0
NPU Real-time Power(W) : 163.1
Chip ID : 1
"""

SUMMARY_OUTPUT = """
| 2     Ascend910           | OK            | 163.1                |
| 0     4                   | 0000:95:00.0  | 0 / 0  2909 / 65536 |
| 2     Ascend910           | OK            | -                    |
| 1     5                   | 0000:97:00.0  | 0 / 0  2882 / 65536 |
"""


class TestAscend910CGetInfo(unittest.TestCase):
    def test_get_info_by_pci_returns_target_logical_npu_only(self):
        summary = SUMMARY_OUTPUT + """
| 7     Ascend910           | OK            | 160.0                |
| 0     6                   | 0000:c2:00.0  | 0 / 0  2900 / 65536 |
"""
        commands = []

        def execute(command):
            commands.append(command)
            if command == "npu-smi info":
                return 0, summary, ""
            if "info -t board -i 2" in command:
                return 0, BASIC_INFO_OUTPUT, ""
            if "info -t hccs -i 2 -c 1" in command:
                return 0, "hccs health status : OK", ""
            self.fail("unexpected npu-smi command: %s" % command)

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            infos = Huawei.get_info_by_pci("0000:97:00.0")

        self.assertEqual(
            [info.pci_address for info in infos],
            ["0000:95:00.0", "0000:97:00.0"])
        self.assertFalse(any("-i 7" in command for command in commands))

    def test_plugin_enriches_both_chips_before_returning_match(self):
        gpu_infos = [
            GPUInfo("0000:95:00.0", extra={
                "npuId": "2", "chipId": "0", "physicalId": "4"}),
            GPUInfo("0000:97:00.0", extra={
                "npuId": "2", "chipId": "1", "physicalId": "5"}),
        ]
        plugin = MagicMock()
        plugin.is_available.return_value = True
        plugin.get_basic_info.return_value = gpu_infos
        plugin.get_info_by_pci.return_value = gpu_infos

        def enrich(info_map, pci_addresses):
            self.assertEqual(
                [info_map[address]["physicalId"] for address in pci_addresses],
                ["4", "5"])
            info_map["0000:97:00.0"]["opaque"] = {
                "aiosRankTable": {"server_count": 2}}

        plugin.enrich_addon_info.side_effect = enrich
        with patch("zstacklib.gpu.get_gpu_vendor", return_value=plugin), \
                patch("zstacklib.gpu.get_vendor_enum_mapping",
                      return_value={"Huawei": "Huawei"}):
            result = gpu.get_info(
                "0000:97:00.0", vendor_name=VendorEnum.HUAWEI)

        plugin.enrich_addon_info.assert_called_once()
        self.assertEqual(result["physicalId"], "5")
        self.assertEqual(
            result["opaque"]["aiosRankTable"]["server_count"], 2)

    def test_plugin_returns_chip1_with_full_rank_table(self):
        def npu_smi(command):
            if command == "npu-smi info":
                return 0, SUMMARY_OUTPUT, ""
            if "info -t board -i 2" in command:
                return 0, BASIC_INFO_OUTPUT, ""
            if "info -t hccs -i 2 -c " in command:
                return 0, "hccs health status : OK", ""
            if command == "npu-smi info -t product -i 2":
                return 0, \
                    "This device does not support querying product.", ""
            self.fail("unexpected npu-smi command: %s" % command)

        def hccn(command):
            if "hccn_tool -i 4 " in command:
                return 0, "ipaddr:10.20.0.6\nnetmask:255.255.0.0", ""
            if "hccn_tool -i 5 " in command:
                return 0, "ipaddr:10.20.0.7\nnetmask:255.255.0.0", ""
            self.fail("unexpected HCCN command: %s" % command)

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["2"]), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch.object(gpu, "get_npu_smi_path",
                             return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=npu_smi), \
                patch.object(gpu, "bash_roe", side_effect=hccn):
            result = gpu.get_info(
                "0000:97:00.0", vendor_name=VendorEnum.HUAWEI)

        self.assertEqual(result["npuId"], "2")
        self.assertEqual(result["chipId"], "1")
        self.assertEqual(result["physicalId"], "5")
        self.assertEqual(result["memory"], "65536 MB")
        self.assertNotIn("productName", result)
        self.assertEqual(
            [entry["device_id"] for entry in
             result["opaque"]["aiosRankTable"]["server_list"]],
            ["4", "5"])

    def test_legacy_returns_chip1_with_full_rank_table(self):
        def execute(command):
            if "info -t board -i 2" in command:
                return 0, BASIC_INFO_OUTPUT, ""
            if command == "npu-smi info":
                return 0, SUMMARY_OUTPUT, ""
            if "info -t hccs -i 2 -c 1" in command:
                return 0, "hccs health status : OK", ""
            if command == "npu-smi info -t product -i 2":
                return 0, \
                    "This device does not support querying product.", ""
            if "hccn_tool -i 4 " in command:
                return 0, "ipaddr:10.20.0.6\nnetmask:255.255.0.0", ""
            if "hccn_tool -i 5 " in command:
                return 0, "ipaddr:10.20.0.7\nnetmask:255.255.0.0", ""
            self.fail("unexpected legacy command: %s" % command)

        with patch.object(Huawei, "is_available", return_value=False), \
                patch.object(gpu, "get_npu_smi_path",
                             return_value="npu-smi"), \
                patch.object(gpu, "bash_ro",
                             return_value=(0, "NPU ID : 2")), \
                patch.object(gpu, "bash_roe", side_effect=execute):
            result = gpu.get_info(
                "0000:97:00.0", vendor_name=VendorEnum.HUAWEI)

        self.assertEqual(result["chipId"], "1")
        self.assertEqual(result["physicalId"], "5")
        self.assertEqual(result["memory"], "65536 MB")
        self.assertNotIn("productName", result)
        self.assertEqual(
            [entry["device_id"] for entry in
             result["opaque"]["aiosRankTable"]["server_list"]],
            ["4", "5"])

    def test_partial_summary_preserves_unclassified_board_pci(self):
        board_infos = [{
            "pciAddress": "0000:95:00.0",
            "memory": "131072 MB",
            "serialNumber": "BOARD002",
            "npuId": "2",
        }]
        partial_summary = """
| 2     Ascend910           | OK            | -                    |
| 1     5                   | 0000:97:00.0  | 0 / 0  2909 / 65536 |
"""

        result = gpu.merge_huawei_gpu_chip_infos(
            board_infos, partial_summary)

        self.assertEqual(
            [info["pciAddress"] for info in result],
            ["0000:95:00.0", "0000:97:00.0"])
        self.assertEqual([info["memory"] for info in result],
                         ["65536 MB", "65536 MB"])

    def test_warning_summary_preserves_board_without_rank_table_id(self):
        board_infos = [{
            "pciAddress": "0000:95:00.0",
            "memory": "131072 MB",
            "serialNumber": "BOARD002",
            "npuId": "2",
        }]
        warning_summary = """
| 2     Ascend910           | Warning       | 163.1                |
| 0     4                   | 0000:95:00.0  | 0 / 0  2909 / 65536 |
| 2     Ascend910           | OK            | -                    |
| 1     5                   | 0000:97:00.0  | 0 / 0  2882 / 65536 |
"""

        result = gpu.merge_huawei_gpu_chip_infos(
            board_infos, warning_summary)
        info_map = {info["pciAddress"]: info for info in result}

        self.assertEqual(
            [info["pciAddress"] for info in result],
            ["0000:95:00.0", "0000:97:00.0"])
        self.assertNotIn("chipId", result[0])
        self.assertNotIn("physicalId", result[0])
        self.assertEqual(result[1]["physicalId"], "5")
        self.assertEqual(Huawei.get_rank_table_device_ids(
            info_map, sorted(info_map)), ["5"])

    def test_malformed_board_entry_does_not_create_pseudo_device(self):
        result = gpu.merge_huawei_gpu_chip_infos(
            [{"npuId": "2", "memory": "131072 MB"}], SUMMARY_OUTPUT)

        self.assertEqual(
            [info["pciAddress"] for info in result],
            ["0000:95:00.0", "0000:97:00.0"])
        self.assertEqual(
            gpu.parse_huawei_gpu_output_by_npu_id(
                "summary command failed"), [])

    def test_legacy_topology_fallback_uses_910c_physical_id(self):
        # Synthetic isolation state using the real 910C Phy-ID matrix shape.
        output = """\
          Phy-ID2    Phy-ID3    Phy-ID12   Phy-ID13
Phy-ID2    X          SIO        SYS        SYS
Phy-ID3    SIO        X          SYS        SYS
"""

        def execute(command):
            if "-t hccs" in command:
                return 0, "no health line", ""
            return 0, output, ""

        with patch.object(gpu, "get_npu_smi_path",
                          return_value="npu-smi"), \
                patch.object(gpu, "bash_roe", side_effect=execute):
            self.assertTrue(gpu.check_huawei_npu_is_isolated(
                "1", ["1", "6"], chip_id="0", physical_id="2"))


if __name__ == "__main__":
    unittest.main()

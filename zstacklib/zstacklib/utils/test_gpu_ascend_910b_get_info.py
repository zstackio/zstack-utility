# -*- coding: utf-8 -*-
import unittest

try:
    from unittest.mock import MagicMock, patch
except ImportError:
    from mock import MagicMock, patch

from zstacklib.gpu.base import GPUInfo, VendorEnum
from zstacklib.gpu.vendors.huawei import Huawei
from zstacklib.utils import gpu


BOARD_OUTPUT = """
Serial Number : BOARD910B
PCIe Bus Info : 0000:C2:00.0
HBM Capacity(MB) : 32768
NPU Real-time Power(W) : 82
"""

SUMMARY_OUTPUT = """
| 1     910B4               | OK            | 82.3                 |
| 0                         | 0000:C2:00.0  | 0 / 0  2658 / 32768 |
"""


class TestAscend910BGetInfo(unittest.TestCase):
    def test_get_info_by_pci_queries_only_target_npu(self):
        commands = []

        def execute(command):
            commands.append(command)
            if command == "npu-smi info":
                return 0, SUMMARY_OUTPUT, ""
            if "info -t board -i 1" in command:
                return 0, BOARD_OUTPUT, ""
            self.fail("unexpected npu-smi command: %s" % command)

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            infos = Huawei.get_info_by_pci("0000:c2:00.0")

        self.assertEqual([info.pci_address for info in infos],
                         ["0000:c2:00.0"])
        self.assertEqual(
            [command for command in commands if "-t board" in command],
            ["npu-smi info -t board -i 1;npu-smi info -i 1 -t memory;"
             "npu-smi info -t power -i 1"])

    def test_plugin_preserves_single_chip_metadata(self):
        gpu_infos = [
            GPUInfo("0000:c2:00.0", memory="32768 MB",
                    extra={"npuId": "1", "chipId": "0"}),
            GPUInfo("0000:42:00.0", memory="32768 MB",
                    extra={"npuId": "7", "chipId": "0"}),
        ]
        plugin = MagicMock()
        plugin.is_available.return_value = True
        plugin.get_basic_info.return_value = gpu_infos
        plugin.get_info_by_pci.return_value = gpu_infos

        def enrich(info_map, pci_addresses):
            self.assertEqual(pci_addresses,
                             ["0000:42:00.0", "0000:c2:00.0"])
            info_map["0000:c2:00.0"]["opaque"] = {
                "aiosRankTable": {
                    "server_count": 2,
                    "server_list": [
                        {"device_id": "1"}, {"device_id": "7"}],
                }}

        plugin.enrich_addon_info.side_effect = enrich
        with patch("zstacklib.gpu.get_gpu_vendor", return_value=plugin), \
                patch("zstacklib.gpu.get_vendor_enum_mapping",
                      return_value={"Huawei": "Huawei"}):
            result = gpu.get_info(
                "0000:C2:00.0", vendor_name=VendorEnum.HUAWEI)

        self.assertEqual(result["npuId"], "1")
        self.assertEqual(result["chipId"], "0")
        self.assertNotIn("physicalId", result)
        self.assertEqual(
            [entry["device_id"] for entry in
             result["opaque"]["aiosRankTable"]["server_list"]],
            ["1", "7"])

    def test_legacy_keeps_board_fallback_without_physical_id(self):
        board_output = """
Serial Number : BOARD910B
PCIe Bus Info : 0000:C2:00.0
HBM Capacity(MB) : 32768
NPU Real-time Power(W) : 82
"""

        with patch.object(Huawei, "is_available", return_value=False), \
                patch.object(Huawei, "get_aios_rank_table",
                             return_value={
                                 "server_count": 1,
                                 "server_list": [{"device_id": "1"}],
                             }), \
                patch.object(gpu, "get_npu_smi_path",
                             return_value="npu-smi"), \
                patch.object(gpu, "bash_ro",
                             return_value=(0, "NPU ID : 1")), \
                patch.object(gpu, "bash_roe", side_effect=[
                    (0, board_output, ""),
                    (1, "", "summary unavailable"),
                    (0, "This device does not support querying product.", ""),
                ]), \
                patch.object(gpu, "check_huawei_npu_is_isolated",
                             return_value=False):
            result = gpu.get_info(
                "0000:c2:00.0", vendor_name=VendorEnum.HUAWEI)

        self.assertEqual(result["npuId"], "1")
        self.assertEqual(result["memory"], "32768 MB")
        self.assertNotIn("productName", result)
        self.assertNotIn("physicalId", result)
        self.assertEqual(
            result["opaque"]["aiosRankTable"]["server_list"],
            [{"device_id": "1"}])

    def test_legacy_normalizes_eight_digit_pci_domain(self):
        board_output = """
Serial Number : BOARD910B
PCIe Bus Info : 00000000:C2:00.0
HBM Capacity(MB) : 32768
"""

        with patch.object(gpu, "get_npu_smi_path",
                          return_value="npu-smi"), \
                patch.object(gpu, "bash_ro",
                             return_value=(0, "NPU ID : 1")), \
                patch.object(gpu, "bash_roe", side_effect=[
                    (0, board_output, ""),
                    (1, "", "summary unavailable"),
                    (1, "", "product unavailable"),
                ]), \
                patch.object(gpu, "check_huawei_npu_is_isolated",
                             return_value=False), \
                patch.object(Huawei, "get_aios_rank_table",
                             return_value=None):
            result = gpu._collect_huawei_legacy("0000:c2:00.0")

        self.assertIsNotNone(result)
        self.assertEqual(result["npuId"], "1")
        self.assertEqual(result["serialNumber"], "BOARD910B")

    def test_invalid_npu_placeholders_are_filtered(self):
        output = """
NPU ID : -1
NPU ID : 1
NPU ID : unknown
NPU ID : 7
"""

        self.assertEqual(gpu.get_huawei_npu_id(output), ["1", "7"])


if __name__ == "__main__":
    unittest.main()

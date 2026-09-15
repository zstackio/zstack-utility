# -*- coding: utf-8 -*-
import unittest

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from zstacklib.gpu.vendors.huawei import Huawei
from zstacklib.utils.gpu import check_huawei_npu_is_isolated


BOARD_OUTPUT = """
Serial Number : BOARD910B
PCIe Bus Info : 0000:C2:00.0
HBM Capacity(MB) : 32768
"""

SUMMARY_OUTPUT = """
| 1     910B4               | OK            | 82.3                 |
| 0                         | 0000:C2:00.0  | 0 / 0  2658 / 32768 |
"""


class TestAscend910BVendor(unittest.TestCase):
    def test_unsupported_product_query_does_not_add_product_name(self):
        pci_addresses = ["0000:c2:00.0"]
        gpu_info_map = {
            "0000:c2:00.0": {"npuId": "1"},
        }

        def query_product(command):
            self.assertTrue(command.endswith(" -i 1"))
            return 0, "This device does not support querying product.", ""

        with patch.object(Huawei, "get_npu_ids", return_value=["1"]), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=query_product), \
                patch.object(Huawei, "get_aios_rank_table",
                             return_value=None):
            Huawei.enrich_addon_info(gpu_info_map, pci_addresses)

        self.assertNotIn("productName", gpu_info_map["0000:c2:00.0"])

    def test_get_basic_info_keeps_board_data_when_summary_is_unavailable(self):
        def execute(command):
            if command.endswith(" info"):
                return 1, "", "summary unavailable"
            return 0, BOARD_OUTPUT, ""

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["1"]), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch.object(Huawei, "check_npu_isolation",
                             return_value=False), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            infos = Huawei.get_basic_info()

        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].pci_address, "0000:c2:00.0")
        self.assertEqual(infos[0].memory, "32768 MB")
        self.assertEqual(infos[0].extra["npuId"], "1")
        self.assertNotIn("physicalId", infos[0].extra)

    def test_summary_keeps_npu_id_without_physical_id(self):
        infos = Huawei.parse_chip_info_summary(SUMMARY_OUTPUT)

        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].pci_address, "0000:c2:00.0")
        self.assertEqual(infos[0].extra["npuId"], "1")
        self.assertEqual(infos[0].extra["chipId"], "0")
        self.assertNotIn("physicalId", infos[0].extra)

    def test_rank_table_keeps_npu_ids(self):
        gpu_info_map = {
            "0000:c2:00.0": {"npuId": "1", "chipId": "0"},
            "0000:42:00.0": {"npuId": "7", "chipId": "0"},
        }

        result = Huawei.get_rank_table_device_ids(
            gpu_info_map, sorted(gpu_info_map))

        self.assertEqual(result, ["1", "7"])

    def test_metrics_keep_single_chip_command_without_selector(self):
        metric_output = """
Serial Number : BOARD910B
PCIe Bus Info : 0000:C2:00.0
Aicore Usage Rate(%) : 11
HBM Capacity(MB) : 32768
"""
        commands = []

        def execute(command):
            commands.append(command)
            if command.endswith(" info"):
                return 0, SUMMARY_OUTPUT, ""
            return 0, metric_output, ""

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["1"]), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            metrics = Huawei.collect_metrics()

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].pci_address, "0000:c2:00.0")
        metric_commands = [command for command in commands if ";" in command]
        self.assertEqual(len(metric_commands), 1)
        self.assertNotIn(" -c ", metric_commands[0])

    def test_single_chip_devices_do_not_gain_dependencies(self):
        first = type("PciDeviceTO", (), {})()
        first.pciDeviceAddress = "0000:c2:00.0"
        first.dependentDevices = []
        second = type("PciDeviceTO", (), {})()
        second.pciDeviceAddress = "0000:42:00.0"
        second.dependentDevices = []
        gpu_info_map = {
            first.pciDeviceAddress: {"npuId": "1", "chipId": "0"},
            second.pciDeviceAddress: {"npuId": "7", "chipId": "0"},
        }

        Huawei.enrich_pci_device_dependencies(
            [first, second], gpu_info_map)

        self.assertEqual(first.dependentDevices, [])
        self.assertEqual(second.dependentDevices, [])

    def test_isolation_keeps_legacy_chip_zero_query(self):
        with patch.object(Huawei, "get_npu_smi_cmd",
                          return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      return_value=(
                          0, "hccs health status : OK", "")) as execute:
            result = Huawei.check_npu_isolation("1", ["1", "7"])

        self.assertFalse(result)
        execute.assert_called_once_with(
            "npu-smi info -t hccs -i 1 -c 0")

    def test_legacy_topology_fallback_accepts_indented_npu_row(self):
        output = """\
             NPU0   NPU1   CPU Affinity
        NPU0   X      SYS    0-23
"""

        def execute(command):
            if "-t hccs" in command:
                return 0, "no health line", ""
            return 0, output, ""

        with patch("zstacklib.utils.gpu.get_npu_smi_path",
                   return_value="npu-smi"), \
                patch("zstacklib.utils.gpu.bash_roe",
                      side_effect=execute):
            result = check_huawei_npu_is_isolated(
                "0", ["0", "1"])

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()

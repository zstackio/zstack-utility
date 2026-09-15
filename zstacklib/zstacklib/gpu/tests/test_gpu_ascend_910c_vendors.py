# -*- coding: utf-8 -*-
import unittest
from io import StringIO

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from zstacklib.gpu.vendors.huawei import Huawei


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


class TestAscend910CVendor(unittest.TestCase):
    def test_mixed_models_query_product_per_logical_npu_when_supported(self):
        # Synthetic supported responses keep coverage for mixed-model hosts;
        # the current 910B/910C driver reports product querying as unsupported.
        pci_addresses = [
            "0000:c2:00.0", "0000:95:00.0", "0000:97:00.0",
        ]
        gpu_info_map = {
            "0000:c2:00.0": {"npuId": "1"},
            "0000:95:00.0": {"npuId": "2", "physicalId": "4"},
            "0000:97:00.0": {"npuId": "2", "physicalId": "5"},
        }

        def query_product(command):
            if command.endswith(" -i 1"):
                return 0, "Product Type : Ascend 910B", ""
            if command.endswith(" -i 2"):
                return 0, "Product Type : Ascend 910C", ""
            self.fail("unexpected command: %s" % command)

        with patch.object(Huawei, "get_npu_ids", return_value=["1", "2"]), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=query_product), \
                patch.object(Huawei, "get_aios_rank_table",
                             return_value=None):
            Huawei.enrich_addon_info(gpu_info_map, pci_addresses)

        self.assertEqual(
            gpu_info_map["0000:c2:00.0"]["productName"], "Ascend 910B")
        self.assertEqual(
            gpu_info_map["0000:95:00.0"]["productName"], "Ascend 910C")
        self.assertEqual(
            gpu_info_map["0000:97:00.0"]["productName"], "Ascend 910C")

    def test_get_basic_info_merges_both_chips_and_checks_each_chip(self):
        def execute(command):
            if command.endswith(" info"):
                return 0, SUMMARY_OUTPUT, ""
            return 0, BASIC_INFO_OUTPUT, ""

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["2"]), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch.object(
                    Huawei,
                    "check_npu_isolation",
                    side_effect=lambda _npu_id, _npu_ids, chip_id=None,
                    physical_id=None:
                    chip_id == "1") as check_isolation, \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            infos = Huawei.get_basic_info()

        self.assertEqual(
            [info.pci_address for info in infos],
            ["0000:95:00.0", "0000:97:00.0"])
        self.assertEqual([info.memory for info in infos],
                         ["65536 MB", "65536 MB"])
        self.assertEqual(
            [info.extra["physicalId"] for info in infos], ["4", "5"])
        self.assertEqual(
            [info.extra["isIsolated"] for info in infos], [False, True])
        self.assertEqual(
            [call.kwargs.get("chip_id") for call in
             check_isolation.call_args_list], ["0", "1"])
        self.assertEqual(
            [call.kwargs.get("physical_id") for call in
             check_isolation.call_args_list], ["4", "5"])

    def test_get_basic_info_keeps_board_fallback_for_partial_summary(self):
        partial_summary = """
| 2     Ascend910           | OK            | -                    |
| 1     5                   | 0000:97:00.0  | 0 / 0  2882 / 65536 |
"""

        def execute(command):
            if command.endswith(" info"):
                return 0, partial_summary, ""
            return 0, BASIC_INFO_OUTPUT, ""

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["2"]), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch.object(Huawei, "check_npu_isolation",
                             return_value=False), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            infos = Huawei.get_basic_info()

        self.assertEqual(
            [info.pci_address for info in infos],
            ["0000:95:00.0", "0000:97:00.0"])
        self.assertEqual(infos[0].memory, "65536 MB")
        self.assertNotIn("chipId", infos[0].extra)
        self.assertEqual(infos[1].extra["physicalId"], "5")

    def test_get_basic_info_preserves_warning_board_without_chip_metadata(self):
        warning_summary = """
| 2     Ascend910           | Warning       | 163.1                |
| 0     4                   | 0000:95:00.0  | 0 / 0  2909 / 65536 |
| 2     Ascend910           | OK            | -                    |
| 1     5                   | 0000:97:00.0  | 0 / 0  2882 / 65536 |
"""

        def execute(command):
            if command.endswith(" info"):
                return 0, warning_summary, ""
            return 0, BASIC_INFO_OUTPUT, ""

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["2"]), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch.object(Huawei, "check_npu_isolation",
                             return_value=False), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            infos = Huawei.get_basic_info()

        self.assertEqual(
            [info.pci_address for info in infos],
            ["0000:95:00.0", "0000:97:00.0"])
        self.assertNotIn("chipId", infos[0].extra)
        self.assertNotIn("physicalId", infos[0].extra)
        self.assertEqual(infos[1].extra["physicalId"], "5")

    def test_partial_summary_still_groups_both_pci_dependencies(self):
        first = type("PciDeviceTO", (), {})()
        first.pciDeviceAddress = "0000:95:00.0"
        first.dependentDevices = []
        second = type("PciDeviceTO", (), {})()
        second.pciDeviceAddress = "0000:97:00.0"
        second.dependentDevices = []
        gpu_info_map = {
            first.pciDeviceAddress: {"npuId": "2"},
            second.pciDeviceAddress: {
                "npuId": "2", "chipId": "1", "physicalId": "5"},
        }

        Huawei.enrich_pci_device_dependencies(
            [first, second], gpu_info_map)

        self.assertEqual(first.dependentDevices, [second.pciDeviceAddress])
        self.assertEqual(second.dependentDevices, [first.pciDeviceAddress])

    def test_metrics_keep_chip0_when_summary_only_contains_chip1(self):
        partial_summary = """
| 2     Ascend910           | OK            | -                    |
| 1     5                   | 0000:97:00.0  | 0 / 0  2909 / 65536 |
"""
        chip0_output = """
Serial Number : BOARD002
PCIe Bus Info : 0000:95:00.0
Aicore Usage Rate(%) : 11
"""
        chip1_output = """
PCIe Bus Info : 0000:97:00.0
Aicore Usage Rate(%) : 21
"""
        commands = []

        def execute(command):
            commands.append(command)
            if command.endswith(" info"):
                return 0, partial_summary, ""
            if command == "npu-smi info -t board -i 2":
                return 0, chip0_output, ""
            if " -c 1" in command:
                return 0, chip1_output, ""
            return 0, chip0_output, ""

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["2"]), \
                patch.object(Huawei, "get_npu_smi_cmd",
                             return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            metrics = Huawei.collect_metrics()

        self.assertEqual(
            [metric.pci_address for metric in metrics],
            ["0000:95:00.0", "0000:97:00.0"])
        metric_commands = [command for command in commands if ";" in command]
        self.assertNotIn(" -c ", metric_commands[0])
        self.assertIn(" -c 1", metric_commands[1])

    def test_metric_targets_include_warning_chip(self):
        warning_summary = """
| 3     Ascend910           | OK            | 161.1                |
| 0     6                   | 0000:91:00.0  | 0 / 0  2909 / 65536 |
| 3     Ascend910           | Warning       | -                    |
| 1     7                   | 0000:93:00.0  | 0 / 0  2870 / 65536 |
"""

        with patch.object(Huawei, "get_npu_smi_cmd",
                          return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      return_value=(0, warning_summary, "")):
            result = Huawei.get_metric_chip_ids(["3"])

        self.assertEqual(result, {"3": ["0", "1"]})

    def test_rank_table_uses_physical_ids(self):
        gpu_info_map = {
            "0000:95:00.0": {
                "npuId": "2", "chipId": "0", "physicalId": "4"},
            "0000:97:00.0": {
                "npuId": "2", "chipId": "1", "physicalId": "5"},
        }

        result = Huawei.get_rank_table_device_ids(
            gpu_info_map, sorted(gpu_info_map))

        self.assertEqual(result, ["4", "5"])

    def test_sriov_skips_complete_and_partial_dual_chip_mapping(self):
        device = type("PciDeviceTO", (), {
            "pciDeviceAddress": "0000:95:00.0"})()
        complete = {
            "0000:95:00.0": {"npuId": "2", "chipId": "0"},
            "0000:97:00.0": {"npuId": "2", "chipId": "1"},
        }
        partial = {
            "0000:95:00.0": {"npuId": "2"},
            "0000:97:00.0": {
                "npuId": "2", "chipId": "1", "physicalId": "5"},
        }

        with patch("zstacklib.gpu.vendors.huawei.os.path.exists",
                   return_value=True), \
                patch("zstacklib.gpu.vendors.huawei.open",
                      return_value=StringIO("0"), create=True):
            complete_result = Huawei.detect_sriov_capability(
                device, complete)
            partial_result = Huawei.detect_sriov_capability(device, partial)

        self.assertEqual(complete_result, (False, {}))
        self.assertEqual(partial_result, (False, {}))

    def test_sriov_uses_product_name_when_summary_is_unavailable(self):
        device = type("PciDeviceTO", (), {
            "pciDeviceAddress": "0000:95:00.0"})()
        gpu_info_map = {
            "0000:95:00.0": {
                "npuId": "2", "productName": "Atlas 900 Ascend 910C"},
        }

        with patch("zstacklib.gpu.vendors.huawei.os.path.exists",
                   return_value=True), \
                patch("zstacklib.gpu.vendors.huawei.open",
                      return_value=StringIO("0"), create=True):
            result = Huawei.detect_sriov_capability(device, gpu_info_map)

        self.assertEqual(result, (False, {}))

    def test_isolation_queries_requested_chip_with_stable_command_path(self):
        with patch.object(Huawei, "get_npu_smi_cmd",
                          return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      return_value=(
                          0, "hccs health status : OK", "")) as execute:
            result = Huawei.check_npu_isolation(
                "2", ["2"], chip_id="1")

        self.assertFalse(result)
        execute.assert_called_once_with(
            "npu-smi info -t hccs -i 2 -c 1")

    def test_topology_fallback_accepts_910c_physical_id_row(self):
        output = """\
          Phy-ID2    Phy-ID3    Phy-ID12   Phy-ID13
Phy-ID2    X          SIO        HCCS_SW    HCCS_SW
Phy-ID3    SIO        X          HCCS_SW    HCCS_SW
"""
        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(0, output, "")):
            self.assertFalse(Huawei._check_isolation_by_topo(
                "1", physical_id="2"))

    def test_topology_fallback_detects_isolated_910c_physical_id_row(self):
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

        with patch.object(Huawei, "get_npu_smi_cmd",
                          return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            self.assertTrue(Huawei.check_npu_isolation(
                "1", ["1", "6"], chip_id="0", physical_id="2"))


if __name__ == "__main__":
    unittest.main()

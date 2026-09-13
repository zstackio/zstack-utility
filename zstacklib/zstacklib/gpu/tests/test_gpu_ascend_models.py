# -*- coding: utf-8 -*-
"""Cross-model contracts; single-model fixtures remain in their own suites."""
import copy
import unittest

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from zstacklib.gpu.vendors.huawei import Huawei
from zstacklib.gpu.vendors import huawei_common
from zstacklib.gpu.tests.test_gpu_ascend_910b_vendors import (
    BOARD_OUTPUT as BOARD_910B, SUMMARY_OUTPUT as SUMMARY_910B)
from zstacklib.gpu.tests.test_gpu_ascend_910c_vendors import (
    BASIC_INFO_OUTPUT as BOARD_910C, SUMMARY_OUTPUT as SUMMARY_910C)
from zstacklib.utils import gpu

# Synthetic mixed host assembled from the independently captured row formats.
# Deliberately non-arithmetic physical IDs guard against npuId * 2 assumptions.
MIXED_SUMMARY = SUMMARY_910B + SUMMARY_910C.replace(
    "0     4 ", "0     41 ").replace("1     5 ", "1     57 ")


class TestHuaweiModelDispatch(unittest.TestCase):
    def _collect(self, summary=MIXED_SUMMARY):
        def execute(command):
            if command == "npu-smi info":
                return 0, summary, ""
            if command == Huawei.get_basic_info_cmd_for_npu("1"):
                return 0, BOARD_910B, ""
            if command == Huawei.get_basic_info_cmd_for_npu("2"):
                return 0, BOARD_910C, ""
            self.fail("unexpected command: %s" % command)

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["1", "2"]), \
                patch.object(Huawei, "get_npu_smi_cmd", return_value="npu-smi"), \
                patch.object(Huawei, "check_npu_isolation",
                             return_value=False) as isolation, \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            infos = Huawei.get_basic_info()
        return infos, isolation.call_args_list

    def test_resolve_per_npu_without_product_query(self):
        groups = huawei_common.group_npus(
            chips=huawei_common.parse_summary(MIXED_SUMMARY))
        self.assertEqual(groups["1"].handler.model, "910B")
        self.assertEqual(groups["2"].handler.model, "910C")

    def test_partial_summary_is_enough_for_910c(self):
        chips = huawei_common.parse_summary(MIXED_SUMMARY)
        groups = huawei_common.group_npus(
            chips=[chip for chip in chips
                   if chip.info.extra.get("chipId") == "1"])
        self.assertEqual(groups["2"].handler.model, "910C")
        self.assertEqual(groups["2"].handler.get_metric_targets(groups["2"]),
                         [None, "1"])

    def test_unknown_preserves_board_without_inventing_chip(self):
        boards = [{"pciAddress": "0000:8d:00.0", "npuId": "9",
                   "memory": "131072 MB", "serialNumber": "UNKNOWN"}]
        group = huawei_common.group_npus(boards)["9"]
        self.assertEqual(group.handler.model, "unknown")
        self.assertFalse(group.handler.multi_chip)
        self.assertEqual(group.handler.get_metric_targets(group), [None])
        self.assertEqual(huawei_common.merge_basic_info(boards, []), boards)

    def test_mixed_basic_info_and_isolation_targets(self):
        infos, calls = self._collect()
        self.assertEqual([info.pci_address for info in infos],
                         ["0000:c2:00.0", "0000:95:00.0", "0000:97:00.0"])
        self.assertEqual([info.memory for info in infos],
                         ["32768 MB", "65536 MB", "65536 MB"])
        self.assertEqual([info.serial_number for info in infos],
                         ["BOARD910B", "BOARD002", "BOARD002"])
        self.assertEqual(
            [(call[0][0], call[1]["chip_id"], call[1]["physical_id"])
             for call in calls],
            [("1", None, None), ("2", "0", "41"), ("2", "1", "57")])
        info_map = {info.pci_address: info.to_addon_dict() for info in infos}
        self.assertEqual(Huawei.get_rank_table_device_ids(
            info_map, list(info_map)), ["1", "41", "57"])
        for address, expected in [("0000:c2:00.0", False),
                                  ("0000:95:00.0", True),
                                  ("0000:97:00.0", True)]:
            device = type("PciDevice", (), {"pciDeviceAddress": address})()
            self.assertEqual(Huawei.is_multi_chip_npu(device, info_map),
                             expected)

    def test_legacy_and_plugin_merge_agree_on_mixed_host(self):
        infos, _ = self._collect()
        expected = []
        for info in infos:
            record = huawei_common.gpu_info_to_record(info)
            record.pop("isIsolated")
            expected.append(record)
        boards = []
        for npu_id, output in [("1", BOARD_910B), ("2", BOARD_910C)]:
            for record in gpu.parse_huawei_gpu_output_by_npu_id(output):
                record["npuId"] = npu_id
                boards.append(record)
        original = copy.deepcopy(boards)
        self.assertEqual(gpu.merge_huawei_gpu_chip_infos(boards, MIXED_SUMMARY),
                         expected)
        self.assertEqual(boards, original)

    def test_warning_board_kept_without_usable_chip_ids_on_mixed_host(self):
        summary = MIXED_SUMMARY.replace(
            "| 2     Ascend910           | OK", "| 2     Ascend910           | Warning",
            1)
        infos, _ = self._collect(summary)
        board = infos[1]
        self.assertEqual(board.pci_address, "0000:95:00.0")
        self.assertNotIn("chipId", board.extra)
        self.assertNotIn("physicalId", board.extra)
        info_map = {info.pci_address: info.to_addon_dict() for info in infos}
        self.assertEqual(Huawei.get_rank_table_device_ids(
            info_map, list(info_map)), ["1", "57"])
        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(0, summary, "")):
            self.assertEqual(Huawei.get_metric_targets(["1", "2"]),
                             {"1": [None], "2": ["0", "1"]})

    def test_mixed_metrics_use_model_specific_commands(self):
        commands = []
        def execute(command):
            commands.append(command)
            if command == "npu-smi info":
                return 0, MIXED_SUMMARY, ""
            if command == "npu-smi info -t board -i 2":
                return 0, BOARD_910C, ""
            expected = {
                Huawei.get_metric_cmd_for_npu("1"): BOARD_910B,
                Huawei.get_metric_cmd_for_npu("2", "0"):
                    "PCIe Bus Info : 0000:95:00.0",
                Huawei.get_metric_cmd_for_npu("2", "1"):
                    "PCIe Bus Info : 0000:97:00.0",
            }
            if command not in expected:
                self.fail("unexpected command: %s" % command)
            return 0, expected[command], ""

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["1", "2"]), \
                patch.object(Huawei, "get_npu_smi_cmd", return_value="npu-smi"), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe",
                      side_effect=execute):
            metrics = Huawei.collect_metrics()
        self.assertEqual([metric.pci_address for metric in metrics],
                         ["0000:c2:00.0", "0000:95:00.0", "0000:97:00.0"])
        self.assertEqual([metric.serial_number for metric in metrics],
                         ["BOARD910B", "BOARD002", "BOARD002"])
        self.assertEqual(commands.count("npu-smi info"), 1)
        self.assertEqual(len(commands), 5)

    def test_collection_does_not_cache_model_across_snapshots(self):
        with patch("zstacklib.gpu.vendors.huawei.bash_roe", side_effect=[
                (0, MIXED_SUMMARY, ""), (1, "", "summary unavailable")]):
            self.assertEqual(Huawei.get_metric_targets(["1", "2"]),
                             {"1": [None], "2": ["0", "1"]})
            self.assertEqual(Huawei.get_metric_targets(["1", "2"]),
                             {"1": [None], "2": [None]})

    def test_legacy_merge_matches_pci_when_board_has_no_npu_id(self):
        boards = [{"pciAddress": "0000:C2:00.0", "serialNumber": "BOARD"}]
        records = gpu.merge_huawei_gpu_chip_infos(boards, SUMMARY_910B)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["npuId"], "1")
        self.assertEqual(records[0]["serialNumber"], "BOARD")
        self.assertEqual(records[0]["memory"], "32768 MB")

    def test_rank_table_filters_invalid_npu_and_unselected_devices(self):
        infos = {"a": {"npuId": "1"},
                 "b": {"npuId": "2", "physicalId": "41"},
                 "c": {"npuId": "2", "physicalId": "57"},
                 "d": {"physicalId": "99"},
                 "e": {"npuId": "bad", "physicalId": "100"}}
        self.assertEqual(Huawei.get_rank_table_device_ids(
            infos, ["a", "c", "d", "e", "missing"]), ["1", "57"])
        # Preserve the public fallback when only a board record is selected.
        self.assertEqual(Huawei.get_rank_table_device_ids(
            {"board": {"npuId": "2"}}, ["board"]), ["2"])

    def test_topology_fallback_agrees_for_plugin_and_legacy(self):
        for npu_id, physical_id, output, isolated in [
                ("1", None, "NPU1 X HCCS SYS", False),
                ("1", None, "NPU1 X SYS PHB", True),
                ("2", "41", "Phy-ID41 X SIO HCCS_SW", False),
                ("2", "41", "Phy-ID41 X SIO SYS", True),
                ("2", "41", "Phy-ID410 X SYS PHB", False),
                ("2", "41", "Phy-ID41 Phy-ID57\ninvalid output", False),
                ("2", None, "Phy-ID4 X SYS PHB", False)]:
            with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                       return_value=(0, output, "")), \
                    patch("zstacklib.utils.gpu.bash_roe",
                          return_value=(0, output, "")):
                self.assertEqual(Huawei._check_isolation_by_topo(
                    npu_id, physical_id), isolated)
                self.assertEqual(gpu._check_npu_isolation_by_topo(
                    npu_id, physical_id=physical_id), isolated)

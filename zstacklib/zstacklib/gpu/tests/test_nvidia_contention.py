#!/usr/bin/env python
# -*- coding: utf-8 -*-

import unittest

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from zstacklib.gpu.vendors.nvidia import NVIDIA
from zstacklib.gpu.operation_gate import gpu_operation_gate


def _metric_output(count=8):
    return "\n".join(
        "00000000:%02X:00.0, %d, %d, %d, %.2f, %d, SN%02d" % (
            0x1a + index, 10 + index, 20 + index, 40 + index,
            60.0 + index, index, index)
        for index in range(count)
    )


def _basic_output(count=8):
    return "\n".join(
        "00000000:%02X:00.0, 24576 MiB, 350.00 W, SN%02d, 580.142" % (
            0x1a + index, index)
        for index in range(count)
    )


def _pcie_output(count=8):
    return "\n".join(
        "GPU %d: NVIDIA GeForce RTX 3090\n    TX_BYTES: %d\n    RX_BYTES: %d" % (
            index, 1024 + index, 2048 + index)
        for index in range(count)
    )


def _lspci_outputs(count=8):
    id_output = "\n\n".join(
        "Slot:\t0000:%02x:00.0\n"
        "Class:\t030200\n"
        "Vendor:\t10de\n"
        "Device:\t2204" % (0x1a + index)
        for index in range(count)
    )
    name_output = "\n\n".join(
        "Slot:\t0000:%02x:00.0\n"
        "Class:\t3D controller\n"
        "Vendor:\tNVIDIA Corporation\n"
        "Device:\tNVIDIA GPU" % (0x1a + index)
        for index in range(count)
    )
    return id_output, name_output


def _worker(pid=123):
    return type('Worker', (), {
        'device_uuid': 'device-uuid',
        'vm_uuid': 'vm-uuid',
        'pci_address': '0000:1a:00.0',
        'pid': pid,
        'container_id': None,
        'restarting': False,
        'allocated_memory_mb': 1024,
    })()


class TestNVIDIAContention(unittest.TestCase):

    def setUp(self):
        self._reset_metrics_cache()

    def tearDown(self):
        self._reset_metrics_cache()

    @staticmethod
    def _reset_metrics_cache():
        NVIDIA._metrics_cache = []
        NVIDIA._metrics_cache_time = 0
        NVIDIA._pcie_metrics_cache = {}
        NVIDIA._pcie_last_attempt = {}
        NVIDIA._pcie_blocked_until = {}
        NVIDIA._basic_info_cache = []
        NVIDIA._basic_info_cache_time = 0

    def test_parse_metrics_is_pure_for_eight_gpus(self):
        with patch("zstacklib.gpu.vendors.nvidia.bash_roe") as bash_roe:
            metrics = NVIDIA.parse_metrics(_metric_output())

        self.assertEqual(len(metrics), 8)
        self.assertEqual(metrics[0].pci_address, "0000:1a:00.0")
        self.assertEqual(metrics[-1].pci_address, "0000:21:00.0")
        self.assertIsNone(metrics[0].pcie_tx_bytes)
        self.assertIsNone(metrics[0].pcie_rx_bytes)
        self.assertEqual(metrics[0]._nvidia_index, "0")
        bash_roe.assert_not_called()

    def test_collect_vgpu_metrics_skips_nvidia_smi_without_active_mdev(self):
        with patch.object(NVIDIA, "_has_active_mdev_devices", return_value=False), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe") as bash_roe:
            metrics = NVIDIA.collect_vgpu_metrics()

        self.assertEqual(metrics, [])
        bash_roe.assert_not_called()

    def test_basic_info_carries_driver_version_for_all_gpus(self):
        infos = NVIDIA.parse_basic_info(_basic_output())

        self.assertEqual(len(infos), 8)
        self.assertTrue(all(info.extra.get("driverVersion") == "580.142"
                            for info in infos))

    def test_basic_info_accepts_inventory_shrink_after_driver_rebind(self):
        now = [1000]
        outputs = [(0, _basic_output(), ""),
                   (0, _basic_output(7), "")]

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.exists",
                      return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.islink",
                      return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.realpath",
                      return_value="/sys/bus/pci/drivers/vfio-pci"), \
                patch("zstacklib.gpu.vendors.nvidia.time.time",
                      side_effect=lambda: now[0]), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                      side_effect=outputs) as bash_roe:
            first = NVIDIA.get_basic_info()
            now[0] = 1031
            second = NVIDIA.get_basic_info()

        self.assertEqual(len(first), 8)
        self.assertEqual(len(second), 7)
        self.assertNotIn("0000:21:00.0",
                         [info.pci_address for info in second])
        self.assertEqual(bash_roe.call_count, 2)
        self.assertTrue(all(call[0][0].startswith("timeout 12 nvidia-smi")
                            for call in bash_roe.call_args_list))

    def test_basic_info_retries_single_partial_inventory(self):
        now = [1000]
        outputs = [(0, _basic_output(), ""),
                   (0, _basic_output(7), ""),
                   (0, _basic_output(), "")]

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch.object(NVIDIA, "_is_nvidia_driver_bound",
                             return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.time.time",
                      side_effect=lambda: now[0]), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                      side_effect=outputs) as bash_roe:
            NVIDIA.get_basic_info()
            now[0] = 1031
            refreshed = NVIDIA.get_basic_info()

        self.assertEqual(len(refreshed), 8)
        self.assertIn("0000:21:00.0",
                      [info.pci_address for info in refreshed])
        self.assertEqual(bash_roe.call_count, 3)

    def test_basic_info_keeps_repeated_partial_when_gpu_still_uses_nvidia(self):
        now = [1000]
        outputs = [(0, _basic_output(), ""),
                   (0, _basic_output(7), ""),
                   (0, _basic_output(7), "")]

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.exists",
                      return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.islink",
                      return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.realpath",
                      return_value="/sys/bus/pci/drivers/nvidia"), \
                patch("zstacklib.gpu.vendors.nvidia.time.time",
                      side_effect=lambda: now[0]), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                      side_effect=outputs) as bash_roe:
            NVIDIA.get_basic_info()
            now[0] = 1031
            refreshed = NVIDIA.get_basic_info()

        self.assertEqual(len(refreshed), 8)
        self.assertIn("0000:21:00.0",
                      [info.pci_address for info in refreshed])
        self.assertEqual(bash_roe.call_count, 3)

    def test_pci_fallback_marks_gpu_missing_from_stable_inventory_unloaded(self):
        from zstacklib.utils.gpu import get_all_gpu_infos_by_pci

        id_output, name_output = _lspci_outputs()
        NVIDIA._basic_info_cache = NVIDIA.parse_basic_info(_basic_output(7))
        NVIDIA._basic_info_cache_time = 1000

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.time.time",
                      return_value=1000), \
                patch("zstacklib.gpu.get_all_gpu_vendors",
                      return_value=[NVIDIA]), \
                patch("zstacklib.utils.pci.get_pci_device_ids",
                      return_value=(0, id_output, "")), \
                patch("zstacklib.utils.pci.get_pci_device_names",
                      return_value=(0, name_output, "")):
            gpu_info_map = get_all_gpu_infos_by_pci()

        self.assertEqual(len(gpu_info_map), 8)
        self.assertFalse(gpu_info_map["0000:21:00.0"]["isDriverLoaded"])
        self.assertNotIn("driverVersion", gpu_info_map["0000:21:00.0"])

    def test_metrics_cache_batches_all_pcie_values_in_one_query(self):
        commands = []

        def run_command(command):
            commands.append(command)
            if "--query-gpu" in command:
                return 0, _metric_output(), ""
            return 0, _pcie_output(), ""

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.time.time", return_value=1000), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe", side_effect=run_command):
            results = [NVIDIA.collect_metrics() for _ in range(9)]

        base_queries = [command for command in commands if "--query-gpu" in command]
        pcie_queries = [command for command in commands if " pci " in command]
        self.assertEqual(len(base_queries), 1)
        self.assertEqual(len(pcie_queries), 1)
        self.assertTrue(all(len(metrics) == 8 for metrics in results))
        self.assertEqual(pcie_queries[0], "timeout 10 nvidia-smi pci -gCnt")
        self.assertEqual(results[-1][0].pcie_tx_bytes, 1024.0)
        self.assertEqual(results[-1][-1].pcie_rx_bytes, 2055.0)

    def test_metrics_cache_keeps_last_good_data_after_refresh_failure(self):
        now = [1000]

        def run_command(command):
            if " pci " in command:
                return 1, "", "PCI query failed"
            if now[0] == 1000:
                return 0, _metric_output(1), ""
            return 1, "", "NVML busy"

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.time.time", side_effect=lambda: now[0]), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe", side_effect=run_command):
            first = NVIDIA.collect_metrics()
            now[0] = 1031
            second = NVIDIA.collect_metrics()

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].pci_address, "0000:1a:00.0")

    def test_metrics_cache_accepts_inventory_shrink_after_driver_unbind(self):
        now = [1000]
        outputs = [(0, _metric_output(), ""),
                   (0, _metric_output(7), "")]

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch.object(NVIDIA, "_is_nvidia_driver_bound",
                             return_value=False), \
                patch.object(NVIDIA, "_collect_pcie_metrics"), \
                patch("zstacklib.gpu.vendors.nvidia.time.time",
                      side_effect=lambda: now[0]), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                      side_effect=outputs) as bash_roe:
            first = NVIDIA.collect_metrics()
            now[0] = 1031
            second = NVIDIA.collect_metrics()

        self.assertEqual(len(first), 8)
        self.assertEqual(len(second), 7)
        self.assertNotIn("0000:21:00.0",
                         [metric.pci_address for metric in second])
        self.assertEqual(NVIDIA._metrics_cache_time, 1031)
        self.assertEqual(bash_roe.call_count, 2)

    def test_pcie_failure_opens_per_device_circuit_breaker(self):
        commands = []
        now = [1000]

        def run_command(command):
            commands.append(command)
            if "--query-gpu" in command:
                return 0, _metric_output(1), ""
            return 1, "", "NVML busy"

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.time.time", side_effect=lambda: now[0]), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe", side_effect=run_command):
            NVIDIA.collect_metrics()
            now[0] = 1061
            NVIDIA.collect_metrics()

        pcie_queries = [command for command in commands if " pci " in command]
        self.assertEqual(len(pcie_queries), 1)
        self.assertGreater(NVIDIA._pcie_blocked_until["_all"], now[0])

    def test_monitoring_returns_cache_without_shell_when_critical_is_active(self):
        NVIDIA._metrics_cache = NVIDIA.parse_metrics(_metric_output(1))
        NVIDIA._metrics_cache_time = 1000

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.time.time", return_value=1031), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe") as bash_roe, \
                gpu_operation_gate.critical():
            metrics = NVIDIA.collect_metrics()

        self.assertEqual(len(metrics), 1)
        bash_roe.assert_not_called()

    def test_pcie_skip_does_not_delay_next_attempt(self):
        metrics = NVIDIA.parse_metrics(_metric_output(1))

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe") as bash_roe, \
                gpu_operation_gate.critical():
            NVIDIA._collect_pcie_metrics(metrics, 1000)

        self.assertNotIn("_all", NVIDIA._pcie_last_attempt)
        bash_roe.assert_not_called()

    def test_dgpu_metrics_are_unavailable_while_critical_is_active(self):
        with patch("zstacklib.gpu.vendors.nvidia.bash_roe") as bash_roe, \
                gpu_operation_gate.critical():
            metrics = NVIDIA.collect_dgpu_worker_metrics([_worker()])

        self.assertEqual(metrics, [])
        bash_roe.assert_not_called()

    def test_dgpu_metrics_are_unavailable_after_pmon_failure(self):
        with patch.object(
                NVIDIA, "_run_monitoring_command",
                return_value=(1, "", "NVML busy")):
            metrics = NVIDIA.collect_dgpu_worker_metrics([_worker()])

        self.assertEqual(metrics, [])

    def test_dgpu_metrics_keep_zero_for_pid_missing_from_successful_pmon(self):
        with patch.object(NVIDIA, "_parse_pmon_output", return_value={}):
            metrics = NVIDIA.collect_dgpu_worker_metrics([_worker()])

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].utilization, 0.0)
        self.assertEqual(metrics[0].memory_utilization, 0.0)

    def test_query_gpu_details_owns_reentrant_critical_gate(self):
        output = "0, 00000000:1A:00.0, NVIDIA GeForce RTX 3090, 24576, 580.142"
        monitoring_states = []

        def run_command(command):
            with gpu_operation_gate.monitoring() as acquired:
                monitoring_states.append(acquired)
            return 0, output, ""

        with patch.object(NVIDIA, "is_available", return_value=True), \
                patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                      side_effect=run_command) as bash_roe:
            direct = NVIDIA.query_gpu_details()
            with gpu_operation_gate.critical():
                nested = NVIDIA.query_gpu_details()

        self.assertEqual([False, False], monitoring_states)
        self.assertEqual(direct, nested)
        self.assertIn("0000:1a:00.0", direct)
        self.assertEqual(2, bash_roe.call_count)
        self.assertTrue(all(
            call[0][0].startswith(
                "timeout 12 nvidia-smi --query-gpu=index")
            for call in bash_roe.call_args_list))
        with gpu_operation_gate.monitoring() as acquired:
            self.assertTrue(acquired)

    def test_prepared_context_reuses_tensorfusion_prerequisites_for_eight_gpus(self):
        gpu_info_map = {}
        for index in range(8):
            address = "0000:%02x:00.0" % (0x1a + index)
            gpu_info_map[address] = {
                '_vendor': 'NVIDIA',
                '_deviceId': '2204',
                'driverVersion': '580.142',
            }
        prepared = NVIDIA.prepare_capability_context(gpu_info_map)
        commands = []

        def run_command(command):
            commands.append(command)
            return 0, '', ''

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe", side_effect=run_command), \
                patch.object(NVIDIA, "_is_bound_to_vfio", return_value=False), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.exists", return_value=False):
            for address in gpu_info_map:
                pci_device = type('PciDeviceTO', (), {
                    'pciDeviceAddress': address,
                })()
                supported, info = NVIDIA.detect_tensorfusion_capability(
                    pci_device, prepared)
                self.assertTrue(supported)
                self.assertEqual(info.get('driverVersion'), '580.142')

        self.assertEqual(commands, [
            'which docker',
            'which nvidia-ctk',
            'docker image inspect tf-worker:latest',
        ])
        self.assertFalse(any('nvidia-smi' in command for command in commands))

    def test_vgpu_probe_reuses_static_result_without_sysfs_capability_signal(self):
        gpu_info_map = {}
        for index in range(8):
            address = "0000:%02x:00.0" % (0x1a + index)
            gpu_info_map[address] = {
                '_vendor': 'NVIDIA',
                '_deviceId': '2204',
                'driverVersion': '580.142',
            }
        prepared = NVIDIA.prepare_capability_context(gpu_info_map)

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                   return_value=(0, "No supported devices", "")) as bash_roe, \
                patch.object(NVIDIA, "_is_bound_to_vfio", return_value=False), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.isdir", return_value=False), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.exists", return_value=False):
            for address in gpu_info_map:
                pci_device = type('PciDeviceTO', (), {
                    'pciDeviceAddress': address,
                })()
                supported, info = NVIDIA.detect_vfio_mdev_capability(
                    pci_device, prepared)
                self.assertFalse(supported)
                self.assertEqual(info, {})

        bash_roe.assert_called_once_with(
            "timeout 10 nvidia-smi vgpu -i 0000:1a:00.0 -s")

    def test_vgpu_probe_bounds_transient_family_failures(self):
        gpu_info_map = {}
        for index in range(8):
            address = "0000:%02x:00.0" % (0x1a + index)
            gpu_info_map[address] = {
                '_deviceId': '2204',
                'driverVersion': '580.142',
            }
        prepared = NVIDIA.prepare_capability_context(gpu_info_map)

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                   return_value=(124, "", "timed out")) as bash_roe, \
                patch.object(NVIDIA, "_is_bound_to_vfio", return_value=False), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.isdir", return_value=False), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.exists", return_value=False):
            for address in gpu_info_map:
                pci_device = type('PciDeviceTO', (), {
                    'pciDeviceAddress': address,
                })()
                self.assertFalse(NVIDIA.detect_vfio_mdev_capability(
                    pci_device, prepared)[0])

        self.assertEqual(bash_roe.call_count, 3)
        self.assertEqual(prepared['vgpu_families'], {})

    def test_vgpu_probe_recovers_after_two_transient_family_failures(self):
        addresses = ["0000:%02x:00.0" % (0x1a + index)
                     for index in range(4)]
        gpu_info_map = dict((address, {
            '_deviceId': '26b9',
            'driverVersion': '580.142',
        }) for address in addresses)
        prepared = NVIDIA.prepare_capability_context(gpu_info_map)
        output = ("GPU 00000000:1C:00.0\n"
                  "vGPU Type ID : 239\n"
                  "Name : GRID L20-4Q\n")
        probe_results = [(124, "", "timed out"),
                         (124, "", "timed out"),
                         (0, output, "")]

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                   side_effect=probe_results) as bash_roe, \
                patch.object(NVIDIA, "_is_bound_to_vfio", return_value=False), \
                patch.object(NVIDIA, "_has_mdev_for_pci_address",
                             return_value=False), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.isdir",
                      return_value=True):
            results = []
            for address in addresses:
                pci_device = type('PciDeviceTO', (), {
                    'pciDeviceAddress': address,
                })()
                results.append(NVIDIA.detect_vfio_mdev_capability(
                    pci_device, prepared))

        self.assertEqual([supported for supported, _ in results],
                         [False, False, True, True])
        self.assertEqual(bash_roe.call_count, 3)
        self.assertTrue(list(prepared['vgpu_families'].values())[0]
                        ['supported'])

    def test_vgpu_probe_caches_only_static_supported_types_per_family(self):
        addresses = ["0000:1a:00.0", "0000:1b:00.0"]
        gpu_info_map = dict((address, {
            '_deviceId': '26b9',
            'driverVersion': '580.142',
        }) for address in addresses)
        prepared = NVIDIA.prepare_capability_context(gpu_info_map)
        output = ("GPU 00000000:1A:00.0\n"
                  "vGPU Type ID : 239\n"
                  "Name : GRID L20-4Q\n")

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                   return_value=(0, output, "")) as bash_roe, \
                patch.object(NVIDIA, "_is_bound_to_vfio", return_value=False), \
                patch.object(NVIDIA, "_has_mdev_for_pci_address", return_value=False), \
                patch("zstacklib.gpu.vendors.nvidia.os.path.isdir", return_value=True):
            results = []
            for address in addresses:
                pci_device = type('PciDeviceTO', (), {
                    'pciDeviceAddress': address,
                })()
                results.append(NVIDIA.detect_vfio_mdev_capability(
                    pci_device, prepared))

        self.assertTrue(all(supported for supported, _ in results))
        self.assertTrue(all(info['mdevSpecifications'][0]['TypeId'] == '239'
                            for _, info in results))
        bash_roe.assert_called_once_with(
            "timeout 10 nvidia-smi vgpu -i 0000:1a:00.0 -s")


if __name__ == "__main__":
    unittest.main()

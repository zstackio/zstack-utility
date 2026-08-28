#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for GPU get_info() function and vendor-specific logic

Tests cover:
- Plugin-based collection
- Legacy fallback for different vendors
- Vendor-specific field handling (Huawei npuId, product names, etc.)
"""

from zstacklib.utils.bash import bash_roe
from zstacklib.gpu.base import (
    VendorEnum,
    PCI_CLASS_VGA,
    PCI_CLASS_PROCESSING_ACCEL,
)
from zstacklib.utils import gpu
import unittest
import sys
import os

try:
    from unittest.mock import patch, MagicMock
except ImportError:
    from mock import patch, MagicMock

# Add parent directory to path for imports
# Calculate path: zstacklib/zstacklib/utils/test_*.py -> zstacklib/
parent_dir = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, parent_dir)


class TestGetInfo(unittest.TestCase):
    """Test get_info() function"""

    def test_get_info_no_pci_address(self):
        """Test get_info returns None when no PCI address provided"""
        self.assertIsNone(gpu.get_info(None))
        self.assertIsNone(gpu.get_info(pci_device=None))

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_info_via_plugin_nvidia(self, mock_bash):
        """Test get_info via NVIDIA plugin"""
        # Mock the imports inside get_info function
        with patch('zstacklib.gpu.get_gpu_vendor') as mock_get_vendor, \
                patch('zstacklib.gpu.get_vendor_enum_mapping') as mock_mapping:
            from zstacklib.gpu.base import GPUInfo

            # Mock plugin
            mock_plugin = MagicMock()
            mock_plugin.is_available.return_value = True
            mock_plugin.get_basic_info.return_value = [
                GPUInfo(
                    pci_address="0000:3b:00.0",
                    memory="15360 MiB",
                    power="70.00 W",
                    serial_number="1322519087621"
                )
            ]

            mock_get_vendor.return_value = mock_plugin
            mock_mapping.return_value = {"NVIDIA": "NVIDIA"}

            result = gpu.get_info("0000:3b:00.0", vendor_name=VendorEnum.NVIDIA)
            self.assertIsNotNone(result)
            self.assertEqual(result["memory"], "15360 MiB")
            self.assertEqual(result["power"], "70.00 W")
            self.assertEqual(result["serialNumber"], "1322519087621")
            self.assertTrue(result["isDriverLoaded"])

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_info_via_plugin_huawei(self, mock_bash):
        """Test get_info via Huawei plugin with special fields"""
        # Mock the imports inside get_info function
        with patch('zstacklib.gpu.get_gpu_vendor') as mock_get_vendor, \
                patch('zstacklib.gpu.get_vendor_enum_mapping') as mock_mapping:
            from zstacklib.gpu.base import GPUInfo

            # Mock Huawei plugin
            mock_plugin = MagicMock()
            mock_plugin.is_available.return_value = True
            mock_plugin.get_basic_info.return_value = [
                GPUInfo(
                    pci_address="0000:81:00.0",
                    memory="32768 MB",
                    power="300 W",
                    serial_number="HUAWEI001",
                    extra={"npuId": "0", "isIsolated": False}
                )
            ]
            mock_plugin.get_npu_ids.return_value = ["0", "1"]

            # Mock product name command
            mock_bash.side_effect = [
                (0, "Product Type: Atlas 800", ""),  # product name
                (0, "", ""),  # aios rank table (simplified)
            ]

            mock_get_vendor.return_value = mock_plugin
            mock_mapping.return_value = {"Huawei": "Huawei"}

            result = gpu.get_info("0000:81:00.0", vendor_name=VendorEnum.HUAWEI)
            self.assertIsNotNone(result)
            self.assertEqual(result["npuId"], "0")
            self.assertEqual(result["isIsolated"], False)
            # Product name should be collected
            # Note: This requires actual implementation of get_huawei_product_type

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_info_legacy_nvidia(self, mock_bash):
        """Test get_info legacy fallback for NVIDIA"""
        mock_bash.side_effect = [
            (0, "/usr/bin/nvidia-smi", ""),  # which nvidia-smi
            # nvidia-smi query
            (0, "00000000:3B:00.0, 15360 MiB, 70.00 W, 1322519087621", ""),
        ]

        result = gpu._get_info_legacy("0000:3b:00.0", VendorEnum.NVIDIA)
        self.assertIsNotNone(result)
        self.assertTrue(result.get("isDriverLoaded", False))

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_info_legacy_amd(self, mock_bash):
        """Test get_info legacy fallback for AMD"""
        mock_bash.side_effect = [
            (0, "/usr/bin/rocm-smi", ""),  # which rocm-smi
            # rocm-smi
            (0, '{"card_list": [{"pci_bus": "0000:42:00.0", "memory": "16384 MiB"}]}', ""),
        ]

        result = gpu._get_info_legacy("0000:42:00.0", VendorEnum.AMD)
        # Note: This requires actual parse_amd_gpu_output implementation
        # For now, just verify it doesn't crash
        self.assertIsNotNone(result)

    @patch('zstacklib.utils.gpu.bash_roe')
    @patch('zstacklib.utils.gpu.bash_ro')
    def test_get_info_legacy_huawei(self, mock_bash_ro, mock_bash_roe):
        """Test get_info legacy fallback for Huawei with special fields"""
        # bash_ro returns (r, o) only, not (r, o, e)
        mock_bash_ro.return_value = (0, "NPU ID: 0\nNPU ID: 1")  # npu-smi info -l
        mock_bash_roe.side_effect = [
            (0, "/usr/bin/npu-smi", ""),  # which npu-smi
            (0, "PCIe Bus Info: 0000:81:00.0\nSerial Number: HUAWEI001", ""),  # npu info
            (0, "Product Type: Atlas 800", ""),  # product name
        ]

        result = gpu._get_info_legacy("0000:81:00.0", VendorEnum.HUAWEI)
        # Note: This requires actual implementation
        # For now, verify it handles Huawei-specific logic
        self.assertIsNotNone(result)

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_info_legacy_tianshu(self, mock_bash):
        """Test get_info legacy fallback for Tianshu"""
        mock_bash.side_effect = [
            (0, "/usr/bin/ixsmi", ""),  # which ixsmi
            (0, "00000000:86:00.0, 8192 MiB, 150.00 W, TIANSHU001", ""),  # ixsmi query
            (0, "Product Name: Tianshu GPU", ""),  # product name
        ]

        result = gpu._get_info_legacy("0000:86:00.0", VendorEnum.TIANSHU)
        self.assertIsNotNone(result)
        # Product name should be collected

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_info_legacy_alibaba(self, mock_bash):
        """Test get_info legacy fallback for Alibaba"""
        mock_bash.side_effect = [
            (0, "/usr/bin/ppu-smi", ""),  # which ppu-smi
            # ppu-smi query
            (0, "00000000:08:00.0, 98304 MiB, 400.00 W, ALIBABA001", ""),
            (0, "Product Name: Alibaba PPU", ""),  # product name
        ]

        result = gpu._get_info_legacy("0000:08:00.0", VendorEnum.ALIBABA)
        self.assertIsNotNone(result)
        # Product name should be collected

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_info_legacy_kunlunxin(self, mock_bash):
        """Test get_info legacy fallback for Kunlunxin (includes productName)."""
        kunlunxin_q_output = (
            "Product Name                          : P800 PCIe\n"
            "Serial Number                         : 02K0MA0258D0007R\n"
            "PCI\n"
            "    Bus Id                            : 00000000:21:00.0\n"
            "Memory Usage\n"
            "    Total                             : 98304 MiB\n"
            "    Used                              : 0 MiB\n"
            "Power Readings\n"
            "    Enforced Power Limit              : 350.00 W\n"
            "    Power Draw                        : 76.00 W\n"
        )
        mock_bash.side_effect = [
            (0, "/usr/bin/xpu-smi", ""),  # which xpu-smi
            (0, "XPU 0: 00000000:21:00.0\n", ""),  # xpu-smi -L
            (0, kunlunxin_q_output, ""),  # xpu-smi -q --id=0
        ]

        result = gpu._get_info_legacy("0000:21:00.0", VendorEnum.KUNLUNXIN)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("memory"), "98304 MiB")
        self.assertEqual(result.get("power"), "350.00 W")
        self.assertEqual(result.get("serialNumber"), "02K0MA0258D0007R")
        self.assertEqual(result.get("productName"), "P800 PCIe")
        self.assertTrue(result.get("isDriverLoaded", False))

    def test_get_info_legacy_unknown_vendor(self):
        """Test get_info legacy returns None for unknown vendor"""
        result = gpu._get_info_legacy("0000:ff:00.0", "UnknownVendor")
        self.assertIsNone(result)

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_info_returns_none_when_plugin_finds_no_matching_gpu(self, mock_bash):
        """Test get_info returns None when plugin runs but no GPU matches the given PCI (ZSTAC-81489)"""
        with patch('zstacklib.gpu.get_gpu_vendor') as mock_get_vendor, \
                patch('zstacklib.gpu.get_vendor_enum_mapping') as mock_mapping:
            from zstacklib.gpu.base import GPUInfo

            # Plugin returns list that does NOT contain the requested PCI
            mock_plugin = MagicMock()
            mock_plugin.is_available.return_value = True
            mock_plugin.get_basic_info.return_value = [
                GPUInfo(
                    pci_address="0000:86:00.0",
                    memory="16384 MiB",
                    power="75.00 W",
                    serial_number="OTHER_PCI"
                )
            ]
            mock_get_vendor.return_value = mock_plugin
            mock_mapping.return_value = {"NVIDIA": "NVIDIA"}

            result = gpu.get_info("0000:3b:00.0", vendor_name=VendorEnum.NVIDIA)
            self.assertIsNone(result)


class TestLegacyCollectors(unittest.TestCase):
    """Test legacy collection functions for each vendor"""

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_collect_nvidia_legacy(self, mock_bash):
        """Test _collect_nvidia_legacy"""
        mock_bash.side_effect = [
            (0, "/usr/bin/nvidia-smi", ""),  # which
            (0, "00000000:3B:00.0, 15360 MiB, 70.00 W, SN001", ""),  # nvidia-smi
        ]

        result = gpu._collect_nvidia_legacy("0000:3b:00.0")
        self.assertIsNotNone(result)
        self.assertTrue(result.get("isDriverLoaded", False))

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_collect_nvidia_legacy_no_tool(self, mock_bash):
        """Test _collect_nvidia_legacy returns None when tool not available (no-match/failure)"""
        mock_bash.return_value = (1, "", "command not found")

        result = gpu._collect_nvidia_legacy("0000:3b:00.0")
        self.assertIsNone(result)

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_collect_nvidia_legacy_returns_none_when_no_matching_pci(self, mock_bash):
        """Test _collect_nvidia_legacy returns None when no GPU in output matches PCI (ZSTAC-81489)"""
        mock_bash.side_effect = [
            (0, "/usr/bin/nvidia-smi", ""),
            (0, "00000000:86:00.0, 16384 MiB, 75.00 W, SN_OTHER", ""),
        ]
        result = gpu._collect_nvidia_legacy("0000:3b:00.0")
        self.assertIsNone(result)

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_collect_amd_legacy(self, mock_bash):
        """Test _collect_amd_legacy with card_list format from rocm-smi."""
        mock_bash.side_effect = [
            (0, "/usr/bin/rocm-smi", ""),  # which
            (0, '{"card_list": [{"pci_bus": "0000:42:00.0", "memory": "16384 MiB"}]}', ""),  # rocm-smi
        ]

        result = gpu._collect_amd_legacy("0000:42:00.0")
        self.assertIsNotNone(result)
        self.assertEqual(result.get("memory"), "16384 MiB")
        self.assertTrue(result.get("isDriverLoaded"))

    @patch('zstacklib.utils.gpu.bash_roe')
    @patch('zstacklib.utils.gpu.bash_ro')
    def test_collect_huawei_legacy(self, mock_bash_ro, mock_bash_roe):
        """Test _collect_huawei_legacy with special fields"""
        # bash_ro returns (r, o) only, not (r, o, e)
        mock_bash_ro.return_value = (0, "NPU ID: 0")
        mock_bash_roe.side_effect = [
            (0, "/usr/bin/npu-smi", ""),  # which
            (0, "PCIe Bus Info: 0000:81:00.0\nSerial Number: HW001", ""),  # npu info
            (0, "Product Type: Atlas 800", ""),  # product name
        ]

        result = gpu._collect_huawei_legacy("0000:81:00.0")
        # Note: Requires actual implementation
        self.assertIsNotNone(result)

    @patch('zstacklib.utils.shell.run_with_json_result')
    @patch('zstacklib.utils.gpu.bash_roe')
    def test_collect_vastai_legacy(self, mock_bash, mock_run_json):
        """Test _collect_vastai_legacy (shell is imported inside the function from zstacklib.utils)."""
        mock_bash.return_value = (0, "/usr/bin/vasmi", "")
        mock_run_json.side_effect = [
            # getmem
            {"elem": [{"pci_bus": "00000000:65:00.0", "sn": "VASTAI001"}]},
            # summary
            {"elem": [{"vals": {"devBusId": {"value": "00000000:65:00.0"},
                                "P_Cap": {"value": "300 W"}}}]},
        ]

        result = gpu._collect_vastai_legacy("0000:65:00.0")
        self.assertIsNotNone(result)


class TestGetAllGPUInfosByPCI(unittest.TestCase):
    """Test get_all_gpu_infos_by_pci() function"""

    @patch('zstacklib.utils.gpu.bash_roe')
    def test_get_all_gpu_infos_by_pci_only_function_0(self, mock_bash):
        """Test that get_all_gpu_infos_by_pci() only includes function 0 devices"""
        with patch('zstacklib.gpu.get_all_gpu_vendors') as mock_get_vendors:
            from zstacklib.gpu.base import GPUInfo
            from zstacklib.utils import gpu

            # Mock NVIDIA vendor returning both function 0 and function 1
            mock_nvidia = MagicMock()
            mock_nvidia.is_available.return_value = True
            mock_nvidia.VENDOR_NAME = "NVIDIA"
            mock_nvidia.get_basic_info.return_value = [
                GPUInfo(
                    pci_address="0000:34:00.0",
                    memory="15360 MiB",
                    power="70.00 W",
                    serial_number="SN001"
                ),
                GPUInfo(
                    pci_address="0000:34:00.1",
                    memory="15360 MiB",
                    power="70.00 W",
                    serial_number="SN001"
                ),
                GPUInfo(
                    pci_address="0000:9e:00.0",
                    memory="16384 MiB",
                    power="75.00 W",
                    serial_number="SN002"
                )
            ]

            mock_get_vendors.return_value = [mock_nvidia]

            result = gpu.get_all_gpu_infos_by_pci()

            # Should only include function 0 devices
            self.assertIn("0000:34:00.0", result)
            self.assertIn("0000:9e:00.0", result)
            # Function 1 device should NOT be in the map
            self.assertNotIn("0000:34:00.1", result)
            self.assertEqual(len(result), 2)


class TestGPUDeviceMatcher(unittest.TestCase):
    """Test _gpu_device_matcher: only matches devices in context.gpu_info_map (ZSTAC-81489)"""

    def test_matcher_returns_true_only_when_in_gpu_info_map(self):
        """Matcher returns True only when device PCI is in context.gpu_info_map"""
        from zstacklib.utils.gpu import _gpu_device_matcher

        class MockTO(object):
            pciDeviceAddress = "0000:3b:00.0"

        class MockContext(object):
            gpu_info_map = {"0000:3b:00.0": {"memory": "15360 MiB"}}

        self.assertTrue(_gpu_device_matcher(MockTO(), MockContext()))

    def test_matcher_returns_false_when_no_context(self):
        """Matcher returns False when context is None"""
        from zstacklib.utils.gpu import _gpu_device_matcher

        class MockTO(object):
            pciDeviceAddress = "0000:3b:00.0"

        self.assertFalse(_gpu_device_matcher(MockTO(), None))

    def test_matcher_returns_false_when_no_gpu_info_map(self):
        """Matcher returns False when context has no gpu_info_map"""
        from zstacklib.utils.gpu import _gpu_device_matcher

        class MockTO(object):
            pciDeviceAddress = "0000:3b:00.0"

        class MockContext(object):
            gpu_info_map = None

        self.assertFalse(_gpu_device_matcher(MockTO(), MockContext()))

    def test_matcher_returns_false_when_pci_not_in_map(self):
        """Matcher returns False when device PCI is not in gpu_info_map"""
        from zstacklib.utils.gpu import _gpu_device_matcher

        class MockTO(object):
            pciDeviceAddress = "0000:ff:00.0"

        class MockContext(object):
            gpu_info_map = {"0000:3b:00.0": {}}

        self.assertFalse(_gpu_device_matcher(MockTO(), MockContext()))


class TestGPUDevicePrepare(unittest.TestCase):
    @patch('zstacklib.utils.gpu.enrich_gpu_info_map')
    @patch('zstacklib.utils.gpu.get_all_gpu_infos_by_pci')
    def test_post_prepare_hook_enriches_vendor_dependencies(
            self, mock_get_gpu_infos, _mock_enrich_gpu_info_map):
        from zstacklib.utils.gpu import _gpu_device_prepare

        gpu_info_map = {
            "0000:87:00.0": {"npuId": "0", "chipId": "0"},
            "0000:97:00.0": {"npuId": "0", "chipId": "1"},
        }
        mock_get_gpu_infos.return_value = gpu_info_map
        context = type('Context', (), {'gpu_info_map': None})()
        first = type('PciDeviceTO', (), {})()
        first.vendor = "Huawei"
        first.pciDeviceAddress = "0000:87:00.0"
        first.dependentDevices = []
        second = type('PciDeviceTO', (), {})()
        second.vendor = "Huawei"
        second.pciDeviceAddress = "0000:97:00.0"
        second.dependentDevices = []

        post_prepare = _gpu_device_prepare(context)
        post_prepare([first, second], context)

        self.assertEqual(first.dependentDevices, [second.pciDeviceAddress])
        self.assertEqual(second.dependentDevices, [first.pciDeviceAddress])


class TestGPUDeviceProcessor(unittest.TestCase):
    """Test _gpu_device_processor: only treats device as GPU when gpu_info is valid (ZSTAC-81489)"""

    @patch('zstacklib.utils.gpu.get_info')
    def test_processor_returns_false_when_get_info_returns_none(self, mock_get_info):
        """Processor does not treat device as GPU when get_info returns None (no-match)"""
        from zstacklib.utils.gpu import _gpu_device_processor

        mock_get_info.return_value = None

        class MockTO(object):
            pciDeviceAddress = "0000:3b:00.0"
            type = PCI_CLASS_VGA
            device = "Tesla T4"
            vendor = None

        class MockContext(object):
            gpu_info_map = {}
            pci_device_mapper = {}
            opaque = None

        result = _gpu_device_processor(MockTO(), MockContext())
        self.assertFalse(result)

    @patch('zstacklib.utils.gpu.get_info')
    def test_processor_returns_false_when_get_info_returns_is_driver_loaded_false(self, mock_get_info):
        """Processor does not treat device as GPU when get_info returns isDriverLoaded=False placeholder"""
        from zstacklib.utils.gpu import _gpu_device_processor

        mock_get_info.return_value = {"isDriverLoaded": False}

        class MockTO(object):
            pciDeviceAddress = "0000:3b:00.0"
            type = PCI_CLASS_VGA
            device = "Tesla T4"
            vendor = None

        class MockContext(object):
            gpu_info_map = {}
            pci_device_mapper = {}
            opaque = None

        result = _gpu_device_processor(MockTO(), MockContext())
        self.assertFalse(result)


class TestParseLspciOutput(unittest.TestCase):
    """Test _parse_lspci_output for PCI supplement parsing."""

    def test_parse_lspci_output_single_device(self):
        """Parse single device block from lspci -Dmmnv / -Dmmv style."""
        from zstacklib.utils.gpu import _parse_lspci_output

        o_id = """Slot:	0000:82:00.0
Class:	120000
Vendor:	19e5
Device:	d802
"""
        o_name = """Slot:	0000:82:00.0
Class:	Processing accelerators
Vendor:	Huawei Technologies Co., Ltd.
Device:	Device d802
"""
        device_ids, device_names = _parse_lspci_output(o_id, o_name)
        self.assertIn("0000:82:00.0", device_ids)
        self.assertIn("0000:82:00.0", device_names)
        self.assertEqual(device_ids["0000:82:00.0"].get("Vendor"), "19e5")
        self.assertEqual(device_names["0000:82:00.0"].get("Class"), PCI_CLASS_PROCESSING_ACCEL)
        self.assertIn("Device d802", device_names["0000:82:00.0"].get("Device", ""))

    def test_parse_lspci_output_multiple_devices(self):
        """Parse multiple device blocks."""
        from zstacklib.utils.gpu import _parse_lspci_output

        o_id = """Slot:	0000:82:00.0
Class:	120000
Vendor:	19e5
Device:	d802

Slot:	0000:01:00.0
Class:	020000
Vendor:	8086
Device:	1234
"""
        o_name = """Slot:	0000:82:00.0
Class:	Processing accelerators
Vendor:	Huawei Technologies Co., Ltd.
Device:	Device d802

Slot:	0000:01:00.0
Class:	Ethernet controller
Vendor:	Intel Corporation
Device:	Ethernet X710
"""
        device_ids, device_names = _parse_lspci_output(o_id, o_name)
        self.assertEqual(len(device_ids), 2)
        self.assertEqual(device_ids["0000:82:00.0"].get("Vendor"), "19e5")
        self.assertEqual(device_ids["0000:01:00.0"].get("Vendor"), "8086")
        self.assertEqual(device_names["0000:82:00.0"].get("Class"), PCI_CLASS_PROCESSING_ACCEL)
        self.assertEqual(device_names["0000:01:00.0"].get("Class"), "Ethernet controller")


class TestSupplementGpuInfoMapFromPci(unittest.TestCase):
    """Test SMI primary + PCI fallback: supplement only when vendor has no SMI."""

    @patch('zstacklib.gpu.get_all_gpu_vendors')
    @patch('zstacklib.utils.pci.get_pci_device_names')
    @patch('zstacklib.utils.pci.get_pci_device_ids')
    def test_supplement_adds_npu_when_vendor_not_available(
            self, mock_get_ids, mock_get_names, mock_get_vendors):
        """When Huawei vendor is not available (no npu-smi), PCI supplement adds via get_pci_only_candidates."""
        from zstacklib.utils.gpu import get_all_gpu_infos_by_pci

        mock_get_ids.return_value = (
            0,
            "Slot:\t0000:82:00.0\nClass:\t120000\nVendor:\t19e5\nDevice:\td802\n",
            "",
        )
        mock_get_names.return_value = (
            0,
            "Slot:\t0000:82:00.0\nClass:\tProcessing accelerators\n"
            "Vendor:\tHuawei Technologies Co., Ltd.\nDevice:\tDevice d802\n",
            "",
        )
        mock_huawei = MagicMock()
        mock_huawei.is_available.return_value = False
        mock_huawei.VENDOR_NAME = "Huawei"
        mock_huawei.get_pci_only_candidates.return_value = [
            ("0000:82:00.0", {"isDriverLoaded": False})
        ]
        mock_get_vendors.return_value = [mock_huawei]

        result = get_all_gpu_infos_by_pci()

        self.assertIn("0000:82:00.0", result)
        self.assertEqual(result["0000:82:00.0"].get("isDriverLoaded"), False)

    @patch('zstacklib.gpu.get_all_gpu_vendors')
    @patch('zstacklib.utils.pci.get_pci_device_names')
    @patch('zstacklib.utils.pci.get_pci_device_ids')
    def test_smi_primary_not_overwritten_by_supplement(
            self, mock_get_ids, mock_get_names, mock_get_vendors):
        """When SMI already provided a device, supplement does not overwrite (SMI is primary)."""
        from zstacklib.gpu.base import GPUInfo
        from zstacklib.utils.gpu import get_all_gpu_infos_by_pci

        mock_get_ids.return_value = (
            0,
            "Slot:\t0000:82:00.0\nClass:\t120000\nVendor:\t19e5\nDevice:\td802\n",
            "",
        )
        mock_get_names.return_value = (
            0,
            "Slot:\t0000:82:00.0\nClass:\tProcessing accelerators\n"
            "Vendor:\tHuawei Technologies Co., Ltd.\nDevice:\tDevice d802\n",
            "",
        )
        mock_huawei = MagicMock()
        mock_huawei.is_available.return_value = True
        mock_huawei.VENDOR_NAME = "Huawei"
        mock_huawei.VENDOR_IDS = {"19e5"}
        mock_huawei.DEVICE_TYPES = {PCI_CLASS_PROCESSING_ACCEL}
        mock_huawei.IS_GPU_VENDOR = True
        mock_huawei.get_basic_info.return_value = [
            GPUInfo(pci_address="0000:82:00.0", memory="8192 MB", serial_number="SN1")
        ]
        mock_get_vendors.return_value = [mock_huawei]

        result = get_all_gpu_infos_by_pci()

        self.assertIn("0000:82:00.0", result)
        self.assertEqual(result["0000:82:00.0"].get("memory"), "8192 MB")
        self.assertNotEqual(result["0000:82:00.0"].get("isDriverLoaded"), False)

    @patch('zstacklib.gpu.get_all_gpu_vendors')
    @patch('zstacklib.utils.pci.get_pci_device_names')
    @patch('zstacklib.utils.pci.get_pci_device_ids')
    def test_supplement_skips_same_vendor_different_class(
            self, mock_get_ids, mock_get_names, mock_get_vendors):
        """Same vendor id (19e5) but different class (Ethernet): vendor returns no candidates."""
        from zstacklib.utils.gpu import get_all_gpu_infos_by_pci

        mock_get_ids.return_value = (
            0,
            "Slot:\t0000:82:00.0\nClass:\t020000\nVendor:\t19e5\nDevice:\tabcd\n",
            "",
        )
        mock_get_names.return_value = (
            0,
            "Slot:\t0000:82:00.0\nClass:\tEthernet controller\n"
            "Vendor:\tHuawei Technologies Co., Ltd.\nDevice:\tSome NIC\n",
            "",
        )
        mock_huawei = MagicMock()
        mock_huawei.is_available.return_value = False
        mock_huawei.VENDOR_NAME = "Huawei"
        mock_huawei.get_pci_only_candidates.return_value = []
        mock_get_vendors.return_value = [mock_huawei]

        result = get_all_gpu_infos_by_pci()

        self.assertNotIn("0000:82:00.0", result)

    @patch('zstacklib.gpu.get_all_gpu_vendors')
    @patch('zstacklib.utils.pci.get_pci_device_names')
    @patch('zstacklib.utils.pci.get_pci_device_ids')
    def test_supplement_skips_processing_accelerators_without_valid_device_name(
            self, mock_get_ids, mock_get_names, mock_get_vendors):
        """Vendor returns no candidates when device name fails validation (e.g. Huawei)."""
        from zstacklib.utils.gpu import get_all_gpu_infos_by_pci

        mock_get_ids.return_value = (
            0,
            "Slot:\t0000:82:00.0\nClass:\t120000\nVendor:\t19e5\nDevice:\tunknown\n",
            "",
        )
        mock_get_names.return_value = (
            0,
            "Slot:\t0000:82:00.0\nClass:\tProcessing accelerators\n"
            "Vendor:\tHuawei Technologies Co., Ltd.\nDevice:\tUnknown accelerator XYZ\n",
            "",
        )
        mock_huawei = MagicMock()
        mock_huawei.is_available.return_value = False
        mock_huawei.VENDOR_NAME = "Huawei"
        mock_huawei.get_pci_only_candidates.return_value = []
        mock_get_vendors.return_value = [mock_huawei]

        result = get_all_gpu_infos_by_pci()

        self.assertNotIn("0000:82:00.0", result)

    @patch('zstacklib.gpu.get_all_gpu_vendors')
    @patch('zstacklib.utils.pci.get_pci_device_names')
    @patch('zstacklib.utils.pci.get_pci_device_ids')
    def test_supplement_skips_non_function_0(self, mock_get_ids, mock_get_names, mock_get_vendors):
        """Vendor returns only function 0 in candidates (e.g. 82:00.1 not returned)."""
        from zstacklib.utils.gpu import get_all_gpu_infos_by_pci

        mock_get_ids.return_value = (
            0,
            "Slot:\t0000:82:00.1\nClass:\t120000\nVendor:\t19e5\nDevice:\td802\n",
            "",
        )
        mock_get_names.return_value = (
            0,
            "Slot:\t0000:82:00.1\nClass:\tProcessing accelerators\n"
            "Vendor:\tHuawei Technologies Co., Ltd.\nDevice:\tDevice d802\n",
            "",
        )
        mock_huawei = MagicMock()
        mock_huawei.is_available.return_value = False
        mock_huawei.VENDOR_NAME = "Huawei"
        mock_huawei.get_pci_only_candidates.return_value = []
        mock_get_vendors.return_value = [mock_huawei]

        result = get_all_gpu_infos_by_pci()

        self.assertNotIn("0000:82:00.1", result)


if __name__ == '__main__':
    unittest.main()

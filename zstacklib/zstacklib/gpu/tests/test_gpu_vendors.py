#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GPU Vendor Plugin System - Unit Tests

Run with: python -m pytest tests/test_gpu_vendors.py -v
Or simply: python tests/test_gpu_vendors.py
"""

import unittest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zstacklib.gpu.base import PCI_CLASS_PROCESSING_ACCEL


class TestGPUBase(unittest.TestCase):
    """Test base class functionality"""
    
    def test_normalize_pci_address_8char_domain(self):
        """Test PCI address normalization with 8-char domain"""
        from zstacklib.gpu.base import GPUBase
        
        result = GPUBase.normalize_pci_address("00000000:3B:00.0")
        self.assertEqual(result, "0000:3b:00.0")
    
    def test_normalize_pci_address_4char_domain(self):
        """Test PCI address normalization with 4-char domain"""
        from zstacklib.gpu.base import GPUBase
        
        result = GPUBase.normalize_pci_address("0000:3B:00.0")
        self.assertEqual(result, "0000:3b:00.0")

    def test_normalize_pci_address_with_hygon_suffix(self):
        from zstacklib.gpu.base import GPUBase

        result = GPUBase.normalize_pci_address("0000:06:00.0 --> SN: TRCW390010030401")
        self.assertEqual(result, "0000:06:00.0")
    
    def test_parse_unit_value(self):
        """Test unit value parsing"""
        from zstacklib.gpu.base import GPUBase
        
        # Test various formats
        self.assertEqual(GPUBase.parse_unit_value("15360 MiB"), 15360.0)
        self.assertEqual(GPUBase.parse_unit_value("70.00 W"), 70.0)
        self.assertEqual(GPUBase.parse_unit_value("45.5"), 45.5)
        self.assertIsNone(GPUBase.parse_unit_value(""))
        self.assertIsNone(GPUBase.parse_unit_value(None))
    
    def test_parse_unit_value_with_target_unit(self):
        """Test unit value parsing with target_unit validation"""
        from zstacklib.gpu.base import GPUBase
        
        # Test matching units
        self.assertEqual(GPUBase.parse_unit_value("15360 MiB", "MiB"), 15360.0)
        self.assertEqual(GPUBase.parse_unit_value("70.00 W", "W"), 70.0)
        self.assertEqual(GPUBase.parse_unit_value("45.5 %", "%"), 45.5)
        self.assertEqual(GPUBase.parse_unit_value("40 C", "C"), 40.0)
        
        # Test case-insensitive matching
        self.assertEqual(GPUBase.parse_unit_value("15360 mib", "MiB"), 15360.0)
        self.assertEqual(GPUBase.parse_unit_value("70.00 w", "W"), 70.0)
        
        # Test unit mismatch - should return None
        self.assertIsNone(GPUBase.parse_unit_value("15360 MiB", "W"))
        self.assertIsNone(GPUBase.parse_unit_value("70.00 W", "MiB"))
        self.assertIsNone(GPUBase.parse_unit_value("45.5", "W"))  # No unit when expected
        
        # Test without target_unit - should work as before
        self.assertEqual(GPUBase.parse_unit_value("15360 MiB"), 15360.0)
        self.assertEqual(GPUBase.parse_unit_value("70.00 W"), 70.0)


class TestGPUVendorRegistry(unittest.TestCase):
    """Test vendor registration system"""

    def test_enrich_pci_device_dependencies_dispatches_by_vendor(self):
        from zstacklib.gpu import enrich_pci_device_dependencies

        first = type('PciDeviceTO', (), {})()
        first.vendor = "Huawei"
        first.pciDeviceAddress = "0000:87:00.0"
        first.dependentDevices = []
        second = type('PciDeviceTO', (), {})()
        second.vendor = "Huawei"
        second.pciDeviceAddress = "0000:97:00.0"
        second.dependentDevices = []
        gpu_info_map = {
            first.pciDeviceAddress: {"npuId": "0", "chipId": "0"},
            second.pciDeviceAddress: {"npuId": "0", "chipId": "1"},
        }

        enrich_pci_device_dependencies([first, second], gpu_info_map)

        self.assertEqual(first.dependentDevices, [second.pciDeviceAddress])
        self.assertEqual(second.dependentDevices, [first.pciDeviceAddress])
    
    def test_nvidia_registered(self):
        """Test NVIDIA vendor is registered"""
        from zstacklib.gpu import get_gpu_vendor
        
        vendor = get_gpu_vendor("NVIDIA")
        self.assertIsNotNone(vendor)
        self.assertEqual(vendor.VENDOR_NAME, "NVIDIA")
    
    def test_amd_registered(self):
        """Test AMD vendor is registered"""
        from zstacklib.gpu import get_gpu_vendor
        
        vendor = get_gpu_vendor("AMD")
        self.assertIsNotNone(vendor)
        self.assertEqual(vendor.VENDOR_NAME, "AMD")
    
    def test_huawei_registered(self):
        """Test Huawei vendor is registered"""
        from zstacklib.gpu import get_gpu_vendor
        
        vendor = get_gpu_vendor("Huawei")
        self.assertIsNotNone(vendor)
        self.assertEqual(vendor.VENDOR_NAME, "Huawei")
    
    def test_get_all_vendors(self):
        """Test getting all registered vendors"""
        from zstacklib.gpu import get_all_gpu_vendors
        
        vendors = get_all_gpu_vendors()
        # In Python 2 values() returns a list, in Python 3 it returns a view
        self.assertTrue(len(vendors) >= 8)
        
        vendor_names = [v.VENDOR_NAME for v in vendors]
        self.assertIn("NVIDIA", vendor_names)
        self.assertIn("AMD", vendor_names)
        self.assertIn("Huawei", vendor_names)
        self.assertIn("Tianshu", vendor_names)
        self.assertIn("Vastai", vendor_names)
        self.assertIn("Enflame", vendor_names)
        self.assertIn("Haiguang", vendor_names)
        self.assertIn("Alibaba", vendor_names)

    def test_get_vendor_by_id(self):
        """Test finding vendor by PCI ID"""
        from zstacklib.gpu import get_vendor_by_id
        
        # NVIDIA
        vendor = get_vendor_by_id("10de")
        self.assertIsNotNone(vendor)
        self.assertEqual(vendor.VENDOR_NAME, "NVIDIA")
        
        # AMD
        vendor = get_vendor_by_id("1002")
        self.assertIsNotNone(vendor)
        self.assertEqual(vendor.VENDOR_NAME, "AMD")

        # Tianshu
        vendor = get_vendor_by_id("1e3e")
        self.assertIsNotNone(vendor)
        self.assertEqual(vendor.VENDOR_NAME, "Tianshu")

        # Vastai
        vendor = get_vendor_by_id("1edb")
        self.assertIsNotNone(vendor)
        self.assertEqual(vendor.VENDOR_NAME, "Vastai")

    def test_get_vendor_enum_mapping(self):
        """Test dynamic VendorEnum mapping"""
        from zstacklib.gpu import get_vendor_enum_mapping
        
        mapping = get_vendor_enum_mapping()
        self.assertIsInstance(mapping, dict)
        self.assertEqual(mapping.get("NVIDIA"), "NVIDIA")
        self.assertEqual(mapping.get("AMD"), "AMD")
        self.assertEqual(mapping.get("TianShu"), "Tianshu")
        self.assertEqual(mapping.get("Vastai"), "Vastai")


class TestNVIDIA(unittest.TestCase):
    """Test NVIDIA vendor implementation"""
    
    def test_vendor_config(self):
        """Test NVIDIA vendor configuration"""
        from zstacklib.gpu.vendors.nvidia import NVIDIA
        
        self.assertEqual(NVIDIA.VENDOR_NAME, "NVIDIA")
        self.assertIn("10de", NVIDIA.VENDOR_IDS)
        self.assertEqual(NVIDIA.CLI_TOOL, "nvidia-smi")
    
    def test_parse_basic_info(self):
        """Test NVIDIA basic info parsing"""
        from zstacklib.gpu.vendors.nvidia import NVIDIA

        output = """00000000:3B:00.0, 15360 MiB, 70.00 W, 1322519087621
00000000:86:00.0, 15360 MiB, 70.00 W, 1322519087622"""

        infos = NVIDIA.parse_basic_info(output)

        self.assertEqual(len(infos), 2)
        self.assertEqual(infos[0].pci_address, "0000:3b:00.0")
        self.assertEqual(infos[0].memory, "15360 MiB")
        self.assertEqual(infos[0].power, "70.00 W")
        self.assertEqual(infos[0].serial_number, "1322519087621")

    def test_parse_basic_info_with_function_1(self):
        """Test NVIDIA basic info parsing with function 1 devices (should only return function 0)"""
        from zstacklib.gpu.vendors.nvidia import NVIDIA

        # Simulate nvidia-smi returning both function 0 and function 1
        # Note: In reality, nvidia-smi should only return function 0, but we test the edge case
        output = """00000000:34:00.0, 15360 MiB, 70.00 W, 1322519087621
00000000:34:00.1, 15360 MiB, 70.00 W, 1322519087621
00000000:9e:00.0, 15360 MiB, 70.00 W, 1322519087622"""

        infos = NVIDIA.parse_basic_info(output)

        # All devices are parsed, but in get_all_gpu_infos_by_pci() we should filter to only function 0
        self.assertEqual(len(infos), 3)
        # Verify function numbers are preserved
        self.assertEqual(infos[0].pci_address, "0000:34:00.0")
        self.assertEqual(infos[1].pci_address, "0000:34:00.1")
        self.assertEqual(infos[2].pci_address, "0000:9e:00.0")
    
    def test_parse_metrics(self):
        """Test NVIDIA metrics parsing"""
        from zstacklib.gpu.vendors.nvidia import NVIDIA
        
        # Format: gpu_bus_id,utilization.gpu,utilization.memory,temperature.gpu,power.draw,index,gpu_serial
        # Note: index is required (7 fields total)
        output = "00000000:3B:00.0, 45 %, 62 %, 58, 65.23, 0, ABC123"
        
        metrics = NVIDIA.parse_metrics(output)
        
        self.assertEqual(len(metrics), 1)
        m = metrics[0]
        self.assertEqual(m.pci_address, "0000:3b:00.0")
        self.assertEqual(m.serial_number, "ABC123")
        self.assertEqual(m.power_draw, 65.23)
        self.assertEqual(m.temperature, 58.0)
        self.assertEqual(m.utilization, 45.0)
        self.assertEqual(m.memory_utilization, 62.0)

    def test_get_pci_only_candidates_3d_controller(self):
        """NVIDIA get_pci_only_candidates returns 10de + 3D controller when slot is function 0."""
        from zstacklib.gpu.vendors.nvidia import NVIDIA

        device_ids = {"0000:3b:00.0": {"Vendor": "10de", "Class": "030200", "Device": "1eb8"}}
        device_names = {
            "0000:3b:00.0": {
                "Class": "3D controller",
                "Vendor": "NVIDIA Corporation",
                "Device": "TU104",
            },
        }
        candidates = NVIDIA.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "0000:3b:00.0")
        self.assertEqual(candidates[0][1], {"isDriverLoaded": False})

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """NVIDIA get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.nvidia import NVIDIA

        device_ids = {"0000:3b:00.1": {"Vendor": "10de", "Class": "030200", "Device": "1eb8"}}
        device_names = {
            "0000:3b:00.1": {"Class": "3D controller", "Vendor": "NVIDIA Corporation", "Device": "TU104"},
        }
        candidates = NVIDIA.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])

    def test_detect_vfio_mdev_capability_creatable_fails_supported_also_fails(self):
        """When both -v -c and -s fail, card does not support vGPU."""
        from unittest.mock import patch, MagicMock
        from zstacklib.gpu.vendors.nvidia import NVIDIA

        pci_to = MagicMock()
        pci_to.pciDeviceAddress = "0000:3b:00.0"

        def fake_bash_roe(cmd):
            # both nvidia-smi vgpu queries fail
            return 1, '', 'error'

        with patch('zstacklib.gpu.vendors.nvidia.bash_roe', side_effect=fake_bash_roe), \
             patch('os.path.isdir', return_value=False):
            supported, info = NVIDIA.detect_vfio_mdev_capability(pci_to)

        self.assertFalse(supported)
        self.assertEqual(info, {})

    def test_detect_vfio_mdev_capability_sriov_vgpu_card_no_vfs(self):
        """SR-IOV backed vGPU card (L20/RTX8000): -v -c fails, -s succeeds,
        no sysfs dirs yet (VFs not created) -> VFIO_MDEV_VIRTUALIZABLE."""
        from unittest.mock import patch, MagicMock
        from zstacklib.gpu.vendors.nvidia import NVIDIA

        pci_to = MagicMock()
        pci_to.pciDeviceAddress = "0000:3b:00.0"

        def fake_bash_roe(cmd):
            if '-v -c' in cmd:
                return 1, '', 'no creatable instances'
            if ' -s' in cmd:
                return 0, 'vGPU Type ID : 239\n  Name : GRID L20-4Q\n', ''
            return 0, '', ''

        with patch('zstacklib.gpu.vendors.nvidia.bash_roe', side_effect=fake_bash_roe), \
             patch('os.path.isdir', return_value=False):
            supported, info = NVIDIA.detect_vfio_mdev_capability(pci_to)

        self.assertTrue(supported)
        self.assertEqual(info.get('virtStatus'), 'VFIO_MDEV_VIRTUALIZABLE')

    def test_detect_vfio_mdev_capability_normal_card_creatable_succeeds(self):
        """Normal vGPU card: -v -c succeeds, no sysfs dirs -> VFIO_MDEV_VIRTUALIZABLE."""
        from unittest.mock import patch, MagicMock
        from zstacklib.gpu.vendors.nvidia import NVIDIA

        pci_to = MagicMock()
        pci_to.pciDeviceAddress = "0000:3b:00.0"

        def fake_bash_roe(cmd):
            if '-v -c' in cmd:
                return 0, 'vGPU Type ID : 239\n  Name : GRID L20-4Q\n', ''
            return 0, '', ''

        with patch('zstacklib.gpu.vendors.nvidia.bash_roe', side_effect=fake_bash_roe), \
             patch('os.path.isdir', return_value=False):
            supported, info = NVIDIA.detect_vfio_mdev_capability(pci_to)

        self.assertTrue(supported)
        self.assertEqual(info.get('virtStatus'), 'VFIO_MDEV_VIRTUALIZABLE')

    def test_detect_tensorfusion_capability_supported(self):
        """TensorFusion capability requires NVIDIA driver >= 570.x."""
        from zstacklib.gpu.vendors.nvidia import NVIDIA
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        pci_device = type('PciDeviceTO', (), {'pciDeviceAddress': '0000:3b:00.0'})()

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                   return_value=(0, "00000000:3B:00.0, 570.124.06\n", "")), \
             patch("zstacklib.gpu.vendors.nvidia.os.path.exists", return_value=True):
            supported, info = NVIDIA.detect_tensorfusion_capability(pci_device)

        self.assertTrue(supported)
        self.assertEqual(info.get("virtStatus"), "TENSORFUSION_VIRTUALIZABLE")
        self.assertEqual(info.get("driverVersion"), "570.124.06")

    def test_detect_tensorfusion_capability_rejects_old_driver(self):
        """TensorFusion capability should reject NVIDIA driver versions below 570.x."""
        from zstacklib.gpu.vendors.nvidia import NVIDIA
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        pci_device = type('PciDeviceTO', (), {'pciDeviceAddress': '0000:3b:00.0'})()

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                   return_value=(0, "00000000:3B:00.0, 565.43.01\n", "")), \
             patch("zstacklib.gpu.vendors.nvidia.os.path.exists", return_value=True):
            supported, info = NVIDIA.detect_tensorfusion_capability(pci_device)

        self.assertFalse(supported)
        self.assertEqual(info.get("virtStatus"), "TENSORFUSION_NOT_SUPPORTED")
        self.assertIn("570.x", info.get("reason", ""))

    def test_detect_tensorfusion_capability_rejects_missing_worker_binary(self):
        """TensorFusion capability should reject hosts without tensor-fusion-worker installed."""
        from zstacklib.gpu.vendors.nvidia import NVIDIA
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        pci_device = type('PciDeviceTO', (), {'pciDeviceAddress': '0000:3b:00.0'})()

        with patch("zstacklib.gpu.vendors.nvidia.bash_roe",
                   return_value=(0, "00000000:3B:00.0, 570.124.06\n", "")), \
             patch("zstacklib.gpu.vendors.nvidia.os.path.exists", return_value=False):
            supported, info = NVIDIA.detect_tensorfusion_capability(pci_device)

        self.assertFalse(supported)
        self.assertEqual(info.get("virtStatus"), "TENSORFUSION_NOT_SUPPORTED")
        self.assertIn("tensor-fusion-worker", info.get("reason", ""))

class TestAMD(unittest.TestCase):
    """Test AMD vendor implementation"""
    
    def test_parse_basic_info_json(self):
        """Test AMD JSON parsing"""
        from zstacklib.gpu.vendors.amd import AMD
        
        output = """{
            "card0": {
                "PCI Bus": "0000:03:00.0",
                "VRAM Total Memory (B)": 16106127360,
                "Average Graphics Package Power (W)": "42.0",
                "Serial Number": "ABC123"
            }
        }"""
        
        infos = AMD.parse_basic_info(output)
        
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].pci_address, "0000:03:00.0")
        self.assertEqual(infos[0].serial_number, "ABC123")
        self.assertIn("MiB", infos[0].memory)

    def test_get_pci_only_candidates(self):
        """AMD get_pci_only_candidates returns 1002 + 3D controller when slot is function 0."""
        from zstacklib.gpu.vendors.amd import AMD

        device_ids = {"0000:03:00.0": {"Vendor": "1002", "Class": "030200", "Device": "7310"}}
        device_names = {
            "0000:03:00.0": {
                "Class": "3D controller",
                "Vendor": "Advanced Micro Devices, Inc.",
                "Device": "Navi 10",
            },
        }
        candidates = AMD.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "0000:03:00.0")
        self.assertEqual(candidates[0][1], {"isDriverLoaded": False})

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """AMD get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.amd import AMD

        device_ids = {"0000:03:00.1": {"Vendor": "1002", "Class": "030200", "Device": "7310"}}
        device_names = {
            "0000:03:00.1": {"Class": "3D controller", "Vendor": "Advanced Micro Devices, Inc.", "Device": "Navi 10"},
        }
        candidates = AMD.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])


class TestHuawei(unittest.TestCase):
    """Test Huawei vendor implementation"""

    def test_enrich_pci_device_dependencies_groups_chips_of_one_npu(self):
        from zstacklib.gpu.vendors.huawei import Huawei

        first = type('PciDeviceTO', (), {})()
        first.pciDeviceAddress = "0000:87:00.0"
        first.dependentDevices = ["0000:86:00.0"]
        second = type('PciDeviceTO', (), {})()
        second.pciDeviceAddress = "0000:97:00.0"
        second.dependentDevices = []
        gpu_info_map = {
            first.pciDeviceAddress: {"npuId": "0", "chipId": "0"},
            second.pciDeviceAddress: {"npuId": "0", "chipId": "1"},
        }

        Huawei.enrich_pci_device_dependencies(
            [first, second], gpu_info_map)

        self.assertEqual(
            first.dependentDevices,
            ["0000:86:00.0", second.pciDeviceAddress])
        self.assertEqual(second.dependentDevices, [first.pciDeviceAddress])

    def test_enrich_pci_device_dependencies_excludes_device_itself(self):
        from zstacklib.gpu.vendors.huawei import Huawei

        first = type('PciDeviceTO', (), {})()
        first.pciDeviceAddress = "0000:87:00.0"
        first.dependentDevices = [first.pciDeviceAddress]
        second = type('PciDeviceTO', (), {})()
        second.pciDeviceAddress = "0000:97:00.0"
        second.dependentDevices = []
        gpu_info_map = {
            first.pciDeviceAddress: {"npuId": "0", "chipId": "0"},
            second.pciDeviceAddress: {"npuId": "0", "chipId": "1"},
        }

        Huawei.enrich_pci_device_dependencies(
            [first, second], gpu_info_map)

        self.assertEqual(first.dependentDevices, [second.pciDeviceAddress])

    def test_enrich_pci_device_dependencies_ignores_incomplete_groups(self):
        from zstacklib.gpu.vendors.huawei import Huawei

        first = type('PciDeviceTO', (), {})()
        first.pciDeviceAddress = "0000:87:00.0"
        first.dependentDevices = []
        second = type('PciDeviceTO', (), {})()
        second.pciDeviceAddress = "0000:97:00.0"
        second.dependentDevices = []
        gpu_info_map = {
            first.pciDeviceAddress: {"npuId": "0", "chipId": "0"},
            second.pciDeviceAddress: {"npuId": "1", "chipId": "0"},
            "0000:a7:00.0": {"npuId": "0", "chipId": "1"},
        }

        Huawei.enrich_pci_device_dependencies(
            [first, second], gpu_info_map)

        self.assertEqual(first.dependentDevices, [])
        self.assertEqual(second.dependentDevices, [])
    
    def test_vendor_config(self):
        """Test Huawei vendor configuration"""
        from zstacklib.gpu.vendors.huawei import Huawei
        
        self.assertEqual(Huawei.VENDOR_NAME, "Huawei")
        self.assertIn("19e5", Huawei.VENDOR_IDS)
        self.assertEqual(Huawei.CLI_TOOL, "npu-smi")
    
    def test_parse_basic_info(self):
        """Test Huawei basic info parsing"""
        from zstacklib.gpu.vendors.huawei import Huawei
        
        output = """
Serial Number : ABC123456
PCIe Bus Info : 0000:3b:00.0
DDR Capacity(MB) : 32768
Power Dissipation : 150 W
"""
        
        infos = Huawei.parse_basic_info(output)
        
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].pci_address, "0000:3b:00.0")
        self.assertEqual(infos[0].serial_number, "ABC123456")
        self.assertEqual(infos[0].memory, "32768 MB")
        self.assertEqual(infos[0].power, "150 W")

    def test_parse_chip_info_summary_returns_only_healthy_chips(self):
        """Ascend 910C secondary chips are discovered without accepting Warning chips."""
        from zstacklib.gpu.vendors.huawei import Huawei

        output = """
| 0     Ascend910           | OK            | 161.9                32                      0    / 0                |
| 0     0                   | 0000:9D:00.0  | 0                    0    / 0                3101 / 65536            |
| 0     Ascend910           | Warning       | -                    32                      0    / 0                |
| 1     1                   | 0000:9F:00.0  | 0                    0    / 0                2887 / 65536            |
| 1     Ascend910           | OK            | 164.2                32                      0    / 0                |
| 0     2                   | 0000:99:00.0  | 0                    0    / 0                3101 / 65536            |
| 1     Ascend910           | OK            | -                    32                      0    / 0                |
| 1     3                   | 0000:9B:00.0  | 0                    0    / 0                2887 / 65536            |
"""

        infos = Huawei.parse_chip_info_summary(output)

        self.assertEqual(
            [info.pci_address for info in infos],
            ["0000:9d:00.0", "0000:99:00.0", "0000:9b:00.0"])
        self.assertEqual(infos[0].power, "161.9 W")
        self.assertEqual(infos[1].power, "164.2 W")
        self.assertIsNone(infos[2].power)
        self.assertEqual(infos[2].memory, "65536 MB")
        self.assertEqual(infos[2].extra["npuId"], "1")
        self.assertEqual(infos[2].extra["chipId"], "1")
        self.assertEqual(infos[2].extra["physicalId"], "3")

    def test_parse_chip_info_summary_resets_state_after_malformed_chip(self):
        """A malformed chip row must not leak its NPU state to the next row."""
        from zstacklib.gpu.vendors.huawei import Huawei

        output = """
| 0     Ascend910           | OK            | 161.9                32                      0    / 0                |
| 0                         | 0000:9D:00.0  | 0                    0    / 0                3101 / 65536            |
| 1     1                   | 0000:9B:00.0  | 0                    0    / 0                2887 / 65536            |
| 1     Ascend910           | OK            | 164.2                32                      0    / 0                |
| 0     2                   | 0000:99:00.0  | 0                    0    / 0                3101 / 65536            |
"""

        infos = Huawei.parse_chip_info_summary(output)

        self.assertEqual(
            [info.pci_address for info in infos], ["0000:99:00.0"])
        self.assertEqual(infos[0].extra["npuId"], "1")

    def test_get_basic_info_adds_healthy_secondary_chip(self):
        """Board output identifies chip 0; summary output supplies chip 1."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        board_output = """
Serial Number : BOARD001
PCIe Bus Info : 0000:99:00.0
Total DDR Capacity(MB) : 131072
Power Dissipation : 164.2 W
"""
        summary_output = """
| 1     Ascend910           | OK            | 164.2                32                      0    / 0                |
| 0     2                   | 0000:99:00.0  | 0                    0    / 0                3101 / 65536            |
| 1     Ascend910           | OK            | -                    32                      0    / 0                |
| 1     3                   | 0000:9B:00.0  | 0                    0    / 0                2887 / 65536            |
"""

        def mock_bash_roe(cmd):
            if cmd == "npu-smi info":
                return 0, summary_output, ""
            return 0, board_output, ""

        with patch.object(Huawei, "is_available", return_value=True), \
                patch.object(Huawei, "get_npu_ids", return_value=["1"]), \
                patch.object(Huawei, "check_npu_isolation", return_value=False), \
                patch("zstacklib.gpu.vendors.huawei.bash_roe", side_effect=mock_bash_roe):
            infos = Huawei.get_basic_info()

        self.assertEqual(
            [info.pci_address for info in infos],
            ["0000:99:00.0", "0000:9b:00.0"])
        self.assertEqual(infos[1].serial_number, "BOARD001")
        self.assertTrue(infos[1].driver_loaded)
        self.assertFalse(infos[1].extra["isIsolated"])

    def test_get_pci_only_candidates_processing_accelerators(self):
        """Huawei get_pci_only_candidates returns 19e5 + Processing accelerators when device name is valid."""
        from zstacklib.gpu.vendors.huawei import Huawei

        device_ids = {
            "0000:82:00.0": {"Vendor": "19e5", "Class": "120000", "Device": "d802"},
        }
        device_names = {
            "0000:82:00.0": {
                "Class": PCI_CLASS_PROCESSING_ACCEL,
                "Vendor": "Huawei Technologies Co., Ltd.",
                "Device": "Device d802",
            },
        }
        candidates = Huawei.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "0000:82:00.0")
        self.assertEqual(candidates[0][1], {"isDriverLoaded": False})

    def test_get_pci_only_candidates_skips_invalid_device_name(self):
        """Huawei get_pci_only_candidates returns empty when device name fails is_valid_processing_accelerator."""
        from zstacklib.gpu.vendors.huawei import Huawei

        device_ids = {
            "0000:82:00.0": {"Vendor": "19e5", "Class": "120000", "Device": "unknown"},
        }
        device_names = {
            "0000:82:00.0": {
                "Class": PCI_CLASS_PROCESSING_ACCEL,
                "Vendor": "Huawei Technologies Co., Ltd.",
                "Device": "Unknown accelerator XYZ",
            },
        }
        candidates = Huawei.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """Huawei get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.huawei import Huawei

        device_ids = {
            "0000:82:00.1": {"Vendor": "19e5", "Class": "120000", "Device": "d802"},
        }
        device_names = {
            "0000:82:00.1": {
                "Class": PCI_CLASS_PROCESSING_ACCEL,
                "Vendor": "Huawei Technologies Co., Ltd.",
                "Device": "Device d802",
            },
        }
        candidates = Huawei.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])

    def test_detect_sriov_capability_for_pf_with_vfs(self):
        from io import StringIO
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        class PciDevice(object):
            pciDeviceAddress = "0000:42:00.0"

        def open_sysfs(path, mode='r'):
            value = "12" if path.endswith("sriov_totalvfs") else "8"
            return StringIO(value)

        with patch("zstacklib.gpu.vendors.huawei.os.path.exists",
                   side_effect=lambda path: path.endswith(("sriov_totalvfs", "sriov_numvfs"))), \
                patch("zstacklib.gpu.vendors.huawei.open",
                      side_effect=open_sysfs, create=True):
            supported, info = Huawei.detect_sriov_capability(PciDevice())

        self.assertTrue(supported)
        self.assertEqual(info["maxPartNum"], "12")
        self.assertEqual(info["virtStatus"], "SRIOV_VIRTUALIZED")
        self.assertEqual(info["virtState"], "VIRTUALIZED")
        self.assertEqual(info["virtMode"], "SRIOV")
        self.assertEqual(info["virtCapabilities"], ["SRIOV"])

    def test_detect_sriov_capability_for_pf_without_vfs(self):
        from io import StringIO
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        class PciDevice(object):
            pciDeviceAddress = "0000:42:00.0"

        def open_sysfs(path, mode='r'):
            value = "12" if path.endswith("sriov_totalvfs") else "0"
            return StringIO(value)

        with patch("zstacklib.gpu.vendors.huawei.os.path.exists",
                   side_effect=lambda path: path.endswith(("sriov_totalvfs", "sriov_numvfs"))), \
                patch("zstacklib.gpu.vendors.huawei.open",
                      side_effect=open_sysfs, create=True):
            supported, info = Huawei.detect_sriov_capability(PciDevice())

        self.assertTrue(supported)
        self.assertEqual(info["maxPartNum"], "12")
        self.assertEqual(info["virtStatus"], "SRIOV_VIRTUALIZABLE")
        self.assertEqual(info["virtState"], "VIRTUALIZABLE")
        self.assertEqual(info["virtMode"], "")
        self.assertEqual(info["virtCapabilities"], ["SRIOV"])

    def test_detect_sriov_capability_for_vf(self):
        from io import StringIO
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        class PciDevice(object):
            pciDeviceAddress = "0000:42:01.0"

        def path_exists(path):
            return path.endswith("physfn") or path.endswith("physfn/sriov_numvfs")

        with patch("zstacklib.gpu.vendors.huawei.os.path.exists", side_effect=path_exists), \
                patch("zstacklib.gpu.vendors.huawei.os.readlink",
                      return_value="../0000:42:00.0"), \
                patch("zstacklib.gpu.vendors.huawei.open",
                      return_value=StringIO("8"), create=True):
            supported, info = Huawei.detect_sriov_capability(PciDevice())

        self.assertTrue(supported)
        self.assertEqual(info["maxPartNum"], "8")
        self.assertEqual(info["parentAddress"], "0000:42:00.0")
        self.assertEqual(info["virtStatus"], "SRIOV_VIRTUAL")
        self.assertEqual(info["virtState"], "VIRTUAL")
        self.assertEqual(info["virtMode"], "SRIOV")
        self.assertEqual(info["virtCapabilities"], [])

    def test_detect_sriov_capability_for_physical_device(self):
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        class PciDevice(object):
            pciDeviceAddress = "0000:01:00.0"

        with patch("zstacklib.gpu.vendors.huawei.os.path.exists", return_value=False):
            supported, info = Huawei.detect_sriov_capability(PciDevice())

        self.assertFalse(supported)
        self.assertEqual(info, {})

    def test_post_process_preserves_product_name_in_device(self):
        """ZSTAC-83466: When productName is available, device should keep productName
        after post_process_pci_device_by_vendor (not be overwritten to '-').

        The processing chain in _gpu_device_processor:
        1. lspci collects raw device (e.g. 'Device [d500]')
        2. gpu_info_map has productName -> device = productName
        3. post_process_pci_device_by_vendor is called last

        Previously step 3 forced device='-', losing the productName from step 2.
        """
        from zstacklib.utils.gpu import post_process_pci_device_by_vendor

        class FakePciDeviceTO(object):
            pass

        to = FakePciDeviceTO()
        to.vendor = "Huawei"
        # Simulate step 2: productName was set as device/name
        to.device = "Atlas 300T A2"
        to.name = "Atlas 300T A2"

        post_process_pci_device_by_vendor(to, "Huawei")

        self.assertEqual(to.device, "Atlas 300T A2")
        self.assertEqual(to.name, "Atlas 300T A2")

    def test_post_process_preserves_lspci_raw_device(self):
        """ZSTAC-83466: When no productName, device should keep lspci raw value
        after post_process_pci_device_by_vendor (not be overwritten to '-').

        This covers the case where npu-smi cannot retrieve productName,
        so device retains the lspci original value like 'Device [d500]'.
        """
        from zstacklib.utils.gpu import post_process_pci_device_by_vendor

        class FakePciDeviceTO(object):
            pass

        to = FakePciDeviceTO()
        to.vendor = "Huawei"
        # Simulate: no productName, lspci raw value kept
        to.device = "Device [d500]"
        to.name = "Huawei_Device [d500]"

        post_process_pci_device_by_vendor(to, "Huawei")

        self.assertEqual(to.device, "Device [d500]")
        self.assertEqual(to.name, "Huawei_Device [d500]")


class TestHaiguangGetPciOnlyCandidates(unittest.TestCase):
    """Test Haiguang get_pci_only_candidates."""

    def test_get_pci_only_candidates(self):
        """Haiguang get_pci_only_candidates returns 1d94 + 3D controller when slot is function 0."""
        from zstacklib.gpu.vendors.haiguang import Haiguang

        device_ids = {"0000:18:00.0": {"Vendor": "1d94", "Class": "030200", "Device": "0010"}}
        device_names = {
            "0000:18:00.0": {"Class": "3D controller", "Vendor": "Haiguang", "Device": "DCU"},
        }
        candidates = Haiguang.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "0000:18:00.0")
        self.assertEqual(candidates[0][1], {"isDriverLoaded": False})

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """Haiguang get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.haiguang import Haiguang

        device_ids = {"0000:18:00.1": {"Vendor": "1d94", "Class": "030200", "Device": "0010"}}
        device_names = {"0000:18:00.1": {"Class": "3D controller", "Vendor": "Haiguang", "Device": "DCU"}}
        candidates = Haiguang.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])


class TestHaiguang(unittest.TestCase):
    """Test Haiguang vendor implementation."""

    def test_parse_basic_info_accepts_pci_bus_with_serial_suffix(self):
        from zstacklib.gpu.vendors.haiguang import Haiguang

        output = """
{
  "card0": {
    "Serial Number": "TRCW390010030401",
    "PCI Bus": "0000:06:00.0 --> SN: TRCW390010030401",
    "Max Graphics Package Power (W)": "300.0",
    "Available memory size (MiB)": "65536"
  }
}
"""
        infos = Haiguang.parse_basic_info(output)

        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].pci_address, "0000:06:00.0")
        self.assertEqual(infos[0].serial_number, "TRCW390010030401")
        self.assertEqual(infos[0].power, "300.0")
        self.assertEqual(infos[0].memory, "65536 MiB")

    def test_parse_metrics_accepts_pci_bus_with_serial_suffix(self):
        from zstacklib.gpu.vendors.haiguang import Haiguang

        output = """
{
  "card0": {
    "Serial Number": "TRCW390010030401",
    "PCI Bus": "0000:06:00.0 --> SN: TRCW390010030401",
    "Average Graphics Package Power (W)": "108.0",
    "Temperature (Sensor junction) (C)": "70.0",
    "HCU use (%)": "3.0",
    "HCU memory use (%)": "5"
  }
}
"""
        metrics = Haiguang.parse_metrics(output)

        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].pci_address, "0000:06:00.0")
        self.assertEqual(metrics[0].serial_number, "TRCW390010030401")
        self.assertEqual(metrics[0].power_draw, 108.0)
        self.assertEqual(metrics[0].temperature, 70.0)
        self.assertEqual(metrics[0].utilization, 3.0)
        self.assertEqual(metrics[0].memory_utilization, 5.0)


class TestKunlunxinGetPciOnlyCandidates(unittest.TestCase):
    """Test Kunlunxin get_pci_only_candidates."""

    def test_get_pci_only_candidates(self):
        """Kunlunxin get_pci_only_candidates returns 2057 + Processing accelerators when slot is function 0."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        device_ids = {"0000:21:00.0": {"Vendor": "2057", "Class": "120000", "Device": "a000"}}
        device_names = {
            "0000:21:00.0": {
                "Class": PCI_CLASS_PROCESSING_ACCEL,
                "Vendor": "Kunlunxin",
                "Device": "XPU",
            },
        }
        candidates = Kunlunxin.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "0000:21:00.0")
        self.assertEqual(candidates[0][1], {"isDriverLoaded": False})

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """Kunlunxin get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        device_ids = {"0000:21:00.1": {"Vendor": "2057", "Class": "120000", "Device": "a000"}}
        device_names = {
            "0000:21:00.1": {"Class": PCI_CLASS_PROCESSING_ACCEL, "Vendor": "Kunlunxin", "Device": "XPU"},
        }
        candidates = Kunlunxin.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])


XPU_SMI_SAMPLE_OUTPUT = """\
==============XPUSMI LOG==============

Timestamp                                 : Tue Feb  3 18:20:01 2026
Driver Version                            : 5.0.21.26
XPU-RT Version                            : 10.2

Attached XPUs                             : 2
XPU 00000000:01:00.0
    Product Name                          : P800 PCIe
    Product Brand                         : KUNLUNXIN
    Serial Number                         : 02K0MA0258D0007R
    PCI
        Bus Id                            : 00000000:01:00.0
    Memory Usage
        Total                             : 98304 MiB
        Used                              : 0 MiB
    Utilization
        Xpu                               : 0 %
    Temperature
        XPU Current Temp                  : 46 C
    Power Readings
        Enforced Power Limit              : 350.00 W
        Power Draw                        : 76.00 W
"""


class TestKunlunxinParseBasicInfo(unittest.TestCase):
    """Test Kunlunxin parse_basic_info (vendor plugin path) - ZSTAC-81958."""

    def test_parse_basic_info_ignores_product_name(self):
        """Output contains Product Name but parse_basic_info should NOT put it in extra;
        productName is handled by enrich_addon_info instead."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        # XPU_SMI_SAMPLE_OUTPUT contains "Product Name : P800 PCIe"
        infos = Kunlunxin.parse_basic_info(XPU_SMI_SAMPLE_OUTPUT)
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].extra, {})

    def test_parse_basic_info_extracts_pci_address(self):
        """PCI address should be normalized."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        infos = Kunlunxin.parse_basic_info(XPU_SMI_SAMPLE_OUTPUT)
        self.assertEqual(infos[0].pci_address, "0000:01:00.0")

    def test_parse_basic_info_extracts_memory(self):
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        infos = Kunlunxin.parse_basic_info(XPU_SMI_SAMPLE_OUTPUT)
        self.assertEqual(infos[0].memory, "98304 MiB")

    def test_parse_basic_info_extracts_serial_number(self):
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        infos = Kunlunxin.parse_basic_info(XPU_SMI_SAMPLE_OUTPUT)
        self.assertEqual(infos[0].serial_number, "02K0MA0258D0007R")

    def test_parse_basic_info_extracts_power(self):
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        infos = Kunlunxin.parse_basic_info(XPU_SMI_SAMPLE_OUTPUT)
        self.assertEqual(infos[0].power, "350.00 W")

    def test_parse_basic_info_empty_output(self):
        """Empty output should return no GPUInfo."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        infos = Kunlunxin.parse_basic_info("")
        self.assertEqual(infos, [])

    def test_parse_basic_info_no_product_name(self):
        """parse_basic_info never sets productName; extra should always be empty."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        output = """\
XPU 00000000:02:00.0
    Serial Number                         : ABC123
    PCI
        Bus Id                            : 00000000:02:00.0
    Memory Usage
        Total                             : 32768 MiB
"""
        infos = Kunlunxin.parse_basic_info(output)
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].extra, {})


class TestKunlunxinEnrichAddonInfo(unittest.TestCase):
    """Test Kunlunxin enrich_addon_info with productName."""

    def test_enrich_addon_info_sets_product_name(self):
        """enrich_addon_info sets productName for Kunlunxin devices."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        gpu_info_map = {
            "0000:01:00.0": {"isDriverLoaded": True},
        }

        with patch.object(Kunlunxin, 'get_xpu_ids', return_value=["0"]):
            with patch('zstacklib.gpu.vendors.kunlunxin.bash_roe',
                        return_value=(0, XPU_SMI_SAMPLE_OUTPUT, "")):
                Kunlunxin.enrich_addon_info(gpu_info_map, ["0000:01:00.0"])

        self.assertEqual(gpu_info_map["0000:01:00.0"]["productName"], "P800 PCIe")

    def test_enrich_addon_info_cmd_fails(self):
        """enrich_addon_info does nothing when xpu-smi command fails."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        gpu_info_map = {
            "0000:01:00.0": {"isDriverLoaded": True},
        }

        with patch.object(Kunlunxin, 'get_xpu_ids', return_value=["0"]):
            with patch('zstacklib.gpu.vendors.kunlunxin.bash_roe',
                        return_value=(1, "", "error")):
                Kunlunxin.enrich_addon_info(gpu_info_map, ["0000:01:00.0"])

        self.assertNotIn("productName", gpu_info_map["0000:01:00.0"])

    def test_enrich_addon_info_empty_pci_addresses(self):
        """enrich_addon_info does nothing with empty pci_addresses."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        gpu_info_map = {}
        Kunlunxin.enrich_addon_info(gpu_info_map, [])
        self.assertEqual(gpu_info_map, {})


class TestKunlunxinPostProcessPciDevice(unittest.TestCase):
    """Test Kunlunxin post_process_pci_device cleans up wrong ID names."""

    def _make_pci_device(self, name, device, device_id="3686"):
        class FakePciDeviceTO(object):
            pass
        to = FakePciDeviceTO()
        to.name = name
        to.device = device
        to.deviceId = device_id
        return to

    def test_cleans_wrong_id_name(self):
        """'wrong ID' in name should be replaced with clean Kunlunxin_Device format."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        to = self._make_pci_device(
            "SafeNet (wrong ID)_Device 3686", "SafeNet (wrong ID)_Device 3686")
        Kunlunxin.post_process_pci_device(to)
        self.assertEqual(to.name, "Kunlunxin_3686")
        self.assertEqual(to.device, "Kunlunxin_3686")

    def test_no_change_for_normal_name(self):
        """Normal name without 'wrong ID' should not be modified."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        to = self._make_pci_device("P800 PCIe", "P800 PCIe")
        Kunlunxin.post_process_pci_device(to)
        self.assertEqual(to.name, "P800 PCIe")
        self.assertEqual(to.device, "P800 PCIe")

    def test_fallback_when_no_device_id(self):
        """When deviceId is empty, fall back to 'Kunlunxin_XPU'."""
        from zstacklib.gpu.vendors.kunlunxin import Kunlunxin

        to = self._make_pci_device(
            "SafeNet (wrong ID)_Device 3686", "SafeNet (wrong ID)_Device 3686",
            device_id="")
        Kunlunxin.post_process_pci_device(to)
        self.assertEqual(to.name, "Kunlunxin_XPU")
        self.assertEqual(to.device, "Kunlunxin_XPU")


class TestKunlunxinLegacyParse(unittest.TestCase):
    """Test legacy parse_kunlunxin_gpu_output_by_npu_id (gpu.py path) - ZSTAC-81958."""

    def test_legacy_parse_extracts_product_name(self):
        """Legacy parser should put productName at top level of dict."""
        from zstacklib.utils.gpu import parse_kunlunxin_gpu_output_by_npu_id

        infos = parse_kunlunxin_gpu_output_by_npu_id(XPU_SMI_SAMPLE_OUTPUT)
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].get("productName"), "P800 PCIe")

    def test_legacy_parse_extracts_all_fields(self):
        """Legacy parser should extract pciAddress, memory, serialNumber, temperature, etc."""
        from zstacklib.utils.gpu import parse_kunlunxin_gpu_output_by_npu_id

        infos = parse_kunlunxin_gpu_output_by_npu_id(XPU_SMI_SAMPLE_OUTPUT)
        info = infos[0]
        self.assertEqual(info.get("pciAddress"), "0000:01:00.0")
        self.assertEqual(info.get("memory"), "98304 MiB")
        self.assertEqual(info.get("memoryUsage"), "0 MiB")
        self.assertEqual(info.get("serialNumber"), "02K0MA0258D0007R")
        self.assertEqual(info.get("temperature"), "46 C")
        self.assertEqual(info.get("power"), "350.00 W")
        self.assertEqual(info.get("powerDraw"), "76.00 W")
        self.assertEqual(info.get("xpuUtilization"), "0 %")

    def test_legacy_parse_no_product_name(self):
        """If output has no Product Name line, key should be absent."""
        from zstacklib.utils.gpu import parse_kunlunxin_gpu_output_by_npu_id

        output = """\
XPU 00000000:02:00.0
    Serial Number                         : XYZ
    PCI
        Bus Id                            : 00000000:02:00.0
"""
        infos = parse_kunlunxin_gpu_output_by_npu_id(output)
        self.assertNotIn("productName", infos[0])


class TestVastaiGetPciOnlyCandidates(unittest.TestCase):
    """Test Vastai get_pci_only_candidates."""

    def test_get_pci_only_candidates(self):
        """Vastai get_pci_only_candidates returns 1edb + 3D controller when slot is function 0."""
        from zstacklib.gpu.vendors.vastai import Vastai

        device_ids = {"0000:17:00.0": {"Vendor": "1edb", "Class": "030200", "Device": "0001"}}
        device_names = {
            "0000:17:00.0": {"Class": "3D controller", "Vendor": "Vastai", "Device": "GPU"},
        }
        candidates = Vastai.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "0000:17:00.0")
        self.assertEqual(candidates[0][1], {"isDriverLoaded": False})

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """Vastai get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.vastai import Vastai

        device_ids = {"0000:17:00.1": {"Vendor": "1edb", "Class": "030200", "Device": "0001"}}
        device_names = {"0000:17:00.1": {"Class": "3D controller", "Vendor": "Vastai", "Device": "GPU"}}
        candidates = Vastai.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])


class TestEnflame(unittest.TestCase):
    """Test Enflame (燧原) vendor plugin; efsmi -q new driver uses Total Size."""

    def test_parse_basic_info_new_driver_total_size(self):
        """parse_basic_info accepts Total Size (new efsmi) and exact Dev key (not Device ID)."""
        from zstacklib.gpu.vendors.enflame import Enflame

        output = """
DEV ID 0
    Device Info
        Dev Name                : S60
        Dev SN                  : A0A1650510676
    PCIe Info
        Vendor ID               : 1e36
        Device ID               : c035
        Domain                  : 0000
        Bus                     : 17
        Dev                     : 00
        Func                    : 0
    Power Info
        Power Capa              : 300 W
    Device Mem Info
        Total Size              : 42976 MiB
"""
        infos = Enflame.parse_basic_info(output)
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0].pci_address, "0000:17:00.0")
        self.assertEqual(infos[0].serial_number, "A0A1650510676")
        self.assertEqual(infos[0].memory, "42976 MiB")
        self.assertEqual(infos[0].power, "300 W")
        self.assertEqual(infos[0].device_name, "S60")

    def test_get_basic_info_cmd_uses_efsmi_q(self):
        """get_basic_info_cmd returns efsmi -q for new driver compatibility."""
        from zstacklib.gpu.vendors.enflame import Enflame

        self.assertEqual(Enflame.get_basic_info_cmd(), "efsmi -q")

    def test_get_pci_only_candidates(self):
        """Enflame get_pci_only_candidates returns 1e36 + 3D controller when slot is function 0."""
        from zstacklib.gpu.vendors.enflame import Enflame

        device_ids = {"0000:17:00.0": {"Vendor": "1e36", "Class": "030200", "Device": "c035"}}
        device_names = {
            "0000:17:00.0": {"Class": "3D controller", "Vendor": "Enflame", "Device": "S60"},
        }
        candidates = Enflame.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "0000:17:00.0")
        self.assertEqual(candidates[0][1], {"isDriverLoaded": False})

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """Enflame get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.enflame import Enflame

        device_ids = {"0000:17:00.1": {"Vendor": "1e36", "Class": "030200", "Device": "c035"}}
        device_names = {"0000:17:00.1": {"Class": "3D controller", "Vendor": "Enflame", "Device": "S60"}}
        candidates = Enflame.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])


class TestEnflameMetrics(unittest.TestCase):
    """Test Enflame parse_metrics including powerCap in extra dict."""

    def test_parse_metrics_includes_power_cap(self):
        """parse_metrics should expose Power Capa as extra['powerCap'] for max power display."""
        from zstacklib.gpu.vendors.enflame import Enflame

        output = """
DEV ID 0
    Device Info
        Dev Name                : S60
        Dev SN                  : A0A1650510676
    PCIe Info
        Domain                  : 0000
        Bus                     : 17
        Dev                     : 00
        Func                    : 0
    Power Info
        Cur Power               : 102 W
        Power Capa              : 300 W
    Device Mem Info
        Total Size              : 42976 MiB
        Used Size               : 1024 MiB
    GCU Info
        GCU Temp                : 45 C
        GCU Usage               : 30 %
"""
        metrics = Enflame.parse_metrics(output)
        self.assertEqual(len(metrics), 1)
        m = metrics[0]
        self.assertEqual(m.pci_address, "0000:17:00.0")
        # power_draw should be current power (Cur Power)
        self.assertEqual(m.power_draw, 102.0)
        # temperature
        self.assertEqual(m.temperature, 45.0)
        # utilization
        self.assertEqual(m.utilization, 30.0)
        # powerCap should be in extra dict (max power for "最大功耗")
        self.assertIn("powerCap", m.extra)
        self.assertEqual(m.extra["powerCap"], 300.0)

    def test_parse_metrics_no_power_cap(self):
        """parse_metrics should handle missing Power Capa gracefully."""
        from zstacklib.gpu.vendors.enflame import Enflame

        output = """
DEV ID 0
    PCIe Info
        Domain                  : 0000
        Bus                     : 17
        Dev                     : 00
        Func                    : 0
    Power Info
        Cur Power               : 50 W
    GCU Info
        GCU Temp                : 38 C
"""
        metrics = Enflame.parse_metrics(output)
        self.assertEqual(len(metrics), 1)
        m = metrics[0]
        self.assertEqual(m.power_draw, 50.0)
        # No Power Capa in output, extra should be empty
        self.assertNotIn("powerCap", m.extra)


class TestTianshuGetPciOnlyCandidates(unittest.TestCase):
    """Test Tianshu get_pci_only_candidates."""

    def test_get_pci_only_candidates(self):
        """Tianshu get_pci_only_candidates returns 1e3e + 3D controller when slot is function 0."""
        from zstacklib.gpu.vendors.tianshu import Tianshu

        device_ids = {"0000:42:00.0": {"Vendor": "1e3e", "Class": "030200", "Device": "0001"}}
        device_names = {
            "0000:42:00.0": {"Class": "3D controller", "Vendor": "1e3e", "Device": "Tianshu GPU"},
        }
        candidates = Tianshu.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0][0], "0000:42:00.0")
        self.assertEqual(candidates[0][1], {"isDriverLoaded": False})

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """Tianshu get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.tianshu import Tianshu

        device_ids = {"0000:42:00.1": {"Vendor": "1e3e", "Class": "030200", "Device": "0001"}}
        device_names = {"0000:42:00.1": {"Class": "3D controller", "Vendor": "1e3e", "Device": "Tianshu GPU"}}
        candidates = Tianshu.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])


class TestAlibabaGetPciOnlyCandidates(unittest.TestCase):
    """Test Alibaba get_pci_only_candidates with _deviceId."""

    def test_get_pci_only_candidates_returns_device_id(self):
        """Alibaba get_pci_only_candidates returns _deviceId from lspci device_ids."""
        from zstacklib.gpu.vendors.alibaba import Alibaba

        device_ids = {
            "0000:08:00.0": {"Vendor": "1ded", "Class": "030200", "Device": "6001"},
            "0000:09:00.0": {"Vendor": "1ded", "Class": "030200", "Device": "6001"},
        }
        device_names = {
            "0000:08:00.0": {"Class": "3D controller", "Vendor": "Alibaba", "Device": "PPU-ZW810E"},
            "0000:09:00.0": {"Class": "3D controller", "Vendor": "Alibaba", "Device": "PPU-ZW810E"},
        }
        candidates = Alibaba.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(len(candidates), 2)
        for normalized, info in candidates:
            self.assertFalse(info["isDriverLoaded"])
            self.assertEqual(info["_deviceId"], "6001")

    def test_get_pci_only_candidates_skips_non_function_0(self):
        """Alibaba get_pci_only_candidates returns only function 0 slots."""
        from zstacklib.gpu.vendors.alibaba import Alibaba

        device_ids = {"0000:08:00.1": {"Vendor": "1ded", "Class": "030200", "Device": "6001"}}
        device_names = {
            "0000:08:00.1": {"Class": "3D controller", "Vendor": "Alibaba", "Device": "PPU-ZW810E"},
        }
        candidates = Alibaba.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])

    def test_get_pci_only_candidates_skips_wrong_vendor(self):
        """Alibaba get_pci_only_candidates skips non-Alibaba vendors."""
        from zstacklib.gpu.vendors.alibaba import Alibaba

        device_ids = {"0000:08:00.0": {"Vendor": "10de", "Class": "030200", "Device": "1eb8"}}
        device_names = {
            "0000:08:00.0": {"Class": "3D controller", "Vendor": "NVIDIA", "Device": "T4"},
        }
        candidates = Alibaba.get_pci_only_candidates(device_ids, device_names)
        self.assertEqual(candidates, [])


class TestAlibabaEnrichAddonInfo(unittest.TestCase):
    """Test Alibaba enrich_addon_info with device_id-based productName propagation."""

    def _make_gpu_info_map(self):
        """Build a gpu_info_map simulating 3 ppu-smi visible + 2 PCI-only (passthrough'd) devices."""
        return {
            # ppu-smi visible devices (have memory/serial, no isDriverLoaded=False)
            "0000:08:00.0": {"memory": "32768 MiB", "serialNumber": "SN001", "_deviceId": "6001"},
            "0000:09:00.0": {"memory": "32768 MiB", "serialNumber": "SN002", "_deviceId": "6001"},
            "0000:0a:00.0": {"memory": "32768 MiB", "serialNumber": "SN003", "_deviceId": "6001"},
            # PCI-only candidates (passthrough'd, isDriverLoaded=False)
            "0000:0b:00.0": {"isDriverLoaded": False, "_deviceId": "6001", "_vendor": "Alibaba"},
            "0000:0c:00.0": {"isDriverLoaded": False, "_deviceId": "6001", "_vendor": "Alibaba"},
        }

    def test_propagates_product_name_to_pci_only_by_device_id(self):
        """enrich_addon_info propagates productName to PCI-only devices with matching device_id."""
        from zstacklib.gpu.vendors.alibaba import Alibaba
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        gpu_info_map = self._make_gpu_info_map()
        all_pcis = list(gpu_info_map.keys())

        with patch("zstacklib.gpu.vendors.alibaba.bash_roe",
                   return_value=(0, "Product Name                          : PPU-ZW810E\n", "")):
            Alibaba.enrich_addon_info(gpu_info_map, all_pcis)

        # All 5 devices should have productName
        for pci_addr in all_pcis:
            self.assertEqual(gpu_info_map[pci_addr].get("productName"), "PPU-ZW810E",
                             "productName missing for %s" % pci_addr)

    def test_does_not_propagate_to_mismatched_device_id(self):
        """enrich_addon_info does NOT propagate productName if device_id doesn't match."""
        from zstacklib.gpu.vendors.alibaba import Alibaba
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        gpu_info_map = {
            "0000:08:00.0": {"memory": "32768 MiB", "_deviceId": "6001"},
            # Different device_id — should NOT get productName
            "0000:0b:00.0": {"isDriverLoaded": False, "_deviceId": "7002", "_vendor": "Alibaba"},
        }
        all_pcis = list(gpu_info_map.keys())

        with patch("zstacklib.gpu.vendors.alibaba.bash_roe",
                   return_value=(0, "Product Name                          : PPU-ZW810E\n", "")):
            Alibaba.enrich_addon_info(gpu_info_map, all_pcis)

        self.assertEqual(gpu_info_map["0000:08:00.0"]["productName"], "PPU-ZW810E")
        self.assertNotIn("productName", gpu_info_map["0000:0b:00.0"])

    def test_no_propagation_when_ppu_smi_fails(self):
        """enrich_addon_info does nothing when ppu-smi command fails."""
        from zstacklib.gpu.vendors.alibaba import Alibaba
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        gpu_info_map = self._make_gpu_info_map()
        all_pcis = list(gpu_info_map.keys())

        with patch("zstacklib.gpu.vendors.alibaba.bash_roe",
                   return_value=(1, "", "command not found")):
            Alibaba.enrich_addon_info(gpu_info_map, all_pcis)

        for pci_addr in all_pcis:
            self.assertNotIn("productName", gpu_info_map[pci_addr])


class TestEnrichGpuInfoMapPciOnlyInclusion(unittest.TestCase):
    """Test that enrich_gpu_info_map includes PCI-only candidates in vendor dispatch."""

    def test_pci_only_entries_dispatched_to_enrich_addon_info(self):
        """PCI-only entries with _vendor tag are passed to the vendor's enrich_addon_info."""
        try:
            from unittest.mock import patch, MagicMock
        except ImportError:
            from mock import patch, MagicMock

        from zstacklib.gpu import enrich_gpu_info_map, get_gpu_vendor

        gpu_info_map = {
            # PCI-only candidate with _vendor tag (no ppu-smi match)
            "0000:0b:00.0": {"isDriverLoaded": False, "_deviceId": "6001", "_vendor": "Alibaba"},
        }

        alibaba_cls = get_gpu_vendor("Alibaba")
        original_enrich = alibaba_cls.enrich_addon_info
        enrich_calls = []

        def mock_enrich(gmap, pcis):
            enrich_calls.append(pcis)

        with patch.object(alibaba_cls, 'enrich_addon_info', side_effect=mock_enrich):
            with patch.object(alibaba_cls, 'is_available', return_value=False):
                enrich_gpu_info_map(gpu_info_map)

        # enrich_addon_info should be called with the PCI-only address
        self.assertEqual(len(enrich_calls), 1)
        self.assertIn("0000:0b:00.0", enrich_calls[0])


class TestSupplementGpuInfoMapAnnotations(unittest.TestCase):
    """Test _supplement_gpu_info_map_from_pci annotates _vendor and _deviceId."""

    def test_pci_only_candidates_tagged_with_vendor_and_device_id(self):
        """PCI-only candidates from _supplement get _vendor and _deviceId tags."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        from zstacklib.utils.gpu import _supplement_gpu_info_map_from_pci

        lspci_id_output = """Slot:\t0000:08:00.0
Class:\t030200
Vendor:\t1ded
Device:\t6001

Slot:\t0000:09:00.0
Class:\t030200
Vendor:\t1ded
Device:\t6001
"""
        lspci_name_output = """Slot:\t0000:08:00.0
Class:\t3D controller
Vendor:\tAlibaba
Device:\tPPU-ZW810E

Slot:\t0000:09:00.0
Class:\t3D controller
Vendor:\tAlibaba
Device:\tPPU-ZW810E
"""
        gpu_info_map = {}  # Empty — no ppu-smi entries

        with patch("zstacklib.utils.pci.get_pci_device_ids",
                   return_value=(0, lspci_id_output, "")), \
             patch("zstacklib.utils.pci.get_pci_device_names",
                   return_value=(0, lspci_name_output, "")):
            _supplement_gpu_info_map_from_pci(gpu_info_map)

        # Both PCI devices should be added with _vendor and _deviceId
        self.assertIn("0000:08:00.0", gpu_info_map)
        self.assertIn("0000:09:00.0", gpu_info_map)
        for pci_addr in ["0000:08:00.0", "0000:09:00.0"]:
            self.assertEqual(gpu_info_map[pci_addr]["_vendor"], "Alibaba")
            self.assertEqual(gpu_info_map[pci_addr]["_deviceId"], "6001")
            self.assertFalse(gpu_info_map[pci_addr]["isDriverLoaded"])

    def test_existing_entries_annotated_with_device_id(self):
        """Pre-existing gpu_info_map entries (from ppu-smi) get _deviceId from lspci."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch

        from zstacklib.utils.gpu import _supplement_gpu_info_map_from_pci

        lspci_id_output = """Slot:\t0000:08:00.0
Class:\t030200
Vendor:\t1ded
Device:\t6001
"""
        lspci_name_output = """Slot:\t0000:08:00.0
Class:\t3D controller
Vendor:\tAlibaba
Device:\tPPU-ZW810E
"""
        # Pre-existing entry from ppu-smi (no _deviceId yet)
        gpu_info_map = {
            "0000:08:00.0": {"memory": "32768 MiB", "serialNumber": "SN001"},
        }

        with patch("zstacklib.utils.pci.get_pci_device_ids",
                   return_value=(0, lspci_id_output, "")), \
             patch("zstacklib.utils.pci.get_pci_device_names",
                   return_value=(0, lspci_name_output, "")):
            _supplement_gpu_info_map_from_pci(gpu_info_map)

        # Existing entry should NOT be replaced but should get _deviceId
        self.assertEqual(gpu_info_map["0000:08:00.0"]["memory"], "32768 MiB")
        self.assertEqual(gpu_info_map["0000:08:00.0"]["_deviceId"], "6001")


# =============================================================================
# Huawei NPU Isolation Detection Tests (ZSTAC-79981)
# =============================================================================

# Real npu-smi output samples captured from 172.30.8.31 (Ascend 910B, driver 25.3.rc1)

HCCS_OUTPUT_PARTIAL_ISOLATED_NOK = """\
        hccs health status              : NOK
        hccs link num in used           : 0
        hccs total bandwidth(GB/s)      : 0
        hccs used bandwidth(GB/s)       : 0
        HCCS lane detail info
                lane 0                  : 0
                lane 1                  : 0
                lane 2                  : 0
"""

HCCS_OUTPUT_HEALTHY_OK = """\
        hccs health status              : OK
        hccs link num in used           : 3
        hccs total bandwidth(GB/s)      : 89.4
        hccs used bandwidth(GB/s)       : 0
        HCCS lane detail info
                lane 0                  : 1
                lane 1                  : 1
                lane 2                  : 1
"""

HCCS_OUTPUT_FULL_ISOLATED_NOK = """\
        hccs health status              : NOK
        hccs link num in used           : 0
        hccs total bandwidth(GB/s)      : 0
        hccs used bandwidth(GB/s)       : 0
        HCCS lane detail info
                lane 0                  : 0
                lane 1                  : 0
                lane 2                  : 0
"""

TOPO_OUTPUT_NORMAL = """\
         NPU0   NPU1   NPU2   NPU3   NPU4   NPU5   NPU6   NPU7   CPU Affinity
NPU0      X     HCCS   HCCS   HCCS   SYS    SYS    SYS    SYS    0-23
NPU1     HCCS    X     HCCS   HCCS   SYS    SYS    SYS    SYS    0-23
NPU2     HCCS   HCCS    X     HCCS   SYS    SYS    SYS    SYS    0-23
NPU3     HCCS   HCCS   HCCS    X     SYS    SYS    SYS    SYS    0-23
NPU4      SYS    SYS    SYS    SYS    X     HCCS   HCCS   HCCS   24-47
NPU5      SYS    SYS    SYS    SYS   HCCS    X     HCCS   HCCS   24-47
NPU6      SYS    SYS    SYS    SYS   HCCS   HCCS    X     HCCS   24-47
NPU7      SYS    SYS    SYS    SYS   HCCS   HCCS   HCCS    X     24-47
"""

TOPO_OUTPUT_FULLY_ISOLATED = """\
         NPU0   NPU1   NPU2   NPU3   NPU4   NPU5   NPU6   NPU7   CPU Affinity
NPU0      X      SYS    SYS    SYS    SYS    SYS    SYS    SYS    0-23
NPU1      SYS    X      SYS    SYS    SYS    SYS    SYS    SYS    0-23
NPU2      SYS    SYS    X      SYS    SYS    SYS    SYS    SYS    0-23
NPU3      SYS    SYS    SYS    X      SYS    SYS    SYS    SYS    0-23
NPU4      SYS    SYS    SYS    SYS    X      SYS    SYS    SYS    24-47
NPU5      SYS    SYS    SYS    SYS    SYS    X      SYS    SYS    24-47
NPU6      SYS    SYS    SYS    SYS    SYS    SYS    X      SYS    24-47
NPU7      SYS    SYS    SYS    SYS    SYS    SYS    SYS    X      24-47
"""

TOPO_OUTPUT_PARTIAL_ISOLATED = """\
         NPU0   NPU1   NPU2   NPU3   NPU4   NPU5   NPU6   NPU7   CPU Affinity
NPU5      SYS    SYS    SYS    SYS    SYS    X      SYS    SYS    24-47
"""


class TestHuaweiNpuIsolation(unittest.TestCase):
    """Test Huawei NPU isolation detection (ZSTAC-79981).

    Scenarios verified on real hardware (172.30.8.31, Ascend 910B, driver 25.3.rc1):
      - Partial isolation: NPU 5,7 isolated via BMC → hccs NOK, topo shows 0 HCCS
      - Full isolation: all 8 NPUs isolated → hccs NOK for all, topo all SYS
      - Normal: all NPUs healthy → hccs OK, topo shows HCCS connections
    """

    def test_hccs_detects_isolated_npu(self):
        """Primary detection: hccs health NOK → isolated=True."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(0, HCCS_OUTPUT_PARTIAL_ISOLATED_NOK, "")):
            result = Huawei.check_npu_isolation("5", ["0", "1", "2", "3", "4", "5", "6", "7"])
        self.assertTrue(result)

    def test_hccs_detects_healthy_npu(self):
        """Primary detection: hccs health OK → isolated=False."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(0, HCCS_OUTPUT_HEALTHY_OK, "")):
            result = Huawei.check_npu_isolation("0", ["0", "1", "2", "3"])
        self.assertFalse(result)

    def test_hccs_detects_full_isolation(self):
        """Full isolation: all NPUs hccs NOK → each returns isolated=True."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        all_ids = ["0", "1", "2", "3", "4", "5", "6", "7"]
        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(0, HCCS_OUTPUT_FULL_ISOLATED_NOK, "")):
            for npu_id in all_ids:
                result = Huawei.check_npu_isolation(npu_id, all_ids)
                self.assertTrue(result, "NPU %s should be isolated" % npu_id)

    def test_single_npu_never_isolated(self):
        """Single NPU host (len <= 1) always returns False."""
        from zstacklib.gpu.vendors.huawei import Huawei

        self.assertFalse(Huawei.check_npu_isolation("0", ["0"]))
        self.assertFalse(Huawei.check_npu_isolation("0", []))
        self.assertFalse(Huawei.check_npu_isolation(None, ["0", "1"]))

    def test_get_npu_ids_filters_invalid_ids(self):
        """Invalid npu-smi placeholders such as -1 must not feed spec collection."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        output = """\
NPU ID                         : -1
NPU ID                         : 0
NPU ID                         : abc
NPU ID                         : 7
"""

        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(0, output, "")):
            self.assertEqual(Huawei.get_npu_ids(), ["0", "7"])

    def test_npu_smi_failure_returns_false(self):
        """When npu-smi fails (e.g. dcmi init error), falls back to topo."""
        try:
            from unittest.mock import patch, call
        except ImportError:
            from mock import patch, call
        from zstacklib.gpu.vendors.huawei import Huawei

        # Both hccs and topo fail → returns False
        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(1, "", "dcmi module initialize failed")):
            result = Huawei.check_npu_isolation("0", ["0", "1"])
        self.assertFalse(result)

    def test_topo_fallback_detects_isolated_npu(self):
        """When hccs output lacks health line, topo fallback detects isolation."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        hccs_no_health_line = "some unrelated output\nno health status here\n"

        def mock_bash_roe(cmd):
            if "-t hccs" in cmd:
                return (0, hccs_no_health_line, "")
            if "-t topo" in cmd:
                return (0, TOPO_OUTPUT_PARTIAL_ISOLATED, "")
            return (1, "", "unknown command")

        with patch("zstacklib.gpu.vendors.huawei.bash_roe", side_effect=mock_bash_roe):
            result = Huawei.check_npu_isolation("5", ["0", "1", "2", "3", "4", "5", "6", "7"])
        self.assertTrue(result)

    def test_topo_fallback_detects_healthy_npu(self):
        """When hccs output lacks health line, topo with HCCS links → not isolated."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        hccs_no_health_line = "some unrelated output\n"

        def mock_bash_roe(cmd):
            if "-t hccs" in cmd:
                return (0, hccs_no_health_line, "")
            if "-t topo" in cmd:
                return (0, TOPO_OUTPUT_NORMAL, "")
            return (1, "", "")

        with patch("zstacklib.gpu.vendors.huawei.bash_roe", side_effect=mock_bash_roe):
            result = Huawei.check_npu_isolation("0", ["0", "1"])
        self.assertFalse(result)

    def test_topo_full_isolation_all_sys(self):
        """Topo fallback: all SYS/no HCCS → isolated."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(0, TOPO_OUTPUT_FULLY_ISOLATED, "")):
            result = Huawei._check_isolation_by_topo("0")
        self.assertTrue(result)

    def test_topo_normal_has_hccs_links(self):
        """Topo: NPU with HCCS connections → not isolated."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.gpu.vendors.huawei import Huawei

        with patch("zstacklib.gpu.vendors.huawei.bash_roe",
                   return_value=(0, TOPO_OUTPUT_NORMAL, "")):
            result = Huawei._check_isolation_by_topo("0")
        self.assertFalse(result)


class TestLegacyNpuIsolation(unittest.TestCase):
    """Test legacy gpu.py check_huawei_npu_is_isolated with topo fallback (ZSTAC-79981)."""

    def test_get_huawei_npu_id_filters_invalid_ids(self):
        """Legacy Huawei parser filters invalid npu-smi placeholder IDs."""
        from zstacklib.utils.gpu import get_huawei_npu_id

        output = """\
NPU ID                         : -1
NPU ID                         : 2
NPU ID                         : unknown
NPU ID                         : 5
"""
        self.assertEqual(get_huawei_npu_id(output), ["2", "5"])

    def test_hccs_detects_isolated(self):
        """Legacy path: hccs NOK → isolated."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.utils.gpu import check_huawei_npu_is_isolated

        def mock_bash_roe(cmd):
            if "which npu-smi" in cmd:
                return (0, "/usr/bin/npu-smi", "")
            if "-t hccs" in cmd:
                return (0, HCCS_OUTPUT_PARTIAL_ISOLATED_NOK, "")
            return (1, "", "")

        with patch("zstacklib.utils.gpu.bash_roe", side_effect=mock_bash_roe):
            result = check_huawei_npu_is_isolated("5", ["0", "1", "2", "3", "4", "5", "6", "7"])
        self.assertTrue(result)

    def test_hccs_detects_healthy(self):
        """Legacy path: hccs OK → not isolated."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.utils.gpu import check_huawei_npu_is_isolated

        def mock_bash_roe(cmd):
            if "which npu-smi" in cmd:
                return (0, "/usr/bin/npu-smi", "")
            if "-t hccs" in cmd:
                return (0, HCCS_OUTPUT_HEALTHY_OK, "")
            return (1, "", "")

        with patch("zstacklib.utils.gpu.bash_roe", side_effect=mock_bash_roe):
            result = check_huawei_npu_is_isolated("0", ["0", "1", "2", "3"])
        self.assertFalse(result)

    def test_topo_fallback_when_hccs_missing_health(self):
        """Legacy path: hccs no health line → topo fallback detects isolation."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.utils.gpu import check_huawei_npu_is_isolated

        def mock_bash_roe(cmd):
            if "which npu-smi" in cmd:
                return (0, "/usr/bin/npu-smi", "")
            if "-t hccs" in cmd:
                return (0, "no health line here\n", "")
            if "-t topo" in cmd:
                return (0, TOPO_OUTPUT_FULLY_ISOLATED, "")
            return (1, "", "")

        with patch("zstacklib.utils.gpu.bash_roe", side_effect=mock_bash_roe):
            result = check_huawei_npu_is_isolated("0", ["0", "1", "2", "3", "4", "5", "6", "7"])
        self.assertTrue(result)

    def test_single_npu_never_isolated(self):
        """Legacy path: single NPU → False."""
        from zstacklib.utils.gpu import check_huawei_npu_is_isolated

        self.assertFalse(check_huawei_npu_is_isolated("0", ["0"]))
        self.assertFalse(check_huawei_npu_is_isolated("0", []))

    def test_npu_smi_not_found(self):
        """Legacy path: npu-smi not installed → False."""
        try:
            from unittest.mock import patch
        except ImportError:
            from mock import patch
        from zstacklib.utils.gpu import check_huawei_npu_is_isolated

        with patch("zstacklib.utils.gpu.bash_roe",
                   return_value=(1, "", "command not found")):
            result = check_huawei_npu_is_isolated("0", ["0", "1"])
        self.assertFalse(result)


class TestGPUInfo(unittest.TestCase):
    """Test GPUInfo dataclass"""
    
    def test_to_addon_dict(self):
        """Test conversion to addon dict"""
        from zstacklib.gpu.base import GPUInfo
        
        info = GPUInfo(
            pci_address="0000:3b:00.0",
            memory="15360 MiB",
            power="70 W",
            serial_number="ABC123",
            driver_loaded=True,
        )
        
        addon = info.to_addon_dict()
        
        self.assertEqual(addon["memory"], "15360 MiB")
        self.assertEqual(addon["power"], "70 W")
        self.assertEqual(addon["serialNumber"], "ABC123")
        self.assertTrue(addon["isDriverLoaded"])

    def test_to_addon_dict_with_driver_not_loaded(self):
        """Test to_addon_dict with isDriverLoaded=False: reserved for real GPU info, driver not loaded (ZSTAC-81489).
        No-match/failure should return None, not this dict."""
        from zstacklib.gpu.base import GPUInfo

        info = GPUInfo(
            pci_address="0000:3b:00.0",
            memory="15360 MiB",
            power="70 W",
            serial_number="ABC123",
            driver_loaded=False,
        )
        addon = info.to_addon_dict()
        self.assertFalse(addon["isDriverLoaded"])
        self.assertEqual(addon["memory"], "15360 MiB")


class TestIdentifyVendor(unittest.TestCase):
    """Test vendor identification utilities"""
    
    def test_identify_vendor_by_pci_id(self):
        """Test vendor identification by PCI ID"""
        from zstacklib.gpu import identify_vendor
        
        # NVIDIA by vendor ID
        result = identify_vendor("Unknown Device", "10de")
        self.assertEqual(result, "NVIDIA")
        
        # AMD by vendor ID
        result = identify_vendor("Unknown Device", "1002")
        self.assertEqual(result, "AMD")
    
    def test_identify_vendor_by_name(self):
        """Test vendor identification by PCI name"""
        from zstacklib.gpu import identify_vendor
        
        # NVIDIA by name
        result = identify_vendor("NVIDIA Corporation Tesla T4", "ffff")
        self.assertEqual(result, "NVIDIA")
    
    def test_identify_vendor_combined(self):
        """Test vendor identification with both name and ID"""
        from zstacklib.gpu import identify_vendor
        
        # Should match by ID first
        result = identify_vendor("NVIDIA Corporation Tesla T4", "10de")
        self.assertEqual(result, "NVIDIA")


class TestSimplifyDeviceName(unittest.TestCase):
    """Test pci.simplify_device_name extracts bracketed product name."""

    def test_nvidia_with_brackets(self):
        from zstacklib.utils.pci import simplify_device_name
        self.assertEqual(simplify_device_name("GA102 [GeForce RTX 3090]"), "GeForce RTX 3090")

    def test_nvidia_with_revision(self):
        from zstacklib.utils.pci import simplify_device_name
        self.assertEqual(simplify_device_name("GP107 [GeForce GTX 1050 Ti Rev. A]"),
                         "GeForce GTX 1050 Ti Rev. A")

    def test_no_brackets(self):
        from zstacklib.utils.pci import simplify_device_name
        self.assertEqual(simplify_device_name("Ascend 310P3"), "Ascend 310P3")

    def test_device_id_only(self):
        from zstacklib.utils.pci import simplify_device_name
        self.assertEqual(simplify_device_name("Device 3686"), "Device 3686")

    def test_empty(self):
        from zstacklib.utils.pci import simplify_device_name
        self.assertEqual(simplify_device_name(""), "")

    def test_none(self):
        from zstacklib.utils.pci import simplify_device_name
        self.assertIsNone(simplify_device_name(None))


class TestSimplifyVendorNameFallback(unittest.TestCase):
    """Test simplify_vendor_name fallback handles brackets."""

    def test_unknown_vendor_with_brackets(self):
        from zstacklib.utils.pci import simplify_vendor_name
        self.assertEqual(
            simplify_vendor_name("SomeVendor Co., Ltd [RealName]"),
            "RealName")

    def test_unknown_vendor_no_brackets(self):
        from zstacklib.utils.pci import simplify_vendor_name
        self.assertEqual(
            simplify_vendor_name("SomeVendor Co., Ltd Foo"),
            "SomeVendor Foo")

    def test_unknown_vendor_with_multiple_brackets(self):
        from zstacklib.utils.pci import simplify_vendor_name
        self.assertEqual(
            simplify_vendor_name("SomeVendor Co., Ltd [PartA] [PartB]"),
            "PartA PartB")

    def test_known_vendor_not_affected(self):
        from zstacklib.utils.pci import simplify_vendor_name
        self.assertEqual(simplify_vendor_name("NVIDIA Corporation"), "NVIDIA")


if __name__ == '__main__':
    unittest.main(verbosity=2)

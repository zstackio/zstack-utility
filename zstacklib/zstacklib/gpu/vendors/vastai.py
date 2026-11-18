# -*- coding: utf-8 -*-
"""
VastAI GPU Vendor Implementation (Python 2/3 Compatible)
"""

import json
import re

from zstacklib.utils import log
from zstacklib.utils.bash import bash_roe
from zstacklib.gpu.base import GPUBase, GPUInfo, GPUMetrics, register_gpu_vendor
from zstacklib.utils import shell, sizeunit

logger = log.get_logger(__name__)


@register_gpu_vendor
class Vastai(GPUBase):
    """
    VastAI GPU vendor implementation.
    """
    
    VENDOR_NAME = "Vastai"
    VENDOR_ENUM_NAME = "Vastai"
    VENDOR_IDS = {"1edb", "1ec6"}
    PCI_NAME_KEYWORDS = {"Vastai"}
    CLI_TOOL = "vasmi"
    DEVICE_TYPES = {"3D controller", "Processing accelerators"}

    @classmethod
    def get_pci_only_candidates(cls, device_ids, device_names):
        """
        When vasmi cannot report a device, identify VastAI GPU by PCI: vendor
        1edb or 1ec6, class 3D controller or Processing accelerators.
        """
        from zstacklib.utils.pci import normalize_pci_address

        result = []
        vendor_ids_lower = {v.lower() for v in cls.VENDOR_IDS}
        for slot in device_ids:
            if slot not in device_names or not slot.endswith('.0'):
                continue
            ids = device_ids[slot]
            names = device_names[slot]
            vendor_id = (ids.get('Vendor') or '').strip().lower()
            class_name = (names.get('Class') or '').strip()
            if vendor_id not in vendor_ids_lower:
                continue
            if class_name not in cls.DEVICE_TYPES:
                continue
            normalized = normalize_pci_address(slot)
            if normalized:
                result.append((normalized, {"isDriverLoaded": False}))
        return result

    @classmethod
    def get_vastai_type(cls):
        """
        Get VastAI GPU type by checking lspci output.
        
        Returns:
            "3D" for 3D controller, "AI" for Processing accelerators, or None
        """
        r, o, e = bash_roe("lspci | grep -E 'Vastai|1ec6'")
        if r != 0:
            return None
        
        first_line = o.split('\n')[0] if o else ""
        if "3D controller" in first_line:
            return "3D"
        elif "Processing accelerators" in first_line:
            return "AI"
        return None
    
    @classmethod
    def get_basic_info_cmd(cls, is_windows=False):
        """
        Return command to get basic GPU information (memory and serial number).
        
        Note: VastAI requires two commands to get complete info:
        1. vasmi getmem --display-format=json (memory and serial)
        2. vasmi summary --display-format=json (power)
        
        This method returns the first command. The second command is called
        internally in parse_basic_info() to supplement power information.
        
        Args:
            is_windows: True if running in Windows guest (not currently supported)
            
        Returns:
            Command string to execute
        """
        cmd = "vasmi getmem --display-format=json"
        if is_windows:
            # Note: Windows support may require different command format
            cmd = cmd.replace(" ", "|")
        return cmd
    
    @classmethod
    def parse_basic_info(cls, output):
        """
        Parse vasmi getmem output and supplement with power info from summary.
        
        Input format (JSON):
        {
            "elem": [
                {
                    "pci_bus": "0000:3b:00.0",
                    "sn": "SN123456",
                    "vals": {
                        "Physical": {"value": "16384 MiB"}  # for AI type
                        # or
                        "Physical memory": {"value": "16384 MiB"}  # for 3D type
                    }
                }
            ]
        }
        
        Args:
            output: JSON output from vasmi getmem command
            
        Returns:
            List of GPUInfo objects
        """
        gpu_infos = []
        if not output:
            return gpu_infos
        
        try:
            # Parse JSON output
            # Python 2/3 compatible: check if output is a string-like type
            if isinstance(output, str):
                mem_data = json.loads(output.strip())
            elif hasattr(output, 'decode'):  # bytes in Python 3
                mem_data = json.loads(output.decode('utf-8').strip())
            else:
                mem_data = output
        except (ValueError, TypeError) as e:
            logger.error("Failed to parse VastAI getmem JSON: %s" % str(e))
            return gpu_infos
        
        if not mem_data or "elem" not in mem_data:
            return gpu_infos
        
        # Get GPU type to determine memory key
        gpu_type = cls.get_vastai_type()
        
        # Parse memory and serial number from getmem output
        for elem in mem_data["elem"]:
            pci_address = cls.normalize_pci_address(elem.get("pci_bus", "N/A"))
            serial = elem.get("sn", "N/A")
            
            vals = elem.get("vals", {})
            # Determine memory key based on GPU type
            # When type is unknown (None), try both keys to avoid missing data
            if gpu_type == "AI":
                mem_val = vals.get("Physical", {}).get("value", "N/A")
            elif gpu_type == "3D":
                mem_val = vals.get("Physical memory", {}).get("value", "N/A")
            else:
                # Unknown type: try both keys, prefer Physical (AI type) first
                mem_val = vals.get("Physical", {}).get("value") or \
                          vals.get("Physical memory", {}).get("value", "N/A")
            
            # Convert memory to bytes if not "N/A"
            memory = mem_val
            if mem_val != "N/A":
                try:
                    memory = str(sizeunit.get_size(mem_val)) + "B"
                except Exception as e:
                    logger.debug("Failed to convert memory size %s: %s" % (mem_val, str(e)))
                    # Keep original value if parsing fails
                    memory = mem_val
            
            gpu_infos.append(GPUInfo(
                pci_address=pci_address,
                memory=memory,
                serial_number=serial
            ))
        
        # Supplement power information from summary command
        try:
            summary_data = shell.run_with_json_result("vasmi summary --display-format=json")
            if summary_data and "elem" in summary_data:
                for elem in summary_data["elem"]:
                    vals = elem.get("vals", {})
                    dev_bus_id = cls.normalize_pci_address(vals.get("devBusId", {}).get("value", "N/A"))
                    power = vals.get("P_Cap", {}).get("value", "N/A")
                    
                    # Match by PCI address and update power
                    for info in gpu_infos:
                        if info.pci_address == dev_bus_id:
                            info.power = power
                            break
        except Exception as e:
            logger.debug("Failed to get power info from summary: %s" % str(e))
        
        return gpu_infos
    
    @classmethod
    def _extract_number(cls, s):
        """
        Extract numeric value from string, handling various formats.
        
        Examples:
            "45.5 W" -> 45.5
            "62 %" -> 62
            "100 MB/S" -> 104857600 (converted to bytes)
            "58" -> 58.0
        """
        if s is None or s == "":
            return None
        
        if isinstance(s, (int, float)):
            return float(s)
        
        # Handle MB/S format and convert to bytes
        match = re.search(r'(\d+(?:\.\d+)?)\s*MB/S', str(s), flags=re.IGNORECASE)
        if match:
            return float(match.group(1)) * 1024 * 1024  # Convert to bytes
        
        # Extract any number (integer or float)
        match = re.search(r'(\d+(?:\.\d+)?)', str(s))
        return float(match.group(1)) if match else None
    
    @classmethod
    def get_metric_cmd(cls, is_windows=False):
        """
        Return command to get GPU metrics.
        
        Note: VastAI uses different commands based on GPU type:
        - AI type: vasmi show --display-format=json
        - 3D type: vasmi show --display-format=json
        
        This method returns the show command. The actual parsing
        will handle different GPU types internally.
        
        Args:
            is_windows: True if running in Windows guest (not currently supported)
            
        Returns:
            Command string to execute
        """
        cmd = "vasmi show --display-format=json"
        if is_windows:
            # Note: Windows support may require different command format
            cmd = cmd.replace(" ", "|")
        return cmd
    
    @classmethod
    def parse_metrics(cls, output):
        """
        Parse vasmi show output to extract GPU metrics.
        
        Input format (JSON):
        {
            "elem": [
                {
                    "pci_bus": "0000:3b:00.0",
                    "sn": "SN123456",
                    "vals": {
                        "Power Draw": {"value": "75.5 W"},
                        "Temperature": {"value": "62 C"},
                        "Utilization": {"value": "45 %"},
                        "Memory Utilization": {"value": "58 %"},
                        "Tx PCI": {"value": "100 MB/S"},
                        "Rx PCI": {"value": "200 MB/S"}
                    }
                }
            ]
        }
        
        Args:
            output: JSON output from vasmi show command
            
        Returns:
            List of GPUMetrics objects
        """
        results = []
        if not output:
            return results
        
        try:
            # Parse JSON output
            # Python 2/3 compatible: check if output is a string-like type
            if isinstance(output, str):
                show_data = json.loads(output.strip())
            elif hasattr(output, 'decode'):  # bytes in Python 3
                show_data = json.loads(output.decode('utf-8').strip())
            else:
                show_data = output
        except (ValueError, TypeError) as e:
            logger.error("Failed to parse VastAI show JSON: %s" % str(e))
            return results
        
        if not show_data or "elem" not in show_data:
            return results
        
        # Get GPU type to determine field names
        gpu_type = cls.get_vastai_type()
        
        # Parse metrics from show output
        for elem in show_data["elem"]:
            pci_address = cls.normalize_pci_address(elem.get("pci_bus", "N/A"))
            serial = elem.get("sn", "N/A")
            
            vals = elem.get("vals", {})
            
            # Extract metrics based on common field names
            # Field names may vary between AI and 3D types
            power_draw = None
            temperature = None
            utilization = None
            memory_utilization = None
            tx_pci_bytes = None
            rx_pci_bytes = None
            
            # Try different possible field names
            # Match field names flexibly to handle variations between AI and 3D types
            for key, val_dict in vals.items():
                key_lower = key.lower().replace("_", "").replace("-", "").replace(" ", "")
                value = val_dict.get("value") if isinstance(val_dict, dict) else None
                
                if not value or value == "N/A":
                    continue
                
                # Power draw - match "powerdraw", "power_draw", "p_cur", "currentpower", etc.
                if not power_draw and ("power" in key_lower and ("draw" in key_lower or "cur" in key_lower or "current" in key_lower)):
                    power_draw = cls._extract_number(value)
                elif not power_draw and key_lower in ("p_cur", "pcur", "currentpower", "powercurrent"):
                    power_draw = cls._extract_number(value)
                
                # Temperature - match "temperature", "temp", etc.
                elif not temperature and "temp" in key_lower:
                    temperature = cls._extract_number(value)
                
                # Utilization - match "utilization", "util", "gpuutil", etc. (but not memory utilization)
                elif not utilization and "util" in key_lower and "memory" not in key_lower:
                    utilization = cls._extract_number(value)
                
                # Memory utilization - match "memoryutilization", "memutil", etc.
                elif not memory_utilization and "memory" in key_lower and "util" in key_lower:
                    memory_utilization = cls._extract_number(value)
                
                # PCIe TX throughput - match "txpci", "tx_pci", "pcietx", "txpciinbytes", etc.
                elif not tx_pci_bytes and "tx" in key_lower and "pci" in key_lower:
                    tx_pci_bytes = cls._extract_number(value)
                
                # PCIe RX throughput - match "rxpci", "rx_pci", "pcierx", "rxpciinbytes", etc.
                elif not rx_pci_bytes and "rx" in key_lower and "pci" in key_lower:
                    rx_pci_bytes = cls._extract_number(value)
            
            # If no metrics found, try to get from summary command as fallback
            if power_draw is None:
                try:
                    summary_data = shell.run_with_json_result("vasmi summary --display-format=json")
                    if summary_data and "elem" in summary_data:
                        for summary_elem in summary_data["elem"]:
                            summary_vals = summary_elem.get("vals", {})
                            dev_bus_id = cls.normalize_pci_address(
                                summary_vals.get("devBusId", {}).get("value", "N/A"))
                            
                            if dev_bus_id == pci_address:
                                # Try to get current power from summary
                                power_val = summary_vals.get("P_Cur", {}).get("value") or \
                                           summary_vals.get("Power", {}).get("value")
                                if power_val:
                                    power_draw = cls._extract_number(power_val)
                                break
                except Exception as e:
                    logger.debug("Failed to get power from summary: %s" % str(e))
            
            # Create GPUMetrics object
            metrics = GPUMetrics(
                pci_address=pci_address,
                serial_number=serial,
                utilization=utilization,
                memory_utilization=memory_utilization,
                temperature=temperature,
                power_draw=power_draw,
                pcie_tx_bytes=tx_pci_bytes,
                pcie_rx_bytes=rx_pci_bytes
            )
            
            results.append(metrics)
        
        return results

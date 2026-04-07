# -*- coding: utf-8 -*-
"""
Enflame GPU vendor plugin.

Adaptation requirement: basic info and metrics both rely on the efsmi CLI; output format must
match the efsmi -q sample below. If driver/efsmi upgrade changes field names or section layout,
update parse_basic_info / parse_metrics accordingly.
"""
import re
from zstacklib.gpu.base import GPUBase, GPUInfo, GPUMetrics, register_gpu_vendor
from zstacklib.utils import log

logger = log.get_logger(__name__)

# efsmi -q output format (GPU CLI adaptation requirement; parse with exact key match for key: value)
# Old driver may use Mem Size / Mem Usage; new driver uses Total Size / Used Size / Free Size.
#
# -------------------------------------------------------------------------------
# ---------------------- Enflame System Management Interface ----------------------
# --------- Enflame Tech, All Rights Reserved. 2024-2025 Copyright (C) ----------
# --------------------------------------------------------------------------------
# DEV ID 0
#     Driver Info
#         Ver                     : 1.4.3.4
#     Device Info
#         Dev Name                : S60
#         Dev UUID                : TR6Y46010302
#         Dev SN                  : A0A1650510676
#         Dev PN                  : EFB-0088000-00
#         Dev MFD                 : 2025-1-6
#         Health                  : True
#     PCIe Info
#         Vendor ID               : 1e36
#         Device ID               : c035
#         Domain                  : 0000
#         Bus                     : 17
#         Dev                     : 00
#         Func                    : 0
#         Link Info
#         Max Link Speed          : Gen5
#         Max Link Width          : X16
#         Cur Link Speed          : Gen3
#         Cur Link Width          : X8
#         Tx Throughput           : 0 MiB/s
#         Rx Throughput           : 0 MiB/s
#     Clock Info
#         Mem CLK                 : 7000 MHz
#     Power Info
#         Power Capa              : 300 W
#         Cur Power               : 96 W
#         Dpm Level               : Sleep
#     Device Mem Info
#         Total Size              : 42976 MiB
#         Reserved Size           : 1129 MiB
#         Used Size               : 0 MiB
#         Free Size               : 41846 MiB
#     Temperature Info
#         GCU Temp                : 35 ℃
#     Voltage Info
#         VDD GCU                 : 0.702 V
#         VDD SOC                 : 0.743 V
#         VDD MEMQC               : 1.349 V
#     Device Usage Info
#         GCU Usage               : 0.0 %
#     ECC Mode
#         Current                 : Enable
#         Pending                 : Enable
#     RMA Info
#         Flags                   : False
#         Total DBE               : 0
#         ...
#     Power Cable
#         Status                  : Normal
#     VPU Info
#         Encoder Usage           : 0 %
#         Decoder Usage           : 0 %
#     Error Records / Error Details
#         ...
# DEV ID 1
#     ... (same structure, repeated for multiple devices)
# -------------------------------------------------------------------------------


@register_gpu_vendor
class Enflame(GPUBase):
    """Enflame GPU; CLI is efsmi; basic info and metrics both use efsmi -q; output format see file header."""

    VENDOR_NAME = "Enflame"
    VENDOR_ENUM_NAME = "Enflame"
    VENDOR_IDS = {"1e36"}
    PCI_NAME_KEYWORDS = {"Enflame"}
    CLI_TOOL = "efsmi"
    DEVICE_TYPES = {"3D controller", "Processing accelerators"}

    @classmethod
    def get_pci_only_candidates(cls, device_ids, device_names):
        """
        When efsmi is not available, identify Enflame GPU by PCI: vendor 1e36,
        class 3D controller or Processing accelerators.
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
    def get_basic_info_cmd(cls, is_windows=False):
        """Use efsmi -q for basic info (same as new driver; -a may be unavailable after upgrade)."""
        return "efsmi -q"

    @classmethod
    def parse_basic_info(cls, output):
        """
        Parse efsmi -q output; format see efsmi -q output block at file header (GPU CLI adaptation requirement).

        Supports old driver (Mem Size) and new driver (Total Size); PCI uses exact key match for Dev
        (do not match Device ID). Parsed fields: Dev Name, Dev SN, Domain, Bus, Dev, Func,
        Power Capa, Mem Size / Total Size.
        """
        gpu_infos = []
        if not output:
            return gpu_infos

        current_gpu = {}
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("DEV ID"):
                if current_gpu and "pciAddress" in current_gpu:
                    gpu_infos.append(GPUInfo(
                        pci_address=current_gpu["pciAddress"],
                        memory=current_gpu.get("memory"),
                        power=current_gpu.get("power"),
                        serial_number=current_gpu.get("serialNumber"),
                        device_name=current_gpu.get("deviceName")
                    ))
                current_gpu = {}
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key == "Dev Name":
                current_gpu["deviceName"] = value
            elif key == "Dev SN":
                current_gpu["serialNumber"] = value
            elif key == "Domain":
                current_gpu["domain"] = value
            elif key == "Bus":
                current_gpu["bus"] = value
            elif key == "Dev":
                current_gpu["dev"] = value
            elif key == "Func":
                current_gpu["func"] = value
                if all(k in current_gpu for k in ["domain", "bus", "dev", "func"]):
                    domain = current_gpu["domain"].strip()
                    if len(domain) == 8:
                        domain = domain[-4:]
                    else:
                        domain = domain.zfill(4)
                    addr = "%s:%s:%s.%s" % (
                        domain,
                        current_gpu["bus"],
                        current_gpu["dev"],
                        current_gpu["func"]
                    )
                    current_gpu["pciAddress"] = cls.normalize_pci_address(addr)
            elif key == "Power Capa":
                current_gpu["power"] = value
            elif key == "Mem Size" or key == "Total Size":
                current_gpu["memory"] = value

        if current_gpu and "pciAddress" in current_gpu:
            gpu_infos.append(GPUInfo(
                pci_address=current_gpu["pciAddress"],
                memory=current_gpu.get("memory"),
                power=current_gpu.get("power"),
                serial_number=current_gpu.get("serialNumber"),
                device_name=current_gpu.get("deviceName")
            ))

        return gpu_infos

    @classmethod
    def get_metric_cmd(cls, is_windows=False):
        """
        Return command to collect Enflame GPU metrics; output format see efsmi -q block at file header.

        Command: efsmi -q
        """
        cmd = "efsmi -q"
        if is_windows:
            cmd = cmd.replace(" ", "|")
        return cmd

    @classmethod
    def _extract_number(cls, text):
        """
        Extract numeric value from text, handling various formats.
        
        Examples:
            "102 W" -> 102.0
            "45 C" -> 45.0
            "58.5 %" -> 58.5
            "100 MiB/s" -> 104857600 (converted to bytes)
        """
        if not text:
            return None
        text = str(text).strip()
        
        # Handle MB/s or MiB/s format and convert to bytes
        match = re.search(r'(\d+(?:\.\d+)?)\s*(MB|MiB)/s', text, flags=re.IGNORECASE)
        if match:
            num = float(match.group(1))
            return int(num * 1024 * 1024)  # Convert to bytes
        
        # Extract any number (integer or float)
        match = re.search(r'(\d+(?:\.\d+)?)', text)
        return float(match.group(1)) if match else None

    @classmethod
    def _is_number(cls, s):
        """Check if string is a number"""
        if s is None or s == "":
            return False
        try:
            float(s)
            return True
        except (ValueError, TypeError):
            return False

    @classmethod
    def _calculate_percentage(cls, part, total):
        """Calculate percentage from part and total"""
        if not cls._is_number(part) or not cls._is_number(total):
            return None
        try:
            part_val = float(part)
            total_val = float(total)
            if total_val == 0:
                return None
            return (part_val / total_val) * 100
        except (ValueError, TypeError, ZeroDivisionError):
            return None

    @classmethod
    def parse_metrics(cls, output):
        """
        Parse efsmi -q output to get GPU metrics; format see efsmi -q block at file header.

        Same parsing logic as gpu.parse_enflame_gpu_output; use exact key match (e.g. Dev vs Device ID).
        """
        results = []
        if not output:
            return results
        
        # Parse using same logic as parse_enflame_gpu_output
        for dev in output.split("DEV ID")[1:]:
            gpuinfo = {}
            domain = bus = dev_id = func = None
            
            for line in dev.strip().splitlines():
                line = line.strip()
                if ':' in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                else:
                    key = line
                    value = ''
                
                if key == "Domain":
                    domain = value.zfill(4)
                elif key == "Bus":
                    bus = value.zfill(2)
                elif key == "Dev":
                    dev_id = value.zfill(2)
                elif key == "Func":
                    func = value
                elif key == "Mem Size" or key == "Total Size":
                    gpuinfo["memory"] = value
                elif key == "Mem Usage" or key == "Used Size":
                    gpuinfo["memoryUsage"] = value
                elif key == "Cur Power":
                    gpuinfo["power"] = value
                elif key == "Power Capa":
                    gpuinfo["powerCap"] = value
                elif key == "GCU Temp":
                    # Handle temperature with special characters (e.g., "45 'C")
                    gpuinfo["temperature"] = value
                elif key == "GCU Usage":
                    gpuinfo["gcuUsage"] = value
                elif key == "Dev SN":
                    gpuinfo["serialNumber"] = value
                elif key == "Tx Throughput":
                    gpuinfo["txThroughput"] = value
                elif key == "Rx Throughput":
                    gpuinfo["rxThroughput"] = value
            
            if domain and bus and dev_id and func:
                pci_address = cls.normalize_pci_address("{}:{}:{}.{}".format(
                    domain, bus, dev_id, func))
                serial_number = gpuinfo.get("serialNumber", "").strip()
                
                # Parse power (remove W unit)
                power = gpuinfo.get("power", "").replace(" ", "").strip().rstrip("W")
                power_value = cls._extract_number(power) if power else None
                
                # Parse temperature (remove C unit and special chars)
                temp = gpuinfo.get("temperature", "").replace(" ", "").strip()
                # Remove degree Celsius sign and C
                temp = re.sub(r"['\u00b0\u2103]?\s*C", "", temp, flags=re.IGNORECASE)
                temperature_value = cls._extract_number(temp) if temp else None
                
                # Parse GCU usage (remove % unit)
                gcu_usage = gpuinfo.get("gcuUsage", "").replace(" ", "").strip().rstrip("%")
                utilization_value = cls._extract_number(gcu_usage) if gcu_usage else None
                
                # Calculate memory utilization
                memory_usage = gpuinfo.get("memoryUsage", "").strip().rstrip("MiB")
                memory_total = gpuinfo.get("memory", "").strip().rstrip("MiB")
                memory_utilization_value = None
                if cls._is_number(memory_usage) and cls._is_number(memory_total):
                    memory_utilization_value = cls._calculate_percentage(memory_usage, memory_total)
                
                # Parse PCIe throughput (MiB/s -> bytes)
                rx_throughput = gpuinfo.get("rxThroughput", "").strip().rstrip("MiB/s")
                tx_throughput = gpuinfo.get("txThroughput", "").strip().rstrip("MiB/s")
                rx_bytes = cls._extract_number(rx_throughput + " MiB/s") if rx_throughput else None
                tx_bytes = cls._extract_number(tx_throughput + " MiB/s") if tx_throughput else None
                
                results.append(GPUMetrics(
                    pci_address=pci_address,
                    serial_number=serial_number,
                    utilization=utilization_value,
                    memory_utilization=memory_utilization_value,
                    temperature=temperature_value,
                    power_draw=power_value,
                    pcie_rx_bytes=rx_bytes,
                    pcie_tx_bytes=tx_bytes
                ))
        
        return results
    
    @classmethod
    def post_process_pci_device(cls, pci_device_to):
        """
        Post-process PCI device after collection.
        
        Enflame GPUs are not virtualizable, so set virtStatus to UNVIRTUALIZABLE.
        
        Args:
            pci_device_to: The PCI device transfer object
        """
        pci_device_to.virtStatus = "UNVIRTUALIZABLE"
        pci_device_to.virtState = "UNVIRTUALIZABLE"
        pci_device_to.virtMode = ""
        pci_device_to.virtCapabilities = []

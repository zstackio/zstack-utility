# -*- coding: utf-8 -*-
"""
Huawei NPU Vendor Implementation (Python 2/3 Compatible)
"""

import os
import re

from zstacklib.utils import log
from zstacklib.utils.bash import bash_roe, bash_ro
from zstacklib.gpu.base import (
    GPUBase,
    GPUInfo,
    GPUMetrics,
    register_gpu_vendor
)

logger = log.get_logger(__name__)


@register_gpu_vendor
class Huawei(GPUBase):
    """
    Huawei NPU vendor implementation.
    """

    # ==========================================================================
    # Vendor Identification
    # ==========================================================================

    VENDOR_NAME = "Huawei"
    VENDOR_ENUM_NAME = "Huawei"
    VENDOR_IDS = {"19e5"}
    PCI_NAME_KEYWORDS = {"Huawei Technologies", "HUAWEI"}
    CLI_TOOL = "npu-smi"

    DEVICE_TYPES = {"Processing accelerators"}
    IS_GPU_VENDOR = True

    # ==========================================================================
    # PCI-only fallback (no npu-smi): match by vendor_id + class + device name
    # ==========================================================================

    @classmethod
    def get_pci_only_candidates(cls, device_ids, device_names):
        """
        When npu-smi is not available, identify Huawei NPU by PCI: vendor 19e5,
        class Processing accelerators, and device name passing
        is_valid_processing_accelerator (supplementary filter).
        """
        from zstacklib.utils.gpu import is_valid_processing_accelerator
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
            device_name = (names.get('Device') or '').strip()
            if vendor_id not in vendor_ids_lower:
                continue
            if class_name not in cls.DEVICE_TYPES:
                continue
            if class_name == 'Processing accelerators' and not is_valid_processing_accelerator(
                    device_name):
                continue
            normalized = normalize_pci_address(slot)
            if normalized:
                result.append((normalized, {"isDriverLoaded": False}))
        return result

    # ==========================================================================
    # Multi-Device Enumeration
    # ==========================================================================

    @classmethod
    def get_npu_ids(cls):
        r, o, _ = bash_roe("npu-smi info -l")
        if r != 0:
            return []

        npu_ids = []
        for line in o.splitlines():
            line = line.strip()
            if "NPU ID" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    npu_id = parts[1].strip()
                    if not npu_id.isdigit():
                        logger.debug("Ignore invalid Huawei NPU ID: %s" % npu_id)
                        continue
                    npu_ids.append(npu_id)
        return npu_ids

    # ==========================================================================
    # Basic Information Collection
    # ==========================================================================

    @classmethod
    def get_basic_info_cmd(cls, is_windows=False):
        """
        This is not used directly - we override get_basic_info.
        """
        return "npu-smi info -l"

    @classmethod
    def get_basic_info_cmd_for_npu(cls, npu_id, is_windows=False):
        """Get command for specific NPU ID"""
        cmd = "npu-smi info -t board -i {0};npu-smi info -i {0} -t memory;npu-smi info -t power -i {0}".format(
            npu_id)
        if is_windows:
            cmd = cmd.replace(" ", "|")
        return cmd

    @classmethod
    def parse_basic_info(cls, output):
        """
        Parse npu-smi output for a single NPU.
        """
        gpu_infos = []
        gpu_info_dict = {}

        total_memory = 0
        total_ddr_memory = 0
        found_total_memory = False

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            if "Serial Number" in line:
                gpu_info_dict["serial_number"] = line.split(":")[1].strip()
            elif "PCIe Bus Info" in line:
                pci_addr = line.partition(": ")[-1].strip()
                gpu_info_dict["pci_address"] = cls.normalize_pci_address(
                    pci_addr)
            elif line.startswith("Total DDR Capacity(MB)"):
                try:
                    memory_value = int(line.split(":")[1].strip().split()[0])
                    total_ddr_memory += memory_value
                    found_total_memory = True
                except (ValueError, IndexError):
                    logger.debug(
                        "Failed to parse Total DDR Capacity: %s" % line)
            elif (line.startswith("DDR Capacity(MB)") or line.startswith("HBM Capacity")) and not found_total_memory:
                try:
                    memory_value = int(line.split(":")[1].strip().split()[0])
                    total_memory += memory_value
                except (ValueError, IndexError):
                    logger.debug("Failed to parse DDR/HBM Capacity: %s" % line)
            elif "Power Dissipation" in line or "Real-time Power(W)" in line:
                gpu_info_dict["power"] = line.split(":")[1].strip()

        total_memory = total_ddr_memory if found_total_memory else total_memory
        if total_memory > 0:
            gpu_info_dict["memory"] = "%s MB" % total_memory

        if gpu_info_dict.get("pci_address"):
            gpu_info = GPUInfo(
                pci_address=gpu_info_dict.get("pci_address", ""),
                memory=gpu_info_dict.get("memory"),
                power=gpu_info_dict.get("power"),
                serial_number=gpu_info_dict.get("serial_number"),
            )
            gpu_infos.append(gpu_info)

        return gpu_infos

    @classmethod
    def parse_chip_info_summary(cls, output):
        """Parse healthy chip PCI addresses from the ``npu-smi info`` table.

        On dual-chip devices such as Ascend 910C, ``info -t board`` only
        reports the PCI address of chip 0.  The summary table reports both
        chips, so use it to discover the secondary PCI function without
        treating Warning or otherwise unhealthy chips as nominal.

        See docs/hardware-tools/npu-smi-output.md#910c_normal_npu-smi-info_output
        for the complete real output captured from the 910C environment.

        See docs/hardware-tools/npu-smi-output.md#910b_normal_npu-smi-info_output
        for the complete real output captured from the 910B environment.
        """
        gpu_infos = []
        npu_id = None
        health = None
        power = None

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line.startswith("|"):
                continue

            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 3:
                continue

            pci_match = re.match(
                r"^(?:[0-9a-fA-F]{4}:)?[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$",
                cells[1])
            if pci_match:
                chip_fields = cells[0].split()
                current_npu_id, current_health, current_power = (
                    npu_id, health, power)
                npu_id, health, power = None, None, None

                if (current_npu_id is None or current_health is None
                        or len(chip_fields) < 2):
                    continue

                chip_id, physical_id = chip_fields[0], chip_fields[1]
                if current_health.upper() == "OK":
                    memory = None
                    memory_usages = re.findall(r"(\d+)\s*/\s*(\d+)", cells[2])
                    if memory_usages:
                        memory = "%s MB" % memory_usages[-1][1]

                    gpu_infos.append(GPUInfo(
                        pci_address=cls.normalize_pci_address(cells[1]),
                        memory=memory,
                        power=current_power,
                        extra={
                            "npuId": current_npu_id,
                            "chipId": chip_id,
                            "physicalId": physical_id,
                        }))

                continue

            npu_fields = cells[0].split()
            if not npu_fields or not npu_fields[0].isdigit():
                continue

            health_fields = cells[1].split()
            if not health_fields:
                continue

            npu_id = npu_fields[0]
            health = health_fields[0]
            power_fields = cells[2].split()
            power = "%s W" % power_fields[0] if power_fields and re.match(
                r"^[0-9]+(?:\.[0-9]+)?$", power_fields[0]) else None

        return gpu_infos

    @classmethod
    def get_basic_info(cls):
        """
        Override to handle multi-device enumeration.

        Steps:
        1. Get NPU ID list
        2. Query each NPU individually
        3. Combine results
        """
        if not cls.is_available():
            return []

        npu_ids = cls.get_npu_ids()
        if not npu_ids:
            logger.debug("No NPU IDs found")
            return []

        all_gpu_infos = []
        npu_id_map = {}  # pci_address -> npu_id
        npu_board_info = {}
        isolation_by_npu = {}

        for npu_id in npu_ids:
            cmd = cls.get_basic_info_cmd_for_npu(npu_id)
            r, o, e = bash_roe(cmd)
            if r != 0:
                logger.error("Failed to get NPU %s info: %s" % (npu_id, e))
                continue

            gpu_infos = cls.parse_basic_info(o)

            # Store NPU ID mapping
            for info in gpu_infos:
                if info.pci_address:
                    npu_id_map[info.pci_address.lower()] = npu_id
                    # Store NPU ID in extra field
                    info.extra["npuId"] = npu_id

                    # Check isolation status
                    try:
                        is_isolated = cls.check_npu_isolation(npu_id, npu_ids)
                        info.extra["isIsolated"] = is_isolated
                        isolation_by_npu[npu_id] = is_isolated
                    except Exception as ex:
                        logger.debug(
                            "Failed to check isolation for NPU %s: %s" % (npu_id, ex))
                        info.extra["isIsolated"] = False

                    npu_board_info[npu_id] = info

            all_gpu_infos.extend(gpu_infos)

        # ``info -t board`` exposes only chip 0 on dual-chip 910C boards.  Add
        # every secondary chip that the summary reports as healthy.  Keep the
        # detailed board data for chip 0 and use per-chip memory from the
        # summary for newly discovered PCI functions.
        r, o, e = bash_roe("npu-smi info")
        if r != 0:
            logger.debug("Failed to get Huawei NPU summary info: %s" % e)
            return all_gpu_infos

        summary_infos = cls.parse_chip_info_summary(o)
        existing_by_pci = {
            info.pci_address.lower(): info for info in all_gpu_infos
            if info.pci_address
        }
        for summary_info in summary_infos:
            pci_address = summary_info.pci_address.lower()
            npu_id = summary_info.extra.get("npuId")
            if pci_address in existing_by_pci:
                existing_by_pci[pci_address].extra.update(summary_info.extra)
                continue

            board_info = npu_board_info.get(npu_id)
            if board_info is not None:
                summary_info.serial_number = board_info.serial_number
            summary_info.extra["isIsolated"] = isolation_by_npu.get(
                npu_id, False)
            all_gpu_infos.append(summary_info)
            existing_by_pci[pci_address] = summary_info

        return all_gpu_infos

    # ==========================================================================
    # Addon Info Enrichment (productName, opaque)
    # ==========================================================================

    @classmethod
    def enrich_addon_info(cls, gpu_info_map, pci_addresses):
        """Add productName and opaque.aiosRankTable for Huawei NPUs."""
        if not pci_addresses:
            return
        npu_ids = cls.get_npu_ids()
        if not npu_ids:
            return
        from zstacklib.utils.gpu import (
            get_huawei_gpu_product_name_cmd,
            get_huawei_product_type,
            get_huawei_gpu_aios_rank_table_dict,
        )
        r, o, e = bash_roe(get_huawei_gpu_product_name_cmd(npu_ids[0]))
        if r == 0 and o and "not support" not in o:
            product_type = get_huawei_product_type(o)
            if product_type:
                for pci_addr in pci_addresses:
                    if pci_addr in gpu_info_map:
                        gpu_info_map[pci_addr]["productName"] = product_type
        try:
            aios_rank_table = get_huawei_gpu_aios_rank_table_dict(npu_ids)
            if aios_rank_table:
                for pci_addr in pci_addresses:
                    if pci_addr not in gpu_info_map:
                        continue
                    if "opaque" not in gpu_info_map[pci_addr]:
                        gpu_info_map[pci_addr]["opaque"] = {}
                    gpu_info_map[pci_addr]["opaque"]["aiosRankTable"] = aios_rank_table
        except Exception as ex:
            logger.debug(
                "Failed to batch collect Huawei aios rank table: %s" % ex)

    @classmethod
    def enrich_pci_device_dependencies(cls, pci_devices, gpu_info_map):
        devices_by_address = {
            cls.normalize_pci_address(device.pciDeviceAddress): device
            for device in pci_devices
        }
        chips_by_npu = {}
        for address, info in (gpu_info_map or {}).items():
            npu_id = info.get("npuId")
            chip_id = info.get("chipId")
            normalized_address = cls.normalize_pci_address(address)
            if (npu_id is None or chip_id is None
                    or normalized_address not in devices_by_address):
                continue
            chips_by_npu.setdefault(npu_id, {})[chip_id] = normalized_address

        for chips in chips_by_npu.values():
            if len(chips) < 2:
                continue
            addresses = set(chips.values())
            for address in addresses:
                device = devices_by_address[address]
                dependencies = {
                    dependency for dependency in (device.dependentDevices or [])
                    if cls.normalize_pci_address(dependency) != address
                }
                dependencies.update(
                    devices_by_address[peer].pciDeviceAddress
                    for peer in addresses if peer != address)
                device.dependentDevices = sorted(dependencies)

    # ==========================================================================
    # Prometheus Metrics Collection
    # ==========================================================================

    @classmethod
    def get_metric_cmd(cls, is_windows=False):
        """Not used directly - we override collect_metrics"""
        return "npu-smi info -l"

    @classmethod
    def get_metric_cmd_for_npu(cls, npu_id):
        """Get metrics command for specific NPU.
        Include board so combined output has PCIe Bus Info and Serial Number
        (usages/memory/temp/power alone may not contain them -> pci_address
        stays empty -> _collect_metrics_for_npu returns None -> no monitoring).
        """
        return ("npu-smi info -t board -i {0};"
                "npu-smi info -t usages -i {0};"
                "npu-smi info -t memory -i {0};"
                "npu-smi info -t temp -i {0};"
                "npu-smi info -t power -i {0}".format(npu_id))

    @classmethod
    def parse_metrics(cls, output):
        """
        Parse npu-smi metrics output.
        """
        # This would need to parse the combined output
        # For simplicity, we override collect_metrics
        return []

    @classmethod
    def collect_metrics(cls):
        """
        Override to handle multi-device enumeration for metrics.
        """
        if not cls.is_available():
            return []

        npu_ids = cls.get_npu_ids()
        if not npu_ids:
            return []

        all_metrics = []

        for npu_id in npu_ids:
            metrics = cls._collect_metrics_for_npu(npu_id)
            if metrics:
                all_metrics.append(metrics)

        return all_metrics

    @classmethod
    def _collect_metrics_for_npu(cls, npu_id):
        """Collect metrics for a single NPU"""
        cmd = cls.get_metric_cmd_for_npu(npu_id)
        r, o, _ = bash_roe(cmd)
        if r != 0:
            return None

        pci_address = ""
        serial_number = ""
        utilization = None
        mem_util = None
        temperature = None
        power_draw = None

        # Extra metrics for Huawei
        ddr_capacity = None
        ddr_usage_rate = None
        hbm_capacity = None
        hbm_usage_rate = None

        for line in o.splitlines():
            line = line.strip()
            if not line:
                continue

            if "PCIe Bus Info" in line or "Bus-Id" in line or "Bus Id" in line:
                raw = (line.partition(": ")[-1] or line.partition(":")[-1]).strip()
                normalized = cls.normalize_pci_address(raw)
                if normalized:
                    pci_address = normalized
            elif "Serial Number" in line:
                serial_number = line.split(":")[1].strip()
            elif "Aicore Usage Rate" in line or "NPU Usage" in line:
                match = re.search(r'(\d+(?:\.\d+)?)\s*%?', line.split(":")[1])
                if match:
                    utilization = float(match.group(1))
            elif "Memory Usage Rate" in line:
                match = re.search(r'(\d+(?:\.\d+)?)\s*%?', line.split(":")[1])
                if match:
                    mem_util = float(match.group(1))
            elif "Temperature" in line or "NPU Temp" in line:
                match = re.search(r'(\d+(?:\.\d+)?)', line.split(":")[1])
                if match:
                    temperature = float(match.group(1))
            elif "Real-time Power" in line or "Power Dissipation" in line:
                match = re.search(r'(\d+(?:\.\d+)?)', line.split(":")[1])
                if match:
                    power_draw = float(match.group(1))
            elif "DDR Capacity" in line:
                match = re.search(r'(\d+)', line.split(":")[1])
                if match:
                    ddr_capacity = float(match.group(1))
            elif "DDR Usage Rate" in line:
                match = re.search(r'(\d+(?:\.\d+)?)', line.split(":")[1])
                if match:
                    ddr_usage_rate = float(match.group(1))
            elif "HBM Capacity" in line:
                match = re.search(r'(\d+)', line.split(":")[1])
                if match:
                    hbm_capacity = float(match.group(1))
            elif "HBM Usage Rate" in line:
                match = re.search(r'(\d+(?:\.\d+)?)', line.split(":")[1])
                if match:
                    hbm_usage_rate = float(match.group(1))

        if not pci_address:
            return None

        metrics = GPUMetrics(
            pci_address=pci_address,
            serial_number=serial_number,
            utilization=utilization,
            memory_utilization=mem_util,
            temperature=temperature,
            power_draw=power_draw,
        )

        # Add extra Huawei-specific metrics
        if ddr_capacity is not None:
            metrics.extra["host_gpu_ddr_capacity"] = ddr_capacity
        if ddr_usage_rate is not None:
            metrics.extra["host_gpu_ddr_usage_rate"] = ddr_usage_rate
        if hbm_capacity is not None:
            metrics.extra["host_gpu_hbm_capacity"] = hbm_capacity
        if hbm_usage_rate is not None:
            metrics.extra["host_gpu_hbm_rate"] = hbm_usage_rate

        return metrics

    # ==========================================================================
    # Custom Prometheus Metrics
    # ==========================================================================

    @classmethod
    def get_custom_prometheus_metrics(cls):
        """
        Define Huawei-specific metrics.
        """
        return {
            "host_gpu_ddr_capacity": (
                "GPU DDR Capacity (MB)",
                "gauge",
                ["pci_device_address", "gpu_serial"]
            ),
            "host_gpu_ddr_usage_rate": (
                "GPU DDR Usage Rate (%)",
                "gauge",
                ["pci_device_address", "gpu_serial"]
            ),
            "host_gpu_hbm_capacity": (
                "GPU HBM Capacity (MB)",
                "gauge",
                ["pci_device_address", "gpu_serial"]
            ),
            "host_gpu_hbm_rate": (
                "GPU HBM Usage Rate (%)",
                "gauge",
                ["pci_device_address", "gpu_serial"]
            ),
        }

    # ==========================================================================
    # Isolation Detection
    # ==========================================================================

    @classmethod
    def check_npu_isolation(cls, npu_id, all_npu_ids):
        """
        Check if NPU is isolated using hccs health status, with topo-based
        fallback when hccs health line is missing from output.

        An isolated NPU should not be used for computation.
        Detection methods:
          1. Primary: `npu-smi info -t hccs` — health status != OK means isolated
          2. Fallback: `npu-smi info -t topo` — zero HCCS connections means isolated
        """
        if not npu_id or not all_npu_ids or len(all_npu_ids) <= 1:
            return False

        # Primary: hccs health status
        cmd = "npu-smi info -t hccs -i %s -c 0" % npu_id
        r, o, e = bash_roe(cmd)

        if r == 0 and o:
            for line in o.splitlines():
                line = line.strip().lower()
                if "hccs health status" in line:
                    parts = line.split(":", 1)
                    status = parts[1].strip().upper() if len(parts) > 1 else ""
                    if status != "OK":
                        logger.debug("NPU %s health status: %s (isolated)" %
                                     (npu_id, status))
                        return True
                    return False

        # Fallback: topo matrix — count HCCS connections for this NPU
        logger.debug("hccs health not available for NPU %s, trying topo fallback" % npu_id)
        return cls._check_isolation_by_topo(npu_id)

    @classmethod
    def _check_isolation_by_topo(cls, npu_id):
        """
        Fallback isolation detection via topo matrix.
        An isolated NPU has zero HCCS connections (all links show SYS or PHB).
        """
        cmd = "npu-smi info -t topo -i %s" % npu_id
        r, o, e = bash_roe(cmd)

        if r != 0 or not o:
            logger.debug("Failed to get topo for NPU %s: %s" % (npu_id, e))
            return False

        target_prefix = ("NPU%s" % npu_id).upper()
        hccs_count = None
        for line in o.splitlines():
            # Data rows start with NPU<id> at column 0 (no leading whitespace).
            # The header line is indented, so we check the raw (unstripped) line.
            if not line.startswith(target_prefix):
                continue
            parts = line.split()
            if not parts or parts[0].upper() != target_prefix:
                continue
            hccs_count = sum(1 for part in parts[1:] if part.upper() == "HCCS")
            break

        if hccs_count is None:
            logger.debug("NPU %s row not found in topo output" % npu_id)
            return False

        if hccs_count == 0:
            logger.debug("NPU %s has 0 HCCS connections in topo (isolated)" % npu_id)
            return True

        return False

    # ==========================================================================
    # AIOS Rank Table (for cluster interconnect)
    # ==========================================================================

    @classmethod
    def get_aios_rank_table(cls, npu_ids):
        """
        Get AIOS rank table for cluster interconnect.

        This is stored in addonInfo["opaque"]["aiosRankTable"].
        """
        if not npu_ids:
            return None

        device_ips = {}
        device_netmasks = {}

        for npu_id in npu_ids:
            if not npu_id.isdigit():
                continue

            r, o, _ = bash_roe("hccn_tool -i %s -ip -g" % npu_id)

            ip = None
            netmask = None

            if r == 0 and o:
                # Parse IP address
                ip_match = re.search(r'ipaddr:(\d+\.\d+\.\d+\.\d+)', o)
                if ip_match:
                    ip = ip_match.group(1)

                # Parse netmask
                netmask_match = re.search(r'netmask:(\d+\.\d+\.\d+\.\d+)', o)
                if netmask_match:
                    netmask = netmask_match.group(1)

            # Fallback defaults
            if not ip:
                ip = "10.20.0.%s" % (int(npu_id) + 2)
            if not netmask:
                netmask = "255.255.0.0"

            device_ips[npu_id] = ip
            device_netmasks[npu_id] = netmask

        rank_table = {
            "server_count": len(npu_ids),
            "server_list": []
        }

        for npu_id in npu_ids:
            server_info = {
                "device_id": npu_id,
                "host": device_ips.get(npu_id, ""),
                "device_ip": device_ips.get(npu_id, ""),
                "netmask": device_netmasks.get(npu_id, "")
            }
            rank_table["server_list"].append(server_info)

        return rank_table

    # ==========================================================================
    # Virtualization Capabilities Detection
    # ==========================================================================

    @classmethod
    def detect_vfio_mdev_capability(cls, pci_device_to):
        """
        Detect Huawei NPU mdev (mediated device) capability.

        Returns tuple: (is_supported, capability_info)
        """
        import os
        from zstacklib.utils import shell

        addr = pci_device_to.pciDeviceAddress
        check_mdev_folder = '/sys/bus/pci/devices/%s/mdev_supported_types' % addr
        if not os.path.isdir(check_mdev_folder):
            return False, {}

        if shell.run("which npu-smi") != 0:
            logger.debug("no npu-smi")
            return False, {}

        r, npu_ids_out = bash_ro("npu-smi info -l")
        if r != 0:
            logger.error("npu query gpu is error, %s " % npu_ids_out)
            return False, {}

        npu_ids = []
        for line in npu_ids_out.splitlines():
            line = line.strip()
            if not line:
                continue
            if "NPU ID" in line:
                npu_ids.append(line.split(":")[1].strip())

        if len(npu_ids) == 0:
            return False, {}

        add_found = False
        mdev_specs = []

        for npu_id in npu_ids:
            r, o, e = bash_roe("npu-smi info -t board -i %s" % npu_id)
            if r != 0:
                logger.error("npu query gpu board is error, %s " % e)
                continue

            if addr.lower() not in o.lower():
                continue

            add_found = True

            r, o, e = bash_roe("npu-smi info -t template-info -i %s" % npu_id)

            if r != 0:
                logger.error("npu query gpu template-info is error, %s " % e)
                continue

            for line in o.splitlines():
                match = re.match(
                    r'\|(\w+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\|', line)
                if match and len(match.group(1)) > 0:
                    template = {
                        'Name': match.group(1),
                        'TypeId': match.group(1),
                        'AICORE': int(match.group(2)),
                        'Memory': int(match.group(3)),
                        'AICPU': int(match.group(4)),
                        'VPC': int(match.group(5)),
                        'VENC': int(match.group(6)),
                        'JPEGD': int(match.group(7))
                    }
                    mdev_specs.append(template)

        if not add_found:
            logger.error(
                "can't find gpu %s mdev spec in npu-smi output" % addr)
            return False, {}

        capability_info = {
            'mdevSpecifications': mdev_specs
        }

        r, virtStatusOut = bash_ro("ls -l  /sys/bus/mdev/devices/")
        if r != 0:
            cls.set_capability_virt_metadata(
                capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                "VIRTUALIZABLE", None, ["VFIO_MDEV"])
        else:
            if addr.lower() in virtStatusOut.lower():
                cls.set_capability_virt_metadata(
                    capability_info, "VFIO_MDEV_VIRTUALIZED",
                    "VIRTUALIZED", "VFIO_MDEV", ["VFIO_MDEV"])
            else:
                cls.set_capability_virt_metadata(
                    capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                    "VIRTUALIZABLE", None, ["VFIO_MDEV"])

        return True, capability_info

    @classmethod
    def detect_sriov_capability(cls, pci_device_to, gpu_info_map=None):
        """
        Detect Huawei NPU SR-IOV capability.

        Returns tuple: (is_supported, capability_info)
        """
        addr = pci_device_to.pciDeviceAddress
        dev = os.path.join("/sys/bus/pci/devices/", addr)
        totalvfs = os.path.join(dev, "sriov_totalvfs")
        numvfs = os.path.join(dev, "sriov_numvfs")
        physfn = os.path.join(dev, "physfn")
        capability_info = {}

        if os.path.exists(totalvfs):
            with open(totalvfs, 'r') as f:
                capability_info['maxPartNum'] = f.read().strip()

            with open(numvfs, 'r') as f:
                if f.read().strip() != '0':
                    cls.set_capability_virt_metadata(
                        capability_info, "SRIOV_VIRTUALIZED",
                        "VIRTUALIZED", "SRIOV", ["SRIOV"])
                else:
                    cls.set_capability_virt_metadata(
                        capability_info, "SRIOV_VIRTUALIZABLE",
                        "VIRTUALIZABLE", None, ["SRIOV"])
            return True, capability_info

        if os.path.exists(physfn):
            parent_numvfs = os.path.join(physfn, "sriov_numvfs")
            if os.path.exists(parent_numvfs):
                with open(parent_numvfs, 'r') as f:
                    capability_info['maxPartNum'] = f.read().strip()

            cls.set_capability_virt_metadata(
                capability_info, "SRIOV_VIRTUAL",
                "VIRTUAL", "SRIOV", [])
            capability_info['parentAddress'] = os.readlink(
                physfn).split('/')[-1]
            return True, capability_info

        return False, {}

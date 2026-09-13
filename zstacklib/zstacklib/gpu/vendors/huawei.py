# -*- coding: utf-8 -*-
"""
Huawei NPU Vendor Implementation (Python 2/3 Compatible)
"""

import os
import re

from zstacklib.gpu.vendors import huawei_common

from zstacklib.utils import log
from zstacklib.utils.bash import bash_roe, bash_ro
from zstacklib.utils.npu import get_npu_smi_path
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

    @classmethod
    def get_npu_smi_cmd(cls):
        """Return a resolved command after callers have checked availability."""
        return get_npu_smi_path() or cls.CLI_TOOL

    @classmethod
    def is_available(cls):
        return get_npu_smi_path() is not None

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
        r, o, _ = bash_roe("%s info -l" % cls.get_npu_smi_cmd())
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
        return "%s info -l" % cls.get_npu_smi_cmd()

    @classmethod
    def get_basic_info_cmd_for_npu(cls, npu_id, is_windows=False):
        """Get command for specific NPU ID"""
        cmd = "{0} info -t board -i {1};{0} info -i {1} -t memory;{0} info -t power -i {1}".format(
            cls.get_npu_smi_cmd(), npu_id)
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
    def _parse_chip_info_summary_rows(cls, output):
        """Compatibility adapter for existing GPUInfo/health tuple callers."""
        return [(chip.info, chip.healthy)
                for chip in huawei_common.parse_summary(output)]

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
        return [
            info for info, is_healthy in cls._parse_chip_info_summary_rows(output)
            if is_healthy
        ]

    @classmethod
    def get_info_by_pci(cls, pci_address):
        """Collect only the logical NPU group containing ``pci_address``.

        The summary is the only host-wide query.  Once it maps the requested
        PCI function to an NPU ID, board/memory/power information is collected
        for that NPU only.  The model handler then decides whether the result
        contains one 910B chip or both 910C chips.
        """
        target_pci = cls.normalize_pci_address(pci_address)
        if not target_pci or not cls.is_available():
            return super(Huawei, cls).get_info_by_pci(pci_address)

        r, output, error = bash_roe("%s info" % cls.get_npu_smi_cmd())
        if r != 0 or not output:
            logger.debug("Failed to get Huawei NPU summary info: %s" % error)
            return super(Huawei, cls).get_info_by_pci(pci_address)

        chips = huawei_common.parse_summary(output)
        target_chip = next((
            chip for chip in chips if chip.info.pci_address == target_pci
        ), None)
        if target_chip is None or not target_chip.healthy:
            return super(Huawei, cls).get_info_by_pci(pci_address)

        target_npu_id = target_chip.info.extra.get("npuId")
        if target_npu_id is None:
            return super(Huawei, cls).get_info_by_pci(pci_address)

        board_records = []
        board_r, board_output, board_error = bash_roe(
            cls.get_basic_info_cmd_for_npu(target_npu_id))
        if board_r == 0:
            for info in cls.parse_basic_info(board_output):
                info.extra["npuId"] = target_npu_id
                board_records.append(huawei_common.gpu_info_to_record(info))
        else:
            logger.debug(
                "Failed to get NPU %s info: %s" %
                (target_npu_id, board_error))

        target_chips = [
            chip for chip in chips
            if chip.info.extra.get("npuId") == target_npu_id
        ]
        groups = huawei_common.group_npus(board_records, target_chips)
        group = groups.get(str(target_npu_id))
        if group is None:
            return super(Huawei, cls).get_info_by_pci(pci_address)

        records = huawei_common.merge_basic_info(board_records, target_chips)
        all_npu_ids = sorted({
            str(chip.info.extra.get("npuId")) for chip in chips
            if str(chip.info.extra.get("npuId", "")).isdigit()
        })
        for record in records:
            if record.get("pciAddress") != target_pci:
                continue
            chip_id = group.handler.get_isolation_chip_id(record)
            try:
                record["isIsolated"] = cls.check_npu_isolation(
                    target_npu_id, all_npu_ids, chip_id=chip_id,
                    physical_id=record.get("physicalId"))
            except Exception as ex:
                logger.debug(
                    "Failed to check isolation for NPU %s chip %s: %s" %
                    (target_npu_id, chip_id, ex))
                record["isIsolated"] = False
            break

        return [huawei_common.record_to_gpu_info(record)
                for record in records]

    @classmethod
    def get_basic_info(cls):
        """Collect board observations, then merge each logical NPU's model."""
        if not cls.is_available():
            return []
        npu_ids = cls.get_npu_ids()
        if not npu_ids:
            return []

        boards = []
        for npu_id in npu_ids:
            r, output, error = bash_roe(cls.get_basic_info_cmd_for_npu(npu_id))
            if r != 0:
                logger.error("Failed to get NPU %s info: %s" % (npu_id, error))
                continue
            for info in cls.parse_basic_info(output):
                info.extra["npuId"] = npu_id
                boards.append(huawei_common.gpu_info_to_record(info))

        r, output, error = bash_roe("%s info" % cls.get_npu_smi_cmd())
        if r != 0:
            logger.debug("Failed to get Huawei NPU summary info: %s" % error)
        chips = huawei_common.parse_summary(output) if r == 0 else []
        groups = huawei_common.group_npus(boards, chips)
        records = huawei_common.merge_basic_info(boards, chips)

        isolation_by_chip = {}
        for record in records:
            npu_id = record.get("npuId")
            group = groups[str(npu_id) if npu_id is not None else None]
            chip_id = group.handler.get_isolation_chip_id(record)
            key = (npu_id, chip_id)
            if key not in isolation_by_chip:
                try:
                    isolation_by_chip[key] = cls.check_npu_isolation(
                        npu_id, npu_ids, chip_id=chip_id,
                        physical_id=record.get("physicalId"))
                except Exception as ex:
                    logger.debug(
                        "Failed to check isolation for NPU %s chip %s: %s" %
                        (npu_id, chip_id, ex))
                    isolation_by_chip[key] = False
            record["isIsolated"] = isolation_by_chip[key]
        return [huawei_common.record_to_gpu_info(record) for record in records]

    # ==========================================================================
    # Addon Info Enrichment (productName, opaque)
    # ==========================================================================

    @classmethod
    def get_rank_table_device_ids(cls, gpu_info_map, pci_addresses):
        """Choose HCCN IDs using each selected logical NPU's model rules."""
        return huawei_common.rank_table_ids(gpu_info_map, pci_addresses)

    @classmethod
    def get_aios_rank_table(cls, gpu_info_map, pci_addresses):
        """Build a rank table for the selected Huawei PCI devices."""
        from zstacklib.utils.gpu import get_huawei_gpu_aios_rank_table_dict

        device_ids = cls.get_rank_table_device_ids(
            gpu_info_map, pci_addresses)
        if not device_ids:
            return None
        return get_huawei_gpu_aios_rank_table_dict(device_ids)

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
        )
        addresses_by_npu = {}
        for pci_addr in pci_addresses:
            info = gpu_info_map.get(pci_addr) or {}
            npu_id = info.get("npuId")
            if npu_id is not None:
                addresses_by_npu.setdefault(str(npu_id), []).append(pci_addr)

        # Product type is a logical-NPU property.  Query each selected NPU so
        # mixed hosts do not inherit the model name of the first NPU.
        for npu_id, addresses in addresses_by_npu.items():
            r, o, e = bash_roe(get_huawei_gpu_product_name_cmd(npu_id))
            if r != 0 or not o or "not support" in o:
                continue
            product_type = get_huawei_product_type(o)
            if product_type:
                for pci_addr in addresses:
                    gpu_info_map[pci_addr]["productName"] = product_type
        try:
            aios_rank_table = cls.get_aios_rank_table(
                gpu_info_map, pci_addresses)
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
        addresses_by_npu = {}
        for address, info in (gpu_info_map or {}).items():
            npu_id = info.get("npuId")
            normalized_address = cls.normalize_pci_address(address)
            if (npu_id is None
                    or normalized_address not in devices_by_address):
                continue
            addresses_by_npu.setdefault(npu_id, set()).add(
                normalized_address)

        for addresses in addresses_by_npu.values():
            if len(addresses) < 2:
                continue
            for address in addresses:
                device = devices_by_address[address]
                dependencies = {
                    cls.normalize_pci_address(dependency)
                    for dependency in (device.dependentDevices or [])
                    if cls.normalize_pci_address(dependency) != address
                }
                dependencies.update(
                    peer for peer in addresses if peer != address)
                device.dependentDevices = sorted(dependencies)

    # ==========================================================================
    # Prometheus Metrics Collection
    # ==========================================================================

    @classmethod
    def get_metric_cmd(cls, is_windows=False):
        """Not used directly - we override collect_metrics"""
        return "%s info -l" % cls.get_npu_smi_cmd()

    @classmethod
    def get_metric_cmd_for_npu(cls, npu_id, chip_id=None):
        """Get metrics command for a specific NPU/chip.
        Include board so combined output has PCIe Bus Info and Serial Number
        (usages/memory/temp/power alone may not contain them -> pci_address
        stays empty -> _collect_metrics_for_npu returns None -> no monitoring).
        """
        chip_option = "" if chip_id is None else " -c %s" % chip_id
        return ("{0} info -t board -i {1}{2};"
                "{0} info -t usages -i {1}{2};"
                "{0} info -t memory -i {1}{2};"
                "{0} info -t temp -i {1}{2};"
                "{0} info -t power -i {1}{2}".format(
                    cls.get_npu_smi_cmd(), npu_id, chip_option))

    @classmethod
    def get_metric_targets(cls, npu_ids):
        """One summary query yields per-NPU command selectors for mixed hosts."""
        r, output, error = bash_roe("%s info" % cls.get_npu_smi_cmd())
        if r != 0:
            logger.debug("Failed to get Huawei NPU summary info: %s" % error)
        groups = huawei_common.group_npus(
            chips=huawei_common.parse_summary(output) if r == 0 else [])
        targets = {}
        for npu_id in npu_ids:
            group = groups.get(str(npu_id), huawei_common.HuaweiNpuGroup(npu_id))
            targets[npu_id] = group.handler.get_metric_targets(group)
        return targets

    @classmethod
    def get_metric_chip_ids(cls, npu_ids):
        """Compatibility API: report only explicit chip selectors."""
        return {
            npu_id: [chip for chip in targets if chip is not None]
            for npu_id, targets in cls.get_metric_targets(npu_ids).items()
            if any(chip is not None for chip in targets)
        }

    @classmethod
    def get_npu_board_serial_number(cls, npu_id):
        """Get the logical NPU board serial without a chip selector.

        On Ascend 910C, the ``-c`` board query returns a chip PCI address but
        omits ``Serial Number``.  The non-chip board query retains the board
        serial shared by both chips.
        """
        r, output, error = bash_roe(
            "%s info -t board -i %s" % (cls.get_npu_smi_cmd(), npu_id))
        if r != 0:
            logger.debug("Failed to get Huawei NPU board serial: %s" % error)
            return None

        for line in output.splitlines():
            if "Serial Number" in line:
                return line.partition(":")[2].strip() or None
        return None

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

        targets_by_npu = cls.get_metric_targets(npu_ids)
        for npu_id in npu_ids:
            chip_ids = targets_by_npu[npu_id]
            board_serial_number = None
            if any(chip_id is not None for chip_id in chip_ids):
                board_serial_number = cls.get_npu_board_serial_number(npu_id)
            for chip_id in chip_ids:
                metrics = cls._collect_metrics_for_npu(npu_id, chip_id)
                if metrics:
                    if not metrics.serial_number and board_serial_number:
                        metrics.serial_number = board_serial_number
                    all_metrics.append(metrics)

        return all_metrics

    @classmethod
    def _collect_metrics_for_npu(cls, npu_id, chip_id=None):
        """Collect metrics for a single NPU chip."""
        cmd = cls.get_metric_cmd_for_npu(npu_id, chip_id)
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

        if mem_util is None:
            mem_util = hbm_usage_rate

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
    def check_npu_isolation(
            cls, npu_id, all_npu_ids, chip_id=None, physical_id=None):
        """
        Check if NPU is isolated using hccs health status, with topo-based
        fallback when hccs health line is missing from output.

        An isolated NPU should not be used for computation.
        Detection methods:
          1. Primary: `npu-smi info -t hccs` — health status != OK means isolated
          2. Fallback: `npu-smi info -t topo` — zero HCCS connections means isolated

        Ascend 910B topology rows are keyed by NPU ID. Ascend 910C rows are
        keyed by physical ID, so callers must pass the summary's physicalId
        when it is available.
        """
        if (not npu_id or not all_npu_ids
                or (len(all_npu_ids) <= 1 and chip_id is None)):
            return False

        # Primary: hccs health status
        target_chip_id = chip_id if chip_id is not None else "0"
        cmd = "%s info -t hccs -i %s -c %s" % (
            cls.get_npu_smi_cmd(), npu_id, target_chip_id)
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
        return cls._check_isolation_by_topo(npu_id, physical_id)

    @classmethod
    def _check_isolation_by_topo(cls, npu_id, physical_id=None):
        """
        Fallback isolation detection via topo matrix.
        An isolated NPU has zero HCCS connections (all links show SYS or PHB).
        """
        cmd = "%s info -t topo -i %s" % (cls.get_npu_smi_cmd(), npu_id)
        r, o, e = bash_roe(cmd)

        if r != 0 or not o:
            logger.debug("Failed to get topo for NPU %s: %s" % (npu_id, e))
            return False

        return huawei_common.topology_isolated(o, npu_id, physical_id)

    # ==========================================================================
    # Virtualization Capabilities Detection
    # ==========================================================================

    @classmethod
    def detect_vfio_mdev_capability(cls, pci_device_to, gpu_info_map=None):
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

        npu_smi_path = get_npu_smi_path()
        if not npu_smi_path:
            logger.debug("no npu-smi")
            return False, {}

        normalized_addr = cls.normalize_pci_address(addr)
        gpu_info = (gpu_info_map or {}).get(normalized_addr) or {}
        mapped_npu_id = gpu_info.get("npuId")

        if mapped_npu_id is not None:
            npu_ids = [mapped_npu_id]
        else:
            r, npu_ids_out = bash_ro("%s info -l" % npu_smi_path)
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
            if mapped_npu_id is None:
                r, o, e = bash_roe(
                    "%s info -t board -i %s" % (npu_smi_path, npu_id))
                if r != 0:
                    logger.error("npu query gpu board is error, %s " % e)
                    continue
                if addr.lower() not in o.lower():
                    continue

            add_found = True

            r, o, e = bash_roe("%s info -t template-info -i %s" % (npu_smi_path, npu_id))

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
        if cls.is_multi_chip_npu(pci_device_to, gpu_info_map):
            return False, {}

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

    @classmethod
    def is_multi_chip_npu(cls, pci_device_to, gpu_info_map):
        if not gpu_info_map:
            return False

        pci_address = cls.normalize_pci_address(
            pci_device_to.pciDeviceAddress)
        gpu_info = gpu_info_map.get(pci_address)
        if not gpu_info:
            return False

        npu_id = gpu_info.get("npuId")
        if npu_id is None:
            return False

        groups = huawei_common.group_npus(gpu_info_map.values())
        return groups[str(npu_id)].handler.multi_chip

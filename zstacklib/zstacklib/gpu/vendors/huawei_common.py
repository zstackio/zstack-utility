# -*- coding: utf-8 -*-
"""Shared Huawei observations and dispatch for plugin and legacy callers.

This module and the card-layout handlers perform no I/O. Public callers retain
their command runners, exception boundaries, and result formats. A group
belongs to one logical NPU in one collection; there is no host-wide model
cache.
"""
from collections import OrderedDict
import re

from zstacklib.gpu.base import GPUBase, GPUInfo
from zstacklib.gpu.vendors.ascend_one_chip_per_card import (
    AscendOneChipPerCardHandler)
from zstacklib.gpu.vendors.ascend_multiple_chips_per_card import (
    AscendMultipleChipsPerCardHandler)


class UnknownHuaweiHandler(AscendOneChipPerCardHandler):
    """Preserve board data and the legacy NPU-scoped fallback."""


class HuaweiChipInfo(object):
    def __init__(self, info, healthy, name=None):
        self.info = info
        self.healthy = healthy
        self.name = name

    def to_record(self, serial_number=None):
        result = gpu_info_to_record(self.info)
        if serial_number:
            result["serialNumber"] = serial_number
        return result


class HuaweiNpuGroup(object):
    def __init__(self, npu_id):
        self.npu_id = npu_id
        self.records = []
        self.chips = []
        self.chip_by_pci = {}

    def add_chip(self, chip):
        self.chips.append(chip)
        self.chip_by_pci[chip.info.pci_address] = chip

    @property
    def handler(self):
        return resolve_handler(self)


def resolve_handler(group):
    """Resolve observed layout per logical NPU, including partial summaries.

    Product metadata is only a compatibility hint from existing callers.
    No product command is required. Missing evidence remains unknown.
    """
    infos = group.records + [chip.info.extra for chip in group.chips]
    if (any(info.get("physicalId") is not None for info in infos)
            or len({info.get("chipId") for info in infos
                    if info.get("chipId") is not None}) > 1
            or any("910C" in str(info.get("productName", "")).upper()
                   for info in infos)):
        return AscendMultipleChipsPerCardHandler
    if (any((chip.name or "").upper().startswith("910B")
            for chip in group.chips)
            or any("910B" in str(info.get("productName", "")).upper()
                   for info in infos)):
        return AscendOneChipPerCardHandler
    return UnknownHuaweiHandler


def group_npus(records=(), chips=()):
    groups = OrderedDict()

    def get_group(npu_id):
        key = str(npu_id) if npu_id is not None else None
        if key not in groups:
            groups[key] = HuaweiNpuGroup(key)
        return groups[key]

    for record in records:
        get_group(record.get("npuId")).records.append(record)
    for chip in chips:
        get_group(chip.info.extra.get("npuId")).add_chip(chip)
    return groups


def gpu_info_to_record(info):
    result = info.to_addon_dict()
    result["pciAddress"] = info.pci_address
    return result


def record_to_gpu_info(record):
    extra = dict(record)
    return GPUInfo(
        pci_address=extra.pop("pciAddress"),
        memory=extra.pop("memory", None),
        power=extra.pop("power", None),
        serial_number=extra.pop("serialNumber", None),
        driver_loaded=extra.pop("isDriverLoaded", True),
        extra=extra)


def parse_summary(output):
    """Decode table rows once, retaining health for monitoring and inventory."""
    gpu_infos = []
    npu_id = None
    npu_name = None
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
            current_npu_id, current_npu_name, current_health, current_power = (
                npu_id, npu_name, health, power)
            npu_id, npu_name, health, power = None, None, None, None

            if (current_npu_id is None or current_health is None
                    or not chip_fields):
                continue
            if (len(chip_fields) < 2
                    and not (current_npu_name or "").upper().startswith("910B")):
                continue

            chip_id = chip_fields[0]
            physical_id = chip_fields[1] if len(chip_fields) > 1 else None
            memory = None
            memory_usages = re.findall(r"(\d+)\s*/\s*(\d+)", cells[2])
            if memory_usages:
                memory = "%s MB" % memory_usages[-1][1]

            extra = {
                "npuId": current_npu_id,
                "chipId": chip_id,
            }
            if physical_id is not None:
                extra["physicalId"] = physical_id
            gpu_infos.append(HuaweiChipInfo(
                GPUInfo(
                    pci_address=GPUBase.normalize_pci_address(cells[1]),
                    memory=memory,
                    power=current_power,
                    extra=extra),
                current_health.upper() == "OK", current_npu_name))

            continue

        npu_fields = cells[0].split()
        if not npu_fields or not npu_fields[0].isdigit():
            continue

        health_fields = cells[1].split()
        if not health_fields:
            continue

        npu_id = npu_fields[0]
        npu_name = npu_fields[1] if len(npu_fields) > 1 else None
        health = health_fields[0]
        power_fields = cells[2].split()
        power = "%s W" % power_fields[0] if power_fields and re.match(
            r"^[0-9]+(?:\.[0-9]+)?$", power_fields[0]) else None

    return gpu_infos


def merge_basic_info(board_records, chips):
    """Return board order first, followed by newly discovered healthy chips."""
    boards = []
    for record in board_records:
        address = GPUBase.normalize_pci_address(record.get("pciAddress"))
        if address:
            board = dict(record)
            board["pciAddress"] = address
            boards.append(board)
    groups = group_npus(boards, chips)
    chip_by_pci = {chip.info.pci_address: chip for chip in chips}
    results = []
    consumed = set()
    for board in boards:
        # PCI remains the primary match, including older callers whose board
        # record lacks npuId. Group-scoped peer fallback still needs npuId.
        chip = chip_by_pci.get(board["pciAddress"])
        key = (chip.info.extra.get("npuId") if chip is not None
               else board.get("npuId"))
        group = groups[str(key) if key is not None else None]
        results.append(group.handler.merge_basic_info(board, group))
        consumed.add(board["pciAddress"])

    for chip in chips:
        if not chip.healthy or chip.info.pci_address in consumed:
            continue
        group = groups[str(chip.info.extra["npuId"])]
        board = group.records[-1] if group.records else {}
        results.append(chip.to_record(board.get("serialNumber")))
    return results


def rank_table_ids(gpu_info_map, pci_addresses):
    # Only selected PCI devices contribute HCCN IDs, including mixed hosts.
    records = [gpu_info_map.get(address) or {} for address in pci_addresses]
    records = [info for info in records
               if str(info.get("npuId", "")).isdigit()]
    ids = set()
    for group in group_npus(records).values():
        ids.update(group.handler.get_rank_table_ids(group))
    return sorted(ids, key=int)


def topology_isolated(output, npu_id, physical_id=None):
    handler = (AscendMultipleChipsPerCardHandler
               if physical_id is not None else UnknownHuaweiHandler)
    target = handler.get_topology_target(npu_id, physical_id)
    if target is None:
        return False
    target = target.upper()
    relation_types = {
        "X", "HCCS", "HCCS_SW", "SIO", "SYS", "PHB", "PIX", "PXB", "NODE", "NA",
    }
    for line in output.splitlines():
        parts = line.upper().split()
        # Exact equality avoids Phy-ID1 matching Phy-ID12 and ignores headers.
        if (len(parts) < 2 or parts[0] != target
                or parts[1] not in relation_types):
            continue
        return not any(part in {"HCCS", "HCCS_SW"} for part in parts[1:])
    # Keep the established unknown-topology fallback.
    return False

# -*- coding: utf-8 -*-
"""Ascend 910C dual-chip rules. IDs come from observations, never arithmetic."""


class Ascend910CHandler(object):
    model = "910C"
    multi_chip = True

    @staticmethod
    def merge_basic_info(board, group):
        chip = group.chip_by_pci.get(board["pciAddress"])
        if chip is not None:
            # A warning board remains inventory, without usable chip metadata.
            if not chip.healthy:
                return dict(board)
            return chip.to_record(board.get("serialNumber"))

        # A chip1-only summary must not drop chip0 or double its memory.
        result = dict(board)
        peer_memory = next((
            peer.info.memory for peer in group.chips
            if peer.info.extra.get("physicalId") is not None
            and peer.info.memory
        ), None)
        if peer_memory:
            result["memory"] = peer_memory
        return result

    @staticmethod
    def get_metric_targets(group):
        # Warning chips still need monitoring. A missing chip0 uses the
        # existing board query until its chip metadata is available.
        chip_ids = sorted({
            chip.info.extra["chipId"] for chip in group.chips
            if chip.info.extra.get("physicalId") is not None
            and chip.info.extra.get("chipId") is not None
        }, key=int)
        if not chip_ids:
            return [None]
        return chip_ids if "0" in chip_ids else [None] + chip_ids

    @staticmethod
    def get_rank_table_ids(group):
        physical_ids = {
            str(info.get("physicalId")) for info in group.records
            if str(info.get("physicalId", "")).isdigit()
        }
        if physical_ids:
            return sorted(physical_ids, key=int)
        # Preserve the existing public API's NPU fallback when no physical
        # mapping is present (e.g. metadata supplied by an older caller).
        return [group.npu_id] if str(group.npu_id).isdigit() else []

    @staticmethod
    def get_isolation_chip_id(info):
        return info.get("chipId") if info.get("chipId") is not None else "0"

    @staticmethod
    def get_topology_target(npu_id, physical_id=None):
        if physical_id is None:
            return None
        return "PHY-ID%s" % physical_id

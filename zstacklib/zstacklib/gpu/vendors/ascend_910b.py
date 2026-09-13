# -*- coding: utf-8 -*-
"""Ascend 910B single-chip rules. No command execution or vendor registration."""


class Ascend910BHandler(object):
    model = "910B"
    multi_chip = False

    @staticmethod
    def merge_basic_info(board, group):
        chip = group.chip_by_pci.get(board["pciAddress"])
        if chip is None or not chip.healthy:
            return dict(board)
        return chip.to_record(board.get("serialNumber"))

    @staticmethod
    def get_metric_targets(group):
        # 910B queries stay at logical-NPU scope, without a chip selector.
        return [None]

    @staticmethod
    def get_rank_table_ids(group):
        return [group.npu_id] if str(group.npu_id).isdigit() else []

    @staticmethod
    def get_isolation_chip_id(info):
        return None

    @staticmethod
    def get_topology_target(npu_id, physical_id=None):
        return "NPU%s" % npu_id

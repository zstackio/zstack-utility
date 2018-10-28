'''

@author: lining
'''
import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import shell
from zstacklib.utils import log

logger = log.get_logger(__name__)

def getCephPoolsCapacity():
    result = []

    o = shell.call('ceph osd dump -f json')
    df = jsonobject.loads(o)
    if not df.pools:
        return result

    for pool in df.pools:
        poolCapacity = CephPoolCapacity(pool.pool_name, pool.size, pool.crush_ruleset)
        result.append(poolCapacity)

    # fill availableCapacity, usedCapacity
    o = shell.call('ceph df -f json')
    pools = jsonobject.loads(o).pools
    if not pools:
        return result
    for pool in pools:
        for poolCapacity in result:
            if pool.name == poolCapacity.poolName:
                poolCapacity.availableCapacity = pool.stats.max_avail
                poolCapacity.usedCapacity = pool.stats.bytes_used
                break

    # fill crushRuleItemName
    o = shell.call('ceph osd crush rule dump -f json')
    crushRules = jsonobject.loads(o)
    if not crushRules:
        return result
    for poolCapacity in result:
        crushRule = crushRules[poolCapacity.crushRuleSet]
        if not crushRule:
            continue
        for step in crushRule.steps:
            if step.op == "take":
                poolCapacity.crushRuleItemName = step.item_name
            break

    # fill crushItemOsds
    o = shell.call('ceph osd crush tree -f json')
    crushTrees = jsonobject.loads(o)
    if not crushTrees:
        return result
    for poolCapacity in result:
        if not poolCapacity.crushRuleItemName:
            continue
        for crush in crushTrees:
            if crush.name != poolCapacity.crushRuleItemName:
                continue
            for item in crush.items:
                if item.type != "host":
                    continue
                for i in item.items:
                    if i.type != "osd":
                        continue
                    poolCapacity.crushItemOsds.append(i.name)

    # fill crushItemOsdsTotalSize, poolTotalSize
    o = shell.call('ceph osd df -f json')
    osds = jsonobject.loads(o)
    if not osds.nodes:
        return result
    for poolCapacity in result:
        if not poolCapacity.crushItemOsds:
            continue
        for osdName in poolCapacity.crushItemOsds:
            for osd in osds.nodes:
                if osd.name != osdName:
                    continue
                poolCapacity.crushItemOsdsTotalSize = poolCapacity.crushItemOsdsTotalSize + osd.kb * 1024

        if poolCapacity.crushItemOsdsTotalSize != 0 and poolCapacity.replicatedSize != 0:
            poolCapacity.poolTotalSize = poolCapacity.crushItemOsdsTotalSize / poolCapacity.replicatedSize

    return result


class CephPoolCapacity:

    def __init__(self, poolName, replicatedSize, crushRuleSet):
        self.poolName = poolName
        self.replicatedSize = replicatedSize
        self.crushRuleSet = crushRuleSet
        self.availableCapacity = 0
        self.usedCapacity = 0
        self.crushRuleItemName = None
        self.crushItemOsds = []
        self.crushItemOsdsTotalSize = 0
        self.poolTotalSize = 0


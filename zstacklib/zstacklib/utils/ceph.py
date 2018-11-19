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
        crush_rule = None
        if pool.crush_ruleset is None:
            crush_rule = pool.crush_rule
        else:
            crush_rule = pool.crush_ruleset
        poolCapacity = CephPoolCapacity(pool.pool_name, pool.size, crush_rule)
        result.append(poolCapacity)

    # fill crushRuleItemName
    o = shell.call('ceph osd crush rule dump -f json')
    crushRules = jsonobject.loads(o)
    if not crushRules:
        return result
    for poolCapacity in result:
        if poolCapacity.crushRuleSet is None:
            continue

        def setCrushRuleName(crushRule):
            if not crushRule:
                return
            for step in crushRule.steps:
                if step.op == "take":
                    poolCapacity.crushRuleItemName = step.item_name

        [setCrushRuleName(crushRule) for crushRule in crushRules if crushRule.rule_id == poolCapacity.crushRuleSet]

    # fill crushItemOsds
    o = shell.call('ceph osd tree -f json')
    tree = jsonobject.loads(o)
    if not tree.nodes:
        return result
    for poolCapacity in result:
        if not poolCapacity.crushRuleItemName:
            continue
        for node in tree.nodes:
            if node.name != poolCapacity.crushRuleItemName:
                continue
            if not node.children:
                continue

            osdNodes = []
            for hostNodeId in node.children:
                def addOsdNodes(hostNode):
                    if hostNode.type != "host":
                        return
                    if not hostNode.children:
                        return
                    osdNodes.extend(hostNode.children)

                [addOsdNodes(hostNode) for hostNode in tree.nodes if hostNode.id == hostNodeId]

            if not osdNodes:
                continue
            for osdNodeId in osdNodes:
                def addOsd(osdNode):
                    if osdNode.type != "osd":
                        return
                    if osdNode.name in poolCapacity.crushItemOsds:
                        return
                    poolCapacity.crushItemOsds.append(osdNode.name)

                [addOsd(osdNode) for osdNode in tree.nodes if osdNode.id == osdNodeId]

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
                poolCapacity.availableCapacity = poolCapacity.availableCapacity + osd.kb_avail * 1024
                poolCapacity.usedCapacity = poolCapacity.usedCapacity + osd.kb_used * 1024

        if poolCapacity.crushItemOsdsTotalSize != 0 and poolCapacity.replicatedSize != 0:
            poolCapacity.poolTotalSize = poolCapacity.crushItemOsdsTotalSize / poolCapacity.replicatedSize
        if poolCapacity.availableCapacity != 0 and poolCapacity.replicatedSize != 0:
            poolCapacity.availableCapacity = poolCapacity.availableCapacity / poolCapacity.replicatedSize
        if poolCapacity.usedCapacity != 0 and poolCapacity.replicatedSize != 0:
            poolCapacity.usedCapacity = poolCapacity.usedCapacity / poolCapacity.replicatedSize

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


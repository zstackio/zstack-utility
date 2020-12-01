'''

@author: lining
'''
import os
import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import shell
from zstacklib.utils import log

logger = log.get_logger(__name__)


def is_xsky():
    return os.path.exists("/usr/bin/xms-cli")


def is_sandstone():
    return os.path.exists("/opt/sandstone/bin/sds")


def parseDfPools(pools):
    res = {}

    for pool in pools:
        if not pool.name: continue

        st = pool.stats
        if st and st.bytes_used and st.max_avail:
            res[pool.name] = (st.bytes_used, st.max_avail)

    return res

def getCephPoolsCapacity(pools):
    result = []
    poolDfDict = parseDfPools(pools)

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
    # In the open source Ceph 10 version, the value returned by executing 'ceph osd tree -f json' might have '-nan', causing json parsing to fail.
    o = o.replace("-nan", "\"\"")
    tree = jsonobject.loads(o)
    if not tree.nodes:
        return result

    def findNodeById(id):
        for node in tree.nodes:
            if node.id == id:
                return node

    def findAllChilds(node):
        childs = []

        if not node.children:
            return childs

        for childId in node.children:
            child = findNodeById(childId)
            if not child:
                continue
            childs.append(child)
            if child.children:
                grandson_childs = findAllChilds(child)
                childs.extend(grandson_childs)
        return childs

    for poolCapacity in result:
        if not poolCapacity.crushRuleItemName:
            continue
        for node in tree.nodes:
            if node.name != poolCapacity.crushRuleItemName:
                continue
            if not node.children:
                continue

            osdNodes = []
            nodes = findAllChilds(node)
            for node in nodes:
                if node.type != "osd":
                    continue
                if node.name in osdNodes:
                    continue
                osdNodes.append(node.name)
            poolCapacity.crushItemOsds = osdNodes

    # fill crushItemOsdsTotalSize, poolTotalSize
    o = shell.call('ceph osd df -f json')
    # In the open source Ceph 10 version, the value returned by executing 'ceph osd df -f json' might have '-nan', causing json parsing to fail.
    o = o.replace("-nan", "\"\"")
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

    for poolCapacity in result:
        try:
            bytes_used, max_avail = poolDfDict[poolCapacity.poolName]
            poolCapacity.usedCapacity = bytes_used
            poolCapacity.availableCapacity = max_avail
            poolCapacity.poolTotalSize = max_avail
        except KeyError:
            pass
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


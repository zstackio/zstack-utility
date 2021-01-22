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
    return os.path.exists("/opt/sandstone/bin/sds") or os.path.exists("/var/lib/ceph/bin/ceph")


def get_ceph_manufacturer():
    if is_xsky():
        return "xsky"
    elif is_sandstone():
        return "sandstone"
    else:
        return "open-source"


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

        if pool.type == 1:
            poolCapacity = CephPoolCapacity(pool.pool_name, pool.size, crush_rule)
        elif pool.type == 3:
            prof = shell.call('ceph osd erasure-code-profile get %s -f json' % pool.erasure_code_profile)
            jprof = jsonobject.loads(prof)
            if not jprof.k or not jprof.m:
                raise Exception('unexpected erasure-code-profile for pool: %s' % pool.pool_name)
            k = int(jprof.k)
            m = int(jprof.m)
            r = float(k+m)/k
            poolCapacity = CephPoolCapacity(pool.pool_name, pool.size, crush_rule, r)
        else:
            raise Exception("unexpected pool type: %s:%d" % (pool.pool_name, pool.type))

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

        r = poolCapacity.ecRedundancy if poolCapacity.ecRedundancy else poolCapacity.replicatedSize

        if poolCapacity.crushItemOsdsTotalSize != 0 and poolCapacity.replicatedSize != 0:
            poolCapacity.poolTotalSize = int(poolCapacity.crushItemOsdsTotalSize / r)
        if poolCapacity.availableCapacity != 0 and poolCapacity.replicatedSize != 0:
            poolCapacity.availableCapacity = int(poolCapacity.availableCapacity / r)
        if poolCapacity.usedCapacity != 0 and poolCapacity.replicatedSize != 0:
            poolCapacity.usedCapacity = int(poolCapacity.usedCapacity / r)

    return result


class CephPoolCapacity:

    def __init__(self, poolName, replicatedSize, crushRuleSet, ecRedundancy=None):
        self.poolName = poolName
        self.replicatedSize = replicatedSize
        self.ecRedundancy = ecRedundancy
        self.crushRuleSet = crushRuleSet
        self.availableCapacity = 0
        self.usedCapacity = 0
        self.crushRuleItemName = None
        self.crushItemOsds = []
        self.crushItemOsdsTotalSize = 0
        self.poolTotalSize = 0


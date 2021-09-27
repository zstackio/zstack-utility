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


def get_pools_capacity():
    result = []

    o = shell.call('ceph osd dump -f json')
    df = jsonobject.loads(o)
    if not df.pools:
        return result

    for pool in df.pools:
        crush_rule = pool.crush_ruleset if pool.crush_ruleset is not None else pool.crush_rule

        if pool.type == 1:
            pool_capacity = CephPoolCapacity(pool.pool_name, pool.size, crush_rule, "Copy", 1.0 / pool.size)
        elif pool.type == 3:
            prof = shell.call('ceph osd erasure-code-profile get %s -f json' % pool.erasure_code_profile)
            jprof = jsonobject.loads(prof)
            if not jprof.k or not jprof.m:
                raise Exception('unexpected erasure-code-profile for pool: %s' % pool.pool_name)
            k = int(jprof.k)
            m = int(jprof.m)
            utilization = float(k)/(k + m)
            pool_capacity = CephPoolCapacity(pool.pool_name, pool.size, crush_rule, "ErasureCode", utilization)
        else:
            raise Exception("unexpected pool type: %s:%d" % (pool.pool_name, pool.type))

        result.append(pool_capacity)

    # fill crush_rule_item_name
    o = shell.call('ceph osd crush rule dump -f json')
    crush_rules = jsonobject.loads(o)
    if not crush_rules:
        return result
    for pool_capacity in result:
        if pool_capacity.crush_rule_set is None:
            continue

        for crush_rule in crush_rules:
            if crush_rule.rule_id == pool_capacity.crush_rule_set:
                # set crush rule name
                for step in crush_rule.steps:
                    if step.op == "take":
                        pool_capacity.crush_rule_item_name = step.item_name

    # fill crush_item_osds
    o = shell.call('ceph osd tree -f json')
    # In the open source Ceph 10 version, the value returned by executing 'ceph osd tree -f json' might have '-nan', causing json parsing to fail.
    o = o.replace("-nan", "\"\"")
    tree = jsonobject.loads(o)
    if not tree.nodes:
        return result

    def find_node_by_id(id):
        for node in tree.nodes:
            if node.id == id:
                return node

    def find_all_childs(node):
        childs = []

        if not node.children:
            return childs

        for child_id in node.children:
            child = find_node_by_id(child_id)
            if not child:
                continue
            childs.append(child)
            if child.children:
                grandson_childs = find_all_childs(child)
                childs.extend(grandson_childs)
        return childs

    for pool_capacity in result:
        if not pool_capacity.crush_rule_item_name:
            continue
        for node in tree.nodes:
            if node.name != pool_capacity.crush_rule_item_name:
                continue
            if not node.children:
                continue

            osd_nodes = []
            nodes = find_all_childs(node)
            for node in nodes:
                if node.type != "osd":
                    continue
                if node.name in osd_nodes:
                    continue
                osd_nodes.append(node.name)
            pool_capacity.crush_item_osds = osd_nodes

    # fill crush_item_osds_total_size, poolTotalSize
    o = shell.call('ceph osd df -f json')
    # In the open source Ceph 10 version, the value returned by executing 'ceph osd df -f json' might have '-nan', causing json parsing to fail.
    o = o.replace("-nan", "\"\"")
    osds = jsonobject.loads(o)
    if not osds.nodes:
        return result
    for pool_capacity in result:
        if not pool_capacity.crush_item_osds:
            continue
        for osd_name in pool_capacity.crush_item_osds:
            for osd in osds.nodes:
                if osd.name != osd_name:
                    continue
                pool_capacity.crush_item_osds_total_size = pool_capacity.crush_item_osds_total_size + osd.kb * 1024
                pool_capacity.available_capacity = pool_capacity.available_capacity + osd.kb_avail * 1024
                pool_capacity.used_capacity = pool_capacity.used_capacity + osd.kb_used * 1024

        if not pool_capacity.disk_utilization:
            continue

        if pool_capacity.crush_item_osds_total_size:
            pool_capacity.pool_total_size = int(pool_capacity.crush_item_osds_total_size * pool_capacity.disk_utilization)
        if pool_capacity.available_capacity:
            pool_capacity.available_capacity = int(pool_capacity.available_capacity * pool_capacity.disk_utilization)
        if pool_capacity.used_capacity:
            pool_capacity.used_capacity = int(pool_capacity.used_capacity * pool_capacity.disk_utilization)

    return result


class CephPoolCapacity:
    def __init__(self, pool_name, replicated_size, crush_rule_set, security_policy, disk_utilization):
        # type: (str, int, str, str, float) -> None
        self.pool_name = pool_name
        self.replicated_size = replicated_size
        self.disk_utilization = disk_utilization
        self.security_policy = security_policy
        self.crush_rule_set = crush_rule_set
        self.available_capacity = 0
        self.used_capacity = 0
        self.crush_rule_item_name = None
        self.crush_item_osds = []
        self.crush_item_osds_total_size = 0
        self.pool_total_size = 0


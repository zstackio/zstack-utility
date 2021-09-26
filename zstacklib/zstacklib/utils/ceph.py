'''

@author: lining
'''
import os
import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import linux
import rbd

logger = log.get_logger(__name__)

CEPH_CONF_ROOT = "/var/lib/zstack/ceph"
CEPH_KEYRING_CONFIG_NAME = 'client.zstack.keyring'


def get_fsid(conffile='/etc/ceph/ceph.conf'):
    import rados
    with rados.Rados(conffile=conffile) as cluster:
        return cluster.get_fsid()


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


def get_ceph_client_conf(ps_uuid, manufacturer=None):
    ceph_client_config_dir = os.path.join(CEPH_CONF_ROOT, ps_uuid)

    # xsky use admin to access mon node
    # other ceph storages for example open-source uses client.zstack to access mon node
    username = None
    if manufacturer != "xsky":
        username = "client.zstack"

    key_path = os.path.join(ceph_client_config_dir, CEPH_KEYRING_CONFIG_NAME)
    # set key_path to None if no keyring config file exists
    if not os.path.exists(key_path):
        key_path = None

    return os.path.join(ceph_client_config_dir, "ceph.conf"), key_path, username

def update_ceph_client_access_conf(ps_uuid, mon_urls, user_key, manufacturer, fsid):
    conf_folder = os.path.join(CEPH_CONF_ROOT, ps_uuid)
    if not os.path.exists(conf_folder):
        linux.mkdir(conf_folder)

    conf_content = '[global]\nfsid = %s\nmon_host=%s\n' % (fsid, ','.join(mon_urls))

    # key used for ceph client keyring configuration
    keyring_path = None
    username = None
    if user_key:
        keyring_content = None
        # xsky keyring file just contains the keyring string
        # but other ceph storages used keyring file is format
        # as following:
        # [client.zstack]
        #     key = your user key for client.zstack
        if manufacturer == "xsky":
            keyring_content = user_key
        else:
            username = "client.zstack"
            keyring_content = """[client.zstack]
    key = %s
""" % user_key
        keyring_path = os.path.join(conf_folder, CEPH_KEYRING_CONFIG_NAME)
        with open(keyring_path, 'w') as fd:
            fd.write(keyring_content)

        conf_content = conf_content + "keyring=%s" % keyring_path

    conf_path = os.path.join(conf_folder, "ceph.conf")
    with open(conf_path, 'w') as fd:
        fd.write(conf_content)
            
    return conf_path, keyring_path, username


def get_heartbeat_object_name(ioctx, primary_storage_uuid, host_uuid):
    image = None
    try:
        logger.debug("try to get image block name prefix of host:%s" % host_uuid)
        image = rbd.Image(ioctx, get_heartbeat_file_name(primary_storage_uuid, host_uuid))
        block_name = image.stat()['block_name_prefix']
        logger.debug("get image block name prefix:%s of host:%s" % (block_name, host_uuid))
        return block_name
    except Exception as e:
        logger.debug("failed to open image, %s", e)
    finally:
        if image:
            image.close()


def get_heartbeat_volume(pool_name, ps_uuid, host_uuid):
    return '%s/ceph-ps-%s-host-hb-%s' % (pool_name, ps_uuid, host_uuid)

def get_heartbeat_file_name(ps_uuid, host_uuid):
    return 'ceph-ps-%s-host-hb-%s' % (ps_uuid, host_uuid)

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


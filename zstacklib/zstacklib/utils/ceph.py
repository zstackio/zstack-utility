'''

@author: lining
'''
import os

import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import remoteStorage
from zstacklib.utils.bash import bash_r
from zstacklib.utils.linux import get_fs_type, check_nbd
from zstacklib.utils.zstone import ZStoneCephPoolCapacityGetter

logger = log.get_logger(__name__)

CEPH_CONF_ROOT = "/var/lib/zstack/ceph"
CEPH_KEYRING_CONFIG_NAME = 'client.zstack.keyring'
CEPH_MON_PROTOCOL_PREFIX = 'v'
CEPH_MON_PROTOCOL_SEPARATOR = ':'
CEPH_MON_ADDR_SUFFIX_SEPARATOR = '/'
CEPH_MON_IPV6_BRACKET_PREFIX = '['
CEPH_MON_IPV6_BRACKET_SUFFIX = ']'
ROUTE_PROTOCOL_KERNEL = 'kernel'
ROUTE_MATCH_CMD_FORMAT = "ip route | grep -w '%s' > /dev/null"
ROUTE_KERNEL_MATCH_CMD_FORMAT = 'ip route | grep -w "proto kernel" | grep -w \'%s\' > /dev/null'
IPV6_ROUTE_MATCH_CMD_FORMAT = "ip -6 route | grep -w '%s' > /dev/null"
IPV6_ROUTE_KERNEL_MATCH_CMD_FORMAT = "ip -6 route get '%s' | grep -E '^local[[:space:]]' > /dev/null"

QEMU_NBD_SOCKET_DIR = "/var/lock/"
QEMU_NBD_SOCKET_PREFIX = "qemu-nbd-nbd"
NBD_DEV_PREFIX = "/dev/nbd"
SUPPORT_DEFER_DELETING = None
from zstacklib.utils.version import NumericVersion

def get_fsid(conffile='/etc/ceph/ceph.conf'):
    import rados
    with rados.Rados(conffile=conffile) as cluster:
        return cluster.get_fsid()


def is_xsky():
    return os.path.exists("/usr/bin/xms-cli")


def is_sandstone():
    return os.path.exists("/opt/sandstone/bin/sds") or os.path.exists("/var/lib/ceph/bin/ceph")

def support_defer_deleting():
    global SUPPORT_DEFER_DELETING
    if SUPPORT_DEFER_DELETING is None:
        SUPPORT_DEFER_DELETING = bash.bash_r("rbd help trash list") == 0
    return SUPPORT_DEFER_DELETING

def get_defer_deleting_options(cmd):
    help_info = shell.call("rbd help trash mv")
    opts = ''
    if "--expires-at" in help_info:
        opts += "--expires-at '%s seconds'" % cmd.expirationTime
    elif "--delay" in help_info:
        opts += "--delay %s" % cmd.expirationTime

    return opts

def find_rbd_trash(trash_list, image_name):
    return next((t for t in trash_list if image_name in (t.get("id"), t.get("name"))), None)

def rbd_children(path):
    children = bash.bash_o('rbd children %s' % path)
    if not children:
        return []
    return [c.strip() for c in children.splitlines() if c.strip()]

def rbd_trash_list(pool_name):
    ret, stdout, stderr = bash.bash_roe("rbd trash list -p %s --format json" % pool_name)
    if ret != 0 or not stdout or not stdout.strip():
        return ret, [], stderr

    entries = jsonobject.loads(stdout)
    if not entries:
        return ret, [], stderr

    if isinstance(entries[0], str):
        trash_list = [{"id": entries[i], "name": entries[i + 1] if i + 1 < len(entries) else entries[i]}
                      for i in range(0, len(entries), 2)]
    else:
        trash_list = [{"id": e.id, "name": e.name} for e in entries]
    return ret, trash_list, stderr

def rbd_trash_rm(pool_name, trash_id, force=False):
    cmd = "rbd trash rm %s/%s" % (pool_name, trash_id)
    if force:
        cmd += " --force"
    return bash.bash_roe(cmd)

def is_zstone():
    return os.path.exists("/opt/zstone/bin/zstnlet")


def get_ceph_manufacturer():
    if is_xsky():
        return "xsky"
    elif is_sandstone():
        return "sandstone"
    elif is_zstone():
        return "zstone"
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

        #add \n because of ZSTAC-43092
        conf_content = conf_content + "keyring=%s\n" % keyring_path

    conf_path = os.path.join(conf_folder, "ceph.conf")
    with open(conf_path, 'w') as fd:
        fd.write(conf_content)

    return conf_path, keyring_path, username


def get_heartbeat_object_name(primary_storage_uuid, host_uuid):
    return 'ceph-ps-%s-host-hb-%s' % (primary_storage_uuid, host_uuid)


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
                        pool_capacity.crush_rule_item_names.append(step.item_name)

    # fill crush_item_osds
    has_shadow = any(
        name and '~' in name
        for pool_capacity in result
        for name in pool_capacity.crush_rule_item_names
    )
    if has_shadow:
        o = shell.call('ceph osd crush tree --show-shadow -f json')
    else:
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
        if not pool_capacity.crush_rule_item_names:
            continue

        osd_nodes = set()
        for node in tree.nodes:
            if node.name not in pool_capacity.crush_rule_item_names:
                continue
            if not node.children:
                continue

            nodes = find_all_childs(node)
            for node in nodes:
                if node.type != "osd":
                    continue
                osd_nodes.add(node.name)
        pool_capacity.crush_item_osds = sorted(osd_nodes)

    # fill osds capacity
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
                pool_capacity.related_osd_capacity.update({osd_name : CephOsdCapacity(osd.kb * 1024, osd.kb_avail * 1024, osd.kb_used * 1024)})

    pool_capacity_getter_mapping.get(get_ceph_manufacturer(), DefaultCephPoolCapacityGetter()).fill_pool_capacity(result)
    return result


class CephOsdCapacity:
    def __init__(self, crush_item_osd_size, crush_item_osd_available_capacity, crush_item_osd_used_capacity):
        self.size = crush_item_osd_size
        self.availableCapacity = crush_item_osd_available_capacity
        self.usedCapacity = crush_item_osd_used_capacity

    def get_size(self):
        return self.size

    def get_available_capacity(self):
        return self.availableCapacity

    def get_used_capacity(self):
        return self.usedCapacity


def strip_mon_addr_protocol(addr):
    protocol, separator, rest = addr.partition(CEPH_MON_PROTOCOL_SEPARATOR)
    if separator and protocol.startswith(CEPH_MON_PROTOCOL_PREFIX) and protocol[1:].isdigit():
        return rest
    return addr


def extract_mon_host(addr):
    if not addr:
        return None

    addr = strip_mon_addr_protocol(addr.strip())
    if addr.startswith(CEPH_MON_IPV6_BRACKET_PREFIX):
        end = addr.find(CEPH_MON_IPV6_BRACKET_SUFFIX)
        if end > 0:
            return addr[1:end]
        return addr[1:]

    has_addr_suffix = CEPH_MON_ADDR_SUFFIX_SEPARATOR in addr
    addr_without_suffix = addr.split(CEPH_MON_ADDR_SUFFIX_SEPARATOR, 1)[0]
    if CEPH_MON_PROTOCOL_SEPARATOR not in addr_without_suffix:
        return addr_without_suffix

    host, separator, port = addr_without_suffix.rpartition(CEPH_MON_PROTOCOL_SEPARATOR)
    if addr_without_suffix.count(CEPH_MON_PROTOCOL_SEPARATOR) == 1:
        return host
    if has_addr_suffix and separator and port.isdigit():
        return host
    return addr_without_suffix


def get_route_match_cmd(addr, route_protocol=None):
    if CEPH_MON_PROTOCOL_SEPARATOR in addr:
        route_match_cmd_format = IPV6_ROUTE_MATCH_CMD_FORMAT
        route_kernel_match_cmd_format = IPV6_ROUTE_KERNEL_MATCH_CMD_FORMAT
    else:
        route_match_cmd_format = ROUTE_MATCH_CMD_FORMAT
        route_kernel_match_cmd_format = ROUTE_KERNEL_MATCH_CMD_FORMAT

    if route_protocol is None:
        return route_match_cmd_format % addr
    if route_protocol == ROUTE_PROTOCOL_KERNEL:
        return route_kernel_match_cmd_format % addr
    return ''


def get_mon_addr(monmap, route_protocol=None):
    for mon in jsonobject.loads(monmap).mons:
        addr = extract_mon_host(mon.addr)
        if addr is None or not linux.is_valid_address(addr):
            continue

        cmd = get_route_match_cmd(addr, route_protocol)
        if cmd == '':
            return
        if bash_r(cmd) == 0:
            return addr


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
        self.crush_rule_item_names = []
        self.crush_item_osds = []
        self.crush_item_osds_total_size = 0
        self.pool_total_size = 0
        self.related_osd_capacity = {} # type: dict[str, CephOsdCapacity]


    def get_related_osds(self):
        return ",".join(self.crush_item_osds)


class NbdRemoteStorage(remoteStorage.RemoteStorage):
    def __init__(self, volume_install_path, mount_path, volume_mounted_device, ps_uuid=None):
        super(NbdRemoteStorage, self).__init__(mount_path, volume_mounted_device)
        self.normalize_install_path = volume_install_path.replace('ceph://', '')
        self.ps_uuid = ps_uuid
        self.nbd_dev = None
        self.cmd = None
        self.POOL_NAME = 1
        self.IMAGE = 2
        self.DEVICE = 4

    @staticmethod
    def check_nbd_dev_empty(nbd_id):
        with open('/sys/block/nbd{}/size'.format(nbd_id), 'r') as f:
            size = f.read()
        if int(size) > 0:
            return False
        return True

    def get_available_nbd_dev(self):
        block_devices = os.listdir('/sys/block/')
        all_nbd_ids = []
        for dev in block_devices:
            if dev.startswith('nbd'):
                all_nbd_ids.append(int(dev.split('nbd')[-1]))
        available_nbd_ids = sorted(set(all_nbd_ids))
        if not available_nbd_ids:
            raise Exception('can not find available nbd device. try increase `nbds_max` param during modprobe nbd')
        for nbd_id in available_nbd_ids:
            if self.check_nbd_dev_empty(nbd_id):
                return NBD_DEV_PREFIX + str(nbd_id)

    def get_cmd(self):
        self.nbd_dev = self.get_available_nbd_dev()
        conf_path, _, username = get_ceph_client_conf(self.ps_uuid, get_ceph_manufacturer())
        if username is not None:
            name = username.split(".")[-1]
            self.cmd = 'qemu-nbd -f raw -c %s rbd:%s:id=%s:conf=%s' % (
                self.nbd_dev, self.normalize_install_path, name, conf_path)
        else:
            self.cmd = 'qemu-nbd -f raw -c %s rbd:%s:conf=%s' % (
                self.nbd_dev, self.normalize_install_path, conf_path)

    def qemu_nbd_socket_is_exists(self, qemu_nbd_socket):
        for nbd_socket in os.listdir(QEMU_NBD_SOCKET_DIR):
            if qemu_nbd_socket == nbd_socket:
                return self.volume_mounted_device
        return None

    def build_qemu_nbd_socket_name(self):
        nbd_id = self.volume_mounted_device.split(NBD_DEV_PREFIX)[-1]
        return QEMU_NBD_SOCKET_PREFIX + str(nbd_id)

    def do_mount(self, fstype=None):
        try:
            check_nbd()
            self.get_cmd()
            shell.call(self.cmd)
            if fstype is not None:
                shell.call('mkfs -F -t %s %s' % (fstype, self.nbd_dev))
            linux.mount(self.nbd_dev, self.mount_path)
        except Exception as e:
            if self.nbd_dev is not None:
                shell.call('qemu-nbd -d %s' % self.nbd_dev)
            raise e
        return self.nbd_dev

    def mount(self):
        if self.volume_mounted_device is not None:
            cmd = shell.ShellCmd("mountpoint %s" % self.mount_path)
            cmd(is_exception=False)
            if cmd.return_code == 0:
                return self.volume_mounted_device
            if self.qemu_nbd_socket_is_exists(self.build_qemu_nbd_socket_name()) is not None:
                linux.mount(self.volume_mounted_device, self.mount_path)
                return self.volume_mounted_device
            else:
                return self.do_mount()

        if not os.path.isdir(self.mount_path):
            linux.mkdir(self.mount_path)

        fstype = get_fs_type(self.mount_path)
        return self.do_mount(fstype)

    def umount(self):
        device_and_mount_path = bash.bash_o("mount | grep %s" % self.mount_path)
        if len(device_and_mount_path) != 0:
            shell.call('umount -f %s' % self.mount_path)
        shell.call("qemu-nbd -d %s" % self.volume_mounted_device)

class DefaultCephPoolCapacityGetter:
    def fill_pool_capacity(self, result):
        for pool_capacity in result:
            if not pool_capacity.related_osd_capacity:
                continue
            for osd_capacity in list(pool_capacity.related_osd_capacity.values()):
                pool_capacity.crush_item_osds_total_size = pool_capacity.crush_item_osds_total_size + osd_capacity.get_size()
                pool_capacity.available_capacity = pool_capacity.available_capacity + osd_capacity.get_available_capacity()
                pool_capacity.used_capacity = pool_capacity.used_capacity + osd_capacity.get_used_capacity()

            if not pool_capacity.disk_utilization:
                continue

            if pool_capacity.crush_item_osds_total_size:
                pool_capacity.pool_total_size = int(pool_capacity.crush_item_osds_total_size * pool_capacity.disk_utilization)
            if pool_capacity.available_capacity:
                pool_capacity.available_capacity = int(pool_capacity.available_capacity * pool_capacity.disk_utilization)
            if pool_capacity.used_capacity:
                pool_capacity.used_capacity = int(pool_capacity.used_capacity * pool_capacity.disk_utilization)

pool_capacity_getter_mapping = {
    "zstone":ZStoneCephPoolCapacityGetter()
}

ceph_version = ""
def get_version():
    global ceph_version
    if ceph_version:
        return ceph_version
    ceph_version = shell.call("ceph version").split(" ")[2]
    return ceph_version

def rbd_create_support_byte():
    # ceph hammer not support in bytes
    return get_ceph_manufacturer() != "open-source" or NumericVersion(get_version()) >= NumericVersion("10.0.0")

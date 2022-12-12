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

logger = log.get_logger(__name__)

CEPH_CONF_ROOT = "/var/lib/zstack/ceph"
CEPH_KEYRING_CONFIG_NAME = 'client.zstack.keyring'

QEMU_NBD_SOCKET_DIR = "/var/lock/"
QEMU_NBD_SOCKET_PREFIX = "qemu-nbd-nbd"
NBD_DEV_PREFIX = "/dev/nbd"

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

    # fill crush_item_osds_total_size, poolTotalSize
    o = shell.call('ceph osd df -f json')
    # In the open source Ceph 10 version, the value returned by executing 'ceph osd df -f json' might have '-nan', causing json parsing to fail.
    o = o.replace("-nan", "\"\"")
    manufacturer = get_ceph_manufacturer()
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
                if manufacturer == "open-source":
                    pool_capacity.related_osd_capacity.update({osd_name : CephOsdCapacity(osd.kb * 1024, osd.kb_avail * 1024, osd.kb_used * 1024)})

        if not pool_capacity.disk_utilization:
            continue

        if pool_capacity.crush_item_osds_total_size:
            pool_capacity.pool_total_size = int(pool_capacity.crush_item_osds_total_size * pool_capacity.disk_utilization)
        if pool_capacity.available_capacity:
            pool_capacity.available_capacity = int(pool_capacity.available_capacity * pool_capacity.disk_utilization)
        if pool_capacity.used_capacity:
            pool_capacity.used_capacity = int(pool_capacity.used_capacity * pool_capacity.disk_utilization)

    return result


def get_mon_addr(monmap, route_protocol):
    for mon in jsonobject.loads(monmap).mons:
        ADDR = mon.addr.split(':')[0]
        cmd = ''
        if route_protocol is None:
            cmd = 'ip route | grep -w {{ADDR}} > /dev/null'
        elif route_protocol == "kernel":
            cmd = 'ip route | grep -w "proto kernel" | grep -w {{ADDR}} > /dev/null'
        if cmd == '':
            return
        if bash_r(cmd) == 0:
            return ADDR


class CephOsdCapacity:
    def __init__(self, crush_item_osd_size, crush_item_osd_available_capacity, crush_item_osd_used_capacity):
        self.size = crush_item_osd_size
        self.availableCapacity = crush_item_osd_available_capacity
        self.usedCapacity = crush_item_osd_used_capacity


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
        self.related_osd_capacity = {}


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

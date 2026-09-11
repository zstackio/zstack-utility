__author__ = 'Xingwei Yu'

from collections import defaultdict
import os
import time
from zstacklib.utils.version import NumericVersion

import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import form

from zstacklib.utils.bash import *

logger = log.get_logger(__name__)

ZBSADM_BIN_PATH = "/usr/local/bin/zbsadm"
ZBS_BIN_PATH = "/usr/bin/zbs"
ZBS_CLIENT_CONF_PATH = "/etc/zbs/client.conf"
ZBS_USER_NAME = "zbs"
STRIPE_VOLUME_COUNT = 64
STRIPE_VOLUME_UINT = "64KiB"
CLONAL_FLAG = 5
CBD_PREFIX = "cbd"
CBD_VOLUME_PATH = CBD_PREFIX + ":{}/{}/{}"
CBD_SNAPSHOT_PATH = CBD_VOLUME_PATH + "@{}"
CLUSTER_UUID_SUPPORTED_VERSION = "1.5.1"
VHOST_SOCKET_DIR = "/var/zbsvhost/sockets"
VHOST_VOLUME_SUFFIX = "_zbs_"
VHOST_TARGET_CONTAINER_PREFIX = "zbsvhost-"
VHOST_ADMIN_SOCK_NAME = "admin.sock"
VHOST_DEPLOY_READY_RETRIES = 40
VHOST_DEPLOY_READY_INTERVAL_SECONDS = 0.5
DEFAULT_VHOST_TARGET_HUGEPAGE_DIR = "/dev/hugepages2m"
DEFAULT_VHOST_TARGET_CPU_COUNT = 4
VHOST_CPU_TOPOLOGY_CMD = "LC_ALL=C lscpu --online -e=CPU,NODE,SOCKET,CORE"


class ClientInfo(object):
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port


def is_clonal_type(file_type):
    return file_type == CLONAL_FLAG


def parse_cbd_path(path):
    parts = path.split(":")[1].split("/")
    physical_pool = parts[0]
    logical_pool = parts[1]
    volume_part = parts[2]
    if "@" in volume_part:
        volume, snapshot = volume_part.split("@")
    else:
        volume = volume_part
        snapshot = None
    return physical_pool, logical_pool, volume, snapshot


"""
ZBS Storage UUID Output Behavior:
--------------------------------
< v1.5.1        : UUID output NOT SUPPORTED
v1.5.1 ~ v1.6.0 : UUID output enabled but returns status code 1 (ERROR)
> v1.6.0        : Fixed to return status code 0 (SUCCESS)
c.f. http://jira.zstack.io/browse/ZBS-327
"""


@in_bash
def get_cluster_uuid(cluster_version):
    if cluster_version and NumericVersion(cluster_version) < NumericVersion(CLUSTER_UUID_SUPPORTED_VERSION):
        return None

    _, o, _ = bash_roe("%s cluster ls --format json" % ZBSADM_BIN_PATH)
    r = jsonobject.loads(o)
    if r.error.code != 0:
        raise ValueError("failed to get cluster info, error[%s]" % r.error.message)

    return r.clusters[0].UUId


def get_version():
    return shell.call("%s --version | awk '{print $2}'" % ZBS_BIN_PATH).strip()


def deploy_client(ip, port, username, password):
    return shell.call("%s client deploy --host %s --port %s -u %s -p %s --silent" % (
        ZBSADM_BIN_PATH, ip, port, username, linux.shellquote(password)))


def _select_vhost_cpus(topology):
    numa_nodes = defaultdict(list)
    for cpu_topology in topology:
        numa_nodes[cpu_topology[1]].append(cpu_topology)

    selected_node = max(
        numa_nodes.values(),
        key=lambda cpus: (len(cpus), max(cpu[0] for cpu in cpus)))
    physical_cores = defaultdict(list)
    for cpu, _, socket, core in selected_node:
        physical_cores[(socket, core)].append(cpu)

    selected = []
    core_groups = sorted(physical_cores.values(), key=max, reverse=True)
    for siblings in core_groups[:DEFAULT_VHOST_TARGET_CPU_COUNT]:
        selected.append(max(siblings))

    if len(selected) < DEFAULT_VHOST_TARGET_CPU_COUNT:
        remaining = sorted(
            (cpu[0] for cpu in selected_node if cpu[0] not in selected),
            reverse=True)
        selected.extend(remaining[:DEFAULT_VHOST_TARGET_CPU_COUNT - len(selected)])
    return sorted(selected)


def vhost_auto_cpuset(ip, port, username, password):
    ret, out, err = linux.sshpass_run(
        ip, password, VHOST_CPU_TOPOLOGY_CMD, user=username, port=int(port))
    if ret != 0:
        detail = (err or "").strip() or (out or "").strip() or "no command output"
        raise Exception("failed to query vhost CPU topology on host[%s], exit code[%s]: %s" %
                        (ip, ret, detail))

    try:
        topology = [tuple(int(row[key]) for key in ("CPU", "NODE", "SOCKET", "CORE"))
                    for row in form.load(out)]
        cpus = _select_vhost_cpus(topology)
    except (KeyError, TypeError, ValueError) as error:
        raise Exception("failed to select vhost CPUs on host[%s]: %s" % (ip, error))
    return "[%s]" % ",".join(str(cpu) for cpu in cpus)


def find_2m_hugetlbfs_mount(ip, port, username, password):
    cmd = "findmnt -rn -t hugetlbfs -o TARGET,OPTIONS | awk '\\$2 ~ /(^|,)pagesize=2M(,|$)/ {print \\$1; exit}'"
    ret, out, err = linux.sshpass_run(ip, password, cmd, user=username, port=int(port))
    if ret != 0:
        raise Exception("failed to find 2M hugetlbfs mount on host[%s]: %s" % (ip, err))
    return out.strip() if out else None


def ensure_2m_hugetlbfs_mount(ip, port, username, password, mount_dir=DEFAULT_VHOST_TARGET_HUGEPAGE_DIR):
    existing = find_2m_hugetlbfs_mount(ip, port, username, password)
    if existing:
        return existing

    quoted_mount_dir = linux.shellquote(mount_dir)
    cmd = "mkdir -p %s && mount -t hugetlbfs -o pagesize=2M none %s" % (
        quoted_mount_dir, quoted_mount_dir)
    ret, _, err = linux.sshpass_run(ip, password, cmd, user=username, port=int(port))
    if ret != 0:
        raise Exception("failed to mount 2M hugetlbfs on host[%s], dir[%s]: %s" % (ip, mount_dir, err))
    return mount_dir


def deploy_vhost(ip, port, username, password, cpuset=None, hugepage_size=None, hugepage_dir=None):
    if not cpuset:
        cpuset = vhost_auto_cpuset(ip, port, username, password)
    if not hugepage_dir:
        hugepage_dir = ensure_2m_hugetlbfs_mount(ip, port, username, password)
    cmd = "%s vhost deploy --host %s --cpuset %s --silent" % (ZBSADM_BIN_PATH, ip, linux.shellquote(cpuset))
    if hugepage_size:
        cmd += " --hugepage-size %s" % hugepage_size
    if hugepage_dir:
        cmd += " --hugepage-dir %s" % hugepage_dir
    return shell.call(cmd)


def wait_vhost_target_ready(ip, port, username, password, retries=VHOST_DEPLOY_READY_RETRIES,
                            interval=VHOST_DEPLOY_READY_INTERVAL_SECONDS):
    container_name = VHOST_TARGET_CONTAINER_PREFIX + ip
    control_sock = "%s/%s" % (VHOST_SOCKET_DIR, VHOST_ADMIN_SOCK_NAME)
    cmd = "docker ps --filter %s --filter status=running -q | grep -q . && test -S %s" % (
        linux.shellquote("name=^/%s$" % container_name),
        linux.shellquote(control_sock))

    for _ in range(retries):
        ret, _, _ = linux.sshpass_run(ip, password, cmd, user=username, port=int(port))
        if ret == 0:
            return True
        time.sleep(interval)

    return False


def destroy_vhost(ip, port, username, password):
    return shell.call("%s vhost destroy --host %s --silent" % (ZBSADM_BIN_PATH, ip))


def create_vhost_bdev(ip, port, username, password, logical_pool, volume, bdev_name):
    return shell.call(
        "%s vhost create-bdev --host %s --volume %s/%s%s --name %s --silent" % (
            ZBSADM_BIN_PATH, ip, logical_pool, volume, VHOST_VOLUME_SUFFIX, bdev_name))


def delete_vhost_bdev(ip, port, username, password, bdev_name):
    return shell.call("%s vhost delete-bdev --host %s --name %s --silent" % (ZBSADM_BIN_PATH, ip, bdev_name))


def vhost_socket_path(bdev_name):
    return VHOST_SOCKET_DIR + "/" + bdev_name


def query_mds_status_info():
    return shell.call("%s status mds --format json" % ZBS_BIN_PATH)


def query_logical_pool_info():
    return shell.call("%s list logical-pool --format json" % ZBS_BIN_PATH)


def query_volume_info(logical_pool, volume):
    return shell.call("%s query file --path %s/%s --format json" % (ZBS_BIN_PATH, logical_pool, volume))


def query_volumes_in_logical_pool(logical_pool_name):
    return shell.call("%s list file --pool %s --format json" % (ZBS_BIN_PATH, logical_pool_name))


def query_children_volume(logical_pool, volume, snapshot, is_snapshot=False):
    if is_snapshot:
        return shell.call("%s children --snappath %s/%s@%s --user %s --format json" % (
            ZBS_BIN_PATH, logical_pool, volume, snapshot, ZBS_USER_NAME))
    else:
        return shell.call(
            "%s children --path %s/%s --user %s --format json" % (ZBS_BIN_PATH, logical_pool, volume, ZBS_USER_NAME))


def is_support_get_volume_clients():
    return shell.run("%s list client --help | grep -E '\--path'" % ZBS_BIN_PATH) == 0

def is_volume_exist(logical_pool, volume):
    o = query_volume_info(logical_pool, volume)
    ret = jsonobject.loads(o)
    if ret.error.code != 0:
        match = re.search(r"status code:\s*(\w+)", ret.error.message)
        if match and match.group(1) == "kFileNotExists":
            return False
        raise Exception('failed to query volume[%s/%s] info, error[%s]' % (logical_pool, volume, ret.error.message))
    return True
        

def get_volume_clients(logical_pool, volume):
    o = shell.call("%s list client --path %s/%s --format json" % (ZBS_BIN_PATH, logical_pool, volume))
    r = jsonobject.loads(o)
    if r.error.code != 0:
        raise Exception('failed to get volume[%s/%s] clients, error[%s]' % (logical_pool, volume, r.error.message))

    clients = []
    for ret in r.result:
        clients.append(ClientInfo(ret.ip, ret.port))

    return clients


def query_snapshot_info(logical_pool, volume):
    return shell.call("%s list snapshot --path %s/%s --format json" % (ZBS_BIN_PATH, logical_pool, volume))


def get_physical_pool_name(logical_pool):
    o = query_logical_pool_info()
    r = jsonobject.loads(o)
    if r.error.code != 0:
        raise Exception('failed to get logical pool[%s] info, error[%s]' % (logical_pool, r.error.message))

    physical_pool_name = ""
    for ret in r.result:
        for lp in ret.logicalPoolInfos:
            if logical_pool in lp.logicalPoolName:
                physical_pool_name = lp.physicalPoolName
                break

    if physical_pool_name is None:
        raise Exception('cannot found logical pool[%s], you must create it manually' % logical_pool)

    return physical_pool_name


def create_volume(logical_pool, volume, size, unit):
    return shell.call(
        "%s create file --path %s/%s --size %s%s --stripecount %d --stripeunit %s --user %s --format json" % (
            ZBS_BIN_PATH, logical_pool, volume, size, unit, STRIPE_VOLUME_COUNT, STRIPE_VOLUME_UINT, ZBS_USER_NAME))


@linux.retry(times=30, sleep_time=5)
def delete_volume_and_snapshots(logical_pool, volume):
    o = query_volume_info(logical_pool, volume)
    r = jsonobject.loads(o)
    if r.error.code != 0:
        return

    o = query_snapshot_info(logical_pool, volume)
    r = jsonobject.loads(o)
    if r.error.code != 0:
        return
    if r.result and r.result.hasattr('fileInfo'):
        delete_snapshots(logical_pool, volume, r.result.fileInfo)

    shell.call("%s delete file --path %s/%s" % (ZBS_BIN_PATH, logical_pool, volume))


def clone_volume(logical_pool, volume, snapshot, dst_volume):
    return shell.call("%s clone --snappath %s/%s@%s --dstpath %s/%s --user %s --format json" % (
        ZBS_BIN_PATH, logical_pool, volume, snapshot, logical_pool, dst_volume, ZBS_USER_NAME))


def expand_volume(logical_pool, volume, size, unit):
    return shell.call("%s update file --path %s/%s --size %s%s --user %s --format json" % (
        ZBS_BIN_PATH, logical_pool, volume, size, unit, ZBS_USER_NAME))


def flatten_volume(logical_pool, volume):
    return shell.call("%s flatten --path %s/%s --format json" % (ZBS_BIN_PATH, logical_pool, volume))


def create_snapshot(logical_pool, volume, snapshot):
    return shell.call("%s create snapshot --snappath %s/%s@%s --user %s --format json" % (
        ZBS_BIN_PATH, logical_pool, volume, snapshot, ZBS_USER_NAME))


def delete_snapshots(logical_pool, volume, file_infos):
    for file_info in file_infos:
        o = query_children_volume(logical_pool, volume, file_info.fileName, True)
        r = jsonobject.loads(o)
        if r.error.code != 0:
            raise Exception('failed to list children of [%s/%s@%s], error[%s]' % (
                logical_pool, volume, file_info.fileName, r.error.message))
        if r.result.hasattr('fileNames'):
            raise Exception('the snapshot[%s/%s@%s] is still in used' % (logical_pool, volume, file_info.fileName))

        is_protected = file_info.isProtected if file_info.hasattr('isProtected') else False
        if is_protected:
            o = unprotect_snapshot(logical_pool, volume, file_info.fileName)
            r = jsonobject.loads(o)
            if r.error.code != 0:
                raise Exception('failed to unprotect snapshot[%s/%s@%s], error[%s]' % (
                    logical_pool, volume, file_info.fileName, r.error.message))

        shell.call("%s delete snapshot --snappath %s/%s@%s --format json" % (
            ZBS_BIN_PATH, logical_pool, volume, file_info.fileName))


def protect_snapshot(logical_pool, volume, snapshot):
    return shell.call("%s protect --snappath %s/%s@%s" % (ZBS_BIN_PATH, logical_pool, volume, snapshot))


def unprotect_snapshot(logical_pool, volume, snapshot):
    return shell.call("%s unprotect --snappath %s/%s@%s --format json" % (ZBS_BIN_PATH, logical_pool, volume, snapshot))


def rollback_snapshot(logical_pool, volume, snapshot):
    return shell.call("%s rollback --snappath %s/%s@%s --format json" % (ZBS_BIN_PATH, logical_pool, volume, snapshot))


def cbd_to_nbd(desc, port, install_path):
    cmd = "qemu-nbd -D %s -f raw -p %d --fork %s_%s_:%s" % (
        desc, port, install_path, ZBS_USER_NAME, ZBS_CLIENT_CONF_PATH)
    logger.debug(cmd)
    os.system(cmd)


def copy(src_path, dst_path, is_snapshot=False):
    if is_snapshot:
        return shell.call("%s copy --snappath %s --dstpath %s --user %s --format json" % (
            ZBS_BIN_PATH, src_path, dst_path, ZBS_USER_NAME))
    return shell.call(
        "%s copy --path %s --dstpath %s --user %s --format json" % (ZBS_BIN_PATH, src_path, dst_path, ZBS_USER_NAME))

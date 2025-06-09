__author__ = 'Xingwei Yu'

import os

import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils.bash import *


logger = log.get_logger(__name__)


ZBSADM_BIN_PATH = "/usr/local/bin/zbsadm"
ZBS_BIN_PATH = "/usr/bin/zbs"
ZBS_CLIENT_CONF_PATH = "/etc/zbs/client.conf"
ZBS_USER_NAME = "zbs"
STRIPE_VOLUME_COUNT = 64
STRIPE_VOLUME_UINT = "64KiB"

CBD_PREFIX = "cbd"
CBD_VOLUME_PATH = CBD_PREFIX + ":{}/{}/{}"
CBD_SNAPSHOT_PATH = CBD_VOLUME_PATH + "@{}"


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


def deploy_client(ip, password):
    return shell.call("%s client deploy --host %s -p %s --silent" % (ZBSADM_BIN_PATH, ip, linux.shellquote(password)))


def query_mds_status_info():
    return shell.call("%s status mds --format json" % ZBS_BIN_PATH)


def query_logical_pool_info():
    return shell.call("%s list logical-pool --format json" % ZBS_BIN_PATH)


def query_volume_info(logical_pool, volume):
    return shell.call("%s query file --path %s/%s --format json" % (ZBS_BIN_PATH, logical_pool, volume))


def query_children_volume(logical_pool, volume, snapshot, is_snapshot=False):
    if is_snapshot:
        return shell.call("%s children --snappath %s/%s@%s --user %s --format json" % (ZBS_BIN_PATH, logical_pool, volume, snapshot, ZBS_USER_NAME))
    else:
        return shell.call("%s children --path %s/%s --user %s --format json" % (ZBS_BIN_PATH, logical_pool, volume, ZBS_USER_NAME))


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


def create_volume(logical_pool, volume, size):
    return shell.call("%s create file --path %s/%s --size %s --stripecount %d --stripeunit %s --user %s --format json" % (ZBS_BIN_PATH, logical_pool, volume, size, STRIPE_VOLUME_COUNT, STRIPE_VOLUME_UINT, ZBS_USER_NAME))


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
    return shell.call("%s clone --snappath %s/%s@%s --dstpath %s/%s --user %s --format json" % (ZBS_BIN_PATH, logical_pool, volume, snapshot, logical_pool, dst_volume, ZBS_USER_NAME))


def expand_volume(logical_pool, volume, size):
    return shell.call("%s update file --path %s/%s --size %s --user %s --format json" % (ZBS_BIN_PATH, logical_pool, volume, size, ZBS_USER_NAME))


def flatten_volume(logical_pool, volume):
    return shell.call("%s flatten --path %s/%s --format json" % (ZBS_BIN_PATH, logical_pool, volume))


def create_snapshot(logical_pool, volume, snapshot):
    return shell.call("%s create snapshot --snappath %s/%s@%s --user %s --format json" % (ZBS_BIN_PATH, logical_pool, volume, snapshot, ZBS_USER_NAME))


def delete_snapshots(logical_pool, volume, file_infos):
    for file_info in file_infos:
        o = query_children_volume(logical_pool, volume, file_info.fileName, True)
        r = jsonobject.loads(o)
        if r.error.code != 0:
            raise Exception('failed to list children of [%s/%s@%s], error[%s]' % (logical_pool, volume, file_info.fileName, r.error.message))
        if r.result.hasattr('fileNames'):
            raise Exception('the snapshot[%s/%s@%s] is still in used' % (logical_pool, volume, file_info.fileName))

        is_protected = file_info.isProtected if file_info.hasattr('isProtected') else False
        if is_protected:
            o = unprotect_snapshot(logical_pool, volume, file_info.fileName)
            r = jsonobject.loads(o)
            if r.error.code != 0:
                raise Exception('failed to unprotect snapshot[%s/%s@%s], error[%s]' % (logical_pool, volume, file_info.fileName, r.error.message))

        shell.call("%s delete snapshot --snappath %s/%s@%s --format json" % (ZBS_BIN_PATH, logical_pool, volume, file_info.fileName))


def protect_snapshot(logical_pool, volume, snapshot):
    return shell.call("%s protect --snappath %s/%s@%s" % (ZBS_BIN_PATH, logical_pool, volume, snapshot))


def unprotect_snapshot(logical_pool, volume, snapshot):
    return shell.call("%s unprotect --snappath %s/%s@%s --format json" % (ZBS_BIN_PATH, logical_pool, volume, snapshot))


def rollback_snapshot(logical_pool, volume, snapshot):
    return shell.call("%s rollback --snappath %s/%s@%s --format json" % (ZBS_BIN_PATH, logical_pool, volume, snapshot))


def cbd_to_nbd(desc, port, install_path):
    logger.debug("qemu-nbd -D %s -f raw -p %d --fork %s_%s_:%s" % (desc, port, install_path, ZBS_USER_NAME, ZBS_CLIENT_CONF_PATH))
    os.system("qemu-nbd -D %s -f raw -p %d --fork %s_%s_:%s" % (desc, port, install_path, ZBS_USER_NAME, ZBS_CLIENT_CONF_PATH))


def copy(src_path, dst_path, is_snapshot=False):
    if is_snapshot:
        return shell.call("%s copy --snappath %s --dstpath %s --user %s --format json" % (ZBS_BIN_PATH, src_path, dst_path, ZBS_USER_NAME))
    return shell.call("%s copy --path %s --dstpath %s --user %s --format json" % (ZBS_BIN_PATH, src_path, dst_path, ZBS_USER_NAME))

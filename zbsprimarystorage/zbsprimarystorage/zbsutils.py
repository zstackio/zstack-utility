__author__ = 'Xingwei Yu'

import os

import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils.bash import *


logger = log.get_logger(__name__)


DEFAULT_ZBS_CONF_PATH = "/etc/zbs/client.conf"
DEFAULT_ZBS_USER_NAME = "zbs"
DEFAULT_STRIPE_VOLUME_COUNT = 64
DEFAULT_STRIPE_VOLUME_UINT = "64KiB"


def query_mds_status_info():
    return shell.call("zbs status mds --format json")


def query_logical_pool_info():
    return shell.call("zbs list logical-pool --format json")


def query_volume_info(logical_pool_name, lun_name):
    return shell.call("zbs query file --path %s/%s --format json" % (logical_pool_name, lun_name))


def query_children_volume(logical_pool_name, lun_name, snapshot_name, is_snapshot=False):
    if is_snapshot:
        return shell.call("zbs children --snappath %s/%s@%s --user %s --format json" % (logical_pool_name, lun_name, snapshot_name, DEFAULT_ZBS_USER_NAME))
    else:
        return shell.call("zbs children --path %s/%s --user %s --format json" % (logical_pool_name, lun_name, DEFAULT_ZBS_USER_NAME))


def query_snapshot_info(logical_pool_name, lun_name):
    return shell.call("zbs list snapshot --path %s/%s --format json" % ((logical_pool_name, lun_name)))


def get_physical_pool_name(logical_pool_name):
    o = query_logical_pool_info()
    r = jsonobject.loads(o)

    if r.error.code != 0:
        raise Exception('failed to get logical pool[%s] info, error[%s]' % (logical_pool_name, r.error.message))

    physical_pool_name = ""
    for ret in r.result:
        for lp in ret.logicalPoolInfos:
            if logical_pool_name in lp.logicalPoolName:
                physical_pool_name = lp.physicalPoolName
                break

    if physical_pool_name is None:
        raise Exception('cannot found logical pool[%s], you must create it manually' % logical_pool_name)

    return physical_pool_name


def create_volume(logical_pool_name, lun_name, lun_size):
    return shell.call("zbs create file --path %s/%s --size %s --stripecount %d --stripeunit %s --user %s --format json" % (logical_pool_name, lun_name, lun_size, DEFAULT_STRIPE_VOLUME_COUNT, DEFAULT_STRIPE_VOLUME_UINT, DEFAULT_ZBS_USER_NAME))


@linux.retry(times=30, sleep_time=5)
def delete_volume(logical_pool_name, lun_name):
    o = query_volume_info(logical_pool_name, lun_name)
    r = jsonobject.loads(o)
    if r.error.code != 0:
        raise Exception('cannot found lun[%s/%s], error[%s]' % (logical_pool_name, lun_name, r.error.message))
    shell.call("zbs delete file --path %s/%s" % (logical_pool_name, lun_name))


def clone_volume(logical_pool_name, lun_name, snapshot_name, dst_lun_name):
    return shell.call("zbs clone --snappath %s/%s@%s --dstpath %s/%s --user %s --format json" % (logical_pool_name, lun_name, snapshot_name, logical_pool_name, dst_lun_name, DEFAULT_ZBS_USER_NAME))


def expand_volume(logical_pool_name, lun_name, lun_size):
    return shell.call("zbs update file --path %s/%s --size %s --user %s --format json" % (logical_pool_name, lun_name, lun_size, DEFAULT_ZBS_USER_NAME))


def create_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("zbs create snapshot --snappath %s/%s@%s --user %s --format json" % (logical_pool_name, lun_name, snapshot_name, DEFAULT_ZBS_USER_NAME))


def delete_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("zbs delete snapshot --snappath %s/%s@%s --format json" % (logical_pool_name, lun_name, snapshot_name))


def protect_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("zbs protect --snappath %s/%s@%s" % (logical_pool_name, lun_name, snapshot_name))


def unprotect_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("zbs unprotect --snappath %s/%s@%s" % (logical_pool_name, lun_name, snapshot_name))


def rollback_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("zbs rollback --snappath %s/%s@%s --format json" % (logical_pool_name, lun_name, snapshot_name))


def cbd_to_nbd(desc, port, install_path):
    logger.debug("qemu-nbd -D %s -f raw -p %d --fork %s_%s_:%s" % (desc, port, install_path, DEFAULT_ZBS_USER_NAME, DEFAULT_ZBS_CONF_PATH))
    os.system("qemu-nbd -D %s -f raw -p %d --fork %s_%s_:%s" % (desc, port, install_path, DEFAULT_ZBS_USER_NAME, DEFAULT_ZBS_CONF_PATH))


def copy(src_path, dst_path, is_snapshot=False):
    if is_snapshot:
        return shell.call("zbs copy --snappath %s --dstpath %s --user %s --format json" % (src_path, dst_path, DEFAULT_ZBS_USER_NAME))
    return shell.call("zbs copy --path %s --dstpath %s --user %s --format json" % (src_path, dst_path, DEFAULT_ZBS_USER_NAME))

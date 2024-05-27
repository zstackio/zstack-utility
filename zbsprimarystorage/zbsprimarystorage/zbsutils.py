__author__ = 'Xingwei Yu'

import os

import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils.bash import *


logger = log.get_logger(__name__)


DEFAULT_ZBS_CONF_PATH = "/etc/zbs/client.conf"
DEFAULT_ZBS_USER_NAME = "zbs"


def query_mds_status_info():
    return shell.call("zbs status mds --format json")


def query_logical_pool_info():
    return shell.call("zbs list logical-pool --format json")


def query_volume_info(logical_pool_name, lun_name):
    return shell.call("zbs query file --path %s/%s --format json" % (logical_pool_name, lun_name))


def query_volume(logical_pool_name, lun_name):
    return shell.run("zbs query file --path %s/%s" % (logical_pool_name, lun_name))


def query_snapshot_info(logical_pool_name, lun_name):
    return shell.call("zbs list snapshot --path %s/%s --format json" % ((logical_pool_name, lun_name)))


def get_physical_pool_name(logical_pool_name):
    o = query_logical_pool_info()

    physical_pool_name = ""
    for ret in jsonobject.loads(o).result:
        for lp in ret.logicalPoolInfos:
            if logical_pool_name in lp.logicalPoolName:
                physical_pool_name = lp.physicalPoolName
                break

    if physical_pool_name is None:
        raise Exception(
            'cannot find logical pool[%s] in the zbs storage, you must create it manually' % logical_pool_name)

    return physical_pool_name


def create_volume(logical_pool_name, lun_name, lun_size):
    return shell.call("zbs create file --path %s/%s --size %s --user %s --format json" % (logical_pool_name, lun_name, lun_size, DEFAULT_ZBS_USER_NAME))


@linux.retry(times=30, sleep_time=5)
def delete_volume(logical_pool_name, lun_name):
    if query_volume(logical_pool_name, lun_name) != 0:
        raise Exception('cannot found lun[%s/%s]' % (logical_pool_name, lun_name))
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


def rollback_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("zbs rollback --snappath %s/%s@%s --format json" % (logical_pool_name, lun_name, snapshot_name))


def cbd_to_nbd(port, install_path):
    os.system("qemu-nbd -f raw -p %d --fork %s_%s_:%s" % (port, install_path, DEFAULT_ZBS_USER_NAME, DEFAULT_ZBS_CONF_PATH))


def copy_snapshot(src_path, dst_path):
    return shell.run("qemu-img convert -n -p %s_%s_:%s %s_%s_:%s" % (src_path, DEFAULT_ZBS_USER_NAME, DEFAULT_ZBS_CONF_PATH, dst_path, DEFAULT_ZBS_USER_NAME, DEFAULT_ZBS_CONF_PATH))

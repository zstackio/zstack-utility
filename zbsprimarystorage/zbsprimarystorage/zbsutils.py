__author__ = 'Xingwei Yu'

import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils.bash import *

logger = log.get_logger(__name__)


def do_query_mds_status_info():
    return shell.call("zbs status mds --format json")


def do_query_logical_pool_info():
    return shell.call("zbs list logical-pool --format json")


def do_query_volume_info(logical_pool_name, volume_name):
    return shell.call("zbs query file --path %s/%s --format json" % (logical_pool_name, volume_name))


def do_query_volume(logical_pool_name, volume_name):
    return shell.run("zbs query file --path %s/%s" % (logical_pool_name, volume_name))


def do_create_volume(logical_pool_name, volume_name, size):
    return shell.call("zbs create file --path %s/%s --size %s --user zbs --format json" % (logical_pool_name, volume_name, size))


@linux.retry(times=30, sleep_time=5)
def do_delete_volume(install_path):
    if install_path is None:
        raise Exception("install path can not be null.")
    path = install_path.split(":")[1].split("/", 1)[1]

    if shell.run("zbs query file --path %s" % path) != 0:
        return
    shell.call("zbs delete file --path %s" % path)


def get_physical_pool_name(logical_pool_name):
    o = do_query_logical_pool_info()

    physicalPoolName = ""
    for lp in jsonobject.loads(o).result[0].logicalPoolInfos:
        if logical_pool_name in lp.logicalPoolName:
            physicalPoolName = lp.physicalPoolName
            break

    if physicalPoolName is None:
        raise Exception(
            'cannot find logical pool[%s] in the zbs storage, you must create it manually' % cmd.logicalPoolName)

    return physicalPoolName
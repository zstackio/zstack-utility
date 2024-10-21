__author__ = 'Xingwei Yu'

import os

import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils.bash import *


logger = log.get_logger(__name__)


DEFAULT_ZBSADM_BIN_PATH = "/usr/local/bin/zbsadm"
DEFAULT_ZBS_BIN_PATH = "/usr/bin/zbs"
DEFAULT_ZBS_CONF_PATH = "/etc/zbs/client.conf"
DEFAULT_ZBS_USER_NAME = "zbs"
DEFAULT_STRIPE_VOLUME_COUNT = 64
DEFAULT_STRIPE_VOLUME_UINT = "64KiB"


def deploy_client(client_ip, client_password):
    return shell.call("%s client deploy --host %s -p %s --silent" % (DEFAULT_ZBSADM_BIN_PATH, client_ip, client_password))


def query_mds_status_info():
    return shell.call("%s status mds --format json" % DEFAULT_ZBS_BIN_PATH)


def query_logical_pool_info():
    return shell.call("%s list logical-pool --format json" % DEFAULT_ZBS_BIN_PATH)


def query_volume_info(logical_pool_name, lun_name):
    return shell.call("%s query file --path %s/%s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name))


def query_children_volume(logical_pool_name, lun_name, snapshot_name, is_snapshot=False):
    if is_snapshot:
        return shell.call("%s children --snappath %s/%s@%s --user %s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, snapshot_name, DEFAULT_ZBS_USER_NAME))
    else:
        return shell.call("%s children --path %s/%s --user %s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, DEFAULT_ZBS_USER_NAME))


def query_snapshot_info(logical_pool_name, lun_name):
    return shell.call("%s list snapshot --path %s/%s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name))


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
    return shell.call("%s create file --path %s/%s --size %s --stripecount %d --stripeunit %s --user %s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, lun_size, DEFAULT_STRIPE_VOLUME_COUNT, DEFAULT_STRIPE_VOLUME_UINT, DEFAULT_ZBS_USER_NAME))


@linux.retry(times=30, sleep_time=5)
def delete_volume(logical_pool_name, lun_name):
    o = query_volume_info(logical_pool_name, lun_name)
    r = jsonobject.loads(o)
    if r.error.code != 0:
        return

    o = query_snapshot_info(logical_pool_name, lun_name)
    r = jsonobject.loads(o)
    if r.error.code != 0:
        return
    if r.result and r.result.hasattr('fileInfo'):
        delete_snapshot(logical_pool_name, lun_name, r.result.fileInfo)

    shell.call("%s delete file --path %s/%s" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name))


def clone_volume(logical_pool_name, lun_name, snapshot_name, dst_lun_name):
    return shell.call("%s clone --snappath %s/%s@%s --dstpath %s/%s --user %s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, snapshot_name, logical_pool_name, dst_lun_name, DEFAULT_ZBS_USER_NAME))


def expand_volume(logical_pool_name, lun_name, lun_size):
    return shell.call("%s update file --path %s/%s --size %s --user %s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, lun_size, DEFAULT_ZBS_USER_NAME))


def create_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("%s create snapshot --snappath %s/%s@%s --user %s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, snapshot_name, DEFAULT_ZBS_USER_NAME))


def delete_snapshot(logical_pool_name, lun_name, file_infos):
    for file_info in file_infos:
        o = query_children_volume(logical_pool_name, lun_name, file_info.fileName, True)
        r = jsonobject.loads(o)
        if r.error.code != 0:
            raise Exception('failed to list children of [%s/%s@%s], error[%s]' % (logical_pool_name, lun_name, file_info.fileName, r.error.message))
        if r.result.hasattr('fileNames'):
            raise Exception('the snapshot[%s/%s@%s] is still in used' % (logical_pool_name, lun_name, file_info.fileName))

        is_protected = file_info.isProtected if file_info.hasattr('isProtected') else False
        if is_protected:
            o = unprotect_snapshot(logical_pool_name, lun_name, file_info.fileName)
            r = jsonobject.loads(o)
            if r.error.code != 0:
                raise Exception('failed to unprotect snapshot[%s/%s@%s], error[%s]' % (logical_pool_name, lun_name, file_info.fileName, r.error.message))

        shell.call("%s delete snapshot --snappath %s/%s@%s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, file_info.fileName))


def protect_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("%s protect --snappath %s/%s@%s" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, snapshot_name))


def unprotect_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("%s unprotect --snappath %s/%s@%s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, snapshot_name))


def rollback_snapshot(logical_pool_name, lun_name, snapshot_name):
    return shell.call("%s rollback --snappath %s/%s@%s --format json" % (DEFAULT_ZBS_BIN_PATH, logical_pool_name, lun_name, snapshot_name))


def cbd_to_nbd(desc, port, install_path):
    logger.debug("qemu-nbd -D %s -f raw -p %d --fork %s_%s_:%s" % (desc, port, install_path, DEFAULT_ZBS_USER_NAME, DEFAULT_ZBS_CONF_PATH))
    os.system("qemu-nbd -D %s -f raw -p %d --fork %s_%s_:%s" % (desc, port, install_path, DEFAULT_ZBS_USER_NAME, DEFAULT_ZBS_CONF_PATH))


def copy(src_path, dst_path, is_snapshot=False):
    if is_snapshot:
        return shell.call("%s copy --snappath %s --dstpath %s --user %s --format json" % (DEFAULT_ZBS_BIN_PATH, src_path, dst_path, DEFAULT_ZBS_USER_NAME))
    return shell.call("%s copy --path %s --dstpath %s --user %s --format json" % (DEFAULT_ZBS_BIN_PATH, src_path, dst_path, DEFAULT_ZBS_USER_NAME))

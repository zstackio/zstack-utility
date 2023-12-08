'''

@author: jialong.dong
'''
import os
import log

from zstacklib.utils import shell
from zstacklib.utils import linux

logger = log.get_logger(__name__)

def get_max_nbds_num():
    if shell.check_run('lsmod | grep nbd'):
        raise Exception('Module nbd not inserted.')

    with open('/sys/module/nbd/parameters/nbds_max', 'r') as f:
        max_num = f.read()
        return int(max_num)

def check_nbd_dev_empty(nbd_id):
    with open('/sys/block/nbd{}/size'.format(nbd_id), 'r') as f:
        size = f.read()
    if int(size) > 0:
        return False
    return True

def check_pid_exists(nbd_id):
    return os.path.exists("/sys/block/nbd{}/pid".format(nbd_id))

def get_a_free_nbd_id():
    for nbd_id in range(get_max_nbds_num()):
        if not check_pid_exists(nbd_id) and check_nbd_dev_empty(nbd_id):
            return nbd_id

def get_free_nbd_ids():
    available_ids = []
    for nbd_id in range(get_max_nbds_num()):
        if not check_pid_exists(nbd_id) and check_nbd_dev_empty(nbd_id):
            available_ids.append(nbd_id)
    return available_ids

def connect(src):
    nbd_id = get_a_free_nbd_id()
    if nbd_id is None:
        raise Exception("There is no available nbd id.")

    fmt = linux.get_img_fmt(src)
    nbd_dev = "/dev/nbd{}".format(nbd_id)
    # rbd-nbd tools and librados2 from xsky are conflicting
    # so rbd image is also connect by qemu-nbd
    # shell.call("rbd-nbd map --device {} {}".format(nbd_dev, src))
    shell.call("qemu-nbd --format {} -c {} --fork {}".format(fmt, nbd_dev, src))
    return nbd_dev

def disconnect(nbd_dev):
    shell.call("qemu-nbd -d {}".format(nbd_dev))
    nbd_id = nbd_dev.lstrip("/dev/").replace("nbd", "")
    if not check_nbd_dev_empty(nbd_id):
        raise Exception("Nbd device {} is disconnected, but size is not empty.".format(nbd_dev))
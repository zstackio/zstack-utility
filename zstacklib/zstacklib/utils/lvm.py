import functools
import random
import os.path
import time

from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import linux

logger = log.get_logger(__name__)
LV_RESERVED_SIZE = 1024*1024*4
LVM_CONFIG_PATH = "/etc/lvm"
SANLOCK_CONFIG_FILE_PATH = "/etc/sanlock/sanlock.conf"
LVM_CONFIG_BACKUP_PATH = "/etc/lvm/zstack-backup"


class LvmlockdLockType(object):
    NULL = 0
    SHARE = 1
    EXCLUSIVE = 2

    @staticmethod
    def from_abbr(abbr):
        if abbr == "sh":
            return LvmlockdLockType.SHARE
        elif abbr == "ex":
            return LvmlockdLockType.EXCLUSIVE
        elif abbr == "un":
            return LvmlockdLockType.NULL
        else:
            raise Exception("unknown lock type %s" % abbr)

    @staticmethod
    def from_str(string):
        if string == "NULL":
            return LvmlockdLockType.SHARE
        elif string == "SHARE":
            return LvmlockdLockType.EXCLUSIVE
        elif string == "EXCLUSIVE":
            return LvmlockdLockType.NULL
        else:
            raise Exception("unknown lock type %s" % string)


class RetryException(Exception):
    pass


def calcLvReservedSize(size):
    # NOTE(weiw): Add additional 12M for every lv
    size = int(size) + 3 * LV_RESERVED_SIZE
    # NOTE(weiw): Add additional 4M per 4GB for qcow2 potential use
    size = int(size) + (size/1024/1024/1024/4) * LV_RESERVED_SIZE
    return size


def check_lvm_config_is_default():
    cmd = shell.ShellCmd("lvmconfig --type diff")
    cmd(is_exception=True)
    if cmd.stdout != "":
        return False
    else:
        return True


def backup_lvm_config():
    if not os.path.exists(LVM_CONFIG_PATH):
        logger.warn("can not find lvm config path: %s, backup failed" % LVM_CONFIG_PATH)
        return

    if not os.path.exists(LVM_CONFIG_BACKUP_PATH):
        os.makedirs(LVM_CONFIG_BACKUP_PATH)

    current_time = time.time()
    cmd = shell.ShellCmd("cp %s/lvm.conf %s/lvm-%s.conf; "
                         "cp %s/lvmlocal.conf %s/lvmlocal-%s.conf" %
                         (LVM_CONFIG_PATH, LVM_CONFIG_BACKUP_PATH, current_time,
                          LVM_CONFIG_PATH, LVM_CONFIG_BACKUP_PATH, current_time))
    cmd(is_exception=False)
    logger.debug("backup lvm config file success")


def reset_lvm_conf_default():
    if not os.path.exists(LVM_CONFIG_PATH):
        raise Exception("can not find lvm config path: %s, reset lvm config failed" % LVM_CONFIG_PATH)

    cmd = shell.ShellCmd("lvmconfig --type default > %s/lvm.conf; "
                         "lvmconfig --type default > %s/lvmlocal.conf" %
                         (LVM_CONFIG_PATH, LVM_CONFIG_PATH))
    cmd(is_exception=False)


def config_lvm_by_sed(keyword, entry, files):
    if not os.path.exists(LVM_CONFIG_PATH):
        raise Exception("can not find lvm config path: %s, config lvm failed" % LVM_CONFIG_PATH)

    for file in files:
        cmd = shell.ShellCmd("sed -i 's/.*%s.*/%s/g' %s/%s" %
                             (keyword, entry, LVM_CONFIG_PATH, file))
        cmd(is_exception=False)


def config_sanlock_by_sed(keyword, entry):
    if not os.path.exists(SANLOCK_CONFIG_FILE_PATH):
        raise Exception("can not find sanlock config path: %s, config sanlock failed" % LVM_CONFIG_PATH)

    cmd = shell.ShellCmd("sed -i 's/.*%s.*/%s/g' %s" %
                         (keyword, entry, SANLOCK_CONFIG_FILE_PATH))
    cmd(is_exception=False)


def config_lvm_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --mergedconfig --config %s=%s -f /etc/lvm/lvm.conf" % (node, value))
    cmd(is_exception=True)


def config_lvmlocal_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --mergedconfig --config %s=%s -f /etc/lvm/lvmlocal.conf" % (node, value))
    cmd(is_exception=True)


def start_lvmlockd():
    for service in ["lvm2-lvmlockd", "wdmd", "sanlock"]:
        cmd = shell.ShellCmd("systemctl start %s" % service)
        cmd(is_exception=True)


def start_vg_lock(vgUuid):
    @linux.retry(times=20, sleep_time=random.uniform(1,10))
    def vg_lock_is_adding(vgUuid):
        # NOTE(weiw): this means vg locking is adding rather than complete
        cmd = shell.ShellCmd("sanlock client status | grep -E 's lvm_%s.*\\:0 ADD'" % vgUuid)
        cmd(is_exception=False)
        if cmd.return_code == 0:
            raise RetryException("vg %s lock space is starting" % vgUuid)
        return False

    @linux.retry(times=3, sleep_time=random.uniform(0.1, 1))
    def vg_lock_exists(vgUuid):
        cmd = shell.ShellCmd("lvmlockctl -i | grep %s" % vgUuid)
        cmd(is_exception=False)
        if cmd.return_code != 0:
            raise RetryException("can not find lock space for vg %s via lvmlockctl" % vgUuid)
        elif vg_lock_is_adding(vgUuid) is False:
            return True
        else:
            return False

    @linux.retry(times=15, sleep_time=random.uniform(0.1, 30))
    def start_lock(vgUuid):
        cmd = shell.ShellCmd("vgchange --lock-start %s" % vgUuid)
        cmd(is_exception=True)
        if cmd.return_code != 0:
            raise Exception("vgchange --lock-start failed")

        vg_lock_exists(vgUuid)

    try:
        vg_lock_exists(vgUuid)
    except RetryException:
        start_lock(vgUuid)
    except Exception as e:
        raise e


def get_vg_size(vgUuid):
    cmd = shell.ShellCmd("vgs --nolocking --readonly %s --noheadings --separator : --units b -o vg_size,vg_free" % vgUuid)
    cmd(is_exception=True)
    return cmd.stdout.strip().split(':')[0].strip("B"), cmd.stdout.strip().split(':')[1].strip("B")


def add_vg_tag(vgUuid, tag):
    cmd = shell.ShellCmd("vgchange --addtag %s %s" % (tag, vgUuid))
    cmd(is_exception=True)

def has_lv_tag(path, tag):
    o = shell.call("lvs -Stags={%s} %s --nolocking --noheadings --readonly 2>/dev/null | wc -l" % (tag, path))
    return o.strip() == '1'

def get_meta_lv_path(path):
    return path+"_meta"

def delete_image(path, tag):
    def activate_and_remove(f):
        active_lv(f, shared=False)
        backing = linux.qcow2_get_backing_file(f)
        shell.check_run("lvremove -y -Stags={%s} %s" % (tag, f))
        return f

    fpath = path
    while fpath:
        backing = activate_and_remove(fpath)
        activate_and_remove(get_meta_lv_path(fpath))
        fpath = backing

def clean_vg_exists_host_tags(vgUuid, hostUuid, tag):
    cmd = shell.ShellCmd("vgs %s -otags --nolocking --noheading | grep -Po '%s::%s::[\d.]*'" % (vgUuid, tag, hostUuid))
    cmd(is_exception=False)
    exists_tags = cmd.stdout.strip().split("\n")
    if len(exists_tags) == 0:
        return
    t = " --deltag " + " --deltag ".join(exists_tags)
    cmd = shell.ShellCmd("vgchange %s %s" % (t, vgUuid))
    cmd(is_exception=False)


@linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
def create_lv_from_absolute_path(path, size, tag="zs::sharedblock::volume"):
    vgName = path.split("/")[2]
    lvName = path.split("/")[3]

    cmd = shell.ShellCmd("lvcreate -an --addtag %s --size %sb --name %s %s" %
                         (tag, calcLvReservedSize(size), lvName, vgName))
    cmd(is_exception=True)


def get_lv_size(path):
    cmd = shell.ShellCmd("lvs --nolocking --readonly --noheading -osize --units b %s" % path)
    cmd(is_exception=True)
    return cmd.stdout.strip().strip("B")


def resize_lv(path, size):
    cmd = shell.ShellCmd("lvresize --size %sb %s" % (calcLvReservedSize(size), path))
    cmd(is_exception=True)


@linux.retry(times=10, sleep_time=random.uniform(0.1, 3))
def active_lv(path, shared=False):
    flag = "-ay"
    if shared:
        flag = "-asy"

    cmd = shell.ShellCmd("lvchange %s %s" % (flag, path))
    cmd(is_exception=True)


def deactive_lv(path, raise_exception=True):
    if not lv_exists(path):
        return
    cmd = shell.ShellCmd("lvchange -an %s" % path)
    cmd(is_exception=raise_exception)


def delete_lv(path, raise_exception=True):
    # remove meta-lv if any
    if lv_exists(get_meta_lv_path(path)):
        shell.run("lvremove -y %s" % get_meta_lv_path(path))
    if not lv_exists(path):
        return
    cmd = shell.ShellCmd("lvremove -y %s" % path)
    cmd(is_exception=raise_exception)
    return cmd.return_code


def lv_exists(path):
    cmd = shell.ShellCmd("lvs --nolocking --readonly %s" % path)
    cmd(is_exception=False)
    return cmd.return_code == 0


def lv_uuid(path):
    cmd = shell.ShellCmd("lvs --nolocking --readonly --noheadings %s -ouuid" % path)
    cmd(is_exception=False)
    return cmd.stdout.strip()


def lv_is_active(path):
    cmd = shell.ShellCmd("lvs --nolocking --readonly --noheadings %s -oactive | grep active" % path)
    cmd(is_exception=False)
    return cmd.return_code == 0


def get_lv_locking_type(path):
    if not lv_is_active(path):
        return LvmlockdLockType.NULL
    cmd = shell.ShellCmd("lvmlockctl -i | grep %s | awk '{print $3}'" % lv_uuid(path))
    cmd(is_exception=True)
    return LvmlockdLockType.from_abbr(cmd.stdout.strip())


def lv_operate(abs_path, shared=False):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            with OperateLv(abs_path, shared):
                retval = f(*args, **kwargs)
            return retval
        return inner
    return wrap


def qcow2_lv_recursive_operate(abs_path, shared=False):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            with RecursiveOperateLv(abs_path, shared):
                retval = f(*args, **kwargs)
            return retval
        return inner
    return wrap


class OperateLv(object):
    def __init__(self, abs_path, shared=False):
        self.abs_path = abs_path
        self.shared = shared
        self.exists_lock = get_lv_locking_type(abs_path)
        self.target_lock = LvmlockdLockType.EXCLUSIVE if shared == False else LvmlockdLockType.SHARE

    def __enter__(self):
        if self.exists_lock < self.target_lock:
            active_lv(self.abs_path, self.shared)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.exists_lock == LvmlockdLockType.NULL:
            deactive_lv(self.abs_path, raise_exception=False)
        else:
            active_lv(self.abs_path, self.exists_lock == LvmlockdLockType.SHARE)


class RecursiveOperateLv(object):
    def __init__(self, abs_path, shared=False):
        self.abs_path = abs_path
        self.shared = shared
        self.exists_lock = get_lv_locking_type(abs_path)
        self.target_lock = LvmlockdLockType.EXCLUSIVE if shared == False else LvmlockdLockType.SHARE
        self.backing = None

    def __enter__(self):
        if self.exists_lock < self.target_lock:
            active_lv(self.abs_path, self.shared)
        if linux.qcow2_get_backing_file(self.abs_path) != "":
            self.backing = RecursiveOperateLv(linux.qcow2_get_backing_file(self.abs_path), True)

        if self.backing is not None:
            self.backing.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.backing is not None:
            self.backing.__exit__(exc_type, exc_val, exc_tb)
        if self.exists_lock == LvmlockdLockType.NULL:
            deactive_lv(self.abs_path, raise_exception=False)
        else:
            active_lv(self.abs_path, self.exists_lock == LvmlockdLockType.SHARE)

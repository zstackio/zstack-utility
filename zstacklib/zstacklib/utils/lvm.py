import functools
import random

from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import linux

logger = log.get_logger(__name__)
LV_RESERVED_SIZE = 1024*1024*4


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


def check_lvm_config_is_default():
    cmd = shell.ShellCmd("lvmconfig --type diff")
    cmd(is_exception=True)
    if cmd.stdout != "":
        return True
    else:
        return False


def config_lvm_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --config %s=%s -f /etc/lvm/lvm.conf" % (node, value))
    cmd(is_exception=True)


def config_lvmlocal_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --config %s=%s -f /etc/lvm/lvmlocal.conf" % (node, value))
    cmd(is_exception=True)


def start_lvmlockd():
    for service in ["lvmlockd", "wdmd", "sanlock"]:
        cmd = shell.ShellCmd("systemctl start %s" % service)
        cmd(is_exception=True)


def start_vg_lock(vgUuid):
    @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
    def start_lock(vgUuid):
        cmd = shell.ShellCmd("vgchange --lock-start %s" % vgUuid)
        cmd(is_exception=True)
        if cmd.return_code != 0:
            raise Exception("vgchange --lock-start failed")

        cmd = shell.ShellCmd("lvmlockctl -i | grep %s" % vgUuid)
        cmd(is_exception=True)
        if cmd.return_code != 0:
            raise RetryException("can not find lock space for vg %s via lvmlockctl" % vgUuid)

    try:
        start_lock(vgUuid)
    except RetryException as e:
        raise e


def get_vg_size(vgUuid):
    cmd = shell.ShellCmd("vgs --nolocking %s --noheadings --separator : --units b -o vg_size,vg_free" % vgUuid)
    cmd(is_exception=True)
    return cmd.stdout.strip().split(':')[0].strip("B"), cmd.stdout.strip().split(':')[1].strip("B")


def add_vg_tag(vgUuid, tag):
    cmd = shell.ShellCmd("vgchange --addtag %s %s" % (tag, vgUuid))
    cmd(is_exception=True)


def create_lv_from_absolute_path(path, size, tag="zs::sharedblock::volume"):
    vgName = path.split("/")[2]
    lvName = path.split("/")[3]

    cmd = shell.ShellCmd("lvcreate -an --addtag %s --size %sb --name %s %s" %
                         (tag, int(size) + LV_RESERVED_SIZE, lvName, vgName))
    cmd(is_exception=True)


def resize_lv(path, size):
    cmd = shell.ShellCmd("lvresize --size %sb %s" % (int(size) + LV_RESERVED_SIZE, path))
    cmd(is_exception=True)


def active_lv(path, shared=False):
    flag = "-ay"
    if shared:
        flag = "-asy"

    cmd = shell.ShellCmd("lvchange %s %s" % (flag, path))
    cmd(is_exception=True)


def deactive_lv(path, raise_exception=True):
    cmd = shell.ShellCmd("lvchange -an %s" % path)
    cmd(is_exception=raise_exception)


def delete_lv(path):
    cmd = shell.ShellCmd("lvremove -an %s" % path)
    cmd(is_exception=True)


def lv_exists(path):
    cmd = shell.ShellCmd("lvs --nolocking %s" % path)
    cmd(is_exception=False)
    return cmd.return_code == 0


def lv_uuid(path):
    cmd = shell.ShellCmd("lvs --nolocking --noheadings %s -ouuid" % path)
    cmd(is_exception=False)
    return cmd.stdout.strip()


def lv_active(path):
    cmd = shell.ShellCmd("lvs --nolocking --noheadings %s -oactive | grep active" % path)
    cmd(is_exception=False)
    return cmd.return_code == 0


def get_lv_locking_type(path):
    if not lv_active(path):
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

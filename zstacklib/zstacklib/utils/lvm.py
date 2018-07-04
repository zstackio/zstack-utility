import functools
import random
import os.path
import time

from zstacklib.utils import shell
from zstacklib.utils import bash
from zstacklib.utils import log
from zstacklib.utils import linux

logger = log.get_logger(__name__)
LV_RESERVED_SIZE = 1024*1024*4
LVM_CONFIG_PATH = "/etc/lvm"
SANLOCK_CONFIG_FILE_PATH = "/etc/sanlock/sanlock.conf"
LVM_CONFIG_BACKUP_PATH = "/etc/lvm/zstack-backup"
SUPER_BLOCK_BACKUP = "superblock.bak"


class LvmlockdLockType(object):
    NULL = 0
    SHARE = 1
    EXCLUSIVE = 2

    @staticmethod
    def from_abbr(abbr):
        if abbr.strip() == "sh":
            return LvmlockdLockType.SHARE
        elif abbr.strip() == "ex":
            return LvmlockdLockType.EXCLUSIVE
        elif abbr.strip() == "un":
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


def clean_duplicate_configs():
    cmd = shell.ShellCmd("md5sum %s/* " % LVM_CONFIG_BACKUP_PATH +
                         " | awk 'p[$1]++ { printf \"rm %s\\n\",$2;}' | bash")
    cmd(is_exception=False)


def backup_lvm_config():
    if not os.path.exists(LVM_CONFIG_PATH):
        logger.warn("can not find lvm config path: %s, backup failed" % LVM_CONFIG_PATH)
        return

    if not os.path.exists(LVM_CONFIG_BACKUP_PATH):
        os.makedirs(LVM_CONFIG_BACKUP_PATH)

    clean_duplicate_configs()
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


@bash.in_bash
def start_vg_lock(vgUuid):
    @linux.retry(times=20, sleep_time=random.uniform(1,10))
    def vg_lock_is_adding(vgUuid):
        # NOTE(weiw): this means vg locking is adding rather than complete
        return_code = bash.bash_r("sanlock client status | grep -E 's lvm_%s.*\\:0 ADD'" % vgUuid)
        if return_code == 0:
            raise RetryException("vg %s lock space is starting" % vgUuid)
        return False

    @linux.retry(times=3, sleep_time=random.uniform(0.1, 1))
    def vg_lock_exists(vgUuid):
        return_code = bash.bash_r("lvmlockctl -i | grep %s" % vgUuid)
        if return_code != 0:
            raise RetryException("can not find lock space for vg %s via lvmlockctl" % vgUuid)
        elif vg_lock_is_adding(vgUuid) is True:
            raise RetryException("lock space for vg %s is adding" % vgUuid)
        else:
            return True

    @linux.retry(times=15, sleep_time=random.uniform(0.1, 30))
    def start_lock(vgUuid):
        return_code = bash.bash_r("vgchange --lock-start %s" % vgUuid)
        if return_code != 0:
            raise Exception("vgchange --lock-start failed")

        vg_lock_exists(vgUuid)

    try:
        vg_lock_exists(vgUuid)
    except RetryException:
        start_lock(vgUuid)
    except Exception as e:
        raise e


def stop_vg_lock(vgUuid):
    @linux.retry(times=3, sleep_time=random.uniform(0.1, 1))
    def vg_lock_not_exists(vgUuid):
        cmd = shell.ShellCmd("lvmlockctl -i | grep %s" % vgUuid)
        cmd(is_exception=False)
        if cmd.return_code == 0:
            raise RetryException("lock space for vg %s still exists" % vgUuid)
        else:
            return True

    @linux.retry(times=15, sleep_time=random.uniform(0.1, 30))
    def stop_lock(vgUuid):
        cmd = shell.ShellCmd("vgchange --lock-stop %s" % vgUuid)
        cmd(is_exception=True)
        if cmd.return_code != 0:
            raise Exception("vgchange --lock-stop failed")

        vg_lock_not_exists(vgUuid)

    try:
        vg_lock_not_exists(vgUuid)
    except RetryException:
        stop_lock(vgUuid)
    except Exception as e:
        raise e


def get_running_host_id(vgUuid):
    cmd = shell.ShellCmd("sanlock client gets | grep %s | awk -F':' '{ print $2 }'" % vgUuid)
    cmd(is_exception=False)
    if cmd.stdout.strip() == "":
        raise Exception("can not get running host id for vg %s" % vgUuid)
    return cmd.stdout.strip()


def get_wwid(disk_path):
    cmd = shell.ShellCmd("udevadm info --name=%s | grep 'disk/by-id.*' -m1 -o | awk -F '/' {' print $3 '}" % disk_path)
    cmd(is_exception=False)
    return cmd.stdout.strip()


def backup_super_block(disk_path):
    wwid = get_wwid(disk_path)
    if wwid is None or wwid == "":
        logger.warn("can not get wwid of disk %s" % disk_path)

    current_time = time.time()
    disk_back_file = os.path.join(LVM_CONFIG_BACKUP_PATH, "%s.%s.%s" % (wwid, SUPER_BLOCK_BACKUP, current_time))
    cmd = shell.ShellCmd("dd if=%s of=%s bs=64KB count=1 conv=notrunc" % (disk_path, disk_back_file))
    cmd(is_exception=False)


@bash.in_bash
def wipe_fs(disks):
    for disk in disks:
        cmd = shell.ShellCmd("pvdisplay %s" % disk)
        cmd(is_exception=False)
        if cmd.return_code == 0:
            continue

        backup_super_block(disk)
        need_flush_mpath = False

        cmd_part = shell.ShellCmd("partprobe -s %s" % disk)
        cmd_part(is_exception=False)

        cmd_type = shell.ShellCmd("lsblk %s -oTYPE | grep mpath" % disk)
        cmd_type(is_exception=False)
        if cmd_type.stdout.strip() != "":
            need_flush_mpath = True

        cmd_wipefs = shell.ShellCmd("wipefs -af %s" % disk)
        cmd_wipefs(is_exception=False)

        if need_flush_mpath:
            cmd_flush_mpath = shell.ShellCmd("multipath -f %s && systemctl restart multipathd.service && sleep 1" % disk)
            cmd_flush_mpath(is_exception=False)


def add_pv(vg_uuid, disk_path, metadata_size):
    cmd = shell.ShellCmd("vgextend --metadatasize %s %s %s" % (metadata_size, vg_uuid, disk_path))
    cmd(is_exception=True)


def get_vg_size(vgUuid):
    cmd = shell.ShellCmd("vgs --nolocking --readonly %s --noheadings --separator : --units b -o vg_size,vg_free" % vgUuid)
    cmd(is_exception=True)
    return cmd.stdout.strip().split(':')[0].strip("B"), cmd.stdout.strip().split(':')[1].strip("B")


def add_vg_tag(vgUuid, tag):
    cmd = shell.ShellCmd("vgchange --addtag %s %s" % (tag, vgUuid))
    cmd(is_exception=True)


def has_lv_tag(path, tag):
    if tag == "":
        logger.debug("check tag is empty, return false")
        return False
    o = shell.call("lvs -Stags={%s} %s --nolocking --noheadings --readonly 2>/dev/null | wc -l" % (tag, path))
    return o.strip() == '1'


def clean_lv_tag(path, tag):
    if has_lv_tag(path, tag):
        shell.run('lvchange --deltag %s %s' % (tag, path))


def add_lv_tag(path, tag):
    if not has_lv_tag(path, tag):
        shell.run('lvchange --addtag %s %s' % (tag, path))


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


@bash.in_bash
@linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
def create_lv_from_absolute_path(path, size, tag="zs::sharedblock::volume"):
    vgName = path.split("/")[2]
    lvName = path.split("/")[3]

    bash.bash_errorout("lvcreate -an --addtag %s --size %sb --name %s %s" %
                         (tag, calcLvReservedSize(size), lvName, vgName))
    if not lv_exists(path):
        raise Exception("can not find lv %s after create", path)

    with OperateLv(path, shared=False):
        dd_zero(path)


def dd_zero(path):
    cmd = shell.ShellCmd("dd if=/dev/zero of=%s bs=65536 count=1 conv=sync,notrunc" % path)
    cmd(is_exception=False)


def get_lv_size(path):
    cmd = shell.ShellCmd("lvs --nolocking --readonly --noheading -osize --units b %s" % path)
    cmd(is_exception=True)
    return cmd.stdout.strip().strip("B")


def resize_lv(path, size):
    cmd = shell.ShellCmd("lvresize --size %sb %s" % (calcLvReservedSize(size), path))
    cmd(is_exception=True)


@bash.in_bash
@linux.retry(times=10, sleep_time=random.uniform(0.1, 3))
def active_lv(path, shared=False):
    flag = "-ay"
    if shared:
        flag = "-asy"

    bash.bash_errorout("lvchange %s %s" % (flag, path))
    if lv_is_active(path) is False:
        raise Exception("active lv %s with %s failed" % (path, flag))


@bash.in_bash
@linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
def deactive_lv(path, raise_exception=True):
    if not lv_exists(path):
        return
    if not lv_is_active(path):
        return
    if raise_exception:
        bash.bash_errorout("lvchange -an %s" % path)
    else:
        bash.bash_r("lvchange -an %s" % path)
    if lv_is_active(path):
        raise RetryException("lv %s is still active after lvchange -an" % path)


@bash.in_bash
def delete_lv(path, raise_exception=True):
    logger.debug("deleting lv %s" % path)
    # remove meta-lv if any
    if lv_exists(get_meta_lv_path(path)):
        shell.run("lvremove -y %s" % get_meta_lv_path(path))
    if not lv_exists(path):
        return
    if raise_exception:
        o = bash.bash_errorout("lvremove -y %s" % path)
    else:
        o = bash.bash_o("lvremove -y %s" % path)
    return o


@bash.in_bash
def lv_exists(path):
    r = bash.bash_r("lvs --nolocking --readonly %s" % path)
    return r == 0


def lv_uuid(path):
    cmd = shell.ShellCmd("lvs --nolocking --readonly --noheadings %s -ouuid" % path)
    cmd(is_exception=False)
    return cmd.stdout.strip()


def lv_is_active(path):
    # NOTE(weiw): use readonly to get active may return 'unknown'
    r = bash.bash_r("lvs --nolocking --noheadings %s -oactive | grep -w active" % path)
    return r == 0


@bash.in_bash
def lv_rename(old_abs_path, new_abs_path, overwrite=False):
    if not lv_exists(new_abs_path):
        return bash.bash_roe("lvrename %s %s" % (old_abs_path, new_abs_path))

    if overwrite is False:
        raise Exception("lv with name %s is already exists, can not rename lv %s to it" %
                        (new_abs_path, old_abs_path))

    tmp_path = new_abs_path + "_%s" % int(time.time())
    r, o, e = lv_rename(new_abs_path, tmp_path)
    if r != 0:
        raise Exception("rename lv %s to tmp name %s failed: stdout: %s, stderr: %s" %
                        (new_abs_path, tmp_path, o, e))

    r, o, e = lv_rename(old_abs_path, new_abs_path)
    if r != 0:
        bash.bash_errorout("lvrename %s %s" % (tmp_path, new_abs_path))
        raise Exception("rename lv %s to tmp name %s failed: stdout: %s, stderr: %s" %
                        (old_abs_path, new_abs_path, o, e))

    delete_lv(tmp_path, False)


def list_local_active_lvs(vgUuid):
    cmd = shell.ShellCmd("lvs --nolocking %s --noheadings -opath -Slv_active=active" % vgUuid)
    cmd(is_exception=False)
    result = []
    for i in cmd.stdout.strip().split("\n"):
        if i != "":
            result.append(i)
    return result


def check_gl_lock(raise_exception=False):
    r = bash.bash_r("lvmlockctl -i | grep 'LK GL'")
    if r == 0:
        return
    logger.debug("can not find any gl lock")
    r, o = bash.bash_ro("vgs --nolocking --noheadings -Svg_lock_type=sanlock -oname")
    result = []
    for i in o.strip().split("\n"):
        if i != "":
            result.append(i)
    if len(result) == 0:
        if raise_exception is True:
            raise Exception("can not find any sanlock shared vg")
        else:
            return
    r, o, e = bash.bash_roe("lvmlockctl --gl-enable %s" % result[0])
    if r != 0:
        raise Exception("failed to enable gl lock on vg: %s" % result[0])


def do_active_lv(absolutePath, lockType, recursive):
    def handle_lv(lockType, fpath):
        if lockType > LvmlockdLockType.NULL:
            active_lv(fpath, lockType == LvmlockdLockType.SHARE)
        else:
            deactive_lv(fpath)

    handle_lv(lockType, absolutePath)

    if recursive is False:
        return

    while linux.qcow2_get_backing_file(absolutePath) != "":
        absolutePath = linux.qcow2_get_backing_file(absolutePath)
        if lockType == LvmlockdLockType.NULL:
            handle_lv(LvmlockdLockType.NULL, absolutePath)
        else:
            # activate backing files only in shared mode
            handle_lv(LvmlockdLockType.SHARE, absolutePath)


@bash.in_bash
@linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
def get_lv_locking_type(path):
    if not lv_is_active(path):
        return LvmlockdLockType.NULL
    output = bash.bash_o("lvmlockctl -i | grep %s | head -n1 | awk '{print $3}'" % lv_uuid(path))
    return LvmlockdLockType.from_abbr(output.strip())


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
    def __init__(self, abs_path, shared=False, delete_when_exception=False):
        self.abs_path = abs_path
        self.shared = shared
        self.exists_lock = get_lv_locking_type(abs_path)
        self.target_lock = LvmlockdLockType.EXCLUSIVE if shared is False else LvmlockdLockType.SHARE
        self.delete_when_exception = delete_when_exception

    def __enter__(self):
        if self.exists_lock < self.target_lock:
            active_lv(self.abs_path, self.shared)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None and self.delete_when_exception is True:
            delete_lv(self.abs_path, False)
            return

        if self.exists_lock == LvmlockdLockType.NULL:
            deactive_lv(self.abs_path, raise_exception=False)
        else:
            active_lv(self.abs_path, self.exists_lock == LvmlockdLockType.SHARE)


class RecursiveOperateLv(object):
    def __init__(self, abs_path, shared=False, skip_deactivate_tag="", delete_when_exception=False):
        self.abs_path = abs_path
        self.shared = shared
        self.exists_lock = get_lv_locking_type(abs_path)
        self.target_lock = LvmlockdLockType.EXCLUSIVE if shared is False else LvmlockdLockType.SHARE
        self.backing = None
        self.delete_when_exception = delete_when_exception
        self.skip_deactivate_tag = skip_deactivate_tag

    def __enter__(self):
        if self.exists_lock < self.target_lock:
            active_lv(self.abs_path, self.shared)
        if linux.qcow2_get_backing_file(self.abs_path) != "":
            self.backing = RecursiveOperateLv(
                linux.qcow2_get_backing_file(self.abs_path), True, self.skip_deactivate_tag, False)

        if self.backing is not None:
            self.backing.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.backing is not None:
            self.backing.__exit__(exc_type, exc_val, exc_tb)

        if exc_val is not None \
                and self.delete_when_exception is True\
                and not has_lv_tag(self.abs_path, self.skip_deactivate_tag):
            delete_lv(self.abs_path, False)
            return

        if has_lv_tag(self.abs_path, self.skip_deactivate_tag):
            logger.debug("the volume %s has skip tag: %s" %
                         (self.abs_path, has_lv_tag(self.abs_path, self.skip_deactivate_tag)))
            return

        if self.exists_lock == LvmlockdLockType.NULL:
            deactive_lv(self.abs_path, raise_exception=False)
        else:
            active_lv(self.abs_path, self.exists_lock == LvmlockdLockType.SHARE)

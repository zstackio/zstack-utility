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
SANLOCK_IO_TIMEOUT = 40
LVMLOCKD_LOG_FILE_PATH = "/var/log/lvmlockd/lvmlockd.log"
LVMLOCKD_LOG_LOGROTATE_PATH = "/etc/logrotate.d/lvmlockd"
LVM_CONFIG_BACKUP_PATH = "/etc/lvm/zstack-backup"
SUPER_BLOCK_BACKUP = "superblock.bak"
COMMON_TAG = "zs::sharedblock"
VOLUME_TAG = COMMON_TAG + "::volume"
IMAGE_TAG = COMMON_TAG + "::image"
ENABLE_DUP_GLOBAL_CHECK = False
thinProvisioningInitializeSize = "thinProvisioningInitializeSize"


class VolumeProvisioningStrategy(object):
    ThinProvisioning = "ThinProvisioning"
    ThickProvisioning = "ThickProvisioning"


class VmStruct(object):
    def __init__(self):
        super(VmStruct, self).__init__()
        self.pid = ""
        self.cmdline = ""
        self.root_volume = ""
        self.uuid = ""
        self.volumes = []


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
        elif abbr.strip() == "":
            logger.warn("can not get correct lvm lock type! use null as a safe choice")
            return LvmlockdLockType.NULL
        else:
            raise Exception("unknown lock type from abbr: %s" % abbr)

    @staticmethod
    def from_str(string):
        if string == "NULL":
            return LvmlockdLockType.SHARE
        elif string == "SHARE":
            return LvmlockdLockType.EXCLUSIVE
        elif string == "EXCLUSIVE":
            return LvmlockdLockType.NULL
        else:
            raise Exception("unknown lock type from str: %s" % string)


class RetryException(Exception):
    pass


class SharedBlockCandidateStruct:
    wwids = []  # type: list[str]
    vendor = None  # type: str
    model = None  # type: str
    wwn = None  # type: str
    serial = None  # type: str
    hctl = None  # type: str
    type = None  # type: str
    size = None  # type: long
    path = None  # type: str

    def __init__(self):
        pass


def get_block_devices():
    # 1. get multi path devices
    # 2. get multi path device information from raw device
    # 3. get information of other devices
    mpath_devices = []
    block_devices = []  # type: List[SharedBlockCandidateStruct]
    cmd = shell.ShellCmd("multipath -l -v1")
    cmd(is_exception=False)
    if cmd.return_code == 0 and cmd.stdout.strip() != "":
        mpath_devices = cmd.stdout.strip().split("\n")

    for mpath_device in mpath_devices:  # type: str
        try:
            cmd = shell.ShellCmd("realpath /dev/mapper/%s | grep -E -o 'dm-.*'" % mpath_device)
            cmd(is_exception=False)
            if cmd.return_code != 0 or cmd.stdout.strip() == "":
                continue

            dm = cmd.stdout.strip()
            slaves = shell.call("ls /sys/class/block/%s/slaves/" % dm).strip().split("\n")
            if slaves is None or len(slaves) == 0:
                struct = SharedBlockCandidateStruct()
                cmd = shell.ShellCmd("udevadm info -n %s | grep dm-uuid-mpath | grep -o 'dm-uuid-mpath-\S*' | head -n 1 | awk -F '-' '{print $NF}'" % dm)
                cmd(is_exception=True)
                struct.wwids = [cmd.stdout.strip().strip("()")]
                struct.type = "mpath"
                block_devices.append(struct)
                continue

            struct = get_device_info(slaves[0])
            cmd = shell.ShellCmd("udevadm info -n %s | grep dm-uuid-mpath | grep -o 'dm-uuid-mpath-\S*' | head -n 1 | awk -F '-' '{print $NF}'" % dm)
            cmd(is_exception=True)
            struct.wwids = [cmd.stdout.strip().strip("()")]
            struct.type = "mpath"
            block_devices.append(struct)
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            continue

    disks = shell.call("lsblk -p -o NAME,TYPE | grep disk | awk '{print $1}'").strip().split()
    for disk in disks:
        try:
            if is_slave_of_multipath(disk):
                continue
            d = get_device_info(disk.strip().split("/")[-1])
            if len(d.wwids) is 0:
                continue
            if get_pv_uuid_by_path("/dev/disk/by-id/%s" % d.wwids[0]) not in ("", None):
                d.type = "lvm-pv"
            block_devices.append(d)
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            continue

    return block_devices


@bash.in_bash
def is_multipath_running():
    r = bash.bash_r("multipath -t")
    if r != 0:
        return False

    r = bash.bash_r("pgrep multipathd")
    if r != 0:
        return False
    return True


@bash.in_bash
def is_slave_of_multipath(dev_path):
    # type: (str) -> bool
    if is_multipath_running is False:
        return False

    r = bash.bash_r("multipath %s -l | grep policy" % dev_path)
    if r == 0:
        return True
    return False


def is_multipath(dev_name):
    if not is_multipath_running():
        return False
    r = bash.bash_r("multipath /dev/%s -l | grep policy" % dev_name)
    if r == 0:
        return True

    slaves = shell.call("ls /sys/class/block/%s/slaves/" % dev_name).strip().split("\n")
    if slaves is not None and len(slaves) > 0:
        if len(slaves) == 1 and slaves[0] == "":
            return False
        return True
    return False


def get_multipath_name(dev_name):
    return bash.bash_o("multipath /dev/%s -l -v1" % dev_name).strip()


def get_device_info(dev_name):
    # type: (str) -> SharedBlockCandidateStruct
    s = SharedBlockCandidateStruct()
    o = shell.call("lsblk --pair -b -p -o NAME,VENDOR,MODEL,WWN,SERIAL,HCTL,TYPE,SIZE /dev/%s" % dev_name).strip().split("\n")[0]
    if o == "":
        raise Exception("can not get device information from %s" % dev_name)

    def get_data(e):
        return e.split("=")[1].strip().strip('"')

    def get_wwids(dev):
        return shell.call("udevadm info -n %s | grep 'by-id' | grep -v DEVLINKS | awk -F 'by-id/' '{print $2}'" % dev).strip().split()

    def get_path(dev):
        return shell.call("udevadm info -n %s | grep 'by-path' | grep -v DEVLINKS | head -n1 | awk -F 'by-path/' '{print $2}'" % dev).strip()

    for entry in o.split('" '):  # type: str
        if entry.startswith("VENDOR"):
            s.vendor = get_data(entry)
        elif entry.startswith("MODEL"):
            s.model = get_data(entry)
        elif entry.startswith("WWN"):
            s.wwn = get_data(entry)
        elif entry.startswith("SERIAL"):
            s.serial = get_data(entry)
        elif entry.startswith('HCTL'):
            s.hctl = get_data(entry)
        elif entry.startswith('SIZE'):
            s.size = get_data(entry)
        elif entry.startswith('TYPE'):
            s.type = get_data(entry)

    s.wwids = get_wwids(dev_name)
    s.path = get_path(dev_name)
    return s


def calcLvReservedSize(size):
    # NOTE(weiw): Add additional 12M for every lv
    size = int(size) + 3 * LV_RESERVED_SIZE
    # NOTE(weiw): Add additional 4M per 4GB for qcow2 potential use
    size = int(size) + (size/1024/1024/1024/4) * LV_RESERVED_SIZE
    return size


def getOriginalSize(size):
    size = int(size) - (int(size) / 1024 / 1024 / 1024 / 4) * LV_RESERVED_SIZE
    size = int(size) - 3 * LV_RESERVED_SIZE
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
    cmd = shell.ShellCmd("sync")
    cmd(is_exception=False)


def config_sanlock_by_sed(keyword, entry):
    if not os.path.exists(SANLOCK_CONFIG_FILE_PATH):
        raise Exception("can not find sanlock config path: %s, config sanlock failed" % LVM_CONFIG_PATH)

    cmd = shell.ShellCmd("sed -i 's/.*%s.*/%s/g' %s" %
                         (keyword, entry, SANLOCK_CONFIG_FILE_PATH))
    cmd(is_exception=False)
    cmd = shell.ShellCmd("sync")
    cmd(is_exception=False)


def config_lvmlockd_by_sed():
    cmd = shell.ShellCmd(
        "sed -i 's/.*ExecStart=.*/ExecStart=\\/usr\\/sbin\\/lvmlockd --daemon-debug --sanlock-timeout %s/g' /usr/lib/systemd/system/lvm2-lvmlockd.service" % SANLOCK_IO_TIMEOUT)
    cmd(is_exception=False)

    if bash.bash_r("grep StandardOutput /usr/lib/systemd/system/lvm2-lvmlockd.service") != 0:
        cmd = shell.ShellCmd(
            "sed -i '/ExecStart/a StandardOutput=%s' /usr/lib/systemd/system/lvm2-lvmlockd.service" % LVMLOCKD_LOG_FILE_PATH)
        cmd(is_exception=False)

    if bash.bash_r("grep StandardError /usr/lib/systemd/system/lvm2-lvmlockd.service") != 0:
        cmd = shell.ShellCmd(
            "sed -i '/ExecStart/a StandardError=%s' /usr/lib/systemd/system/lvm2-lvmlockd.service" % LVMLOCKD_LOG_FILE_PATH)
        cmd(is_exception=False)
    cmd = shell.ShellCmd("sync")
    cmd(is_exception=False)


def config_lvm_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --mergedconfig --config %s=%s -f /etc/lvm/lvm.conf" % (node, value))
    cmd(is_exception=True)


def config_lvmlocal_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --mergedconfig --config %s=%s -f /etc/lvm/lvmlocal.conf" % (node, value))
    cmd(is_exception=True)


@bash.in_bash
def start_lvmlockd():
    if not os.path.exists(os.path.dirname(LVMLOCKD_LOG_FILE_PATH)):
        os.mkdir(os.path.dirname(LVMLOCKD_LOG_FILE_PATH))

    config_lvmlockd_by_sed()
    for service in ["wdmd", "sanlock", "lvm2-lvmlockd"]:
        cmd = shell.ShellCmd("systemctl start %s" % service)
        cmd(is_exception=True)

    if not os.path.exists(LVMLOCKD_LOG_LOGROTATE_PATH):
        content = """/var/log/lvmlockd/lvmlockd.log {
    rotate 5
    missingok
    copytruncate
    size 30M
    compress
    compresscmd /usr/bin/xz
    uncompresscmd /usr/bin/unxz
    compressext .xz
}"""
        with open(LVMLOCKD_LOG_LOGROTATE_PATH, 'w') as f:
            f.write(content)
        cmd = shell.ShellCmd("sync")
        cmd(is_exception=False)


@bash.in_bash
def start_vg_lock(vgUuid):
    @linux.retry(times=60, sleep_time=random.uniform(1, 10))
    def vg_lock_is_adding(vgUuid):
        # NOTE(weiw): this means vg locking is adding rather than complete
        return_code = bash.bash_r("sanlock client status | grep -E 's lvm_%s.*\\:0 ADD'" % vgUuid)
        if return_code == 0:
            raise RetryException("vg %s lock space is starting" % vgUuid)
        return False

    @linux.retry(times=15, sleep_time=random.uniform(0.1, 2))
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


@bash.in_bash
def drop_vg_lock(vgUuid):
    bash.bash_roe("lvmlockctl --drop %s" % vgUuid)


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


@bash.in_bash
def backup_super_block(disk_path):
    wwid = get_wwid(disk_path)
    if wwid is None or wwid == "":
        logger.warn("can not get wwid of disk %s" % disk_path)

    current_time = time.time()
    disk_back_file = os.path.join(LVM_CONFIG_BACKUP_PATH, "%s.%s.%s" % (wwid, SUPER_BLOCK_BACKUP, current_time))
    bash.bash_roe("dd if=%s of=%s bs=64KB count=1 conv=notrunc" % (disk_path, disk_back_file))
    return disk_back_file


@bash.in_bash
def wipe_fs(disks, expected_vg=None):
    for disk in disks:
        exists_vg = None
        r = bash.bash_r("pvdisplay %s | grep %s" % (disk, expected_vg))
        if r == 0:
            continue

        r, o = bash.bash_ro("pvs --nolocking --noheading -o vg_name %s" % disk)
        if r == 0 and o.strip() != "":
            exists_vg = o.strip()

        backup = backup_super_block(disk)
        if bash.bash_r("grep %s %s" % (expected_vg, backup)) == 0:
            raise Exception("found vg uuid in superblock backup while not found in lvm command!")
        need_flush_mpath = False

        bash.bash_roe("partprobe -s %s" % disk)

        cmd_type = bash.bash_o("lsblk %s -oTYPE | grep mpath" % disk)
        if cmd_type.strip() != "":
            need_flush_mpath = True

        bash.bash_roe("wipefs -af %s" % disk)

        if need_flush_mpath:
            bash.bash_roe("multipath -f %s && systemctl restart multipathd.service && sleep 1" % disk)

        if exists_vg is not None:
            logger.debug("found vg %s exists on this pv %s, start wipe" %
                         (exists_vg, disk))
            try:
                drop_vg_lock(exists_vg)
                remove_device_map_for_vg(exists_vg)
            finally:
                pass


@bash.in_bash
@linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
def add_pv(vg_uuid, disk_path, metadata_size):
    bash.bash_errorout("vgextend --metadatasize %s %s %s" % (metadata_size, vg_uuid, disk_path))
    if bash.bash_r("pvs --nolocking --readonly %s | grep %s" % (disk_path, vg_uuid)):
        raise Exception("disk %s not added to vg %s after vgextend" % (disk_path, vg_uuid))


def get_vg_size(vgUuid, raise_exception=True):
    cmd = shell.ShellCmd("vgs --nolocking --readonly %s --noheadings --separator : --units b -o vg_size,vg_free" % vgUuid)
    cmd(is_exception=raise_exception)
    if cmd.return_code != 0:
        return None, None
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
    cmd = shell.ShellCmd("vgs %s -otags --nolocking --noheading | tr ',' '\n' | grep %s | grep %s" % (vgUuid, tag, hostUuid))
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


def create_lv_from_cmd(path, size, cmd, tag="zs::sharedblock::volume"):
    if cmd.provisioning == VolumeProvisioningStrategy.ThinProvisioning and size > cmd.addons[thinProvisioningInitializeSize]:
        create_lv_from_absolute_path(path, cmd.addons[thinProvisioningInitializeSize], tag)
    else:
        create_lv_from_absolute_path(path, size, tag)


def dd_zero(path):
    cmd = shell.ShellCmd("dd if=/dev/zero of=%s bs=65536 count=1 conv=sync,notrunc" % path)
    cmd(is_exception=False)


def get_lv_size(path):
    cmd = shell.ShellCmd("lvs --nolocking --readonly --noheading -osize --units b %s" % path)
    cmd(is_exception=True)
    return cmd.stdout.strip().strip("B")


@bash.in_bash
def resize_lv(path, size):
    r, o, e = bash.bash_roe("lvresize --size %sb %s" % (calcLvReservedSize(size), path))
    if r == 0:
        return
    elif "matches existing size" in e or "matches existing size" in o:
        return
    else:
        raise Exception("resize lv %s to size %s failed, return code: %s, stdout: %s, stderr: %s" %
                        (path, size, r, o, e))


@bash.in_bash
def resize_lv_from_cmd(path, size, cmd):
    if cmd.provisioning != VolumeProvisioningStrategy.ThinProvisioning:
        resize_lv(path, size)

    current_size = int(get_lv_size(path))
    if int(size) - current_size > cmd.addons[thinProvisioningInitializeSize]:
        resize_lv(path, current_size + cmd.addons[thinProvisioningInitializeSize])
    else:
        resize_lv(path, size)


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
def remove_device_map_for_vg(vgUuid):
    o = bash.bash_o("dmsetup ls | grep %s | awk '{print $1}'" % vgUuid).strip().splitlines()
    if len(o) == 0:
        return
    for dm in o:
        bash.bash_roe("dmsetup remove %s" % dm.strip())


@bash.in_bash
def lv_exists(path):
    r = bash.bash_r("lvs --nolocking --readonly %s" % path)
    return r == 0


@bash.in_bash
def vg_exists(vgUuid):
    cmd = shell.ShellCmd("vgs --nolocking %s" % (vgUuid))
    cmd(is_exception=False)
    return cmd.return_code == 0


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


@bash.in_bash
def check_gl_lock(raise_exception=False):
    r = bash.bash_r("lvmlockctl -i | grep 'LK GL'")
    if r == 0:
        return
    logger.debug("can not find any gl lock")

    r, o = bash.bash_ro("lvmlockctl -i | grep 'lock_type=sanlock' | awk '{print $2}'")
    if len(o.strip().splitlines()) != 0:
        for i in o.strip().splitlines():
            if i == "":
                continue
            r, o, e = bash.bash_roe("lvmlockctl --gl-enable %s" % i)
            if r != 0:
                raise Exception("failed to enable gl lock on vg: %s, %s, %s" % (i, o, e))

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

    if recursive is False or lockType is LvmlockdLockType.NULL:
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


def get_lockspace(vgUuid):
    output = bash.bash_o("sanlock client gets | awk '{print $2}' | grep %s" % vgUuid)
    return output.strip()


def examine_lockspace(lockspace):
    r = bash.bash_r("sanlock client examine -s %s" % lockspace)
    if r != 0:
        logger.warn("sanlock examine %s failed, return %s" % (lockspace, r))
        return r
    # r = bash.bash_r("sanlock direct read_leader -s %s" % lockspace)
    # if r != 0:
    #     logger.warn("sanlock read leader %s failed, return %s" % (lockspace, r))
    return r


def check_stuck_vglk():
    @linux.retry(3, 0.1)
    def is_stuck_vglk():
        r, o, e = bash.bash_roe("sanlock client status | grep ':VGLK:'")
        if r != 0:
            return
        else:
            raise RetryException("found sanlock vglk lock stuck")
    try:
        is_stuck_vglk()
    except Exception as e:
        r, o, e = bash.bash_roe("sanlock client status | grep ':VGLK:'")
        if r != 0:
            return
        if len(o.strip().splitlines()) == 0:
            return
        for stucked in o.strip().splitlines():  # type: str
            if "ADD" in stucked or "REM" in stucked:
                continue
            cmd = "sanlock client release -%s" % stucked.replace(" p ", " -p ")
            r, o, e = bash.bash_roe(cmd)
            logger.warn("find stuck vglk and already released, detail: [return_code: %s, stdout: %s, stderr: %s]" %
                        (r, o, e))


@bash.in_bash
def fix_global_lock():
    if not ENABLE_DUP_GLOBAL_CHECK:
        return
    vg_names = bash.bash_o("lvmlockctl -i | grep lock_type=sanlock | awk '{print $2}'").strip().splitlines()  # type: list
    vg_names.sort()
    if len(vg_names) < 2:
        return
    for vg_name in vg_names[1:]:
        bash.bash_roe("lvmlockctl --gl-disable %s" % vg_name)
    bash.bash_roe("lvmlockctl --gl-enable %s" % vg_names[0])


def check_pv_status(vgUuid, timeout):
    r, o , e = bash.bash_roe("timeout -s SIGKILL %s pvs --noheading --nolocking -Svg_name=%s -oname,missing" % (timeout, vgUuid))
    if len(o) == 0 or r != 0:
        s = "can not find shared block in shared block group %s, detail: [return_code: %s, stdout: %s, stderr: %s]" % (vgUuid, r, o, e)
        logger.warn(s)
        return False, s
    for pvs_out in o:
        if "unknown" in pvs_out:
            s = "disk in shared block group %s missing" % vgUuid
            logger.warn("%s, details: %s" % (s, o))
            return False, s
        if "missing" in pvs_out:
            s = "disk %s in shared block group %s exists but state is missing" % (pvs_out.strip().split(" ")[0], vgUuid)
            logger.warn("%s, details: %s" % (s, o))
            return False, s

    r, s = lvm_vgck(vgUuid, timeout)
    if r is False:
        return r, s

    health = bash.bash_o('timeout -s SIGKILL %s vgs -oattr --nolocking --readonly --noheadings --shared %s ' % (10 if timeout < 10 else timeout, vgUuid)).strip()
    if health == "":
        logger.warn("can not get proper attr of vg, return false")
        return False, "primary storage %s attr get error, expect 'wz--ns' got %s" % (vgUuid, health)

    if health[0] != "w":
        return False, "primary storage %s permission error, expect 'w' but now is %s, deatils: %s" % (vgUuid, health.stdout.strip()[0], health)

    if health[1] != "z":
        return False, "primary storage %s resizeable error, expect 'z' but now is %s, deatils: %s" % (vgUuid, health.stdout.strip()[1], health)

    if health[3] != "-":
        return False, "primary storage %s partial error, expect '-' but now is %s, deatils: %s" % (vgUuid, health.stdout.strip()[3], health)

    if health[5] != "s":
        return False, "primary storage %s shared mode error, expect 's' but now is %s, deatils: %s" % (vgUuid, health.stdout.strip()[5], health)

    return True, ""


def lvm_vgck(vgUuid, timeout):
    health, o, e = bash.bash_roe('timeout -s SIGKILL %s vgck %s 2>&1' % (15 if timeout < 15 else timeout, vgUuid))
    check_stuck_vglk()

    if health != 0:
        s = "vgck %s failed, detail: [return_code: %s, stdout: %s, stderr: %s]" % (vgUuid, health, o, e)
        logger.warn(s)
        return False, s

    if o is not None and o != "":
        for es in o.strip().splitlines():
            if "WARNING" in es:
                continue
            if "Duplicate sanlock global lock" in es:
                fix_global_lock()
                continue
            if es.strip() == "":
                continue
            s = "vgck %s failed, details: %s" % (vgUuid, o)
            logger.warn(s)
            return False, s
    return True, ""


def check_vg_status(vgUuid, check_timeout, check_pv=True):
    # type: (str) -> tuple[bool, str]
    # 1. examine sanlock lock
    # 2. check the consistency of volume group
    # 3. check ps missing
    # 4. check vg attr
    lock_space = get_lockspace(vgUuid)
    if lock_space == "":
        s = "can not find lockspace of %s" % vgUuid
        logger.warn(s)
        return False, s

    r, s = check_sanlock_renewal_failure(lock_space)
    if r is False:
        return r, s

    r, s = check_sanlock_status(lock_space)
    if r is False:
        return r, s

    if examine_lockspace(lock_space) != 0:
        return False, "examine lockspace %s failed" % lock_space

    if not set_sanlock_event(lock_space):
        return False, "sanlock set event on lock space %s failed" % lock_space

    if not check_pv:
        return True, ""

    return check_pv_status(vgUuid, check_timeout)


def set_sanlock_event(lockspace):
    """

    :type lockspace: str
    """
    host_id = lockspace.split(":")[1]
    r, o, e = bash.bash_roe("sanlock client set_event -s %s -i %s -e 1 -d 1" % (lockspace, host_id))
    return r == 0


def get_sanlock_renewal(lockspace):
    r, o, e = bash.bash_roe("sanlock client renewal -s %s" % lockspace)
    return o.strip().splitlines()[-1]


def check_sanlock_renewal_failure(lockspace):
    last_record = linux.wait_callback_success(get_sanlock_renewal, lockspace, 10, 1, True)
    if last_record is False:
        logger.warn("unable find correct sanlock renewal record, may be rotated")
        return True
    if "next_errors=" not in last_record:
        return True, ""
    errors = int(last_record.split("next_errors=")[-1])
    if errors > 2:
        return False, "sanlock renew lease of lockspace %s failed for %s times, storage may failed" % (
        lockspace, errors)
    return True, ""


def check_sanlock_status(lockspace):
    r, o, e = bash.bash_roe("sanlock client status -D | grep %s -A 18" % lockspace)
    if r != 0:
        return False, "sanlock can not get lockspace %s status" % lockspace

    renewal_last_result = 0
    renewal_last_attempt = 0
    renewal_last_success = 0
    for i in o.strip().splitlines():
        if "renewal_last_result" in i:
            renewal_last_result = int(i.strip().split("=")[-1])
        if "renewal_last_attempt" in i:
            renewal_last_attempt = int(i.strip().split("=")[-1])
        if "renewal_last_success" in i:
            renewal_last_success = int(i.strip().split("=")[-1])
    if renewal_last_result != 1:
        if (renewal_last_attempt > renewal_last_success and renewal_last_attempt - renewal_last_success > 100) or (
                100 < renewal_last_attempt < renewal_last_success - 100 < renewal_last_success):
            return False, "sanlock last renewal failed with %s and last attempt is %s, last success is %s" % (
                renewal_last_result, renewal_last_attempt, renewal_last_success)
    return True, ""


@bash.in_bash
def get_pv_name_by_uuid(pvUuid):
    return bash.bash_o(
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -oname -Spv_uuid=%s" % pvUuid).strip()


@bash.in_bash
def get_pv_uuid_by_path(pvPath):
    return bash.bash_o(
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -ouuid %s" % pvPath).strip()


@bash.in_bash
def check_lv_on_pv_valid(vgUuid, pvUuid, lv_path=None):
    pv_name = bash.bash_o(
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -oname -Spv_uuid=%s" % pvUuid).strip()
    one_active_lv = lv_path if lv_path is not None else bash.bash_o(
        "timeout -s SIGKILL 10 lvs --noheading --nolocking -opath,devices,tags " +
        "-Sactive=active %s | grep %s | grep %s | awk '{print $1}' | head -n1" % (vgUuid, pv_name, VOLUME_TAG)).strip()
    if one_active_lv == "":
        return True
    r = bash.bash_r("qemu-img info %s" % one_active_lv)
    if r != 0:
        return False
    return True


@bash.in_bash
def get_invalid_pv_uuids(vgUuid, checkIo = False):
    invalid_pv_uuids = []
    pvs_outs = bash.bash_o(
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -Svg_name=%s -ouuid,name,missing" % vgUuid).strip().split("\n")
    if len(pvs_outs) == 0:
        return
    for pvs_out in pvs_outs:
        pv_uuid = pvs_out.strip().split(" ")[0]
        if "unknown" in pvs_out:
            invalid_pv_uuids.append(pv_uuid)
        elif "missing" in pvs_out:
            invalid_pv_uuids.append(pv_uuid)
        elif checkIo is True and check_lv_on_pv_valid(vgUuid, pv_uuid) is False:
            invalid_pv_uuids.append(pv_uuid)

    return invalid_pv_uuids


@bash.in_bash
def is_volume_on_pvs(volume_path, pvUuids, includingMissing=True):
    files = linux.qcow2_get_file_chain(volume_path)
    if len(files) == 0:
        # could not read qcow2
        logger.debug("can not read volume %s, return true" % volume_path)
        return True
    pv_names = []
    for p in pvUuids:
        name = get_pv_name_by_uuid(p)
        if name != "":
            pv_names.append(get_pv_name_by_uuid(p) + "(")

    if includingMissing:
        pv_names.append("unknown")
    for f in files:
        o = bash.bash_o(
            "timeout -s SIGKILL 10 lvs --noheading --nolocking %s -odevices" % f).strip().lower()  # type: str
        logger.debug("volume %s is on pv %s" % (volume_path, o))
        if len(filter(lambda n: o.find(n.lower()) > 0, pv_names)) > 0:
            logger.debug("lv %s on pv %s(%s), return true" % (volume_path, pvUuids, pv_names))
            return True
        if o == "" and includingMissing:
            logger.debug("pv of lv %s is missing, return true")
            return True
    return False


@bash.in_bash
def get_running_vm_root_volume_on_pv(vgUuid, pvUuids, checkIo=True):
    # 1. get "-drive ... -device ... bootindex=1,
    # 2. get "-boot order=dc ... -drive id=drive-virtio-disk"
    # 3. make sure io has error
    # 4. filter for pv
    out = bash.bash_o("pgrep -a qemu-kvm | grep %s" % vgUuid).strip().split("\n")
    if len(out) == 0:
        return []

    vms = []
    for o in out:
        vm = VmStruct()
        vm.pid = o.split(" ")[0]
        vm.cmdline = o.split(" ", 3)[-1]
        vm.uuid = o.split(" -uuid ")[-1].split(" ")[0]
        if "bootindex=1" in vm.cmdline:
            vm.root_volume = vm.cmdline.split("bootindex=1")[0].split(" -drive file=")[-1].split(",")[0]
        elif " -boot order=dc" in vm.cmdline:
            # TODO(weiw): maybe support scsi volume as boot volume one day
            vm.root_volume = vm.cmdline.split("id=drive-virtio-disk0")[0].split(" -drive file=")[-1].split(",")[0]
        else:
            logger.warn("found strange vm[pid: %s, cmdline: %s], can not find boot volume" % (vm.pid, vm.cmdline))
            continue

        r = bash.bash_r("qemu-img info --backing-chain %s" % vm.root_volume)
        if checkIo is True and r == 0:
            logger.debug("volume %s for vm %s io success, skiped" % (vm.root_volume, vm.uuid))
            continue

        out = bash.bash_o("virsh dumpxml %s | grep \"source file='/dev/\"" % vm.uuid).strip().splitlines()
        if len(out) != 0:
            for file in out:
                vm.volumes.append(file.strip().split("'")[1])

        if is_volume_on_pvs(vm.root_volume, pvUuids, True):
            vms.append(vm)

    return vms


@bash.in_bash
def remove_partial_lv_dm(vgUuid):
    o = bash.bash_o("lvs --noheading --nolocking --readonly %s -opath,tags -Slv_health_status=partial | grep %s" % (vgUuid, COMMON_TAG)).strip().splitlines()
    if len(o) == 0:
        return

    for volume in o:
        bash.bash_roe("dmsetup remove %s" % volume.strip().split(" ")[0])


@bash.in_bash
def unpriv_sgio():
    bash.bash_roe("for i in `ls /sys/block/`; do echo 1 > /sys/block/$i/queue/unpriv_sgio; done")


@bash.in_bash
@linux.retry(times=3, sleep_time=1)
def enable_multipath():
    bash.bash_roe("modprobe dm-multipath")
    bash.bash_roe("modprobe dm-round-robin")
    bash.bash_roe("mpathconf --enable --with_multipathd y")
    bash.bash_roe("systemctl enable multipathd")
    if not is_multipath_running():
        raise RetryException("multipath still not running")
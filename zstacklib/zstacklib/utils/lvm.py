import functools
import random
import os
import os.path
import time
import re
import xml.etree.ElementTree as etree

import simplejson

from zstacklib.utils import form
from zstacklib.utils import shell
from zstacklib.utils import bash
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import linux
from zstacklib.utils import qemu_img
from zstacklib.utils import thread
from distutils.version import LooseVersion

logger = log.get_logger(__name__)
LV_RESERVED_SIZE = 1024*1024*4
LVM_CONFIG_PATH = "/etc/lvm"
LVM_CONFIG_FILE = '/etc/lvm/lvm.conf'
SANLOCK_CONFIG_FILE_PATH = "/etc/sanlock/sanlock.conf"
DEB_SANLOCK_CONFIG_FILE_PATH = "/etc/default/sanlock"
LIVE_LIBVIRT_XML_DIR = "/var/run/libvirt/qemu"
SANLOCK_IO_TIMEOUT = 40
LVMLOCKD_LOG_FILE_PATH = "/var/log/lvmlockd/lvmlockd.log"
LVMLOCKD_LOG_RSYSLOG_PATH = "/etc/rsyslog.d/lvmlockd.conf"
LVMLOCKD_SERVICE_PATH = "/lib/systemd/system/lvm2-lvmlockd.service"
LVMLOCKD_LOG_LOGROTATE_PATH = "/etc/logrotate.d/lvmlockd"
LVMLOCKD_ADOPT_FILE = "/run/lvm/lvmlockd.adopt"
LVM_CONFIG_BACKUP_PATH = "/etc/lvm/zstack-backup"
LVM_CONFIG_ARCHIVE_PATH = "/etc/lvm/archive"
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
        self.xml = ""
        self.root_volume = ""
        self.uuid = ""
        self.volumes = []

    def load_from_xml(self, xml):
        def load_source(element):
            is_root_vol = False
            path = None
            for e in element:
                if e.tag == "boot":
                    is_root_vol = True
                elif e.tag == "source":
                    if "file" in e.attrib:
                        path = e.attrib["file"]
                    elif "dev" in e.attrib:
                        path = e.attrib["dev"]
                    if path and path.startswith("/dev/"):
                        self.volumes.append(path)

            if is_root_vol:
                self.root_volume = path

        self.xml = xml
        root = etree.fromstring(xml)
        for e1 in root:
            if e1.tag == "domain":
                for e2 in e1:
                    if e2.tag == "devices":
                        for e3 in e2:
                            if e3.tag == "disk":
                                load_source(e3)
                        return

class LvmlockdLockType(object):
    NULL = 0
    SHARE = 1
    EXCLUSIVE = 2

    @staticmethod
    def from_abbr(abbr, raise_exception=False):
        if abbr.strip() == "sh":
            return LvmlockdLockType.SHARE
        elif abbr.strip() == "ex":
            return LvmlockdLockType.EXCLUSIVE
        elif abbr.strip() == "un":
            return LvmlockdLockType.NULL
        elif abbr.strip() == "":
            if raise_exception:
                raise RetryException("can not get locking type sice it is active without lvmlock info")
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
    # 1. get multi path devices information
    block_devices, slave_devices = get_mpath_block_devices()
    # 2. get information of other devices
    block_devices.extend(get_disk_block_devices(slave_devices))

    return block_devices

def get_mpath_block_devices():
    slave_devices = []
    mpath_devices = []

    cmd = shell.ShellCmd("multipath -l -v1")
    cmd(is_exception=False)
    if cmd.return_code == 0 and cmd.stdout.strip() != "":
        mpath_devices = cmd.stdout.strip().split("\n")

    block_devices_list = [None] * len(mpath_devices)

    def get_block_devices(slave, dm, i):
        try:
            struct = get_device_info(slave)
            if struct is None:
                return
            cmd = shell.ShellCmd(
                "udevadm info -n %s | grep dm-uuid-mpath | grep -o 'dm-uuid-mpath-\S*' | head -n 1 | awk -F '-' '{print $NF}'" % dm)
            cmd(is_exception=True)
            struct.wwids = [cmd.stdout.strip().strip("()")]
            struct.type = "mpath"
            block_devices_list[i] = struct
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            return

    threads = []
    for idx, mpath_device in enumerate(mpath_devices, start=0):
        try:
            cmd = shell.ShellCmd("realpath /dev/mapper/%s | grep -E -o 'dm-.*'" % mpath_device)
            cmd(is_exception=False)
            if cmd.return_code != 0 or cmd.stdout.strip() == "":
                continue

            dm = cmd.stdout.strip()
            slaves = shell.call("ls /sys/class/block/%s/slaves/" % dm).strip().split("\n")
            if slaves is None or len(slaves) == 0:
                struct = SharedBlockCandidateStruct()
                cmd = shell.ShellCmd(
                    "udevadm info -n %s | grep dm-uuid-mpath | grep -o 'dm-uuid-mpath-\S*' | head -n 1 | awk -F '-' '{print $NF}'" % dm)
                cmd(is_exception=True)
                struct.wwids = [cmd.stdout.strip().strip("()")]
                struct.type = "mpath"
                block_devices_list[idx] = struct
                continue

            slave_devices.extend(slaves)
            threads.append(thread.ThreadFacade.run_in_thread(get_block_devices, [slaves[0], dm, idx]))
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            continue

    for t in threads:
        t.join()

    return filter(None, block_devices_list), slave_devices

def get_disk_block_devices(slave_devices):
    disks = shell.call("lsblk -p -o NAME,TYPE | grep disk | awk '{print $1}'").strip().split()
    block_devices_list = [None] * len(disks)

    def get_block_devices(disk, i):
        try:
            d = get_device_info(disk.strip().split("/")[-1])
            if d is None:
                return
            if len(d.wwids) is 0:
                return
            if get_pv_uuid_by_path("/dev/disk/by-id/%s" % d.wwids[0]) not in ("", None):
                d.type = "lvm-pv"
            block_devices_list[i] = d
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            return

    threads = []
    for idx, disk in enumerate(disks, start=0):
        try:
            if disk.split("/")[-1] in slave_devices or is_slave_of_multipath(disk):
                continue
            threads.append(thread.ThreadFacade.run_in_thread(get_block_devices, [disk, idx]))
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            continue

    for t in threads:
        t.join()

    return filter(None, block_devices_list)

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

def get_scsi_id(dev_path):
    return bash.bash_o("/usr/lib/udev/scsi_id -g -u -d %s" % dev_path).strip()

def get_multipath_dmname(dev_name):
    # if is multipath dev, return;
    # if is one of multipath paths, return multipath dev(dm-xxx);
    # else return None
    slaves = shell.call("ls /sys/class/block/%s/slaves/" % dev_name).strip().splitlines()
    if slaves is not None and len(slaves) > 0 and slaves[0].strip() != "":
        return dev_name

    r = bash.bash_r("multipath /dev/%s -l | grep policy" % dev_name)
    if r != 0:
        return None
    o = bash.bash_o("multipath -l /dev/%s | head -n1 | awk -F 'dm' '{print $2}' | awk '{print $1}'" % dev_name).strip()
    return "dm%s" % o


def get_multipath_name(dev_name):
    return bash.bash_o("multipath /dev/%s -l -v1" % dev_name).strip()

def get_lvmlockd_service_name():
    service_name = 'lvm2-lvmlockd.service'
    lvmlockd_version = shell.call("""lvmlockd --version | awk '{print $3}' | awk -F'.' '{print $1"."$2}'""").strip()
    if LooseVersion(lvmlockd_version) > LooseVersion("2.02"):
        service_name = 'lvmlockd.service'
    return service_name

def get_lvmlockd_version():
    global LVMLOCKD_VERSION
    if LVMLOCKD_VERSION is None:
        LVMLOCKD_VERSION = shell.call("""lvmlockd --version | awk '{print $3}' | awk -F'.' '{print $1"."$2}'""").strip()
    return LVMLOCKD_VERSION

def get_running_lvmlockd_version():
    pid = get_lvmlockd_pid()
    if pid:
        exe = "/proc/%s/exe" % pid
        return shell.call("""%s --version | awk '{print $3}' | awk -F'.' '{print $1"."$2}'""" % exe).strip()

def get_lvmlockd_pid():
    return shell.call("""ps x | awk '/sbin\/lvmlockd/{print $1; exit}'""").strip()

def get_device_info(dev_name):
    s = SharedBlockCandidateStruct()
    r, o, e = bash.bash_roe("lsblk --pair -b -p -o NAME,VENDOR,MODEL,WWN,SERIAL,HCTL,TYPE,SIZE /dev/%s" % dev_name, False)
    if r != 0 or o.strip() == "":
        logger.warn("can not get device information from %s" % dev_name)
        return None

    def get_data(e):
        return e.split("=")[1].strip().strip('"')

    def get_wwids(dev):
        return shell.call("udevadm info -n %s | grep 'by-id' | grep -v DEVLINKS | awk -F 'by-id/' '{print $2}'" % dev).strip().split()

    def get_path(dev):
        return shell.call("udevadm info -n %s | grep 'by-path' | grep -v DEVLINKS | head -n1 | awk -F 'by-path/' '{print $2}'" % dev).strip()

    for entry in o.strip().split("\n")[0].split('" '):  # type: str
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

    for f in files:
        cmd = shell.ShellCmd("sed -i 's/.*\\b%s\\b.*/%s/g' %s/%s" %
                             (keyword, entry, LVM_CONFIG_PATH, f))
        cmd(is_exception=False)
    logger.debug(bash.bash_o("lvmconfig --type diff"))


@bash.in_bash
def config_lvm_filter(files, no_drbd=False, preserve_disks=None):
    # type: (list[str], bool, set[str]) -> object
    if not os.path.exists(LVM_CONFIG_PATH):
        raise Exception("can not find lvm config path: %s, config lvm failed" % LVM_CONFIG_PATH)

    if preserve_disks is not None and len(preserve_disks) != 0:
        filter_str = 'filter=['
        for disk in preserve_disks:
            filter_str += '"a|^%s$|", ' % disk.replace("/", "\\/")
        filter_str += '"r\/.*\/"]'

        for f in files:
            bash.bash_r("sed -i 's/.*\\b%s.*/%s/g' %s/%s" % ("filter", filter_str, LVM_CONFIG_PATH, f))
            bash.bash_r("sed -i 's/.*\\b%s.*/global_%s/g' %s/%s" % ("global_filter", filter_str, LVM_CONFIG_PATH, f))
        linux.sync_file(LVM_CONFIG_FILE)
        return

    filter_str = 'filter=["r|\\/dev\\/cdrom|"'
    vgs = bash.bash_o("vgs --nolocking -t -oname --noheading").splitlines()
    for vg in vgs:
        filter_str += ', "r\\/dev\\/mapper\\/%s.*\\/"' % vg.strip()
    if no_drbd:
        filter_str += ', "r\\/dev\\/drbd.*\\/"'

    filter_str += ']'

    for f in files:
        bash.bash_r("sed -i 's/.*\\b%s.*/%s/g' %s/%s" % ("filter", filter_str, LVM_CONFIG_PATH, f))
    linux.sync_file(LVM_CONFIG_FILE)


def modify_sanlock_config(key, value):
    if not os.path.exists(SANLOCK_CONFIG_FILE_PATH) and os.path.exists(DEB_SANLOCK_CONFIG_FILE_PATH):
        global SANLOCK_CONFIG_FILE_PATH
        SANLOCK_CONFIG_FILE_PATH = DEB_SANLOCK_CONFIG_FILE_PATH
    if not os.path.exists(os.path.dirname(SANLOCK_CONFIG_FILE_PATH)):
        linux.mkdir(os.path.dirname(SANLOCK_CONFIG_FILE_PATH))
    if not os.path.exists(SANLOCK_CONFIG_FILE_PATH):
        raise Exception("can not find sanlock config path: %s, config sanlock failed" % SANLOCK_CONFIG_FILE_PATH)
    with open(SANLOCK_CONFIG_FILE_PATH,'r') as r:
        lines=r.readlines()
    with open(SANLOCK_CONFIG_FILE_PATH,'w') as w:
        value_with_key = key + ' = ' + str(value)
        find_key = False
        need_delete_line = False
        for line in lines:
            # pure_line is line without comment and space
            pure_line = line.replace('#', '')
            pure_line = pure_line.replace(' ', '')
            if pure_line.startswith(key):
                if find_key is True:
                    # more than one key in config file, so delete it
                    need_delete_line = True
                else:
                    find_key = True
                line = line.replace(line, value_with_key)
                if need_delete_line is False:
                    # change line: modify value if key exist && unique
                    w.write(value_with_key)
                    w.write('\n')
                else:
                    # do nothing to delete, and reset the value
                    need_delete_line = False
            else:
                w.write(line)
        if find_key is False:
            # change line: add "key = value" if key not exist
            w.write('\n')
            w.write(value_with_key)


def config_lvmlockd(io_timeout=40):
    content = """[Unit]
Description=LVM2 lock daemon
Documentation=man:lvmlockd(8)
After=lvm2-lvmetad.service

[Service]
Type=simple
NonBlocking=true
ExecStart=/sbin/lvmlockd --daemon-debug --sanlock-timeout %s --adopt 1
StandardError=syslog
StandardOutput=syslog
SyslogIdentifier=lvmlockd
Environment=SD_ACTIVATION=1
PIDFile=/run/lvmlockd.pid
SendSIGKILL=no

[Install]
WantedBy=multi-user.target
""" % io_timeout
    lvmlockd_service_path = os.path.join("/lib/systemd/system", get_lvmlockd_service_name())
    with open(lvmlockd_service_path, 'w') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(lvmlockd_service_path, 0644)

    if not os.path.exists(LVMLOCKD_LOG_RSYSLOG_PATH):
        content = """if $programname == 'lvmlockd' then %s 
& stop
""" % LVMLOCKD_LOG_FILE_PATH
        with open(LVMLOCKD_LOG_RSYSLOG_PATH, 'w') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(LVMLOCKD_LOG_RSYSLOG_PATH, 0644)
        shell.call("systemctl restart rsyslog", exception=False)

    cmd = shell.ShellCmd("systemctl daemon-reload")
    cmd(is_exception=False)


def config_lvm_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --mergedconfig --config %s=%s -f /etc/lvm/lvm.conf" % (node, value))
    cmd(is_exception=True)


def config_lvmlocal_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --mergedconfig --config %s=%s -f /etc/lvm/lvmlocal.conf" % (node, value))
    cmd(is_exception=True)


@bash.in_bash
def start_lvmlockd(io_timeout=40):
    if not os.path.exists(os.path.dirname(LVMLOCKD_LOG_FILE_PATH)):
        os.mkdir(os.path.dirname(LVMLOCKD_LOG_FILE_PATH))

    config_lvmlockd(io_timeout)
    running_lockd_version = get_running_lvmlockd_version()
    if running_lockd_version and LooseVersion(running_lockd_version) < LooseVersion(get_lvmlockd_version()):
        write_lvmlockd_adopt_file()
        stop_lvmlockd()
    for service in ["sanlock", get_lvmlockd_service_name()]:
        cmd = shell.ShellCmd("timeout 30 systemctl start %s" % service)
        cmd(is_exception=True)

    content = """/var/log/lvmlockd/lvmlockd.log {
    rotate 15
    missingok
    copytruncate
    size 30M
    su root root
    compress
    compresscmd /usr/bin/xz
    uncompresscmd /usr/bin/unxz
    compressext .xz
}"""
    with open(LVMLOCKD_LOG_LOGROTATE_PATH, 'w') as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(LVMLOCKD_LOG_LOGROTATE_PATH, 0644)

def write_lvmlockd_adopt_file():
    def _get_lockspace_name(line):
        return line.split()[1].split(":")[0]

    class Lock:
        def __init__(self, line):
            ## line format: r lvm_8c8b0ad64b0e42f4a9792db1f2bbacd8:OGDB3v-DKJ9-kdYX-XO7p-7cEp-jK22-jm1sgp:/dev/mapper/8c8b0ad64b0e42f4a9792db1f2bbacd8-lvmlock:70254592:1 p 60836
            self.line = line

        def get_lockspace(self):
            return self.line.split()[1].split(":")[0]

        def get_uuid(self):
            return self.line.split()[1].split(":")[1]

        def get_path(self):
            return self.line.split()[1].split(":")[2]

        def get_offset(self):
            return self.line.split()[1].split(":")[3]

        def get_mode(self):
            return self.line.split()[1].split(":")[4]


    def _build_lvmlockd_adopt_file(all_locks):
        content = ""
        for lockspace in all_locks:
            VG_NAME = lockspace.replace("lvm_", "")
            VG_UUID = get_vg_lvm_uuid(VG_NAME)
            vg = "VG: %s %s sanlock 1.0.0:lvmlock\n" % (VG_UUID, VG_NAME)
            content += vg
            for resource in all_locks.get(lockspace):
                lv = "LV: %s %s 1.0.0:%s %s 0\n" % (VG_UUID, resource.get_uuid(), resource.get_offset(), "sh "if resource.get_mode() == "SH" else "ex")
                content += lv

        if len(content) != 0:
            logger.debug("write sanlock records to %s, content : \n%s" % (LVMLOCKD_ADOPT_FILE, content))
            linux.write_file(LVMLOCKD_ADOPT_FILE, content, create_if_not_exist=True)

    lines = bash.bash_o("sanlock client status").splitlines()
    all_locks = {}
    for line in lines:
        if line.startswith("s "):
            all_locks.update({_get_lockspace_name(line) : []})
        elif line.startswith("r "):
            all_locks.get(_get_lockspace_name(line)).append(Lock(line))

    _build_lvmlockd_adopt_file(all_locks)


@bash.in_bash
def stop_lvmlockd():
    pid = get_lvmlockd_pid()
    if pid:
        linux.kill_process(pid)

@bash.in_bash
def start_vg_lock(vgUuid, retry_times_for_checking_vg_lockspace):
    @linux.retry(times=60, sleep_time=random.uniform(1, 10))
    def vg_lock_is_adding(vgUuid):
        # NOTE(weiw): this means vg locking is adding rather than complete
        return_code = bash.bash_r("sanlock client status | grep -E 's lvm_%s.*\\:0 ADD'" % vgUuid)
        if return_code == 0:
            raise RetryException("vg %s lock space is starting" % vgUuid)
        return False

    @linux.retry(times=retry_times_for_checking_vg_lockspace, sleep_time=random.uniform(0.1, 2))
    def vg_lock_exists(vgUuid):
        return_code = bash.bash_r("lvmlockctl -i | grep %s" % vgUuid)
        if return_code != 0:
            raise RetryException("can not find lock space for vg %s via lvmlockctl" % vgUuid)
        elif vg_lock_is_adding(vgUuid) is True:
            raise RetryException("lock space for vg %s is adding" % vgUuid)
        else:
            return True

    @linux.retry(times=5, sleep_time=random.uniform(0.1, 10))
    def start_lock(vgUuid):
        modify_sanlock_config("use_zstack_vglock_timeout", 1)
        modify_sanlock_config("use_zstack_vglock_large_delay", 1)
        r, o, e = bash.bash_roe("vgchange --lock-start %s" % vgUuid)
        modify_sanlock_config("use_zstack_vglock_timeout", 0)
        modify_sanlock_config("use_zstack_vglock_large_delay", 0)

        if r != 0:
            if ("Device or resource busy" in o+e) :
                bash.bash_roe("dmsetup remove %s-lvmlock" % vgUuid)
            raise Exception("vgchange --lock-start failed: return code: %s, stdout: %s, stderr: %s" %
                            (r, o, e))

        vg_lock_exists(vgUuid)

    try:
        vg_lock_exists(vgUuid)
    except RetryException:
        start_lock(vgUuid)
    except Exception as e:
        raise e

@bash.in_bash
def check_missing_pv(vgUuid):
    pvs_outs = bash.bash_o(
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -t -Svg_name=%s -ouuid,name,missing" % vgUuid).strip().splitlines()
    if len(pvs_outs) == 0:
        return

    @linux.retry(times=3, sleep_time=random.uniform(0.1, 1))
    def restore_missing_pv(pv_name):
        r, o, e = bash.bash_roe("vgextend --restoremissing %s %s" % (vgUuid, pv_name))
        if r != 0:
            raise Exception("unable to restore missing pv %s for vg %s, stdout:%s, stderr:%s" % (pv_name, vgUuid, str(o), str(e)))
        logger.debug("restore missing pv[name:%s, uuid:%s] for vg %s successfully" % (pv_name, pv_uuid, vgUuid))

    check_gl_lock()
    for pvs_out in pvs_outs:
        pv_uuid = pvs_out.strip().split(" ")[0]
        pv_name = pvs_out.strip().split(" ")[1]
        if "missing" in pvs_out:
            if "unknown" in pv_name:
                raise Exception("vg %s was missing pv[name:%s, uuid:%s] , unable to restore" % (vgUuid, pv_name, pv_uuid))
            restore_missing_pv(pv_name)

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
def clean_lvm_archive_files(vgUuid):
    if not os.path.exists(LVM_CONFIG_ARCHIVE_PATH):
        logger.warn("can not find lvm archive path %s" % LVM_CONFIG_ARCHIVE_PATH)
        return
    archive_files = bash.bash_o("ls -rt %s | grep %s | wc -l" % (LVM_CONFIG_ARCHIVE_PATH, vgUuid))
    if int(archive_files) > 10:
        bash.bash_r("ls -rt %s | grep %s | head -n %s | xargs -i rm -rf %s/{}" % (LVM_CONFIG_ARCHIVE_PATH, vgUuid, (int(archive_files)-10), LVM_CONFIG_ARCHIVE_PATH))

@bash.in_bash
def quitLockServices():
    bash.bash_roe("sanlock client shutdown")
    bash.bash_roe("lvmlockctl -q")


@bash.in_bash
def drop_vg_lock(vgUuid):
    bash.bash_roe("lvmlockctl --gl-disable %s" % vgUuid)
    bash.bash_roe("lvmlockctl --drop %s" % vgUuid)


@bash.in_bash
def get_vg_lvm_uuid(vgUuid):
    return bash.bash_o("vgs --nolocking -t --noheading -ouuid %s" % vgUuid).strip()


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
def wipe_fs(disks, expected_vg=None, with_lock=True):
    @bash.in_bash
    def clear_lvmlock(vg_name):
        bash.bash_r("lvmlockctl -D %s; lvmlockctl -k %s; lvmlockctl -r %s" % (vg_name, vg_name, vg_name))

    for disk in disks:
        exists_vg = None

        r, o = bash.bash_ro("pvs --nolocking -t --noheading -o vg_name %s" % disk)
        if r == 0 and o.strip() != "":
            exists_vg = o.strip()

        if expected_vg in o.strip():
            continue

        backup = backup_super_block(disk)
        if bash.bash_r("grep %s %s" % (expected_vg, backup)) == 0:
            raise Exception("found vg uuid in superblock backup while not found in lvm command!")
        need_flush_mpath = False

        bash.bash_roe("partprobe -s %s" % disk)

        cmd_type = bash.bash_o("lsblk %s -oTYPE | grep mpath" % disk)
        if cmd_type.strip() != "":
            need_flush_mpath = True

        if exists_vg is not None:
            thread.ThreadFacade.run_in_thread(clear_lvmlock, [exists_vg])
            time.sleep(1)

        bash.bash_roe("wipefs -af %s" % disk)

        for holder in get_disk_holders([disk.split("/")[-1]]):
            if not holder.startswith("dm-"):
                continue
            bash.bash_roe("dmsetup remove /dev/%s" % holder)

        if need_flush_mpath:
            bash.bash_roe("multipath -f %s && systemctl reload multipathd.service && sleep 1" % disk)

        if exists_vg is not None:
            bash.bash_r("grep %s /etc/drbd.d/* | awk '{print $1}' | sort | uniq | tr -d ':' | xargs rm" % exists_vg)
            logger.debug("found vg %s exists on this pv %s, start wipe" %
                         (exists_vg, disk))
            try:
                if with_lock:
                    drop_vg_lock(exists_vg)
                remove_device_map_for_vg(exists_vg)
            finally:
                pass


def get_disk_holders(disk_names):
    holders = []
    for disk_name in disk_names:
        h = bash.bash_o("ls /sys/class/block/%s/holders/" % disk_name).strip().splitlines()
        if len(h) == 0:
            continue
        holders.extend(h)
        holders.extend(get_disk_holders(h))
    holders.reverse()
    return holders


@bash.in_bash
@linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
def add_pv(vg_uuid, disk_path, metadata_size):
    bash.bash_errorout("vgextend --metadatasize %s %s %s" % (metadata_size, vg_uuid, disk_path))
    if bash.bash_r("pvs --nolocking -t --readonly %s | grep %s" % (disk_path, vg_uuid)):
        raise Exception("disk %s not added to vg %s after vgextend" % (disk_path, vg_uuid))


def get_vg_size(vgUuid, raise_exception=True):
    r, o, _ = bash.bash_roe("vgs --nolocking -t %s --noheadings --separator : --units b -o vg_size,vg_free,vg_lock_type" % vgUuid, errorout=raise_exception)
    if r != 0:
        return None, None
    vg_size, vg_free = o.strip().split(':')[0].strip("B"), o.strip().split(':')[1].strip("B")
    if "sanlock" in o:
        return vg_size, vg_free

    pools = get_thin_pools_from_vg(vgUuid)
    if len(pools) == 0:
        return vg_size, vg_free
    vg_free = float(vg_free)
    for pool in pools:
        vg_free += pool.free
    return vg_size, str(int(vg_free))


def add_vg_tag(vgUuid, tag):
    cmd = shell.ShellCmd("vgchange --addtag %s %s" % (tag, vgUuid))
    cmd(is_exception=True)


def has_lv_tag(path, tag):
    # type: (str, str) -> bool
    if tag == "":
        logger.debug("check tag is empty, return false")
        return False
    o = shell.call("lvs -Stags={%s} %s --nolocking -t --noheadings 2>/dev/null | wc -l" % (tag, path))
    return o.strip() == '1'


def has_one_lv_tag_sub_string(path, tags):
    # type: (str, list) -> bool
    if not tags or len(tags) == 0:
        logger.debug("check tag is empty, return false")
        return False
    exists_tags = set(shell.call("lvs %s -otags --nolocking -t --noheadings" % path).strip().split(","))
    for tag in tags:
        for exists_tag in exists_tags:
            if tag in exists_tag:
                return True
    return False


def clean_lv_tag(path, tag):
    if has_lv_tag(path, tag):
        shell.run('lvchange --deltag %s %s' % (tag, path))


def add_lv_tag(path, tag):
    if not has_lv_tag(path, tag):
        shell.run('lvchange --addtag %s %s' % (tag, path))


def get_meta_lv_path(path):
    return path+"_meta"


def delete_image(path, tag, deactive=True):
    def activate_and_remove(f, deactive):
        if deactive:
            active_lv(f, shared=False)
        backing = linux.qcow2_get_backing_file(f)
        shell.check_run("lvremove -y -Stags={%s} %s" % (tag, f))
        return backing

    fpath = path
    backing = activate_and_remove(fpath, deactive)
    activate_and_remove(get_meta_lv_path(fpath), deactive)


def clean_vg_exists_host_tags(vgUuid, hostUuid, tag):
    cmd = shell.ShellCmd("vgs %s -otags --nolocking -t --noheading | tr ',' '\n' | grep %s | grep %s" % (vgUuid, tag, hostUuid))
    cmd(is_exception=False)
    exists_tags = [x.strip() for x in cmd.stdout.splitlines()]
    if len(exists_tags) == 0:
        return
    t = " --deltag " + " --deltag ".join(exists_tags)
    cmd = shell.ShellCmd("vgchange %s %s" % (t, vgUuid))
    cmd(is_exception=False)

def round_to(n, r):
    return (n + r - 1) / r * r

@bash.in_bash
@linux.retry(times=15, sleep_time=random.uniform(0.1, 3))
def create_lv_from_absolute_path(path, size, tag="zs::sharedblock::volume", lock=True, exact_size=False):
    if lv_exists(path):
        return

    vgName = path.split("/")[2]
    lvName = path.split("/")[3]

    if not exact_size:
        size = round_to(calcLvReservedSize(size), 512)
    r, o, e = bash.bash_roe("lvcreate -ay --addtag %s --size %sb --name %s %s" %
                         (tag, size, lvName, vgName))

    if not lv_exists(path):
        raise Exception("can not find lv %s after create, lvcreate return: %s, %s, %s" % (path, r, o, e))

    if lock:
        dd_zero(path)
        deactive_lv(path)
    else:
        dd_zero(path)


def create_lv_from_cmd(path, size, cmd, tag="zs::sharedblock::volume", lvmlock=True):
    # TODO(weiw): fix it
    if "ministorage" in tag and cmd.provisioning == VolumeProvisioningStrategy.ThinProvisioning:
        create_thin_lv_from_absolute_path(path, size, tag, lvmlock)
    elif cmd.provisioning == VolumeProvisioningStrategy.ThinProvisioning and size > cmd.addons[thinProvisioningInitializeSize]:
        create_lv_from_absolute_path(path, cmd.addons[thinProvisioningInitializeSize], tag, lvmlock)
    else:
        create_lv_from_absolute_path(path, size, tag, lvmlock)


@bash.in_bash
@linux.retry(times=15, sleep_time=random.uniform(0.1, 3))
def create_thin_lv_from_absolute_path(path, size, tag, lock=False):
    if lv_exists(path):
        return

    vgName = path.split("/")[2]
    lvName = path.split("/")[3]

    thin_pool = get_thin_pool_from_vg(vgName)
    assert thin_pool != ""

    r, o, e = bash.bash_roe("lvcreate --addtag %s -n %s -V %sb --thinpool %s %s" %
                  (tag, lvName, round_to(calcLvReservedSize(size), 512), thin_pool, vgName))
    if not lv_exists(path):
        raise Exception("can not find lv %s after create, lvcreate return : %s, %s, %s" %
                        (path, r, o, e))

    if lock:
        with OperateLv(path, shared=False):
            dd_zero(path)
    else:
        active_lv(path)
        dd_zero(path)


def get_thin_pool_from_vg(vgName):
    thin_pools = get_thin_pools_from_vg(vgName)
    most_free = [""]
    for pool in thin_pools:
        if len(most_free) < 2 or most_free[1] < pool.free:
            most_free = [pool.name, pool.free]

    return most_free[0]


class ThinPool(object):
    def __init__(self, path):
        o = bash.bash_o("lvs --nolocking -t %s --separator ' ' -oname,data_percent,lv_size,pool_lv --noheading --unit B" % path).strip()
        self.name = o.split(" ")[0].strip()
        self.total = float(o.split(" ")[2].strip("B"))
        self.thin_lvs = [l.strip() for l in bash.bash_o("lvs -Spool_lv=%s --noheadings --nolocking -t -oname" % self.name).strip().splitlines()]
        if len(self.thin_lvs) == 0 and not is_thin_lv(path):
            self.free = self.total
        else:
            try:
                self.free = self.total * (100 - float(o.split(" ")[1].strip("B")))/100
            except Exception as e:
                self.free = self.total


def get_thin_pools_from_vg(vgName):
    names = bash.bash_o("lvs --nolocking -t %s -Slayout=pool -oname --noheading" % vgName).strip().splitlines()
    if len(names) == 0:
        return []
    return [ThinPool("/dev/%s/%s" % (vgName, n)) for n in names]


def dd_zero(path):
    # we add at least additional 4M space for every lv, so it is safe to write 4M
    cmd = shell.ShellCmd("dd if=/dev/zero of=%s bs=1M count=4 oflag=direct" % path)
    cmd(is_exception=False)


def get_lv_size(path):
    if is_thin_lv(path):
        return get_thin_lv_size(path)
    cmd = shell.ShellCmd("lvs --nolocking -t --noheading -osize --units b %s" % path)
    cmd(is_exception=True, logcmd=False)
    return cmd.stdout.strip().strip("B")


def get_thin_lv_size(path):
    l = ThinPool(path)
    return str(int(l.total - l.free))


def is_thin_lv(path):
    return bash.bash_r("lvs --nolocking -t --noheadings  -olayout %s | grep 'thin,sparse'" % path) == 0


@bash.in_bash
def resize_lv(path, size, force=False):
    _force = "" if force is False else " --force "
    r, o, e = bash.bash_roe("lvresize %s --size %sb %s" % (_force, calcLvReservedSize(size), path))
    if r == 0:
        logger.debug("successfully resize lv %s size to %s" % (path, size))
        return
    elif "matches existing size" in e or "matches existing size" in o:
        logger.debug("lv %s size already matches existing size: %s, return as successful" % (path, size))
        return
    else:
        raise Exception("resize lv %s to size %s failed, return code: %s, stdout: %s, stderr: %s" %
                        (path, size, r, o, e))


@bash.in_bash
def resize_lv_from_cmd(path, size, cmd, extend_thin_by_specified_size=False):
    # type: (str, long, object, bool) -> None
    if cmd.provisioning is None or \
            cmd.addons is None or \
            cmd.provisioning != VolumeProvisioningStrategy.ThinProvisioning:
        resize_lv(path, size)
        return

    current_size = int(get_lv_size(path))

    if extend_thin_by_specified_size:
        v_size = linux.qcow2_virtualsize(path)
        if size + cmd.addons[thinProvisioningInitializeSize] > v_size:
            size = v_size
        else:
            size = size + cmd.addons[thinProvisioningInitializeSize]
        resize_lv(path, size)
        return

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
    r = 0
    e = None
    if raise_exception:
        o = bash.bash_errorout("lvchange -an %s" % path)
    else:
        r, o, e = bash.bash_roe("lvchange -an %s" % path)
    if lv_is_active(path):
        raise RetryException("lv %s is still active after lvchange -an, returns code: %s, stdout: %s, stderr: %s"
                             % (path, r, o, e))


@bash.in_bash
def delete_lv(path, raise_exception=True, deactive=True, zeroed=False):
    logger.debug("deleting lv %s" % path)
    if zeroed:
        if not lv_is_active(path):
            active_lv(path, shared=False)
        linux.zeroed_file_dev(path)
        deactive_lv(path, False)

    if deactive:
        deactive_lv(path, False)
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
def delete_lv_meta(path, raise_exception=True):
    logger.debug("deleting lv meta %s" % path)
    meta_path = get_meta_lv_path(path)
    if not lv_exists(meta_path):
        return
    if raise_exception:
        o = bash.bash_errorout("lvremove -y %s" % meta_path)
    else:
        o = bash.bash_o("lvremove -y %s" % meta_path)
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
    r = bash.bash_r("lvs --nolocking -t %s" % path)
    return r == 0


@bash.in_bash
def vg_exists(vgUuid):
    cmd = shell.ShellCmd("vgs --nolocking -t %s" % (vgUuid))
    cmd(is_exception=False)
    return cmd.return_code == 0


def lv_uuid(path):
    cmd = shell.ShellCmd("lvs --nolocking -t --noheadings %s -ouuid" % path)
    cmd(is_exception=False)
    return cmd.stdout.strip()


def lv_is_active(lv_path):
    # NOTE(weiw): use readonly to get active may return 'unknown'
    r = bash.bash_r("lvs --nolocking -t --noheadings %s -oactive | grep -w active" % lv_path)
    if r == 0:
        return True
    return os.path.exists(lv_path)


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
    cmd = shell.ShellCmd("lvs --nolocking -t %s --noheadings -opath -Slv_active=active" % vgUuid)
    cmd(is_exception=False)
    result = []
    for i in cmd.stdout.strip().split("\n"):
        if i.strip() != "":
            result.append(i.strip())
    return result


@bash.in_bash
def check_gl_lock():
    r, o = bash.bash_ro("lvmlockctl -i | grep 'LK GL' -B 5")
    if r == 0:
        return

    # NOTE(weiw): if lockspace exists, choose one as gl lock
    r, o = bash.bash_ro("lvmlockctl -i | grep 'lock_type=sanlock' | awk '{print $2}'")
    if r == 0:
        o = o.strip()
        if len(o.splitlines()) != 0:
            for i in o.splitlines():
                i = i.strip()
                if i == "":
                    continue
                bash.bash_roe("lvmlockctl --gl-enable %s" % i)
                return


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


# FIXME(weiw): drbd_path is a hack
@bash.in_bash
def create_lvm_snapshot(absolutePath, remove_oldest=True, snapName=None, size_percent=0.1, drbd_path=None):
    # type: (str, bool, str, float) -> str
    if snapName is None:
        snapName = get_new_snapshot_name(absolutePath, remove_oldest)
    if is_thin_lv(absolutePath):
        size_command = ""
    else:
        virtual_size = linux.qcow2_virtualsize(absolutePath) if drbd_path is None else linux.qcow2_virtualsize(drbd_path)
        if virtual_size <= 2147483648:  # 2GB
            snap_size = calcLvReservedSize(virtual_size)
            snap_size = int(snap_size / 512 + 1) * 512
        elif int((virtual_size / 512) * size_percent * 512) <= 2147483648:
            snap_size = 2147483648
        else:
            snap_size = int((virtual_size / 512) * size_percent + 1) * 512
        size_command = " -L %sB " % snap_size
    bash.bash_errorout("sync; lvcreate --snapshot -n %s %s %s" % (snapName, absolutePath, size_command))
    path = "/".join(absolutePath.split("/")[:-1]) + "/" + snapName
    if size_command == "":
        bash.bash_r("lvchange -ay -K %s" % path)
    return path


def delete_snapshots(lv_path):
    all_snaps = bash.bash_o("lvs -oname -Sorigin=%s --nolocking -t --noheadings | grep _snap_" % lv_path.split("/")[-1]).strip().splitlines()
    if len(all_snaps) == 0:
        return
    for snap in all_snaps:
        delete_lv(snap)


def get_new_snapshot_name(absolutePath, remove_oldest=True):
    @bash.in_bash
    @lock.file_lock(absolutePath)
    def do_get_new_snapshot_name(name):
        all_snaps = bash.bash_o("lvs -oname -Sorigin=%s --nolocking -t --noheadings | grep _snap_" % name).strip().splitlines()
        if len(all_snaps) == 0:
            return name + "_snap_1"
        numbers = map(lambda x: int(x.strip().split("_")[-1]), all_snaps)
        if len(all_snaps) >= 3 and remove_oldest:
            oldest = name + "_snap_" + str(min(numbers))
            delete_lv("/".join(absolutePath.split("/")[:-1]) + "/" + oldest)
        elif len(all_snaps) >= 3:
            raise Exception("there are %s snapshots for lv %s exits" % (len(all_snaps), absolutePath))
        return name + "_snap_" + str(max(numbers) + 1)
    return do_get_new_snapshot_name(absolutePath.split("/")[-1])


@bash.in_bash
def get_lv_locking_type(path):
    @linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
    def _get_lv_locking_type(path):
        output = bash.bash_o("lvmlockctl -i | grep %s | head -n1 | awk '{print $3}'" % lv_uuid(path))
        return LvmlockdLockType.from_abbr(output.strip(), raise_exception=True)

    locking_type = LvmlockdLockType.NULL
    active = None
    with lock.NamedLock(path.split("/")[-1]):
        try:
            active = lv_is_active(path)
            if not active:
                return locking_type
            locking_type = _get_lv_locking_type(path)
        except Exception as e:
            output = bash.bash_o("lvmlockctl -i | grep %s | head -n1 | awk '{print $3}'" % lv_uuid(path))
            locking_type = LvmlockdLockType.from_abbr(output.strip(), raise_exception=False)
            if active is True and locking_type == LvmlockdLockType.NULL:
                # NOTE(weiw): this usually because of manipulation of locking by hand
                locking_type = LvmlockdLockType.SHARE

    return locking_type


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


#TODO(weiw): This is typically mini usage
def qcow2_lv_recursive_active(abs_path, lock_type):
    # type: (str, int) -> object
    backing = linux.qcow2_get_backing_file(abs_path)
    active_lv(abs_path, lock_type == LvmlockdLockType.SHARE)

    if backing != "":
        qcow2_lv_recursive_active(backing, LvmlockdLockType.SHARE)


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
    def __init__(self, abs_path, shared=False, skip_deactivate_tags=None, delete_when_exception=False):
        # type: (str, bool, list[str], bool) -> object
        self.abs_path = abs_path
        self.shared = shared
        self.exists_lock = get_lv_locking_type(abs_path)
        self.target_lock = LvmlockdLockType.EXCLUSIVE if shared is False else LvmlockdLockType.SHARE
        self.backing = None
        self.delete_when_exception = delete_when_exception
        self.skip_deactivate_tags = skip_deactivate_tags

    def __enter__(self):
        if self.exists_lock < self.target_lock:
            active_lv(self.abs_path, self.shared)
        if linux.qcow2_get_backing_file(self.abs_path) != "":
            self.backing = RecursiveOperateLv(
                linux.qcow2_get_backing_file(self.abs_path), True, self.skip_deactivate_tags, False)

        if self.backing is not None:
            self.backing.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.backing is not None:
            self.backing.__exit__(exc_type, exc_val, exc_tb)

        if exc_val is not None \
                and self.delete_when_exception is True\
                and not has_one_lv_tag_sub_string(self.abs_path, self.skip_deactivate_tags):
            delete_lv(self.abs_path, False)
            return

        if has_one_lv_tag_sub_string(self.abs_path, self.skip_deactivate_tags):
            logger.debug("the volume %s has skip tag: %s" %
                         (self.abs_path, has_one_lv_tag_sub_string(self.abs_path, self.skip_deactivate_tags)))
            return

        if self.exists_lock > self.target_lock:
            return

        if self.exists_lock == LvmlockdLockType.NULL:
            deactive_lv(self.abs_path, raise_exception=False)
        else:
            active_lv(self.abs_path, self.exists_lock == LvmlockdLockType.SHARE)


def get_lockspace(vgUuid):
    @linux.retry(times=3, sleep_time=0.5)
    def _do_get_lockspace(vgUuid):
        o = bash.bash_o("sanlock client gets | awk '{print $2}' | grep %s" % vgUuid).strip()
        if o == "":
            raise RetryException
        return o

    out = bash.bash_o("sanlock client gets | awk '{print $2}' | grep %s" % vgUuid).strip()
    if out != "":
        return out
    try:
        logger.debug("retrying get lockspace for vg %s" % vgUuid)
        out = _do_get_lockspace(vgUuid)
    except Exception as e:
        out = bash.bash_o("sanlock client gets | awk '{print $2}' | grep %s" % vgUuid).strip()

    return out


def examine_lockspace(lockspace):
    @linux.retry(times=3, sleep_time=0.5)
    def _do_examine_lockspace(lockspace):
        r, _, _ = bash.bash_roe("sanlock client examine -s %s" % lockspace, errorout=False)
        if r != 0:
            raise RetryException("can not examine lockspace")
        return r

    r, _, _ = bash.bash_roe("sanlock client examine -s %s" % lockspace, errorout=False)
    if r == 0:
        return r
    try:
        logger.debug("retrying examine lockspace for %s" % lockspace)
        r = _do_examine_lockspace(lockspace)
    except Exception as e:
        r, _, _ = bash.bash_roe("sanlock client examine -s %s" % lockspace, errorout=False)

    return r


def check_stuck_vglk():
    @linux.retry(3, 1)
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
    r, o , e = bash.bash_roe("timeout -s SIGKILL %s pvs --noheading --nolocking -t -Svg_name=%s -oname,missing" % (timeout, vgUuid))
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

    # r, s = lvm_vgck(vgUuid, timeout)
    # if r is False:
    #     return r, s

    health = bash.bash_o('timeout -s SIGKILL %s vgs -oattr --nolocking -t --noheadings --shared %s ' % (10 if timeout < 10 else timeout, vgUuid)).strip()
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

@bash.in_bash
def vgck(vgUuid, timeout):
    return bash.bash_roe('timeout -s SIGKILL %s vgck %s 2>&1' % (timeout, vgUuid))

def lvm_vgck(vgUuid, timeout):
    health, o, e = vgck(vgUuid, 360 if timeout < 360 else timeout)
    check_stuck_vglk()

    if health != 0:
        s = "vgck %s failed, detail: [return_code: %s, stdout: %s, stderr: %s]" % (vgUuid, health, o, e)
        logger.warn(s)
        return False, s

    if o is not None and o != "":
        for es in o.strip().splitlines():
            if "WARNING" in es:
                continue
            if "Retrying" in es:
                continue
            if "Duplicate sanlock global lock" in es:
                fix_global_lock()
                continue
            if "have changed sizes" in es:
                logger.debug("found pv of vg %s size may changed, details: %s" % (vgUuid, es))
                continue
            if "held by other host" in es:
                continue
            if "without a lock" in es:
                continue
            if es.strip() == "":
                continue
            s = "vgck %s failed, details: [return_code: %s, stdout: %s, stderr: %s]" % (vgUuid, health, o, e)
            logger.warn(s)
            return False, s
    return True, ""


def lvm_check_operation(vgUuid):
    test_lv = "/dev/%s/zscheckvolume%s" % (vgUuid, random.randint(100000, 999999))
    try:
        create_lv_from_absolute_path(test_lv, 1024*1024*4)
        delete_lv(test_lv, True)
    except Exception as e:
        if "already exists" in e.message:
            return True
        return False
    finally:
        delete_lv(test_lv, False)
    return True


def check_vg_status(vgUuid, check_timeout, check_pv=True):
    # type: (str) -> tuple[bool, str]
    # 1. examine sanlock lock
    # 2. check the consistency of volume group
    # 3. check ps missing
    # 4. check vg attr
    return_code = bash.bash_r("sanlock client status | grep -E 's lvm_%s.*\\:0 ADD'" % vgUuid)
    if return_code == 0:
        logger.debug("lockspace for vg %s is adding, skip run fencer" % vgUuid)
        return True, ""

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

    # if examine_lockspace(lock_space) != 0:
    #     return False, "examine lockspace %s failed" % lock_space
    #
    # if set_sanlock_event(lock_space) != 0:
    #     return False, "sanlock set event on lock space %s failed" % lock_space

    if not check_pv:
        return True, ""

    return check_pv_status(vgUuid, check_timeout)


def set_sanlock_event(lockspace):
    @linux.retry(times=3, sleep_time=0.5)
    def _set_sanlock_event(lockspace):
        host_id = lockspace.split(":")[1]
        r, _, _ = bash.bash_roe("sanlock client set_event -s %s -i %s -e 1 -d 1" % (lockspace, host_id), errorout=False)
        if r != 0:
            raise RetryException("set sanlock event failed")
        return r

    host_id = lockspace.split(":")[1]
    r, _, _ = bash.bash_roe("sanlock client set_event -s %s -i %s -e 1 -d 1" % (lockspace, host_id), errorout=False)
    if r == 0:
        return r
    try:
        logger.debug("retrying set sanlock event for %s" % lockspace)
        r = _set_sanlock_event(lockspace)
    except Exception as e:
        r, _, _ = bash.bash_roe("sanlock client set_event -s %s -i %s -e 1 -d 1" % (lockspace, host_id), errorout=False)
    finally:
        return r


def get_sanlock_renewal(lockspace):
    r, o, e = bash.bash_roe("sanlock client renewal -s %s" % lockspace)
    return o.strip().splitlines()[-1]


def check_sanlock_renewal_failure(lockspace):
    last_record = linux.wait_callback_success(get_sanlock_renewal, lockspace, 10, 1, True)
    if last_record is False:
        logger.warn("unable find correct sanlock renewal record, may be rotated")
        return True, ""
    if "next_errors=" not in last_record:
        return True, ""
    errors = int(last_record.split("next_errors=")[-1])
    if errors > 2:
        return False, "sanlock renew lease of lockspace %s failed for %s times, storage may failed" % (
        lockspace, errors)
    return True, ""


def check_sanlock_status(lockspace):
    @linux.retry(4, 0.5)
    def _check_sanlock_status(lockspace):
        r, o, e = bash.bash_roe("sanlock client status -D | grep %s -A 18" % lockspace)
        if r != 0:
             raise RetryException("sanlock can not get lockspace %s status" % lockspace)
        return r, o, e
    try:
        r, o, e = _check_sanlock_status(lockspace)
    except Exception:
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
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -t -oname -Spv_uuid=%s" % pvUuid).strip()


@bash.in_bash
def get_pv_uuid_by_path(pvPath):
    return bash.bash_o(
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -t -ouuid %s" % pvPath).strip()


@bash.in_bash
def check_lv_on_pv_valid(vgUuid, pvUuid, lv_path=None):
    pv_name = bash.bash_o(
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -t -oname -Spv_uuid=%s" % pvUuid).strip()
    one_active_lv = lv_path if lv_path is not None else bash.bash_o(
        "timeout -s SIGKILL 10 lvs --noheading --nolocking -t -opath,devices,tags " +
        "-Sactive=active %s | grep %s | grep %s | awk '{print $1}' | head -n1" % (vgUuid, pv_name, VOLUME_TAG)).strip()
    if one_active_lv == "":
        return True
    r = bash.bash_r("%s %s" % (qemu_img.subcmd('info'), one_active_lv))
    if r != 0:
        return False
    return True


@bash.in_bash
def get_invalid_pv_uuids(vgUuid, checkIo = False):
    invalid_pv_uuids = []
    pvs_outs = bash.bash_o(
        "timeout -s SIGKILL 10 pvs --noheading --nolocking -t -Svg_name=%s -ouuid,name,missing" % vgUuid).strip().split("\n")
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
            "timeout -s SIGKILL 10 lvs --noheading --nolocking -t %s -odevices" % f).strip().lower()  # type: str
        logger.debug("volume %s is on pv %s" % (volume_path, o))
        if len(filter(lambda n: o.find(n.lower()) > 0, pv_names)) > 0:
            logger.debug("lv %s on pv %s(%s), return true" % (volume_path, pvUuids, pv_names))
            return True
        if o == "" and includingMissing:
            logger.debug("pv of lv %s is missing, return true")
            return True
    return False

'''
e.g. lsblk command output when iscsi disconnected:

    [root@10-0-0-0 linus]# lsblk -P /dev/$VG/$LV -s -o NAME,TYPE,STATE
    NAME="$VG-$LV" TYPE="lvm" STATE="transport-offline"
    NAME="sda" TYPE="disk" STATE="running"

explain:

    If you switch off the network/machine for a iscsi based storage,
    "qemu-img --backing-chain $vm_root_volume" may not be able to determine
    the running vm I/O on that storage works or not. One solution is check
    if the state of the disk of lv is "transport-offline".
'''

@bash.in_bash
def is_bad_vm_root_volume(vm_root_volume):
    cmd = "lsblk -sr " + vm_root_volume + "-o NAME,TYPE,STATE"
    r, o = bash.bash_ro(cmd)
    if r != 0:
        return True

    dep_devices = form.load(o)
    has_running_disk = any(dep_dev["TYPE"] == "disk" and dep_dev["STATE"] == "running" for dep_dev in dep_devices)
    has_not_running_disk = any(dep_dev["TYPE"] == "disk" and dep_dev["STATE"] != "running" for dep_dev in dep_devices)
    return has_not_running_disk or not has_running_disk

def get_vm_pid(uuid):
    pid = linux.read_file(os.path.join(LIVE_LIBVIRT_XML_DIR, uuid + ".pid"))
    if pid:
        return pid.strip()

    return linux.find_vm_pid_by_uuid(uuid)

@bash.in_bash
def get_running_vm_root_volume_on_pv(vgUuid, pvUuids, checkIo=True):
    # type: (str, list[str], bool) -> list[VmStruct]
    # 1. get root volume from live vm xml
    # 2. make sure io has error
    # 3. filter for pv

    vms = []
    for file_name in linux.listdir(LIVE_LIBVIRT_XML_DIR):
        xs = file_name.split(".")
        if len(xs) != 2 or xs[1] != "xml":
            continue

        xml = linux.read_file(os.path.join(LIVE_LIBVIRT_XML_DIR, file_name))
        if not '/dev/' + vgUuid in xml:
            continue

        vm = VmStruct()
        vm.uuid = xs[0]
        vm.pid = get_vm_pid(vm.uuid)
        vm.load_from_xml(xml)
        if not vm.root_volume:
            logger.warn("found strange vm[pid: %s, uuid: %s], can not find boot volume" % (vm.pid, vm.uuid))
            continue

        if not vm.root_volume.startswith("/dev/" + vgUuid):
            continue

        bad_vm_root_volume_condition = False
        r = bash.bash_r("blockdev --flushbufs %s" % vm.root_volume)
        if is_bad_vm_root_volume(vm.root_volume) is True:
            bad_vm_root_volume_condition = True
        elif checkIo is True and r == 0:
            logger.debug("volume %s for vm %s io success, skiped" % (vm.root_volume, vm.uuid))
            continue

        if bad_vm_root_volume_condition is True or is_volume_on_pvs(vm.root_volume, pvUuids, True):
            vms.append(vm)

    return vms


@bash.in_bash
def remove_partial_lv_dm(vgUuid):
    o = bash.bash_o("lvs --noheading --nolocking -t %s -opath,tags -Slv_health_status=partial | grep %s" % (vgUuid, COMMON_TAG)).strip().splitlines()
    if len(o) == 0:
        return

    for volume in o:
        bash.bash_roe("dmsetup remove %s" % volume.strip().split(" ")[0])


@bash.in_bash
def unpriv_sgio():
    bash.bash_roe("for i in `ls /sys/block/ | grep -v loop`; do echo 1 > /sys/block/$i/queue/unpriv_sgio; done")


@bash.in_bash
@linux.retry(times=3, sleep_time=1)
def enable_multipath():
    bash.bash_roe("modprobe dm-multipath")
    bash.bash_roe("modprobe dm-round-robin")
    bash.bash_roe("mpathconf --enable --with_multipathd y")
    bash.bash_roe("systemctl enable multipathd")

    if not is_multipath_running():
        raise RetryException("multipath still not running")


class QemuStruct(object):
    def __init__(self, pid):
        self.pid = pid
        args = bash.bash_o("ps -o args --width 99999 --pid %s" % pid)
        self.name = args.split(' -uuid ')[-1].split(' ')[0].replace("-", "")
        self.state = bash.bash_o("virsh domstate %s" % self.name).strip()


@bash.in_bash
def find_qemu_for_lv_in_use(lv_path):
    # type: (str) -> list[QemuStruct]
    dm_path = bash.bash_o("readlink -e %s" % lv_path)
    pids = [x.strip() for x in bash.bash_o("lsof -b -c qemu-kvm -c qemu-system| grep -w %s | awk '{print $2}'" % dm_path).splitlines()]
    return [QemuStruct(pid) for pid in pids]

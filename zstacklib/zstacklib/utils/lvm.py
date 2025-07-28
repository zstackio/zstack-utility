import difflib
import functools
import random
import os
import os.path
import threading
import time
import traceback
import weakref
import re
import warnings
import datetime
import xml.etree.ElementTree as etree

import simplejson

from zstacklib.utils import form, report
from zstacklib.utils import shell
from zstacklib.utils import bash
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import linux
from zstacklib.utils import thread
from zstacklib.utils import sanlock
from zstacklib.utils import remoteStorage
from cachetools import TTLCache
from distutils.version import LooseVersion

from zstacklib.utils.linux import get_fs_type

logger = log.get_logger(__name__)
LV_RESERVED_SIZE = 1024*1024*4
LVM_CONFIG_PATH = "/etc/lvm"
LVM_CONFIG_FILE = '/etc/lvm/lvm.conf'
LVM_LOCAL_CONFIG_FILE = '/etc/lvm/lvmlocal.conf'
LVM_CONFIG_TMP_FILE = '/etc/lvm/lvm.conf.tmp'
SANLOCK_CONFIG_FILE_PATH = "/etc/sanlock/sanlock.conf"
DEB_SANLOCK_CONFIG_FILE_PATH = "/etc/default/sanlock"
LIVE_LIBVIRT_XML_DIR = "/var/run/libvirt/qemu"
SANLOCK_IO_TIMEOUT = 40
SANLOCK_CLIENT_SET_CONFIG_TIMEOUT = 10
LVMLOCKD_LOG_FILE_PATH = "/var/log/lvmlockd/lvmlockd.log"
LVMLOCKD_SOCKET = "/run/lvm/lvmlockd.socket"
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
LVMLOCKD_VERSION = None
thinProvisioningInitializeSize = "thinProvisioningInitializeSize"
PV_DISCARD_MIN_SIZE_IN_BYTES = 1*1024**3
PV_DISCARD_MAX_SIZE_IN_BYTES = 100*1024**3
ONE_HOUR_IN_SEC = 60 * 60
LV_UUID_REFRESH_INTERVAL_IN_SEC = 60 * 30
LVM_CONFIG_CHANGED_FILE = "/var/run/zstack/lvmConfigChanged"
'''
If the lvm command with locking is hung, it will always occupy the lock and cannot be released.
And in scenarios where storage IO is slow and lock contention occurs, it may take longer to execute, 
so we need to set a timeout that can tolerate this scenario.
'''
lvm_cmd_timeout_with_locking = 210

lv_offset = TTLCache(maxsize=100, ttl=ONE_HOUR_IN_SEC)
continue_lockspace_track = {}  # type: dict[str, bool]
lv_uuid_cache = {}  # type: dict[str, str]
lv_uuid_cache_last_refresh_time = 0

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

class LvDiscardStrategy(object):
    NEVER = "never"
    ALWAYS = "always"
    AUTO = "auto"

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
    def __init__(self):
        self.wwid = None  # type: str
        self.vendor = None  # type: str
        self.model = None  # type: str
        self.wwn = None  # type: str
        self.serial = None  # type: str
        self.hctl = None  # type: str
        self.type = None  # type: str
        self.size = None  # type: long
        self.path = None  # type: str
        self.source = None  # type: str
        self.transport = None  # type: str
        self.targetIdentifier = None  # type: str
        self.multipathPath = None  # type: str

def get_vg_uuid(path):
    # type: (str) -> str
    if not path or len(path.split("/")) != 4:
        raise Exception("invalid lv path[%s]" % path)

    return path.split("/")[2]

def get_block_devices():
    scsi_info = get_lsscsi_info()
    # 1. get multi path devices information
    block_devices, slave_devices = get_mpath_block_devices(scsi_info)
    # 2. get information of other devices
    block_devices.extend(get_disk_block_devices(slave_devices, scsi_info))
    # 3. get nvme block devices
    block_devices.extend(get_nvme_block_devices())

    device_iqn = get_dev_iqn()
    for d in block_devices:
        if d.source == 'fc':
            d.targetIdentifier = get_storage_wwnn(d.hctl)
        elif d.source == 'iscsi':
            d.targetIdentifier = device_iqn.get(d.dev_name)
        elif d.source == 'nvme':
            d.targetIdentifier = get_nqn(d.dev_name)

    return block_devices

def get_nvme_transport(dev_name):
    transport = linux.read_file("/sys/class/block/%s/device/transport" % dev_name)
    if transport:
        return transport.strip()

    nvme_subsystems = []
    if os.path.exists("/sys/class/nvme-subsystem/"):
        nvme_subsystems = os.listdir("/sys/class/nvme-subsystem/")

    for target in nvme_subsystems:
        for fpath in linux.walk("/sys/class/nvme-subsystem/%s" % target, depth=2):
            if os.path.basename(fpath) != dev_name:
                continue
            transport = linux.read_file(fpath + "/../transport")
            if transport:
                return transport.strip()

def get_storage_wwnn(hctl):
    o = shell.call(
        "systool -c fc_transport -A node_name | grep '\"target%s\"' -B2 | awk '/node_name/{print $NF}'" % ":".join(hctl.split(":")[0:3]))
    return o.strip().strip('"')

def get_dev_iqn():
    device_iqn = {}
    r, o, e = bash.bash_roe("iscsiadm -m session -P 3 | grep -E 'Target: iqn|Attached scsi disk'")
    if r != 0 or o is None:
        return device_iqn

    iqn = None
    for line in o.splitlines():
        line = line.strip()
        if "Target: iqn" in line:
            iqn = line.split(' ')[1]
        elif "Attached scsi disk" in line:
            device_iqn.update({line.split('\t')[0].split(' ')[-1] : iqn})

    return device_iqn

def get_nqn(dev_name):
    nqn = linux.read_file("/sys/class/block/%s/device/subsysnqn" % dev_name)
    if nqn:
        return nqn.strip()

    nvme_subsystems = []
    if os.path.exists("/sys/class/nvme-subsystem/"):
        nvme_subsystems = os.listdir("/sys/class/nvme-subsystem/")

    for target in nvme_subsystems:
        nqn = linux.read_file("/sys/class/nvme-subsystem/%s/subsysnqn" % target)
        if nqn and any(os.path.basename(fpath) == dev_name for fpath in
                       linux.walk("/sys/class/nvme-subsystem/%s" % target, depth=2)):
            return nqn.strip()

def get_nvme_block_devices():
    if not os.path.exists('/usr/sbin/nvme') and not os.path.exists('/sbin/nvme'):
        return []

    s = shell.ShellCmd("nvme list -o json")
    s(False)
    if s.return_code != 0 or not s.stdout or not s.stdout.strip():
        return []

    try:
        devices = []
        ret = simplejson.loads(s.stdout)
        for d in ret.get("Devices", []):
            dev = os.path.basename(d.get("DevicePath", ""))
            if not dev or not os.path.exists("/sys/block/%s/wwid" % dev):
                continue

            wwid = linux.read_file("/sys/block/%s/wwid" % dev)
            if wwid:
                device_info = get_device_info(dev, {dev: wwid.strip()})
                device_info.transport = get_nvme_transport(dev)
                device_info.source = 'nvme'
                device_info.dev_name = dev
                devices.append(device_info)
        return devices
    except Exception as e:
        logger.error(traceback.format_exc())
        return []


@bash.in_bash
def get_mpath_block_devices(scsi_info):
    slave_devices = []
    mpath_devices = []

    cmd = shell.ShellCmd("multipath -l -v1")
    cmd(is_exception=False)
    if cmd.return_code == 0 and cmd.stdout.strip() != "":
        mpath_devices = cmd.stdout.strip().splitlines()

    block_devices_list = [None] * len(mpath_devices)

    def get_slave_block_devices(slave, dm, i, mpath_dev):
        try:
            struct = get_device_info(slave, scsi_info)
            if struct is None:
                return
            struct.type = "mpath"
            struct.dev_name = slave
            struct.multipathPath = mpath_dev
            block_devices_list[i] = struct
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            return

    threads = []
    for idx, mpath_device in enumerate(mpath_devices, start=0):
        try:
            dm = os.path.basename(os.path.realpath("/dev/mapper/%s" % mpath_device))
            if not dm.startswith("dm-"):
                continue

            slaves = os.listdir("/sys/class/block/%s/slaves/" % dm)
            if slaves is None or len(slaves) == 0:
                struct = SharedBlockCandidateStruct()
                struct.wwid = get_dm_wwid(dm)
                struct.type = "mpath"
                struct.multipathPath = mpath_device
                block_devices_list[idx] = struct
                continue

            slave_devices.extend(slaves)
            threads.append(thread.ThreadFacade.run_in_thread(get_slave_block_devices, [slaves[0], dm, idx, mpath_device]))
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            continue

    for t in threads:
        t.join()

    return filter(None, block_devices_list), slave_devices

def get_disk_block_devices(slave_devices, scsi_info):
    disks = shell.call("lsblk -e 43 -p -o NAME,TYPE | awk '/disk/{print $1}'").strip().split()
    block_devices_list = [None] * len(disks)

    slave_multipaths = shell.call("multipath -l | grep -A 1 policy | grep -v policy |awk -F - '{print $2}'| awk '{print $2}'").strip().splitlines()
    slave_multipaths = filter(None, slave_multipaths)
    is_multipath_running_sign = is_multipath_running()

    def get_block_device_info(disk, i):
        try:
            struct = get_device_info(disk.strip().split("/")[-1], scsi_info)
            if struct is None:
                return
            if bash.bash_r('wipefs -n %s | grep LVM2  > /dev/null' % disk.strip()) == 0:
                struct.type = "lvm-pv"
            struct.dev_name = os.path.basename(disk)
            block_devices_list[i] = struct
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            return

    threads = []
    for idx, disk in enumerate(disks, start=0):
        try:
            if disk.split("/")[-1] in slave_devices or is_slave_of_multipath_list(disk, slave_multipaths, is_multipath_running_sign):
                continue
            threads.append(thread.ThreadFacade.run_in_thread(get_block_device_info, [disk, idx]))
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            continue

    for t in threads:
        t.join()

    return filter(None, block_devices_list)

def get_lsscsi_info():
    scsi_info = {}
    o = filter(lambda s: "/dev/" in s, run_lsscsi_i())
    for info in o:
        dev_and_wwid = info.split("/dev/")[1].split(" ")
        dev_name = dev_and_wwid[0]
        wwid = dev_and_wwid[-1]
        if not wwid or wwid == "-":
            continue
        scsi_info[dev_name] = wwid
    return scsi_info


def run_lsscsi_i():
    if os.path.exists("/usr/lib/udev/scsi_id"):
        return bash.bash_o("""lsscsi | awk '{printf $0"  "; system("/usr/lib/udev/scsi_id -g -u -d "$NF" || echo '-'");}'""").strip().splitlines()
    else:
        return bash.bash_o("lsscsi -i").strip().splitlines()


def is_multipath_running():
    r = bash.bash_r("multipath -t > /dev/null")
    if r != 0:
        return False

    r = bash.bash_r("pgrep multipathd")
    if r != 0:
        return False
    return True


@bash.in_bash
def is_slave_of_multipath(dev_path):
    # type: (str) -> bool
    if is_multipath_running() is False:
        return False

    r = bash.bash_r("multipath -c %s" % dev_path)
    return r == 0


def is_slave_of_multipath_list(dev_path, slave_multipath, is_multipath_running_sign):
    if is_multipath_running_sign is False:
        return False

    if dev_path.split("/")[-1] in slave_multipath:
        return True
    else:
        return False


def is_multipath(dev_name):
    if not is_multipath_running():
        return False
    r = bash.bash_r("multipath /dev/%s -l | grep policy" % dev_name)
    if r == 0:
        return True

    slaves = linux.listdir("/sys/class/block/%s/slaves/" % dev_name)
    if slaves is not None and len(slaves) > 0:
        if len(slaves) == 1 and slaves[0] == "":
            return False
        return True
    return False


def get_multipath_dmname(dev_name):
    # if is multipath dev, return;
    # if is one of multipath paths, return multipath dev(dm-xxx);
    # else return None
    slaves = linux.listdir("/sys/class/block/%s/slaves/" % dev_name)
    if slaves is not None and len(slaves) > 0 and slaves[0].strip() != "":
        return dev_name

    r = bash.bash_r("multipath /dev/%s -l | grep policy" % dev_name)
    if r != 0:
        return None
    return bash.bash_o("multipath -l /dev/%s | head -n1 | grep -Eo 'dm-[[:digits:]]+'" % dev_name).strip()


def get_multipath_name(dev_name):
    return bash.bash_o("multipath /dev/%s -l -v1" % dev_name).strip()

def get_lvmlockd_service_name():
    service_name = 'lvm2-lvmlockd.service'
    if LooseVersion(get_lvmlockd_version()) > LooseVersion("2.02"):
        service_name = 'lvmlockd.service'
    return service_name

def get_lvmlockd_version():
    global LVMLOCKD_VERSION
    if LVMLOCKD_VERSION is None:
        LVMLOCKD_VERSION = shell.call("""lvmlockd --version | awk '{print $3}' | awk -F'.' '{print $1"."$2}'""").strip()
    return LVMLOCKD_VERSION

def get_sanlock_patch_version():
    return bash.bash_o("sanlock get_patch_version").strip()

def get_sanlock_pid():
    return linux.find_process_by_command('sanlock')

def get_running_sanlock_patch_version():
    pid = get_sanlock_pid()
    if pid:
        exe = "/proc/%s/exe" % pid
        return bash.bash_o("%s get_patch_version" % exe).strip()

def get_running_lvmlockd_version():
    pid = get_lvmlockd_pid()
    if pid:
        exe = "/proc/%s/exe" % pid
        return shell.call("""%s --version | awk '{print $3}' | awk -F'.' '{print $1"."$2}'""" % exe).strip()

def get_lvmlockd_pid():
    return linux.find_process_by_command('lvmlockd')

def get_dm_wwid(dm):
    try:
        stdout = shell.call("set -o pipefail; udevadm info -n %s | grep -o 'dm-uuid-mpath-\S*' | awk -F '-' '{print $NF; exit}'" % dm)
        return stdout.strip().strip("()")
    except Exception as e:
        logger.warn(linux.get_exception_stacktrace())
        return None

def get_device_info(dev_name, scsi_info):
    # type: (str, dict[str, str]) -> SharedBlockCandidateStruct
    s = SharedBlockCandidateStruct()
    dev_name = dev_name.strip()

    def get_wwid(dev):
        try:
            if dev in scsi_info.keys():
                return scsi_info[dev]
            elif dev.startswith("dm-"):
                return get_dm_wwid(dev)
            else:
                return None
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            return None

    s = lsblk_info(dev_name)
    if not s:
        return s

    wwid = get_wwid(dev_name)
    if not wwid or wwid == "-":
        return None

    s.wwid = wwid
    s.path = get_device_path(dev_name)
    return s

def lsblk_info(dev_name):
    # type: (str) -> SharedBlockCandidateStruct
    s = SharedBlockCandidateStruct()

    r, o, e = bash.bash_roe("lsblk --pair -b -p -o NAME,VENDOR,MODEL,WWN,SERIAL,HCTL,TYPE,SIZE,TRAN /dev/%s" % dev_name,
                            False)
    if r != 0 or o.strip() == "":
        logger.warn("can not get device information from %s" % dev_name)
        return None

    def get_data(e):
        return e.split("=")[1].strip().strip('"')

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
        elif entry.startswith('TRAN'):
            s.transport = get_data(entry)
            s.source = s.transport

    return s

def get_device_path(dev):
    for symlink in shell.call("udevadm info -q symlink -n %s" % dev).strip().split():
        if 'by-path' in symlink:
            return os.path.basename(symlink)

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



def get_lvm_default_config():
    class Config():
        def __init__(self, config_str):
            self.config_str = config_str

        def modify(self, config_dict):
            for keyword in config_dict:
                self.config_str = re.sub(r'.*%s.*' % keyword, "%s=%s" % (keyword, config_dict[keyword]), self.config_str)

        def write_to_file(self, path, create_if_not_exist=True):
            linux.write_file(path, self.config_str, create_if_not_exist=create_if_not_exist)

    @linux.retry(3, 1)
    def _get_config():
        return bash.bash_errorout("lvmconfig --type default")

    return Config(_get_config())


def config_lvm_by_sed(keyword, entry, files):
    warnings.warn("config_lvm_by_sed() is deprecated", DeprecationWarning)
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
            linux.sync_file(os.path.join(LVM_CONFIG_PATH, f))
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
        linux.sync_file(os.path.join(LVM_CONFIG_PATH, f))


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
    os.chmod(lvmlockd_service_path, 0o644)

    if not os.path.exists(LVMLOCKD_LOG_RSYSLOG_PATH):
        content = """if $programname == 'lvmlockd' then %s 
& stop
""" % LVMLOCKD_LOG_FILE_PATH
        with open(LVMLOCKD_LOG_RSYSLOG_PATH, 'w') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(LVMLOCKD_LOG_RSYSLOG_PATH, 0o644)
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
@linux.retry(3, 1)
def get_lvm_version():
    cmd = shell.ShellCmd("lvm version")
    cmd(is_exception=True)
    return cmd.stdout

@bash.in_bash
def is_lvmlockd_socket_abnormal():
    if linux.check_unixsock_connection(LVMLOCKD_SOCKET) == 0:
        return False

    @linux.retry(3, 1)
    def check_lvmlockd_log():
        # check if lvmlockd can receive the lvm command
        fake_vg = 'fake_vg_%s' % linux.get_current_timestamp()
        start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        vgck(fake_vg, 10)
        end_time = (datetime.datetime.now() + datetime.timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S")
        if not lvmlockd_log_search('vgck', start_time, end_time):
            raise RetryException("lvmlockd socket exceptions!")
    try:
        check_lvmlockd_log()
        return False
    except Exception as e:
        logger.warn(str(e))
        return True

@bash.in_bash
def start_lock_service(io_timeout=40):
    if not os.path.exists(os.path.dirname(LVMLOCKD_LOG_FILE_PATH)):
        os.mkdir(os.path.dirname(LVMLOCKD_LOG_FILE_PATH))

    logger.info("get lvm version info:\n %s" % get_lvm_version())
    config_lvmlockd(io_timeout)

    def is_lvmlockd_upgraded():
        running_lockd_version = get_running_lvmlockd_version()
        return running_lockd_version is not None and LooseVersion(running_lockd_version) < LooseVersion(get_lvmlockd_version())

    def need_restart_sanlock():
        running_patch_version = get_running_sanlock_patch_version()
        local_patch_version = get_sanlock_patch_version()
        if not running_patch_version:
            # sanlock not running
            return False
        elif not local_patch_version.isdigit():
            return False
        elif not running_patch_version.isdigit() or int(local_patch_version) > int(running_patch_version):
            # patch version N  ->  patch version >N or other version  ->  patch version N
            return True
        if sanlock.SanlockClientStatusParser().get_config("max_sectors_kb_ignore") == "0":
            logger.debug("need restarting sanlock to reload config")
            return True
        return False


    restart_sanlock = need_restart_sanlock()
    restart_lvmlockd = restart_sanlock or is_lvmlockd_upgraded() or \
                       (LooseVersion(get_lvmlockd_version()) >= LooseVersion("2.03") and LvmlockdStatus().failed)
    if restart_sanlock:
        stop_sanlock()
    if restart_lvmlockd:
        write_lvmlockd_adopt_file()
        stop_lvmlockd()
        linux.rm_file_force(LVMLOCKD_SOCKET)

    r = bash.bash_r("systemctl status sanlock | grep '(running)'")
    if r != 0 and not linux.find_process_by_command("sanlock"):
        bash.bash_r("timeout 30 systemctl stop sanlock")
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
    os.chmod(LVMLOCKD_LOG_LOGROTATE_PATH, 0o644)

@bash.in_bash
def update_lockspace_io_timeout_if_need(vgName, io_timeout):
    lockspace_name = "lvm_%s" % vgName
    if io_timeout is None or str(io_timeout).strip() == "":
        logger.warn("skip updating sanlock io timeout for lockspace %s: invalid io_timeout %s" %
                    (lockspace_name, io_timeout))
        return

    try:
        expected_io_timeout = int(io_timeout)
    except (TypeError, ValueError):
        logger.warn("skip updating sanlock io timeout for lockspace %s: invalid io_timeout %s" %
                    (lockspace_name, io_timeout))
        return

    parser = sanlock.SanlockClientStatusParser()
    lockspace = parser.get_lockspace_record(vgName)
    if not lockspace:
        if not parser.status:
            logger.warn("skip updating sanlock io timeout for lockspace %s: failed to query sanlock status" %
                        lockspace_name)
            return
        logger.warn("skip updating sanlock io timeout for lockspace %s: lockspace is not found in sanlock status" %
                    lockspace_name)
        return

    try:
        current_io_timeout = lockspace.get_io_timeout()
    except Exception as e:
        logger.warn("skip updating sanlock io timeout for lockspace %s: invalid sanlock status, %s" %
                    (lockspace_name, str(e)))
        return

    if current_io_timeout == expected_io_timeout:
        logger.debug("sanlock io timeout for lockspace %s is already %s" %
                     (lockspace_name, expected_io_timeout))
        return

    r, o, e = bash.bash_roe("timeout -s SIGKILL %s sanlock client set_config -s %s -o %s" %
                            (SANLOCK_CLIENT_SET_CONFIG_TIMEOUT, linux.shellquote(lockspace_name),
                             expected_io_timeout))
    if r != 0:
        logger.warn("failed to update sanlock io timeout for lockspace %s from %s to %s, stdout: %s, stderr: %s" %
                    (lockspace_name, current_io_timeout, expected_io_timeout, o, e))
        return

    logger.info("updated sanlock io timeout for lockspace %s from %s to %s" %
                (lockspace_name, current_io_timeout, expected_io_timeout))

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
def stop_sanlock():
    pid = get_sanlock_pid()
    if pid:
        linux.kill_process(pid)
        bash.bash_r("timeout 30 systemctl stop sanlock.service")

@bash.in_bash
def start_vg_lock(vgUuid, hostId, retry_times_for_checking_vg_lockspace):
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
            continue_lockspace_track.update({vgUuid: True})
            return True

    def check_lockspace():
        r = sanlock.dd_check_lockspace("/dev/mapper/%s-lvmlock" % vgUuid)
        if r != 0:
            bash.bash_roe("dmsetup remove %s-lvmlock" % vgUuid)
            return
        elif continue_lockspace_track.get(vgUuid) is False:
            logger.debug("direct init lockspace[%s] has already been executed but the lockspace has not been restored, skip it" % vgUuid)
            return
        sanlock.check_delta_lease(vgUuid, hostId)
        continue_lockspace_track.update({vgUuid: False})

    @linux.retry(times=5, sleep_time=random.uniform(0.1, 10))
    def start_lock(vgUuid):
        modify_sanlock_config("use_zstack_vglock_timeout", 1)
        modify_sanlock_config("use_zstack_vglock_large_delay", 1)
        r, o, e = bash.bash_roe("vgchange --lock-start %s" % vgUuid)
        modify_sanlock_config("use_zstack_vglock_timeout", 0)
        modify_sanlock_config("use_zstack_vglock_large_delay", 0)

        try:
            if r != 0:
                raise Exception("vgchange --lock-start failed: return code: %s, stdout: %s, stderr: %s" % (r, o, e))
            vg_lock_exists(vgUuid)
        except Exception:
            check_lockspace()
            sanlock.init_gllk_if_need(vgUuid)
            raise
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
    archive_files = len([f for f in os.listdir(LVM_CONFIG_ARCHIVE_PATH) if vgUuid in f])
    if archive_files > 10:
        bash.bash_r("ls -rt %s | grep %s | head -n %s | xargs -i rm -rf %s/{}" % (LVM_CONFIG_ARCHIVE_PATH, vgUuid, archive_files-10, LVM_CONFIG_ARCHIVE_PATH))

@bash.in_bash
def quitLockServices():
    bash.bash_roe("sanlock client shutdown")
    bash.bash_roe("timeout 30 systemctl stop sanlock.service")
    bash.bash_roe("lvmlockctl -q")


@bash.in_bash
def drop_vg_lock(vgUuid):
    def clear_orphan_locks():
        r, sanlock_locks = bash.bash_ro("sanlock client status | grep 'r lvm_{}'".format(vgUuid))
        if r != 0:
            return
        lv_locks = bash.bash_o("lvmlockctl -i | grep -E 'LK LV (ex|sh)'")
        for line in sanlock_locks.strip().splitlines():
            lock_uuid = line.split()[1].split(":")[1]
            if "VGLK" in lock_uuid or "GLLK" in lock_uuid or lock_uuid not in lv_locks:
                bash.bash_r("sanlock client release -%s" % line.replace(" p ", " -p ").replace(" C ", " -C "))
    
    clear_orphan_locks()
    bash.bash_roe("lvmlockctl --gl-disable %s" % vgUuid)
    bash.bash_roe("lvmlockctl --drop %s" % vgUuid)


@bash.in_bash
def get_vg_lvm_uuid(vgUuid):
    return bash.bash_o("vgs --nolocking -t --noheading -ouuid %s" % vgUuid).strip()


@linux.retry(5, 0.5)
def get_running_host_id(vgUuid):
    cmd = shell.ShellCmd("sanlock client gets | awk -F':' '/%s/{ print $2 }'" % vgUuid)
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
def is_running_vm_using_lun_passthrough():
    return bash.bash_r('''grep -rlF "<disk type='block' device='lun'" %s/*''' % LIVE_LIBVIRT_XML_DIR) == 0


@bash.in_bash
def flush_mpath(disk):
    wwid = get_dm_wwid(disk)
    bash.bash_roe("multipath -f %s" % disk)
    lun_passthrough_in_use = is_running_vm_using_lun_passthrough()
    if lun_passthrough_in_use and wwid:
        # re-create only this disk's map; a host-wide multipathd reload would
        # suspend in-use maps and abort in-flight IO on LUN-passthrough guests
        logger.warn("re-create multipath map %s for %s without host-wide multipathd reload because a LUN-passthrough VM is running" % (wwid, disk))
        r, o, e = bash.bash_roe("multipath %s && sleep 1" % wwid)
        if r != 0:
            logger.warn("failed to re-create multipath map %s for %s, return code: %s, stdout: %s, stderr: %s" % (wwid, disk, r, o, e))
    else:
        if lun_passthrough_in_use:
            logger.warn("fall back to host-wide multipathd reload for %s because WWID is unknown while a LUN-passthrough VM is running" % disk)
        r, o, e = bash.bash_roe("systemctl reload multipathd.service && sleep 1")
        if r != 0:
            logger.warn("failed to reload multipathd while flushing %s, return code: %s, stdout: %s, stderr: %s" % (disk, r, o, e))


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
            flush_mpath(disk)

        if exists_vg is not None:
            bash.bash_r("grep -l %s /etc/drbd.d/* | xargs rm" % exists_vg)
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
        h = linux.listdir("/sys/class/block/%s/holders/" % disk_name)
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


def get_all_vg_size():
    # type: () -> dict[str, tuple[int, int]]
    d = {}

    o = bash.bash_o("vgs --nolocking -t %s --noheadings --separator : --units b -o name,vg_size,vg_free,vg_lock_type")
    if not o:
        return d

    for line in o.splitlines():
        xs = line.strip().split(':')
        vg_name = xs[0]
        vg_size = int(xs[1].strip("B"))
        vg_free = int(xs[2].strip("B"))

        if "sanlock" in line:
            d[vg_name] = (vg_size, vg_free)
            continue

        pools = get_thin_pools_from_vg(vg_name)
        if len(pools) == 0:
            d[vg_name] = (vg_size, vg_free)
            continue

        for pool in pools:
            vg_free += int(pool.free)
        d[vg_name] = (vg_size, vg_free)

    return d


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
        shell.run('%s --deltag %s %s' % (subcmd("lvchange"), tag, path))


def add_lv_tag(path, tag):
    if not has_lv_tag(path, tag):
        shell.run('%s --addtag %s %s' % (subcmd("lvchange"), tag, path))


def get_meta_lv_path(path):
    return path+"_meta"


def delete_image(path, tag, deactive=True):
    def activate_and_remove(f, deactive):
        if deactive:
            _active_lv(f, shared=False)
        backing = linux.qcow2_get_backing_file(f)
        shell.check_run("%s -y -Stags={%s} %s" % (subcmd("lvremove"), tag, f))
        return backing

    fpath = path
    activate_and_remove(fpath, deactive)
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



def get_lv_discard_max_bytes(path):
    pvs = [os.path.realpath(pv) for pv in get_lv_location(path) if os.path.exists(pv)]
    if len(pvs) == 0:
        raise Exception("cannot get pvs for lv %s" % path)

    pv_discard_max_bytes = sorted([linux.get_block_discard_max_bytes(pv) for pv in pvs])
    return pv_discard_max_bytes[0]


def get_lv_discard_granularity(path):
    pvs = [os.path.realpath(pv) for pv in get_lv_location(path) if os.path.exists(pv)]
    if len(pvs) == 0:
        raise Exception("cannot get pvs for lv %s" % path)

    pv_discard_granularity = sorted([linux.get_block_discard_granularity(pv) for pv in pvs])
    return pv_discard_granularity[0]

@bash.in_bash
@linux.retry(times=15, sleep_time=random.uniform(0.1, 3))
def create_lv_from_absolute_path(path, size, tag="zs::sharedblock::volume", lock=True, exact_size=False, pe_ranges=None):
    ## if LV exists, false will be returned, otherwise it will create LV and return true
    if lv_exists(path):
        return False

    vgName = path.split("/")[2]
    lvName = path.split("/")[3]
    pe_range = ' '.join(get_allocated_pvs(vgName) if pe_ranges is None else pe_ranges)

    exact_size |= tag == IMAGE_TAG
    size = round_to(int(size), 512) if exact_size else round_to(calcLvReservedSize(size), 512)
    r, o, e = bash.bash_roe("%s -ay --wipesignatures y -y --addtag %s --size %sb --name %s %s %s" %
                         (subcmd("lvcreate"), tag, size, lvName, vgName, pe_range))

    if r != 0:
        if lv_exists(path):
            return False
        raise Exception("failed to create lv %s, lvcreate return: %s, %s, %s" % (path, r, o, e))

    if not lv_exists(path):
        raise Exception("can not find lv %s after create, lvcreate return: %s, %s, %s" % (path, r, o, e))

    if lock:
        dd_zero(path)
        deactive_lv(path)
    else:
        dd_zero(path)

    return True

def create_lv_from_cmd(path, size, cmd, tag="zs::sharedblock::volume", lvmlock=True, pe_ranges=None):
    update_pv_allocate_strategy(cmd)
    start_time = linux.get_current_timestamp()
    timeout = report.get_timeout(cmd)
    def _delete_lv(args):
        delete_lv(path)
        raise Exception("create lv timeout, timeout is %d s, execution time is %d s" % (timeout, linux.get_current_timestamp()-start_time))

    @linux.timeout_defer(timeout_in_seconds=timeout, handler=_delete_lv)
    def create_lv(path):
        # TODO(weiw): fix it
        if "ministorage" in tag and cmd.provisioning == VolumeProvisioningStrategy.ThinProvisioning:
            create_thin_lv_from_absolute_path(path, size, tag, lvmlock)
        elif cmd.provisioning == VolumeProvisioningStrategy.ThinProvisioning and size > cmd.addons[thinProvisioningInitializeSize]:
            create_lv_from_absolute_path(path, cmd.addons[thinProvisioningInitializeSize], tag, lvmlock, pe_ranges=pe_ranges)
        else:
            create_lv_from_absolute_path(path, size, tag, lvmlock, cmd.volumeFormat == 'raw', pe_ranges=pe_ranges)

    create_lv(path)


@bash.in_bash
@linux.retry(times=15, sleep_time=random.uniform(0.1, 3))
def create_thin_lv_from_absolute_path(path, size, tag, lock=False):
    if lv_exists(path):
        return

    vgName = path.split("/")[2]
    lvName = path.split("/")[3]

    thin_pool = get_thin_pool_from_vg(vgName)
    assert thin_pool != ""

    r, o, e = bash.bash_roe("%s --wipesignatures y -y --addtag %s -n %s -V %sb --thinpool %s %s" %
                  (subcmd("lvcreate"), tag, lvName, round_to(calcLvReservedSize(size), 512), thin_pool, vgName))
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
    r, o, e = bash.bash_roe("%s %s --size %sb %s" % (subcmd("lvresize"), _force, calcLvReservedSize(size), path))
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
@linux.retry(times=15, sleep_time=random.uniform(0.1, 3))
def extend_lv(path, extend_size, skip_if_sufficient=False):
    final_size = calcLvReservedSize(extend_size)
    if skip_if_sufficient and int(get_lv_size(path)) >= final_size:
        return

    r, o, e = bash.bash_roe("%s --size %sb %s" % (subcmd("lvextend"), final_size, path))
    if r == 0:
        logger.debug("successfully extend lv %s size to %s" % (path, extend_size))
        return
    elif "matches existing size" in e or "matches existing size" in o:
        logger.debug("lv %s size already matches existing size: %s, return as successful" % (path, extend_size))
        return
    else:
        raise RetryException("extend lv %s to size %s failed, return code: %s, stdout: %s, stderr: %s" %
                             (path, extend_size, r, o, e))

@bash.in_bash
def extend_lv_from_cmd(path, size, cmd, extend_thin_by_specified_size=False, skip_if_sufficient=False):
    # type: (str, long, object, bool) -> None
    if cmd.provisioning is None or \
            cmd.addons is None or \
            cmd.provisioning != VolumeProvisioningStrategy.ThinProvisioning:
        extend_lv(path, size, skip_if_sufficient)
        return

    current_size = int(get_lv_size(path))

    if extend_thin_by_specified_size:
        v_size = linux.qcow2_virtualsize(path)
        if size + cmd.addons[thinProvisioningInitializeSize] > v_size:
            size = v_size
        else:
            size = size + cmd.addons[thinProvisioningInitializeSize]
        extend_lv(path, size, skip_if_sufficient)
        return

    if int(size) - current_size > cmd.addons[thinProvisioningInitializeSize]:
        extend_lv(path, current_size + cmd.addons[thinProvisioningInitializeSize], skip_if_sufficient)
    else:
        extend_lv(path, size, True)


def active_lv(path, shared=False):
    op = LvLockOperator.get_lock_cnt_or_else_none(path)
    if op:
        op.force_lock(LvmlockdLockType.SHARE if shared else LvmlockdLockType.EXCLUSIVE)
    else:
        _active_lv(path, shared)

def _need_retry_active_lv(arg, exception):
    path = arg[0]
    def check_lv_lock_on_client():
        LV_UUID = lv_uuid(path)
        if not LV_UUID:
            raise Exception("cannot get lv uuid of path[%s]" % path)

        cmd = "sanlock client status | grep %s" % LV_UUID
        return bash.bash_r(cmd) == 0

    def get_lock_hold_by_us():
        LV_UUID = lv_uuid(path)
        if not LV_UUID:
            logger.warn("cannot get lv uuid of path[%s]" % path)
            return None

        VG_UUID = get_vg_uuid(path)
        lockspace = get_lockspace(VG_UUID)
        if not lockspace:
            logger.warn("cannot find lockspace of %s" % VG_UUID)
            return None

        LOCKSPACE_NAME = lockspace.split(":")[0]
        HOST_ID = lockspace.split(":")[1]
        LVMLOCK_PATH = lockspace.split(":")[2]
        LV_START = lv_offset.get(path) if lv_offset.get(path) is not None else "0"
        LV_END = "1048576" if lv_offset.get(path) is not None else get_lv_size("/dev/%s/lvmlock" % VG_UUID)

        cmd = "sanlock direct dump %s:%s:%s | grep %s -m1 | awk '{print $1,$4,$5}'" % (LVMLOCK_PATH, LV_START, LV_END, LV_UUID)
        r, o, e = bash.bash_roe(cmd)
        if r == 0 and o is not None and o.strip() != "":
            res = o.strip().split()
            offset = int(res[0])
            timestamp = int(res[1])
            host_id = int(res[2])
            lv_offset.update({path:str(offset)})
            if timestamp != 0 and host_id == int(HOST_ID):
                lock = "{}:{}:{}:{}".format(LOCKSPACE_NAME, LV_UUID, LVMLOCK_PATH, offset)
                return lock
            else:
                logger.debug("lv[path:%s] lockd by other host" % path)

        return None

    if "LV locked by other host" not in str(exception) or check_lv_lock_on_client():
        return False

    lock = get_lock_hold_by_us()
    if lock is not None:
        logger.debug("find lv lock hold by us on lockspace but not on client, directly init lv[path:%s]" % path)
        return sanlock.direct_init_resource(lock) == 0

    return False

@linux.retry_with_check(handler=_need_retry_active_lv)
def active_lv_with_check(path, shared=False):
    active_lv(path, shared)

def deactive_lv(path, raise_exception=True):
    op = LvLockOperator.get_lock_cnt_or_else_none(path)
    if op:
        op.force_unlock(raise_exception)
    else:
        _deactive_lv(path, raise_exception)

@bash.in_bash
def _active_lv(path, shared=False):
    @linux.retry(times=10, sleep_time=random.uniform(0.1, 3))
    def active():
        bash.bash_errorout("%s %s %s" % (subcmd("lvchange"), flag, path))
        if lv_is_active(path) is False:
            raise Exception("active lv %s with %s failed" % (path, flag))

    def lv_lock_not_exists():
        return bash.bash_r("lvmlockctl -i | grep %s" % lv_uuid(path)) != 0

    flag = "-ay"
    if shared:
        flag = "-asy"

    # if lv does not have a lock, we will try to reactivate it
    if os.path.exists(path) and lv_lock_not_exists():
        bash.bash_r("%s -an %s" % (subcmd("lvchange"), path))

    active()


@bash.in_bash
def _deactive_lv(path, raise_exception=True):
    if not lv_exists(path):
        return
    if not lv_is_active(path):
        return

    @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
    def _deactive():
        r = 0
        e = None
        if raise_exception:
            o = bash.bash_errorout("%s -an %s" % (subcmd("lvchange"), path))
        else:
            r, o, e = bash.bash_roe("%s -an %s" % (subcmd("lvchange"), path))
        if lv_is_active(path):
            raise RetryException("lv %s is still active after lvchange -an, returns code: %s, stdout: %s, stderr: %s"
                                 % (path, r, o, e))
    try:
        _deactive()
    except Exception as e:
        if "in use" in str(e):
            # just for debugging
            o = linux.lsof(path)
            if o == "":
                o = ['vm-' + p.name for p in linux.find_qemu_for_volume_in_use(path)]
            logger.warn("find lv used by other process:\n%s" % str(o))
        raise

@bash.in_bash
def lv_in_use(path):
    if not os.path.exists(path):
        return False

    o = bash.bash_errorout("%s --noheadings %s -olv_device_open" % (subcmd("lvs"), path))
    return any(line.strip() == "open" for line in o.splitlines())


def discard_lv(path, discard_strategy, deadline=None):
    if discard_strategy == LvDiscardStrategy.NEVER:
        return False
    elif discard_strategy != LvDiscardStrategy.ALWAYS and discard_strategy != LvDiscardStrategy.AUTO:
        logger.debug("unknown discard strategy %s" % discard_strategy)
        return False

    try:
        if not lv_exists(path):
            return False

        discard_max_bytes = get_lv_discard_max_bytes(path)
        if discard_max_bytes == 0:
            # not support block discard
            return False

        slow_discard = discard_max_bytes < PV_DISCARD_MIN_SIZE_IN_BYTES
        if discard_strategy == LvDiscardStrategy.AUTO and slow_discard:
            return False

        with OperateLv(path):
            if lv_in_use(path):
                logger.warn("cannot discard lv because lv[%s] in use" % path)
                return False

            step = min(max(get_lv_discard_max_bytes(path), PV_DISCARD_MIN_SIZE_IN_BYTES), PV_DISCARD_MAX_SIZE_IN_BYTES)
            discard_granularity = get_lv_discard_granularity(path)
            step = int(round_to(step, discard_granularity))
            timeout = int(deadline - time.time()) if deadline is not None else None
            if timeout is not None and timeout <= 120:
                logger.debug("skip discard lv because timeout[%s] is too short" % timeout)
                return False

            shell.call("%s blkdiscard %s --step %s" % ("timeout -s SIGKILL %s" % (timeout-120) if timeout else "", path, step))
    except Exception as e:
        logger.warn("discard lv %s exception: %s" % (path, str(e)))
        return False

    return True

@bash.in_bash
def delete_lv(path, raise_exception=True, deactive=True):
    logger.debug("deleting lv %s" % path)
    if deactive:
        _deactive_lv(path, False)
    # remove meta-lv if any
    if lv_exists(get_meta_lv_path(path)):
        shell.run("%s -y %s" % (subcmd("lvremove"), get_meta_lv_path(path)))
    if not lv_exists(path):
        return
    if raise_exception:
        return bash.bash_errorout("%s -y %s" % (subcmd("lvremove"), path))
    else:
        return bash.bash_o("%s -y %s" % (subcmd("lvremove"), path))


@bash.in_bash
def delete_lv_meta(path, raise_exception=True):
    logger.debug("deleting lv meta %s" % path)
    meta_path = get_meta_lv_path(path)
    if not lv_exists(meta_path):
        return
    if raise_exception:
        o = bash.bash_errorout("%s -y %s" % (subcmd("lvremove"), meta_path))
    else:
        o = bash.bash_o("%s -y %s" % (subcmd("lvremove"), meta_path))
    return o


def log_vg_lock_diagnostics(vgUuid, reason, warn=False): # type: (str, str, bool) -> None
    def shrink(output):
        if output is None:
            return None
        if len(output) > 4096:
            return output[:4096] + "...<truncated>"
        return output

    accept_all_config = (
        '--config \'devices/filter=["a|.*|"] devices/global_filter=["a|.*|"]\''
    )
    commands = [
        ("sanlock_gets", "timeout -s SIGKILL 10 sanlock client gets | grep %s || true" % vgUuid),
        ("sanlock_status", "timeout -s SIGKILL 10 sanlock client status | grep %s || true" % vgUuid),
        ("lvmlockctl", "timeout -s SIGKILL 10 lvmlockctl -i -d | grep -A10 -B10 %s || true" % vgUuid),
        ("dmsetup_ls", "timeout -s SIGKILL 10 dmsetup ls | grep %s || true" % vgUuid),
        ("lvmlock_readlink", "readlink -f /dev/mapper/%s-lvmlock || true" % vgUuid),
        ("lvmlock_info", "timeout -s SIGKILL 10 dmsetup info %s-lvmlock || true" % vgUuid),
        ("lvmlock_table", "timeout -s SIGKILL 10 dmsetup table %s-lvmlock || true" % vgUuid),
        ("pvs", "timeout -s SIGKILL 20 pvs --nolocking -t --foreign %s "
                "-o pv_name,pv_uuid,vg_name,vg_uuid,dev_size,pv_size 2>&1 | grep %s || true" %
                (accept_all_config, vgUuid)),
        ("vgs", "timeout -s SIGKILL 20 vgs --nolocking -t --foreign --shared %s "
                "-o vg_name,vg_uuid,pv_name,pv_uuid,pv_count,lock_type,lock_args,tags %s 2>&1 || true" %
                (accept_all_config, vgUuid)),
        ("lvs", "timeout -s SIGKILL 20 lvs --nolocking -t --foreign %s -a -Svg_name=%s "
                "-o vg_name,lv_name,lv_uuid,lv_path,lv_size,lv_attr,lock_args,tags 2>&1 || true" %
                (accept_all_config, vgUuid)),
    ]
    diagnostics = []
    for label, cmd in commands:
        r, o, e = bash.bash_roe("(%s) | head -c 4096" % cmd)
        diagnostics.append({
            "label": label,
            "return_code": r,
            "stdout": shrink(o),
            "stderr": shrink(e),
        })
    msg = "VG lock diagnostics for %s [%s]: %s" % (vgUuid, reason, simplejson.dumps(diagnostics))
    if warn:
        logger.warn(msg)
    else:
        logger.debug(msg)


@bash.in_bash
def remove_device_map_for_vg(vgUuid, raise_exception=False): # type: (str, bool) -> None
    o = bash.bash_o("dmsetup ls | awk '/%s/{print $1}'" % vgUuid).strip().splitlines()
    if len(o) == 0:
        logger.debug("no device maps found for VG %s" % vgUuid)
        return
    log_vg_lock_diagnostics(vgUuid, "before removing device maps")
    failed_maps = []
    for dm in o:
        dm = dm.strip()
        r, out, err = bash.bash_roe("timeout -s SIGKILL 10 dmsetup remove %s" % dm)
        if r != 0:
            if bash.bash_r("timeout -s SIGKILL 10 dmsetup info %s >/dev/null 2>&1" % dm) != 0:
                logger.debug("device map %s for VG %s was already removed" % (dm, vgUuid))
                continue
            failed_maps.append({"dm": dm, "return_code": r, "stdout": out, "stderr": err})
    if failed_maps:
        log_vg_lock_diagnostics(vgUuid, "after failed device map removal", warn=True)
        msg = "failed to remove device maps for VG %s: %s" % (vgUuid, simplejson.dumps(failed_maps))
        if raise_exception:
            raise Exception(msg)
        logger.warn(msg)
        return
    logger.info("removed device maps for VG %s: %s" % (vgUuid, o))

@bash.in_bash
def remove_device_map_for_vg_except(vgUuid, keep_device_map): # type: (str, list[str]) -> None
    o = bash.bash_o("dmsetup ls | awk '/%s/{print $1}'" % vgUuid).strip().splitlines()
    if len(o) == 0:
        return
    for dm in o:
        if dm in keep_device_map:
            continue
        bash.bash_roe("dmsetup remove %s" % dm.strip())

@bash.in_bash
def lv_exists(path):
    r = bash.bash_r("lvs --nolocking -t %s" % path)
    return r == 0


@bash.in_bash
def vg_exists(vgUuid):
    cmd = shell.ShellCmd("vgs --nolocking -t %s" % vgUuid)
    cmd(is_exception=False)
    return cmd.return_code == 0

@lock.file_lock("/var/run/zstack/sharedblock.ping.lock")
def refresh_lv_uuid_cache_if_need():
    global lv_uuid_cache_last_refresh_time
    if linux.get_current_timestamp() - lv_uuid_cache_last_refresh_time <= LV_UUID_REFRESH_INTERVAL_IN_SEC:
        return

    lv_uuid_cache.clear()
    cmd = shell.ShellCmd("lvs -olv_path,uuid,lv_tags --nolocking -t --noheading | grep %s" % COMMON_TAG)
    cmd(is_exception=False)
    if cmd.return_code != 0:
        logger.debug("refresh lv uuid cache error: %s" % cmd.stderr)
        return
    for line in cmd.stdout.strip().splitlines():
        lv_path = line.strip().split()[0]
        uuid = line.strip().split()[1]
        lv_uuid_cache.update({lv_path: uuid})
    lv_uuid_cache_last_refresh_time = linux.get_current_timestamp()
    logger.debug("lv uuid cache refreshed")


def lv_uuid(path):
    cmd = shell.ShellCmd("lvs --nolocking -t --noheadings %s -ouuid" % path)
    cmd(is_exception=False)
    uuid = cmd.stdout.strip()
    if cmd.return_code == 0 and uuid != '':
        return uuid


def lv_is_active(lv_path):
    # NOTE(weiw): use readonly to get active may return 'unknown'
    r = bash.bash_r("lvs --nolocking -t --noheadings %s -oactive | grep -w active" % lv_path)
    if r == 0:
        return True
    return os.path.exists(lv_path)


def get_lv_attr(lv_path, *attr):
    o = bash.bash_o("lvs --nolocking -t --noheadings %s -o%s --reportformat json" % (lv_path, ",".join(attr)))
    o = simplejson.loads(o)
    return o["report"][0]["lv"][0]


@bash.in_bash
def lv_rename(old_abs_path, new_abs_path, overwrite=False):
    if not lv_exists(new_abs_path):
        return bash.bash_roe("%s %s %s" % (subcmd("lvrename"), old_abs_path, new_abs_path))

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
        bash.bash_errorout("%s %s %s" % (subcmd("lvrename"), tmp_path, new_abs_path))
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
    # type: (str, bool, str, float, str) -> str
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
    bash.bash_errorout("blockdev --flushbufs %s; lvcreate --snapshot -n %s %s %s" % (absolutePath, snapName, absolutePath, size_command))
    path = "/".join(absolutePath.split("/")[:-1]) + "/" + snapName
    if size_command == "":
        bash.bash_r("%s -ay -K %s" % (subcmd("lvchange"), path))
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
        output = bash.bash_o("lvmlockctl -i | grep %s | head -n1 | awk '{print $3}'" % uuid)
        return LvmlockdLockType.from_abbr(output.strip(), raise_exception=True)

    locking_type = LvmlockdLockType.NULL
    active = None
    uuid = None
    with lock.NamedLock(path.split("/")[-1]):
        try:
            attr = get_lv_attr(path, "lv_uuid", "lv_active")
            uuid = attr.get("lv_uuid")
            active = attr.get("lv_active") == "active"
            if not active:
                return locking_type
            locking_type = _get_lv_locking_type(path)
        except Exception as e:
            output = bash.bash_o("lvmlockctl -i | grep %s | head -n1 | awk '{print $3}'" % uuid)
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


# TODO(weiw): This is typically mini usage
def qcow2_lv_recursive_active(abs_path, lock_type):
    # type: (str, int) -> None
    backing = linux.qcow2_get_backing_file(abs_path)
    active_lv(abs_path, lock_type == LvmlockdLockType.SHARE)

    if backing != "":
        qcow2_lv_recursive_active(backing, LvmlockdLockType.SHARE)


_internal_lock = threading.RLock()
_lv_locks = weakref.WeakValueDictionary()


class LvLockOperator(object):
    def __init__(self, abs_path):
        self.op_lock = threading.Lock()
        self.inited = False
        self.abs_path = abs_path
        self.exists_locks = []

    def _init(self):
        exists_lock = get_lv_locking_type(self.abs_path)
        self.exists_locks = [] if exists_lock == LvmlockdLockType.NULL else [exists_lock]
        self.inited = True
        logger.debug("lv [path:%s] lock operator inited, existing lock: %s" % (self.abs_path, exists_lock))

    def lock(self, target_lock):
        with self.op_lock:
            if not self.inited:
                self._init()

            if all(l < target_lock for l in self.exists_locks):
                _active_lv(self.abs_path, target_lock == LvmlockdLockType.SHARE)
            self.exists_locks.append(target_lock)
            logger.debug("lv [path:%s] add lock %d, existing locks: %s" % (self.abs_path, target_lock, self.exists_locks))

    def force_lock(self, target_lock):
        with self.op_lock:
            self.exists_locks = filter(lambda exist_lock: exist_lock <= target_lock, self.exists_locks)
            _active_lv(self.abs_path, target_lock == LvmlockdLockType.SHARE)
            self.exists_locks.append(target_lock)
            logger.debug("lv [path:%s] force lock to %d, existing locks: %s" % (self.abs_path, target_lock, self.exists_locks))

    def unlock(self, target_lock):
        with self.op_lock:
            try:
                self.exists_locks.remove(target_lock)
            except ValueError:
                pass

            after_lock_type = LvmlockdLockType.NULL if len(self.exists_locks) == 0 else max(self.exists_locks)
            if after_lock_type == LvmlockdLockType.NULL:
                _deactive_lv(self.abs_path, raise_exception=False)
            elif after_lock_type == LvmlockdLockType.SHARE:
                _active_lv(self.abs_path, True)

            logger.debug("lv [path:%s] remove lock %d, unlock to %d, existing locks: %s"
                         % (self.abs_path, target_lock, after_lock_type, self.exists_locks))

    def force_unlock(self, raise_exception=True):
        with self.op_lock:
            del self.exists_locks[:]
            _deactive_lv(self.abs_path, raise_exception)
            logger.debug("lv [path:%s] force unlock to 0" % self.abs_path)

    @staticmethod
    def get_lock_cnt(abs_path):
        global _lv_locks, _internal_lock
        with _internal_lock:
            lock_cnt = _lv_locks.get(abs_path, LvLockOperator(abs_path))
            if not abs_path in _lv_locks:
                _lv_locks[abs_path] = lock_cnt
            return lock_cnt

    @staticmethod
    def get_lock_cnt_or_else_none(abs_path):
        global _lv_locks, _internal_lock
        with _internal_lock:
            return _lv_locks.get(abs_path)

class OperateLv(object):
    def __init__(self, abs_path, shared=False, delete_when_exception=False):
        self.abs_path = abs_path
        self.lock_ref_cnt = LvLockOperator.get_lock_cnt(abs_path)
        self.target_lock = LvmlockdLockType.EXCLUSIVE if shared is False else LvmlockdLockType.SHARE
        self.delete_when_exception = delete_when_exception

    def __enter__(self):
        self.lock_ref_cnt.lock(self.target_lock)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None and self.delete_when_exception is True:
            delete_lv(self.abs_path, False)
            return

        self.lock_ref_cnt.unlock(self.target_lock)


class RecursiveOperateLv(object):
    def __init__(self, abs_path, shared=False, skip_deactivate_tags=None, delete_when_exception=False):
        # type: (str, bool, list[str], bool) -> None
        self.abs_path = abs_path
        self.shared = shared
        self.lock_ref_cnt = LvLockOperator.get_lock_cnt(abs_path)
        self.target_lock = LvmlockdLockType.EXCLUSIVE if shared is False else LvmlockdLockType.SHARE
        self.backing = None
        self.delete_when_exception = delete_when_exception
        self.skip_deactivate_tags = skip_deactivate_tags

    def __enter__(self):
        self.lock_ref_cnt.lock(self.target_lock)
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

        self.lock_ref_cnt.unlock(self.target_lock)

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


@bash.in_bash
def check_stuck_vglk_and_gllk():
    stucked_vglks = {}
    def vglk_in_use(vglk):
        return bash.bash_r("lvmlockctl -i | grep %s -A 5 | grep -E 'LK VG (ex|sh)'" % vglk) == 0

    @linux.retry(6, sleep_time=random.uniform(2, 3))
    def check_stuck_vglk():
        if not stucked_vglks:
            # init stucked vglk
            r, o = bash.bash_ro("sanlock client status | grep ':VGLK:'")
            if r != 0:
                return
            for line in o.strip().splitlines():
                vglk = line.split()[1].split(":")[0]
                stucked_vglks.update({vglk: line})
            logger.debug("found sanlock vglk stuck: %s" % simplejson.dumps(stucked_vglks))
            raise RetryException()
        for vglk in stucked_vglks.keys():
            if bash.bash_r("sanlock client status | grep '%s'" % stucked_vglks.get(vglk)) != 0 or vglk_in_use(vglk):
                stucked_vglks.pop(vglk)
        if len(stucked_vglks) != 0:
            logger.debug("found sanlock vglk stuck: %s" % simplejson.dumps(stucked_vglks))
            raise RetryException()
    try:
        check_stuck_vglk()
    except Exception as e:
        for stucked in stucked_vglks.values():  # type: str
            if "ADD" in stucked or "REM" in stucked:
                continue
            cmd = "sanlock client release -%s" % stucked.replace(" p ", " -p ").replace(" C ", " -C ")
            r, o, e = bash.bash_roe(cmd)
            logger.warn("find stuck vglk and already released, detail: [return_code: %s, stdout: %s, stderr: %s]" %
                        (r, o, e))

    check_lock = lock._get_lock("check-vglk-and-gllk")
    if check_lock.acquire(False) is False:
        logger.debug("other thread is checking vglk or gllk...")
        return

    def release_lock(lck):
        try:
            lck.release()
        except Exception:
            return
    try:
        sanlock.check_stuck_vglk_and_gllk()
    except Exception as e:
        logger.debug("an exception was found on checking abnormal vglk/gllk: %s" % str(e))
    finally:
        release_lock(check_lock)

@bash.in_bash
def fix_global_lock():
    if not ENABLE_DUP_GLOBAL_CHECK:
        return
    vg_names = bash.bash_o("lvmlockctl -i | awk '/lock_type=sanlock/{print $2}'").strip().splitlines()  # type: list
    vg_names.sort()
    if len(vg_names) < 2:
        return
    for vg_name in vg_names[1:]:
        bash.bash_roe("lvmlockctl --gl-disable %s" % vg_name)
    bash.bash_roe("lvmlockctl --gl-enable %s" % vg_names[0])

def fix_vglk(vg_uuid):
    vglk = sanlock.get_vglk(vg_uuid)
    if not vglk:
        return
    hosts_state = sanlock.get_hosts_state("lvm_" + vg_uuid)
    if hosts_state is not None and hosts_state.get_live_min_hostid() == int(get_running_host_id(vg_uuid)):
        sanlock.direct_init_resource("{}:{}:/dev/mapper/{}-lvmlock:{}".format(vglk.lockspace_name, vglk.resource_name, vglk.vg_name, vglk.offset))


def list_pvs(vgUuid, timeout=10):
    r, o = bash.bash_ro("timeout -s SIGKILL %s pvs --noheading --nolocking -t -Svg_name=%s -oname" % (timeout, vgUuid))
    if r != 0:
        return None

    paths = [s.strip() for s in o.splitlines()]
    return filter(bool, paths)

def check_pv_status(vgUuid, timeout):
    r, o, e = bash.bash_roe("timeout -s SIGKILL %s pvs --noheading --nolocking -t -Svg_name=%s -oname,missing" % (timeout, vgUuid))
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
        return False, "primary storage %s attr get error, expect 'wz--ns' got '%s'" % (vgUuid, health)

    if health[0] != "w":
        return False, "primary storage %s permission error, expect 'w', got '%s'" % (vgUuid, health)

    if health[1] != "z":
        return False, "primary storage %s resizeable error, expect 'z', got '%s'" % (vgUuid, health)

    if health[3] != "-":
        return False, "primary storage %s partial error, expect '-', got '%s'" % (vgUuid, health)

    if health[5] != "s":
        return False, "primary storage %s shared mode error, expect 's', got '%s'" % (vgUuid, health)

    return True, ""

@bash.in_bash
def vgck(vgUuid, timeout):
    return bash.bash_roe('timeout -s SIGKILL %s vgck %s 2>&1' % (timeout, vgUuid))

@bash.in_bash
def lvmlockd_log_search(lvmlockd_match_regexp, since, until):
    return bash.bash_r('''journalctl --since '%s' --until '%s' --unit %s | grep -E '%s' ''' % (since, until, get_lvmlockd_service_name(), lvmlockd_match_regexp)) == 0

def lvm_vgck(vgUuid, timeout):
    start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    health, o, e = vgck(vgUuid, 360 if timeout < 360 else timeout)
    end_time = (datetime.datetime.now() + datetime.timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
    check_stuck_vglk_and_gllk()

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
            # fix ZSTAC-61116
            if es.strip().endswith("lock skipped: error -22") and lvmlockd_log_search("S lvm_%s R VGLK res_lock invalid val_blk" % vgUuid,
                                                                                      start_time, end_time):
                fix_vglk(vgUuid)
            elif es.strip().endswith("lock failed: removed"):
            # fix ZSTAC-57545
                fix_vglk(vgUuid)
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
    # type: (str, int, bool) -> tuple[bool, str]
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
    r = bash.bash_r("blockdev --flushbufs %s" % one_active_lv)  # fcntl.ioctl(fd, BLKFLSBUF)
    if r != 0:
        return False
    return True


@bash.in_bash
def get_invalid_pv_uuids(vgUuid, checkIo = False, timeout=10):
    invalid_pv_uuids = []
    pvs_outs = bash.bash_o(
        "timeout -s SIGKILL %s pvs --noheading --nolocking -t -Svg_name=%s -ouuid,name,missing" % (timeout, vgUuid)).strip().splitlines()
    if len(pvs_outs) == 0:
        return invalid_pv_uuids, "vg %s not found" % vgUuid
    for pvs_out in pvs_outs:
        pv_uuid = pvs_out.strip().split(" ")[0]
        if "unknown" in pvs_out:
            invalid_pv_uuids.append(pv_uuid)
        elif "missing" in pvs_out:
            invalid_pv_uuids.append(pv_uuid)
        elif checkIo is True and check_lv_on_pv_valid(vgUuid, pv_uuid) is False:
            invalid_pv_uuids.append(pv_uuid)

    return invalid_pv_uuids, None


@bash.in_bash
def is_volume_on_pvs(volume_path, pvUuids, includingMissing=True):
    # type: (str, list[str], bool) -> bool
    if pvUuids is None:
        logger.warn("pvUuid is None! volume_path:%s" % volume_path)
        return False

    files = linux.qcow2_get_file_chain(volume_path)
    if len(files) == 0 or files is None:
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
            logger.debug("pv of lv %s is missing, return true" % volume_path)
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
    cmd = "lsblk -sr " + vm_root_volume + " -o NAME,TYPE,STATE"
    r, o = bash.bash_ro(cmd)
    if r != 0:
        return True

    dep_devices = form.load(o)
    has_running_disk = any(dep_dev["TYPE"] == "disk" and dep_dev["STATE"] == "running" for dep_dev in dep_devices)
    has_not_running_disk = any(dep_dev["TYPE"] == "disk" and dep_dev["STATE"] != "running" for dep_dev in dep_devices)
    return has_not_running_disk or not has_running_disk

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
        vm.pid = linux.get_vm_pid(vm.uuid)
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
def get_running_vm_root_volume_on_vg(vgUuid):
    # type: (str) -> list[VmStruct]
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
        vm.pid = linux.get_vm_pid(vm.uuid)
        vm.load_from_xml(xml)
        if not vm.root_volume:
            logger.warn("found strange vm[pid: %s, uuid: %s], can not find boot volume" % (vm.pid, vm.uuid))
            continue

        if vm.root_volume.startswith("/dev/" + vgUuid):
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
    for devname in os.listdir("/sys/block/"):
        if "loop" in devname:
            continue
        linux.write_file("/sys/block/%s/queue/unpriv_sgio" % devname, "1")


@bash.in_bash
@linux.retry(times=3, sleep_time=1)
def enable_multipath():
    bash.bash_roe("modprobe dm-multipath")
    bash.bash_roe("modprobe dm-round-robin")
    bash.bash_roe("mpathconf --enable --with_multipathd y")
    bash.bash_roe("systemctl enable multipathd")

    if not is_multipath_running():
        raise RetryException("multipath still not running")

@bash.in_bash
@linux.retry(times=3, sleep_time=1)
def disable_multipath():
    bash.bash_roe("systemctl disable multipathd")
    bash.bash_roe("systemctl stop multipathd")

    if is_multipath_running():
        raise RetryException("multipath is still running")



pv_allocate_strategy = {}  # type:dict


def update_pv_allocate_strategy(cmd):
    global pv_allocate_strategy
    new_strategy = {}
    if cmd.addons and cmd.addons.allocateStrategy:
        new_strategy = cmd.addons.allocateStrategy.__dict__

    if cmd.vgUuid not in new_strategy:
        new_strategy[cmd.vgUuid] = "none"
    pv_allocate_strategy.update(new_strategy)


def get_allocated_pvs(vg_name):
    global pv_allocate_strategy
    try:
        strategy = pv_allocate_strategy[vg_name]
    except KeyError:
        strategy = "none"

    if strategy == "none":
        return []
    elif strategy == "minLvCounts":
        return get_volume_lv_sorted_pvs(vg_name)
    elif strategy == "maxFreeSize":
        return get_free_sorted_pvs(vg_name)
    else:
        return []


@bash.in_bash
def get_lv_location(lv_path):
    r, o = bash.bash_ro('''lvs --nolocking -t --noheadings -o devices %s | awk -F '(' '!pv[$1]++{printf " "$1}' ''' % lv_path)
    if r == 0:
        return o.strip().split()
    return []


def get_lv_affinity_sorted_pvs(lv_path, cmd=None):
    if cmd:
        update_pv_allocate_strategy(cmd)

    vg_name, lv_name = lv_path.split(os.sep)[-2::]
    total_pvs = get_allocated_pvs(vg_name)
    if not total_pvs:
        return None

    locations = get_lv_location(os.path.join("/dev", vg_name, lv_name))
    rest_pvs = filter(lambda p: p not in locations, total_pvs)
    return locations + rest_pvs


@bash.in_bash
def get_volume_lv_sorted_pvs(vg_name):
    cmd = '''pvs --segments --noheadings --nolocking -t \
-S 'vg_name=%s,seg_type!=free,lv_tags!=%s,lv_tags!=""' \
-o pv_name,lv_name -O pv_name,lv_name | uniq | awk '{count[$1]++;} END {for(pv in count) {print pv" "count[pv]}}' \
''' % (vg_name, IMAGE_TAG)

    r, o = bash.bash_ro(cmd)
    all_pvs = list_pvs(vg_name)
    lv_counts = dict(zip(all_pvs, [0] * len(all_pvs)))
    for l in o.strip().splitlines():
        pv_name, lv_count = l.split()
        lv_counts[pv_name] = int(lv_count)

    return sorted(lv_counts.keys(), key=lambda lv: lv_counts[lv] + random.random())


@bash.in_bash
def get_free_sorted_pvs(vg_name):
    r, o = bash.bash_ro("pvs --nolocking -t --noheadings -S 'vg_name=%s' -o pv_name -O-pv_free --rows" % vg_name)
    if r == 0:
        return o.strip().split()
    return []


class LunWwidAndCapacity(object):
    def __init__(self, wwid, total_capacity, available_capacity):
        self.wwid = wwid
        self.totalCapacity = total_capacity
        self.availableCapacity = available_capacity


@bash.in_bash
def get_lun_capacities_from_vg(vg_uuid, vgs_path_and_wwid):
    r, pvs_out, _ = bash.bash_roe("timeout -s SIGKILL 10 pvs --noheading --nolocking -t --nosuffix"
                                  " -S 'vg_name=%s' -o 'pv_name,pv_size,pv_free' --units b" % vg_uuid)
    if r != 0:
        return None

    DEV = 0
    SIZE = 1
    FREE_SIZE = 2
    lun_capacities = []
    for lun_info in pvs_out.strip().splitlines():
        dev_and_size = lun_info.split()
        size = dev_and_size[SIZE]
        free_size = dev_and_size[FREE_SIZE]

        dev = dev_and_size[DEV]
        path = os.path.realpath(dev)
        if (vg_uuid in vgs_path_and_wwid) and (path in vgs_path_and_wwid[vg_uuid]):
            wwid = vgs_path_and_wwid[vg_uuid][path]
            lun_capacities.append(LunWwidAndCapacity(wwid, size, free_size))

    return lun_capacities


class LvmRemoteStorage(remoteStorage.RemoteStorage):
    def __init__(self, volume_install_path, mount_path, volume_mounted_device=None):
        super(LvmRemoteStorage, self).__init__(mount_path, volume_mounted_device)
        self.normalize_install_path = volume_install_path.replace("sharedblock:/", "/dev")

    def do_mount(self, fstype=None):
        try:
            active_lv(self.normalize_install_path)
            if fstype is not None:
                shell.call("mkfs -F -t %s %s" % (fstype, self.normalize_install_path))
            linux.mount(self.normalize_install_path, self.mount_path)
        except Exception as e:
            deactive_lv(self.normalize_install_path)
            raise e
        return self.normalize_install_path

    def mount(self):
        if self.volume_mounted_device is not None:
            cmd = shell.ShellCmd("mountpoint %s" % self.mount_path)
            cmd(is_exception=False)
            if cmd.return_code == 0:
                return self.volume_mounted_device
            if os.path.exists(self.volume_mounted_device):
                linux.mount(self.volume_mounted_device, self.mount_path)
                return self.volume_mounted_device
            else:
                return self.do_mount()

        if not os.path.isdir(self.mount_path):
            linux.mkdir(self.mount_path)

        fstype = get_fs_type(self.mount_path)
        return self.do_mount(fstype)

    def umount(self):
        device_and_mount_path = bash.bash_o("mount | grep %s" % self.mount_path)
        if len(device_and_mount_path) != 0:
            shell.call('umount -f %s' % self.mount_path)
        deactive_lv(self.normalize_install_path)


def report_config_changed():
    shell.run("touch %s" % LVM_CONFIG_CHANGED_FILE)


def subcmd(cmd, timeout=lvm_cmd_timeout_with_locking):
    if cmd in ["lvs", "pvs", "vgs"]:
        return "%s --nolocking -t" % cmd
    elif cmd in ["lvchange", "lvcreate", "lvrename", "lvresize", "lvextend", "lvremove"]:
        return "timeout -s SIGKILL %s %s"% (timeout, cmd)
    return cmd

class LvmlockdStatus(object):
    def __init__(self):
        self.failed = False
        self.ls_status = {}
        self._init()

    '''
    info=ls ls_name=lvm_3ae7fd0635404f048429a0418752a738 vg_name=3ae7fd0635404f048429a0418752a738
    vg_uuid=G5vV72-Yjwy-7VrR-nVyQ-qAfL-EzFl-NKGkuk vg_sysid=. vg_args=1.0.0:lvmlock lm_type=sanlock
    host_id=1 create_fail=0 create_done=1 thread_work=0 thread_stop=0 thread_done=0 kill_vg=0 drop_vg=0 sanlock_gl_enabled=1
    '''
    class LockspaceStatus(object):
        def __init__(self, line):
            ls = {kv.split('=')[0]: kv.split('=')[1] for kv in line.strip().split()}
            self.killed = bool(int(ls.get("kill_vg")))
            self.dropped = bool(int(ls.get("drop_vg")))
            self.vg_name = ls.get("vg_name")

    def _init(self):
        @linux.retry(3, 1)
        def _update():
            r, status_line, e = bash.bash_roe("timeout 10 lvmlockctl -i -d")
            if r != 0:
                raise Exception("dump lvmlockd info failed: retcode %s, error %s" % (r, e))
            for line in filter(lambda l: 'ls_name=lvm_' in l, status_line.splitlines()):
                ls = self.LockspaceStatus(line)
                self.ls_status.update({ls.vg_name: ls})

        try:
            _update()
        except Exception as e:
            logger.warn(str(e))
            self._check()

    def _check(self):
        @linux.retry(3, 1)
        def check_lvmlockd_log():
            # check if lvmlockd can receive the lvm command
            fake_vg = 'fake_vg_%s' % linux.get_current_timestamp()
            start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            vgck(fake_vg, 10)
            end_time = (datetime.datetime.now() + datetime.timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S")
            if not lvmlockd_log_search('vgck', start_time, end_time):
                raise RetryException("lvmlockd socket exceptions!")
        try:
            check_lvmlockd_log()
        except Exception as e:
            logger.warn(str(e))
            self.failed = True


@bash.in_bash
def get_retry_times_for_checking_vg_lockspace():
    _, sanlock_patch_version = bash.bash_ro("sanlock get_patch_version")
    # if version is not a digit, e.g. "client action get_patch_version is unknown", it also means that sanlock patch version < 2
    if sanlock_patch_version.strip().isdigit() is False:
        return 15
    elif int(sanlock_patch_version.strip()) >= 2:
        return 3
    else:
        return 15


def config_lvm(host_id, all_disk_paths, vg_uuid, host_uuid, default_sanlock_lv_size, host_os_type, enable_lvmetad):
    backup_lvm_config()
    config = get_lvm_default_config()
    lvmlockd_lock_retries = 6
    config.modify({
        "use_lvmlockd": 1,
        "host_id": host_id,
        "sanlock_lv_extend": default_sanlock_lv_size,
        "lvmlockd_lock_retries": lvmlockd_lock_retries,
        "issue_discards": 0,
        "reserved_stack": 256,
        "reserved_memory": 131072,
        "use_lvmetad": 1 if enable_lvmetad else 0
    })

    if host_os_type == "debian":
        config.modify({"udev_rules": 0, "udev_sync": 0})
    config.write_to_file(LVM_CONFIG_TMP_FILE)
    config_lvm_filter([os.path.basename(LVM_CONFIG_TMP_FILE)], preserve_disks=all_disk_paths)

    new_config = linux.read_file(LVM_CONFIG_TMP_FILE)
    old_config = linux.read_file(LVM_LOCAL_CONFIG_FILE)
    diff = list(difflib.unified_diff(old_config.splitlines() if old_config is not None else [], new_config.splitlines()))
    if len(diff) == 0:
        logger.debug("lvm config has not changed")
    else:
        linux.write_file(LVM_CONFIG_FILE, new_config, create_if_not_exist=True)
        linux.write_file(LVM_LOCAL_CONFIG_FILE, new_config, create_if_not_exist=True)
        logger.debug("lvm config has changed:\n %s" % '\n'.join(diff))
        report_config_changed()

    # max lock retries times = (external lvmlockd_lock_retries + 1) * (internal lock_retries + 1 after a lock conflict)
    global lvm_cmd_timeout_with_locking
    lvm_cmd_timeout_with_locking = ((lvmlockd_lock_retries + 1) * 6) * 5
    modify_sanlock_config("sh_retries", 20)
    modify_sanlock_config("logfile_priority", 7)
    modify_sanlock_config("renewal_read_extend_sec", 24)
    modify_sanlock_config("debug_renew", 1)
    modify_sanlock_config("use_watchdog", 0)
    modify_sanlock_config("max_sectors_kb", "ignore")
    modify_sanlock_config("watchdog_fire_timeout", 1)
    modify_sanlock_config("kill_grace_seconds", 40)
    modify_sanlock_config("zstack_vglock_timeout", 0)
    modify_sanlock_config("use_zstack_vglock_timeout", 0)
    modify_sanlock_config("zstack_vglock_large_delay", 8)
    modify_sanlock_config("use_zstack_vglock_large_delay", 0)

    sanlock_hostname = "%s-%s-%s" % (vg_uuid[:8], host_uuid[:8], linux.get_hostname()[:20])
    modify_sanlock_config("our_host_name", sanlock_hostname)
    shell.call("sed -i 's/.*rotate .*/rotate 10/g' /etc/logrotate.d/sanlock", exception=False)
    shell.call("sed -i 's/.*size .*/size 20M/g' /etc/logrotate.d/sanlock", exception=False)


def _resolve_vgs_info(o, tag):
    groupDiskInfos = {}

    block_devices = get_block_devices()

    block_devices_by_dev_name = {}
    for bd in block_devices:
        if bd.dev_name:
            block_devices_by_dev_name[bd.dev_name] = bd
        if bd.multipathPath:
            block_devices_by_dev_name[bd.multipathPath] = bd
            try:
                dm_name = os.path.basename(os.path.realpath("/dev/mapper/%s" % bd.multipathPath))
                if dm_name:
                    block_devices_by_dev_name[dm_name] = bd
                    for slave in os.listdir("/sys/class/block/%s/slaves/" % dm_name):
                        if slave and slave.strip():
                            block_devices_by_dev_name[slave.strip()] = bd
            except Exception:
                logger.warn("resolve dm name failed for mpath device %s: %s" %
                            (bd.multipathPath, linux.get_exception_stacktrace()))

    for info in form.load('vg_name pv_count pv_name tags\n' + o):
        vg_name = info['vg_name']
        pv_count = info['pv_count']
        pv_name = info['pv_name']
        tags = info['tags']

        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        if not any(t.startswith(tag) for t in tag_list):
            continue

        pv_basename = os.path.basename(pv_name)
        if vg_name not in groupDiskInfos:
            groupDiskInfos[vg_name] = {"disks": [], "diskCount": int(pv_count)}

        block_device = block_devices_by_dev_name.get(pv_basename)
        if block_device is None:
            # fallback: try resolving via realpath (e.g. /dev/mapper/mpathX -> dm-N)
            try:
                real_name = os.path.basename(os.path.realpath(pv_name))
                block_device = block_devices_by_dev_name.get(real_name)
            except Exception as e:
                logger.warn("resolve realpath failed for pv %s: %s" % (pv_name, str(e)))
        if block_device:
            groupDiskInfos[vg_name]["disks"].append(block_device)
        else:
            logger.warn("PV %s belongs to VG %s but not found in block devices scan" % (pv_basename, vg_name))

    for vg_name, info in groupDiskInfos.items():
        actual_count = len(info["disks"])
        expected_count = info["diskCount"]
        if actual_count < expected_count:
            logger.warn("VG %s has incomplete WWID set: expected %d PVs but resolved %d block devices. "
                        "WWID matching may fail for this VG." % (vg_name, expected_count, actual_count))

    return groupDiskInfos


@bash.in_bash
def get_all_vgs(tag):
    """Full-scan VG view: includes foreign sanlock VGs, bypasses lvm.conf filter."""
    accept_all_config = (
        '--config \'devices/filter=["a|.*|"] devices/global_filter=["a|.*|"]\''
    )
    r, o, e = bash.bash_roe(
        "timeout -s SIGKILL 120 vgs --nolocking --shared --foreign -t %s "
        "-o vg_name,pv_count,pv_name,tags --noheadings" % accept_all_config)
    if r != 0:
        raise Exception("get all vgs failed, error: %s" % e)
    return _resolve_vgs_info(o, tag)


@bash.in_bash
def get_managed_vgs(tag):
    """Host-managed VG view: subject to lvm.conf filter, excludes foreign VGs."""
    r, o, e = bash.bash_roe("timeout -s SIGKILL 120 vgs --nolocking -t -o vg_name,pv_count,pv_name,tags --noheadings")
    if r != 0:
        raise Exception("get managed vgs failed, error: %s" % e)
    return _resolve_vgs_info(o, tag)


@bash.in_bash
def reset_pv_uuids(vg_uuid):
    """Reset all PV UUIDs in the VG to avoid collision with the source platform."""
    r, o, e = bash.bash_roe(
        "timeout -s SIGKILL 30 pvs --noheading --nolocking -t -Svg_name=%s -oname" % vg_uuid)
    if r != 0:
        raise Exception("failed to list PVs for VG %s: stdout=%s, stderr=%s" % (vg_uuid, o, e))
    pv_names = [line.strip() for line in o.strip().splitlines() if line.strip()]
    if not pv_names:
        raise Exception("no PVs found for VG %s while resetting PV UUIDs" % vg_uuid)

    all_pvs = " ".join(pv_names)
    r, _, e = bash.bash_roe("timeout -s SIGKILL %s pvchange --yes --uuid %s" % (lvm_cmd_timeout_with_locking, all_pvs))
    if r != 0:
        raise Exception("failed to reset PV UUIDs for VG %s (pvs: %s): %s" % (vg_uuid, all_pvs, e))

    logger.debug("reset PV UUIDs for VG %s: %s" % (vg_uuid, pv_names))


@bash.in_bash
def rename_vg(old_vg_uuid, new_vg_uuid):
    if old_vg_uuid == new_vg_uuid:
        logger.debug("rename vg skipped: old_vgUuid == new_vgUuid (%s)" % old_vg_uuid)
        return

    if vg_exists(new_vg_uuid) and not vg_exists(old_vg_uuid):
        logger.debug("rename vg skipped: %s already exists and %s not found" % (new_vg_uuid, old_vg_uuid))
        return

    if vg_exists(new_vg_uuid) and vg_exists(old_vg_uuid):
        raise Exception("both old VG %s and new VG %s exist on this host. "
                        "Refusing to rename - manual investigation required." % (old_vg_uuid, new_vg_uuid))

    @linux.retry(times=5, sleep_time=2)
    def do_vg_rename():
        # Guard: rename may have already succeeded in a previous retry
        if vg_exists(new_vg_uuid) and not vg_exists(old_vg_uuid):
            logger.debug("rename vg already completed: %s -> %s" % (old_vg_uuid, new_vg_uuid))
            return

        r, o, e = bash.bash_roe(
            "timeout -s SIGKILL %s vgrename %s %s" %
            (lvm_cmd_timeout_with_locking, old_vg_uuid, new_vg_uuid))
        if r != 0:
            raise Exception("unable to rename vg %s to %s, "
                            "stdout:%s, stderr:%s" % (old_vg_uuid, new_vg_uuid, str(o), str(e)))

        old_exists = vg_exists(old_vg_uuid)
        new_exists = vg_exists(new_vg_uuid)
        if old_exists or not new_exists:
            raise RetryException(
                "unexpected VG state after rename %s -> %s: old_exists=%s, new_exists=%s" % (
                    old_vg_uuid, new_vg_uuid, old_exists, new_exists))

        logger.debug("rename vg %s to %s successfully" % (old_vg_uuid, new_vg_uuid))

    do_vg_rename()

    old_exists = vg_exists(old_vg_uuid)
    new_exists = vg_exists(new_vg_uuid)
    if old_exists or not new_exists:
        raise Exception("vg rename post-check failed: old_exists=%s, new_exists=%s for %s -> %s" %
                        (old_exists, new_exists, old_vg_uuid, new_vg_uuid))


@bash.in_bash
def reset_sanlock_lockspace(vg_uuid, io_timeout):
    lockspace_path = "/dev/mapper/%s-lvmlock" % vg_uuid

    log_vg_lock_diagnostics(vg_uuid, "before reset_sanlock_lockspace")
    fix_vglk(vg_uuid)

    def align_size_to_sanlock_option(align_size):
        align_options = {
            sanlock.SMALL_ALIGN_SIZE: "1M",
            sanlock.SMALL_ALIGN_SIZE * 2: "2M",
            sanlock.SMALL_ALIGN_SIZE * 4: "4M",
            sanlock.BIG_ALIGN_SIZE: "8M",
        }
        if align_size not in align_options:
            raise Exception("unsupported sanlock align size %s for %s" % (align_size, vg_uuid))
        return align_options[align_size]

    def infer_layout_from_lv_leases(leases):
        lease_offsets = sorted(set(offset for _, offset in leases))
        if not lease_offsets:
            raise Exception("no LV lease offsets available")

        big_first_lv_offset = (sanlock.VGLK_BEGIN + 1) * sanlock.BIG_ALIGN_SIZE
        if any(offset < big_first_lv_offset or offset % sanlock.BIG_ALIGN_SIZE != 0
               for offset in lease_offsets):
            return sanlock.SECTOR_SIZE_512, sanlock.SMALL_ALIGN_SIZE
        if lease_offsets[0] == big_first_lv_offset:
            return sanlock.SECTOR_SIZE_4K, sanlock.BIG_ALIGN_SIZE

        raise Exception("ambiguous LV lease offsets: %s" % lease_offsets[:10])

    lv_lock_output = bash.bash_errorout(
        "timeout -s SIGKILL 30 lvs -ouuid,lock_args -Svg_name=%s --noheading --nolocking -t" % vg_uuid)

    lv_leases = []
    for line in lv_lock_output.strip().splitlines():
        xs = line.strip().split()
        if len(xs) < 2 or ":" not in xs[1]:
            logger.warn("reset_sanlock_lockspace: skip unparseable LV lease line: %r" % line)
            continue
        try:
            offset = int(xs[1].split(":")[-1])
        except ValueError:
            logger.warn("reset_sanlock_lockspace: skip LV lease line with unparseable offset: %r" % line)
            continue
        lv_leases.append((xs[0], offset))
    lease_offsets = [offset for _, offset in lv_leases]
    logger.debug("reset_sanlock_lockspace: LV lease count=%s min_offset=%s max_offset=%s sample=%s" %
                 (len(lease_offsets),
                  min(lease_offsets) if lease_offsets else None,
                  max(lease_offsets) if lease_offsets else None,
                  sorted(lease_offsets)[:10]))

    try:
        sector_size = sanlock.get_sector_size(vg_uuid)
        align_size = sanlock.sector_size_to_align_size(sector_size)
    except Exception as e:
        try:
            sector_size, align_size = infer_layout_from_lv_leases(lv_leases)
        except Exception as infer_err:
            raise Exception("failed to detect sanlock layout for %s: %s; "
                            "fallback from LV leases failed: %s" %
                            (vg_uuid, str(e), str(infer_err)))
        logger.warn("reset_sanlock_lockspace: failed to detect sector size from GLLK/VGLK for %s, "
                    "fallback to LV lease offsets with sector_size=%s align_size=%s: %s" %
                    (vg_uuid, sector_size, align_size, str(e)))
    logger.debug("reset_sanlock_lockspace: use sector_size=%s align_size=%s io_timeout=%s" %
                 (sector_size, align_size, io_timeout))

    align_option = align_size_to_sanlock_option(align_size)
    lockspace_init_options = "-Z %s -A %s -o %s" % (sector_size, align_option, io_timeout)
    resource_init_options = "-Z %s -A %s" % (sector_size, align_option)

    # Reinit delta lease area (clears ALL host slots).
    r, o, e = bash.bash_roe(
        "timeout -s SIGKILL 60 sanlock direct init %s -s lvm_%s:0:%s:0" %
        (lockspace_init_options, vg_uuid, lockspace_path))
    if r != 0:
        log_vg_lock_diagnostics(vg_uuid, "after failed sanlock lockspace init", warn=True)
        raise Exception("failed to init sanlock lockspace for %s: stdout=%s, stderr=%s"
                        % (vg_uuid, o, e))

    # Reinit GLLK and VGLK resource leases (clear source platform owner residue).
    gllk_offset = sanlock.GLLK_BEGIN * align_size
    vglk_offset = sanlock.VGLK_BEGIN * align_size

    r, o, e = bash.bash_roe(
        "timeout -s SIGKILL 30 sanlock direct init %s -r lvm_%s:GLLK:%s:%s" %
        (resource_init_options, vg_uuid, lockspace_path, gllk_offset))
    if r != 0:
        log_vg_lock_diagnostics(vg_uuid, "after failed GLLK init", warn=True)
        raise Exception("failed to reinit GLLK for %s: %s" % (vg_uuid, e))
    logger.debug("reset_sanlock_lockspace: reinit GLLK at offset %s" % gllk_offset)

    r, o, e = bash.bash_roe(
        "timeout -s SIGKILL 30 sanlock direct init %s -r lvm_%s:VGLK:%s:%s" %
        (resource_init_options, vg_uuid, lockspace_path, vglk_offset))
    if r != 0:
        log_vg_lock_diagnostics(vg_uuid, "after failed VGLK init", warn=True)
        raise Exception("failed to reinit VGLK for %s: %s" % (vg_uuid, e))
    logger.debug("reset_sanlock_lockspace: reinit VGLK at offset %s" % vglk_offset)

    # Reinit per-LV resource leases.
    failed_lvs = []
    for uuid, offset in lv_leases:
        logger.debug("reset_sanlock_lockspace: reinit LV lease %s offset %s" % (uuid, offset))
        r, _o, e = bash.bash_roe(
            "timeout -s SIGKILL 30 sanlock direct init %s -r lvm_%s:%s:%s:%s" %
            (resource_init_options, vg_uuid, uuid, lockspace_path, offset))
        if r != 0:
            failed_lvs.append(uuid)
            logger.warn("failed to reinit LV lease %s for %s: %s" % (uuid, vg_uuid, e))

    if failed_lvs:
        log_vg_lock_diagnostics(vg_uuid, "after failed LV lease init", warn=True)
        raise Exception("failed to reinit %d LV lease(s) for %s: %s" % (len(failed_lvs), vg_uuid, failed_lvs))


@bash.in_bash
def update_vg_tag(vg_uuid, old_tag_prefix, new_tag):
    """Update VG tag: find existing tag by old_tag_prefix and replace with new_tag."""
    r, o, e = bash.bash_roe("timeout -s SIGKILL 30 vgs --nolocking -t -o tags --noheadings %s" % vg_uuid)
    if r != 0:
        raise Exception("failed to get VG tags for %s: %s" % (vg_uuid, e))

    old_tags = [t.strip() for t in o.strip().split(",")
                if t.strip().startswith(old_tag_prefix)]

    # Add new tag first - ensures VG always has at least one matchable tag,
    # even if the subsequent deltag fails. This makes retry safe: get_managed_vgs(tag=INIT_TAG)
    # can always find the VG.
    bash.bash_errorout("timeout -s SIGKILL %s vgchange --addtag %s %s" % (lvm_cmd_timeout_with_locking, linux.shellquote(new_tag), vg_uuid))

    # Remove all old tags (may be >1 if a previous attempt partially succeeded)
    for old_tag in old_tags:
        r, o, e = bash.bash_roe("timeout -s SIGKILL %s vgchange --deltag %s %s" % (lvm_cmd_timeout_with_locking, linux.shellquote(old_tag), vg_uuid))
        if r != 0:
            logger.warn("failed to remove old tag %s from VG %s: %s (non-fatal, new tag already set)"
                        % (old_tag, vg_uuid, e))
    if old_tags:
        logger.debug("updated VG tag for %s: %s -> %s" % (vg_uuid, old_tags, new_tag))
    else:
        logger.warn("no tag with prefix [%s] found on VG %s, added new tag directly" % (old_tag_prefix, vg_uuid))

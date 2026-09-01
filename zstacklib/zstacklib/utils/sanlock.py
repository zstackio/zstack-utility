import os.path
import re
import random
import struct
import time
import traceback
from string import whitespace

from zstacklib.utils import log, sizeunit
from zstacklib.utils import linux
from zstacklib.utils import thread
from zstacklib.utils import jsonobject
from zstacklib.utils import bash
from zstacklib.utils import lock
from zstacklib.utils import shell
from zstacklib.utils.linux import ignoreerror

GLLK_BEGIN = 65
VGLK_BEGIN = 66
SMALL_ALIGN_SIZE = 1*1024**2
SECTOR_SIZE_512 = 512
SECTOR_SIZE_4K = 8*512
BIG_ALIGN_SIZE = 8*1024**2
EIO = -5
SANLK_AIO_TIMEOUT = -202
LEASE_CORRUPTED_ERR = (-222, -223, -224, -225, -226, -227, -229, -214)

def io_failed(rv):
    return rv == EIO or rv == SANLK_AIO_TIMEOUT

sector_size_cache = {}

logger = log.get_logger(__name__)

def is_lease_corrupted(retcode: int):
    return retcode in LEASE_CORRUPTED_ERR

class SanlockHostStatus(object):
    def __init__(self, record):
        lines = record.strip().splitlines()
        hid, s, ts = lines[0].split()
        if s != 'timestamp':
            raise Exception('unexpected sanlock host status: ' + record)
        self.host_id = int(hid)
        self.timestamp = int(ts)

        for line in lines[1:]:
            try:
                k, v = line.strip().split('=', 2)
                if k == 'io_timeout': self.io_timeout = int(v)
                elif k == 'last_check': self.last_check = int(v)
                elif k == 'last_live': self.last_live = int(v)
                elif k == 'owner_name': self.owner_name = v
            except ValueError:
                logger.warn("unexpected sanlock status: %s" % line)

        if not all([self.io_timeout, self.last_check, self.last_live]):
            raise Exception('unexpected sanlock host status: ' + record)

    def get_timestamp(self):
        return self.timestamp

    def get_io_timeout(self):
        return self.io_timeout

    def get_last_check(self):
        return self.last_check

    def get_last_live(self):
        return self.last_live

    def get_owner_name(self):
        return self.owner_name


class SanlockHostStatusParser(object):
    def __init__(self, status):
        self.status = status

    def is_timed_out(self, hostId):
        r = self.get_record(hostId)
        if r is None:
            return None

        return r.get_timestamp() == 0 or r.get_last_check() - r.get_last_live() > 10 * r.get_io_timeout()

    def is_alive(self, hostId):
        r = self.get_record(hostId)
        if r is None:
            return None

        return r.get_timestamp() != 0 and r.get_last_check() - r.get_last_live() < 2 * r.get_io_timeout()

    def get_record(self, hostId):
        m = re.search(r"^%d\b" % hostId, self.status, re.M)
        if not m:
            return None

        substr = self.status[m.end():]
        m = re.search(r"^\d+\b", substr, re.M)
        remainder = substr if not m else substr[:m.start()]
        return SanlockHostStatus(str(hostId) + remainder)


class SanlockClientStatus(object):
    def __init__(self, status_lines):
        self.lockspace = status_lines[0].split()[1]
        self.is_adding = ':0 ADD' in status_lines[0]

        for line in status_lines[1:]:
            try:
                k, v = line.strip().split('=', 2)
                if k == 'renewal_last_result': self.renewal_last_result = int(v)
                elif k == 'renewal_last_attempt': self.renewal_last_attempt = int(v)
                elif k == 'renewal_last_success': self.renewal_last_success = int(v)
                elif k == 'io_timeout': self.io_timeout = int(v)
                elif k == 'space_dead': self.space_dead = int(v)
            except ValueError:
                logger.warn("unexpected sanlock client status: %s" % line)

    def get_lockspace(self):
        return self.lockspace

    def get_renewal_last_result(self):
        return self.renewal_last_result

    def get_renewal_last_attempt(self):
        return self.renewal_last_attempt

    def get_renewal_last_success(self):
        return self.renewal_last_success

    def get_io_timeout(self):
        return self.io_timeout

    def is_space_dead(self):
        return bool(self.space_dead)


class SanlockClientStatusParser(object):
    def __init__(self):
        self.status = self._init()
        self.lockspace_records = None  # type: list[SanlockClientStatus]

    def get_lockspace_records(self):
        if self.lockspace_records is None:
            self.lockspace_records = self._do_get_lockspace_records()
        return self.lockspace_records

    def get_lockspace_record(self, needle):
        for r in self.get_lockspace_records():
            if needle in r.get_lockspace():
                return r
        return None

    def _init(self):
        @linux.retry(3, 1)
        def _get():
            return bash.bash_errorout("timeout 10 sanlock client status -D")
        try:
            return _get()
        except:
            return ""

    def _do_get_lockspace_records(self):
        records = []
        current_lines = []

        for line in self.status.splitlines():
            if len(line) == 0:
                continue

            if line[0] in whitespace and len(current_lines) > 0:
                current_lines.append(line)
                continue

            # found new records - check whether to complete last record.
            if len(current_lines) > 0:
                records.append(SanlockClientStatus(current_lines))
                current_lines = []

            if line.startswith("s "):
                current_lines.append(line)

        if len(current_lines) > 0:
            records.append(SanlockClientStatus(current_lines))

        return records

    def get_config(self, config_key):
        for line in self.status.splitlines():
            if config_key in line:
                return line.strip().split("=")[-1]


@bash.in_bash
def direct_init_resource(resource, vg_name):
    sector_size = get_sector_size(vg_name)
    align_size = sector_size_to_align_size(sector_size)
    cmd = "sanlock direct init -r %s" % resource
    cmd += " -A %sM -Z %s" % (sizeunit.Byte.toMegaByte(align_size), sector_size)
    return bash.bash_r(cmd)


def check_stuck_vglk_and_gllk():
    # 1. clear the vglk/gllk held by the dead host
    # 2. check stuck vglk/gllk
    locks = get_vglks() + get_gllks()
    logger.debug("start checking all vgs[%s] to see if the VGLK/GLLK on disk is normal" % [v.vg_name for v in locks])

    abnormal_lcks = [v for v in locks if v.abnormal_held()]
    if len(abnormal_lcks) == 0:
        logger.debug("no abnormal vglk or gllk found")
        return

    logger.debug("found possible dirty vglk/gllk on disk: %s" % [v.vg_name for v in abnormal_lcks])
    results = {}
    def check_stuck_lock():
        @thread.AsyncThread
        def check(lck):
            results.update({lck.vg_name: lck.stuck()})
        for lck in abnormal_lcks:
            check(lck)

    def wait(_):
        return len(results) == len(abnormal_lcks)

    check_stuck_lock()
    linux.wait_callback_success(wait, timeout=60, interval=3)
    for lck in [v for v in abnormal_lcks if results.get(v.vg_name) is True]:
        lck.refresh()
        if not lck.abnormal_held():
            continue

        if lck.host_id not in lck.owners:
            live_min_host_id = get_hosts_state(lck.lockspace_name).get_live_min_hostid()
            if int(lck.host_id) != live_min_host_id:
                logger.debug("find dirty %s on vg %s, init it directly by host[hostId:%s] with min hostId" % (lck.resource_name, lck.vg_name, live_min_host_id))
                continue

        logger.debug("find dirty %s on vg %s, init it directly" % (lck.resource_name, lck.vg_name))
        direct_init_resource("{}:{}:/dev/mapper/{}-lvmlock:{}".format(lck.lockspace_name, lck.resource_name, lck.vg_name, lck.offset),
                             lck.vg_name)


def read_lockspace_metadata_from_backup(vg_uuid):
    from zstacklib.utils.lvm import LVM_LOCKSPACE_BACKUP_PATH

    bk_file = os.path.join(LVM_LOCKSPACE_BACKUP_PATH, "lvmlockd_info_{}".format(vg_uuid))
    meta_backup = linux.read_file(bk_file)
    if not meta_backup:
        return {}

    result = {}
    try:
        for line in meta_backup.strip().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('host_id '):
                result['host_id'] = int(line.split()[1])
            elif line.startswith('generation '):
                result['generation'] = int(line.split()[1])
            elif line.startswith('sector_size '):
                result['sector_size'] = int(line.split()[1])
            elif line.startswith('align_size '):
                result['align_size'] = int(line.split()[1])
    except Exception:
        content = traceback.format_exc()
        logger.warn(content)
        logger.warn(meta_backup)

    return result


class Resource(object):
    def __init__(self, lines, host_id=None, align_size=SMALL_ALIGN_SIZE):
        self.host_id = host_id
        self.align_size = align_size
        self.owners = []
        self.shared = None
        self._update(lines)

    def _update(self, lines):
        self.owners = []
        self.shared = None
        for line in lines.strip().splitlines():
            line = line.strip()
            if ' lvm_' in line:
                self.offset, self.lockspace_name, self.resource_name, self.timestamp, own, self.gen = line.split()[:6]
                if len(line.split()) == 7:
                    self.lver = line.split()[6]
                self.vg_name = self.lockspace_name.strip("lvm_")
                if self.timestamp.strip("0") != '':
                    self.owners.append(str(int(own)))
            elif ' SH' in line:
                self.shared = True
                self.owners.append(str(int(line.split()[0])))

    @property
    def lock_type(self):
        if self.shared:
            return 'sh'
        elif len(self.owners) == 1:
            return 'ex'
        else:
            return 'un'

    def refresh(self):
        r, o, e = direct_dump_resource("/dev/mapper/%s-lvmlock" % self.vg_name, self.offset, size=self.align_size)
        self._update(o)

    def in_use(self):
        return bash.bash_r("sanlock client status | grep %s:%s | grep -v 'ADD' " % (self.lockspace_name, self.resource_name)) == 0

    # the current host holds the resource lock, but the process holding the lock cannot be found or held by a dead host
    def abnormal_held(self):
        if self.lock_type == 'un':
            return False
        # held by us
        if self.host_id in self.owners:
            return not self.in_use()
        # held by dead host with ex mode
        if self.lock_type != 'ex':
            return False
        host_state = get_hosts_state(self.lockspace_name)
        if host_state is not None and host_state.is_host_dead(self.owners[0]):
            return True

        return False

    def stuck(self):
        if not self.abnormal_held():
            return False

        ori_lver = self.lver
        ori_lock_type = self.lock_type
        ori_time = linux.get_current_timestamp()
        # the purpose of retrying is to repeatedly confirm that the lock on the resource has generated dirty data
        # because the results of 'sanlock client status' and 'sanlock direct dump' may not necessarily be at the same time
        @linux.retry(12, sleep_time=random.uniform(3, 4))
        def _stuck():
            self.refresh()
            if not self.abnormal_held() or self.lock_type != ori_lock_type:
                return
            elif self.lock_type == 'ex' and self.lver == ori_lver:
                raise RetryException("resource %s held by us, lock type: ex" % self.resource_name)
            elif self.lock_type == 'sh':
                raise RetryException("resource %s held by us, lock type: sh" % self.resource_name)

        try:
            _stuck()
        except RetryException as e:
            logger.warn(str(e) + (" over %s seconds" % (linux.get_current_timestamp() - ori_time)))
            return True
        except Exception as e:
            raise e

        return False


'''
s lvm_8e97627ab5ea4b0e8cb9f42c8345d728:7:/dev/mapper/8e97627ab5ea4b0e8cb9f42c8345d728-lvmlock:0 
h 7 gen 3 timestamp 3654034 LIVE
h 52 gen 2 timestamp 1815547 DEAD
h 58 gen 3 timestamp 1104848 DEAD
h 67 gen 5 timestamp 1824156 DEAD
h 100 gen 4 timestamp 1207551 LIVE
s lvm_675a67fb03b54acf9daac0a7ae966b74:70:/dev/mapper/675a67fb03b54acf9daac0a7ae966b74-lvmlock:0 
h 70 gen 2 timestamp 3654038 LIVE
h 100 gen 1 timestamp 1207549 LIVE
'''
class HostsState(object):
    def __init__(self, lines, lockspace_name):
        self.lockspace_name = lockspace_name
        self.hosts = {}
        self.host_timestamp = {}
        self._update(lines)

    def _update(self, lines):
        self.hosts = {}
        find_lockspace = False
        for line in lines.strip().splitlines():
            if line.strip().startswith('s %s' % self.lockspace_name):
                find_lockspace = True
            elif line.strip().startswith('h ') and find_lockspace:
                host_id = line.split()[1]
                host_state = line.split()[-1]
                timestamp = line.split()[-2]
                self.hosts.update({host_id: host_state})
                self.host_timestamp.update({host_id: timestamp})
            elif find_lockspace and line.strip().startswith('s lvm_'):
                break
        logger.debug("get hosts state[%s] on lockspace %s" % (self.hosts, self.lockspace_name))

    def is_host_live(self, host_id):
        return self.hosts.get(str(host_id)) == "LIVE"

    def is_host_dead(self, host_id):
        return self.hosts.get(str(host_id)) == "DEAD"

    def get_timestamp(self, host_id):
        return self.host_timestamp.get(str(host_id))
    
    def get_live_min_hostid(self):
        ids = [int(id) for id in list(self.hosts.keys()) if self.is_host_live(id)]
        if len(ids) == 0:
            return None
        return min(ids)


def get_hosts_state(lockspace_name):
    r, o, e = bash.bash_roe("sanlock client gets -h 1")
    if r == 0 and lockspace_name in o:
        return HostsState(o, lockspace_name)


def get_host_status(lockspace_name, host_id):
    status = shell.call("timeout 30 sanlock client host_status -s %s -D" % lockspace_name)
    return SanlockHostStatusParser(status).get_record(host_id)


@linux.retry(5, 0.5)
def get_running_host_id(vg_uuid):
    cmd = shell.ShellCmd("sanlock client gets | awk -F':' '/%s/{ print $2 }'" % vg_uuid)
    cmd(is_exception=False)
    if cmd.stdout.strip() == "":
        raise Exception("can not get running host id for vg %s" % vg_uuid)
    return cmd.stdout.strip()


def check_host_liveness(vg_uuid, dst_host_id, dst_host_uuid=None):
    DEAD = "dead"
    LIVE = "live"

    def get_host_status_from_sanlock():
        host_status = get_hosts_state("lvm_" + vg_uuid)
        if not host_status or str(dst_host_id) not in host_status.hosts:
            raise Exception("cannot get host status from sanlock client")
        ts = host_status.get_timestamp(dst_host_id)
        return (DEAD if host_status.is_host_dead(dst_host_id) else LIVE), ts

    check_interval = 10
    count = 0
    our_host_id = int(get_running_host_id(vg_uuid))
    parser = SanlockHostStatusParser(shell.call("timeout 30 sanlock client host_status -s lvm_%s -D" % vg_uuid))
    dst_host_io_timeout = parser.get_record(dst_host_id).get_io_timeout()
    our_host_io_timeout = parser.get_record(our_host_id).get_io_timeout()
    max_check_count = (calc_host_dead_seconds(dst_host_io_timeout) + 2 * our_host_io_timeout) // check_interval + 1
    host_info = "hostId:%s" % dst_host_id
    if dst_host_uuid:
        host_info = "hostUuid:%s, %s" % (dst_host_uuid, host_info)
    logger.debug("host[%s] sanlock io timeout is %s, current host io timeout is %s" %
                 (host_info, dst_host_io_timeout, our_host_io_timeout))
    latest_timestamp = None
    timestamp_change_count = 0
    while count < max_check_count:
        if latest_timestamp is not None:
            time.sleep(check_interval)

        status, current_timestamp = get_host_status_from_sanlock()
        logger.info("read sanlock current heartbeat: %s, latest heartbeat: %s on sanlock" % (current_timestamp, latest_timestamp))
        if status == DEAD:
            logger.debug("sanlock host lease on vg %s has expired for host[%s]" % (vg_uuid, host_info))
            return False
        elif latest_timestamp is None:
            latest_timestamp = current_timestamp
        elif latest_timestamp != current_timestamp:
            timestamp_change_count += 1
            latest_timestamp = current_timestamp
            if timestamp_change_count > 1:
                break
        else:
            count += 1

    logger.debug("host[%s] is still alive judged by sanlock" % host_info)
    return True


def get_host_name(lockspace_name, host_id):
    bash.bash_r("sanlock client host_status -D ")


@bash.in_bash
def direct_dump(path, offset, length):
    return bash.bash_roe("sanlock direct dump %s:%s:%s" % (path, offset, length))


@bash.in_bash
def direct_dump_resource(path, offset, size=SMALL_ALIGN_SIZE):
    return bash.bash_roe("sanlock direct dump %s:%s:%s" % (path, offset, size))


VAL_BLK_VERSION = 0x0101
VBF_REMOVED = 0x0001

'''
Check if lvb block version and flag are valid, see also daemons/lvmlockd/lvmlockd-core.c.
We hope to detect this error without actually locking VG.
jira: ZSTAC-61116/ZSTAC-57545
'''
def is_vglk_lvb_invalid(lvb, vg_name):
    data = struct.pack('<Q', lvb)
    version, flags, r_version = struct.unpack('<HHI', data[:8])

    def _vglk_failed():
        o = bash.bash_o("vgck {} 2>&1".format(vg_name))
        return re.search(r'VG {} lock (skipped|failed)'.format(vg_name), o) is not None

    return ((version != 0 and (version & 0xFF00) > (VAL_BLK_VERSION & 0xFF00)) or
            (version != 0 and r_version != 0 and (flags & VBF_REMOVED))) and _vglk_failed()


@ignoreerror
def repair_vglk_metadata(vg_name):
    if not os.path.exists("/dev/mapper/{}-lvmlock".format(vg_name)):
        return

    with lock.NonBlockNamedLock("check-vglk-{}-lease".format(vg_name)) as lck:
        if not lck.acquired:
            return
        sector_size = get_sector_size(vg_name)
        align_size = sector_size_to_align_size(sector_size)
        offset = VGLK_BEGIN * align_size
        align_size_MB = sizeunit.Byte.toMegaByte(align_size)
        cmd = "sanlock direct read -r lvm_{0}:{1}:/dev/mapper/{0}-lvmlock:{2} -A {3}M -Z {4} 2>&1".format(vg_name,
                                                                                                          "VGLK", offset,
                                                                                                          align_size_MB,
                                                                                                          sector_size)
        o = bash.bash_o(cmd)
        for line in o.strip().splitlines():
            line = line.strip()
            if line.startswith("read done "):
                read_rv = int(line.split()[-1])
                if is_lease_corrupted(read_rv):
                    logger.debug("vglk lease corrupted, cmd {}, err:\n{}, reinit it.".format(cmd, o))
                    if "sanlock lease needs repair" in bash.bash_o("vgck {} --lockopt repairvg 2>&1".format(vg_name)):
                        direct_init_resource("lvm_{0}:VGLK:/dev/mapper/{0}-lvmlock:{1}".format(vg_name, offset), vg_name)
                    break

            if line.startswith("lvb "):
                lvb = int(line.split()[-1], 16)
                if is_vglk_lvb_invalid(lvb, vg_name):
                    logger.debug("vglk lvb invalid, cmd {}, err:\n{}, reinit it.".format(cmd, o))
                    direct_init_resource("lvm_{0}:VGLK:/dev/mapper/{0}-lvmlock:{1}".format(vg_name, offset), vg_name)
                    break


def parse_lockspace(lockspace):
    vg_uuid = lockspace.split(":")[0].replace("lvm_", "", 1)
    host_id = lockspace.split(":")[1]
    path = lockspace.split(":")[2]
    return vg_uuid, host_id, path

def get_vglks():
    result = []
    for lockspace in get_lockspaces():
        vg_uuid, host_id, path = parse_lockspace(lockspace)
        align_size = sector_size_to_align_size(get_sector_size(vg_uuid))
        r, o, e = direct_dump_resource(path, VGLK_BEGIN * align_size)
        if ' VGLK ' in o:
            result.append(Resource(o, host_id, align_size=align_size))
    return result


def get_vglk(vg_uuid):
    lockspace = get_lockspace(vg_uuid)
    if lockspace is None:
        return None

    vg_uuid, host_id, path = parse_lockspace(lockspace)
    align_size = sector_size_to_align_size(get_sector_size(vg_uuid))
    r, o, e = direct_dump_resource(path, VGLK_BEGIN * align_size)
    if ' VGLK ' in o:
        return Resource(o, host_id, align_size=align_size)
    return None


def get_gllks():
    result = []
    for lockspace in get_lockspaces():
        vg_uuid, host_id, path = parse_lockspace(lockspace)
        align_size = sector_size_to_align_size(get_sector_size(vg_uuid))
        r, o, e = direct_dump_resource(path, GLLK_BEGIN * align_size)
        if ' GLLK ' in o:
            result.append(Resource(o, host_id, align_size=align_size))
    return result


def get_lockspaces():
    result = []
    r, o, e = bash.bash_roe("sanlock client gets")
    if r != 0 or o.strip() == '':
        return result
    return [line.split()[1].strip() for line in o.strip().splitlines() if 's lvm_' in line]


def get_lockspace(vg_uuid):
    r, o, e = bash.bash_roe("sanlock client gets | grep %s" % vg_uuid)
    if r == 0:
        return o.split()[1].strip()
    return None


def get_lockspace_sector_size(vg_uuid):
    dev_path = "/dev/mapper/%s-lvmlock" % vg_uuid
    try:
        physical_block_size = linux.get_dev_physical_sector_size(dev_path)
    except Exception:
        physical_block_size = 0
    try:
        logical_block_size = linux.get_dev_logical_sector_size(dev_path)
    except Exception:
        logical_block_size = 0

    if physical_block_size not in (SECTOR_SIZE_512, SECTOR_SIZE_4K):
        physical_block_size = 0
    if logical_block_size not in (SECTOR_SIZE_512, SECTOR_SIZE_4K):
        logical_block_size = 0
    if not physical_block_size and not logical_block_size:
        raise Exception("cannot get block size for lockspace device %s" % dev_path)
    if physical_block_size == SECTOR_SIZE_4K or logical_block_size == SECTOR_SIZE_4K:
        return SECTOR_SIZE_4K
    return SECTOR_SIZE_512


def get_sector_size(vg_uuid):
    if vg_uuid in sector_size_cache:
        return sector_size_cache.get(vg_uuid)

    backup = read_lockspace_metadata_from_backup(vg_uuid)
    sector_size = backup.get("sector_size")
    if sector_size in (SECTOR_SIZE_512, SECTOR_SIZE_4K):
        sector_size_cache[vg_uuid] = sector_size
        logger.debug("read sector size[{}] from lvm lockspace info for vg {}".format(sector_size, vg_uuid))
        return sector_size

    sector_size = get_lockspace_sector_size(vg_uuid)
    if sector_size in (SECTOR_SIZE_512, SECTOR_SIZE_4K):
        sector_size_cache[vg_uuid] = sector_size
        logger.debug("read sector size[{0}] from lockspace for vg {1}".format(sector_size, vg_uuid))
        return sector_size

    raise Exception("sector size[{}] is invalid".format(sector_size))

def sector_size_to_align_size(sector_size):
    if sector_size == SECTOR_SIZE_512:
        return SMALL_ALIGN_SIZE
    elif sector_size == SECTOR_SIZE_4K:
        return BIG_ALIGN_SIZE
    raise Exception("invalid sector size %s" % sector_size)


class RetryException(Exception):
    pass

def calc_id_renewal_fail_seconds(io_timeout):
    return 8 * int(io_timeout)


def calc_host_dead_seconds(io_timeout):
    return calc_id_renewal_fail_seconds(io_timeout) + get_watchdog_fire_timeout()

@bash.in_bash
def get_watchdog_fire_timeout():
    r, o = bash.bash_ro("sanlock client status -D | grep watchdog_fire_timeout")
    if r == 0:
        return int(o.strip().split("=")[1])
    return 60

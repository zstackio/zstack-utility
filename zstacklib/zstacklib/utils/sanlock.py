from zstacklib.utils import log, linux, thread

import re
import random
from string import whitespace
from zstacklib.utils import bash

GLLK_BEGIN = 65
VGLK_BEGIN = 66
SMALL_ALIGN_SIZE = 1*1024**2
SECTOR_SIZE_512 = 512
SECTOR_SIZE_4K = 8*512
BIG_ALIGN_SIZE = 8*1024**2


logger = log.get_logger(__name__)

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


class SanlockClientStatusParser(object):
    def __init__(self, status):
        self.status = status
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

@bash.in_bash
def direct_init_resource(resource):
    cmd = "sanlock direct init -r %s" % resource
    return bash.bash_r(cmd)


def check_stuck_vglk_and_gllk():
    # 1. clear the vglk/gllk held by the dead host
    # 2. check stuck vglk/gllk
    locks = get_vglks() + get_gllks()
    logger.debug("start checking all vgs[%s] to see if the VGLK/GLLK on disk is normal" % map(lambda v: v.vg_name, locks))

    abnormal_lcks = filter(lambda v: v.abnormal_held(), locks)
    if len(abnormal_lcks) == 0:
        logger.debug("no abnormal vglk or gllk found")
        return

    logger.debug("found possible dirty vglk/gllk on disk: %s" % map(lambda v: v.vg_name, abnormal_lcks))
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
    for lck in filter(lambda v: results.get(v.vg_name) is True, abnormal_lcks):
        lck.refresh()
        if not lck.abnormal_held():
            continue

        if lck.host_id not in lck.owners:
            live_min_host_id = get_hosts_state(lck.lockspace_name).get_live_min_hostid()
            if int(lck.host_id) != live_min_host_id:
                logger.debug("find dirty %s on vg %s, init it directly by host[hostId:%s] with min hostId" % (lck.resource_name, lck.vg_name, live_min_host_id))
                continue

        logger.debug("find dirty %s on vg %s, init it directly" % (lck.resource_name, lck.vg_name))
        direct_init_resource("{}:{}:/dev/mapper/{}-lvmlock:{}".format(lck.lockspace_name, lck.resource_name, lck.vg_name, lck.offset))


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
        self._update(lines)

    def _update(self, lines):
        self.hosts = {}
        find_lockspace = False
        for line in lines.strip().splitlines():
            if line.strip().startswith('s %s' % self.lockspace_name):
                find_lockspace = True
            elif line.strip().startswith('h ') and find_lockspace:
                host_id = line.split()[1]
                host_state = line.split()[6]
                self.hosts.update({host_id: host_state})
            elif find_lockspace and line.strip().startswith('s lvm_'):
                break
        logger.debug("get hosts state[%s] on lockspace %s" % (self.hosts, self.lockspace_name))

    def is_host_live(self, host_id):
        return self.hosts.get(host_id) == "LIVE"

    def is_host_dead(self, host_id):
        return self.hosts.get(host_id) == "DEAD"
    
    def get_live_min_hostid(self):
        ids = [int(id) for id in self.hosts.keys() if self.is_host_live(id)]
        if len(ids) == 0:
            return None
        return min(ids)


def get_hosts_state(lockspace_name):
    r, o, e = bash.bash_roe("sanlock client gets -h 1")
    if r == 0 and lockspace_name in o:
        return HostsState(o, lockspace_name)


@bash.in_bash
def direct_dump(path, offset, length):
    return bash.bash_roe("sanlock direct dump %s:%s:%s" % (path, offset, length))


@bash.in_bash
def direct_dump_resource(path, offset, size=SMALL_ALIGN_SIZE):
    return bash.bash_roe("sanlock direct dump %s:%s:%s" % (path, offset, size))

@bash.in_bash
def vertify_delta_lease(vg_uuid, host_id):
    return bash.bash_r("sanlock client read -s lvm_%s:%s:/dev/mapper/%s-lvmlock:0" % (vg_uuid, host_id, vg_uuid))

@bash.in_bash
def vertify_paxos_lease(vg_uuid, resource_name, offset):
    return bash.bash_r("sanlock client read -r lvm_%s:%s:/dev/mapper/%s-lvmlock:%s" % (vg_uuid, resource_name, vg_uuid, offset))

def get_vglks():
    result = []
    for lockspace in get_lockspaces():
        path = lockspace.split(":")[2]
        host_id = lockspace.split(":")[1]
        r, o, e = direct_dump_resource(path, VGLK_BEGIN * SMALL_ALIGN_SIZE)
        if ' VGLK ' in o:
            result.append(Resource(o, host_id))
            continue
        # vglk may be stored at 66M or 528M
        r, o, e = direct_dump_resource(path, VGLK_BEGIN * BIG_ALIGN_SIZE, size=BIG_ALIGN_SIZE)
        if ' VGLK ' in o:
            result.append(Resource(o, host_id, align_size=BIG_ALIGN_SIZE))
    return result


def get_vglk(vg_uuid):
    lockspace = get_lockspace(vg_uuid)
    if lockspace is None:
        return None

    path = lockspace.split(":")[2]
    host_id = lockspace.split(":")[1]
    r, o, e = direct_dump_resource(path, VGLK_BEGIN * SMALL_ALIGN_SIZE)
    if ' VGLK ' in o:
        return Resource(o, host_id)
    # vglk may be stored at 66M or 528M
    r, o, e = direct_dump_resource(path, VGLK_BEGIN * BIG_ALIGN_SIZE, size=BIG_ALIGN_SIZE)
    if ' VGLK ' in o:
        return Resource(o, host_id, align_size=BIG_ALIGN_SIZE)
    return None


def get_gllks():
    result = []
    for lockspace in get_lockspaces():
        path = lockspace.split(":")[2]
        host_id = lockspace.split(":")[1]
        r, o, e = direct_dump_resource(path, GLLK_BEGIN * SMALL_ALIGN_SIZE)
        if ' GLLK ' in o:
            result.append(Resource(o, host_id))
            continue
        elif '_GLLK_disabled' in o:
            continue
        # gllk may be stored at 65M or 520M
        r, o, e = direct_dump_resource(path, GLLK_BEGIN * BIG_ALIGN_SIZE, size=BIG_ALIGN_SIZE)
        if ' GLLK ' in o:
            result.append(Resource(o, host_id, align_size=BIG_ALIGN_SIZE))
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

@bash.in_bash
def check_delta_lease(vg_uuid, host_id):
    r = vertify_delta_lease(vg_uuid, host_id)
    if r == 0:
        return False
    sector_size = get_sector_size(vg_uuid)
    seek = int(host_id) - 1
    bash.bash_r("dd if=/dev/mapper/{0}-lvmlock bs={1} count=1 skip=1999 iflag=direct | "
                "dd of=/dev/mapper/{0}-lvmlock bs={1} seek={2} count=1 oflag=direct".format(vg_uuid, sector_size, seek))
    return True

def check_vglk_paxos_lease(vg_uuid):
    sector_size = get_sector_size(vg_uuid)
    return vertify_paxos_lease(vg_uuid, "VGLK", VGLK_BEGIN * sector_size_to_align_size(sector_size)) == 0


def dd_check_lockspace(path):
    return bash.bash_r("dd if=%s of=/dev/null bs=1M count=1 iflag=direct" % path)


def get_sector_size(vg_uuid):
    r = bash.bash_r("dd if=/dev/mapper/%s-lvmlock bs=%s count=2 skip=%s | grep -E 'VGLK|GLLK'" % (vg_uuid, SMALL_ALIGN_SIZE, GLLK_BEGIN))
    if r == 0:
        return SECTOR_SIZE_512
    r = bash.bash_r("dd if=/dev/mapper/%s-lvmlock bs=%s count=2 skip=%s | grep -E 'VGLK|GLLK'" % (vg_uuid, BIG_ALIGN_SIZE, GLLK_BEGIN))
    if r == 0:
        return SECTOR_SIZE_4K
    raise Exception("unable to find sector size")

def sector_size_to_align_size(sector_size):
    if sector_size == SECTOR_SIZE_512:
        return SMALL_ALIGN_SIZE
    elif sector_size == SECTOR_SIZE_4K:
        return BIG_ALIGN_SIZE
    raise Exception("invalid sector size %s" % sector_size)


class RetryException(Exception):
    pass
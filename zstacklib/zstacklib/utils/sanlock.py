from zstacklib.utils import bash
from zstacklib.utils import log
from zstacklib.utils import linux
from string import whitespace

import re

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
def dd_check_lockspace(path):
    return bash.bash_r("dd if=%s of=/dev/null bs=1M count=1 iflag=direct" % path)

@bash.in_bash
def vertify_delta_lease(vg_uuid, host_id):
    r, o = bash.bash_ro("sanlock direct read_leader -s lvm_%s:%s:/dev/mapper/%s-lvmlock:0" % (vg_uuid, host_id, vg_uuid))
    if r != 0:
        raise Exception("detected sanlock metadata corruption at offset %s length 512 on /dev/mapper/%s-lvmlock, the "
                        "content read is:\n%s\nWe suspect that there has been a storage malfunction!" % (int(host_id)*512-512, vg_uuid, o))


@bash.in_bash
def vertify_paxos_lease(vg_uuid, resource_name, offset):
    return bash.bash_roe("sanlock client read -r lvm_%s:%s:/dev/mapper/%s-lvmlock:%s" % (vg_uuid, resource_name, vg_uuid, offset))
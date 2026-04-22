import hashlib
import os
import threading
import time
import traceback

from kvmagent.plugins.nvram import nvram_common
from kvmagent.plugins.vms import tpm
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import thread

# Periodically monitor VM host files (TPM state / NvRam) for changes.
#
# After a VM starts, the data plane registers the files that need watching.
# A background thread polls every 5 seconds: for each monitored VM it checks
# whether the VM is still active (dead VMs are removed from the watch list),
# then computes an MD5 checksum of each tracked file and compares it with the
# previously recorded value.  When a change is detected, an event is reported
# to the management node (KVM_REPORT_VM_HOST_FILE_CHANGED) so that the
# control plane can record the change and optimise subsequent sync workflows.

logger = log.get_logger(__name__)

KVM_REPORT_VM_HOST_FILE_CHANGED = '/kvm/reporthostfilechanged'

# Number of consecutive scan misses before removing a VM from the watch list.
MISS_COUNT_THRESHOLD = 10


def _file_md5(path):
    # type: (str) -> str | None
    """Return hex md5 digest of *path*, or None if file does not exist."""
    if not os.path.isfile(path):
        return None
    md5 = hashlib.md5()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


class VmHostFileChangedCmd(object):
    def __init__(self):
        self.hostUuid = None   # type: str
        self.vmUuid = None     # type: str
        self.types = None      # type: list


class _VmHostFileMonitorEntry(object):
    def __init__(self, vm_uuid, host_uuid, types):
        self.vm_uuid = vm_uuid      # type: str
        self.host_uuid = host_uuid  # type: str
        self.types = types          # type: list[str]
        # md5 cache: {file_path: last_md5_hex_or_None}
        self.md5_cache = {}         # type: dict
        # consecutive number of scans in which this VM was not active
        self.miss_count = 0         # type: int


class _VmHostFileChangeEntry(object):
    def __init__(self, type, path, current_md5):
        self.type = type                 # type: str
        self.path = path                 # type: str
        self.current_md5 = current_md5   # type: str


class VmHostFileMonitor(object):
    def __init__(self):
        self._lock = threading.Lock()
        self._report_semaphore = threading.Semaphore(5)
        self._entries = {}           # type: dict[str, _VmHostFileMonitorEntry]
        self._get_active_vms_func = None
        self._send_command_url = None
        self._started = False

    def register_get_active_vms(self, func):
        """Register the function that returns a list of active Vm objects."""
        self._get_active_vms_func = func

    def add_monitor(self, vm_uuid, host_uuid, types, report_url=None):
        # type: (str, str, list, str) -> None
        """Add or update a monitoring entry for *vm_uuid*."""
        if report_url:
            self._send_command_url = report_url
        with self._lock:
            self._entries[vm_uuid] = _VmHostFileMonitorEntry(vm_uuid, host_uuid, types)
        logger.debug('vm host file monitor: added vm[uuid:%s] types=%s' % (vm_uuid, types))

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True

        @thread.AsyncThread
        def _loop():
            while True:
                try:
                    self._check_once()
                except Exception:
                    logger.warn('vm host file monitor error: %s' % traceback.format_exc())
                time.sleep(5)

        _loop()
        logger.debug('vm host file monitor started')

    def _get_active_vm_uuids(self):
        # type: () -> set | None
        if self._get_active_vms_func is None:
            return None
        try:
            vms = self._get_active_vms_func()
            return set(vm.uuid for vm in vms)
        except Exception:
            logger.warn('vm host file monitor: failed to get active vms: %s' % traceback.format_exc())
            return None

    def _check_once(self):
        active_uuids = self._get_active_vm_uuids()
        if active_uuids is None:
            return

        with self._lock:
            entries_snapshot = dict(self._entries)

        # Track consecutive misses; only remove after MISS_COUNT_THRESHOLD
        evict_uuids = []
        for uid, entry in entries_snapshot.items():
            if uid not in active_uuids:
                entry.miss_count += 1
                if entry.miss_count >= MISS_COUNT_THRESHOLD:
                    evict_uuids.append(uid)
                elif entry.miss_count == 1: # only logger in first time
                    logger.debug('vm host file monitor: vm[uuid:%s] not active, still wait for %d scanning.' % (uid, MISS_COUNT_THRESHOLD))
            else:
                # VM is active again - reset the counter
                if entry.miss_count > 0:
                    logger.debug('vm host file monitor: vm[uuid:%s] active again' % (uid))
                    entry.miss_count = 0

        if evict_uuids:
            with self._lock:
                for uid in evict_uuids:
                    if self._entries.get(uid) is entries_snapshot.get(uid):
                        self._entries.pop(uid, None)
            for uid in evict_uuids:
                logger.debug('vm host file monitor: vm[uuid:%s] not active for %d consecutive scans, '
                             'removed from monitoring' % (uid, MISS_COUNT_THRESHOLD))
                entries_snapshot.pop(uid, None)

        # check surviving entries
        for vm_uuid, entry in entries_snapshot.items():
            changed_entries = self._detect_changes(entry)
            if changed_entries:
                self._report_change(entry, changed_entries)

    def _update_md5_cache(self, vm_uuid, entries):
        # type: (str, list[_VmHostFileChangeEntry]) -> None
        with self._lock:
            entry = self._entries.get(vm_uuid)
            if not entry:
                return
            for change_entry in entries:
                entry.md5_cache[change_entry.path] = change_entry.current_md5

    def _resolve_path(self, vm_uuid, file_type):
        # type: (str, str) -> str | None
        if file_type == 'NvRam':
            return nvram_common.build_nvram_vm_host_file_path(vm_uuid)
        elif file_type == 'TpmState':
            return tpm.build_tpm_permall_path(vm_uuid)
        return None

    def _detect_changes(self, entry):
        # type: (_VmHostFileMonitorEntry) -> list[_VmHostFileChangeEntry]
        changed = []
        for t in entry.types:
            path = self._resolve_path(entry.vm_uuid, t)
            if path is None:
                continue
            try:
                current_md5 = _file_md5(path)
            except Exception:
                logger.warn('vm host file monitor: failed to compute md5 for %s: %s'
                            % (path, traceback.format_exc()))
                continue

            if path not in entry.md5_cache:
                # first time: record baseline, do not report
                self._update_md5_cache(entry.vm_uuid, [_VmHostFileChangeEntry(t, path, current_md5)])
                continue

            prev_md5 = entry.md5_cache[path]
            if current_md5 != prev_md5:
                changed.append(_VmHostFileChangeEntry(t, path, current_md5))
                logger.debug('vm host file monitor: detected change for vm[uuid:%s] type=%s path=%s'
                             % (entry.vm_uuid, t, path))
        return changed

    def _report_change(self, entry, changed_entries):
        # type: (_VmHostFileMonitorEntry, list[_VmHostFileChangeEntry]) -> None
        url = self._send_command_url
        if not url:
            logger.warn('vm host file monitor: no report url, cannot report change for vm[uuid:%s]' % entry.vm_uuid)
            return

        @thread.AsyncThread
        def _do_report():
            if not self._report_semaphore.acquire(blocking=False):
                logger.debug('too many reporting threads, report in next scanning')
                return

            try:
                cmd = VmHostFileChangedCmd()
                cmd.hostUuid = entry.host_uuid
                cmd.vmUuid = entry.vm_uuid
                cmd.types = [e.type for e in changed_entries]
                logger.debug('vm host file monitor: reporting change for vm[uuid:%s] types=%s to %s'
                            % (entry.vm_uuid, cmd.types, url))
                http.json_dump_post(url, cmd, {'commandpath': KVM_REPORT_VM_HOST_FILE_CHANGED})
                self._update_md5_cache(entry.vm_uuid, changed_entries)
            finally:
                self._report_semaphore.release()

        _do_report()


_monitor = VmHostFileMonitor()


def register_get_active_vms(func):
    """Register the function (from vm_plugin) that returns active Vm list."""
    _monitor.register_get_active_vms(func)


def add_monitor(vm_uuid, host_uuid, types, report_url=None):
    # type: (str, str, list, str) -> None
    _monitor.add_monitor(vm_uuid, host_uuid, types, report_url)


def start_monitor():
    _monitor.start()

"""The Host's swap disk for the disk-swap memory reclaim backend.

One local NVMe disk or partition is the Host's only swap. It is prepared once
(mkswap with a label, swapon with discard). The Agent verifies hardware identity
and swap signature before restoring it. Disks are vetted by the writeback backend probe;
this module adds the swap rules and keeps a record of the disk it prepared in
the Agent's operation directory.
"""

import json
import logging
import os
import re

from kvmagent.plugins.memory_writeback_backends import probe_writeback_backends, _run_command

logger = logging.getLogger(__name__)

SWAP_LABEL = 'zstack-swap'
FSTAB = '/etc/fstab'
FSTAB_MARK = '# zstack memory swap disk'
# What swapoff must leave free after taking the swapped data back.
SWAPOFF_MARGIN_BYTES = 2 << 30
NVME_DEVICE = re.compile(r'^/dev/nvme\d+n\d+(p\d+)?\Z')
SIGNATURE_REASON = 'EXISTING_FILESYSTEM_OR_PARTITION_SIGNATURE'
# A command that rewrites or reads back a whole disk may take minutes.
LONG_COMMAND_SECONDS = 3600


def _nvme_disk(device):
    return re.sub(r'^(/dev/nvme\d+n\d+)p\d+\Z', r'\1', str(device or ''))


def _same_disk(first, second):
    """Whether two NVMe devices are the same disk or a disk and one of its partitions."""
    return bool(first and second) and _nvme_disk(first) == _nvme_disk(second)


class Rejected(Exception):
    def __init__(self, reason, details=None):
        Exception.__init__(self, reason)
        self.reason = reason
        self.details = details


class _LocalFiles(object):
    def read(self, path):
        with open(path, 'r') as stream:
            return stream.read()

    def write(self, path, text):
        temporary = '%s.tmp-%d' % (path, os.getpid())
        with open(temporary, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if os.path.exists(path):
            os.chmod(temporary, os.stat(path).st_mode & 0o7777)
        os.rename(temporary, path)

    def write_kernel(self, path, value):
        # procfs/sysfs attributes cannot be replaced by renaming a temporary file.
        with open(path, 'w') as stream:
            stream.write(value + '\n')

    def remove(self, path):
        try:
            os.remove(path)
        except OSError as exc:
            if exc.errno != 2:
                raise

    def listdir(self, path):
        return os.listdir(path)

    def realpath(self, path):
        if not os.path.exists(path):
            raise OSError(2, 'missing', path)
        return os.path.realpath(path)


class SwapDisks(object):
    def __init__(self, host_uuid, record_path, runner=None, filesystem=None, probe=None, writeback_device=None):
        self.host_uuid = host_uuid
        # The ZRAM writeback disk in the service configuration, kept for ZRAM even while it is drained.
        self.writeback_device = writeback_device
        self.record_path = record_path
        self.run = runner or _run_command
        self.files = filesystem or _LocalFiles()
        self.probe = probe or (lambda host_uuid: probe_writeback_backends(host_uuid))

    # ------------------------------------------------------------ observation

    def inventory(self):
        record = self._record()
        swaps = self._swaps()
        probe = self.probe(self.host_uuid) or {}
        disk = self._observe(record, swaps, probe) if record else None
        backing = self._zram_backing_devices()
        candidates = [self._candidate(item, disk, backing) for item in probe.get('candidates') or []
                      if isinstance(item, dict) and item.get('type') == 'block']
        reasons = []
        if record:
            reasons.append('SWAP_DISK_ALREADY_CONFIGURED')
        others = sorted(device for device in swaps if not (disk and device == disk.get('device')))
        if others:
            reasons.append('OTHER_SWAP_ACTIVE')
        if not record and not any(c['state'] in ('AVAILABLE', 'NEEDS_OVERWRITE_CONFIRMATION') for c in candidates):
            reasons.append('NO_ELIGIBLE_SWAP_DISK_CANDIDATE')
        if not record:
            status = 'NOT_CONFIGURED'
        else:
            status = 'ACTIVE' if not disk['reasons'] else 'FAULT'
        return {'hostUuid': self.host_uuid, 'status': status, 'swapDisk': disk, 'otherSwaps': others,
                'candidates': candidates, 'probeStatus': probe.get('status'), 'probeReasons': probe.get('reasons') or [],
                'canPrepare': not reasons, 'preparationReasons': reasons}

    def _candidate(self, item, disk, backing):
        stable = item.get('stableIdentity') or {}
        device = str(item.get('device') or '')
        reasons = [r for r in item.get('reasons') or [] if r != 'NEEDS_OFFLINE_PREPARATION']
        if not NVME_DEVICE.match(device):
            reasons.append('NOT_LOCAL_NVME_DEVICE')
        # zram claims its writeback disk without a sysfs holder, so the probe cannot see that use.
        if any(_same_disk(device, other) for other in backing):
            reasons.append('ZRAM_WRITEBACK_BACKEND')
        if self.writeback_device and _same_disk(device, self.writeback_device):
            reasons.append('WRITEBACK_BACKEND_CONFIGURED')
        if disk and item.get('device') == disk.get('device'):
            state, reasons = ('ACTIVE' if not disk['reasons'] else 'FAULT'), list(disk['reasons'])
        elif not reasons:
            state = 'AVAILABLE'
        elif reasons == [SIGNATURE_REASON]:
            state = 'NEEDS_OVERWRITE_CONFIRMATION'
        else:
            state = 'INELIGIBLE'
        return {'id': item.get('identity'), 'device': item.get('device'), 'byIdPath': item.get('byIdPath') or '',
                'capacityBytes': item.get('capacityBytes'), 'serial': stable.get('serial') or '',
                'wwn': stable.get('wwn') or '', 'state': state, 'reasons': sorted(set(reasons))}

    def current(self):
        record = self._record()
        return self._observe(record, self._swaps()) if record else None

    def _observe(self, record, swaps, probe=None):
        """Where the recorded disk is now and whether it is the enabled swap with our signature."""
        disk = dict((key, record.get(key)) for key in ('device', 'byIdPath', 'serial', 'wwn', 'capacityBytes', 'uuid', 'stage'))
        disk['reasons'] = []
        if record.get('stage') != 'ACTIVE':
            disk['reasons'].append('SWAP_DISK_PREPARATION_INCOMPLETE')
        try:
            device = self.files.realpath(record.get('byIdPath') or record.get('device'))
        except (IOError, OSError):
            disk['reasons'].append('SWAP_DISK_NOT_FOUND')
            return disk
        disk['device'] = device
        if record.get('uuid') and self._signature(device) != record['uuid']:
            disk['reasons'].append('SWAP_DISK_SIGNATURE_MISMATCH')
        else:
            if probe is None:
                probe = self.probe(self.host_uuid) or {}
            candidate = self._matching_candidate(record, device, probe)
            if candidate is None:
                disk['reasons'].append('SWAP_DISK_IDENTITY_MISMATCH')
        if any(other != device for other in swaps):
            disk['reasons'].append('OTHER_SWAP_ACTIVE')
        if device in swaps:
            disk['usedBytes'] = swaps[device]
        elif not disk['reasons']:
            disk['reasons'].append('SWAP_DISK_NOT_ENABLED')
        disk['reasons'] = sorted(set(disk['reasons']))
        return disk

    def _zram_backing_devices(self):
        devices = []
        for name in self.files.listdir('/sys/block'):
            if not name.startswith('zram'):
                continue
            try:
                value = self.files.read('/sys/block/%s/backing_dev' % name).strip()
            except (IOError, OSError):
                continue
            if value and value != 'none':
                devices.append(value)
        return devices

    def _swaps(self):
        """Enabled swap devices (resolved) with the bytes swapped out to each."""
        swaps = {}
        for line in self.files.read('/proc/swaps').splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4:
                continue
            try:
                device = self.files.realpath(fields[0])
            except (IOError, OSError):
                device = fields[0]
            swaps[device] = int(fields[3]) * 1024
        return swaps

    def _signature(self, device):
        result = self.run(['blkid', '-p', '-s', 'UUID', '-o', 'value', device], timeout=10)
        return (result.get('stdout') or '').strip() if result.get('returncode') == 0 else ''

    # ------------------------------------------------------------ changes

    def prepare(self, candidate_id, overwrite):
        inventory = self.inventory()
        if 'SWAP_DISK_ALREADY_CONFIGURED' in inventory['preparationReasons']:
            raise Rejected('SWAP_DISK_ALREADY_CONFIGURED')
        if inventory['otherSwaps']:
            # ZRAM (or any other swap) is drained before the disk becomes the Host's only swap.
            raise Rejected('OTHER_SWAP_ACTIVE', {'devices': inventory['otherSwaps']})
        chosen = next((c for c in inventory['candidates'] if c['id'] == candidate_id), None)
        if chosen is None:
            raise Rejected('SWAP_DISK_CANDIDATE_NOT_FOUND')
        if chosen['state'] == 'NEEDS_OVERWRITE_CONFIRMATION' and overwrite is not True:
            raise Rejected('OVERWRITE_CONFIRMATION_REQUIRED')
        if chosen['state'] not in ('AVAILABLE', 'NEEDS_OVERWRITE_CONFIRMATION'):
            raise Rejected('SWAP_DISK_CANDIDATE_NOT_ELIGIBLE', {'reasons': chosen['reasons']})
        device = chosen['byIdPath']
        record = {'stage': 'PREPARING', 'device': chosen['device'], 'byIdPath': chosen['byIdPath'], 'serial': chosen['serial'],
                  'wwn': chosen['wwn'], 'capacityBytes': chosen['capacityBytes'], 'uuid': None, 'originalTuning': {}}
        # Recorded before the disk changes: an interrupted preparation is a fault that disable cleans up.
        self._save(record)
        if chosen['state'] == 'NEEDS_OVERWRITE_CONFIRMATION':
            self._must(['wipefs', '-a', device])
        self._must(['mkswap', '-L', SWAP_LABEL, device])
        record['uuid'] = self._signature(device)
        if not record['uuid']:
            raise Rejected('SWAP_SIGNATURE_UNREADABLE')
        self._save(record)
        self._set_boot_entry(record['uuid'])
        self._must(['swapon', '--discard', device])
        record['stage'] = 'ACTIVE'
        self._save(record)
        self._tune(record, chosen['device'])
        return self.inventory()

    def disable(self):
        record = self._record()
        if not record:
            return self.inventory()
        swaps = self._swaps()
        disk = self._observe(record, swaps)
        device = disk.get('device')
        if not record.get('uuid'):
            raise Rejected('SWAP_DISK_PREPARATION_INCOMPLETE')
        if 'SWAP_DISK_NOT_FOUND' in disk['reasons']:
            raise Rejected('SWAP_DISK_NOT_FOUND')
        if 'SWAP_DISK_IDENTITY_MISMATCH' in disk['reasons']:
            raise Rejected('SWAP_DISK_IDENTITY_MISMATCH')
        if device in swaps:
            if 'SWAP_DISK_SIGNATURE_MISMATCH' in disk['reasons']:
                raise Rejected('SWAP_DISK_SIGNATURE_MISMATCH')
            available = self._mem_available()
            required = swaps[device] + SWAPOFF_MARGIN_BYTES
            if available < required:
                raise Rejected('INSUFFICIENT_MEMORY_FOR_SWAPOFF', {
                    'swappedBytes': swaps[device], 'availableBytes': available, 'requiredBytes': required})
            self._must(['swapoff', record['byIdPath']], LONG_COMMAND_SECONDS)
        path = record.get('byIdPath')
        signature = self._signature(path)
        if not signature:
            raise Rejected('SWAP_SIGNATURE_UNREADABLE')
        if signature == record['uuid']:
            if not self._matching_candidate(record, self.files.realpath(path), self.probe(self.host_uuid) or {}):
                raise Rejected('SWAP_DISK_IDENTITY_MISMATCH')
        if record.get('originalTuning'):
            # A helper may have replaced the inactive signature. Only restore host settings in that case.
            self._tune(record, device if signature == record['uuid'] else None, restoring=True)
        if signature == record['uuid']:
            self._must(['wipefs', '-a', '-t', 'swap', path])
        self._set_boot_entry(None)
        self.files.remove(self.record_path)
        return self.inventory()

    @staticmethod
    def _matching_candidate(record, device, probe):
        for item in probe.get('candidates') or []:
            if (item.get('type') != 'block' or item.get('device') != device
                    or 'SERIAL_IDENTITY_NOT_UNIQUE' in (item.get('reasons') or [])):
                continue
            stable = item.get('stableIdentity') or {}
            if (record.get('byIdPath') and record['byIdPath'] == item.get('byIdPath')
                    and record.get('serial') and record['serial'] == stable.get('serial')
                    and (not record.get('wwn') or record['wwn'] == stable.get('wwn'))):
                return item
        return None

    def restore(self):
        """Only a disk we finished preparing can be re-enabled after boot."""
        record = self._record()
        if not record:
            return False
        uuid = record.get('uuid')
        if uuid:
            # Also migrate an earlier managed fstab entry before the next boot.
            self._set_boot_entry(uuid)
        if not uuid or record.get('stage') != 'ACTIVE':
            raise Rejected('SWAP_DISK_PREPARATION_INCOMPLETE')
        swaps = self._swaps()
        probe = self.probe(self.host_uuid) or {}
        disk = self._observe(record, swaps, probe)
        if disk['reasons'] not in ([], ['SWAP_DISK_NOT_ENABLED']):
            raise Rejected(disk['reasons'][0])
        device = disk['device']
        path = record.get('byIdPath')
        candidate = self._matching_candidate(record, device, probe)
        if device not in swaps:
            checked = self._candidate(candidate, None, self._zram_backing_devices())
            if checked['state'] not in ('AVAILABLE', 'NEEDS_OVERWRITE_CONFIRMATION'):
                raise Rejected('SWAP_DISK_CANDIDATE_NOT_ELIGIBLE', {'reasons': checked['reasons']})
            if self._signature(path) != uuid:
                raise Rejected('SWAP_DISK_SIGNATURE_MISMATCH')
            self._must(['swapon', '--discard', path])
        # Older Agent versions prepared disks without taking ownership of host tuning.
        if 'originalTuning' in record:
            self._tune(record, device)
        return True

    def _tune(self, record, device, restoring=False):
        original = record.get('originalTuning', {})
        knobs = [('watermark_scale_factor', '/proc/sys/vm/watermark_scale_factor', '200')]
        if restoring:
            minimum = original.get('min_free_kbytes')
        else:
            # The validated guide specifies 1/2/3 GiB at 64/128/256 GB; leave smaller hosts alone.
            try:
                total = next((int(line.split()[1]) * 1024 for line in self.files.read('/proc/meminfo').splitlines()
                              if line.startswith('MemTotal:')), 0)
            except (IOError, OSError, ValueError, IndexError) as exc:
                logger.warning('Cannot determine swap memory reserve: %s', exc)
                total = 0
            minimum = next((str(size << 20) for gb, size in ((256, 3), (128, 2), (64, 1))
                            if total >= gb * 10 ** 9), None)
        if minimum:
            knobs.append(('min_free_kbytes', '/proc/sys/vm/min_free_kbytes', minimum))
        if device and NVME_DEVICE.match(device):
            queue = '/sys/block/%s/queue/' % os.path.basename(_nvme_disk(device))
            knobs.extend([('scheduler', queue + 'scheduler', 'mq-deadline'),
                          ('nr_requests', queue + 'nr_requests', '64')])

        def current(name, path):
            value = self.files.read(path).strip()
            if name == 'scheduler':
                for token in value.split():
                    if token.startswith('[') and token.endswith(']'):
                        return token[1:-1]
                if value == 'none':
                    return value
                raise ValueError('invalid scheduler: %s' % value)
            return str(int(value))

        # Capture queue depth before switching scheduler, which can reset it.
        if not restoring:
            saved = dict(original)
            for name, path, _ in knobs:
                if name not in saved:
                    try:
                        saved[name] = current(name, path)
                    except (IOError, OSError, ValueError) as exc:
                        logger.warning('Cannot read swap tuning %s: %s', path, exc)
            if saved != original:
                record['originalTuning'] = saved
                try:
                    self._save(record)
                except (IOError, OSError) as exc:
                    logger.warning('Cannot save original swap tuning: %s', exc)
                    return
                original = saved
        for name, path, target in knobs:
            if name not in original or (name == 'scheduler' and 'nr_requests' not in original):
                continue
            try:
                actual = current(name, path)
                if restoring:
                    target = original[name]
                elif name in ('watermark_scale_factor', 'min_free_kbytes'):
                    target = str(max(int(original[name]), int(actual), int(target)))
                if actual != target:
                    self.files.write_kernel(path, target)
                    if current(name, path) != target:
                        raise ValueError('expected %s after write' % target)
            except (IOError, OSError, ValueError) as exc:
                if restoring:
                    # Keep the signature and original values so disable can be retried.
                    raise Rejected('SWAP_DISK_COMMAND_FAILED', {'command': path, 'stderr': str(exc)})
                logger.warning('Cannot apply swap tuning %s: %s', path, exc)

    def _set_boot_entry(self, uuid):
        """Keep exactly one marked fstab line, for this signature; None removes it."""
        original = self.files.read(FSTAB)
        lines = [line for line in original.splitlines() if not line.rstrip().endswith(FSTAB_MARK)]
        if uuid:
            lines.append('UUID=%s none swap noauto,discard,nofail 0 0 %s' % (uuid, FSTAB_MARK))
        updated = '\n'.join(lines) + '\n'
        if original != updated:
            self.files.write(FSTAB, updated)

    def _mem_available(self):
        for line in self.files.read('/proc/meminfo').splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) * 1024
        raise Rejected('MEMORY_AVAILABILITY_UNKNOWN')

    def _must(self, argv, timeout=60):
        result = self.run(argv, timeout=timeout)
        if result.get('returncode') != 0:
            raise Rejected('SWAP_DISK_COMMAND_FAILED', {'command': argv[0], 'stderr': (result.get('stderr') or '')[-500:]})

    def _record(self):
        try:
            record = json.loads(self.files.read(self.record_path))
        except (IOError, OSError) as exc:
            if exc.errno == 2:
                return None
            raise
        except ValueError:
            raise Rejected('SWAP_DISK_RECORD_INVALID')
        if not isinstance(record, dict) or not record:
            raise Rejected('SWAP_DISK_RECORD_INVALID')
        return record

    def _save(self, record):
        self.files.write(self.record_path, json.dumps(record, sort_keys=True))

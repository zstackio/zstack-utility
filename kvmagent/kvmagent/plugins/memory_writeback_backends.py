"""Read-only discovery for memory writeback backend resources.

This module intentionally defines no KvmAgent subclass. The caller passes the
already-read service backend/configuration snapshots; this helper never starts
another service client and never claims, formats, mounts, or writes a device.
"""

import calendar
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import time


DISCOVERY_MAX_AGE_SECONDS = 90
LSBLK_COLUMNS = ('NAME,KNAME,TYPE,SIZE,PKNAME,MAJ:MIN,MODEL,SERIAL,WWN,TRAN,RO,RM')
SUPPORTED_LOCAL_TRANSPORTS = ('virtio', 'sata', 'ata', 'sas', 'scsi', 'nvme', '')
SHARED_TRANSPORTS = ('iscsi', 'fc', 'fibre', 'fibrechannel', 'mpath',
                     'nvmeof', 'nvme-o-f', 'nvme-fc', 'nvme-tcp', 'nvme-rdma',
                     'tcp', 'rdma')
LAYERED_TYPES = ('crypt', 'lvm', 'mpath', 'raid', 'raid0', 'raid1', 'raid10', 'raid5', 'raid6')


class _LocalFilesystem(object):
    def read(self, path):
        with open(path, 'r') as stream:
            return stream.read()

    def exists(self, path):
        return os.path.exists(path)

    def listdir(self, path):
        return os.listdir(path)

    def realpath(self, path):
        return os.path.realpath(path)

    def stat(self, path):
        return os.stat(path)

    def lstat(self, path):
        return os.lstat(path)


def _run_command(argv, timeout=5):
    try:
        output = subprocess.check_output(argv, stderr=subprocess.STDOUT,
                                         universal_newlines=True, timeout=timeout)
        return {'returncode': 0, 'stdout': output, 'stderr': ''}
    except subprocess.CalledProcessError as exc:
        output = exc.output or ''
        if not isinstance(output, str):
            output = output.decode('utf-8', 'replace')
        return {'returncode': exc.returncode, 'stdout': output, 'stderr': output}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'returncode': 127, 'stdout': '', 'stderr': str(exc)}


def _command(runner, argv, timeout=5):
    result = runner(argv, timeout=timeout)
    if isinstance(result, dict):
        return {'returncode': result.get('returncode', 0),
                'stdout': result.get('stdout', ''), 'stderr': result.get('stderr', '')}
    if isinstance(result, tuple) and len(result) == 3:
        return {'returncode': result[0], 'stdout': result[1], 'stderr': result[2]}
    raise ValueError('PROBE_RUNNER_RESULT_INVALID')


def _decode_mount_field(value):
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), value)


def _rows_from_lsblk(document):
    parsed = json.loads(document)
    devices = parsed.get('blockdevices')
    if not isinstance(devices, list):
        raise ValueError('LSBLK_OUTPUT_INVALID')
    rows = []

    def visit(row, parent=None):
        if not isinstance(row, dict):
            raise ValueError('LSBLK_OUTPUT_INVALID')
        item = dict((str(key).lower(), value) for key, value in row.items())
        item['name'] = item.get('name')
        item['kname'] = item.get('kname') or os.path.basename(str(item.get('name') or ''))
        item['pkname'] = item.get('pkname') or parent
        item['children'] = item.get('children') or []
        try:
            item['size'] = int(item.get('size') or 0)
        except (TypeError, ValueError):
            item['size'] = 0
        item['major_minor'] = str(item.get('maj:min') or '')
        rows.append(item)
        for child in item['children']:
            visit(child, item['kname'])

    for device in devices:
        visit(device)
    return rows


def _identity_value(identity, *names):
    if not isinstance(identity, dict):
        return None
    for name in names:
        if name in identity:
            return identity[name]
        aliases = {
            'device': ('canonical_device',),
            'sys_inode': ('sysfs_inode',),
            'boot_id': ('BootID',),
        }
        for alias in aliases.get(name, ()):
            if alias in identity:
                return identity[alias]
        pascal = ''.join(part[:1].upper() + part[1:] for part in name.split('_'))
        if pascal in identity:
            return identity[pascal]
    return None


def _parse_observed_at(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    match = re.match(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$', value)
    if not match:
        return None
    try:
        result = calendar.timegm(time.strptime(match.group(1), '%Y-%m-%dT%H:%M:%S'))
        if match.group(2):
            result += float('0.' + match.group(2))
        zone = match.group(3)
        if zone != 'Z':
            offset = int(zone[1:3]) * 3600 + int(zone[4:6]) * 60
            result += -offset if zone[0] == '+' else offset
        return result
    except (ValueError, OverflowError):
        return None


def _now_epoch(now):
    if now is None:
        return time.time()
    if isinstance(now, datetime.datetime):
        return calendar.timegm(now.utctimetuple()) + now.microsecond / 1000000.0
    return float(now)


def _fresh_observation(value, now):
    observed = _parse_observed_at(value)
    if observed is None:
        return False
    age = _now_epoch(now) - observed
    return -5 <= age <= DISCOVERY_MAX_AGE_SECONDS


def _service_resource(service_backend):
    if not isinstance(service_backend, dict):
        return {}, {}, None
    resource = service_backend.get('backend_resource')
    if not isinstance(resource, dict):
        resource = service_backend
    effective = service_backend.get('effective') or {}
    identity = effective.get('identity') if isinstance(effective, dict) else None
    return resource, identity if isinstance(identity, dict) else {}, effective


def _service_config(service_config):
    if not isinstance(service_config, dict):
        return {}
    for key in ('configured', 'backend', 'desired'):
        value = service_config.get(key)
        if isinstance(value, dict):
            service_config = value
            break
    return service_config


def _read_optional(fs, path):
    try:
        return fs.read(path)
    except (IOError, OSError):
        return None


def _major_minor_for_stat(value):
    try:
        return '%d:%d' % (os.major(value.st_rdev), os.minor(value.st_rdev))
    except (AttributeError, ValueError):
        return ''


def _mount_and_swap_devices(fs, rows, runner):
    """Return device ids protected by mount/swap use, or None if unverifiable."""
    mountinfo = _read_optional(fs, '/proc/self/mountinfo')
    swaps = _read_optional(fs, '/proc/swaps')
    if mountinfo is None or swaps is None:
        return None
    by_dev = dict((row['major_minor'], row) for row in rows if row['major_minor'])
    by_path = {}
    for row in rows:
        for path in (row.get('name'), '/dev/' + str(row.get('kname') or '')):
            if path:
                by_path[path] = row
        try:
            by_path[fs.realpath(row.get('name'))] = row
        except (IOError, OSError, TypeError):
            pass

    protected = set()

    def mark_tree(row):
        current = row
        seen = set()
        while current and current.get('kname') not in seen:
            seen.add(current.get('kname'))
            protected.add(current.get('kname'))
            current = next((candidate for candidate in rows
                            if candidate.get('kname') == current.get('pkname')), None)

        def mark_children(parent):
            for child in parent.get('children') or []:
                child_name = child.get('kname') or os.path.basename(str(child.get('name') or ''))
                protected.add(child_name)
                mark_children(child)
        mark_children(row)

    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) > 4:
            row = by_dev.get(fields[2])
            if row is not None:
                mark_tree(row)
    for line in swaps.splitlines()[1:]:
        fields = line.split()
        if not fields:
            continue
        source = fields[0]
        try:
            source = fs.realpath(source)
        except (IOError, OSError):
            pass
        row = by_path.get(source) or by_path.get(fields[0])
        if row is not None:
            mark_tree(row)

    # Some storage stacks only expose a mounted DM node. lsblk's tree includes
    # its dependencies; marking descendants keeps the leaf disk unavailable.
    return protected


def _by_id_links(fs, rows):
    links = {}
    try:
        names = fs.listdir('/dev/disk/by-id')
    except (IOError, OSError):
        return None
    for name in names:
        path = '/dev/disk/by-id/' + name
        try:
            target = fs.realpath(path)
        except (IOError, OSError):
            continue
        links.setdefault(target, []).append(path)
    for paths in links.values():
        paths.sort()
    return links


def _sysfs_path(fs, major_minor):
    if not major_minor:
        return None
    try:
        return fs.realpath('/sys/dev/block/' + major_minor)
    except (IOError, OSError):
        return None


def _sysfs_entries(fs, path):
    try:
        return fs.listdir(path)
    except (IOError, OSError):
        return None


def _nvme_controller_transport(fs, sys_path):
    """Read the kernel's transport classification for an NVMe controller."""
    match = re.search(r'(?:^|/)(nvme\d+)(?:/|$)', str(sys_path or ''))
    if not match:
        return ''
    value = _read_optional(fs, '/sys/class/nvme/%s/transport' % match.group(1))
    return str(value or '').strip().lower()


def _has_local_controller_evidence(fs, sys_path, transport):
    """Require positive local topology, not merely absence of a remote tran."""
    path = str(sys_path or '').lower()
    if '/devices/pci' in path:
        return True
    # NVMe controllers expose their actual transport separately from lsblk's
    # often-empty TRAN column. Only the kernel's pcie transport is local here;
    # require an NVMe controller in sysfs, but do not require lsblk TRAN to be
    # populated (many kernel/udev combinations leave it blank).
    has_nvme_controller = re.search(r'(?:^|/)nvme\d+(?:/|$)', path) is not None
    return has_nvme_controller and _nvme_controller_transport(fs, sys_path) == 'pcie'


def _remote_storage_path(fs, sys_path):
    path = str(sys_path or '').lower()
    if any(token in path for token in (
            'iscsi', '/session', '/rport-', 'fc_remote_ports',
            'nvme-fabrics', 'nvmeof', 'nvme-o-f')):
        return True
    # FC and iSCSI paths can still traverse a local PCI HBA/NIC. Check their
    # class-device identity as well so PCI ancestry alone cannot bless SAN IO.
    hosts = re.findall(r'(?:^|/)host(\d+)(?:/|$)', path)
    for host in hosts:
        if fs.exists('/sys/class/fc_host/host%s' % host):
            return True
        if fs.exists('/sys/class/iscsi_host/host%s' % host):
            return True
    return False


def _candidate_fingerprint(boot_id, row, device, by_id, serial, sys_path, sys_inode):
    identity = {
        'boot_id': boot_id,
        'device': device,
        'by_id_path': by_id or '',
        'major_minor': row.get('major_minor', ''),
        'serial': serial,
        'wwn': str(row.get('wwn') or '').strip(),
        'capacity_bytes': row.get('size', 0),
        'transport': str(row.get('tran') or '').strip().lower(),
        'sysfs_path': sys_path or '',
        'sysfs_inode': str(sys_inode or ''),
    }
    raw = json.dumps(identity, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest(), identity


def _by_id_matches_serial(path, serial):
    """Match a serial as a complete by-id suffix, not an arbitrary substring."""
    basename = os.path.basename(path).lower()
    serial = str(serial).strip().lower()
    return bool(serial and (basename.endswith('-' + serial) or
                            basename.endswith('_' + serial)))


def _camelize(value):
    if isinstance(value, dict):
        return dict((re.sub(r'_([a-z])', lambda match: match.group(1).upper(), key),
                     _camelize(item)) for key, item in value.items())
    if isinstance(value, list):
        return [_camelize(item) for item in value]
    return value


def _candidate_reasons(row, parent, by_id, serial, duplicate_serial,
                       protected, fs, sys_path, now):
    reasons = []
    name = row.get('kname')
    row_type = str(row.get('type') or '').lower()
    transport = str(row.get('tran') or '').strip().lower()
    syspath_lower = str(sys_path or '').lower()
    if row_type not in ('disk', 'part'):
        reasons.append('UNSUPPORTED_BLOCK_TYPE')
    if name in protected:
        reasons.append('SYSTEM_OR_MOUNTED_DEVICE')
    if row_type == 'disk' and row.get('children'):
        reasons.append('DEVICE_HAS_CHILDREN')
    if row_type in LAYERED_TYPES or transport in SHARED_TRANSPORTS or \
            _remote_storage_path(fs, sys_path) or any(
                token in syspath_lower for token in ('/fc/', 'fibrechannel', 'multipath')):
        reasons.append('SHARED_OR_LAYERED_STORAGE')
    elif (transport not in SUPPORTED_LOCAL_TRANSPORTS or
          not _has_local_controller_evidence(fs, sys_path, transport)):
        reasons.append('LOCAL_EXCLUSIVITY_NOT_PROVEN')
    if bool(str(row.get('ro') or '0') in ('1', 'true', 'True')):
        reasons.append('DEVICE_READ_ONLY')
    if bool(str(row.get('rm') or '0') in ('1', 'true', 'True')):
        reasons.append('REMOVABLE_DEVICE')
    if not serial:
        reasons.append('SERIAL_IDENTITY_MISSING')
    elif duplicate_serial:
        reasons.append('SERIAL_IDENTITY_NOT_UNIQUE')
    if not by_id:
        reasons.append('BY_ID_IDENTITY_MISSING')
    if row.get('size', 0) <= 0:
        reasons.append('CAPACITY_UNAVAILABLE')
    if sys_path is None:
        reasons.append('SYSFS_IDENTITY_UNAVAILABLE')
    else:
        holders = _sysfs_entries(fs, os.path.join(sys_path, 'holders'))
        slaves = _sysfs_entries(fs, os.path.join(sys_path, 'slaves'))
        if holders is None or slaves is None:
            reasons.append('SYSFS_DEPENDENCY_STATE_UNAVAILABLE')
        elif holders:
            reasons.append('ACTIVE_BLOCK_HOLDERS')
        if slaves:
            reasons.append('LAYERED_DEVICE_UNSUPPORTED')
    return reasons


def _signature_reason(runner, device):
    result = _command(runner, ['blkid', '-p', '-o', 'export', '--', device], timeout=5)
    output = result.get('stdout') or ''
    if result.get('returncode') == 2 and not output.strip():
        return None
    if result.get('returncode') == 0:
        return 'EXISTING_FILESYSTEM_OR_PARTITION_SIGNATURE'
    return 'SIGNATURE_PROBE_FAILED'


def _prepared_service_data(service_backend, service_config, boot_id, now, fs):
    resource, identity, effective = _service_resource(service_backend)
    config = _service_config(service_config)
    state = str(resource.get('state') or '').upper()
    resource_uuid = resource.get('resource_uuid')
    fingerprint = resource.get('fingerprint')
    observed_at = resource.get('observed_at')
    capacity = resource.get('capacity_bytes')
    ownership_generation = service_backend.get('ownership_generation') if isinstance(service_backend, dict) else None
    identity_qualified = service_backend.get('identity_qualified') is True if isinstance(service_backend, dict) else False
    if state not in ('PREPARED', 'ACTIVE'):
        return None
    if (not isinstance(resource_uuid, str) or not re.match(r'^[0-9a-fA-F]{32}$', resource_uuid) or
            not isinstance(fingerprint, str) or not re.match(r'^[0-9a-fA-F]{64}$', fingerprint) or
            not _fresh_observation(observed_at, now) or not isinstance(identity, dict) or
            not identity_qualified or
            ownership_generation != resource_uuid):
        return {'invalid': True, 'reason': 'PREPARED_BACKEND_EVIDENCE_INVALID'}
    if not config:
        return {'invalid': True, 'reason': 'PREPARED_BACKEND_CONFIG_MISSING'}
    configured_device = config.get('device') or _identity_value(identity, 'device', 'canonical_device')
    device = _identity_value(identity, 'device', 'canonical_device')
    file_path = config.get('file_path') or _identity_value(identity, 'file_path')
    if not isinstance(device, str) or not device or not isinstance(configured_device, str):
        return {'invalid': True, 'reason': 'PREPARED_BACKEND_DEVICE_UNKNOWN'}
    try:
        configured_canonical = fs.realpath(configured_device)
    except (IOError, OSError):
        configured_canonical = configured_device
    if configured_canonical != device:
        return {'invalid': True, 'reason': 'PREPARED_BACKEND_CONFIG_MISMATCH'}
    if _identity_value(identity, 'boot_id') != boot_id:
        return {'invalid': True, 'reason': 'PREPARED_BACKEND_BOOT_ID_MISMATCH'}
    try:
        if int(capacity) != int(_identity_value(identity, 'capacity_bytes')):
            return {'invalid': True, 'reason': 'PREPARED_BACKEND_CAPACITY_MISMATCH'}
    except (TypeError, ValueError):
        return {'invalid': True, 'reason': 'PREPARED_BACKEND_CAPACITY_UNKNOWN'}
    return {
        'resource_uuid': resource_uuid,
        'fingerprint': fingerprint,
        'state': state,
        'capacity_bytes': int(capacity),
        'device': device,
        'file_path': file_path,
        'identity': identity,
        'effective': effective,
        'config': config,
        'active': bool(resource.get('active')) or state == 'ACTIVE',
    }


def _prepared_file_candidate(prepared, fs, boot_id, now):
    file_path = prepared.get('file_path')
    if not file_path:
        return None
    reasons = []
    try:
        canonical = fs.realpath(file_path)
        file_stat = fs.lstat(file_path)
    except (IOError, OSError):
        return {
            'type': 'file', 'path': file_path, 'device': prepared.get('device'),
            'resource_uuid': prepared['resource_uuid'],
            'fingerprint': prepared['fingerprint'], 'capacity_bytes': prepared['capacity_bytes'],
            'eligible': False, 'writeback_ready': False, 'state': 'DISCONNECTED',
            'reasons': ['PREPARED_BACKEND_FILE_DISCONNECTED'], 'by_id_path': '',
        }
    if canonical != file_path or stat.S_ISLNK(file_stat.st_mode):
        reasons.append('PREPARED_FILE_PATH_CHANGED')
    if not stat.S_ISREG(file_stat.st_mode) or getattr(file_stat, 'st_nlink', 0) != 1:
        reasons.append('PREPARED_FILE_IDENTITY_CHANGED')
    identity = prepared['identity']
    expected = (
        ('file_inode', getattr(file_stat, 'st_ino', None)),
        ('file_device', getattr(file_stat, 'st_dev', None)),
        ('file_size', getattr(file_stat, 'st_size', None)),
    )
    for key, actual in expected:
        wanted = _identity_value(identity, key)
        if actual is None or wanted is None or str(actual) != str(wanted):
            reasons.append('PREPARED_FILE_IDENTITY_MISMATCH')
            break
    if getattr(file_stat, 'st_size', 0) != prepared['capacity_bytes']:
        reasons.append('PREPARED_FILE_CAPACITY_MISMATCH')
    if reasons:
        return {
            'type': 'file', 'path': file_path, 'device': prepared.get('device'),
            'resource_uuid': prepared['resource_uuid'],
            'fingerprint': prepared['fingerprint'], 'capacity_bytes': prepared['capacity_bytes'],
            'eligible': False, 'writeback_ready': False, 'state': 'IDENTITY_MISMATCH',
            'reasons': sorted(set(reasons)), 'by_id_path': '',
        }
    return {
        'type': 'file', 'path': file_path, 'device': prepared.get('device'),
        'resource_uuid': prepared['resource_uuid'],
        'fingerprint': prepared['fingerprint'], 'capacity_bytes': prepared['capacity_bytes'],
        'eligible': True, 'writeback_ready': True, 'state': prepared['state'],
        'reasons': [], 'by_id_path': '', 'identity': prepared['fingerprint'],
        'active': prepared['active'], 'host_boot_id': boot_id,
    }


def probe_writeback_backends(host_uuid=None, service_backend=None, service_config=None,
                             now=None, runner=None, filesystem=None):
    """Return a conservative read-only inventory of safe writeback targets.

    ``runner`` accepts ``(argv, timeout=seconds)`` and returns a result dict
    with returncode/stdout/stderr. ``filesystem`` provides read/exists/listdir/
    realpath/stat/lstat methods. These injection points make the probe
    deterministic in unit tests. An unprepared block candidate is selectable
    only as an offline-preparation target and never receives a service-owned
    resource UUID. Files are returned only when the service already reports a
    fresh, identity-matched PREPARED/ACTIVE resource.
    """
    runner = runner or _run_command
    filesystem = filesystem or _LocalFilesystem()
    try:
        boot_id = (filesystem.read('/proc/sys/kernel/random/boot_id') or '').strip()
    except (IOError, OSError):
        boot_id = ''
    probed_at_epoch = _now_epoch(now)
    probed_at = datetime.datetime.utcfromtimestamp(probed_at_epoch).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    response = {'host_uuid': host_uuid, 'boot_id': boot_id or None,
                'observed_at': probed_at, 'status': 'UNSUPPORTED',
                'reasons': [], 'candidates': []}
    if not boot_id:
        response['reasons'] = ['HOST_BOOT_ID_UNAVAILABLE']
        return _camelize(response)

    result = _command(runner, ['lsblk', '--json', '--bytes', '--paths', '--tree',
                               '--output', LSBLK_COLUMNS], timeout=5)
    if result.get('returncode') != 0:
        response['reasons'] = ['LSBLK_UNSUPPORTED_OR_FAILED']
        return _camelize(response)
    try:
        rows = _rows_from_lsblk(result.get('stdout') or '')
    except (TypeError, ValueError):
        response['reasons'] = ['LSBLK_OUTPUT_INVALID']
        return _camelize(response)
    response['status'] = 'AVAILABLE'
    if not rows:
        response['status'] = 'DISCONNECTED'
        response['reasons'] = ['NO_BLOCK_DEVICES']
        prepared = _prepared_service_data(service_backend or {}, service_config or {},
                                          boot_id, now, filesystem)
        if prepared and prepared.get('invalid'):
            response['reasons'].append(prepared['reason'])
        elif prepared:
            response['candidates'].append({
                'identity': prepared['fingerprint'],
                'fingerprint': prepared['fingerprint'],
                'resource_uuid': prepared['resource_uuid'],
                'type': 'file' if prepared.get('file_path') else 'block',
                'path': prepared.get('file_path') or prepared['device'],
                'device': prepared['device'], 'by_id_path': '',
                'capacity_bytes': prepared['capacity_bytes'],
                'eligible': False, 'writeback_ready': False,
                'state': 'DISCONNECTED',
                'reasons': ['PREPARED_BACKEND_NOT_FOUND'],
            })
        return _camelize(response)

    protected = _mount_and_swap_devices(filesystem, rows, runner)
    if protected is None:
        protected = set(row.get('kname') for row in rows)
        response['reasons'] = ['MOUNT_OR_SWAP_STATE_UNAVAILABLE']
    by_id = _by_id_links(filesystem, rows)
    if by_id is None:
        by_id = {}
        response['reasons'].append('BY_ID_INVENTORY_UNAVAILABLE')
    serial_counts = {}
    for row in rows:
        if str(row.get('type') or '').lower() == 'disk':
            serial = str(row.get('serial') or '').strip()
            if serial:
                serial_counts[serial] = serial_counts.get(serial, 0) + 1

    prepared = _prepared_service_data(service_backend or {}, service_config or {},
                                      boot_id, now, filesystem)
    prepared_file = None
    prepared_file_device_ready = False
    if prepared and not prepared.get('invalid') and prepared.get('file_path'):
        prepared_file = _prepared_file_candidate(prepared, filesystem, boot_id, now)

    # Prepared service files are the only file candidates. Never walk arbitrary
    # directories or infer ownership from a plausible pathname. Add the file
    # only after its loop block is independently matched below.

    for row in rows:
        row_type = str(row.get('type') or '').lower()
        discoverable_types = ('disk', 'part') + LAYERED_TYPES + ('lvm',)
        if row_type not in discoverable_types and not (
                row_type == 'loop' and prepared and prepared.get('file_path')):
            continue
        name = row.get('name')
        kname = row.get('kname')
        if not isinstance(name, str) or not name.startswith('/dev/') or not kname:
            continue
        parent = next((item for item in rows if item.get('kname') == row.get('pkname')), None)
        serial = str(row.get('serial') or '').strip()
        if not serial and parent is not None:
            serial = str(parent.get('serial') or '').strip()
        links = by_id.get(name, [])
        if not links:
            try:
                canonical = filesystem.realpath(name)
                links = by_id.get(canonical, [])
            except (IOError, OSError):
                pass
        # Require a by-id alias that actually carries the hardware serial.
        by_id_path = next((path for path in links
                           if serial and _by_id_matches_serial(path, serial)), '')
        sys_path = _sysfs_path(filesystem, row.get('major_minor'))
        sys_stat = None
        if sys_path:
            try:
                sys_stat = filesystem.stat(sys_path)
            except (IOError, OSError):
                pass
        reasons = _candidate_reasons(
            row, parent, by_id_path, serial,
            bool(serial and serial_counts.get(serial, 0) > 1),
            protected, filesystem, sys_path, now)
        signature_reason = _signature_reason(runner, name)
        if signature_reason:
            reasons.append(signature_reason)

        try:
            device_stat = filesystem.stat(name)
            device_realpath = filesystem.realpath(name)
        except (IOError, OSError):
            device_stat, device_realpath = None, None
            reasons.append('DEVICE_DISCONNECTED')
        local_identity = {
            'boot_id': boot_id,
            'device': device_realpath,
            'rdev': getattr(device_stat, 'st_rdev', None),
            'node_inode': getattr(device_stat, 'st_ino', None),
            'sys_inode': getattr(sys_stat, 'st_ino', None),
            'capacity_bytes': row.get('size', 0),
        }
        fingerprint, stable_identity = _candidate_fingerprint(
            boot_id, row, device_realpath or name, by_id_path, serial,
            sys_path, local_identity['sys_inode'])
        # Include the native device-node identity in the stable readback
        # contract used to construct the service's BackendFingerprint.
        stable_identity['rdev'] = local_identity['rdev']
        stable_identity['node_inode'] = local_identity['node_inode']
        reasons = sorted(set(reasons))
        candidate = {
            'identity': 'candidate:' + fingerprint,
            'fingerprint': fingerprint,
            'resource_uuid': None,
            'type': 'block',
            'path': by_id_path or name,
            'device': device_realpath or name,
            'by_id_path': by_id_path,
            'capacity_bytes': row.get('size', 0),
            'host_boot_id': boot_id,
            'eligible': not reasons,
            'writeback_ready': False,
            'state': 'NEEDS_OFFLINE_PREPARATION' if not reasons else 'INELIGIBLE',
            'reasons': reasons if reasons else ['NEEDS_OFFLINE_PREPARATION'],
            'transport': str(row.get('tran') or '').strip().lower(),
            'stable_identity': stable_identity,
        }

        if prepared and not prepared.get('invalid') and \
                prepared.get('device') == local_identity['device']:
            service_identity = prepared.get('identity') or {}
            expected = {
                'boot_id': boot_id,
                'device': local_identity['device'],
                'rdev': local_identity['rdev'],
                'node_inode': local_identity['node_inode'],
                'sys_inode': local_identity['sys_inode'],
                'capacity_bytes': local_identity['capacity_bytes'],
            }
            matches = all(
                _identity_value(service_identity, key) is not None and
                str(_identity_value(service_identity, key)) == str(value)
                for key, value in expected.items())
            permitted_existing_reasons = set()
            if prepared.get('file_path'):
                permitted_existing_reasons.update((
                    'UNSUPPORTED_BLOCK_TYPE', 'LOCAL_EXCLUSIVITY_NOT_PROVEN',
                    'SERIAL_IDENTITY_MISSING', 'BY_ID_IDENTITY_MISSING'))
            if prepared['active']:
                permitted_existing_reasons.add('ACTIVE_BLOCK_HOLDERS')
            local_risks = set(reasons) - permitted_existing_reasons
            if matches and not local_risks:
                prepared_file_device_ready = bool(prepared.get('file_path'))
                candidate.update({
                    'identity': prepared['fingerprint'],
                    'fingerprint': prepared['fingerprint'],
                    'resource_uuid': prepared['resource_uuid'],
                    'eligible': True,
                    'writeback_ready': True,
                    'state': prepared['state'],
                    'reasons': [],
                    'active': prepared['active'],
                })
            else:
                candidate['eligible'] = False
                candidate['writeback_ready'] = False
                candidate['state'] = 'IDENTITY_MISMATCH'
                candidate['reasons'] = sorted(local_risks | set(
                    [] if matches else ['PREPARED_BACKEND_IDENTITY_MISMATCH']))
        if not (prepared and prepared.get('file_path') and
                prepared.get('device') == local_identity['device'] and
                candidate.get('writeback_ready')):
            response['candidates'].append(candidate)

    if prepared and prepared.get('invalid'):
        response['reasons'].append(prepared['reason'])
    if prepared and not prepared.get('invalid'):
        if not prepared.get('file_path'):
            present = any(candidate.get('resource_uuid') == prepared['resource_uuid']
                          for candidate in response['candidates'])
            if not present:
                response['candidates'].append({
                    'type': 'block', 'path': prepared['device'],
                    'device': prepared['device'], 'resource_uuid': prepared['resource_uuid'],
                    'fingerprint': prepared['fingerprint'],
                    'capacity_bytes': prepared['capacity_bytes'],
                    'eligible': False, 'writeback_ready': False,
                    'state': 'DISCONNECTED', 'by_id_path': '',
                    'reasons': ['PREPARED_BACKEND_NOT_FOUND'],
                })
    if prepared_file is not None:
        if prepared_file_device_ready:
            response['candidates'].append(prepared_file)
        else:
            prepared_file['eligible'] = False
            prepared_file['writeback_ready'] = False
            prepared_file['state'] = 'IDENTITY_MISMATCH'
            prepared_file['reasons'] = ['PREPARED_BACKEND_DEVICE_NOT_READY']
            response['candidates'].append(prepared_file)
    response['candidates'].sort(key=lambda candidate: (
        0 if candidate.get('writeback_ready') else 1,
        str(candidate.get('path') or '')))
    return _camelize(response)

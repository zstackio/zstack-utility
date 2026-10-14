"""Request construction and read-only reconciliation for writeback maintenance.

This module does not start a service client or perform device operations. The
caller passes a freshly probed inventory and the already-authorized API
preparation fields. It returns a strict request body for the service CLI.
"""

import hashlib
import calendar
import datetime
import re
import time


def _pick(mapping, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _stable(stable, key):
    aliases = {
        'boot_id': ('boot_id', 'bootId'),
        'major_minor': ('major_minor', 'majorMinor'),
        'capacity_bytes': ('capacity_bytes', 'capacityBytes'),
        'sysfs_path': ('sysfs_path', 'sysfsPath'),
        'sysfs_inode': ('sysfs_inode', 'sysfsInode'),
        'node_inode': ('node_inode', 'nodeInode'),
    }
    return _pick(stable, *aliases.get(key, (key,)))


def _fresh_inventory(inventory):
    observed = _pick(inventory, 'observed_at', 'observedAt')
    try:
        observed = float(observed)
    except (TypeError, ValueError):
        if not isinstance(observed, str):
            raise ValueError('WRITEBACK_INVENTORY_TIMESTAMP_REQUIRED')
        try:
            parsed = datetime.datetime.strptime(observed, '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError:
            try:
                parsed = datetime.datetime.strptime(observed, '%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                raise ValueError('WRITEBACK_INVENTORY_TIMESTAMP_REQUIRED')
        observed = calendar.timegm(parsed.utctimetuple()) + parsed.microsecond / 1000000.0
    age = time.time() - observed
    if age < -5 or age > 90:
        raise ValueError('WRITEBACK_INVENTORY_STALE')


def _canonical_candidate(inventory, candidate_id):
    if not isinstance(inventory, dict):
        raise ValueError('WRITEBACK_INVENTORY_REQUIRED')
    _fresh_inventory(inventory)
    candidates = inventory.get('candidates')
    if not isinstance(candidates, list):
        raise ValueError('WRITEBACK_INVENTORY_INVALID')
    matches = [candidate for candidate in candidates
               if _pick(candidate, 'identity') == candidate_id]
    if len(matches) != 1:
        raise ValueError('WRITEBACK_CANDIDATE_NOT_UNIQUE')
    candidate = matches[0]
    if (candidate.get('type') != 'block' or not candidate.get('eligible') or
            _pick(candidate, 'writeback_ready', 'writebackReady') or
            candidate.get('state') != 'NEEDS_OFFLINE_PREPARATION'):
        raise ValueError('WRITEBACK_CANDIDATE_NOT_PREPARABLE')
    identity = _pick(candidate, 'stable_identity', 'stableIdentity')
    required = ('boot_id', 'device', 'major_minor', 'capacity_bytes',
                'sysfs_path', 'sysfs_inode', 'rdev', 'node_inode')
    if not isinstance(identity, dict) or any(_stable(identity, key) in (None, '') for key in required):
        raise ValueError('WRITEBACK_CANDIDATE_IDENTITY_INCOMPLETE')
    if not re.match(r'^candidate:[0-9a-f]{64}$', str(candidate_id)):
        raise ValueError('WRITEBACK_CANDIDATE_ID_INVALID')
    return candidate, identity


def build_backend_maintenance_request(inventory, backend_preparation):
    """Build the internal CLI request from a fresh probe and API fields.

    `backend_preparation` must contain requestId/taskUuid, candidateId,
    expectedHostBootId, expectedPoolGeneration, backendCapacityBytes, and
    resetConfirmed. Raw device path and service plan come only from the
    selected, freshly probed candidate.
    """
    if not isinstance(backend_preparation, dict):
        raise ValueError('BACKEND_PREPARATION_REQUIRED')
    candidate_id = _pick(backend_preparation, 'candidateId', 'candidate_id')
    candidate, stable = _canonical_candidate(inventory, candidate_id)
    request_id = _pick(backend_preparation, 'requestId', 'request_id', 'taskUuid', 'task_uuid')
    expected_boot = _pick(backend_preparation, 'expectedHostBootId', 'expected_host_boot_id')
    expected_generation = _pick(backend_preparation, 'expectedPoolGeneration', 'expected_pool_generation')
    capacity = _pick(backend_preparation, 'backendCapacityBytes', 'backend_capacity_bytes')
    reset_confirmed = _pick(backend_preparation, 'resetConfirmed', 'reset_confirmed')
    host_boot = _pick(inventory, 'host_boot_id', 'hostBootId', 'boot_id', 'bootId')
    candidate_boot = _pick(candidate, 'host_boot_id', 'hostBootId')
    if not request_id or not expected_boot or expected_generation is None or reset_confirmed is not True:
        raise ValueError('BACKEND_MAINTENANCE_CONFIRMATION_REQUIRED')
    if (str(expected_boot) != str(host_boot) or str(expected_boot) != str(candidate_boot) or
            str(expected_boot) != str(_stable(stable, 'boot_id'))):
        raise ValueError('BACKEND_MAINTENANCE_BOOT_ID_MISMATCH')
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
        raise ValueError('BACKEND_MAINTENANCE_CAPACITY_REQUIRED')
    if capacity != int(_stable(stable, 'capacity_bytes')) or capacity != int(_pick(candidate, 'capacity_bytes', 'capacityBytes')):
        raise ValueError('BACKEND_MAINTENANCE_CAPACITY_MISMATCH')
    major_minor = str(_stable(stable, 'major_minor'))
    if not re.match(r'^\d+:\d+$', major_minor):
        raise ValueError('BACKEND_MAINTENANCE_MAJOR_MINOR_INVALID')
    sys_path = str(_stable(stable, 'sysfs_path'))
    if not sys_path.startswith('/sys/devices/') and not sys_path.startswith('/sys/block/'):
        raise ValueError('BACKEND_MAINTENANCE_SYSFS_PATH_INVALID')
    # Match service backendStackDigest's leaf-device digest exactly.
    sys_inode = _stable(stable, 'sysfs_inode')
    stack_input = '%s:%s:%s\n' % (major_minor, sys_path, sys_inode)
    stack_sha256 = hashlib.sha256(stack_input.encode('utf-8')).hexdigest()
    device = str(stable['device'])
    fingerprint = {
        'boot_id': str(_stable(stable, 'boot_id')),
        'canonical_device': device,
        'rdev': int(_stable(stable, 'rdev')),
        'node_inode': int(_stable(stable, 'node_inode')),
        'sysfs_inode': int(sys_inode),
        'capacity_bytes': capacity,
        'direct_io': False,
        'stack_sha256': stack_sha256,
    }
    return {
        'request_id': str(request_id),
        'candidate_id': str(candidate_id),
        'expected_host_boot_id': str(expected_boot),
        'expected_pool_generation': str(expected_generation),
        'backend_capacity_bytes': capacity,
        'target_identity': fingerprint,
        'backend': {
            'device': device,
            'minimum_filesystem_free_bytes': 0,
            # BackendMaintenanceRequest embeds BackendPlan, whose validation
            # requires an explicit exclusivity confirmation. This is distinct
            # from BackendSpec (which has no such field).
            'exclusive': True,
        },
        'reset_confirmed': True,
    }


def read_backend_maintenance_status(service_client):
    """Read durable status only; never retries or starts maintenance."""
    if service_client is None or not callable(getattr(service_client, 'get', None)):
        raise ValueError('MEMORY_SERVICE_CLIENT_REQUIRED')
    response = service_client.get('/v1/backend-maintenance')
    if not isinstance(response, dict) or not response.get('stage'):
        raise ValueError('BACKEND_MAINTENANCE_STATUS_INVALID')
    return response

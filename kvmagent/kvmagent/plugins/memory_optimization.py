# -*- coding: utf-8 -*-
"""Host memory optimisation control plane for the KVM agent.

The management node owns policy. The Agent applies KSM settings through the
distribution's native ksmtuned units and the ZRAM service's existing control
contract. It must not start a parallel KSM daemon or silently turn an unknown
operation result into success.
"""
import json
import copy
import hashlib
import os
import socket
import signal
import subprocess
import stat
import tempfile
import time
import platform
import errno
import calendar
import fcntl
import re
import shlex
import math
from collections import OrderedDict
try:
    from urllib.parse import urlencode
except ImportError:  # pragma: no cover - Python 2 deployment baseline
    from urllib import urlencode
from contextlib import contextmanager
try:
    import http.client as stdlib_http
except ImportError:  # pragma: no cover - Python 2 deployment baseline
    import httplib as stdlib_http

from kvmagent import kvmagent
from kvmagent.plugins.memory_writeback_backends import probe_writeback_backends
from kvmagent.plugins.memory_writeback_maintenance import (
    build_backend_maintenance_request, read_backend_maintenance_status)
from kvmagent.plugins.memory_optimization_ksm_native import (
    NativeKsmConfigError, managed_config_values, native_sleep_msec,
    parse_memtotal_kb, render_config)
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import zram_driver

logger = log.get_logger(__name__)
try:
    STRING_TYPES = (basestring,)
except NameError:
    STRING_TYPES = (str,)
try:
    INTEGER_TYPES = (int, long)
except NameError:
    INTEGER_TYPES = (int,)


class FirstZramConfigRejected(Exception):
    """A positively observed non-vendor config rejected before any write."""


class _UnixHTTPConnection(stdlib_http.HTTPConnection):
    """HTTPConnection transport that keeps stdlib chunked decoding."""
    def __init__(self, socket_path, timeout):
        stdlib_http.HTTPConnection.__init__(self, 'localhost', timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


def _accounting_wire_identity(value):
    """Keep uint64 identity tokens exact across generic Java/JS JSON maps.

    Python decodes the service's integer JSON without losing precision. Do
    this before serializing the Agent response; converting a Java Double
    later cannot recover lost bits. Metrics remain numeric for charts.
    Return a copy so the collector's native inventory is not modified.
    """
    identity_fields = frozenset(('pool_generation', 'sequence', 'cgroup_id',
                                'cgroup_inode', 'mm_context_id', 'start_time',
                                'sampled_monotonic_ns'))
    if isinstance(value, list):
        return [_accounting_wire_identity(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key in identity_fields and item is not None:
            if isinstance(item, bool) or not isinstance(item, INTEGER_TYPES + STRING_TYPES):
                raise ValueError('INVALID_ACCOUNTING_IDENTITY:%s' % key)
            decimal = str(item)
            if not re.match(r'^(0|[1-9][0-9]*)\Z', decimal) or int(decimal) > (1 << 64) - 1:
                raise ValueError('INVALID_ACCOUNTING_IDENTITY:%s' % key)
            result[key] = decimal
        else:
            result[key] = _accounting_wire_identity(item)
    return result


def _product_vm_uuid(value):
    if isinstance(value, STRING_TYPES) and re.match(
            r'^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z', value):
        return value.replace('-', '').lower()
    return value


class MemoryOptimizationPlugin(kvmagent.KvmAgent):
    STATE_PATH = '/memory/optimization/state'
    APPLY_PATH = '/memory/optimization/apply'
    RECONCILE_PATH = '/memory/optimization/reconcile'
    MIGRATION_HOLD_PATH = '/memory/optimization/migration-hold'
    VM_EFFICIENCY_PATH = '/memory/optimization/vm-efficiency'
    ACCOUNTING_PATH = '/memory/optimization/accounting'
    WRITEBACK_BACKENDS_PATH = '/memory/optimization/writeback-backends'

    # The socket and endpoint are configuration values so the Agent does not
    # bake in a deployment-specific service path.
    DEFAULT_SOCKET = '/run/zram-efficiency-admission/control.sock'
    DEFAULT_MONITOR_SOCKET = '/run/zram-efficiency-admission/monitor.sock'
    DEFAULT_SERVICE_PATH = '/v1/zram/tuning'
    DEFAULT_REQUEST_BYTES = 1 * 1024 * 1024
    DEFAULT_RESPONSE_BYTES = 16 * 1024 * 1024
    DEFAULT_COMMUNICATION_SECONDS = 30
    KSM_UNIT = 'ksm.service'
    KSM_TUNED_UNIT = 'ksmtuned.service'
    NATIVE_KSM_FILES = ('/usr/sbin/ksmtuned', '/usr/libexec/ksmctl',
                        '/usr/lib/systemd/system/ksm.service',
                        '/usr/lib/systemd/system/ksmtuned.service')
    MANAGED_ZRAM_UNIT = 'zram-memory.service'
    POOL_STARTUP_OBSERVATION_REASON = 'NO_QUALIFIED_MANAGED_POOL: STARTUP_OBSERVATION_IN_PROGRESS'
    KSM_CONF = '/etc/ksmtuned.conf'
    KSM_LOCK = '/run/zstack/memory-optimization/ksm.writer.lock'
    OPERATION_DIR = '/var/lib/zstack/memory-optimization/operations'
    ACTIVE_CONTROL = '/var/lib/zstack/memory-optimization/active-control'
    VM_BINDING_DIR = '/var/lib/zstack/memory-optimization/vm-bindings'
    ZRAM_CONFIG = '/etc/zram-memory/config.json'
    ZRAM_CONFIG_TEMPLATE = '/usr/share/zstack-zram/config.json'
    FIRST_USE_AUTHORIZING_STAGE = 'FIRST_USE_AUTHORIZING'

    def __init__(self, service_call=None):
        super(MemoryOptimizationPlugin, self).__init__()
        self.service_call = service_call or self._call_local_service
        self.host_uuid = None
        self.socket_path = self.DEFAULT_SOCKET
        self.monitor_socket_path = self.DEFAULT_MONITOR_SOCKET
        self.service_path = self.DEFAULT_SERVICE_PATH
        self.request_bytes = self.DEFAULT_REQUEST_BYTES
        self.response_bytes = self.DEFAULT_RESPONSE_BYTES
        self.communication_seconds = self.DEFAULT_COMMUNICATION_SECONDS
        self.operation_dir = self.OPERATION_DIR
        self.active_control_path = self.ACTIVE_CONTROL
        self.vm_binding_dir = self.VM_BINDING_DIR
        self.drain_unit = self.MANAGED_ZRAM_UNIT
        self.drain_binary = '/usr/local/libexec/zram-efficiency'
        self.drain_config = '/etc/zram-memory/config.json'
        self.zram_config_path = self.ZRAM_CONFIG
        self.zram_config_template_path = self.ZRAM_CONFIG_TEMPLATE
        self.drain_dir = os.path.join(self.operation_dir, 'drain')

    def configure(self, config):
        # KvmRESTService shares this dict with HostPlugin, whose connect
        # handshake fills HOST_UUID later. Preserve even an empty dict.
        if config is None:
            config = {}
        self.config = config
        self.host_uuid = config.get('hostUuid', self.host_uuid)
        self.socket_path = config.get('socketPath', self.socket_path)
        self.monitor_socket_path = config.get(
            'monitorSocketPath', os.path.join(os.path.dirname(self.socket_path), 'monitor.sock'))
        self.service_path = config.get('servicePath', self.service_path)
        for name, default in (('requestBytes', self.request_bytes),
                              ('responseBytes', self.response_bytes),
                              ('communicationSeconds', self.communication_seconds)):
            value = config.get(name, default)
            integer_budget = name in ('requestBytes', 'responseBytes')
            valid_type = isinstance(value, (int, float)) if not integer_budget else isinstance(value, int)
            if isinstance(value, bool) or not valid_type or value <= 0:
                raise ValueError('invalid memory service %s' % name)
            setattr(self, {'requestBytes': 'request_bytes',
                           'responseBytes': 'response_bytes',
                           'communicationSeconds': 'communication_seconds'}[name], value)
        self.operation_dir = config.get('operationDir', self.operation_dir)
        self.active_control_path = config.get(
            'activeControlPath', os.path.join(self.operation_dir, 'active-control'))
        self.vm_binding_dir = config.get(
            'vmBindingDir', os.path.join(self.operation_dir, 'vm-bindings'))
        self.drain_unit = config.get('drainUnit', self.drain_unit)
        self.drain_binary = config.get('drainBinary', self.drain_binary)
        self.drain_config = config.get('drainConfig', self.drain_config)
        self.drain_dir = config.get('drainDir', os.path.join(self.operation_dir, 'drain'))

    def _vm_binding_path(self, vm_uuid):
        if not self._valid_identifier(vm_uuid):
            raise ValueError('INVALID_VM_UUID')
        return os.path.join(self.vm_binding_dir, '%s.json' % vm_uuid)

    def _load_vm_binding(self, vm_uuid):
        try:
            with open(self._vm_binding_path(vm_uuid), 'r') as stream:
                return json.load(stream)
        except (IOError, OSError, ValueError):
            return None

    def _save_vm_binding(self, command):
        if not os.path.isdir(self.vm_binding_dir):
            os.makedirs(self.vm_binding_dir)
        target = self._vm_binding_path(command['resourceUuid'])
        fd, temp_path = tempfile.mkstemp(prefix='.binding-', dir=self.vm_binding_dir)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'resourceUuid': command['resourceUuid'],
                       'expectedInstanceGeneration': command['expectedInstanceGeneration'],
                       'participation': command.get('participation', 'inherit'),
                       'operationUuid': command['operationUuid'],
                       'updatedAt': int(time.time() * 1000)}, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temp_path, target)

    def _get_active_control(self):
        try:
            with open(self.active_control_path, 'r') as stream:
                return stream.read().strip()
        except (IOError, OSError):
            return None

    def _set_active_control(self, operation_uuid):
        directory = os.path.dirname(self.active_control_path)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        fd, temp_path = tempfile.mkstemp(prefix='.active-control-', dir=directory)
        with os.fdopen(fd, 'w') as stream:
            stream.write(operation_uuid or '')
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temp_path, self.active_control_path)

    def _resume_control_record(self):
        """Return the current-boot completed pause record, if any.

        The active UUID is only a fence.  It must not by itself authorize a
        resume: a drain remains non-resumable and journals from a prior boot
        must not be used to restart host memory work.
        """
        operation_uuid = self._get_active_control()
        if not operation_uuid:
            return None
        record = self._load_operation({'operationUuid': operation_uuid})
        if not isinstance(record, dict) or record.get('stage') != 'APPLIED':
            return None
        if record.get('action') != 'pause' or record.get('bootId') != self._current_boot_id():
            return None
        return record

    def _acquire_host_control_lock(self):
        if not os.path.isdir(self.operation_dir):
            os.makedirs(self.operation_dir)
        lock = open(os.path.join(self.operation_dir, '.host-control.flock'), 'a')
        try:
            fcntl.fcntl(lock.fileno(), fcntl.F_SETFD, fcntl.FD_CLOEXEC)
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            lock.close()
            raise
        return lock

    def _record_operation(self, command, stage, result=None):
        if (not isinstance(command, dict) or
                not self._valid_identifier(command.get('operationUuid'))):
            return False
        record = {
            'operationUuid': command.get('operationUuid'),
            'requestHash': self._operation_hash(command),
            'desiredRevision': command.get('desiredRevision'),
            'stage': stage,
            'updatedAt': int(time.time() * 1000),
        }
        if (isinstance(command.get('policy'), dict) and
                command.get('action') in (None, 'apply')):
            policy_mode = command.get('policyMode', 'effective')
            if policy_mode in ('delta', 'effective'):
                # Record the resolved behavior without rewriting the original
                # command that participates in requestHash.
                record['policyMode'] = policy_mode
        try:
            with open('/proc/sys/kernel/random/boot_id', 'r') as stream:
                record['bootId'] = stream.read().strip()
        except (IOError, OSError):
            record['bootId'] = None
        if result is not None:
            record['readback'] = result
        existing = self._load_operation(command)
        if isinstance(existing, dict) and existing.get('requestHash') == record['requestHash']:
            # Keep the first apply receipt separately from the latest
            # reconcile readback.  In particular, a 202 capacity receipt is
            # needed to distinguish a known native BLOCKED result from an
            # operation whose execution outcome is unknown.
            if isinstance(existing.get('applyEvidence'), dict):
                record['applyEvidence'] = existing['applyEvidence']
            elif (command.get('action') in (None, 'apply') and
                  isinstance(result, dict)):
                record['applyEvidence'] = result
            if isinstance(existing.get('activationIntent'), dict):
                record['activationIntent'] = existing['activationIntent']
            if isinstance(existing.get('firstZramUse'), dict):
                record['firstZramUse'] = existing['firstZramUse']
            if existing.get('stage') == 'ACTIVATING' and stage not in ('APPLIED', 'REJECTED'):
                record['stage'] = 'ACTIVATING'
        elif command.get('action') in (None, 'apply') and isinstance(result, dict):
            record['applyEvidence'] = result
        if isinstance(command.get('policy'), dict):
            # Reconcile must know the exact product target.  It must only
            # read native state and compare; it must never reconstruct and
            # replay the original PUT from an operation UUID.
            record['policy'] = command['policy']
            record['policyHash'] = self._policy_digest(command['policy'])
        for key in ('hostUuid', 'scope', 'resourceUuid', 'expectedInstanceGeneration', 'participation',
                    'backendPreparation', 'poolPreparation', 'expectedControlOperationUuid',
                    'maintenanceIntentPath', 'poolMaintenanceIntentPath', 'maintenanceProof'):
            if key in command:
                record[key] = command[key]
        if command.get('action'):
            record['action'] = command['action']
        try:
            if not os.path.isdir(self.operation_dir):
                os.makedirs(self.operation_dir)
            target = os.path.join(self.operation_dir, '%s.json' % command['operationUuid'])
            fd, temp_path = tempfile.mkstemp(prefix='.operation-', dir=self.operation_dir)
            with os.fdopen(fd, 'w') as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temp_path, target)
            directory_fd = os.open(self.operation_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return True
        except (IOError, OSError):
            logger.warn('unable to persist memory optimization operation %s', command.get('operationUuid'))
            return False

    @staticmethod
    def _current_boot_id():
        try:
            with open('/proc/sys/kernel/random/boot_id', 'r') as stream:
                return stream.read().strip()
        except (IOError, OSError):
            return None

    def _read_ksm_ack(self):
        """Read native sysfs and revisioned ksmtuned config without a sidecar daemon."""
        try:
            run = self._read_ksm_sysfs('run')
            pages = self._read_ksm_sysfs('pages_to_scan')
            sleep = self._read_ksm_sysfs('sleep_millisecs')
            zero = self._read_ksm_zero_pages()
            config = self._read_native_ksm_config()
            revision = config.get('CONFIG_REVISION') if config else None
        except (IOError, OSError, ValueError, NativeKsmConfigError):
            return None
        if (run not in ('0', '1') or zero not in ('0', '1', 'unsupported') or
                revision is None or pages is None or sleep is None):
            return None
        return {'run': run, 'configRevision': str(revision),
                'pages_to_scan': pages, 'sleep_millisecs': sleep,
                'use_zero_pages': zero}

    def _read_ksm_zero_pages(self):
        """Distinguish a missing optional sysfs interface from read failure."""
        try:
            value = self._read_ksm_sysfs('use_zero_pages')
        except (IOError, OSError) as exc:
            if exc.errno == errno.ENOENT:
                return 'unsupported'
            raise
        if value not in ('0', '1'):
            raise ValueError('KSM_ZERO_PAGES_READBACK_INVALID')
        return value

    @staticmethod
    def _read_ksm_sysfs(name):
        if name not in ('run', 'pages_to_scan', 'sleep_millisecs', 'use_zero_pages'):
            raise ValueError('KSM_SYSFS_ATTRIBUTE_INVALID')
        path = '/sys/kernel/mm/ksm/%s' % name
        with open(path, 'r') as stream:
            value = stream.read().strip()
        if not re.match(r'^(0|[1-9][0-9]*)\Z', value):
            raise ValueError('KSM_SYSFS_READBACK_INVALID:%s' % name)
        return value

    def _read_native_ksm_config(self):
        try:
            with open(self.KSM_CONF, 'r') as stream:
                return managed_config_values(stream.read())
        except IOError as exc:
            if exc.errno == errno.ENOENT:
                return None
            raise

    def _verify_native_ksm_profile(self):
        """Gate writes on the vendor ksm/ksmtuned tooling being installed; any package version is accepted."""
        if not all(os.path.isfile(path) for path in self.NATIVE_KSM_FILES):
            raise ValueError('KSM_NATIVE_PROFILE_UNSUPPORTED')

    @staticmethod
    def _native_service_state(unit, operation):
        if unit not in ('ksm.service', 'ksmtuned.service') or operation not in ('active', 'enabled'):
            raise ValueError('KSM_SERVICE_QUERY_INVALID')
        try:
            output = subprocess.check_output(['systemctl', 'is-%s' % operation, unit],
                                             stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as exc:
            output = getattr(exc, 'output', '') or ''
            if not isinstance(output, str):
                output = output.decode('utf-8', 'replace')
        if not isinstance(output, str):
            output = output.decode('utf-8', 'replace')
        value = output.strip().splitlines()[-1] if output.strip() else ''
        if operation == 'active':
            return value if value in ('active', 'inactive', 'failed', 'activating', 'deactivating') else None
        return value if value in ('enabled', 'enabled-runtime', 'disabled', 'static',
                                  'indirect', 'masked', 'masked-runtime') else None

    @staticmethod
    def _write_ksm_sysfs(name, value):
        if name in ('run', 'use_zero_pages'):
            valid = value in ('0', '1')
        elif name in ('pages_to_scan', 'sleep_millisecs'):
            valid = (isinstance(value, STRING_TYPES) and
                     re.match(r'^[1-9][0-9]*\Z', value) is not None)
        else:
            valid = False
        if not valid:
            raise ValueError('KSM_SYSFS_WRITE_INVALID')
        path = '/sys/kernel/mm/ksm/%s' % name
        with open(path, 'w') as stream:
            stream.write(value)
            stream.flush()
        if MemoryOptimizationPlugin._read_ksm_sysfs(name) != value:
            raise RuntimeError('KSM_SYSFS_WRITE_READBACK_MISMATCH:%s' % name)

    def _ksm_proof_policy(self, proof, revision=None):
        """Validate a persisted full native proof and convert it to policy shape."""
        if not isinstance(proof, dict):
            return None
        required = ('run', 'configRevision', 'pages_to_scan', 'sleep_millisecs', 'use_zero_pages')
        if any(not isinstance(proof.get(key), STRING_TYPES) for key in required):
            return None
        if (proof['run'] not in ('0', '1') or
                proof['use_zero_pages'] not in ('0', '1', 'unsupported') or
                not re.match(r'^[1-9][0-9]*\Z', proof['configRevision']) or
                not re.match(r'^[1-9][0-9]*\Z', proof['pages_to_scan']) or
                not re.match(r'^[1-9][0-9]*\Z', proof['sleep_millisecs'])):
            return None
        if revision is None or proof['configRevision'] != str(revision):
            return None
        policy = {'enabled': proof['run'] == '1',
                  'pagesToScan': int(proof['pages_to_scan']),
                  'sleepMillis': int(proof['sleep_millisecs'])}
        if proof['use_zero_pages'] != 'unsupported':
            policy['zeroPagesEnabled'] = proof['use_zero_pages'] == '1'
        return policy

    def _ksm_proof_matches(self, proof, revision):
        """Require every persisted native KSM value to match current sysfs readback."""
        policy = self._ksm_proof_policy(proof, revision)
        if policy is None:
            return False
        current = self._read_ksm_ack()
        if current is None:
            return False
        expected = {
            'run': '1' if policy['enabled'] else '0',
            'configRevision': str(revision),
            'pages_to_scan': str(policy['pagesToScan']),
            'sleep_millisecs': str(policy['sleepMillis']),
            'use_zero_pages': ('1' if policy['zeroPagesEnabled'] else '0')
            if 'zeroPagesEnabled' in policy else 'unsupported',
        }
        return current == expected

    def _reconcile_ksm_proof(self, record, policy, operation_uuid):
        """Select only this apply's verified KSM receipt for read-only reconcile."""
        if (not isinstance(record, dict) or record.get('action') != 'apply' or
                record.get('operationUuid') != operation_uuid or
                record.get('hostUuid') != self._load_host_uuid() or
                record.get('bootId') != self._current_boot_id() or
                not isinstance(record.get('requestHash'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{64}\Z', record.get('requestHash', '')) is None or
                record.get('policyHash') != self._policy_digest(record.get('policy')) or
                (record.get('policy') or {}).get('ksm') != policy):
            return None

        def valid_proof(proof):
            revision = record.get('desiredRevision')
            return (self._ksm_proof_policy(proof, revision) is not None and
                    self._ksm_proof_matches(proof, revision) and
                    self._ksm_readback_matches(policy, revision, proof))

        readback = record.get('readback')
        if not isinstance(readback, dict):
            return None
        if 'ksmReadback' in readback:
            # A present but malformed/contradictory latest receipt is not a
            # missing receipt and must never be hidden by older evidence.
            latest = readback.get('ksmReadback')
            if not valid_proof(latest):
                return None
            evidence = record.get('applyEvidence')
            original = evidence.get('ksmReadback') if isinstance(evidence, dict) else None
            if original is not None and original != latest:
                return None
            return latest

        evidence = record.get('applyEvidence')
        if (not isinstance(evidence, dict) or
                evidence.get('operationUuid') != operation_uuid):
            return None
        original = evidence.get('ksmReadback')
        return original if valid_proof(original) else None

    def _ksm_readback_matches(self, policy, revision=None, previous_ack=None):
        """Read-only proof for a KSM-only journal reconciliation."""
        values = self._read_ksm_ack()
        if values is None or revision is None or values.get('configRevision') != str(revision):
            return False
        if previous_ack is not None:
            if not isinstance(previous_ack, dict):
                return False
            previous_zero = previous_ack.get('use_zero_pages')
            current_zero = values.get('use_zero_pages')
            if (previous_zero not in ('0', '1', 'unsupported') or
                    current_zero not in ('0', '1', 'unsupported') or
                    ((previous_zero == 'unsupported') !=
                     (current_zero == 'unsupported'))):
                return False
        if 'enabled' in policy and values.get('run') != ('1' if policy['enabled'] else '0'):
            return False
        for field, native in (('pagesToScan', 'pages_to_scan'), ('sleepMillis', 'sleep_millisecs')):
            if field in policy and values.get(native) != str(policy[field]):
                return False
        if 'zeroPagesEnabled' in policy:
            if policy['zeroPagesEnabled']:
                return values.get('use_zero_pages') == '1'
            return values.get('use_zero_pages') in ('0', 'unsupported')
        return True

    def _update_operation_record(self, operation_uuid, stage, result):
        """Update a journaled operation without changing its request hash."""
        if not self._valid_identifier(operation_uuid):
            return False
        record = self._load_operation({'operationUuid': operation_uuid}) or {
            'operationUuid': operation_uuid}
        record['stage'] = stage
        record['updatedAt'] = int(time.time() * 1000)
        record['readback'] = result
        try:
            if not os.path.isdir(self.operation_dir):
                os.makedirs(self.operation_dir)
            target = self._operation_path(operation_uuid)
            fd, temp_path = tempfile.mkstemp(prefix='.operation-', dir=self.operation_dir)
            with os.fdopen(fd, 'w') as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temp_path, target)
            return True
        except (IOError, OSError):
            return False

    def _operation_path(self, operation_uuid):
        if not self._valid_identifier(operation_uuid):
            raise ValueError('INVALID_OPERATION_UUID')
        return os.path.join(self.operation_dir, '%s.json' % operation_uuid)

    @staticmethod
    def _valid_identifier(value):
        return (isinstance(value, STRING_TYPES) and 1 <= len(value) <= 160 and
                re.match(r'^[A-Za-z0-9_-]+$', value) is not None)

    def _load_operation(self, command):
        try:
            path = self._operation_path(command.get('operationUuid'))
            with open(path, 'r') as stream:
                return json.load(stream)
        except (IOError, OSError, ValueError):
            return None

    def _operation_file_state(self, operation_uuid):
        """Distinguish an absent journal from corrupt or unreadable evidence."""
        path = self._operation_path(operation_uuid)
        if not os.path.exists(path):
            return 'missing', None
        try:
            with open(path, 'r') as stream:
                return 'present', json.load(stream)
        except ValueError:
            return 'corrupt', None
        except (IOError, OSError):
            return 'unreadable', None

    def _operation_hash(self, command):
        # A service-default capacity side is hashed as requested, before the
        # service resolves it to bytes.
        sides = command.get('defaultCapacitySides') if isinstance(command, dict) else None
        zram = ((command.get('policy') or {}).get('zram')
                if sides and isinstance(command.get('policy'), dict) else None)
        if isinstance(zram, dict):
            command = dict(command, policy=dict(command['policy'], zram=dict(
                zram, **dict((side, None) for side in sides if side in zram))))
        return hashlib.sha256(json.dumps(command, sort_keys=True).encode('utf-8')).hexdigest()

    @staticmethod
    def _policy_mode(command):
        """Return the policy semantics; legacy commands remain effective."""
        if not isinstance(command, dict):
            raise ValueError('invalid policyMode')
        if 'policyMode' not in command:
            return 'effective'
        mode = command.get('policyMode')
        if not isinstance(mode, STRING_TYPES) or mode not in ('delta', 'effective'):
            raise ValueError('invalid policyMode')
        return mode

    def _claim_operation(self, command):
        """Claim one operation UUID, or return its durable prior outcome.

        The kernel releases the writer flock after an Agent crash. The durable
        PREPARING record survives and requires reconciliation rather than a
        replay; a stale directory must not block every future host operation.
        """
        if not os.path.isdir(self.operation_dir):
            os.makedirs(self.operation_dir)
        # One control writer per host, independent of operation UUID.  This
        # fences an old apply against a newer lifecycle/control operation.
        try:
            lock = self._acquire_host_control_lock()
        except (IOError, OSError) as exc:
            if exc.errno in (errno.EAGAIN, errno.EACCES):
                prior = self._load_operation(command)
                if prior and prior.get('requestHash') != self._operation_hash(command):
                    raise ValueError('OPERATION_UUID_REUSE')
                if prior and prior.get('stage') == 'APPLIED' and isinstance(prior.get('readback'), dict):
                    return prior['readback'], False
                if prior and prior.get('stage') == 'DRAINING' and isinstance(prior.get('readback'), dict):
                    return prior['readback'], False
                if prior and prior.get('stage') in (
                    'PREPARING', 'UNKNOWN', 'ACTIVATING', 'RECOVERING',
                    self.FIRST_USE_AUTHORIZING_STAGE):
                    return {'success': False, 'status': 'Unknown', 'state': {},
                            'reasonCode': 'OPERATION_RECONCILE_REQUIRED',
                            'operationUuid': command['operationUuid']}, False
                return None, False
            raise
        prior = self._load_operation(command)
        if prior:
            if prior.get('requestHash') != self._operation_hash(command):
                self._release_operation(lock)
                raise ValueError('OPERATION_UUID_REUSE')
            if prior.get('stage') == 'APPLIED' and isinstance(prior.get('readback'), dict):
                self._release_operation(lock)
                return prior['readback'], False
            if (prior.get('stage') == 'REJECTED' and isinstance(prior.get('readback'), dict) and
                    prior['readback'].get('status') == 'Failed'):
                self._release_operation(lock)
                return prior['readback'], False
            if prior.get('stage') == 'DRAINING' and isinstance(prior.get('readback'), dict):
                self._release_operation(lock)
                return prior['readback'], False
            if prior.get('stage') in ('PREPARING', 'UNKNOWN', 'ACTIVATING', 'RECOVERING',
                                      self.FIRST_USE_AUTHORIZING_STAGE):
                self._release_operation(lock)
                return {'success': False, 'status': 'Unknown', 'state': {},
                        'reasonCode': 'OPERATION_RECONCILE_REQUIRED',
                        'operationUuid': command['operationUuid']}, False
        return lock, True

    def _persist_maintenance_activation_intent(self, command, proof):
        """Durably bind the one-shot Go activation to the current drain."""
        operation_uuid = command['operationUuid']
        record = self._load_operation({'operationUuid': operation_uuid})
        if (not isinstance(record, dict) or record.get('requestHash') != self._operation_hash(command) or
                record.get('stage') != 'PREPARING' or self._get_active_control() != proof.get('drainOperationUuid')):
            return None
        request_id = hashlib.sha256((operation_uuid + ':maintenance-activation').encode('utf-8')).hexdigest()[:32]
        request = OrderedDict([
            ('request_id', request_id),
            ('expected_control_operation_uuid', proof['drainOperationUuid']),
            ('expected_host_boot_id', self._current_boot_id()),
            ('expected_pool_generation', proof['oldPoolGeneration']),
        ])
        proof_bytes = json.dumps(proof, sort_keys=True, separators=(',', ':')).encode('utf-8')
        intent = {'request': request, 'proof': proof,
                  'proofFingerprint': hashlib.sha256(proof_bytes).hexdigest(),
                  'bootId': self._current_boot_id(), 'hostUuid': self._load_host_uuid(),
                  'operationUuid': operation_uuid, 'expectedControlOperationUuid': proof['drainOperationUuid']}
        record['stage'] = 'ACTIVATING'
        record['activationIntent'] = intent
        record['readback'] = {'success': False, 'status': 'Unknown',
                              'state': {'phase': 'ACTIVATING'},
                              'reasonCode': 'MAINTENANCE_ACTIVATION_PENDING',
                              'operationUuid': operation_uuid}
        record['updatedAt'] = int(time.time() * 1000)
        try:
            target = self._operation_path(operation_uuid)
            fd, temp_path = tempfile.mkstemp(prefix='.operation-', dir=self.operation_dir)
            with os.fdopen(fd, 'w') as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temp_path, target)
            directory_fd = os.open(self.operation_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return intent
        except (IOError, OSError):
            logger.warn('unable to persist maintenance activation intent %s', operation_uuid)
            return None

    def _maintenance_activation_observation(self, command, intent):
        """Read-only verification; never reissues an activation after intent."""
        if (not isinstance(intent, dict) or intent.get('operationUuid') != command.get('operationUuid') or
                intent.get('hostUuid') != self._load_host_uuid() or
                intent.get('bootId') != self._current_boot_id()):
            return False, 'MAINTENANCE_ACTIVATION_IDENTITY_MISMATCH', {}
        proof = intent.get('proof')
        request = intent.get('request')
        if not isinstance(proof, dict) or not isinstance(request, dict):
            return False, 'MAINTENANCE_ACTIVATION_INTENT_INVALID', {}
        proof_digest = hashlib.sha256(json.dumps(
            proof, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        drain_uuid = intent.get('expectedControlOperationUuid')
        if (proof_digest != intent.get('proofFingerprint') or
                proof.get('drainOperationUuid') != drain_uuid or
                request.get('expected_control_operation_uuid') != drain_uuid or
                request.get('expected_host_boot_id') != self._current_boot_id() or
                request.get('expected_pool_generation') != proof.get('oldPoolGeneration')):
            return False, 'MAINTENANCE_ACTIVATION_INTENT_INVALID', {}
        drain = self._load_operation({'operationUuid': drain_uuid})
        # As in the recovery proof, only an empty-device activation may follow a
        # drain from before a reboot.
        if (not isinstance(drain, dict) or drain.get('action') != 'drain' or
                drain.get('stage') != 'APPLIED' or
                (drain.get('bootId') != self._current_boot_id() and proof.get('newPoolGeneration'))):
            return False, 'MAINTENANCE_ACTIVATION_DRAIN_HISTORY_UNQUALIFIED', {}
        if self._get_active_control() not in (drain_uuid, command.get('operationUuid')):
            return False, 'MAINTENANCE_ACTIVATION_CONTROL_FENCED', {}
        try:
            activation = self._service_request('lifecycle-activation-state',
                                               {'requestId': request['request_id']})
            native = self._service_request('state', {})
        except Exception:
            return False, 'MAINTENANCE_ACTIVATION_READBACK_UNKNOWN', {}
        receipt = activation.get('receipt') if isinstance(activation, dict) else None
        lifecycle = activation.get('lifecycle') if isinstance(activation, dict) else None
        pool = (native.get('host_zram') or native.get('pool') or {}) if isinstance(native, dict) else {}
        host = native.get('host') if isinstance(native, dict) else None
        pending = native.get('pending_operations') if isinstance(native, dict) else None
        if pending is None and isinstance(native, dict) and 'pending_operations' in native:
            pending = []
        if pending is None and isinstance(native, dict) and 'pending' in native:
            pending = native.get('pending') or []
        # Match Go's struct-order encoding exactly; the journal is key-sorted
        # on disk and must not alter the transport fingerprint.
        wire_request = OrderedDict([
            ('request_id', request.get('request_id')),
            ('expected_control_operation_uuid', request.get('expected_control_operation_uuid')),
            ('expected_host_boot_id', request.get('expected_host_boot_id')),
            ('expected_pool_generation', request.get('expected_pool_generation')),
        ])
        expected_fingerprint = hashlib.sha256(json.dumps(
            wire_request, separators=(',', ':')).encode('utf-8')).hexdigest()
        unpaused_confirmed = (isinstance(receipt, dict) and
                              (receipt.get('stage') == 'UNPAUSED' or
                               (receipt.get('stage') == 'INTENT_DURABLE' and
                                activation.get('unpaused_observed') is True)))
        if (not isinstance(receipt, dict) or receipt.get('request_id') != request.get('request_id') or
                receipt.get('request_fingerprint') != expected_fingerprint or
                receipt.get('expected_control_operation_uuid') != drain_uuid or
                receipt.get('host_boot_id') != self._current_boot_id() or
                receipt.get('pool_generation') != proof.get('oldPoolGeneration')):
            return False, 'MAINTENANCE_ACTIVATION_NOT_CONFIRMED', {'activation': activation}
        if (receipt.get('schema') == 1 and receipt.get('stage') == 'REJECTED' and
                re.match(r'^MAINTENANCE_ACTIVATION_[A-Z0-9_]+$', str(receipt.get('reason_code', ''))) and
                isinstance(lifecycle, dict) and lifecycle.get('paused') is True and
                activation.get('unpaused_observed') is False and
                self._get_active_control() == drain_uuid):
            return False, receipt['reason_code'], {'activation': activation, 'activationRejected': True}
        if not unpaused_confirmed:
            return False, 'MAINTENANCE_ACTIVATION_NOT_CONFIRMED', {'activation': activation}
        if (not isinstance(lifecycle, dict) or lifecycle.get('paused') is not False or
                lifecycle.get('migrationHold') not in (None, {}) or
                not isinstance(pool, dict) or not pool.get('pool_generation') or
                pool.get('quality') != 'native_host_device' or pool.get('reason') or
                pool.get('pool_generation') == proof.get('oldPoolGeneration') or
                not isinstance(host, dict) or host.get('qualified') is not True or
                host.get('safe') is not True or
                native.get('maintenance_blocks_activation') is True or
                not isinstance(pending, list) or pending):
            settling = self._activation_settling_reason(
                lifecycle, pool, host, native, pending, proof.get('oldPoolGeneration'))
            return False, settling or 'MAINTENANCE_ACTIVATION_POOL_NOT_READY', {
                'activation': activation, 'service': native}
        ttl = (command.get('policy') or {}).get('zram', {}).get('hostSampleTtlSeconds', 3)
        # The Agent envelope was just collected, but service qualification
        # may itself be stale. Both native and host observations are required.
        native_observed = native.get('observed_at', native.get('observedAt'))
        host_observed = host.get('observed_at', host.get('observedAt', host.get('timestamp')))
        if (not self._native_observation_is_fresh(native_observed, ttl) or
                not self._native_observation_is_fresh(host_observed, ttl)):
            return False, 'MAINTENANCE_ACTIVATION_NATIVE_STATE_STALE', {
                'activation': activation, 'service': native}
        policy_state = self._read_policy_state(command, command.get('policy') or {})
        if policy_state.get('complete') is not True:
            return False, 'MAINTENANCE_ACTIVATION_POLICY_READBACK_INCOMPLETE', {
                'activation': activation, 'service': native, 'policyReadback': policy_state}
        ksm = (command.get('policy') or {}).get('ksm') or {}
        if ksm and not self._ksm_readback_matches(ksm, command.get('desiredRevision')):
            return False, 'MAINTENANCE_ACTIVATION_KSM_READBACK_INCOMPLETE', {
                'activation': activation, 'service': native, 'policyReadback': policy_state}
        return True, None, {'activation': activation, 'service': native,
                            'poolGeneration': pool.get('pool_generation'),
                            'policyReadback': policy_state}

    @staticmethod
    def _native_observation_is_fresh(value, ttl_seconds, now=None):
        """Check a native Unix-ABI observation timestamp against its TTL."""
        if isinstance(value, dict):
            value = value.get('observed_at', value.get('observedAt', value.get('timestamp')))
        if isinstance(ttl_seconds, bool):
            return False
        try:
            ttl_seconds = float(ttl_seconds)
        except (TypeError, ValueError):
            return False
        if math.isnan(ttl_seconds) or math.isinf(ttl_seconds) or ttl_seconds < 0:
            return False
        try:
            observed = float(value)
        except (TypeError, ValueError):
            if not isinstance(value, STRING_TYPES):
                return False
            try:
                import datetime
                match = re.match(
                    r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)$',
                    value)
                if not match:
                    return False
                base, fraction, zone = match.groups()
                parsed = datetime.datetime.strptime(base, '%Y-%m-%dT%H:%M:%S')
                offset_seconds = 0
                if zone != 'Z':
                    hours, minutes = int(zone[1:3]), int(zone[4:6])
                    if hours > 23 or minutes > 59:
                        return False
                    sign = 1 if zone[0] == '+' else -1
                    offset_seconds = sign * (hours * 3600 + minutes * 60)
                observed = calendar.timegm(parsed.utctimetuple()) - offset_seconds
                if fraction:
                    observed += int(fraction.ljust(9, '0')) / 1000000000.0
            except (TypeError, ValueError, AttributeError):
                return False
        current = time.time() if now is None else now
        if isinstance(current, bool):
            return False
        try:
            current = float(current)
        except (TypeError, ValueError):
            return False
        if (math.isnan(current) or math.isinf(current) or
                math.isnan(observed) or math.isinf(observed)):
            return False
        age = current - observed
        return age >= 0 and age <= ttl_seconds

    def _maintenance_policy_intent_readback(self, command, apply_result):
        """Allow exact durable desired capacity while its pool is paused.

        No other async section is accepted. CPU and tuning are checked through
        regular native readback; only capacity may be pending maintenance.
        """
        if not isinstance(apply_result, dict):
            return {'complete': False, 'reason': 'SERVICE_APPLY_READBACK_INVALID'}
        state = self._read_policy_state(command, command.get('policy') or {})
        if state.get('complete') is True:
            return state
        if apply_result.get('asyncSections') != ['capacity']:
            return state
        sections = state.get('sections') or {}
        capacity = sections.get('capacity')
        desired = capacity.get('desired') if isinstance(capacity, dict) else None
        zram = (command.get('policy') or {}).get('zram') or {}
        expected = {}
        if 'logicalCapacityBytes' in zram:
            expected['logical'] = zram['logicalCapacityBytes']
        if 'ramLimitBytes' in zram:
            expected['physical'] = zram['ramLimitBytes']
        apply_state = str(capacity.get('apply_state', '')).upper() if isinstance(capacity, dict) else ''
        reason = str(capacity.get('reason', '')).upper() if isinstance(capacity, dict) else ''
        # A freshly drained host can report BLOCKED/NATIVE_POOL_UNQUALIFIED
        # until Go opens the replacement pool. It is acceptable only for this
        # precise reason and only as durable desired state; no effective bytes
        # are inferred from it.
        pending = (apply_state in ('PENDING_MAINTENANCE', 'PENDING', 'RECONCILING') or
                   (apply_state == 'BLOCKED' and reason == 'NATIVE_POOL_UNQUALIFIED'))
        section_complete = state.get('sectionComplete') or {}
        others_match = all(value for key, value in section_complete.items()
                           if key != 'capacity')
        desired_matches = isinstance(desired, dict)
        for key, value in expected.items():
            aliases = (key.capitalize(), key + '_resolved_bytes')
            observed = next((desired[name] for name in aliases if name in desired), None)
            if observed != value:
                desired_matches = False
        if expected and pending and desired_matches and others_match:
            state['complete'] = True
            state['capacityDesiredNotEffective'] = True
        return state

    def _await_safe_host_sample(self):
        """Bounded wait for the first fresh safe Host sample; the service still decides."""
        timeout = getattr(self, 'maintenance_activation_host_wait', 8)
        interval = getattr(self, 'maintenance_activation_poll_interval', 0.25)
        clock = getattr(time, 'monotonic', time.time)
        deadline = clock() + timeout
        while True:
            try:
                host = self._service_request('state', {}).get('host') or {}
            except Exception:
                host = {}
            # A young sample stays current until the activation request reaches the service.
            if (host.get('qualified') is True and host.get('safe') is True and
                    self._native_observation_is_fresh(host.get('observed_at'), 1)):
                return True
            if clock() >= deadline:
                return False
            time.sleep(interval)

    def _finish_maintenance_activation(self, command, intent, wait=True):
        timeout = getattr(self, 'maintenance_activation_timeout', 12)
        interval = getattr(self, 'maintenance_activation_poll_interval', 0.25)
        clock = getattr(time, 'monotonic', time.time)
        deadline = clock() + (timeout if wait else 0)
        last = {}
        while True:
            ready, reason, last = self._maintenance_activation_observation(command, intent)
            if last.get('activationRejected') is True:
                return self._finish_rejected_maintenance_activation(command, reason, last)
            if ready:
                # The pool and every requested native section are now proven.
                # Only this commit advances the host control fence.
                self._set_active_control(command['operationUuid'])
                result = {'success': True, 'status': 'Succeeded',
                          'state': {'phase': 'POOL_READY', 'maintenanceActivation': last},
                          'appliedRevision': command.get('desiredRevision'),
                          'operationUuid': command.get('operationUuid')}
                if not self._update_operation_record(command['operationUuid'], 'APPLIED', result):
                    result.update({'success': False, 'status': 'Unknown',
                                   'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                                   'state': {'phase': 'UNKNOWN'}})
                return result
            if not wait or clock() >= deadline:
                return self._pending_maintenance_activation(command.get('operationUuid'), reason, last)
            time.sleep(interval)

    @classmethod
    def _activation_settling_reason(cls, lifecycle, pool, host, native, pending, old_generation):
        """Transient states of an accepted activation that MN should keep polling."""
        if not isinstance(lifecycle, dict) or lifecycle.get('paused') is not False or not isinstance(pool, dict):
            return None
        if pool.get('reason') == cls.POOL_STARTUP_OBSERVATION_REASON:
            # The service creates the pool after its bounded startup observation.
            return 'MAINTENANCE_ACTIVATION_POOL_STARTING'
        pool_ready = (pool.get('pool_generation') and pool.get('quality') == 'native_host_device' and
                      not pool.get('reason') and pool.get('pool_generation') != old_generation and
                      lifecycle.get('migrationHold') in (None, {}) and
                      native.get('maintenance_blocks_activation') is not True and
                      isinstance(pending, list) and not pending)
        if pool_ready and isinstance(host, dict) and not (host.get('qualified') is True and host.get('safe') is True):
            # The new pool exists; only a momentary Host sample is not yet safe.
            return 'MAINTENANCE_ACTIVATION_HOST_SETTLING'
        return None

    @staticmethod
    def _pending_maintenance_activation(operation_uuid, reason, readback):
        # A settling activation stays in progress so MN keeps polling; anything else needs review.
        starting = reason in ('MAINTENANCE_ACTIVATION_POOL_STARTING', 'MAINTENANCE_ACTIVATION_HOST_SETTLING')
        return {'success': starting, 'status': 'Draining' if starting else 'Unknown',
                'reasonCode': reason or 'MAINTENANCE_ACTIVATION_NOT_READY',
                'state': {'phase': 'ACTIVATING', 'readback': readback},
                'operationUuid': operation_uuid}

    def _finish_rejected_maintenance_activation(self, command, reason, readback):
        """Commit only an identity-verified, durable pre-activation rejection."""
        result = {'success': False, 'status': 'Failed', 'reasonCode': reason, 'reason': reason,
                  'state': {'phase': 'FAILED', 'activationRejected': True,
                            'maintenanceActivation': readback},
                  'operationUuid': command.get('operationUuid')}
        if not self._update_operation_record(command['operationUuid'], 'REJECTED', result):
            return {'success': False, 'status': 'Unknown',
                    'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                    'state': {'phase': 'ACTIVATING'}, 'operationUuid': command.get('operationUuid')}
        return result

    def _reconcile_maintenance_activation(self, command, prior):
        operation_uuid = command.get('operationUuid')
        intent = prior.get('activationIntent')
        if (prior.get('action') != 'apply' or prior.get('hostUuid') != self._load_host_uuid() or
                prior.get('bootId') != self._current_boot_id() or not isinstance(intent, dict)):
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'MAINTENANCE_ACTIVATION_INTENT_UNQUALIFIED',
                    'operationUuid': operation_uuid}
        try:
            lock = self._acquire_host_control_lock()
        except (IOError, OSError):
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'OPERATION_CONCURRENT', 'operationUuid': operation_uuid}
        try:
            ready, reason, readback = self._maintenance_activation_observation(
                {'operationUuid': operation_uuid, 'policy': prior.get('policy') or {},
                 'desiredRevision': prior.get('desiredRevision')}, intent)
            if readback.get('activationRejected') is True:
                return self._finish_rejected_maintenance_activation(command, reason, readback)
            if not ready:
                return self._pending_maintenance_activation(operation_uuid, reason, readback)
            self._set_active_control(operation_uuid)
            result = {'success': True, 'status': 'Succeeded',
                      'state': {'phase': 'POOL_READY', 'maintenanceActivation': readback},
                      'appliedRevision': prior.get('desiredRevision'),
                      'operationUuid': operation_uuid}
            if not self._update_operation_record(operation_uuid, 'APPLIED', result):
                return {'success': False, 'status': 'Unknown',
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'state': {'phase': 'UNKNOWN'}, 'operationUuid': operation_uuid}
            return result
        finally:
            self._release_operation(lock)

    def _recovery_failure(self, command, reason, phase='UNKNOWN'):
        return {'success': False, 'status': 'Unknown', 'appliedRevision': None,
                'reasonCode': reason, 'operationUuid': command.get('operationUuid'),
                'state': {'phase': phase}}

    def _recovery_not_issued(self, command, reason):
        recovery = command.get('recovery') or {}
        boot_id = self._current_boot_id()
        host_uuid = self._load_host_uuid()
        proof = {'schemaVersion': 1, 'hostUuid': host_uuid, 'bootId': boot_id,
                 'recoveryOperationUuid': command.get('operationUuid'),
                 'unresolvedOperationUuid': command.get('expectedControlOperationUuid'),
                 'drainControlOperationUuid': recovery.get('drainControlOperationUuid'),
                 'expectedPoolGeneration': recovery.get('expectedPoolGeneration'),
                 'notIssued': True}
        return {'success': False, 'status': 'Failed', 'appliedRevision': None,
                'reasonCode': reason, 'operationUuid': command.get('operationUuid'),
                'bootId': boot_id,
                'state': {'phase': 'RECOVERY_NOT_ISSUED', 'bootId': boot_id,
                          'recoveryRejectionProof': proof}}

    def _valid_recovery_not_issued(self, command, prior):
        result = prior.get('readback') if isinstance(prior, dict) else None
        state = result.get('state') if isinstance(result, dict) else None
        proof = state.get('recoveryRejectionProof') if isinstance(state, dict) else None
        recovery = command.get('recovery') or {}
        reconcile_existing = command.get('action') == 'reconcile'
        if reconcile_existing:
            request_hash = prior.get('requestHash') if isinstance(prior, dict) else None
            request_matches = (isinstance(prior, dict) and
                               isinstance(request_hash, STRING_TYPES) and
                               re.match(r'^[0-9a-f]{64}$', request_hash) is not None and
                               command.get('hostUuid') == self._load_host_uuid() and
                               command.get('policy') == {} and
                               prior.get('scope') == command.get('scope') == 'Host' and
                               prior.get('resourceUuid') == command.get('resourceUuid') ==
                               self._load_host_uuid() and
                               recovery.get('confirmed') is True and
                               recovery.get('expectedHostBootId') == self._current_boot_id() and
                               prior.get('expectedControlOperationUuid') ==
                               command.get('expectedControlOperationUuid') and
                               prior.get('desiredRevision') == command.get('desiredRevision'))
        else:
            request_matches = prior.get('requestHash') == self._operation_hash(command)
        return (isinstance(prior, dict) and prior.get('action') == 'recoverUncertain' and
                prior.get('stage') == 'REJECTED' and
                prior.get('hostUuid') == self._load_host_uuid() and
                prior.get('bootId') == self._current_boot_id() and
                request_matches and
                all(key not in prior for key in ('recoveryIntent', 'recoveryAttempt',
                                                 'recoveryReceipt', 'recoveryResult')) and
                isinstance(result, dict) and
                isinstance(state, dict) and
                result.get('success') is False and result.get('status') == 'Failed' and
                result.get('appliedRevision') is None and
                result.get('operationUuid') == command.get('operationUuid') and
                result.get('bootId') == self._current_boot_id() and
                state.get('phase') == 'RECOVERY_NOT_ISSUED' and
                isinstance(proof, dict) and type(proof.get('schemaVersion')) is int and
                proof['schemaVersion'] == 1 and
                proof.get('hostUuid') == self._load_host_uuid() and
                proof.get('bootId') == self._current_boot_id() and
                proof.get('recoveryOperationUuid') == command.get('operationUuid') and
                proof.get('unresolvedOperationUuid') == command.get('expectedControlOperationUuid') and
                proof.get('drainControlOperationUuid') == recovery.get('drainControlOperationUuid') and
                proof.get('expectedPoolGeneration') == recovery.get('expectedPoolGeneration') and
                proof.get('notIssued') is True)

    def _seal_rejected_recovery(self, command):
        """Seal only a manager-retained pre-claim rejection, never an unknown write.

        The original Agent had no journal for an invalid envelope. Bind the
        manager's immutable request hash to a durable tombstone under the same
        Host writer lock used by recovery, so a delayed old request cannot run.
        """
        failure = self._recovery_failure(command, 'RECOVERY_REJECTION_PROOF_UNQUALIFIED')
        recovery = command.get('recovery')
        request_hash = command.get('recoveryRequestHash')
        host = self._load_host_uuid()
        boot = self._current_boot_id()
        submitted = command.get('taskSubmittedAt')
        boot_epoch = self._boot_epoch_millis()
        if (command.get('action') != 'reconcile' or command.get('scope') != 'Host' or
                not host or command.get('hostUuid') != host or not boot or
                command.get('bootId') != boot or command.get('policy') != {} or
                isinstance(command.get('desiredRevision'), bool) or
                not isinstance(command.get('desiredRevision'), INTEGER_TYPES) or
                command['desiredRevision'] < 1 or
                not self._valid_identifier(command.get('operationUuid')) or
                not self._valid_identifier(command.get('expectedControlOperationUuid')) or
                command['operationUuid'] == command['expectedControlOperationUuid'] or
                not isinstance(request_hash, STRING_TYPES) or
                re.match(r'^[0-9a-f]{64}$', request_hash) is None or
                not isinstance(recovery, dict) or
                set(recovery) != {'expectedHostBootId', 'expectedPoolGeneration', 'confirmed'} or
                recovery.get('confirmed') is not True or recovery.get('expectedHostBootId') != boot or
                not isinstance(recovery.get('expectedPoolGeneration'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{64}$', recovery['expectedPoolGeneration']) is None or
                isinstance(submitted, bool) or not isinstance(submitted, INTEGER_TYPES) or
                not isinstance(boot_epoch, INTEGER_TYPES) or
                not boot_epoch <= submitted <= int(time.time() * 1000)):
            return failure
        sealed = {key: command[key] for key in (
            'hostUuid', 'scope', 'operationUuid', 'expectedControlOperationUuid',
            'recovery', 'recoveryRequestHash', 'taskSubmittedAt')}
        sealed.update(action='recoverUncertain', policy={}, desiredRevision=command.get('desiredRevision'))
        lock = None
        try:
            lock = self._acquire_host_control_lock()
            path = self._operation_path(command['operationUuid'])
            if os.path.islink(path):
                return failure
            kind, prior = self._operation_file_state(command['operationUuid'])
            if kind == 'present':
                if self._valid_recovery_not_issued(sealed, prior):
                    return prior['readback']
                return failure
            if (kind != 'missing' or command.get('reconcileAction') != 'seal-rejected-recovery' or
                    command.get('classification') != 'RECOVERY_REQUEST_INVALID'):
                return failure
            old_uuid = command['expectedControlOperationUuid']
            old_path = self._operation_path(old_uuid)
            if (os.path.islink(self.active_control_path) or
                    os.path.islink(old_path) or os.path.realpath(old_path) != old_path):
                return failure
            old_kind, old = self._operation_file_state(old_uuid)
            if (old_kind != 'present' or not isinstance(old, dict) or
                    old.get('operationUuid') != old_uuid or old.get('hostUuid') != host or
                    old.get('bootId') != boot or old.get('stage') != 'UNKNOWN' or
                    old.get('action') != 'apply' or old.get('scope') != 'Host' or
                    old.get('desiredRevision') != command.get('desiredRevision') or
                    not isinstance(old.get('requestHash'), STRING_TYPES) or
                    re.match(r'^[0-9a-f]{64}$', old['requestHash']) is None):
                return failure
            old_hash = self._operation_hash(old)
            active = self._get_active_control()
            if active:
                anchor_path = self._operation_path(active)
                if os.path.islink(anchor_path) or os.path.realpath(anchor_path) != anchor_path:
                    return failure
            anchor = self._load_operation({'operationUuid': active}) if active else None
            if (not isinstance(anchor, dict) or active in (old_uuid, command['operationUuid']) or
                    anchor.get('operationUuid') != active or anchor.get('hostUuid') != host or
                    anchor.get('bootId') != boot or anchor.get('stage') != 'APPLIED' or
                    anchor.get('action') not in ('apply', 'clearOverride') or
                    (anchor.get('readback') or {}).get('status') != 'Succeeded'):
                return failure
            live = self._service_request('monitor-state', {})
            operations = self._readonly_query('operations', {'hostUuid': host, 'limit': 1})
            cq = operations.get('cq') or {}
            if ('pending_operations' not in live or live['pending_operations'] not in (None, []) or
                    type(cq.get('C')) is not int or cq['C'] != 0 or
                    type(cq.get('Q')) is not int or cq['Q'] != 0 or
                    (live.get('host_zram') or {}).get('pool_generation') != recovery['expectedPoolGeneration'] or
                    self._current_boot_id() != boot or self._get_active_control() != active or
                    self._operation_hash(self._load_operation({'operationUuid': old_uuid})) != old_hash):
                return failure
            result = self._recovery_not_issued(sealed, 'RECOVERY_REQUEST_INVALID')
            result['state']['recoveryRejectionProof']['managerRequestHash'] = request_hash
            if not self._record_operation(sealed, 'REJECTED', result):
                return self._recovery_failure(command, 'RECOVERY_REJECTION_JOURNAL_UNAVAILABLE')
            return result
        except Exception:
            return failure
        finally:
            self._release_operation(lock)

    @staticmethod
    def _activation_request_fingerprint(request):
        wire = OrderedDict([
            ('request_id', request.get('request_id')),
            ('expected_control_operation_uuid', request.get('expected_control_operation_uuid')),
            ('expected_host_boot_id', request.get('expected_host_boot_id')),
            ('expected_pool_generation', request.get('expected_pool_generation')),
        ])
        return hashlib.sha256(json.dumps(wire, separators=(',', ':')).encode('utf-8')).hexdigest()

    @staticmethod
    def _activation_receipt_absent(observation):
        """Accept only the Go API's explicit receipt-absent wire responses."""
        return (isinstance(observation, dict) and
                ((observation.get('_http_status') == 200 and
                  'receipt' in observation and observation.get('receipt') is None) or
                 (observation.get('_http_status') == 404 and
                  observation.get('error') == 'MAINTENANCE_ACTIVATION_NOT_FOUND' and
                  observation.get('receipt') is None)))

    def _validate_uncertain_activation(self, old_uuid, drain_uuid, expected_boot,
                                       expected_generation):
        old_state, old = self._operation_file_state(old_uuid)
        if old_state != 'present' or not isinstance(old, dict):
            return None, 'RECOVERY_OLD_JOURNAL_UNAVAILABLE'
        if (old.get('operationUuid') != old_uuid or old.get('action') != 'apply' or
                old.get('stage') != 'ACTIVATING' or
                old.get('hostUuid') != self._load_host_uuid() or
                old.get('bootId') != expected_boot or self._current_boot_id() != expected_boot):
            return None, 'RECOVERY_OLD_ACTIVATION_UNQUALIFIED'
        intent = old.get('activationIntent')
        request = intent.get('request') if isinstance(intent, dict) else None
        proof = intent.get('proof') if isinstance(intent, dict) else None
        if not isinstance(request, dict) or not isinstance(proof, dict):
            return None, 'RECOVERY_OLD_ACTIVATION_UNQUALIFIED'
        proof_hash = hashlib.sha256(json.dumps(
            proof, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        fingerprint = self._activation_request_fingerprint(request)
        if (intent.get('operationUuid') != old_uuid or
                intent.get('hostUuid') != self._load_host_uuid() or
                intent.get('bootId') != expected_boot or
                proof_hash != intent.get('proofFingerprint') or
                proof.get('drainOperationUuid') != drain_uuid or
                proof.get('oldPoolGeneration') != expected_generation or
                request.get('expected_control_operation_uuid') != drain_uuid or
                request.get('expected_host_boot_id') != expected_boot or
                request.get('expected_pool_generation') != expected_generation or
                not isinstance(request.get('request_id'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{32}$', request.get('request_id', '')) is None):
            return None, 'RECOVERY_OLD_ACTIVATION_UNQUALIFIED'
        drain = self._load_operation({'operationUuid': drain_uuid})
        if (not isinstance(drain, dict) or drain.get('action') != 'drain' or
                drain.get('stage') != 'APPLIED' or drain.get('hostUuid') != self._load_host_uuid() or
                drain.get('bootId') != expected_boot):
            return None, 'RECOVERY_DRAIN_HISTORY_UNQUALIFIED'
        active = self._get_active_control()
        if active not in (old_uuid, drain_uuid):
            return None, 'RECOVERY_CONTROL_FENCE_MISMATCH'
        maintenance_proof = dict(proof)
        if (maintenance_proof.get('maintenanceReady') is not True or
                maintenance_proof.get('maintenanceArchived') is not True or
                maintenance_proof.get('activeOperations') != 0 or
                maintenance_proof.get('oldPoolOwnershipAbsent') is not True or
                maintenance_proof.get('originalDeviceInactive') is not True or
                maintenance_proof.get('readyForInitialization') is not True):
            return None, 'RECOVERY_MAINTENANCE_PROOF_UNQUALIFIED'
        if not self._maintenance_recovery_proof(
                {'maintenanceProof': maintenance_proof}, expected_active_control=active):
            return None, 'RECOVERY_MAINTENANCE_PROOF_UNQUALIFIED'
        try:
            # The current Go API expresses an absent receipt as a typed 404,
            # not a successful response containing receipt:null. Inspect the
            # read-only transport envelope directly so only that exact 404 is
            # treated as absence; all other errors remain unknown.
            observation = self.service_call(
                'lifecycle-activation-state', {'requestId': request['request_id']})
        except Exception:
            return None, 'RECOVERY_ACTIVATION_OBSERVATION_UNKNOWN'
        if not self._activation_receipt_absent(observation):
            return None, 'RECOVERY_OLD_ACTIVATION_RECEIPT_PRESENT_OR_UNKNOWN'
        return {'proof': maintenance_proof, 'request': request,
                'fingerprint': fingerprint}, None

    def _persist_recovery_intent(self, command, intent):
        record = self._load_operation(command)
        if not isinstance(record, dict) or record.get('stage') != 'PREPARING':
            return False
        record['stage'] = 'RECOVERING'
        record['recoveryIntent'] = intent
        reason = ('POLICY_CPU_RESTORE_PENDING' if intent.get('kind') == 'finalCpuGate'
                  else 'PARTIAL_SERVICE_APPLY_PENDING'
                  if intent.get('kind') == 'partialServiceApply'
                  else 'ACTIVATION_RETIREMENT_PENDING')
        record['readback'] = self._recovery_failure(command, reason, 'RECOVERING')
        record['updatedAt'] = int(time.time() * 1000)
        try:
            target = self._operation_path(command['operationUuid'])
            fd, temp_path = tempfile.mkstemp(prefix='.operation-', dir=self.operation_dir)
            with os.fdopen(fd, 'w') as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temp_path, target)
            directory_fd = os.open(self.operation_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return True
        except (IOError, OSError):
            logger.warn('unable to persist uncertain recovery intent')
            return False

    @staticmethod
    def _retirement_matches(result, intent):
        if not isinstance(result, dict) or result.get('_http_status') != 200:
            return False
        expected = {
            'schema': 1, 'requestId': intent.get('requestId'),
            'oldActivationRequestId': intent.get('oldActivationRequestId'),
            'oldActivationFingerprint': intent.get('oldActivationFingerprint'),
            'drainControlOperationUuid': intent.get('drainControlOperationUuid'),
            'bootId': intent.get('expectedBootId'),
            'poolGeneration': intent.get('expectedPoolGeneration'),
            'reason': 'USER_CONFIRMED_UNCERTAIN_RECOVERY', 'stage': 'RETIRED',
            'nativeObserved': 'ZERO_INACTIVE_NO_BACKING'}
        return all(result.get(key) == value for key, value in expected.items())

    def _finish_uncertain_recovery(self, command, intent, retirement):
        try:
            live = self._service_request('monitor-state', {})
        except Exception:
            return self._recovery_failure(command, 'RECOVERY_NATIVE_STATE_UNKNOWN', 'RECOVERING')
        pending = live.get('pending_operations', live.get('pending'))
        if pending is None and ('pending_operations' in live or 'pending' in live):
            pending = []
        lifecycle = live.get('lifecycle')
        pool = live.get('host_zram') or live.get('pool') or {}
        # The service's public status schema does not expose its internal
        # Runtime.activeOps map. The RETIRED receipt is issued only after Go
        # has checked len(activeOps)==0; do not invent an Agent-side field.
        if (not isinstance(pending, list) or pending or
                not isinstance(lifecycle, dict) or lifecycle.get('paused') is not True or
                lifecycle.get('migrationHold') not in (None, {}) or
                (pool and not self._is_uninitialized_pool_snapshot(pool))):
            return self._recovery_failure(command, 'RECOVERY_NATIVE_STATE_NOT_QUIESCENT', 'RECOVERING')
        proof = intent.get('maintenanceProof')
        active_control = self._get_active_control()
        drain_uuid = intent.get('drainControlOperationUuid')
        # A crash can occur after the durable Go RETIRED receipt and local
        # fence advancement, but before the recovery journal is finalized.
        # Accept exactly that intermediate fence; no unrelated control may
        # be promoted to recovery authority.
        if active_control not in (intent.get('priorActiveControl'), drain_uuid):
            return self._recovery_failure(command, 'RECOVERY_CONTROL_FENCE_MISMATCH', 'RECOVERING')
        if not self._maintenance_recovery_proof(
                {'maintenanceProof': proof}, live_state=live,
                expected_active_control=active_control):
            return self._recovery_failure(command, 'RECOVERY_MAINTENANCE_STATE_CHANGED', 'RECOVERING')
        if (self._current_boot_id() != intent.get('expectedBootId') or
                self._load_host_uuid() != intent.get('hostUuid') or
                not self._retirement_matches(retirement, intent)):
            return self._recovery_failure(command, 'RECOVERY_RETIREMENT_RECEIPT_MISMATCH', 'RECOVERING')
        self._set_active_control(drain_uuid)
        maintenance_proof = dict(proof)
        maintenance_proof.update({
            'maintenanceReady': True,
            'maintenanceArchived': True,
            'executorExited': True,
            'drainOperationUuid': drain_uuid,
            'oldPoolGeneration': intent.get('expectedPoolGeneration'),
            'activeOperations': 0,
            'readyForInitialization': True,
            'originalDeviceInactive': True,
            'oldPoolOwnershipAbsent': True,
        })
        result = {'success': True, 'status': 'Succeeded', 'appliedRevision': None,
                  'operationUuid': command.get('operationUuid'),
                  'bootId': intent.get('expectedBootId'),
                  'state': {'phase': 'UNCERTAIN_RECOVERED',
                            'bootId': intent.get('expectedBootId'),
                            'lastConfirmedOperationUuid': drain_uuid,
                            'recoveryProof': {
                                'schemaVersion': 1, 'hostUuid': intent.get('hostUuid'),
                                'bootId': intent.get('expectedBootId'),
                                'recoveryOperationUuid': command.get('operationUuid'),
                                'unresolvedOperationUuid': intent.get('unresolvedOperationUuid'),
                                'drainControlOperationUuid': drain_uuid,
                                'oldActivationRequestId': intent.get('oldActivationRequestId'),
                                'oldActivationFingerprint': intent.get('oldActivationFingerprint'),
                                'expectedPoolGeneration': intent.get('expectedPoolGeneration'),
                                'retired': True, 'originalOutcome': 'Unknown'},
                            'maintenanceProof': maintenance_proof,
                            'retirementReceipt': {key: value for key, value in retirement.items()
                                                  if key != '_http_status'}}}
        if not self._update_operation_record(command['operationUuid'], 'APPLIED', result):
            return self._recovery_failure(command, 'OPERATION_JOURNAL_UNAVAILABLE')
        return result

    def _reconcile_uncertain_recovery(self, command, prior):
        if prior.get('stage') == 'REJECTED':
            if self._valid_recovery_not_issued(command, prior):
                return prior['readback']
            return self._recovery_failure(command, 'RECOVERY_REJECTION_PROOF_UNQUALIFIED')
        intent = prior.get('recoveryIntent')
        if intent is None:
            recovery = command.get('recovery')
            evidence = prior.get('readback')
            evidence_state = evidence.get('state') if isinstance(evidence, dict) else None
            reason_code = evidence.get('reasonCode') if isinstance(evidence, dict) else None
            request_hash = prior.get('requestHash')
            exact_unissued_candidate = (
                command.get('action') == 'reconcile' and command.get('policy') == {} and
                isinstance(recovery, dict) and recovery.get('confirmed') is True and
                set(prior) == {'action', 'bootId', 'desiredRevision',
                               'expectedControlOperationUuid', 'hostUuid', 'operationUuid',
                               'policy', 'policyHash', 'readback', 'requestHash',
                               'resourceUuid', 'scope', 'stage', 'updatedAt'} and
                prior.get('action') == 'recoverUncertain' and prior.get('stage') == 'UNKNOWN' and
                prior.get('operationUuid') == command.get('operationUuid') and
                prior.get('scope') == command.get('scope') == 'Host' and
                prior.get('resourceUuid') == command.get('resourceUuid') == self._load_host_uuid() and
                prior.get('hostUuid') == command.get('hostUuid') == self._load_host_uuid() and
                prior.get('bootId') == self._current_boot_id() and
                prior.get('desiredRevision') == command.get('desiredRevision') and
                isinstance(prior.get('desiredRevision'), INTEGER_TYPES) and
                not isinstance(prior.get('desiredRevision'), bool) and
                prior.get('expectedControlOperationUuid') ==
                command.get('expectedControlOperationUuid') and
                prior.get('policy') == {} and
                prior.get('policyHash') == self._policy_digest({}) and
                isinstance(command.get('recoveryRequestHash'), STRING_TYPES) and
                re.match(r'^[0-9a-f]{64}$', command.get('recoveryRequestHash', '')) is not None and
                recovery.get('expectedHostBootId') == self._current_boot_id() and
                recovery.get('expectedPoolGeneration') and
                isinstance(request_hash, STRING_TYPES) and
                re.match(r'^[0-9a-f]{64}$', request_hash) is not None and
                all(key not in prior for key in ('recoveryIntent', 'recoveryAttempt',
                                                 'recoveryReceipt', 'recoveryResult')) and
                isinstance(evidence, dict) and evidence.get('success') is False and
                set(evidence) == {'success', 'status', 'appliedRevision', 'reasonCode',
                                  'operationUuid', 'state'} and
                evidence.get('appliedRevision') is None and
                evidence.get('status') == 'Unknown' and
                evidence.get('operationUuid') == prior.get('operationUuid') and
                isinstance(evidence_state, dict) and set(evidence_state) == {'phase'} and
                evidence_state.get('phase') == 'UNKNOWN' and
                reason_code == 'RECOVERY_PARTIAL_APPLY_NOT_PROVEN')
            if not exact_unissued_candidate:
                return self._recovery_failure(command, 'RECOVERY_INTENT_UNQUALIFIED')
            try:
                lock = self._acquire_host_control_lock()
            except (IOError, OSError):
                return self._recovery_failure(command, 'OPERATION_CONCURRENT')
            try:
                latest_state, latest = self._operation_file_state(command.get('operationUuid'))
                if (latest_state != 'present' or not isinstance(latest, dict) or
                        self._operation_hash(latest) != self._operation_hash(prior) or
                        latest.get('requestHash') != request_hash or
                        latest.get('stage') != 'UNKNOWN' or
                        any(key in latest for key in ('recoveryIntent', 'recoveryAttempt',
                                                      'recoveryReceipt', 'recoveryResult'))):
                    return self._recovery_failure(command, 'RECOVERY_INTENT_UNQUALIFIED')
                return self._recover_uncertain_partial_service_policy(command, prior=latest)
            finally:
                self._release_operation(lock)
        if (prior.get('action') != 'recoverUncertain' or
                prior.get('hostUuid') != self._load_host_uuid() or
                prior.get('bootId') != self._current_boot_id() or
                not isinstance(intent, dict) or
                intent.get('recoveryOperationUuid') != command.get('operationUuid')):
            return self._recovery_failure(command, 'RECOVERY_INTENT_UNQUALIFIED')
        try:
            lock = self._acquire_host_control_lock()
        except (IOError, OSError):
            return self._recovery_failure(command, 'OPERATION_CONCURRENT')
        try:
            if intent.get('kind') == 'finalCpuGate':
                return self._recover_uncertain_cpu_policy(command, prior=prior)
            if intent.get('kind') == 'partialServiceApply':
                return self._recover_uncertain_partial_service_policy(command, prior=prior)
            try:
                receipt = self._service_request('lifecycle-activation-retirement-state', intent)
            except Exception:
                return self._recovery_failure(command, 'RECOVERY_RETIREMENT_OBSERVATION_UNKNOWN', 'RECOVERING')
            if not self._retirement_matches(receipt, intent):
                return self._recovery_failure(command, 'RECOVERY_RETIREMENT_NOT_CONFIRMED', 'RECOVERING')
            return self._finish_uncertain_recovery(command, intent, receipt)
        finally:
            self._release_operation(lock)

    def _completed_uncertain_recovery(self, command):
        """Return a same-request completed receipt only after local proof checks."""
        record = self._load_operation(command)
        if (not isinstance(record, dict) or record.get('action') != 'recoverUncertain' or
                record.get('stage') != 'APPLIED' or
                record.get('requestHash') != self._operation_hash(command) or
                record.get('operationUuid') != command.get('operationUuid') or
                record.get('hostUuid') != self._load_host_uuid() or
                record.get('bootId') != self._current_boot_id()):
            return None
        result = record.get('readback')
        state = result.get('state') if isinstance(result, dict) else None
        intent = record.get('recoveryIntent')
        recovery_proof = state.get('recoveryProof') if isinstance(state, dict) else None
        retirement_receipt = state.get('retirementReceipt') if isinstance(state, dict) else None
        if isinstance(intent, dict) and intent.get('kind') in ('finalCpuGate', 'partialServiceApply'):
            if (isinstance(state, dict) and isinstance(recovery_proof, dict) and
                    result.get('success') is True and result.get('status') == 'Succeeded' and
                    state.get('phase') == 'POLICY_RECOVERED' and
                    result.get('operationUuid') == command.get('operationUuid') and
                    result.get('bootId') == self._current_boot_id() and
                    state.get('lastConfirmedOperationUuid') == command.get('operationUuid') and
                    recovery_proof.get('recoveryOperationUuid') == command.get('operationUuid') and
                    recovery_proof.get('unresolvedOperationUuid') == intent.get('unresolvedOperationUuid') and
                    recovery_proof.get('originalRequestHash') == intent.get('originalRequestHash') and
                    state.get('cpuReceipt') == intent.get('cpuReceipt') and
                    isinstance(intent.get('cpuReceipt'), dict) and
                    (intent.get('kind') != 'partialServiceApply' or
                     (recovery_proof.get('kind') == 'partialServiceApply' and
                      recovery_proof.get('anchorJournalHash') == intent.get('anchorJournalHash') and
                      recovery_proof.get('tuningCommand') == self._service_payload(
                          'apply', intent.get('tuningCommand') or {}) and
                      recovery_proof.get('tuningPayloadSha256') == intent.get('tuningPayloadSha256') and
                      recovery_proof.get('tuningReceipt') == intent.get('tuningReceipt') and
                      recovery_proof.get('tuningReadback') == intent.get('tuningReadback') and
                      recovery_proof.get('originalKsmReadback') == intent.get('originalKsmReadback')))):
                if intent.get('kind') == 'partialServiceApply':
                    try:
                        validation_command = dict(command)
                        validation_command['expectedControlOperationUuid'] = command.get('operationUuid')
                        self._validate_final_cpu_no_ksm_control(
                            validation_command, record, command.get('operationUuid'))
                    except Exception:
                        return None
                return result
            return None
        if (not isinstance(state, dict) or not isinstance(intent, dict) or
                not isinstance(recovery_proof, dict) or
                not isinstance(retirement_receipt, dict) or
                result.get('success') is not True or result.get('status') != 'Succeeded' or
                result.get('bootId') != self._current_boot_id() or
                state.get('phase') != 'UNCERTAIN_RECOVERED' or
                state.get('lastConfirmedOperationUuid') != intent.get('drainControlOperationUuid') or
                state.get('bootId') != self._current_boot_id() or
                recovery_proof.get('recoveryOperationUuid') != command.get('operationUuid')):
            return None
        receipt = dict(retirement_receipt, _http_status=200)
        if not self._retirement_matches(receipt, intent):
            return None
        return result

    def _recover_uncertain_activation(self, command):
        """Retire a lost activation only after explicit same-boot drain proof."""
        recovery = command.get('recovery')
        required_command_fields = {
            'hostUuid', 'scope', 'action', 'operationUuid',
            'expectedControlOperationUuid', 'policy', 'recovery'}
        # Keep the actual common MemoryOptimizationManager command envelope:
        # recovery is Host scoped, but dispatch still carries standard task,
        # target-generation and communication-budget fields. KVMHost also
        # appends transport addons after the Manager serializes its command.
        optional_command_fields = {
            'resourceUuid', 'desiredRevision', 'targetSnapshotGeneration',
            'expectedInstanceGeneration', 'communication', 'kvmHostAddons'}
        if (not required_command_fields.issubset(set(command)) or
                set(command) - required_command_fields - optional_command_fields or
                command.get('scope') != 'Host' or command.get('policy') != {} or
                command.get('resourceUuid') not in (None, command.get('hostUuid')) or
                command.get('expectedInstanceGeneration') is not None or
                not isinstance(recovery, dict) or
                set(recovery) not in ({'expectedHostBootId', 'expectedPoolGeneration',
                                       'drainControlOperationUuid', 'confirmed'},
                                      {'expectedHostBootId', 'expectedPoolGeneration', 'confirmed'}) or
                recovery.get('confirmed') is not True):
            return self._recovery_failure(command, 'RECOVERY_REQUEST_INVALID')
        old_uuid = command.get('expectedControlOperationUuid')
        drain_uuid = recovery.get('drainControlOperationUuid')
        expected_boot = recovery.get('expectedHostBootId')
        expected_generation = recovery.get('expectedPoolGeneration')
        if (not isinstance(command.get('operationUuid'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{32}$', command.get('operationUuid', '')) is None or
                not isinstance(old_uuid, STRING_TYPES) or
                re.match(r'^[0-9a-f]{32}$', old_uuid or '') is None or
                ('drainControlOperationUuid' in recovery and
                 (not isinstance(drain_uuid, STRING_TYPES) or
                  re.match(r'^[0-9a-f]{32}$', drain_uuid or '') is None)) or
                not isinstance(expected_boot, STRING_TYPES) or
                not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', expected_boot) or
                not isinstance(expected_generation, STRING_TYPES) or
                not re.match(r'^[0-9a-f]{64}$', expected_generation)):
            return self._recovery_failure(command, 'RECOVERY_REQUEST_INVALID')
        try:
            self._operation_request(command)
            if command.get('hostUuid') != self._load_host_uuid():
                return self._recovery_failure(command, 'HOST_IDENTITY_UNKNOWN')
            lock, claimed = self._claim_operation(command)
        except Exception:
            return self._recovery_failure(command, 'RECOVERY_OPERATION_CLAIM_FAILED')
        if not claimed or lock is None:
            completed = self._completed_uncertain_recovery(command)
            if completed is not None:
                return completed
            prior = self._load_operation(command)
            if (isinstance(prior, dict) and prior.get('stage') == 'REJECTED' and
                    self._valid_recovery_not_issued(command, prior)):
                return prior['readback']
            return self._recovery_failure(command, 'OPERATION_RECONCILE_REQUIRED')
        try:
            if not self._record_operation(command, 'PREPARING'):
                return self._recovery_failure(command, 'OPERATION_JOURNAL_UNAVAILABLE')
            if drain_uuid is None:
                return self._recover_uncertain_cpu_policy(command, issue=True)
            try:
                evidence, reason = self._validate_uncertain_activation(
                    old_uuid, drain_uuid, expected_boot, expected_generation)
            except Exception:
                evidence, reason = None, 'RECOVERY_PREFLIGHT_UNKNOWN'
            if evidence is None:
                result = self._recovery_not_issued(command, reason)
                if not self._record_operation(command, 'REJECTED', result):
                    return self._recovery_failure(
                        command, 'RECOVERY_REJECTION_JOURNAL_UNAVAILABLE')
                return result
            # The Go child request is the same unique operation UUID that the
            # MN claimed and journaled, so recovery is idempotent across layers.
            request_id = command['operationUuid']
            intent = {'recoveryOperationUuid': command['operationUuid'],
                      'unresolvedOperationUuid': old_uuid,
                      'hostUuid': self._load_host_uuid(), 'expectedBootId': expected_boot,
                      'expectedPoolGeneration': expected_generation,
                      'drainControlOperationUuid': drain_uuid,
                      'oldActivationRequestId': evidence['request']['request_id'],
                      'oldActivationFingerprint': evidence['fingerprint'],
                      'maintenanceProof': evidence['proof'],
                      'priorActiveControl': self._get_active_control(),
                      'requestId': request_id}
            if not self._persist_recovery_intent(command, intent):
                return self._recovery_failure(command, 'OPERATION_JOURNAL_UNAVAILABLE')
            post = {'requestId': request_id,
                    'oldActivationRequestId': intent['oldActivationRequestId'],
                    'oldActivationFingerprint': intent['oldActivationFingerprint'],
                    'drainControlOperationUuid': drain_uuid,
                    'expectedBootId': expected_boot,
                    'expectedPoolGeneration': expected_generation,
                    'reason': 'USER_CONFIRMED_UNCERTAIN_RECOVERY'}
            try:
                receipt = self._service_request('lifecycle-activation-retirement', post)
            except Exception:
                return self._recovery_failure(command, 'RECOVERY_RETIREMENT_RESULT_UNKNOWN', 'RECOVERING')
            if not self._retirement_matches(receipt, intent):
                return self._recovery_failure(command, 'RECOVERY_RETIREMENT_RECEIPT_MISMATCH', 'RECOVERING')
            return self._finish_uncertain_recovery(command, intent, receipt)
        finally:
            self._release_operation(lock)

    def _recover_uncertain_partial_service_policy(self, command, prior=None, issue=False):
        """Finish the one proven KSM+CPU partial apply without replaying KSM.

        The original apply receipt remains immutable.  Its typed tuning
        pre-write rejection, same-boot active anchor, current KSM ACK, CPU
        guard and prepared-pool generation must all agree before a durable
        recovery intent can authorize the original tuning request ID.
        """
        recovery = command.get('recovery') or {}
        intent = prior.get('recoveryIntent') if isinstance(prior, dict) else None
        dispatched = isinstance(intent, dict)
        may_issue = issue and not dispatched
        old_uuid = (intent.get('unresolvedOperationUuid') if dispatched
                    else command.get('expectedControlOperationUuid'))
        boot = intent.get('expectedBootId') if dispatched else recovery.get('expectedHostBootId')
        generation = (intent.get('expectedPoolGeneration') if dispatched
                      else recovery.get('expectedPoolGeneration'))
        recovery_uuid = command.get('operationUuid')

        def unknown(reason):
            result = self._recovery_failure(command, reason,
                                            'RECOVERING' if dispatched else 'UNKNOWN')
            if not dispatched:
                self._update_operation_record(recovery_uuid, 'UNKNOWN', result)
            else:
                self._update_operation_record(recovery_uuid, 'RECOVERING', result)
            return result

        try:
            old_state, old = self._operation_file_state(old_uuid)
            if (old_state != 'present' or not isinstance(old, dict) or
                    old.get('operationUuid') != old_uuid or old.get('stage') != 'UNKNOWN' or
                    old.get('action') != 'apply' or old.get('scope') != 'Host' or
                    old.get('hostUuid') != self._load_host_uuid() or old.get('bootId') != boot or
                    boot != self._current_boot_id() or old.get('policyMode') != 'delta' or
                    command.get('desiredRevision') != old.get('desiredRevision') or
                    any(key in old for key in ('firstZramUse', 'activationIntent', 'maintenanceIntent',
                                               'maintenanceProof', 'mixedClearEvidence'))):
                return unknown('RECOVERY_OLD_POLICY_UNQUALIFIED')
            policy = old.get('policy')
            if (not isinstance(policy, dict) or
                    set(policy) - {'schemaVersion', 'ksm', 'writeback'} or
                    type(policy.get('schemaVersion')) is not int or policy.get('schemaVersion') != 1 or
                    not isinstance(policy.get('ksm'), dict) or
                    set(policy.get('ksm', {})) != {'enabled', 'zeroPagesEnabled'} or
                    policy['ksm'].get('enabled') is not True or
                    policy['ksm'].get('zeroPagesEnabled') is not True or
                    not isinstance(policy.get('writeback'), dict) or
                    set(policy.get('writeback', {})) != {'enabled'} or
                    policy['writeback'].get('enabled') is not False or
                    old.get('policyHash') != self._policy_digest(policy) or
                    not isinstance(old.get('requestHash'), STRING_TYPES) or
                    re.match(r'^[0-9a-f]{64}$', old.get('requestHash', '')) is None):
                return unknown('RECOVERY_OLD_POLICY_UNQUALIFIED')
            old_hash = self._operation_hash(old)
            evidence = old.get('applyEvidence')
            old_readback = old.get('readback')
            state = evidence.get('state') if isinstance(evidence, dict) else None
            sections = state.get('sections') if isinstance(state, dict) else None
            ksm_ack = evidence.get('ksmReadback') if isinstance(evidence, dict) else None
            if (not isinstance(evidence, dict) or not isinstance(old_readback, dict) or
                    not self._strict_service_match(evidence, old_readback) or
                    evidence.get('success') is not False or evidence.get('status') != 'Unknown' or
                    evidence.get('reasonCode') not in ('SERVICE_APPLY_FAILED', 'MEMORY_RESULT_UNKNOWN') or
                    evidence.get('reason') != 'SERVICE_APPLY_FAILED:TUNING_REQUIRES_QUIESCENT_EXECUTOR' or
                    state.get('lastStep') != 'tuning_apply_and_vm_scope_commit' or
                    state.get('sequence') != ['cpu_guard_written', 'cpu_guard_verified_off'] or
                    state.get('notAttempted') != ['remainingPolicyWrites', 'finalCpuGate'] or
                    not isinstance(sections, dict) or
                    set(sections) != {'cpuBefore', 'cpuGuard', 'cpuGuardReadback'} or
                    not isinstance(ksm_ack, dict) or
                    old_readback.get('ksmReadback') != ksm_ack):
                return unknown('RECOVERY_PARTIAL_APPLY_NOT_PROVEN')
            ksm_ack_policy = self._ksm_proof_policy(ksm_ack, old.get('desiredRevision'))
            if (ksm_ack_policy is None or
                    not self._ksm_proof_matches(ksm_ack, old.get('desiredRevision')) or
                    any(key not in ksm_ack_policy or
                        not self._strict_service_match(ksm_ack_policy[key], value)
                        for key, value in policy['ksm'].items())):
                return unknown('RECOVERY_ORIGINAL_KSM_ACK_UNKNOWN')
            original_cpu_before = self._strict_service_success(
                'host-cpu-state', sections.get('cpuBefore'))
            original_guard = self._strict_service_success('host-cpu', sections.get('cpuGuard'))
            original_guard_read = self._strict_service_success(
                'host-cpu-state', sections.get('cpuGuardReadback'))
            cpu_fields = ('efficiency_enabled', 'idle_cpu_threshold_percent',
                          'idle_duration_seconds')
            cpu_target = {key: original_cpu_before[key] for key in cpu_fields}
            held = dict(cpu_target, efficiency_enabled=False,
                        revision=original_cpu_before['revision'] + 1)
            if (original_cpu_before.get('efficiency_enabled') is not True or
                    original_guard.get('request_id') != self._derived_service_request_id(old_uuid, 'cpu-hold') or
                    original_guard.get('revision') != original_cpu_before.get('revision') + 1 or
                    not self._strict_service_match(original_guard, held) or
                    not self._strict_service_match(original_guard_read, held)):
                return unknown('RECOVERY_ORIGINAL_CPU_GUARD_UNQUALIFIED')

            observed_active_uuid = self._get_active_control()
            active_uuid = (intent.get('priorActiveControl') if dispatched else
                           observed_active_uuid)
            if (not self._valid_identifier(active_uuid) or active_uuid in (old_uuid, recovery_uuid) or
                    command.get('expectedControlOperationUuid') != old_uuid or
                    recovery.get('expectedHostBootId') != boot or
                    recovery.get('expectedPoolGeneration') != generation or
                    (not dispatched and observed_active_uuid != active_uuid) or
                    (dispatched and observed_active_uuid not in (active_uuid, recovery_uuid))):
                return unknown('RECOVERY_CONTROL_FENCE_MISMATCH')
            anchor_path = self._operation_path(active_uuid)
            if os.path.islink(anchor_path) or os.path.realpath(anchor_path) != anchor_path:
                return unknown('RECOVERY_CONTROL_FENCE_MISMATCH')
            anchor_state, anchor = self._operation_file_state(active_uuid)
            if (anchor_state != 'present' or not isinstance(anchor, dict) or
                    anchor.get('operationUuid') != active_uuid or anchor.get('stage') != 'APPLIED' or
                    anchor.get('action') != 'apply' or anchor.get('scope') != 'Host' or
                    anchor.get('hostUuid') != self._load_host_uuid() or anchor.get('bootId') != boot or
                    type(anchor.get('desiredRevision')) is not int or
                    anchor.get('desiredRevision') >= old.get('desiredRevision') or
                    anchor.get('policyHash') != self._policy_digest(anchor.get('policy') or {}) or
                    not isinstance(anchor.get('requestHash'), STRING_TYPES) or
                    re.match(r'^[0-9a-f]{64}$', anchor.get('requestHash', '')) is None):
                return unknown('RECOVERY_CONTROL_FENCE_MISMATCH')
            anchor_readback = anchor.get('readback')
            anchor_evidence = anchor.get('applyEvidence')
            anchor_state_value = (anchor_readback or {}).get('state') if isinstance(anchor_readback, dict) else None
            anchor_sections = anchor_state_value.get('sections') if isinstance(anchor_state_value, dict) else None
            if (not isinstance(anchor_readback, dict) or
                    not self._strict_service_match(anchor_readback, anchor_evidence) or
                    anchor_readback.get('success') is not True or anchor_readback.get('status') != 'Succeeded' or
                    anchor_readback.get('operationUuid') != active_uuid or
                    anchor_readback.get('appliedRevision') != anchor.get('desiredRevision') or
                    not isinstance(anchor_state_value, dict) or anchor_state_value.get('phase') != 'READBACK' or
                    anchor_state_value.get('sectionComplete') != {'cpu': True, 'tuning': True} or
                    not isinstance(anchor_sections, dict) or
                    set(anchor_sections) != {'cpu', 'cpuBefore', 'cpuGuard', 'cpuGuardReadback',
                                             'cpuReadback', 'tuning', 'tuningReadback'}):
                return unknown('RECOVERY_ANCHOR_RECEIPT_UNQUALIFIED')
            anchor_policy = anchor.get('policy')
            anchor_wb = anchor_policy.get('writeback') if isinstance(anchor_policy, dict) else None
            if (not isinstance(anchor_wb, dict) or anchor_wb.get('enabled') is not True or
                    not self._valid_identifier(anchor_wb.get('backendResourceUuid')) or
                    type(anchor_wb.get('backendCapacityBytes')) is not int or
                    anchor_wb.get('backendCapacityBytes') <= 0):
                return unknown('RECOVERY_ANCHOR_BACKEND_MISMATCH')
            anchor_tuning = self._strict_service_success('apply', anchor_sections.get('tuning'))
            anchor_tuning_read = self._strict_service_success(
                'tuning-state', anchor_sections.get('tuningReadback'))
            if (anchor_tuning.get('agent_request_id') != self._derived_service_request_id(active_uuid, 'tuning') or
                    type(anchor_tuning.get('revision')) is not int or
                    anchor_tuning.get('revision') != anchor_tuning_read.get('revision') or
                    not self._strict_service_match(anchor_tuning.get('settings'),
                                                   anchor_tuning_read.get('settings')) or
                    not self._strict_service_match(anchor_tuning_read.get('settings'),
                                                   anchor_tuning.get('settings')) or
                    (anchor_tuning.get('settings', {}).get('writeback') or {}).get('enabled') is not True):
                return unknown('RECOVERY_ANCHOR_TUNING_UNQUALIFIED')
            anchor_cpu_before = self._strict_service_success(
                'host-cpu-state', anchor_sections.get('cpuBefore'))
            anchor_cpu_guard = self._strict_service_success('host-cpu', anchor_sections.get('cpuGuard'))
            anchor_cpu_guard_read = self._strict_service_success(
                'host-cpu-state', anchor_sections.get('cpuGuardReadback'))
            anchor_cpu = self._strict_service_success('host-cpu', anchor_sections.get('cpu'))
            anchor_cpu_read = self._strict_service_success(
                'host-cpu-state', anchor_sections.get('cpuReadback'))
            anchor_cpu_fields = ('efficiency_enabled', 'idle_cpu_threshold_percent',
                                 'idle_duration_seconds')
            anchor_guard_target = {key: anchor_cpu_before[key] for key in anchor_cpu_fields}
            anchor_guard_target['efficiency_enabled'] = False
            anchor_guard_target['revision'] = anchor_cpu_before['revision'] + 1
            anchor_cpu_target = {key: anchor_cpu_before[key] for key in anchor_cpu_fields}
            anchor_cpu_target['revision'] = anchor_cpu_before['revision'] + 2
            if (anchor_cpu_before.get('efficiency_enabled') is not True or
                    anchor_cpu_guard.get('request_id') != self._derived_service_request_id(active_uuid, 'cpu-hold') or
                    anchor_cpu_guard.get('revision') != anchor_cpu_before.get('revision') + 1 or
                    anchor_cpu_guard.get('efficiency_enabled') is not False or
                    not self._strict_service_match(anchor_cpu_guard, anchor_guard_target) or
                    not self._strict_service_match(anchor_cpu_guard_read, anchor_guard_target) or
                    anchor_cpu.get('request_id') != self._derived_service_request_id(active_uuid, 'cpu') or
                    anchor_cpu.get('agent_expected_revision') != anchor_cpu_guard.get('revision') or
                    anchor_cpu.get('revision') != anchor_cpu_guard.get('revision') + 1 or
                    anchor_cpu.get('efficiency_enabled') is not True or
                    not self._strict_service_match(anchor_cpu, anchor_cpu_target) or
                    not self._strict_service_match(anchor_cpu_read, anchor_cpu_target) or
                    anchor_cpu_read.get('revision') != original_cpu_before.get('revision') or
                    not self._strict_service_match(anchor_cpu_read, original_cpu_before)):
                return unknown('RECOVERY_ANCHOR_CPU_UNQUALIFIED')

            if dispatched:
                if (intent.get('kind') != 'partialServiceApply' or
                        intent.get('hostUuid') != self._load_host_uuid() or
                        intent.get('expectedBootId') != boot or
                        intent.get('unresolvedOperationUuid') != old_uuid or
                        intent.get('recoveryOperationUuid') != recovery_uuid or
                        intent.get('originalJournalHash') != old_hash or
                        intent.get('originalRequestHash') != old.get('requestHash') or
                        intent.get('priorActiveControl') != active_uuid or
                        intent.get('anchorJournalHash') != self._operation_hash(anchor)):
                    return unknown('RECOVERY_INTENT_UNQUALIFIED')
                before_tuning = intent.get('tuningBefore')
                tuning_command = intent.get('tuningCommand')
            else:
                before_tuning = dict(anchor_tuning_read)
                tuning_command = {'operationUuid': self._derived_service_request_id(old_uuid, 'tuning'),
                                  'expectedRevision': before_tuning.get('revision'), 'policy': policy}
                self._merge_tuning_settings(tuning_command, before_tuning)
            before_tuning = self._strict_service_success('tuning-state', before_tuning)
            target_tuning = tuning_command.get('nativeSettings')
            body = self._service_payload('apply', tuning_command)
            expected_tuning_command = {'policy': policy}
            self._merge_tuning_settings(expected_tuning_command, before_tuning)
            body_hash = hashlib.sha256(json.dumps(
                body, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
            if (tuning_command.get('operationUuid') != self._derived_service_request_id(old_uuid, 'tuning') or
                    tuning_command.get('expectedRevision') != before_tuning.get('revision') or
                    not self._strict_service_match(before_tuning.get('settings'), anchor_tuning_read.get('settings')) or
                    not self._strict_service_match(target_tuning,
                                                   expected_tuning_command.get('nativeSettings')) or
                    (dispatched and (intent.get('tuningPayloadSha256') != body_hash or
                                     intent.get('tuningCommand') != tuning_command))):
                return unknown('RECOVERY_TUNING_INTENT_MISMATCH')
            vm_management = target_tuning.get('vm_management') if isinstance(target_tuning, dict) else None
            if (not isinstance(vm_management, dict) or
                    vm_management.get('mode') != 'all_running' or
                    vm_management.get('vm_uuids') != []):
                return unknown('RECOVERY_VM_SHARD_REPLAY_UNSAFE')

            transport = command.get('communication') or {}
            if not isinstance(transport, dict):
                return unknown('RECOVERY_COMMUNICATION_BUDGET_INVALID')
            communication_seconds = transport.get(
                'communicationSeconds', self.communication_seconds)
            if (isinstance(communication_seconds, bool) or
                    not isinstance(communication_seconds, (int, float)) or communication_seconds <= 0):
                return unknown('RECOVERY_COMMUNICATION_BUDGET_INVALID')
            if dispatched:
                deadline = intent.get('tuningDeadlineMonotime')
                if (isinstance(deadline, bool) or
                        not isinstance(deadline, (int, float)) or deadline <= 0):
                    return unknown('RECOVERY_TUNING_DEADLINE_UNKNOWN')
            else:
                deadline = linux.monotime() + communication_seconds

            tuning_receipt = intent.get('tuningReceipt') if dispatched else None
            tuning_receipt_readback = intent.get('tuningReadback') if dispatched else None
            if tuning_receipt is not None:
                if (not isinstance(tuning_receipt, dict) or
                        not isinstance(tuning_receipt_readback, dict) or
                        tuning_receipt.get('agent_request_id') != tuning_command.get('operationUuid') or
                        tuning_receipt.get('agent_expected_revision') != tuning_command.get('expectedRevision') or
                        tuning_receipt.get('revision') != before_tuning.get('revision') + 1 or
                        not self._strict_service_match(tuning_receipt.get('settings'), target_tuning) or
                        tuning_receipt_readback.get('revision') != tuning_receipt.get('revision') or
                        not self._strict_service_match(tuning_receipt_readback.get('settings'), target_tuning)):
                    return unknown('RECOVERY_TUNING_RECEIPT_UNCONFIRMED')
            current_ack = self._read_ksm_ack()
            current_cpu = self._strict_service_success(
                'host-cpu-state', self._service_request('host-cpu-state', {}))
            current_tuning = self._strict_service_success(
                'tuning-state', self._service_request('tuning-state', {}))
            live = self._service_request('monitor-state', {})
            expected_tuning = (tuning_receipt.get('settings') if tuning_receipt is not None
                               else before_tuning.get('settings'))
            expected_tuning_revision = (tuning_receipt.get('revision') if tuning_receipt is not None
                                        else before_tuning.get('revision'))
            cpu_receipt = intent.get('cpuReceipt') if dispatched else None
            expected_cpu = (cpu_target if isinstance(cpu_receipt, dict) else held)
            if (current_ack != ksm_ack or not self._strict_service_match(current_cpu, expected_cpu) or
                    current_tuning.get('revision') != expected_tuning_revision or
                    not self._strict_service_match(current_tuning.get('settings'), expected_tuning) or
                    (live.get('host_zram') or {}).get('pool_generation') != generation or
                    (live.get('lifecycle') or {}).get('paused') is not False or
                    (live.get('lifecycle') or {}).get('migrationHold') not in (None, {})):
                return unknown('RECOVERY_PARTIAL_STATE_CHANGED')
            operations = self._readonly_query('operations', {
                'hostUuid': self._load_host_uuid(), 'limit': 1})
            cq = operations.get('cq') or {}
            if (type(cq.get('C')) is not int or cq.get('C') != 0 or
                    type(cq.get('Q')) is not int or cq.get('Q') != 0 or
                    'pending_operations' not in live or live.get('pending_operations') not in (None, [])):
                return unknown('RECOVERY_NATIVE_STATE_NOT_QUIESCENT')

            if not dispatched and command.get('action') == 'reconcile':
                result = self._recovery_not_issued(
                    command, 'RECOVERY_NOT_ISSUED')
                if not self._update_operation_record(recovery_uuid, 'REJECTED', result):
                    return unknown('OPERATION_JOURNAL_UNAVAILABLE')
                return result

            if not dispatched:
                intent = {'kind': 'partialServiceApply', 'hostUuid': self._load_host_uuid(),
                          'expectedBootId': boot, 'expectedPoolGeneration': generation,
                          'recoveryOperationUuid': recovery_uuid, 'unresolvedOperationUuid': old_uuid,
                          'priorActiveControl': active_uuid, 'originalJournalHash': old_hash,
                          'originalRequestHash': old.get('requestHash'),
                          'originalPolicyHash': old.get('policyHash'),
                          'desiredRevision': old.get('desiredRevision'),
                          'anchorOperationUuid': active_uuid,
                          'anchorJournalHash': self._operation_hash(anchor),
                          'anchorRequestHash': anchor.get('requestHash'),
                          'anchorPolicyHash': anchor.get('policyHash'),
                          'anchorDesiredRevision': anchor.get('desiredRevision'),
                          'originalKsmReadback': dict(ksm_ack),
                          'cpuBefore': dict(original_cpu_before),
                          'cpuGuard': dict(original_guard),
                          'cpuGuardReadback': dict(original_guard_read),
                          'tuningBefore': dict(before_tuning),
                          'tuningCommand': tuning_command,
                          'tuningPayloadSha256': body_hash,
                          'tuningDeadlineMonotime': deadline,
                          'tuningAttempted': False,
                          'cpuAttempted': False}
                if not self._persist_recovery_intent(command, intent):
                    return unknown('OPERATION_JOURNAL_UNAVAILABLE')
                dispatched = True
            receipt = intent.get('tuningReceipt')
            if not isinstance(receipt, dict):
                if not may_issue or intent.get('tuningAttempted'):
                    return unknown('RECOVERY_TUNING_RESULT_UNKNOWN')
                intent['tuningAttempted'] = True
                recorded = self._load_operation(command)
                recorded['recoveryIntent'] = intent
                if not self._write_operation_record(recorded):
                    return unknown('OPERATION_JOURNAL_UNAVAILABLE')
                while True:
                    remaining = deadline - linux.monotime()
                    if remaining <= 0:
                        return unknown('RECOVERY_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                    attempt_receipts = []
                    attempt_transport = dict(transport)
                    attempt_transport['communicationSeconds'] = remaining
                    try:
                        receipt = self._strict_service_success(
                            'apply', self._service_request(
                                'apply', tuning_command, receipt_sink=attempt_receipts.append,
                                communication=attempt_transport))
                        break
                    except Exception:
                        rejection = attempt_receipts[-1] if attempt_receipts else None
                        if (not isinstance(rejection, dict) or
                                type(rejection.get('_http_status')) is not int or
                                rejection.get('_http_status') != 409 or
                                rejection.get('error') != 'TUNING_REQUIRES_QUIESCENT_EXECUTOR' or
                                ('success' in rejection and rejection.get('success') is not False)):
                            intent['tuningOutcomeUnknown'] = True
                            recorded = self._load_operation(command)
                            recorded['recoveryIntent'] = intent
                            self._write_operation_record(recorded)
                            return unknown('RECOVERY_TUNING_RESULT_UNKNOWN')
                        vm_management = body.get('settings', {}).get('vm_management', {})
                        vm_uuids = vm_management.get('vm_uuids') if isinstance(vm_management, dict) else None
                        if isinstance(vm_uuids, list) and vm_uuids:
                            return unknown('RECOVERY_VM_SHARD_REPLAY_UNSAFE')
                        while True:
                            remaining = deadline - linux.monotime()
                            if remaining <= 0:
                                return unknown('RECOVERY_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                            poll_transport = dict(transport)
                            poll_transport['communicationSeconds'] = remaining
                            try:
                                operations = self._readonly_query('operations', {
                                    'hostUuid': self._load_host_uuid(), 'limit': 1,
                                    'communication': poll_transport})
                            except Exception:
                                return unknown('RECOVERY_TUNING_QUEUE_STATE_UNKNOWN')
                            cq = operations.get('cq') if isinstance(operations, dict) else None
                            if (not isinstance(cq, dict) or type(cq.get('C')) is not int or
                                    type(cq.get('Q')) is not int):
                                return unknown('RECOVERY_TUNING_QUEUE_STATE_UNKNOWN')
                            remaining = deadline - linux.monotime()
                            if remaining <= 0:
                                return unknown('RECOVERY_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                            poll_transport = dict(transport)
                            poll_transport['communicationSeconds'] = remaining
                            try:
                                monitor = self._service_request('monitor-state', {},
                                                                communication=poll_transport)
                            except Exception:
                                return unknown('RECOVERY_TUNING_PENDING_STATE_UNKNOWN')
                            if ('pending_operations' not in monitor or
                                    (monitor.get('pending_operations') not in (None, []) and
                                     not isinstance(monitor.get('pending_operations'), list))):
                                return unknown('RECOVERY_TUNING_PENDING_STATE_UNKNOWN')
                            pending = monitor.get('pending_operations') not in (None, [])
                            if cq['C'] == 0 and cq['Q'] == 0 and not pending:
                                break
                            remaining = deadline - linux.monotime()
                            if remaining <= 0:
                                return unknown('RECOVERY_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                            time.sleep(min(0.1, remaining))
                receipt = dict(receipt, agent_request_id=tuning_command['operationUuid'],
                               agent_expected_revision=tuning_command['expectedRevision'])
                if (receipt.get('revision') != before_tuning.get('revision') + 1 or
                        not self._strict_service_match(receipt.get('settings'), target_tuning)):
                    intent['tuningOutcomeUnknown'] = True
                    recorded = self._load_operation(command)
                    recorded['recoveryIntent'] = intent
                    self._write_operation_record(recorded)
                    return unknown('RECOVERY_TUNING_RECEIPT_UNCONFIRMED')
                intent['tuningReceipt'] = receipt
                recorded = self._load_operation(command)
                recorded['recoveryIntent'] = intent
                if not self._write_operation_record(recorded):
                    return unknown('OPERATION_JOURNAL_UNAVAILABLE')
            elif (receipt.get('agent_request_id') != tuning_command.get('operationUuid') or
                  receipt.get('agent_expected_revision') != tuning_command.get('expectedRevision') or
                  receipt.get('revision') != before_tuning.get('revision') + 1 or
                  not self._strict_service_match(receipt.get('settings'), target_tuning)):
                return unknown('RECOVERY_TUNING_RECEIPT_UNCONFIRMED')
            tuning_read = self._strict_service_success(
                'tuning-state', self._service_request('tuning-state', {}))
            if (tuning_read.get('revision') != receipt.get('revision') or
                    not self._strict_service_match(tuning_read.get('settings'), target_tuning) or
                    not self._strict_service_match(receipt.get('settings'), tuning_read.get('settings'))):
                return unknown('RECOVERY_TUNING_READBACK_UNCONFIRMED')
            intent['tuningReadback'] = tuning_read
            recorded = self._load_operation(command)
            recorded['recoveryIntent'] = intent
            if not self._write_operation_record(recorded):
                return unknown('OPERATION_JOURNAL_UNAVAILABLE')

            cpu_receipt = intent.get('cpuReceipt')
            if not isinstance(cpu_receipt, dict):
                if not may_issue or intent.get('cpuAttempted'):
                    return unknown('RECOVERY_CPU_RESULT_UNKNOWN')
                intent['cpuAttempted'] = True
                recorded = self._load_operation(command)
                recorded['recoveryIntent'] = intent
                if not self._write_operation_record(recorded):
                    return unknown('OPERATION_JOURNAL_UNAVAILABLE')
                cpu_command = {'operationUuid': self._derived_service_request_id(old_uuid, 'cpu'),
                               'cpuExpectedRevision': current_cpu['revision'],
                               'nativeCpuState': current_cpu,
                               'policy': {'zram': {'enabled': cpu_target['efficiency_enabled'],
                                   'cpuThresholdPercent': cpu_target['idle_cpu_threshold_percent'],
                                   'cpuHoldSeconds': cpu_target['idle_duration_seconds']}}}
                try:
                    cpu_receipt = self._strict_service_success(
                        'host-cpu', self._service_request('host-cpu', cpu_command))
                except Exception:
                    return unknown('RECOVERY_CPU_RESULT_UNKNOWN')
                cpu_receipt = dict(cpu_receipt,
                                   agent_expected_revision=current_cpu['revision'],
                                   agent_desired_enabled=cpu_target['efficiency_enabled'],
                                   agent_desired_threshold_percent=cpu_target['idle_cpu_threshold_percent'],
                                   agent_desired_duration_seconds=cpu_target['idle_duration_seconds'])
                if (cpu_receipt.get('request_id') != cpu_command['operationUuid'] or
                        cpu_receipt.get('revision') != current_cpu['revision'] + 1 or
                        not self._strict_service_match(cpu_receipt, cpu_target)):
                    return unknown('RECOVERY_CPU_RECEIPT_UNCONFIRMED')
                intent['cpuReceipt'] = cpu_receipt
                recorded = self._load_operation(command)
                recorded['recoveryIntent'] = intent
                if not self._write_operation_record(recorded):
                    return unknown('OPERATION_JOURNAL_UNAVAILABLE')
            else:
                cpu_receipt = self._strict_service_success('host-cpu', cpu_receipt)
                if (cpu_receipt.get('request_id') != self._derived_service_request_id(old_uuid, 'cpu') or
                        cpu_receipt.get('revision') != cpu_receipt.get('agent_expected_revision', -1) + 1 or
                        not self._strict_service_match(cpu_receipt, cpu_target)):
                    return unknown('RECOVERY_CPU_RECEIPT_UNCONFIRMED')
            final_cpu = self._strict_service_success(
                'host-cpu-state', self._service_request('host-cpu-state', {}))
            if (final_cpu.get('revision') != cpu_receipt.get('revision') or
                    not self._strict_service_match(final_cpu, cpu_target) or
                    self._current_boot_id() != boot or
                    self._get_active_control() not in (active_uuid, recovery_uuid) or
                    self._operation_hash(self._load_operation({'operationUuid': old_uuid})) != old_hash):
                return unknown('RECOVERY_FINAL_CPU_READBACK_UNCONFIRMED')
            proof = {'schemaVersion': 1, 'kind': 'partialServiceApply',
                     'hostUuid': self._load_host_uuid(), 'bootId': boot,
                     'recoveryOperationUuid': recovery_uuid, 'unresolvedOperationUuid': old_uuid,
                     'expectedPoolGeneration': generation, 'originalRequestHash': old.get('requestHash'),
                     'originalJournalHash': old_hash,
                     'originalPolicyHash': old.get('policyHash'), 'originalDesiredRevision': old.get('desiredRevision'),
                     'originalKsmReadback': dict(ksm_ack),
                     'anchorOperationUuid': active_uuid,
                     'anchorJournalHash': self._operation_hash(anchor),
                     'anchorRequestHash': anchor.get('requestHash'),
                     'anchorPolicyHash': anchor.get('policyHash'),
                     'anchorDesiredRevision': anchor.get('desiredRevision'),
                     'tuningBefore': before_tuning, 'tuningCommand': body,
                     'tuningRequestId': tuning_command.get('operationUuid'),
                     'tuningExpectedRevision': tuning_command.get('expectedRevision'),
                     'tuningRevision': receipt.get('revision'),
                     'tuningPayloadSha256': body_hash, 'tuningReceipt': receipt,
                     'tuningReadback': tuning_read,
                     'cpuGuard': original_guard, 'cpuGuardReadback': original_guard_read,
                     'cpuExpectedRevision': original_guard.get('revision'),
                     'finalCpuRestored': True, 'originalOutcome': 'Unknown'}
            result = {'success': True, 'status': 'Succeeded', 'operationUuid': recovery_uuid,
                      'bootId': boot, 'sampleTime': int(time.time() * 1000),
                      'appliedRevision': old.get('desiredRevision'), 'state': {
                          'phase': 'POLICY_RECOVERED', 'bootId': boot,
                          'lastConfirmedOperationUuid': recovery_uuid,
                          'lastConfirmedAppliedRevision': old.get('desiredRevision'),
                          'recoveryProof': proof, 'cpuBefore': original_cpu_before,
                          'cpuReceipt': cpu_receipt, 'cpuReadback': final_cpu}}
            if (not self._valid_identifier(active_uuid) or
                    self._get_active_control() not in (active_uuid, recovery_uuid) or
                    self._operation_hash(self._load_operation({'operationUuid': old_uuid})) != old_hash):
                return unknown('RECOVERY_CONTROL_FENCE_MISMATCH')
            self._set_active_control(recovery_uuid)
            if not self._update_operation_record(recovery_uuid, 'APPLIED', result):
                return unknown('OPERATION_JOURNAL_UNAVAILABLE')
            return result
        except Exception:
            return unknown('RECOVERY_PARTIAL_PROOF_UNKNOWN')

    def _recover_uncertain_cpu_policy(self, command, prior=None, issue=False):
        """Finish only a proven tuning-only apply's missing final CPU gate.

        The caller holds the existing Host writer lock. The original journal
        is immutable; a new recovery owns its intent and receipt. A lost PUT
        receipt stays Unknown: a GET with equal values cannot prove ownership.
        """
        intent = prior.get('recoveryIntent') if isinstance(prior, dict) else None
        dispatched = isinstance(intent, dict)
        try:
            recovery = command.get('recovery') or {}
            old_uuid = (intent.get('unresolvedOperationUuid') if dispatched
                        else command.get('expectedControlOperationUuid'))
            boot = intent.get('expectedBootId') if dispatched else recovery.get('expectedHostBootId')
            generation = (intent.get('expectedPoolGeneration') if dispatched
                          else recovery.get('expectedPoolGeneration'))
            old_state, old = self._operation_file_state(old_uuid)
            old_policy = old.get('policy') if isinstance(old, dict) else None
            if isinstance(old_policy, dict) and old_policy.get('ksm'):
                return self._recover_uncertain_partial_service_policy(
                    command, prior=prior, issue=issue)
            if (old_state != 'present' or not isinstance(old, dict) or
                    old.get('operationUuid') != old_uuid or old.get('action') != 'apply' or
                    old.get('scope') != 'Host' or old.get('stage') != 'UNKNOWN' or
                    old.get('policyMode') != 'delta' or old.get('hostUuid') != self._load_host_uuid() or
                    old.get('bootId') != boot or boot != self._current_boot_id() or
                    any(key in old for key in ('firstZramUse', 'activationIntent', 'maintenanceProof',
                                               'mixedClearEvidence'))):
                raise ValueError('RECOVERY_OLD_POLICY_UNQUALIFIED')
            policy = old.get('policy') or {}
            zram, wb = policy.get('zram') or {}, policy.get('writeback') or {}
            if (policy.get('ksm') or not (zram or wb) or 'enabled' in wb or
                    any(key in zram for key in ('logicalCapacityBytes', 'ramLimitBytes', 'enabled',
                                                'cpuThresholdPercent', 'cpuHoldSeconds')) or
                    old.get('policyHash') != self._policy_digest(policy) or
                    not isinstance(old.get('requestHash'), STRING_TYPES) or
                    re.match(r'^[0-9a-f]{64}$', old['requestHash']) is None):
                raise ValueError('RECOVERY_OLD_POLICY_UNQUALIFIED')
            original_hash = self._operation_hash(old)
            evidence = old.get('applyEvidence') or {}
            state = evidence.get('state') or {}
            sections = state.get('sections') or {}
            if (evidence.get('status') != 'Unknown' or
                    state.get('lastStep') != 'tuning_target_readback' or
                    state.get('sequence') != ['cpu_guard_written', 'cpu_guard_verified_off', 'tuning_apply_returned'] or
                    'finalCpuGate' not in state.get('notAttempted', []) or
                    any(key in sections for key in ('cpu', 'capacity', 'capacityReadback'))):
                raise ValueError('RECOVERY_FINAL_CPU_NOT_PROVEN_UNISSUED')
            before = self._strict_service_success('host-cpu-state', sections.get('cpuBefore'))
            guard = self._strict_service_success('host-cpu', sections.get('cpuGuard'))
            guard_read = self._strict_service_success('host-cpu-state', sections.get('cpuGuardReadback'))
            tuning = self._strict_service_success('apply', sections.get('tuning'))
            tuning_read = self._strict_service_success('tuning-state', sections.get('tuningReadback'))
            desired_tuning = {'policy': policy}
            self._merge_tuning_settings(desired_tuning, tuning)
            cpu_keys = ('efficiency_enabled', 'idle_cpu_threshold_percent', 'idle_duration_seconds')
            target = {key: before[key] for key in cpu_keys}
            held = dict(target, efficiency_enabled=False, revision=before['revision'] + 1)
            if (before['efficiency_enabled'] is not True or
                    guard.get('request_id') != self._derived_service_request_id(old_uuid, 'cpu-hold') or
                    not self._strict_service_match(guard, held) or not self._strict_service_match(guard_read, held) or
                    tuning.get('agent_request_id') != self._derived_service_request_id(old_uuid, 'tuning') or
                    not self._strict_service_match(tuning['settings'], desired_tuning['nativeSettings']) or
                    tuning['revision'] != tuning_read['revision'] or
                    not self._strict_service_match(tuning['settings'], tuning_read['settings']) or
                    not self._strict_service_match(tuning_read['settings'], tuning['settings'])):
                raise ValueError('RECOVERY_ORIGINAL_RECEIPTS_UNQUALIFIED')
            active = self._get_active_control()
            if dispatched:
                if (intent.get('hostUuid') != self._load_host_uuid() or
                        intent.get('recoveryOperationUuid') != command.get('operationUuid') or
                        intent.get('originalJournalHash') != original_hash or
                        active not in (intent.get('priorActiveControl'), command.get('operationUuid'))):
                    raise ValueError('RECOVERY_CONTROL_FENCE_MISMATCH')
            else:
                anchor = self._load_operation({'operationUuid': active}) if active else None
                if (not isinstance(anchor, dict) or anchor.get('stage') != 'APPLIED' or
                        anchor.get('hostUuid') != self._load_host_uuid() or anchor.get('bootId') != boot or
                        (anchor.get('readback') or {}).get('status') != 'Succeeded' or
                        command.get('desiredRevision') != old.get('desiredRevision') or
                        anchor.get('desiredRevision') is None or
                        anchor['desiredRevision'] >= old['desiredRevision']):
                    raise ValueError('RECOVERY_CONTROL_FENCE_MISMATCH')
            current_tuning = self._strict_service_success('tuning-state', self._service_request('tuning-state', {}))
            current_cpu = self._strict_service_success('host-cpu-state', self._service_request('host-cpu-state', {}))
            live = self._service_request('monitor-state', {})
            if (current_tuning['revision'] != tuning['revision'] or
                    not self._strict_service_match(current_tuning['settings'], tuning['settings']) or
                    not self._strict_service_match(tuning['settings'], current_tuning['settings']) or
                    (live.get('host_zram') or {}).get('pool_generation') != generation or
                    (live.get('lifecycle') or {}).get('paused') is not False or
                    (live.get('lifecycle') or {}).get('migrationHold') not in (None, {})):
                raise ValueError('RECOVERY_NATIVE_POLICY_CHANGED')
            if issue:
                operations = self._readonly_query('operations', {
                    'hostUuid': self._load_host_uuid(), 'limit': 1})
                cq = operations.get('cq') or {}
                if (not self._strict_service_match(current_cpu, held) or
                        type(cq.get('C')) is not int or cq['C'] != 0 or
                        type(cq.get('Q')) is not int or cq['Q'] != 0 or
                        'pending_operations' not in live or live['pending_operations'] not in (None, [])):
                    raise ValueError('RECOVERY_NATIVE_STATE_NOT_QUIESCENT')
                intent = {'kind': 'finalCpuGate', 'hostUuid': self._load_host_uuid(),
                          'expectedBootId': boot, 'expectedPoolGeneration': generation,
                          'recoveryOperationUuid': command['operationUuid'], 'unresolvedOperationUuid': old_uuid,
                          'priorActiveControl': active, 'originalRequestHash': old['requestHash'],
                          'originalJournalHash': original_hash, 'desiredRevision': old['desiredRevision'],
                          'cpuExpectedRevision': guard['revision'], 'cpuTarget': target}
                if not self._persist_recovery_intent(command, intent):
                    raise ValueError('OPERATION_JOURNAL_UNAVAILABLE')
                dispatched = True
                cpu_command = {'operationUuid': self._derived_service_request_id(old_uuid, 'cpu'),
                               'cpuExpectedRevision': guard['revision'], 'nativeCpuState': current_cpu,
                               'policy': {'zram': {'enabled': target['efficiency_enabled'],
                                   'cpuThresholdPercent': target['idle_cpu_threshold_percent'],
                                   'cpuHoldSeconds': target['idle_duration_seconds']}}}
                receipt = self._strict_service_success('host-cpu', self._service_request('host-cpu', cpu_command))
                if (receipt.get('request_id') != cpu_command['operationUuid'] or
                        receipt['revision'] != guard['revision'] + 1 or
                        not self._strict_service_match(receipt, target)):
                    raise ValueError('RECOVERY_CPU_RECEIPT_MISMATCH')
                intent['cpuReceipt'] = receipt
                recorded = self._load_operation(command)
                recorded['recoveryIntent'] = intent
                if not self._write_operation_record(recorded):
                    raise ValueError('OPERATION_JOURNAL_UNAVAILABLE')
                current_cpu = self._strict_service_success('host-cpu-state', self._service_request('host-cpu-state', {}))
                current_tuning = self._strict_service_success('tuning-state', self._service_request('tuning-state', {}))
                if (current_tuning['revision'] != tuning['revision'] or
                        not self._strict_service_match(current_tuning['settings'], tuning['settings']) or
                        not self._strict_service_match(tuning['settings'], current_tuning['settings'])):
                    raise ValueError('RECOVERY_NATIVE_POLICY_CHANGED')
            receipt = intent.get('cpuReceipt') if isinstance(intent, dict) else None
            if (not isinstance(receipt, dict) or
                    receipt.get('request_id') != self._derived_service_request_id(old_uuid, 'cpu') or
                    receipt.get('revision') != guard['revision'] + 1 or
                    not self._strict_service_match(receipt, target) or
                    current_cpu['revision'] != receipt['revision'] or
                    not self._strict_service_match(current_cpu, target)):
                raise ValueError('RECOVERY_CPU_RECEIPT_UNCONFIRMED')
            # Recheck the immutable original and ownership before committing
            # the new control. No rewrite of the old Unknown is allowed.
            if (self._operation_hash(self._load_operation({'operationUuid': old_uuid})) != original_hash or
                    self._get_active_control() not in (intent['priorActiveControl'], command['operationUuid']) or
                    self._current_boot_id() != boot):
                raise ValueError('RECOVERY_CONTROL_FENCE_MISMATCH')
            proof = {'schemaVersion': 1, 'hostUuid': self._load_host_uuid(), 'bootId': boot,
                     'recoveryOperationUuid': command['operationUuid'], 'unresolvedOperationUuid': old_uuid,
                     'expectedPoolGeneration': generation, 'originalRequestHash': old['requestHash'],
                     'originalPolicyHash': old['policyHash'], 'originalDesiredRevision': old['desiredRevision'],
                     'tuningRevision': tuning['revision'], 'cpuExpectedRevision': guard['revision'],
                     'finalCpuRestored': True, 'originalOutcome': 'Unknown'}
            result = {'success': True, 'status': 'Succeeded', 'operationUuid': command['operationUuid'],
                      'bootId': boot, 'sampleTime': int(time.time() * 1000),
                      'appliedRevision': old['desiredRevision'], 'state': {
                          'phase': 'POLICY_RECOVERED', 'bootId': boot,
                          'lastConfirmedOperationUuid': command['operationUuid'],
                          'lastConfirmedAppliedRevision': old['desiredRevision'],
                          'recoveryProof': proof, 'cpuBefore': before,
                          'cpuReceipt': receipt, 'cpuReadback': current_cpu}}
            self._set_active_control(command['operationUuid'])
            if not self._update_operation_record(command['operationUuid'], 'APPLIED', result):
                raise ValueError('OPERATION_JOURNAL_UNAVAILABLE')
            return result
        except Exception as exc:
            reason = str(exc) if re.match(r'^[A-Z][A-Z0-9_]+$', str(exc)) else 'RECOVERY_PREFLIGHT_UNKNOWN'
            if issue and not dispatched:
                rejected = self._recovery_not_issued(command, reason)
                if self._record_operation(command, 'REJECTED', rejected):
                    return rejected
            return self._recovery_failure(command, reason, 'RECOVERING' if dispatched else 'UNKNOWN')

    @staticmethod
    def _release_operation(lock):
        if lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            finally:
                lock.close()

    def _active_ksm_only(self):
        record = self._load_operation({'operationUuid': self._get_active_control()}) or {}
        policy = record.get('policy') or {}
        policy_ksm = policy.get('ksm') or {}
        state = record.get('readback', {}).get('state', {}) if isinstance(record, dict) else {}
        pause_active = record.get('action') == 'pause' and isinstance(state, dict) and state.get('ksmOnly') is True
        return (record.get('stage') == 'APPLIED' and
                record.get('bootId') == self._current_boot_id() and
                ((bool(policy_ksm) and policy_ksm.get('enabled') is not False) or pause_active) and
                not (policy.get('zram') or {}).get('enabled') and
                not (policy.get('writeback') or {}).get('enabled'))

    def _promote_ksm_only_state(self, result, observer=False):
        """Reconcile a native journal with an absent service or empty observer.

        Kylin V10 can provide the native KSM interfaces without the Go
        zram-service.  A current-boot APPLIED journal is useful evidence in
        that case, but only after the native KSM values have been read back.
        This helper is deliberately fail-closed: stale, missing, pending, or
        mixed (zram/writeback) journals remain Unknown and removable is never
        inferred from KSM evidence.
        """
        if not isinstance(result, dict):
            return result
        if observer:
            if result.get('status') != 'Succeeded' or result.get('success') is not True:
                return result
        elif result.get('status') != 'Unknown':
            return result
        state = result.get('state')
        if not isinstance(state, dict):
            if observer:
                return result
            state = {}
            result['state'] = state
        if observer:
            lifecycle = state.get('lifecycle')
            pool = state.get('host_zram')
            if (state.get('mode') != 'observe' or state.get('resource_authorized') is not False or
                    not isinstance(lifecycle, dict) or lifecycle.get('activeState') != 'compatibility' or
                    lifecycle.get('paused') is not False or lifecycle.get('migrationHold') is not None or
                    state.get('maintenance_blocks_activation') is True or
                    not isinstance(pool, dict) or pool.get('quality') != 'unavailable' or
                    pool.get('pool_generation') != '' or pool.get('device') != ''):
                return result
        pending = state.get('pending_operations') or state.get('pending') or []
        if pending:
            return result
        # The operation UUID in a state observation is generated by the MN
        # and is not a durable ownership reference.  Only the host-local
        # active-control fence may select a journal for reconciliation.
        active_operation = self._get_active_control()
        operation_uuid = active_operation
        if not operation_uuid:
            return result
        record = self._load_operation({'operationUuid': operation_uuid})
        if (not isinstance(record, dict) or
                record.get('operationUuid') != operation_uuid or
                record.get('stage') != 'APPLIED'):
            return result
        current_boot = self._current_boot_id()
        if not current_boot or record.get('bootId') != current_boot:
            return result
        readback = record.get('readback')
        if not isinstance(readback, dict):
            return result
        journal_state = readback.get('state')
        if not isinstance(journal_state, dict) or journal_state.get('ksmOnly') is not True:
            return result
        policy = record.get('policy')
        if not isinstance(policy, dict):
            return result
        ksm_policy = policy.get('ksm')
        if not isinstance(ksm_policy, dict):
            return result
        zram_policy = policy.get('zram', {})
        writeback_policy = policy.get('writeback', {})
        if (not isinstance(zram_policy, dict) or
                not isinstance(writeback_policy, dict)):
            return result
        if zram_policy.get('enabled') or writeback_policy.get('enabled'):
            return result
        revision = record.get('desiredRevision')
        if (isinstance(revision, bool) or not isinstance(revision, INTEGER_TYPES) or
                revision < 0):
            return result
        if ksm_policy:
            # Preserve the established policy-subset check for ordinary KSM
            # journals; empty clear journals use the complete persisted proof
            # below because their request intentionally has no KSM fields.
            if not self._ksm_readback_matches(
                    ksm_policy, revision, readback.get('ksmReadback')):
                return result
        elif not self._ksm_proof_matches(readback.get('ksmReadback'), revision):
            return result
        if observer and (result.get('lastConfirmedOperationUuid') != operation_uuid or
                         result.get('lastConfirmedAppliedRevision') != revision or
                         state.get('bootId') != current_boot or
                         self._get_active_control() != operation_uuid):
            return result
        result['success'] = True
        result['status'] = 'Succeeded'
        # This fallback intentionally handles the socket failure. Do not
        # leave it as the top-level result reason after confirming KSM; ZRAM
        # support limitations remain visible in capabilities and actual state.
        result.pop('reason', None)
        result.pop('reasonCode', None)
        result['state'] = dict(state, ksmOnly=True)
        if observer:
            result['state']['lastConfirmedOperationUuid'] = operation_uuid
            result['state']['lastConfirmedAppliedRevision'] = revision
        # This is evidence for presentation, never authorization to remove or
        # initialize a pool. Keep the observer's lifecycle and quality intact.
        result['state']['safeToRemove'] = False
        return result

    @staticmethod
    def _is_local_service_transport_unavailable(exc):
        """Recognize only concrete socket transport failures for KSM fallback.

        Business errors, invalid JSON, HTTP error replies, and arbitrary
        RuntimeError instances must not be converted into a successful KSM
        observation merely because a prior KSM journal exists.
        """
        if not isinstance(exc, (socket.error, OSError)):
            return False
        error_number = getattr(exc, 'errno', None)
        if error_number is None and getattr(exc, 'args', None):
            first = exc.args[0]
            if isinstance(first, int) and not isinstance(first, bool):
                error_number = first
        transport_errnos = set(
            value for value in (getattr(errno, name, None) for name in (
                'ENOENT', 'ECONNREFUSED', 'ECONNRESET', 'EPIPE',
                'ENOTCONN', 'ETIMEDOUT')) if value is not None)
        return error_number in transport_errnos

    def _maintenance_recovery_proof(self, command, live_state=None,
                                    expected_active_control=None):
        """Validate the existing Go maintenance archive before reopening apply.

        This is intentionally a local evidence check, not a caller-supplied
        bypass: the drain journal/receipt and service StateDir archive must
        agree, and either a different live pool or a locally empty reset
        device must be observed.
        """
        proof = command.get('maintenanceProof')
        if (not isinstance(proof, dict) or proof.get('maintenanceReady') is not True or
                proof.get('maintenanceArchived') is not True or
                proof.get('activeOperations') != 0):
            return False
        drain_uuid = proof.get('drainOperationUuid')
        old_generation = proof.get('oldPoolGeneration')
        new_generation = proof.get('newPoolGeneration')
        if not (self._valid_identifier(drain_uuid) and
                isinstance(old_generation, STRING_TYPES) and
                re.match(r'^[0-9a-fA-F]{64}$', old_generation) and
                (new_generation is None or
                 (isinstance(new_generation, STRING_TYPES) and
                  re.match(r'^[0-9a-fA-F]{64}$', new_generation)))):
            return False
        record = self._load_operation({'operationUuid': drain_uuid})
        if (not isinstance(record, dict) or record.get('action') != 'drain' or
                record.get('stage') != 'APPLIED'):
            return False
        # A reboot resets the drained device. Only the empty-device proof below
        # may span it; a live replacement pool must belong to the drain's boot.
        if record.get('bootId') != self._current_boot_id() and new_generation:
            return False
        if self._get_active_control() != (expected_active_control or drain_uuid):
            return False
        try:
            with open(os.path.join(self.operation_dir, '%s.drain-intent.json' % drain_uuid)) as stream:
                intent = json.load(stream)
            with open(self.drain_config) as stream:
                service_config = json.load(stream)
            state_dir = service_config.get('state_dir')
            manifest_path = os.path.join(state_dir, 'drained-pool-archives',
                                         old_generation, 'manifest.json')
            with open(manifest_path) as stream:
                manifest = json.load(stream)
        except (IOError, OSError, TypeError, ValueError):
            return False
        if intent.get('operationUuid') != drain_uuid or intent.get('poolGeneration') != old_generation:
            return False
        if not self._drained_archive_manifest_qualified(
                manifest, os.path.dirname(manifest_path), old_generation):
            return False
        receipt = None
        try:
            with open(intent.get('receiptPath')) as stream:
                receipt = json.load(stream)
        except (IOError, OSError, TypeError, ValueError):
            # The Go archive retains the executor's observed receipt even when
            # the Agent-side drain receipt is absent. Only accept an
            # observed.json below the manifest-declared maintenance archive;
            # never synthesize proof from a missing receipt.
            archive_maintenance = os.path.join(state_dir, 'drained-pool-archives',
                                               old_generation, 'maintenance')
            try:
                for root, dirs, files in os.walk(archive_maintenance):
                    for name in sorted(files):
                        if name != 'observed.json':
                            continue
                        with open(os.path.join(root, name)) as stream:
                            candidate = json.load(stream)
                        if (isinstance(candidate, dict) and
                                candidate.get('pool_generation') == old_generation and
                                candidate.get('state') == 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED' and
                                candidate.get('active') is False and
                                candidate.get('reset_performed') is False):
                            receipt = candidate
                            break
                    if receipt is not None:
                        break
            except (IOError, OSError, TypeError, ValueError):
                receipt = None
        if (not isinstance(receipt, dict) or
                receipt.get('pool_generation') != old_generation or
                receipt.get('state') != 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED' or
                receipt.get('active') is not False or
                receipt.get('reset_performed') is not False):
            return False
        if new_generation:
            if proof.get('poolOwnedByService') is not True:
                return False
            try:
                state = live_state if isinstance(live_state, dict) else self._service_request('state', {})
                pool = state.get('host_zram') or state.get('pool') or {}
                if 'pending_operations' in state:
                    pending = state['pending_operations']
                elif 'pending' in state:
                    pending = state['pending']
                else:
                    return False
                # Go encodes an empty []PendingOperation as JSON null in the
                # runtime snapshot; explicit null is therefore equivalent to
                # an empty list, while omission remains unknown.
                if pending is None:
                    pending = []
                if not isinstance(pending, list):
                    return False
            except (IOError, OSError, RuntimeError, ValueError):
                return False
            return (pool.get('pool_generation') == new_generation and
                    new_generation != old_generation and not pending)
        # Empty-pool recovery is valid only after the archive removed all
        # ownership files and the native device is reset/inactive.
        if (proof.get('readyForInitialization') is not True or
                proof.get('originalDeviceInactive') is not True or
                proof.get('oldPoolOwnershipAbsent') is not True):
            return False
        if any(os.path.exists(os.path.join(state_dir, name))
               for name in ('stock-pool.json', 'zram-ownership.json', 'maintenance')):
            return False
        try:
            state = live_state if isinstance(live_state, dict) else self._service_request('state', {})
            if 'pending_operations' in state:
                pending = state['pending_operations']
            elif 'pending' in state:
                pending = state['pending']
            else:
                return False
            if pending is None:
                pending = []
            if not isinstance(pending, list) or pending:
                return False
            pool = state.get('host_zram') or state.get('pool')
            if pool and not self._is_uninitialized_pool_snapshot(pool):
                return False
        except (IOError, OSError, RuntimeError, ValueError):
            return False
        device = receipt.get('device') or intent.get('device')
        if not isinstance(device, STRING_TYPES) or not device.startswith('/dev/'):
            return False
        name = os.path.basename(device)
        try:
            if device in open('/proc/swaps').read():
                return False
            with open('/sys/block/%s/mm_stat' % name) as stream:
                first = stream.read().split()[0]
            return int(first) == 0
        except (IOError, OSError, ValueError, IndexError):
            return False

    @staticmethod
    def _drained_archive_manifest_qualified(manifest, archive_root, old_generation):
        """Match both Go archive shapes; extra writeback evidence must be idle.

        The schedule belongs to the archived pool/backend, not to a newly
        prepared backend. Do not accept arbitrary extra files or a pending
        old writeback intent as a completed maintenance proof.
        """
        base = ['stock-pool.json', 'zram-ownership.json', 'maintenance']
        if (not isinstance(manifest, dict) or isinstance(manifest.get('schema'), bool) or
                manifest.get('schema') != 1 or
                manifest.get('pool_generation') != old_generation or
                manifest.get('files') not in (base, base + ['writeback-schedule.json'])):
            return False
        schedule_path = os.path.join(archive_root, 'writeback-schedule.json')
        if manifest['files'] == base:
            return not os.path.lexists(schedule_path)
        try:
            with open(schedule_path) as stream:
                schedule = json.load(stream)
            with open(os.path.join(archive_root, 'stock-pool.json')) as stream:
                archived_pool = json.load(stream)
            if not isinstance(schedule, dict) or not isinstance(archived_pool, dict):
                return False
            backend = archived_pool.get('backend')
            backend_generation = backend.get('generation') if isinstance(backend, dict) else None
            return (isinstance(backend_generation, STRING_TYPES) and bool(backend_generation) and
                    archived_pool.get('userspace_ownership_generation') == old_generation and
                    not isinstance(schedule.get('version'), bool) and schedule.get('version') == 1 and
                    schedule.get('pool_generation') == old_generation and
                    schedule.get('backend_generation') == backend_generation and
                    schedule.get('active_id') == '' and schedule.get('active_action') == '')
        except (IOError, OSError, ValueError, TypeError):
            return False

    @staticmethod
    def _is_uninitialized_pool_snapshot(pool):
        """Recognize Go's explicit no-qualified-pool placeholder only."""
        return (isinstance(pool, dict) and pool.get('pool_generation') == '' and
                pool.get('device') == '' and pool.get('quality') == 'unavailable' and
                str(pool.get('reason', '')).startswith('NO_QUALIFIED_MANAGED_POOL:'))

    def _host_control_blocks_policy(self, command=None):
        """Return true while a same-boot pause/drain fence lacks proof."""
        record = self._load_operation({'operationUuid': self._get_active_control()}) or {}
        if record.get('bootId') != self._current_boot_id():
            return False
        blocked = ((record.get('action') == 'pause' and record.get('stage') == 'APPLIED') or
                   (record.get('action') == 'drain' and
                    record.get('stage') in ('DRAINING', 'APPLIED')))
        return blocked and not (command and record.get('action') == 'drain' and
                                record.get('stage') == 'APPLIED' and
                                self._maintenance_recovery_proof(command))

    def _cold_ksm_local_fence_clear(self, lock_held=False):
        """Prove there is no durable local operation fence before cold KSM admission.

        Missing, malformed, unreadable, symlinked, or in-progress evidence is
        deliberately not interpreted as an empty operation history.  Apply
        calls this again while holding the host-control writer flock.
        """
        directory = self.operation_dir
        if (not os.path.isdir(directory) or os.path.islink(directory) or
                os.path.realpath(directory) != directory):
            return False
        lock_path = os.path.join(directory, '.host-control.flock')
        if os.path.islink(lock_path):
            return False
        lock = None
        if not lock_held:
            try:
                lock = self._acquire_host_control_lock()
            except (IOError, OSError):
                return False
        try:
            active_path = self.active_control_path
            if os.path.islink(active_path):
                return False
            try:
                with open(active_path, 'r') as stream:
                    if stream.read().strip():
                        return False
            except (IOError, OSError) as exc:
                if exc.errno != errno.ENOENT:
                    return False

            # The Go maintenance service keeps its current marker in the
            # configured StateDir (outside operation_dir). When that config
            # exists, require it to be trustworthy and reject any current
            # maintenance marker rather than inferring from a missing socket.
            # An installed service that never ran has no StateDir and no marker.
            if os.path.lexists(self.drain_config) and not self._managed_service_never_used():
                if os.path.islink(self.drain_config):
                    return False
                try:
                    _config, state_dir, _device = self._read_maintenance_config()
                except (IOError, OSError, ValueError, TypeError):
                    return False
                maintenance_marker = os.path.join(state_dir, 'backend-maintenance', 'current.json')
                if os.path.lexists(maintenance_marker):
                    return False

            terminal = frozenset(('APPLIED', 'REJECTED', 'NOT_ISSUED'))
            allowed = frozenset(('.host-control.flock', 'active-control', 'drain',
                                 'vm-bindings', 'backend-maintenance'))
            try:
                names = os.listdir(directory)
            except (IOError, OSError):
                return False
            for name in names:
                path = os.path.join(directory, name)
                if os.path.islink(path):
                    return False
                if name in allowed:
                    if name == '.host-control.flock' or name == 'active-control':
                        if not os.path.isfile(path):
                            return False
                    elif not os.path.isdir(path) or os.path.realpath(path) != path:
                        return False
                    elif name in ('drain', 'backend-maintenance'):
                        # These are durable control-plane journals, not caches.
                        # Do not silently skip their contents when the service
                        # that interprets them is unavailable.
                        if os.listdir(path):
                            return False
                    elif name == 'vm-bindings' and not self._cold_ksm_vm_bindings_valid(path):
                        return False
                    continue
                if name.startswith('.operation-') or name.startswith('.active-control-'):
                    return False
                if not name.endswith('.json') or not os.path.isfile(path):
                    return False
                try:
                    with open(path, 'r') as stream:
                        record = json.load(stream)
                except (IOError, OSError, ValueError, TypeError):
                    return False
                operation_uuid = name[:-5]
                if (not isinstance(record, dict) or
                        record.get('operationUuid') != operation_uuid or
                        record.get('stage') not in terminal):
                    return False
                if record.get('stage') == 'APPLIED':
                    readback = record.get('readback')
                    if (not isinstance(readback, dict) or readback.get('success') is not True or
                            readback.get('status') != 'Succeeded' or
                            record.get('action') in ('pause', 'drain')):
                        return False
            return True
        finally:
            if lock is not None:
                self._release_operation(lock)

    @staticmethod
    def _first_zram_enable_requested(command):
        if (not isinstance(command, dict) or command.get('action') not in (None, 'apply') or
                str(command.get('scope', '')).lower() not in ('host', 'cluster', 'global')):
            return False
        policy = command.get('policy') or {}
        return isinstance(policy, dict) and (policy.get('zram') or {}).get('enabled') is True

    @staticmethod
    def _ksm_only_disabled_service_sections(policy):
        """Accept only absent/empty or explicit-disabled service sections."""
        if not isinstance(policy, dict):
            return False
        for name in ('zram', 'writeback'):
            if name not in policy:
                continue
            component = policy[name]
            if not isinstance(component, dict):
                return False
            if component and (set(component) != {'enabled'} or
                              component.get('enabled') is not False):
                return False
        return True

    def _first_use_terminal_ksm_record(self, record, allow_empty_noop=False):
        if not isinstance(record, dict):
            return False
        readback = record.get('readback') if isinstance(record, dict) else None
        state = readback.get('state') if isinstance(readback, dict) else None
        policy = record.get('policy') if isinstance(record, dict) else None
        if not (record.get('stage') == 'APPLIED' and
                record.get('action') in (None, 'apply') and
                record.get('hostUuid') == self._load_host_uuid() and
                isinstance(record.get('requestHash'), STRING_TYPES) and
                re.match(r'^[0-9a-f]{64}\Z', record.get('requestHash')) is not None and
                isinstance(readback, dict) and readback.get('success') is True and
                readback.get('status') == 'Succeeded' and
                readback.get('appliedRevision') == record.get('desiredRevision') and
                isinstance(state, dict) and state.get('ksmOnly') is True and
                isinstance(policy, dict) and isinstance(policy.get('ksm'), dict) and
                (bool(policy['ksm']) or (allow_empty_noop and not policy['ksm'])) and
                self._ksm_only_disabled_service_sections(policy)):
            return False
        if not policy['ksm'] and (
                record.get('policyMode') != 'effective' or
                set(policy) - set(('ksm', 'schemaVersion')) or
                ('schemaVersion' in policy and
                 (type(policy['schemaVersion']) not in INTEGER_TYPES or policy['schemaVersion'] != 1)) or
                readback.get('operationUuid') != record.get('operationUuid') or
                not isinstance(record.get('bootId'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z',
                         record['bootId']) is None):
            return False
        revision = record.get('desiredRevision')
        if isinstance(revision, bool) or not isinstance(revision, INTEGER_TYPES) or revision < 1:
            return False
        proof = self._ksm_proof_policy(readback.get('ksmReadback'), revision)
        if proof is None:
            return False
        allowed = frozenset(('enabled', 'pagesToScan', 'sleepMillis', 'zeroPagesEnabled'))
        if set(policy['ksm']) - allowed:
            return False
        for key, expected in policy['ksm'].items():
            actual = proof.get(key)
            if (key == 'zeroPagesEnabled' and actual is None and
                    isinstance(readback.get('ksmReadback'), dict) and
                    readback['ksmReadback'].get('use_zero_pages') == 'unsupported' and
                    expected is False):
                # Unsupported is not false; preserve ordinary KSM history
                # without claiming a zero-page capability/value.
                continue
            if isinstance(expected, bool):
                if not isinstance(actual, bool) or actual is not expected:
                    return False
            elif (isinstance(expected, bool) or not isinstance(expected, INTEGER_TYPES) or
                  not isinstance(actual, INTEGER_TYPES) or isinstance(actual, bool) or
                  actual != expected):
                return False
        return True

    KSM_PREWRITE_REJECTIONS = frozenset((
        'invalid KSM policy revision', 'KSM_POLICY_VALUE_INVALID', 'KSM_ZERO_PAGES_POLICY_INVALID',
        'KSM_ZERO_PAGES_UNSUPPORTED', 'KSM_ENABLED_POLICY_INVALID', 'KSM_MEMTOTAL_UNKNOWN',
        'KSM_SLEEP_UNREPRESENTABLE', 'KSM_CONFIG_VALUE_INVALID'))

    def _first_use_ksm_prewrite_rejection(self, record):
        """A KSM-only apply rejected by value validation wrote nothing."""
        policy = record.get('policy') if isinstance(record, dict) else None
        return (isinstance(policy, dict) and isinstance(policy.get('ksm'), dict) and
                bool(policy['ksm']) and not set(policy) - set(('ksm', 'schemaVersion')) and
                record.get('stage') == 'REJECTED' and record.get('action') in (None, 'apply') and
                record.get('hostUuid') == self._load_host_uuid() and
                isinstance(record.get('readback'), dict) and set(record['readback']) == {'reason'} and
                record['readback']['reason'] in self.KSM_PREWRITE_REJECTIONS)

    def _first_use_backend_bound_ksm_record(self, record, preparations,
                                           expected_boot=None,
                                           expected_operation=None,
                                           expected_resource_uuid=None,
                                           expected_capacity=None):
        """Accept KSM-only history retaining the exact disabled prepared backend."""
        if not isinstance(record, dict) or not isinstance(preparations, dict):
            return False
        policy = record.get('policy')
        writeback = policy.get('writeback') if isinstance(policy, dict) else None
        capacity = (writeback.get('backendCapacityBytes')
                    if isinstance(writeback, dict) else None)
        resource_uuid = (writeback.get('backendResourceUuid')
                         if isinstance(writeback, dict) else None)
        readback = record.get('readback')
        if (not isinstance(policy, dict) or set(policy) !=
                set(('ksm', 'schemaVersion', 'writeback')) or
                type(policy.get('schemaVersion')) not in INTEGER_TYPES or
                policy.get('schemaVersion') != 1 or
                not isinstance(writeback, dict) or
                set(writeback) != set(('enabled', 'backendResourceUuid',
                                       'backendCapacityBytes')) or
                writeback.get('enabled') is not False or
                not isinstance(resource_uuid, STRING_TYPES) or
                re.match(r'^[0-9a-f]{32}$', resource_uuid) is None or
                isinstance(capacity, bool) or not isinstance(capacity, INTEGER_TYPES) or
                capacity <= 0 or
                record.get('policyHash') != self._policy_digest(policy) or
                not isinstance(readback, dict) or
                readback.get('operationUuid') !=
                record.get('operationUuid') or
                (expected_operation is not None and
                 record.get('operationUuid') != expected_operation) or
                (expected_boot is not None and record.get('bootId') != expected_boot) or
                (expected_resource_uuid is not None and
                 resource_uuid != expected_resource_uuid) or
                (expected_capacity is not None and capacity != expected_capacity)):
            return False
        matched = False
        for preparation_uuid, preparation_record in preparations.items():
            if (not isinstance(preparation_record, dict) or
                    preparation_record.get('operationUuid') != preparation_uuid or
                    preparation_record.get('hostUuid') != self._load_host_uuid()):
                continue
            preparation_boot = preparation_record.get('bootId')
            evidence = self._completed_backend_preparation_evidence(
                preparation_uuid, preparation_record, self._load_host_uuid(),
                preparation_boot)
            if evidence is None:
                continue
            receipt = evidence.get('receipt')
            request = evidence.get('request')
            if (not isinstance(receipt, dict) or not isinstance(request, dict) or
                    receipt.get('stage') != 'APPLIED' or
                    receipt.get('backend_resource_uuid') != resource_uuid or
                    request.get('backend_capacity_bytes') != capacity or
                    preparation_boot != record.get('bootId') or
                    receipt.get('host_boot_id') != preparation_boot):
                continue
            matched = True
            break
        if not matched:
            return False
        # Reuse the strict KSM proof validator after removing only the exact
        # disabled backend metadata proven above. The original policy hash was
        # checked before this view is constructed.
        ksm_record = dict(record)
        ksm_policy = dict(policy)
        ksm_policy.pop('writeback')
        ksm_record['policy'] = ksm_policy
        return self._first_use_terminal_ksm_record(ksm_record, allow_empty_noop=True)

    def _first_use_terminal_service_disable(self, record, cpu_state=None, tuning_state=None):
        """Accept a completed service disable as history, never as pool proof.

        Older Agents sent explicit disabled targets through CPU/tuning even
        before a pool existed. Their receipts are not KSM-only acknowledgments;
        current control ownership and first-use native safety stay separate.
        """
        if not isinstance(record, dict):
            return False
        policy, readback = record.get('policy'), record.get('readback')
        revision, operation_uuid = record.get('desiredRevision'), record.get('operationUuid')
        if (record.get('stage') != 'APPLIED' or record.get('action') != 'apply' or
                record.get('scope') != 'Host' or record.get('hostUuid') != self._load_host_uuid() or
                record.get('resourceUuid') not in (None, record.get('hostUuid')) or
                record.get('policyMode', 'effective') not in ('delta', 'effective') or
                not self._valid_identifier(operation_uuid) or
                not isinstance(record.get('bootId'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z',
                         record['bootId']) is None or
                not isinstance(record.get('requestHash'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{64}\Z', record['requestHash']) is None or
                isinstance(revision, bool) or not isinstance(revision, INTEGER_TYPES) or revision < 1 or
                not isinstance(policy, dict) or
                set(policy) - set(('ksm', 'zram', 'writeback', 'schemaVersion')) or
                not self._ksm_only_disabled_service_sections(policy) or
                not (policy.get('zram') or policy.get('writeback')) or
                ('schemaVersion' in policy and
                 (type(policy['schemaVersion']) not in INTEGER_TYPES or policy['schemaVersion'] != 1)) or
                record.get('policyHash') != self._policy_digest(policy) or
                set(record) - set(('action', 'applyEvidence', 'bootId', 'desiredRevision', 'hostUuid',
                                   'operationUuid', 'policy', 'policyHash', 'policyMode', 'readback',
                                   'requestHash', 'resourceUuid', 'scope', 'stage', 'updatedAt')) or
                not isinstance(readback, dict) or readback.get('success') is not True or
                set(readback) - set(('success', 'status', 'operationUuid', 'appliedRevision',
                                     'sampleTime', 'ksmReadback', 'state')) or
                readback.get('status') != 'Succeeded' or readback.get('operationUuid') != operation_uuid or
                not self._strict_service_match(readback.get('appliedRevision'), revision) or
                not self._strict_service_match(record.get('applyEvidence'), readback) or
                not self._strict_service_match(readback, record.get('applyEvidence'))):
            return False
        ksm = policy.get('ksm', {})
        if not isinstance(ksm, dict):
            return False
        if ksm:
            proof = self._ksm_proof_policy(readback.get('ksmReadback'), revision)
            if proof is None or set(ksm) - set(('enabled', 'zeroPagesEnabled', 'pagesToScan', 'sleepMillis')):
                return False
            for key, value in ksm.items():
                if key == 'zeroPagesEnabled' and key not in proof and value is False:
                    continue  # An explicit unsupported zero-page ABI is not a fabricated zero.
                if key not in proof or not self._strict_service_match(value, proof[key]):
                    return False
        state = readback.get('state')
        if (not isinstance(state, dict) or state.get('phase') != 'READBACK' or
                set(state) != {'phase', 'sectionComplete', 'sequence', 'sections'} or
                not self._strict_service_match(state.get('sectionComplete'), {'cpu': True, 'tuning': True}) or
                set(state.get('sectionComplete', {})) != {'cpu', 'tuning'}):
            return False
        sections = state.get('sections')
        if not isinstance(sections, dict):
            return False
        try:
            before = self._strict_service_success('host-cpu-state', sections.get('cpuBefore'))
            cpu = self._strict_service_success('host-cpu', sections.get('cpu'))
            cpu_read = self._strict_service_success('host-cpu-state', sections.get('cpuReadback'))
            tuning = self._strict_service_success('apply', sections.get('tuning'))
            tuning_read = self._strict_service_success('tuning-state', sections.get('tuningReadback'))
            target = {'efficiency_enabled': False,
                      'idle_cpu_threshold_percent': before['idle_cpu_threshold_percent'],
                      'idle_duration_seconds': before['idle_duration_seconds']}
            expected_revision = before['revision']
            expected_sections = {'cpuBefore', 'cpu', 'cpuReadback', 'tuning', 'tuningReadback'}
            sequence = ['tuning_apply_returned', 'tuning_target_verified', 'cpu_target_verified']
            if before['efficiency_enabled']:
                guard = self._strict_service_success('host-cpu', sections.get('cpuGuard'))
                guard_read = self._strict_service_success('host-cpu-state', sections.get('cpuGuardReadback'))
                if (guard.get('request_id') != self._derived_service_request_id(operation_uuid, 'cpu-hold') or
                        guard['revision'] != before['revision'] + 1 or
                        not self._strict_service_match(guard, target) or
                        not self._strict_service_match(guard_read, dict(target, revision=guard['revision']))):
                    return False
                expected_revision = guard_read['revision']
                expected_sections.update(('cpuGuard', 'cpuGuardReadback'))
                sequence = ['cpu_guard_written', 'cpu_guard_verified_off'] + sequence
            valid = bool(
                set(sections) == expected_sections and state.get('sequence') == sequence and
                cpu.get('request_id') == self._derived_service_request_id(operation_uuid, 'cpu') and
                self._strict_service_match(cpu, dict(
                    target, agent_expected_revision=expected_revision, agent_desired_enabled=False,
                    agent_desired_threshold_percent=target['idle_cpu_threshold_percent'],
                    agent_desired_duration_seconds=target['idle_duration_seconds'])) and
                self._strict_service_match(cpu_read, dict(target, revision=cpu['revision'])) and
                tuning.get('agent_request_id') == self._derived_service_request_id(operation_uuid, 'tuning') and
                tuning['revision'] == tuning_read['revision'] and
                self._strict_service_match(tuning['settings'], {'writeback': {'enabled': False}}) and
                self._strict_service_match(tuning['settings'], tuning_read['settings']) and
                self._strict_service_match(tuning_read['settings'], tuning['settings']))
            if not valid:
                return False
            if cpu_state is None and tuning_state is None:
                return True
            if not isinstance(cpu_state, dict) or not isinstance(tuning_state, dict):
                return False
            expected_cpu = self._strict_service_success(
                'host-cpu-state', sections.get('cpuReadback'))
            expected_tuning = self._strict_service_success(
                'tuning-state', sections.get('tuningReadback'))
            return (self._strict_service_match(cpu_state, expected_cpu) and
                    self._strict_service_match(tuning_state, expected_tuning))
        except (RuntimeError, ValueError, TypeError):
            return False

    def _first_use_terminal_vm_binding(self, record):
        """A completed VM participation write is not a prior Host writer."""
        if not isinstance(record, dict):
            return False
        operation_uuid = record.get('operationUuid')
        readback = record.get('readback')
        policy = record.get('policy', {})
        if not (record.get('stage') == 'APPLIED' and record.get('action') == 'bind' and
                str(record.get('scope', '')).lower() == 'vm' and
                record.get('hostUuid') == self._load_host_uuid() and
                self._valid_identifier(operation_uuid) and
                self._valid_identifier(record.get('resourceUuid')) and
                self._valid_identifier(record.get('expectedInstanceGeneration')) and
                isinstance(record.get('requestHash'), STRING_TYPES) and
                re.match(r'^[0-9a-f]{64}\Z', record['requestHash']) is not None and
                isinstance(policy, dict) and not set(policy) - {'participation'} and
                record.get('participation') in ('inherit', 'allow', 'deny', 'auto') and
                isinstance(readback, dict) and readback.get('success') is True and
                readback.get('status') == 'Succeeded' and
                readback.get('operationUuid') == operation_uuid):
            return False
        if any(key in record for key in ('firstZramUse', 'activationIntent',
                                          'maintenanceProof', 'expectedControlOperationUuid')):
            return False
        participation = policy.get('participation', record['participation'])
        if participation not in ('inherit', 'allow', 'deny', 'auto'):
            return False
        if readback.get('request_id') == operation_uuid:
            revision = readback.get('revision')
        else:
            # A GET-only reconcile keeps the generation/mode proof instead
            # of the original service PUT receipt. It cannot authorize Host
            # policy and must never replace the active-control record.
            state = readback.get('state')
            service = state.get('service') if isinstance(state, dict) else None
            expected_mode = 'deny' if participation == 'deny' else 'auto'
            if not ('request_id' not in readback and isinstance(state, dict) and
                    state.get('phase') == 'VM_READBACK' and
                    state.get('complete') is True and isinstance(service, dict) and
                    service.get('instance_generation') == record['expectedInstanceGeneration'] and
                    service.get('mode') == expected_mode):
                return False
            revision = service.get('revision')
        return (isinstance(revision, INTEGER_TYPES) and not isinstance(revision, bool) and
                revision >= 0)

    def _first_use_admission_rejected(self, record):
        """Recognize exact durable pre-write rejections eligible for sealing.

        The durable applyEvidence is retained by later queries. A generic
        Unknown/error string, or any authorization/maintenance intent, is
        not evidence that a policy was never submitted.
        """
        if not isinstance(record, dict):
            return False
        policy = record.get('policy')
        if not isinstance(policy, dict):
            return False
        if (record.get('stage') not in ('UNKNOWN', 'NOT_ISSUED') or
                record.get('action') != 'apply' or
                not self._valid_identifier(record.get('hostUuid')) or
                record.get('hostUuid') != self._load_host_uuid() or
                not isinstance(record.get('bootId'), STRING_TYPES) or not record['bootId'] or
                not self._valid_identifier(record.get('operationUuid')) or
                not isinstance(record.get('requestHash'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{64}\Z', record['requestHash']) is None):
            return False
        evidence = record.get('applyEvidence')
        if not isinstance(evidence, dict) or set(evidence) != set(('reason',)):
            return False
        reason = evidence.get('reason')
        if reason == 'FIRST_ZRAM_LOCAL_CONTROL_FENCED':
            # Preserve the existing legacy path unchanged.
            return (isinstance(policy.get('zram'), dict) and
                    self._first_zram_enable_requested(record) and
                    not any(key in record for key in ('firstZramUse', 'activationIntent',
                                                      'maintenanceProof', 'mixedClearEvidence')))
        if reason == 'FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE':
            return (record.get('policyHash') == self._policy_digest(policy) and
                    isinstance(policy.get('zram'), dict) and
                    self._first_zram_enable_requested(record) and
                    not any(key in record for key in (
                        'firstZramUse', 'activationIntent', 'maintenanceProof',
                        'mixedClearEvidence', 'maintenanceProgress')))
        if reason == 'KSM_CLEAR_PRIOR_JOURNAL_INVALID':
            writeback = policy.get('writeback')
            capacity = writeback.get('backendCapacityBytes') if isinstance(writeback, dict) else None
            return (record.get('policyHash') == self._policy_digest(policy) and
                    not any(key in record for key in (
                        'firstZramUse', 'activationIntent', 'maintenanceProof',
                        'mixedClearEvidence', 'maintenanceProgress')) and
                    set(policy) == set(('schemaVersion', 'ksm', 'writeback')) and
                    type(policy.get('schemaVersion')) in INTEGER_TYPES and
                    policy.get('schemaVersion') == 1 and policy.get('ksm') == {} and
                    isinstance(writeback, dict) and
                    set(writeback) == set(('enabled', 'backendResourceUuid',
                                           'backendCapacityBytes')) and
                    writeback.get('enabled') is False and
                    self._valid_identifier(writeback.get('backendResourceUuid')) and
                    isinstance(capacity, INTEGER_TYPES) and not isinstance(capacity, bool) and
                    capacity > 0)
        return False

    def _first_use_admission_not_issued(self, record):
        if not self._first_use_admission_rejected(record) or record.get('stage') != 'NOT_ISSUED':
            return False
        readback = record.get('readback')
        return (isinstance(readback, dict) and readback.get('success') is False and
                readback.get('status') == 'Failed' and
                readback.get('operationUuid') == record['operationUuid'] and
                readback.get('reasonCode') == 'FIRST_ZRAM_ADMISSION_NOT_ISSUED' and
                readback.get('state') == {'phase': 'NOT_ISSUED',
                                         'bootId': record.get('bootId'),
                                         'requestHash': record['requestHash'],
                                         'policyWritesIssued': False})

    def _completed_backend_preparation_evidence(self, operation_uuid, record,
                                                host_uuid=None, boot_id=None):
        """Validate immutable worker and finalized journal evidence for one prep."""
        host_uuid = host_uuid or self._load_host_uuid()
        boot_id = boot_id or self._current_boot_id()
        if (not self._valid_identifier(operation_uuid) or not host_uuid or not boot_id or
                not isinstance(record, dict) or
                record.get('operationUuid') != operation_uuid or
                record.get('action') != 'prepareWritebackBackend' or
                record.get('scope') != 'Host' or record.get('stage') != 'APPLIED' or
                record.get('hostUuid') != host_uuid or record.get('bootId') != boot_id or
                not isinstance(record.get('requestHash'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{64}\Z', record.get('requestHash', '')) is None or
                record.get('maintenanceIntentPath') != os.path.join(
                    self.operation_dir, 'backend-maintenance',
                    '%s.intent.json' % operation_uuid)):
            return None
        operation_path = self._operation_path(operation_uuid)
        if (os.path.islink(operation_path) or not os.path.isfile(operation_path) or
                os.path.realpath(operation_path) != operation_path):
            return None
        journal_state, saved_record = self._operation_file_state(operation_uuid)
        if journal_state != 'present' or saved_record != record:
            return None
        receipt = record.get('readback')
        if not isinstance(receipt, dict):
            return None
        receipt_state = receipt.get('state')
        if not isinstance(receipt_state, dict):
            return None
        final_receipt = receipt_state.get('maintenance')
        if (not isinstance(receipt, dict) or receipt.get('success') is not True or
                receipt.get('status') != 'Succeeded' or receipt.get('operationUuid') != operation_uuid or
                receipt_state.get('phase') != 'APPLIED' or
                not isinstance(final_receipt, dict) or final_receipt.get('stage') != 'APPLIED'):
            return None
        try:
            _, paths = self._maintenance_intent_paths(operation_uuid, create=False)
            for path in paths.values():
                if (os.path.islink(path) or not os.path.isfile(path) or
                        os.path.realpath(path) != path):
                    return None
            with open(paths['intentPath'], 'r') as stream:
                intent = json.load(stream)
            with open(paths['requestPath'], 'r') as stream:
                request = json.load(stream)
            with open(paths['receiptPath'], 'r') as stream:
                worker_receipt = json.load(stream)
        except (IOError, OSError, ValueError, TypeError):
            return None
        expected_intent = os.path.join(
            self.operation_dir, 'backend-maintenance', '%s.intent.json' % operation_uuid)
        if (paths['intentPath'] != expected_intent or
                not isinstance(intent, dict) or intent.get('schema') != 1 or
                intent.get('operationUuid') != operation_uuid or
                intent.get('hostUuid') != host_uuid or intent.get('bootId') != boot_id or
                intent.get('requestHash') != record.get('requestHash') or
                intent.get('controlOperationUuid') != record.get('expectedControlOperationUuid') or
                intent.get('unit') != self._maintenance_systemd_unit(operation_uuid) or
                intent.get('requestPath') != paths['requestPath'] or
                intent.get('receiptPath') != paths['receiptPath'] or
                intent.get('stderrPath') != paths['stderrPath'] or
                intent.get('configPath') != self.drain_config or
                intent.get('workerLaunchAttempted') is not True or
                not isinstance(request, dict) or request.get('request_id') != operation_uuid or
                request.get('expected_host_boot_id') != boot_id or
                request.get('expected_pool_generation') != 'none' or
                not isinstance(record.get('backendPreparation'), dict) or
                record['backendPreparation'].get('candidateId') != request.get('candidate_id') or
                record['backendPreparation'].get('expectedHostBootId') != boot_id or
                record['backendPreparation'].get('expectedPoolGeneration') != 'none' or
                record['backendPreparation'].get('backendCapacityBytes') !=
                request.get('backend_capacity_bytes') or
                not self._maintenance_receipt_matches_request(worker_receipt, request, boot_id) or
                not self._maintenance_receipt_matches_request(final_receipt, request, boot_id)):
            return None
        common_fields = ('request_id', 'candidate_id', 'request_fingerprint',
                         'host_boot_id', 'backend_resource_uuid', 'target_identity')
        if (not isinstance(worker_receipt, dict) or worker_receipt.get('schema') != 1 or
                worker_receipt.get('stage') != 'AWAITING_SERVICE_READBACK' or
                worker_receipt.get('request_fingerprint') is None or
                re.match(r'^[0-9a-f]{64}\Z', worker_receipt.get('request_fingerprint', '')) is None or
                any(worker_receipt.get(key) != final_receipt.get(key) for key in common_fields) or
                not isinstance(final_receipt.get('backend_resource_uuid'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{32}\Z', final_receipt.get('backend_resource_uuid', '')) is None):
            return None
        worker, exit_status = self._systemd_worker_exit(intent['unit'])
        if worker != 'exited' or exit_status != 0:
            return None
        return {'operationUuid': operation_uuid, 'record': record, 'intent': intent,
                'request': request, 'workerReceipt': worker_receipt,
                'receipt': final_receipt, 'paths': paths}

    def _first_use_active_service_disable_safe(self, record, command=None,
                                              failed_backend_record=None):
        """Bind an active disabled Host receipt to current or stop-bound state."""
        if not isinstance(record, dict) or not self._first_use_terminal_service_disable(record):
            return False
        try:
            service_state = self._maintenance_service_state()
            if service_state == 'active':
                # The live (or same-boot stop-bound) service state proves the
                # receipt again, so one from before a reboot also qualifies.
                cpu_state = self._service_request('host-cpu-state', {})
                tuning_state = self._service_request('tuning-state', {})
            elif service_state == 'inactive' and isinstance(command, dict):
                current = self._load_operation(command)
                if not isinstance(current, dict):
                    return False
                progress = current.get('maintenanceProgress')
                if not isinstance(progress, dict):
                    return False
                stop = progress.get('controllerStop')
                if not isinstance(stop, dict):
                    return False
                identity = stop.get('identity') if isinstance(stop, dict) else None
                request = stop.get('request') if isinstance(stop, dict) else None
                native_state = stop.get('nativeState') if isinstance(stop, dict) else None
                operation_uuid = command.get('operationUuid')
                stopped_continuation = bool(
                    isinstance(stop, dict) and current.get('stage') == 'UNKNOWN' and
                    stop.get('attempted') is True and stop.get('completed') is True and
                    stop.get('continuationReady') is True and
                    stop.get('workerLaunchAttempted') is False and
                    isinstance(request, dict) and request.get('request_id') == operation_uuid and
                    request.get('expected_host_boot_id') == self._current_boot_id() and
                    request.get('expected_pool_generation') == 'none' and
                    not os.path.lexists(current.get('maintenanceIntentPath', '')))
                failed_worker = (
                    isinstance(failed_backend_record, dict) and
                    current == failed_backend_record and
                    current.get('stage') in ('FAILED_REQUIRES_REVIEW', 'UNKNOWN') and
                    stop.get('workerLaunchAttempted') is True)
                if (current.get('action') != 'prepareWritebackBackend' or
                        (current.get('stage') not in ('PREPARING', 'DRAINING') and
                         not failed_worker and not stopped_continuation) or
                        current.get('requestHash') != self._operation_hash(command) or
                        not isinstance(stop, dict) or stop.get('attempted') is not True or
                        stop.get('completed') is not True or
                        (stop.get('workerLaunchAttempted') is not False and
                         not failed_worker) or
                        stop.get('hostUuid') != self._load_host_uuid() or
                        stop.get('bootId') != self._current_boot_id() or
                        stop.get('requestHash') != current.get('requestHash') or
                        not isinstance(identity, dict) or
                        identity.get('bootId') != self._current_boot_id() or
                        identity.get('unit') != self.MANAGED_ZRAM_UNIT or
                        identity.get('killMode') != 'process' or
                        identity.get('restart') != 'no' or
                        isinstance(identity.get('pid'), bool) or
                        not isinstance(identity.get('pid'), INTEGER_TYPES) or identity['pid'] <= 0 or
                        not isinstance(identity.get('processStartTime'), STRING_TYPES) or
                        not identity['processStartTime'].isdigit() or
                        any(re.match(r'^[0-9a-f]{64}$', str(identity.get(key, ''))) is None
                            for key in ('unitSha256', 'binarySha256', 'templateSha256',
                                        'sourceConfigSha256')) or
                        not isinstance(request, dict) or request.get('request_id') != operation_uuid or
                        request.get('expected_host_boot_id') != self._current_boot_id() or
                        request.get('expected_pool_generation') != 'none' or
                        not isinstance(native_state, dict) or
                        not isinstance(stop.get('nativeStateCheckedAt'), (int, float)) or
                        not self._first_use_state_safe(
                            native_state,
                            observation_time=stop.get('nativeStateCheckedAt')) or
                        not isinstance(native_state.get('host_tuning_state'), dict)):
                    return False
                output = self._bounded_command_output([
                    'systemctl', 'show', self.MANAGED_ZRAM_UNIT,
                    '--property=Id', '--property=MainPID', '--property=ActiveState',
                    '--property=KillMode', '--property=Restart'], 5)
                if not isinstance(output, STRING_TYPES):
                    output = output.decode('utf-8')
                props = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
                if (props.get('Id') != self.MANAGED_ZRAM_UNIT or
                        props.get('MainPID') not in ('0', '', None) or
                        props.get('ActiveState') != 'inactive' or
                        props.get('KillMode') != 'process' or props.get('Restart') != 'no' or
                        self._controller_process_start_time(identity['pid']) is not None):
                    return False
                cpu_state = native_state.get('host_cpu')
                tuning_state = native_state.get('host_tuning_state')
            else:
                return False
            if not self._first_use_terminal_service_disable(record, cpu_state, tuning_state):
                return False
            policy = record.get('policy') or {}
            if policy.get('ksm'):
                readback = record.get('readback') or {}
                if not self._ksm_proof_matches(
                        readback.get('ksmReadback'), record.get('desiredRevision')):
                    return False
            return True
        except (IOError, OSError, RuntimeError, ValueError, TypeError,
                subprocess.CalledProcessError):
            return False

    def _first_use_backend_preparation_proof(self, current_config, template_config,
                                            stopped_command=None):
        """Validate the one allowed cold-backend delta and its completed proof."""
        if (not isinstance(current_config, dict) or not isinstance(template_config, dict) or
                'backend' in template_config or not isinstance(current_config.get('backend'), dict)):
            raise FirstZramConfigRejected('FIRST_ZRAM_CONFIG_NOT_FACTORY')

        try:
            def reject_duplicate_keys(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('DUPLICATE_RUNTIME_CONFIG_KEY')
                    result[key] = value
                return result

            def reject_nonfinite(value):
                raise ValueError('NONFINITE_RUNTIME_CONFIG_NUMBER')

            def strict_json(raw):
                return json.loads(raw.decode('utf-8'), object_pairs_hook=reject_duplicate_keys,
                                  parse_constant=reject_nonfinite)

            def canonical(value):
                return json.dumps(value, sort_keys=True, separators=(',', ':'),
                                  allow_nan=False)

            def exact_int(value):
                return isinstance(value, INTEGER_TYPES) and not isinstance(value, bool)

            def exact_number(value):
                if isinstance(value, bool):
                    return False
                if isinstance(value, INTEGER_TYPES):
                    return True
                return (isinstance(value, float) and
                        not math.isnan(value) and not math.isinf(value))

            def check_object(value, required, optional, types):
                if (not isinstance(value, dict) or not set(value) <= set(required + optional) or
                        not set(required) <= set(value)):
                    raise ValueError('RUNTIME_CONFIG_SCHEMA_INVALID')
                for key, expected in types.items():
                    if key not in value:
                        continue
                    current = value[key]
                    if expected == 'int':
                        valid = exact_int(current)
                    elif expected == 'number':
                        valid = exact_number(current)
                    elif expected == 'bool':
                        valid = isinstance(current, bool)
                    elif expected == 'string':
                        valid = isinstance(current, STRING_TYPES)
                    elif expected == 'strings':
                        valid = (isinstance(current, list) and
                                 all(isinstance(item, STRING_TYPES) for item in current))
                    elif expected == 'object':
                        valid = isinstance(current, dict)
                    else:
                        valid = False
                    if not valid:
                        raise ValueError('RUNTIME_CONFIG_TYPE_INVALID:%s' % key)

            def check_runtime_config(value):
                required = ['version', 'mode', 'resource_authorized', 'state_dir',
                            'monitor_socket', 'control_socket', 'device', 'vm_uuids',
                            'internal_rule', 'budget']
                optional = ['ram_admission', 'backend', 'managed', 'monitor_gid',
                            'algorithm_preference', 'startup_observation_seconds',
                            'vm_selection', 'initial_efficiency_enabled',
                            'discovery_interval_seconds', 'discovery_timeout_seconds',
                            'vm_list_ttl_seconds', 'vm_identity_request_bytes']
                check_object(value, required, optional, {
                    'version': 'int', 'mode': 'string',
                    'resource_authorized': 'bool', 'state_dir': 'string',
                    'monitor_socket': 'string', 'control_socket': 'string',
                    'device': 'string', 'vm_uuids': 'strings', 'managed': 'bool',
                    'monitor_gid': 'int', 'algorithm_preference': 'strings',
                    'startup_observation_seconds': 'int', 'vm_selection': 'string',
                    'initial_efficiency_enabled': 'bool',
                    'discovery_interval_seconds': 'int',
                    'discovery_timeout_seconds': 'int', 'vm_list_ttl_seconds': 'int',
                    'vm_identity_request_bytes': 'int',
                })
                rule = value['internal_rule']
                check_object(rule, [], ['cpu_only', 'cpu_fraction',
                    'memory_change_bytes_per_second', 'io_bytes_per_second',
                    'idle_seconds', 'cooldown_seconds', 'step_bytes',
                    'require_external_data'], {
                        'cpu_only': 'bool', 'cpu_fraction': 'number',
                        'memory_change_bytes_per_second': 'int',
                        'io_bytes_per_second': 'int', 'idle_seconds': 'int',
                        'cooldown_seconds': 'int', 'step_bytes': 'int',
                        'require_external_data': 'bool',
                    })
                budget = value['budget']
                check_object(budget, [], ['required_available_override_bytes', 'version',
                    'pool_bytes', 'allocator_limit_bytes', 'host_floor_bytes',
                    'metadata_reserve_bytes', 'metadata_committed_bytes',
                    'transient_reserve_bytes', 'step_limit_bytes',
                    'host_bytes_per_minute', 'vm_bytes_per_minute'], {
                        'required_available_override_bytes': 'int', 'version': 'int',
                        'pool_bytes': 'int', 'allocator_limit_bytes': 'int',
                        'host_floor_bytes': 'int', 'metadata_reserve_bytes': 'int',
                        'metadata_committed_bytes': 'int', 'transient_reserve_bytes': 'int',
                        'step_limit_bytes': 'int', 'host_bytes_per_minute': 'int',
                        'vm_bytes_per_minute': 'int',
                    })
                if 'backend' in value:
                    backend = value['backend']
                    check_object(backend, ['device', 'minimum_filesystem_free_bytes'],
                        ['file_path'], {'device': 'string',
                        'minimum_filesystem_free_bytes': 'int', 'file_path': 'string'})
                if 'ram_admission' in value:
                    admission = value['ram_admission']
                    check_object(admission, ['socket', 'gid', 'qemu_executable', 'qemu_sha256'],
                        [], {'socket': 'string', 'gid': 'int', 'qemu_executable': 'string',
                             'qemu_sha256': 'string'})

            def read_regular(path):
                if (not os.path.isabs(path) or os.path.realpath(path) != path or
                        os.path.islink(path)):
                    raise ValueError('RUNTIME_CONFIG_EVIDENCE_PATH_INVALID')
                info = os.lstat(path)
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError('RUNTIME_CONFIG_EVIDENCE_NOT_REGULAR')
                with open(path, 'rb') as stream:
                    return stream.read()

            template_bytes = read_regular(self.zram_config_template_path)
            parsed_template = strict_json(template_bytes)
            if canonical(parsed_template) != canonical(template_config):
                raise ValueError('RUNTIME_CONFIG_TEMPLATE_CHANGED')
            current_bytes = read_regular(self.zram_config_path)
            parsed_current = strict_json(current_bytes)
            if canonical(parsed_current) != canonical(current_config):
                raise ValueError('RUNTIME_CONFIG_CURRENT_CHANGED')
            check_runtime_config(parsed_current)
            template_control_fields = (
                'version', 'mode', 'resource_authorized', 'managed', 'state_dir',
                'monitor_socket', 'control_socket', 'monitor_gid', 'device',
                'vm_uuids', 'vm_selection', 'initial_efficiency_enabled',
                'ram_admission')
            if any(key in template_config and
                   (key not in parsed_current or
                    canonical(parsed_current[key]) != canonical(template_config[key]))
                   for key in template_control_fields):
                raise FirstZramConfigRejected('FIRST_ZRAM_CONFIG_NOT_FACTORY')

            receipt, status_error = self._read_backend_maintenance_receipt()
            if status_error or not isinstance(receipt, dict) or receipt.get('stage') != 'APPLIED':
                raise ValueError('BACKEND_MAINTENANCE_RECEIPT_UNPROVEN')
            operation_uuid = receipt.get('request_id')
            if not self._valid_identifier(operation_uuid):
                raise ValueError('BACKEND_MAINTENANCE_OPERATION_ID_INVALID')
            journal_state, record = self._operation_file_state(operation_uuid)
            boot_id = self._current_boot_id()
            host_uuid = self._load_host_uuid()
            evidence = (self._completed_backend_preparation_evidence(
                operation_uuid, record, host_uuid, boot_id)
                        if journal_state == 'present' else None)
            if (evidence is None or host_uuid != self._load_host_uuid()):
                raise ValueError('BACKEND_MAINTENANCE_OPERATION_UNPROVEN')
            if evidence['receipt'] != receipt:
                raise ValueError('BACKEND_MAINTENANCE_OPERATION_READBACK_UNPROVEN')
            intent, paths = evidence['intent'], evidence['paths']
            state_dir = parsed_current.get('state_dir')
            if (not isinstance(state_dir, STRING_TYPES) or not os.path.isabs(state_dir) or
                    os.path.realpath(state_dir) != state_dir or os.path.islink(state_dir)):
                raise ValueError('BACKEND_MAINTENANCE_STATE_DIR_UNPROVEN')
            request_dir = os.path.join(state_dir, 'backend-maintenance', operation_uuid)
            archive_dir = os.path.join(request_dir, 'pre-reset-archive')
            if (receipt.get('archive') != archive_dir or
                    os.path.realpath(request_dir) != request_dir or
                    os.path.islink(request_dir) or not os.path.isdir(request_dir) or
                    os.path.realpath(archive_dir) != archive_dir or
                    os.path.islink(archive_dir) or not os.path.isdir(archive_dir)):
                raise ValueError('BACKEND_MAINTENANCE_ARCHIVE_PATH_UNPROVEN')
            before_path = os.path.join(request_dir, 'config.before.json')
            before_bytes = read_regular(before_path)
            before_config = strict_json(before_bytes)
            check_runtime_config(before_config)
            manifest_path = os.path.join(archive_dir, 'manifest.json')
            archive_config_path = os.path.join(archive_dir, 'config.json')
            manifest = strict_json(read_regular(manifest_path))
            archive_config_bytes = read_regular(archive_config_path)
            archive_config = strict_json(archive_config_bytes)
            check_runtime_config(archive_config)
            archive_names = frozenset((
                'stock-pool.json', 'zram-ownership.json', 'capacity-effective.json',
                'backend-ownership.json', 'backend-settings.json', 'backend-setup.json',
                'ram-admission.json', 'writeback-schedule.json',
                'backend-maintenance-current.json', 'config.json',
            ))
            if (not isinstance(manifest, dict) or
                    not set(manifest) <= archive_names | frozenset(('target_device',
                                                                     'pool_generation')) and
                    not all(name.startswith('maintenance/') and
                            os.path.normpath(name) == name and
                            not name.startswith('../') and '/..' not in name
                            for name in set(manifest) - archive_names -
                            frozenset(('target_device', 'pool_generation'))) or
                    not isinstance(manifest.get('config.json'), STRING_TYPES) or
                    re.match(r'^[0-9a-f]{64}$', manifest['config.json']) is None or
                    hashlib.sha256(archive_config_bytes).hexdigest() != manifest['config.json']):
                raise ValueError('BACKEND_MAINTENANCE_ARCHIVE_CONFIG_UNPROVEN')
            for name, digest in manifest.items():
                if name in ('target_device', 'pool_generation'):
                    if not isinstance(digest, STRING_TYPES):
                        raise ValueError('BACKEND_MAINTENANCE_ARCHIVE_MANIFEST_INVALID')
                elif (not isinstance(digest, STRING_TYPES) or
                      re.match(r'^[0-9a-f]{64}$', digest) is None):
                    raise ValueError('BACKEND_MAINTENANCE_ARCHIVE_MANIFEST_INVALID')
            progress = record.get('maintenanceProgress')
            controller_stop = (progress.get('controllerStop')
                               if isinstance(progress, dict) else None)
            controller_identity = (controller_stop.get('identity')
                                   if isinstance(controller_stop, dict) else None)
            if progress is not None and not isinstance(progress, dict):
                raise ValueError('BACKEND_MAINTENANCE_SOURCE_CONFIG_UNPROVEN')
            if isinstance(progress, dict) and 'controllerStop' in progress:
                if (not isinstance(controller_stop, dict) or
                        not isinstance(controller_identity, dict) or
                        controller_identity.get('sourceConfigSha256') != manifest['config.json'] or
                        controller_identity.get('templateSha256') !=
                        hashlib.sha256(template_bytes).hexdigest()):
                    raise ValueError('BACKEND_MAINTENANCE_SOURCE_CONFIG_UNPROVEN')
            # OpenRuntime writes a complete typed snapshot before changing
            # Backend. All non-backend effective fields must remain identical;
            # the original archive binds the stable template controls and any
            # backend already present before this request.
            current_without_backend = dict(parsed_current)
            current_without_backend.pop('backend')
            before_without_backend = dict(before_config)
            before_backend = before_without_backend.pop('backend', None)
            if canonical(current_without_backend) != canonical(before_without_backend):
                raise ValueError('BACKEND_MAINTENANCE_CONFIG_SNAPSHOT_MISMATCH')
            if ('backend' in archive_config) != ('backend' in before_config):
                raise ValueError('BACKEND_MAINTENANCE_PRIOR_BACKEND_UNPROVEN')
            if ('backend' in archive_config and
                    canonical(archive_config['backend']) != canonical(before_backend)):
                raise ValueError('BACKEND_MAINTENANCE_PRIOR_BACKEND_UNPROVEN')
            prior_preparation_records = {}
            if 'backend' in before_config:
                prior_required_files = ('backend-maintenance-current.json',
                                        'backend-ownership.json', 'backend-settings.json')
                prior_files = {}
                for name in prior_required_files:
                    digest = manifest.get(name)
                    if not isinstance(digest, STRING_TYPES) or re.match(
                            r'^[0-9a-f]{64}$', digest) is None:
                        raise ValueError('BACKEND_MAINTENANCE_PRIOR_BACKEND_UNPROVEN')
                    data = read_regular(os.path.join(archive_dir, name))
                    if hashlib.sha256(data).hexdigest() != digest:
                        raise ValueError('BACKEND_MAINTENANCE_PRIOR_BACKEND_UNPROVEN')
                    prior_files[name] = strict_json(data)
                prior_receipt = prior_files['backend-maintenance-current.json']
                prior_uuid = (prior_receipt.get('request_id')
                              if isinstance(prior_receipt, dict) else None)
                prior_boot = (prior_receipt.get('host_boot_id')
                              if isinstance(prior_receipt, dict) else None)
                prior_state, prior_record = ('missing', None)
                if (self._valid_identifier(prior_uuid) and
                        isinstance(prior_boot, STRING_TYPES) and prior_boot):
                    prior_state, prior_record = self._operation_file_state(prior_uuid)
                prior_evidence = (self._completed_backend_preparation_evidence(
                    prior_uuid, prior_record, host_uuid, prior_boot)
                    if prior_state == 'present' else None)
                owner = prior_files['backend-ownership.json']
                settings = prior_files['backend-settings.json']
                owner_fields = ('version', 'generation', 'configured', 'identity', 'claimed_at')
                owner_identity = owner.get('identity') if isinstance(owner, dict) else None
                owner_spec = owner.get('configured') if isinstance(owner, dict) else None
                if (prior_evidence is None or prior_evidence['receipt'] != prior_receipt or
                        prior_receipt.get('stage') != 'APPLIED' or
                        not isinstance(owner, dict) or
                        set(owner) != set(owner_fields) or
                        not exact_int(owner.get('version')) or owner.get('version') != 1 or
                        owner.get('generation') != prior_receipt.get('backend_resource_uuid') or
                        not isinstance(owner.get('claimed_at'), STRING_TYPES) or
                        canonical(owner_identity) !=
                        canonical(prior_receipt.get('target_identity')) or
                        not isinstance(settings, dict) or
                        not set(settings) <= set(('revision', 'desired', 'apply_state',
                                                  'request_id', 'request_fingerprint')) or
                        not set(('revision', 'desired', 'apply_state')) <= set(settings) or
                        isinstance(settings.get('revision'), bool) or
                        not exact_int(settings.get('revision')) or settings.get('revision') <= 0 or
                        settings.get('apply_state') != 'APPLIED' or
                        settings.get('request_id') != prior_uuid or
                        settings.get('request_fingerprint') !=
                        prior_receipt.get('request_fingerprint')):
                    raise ValueError('BACKEND_MAINTENANCE_PRIOR_BACKEND_UNPROVEN')
                prior_request = prior_evidence['request']
                prior_backend = prior_request.get('backend')
                check_object(owner_spec, ['device', 'minimum_filesystem_free_bytes'],
                             ['file_path'], {'device': 'string',
                                 'minimum_filesystem_free_bytes': 'int',
                                 'file_path': 'string'})
                check_object(owner_identity, ['boot_id', 'canonical_device', 'rdev',
                    'node_inode', 'sysfs_inode', 'capacity_bytes', 'direct_io',
                    'stack_sha256'], ['file_path', 'file_inode', 'file_device',
                    'file_size', 'file_stack_sha256'], {
                        'boot_id': 'string', 'canonical_device': 'string',
                        'rdev': 'int', 'node_inode': 'int', 'sysfs_inode': 'int',
                        'capacity_bytes': 'int', 'direct_io': 'bool',
                        'stack_sha256': 'string', 'file_path': 'string',
                        'file_inode': 'int', 'file_device': 'int', 'file_size': 'int',
                        'file_stack_sha256': 'string',
                    })
                check_object(prior_backend, ['minimum_filesystem_free_bytes', 'exclusive'],
                             ['device', 'file_path', 'size_bytes'], {
                                 'minimum_filesystem_free_bytes': 'int',
                                 'exclusive': 'bool', 'device': 'string',
                                 'file_path': 'string', 'size_bytes': 'int'})
                prior_spec = owner_spec
                settings_spec = (settings.get('desired')
                                 if isinstance(settings, dict) else None)
                if (not isinstance(prior_spec, dict) or
                        canonical(prior_spec) != canonical(before_backend) or
                        not isinstance(settings_spec, dict) or
                        canonical(settings_spec) != canonical(prior_backend)):
                    raise ValueError('BACKEND_MAINTENANCE_PRIOR_BACKEND_UNPROVEN')
                prior_preparation_records[prior_uuid] = prior_record
            for key in template_control_fields:
                template_has_value = key in template_config
                if ((key in parsed_current) != template_has_value or
                        (key in archive_config) != template_has_value or
                        (key in before_config) != template_has_value or
                        (template_has_value and
                         (canonical(parsed_current[key]) != canonical(template_config[key]) or
                          canonical(archive_config[key]) != canonical(template_config[key]) or
                          canonical(before_config[key]) != canonical(template_config[key])))):
                    raise ValueError('BACKEND_MAINTENANCE_TEMPLATE_CONTROL_MISMATCH')
            backend_spec = parsed_current['backend']
            active_control = self._get_active_control()
            offline_readback_bound = False
            if isinstance(stopped_command, dict):
                stopped_operation = stopped_command.get('operationUuid')
                stopped_record = self._load_operation(stopped_command)
                stopped_progress = (stopped_record.get('maintenanceProgress')
                                    if isinstance(stopped_record, dict) else None)
                stop = (stopped_progress.get('controllerStop')
                        if isinstance(stopped_progress, dict) else None)
                saved_proof = (stop.get('backendPreparationProof')
                               if isinstance(stop, dict) else None)
                stop_request = stop.get('request') if isinstance(stop, dict) else None
                identity = stop.get('identity') if isinstance(stop, dict) else None
                native_state = stop.get('nativeState') if isinstance(stop, dict) else None
                with open(self.zram_config_path, 'rb') as stream:
                    current_config_bytes = stream.read()
                record_hash = hashlib.sha256(
                    json.dumps(record, sort_keys=True, separators=(',', ':'))
                    .encode('utf-8')).hexdigest()
                expected_saved_proof = {
                    'operationUuid': operation_uuid, 'requestHash': record['requestHash'],
                    'resourceUuid': receipt['backend_resource_uuid'],
                    'recordSha256': record_hash,
                    'activeControlOperationUuid': active_control,
                    'serviceReadbackVerified': True,
                }
                offline_readback_bound = bool(
                    stopped_operation and self._valid_identifier(stopped_operation) and
                    isinstance(stopped_record, dict) and
                    stopped_record == self._load_operation({'operationUuid': stopped_operation}) and
                    stopped_record.get('operationUuid') == stopped_operation and
                    stopped_record.get('action') == 'prepareWritebackBackend' and
                    stopped_record.get('hostUuid') == host_uuid and
                    stopped_record.get('bootId') == boot_id and
                    stopped_record.get('requestHash') == self._operation_hash(stopped_command) and
                    stopped_record.get('stage') in ('PREPARING', 'DRAINING', 'UNKNOWN') and
                    isinstance(stop, dict) and stop.get('attempted') is True and
                    stop.get('completed') is True and stop.get('workerLaunchAttempted') is False and
                    stop.get('hostUuid') == host_uuid and stop.get('bootId') == boot_id and
                    stop.get('requestHash') == stopped_record.get('requestHash') and
                    ((stopped_record.get('stage') == 'UNKNOWN' and
                      stop.get('continuationReady') is True) or
                     (stopped_record.get('stage') == 'PREPARING' and
                      (stop.get('continuationReady') is None or
                       stop.get('continuationReady') is False or
                       stop.get('continuationReady') is True)) or
                     (stopped_record.get('stage') not in ('PREPARING', 'UNKNOWN') and
                      (stop.get('continuationReady') is None or
                       stop.get('continuationReady') is False))) and
                    not os.path.lexists(stopped_record.get('maintenanceIntentPath', '')) and
                    isinstance(identity, dict) and identity.get('bootId') == boot_id and
                    identity.get('unit') == self.MANAGED_ZRAM_UNIT and
                    identity.get('killMode') == 'process' and identity.get('restart') == 'no' and
                    isinstance(identity.get('pid'), INTEGER_TYPES) and
                    not isinstance(identity.get('pid'), bool) and identity.get('pid') > 0 and
                    isinstance(identity.get('processStartTime'), STRING_TYPES) and
                    identity.get('processStartTime').isdigit() and
                    all(re.match(r'^[0-9a-f]{64}$', str(identity.get(key, ''))) is not None
                        for key in ('unitSha256', 'binarySha256', 'templateSha256',
                                    'sourceConfigSha256')) and
                    identity.get('sourceConfigSha256') == hashlib.sha256(
                        current_config_bytes).hexdigest() and
                    isinstance(stop_request, dict) and
                    stop_request.get('request_id') == stopped_operation and
                    stop_request.get('expected_host_boot_id') == boot_id and
                    stop_request.get('expected_pool_generation') == 'none' and
                    isinstance(native_state, dict) and
                    isinstance(stop.get('nativeStateCheckedAt'), (int, float)) and
                    self._first_use_state_safe(
                        native_state, observation_time=stop.get('nativeStateCheckedAt')) and
                    saved_proof == expected_saved_proof and
                    self._maintenance_service_state() == 'inactive')
            intent_control = intent.get('controlOperationUuid')
            if intent_control is not None:
                if not self._valid_identifier(intent_control):
                    raise ValueError('BACKEND_MAINTENANCE_ACTIVE_CONTROL_UNPROVEN')
                # The intent links the preparation to its historical control;
                # current authorization is proved independently below.
                intent_record = self._load_operation({'operationUuid': intent_control})
                intent_is_ksm = (self._first_use_terminal_ksm_record(
                    intent_record, allow_empty_noop=True) or
                    self._first_use_backend_bound_ksm_record(
                        intent_record, prior_preparation_records) if
                    isinstance(intent_record, dict) else False)
                if (not isinstance(intent_record, dict) or
                        intent_record.get('operationUuid') != intent_control or
                        not (intent_is_ksm or
                             self._first_use_terminal_service_disable(intent_record))):
                    raise ValueError('BACKEND_MAINTENANCE_ACTIVE_CONTROL_UNPROVEN')
            if active_control:
                # Preserve the existing KSM-only exception, but independently
                # require the current active control's same-boot terminal
                # journal and live native ACK. A generic applied Host policy
                # must not bless first-use history.
                active_record = self._load_operation({'operationUuid': active_control})
                active_readback = (active_record.get('readback')
                                   if isinstance(active_record, dict) else None)
                active_revision = (active_record.get('desiredRevision')
                                   if isinstance(active_record, dict) else None)
                if not isinstance(active_record, dict):
                    raise ValueError('BACKEND_MAINTENANCE_ACTIVE_CONTROL_UNPROVEN')
                active_ksm_record = self._first_use_terminal_ksm_record(
                    active_record, allow_empty_noop=True)
                if not active_ksm_record:
                    active_ksm_record = self._first_use_backend_bound_ksm_record(
                        active_record, {operation_uuid: record}, expected_boot=boot_id,
                        expected_operation=active_control,
                        expected_resource_uuid=receipt.get('backend_resource_uuid'),
                        expected_capacity=evidence['request'].get('backend_capacity_bytes'))
                if not active_ksm_record:
                    # An earlier backend may remain as disabled metadata in
                    # the active KSM-only control after this request prepared
                    # a different backend. Accept it only when the verified
                    # archive contains the exact completed preparation for A.
                    active_ksm_record = self._first_use_backend_bound_ksm_record(
                        active_record, prior_preparation_records,
                        expected_boot=boot_id, expected_operation=active_control)
                if active_ksm_record:
                    active_ksm_policy = (active_record.get('policy') or {}).get('ksm')
                    if active_ksm_policy:
                        if (active_record.get('bootId') != boot_id or
                                not isinstance(active_readback, dict) or
                            not self._ksm_proof_matches(active_readback.get('ksmReadback'),
                                                        active_revision)):
                            raise ValueError('BACKEND_MAINTENANCE_ACTIVE_CONTROL_UNPROVEN')
                elif (active_record.get('bootId') != boot_id or
                      not self._first_use_active_service_disable_safe(
                          active_record, stopped_command)):
                    raise ValueError('BACKEND_MAINTENANCE_ACTIVE_CONTROL_UNPROVEN')
            request = evidence['request']
            if (not isinstance(request, dict) or
                    set(request) != frozenset(('request_id', 'candidate_id',
                        'expected_host_boot_id', 'expected_pool_generation',
                        'backend_capacity_bytes', 'target_identity', 'backend',
                        'reset_confirmed')) or
                    request.get('request_id') != operation_uuid or
                    request.get('expected_host_boot_id') != boot_id or
                    request.get('expected_pool_generation') != 'none' or
                    request.get('reset_confirmed') is not True or
                    not isinstance(request.get('candidate_id'), STRING_TYPES) or
                    re.match(r'^candidate:[0-9a-f]{64}$', request.get('candidate_id')) is None or
                    not isinstance(request.get('backend'), dict) or
                    set(request['backend']) != frozenset((
                        'device', 'minimum_filesystem_free_bytes', 'exclusive')) or
                    request['backend'].get('exclusive') is not True or
                    not isinstance(request['backend'].get('device'), STRING_TYPES) or
                    isinstance(request['backend'].get('minimum_filesystem_free_bytes'), bool) or
                    not isinstance(request['backend'].get('minimum_filesystem_free_bytes'), INTEGER_TYPES) or
                    request['backend'].get('minimum_filesystem_free_bytes') < 0):
                raise ValueError('BACKEND_MAINTENANCE_REQUEST_UNPROVEN')
            target = request.get('target_identity')
            capacity = request.get('backend_capacity_bytes')
            if (not isinstance(target, dict) or target.get('boot_id') != boot_id or
                    isinstance(capacity, bool) or not isinstance(capacity, INTEGER_TYPES) or
                    capacity <= 0 or target.get('capacity_bytes') != capacity or
                    target.get('canonical_device') != request['backend'].get('device') or
                    backend_spec != {'device': request['backend']['device'],
                                     'minimum_filesystem_free_bytes':
                                         request['backend']['minimum_filesystem_free_bytes']}):
                raise ValueError('BACKEND_MAINTENANCE_TARGET_UNPROVEN')
            if (evidence['receipt'] != receipt or
                    not self._maintenance_receipt_matches_request(receipt, request, boot_id) or
                    not isinstance(receipt.get('request_fingerprint'), STRING_TYPES) or
                    re.match(r'^[0-9a-f]{64}$', receipt.get('request_fingerprint')) is None or
                    not isinstance(receipt.get('backend_resource_uuid'), STRING_TYPES) or
                    re.match(r'^[0-9a-f]{32}$', receipt.get('backend_resource_uuid')) is None):
                raise ValueError('BACKEND_MAINTENANCE_RECEIPT_UNPROVEN')
            if not offline_readback_bound:
                readback_ok, readback_error = self._verify_maintenance_service_readback(
                    host_uuid, request, receipt)
                if not readback_ok:
                    raise ValueError(readback_error or 'BACKEND_MAINTENANCE_SERVICE_READBACK_UNPROVEN')
            return {'operationUuid': operation_uuid, 'requestHash': record['requestHash'],
                    'resourceUuid': receipt['backend_resource_uuid'], 'record': record,
                    'stopProof': {
                        'operationUuid': operation_uuid,
                        'requestHash': record['requestHash'],
                        'resourceUuid': receipt['backend_resource_uuid'],
                        'recordSha256': hashlib.sha256(
                            json.dumps(record, sort_keys=True, separators=(',', ':'))
                            .encode('utf-8')).hexdigest(),
                        'activeControlOperationUuid': active_control,
                        'serviceReadbackVerified': True,
                    }}
        except (IOError, OSError, ValueError, TypeError, KeyError):
            raise RuntimeError('FIRST_ZRAM_BACKEND_PREPARATION_UNPROVEN')

    def _archive_foreign_host_history(self):
        """Move journals written under another Host UUID out of the fence directory.

        A Host deleted and re-added in the cloud keeps its old Agent journals.
        They are not evidence for the current identity, which is verified again
        from live native state; keep them archived instead of fencing forever.
        """
        host = self._load_host_uuid()
        directory = self.operation_dir
        if not self._valid_identifier(host) or not os.path.isdir(directory) or os.path.islink(directory):
            return
        foreign = set()
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if not name.endswith('.json') or os.path.islink(path) or not os.path.isfile(path):
                continue
            try:
                with open(path) as stream:
                    record = json.load(stream)
            except (IOError, OSError, ValueError):
                continue
            owner = record.get('hostUuid') if isinstance(record, dict) else None
            if self._valid_identifier(owner) and owner != host and record.get('operationUuid') == name[:-5]:
                foreign.add(name[:-5])
        if not foreign:
            return
        archive = os.path.join(os.path.dirname(directory), 'foreign-host-operations',
                               '%d-%s' % (int(time.time() * 1000), host))
        try:
            os.makedirs(archive)
            for name in os.listdir(directory):
                if name.split('.', 1)[0] in foreign:
                    os.rename(os.path.join(directory, name), os.path.join(archive, name))
            if self._get_active_control() in foreign:
                os.rename(self.active_control_path, os.path.join(archive, 'active-control'))
        except (IOError, OSError) as exc:
            logger.warn('foreign host memory journals were not archived: %s', exc)

    def _first_use_local_history_clear(self, command, rejected_record=None,
                                       backend_preparation=None, failed_backend_record=None):
        """Permit proven KSM/VM, service-disable and completed backend-prep history."""
        operation_uuid = command['operationUuid']
        directory = self.operation_dir
        if (not os.path.isdir(directory) or os.path.islink(directory) or
                os.path.realpath(directory) != directory):
            return False
        try:
            active = ''
            if os.path.lexists(self.active_control_path):
                if os.path.islink(self.active_control_path):
                    return False
                with open(self.active_control_path, 'r') as stream:
                    active = stream.read().strip()
            names = os.listdir(directory)
            allowed = {'.host-control.flock', 'active-control', 'vm-bindings',
                       'drain', 'backend-maintenance'}
            completed_preparations = {}
            for name in names:
                path = os.path.join(directory, name)
                if name.endswith('.json') and os.path.isfile(path) and not os.path.islink(path):
                    with open(path, 'r') as stream:
                        candidate_record = json.load(stream)
                    if (isinstance(candidate_record, dict) and
                            candidate_record.get('action') == 'prepareWritebackBackend'):
                        candidate_uuid = name[:-5]
                        # The current cold-prepare operation is validated in
                        # the exact operation branch below. It is intentionally
                        # not historical completed-preparation evidence yet.
                        if candidate_uuid == operation_uuid:
                            continue
                        evidence = self._completed_backend_preparation_evidence(
                            candidate_uuid, candidate_record)
                        if evidence is None:
                            return False
                        completed_preparations[candidate_uuid] = candidate_record
            if bool(completed_preparations) != (backend_preparation is not None):
                failed_prepare_context = (
                    backend_preparation is not None and
                    backend_preparation.get('operationUuid') == operation_uuid and
                    'record' not in backend_preparation and
                    isinstance(failed_backend_record, dict) and
                    failed_backend_record.get('operationUuid') == operation_uuid)
                if not failed_prepare_context:
                    return False
            if (backend_preparation is not None and
                    completed_preparations.get(backend_preparation.get('operationUuid')) !=
                    backend_preparation.get('record')):
                return False
            for name in names:
                path = os.path.join(directory, name)
                if os.path.islink(path):
                    return False
                if name in allowed:
                    if name == 'drain':
                        if not os.path.isdir(path) or os.listdir(path):
                            return False
                    elif name == 'backend-maintenance':
                        if not os.path.isdir(path) or os.path.realpath(path) != path:
                            return False
                        expected = {operation_id + suffix for operation_id in completed_preparations
                                    for suffix in ('.request.json', '.receipt.json',
                                                   '.stderr', '.intent.json')}
                        if (backend_preparation is not None and
                                'record' not in backend_preparation and
                                backend_preparation.get('operationUuid') == operation_uuid and
                                isinstance(failed_backend_record, dict) and
                                failed_backend_record.get('operationUuid') == operation_uuid):
                            expected.update(operation_uuid + suffix for suffix in (
                                '.request.json', '.receipt.json', '.stderr', '.intent.json'))
                        if set(os.listdir(path)) != expected:
                            return False
                    elif name == 'vm-bindings':
                        if not os.path.isdir(path) or not self._cold_ksm_vm_bindings_valid(path):
                            return False
                    elif name in ('.host-control.flock', 'active-control') and not os.path.isfile(path):
                        return False
                    continue
                if name.startswith('.operation-') or name.startswith('.active-control-'):
                    return False
                if not name.endswith('.json') or not os.path.isfile(path):
                    return False
                with open(path, 'r') as stream:
                    record = json.load(stream)
                if (not self._valid_identifier(name[:-5]) or not isinstance(record, dict) or
                        record.get('operationUuid') != name[:-5]):
                    return False
                if name[:-5] == operation_uuid:
                    if (rejected_record is not None and record == rejected_record and
                            self._first_use_admission_rejected(record)):
                        continue
                    failed_stop = ((record.get('maintenanceProgress') or {}).get('controllerStop')
                                   if isinstance(record.get('maintenanceProgress'), dict) else None)
                    failed_identity = (failed_stop.get('identity')
                                       if isinstance(failed_stop, dict) else None)
                    failed_request = (failed_stop.get('request')
                                      if isinstance(failed_stop, dict) else None)
                    failed_backend = (
                        failed_backend_record is not None and record == failed_backend_record and
                        record.get('stage') in ('DRAINING', 'UNKNOWN', 'FAILED_REQUIRES_REVIEW') and
                        record.get('action') == 'prepareWritebackBackend' and
                        record.get('hostUuid') == self._load_host_uuid() and
                        record.get('bootId') == self._current_boot_id() and
                        record.get('requestHash') == self._operation_hash(command) and
                        isinstance(failed_stop, dict) and failed_stop.get('attempted') is True and
                        failed_stop.get('completed') is True and
                        failed_stop.get('continuationReady') is True and
                        failed_stop.get('workerLaunchAttempted') is True and
                        failed_stop.get('hostUuid') == record.get('hostUuid') and
                        failed_stop.get('bootId') == record.get('bootId') and
                        failed_stop.get('requestHash') == record.get('requestHash') and
                        isinstance(failed_identity, dict) and
                        failed_identity.get('bootId') == self._current_boot_id() and
                        failed_identity.get('unit') == self.MANAGED_ZRAM_UNIT and
                        failed_identity.get('killMode') == 'process' and
                        failed_identity.get('restart') == 'no' and
                        all(re.match(r'^[0-9a-f]{64}$', str(failed_identity.get(key, ''))) for key in
                            ('unitSha256', 'binarySha256', 'templateSha256', 'sourceConfigSha256')) and
                        isinstance(failed_request, dict) and
                        failed_request.get('request_id') == operation_uuid and
                        failed_request.get('expected_host_boot_id') == self._current_boot_id() and
                        failed_request.get('expected_pool_generation') == 'none' and
                        isinstance(failed_request.get('target_identity'), dict) and
                        failed_request['target_identity'].get('boot_id') == self._current_boot_id() and
                        isinstance(failed_stop.get('nativeState'), dict) and
                        self._first_use_state_safe(
                            failed_stop['nativeState'],
                            observation_time=failed_stop.get('nativeStateCheckedAt')))
                    if failed_backend:
                        continue
                    stop = ((record.get('maintenanceProgress') or {}).get('controllerStop')
                            if isinstance(record.get('maintenanceProgress'), dict) else None)
                    identity = stop.get('identity') if isinstance(stop, dict) else None
                    stop_request = stop.get('request') if isinstance(stop, dict) else None
                    stop_unknown = (record.get('stage') == 'UNKNOWN' and
                                    record.get('action') == 'prepareWritebackBackend' and
                                    isinstance(stop, dict) and stop.get('attempted') is True and
                                    stop.get('workerLaunchAttempted') is False and
                                    stop.get('hostUuid') == self._load_host_uuid() and
                                    stop.get('bootId') == self._current_boot_id() and
                                    stop.get('requestHash') == self._operation_hash(command) and
                                    isinstance(identity, dict) and
                                    isinstance(identity.get('pid'), INTEGER_TYPES) and
                                    not isinstance(identity.get('pid'), bool) and identity['pid'] > 0 and
                                    isinstance(identity.get('processStartTime'), STRING_TYPES) and
                                    identity['processStartTime'].isdigit() and
                                    identity.get('bootId') == self._current_boot_id() and
                                    identity.get('unit') == self.MANAGED_ZRAM_UNIT and
                                    identity.get('unitPath') ==
                                    '/usr/lib/systemd/system/zram-memory.service' and
                                    identity.get('killMode') == 'process' and
                                    identity.get('restart') == 'no' and
                                    all(re.match(r'^[0-9a-f]{64}$', str(identity.get(key, ''))) for key in
                                        ('unitSha256', 'binarySha256', 'templateSha256',
                                         'sourceConfigSha256')) and
                                    isinstance(stop_request, dict) and
                                    stop_request.get('request_id') == operation_uuid and
                                    stop_request.get('expected_host_boot_id') == self._current_boot_id() and
                                    stop_request.get('expected_pool_generation') == 'none' and
                                    isinstance(stop_request.get('target_identity'), dict) and
                                    stop_request['target_identity'].get('boot_id') ==
                                    self._current_boot_id() and
                                    isinstance(stop.get('nativeState'), dict) and
                                    self._first_use_state_safe(
                                        stop['nativeState'],
                                        observation_time=stop.get('nativeStateCheckedAt')))
                    if (not isinstance(record, dict) or
                            record.get('operationUuid') != operation_uuid or
                            (record.get('stage') != 'PREPARING' and not stop_unknown) or
                            record.get('requestHash') != self._operation_hash(command)):
                        return False
                    continue
                if (name[:-5] in completed_preparations and
                        record == completed_preparations[name[:-5]]):
                    continue
                if not (self._first_use_terminal_ksm_record(record, allow_empty_noop=True) or
                        self._first_use_backend_bound_ksm_record(
                            record, completed_preparations) or
                        self._first_use_terminal_service_disable(record) or
                        self._first_use_terminal_vm_binding(record) or
                        self._first_use_admission_not_issued(record) or
                        self._first_use_ksm_prewrite_rejection(record)):
                    return False
            if active:
                active_record = self._load_operation({'operationUuid': active})
                active_backend_bound = False
                if (backend_preparation is not None and
                        isinstance(backend_preparation.get('record'), dict) and
                        isinstance(backend_preparation.get('stopProof'), dict)):
                    expected_active = backend_preparation['stopProof'].get(
                        'activeControlOperationUuid')
                    if active == expected_active:
                        active_backend_bound = self._first_use_backend_bound_ksm_record(
                            active_record,
                            {backend_preparation['operationUuid']:
                             backend_preparation['record']},
                            expected_boot=self._current_boot_id(),
                            expected_operation=active,
                            expected_resource_uuid=backend_preparation.get('resourceUuid'),
                            expected_capacity=(backend_preparation['record'].get(
                                'backendPreparation') or {}).get('backendCapacityBytes'))
                        if not active_backend_bound:
                            # A prior disabled backend may remain on the active
                            # KSM-only control after the current preparation has
                            # replaced it. The history whitelist above has
                            # already validated each prior preparation; match
                            # this control only to that exact completed set.
                            active_backend_bound = self._first_use_backend_bound_ksm_record(
                                active_record, completed_preparations,
                                expected_boot=self._current_boot_id(),
                                expected_operation=active)
                if (self._first_use_terminal_ksm_record(
                        active_record, allow_empty_noop=True) or active_backend_bound):
                    active_readback = active_record.get('readback') or {}
                    active_revision = active_record.get('desiredRevision')
                    # A new first-use request must match current KSM ownership.
                    # The rejection-only caller already proves, under this lock,
                    # that its exact same-boot request never authorized/wrote ZRAM.
                    # Keep validating the original terminal KSM receipt above, but
                    # do not require historical settings to match today's config
                    # just to record that this rejected request was not issued.
                    # A completed empty target released KSM policy ownership;
                    # its full historical ACK proves completion, not a setting
                    # that a later first-use operation may restore or enforce.
                    if (rejected_record is None and
                            (active_record.get('policy') or {}).get('ksm') and
                            not self._ksm_proof_matches(active_readback.get('ksmReadback'),
                                                        active_revision)):
                        return False
                elif not self._first_use_active_service_disable_safe(
                        active_record, command, failed_backend_record=failed_backend_record):
                    return False
            return True
        except (IOError, OSError, ValueError, TypeError):
            return False

    def _reconcile_first_zram_admission(self, command, prior):
        """Resolve a pre-authorization rejection by GETs only; never retry it."""
        lock = None
        try:
            lock = self._acquire_host_control_lock()
            latest = self._load_operation(command)
            evidence = latest.get('applyEvidence') if isinstance(latest, dict) else None
            readback = latest.get('readback') if isinstance(latest, dict) else None
            prewrite_reason = ('FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE',
                               'KSM_CLEAR_PRIOR_JOURNAL_INVALID')
            prewrite_candidate = (
                isinstance(latest, dict) and latest.get('stage') in ('UNKNOWN', 'NOT_ISSUED') and
                any(isinstance(section, dict) and section.get('reason') in prewrite_reason
                    for section in (evidence, readback)))
            if (latest != prior or
                    (not self._first_use_admission_rejected(latest) and not prewrite_candidate) or
                    command.get('hostUuid') != self._load_host_uuid() or
                    command.get('operationUuid') != latest.get('operationUuid')):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN')
            if latest.get('bootId') != self._current_boot_id():
                raise RuntimeError('FIRST_ZRAM_RECONCILE_BOOT_CHANGED')
            reason = (latest.get('applyEvidence') or {}).get('reason')
            if reason == 'FIRST_ZRAM_LOCAL_CONTROL_FENCED' and \
                    self._first_use_admission_not_issued(latest):
                # Keep the pre-existing local-fence compatibility behavior.
                return latest['readback']
            if reason in ('FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE',
                          'KSM_CLEAR_PRIOR_JOURNAL_INVALID'):
                # MemoryOptimizationManager sends a query command, not the
                # original apply policy. Bind it to the immutable apply record
                # and use that record's policy/hash for all eligibility checks.
                submitted = command.get('taskSubmittedAt')
                boot_epoch = self._boot_epoch_millis()
                updated_at = latest.get('updatedAt')
                if (command.get('action') != 'reconcile' or
                        command.get('reconcileAction') != 'seal-if-never-issued' or
                        command.get('policy') != {} or
                        command.get('hostUuid') != latest.get('hostUuid') or
                        command.get('scope') != latest.get('scope') or
                        command.get('resourceUuid') != latest.get('resourceUuid') or
                        command.get('desiredRevision') != latest.get('desiredRevision') or
                        command.get('bootId') != self._current_boot_id() or
                        latest.get('bootId') != self._current_boot_id() or
                        isinstance(submitted, bool) or not isinstance(submitted, INTEGER_TYPES) or
                        isinstance(boot_epoch, bool) or not isinstance(boot_epoch, INTEGER_TYPES) or
                        submitted < boot_epoch or submitted > int(time.time() * 1000) or
                        isinstance(updated_at, bool) or not isinstance(updated_at, INTEGER_TYPES) or
                        submitted > updated_at or
                        not self._first_use_admission_rejected(latest) or
                        latest.get('policyHash') != self._policy_digest(latest.get('policy')) or
                        (latest.get('stage') == 'UNKNOWN' and
                         (not isinstance(latest.get('readback'), dict) or
                          latest.get('readback') != latest.get('applyEvidence'))) or
                        any(key in latest for key in ('firstZramUse', 'activationIntent',
                                                      'maintenanceProof', 'mixedClearEvidence',
                                                      'maintenanceProgress'))):
                    raise RuntimeError('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN')
                if self._first_use_admission_not_issued(latest):
                    return latest['readback']
                if latest.get('stage') != 'UNKNOWN':
                    raise RuntimeError('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN')
                if reason == 'FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE':
                    if (not self._first_zram_enable_requested(latest) or
                            os.path.islink(self.zram_config_path) or
                            os.path.islink(self.zram_config_template_path) or
                            not os.path.isfile(self.zram_config_path) or
                            not os.path.isfile(self.zram_config_template_path)):
                        raise RuntimeError('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN')
                    with open(self.zram_config_path, 'rb') as stream:
                        current = stream.read()
                    with open(self.zram_config_template_path, 'rb') as stream:
                        template = stream.read()
                    try:
                        current_config = json.loads(current.decode('utf-8'))
                        template_config = json.loads(template.decode('utf-8'))
                    except (UnicodeError, ValueError):
                        raise RuntimeError('FIRST_ZRAM_CONFIG_READBACK_UNKNOWN')
                    if current != template:
                        self._first_use_backend_preparation_proof(
                            current_config, template_config)
                    self._first_use_runtime_identity(template, current)
                else:
                    state_dir = self._read_maintenance_config()[1]
                    current_path = os.path.join(state_dir, 'backend-maintenance', 'current.json')
                    if (not os.path.isfile(current_path) or os.path.islink(current_path) or
                        latest.get('policyMode') != 'effective'):
                        raise RuntimeError('FIRST_ZRAM_BACKEND_PREPARATION_UNPROVEN')
                native = self._service_request('state', {})
                cpu_state = self._service_request('host-cpu-state', {})
                if (not isinstance(native, dict) or not isinstance(cpu_state, dict) or
                        cpu_state.get('efficiency_enabled') is not False):
                    raise RuntimeError('FIRST_ZRAM_RECONCILE_READBACK_UNKNOWN')
                native = dict(native)
                native['host_cpu'] = cpu_state
                if not self._first_use_state_safe(
                        native, allow_host_pressure_unavailable=True):
                    raise RuntimeError('FIRST_ZRAM_RECONCILE_READBACK_UNKNOWN')
                if not self._first_use_no_pool_verified(
                        {'operationUuid': latest['operationUuid']}, rejected_record=latest):
                    raise RuntimeError('FIRST_ZRAM_LOCAL_CONTROL_FENCED')
                result = {'success': False, 'status': 'Failed',
                          'reasonCode': 'FIRST_ZRAM_ADMISSION_NOT_ISSUED',
                          'operationUuid': latest['operationUuid'],
                          'state': {'phase': 'NOT_ISSUED', 'bootId': latest['bootId'],
                                    'requestHash': latest['requestHash'],
                                    'policyWritesIssued': False}}
                updated = dict(latest, stage='NOT_ISSUED', readback=result,
                               updatedAt=int(time.time() * 1000))
                if not self._write_operation_record(updated):
                    raise RuntimeError('FIRST_ZRAM_RECONCILE_JOURNAL_UNAVAILABLE')
                return result
            if prewrite_candidate:
                # A reason mismatch or malformed immutable policy is still an
                # unresolved operation. Do not let it fall through to the
                # generic reconciler, which may update its readback.
                raise RuntimeError('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN')
            if (os.path.islink(self.zram_config_path) or os.path.islink(self.zram_config_template_path) or
                    not os.path.isfile(self.zram_config_path) or
                    not os.path.isfile(self.zram_config_template_path)):
                raise RuntimeError('FIRST_ZRAM_CONFIG_READ_UNKNOWN')
            with open(self.zram_config_path, 'rb') as stream:
                current = stream.read()
            with open(self.zram_config_template_path, 'rb') as stream:
                template = stream.read()
            config = json.loads(current.decode('utf-8'))
            if (current != template or not isinstance(config, dict) or
                    config.get('managed') is not True or config.get('mode') != 'observe' or
                    config.get('resource_authorized') is not False or
                    config.get('initial_efficiency_enabled') is not False):
                raise RuntimeError('FIRST_ZRAM_CONFIG_READBACK_UNKNOWN')
            self._first_use_runtime_identity(template, current)
            native = self._service_request('state', {})
            native['host_cpu'] = self._service_request('host-cpu-state', {})
            if not self._first_use_state_safe(native):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_STATE_UNKNOWN')
            if not self._first_use_local_history_clear(command, rejected_record=latest):
                raise RuntimeError('FIRST_ZRAM_LOCAL_CONTROL_FENCED')
            result = {'success': False, 'status': 'Failed',
                      'reasonCode': 'FIRST_ZRAM_ADMISSION_NOT_ISSUED',
                      'operationUuid': latest['operationUuid'],
                      'state': {'phase': 'NOT_ISSUED', 'bootId': latest['bootId'],
                                'requestHash': latest['requestHash'], 'policyWritesIssued': False}}
            # Keep the original request/hash/applyEvidence, and durably reject
            # replay of this ID. Only the outcome proof is appended/updated.
            updated = dict(latest, stage='NOT_ISSUED', readback=result,
                           updatedAt=int(time.time() * 1000))
            if not self._write_operation_record(updated):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_JOURNAL_UNAVAILABLE')
            return result
        except Exception as exc:
            # In particular, lock contention/stale snapshots must not change
            # another writer's record or erase the original rejection proof.
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'operationUuid': command.get('operationUuid'),
                    'reasonCode': str(exc) if re.match(r'^[A-Z][A-Z0-9_]+$', str(exc)) else
                    'FIRST_ZRAM_RECONCILE_READBACK_UNKNOWN'}
        finally:
            self._release_operation(lock)

    def _first_use_state_safe(self, native, require_reclaim=False, observation_time=None,
                              allow_failed_backend_maintenance=False,
                              allow_host_pressure_unavailable=False):
        if not isinstance(native, dict):
            return False
        lifecycle = native.get('lifecycle')
        pool = native.get('host_zram')
        host = native.get('host')
        pending = native.get('pending_operations')
        expected_mode = 'reclaim' if require_reclaim else 'observe'
        expected_auth = True if require_reclaim else False
        cpu = native.get('host_cpu') or native.get('host_cpu_state')
        # RuntimeSnapshot always serializes Pending, but an empty Go slice is
        # encoded as JSON null. LifecycleSnapshot always carries its ABI and
        # readback fields; MigrationHold is intentionally omitted when nil.
        # Accept only those exact wire forms, not arbitrary missing evidence.
        if 'pending_operations' not in native:
            return False
        if native.get('pending_operations') is None:
            pending = []
        elif isinstance(native.get('pending_operations'), list):
            pending = native['pending_operations']
        else:
            return False
        lifecycle_state = lifecycle.get('activeState') if isinstance(lifecycle, dict) else None
        hold_ok = (isinstance(lifecycle, dict) and
                   ('migrationHold' not in lifecycle or lifecycle.get('migrationHold') is None))
        maintenance_ok = (native.get('maintenance_blocks_activation') is False and
                          not allow_failed_backend_maintenance)
        if allow_failed_backend_maintenance:
            maintenance_ok = (native.get('maintenance_blocks_activation') is True and
                              native.get('reason') == 'MAINTENANCE_BLOCKS_ACTIVATION')
        if (native.get('mode') != expected_mode or
                native.get('resource_authorized') is not expected_auth or
                not isinstance(lifecycle, dict) or lifecycle.get('schemaVersion') != 1 or
                lifecycle.get('abiProfile') != 'zram-service-v1' or
                lifecycle.get('readbackAllowed') is not True or 'paused' not in lifecycle or
                lifecycle.get('paused') is not False or
                not hold_ok or lifecycle_state != 'compatibility' or
                not maintenance_ok or
                pending or
                not self._is_uninitialized_pool_snapshot(pool) or
                not isinstance(host, dict) or
                (not allow_host_pressure_unavailable and
                 (host.get('qualified') is not True or host.get('safe') is not True)) or
                not self._native_observation_is_fresh(
                    native.get('observed_at'), 3, now=observation_time) or
                (not allow_host_pressure_unavailable and
                 not self._native_observation_is_fresh(
                     host.get('observed_at'), 3, now=observation_time))):
            return False
        if not isinstance(cpu, dict) or cpu.get('efficiency_enabled') is not False:
            return False
        return True

    @staticmethod
    def _verify_first_use_rpm_files(config_bytes):
        """Require RPM verification to report no drift outside managed config."""
        command = ['rpm', '-V', 'zstack-zram']
        try:
            output = MemoryOptimizationPlugin._bounded_command_output(command, 30)
            exit_code = 0
        except subprocess.CalledProcessError as exc:
            # rpm -V uses exit 1 to report a package-file mismatch. That is
            # expected only for the config atomically changed by this
            # manager-authorized first-use path; any other status/output is
            # treated as package identity uncertainty.
            if exc.returncode != 1:
                raise RuntimeError('FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH')
            output = getattr(exc, 'output', None)
            exit_code = exc.returncode
        if output is None:
            raise RuntimeError('FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH')
        if not isinstance(output, STRING_TYPES):
            output = output.decode('utf-8')
        # This is the actual config path shipped by zstack-zram and consumed by
        # the vendor unit.  RPM verification may report drift here only after
        # the manager-authorized first-use mutation; every other package file
        # must still match its RPM payload.
        allowed = '/etc/zram-memory/config.json'
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if exit_code == 0 and lines:
            raise RuntimeError('FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH')
        if exit_code == 1 and len(lines) != 1:
            raise RuntimeError('FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH')
        for line in lines:
            fields = line.split()
            flags_ok = (len(fields) == 3 and len(fields[0]) == 9 and
                        fields[0][0] in 'S.' and fields[0][1] == '.' and
                        fields[0][2] in '5.' and fields[0][3:7] == '....' and
                        fields[0][7] in 'T.' and fields[0][8] == '.')
            if (not flags_ok or
                    fields[1] != 'c' or
                    not re.match(r'^[.SM5DLUGTP]{9}\Z', fields[0]) or
                    fields[-1] != allowed):
                raise RuntimeError('FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH')
        # The generated config is not required to retain the RPM's mode or
        # digest after authorization, but its exact bytes are separately bound
        # into the durable first-use receipt.
        return hashlib.sha256(config_bytes).hexdigest()

    @staticmethod
    def _first_use_runtime_identity(template_bytes, config_bytes):
        """Bind first-use authorization to the effective RPM service process."""
        try:
            output = MemoryOptimizationPlugin._bounded_command_output([
                'systemctl', 'show', 'zram-memory.service',
                '--property=FragmentPath,DropInPaths,MainPID,ActiveState'], 5)
            if not isinstance(output, STRING_TYPES):
                output = output.decode('utf-8')
            props = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
            if (props.get('FragmentPath') != '/usr/lib/systemd/system/zram-memory.service' or
                    props.get('DropInPaths', '').strip() or props.get('ActiveState') != 'active'):
                raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_UNKNOWN')
            pid = props.get('MainPID', '')
            if not pid.isdigit() or int(pid) <= 0:
                raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_UNKNOWN')
            exe_path = '/proc/%s/exe' % pid
            actual_exe = os.readlink(exe_path)
            if actual_exe.endswith(' (deleted)'):
                raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_UNKNOWN')
            if os.path.realpath(actual_exe) != '/usr/local/libexec/zram-efficiency':
                raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_UNKNOWN')
            with open('/proc/%s/stat' % pid, 'r') as stream:
                stat_text = stream.read()
            _comm, delim, tail = stat_text.rpartition(')')
            fields = tail.split()
            if not delim or len(fields) <= 19 or not fields[19].isdigit():
                raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_UNKNOWN')
            package = MemoryOptimizationPlugin._bounded_command_output([
                'rpm', '-q', '--qf', '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}', 'zstack-zram'], 30)
            owners = {}
            for path in ('/usr/lib/systemd/system/zram-memory.service',
                         '/usr/share/zstack-zram/config.json',
                         '/usr/local/libexec/zram-efficiency'):
                value = MemoryOptimizationPlugin._bounded_command_output(
                    ['rpm', '-qf', '--qf', '%{NAME}', path], 30)
                owners[path] = value.decode('utf-8').strip() if not isinstance(value, STRING_TYPES) else value.strip()
            if not isinstance(package, STRING_TYPES):
                package = package.decode('utf-8')
            package = package.strip()
            if any(owner != 'zstack-zram' for owner in owners.values()):
                raise RuntimeError('FIRST_ZRAM_RUNTIME_PACKAGE_MISMATCH')
            config_sha = MemoryOptimizationPlugin._verify_first_use_rpm_files(config_bytes)
            with open('/usr/lib/systemd/system/zram-memory.service', 'rb') as stream:
                unit_sha = hashlib.sha256(stream.read()).hexdigest()
            with open('/usr/local/libexec/zram-efficiency', 'rb') as stream:
                binary_sha = hashlib.sha256(stream.read()).hexdigest()
            boot_id = MemoryOptimizationPlugin._current_boot_id()
            if not isinstance(boot_id, STRING_TYPES) or not re.match(
                    r'^[0-9a-f-]{36}\Z', boot_id):
                raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_UNKNOWN')
            return {
                'package': package,
                'unitPath': props['FragmentPath'],
                'unitSha256': unit_sha,
                'binarySha256': binary_sha,
                'pid': int(pid),
                'processStartTime': fields[19],
                'bootId': boot_id,
                'templateSha256': hashlib.sha256(template_bytes).hexdigest(),
                'sourceConfigSha256': config_sha,
            }
        except RuntimeError:
            raise
        except (IOError, OSError, subprocess.CalledProcessError, ValueError, TypeError):
            raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_UNKNOWN')

    @staticmethod
    def _first_use_digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode(
            'utf-8')).hexdigest()

    def _verify_first_use_runtime_for_policy_reconcile(self, prior):
        """Bind the existing read-only policy reconciler to the same runtime."""
        first = prior.get('firstZramUse') if isinstance(prior, dict) else None
        if not isinstance(first, dict) or first.get('policySubmissionStarted') is not True:
            raise RuntimeError('FIRST_ZRAM_POLICY_OUTCOME_UNKNOWN')
        if first.get('bootId') != self._current_boot_id():
            raise RuntimeError('FIRST_ZRAM_RECONCILE_BOOT_CHANGED')
        with open(self.zram_config_path, 'rb') as stream:
            config_bytes = stream.read()
        if hashlib.sha256(config_bytes).hexdigest() != first.get('expectedConfigSha256'):
            raise RuntimeError('FIRST_ZRAM_CONFIG_READBACK_UNKNOWN')
        with open(self.zram_config_template_path, 'rb') as stream:
            template_bytes = stream.read()
        identity = self._first_use_runtime_identity(template_bytes, config_bytes)
        baseline = first.get('activatedIdentity') or first.get('runtimeIdentity')
        if (not isinstance(baseline, dict) or
                identity.get('package') != baseline.get('package') or
                identity.get('unitPath') != baseline.get('unitPath') or
                identity.get('unitSha256') != baseline.get('unitSha256') or
                identity.get('binarySha256') != baseline.get('binarySha256') or
                identity.get('templateSha256') != baseline.get('templateSha256') or
                identity.get('bootId') != first.get('bootId')):
            raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_CHANGED')
        # This is a read-only fence check performed before the ordinary
        # reconciler takes its own operation lock. Do not write the caller's
        # potentially stale `prior` snapshot here: the original apply may
        # have advanced to APPLIED/applyEvidence while this request was in
        # flight. The standard reconciler owns any durable journal updates.
        return True

    def _first_use_prior_fence_clear(self, current_uuid):
        try:
            for name in os.listdir(self.operation_dir):
                if not name.endswith('.json') or name[:-5] == current_uuid:
                    continue
                path = os.path.join(self.operation_dir, name)
                if os.path.islink(path) or not os.path.isfile(path):
                    return False
                with open(path, 'r') as stream:
                    record = json.load(stream)
                if not isinstance(record, dict) or not isinstance(record.get('firstZramUse'), dict):
                    continue
                if record.get('stage') in (self.FIRST_USE_AUTHORIZING_STAGE, 'UNKNOWN'):
                    return False
            return True
        except (IOError, OSError, ValueError, TypeError):
            return False

    def _reconcile_first_zram_use(self, command, prior):
        """Retire only a provably unissued first-use apply; never replay writes."""
        lock = None
        locked_snapshot = None
        reconcile_identity_validated = False
        caller_snapshot_current = False
        try:
            lock = self._acquire_host_control_lock()
            # The caller's `prior` was read before the writer lock. A policy
            # request may have completed while reconcile waited, so all stage
            # and identity decisions must use a fresh journal read under lock.
            latest = self._load_operation(command)
            if not isinstance(latest, dict):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN')
            locked_snapshot = copy.deepcopy(latest)
            caller_snapshot_current = latest == prior
            host_uuid = self._load_host_uuid()
            operation_uuid = command.get('operationUuid')
            original_request_hash = prior.get('requestHash')
            if (not host_uuid or command.get('hostUuid') != host_uuid or
                    not self._valid_identifier(operation_uuid) or
                    prior.get('operationUuid') != operation_uuid or
                    latest.get('operationUuid') != operation_uuid or
                    prior.get('hostUuid') != host_uuid or
                    latest.get('hostUuid') != host_uuid or
                    not isinstance(original_request_hash, STRING_TYPES) or
                    latest.get('requestHash') != original_request_hash):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN')
            first = latest.get('firstZramUse')
            if (not isinstance(first, dict) or first.get('hostUuid') != host_uuid or
                    first.get('requestHash') != original_request_hash):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_IDENTITY_UNKNOWN')
            if (latest.get('bootId') != self._current_boot_id() or
                    first.get('bootId') != self._current_boot_id()):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_BOOT_CHANGED')
            if (latest.get('stage') in ('APPLIED', 'REJECTED', 'NOT_ISSUED') and
                    isinstance(latest.get('readback'), dict)):
                return latest['readback']
            reconcile_identity_validated = True
            # Once the durable marker says the standard policy phase may have
            # begun, do not call it "not issued" or release the operation
            # fence. This reconciler deliberately never replays policy writes.
            if first.get('policySubmissionStarted') is True:
                raise RuntimeError('FIRST_ZRAM_POLICY_OUTCOME_UNKNOWN')
            if first.get('bootId') != self._current_boot_id():
                raise RuntimeError('FIRST_ZRAM_RECONCILE_BOOT_CHANGED')
            with open(self.zram_config_path, 'rb') as stream:
                config_bytes = stream.read()
            if hashlib.sha256(config_bytes).hexdigest() != first.get('expectedConfigSha256'):
                raise RuntimeError('FIRST_ZRAM_CONFIG_READBACK_UNKNOWN')
            with open(self.zram_config_template_path, 'rb') as stream:
                template_bytes = stream.read()
            identity = self._first_use_runtime_identity(template_bytes, config_bytes)
            original_identity = first.get('runtimeIdentity')
            if (not isinstance(original_identity, dict) or
                    identity.get('package') != original_identity.get('package') or
                    identity.get('unitPath') != original_identity.get('unitPath') or
                    identity.get('unitSha256') != original_identity.get('unitSha256') or
                    identity.get('binarySha256') != original_identity.get('binarySha256') or
                    identity.get('templateSha256') != original_identity.get('templateSha256')):
                raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_CHANGED')
            native = self._service_request('state', {})
            cpu = self._service_request('host-cpu-state', {})
            native['host_cpu'] = cpu
            if not self._first_use_state_safe(native, require_reclaim=True):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_STATE_UNKNOWN')
            capacity = self._service_request('capacity-state', {})
            tuning = self._service_request('tuning-state', {})
            baseline = first.get('baseline')
            if not isinstance(baseline, dict):
                raise RuntimeError('FIRST_ZRAM_BASELINE_UNKNOWN')
            unchanged = (
                capacity.get('revision') == baseline.get('capacityRevision') and
                cpu.get('revision') == baseline.get('cpuRevision') and
                cpu.get('efficiency_enabled') is False and
                tuning.get('revision') == baseline.get('tuningRevision') and
                self._get_active_control() == baseline.get('activeControl') and
                ((baseline.get('ksmRequested') is not True) or
                 (isinstance(baseline.get('ksmReadback'), dict) and
                  self._read_ksm_ack() == baseline.get('ksmReadback'))))
            if not unchanged:
                raise RuntimeError('FIRST_ZRAM_POLICY_WRITE_OUTCOME_UNKNOWN')
            result = {'success': False, 'status': 'Failed',
                      'state': {'phase': 'FIRST_USE_CONFIGURED_POLICY_NOT_ISSUED'},
                      'reasonCode': 'FIRST_ZRAM_POLICY_NOT_ISSUED',
                      'operationUuid': command.get('operationUuid'),
                      'firstUse': {'configAuthorized': True,
                                   'controllerRestartVerified': True,
                                   'policyWritesIssued': False},
                      'readback': {'mode': native.get('mode'),
                                   'resourceAuthorized': native.get('resource_authorized'),
                                   'poolGeneration': (native.get('host_zram') or {}).get('pool_generation'),
                                   'bootId': self._current_boot_id()}}
            if not self._update_operation_record(command['operationUuid'], 'REJECTED', result):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_JOURNAL_UNAVAILABLE')
            latest = self._load_operation(command) or {}
            latest['firstZramUse']['reconciledIdentity'] = identity
            if not self._write_operation_record(latest):
                raise RuntimeError('FIRST_ZRAM_RECONCILE_JOURNAL_UNAVAILABLE')
            return result
        except Exception as exc:
            result = {'success': False, 'status': 'Unknown',
                      'state': {'phase': 'UNKNOWN'},
                      'reasonCode': str(exc) if re.match(r'^[A-Z][A-Z0-9_]+$', str(exc))
                      else 'FIRST_ZRAM_RECONCILE_READBACK_UNKNOWN',
                      'operationUuid': command.get('operationUuid')}
            # Lock contention means another writer owns the record. Never
            # mutate a journal unless this reconciler owns the host lock.
            if lock is not None:
                current = self._load_operation(command)
                current_first = (current.get('firstZramUse')
                                 if isinstance(current, dict) else None)
                expected_host = self._load_host_uuid()
                expected_operation = command.get('operationUuid')
                expected_request_hash = prior.get('requestHash')
                if (isinstance(current, dict) and
                        command.get('hostUuid') == expected_host and
                        prior.get('hostUuid') == expected_host and
                        prior.get('operationUuid') == expected_operation and
                        self._valid_identifier(expected_operation) and
                        current.get('operationUuid') == expected_operation and
                        current.get('hostUuid') == expected_host and
                        current.get('bootId') == self._current_boot_id() and
                        current.get('requestHash') == expected_request_hash and
                        isinstance(current_first, dict) and
                        current_first.get('hostUuid') == expected_host and
                        current_first.get('bootId') == self._current_boot_id() and
                        current_first.get('requestHash') == expected_request_hash and
                        current.get('stage') in ('APPLIED', 'REJECTED', 'NOT_ISSUED') and
                        isinstance(current.get('readback'), dict)):
                    return current['readback']
                # If the lock-acquisition reread already differed from the
                # caller snapshot, retain that newer phase/evidence rather
                # than replacing it with a stale Unknown result.
                if (isinstance(locked_snapshot, dict) and isinstance(current, dict) and
                        current != locked_snapshot):
                    return result
                if (caller_snapshot_current and reconcile_identity_validated and
                        isinstance(locked_snapshot, dict) and
                        current == locked_snapshot):
                    self._update_operation_record(command['operationUuid'], 'UNKNOWN', result)
            return result
        finally:
            if lock is not None:
                self._release_operation(lock)

    def _write_first_use_config(self, command, expected_source_sha256):
        """Atomically promote the previously validated vendor config snapshot."""
        config_path = self.zram_config_path
        template_path = self.zram_config_template_path
        if (os.path.islink(config_path) or os.path.islink(template_path) or
                not os.path.isfile(config_path) or not os.path.isfile(template_path)):
            raise RuntimeError('FIRST_ZRAM_CONFIG_READ_UNKNOWN')
        try:
            with open(config_path, 'rb') as stream:
                current = stream.read()
            with open(template_path, 'rb') as stream:
                template = stream.read()
        except (IOError, OSError):
            raise RuntimeError('FIRST_ZRAM_CONFIG_READ_UNKNOWN')
        if (not isinstance(expected_source_sha256, STRING_TYPES) or
                hashlib.sha256(current).hexdigest() != expected_source_sha256):
            # Authorization has already been durably recorded before this
            # compare-and-swap. A concurrent edit now has an ambiguous outcome
            # and must retain the operation fence as Unknown, never REJECTED.
            raise RuntimeError('FIRST_ZRAM_CONFIG_READBACK_MISMATCH')
        try:
            config = json.loads(current.decode('utf-8'))
        except (UnicodeError, ValueError):
            raise RuntimeError('FIRST_ZRAM_TEMPLATE_INVALID')
        if (not isinstance(config, dict) or config.get('managed') is not True or
                config.get('mode') != 'observe' or
                config.get('resource_authorized') is not False or
                config.get('initial_efficiency_enabled') is not False):
            raise RuntimeError('FIRST_ZRAM_TEMPLATE_INVALID')
        config['mode'] = 'reclaim'
        config['resource_authorized'] = True
        payload = json.dumps(config, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        directory = os.path.dirname(config_path)
        fd, temporary = tempfile.mkstemp(prefix='.config-first-use-', dir=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temporary, config_path)
            dirfd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    @staticmethod
    def _bounded_controller_restart(timeout_seconds=30):
        process = subprocess.Popen(['systemctl', 'restart', 'zram-memory.service'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        clock = getattr(time, 'monotonic', time.time)
        deadline = clock() + timeout_seconds
        while process.poll() is None:
            if clock() >= deadline:
                try:
                    process.terminate()
                    stop_deadline = clock() + 3
                    while process.poll() is None and clock() < stop_deadline:
                        time.sleep(0.05)
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                except OSError:
                    logger.warn('unable to reap first-use systemctl restart process')
                raise RuntimeError('FIRST_ZRAM_RESTART_RESULT_UNKNOWN')
            time.sleep(0.1)
        if process.returncode != 0:
            raise RuntimeError('FIRST_ZRAM_RESTART_FAILED')

    def _prepare_first_zram_use(self, command):
        if not self._first_zram_enable_requested(command):
            return False
        if (os.path.islink(self.zram_config_path) or os.path.islink(self.zram_config_template_path) or
                not os.path.isfile(self.zram_config_path) or
                not os.path.isfile(self.zram_config_template_path)):
            raise RuntimeError('FIRST_ZRAM_CONFIG_READ_UNKNOWN')
        try:
            with open(self.zram_config_path, 'rb') as stream:
                current = stream.read()
            with open(self.zram_config_template_path, 'rb') as stream:
                template = stream.read()
        except (IOError, OSError):
            raise RuntimeError('FIRST_ZRAM_CONFIG_READ_UNKNOWN')
        # Already-authorized standard installs continue through the ordinary
        # policy path. Only the exact product template is eligible for this
        # one-time bootstrap; user-maintained config is never overwritten.
        try:
            current_config = json.loads(current.decode('utf-8'))
            template_config = json.loads(template.decode('utf-8'))
        except (UnicodeError, ValueError):
            if hashlib.sha256(current).hexdigest() != hashlib.sha256(template).hexdigest():
                raise FirstZramConfigRejected('FIRST_ZRAM_CONFIG_NOT_FACTORY')
            raise RuntimeError('FIRST_ZRAM_TEMPLATE_INVALID')
        if (isinstance(current_config, dict) and current_config.get('managed') is True and
                current_config.get('mode') == 'reclaim' and
                current_config.get('resource_authorized') is True):
            return False
        if hashlib.sha256(current).hexdigest() != hashlib.sha256(template).hexdigest():
            backend_preparation = self._first_use_backend_preparation_proof(
                current_config, template_config)
        else:
            backend_preparation = None
        if (not isinstance(current_config, dict) or current_config.get('managed') is not True or
                current_config.get('mode') != 'observe' or
                current_config.get('resource_authorized') is not False or
                current_config.get('initial_efficiency_enabled') is not False):
            raise RuntimeError('FIRST_ZRAM_TEMPLATE_INVALID')
        runtime_identity = self._first_use_runtime_identity(template, current)
        if not self._first_use_local_history_clear(
                command, backend_preparation=backend_preparation):
            raise RuntimeError('FIRST_ZRAM_LOCAL_CONTROL_FENCED')
        cpu_before = self._service_request('host-cpu-state', {})
        if cpu_before.get('efficiency_enabled') is not False:
            raise RuntimeError('FIRST_ZRAM_HOST_POLICY_NOT_DISABLED')
        before = self._service_request('state', {})
        before['host_cpu'] = cpu_before
        if not self._first_use_state_safe(before):
            raise RuntimeError('FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE')
        capacity_before = self._service_request('capacity-state', {})
        tuning_before = self._service_request('tuning-state', {})
        if (not isinstance(capacity_before.get('revision'), int) or
                not isinstance(tuning_before.get('revision'), int) or
                not isinstance(cpu_before.get('revision'), int) or
                isinstance(capacity_before.get('revision'), bool) or
                isinstance(tuning_before.get('revision'), bool) or
                isinstance(cpu_before.get('revision'), bool)):
            raise RuntimeError('FIRST_ZRAM_BASELINE_UNKNOWN')
        ksm_requested = bool((command.get('policy') or {}).get('ksm'))
        ksm_before = self._read_ksm_ack() if ksm_requested else None
        if ksm_requested and not isinstance(ksm_before, dict):
            raise RuntimeError('FIRST_ZRAM_KSM_STATE_UNKNOWN')
        target_config = dict(current_config)
        target_config['mode'] = 'reclaim'
        target_config['resource_authorized'] = True
        target_bytes = json.dumps(target_config, sort_keys=True, indent=2).encode('utf-8') + b'\n'
        record = self._load_operation(command)
        if (not isinstance(record, dict) or record.get('stage') != 'PREPARING' or
                record.get('requestHash') != self._operation_hash(command)):
            raise RuntimeError('FIRST_ZRAM_JOURNAL_UNAVAILABLE')
        record['stage'] = self.FIRST_USE_AUTHORIZING_STAGE
        record['firstZramUse'] = {
            'hostUuid': self._load_host_uuid(),
            'bootId': self._current_boot_id(),
            'observedAt': before.get('observed_at'),
            'templateSha256': hashlib.sha256(template).hexdigest(),
            'expectedConfigSha256': hashlib.sha256(target_bytes).hexdigest(),
            'sourceConfigSha256': hashlib.sha256(current).hexdigest(),
            'runtimeIdentity': runtime_identity,
            'baseline': {'capacityRevision': capacity_before['revision'],
                         'cpuRevision': cpu_before.get('revision'),
                         'tuningRevision': tuning_before['revision'],
                         'cpuEnabled': cpu_before.get('efficiency_enabled'),
                         'ksmRequested': ksm_requested,
                         'ksmReadback': ksm_before,
                         'activeControl': self._get_active_control()},
            'requestHash': self._operation_hash(command),
        }
        if backend_preparation is not None:
            record['firstZramUse']['backendPreparation'] = {
                'operationUuid': backend_preparation['operationUuid'],
                'requestHash': backend_preparation['requestHash'],
                'resourceUuid': backend_preparation['resourceUuid'],
            }
        if not self._write_operation_record(record):
            raise RuntimeError('FIRST_ZRAM_JOURNAL_UNAVAILABLE')
        self._write_first_use_config(
            command, record['firstZramUse']['sourceConfigSha256'])
        self._bounded_controller_restart()
        deadline = time.time() + 15
        after = None
        cpu = None
        while time.time() < deadline:
            try:
                candidate = self._service_request('state', {})
                candidate_cpu = self._service_request('host-cpu-state', {})
                candidate['host_cpu'] = candidate_cpu
                if self._first_use_state_safe(candidate, require_reclaim=True):
                    after, cpu = candidate, candidate_cpu
                    break
            except Exception:
                pass
            time.sleep(0.25)
        if after is None:
            raise RuntimeError('FIRST_ZRAM_RESTART_READBACK_UNKNOWN')
        with open(self.zram_config_path, 'rb') as stream:
            applied_config = stream.read()
        if hashlib.sha256(applied_config).hexdigest() != record['firstZramUse']['expectedConfigSha256']:
            raise RuntimeError('FIRST_ZRAM_CONFIG_READBACK_MISMATCH')
        post_identity = self._first_use_runtime_identity(template, applied_config)
        if (post_identity.get('package') != runtime_identity.get('package') or
                post_identity.get('unitPath') != runtime_identity.get('unitPath') or
                post_identity.get('unitSha256') != runtime_identity.get('unitSha256') or
                post_identity.get('binarySha256') != runtime_identity.get('binarySha256') or
                post_identity.get('templateSha256') != runtime_identity.get('templateSha256') or
                (post_identity.get('pid'), post_identity.get('processStartTime')) ==
                (runtime_identity.get('pid'), runtime_identity.get('processStartTime')) or
                post_identity.get('bootId') != self._current_boot_id()):
            raise RuntimeError('FIRST_ZRAM_RUNTIME_IDENTITY_CHANGED')
        record['firstZramUse']['activatedIdentity'] = post_identity
        record['firstZramUse']['postObservedAt'] = after.get('observed_at')
        record['firstZramUse']['postCpuRevision'] = cpu.get('revision')
        if not self._write_operation_record(record):
            raise RuntimeError('FIRST_ZRAM_JOURNAL_UNAVAILABLE')
        return True

    def _mark_first_zram_policy_started(self, command):
        record = self._load_operation(command)
        first = record.get('firstZramUse') if isinstance(record, dict) else None
        if (not isinstance(first, dict) or
                record.get('stage') != self.FIRST_USE_AUTHORIZING_STAGE or
                first.get('requestHash') != self._operation_hash(command) or
                first.get('policySubmissionStarted') is True):
            return False
        first['policySubmissionStarted'] = True
        first['policySubmissionAt'] = int(time.time() * 1000)
        return self._write_operation_record(record)

    def _write_operation_record(self, record):
        try:
            if not os.path.isdir(self.operation_dir):
                os.makedirs(self.operation_dir)
            target = os.path.join(self.operation_dir, '%s.json' % record['operationUuid'])
            fd, temp_path = tempfile.mkstemp(prefix='.operation-', dir=self.operation_dir)
            with os.fdopen(fd, 'w') as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temp_path, target)
            directory_fd = os.open(self.operation_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return True
        except (IOError, OSError, ValueError, TypeError):
            return False

    def _cold_ksm_vm_bindings_valid(self, directory):
        """Validate durable completed VM bindings; reject temp/unknown evidence."""
        try:
            for name in os.listdir(directory):
                if name.startswith('.') or not name.endswith('.json'):
                    return False
                vm_uuid = name[:-5]
                if not self._valid_identifier(vm_uuid):
                    return False
                path = os.path.join(directory, name)
                if os.path.islink(path) or not os.path.isfile(path) or os.path.realpath(path) != path:
                    return False
                with open(path, 'r') as stream:
                    record = json.load(stream)
                if (not isinstance(record, dict) or
                        set(record) != frozenset(('resourceUuid', 'expectedInstanceGeneration',
                                                  'participation', 'operationUuid', 'updatedAt')) or
                        record.get('resourceUuid') != vm_uuid or
                        not self._valid_identifier(record.get('operationUuid')) or
                        record.get('participation') not in ('inherit', 'allow', 'deny', 'auto') or
                        not isinstance(record.get('expectedInstanceGeneration'), STRING_TYPES) or
                        not isinstance(record.get('updatedAt'), INTEGER_TYPES) or
                        isinstance(record.get('updatedAt'), bool) or record.get('updatedAt') < 0):
                    return False
            return True
        except (IOError, OSError, ValueError, TypeError):
            return False

    def _validate_cold_ksm_partial_fence(self, command):
        if not isinstance(command, dict) or command.get('requiresKsmNativePartialFence') is not True:
            return None
        policy = command.get('policy')
        if (command.get('action') != 'apply' or command.get('scope') not in ('Host', 'Cluster', 'Global') or
                not isinstance(policy, dict) or not isinstance(policy.get('ksm'), dict) or
                policy.get('zram') not in (None, {}, {'enabled': False}) or
                policy.get('writeback') not in (None, {}, {'enabled': False})):
            return 'LOCAL_CONTROL_FENCE_UNKNOWN'
        boot_id = command.get('ksmNativeObservationBootId')
        sample_time = command.get('ksmNativeObservationSampleTime')
        now = int(time.time() * 1000)
        if (not isinstance(boot_id, STRING_TYPES) or not boot_id or
                boot_id != self._current_boot_id() or
                not isinstance(sample_time, INTEGER_TYPES) or isinstance(sample_time, bool) or
                sample_time > now + 5000 or now - sample_time < 0 or now - sample_time >= 300000):
            return 'LOCAL_CONTROL_FENCE_UNKNOWN'
        if not self._cold_ksm_local_fence_clear(lock_held=True):
            return 'LOCAL_CONTROL_FENCE_UNKNOWN'
        return None

    def _validate_confirmed_ksm_reconnect(self, command):
        """Under the writer lock, authorize only a proven previous-boot KSM target."""
        if 'confirmedKsmReconnect' not in command:
            return None
        reason = 'KSM_RECONNECT_PROOF_UNQUALIFIED'
        policy = command.get('policy')
        ksm = policy.get('ksm') if isinstance(policy, dict) else None
        operation_uuid = command.get('expectedControlOperationUuid')
        boot_id = self._current_boot_id()
        if (command.get('confirmedKsmReconnect') is not True or
                command.get('action') != 'apply' or command.get('scope') != 'Host' or
                command.get('policyMode') != 'delta' or
                not isinstance(policy, dict) or set(policy) - set(('ksm', 'schemaVersion')) or
                ('schemaVersion' in policy and
                 (type(policy['schemaVersion']) not in INTEGER_TYPES or policy['schemaVersion'] != 1)) or
                not isinstance(ksm, dict) or
                not set(('enabled', 'pagesToScan', 'sleepMillis')).issubset(ksm) or
                not boot_id or command.get('reconnectObservationBootId') != boot_id or
                not self._valid_identifier(operation_uuid) or
                operation_uuid == command.get('operationUuid') or
                os.path.islink(self.active_control_path) or
                os.path.islink(self._operation_path(operation_uuid)) or
                self._get_active_control() != operation_uuid):
            return reason
        file_state, old = self._operation_file_state(operation_uuid)
        if file_state != 'present' or not isinstance(old, dict):
            return reason
        old_policy = old.get('policy')
        old_ksm = old_policy.get('ksm') if isinstance(old_policy, dict) else None
        readback = old.get('readback')
        if (old.get('operationUuid') != operation_uuid or
                old.get('hostUuid') != command.get('hostUuid') or
                old.get('scope') != 'Host' or
                old.get('resourceUuid') not in (None, command.get('hostUuid')) or
                old.get('stage') != 'APPLIED' or old.get('action') not in (None, 'apply') or
                not isinstance(old.get('bootId'), STRING_TYPES) or not old['bootId'] or
                old['bootId'] == boot_id or
                not isinstance(old_ksm, dict) or not old_ksm or
                ('zeroPagesEnabled' in ksm) != ('zeroPagesEnabled' in old_ksm) or
                not self._strict_service_match(ksm, old_ksm) or
                old.get('policyHash') != self._policy_digest(old_policy) or
                not re.match(r'^[0-9a-f]{64}\Z', str(old.get('requestHash', ''))) or
                not isinstance(readback, dict) or readback.get('success') is not True or
                readback.get('status') != 'Succeeded' or
                readback.get('appliedRevision') != old.get('desiredRevision')):
            return reason
        try:
            self._validate_policy({'ksm': old_ksm})
            self._validate_policy({'ksm': ksm})
        except ValueError:
            return reason
        proven = self._ksm_proof_policy(readback.get('ksmReadback'), old.get('desiredRevision'))
        if (proven is None or not self._strict_service_match(proven, ksm) or
                self._has_unresolved_operation_journal()):
            return reason
        return None

    def _load_host_uuid(self):
        # Do not cache: a later /host/connect may refresh the identity.
        # Never infer it from the request or an unrelated on-disk UUID.
        if self.config is not None and kvmagent.HOST_UUID in self.config:
            return self.config[kvmagent.HOST_UUID]
        return self.host_uuid

    def start(self):
        server = kvmagent.get_http_server()
        for path, handler in (
                (self.STATE_PATH, self.state),
                (self.APPLY_PATH, self.apply_request),
                (self.RECONCILE_PATH, self.reconcile),
                (self.MIGRATION_HOLD_PATH, self.migration_hold),
                (self.VM_EFFICIENCY_PATH, self.vm_efficiency),
                (self.ACCOUNTING_PATH, self.accounting),
                (self.WRITEBACK_BACKENDS_PATH, self.writeback_backends)):
            server.register_async_uri(path, handler)

    def stop(self):
        pass

    @staticmethod
    def _request_body(req):
        body = req.get(http.REQUEST_BODY, '{}')
        command = jsonobject.loads(body)
        # jsonobject objects expose attributes, while the local service
        # accepts normal JSON objects.  Serialising and parsing also avoids
        # accidentally forwarding implementation-only attributes.
        return json.loads(jsonobject.dumps(command))

    def _reply(self, payload):
        return jsonobject.dumps(payload)

    @staticmethod
    def _operation_request(command):
        if not isinstance(command, dict):
            raise ValueError('request must be a JSON object')
        for key in ('hostUuid', 'operationUuid'):
            if not MemoryOptimizationPlugin._valid_identifier(command.get(key)):
                raise ValueError('%s is required' % key)
        if str(command.get('scope', '')).lower() == 'vm':
            if not MemoryOptimizationPlugin._valid_identifier(command.get('resourceUuid')):
                raise ValueError('resourceUuid is required for VM scope')
            if not MemoryOptimizationPlugin._valid_identifier(command.get('expectedInstanceGeneration')):
                raise ValueError('expectedInstanceGeneration is required for VM scope')
        return command

    def _readonly_query_request(self, command):
        if not isinstance(command, dict):
            raise ValueError('request must be a JSON object')
        host_uuid = self._load_host_uuid()
        if not host_uuid or command.get('hostUuid') != host_uuid:
            raise ValueError('HOST_IDENTITY_UNKNOWN')
        for key in ('vmUuid', 'operationId', 'status'):
            if key in command and command[key] is not None:
                if not isinstance(command[key], STRING_TYPES) or not command[key]:
                    raise ValueError('invalid %s' % key)
        for key in ('start', 'limit'):
            if key in command and (isinstance(command[key], bool) or
                                   not isinstance(command[key], INTEGER_TYPES) or
                                   command[key] < 0):
                raise ValueError('invalid %s' % key)
        return command

    def _readonly_query(self, action, command):
        self._readonly_query_request(command)
        result = self.service_call(action, command)
        if not isinstance(result, dict):
            raise RuntimeError('INVALID_SERVICE_RESPONSE:%s' % action)
        status = result.get('_http_status')
        if result.get('success') is False or (isinstance(status, int) and status >= 300):
            raise RuntimeError('SERVICE_%s_FAILED:%s' %
                               (action.upper(), result.get('error', 'unknown')))
        result = dict(result)
        result.pop('_http_status', None)
        return result

    def _dispatch(self, action, command):
        command = self._operation_request(command)
        host_uuid = self._load_host_uuid()
        if not host_uuid:
            raise ValueError('HOST_IDENTITY_UNKNOWN')
        if command.get('hostUuid') != host_uuid:
            raise ValueError('hostUuid does not match this Agent')
        lock = None
        try:
            if action == 'migration-hold':
                lock = self._acquire_host_control_lock()
            service_action = action
            if action == 'apply' and str(command.get('scope', '')).lower() == 'vm':
                service_action = 'vm-policy'
            payload = self._service_payload(action, command)
            if service_action == 'apply' and command.get('targetSnapshotGeneration'):
                payload['_target_snapshot_generation'] = command['targetSnapshotGeneration']
            result = self.service_call(service_action, payload)
            normalized = self._normalize_response(result, action, command)
            return normalized
        finally:
            self._release_operation(lock)

    @staticmethod
    def _normalize_response(result, action, command):
        if not isinstance(result, dict):
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reason': 'INVALID_SERVICE_RESPONSE',
                    'operationUuid': command.get('operationUuid')}
        http_status = result.get('_http_status')
        succeeded = (result.get('success') is True or
                     (isinstance(http_status, int) and 200 <= http_status < 300) or
                     str(result.get('status', '')).upper() == 'SUCCEEDED')
        status = result.get('status') or ('Succeeded' if succeeded else 'Unknown')
        body_state = result.get('state')
        state_name = body_state if isinstance(body_state, str) else (
            body_state.get('phase') if isinstance(body_state, dict) else None)
        if isinstance(state_name, str) and state_name.upper() in (
                'DRAINING', 'DRAIN', 'PENDING', 'RECONCILING'):
            status = 'Draining'
            # The operation was accepted but is not complete.  This is a
            # successful lifecycle acknowledgement, not a failed request.
            succeeded = True
        if str(status).upper() in ('DRAIN', 'DRAINING', 'PENDING', 'RECONCILING'):
            status = 'Draining'
            succeeded = True
        if status == 'SUCCEEDED':
            status = 'Succeeded'
        if status == 'FAILED':
            status = 'Failed'
        if status == 'UNKNOWN':
            status = 'Unknown'
        if status in ('DRAIN', 'DRAINING', 'PENDING', 'RECONCILING'):
            status = 'Draining'
        normalized = dict(result)
        normalized['status'] = status
        # zram-service returns LifecycleSnapshot fields at the response
        # top-level (not under ``state``).  Materialize that snapshot as the
        # intermediate state consumed by the lifecycle admission code; the
        # caller below adds the explicit Agent phase only after checking the
        # native paused fact.  Already-normalized state dictionaries remain
        # untouched.
        if (action in ('lifecycle-pause', 'pause', 'resume', 'release') and
                isinstance(result.get('paused'), bool) and
                not isinstance(result.get('state'), dict)):
            normalized['state'] = {
                key: value for key, value in result.items()
                if key not in ('_http_status', 'success', 'status', 'error')
            }
        # A 2xx response with an asynchronous drain is a successfully
        # accepted operation, not a transport failure.  MN uses ``status``
        # to distinguish Draining from Succeeded; keep success true so it can
        # persist/reconcile the same operation instead of retrying it.
        normalized['success'] = succeeded and result.get('success', True) is not False
        normalized.pop('_http_status', None)
        normalized.setdefault('operationUuid', command.get('operationUuid'))
        revision = result.get('revision')
        if revision is None and isinstance(result.get('state'), dict):
            revision = result['state'].get('revision')
        normalized.setdefault('appliedRevision', revision)
        normalized.setdefault('sampleTime', int(time.time() * 1000))
        if status not in ('Succeeded', 'Draining'):
            normalized.setdefault('reason', result.get('error', 'MEMORY_RESULT_UNKNOWN'))
            # Preserve a structured state returned by the service.  Replacing
            # it with a string breaks the AgentResponse state contract.
            if not isinstance(normalized.get('state'), dict):
                normalized['state'] = {'phase': 'UNKNOWN' if status == 'Unknown' else 'FAILED'}
        elif status == 'Draining' and not isinstance(normalized.get('state'), dict):
            normalized['state'] = {'phase': str(normalized.get('state', 'DRAINING'))}
        if status == 'Draining':
            normalized['appliedRevision'] = None
        return normalized

    @staticmethod
    def _service_payload(action, command):
        """Map the platform policy to the service's strict JSON contract.

        KSM is intentionally not sent to zram-service: the distro ksmtuned
        service owns KSM scanning. Silently forwarding nested policy would make a
        successful HTTP response look like KSM had been applied.
        """
        if action in ('state', 'monitor-state', 'preview', 'capacity-state', 'host-cpu-state',
                      'tuning-state', 'vm-policy-state'):
            return command
        if action == 'reconcile':
            return {'operation_id': command['operationUuid']}
        if action == 'backend-maintenance-finalize':
            return {'request_id': command['requestId']}
        if action == 'zram-pool-maintenance-finalize':
            return {'request_id': command['requestId']}
        if action == 'migration-hold':
            return {'action': command.get('holdAction', 'acquire'),
                    'operation_id': command['operationUuid'],
                    'pool_generation': command.get('poolGeneration', '')}
        if action == 'lifecycle-pause':
            return {'action': command.get('lifecycleAction', 'pause')}
        if action == 'lifecycle-activate-maintenance':
            return {'request_id': command['requestId'],
                    'expected_control_operation_uuid': command['expectedControlOperationUuid'],
                    'expected_host_boot_id': command['expectedHostBootId'],
                    'expected_pool_generation': command['expectedPoolGeneration']}
        if action == 'lifecycle-activation-state':
            return {'request_id': command['requestId']}
        if action == 'lifecycle-activation-retirement':
            return command
        if action == 'lifecycle-activation-retirement-state':
            return command
        if action == 'drain-start':
            return {'request_id': command['operationUuid'],
                    'resource_id': command['resource_id'],
                    'expected_epoch': command['expected_epoch']}
        if action in ('drain-status',):
            return command
        if action == 'capacity':
            zram = (command.get('policy') or {}).get('zram') or {}
            return {'request_id': command['operationUuid'],
                    'expected_revision': command.get('capacityExpectedRevision', command.get('expectedRevision', 0)),
                    'logical_capacity': MemoryOptimizationPlugin._native_capacity_value(zram.get('logicalCapacityBytes')),
                    'physical_memory_limit': MemoryOptimizationPlugin._native_capacity_value(zram.get('ramLimitBytes'))}
        if action == 'host-cpu':
            zram = (command.get('policy') or {}).get('zram') or {}
            wb = (command.get('policy') or {}).get('writeback') or {}
            native = command.get('nativeCpuState') or {}
            return {'request_id': command['operationUuid'],
                    'expected_revision': command.get('cpuExpectedRevision', command.get('expectedRevision', 0)),
                    'efficiency_enabled': bool(zram.get('enabled', native.get('efficiency_enabled', False)) or wb.get(
                        'enabled', (command.get('nativeSettings') or {}).get('writeback', {}).get('enabled', False))),
                    'idle_cpu_threshold_percent': zram.get('cpuThresholdPercent', native.get('idle_cpu_threshold_percent', 5)),
                    'idle_duration_seconds': zram.get('cpuHoldSeconds', native.get('idle_duration_seconds', 60))}
        policy = command.get('policy') or {}
        if str(command.get('scope', '')).lower() == 'vm':
            participation = (policy.get('participation') or
                             command.get('participation', 'inherit'))
            # Platform's inherit means service auto; the service has no
            # literal "inherit" mode.
            # A platform VM policy must not manufacture a short-lived grant,
            # so both inherit and allow use the durable auto rule;
            # deny remains the only explicit exclusion.
            mode = 'auto' if participation in ('inherit', 'allow') else participation
            payload = {'request_id': command['operationUuid'],
                       'expected_revision': command.get('expectedRevision', 0),
                    # The Go API calls this expected_instance_generation.
                    # The platform-facing field is mapped here only; it is
                    # never silently dropped.
                       'expected_instance_generation': command['expectedInstanceGeneration'],
                       'mode': mode,
                       # null is the service's explicit "use internal rule"
                       # form; an empty object would fail COMPLETE_CPU_RULE.
                    'cpu_rule': command.get('cpuRule')}
            payload['_resource_uuid'] = command['resourceUuid']
            return payload
        zram = policy.get('zram') or {}
        if zram.get('selectionMode') not in (None, 'all_running', 'list'):
            raise ValueError('invalid ZRAM selectionMode')
        if 'selectedVmUuids' in zram and not isinstance(zram['selectedVmUuids'], list):
            raise ValueError('invalid ZRAM selectedVmUuids')
        for key in ('hostCpuThresholdPercent', 'hostMemoryPsiThresholdPercent', 'hostIoPsiThresholdPercent'):
            if key in zram and (not isinstance(zram[key], (int, float)) or zram[key] < 0 or zram[key] > 100):
                raise ValueError('invalid ZRAM %s' % key)
        for key in ('discoveryIntervalSeconds', 'discoveryTimeoutSeconds', 'discoveryTtlSeconds',
                    'hostSampleIntervalSeconds', 'hostSampleTtlSeconds', 'vmSampleIntervalSeconds',
                    'vmSampleTtlSeconds', 'reclaimBatchBytes', 'concurrency',
                    'reclaimSlowOperationSeconds', 'timeoutIsolationSlots',
                    'operationRecordBudgetBytes', 'startupObservationSeconds'):
            minimum = 0 if key in ('startupObservationSeconds', 'timeoutIsolationSlots') else 1
            if key in zram and (isinstance(zram[key], bool) or not isinstance(zram[key], INTEGER_TYPES) or zram[key] < minimum):
                raise ValueError('invalid ZRAM %s' % key)
        wb = policy.get('writeback') or {}
        settings = {
            'vm_management': {
                'mode': zram.get('selectionMode', 'all_running'),
                'vm_uuids': zram.get('selectedVmUuids', []),
            },
            'discovery_interval_seconds': zram.get('discoveryIntervalSeconds', 60),
            'discovery_timeout_seconds': zram.get('discoveryTimeoutSeconds', 30),
            'discovery_ttl_seconds': zram.get('discoveryTtlSeconds', 120),
            'host_sample_interval_seconds': zram.get('hostSampleIntervalSeconds', 2),
            'host_sample_ttl_seconds': zram.get('hostSampleTtlSeconds', 3),
            'vm_sample_interval_seconds': zram.get('vmSampleIntervalSeconds', 2),
            'vm_sample_ttl_seconds': zram.get('vmSampleTtlSeconds', 6),
            'host_cpu_guard_enabled': zram.get('hostCpuGuardEnabled', True),
            'host_memory_psi_guard_enabled': zram.get('hostMemoryPsiGuardEnabled', True),
            'host_io_psi_guard_enabled': zram.get('hostIoPsiGuardEnabled', True),
            'host_cpu_threshold_percent': zram.get('hostCpuThresholdPercent', 50),
            'host_memory_psi_threshold_percent': zram.get('hostMemoryPsiThresholdPercent', 0.1),
            'host_io_psi_threshold_percent': zram.get('hostIoPsiThresholdPercent', 1),
            'reclaim_batch_bytes': zram.get('reclaimBatchBytes', 64 * 1024 * 1024),
            'reclaim_concurrency': zram.get('concurrency', 1),
            'reclaim_slow_operation_seconds': zram.get('reclaimSlowOperationSeconds', 60),
            'timeout_isolation_slots': zram.get('timeoutIsolationSlots', 10),
            'operation_record_budget_bytes': zram.get('operationRecordBudgetBytes', 1 * 1024 * 1024 * 1024),
            'startup_observation_seconds': zram.get('startupObservationSeconds', 60),
            'algorithm': zram.get('algorithm', 'lzo'),
            'required_available_bytes': zram.get('requiredAvailableBytes'),
            'host_floor_bytes': zram.get('hostFloorBytes', 0),
            'metadata_reserve_bytes': zram.get('metadataReserveBytes', 0),
            'transient_reserve_bytes': zram.get('transientReserveBytes', 0),
            'reclaim_operation_interval_seconds': zram.get('operationIntervalSeconds', 2),
            'writeback': {
                'enabled': wb.get('enabled', False),
                'batch_bytes': wb.get('batchBytes', 64 * 1024 * 1024),
                'idle_observation_seconds': wb.get('idleObservationSeconds', 10),
                'operation_interval_seconds': wb.get('operationIntervalSeconds', 2),
                'slow_operation_seconds': wb.get('slowOperationSeconds', 60),
                'no_progress_limit': wb.get('noProgressLimit', 3),
                'backoff_seconds': wb.get('backoffSeconds', 60),
                'io_error_backoff_seconds': wb.get('ioErrorBackoffSeconds', 60),
                'metadata_budget_bytes': wb.get('metadataBudgetBytes', 1 * 1024 * 1024 * 1024),
                'filesystem_reserve_bytes': wb.get('filesystemReserveBytes', 16 * 1024 * 1024 * 1024),
            },
        }
        # _apply_service_policy replaces this with the complete native
        # settings readback before every update.  Keeping this fallback makes
        # the mapper explicit for callers that use it directly, but policy
        # application never relies on these defaults.
        if isinstance(command.get('nativeSettings'), dict):
            settings = command['nativeSettings']
        payload = {'request_id': command['operationUuid'],
                   'expected_revision': command.get('expectedRevision', 0),
                   'settings': settings}
        # KSM fields are consumed by _apply_ksm_policy, never this payload.
        return payload

    def _apply_service_policy(self, command, receipt_sink=None):
        """Apply each service-owned section through its strict local ABI."""
        request_policy = command.get('policy') or {}
        request_zram = request_policy.get('zram') or {}
        request_writeback = request_policy.get('writeback') or {}
        # Every host service-policy change must quiesce an already active
        # reclaim gate before capacity or VM-scope mutation.  This includes
        # explicit disable requests and maintenance activation; the same
        # ordering is required even when a request only changes tuning.
        if (receipt_sink is None and
                (bool(request_zram) or bool(request_writeback))):
            return self._apply_service_policy_fail_closed(command)
        policy = command.get('policy') or {}
        zram = policy.get('zram') or {}
        wb = policy.get('writeback') or {}
        readback = {}
        read_state = (self._strict_service_revision if receipt_sink is not None
                      else self._read_service_revision)

        def write_service(action, payload, key):
            if receipt_sink is None:
                return self._service_request(action, payload)
            attempts = receipt_sink.setdefault('writeAttempts', {})
            attempts[key] = 'ATTEMPTED'
            try:
                result = self._service_request(
                    action, payload,
                    receipt_sink=lambda value: receipt_sink.setdefault('writes', {}).__setitem__(
                        key, value))
            except Exception as exc:
                attempts[key] = 'RESULT_UNKNOWN'
                receipt_sink.setdefault('writeErrors', {})[key] = str(exc)[:256]
                raise
            if self._is_async_service_result(result):
                attempts[key] = 'RESULT_UNKNOWN'
                receipt_sink.setdefault('writeErrors', {})[key] = 'ASYNC_SERVICE_RESULT'
            else:
                attempts[key] = 'ACKNOWLEDGED'
            return result

        tuning_command = dict(command)
        tuning_command['operationUuid'] = '%s-tuning' % command['operationUuid']
        tuning_state = read_state('tuning-state')
        tuning_command['expectedRevision'] = tuning_state['revision']
        self._merge_tuning_settings(tuning_command, tuning_state)
        if 'logicalCapacityBytes' in zram or 'ramLimitBytes' in zram:
            cap_command = dict(command)
            cap_command['operationUuid'] = '%s-capacity' % command['operationUuid']
            cap_command['capacityExpectedRevision'] = read_state('capacity-state')['revision']
            readback['capacity'] = write_service('capacity', cap_command, 'capacity')
            self._adopt_default_capacity(zram, readback['capacity'])
        if (any(key in zram for key in ('enabled', 'cpuThresholdPercent', 'cpuHoldSeconds')) or
                'enabled' in wb):
            cpu_command = dict(command)
            cpu_command['operationUuid'] = '%s-cpu' % command['operationUuid']
            native_cpu = read_state('host-cpu-state')
            required = ('efficiency_enabled', 'idle_cpu_threshold_percent', 'idle_duration_seconds')
            if any(key not in native_cpu for key in required):
                raise RuntimeError('SERVICE_CPU_SETTINGS_UNKNOWN')
            cpu_command['cpuExpectedRevision'] = native_cpu['revision']
            cpu_command['nativeCpuState'] = native_cpu
            cpu_command['nativeSettings'] = tuning_command['nativeSettings']
            readback['cpu'] = write_service('host-cpu', cpu_command, 'host-cpu')
        readback['tuning'] = write_service('apply', tuning_command, 'apply')
        # A 202/Draining response means the local service accepted work but
        # has not proved the requested configuration.  Do not turn it into a
        # successful product revision; apply() will journal it for reconcile.
        async_sections = [key for key, item in readback.items()
                          if self._is_async_service_result(item)]
        if async_sections:
            return {'status': 'Draining', 'state': readback,
                    'asyncSections': async_sections}
        return {'status': 'Succeeded', 'state': readback}

    @staticmethod
    def _derived_service_request_id(operation_uuid, suffix):
        candidate = '%s-%s' % (operation_uuid, suffix)
        if len(candidate) <= 128:
            return candidate
        digest = hashlib.sha256(candidate.encode('utf-8')).hexdigest()
        return 'memopt-%s' % digest

    def _apply_service_policy_fail_closed(self, command):
        """Commit the VM scope and tuning before allowing host reclaim.

        apply() holds the per-Host control flock for this entire method.  If a
        prior policy is active, turn its CPU gate off before any capacity or
        VM-management mutation.  Stage/commit/tuning failures therefore leave
        dispatch disabled; only a complete tuning readback permits the final
        CPU gate write.
        """
        policy = command.get('policy') or {}
        zram = policy.get('zram') or {}
        wb = policy.get('writeback') or {}
        sections = {}
        sequence = []
        async_sections = []
        last_step = 'preflight'
        capacity_requested = ('logicalCapacityBytes' in zram or 'ramLimitBytes' in zram)
        cpu_policy_requested = (any(key in zram for key in (
            'enabled', 'cpuThresholdPercent', 'cpuHoldSeconds')) or 'enabled' in wb)
        try:
            # Read every revision before mutation.  These reads are strict and
            # the later writes remain compare-and-swap fenced.
            capacity_before = None
            if capacity_requested:
                capacity_before = self._strict_service_success(
                    'capacity-state', self._service_request('capacity-state', {}))
            cpu_before = self._strict_service_success(
                'host-cpu-state', self._service_request('host-cpu-state', {}))
            tuning_before = self._strict_service_success(
                'tuning-state', self._service_request('tuning-state', {}))
            native_cpu = dict(cpu_before)
            sections['cpuBefore'] = dict(cpu_before)

            # A configuration update may widen the VM set.  Quiesce existing
            # dispatch before the capacity write and before stage/commit.
            guard_receipt = None
            guard_id = self._derived_service_request_id(
                command['operationUuid'], 'cpu-hold')
            if cpu_before.get('efficiency_enabled') is True:
                last_step = 'cpu_guard_write'
                guard_command = dict(command)
                guard_policy = dict(policy)
                guard_zram = dict(zram)
                guard_zram['enabled'] = False
                guard_wb = dict(wb)
                guard_wb['enabled'] = False
                guard_policy['zram'] = guard_zram
                guard_policy['writeback'] = guard_wb
                guard_command.update({
                    'operationUuid': guard_id,
                    'expectedRevision': cpu_before['revision'],
                    'cpuExpectedRevision': cpu_before['revision'],
                    'nativeCpuState': native_cpu,
                    'policy': guard_policy,
                })
                guard_receipt = self._service_request('host-cpu', guard_command)
                sections['cpuGuard'] = guard_receipt
                sequence.append('cpu_guard_written')
                self._strict_service_success('host-cpu', guard_receipt)
                if guard_receipt.get('request_id') != guard_id:
                    raise RuntimeError('SERVICE_CPU_GUARD_RECEIPT_MISMATCH')
                last_step = 'cpu_guard_readback'
                cpu_guard_state = self._strict_service_success(
                    'host-cpu-state', self._service_request('host-cpu-state', {}))
                if (cpu_guard_state.get('efficiency_enabled') is not False or
                        cpu_guard_state.get('revision') != guard_receipt.get('revision')):
                    raise RuntimeError('SERVICE_CPU_GUARD_NOT_VERIFIED')
                native_cpu = dict(cpu_guard_state)
                sections['cpuGuardReadback'] = cpu_guard_state
                sequence.append('cpu_guard_verified_off')
                if capacity_requested:
                    # Capacity and CPU-policy revisions are shared by the
                    # service.  The guard write advances that revision, so
                    # refresh the capacity CAS token after quiescing rather
                    # than submitting the stale preflight revision.
                    capacity_before = self._strict_service_success(
                        'capacity-state', self._service_request('capacity-state', {}))

            if capacity_requested:
                last_step = 'capacity_write'
                capacity_command = dict(command)
                capacity_command['operationUuid'] = self._derived_service_request_id(
                    command['operationUuid'], 'capacity')
                capacity_command['capacityExpectedRevision'] = capacity_before['revision']
                capacity_receipt = self._service_request('capacity', capacity_command)
                if isinstance(capacity_receipt, dict):
                    # The capacity endpoint currently returns CapacityStatus
                    # without echoing request_id. Keep an explicit local
                    # binding to the exact request/revision that produced this
                    # response; never infer it later from matching values.
                    capacity_receipt = dict(capacity_receipt)
                    capacity_receipt['agent_request_id'] = capacity_command['operationUuid']
                    capacity_receipt['agent_expected_revision'] = capacity_before['revision']
                sections['capacity'] = capacity_receipt
                sequence.append('capacity_written')
                self._adopt_default_capacity(zram, capacity_receipt)
                if self._is_async_service_result(capacity_receipt):
                    async_sections.append('capacity')

            tuning_command = dict(command)
            tuning_command['operationUuid'] = self._derived_service_request_id(
                command['operationUuid'], 'tuning')
            tuning_command['expectedRevision'] = tuning_before['revision']
            self._merge_tuning_settings(tuning_command, tuning_before)
            last_step = 'tuning_apply_and_vm_scope_commit'
            tuning_payload = self._service_payload('apply', tuning_command)
            try:
                transport = command.get('communication') or {}
            except AttributeError:
                transport = {}
            if not isinstance(transport, dict):
                raise ValueError('invalid per-request communication budget')
            communication_seconds = transport.get(
                'communicationSeconds', self.communication_seconds)
            if (isinstance(communication_seconds, bool) or
                    not isinstance(communication_seconds, (int, float)) or
                    communication_seconds <= 0):
                raise ValueError('invalid per-request communication budget')
            deadline = linux.monotime() + communication_seconds
            while True:
                remaining = deadline - linux.monotime()
                if remaining <= 0:
                    raise RuntimeError('SERVICE_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                attempt_receipts = []
                try:
                    attempt_transport = dict(transport)
                    attempt_transport['communicationSeconds'] = remaining
                    tuning_receipt = self._service_request(
                        'apply', tuning_command, receipt_sink=attempt_receipts.append,
                        communication=attempt_transport)
                    break
                except Exception:
                    rejection = attempt_receipts[-1] if attempt_receipts else None
                    if (not isinstance(rejection, dict) or
                            type(rejection.get('_http_status')) is not int or
                            rejection.get('_http_status') != 409 or
                            rejection.get('error') != 'TUNING_REQUIRES_QUIESCENT_EXECUTOR' or
                            ('success' in rejection and rejection.get('success') is not False)):
                        raise
                    vm_management = tuning_payload.get('settings', {}).get('vm_management', {})
                    vm_uuids = vm_management.get('vm_uuids') if isinstance(vm_management, dict) else None
                    if isinstance(vm_uuids, list) and vm_uuids:
                        # The local apply transport stages/commits VM shards
                        # before the tuning PUT.  A retry could replay that
                        # side effect, so leave this operation Unknown unless
                        # the shard protocol has its own completed proof.
                        raise
                    # The typed 409 proves this exact PUT did not write.  Wait
                    # for the existing executor queues to drain, but retain the
                    # Go PUT as the authoritative quiet/CAS gate.  Unknown query
                    # results cannot authorize another write.
                    while True:
                        remaining = deadline - linux.monotime()
                        if remaining <= 0:
                            raise RuntimeError(
                                'SERVICE_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                        attempt_transport = dict(transport)
                        attempt_transport['communicationSeconds'] = remaining
                        operations = self._readonly_query('operations', {
                            'hostUuid': command['hostUuid'], 'limit': 1,
                            'communication': attempt_transport})
                        cq = operations.get('cq')
                        if (not isinstance(cq, dict) or
                                type(cq.get('C')) is not int or
                                type(cq.get('Q')) is not int):
                            raise RuntimeError('SERVICE_TUNING_QUEUE_STATE_UNKNOWN')
                        remaining = deadline - linux.monotime()
                        if remaining <= 0:
                            raise RuntimeError(
                                'SERVICE_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                        attempt_transport = dict(transport)
                        attempt_transport['communicationSeconds'] = remaining
                        monitor = self._service_request('monitor-state', {
                            }, communication=attempt_transport)
                        if ('pending_operations' not in monitor or
                                monitor.get('pending_operations') not in (None, []) and
                                not isinstance(monitor.get('pending_operations'), list)):
                            raise RuntimeError('SERVICE_TUNING_PENDING_STATE_UNKNOWN')
                        pending = monitor.get('pending_operations') not in (None, [])
                        if cq['C'] == 0 and cq['Q'] == 0 and not pending:
                            remaining = deadline - linux.monotime()
                            if remaining <= 0:
                                raise RuntimeError(
                                    'SERVICE_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                            time.sleep(min(0.1, remaining))
                            break
                        remaining = deadline - linux.monotime()
                        if remaining <= 0:
                            raise RuntimeError(
                                'SERVICE_TUNING_QUIESCENCE_DEADLINE_EXCEEDED')
                        time.sleep(min(0.1, remaining))
            if isinstance(tuning_receipt, dict):
                tuning_receipt = dict(tuning_receipt)
                # This synchronous endpoint does not echo request_id. Persist
                # the exact request binding locally instead of treating a
                # matching revision/settings as proof of ownership.
                tuning_receipt['agent_request_id'] = tuning_command['operationUuid']
            sections['tuning'] = tuning_receipt
            sequence.append('tuning_apply_returned')
            if self._is_async_service_result(tuning_receipt):
                async_sections.append('tuning')
                return {'success': True, 'status': 'Draining',
                        'state': {'phase': 'DRAINING', 'sequence': sequence,
                                  'lastStep': last_step, 'sections': sections,
                                  'notAttempted': ['finalCpuGate']},
                        'asyncSections': async_sections}

            # The tuning endpoint is called only after the VM shard protocol
            # returns.  Confirm its complete readback (including the target
            # VM mode/list) before a host gate may be enabled again.
            last_step = 'tuning_target_readback'
            target_readback = self._read_policy_state(command, policy)
            observed_sections = target_readback.get('sections', {})
            sections['tuningReadback'] = observed_sections.get('tuning')
            if capacity_requested:
                sections['capacityReadback'] = observed_sections.get('capacity')
            if target_readback.get('sectionComplete', {}).get('tuning') is not True:
                raise RuntimeError('SERVICE_TUNING_TARGET_NOT_VERIFIED')
            self._strict_service_success('tuning-state', sections['tuningReadback'])
            if capacity_requested:
                capacity_receipt = sections.get('capacity')
                capacity_readback = sections.get('capacityReadback')
                if (not isinstance(capacity_receipt, dict) or
                        capacity_receipt.get('_http_status') not in (200, 202) or
                        not self._revision(capacity_receipt.get('revision')) or
                        not isinstance(capacity_readback, dict) or
                        capacity_readback.get('_http_status') != 200 or
                        capacity_readback.get('revision') != capacity_receipt.get('revision') or
                        not self._capacity_desired_matches(capacity_receipt, zram) or
                        not self._capacity_desired_matches(capacity_readback, zram)):
                    raise RuntimeError('SERVICE_CAPACITY_TARGET_NOT_VERIFIED')
            sections['cpuReadback'] = observed_sections.get('cpu')
            cpu_readback = self._strict_service_success(
                'host-cpu-state', sections['cpuReadback'])
            if not isinstance(cpu_readback, dict) or not self._revision(cpu_readback.get('revision')):
                raise RuntimeError('SERVICE_CPU_STATE_UNKNOWN')
            native_cpu = cpu_readback
            sequence.append('tuning_target_verified')

            if 'capacity' in async_sections:
                capacity_receipt = sections.get('capacity')
                capacity_readback = sections.get('capacityReadback')
                if (not isinstance(capacity_receipt, dict) or
                        not isinstance(capacity_readback, dict) or
                        not self._revision(capacity_receipt.get('revision')) or
                        capacity_readback.get('revision') != capacity_receipt.get('revision') or
                        native_cpu.get('revision') != capacity_receipt.get('revision')):
                    raise RuntimeError('SERVICE_CAPACITY_CPU_REVISION_CONFLICT')

            desired_cpu_enabled = bool(
                zram.get('enabled', cpu_before.get('efficiency_enabled', False)) or
                tuning_command['nativeSettings'].get('writeback', {}).get('enabled', False))
            desired_cpu_threshold = zram.get(
                'cpuThresholdPercent', native_cpu.get('idle_cpu_threshold_percent'))
            desired_cpu_duration = zram.get(
                'cpuHoldSeconds', native_cpu.get('idle_duration_seconds'))
            if cpu_policy_requested or guard_receipt is not None:
                last_step = 'cpu_target_write'
                cpu_id = self._derived_service_request_id(
                    command['operationUuid'], 'cpu')
                cpu_command = dict(command)
                cpu_policy = dict(policy)
                cpu_zram = dict(zram)
                cpu_zram['enabled'] = desired_cpu_enabled
                cpu_policy['zram'] = cpu_zram
                cpu_command['policy'] = cpu_policy
                cpu_command.update({'operationUuid': cpu_id,
                                    'cpuExpectedRevision': native_cpu['revision'],
                                    'nativeCpuState': native_cpu})
                cpu_receipt = self._service_request('host-cpu', cpu_command)
                if isinstance(cpu_receipt, dict):
                    cpu_receipt = dict(cpu_receipt)
                    # Persist the exact CAS token used for this operation's
                    # final Host CPU write. A matching final revision alone
                    # cannot rule out an unrelated writer between the
                    # capacity readback and this PUT.
                    cpu_receipt['agent_expected_revision'] = native_cpu['revision']
                    cpu_receipt['agent_desired_enabled'] = desired_cpu_enabled
                    cpu_receipt['agent_desired_threshold_percent'] = desired_cpu_threshold
                    cpu_receipt['agent_desired_duration_seconds'] = desired_cpu_duration
                sections['cpu'] = cpu_receipt
                self._strict_service_success('host-cpu', cpu_receipt)
                if cpu_receipt.get('request_id') != cpu_id:
                    raise RuntimeError('SERVICE_CPU_RECEIPT_MISMATCH')
                if cpu_receipt.get('efficiency_enabled') is not desired_cpu_enabled:
                    raise RuntimeError('SERVICE_CPU_TARGET_RECEIPT_MISMATCH')
                last_step = 'cpu_target_readback'
                cpu_final = self._strict_service_success(
                    'host-cpu-state', self._service_request('host-cpu-state', {}))
                if (cpu_final.get('efficiency_enabled') is not desired_cpu_enabled or
                        cpu_final.get('revision') != cpu_receipt.get('revision')):
                    raise RuntimeError('SERVICE_CPU_TARGET_NOT_VERIFIED')
                sections['cpuReadback'] = cpu_final
                sequence.append('cpu_target_verified')

            final_cpu_readback = sections.get('cpuReadback', native_cpu)
            cpu_complete = (isinstance(final_cpu_readback, dict) and
                            final_cpu_readback.get('efficiency_enabled') is desired_cpu_enabled and
                            final_cpu_readback.get('idle_cpu_threshold_percent') == desired_cpu_threshold and
                            final_cpu_readback.get('idle_duration_seconds') == desired_cpu_duration)
            state = {'phase': 'READBACK', 'sequence': sequence,
                     'sections': sections,
                     'sectionComplete': {
                         'tuning': True,
                         'cpu': cpu_complete,
                     }}
            if async_sections:
                state['sectionComplete']['capacity'] = False
                state['phase'] = 'BLOCKED'
                return {'success': True, 'status': 'Draining', 'state': state,
                        'asyncSections': async_sections}
            return {'success': True, 'status': 'Succeeded', 'state': state}
        except Exception as exc:
            reason = str(exc)
            reason_code = (reason if re.match(r'^[A-Z][A-Z0-9_]+$', reason)
                           else 'MEMORY_RESULT_UNKNOWN')
            return {'success': False, 'status': 'Unknown',
                    'reason': reason, 'reasonCode': reason_code,
                    'state': {'phase': 'UNKNOWN', 'lastStep': last_step,
                              'sequence': sequence, 'sections': sections,
                              'notAttempted': ['remainingPolicyWrites', 'finalCpuGate']},
                    'operationUuid': command.get('operationUuid')}

    def _read_service_revision(self, action, command=None):
        """Read a native section before its compare-and-swap update."""
        result = self._service_request(action, command or {})
        revision = result.get('revision')
        if not isinstance(revision, int) or revision < 0:
            raise RuntimeError('SERVICE_%s_REVISION_UNKNOWN' % action.upper())
        return result

    @staticmethod
    def _merge_tuning_settings(command, state):
        """Read full native settings, then overlay explicit product fields.

        In the native ABI zero is a real value, not an inheritance marker;
        sending Agent-side defaults would therefore overwrite service policy.
        """
        native = state.get('settings')
        if not isinstance(native, dict):
            raise RuntimeError('SERVICE_TUNING_SETTINGS_UNKNOWN')
        settings = dict(native)
        wb_settings = dict(native.get('writeback') or {})
        policy = command.get('policy') or {}
        zram = policy.get('zram') or {}
        wb = policy.get('writeback') or {}
        for product_key, native_key in (
                ('requiredAvailableBytes', 'required_available_bytes'),
                ('hostFloorBytes', 'host_floor_bytes'),
                ('metadataReserveBytes', 'metadata_reserve_bytes'),
                ('transientReserveBytes', 'transient_reserve_bytes')):
            if product_key in zram:
                settings[native_key] = zram[product_key]
        for product_key, native_key in (
                ('selectionMode', 'vm_management.mode'),
                ('selectedVmUuids', 'vm_management.vm_uuids'),
                ('discoveryIntervalSeconds', 'discovery_interval_seconds'),
                ('discoveryTimeoutSeconds', 'discovery_timeout_seconds'),
                ('discoveryTtlSeconds', 'discovery_ttl_seconds'),
                ('hostSampleIntervalSeconds', 'host_sample_interval_seconds'),
                ('hostSampleTtlSeconds', 'host_sample_ttl_seconds'),
                ('vmSampleIntervalSeconds', 'vm_sample_interval_seconds'),
                ('vmSampleTtlSeconds', 'vm_sample_ttl_seconds'),
                ('hostCpuGuardEnabled', 'host_cpu_guard_enabled'),
                ('hostMemoryPsiGuardEnabled', 'host_memory_psi_guard_enabled'),
                ('hostIoPsiGuardEnabled', 'host_io_psi_guard_enabled'),
                ('hostCpuThresholdPercent', 'host_cpu_threshold_percent'),
                ('hostMemoryPsiThresholdPercent', 'host_memory_psi_threshold_percent'),
                ('hostIoPsiThresholdPercent', 'host_io_psi_threshold_percent'),
                ('reclaimBatchBytes', 'reclaim_batch_bytes'),
                ('concurrency', 'reclaim_concurrency'),
                ('reclaimSlowOperationSeconds', 'reclaim_slow_operation_seconds'),
                ('timeoutIsolationSlots', 'timeout_isolation_slots'),
                ('operationRecordBudgetBytes', 'operation_record_budget_bytes'),
                ('startupObservationSeconds', 'startup_observation_seconds'),
                ('algorithm', 'algorithm')):
            if product_key in zram:
                if '.' in native_key:
                    section, key = native_key.split('.', 1)
                    nested = dict(settings.get(section) or {})
                    nested[key] = zram[product_key]
                    settings[section] = nested
                else:
                    settings[native_key] = zram[product_key]
                    # Older service snapshots may expose both spellings.
                    # Keep aliases equal when the product explicitly changes
                    # concurrency; Go rejects conflicting alias values.
                    if product_key == 'concurrency' and 'concurrency' in settings:
                        settings['concurrency'] = zram[product_key]
        if 'operationIntervalSeconds' in zram:
            settings['reclaim_operation_interval_seconds'] = zram['operationIntervalSeconds']
        for product_key, native_key in (
                ('enabled', 'enabled'),
                ('batchBytes', 'batch_bytes'),
                ('idleObservationSeconds', 'idle_observation_seconds'),
                ('operationIntervalSeconds', 'operation_interval_seconds')):
            if product_key in wb:
                wb_settings[native_key] = wb[product_key]
        for product_key, native_key in (
                ('slowOperationSeconds', 'slow_operation_seconds'),
                ('noProgressLimit', 'no_progress_limit'),
                ('backoffSeconds', 'backoff_seconds'),
                ('ioErrorBackoffSeconds', 'io_error_backoff_seconds'),
                ('metadataBudgetBytes', 'metadata_budget_bytes'),
                ('filesystemReserveBytes', 'filesystem_reserve_bytes')):
            if product_key in wb:
                wb_settings[native_key] = wb[product_key]
        settings['writeback'] = wb_settings
        command['nativeSettings'] = settings

    @staticmethod
    def _is_async_service_result(result):
        if not isinstance(result, dict):
            return False
        if result.get('_http_status') == 202:
            return True
        status = str(result.get('status', '')).upper()
        state = result.get('state')
        phase = state.get('phase') if isinstance(state, dict) else state
        return status in ('DRAINING', 'PENDING', 'RECONCILING') or \
            str(phase or '').upper() in ('DRAINING', 'PENDING', 'RECONCILING')

    def _service_request(self, action, command, receipt_sink=None, communication=None):
        payload = self._service_payload(action, command)
        if communication is not None:
            if not isinstance(communication, dict):
                raise ValueError('invalid per-request communication budget')
            payload['communication'] = dict(communication)
        if action == 'apply' and command.get('targetSnapshotGeneration'):
            payload['_target_snapshot_generation'] = command['targetSnapshotGeneration']
        result = self.service_call(action, payload)
        if receipt_sink is not None:
            receipt_sink(result)
        if not isinstance(result, dict):
            raise RuntimeError('INVALID_SERVICE_RESPONSE:%s' % action)
        code = result.get('_http_status')
        if result.get('success') is False or (isinstance(code, int) and code >= 300):
            # The activation status API uses a precise 404 to report that no
            # receipt exists yet. Preserve only this typed absence for the
            # caller's explicit receipt-absence check; all other HTTP failures
            # remain errors and therefore cannot authorize recovery.
            if (action == 'lifecycle-activation-state' and code == 404 and
                    result.get('error') == 'MAINTENANCE_ACTIVATION_NOT_FOUND' and
                    result.get('receipt') is None):
                return result
            # A rejection receipt is not success. Let the activation path
            # query and validate its durable identity before returning Failed.
            receipt = result.get('receipt')
            if (action == 'lifecycle-activate-maintenance' and code == 409 and
                    isinstance(receipt, dict) and receipt.get('stage') == 'REJECTED'):
                return result
            raise RuntimeError('SERVICE_%s_FAILED:%s' %
                               (action.upper(), result.get('error', 'unknown')))
        return result

    @kvmagent.replyerror
    def state(self, req):
        command = self._request_body(req)
        operation_uuid = command.get('operationUuid') if isinstance(command, dict) else None
        try:
            # Apply the same request and local-host identity checks before a
            # service outage can select the host-local KSM journal fallback.
            self._operation_request(command)
            host_uuid = self._load_host_uuid()
            if not host_uuid or command.get('hostUuid') != host_uuid:
                raise ValueError('HOST_IDENTITY_UNKNOWN')
        except Exception as exc:
            result = {'success': False, 'status': 'Unknown',
                      'state': {}, 'reason': str(exc),
                      'operationUuid': operation_uuid}
            return self._reply(self._enrich_state(result))
        local_service_transport_unavailable = False
        try:
            result = self._dispatch('state', command)
        except Exception as exc:
            # KSM metrics remain useful while the optional zram service is
            # down.  Do not report absent service as unsupported capability.
            result = {'success': False, 'status': 'Unknown',
                      'state': {}, 'reason': str(exc),
                      'operationUuid': operation_uuid}
            if self._is_local_service_transport_unavailable(exc):
                local_service_transport_unavailable = True
                result = self._promote_ksm_only_state(result)
        result = self._enrich_state(result)
        if not local_service_transport_unavailable:
            result = self._promote_ksm_only_state(result, observer=True)
        # Keep the existing transport fact available even when native KSM
        # states are failed/mixed and therefore cannot qualify as a partial
        # KSM observation.  Identity was checked before dispatch, so this
        # cannot label a request for another host.  Partial admission and its
        # fence requirements remain guarded by _has_complete_native_ksm_read.
        if (local_service_transport_unavailable and
                result.get('status') == 'Unknown' and not result.get('success')):
            result['reasonCode'] = 'LOCAL_SERVICE_UNAVAILABLE'
        # A native KSM read can inform the KSM capability independently from
        # the optional Go control service.  This is not a control result: keep
        # Unknown/success=false and never synthesize ownership or removability.
        if (local_service_transport_unavailable and result.get('status') == 'Unknown' and
                not result.get('success') and self._has_complete_native_ksm_read(result)):
            result['observationKind'] = 'KSM_NATIVE_PARTIAL'
            result['reasonCode'] = 'LOCAL_SERVICE_UNAVAILABLE'
            state = result.get('state')
            result['bootId'] = state.get('bootId') if isinstance(state, dict) else None
            result['coldKsmAdmissionReady'] = self._cold_ksm_local_fence_clear()
            result['coldKsmAdmissionReason'] = ('LOCAL_CONTROL_FENCE_CLEAR'
                    if result['coldKsmAdmissionReady'] else 'LOCAL_CONTROL_FENCE_UNKNOWN')
        # Bind this read to the locally verified Agent identity and the boot
        # read by _enrich_state. These are current observations, never fields
        # retrofitted onto an immutable historical reconciliation receipt.
        result['hostUuid'] = host_uuid
        state = result.get('state')
        result['bootId'] = state.get('bootId') if isinstance(state, dict) else None
        return self._reply(result)

    @staticmethod
    def _has_complete_native_ksm_read(result):
        if not isinstance(result, dict):
            return False
        capabilities = result.get('capabilities')
        state = result.get('state')
        actual = state.get('actual') if isinstance(state, dict) else None
        ksm = actual.get('ksm') if isinstance(actual, dict) else None
        if (not isinstance(capabilities, dict) or capabilities.get('supported') is not True or
                capabilities.get('ksm') is not True or not isinstance(ksm, dict) or
                not isinstance(ksm.get('enabled'), bool)):
            return False
        for name in ('pagesToScan', 'sleepMillis'):
            value = ksm.get(name)
            if isinstance(value, bool) or not isinstance(value, INTEGER_TYPES) or value < 0:
                return False
        return True

    @kvmagent.replyerror
    def accounting(self, req):
        command = self._request_body(req)
        try:
            report = _accounting_wire_identity(self._readonly_query('accounting', command))
            result = {'success': True, 'status': 'Succeeded', 'state': report,
                      'hostUuid': command.get('hostUuid')}
        except Exception as exc:
            result = {'success': False, 'status': 'Unknown', 'state': {},
                      'reason': str(exc), 'hostUuid': command.get('hostUuid')}
        return self._reply(result)

    @kvmagent.replyerror
    def writeback_backends(self, req):
        command = self._request_body(req)
        try:
            self._readonly_query_request(command)
            backend, config, observation_error = {}, {}, None
            try:
                status = self._readonly_query('backend-state', command)
                detail = self._readonly_query('backend-view', command)
                backend = dict(detail)
                backend['backend_resource'] = status.get('backend_resource')
                config = detail.get('configured') or {}
            except Exception:
                # An offline service does not make a blank disk PREPARED.
                # Still return read-only candidates, with no ownership UUID.
                observation_error = 'BACKEND_SERVICE_OBSERVATION_UNAVAILABLE'
            inventory = probe_writeback_backends(command['hostUuid'], backend, config)
            inventory = self._decorate_backend_maintenance_inventory(
                inventory, status if not observation_error else None, command, observation_error)
            inventory = self._decorate_zram_pool_preparation_inventory(inventory, command)
            if observation_error:
                inventory.setdefault('reasons', []).append(observation_error)
                if inventory.get('status') == 'AVAILABLE':
                    inventory['status'] = 'PARTIAL'
            result = {'success': True, 'status': 'Succeeded', 'state': inventory,
                      'hostUuid': command['hostUuid']}
        except Exception as exc:
            result = {'success': False, 'status': 'Unknown', 'state': {},
                      'reason': str(exc), 'hostUuid': command.get('hostUuid')}
        return self._reply(result)

    def _read_backend_maintenance_receipt(self):
        class _Client(object):
            def __init__(self, plugin):
                self.plugin = plugin

            def get(self, path):
                if path != '/v1/backend-maintenance':
                    raise ValueError('BACKEND_MAINTENANCE_STATUS_PATH_INVALID')
                return self.plugin._service_request('backend-maintenance', {})

        try:
            return read_backend_maintenance_status(_Client(self)), None
        except Exception as service_error:
            # The service must remain stopped during the destructive reset.
            # Its standalone status command is strictly read-only and allows
            # inventory/reconcile to continue without starting another daemon.
            try:
                output = subprocess.check_output([
                    self.drain_binary, '--config', self.drain_config,
                    '--backend-maintenance-status'])
                receipt = json.loads(output.decode('utf-8'))
                if not isinstance(receipt, dict) or not receipt.get('stage'):
                    raise ValueError('BACKEND_MAINTENANCE_STATUS_INVALID')
                return receipt, None
            except Exception as status_error:
                return None, 'BACKEND_MAINTENANCE_STATUS_UNKNOWN:%s:%s' % (
                    service_error, status_error)

    def _read_zram_pool_preparation_receipt(self):
        class _Client(object):
            def __init__(self, plugin):
                self.plugin = plugin

            def get(self, path):
                if path != '/v1/zram-pool-maintenance':
                    raise ValueError('ZRAM_POOL_MAINTENANCE_STATUS_PATH_INVALID')
                return self.plugin._service_request('zram-pool-maintenance', {})

        try:
            receipt = _Client(self).get('/v1/zram-pool-maintenance')
            if not isinstance(receipt, dict) or not receipt.get('stage'):
                raise ValueError('ZRAM_POOL_PREPARATION_STATUS_INVALID')
            return receipt, None
        except Exception as service_error:
            try:
                output = subprocess.check_output([
                    self.drain_binary, '--config', self.drain_config,
                    '--zram-pool-preparation-status'])
                receipt = json.loads(output.decode('utf-8'))
                if not isinstance(receipt, dict) or not receipt.get('stage'):
                    raise ValueError('ZRAM_POOL_PREPARATION_STATUS_INVALID')
                return receipt, None
            except Exception as status_error:
                return None, 'ZRAM_POOL_PREPARATION_STATUS_UNKNOWN:%s:%s' % (
                    service_error, status_error)

    @staticmethod
    def _zram_pool_maintenance_systemd_unit(operation_uuid):
        if not MemoryOptimizationPlugin._valid_identifier(operation_uuid):
            raise ValueError('INVALID_OPERATION_UUID')
        return 'zstack-memory-zram-pool-maintenance-%s' % operation_uuid

    def _zram_pool_maintenance_intent_paths(self, operation_uuid, create=True):
        directory = os.path.join(self.operation_dir, 'zram-pool-maintenance')
        if create and not os.path.isdir(directory):
            os.makedirs(directory, 0o700)
        if not create and not os.path.isdir(directory):
            raise ValueError('ZRAM_POOL_MAINTENANCE_JOURNAL_UNAVAILABLE')
        if os.path.islink(directory) or os.path.realpath(directory) != directory:
            raise ValueError('ZRAM_POOL_MAINTENANCE_JOURNAL_UNTRUSTED')
        return directory, {
            'requestPath': os.path.join(directory, '%s.request.json' % operation_uuid),
            'receiptPath': os.path.join(directory, '%s.receipt.json' % operation_uuid),
            'stderrPath': os.path.join(directory, '%s.stderr' % operation_uuid),
            'intentPath': os.path.join(directory, '%s.intent.json' % operation_uuid),
        }

    def _zram_pool_preparation_request(self, command, snapshot):
        preparation = command.get('poolPreparation')
        expected = frozenset(('expectedHostBootId', 'expectedPoolGeneration', 'resetConfirmed'))
        if (not isinstance(preparation, dict) or set(preparation) != expected or
                command.get('scope') != 'Host' or command.get('targetHostUuids') not in (None, []) or
                command.get('policy') not in (None, {})):
            raise ValueError('ZRAM_POOL_PREPARATION_INVALID')
        if preparation.get('resetConfirmed') is not True:
            raise ValueError('ZRAM_POOL_PREPARATION_CONFIRMATION_REQUIRED')
        boot_id = self._current_boot_id()
        generation = preparation.get('expectedPoolGeneration')
        control_uuid = command.get('expectedControlOperationUuid')
        if not boot_id or preparation.get('expectedHostBootId') != boot_id:
            raise ValueError('ZRAM_POOL_PREPARATION_BOOT_MISMATCH')
        if not isinstance(generation, STRING_TYPES) or re.match(r'^[0-9a-f]{64}$', generation) is None:
            raise ValueError('ZRAM_POOL_PREPARATION_EXISTING_POOL_REQUIRED')
        if not self._valid_identifier(control_uuid):
            raise ValueError('ZRAM_POOL_PREPARATION_DRAIN_CONTROL_REQUIRED')
        if (snapshot.get('hostUuid') != command.get('hostUuid') or snapshot.get('bootId') != boot_id or
                snapshot.get('poolGeneration') != generation or
                snapshot.get('controlOperationUuid') != control_uuid or
                snapshot.get('canPrepareZramPool') is not True):
            reasons = snapshot.get('zramPoolPreparationReasons') or []
            raise ValueError(reasons[0] if reasons else 'ZRAM_POOL_PREPARATION_NOT_ELIGIBLE')
        request = OrderedDict([
            ('request_id', command['operationUuid']),
            ('expected_control_operation_uuid', control_uuid),
            ('expected_host_boot_id', boot_id),
            ('expected_pool_generation', generation),
            ('reset_confirmed', True),
        ])
        canonical = json.dumps(request, separators=(',', ':')).encode('utf-8')
        request['_request_fingerprint'] = hashlib.sha256(canonical).hexdigest()
        return request

    @staticmethod
    def _zram_pool_receipt_matches(receipt, request, boot_id):
        return (isinstance(receipt, dict) and isinstance(request, dict) and
                receipt.get('request_id') == request.get('request_id') and
                receipt.get('request_fingerprint') == request.get('_request_fingerprint') and
                receipt.get('expected_control_operation_uuid') == request.get('expected_control_operation_uuid') and
                receipt.get('host_boot_id') == boot_id and
                receipt.get('pool_generation') == request.get('expected_pool_generation'))

    def _prepare_zram_pool(self, command):
        operation_lock = None
        service_stopped_here = False
        executor_launched = False
        command = dict(command)
        try:
            self._operation_request(command)
            host_uuid = self._load_host_uuid()
            if not host_uuid or command.get('hostUuid') != host_uuid:
                raise ValueError('HOST_IDENTITY_UNKNOWN')
            if command.get('action') != 'prepareZramPool':
                raise ValueError('ZRAM_POOL_PREPARATION_INVALID')
            command['poolMaintenanceIntentPath'] = os.path.join(
                self.operation_dir, 'zram-pool-maintenance', '%s.intent.json' % command['operationUuid'])
            journal_state, prior = self._operation_file_state(command['operationUuid'])
            request_hash = self._operation_hash(command)
            if journal_state in ('corrupt', 'unreadable') or (journal_state == 'present' and not isinstance(prior, dict)):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE')
            if journal_state == 'present':
                if prior.get('requestHash') != request_hash:
                    raise ValueError('OPERATION_UUID_REUSE')
                return prior.get('readback') or self._maintenance_result(
                    command, 'Unknown', 'UNKNOWN', 'OPERATION_RECONCILE_REQUIRED')
            if journal_state != 'missing':
                raise ValueError('OPERATION_JOURNAL_UNAVAILABLE')
            try:
                operation_lock = self._acquire_host_control_lock()
            except (IOError, OSError) as exc:
                if exc.errno in (errno.EAGAIN, errno.EACCES):
                    return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'OPERATION_CONCURRENT')
                raise
            journal_state, prior = self._operation_file_state(command['operationUuid'])
            if journal_state != 'missing':
                if (journal_state == 'present' and isinstance(prior, dict) and
                        prior.get('requestHash') == request_hash):
                    return prior.get('readback') or self._maintenance_result(
                        command, 'Unknown', 'UNKNOWN', 'OPERATION_RECONCILE_REQUIRED')
                raise ValueError('OPERATION_UUID_REUSE' if journal_state == 'present' else
                                 'OPERATION_JOURNAL_UNAVAILABLE')
            if not self._service_unit_stopped():
                preview = self._zram_pool_preparation_eligibility(
                    host_uuid, command.get('expectedControlOperationUuid'))
                if preview.get('canPrepareZramPool') is not True:
                    reasons = preview.get('zramPoolPreparationReasons') or []
                    raise ValueError(reasons[0] if reasons else 'MEMORY_SERVICE_NOT_STOPPED')
                service_stopped_here = True
                try:
                    self._bounded_command_output(['systemctl', 'stop', self.drain_unit], 60)
                except (IOError, OSError, RuntimeError, subprocess.CalledProcessError):
                    pass
                if not self._service_unit_stopped():
                    raise ValueError('MEMORY_SERVICE_NOT_STOPPED')
            if not os.path.isfile(self.drain_binary) or not os.path.isfile(self.drain_config):
                raise ValueError('ZRAM_POOL_PREPARATION_EXECUTOR_UNAVAILABLE')
            snapshot = self._zram_pool_preparation_eligibility(
                host_uuid, command.get('expectedControlOperationUuid'))
            request = self._zram_pool_preparation_request(command, snapshot)
            _, paths = self._zram_pool_maintenance_intent_paths(command['operationUuid'])
            if any(os.path.lexists(path) for path in paths.values()):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE')
            wire_request = OrderedDict((key, value) for key, value in request.items()
                                       if key != '_request_fingerprint')
            self._atomic_json(paths['requestPath'], wire_request)
            unit = self._zram_pool_maintenance_systemd_unit(command['operationUuid'])
            intent = {'schema': 1, 'operationUuid': command['operationUuid'],
                      'hostUuid': host_uuid, 'bootId': self._current_boot_id(),
                      'requestHash': request_hash, 'requestFingerprint': request['_request_fingerprint'],
                      'unit': unit, 'requestPath': paths['requestPath'], 'receiptPath': paths['receiptPath'],
                      'stderrPath': paths['stderrPath'], 'configPath': self.drain_config,
                      'controlOperationUuid': command['expectedControlOperationUuid'],
                      'workerLaunchAttempted': True}
            self._atomic_json(paths['intentPath'], intent)
            if not self._record_operation(command, 'PREPARING',
                    self._maintenance_result(command, 'Draining', 'WORKER_STARTING')):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE')
            subprocess.check_call([
                'systemd-run', '--unit=%s' % unit, '--no-block',
                '--property=UMask=0077', '--property=RemainAfterExit=yes',
                '--property=TimeoutStartSec=infinity',
                '--property=StandardInput=file:%s' % paths['requestPath'],
                '--property=StandardOutput=file:%s' % paths['receiptPath'],
                '--property=StandardError=file:%s' % paths['stderrPath'],
                self.drain_binary, '--config', self.drain_config, '--prepare-zram-pool'])
            executor_launched = True
            result = self._maintenance_result(command, 'Draining', 'EXECUTOR_RUNNING')
            self._update_operation_record(command['operationUuid'], 'DRAINING', result)
            return result
        except ValueError as exc:
            stop_failure = None
            if service_stopped_here and not executor_launched:
                # Nothing was reset; return the drained service to its paused state.
                try:
                    self._bounded_command_output(['systemctl', 'start', self.drain_unit], 30)
                except (IOError, OSError, RuntimeError, subprocess.CalledProcessError):
                    logger.warn('drained memory service was not restarted after a rejected preparation')
            if self._valid_identifier(command.get('operationUuid')):
                state, prior = self._operation_file_state(command['operationUuid'])
                if state == 'missing' or (state == 'present' and isinstance(prior, dict) and
                                          prior.get('requestHash') == self._operation_hash(command)):
                    self._record_operation(command, 'REJECTED', {
                        'success': False, 'status': 'Failed', 'state': {'phase': 'FAILED'},
                        'reasonCode': str(exc), 'operationUuid': command.get('operationUuid')})
            return self._maintenance_result(command, 'Failed', 'FAILED', str(exc))
        except Exception as exc:
            logger.warn('zram pool preparation launch is uncertain: %s', exc)
            if self._valid_identifier(command.get('operationUuid')):
                self._update_operation_record(command['operationUuid'], 'UNKNOWN',
                    self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                             'ZRAM_POOL_PREPARATION_EXECUTOR_UNKNOWN'))
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                            'ZRAM_POOL_PREPARATION_EXECUTOR_UNKNOWN')
        finally:
            self._release_operation(operation_lock)

    def _reconcile_zram_pool(self, command, prior):
        operation_uuid = command.get('operationUuid')
        if (prior.get('hostUuid') != self._load_host_uuid() or prior.get('bootId') != self._current_boot_id()):
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'OPERATION_BOOT_CHANGED')
        if prior.get('action') != 'prepareZramPool':
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'OPERATION_ACTION_MISMATCH')
        try:
            intent_path = os.path.join(self.operation_dir, 'zram-pool-maintenance', '%s.intent.json' % operation_uuid)
            if prior.get('poolMaintenanceIntentPath') != intent_path:
                raise ValueError('ZRAM_POOL_MAINTENANCE_INTENT_INVALID')
            with open(intent_path, 'r') as stream:
                intent = json.load(stream)
            _, paths = self._zram_pool_maintenance_intent_paths(operation_uuid, create=False)
            if (intent.get('operationUuid') != operation_uuid or intent.get('hostUuid') != self._load_host_uuid() or
                    intent.get('bootId') != self._current_boot_id() or
                    intent.get('requestHash') != prior.get('requestHash') or
                    intent.get('unit') != self._zram_pool_maintenance_systemd_unit(operation_uuid) or
                    intent.get('configPath') != self.drain_config or
                    intent.get('controlOperationUuid') != prior.get('expectedControlOperationUuid') or
                    intent.get('workerLaunchAttempted') is not True):
                raise ValueError('ZRAM_POOL_MAINTENANCE_INTENT_INVALID')
            for key in ('requestPath', 'receiptPath', 'stderrPath'):
                if intent.get(key) != paths[key]:
                    raise ValueError('ZRAM_POOL_MAINTENANCE_INTENT_INVALID')
            with open(paths['requestPath'], 'r') as stream:
                wire_request = json.load(stream)
            request = OrderedDict([
                ('request_id', operation_uuid),
                ('expected_control_operation_uuid', prior.get('expectedControlOperationUuid')),
                ('expected_host_boot_id', self._current_boot_id()),
                ('expected_pool_generation', (prior.get('poolPreparation') or {}).get('expectedPoolGeneration')),
                ('reset_confirmed', True),
            ])
            request['_request_fingerprint'] = hashlib.sha256(
                json.dumps(OrderedDict((k, v) for k, v in request.items() if k != '_request_fingerprint'),
                           separators=(',', ':')).encode('utf-8')).hexdigest()
            if (wire_request != dict((k, v) for k, v in request.items() if k != '_request_fingerprint') or
                    request['_request_fingerprint'] != intent.get('requestFingerprint')):
                raise ValueError('ZRAM_POOL_MAINTENANCE_REQUEST_INVALID')
        except (IOError, OSError, ValueError, TypeError, AttributeError) as exc:
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN', str(exc))
        worker, exit_status = self._systemd_worker_exit(intent['unit'])
        if worker == 'running':
            return self._maintenance_result(command, 'Draining', 'EXECUTOR_RUNNING')
        if worker != 'exited':
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                             'ZRAM_POOL_PREPARATION_WORKER_STATE_UNKNOWN')
        if exit_status != 0:
            reason, detail, _ = self._backend_maintenance_exit_error(paths['stderrPath'])
            result = self._maintenance_result(command, 'Failed', 'FAILED_REQUIRES_REVIEW', reason)
            if detail:
                result['failureDetail'] = detail
            self._update_operation_record(operation_uuid, 'FAILED_REQUIRES_REVIEW', result)
            return result
        receipt, error = self._read_zram_pool_preparation_receipt()
        if error or not self._zram_pool_receipt_matches(receipt, request, self._current_boot_id()):
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                             error or 'ZRAM_POOL_PREPARATION_RECEIPT_UNKNOWN')
        if receipt.get('stage') == 'FAILED_REQUIRES_REVIEW':
            result = self._maintenance_result(command, 'Failed', receipt.get('stage'),
                                              receipt.get('reason') or receipt.get('stage'), receipt)
            self._update_operation_record(operation_uuid, receipt.get('stage'), result)
            return result
        if receipt.get('stage') in ('AWAITING_SERVICE_READBACK', 'FINALIZING'):
            return self._continue_zram_pool_preparation(command, prior, request, receipt)
        if receipt.get('stage') == 'APPLIED':
            disabled, reason = self._host_optimization_disabled()
            if not disabled:
                return self._maintenance_result(command, 'Unknown', 'HOST_POLICY_READBACK_UNKNOWN', reason, receipt)
            result = self._maintenance_result(command, 'Succeeded', 'APPLIED', receipt=receipt)
            self._update_operation_record(operation_uuid, 'APPLIED', result)
            return result
        return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
            'ZRAM_POOL_PREPARATION_RECEIPT_PENDING:%s' % receipt.get('stage'), receipt)

    def _continue_zram_pool_preparation(self, command, prior, request, receipt):
        operation_uuid = command.get('operationUuid')
        try:
            lock = self._acquire_host_control_lock()
        except (IOError, OSError):
            return self._maintenance_result(command, 'Draining', 'CONTINUATION_LOCK_BUSY')
        try:
            latest, error = self._read_zram_pool_preparation_receipt()
            if error or not self._zram_pool_receipt_matches(latest, request, self._current_boot_id()):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                error or 'ZRAM_POOL_PREPARATION_RECEIPT_UNKNOWN')
            current = self._load_operation({'operationUuid': operation_uuid})
            if (not isinstance(current, dict) or current.get('action') != 'prepareZramPool' or
                    current.get('hostUuid') != self._load_host_uuid() or current.get('bootId') != self._current_boot_id() or
                    current.get('requestHash') != prior.get('requestHash') or
                    current.get('poolMaintenanceIntentPath') != prior.get('poolMaintenanceIntentPath')):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                'OPERATION_JOURNAL_IDENTITY_MISMATCH', latest)
            if latest.get('stage') == 'APPLIED':
                disabled, reason = self._host_optimization_disabled()
                if not disabled:
                    return self._maintenance_result(command, 'Unknown', 'HOST_POLICY_READBACK_UNKNOWN', reason, latest)
                result = self._maintenance_result(command, 'Succeeded', 'APPLIED', receipt=latest)
                self._update_operation_record(operation_uuid, 'APPLIED', result)
                return result
            if latest.get('stage') not in ('AWAITING_SERVICE_READBACK', 'FINALIZING'):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                    'ZRAM_POOL_PREPARATION_RECEIPT_PENDING:%s' % latest.get('stage'), latest)
            progress = current.get('maintenanceProgress')
            if not isinstance(progress, dict):
                progress = {}
            service_state = self._maintenance_service_state()
            if service_state == 'inactive':
                if progress.get('serviceStartAttempted') is True:
                    return self._maintenance_result(command, 'Unknown', 'SERVICE_START_UNRESOLVED',
                                                    'ZRAM_POOL_SERVICE_START_UNRESOLVED', latest)
                config, _, _ = self._read_maintenance_config()
                if config.get('initial_efficiency_enabled') is True:
                    return self._maintenance_result(command, 'Unknown', 'SERVICE_CONFIG_NOT_DISABLED',
                        'ZRAM_POOL_INITIAL_POLICY_MUST_BE_DISABLED', latest)
                progress = dict(progress)
                progress.update({'serviceStartAttempted': True, 'serviceUnit': self.MANAGED_ZRAM_UNIT})
                pending = self._maintenance_result(command, 'Draining', 'SERVICE_START_REQUESTED', receipt=latest)
                if not self._persist_maintenance_progress(operation_uuid, 'SERVICE_START_REQUESTED',
                                                          pending, progress):
                    return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                    'OPERATION_JOURNAL_UNAVAILABLE', latest)
                try:
                    self._bounded_command_output(
                        ['systemctl', 'start', self.MANAGED_ZRAM_UNIT], 30)
                except (IOError, OSError, RuntimeError, subprocess.CalledProcessError):
                    service_state = self._maintenance_service_state()
                    if service_state not in ('active', 'starting'):
                        unknown = self._maintenance_result(command, 'Unknown', 'SERVICE_START_UNKNOWN',
                            'ZRAM_POOL_SERVICE_START_UNKNOWN', latest)
                        self._persist_maintenance_progress(operation_uuid, 'SERVICE_START_UNKNOWN', unknown, progress)
                        return unknown
                service_state = self._maintenance_service_state()
            if service_state == 'starting':
                pending = self._maintenance_result(command, 'Draining', 'SERVICE_STARTING', receipt=latest)
                self._persist_maintenance_progress(operation_uuid, 'SERVICE_STARTING', pending, progress)
                return pending
            if service_state != 'active':
                return self._maintenance_result(command, 'Unknown', 'SERVICE_STATE_UNKNOWN',
                    'ZRAM_POOL_SERVICE_STATE_UNKNOWN', latest)
            try:
                native = self._readonly_query('state', {'hostUuid': self._load_host_uuid()})
                host_state = self._readonly_query('host-cpu-state', {'hostUuid': self._load_host_uuid()})
            except Exception:
                return self._maintenance_result(command, 'Draining', 'SERVICE_READBACK_PENDING',
                                                'ZRAM_POOL_SERVICE_READBACK_UNAVAILABLE', latest)
            pool = native.get('host_zram')
            pool_uninitialized = (isinstance(pool, dict) and
                                  not pool.get('pool_generation') and
                                  pool.get('quality') == 'unavailable' and
                                  isinstance(pool.get('reason'), STRING_TYPES) and
                                  pool.get('reason').startswith('NO_QUALIFIED_MANAGED_POOL:'))
            if (host_state.get('efficiency_enabled') is not False or
                    native.get('maintenance_blocks_activation') is not True or
                    not pool_uninitialized):
                return self._maintenance_result(command, 'Draining', 'SERVICE_READBACK_PENDING',
                    'ZRAM_POOL_DISABLED_READBACK_MISMATCH', latest)
            verified = dict(progress)
            verified.update({'serviceReadbackVerified': True, 'serviceUnit': self.MANAGED_ZRAM_UNIT})
            pending = self._maintenance_result(command, 'Draining', 'FINALIZE_REQUESTED', receipt=latest)
            if not self._persist_maintenance_progress(operation_uuid, 'FINALIZE_REQUESTED', pending, verified):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                'OPERATION_JOURNAL_UNAVAILABLE', latest)
            try:
                self._service_request('zram-pool-maintenance-finalize', {'requestId': operation_uuid})
            except Exception:
                pass
            finalized, error = self._read_zram_pool_preparation_receipt()
            if (not error and self._zram_pool_receipt_matches(finalized, request, self._current_boot_id()) and
                    finalized.get('stage') == 'APPLIED'):
                disabled, reason = self._host_optimization_disabled()
                if not disabled:
                    return self._maintenance_result(command, 'Unknown', 'HOST_POLICY_READBACK_UNKNOWN', reason, finalized)
                result = self._maintenance_result(command, 'Succeeded', 'APPLIED', receipt=finalized)
                if not self._persist_maintenance_progress(operation_uuid, 'APPLIED', result, verified):
                    return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                    'OPERATION_JOURNAL_UNAVAILABLE', finalized)
                return result
            unknown = self._maintenance_result(command, 'Unknown', 'FINALIZE_PENDING',
                error or 'ZRAM_POOL_PREPARATION_FINALIZE_PENDING', finalized)
            self._persist_maintenance_progress(operation_uuid, 'FINALIZE_PENDING', unknown, verified)
            return unknown
        finally:
            self._release_operation(lock)

    def _service_unit_stopped(self):
        try:
            value = subprocess.check_output([
                'systemctl', 'show', self.drain_unit, '--property=ActiveState', '--value'])
            if not isinstance(value, str):
                value = value.decode('utf-8')
            return value.strip() == 'inactive'
        except (IOError, OSError, subprocess.CalledProcessError):
            return False

    def _read_maintenance_config(self):
        if (not isinstance(self.drain_config, STRING_TYPES) or
                not os.path.isabs(self.drain_config) or
                os.path.realpath(self.drain_config) != self.drain_config):
            raise ValueError('MAINTENANCE_CONFIG_PATH_UNTRUSTED')
        with open(self.drain_config, 'r') as stream:
            config = json.load(stream)
        if not isinstance(config, dict):
            raise ValueError('MAINTENANCE_CONFIG_INVALID')
        state_dir = config.get('state_dir')
        device = config.get('device')
        if (not isinstance(state_dir, STRING_TYPES) or not os.path.isabs(state_dir) or
                os.path.normpath(state_dir) != state_dir or state_dir == '/' or
                os.path.realpath(state_dir) != state_dir or not os.path.isdir(state_dir)):
            raise ValueError('MAINTENANCE_STATE_DIR_UNTRUSTED')
        if (not isinstance(device, STRING_TYPES) or
                re.match(r'^/dev/zram[0-9]+$', device) is None):
            raise ValueError('MAINTENANCE_ZRAM_DEVICE_UNKNOWN')
        return config, state_dir, device

    def _first_use_no_pool_verified(self, command=None, failed_backend_record=None,
                                    failed_backend_receipt=None,
                                    backend_preparation_out=None,
                                    rejected_record=None):
        """Prove an explicitly uninitialized first-use host; absence alone is not proof."""
        if command is not None:
            if not isinstance(command, dict):
                return False
            if 'operationUuid' in command:
                if not self._valid_identifier(command.get('operationUuid')):
                    return False
            else:
                # Inventory callers may only have a host context, not an
                # operation nonce. Treat that like a global no-current-op
                # check; never exclude a journal on their behalf.
                command = None
        active_control = self._get_active_control()
        active_control_requires_backend_proof = False
        if active_control:
            active_record = self._load_operation({'operationUuid': active_control})
            if (not self._valid_identifier(active_control) or
                    not isinstance(active_record, dict) or
                    active_record.get('operationUuid') != active_control or
                    not isinstance(active_record.get('bootId'), STRING_TYPES) or
                    not active_record['bootId']):
                return False
            active_ksm = self._first_use_terminal_ksm_record(
                active_record, allow_empty_noop=True)
            if active_ksm:
                if ((active_record.get('policy') or {}).get('ksm') and
                        active_record.get('bootId') != self._current_boot_id()):
                    return False
            elif not self._first_use_active_service_disable_safe(
                    active_record, command, failed_backend_record=failed_backend_record):
                # A KSM-only control may retain the already-prepared backend
                # as disabled metadata. It is accepted only after the complete
                # current APPLIED preparation proof below binds that metadata;
                # it is never an independent no-pool authorization.
                active_control_requires_backend_proof = True
        try:
            config, state_dir, device = self._read_maintenance_config()
            current_path = os.path.join(state_dir, 'backend-maintenance', 'current.json')
            maintenance_fence = os.path.join(state_dir, 'maintenance')
            backend_preparation = None
            if any(os.path.lexists(os.path.join(state_dir, name)) for name in (
                    'stock-pool.json', 'zram-ownership.json', 'managed-zram.json')):
                return False
            if failed_backend_receipt is None:
                # A finalized no-pool preparation is accepted only through
                # its complete worker/journal/current receipt proof. A live
                # maintenance fence still blocks all first-use paths.
                if os.path.lexists(maintenance_fence):
                    return False
                if os.path.lexists(current_path):
                    if (os.path.islink(current_path) or
                            os.path.realpath(os.path.dirname(current_path)) !=
                            os.path.dirname(current_path) or
                            os.path.islink(self.zram_config_path) or
                            os.path.islink(self.zram_config_template_path)):
                        return False
                    with open(self.zram_config_path, 'rb') as stream:
                        current_bytes = stream.read()
                    with open(self.zram_config_template_path, 'rb') as stream:
                        template_bytes = stream.read()
                    current_config = json.loads(current_bytes.decode('utf-8'))
                    template_config = json.loads(template_bytes.decode('utf-8'))
                    backend_preparation = self._first_use_backend_preparation_proof(
                        current_config, template_config, stopped_command=command)
                    if active_control_requires_backend_proof and backend_preparation is None:
                        return False
                    rejected_reason = ((rejected_record.get('applyEvidence') or {}).get('reason')
                                       if isinstance(rejected_record, dict) else None)
                    if rejected_reason == 'KSM_CLEAR_PRIOR_JOURNAL_INVALID':
                        if not isinstance(backend_preparation, dict):
                            return False
                        preparation_record = backend_preparation.get('record')
                        preparation = (preparation_record.get('backendPreparation')
                                       if isinstance(preparation_record, dict) else None)
                        if not isinstance(preparation, dict):
                            return False
                        prepared_backend = {
                            'operationUuid': backend_preparation.get('operationUuid'),
                            'record': preparation_record,
                            'bootId': self._current_boot_id(),
                            'resourceUuid': backend_preparation.get('resourceUuid'),
                            'capacityBytes': preparation.get('backendCapacityBytes'),
                        }
                        try:
                            current_ksm = self._managed_ksm_clear_ack(
                                prepared_backend=prepared_backend)
                        except (IOError, OSError, RuntimeError, ValueError, TypeError):
                            return False
                        if current_ksm is None:
                            return False
            else:
                if active_control_requires_backend_proof:
                    return False
                # Go persists the exact failed receipt at current.json and
                # leaves an empty maintenance directory as an activation
                # fence. The fence itself has no operation identity; bind it
                # only through the exact receipt, local request/worker files,
                # stop intent, boot, and operation record checked here.
                if (not isinstance(failed_backend_record, dict) or command is None or
                        not os.path.lexists(current_path) or os.path.islink(current_path) or
                        not os.path.isfile(current_path) or
                        not os.path.isdir(os.path.dirname(current_path)) or
                        os.path.islink(os.path.dirname(current_path)) or
                        not os.path.isdir(maintenance_fence) or os.path.islink(maintenance_fence) or
                        os.listdir(maintenance_fence)):
                    return False
                operation_uuid = command.get('operationUuid')
                if not self._valid_identifier(operation_uuid):
                    return False
                _, paths = self._maintenance_intent_paths(operation_uuid, create=False)
                if any(os.path.islink(paths[key]) or not os.path.isfile(paths[key])
                       for key in ('requestPath', 'receiptPath', 'stderrPath', 'intentPath')):
                    return False
                with open(paths['requestPath'], 'r') as stream:
                    persisted_request = json.load(stream)
                with open(paths['receiptPath'], 'r') as stream:
                    persisted_receipt = json.load(stream)
                with open(current_path, 'r') as stream:
                    current_receipt = json.load(stream)
                stop = ((failed_backend_record.get('maintenanceProgress') or {}).get('controllerStop')
                        if isinstance(failed_backend_record.get('maintenanceProgress'), dict) else None)
                readback = failed_backend_record.get('readback')
                readback_state = readback.get('state') if isinstance(readback, dict) else None
                if (not isinstance(stop, dict) or stop.get('workerLaunchAttempted') is not True or
                        persisted_request != stop.get('request') or
                        persisted_request.get('request_id') != operation_uuid or
                        failed_backend_record.get('stage') not in ('UNKNOWN', 'FAILED_REQUIRES_REVIEW') or
                        not isinstance(readback_state, dict) or
                        readback_state.get('maintenance') != failed_backend_receipt or
                        not self._maintenance_receipt_matches_request(
                            failed_backend_receipt, persisted_request, self._current_boot_id()) or
                        failed_backend_receipt.get('stage') != 'FAILED_REQUIRES_REVIEW' or
                        persisted_receipt != failed_backend_receipt or
                        current_receipt != failed_backend_receipt):
                    return False
                reason_code, _, stderr_error = self._backend_maintenance_exit_error(
                    paths['stderrPath'])
                receipt_reason = failed_backend_receipt.get('reason')
                if (not isinstance(receipt_reason, STRING_TYPES) or
                        not isinstance(stderr_error, STRING_TYPES) or
                        receipt_reason != stderr_error):
                    return False
                worker, exit_status = self._systemd_worker_exit(
                    self._maintenance_systemd_unit(operation_uuid))
                if worker != 'exited' or exit_status != 1:
                    return False
                backend_preparation = ({'operationUuid': command.get('operationUuid')}
                                       if command is not None and failed_backend_record is not None
                                       else None)
            if command is None:
                if self._has_unresolved_operation_journal():
                    return False
            elif not self._first_use_local_history_clear(
                    command, rejected_record=rejected_record,
                    backend_preparation=backend_preparation,
                    failed_backend_record=failed_backend_record):
                # The existing history validator excludes only this exact
                # PREPARING operation (UUID + request hash); all other
                # operation and KSM/VM evidence remains subject to its full
                # whitelist.
                return False
            swap_rows = open('/proc/swaps', 'r').read().splitlines()
            if not swap_rows or not swap_rows[0].startswith('Filename'):
                return False
            device_name = os.path.basename(device)
            if any(row.split() and row.split()[0] == device for row in swap_rows[1:]):
                return False
            base = os.path.join('/sys/block', device_name)
            with open(os.path.join(base, 'disksize'), 'r') as stream:
                disksize = stream.read().strip()
            # zram's mem_limit sysfs attribute is write-only on supported
            # kernels. The effective allocator limit is the fourth mm_stat
            # field, matching Go's readZramMemoryLimit contract.
            with open(os.path.join(base, 'mm_stat'), 'r') as stream:
                mm_stat = stream.read().split()
            if len(mm_stat) < 4 or len(mm_stat) > 16:
                return False
            memory_limit = mm_stat[3]
            if not memory_limit.isdigit():
                return False
            with open(os.path.join(base, 'backing_dev'), 'r') as stream:
                backing = stream.read().strip()
            if disksize != '0' or memory_limit != '0' or backing != 'none':
                return False
            # Permit a verified current-boot KSM-only controller, or a
            # completed empty KSM target that no longer owns settings.
            # Reuse the complete operation-history whitelist and the live
            # ACK check for still-managed KSM; an
            # ordinary Host writer, Unknown record, or old ZRAM operation
            # must not be interpreted as an empty first-use state.
            valid = (self._first_use_local_history_clear(
                        command,
                        rejected_record=rejected_record,
                        backend_preparation=backend_preparation,
                        failed_backend_record=failed_backend_record)
                    if command is not None else
                    self._first_use_local_history_clear(
                        {'operationUuid': None}, backend_preparation=backend_preparation))
            if (valid and isinstance(backend_preparation_out, dict) and
                    isinstance(backend_preparation, dict) and
                    isinstance(backend_preparation.get('stopProof'), dict)):
                backend_preparation_out['proof'] = backend_preparation['stopProof']
                backend_preparation_out['backendPreparation'] = {
                    'operationUuid': backend_preparation.get('operationUuid'),
                    'record': backend_preparation.get('record'),
                }
            return valid
        except (IOError, OSError, ValueError, TypeError):
            return False

    @staticmethod
    def _bounded_command_output(command, timeout_seconds):
        """Run a small local command with a Python 2-compatible poll deadline."""
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        deadline = linux.monotime() + timeout_seconds
        while process.poll() is None:
            remaining = deadline - linux.monotime()
            if remaining <= 0:
                # This terminates only the systemctl client process. The
                # managed service is never stopped or force-killed here.
                try:
                    process.terminate()
                except OSError:
                    pass
                if process.poll() is None:
                    try:
                        process.kill()
                    except OSError:
                        pass
                process.wait()
                raise RuntimeError('BOUNDED_COMMAND_TIMEOUT')
            time.sleep(min(0.05, remaining))
        output = process.communicate()[0]
        if process.returncode != 0:
            error = subprocess.CalledProcessError(process.returncode, command)
            # Match check_output's useful failure evidence, including on
            # Python 2 where subprocess APIs do not accept timeout=.
            error.output = output
            raise error
        return output

    @staticmethod
    def _controller_process_start_time(pid):
        try:
            with open('/proc/%s/stat' % pid, 'r') as stream:
                stat_text = stream.read()
            _comm, delim, tail = stat_text.rpartition(')')
            fields = tail.split()
            if not delim or len(fields) <= 19 or not fields[19].isdigit():
                return None
            return fields[19]
        except (IOError, OSError):
            return None

    def _cold_controller_identity(self, template_bytes, config_bytes):
        """Return a pinned identity only for the vendor-owned, non-restarting unit."""
        try:
            identity = self._first_use_runtime_identity(template_bytes, config_bytes)
            output = self._bounded_command_output([
                'systemctl', 'show', self.MANAGED_ZRAM_UNIT,
                '--property=Id', '--property=FragmentPath', '--property=DropInPaths',
                '--property=MainPID', '--property=ActiveState', '--property=KillMode',
                '--property=Restart', '--property=ExecStop'],
                5)
            if not isinstance(output, STRING_TYPES):
                output = output.decode('utf-8')
            props = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
            pid = str(identity.get('pid')) if isinstance(identity, dict) else ''
            if (not isinstance(identity, dict) or
                    props.get('Id') != self.MANAGED_ZRAM_UNIT or
                    props.get('FragmentPath') != '/usr/lib/systemd/system/zram-memory.service' or
                    props.get('DropInPaths', '').strip() or props.get('MainPID') != pid or
                    props.get('ActiveState') != 'active' or props.get('KillMode') != 'process' or
                    props.get('Restart') != 'no' or props.get('ExecStop', '').strip()):
                return None
            identity = dict(identity)
            identity.update({'unit': self.MANAGED_ZRAM_UNIT,
                             'fragmentPath': props['FragmentPath'],
                             'killMode': props['KillMode'], 'restart': props['Restart']})
            if (identity.get('bootId') != self._current_boot_id() or
                    self._controller_process_start_time(pid) != identity.get('processStartTime')):
                return None
            return identity
        except (IOError, OSError, ValueError, TypeError, RuntimeError,
                subprocess.CalledProcessError):
            return None

    def _signal_and_wait_cold_controller(self, command, identity, timeout=75):
        """SIGTERM only the revalidated PID; never stop the unit or force-kill."""
        try:
            config, _, _ = self._read_maintenance_config()
            with open(self.zram_config_template_path, 'rb') as stream:
                template_bytes = stream.read()
            with open(self.zram_config_path, 'rb') as stream:
                config_bytes = stream.read()
            current = self._cold_controller_identity(template_bytes, config_bytes)
            if (current != identity or not self._first_use_no_pool_verified(command)):
                return False, 'COLD_CONTROLLER_IDENTITY_CHANGED', None, None
            native = self._service_request('state', {})
            cpu = self._service_request('host-cpu-state', {})
            tuning = self._service_request('tuning-state', {})
            checked_at = time.time()
            if isinstance(native, dict):
                native = dict(native)
                native['host_cpu'] = cpu
                native['host_tuning_state'] = tuning
            if not self._first_use_state_safe(native, observation_time=checked_at):
                return False, 'COLD_CONTROLLER_NATIVE_STATE_UNSAFE', None, None
            # Re-read the unit immediately before the signal and reject an
            # observed PID/start-time change. This narrows (but cannot make
            # atomic) the check-to-signal window. No systemctl stop/kill path is
            # used, so systemd cannot escalate this bounded request to SIGKILL.
            output = self._bounded_command_output([
                'systemctl', 'show', self.MANAGED_ZRAM_UNIT,
                '--property=Id', '--property=MainPID', '--property=ActiveState',
                '--property=KillMode', '--property=Restart'],
                5)
            if not isinstance(output, STRING_TYPES):
                output = output.decode('utf-8')
            props = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
            pid = str(identity['pid'])
            if (props.get('Id') != self.MANAGED_ZRAM_UNIT or props.get('MainPID') != pid or
                    props.get('ActiveState') != 'active' or props.get('KillMode') != 'process' or
                    props.get('Restart') != 'no' or
                    self._controller_process_start_time(pid) != identity.get('processStartTime')):
                return False, 'COLD_CONTROLLER_IDENTITY_CHANGED', None, None
            # The unit read can itself take seconds. Require the observation to
            # remain fresh at the actual signal boundary; do not reuse an older
            # checkedAt merely because it passed before systemctl returned.
            checked_at = time.time()
            if not self._first_use_state_safe(native, observation_time=checked_at):
                return False, 'COLD_CONTROLLER_NATIVE_STATE_STALE', None, None
            os.kill(int(pid), signal.SIGTERM)
        except (IOError, OSError, ValueError, TypeError, RuntimeError,
                subprocess.CalledProcessError):
            return False, 'COLD_CONTROLLER_STOP_UNKNOWN', None, None

        deadline = linux.monotime() + timeout
        while linux.monotime() < deadline:
            try:
                remaining = deadline - linux.monotime()
                if remaining <= 0:
                    break
                output = self._bounded_command_output([
                    'systemctl', 'show', self.MANAGED_ZRAM_UNIT,
                    '--property=Id', '--property=MainPID', '--property=ActiveState',
                    '--property=KillMode', '--property=Restart'],
                    min(1, remaining))
                if not isinstance(output, STRING_TYPES):
                    output = output.decode('utf-8')
                props = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
                if props.get('Id') != self.MANAGED_ZRAM_UNIT:
                    return False, 'COLD_CONTROLLER_STOP_UNKNOWN', None, None
                main_pid = props.get('MainPID')
                if main_pid not in ('0', '', None) and main_pid != str(identity['pid']):
                    return False, 'COLD_CONTROLLER_IDENTITY_CHANGED', None, None
                current_start = self._controller_process_start_time(identity['pid'])
                if current_start is not None and current_start != identity['processStartTime']:
                    return False, 'COLD_CONTROLLER_IDENTITY_CHANGED', None, None
                if (main_pid == '0' and props.get('ActiveState') == 'inactive' and
                        current_start is None):
                    return True, None, native, checked_at
            except (IOError, OSError, ValueError, TypeError,
                    RuntimeError, subprocess.CalledProcessError):
                return False, 'COLD_CONTROLLER_STOP_UNKNOWN', None, None
            time.sleep(min(0.2, max(0, deadline - linux.monotime())))
        return False, 'COLD_CONTROLLER_STOP_TIMEOUT', None, None

    def _has_unresolved_operation_journal(self):
        unresolved = frozenset(('PREPARING', 'UNKNOWN', 'RECOVERING', 'ACTIVATING',
                                self.FIRST_USE_AUTHORIZING_STAGE, 'DRAINING', 'RESET_ISSUED',
                                'RESET_VERIFIED', 'BACKEND_CLAIMED',
                                'AWAITING_SERVICE_READBACK'))
        try:
            names = os.listdir(self.operation_dir)
        except (IOError, OSError):
            return True
        for name in names:
            if not name.endswith('.json'):
                continue
            operation_uuid = name[:-5]
            if not self._valid_identifier(operation_uuid):
                continue
            state, record = self._operation_file_state(operation_uuid)
            if state != 'present' or not isinstance(record, dict):
                return True
            if record.get('stage') in unresolved:
                return True
        return False

    def _drained_pool_generation(self, host_uuid, control_operation_uuid, native_check=True):
        """Verify the existing drain journal/intent/receipt and native read-only check.

        The native check takes the service state lock; while the service runs,
        native_check=False verifies the journal and receipt only.
        """
        if not self._valid_identifier(control_operation_uuid):
            return None
        record = self._load_operation({'operationUuid': control_operation_uuid})
        if (not isinstance(record, dict) or record.get('action') != 'drain' or
                record.get('stage') != 'APPLIED' or record.get('bootId') != self._current_boot_id() or
                record.get('hostUuid') != host_uuid):
            return None
        intent_path = os.path.join(self.operation_dir,
                                   '%s.drain-intent.json' % control_operation_uuid)
        try:
            with open(intent_path, 'r') as stream:
                intent = json.load(stream)
            if (not isinstance(intent, dict) or intent.get('operationUuid') != control_operation_uuid or
                    intent.get('bootId') != self._current_boot_id() or
                    intent.get('configPath') != self.drain_config or
                    not re.match(r'^[0-9a-fA-F]{64}$', str(intent.get('poolGeneration', '')))):
                return None
            with open(intent.get('receiptPath'), 'r') as stream:
                receipt = json.load(stream)
            if (not isinstance(receipt, dict) or
                    receipt.get('pool_generation') != intent.get('poolGeneration') or
                    receipt.get('state') != 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED' or
                    receipt.get('active') is not False or receipt.get('reset_performed') is not False):
                return None
            if not native_check:
                return intent.get('poolGeneration')
            native = json.loads(subprocess.check_output([
                self.drain_binary, '--config', self.drain_config, '--drain-check']).decode('utf-8'))
            if (not isinstance(native, dict) or
                    native.get('pool_generation') != intent.get('poolGeneration') or
                    native.get('state') != 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED' or
                    native.get('active') is not False or native.get('reset_performed') is not False):
                return None
            return intent.get('poolGeneration')
        except (IOError, OSError, ValueError, TypeError, subprocess.CalledProcessError):
            return None

    def _decorate_backend_maintenance_inventory(self, inventory, service_state, command,
                                               observation_error=None,
                                               allow_cold_active=False):
        reasons = []
        if not isinstance(inventory, dict):
            return inventory
        host_uuid = command.get('hostUuid')
        control_uuid = self._get_active_control()
        inventory['controlOperationUuid'] = control_uuid or None
        receipt, receipt_error = self._read_backend_maintenance_receipt()
        inventory['maintenance'] = receipt
        pool = ((service_state or {}).get('host_zram') or
                (service_state or {}).get('pool') or {})
        generation = pool.get('pool_generation') if isinstance(pool, dict) else None
        drained_generation = self._drained_pool_generation(
            host_uuid, control_uuid,
            native_check=self._maintenance_service_state() != 'active') if control_uuid else None
        if not (isinstance(generation, STRING_TYPES) and re.match(r'^[0-9a-fA-F]{64}$', generation)):
            generation = drained_generation
        elif drained_generation and generation != drained_generation:
            reasons.append('DRAIN_POOL_GENERATION_MISMATCH')
        first_use_ok = False
        if generation:
            inventory['poolGeneration'] = generation
        elif self._first_use_no_pool_verified(command):
            first_use_ok = True
            inventory['poolGeneration'] = 'none'
        else:
            inventory['poolGeneration'] = None

        candidates = inventory.get('candidates')
        owner_proof = None
        if (drained_generation and inventory.get('poolGeneration') == drained_generation and
                control_uuid):
            owner_proof = self._drained_backend_owner_proof(
                host_uuid, control_uuid, drained_generation)
        if owner_proof and isinstance(candidates, list):
            for candidate in candidates:
                if self._drained_backend_candidate_matches(owner_proof, candidate):
                    # The ordinary probe found exactly the previous backend
                    # disk, and sysfs shows its sole holder is the drained
                    # ZRAM device. Keep every other offline eligibility rule.
                    candidate['eligible'] = True
                    candidate['state'] = 'NEEDS_OFFLINE_PREPARATION'
                    candidate['reasons'] = ['NEEDS_OFFLINE_PREPARATION']
        eligible = isinstance(candidates, list) and any(
            isinstance(candidate, dict) and candidate.get('type') == 'block' and
            candidate.get('eligible') is True and
            candidate.get('state') == 'NEEDS_OFFLINE_PREPARATION' and
            candidate.get('writebackReady', candidate.get('writeback_ready')) is False and
            isinstance(candidate.get('identity'), STRING_TYPES) and
            re.match(r'^candidate:[0-9a-f]{64}$', candidate.get('identity'))
            for candidate in candidates)
        cold_active = False
        if allow_cold_active and self._maintenance_service_state() == 'active':
            try:
                native = self._service_request('state', {})
                cpu = self._service_request('host-cpu-state', {})
                if isinstance(native, dict):
                    native = dict(native)
                    native['host_cpu'] = cpu
                config, _, _ = self._read_maintenance_config()
                with open(self.zram_config_template_path, 'rb') as stream:
                    template_bytes = stream.read()
                with open(self.zram_config_path, 'rb') as stream:
                    config_bytes = stream.read()
                cold_active = (inventory.get('poolGeneration') == 'none' and
                               self._first_use_state_safe(native) and
                               self._first_use_no_pool_verified(command) and
                               self._cold_controller_identity(template_bytes, config_bytes) is not None)
            except (IOError, OSError, ValueError, TypeError, RuntimeError):
                cold_active = False
        if not self._service_unit_stopped() and not cold_active:
            reasons.append('MEMORY_SERVICE_NOT_STOPPED')
        if not eligible:
            reasons.append('NO_ELIGIBLE_WRITEBACK_CANDIDATE')
        if inventory.get('poolGeneration') is None:
            reasons.append('POOL_GENERATION_UNKNOWN')
        if receipt_error:
            reasons.append('BACKEND_MAINTENANCE_STATUS_UNKNOWN')
        elif isinstance(receipt, dict) and receipt.get('stage') not in ('NOT_STARTED', 'APPLIED'):
            reasons.append('BACKEND_MAINTENANCE_UNRESOLVED')
        if (control_uuid and inventory.get('poolGeneration') not in ('none', None) and
                not drained_generation):
            reasons.append('DRAIN_PROOF_UNAVAILABLE')
        if (inventory.get('poolGeneration') not in ('none', None) and
                (not control_uuid or not drained_generation)):
            reasons.append('DRAIN_PROOF_UNAVAILABLE')
        if inventory.get('poolGeneration') == 'none' and not first_use_ok:
            reasons.append('FIRST_USE_NO_POOL_PROOF_UNAVAILABLE')
        if self._has_unresolved_operation_journal() and not first_use_ok:
            # A completed drain journal is the permitted maintenance anchor.
            active = self._load_operation({'operationUuid': control_uuid}) if control_uuid else None
            if not (isinstance(active, dict) and active.get('action') == 'drain' and
                    active.get('stage') == 'APPLIED' and
                    self._drained_pool_generation(host_uuid, control_uuid)):
                reasons.append('OPERATION_JOURNAL_UNRESOLVED')
        inventory['canPrepare'] = not reasons
        inventory['preparationReasons'] = reasons
        return inventory

    def _zram_pool_preparation_eligibility(self, host_uuid, expected_control_uuid=None):
        reasons = []
        boot_id = self._current_boot_id()
        if not host_uuid or host_uuid != self._load_host_uuid():
            reasons.append('HOST_IDENTITY_UNKNOWN')
        control_uuid = self._get_active_control()
        if not boot_id:
            reasons.append('HOST_BOOT_ID_UNKNOWN')
        if not self._valid_identifier(control_uuid):
            reasons.append('DRAIN_CONTROL_OPERATION_UNKNOWN')
        if expected_control_uuid is not None and expected_control_uuid != control_uuid:
            reasons.append('DRAIN_CONTROL_OPERATION_MISMATCH')
        service_state = self._maintenance_service_state()
        running = service_state == 'active'
        generation = (self._drained_pool_generation(host_uuid, control_uuid, native_check=not running)
                      if control_uuid else None)
        if not generation:
            reasons.append('DRAIN_PROOF_UNAVAILABLE')
        # Preparation stops a drained, quiescent service itself and repeats
        # this check, including the native drain check, before any reset.
        if service_state != 'inactive' and not (running and self._drained_service_quiescent()):
            reasons.append('MEMORY_SERVICE_NOT_STOPPED')
        if self._has_unresolved_operation_journal():
            reasons.append('OPERATION_JOURNAL_UNRESOLVED')
        try:
            config, state_dir, device = self._read_maintenance_config()
            if config.get('initial_efficiency_enabled') is not False:
                reasons.append('HOST_MEMORY_OPTIMIZATION_NOT_DISABLED')
            if config.get('backend') not in (None, {}):
                reasons.append('WRITEBACK_BACKEND_CONFIGURED')
            policy_path = os.path.join(state_dir, 'policies', 'policies.json')
            if os.path.islink(policy_path) or os.path.realpath(policy_path) != policy_path:
                reasons.append('HOST_POLICY_PATH_UNTRUSTED')
            else:
                with open(policy_path, 'r') as stream:
                    policies = json.load(stream)
                host_policy = policies.get('host') if isinstance(policies, dict) else None
                if (not isinstance(host_policy, dict) or
                        host_policy.get('efficiency_enabled') is not False):
                    reasons.append('HOST_MEMORY_OPTIMIZATION_NOT_DISABLED')
            backend_receipt, backend_error = self._read_backend_maintenance_receipt()
            if backend_error:
                reasons.append('BACKEND_MAINTENANCE_STATUS_UNKNOWN')
            else:
                if isinstance(backend_receipt, dict) and backend_receipt.get('stage') not in ('NOT_STARTED', 'APPLIED'):
                    reasons.append('BACKEND_MAINTENANCE_UNRESOLVED')
            pool_receipt, receipt_error = self._read_zram_pool_preparation_receipt()
            if receipt_error:
                reasons.append('ZRAM_POOL_PREPARATION_STATUS_UNKNOWN')
            elif isinstance(pool_receipt, dict):
                # The service archives a completed preparation of an earlier drain cycle.
                earlier_cycle = (pool_receipt.get('stage') == 'APPLIED' and generation and
                                 pool_receipt.get('pool_generation') != generation)
                if pool_receipt.get('stage') not in ('NOT_STARTED',) and not earlier_cycle:
                    reasons.append('ZRAM_POOL_PREPARATION_ALREADY_REQUESTED')
            # A prior drain must leave the native KSM scanner stopped too, when
            # it controlled KSM; an unmanaged scanner is not the drain's to stop.
            if self._drain_controlled_ksm(control_uuid):
                with open('/sys/kernel/mm/ksm/run', 'r') as stream:
                    if stream.read().strip() != '0':
                        reasons.append('KSM_NOT_DISABLED')
            if not re.match(r'^/dev/zram[0-9]+$', device):
                reasons.append('ZRAM_DEVICE_UNKNOWN')
        except (IOError, OSError, ValueError, TypeError, KeyError):
            reasons.append('ZRAM_POOL_PREPARATION_EVIDENCE_UNKNOWN')
        return {'hostUuid': host_uuid, 'bootId': boot_id or None,
                'poolGeneration': generation, 'controlOperationUuid': control_uuid or None,
                'canPrepareZramPool': not reasons,
                'zramPoolPreparationReasons': reasons,
                'zramPoolPreparationQuality': 'Fresh' if not reasons else
                    ('Unknown' if any('UNKNOWN' in item for item in reasons) else 'Ineligible'),
                'zramPoolPreparationObservedAt': int(time.time() * 1000)}

    def _drained_service_quiescent(self):
        try:
            native = self._service_request('state', {})
        except Exception:
            return False
        lifecycle = native.get('lifecycle') if isinstance(native, dict) else None
        pool = native.get('host_zram') if isinstance(native, dict) else None
        return (isinstance(lifecycle, dict) and lifecycle.get('paused') is True and
                lifecycle.get('migrationHold') is None and
                native.get('maintenance_blocks_activation') is True and
                not native.get('pending_operations') and
                isinstance(pool, dict) and not pool.get('pool_generation'))

    def _drain_controlled_ksm(self, drain_uuid):
        """Drain stops KSM through the KSM section of the control it replaced."""
        drain = self._load_operation({'operationUuid': drain_uuid}) if self._valid_identifier(drain_uuid) else None
        prior_uuid = drain.get('expectedControlOperationUuid') if isinstance(drain, dict) else None
        prior = self._load_operation({'operationUuid': prior_uuid}) if self._valid_identifier(prior_uuid) else None
        return not isinstance(prior, dict) or bool((prior.get('policy') or {}).get('ksm'))

    def _decorate_zram_pool_preparation_inventory(self, inventory, command):
        if not isinstance(inventory, dict):
            return inventory
        snapshot = self._zram_pool_preparation_eligibility(command.get('hostUuid'))
        # Preserve the writeback inventory's established identity fields. Cold
        # preparation has a separate eligibility decision and must not erase a
        # live pool generation (or its explicit "none" value) on an unrelated
        # snapshot with incomplete drain evidence.
        identity_matches = all(inventory.get(key) == snapshot.get(key) for key in
                               ('bootId', 'poolGeneration', 'controlOperationUuid'))
        can_prepare = bool(snapshot.get('canPrepareZramPool')) and identity_matches
        reasons = list(snapshot.get('zramPoolPreparationReasons') or [])
        if snapshot.get('canPrepareZramPool') and not identity_matches:
            reasons.append('COLD_POOL_INVENTORY_IDENTITY_MISMATCH')
        inventory.update({
            'canPrepareZramPool': can_prepare,
            'zramPoolPreparationReasons': reasons,
            'zramPoolPreparationQuality': snapshot.get('zramPoolPreparationQuality') if can_prepare else
                ('Unknown' if any('UNKNOWN' in item for item in reasons) else 'Ineligible'),
            'zramPoolPreparationObservedAt': snapshot.get('zramPoolPreparationObservedAt'),
        })
        return inventory

    def _fresh_backend_maintenance_inventory(self, host_uuid, command=None,
                                             allow_cold_active=False):
        backend, config, status, observation_error = {}, {}, None, None
        try:
            status = self._readonly_query('backend-state', {'hostUuid': host_uuid})
            detail = self._readonly_query('backend-view', {'hostUuid': host_uuid})
            backend['backend_resource'] = status.get('backend_resource')
            config = detail.get('configured') or {}
            backend.update(detail)
        except Exception as exc:
            observation_error = str(exc)
            status = None
            backend, config = {}, {}
        inventory = probe_writeback_backends(host_uuid, backend, config)
        return self._decorate_backend_maintenance_inventory(
            inventory, status, command or {'hostUuid': host_uuid}, observation_error,
            allow_cold_active=allow_cold_active)

    @staticmethod
    def _atomic_json(path, value):
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory, 0o700)
        if os.path.islink(directory) or os.path.realpath(directory) != directory:
            raise ValueError('MAINTENANCE_JOURNAL_DIRECTORY_UNTRUSTED')
        fd, temporary = tempfile.mkstemp(prefix='.maintenance-', dir=directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream, sort_keys=True, separators=(',', ':'))
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temporary, path)
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise

    @staticmethod
    def _maintenance_systemd_unit(operation_uuid):
        if not MemoryOptimizationPlugin._valid_identifier(operation_uuid):
            raise ValueError('INVALID_OPERATION_UUID')
        return 'zstack-memory-backend-maintenance-%s' % operation_uuid

    def _maintenance_intent_paths(self, operation_uuid, create=True):
        directory = os.path.join(self.operation_dir, 'backend-maintenance')
        if create and not os.path.isdir(directory):
            os.makedirs(directory, 0o700)
        if not create and not os.path.isdir(directory):
            raise ValueError('MAINTENANCE_JOURNAL_UNAVAILABLE')
        if os.path.islink(directory) or os.path.realpath(directory) != directory:
            raise ValueError('MAINTENANCE_JOURNAL_DIRECTORY_UNTRUSTED')
        return directory, {
            'requestPath': os.path.join(directory, '%s.request.json' % operation_uuid),
            'receiptPath': os.path.join(directory, '%s.receipt.json' % operation_uuid),
            'stderrPath': os.path.join(directory, '%s.stderr' % operation_uuid),
            'intentPath': os.path.join(directory, '%s.intent.json' % operation_uuid),
        }

    def _backend_preparation_request(self, command, inventory):
        preparation = command.get('backendPreparation')
        expected_keys = frozenset(('candidateId', 'expectedHostBootId',
                                   'expectedPoolGeneration', 'backendCapacityBytes',
                                   'resetConfirmed'))
        if not isinstance(preparation, dict) or set(preparation) != expected_keys:
            raise ValueError('MEMORY_BACKEND_PREPARATION_INVALID')
        if (command.get('scope') != 'Host' or command.get('targetHostUuids') not in (None, []) or
                command.get('policy') not in (None, {})):
            raise ValueError('MEMORY_BACKEND_PREPARATION_INVALID')
        if preparation.get('resetConfirmed') is not True:
            raise ValueError('BACKEND_MAINTENANCE_CONFIRMATION_REQUIRED')
        capacity = preparation.get('backendCapacityBytes')
        if (isinstance(capacity, bool) or not isinstance(capacity, INTEGER_TYPES) or
                capacity < 8192 or capacity > 9007199254740991 or capacity % 4096 != 0):
            raise ValueError('BACKEND_MAINTENANCE_CAPACITY_REQUIRED')
        generation = preparation.get('expectedPoolGeneration')
        if (not isinstance(generation, STRING_TYPES) or
                (generation != 'none' and re.match(r'^[0-9a-f]{64}$', generation) is None)):
            raise ValueError('BACKEND_MAINTENANCE_POOL_GENERATION_INVALID')
        boot_id = self._current_boot_id()
        if (not boot_id or preparation.get('expectedHostBootId') != boot_id):
            raise ValueError('BACKEND_MAINTENANCE_BOOT_ID_MISMATCH')
        if inventory.get('hostUuid') != command.get('hostUuid'):
            raise ValueError('BACKEND_RESOURCE_HOST_MISMATCH')
        if inventory.get('bootId') != boot_id:
            raise ValueError('BACKEND_MAINTENANCE_BOOT_ID_MISMATCH')
        if inventory.get('poolGeneration') != generation:
            raise ValueError('BACKEND_MAINTENANCE_POOL_GENERATION_MISMATCH')
        if inventory.get('canPrepare') is not True:
            reasons = inventory.get('preparationReasons') or []
            raise ValueError(reasons[0] if reasons else 'BACKEND_MAINTENANCE_NOT_ELIGIBLE')
        internal = dict(preparation)
        internal['requestId'] = command['operationUuid']
        return build_backend_maintenance_request(inventory, internal)

    @staticmethod
    def _maintenance_result(command, status, phase, reason=None, receipt=None):
        result = {'success': status in ('Succeeded', 'Draining'), 'status': status,
                  'state': {'phase': phase, 'writebackReady': False},
                  'operationUuid': command.get('operationUuid')}
        if receipt is not None:
            result['state']['maintenance'] = receipt
        if reason:
            result['reason'] = reason
            result['reasonCode'] = reason if re.match(r'^[A-Z][A-Z0-9_]+$', reason) else 'BACKEND_MAINTENANCE_UNKNOWN'
        return result

    def _maintenance_service_state(self):
        """Read the one managed service unit; never follow an alias/config override."""
        if self.drain_unit != self.MANAGED_ZRAM_UNIT:
            return 'unknown'
        try:
            output = subprocess.check_output([
                'systemctl', 'show', self.MANAGED_ZRAM_UNIT,
                '--property=Id', '--property=ActiveState', '--property=SubState'])
            if not isinstance(output, str):
                output = output.decode('utf-8')
            values = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
            if values.get('Id') != self.MANAGED_ZRAM_UNIT:
                return 'unknown'
            active, sub = values.get('ActiveState'), values.get('SubState')
            if active == 'active' and sub in ('running', 'listening'):
                return 'active'
            if active == 'activating':
                return 'starting'
            if active == 'inactive' and sub in ('dead', 'exited'):
                return 'inactive'
            if active == 'failed':
                return 'failed'
        except (IOError, OSError, subprocess.CalledProcessError):
            pass
        return 'unknown'

    def _persist_maintenance_progress(self, operation_uuid, stage, result, progress):
        """Durably persist continuation before/after service start and finalize."""
        record = self._load_operation({'operationUuid': operation_uuid})
        if (not isinstance(record, dict) or record.get('action') not in
                ('prepareWritebackBackend', 'prepareZramPool')):
            return False
        record['stage'] = stage
        record['updatedAt'] = int(time.time() * 1000)
        record['readback'] = result
        record['maintenanceProgress'] = dict(progress or {})
        try:
            self._atomic_json(self._operation_path(operation_uuid), record)
            return True
        except (IOError, OSError, ValueError):
            return False

    @staticmethod
    def _maintenance_receipt_matches_request(receipt, request, boot_id):
        if not isinstance(receipt, dict) or not isinstance(request, dict):
            return False
        target = request.get('target_identity')
        receipt_target = receipt.get('target_identity')
        if not isinstance(target, dict) or not isinstance(receipt_target, dict):
            return False
        # BackendFingerprint's Go JSON encoder always emits this bool. Older
        # block-only requests omitted its false zero value. Normalize only that
        # documented default; retain exact matching of all identity fields and
        # reject non-bools (Python otherwise treats 0 as equal to False).
        target = dict(target)
        receipt_target = dict(receipt_target)
        for identity in (target, receipt_target):
            if 'direct_io' not in identity:
                identity['direct_io'] = False
            elif not isinstance(identity['direct_io'], bool):
                return False
        expected_pool = request.get('expected_pool_generation')
        receipt_pool = receipt.get('pool_generation')
        return (receipt.get('request_id') == request.get('request_id') and
                receipt.get('candidate_id') == request.get('candidate_id') and
                request.get('expected_host_boot_id') == boot_id and
                receipt.get('host_boot_id') == boot_id and
                receipt_target == target and
                ((expected_pool == 'none' and receipt_pool in (None, '')) or
                 (isinstance(expected_pool, str) and expected_pool == receipt_pool)))

    def _verify_maintenance_service_readback(self, host_uuid, request, receipt):
        """Require the disabled host policy and exact prepared backend before finalize."""
        if self.drain_unit != self.MANAGED_ZRAM_UNIT:
            return False, 'MANAGED_MEMORY_SERVICE_UNIT_MISMATCH'
        try:
            policy = self._readonly_query('host-cpu-state', {'hostUuid': host_uuid})
            if policy.get('efficiency_enabled') is not False:
                return False, 'HOST_MEMORY_OPTIMIZATION_NOT_DISABLED'
            status = self._readonly_query('backend-state', {'hostUuid': host_uuid})
            detail = self._readonly_query('backend-view', {'hostUuid': host_uuid})
        except Exception:
            return False, 'BACKEND_SERVICE_READBACK_UNAVAILABLE'
        backend = status.get('backend_resource') if isinstance(status, dict) else None
        resource_uuid = receipt.get('backend_resource_uuid')
        if (not isinstance(backend, dict) or not resource_uuid or
                backend.get('resource_uuid') != resource_uuid or
                backend.get('state') != 'PREPARED' or backend.get('active') is not False or
                backend.get('fingerprint') in (None, '') or
                backend.get('capacity_bytes') != request.get('backend_capacity_bytes')):
            return False, 'BACKEND_SERVICE_PREPARED_READBACK_MISMATCH'
        if (detail.get('claimed') is not True or detail.get('identity_qualified') is not True or
                detail.get('ownership_generation') != resource_uuid):
            return False, 'BACKEND_SERVICE_IDENTITY_READBACK_MISMATCH'
        effective = detail.get('effective') or {}
        identity = effective.get('identity') if isinstance(effective, dict) else None
        target = request.get('target_identity') or {}
        expected_identity = {
            'boot_id': target.get('boot_id'),
            'canonical_device': target.get('canonical_device'),
            'rdev': target.get('rdev'),
            'node_inode': target.get('node_inode'),
            'sysfs_inode': target.get('sysfs_inode'),
            'capacity_bytes': target.get('capacity_bytes'),
        }
        if not isinstance(identity, dict) or any(
                identity.get(key) is None or str(identity.get(key)) != str(value)
                for key, value in expected_identity.items()):
            return False, 'BACKEND_SERVICE_TARGET_IDENTITY_MISMATCH'
        # Keep the ordinary candidate API and UI contract honest: the claimed
        # disk must now be the uniquely prepared, ready resource.
        merged = dict(detail)
        merged['backend_resource'] = backend
        inventory = probe_writeback_backends(host_uuid, merged, detail.get('configured') or {})
        candidates = inventory.get('candidates') if isinstance(inventory, dict) else None
        candidate = next((item for item in candidates or []
                          if isinstance(item, dict) and item.get('resourceUuid') == resource_uuid), None)
        if (inventory.get('hostUuid') != host_uuid or
                inventory.get('bootId') != request.get('expected_host_boot_id') or
                candidate is None or candidate.get('state') != 'PREPARED' or
                candidate.get('writebackReady') is not True or candidate.get('eligible') is not True):
            return False, 'BACKEND_SERVICE_CANDIDATE_NOT_READY'
        return True, None

    def _prepare_backend_maintenance(self, command):
        operation_lock = None
        command = dict(command)
        try:
            self._operation_request(command)
            host_uuid = self._load_host_uuid()
            if not host_uuid or command.get('hostUuid') != host_uuid:
                raise ValueError('HOST_IDENTITY_UNKNOWN')
            if command.get('action') != 'prepareWritebackBackend':
                raise ValueError('MEMORY_BACKEND_PREPARATION_INVALID')
            command['maintenanceIntentPath'] = os.path.join(
                self.operation_dir, 'backend-maintenance',
                '%s.intent.json' % command['operationUuid'])
            journal_state, prior = self._operation_file_state(command['operationUuid'])
            request_hash = self._operation_hash(command)
            if journal_state in ('corrupt', 'unreadable') or (journal_state == 'present' and not isinstance(prior, dict)):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': command['operationUuid']}
            if journal_state == 'present':
                if prior.get('requestHash') != request_hash:
                    raise ValueError('OPERATION_UUID_REUSE')
                # A request UUID is one-shot. Even an UNKNOWN or interrupted
                # launch can only be resolved by reconcile, never a new fork.
                return prior.get('readback') or {
                    'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'OPERATION_RECONCILE_REQUIRED',
                    'operationUuid': command['operationUuid']}
            if journal_state != 'missing':
                raise ValueError('OPERATION_JOURNAL_UNAVAILABLE')
            try:
                operation_lock = self._acquire_host_control_lock()
            except (IOError, OSError) as exc:
                if exc.errno in (errno.EAGAIN, errno.EACCES):
                    return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                            'reasonCode': 'OPERATION_CONCURRENT',
                            'operationUuid': command['operationUuid']}
                raise
            # Recheck the nonce under the host lock before native probing.
            journal_state, prior = self._operation_file_state(command['operationUuid'])
            if journal_state != 'missing':
                if journal_state == 'present' and isinstance(prior, dict) and prior.get('requestHash') == request_hash:
                    return prior.get('readback') or {
                        'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_RECONCILE_REQUIRED',
                        'operationUuid': command['operationUuid']}
                raise ValueError('OPERATION_UUID_REUSE' if journal_state == 'present' else
                                 'OPERATION_JOURNAL_UNAVAILABLE')
            service_state = self._maintenance_service_state()
            cold_identity = None
            backend_preparation_check = {}
            if service_state != 'inactive':
                if service_state != 'active':
                    raise ValueError('MEMORY_SERVICE_STATE_UNKNOWN')
                with open(self.zram_config_template_path, 'rb') as stream:
                    template_bytes = stream.read()
                with open(self.zram_config_path, 'rb') as stream:
                    config_bytes = stream.read()
                cold_identity = self._cold_controller_identity(template_bytes, config_bytes)
                native = self._service_request('state', {})
                cpu = self._service_request('host-cpu-state', {})
                if isinstance(native, dict):
                    native = dict(native)
                    native['host_cpu'] = cpu
                if (cold_identity is None or not self._first_use_state_safe(native) or
                        not self._first_use_no_pool_verified(
                            backend_preparation_out=backend_preparation_check)):
                    raise ValueError('COLD_BACKEND_FIRST_USE_NOT_PROVEN')
            if not os.path.isfile(self.drain_binary) or not os.path.isfile(self.drain_config):
                raise ValueError('BACKEND_MAINTENANCE_EXECUTOR_UNAVAILABLE')
            inventory = self._fresh_backend_maintenance_inventory(
                host_uuid, command=command, allow_cold_active=cold_identity is not None)
            request = self._backend_preparation_request(command, inventory)
            directory, paths = self._maintenance_intent_paths(command['operationUuid'])
            if any(os.path.lexists(path) for path in paths.values()):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': command['operationUuid']}
            request['request_id'] = command['operationUuid']
            unit = self._maintenance_systemd_unit(command['operationUuid'])
            stop_progress = None
            if cold_identity is not None:
                controller_stop = {
                    'attempted': True, 'unit': self.MANAGED_ZRAM_UNIT,
                    'hostUuid': host_uuid, 'bootId': self._current_boot_id(),
                    'requestHash': request_hash, 'identity': cold_identity,
                    'request': request, 'nativeState': native,
                    'workerLaunchAttempted': False}
                if isinstance(backend_preparation_check.get('proof'), dict):
                    controller_stop['backendPreparationProof'] = \
                        backend_preparation_check['proof']
                stop_progress = {'controllerStop': controller_stop}
                starting = self._maintenance_result(
                    command, 'Draining', 'CONTROLLER_STOP_REQUESTED')
                if not self._record_operation(command, 'PREPARING', starting):
                    return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                            'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                            'operationUuid': command['operationUuid']}
                if not self._persist_maintenance_progress(
                        command['operationUuid'], 'PREPARING', starting, stop_progress):
                    return self._maintenance_result(
                        command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE')
                stopped, stop_error, stop_native, native_checked_at = self._signal_and_wait_cold_controller(
                    command, cold_identity)
                if not stopped:
                    unknown = self._maintenance_result(
                        command, 'Unknown', 'CONTROLLER_STOP_UNRESOLVED', stop_error)
                    self._persist_maintenance_progress(
                        command['operationUuid'], 'UNKNOWN', unknown, stop_progress)
                    return unknown
                # Bind the completed stop to the exact fresh native observation
                # revalidated immediately before SIGTERM, not the earlier
                # inventory sample used during initial admission.
                stop_progress['controllerStop']['nativeState'] = stop_native
                stop_progress['controllerStop']['nativeStateCheckedAt'] = native_checked_at
                stop_progress['controllerStop']['completed'] = True
                if not self._persist_maintenance_progress(
                        command['operationUuid'], 'PREPARING', starting, stop_progress):
                    return self._maintenance_result(
                        command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE')
                if not self._first_use_no_pool_verified(command):
                    unknown = self._maintenance_result(
                        command, 'Unknown', 'CONTROLLER_STOP_READBACK_UNKNOWN',
                        'COLD_BACKEND_FIRST_USE_NOT_PROVEN')
                    self._persist_maintenance_progress(
                        command['operationUuid'], 'UNKNOWN', unknown, stop_progress)
                    return unknown
                stop_progress['controllerStop']['continuationReady'] = True
                if not self._persist_maintenance_progress(
                        command['operationUuid'], 'PREPARING', starting, stop_progress):
                    return self._maintenance_result(
                        command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE')
                # The selected candidate is re-probed after controller exit;
                # an old active-service observation is never sent to Go.
                fresh_inventory = self._fresh_backend_maintenance_inventory(
                    host_uuid, command=command)
                fresh_request = self._backend_preparation_request(command, fresh_inventory)
                if fresh_request != request:
                    unknown = self._maintenance_result(
                        command, 'Unknown', 'CANDIDATE_READBACK_CHANGED',
                        'COLD_BACKEND_CANDIDATE_CHANGED')
                    self._persist_maintenance_progress(
                        command['operationUuid'], 'UNKNOWN', unknown, stop_progress)
                    return unknown

            self._atomic_json(paths['requestPath'], request)
            intent = {'schema': 1, 'operationUuid': command['operationUuid'],
                      'hostUuid': host_uuid, 'bootId': self._current_boot_id(),
                      'requestHash': request_hash, 'unit': unit,
                      'requestPath': paths['requestPath'], 'receiptPath': paths['receiptPath'],
                      'stderrPath': paths['stderrPath'], 'configPath': self.drain_config,
                      'controlOperationUuid': self._get_active_control(),
                      'workerLaunchAttempted': True}
            # The durable intent precedes the only systemd-run call. If this
            # process exits in the syscall window, reconcile observes status;
            # apply with this UUID is never allowed to launch again.
            self._atomic_json(paths['intentPath'], intent)
            worker_starting = self._maintenance_result(command, 'Draining', 'WORKER_STARTING')
            if cold_identity is None:
                if not self._record_operation(command, 'PREPARING', worker_starting):
                    return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                            'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                            'operationUuid': command['operationUuid']}
            else:
                stop_progress['controllerStop']['workerLaunchAttempted'] = True
                if not self._persist_maintenance_progress(
                        command['operationUuid'], 'PREPARING', worker_starting, stop_progress):
                    return self._maintenance_result(
                        command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE')
            subprocess.check_call([
                'systemd-run', '--unit=%s' % unit, '--no-block',
                '--property=UMask=0077', '--property=RemainAfterExit=yes',
                '--property=TimeoutStartSec=infinity',
                '--property=StandardInput=file:%s' % paths['requestPath'],
                '--property=StandardOutput=file:%s' % paths['receiptPath'],
                '--property=StandardError=file:%s' % paths['stderrPath'],
                self.drain_binary, '--config', self.drain_config,
                '--prepare-backend-maintenance'])
            result = self._maintenance_result(command, 'Draining', 'EXECUTOR_RUNNING')
            self._update_operation_record(command['operationUuid'], 'DRAINING', result)
            return result
        except ValueError as exc:
            stop_failure = None
            if self._valid_identifier(command.get('operationUuid')):
                state, prior = self._operation_file_state(command['operationUuid'])
                prior_progress = prior.get('maintenanceProgress') if isinstance(prior, dict) else None
                stop = prior_progress.get('controllerStop') if isinstance(prior_progress, dict) else None
                if (state == 'present' and isinstance(stop, dict) and
                        stop.get('attempted') is True and
                        prior.get('requestHash') == self._operation_hash(command)):
                    failure = self._maintenance_result(
                        command, 'Unknown', 'CONTROLLER_STOPPED_PREPARATION_UNRESOLVED', str(exc))
                    self._persist_maintenance_progress(
                        command['operationUuid'], 'UNKNOWN', failure, prior_progress)
                    stop_failure = failure
                elif state == 'missing' or (state == 'present' and isinstance(prior, dict) and
                                             prior.get('requestHash') == self._operation_hash(command)):
                    self._record_operation(command, 'REJECTED', {'success': False, 'status': 'Failed',
                        'state': {'phase': 'FAILED'}, 'reasonCode': str(exc),
                        'operationUuid': command.get('operationUuid')})
            if stop_failure is not None:
                return stop_failure
            return {'success': False, 'status': 'Failed', 'state': {'phase': 'FAILED'},
                    'reason': str(exc), 'reasonCode': str(exc),
                    'operationUuid': command.get('operationUuid')}
        except Exception as exc:
            logger.warn('writeback backend maintenance launch is uncertain: %s', exc)
            if self._valid_identifier(command.get('operationUuid')):
                self._update_operation_record(command['operationUuid'], 'UNKNOWN',
                    self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'BACKEND_MAINTENANCE_EXECUTOR_UNKNOWN'))
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'BACKEND_MAINTENANCE_EXECUTOR_UNKNOWN',
                    'operationUuid': command.get('operationUuid')}
        finally:
            self._release_operation(operation_lock)

    def _systemd_worker_exit(self, unit):
        try:
            output = subprocess.check_output([
                'systemctl', 'show', unit, '--property=ActiveState', '--property=SubState',
                '--property=ExecMainCode', '--property=ExecMainStatus',
                '--property=MainPID', '--property=ControlPID'])
            if not isinstance(output, str):
                output = output.decode('utf-8')
            values = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        except (IOError, OSError, subprocess.CalledProcessError):
            return 'unknown', None
        active, sub = values.get('ActiveState'), values.get('SubState')
        code, status = values.get('ExecMainCode'), values.get('ExecMainStatus')
        main_pid, control_pid = values.get('MainPID'), values.get('ControlPID')
        if (not main_pid or not main_pid.isdigit() or
                not control_pid or not control_pid.isdigit()):
            return 'unknown', None
        if int(main_pid) != 0 or int(control_pid) != 0:
            if active in ('activating', 'active', 'deactivating') and sub != 'exited':
                return 'running', None
            return 'unknown', None
        if active in ('activating', 'active', 'deactivating') and sub != 'exited':
            return 'running', None
        if active == 'active' and sub == 'exited' and code in ('1', 'exited') and status and status.isdigit():
            return 'exited', int(status)
        if active == 'inactive' and sub in ('dead', 'exited') and code in ('1', 'exited') and status and status.isdigit():
            return 'exited', int(status)
        if active == 'failed' and sub in ('failed', 'dead') and code in ('1', 'exited') and status and status.isdigit():
            return 'exited', int(status)
        return 'unknown', None

    @staticmethod
    def _backend_maintenance_exit_error(stderr_path):
        """Normalize a Go worker error while preserving its exact receipt binding."""
        try:
            with open(stderr_path, 'r') as stream:
                value = json.load(stream)
            raw = value.get('error') if isinstance(value, dict) else None
            if not isinstance(raw, STRING_TYPES):
                return 'BACKEND_MAINTENANCE_EXECUTOR_FAILED', None, None
            parts = raw.split(': ', 1)
            code = parts[0]
            if not re.match(r'^[A-Z][A-Z0-9_]{2,127}$', code):
                return 'BACKEND_MAINTENANCE_EXECUTOR_FAILED', None, raw
            detail = None
            if len(parts) == 2 and re.match(r'^[A-Z][A-Z0-9_]{2,127}$', parts[1]):
                detail = parts[1]
            return code, detail, raw
        except (IOError, OSError, ValueError, TypeError):
            return 'BACKEND_MAINTENANCE_EXECUTOR_FAILED', None, None

    def _continue_cold_backend_prepare(self, command, prior):
        """Explicit reconcile continuation after the one recorded SIGTERM attempt."""
        try:
            lock = self._acquire_host_control_lock()
        except (IOError, OSError):
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                             'OPERATION_CONCURRENT')
        try:
            current = self._load_operation(command)
            progress = (current.get('maintenanceProgress') if isinstance(current, dict) else None)
            stop = progress.get('controllerStop') if isinstance(progress, dict) else None
            if (current != prior or current.get('action') != 'prepareWritebackBackend' or
                    current.get('stage') != 'UNKNOWN' or
                    current.get('hostUuid') != self._load_host_uuid() or
                    current.get('bootId') != self._current_boot_id() or
                    current.get('requestHash') != self._operation_hash(command) or
                    not isinstance(stop, dict) or stop.get('attempted') is not True or
                    stop.get('completed') is not True or
                    stop.get('continuationReady') is not True or
                    stop.get('workerLaunchAttempted') is not False or
                    stop.get('requestHash') != current.get('requestHash') or
                    stop.get('hostUuid') != current.get('hostUuid') or
                    stop.get('bootId') != current.get('bootId') or
                    not isinstance(stop.get('identity'), dict) or
                    not isinstance(stop.get('request'), dict)):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'COLD_CONTROLLER_STOP_INTENT_INVALID')
            intent_path = current.get('maintenanceIntentPath')
            if (not isinstance(intent_path, STRING_TYPES) or os.path.lexists(intent_path)):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'COLD_CONTROLLER_STOP_CONTINUATION_UNSAFE')
            identity = stop['identity']
            if (identity.get('bootId') != self._current_boot_id() or
                    identity.get('unit') != self.MANAGED_ZRAM_UNIT or
                    identity.get('killMode') != 'process' or identity.get('restart') != 'no' or
                    self._controller_process_start_time(identity.get('pid')) is not None or
                    self._maintenance_service_state() != 'inactive'):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'COLD_CONTROLLER_STOP_UNRESOLVED')
            # The stopped daemon's Unix socket is intentionally unavailable.
            # Reuse only the exact native snapshot freshly checked immediately
            # before the durably-bound SIGTERM. Its timestamps are evidence of
            # that prior check, not a new observation; independently re-check
            # local no-pool/sysfs/history and the candidate after stop.
            native = stop.get('nativeState')
            checked_at = stop.get('nativeStateCheckedAt')
            if (not self._first_use_state_safe(native, observation_time=checked_at) or
                    not self._first_use_no_pool_verified(command)):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'COLD_BACKEND_FIRST_USE_NOT_PROVEN')
            with open(self.zram_config_path, 'rb') as stream:
                config_bytes = stream.read()
            if hashlib.sha256(config_bytes).hexdigest() != identity.get('sourceConfigSha256'):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'COLD_BACKEND_CONFIG_CHANGED')
            inventory = self._fresh_backend_maintenance_inventory(
                current['hostUuid'], command=command)
            rebuilt = self._backend_preparation_request(command, inventory)
            saved = dict(stop['request'])
            if saved != rebuilt:
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'COLD_BACKEND_CANDIDATE_CHANGED')
            directory, paths = self._maintenance_intent_paths(command['operationUuid'])
            if any(os.path.lexists(path) for path in paths.values()):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'OPERATION_JOURNAL_UNAVAILABLE')
            self._atomic_json(paths['requestPath'], rebuilt)
            intent = {'schema': 1, 'operationUuid': command['operationUuid'],
                      'hostUuid': current['hostUuid'], 'bootId': current['bootId'],
                      'requestHash': current['requestHash'],
                      'unit': self._maintenance_systemd_unit(command['operationUuid']),
                      'requestPath': paths['requestPath'], 'receiptPath': paths['receiptPath'],
                      'stderrPath': paths['stderrPath'], 'configPath': self.drain_config,
                      'controlOperationUuid': self._get_active_control(),
                      'workerLaunchAttempted': True}
            self._atomic_json(paths['intentPath'], intent)
            stop = dict(stop, workerLaunchAttempted=True, completed=True)
            progress = dict(progress, controllerStop=stop)
            pending = self._maintenance_result(command, 'Draining', 'WORKER_STARTING')
            if not self._persist_maintenance_progress(
                    command['operationUuid'], 'PREPARING', pending, progress):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'OPERATION_JOURNAL_UNAVAILABLE')
            subprocess.check_call([
                'systemd-run', '--unit=%s' % intent['unit'], '--no-block',
                '--property=UMask=0077', '--property=RemainAfterExit=yes',
                '--property=TimeoutStartSec=infinity',
                '--property=StandardInput=file:%s' % paths['requestPath'],
                '--property=StandardOutput=file:%s' % paths['receiptPath'],
                '--property=StandardError=file:%s' % paths['stderrPath'],
                self.drain_binary, '--config', self.drain_config,
                '--prepare-backend-maintenance'])
            result = self._maintenance_result(command, 'Draining', 'EXECUTOR_RUNNING')
            self._update_operation_record(command['operationUuid'], 'DRAINING', result)
            return result
        except Exception as exc:
            logger.warn('cold backend prepare continuation is uncertain: %s', exc)
            result = self._maintenance_result(
                command, 'Unknown', 'UNKNOWN', 'BACKEND_MAINTENANCE_EXECUTOR_UNKNOWN')
            self._update_operation_record(command['operationUuid'], 'UNKNOWN', result)
            return result
        finally:
            self._release_operation(lock)

    def _restore_cold_controller_after_prepare_failure(
            self, command, current, request, receipt):
        """Restore only the same cold controller after a proven failed prepare."""
        reason = receipt.get('reason') or 'BACKEND_MAINTENANCE_PREPARE_FAILED'
        failed = self._maintenance_result(
            command, 'Failed', 'FAILED_REQUIRES_REVIEW', reason, receipt)
        progress = current.get('maintenanceProgress')
        stop = progress.get('controllerStop') if isinstance(progress, dict) else None
        identity = stop.get('identity') if isinstance(stop, dict) else None
        if (not isinstance(progress, dict) or not isinstance(stop, dict) or
                current.get('action') != 'prepareWritebackBackend' or
                current.get('hostUuid') != self._load_host_uuid() or
                current.get('bootId') != self._current_boot_id() or
                current.get('requestHash') != self._operation_hash(command) or
                stop.get('attempted') is not True or stop.get('completed') is not True or
                stop.get('continuationReady') is not True or
                stop.get('workerLaunchAttempted') is not True or
                stop.get('requestHash') != current.get('requestHash') or
                stop.get('hostUuid') != current.get('hostUuid') or
                stop.get('bootId') != current.get('bootId') or
                not isinstance(identity, dict) or
                identity.get('bootId') != self._current_boot_id() or
                identity.get('unit') != self.MANAGED_ZRAM_UNIT or
                identity.get('killMode') != 'process' or identity.get('restart') != 'no' or
                not self._maintenance_receipt_matches_request(
                    receipt, request, self._current_boot_id()) or
                receipt.get('stage') != 'FAILED_REQUIRES_REVIEW'):
            self._update_operation_record(command['operationUuid'], 'FAILED_REQUIRES_REVIEW', failed)
            return failed
        attempted = progress.get('serviceStartAttempted') is True
        if progress.get('serviceStartAttempted') not in (None, False, True):
            self._update_operation_record(command['operationUuid'], 'FAILED_REQUIRES_REVIEW', failed)
            return failed
        try:
            if (self.drain_config != self.zram_config_path or
                    os.path.islink(self.zram_config_path) or
                    os.path.islink(self.zram_config_template_path)):
                raise ValueError('COLD_BACKEND_CONFIG_PATH_CHANGED')
            with open(self.zram_config_path, 'rb') as stream:
                config_bytes = stream.read()
            with open(self.zram_config_template_path, 'rb') as stream:
                template_bytes = stream.read()
            if (hashlib.sha256(config_bytes).hexdigest() != identity.get('sourceConfigSha256') or
                    hashlib.sha256(template_bytes).hexdigest() != identity.get('templateSha256')):
                raise ValueError('COLD_BACKEND_CONFIG_CHANGED')
            config, _, _ = self._read_maintenance_config()
            if config.get('initial_efficiency_enabled') is not False:
                raise ValueError('COLD_BACKEND_POLICY_NOT_DISABLED')
            intent_path = current.get('maintenanceIntentPath')
            with open(intent_path, 'r') as stream:
                intent = json.load(stream)
            if (not isinstance(intent, dict) or
                    intent.get('operationUuid') != command.get('operationUuid') or
                    intent.get('requestHash') != current.get('requestHash') or
                    intent.get('controlOperationUuid') != self._get_active_control()):
                raise ValueError('COLD_BACKEND_CONTROL_CHANGED')
            if not self._first_use_no_pool_verified(
                    command, failed_backend_record=current,
                    failed_backend_receipt=receipt):
                raise ValueError('COLD_BACKEND_FIRST_USE_NOT_PROVEN')
        except (IOError, OSError, ValueError, TypeError):
            if attempted:
                return self._maintenance_result(
                    command, 'Unknown', 'SERVICE_START_UNRESOLVED',
                    'COLD_CONTROLLER_RESTORE_NOT_PROVEN', receipt)
            self._update_operation_record(command['operationUuid'], 'FAILED_REQUIRES_REVIEW', failed)
            return failed

        service_state = self._maintenance_service_state()
        if service_state == 'starting':
            return self._maintenance_result(
                command, 'Unknown', 'SERVICE_STARTING',
                'COLD_CONTROLLER_RESTORE_IN_PROGRESS', receipt)
        if service_state == 'inactive':
            if attempted:
                return self._maintenance_result(
                    command, 'Unknown', 'SERVICE_START_UNRESOLVED',
                    'COLD_CONTROLLER_RESTORE_UNRESOLVED', receipt)
            next_progress = dict(progress)
            next_progress.update({'serviceStartAttempted': True,
                                  'serviceUnit': self.MANAGED_ZRAM_UNIT})
            pending = self._maintenance_result(
                command, 'Unknown', 'SERVICE_START_REQUESTED',
                'COLD_CONTROLLER_RESTORE_REQUESTED', receipt)
            if not self._persist_maintenance_progress(
                    command['operationUuid'], 'UNKNOWN', pending, next_progress):
                return self._maintenance_result(
                    command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE', receipt)
            progress = next_progress
            try:
                self._bounded_command_output(
                    ['systemctl', 'start', self.MANAGED_ZRAM_UNIT], 30)
            except (IOError, OSError, RuntimeError, subprocess.CalledProcessError):
                service_state = self._maintenance_service_state()
                if service_state not in ('active', 'starting'):
                    return self._maintenance_result(
                        command, 'Unknown', 'SERVICE_START_UNRESOLVED',
                        'COLD_CONTROLLER_RESTORE_UNRESOLVED', receipt)
        elif service_state != 'active':
            if not attempted:
                self._update_operation_record(command['operationUuid'],
                                              'FAILED_REQUIRES_REVIEW', failed)
                return failed
            return self._maintenance_result(
                command, 'Unknown', 'SERVICE_STATE_UNKNOWN',
                'COLD_CONTROLLER_RESTORE_UNRESOLVED', receipt)

        service_state = self._maintenance_service_state()
        if service_state == 'starting':
            return self._maintenance_result(
                command, 'Unknown', 'SERVICE_STARTING',
                'COLD_CONTROLLER_RESTORE_IN_PROGRESS', receipt)
        if service_state != 'active':
            return self._maintenance_result(
                command, 'Unknown', 'SERVICE_START_UNRESOLVED',
                'COLD_CONTROLLER_RESTORE_UNRESOLVED', receipt)
        try:
            runtime = self._first_use_runtime_identity(template_bytes, config_bytes)
            if runtime.get('bootId') != current.get('bootId'):
                raise ValueError('COLD_CONTROLLER_RESTORE_IDENTITY_UNKNOWN')
            native = self._service_request('state', {})
            native = dict(native) if isinstance(native, dict) else native
            if isinstance(native, dict):
                native['host_cpu'] = self._service_request('host-cpu-state', {})
            if (not self._first_use_state_safe(
                    native, allow_failed_backend_maintenance=True) or
                    not self._first_use_no_pool_verified(
                        command, failed_backend_record=self._load_operation(command),
                        failed_backend_receipt=receipt)):
                raise ValueError('COLD_CONTROLLER_RESTORE_READBACK_UNKNOWN')
        except Exception:
            return self._maintenance_result(
                command, 'Unknown', 'SERVICE_READBACK_UNKNOWN',
                'COLD_CONTROLLER_RESTORE_READBACK_UNKNOWN', receipt)
        restored = dict(progress)
        restored['serviceRestored'] = True
        if not self._persist_maintenance_progress(
                command['operationUuid'], 'FAILED_REQUIRES_REVIEW', failed, restored):
            return self._maintenance_result(
                command, 'Unknown', 'UNKNOWN', 'OPERATION_JOURNAL_UNAVAILABLE', receipt)
        return failed

    def _reconcile_backend_maintenance(self, command, prior):
        command = dict(command)
        operation_uuid = command.get('operationUuid')
        command['maintenanceIntentPath'] = os.path.join(
            self.operation_dir, 'backend-maintenance', '%s.intent.json' % operation_uuid)
        if (prior.get('hostUuid') != self._load_host_uuid() or
                prior.get('bootId') != self._current_boot_id()):
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'OPERATION_BOOT_CHANGED')
        progress = prior.get('maintenanceProgress')
        stop = progress.get('controllerStop') if isinstance(progress, dict) else None
        if (prior.get('stage') == 'UNKNOWN' and isinstance(stop, dict) and
                stop.get('attempted') is True and stop.get('workerLaunchAttempted') is False):
            if stop.get('completed') is not True or stop.get('continuationReady') is not True:
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'COLD_CONTROLLER_STOP_UNRESOLVED')
            intent_path = prior.get('maintenanceIntentPath')
            if isinstance(intent_path, STRING_TYPES) and not os.path.lexists(intent_path):
                return self._continue_cold_backend_prepare(command, prior)
        intent_path = prior.get('maintenanceIntentPath')
        if (not isinstance(intent_path, STRING_TYPES) or
                intent_path != os.path.join(self.operation_dir, 'backend-maintenance',
                                            '%s.intent.json' % operation_uuid)):
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'MAINTENANCE_INTENT_INVALID')
        try:
            with open(intent_path, 'r') as stream:
                intent = json.load(stream)
            if (not isinstance(intent, dict) or intent.get('operationUuid') != operation_uuid or
                    intent.get('hostUuid') != self._load_host_uuid() or
                    intent.get('bootId') != self._current_boot_id() or
                    intent.get('requestHash') != prior.get('requestHash') or
                    intent.get('unit') != self._maintenance_systemd_unit(operation_uuid) or
                    intent.get('configPath') != self.drain_config or
                    intent.get('workerLaunchAttempted') is not True):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'MAINTENANCE_INTENT_INVALID')
            _, paths = self._maintenance_intent_paths(operation_uuid, create=False)
            if (intent.get('requestPath') != paths['requestPath'] or
                    intent.get('receiptPath') != paths['receiptPath'] or
                    intent.get('stderrPath') != paths['stderrPath']):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'MAINTENANCE_INTENT_INVALID')
            with open(paths['requestPath'], 'r') as stream:
                persisted_request = json.load(stream)
            if (not isinstance(persisted_request, dict) or
                    persisted_request.get('request_id') != operation_uuid or
                    persisted_request.get('expected_host_boot_id') != self._current_boot_id()):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'MAINTENANCE_REQUEST_INVALID')
        except (IOError, OSError, ValueError, TypeError):
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN', 'MAINTENANCE_INTENT_UNAVAILABLE')

        worker, exit_status = self._systemd_worker_exit(intent['unit'])
        if worker == 'running':
            return self._maintenance_result(command, 'Draining', 'EXECUTOR_RUNNING')
        if worker != 'exited':
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                             'BACKEND_MAINTENANCE_WORKER_STATE_UNKNOWN')
        if exit_status != 0:
            reason_code, detail, _ = self._backend_maintenance_exit_error(paths['stderrPath'])
            receipt, receipt_error = self._read_backend_maintenance_receipt()
            if (not receipt_error and
                    self._maintenance_receipt_matches_request(
                        receipt, persisted_request, self._current_boot_id()) and
                    receipt.get('stage') == 'FAILED_REQUIRES_REVIEW'):
                # A failed Go worker writes its durable failure receipt before
                # returning exit 1. Continue only the narrowly proven cold
                # controller restoration path; this does not convert failure
                # into success or replay the prepare request.
                failed = self._maintenance_result(
                    command, 'Failed', 'FAILED_REQUIRES_REVIEW', reason_code, receipt)
                if detail:
                    failed['failureDetail'] = detail
                prior_progress = prior.get('maintenanceProgress')
                restore_was_attempted = (
                    prior.get('stage') == 'UNKNOWN' and
                    prior.get('action') == 'prepareWritebackBackend' and
                    isinstance(prior_progress, dict) and
                    prior_progress.get('serviceStartAttempted') is True and
                    prior_progress.get('serviceUnit') == self.MANAGED_ZRAM_UNIT)
                if restore_was_attempted:
                    # A prior service-start attempt is deliberately query-only.
                    # Keep its UNKNOWN journal and failed Go receipt intact until
                    # the existing continuation proves the service outcome.
                    failed_prior = prior
                else:
                    if not self._update_operation_record(
                            operation_uuid, 'FAILED_REQUIRES_REVIEW', failed):
                        return self._maintenance_result(
                            command, 'Unknown', 'UNKNOWN',
                            'OPERATION_JOURNAL_UNAVAILABLE', receipt)
                    failed_prior = self._load_operation({'operationUuid': operation_uuid})
                return self._continue_backend_maintenance(
                    command, failed_prior, persisted_request, receipt)
            result = self._maintenance_result(command, 'Failed', 'FAILED_REQUIRES_REVIEW',
                                              reason_code)
            result['reasonCode'] = reason_code
            if detail:
                result['failureDetail'] = detail
            self._update_operation_record(operation_uuid, 'FAILED_REQUIRES_REVIEW', result)
            return result

        receipt, error = self._read_backend_maintenance_receipt()
        if error or not self._maintenance_receipt_matches_request(
                receipt, persisted_request, self._current_boot_id()):
            return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                             error or 'BACKEND_MAINTENANCE_RECEIPT_UNKNOWN')
        stage = receipt.get('stage')
        if stage == 'FAILED_REQUIRES_REVIEW':
            return self._continue_backend_maintenance(
                command, prior, persisted_request, receipt)
        if stage == 'AWAITING_SERVICE_READBACK':
            return self._continue_backend_maintenance(
                command, prior, persisted_request, receipt)
        if stage == 'APPLIED':
            policy_ok, policy_error = self._host_optimization_disabled()
            if not policy_ok:
                return self._maintenance_result(command, 'Unknown', 'HOST_POLICY_READBACK_UNKNOWN',
                    policy_error or 'HOST_MEMORY_OPTIMIZATION_NOT_DISABLED', receipt)
            result = self._maintenance_result(command, 'Succeeded', stage, receipt=receipt)
            self._update_operation_record(operation_uuid, stage, result)
            return result
        return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                         'BACKEND_MAINTENANCE_RECEIPT_PENDING:%s' % stage, receipt)

    def _continue_backend_maintenance(self, command, prior, request, receipt):
        """Start only the canonical disabled service, verify PREPARED, then finalize."""
        operation_uuid = command.get('operationUuid')
        try:
            lock = self._acquire_host_control_lock()
        except (IOError, OSError):
            return self._maintenance_result(command, 'Draining', 'CONTINUATION_LOCK_BUSY')
        try:
            # Re-read under the host control lock so a duplicate reconcile on
            # another worker cannot race start/finalize progress.
            latest, error = self._read_backend_maintenance_receipt()
            if error or not self._maintenance_receipt_matches_request(
                    latest, request, self._current_boot_id()):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 error or 'BACKEND_MAINTENANCE_RECEIPT_UNKNOWN')
            # The reconciler's `prior` argument is an unlocked snapshot. A
            # concurrent pass may have persisted a service-start attempt while
            # this one waited for the host lock. Reload and validate the journal
            # under the lock before deciding any terminal or non-idempotent step.
            current = self._load_operation({'operationUuid': operation_uuid})
            if (not isinstance(current, dict) or
                    current.get('operationUuid') != operation_uuid or
                    current.get('action') != 'prepareWritebackBackend' or
                    current.get('hostUuid') != self._load_host_uuid() or
                    current.get('bootId') != self._current_boot_id() or
                    not current.get('requestHash') or
                    current.get('requestHash') != prior.get('requestHash') or
                    current.get('maintenanceIntentPath') != prior.get('maintenanceIntentPath')):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'OPERATION_JOURNAL_IDENTITY_MISMATCH', latest)
            if latest.get('stage') == 'APPLIED':
                policy_ok, policy_error = self._host_optimization_disabled()
                if not policy_ok:
                    return self._maintenance_result(command, 'Unknown', 'HOST_POLICY_READBACK_UNKNOWN',
                        policy_error or 'HOST_MEMORY_OPTIMIZATION_NOT_DISABLED', latest)
                result = self._maintenance_result(command, 'Succeeded', 'APPLIED', receipt=latest)
                self._update_operation_record(operation_uuid, 'APPLIED', result)
                return result
            if latest.get('stage') == 'FAILED_REQUIRES_REVIEW':
                return self._restore_cold_controller_after_prepare_failure(
                    command, current, request, latest)
            if latest.get('stage') != 'AWAITING_SERVICE_READBACK':
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                    'BACKEND_MAINTENANCE_RECEIPT_PENDING:%s' % latest.get('stage'), latest)
            progress = current.get('maintenanceProgress')
            if not isinstance(progress, dict):
                progress = {}
            service_state = self._maintenance_service_state()
            if service_state == 'inactive':
                if progress.get('serviceStartAttempted') is True:
                    return self._maintenance_result(command, 'Unknown', 'SERVICE_START_UNRESOLVED',
                                                     'BACKEND_MAINTENANCE_SERVICE_START_UNRESOLVED', latest)
                try:
                    config, _, _ = self._read_maintenance_config()
                except (IOError, OSError, ValueError, TypeError):
                    return self._maintenance_result(command, 'Unknown', 'SERVICE_CONFIG_UNKNOWN',
                        'BACKEND_MAINTENANCE_SERVICE_CONFIG_UNKNOWN', latest)
                if config.get('initial_efficiency_enabled') is True:
                    return self._maintenance_result(command, 'Unknown', 'SERVICE_CONFIG_NOT_DISABLED',
                        'BACKEND_MAINTENANCE_INITIAL_POLICY_MUST_BE_DISABLED', latest)
                next_progress = dict(progress)
                next_progress.update({'serviceStartAttempted': True,
                                      'serviceUnit': self.MANAGED_ZRAM_UNIT})
                pending = self._maintenance_result(command, 'Draining', 'SERVICE_START_REQUESTED',
                                                   receipt=latest)
                if not self._persist_maintenance_progress(operation_uuid, 'SERVICE_START_REQUESTED',
                                                          pending, next_progress):
                    return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                     'OPERATION_JOURNAL_UNAVAILABLE', latest)
                progress = next_progress
                try:
                    self._bounded_command_output(
                        ['systemctl', 'start', self.MANAGED_ZRAM_UNIT], 30)
                except (IOError, OSError, RuntimeError, subprocess.CalledProcessError):
                    # The start command can time out after systemd accepted
                    # it. Observe before deciding; never replay while active.
                    service_state = self._maintenance_service_state()
                    if service_state not in ('active', 'starting'):
                        unknown = self._maintenance_result(command, 'Unknown', 'SERVICE_START_UNKNOWN',
                            'BACKEND_MAINTENANCE_SERVICE_START_UNKNOWN', latest)
                        self._persist_maintenance_progress(operation_uuid, 'SERVICE_START_UNKNOWN',
                                                           unknown, progress)
                        return unknown
                service_state = self._maintenance_service_state()
            if service_state == 'starting':
                pending = self._maintenance_result(command, 'Draining', 'SERVICE_STARTING', receipt=latest)
                self._persist_maintenance_progress(operation_uuid, 'SERVICE_STARTING', pending, progress)
                return pending
            if service_state != 'active':
                return self._maintenance_result(command, 'Unknown', 'SERVICE_STATE_UNKNOWN',
                    'BACKEND_MAINTENANCE_SERVICE_STATE_UNKNOWN', latest)

            ready, reason = self._verify_maintenance_service_readback(
                self._load_host_uuid(), request, latest)
            if not ready:
                pending = self._maintenance_result(command, 'Draining', 'SERVICE_READBACK_PENDING',
                                                   reason, latest)
                self._persist_maintenance_progress(operation_uuid, 'SERVICE_READBACK_PENDING',
                                                   pending, progress)
                return pending
            verified = dict(progress)
            verified.update({'serviceReadbackVerified': True,
                             'serviceUnit': self.MANAGED_ZRAM_UNIT})
            pending = self._maintenance_result(command, 'Draining', 'FINALIZE_REQUESTED', receipt=latest)
            if not self._persist_maintenance_progress(operation_uuid, 'FINALIZE_REQUESTED',
                                                      pending, verified):
                return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                 'OPERATION_JOURNAL_UNAVAILABLE', latest)
            try:
                self._service_request('backend-maintenance-finalize', {'requestId': operation_uuid})
            except Exception:
                # Finalize may have committed before transport loss. The only
                # authority is its durable receipt, never the HTTP result.
                pass
            finalized, error = self._read_backend_maintenance_receipt()
            if (not error and self._maintenance_receipt_matches_request(
                    finalized, request, self._current_boot_id()) and
                    finalized.get('stage') == 'APPLIED'):
                policy_ok, policy_error = self._host_optimization_disabled()
                if not policy_ok:
                    unknown = self._maintenance_result(command, 'Unknown', 'HOST_POLICY_READBACK_UNKNOWN',
                        policy_error or 'HOST_MEMORY_OPTIMIZATION_NOT_DISABLED', finalized)
                    self._persist_maintenance_progress(operation_uuid, 'HOST_POLICY_READBACK_UNKNOWN',
                                                       unknown, verified)
                    return unknown
                success = self._maintenance_result(command, 'Succeeded', 'APPLIED', receipt=finalized)
                if not self._persist_maintenance_progress(operation_uuid, 'APPLIED', success, verified):
                    return self._maintenance_result(command, 'Unknown', 'UNKNOWN',
                                                     'OPERATION_JOURNAL_UNAVAILABLE', finalized)
                return success
            unknown = self._maintenance_result(command, 'Unknown', 'FINALIZE_PENDING',
                error or 'BACKEND_MAINTENANCE_FINALIZE_PENDING', finalized)
            self._persist_maintenance_progress(operation_uuid, 'FINALIZE_PENDING', unknown, verified)
            return unknown
        finally:
            self._release_operation(lock)

    def _host_optimization_disabled(self):
        try:
            state = self._readonly_query('host-cpu-state', {'hostUuid': self._load_host_uuid()})
        except Exception:
            return False, 'HOST_POLICY_READBACK_UNAVAILABLE'
        if state.get('efficiency_enabled') is not False:
            return False, 'HOST_MEMORY_OPTIMIZATION_NOT_DISABLED'
        return True, None

    @kvmagent.replyerror
    def apply_request(self, req):
        return self._reply(self.apply(self._request_body(req)))

    def _is_safe_control_action(self, command):
        """Return whether this is a lifecycle-only control request.

        The management API deliberately routes pause/drain/resume through the
        same Agent endpoint as policy updates. Pause/drain stop admission;
        resume only releases a same-boot confirmed pause and does not change
        the durable KSM/ZRAM policy.
        """
        return str(command.get('action', '')).lower() in (
            'pause', 'drain', 'resume', 'release')

    def _apply_safe_control_action(self, command):
        action = str(command.get('action', '')).lower()
        command = dict(command)
        operation_lock = None
        try:
            self._operation_request(command)
            # Global/Cluster requests are expanded into per-Host tasks by MN.
            # VM participation must never reach this Host lifecycle endpoint.
            if str(command.get('scope', 'Host')).lower() not in ('host', 'cluster', 'global'):
                raise ValueError('HOST_CONTROL_SCOPE_REQUIRED')
            host_uuid = self._load_host_uuid()
            if not host_uuid or command.get('hostUuid') != host_uuid:
                raise ValueError('HOST_IDENTITY_UNKNOWN')
            journal_state, journal_record = self._operation_file_state(command['operationUuid'])
            if journal_state in ('corrupt', 'unreadable'):
                raise ValueError('OPERATION_JOURNAL_UNAVAILABLE')
            if (isinstance(journal_record, dict) and
                    journal_record.get('stage') == 'NOT_ISSUED' and
                    isinstance(journal_record.get('readback'), dict)):
                return journal_record['readback']
            if journal_state == 'present' and not isinstance(journal_record, dict):
                raise ValueError('OPERATION_JOURNAL_UNAVAILABLE')
            if action in ('resume', 'release'):
                if (command.get('expectedControlOperationUuid') != self._get_active_control() or
                        self._resume_control_record() is None):
                    raise ValueError('CONTROL_OPERATION_FENCED')
            prior, claimed = self._claim_operation(command)
            if claimed:
                operation_lock = prior
            elif prior is not None:
                return prior
            else:
                return {'success': False, 'status': 'Unknown', 'state': {},
                        'reasonCode': 'OPERATION_CONCURRENT',
                        'operationUuid': command.get('operationUuid')}
            # The optimistic resume check above is not a writer fence: a
            # newer pause/drain may have completed while acquiring the lock.
            if action in ('resume', 'release'):
                if (command.get('expectedControlOperationUuid') != self._get_active_control() or
                        self._resume_control_record() is None):
                    raise ValueError('CONTROL_OPERATION_FENCED')
            if action in ('pause', 'drain'):
                active_control = self._get_active_control()
                if active_control and command.get('expectedControlOperationUuid') != active_control:
                    raise ValueError('KSM_CONTROL_OPERATION_FENCED')
                self._validate_maintenance_control_before_effects(command)
            if not self._record_operation(command, 'PREPARING'):
                return {'success': False, 'status': 'Unknown',
                        'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': command.get('operationUuid')}
            # Do not call _apply_ksm_policy, _validate_backend_resource, or
            # discover_capabilities here.  Lifecycle operations are owned by
            # the local service and do not alter the durable configuration.
            if action in ('pause', 'resume', 'release'):
                ksm_only = self._active_ksm_only()
                ksm_lifecycle = None
                if action == 'pause':
                    ksm_lifecycle = self._control_managed_ksm('pause', command)
                lifecycle = dict(command)
                lifecycle['lifecycleAction'] = 'pause' if action == 'pause' else 'resume'
                if action in ('pause', 'resume') and ksm_only and not os.path.exists(self.socket_path):
                    result = {'status': 'Succeeded', 'state': {
                        'phase': 'PAUSED' if action == 'pause' else 'RESUMED',
                        'source': 'ksmtuned', 'ksmOnly': True}}
                else:
                    result = self._service_request('lifecycle-pause', lifecycle)
                result = self._normalize_response(result, 'lifecycle-pause', command)
                # The Go lifecycle endpoint returns LifecycleSnapshot at the
                # top level of ``state`` (paused/activeState), while MN's
                # resume CAS consumes the explicit Agent phase. Add that
                # phase only when the native snapshot proves it; preserve
                # migrationHold and the complete lifecycle snapshot.
                if result.get('success') and action in ('pause', 'resume'):
                    lifecycle = result.get('state')
                    if isinstance(lifecycle, dict) and isinstance(lifecycle.get('paused'), bool):
                        expected = action == 'pause'
                        if lifecycle.get('paused') == expected:
                            result['state'] = {
                                'phase': 'PAUSED' if expected else 'RESUMED',
                                'lifecycle': lifecycle}
                if result.get('success') and action == 'pause' and ksm_only:
                    result.setdefault('state', {})['ksmOnly'] = True
                if result.get('success') and ksm_lifecycle is not None:
                    result.setdefault('state', {})['ksmLifecycle'] = ksm_lifecycle
                if result.get('success') and action != 'pause':
                    ksm_transition = self._control_managed_ksm(action, command)
                    if ksm_transition is not None:
                        result.setdefault('state', {})['ksmLifecycle'] = ksm_transition
                    # The managed KSM transition is part of the lifecycle
                    # action. Stamp the ACK after it completes so a slower
                    # resume cannot be discarded by MN as older than a
                    # periodic state sample taken during the transition.
                    result['sampleTime'] = int(time.time() * 1000)
            else:
                # Pause admission first, then launch exactly one durable
                # stock-pool maintenance CLI.  The CLI owns all native
                # qualification/swapoff/receipt logic; the Agent never does
                # swapoff itself and never retries an unknown executor.
                lifecycle = dict(command)
                lifecycle['lifecycleAction'] = 'pause'
                paused = self._service_request('lifecycle-pause', lifecycle)
                if isinstance(paused, dict) and paused.get('success') is False:
                    result = self._normalize_response(paused, 'lifecycle-pause', command)
                else:
                    drain_state = self._prepare_stock_drain(command)
                    ksm_lifecycle = self._control_managed_ksm('pause', command)
                    drain_command = dict(command)
                    drain_command.update(drain_state)
                    start_result = self._start_stock_drain(drain_command)
                    result = {'success': True, 'status': 'Draining',
                              'state': {'phase': 'DRAINING',
                                        'poolGeneration': drain_state['poolGeneration'],
                                        'device': drain_state['device'],
                                        'receipt': start_result},
                              'operationUuid': command.get('operationUuid')}
                    if ksm_lifecycle is not None:
                        result['state']['ksmLifecycle'] = ksm_lifecycle
            if result.get('success'):
                # A pause/drain fences late control operations.  The migration hold has
                # its own generation and does not overwrite this UUID.
                self._set_active_control(command['operationUuid'])
                self._record_operation(command,
                                       'DRAINING' if action == 'drain' else 'APPLIED',
                                       result)
            else:
                self._record_operation(command, 'UNKNOWN', result)
            return result
        except ValueError as exc:
            self._record_operation(command, 'REJECTED', {'reason': str(exc)})
            return {'success': False, 'status': 'Failed',
                    'state': {'phase': 'FAILED'}, 'reason': str(exc),
                    'reasonCode': 'INVALID_CONTROL_ACTION',
                    'operationUuid': command.get('operationUuid')}
        except Exception as exc:
            self._record_operation(command, 'UNKNOWN', {'reason': str(exc)})
            logger.warn('memory optimisation control action is unknown: %s', exc)
            return {'success': False, 'status': 'Unknown',
                    'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'MEMORY_RESULT_UNKNOWN',
                    'operationUuid': command.get('operationUuid')}
        finally:
            self._release_operation(operation_lock)

    def _validate_maintenance_control_before_effects(self, command):
        """Validate the one recovery control that can safely precede maintenance."""
        if os.path.islink(self.active_control_path):
            raise ValueError('KSM_CONTROL_OPERATION_UNKNOWN')
        active_uuid = self._get_active_control()
        if not active_uuid:
            return
        path = self._operation_path(active_uuid)
        if os.path.islink(path) or os.path.realpath(path) != path:
            raise ValueError('KSM_CONTROL_OPERATION_UNKNOWN')
        kind, record = self._operation_file_state(active_uuid)
        if (not isinstance(record, dict) or record.get('operationUuid') != active_uuid or
                kind != 'present' or
                record.get('stage') != 'APPLIED' or
                record.get('hostUuid') != self._load_host_uuid() or
                record.get('bootId') != self._current_boot_id() or
                record.get('action') not in (None, 'apply', 'recoverUncertain')):
            raise ValueError('KSM_CONTROL_OPERATION_UNKNOWN')
        if record.get('action') == 'recoverUncertain':
            self._validate_final_cpu_no_ksm_control(command, record, active_uuid)

    def _validate_final_cpu_no_ksm_control(self, command, recovery, active_uuid):
        """Allow ordinary maintenance after only a fully proven no-KSM CPU recovery."""
        intent = recovery.get('recoveryIntent') if isinstance(recovery, dict) else None
        if isinstance(intent, dict) and intent.get('kind') == 'partialServiceApply':
            self._validate_partial_service_control(command, recovery, active_uuid)
            return
        unknown = 'FINAL_CPU_RECOVERY_CONTROL_UNKNOWN'
        try:
            intent = recovery.get('recoveryIntent')
            result = recovery.get('readback')
            state = result.get('state') if isinstance(result, dict) else None
            proof = state.get('recoveryProof') if isinstance(state, dict) else None
            receipt = intent.get('cpuReceipt') if isinstance(intent, dict) else None
            boot = self._current_boot_id()
            host = self._load_host_uuid()
            original_uuid = intent.get('unresolvedOperationUuid') if isinstance(intent, dict) else None
            anchor_uuid = intent.get('priorActiveControl') if isinstance(intent, dict) else None
            request_hash = recovery.get('requestHash')
            if (not isinstance(intent, dict) or not isinstance(result, dict) or
                    not isinstance(state, dict) or not isinstance(proof, dict) or
                    not isinstance(receipt, dict)):
                raise ValueError(unknown)
            if (recovery.get('operationUuid') != active_uuid or
                    recovery.get('action') != 'recoverUncertain' or recovery.get('stage') != 'APPLIED' or
                    recovery.get('scope') != 'Host' or recovery.get('hostUuid') != host or
                    recovery.get('resourceUuid') not in (None, host) or recovery.get('bootId') != boot or
                    not isinstance(request_hash, STRING_TYPES) or
                    not re.match(r'^[0-9a-f]{64}$', request_hash) or
                    recovery.get('policy') != {} or recovery.get('policyHash') != self._policy_digest({}) or
                    command.get('expectedControlOperationUuid') != active_uuid or
                    intent.get('kind') != 'finalCpuGate' or intent.get('hostUuid') != host or
                    intent.get('expectedBootId') != boot or intent.get('recoveryOperationUuid') != active_uuid or
                    not self._valid_identifier(original_uuid) or not self._valid_identifier(anchor_uuid) or
                    anchor_uuid == original_uuid or intent.get('priorActiveControl') != anchor_uuid or
                    not re.match(r'^[0-9a-f]{64}$', intent.get('expectedPoolGeneration', '')) or
                    not re.match(r'^[0-9a-f]{64}$', intent.get('originalJournalHash', '')) or
                    not re.match(r'^[0-9a-f]{64}$', intent.get('originalRequestHash', '')) or
                    result.get('success') is not True or result.get('status') != 'Succeeded' or
                    result.get('operationUuid') != active_uuid or result.get('bootId') != boot or
                    state.get('phase') != 'POLICY_RECOVERED' or state.get('bootId') != boot or
                    state.get('lastConfirmedOperationUuid') != active_uuid or
                    state.get('cpuReceipt') != receipt or
                    type(proof.get('schemaVersion')) is not int or proof.get('schemaVersion') != 1 or
                    proof.get('hostUuid') != host or proof.get('bootId') != boot or
                    proof.get('recoveryOperationUuid') != active_uuid or
                    proof.get('unresolvedOperationUuid') != original_uuid or
                    proof.get('expectedPoolGeneration') != intent.get('expectedPoolGeneration') or
                    proof.get('originalRequestHash') != intent.get('originalRequestHash') or
                    proof.get('originalOutcome') != 'Unknown' or proof.get('finalCpuRestored') is not True):
                raise ValueError(unknown)
            recovery_path = self._operation_path(active_uuid)
            original_path = self._operation_path(original_uuid)
            anchor_path = self._operation_path(anchor_uuid)
            if any(os.path.islink(path) or os.path.realpath(path) != path
                   for path in (recovery_path, original_path, anchor_path)):
                raise ValueError(unknown)
            recovery_kind, current_recovery = self._operation_file_state(active_uuid)
            original_kind, original = self._operation_file_state(original_uuid)
            anchor_kind, anchor = self._operation_file_state(anchor_uuid)
            if (recovery_kind != 'present' or current_recovery != recovery or
                    original_kind != 'present' or not isinstance(original, dict) or
                    anchor_kind != 'present' or not isinstance(anchor, dict) or
                    original.get('operationUuid') != original_uuid or original.get('stage') != 'UNKNOWN' or
                    original.get('action') != 'apply' or original.get('scope') != 'Host' or
                    original.get('hostUuid') != host or original.get('bootId') != boot or
                    not isinstance(original.get('requestHash'), STRING_TYPES) or
                    not re.match(r'^[0-9a-f]{64}$', original.get('requestHash', '')) or
                    original.get('requestHash') != intent.get('originalRequestHash') or
                    self._operation_hash(original) != intent.get('originalJournalHash') or
                    original.get('desiredRevision') != intent.get('desiredRevision') or
                    original.get('policyHash') != self._policy_digest(original.get('policy') or {}) or
                    anchor.get('operationUuid') != anchor_uuid or anchor.get('stage') != 'APPLIED' or
                    anchor.get('action') not in (None, 'apply') or anchor.get('scope') != 'Host' or
                    anchor.get('hostUuid') != host or anchor.get('bootId') != boot or
                    anchor.get('policyHash') != self._policy_digest(anchor.get('policy') or {}) or
                    type(anchor.get('desiredRevision')) is not int or
                    type(original.get('desiredRevision')) is not int or
                    anchor.get('desiredRevision') >= original.get('desiredRevision') or
                    (anchor.get('readback') or {}).get('success') is not True or
                    (anchor.get('readback') or {}).get('status') != 'Succeeded' or
                    original.get('policyMode') != 'delta'):
                raise ValueError(unknown)
            original_policy = original.get('policy')
            anchor_policy = anchor.get('policy')
            original_readback = original.get('readback') or {}
            anchor_readback = anchor.get('readback') or {}
            original_state = original_readback.get('state') or {}
            anchor_state = anchor_readback.get('state') or {}
            original_evidence = original.get('applyEvidence') or {}
            anchor_evidence = anchor.get('applyEvidence') or {}
            if (not isinstance(original_policy, dict) or original_policy.get('ksm') or
                    not isinstance(anchor_policy, dict) or anchor_policy.get('ksm') or
                    not isinstance(original_readback, dict) or original_readback.get('ksmReadback') is not None or
                    not isinstance(original_state, dict) or original_state.get('ksmReadback') is not None or
                    not isinstance(anchor_readback, dict) or anchor_readback.get('ksmReadback') is not None or
                    not isinstance(anchor_state, dict) or anchor_state.get('ksmReadback') is not None or
                    not isinstance(original_evidence, dict) or original_evidence.get('ksmReadback') is not None or
                    not isinstance(anchor_evidence, dict) or anchor_evidence.get('ksmReadback') is not None or
                    any(key.lower().startswith('ksm') for key in (original_evidence.get('state') or {}).get('sections', {})) or
                    any(key.lower().startswith('ksm') for key in (anchor_evidence.get('state') or {}).get('sections', {}))):
                raise ValueError(unknown)
            cpu_readback = state.get('cpuReadback')
            target = intent.get('cpuTarget')
            original_revision = original.get('desiredRevision')
            if (proof.get('originalPolicyHash') != original.get('policyHash') or
                    proof.get('originalDesiredRevision') != original_revision or
                    recovery.get('desiredRevision') != original_revision or
                    result.get('appliedRevision') != original_revision or
                    state.get('lastConfirmedAppliedRevision') != original_revision or
                    receipt.get('request_id') != self._derived_service_request_id(original_uuid, 'cpu') or
                    type(intent.get('cpuExpectedRevision')) is not int or
                    receipt.get('revision') != intent.get('cpuExpectedRevision') + 1 or
                    not isinstance(cpu_readback, dict) or
                    not isinstance(target, dict) or
                    set(target) != set(('efficiency_enabled', 'idle_cpu_threshold_percent', 'idle_duration_seconds'))):
                raise ValueError(unknown)
            receipt = self._strict_service_success('host-cpu', receipt)
            cpu_readback = self._strict_service_success('host-cpu-state', cpu_readback)
            if (cpu_readback['revision'] != receipt.get('revision') or
                    not self._strict_service_match(cpu_readback, target) or
                    not self._strict_service_match(receipt, target)):
                raise ValueError(unknown)
        except Exception:
            raise ValueError(unknown)

    def _validate_partial_service_control(self, command, recovery, active_uuid):
        """Keep a completed partial KSM recovery fenced to its original receipts."""
        unknown = 'PARTIAL_SERVICE_RECOVERY_CONTROL_UNKNOWN'
        try:
            intent = recovery.get('recoveryIntent')
            result = recovery.get('readback')
            state = result.get('state') if isinstance(result, dict) else None
            proof = state.get('recoveryProof') if isinstance(state, dict) else None
            host = self._load_host_uuid()
            boot = self._current_boot_id()
            old_uuid = intent.get('unresolvedOperationUuid') if isinstance(intent, dict) else None
            anchor_uuid = intent.get('anchorOperationUuid') if isinstance(intent, dict) else None
            if (not isinstance(intent, dict) or not isinstance(result, dict) or
                    not isinstance(state, dict) or not isinstance(proof, dict) or
                    recovery.get('operationUuid') != active_uuid or
                    recovery.get('action') != 'recoverUncertain' or recovery.get('stage') != 'APPLIED' or
                    recovery.get('scope') != 'Host' or recovery.get('hostUuid') != host or
                    recovery.get('bootId') != boot or recovery.get('policy') != {} or
                    recovery.get('policyHash') != self._policy_digest({}) or
                    command.get('expectedControlOperationUuid') != active_uuid or
                    intent.get('kind') != 'partialServiceApply' or intent.get('hostUuid') != host or
                    intent.get('expectedBootId') != boot or intent.get('recoveryOperationUuid') != active_uuid or
                    intent.get('priorActiveControl') != anchor_uuid or
                    not self._valid_identifier(old_uuid) or not self._valid_identifier(anchor_uuid) or
                    state.get('phase') != 'POLICY_RECOVERED' or state.get('bootId') != boot or
                    state.get('lastConfirmedOperationUuid') != active_uuid or
                    result.get('success') is not True or result.get('status') != 'Succeeded' or
                    result.get('operationUuid') != active_uuid or result.get('bootId') != boot or
                    type(proof.get('schemaVersion')) is not int or proof.get('schemaVersion') != 1 or
                    proof.get('kind') != 'partialServiceApply' or proof.get('hostUuid') != host or
                    proof.get('bootId') != boot or proof.get('recoveryOperationUuid') != active_uuid or
                    proof.get('unresolvedOperationUuid') != old_uuid or
                    proof.get('anchorOperationUuid') != anchor_uuid or
                    proof.get('originalOutcome') != 'Unknown' or proof.get('finalCpuRestored') is not True or
                    proof.get('originalJournalHash') != intent.get('originalJournalHash') or
                    proof.get('originalRequestHash') != intent.get('originalRequestHash') or
                    proof.get('originalPolicyHash') != intent.get('originalPolicyHash') or
                    proof.get('originalKsmReadback') != intent.get('originalKsmReadback') or
                    proof.get('anchorJournalHash') != intent.get('anchorJournalHash') or
                    proof.get('tuningPayloadSha256') != intent.get('tuningPayloadSha256') or
                    proof.get('tuningCommand') != self._service_payload(
                        'apply', intent.get('tuningCommand') or {}) or
                    proof.get('tuningBefore') != intent.get('tuningBefore') or
                    proof.get('tuningRequestId') != (intent.get('tuningCommand') or {}).get('operationUuid') or
                    proof.get('tuningExpectedRevision') != (intent.get('tuningCommand') or {}).get('expectedRevision') or
                    proof.get('tuningRevision') != (intent.get('tuningReceipt') or {}).get('revision') or
                    proof.get('tuningReceipt') != intent.get('tuningReceipt') or
                    proof.get('tuningReadback') != intent.get('tuningReadback') or
                    proof.get('cpuGuard') != intent.get('cpuGuard') or
                    proof.get('cpuGuardReadback') != intent.get('cpuGuardReadback') or
                    proof.get('cpuExpectedRevision') != (intent.get('cpuGuard') or {}).get('revision') or
                    state.get('cpuReceipt') != intent.get('cpuReceipt') or
                    not isinstance(intent.get('cpuReceipt'), dict)):
                raise ValueError(unknown)
            original_path = self._operation_path(old_uuid)
            anchor_path = self._operation_path(anchor_uuid)
            recovery_path = self._operation_path(active_uuid)
            if any(os.path.islink(path) or os.path.realpath(path) != path
                   for path in (original_path, anchor_path, recovery_path)):
                raise ValueError(unknown)
            recovery_kind, stored_recovery = self._operation_file_state(active_uuid)
            original_kind, original = self._operation_file_state(old_uuid)
            anchor_kind, anchor = self._operation_file_state(anchor_uuid)
            if (recovery_kind != 'present' or stored_recovery != recovery or
                    original_kind != 'present' or anchor_kind != 'present' or
                    not isinstance(original, dict) or not isinstance(anchor, dict) or
                    self._operation_hash(original) != intent.get('originalJournalHash') or
                    self._operation_hash(anchor) != intent.get('anchorJournalHash') or
                    original.get('operationUuid') != old_uuid or original.get('stage') != 'UNKNOWN' or
                    original.get('action') != 'apply' or original.get('scope') != 'Host' or
                    original.get('hostUuid') != host or original.get('bootId') != boot or
                    original.get('requestHash') != intent.get('originalRequestHash') or
                    original.get('policyHash') != intent.get('originalPolicyHash') or
                    original.get('desiredRevision') != intent.get('desiredRevision') or
                    original.get('policyHash') != self._policy_digest(original.get('policy') or {}) or
                    proof.get('originalPolicyHash') != original.get('policyHash') or
                    proof.get('originalDesiredRevision') != original.get('desiredRevision') or
                    anchor.get('operationUuid') != anchor_uuid or anchor.get('stage') != 'APPLIED' or
                    anchor.get('action') != 'apply' or anchor.get('scope') != 'Host' or
                    anchor.get('hostUuid') != host or anchor.get('bootId') != boot or
                    anchor.get('requestHash') != intent.get('anchorRequestHash') or
                    anchor.get('policyHash') != intent.get('anchorPolicyHash') or
                    anchor.get('desiredRevision') != intent.get('anchorDesiredRevision') or
                    anchor.get('policyHash') != self._policy_digest(anchor.get('policy') or {})):
                raise ValueError(unknown)
            original_policy = original.get('policy') or {}
            original_ksm = original_policy.get('ksm')
            original_writeback = original_policy.get('writeback')
            original_evidence = original.get('applyEvidence')
            original_readback = original.get('readback')
            original_state = (original_evidence.get('state')
                              if isinstance(original_evidence, dict) else None)
            original_sections = (original_state.get('sections')
                                 if isinstance(original_state, dict) else None)
            if (not isinstance(original_evidence, dict) or not isinstance(original_readback, dict) or
                    set(original_policy) != {'schemaVersion', 'ksm', 'writeback'} or
                    type(original_policy.get('schemaVersion')) is not int or
                    original_policy.get('schemaVersion') != 1 or
                    not isinstance(original_ksm, dict) or
                    set(original_ksm) != {'enabled', 'zeroPagesEnabled'} or
                    original_ksm.get('enabled') is not True or
                    original_ksm.get('zeroPagesEnabled') is not True or
                    not isinstance(original_writeback, dict) or
                    original_writeback != {'enabled': False} or
                    not self._strict_service_match(original_evidence, original_readback) or
                    original_evidence.get('success') is not False or
                    original_evidence.get('status') != 'Unknown' or
                    original_evidence.get('reason') != 'SERVICE_APPLY_FAILED:TUNING_REQUIRES_QUIESCENT_EXECUTOR' or
                    original_state.get('lastStep') != 'tuning_apply_and_vm_scope_commit' or
                    original_state.get('sequence') != ['cpu_guard_written', 'cpu_guard_verified_off'] or
                    original_state.get('notAttempted') != ['remainingPolicyWrites', 'finalCpuGate'] or
                    not isinstance(original_sections, dict) or
                    set(original_sections) != {'cpuBefore', 'cpuGuard', 'cpuGuardReadback'} or
                    original_evidence.get('ksmReadback') != intent.get('originalKsmReadback') or
                    original_sections.get('cpuBefore') != intent.get('cpuBefore') or
                    original_sections.get('cpuGuard') != intent.get('cpuGuard') or
                    original_sections.get('cpuGuardReadback') != intent.get('cpuGuardReadback')):
                raise ValueError(unknown)
            anchor_policy = anchor.get('policy') or {}
            anchor_ksm = anchor_policy.get('ksm') or {}
            anchor_wb = anchor_policy.get('writeback') or {}
            if (type(original.get('desiredRevision')) is not int or
                    type(anchor.get('desiredRevision')) is not int or
                    anchor.get('desiredRevision') >= original.get('desiredRevision') or
                    anchor_ksm.get('enabled') is not False or
                    anchor_ksm.get('zeroPagesEnabled') is not False or
                    anchor_wb.get('enabled') is not True or
                    not self._valid_identifier(anchor_wb.get('backendResourceUuid')) or
                    type(anchor_wb.get('backendCapacityBytes')) is not int or
                    anchor_wb.get('backendCapacityBytes') <= 0):
                raise ValueError(unknown)
            ksm_ack = intent.get('originalKsmReadback')
            ack_policy = self._ksm_proof_policy(ksm_ack, original.get('desiredRevision'))
            if (not isinstance(original_ksm, dict) or not isinstance(ack_policy, dict) or
                    any(key not in ack_policy or
                        not self._strict_service_match(ack_policy[key], value)
                        for key, value in original_ksm.items()) or
                    not self._ksm_proof_matches(ksm_ack, original.get('desiredRevision'))):
                raise ValueError(unknown)
            tuning_command = intent.get('tuningCommand')
            tuning_receipt = intent.get('tuningReceipt')
            tuning_readback = intent.get('tuningReadback')
            tuning_before = intent.get('tuningBefore')
            if (not isinstance(tuning_command, dict) or not isinstance(tuning_receipt, dict) or
                    not isinstance(tuning_readback, dict) or not isinstance(tuning_before, dict) or
                    tuning_command.get('operationUuid') != self._derived_service_request_id(old_uuid, 'tuning') or
                    tuning_command.get('expectedRevision') != tuning_before.get('revision') or
                    tuning_receipt.get('agent_request_id') != tuning_command.get('operationUuid') or
                    tuning_receipt.get('agent_expected_revision') != tuning_command.get('expectedRevision') or
                    tuning_receipt.get('_http_status') != 200 or
                    tuning_receipt.get('revision') != tuning_readback.get('revision') or
                    tuning_receipt.get('revision') != tuning_command.get('expectedRevision') + 1 or
                    not self._strict_service_match(tuning_receipt.get('settings'),
                                                   tuning_readback.get('settings')) or
                    not self._strict_service_match(tuning_command.get('nativeSettings'),
                                                   tuning_receipt.get('settings'))):
                raise ValueError(unknown)
            tuning_wire = self._service_payload('apply', tuning_command)
            if (proof.get('tuningPayloadSha256') != hashlib.sha256(json.dumps(
                    tuning_wire, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest() or
                    proof.get('tuningCommand') != tuning_wire):
                raise ValueError(unknown)
            current_tuning = self._strict_service_success(
                'tuning-state', self._service_request('tuning-state', {}))
            current_cpu = self._strict_service_success(
                'host-cpu-state', self._service_request('host-cpu-state', {}))
            live = self._service_request('monitor-state', {})
            cpu_receipt = self._strict_service_success('host-cpu', intent.get('cpuReceipt'))
            cpu_target = {'efficiency_enabled': cpu_receipt.get('agent_desired_enabled'),
                          'idle_cpu_threshold_percent': cpu_receipt.get('agent_desired_threshold_percent'),
                          'idle_duration_seconds': cpu_receipt.get('agent_desired_duration_seconds')}
            cpu_before = intent.get('cpuBefore')
            cpu_guard = intent.get('cpuGuard')
            if (current_tuning.get('revision') != tuning_receipt.get('revision') or
                    not self._strict_service_match(current_tuning.get('settings'),
                                                   tuning_receipt.get('settings')) or
                    not isinstance(cpu_before, dict) or not isinstance(cpu_guard, dict) or
                    cpu_receipt.get('request_id') != self._derived_service_request_id(old_uuid, 'cpu') or
                    cpu_receipt.get('agent_expected_revision') != cpu_guard.get('revision') or
                    cpu_receipt.get('revision') != cpu_guard.get('revision') + 1 or
                    cpu_target.get('efficiency_enabled') is not cpu_before.get('efficiency_enabled') or
                    cpu_target.get('idle_cpu_threshold_percent') != cpu_before.get('idle_cpu_threshold_percent') or
                    cpu_target.get('idle_duration_seconds') != cpu_before.get('idle_duration_seconds') or
                    current_cpu.get('revision') != cpu_receipt.get('revision') or
                    not self._strict_service_match(current_cpu, cpu_target) or
                    (state.get('cpuReadback') or {}).get('revision') != cpu_receipt.get('revision') or
                    not self._strict_service_match(state.get('cpuReadback'), cpu_target) or
                    (live.get('host_zram') or {}).get('pool_generation') != intent.get('expectedPoolGeneration') or
                    (live.get('lifecycle') or {}).get('paused') is not False or
                    (live.get('lifecycle') or {}).get('migrationHold') not in (None, {}) or
                    ('pending_operations' not in live or live.get('pending_operations') not in (None, [])) or
                    self._get_active_control() != active_uuid or
                    self._current_boot_id() != boot):
                raise ValueError(unknown)
        except Exception:
            raise ValueError(unknown)

    def _control_managed_ksm(self, action, command):
        """Pause/resume only native units proven by the fenced operation journal."""
        if action in ('pause', 'drain'):
            active_uuid = self._get_active_control()
            if not active_uuid:
                return None
            if command.get('expectedControlOperationUuid') != active_uuid:
                raise RuntimeError('KSM_CONTROL_OPERATION_FENCED')
            record = self._load_operation({'operationUuid': active_uuid})
            if (not isinstance(record, dict) or record.get('operationUuid') != active_uuid or
                    record.get('stage') != 'APPLIED' or
                    record.get('hostUuid') != self._load_host_uuid() or
                    record.get('bootId') != self._current_boot_id()):
                raise RuntimeError('KSM_CONTROL_OPERATION_UNKNOWN')
            if record.get('action') == 'recoverUncertain':
                self._validate_final_cpu_no_ksm_control(command, record, active_uuid)
                return None
            if record.get('action') not in (None, 'apply'):
                raise RuntimeError('KSM_CONTROL_OPERATION_UNKNOWN')
            policy = record.get('policy') or {}
            ksm = policy.get('ksm') if isinstance(policy, dict) else None
            if not isinstance(ksm, dict) or not ksm:
                return None
            ack = self._managed_ksm_clear_ack(require_ksm_only=False)
            if ack is None:
                return None
            self._verify_native_ksm_profile()
            active_ksm = self._native_service_state(self.KSM_UNIT, 'active')
            active_tuned = self._native_service_state(self.KSM_TUNED_UNIT, 'active')
            if active_ksm not in ('active', 'inactive') or active_tuned not in ('active', 'inactive'):
                raise RuntimeError('KSM_NATIVE_SERVICE_STATE_UNKNOWN')
            if active_tuned == 'active':
                subprocess.check_call(['systemctl', 'stop', self.KSM_TUNED_UNIT])
            if active_ksm == 'active':
                subprocess.check_call(['systemctl', 'stop', self.KSM_UNIT])
            self._write_ksm_sysfs('run', '0')
            return {'controlOperationUuid': active_uuid,
                    'runBeforePause': ack['run'],
                    'ksmWasActive': active_ksm == 'active',
                    'ksmtunedWasActive': active_tuned == 'active'}

        if action not in ('resume', 'release'):
            return None
        pause_record = self._resume_control_record()
        if not isinstance(pause_record, dict):
            return None
        pause_readback = pause_record.get('readback')
        pause_state = pause_readback.get('state') if isinstance(pause_readback, dict) else None
        previous = pause_state.get('ksmLifecycle') if isinstance(pause_state, dict) else None
        if not isinstance(previous, dict):
            return None
        prior_uuid = pause_record.get('expectedControlOperationUuid')
        if (not isinstance(prior_uuid, STRING_TYPES) or not prior_uuid or
                previous.get('controlOperationUuid') != prior_uuid or
                command.get('expectedControlOperationUuid') != pause_record.get('operationUuid')):
            raise RuntimeError('KSM_RESUME_CONTROL_IDENTITY_UNKNOWN')
        prior = self._load_operation({'operationUuid': prior_uuid})
        if (not isinstance(prior, dict) or prior.get('operationUuid') != prior_uuid or
                prior.get('stage') != 'APPLIED' or prior.get('action') not in (None, 'apply') or
                prior.get('hostUuid') != self._load_host_uuid() or
                prior.get('bootId') != self._current_boot_id() or
                pause_record.get('hostUuid') != prior.get('hostUuid') or
                pause_record.get('bootId') != prior.get('bootId')):
            raise RuntimeError('KSM_RESUME_PRIOR_OPERATION_UNKNOWN')
        prior_policy = prior.get('policy') or {}
        prior_ksm = prior_policy.get('ksm') if isinstance(prior_policy, dict) else None
        prior_result = prior.get('readback')
        prior_ack = prior_result.get('ksmReadback') if isinstance(prior_result, dict) else None
        revision = prior.get('desiredRevision')
        if (not isinstance(prior_ksm, dict) or not prior_ksm or
                self._ksm_proof_policy(prior_ack, revision) is None or
                previous.get('runBeforePause') not in ('0', '1') or
                not isinstance(previous.get('ksmWasActive'), bool) or
                not isinstance(previous.get('ksmtunedWasActive'), bool)):
            raise RuntimeError('KSM_RESUME_PRIOR_PROOF_UNKNOWN')
        self._verify_native_ksm_profile()
        current = self._read_ksm_ack()
        if current is None or current.get('run') != '0':
            raise RuntimeError('KSM_RESUME_PAUSED_READBACK_UNKNOWN')
        expected_paused = dict(prior_ack)
        expected_paused['run'] = '0'
        if current != expected_paused:
            raise RuntimeError('KSM_RESUME_CONFIG_IDENTITY_MISMATCH')
        active_ksm = self._native_service_state(self.KSM_UNIT, 'active')
        active_tuned = self._native_service_state(self.KSM_TUNED_UNIT, 'active')
        if active_ksm not in ('active', 'inactive') or active_tuned not in ('active', 'inactive'):
            raise RuntimeError('KSM_NATIVE_SERVICE_STATE_UNKNOWN')
        if not previous['ksmWasActive'] and active_ksm != 'inactive':
            raise RuntimeError('KSM_RESUME_UNEXPECTED_KSM_SERVICE')
        if not previous['ksmtunedWasActive'] and active_tuned != 'inactive':
            raise RuntimeError('KSM_RESUME_UNEXPECTED_KSMTUNED_SERVICE')
        if previous['ksmWasActive'] and active_ksm == 'inactive':
            subprocess.check_call(['systemctl', 'start', self.KSM_UNIT])
        if previous['ksmtunedWasActive'] and active_tuned == 'inactive':
            subprocess.check_call(['systemctl', 'start', self.KSM_TUNED_UNIT])
        desired_run = previous['runBeforePause']
        if self._read_ksm_sysfs('run') != desired_run:
            self._write_ksm_sysfs('run', desired_run)
        restored = self._read_ksm_ack()
        expected_restored = dict(prior_ack)
        expected_restored['run'] = desired_run
        if restored != expected_restored:
            raise RuntimeError('KSM_RESUME_READBACK_MISMATCH')
        return {'controlOperationUuid': prior_uuid,
                'runRestored': desired_run,
                'ksmResumed': previous['ksmWasActive'],
                'ksmtunedResumed': previous['ksmtunedWasActive']}

    def _start_stock_drain(self, command):
        """Stop the managed unit and start one bounded stock drain executor."""
        if not os.path.isfile(self.drain_binary) or not os.path.isfile(self.drain_config):
            raise ValueError('DRAIN_MANAGED_CONFIG_UNAVAILABLE')
        if not os.path.isdir(self.drain_dir):
            os.makedirs(self.drain_dir)
        output_path = os.path.join(self.drain_dir, '%s.receipt.json' % command['operationUuid'])
        error_path = os.path.join(self.drain_dir, '%s.stderr' % command['operationUuid'])
        unit = 'zstack-memory-drain-%s' % command['operationUuid']
        intent_path = os.path.join(self.operation_dir,
                                   '%s.drain-intent.json' % command['operationUuid'])
        intent = {'operationUuid': command['operationUuid'], 'unit': unit,
                  'receiptPath': output_path, 'stderrPath': error_path,
                  'bootId': self._current_boot_id(),
                  'poolGeneration': command.get('poolGeneration'),
                  'device': command.get('device'), 'configPath': self.drain_config}
        owner_proof = command.get('backendOwnerProof')
        if isinstance(owner_proof, dict):
            if (owner_proof.get('hostUuid') != command.get('hostUuid') or
                    owner_proof.get('controlOperationUuid') != command.get('operationUuid') or
                    owner_proof.get('bootId') != intent['bootId'] or
                    owner_proof.get('poolGeneration') != intent['poolGeneration'] or
                    owner_proof.get('zramDevice') != intent['device']):
                raise ValueError('DRAIN_BACKEND_OWNER_PROOF_MISMATCH')
            intent['backendOwnerProof'] = owner_proof
        if not intent['bootId'] or not intent['poolGeneration'] or not intent['device']:
            raise ValueError('DRAIN_INTENT_INCOMPLETE')
        fd, temp_intent = tempfile.mkstemp(prefix='.drain-intent-', dir=self.operation_dir)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(intent, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temp_intent, intent_path)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            if os.path.exists(temp_intent):
                os.unlink(temp_intent)
            raise
        # Stop only the fixed, feature-owned unit.  Do not stop arbitrary
        # services or restore the unit automatically after a failure.
        subprocess.check_call(['systemctl', 'stop', self.drain_unit])
        subprocess.check_call([
            'systemd-run', '--unit=%s' % unit, '--no-block',
            '--property=UMask=0077', '--property=RemainAfterExit=yes',
            '--property=TimeoutStartSec=infinity',
            '--property=StandardOutput=file:%s' % output_path,
            '--property=StandardError=file:%s' % error_path,
            self.drain_binary, '--config', self.drain_config, '--drain'])
        return {'unit': unit, 'receiptPath': output_path,
                'stderrPath': error_path, 'configPath': self.drain_config,
                'serviceUnit': self.drain_unit}

    def _capture_stock_drain_backend_owner(self, command, pool_generation, device):
        """Pin an already-owned active backend before the drain stops its reader."""
        host_uuid = command.get('hostUuid')
        boot_id = self._current_boot_id()
        try:
            status = self._readonly_query('backend-state', {'hostUuid': host_uuid})
            detail = self._readonly_query('backend-view', {'hostUuid': host_uuid})
            status_pool = status.get('host_zram') or status.get('pool') or {}
            if (status_pool.get('pool_generation') != pool_generation or
                    status_pool.get('device') != device):
                return None
            resource = status.get('backend_resource')
            if (not isinstance(resource, dict) or resource.get('state') != 'ACTIVE' or
                    resource.get('active') is not True or
                    detail.get('claimed') is not True or
                    detail.get('identity_qualified') is not True or
                    detail.get('ownership_generation') != resource.get('resource_uuid')):
                return None
            backend = dict(detail)
            backend['backend_resource'] = resource
            configured = detail.get('configured') or {}
            inventory = probe_writeback_backends(host_uuid, backend, configured)
            candidates = inventory.get('candidates') if isinstance(inventory, dict) else None
            active = [candidate for candidate in candidates or []
                      if isinstance(candidate, dict) and candidate.get('type') == 'block' and
                      candidate.get('state') == 'ACTIVE' and candidate.get('active') is True and
                      candidate.get('eligible') is True and
                      candidate.get('writebackReady', candidate.get('writeback_ready')) is True]
            if len(active) != 1:
                return None
            candidate = active[0]
            identity = candidate.get('stableIdentity', candidate.get('stable_identity'))
            resource_uuid = resource.get('resource_uuid')
            fingerprint = resource.get('fingerprint')
            if (inventory.get('hostUuid', inventory.get('host_uuid')) != host_uuid or
                    inventory.get('bootId', inventory.get('boot_id')) != boot_id or
                    candidate.get('resourceUuid', candidate.get('resource_uuid')) != resource_uuid or
                    candidate.get('fingerprint') != fingerprint or
                    candidate.get('identity') != fingerprint or
                    not isinstance(identity, dict) or
                    identity.get('bootId', identity.get('boot_id')) != boot_id or
                    identity.get('device') != candidate.get('device') or
                    identity.get('capacityBytes', identity.get('capacity_bytes')) !=
                    candidate.get('capacityBytes', candidate.get('capacity_bytes'))):
                return None
            if (not re.match(r'^[0-9a-fA-F]{32}$', str(resource_uuid or '')) or
                    not re.match(r'^[0-9a-fA-F]{64}$', str(fingerprint or ''))):
                return None
            return {
                'schemaVersion': 1,
                'hostUuid': host_uuid,
                'controlOperationUuid': command.get('operationUuid'),
                'resourceUuid': resource_uuid,
                'fingerprint': fingerprint,
                'ownershipGeneration': detail.get('ownership_generation'),
                'bootId': boot_id,
                'poolGeneration': pool_generation,
                'zramDevice': device,
                'candidateIdentity': candidate.get('identity'),
                'candidateState': candidate.get('state'),
                'capacityBytes': candidate.get('capacityBytes', candidate.get('capacity_bytes')),
                'stableIdentity': identity,
                'observedAt': resource.get('observed_at'),
            }
        except Exception:
            # An unreadable or stale backend view must not block the ordinary
            # RAM drain, but it can never authorize offline backend preparation.
            return None

    def _drained_backend_owner_proof(self, host_uuid, control_uuid, pool_generation):
        """Read the owner proof only from the exact, current drained control journal."""
        if (not self._valid_identifier(control_uuid) or
                os.path.islink(self.active_control_path) or
                os.path.realpath(self.active_control_path) != self.active_control_path or
                self._get_active_control() != control_uuid):
            return None
        operation_path = self._operation_path(control_uuid)
        if (os.path.islink(operation_path) or
                os.path.realpath(operation_path) != operation_path):
            return None
        state, record = self._operation_file_state(control_uuid)
        boot_id = self._current_boot_id()
        if (state != 'present' or not isinstance(record, dict) or
                record.get('operationUuid') != control_uuid or
                record.get('action') != 'drain' or record.get('stage') != 'APPLIED' or
                record.get('hostUuid') != host_uuid or record.get('bootId') != boot_id):
            return None
        intent_path = os.path.join(self.operation_dir, '%s.drain-intent.json' % control_uuid)
        if (os.path.islink(intent_path) or
                os.path.realpath(intent_path) != intent_path):
            return None
        try:
            with open(intent_path, 'r') as stream:
                intent = json.load(stream)
        except (IOError, OSError, ValueError, TypeError):
            return None
        if (not isinstance(intent, dict) or intent.get('operationUuid') != control_uuid or
                intent.get('bootId') != boot_id or intent.get('poolGeneration') != pool_generation or
                intent.get('configPath') != self.drain_config or
                intent.get('unit') != 'zstack-memory-drain-%s' % control_uuid or
                intent.get('receiptPath') != os.path.join(
                    self.drain_dir, '%s.receipt.json' % control_uuid) or
                intent.get('stderrPath') != os.path.join(
                    self.drain_dir, '%s.stderr' % control_uuid)):
            return None
        proof = intent.get('backendOwnerProof')
        expected = frozenset(('schemaVersion', 'hostUuid', 'controlOperationUuid',
                              'resourceUuid', 'fingerprint', 'ownershipGeneration',
                              'bootId', 'poolGeneration', 'zramDevice', 'candidateIdentity',
                              'candidateState', 'capacityBytes', 'stableIdentity', 'observedAt'))
        if (not isinstance(proof, dict) or set(proof) != expected or
                proof.get('schemaVersion') != 1 or proof.get('hostUuid') != host_uuid or
                proof.get('controlOperationUuid') != control_uuid or
                proof.get('bootId') != boot_id or proof.get('poolGeneration') != pool_generation or
                proof.get('zramDevice') != intent.get('device') or
                proof.get('candidateState') != 'ACTIVE' or
                proof.get('ownershipGeneration') != proof.get('resourceUuid') or
                proof.get('candidateIdentity') != proof.get('fingerprint') or
                not re.match(r'^[0-9a-fA-F]{32}$', str(proof.get('resourceUuid') or '')) or
                not re.match(r'^[0-9a-fA-F]{64}$', str(proof.get('fingerprint') or '')) or
                not isinstance(proof.get('observedAt'), STRING_TYPES)):
            return None
        identity = proof.get('stableIdentity')
        stable_fields = frozenset(('bootId', 'device', 'byIdPath', 'majorMinor', 'serial',
                                   'wwn', 'capacityBytes', 'transport', 'sysfsPath',
                                   'sysfsInode', 'rdev', 'nodeInode'))
        if (not isinstance(identity, dict) or set(identity) != stable_fields or
                identity.get('bootId') != boot_id or
                identity.get('device') == proof.get('zramDevice') or
                identity.get('capacityBytes') != proof.get('capacityBytes') or
                any(not isinstance(identity.get(key), STRING_TYPES)
                    for key in ('device', 'byIdPath', 'majorMinor', 'serial', 'wwn',
                                'transport', 'sysfsPath', 'sysfsInode')) or
                not identity.get('sysfsPath').startswith(('/sys/devices/', '/sys/block/'))):
            return None
        if (not re.match(r'^[1-9][0-9]*$', identity.get('sysfsInode')) or
                not identity.get('byIdPath') or not identity.get('serial')):
            return None
        for key in ('capacityBytes', 'rdev', 'nodeInode'):
            value = identity.get(key)
            if isinstance(value, bool) or not isinstance(value, INTEGER_TYPES) or value <= 0:
                return None
        return proof

    @staticmethod
    def _drained_backend_candidate_matches(proof, candidate):
        """Require the same fresh disk identity and its sole original ZRAM holder."""
        if (not isinstance(candidate, dict) or candidate.get('type') != 'block' or
                candidate.get('eligible') is not False or
                candidate.get('writebackReady', candidate.get('writeback_ready')) is not False or
                candidate.get('state') != 'INELIGIBLE' or
                candidate.get('reasons') != ['ACTIVE_BLOCK_HOLDERS'] or
                candidate.get('hostBootId', candidate.get('host_boot_id')) != proof.get('bootId') or
                candidate.get('device') != (proof.get('stableIdentity') or {}).get('device') or
                candidate.get('capacityBytes', candidate.get('capacity_bytes')) !=
                proof.get('capacityBytes') or
                candidate.get('resourceUuid', candidate.get('resource_uuid')) is not None or
                not re.match(r'^[0-9a-f]{64}$', str(candidate.get('fingerprint') or '')) or
                candidate.get('identity') != 'candidate:' + candidate.get('fingerprint')):
            return False
        identity = candidate.get('stableIdentity', candidate.get('stable_identity'))
        if identity != proof.get('stableIdentity'):
            return False
        zram_name = os.path.basename(proof.get('zramDevice') or '')
        sysfs_path = identity.get('sysfsPath')
        if (not zram_name or os.path.realpath(sysfs_path) != sysfs_path or
                not sysfs_path.startswith(('/sys/devices/', '/sys/block/'))):
            return False
        holders_path = os.path.join(sysfs_path, 'holders')
        try:
            holders = os.listdir(holders_path)
            if holders != [zram_name]:
                return False
            expected = os.path.realpath(os.path.join('/sys/class/block', zram_name))
            actual = os.path.realpath(os.path.join(holders_path, zram_name))
            return (expected.startswith('/sys/devices/') and actual == expected)
        except (IOError, OSError):
            return False

    def _prepare_stock_drain(self, command):
        """Fence pool identity and disable host admission before withdrawal."""
        native = self._service_request('state', {})
        pool = native.get('host_zram') or native.get('pool') or {}
        generation = pool.get('pool_generation') or native.get('pool_generation')
        device = pool.get('device') or native.get('device')
        if not generation or not device:
            raise ValueError('DRAIN_POOL_IDENTITY_UNKNOWN')
        # Platform drain targets the currently owned pool. An explicit fence
        # is checked when supplied; otherwise this first native observation
        # is frozen in the durable drain intent before the executor starts.
        if command.get('poolGeneration') is not None and command['poolGeneration'] != generation:
            raise ValueError('DRAIN_POOL_GENERATION_MISMATCH')
        backend_owner_proof = self._capture_stock_drain_backend_owner(
            command, generation, device)
        cpu = self._service_request('host-cpu-state', {})
        if not isinstance(cpu.get('revision'), int):
            raise ValueError('DRAIN_CPU_REVISION_UNKNOWN')
        if cpu.get('efficiency_enabled'):
            disable = dict(command)
            disable['operationUuid'] = '%s-drain-disable' % command['operationUuid']
            disable['cpuExpectedRevision'] = cpu['revision']
            policy = dict(disable.get('policy') or {})
            policy['zram'] = {'enabled': False,
                              'cpuThresholdPercent': cpu.get('idle_cpu_threshold_percent', 80),
                              'cpuHoldSeconds': cpu.get('idle_duration_seconds', 60)}
            disable['policy'] = policy
            result = self._service_request('host-cpu', disable)
            if result.get('success') is False:
                raise ValueError('DRAIN_HOST_DISABLE_FAILED')
            verified = self._service_request('host-cpu-state', {})
            if verified.get('efficiency_enabled') is not False:
                raise RuntimeError('DRAIN_HOST_DISABLE_UNVERIFIED')
        return {'poolGeneration': generation, 'device': device,
                'backendOwnerProof': backend_owner_proof}

    def _requires_new_optimization(self, command):
        policy = command.get('policy') or {}
        ksm = policy.get('ksm') or {}
        zram = policy.get('zram') or {}
        writeback = policy.get('writeback') or {}
        return bool(
            ksm.get('enabled') or
            ksm.get('zeroPagesEnabled') or
            zram.get('enabled') or
            writeback.get('enabled'))

    def _verify_rejected_resume_fence(self, command):
        """Read-only proof for an old MN that advanced a rejected resume fence.

        CONTROL_OPERATION_FENCED is raised before preparing/issuing resume.
        A generic failed/unknown operation is not evidence of non-execution.
        Keep both original journals unchanged, even after successful proof.
        """
        operation_uuid = command.get('operationUuid')
        failure = {'success': False, 'status': 'Unknown',
                   'operationUuid': operation_uuid, 'state': {'phase': 'UNKNOWN'},
                   'reasonCode': 'REJECTED_RESUME_FENCE_UNPROVEN'}
        lock = None
        try:
            expected = command.get('expectedControlOperationUuid')
            if (not self._valid_identifier(operation_uuid) or
                    not self._valid_identifier(expected) or operation_uuid == expected):
                return failure
            lock = self._acquire_host_control_lock()
            host = self._load_host_uuid()
            boot = self._current_boot_id()
            if not host or command.get('hostUuid') != host or not boot:
                return failure
            if self._get_active_control() != expected:
                return failure
            records = []
            for identifier in (operation_uuid, expected):
                path = self._operation_path(identifier)
                if os.path.islink(path) or os.path.realpath(path) != path:
                    return failure
                kind, record = self._operation_file_state(identifier)
                if (kind != 'present' or not isinstance(record, dict) or
                        record.get('operationUuid') != identifier or
                        record.get('hostUuid') != host or record.get('bootId') != boot):
                    return failure
                records.append(record)
            rejected, anchor = records
            readback = rejected.get('readback')
            confirmed = anchor.get('readback')
            if (rejected.get('action') != 'resume' or rejected.get('stage') != 'REJECTED' or
                    rejected.get('expectedControlOperationUuid') != expected or
                    not isinstance(readback, dict) or
                    readback.get('reason') != 'CONTROL_OPERATION_FENCED' or
                    anchor.get('action') not in ('pause', 'drain') or anchor.get('stage') != 'APPLIED' or
                    not isinstance(confirmed, dict) or confirmed.get('success') is not True or
                    confirmed.get('status') != 'Succeeded'):
                return failure
            # Recheck the retained fence/epoch while still holding the writer lock.
            if self._get_active_control() != expected or self._current_boot_id() != boot:
                return failure
            return {'success': True, 'status': 'Succeeded', 'operationUuid': operation_uuid,
                    'bootId': boot, 'sampleTime': int(time.time() * 1000),
                    'state': {'phase': 'CONTROL_NOT_ISSUED', 'controlFenceProof': {
                        'schemaVersion': 1, 'hostUuid': host, 'bootId': boot,
                        'rejectedOperationUuid': operation_uuid, 'controlOperationUuid': expected,
                        'controlAction': anchor['action'], 'controlStage': 'APPLIED',
                        'rejectedStage': 'REJECTED', 'reasonCode': 'CONTROL_OPERATION_FENCED'}}}
        except (IOError, OSError, ValueError, TypeError):
            return failure
        finally:
            self._release_operation(lock)

    @kvmagent.replyerror
    def reconcile(self, req):
        command = self._request_body(req)
        if command.get('reconcileAction') == 'verify-completed':
            # This internal action is deliberately separate from normal
            # reconciliation: it may only return a durable, already-APPLIED
            # receipt. It must never resume a worker or repair a journal.
            return self._reply(self._verify_completed_operation(command))
        if command.get('reconcileAction') == 'verify-rejected-resume':
            return self._reply(self._verify_rejected_resume_fence(command))
        operation_uuid = command.get('operationUuid')
        prior = self._load_operation(command) or {}
        proof = ((prior.get('readback') or {}).get('state') or {}).get('recoveryRejectionProof')
        if (command.get('reconcileAction') == 'seal-rejected-recovery' or
                (isinstance(proof, dict) and 'managerRequestHash' in proof)):
            return self._reply(self._seal_rejected_recovery(command))
        if not prior:
            tombstone = self._mark_not_issued(command)
            if tombstone is not None:
                return self._reply(tombstone)
            return self._reply({'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'OPERATION_NOT_FOUND',
                                'operationUuid': operation_uuid})
        evidence = prior.get('applyEvidence') if isinstance(prior, dict) else None
        readback = prior.get('readback') if isinstance(prior, dict) else None
        if (isinstance(evidence, dict) and
                evidence.get('reason') == 'KSM_CLEAR_PRIOR_JOURNAL_INVALID' and
                prior.get('policy') == {'schemaVersion': 1, 'ksm': {}}):
            sealed = self._mark_not_issued(command, expected_prior=prior)
            return self._reply(sealed or {
                'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                'operationUuid': operation_uuid})
        mixed_clear_candidate = (
            isinstance(prior, dict) and
            prior.get('policy') == {'schemaVersion': 1, 'ksm': {}} and
            any(isinstance(item, dict) and
                item.get('reason') == 'MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN'
                for item in (evidence, readback)))
        if mixed_clear_candidate:
            sealed = self._mark_not_issued(command, expected_prior=prior)
            return self._reply(sealed or {
                'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                'operationUuid': operation_uuid})
        prewrite_reasons = ('FIRST_ZRAM_OBSERVATION_NOT_FRESH_OR_SAFE',
                            'KSM_CLEAR_PRIOR_JOURNAL_INVALID')
        prewrite_candidate = (
            isinstance(prior, dict) and prior.get('stage') in ('UNKNOWN', 'NOT_ISSUED') and
            any(isinstance(section, dict) and section.get('reason') in prewrite_reasons
                for section in (evidence, readback)))
        if self._first_use_admission_rejected(prior) or prewrite_candidate:
            return self._reply(self._reconcile_first_zram_admission(command, prior))
        if (isinstance(prior.get('firstZramUse'), dict) and
                prior.get('stage') in (self.FIRST_USE_AUTHORIZING_STAGE, 'UNKNOWN')):
            first_use = prior['firstZramUse']
            if first_use.get('policySubmissionStarted') is True:
                # The normal policy writer may have run.  Bind the ordinary
                # read-only reconciler to the exact authorized runtime, then
                # fall through to its GET/readback-only path.  Never replay
                # apply or clear the first-use fence based on config alone.
                try:
                    self._verify_first_use_runtime_for_policy_reconcile(prior)
                except Exception as exc:
                    return self._reply({'success': False, 'status': 'Unknown',
                                        'state': {'phase': 'UNKNOWN'},
                                        'reasonCode': (str(exc) if re.match(
                                            r'^[A-Z][A-Z0-9_]+$', str(exc)) else
                                            'FIRST_ZRAM_RUNTIME_IDENTITY_UNKNOWN'),
                                        'operationUuid': operation_uuid})
            else:
                return self._reply(self._reconcile_first_zram_use(command, prior))
        if prior.get('bootId') != self._current_boot_id():
            return self._reply({'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'OPERATION_BOOT_CHANGED',
                                'operationUuid': operation_uuid})
        if prior.get('action') == 'recoverUncertain':
            return self._reply(self._reconcile_uncertain_recovery(command, prior))
        if (prior.get('action') == 'apply' and prior.get('stage') == 'APPLIED' and
                isinstance(prior.get('readback'), dict) and
                (prior.get('readback', {}).get('state') or {}).get('phase') == 'POOL_READY'):
            receipt = prior['readback']
            policy = prior.get('policy') or {}
            if policy.get('ksm'):
                ksm_ack = self._reconcile_ksm_proof(prior, policy['ksm'], operation_uuid)
                if ksm_ack is None:
                    return self._reply({'success': False, 'status': 'Unknown',
                                        'state': {'phase': 'UNKNOWN'},
                                        'reasonCode': 'RECONCILE_KSM_NOT_VERIFIED',
                                        'operationUuid': operation_uuid})
                if 'ksmReadback' not in receipt:
                    receipt = dict(receipt, ksmReadback=ksm_ack)
            return self._reply(receipt)
        if (prior.get('action') == 'apply' and
                (prior.get('stage') == 'ACTIVATING' or
                 isinstance(prior.get('activationIntent'), dict))):
            return self._reply(self._reconcile_maintenance_activation(command, prior))
        if (prior.get('action') == 'apply' and prior.get('maintenanceProof') and
                not isinstance(prior.get('activationIntent'), dict)):
            # A drained apply is never reconciled from configuration alone.
            # It may have crashed between native policy writes and durable
            # activation intent; only a new, explicit apply after inspection
            # can proceed from that state.
            return self._reply({'success': False, 'status': 'Unknown',
                                'state': {'phase': 'MAINTENANCE_ACTIVATION_REQUIRED'},
                                'reasonCode': 'MAINTENANCE_ACTIVATION_INTENT_REQUIRED',
                                'operationUuid': operation_uuid})
        if prior.get('action') == 'prepareWritebackBackend':
            return self._reply(self._reconcile_backend_maintenance(command, prior))
        if prior.get('action') == 'prepareZramPool':
            return self._reply(self._reconcile_zram_pool(command, prior))
        if prior.get('action') == 'drain':
            result = self._reconcile_stock_drain(command, prior)
            return self._reply(result)
        policy = prior.get('policy') or {}
        prior_ksm_ack = None
        try:
            if prior.get('hostUuid') != self._load_host_uuid():
                raise ValueError('HOST_IDENTITY_UNKNOWN')
            if prior.get('bootId') != self._current_boot_id():
                raise ValueError('OPERATION_BOOT_CHANGED')
            if prior.get('action') == 'pause':
                state = self._service_request('state', {})
                if (state.get('lifecycle') or {}).get('paused') is not True:
                    raise ValueError('RECONCILE_PAUSE_NOT_VERIFIED')
                pause_state = ((prior.get('readback') or {}).get('state') or {}).get('ksmLifecycle')
                if isinstance(pause_state, dict) and pause_state.get('ksmWasActive') is True:
                    if self._read_ksm_sysfs('run') != '0':
                        raise ValueError('RECONCILE_KSM_NOT_PAUSED')
                result = {'success': True, 'status': 'Succeeded',
                          'state': {'phase': 'PAUSED', 'nativeReadback': state},
                          'operationUuid': operation_uuid}
                self._update_operation_record(operation_uuid, 'APPLIED', result)
                return self._reply(result)
            if str(prior.get('scope', 'host')).lower() == 'vm':
                vm_command = {'_resource_uuid': prior.get('resourceUuid')}
                vm_state = self._service_request('vm-policy-state', vm_command)
                expected_mode = 'deny' if (policy.get('participation') == 'deny' or
                                           prior.get('participation') == 'deny') else 'auto'
                complete = (vm_state.get('mode') == expected_mode and
                            vm_state.get('instance_generation') == prior.get('expectedInstanceGeneration'))
                readback = {'phase': 'VM_READBACK', 'service': vm_state, 'complete': complete}
                if not complete:
                    raise ValueError('RECONCILE_TARGET_NOT_VERIFIED')
                result = {'success': True, 'status': 'Succeeded', 'state': readback,
                          'appliedRevision': prior.get('desiredRevision'),
                          'operationUuid': operation_uuid}
                self._update_operation_record(operation_uuid, 'APPLIED', result)
                return self._reply(result)
            if policy.get('ksm'):
                prior_ksm_ack = self._reconcile_ksm_proof(
                    prior, policy['ksm'], operation_uuid)
                if prior_ksm_ack is None:
                    raise ValueError('RECONCILE_KSM_NOT_VERIFIED')
            if not policy.get('zram') and not policy.get('writeback'):
                if not policy.get('ksm'):
                    raise ValueError('RECONCILE_POLICY_EMPTY')
                result = {'success': True, 'status': 'Succeeded',
                          'state': {'phase': 'KSM_READBACK', 'complete': True},
                          'appliedRevision': prior.get('desiredRevision'),
                          'operationUuid': operation_uuid}
                if prior_ksm_ack is not None:
                    result['ksmReadback'] = prior_ksm_ack
                self._set_active_control(operation_uuid)
                self._update_operation_record(operation_uuid, 'APPLIED', result)
                return self._reply(result)
            readback = self._read_policy_state(command, policy)
            zram_capacity_requested = any(
                key in (policy.get('zram') or {})
                for key in ('logicalCapacityBytes', 'ramLimitBytes'))
            capacity_proof = (self._capacity_apply_evidence(command, prior, readback)
                              if zram_capacity_requested else None)
            evidence_sections = ((prior.get('applyEvidence') or {}).get('state') or {}).get(
                'sections') or {}
            if not zram_capacity_requested and 'cpuGuard' in evidence_sections:
                # A sparse tuning delta can have paused an already enabled
                # host. Matching tuning alone does not prove that its final
                # CPU restore was issued. Reconcile remains read-only and
                # requires this operation's original final receipt.
                before_cpu = self._strict_service_success(
                    'host-cpu-state', evidence_sections.get('cpuBefore'))
                guard = self._strict_service_success(
                    'host-cpu', evidence_sections.get('cpuGuard'))
                final_cpu = self._strict_service_success(
                    'host-cpu', evidence_sections.get('cpu'))
                zram = policy.get('zram') or {}
                expected_cpu = {
                    'efficiency_enabled': bool(zram.get('enabled', before_cpu['efficiency_enabled']) or
                                               ((evidence_sections.get('tuning') or {}).get('settings') or {}).get(
                                                   'writeback', {}).get('enabled', False)),
                    'idle_cpu_threshold_percent': zram.get(
                        'cpuThresholdPercent', before_cpu['idle_cpu_threshold_percent']),
                    'idle_duration_seconds': zram.get(
                        'cpuHoldSeconds', before_cpu['idle_duration_seconds']),
                }
                if (guard.get('request_id') != self._derived_service_request_id(operation_uuid, 'cpu-hold') or
                        guard.get('efficiency_enabled') is not False or
                        final_cpu.get('request_id') != self._derived_service_request_id(operation_uuid, 'cpu') or
                        final_cpu.get('agent_expected_revision') != guard.get('revision') or
                        not self._strict_service_match(
                            {key: final_cpu.get(key) for key in expected_cpu}, expected_cpu)):
                    raise ValueError('RECONCILE_TARGET_NOT_VERIFIED')
                observed_cpu = self._strict_service_success(
                    'host-cpu-state', readback['sections'].get('cpu'))
                if (observed_cpu.get('revision') != final_cpu.get('revision') or
                        not self._strict_service_match(
                            {key: observed_cpu.get(key) for key in expected_cpu}, expected_cpu)):
                    raise ValueError('RECONCILE_TARGET_NOT_VERIFIED')
            if not readback.get('complete'):
                blocked = self._known_capacity_blocker(readback, capacity_proof)
                if blocked is not None:
                    blocked['operationUuid'] = operation_uuid
                    if prior_ksm_ack is not None:
                        blocked['ksmReadback'] = prior_ksm_ack
                    self._update_operation_record(operation_uuid, 'BLOCKED', blocked)
                    return self._reply(blocked)
                result = {'success': False, 'status': 'Unknown',
                          'state': readback,
                          'reasonCode': 'RECONCILE_TARGET_NOT_VERIFIED',
                          'operationUuid': operation_uuid}
                if prior_ksm_ack is not None:
                    result['ksmReadback'] = prior_ksm_ack
                self._update_operation_record(operation_uuid, 'UNKNOWN', result)
                return self._reply(result)
            if zram_capacity_requested and capacity_proof is None:
                # Configuration equality alone cannot prove that this
                # operation produced the native state.  Keep query-only until
                # an original receipt can be tied to the observed revisions.
                result = {'success': False, 'status': 'Unknown',
                          'state': dict(readback, phase='UNKNOWN',
                                        reasonCode='CAPACITY_APPLY_RECEIPT_UNVERIFIED'),
                          'reasonCode': 'CAPACITY_APPLY_RECEIPT_UNVERIFIED',
                          'operationUuid': operation_uuid}
                if prior_ksm_ack is not None:
                    result['ksmReadback'] = prior_ksm_ack
                self._update_operation_record(operation_uuid, 'UNKNOWN', result)
                return self._reply(result)
            result = {'success': True, 'status': 'Succeeded',
                      'state': readback, 'appliedRevision': prior.get('desiredRevision'),
                      'operationUuid': operation_uuid}
            if prior_ksm_ack is not None:
                result['ksmReadback'] = prior_ksm_ack
            self._set_active_control(operation_uuid)
            self._update_operation_record(operation_uuid, 'APPLIED', result)
        except Exception as exc:
            result = {'success': False, 'status': 'Unknown',
                      'state': {'phase': 'UNKNOWN'}, 'reason': str(exc),
                      'reasonCode': 'RECONCILE_READBACK_FAILED',
                      'operationUuid': operation_uuid}
            if prior_ksm_ack is not None:
                result['ksmReadback'] = prior_ksm_ack
            self._update_operation_record(operation_uuid, 'UNKNOWN', result)
        return self._reply(result)

    def _verify_completed_operation(self, command):
        """Return an immutable APPLIED receipt only when its current identity binds."""
        operation_uuid = command.get('operationUuid')

        def unknown(reason):
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': reason, 'operationUuid': operation_uuid}

        host_uuid = self._load_host_uuid()
        boot_id = self._current_boot_id()
        revision = command.get('desiredRevision')
        scope = command.get('scope')
        resource_uuid = command.get('resourceUuid')
        if scope == 'Host':
            command_resource_matches = resource_uuid == host_uuid
        elif scope == 'Global':
            command_resource_matches = resource_uuid == 'global'
        elif scope == 'Cluster':
            command_resource_matches = (isinstance(resource_uuid, STRING_TYPES) and
                                        re.match(r'^[0-9a-f]{32}\Z', resource_uuid) is not None)
        else:
            command_resource_matches = False
        if (not self._valid_identifier(operation_uuid) or
                command.get('action') != 'reconcile' or
                scope not in ('Host', 'Cluster', 'Global') or not command_resource_matches or
                command.get('hostUuid') != host_uuid or not host_uuid or
                command.get('bootId') != boot_id or not boot_id or
                isinstance(revision, bool) or not isinstance(revision, INTEGER_TYPES) or
                revision < 0):
            return unknown('VERIFY_COMPLETED_REQUEST_IDENTITY_INVALID')

        path = self._operation_path(operation_uuid)
        if os.path.islink(path) or not os.path.isfile(path) or os.path.realpath(path) != path:
            return unknown('VERIFY_COMPLETED_OPERATION_UNAVAILABLE')
        state, prior = self._operation_file_state(operation_uuid)
        if state != 'present' or not isinstance(prior, dict):
            return unknown('VERIFY_COMPLETED_OPERATION_UNAVAILABLE')
        expected_control = (operation_uuid if prior.get('action') == 'apply' else
                            prior.get('expectedControlOperationUuid'))
        if (prior.get('operationUuid') != operation_uuid or
                prior.get('action') not in ('apply', 'prepareWritebackBackend') or
                prior.get('scope') != scope or prior.get('resourceUuid') != resource_uuid or
                command.get('expectedControlOperationUuid') != expected_control or
                self._get_active_control() != expected_control or
                prior.get('stage') != 'APPLIED' or prior.get('hostUuid') != host_uuid or
                prior.get('bootId') != boot_id or prior.get('desiredRevision') != revision or
                isinstance(prior.get('desiredRevision'), bool) or
                not isinstance(prior.get('desiredRevision'), INTEGER_TYPES) or
                not isinstance(prior.get('requestHash'), STRING_TYPES) or
                re.match(r'^[0-9a-f]{64}\Z', prior.get('requestHash', '')) is None):
            return unknown('VERIFY_COMPLETED_OPERATION_IDENTITY_MISMATCH')

        receipt = prior.get('readback')
        if (not isinstance(receipt, dict) or receipt.get('success') is not True or
                receipt.get('status') != 'Succeeded' or
                receipt.get('operationUuid') != operation_uuid or
                (prior.get('action') == 'apply' and
                 (receipt.get('appliedRevision') != revision or
                  isinstance(receipt.get('appliedRevision'), bool) or
                  not isinstance(receipt.get('appliedRevision'), INTEGER_TYPES))) or
                (prior.get('action') == 'prepareWritebackBackend' and
                 receipt.get('appliedRevision') is not None and
                 (receipt.get('appliedRevision') != revision or
                  isinstance(receipt.get('appliedRevision'), bool) or
                  not isinstance(receipt.get('appliedRevision'), INTEGER_TYPES))) or
                not isinstance(receipt.get('state'), dict)):
            return unknown('VERIFY_COMPLETED_RECEIPT_UNPROVEN')
        verified_ksm_ack = None
        if prior.get('action') == 'apply':
            policy = prior.get('policy')
            state = receipt['state']
            phase = state.get('phase')
            if not isinstance(policy, dict):
                return unknown('VERIFY_COMPLETED_RECEIPT_UNPROVEN')
            if state.get('ksmOnly') is True or phase == 'KSM_READBACK':
                if (policy.get('zram') or policy.get('writeback') or
                        not self._first_use_terminal_ksm_record(prior, allow_empty_noop=True)):
                    return unknown('VERIFY_COMPLETED_RECEIPT_UNPROVEN')
            elif phase == 'POOL_READY':
                if (not (isinstance(state.get('nativeReadback'), dict) or
                         isinstance(state.get('maintenanceActivation'), dict)) or
                        ('complete' in state and state.get('complete') is not True)):
                    return unknown('VERIFY_COMPLETED_RECEIPT_UNPROVEN')
            elif phase == 'READBACK':
                sections = state.get('sections')
                complete = state.get('sectionComplete')
                if (state.get('complete') is not True or not isinstance(sections, dict) or
                        not isinstance(complete, dict) or not complete or
                        any(value is not True for value in complete.values())):
                    return unknown('VERIFY_COMPLETED_RECEIPT_UNPROVEN')
            else:
                return unknown('VERIFY_COMPLETED_RECEIPT_UNPROVEN')
            if policy.get('ksm'):
                verified_ksm_ack = self._reconcile_ksm_proof(
                    prior, policy['ksm'], operation_uuid)
                if verified_ksm_ack is None:
                    return unknown('VERIFY_COMPLETED_KSM_RECEIPT_UNPROVEN')
        else:
            evidence = self._completed_backend_preparation_evidence(
                operation_uuid, prior, host_uuid, boot_id)
            if evidence is None:
                return unknown('VERIFY_COMPLETED_MAINTENANCE_FILES_UNPROVEN')
            intent = evidence['intent']
            request = evidence['request']
            saved_receipt = evidence['receipt']
            current_receipt, receipt_error = self._read_backend_maintenance_receipt()
            if (receipt_error or current_receipt != saved_receipt):
                return unknown('VERIFY_COMPLETED_MAINTENANCE_RECEIPT_UNPROVEN')
            if self._maintenance_service_state() != 'active':
                return unknown('VERIFY_COMPLETED_MAINTENANCE_SERVICE_UNPROVEN')
            try:
                current_state = self._service_request('state', {})
            except Exception:
                return unknown('VERIFY_COMPLETED_MAINTENANCE_STATE_UNAVAILABLE')
            if not isinstance(current_state, dict):
                return unknown('VERIFY_COMPLETED_MAINTENANCE_STATE_UNAVAILABLE')
            pending = current_state.get('pending_operations')
            if pending is None and 'pending_operations' in current_state:
                pending = []
            host_observation = current_state.get('host')
            if (current_state.get('maintenance_blocks_activation') is not False or
                    not self._is_uninitialized_pool_snapshot(current_state.get('host_zram')) or
                    not isinstance(pending, list) or pending or
                    not isinstance(host_observation, dict) or
                    host_observation.get('qualified') is not True or
                    host_observation.get('safe') is not True or
                    not self._native_observation_is_fresh(current_state, 3) or
                    not self._native_observation_is_fresh(host_observation, 3)):
                return unknown('VERIFY_COMPLETED_MAINTENANCE_POOL_UNPROVEN')
            verified, _ = self._verify_maintenance_service_readback(
                host_uuid, request, saved_receipt)
            if not verified:
                return unknown('VERIFY_COMPLETED_MAINTENANCE_READBACK_UNPROVEN')

        # Never modify the stored readback. This response copy adds only
        # identity/revision values proven by the journal and current host.
        result = dict(receipt)
        result['state'] = dict(receipt['state'])
        if verified_ksm_ack is not None and 'ksmReadback' not in result:
            result['ksmReadback'] = verified_ksm_ack
        result.update({'hostUuid': host_uuid, 'bootId': boot_id,
                       'appliedRevision': revision})
        return result

    def _boot_epoch_millis(self):
        try:
            with open('/proc/stat') as stream:
                for line in stream:
                    if line.startswith('btime '):
                        return int(line.split()[1]) * 1000
        except (IOError, OSError, ValueError, IndexError):
            return None
        return None

    def _mark_not_issued(self, command, expected_prior=None):
        """Persist a manager-proven NOT_SENT result, never a successful apply."""
        if (not self._valid_identifier(command.get('operationUuid')) or
                str(command.get('reconcileAction', '')).lower() != 'seal-if-never-issued' or
                (command.get('classification') is not None and
                 str(command.get('classification')).upper() != 'NOT_SENT')):
            return None
        host_uuid = self._load_host_uuid()
        if not host_uuid or command.get('hostUuid') != host_uuid:
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'HOST_IDENTITY_UNKNOWN',
                    'operationUuid': command.get('operationUuid')}
        current_boot = self._current_boot_id()
        if not current_boot or command.get('bootId') != current_boot:
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'OPERATION_BOOT_CHANGED',
                    'operationUuid': command.get('operationUuid')}
        boot_epoch = self._boot_epoch_millis()
        submitted = command.get('submittedAt', command.get('taskSubmittedAt'))
        if (isinstance(submitted, bool) or not isinstance(submitted, INTEGER_TYPES) or
                not isinstance(boot_epoch, INTEGER_TYPES) or submitted < boot_epoch):
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'NOT_SENT_SUBMISSION_TIME_UNVERIFIED',
                    'operationUuid': command.get('operationUuid')}
        if submitted > int(time.time() * 1000):
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'NOT_SENT_SUBMISSION_TIME_FUTURE',
                    'operationUuid': command.get('operationUuid')}
        operation_uuid = command['operationUuid']
        if not os.path.isdir(self.operation_dir) or not os.access(self.operation_dir, os.R_OK | os.W_OK | os.X_OK):
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                    'operationUuid': operation_uuid}
        try:
            lock = self._acquire_host_control_lock()
        except (IOError, OSError):
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'reasonCode': 'OPERATION_CONCURRENT', 'operationUuid': operation_uuid}
        try:
            journal_state, prior = self._operation_file_state(operation_uuid)
            if journal_state in ('corrupt', 'unreadable'):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': operation_uuid}
            if journal_state == 'present' and not isinstance(prior, dict):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': operation_uuid}
            if (expected_prior is not None and
                    (not isinstance(expected_prior, dict) or
                     not isinstance(prior, dict) or
                     self._operation_hash(prior) != self._operation_hash(expected_prior))):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                        'operationUuid': operation_uuid}
            if os.path.exists(os.path.join(self.operation_dir,
                                           '%s.drain-intent.json' % operation_uuid)):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_RECONCILE_REQUIRED',
                        'operationUuid': operation_uuid}
            if prior:
                evidence = prior.get('applyEvidence')
                if (isinstance(evidence, dict) and
                        evidence.get('reason') == 'KSM_CLEAR_PRIOR_JOURNAL_INVALID' and
                        prior.get('policy') == {'schemaVersion': 1, 'ksm': {}}):
                    readback = prior.get('readback')
                    revision = prior.get('desiredRevision')
                    request_hash = prior.get('requestHash')
                    result = {'success': False, 'status': 'Failed',
                              'reasonCode': 'KSM_CLEAR_NOT_ISSUED',
                              'operationUuid': operation_uuid,
                              'state': {'phase': 'NOT_ISSUED', 'bootId': current_boot,
                                        'requestHash': request_hash,
                                        'policyWritesIssued': False}}
                    # Only the immutable, reason-only pre-write rejection is
                    # eligible. A partial write or a different query identity
                    # remains Unknown and cannot rewrite this journal.
                    valid = (
                        command.get('action') == 'reconcile' and command.get('policy') == {} and
                        command.get('scope') == prior.get('scope') == 'Host' and
                        command.get('resourceUuid') == prior.get('resourceUuid') == host_uuid and
                        command.get('expectedControlOperationUuid') == operation_uuid and
                        prior.get('operationUuid') == operation_uuid and
                        prior.get('hostUuid') == host_uuid and prior.get('bootId') == current_boot and
                        prior.get('action') == 'apply' and prior.get('policyMode') == 'effective' and
                        self._revision(revision) and command.get('desiredRevision') == revision and
                        not isinstance(command.get('desiredRevision'), bool) and
                        isinstance(request_hash, STRING_TYPES) and
                        re.match(r'^[0-9a-f]{64}\Z', request_hash) is not None and
                        prior.get('policyHash') == self._policy_digest(prior['policy']) and
                        evidence == {'reason': 'KSM_CLEAR_PRIOR_JOURNAL_INVALID'} and
                        isinstance(prior.get('updatedAt'), INTEGER_TYPES) and
                        not isinstance(prior.get('updatedAt'), bool) and submitted <= prior['updatedAt'] and
                        not any(key in prior for key in (
                            'firstZramUse', 'activationIntent', 'maintenanceProof',
                            'mixedClearEvidence', 'maintenanceProgress', 'backendPreparation',
                            'poolPreparation')) and
                        ((prior.get('stage') == 'UNKNOWN' and readback == evidence) or
                         (prior.get('stage') == 'NOT_ISSUED' and readback == result)))
                    if (not valid or self._current_boot_id() != current_boot or
                            self._load_host_uuid() != host_uuid):
                        return {'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                                'operationUuid': operation_uuid}
                    if prior.get('stage') == 'NOT_ISSUED':
                        return readback
                    updated = dict(prior, stage='NOT_ISSUED', readback=result,
                                   updatedAt=int(time.time() * 1000))
                    if self._write_operation_record(updated):
                        return result
                    return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                            'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                            'operationUuid': operation_uuid}
                mixed_evidence = (prior.get('applyEvidence')
                                  if isinstance(prior, dict) else None)
                mixed_readback = prior.get('readback') if isinstance(prior, dict) else None
                if (isinstance(mixed_evidence, dict) and
                        mixed_evidence.get('reason') == 'MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN' and
                        prior.get('policy') == {'schemaVersion': 1, 'ksm': {}}):
                    if prior.get('stage') == 'NOT_ISSUED':
                        expected_result = {
                            'success': False, 'status': 'Failed',
                            'reasonCode': 'KSM_CLEAR_NOT_ISSUED',
                            'operationUuid': operation_uuid,
                            'state': {'phase': 'NOT_ISSUED', 'bootId': current_boot,
                                      'requestHash': prior.get('requestHash'),
                                      'policyWritesIssued': False}}
                        if (command.get('action') == 'reconcile' and
                                command.get('policy') == {} and
                                command.get('scope') == prior.get('scope') == 'Host' and
                                command.get('resourceUuid') == prior.get('resourceUuid') == host_uuid and
                                command.get('expectedControlOperationUuid') == operation_uuid and
                                command.get('desiredRevision') == prior.get('desiredRevision') and
                                prior.get('hostUuid') == host_uuid and
                                prior.get('bootId') == current_boot and
                                isinstance(prior.get('requestHash'), STRING_TYPES) and
                                re.match(r'^[0-9a-f]{64}\Z', prior.get('requestHash')) is not None and
                                mixed_readback == expected_result):
                            return mixed_readback
                        return {'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                                'operationUuid': operation_uuid}
                    if prior.get('stage') != 'UNKNOWN' or not isinstance(mixed_readback, dict):
                        return {'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                                'operationUuid': operation_uuid}
                    mixed = ((mixed_evidence.get('state') or {}).get('mixedClearEvidence')
                             if isinstance(mixed_evidence.get('state'), dict) else None)
                    current_control = self._get_active_control()
                    active_state, active = self._operation_file_state(current_control) \
                        if self._valid_identifier(current_control) else ('missing', None)
                    required_record_keys = {
                        'action', 'applyEvidence', 'bootId', 'desiredRevision', 'hostUuid',
                        'operationUuid', 'policy', 'policyHash', 'policyMode', 'readback',
                        'requestHash', 'resourceUuid', 'scope', 'stage', 'updatedAt'}
                    allowed_record_keys = required_record_keys | {'expectedControlOperationUuid'}
                    required_response_keys = {
                        'success', 'status', 'state', 'operationUuid', 'reason', 'reasonCode'}
                    valid = (
                        command.get('action') == 'reconcile' and command.get('policy') == {} and
                        command.get('scope') == prior.get('scope') == 'Host' and
                        command.get('resourceUuid') == prior.get('resourceUuid') == host_uuid and
                        command.get('expectedControlOperationUuid') == operation_uuid and
                        prior.get('operationUuid') == operation_uuid and
                        prior.get('hostUuid') == host_uuid and prior.get('bootId') == current_boot and
                        prior.get('action') == 'apply' and prior.get('policyMode') == 'effective' and
                        prior.get('policy') == {'schemaVersion': 1, 'ksm': {}} and
                        prior.get('policyHash') == self._policy_digest(prior['policy']) and
                        self._revision(prior.get('desiredRevision')) and
                        not isinstance(prior.get('desiredRevision'), bool) and
                        command.get('desiredRevision') == prior.get('desiredRevision') and
                        set(prior) >= required_record_keys and set(prior) <= allowed_record_keys and
                        isinstance(prior.get('requestHash'), STRING_TYPES) and
                        re.match(r'^[0-9a-f]{64}\Z', prior.get('requestHash')) is not None and
                        isinstance(prior.get('updatedAt'), INTEGER_TYPES) and
                        not isinstance(prior.get('updatedAt'), bool) and
                        submitted <= prior.get('updatedAt') and
                        current_control == (mixed.get('priorOperationUuid')
                                            if isinstance(mixed, dict) else None) and
                        active_state == 'present' and isinstance(active, dict) and
                        not any(key in prior for key in (
                            'activationIntent', 'firstZramUse', 'maintenanceProof',
                            'maintenanceProgress', 'maintenanceIntentPath',
                            'poolMaintenanceIntentPath', 'backendPreparation',
                            'poolPreparation', 'recoveryIntent', 'recoveryAttempt',
                            'recoveryReceipt', 'recoveryResult')) and
                        set(mixed_evidence) == required_response_keys and
                        isinstance(mixed_evidence.get('state'), dict) and
                        set(mixed_evidence['state']) == {'phase', 'mixedClearEvidence'} and
                        mixed_evidence.get('success') is False and
                        mixed_evidence.get('status') == 'Unknown' and
                        mixed_evidence.get('operationUuid') == operation_uuid and
                        mixed_evidence.get('reason') == 'MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN' and
                        mixed_evidence.get('reasonCode') == 'MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN' and
                        mixed_evidence['state'].get('phase') == 'UNKNOWN' and
                        mixed_evidence['state'].get('mixedClearEvidence') == mixed and
                        mixed_readback == mixed_evidence and
                        isinstance(mixed, dict) and set(mixed) == {
                            'operationUuid', 'priorOperationUuid', 'priorPolicy', 'priorState',
                            'preflight', 'writes', 'writeAttempts', 'postflight',
                            'ksmReadback', 'priorKsmAck'} and
                        mixed.get('operationUuid') == operation_uuid and
                        mixed.get('priorOperationUuid') == current_control and
                        isinstance(mixed.get('priorPolicy'), dict) and
                        isinstance(mixed.get('priorState'), dict) and
                        isinstance(mixed.get('preflight'), dict) and
                        set(mixed['preflight']) == {'capacity', 'cpu', 'tuning'} and
                        mixed.get('writes') == {} and mixed.get('writeAttempts') == {} and
                        mixed.get('postflight') == {} and mixed.get('ksmReadback') is None and
                        isinstance(mixed.get('priorKsmAck'), dict) and
                        isinstance(active.get('policy'), dict) and
                        mixed.get('priorPolicy') == active.get('policy') and
                        active.get('operationUuid') == current_control and
                        active.get('stage') == 'APPLIED' and
                        active.get('action') == 'apply' and
                        active.get('scope') == 'Host' and active.get('hostUuid') == host_uuid and
                        active.get('resourceUuid') == host_uuid and
                        active.get('bootId') == current_boot and
                        active.get('policyHash') == self._policy_digest(active.get('policy')) and
                        isinstance(active.get('requestHash'), STRING_TYPES) and
                        re.match(r'^[0-9a-f]{64}\Z', active.get('requestHash')) is not None and
                        isinstance(active.get('readback'), dict) and
                        active['readback'].get('status') == 'Succeeded' and
                        active['readback'].get('success') is True and
                        mixed.get('priorKsmAck') ==
                        active['readback'].get('ksmReadback') and
                        self._ksm_proof_policy(mixed.get('priorKsmAck'),
                                               active.get('desiredRevision')) is not None)
                    if not valid:
                        return {'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                                'operationUuid': operation_uuid}
                    if valid:
                        active_state = active['readback'].get('state')
                        sections = active_state.get('sections') if isinstance(active_state, dict) else None
                        if not isinstance(sections, dict):
                            sections = active_state if isinstance(active_state, dict) else {}
                        active_sections = {key: sections[key] for key in
                                           ('capacity', 'cpu', 'tuning') if key in sections}
                        valid = (mixed.get('priorState') == active_sections and
                                 'capacity' not in active_sections)
                    if not valid:
                        return {'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                                'operationUuid': operation_uuid}
                    if valid:
                        for section, action in (('capacity', 'capacity-state'),
                                                ('cpu', 'host-cpu-state'),
                                                ('tuning', 'tuning-state')):
                            saved = mixed['preflight'].get(section)
                            try:
                                self._strict_service_success(action, saved)
                            except (TypeError, ValueError, RuntimeError):
                                valid = False
                                break
                        if valid:
                            saved_capacity = mixed['preflight']['capacity']
                            saved_cpu = mixed['preflight']['cpu']
                            saved_tuning = mixed['preflight']['tuning']
                            prior_cpu = active_sections.get('cpu')
                            prior_tuning = active_sections.get('tuning')
                            saved_capacity_desired = saved_capacity.get('desired')
                            saved_configured = (saved_capacity_desired.get('configured')
                                                if isinstance(saved_capacity_desired, dict) else None)
                            valid = (
                                saved_capacity.get('apply_state') == 'BLOCKED' and
                                saved_capacity.get('reason') == 'NATIVE_POOL_UNQUALIFIED' and
                                isinstance(saved_configured, dict) and bool(saved_configured) and
                                'effective_logical_bytes' in saved_capacity and
                                saved_capacity.get('effective_logical_bytes') is None and
                                'effective_physical_limit_bytes' in saved_capacity and
                                saved_capacity.get('effective_physical_limit_bytes') is None and
                                saved_cpu.get('efficiency_enabled') is False and
                                isinstance(prior_cpu, dict) and
                                saved_cpu.get('revision') == prior_cpu.get('revision') and
                                isinstance(prior_tuning, dict) and
                                prior_tuning.get('_http_status') == 200 and
                                prior_tuning.get('agent_request_id',
                                                  prior_tuning.get('request_id')) ==
                                self._derived_service_request_id(current_control, 'tuning') and
                                isinstance(prior_tuning.get('revision'), INTEGER_TYPES) and
                                not isinstance(prior_tuning.get('revision'), bool) and
                                saved_tuning.get('revision') == prior_tuning.get('revision') and
                                self._strict_service_match(saved_tuning.get('settings'),
                                                           prior_tuning.get('settings')) and
                                isinstance(saved_tuning.get('settings'), dict) and
                                isinstance(saved_tuning['settings'].get('writeback'), dict) and
                                saved_tuning['settings']['writeback'].get('enabled') is False)
                    if not valid:
                        return {'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                                'operationUuid': operation_uuid}
                    if valid:
                        target_command = {
                            'action': 'apply', 'operationUuid': operation_uuid,
                            'hostUuid': host_uuid, 'scope': 'Host',
                            'resourceUuid': host_uuid, 'policyMode': 'effective',
                            'desiredRevision': prior.get('desiredRevision'),
                            'policy': prior.get('policy')}
                        if 'expectedControlOperationUuid' in prior:
                            target_command['expectedControlOperationUuid'] = prior.get(
                                'expectedControlOperationUuid')
                        context_holder = {}
                        try:
                            context = self._mixed_clear_context(target_command, context_holder)
                        except Exception:
                            valid = False
                        current_preflight = context_holder.get('context', {}).get('preflight')
                        valid = (valid and context is None and
                                 context_holder.get('preparedKsmClear') == {
                                     'priorKsmAck': mixed.get('priorKsmAck')} and
                                 isinstance(current_preflight, dict) and
                                 all(self._strict_service_match(
                                     current_preflight.get(section), mixed['preflight'][section])
                                     for section in ('capacity', 'cpu', 'tuning')))
                    if not valid:
                        return {'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                                'operationUuid': operation_uuid}
                    if valid:
                        result = {'success': False, 'status': 'Failed',
                                  'reasonCode': 'KSM_CLEAR_NOT_ISSUED',
                                  'operationUuid': operation_uuid,
                                  'state': {'phase': 'NOT_ISSUED', 'bootId': current_boot,
                                            'requestHash': prior.get('requestHash'),
                                            'policyWritesIssued': False}}
                        if prior.get('stage') == 'NOT_ISSUED':
                            return prior.get('readback')
                        updated = dict(prior, stage='NOT_ISSUED', readback=result,
                                       updatedAt=int(time.time() * 1000))
                        if self._write_operation_record(updated):
                            return result
                        return {'success': False, 'status': 'Unknown',
                                'state': {'phase': 'UNKNOWN'},
                                'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                                'operationUuid': operation_uuid}
                    return {'success': False, 'status': 'Unknown',
                            'state': {'phase': 'UNKNOWN'},
                            'reasonCode': 'KSM_CLEAR_RECONCILE_IDENTITY_UNKNOWN',
                            'operationUuid': operation_uuid}
                if prior.get('stage') in ('NOT_ISSUED', 'APPLIED') and isinstance(prior.get('readback'), dict):
                    return prior['readback']
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_RECONCILE_REQUIRED',
                        'operationUuid': operation_uuid}
            result = {'success': False, 'status': 'Failed',
                      'state': {'phase': 'NOT_ISSUED'},
                      'reasonCode': 'OPERATION_NEVER_ISSUED',
                      'operationUuid': operation_uuid}
            if not self._record_operation(command, 'NOT_ISSUED', result):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': operation_uuid}
            return result
        finally:
            self._release_operation(lock)

    def _reconcile_stock_drain(self, command, prior):
        # Concurrent polls of one drain must not overwrite each other's result.
        try:
            lock = self._acquire_host_control_lock()
        except (IOError, OSError):
            return {'success': True, 'status': 'Draining', 'state': {'phase': 'DRAINING', 'pending': True},
                    'reasonCode': 'DRAIN_RECONCILE_LOCK_BUSY', 'operationUuid': command.get('operationUuid')}
        try:
            return self._reconcile_stock_drain_locked(command, prior)
        finally:
            self._release_operation(lock)

    def _reconcile_stock_drain_locked(self, command, prior):
        operation_uuid = command.get('operationUuid')
        def unknown(reason, phase='UNKNOWN'):
            result = {'success': False, 'status': 'Unknown',
                      'state': {'phase': phase}, 'reasonCode': reason,
                      'operationUuid': operation_uuid}
            self._update_operation_record(operation_uuid, phase, result)
            return result
        if not self._valid_identifier(operation_uuid):
            return unknown('INVALID_OPERATION_UUID')
        try:
            with open(os.path.join(self.operation_dir, '%s.drain-intent.json' % operation_uuid)) as stream:
                intent = json.load(stream)
        except (IOError, OSError, ValueError):
            return unknown('DRAIN_INTENT_MISSING')
        boot = self._current_boot_id()
        if not boot or prior.get('bootId') != boot or intent.get('bootId') != boot:
            return unknown('DRAIN_BOOT_CHANGED')
        if prior.get('hostUuid') != self._load_host_uuid():
            return unknown('HOST_IDENTITY_UNKNOWN')
        expected_pool, device = intent.get('poolGeneration'), intent.get('device')
        unit = 'zstack-memory-drain-%s' % operation_uuid
        receipt_path = os.path.join(self.drain_dir, '%s.receipt.json' % operation_uuid)
        if (intent.get('operationUuid') != operation_uuid or not expected_pool or not device
                or intent.get('unit') != unit or intent.get('receiptPath') != receipt_path
                or intent.get('configPath') != self.drain_config):
            return unknown('DRAIN_INTENT_INVALID')
        try:
            with open(receipt_path, 'r') as stream:
                data = stream.read().strip()
            receipt = json.loads(data) if data else None
        except (IOError, OSError, ValueError):
            receipt = None
        if not isinstance(receipt, dict):
            alive = False
            if unit:
                try:
                    status = subprocess.check_output(
                        ['systemctl', 'show', unit, '--property=ActiveState', '--value'])
                    alive = status.decode('utf-8').strip() in ('activating', 'active', 'deactivating')
                except (IOError, OSError, subprocess.CalledProcessError):
                    alive = False
            if alive:
                result = {'success': True, 'status': 'Draining',
                          'state': {'phase': 'DRAINING', 'pending': True},
                          'reasonCode': 'DRAIN_RECEIPT_PENDING',
                          'operationUuid': operation_uuid}
                # Keep the durable operation in DRAINING so MN continues its
                # normal poll/reconcile loop; this is not completion.
                self._update_operation_record(operation_uuid, 'DRAINING', result)
                return result
            return unknown('DRAIN_EXECUTOR_RESULT_UNKNOWN', 'UNKNOWN')
        def withdrawn(value):
            return (isinstance(value, dict) and
                    value.get('state') == 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED' and
                    value.get('active') is False and value.get('reset_performed') is False and
                    value.get('pool_generation') == expected_pool and value.get('device') == device)
        if not withdrawn(receipt):
            return unknown('DRAIN_RECEIPT_UNVERIFIED')
        latest = self._load_operation(command)
        confirmed = (latest.get('readback') if isinstance(latest, dict) and latest.get('stage') == 'APPLIED'
                     and (latest.get('readback') or {}).get('status') == 'Succeeded' else None)
        try:
            # Mandatory, fresh, read-only native check. Never trust a receipt
            # alone or silently skip verification when the binary is missing.
            check = subprocess.check_output(
                [self.drain_binary, '--config', self.drain_config, '--drain-check'],
                stderr=subprocess.STDOUT)
            native = json.loads(check.decode('utf-8'))
            if not withdrawn(native):
                return unknown('DRAIN_CHECK_UNVERIFIED')
        except subprocess.CalledProcessError as exc:
            # The native check takes the service state lock; a concurrent poll
            # holding it neither proves nor disproves the drain.
            if b'state directory already in use' in (exc.output or b''):
                return confirmed or {'success': True, 'status': 'Draining',
                                     'state': {'phase': 'DRAINING', 'pending': True},
                                     'reasonCode': 'DRAIN_CHECK_BUSY', 'operationUuid': operation_uuid}
            return confirmed or unknown('DRAIN_CHECK_UNVERIFIED')
        except (IOError, OSError, ValueError):
            return confirmed or unknown('DRAIN_CHECK_UNVERIFIED')
        result = {'success': True, 'status': 'Succeeded',
                  'state': {'phase': native['state'], 'receipt': receipt, 'nativeReadback': native},
                  'appliedRevision': prior.get('desiredRevision'),
                  'operationUuid': operation_uuid}
        if self._update_operation_record(operation_uuid, 'APPLIED', result):
            owner_proof = self._drained_backend_owner_proof(
                prior.get('hostUuid'), operation_uuid, expected_pool)
            if owner_proof:
                result['state']['backendOwnerProof'] = owner_proof
                if not self._update_operation_record(operation_uuid, 'APPLIED', result):
                    result['state'].pop('backendOwnerProof', None)
        return result

    @staticmethod
    def _mapping_contains(actual, expected):
        """Compare only fields owned by this product policy."""
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            return False
        for key, value in expected.items():
            if isinstance(value, dict):
                if not MemoryOptimizationPlugin._mapping_contains(actual.get(key), value):
                    return False
            elif value is not None and actual.get(key) != value:
                return False
        return True

    @staticmethod
    def _revision(value):
        return (isinstance(value, INTEGER_TYPES) and not isinstance(value, bool) and
                value > 0)

    @staticmethod
    def _policy_digest(policy):
        return hashlib.sha256(json.dumps(
            policy, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()

    def _capacity_apply_evidence(self, command, prior, readback):
        """Return strict receipt/readback proof for a capacity apply.

        Capacity and host CPU share one service revision. The original 202
        capacity receipt must therefore be tied to this operation, verified by
        a capacity GET and the final CPU/capacity GET revisions. When this
        operation writes CPU policy, its exact receipt is also required; a
        capacity-only update with dispatch already off performs no CPU PUT.
        Any intervening writer leaves the result Unknown. This does not parse
        free text, host metrics, or VM inventory.
        """
        operation_uuid = command.get('operationUuid')
        if (not isinstance(prior, dict) or prior.get('action') not in (None, 'apply') or
                prior.get('operationUuid') != operation_uuid or
                prior.get('hostUuid') != self._load_host_uuid() or
                prior.get('bootId') != self._current_boot_id()):
            return None
        request_hash = prior.get('requestHash')
        if (not isinstance(request_hash, STRING_TYPES) or
                re.match(r'^[0-9a-f]{64}$', request_hash) is None):
            return None
        policy = prior.get('policy')
        if (not isinstance(policy, dict) or
                prior.get('policyHash') != self._policy_digest(policy)):
            return None
        evidence = prior.get('applyEvidence')
        if (not isinstance(evidence, dict) or evidence.get('operationUuid') != operation_uuid or
                evidence.get('status') != 'Draining' or evidence.get('success') is not True):
            return None
        evidence_state = evidence.get('state')
        nested_sections = (evidence_state.get('sections')
                           if isinstance(evidence_state, dict) else None)
        sections = (nested_sections.get('capacity')
                    if isinstance(nested_sections, dict) else
                    (evidence_state.get('capacity')
                     if isinstance(evidence_state, dict) else None))
        zram = policy.get('zram') or {}
        expected_logical = zram.get('logicalCapacityBytes')
        expected_physical = zram.get('ramLimitBytes')
        if (not isinstance(sections, dict) or sections.get('_http_status') != 202 or
                not self._revision(sections.get('revision')) or
                sections.get('agent_request_id') != self._derived_service_request_id(
                    operation_uuid, 'capacity') or
                (sections.get('request_id') is not None and
                 sections.get('request_id') != self._derived_service_request_id(
                     operation_uuid, 'capacity')) or
                expected_logical is None or expected_physical is None):
            return None
        expected_capacity_revision = sections.get('agent_expected_revision')
        if (not isinstance(expected_capacity_revision, INTEGER_TYPES) or
                isinstance(expected_capacity_revision, bool) or expected_capacity_revision < 0):
            return None
        desired = sections.get('desired')
        configured = desired.get('configured') if isinstance(desired, dict) else None
        logical = configured.get('logical_capacity') if isinstance(configured, dict) else None
        physical = configured.get('physical_memory_limit') if isinstance(configured, dict) else None
        if (not isinstance(logical, dict) or
                not self._strict_service_match(logical.get('bytes'), expected_logical) or
                not isinstance(physical, dict) or
                not self._strict_service_match(physical.get('bytes'), expected_physical)):
            return None
        original_state = evidence.get('state')
        original_sections = original_state if isinstance(original_state, dict) else {}
        original_section_map = original_sections.get('sections')
        if not isinstance(original_section_map, dict):
            return None
        cpu_before = original_section_map.get('cpuBefore')
        if (not isinstance(cpu_before, dict) or cpu_before.get('_http_status') != 200 or
                not isinstance(cpu_before.get('revision'), INTEGER_TYPES) or
                isinstance(cpu_before.get('revision'), bool) or
                cpu_before.get('revision') < 0 or
                not isinstance(cpu_before.get('efficiency_enabled'), bool) or
                'idle_cpu_threshold_percent' not in cpu_before or
                'idle_duration_seconds' not in cpu_before):
            return None

        # The in-operation capacity GET occurs after tuning but before the
        # final host CPU PUT. It proves the accepted 202 still described the
        # configured target at the exact receipt revision.
        capacity_before_cpu = original_section_map.get('capacityReadback')
        if (not isinstance(capacity_before_cpu, dict) or
                capacity_before_cpu.get('_http_status') != 200 or
                not self._revision(capacity_before_cpu.get('revision')) or
                capacity_before_cpu.get('revision') != sections.get('revision') or
                capacity_before_cpu.get('apply_state') != 'BLOCKED' or
                capacity_before_cpu.get('reason') != 'NATIVE_POOL_UNQUALIFIED'):
            return None
        before_cpu_desired = capacity_before_cpu.get('desired')
        before_cpu_configured = (before_cpu_desired.get('configured')
                                 if isinstance(before_cpu_desired, dict) else None)
        before_cpu_logical = (before_cpu_configured.get('logical_capacity')
                              if isinstance(before_cpu_configured, dict) else None)
        before_cpu_physical = (before_cpu_configured.get('physical_memory_limit')
                               if isinstance(before_cpu_configured, dict) else None)
        if (not isinstance(before_cpu_logical, dict) or
                not self._strict_service_match(before_cpu_logical.get('bytes'), expected_logical) or
                not isinstance(before_cpu_physical, dict) or
                not self._strict_service_match(before_cpu_physical.get('bytes'), expected_physical)):
            return None

        # Capacity and CPU share the Host policy revision. Accept a newer
        # current capacity revision only when it is exactly the revision
        # committed by this operation's final CPU PUT, with a matching CPU
        # readback. Do not assume arithmetic (for example N+1), and do not
        # accept a merely equal capacity value after an unrelated write.
        cpu_receipt = original_section_map.get('cpu')
        cpu_observed = original_section_map.get('cpuReadback')
        cpu_expected_revision = (cpu_receipt.get('agent_expected_revision')
                                 if isinstance(cpu_receipt, dict) else None)
        expected_cpu_request_id = self._derived_service_request_id(operation_uuid, 'cpu')
        zram_enabled = zram.get('enabled', cpu_before.get('efficiency_enabled'))
        writeback_enabled = ((original_section_map.get('tuning') or {}).get('settings') or {}).get(
            'writeback', {}).get('enabled', False)
        expected_cpu_enabled = bool(zram_enabled or writeback_enabled)
        expected_cpu_threshold = zram.get(
            'cpuThresholdPercent', cpu_before.get('idle_cpu_threshold_percent'))
        expected_cpu_duration = zram.get(
            'cpuHoldSeconds', cpu_before.get('idle_duration_seconds'))
        cpu_write_required = (cpu_before['efficiency_enabled'] or
                              any(key in zram for key in (
                                  'enabled', 'cpuThresholdPercent', 'cpuHoldSeconds')) or
                              'enabled' in (policy.get('writeback') or {}))
        if cpu_write_required:
            if (not isinstance(cpu_receipt, dict) or cpu_receipt.get('_http_status') != 200 or
                    not self._revision(cpu_receipt.get('revision')) or
                    cpu_receipt.get('request_id') != expected_cpu_request_id or
                    not self._revision(cpu_expected_revision) or
                    cpu_expected_revision != sections.get('revision') or
                    cpu_receipt.get('agent_desired_enabled') is not expected_cpu_enabled or
                    cpu_receipt.get('agent_desired_threshold_percent') != expected_cpu_threshold or
                    cpu_receipt.get('agent_desired_duration_seconds') != expected_cpu_duration or
                    cpu_receipt.get('efficiency_enabled') is not expected_cpu_enabled):
                return None
            final_revision = cpu_receipt['revision']
        else:
            # The existing apply path skips CPU writes only when dispatch was
            # already off and the delta contains no CPU policy. Its capacity
            # CAS must start at that original CPU revision; all subsequent
            # readbacks must remain at the capacity receipt revision. A
            # missing receipt from a requested/guarded CPU write is never
            # evidence for this branch.
            if (any(key in original_section_map for key in (
                    'cpu', 'cpuGuard', 'cpuGuardReadback')) or
                    expected_capacity_revision != cpu_before['revision'] or
                    evidence_state.get('sectionComplete', {}).get('tuning') is not True):
                return None
            final_revision = sections['revision']
        if (not isinstance(cpu_observed, dict) or cpu_observed.get('_http_status') != 200 or
                not self._revision(cpu_observed.get('revision')) or
                cpu_observed.get('revision') != final_revision or
                cpu_observed.get('efficiency_enabled') is not expected_cpu_enabled or
                cpu_observed.get('idle_cpu_threshold_percent') != expected_cpu_threshold or
                cpu_observed.get('idle_duration_seconds') != expected_cpu_duration or
                evidence_state.get('sectionComplete', {}).get('cpu') is not True):
            return None

        current = (readback.get('sections') or {}).get('capacity')
        current_cpu = (readback.get('sections') or {}).get('cpu')
        if (not isinstance(current, dict) or current.get('_http_status') != 200 or
                not self._revision(current.get('revision')) or
                current.get('revision') != final_revision or
                not isinstance(current_cpu, dict) or current_cpu.get('_http_status') != 200 or
                not self._revision(current_cpu.get('revision')) or
                current_cpu.get('revision') != final_revision or
                current_cpu.get('efficiency_enabled') is not expected_cpu_enabled or
                current_cpu.get('idle_cpu_threshold_percent') != expected_cpu_threshold or
                current_cpu.get('idle_duration_seconds') != expected_cpu_duration or
                readback.get('sectionComplete', {}).get('cpu') is not True):
            return None
        current_desired = current.get('desired')
        current_configured = (current_desired.get('configured')
                              if isinstance(current_desired, dict) else None)
        current_logical = (current_configured.get('logical_capacity')
                           if isinstance(current_configured, dict) else None)
        current_physical = (current_configured.get('physical_memory_limit')
                            if isinstance(current_configured, dict) else None)
        if (not isinstance(current_logical, dict) or
                not self._strict_service_match(current_logical.get('bytes'), expected_logical) or
                not isinstance(current_physical, dict) or
                not self._strict_service_match(current_physical.get('bytes'), expected_physical)):
            return None

        # CPU and tuning were already accepted in the same request.  Their
        # exact receipt revisions must still be the revisions observed now;
        # otherwise another writer may have superseded this request.
        for name in ('tuning',):
            receipt = original_section_map.get(name)
            observed = (readback.get('sections') or {}).get(name)
            expected_request_id = self._derived_service_request_id(
                operation_uuid, 'cpu' if name == 'cpu' else 'tuning')
            if (not isinstance(receipt, dict) or receipt.get('_http_status') != 200 or
                    not self._revision(receipt.get('revision')) or
                    receipt.get('request_id', receipt.get('agent_request_id')) != expected_request_id or
                    not isinstance(observed, dict) or observed.get('_http_status') != 200 or
                    not self._revision(observed.get('revision')) or
                    observed.get('revision') != receipt.get('revision') or
                    not readback.get('sectionComplete', {}).get(name)):
                return None
        return {
            'capacityRevision': sections['revision'],
            'currentCapacity': current,
            'applyEvidence': evidence,
        }

    @staticmethod
    def _known_capacity_blocker(readback, proof):
        if proof is None:
            return None
        current = proof['currentCapacity']
        # This enum is emitted by CapacityApplication; never map free-form
        # host/service reason text to a blocker.
        if (current.get('apply_state') != 'BLOCKED' or
                current.get('reason') != 'NATIVE_POOL_UNQUALIFIED'):
            return None
        blockers = [{'section': 'capacity', 'code': current['reason']}]
        state = dict(readback)
        state.update({'phase': 'BLOCKED', 'knownBlocked': True,
                      'blockers': blockers, 'applyEvidence': proof['applyEvidence']})
        return {'success': False, 'status': 'Blocked', 'appliedRevision': None,
                'state': state, 'blockers': blockers,
                'reasonCode': current['reason']}

    def _read_policy_state(self, command, policy):
        """Read all native sections and prove the product target is applied."""
        state = {'phase': 'READBACK', 'sections': {}, 'sectionComplete': {}}
        complete = True
        zram = policy.get('zram') or {}
        if 'logicalCapacityBytes' in zram or 'ramLimitBytes' in zram:
            capacity = self._service_request('capacity-state', command)
            expected = {'effective_logical_bytes': zram.get('logicalCapacityBytes'),
                        'effective_physical_limit_bytes': zram.get('ramLimitBytes')}
            ok = (isinstance(capacity, dict) and
                  self._mapping_contains(capacity, expected) and
                  str(capacity.get('apply_state', '')).upper() == 'APPLIED')
            state['sections']['capacity'] = capacity
            state['sectionComplete']['capacity'] = ok
            complete = complete and ok
        tuning = self._service_request('tuning-state', command)
        # Every service-backed delta may quiesce CPU dispatch, including a
        # backend-only or tuning-only update with no explicit CPU fields.
        # Always read the real state needed by the final CAS/restore.
        if zram or policy.get('writeback'):
            cpu = self._service_request('host-cpu-state', command)
            expected = {}
            for product, native in (('enabled', 'efficiency_enabled'),
                                    ('cpuThresholdPercent', 'idle_cpu_threshold_percent'),
                                    ('cpuHoldSeconds', 'idle_duration_seconds')):
                if product in zram:
                    expected[native] = zram[product]
            if 'enabled' in zram:
                expected['efficiency_enabled'] = bool(
                    zram['enabled'] or (policy.get('writeback') or {}).get(
                        'enabled', (tuning.get('settings', tuning).get('writeback') or {}).get(
                            'enabled', False)))
            elif (policy.get('writeback') or {}).get('enabled') is True:
                expected['efficiency_enabled'] = True
            state['sections']['cpu'] = cpu
            cpu_ok = (isinstance(cpu, dict) and cpu.get('_http_status') == 200 and
                      isinstance(cpu.get('efficiency_enabled'), bool) and
                      self._mapping_contains(cpu, expected))
            state['sectionComplete']['cpu'] = cpu_ok
            complete = complete and cpu_ok
        # Tuning is written for every service-backed policy.  Compare the
        # explicit fields only; service defaults are not product evidence.
        tuning_expected = {}
        for product_key, native_key in (
                ('requiredAvailableBytes', 'required_available_bytes'),
                ('hostFloorBytes', 'host_floor_bytes'),
                ('metadataReserveBytes', 'metadata_reserve_bytes'),
                ('transientReserveBytes', 'transient_reserve_bytes'),
                ('operationIntervalSeconds', 'reclaim_operation_interval_seconds')):
            if product_key in zram:
                tuning_expected[native_key] = zram[product_key]
        for product_key, native_key in (
                ('selectionMode', 'vm_management.mode'),
                ('selectedVmUuids', 'vm_management.vm_uuids'),
                ('discoveryIntervalSeconds', 'discovery_interval_seconds'),
                ('discoveryTimeoutSeconds', 'discovery_timeout_seconds'),
                ('discoveryTtlSeconds', 'discovery_ttl_seconds'),
                ('hostSampleIntervalSeconds', 'host_sample_interval_seconds'),
                ('hostSampleTtlSeconds', 'host_sample_ttl_seconds'),
                ('vmSampleIntervalSeconds', 'vm_sample_interval_seconds'),
                ('vmSampleTtlSeconds', 'vm_sample_ttl_seconds'),
                ('hostCpuGuardEnabled', 'host_cpu_guard_enabled'),
                ('hostMemoryPsiGuardEnabled', 'host_memory_psi_guard_enabled'),
                ('hostIoPsiGuardEnabled', 'host_io_psi_guard_enabled'),
                ('hostCpuThresholdPercent', 'host_cpu_threshold_percent'),
                ('hostMemoryPsiThresholdPercent', 'host_memory_psi_threshold_percent'),
                ('hostIoPsiThresholdPercent', 'host_io_psi_threshold_percent'),
                ('reclaimBatchBytes', 'reclaim_batch_bytes'),
                ('concurrency', 'reclaim_concurrency'),
                ('reclaimSlowOperationSeconds', 'reclaim_slow_operation_seconds'),
                ('timeoutIsolationSlots', 'timeout_isolation_slots'),
                ('operationRecordBudgetBytes', 'operation_record_budget_bytes'),
                ('startupObservationSeconds', 'startup_observation_seconds'),
                ('algorithm', 'algorithm')):
            if product_key in zram:
                if '.' in native_key:
                    section, key = native_key.split('.', 1)
                    tuning_expected.setdefault(section, {})[key] = zram[product_key]
                else:
                    tuning_expected[native_key] = zram[product_key]
        wb = policy.get('writeback') or {}
        wb_expected = {}
        for product_key, native_key in (
                ('enabled', 'enabled'), ('batchBytes', 'batch_bytes'),
                ('idleObservationSeconds', 'idle_observation_seconds'),
                ('operationIntervalSeconds', 'operation_interval_seconds'),
                ('slowOperationSeconds', 'slow_operation_seconds'),
                ('noProgressLimit', 'no_progress_limit'),
                ('backoffSeconds', 'backoff_seconds'),
                ('ioErrorBackoffSeconds', 'io_error_backoff_seconds'),
                ('metadataBudgetBytes', 'metadata_budget_bytes'),
                ('filesystemReserveBytes', 'filesystem_reserve_bytes')):
            if product_key in wb:
                wb_expected[native_key] = wb[product_key]
        if wb_expected:
            tuning_expected['writeback'] = wb_expected
        state['sections']['tuning'] = tuning
        tuning_ok = isinstance(tuning, dict) and self._mapping_contains(
            tuning.get('settings', tuning), tuning_expected)
        state['sectionComplete']['tuning'] = tuning_ok
        complete = complete and tuning_ok
        state['complete'] = complete
        return state

    @staticmethod
    def _strict_service_match(actual, expected):
        """Compare service JSON without Python's bool/int equality coercion."""
        if isinstance(expected, bool):
            return isinstance(actual, bool) and actual is expected
        if isinstance(expected, INTEGER_TYPES):
            return (isinstance(actual, INTEGER_TYPES) and not isinstance(actual, bool) and
                    actual == expected)
        if isinstance(expected, float):
            return (isinstance(actual, (int, float)) and not isinstance(actual, bool) and
                    actual == expected)
        if isinstance(expected, dict):
            return (isinstance(actual, dict) and all(
                key in actual and MemoryOptimizationPlugin._strict_service_match(actual[key], value)
                for key, value in expected.items()))
        if isinstance(expected, list):
            return (isinstance(actual, list) and len(actual) == len(expected) and all(
                MemoryOptimizationPlugin._strict_service_match(a, e)
                for a, e in zip(actual, expected)))
        return actual == expected

    @classmethod
    def _capacity_desired_matches(cls, response, zram):
        """Check persisted capacity intent without claiming native activation."""
        desired = response.get('desired') if isinstance(response, dict) else None
        configured = desired.get('configured') if isinstance(desired, dict) else None
        if not isinstance(configured, dict):
            return False
        expected = {}
        for product, native in (('logicalCapacityBytes', 'logical_capacity'),
                                ('ramLimitBytes', 'physical_memory_limit')):
            if product in zram:
                expected[native] = {'bytes': zram[product]}
        return bool(expected) and cls._strict_service_match(configured, expected)

    @staticmethod
    def _strict_service_success(action, response):
        state = response.get('state') if isinstance(response, dict) else None
        phase = state.get('phase') if isinstance(state, dict) else state
        if (not isinstance(response, dict) or type(response.get('_http_status')) is not int or
                response.get('_http_status') != 200 or
                ('success' in response and response.get('success') is not True) or
                response.get('error') is not None or
                (isinstance(phase, STRING_TYPES) and
                 phase.upper() in
                 ('UNKNOWN', 'FAILED', 'DRAINING', 'PENDING', 'RECONCILING')) or
                (response.get('status') is not None and
                 str(response.get('status')).upper() not in ('SUCCEEDED', 'APPLIED')) or
                MemoryOptimizationPlugin._is_async_service_result(response)):
            raise RuntimeError('SERVICE_%s_READBACK_UNTRUSTED' % action.upper())
        revision = response.get('revision')
        if (not isinstance(revision, INTEGER_TYPES) or isinstance(revision, bool) or
                revision < 0):
            raise RuntimeError('SERVICE_%s_REVISION_UNKNOWN' % action.upper())
        if action in ('capacity-state', 'capacity'):
            if action == 'capacity-state':
                if not isinstance(response.get('apply_state'), STRING_TYPES):
                    raise RuntimeError('SERVICE_CAPACITY_STATE_UNKNOWN')
            elif response.get('request_id') is not None and not isinstance(
                    response.get('request_id'), STRING_TYPES):
                raise RuntimeError('SERVICE_CAPACITY_RECEIPT_INVALID')
        elif action in ('host-cpu-state', 'host-cpu'):
            if action == 'host-cpu-state':
                if (not isinstance(response.get('efficiency_enabled'), bool) or
                        isinstance(response.get('idle_cpu_threshold_percent'), bool) or
                        not isinstance(response.get('idle_cpu_threshold_percent'), (int, float)) or
                        isinstance(response.get('idle_duration_seconds'), bool) or
                        not isinstance(response.get('idle_duration_seconds'), INTEGER_TYPES)):
                    raise RuntimeError('SERVICE_CPU_STATE_UNKNOWN')
            elif not isinstance(response.get('request_id'), STRING_TYPES):
                raise RuntimeError('SERVICE_CPU_RECEIPT_INVALID')
        elif action in ('tuning-state', 'apply'):
            if not isinstance(response.get('settings'), dict):
                raise RuntimeError('SERVICE_TUNING_STATE_UNKNOWN')
        return response

    def _strict_service_revision(self, action):
        value = self._strict_service_success(action, self.service_call(action, {}))
        revision = value.get('revision')
        if not isinstance(revision, INTEGER_TYPES) or isinstance(revision, bool) or revision < 0:
            raise RuntimeError('SERVICE_%s_REVISION_UNKNOWN' % action.upper())
        return value

    def _mixed_clear_context(self, command, context_holder=None):
        """Preflight a current mixed journal before any native clear write."""
        policy = command.get('policy') or {}
        if self._policy_mode(command) != 'effective':
            return None
        operation_uuid = self._get_active_control()
        prior = self._load_operation({'operationUuid': operation_uuid}) if operation_uuid else None
        prior_policy = prior.get('policy') if isinstance(prior, dict) else None
        retained_ksm_service_clear = (
            policy.get('ksm') not in (None, {}) and isinstance(prior_policy, dict) and
            any(isinstance(prior_policy.get(section), dict) and
                isinstance(prior_policy[section].get('enabled'), bool) and
                'enabled' not in (policy.get(section) or {})
                for section in ('zram', 'writeback')))
        if policy.get('ksm') not in (None, {}) and not retained_ksm_service_clear:
            return None
        prior_state = ((prior.get('readback') or {}).get('state')
                       if isinstance(prior, dict) and isinstance(prior.get('readback'), dict)
                       else None)
        # Recent fail-closed applies keep all service observations under
        # state.sections; older journals used capacity/cpu/tuning directly.
        # Accept both layouts without weakening the receipt checks below.
        prior_sections = (prior_state.get('sections')
                          if isinstance(prior_state, dict) and
                          isinstance(prior_state.get('sections'), dict)
                          else prior_state)
        prior_writeback = (prior_policy.get('writeback')
                           if isinstance(prior_policy, dict) else None)
        target_writeback = policy.get('writeback')
        target_ksm_only_clear = (
            command.get('action') == 'apply' and command.get('scope') == 'Host' and
            command.get('hostUuid') == self._load_host_uuid() and
            command.get('resourceUuid') == command.get('hostUuid') and
            policy == {'schemaVersion': 1, 'ksm': {}})
        if (isinstance(prior, dict) and isinstance(prior_state, dict) and
                prior_state.get('ksmOnly') is True and
                isinstance(prior_policy, dict) and
                isinstance(prior_writeback, dict) and
                set(prior_writeback) == set(('enabled', 'backendResourceUuid',
                                             'backendCapacityBytes')) and
                prior_writeback.get('enabled') is False and
                isinstance(target_writeback, dict) and
                target_writeback == prior_writeback and
                self._policy_mode(command) == 'effective' and
                policy.get('ksm') in (None, {})):
            # A completed cold preparation may be retained as disabled
            # backend metadata in the active KSM-only record. Keep the
            # generic ownership predicate strict; use the existing complete
            # no-pool/preparation proof to authorize only this exact clear.
            proof = {}
            if not self._first_use_no_pool_verified(
                    command, backend_preparation_out=proof):
                raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_INVALID')
            preparation = proof.get('backendPreparation')
            if (not isinstance(preparation, dict) or
                    not isinstance(preparation.get('record'), dict) or
                    not isinstance(preparation.get('operationUuid'), STRING_TYPES)):
                raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_INVALID')
            prior_readback = prior.get('readback')
            prior_ack = (prior_readback.get('ksmReadback')
                         if isinstance(prior_readback, dict) else None)
            if self._ksm_proof_policy(
                    prior_ack, prior.get('desiredRevision')) is None:
                raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_INVALID')
            current_ack = self._managed_ksm_clear_ack(prepared_backend={
                'operationUuid': preparation['operationUuid'],
                'record': preparation['record'],
                'bootId': self._current_boot_id(),
                'resourceUuid': prior_writeback.get('backendResourceUuid'),
                'capacityBytes': prior_writeback.get('backendCapacityBytes'),
            })
            if current_ack is None or current_ack != prior_ack:
                raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_INVALID')
            if context_holder is not None:
                context_holder['preparedKsmClear'] = {'priorKsmAck': current_ack}
            return None
        if (not isinstance(prior_policy, dict) or not isinstance(prior_state, dict) or
                not isinstance(prior_sections, dict) or
                not any(key in prior_sections for key in ('capacity', 'cpu', 'tuning')) or
                not any(prior_policy.get(key) for key in ('zram', 'writeback'))):
            if retained_ksm_service_clear:
                raise RuntimeError('MIXED_CLEAR_PRIOR_SERVICE_JOURNAL_INVALID')
            return None

        # This is KSM ownership proof only; it deliberately does not promote
        # the Host to ksmOnly. The helper still checks the complete active
        # journal/native/config identity contract.
        prior_ksm = self._managed_ksm_clear_ack(require_ksm_only=False)
        if prior_ksm is None:
            raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_INVALID')
        prior_readback = prior.get('readback') or {}
        if (prior_readback.get('success') is not True or
                prior_readback.get('status') != 'Succeeded' or
                prior_readback.get('appliedRevision') != prior.get('desiredRevision')):
            raise RuntimeError('MIXED_CLEAR_PRIOR_SERVICE_JOURNAL_INVALID')

        compact_prior_state = {key: prior_sections[key] for key in
                               ('capacity', 'cpu', 'tuning') if key in prior_sections}
        prior_evidence = prior_state.get('mixedClearEvidence')
        prior_postflight = (prior_evidence.get('postflight')
                            if isinstance(prior_evidence, dict) else None)
        if (isinstance(prior_postflight, dict) and
                isinstance(prior_evidence, dict) and
                prior_evidence.get('complete') is True and
                prior_evidence.get('operationUuid') == operation_uuid):
            prior_capacity_state = prior_postflight.get('capacity')
            prior_cpu_state = prior_postflight.get('cpu')
            if isinstance(prior_capacity_state, dict) and isinstance(prior_cpu_state, dict):
                cap_revision = prior_capacity_state.get('revision')
                cpu_revision = prior_cpu_state.get('revision')
                if (isinstance(cap_revision, INTEGER_TYPES) and not isinstance(cap_revision, bool) and
                        isinstance(cpu_revision, INTEGER_TYPES) and not isinstance(cpu_revision, bool) and
                        cpu_revision == cap_revision):
                    compact_prior_state['hostPolicyRevision'] = cap_revision

        context = {'operationUuid': command.get('operationUuid'),
                   'priorOperationUuid': operation_uuid,
                   'priorPolicy': prior_policy,
                   # Keep evidence bounded across successive mixed clears:
                   # never nest the previous operation's mixedClearEvidence.
                   'priorState': compact_prior_state,
                   'preflight': {}, 'writes': {}, 'writeAttempts': {}, 'postflight': {},
                   'ksmReadback': None, 'priorKsmAck': prior_ksm}
        if context_holder is not None:
            context_holder['context'] = context
        # Read all three current control sections through their real GET APIs.
        # A failed first read short-circuits before all writes.
        for action, section in (('capacity-state', 'capacity'),
                                ('host-cpu-state', 'cpu'),
                                ('tuning-state', 'tuning')):
            try:
                value = self.service_call(action, {})
            except Exception as exc:
                context['preflight'][section] = {'transportError': str(exc)}
                raise RuntimeError('MIXED_CLEAR_SERVICE_PREFLIGHT_UNKNOWN')
            context['preflight'][section] = value
            self._strict_service_success(action, value)

        preflight_capacity = context['preflight']['capacity']
        capacity_desired = preflight_capacity.get('desired')
        capacity_configured = (capacity_desired.get('configured')
                               if isinstance(capacity_desired, dict) else None)
        prepared_disabled_prior = (
            target_ksm_only_clear and isinstance(prior, dict) and
            prior.get('stage') == 'APPLIED' and prior.get('action') == 'apply' and
            prior.get('policyMode', 'effective') == 'effective' and
            prior.get('hostUuid') == self._load_host_uuid() and
            prior.get('bootId') == self._current_boot_id() and
            isinstance(prior.get('readback'), dict) and
            prior['readback'].get('success') is True and
            prior['readback'].get('status') == 'Succeeded' and
            prior['readback'].get('appliedRevision') == prior.get('desiredRevision') and
            self._strict_service_match(prior.get('applyEvidence'), prior.get('readback')) and
            self._strict_service_match(prior.get('readback'), prior.get('applyEvidence')) and
            isinstance(prior_policy, dict) and
            type(prior_policy.get('schemaVersion')) in INTEGER_TYPES and
            prior_policy.get('schemaVersion') == 1 and
            prior.get('policyHash') == self._policy_digest(prior_policy) and
            isinstance(prior_policy.get('zram'), dict) and
            prior_policy['zram'].get('enabled') is False and
            not any(key in prior_policy['zram']
                    for key in ('logicalCapacityBytes', 'ramLimitBytes')) and
            prior_policy.get('writeback') == {'enabled': False} and
            isinstance(prior_sections, dict) and
            'capacity' not in prior_sections and
            isinstance(capacity_configured, dict) and bool(capacity_configured) and
            preflight_capacity.get('apply_state') == 'BLOCKED' and
            preflight_capacity.get('reason') == 'NATIVE_POOL_UNQUALIFIED' and
            'effective_logical_bytes' in preflight_capacity and
            preflight_capacity.get('effective_logical_bytes') is None and
            'effective_physical_limit_bytes' in preflight_capacity and
            preflight_capacity.get('effective_physical_limit_bytes') is None)
        if preflight_capacity.get('apply_state') == 'APPLIED':
            for field in ('effective_logical_bytes', 'effective_physical_limit_bytes'):
                value = preflight_capacity.get(field)
                if (field not in preflight_capacity or
                        not isinstance(value, INTEGER_TYPES) or isinstance(value, bool) or
                        value < 0):
                    raise RuntimeError('MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN')
        elif (not self._is_unconfigured_capacity_state(preflight_capacity) and
              not prepared_disabled_prior):
            raise RuntimeError('MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN')

        receipts = context['priorState']
        prior_zram = prior_policy.get('zram') or {}
        prior_writeback = prior_policy.get('writeback') or {}
        cap_receipt = receipts.get('capacity')
        cpu_receipt = receipts.get('cpu')
        tuning_receipt = receipts.get('tuning')
        if isinstance(cap_receipt, dict):
            self._strict_service_success('capacity', cap_receipt)
        if isinstance(cpu_receipt, dict):
            if cpu_receipt.get('request_id') != '%s-cpu' % operation_uuid:
                raise RuntimeError('MIXED_CLEAR_PRIOR_CPU_RECEIPT_MISMATCH')
            self._strict_service_success('host-cpu', cpu_receipt)
        if isinstance(tuning_receipt, dict):
            self._strict_service_success('apply', tuning_receipt)
        host_revisions = []
        for name, receipt in (('capacity', cap_receipt), ('cpu', cpu_receipt)):
            if isinstance(receipt, dict):
                rev = receipt.get('revision')
                if not isinstance(rev, INTEGER_TYPES) or isinstance(rev, bool) or rev < 0:
                    raise RuntimeError('MIXED_CLEAR_PRIOR_HOST_REVISION_UNKNOWN')
                host_revisions.append(rev)
        if not host_revisions:
            prior_host_revision = receipts.get('hostPolicyRevision')
            if (not isinstance(prior_host_revision, INTEGER_TYPES) or
                    isinstance(prior_host_revision, bool) or prior_host_revision < 0):
                raise RuntimeError('MIXED_CLEAR_PRIOR_HOST_REVISION_UNKNOWN')
            host_revisions.append(prior_host_revision)
        final_host_revision = max(host_revisions)
        for section in ('capacity', 'cpu'):
            revision = context['preflight'][section].get('revision')
            if (not isinstance(revision, INTEGER_TYPES) or isinstance(revision, bool) or
                    revision != final_host_revision):
                raise RuntimeError('MIXED_CLEAR_PRIOR_HOST_REVISION_MISMATCH')

        if isinstance(cap_receipt, dict):
            zram_capacity = {}
            if 'logicalCapacityBytes' in prior_zram:
                zram_capacity['effective_logical_bytes'] = prior_zram['logicalCapacityBytes']
            if 'ramLimitBytes' in prior_zram:
                zram_capacity['effective_physical_limit_bytes'] = prior_zram['ramLimitBytes']
            if (not zram_capacity or
                    not self._strict_service_match(context['preflight']['capacity'], zram_capacity) or
                    context['preflight']['capacity'].get('apply_state') != 'APPLIED'):
                raise RuntimeError('MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN')
        if isinstance(cpu_receipt, dict):
            expected_cpu = {}
            if 'enabled' in prior_zram:
                expected_cpu['efficiency_enabled'] = bool(
                    prior_zram['enabled'] or (tuning_receipt.get('settings') or {}).get(
                        'writeback', {}).get('enabled', False))
            elif prior_writeback.get('enabled') is True:
                expected_cpu['efficiency_enabled'] = True
            for product, native in (('cpuThresholdPercent', 'idle_cpu_threshold_percent'),
                                    ('cpuHoldSeconds', 'idle_duration_seconds')):
                if product in prior_zram:
                    expected_cpu[native] = prior_zram[product]
            if not expected_cpu or not self._strict_service_match(
                    context['preflight']['cpu'], expected_cpu):
                raise RuntimeError('MIXED_CLEAR_PRIOR_CPU_UNKNOWN')
        if (not isinstance(tuning_receipt, dict) or
                not isinstance(tuning_receipt.get('settings'), dict)):
            raise RuntimeError('MIXED_CLEAR_PRIOR_TUNING_UNKNOWN')
        tuning_revision = tuning_receipt.get('revision')
        current_tuning_revision = context['preflight']['tuning'].get('revision')
        if (not isinstance(tuning_revision, INTEGER_TYPES) or isinstance(tuning_revision, bool) or
                not isinstance(current_tuning_revision, INTEGER_TYPES) or
                isinstance(current_tuning_revision, bool) or
                current_tuning_revision != tuning_revision or
                not self._strict_service_match(context['preflight']['tuning'].get('settings'),
                                               tuning_receipt['settings'])):
            raise RuntimeError('MIXED_CLEAR_PRIOR_TUNING_MISMATCH')
        if (context['preflight']['capacity'].get('apply_state') != 'APPLIED' and
                not self._mixed_clear_unconfigured_capacity_allowed(command, context) and
                not prepared_disabled_prior):
            # A BLOCKED/unconfigured capacity is acceptable only for a truly
            # disabled, unmanaged policy. The narrowly identified KSM-only
            # clear above is also safe without a pool: it validates the full
            # prior/current CPU and tuning receipts and carries only the
            # already verified native KSM acknowledgment forward.
            raise RuntimeError('MIXED_CLEAR_PRIOR_CAPACITY_UNKNOWN')
        if prepared_disabled_prior:
            if context_holder is not None:
                context_holder['preparedKsmClear'] = {'priorKsmAck': prior_ksm}
            return None
        return context

    @staticmethod
    def _is_unconfigured_capacity_state(value):
        return (isinstance(value, dict) and
                value.get('apply_state') == 'BLOCKED' and
                value.get('reason') == 'CAPACITY_NOT_CONFIGURED' and
                all(key in value and value[key] is None for key in
                    ('desired', 'effective_logical_bytes',
                     'effective_physical_limit_bytes')))

    def _mixed_clear_unconfigured_capacity_allowed(self, command, context,
                                                   post_capacity=None, post_cpu=None,
                                                   post_tuning=None):
        """Recognize only the explicit disabled/no-capacity management case."""
        policy = command.get('policy') or {}
        zram = policy.get('zram') or {}
        writeback = policy.get('writeback') or {}
        prior_policy = context.get('priorPolicy') or {}
        prior_zram = prior_policy.get('zram') or {}
        prior_writeback = prior_policy.get('writeback') or {}
        prior_state = context.get('priorState') or {}
        capacity = (context.get('preflight') or {}).get('capacity')
        cpu = (context.get('preflight') or {}).get('cpu')
        tuning = (context.get('preflight') or {}).get('tuning')
        tuning_settings = tuning.get('settings') if isinstance(tuning, dict) else None
        prior_capacity_managed = any(key in prior_zram for key in
                                     ('logicalCapacityBytes', 'ramLimitBytes'))
        target_has_capacity = any(key in zram for key in
                                  ('logicalCapacityBytes', 'ramLimitBytes'))
        if not (zram.get('enabled') is False and writeback.get('enabled') is False and
                prior_zram.get('enabled') is False and prior_writeback.get('enabled') is False and
                not target_has_capacity and not prior_capacity_managed and
                'capacity' not in prior_state and 'capacity' not in context.get('writes', {}) and
                self._is_unconfigured_capacity_state(capacity) and
                isinstance(cpu, dict) and cpu.get('efficiency_enabled') is False and
                isinstance(tuning_settings, dict) and
                isinstance(tuning_settings.get('writeback'), dict) and
                tuning_settings['writeback'].get('enabled') is False):
            return False
        if post_capacity is not None or post_cpu is not None or post_tuning is not None:
            settings = post_tuning.get('settings') if isinstance(post_tuning, dict) else None
            if not (self._is_unconfigured_capacity_state(post_capacity) and
                    isinstance(post_cpu, dict) and
                    post_cpu.get('efficiency_enabled') is False and
                    isinstance(settings, dict) and
                    isinstance(settings.get('writeback'), dict) and
                    settings['writeback'].get('enabled') is False):
                return False
        return True

    def _verify_mixed_clear_postflight(self, command, context):
        """Prove the target after Go updates, using strict typed ABI checks."""
        policy = command.get('policy') or {}
        zram = policy.get('zram') or {}
        wb = policy.get('writeback') or {}
        expected_cpu = {}
        if 'enabled' in zram:
            expected_cpu['efficiency_enabled'] = bool(zram['enabled'] or wb.get(
                'enabled', context['preflight']['tuning']['settings'].get(
                    'writeback', {}).get('enabled', False)))
        elif wb.get('enabled') is True:
            expected_cpu['efficiency_enabled'] = True
        else:
            expected_cpu['efficiency_enabled'] = context['preflight']['cpu']['efficiency_enabled']
        for product, native in (('cpuThresholdPercent', 'idle_cpu_threshold_percent'),
                                ('cpuHoldSeconds', 'idle_duration_seconds')):
            if product in zram:
                expected_cpu[native] = zram[product]
            else:
                expected_cpu[native] = context['preflight']['cpu'][native]
        expected_capacity = {}
        if 'logicalCapacityBytes' in zram:
            expected_capacity['effective_logical_bytes'] = zram['logicalCapacityBytes']
        else:
            expected_capacity['effective_logical_bytes'] = context['preflight']['capacity'].get(
                'effective_logical_bytes')
        if 'ramLimitBytes' in zram:
            expected_capacity['effective_physical_limit_bytes'] = zram['ramLimitBytes']
        else:
            expected_capacity['effective_physical_limit_bytes'] = context['preflight']['capacity'].get(
                'effective_physical_limit_bytes')
        cap_write = context['writes'].get('capacity')
        cpu_write = context['writes'].get('host-cpu')
        tuning_write = context['writes'].get('apply')
        cap_pre = context['preflight'].get('capacity')
        cpu_pre = context['preflight'].get('cpu')
        tuning_pre = context['preflight'].get('tuning')
        final_host_revision = None
        if cap_write is not None:
            self._strict_service_success('capacity', cap_write)
            base_revision = cap_pre.get('revision')
            revision = cap_write.get('revision')
            if (not isinstance(base_revision, INTEGER_TYPES) or isinstance(base_revision, bool) or
                    not isinstance(revision, INTEGER_TYPES) or isinstance(revision, bool) or
                    revision != base_revision + 1 or
                    cap_write.get('apply_state') != 'APPLIED' or
                    not self._strict_service_match(cap_write, expected_capacity)):
                raise RuntimeError('MIXED_CLEAR_CAPACITY_WRITE_RECEIPT_INVALID')
            final_host_revision = revision
        if cpu_write is not None:
            self._strict_service_success('host-cpu', cpu_write)
            base_revision = (final_host_revision if final_host_revision is not None
                             else cpu_pre.get('revision'))
            revision = cpu_write.get('revision')
            if (not isinstance(base_revision, INTEGER_TYPES) or isinstance(base_revision, bool) or
                    not isinstance(revision, INTEGER_TYPES) or isinstance(revision, bool) or
                    revision != base_revision + 1 or
                    cpu_write.get('request_id') != '%s-cpu' % command.get('operationUuid')):
                raise RuntimeError('MIXED_CLEAR_CPU_WRITE_RECEIPT_INVALID')
            final_host_revision = revision
        if final_host_revision is None:
            final_host_revision = cap_pre.get('revision')
        if (not isinstance(final_host_revision, INTEGER_TYPES) or
                isinstance(final_host_revision, bool)):
            raise RuntimeError('MIXED_CLEAR_HOST_POLICY_REVISION_UNKNOWN')
        if (not isinstance(tuning_write, dict)):
            raise RuntimeError('MIXED_CLEAR_TUNING_WRITE_MISSING')
        self._strict_service_success('apply', tuning_write)
        tuning_base_revision = tuning_pre.get('revision')
        tuning_revision = tuning_write.get('revision')
        if (not isinstance(tuning_base_revision, INTEGER_TYPES) or isinstance(tuning_base_revision, bool) or
                not isinstance(tuning_revision, INTEGER_TYPES) or isinstance(tuning_revision, bool) or
                tuning_revision != tuning_base_revision + 1 or
                not isinstance(tuning_write.get('settings'), dict)):
            raise RuntimeError('MIXED_CLEAR_TUNING_WRITE_RECEIPT_INVALID')

        capacity = self.service_call('capacity-state', {})
        context['postflight']['capacity'] = capacity
        self._strict_service_success('capacity-state', capacity)
        cpu = self.service_call('host-cpu-state', {})
        context['postflight']['cpu'] = cpu
        self._strict_service_success('host-cpu-state', cpu)
        if (capacity.get('revision') != final_host_revision or
                cpu.get('revision') != final_host_revision):
            raise RuntimeError('MIXED_CLEAR_HOST_POLICY_POSTREVISION_MISMATCH')
        if not self._strict_service_match(cpu, expected_cpu):
            raise RuntimeError('MIXED_CLEAR_CPU_POSTREADBACK_MISMATCH')
        tuning = self._service_request('tuning-state', command)
        context['postflight']['tuning'] = tuning
        self._strict_service_success('tuning-state', tuning)
        if (tuning.get('revision') != tuning_revision or
                not self._strict_service_match(tuning.get('settings'), tuning_write.get('settings'))):
            raise RuntimeError('MIXED_CLEAR_TUNING_POSTREADBACK_MISMATCH')
        capacity_applied = (self._strict_service_match(capacity, expected_capacity) and
                            capacity.get('apply_state') == 'APPLIED')
        if not capacity_applied and not self._mixed_clear_unconfigured_capacity_allowed(
                command, context, post_capacity=capacity, post_cpu=cpu, post_tuning=tuning):
            raise RuntimeError('MIXED_CLEAR_CAPACITY_POSTREADBACK_MISMATCH')
        context['complete'] = True
        return context

    @kvmagent.replyerror
    def migration_hold(self, req):
        return self._reply(self._dispatch('migration-hold', self._request_body(req)))

    @kvmagent.replyerror
    def vm_efficiency(self, req):
        command = self._request_body(req)
        command['scope'] = 'vm'
        # bind/deny are platform verbs; Go receives auto/allow/deny through
        # the same generation-fenced VM efficiency endpoint.
        if command.get('action') == 'revoke':
            command['participation'] = 'deny'
            # Revoke is a lifecycle cleanup after the source VM stopped or
            # disappeared. It must never be turned into a new VM deny request;
            # the old commercial permit, when supplied by a legacy caller,
            # must not change this local journal-only behavior.
            try:
                self._save_vm_binding(command)
            except (IOError, OSError):
                return self._reply({'success': False, 'status': 'Unknown',
                                    'state': {'phase': 'UNKNOWN'},
                                    'reasonCode': 'VM_BINDING_JOURNAL_UNAVAILABLE',
                                    'operationUuid': command.get('operationUuid')})
            return self._reply({'success': True, 'status': 'Succeeded',
                                'state': {'phase': 'REVOKED', 'inventoryComplete': False},
                                'operationUuid': command.get('operationUuid')})
        elif command.get('action') == 'bind':
            command['participation'] = command.get('participation', 'allow')
        result = self.apply(command)
        if result.get('success') and command.get('action') == 'bind':
            try:
                self._save_vm_binding(command)
            except (IOError, OSError):
                # Native VM policy may already be applied; do not report a
                # false success when the durable Agent binding is missing.
                result = {'success': False, 'status': 'Unknown',
                          'state': {'phase': 'UNKNOWN'},
                          'reasonCode': 'VM_BINDING_JOURNAL_UNAVAILABLE',
                          'operationUuid': command.get('operationUuid')}
        return self._reply(result)

    def apply(self, command):
        """Apply a policy and preserve UNKNOWN on transport/service failure."""
        if isinstance(command, dict) and command.get('action') == 'prepareWritebackBackend':
            return self._prepare_backend_maintenance(command)
        if isinstance(command, dict) and command.get('action') == 'prepareZramPool':
            return self._prepare_zram_pool(command)
        if isinstance(command, dict) and command.get('action') == 'recoverUncertain':
            return self._recover_uncertain_activation(command)
        if self._is_safe_control_action(command):
            return self._apply_safe_control_action(command)
        operation_lock = None
        mixed_context_holder = {}
        try:
            # All validation and identity checks precede any KSM or
            # service side effect.
            self._operation_request(command)
            # bool is an int subclass in Python. Reject malformed revision
            # values before capability discovery, native KSM probing, or any
            # operation-journal mutation; otherwise True can be applied as 1.
            for key, minimum in (('desiredRevision', 1), ('expectedRevision', 0)):
                if key in command:
                    revision = command[key]
                    if (not isinstance(revision, INTEGER_TYPES) or
                            isinstance(revision, bool) or revision < minimum):
                        raise ValueError('INVALID_POLICY_REVISION:%s' % key)
            host_uuid = self._load_host_uuid()
            if not host_uuid or command.get('hostUuid') != host_uuid:
                raise ValueError('HOST_IDENTITY_UNKNOWN')
            # A completed operation is idempotent even when a later drain
            # fence is now active.  Return its durable receipt before asking
            # for a fresh maintenance proof; this also keeps the proof out of
            # any retry-time mutation path.
            journal_state, journal_record = self._operation_file_state(command['operationUuid'])
            if journal_state in ('corrupt', 'unreadable'):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': command['operationUuid']}
            existing = journal_record
            if journal_state == 'present' and not isinstance(existing, dict):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': command['operationUuid']}
            try:
                policy_mode = self._policy_mode(command)
            except ValueError as exc:
                if isinstance(existing, dict):
                    return {'success': False, 'status': 'Failed', 'state': {'phase': 'FAILED'},
                            'reason': str(exc), 'reasonCode': 'INVALID_POLICY',
                            'operationUuid': command['operationUuid']}
                raise
            if (isinstance(existing, dict) and
                    existing.get('policyMode', 'effective') != policy_mode):
                # A retry may not relabel or overwrite a prior operation proof.
                return {'success': False, 'status': 'Failed', 'state': {'phase': 'FAILED'},
                        'reason': 'OPERATION_UUID_REUSE',
                        'reasonCode': 'OPERATION_UUID_REUSE',
                        'operationUuid': command['operationUuid']}
            if (isinstance(existing, dict) and
                    existing.get('stage') == 'NOT_ISSUED' and
                    isinstance(existing.get('readback'), dict)):
                return existing['readback']
            if (isinstance(existing, dict) and
                    existing.get('requestHash') == self._operation_hash(command) and
                    existing.get('stage') == 'APPLIED' and
                    isinstance(existing.get('readback'), dict)):
                return existing['readback']
            if (str(command.get('scope', '')).lower() != 'vm' and
                    self._host_control_blocks_policy(command)):
                raise ValueError('CONTROL_PAUSED_RESUME_REQUIRED')
            active_control = self._get_active_control()
            active_control_record = self._load_operation({'operationUuid': active_control}) if active_control else None
            maintenance_apply = bool(
                str(command.get('scope', '')).lower() != 'vm' and
                isinstance(active_control_record, dict) and
                active_control_record.get('action') == 'drain' and
                active_control_record.get('stage') == 'APPLIED' and
                self._maintenance_recovery_proof(command))
            if maintenance_apply and (command.get('policy') or {}).get('zram', {}).get('enabled') is not True:
                raise ValueError('MAINTENANCE_APPLY_REQUIRES_ENABLED_ZRAM_POLICY')
            # The service is installed inactive; the first ZRAM enable starts it.
            if ((command.get('policy') or {}).get('zram') or {}).get('enabled') is True:
                self._activate_managed_service()
            # Discover facts before any validation or side effect.  Legacy
            # KSM remains queryable/applicable on older hosts, while new
            # ZStack-managed optimisation is explicitly rejected unless the
            # h84r/x86_64/4 KiB ABI is complete.
            capabilities = self.discover_capabilities()
            if (self._requires_new_optimization(command) and
                    not capabilities.get('supported')):
                raise ValueError('UNSUPPORTED_HOST_CAPABILITY:%s' %
                                 capabilities.get('reasonCode', 'UNKNOWN'))
            self._validate_requested_capabilities(command, capabilities)
            self._restore_default_capacity_sides(command)
            self._fill_resolved_capacity_defaults(command)
            self._validate_policy(command.get('policy') or {})
            # A strict VM deny is a safety/rebind operation: it only removes
            # participation and cannot carry host optimisation fields.
            self._validate_backend_resource(command)
            prior, claimed = self._claim_operation(command)
            if claimed:
                operation_lock = prior
            elif prior is not None:
                return prior
            else:
                return {'success': False, 'status': 'Unknown', 'state': {},
                        'reasonCode': 'OPERATION_CONCURRENT',
                        'operationUuid': command.get('operationUuid')}
            cold_fence_error = (self._validate_cold_ksm_partial_fence(command) or
                                self._validate_confirmed_ksm_reconnect(command))
            if cold_fence_error is not None:
                self._release_operation(operation_lock)
                operation_lock = None
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': cold_fence_error,
                        'operationUuid': command.get('operationUuid')}
            if not self._record_operation(command, 'PREPARING'):
                return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': command.get('operationUuid')}
            if str(command.get('scope', '')).lower() == 'vm':
                # VM participation is a service-owned policy, independent of
                # host KSM/ZRAM policy.  Never let the KSM-only shortcut hide
                # this request.
                # It must not acquire a host-wide control lock or replace the host
                # active-control fence: a VM bind cannot fence host policy.
                vm_command = dict(command)
                vm_command['_resource_uuid'] = command['resourceUuid']
                vm_command['expectedRevision'] = self._read_service_revision(
                    'vm-policy-state', vm_command)['revision']
                result = self._service_request('vm-policy', vm_command)
                normalized = self._normalize_response(result, 'apply', command)
                if normalized.get('success') and normalized.get('status') == 'Succeeded':
                    normalized['appliedRevision'] = command.get('desiredRevision')
                recorded = self._record_operation(
                    command, 'APPLIED' if normalized.get('status') == 'Succeeded' else 'UNKNOWN',
                    normalized)
                if normalized.get('success') and not recorded:
                    normalized['success'] = False
                    normalized['status'] = 'Unknown'
                    normalized['state'] = {'phase': 'UNKNOWN'}
                    normalized['reasonCode'] = 'OPERATION_JOURNAL_UNAVAILABLE'
                return normalized
            if ((command.get('policy') or {}).get('zram') or {}).get('enabled') is True:
                self._archive_foreign_host_history()
            if not self._first_use_prior_fence_clear(command['operationUuid']):
                raise RuntimeError('FIRST_ZRAM_PRIOR_OPERATION_UNRESOLVED')
            try:
                first_zram_use = self._prepare_first_zram_use(command)
            except FirstZramConfigRejected as exc:
                # Only a positively read, non-vendor config is a definitive
                # no-effect rejection. Missing files, unknown identity/state,
                # and every post-write outcome remain on the Unknown path.
                rejection = {'success': False, 'status': 'Failed',
                             'state': {'phase': 'FAILED'},
                             'reasonCode': str(exc),
                             'operationUuid': command.get('operationUuid')}
                if self._record_operation(command, 'REJECTED', rejection):
                    return rejection
                return {'success': False, 'status': 'Unknown',
                        'state': {'phase': 'UNKNOWN'},
                        'reasonCode': 'OPERATION_JOURNAL_UNAVAILABLE',
                        'operationUuid': command.get('operationUuid')}
            if first_zram_use and not self._mark_first_zram_policy_started(command):
                raise RuntimeError('FIRST_ZRAM_POLICY_INTENT_UNAVAILABLE')
            policy = command.get('policy') or {}
            zram_policy = policy.get('zram') or {}
            wb_policy = policy.get('writeback') or {}
            ksm_policy = policy.get('ksm')
            delta_ksm_untouched = (policy_mode == 'delta' and
                                   (ksm_policy is None or ksm_policy == {}))
            mixed_context = self._mixed_clear_context(command, mixed_context_holder)
            if delta_ksm_untouched:
                ksm_readback = None
            elif mixed_context is None:
                prepared_clear = mixed_context_holder.get('preparedKsmClear')
                ksm_readback = (self._apply_ksm_policy(command, clear_context=prepared_clear)
                                if prepared_clear is not None else
                                self._apply_ksm_policy(command))
            else:
                ksm_readback = self._apply_ksm_policy(command, clear_context=mixed_context)
            if mixed_context is not None:
                mixed_context['ksmReadback'] = ksm_readback
            policy = command.get('policy') or {}
            zram = policy.get('zram') or {}
            writeback = policy.get('writeback') or {}
            explicit_zram_disable = ('enabled' in zram and not zram.get('enabled'))
            delta_has_service_policy = (policy_mode == 'delta' and
                                        (bool(zram) or bool(writeback)))
            if (not delta_has_service_policy and
                    not zram.get('enabled', False) and not writeback.get('enabled', False)
                    and mixed_context is None
                    and not (explicit_zram_disable and os.path.exists(self.socket_path))):
                # KSM-only is valid and must not require a loaded ZRAM pool.
                # Stamp the durable marker only after _apply_ksm_policy has
                # completed its native revisioned readback.  A policy shape
                # alone must never make a later service failure look safe.
                state = {'source': 'ksmtuned'}
                if isinstance(ksm_readback, dict):
                    state['ksmOnly'] = True
                result = {'status': 'Succeeded', 'state': state}
            else:
                if mixed_context is None:
                    result = self._apply_service_policy(command)
                else:
                    result = self._apply_service_policy(command,
                                                        receipt_sink=mixed_context)
                if mixed_context is not None:
                    if result.get('status') != 'Succeeded':
                        raise RuntimeError('MIXED_CLEAR_SERVICE_APPLY_UNCONFIRMED')
                    mixed_context = self._verify_mixed_clear_postflight(
                        command, mixed_context)
                    result.setdefault('state', {})['mixedClearEvidence'] = mixed_context
            maintenance_activation_pending = (
                maintenance_apply and isinstance(result, dict) and
                (result.get('status') == 'Succeeded' or
                 (result.get('status') == 'Draining' and
                  result.get('asyncSections') == ['capacity'])))
            if maintenance_activation_pending:
                # Revalidate the empty-pool maintenance proof after every
                # requested setting has been written but before Go is opened.
                try:
                    native_before = self._service_request('state', {})
                    if not self._maintenance_recovery_proof(command, live_state=native_before):
                        result = {'success': False, 'status': 'Failed',
                                  'reasonCode': 'MAINTENANCE_PROOF_CHANGED_BEFORE_ACTIVATION',
                                  'state': {'phase': 'FAILED'},
                                  'operationUuid': command.get('operationUuid')}
                    else:
                        policy_readback = self._maintenance_policy_intent_readback(command, result)
                        if policy_readback.get('complete') is not True:
                            result = {'success': False, 'status': 'Failed',
                                      'reasonCode': 'MAINTENANCE_POLICY_READBACK_INCOMPLETE',
                                      'state': {'phase': 'FAILED', 'policyReadback': policy_readback},
                                      'operationUuid': command.get('operationUuid')}
                        else:
                            # A pool preparation has just restarted the service.
                            self._await_safe_host_sample()
                            activation_intent = self._persist_maintenance_activation_intent(
                                command, command['maintenanceProof'])
                            if activation_intent is None:
                                result = {'success': False, 'status': 'Unknown',
                                          'reasonCode': 'MAINTENANCE_ACTIVATION_INTENT_UNAVAILABLE',
                                          'state': {'phase': 'UNKNOWN'},
                                          'operationUuid': command.get('operationUuid')}
                            else:
                                request = activation_intent['request']
                                activation_request = {
                                    'requestId': request['request_id'],
                                    'expectedControlOperationUuid': request['expected_control_operation_uuid'],
                                    'expectedHostBootId': request['expected_host_boot_id'],
                                    'expectedPoolGeneration': request['expected_pool_generation']}
                                self._service_request('lifecycle-activate-maintenance', activation_request)
                                result = self._finish_maintenance_activation(command, activation_intent, wait=True)
                except Exception as exc:
                    # The durable ACTIVATING journal suppresses retry. An
                    # ambiguous service response is resolved only by reconcile.
                    logger.warn('maintenance activation outcome is unknown: %s', exc)
                    result = {'success': False, 'status': 'Unknown',
                              'reasonCode': 'MAINTENANCE_ACTIVATION_RESULT_UNKNOWN',
                              'state': {'phase': 'ACTIVATING'},
                              'operationUuid': command.get('operationUuid')}
            if not isinstance(result, dict):
                return {'success': False, 'state': 'UNKNOWN',
                        'reasonCode': 'INVALID_SERVICE_RESPONSE'}
            if ksm_readback:
                result['ksmReadback'] = ksm_readback
            normalized = self._normalize_response(result, 'apply', command)
            # desiredRevision is the product policy generation.  A zram
            # service revision is an implementation detail and is retained in
            # readback rather than exposed as the applied product revision.
            if normalized.get('success') and normalized.get('status') == 'Succeeded':
                normalized['appliedRevision'] = command.get('desiredRevision')
                self._set_active_control(command['operationUuid'])
            operation_stage = 'APPLIED' if normalized.get('status') == 'Succeeded' else 'UNKNOWN'
            if (normalized.get('status') == 'Failed' and
                    isinstance(normalized.get('state'), dict) and
                    normalized['state'].get('activationRejected') is True):
                operation_stage = 'REJECTED'
            recorded = self._record_operation(command, operation_stage, normalized)
            if normalized.get('success') and not recorded:
                normalized['success'] = False
                normalized['status'] = 'Unknown'
                normalized['state'] = {'phase': 'UNKNOWN'}
                normalized['reasonCode'] = 'OPERATION_JOURNAL_UNAVAILABLE'
            return normalized
        except ValueError as exc:
            if str(exc) == 'OPERATION_UUID_REUSE':
                return {'success': False, 'status': 'Failed', 'state': {'phase': 'FAILED'},
                        'reason': str(exc), 'reasonCode': 'OPERATION_UUID_REUSE',
                        'operationUuid': command.get('operationUuid')}
            self._record_operation(command, 'REJECTED', {'reason': str(exc)})
            return {'success': False, 'status': 'Failed', 'state': {'phase': 'FAILED'},
                    'reason': str(exc), 'reasonCode': 'INVALID_POLICY',
                    'operationUuid': command.get('operationUuid')}
        except Exception as exc:
            mixed_context = mixed_context_holder.get('context')
            unknown_result = {'success': False, 'status': 'Unknown',
                              'state': {'phase': 'UNKNOWN'},
                              'operationUuid': command.get('operationUuid'),
                              'reason': str(exc)}
            if isinstance(mixed_context, dict):
                unknown_result['reasonCode'] = (
                    str(exc) if re.match(r'^[A-Z][A-Z0-9_]+$', str(exc))
                    else 'MIXED_CLEAR_RESULT_UNKNOWN')
                unknown_result['state']['mixedClearEvidence'] = mixed_context
                if isinstance(mixed_context.get('ksmReadback'), dict):
                    unknown_result['ksmReadback'] = mixed_context['ksmReadback']
                self._record_operation(command, 'UNKNOWN', unknown_result)
                logger.warn('mixed memory optimisation apply result is unknown: %s', exc)
                return unknown_result
            self._record_operation(command, 'UNKNOWN', {'reason': str(exc)})
            logger.warn('memory optimisation apply result is unknown: %s', exc)
            reason = str(exc)
            reason_code = reason if re.match(r'^[A-Z][A-Z0-9_]+$', reason) else 'MEMORY_RESULT_UNKNOWN'
            return {'success': False, 'status': 'Unknown', 'state': {'phase': 'UNKNOWN'},
                    'operationUuid': command.get('operationUuid'),
                    'reasonCode': reason_code}
        finally:
            self._release_operation(operation_lock)

    @staticmethod
    def _validate_policy(policy):
        def is_integer(value):
            return isinstance(value, INTEGER_TYPES) and not isinstance(value, bool)

        def validate_positive_integer(section, key, value):
            if not is_integer(value) or value < 1:
                raise ValueError('invalid %s %s' % (section, key))

        def validate_nonnegative_integer(section, key, value):
            if not is_integer(value) or value < 0:
                raise ValueError('invalid %s %s' % (section, key))

        def validate_number(section, key, value):
            # PSI is deliberately a fractional percentage.  Do not coerce it
            # to int here: 0.1 is a meaningful threshold in the service ABI.
            if isinstance(value, bool) or not isinstance(value, (int, float)) or \
                    math.isnan(value) or math.isinf(value) or value < 0 or value > 100:
                raise ValueError('invalid %s %s' % (section, key))

        ksm = policy.get('ksm') or {}
        allowed_ksm = {'enabled', 'zeroPagesEnabled', 'pagesToScan', 'sleepMillis'}
        unknown_ksm = set(ksm) - allowed_ksm
        if unknown_ksm:
            raise ValueError('unsupported KSM field: %s' % sorted(unknown_ksm)[0])
        for key in ('pagesToScan', 'sleepMillis'):
            if key in ksm:
                validate_positive_integer('KSM', key, ksm[key])
                if ksm[key] > 4294967295 or (key == 'sleepMillis' and ksm[key] < 10):
                    raise ValueError('KSM_NATIVE_VALUE_UNREPRESENTABLE: %s' % key)
        for key in ('enabled', 'zeroPagesEnabled'):
            if key in ksm and not isinstance(ksm[key], bool):
                raise ValueError('invalid KSM %s' % key)
        writeback = policy.get('writeback') or {}
        if writeback.get('enabled') and not writeback.get('backendResourceUuid'):
            raise ValueError('BACKEND_RESOURCE_UUID_REQUIRED')
        zram = policy.get('zram') or {}
        for key in ('logicalCapacityBytes', 'ramLimitBytes'):
            # None asks the service for its default capacity on that side.
            if zram.get(key) is not None:
                validate_positive_integer('ZRAM', key, zram[key])
        if 'cpuThresholdPercent' in zram and (not isinstance(zram['cpuThresholdPercent'], (int, float)) or
                                               zram['cpuThresholdPercent'] < 0 or
                                               zram['cpuThresholdPercent'] > 100):
            raise ValueError('invalid ZRAM cpuThresholdPercent')
        if 'cpuThresholdPercent' in zram:
            validate_number('ZRAM', 'cpuThresholdPercent', zram['cpuThresholdPercent'])
        if 'cpuHoldSeconds' in zram:
            validate_positive_integer('ZRAM', 'cpuHoldSeconds', zram['cpuHoldSeconds'])
        if 'selectionMode' in zram and zram['selectionMode'] not in ('all_running', 'list'):
            raise ValueError('invalid ZRAM selectionMode')
        if 'selectedVmUuids' in zram:
            uuids = zram['selectedVmUuids']
            if not isinstance(uuids, list) or any(not isinstance(item, STRING_TYPES) or not item for item in uuids):
                raise ValueError('invalid ZRAM selectedVmUuids')
        for key in ('hostCpuThresholdPercent', 'hostMemoryPsiThresholdPercent',
                    'hostIoPsiThresholdPercent'):
            if key in zram:
                validate_number('ZRAM', key, zram[key])
        for key in ('discoveryIntervalSeconds', 'discoveryTimeoutSeconds',
                    'discoveryTtlSeconds', 'hostSampleIntervalSeconds',
                    'hostSampleTtlSeconds', 'vmSampleIntervalSeconds',
                    'vmSampleTtlSeconds', 'reclaimBatchBytes', 'concurrency',
                    'reclaimSlowOperationSeconds', 'timeoutIsolationSlots',
                    'operationRecordBudgetBytes', 'startupObservationSeconds',
                    'operationIntervalSeconds'):
            if key in zram:
                validator = validate_nonnegative_integer if key in ('startupObservationSeconds', 'timeoutIsolationSlots') else validate_positive_integer
                validator('ZRAM', key, zram[key])
        for key in ('hostCpuGuardEnabled', 'hostMemoryPsiGuardEnabled',
                    'hostIoPsiGuardEnabled'):
            if key in zram and not isinstance(zram[key], bool):
                raise ValueError('invalid ZRAM %s' % key)
        if 'algorithm' in zram and (not isinstance(zram['algorithm'], STRING_TYPES) or
                                     not zram['algorithm']):
            raise ValueError('invalid ZRAM algorithm')
        for key in ('batchBytes', 'idleObservationSeconds', 'operationIntervalSeconds',
                    'slowOperationSeconds', 'noProgressLimit', 'backoffSeconds',
                    'ioErrorBackoffSeconds', 'metadataBudgetBytes',
                    'filesystemReserveBytes'):
            if key in writeback:
                validator = validate_nonnegative_integer if key == 'filesystemReserveBytes' else validate_positive_integer
                validator('writeback', key, writeback[key])
        if zram.get('enabled') and ('logicalCapacityBytes' not in zram or 'ramLimitBytes' not in zram):
            raise ValueError('ZRAM_CAPACITY_REQUIRED_WHEN_ENABLED')

    @staticmethod
    def _validate_requested_capabilities(command, capabilities):
        policy = command.get('policy') or {}
        ksm = policy.get('ksm') or {}
        zram = policy.get('zram') or {}
        writeback = policy.get('writeback') or {}
        missing = []
        driver = capabilities.get('zramDriver')
        accounting_unavailable = (
            isinstance(driver, dict) and driver.get('applicable') is True and
            driver.get('accountingSupported') is not True)
        if ksm.get('enabled') and not capabilities.get('ksm'):
            missing.append('ksm')
        if ksm.get('zeroPagesEnabled') and not capabilities.get('ksmZeroPages'):
            missing.append('ksmZeroPages')
        if zram.get('enabled') and (
                not capabilities.get('zram') or accounting_unavailable):
            missing.append('zram')
        if writeback.get('enabled') and not capabilities.get('writeback'):
            missing.append('writeback')
        if missing:
            raise ValueError('UNSUPPORTED_HOST_CAPABILITY:%s' % ','.join(missing))

    @staticmethod
    def _restore_default_capacity_sides(command):
        """MN names the service-default sides because JSON drops null fields."""
        sides = command.get('defaultCapacitySides')
        if sides is None:
            return
        if (not isinstance(sides, list) or
                any(side not in ('logicalCapacityBytes', 'ramLimitBytes') for side in sides)):
            raise ValueError('invalid defaultCapacitySides')
        policy = command.setdefault('policy', {})
        zram = policy.setdefault('zram', {})
        for side in sides:
            zram[side] = None

    @staticmethod
    def _native_capacity_value(value):
        # A side without a unit is resolved from the service default.
        return {} if value is None else {'bytes': value}

    @staticmethod
    def _adopt_default_capacity(zram, receipt):
        """Record the bytes the service resolved for a default capacity side."""
        desired = receipt.get('desired') if isinstance(receipt, dict) else None
        for key, resolved in (('logicalCapacityBytes', 'logical_resolved_bytes'),
                              ('ramLimitBytes', 'physical_resolved_bytes')):
            value = desired.get(resolved) if isinstance(desired, dict) else None
            if (key in zram and zram[key] is None and isinstance(value, INTEGER_TYPES) and
                    not isinstance(value, bool) and value > 0):
                zram[key] = value

    def _fill_resolved_capacity_defaults(self, command):
        """Fill omitted global ZRAM capacity from the service's current target."""
        policy = command.get('policy') or {}
        zram = policy.get('zram') or {}
        # The native capacity write needs both sides, so a single-side update
        # keeps the other side's current target.
        if str(command.get('scope', '')).lower() == 'vm' or not (
                zram.get('enabled') or 'logicalCapacityBytes' in zram or 'ramLimitBytes' in zram):
            return
        if 'logicalCapacityBytes' in zram and 'ramLimitBytes' in zram:
            return
        capacity = self.service_call('capacity-state', {})
        desired = capacity.get('desired') if isinstance(capacity, dict) else None
        logical = desired.get('logical_resolved_bytes') if isinstance(desired, dict) else None
        physical = desired.get('physical_resolved_bytes') if isinstance(desired, dict) else None
        if logical is None or physical is None:
            raise ValueError('CAPACITY_DEFAULT_UNKNOWN')
        zram.setdefault('logicalCapacityBytes', logical)
        zram.setdefault('ramLimitBytes', physical)
        policy['zram'] = zram
        command['policy'] = policy

    def _validate_backend_resource(self, command):
        writeback = ((command.get('policy') or {}).get('writeback') or {})
        if not writeback.get('enabled'):
            return
        resource_uuid = writeback.get('backendResourceUuid')
        if not resource_uuid:
            raise ValueError('BACKEND_RESOURCE_UUID_REQUIRED')

        # The resource UUID in the policy is only a reference. Before allowing
        # writeback, re-read both service views and independently probe the
        # current device. This intentionally fails closed if the service is
        # down, the ownership observation is stale, or the kernel device has
        # changed since it was prepared.
        host_uuid = self._load_host_uuid()
        if not host_uuid:
            raise ValueError('HOST_IDENTITY_UNKNOWN')
        if command.get('hostUuid') != host_uuid:
            raise ValueError('HOST_IDENTITY_MISMATCH')
        query = {'hostUuid': host_uuid}
        try:
            status = self._readonly_query('backend-state', query)
            detail = self._readonly_query('backend-view', query)
        except Exception:
            # A failed read-only preflight cannot prove the writeback resource
            # is invalid, nor that a later data-plane request failed. Preserve
            # the operation as UNKNOWN so callers can retry/reconcile instead
            # of reporting a definitive policy rejection.
            raise RuntimeError('BACKEND_SERVICE_OBSERVATION_UNAVAILABLE')

        backend = status.get('backend_resource') if isinstance(status, dict) else None
        if not isinstance(backend, dict):
            raise ValueError('NEEDS_OFFLINE_PREPARATION')
        generation = backend.get('resource_uuid')
        capacity = backend.get('capacity_bytes')
        fingerprint = backend.get('fingerprint')
        state = backend.get('state')
        if not generation or not capacity or not fingerprint:
            raise ValueError('NEEDS_OFFLINE_PREPARATION')
        if resource_uuid != generation:
            raise ValueError('BACKEND_RESOURCE_NOT_ACTIVE')
        if state not in ('PREPARED', 'ACTIVE'):
            raise ValueError('BACKEND_RESOURCE_NOT_ACTIVE')
        if (detail.get('claimed') is not True or
                detail.get('identity_qualified') is not True):
            raise ValueError('BACKEND_RESOURCE_IDENTITY_UNQUALIFIED')
        if detail.get('ownership_generation') != generation:
            raise ValueError('BACKEND_RESOURCE_OWNERSHIP_MISMATCH')

        requested_capacity = writeback.get('backendCapacityBytes')
        if requested_capacity is not None and requested_capacity != capacity:
            raise ValueError('BACKEND_CAPACITY_MISMATCH')
        if isinstance(capacity, bool) or not isinstance(capacity, INTEGER_TYPES) or capacity <= 0:
            raise ValueError('BACKEND_CAPACITY_UNKNOWN')

        observed = backend.get('observed_at')
        observed_epoch = self._backend_observation_epoch(observed)
        if observed_epoch is None:
            raise ValueError('BACKEND_RESOURCE_TIMESTAMP_UNKNOWN')
        now = time.time()
        if observed_epoch > now:
            raise ValueError('BACKEND_RESOURCE_TIMESTAMP_FUTURE')
        if now - observed_epoch > 90:
            raise ValueError('BACKEND_RESOURCE_STALE')

        service_identity = ((detail.get('effective') or {}).get('identity')
                            if isinstance(detail.get('effective'), dict) else None)
        if not isinstance(service_identity, dict):
            raise ValueError('BACKEND_RESOURCE_IDENTITY_UNQUALIFIED')
        boot_id = self._current_boot_id()
        if not boot_id:
            raise ValueError('HOST_BOOT_ID_UNAVAILABLE')
        if service_identity.get('boot_id') != boot_id:
            raise ValueError('BACKEND_RESOURCE_BOOT_ID_MISMATCH')

        # The helper gets the unmodified service responses (apart from merging
        # the resource reference into the view) so it can bind the live
        # by-id/sysfs identity to the service's owned identity.
        raw_backend = dict(detail)
        raw_backend['backend_resource'] = backend
        configured = detail.get('configured') or {}
        if not isinstance(configured, dict):
            raise ValueError('BACKEND_RESOURCE_CONFIG_UNKNOWN')
        inventory = probe_writeback_backends(
            host_uuid, raw_backend, configured)
        if not isinstance(inventory, dict):
            raise ValueError('BACKEND_RESOURCE_PROBE_UNAVAILABLE')
        if inventory.get('hostUuid') != host_uuid:
            raise ValueError('BACKEND_RESOURCE_HOST_MISMATCH')
        if inventory.get('bootId') != boot_id:
            raise ValueError('BACKEND_RESOURCE_BOOT_ID_MISMATCH')
        if inventory.get('status') not in ('AVAILABLE', 'PARTIAL'):
            reasons = inventory.get('reasons') or []
            reason = next((item for item in reasons if isinstance(item, STRING_TYPES) and
                           re.match(r'^[A-Z][A-Z0-9_]+$', item)), None)
            raise ValueError(reason or 'BACKEND_RESOURCE_PROBE_UNAVAILABLE')

        candidates = inventory.get('candidates')
        if not isinstance(candidates, list):
            raise ValueError('BACKEND_RESOURCE_PROBE_UNAVAILABLE')
        candidate = next((item for item in candidates
                          if isinstance(item, dict) and
                          item.get('resourceUuid') == generation), None)
        if candidate is None:
            matching_device = next((item for item in candidates
                                    if isinstance(item, dict) and
                                    item.get('device') == service_identity.get('canonical_device')),
                                   None)
            if isinstance(matching_device, dict) and matching_device.get('state') == 'IDENTITY_MISMATCH':
                raise ValueError('BACKEND_RESOURCE_IDENTITY_MISMATCH')
            if isinstance(matching_device, dict) and matching_device.get('state') == 'DISCONNECTED':
                raise ValueError('BACKEND_RESOURCE_DISCONNECTED')
            if isinstance(matching_device, dict):
                reasons = matching_device.get('reasons') or []
                reason = next((item for item in reasons if isinstance(item, STRING_TYPES) and
                               re.match(r'^[A-Z][A-Z0-9_]+$', item)), None)
                if reason:
                    raise ValueError(reason)
            reasons = inventory.get('reasons') or []
            reason = next((item for item in reasons if isinstance(item, STRING_TYPES) and
                           re.match(r'^[A-Z][A-Z0-9_]+$', item)), None)
            if reason:
                raise ValueError(reason)
            raise ValueError('BACKEND_RESOURCE_NOT_ACTIVE')
        if candidate.get('eligible') is not True or candidate.get('writebackReady') is not True:
            reasons = candidate.get('reasons') or []
            if 'PREPARED_BACKEND_EVIDENCE_INVALID' in reasons:
                raise ValueError('BACKEND_RESOURCE_STALE')
            if candidate.get('state') == 'IDENTITY_MISMATCH':
                raise ValueError('BACKEND_RESOURCE_IDENTITY_MISMATCH')
            if candidate.get('state') == 'DISCONNECTED':
                raise ValueError('BACKEND_RESOURCE_DISCONNECTED')
            reason = next((item for item in reasons if isinstance(item, STRING_TYPES) and
                           re.match(r'^[A-Z][A-Z0-9_]+$', item)), None)
            if reason:
                raise ValueError(reason)
            raise ValueError('BACKEND_RESOURCE_NOT_ACTIVE')
        if candidate.get('state') not in ('PREPARED', 'ACTIVE'):
            raise ValueError('BACKEND_RESOURCE_NOT_ACTIVE')
        if candidate.get('resourceUuid') != generation:
            raise ValueError('BACKEND_RESOURCE_OWNERSHIP_MISMATCH')
        if candidate.get('capacityBytes') != capacity:
            raise ValueError('BACKEND_CAPACITY_MISMATCH')
        if candidate.get('fingerprint') != fingerprint or candidate.get('identity') != fingerprint:
            raise ValueError('BACKEND_RESOURCE_FINGERPRINT_MISMATCH')
        if candidate.get('hostBootId') != boot_id:
            raise ValueError('BACKEND_RESOURCE_BOOT_ID_MISMATCH')

        # Cross-check the stable identity fields explicitly as well. The
        # candidate probe also verifies rdev/node/sysfs identity against live
        # stat data; these checks ensure the API and probe are talking about
        # the same resource and pool capacity.
        stable = candidate.get('stableIdentity') or {}
        canonical_device = service_identity.get('canonical_device')
        if (candidate.get('device') != canonical_device or
                service_identity.get('capacity_bytes') != capacity):
            raise ValueError('BACKEND_RESOURCE_IDENTITY_MISMATCH')
        if candidate.get('type') == 'block':
            if (stable.get('bootId') != boot_id or
                    stable.get('device') != canonical_device or
                    stable.get('capacityBytes') != capacity or
                    str(stable.get('sysfsInode')) != str(service_identity.get('sysfs_inode'))):
                raise ValueError('BACKEND_RESOURCE_IDENTITY_MISMATCH')
        elif candidate.get('type') == 'file':
            if (candidate.get('path') != service_identity.get('file_path') or
                    configured.get('file_path') != service_identity.get('file_path')):
                raise ValueError('BACKEND_RESOURCE_IDENTITY_MISMATCH')
        else:
            raise ValueError('BACKEND_RESOURCE_TYPE_UNSUPPORTED')

    @staticmethod
    def _backend_observation_epoch(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            try:
                numeric = float(value)
            except (OverflowError, TypeError, ValueError):
                return None
            return numeric if not math.isnan(numeric) and not math.isinf(numeric) else None
        if not isinstance(value, STRING_TYPES):
            return None
        match = re.match(
            r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)$',
            value)
        if not match:
            return None
        try:
            epoch = calendar.timegm(time.strptime(match.group(1), '%Y-%m-%dT%H:%M:%S'))
            if match.group(2):
                epoch += float('0.' + match.group(2))
            zone = match.group(3)
            if zone != 'Z':
                hours, minutes = int(zone[1:3]), int(zone[4:6])
                if hours > 23 or minutes > 59:
                    return None
                offset = hours * 3600 + minutes * 60
                epoch += -offset if zone[0] == '+' else offset
            return epoch
        except (ValueError, OverflowError):
            return None

    def _apply_ksm_policy(self, command, clear_context=None):
        """Apply KSM under the claimed host-operation lock via native units."""
        policy = command.get('policy') or {}
        ksm = policy.get('ksm') or {}
        inherited_clear = not ksm
        clear_boot = self._current_boot_id() if inherited_clear else None
        clear_control = self._get_active_control() if inherited_clear else None
        if not ksm:
            # A sparse clear target may still need to advance the revision of
            # an already managed controller. Reuse only a complete current
            # native acknowledgment tied to this Agent's durable KSM-only
            # journal or ownership marker; an empty target alone never takes
            # over distro/native KSM.
            prior_ack = (clear_context.get('priorKsmAck') if isinstance(clear_context, dict)
                         else self._managed_ksm_clear_ack(clear_command=command))
            if prior_ack is None and isinstance(clear_context, dict):
                raise RuntimeError('KSM_CLEAR_PRIOR_PROOF_MISSING')
            if prior_ack is None:
                return
            ksm = self._ksm_proof_policy(prior_ack, prior_ack.get('configRevision'))
            if ksm is None:
                raise RuntimeError('KSM_CLEAR_NATIVE_PROOF_INVALID')
        self._verify_native_ksm_profile()
        revision = command.get('desiredRevision', command.get('expectedRevision', 0) + 1)
        if not isinstance(revision, int) or revision < 1:
            raise ValueError('invalid KSM policy revision')
        # PRD defaults apply only where management has no explicit value. An
        # existing local native override is never silently overwritten.
        pages = ksm.get('pagesToScan', 2000)
        sleep = ksm.get('sleepMillis', 20)
        if (isinstance(pages, bool) or not isinstance(pages, INTEGER_TYPES) or pages < 1 or
                isinstance(sleep, bool) or not isinstance(sleep, INTEGER_TYPES) or sleep < 10):
            raise ValueError('KSM_POLICY_VALUE_INVALID')
        zero_value = self._read_ksm_zero_pages()
        if 'zeroPagesEnabled' in ksm:
            if not isinstance(ksm['zeroPagesEnabled'], bool):
                raise ValueError('KSM_ZERO_PAGES_POLICY_INVALID')
        if zero_value == 'unsupported' and ksm.get('zeroPagesEnabled') is True:
            # Do not turn an absent optional interface into a false value.
            # Explicit true is rejected before config, service, or sysfs writes.
            raise ValueError('KSM_ZERO_PAGES_UNSUPPORTED')
        if zero_value != 'unsupported' and ksm.get('zeroPagesEnabled') is not None:
            zero_value = '1' if ksm['zeroPagesEnabled'] else '0'
        # Removing an override leaves the native run switch unmanaged by this
        # sparse request. Do not infer an administrator disable from run=0:
        # ksmtuned may temporarily pause scanning under memory pressure.
        enabled = None if inherited_clear else ksm.get('enabled')
        if enabled not in (None, True, False):
            raise ValueError('KSM_ENABLED_POLICY_INVALID')
        current_ksm = self._native_service_state(self.KSM_UNIT, 'active')
        current_tuned = self._native_service_state(self.KSM_TUNED_UNIT, 'active')
        current_ksm_enabled = self._native_service_state(self.KSM_UNIT, 'enabled')
        current_tuned_enabled = self._native_service_state(self.KSM_TUNED_UNIT, 'enabled')
        if (current_ksm not in ('active', 'inactive') or
                current_tuned not in ('active', 'inactive') or
                current_ksm_enabled not in ('enabled', 'enabled-runtime', 'disabled', 'static', 'indirect') or
                current_tuned_enabled not in ('enabled', 'enabled-runtime', 'disabled', 'static', 'indirect')):
            raise ValueError('KSM_NATIVE_SERVICE_STATE_UNKNOWN')
        try:
            with open('/proc/meminfo', 'r') as stream:
                memtotal_kb = parse_memtotal_kb(stream.read())
            native_sleep = native_sleep_msec(sleep, memtotal_kb)
            try:
                with open(self.KSM_CONF, 'r') as stream:
                    existing_text = stream.read()
            except IOError as exc:
                if exc.errno != errno.ENOENT:
                    raise
                existing_text = ''
            content = render_config(existing_text, revision, pages, native_sleep)
        except NativeKsmConfigError as exc:
            raise ValueError(str(exc))

        if inherited_clear:
            if (clear_boot != self._current_boot_id() or
                    command.get('hostUuid') != self._load_host_uuid() or
                    clear_control != self._get_active_control()):
                raise RuntimeError('KSM_CLEAR_IDENTITY_CHANGED')
            if clear_context is None and self._managed_ksm_clear_ack(clear_command=command) != prior_ack:
                raise RuntimeError('KSM_CLEAR_PRIOR_PROOF_MISMATCH')

        # Service state is not inferred from run=0 because native ksmtuned may
        # temporarily stop scanning under pressure. For explicit disable, stop
        # the writer before replacing its config; other modes publish before a
        # controlled restart/start below.
        if enabled is True:
            self._publish_ksm_config(content)
            if zero_value in ('0', '1') and ksm.get('zeroPagesEnabled') is not None:
                self._write_ksm_sysfs('use_zero_pages', zero_value)
            # Runtime start only; the vendor boot enablement stays as the administrator left it.
            subprocess.check_call(['systemctl', 'start', self.KSM_UNIT])
            # Vendor ksmtuned waits for its first monitor interval; apply the
            # requested values with the same locked writer before it manages KSM.
            self._write_ksm_sysfs('pages_to_scan', str(pages))
            self._write_ksm_sysfs('sleep_millisecs', str(sleep))
            # An already-active oneshot ksm unit does not rerun its start hook.
            self._write_ksm_sysfs('run', '1')
            subprocess.check_call(['systemctl', 'restart' if current_tuned == 'active' else 'start',
                                   self.KSM_TUNED_UNIT])
        elif enabled is False:
            subprocess.check_call(['systemctl', 'stop', self.KSM_TUNED_UNIT])
            subprocess.check_call(['systemctl', 'stop', self.KSM_UNIT])
            self._publish_ksm_config(content)
            # Native ksmtuned applies its file while running; keep both units
            # stopped and update independent scan parameters under the Agent lock.
            self._write_ksm_sysfs('run', '0')
            self._write_ksm_sysfs('pages_to_scan', str(pages))
            self._write_ksm_sysfs('sleep_millisecs', str(sleep))
            if zero_value in ('0', '1') and ksm.get('zeroPagesEnabled') is not None:
                self._write_ksm_sysfs('use_zero_pages', zero_value)
        elif current_tuned == 'active':
            # `none` is not false and a tuning update must not start a service
            # that was previously off. Restart only an already-active writer.
            self._publish_ksm_config(content)
            if zero_value in ('0', '1') and ksm.get('zeroPagesEnabled') is not None:
                self._write_ksm_sysfs('use_zero_pages', zero_value)
            # The vendor daemon applies its configuration on restart, but its
            # monitor interval exceeds this operation's deadline. Write the
            # requested independent scan settings before restarting it.
            self._write_ksm_sysfs('pages_to_scan', str(pages))
            self._write_ksm_sysfs('sleep_millisecs', str(sleep))
            subprocess.check_call(['systemctl', 'restart', self.KSM_TUNED_UNIT])
        else:
            # Keep an inactive native service inactive while applying the
            # explicit scan parameters through the same locked Agent writer.
            self._publish_ksm_config(content)
            self._write_ksm_sysfs('pages_to_scan', str(pages))
            self._write_ksm_sysfs('sleep_millisecs', str(sleep))
            if zero_value in ('0', '1') and ksm.get('zeroPagesEnabled') is not None:
                self._write_ksm_sysfs('use_zero_pages', zero_value)

        clock = getattr(time, 'monotonic', time.time)
        deadline = clock() + getattr(self, 'ksm_apply_timeout', 10)
        while True:
            readback = self._read_ksm_ack()
            reason = None
            if readback is None:
                reason = 'KSM_NATIVE_READBACK_UNKNOWN'
            elif enabled is True and readback.get('run') != '1':
                reason = 'KSM_NOT_RUNNING'
            elif enabled is False and readback.get('run') != '0':
                reason = 'KSM_NOT_STOPPED'
            elif readback.get('configRevision') != str(revision):
                reason = 'KSM_REVISION_NOT_APPLIED'
            elif readback.get('pages_to_scan') != str(pages):
                reason = 'KSM_PAGES_NOT_APPLIED'
            elif readback.get('sleep_millisecs') != str(sleep):
                reason = 'KSM_SLEEP_NOT_APPLIED'
            elif (zero_value in ('0', '1') and
                  readback.get('use_zero_pages') != zero_value):
                reason = 'KSM_ZERO_PAGES_ACK_UNKNOWN'
            if reason is None:
                return readback
            if clock() >= deadline:
                raise RuntimeError(reason)
            time.sleep(0.2)

    def _managed_ksm_clear_ack(self, require_ksm_only=True, prepared_backend=None,
                               clear_command=None):
        """Return the current full ack only when existing managed ownership is proven."""
        operation_uuid = self._get_active_control()
        if not operation_uuid:
            return None
        file_state, record = self._operation_file_state(operation_uuid)
        if file_state in ('corrupt', 'unreadable'):
            raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_UNAVAILABLE')
        readback = record.get('readback') if isinstance(record, dict) else None
        state = readback.get('state') if isinstance(readback, dict) else None
        prior_policy = record.get('policy') if isinstance(record, dict) else None
        prior_ksm = prior_policy.get('ksm') if isinstance(prior_policy, dict) else None
        claims_managed_ksm = isinstance(prior_ksm, dict) and bool(prior_ksm)
        current_boot_id = self._current_boot_id()
        prior_scope = record.get('scope') if isinstance(record, dict) else None
        prior_resource_uuid = record.get('resourceUuid') if isinstance(record, dict) else None
        prior_host_uuid = record.get('hostUuid') if isinstance(record, dict) else None
        scope_resource_matches = (
            (prior_scope is None and prior_resource_uuid is None) or
            (prior_scope in ('Host', 'host') and prior_resource_uuid in (None, prior_host_uuid)) or
            (prior_scope in ('Global', 'global') and prior_resource_uuid == 'global') or
            (prior_scope in ('Cluster', 'cluster') and
             isinstance(prior_resource_uuid, STRING_TYPES) and bool(prior_resource_uuid.strip())))

        revision = record.get('desiredRevision') if isinstance(record, dict) else None
        prior_proof = readback.get('ksmReadback') if isinstance(readback, dict) else None
        prepared_backend_ksm = False
        if prepared_backend is not None:
            expected_fields = frozenset(('operationUuid', 'record', 'bootId',
                                         'resourceUuid', 'capacityBytes'))
            if (not isinstance(prepared_backend, dict) or
                    set(prepared_backend) != expected_fields or
                    not isinstance(prepared_backend.get('operationUuid'), STRING_TYPES) or
                    not isinstance(prepared_backend.get('record'), dict) or
                    prepared_backend.get('bootId') != current_boot_id or
                    not isinstance(prepared_backend.get('resourceUuid'), STRING_TYPES) or
                    isinstance(prepared_backend.get('capacityBytes'), bool) or
                    not isinstance(prepared_backend.get('capacityBytes'), INTEGER_TYPES)):
                raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_INVALID')
            preparation_uuid = prepared_backend['operationUuid']
            prepared_backend_ksm = self._first_use_backend_bound_ksm_record(
                record, {preparation_uuid: prepared_backend['record']},
                expected_boot=current_boot_id, expected_operation=operation_uuid,
                expected_resource_uuid=prepared_backend['resourceUuid'],
                expected_capacity=prepared_backend['capacityBytes'])
        host_is_ksm_only = bool(
            isinstance(state, dict) and state.get('ksmOnly') is True and
            isinstance(prior_policy, dict) and
            (self._ksm_only_disabled_service_sections(prior_policy) or
             prepared_backend_ksm))
        contradictory_mixed_claim = bool(
            isinstance(state, dict) and state.get('ksmOnly') is True and
            isinstance(prior_policy, dict) and
            not (self._ksm_only_disabled_service_sections(prior_policy) or
                 prepared_backend_ksm))
        # A reboot invalidates the old native ACK. For a new Host-only clear,
        # the old terminal journal proves ownership of the persistent config;
        # the complete native ACK below must be read again on this boot.
        cross_boot_clear = False
        if (isinstance(record, dict) and record.get('bootId') != current_boot_id and
                isinstance(clear_command, dict)):
            pending = self._load_operation(clear_command)
            cross_boot_clear = bool(
                require_ksm_only and prepared_backend is None and host_is_ksm_only and
                clear_command.get('action') == 'apply' and
                clear_command.get('scope') == 'Host' and
                clear_command.get('hostUuid') == self._load_host_uuid() and
                clear_command.get('resourceUuid') == clear_command.get('hostUuid') and
                clear_command.get('policyMode', 'effective') == 'effective' and
                clear_command.get('policy') == {'schemaVersion': 1, 'ksm': {}} and
                self._valid_identifier(record.get('bootId')) and
                record.get('policyHash') == self._policy_digest(prior_policy) and
                set(prior_policy or {}) <= set(('schemaVersion', 'ksm')) and
                isinstance(pending, dict) and pending.get('stage') == 'PREPARING' and
                pending.get('bootId') == current_boot_id and
                pending.get('requestHash') == self._operation_hash(clear_command) and
                all(pending.get(key) == clear_command.get(key)
                    for key in ('operationUuid', 'hostUuid', 'scope', 'resourceUuid',
                                'action', 'policy', 'desiredRevision')) and
                pending.get('policyHash') == self._policy_digest(clear_command['policy']) and
                self._revision(revision) and
                self._revision(clear_command.get('desiredRevision')) and
                clear_command['desiredRevision'] > revision)
        journal_proves_ownership = bool(
            isinstance(record, dict) and record.get('operationUuid') == operation_uuid and
            record.get('hostUuid') == self._load_host_uuid() and
            scope_resource_matches and
            record.get('action') in (None, 'apply') and
            record.get('stage') == 'APPLIED' and
            isinstance(current_boot_id, STRING_TYPES) and bool(current_boot_id.strip()) and
            (record.get('bootId') == current_boot_id or cross_boot_clear) and
            isinstance(record.get('requestHash'), STRING_TYPES) and
            re.match(r'^[0-9a-f]{64}\Z', record.get('requestHash')) is not None and
            isinstance(revision, INTEGER_TYPES) and not isinstance(revision, bool) and revision > 0 and
            isinstance(readback, dict) and readback.get('success') is True and
            readback.get('status') == 'Succeeded' and readback.get('appliedRevision') == revision and
            isinstance(prior_policy, dict) and isinstance(prior_ksm, dict) and
            (not require_ksm_only or host_is_ksm_only) and
            not contradictory_mixed_claim and
            self._ksm_proof_policy(prior_proof, revision) is not None)
        if journal_proves_ownership:
            proof_policy = self._ksm_proof_policy(prior_proof, revision)
            for field, expected in proof_policy.items():
                if field not in prior_ksm:
                    continue
                observed = prior_ksm[field]
                if isinstance(expected, bool):
                    matches = isinstance(observed, bool) and observed is expected
                else:
                    matches = (isinstance(observed, INTEGER_TYPES) and
                               not isinstance(observed, bool) and observed == expected)
                if not matches:
                    journal_proves_ownership = False
                    break
        if not journal_proves_ownership:
            if claims_managed_ksm:
                raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_INVALID')
            return None

        current = self._read_ksm_ack()
        if current is None:
            raise RuntimeError('KSM_CLEAR_NATIVE_ACK_UNAVAILABLE')
        current_matches = current == prior_proof
        if cross_boot_clear:
            current_matches = (
                self._ksm_proof_policy(current, revision) is not None and
                all(current.get(key) == prior_proof.get(key)
                    for key in ('configRevision', 'pages_to_scan', 'sleep_millisecs')))
        if (not current_matches and isinstance(prior_proof, dict) and
                prior_proof.get('run') == '1' and current.get('run') == '0'):
            # Native ksmtuned may pause scanning temporarily under pressure.
            # That run-bit transition does not invalidate ownership proof only
            # while both native units remain active and all other readbacks match.
            observed = dict(current)
            observed['run'] = '1'
            try:
                services_active = (
                    self._native_service_state(self.KSM_UNIT, 'active') == 'active' and
                    self._native_service_state(self.KSM_TUNED_UNIT, 'active') == 'active')
            except Exception:
                services_active = False
            current_matches = observed == prior_proof and services_active
        if not current_matches:
            raise RuntimeError('KSM_CLEAR_PRIOR_PROOF_MISMATCH')
        normalized_proof = {key: prior_proof[key] for key in current}
        if not cross_boot_clear and normalized_proof != current:
            raise RuntimeError('KSM_CLEAR_PRIOR_PROOF_MISMATCH')
        existing = self._managed_ksm_config_identity()
        expected_config = {
            'CONFIG_REVISION': int(current['configRevision']),
            'KSM_NPAGES_MIN': int(current['pages_to_scan']),
            'KSM_NPAGES_MAX': int(current['pages_to_scan']),
            'KSM_NPAGES_BOOST': 0,
            'KSM_NPAGES_DECAY': 0,
            'KSM_SLEEP_MSEC': self._native_sleep_for_policy(
                int(current['sleep_millisecs'])),
            'KSM_THRES_COEF': 100,
            'KSM_THRES_CONST': 2048,
        }
        if existing != expected_config:
            raise RuntimeError('KSM_CLEAR_CONFIG_ACK_MISMATCH')
        if cross_boot_clear and (
                self._current_boot_id() != current_boot_id or
                self._load_host_uuid() != clear_command.get('hostUuid') or
                self._get_active_control() != operation_uuid or
                self._load_operation({'operationUuid': operation_uuid}) != record or
                self._load_operation(clear_command) != pending):
            raise RuntimeError('KSM_CLEAR_PRIOR_JOURNAL_INVALID')
        return current

    def _managed_ksm_config_identity(self):
        """Read the owned block from native config, without evaluating shell."""
        try:
            with open(self.KSM_CONF) as stream:
                return managed_config_values(stream.read()) or {}
        except IOError as exc:
            if exc.errno == errno.ENOENT:
                return {}
            raise

    def _native_sleep_for_policy(self, policy_msec):
        try:
            with open('/proc/meminfo', 'r') as stream:
                total = parse_memtotal_kb(stream.read())
            return native_sleep_msec(policy_msec, total)
        except (IOError, OSError, NativeKsmConfigError) as exc:
            raise RuntimeError('KSM_NATIVE_SLEEP_IDENTITY_UNKNOWN:%s' % exc)

    @contextmanager
    def _ksm_writer_lock(self):
        lock_dir = os.path.dirname(self.KSM_LOCK)
        if not os.path.isdir(lock_dir):
            os.makedirs(lock_dir)
        clock = getattr(time, 'monotonic', time.time)
        with open(self.KSM_LOCK, 'a') as lock:
            deadline = clock() + 5
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (IOError, OSError) as exc:
                    if exc.errno not in (errno.EAGAIN, errno.EACCES) or clock() >= deadline:
                        raise RuntimeError('KSM_WRITER_LOCK_UNAVAILABLE')
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _publish_ksm_config(self, content):
        """Publish durable KSM policy without a product-license lease."""
        directory = os.path.dirname(self.KSM_CONF)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with self._ksm_writer_lock():
            fd, temp_path = tempfile.mkstemp(prefix='.ksmtuned-', dir=directory)
            try:
                # Keep the vendor file mode; mkstemp creates 0600.
                mode = stat.S_IMODE(os.stat(self.KSM_CONF).st_mode) if os.path.exists(self.KSM_CONF) else 0o644
                os.fchmod(fd, mode)
                os.write(fd, content.encode('utf-8'))
                os.fsync(fd)
                os.close(fd)
                os.rename(temp_path, self.KSM_CONF)
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    def _call_local_service(self, action, command):
        """Send one JSON request to the host service over its Unix socket."""
        routes = {'state': ('GET', '/v1/status'),
                  'monitor-state': ('GET', '/v1/status'),
                  'capabilities': ('GET', '/v1/capabilities'),
                  'backend-state': ('GET', '/v1/status'),
                  'backend-view': ('GET', '/v1/zram/backend'),
                  'preview': ('GET', '/v1/zram/tuning'),
                  'tuning-state': ('GET', '/v1/zram/tuning'),
                  'capacity-state': ('GET', '/v1/zram/config'),
                  'host-cpu-state': ('GET', '/v1/efficiency/policy'),
                  'vm-policy-state': ('GET', '/v1/vms/%s/efficiency' % command.get('_resource_uuid', '')),
                  'vm-identities': ('POST', '/v1/vm-identities'),
                  'lifecycle-pause': ('POST', '/v1/lifecycle/pause'),
                  'lifecycle-activate-maintenance': ('POST', '/v1/lifecycle/activate-maintenance'),
                  'lifecycle-activation-state': ('GET', '/v1/lifecycle/maintenance-activation'),
                  'lifecycle-activation-retirement': ('POST', '/v1/maintenance/activation-retirements'),
                  'lifecycle-activation-retirement-state': ('GET', '/v1/maintenance/activation-retirements'),
                  'drain-status': ('GET', '/v1/backends/ordinary/drains'),
                  'drain-start': ('POST', '/v1/backends/ordinary/drains'),
                  'apply': ('PUT', '/v1/zram/tuning'),
                  'reconcile': ('POST', '/v1/maintenance/reconcile'),
                  'backend-maintenance': ('GET', '/v1/backend-maintenance'),
                  'backend-maintenance-finalize': ('POST', '/v1/backend-maintenance/finalize'),
                  'zram-pool-maintenance': ('GET', '/v1/zram-pool-maintenance'),
                  'zram-pool-maintenance-finalize': ('POST', '/v1/zram-pool-maintenance/finalize'),
                  'accounting': ('GET', '/v1/memory/accounting'),
                  'operations': ('GET', '/v1/operations'),
                  'migration-hold': ('POST', '/v1/migration-hold'),
                  'capacity': ('PUT', '/v1/zram/config'),
                  'host-cpu': ('PUT', '/v1/efficiency/policy')}
        routes.update({
            'vm-management': ('GET', '/v1/vm-management'),
            'vm-management-shard-stage': ('POST', '/v1/vm-management/shard/stage'),
            'vm-management-shard-commit': ('POST', '/v1/vm-management/shard/commit'),
            'vm-management-shard-cancel': ('POST', '/v1/vm-management/shard/cancel'),
        })
        if action == 'vm-policy':
            routes[action] = ('PUT', '/v1/vms/%s/efficiency' % command['_resource_uuid'])
        method, path = routes[action]
        if action == 'lifecycle-activation-state':
            request_id = command.get('request_id') or command.get('requestId')
            if not request_id:
                raise ValueError('maintenance activation request id is required')
            path += '?request_id=%s' % request_id
        if action == 'lifecycle-activation-retirement-state':
            path += '/%s?requestId=%s' % (command['oldActivationRequestId'],
                                          command['requestId'])
        request_command = dict(command)
        request_command.pop('_resource_uuid', None)
        target_snapshot_generation = request_command.pop('_target_snapshot_generation', None)
        transport = request_command.pop('communication', None) or {}
        request_bytes = transport.get('requestBytes', self.request_bytes)
        response_bytes = transport.get('responseBytes', self.response_bytes)
        communication_seconds = transport.get('communicationSeconds', self.communication_seconds)
        if (isinstance(request_bytes, bool) or not isinstance(request_bytes, int) or request_bytes <= 0 or
                isinstance(response_bytes, bool) or not isinstance(response_bytes, int) or response_bytes <= 0 or
                isinstance(communication_seconds, bool) or
                not isinstance(communication_seconds, (int, float)) or communication_seconds <= 0):
            raise ValueError('invalid per-request communication budget')
        data = b'' if method == 'GET' else json.dumps(request_command).encode('utf-8')
        # An apply request may contain a large VM list which is deliberately
        # removed and sent through the shard protocol below.  Checking its
        # pre-sharding envelope would reject exactly the requests this path
        # is meant to support.
        if action != 'apply' and len(data) > request_bytes:
            raise IOError('memory service request too large')
        if method == 'GET':
            query = {}
            query_names = {}
            if action == 'operations':
                query_names = {'operationId': 'operation_id', 'start': 'start',
                               'limit': 'limit', 'status': 'status'}
            for key, wire_key in query_names.items():
                if request_command.get(key) is not None:
                    query[wire_key] = request_command[key]
            if query:
                path += '?' + urlencode(query)
        if action == 'apply':
            settings = request_command.get('settings')
            vm_management = settings.get('vm_management') if isinstance(settings, dict) else None
            vm_uuids = vm_management.get('vm_uuids') if isinstance(vm_management, dict) else None
            if isinstance(vm_uuids, list) and len(vm_uuids) > 0:
                if not target_snapshot_generation:
                    raise ValueError('VM_TARGET_SNAPSHOT_GENERATION_REQUIRED')
                self._send_vm_management_shards(
                    request_command, vm_uuids, target_snapshot_generation,
                    request_bytes, response_bytes, communication_seconds)
                vm_management = dict(vm_management)
                vm_management['vm_uuids'] = []
                settings = dict(settings)
                settings['vm_management'] = vm_management
                request_command['settings'] = settings
                data = json.dumps(request_command).encode('utf-8')
                if len(data) > request_bytes:
                    raise IOError('memory service request too large after VM shard extraction')
        elif action == 'apply' and len(data) > request_bytes:
            raise IOError('memory service request too large')
        service_socket = self.socket_path
        if action in ('monitor-state', 'lifecycle-activation-retirement-state'):
            service_socket = self.monitor_socket_path
        conn = _UnixHTTPConnection(service_socket, timeout=communication_seconds)
        try:
            conn.request(method, path, body=data,
                         headers={'Host': 'localhost',
                                  'Content-Type': 'application/json',
                                  'Connection': 'close'})
            response = conn.getresponse()
            status_code = response.status
            payload = response.read(response_bytes + 1)
            if len(payload) > response_bytes:
                raise IOError('memory service response too large')
            result = json.loads(payload.decode('utf-8'))
            # The maintenance API is served by the service's outer API
            # envelope, while efficiency endpoints return the value directly.
            if isinstance(result, dict) and isinstance(result.get('data'), dict):
                result = result['data']
            if isinstance(result, dict):
                result['_http_status'] = status_code
            return result
        finally:
            conn.close()

    def _send_vm_management_shards(self, command, vm_uuids, snapshot_generation,
                                   request_bytes, response_bytes, communication_seconds):
        """Stage and atomically commit a VM list through the Go shard API."""
        ids = sorted(set(vm_uuids))
        if len(ids) != len(vm_uuids):
            raise ValueError('duplicate VM UUID in target list')
        request_id = command.get('request_id')
        if not request_id:
            raise ValueError('VM shard request metadata is incomplete')
        current = self._call_local_service('vm-management', {
            'communication': {'requestBytes': request_bytes,
                              'responseBytes': response_bytes,
                              'communicationSeconds': communication_seconds}})
        settings = current.get('settings') if isinstance(current, dict) else None
        expected_revision = settings.get('revision') if isinstance(settings, dict) else None
        if not isinstance(expected_revision, int):
            raise RuntimeError('VM_MANAGEMENT_REVISION_UNKNOWN')
        digest = hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode('utf-8')).hexdigest()
        chunk_size = 256
        base = {'request_id': request_id, 'expected_revision': expected_revision,
                'snapshot_generation': snapshot_generation, 'total_count': len(ids),
                'digest': digest, 'ttl_seconds': 90,
                'communication': {'requestBytes': request_bytes,
                                  'responseBytes': response_bytes,
                                  'communicationSeconds': communication_seconds}}
        try:
            for index in range(0, len(ids), chunk_size):
                payload = dict(base)
                payload['chunk_index'] = index // chunk_size
                payload['vm_uuids'] = ids[index:index + chunk_size]
                result = self._call_local_service('vm-management-shard-stage', payload)
                if not isinstance(result, dict) or result.get('_http_status', 500) >= 300:
                    raise RuntimeError('VM_SHARD_STAGE_FAILED')
            result = self._call_local_service('vm-management-shard-commit', base)
            if not isinstance(result, dict) or result.get('_http_status', 500) >= 300:
                raise RuntimeError('VM_SHARD_COMMIT_FAILED')
        except Exception:
            try:
                self._call_local_service('vm-management-shard-cancel', base)
            except Exception:
                pass
            raise

    def _maintenance_proof_for_state(self, state):
        """Expose only locally reconstructed, archive-backed recovery proof."""
        operation_uuid = self._get_active_control()
        record = self._load_operation({'operationUuid': operation_uuid}) if operation_uuid else None
        if (not isinstance(record, dict) or record.get('action') != 'drain' or
                record.get('stage') != 'APPLIED'):
            return None
        intent_path = os.path.join(self.operation_dir, '%s.drain-intent.json' % operation_uuid)
        try:
            with open(intent_path) as stream:
                intent = json.load(stream)
            old_generation = intent.get('poolGeneration')
        except (IOError, OSError, ValueError):
            return None
        pool = state.get('host_zram') or state.get('pool') or {}
        new_generation = pool.get('pool_generation') if isinstance(pool, dict) else None
        proof = {'maintenanceReady': True,
                 'drainOperationUuid': operation_uuid,
                 'oldPoolGeneration': old_generation}
        if new_generation and new_generation != old_generation:
            proof['newPoolGeneration'] = new_generation
        if new_generation:
            proof.update({'maintenanceArchived': True, 'activeOperations': 0,
                          'poolOwnedByService': True,
                          'readyForInitialization': False,
                          'originalDeviceInactive': True,
                          'oldPoolOwnershipAbsent': True})
        else:
            proof.update({'maintenanceArchived': True, 'activeOperations': 0,
                          'poolOwnedByService': False,
                          'readyForInitialization': True,
                          'originalDeviceInactive': True,
                          'oldPoolOwnershipAbsent': True})
        if self._maintenance_recovery_proof({'maintenanceProof': proof}, live_state=state):
            # This is a claim reconstructed from the Agent journal, Go archive,
            # and live state; MN must echo it in the subsequent CAS request.
            proof['executorExited'] = True
            return proof
        return None

    def _enrich_state(self, result):
        """Add product capabilities and mechanism-estimate savings to state.

        The collector is deliberately read-only.  A missing zram service does
        not erase legacy KSM observations, and unknown values are omitted
        rather than represented as zero.
        """
        # Attach only read-back facts obtained from the native interfaces. Do
        # not derive these values from policy or capabilities: a failed read
        # is retained as a reason and is never presented as a configured value.
        actual = {'ksm': {}, 'zram': {}, 'writeback': {}}
        try:
            native = {'run': self._read_ksm_sysfs('run'),
                      'pages_to_scan': self._read_ksm_sysfs('pages_to_scan'),
                      'sleep_millisecs': self._read_ksm_sysfs('sleep_millisecs'),
                      'use_zero_pages': self._read_ksm_zero_pages()}
            config = self._read_native_ksm_config()
            ksm_active = self._native_service_state(self.KSM_UNIT, 'active')
            tuned_active = self._native_service_state(self.KSM_TUNED_UNIT, 'active')
            service_enabled = (True if ksm_active == 'active' and tuned_active == 'active' else
                               False if ksm_active == 'inactive' and tuned_active == 'inactive' else None)
            actual['ksm'] = {
                'enabled': service_enabled,
                # Preserve the native unit read-back separately from the
                # compatibility boolean above.  Consumers need to
                # distinguish a deliberate inactive state from systemd
                # failure without issuing another systemd query.
                # jsonobject omits None-valued map entries.  Use an explicit
                # token so an unrecognised systemd result remains distinct
                # from an absent field and from inactive/failed.
                'serviceState': ksm_active if ksm_active is not None else 'unknown',
                'tunedServiceState': tuned_active if tuned_active is not None else 'unknown',
                'scanning': native['run'] == '1',
                'pagesToScan': int(native['pages_to_scan']),
                'sleepMillis': int(native['sleep_millisecs']),
                'configRevision': config.get('CONFIG_REVISION') if config else None,
            }
            if native['use_zero_pages'] in ('0', '1'):
                actual['ksm']['zeroPagesEnabled'] = native['use_zero_pages'] == '1'
        except Exception as exc:
            actual['ksm'] = {'quality': 'unknown', 'reason': str(exc)}
        for action, key in (('tuning-state', 'zram'), ('capacity-state', 'zram'), ('backend-state', 'writeback')):
            try:
                value = self.service_call(action, {})
                if action == 'tuning-state':
                    actual['zram']['tuning'] = value
                    settings = value.get('settings', value) if isinstance(value, dict) else None
                    wb = settings.get('writeback') if isinstance(settings, dict) else None
                    if isinstance(wb, dict): actual['writeback']['tuning'] = wb
                elif action == 'capacity-state':
                    actual['zram']['capacity'] = value
                else:
                    actual['writeback']['backend'] = value
            except Exception as exc:
                actual[key].setdefault('errors', []).append({'operation': action, 'reason': str(exc)})
        try:
            # Read the effective native switch, not the desired MN policy or
            # the existence of a pool containing older swapped-out data.
            efficiency = self.service_call('host-cpu-state', {})
            enabled = efficiency.get('efficiency_enabled') if isinstance(efficiency, dict) else None
            if isinstance(enabled, bool):
                actual['zram']['efficiencyEnabled'] = enabled
            else:
                raise ValueError('EFFICIENCY_SWITCH_UNAVAILABLE')
        except Exception as exc:
            actual['zram'].setdefault('errors', []).append({
                'operation': 'host-cpu-state', 'reason': str(exc)})
        # The native state envelope is normalized below. Keep the read-back
        # object separate until that normalization is complete; otherwise the
        # later assignment of result['state'] would silently drop it.
        # This timestamp describes this Agent collection, not the native
        # service's older observation timestamp.  MN uses it to decide
        # whether the complete state envelope is fresh; native timestamps are
        # retained inside their respective state/savings objects.
        if not isinstance(result.get('sampleTime'), INTEGER_TYPES):
            result['sampleTime'] = int(time.time() * 1000)
        # A native RuntimeSnapshot has section revisions, not the product
        # policy revision.  Recover only the last confirmed product revision
        # for the current active-control operation, Host and boot.  Never
        # turn an old journal or a different boot into a fresh confirmation.
        active_operation = self._get_active_control()
        if active_operation:
            record_path = os.path.join(self.operation_dir,
                                       '%s.json' % active_operation)
            try:
                with open(record_path, 'r') as stream:
                    record = json.load(stream)
                current_boot = None
                with open('/proc/sys/kernel/random/boot_id', 'r') as stream:
                    current_boot = stream.read().strip()
                if (record.get('stage') == 'APPLIED' and current_boot and
                        record.get('bootId') == current_boot and
                        record.get('hostUuid') == self._load_host_uuid()):
                    confirmed = record.get('desiredRevision')
                    if isinstance(confirmed, INTEGER_TYPES):
                        result['appliedRevision'] = confirmed
                        result['lastConfirmedAppliedRevision'] = confirmed
                        result['lastConfirmedOperationUuid'] = active_operation
            except (IOError, OSError, ValueError, TypeError):
                pass
        state = result.get('state')
        if not isinstance(state, dict):
            # /v1/status returns the RuntimeSnapshot directly (there is no
            # nested state member).  Preserve that snapshot for MN instead of
            # reducing it to the string/empty state used by error replies.
            state = dict((key, value) for key, value in result.items()
                         if key not in ('success', 'status', 'reason',
                                        'operationUuid', 'appliedRevision',
                                        'sampleTime'))
        # These lifecycle fields are part of the Agent contract.  Only use
        # facts returned by the service; conservative defaults prevent host
        # deletion while managed state may still exist.
        # Historical Agent journals prove that this Agent once issued a
        # request, not that the current service still owns a pool.  Current
        # ownership must come from the live service snapshot/marker only.
        managed = bool(state.get('managed', False) or
                       self._get_active_control() is not None)
        state['managed'] = managed
        try:
            with open('/proc/sys/kernel/random/boot_id', 'r') as stream:
                boot_id = stream.read().strip()
            if boot_id:
                state['bootId'] = boot_id
        except (IOError, OSError):
            state['bootId'] = None
        # Absence of a marker is not proof that an active service has drained;
        # only advertise removable when both control ownership and pending
        # work are absent in the service snapshot.
        pending = state.get('pending_operations') or state.get('pending') or []
        state['safeToRemove'] = (not managed and not state.get('ksmOnly') and not pending and
                                 result.get('status') != 'Unknown')
        pool = state.get('pool') or state.get('host_zram')
        if isinstance(pool, dict) and pool.get('pool_generation') and 'poolGeneration' not in state:
            state['poolGeneration'] = pool['pool_generation']
        if 'pool_generation' in state and 'poolGeneration' not in state:
            state['poolGeneration'] = state['pool_generation']
        maintenance_proof = self._maintenance_proof_for_state(state)
        if maintenance_proof is not None:
            state['maintenanceProof'] = maintenance_proof
        vms = state.get('vms')
        if isinstance(vms, dict):
            for vm_uuid, vm_state in vms.items():
                if not isinstance(vm_state, dict):
                    continue
                stats = vm_state.get('stats') or {}
                identity = stats.get('identity') if isinstance(stats, dict) else None
                if isinstance(identity, dict) and identity.get('instance_generation'):
                    vm_state['instanceGeneration'] = identity['instance_generation']
                # RuntimeSnapshot is native snake_case; the Agent/MN contract
                # is camelCase. Preserve the native keys while adding the
                # contract aliases so older consumers remain compatible.
                if vm_state.get('binding_generation') is not None:
                    vm_state['bindingGeneration'] = vm_state['binding_generation']
                if vm_state.get('binding_mode') is not None:
                    vm_state['bindingMode'] = vm_state['binding_mode']
        # A native snapshot covers selected VMs, not all running domains.
        # Selection must never be used as absence proof during migration.
        state['vms'], state['inventoryComplete'] = self._complete_vm_inventory(vms)
        result['state'] = state
        state['actual'] = actual
        try:
            result['capabilities'] = self.discover_capabilities()
            if isinstance(result['capabilities'], dict):
                # This marker describes the Agent code that served the state
                # request, not the separately versioned Go service package.
                result['capabilities']['readOnlyCompletedReconcile'] = True
        except Exception as exc:
            result['capabilities'] = {'supported': None,
                                       'reasonCode': 'CAPABILITY_UNKNOWN',
                                       'reason': str(exc)}
        state['capabilities'] = result['capabilities']
        try:
            backend = self.service_call('backend-state', {})
            resource = backend.get('backend_resource') if isinstance(backend, dict) else None
            if isinstance(resource, dict) and resource.get('resource_uuid'):
                generation = resource['resource_uuid']
                result['capabilities']['backend'] = {
                    'resourceUuid': generation,
                    'capacityBytes': resource.get('capacity_bytes'),
                    'fingerprint': resource.get('fingerprint'),
                    'state': resource.get('state'),
                    'active': resource.get('active'),
                }
        except Exception:
            pass
        # The Agent reports control/runtime facts only. Savings come from
        # node_exporter -> Prometheus; never create a second sampling path or
        # let an old embedded service field masquerade as a fresh metric.
        result.pop('savings', None)
        state.pop('savings', None)
        return result

    def _complete_vm_inventory(self, native_vms):
        native_vms = native_vms if isinstance(native_vms, dict) else {}
        domains, complete = self._libvirt_vm_generations()
        if not complete:
            return native_vms, False
        inventory = dict((key, {'identityReason': 'VM_IDENTITY_UNAVAILABLE'})
                         for key in domains)
        # Batch by the existing transport byte budget, not a VM count limit.
        batches, batch = [], []
        size = len(json.dumps({'vm_uuids': []}).encode('utf-8'))
        for key in sorted(domains):
            extra = len(json.dumps(key).encode('utf-8')) + (2 if batch else 0)
            if batch and size + extra > self.request_bytes:
                batches.append(batch)
                batch, size = [], len(json.dumps({'vm_uuids': []}).encode('utf-8'))
                extra = len(json.dumps(key).encode('utf-8'))
            if size + extra > self.request_bytes:
                inventory[key]['identityReason'] = 'IDENTITY_REQUEST_BUDGET_TOO_SMALL'
                continue
            batch.append(key)
            size += extra
        if batch:
            batches.append(batch)
        for batch in batches:
            try:
                response = self.service_call('vm-identities', {'vm_uuids': batch})
                identities = dict((_product_vm_uuid(key), value) for key, value in
                                  (response.get('identities') or {}).items())
                for key in batch:
                    identity = identities.get(key)
                    if not isinstance(identity, dict) or _product_vm_uuid(identity.get('uuid')) != key:
                        continue
                    generation = identity.get('instance_generation')
                    if not isinstance(generation, STRING_TYPES) or not generation:
                        continue
                    previous = native_vms.get(key) or {}
                    # Preserve sampled/binding fields only for the same
                    # verified process incarnation, never after a restart.
                    previous_identity = (previous.get('stats') or {}).get('identity') or {}
                    previous_generation = previous.get('instanceGeneration') or previous_identity.get('instance_generation')
                    item = dict(previous) if previous_generation == generation else {}
                    item['instanceGeneration'] = generation
                    item['identity'] = _accounting_wire_identity(identity)
                    inventory[key] = item
            except Exception:
                # Present but unresolvable is not absent and is not an old
                # generation. MN must refuse lifecycle changes for that VM.
                continue
        return inventory, True

    @staticmethod
    def _libvirt_vm_generations():
        """Best-effort generation source for hosts without zram-service.

        Libvirt exposes the current domain UUID and runtime domain ID, not the
        Go resolver's cgroup start-time token.  The pair is therefore only a
        migration-target fallback and is never claimed as a native service
        generation when the Go API is available.
        """
        try:
            import libvirt
            conn = libvirt.openReadOnly(None)
            try:
                result = {}
                for domain in conn.listAllDomains(0):
                    if domain.isActive():
                        raw_uuid = domain.UUIDString()
                        vm_uuid = _product_vm_uuid(raw_uuid)
                        result[vm_uuid] = {
                            'instanceGeneration': '%s:%s' % (vm_uuid, domain.ID())}
                return result, True
            finally:
                conn.close()
        except Exception:
            return {}, False

    def _has_applied_operation(self):
        """Whether this Agent has durable evidence of product ownership."""
        try:
            for name in os.listdir(self.operation_dir):
                if not name.endswith('.json'):
                    continue
                with open(os.path.join(self.operation_dir, name), 'r') as stream:
                    if json.load(stream).get('stage') == 'APPLIED':
                        return True
        except (IOError, OSError, ValueError):
            pass
        return False

    @staticmethod
    def capabilities_from_facts(release, arch, page_size, kernel,
                                module_loaded, service_ready, interfaces=None):
        """Return an explicit capability result; absence is never zero."""
        if arch != 'x86_64':
            return {'supported': False, 'reasonCode': 'UNSUPPORTED_ARCHITECTURE'}
        if release not in ('h84r', 'alinux4', 'kylinV10'):
            return {'supported': False, 'reasonCode': 'UNSUPPORTED_OS_RELEASE'}
        if int(page_size) != 4096:
            return {'supported': False, 'reasonCode': 'UNSUPPORTED_PAGE_SIZE'}
        interfaces = interfaces or {}
        required = ('ksm_run', 'ksm_pages_to_scan', 'ksm_sleep_millisecs',
                    'zram_mm_stat')
        if not kernel or kernel == 'unknown' or not module_loaded or not service_ready:
            return {'supported': False, 'reasonCode': 'CAPABILITY_UNKNOWN'}
        if interfaces and any(not interfaces.get(item) for item in required):
            return {'supported': False, 'reasonCode': 'ABI_INCOMPLETE',
                    'capabilities': interfaces}
        zram_ready = bool(interfaces and all(interfaces.get(item) for item in
                                             ('zram_mm_stat', 'cgroupv2',
                                              'memory_reclaim')))
        return {'supported': True, 'reasonCode': 'SUPPORTED',
                'arch': arch, 'release': release, 'pageSize': int(page_size),
                'kernel': kernel, 'ksm': True, 'zram': zram_ready,
                'writeback': bool(zram_ready and interfaces.get('zram_writeback', True))}

    @staticmethod
    def host_release_from_os_release(content):
        """Match Host facts only; never infer support from an MN/repo label."""
        facts = {}
        try:
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                values = shlex.split(value, comments=True)
                if len(values) == 1:
                    facts[key] = values[0].lower()
        except ValueError:
            return 'unknown'
        if (facts.get('ID') == 'helix' and facts.get('VERSION_ID') in ('8.4', '8.4r')
                and 'green obsidian' in ' '.join(facts.get(key, '') for key in
                                               ('VERSION', 'VERSION_CODENAME', 'PRETTY_NAME'))):
            return 'h84r'
        if (facts.get('ID') in ('alinux', 'alinux4') and
                facts.get('VERSION_ID', '').lower().startswith('4')):
            return 'alinux4'
        if (facts.get('ID') in ('kylin', 'kylin-server') and
                facts.get('VERSION_ID', '').lower() in ('v10', '10', '10.0')):
            return 'kylinV10'
        return 'unknown'

    @staticmethod
    def installed_reclaim_candidate(release, running_kernel):
        # A UI restart hint only, never a qualification grant: cgroup v2 is on
        # but the running kernel lacks memory.reclaim while another default
        # boot kernel is installed.
        if (release not in ('h84r', 'alinux4') or
                not os.path.exists('/sys/fs/cgroup/cgroup.controllers') or
                os.path.exists('/sys/fs/cgroup/memory.reclaim')):
            return None
        try:
            output = subprocess.check_output(['grubby', '--default-kernel'], stderr=subprocess.STDOUT)
        except (OSError, subprocess.CalledProcessError):
            return None
        if not isinstance(output, str):
            output = output.decode('utf-8', 'replace')
        candidate = os.path.basename(output.strip())
        if candidate.startswith('vmlinuz-'):
            candidate = candidate[len('vmlinuz-'):]
        if not candidate or candidate == running_kernel or not os.path.isdir('/lib/modules/' + candidate):
            return None
        return candidate

    def _managed_service_installed(self):
        return os.path.isfile('/usr/lib/systemd/system/' + self.MANAGED_ZRAM_UNIT)

    def _managed_service_never_used(self):
        """An installed service that never ran has no state; cold maintenance flows keep theirs."""
        if not self._managed_service_installed() or os.path.exists(self.socket_path):
            return False
        try:
            with open(self.ZRAM_CONFIG, 'r') as stream:
                state_dir = json.load(stream).get('state_dir')
        except (IOError, OSError, ValueError):
            return False
        return isinstance(state_dir, STRING_TYPES) and (
            not os.path.isdir(state_dir) or not os.listdir(state_dir))

    def _activate_managed_service(self):
        """Start and enable the installed, never used ZRAM service on first use."""
        if not self._managed_service_never_used():
            return
        release = 'unknown'
        try:
            with open('/etc/os-release', 'r') as stream:
                release = self.host_release_from_os_release(stream.read())
        except (IOError, OSError):
            pass
        module = '/lib/modules/%s/updates/zstack-zram/zram.ko' % platform.release()
        if release == 'alinux4' and not os.path.exists(module):
            # Install the kmod that owns the running kernel's exact module path.
            subprocess.check_call('export YUM0=%s; yum -y --disablerepo=* --enablerepo=zstack-mn '
                                  '--exclude="kernel*" --setopt=install_weak_deps=False install %s'
                                  % (kvmagent.get_host_yum_release(), shlex.quote(module)), shell=True)
        subprocess.check_call(['systemctl', 'enable', '--now', self.MANAGED_ZRAM_UNIT])
        deadline = time.time() + self.DEFAULT_COMMUNICATION_SECONDS
        while not os.path.exists(self.socket_path):
            if time.time() > deadline:
                raise RuntimeError('MANAGED_MEMORY_SERVICE_START_TIMEOUT')
            time.sleep(1)

    def discover_capabilities(self):
        release = 'unknown'
        try:
            with open('/etc/os-release', 'r') as stream:
                release = self.host_release_from_os_release(stream.read())
        except (IOError, OSError):
            pass
        page_size = os.sysconf('SC_PAGE_SIZE')
        interfaces = {
            'ksm_run': os.path.exists('/sys/kernel/mm/ksm/run'),
            'ksm_pages_to_scan': os.path.exists('/sys/kernel/mm/ksm/pages_to_scan'),
            'ksm_sleep_millisecs': os.path.exists('/sys/kernel/mm/ksm/sleep_millisecs'),
            'ksm_zero_pages': os.path.exists('/sys/kernel/mm/ksm/use_zero_pages'),
            'ksm_zero_pages_counter': os.path.exists('/sys/kernel/mm/ksm/ksm_zero_pages'),
            'zram_mm_stat': os.path.exists('/sys/block/zram0/mm_stat'),
            'zram_writeback': os.path.exists('/sys/block/zram0/writeback'),
            'cgroupv2': os.path.exists('/sys/fs/cgroup/cgroup.controllers'),
            'memory_reclaim': os.path.exists('/sys/fs/cgroup/memory.reclaim'),
            'psi': (os.path.exists('/proc/pressure/memory') and
                    os.path.exists('/proc/pressure/io')),
        }
        arch = platform.machine()
        if arch != 'x86_64':
            return {'supported': False, 'reasonCode': 'UNSUPPORTED_ARCHITECTURE'}
        if release not in ('h84r', 'alinux4', 'kylinV10'):
            return {'supported': False, 'reasonCode': 'UNSUPPORTED_OS_RELEASE'}
        if int(page_size) != 4096:
            return {'supported': False, 'reasonCode': 'UNSUPPORTED_PAGE_SIZE'}
        ksm_required = ('ksm_run', 'ksm_pages_to_scan', 'ksm_sleep_millisecs')
        ksm = all(interfaces.get(item) for item in ksm_required)
        kernel = platform.release()
        qualification = {}
        reason = 'SERVICE_RECLAIM_CAPABILITY_UNKNOWN'
        service_ready = os.path.exists(self.socket_path)
        if service_ready:
            try:
                native = self.service_call('capabilities', {})
                candidate = native.get('reclaim_qualification') if isinstance(native, dict) else None
                if (native.get('abiProfile') == 'zram-service-v1' and native.get('schemaVersion') == 1
                        and isinstance(candidate, dict) and candidate.get('kernel') == kernel
                        and candidate.get('architecture') == 'amd64' and candidate.get('page_size_bytes') == 4096
                        and isinstance(candidate.get('supported'), bool)):
                    qualification = candidate
                    reason = ('SUPPORTED' if candidate['supported'] else
                              candidate.get('reason_code') or 'UNSUPPORTED_RECLAIM_KERNEL')
                    if not candidate['supported'] and reason == 'SUPPORTED':
                        reason = 'UNSUPPORTED_RECLAIM_KERNEL'
            except Exception:
                # Missing/old/unreachable service must not invent ZRAM support
                # or hide the independently usable KSM interface.
                pass
        zram = bool(interfaces.get('zram_mm_stat') and interfaces.get('cgroupv2') and
                     interfaces.get('memory_reclaim') and qualification.get('supported') is True)
        # An installed but inactive service is started by the first ZRAM apply;
        # its full qualification is checked again after activation.
        activation_required = release in ('h84r', 'alinux4') and self._managed_service_never_used()
        if activation_required and interfaces.get('cgroupv2') and interfaces.get('memory_reclaim'):
            zram, reason = True, 'SERVICE_INACTIVE'
        elif not interfaces.get('zram_mm_stat'):
            reason = 'ABI_INCOMPLETE'
        driver = None
        if release == 'alinux4' and not activation_required:
            # A matching kernel/service reply cannot identify the module
            # actually running in memory. Keep disk and loaded identities
            # separate; the shared observer performs no Host mutation.
            driver = zram_driver.inspect(release=release, architecture=arch, kernel=kernel)
            if driver.get('supported') is not True:
                zram = False
                reason = driver.get('reasonCode') or 'ZRAM_DRIVER_UNKNOWN'
        if not interfaces.get('psi'):
            # The managed reclaim host guards cannot qualify without PSI.
            zram, reason = False, 'HOST_PSI_UNAVAILABLE'
        installed_candidate = self.installed_reclaim_candidate(release, kernel)
        reboot_required = not zram and installed_candidate is not None
        if reboot_required:
            reason = 'REBOOT_REQUIRED'
        capabilities = {
            'supported': bool(ksm or zram),
            'reasonCode': 'SUPPORTED' if (ksm or zram) else 'ABI_INCOMPLETE',
            'arch': arch, 'release': release, 'pageSize': int(page_size),
            'kernel': kernel,
            'ksm': ksm,
            'ksmZeroPages': bool(ksm and interfaces.get('ksm_zero_pages')),
            'ksmZeroPagesCounter': bool(ksm and interfaces.get('ksm_zero_pages_counter')),
            'zram': zram,
            'zramReasonCode': reason,
            'rebootRequired': reboot_required,
            'installedCandidateKernel': installed_candidate,
            'reclaimQualification': qualification,
            'writeback': bool(zram and interfaces.get('zram_writeback') and
                              (driver is None or driver.get('writebackSupported') is True)),
            'service': service_ready,
            'serviceActivationRequired': activation_required,
            'interfaces': interfaces,
        }
        if driver is not None:
            capabilities['zramDriver'] = driver
        return capabilities

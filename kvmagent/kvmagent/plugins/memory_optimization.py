# -*- coding: utf-8 -*-
"""Host memory optimisation for the KVM agent.

The management node owns the desired configuration and resends it until the
host reports it applied. The Agent keeps no operation journal: every apply
reads the host, works out the remaining steps and runs them through the
distribution's native KSM units and the ZRAM service's idempotent API.
Destructive pool and backend steps are recorded by the service itself.
"""
import json
import os
import platform
import re
import shlex
import socket
import stat
import subprocess
import tempfile
import time
import errno
import fcntl
import shutil
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
    NativeKsmConfigError, native_sleep_msec, parse_memtotal_kb, render_config)
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


class Converging(Exception):
    """A multi-step change is in progress; the caller resends the request."""
    def __init__(self, reason, retry_after=5):
        Exception.__init__(self, reason)
        self.reason = reason
        self.retry_after = retry_after


class Rejected(Exception):
    """The host refused the change; its current state is kept."""
    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


class MemoryOptimizationPlugin(kvmagent.KvmAgent):
    STATE_PATH = '/memory/optimization/state'
    APPLY_PATH = '/memory/optimization/apply'
    MIGRATION_HOLD_PATH = '/memory/optimization/migration-hold'
    VM_EFFICIENCY_PATH = '/memory/optimization/vm-efficiency'
    ACCOUNTING_PATH = '/memory/optimization/accounting'
    WRITEBACK_BACKENDS_PATH = '/memory/optimization/writeback-backends'

    DEFAULT_SOCKET = '/run/zram-efficiency-admission/control.sock'
    DEFAULT_MONITOR_SOCKET = '/run/zram-efficiency-admission/monitor.sock'
    DEFAULT_REQUEST_BYTES = 1 * 1024 * 1024
    DEFAULT_RESPONSE_BYTES = 16 * 1024 * 1024
    DEFAULT_COMMUNICATION_SECONDS = 30
    KSM_UNIT = 'ksm.service'
    KSM_TUNED_UNIT = 'ksmtuned.service'
    NATIVE_KSM_FILES = ('/usr/sbin/ksmtuned', '/usr/libexec/ksmctl',
                        '/usr/lib/systemd/system/ksm.service',
                        '/usr/lib/systemd/system/ksmtuned.service')
    KSM_PAGES_TO_SCAN = 2000
    KSM_SLEEP_MILLIS = 20
    MANAGED_ZRAM_UNIT = 'zram-memory.service'
    KSM_CONF = '/etc/ksmtuned.conf'
    KSM_LOCK = '/run/zstack/memory-optimization/ksm.writer.lock'
    OPERATION_DIR = '/var/lib/zstack/memory-optimization/operations'
    # Shared with the RPM installer, which must not upgrade the service mid-change.
    HOST_LOCK = '.host-control.flock'
    ZRAM_CONFIG = '/etc/zram-memory/config.json'
    ZRAM_CONFIG_TEMPLATE = '/usr/share/zstack-zram/config.json'
    DRAINED = 'WITHDRAWN_SWAP_INACTIVE_POOL_PRESERVED'
    ACTIVATION_WAIT_REASONS = ('MAINTENANCE_ACTIVATION_NATIVE_NOT_READY', 'MAINTENANCE_ACTIVATION_RUNTIME_NOT_QUIESCENT')
    # The service's DefaultCapacity(); a numeric 50 equals 50.0 in the comparison.
    SERVICE_DEFAULT_CAPACITY = {'logical_capacity': {'percent_of_host': 50},
                                'physical_memory_limit': {'percent_of_logical': 50}}
    PROGRESS_RETRY_SECONDS = 5
    WAIT_RETRY_SECONDS = 30

    def __init__(self, service_call=None):
        super(MemoryOptimizationPlugin, self).__init__()
        self.service_call = service_call or self._call_local_service
        self.config = None
        self.host_uuid = None
        self.socket_path = self.DEFAULT_SOCKET
        self.monitor_socket_path = self.DEFAULT_MONITOR_SOCKET
        self.request_bytes = self.DEFAULT_REQUEST_BYTES
        self.response_bytes = self.DEFAULT_RESPONSE_BYTES
        self.communication_seconds = self.DEFAULT_COMMUNICATION_SECONDS
        self.operation_dir = self.OPERATION_DIR
        self.service_binary = '/usr/local/libexec/zram-efficiency'
        self.zram_config_path = self.ZRAM_CONFIG
        self.zram_config_template_path = self.ZRAM_CONFIG_TEMPLATE

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
        for name, attribute in (('requestBytes', 'request_bytes'),
                                ('responseBytes', 'response_bytes'),
                                ('communicationSeconds', 'communication_seconds')):
            value = config.get(name, getattr(self, attribute))
            integer_budget = name != 'communicationSeconds'
            valid_type = isinstance(value, int) if integer_budget else isinstance(value, (int, float))
            if isinstance(value, bool) or not valid_type or value <= 0:
                raise ValueError('invalid memory service %s' % name)
            setattr(self, attribute, value)
        self.operation_dir = config.get('operationDir', self.operation_dir)
        self.service_binary = config.get('serviceBinary', self.service_binary)
        self.zram_config_path = config.get('zramConfig', self.zram_config_path)

    def start(self):
        self._retire_legacy_records()
        server = kvmagent.get_http_server()
        for path, handler in (
                (self.STATE_PATH, self.state),
                (self.APPLY_PATH, self.apply_request),
                (self.MIGRATION_HOLD_PATH, self.migration_hold),
                (self.VM_EFFICIENCY_PATH, self.vm_efficiency),
                (self.ACCOUNTING_PATH, self.accounting),
                (self.WRITEBACK_BACKENDS_PATH, self.writeback_backends)):
            server.register_async_uri(path, handler)

    def stop(self):
        pass

    def _retire_legacy_records(self):
        """Move an earlier Agent's operation journal aside; nothing reads it now."""
        legacy = [name for name in self._listdir(self.operation_dir)
                  if name not in ('applied-generation', self.HOST_LOCK, 'executors')]
        if not legacy:
            return
        target = '%s-legacy-%d' % (self.operation_dir, int(time.time()))
        os.makedirs(target, 0o700)
        for name in legacy:
            shutil.move(os.path.join(self.operation_dir, name), os.path.join(target, name))
        logger.info('moved %d legacy memory optimisation records to %s' % (len(legacy), target))

    @staticmethod
    def _listdir(path):
        try:
            return os.listdir(path)
        except (IOError, OSError):
            return []

    # ------------------------------------------------------------------ util

    @staticmethod
    def _request_body(req):
        body = req.get(http.REQUEST_BODY, '{}')
        command = jsonobject.loads(body)
        # jsonobject objects expose attributes, while the local service
        # accepts normal JSON objects.
        return json.loads(jsonobject.dumps(command))

    def _reply(self, payload):
        return jsonobject.dumps(payload)

    def _load_host_uuid(self):
        # Do not cache: a later /host/connect may refresh the identity.
        if self.config is not None and kvmagent.HOST_UUID in self.config:
            return self.config[kvmagent.HOST_UUID]
        return self.host_uuid

    def _check_host(self, command):
        if not isinstance(command, dict):
            raise Rejected('INVALID_REQUEST')
        host_uuid = self._load_host_uuid()
        if not host_uuid or command.get('hostUuid') != host_uuid:
            raise Rejected('HOST_IDENTITY_UNKNOWN')
        return host_uuid

    @staticmethod
    def _current_boot_id():
        try:
            with open('/proc/sys/kernel/random/boot_id', 'r') as stream:
                return stream.read().strip()
        except (IOError, OSError):
            return None

    @staticmethod
    def _valid_identifier(value):
        return isinstance(value, STRING_TYPES) and re.match(r'^[A-Za-z0-9_.:-]{1,128}\Z', value) is not None

    @contextmanager
    def _host_lock(self, wait_seconds=None):
        """Serialize host changes between concurrent requests to this Agent."""
        if not os.path.isdir(self.operation_dir):
            os.makedirs(self.operation_dir, 0o700)
        deadline = linux.monotime() + (self.communication_seconds if wait_seconds is None else wait_seconds)
        with open(os.path.join(self.operation_dir, self.HOST_LOCK), 'a') as lock:
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (IOError, OSError) as exc:
                    if exc.errno not in (errno.EAGAIN, errno.EACCES):
                        raise
                    if linux.monotime() >= deadline:
                        raise Converging('HOST_OPERATION_IN_PROGRESS')
                    time.sleep(0.1)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _atomic_write(path, data, mode=0o600):
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory, 0o700)
        fd, temporary = tempfile.mkstemp(prefix='.memopt-', dir=directory)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.rename(temporary, path)
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise

    def _applied_generation(self):
        try:
            with open(os.path.join(self.operation_dir, 'applied-generation'), 'r') as stream:
                value = stream.read().strip()
            return int(value) if re.match(r'^[0-9]{1,19}\Z', value) else None
        except (IOError, OSError):
            return None

    def _record_applied_generation(self, generation):
        self._atomic_write(os.path.join(self.operation_dir, 'applied-generation'),
                           ('%d\n' % generation).encode('utf-8'))

    @staticmethod
    def _bounded_command_output(command, timeout_seconds):
        """Run a small local command with a Python 2-compatible poll deadline."""
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = linux.monotime() + timeout_seconds
        while process.poll() is None:
            remaining = deadline - linux.monotime()
            if remaining <= 0:
                # This terminates only the client process (for example systemctl).
                for terminate in (process.terminate, process.kill):
                    try:
                        terminate()
                    except OSError:
                        pass
                    if process.poll() is not None:
                        break
                process.wait()
                raise RuntimeError('BOUNDED_COMMAND_TIMEOUT')
            time.sleep(min(0.05, remaining))
        output = process.communicate()[0]
        if process.returncode != 0:
            error = subprocess.CalledProcessError(process.returncode, command)
            error.output = output
            raise error
        if not isinstance(output, STRING_TYPES):
            output = output.decode('utf-8', 'replace')
        return output

    def _unit_properties(self, unit, *names):
        try:
            output = self._bounded_command_output(
                ['systemctl', 'show', unit] + ['--property=%s' % name for name in names], 10)
        except (IOError, OSError, RuntimeError, subprocess.CalledProcessError):
            return {}
        return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)

    def _service_unit_state(self):
        """Return active, starting, inactive, failed or unknown for the managed unit."""
        values = self._unit_properties(self.MANAGED_ZRAM_UNIT, 'Id', 'ActiveState', 'SubState')
        if values.get('Id') != self.MANAGED_ZRAM_UNIT:
            return 'unknown'
        active, sub = values.get('ActiveState'), values.get('SubState')
        if active == 'active' and sub in ('running', 'listening'):
            return 'active'
        if active in ('activating', 'reloading'):
            return 'starting'
        if active == 'inactive':
            return 'inactive'
        if active == 'failed':
            return 'failed'
        return 'unknown'

    def _executor_state(self, unit):
        """Return (running|exited|absent|unknown, exit status) for a transient executor."""
        values = self._unit_properties(unit, 'LoadState', 'ActiveState', 'SubState',
                                       'ExecMainCode', 'ExecMainStatus')
        if not values:
            return 'unknown', None
        if values.get('LoadState') == 'not-found':
            return 'absent', None
        active, sub, status = values.get('ActiveState'), values.get('SubState'), values.get('ExecMainStatus')
        if active in ('activating', 'deactivating') or (active == 'active' and sub != 'exited'):
            return 'running', None
        if status and status.isdigit() and (active == 'failed' or sub in ('exited', 'dead')):
            return 'exited', int(status)
        return 'unknown', None

    def _run_executor(self, unit, argument, request=None):
        """Start one service CLI step as a transient unit; its files live under executors/."""
        directory = os.path.join(self.operation_dir, 'executors')
        paths = dict((kind, os.path.join(directory, '%s.%s' % (unit, kind)))
                     for kind in ('request', 'receipt', 'stderr'))
        command = ['systemd-run', '--unit=%s' % unit, '--no-block',
                   '--property=UMask=0077', '--property=RemainAfterExit=yes',
                   '--property=TimeoutStartSec=infinity',
                   '--property=StandardOutput=file:%s' % paths['receipt'],
                   '--property=StandardError=file:%s' % paths['stderr']]
        if request is not None:
            self._atomic_write(paths['request'], json.dumps(request, sort_keys=True).encode('utf-8'))
            command.append('--property=StandardInput=file:%s' % paths['request'])
        elif not os.path.isdir(directory):
            os.makedirs(directory, 0o700)
        command += [self.service_binary, '--config', self.zram_config_path, argument]
        subprocess.check_call(command)
        return paths

    def _executor_error(self, unit, default):
        """Read the service CLI's coded error from its stderr record."""
        path = os.path.join(self.operation_dir, 'executors', '%s.stderr' % unit)
        try:
            with open(path, 'r') as stream:
                value = json.load(stream)
            raw = value.get('error') if isinstance(value, dict) else None
            code = raw.split(': ', 1)[0] if isinstance(raw, STRING_TYPES) else None
            if code and re.match(r'^[A-Z][A-Z0-9_]{2,127}\Z', code):
                return code
        except (IOError, OSError, ValueError, TypeError):
            pass
        return default

    # ------------------------------------------------------------- handlers

    @kvmagent.replyerror
    def state(self, req):
        command = self._request_body(req)
        try:
            host_uuid = self._check_host(command)
        except Rejected as exc:
            return self._reply({'success': False, 'status': 'Failed', 'reasonCode': exc.reason, 'state': {}})
        return self._reply({'success': True, 'status': 'Succeeded', 'hostUuid': host_uuid,
                            'state': self._observe()})

    def apply_request(self, req):
        return self._reply(self.apply(self._request_body(req)))

    def apply(self, command):
        """Converge the host to the desired configuration; safe to resend."""
        generation = command.get('generation') if isinstance(command, dict) else None
        result = {'generation': generation}
        try:
            self._check_host(command)
            if isinstance(generation, bool) or not isinstance(generation, INTEGER_TYPES) or generation < 1:
                raise Rejected('INVALID_GENERATION')
            desired = self._desired(command.get('desired'))
            with self._host_lock():
                # A delayed request must not take the Host back to an older configuration.
                applied = self._applied_generation()
                if applied is not None and generation < applied:
                    raise Rejected('STALE_GENERATION')
                self._converge(desired, generation)
                self._record_applied_generation(generation)
            result.update({'success': True, 'status': 'Succeeded'})
        except Converging as exc:
            result.update({'success': True, 'status': 'Converging', 'reasonCode': exc.reason,
                           'retryAfterSeconds': exc.retry_after})
        except Rejected as exc:
            result.update({'success': False, 'status': 'Failed', 'reasonCode': exc.reason})
        except Exception as exc:
            logger.warn('memory optimisation apply did not complete: %s' % exc)
            reason = str(exc)
            result.update({'success': False, 'status': 'Failed',
                           'reasonCode': reason if re.match(r'^[A-Z][A-Z0-9_:]+\Z', reason) else 'MEMORY_APPLY_FAILED',
                           'reason': reason})
        result['appliedGeneration'] = self._applied_generation()
        try:
            result['state'] = self._observe()
        except Exception as exc:
            result['state'] = {'reason': str(exc)}
        return result

    @staticmethod
    def _desired(value):
        if not isinstance(value, dict) or value.get('control') not in ('active', 'paused', 'drained'):
            raise Rejected('INVALID_DESIRED_CONFIGURATION')
        desired = {'control': value['control']}
        for section, fields in (('ksm', ('enabled', 'zeroPagesEnabled')),
                                ('zram', ('enabled', 'logicalCapacityBytes', 'ramLimitBytes')),
                                ('writeback', ('enabled',))):
            given = value.get(section) or {}
            if not isinstance(given, dict):
                raise Rejected('INVALID_DESIRED_CONFIGURATION')
            desired[section] = {}
            for field in fields:
                item = given.get(field)
                if field.endswith('Bytes'):
                    if item is not None and (isinstance(item, bool) or not isinstance(item, INTEGER_TYPES) or
                                             item <= 0 or item % 4096):
                        raise Rejected('INVALID_DESIRED_CONFIGURATION')
                elif item not in (None, True, False):
                    raise Rejected('INVALID_DESIRED_CONFIGURATION')
                desired[section][field] = item
        return desired

    @kvmagent.replyerror
    def migration_hold(self, req):
        command = self._request_body(req)
        try:
            self._check_host(command)
            with self._host_lock():
                result = self._service('migration-hold', {
                    'action': command.get('holdAction', 'acquire'),
                    'operation_id': command.get('operationUuid'),
                    'pool_generation': command.get('poolGeneration', '')})
            reply = {'success': True, 'status': 'Succeeded', 'state': result}
        except Rejected as exc:
            reply = {'success': False, 'status': 'Failed', 'reasonCode': exc.reason, 'state': {}}
        except Exception as exc:
            reply = {'success': False, 'status': 'Failed', 'reasonCode': 'MIGRATION_HOLD_FAILED',
                     'reason': str(exc), 'state': {}}
        reply['operationUuid'] = command.get('operationUuid') if isinstance(command, dict) else None
        return self._reply(reply)

    @kvmagent.replyerror
    def vm_efficiency(self, req):
        """Bind a VM's service policy to its running instance, or exclude it."""
        command = self._request_body(req)
        reply = {'operationUuid': command.get('operationUuid') if isinstance(command, dict) else None}
        try:
            self._check_host(command)
            if command.get('action') == 'revoke':
                # The VM has left this host; the service binds policy to the
                # instance generation, so nothing remains to undo here.
                reply.update({'success': True, 'status': 'Succeeded', 'state': {'phase': 'REVOKED'}})
                return self._reply(reply)
            vm_uuid = command.get('resourceUuid')
            generation = command.get('expectedInstanceGeneration')
            if not self._valid_identifier(vm_uuid) or not isinstance(generation, STRING_TYPES) or not generation:
                raise Rejected('VM_IDENTITY_REQUIRED')
            participation = command.get('participation') or 'allow'
            # Platform allow/inherit is the service's durable auto rule; deny excludes the VM.
            mode = 'deny' if participation == 'deny' else 'auto'
            result = self._service('vm-policy', {'expected_instance_generation': generation,
                                                 'mode': mode, 'cpu_rule': command.get('cpuRule')},
                                   resource=vm_uuid)
            reply.update({'success': True, 'status': 'Succeeded', 'state': result})
        except Rejected as exc:
            reply.update({'success': False, 'status': 'Failed', 'reasonCode': exc.reason, 'state': {}})
        except Exception as exc:
            reply.update({'success': False, 'status': 'Failed', 'reasonCode': 'VM_POLICY_FAILED',
                          'reason': str(exc), 'state': {}})
        return self._reply(reply)

    @kvmagent.replyerror
    def accounting(self, req):
        command = self._request_body(req)
        try:
            self._check_host(command)
            report = _accounting_wire_identity(self._service('accounting', {}))
            result = {'success': True, 'status': 'Succeeded', 'state': report,
                      'hostUuid': command.get('hostUuid')}
        except Exception as exc:
            result = {'success': False, 'status': 'Failed', 'state': {},
                      'reason': str(exc), 'hostUuid': command.get('hostUuid') if isinstance(command, dict) else None}
        return self._reply(result)

    @kvmagent.replyerror
    def writeback_backends(self, req):
        command = self._request_body(req)
        host_uuid = command.get('hostUuid') if isinstance(command, dict) else None
        try:
            self._check_host(command)
            if command.get('action') == 'prepare':
                return self._reply(self._prepare_writeback(command))
            result = {'success': True, 'status': 'Succeeded', 'hostUuid': host_uuid,
                      'state': self._writeback_inventory(host_uuid)}
        except Rejected as exc:
            result = {'success': False, 'status': 'Failed', 'reasonCode': exc.reason,
                      'state': {}, 'hostUuid': host_uuid}
        except Exception as exc:
            result = {'success': False, 'status': 'Failed', 'reasonCode': 'WRITEBACK_INVENTORY_FAILED',
                      'reason': str(exc), 'state': {}, 'hostUuid': host_uuid}
        return self._reply(result)

    # ------------------------------------------------------------ service

    SERVICE_ROUTES = {
        'status': ('GET', '/v1/status', False),
        'capabilities': ('GET', '/v1/capabilities', False),
        'backend-view': ('GET', '/v1/zram/backend', False),
        'tuning-state': ('GET', '/v1/zram/tuning', False),
        'capacity-state': ('GET', '/v1/zram/config', False),
        'host-cpu-state': ('GET', '/v1/efficiency/policy', False),
        'accounting': ('GET', '/v1/memory/accounting', False),
        'backend-maintenance': ('GET', '/v1/backend-maintenance', False),
        'zram-pool-maintenance': ('GET', '/v1/zram-pool-maintenance', False),
        'vm-identities': ('POST', '/v1/vm-identities', True),
        'lifecycle-pause': ('POST', '/v1/lifecycle/pause', True),
        'lifecycle-activate-maintenance': ('POST', '/v1/lifecycle/activate-maintenance', True),
        'migration-hold': ('POST', '/v1/migration-hold', True),
        'backend-maintenance-finalize': ('POST', '/v1/backend-maintenance/finalize', True),
        'zram-pool-maintenance-finalize': ('POST', '/v1/zram-pool-maintenance/finalize', True),
        'tuning': ('PUT', '/v1/zram/tuning', True),
        'capacity': ('PUT', '/v1/zram/config', True),
        'host-cpu': ('PUT', '/v1/efficiency/policy', True),
        'vm-policy': ('PUT', '/v1/vms/%s/efficiency', True),
    }

    def _call_local_service(self, action, command):
        """Send one JSON request to the host service over its Unix socket."""
        method, path, control = self.SERVICE_ROUTES[action]
        command = dict(command or {})
        resource = command.pop('_resource', None)
        if '%s' in path:
            path = path % resource
        data = b'' if method == 'GET' else json.dumps(command).encode('utf-8')
        if len(data) > self.request_bytes:
            raise IOError('memory service request too large')
        conn = _UnixHTTPConnection(self.socket_path if control else self.monitor_socket_path,
                                   timeout=self.communication_seconds)
        try:
            conn.request(method, path, body=data,
                         headers={'Host': 'localhost', 'Content-Type': 'application/json',
                                  'Connection': 'close'})
            response = conn.getresponse()
            payload = response.read(self.response_bytes + 1)
            if len(payload) > self.response_bytes:
                raise IOError('memory service response too large')
            result = json.loads(payload.decode('utf-8'))
            if isinstance(result, dict):
                result['_http_status'] = response.status
            return result
        finally:
            conn.close()

    def _service_raw(self, action, payload=None, resource=None):
        payload = dict(payload or {})
        if resource is not None:
            payload['_resource'] = resource
        result = self.service_call(action, payload)
        if not isinstance(result, dict):
            raise RuntimeError('INVALID_SERVICE_RESPONSE:%s' % action)
        return result

    def _service(self, action, payload=None, resource=None):
        """Call the service and raise on any HTTP or service failure."""
        result = self._service_raw(action, payload, resource)
        code = result.get('_http_status')
        if isinstance(code, int) and code >= 300:
            raise Rejected(str(result.get('error') or 'SERVICE_%s_FAILED' % action.upper()))
        result = dict(result)
        result.pop('_http_status', None)
        return result

    def _service_available(self):
        return os.path.exists(self.socket_path)

    # --------------------------------------------------------- capabilities

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
        """An installed service that never ran has no state."""
        if not self._managed_service_installed() or self._service_available():
            return False
        try:
            with open(self.zram_config_path, 'r') as stream:
                state_dir = json.load(stream).get('state_dir')
        except (IOError, OSError, ValueError):
            return False
        return isinstance(state_dir, STRING_TYPES) and (
            not os.path.isdir(state_dir) or not os.listdir(state_dir))

    def _activate_managed_service(self):
        """Start and enable the installed, never used ZRAM service on first use."""
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
        while not self._service_available():
            if time.time() > deadline:
                raise Converging('SERVICE_STARTING')
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
        ksm = all(interfaces.get(item) for item in ('ksm_run', 'ksm_pages_to_scan', 'ksm_sleep_millisecs'))
        kernel = platform.release()
        qualification = {}
        reason = 'SERVICE_RECLAIM_CAPABILITY_UNKNOWN'
        service_ready = self._service_available()
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
            # Keep disk and loaded module identities separate; the shared
            # observer performs no Host mutation.
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

    # ----------------------------------------------------------- native KSM

    @staticmethod
    def _read_ksm_sysfs(name):
        if name not in ('run', 'pages_to_scan', 'sleep_millisecs', 'use_zero_pages'):
            raise ValueError('KSM_SYSFS_ATTRIBUTE_INVALID')
        with open('/sys/kernel/mm/ksm/%s' % name, 'r') as stream:
            value = stream.read().strip()
        if not re.match(r'^(0|[1-9][0-9]*)\Z', value):
            raise ValueError('KSM_SYSFS_READBACK_INVALID:%s' % name)
        return value

    def _read_ksm_zero_pages(self):
        """Distinguish a missing optional sysfs interface from read failure."""
        try:
            return self._read_ksm_sysfs('use_zero_pages')
        except (IOError, OSError) as exc:
            if exc.errno == errno.ENOENT:
                return 'unsupported'
            raise

    @staticmethod
    def _write_ksm_sysfs(name, value):
        if name in ('run', 'use_zero_pages'):
            valid = value in ('0', '1')
        elif name in ('pages_to_scan', 'sleep_millisecs'):
            valid = isinstance(value, STRING_TYPES) and re.match(r'^[1-9][0-9]*\Z', value) is not None
        else:
            valid = False
        if not valid:
            raise ValueError('KSM_SYSFS_WRITE_INVALID')
        with open('/sys/kernel/mm/ksm/%s' % name, 'w') as stream:
            stream.write(value)
            stream.flush()
        if MemoryOptimizationPlugin._read_ksm_sysfs(name) != value:
            raise RuntimeError('KSM_SYSFS_WRITE_READBACK_MISMATCH:%s' % name)


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
        value = output.strip().splitlines()[-1] if output.strip() else ''
        if operation == 'active':
            return value if value in ('active', 'inactive', 'failed', 'activating', 'deactivating') else None
        return value if value in ('enabled', 'enabled-runtime', 'disabled', 'static',
                                  'indirect', 'masked', 'masked-runtime') else None

    @contextmanager
    def _ksm_writer_lock(self):
        lock_dir = os.path.dirname(self.KSM_LOCK)
        if not os.path.isdir(lock_dir):
            os.makedirs(lock_dir)
        deadline = linux.monotime() + 5
        with open(self.KSM_LOCK, 'a') as lock:
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (IOError, OSError) as exc:
                    if exc.errno not in (errno.EAGAIN, errno.EACCES) or linux.monotime() >= deadline:
                        raise RuntimeError('KSM_WRITER_LOCK_UNAVAILABLE')
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _publish_ksm_config(self, content):
        mode = stat.S_IMODE(os.stat(self.KSM_CONF).st_mode) if os.path.exists(self.KSM_CONF) else 0o644
        with self._ksm_writer_lock():
            self._atomic_write(self.KSM_CONF, content.encode('utf-8'), mode)

    def _observe_ksm(self):
        native = {'run': self._read_ksm_sysfs('run'),
                  'pages_to_scan': self._read_ksm_sysfs('pages_to_scan'),
                  'sleep_millisecs': self._read_ksm_sysfs('sleep_millisecs'),
                  'use_zero_pages': self._read_ksm_zero_pages()}
        ksm_active = self._native_service_state(self.KSM_UNIT, 'active')
        tuned_active = self._native_service_state(self.KSM_TUNED_UNIT, 'active')
        ksm = {'enabled': (True if ksm_active == 'active' and tuned_active == 'active' else
                           False if ksm_active == 'inactive' and tuned_active == 'inactive' else None),
               'serviceState': ksm_active or 'unknown',
               'tunedServiceState': tuned_active or 'unknown',
               'scanning': native['run'] == '1',
               'pagesToScan': int(native['pages_to_scan']),
               'sleepMillis': int(native['sleep_millisecs'])}
        if native['use_zero_pages'] in ('0', '1'):
            ksm['zeroPagesEnabled'] = native['use_zero_pages'] == '1'
        return ksm

    def _converge_ksm(self, ksm, control):
        """Run KSM through the vendor units; an unmanaged setting is left alone."""
        enabled, zero = ksm.get('enabled'), ksm.get('zeroPagesEnabled')
        if enabled is None and zero is None:
            return
        if not all(os.path.isfile(path) for path in self.NATIVE_KSM_FILES):
            raise Rejected('KSM_NATIVE_PROFILE_UNSUPPORTED')
        zero_value = self._read_ksm_zero_pages()
        if zero is True and zero_value == 'unsupported':
            raise Rejected('KSM_ZERO_PAGES_UNSUPPORTED')
        if zero is not None and zero_value != 'unsupported':
            zero_value = '1' if zero else '0'
        # A paused or drained host stops the KSM it manages; resuming restarts it.
        if enabled is True and control != 'active':
            enabled = False
        pages, sleep = self.KSM_PAGES_TO_SCAN, self.KSM_SLEEP_MILLIS
        current_tuned = self._native_service_state(self.KSM_TUNED_UNIT, 'active')
        if enabled is not None:
            try:
                with open('/proc/meminfo', 'r') as stream:
                    memtotal_kb = parse_memtotal_kb(stream.read())
                try:
                    with open(self.KSM_CONF, 'r') as stream:
                        existing = stream.read()
                except IOError as exc:
                    if exc.errno != errno.ENOENT:
                        raise
                    existing = ''
                content = render_config(existing, 1, pages, native_sleep_msec(sleep, memtotal_kb))
            except NativeKsmConfigError as exc:
                raise Rejected(str(exc))
            if enabled:
                if content != existing:
                    self._publish_ksm_config(content)
                subprocess.check_call(['systemctl', 'start', self.KSM_UNIT])
                # ksmtuned waits for its first monitor interval; apply the values now.
                self._write_ksm_sysfs('pages_to_scan', str(pages))
                self._write_ksm_sysfs('sleep_millisecs', str(sleep))
                self._write_ksm_sysfs('run', '1')
                if current_tuned != 'active':
                    subprocess.check_call(['systemctl', 'start', self.KSM_TUNED_UNIT])
            else:
                subprocess.check_call(['systemctl', 'stop', self.KSM_TUNED_UNIT])
                subprocess.check_call(['systemctl', 'stop', self.KSM_UNIT])
                if content != existing:
                    self._publish_ksm_config(content)
                self._write_ksm_sysfs('run', '0')
        if zero is not None and zero_value in ('0', '1') and self._read_ksm_zero_pages() != zero_value:
            self._write_ksm_sysfs('use_zero_pages', zero_value)
        expected_run = {True: '1', False: '0'}.get(enabled)
        if expected_run is not None and self._read_ksm_sysfs('run') != expected_run:
            raise RuntimeError('KSM_RUN_NOT_APPLIED')

    # --------------------------------------------------------- observation

    def _read_service_config(self):
        with open(self.zram_config_path, 'r') as stream:
            config = json.load(stream)
        if not isinstance(config, dict):
            raise ValueError('SERVICE_CONFIG_INVALID')
        return config

    def _drain_check(self):
        """The service's read-only native drain check; valid only while the unit is stopped."""
        try:
            output = self._bounded_command_output(
                [self.service_binary, '--config', self.zram_config_path, '--drain-check'], 30)
            native = json.loads(output)
        except subprocess.CalledProcessError as failed:
            # The service reports why it cannot check, for example a backend to reclaim after a reboot.
            try:
                native = json.loads(failed.output)
            except (TypeError, ValueError):
                return None
            return native if isinstance(native, dict) and native.get('error') else None
        except (IOError, OSError, ValueError, RuntimeError):
            return None
        return native if isinstance(native, dict) else None

    def _receipt(self, kind):
        """Read a maintenance receipt from the service, or offline while it is stopped."""
        action = {'pool': 'zram-pool-maintenance', 'backend': 'backend-maintenance'}[kind]
        if self._service_available() and self._service_unit_state() == 'active':
            try:
                if kind == 'backend':
                    plugin = self

                    class _Client(object):
                        def get(self, path):
                            return plugin._service(action, {})
                    return read_backend_maintenance_status(_Client())
                receipt = self._service(action, {})
                if receipt.get('stage'):
                    return receipt
            except Exception:
                pass
        argument = {'pool': '--zram-pool-preparation-status', 'backend': '--backend-maintenance-status'}[kind]
        try:
            receipt = json.loads(self._bounded_command_output(
                [self.service_binary, '--config', self.zram_config_path, argument], 30))
        except (IOError, OSError, ValueError, RuntimeError, subprocess.CalledProcessError):
            raise Converging('%s_MAINTENANCE_STATUS_UNKNOWN' % kind.upper())
        if not isinstance(receipt, dict) or not receipt.get('stage'):
            raise Converging('%s_MAINTENANCE_STATUS_UNKNOWN' % kind.upper())
        return receipt

    def _observe(self):
        """Report the host as it is; unknown values are omitted, never zero."""
        state = {'bootId': self._current_boot_id(), 'sampleTime': int(time.time() * 1000),
                 'appliedGeneration': self._applied_generation()}
        try:
            state['capabilities'] = self.discover_capabilities()
        except Exception as exc:
            state['capabilities'] = {'supported': None, 'reasonCode': 'CAPABILITY_UNKNOWN', 'reason': str(exc)}
        try:
            state['ksm'] = self._observe_ksm()
        except Exception as exc:
            state['ksm'] = {'reason': str(exc)}
        unit = self._service_unit_state() if self._managed_service_installed() else 'absent'
        zram = {'serviceState': unit}
        state['zram'] = zram
        native_vms = None
        if unit == 'active' and self._service_available():
            try:
                status = self._service('status')
                pool = status.get('host_zram') or {}
                lifecycle = status.get('lifecycle') or {}
                zram.update({'poolGeneration': pool.get('pool_generation') or None,
                             'pool': pool, 'lifecycle': lifecycle,
                             'paused': lifecycle.get('paused'),
                             'maintenance': status.get('maintenance_blocks_activation'),
                             'pendingOperations': status.get('pending_operations') or [],
                             'mode': status.get('mode')})
                native_vms = status.pop('vms', None)
                status.pop('pool', None)
                zram['status'] = status
                zram['efficiencyEnabled'] = self._service('host-cpu-state').get('efficiency_enabled')
                zram['capacity'] = self._service('capacity-state')
                settings = (self._service('tuning-state').get('settings') or {})
                state['writeback'] = {'enabled': (settings.get('writeback') or {}).get('enabled'),
                                      'backend': status.get('backend_resource')}
            except Exception as exc:
                zram['reason'] = str(exc)
        state['control'] = self._observed_control(unit, zram)
        state['managed'] = unit == 'active'
        state['vms'], state['inventoryComplete'] = self._complete_vm_inventory(native_vms)
        return state

    def _observed_control(self, unit, zram):
        if unit == 'active':
            if zram.get('maintenance') or zram.get('paused'):
                return 'paused'
            return 'active' if zram.get('lifecycle') else 'unknown'
        if unit in ('inactive', 'failed'):
            # The check takes the service's state lock, which a running apply may be using.
            try:
                with self._host_lock(wait_seconds=0):
                    native = self._drain_check()
            except Converging:
                return 'unknown'
            if isinstance(native, dict) and native.get('state') == self.DRAINED:
                return 'drained'
            return 'stopped'
        return 'absent' if unit == 'absent' else 'unknown'

    def _complete_vm_inventory(self, native_vms):
        native_vms = native_vms if isinstance(native_vms, dict) else {}
        domains, complete = self._libvirt_vm_generations()
        if not complete:
            return native_vms, False
        inventory = dict((key, {'identityReason': 'VM_IDENTITY_UNAVAILABLE'}) for key in domains)
        if not domains or not self._service_available():
            return inventory, True
        # Batch by the existing transport byte budget, not a VM count limit.
        batches, batch = [], []
        empty = len(json.dumps({'vm_uuids': []}).encode('utf-8'))
        size = empty
        for key in sorted(domains):
            extra = len(json.dumps(key).encode('utf-8')) + (2 if batch else 0)
            if batch and size + extra > self.request_bytes:
                batches.append(batch)
                batch, size = [], empty
                extra = len(json.dumps(key).encode('utf-8'))
            batch.append(key)
            size += extra
        if batch:
            batches.append(batch)
        for batch in batches:
            try:
                response = self.service_call('vm-identities', {'vm_uuids': batch})
                identities = dict((_product_vm_uuid(key), value) for key, value in
                                  (response.get('identities') or {}).items())
            except Exception:
                # Present but unresolvable is not absent and is not an old
                # generation. MN must refuse lifecycle changes for that VM.
                continue
            for key in batch:
                identity = identities.get(key)
                if not isinstance(identity, dict) or _product_vm_uuid(identity.get('uuid')) != key:
                    continue
                generation = identity.get('instance_generation')
                if not isinstance(generation, STRING_TYPES) or not generation:
                    continue
                previous = native_vms.get(key) or {}
                previous_identity = (previous.get('stats') or {}).get('identity') or {}
                # Keep sampled fields only for the same verified process incarnation.
                item = dict(previous) if previous_identity.get('instance_generation') == generation else {}
                item['instanceGeneration'] = generation
                item['identity'] = _accounting_wire_identity(identity)
                inventory[key] = item
        return inventory, True

    @staticmethod
    def _libvirt_vm_generations():
        """Running domains; the identity of each is resolved by the service."""
        try:
            import libvirt
            conn = libvirt.openReadOnly(None)
            try:
                result = {}
                for domain in conn.listAllDomains(0):
                    if domain.isActive():
                        vm_uuid = _product_vm_uuid(domain.UUIDString())
                        result[vm_uuid] = {'instanceGeneration': '%s:%s' % (vm_uuid, domain.ID())}
                return result, True
            finally:
                conn.close()
        except Exception:
            return {}, False

    # ----------------------------------------------------------- converge

    def _converge(self, desired, generation):
        capabilities = self.discover_capabilities()
        zram_wanted = desired['zram']['enabled'] is True
        writeback_wanted = desired['writeback']['enabled'] is True
        if desired['ksm']['enabled'] is True and not capabilities.get('ksm'):
            raise Rejected('KSM_UNSUPPORTED')
        interfaces = capabilities.get('interfaces') or {}
        unknown = (capabilities.get('zramReasonCode') == 'SERVICE_RECLAIM_CAPABILITY_UNKNOWN'
                   and interfaces.get('cgroupv2') and interfaces.get('memory_reclaim'))
        if (zram_wanted or writeback_wanted) and not capabilities.get('zram') and not unknown:
            # A stopped (e.g. drained) service cannot report its qualification; it checks
            # the kernel again when it starts, so only a known verdict is a rejection.
            raise Rejected(capabilities.get('zramReasonCode') or 'ZRAM_UNSUPPORTED')
        if writeback_wanted and not zram_wanted:
            raise Rejected('WRITEBACK_REQUIRES_ZRAM')
        control = desired['control']
        self._converge_ksm(desired['ksm'], control)
        if not self._managed_service_installed():
            return
        if not self._managed_service_never_used():
            # A maintenance step the service has recorded is finished before anything else.
            self._finish_recorded_maintenance()
        unit = self._service_unit_state()
        if unit == 'starting':
            raise Converging('SERVICE_STARTING')
        if unit in ('inactive', 'failed') and zram_wanted and self._backend_reclaim_required():
            # A reboot left the backend claimed in the earlier boot; prepare the same disk again.
            self._start_backend_maintenance(self._reboot_backend_request(generation))
        drained = unit in ('inactive', 'failed') and self._is_drained()
        if control == 'drained':
            if not drained:
                self._drain(generation)
            return
        if drained:
            if not zram_wanted or control != 'active':
                return
            # Resume, or the capacity rebuild that drained this pool.
            self._prepare_pool_after_drain(generation)
        if not (zram_wanted or self._service_available()):
            return
        if zram_wanted:
            self._ensure_service(capabilities)
        self._converge_service(desired, generation, control)

    def _is_drained(self):
        native = self._drain_check()
        return isinstance(native, dict) and native.get('state') == self.DRAINED

    def _ensure_service(self, capabilities):
        if self._managed_service_never_used() or capabilities.get('serviceActivationRequired'):
            self._activate_managed_service()
        unit = self._service_unit_state()
        if unit != 'active':
            self._start_service()
        self._authorize_reclaim()

    def _start_service(self):
        try:
            self._bounded_command_output(['systemctl', 'start', self.MANAGED_ZRAM_UNIT], 30)
        except (IOError, OSError, RuntimeError, subprocess.CalledProcessError):
            pass
        unit = self._service_unit_state()
        if unit == 'starting' or (unit == 'active' and not self._service_available()):
            raise Converging('SERVICE_STARTING')
        if unit != 'active':
            raise Rejected('MEMORY_SERVICE_START_FAILED')

    def _authorize_reclaim(self):
        """The packaged config starts in observe mode; the first ZRAM enable authorizes reclaim."""
        config = self._read_service_config()
        if config.get('managed') is not True:
            raise Rejected('SERVICE_CONFIG_NOT_MANAGED')
        if config.get('mode') == 'reclaim' and config.get('resource_authorized') is True:
            return
        if config.get('mode') != 'observe' or config.get('resource_authorized') is not False:
            raise Rejected('SERVICE_CONFIG_UNEXPECTED')
        config['mode'] = 'reclaim'
        config['resource_authorized'] = True
        self._atomic_write(self.zram_config_path,
                           json.dumps(config, sort_keys=True, indent=2).encode('utf-8') + b'\n')
        try:
            self._bounded_command_output(['systemctl', 'restart', self.MANAGED_ZRAM_UNIT], 30)
        except (IOError, OSError, RuntimeError, subprocess.CalledProcessError):
            pass
        raise Converging('SERVICE_STARTING')

    def _converge_service(self, desired, generation, control):
        zram, writeback = desired['zram'], desired['writeback']
        status = self._service('status')
        lifecycle = status.get('lifecycle') or {}
        pool_generation = (status.get('host_zram') or {}).get('pool_generation')
        cpu = self._service('host-cpu-state')
        efficiency = bool(zram['enabled'] or writeback['enabled'])
        changes = self._service_changes(zram, writeback, efficiency, cpu)
        if changes and cpu.get('efficiency_enabled') is True:
            # Stop reclaim while the pool, tuning or VM scope change underneath it.
            self._set_efficiency(cpu, False)
        if 'capacity' in changes:
            self._service('capacity', {
                'logical_capacity': self._capacity_value(zram['logicalCapacityBytes']),
                'physical_memory_limit': self._capacity_value(zram['ramLimitBytes'])})
        if 'tuning' in changes:
            self._set_writeback(writeback['enabled'] is True)
        if efficiency:
            capacity = self._service('capacity-state')
            if capacity.get('apply_state') not in (None, 'APPLIED') and pool_generation:
                # A live pool takes a new capacity only through drain and rebuild.
                self._drain(generation)
                raise Converging('CAPACITY_MAINTENANCE')
        self._set_efficiency(cpu, efficiency)
        if control == 'paused':
            if lifecycle.get('paused') is not True:
                self._service('lifecycle-pause', {'action': 'pause'})
            return
        if lifecycle.get('paused') is True:
            if not pool_generation and self._maintenance_prepared():
                # A rebuilt pool opens only through the service's activation checks.
                self._activate_after_maintenance(generation)
            else:
                self._service('lifecycle-pause', {'action': 'resume'})
        if zram['enabled'] is True and not pool_generation:
            if not (self._service('status').get('host_zram') or {}).get('pool_generation'):
                raise Converging('WAITING_FOR_POOL', self.WAIT_RETRY_SECONDS)

    def _service_changes(self, zram, writeback, efficiency, cpu):
        changes = []
        if zram['enabled'] is not None and efficiency:
            desired = (self._service('capacity-state').get('desired') or {}).get('configured') or {}
            for side, value in (('logical_capacity', zram['logicalCapacityBytes']),
                                ('physical_memory_limit', zram['ramLimitBytes'])):
                if not self._same_capacity(side, desired.get(side) or {}, self._capacity_value(value)):
                    changes.append('capacity')
        if writeback['enabled'] is not None:
            settings = self._service('tuning-state').get('settings') or {}
            if (settings.get('writeback') or {}).get('enabled') is not (writeback['enabled'] is True):
                changes.append('tuning')
        return sorted(set(changes))

    @classmethod
    def _same_capacity(cls, side, configured, wanted):
        # A side without a unit is the service default, which the service stores as its percentage.
        if not wanted:
            return configured == {} or configured == cls.SERVICE_DEFAULT_CAPACITY[side]
        return configured == wanted

    @staticmethod
    def _capacity_value(value):
        # A side without a unit restores the service default.
        return {'bytes': value} if value is not None else {}

    def _set_efficiency(self, cpu, enabled):
        if cpu.get('efficiency_enabled') is enabled:
            return
        self._service('host-cpu', {'efficiency_enabled': enabled,
                                   'idle_cpu_threshold_percent': cpu.get('idle_cpu_threshold_percent', 5),
                                   'idle_duration_seconds': cpu.get('idle_duration_seconds', 60)})
        cpu['efficiency_enabled'] = enabled

    def _set_writeback(self, enabled):
        settings = dict(self._service('tuning-state').get('settings') or {})
        writeback = dict(settings.get('writeback') or {})
        writeback['enabled'] = enabled
        settings['writeback'] = writeback
        result = self._service_raw('tuning', {'settings': settings})
        if result.get('error') == 'TUNING_REQUIRES_QUIESCENT_EXECUTOR':
            raise Converging('WAITING_FOR_QUIESCENT_EXECUTOR')
        if isinstance(result.get('_http_status'), int) and result['_http_status'] >= 300:
            raise Rejected(str(result.get('error') or 'SERVICE_TUNING_FAILED'))

    # --------------------------------------------------- drain and rebuild

    def _drain(self, generation):
        """Withdraw the pool's swap while preserving it; the service CLI does the native work."""
        unit = 'zstack-memory-drain-%d' % generation
        state, exit_status = self._executor_state(unit)
        if state == 'running':
            raise Converging('DRAINING')
        if state == 'exited':
            if exit_status == 0 and self._is_drained():
                return
            raise Rejected(self._executor_error(unit, 'DRAIN_FAILED'))
        if state == 'unknown':
            raise Converging('DRAIN_EXECUTOR_STATE_UNKNOWN')
        if self._service_unit_state() == 'active':
            status = self._service('status')
            if not (status.get('host_zram') or {}).get('pool_generation'):
                raise Rejected('DRAIN_POOL_IDENTITY_UNKNOWN')
            self._service('lifecycle-pause', {'action': 'pause'})
            self._set_efficiency(self._service('host-cpu-state'), False)
            self._bounded_command_output(['systemctl', 'stop', self.MANAGED_ZRAM_UNIT], 60)
        self._run_executor(unit, '--drain')
        raise Converging('DRAINING')

    def _prepare_pool_after_drain(self, generation):
        """Rebuild a drained pool: re-prepare its backend disk, or reset the RAM-only pool."""
        native = self._drain_check() or {}
        pool_generation = native.get('pool_generation')
        if not pool_generation:
            raise Converging('DRAIN_POOL_IDENTITY_UNKNOWN')
        config = self._read_service_config()
        if config.get('backend'):
            self._start_backend_maintenance(self._drained_backend_request(generation, pool_generation, config))
        else:
            self._start_pool_preparation(generation, pool_generation)

    def _start_pool_preparation(self, generation, pool_generation):
        request_id = 'pool-%d-%s' % (generation, pool_generation[:16])
        unit = 'zstack-memory-zram-pool-%d' % generation
        state, exit_status = self._executor_state(unit)
        if state == 'running':
            raise Converging('POOL_PREPARING')
        if state == 'exited':
            receipt = self._receipt('pool')
            if receipt.get('request_id') == request_id and receipt.get('stage') != 'FAILED_REQUIRES_REVIEW':
                self._finish_recorded_maintenance()
                return
            raise Rejected(self._executor_error(unit, receipt.get('reason') or 'ZRAM_POOL_PREPARATION_FAILED'))
        if state == 'unknown':
            raise Converging('POOL_EXECUTOR_STATE_UNKNOWN')
        self._run_executor(unit, '--prepare-zram-pool', {
            'request_id': request_id,
            'expected_control_operation_uuid': request_id,
            'expected_host_boot_id': self._current_boot_id(),
            'expected_pool_generation': pool_generation,
            'reset_confirmed': True})
        raise Converging('POOL_PREPARING')

    def _maintenance_prepared(self):
        """A completed preparation left a rebuilt pool for the service to activate.

        A backend prepared without a pool (e.g. after a reboot) has none; its pool is created on first use.
        """
        pool = self._receipt('pool')
        receipt = pool if pool.get('stage') == 'APPLIED' else self._receipt('backend')
        return receipt.get('stage') == 'APPLIED' and bool(receipt.get('pool_generation'))

    def _activate_after_maintenance(self, generation):
        pool = self._receipt('pool')
        backend = self._receipt('backend')
        # The service activates a completed pool preparation first, else a completed backend one.
        receipt = pool if pool.get('stage') == 'APPLIED' else backend
        pool_generation = receipt.get('pool_generation')
        if receipt.get('stage') != 'APPLIED' or not pool_generation:
            raise Converging('MAINTENANCE_NOT_FINALIZED')
        # The service activates only the exact preparation it recorded; one activation per preparation.
        prepared = receipt.get('request_id') or 'generation-%d' % generation
        result = self._service_raw('lifecycle-activate-maintenance', {
            'request_id': 'activate-%s' % prepared,
            'expected_control_operation_uuid': receipt.get('expected_control_operation_uuid') or prepared,
            'expected_host_boot_id': receipt.get('host_boot_id') or self._current_boot_id(),
            'expected_pool_generation': pool_generation})
        code = result.get('_http_status')
        if isinstance(code, int) and code >= 300:
            error = str(result.get('error') or 'MAINTENANCE_ACTIVATION_FAILED')
            if error in self.ACTIVATION_WAIT_REASONS:
                # A just-started service has no fresh host sample or is still settling; ask again.
                raise Converging(error)
            raise Rejected(error)

    def _finish_recorded_maintenance(self):
        """Start the service for a recorded preparation, verify it, then finalize."""
        for kind in ('pool', 'backend'):
            receipt = self._receipt(kind)
            stage = receipt.get('stage')
            if stage in ('NOT_STARTED', 'APPLIED', None):
                continue
            if receipt.get('host_boot_id') not in (None, '', self._current_boot_id()):
                # Recorded before a reboot; the reboot reclaim prepares the backend again.
                continue
            if stage == 'FAILED_REQUIRES_REVIEW':
                if self._service_unit_state() in ('inactive', 'failed') and not self._is_drained():
                    # Nothing was reset; return a cold service to where it was.
                    self._start_service()
                raise Rejected(receipt.get('reason') or '%s_MAINTENANCE_REQUIRES_REVIEW' % kind.upper())
            if stage not in ('AWAITING_SERVICE_READBACK', 'FINALIZING'):
                raise Converging('%s_MAINTENANCE_%s' % (kind.upper(), stage))
            if self._service_unit_state() != 'active':
                self._start_service()
            if kind == 'backend':
                ready, reason = self._backend_readback_ready(receipt)
                if not ready:
                    raise Converging(reason)
            elif not self._pool_readback_ready():
                raise Converging('ZRAM_POOL_SERVICE_READBACK_PENDING')
            self._service_raw('%s-maintenance-finalize' % ('zram-pool' if kind == 'pool' else 'backend'),
                              {'request_id': receipt.get('request_id')})
            if self._receipt(kind).get('stage') != 'APPLIED':
                raise Converging('%s_MAINTENANCE_FINALIZE_PENDING' % kind.upper())

    def _pool_readback_ready(self):
        status = self._service('status')
        pool = status.get('host_zram') or {}
        return (self._service('host-cpu-state').get('efficiency_enabled') is False and
                status.get('maintenance_blocks_activation') is True and not pool.get('pool_generation'))

    def _backend_readback_ready(self, receipt):
        """Require the disabled host policy and the exact prepared backend before finalize."""
        if self._service('host-cpu-state').get('efficiency_enabled') is not False:
            return False, 'HOST_MEMORY_OPTIMIZATION_NOT_DISABLED'
        resource = self._service('status').get('backend_resource') or {}
        detail = self._service('backend-view')
        resource_uuid = receipt.get('backend_resource_uuid')
        if (not resource_uuid or resource.get('resource_uuid') != resource_uuid or
                resource.get('state') != 'PREPARED' or resource.get('active') is not False or
                detail.get('claimed') is not True or detail.get('identity_qualified') is not True or
                detail.get('ownership_generation') != resource_uuid):
            return False, 'BACKEND_SERVICE_READBACK_PENDING'
        return True, None

    # --------------------------------------------------- writeback backend

    def _writeback_inventory(self, host_uuid):
        backend, config, observation_error = {}, {}, None
        status = None
        if self._service_unit_state() == 'active' and self._service_available():
            try:
                status = self._service('status')
                detail = self._service('backend-view')
                backend = dict(detail)
                backend['backend_resource'] = status.get('backend_resource')
                config = detail.get('configured') or {}
            except Exception:
                # An offline service does not make a blank disk PREPARED.
                observation_error = 'BACKEND_SERVICE_OBSERVATION_UNAVAILABLE'
        inventory = probe_writeback_backends(host_uuid, backend, config)
        if not isinstance(inventory, dict):
            return inventory
        reasons = []
        pool_generation = None
        unit = self._service_unit_state()
        if unit == 'active':
            pool_generation = (status or {}).get('host_zram', {}).get('pool_generation') if status else None
            if pool_generation:
                reasons.append('MEMORY_SERVICE_NOT_STOPPED')
            else:
                pool_generation = 'none'
        elif unit in ('inactive', 'failed'):
            native = self._drain_check() or {}
            if native.get('state') == self.DRAINED:
                pool_generation = native.get('pool_generation')
            elif self._managed_service_never_used() or not native.get('pool_generation'):
                pool_generation = 'none'
        if not pool_generation:
            reasons.append('POOL_GENERATION_UNKNOWN')
        receipt = self._receipt('backend')
        # A preparation left unfinished before a reboot is set aside by the next one.
        if (receipt.get('stage') not in ('NOT_STARTED', 'APPLIED') and
                receipt.get('host_boot_id') in (None, '', self._current_boot_id())):
            reasons.append('BACKEND_MAINTENANCE_UNRESOLVED')
        previous = self._previous_backend_device()
        for candidate in inventory.get('candidates') or []:
            if (previous and isinstance(candidate, dict) and candidate.get('device') == previous and
                    candidate.get('reasons') == ['ACTIVE_BLOCK_HOLDERS'] and
                    self._held_only_by_zram(candidate)):
                # The drained pool's own backend: the service re-verifies its identity.
                candidate.update({'eligible': True, 'state': 'NEEDS_OFFLINE_PREPARATION',
                                  'reasons': ['NEEDS_OFFLINE_PREPARATION']})
        if not any(isinstance(item, dict) and item.get('eligible') is True and
                   item.get('state') == 'NEEDS_OFFLINE_PREPARATION'
                   for item in inventory.get('candidates') or []):
            reasons.append('NO_ELIGIBLE_WRITEBACK_CANDIDATE')
        if observation_error:
            inventory.setdefault('reasons', []).append(observation_error)
            if inventory.get('status') == 'AVAILABLE':
                inventory['status'] = 'PARTIAL'
        inventory.update({'poolGeneration': pool_generation, 'maintenance': receipt,
                          'canPrepare': not reasons, 'preparationReasons': reasons})
        return inventory

    def _previous_backend_device(self):
        try:
            backend = self._read_service_config().get('backend') or {}
        except (IOError, OSError, ValueError):
            return None
        return backend.get('device') if isinstance(backend, dict) else None

    def _held_only_by_zram(self, candidate):
        identity = candidate.get('stableIdentity') or {}
        sysfs_path = identity.get('sysfsPath') or ''
        if not sysfs_path.startswith(('/sys/devices/', '/sys/block/')):
            return False
        try:
            device = self._read_service_config().get('device') or ''
            return os.listdir(os.path.join(sysfs_path, 'holders')) == [os.path.basename(device)]
        except (IOError, OSError, ValueError):
            return False

    def _prepare_writeback(self, command):
        """Prepare the selected disk as the writeback backend; resend to advance."""
        reply = {'operationUuid': command.get('operationUuid')}
        generation = command.get('generation')
        try:
            if isinstance(generation, bool) or not isinstance(generation, INTEGER_TYPES) or generation < 1:
                raise Rejected('INVALID_GENERATION')
            with self._host_lock():
                self._finish_recorded_maintenance()
                receipt = self._receipt('backend')
                request_id = 'backend-%d-%s' % (generation, str(command.get('candidateId', ''))[-16:])
                if receipt.get('request_id') == request_id and receipt.get('stage') == 'APPLIED':
                    reply.update({'success': True, 'status': 'Succeeded', 'state': {'maintenance': receipt}})
                else:
                    inventory = self._writeback_inventory(command['hostUuid'])
                    if inventory.get('canPrepare') is not True and not self._cold_first_use(inventory):
                        reasons = inventory.get('preparationReasons') or []
                        raise Rejected(reasons[0] if reasons else 'BACKEND_MAINTENANCE_NOT_ELIGIBLE')
                    request = build_backend_maintenance_request(inventory, {
                        'requestId': request_id, 'candidateId': command.get('candidateId'),
                        'expectedHostBootId': command.get('expectedHostBootId'),
                        'expectedPoolGeneration': command.get('expectedPoolGeneration'),
                        'backendCapacityBytes': command.get('backendCapacityBytes'),
                        'resetConfirmed': command.get('resetConfirmed')})
                    self._start_backend_maintenance(request)
                    reply.update({'success': True, 'status': 'Succeeded',
                                  'state': {'maintenance': self._receipt('backend')}})
        except Converging as exc:
            reply.update({'success': True, 'status': 'Converging', 'reasonCode': exc.reason,
                          'retryAfterSeconds': exc.retry_after})
        except (Rejected, ValueError) as exc:
            reply.update({'success': False, 'status': 'Failed',
                          'reasonCode': exc.reason if isinstance(exc, Rejected) else str(exc)})
        except Exception as exc:
            logger.warn('writeback backend preparation did not complete: %s' % exc)
            reply.update({'success': False, 'status': 'Failed', 'reasonCode': 'BACKEND_MAINTENANCE_FAILED',
                          'reason': str(exc)})
        return reply

    def _cold_first_use(self, inventory):
        """A never-configured service runs in observe mode without a pool; stop it for the offline step."""
        if inventory.get('poolGeneration') != 'none' or self._service_unit_state() != 'active':
            return False
        if [reason for reason in inventory.get('preparationReasons') or [] if reason != 'MEMORY_SERVICE_NOT_STOPPED']:
            return False
        status = self._service('status')
        if status.get('mode') != 'observe' or (status.get('host_zram') or {}).get('pool_generation'):
            return False
        self._bounded_command_output(['systemctl', 'stop', self.MANAGED_ZRAM_UNIT], 60)
        return self._service_unit_state() == 'inactive'

    def _drained_backend_request(self, generation, pool_generation, config):
        """Re-prepare the drained pool's own backend disk for the rebuilt pool."""
        inventory = self._writeback_inventory(self._load_host_uuid())
        previous = (config.get('backend') or {}).get('device')
        candidate = next((item for item in inventory.get('candidates') or []
                          if isinstance(item, dict) and item.get('device') == previous and
                          item.get('eligible') is True), None)
        if candidate is None or inventory.get('canPrepare') is not True:
            reasons = inventory.get('preparationReasons') or []
            raise Rejected(reasons[0] if reasons else 'DRAINED_BACKEND_NOT_ELIGIBLE')
        return build_backend_maintenance_request(inventory, {
            'requestId': 'backend-%d-%s' % (generation, pool_generation[:16]),
            'candidateId': candidate.get('identity'),
            'expectedHostBootId': self._current_boot_id(),
            'expectedPoolGeneration': pool_generation,
            'backendCapacityBytes': candidate.get('capacityBytes', candidate.get('capacity_bytes')),
            'resetConfirmed': True})

    def _backend_reclaim_required(self):
        native = self._drain_check() or {}
        return str(native.get('error') or '').startswith('BACKEND_RECLAIM_REQUIRED_AFTER_REBOOT')

    def _reboot_backend_request(self, generation):
        """Prepare again the configured disk the last preparation claimed, while it is still eligible.

        Every recorded identity of that claim is bound to the earlier boot, so the disk is the
        configured device with the recorded capacity that the current inventory finds unused.
        """
        boot = self._current_boot_id()
        request_id = 'backend-%d-%s' % (generation, boot.replace('-', '')[:16])
        if self._executor_state('zstack-memory-backend-%s' % request_id)[0] != 'absent':
            # Already started in this boot; the executor's own state decides the next step.
            return {'request_id': request_id}
        target = self._receipt('backend').get('target_identity') or {}
        device = (self._read_service_config().get('backend') or {}).get('device')
        inventory = self._writeback_inventory(self._load_host_uuid())
        candidate = next((item for item in inventory.get('candidates') or []
                          if isinstance(item, dict) and device and item.get('device') == device and
                          item.get('device') == target.get('canonical_device') and
                          item.get('capacityBytes', item.get('capacity_bytes')) == target.get('capacity_bytes') and
                          item.get('eligible') is True), None)
        if candidate is None:
            raise Rejected('REBOOT_BACKEND_NOT_ELIGIBLE')
        if inventory.get('canPrepare') is not True:
            reasons = inventory.get('preparationReasons') or []
            raise Rejected(reasons[0] if reasons else 'REBOOT_BACKEND_NOT_ELIGIBLE')
        return build_backend_maintenance_request(inventory, {
            'requestId': request_id,
            'candidateId': candidate.get('identity'),
            'expectedHostBootId': boot,
            'expectedPoolGeneration': 'none',
            'backendCapacityBytes': candidate.get('capacityBytes', candidate.get('capacity_bytes')),
            'resetConfirmed': True})

    def _start_backend_maintenance(self, request):
        unit = 'zstack-memory-backend-%s' % request['request_id']
        state, exit_status = self._executor_state(unit)
        if state == 'running':
            raise Converging('BACKEND_PREPARING')
        if state == 'exited':
            receipt = self._receipt('backend')
            if receipt.get('request_id') == request['request_id'] and receipt.get('stage') != 'FAILED_REQUIRES_REVIEW':
                self._finish_recorded_maintenance()
                return
            raise Rejected(self._executor_error(unit, receipt.get('reason') or 'BACKEND_MAINTENANCE_FAILED'))
        if state == 'unknown':
            raise Converging('BACKEND_EXECUTOR_STATE_UNKNOWN')
        if self._service_unit_state() not in ('inactive', 'failed'):
            raise Rejected('MEMORY_SERVICE_NOT_STOPPED')
        self._run_executor(unit, '--prepare-backend-maintenance', request)
        raise Converging('BACKEND_PREPARING')

'''
ContainerExecutor - manages tensor-fusion-worker containers via Docker CLI.

Parallel implementation to ProcessExecutor. The caller injects the desired
strategy into TensorFusionService.

@author: tensorfusion
'''

import errno
import json
import os
import subprocess
import threading
import time

from zstacklib.utils import log
from zstacklib.utils.pci import normalize_pci_address

from kvmagent.plugins.tensorfusion.models import Worker
from kvmagent.plugins.tensorfusion.base_executor import WorkerExecutor

logger = log.get_logger(__name__)

SENSITIVE_ENV_KEYS = frozenset(('TF_LICENSE', 'TF_LICENSE_SIGN'))


def _command_for_log(cmd):
    sanitized = []
    for arg in cmd:
        key, separator, _ = arg.partition('=')
        if separator and key in SENSITIVE_ENV_KEYS:
            sanitized.append('%s=*****' % key)
        else:
            sanitized.append(arg)
    return ' '.join(sanitized)


def _redact_sensitive_values(text, cmd, env=None):
    redacted = text
    sensitive_values = []
    for arg in cmd:
        key, separator, value = arg.partition('=')
        if separator and key in SENSITIVE_ENV_KEYS and value:
            sensitive_values.append(value)
    for key in SENSITIVE_ENV_KEYS:
        value = (env or {}).get(key)
        if value:
            sensitive_values.append(value)
    for value in sorted(sensitive_values, key=len, reverse=True):
        redacted = redacted.replace(value, '*****')
    return redacted


def _shared_memory_ready(path, expected_size):
    try:
        return os.path.getsize(path) >= expected_size
    except OSError:
        return False


def _remove_shared_memory_file(path):
    try:
        os.remove(path)
        return True
    except OSError as e:
        if e.errno == errno.ENOENT:
            return True
        raise


class DockerCommandError(Exception):
    """Raised when a docker CLI command exits with a non-zero return code."""
    def __init__(self, rc, cmd_str, stderr):
        self.rc = rc
        self.stderr = stderr
        super(DockerCommandError, self).__init__(
            'docker command failed (rc=%d): %s\nstderr: %s' % (rc, cmd_str, stderr))


class ContainerExecutor(WorkerExecutor):
    """Manages tensor-fusion-worker containers via Docker CLI.

    Each Worker runs as a Docker container with nvidia runtime for GPU
    device-level hard isolation. Container naming convention:
    ``tf-worker-<vm_uuid[:12]>``.
    """

    WORKER_IMAGE = 'tf-worker:latest'
    CONTAINER_PREFIX = 'tf-worker-'
    STARTUP_WAIT_SEC = 10
    STARTUP_POLL_INTERVAL_SEC = 0.2
    STOP_TIMEOUT_SEC = 5
    DOCKER_CMD_TIMEOUT = 30
    DOCKER_RUN_TIMEOUT = 90
    DOCKER_REAP_TIMEOUT = 5
    ROLLBACK_RETRY_WINDOW_SEC = 5
    ROLLBACK_RETRY_INTERVAL_SEC = 0.5
    ROLLBACK_REMOVE_TIMEOUT_SEC = 1

    # Docker labels used for filtering and identification.
    LABEL_MARKER = 'tf-worker'
    LABEL_VM_UUID = 'vm_uuid'
    LABEL_PCI_ADDRESS = 'pci_address'

    def __init__(self, gpu_details):
        super(ContainerExecutor, self).__init__(gpu_details)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public interface (WorkerExecutor contract)
    # ------------------------------------------------------------------

    def start(self, request):
        # type: (object) -> Worker
        """Start a Worker container. Returns Worker with container_id/container_name set."""

        pci = normalize_pci_address(request.pci_address)
        detail = self._gpu_details.get(pci)
        if not detail:
            raise Exception('GPU %s not found in gpu_details' % pci)

        cuda_index = detail['cuda_index']
        device_uuid = request.device_uuid
        container_name = self._container_name(request.vm_uuid)
        shm_path = self.SHM_PREFIX + 'tf_%s' % device_uuid

        # Verify the worker image is available locally.
        if not self._image_exists():
            raise Exception(
                'worker image %s not found. '
                'Install it via zstack-dgpu-toolkit.bin or run: '
                'docker load -i tf-worker-image.tar' % self.WORKER_IMAGE)

        # Resolve shared memory size.
        if request.shmem_size and request.shmem_size > 0:
            shm_size_mb = self._bytes_to_mb(request.shmem_size)
        elif request.memory_mb and request.memory_mb > 0:
            shm_size_mb = request.memory_mb
        else:
            shm_size_mb = self.SHM_SIZE_MB

        log_file = os.path.join(self.LOG_DIR, 'tf-worker-%s.log' % request.vm_uuid)
        enable_log = request.enable_log if request.enable_log is not None else self.DEFAULT_ENABLE_LOG
        log_level = request.log_level or self.DEFAULT_LOG_LEVEL

        if not self._remove_container(container_name):
            raise Exception('failed to remove existing worker container %s' % container_name)
        if not self._remove_shared_memory(shm_path):
            raise Exception('failed to remove existing worker shared memory %s' % shm_path)

        cmd = self._build_run_cmd(
            device_uuid=device_uuid,
            vm_uuid=request.vm_uuid,
            pci_address=pci,
            cuda_index=cuda_index,
            container_name=container_name,
            memory_mb=request.memory_mb,
            sm_percent_limit=request.sm_percent_limit,
            shm_size_mb=shm_size_mb,
            log_file=log_file,
            enable_log=enable_log,
            log_level=log_level,
            protocol=request.protocol or 'shmem',
        )
        docker_env = {
            'TF_LICENSE': request.license or '',
            'TF_LICENSE_SIGN': request.license_sign or '',
        }

        logger.info('starting worker container: %s' % _command_for_log(['docker'] + cmd))

        run_error = None
        try:
            container_id = self._docker(
                cmd, timeout=self.DOCKER_RUN_TIMEOUT, env=docker_env).strip()
        except Exception as e:
            run_error = _redact_sensitive_values(str(e), cmd, docker_env)
        if run_error is not None:
            self._rollback_failed_start(container_name, shm_path)
            raise Exception('failed to start worker container %s: %s' %
                            (container_name, run_error))

        # Verify the container is actually running.
        info = self._inspect_container(container_name)
        if not info:
            self._rollback_failed_start(container_name, shm_path)
            raise Exception('container %s started but inspect failed' % container_name)

        state = info.get('State', {})
        if not state.get('Running', False):
            exit_code = state.get('ExitCode', '?')
            # Grab last few lines of container stdout/stderr.
            docker_logs = self._docker_quiet(['logs', '--tail', '20', container_name])
            # Also read the worker log file — the worker writes to file, not stdout.
            worker_logs = ''
            try:
                if os.path.isfile(log_file):
                    with open(log_file, 'r') as f:
                        lines = f.readlines()
                        worker_logs = ''.join(lines[-20:])
            except Exception:
                pass
            self._rollback_failed_start(container_name, shm_path)
            diag = _redact_sensitive_values(
                docker_logs or worker_logs or '<empty>', cmd, docker_env)
            raise Exception(
                'worker container %s exited immediately (exit_code=%s). logs:\n%s' %
                (container_name, exit_code, diag))

        if (request.protocol or 'shmem') == 'shmem':
            expected_shm_size = shm_size_mb * self.BYTES_PER_MB
            deadline = time.time() + self.STARTUP_WAIT_SEC
            while time.time() < deadline and not _shared_memory_ready(shm_path, expected_shm_size):
                time.sleep(self.STARTUP_POLL_INTERVAL_SEC)
            if not _shared_memory_ready(shm_path, expected_shm_size):
                docker_logs = self._docker_quiet(['logs', '--tail', '20', container_name])
                self._rollback_failed_start(container_name, shm_path)
                diag = _redact_sensitive_values(docker_logs or '<empty>', cmd, docker_env)
                raise Exception(
                    'worker container %s did not create shared memory %s within %ds. logs:\n%s' %
                    (container_name, shm_path, self.STARTUP_WAIT_SEC, diag))
            ready_info = self._inspect_container(container_name)
            if not ready_info or not ready_info.get('State', {}).get('Running', False):
                docker_logs = self._docker_quiet(['logs', '--tail', '20', container_name])
                self._rollback_failed_start(container_name, shm_path)
                diag = _redact_sensitive_values(docker_logs or '<empty>', cmd, docker_env)
                raise Exception(
                    'worker container %s exited before shared memory became ready. logs:\n%s' %
                    (container_name, diag))

        worker = Worker()
        worker.device_uuid = device_uuid
        worker.vm_uuid = request.vm_uuid
        worker.pid = None
        worker.pci_address = pci
        worker.cuda_index = cuda_index
        worker.protocol = request.protocol or 'shmem'
        worker.allocated_memory_mb = request.memory_mb
        worker.sm_percent_limit = request.sm_percent_limit
        worker.shared_memory_path = shm_path
        worker.shared_memory_size = shm_size_mb * self.BYTES_PER_MB
        worker.license = request.license
        worker.license_sign = request.license_sign
        worker.enable_log = enable_log
        worker.log_level = log_level
        worker.container_id = container_id
        worker.container_name = container_name

        logger.info('started worker container %s (id=%s) on GPU %s (cuda %d) for VM %s' %
                     (container_name, container_id[:12], pci, cuda_index, request.vm_uuid))
        return worker

    def stop(self, worker):
        """Stop and remove a Worker container, then clean up shared memory."""
        container_id = getattr(worker, 'container_id', None)
        container_name = getattr(worker, 'container_name', None)
        target = container_id or container_name
        if not target:
            raise Exception('worker %s has no container identity' % worker.device_uuid)

        logger.info('stopping worker container %s (device=%s)' % (target, worker.device_uuid))
        try:
            self._docker(['stop', '-t', str(self.STOP_TIMEOUT_SEC), target])
        except Exception as e:
            logger.warning('docker stop failed for %s: %s, forcing removal' % (target, e))

        if not self._remove_container(target):
            raise Exception('failed to remove worker container %s' % target)
        self._remove_shared_memory(self._worker_shared_memory_path(worker))

    @classmethod
    def is_alive(cls, worker):
        # type: (Worker) -> bool
        """Check if a worker container is still running.

        Uses container_id first to avoid name-reuse issues.
        Distinguishes 'not found' (dead) from 'inspect failed' (unknown, treat as alive).
        """
        container_id = getattr(worker, 'container_id', None)
        container_name = getattr(worker, 'container_name', None)
        target = container_id or container_name
        if not target:
            return False
        try:
            out = cls._docker_class(['inspect', '--format', '{{.State.Running}}', target])
            return out.strip() == 'true'
        except DockerCommandError as e:
            # Only treat as dead when Docker explicitly says the object doesn't exist.
            # Do not rely on rc alone — it varies across Docker versions and error types.
            stderr_lower = e.stderr.lower()
            if 'no such object' in stderr_lower or 'no such container' in stderr_lower:
                return False
            # Anything else (daemon issue, permission denied, etc.) — assume alive.
            logger.warning('is_alive: docker inspect failed for %s, assuming alive: %s' % (target, e))
            return True
        except Exception as e:
            # Timeout or unexpected error — assume alive to avoid false reaping.
            logger.warning('is_alive: docker inspect failed for %s, assuming alive: %s' % (target, e))
            return True

    def scan_running(self):
        # type: () -> list
        """Scan for running tf-worker containers and reconstruct Worker objects."""
        workers = []

        try:
            output = self._docker([
                'ps', '--filter', 'label=%s=true' % self.LABEL_MARKER,
                '--format', '{{.Names}}'
            ])
        except Exception as e:
            logger.warning('scan_running: docker ps failed: %s' % e)
            return workers

        names = [n.strip() for n in output.strip().split('\n') if n.strip()]
        if not names:
            logger.info('scan_running: no tf-worker containers found')
            return workers

        # Build reverse mapping for PCI address lookup.
        cuda_to_pci = {}
        for detail in self._gpu_details.values():
            cuda_to_pci[detail['cuda_index']] = detail['pci_address']

        for name in names:
            try:
                worker = self._reconstruct_worker(name, cuda_to_pci)
                if worker:
                    workers.append(worker)
            except Exception as e:
                logger.warning('scan_running: failed to reconstruct worker from container %s: %s' %
                               (name, e))

        logger.info('scan_running: found %d tf-worker containers' % len(workers))
        return workers

    def reap_dead(self, worker):
        """Remove a stopped container by ID first, fall back to name."""
        container_id = getattr(worker, 'container_id', None)
        container_name = getattr(worker, 'container_name', None)
        target = container_id or container_name
        if not target:
            return False
        if self.is_alive(worker):
            logger.warning('skip reaping worker %s container %s: container is still running' %
                           (worker.device_uuid, target))
            return False
        if not self._remove_container(target):
            raise Exception('failed to reap worker container %s' % target)
        self._remove_shared_memory(self._worker_shared_memory_path(worker))
        logger.debug('reaped dead worker container %s (id=%s, name=%s)' %
                     (target, container_id, container_name))
        return True

    def cleanup_residual_workers_by_vm(self, vm_uuid, known_workers=None):
        # type: (str, list) -> int
        """Remove residual containers for a VM that are not in known_workers."""
        known_ids = set()
        known_names_without_id = set()
        for w in (known_workers or []):
            container_id = getattr(w, 'container_id', None)
            name = getattr(w, 'container_name', None)
            if container_id:
                known_ids.add(container_id)
            elif name:
                known_names_without_id.add(name)

        try:
            output = self._docker([
                'ps', '-aq',
                '--filter', 'label=%s=true' % self.LABEL_MARKER,
                '--filter', 'label=%s=%s' % (self.LABEL_VM_UUID, vm_uuid),
            ])
        except Exception as e:
            logger.warning('cleanup_residual: docker ps failed for VM %s: %s' % (vm_uuid, e))
            return 0

        container_ids = [cid.strip() for cid in output.strip().split('\n') if cid.strip()]
        if not container_ids:
            return 0

        cleaned = 0
        for cid in container_ids:
            try:
                info = self._inspect_container(cid)
                if not info:
                    continue
                name = info.get('Name', '').lstrip('/')
                actual_id = info.get('Id') or cid
                if actual_id in known_ids or name in known_names_without_id:
                    continue

                # Extract device_uuid from env for shm cleanup.
                env_list = info.get('Config', {}).get('Env', [])
                env = {e.split('=', 1)[0]: e.split('=', 1)[1] for e in env_list if '=' in e}
                device_uuid = env.get('TF_DEVICE_UUID')

                shm_path = self.SHM_PREFIX + 'tf_%s' % device_uuid if device_uuid else None
                if self._remove_container(cid):
                    self._remove_shared_memory(shm_path)
                    cleaned += 1
            except Exception as e:
                logger.warning('cleanup_residual: failed to clean container %s: %s' % (cid, e))

        if cleaned:
            logger.info('cleanup_residual: cleaned %d residual containers for VM %s' %
                        (cleaned, vm_uuid))
        return cleaned

    # ------------------------------------------------------------------
    # Docker command helpers
    # ------------------------------------------------------------------

    def _docker(self, args, timeout=None, env=None):
        """Execute a docker command and return stdout. Raises on failure."""
        timeout = timeout or self.DOCKER_CMD_TIMEOUT
        return self._execute_docker(args, timeout, env)

    def _docker_quiet(self, args, timeout=None, env=None):
        """Execute a docker command, returning stdout. Errors are logged but not raised."""
        try:
            return self._docker(args, timeout=timeout, env=env)
        except Exception as e:
            logger.debug('docker command (quiet) failed: %s' % e)
            return ''

    @classmethod
    def _docker_class(cls, args, timeout=30, env=None):
        """Class-level docker command for use in classmethods (e.g. is_alive)."""
        return cls._execute_docker(args, timeout, env)

    @classmethod
    def _execute_docker(cls, args, timeout, env=None):
        cmd = ['docker'] + args
        command_for_log = _command_for_log(cmd)
        process_env = None
        if env is not None:
            process_env = os.environ.copy()
            process_env.update(env)
        timed_out = False
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                close_fds=True, env=process_env)
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=cls.DOCKER_REAP_TIMEOUT)
            except Exception:
                pass
        if timed_out:
            raise Exception('docker command timed out (%ds): %s' % (timeout, command_for_log))
        if proc.returncode != 0:
            stderr_str = stderr.decode('utf-8', 'ignore').strip() if stderr else ''
            stderr_str = _redact_sensitive_values(stderr_str, cmd, env)
            raise DockerCommandError(proc.returncode, command_for_log, stderr_str)
        return stdout.decode('utf-8', 'ignore').strip() if stdout else ''

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _container_name(cls, vm_uuid):
        """Generate container name from VM UUID."""
        return '%s%s' % (cls.CONTAINER_PREFIX, vm_uuid[:12])

    def _inspect_container(self, name_or_id):
        """Run docker inspect and return the parsed JSON dict, or None on error."""
        try:
            output = self._docker(['inspect', name_or_id])
            data = json.loads(output)
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return None
        except Exception:
            return None

    def _rollback_failed_start(self, container_name, shm_path):
        deadline = time.time() + self.ROLLBACK_RETRY_WINDOW_SEC
        removed = False
        while True:
            removed = self._remove_container(
                container_name, timeout=self.ROLLBACK_REMOVE_TIMEOUT_SEC)
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(self.ROLLBACK_RETRY_INTERVAL_SEC, remaining))

        if not removed:
            logger.warning('worker container %s cleanup remains pending after failed start' %
                           container_name)
            return False
        self._remove_shared_memory(shm_path)
        return True

    def _remove_container(self, container_target, timeout=None):
        removed = False
        try:
            args = ['rm', '-f', container_target]
            if timeout is None:
                self._docker(args)
            else:
                self._docker(args, timeout=timeout)
            removed = True
        except DockerCommandError as e:
            stderr_lower = e.stderr.lower()
            removed = ('no such object' in stderr_lower or
                       'no such container' in stderr_lower)
        except Exception as e:
            logger.warning('failed to remove worker container %s: %s' %
                           (container_target, e))

        if not removed:
            logger.warning('worker container %s removal is unconfirmed' % container_target)
            return False
        return True

    @classmethod
    def _worker_shared_memory_path(cls, worker):
        return (getattr(worker, 'shared_memory_path', None) or
                cls.SHM_PREFIX + 'tf_%s' % worker.device_uuid)

    @staticmethod
    def _remove_shared_memory(shm_path):
        if not shm_path:
            return True
        try:
            return _remove_shared_memory_file(shm_path)
        except OSError as e:
            logger.warning('failed to remove shared memory file %s: %s' %
                           (shm_path, e))
            return False

    def _image_exists(self):
        """Check if the worker Docker image is available locally."""
        try:
            self._docker(['image', 'inspect', self.WORKER_IMAGE])
            return True
        except Exception:
            return False

    @classmethod
    def is_available(cls):
        """Check if container runtime environment is ready (docker + nvidia-ctk + image)."""
        from zstacklib.utils.bash import bash_roe
        r, _, _ = bash_roe('which docker')
        if r != 0:
            return False
        r, _, _ = bash_roe('which nvidia-ctk')
        if r != 0:
            return False
        r, _, _ = bash_roe('docker image inspect %s' % cls.WORKER_IMAGE)
        if r != 0:
            return False
        return True

    def _build_run_cmd(self, device_uuid, vm_uuid, pci_address, cuda_index,
                       container_name, memory_mb, sm_percent_limit, shm_size_mb,
                       log_file, enable_log, log_level, protocol='shmem'):
        """Build the full ``docker run`` argument list."""
        cmd = [
            'run', '-d',
            '--runtime=nvidia',
            '--gpus=device=%d' % cuda_index,
            '--ipc=host',
            '--name=%s' % container_name,
            # Labels for identification and filtering.
            '--label', '%s=true' % self.LABEL_MARKER,
            '--label', '%s=%s' % (self.LABEL_VM_UUID, vm_uuid),
            '--label', '%s=%s' % (self.LABEL_PCI_ADDRESS, pci_address),
            # GPU environment: container sees only 1 GPU, always index 0.
            '-e', 'CUDA_DEVICE_ORDER=PCI_BUS_ID',
            '-e', 'CUDA_VISIBLE_DEVICES=0',
            # Worker identification.
            '-e', 'TF_DEVICE_UUID=%s' % device_uuid,
            '-e', 'TF_PCI_ADDRESS=%s' % pci_address,
            '-e', 'VM_UUID=%s' % vm_uuid,
            # Logging.
            '-e', 'TF_ENABLE_LOG=%s' % ('1' if enable_log else '0'),
            '-e', 'TF_LOG_LEVEL=%s' % log_level,
            '-e', 'TF_LOG_PATH=%s' % log_file,
            # License.
            '-e', 'TF_LICENSE',
            '-e', 'TF_LICENSE_SIGN',
            # Resource limits.
            '-e', 'TF_GPU_MEMORY_LIMIT=%d' % (memory_mb or 0),
            '-e', 'TF_CUDA_SM_PERCENT_LIMIT=%d' % (sm_percent_limit or 0),
            # Mount log directory so container can write logs to host.
            '-v', '%s:%s' % (self.LOG_DIR, self.LOG_DIR),
            # Entrypoint with umask 000 so /dev/shm files get 0666 permissions
            # (required for QEMU ivshmem read/write access).
            '--entrypoint', 'sh',
            self.WORKER_IMAGE,
            '-c',
            'umask 000 && exec /usr/local/bin/tensor-fusion-worker "$@"',
            '--',
            # Worker arguments.
            '-n', protocol,
            '-m', '/tf_%s' % device_uuid,
            '-M', str(shm_size_mb),
        ]
        return cmd

    def _reconstruct_worker(self, container_name, cuda_to_pci):
        """Reconstruct a Worker object from a running container via docker inspect."""
        info = self._inspect_container(container_name)
        if not info:
            return None

        state = info.get('State', {})
        if not state.get('Running', False):
            return None

        config = info.get('Config', {})
        labels = config.get('Labels', {})
        env_list = config.get('Env', [])

        # Parse environment variables into a dict.
        env = {}
        for entry in env_list:
            if '=' in entry:
                key, value = entry.split('=', 1)
                env[key] = value

        device_uuid = env.get('TF_DEVICE_UUID')
        vm_uuid = labels.get(self.LABEL_VM_UUID) or env.get('VM_UUID')

        if not device_uuid or not vm_uuid:
            logger.debug('skipping container %s: missing device_uuid or vm_uuid' % container_name)
            return None

        worker = Worker()
        worker.device_uuid = device_uuid
        worker.vm_uuid = vm_uuid
        worker.pid = None
        worker.container_id = info.get('Id', '')
        worker.container_name = container_name

        # PCI address from label or env, falling back to cuda_to_pci mapping.
        worker.pci_address = normalize_pci_address(
            labels.get(self.LABEL_PCI_ADDRESS) or env.get('TF_PCI_ADDRESS'))

        # CUDA index: in container mode, the host cuda_index is in --gpus=device=N.
        # Reconstruct from pci_address reverse mapping.
        worker.cuda_index = None
        if worker.pci_address:
            for idx, pci in cuda_to_pci.items():
                if normalize_pci_address(pci) == worker.pci_address:
                    worker.cuda_index = idx
                    break

        if worker.cuda_index is None and not worker.pci_address:
            logger.warning('skipping container %s: cannot determine GPU' % container_name)
            return None

        # Memory and SM limits from environment.
        mem_limit = env.get('TF_GPU_MEMORY_LIMIT', '0')
        try:
            worker.allocated_memory_mb = int(mem_limit)
        except ValueError:
            worker.allocated_memory_mb = 0

        sm_limit = env.get('TF_CUDA_SM_PERCENT_LIMIT', '0')
        try:
            worker.sm_percent_limit = int(sm_limit)
        except ValueError:
            worker.sm_percent_limit = 0

        # Protocol and shared memory from container command args.
        worker.protocol = 'shmem'
        args = info.get('Args', [])
        for i, arg in enumerate(args):
            if arg == '-n' and i + 1 < len(args):
                worker.protocol = args[i + 1]
            elif arg == '-m' and i + 1 < len(args):
                shm_name = args[i + 1]
                worker.shared_memory_path = self.SHM_PREFIX + shm_name.lstrip('/')
            elif arg == '-M' and i + 1 < len(args):
                try:
                    worker.shared_memory_size = int(args[i + 1]) * self.BYTES_PER_MB
                except ValueError:
                    pass

        # Log settings.
        enable_log_str = env.get('TF_ENABLE_LOG')
        if enable_log_str is None:
            worker.enable_log = self.DEFAULT_ENABLE_LOG
        else:
            worker.enable_log = enable_log_str not in ('0', 'false', 'False')
        worker.log_level = env.get('TF_LOG_LEVEL', self.DEFAULT_LOG_LEVEL)

        # License.
        worker.license = env.get('TF_LICENSE')
        worker.license_sign = env.get('TF_LICENSE_SIGN')
        if not worker.license or not worker.license_sign:
            logger.warning('skipping container %s: missing TF_LICENSE or TF_LICENSE_SIGN' %
                           container_name)
            return None

        logger.debug('scanned running worker container: %s, device=%s, vm=%s' %
                     (container_name, device_uuid, vm_uuid))
        return worker

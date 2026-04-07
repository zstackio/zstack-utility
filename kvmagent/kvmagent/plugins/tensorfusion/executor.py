'''
TensorFusion Worker process lifecycle management.

@author: tensorfusion
'''

import os
import errno
import signal
import subprocess
import threading
import time

from zstacklib.utils import log
from zstacklib.utils.pci import normalize_pci_address

from kvmagent.plugins.tensorfusion.models import Worker, WorkerCreateRequest

logger = log.get_logger(__name__)


class ProcessExecutor(object):
    """Manages tensor-fusion-worker process start/stop/scan."""

    WORKER_BINARY = '/usr/local/bin/tensor-fusion-worker'
    SHM_PREFIX = '/dev/shm/'
    SHM_SIZE_MB = 512
    BYTES_PER_MB = 1024 * 1024
    SHM_SIZE = SHM_SIZE_MB * BYTES_PER_MB
    LOG_DIR = '/var/log/zstack'
    STARTUP_WAIT_SEC = 3
    STARTUP_POLL_INTERVAL_SEC = 0.2
    STOP_WAIT_SEC = 5
    STOP_POLL_INTERVAL_SEC = 0.2
    KILL_WAIT_SEC = 2
    DEFAULT_ENABLE_LOG = True
    DEFAULT_LOG_LEVEL = 'info'

    def __init__(self, gpu_details):
        """
        Args:
            gpu_details: dict {pci_address: detail_dict} from NVIDIA.query_gpu_details().
        """
        self._gpu_details = gpu_details
        self._proc_lock = threading.RLock()
        self._procs = {}

    @classmethod
    def resolve_license_config(cls, license_value=None, license_sign=None, required=False):
        if required and (not license_value or not license_sign):
            raise Exception('tensor-fusion license is required, provide request.license/request.licenseSign')

        return license_value, license_sign

    def start(self, request):
        # type: (WorkerCreateRequest) -> Worker
        """Start a tensor-fusion-worker process and return a Worker descriptor."""
        request.ensure_device_uuid()
        device_uuid = request.device_uuid
        pci_address = request.pci_address

        detail = self._gpu_details.get(normalize_pci_address(pci_address))
        if not detail:
            raise Exception('GPU %s not found via nvidia-smi' % pci_address)
        cuda_index = detail['cuda_index']
        normalized_pci_address = normalize_pci_address(pci_address)

        shm_path = '/tf_%s' % device_uuid
        protocol = request.protocol or 'shmem'
        shm_size = request.shmem_size if request.shmem_size > 0 else (
            request.memory_mb * self.BYTES_PER_MB if request.memory_mb > 0 else self.SHM_SIZE
        )
        shm_size_mb = self._bytes_to_mb(shm_size)
        shm_size = shm_size_mb * self.BYTES_PER_MB

        if protocol != 'shmem':
            raise Exception('unsupported protocol: %s' % protocol)

        cmd = [
            self.WORKER_BINARY,
            '-n', 'shmem',
            '-m', shm_path,
            '-M', str(shm_size_mb),
        ]

        license_value, license_sign = self.resolve_license_config(
            request.license, request.license_sign, required=True
        )

        # Environment variables
        env = os.environ.copy()
        env['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
        env['CUDA_VISIBLE_DEVICES'] = str(cuda_index)
        env['TF_DEVICE_UUID'] = device_uuid
        env['TF_PCI_ADDRESS'] = normalized_pci_address
        env['VM_UUID'] = request.vm_uuid
        enable_log = request.enable_log if request.enable_log is not None else self.DEFAULT_ENABLE_LOG
        env['TF_ENABLE_LOG'] = '1' if enable_log else '0'
        env['TF_LOG_LEVEL'] = request.log_level or self.DEFAULT_LOG_LEVEL
        env['TF_LICENSE'] = license_value
        env['TF_LICENSE_SIGN'] = license_sign
        if request.memory_mb > 0:
            env['TF_GPU_MEMORY_LIMIT'] = str(request.memory_mb)
        if request.sm_percent_limit > 0:
            env['TF_CUDA_SM_PERCENT_LIMIT'] = str(request.sm_percent_limit)

        log_file = os.path.join(self.LOG_DIR, 'tf-worker-%s.log' % request.vm_uuid)
        env['TF_LOG_PATH'] = log_file

        sanitized_env = env.copy()
        sanitized_env['TF_LICENSE'] = '<REDACTED>'
        sanitized_env['TF_LICENSE_SIGN'] = '<REDACTED>'
        logger.info('starting tensor-fusion-worker: cmd=%s, cuda_index=%d, gpu=%s, vm=%s, env=%s' %
                     (' '.join(cmd), cuda_index, pci_address, request.vm_uuid, sanitized_env))

        log_fd = None
        try:
            log_fd = open(log_file, 'a')
            try:
                proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=log_fd,
                    stderr=log_fd,
                    preexec_fn=os.setsid,
                    close_fds=True,
                )
            finally:
                log_fd.close()
        except Exception:
            logger.exception('failed to start tensor-fusion-worker')
            raise

        # Poll for a short stabilization window so early exits fail fast without a fixed long sleep.
        deadline = time.time() + self.STARTUP_WAIT_SEC
        while time.time() < deadline:
            if proc.poll() is not None:
                raise Exception('tensor-fusion-worker exited immediately (rc=%s), check %s' %
                                (proc.returncode, log_file))
            time.sleep(self.STARTUP_POLL_INTERVAL_SEC)

        self._track_proc(proc)

        worker = Worker()
        worker.device_uuid = device_uuid
        worker.vm_uuid = request.vm_uuid
        worker.pid = proc.pid
        worker.pci_address = normalized_pci_address
        worker.cuda_index = cuda_index
        worker.protocol = protocol
        worker.allocated_memory_mb = request.memory_mb
        worker.sm_percent_limit = request.sm_percent_limit
        worker.shared_memory_path = (self.SHM_PREFIX + shm_path.lstrip('/'))
        worker.shared_memory_size = shm_size
        worker.license = license_value
        worker.license_sign = license_sign
        worker.enable_log = enable_log
        worker.log_level = request.log_level or self.DEFAULT_LOG_LEVEL

        logger.info('tensor-fusion-worker started: pid=%d, device=%s, vm=%s' %
                     (worker.pid, device_uuid, request.vm_uuid))
        return worker

    def stop(self, worker):
        # type: (Worker) -> bool
        """Stop a worker process and clean up resources."""
        pid = worker.pid
        proc = self._get_proc(pid)
        stopped = True
        if proc is not None and self._process_has_exited(proc):
            logger.info('worker %s pid %d already exited before destroy' % (worker.device_uuid, pid))
            stopped = False
        if proc is None:
            verified, reason = self._verify_worker_pid(pid, worker)
            if not verified:
                logger.warn('skip stopping pid %d for worker %s: %s' % (
                    pid, worker.device_uuid, reason))
                stopped = False

        if stopped:
            pgid = None
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                logger.info('sent SIGTERM to process group %d (worker %s)' % (pgid, worker.device_uuid))
            except OSError as e:
                if e.errno == errno.ESRCH:
                    logger.info('worker %s pid %d already exited before destroy' % (worker.device_uuid, pid))
                else:
                    raise Exception('failed to kill process group for pid %d: %s' % (pid, str(e)))

            if not self._wait_for_exit(pid, self.STOP_WAIT_SEC, proc):
                if pgid is not None:
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                        logger.warn('sent SIGKILL to process group %d (worker %s) after SIGTERM timeout' % (
                            pgid, worker.device_uuid))
                    except OSError as e:
                        if e.errno != errno.ESRCH:
                            raise Exception('failed to kill process group for pid %d with SIGKILL: %s' % (
                                pid, str(e)))

                if not self._wait_for_exit(pid, self.KILL_WAIT_SEC, proc):
                    raise Exception('worker %s pid %d did not exit within %ss after SIGTERM and %ss after SIGKILL' %
                                    (worker.device_uuid, pid, self.STOP_WAIT_SEC, self.KILL_WAIT_SEC))

        self._forget_proc(pid)

        # Clean up shared memory file
        if worker.shared_memory_path and os.path.exists(worker.shared_memory_path):
            try:
                os.remove(worker.shared_memory_path)
                logger.debug('removed shared memory file: %s' % worker.shared_memory_path)
            except OSError as e:
                raise Exception('failed to remove shared memory file %s: %s' %
                                (worker.shared_memory_path, str(e)))

        return stopped

    def _wait_for_exit(self, pid, timeout, proc=None):
        # type: (int, int, subprocess.Popen) -> bool
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._process_has_exited(proc):
                return True
            try:
                os.getpgid(pid)
            except OSError as e:
                if e.errno == errno.ESRCH:
                    self._reap_process(proc)
                    return True
                raise
            time.sleep(self.STOP_POLL_INTERVAL_SEC)

        if self._process_has_exited(proc):
            return True
        try:
            os.getpgid(pid)
        except OSError as e:
            if e.errno == errno.ESRCH:
                self._reap_process(proc)
                return True
            raise
        return False

    @staticmethod
    def _process_has_exited(proc):
        if proc is None:
            return False

        if proc.poll() is None:
            return False

        ProcessExecutor._reap_process(proc)
        return True

    @staticmethod
    def _reap_process(proc):
        if proc is None:
            return

        try:
            proc.wait()
        except Exception:
            pass

    def _track_proc(self, proc):
        with self._proc_lock:
            self._procs[proc.pid] = proc

    def _get_proc(self, pid):
        with self._proc_lock:
            return self._procs.get(pid)

    def _forget_proc(self, pid):
        with self._proc_lock:
            self._procs.pop(pid, None)

    def _verify_worker_pid(self, pid, worker):
        # type: (int, Worker) -> tuple
        cmdline_path = '/proc/%s/cmdline' % pid
        environ_path = '/proc/%s/environ' % pid

        try:
            with open(cmdline_path, 'rb') as fd:
                raw_cmdline = fd.read()
        except IOError as e:
            if getattr(e, 'errno', None) == errno.ENOENT:
                return False, 'process no longer exists'
            return False, 'failed to read cmdline: %s' % str(e)

        cmdline = [arg for arg in raw_cmdline.decode('utf-8', 'ignore').split('\x00') if arg]
        if not cmdline:
            return False, 'empty cmdline'

        binary = os.path.basename(cmdline[0])
        if binary != os.path.basename(self.WORKER_BINARY):
            return False, 'unexpected binary %s' % binary

        try:
            with open(environ_path, 'rb') as fd:
                raw_environ = fd.read()
        except IOError as e:
            if getattr(e, 'errno', None) == errno.ENOENT:
                return False, 'process no longer exists'
            return False, 'failed to read environ: %s' % str(e)

        environ = {}
        for entry in raw_environ.decode('utf-8', 'ignore').split('\x00'):
            if not entry or '=' not in entry:
                continue
            key, value = entry.split('=', 1)
            environ[key] = value

        actual_device_uuid = environ.get('TF_DEVICE_UUID')
        if actual_device_uuid != worker.device_uuid:
            return False, 'device uuid mismatch: expected %s, actual %s' % (
                worker.device_uuid, actual_device_uuid)

        return True, 'verified tensor-fusion-worker process'

    def scan_running(self):
        # type: () -> list
        """Scan for running tensor-fusion-worker processes and reconstruct Worker objects."""
        workers = []
        try:
            import psutil
        except ImportError:
            logger.warn('psutil not available, cannot scan running workers')
            return workers

        # Build reverse mapping: cuda_index -> pci_address
        cuda_to_pci = {}
        for detail in self._gpu_details.values():
            cuda_to_pci[detail['cuda_index']] = detail['pci_address']

        binary_name = os.path.basename(self.WORKER_BINARY)
        for proc in psutil.process_iter():
            try:
                if proc.name() != binary_name:
                    continue

                cmdline = proc.cmdline() or []
                try:
                    environ = proc.environ() or {}
                except (AttributeError, psutil.AccessDenied):
                    environ = {}

                device_uuid = environ.get('TF_DEVICE_UUID')
                vm_uuid = environ.get('VM_UUID')
                if not device_uuid or not vm_uuid:
                    logger.debug('skipping worker pid=%d: missing TF_DEVICE_UUID or VM_UUID env' % proc.pid)
                    continue

                worker = Worker()
                worker.device_uuid = device_uuid
                worker.vm_uuid = vm_uuid
                worker.pid = proc.pid

                worker.protocol = 'shmem'
                for i, arg in enumerate(cmdline):
                    if arg == '-n' and i + 1 < len(cmdline):
                        worker.protocol = cmdline[i + 1]
                    elif arg == '-m' and i + 1 < len(cmdline):
                        shm_name = cmdline[i + 1]
                        worker.shared_memory_path = self.SHM_PREFIX + shm_name.lstrip('/')
                    elif arg == '-M' and i + 1 < len(cmdline):
                        try:
                            worker.shared_memory_size = int(cmdline[i + 1]) * self.BYTES_PER_MB
                        except ValueError:
                            pass

                # Reconstruct from environment
                cuda_visible = environ.get('CUDA_VISIBLE_DEVICES', '')
                try:
                    worker.cuda_index = int(cuda_visible)
                except ValueError:
                    worker.cuda_index = 0

                worker.pci_address = normalize_pci_address(environ.get('TF_PCI_ADDRESS')) or \
                    cuda_to_pci.get(worker.cuda_index, '')
                if not worker.pci_address:
                    logger.warn('skipping worker pid=%d: missing PCI address' % proc.pid)
                    continue

                mem_limit = environ.get('TF_GPU_MEMORY_LIMIT', '0')
                try:
                    worker.allocated_memory_mb = int(mem_limit)
                except ValueError:
                    worker.allocated_memory_mb = 0

                sm_limit = environ.get('TF_CUDA_SM_PERCENT_LIMIT', '0')
                try:
                    worker.sm_percent_limit = int(sm_limit)
                except ValueError:
                    worker.sm_percent_limit = 0

                enable_log = environ.get('TF_ENABLE_LOG')
                if enable_log is None:
                    worker.enable_log = self.DEFAULT_ENABLE_LOG
                else:
                    worker.enable_log = enable_log not in ('0', 'false', 'False')
                worker.log_level = environ.get('TF_LOG_LEVEL', self.DEFAULT_LOG_LEVEL)
                worker.license = environ.get('TF_LICENSE')
                worker.license_sign = environ.get('TF_LICENSE_SIGN')
                if not worker.license or not worker.license_sign:
                    logger.warn('skipping worker pid=%d: missing TF_LICENSE or TF_LICENSE_SIGN' % proc.pid)
                    continue

                workers.append(worker)
                logger.debug('scanned running worker: pid=%d, device=%s, vm=%s' %
                             (worker.pid, device_uuid, vm_uuid))

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        logger.info('scan_running: found %d tensor-fusion-worker processes' % len(workers))
        return workers

    @classmethod
    def _bytes_to_mb(cls, size):
        # type: (int) -> int
        if size <= 0:
            return 0
        return (size + cls.BYTES_PER_MB - 1) // cls.BYTES_PER_MB

    @staticmethod
    def is_alive(worker):
        # type: (Worker) -> bool
        """Check if a worker process is still alive."""
        try:
            import psutil
            p = psutil.Process(worker.pid)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except ImportError:
            # Fallback: use kill(0), then check Linux /proc state to filter zombies.
            try:
                os.kill(worker.pid, 0)
                return not ProcessExecutor._is_linux_zombie(worker.pid)
            except OSError:
                return False
        except Exception:
            return False

    @staticmethod
    def _is_linux_zombie(pid):
        # type: (int) -> bool
        try:
            with open('/proc/%s/stat' % pid, 'r') as fd:
                content = fd.read().strip()
        except IOError:
            return False

        if not content:
            return False

        parts = content.rsplit(') ', 1)
        if len(parts) != 2:
            return False

        state = parts[1][:1]
        return state == 'Z'

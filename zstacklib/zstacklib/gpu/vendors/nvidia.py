# -*- coding: utf-8 -*-
"""
NVIDIA GPU Vendor Implementation (Python 2/3 Compatible)
"""

import os
import re
import threading
import time

from zstacklib.utils import log, linux
from zstacklib.utils.bash import bash_roe
from zstacklib.gpu.base import (
    GPUBase,
    GPUInfo,
    GPUMetrics,
    VGPUMetrics,
    register_gpu_vendor
)
from zstacklib.gpu.operation_gate import gpu_operation_gate

logger = log.get_logger(__name__)


@register_gpu_vendor
class NVIDIA(GPUBase):
    """
    NVIDIA GPU vendor implementation.
    """

    # ==========================================================================
    # Vendor Identification
    # ==========================================================================

    VENDOR_NAME = "NVIDIA"
    VENDOR_ENUM_NAME = "NVIDIA"
    VENDOR_IDS = {"10de"}
    PCI_NAME_KEYWORDS = {"NVIDIA Corporation"}
    CLI_TOOL = "nvidia-smi"
    TENSORFUSION_WORKER_BINARY = "/usr/local/bin/tensor-fusion-worker"

    # Device types recognized as GPU
    DEVICE_TYPES = {"3D controller", "VGA compatible controller"}
    IS_GPU_VENDOR = True

    _metrics_lock = threading.Lock()
    _metrics_cache = []
    _metrics_cache_time = 0
    _pcie_metrics_cache = {}
    _pcie_last_attempt = {}
    _pcie_blocked_until = {}
    _basic_info_lock = threading.Lock()
    _basic_info_cache = []
    _basic_info_cache_time = 0

    METRICS_CACHE_SECONDS = 30
    METRICS_LAST_GOOD_SECONDS = 300
    QUERY_TIMEOUT_SECONDS = 12
    PCIE_CACHE_SECONDS = 60
    PCIE_CIRCUIT_BREAKER_SECONDS = 300
    VGPU_FAMILY_MAX_PROBE_ATTEMPTS = 3

    # ==========================================================================
    # PCI-only fallback (no nvidia-smi): match by vendor_id + class
    # ==========================================================================

    @classmethod
    def get_pci_only_candidates(cls, device_ids, device_names):
        """
        When nvidia-smi is not available, identify NVIDIA GPU by PCI: vendor 10de,
        class 3D controller or VGA compatible controller.
        """
        from zstacklib.utils.pci import normalize_pci_address

        result = []
        vendor_ids_lower = {v.lower() for v in cls.VENDOR_IDS}
        for slot in device_ids:
            if slot not in device_names or not slot.endswith('.0'):
                continue
            ids = device_ids[slot]
            names = device_names[slot]
            vendor_id = (ids.get('Vendor') or '').strip().lower()
            class_name = (names.get('Class') or '').strip()
            if vendor_id not in vendor_ids_lower:
                continue
            if class_name not in cls.DEVICE_TYPES:
                continue
            normalized = normalize_pci_address(slot)
            if normalized:
                result.append((normalized, {"isDriverLoaded": False}))
        return result

    # ==========================================================================
    # Tool Availability
    # ==========================================================================

    # nvidia-persistenced state tracking
    _persistenced_active = False
    _persistenced_lock = threading.Lock()

    @classmethod
    def has_nvidia_gpu(cls):
        """Check if NVIDIA GPU is present"""
        if not cls.is_available():
            return False
        r, o, e = bash_roe("nvidia-smi -L")
        return r == 0 and o and len(o.strip()) > 0

    # ==========================================================================
    # Basic Information Collection
    # ==========================================================================

    @classmethod
    def get_basic_info_cmd(cls, is_windows=False):
        """
        nvidia-smi command to get basic GPU info.

        Output format (CSV):
        00000000:3B:00.0, 15360 MiB, 70.00 W, 1322519087621

        Fields:
        1. gpu_bus_id     - PCI address
        2. memory.total   - Total GPU memory
        3. power.limit    - Power limit
        4. gpu_serial     - Serial number
        5. driver_version - NVIDIA driver version
        """
        cmd = "nvidia-smi --query-gpu=gpu_bus_id,memory.total,power.limit,gpu_serial,driver_version --format=csv,noheader"
        if is_windows:
            cmd = cmd.replace(" ", "|")
        return cmd

    @classmethod
    def get_basic_info(cls):
        if not cls.is_available():
            return []

        now = time.time()
        with cls._basic_info_lock:
            cache_age = now - cls._basic_info_cache_time
            if cls._basic_info_cache_time and cache_age < cls.METRICS_CACHE_SECONDS:
                return list(cls._basic_info_cache)

            error = ''
            cached_inventory = cls._inventory(
                cls._basic_info_cache)
            for _ in range(2):
                r, output, error = cls._run_critical_command(
                    "timeout %s %s" %
                    (cls.QUERY_TIMEOUT_SECONDS, cls.get_basic_info_cmd()))
                parsed = cls.parse_basic_info(output) if r == 0 else []
                has_usable_cache = (cls._basic_info_cache and
                                    cache_age < cls.METRICS_LAST_GOOD_SECONDS)
                if not parsed:
                    continue

                inventory = cls._inventory(parsed)
                missing_inventory = cached_inventory - inventory
                inventory_is_current = (
                    not has_usable_cache or
                    not missing_inventory or
                    not any(cls._is_nvidia_driver_bound(pci_address)
                            for pci_address in missing_inventory))
                if inventory_is_current:
                    cls._basic_info_cache = parsed
                    cls._basic_info_cache_time = now
                    return list(parsed)

            if cls._basic_info_cache and cache_age < cls.METRICS_LAST_GOOD_SECONDS:
                logger.warn("NVIDIA basic info query returned incomplete data, using last-good cache")
                return list(cls._basic_info_cache)
            logger.warn("Failed to get basic info for NVIDIA: %s" % error)
            return []

    @staticmethod
    def _inventory(gpu_infos):
        return frozenset(info.pci_address for info in gpu_infos
                         if info.pci_address)

    @staticmethod
    def _is_nvidia_driver_bound(pci_address):
        device_path = os.path.join('/sys/bus/pci/devices', pci_address)
        if not os.path.exists(device_path):
            return False
        driver_link = os.path.join(device_path, 'driver')
        if not os.path.islink(driver_link):
            return False
        return os.path.basename(os.path.realpath(driver_link)) == 'nvidia'

    @classmethod
    def parse_basic_info(cls, output):
        """
        Parse nvidia-smi basic info output.

        Input:
            00000000:3B:00.0, 15360 MiB, 70.00 W, 1322519087621

        Returns:
            List of GPUInfo objects
        """
        results = []
        if not output:
            return results

        for line in output.strip().split('\n'):
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 4:
                continue

            pci_address = cls.normalize_pci_address(parts[0])
            # Keep original string format for memory and power (e.g., "15360 MiB", "70.00 W")
            memory = parts[1].strip()
            power = parts[2].strip()
            serial = parts[3].strip()
            extra = {}
            if len(parts) >= 5:
                extra['driverVersion'] = parts[4].strip()

            results.append(GPUInfo(
                pci_address=pci_address,
                memory=memory,
                power=power,
                serial_number=serial,
                extra=extra
            ))
        return results

    # ==========================================================================
    # Prometheus Metrics Collection
    # ==========================================================================

    @classmethod
    def get_metric_cmd(cls, is_windows=False):
        """
        nvidia-smi command to get GPU metrics.

        Output format (CSV, no units):
        00000000:3B:00.0, 45, 62, 58, 65.23, 0, 1322519087621

        Fields:
        1. gpu_bus_id          - PCI address
        2. utilization.gpu     - GPU utilization (%)
        3. utilization.memory  - Memory utilization (%)
        4. temperature.gpu     - GPU temperature (C)
        5. power.draw          - Current power draw (W)
        6. index               - GPU index (for PCIe metrics)
        7. gpu_serial          - Serial number
        """
        cmd = "nvidia-smi --query-gpu=gpu_bus_id,utilization.gpu,utilization.memory,temperature.gpu,power.draw,index,gpu_serial --format=csv,noheader"
        if is_windows:
            cmd = cmd.replace(" ", "|")
        return cmd

    @classmethod
    def parse_metrics(cls, output):
        """
        Parse nvidia-smi metrics output.

        Returns list of GPUMetrics objects.
        """
        results = []
        if not output:
            return results

        for line in output.strip().split('\n'):
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 7:
                continue

            pci_address = cls.normalize_pci_address(parts[0])
            util = cls.parse_unit_value(parts[1])
            mem_util = cls.parse_unit_value(parts[2])
            temp = cls.parse_unit_value(parts[3])
            power = cls.parse_unit_value(parts[4])
            gpu_index = parts[5].strip()
            serial = parts[6]

            metrics = GPUMetrics(
                pci_address=pci_address,
                serial_number=serial,
                utilization=util,
                memory_utilization=mem_util,
                temperature=temp,
                power_draw=power
            )
            metrics._nvidia_index = gpu_index

            results.append(metrics)
        return results

    @classmethod
    def collect_metrics(cls):
        if not cls.is_available():
            return []

        now = time.time()
        with cls._metrics_lock:
            cache_age = now - cls._metrics_cache_time
            cached_inventory = cls._inventory(cls._metrics_cache)
            if not cls._metrics_cache_time or cache_age >= cls.METRICS_CACHE_SECONDS:
                result = cls._run_monitoring_command(
                    "timeout %s %s" %
                    (cls.QUERY_TIMEOUT_SECONDS, cls.get_metric_cmd()))
                if result is None:
                    if cache_age >= cls.METRICS_LAST_GOOD_SECONDS:
                        cls._metrics_cache = []
                    cls._apply_cached_pcie_metrics(cls._metrics_cache, now)
                    return list(cls._metrics_cache)
                r, output, error = result
                if r == 0:
                    try:
                        parsed = cls.parse_metrics(output)
                        has_usable_cache = (cls._metrics_cache and
                                            cache_age < cls.METRICS_LAST_GOOD_SECONDS)
                        missing_inventory = cached_inventory - cls._inventory(parsed)
                        inventory_is_current = (
                            not has_usable_cache or
                            not missing_inventory or
                            not any(cls._is_nvidia_driver_bound(pci_address)
                                    for pci_address in missing_inventory))
                        if parsed and inventory_is_current:
                            cls._metrics_cache = parsed
                            cls._metrics_cache_time = now
                        elif not parsed and cache_age >= cls.METRICS_LAST_GOOD_SECONDS:
                            cls._metrics_cache = []
                    except Exception as ex:
                        logger.warn("Failed to parse NVIDIA metrics: %s" % str(ex))
                elif cache_age >= cls.METRICS_LAST_GOOD_SECONDS:
                    logger.warn("Failed to collect NVIDIA metrics: %s" % error)
                    cls._metrics_cache = []

            metrics = cls._metrics_cache
            cls._collect_pcie_metrics(metrics, now)
            cls._apply_cached_pcie_metrics(metrics, now)
            return list(metrics)

    @classmethod
    def _collect_pcie_metrics(cls, metrics, now):
        if not metrics:
            return

        cache_key = '_all'
        if now < cls._pcie_blocked_until.get(cache_key, 0):
            return
        if now - cls._pcie_last_attempt.get(cache_key, 0) < cls.PCIE_CACHE_SECONDS:
            return

        result = cls._run_monitoring_command("timeout 10 nvidia-smi pci -gCnt")
        if result is None:
            return
        cls._pcie_last_attempt[cache_key] = now
        r, output, error = result
        if r != 0:
            cls._pcie_blocked_until[cache_key] = now + cls.PCIE_CIRCUIT_BREAKER_SECONDS
            logger.debug("Failed to collect NVIDIA PCIe metrics: %s" % error)
            return

        values_by_index = cls._parse_pcie_metrics(output)
        if not values_by_index:
            cls._pcie_blocked_until[cache_key] = now + cls.PCIE_CIRCUIT_BREAKER_SECONDS
            return

        for metric in metrics:
            gpu_index = getattr(metric, '_nvidia_index', None)
            if gpu_index not in values_by_index:
                continue
            tx_bytes, rx_bytes = values_by_index[gpu_index]
            cls._pcie_metrics_cache[metric.pci_address] = (
                tx_bytes, rx_bytes, now)
        cls._pcie_blocked_until.pop(cache_key, None)

    @classmethod
    def _apply_cached_pcie_metrics(cls, metrics, now):
        for metric in metrics:
            cached = cls._pcie_metrics_cache.get(metric.pci_address)
            if not cached or now - cached[2] >= cls.METRICS_LAST_GOOD_SECONDS:
                metric.pcie_tx_bytes = None
                metric.pcie_rx_bytes = None
                continue
            metric.pcie_tx_bytes = cached[0]
            metric.pcie_rx_bytes = cached[1]

    @classmethod
    def _parse_pcie_metrics(cls, output):
        result = {}
        gpu_index = None
        tx_bytes = None
        rx_bytes = None
        for line in (output or '').splitlines():
            line = line.strip()
            match = re.match(r'^GPU\s+(\d+):', line)
            if match:
                if gpu_index is not None and (tx_bytes is not None or rx_bytes is not None):
                    result[gpu_index] = (tx_bytes, rx_bytes)
                gpu_index = match.group(1)
                tx_bytes = None
                rx_bytes = None
            elif line.startswith("TX_BYTES:"):
                tx_bytes = cls.parse_unit_value(line.split()[-1])
            elif line.startswith("RX_BYTES:"):
                rx_bytes = cls.parse_unit_value(line.split()[-1])
        if gpu_index is not None and (tx_bytes is not None or rx_bytes is not None):
            result[gpu_index] = (tx_bytes, rx_bytes)
        return result

    @classmethod
    def _run_critical_command(cls, command):
        with gpu_operation_gate.critical():
            return bash_roe(command)

    @classmethod
    def _run_monitoring_command(cls, command):
        with gpu_operation_gate.monitoring() as acquired:
            if not acquired:
                return None
            return bash_roe(command)

    @classmethod
    def collect_vgpu_metrics(cls):
        """
        Collect vGPU metrics from nvidia-smi vgpu command.

        Returns list of VGPUMetrics for each active vGPU.
        """
        if not cls._has_active_mdev_devices():
            return []

        result = cls._run_monitoring_command("timeout 5 nvidia-smi vgpu -q")
        if result is None:
            return []
        r, output, _ = result
        if r != 0 or "VM Name" not in output:
            return []

        vgpu_metrics = []
        vgpu_list = cls._parse_vgpu_output(output)

        for vgpu in vgpu_list:
            vm_uuid = vgpu.get("VM Name", "")
            mdev_uuid = vgpu.get("MDEV UUID", "").replace('-', '')

            utilization = None
            if vgpu.get("Gpu"):
                try:
                    utilization = float(vgpu["Gpu"].replace('%', '').strip())
                except ValueError:
                    pass

            mem_util = None
            if vgpu.get("Memory"):
                try:
                    mem_util = float(vgpu["Memory"].replace('%', '').strip())
                except ValueError:
                    pass

            metrics = VGPUMetrics(
                vm_uuid=vm_uuid,
                mdev_uuid=mdev_uuid,
                utilization=utilization,
                memory_utilization=mem_util,
            )
            vgpu_metrics.append(metrics)

        return vgpu_metrics

    @classmethod
    def _has_active_mdev_devices(cls):
        mdev_dir = "/sys/bus/mdev/devices"
        try:
            return os.path.isdir(mdev_dir) and bool(os.listdir(mdev_dir))
        except OSError:
            return False

    @staticmethod
    def _parse_vgpu_output(output):
        """
        Parse nvidia-smi vgpu -q output into list of dicts.

        Output format:
            GPU 00000000:3B:00.0
                Active vGPUs: 1
                vGPU ID: 1
                    VM Name: test-vm
                    MDEV UUID: abc123
                    Gpu: 45%
                    Memory: 62%
        """
        vgpus = []
        current_vgpu = None

        for line in output.split('\n'):
            line = line.rstrip()
            if not line:
                continue

            # Detect vGPU section start
            if 'vGPU ID:' in line:
                if current_vgpu:
                    vgpus.append(current_vgpu)
                current_vgpu = {}
                continue

            # Parse key-value pairs
            if current_vgpu is not None and ':' in line:
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip()
                if key and value:
                    current_vgpu[key] = value

        if current_vgpu:
            vgpus.append(current_vgpu)

        return vgpus

    # ==========================================================================
    # dGPU (TensorFusion) Per-Worker Metrics
    # ==========================================================================

    @classmethod
    def collect_dgpu_worker_metrics(cls, workers):
        """Collect per-worker GPU metrics via nvidia-smi pmon + TensorFusion worker list.

        Args:
            workers: list of TensorFusion worker objects, each with device_uuid,
                     vm_uuid, pci_address, pid, container_id, restarting fields.

        Returns list of DGpuWorkerMetrics. Workers not found in pmon get 0 values.
        Only calls nvidia-smi pmon when there are active TF workers.
        """
        from zstacklib.gpu.base import DGpuWorkerMetrics

        if not workers:
            return []

        # Build {host_pid: worker} mapping
        pid_to_worker = {}
        for w in workers:
            if w.restarting:
                continue
            host_pid = cls._get_worker_host_pid(w)
            if host_pid:
                pid_to_worker[host_pid] = w

        if not pid_to_worker:
            return []

        # Get per-PID GPU metrics from nvidia-smi pmon
        pmon = cls._parse_pmon_output()
        if pmon is None:
            return []

        # Iterate all workers; default to 0 if not found in pmon
        result = []
        for host_pid, w in pid_to_worker.items():
            sm_util, fb_mib = pmon.get(host_pid, (0.0, 0.0))
            allocated = getattr(w, 'allocated_memory_mb', 0) or 0
            mem_pct = min((fb_mib / allocated * 100.0), 100.0) if allocated > 0 else 0.0
            result.append(DGpuWorkerMetrics(
                device_uuid=w.device_uuid or '',
                vm_uuid=w.vm_uuid or '',
                pci_address=w.pci_address or '',
                utilization=sm_util,
                memory_utilization=mem_pct,
            ))
        return result

    @classmethod
    def _parse_pmon_output(cls):
        """Call nvidia-smi pmon and return {pid: (sm_util, fb_mib)}.

        sm_util: GPU SM utilization percentage from pmon.
        fb_mib: framebuffer usage in MiB (absolute value, converted to % later using worker.allocatedMemoryMb).
        """
        result = cls._run_monitoring_command("timeout 10 nvidia-smi pmon -c 1 -s mu")
        if result is None:
            return None
        r, o, _ = result
        if r != 0:
            return None

        # nvidia-smi pmon -c 1 -s mu output columns:
        # gpu  pid  type  fb  ccpm  sm  mem  enc  dec  jpg  ofa  command
        #  0    1    2    3    4    5    6    7    8    9   10     11
        result = {}
        for line in o.strip().splitlines():
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            parts = line.split()
            if len(parts) < 7:
                continue
            try:
                pid = int(parts[1])
                sm = float(parts[5]) if parts[5] != '-' else 0.0
                fb_mib = float(parts[3]) if parts[3] != '-' else 0.0
                result[pid] = (sm, fb_mib)
            except (ValueError, IndexError):
                continue
        return result

    @staticmethod
    def _get_worker_host_pid(worker):
        """Get the host-visible PID for a TF worker (handles container mode)."""
        if worker.container_id:
            import subprocess
            proc = None
            try:
                proc = subprocess.Popen(
                    ['docker', 'inspect', '--format', '{{.State.Pid}}', worker.container_id],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    close_fds=True
                )
                stdout, stderr = proc.communicate(timeout=5)
                if proc.returncode != 0:
                    err = stderr.decode('utf-8', 'ignore').strip() if stderr else ''
                    logger.debug('failed to inspect container %s: %s' % (worker.container_id, err))
                    return None
                o = stdout.decode('utf-8', 'ignore').strip()
                if o.isdigit():
                    return int(o)
            except subprocess.TimeoutExpired:
                if proc is not None:
                    proc.kill()
                    proc.wait()
                logger.warning('docker inspect timed out for container %s' % worker.container_id)
                return None
            except Exception as e:
                logger.debug('failed to inspect container %s: %s' % (worker.container_id, str(e)))
                return None
        return worker.pid

    # ==========================================================================
    # Pre-Detach Hooks
    # ==========================================================================

    @classmethod
    def pre_detach_from_vm(cls, domain, vm_uuid):
        """
        Stop nvidia-persistenced in VM before GPU detach.

        This prevents the VM from holding GPU resources.
        """
        from zstacklib.utils.qga import VmQga

        if not domain or not domain.isActive():
            logger.info(
                "No need to shutdown nvidia-persistenced for VM %s, not running" % vm_uuid)
            return 0, None

        logger.info("Shutting down nvidia-persistenced for VM %s" % vm_uuid)

        qga = VmQga(domain)
        if qga.state != VmQga.QGA_STATE_RUNNING:
            return 0, "QGA not running for VM %s, skipping" % vm_uuid

        is_windows = "mswindows" in qga.os
        cmd = cls.get_shut_persistenced_cmd(is_windows)

        if is_windows:
            exitcode, ret_data = qga.guest_exec_powershell(cmd)
        else:
            exitcode, ret_data, _ = qga.guest_exec_bash(cmd)

        return exitcode, ret_data

    @classmethod
    def pre_detach_from_host(cls):
        """Stop nvidia-persistenced on host before GPU detach"""
        logger.info("Shutting down nvidia-persistenced on host")
        cmd = cls.get_shut_persistenced_cmd()
        r, o, _ = bash_roe(cmd)
        return r, o

    # ==========================================================================
    # Device In-Use Check
    # ==========================================================================

    # Processes that transiently open nvidia devices for monitoring/management
    # and are safe to ignore when deciding whether a GPU is actively in use.
    _IGNORED_COMMANDS = frozenset([
        "nvidia-smi",
    ])

    @classmethod
    def _get_dev_path(cls, pci_address):
        """Find /dev/nvidia{N} device path for a given PCI address.

        Uses nvidia-smi to get the authoritative index-to-PCI mapping.

        Args:
            pci_address: Normalized PCI address (e.g., "0000:34:00.0").

        Returns:
            Device path like "/dev/nvidia0", or None if not found.
        """
        try:
            r, o, e = bash_roe(
                "nvidia-smi --query-gpu=index,pci.bus_id --format=csv,noheader 2>/dev/null"
            )
            if r != 0 or not o.strip():
                return None

            # nvidia-smi outputs lines like "0, 00000000:34:00.0"
            # The bus_id uses 8-digit domain; normalize both sides for comparison.
            target = pci_address.lower()
            for line in o.strip().splitlines():
                parts = line.split(",")
                if len(parts) != 2:
                    continue
                idx = parts[0].strip()
                bus_id = parts[1].strip().lower()
                # nvidia-smi uses 8-digit domain (e.g. 00000000:xx:xx.x),
                # normalize to 4-digit (0000:xx:xx.x) for comparison
                domain = bus_id.split(":")[0]
                if len(domain) == 8:
                    bus_id = bus_id[4:]
                if bus_id == target:
                    dev_path = "/dev/nvidia%s" % idx
                    if os.path.exists(dev_path):
                        return dev_path
                    return None
        except Exception:
            pass

        return None

    @classmethod
    def check_device_in_use(cls, pci_address):
        """Check if an NVIDIA GPU is in use by other processes.

        This prevents unbinding a GPU that is actively used, which would cause
        the NVIDIA driver's nv_pci_remove() to hang indefinitely in kernel space,
        leading to zombie processes and libvirtd failure.

        Args:
            pci_address: Normalized PCI address (e.g., "0000:34:00.0").

        Raises:
            PciError: When the device is in use by other processes.
        """
        from zstacklib.hardware.pci.address import PciError

        device_path = os.path.join("/sys/bus/pci/devices", pci_address)
        if not os.path.exists(device_path):
            return

        driver_link = os.path.join(device_path, "driver")
        if not os.path.islink(driver_link):
            return

        current_driver = os.path.basename(os.path.realpath(driver_link))
        if current_driver != "nvidia":
            return

        dev_path = cls._get_dev_path(pci_address)
        if not dev_path:
            logger.debug("cannot find /dev/nvidia* for pci device %s, skip in-use check", pci_address)
            return

        r, o, e = bash_roe("fuser %s 2>/dev/null" % dev_path)
        if r == 1 or not o.strip():
            # fuser exit 1 means no process using the device
            return
        if r != 0:
            # fuser failed (e.g., not installed rc=127), log and skip check
            logger.debug("fuser command failed (rc=%d) for %s, skip in-use check", r, dev_path)
            return

        pids = re.findall(r'\d+', o)
        active_details = []
        for pid in pids:
            try:
                comm = linux.read_file("/proc/%s/comm" % pid)
                comm = comm.strip() if comm else "unknown"
            except Exception:
                if not os.path.exists("/proc/%s" % pid):
                    continue
                comm = "unknown"
            if comm in cls._IGNORED_COMMANDS:
                logger.debug("ignoring benign process %s(%s) on %s", pid, comm, dev_path)
                continue
            active_details.append("%s(%s)" % (pid, comm))
            if len(active_details) >= 5:
                break

        if not active_details:
            return

        raise PciError(
            "GPU %s (%s) is currently in use by process: %s. "
            "Unbinding a busy NVIDIA GPU will cause the kernel driver to hang indefinitely. "
            "Please stop the process using this GPU before detaching it."
            % (pci_address, dev_path, ", ".join(active_details))
        )

    # ==========================================================================
    # Persistenced Management Commands
    # ==========================================================================

    @classmethod
    def get_shut_persistenced_cmd(cls, is_windows=False):
        """Get command to shut down nvidia-persistenced"""
        cmd = "ps -ef | grep nvidia-persistenced | grep -v grep | awk '{print $2}' | xargs -r kill -15"
        if is_windows:
            cmd = cmd.replace(" ", "|")
        return cmd

    # ==========================================================================
    # Persistenced Management
    # ==========================================================================

    @classmethod
    def ensure_persistenced_running(cls, timeout=5):
        """
        Ensure nvidia-persistenced is running.

        This daemon keeps the GPU initialized and improves startup latency.
        """
        with cls._persistenced_lock:
            # Check if already running
            r, o, _ = bash_roe("pgrep -f nvidia-persistenced || true")
            is_running = bool(o and o.strip())

            if is_running:
                cls._persistenced_active = True
                return True

            if cls._persistenced_active:
                cls._persistenced_active = False
                logger.debug(
                    "nvidia-persistenced stopped, will retry next cycle")
                return True

            # Start persistenced
            start_cmd = "nohup nvidia-persistenced >/dev/null 2>&1 &"
            logger.info("Starting nvidia-persistenced: %s" % start_cmd)
            bash_roe(start_cmd)

            # Wait and verify
            import time
            time.sleep(timeout)
            r, o, _ = bash_roe("pgrep -f nvidia-persistenced || true")
            if o and o.strip():
                cls._persistenced_active = True
                return True
            else:
                logger.warn("nvidia-persistenced failed to start")
                return False

    # ==========================================================================
    # VM Guest Tool Support
    # ==========================================================================

    @classmethod
    def get_vm_gpu_info_cmd(cls, is_windows=False):
        """Same command works inside VM"""
        return cls.get_basic_info_cmd(is_windows)

    @classmethod
    def parse_vm_gpu_info(cls, output):
        """Same parsing works inside VM"""
        return cls.parse_basic_info(output)

    # ==========================================================================
    # Virtualization Capabilities Detection
    # ==========================================================================

    @classmethod
    def _is_bound_to_vfio(cls, pci_address):
        """Check if a PCI device is bound to vfio-pci driver (GPU passthrough)."""
        driver_link = os.path.join("/sys/bus/pci/devices", pci_address, "driver")
        if os.path.islink(driver_link):
            current_driver = os.path.basename(os.path.realpath(driver_link))
            return current_driver in ("vfio-pci", "vfio_pci")
        return False

    @classmethod
    def detect_vfio_mdev_capability(cls, pci_device_to, prepared_context=None):
        """
        Detect NVIDIA vGPU (VFIO mdev) capability.

        Returns tuple: (is_supported, capability_info)
        """
        import os
        addr = pci_device_to.pciDeviceAddress

        if cls._is_bound_to_vfio(addr):
            logger.debug('vGPU capability check skipped for %s: device bound to vfio-pci (passthrough)' % addr)
            return False, {}

        check_mdev_folder = '/sys/bus/pci/devices/%s/mdev_supported_types' % addr
        legacy_mdev_dir_exists = os.path.isdir(check_mdev_folder)
        check_virtfn_folder = '/sys/bus/pci/devices/%s/virtfn0/mdev_supported_types' % addr
        virt_function_dir_exits = os.path.isdir(check_virtfn_folder)
        if prepared_context is not None:
            probe = cls._get_cached_vgpu_probe(pci_device_to, prepared_context)
            if not probe['supported']:
                return False, {}
            o = probe['output']
        else:
            r, o, e = cls._run_critical_command(
                "timeout 10 nvidia-smi vgpu -i %s -v -c" % addr)
            if r != 0 or not o or "No supported devices" in o:
                rs, support, _ = cls._run_critical_command(
                    "timeout 10 nvidia-smi vgpu -i %s -s" % addr)
                if rs != 0 or not support or "No supported devices" in support:
                    return False, {}
                o = support

        mdev_specs = []
        for line in o.splitlines()[1:]:
            parts = line.split(':')
            if len(parts) < 2:
                continue
            title = parts[0].strip()
            content = ' '.join(parts[1:]).strip()
            if title == "vGPU Type ID":
                spec = {'TypeId': content}
                mdev_specs.append(spec)
            else:
                if mdev_specs:
                    mdev_specs[-1][title] = content

        capability_info = {
            'mdevSpecifications': mdev_specs
        }

        # Determine virtStatus based on mdev directory structure
        if legacy_mdev_dir_exists:
            if prepared_context is not None:
                if cls._has_mdev_for_pci_address(addr):
                    cls.set_capability_virt_metadata(
                        capability_info, "VFIO_MDEV_VIRTUALIZED",
                        "VIRTUALIZED", "VFIO_MDEV", ["VFIO_MDEV"])
                else:
                    cls.set_capability_virt_metadata(
                        capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                        "VIRTUALIZABLE", None, ["VFIO_MDEV"])
                return True, capability_info

            # Legacy mdev: check if supported specs != creatable specs
            rs, support, _ = cls._run_critical_command(
                "timeout 10 nvidia-smi vgpu -i %s -s | grep -v %s" % (addr, addr))
            rc, creatable, _ = cls._run_critical_command(
                "timeout 10 nvidia-smi vgpu -i %s -c | grep -v %s" % (addr, addr))
            if rs != 0:
                return False, {}
            if rc != 0:
                cls.set_capability_virt_metadata(
                    capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                    "VIRTUALIZABLE", None, ["VFIO_MDEV"])
            else:
                if support != creatable:
                    cls.set_capability_virt_metadata(
                        capability_info, "VFIO_MDEV_VIRTUALIZED",
                        "VIRTUALIZED", "VFIO_MDEV", ["VFIO_MDEV"])
                else:
                    cls.set_capability_virt_metadata(
                        capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                        "VIRTUALIZABLE", None, ["VFIO_MDEV"])
        elif virt_function_dir_exits:
            # Virt function: check virtfn and mdev devices
            r, o, e = bash_roe(
                "ls /sys/bus/pci/devices/%s/ | grep virtfn" % addr)
            if r == 0:
                mdev_r, mdev_o, _ = bash_roe("ls /sys/bus/mdev/devices/")
                virtualizable = False
                mdev_devices_exists = False
                for virtfn in o.splitlines():
                    virtfn_dir = "/sys/bus/pci/devices/%s/%s/" % (addr, virtfn)
                    for mdev in mdev_o.splitlines():
                        if os.path.exists(os.path.join(virtfn_dir, mdev)):
                            mdev_devices_exists = True
                            break
                    mdev_types_dir = os.path.join(virtfn_dir, 'mdev_supported_types')
                    if os.path.isdir(mdev_types_dir):
                        for virf in os.listdir(mdev_types_dir):
                            if "nvidia-" in virf:
                                virtualizable = True
                                break
                if mdev_devices_exists:
                    cls.set_capability_virt_metadata(
                        capability_info, "VFIO_MDEV_VIRTUALIZED",
                        "VIRTUALIZED", "VFIO_MDEV", ["VFIO_MDEV"])
                elif virtualizable:
                    cls.set_capability_virt_metadata(
                        capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                        "VIRTUALIZABLE", None, ["VFIO_MDEV"])
                else:
                    cls.set_capability_virt_metadata(
                        capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                        "VIRTUALIZABLE", None, ["VFIO_MDEV"])
            else:
                cls.set_capability_virt_metadata(
                    capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                    "VIRTUALIZABLE", None, ["VFIO_MDEV"])
        else:
            cls.set_capability_virt_metadata(
                capability_info, "VFIO_MDEV_VIRTUALIZABLE",
                "VIRTUALIZABLE", None, ["VFIO_MDEV"])

        return True, capability_info

    @classmethod
    def _get_cached_vgpu_probe(cls, pci_device_to, prepared_context):
        addr = cls.normalize_pci_address(pci_device_to.pciDeviceAddress)
        gpu_info = prepared_context.get('gpu_info_map', {}).get(addr, {})
        family = (gpu_info.get('_deviceId') or getattr(pci_device_to, 'deviceId', None) or addr,
                  gpu_info.get('driverVersion') or '')
        cache = prepared_context.setdefault('vgpu_families', {})
        if family in cache:
            return cache[family]

        attempts = prepared_context.setdefault('vgpu_family_attempts', {})
        if attempts.get(family, 0) >= cls.VGPU_FAMILY_MAX_PROBE_ATTEMPTS:
            return {'supported': False, 'output': '', 'unknown': True}
        attempts[family] = attempts.get(family, 0) + 1

        r, output, error = cls._run_critical_command(
            "timeout 10 nvidia-smi vgpu -i %s -s" % addr)
        supported = r == 0 and "vGPU Type ID" in (output or '')
        explicit_unsupported = "No supported devices" in (
            "%s\n%s" % (output or '', error or ''))
        result = {
            'supported': supported,
            'output': output if supported else '',
            'unknown': not supported and not explicit_unsupported,
        }
        if supported or explicit_unsupported:
            cache[family] = result
        return result

    @classmethod
    def _has_mdev_for_pci_address(cls, pci_address):
        mdev_dir = "/sys/bus/mdev/devices"
        try:
            for mdev_uuid in os.listdir(mdev_dir):
                path = os.path.realpath(os.path.join(mdev_dir, mdev_uuid))
                if pci_address in path:
                    return True
        except OSError:
            pass
        return False

    @classmethod
    def detect_sriov_capability(cls, pci_device_to, gpu_info_map=None):
        """
        Detect NVIDIA SR-IOV capability.

        Returns tuple: (is_supported, capability_info)
        """
        import os
        from zstacklib.utils import pci, gpu

        addr = pci_device_to.pciDeviceAddress
        dev = os.path.join("/sys/bus/pci/devices/", addr)
        totalvfs = os.path.join(dev, "sriov_totalvfs")
        numvfs = os.path.join(dev, "sriov_numvfs")
        physfn = os.path.join(dev, "physfn")
        gpuvf = os.path.join(dev, "gpuvf")

        capability_info = {}

        if os.path.exists(totalvfs):
            # PF (Physical Function)
            with open(totalvfs, 'r') as f:
                capability_info['maxPartNum'] = f.read().strip()

            with open(numvfs, 'r') as f:
                if f.read().strip() != '0':
                    cls.set_capability_virt_metadata(
                        capability_info, "SRIOV_VIRTUALIZED",
                        "VIRTUALIZED", "SRIOV", ["SRIOV"])
                else:
                    cls.set_capability_virt_metadata(
                        capability_info, "SRIOV_VIRTUALIZABLE",
                        "VIRTUALIZABLE", None, ["SRIOV"])
            return True, capability_info
        elif os.path.exists(physfn):
            # VF (Virtual Function)
            numvfs = os.path.join(physfn, "sriov_numvfs")
            if os.path.exists(numvfs):
                with open(numvfs, 'r') as f:
                    capability_info['maxPartNum'] = f.read().strip()

            # For NVIDIA A-Series, after driver successfully installed, virtfn files will be created
            # set deviceId and vendorId null
            virtfn = os.path.join(dev, os.readlink(physfn), 'virtfn0')
            is_nvidia_gpu = False

            # Use pre-collected gpu_info_map if available
            if gpu_info_map is not None:
                normalized_pci = pci.normalize_pci_address(addr)
                is_nvidia_gpu = normalized_pci in gpu_info_map if normalized_pci else False
            else:
                # Fallback to individual query (backward compatibility)
                gpu_info = gpu.get_info(
                    pci_device=pci_device_to, vendor_name=cls.VENDOR_NAME)
                is_nvidia_gpu = gpu_info is not None

            if is_nvidia_gpu and cls.is_available() and os.path.exists(virtfn):
                # NVIDIA A-Series VF: clear device/vendor IDs
                pci_device_to.deviceId = ""
                pci_device_to.vendorId = ""
            cls.set_capability_virt_metadata(
                capability_info, "SRIOV_VIRTUAL",
                "VIRTUAL", "SRIOV", [])

            capability_info['parentAddress'] = os.readlink(
                physfn).split('/')[-1]

            if os.path.exists(gpuvf):
                with open(gpuvf, 'r') as f:
                    for line in f.readlines():
                        line = line.strip()
                        if 'VF FB Size' in line:
                            capability_info['ramSize'] = line.split(
                                ':')[-1].strip()
                            break

            return True, capability_info
        else:
            return False, {}

    @classmethod
    def detect_tensorfusion_capability(cls, pci_device_to, prepared_context=None):
        """
        Detect NVIDIA TensorFusion (GPU virtualization) capability.

        Requirements:
        - NVIDIA driver version >= 570.x

        Returns tuple: (is_supported, capability_info)
        """
        addr = pci_device_to.pciDeviceAddress
        dev = os.path.join("/sys/bus/pci/devices/", addr)
        physfn = os.path.join(dev, "physfn")

        if os.path.exists(physfn):
            logger.debug('TensorFusion capability check skipped for %s: SR-IOV VF is not eligible' % addr)
            return False, {}

        if cls._is_bound_to_vfio(addr):
            logger.debug('TensorFusion capability check skipped for %s: device bound to vfio-pci (passthrough)' % addr)
            return False, {}

        if prepared_context is not None:
            normalized = cls.normalize_pci_address(addr)
            gpu_info = prepared_context.get('gpu_info_map', {}).get(normalized, {})
            driver_version = gpu_info.get('driverVersion')
            if not driver_version:
                logger.debug('TensorFusion capability check failed for %s: driver version missing from batch query' % addr)
                return False, {}
        else:
            r, o, e = cls._run_critical_command(
                'timeout 10 nvidia-smi --query-gpu=pci.bus_id,driver_version --format=csv,noheader -i %s' % addr)
            if r != 0:
                logger.debug('TensorFusion capability check failed for %s: nvidia-smi query failed' % addr)
                return False, {}

            parts = [p.strip() for p in o.strip().split(',')]
            if len(parts) < 2:
                logger.debug('TensorFusion capability check failed for %s: unexpected nvidia-smi output' % addr)
                return False, {}
            driver_version = parts[1]

        capability_info = {
            'driverVersion': driver_version
        }

        try:
            # Parse driver version (e.g., "535.104.05" -> 535)
            driver_major = int(driver_version.split('.')[0])
            if driver_major < 570:
                cls.set_capability_virt_metadata(
                    capability_info, "TENSORFUSION_NOT_SUPPORTED", "", None, [])
                capability_info['reason'] = "Driver version %s < 570.x" % driver_version
                return False, capability_info

            supported, reason = cls._get_tensorfusion_prerequisites(prepared_context)
            if not supported:
                cls.set_capability_virt_metadata(
                    capability_info, "TENSORFUSION_NOT_SUPPORTED", "", None, [])
                capability_info['reason'] = reason
                return False, capability_info

            # Check if TensorFusion worker can be created (virtualizable)
            # A follow-up enhancement can check whether workers are already
            # running (virtualized).
            cls.set_capability_virt_metadata(
                capability_info, "TENSORFUSION_VIRTUALIZABLE",
                "VIRTUALIZABLE", None, ["TENSORFUSION"])
            return True, capability_info

        except (ValueError, IndexError) as ex:
            logger.warn('TensorFusion capability check failed for %s: failed to parse version info: %s' % (addr, str(ex)))
            cls.set_capability_virt_metadata(
                capability_info, "TENSORFUSION_NOT_SUPPORTED", "", None, [])
            capability_info['reason'] = "Failed to parse version info"
            return False, capability_info

    @classmethod
    def prepare_capability_context(cls, gpu_info_map):
        return {
            'gpu_info_map': gpu_info_map,
            'vgpu_families': {},
            'vgpu_family_attempts': {},
            'tensorfusion_prerequisites': None,
        }

    @classmethod
    def _get_tensorfusion_prerequisites(cls, prepared_context=None):
        if prepared_context is not None:
            cached = prepared_context.get('tensorfusion_prerequisites')
            if cached is not None:
                return cached

        r_docker, _, _ = bash_roe('which docker')
        if r_docker != 0:
            result = (False, "docker is not installed or not in PATH")
        else:
            r_ctk, _, _ = bash_roe('which nvidia-ctk')
            if r_ctk != 0:
                result = (False, "nvidia-container-toolkit (nvidia-ctk) is not installed")
            else:
                r_img, _, _ = bash_roe('docker image inspect tf-worker:latest')
                if r_img != 0:
                    result = (False, "tf-worker:latest image not found, install via zstack-dgpu-toolkit.bin or docker load")
                else:
                    result = (True, '')

        if prepared_context is not None:
            prepared_context['tensorfusion_prerequisites'] = result
        return result

    # ==========================================================================
    # GPU Detail Query
    # ==========================================================================



    @classmethod
    def query_gpu_details(cls):
        """Query nvidia-smi for GPU detail information.

        Returns:
            dict: {pci_address: {cuda_index, pci_address, name, total_memory_mb, driver_version}}
                  Keys are normalized via zstacklib.utils.pci.normalize_pci_address.
        """
        from zstacklib.utils.pci import normalize_pci_address

        if not cls.is_available():
            logger.warn('nvidia-smi not available')
            return {}

        _DETAIL_QUERY_CMD = (
            'timeout %s nvidia-smi --query-gpu=index,pci.bus_id,name,memory.total,driver_version '
            '--format=csv,noheader,nounits' % cls.QUERY_TIMEOUT_SECONDS)

        r, o, e = cls._run_critical_command(_DETAIL_QUERY_CMD)
        if r != 0:
            logger.warn('nvidia-smi detail query failed (rc=%d): %s' % (r, e))
            return {}

        result = {}
        for line in o.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 5:
                logger.warn('unexpected nvidia-smi output line: %s' % line)
                continue

            try:
                cuda_index = int(parts[0])
            except ValueError:
                logger.warn('invalid cuda index: %s' % parts[0])
                continue

            pci_address = normalize_pci_address(parts[1])
            try:
                total_memory_mb = int(float(parts[3]))
            except ValueError:
                total_memory_mb = 0

            entry = {
                'cuda_index': cuda_index,
                'pci_address': pci_address,
                'name': parts[2],
                'total_memory_mb': total_memory_mb,
                'driver_version': parts[4],
            }
            result[pci_address] = entry

        return result

# -*- coding: utf-8 -*-
"""
NVIDIA GPU Vendor Implementation (Python 2/3 Compatible)
"""

import os
import threading

from zstacklib.utils import log
from zstacklib.utils.bash import bash_roe
from zstacklib.gpu.base import (
    GPUBase,
    GPUInfo,
    GPUMetrics,
    VGPUMetrics,
    register_gpu_vendor
)

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
        """
        cmd = "nvidia-smi --query-gpu=gpu_bus_id,memory.total,power.limit,gpu_serial --format=csv,noheader"
        if is_windows:
            cmd = cmd.replace(" ", "|")
        return cmd

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

            results.append(GPUInfo(
                pci_address=pci_address,
                memory=memory,
                power=power,
                serial_number=serial
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

            # Get PCIe metrics
            pcie_tx_bytes = None
            pcie_rx_bytes = None
            if gpu_index:
                try:
                    r, pci_output, _ = bash_roe(
                        "nvidia-smi pci -gCnt -i %s" % gpu_index)
                    if r == 0 and pci_output:
                        for pci_line in pci_output.splitlines():
                            pci_line = pci_line.strip()
                            if pci_line.startswith("TX_BYTES:"):
                                tx_value = pci_line.split()[-1]
                                pcie_tx_bytes = cls.parse_unit_value(tx_value)
                            elif pci_line.startswith("RX_BYTES:"):
                                rx_value = pci_line.split()[-1]
                                pcie_rx_bytes = cls.parse_unit_value(rx_value)
                except Exception as e:
                    logger.debug(
                        "Failed to get PCIe metrics for GPU %s: %s" % (gpu_index, str(e)))

            metrics = GPUMetrics(
                pci_address=pci_address,
                serial_number=serial,
                utilization=util,
                memory_utilization=mem_util,
                temperature=temp,
                power_draw=power,
                pcie_tx_bytes=pcie_tx_bytes,
                pcie_rx_bytes=pcie_rx_bytes
            )

            results.append(metrics)
        return results

    @classmethod
    def collect_vgpu_metrics(cls):
        """
        Collect vGPU metrics from nvidia-smi vgpu command.

        Returns list of VGPUMetrics for each active vGPU.
        """
        r, output, _ = bash_roe("nvidia-smi vgpu -q")
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
    def detect_vfio_mdev_capability(cls, pci_device_to):
        """
        Detect NVIDIA vGPU (VFIO mdev) capability.

        Returns tuple: (is_supported, capability_info)
        """
        import os
        addr = pci_device_to.pciDeviceAddress
        check_mdev_folder = '/sys/bus/pci/devices/%s/mdev_supported_types' % addr
        legacy_mdev_dir_exists = os.path.isdir(check_mdev_folder)
        check_virtfn_folder = '/sys/bus/pci/devices/%s/virtfn0/mdev_supported_types' % addr
        virt_function_dir_exits = os.path.isdir(check_virtfn_folder)

        # Check if nvidia vgpu is supported by current device
        r, o, e = bash_roe("nvidia-smi vgpu -i %s -v -c" % addr)
        if r != 0 or not o or "No supported devices" in o:
            # SR-IOV backed vGPU cards (e.g. L20, RTX8000) may not report
            # creatable types on the PF before VFs are created. Fall back to
            # supported-types query which still reflects device capability.
            rs, support, _ = bash_roe("nvidia-smi vgpu -i %s -s" % addr)
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
            # Legacy mdev: check if supported specs != creatable specs
            rs, support, _ = bash_roe("nvidia-smi vgpu -i %s -s | grep -v %s" %
                                      (addr, addr))
            rc, creatable, _ = bash_roe(
                "nvidia-smi vgpu -i %s -c | grep -v %s" % (addr, addr))
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
    def detect_tensorfusion_capability(cls, pci_device_to):
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

        r, o, e = bash_roe('nvidia-smi --query-gpu=pci.bus_id,driver_version --format=csv,noheader -i %s' % addr)
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

            if not os.path.exists(cls.TENSORFUSION_WORKER_BINARY):
                cls.set_capability_virt_metadata(
                    capability_info, "TENSORFUSION_NOT_SUPPORTED", "", None, [])
                capability_info['reason'] = "TensorFusion worker binary %s not found" % cls.TENSORFUSION_WORKER_BINARY
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

        _DETAIL_QUERY_CMD = ('nvidia-smi --query-gpu=index,pci.bus_id,name,memory.total,driver_version '
                             '--format=csv,noheader,nounits')

        r, o, e = bash_roe(_DETAIL_QUERY_CMD)
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

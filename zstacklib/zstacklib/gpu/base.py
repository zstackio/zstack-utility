# -*- coding: utf-8 -*-
"""
GPU Base Class and Registry (Python 2/3 Compatible)
"""

import abc
import re
import threading

from zstacklib.utils import log
from zstacklib.utils.bash import bash_roe, bash_ro

logger = log.get_logger(__name__)


# =============================================================================
# VendorEnum - GPU Vendor Enumeration
# =============================================================================

class VendorEnum:
    """
    GPU vendor enumeration constants.

    This enum is used throughout the codebase for vendor identification.
    Moved from zstacklib.utils.pci to keep GPU-related logic together.
    """
    INTEL = "Intel"
    AMD = "AMD"
    NVIDIA = "NVIDIA"
    HAIGUANG = "Haiguang"
    HUAWEI = "Huawei"
    TIANSHU = "TianShu"
    VASTAI = "Vastai"
    ENFLAME = "Enflame"
    ALIBABA = "Alibaba"
    KUNLUNXIN = "Kunlunxin"


# =============================================================================
# PCI Class Names and GPU Type Constants (for type refinement)
# =============================================================================
# PCI class strings (lspci Class); pci_device_mapper keys use these for i18n.
PCI_CLASS_VGA = "VGA compatible controller"
PCI_CLASS_DISPLAY = "Display controller"
PCI_CLASS_PROCESSING_ACCEL = "Processing accelerators"
PCI_CLASS_COPROCESSOR = "Co-processor"
PCI_CLASS_COMMUNICATION = "Communication controller"
PCI_CLASS_3D = "3D controller"

# ZStack GPU result types (API/UI contract).
GPU_TYPE_VIDEO_CONTROLLER = "GPU_Video_Controller"
GPU_TYPE_PROCESSING_ACCELERATORS = "GPU_Processing_Accelerators"
GPU_TYPE_CO_PROCESSOR = "GPU_Co_Processor"
GPU_TYPE_COMMUNICATION_CONTROLLER = "GPU_Communication_Controller"
GPU_TYPE_3D_CONTROLLER = "GPU_3D_Controller"


# =============================================================================
# Data Classes (Python 2/3 Compatible)
# =============================================================================

class GPUInfo(object):
    """
    Standard GPU information structure returned by basic info collection.
    """

    def __init__(
            self,
            pci_address,
            memory=None,
            power=None,
            serial_number=None,
            device_name=None,
            driver_loaded=True,
            extra=None):
        self.pci_address = pci_address
        self.memory = memory
        self.power = power
        self.serial_number = serial_number
        self.device_name = device_name
        self.driver_loaded = driver_loaded
        self.extra = extra or {}

    def to_addon_dict(self):
        """Convert to addonInfo dictionary format used by host_plugin"""
        result = {
            "isDriverLoaded": self.driver_loaded
        }
        if self.memory:
            result["memory"] = self.memory
        if self.power:
            result["power"] = self.power
        if self.serial_number:
            result["serialNumber"] = self.serial_number
        if self.extra:
            result.update(self.extra)
        return result


class GPUMetrics(object):
    """
    Standard GPU metrics structure for Prometheus collection.
    """

    def __init__(
            self,
            pci_address,
            serial_number=None,
            utilization=None,
            memory_utilization=None,
            temperature=None,
            power_draw=None,
            fan_speed=None,
            pcie_tx_bytes=None,
            pcie_rx_bytes=None,
            extra=None):
        self.pci_address = pci_address
        self.serial_number = serial_number
        self.utilization = utilization
        self.memory_utilization = memory_utilization
        self.temperature = temperature
        self.power_draw = power_draw
        self.fan_speed = fan_speed
        self.pcie_tx_bytes = pcie_tx_bytes
        self.pcie_rx_bytes = pcie_rx_bytes
        self.extra = extra or {}


class VGPUMetrics(object):
    """vGPU/mdev metrics for Prometheus collection"""

    def __init__(
            self,
            vm_uuid,
            mdev_uuid,
            utilization=None,
            memory_utilization=None):
        self.vm_uuid = vm_uuid
        self.mdev_uuid = mdev_uuid
        self.utilization = utilization
        self.memory_utilization = memory_utilization


class DGpuWorkerMetrics(object):
    """dGPU (TensorFusion) per-worker metrics for Prometheus collection."""

    def __init__(self, device_uuid, vm_uuid, pci_address,
                 utilization=None, memory_utilization=None):
        self.device_uuid = device_uuid
        self.vm_uuid = vm_uuid
        self.pci_address = pci_address
        self.utilization = utilization
        self.memory_utilization = memory_utilization


# =============================================================================
# Abstract Base Class (Python 2/3 Compatible)
# =============================================================================

class GPUBase(object):
    """
    Abstract base class for GPU vendor implementations.
    """
    __metaclass__ = abc.ABCMeta

    # ==========================================================================
    # Class Attributes - Must be overridden by subclasses
    # ==========================================================================

    VENDOR_NAME = ""                   # e.g., "NVIDIA", "AMD", "Huawei"
    VENDOR_ENUM_NAME = None            # Corresponding VendorEnum value
    VENDOR_IDS = set()                 # PCI vendor IDs, e.g., {"10de"}
    PCI_NAME_KEYWORDS = set()          # Keywords in lspci vendor name
    CLI_TOOL = ""                      # e.g., "nvidia-smi", "rocm-smi"
    CLI_TOOL_PATH = None               # Optional: full path to tool

    # Device type configuration
    DEVICE_TYPES = {"3D controller"}   # Default device types
    IS_GPU_VENDOR = True               # Is this a GPU vendor

    # ==========================================================================
    # Tool Availability Check
    # ==========================================================================

    @classmethod
    def is_available(cls):
        """
        Check if the vendor's CLI tool is available.
        """
        if not cls.CLI_TOOL:
            return False
        r, _, _ = bash_roe("which %s" % cls.CLI_TOOL)
        return r == 0

    @classmethod
    def get_tool_path(cls):
        """Get the full path to the CLI tool"""
        if cls.CLI_TOOL_PATH:
            return cls.CLI_TOOL_PATH
        if not cls.CLI_TOOL:
            return None
        r, o, _ = bash_roe("which %s" % cls.CLI_TOOL)
        return o.strip() if r == 0 else None

    # ==========================================================================
    # Device Identification
    # ==========================================================================

    @classmethod
    def matches_vendor_id(cls, vendor_id):
        """Check if vendor_id matches this vendor"""
        return vendor_id.lower() in [v.lower() for v in cls.VENDOR_IDS]

    @classmethod
    def matches_pci_name(cls, pci_name):
        """Check if PCI device name contains vendor keywords"""
        pci_name_lower = pci_name.lower()
        return any(
            kw.lower() in pci_name_lower for kw in cls.PCI_NAME_KEYWORDS)

    @classmethod
    def simplify_vendor_name(cls, pci_name, vendor_id):
        """
        Return simplified vendor name if this vendor matches.
        """
        if cls.matches_vendor_id(vendor_id) or cls.matches_pci_name(pci_name):
            return cls.VENDOR_NAME
        return None

    # ==========================================================================
    # Basic Information Collection
    # ==========================================================================

    @classmethod
    @abc.abstractmethod
    def get_basic_info_cmd(cls, is_windows=False):
        """
        Return the command to get basic GPU information.
        """
        pass

    @classmethod
    def get_basic_info(cls):
        """
        Collect and parse basic GPU information.
        """
        if not cls.is_available():
            return []

        cmd = cls.get_basic_info_cmd()
        if not cmd:
            return []

        r, o, e = bash_roe(cmd)
        if r != 0:
            logger.warn(
                "Failed to get basic info for %s: %s" %
                (cls.VENDOR_NAME, e))
            return []

        return cls.parse_basic_info(o)

    @classmethod
    @abc.abstractmethod
    def parse_basic_info(cls, output):
        """
        Parse command output to GPUInfo list.
        """
        pass

    # ==========================================================================
    # Prometheus Metrics Collection
    # ==========================================================================

    @classmethod
    @abc.abstractmethod
    def get_metric_cmd(cls, is_windows=False):
        """
        Return the command to get GPU metrics for Prometheus.

        The command should output parseable format containing:
        - PCI Address
        - GPU Utilization
        - Memory Utilization
        - Temperature
        - Power Draw
        - Serial Number

        Args:
            is_windows: True if running in Windows guest

        Returns:
            Command string to execute
        """
        pass

    @classmethod
    @abc.abstractmethod
    def parse_metrics(cls, output):
        """
        Parse the output of get_metric_cmd() into GPUMetrics objects.

        Args:
            output: Raw command output string

        Returns:
            List of GPUMetrics objects
        """
        pass

    @classmethod
    def collect_metrics(cls):
        """
        Collect GPU metrics for Prometheus.

        Returns:
            List of GPUMetrics objects, empty list if collection fails
        """
        if not cls.is_available():
            return []

        cmd = cls.get_metric_cmd()
        r, o, e = bash_roe(cmd)
        if r != 0:
            logger.warn(
                "Failed to collect metrics for %s: %s" %
                (cls.VENDOR_NAME, e))
            return []

        try:
            return cls.parse_metrics(o)
        except Exception as ex:
            logger.error(
                "Failed to parse metrics for %s: %s" %
                (cls.VENDOR_NAME, str(ex)))
            return []

    @classmethod
    def collect_vgpu_metrics(cls):
        """
        Collect vGPU/mdev metrics for Prometheus.

        Override if the vendor supports vGPU/mdev.
        Default implementation returns empty list.

        Returns:
            List of VGPUMetrics objects
        """
        return []

    @classmethod
    def get_custom_prometheus_metrics(cls):
        """
        Return vendor-specific custom Prometheus metrics definitions.

        Override to add vendor-specific metrics beyond the standard ones.

        Returns:
            Dict of metric_name -> (help_text, metric_type, label_names)

        Example:
            return {
                "host_gpu_ddr_capacity": ("GPU DDR Capacity", "gauge", ["pci_device_address", "gpu_serial"]),
            }
        """
        return {}

    # ==========================================================================
    # Pre-Detach Hooks
    # ==========================================================================

    @classmethod
    def pre_detach_from_vm(cls, domain, vm_uuid):
        """
        Hook called before detaching GPU from VM.

        Override if vendor requires special handling before detach.
        For example, NVIDIA needs to stop nvidia-persistenced.

        Args:
            domain: libvirt domain object
            vm_uuid: VM UUID

        Returns:
            Tuple of (return_code, output_message)
        """
        return 0, None

    @classmethod
    def pre_detach_from_host(cls):
        """
        Hook called before detaching GPU from host.

        Override if vendor requires special handling before detach.

        Returns:
            Tuple of (return_code, output_message)
        """
        return 0, None

    # ==========================================================================
    # Device In-Use Check Hook
    # ==========================================================================

    @classmethod
    def check_device_in_use(cls, pci_address):
        """
        Check if a PCI device is actively in use and cannot be safely unbound.

        Override in vendor subclass to implement vendor-specific detection
        (e.g., NVIDIA checks /dev/nvidia* file descriptors via fuser).

        Args:
            pci_address: Normalized PCI address (e.g., "0000:34:00.0").

        Raises:
            PciError: When the device is in use and unbinding would be unsafe.
        """
        pass

    # ==========================================================================
    # Post-Processing Hooks
    # ==========================================================================

    @classmethod
    def post_process_pci_device(cls, pci_device_to):
        """
        Post-process PCI device info after collection.

        Override to modify the PCI device object after basic collection.
        For example, Enflame sets virtStatus to UNVIRTUALIZABLE.

        Args:
            pci_device_to: The PCI device transfer object
        """
        pass

    # ==========================================================================
    # Virtualization Capabilities Detection
    # ==========================================================================

    @staticmethod
    def set_capability_virt_metadata(
            capability_info,
            virt_status,
            virt_state,
            virt_mode='',
            virt_capabilities=None):
        capability_info['virtStatus'] = virt_status
        capability_info['virtState'] = virt_state
        capability_info['virtMode'] = virt_mode or ''
        capability_info['virtCapabilities'] = list(virt_capabilities or [])

    @classmethod
    def detect_vfio_mdev_capability(cls, pci_device_to):
        """
        Detect if the GPU device supports VFIO mdev (mediated device) virtualization.

        Override to implement vendor-specific vfio_mdev detection logic.
        This method is called by the GPU processor to detect capabilities.

        Args:
            pci_device_to: PciDeviceTO object representing the GPU device

        Returns:
            tuple: (bool, dict) - (is_supported, capability_info)
                is_supported: True if vfio_mdev is supported
                capability_info: dict with additional info (e.g., {'virtStatus': 'VFIO_MDEV_VIRTUALIZABLE', 'mdevSpecifications': [...]})
        """
        return False, {}

    @classmethod
    def detect_sriov_capability(cls, pci_device_to, gpu_info_map=None):
        """
        Detect if the GPU device supports SR-IOV (Single Root I/O Virtualization).

        Override to implement vendor-specific sriov detection logic.
        This method is called by the GPU processor to detect capabilities.

        Args:
            pci_device_to: PciDeviceTO object representing the GPU device
            gpu_info_map: Optional pre-collected GPU info map for efficient batch processing

        Returns:
            tuple: (bool, dict) - (is_supported, capability_info)
                is_supported: True if sriov is supported
                capability_info: dict with additional info (e.g., {'virtStatus': 'SRIOV_VIRTUALIZABLE', 'maxPartNum': '...'})
        """
        return False, {}

    @classmethod
    def detect_tensorfusion_capability(cls, pci_device_to):
        """
        Detect if the GPU device supports TensorFusion virtualization.

        Override to implement vendor-specific TensorFusion detection logic.
        This method is called by the GPU processor to detect capabilities (lowest priority).

        Args:
            pci_device_to: PciDeviceTO object representing the GPU device

        Returns:
            tuple: (bool, dict) - (is_supported, capability_info)
                is_supported: True if TensorFusion is supported
                capability_info: dict with additional info (e.g., {'virtStatus': 'TENSORFUSION_VIRTUALIZABLE'})
        """
        return False, {}

    # ==========================================================================
    # PCI-only fallback (no SMI): candidates to add to gpu_info_map
    # ==========================================================================

    @classmethod
    def get_pci_only_candidates(cls, device_ids, device_names):
        """
        When SMI is not available, return PCI devices that should still be
        treated as this vendor's GPU/NPU (e.g. by vendor_id + class + device name).

        Override in vendor (e.g. Huawei) to implement vendor-specific rules.
        Called by gpu.get_all_gpu_infos_by_pci() supplement step.

        Args:
            device_ids: dict slot -> {Vendor, Class, Device, ...} from lspci -Dmmnv
            device_names: dict slot -> {Vendor, Class, Device, ...} from lspci -Dmmv

        Returns:
            list of (normalized_pci_address, info_dict). info_dict at least
            {"isDriverLoaded": False}. Only function 0 slots should be included.
        """
        return []

    # ==========================================================================
    # Addon Info Enrichment (productName, opaque, etc.)
    # ==========================================================================

    @classmethod
    def enrich_addon_info(cls, gpu_info_map, pci_addresses):
        """
        Enrich gpu_info_map with vendor-specific additional fields for the given PCI addresses.

        Override to add productName, opaque (e.g. aiosRankTable), or other vendor-specific
        fields into gpu_info_map[pci_addr] for each pci_addr in pci_addresses.

        Args:
            gpu_info_map: dict mapping normalized PCI address -> GPU info dict (mutated in place)
            pci_addresses: list of normalized PCI addresses that belong to this vendor
        """
        pass

    @classmethod
    def enrich_pci_device_dependencies(cls, pci_devices, gpu_info_map):
        """Enrich PCI dependencies using vendor-specific device topology."""
        pass

    # ==========================================================================
    # Device Type Validation
    # ==========================================================================

    @classmethod
    def is_valid_device(cls, device_name, device_type):
        """
        Validate if a PCI device should be recognized as GPU.

        Override for custom validation logic.
        Default checks against DEVICE_TYPES.

        Args:
            device_name: Device name from lspci
            device_type: Device type (e.g., "3D controller")

        Returns:
            True if device should be recognized as GPU
        """
        return True

    @classmethod
    def refine_gpu_type(cls, pci_device_to, raw_type, pci_device_mapper):
        """
        Optionally refine GPU type for this vendor.

        Override in vendor plugin to return a ZStack GPU type constant
        (e.g. GPU_TYPE_VIDEO_CONTROLLER) when this vendor has a specific
        mapping; return None to fall back to central type refinement table.

        Args:
            pci_device_to: PciDeviceTO object (vendor, device, etc.)
            raw_type: Current pci_device_to.type (lspci Class, possibly localized)
            pci_device_mapper: dict mapping PCI class names for i18n

        Returns:
            str or None: GPU type constant (e.g. GPU_TYPE_3D_CONTROLLER),
            or None to use central table
        """
        return None

    # ==========================================================================
    # VM Guest Tool Support
    # ==========================================================================

    @classmethod
    def get_vm_gpu_info_cmd(cls, is_windows=False):
        """
        Get command to retrieve GPU info inside VM via guest agent.

        Default implementation returns basic_info_cmd with Windows escaping.
        Override if different command is needed inside VM.
        """
        return cls.get_basic_info_cmd(is_windows)

    @classmethod
    def parse_vm_gpu_info(cls, output):
        """
        Parse GPU info output from inside VM.

        Default implementation uses parse_basic_info.
        Override if different parsing is needed.
        """
        return cls.parse_basic_info(output)

    # ==========================================================================
    # Utility Methods
    # ==========================================================================

    @staticmethod
    def normalize_pci_address(pci_address):
        """
        Normalize PCI address to standard format.

        Converts "00000000:3B:00.0" to "0000:3B:00.0"
        """
        from zstacklib.utils.pci import normalize_pci_address
        return normalize_pci_address(pci_address)

    @staticmethod
    def parse_unit_value(value, target_unit=None):
        """
        Parse a value with unit (e.g., "15360 MiB", "70.00 W").

        Args:
            value: Value string with unit
            target_unit: Expected unit suffix (optional). If provided, validates
                        that the parsed unit matches the target unit.

        Returns:
            Numeric value as float, or None if parsing fails or unit mismatch
        """
        if not value:
            return None
        value = value.strip()

        # Remove unit suffix
        match = re.match(r'^([\d.]+)\s*(\S*)$', value)
        if not match:
            return None

        parsed_value = match.group(1)
        parsed_unit = match.group(2).strip()

        # If target_unit is provided, validate unit match
        if target_unit:
            # Normalize units for comparison (case-insensitive, handle
            # variations)
            target_unit_norm = target_unit.strip().lower()
            parsed_unit_norm = parsed_unit.lower()

            # Handle common unit variations
            unit_aliases = {
                'mib': ['mib', 'mb', 'm'],
                'w': ['w', 'watts', 'watt'],
                'c': ['c', 'celsius', '°c'],
                '%': ['%', 'percent', 'pct'],
            }

            # Check if units match (exact match or alias match)
            units_match = False
            if parsed_unit_norm == target_unit_norm:
                units_match = True
            else:
                # Check aliases
                for canonical, aliases in unit_aliases.items():
                    if target_unit_norm in aliases and parsed_unit_norm in aliases:
                        units_match = True
                        break

            if not units_match:
                return None

        try:
            return float(parsed_value)
        except ValueError:
            return None


# =============================================================================
# Registry System
# =============================================================================

_vendor_registry = {}


def register_gpu_vendor(cls):
    """Decorator to register a GPU vendor plugin"""
    if cls.VENDOR_NAME:
        _vendor_registry[cls.VENDOR_NAME] = cls
    return cls


def get_gpu_vendor(vendor_name):
    """Get vendor class by name"""
    return _vendor_registry.get(vendor_name)


def get_all_gpu_vendors():
    """Get all registered vendor classes"""
    return _vendor_registry.values()


def get_vendor_by_id(vendor_id):
    """Find vendor class by PCI vendor ID"""
    vendor_id = vendor_id.lower()
    for vendor_class in _vendor_registry.values():
        if vendor_class.matches_vendor_id(vendor_id):
            return vendor_class
    return None


def get_vendor_by_pci_name(pci_name):
    """Find vendor class by PCI device name"""
    for vendor_class in _vendor_registry.values():
        if vendor_class.matches_pci_name(pci_name):
            return vendor_class
    return None


def get_gpu_vendor_names():
    """Get list of vendor names for devices that should be recognized as GPU"""
    return [
        vendor_class.VENDOR_NAME
        for vendor_class in _vendor_registry.values()
        if vendor_class.IS_GPU_VENDOR
    ]


def identify_vendor(pci_name, vendor_id):
    """Identify vendor name from PCI information"""
    for vendor_class in _vendor_registry.values():
        result = vendor_class.simplify_vendor_name(pci_name, vendor_id)
        if result:
            return result
    return None


def get_vendor_enum_mapping():
    """Get mapping from VendorEnum names to plugin vendor names"""
    mapping = {}
    for vendor_class in _vendor_registry.values():
        enum_name = vendor_class.VENDOR_ENUM_NAME or vendor_class.VENDOR_NAME
        if enum_name:
            mapping[enum_name] = vendor_class.VENDOR_NAME
    return mapping

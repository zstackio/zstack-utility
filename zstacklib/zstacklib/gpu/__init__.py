# -*- coding: utf-8 -*-
"""GPU vendor plugins and runtime inventory exports."""

from zstacklib.gpu_runtime_inventory import (
    RuntimeInventoryError,
    RuntimeGpuIdentity,
    RuntimeGpuDriver,
    RuntimeDeviceNode,
    RuntimeGpuDevice,
    build_runtime_inventory,
    build_unsupported_runtime_inventory,
    get_nvidia_runtime_inventory_cmd,
    get_nvidia_topology_cmd,
    parse_nvidia_runtime_query_output,
    parse_nvidia_topology_output,
    build_nvidia_runtime_inventory,
    runtime_inventory_to_legacy_pci_devices,
)


__all__ = [
    'RuntimeInventoryError',
    'RuntimeGpuIdentity',
    'RuntimeGpuDriver',
    'RuntimeDeviceNode',
    'RuntimeGpuDevice',
    'build_runtime_inventory',
    'build_unsupported_runtime_inventory',
    'get_nvidia_runtime_inventory_cmd',
    'get_nvidia_topology_cmd',
    'parse_nvidia_runtime_query_output',
    'parse_nvidia_topology_output',
    'build_nvidia_runtime_inventory',
    'runtime_inventory_to_legacy_pci_devices',
]


from zstacklib.gpu.base import (
    VendorEnum,
    GPUBase,
    GPUInfo,
    GPUMetrics,
    VGPUMetrics,
    register_gpu_vendor,
    get_gpu_vendor,
    get_all_gpu_vendors,
    get_gpu_vendor_names,
    get_vendor_enum_mapping,
    get_vendor_by_id,
    get_vendor_by_pci_name,
    identify_vendor,
)

from zstacklib.gpu.vendors import nvidia
from zstacklib.gpu.vendors import amd
from zstacklib.gpu.vendors import huawei
from zstacklib.gpu.vendors import tianshu
from zstacklib.gpu.vendors import enflame
from zstacklib.gpu.vendors import vastai
from zstacklib.gpu.vendors import alibaba
from zstacklib.gpu.vendors import haiguang
from zstacklib.gpu.vendors import kunlunxin

def enrich_gpu_info_map(gpu_info_map):
    if not gpu_info_map:
        return
    from zstacklib.utils.pci import normalize_pci_address
    from zstacklib.utils import log
    logger = log.get_logger(__name__)

    pci_to_vendor = {}
    for pci, info in gpu_info_map.items():
        if isinstance(info, dict) and info.get('_vendor'):
            pci_to_vendor[pci] = info['_vendor']

    if len(pci_to_vendor) < len(gpu_info_map):
        for vendor_class in get_all_gpu_vendors():
            if not vendor_class.is_available():
                continue
            try:
                for gpu_info in vendor_class.get_basic_info():
                    if gpu_info.pci_address:
                        normalized = normalize_pci_address(
                            gpu_info.pci_address)
                        if normalized and normalized in gpu_info_map \
                                and normalized not in pci_to_vendor:
                            pci_to_vendor[normalized] = \
                                vendor_class.VENDOR_NAME
            except Exception as err:
                logger.debug(
                    'enrich_gpu_info_map: get_basic_info from %s: %s' %
                    (vendor_class.VENDOR_NAME, str(err)))

    vendor_to_pcis = {}
    for pci, vendor in pci_to_vendor.items():
        vendor_to_pcis.setdefault(vendor, []).append(pci)

    for vendor_name, pcis in vendor_to_pcis.items():
        vendor_class = get_gpu_vendor(vendor_name)
        if vendor_class and hasattr(vendor_class, 'enrich_addon_info'):
            try:
                vendor_class.enrich_addon_info(gpu_info_map, pcis)
            except Exception as err:
                logger.debug(
                    'enrich_gpu_info_map: enrich_addon_info for %s: %s' %
                    (vendor_name, str(err)))

__all__.extend([
    'VendorEnum',
    'GPUBase',
    'GPUInfo',
    'GPUMetrics',
    'VGPUMetrics',
    'register_gpu_vendor',
    'get_gpu_vendor',
    'get_all_gpu_vendors',
    'get_gpu_vendor_names',
    'get_vendor_enum_mapping',
    'get_vendor_by_id',
    'get_vendor_by_pci_name',
    'identify_vendor',
    'enrich_gpu_info_map',
])

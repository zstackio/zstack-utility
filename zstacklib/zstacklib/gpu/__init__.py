# -*- coding: utf-8 -*-
"""
GPU Vendor Plugin System

A pure data layer providing plugin-based architecture for GPU vendor support.
This module provides:
  - Abstract base class for GPU vendors
  - Data models (GPUInfo, GPUMetrics, VGPUMetrics)
  - Plugin registration and discovery mechanism
  - Vendor identification utilities

Usage in kvmagent (host_plugin, prometheus, etc.):
  from zstacklib.gpu import get_all_gpu_vendors, get_gpu_vendor

  # Get all registered GPU vendors
  for vendor_class in get_all_gpu_vendors():
      if vendor_class.is_available():
          metrics = vendor_class.collect_metrics()

To add a new vendor:
  1. Copy vendor_template.py to vendor_<name>.py
  2. Implement all abstract methods
  3. Set VENDOR_NAME, VENDOR_IDS, etc.
  4. Uncomment @register_gpu_vendor decorator
  5. Import vendor file below to auto-register

Architecture:
                    ┌─────────────────────┐
                    │   GPUVendorBase     │ (Abstract)
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
    ┌────▼────┐          ┌─────▼─────┐         ┌─────▼─────┐
    │ NVIDIA  │          │   AMD     │         │ NewVendor │
    └─────────┘          └───────────┘         └───────────┘
"""

# =============================================================================
# Core exports: Base classes, data models, and registry
# =============================================================================
from zstacklib.gpu.base import (
    # Vendor enumeration
    VendorEnum,

    # Abstract base class
    GPUBase,

    # Data models
    GPUInfo,
    GPUMetrics,
    VGPUMetrics,

    # Registration decorator
    register_gpu_vendor,

    # Registry query functions
    get_gpu_vendor,
    get_all_gpu_vendors,
    get_gpu_vendor_names,
    get_vendor_enum_mapping,

    # Vendor identification (core utilities)
    get_vendor_by_id,
    get_vendor_by_pci_name,
    identify_vendor,
)

# =============================================================================
# Auto-register vendor implementations
# Import each vendor file to trigger @register_gpu_vendor decorator
# =============================================================================

# NVIDIA - Reference implementation (CSV format parsing)
from zstacklib.gpu.vendors import nvidia

# AMD - JSON output format example
from zstacklib.gpu.vendors import amd

# Huawei - Multi-device enumeration example
from zstacklib.gpu.vendors import huawei

# Tianshu
from zstacklib.gpu.vendors import tianshu

# Enflame
from zstacklib.gpu.vendors import enflame

# Vastai
from zstacklib.gpu.vendors import vastai

# Alibaba
from zstacklib.gpu.vendors import alibaba

# Haiguang
from zstacklib.gpu.vendors import haiguang

# Kunlunxin
from zstacklib.gpu.vendors import kunlunxin


# =============================================================================
# Batch addon enrichment - common logic using vendor hooks
# =============================================================================

def enrich_gpu_info_map(gpu_info_map):
    """
    Enrich gpu_info_map with vendor-specific additional fields (productName, opaque, etc.).

    Builds pci -> vendor mapping from get_basic_info, then calls each vendor's
    enrich_addon_info(gpu_info_map, pci_list) for its PCI addresses.

    Args:
        gpu_info_map: dict from get_all_gpu_infos_by_pci(); mutated in place
    """
    if not gpu_info_map:
        return
    from zstacklib.utils.pci import normalize_pci_address
    from zstacklib.utils import log
    _log = log.get_logger(__name__)

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
                        norm = normalize_pci_address(gpu_info.pci_address)
                        if norm and norm in gpu_info_map and norm not in pci_to_vendor:
                            pci_to_vendor[norm] = vendor_class.VENDOR_NAME
            except Exception as e:
                _log.debug("enrich_gpu_info_map: get_basic_info from %s: %s" %
                           (vendor_class.VENDOR_NAME, str(e)))

    vendor_to_pcis = {}
    for pci, vendor in pci_to_vendor.items():
        vendor_to_pcis.setdefault(vendor, []).append(pci)

    for vendor_name, pcis in vendor_to_pcis.items():
        vendor_class = get_gpu_vendor(vendor_name)
        if vendor_class and hasattr(vendor_class, 'enrich_addon_info'):
            try:
                vendor_class.enrich_addon_info(gpu_info_map, pcis)
            except Exception as e:
                _log.debug("enrich_gpu_info_map: enrich_addon_info for %s: %s" %
                           (vendor_name, str(e)))


__all__ = [
    # Vendor enumeration
    'VendorEnum',

    # Abstract base class
    'GPUBase',

    # Data models
    'GPUInfo',
    'GPUMetrics',
    'VGPUMetrics',

    # Registration
    'register_gpu_vendor',

    # Registry query
    'get_gpu_vendor',
    'get_all_gpu_vendors',
    'get_gpu_vendor_names',
    'get_vendor_enum_mapping',

    # Vendor identification
    'get_vendor_by_id',
    'get_vendor_by_pci_name',
    'identify_vendor',

    # Batch addon enrichment
    'enrich_gpu_info_map',
]

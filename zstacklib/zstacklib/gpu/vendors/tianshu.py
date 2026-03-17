# -*- coding: utf-8 -*-
from zstacklib.gpu.base import GPUBase, GPUInfo, GPUMetrics, register_gpu_vendor
from zstacklib.utils.bash import bash_roe
from zstacklib.utils import shell

@register_gpu_vendor
class Tianshu(GPUBase):
    VENDOR_NAME = "Tianshu"
    VENDOR_ENUM_NAME = "TianShu"
    VENDOR_IDS = {"1e3e"}
    PCI_NAME_KEYWORDS = {"1e3e"}
    CLI_TOOL = "ixsmi"
    DEVICE_TYPES = {"3D controller", "VGA compatible controller", "Processing accelerators"}

    @classmethod
    def get_pci_only_candidates(cls, device_ids, device_names):
        """
        When ixsmi is not available, identify Tianshu GPU by PCI: vendor 1e3e,
        class 3D controller, VGA compatible controller, or Processing accelerators.
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

    @classmethod
    def is_tianshu_v1(cls):
        return "ixsmi -a | grep 'Memory Total'"

    @classmethod
    def get_basic_info_cmd(cls, is_windows=False):
        # Tianshu has two versions of ixsmi
        if shell.run(cls.is_tianshu_v1()) == 0:
            cmd = "ixsmi -a --format=csv,noheader --query-gpu=bus_id,memory.total,power.limit,serial"
        else:
            cmd = "ixsmi --query-gpu=bus_id,memory.total,power.limit,serial --format=csv,noheader"
        
        if is_windows:
            cmd = cmd.replace(" ", "|")
        return cmd

    @classmethod
    def parse_basic_info(cls, output):
        gpu_infos = []
        if not output:
            return gpu_infos
            
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) < 4:
                continue
            
            pci_address = cls.normalize_pci_address(parts[0].strip())
                
            gpu_infos.append(GPUInfo(
                pci_address=pci_address,
                memory=parts[1].strip(),
                power=parts[2].strip(),
                serial_number=parts[3].strip()
            ))
        return gpu_infos

    @classmethod
    def get_metric_cmd(cls, is_windows=False):
        """
        Get command to query GPU metrics for Tianshu GPUs.
        
        Tianshu has two versions of ixsmi:
        - v1: uses 'gpu.power.draw' and includes 'fan.speed'
        - v2: uses 'power.draw' and doesn't include 'fan.speed'
        
        Returns:
            Command string to get GPU metrics
        """
        if shell.run(cls.is_tianshu_v1()) == 0:
            cmd = "ixsmi --query-gpu=gpu.power.draw,temperature.gpu,utilization.gpu,utilization.memory,index,gpu_bus_id," \
                  "gpu_serial,fan.speed --format=csv,noheader,nounits"
        else:
            cmd = "ixsmi --query-gpu=power.draw,temperature.gpu,utilization.gpu,utilization.memory,index,gpu_bus_id," \
                  "gpu_serial --format=csv,noheader,nounits"
        
        if is_windows:
            cmd = cmd.replace(" ", "|")
        return cmd

    @classmethod
    def parse_metrics(cls, output):
        """
        Parse ixsmi metrics output.
        
        Output format (CSV, noheader, nounits):
        For v1: power.draw,temperature.gpu,utilization.gpu,utilization.memory,index,gpu_bus_id,gpu_serial,fan.speed
        For v2: power.draw,temperature.gpu,utilization.gpu,utilization.memory,index,gpu_bus_id,gpu_serial
        
        Returns:
            List of GPUMetrics objects
        """
        results = []
        if not output:
            return results
        
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            
            info = line.split(',')
            if len(info) < 7:
                continue
            
            # Parse fields according to the command output format
            # info[0] = power.draw
            # info[1] = temperature.gpu
            # info[2] = utilization.gpu
            # info[3] = utilization.memory
            # info[4] = index (not used)
            # info[5] = gpu_bus_id (pci_device_address)
            # info[6] = gpu_serial
            # info[7] = fan.speed (only for v1, if len(info) == 8)
            
            pci_device_address = info[5].strip().lower()
            gpu_serial = info[6].strip()
            
            # Normalize PCI address (remove 8-char domain prefix if present)
            pci_device_address = cls.normalize_pci_address(pci_device_address)
            
            # Parse numeric values
            power_draw = cls.parse_unit_value(info[0].strip())
            temperature = cls.parse_unit_value(info[1].strip())
            utilization = cls.parse_unit_value(info[2].strip())
            memory_utilization = cls.parse_unit_value(info[3].strip())
            fan_speed = None
            
            # v1 includes fan.speed as the 8th field
            if len(info) == 8:
                fan_speed = cls.parse_unit_value(info[7].strip())
            
            metrics = GPUMetrics(
                pci_address=pci_device_address,
                serial_number=gpu_serial,
                utilization=utilization,
                memory_utilization=memory_utilization,
                temperature=temperature,
                power_draw=power_draw,
                fan_speed=fan_speed
            )
            
            results.append(metrics)
        
        return results

    @classmethod
    def enrich_addon_info(cls, gpu_info_map, pci_addresses):
        """Add productName for Tianshu GPUs."""
        if not pci_addresses:
            return
        from zstacklib.utils.gpu import get_tianshu_gpu_product_name_cmd, get_tianshu_product_name
        r, o, e = bash_roe(get_tianshu_gpu_product_name_cmd())
        if r == 0 and o:
            product_name = get_tianshu_product_name(o)
            if product_name:
                for pci_addr in pci_addresses:
                    if pci_addr in gpu_info_map:
                        gpu_info_map[pci_addr]["productName"] = product_name

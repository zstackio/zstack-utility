from zstacklib.utils import pci
import threading
import re

from zstacklib.utils import thread
from zstacklib.utils.bash import *
from enum import Enum
import json

from zstacklib.gpu.base import (
    VendorEnum,
    PCI_CLASS_VGA,
    PCI_CLASS_DISPLAY,
    PCI_CLASS_PROCESSING_ACCEL,
    PCI_CLASS_COPROCESSOR,
    PCI_CLASS_COMMUNICATION,
    PCI_CLASS_3D,
    GPU_TYPE_VIDEO_CONTROLLER,
    GPU_TYPE_PROCESSING_ACCELERATORS,
    GPU_TYPE_CO_PROCESSOR,
    GPU_TYPE_COMMUNICATION_CONTROLLER,
    GPU_TYPE_3D_CONTROLLER,
)
from zstacklib.utils.qga import VmQga

logger = log.get_logger(__name__)


class VmGpuStatus(Enum):
    NOT_EXIST = "not_exist"
    CRITICAL_FAULT = "critical"
    NOMINAL = "nominal"


def set_pci_virt_metadata(
        pci_device_to,
        virt_status,
        virt_state,
        virt_mode=None,
        virt_capabilities=None):
    # Keep virtStatus populated for backward compatibility only. New
    # virtualization semantics are carried by virtState/virtMode/
    # virtCapabilities, and virtStatus is expected to be deprecated later.
    pci_device_to.virtStatus = virt_status or ""
    pci_device_to.virtState = virt_state or ""
    pci_device_to.virtMode = virt_mode or ""
    pci_device_to.virtCapabilities = list(virt_capabilities or [])


def apply_explicit_virt_metadata(pci_device_to, capability_info):
    if capability_info is None:
        return

    # Keep virtStatus populated for backward compatibility only. New
    # virtualization semantics are carried by virtState/virtMode/
    # virtCapabilities, and virtStatus is expected to be deprecated later.
    pci_device_to.virtStatus = capability_info.get('virtStatus', '') or ''
    pci_device_to.virtState = capability_info.get('virtState', '') or ''
    pci_device_to.virtMode = capability_info.get('virtMode', '') or ''
    pci_device_to.virtCapabilities = list(
        capability_info.get('virtCapabilities') or [])


def shut_persistenced_by_guesttool(domain):
    vm_uuid = domain.name()
    qga = VmQga(domain)
    if qga.state != VmQga.QGA_STATE_RUNNING:
        return 0, "skip shuting down nvidia-persistenced, qga is not running for vm {}".format(vm_uuid)

    cmd = get_shut_nvidia_persistence_cmd("mswindows" in qga.os)
    if qga.os == "mswindows":
        exitcode, ret_data = qga.guest_exec_powershell(cmd)
    else:
        exitcode, ret_data, _ = qga.guest_exec_bash(cmd)
    return exitcode, ret_data


def nvidia_pre_detach_from_vm(domain, vm_uuid):
    """NVIDIA specific pre-detach-from-VM hook"""
    if not domain or not domain.isActive():
        logger.info(
            "no need to shutdown nvidia-persistenced for vm %s, it is not running" % vm_uuid)
        return 0, None
    else:
        logger.info("start to shutdown nvidia-persistenced for vm %s" % vm_uuid)
        return shut_persistenced_by_guesttool(domain)


def nvidia_pre_detach_from_host():
    """NVIDIA specific pre-detach-from-host hook"""
    logger.info("start to shutdown nvidia-persistenced on host")
    r, o, _ = bash_roe(get_shut_nvidia_persistence_cmd())
    return r, o


_pre_detach_from_vm_hooks = {
    VendorEnum.NVIDIA: nvidia_pre_detach_from_vm
}

_pre_detach_from_host_hooks = {
    VendorEnum.NVIDIA: nvidia_pre_detach_from_host
}


def pre_detach_from_vm(domain, vm_uuid, vendor):
    """Execute pre-detach-from-VM hook for specific vendor"""
    if vendor in _pre_detach_from_vm_hooks:
        return _pre_detach_from_vm_hooks[vendor](domain, vm_uuid)
    logger.warn(
        "No hook registered for vendor: {0}, do nothing".format(vendor))
    return 0, None


# def pre_detach_from_host(vendor):
#     """Execute pre-detach-from-host hook for specific vendor"""
#     if vendor in _pre_detach_from_host_hooks:
#         return _pre_detach_from_host_hooks[vendor]()
#     logger.warn("No hook registered for vendor: {0}, do nothing".format(vendor))
#     return 0, None


def extract_and_clean_json(smi_output):
    start_idx = smi_output.find('{')
    end_idx = smi_output.rfind('}')

    if start_idx == -1 or end_idx == -1:
        logger.info("No JSON brackets found in SMI output")
        return None

    if start_idx >= end_idx:
        logger.info("Invalid JSON bracket order in SMI output")
        return None

    json_str = (
        smi_output[start_idx:end_idx + 1]
        .strip()
        .replace(', ,', ',')
        .replace(',,', ',')
        .replace(', }', '}')
        .replace(', ]', ']')
    )
    return json_str


def parse_nvidia_gpu_output(output):
    gpuinfos = []
    for part in output.split('\n'):
        if len(part.strip()) == 0:
            continue
        infos = part.split(',')
        gpuinfo = {}
        pci_device_address = infos[0].strip().lower()
        if len(pci_device_address.split(':')[0]) == 8:
            pci_device_address = pci_device_address[4:].lower()
        gpuinfo["pciAddress"] = pci_device_address
        gpuinfo["memory"] = infos[1].strip()
        gpuinfo["power"] = infos[2].strip()
        gpuinfo["serialNumber"] = infos[3].strip()
        gpuinfos.append(gpuinfo)
    return gpuinfos


def parse_amd_gpu_output(output):
    gpuinfos = []
    try:
        gpu_info_json = json.loads(extract_and_clean_json(output))
        if gpu_info_json is None:
            return gpuinfos

        # Support rocm-smi card_list format: {"card_list": [{"pci_bus": "...", "memory": "..."}]}
        card_list = gpu_info_json.get("card_list")
        if isinstance(card_list, list):
            for card_data in card_list:
                if not isinstance(card_data, dict):
                    continue
                gpuinfo = {}
                pci_bus = card_data.get("pci_bus") or card_data.get("PCI Bus")
                if not pci_bus:
                    continue
                pci_device_address = pci_bus.lower()
                if len(pci_device_address.split(':')[0]) == 8:
                    pci_device_address = pci_device_address[4:].lower()
                gpuinfo["pciAddress"] = pci_device_address
                gpuinfo["memory"] = card_data.get("memory") or card_data.get('VRAM Total Memory (B)')
                gpuinfo["power"] = card_data.get("power") or card_data.get(
                    'Average Graphics Package Power (W)',
                    card_data.get('Current Socket Graphics Package Power (W)', None))
                gpuinfo["serialNumber"] = card_data.get("serialNumber") or card_data.get('Serial Number')
                gpuinfos.append(gpuinfo)
            return gpuinfos

        # Legacy format: top-level dict of card_name -> card_data
        for card_name, card_data in list(gpu_info_json.items()):
            if not isinstance(card_data, dict):
                continue
            gpuinfo = {}
            pci_device_address = card_data.get('PCI Bus').lower()
            if len(pci_device_address.split(':')[0]) == 8:
                pci_device_address = pci_device_address[4:].lower()

            gpuinfo["pciAddress"] = pci_device_address
            gpuinfo["memory"] = card_data.get('VRAM Total Memory (B)')
            gpuinfo["power"] = card_data.get('Average Graphics Package Power (W)',
                                             card_data.get('Current Socket Graphics Package Power (W)', None))
            gpuinfo["serialNumber"] = card_data.get('Serial Number')
            gpuinfos.append(gpuinfo)
    except Exception as e:
        logger.error("amd query gpu is error, %s " % e)

    return gpuinfos


def parse_hy_gpu_output(output):
    gpuinfos = []
    try:
        gpu_info_json = json.loads(extract_and_clean_json(output))
        if gpu_info_json is None:
            return gpuinfos

        for card_name, card_data in list(gpu_info_json.items()):
            gpuinfo = {}
            pci_device_address = card_data['PCI Bus'].lower()
            if len(pci_device_address.split(':')[0]) == 8:
                pci_device_address = pci_device_address[4:].lower()

            gpuinfo["pciAddress"] = pci_device_address
            gpuinfo["memory"] = card_data['Available memory size (MiB)'] + \
                " MiB"
            gpuinfo["power"] = card_data['Max Graphics Package Power (W)']
            gpuinfo["serialNumber"] = card_data['Serial Number']
            gpuinfos.append(gpuinfo)
    except Exception as e:
        logger.error("haiguang query gpu is error, %s " % e)

    return gpuinfos


def get_huawei_npu_id(npu_id_output):
    npu_ids = []
    for line in npu_id_output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "NPU ID" in line:
            npu_id = line.split(":")[1].strip()
            if not npu_id.isdigit():
                logger.debug("Ignore invalid Huawei NPU ID: %s" % npu_id)
                continue
            npu_ids.append(npu_id)
    return npu_ids


def parse_huawei_gpu_output_by_npu_id(output):
    gpuinfos = []
    gpuinfo = {}
    total_memory = 0
    total_ddr_memory = 0
    found_total_memory = False
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Serial Number" in line:
            gpuinfo["serialNumber"] = line.split(":")[1].strip()
        elif "PCIe Bus Info" in line:
            gpuinfo["pciAddress"] = line.partition(": ")[-1].strip().lower()
        elif line.startswith("Total DDR Capacity(MB)"):
            memory_value = int(line.split(":")[1].strip().split()[0])
            total_ddr_memory += memory_value
            found_total_memory = True
        elif (line.startswith("DDR Capacity(MB)") or line.startswith("HBM Capacity")) and not found_total_memory:
            memory_value = int(line.split(":")[1].strip().split()[0])
            total_memory += memory_value
        elif "Power Dissipation" in line or "Real-time Power(W)" in line:
            gpuinfo["power"] = line.split(":")[1].strip()

    total_memory = total_ddr_memory if found_total_memory else total_memory

    if total_memory > 0:
        gpuinfo["memory"] = "%s MB" % total_memory

    gpuinfos.append(gpuinfo)
    return gpuinfos


def get_huawei_product_type(output):
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Product Type" in line:
            return line.split(":")[1].strip()
    return None


def parse_tianshu_gpu_output(output):
    gpuinfos = []
    for part in output.split('\n'):
        if len(part.strip()) == 0:
            continue
        infos = part.split(',')
        gpuinfo = {}
        pci_device_address = infos[0].strip()
        if len(pci_device_address.split(':')[0]) == 8:
            pci_device_address = pci_device_address[4:].lower()

        gpuinfo["pciAddress"] = pci_device_address
        gpuinfo["memory"] = infos[1].strip()
        gpuinfo["power"] = infos[2].strip()
        gpuinfo["serialNumber"] = infos[3].strip()
        gpuinfos.append(gpuinfo)

    return gpuinfos


def parse_enflame_gpu_output(output):
    """
    ...
    old version driver:

    DEV ID 7
        Driver Info
            Ver                     : 1.2.4.12
        Device Info
            Dev Name                : S60
            Dev UUID                : TR1V57100501
            Dev SN                  : C0AAD40510049
            Dev PN                  : EFB-0088000-00
            Dev MFD                 : 2024-10-13
            Health                  : True
        PCIe Info
            Vendor ID               : 1e36
            Device ID               : c035
            Domain                  : 0000
            Bus                     : b1
            Dev                     : 00
            Func                    : 0
            Link Info
            Max Link Speed          : Gen5
            Max Link Width          : X16
            Cur Link Speed          : Gen5
            Cur Link Width          : X16
            Tx Throughput           : 0 MiB/s
            Rx Throughput           : 0 MiB/s
        Clock Info
            Mem CLK                 : 7000 MHz
        Power Info
            Power Capa              : 300 W
            Cur Power               : 102 W
            Dpm Level               : Sleep
        Device Mem Info
            Mem Size                : 42976 MiB
            Mem Usage               : 1129 MiB
            Mem Ecc                 : enable
        Temperature Info
            GCU Temp                : 41 C
        Voltage Info
            VDD GCU                 : 0.702 V
            VDD SOC                 : 0.743 V
            VDD MEMQC               : 1.349 V
        Device Usage Info
            GCU Usage               : 0.0 %
        ECC Mode
            Current                 : Enable
            Pending                 : Enable
        RMA Info
            Flags                   : False
            DBE                     : 0
        Power Cable
            Status                  : Normal
        VPU Info
            Encoder Usage           : 0 %
            Decoder Usage           : 0 %

    new version driver:
        DEV ID 0
        Driver Info
            Ver                     : 1.4.3.4
        Device Info
            Dev Name                : S60
            Dev UUID                : TPUH74190604
            Dev SN                  : C0AA640520685
            Dev PN                  : EFB-0088000-00
            Dev MFD                 : 2024-10-6
            Health                  : True
        PCIe Info
            Vendor ID               : 1e36
            Device ID               : c035
            Domain                  : 0000
            Bus                     : 00
            Dev                     : 0c
            Func                    : 0
            Link Info
            Max Link Speed          : Gen5
            Max Link Width          : X16
            Cur Link Speed          : Gen5
            Cur Link Width          : X16
            Tx Throughput           : 0 MiB/s
            Rx Throughput           : 0 MiB/s
        Clock Info
            Mem CLK                 : 7000 MHz
        Power Info
            Power Capa              : 300 W
            Cur Power               : 104 W
            Dpm Level               : Sleep
        Device Mem Info
            Total Size              : 42976 MiB
            Reserved Size           : 1129 MiB
            Used Size               : 0 MiB
            Free Size               : 41846 MiB
        Temperature Info
            GCU Temp                : 45 ('C Celsius sign, utf-8 char, not log here)
        Voltage Info
            VDD GCU                 : 0.7 V
            VDD SOC                 : 0.743 V
            VDD MEMQC               : 1.347 V
        Device Usage Info
            GCU Usage               : 0.0 %
        ECC Mode
            Current                 : Enable
            Pending                 : Enable
        RMA Info
            Flags                   : False
            Total DBE               : 0
                MC0 DBE             : 0
                MC1 DBE             : 0
                MC2 DBE             : 0
                MC3 DBE             : 0
                MC4 DBE             : 0
                MC5 DBE             : 0
                MC6 DBE             : 0
                MC7 DBE             : 0
                MC8 DBE             : 0
                MC9 DBE             : 0
                MC10 DBE            : 0
                MC11 DBE            : 0
        Power Cable
            Status                  : Normal
        VPU Info
            Encoder Usage           : 0 %
            Decoder Usage           : 0 %
        Error Records
            Total Error Count       : 0
            Reset Count             : 0
            Last Reset Date         : N/A
        Error Details
            User Triggered Reset    : 0
            Internal Error          : 0
            SIP Error               : 0
            Bus Error               : 0
            FW Error                : 0
            DTE Error               : 0
            DRAM HBM Error          : 0
            PCIE Error              : 0
            Unknown Error           : 0
    ...
    """
    gpu_infos = []

    for dev in output.split("DEV ID")[1:]:
        gpuinfo = {}
        domain = bus = dev_id = func = None

        for line in dev.strip().splitlines():
            line = line.strip()
            if ':' in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
            else:
                key = line
                value = ''

            if key == "Domain":
                domain = value.zfill(4)
            elif key == "Bus":
                bus = value.zfill(2)
            elif key == "Dev":
                dev_id = value.zfill(2)
            elif key == "Func":
                func = value
            elif key == "Mem Size" or key == "Total Size":
                gpuinfo["memory"] = value
            elif key == "Mem Usage" or key == "Used Size":
                gpuinfo["memoryUsage"] = value
            elif key == "Cur Power":
                gpuinfo["power"] = value
            elif key == "Power Capa":
                gpuinfo["powerCap"] = value
            elif key == "Dpm Level":
                gpuinfo["dpmLevel"] = value
            elif key == "GCU Temp":
                gpuinfo["temperature"] = value
            elif key == "GCU Usage":
                gpuinfo["gcuUsage"] = value
            elif key == "Dev SN":
                gpuinfo["serialNumber"] = value
            elif key == "Tx Throughput":
                gpuinfo["txThroughput"] = value
            elif key == "Rx Throughput":
                gpuinfo["rxThroughput"] = value

        if domain and bus and dev_id and func:
            gpuinfo["pciAddress"] = "{}:{}:{}.{}".format(
                domain, bus, dev_id, func)
            gpu_infos.append(gpuinfo)

    return gpu_infos


def get_tianshu_product_name(output):
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Product Name" in line:
            return line.split(":")[1].strip()
    return None


def get_nvidia_gpu_basic_info_cmd(iswindows=False):
    cmd = "nvidia-smi --query-gpu=gpu_bus_id,memory.total,power.limit,gpu_serial --format=csv,noheader"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_amd_gpu_basic_info_cmd(iswindows=False):
    cmd = "rocm-smi --showbus --showmeminfo vram --showpower --showserial --json"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_hy_gpu_basic_info_cmd(iswindows=False):
    cmd = "hy-smi --showserial --showmaxpower --showmemavailable --showbus --json"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def is_tianshu_v1(iswindows=False):
    cmd = "ixsmi --query-gpu=fan.speed --format=csv,noheader"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_tianshu_gpu_basic_info_cmd_v1(iswindows=False):
    cmd = "ixsmi --query-gpu=gpu_bus_id,memory.total,gpu.power.limit,gpu_serial --format=csv,noheader"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_tianshu_gpu_basic_info_cmd_v2(iswindows=False):
    cmd = "ixsmi --query-gpu=gpu_bus_id,memory.total,power.limit,gpu_serial --format=csv,noheader"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_tianshu_gpu_metric_info_cmd_v1(iswindows=False):
    cmd = "ixsmi --query-gpu=gpu.power.draw,temperature.gpu,utilization.gpu,utilization.memory,index,gpu_bus_id," \
          "gpu_serial,fan.speed  --format=csv,noheader,nounits"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_tianshu_gpu_metric_info_cmd_v2(iswindows=False):
    cmd = "ixsmi --query-gpu=power.draw,temperature.gpu,utilization.gpu,utilization.memory,index,gpu_bus_id," \
          "gpu_serial --format=csv,noheader,nounits"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_tianshu_gpu_product_name_cmd(iswindows=False):
    cmd = "ixsmi -q |grep 'Product Name'"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_huawei_gpu_npu_id_cmd():
    return "npu-smi info -l"


def get_huawei_gpu_basic_info_cmd(npu_id, iswindows=False):
    cmd = "npu-smi info -t board -i {0};npu-smi info -i {0} -t memory;npu-smi info -t power -i {0}".format(
        npu_id)
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_huawei_gpu_product_name_cmd(npu_id, iswindows=False):
    cmd = "npu-smi info -t product -i {0}".format(npu_id)
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_huawei_gpu_aios_rank_table_dict(npu_ids, iswindows=False):
    for npu_id in npu_ids:
        if not npu_id.isdigit():
            raise ValueError("NPU ID must be a digit, got: {}".format(npu_id))

    # Build the command to get IP addresses for each NPU ID using hccn_tool
    device_ips = {}
    device_netmasks = {}
    for npu_id in npu_ids:
        # output example:
        # hccn_tool -i 6 -ip -g
        # ipaddr:172.20.9.77
        # netmask:255.255.0.0
        r, o, e = bash_roe("hccn_tool -i %s -ip -g" % npu_id)

        ip = None
        netmask = None
        if r == 0 and o:
            # Try to match "ipaddr:172.20.9.71" pattern
            import re
            ip_match = re.search(r'ipaddr:(\d+\.\d+\.\d+\.\d+)', o)
            if ip_match:
                ip = ip_match.group(1)
            else:
                # Try alternate pattern "IP: 10.20.0.2"
                ip_match_alt = re.search(r'IP:\s+(\d+\.\d+\.\d+\.\d+)', o)
                if ip_match_alt:
                    ip = ip_match_alt.group(1)

            netmask_match = re.search(r'netmask:(\d+\.\d+\.\d+\.\d+)', o)
            if netmask_match:
                netmask = netmask_match.group(1)
            else:
                netmask_match_alt = re.search(
                    r'Netmask:\s+(\d+\.\d+\.\d+\.\d+)', o)
                if netmask_match_alt:
                    netmask = netmask_match_alt.group(1)

        # Use fallback IP if no IP found
        if not ip:
            logger.warning(
                "Could not retrieve IP for NPU ID %s, using default format" % npu_id)
            ip = "10.20.0.%s" % (int(npu_id) + 2)
        if not netmask:
            logger.warning(
                "Could not retrieve netmask for NPU ID %s, using default" % npu_id)
            netmask = "255.255.0.0"

        device_ips[npu_id] = ip
        device_netmasks[npu_id] = netmask

    # Build rank table dictionary
    rank_table = {
        "server_count": len(npu_ids),
        "server_list": []
    }

    for _, npu_id in enumerate(npu_ids):
        server_info = {
            "device_id": npu_id,
            "host": device_ips[npu_id],
            "device_ip": device_ips[npu_id],
            "netmask": device_netmasks[npu_id]
        }
        rank_table["server_list"].append(server_info)

    return rank_table


def check_huawei_npu_is_isolated(npu_id, all_npu_ids, iswindows=False):
    """
    Check whether a Huawei NPU is isolated using `npu-smi info -t hccs`,
    with topo-based fallback when hccs health line is missing.

    Detection methods:
      1. Primary: hccs health status != OK means isolated
      2. Fallback: topo matrix with zero HCCS connections means isolated
    """
    if not npu_id or not all_npu_ids or len(all_npu_ids) <= 1:
        return False

    try:
        r, _, _ = bash_roe("which npu-smi")
        if r != 0:
            logger.debug("npu-smi not found, cannot check isolation status")
            return False

        cmd = "npu-smi info -t hccs -i {0} -c 0".format(npu_id)
        if iswindows:
            cmd = cmd.replace(" ", "|")

        r, o, e = bash_roe(cmd)
        if r == 0 and o:
            for line in o.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith("hccs health status"):
                    parts = line.split(":", 1)
                    status = parts[1].strip().upper() if len(parts) > 1 else ""
                    if status != "OK":
                        logger.debug(
                            "NPU %s health status is %s, treating as isolated" % (npu_id, status))
                        return True
                    return False

        # Fallback: topo matrix
        logger.debug(
            "hccs health not available for NPU %s, trying topo fallback" % npu_id)
        return _check_npu_isolation_by_topo(npu_id, iswindows)

    except Exception as ex:
        logger.warning("failed to check NPU %s isolation status: %s" %
                       (npu_id, str(ex)))
        return False


def _check_npu_isolation_by_topo(npu_id, iswindows=False):
    """
    Fallback isolation detection via topo matrix.
    An isolated NPU has zero HCCS connections (all links show SYS or PHB).
    """
    cmd = "npu-smi info -t topo -i {0}".format(npu_id)
    if iswindows:
        cmd = cmd.replace(" ", "|")

    r, o, e = bash_roe(cmd)
    if r != 0 or not o:
        logger.debug("failed to get topo for NPU %s: %s" % (npu_id, e))
        return False

    hccs_count = 0
    for line in o.splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("NPU"):
            continue
        parts = stripped.split()
        for part in parts[1:]:
            if part.upper() == "HCCS":
                hccs_count += 1

    if hccs_count == 0:
        logger.debug("NPU %s has 0 HCCS connections in topo (isolated)" % npu_id)
        return True

    return False


def is_valid_video_controller(device):
    invalid_keywords = {"iBMC"}
    return all(keyword not in device for keyword in invalid_keywords)


def is_valid_co_processor(vendor):
    return vendor in [VendorEnum.HAIGUANG]


def is_valid_communication_controller(vendor):
    return vendor in [VendorEnum.KUNLUNXIN]


# get_vastai_type() has been moved to zstacklib.gpu.vendors.vastai.Vastai.get_vastai_type()


def is_valid_processing_accelerator(device):
    valid_keywords = {"Device", "SV100", "MI308X", "S60"}
    return any(keyword in device for keyword in valid_keywords)


def get_enflame_gpu_info_cmd():
    return "efsmi -q"


def post_process_enflame_gpu_device(to):
    """Deprecated: Use post_process_pci_device_by_vendor instead"""
    set_pci_virt_metadata(to, "UNVIRTUALIZABLE", "UNVIRTUALIZABLE")


def _gpu_device_matcher(pci_device_to, context):
    """
    Matcher function for GPU devices: only treat as GPU when gpu.py has already
    identified the device as a GPU (i.e. it is in gpu_info_map from vendor plugins).

    This avoids wrongly sending non-GPU PCI devices (e.g. same vendor/class but not
    actually a GPU) into the GPU processor, where they would get type overwritten
    to GPU_3D_Controller when type refinement branches do not match.
    """
    from zstacklib.utils.pci import normalize_pci_address

    if not context or not getattr(context, 'gpu_info_map', None):
        return False
    normalized_pci = normalize_pci_address(
        getattr(pci_device_to, 'pciDeviceAddress', None) or '')
    if not normalized_pci:
        return False
    return normalized_pci in context.gpu_info_map


def _gpu_device_processor(pci_device_to, context):
    """
    GPU device ops init function (Linux kernel style).

    Similar to pci_driver.probe() in Linux kernel, this initializes GPU devices.

    Architecture (Linux kernel style):
    1. Abstract layer: Generic PCI capabilities (vfio_mdev, sriov) are detected in main loop
    2. Device ops layer: This function implements GPU-specific processing (like pci_driver.probe)
    3. Device-specific layer: Uses abstract capabilities + GPU-specific logic

    This device ops handles GPU-specific logic:
    1. Final GPU confirmation (via gpu_info_map)
    2. Set GPU type refinement (e.g., GPU_Video_Controller)
    3. Determine virtStatus based on GPU-specific interpretation of abstract capabilities
    4. Collect GPU addon info (productName, etc.)
    5. Call vendor's post_process_pci_device hook

    Args:
        pci_device_to: PciDeviceTO object (with _pci_capabilities attribute set by main loop)
        context: PciDeviceProcessingContext object containing processing context

    Returns:
        bool: True if device was processed (is a GPU), False otherwise
    """
    if not pci_device_to:
        return False

    from zstacklib.utils.pci import normalize_pci_address

    gpu_info_map = context.gpu_info_map or {}
    pci_device_mapper = context.pci_device_mapper or {}
    opaque = context.opaque

    # Check if device is GPU. Matcher already restricts to gpu_info_map, so
    # normally we only reach here for devices in the map; fallback is for
    # key mismatch or hot-plug edge cases (get_info still uses vendor plugins).
    normalized_pci = normalize_pci_address(pci_device_to.pciDeviceAddress)
    is_gpu_device = normalized_pci and normalized_pci in gpu_info_map

    if not is_gpu_device:
        # Fallback: per-device get_info() when not in gpu_info_map. Purpose:
        # (1) Hot-plug GPUs that were not present at prepare time. (2) Vendors
        # that implement get_info() but not get_basic_info(). (3) Historical
        # compatibility when matcher was looser. With strict matcher (only
        # gpu_info_map), this path is normally unreachable; kept as safety net.
        vendor_name = pci_device_to.vendor if hasattr(
            pci_device_to, 'vendor') else None
        gpu_info = get_info(
            pci_device=pci_device_to, vendor_name=vendor_name)
        is_gpu_device = (
            gpu_info is not None
            and gpu_info.get("isDriverLoaded") is not False
        )

    if not is_gpu_device:
        return False

    # GPU-specific type refinement: try vendor plugin first, else central table
    vendor_name = getattr(pci_device_to, 'vendor', None)
    refined_type = None
    if vendor_name:
        try:
            from zstacklib.gpu import get_gpu_vendor
            vendor_class = get_gpu_vendor(vendor_name)
            if vendor_class:
                refined_type = vendor_class.refine_gpu_type(
                    pci_device_to, pci_device_to.type, pci_device_mapper)
        except Exception as e:
            logger.debug("refine_gpu_type for vendor %s failed: %s" % (
                vendor_name, str(e)))
    if refined_type is not None:
        pci_device_to.type = refined_type
    else:
        # Central type refinement table: map PCI class (lspci Class) to ZStack GPU type.
        # Used when vendor refine_gpu_type() returns None. Order matters (first match wins):
        # Video > Processing accelerators > Co-processor > Communication > 3D/Display > fallback.
        # pci_device_mapper: i18n for PCI class (English key -> localized string in type).
        # Constants: PCI_CLASS_* and GPU_TYPE_* from zstacklib.gpu.base.
        if ((PCI_CLASS_VGA in pci_device_to.type or PCI_CLASS_DISPLAY in pci_device_to.type
             or (pci_device_mapper.get(PCI_CLASS_VGA) is not None
                 and pci_device_mapper.get(PCI_CLASS_VGA) in pci_device_to.type))
                and is_valid_video_controller(pci_device_to.device)):
            pci_device_to.type = GPU_TYPE_VIDEO_CONTROLLER
        elif ((PCI_CLASS_PROCESSING_ACCEL in pci_device_to.type or (
                pci_device_mapper.get(PCI_CLASS_PROCESSING_ACCEL) is not None
                and pci_device_mapper.get(PCI_CLASS_PROCESSING_ACCEL) in pci_device_to.type))
              and is_valid_processing_accelerator(pci_device_to.device)):
            pci_device_to.type = GPU_TYPE_PROCESSING_ACCELERATORS
        elif ((PCI_CLASS_COPROCESSOR in pci_device_to.type or (
                pci_device_mapper.get(PCI_CLASS_COPROCESSOR) is not None
                and pci_device_mapper.get(PCI_CLASS_COPROCESSOR) in pci_device_to.type))
              and is_valid_co_processor(pci_device_to.vendor)):
            pci_device_to.type = GPU_TYPE_CO_PROCESSOR
        elif ((PCI_CLASS_COMMUNICATION in pci_device_to.type or (
                pci_device_mapper.get(PCI_CLASS_COMMUNICATION) is not None
                and pci_device_mapper.get(PCI_CLASS_COMMUNICATION) in pci_device_to.type))
              and is_valid_communication_controller(pci_device_to.vendor)):
            pci_device_to.type = GPU_TYPE_COMMUNICATION_CONTROLLER
        elif (PCI_CLASS_3D in pci_device_to.type or PCI_CLASS_DISPLAY in pci_device_to.type
              or (pci_device_mapper.get(PCI_CLASS_3D) is not None
                  and pci_device_mapper.get(PCI_CLASS_3D) in pci_device_to.type)):
            pci_device_to.type = GPU_TYPE_3D_CONTROLLER
        else:
            pci_device_to.type = GPU_TYPE_3D_CONTROLLER

    # GPU-specific virtualization capabilities detection via vendor methods
    # Detect all capabilities independently; virtCapabilities is the union.
    # virtStatus/virtState/virtMode use priority: vfio_mdev > sriov > tensorfusion
    vendor_name = pci_device_to.vendor if hasattr(
        pci_device_to, 'vendor') else None
    if vendor_name:
        try:
            from zstacklib.gpu import get_gpu_vendor
            vendor_class = get_gpu_vendor(vendor_name)
            if vendor_class:
                def _safe_detect(name, fn, *args):
                    try:
                        return fn(*args)
                    except Exception as e:
                        logger.debug("Failed to detect GPU %s capability for vendor %s: %s" % (
                            name, vendor_name, str(e)))
                        return False, {}

                # Detect all capabilities independently (no short-circuit)
                vfio_mdev_supported, vfio_mdev_info = _safe_detect(
                    "vfio_mdev", vendor_class.detect_vfio_mdev_capability, pci_device_to)
                sriov_supported, sriov_info = _safe_detect(
                    "sriov", vendor_class.detect_sriov_capability, pci_device_to, gpu_info_map)
                tensorfusion_supported, tensorfusion_info = _safe_detect(
                    "tensorfusion", vendor_class.detect_tensorfusion_capability, pci_device_to)

                # Apply non-virtStatus attributes
                if vfio_mdev_supported and 'mdevSpecifications' in vfio_mdev_info:
                    pci_device_to.mdevSpecifications = vfio_mdev_info['mdevSpecifications']
                if sriov_supported:
                    if 'maxPartNum' in sriov_info:
                        pci_device_to.maxPartNum = sriov_info['maxPartNum']
                    if 'parentAddress' in sriov_info:
                        pci_device_to.parentAddress = sriov_info['parentAddress']
                    if 'ramSize' in sriov_info:
                        pci_device_to.ramSize = sriov_info['ramSize']
                        pci_device_to.description = "%s [RAM Size: %s]" % (
                            pci_device_to.description, sriov_info['ramSize'])

                # Set virtStatus/virtState/virtMode by priority (backward compat)
                if vfio_mdev_supported:
                    apply_explicit_virt_metadata(pci_device_to, vfio_mdev_info)
                elif sriov_supported:
                    apply_explicit_virt_metadata(pci_device_to, sriov_info)
                elif tensorfusion_supported:
                    apply_explicit_virt_metadata(pci_device_to, tensorfusion_info)
                elif not pci_device_to.virtStatus:
                    set_pci_virt_metadata(
                        pci_device_to, "UNVIRTUALIZABLE", "UNVIRTUALIZABLE")

                # Merge virtCapabilities from all detected capabilities (union)
                all_capabilities = []
                for _supported, _info in [
                    (vfio_mdev_supported, vfio_mdev_info),
                    (sriov_supported, sriov_info),
                    (tensorfusion_supported, tensorfusion_info),
                ]:
                    if _supported:
                        for _cap in (_info.get('virtCapabilities') or []):
                            if _cap and _cap not in all_capabilities:
                                all_capabilities.append(_cap)
                if all_capabilities:
                    pci_device_to.virtCapabilities = all_capabilities
        except Exception as e:
            logger.debug("Failed to detect GPU capabilities for vendor %s: %s" % (
                vendor_name, str(e)))
            if not pci_device_to.virtStatus:
                set_pci_virt_metadata(
                    pci_device_to, "UNVIRTUALIZABLE", "UNVIRTUALIZABLE")

    # Collect GPU addon info (productName, etc.) from enriched gpu_info_map
    vendor_name = pci_device_to.vendor if hasattr(
        pci_device_to, 'vendor') else None
    if vendor_name and normalized_pci and normalized_pci in gpu_info_map:
        info = gpu_info_map[normalized_pci].copy()
        pci_device_to.addonInfo = info

        # Set ramSize from gpu_info_map when present (e.g. Alibaba ppu-smi memory)
        if info.get("memory"):
            pci_device_to.ramSize = info.get("memory")
        # Set maxPartNum from gpu_info_map when present (e.g. vendor SR-IOV or partition count)
        if info.get("maxPartNum") is not None:
            pci_device_to.maxPartNum = str(info["maxPartNum"])

        # Override device/name with productName when available
        product_name = info.get("productName")
        if product_name:
            pci_device_to.device = product_name
            pci_device_to.name = product_name
        else:
            # Simplify lspci device name: 'GA102 [GeForce RTX 3090]' → 'GeForce RTX 3090'
            from zstacklib.utils.pci import simplify_device_name
            simplified = simplify_device_name(pci_device_to.device)
            if simplified and simplified != pci_device_to.device:
                pci_device_to.device = simplified
                pci_device_to.name = "%s_%s" % (vendor_name, simplified)

    # Call vendor's post_process_pci_device hook
    if vendor_name:
        post_process_pci_device_by_vendor(pci_device_to, vendor_name)

    return True


def post_process_pci_device_by_vendor(pci_device_to, vendor_name=None):
    """
    Post-process PCI device by calling vendor's post_process_pci_device hook.

    This allows each vendor to handle their own virtualization status and other
    post-processing logic.

    Args:
        pci_device_to: PciDeviceTO object
        vendor_name: VendorEnum value (optional, will extract from pci_device_to if not provided)
    """
    if not pci_device_to:
        return

    # Extract vendor_name from pci_device_to if not provided
    if not vendor_name and hasattr(pci_device_to, 'vendor'):
        vendor_name = pci_device_to.vendor

    if not vendor_name:
        return

    try:
        from zstacklib.gpu import get_gpu_vendor
        vendor_class = get_gpu_vendor(vendor_name)
        if vendor_class and hasattr(vendor_class, 'post_process_pci_device'):
            vendor_class.post_process_pci_device(pci_device_to)
    except Exception as e:
        logger.debug(
            "Failed to post-process PCI device for vendor %s: %s" % (vendor_name, str(e)))


def get_kunlunxin_gpu_xpu_id_cmd():
    return "xpu-smi -L"


def get_kunlunxin_xpu_id(xpu_id_output):
    xpu_ids = []
    for line in xpu_id_output.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r'^XPU\s+(\d+):', line)
        if match:
            xpu_ids.append(match.group(1))
    return xpu_ids


def get_kunlunxin_gpu_basic_info_cmd(xpu_id, iswindows=False):
    cmd = "xpu-smi -q --id={0}".format(xpu_id)
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def parse_kunlunxin_gpu_output_by_npu_id(output):
    """
    Parse xpu-smi -q --id=<xpu_id> output (single XPU block).
    Full output sample (if driver/CLI changes, compare against this):
    ---------------
    ==============XPUSMI LOG==============

    Timestamp                                 : Tue Feb  3 18:20:01 2026
    Driver Version                            : 5.0.21.26
    XPU-RT Version                            : 10.2

    Attached XPUs                             : 2
    XPU 00000000:01:00.0
        Product Name                          : P800 PCIe
        Product Brand                         : KUNLUNXIN
        Product Architecture                  : KL3
        Serial Number                         : 02K0MA0258D0007R
        XPU UUID                              : GPU-420716f2-9928-5108-a5b2-e6b7cf36b37c
        Minor Number                          : 0
        PCIe Id                               : 3
        XPU Part Number                       : B00100300110211
        Firmware Version
            PBL Version                       : 1.0
            PCIE Version                      : 2.14
            SBL Version                       : 1.54
            ALL Version                       : 1.0.2.14.1.54
            CPLD Version                      : 2.0
        PCI
            Bus                               : 0x01
            Device                            : 0x00
            Function                          : 0x0
            Domain                            : 0x0000
            Device Id                         : 0x36862057
            Bus Id                            : 00000000:01:00.0
            Sub System Id                     : 0x00010001
            XPU Link Info
                PCIe Generation
                    Max                       : 4
                    Current                   : 3
                Link Width
                    Max                       : 16x
                    Current                   : 16x
        Memory Usage
            Total                             : 98304 MiB
            Reserved                          : 0 MiB
            Used                              : 0 MiB
            Free                              : 98304 MiB
        L3 Usage
            Total                             : 96 MiB
            Reserved                          : 0 MiB
            Used                              : 0 MiB
            Free                              : 96 MiB
        Utilization
            Xpu                               : 0 %
        Ecc Mode
            Current                           : Enabled
            Pending                           : Enabled
        ECC Errors
            Volatile
                DRAM Correctable              : 0
                DRAM Uncorrectable            : 0
            Aggregate
                DRAM Correctable              : 0
                DRAM Uncorrectable            : 0
        Temperature
            XPU Current Temp                  : 46 C
        Power Readings
            Enforced Power Limit              : 350.00 W
            Power Draw                        : 76.00 W
        Clocks
            Cluster                           : 1450 MHz
            CDNN                              : 1450 MHz
        Processes                             : None
    ---------------
    Parsed keys: Product Name, Serial Number, Bus Id, Memory Usage Total/Used,
    Enforced Power Limit, Power Draw, XPU Current Temp, Utilization Xpu.
    """
    gpuinfos = []
    gpuinfo = {}
    current_section = None
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            current_section = line
            continue

        parts = line.split(":", 1)
        if len(parts) < 2:
            continue
        key = parts[0].strip()
        value = parts[1].strip()

        if key == "Product Name":
            gpuinfo["productName"] = value
        elif key == "Serial Number":
            gpuinfo["serialNumber"] = value
        elif key == "Bus Id":
            pci_device_address = value.lower()
            if len(pci_device_address.split(':')[0]) == 8:
                pci_device_address = pci_device_address[4:].lower()
            gpuinfo["pciAddress"] = pci_device_address
        elif current_section == "Memory Usage":
            if key == "Total":
                gpuinfo["memory"] = value
            elif key == "Used":
                gpuinfo["memoryUsage"] = value
        elif current_section == "Utilization":
            if key == "Xpu" and "%" in value:
                gpuinfo["xpuUtilization"] = value
        elif key == "Enforced Power Limit":
            gpuinfo["power"] = value
        elif key == "Power Draw":
            gpuinfo["powerDraw"] = value
        elif key == "XPU Current Temp":
            gpuinfo["temperature"] = value

    logger.info("kunlunxin gpu info: %s" % gpuinfo)
    gpuinfos.append(gpuinfo)
    return gpuinfos


def get_gpu_status_cmd(pci_device_address, iswindows=False):
    cmd = "lspci -s {}".format(pci_device_address)
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_shut_nvidia_persistence_cmd(iswindows=False):
    cmd = "ps -ef | grep nvidia-persistenced | grep -v grep | awk '{print $2}' | xargs -r kill -15"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def has_nvidia_gpu():
    r, _, _ = bash_roe("which nvidia-smi")
    if r != 0:
        return False
    r, o, e = bash_roe("nvidia-smi -L")
    return r == 0 and o and len(o.strip()) > 0


_nvidia_persistenced_active = False
_nvidia_persistenced_lock = threading.Lock()


def ensure_nvidia_persistenced_once(timeout=5):
    global _nvidia_persistenced_active

    with _nvidia_persistenced_lock:
        # If already running, nothing to do
        r, o, e = bash_roe("pgrep -f nvidia-persistenced || true")
        is_running = bool(o and o.strip())

        if is_running:
            _nvidia_persistenced_active = True
            return True

        if _nvidia_persistenced_active:
            _nvidia_persistenced_active = False
            logger.debug(
                'nvidia-persistenced stopped, will retry in next cycle')
            return True

        start_cmd = "nohup nvidia-persistenced >/dev/null 2>&1 &"
        logger.info('starting nvidia-persistenced with: %s' % start_cmd)
        bash_roe(start_cmd)

        # Wait for it to appear
        time.sleep(timeout)
        r, o, e = bash_roe("pgrep -f nvidia-persistenced || true")
        if o and o.strip():
            return True
        else:
            logger.warning(
                'nvidia-persistenced did not appear after start attempt')
            return False


def start_nvidia_persistenced_monitor(poll_interval=60 * 2, stop_event=None):
    """Monitor nvidia-persistenced and restart it if it dies while GPU exists."""
    logger.info(
        "start_nvidia_persistenced_monitor: starting monitor (interval=%s)" % poll_interval)
    if stop_event is None:
        stop_event = threading.Event()

    while not stop_event.is_set():
        if not has_nvidia_gpu():
            stop_event.wait(poll_interval)
            continue

        r = ensure_nvidia_persistenced_once()
        if not r:
            logger.warning(
                "nvidia-persistenced not running and could not be started")

        stop_event.wait(poll_interval)


def watch_and_ensure_nvidia_persistenced(poll_interval=30, stop_event=None):
    """Watch for GPUs appearing later. Once detected, ensure persistenced and start monitor, then exit."""
    logger.info(
        "watch_and_ensure_nvidia_persistenced: watching for NVIDIA GPU (interval=%s)" % poll_interval)
    if stop_event is None:
        stop_event = threading.Event()

    while not stop_event.is_set():
        if has_nvidia_gpu():
            ensure_nvidia_persistenced_once()
            thread.ThreadFacade.run_in_thread(start_nvidia_persistenced_monitor, [
                                              poll_interval, stop_event])
            return

        stop_event.wait(poll_interval)


def get_alibaba_ppu_product_name_cmd(iswindows=False):
    """Get Alibaba PPU product name command"""
    cmd = "ppu-smi -q | grep 'Product Name'"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_alibaba_ppu_product_name(output):
    """Parse Alibaba PPU product name from ppu-smi -q output"""
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Product Name" in line:
            parts = line.split(":", 1)
            if len(parts) > 1:
                return parts[1].strip()
    return None


def get_alibaba_ppu_basic_info_cmd(iswindows=False):
    """Get Alibaba PPU basic info command (PCI address, memory, power limit, serial)"""
    cmd = "ppu-smi --query-ppu=gpu_bus_id,memory.total,power.limit,gpu_serial --format=csv,noheader"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_alibaba_ppu_metric_info_cmd(iswindows=False):
    """Get Alibaba PPU metric info command (PCI address, utilization, temperature, power draw, memory utilization, pcie tx/rx, serial)"""
    cmd = "ppu-smi --query-ppu=gpu_bus_id,utilization.ppu,temperature.ppu,power.draw,utilization.memory,pcie.throughput.tx,pcie.throughput.rx,gpu_serial --format=csv,noheader"
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def parse_alibaba_ppu_output(output):
    """
    Parse Alibaba PPU basic info output.

    Input format:
    00000000:08:00.0, 98304 MiB, 400.00 W, 02A8B95253C002B8

    Returns list of dicts with pciAddress, memory, power, serialNumber
    """
    gpuinfos = []
    for line in output.split('\n'):
        if len(line.strip()) == 0:
            continue
        parts = line.split(',')
        if len(parts) < 4:
            continue

        gpuinfo = {}
        pci_address = parts[0].strip().lower()
        # Remove domain prefix if 8 chars (e.g., 00000000:08:00.0 -> 0000:08:00.0)
        if len(pci_address.split(':')[0]) == 8:
            pci_address = pci_address[4:].lower()

        gpuinfo["pciAddress"] = pci_address
        gpuinfo["memory"] = parts[1].strip()
        gpuinfo["power"] = parts[2].strip()
        gpuinfo["serialNumber"] = parts[3].strip()
        gpuinfos.append(gpuinfo)

    return gpuinfos


def parse_alibaba_ppu_metric_output(output):
    """
    Parse Alibaba PPU metric info output.

    Input format:
    00000000:08:00.0, 0 %, 27 C, 83.03 W, 02A8B95253C002B8

    Returns list of dicts with pciAddress, utilization, temperature, power, serialNumber
    """
    gpuinfos = []
    for line in output.split('\n'):
        if len(line.strip()) == 0:
            continue
        parts = line.split(',')
        if len(parts) < 5:
            continue

        gpuinfo = {}
        pci_address = parts[0].strip().lower()
        # Remove domain prefix if 8 chars
        if len(pci_address.split(':')[0]) == 8:
            pci_address = pci_address[4:].lower()

        gpuinfo["pciAddress"] = pci_address
        gpuinfo["utilization"] = parts[1].replace('%', '').strip()
        gpuinfo["temperature"] = parts[2].replace('C', '').strip()
        gpuinfo["power"] = parts[3].replace('W', '').strip()
        gpuinfo["serialNumber"] = parts[4].strip()
        gpuinfos.append(gpuinfo)

    return gpuinfos


# =============================================================================
# Unified Simplified Interface - One-line call handles all logic
# =============================================================================

def _is_function_0(pci_address):
    """
    Check if PCI address is function 0.

    Args:
        pci_address: PCI address string (any format)

    Returns:
        bool: True if function is 0, False otherwise or if parsing fails
    """
    from zstacklib.utils.pci import normalize_pci_address
    normalized = normalize_pci_address(pci_address)
    if not normalized:
        return False
    # Extract function part (last component after '.')
    try:
        function_part = normalized.split('.')[-1]
        func_num = int(function_part, 16)
        return func_num == 0
    except (ValueError, IndexError):
        return False


def get_info(pci_address=None, pci_device=None, vendor_name=None):
    """
    Unified GPU information collection interface - one-line call handles all logic

    Automatically handles:
    - Auto-identify vendor (if not provided)
    - Prioritize plugin (no environment variable check, try directly)
    - Auto fallback to legacy when plugin fails
    - Handle all vendor-specific fields (Huawei npuId, product name, etc.)

    Args:
        pci_address: PCI address string, e.g., "0000:3b:00.0"
        pci_device: PciDeviceTO object (optional, auto-extract pci_address and vendor)
        vendor_name: VendorEnum value (optional, auto-identify)

    Returns:
        dict: GPU information dictionary, format:
        {
            "memory": "15360 MiB",
            "power": "70.00 W",
            "serialNumber": "...",
            "isDriverLoaded": True,
            # vendor-specific fields (e.g., Huawei's npuId, isIsolated, productName, aiosRankTable, etc.)
        }
        Returns None if collection fails or device is not a GPU
    """
    # 1. Extract pci_address and vendor_name
    if pci_device:
        pci_address = pci_device.pciDeviceAddress
        if not vendor_name and hasattr(pci_device, 'vendor'):
            vendor_name = pci_device.vendor

    if not pci_address:
        return None

    # Normalize PCI address using proper normalization function
    from zstacklib.utils.pci import normalize_pci_address
    normalized_pci = normalize_pci_address(pci_address)
    if not normalized_pci:
        logger.debug("Invalid PCI address format: %s" % pci_address)
        return None

    # Only process function 0 devices - GPU devices typically only have function 0 as the actual GPU,
    # while function 1+ may be other functions (e.g., audio controller) and should not be treated as GPU devices.
    if not _is_function_0(normalized_pci):
        logger.debug("Skipping non-function-0 PCI device: %s (only function 0 devices are treated as GPU)" %
                     normalized_pci)
        return None

    # Use normalized address for all subsequent operations
    pci_address = normalized_pci

    # 2. Try using plugin (no environment variable check, try directly)
    try:
        from zstacklib.gpu import (
            get_gpu_vendor,
            get_vendor_enum_mapping,
        )

        # Get mapping from vendor enum to plugin vendor name
        vendor_enum_mapping = get_vendor_enum_mapping()
        plugin_vendor_name = vendor_enum_mapping.get(
            vendor_name) if vendor_name else None

        if plugin_vendor_name:
            plugin = get_gpu_vendor(plugin_vendor_name)
            if plugin and plugin.is_available():
                # Use plugin to collect information
                gpu_infos = plugin.get_basic_info()
                for gpu_info in gpu_infos:
                    # Normalize plugin returned pci_address for consistent comparison
                    normalized_gpu_pci = normalize_pci_address(
                        gpu_info.pci_address)
                    if not normalized_gpu_pci:
                        continue
                    # Only match function 0 devices and ensure exact match
                    if normalized_gpu_pci == pci_address and _is_function_0(normalized_gpu_pci):
                        result = gpu_info.to_addon_dict()

                        # Handle vendor-specific extra fields
                        if vendor_name == VendorEnum.HUAWEI:
                            # Huawei special handling: npuId, isIsolated already in extra
                            result.update(gpu_info.extra)

                            # Collect product name and aios rank table (using legacy functions)
                            try:
                                npu_ids = plugin.get_npu_ids()  # Class method
                                if npu_ids:
                                    r, o, e = bash_roe(
                                        get_huawei_gpu_product_name_cmd(npu_ids))
                                    if r == 0 and o and "not support" not in o:
                                        product_type = get_huawei_product_type(
                                            o)
                                        if product_type:
                                            result["productName"] = product_type

                                    # Collect aios rank table
                                    try:
                                        aios_rank_table = get_huawei_gpu_aios_rank_table_dict(
                                            npu_ids)
                                        if aios_rank_table:
                                            result["opaque"] = {
                                                "aiosRankTable": aios_rank_table}
                                    except Exception as e:
                                        logger.debug(
                                            "Failed to get aios rank table: %s" % str(e))
                            except Exception as e:
                                logger.debug(
                                    "Failed to get Huawei product name: %s" % str(e))

                        elif vendor_name == VendorEnum.TIANSHU:
                            # Tianshu special handling: product name
                            try:
                                r, o, e = bash_roe(
                                    get_tianshu_gpu_product_name_cmd())
                                if r == 0 and o:
                                    product_name = get_tianshu_product_name(o)
                                    if product_name:
                                        result["productName"] = product_name
                            except Exception as e:
                                logger.debug(
                                    "Failed to get Tianshu product name: %s" % str(e))

                        elif vendor_name == VendorEnum.ALIBABA:
                            # Alibaba special handling: product name
                            try:
                                r, o, e = bash_roe(
                                    get_alibaba_ppu_product_name_cmd())
                                if r == 0 and o:
                                    product_name = get_alibaba_ppu_product_name(
                                        o)
                                    if product_name:
                                        result["productName"] = product_name
                            except Exception as e:
                                logger.debug(
                                    "Failed to get Alibaba product name: %s" % str(e))

                        return result
                # Plugin ran but no matching GPU found (e.g. hy-smi "No device available" in VM)
                # Fall through to legacy so vendor can return minimal addon and device still recognized as GPU
    except Exception as e:
        logger.debug("Plugin failed for %s, fallback to legacy: %s" %
                     (pci_address, str(e)))

    # 3. Fallback to legacy (error tolerance mechanism)
    return _get_info_legacy(pci_address, vendor_name)


def _get_info_legacy(pci_address, vendor_name):
    """
    Legacy method to collect GPU information (as fallback error tolerance)
    """
    if not vendor_name:
        return None

    pci_address = pci_address.lower()

    # Legacy vendor handler function mapping
    legacy_handlers = {
        VendorEnum.NVIDIA: _collect_nvidia_legacy,
        VendorEnum.AMD: _collect_amd_legacy,
        VendorEnum.HAIGUANG: _collect_haiguang_legacy,
        VendorEnum.HUAWEI: _collect_huawei_legacy,
        VendorEnum.TIANSHU: _collect_tianshu_legacy,
        VendorEnum.VASTAI: _collect_vastai_legacy,
        VendorEnum.ENFLAME: _collect_enflame_legacy,
        VendorEnum.ALIBABA: _collect_alibaba_legacy,
        VendorEnum.KUNLUNXIN: _collect_kunlunxin_legacy,
    }

    handler = legacy_handlers.get(vendor_name)
    if not handler:
        return None

    try:
        return handler(pci_address)
    except Exception as e:
        logger.warn("Legacy handler failed for %s (%s): %s" %
                    (vendor_name, pci_address, str(e)))
        return None


def _collect_nvidia_legacy(pci_address):
    """NVIDIA legacy collection"""
    r, o, e = bash_roe("which nvidia-smi")
    if r != 0:
        return None

    r, o, e = bash_roe(get_nvidia_gpu_basic_info_cmd())
    if r != 0:
        return None

    gpu_infos = parse_nvidia_gpu_output(o)
    for gpuinfo in gpu_infos:
        if pci_address in gpuinfo.get("pciAddress", "").lower():
            result = {
                "memory": gpuinfo.get("memory"),
                "power": gpuinfo.get("power"),
                "serialNumber": gpuinfo.get("serialNumber"),
                "isDriverLoaded": True,
            }
            return result

    return None


def _collect_amd_legacy(pci_address):
    """AMD legacy collection"""
    r, o, e = bash_roe("which rocm-smi")
    if r != 0:
        return None

    r, o, e = bash_roe(get_amd_gpu_basic_info_cmd())
    if r != 0:
        return None

    gpu_infos = parse_amd_gpu_output(o)
    for gpuinfo in gpu_infos:
        if pci_address in gpuinfo.get("pciAddress", "").lower():
            result = {
                "memory": gpuinfo.get("memory"),
                "power": gpuinfo.get("power"),
                "serialNumber": gpuinfo.get("serialNumber"),
                "isDriverLoaded": True,
            }
            return result

    return None


def _collect_haiguang_legacy(pci_address):
    """
    Haiguang legacy collection.
    When hy-smi fails (e.g. "No device available" inside VM after GPU passthrough),
    still return minimal addon so the PCI device is recognized as GPU type.
    """
    # Minimal addon when SMI unavailable/fails: device still treated as GPU (e.g. passthrough VM)
    minimal_addon = {
        "memory": None,
        "power": None,
        "serialNumber": "",
        "isDriverLoaded": True,
    }

    r, o, e = bash_roe("which hy-smi")
    if r != 0:
        return minimal_addon

    r, o, e = bash_roe(get_hy_gpu_basic_info_cmd())
    if r != 0:
        # e.g. "No device available, no device found or initialization failed" in VM
        return minimal_addon

    gpu_infos = parse_hy_gpu_output(o)
    for gpuinfo in gpu_infos:
        if pci_address in gpuinfo.get("pciAddress", "").lower():
            return {
                "memory": gpuinfo.get("memory"),
                "power": gpuinfo.get("power"),
                "serialNumber": gpuinfo.get("serialNumber"),
                "isDriverLoaded": True,
            }

    # No matching PCI (e.g. empty output in VM) -> still recognize as GPU
    return minimal_addon


def _collect_huawei_legacy(pci_address):
    """Huawei legacy collection (includes special fields)"""
    r, o, e = bash_roe("which npu-smi")
    if r != 0:
        return None

    r, npu_ids_out = bash_ro(get_huawei_gpu_npu_id_cmd())
    if r != 0:
        return None

    npu_ids = get_huawei_npu_id(npu_ids_out)
    if not npu_ids:
        return None

    npu_infos = []
    npu_id_map = {}
    for npu_id in npu_ids:
        r, o, e = bash_roe(get_huawei_gpu_basic_info_cmd(npu_id))
        if r != 0:
            continue

        parsed_infos = parse_huawei_gpu_output_by_npu_id(o)
        for info in parsed_infos:
            pci_addr = info.get("pciAddress", "")
            if pci_addr:
                npu_id_map[pci_addr.lower()] = npu_id
        npu_infos.extend(parsed_infos)

    # Find matching GPU
    for npu_info in npu_infos:
        if pci_address not in npu_info.get("pciAddress", "").lower():
            continue

        result = {
            "memory": npu_info.get("memory"),
            "power": npu_info.get("power"),
            "serialNumber": npu_info.get("serialNumber"),
            "isDriverLoaded": True,
        }

        # Add Huawei special fields
        matched_npu_id = npu_id_map.get(pci_address)
        if matched_npu_id:
            result["npuId"] = matched_npu_id
            try:
                is_isolated = check_huawei_npu_is_isolated(
                    matched_npu_id, npu_ids)
                result["isIsolated"] = is_isolated
            except Exception as ex:
                result["isIsolated"] = False

        # Collect product name
        try:
            r, o, e = bash_roe(get_huawei_gpu_product_name_cmd(npu_ids))
            if r == 0 and o and "not support" not in o:
                product_type = get_huawei_product_type(o)
                if product_type:
                    result["productName"] = product_type
        except Exception as e:
            logger.debug("Failed to get Huawei product name: %s" % str(e))

        # Collect aios rank table
        try:
            aios_rank_table = get_huawei_gpu_aios_rank_table_dict(npu_ids)
            if aios_rank_table:
                result["opaque"] = {"aiosRankTable": aios_rank_table}
        except Exception as e:
            logger.debug("Failed to get aios rank table: %s" % str(e))

        return result

    return None


def _collect_tianshu_legacy(pci_address):
    """Tianshu legacy collection"""
    r, o, e = bash_roe("which ixsmi")
    if r != 0:
        return None

    if shell.run(is_tianshu_v1()) == 0:
        cmd = get_tianshu_gpu_basic_info_cmd_v1()
    else:
        cmd = get_tianshu_gpu_basic_info_cmd_v2()

    r, o, e = bash_roe(cmd)
    if r != 0:
        return None

    gpu_infos = parse_tianshu_gpu_output(o)
    for gpuinfo in gpu_infos:
        if pci_address in gpuinfo.get("pciAddress", "").lower():
            result = {
                "memory": gpuinfo.get("memory"),
                "power": gpuinfo.get("power"),
                "serialNumber": gpuinfo.get("serialNumber"),
                "isDriverLoaded": True,
            }

            # Collect product name
            try:
                r, o, e = bash_roe(get_tianshu_gpu_product_name_cmd())
                if r == 0 and o:
                    product_name = get_tianshu_product_name(o)
                    if product_name:
                        result["productName"] = product_name
            except Exception as e:
                logger.debug("Failed to get Tianshu product name: %s" % str(e))

            return result

    return None


def _collect_vastai_legacy(pci_address):
    """Vastai legacy collection"""
    try:
        from zstacklib.gpu.vendors.vastai import Vastai
        from zstacklib.utils import shell, sizeunit
    except ImportError:
        return None

    r, o, e = bash_roe("which vasmi")
    if r != 0:
        return None

    gpu_type = Vastai.get_vastai_type()
    gpuinfos = []

    data = shell.run_with_json_result("vasmi getmem --display-format=json")
    if data:
        for elem in data.get("elem", []):
            gpuinfo = {}
            pci_bus = elem.get("pci_bus", "N/A")
            gpuinfo["pciAddress"] = Vastai.normalize_pci_address(pci_bus)
            gpuinfo["serialNumber"] = elem.get("sn", "N/A")
            key = "Physical" if gpu_type == "AI" else "Physical memory"
            row_memory = elem.get("vals", {}).get(key, {}).get("value", "N/A")
            gpuinfo["memory"] = row_memory if row_memory == "N/A" else str(
                sizeunit.get_size(row_memory)) + "B"
            gpuinfos.append(gpuinfo)

    summary_data = shell.run_with_json_result(
        "vasmi summary --display-format=json")
    if summary_data:
        for elem in summary_data.get("elem", []):
            dev_bus_id_raw = elem.get("vals", {}).get(
                "devBusId", {}).get("value", "N/A")
            dev_bus_id = Vastai.normalize_pci_address(dev_bus_id_raw)
            max_power = elem.get("vals", {}).get(
                "P_Cap", {}).get("value", "N/A")
            for gpuinfo in gpuinfos:
                if gpuinfo["pciAddress"] == dev_bus_id:
                    gpuinfo["power"] = max_power

    for gpuinfo in gpuinfos:
        if pci_address in gpuinfo.get("pciAddress", "").lower():
            result = {
                "memory": gpuinfo.get("memory"),
                "power": gpuinfo.get("power"),
                "serialNumber": gpuinfo.get("serialNumber"),
                "isDriverLoaded": True,
            }
            return result

    return None


def _collect_enflame_legacy(pci_address):
    """Enflame legacy collection"""
    r, o, e = bash_roe("which efsmi")
    if r != 0:
        return None

    r, o, e = bash_roe(get_enflame_gpu_info_cmd())
    if r != 0:
        return None

    for info in parse_enflame_gpu_output(o):
        if pci_address not in info.get("pciAddress", "").lower():
            continue

        mem = info.get("memory", "")
        power = info.get("powerCap", "")
        serial = info.get("serialNumber", "")

        result = {"isDriverLoaded": True}

        if mem and re.match(r"^\s*\d+\s*MiB\s*$", mem, re.IGNORECASE):
            result["memory"] = mem.strip()
        if power and re.match(r"^\s*\d+(\.\d+)?\s*W\s*$", power, re.IGNORECASE):
            result["power"] = power.strip()
        if serial and serial.strip():
            result["serialNumber"] = serial

        return result

    return None


def _collect_alibaba_legacy(pci_address):
    """Alibaba legacy collection"""
    r, o, e = bash_roe("which ppu-smi")
    if r != 0:
        return None

    r, o, e = bash_roe(get_alibaba_ppu_basic_info_cmd())
    if r != 0:
        return None

    gpu_infos = parse_alibaba_ppu_output(o)
    for gpuinfo in gpu_infos:
        if pci_address in gpuinfo.get("pciAddress", "").lower():
            result = {
                "memory": gpuinfo.get("memory"),
                "power": gpuinfo.get("power"),
                "serialNumber": gpuinfo.get("serialNumber"),
                "isDriverLoaded": True,
            }

            # Collect product name
            try:
                r, o, e = bash_roe(get_alibaba_ppu_product_name_cmd())
                if r == 0 and o:
                    product_name = get_alibaba_ppu_product_name(o)
                    if product_name:
                        result["productName"] = product_name
            except Exception as e:
                logger.debug("Failed to get Alibaba product name: %s" % str(e))

            return result

    return None


def _collect_kunlunxin_legacy(pci_address):
    """Kunlunxin legacy collection"""
    r, o, e = bash_roe("which xpu-smi")
    if r != 0:
        return None

    r, o, e = bash_roe(get_kunlunxin_gpu_xpu_id_cmd())
    if r != 0:
        return None

    xpu_ids = get_kunlunxin_xpu_id(o)
    for xpu_id in xpu_ids:
        r, o, e = bash_roe(get_kunlunxin_gpu_basic_info_cmd(xpu_id))
        if r != 0:
            continue
        gpu_infos = parse_kunlunxin_gpu_output_by_npu_id(o)
        for gpuinfo in gpu_infos:
            if pci_address in gpuinfo.get("pciAddress", "").lower():
                result = {
                    "memory": gpuinfo.get("memory"),
                    "power": gpuinfo.get("power"),
                    "serialNumber": gpuinfo.get("serialNumber"),
                    "productName": gpuinfo.get("productName"),
                    "isDriverLoaded": True,
                }
                return result

    return None


def get_all_info():
    """
    Collect information for all GPUs

    Returns:
        list: List of GPU information dictionaries
    """
    results = []

    # Try using plugin
    try:
        from zstacklib.gpu import get_all_gpu_vendors
        for vendor_class in get_all_gpu_vendors():
            if not vendor_class.is_available():
                continue
            gpu_infos = vendor_class.get_basic_info()
            for gpu_info in gpu_infos:
                result = gpu_info.to_addon_dict()
                result.update(gpu_info.extra)
                results.append(result)

        if results:
            return results
    except Exception as e:
        logger.debug("Plugin failed, fallback to legacy: %s" % str(e))

    return results


def get_all_gpu_infos_by_pci():
    """
    Collect information for all GPUs and return as a dict mapping PCI address to GPU info.

    This is optimized for batch processing - queries all vendors once, then provides
    O(1) lookup by PCI address.

    Note: Only function 0 devices are included in the map. GPU devices typically
    only have function 0 as the actual GPU, while function 1+ may be other functions
    (e.g., audio controller) and should not be treated as GPU devices.

    Returns:
        dict: Mapping of normalized PCI address -> GPU info dict
        Example: {
            "0000:3b:00.0": {"memory": "15360 MiB", "power": "70.00 W", ...},
            "0000:42:00.0": {"memory": "8192 MiB", "power": "50.00 W", ...}
        }
    """
    from zstacklib.utils.pci import normalize_pci_address

    gpu_info_map = {}

    try:
        from zstacklib.gpu import get_all_gpu_vendors
        for vendor_class in get_all_gpu_vendors():
            if not vendor_class.is_available():
                continue
            try:
                gpu_infos = vendor_class.get_basic_info()
                for gpu_info in gpu_infos:
                    if gpu_info.pci_address:
                        normalized_pci = normalize_pci_address(
                            gpu_info.pci_address)
                        if normalized_pci:
                            # Only include function 0 devices in the map
                            # GPU devices typically only have function 0 as the actual GPU,
                            # while function 1+ may be other functions (e.g., audio controller)
                            # and should not be treated as GPU devices.
                            if normalized_pci.endswith('.0'):
                                result = gpu_info.to_addon_dict()
                                result.update(gpu_info.extra)
                                gpu_info_map[normalized_pci] = result
                            else:
                                logger.debug("Skipping non-function-0 GPU device: %s (vendor: %s)" %
                                             (normalized_pci, vendor_class.VENDOR_NAME))
            except Exception as e:
                logger.debug("Failed to get basic info from plugin %s: %s" %
                             (vendor_class.VENDOR_NAME, str(e)))
                continue
    except Exception as e:
        logger.debug("Failed to collect GPU infos via plugin: %s" % str(e))

    # Fallback (degraded): for vendors without SMI, supplement map from PCI
    # (vendor_id + class). SMI remains primary; we only add when SMI did not
    # provide that device.
    _supplement_gpu_info_map_from_pci(gpu_info_map)

    return gpu_info_map


def _parse_lspci_output(o_id, o_name):
    """
    Parse lspci -Dmmnv and -Dmmv output into device_ids and device_names.
    Format matches host_plugin._parse_pci_device_info for slot/field parsing.
    Returns (device_ids, device_names) where each is slot -> {field: value}.
    """
    device_ids = {}
    device_names = {}
    for part in o_id.split('\n\n'):
        slot = None
        ids = {}
        for line in part.split('\n'):
            if ':' not in line:
                continue
            title = line.split(':', 1)[0].strip()
            content = line.split(':', 1)[1].strip()
            if title == 'Slot':
                slot = content
            elif title in ['Class', 'Vendor', 'Device', 'SVendor', 'SDevice', 'Rev']:
                ids[title] = content
        if slot:
            device_ids[slot] = ids
    for part in o_name.split('\n\n'):
        slot = None
        names = {}
        for line in part.split('\n'):
            if ':' not in line:
                continue
            title = line.split(':', 1)[0].strip()
            content = line.split(':', 1)[1].strip()
            if title == 'Slot':
                slot = content
            elif title in ['Class', 'Vendor', 'Device', 'SVendor', 'SDevice', 'Rev']:
                names[title] = content
        if slot:
            device_names[slot] = names
    return device_ids, device_names


def _supplement_gpu_info_map_from_pci(gpu_info_map):
    """
    Supplement gpu_info_map with PCI devices from lspci for vendors that
    implement get_pci_only_candidates. Used when (1) vendor has no SMI, or
    (2) vendor has SMI but lspci shows more devices (e.g. Alibaba 16 vs ppu-smi 9).
    Only adds entries not already in gpu_info_map (SMI is primary).
    """
    from zstacklib.utils.pci import get_pci_device_ids, get_pci_device_names

    r_id, o_id, _ = get_pci_device_ids()
    r_name, o_name, _ = get_pci_device_names()
    if r_id != 0 or r_name != 0 or not o_id or not o_name:
        return

    try:
        device_ids, device_names = _parse_lspci_output(o_id, o_name)
    except Exception as e:
        logger.debug("Failed to parse lspci for PCI supplement: %s" % str(e))
        return

    try:
        from zstacklib.gpu import get_all_gpu_vendors
        for vendor_class in get_all_gpu_vendors():
            if not getattr(vendor_class, 'get_pci_only_candidates', None):
                continue
            try:
                candidates = vendor_class.get_pci_only_candidates(
                    device_ids, device_names)
            except Exception as e:
                logger.debug("get_pci_only_candidates for %s: %s" %
                             (getattr(vendor_class, 'VENDOR_NAME', ''), str(e)))
                continue
            vendor_name = getattr(vendor_class, 'VENDOR_NAME', '')
            for normalized, info in candidates:
                if not normalized or normalized in gpu_info_map:
                    continue
                info['_vendor'] = vendor_name
                gpu_info_map[normalized] = info
                logger.debug("PCI supplement: added %s (vendor %s)" %
                             (normalized, vendor_name))

        # Annotate all gpu_info_map entries with _deviceId from lspci so
        # enrich_addon_info can propagate productName by device_id match
        from zstacklib.utils.pci import normalize_pci_address
        for slot, ids in device_ids.items():
            norm = normalize_pci_address(slot)
            if norm and norm in gpu_info_map and '_deviceId' not in gpu_info_map[norm]:
                dev_id = (ids.get('Device') or '').strip()
                if dev_id:
                    gpu_info_map[norm]['_deviceId'] = dev_id
    except Exception as e:
        logger.debug("Failed to supplement gpu_info_map from PCI: %s" % str(e))


def enrich_gpu_info_map(gpu_info_map):
    """
    Enrich gpu_info_map with vendor-specific addon fields (productName, opaque, etc.).

    Delegates to zstacklib.gpu.enrich_gpu_info_map which uses each vendor's
    enrich_addon_info hook.

    Args:
        gpu_info_map: dict from get_all_gpu_infos_by_pci(); mutated in place
    """
    from zstacklib.gpu import enrich_gpu_info_map as _enrich
    _enrich(gpu_info_map)


def get_metrics(pci_address=None, pci_device=None, vendor_name=None):
    """
    Collect GPU metrics (for Prometheus)

    Args:
        pci_address: PCI address
        pci_device: PciDeviceTO object
        vendor_name: VendorEnum value

    Returns:
        dict: GPU metrics dictionary, returns None on failure
    """
    # Similar implementation to get_info, but collects metrics
    # Simplified implementation, returns None for now
    return None


def get_all_metrics():
    """
    Collect metrics for all GPUs

    Returns:
        list: List of GPU metrics dictionaries
    """
    results = []

    try:
        from zstacklib.gpu import get_all_gpu_vendors
        for vendor_class in get_all_gpu_vendors():
            if not vendor_class.is_available():
                continue
            metrics_list = vendor_class.collect_metrics()
            for metrics in metrics_list:
                result = {
                    "pci_address": metrics.pci_address,
                    "serial_number": metrics.serial_number,
                    "utilization": metrics.utilization,
                    "memory_utilization": metrics.memory_utilization,
                    "temperature": metrics.temperature,
                    "power_draw": metrics.power_draw,
                    "fan_speed": metrics.fan_speed,
                    "pcie_tx_bytes": metrics.pcie_tx_bytes,
                    "pcie_rx_bytes": metrics.pcie_rx_bytes,
                }
                result.update(metrics.extra)
                results.append(result)
    except Exception as e:
        logger.debug("Failed to collect metrics via plugin: %s" % str(e))

    return results


def _enrich_gpu_pci_device_dependencies(pci_devices, context):
    from zstacklib.gpu import enrich_pci_device_dependencies
    enrich_pci_device_dependencies(pci_devices, context.gpu_info_map)


def _gpu_device_prepare(context):
    """
    GPU device ops preparation hook (Linux kernel style).

    Similar to driver initialization in Linux kernel, this is called once before
    processing devices to batch collect and enrich GPU info map.
    This avoids repeated queries and allows other device ops (e.g., sriov) to use the data.

    Args:
        context: PciDeviceProcessingContext object

    Returns:
        callable or None: Post-prepare hook (device_list, context) -> None, or None
    """
    # Batch collect GPU info
    gpu_info_map = get_all_gpu_infos_by_pci()

    # Batch enrich with vendor-specific info (productName, etc.)
    enrich_gpu_info_map(gpu_info_map)

    # Store in context for use by device ops and other components (e.g., sriov detection)
    context.gpu_info_map = gpu_info_map

    return _enrich_gpu_pci_device_dependencies


# Register GPU device operations on module import (Linux kernel style)
# Similar to pci_register_driver() in Linux kernel, this registers GPU device ops
# This allows the PCI device framework to automatically probe and init GPU devices
gpu_device_ops = pci.PciDeviceOps(
    # Probe function: matches GPU devices (like pci_driver.id_table)
    probe=_gpu_device_matcher,
    # Init function: processes GPU devices (like pci_driver.probe)
    init=_gpu_device_processor,
    # Prepare hook: batch preparation (like driver init)
    prepare=_gpu_device_prepare
)
pci.pci_register_device_ops(gpu_device_ops)

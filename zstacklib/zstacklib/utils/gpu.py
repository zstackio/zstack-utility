import threading

from zstacklib.utils import thread
from zstacklib.utils.bash import *
from enum import Enum
import json

from zstacklib.utils.pci import VendorEnum
from zstacklib.utils.qga import VmQga

logger = log.get_logger(__name__)


class VmGpuStatus(Enum):
    NOT_EXIST = "not_exist"
    CRITICAL_FAULT = "critical"
    NOMINAL = "nominal"


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
        logger.info("no need to shutdown nvidia-persistenced for vm %s, it is not running" % vm_uuid)
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
    logger.warn("No hook registered for vendor: {0}, do nothing".format(vendor))
    return 0, None


# def pre_detach_from_host(vendor):
#     """Execute pre-detach-from-host hook for specific vendor"""
#     if vendor in _pre_detach_from_host_hooks:
#         return _pre_detach_from_host_hooks[vendor]()
#     logger.warn("No hook registered for vendor: {0}, do nothing".format(vendor))
#     return 0, None


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
        gpu_info_json = json.loads(output.strip())
        for card_name, card_data in list(gpu_info_json.items()):
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
        gpu_info_json = json.loads(output)
        for card_name, card_data in list(gpu_info_json.items()):
            gpuinfo = {}
            pci_device_address = card_data['PCI Bus'].lower()
            if len(pci_device_address.split(':')[0]) == 8:
                pci_device_address = pci_device_address[4:].lower()

            gpuinfo["pciAddress"] = pci_device_address
            gpuinfo["memory"] = card_data['Available memory size (MiB)'] + " MiB"
            gpuinfo["power"] = card_data['Max Graphics Package Power (W)']
            gpuinfo["serialNumber"] = card_data['Serial Number']
            gpuinfos.append(gpuinfo)
    except  Exception as e:
        logger.error("haiguang query gpu is error, %s " % e)

    return gpuinfos


def get_huawei_npu_id(npu_id_output):
    npu_ids = []
    for line in npu_id_output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "NPU ID" in line:
            npu_ids.append(line.split(":")[1].strip())
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
            gpuinfo["pciAddress"] = "{}:{}:{}.{}".format(domain, bus, dev_id, func)
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
    cmd = "npu-smi info -t board -i {0};npu-smi info -i {0} -t memory;npu-smi info -t power -i {0}".format(npu_id)
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
                netmask_match_alt = re.search(r'Netmask:\s+(\d+\.\d+\.\d+\.\d+)', o)
                if netmask_match_alt:
                    netmask = netmask_match_alt.group(1)

        # Use fallback IP if no IP found
        if not ip:
            logger.warning("Could not retrieve IP for NPU ID %s, using default format" % npu_id)
            ip = "10.20.0.%s" % (int(npu_id) + 2)
        if not netmask:
            logger.warning("Could not retrieve netmask for NPU ID %s, using default" % npu_id)
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
    Check whether a Huawei NPU is isolated using `npu-smi info -t hccs`.
    Return True when health status is not OK. Do not inspect lane majority.
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
        if r != 0 or not o:
            logger.warning("failed to run '%s' for NPU %s: %s" % (cmd, npu_id, e))
            return False

        for line in o.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("hccs health status"):
                parts = line.split(":", 1)
                status = parts[1].strip().upper() if len(parts) > 1 else ""
                if status != "OK":
                    logger.debug("NPU %s health status is %s, treating as isolated" % (npu_id, status))
                    return True
                return False

        logger.debug("NPU %s health status not found in output, treating as not isolated" % npu_id)
        return False

    except Exception as ex:
        logger.warning("failed to check NPU %s isolation status: %s" % (npu_id, str(ex)))
        return False


def is_valid_video_controller(device):
    invalid_keywords = {"iBMC"}
    return all(keyword not in device for keyword in invalid_keywords)


def is_valid_co_processor(vendor):
    return vendor in [VendorEnum.HAIGUANG]


def get_vastai_type():
    r, o, e = bash_roe("lspci | grep -E 'Vastai|1ec6'")
    if r != 0:
        return None

    first_line = o.split('\n')[0]
    if "3D controller" in first_line:
        return "3D"
    elif "Processing accelerators" in first_line:
        return "AI"
    return None


def is_valid_processing_accelerator(device):
    valid_keywords = {"Device", "SV100", "MI308X", "S60"}
    return any(keyword in device for keyword in valid_keywords)


def get_enflame_gpu_info_cmd():
    return "efsmi -q"


def post_process_enflame_gpu_device(to):
    to.virtStatus = "UNVIRTUALIZABLE"


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
            logger.debug('nvidia-persistenced stopped, will retry in next cycle')
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
            logger.warning('nvidia-persistenced did not appear after start attempt')
            return False


def start_nvidia_persistenced_monitor(poll_interval=60 * 2, stop_event=None):
    """Monitor nvidia-persistenced and restart it if it dies while GPU exists."""
    logger.info("start_nvidia_persistenced_monitor: starting monitor (interval=%s)" % poll_interval)
    if stop_event is None:
        stop_event = threading.Event()

    while not stop_event.is_set():
        if not has_nvidia_gpu():
            stop_event.wait(poll_interval)
            continue

        r = ensure_nvidia_persistenced_once()
        if not r:
            logger.warning("nvidia-persistenced not running and could not be started")

        stop_event.wait(poll_interval)


def watch_and_ensure_nvidia_persistenced(poll_interval=30, stop_event=None):
    """Watch for GPUs appearing later. Once detected, ensure persistenced and start monitor, then exit."""
    logger.info("watch_and_ensure_nvidia_persistenced: watching for NVIDIA GPU (interval=%s)" % poll_interval)
    if stop_event is None:
        stop_event = threading.Event()

    while not stop_event.is_set():
        if has_nvidia_gpu():
            ensure_nvidia_persistenced_once()
            thread.ThreadFacade.run_in_thread(start_nvidia_persistenced_monitor, [poll_interval, stop_event])
            return

        stop_event.wait(poll_interval)

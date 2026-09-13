import json

from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class VendorEnum:
    INTEL = "Intel"
    AMD = "AMD"
    NVIDIA = "NVIDIA"
    HAIGUANG = "Haiguang"
    HUAWEI = "Huawei"
    TIANSHU = "TianShu"
    ENFLAME = "Enflame"


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
            pci_device_address = card_data['PCI Bus'].lower()
            if len(pci_device_address.split(':')[0]) == 8:
                pci_device_address = pci_device_address[4:].lower()

            gpuinfo["pciAddress"] = pci_device_address
            gpuinfo["memory"] = card_data['VRAM Total Memory (B)']
            gpuinfo["power"] = card_data['Average Graphics Package Power (W)']
            gpuinfo["serialNumber"] = card_data['Serial Number']
            gpuinfos.append(gpuinfo)
    except Exception as e:
        LOG.error("amd query gpu is error, %s " % e)

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
    except Exception as e:
        LOG.error("haiguang query gpu is error, %s " % e)

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

    # Do not pass an empty pseudo-device to PCI matching when board output is
    # truncated or otherwise malformed.
    if gpuinfo.get("pciAddress"):
        gpuinfos.append(gpuinfo)
    return gpuinfos


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


def get_huawei_gpu_npu_id_cmd():
    return "npu-smi info -l"


def get_huawei_gpu_basic_info_cmd(npu_id, iswindows=False):
    cmd = "npu-smi info -t board -i %s;npu-smi info -i %s -t memory" % (npu_id, npu_id)
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_huawei_gpu_product_name_cmd(npu_id, iswindows=False):
    cmd = "npu-smi info -t product -i {0}".format(npu_id)
    if iswindows:
        cmd = cmd.replace(" ", "|")
    return cmd


def get_huawei_product_type(output):
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Product Type" in line:
            return line.split(":")[1].strip()
    return None


def get_enflame_gpu_info_cmd():
    return "efsmi -q"


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


def is_valid_processing_accelerator(device):
    valid_keywords = {"Device", "SV100", "MI308X", "S60"}
    return any(keyword in device for keyword in valid_keywords)

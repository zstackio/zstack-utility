
import json

from zstacklib.utils import log

logger = log.get_logger(__name__)


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
        for card_name, card_data in gpu_info_json.items():
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
        logger.error("amd query gpu is error, %s " % e)

    return gpuinfos


def parse_hy_gpu_output(output):
    gpuinfos = []
    try:
        gpu_info_json = json.loads(output)
        for card_name, card_data in gpu_info_json.items():
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
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if "Serial Number" in line:
            gpuinfo["serialNumber"] = line.split(":")[1].strip()
        elif "PCIe Bus Info" in line:
            gpuinfo["pciAddress"] = line.partition(": ")[-1].strip().lower()
        elif "DDR Capacity(MB)" in line or "HBM Capacity" in line:
            memory_value = int(line.split(":")[1].strip().split()[0])
            total_memory += memory_value
        elif "Power Dissipation" in line or "Real-time Power(W)" in line:
            gpuinfo["power"] = line.split(":")[1].strip()

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
            elif key == "Mem Size":
                gpuinfo["memory"] = value
            elif key == "Mem Usage":
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


def is_hygon_gpu_cmd(pci_addr):
    cmd = "hy-smi --showbus | grep {0}".format(pci_addr)
    return cmd


def reload_hygon_gpu_driver_cmd():
    cmd = "hy-smi --unloaddriver && hy-smi --loaddriver"
    return cmd


def get_enflame_gpu_info_cmd():
    return "efsmi -q"


def post_process_enflame_gpu_device(to):
    to.virtStatus = "UNVIRTUALIZABLE"


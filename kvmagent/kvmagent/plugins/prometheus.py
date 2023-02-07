import os.path
import pyudev       # installed by ansible
import threading

import typing
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY
import psutil

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import lvm
from zstacklib.utils import misc
from zstacklib.utils import thread
from zstacklib.utils.bash import *
from zstacklib.utils.ip import get_host_physicl_nics
from zstacklib.utils.ip import get_nic_supported_max_speed

logger = log.get_logger(__name__)
collector_dict = {}  # type: Dict[str, threading.Thread]
latest_collect_result = {}
collectResultLock = threading.RLock()
QEMU_CMD = os.path.basename(kvmagent.get_qemu_path())
ALARM_CONFIG = None
disk_list_record = None
cpu_status_abnormal_list_record = set()
memory_status_abnormal_list_record = set()
fan_status_abnormal_list_record = set()
disk_status_abnormal_list_record = {}


def read_number(fname):
    res = linux.read_file(fname)
    return 0 if not res else int(res)


@thread.AsyncThread
def send_cpu_status_alarm_to_mn(cpu_id, status):
    class PhysicalCpuStatusAlarm(object):
        def __init__(self):
            self.status = None
            self.cpuName = None
            self.host = None
    
    if ALARM_CONFIG is None:
        return
    
    url = ALARM_CONFIG.get(kvmagent.SEND_COMMAND_URL)
    if not url:
        logger.warn(
            "cannot find SEND_COMMAND_URL, unable to transmit physical cpu status alarm info to management node")
        return
    
    global cpu_status_abnormal_list_record
    if cpu_id not in cpu_status_abnormal_list_record:
        physical_cpu_status_alarm = PhysicalCpuStatusAlarm()
        physical_cpu_status_alarm.host = ALARM_CONFIG.get(kvmagent.HOST_UUID)
        physical_cpu_status_alarm.cpuName = cpu_id
        physical_cpu_status_alarm.status = status
        http.json_dump_post(url, physical_cpu_status_alarm, {'commandpath': '/host/physical/cpu/status/alarm'})
        cpu_status_abnormal_list_record.add(cpu_id)


@thread.AsyncThread
def send_physical_memory_status_alarm_to_mn(locator, status):
    class PhysicalMemoryStatusAlarm(object):
        def __init__(self):
            self.host = None
            self.locator = None
            self.status = None
    
    if ALARM_CONFIG is None:
        return
    
    url = ALARM_CONFIG.get(kvmagent.SEND_COMMAND_URL)
    if not url:
        logger.warn(
            "cannot find SEND_COMMAND_URL, unable to transmit physical memory status alarm info to management node")
        return
    
    global memory_status_abnormal_list_record
    if locator not in memory_status_abnormal_list_record:
        physical_memory_status_alarm = PhysicalMemoryStatusAlarm()
        physical_memory_status_alarm.host = ALARM_CONFIG.get(kvmagent.HOST_UUID)
        physical_memory_status_alarm.locator = locator
        physical_memory_status_alarm.status = status
        http.json_dump_post(url, physical_memory_status_alarm, {'commandpath': '/host/physical/memory/status/alarm'})
        memory_status_abnormal_list_record.add(locator)


@thread.AsyncThread
def send_physical_fan_status_alarm_to_mn(fan_name, status):
    class PhysicalFanStatusAlarm(object):
        def __init__(self):
            self.host = None
            self.fan_name = None
            self.status = None
    
    if ALARM_CONFIG is None:
        return
    
    url = ALARM_CONFIG.get(kvmagent.SEND_COMMAND_URL)
    if not url:
        logger.warn(
            "cannot find SEND_COMMAND_URL, unable to transmit physical fan status alarm info to management node")
        return

    global fan_status_abnormal_list_record
    if fan_name not in fan_status_abnormal_list_record:
        physical_fan_status_alarm = PhysicalFanStatusAlarm()
        physical_fan_status_alarm.host = ALARM_CONFIG.get(kvmagent.HOST_UUID)
        physical_fan_status_alarm.fan_name = fan_name
        physical_fan_status_alarm.status = status
        http.json_dump_post(url, physical_fan_status_alarm, {'commandpath': '/host/physical/fan/status/alarm'})
        fan_status_abnormal_list_record.add(fan_name)


@thread.AsyncThread
def send_physical_disk_status_alarm_to_mn(serial_number, slot_number, enclosure_device_id, drive_state):
    class PhysicalDiskStatusAlarm(object):
        def __init__(self):
            self.host = None
            self.slot_number = None
            self.enclosure_device_id = None
            self.drive_state = None
            self.serial_number = None
    
    if ALARM_CONFIG is None:
        return
    
    url = ALARM_CONFIG.get(kvmagent.SEND_COMMAND_URL)
    if not url:
        logger.warn(
            "cannot find SEND_COMMAND_URL, unable to transmit physical disk status alarm info to management node")
        return

    global disk_status_abnormal_list_record
    if (serial_number not in disk_status_abnormal_list_record.keys()) \
            or (serial_number in disk_status_abnormal_list_record.keys()
                and disk_status_abnormal_list_record[serial_number] != drive_state):
        physical_disk_status_alarm = PhysicalDiskStatusAlarm()
        physical_disk_status_alarm.host = ALARM_CONFIG.get(kvmagent.HOST_UUID)
        physical_disk_status_alarm.slot_number = slot_number
        physical_disk_status_alarm.enclosure_device_id = enclosure_device_id
        physical_disk_status_alarm.drive_state = drive_state
        physical_disk_status_alarm.serial_number = serial_number
        http.json_dump_post(url, physical_disk_status_alarm, {'commandpath': '/host/physical/disk/status/alarm'})
        disk_status_abnormal_list_record[serial_number] = drive_state


def send_physical_disk_insert_alarm_to_mn(serial_number, slot):
    class PhysicalDiskInsertAlarm(object):
        def __init__(self):
            self.host = None
            self.serial_number = None
            self.slot_number = None
            self.enclosure_device_id = None
            
    if ALARM_CONFIG is None:
        return
   
    url = ALARM_CONFIG.get(kvmagent.SEND_COMMAND_URL)
    if not url:
        logger.warn(
            "cannot find SEND_COMMAND_URL, unable to transmit physical disk insert alarm info to management node")
        return

    physical_disk_insert_alarm = PhysicalDiskInsertAlarm()
    physical_disk_insert_alarm.host = ALARM_CONFIG.get(kvmagent.HOST_UUID)
    physical_disk_insert_alarm.serial_number = serial_number
    physical_disk_insert_alarm.enclosure_device_id = slot.split("-")[0]
    physical_disk_insert_alarm.slot_number = slot.split("-")[1]
    http.json_dump_post(url, physical_disk_insert_alarm, {'commandpath': '/host/physical/disk/insert/alarm'})


def send_physical_disk_remove_alarm_to_mn(serial_number, slot):
    class PhysicalDiskRemoveAlarm(object):
        def __init__(self):
            self.host = None
            self.serial_number = None
            self.slot_number = None
            self.enclosure_device_id = None
    
    if ALARM_CONFIG is None:
        return
    
    url = ALARM_CONFIG.get(kvmagent.SEND_COMMAND_URL)
    if not url:
        logger.warn(
            "cannot find SEND_COMMAND_URL, unable to transmit physical disk remove alarm info to management node")
        return

    physical_disk_remove_alarm = PhysicalDiskRemoveAlarm()
    physical_disk_remove_alarm.host = ALARM_CONFIG.get(kvmagent.HOST_UUID)
    physical_disk_remove_alarm.serial_number = serial_number
    physical_disk_remove_alarm.enclosure_device_id = slot.split("-")[0]
    physical_disk_remove_alarm.slot_number = slot.split("-")[1]
    http.json_dump_post(url, physical_disk_remove_alarm, {'commandpath': '/host/physical/disk/remove/alarm'})


def collect_memory_locator():
    memory_locator_list = []
    r, infos = bash_ro("dmidecode -q -t memory | grep -E 'Serial Number|Locator'")
    if r != 0:
        return memory_locator_list
    locator = "unknown"
    for line in infos.splitlines():
        k = line.split(":")[0].strip()
        v = ":".join(line.split(":")[1:]).strip()
        if "Locator" == k:
            locator = v
        elif "Serial Number" == k:
            if v.lower() == "no dimm" or v.lower() == "unknown" or v == "":
                continue
            memory_locator_list.append(locator)

    return memory_locator_list


@thread.AsyncThread
def check_disk_insert_and_remove(disk_list):
    global disk_list_record
    if disk_list_record is None:
        disk_list_record = disk_list
        return
    
    if cmp(disk_list_record, disk_list) == 0:
        return
    
    # check disk insert
    for sn in disk_list.keys():
        if sn not in disk_list_record.keys():
            send_physical_disk_insert_alarm_to_mn(sn, disk_list[sn])
    
    # check disk remove
    for sn in disk_list_record.keys():
        if sn not in disk_list.keys():
            send_physical_disk_remove_alarm_to_mn(sn, disk_list_record[sn])
            
    disk_list_record = disk_list


def collect_host_network_statistics():

    all_eths = os.listdir("/sys/class/net/")
    virtual_eths = os.listdir("/sys/devices/virtual/net/")

    interfaces = []
    for eth in all_eths:
        eth = eth.strip(' \t\n\r')
        if eth in virtual_eths: continue
        if eth == 'bonding_masters':
            continue
        elif not eth:
            continue
        else:
            interfaces.append(eth)

    all_in_bytes = 0
    all_in_packets = 0
    all_in_errors = 0
    all_out_bytes = 0
    all_out_packets = 0
    all_out_errors = 0
    for intf in interfaces:
        all_in_bytes += read_number("/sys/class/net/{}/statistics/rx_bytes".format(intf))
        all_in_packets += read_number("/sys/class/net/{}/statistics/rx_packets".format(intf))
        all_in_errors += read_number("/sys/class/net/{}/statistics/rx_errors".format(intf))
        all_out_bytes += read_number("/sys/class/net/{}/statistics/tx_bytes".format(intf))
        all_out_packets += read_number("/sys/class/net/{}/statistics/tx_packets".format(intf))
        all_out_errors += read_number("/sys/class/net/{}/statistics/tx_errors".format(intf))

    metrics = {
        'host_network_all_in_bytes': GaugeMetricFamily('host_network_all_in_bytes',
                                                       'Host all inbound traffic in bytes'),
        'host_network_all_in_packages': GaugeMetricFamily('host_network_all_in_packages',
                                                          'Host all inbound traffic in packages'),
        'host_network_all_in_errors': GaugeMetricFamily('host_network_all_in_errors',
                                                        'Host all inbound traffic errors'),
        'host_network_all_out_bytes': GaugeMetricFamily('host_network_all_out_bytes',
                                                        'Host all outbound traffic in bytes'),
        'host_network_all_out_packages': GaugeMetricFamily('host_network_all_out_packages',
                                                           'Host all outbound traffic in packages'),
        'host_network_all_out_errors': GaugeMetricFamily('host_network_all_out_errors',
                                                         'Host all outbound traffic errors'),
    }

    metrics['host_network_all_in_bytes'].add_metric([], float(all_in_bytes))
    metrics['host_network_all_in_packages'].add_metric([], float(all_in_packets))
    metrics['host_network_all_in_errors'].add_metric([], float(all_in_errors))
    metrics['host_network_all_out_bytes'].add_metric([], float(all_out_bytes))
    metrics['host_network_all_out_packages'].add_metric([], float(all_out_packets))
    metrics['host_network_all_out_errors'].add_metric([], float(all_out_errors))

    return metrics.values()


collect_node_disk_capacity_last_time = None
collect_node_disk_capacity_last_result = None


def collect_host_capacity_statistics():
    default_zstack_path = '/usr/local/zstack/apache-tomcat/webapps/zstack'

    zstack_env_path = os.environ.get('ZSTACK_HOME', None)
    if zstack_env_path and zstack_env_path != default_zstack_path:
        default_zstack_path = zstack_env_path

    zstack_dir = ['/var/lib/zstack', '%s/../../../' % default_zstack_path, '/opt/zstack-dvd/',
                  '/var/log/zstack', '/var/lib/mysql', '/var/lib/libvirt', '/tmp/zstack']

    metrics = {
        'zstack_used_capacity_in_bytes': GaugeMetricFamily('zstack_used_capacity_in_bytes',
                                                           'ZStack used capacity in bytes'),
        'block_device_used_capacity_in_bytes': GaugeMetricFamily('block_device_used_capacity_in_bytes',
                                                                 'block device used capacity in bytes', None, ['disk']),
        'block_device_used_capacity_in_percent': GaugeMetricFamily('block_device_used_capacity_in_percent',
                                                                 'block device used capacity in percent', None, ['disk'])
    }

    global collect_node_disk_capacity_last_time
    global collect_node_disk_capacity_last_result

    if collect_node_disk_capacity_last_time is None or (time.time() - collect_node_disk_capacity_last_time) >= 60:
        collect_node_disk_capacity_last_time = time.time()
    elif (time.time() - collect_node_disk_capacity_last_time) < 60 and collect_node_disk_capacity_last_result is not None:
        return collect_node_disk_capacity_last_result

    zstack_used_capacity = 0
    for d in zstack_dir:
        if not os.path.exists(d):
            continue
        res = bash_o("du -bs %s" % d) # split()[0] is far cheaper than awk
        zstack_used_capacity += int(res.split()[0])

    metrics['zstack_used_capacity_in_bytes'].add_metric([], float(zstack_used_capacity))

    r1, dfInfo = bash_ro("df | awk '{print $3,$6}' | tail -n +2")
    r2, lbkInfo = bash_ro("lsblk -db -oname,size | tail -n +2")
    if r1 != 0 or r2 != 0:
        collect_node_disk_capacity_last_result = metrics.values()
        return collect_node_disk_capacity_last_result

    df_map = {}
    for df in dfInfo.splitlines():
        df_size = long(df.split()[0].strip()) * 1024
        df_name = df.split()[-1].strip()
        df_map[df_name] = df_size
    
    for lbk in lbkInfo.splitlines():
        lbk_name = lbk.split()[0].strip()
        lbk_size = long(lbk.split()[-1].strip())
        
        lbk_used_size = 0L
        ds = bash_o("lsblk -lb /dev/%s -omountpoint |awk '{if(length($1)>0) print $1}' | tail -n +2" % lbk_name)
        for d in ds.splitlines():
            if df_map.get(d.strip(), None) != None:
                lbk_used_size += df_map.get(d.strip())

        metrics['block_device_used_capacity_in_bytes'].add_metric([lbk_name], float(lbk_used_size))
        metrics['block_device_used_capacity_in_percent'].add_metric([lbk_name], float(lbk_used_size * 100) / lbk_size)
        
    collect_node_disk_capacity_last_result = metrics.values()
    return collect_node_disk_capacity_last_result


def collect_lvm_capacity_statistics():
    metrics = {
        'vg_size': GaugeMetricFamily('vg_size',
                                     'volume group size', None, ['vg_name']),
        'vg_avail': GaugeMetricFamily('vg_avail',
                                      'volume group and thin pool free size', None, ['vg_name']),
    }

    if linux.file_has_config("/etc/multipath/wwids"):
        linux.set_fail_if_no_path()

    vg_sizes = lvm.get_all_vg_size()
    for name, tpl in vg_sizes.items():
        metrics['vg_size'].add_metric([name], float(tpl[0]))
        metrics['vg_avail'].add_metric([name], float(tpl[1]))

    return metrics.values()


def convert_raid_state_to_int(state):
    """

    :type state: str
    """
    state = state.lower()
    if "optimal" in state:
        return 0
    elif "degraded" in state or "interim recovery" in state:
        return 5
    elif "ready for recovery" in state or "rebuilding" in state:
        return 10
    else:
        return 100


def convert_disk_state_to_int(state):
    """

    :type state: str
    """
    state = state.lower()
    if "online" in state or "jbod" in state or "ready" in state or "optimal" in state or "hot-spare" in state or "hot spare" in state or "raw" in state:
        return 0
    elif "rebuild" in state:
        return 5
    elif "failed" in state or "offline" in state:
        return 10
    else:
        return 100


def collect_raid_state():
    metrics = {
        'raid_state': GaugeMetricFamily('raid_state',
                                        'raid state', None, ['target_id']),
        'physical_disk_state': GaugeMetricFamily('physical_disk_state',
                                                 'physical disk state', None,
                                                 ['slot_number', 'disk_group']),
    }
    
    r, o = bash_ro("sas3ircu list | grep -A 8 'Index' | awk '{print $1}'")
    if r == 0 and o.strip() != "":
        return collect_sas_raid_state(metrics, o)

    r, o = bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -LDInfo -LALL -aAll | grep -E 'Target Id|State'")
    if r == 0 and o.strip() != "":
        return collect_mega_raid_state(metrics, o)

    r, o = bash_ro("arcconf list | grep -A 8 'Controller ID' | awk '{print $2}'")
    if r == 0 and o.strip() != "":
        return collect_arcconf_raid_state(metrics, o)
    
    return metrics.values()


def collect_arcconf_raid_state(metrics, infos):
    disk_list = {}
    for line in infos.splitlines():
        if line.strip() == "":
            continue
        adapter = line.split(":")[0].strip()
        if not adapter.isdigit():
            continue
        
        r, device_info = bash_ro("arcconf getconfig %s AL" % adapter)
        if r != 0 or device_info.strip() == "":
            continue
        
        # Contain at least raid controller into and a hardDisk info
        device_arr = device_info.split("Device #")
        if len(device_arr) < 3:
            continue
        
        target_id = "unknown"
        for l in device_arr[0].splitlines():
            if l.strip() == "":
                continue
            if "Logical Device number" in l:
                target_id = l.strip().split(" ")[-1]
            elif "Status of Logical Device" in l and target_id != "unknown":
                state = l.strip().split(":")[-1].strip()
                metrics['raid_state'].add_metric([target_id], convert_raid_state_to_int(state))
        
        for infos in device_arr[1:]:
            drive_state = serial_number = "unknown"
            for l in infos.splitlines():
                if l.strip() == "":
                    continue
                k = l.split(":")[0].strip().lower()
                v = ":".join(l.split(":")[1:]).strip()
                if "state" == k:
                    drive_state = v.split(" ")[0].strip()
                elif "serial number" in k:
                    serial_number = v
                elif "reported location" in k and "Enclosure" in v and "Slot" in v and drive_state != "unknown":
                    enclosure_device_id = v.split(",")[0].split(" ")[1].strip()
                    slot_number = v.split("Slot ")[1].split("(")[0].strip()
                    disk_status = convert_disk_state_to_int(drive_state)
                    metrics['physical_disk_state'].add_metric([slot_number, enclosure_device_id], disk_status)
                    disk_list[serial_number] = "%s-%s" % (enclosure_device_id, slot_number)
                    if disk_status == 0 and (slot_number in disk_status_abnormal_list_record.keys()):
                        disk_status_abnormal_list_record.pop(slot_number)
                    elif disk_status != 0:
                        send_physical_disk_status_alarm_to_mn(serial_number, slot_number, enclosure_device_id, drive_state)
     
    check_disk_insert_and_remove(disk_list)
    return metrics.values()


def collect_sas_raid_state(metrics, infos):
    disk_list = {}
    for line in infos.splitlines():
        if not line.strip().isdigit():
            continue
        raid_info = bash_o("sas3ircu %s status | grep -E 'Volume ID|Volume state'" % line.strip())
        target_id = "unknown"
        for info in raid_info.splitlines():
            if "Volume ID" in info:
                target_id = info.strip().split(":")[-1].strip()
            else:
                state = info.strip().split(":")[-1].strip()
                if "Inactive" in state:
                    continue
                metrics['raid_state'].add_metric([target_id], convert_raid_state_to_int(state))
        
        disk_info = bash_o("sas3ircu %s display | grep -E 'Enclosure #|Slot #|State|Serial No|Drive Type'" % line.strip())
        enclosure_device_id = slot_number = state = serial_number = "unknown"
        for info in disk_info.splitlines():
            k = info.split(":")[0].strip()
            v = info.split(":")[1].strip()
            if "Enclosure #" == k:
                enclosure_device_id = v
            elif "Slot #" == k:
                slot_number = v
            elif "State" == k:
                state = v.split(" ")[0].strip()
            elif "Serial No" == k:
                serial_number = v
            elif "Drive Type" == k:
                drive_status = convert_disk_state_to_int(state)
                metrics['physical_disk_state'].add_metric([slot_number, enclosure_device_id], drive_status)
                disk_list[serial_number] = "%s-%s" % (enclosure_device_id, slot_number)
                if drive_status == 0 and (slot_number in disk_status_abnormal_list_record.keys()):
                    disk_status_abnormal_list_record.pop(slot_number)
                elif drive_status != 0:
                    send_physical_disk_status_alarm_to_mn(serial_number, slot_number, enclosure_device_id, state)

    check_disk_insert_and_remove(disk_list)
    return metrics.values()


def collect_mega_raid_state(metrics, infos):
    global disk_status_abnormal_list_record
    disk_list = {}
    raid_info = infos.strip().splitlines()
    target_id = state = "unknown"
    for info in raid_info:
        if "Target Id" in info:
            target_id = info.strip().strip(")").split(" ")[-1]
        else:
            state = info.strip().split(" ")[-1]
            metrics['raid_state'].add_metric([target_id], convert_raid_state_to_int(state))
    
    disk_info = bash_o(
        "/opt/MegaRAID/MegaCli/MegaCli64 -PDList -aAll | grep -E 'Enclosure Device ID|Slot Number|Firmware state|Inquiry Data|Drive has flagged'").strip().splitlines()
    enclosure_device_id = slot_number = serial_number = state = "unknown"
    for info in disk_info:
        k = info.split(":")[0].strip()
        v = info.split(":")[1].strip()
        if "Enclosure Device ID" in k:
            enclosure_device_id = v
        elif "Slot Number" in k:
            slot_number = v
        elif "Firmware state" in k:
            state = v
        elif "Inquiry Data" in k:
            serial_number = v.split()[0].strip()
        elif "Drive has flagged" in k:
            drive_status = convert_disk_state_to_int(state)
            metrics['physical_disk_state'].add_metric([slot_number, enclosure_device_id], drive_status)
            disk_list[serial_number] = "%s-%s" % (enclosure_device_id, slot_number)
            if drive_status == 0 and (slot_number in disk_status_abnormal_list_record.keys()):
                disk_status_abnormal_list_record.pop(slot_number)
            elif drive_status != 0:
                send_physical_disk_status_alarm_to_mn(serial_number, slot_number, enclosure_device_id, state)

    check_disk_insert_and_remove(disk_list)
    return metrics.values()


def collect_mini_raid_state():
    metrics = {
        'raid_state': GaugeMetricFamily('raid_state',
                                        'raid state', None, ['target_id']),
        'physical_disk_state': GaugeMetricFamily('physical_disk_state',
                                                 'physical disk state', None,
                                                 ['slot_number', 'disk_group']),
        'physical_disk_temperature': GaugeMetricFamily('physical_disk_temperature',
                                                       'physical disk temperature', None,
                                                       ['slot_number', 'disk_group']),
    }
    if bash_r("/opt/MegaRAID/MegaCli/MegaCli64 -LDInfo -LALL -aAll") != 0:
        return metrics.values()
    
    raid_info = bash_o(
        "/opt/MegaRAID/MegaCli/MegaCli64 -LDInfo -LALL -aAll | grep -E 'Target Id|State'").strip().splitlines()
    target_id = state = "unknown"
    for info in raid_info:
        if "Target Id" in info:
            target_id = info.strip().strip(")").split(" ")[-1]
        else:
            state = info.strip().split(" ")[-1]
            metrics['raid_state'].add_metric([target_id], convert_raid_state_to_int(state))

    disk_info = bash_o(
        "/opt/MegaRAID/MegaCli/MegaCli64 -PDList -aAll | grep -E 'Slot Number|DiskGroup|Firmware state|Drive Temperature'").strip().splitlines()
    slot_number = state = disk_group = "unknown"
    for info in disk_info:
        if "Slot Number" in info:
            slot_number = info.strip().split(" ")[-1]
        elif "DiskGroup" in info:
            kvs = info.replace("Drive's position: ", "").split(",")
            disk_group = filter(lambda x: "DiskGroup" in x, kvs)[0]
            disk_group = disk_group.split(" ")[-1]
        elif "Drive Temperature" in info:
            temp = info.split(":")[1].split("C")[0]
            metrics['physical_disk_temperature'].add_metric([slot_number, disk_group], int(temp))
        else:
            disk_group = "JBOD" if disk_group == "unknown" and info.count("JBOD") > 0 else disk_group
            disk_group = "unknown" if disk_group is None else disk_group

            state = info.strip().split(":")[-1]
            metrics['physical_disk_state'].add_metric([slot_number, disk_group], convert_disk_state_to_int(state))

    return metrics.values()


def collect_ssd_state():
    metrics = {
        'ssd_life_left': GaugeMetricFamily('ssd_life_left', 'ssd life left', None, ['disk', 'serial_number']),
        'ssd_temperature': GaugeMetricFamily('ssd_temperature', 'ssd temperature', None, ['disk', 'serial_number']),
    }
    
    r, o = bash_ro("lsblk -d -o name,type,rota | grep -w disk | awk '$3 == 0 {print $1}'")  # type: (int, str)
    if r != 0 or o.strip() == "":
        return metrics.values()
    
    for line in o.splitlines():
        disk_name = line.strip()
        r, o = bash_ro("smartctl -i /dev/%s | grep 'Serial Number' | awk '{print $3}'" % disk_name)
        if r != 0 or o.strip() == "":
            continue
        serial_number = o.strip()
        
        if disk_name.startswith('nvme'):
            r, o = bash_ro("smartctl -A /dev/%s | grep -E '^Percentage Used:|^Temperature:'" % disk_name)
            if r != 0 or o.strip() == "":
                continue

            for info in o.splitlines():
                info = info.strip()
                if info.startswith("Percentage Used:") and info.split(":")[1].split("%")[0].strip().isdigit():
                    metrics['ssd_life_left'].add_metric([disk_name, serial_number], float(float(100) - float(info.split(":")[1].split("%")[0].strip())))
                elif info.startswith("Temperature:") and info.split(":")[1].split()[0].strip().isdigit():
                    metrics['ssd_temperature'].add_metric([disk_name, serial_number], float(info.split(":")[1].split()[0].strip()))
        else:
            r, o = bash_ro("smartctl -A /dev/%s | grep -E 'Media_Wearout_Indicator|Temperature_Celsius'" % disk_name)
            if r != 0 or o.strip() == "":
                continue
            for info in o.splitlines():
                info = info.strip()
                if "Media_Wearout_Indicator" in info and info.split()[4].strip().isdigit():
                    metrics['ssd_life_left'].add_metric([disk_name, serial_number], float(info.split()[4].strip()))
                elif "Temperature_Celsius" in info and info.split()[9].strip().isdigit():
                    metrics['ssd_temperature'].add_metric([disk_name, serial_number], float(info.split()[9].strip()))
        
    return metrics.values()


collect_equipment_state_last_time = None
collect_equipment_state_last_result = None


def collect_ipmi_state():
    metrics = {
        'power_supply': GaugeMetricFamily('power_supply',
                                          'power supply', None, ['ps_id']),
        "power_supply_current_output_power": GaugeMetricFamily('power_supply_current_output_power', 'power supply current output power', None, ['ps_id']),
        'ipmi_status': GaugeMetricFamily('ipmi_status', 'ipmi status', None, []),
        "fan_speed_rpm": GaugeMetricFamily('fan_speed_rpm', 'fan speed rpm', None, ['fan_speed_name']),
        "fan_speed_state": GaugeMetricFamily('fan_speed_state', 'fan speed state', None, ['fan_speed_name']),
        "cpu_temperature": GaugeMetricFamily('cpu_temperature', 'cpu temperature', None, ['cpu']),
        "cpu_status": GaugeMetricFamily('cpu_status', 'cpu status', None, ['cpu']),
        "physical_memory_status": GaugeMetricFamily('physical_memory_status', 'physical memory status', None, ['slot_number']),
    }

    global collect_equipment_state_last_time
    global collect_equipment_state_last_result
    global cpu_status_abnormal_list_record
    global memory_status_abnormal_list_record
    global fan_status_abnormal_list_record

    if collect_equipment_state_last_time is None or (time.time() - collect_equipment_state_last_time) >= 25:
        collect_equipment_state_last_time = time.time()
    elif (time.time() - collect_equipment_state_last_time) < 25 and collect_equipment_state_last_result is not None:
        return collect_equipment_state_last_result

    # get ipmi status
    metrics['ipmi_status'].add_metric([], bash_r("ipmitool mc info"))

    # get cpu info
    r, cpu_temps = bash_ro("sensors | awk -F'+' '/Physical id/{print $2}' | grep -oP '\d*\.\d+'")
    if r == 0:
        count = 0
        for temp in cpu_temps.splitlines():
            cpu_id = "CPU" + str(count)
            metrics['cpu_temperature'].add_metric([cpu_id], float(temp.strip()))
            count = count + 1

    r, cpu_infos = bash_ro("hd_ctl -c cpu")
    if r == 0:
        infos = jsonobject.loads(cpu_infos)
        for info in infos:
            cpu_id = "CPU" + info.Processor
            if "populated" in info.Status.lower() and "enabled" in info.Status.lower():
                metrics['cpu_status'].add_metric([cpu_id], 0)
                if cpu_id in cpu_status_abnormal_list_record:
                    cpu_status_abnormal_list_record.remove(cpu_id)
            elif "" == info.Status:
                metrics['cpu_status'].add_metric([cpu_id], 20)
                if cpu_id in cpu_status_abnormal_list_record:
                    cpu_status_abnormal_list_record.remove(cpu_id)
            else:
                metrics['cpu_status'].add_metric([cpu_id], 10)
                send_cpu_status_alarm_to_mn(cpu_id, info.Status)
                
    # get physical memory info
    r, memory_infos = bash_ro("hd_ctl -c memory")
    if r == 0:
        memory_locator_list = collect_memory_locator()
        infos = jsonobject.loads(memory_infos)
        for info in infos:
            slot_number = info.Locator
            if slot_number in memory_locator_list:
                memory_locator_list.remove(slot_number)
            if "ok" == info.State.lower():
                metrics['physical_memory_status'].add_metric([slot_number], 0)
                if slot_number in memory_status_abnormal_list_record:
                    memory_status_abnormal_list_record.remove(slot_number)
            elif "" == info.State:
                metrics['physical_memory_status'].add_metric([slot_number], 20)
                if slot_number in memory_status_abnormal_list_record:
                    memory_status_abnormal_list_record.remove(slot_number)
            else:
                metrics['physical_memory_status'].add_metric([slot_number], 10)
                send_physical_memory_status_alarm_to_mn(slot_number, info.State)
        
        if len(memory_locator_list) != 0:
            for locator in memory_locator_list:
                metrics['physical_memory_status'].add_metric([locator], 10)
                send_physical_memory_status_alarm_to_mn(locator, "unknown")

    # get fan info
    origin_fan_flag = False
    r, fan_infos = bash_ro("hd_ctl -c fan")
    if r == 0:
        infos = jsonobject.loads(fan_infos)
        for info in infos.fan_list:
            fan_name = info.Name
            if fan_name == "":
                origin_fan_flag = True
                break
            if info.Status == "":
                origin_fan_flag = True
                break
            
            fan_rpm = "0" if info.SpeedRPM == "" else info.SpeedRPM
            metrics['fan_speed_rpm'].add_metric([fan_name], float(fan_rpm))
            
            if "ok" == info.Status.lower():
                metrics['fan_speed_state'].add_metric([fan_name], 0)
                if fan_name in fan_status_abnormal_list_record:
                    fan_status_abnormal_list_record.remove(fan_name)
            elif "" == info.Status:
                metrics['fan_speed_state'].add_metric([fan_name], 20)
                if fan_name in fan_status_abnormal_list_record:
                    fan_status_abnormal_list_record.remove(fan_name)
            else:
                metrics['fan_speed_state'].add_metric([fan_name], 10)
                send_physical_fan_status_alarm_to_mn(fan_name, info.Status)
    else:
        origin_fan_flag = True
    
    # get power info
    r, sdr_data = bash_ro("ipmitool sdr elist")
    if r == 0:
        power_list = []
        for line in sdr_data.splitlines():
            info = line.lower().strip()
            if re.match(r"^ps\w*(\ |_)status", info):
                ps_id = info.split("|")[0].strip().split(" ")[0].split("_")[0]
                ps_state = info.split("|")[4].strip()
                if "presence detected" == ps_state:
                    metrics['power_supply'].add_metric([ps_id], 0)
                elif "presence detected" in ps_state and "ac lost" in ps_state:
                    metrics['power_supply'].add_metric([ps_id], 10)
                else:
                    metrics['power_supply'].add_metric([ps_id], 20)
            elif re.match(r"^ps\w*(\ |_)(pin|pout)", info):
                ps_id = info.split("|")[0].strip().split(" ")[0].split("_")[0]
                if "pout" in info and ps_id in power_list:
                    continue
                ps_out_power = info.split("|")[4].strip().lower()
                ps_out_power = float(filter(str.isdigit, ps_out_power)) if bool(re.search(r'\d', ps_out_power)) else float(0)
                metrics['power_supply_current_output_power'].add_metric([ps_id], ps_out_power)
                power_list.append(ps_id)
            elif re.match(r"\w*fan(\w*(_|\ )speed|[a-z0-9]\ *\|)\w*", info):
                if not origin_fan_flag:
                    continue
                if "m2" in info:
                    continue
                fan_rpm = info.split("|")[4].strip()
                if fan_rpm == "" or fan_rpm == "no reading" or fan_rpm == "disabled":
                    continue
                fan_name = info.split("|")[0].strip()
                fan_state = 0 if info.split("|")[2].strip() == "ok" else 10
                fan_rpm = float(filter(str.isdigit, fan_rpm)) if bool(re.search(r'\d', fan_rpm)) else float(0)
                metrics['fan_speed_state'].add_metric([fan_name], fan_state)
                metrics['fan_speed_rpm'].add_metric([fan_name], fan_rpm)
                if fan_state == 0 and fan_name in fan_status_abnormal_list_record:
                    fan_status_abnormal_list_record.remove(fan_name)
                elif fan_state == 10:
                    send_physical_fan_status_alarm_to_mn(fan_name, info.split("|")[2].strip())

    collect_equipment_state_last_result = metrics.values()
    return collect_equipment_state_last_result


def collect_physical_cpu_state():
    metrics = {
        "cpu_temperature": GaugeMetricFamily('cpu_temperature', 'cpu temperature', None, ['cpu']),
        "cpu_status": GaugeMetricFamily('cpu_status', 'cpu status', None, ['cpu']),
    }

    r, cpu_info = bash_ro(
        "ipmitool sdr elist | grep -E -i '^CPU[0-9]*(\ |_)Temp|CPU[0-9]*(\ |_)Status'")  # type: (int, str)
    if r == 0:
        count = 0
        for info in cpu_info.splitlines():
            info = info.strip().lower()
            cpu_id = "CPU" + str(count)
            if "temp" in info:
                cpu_temp = info.split("|")[4].strip()
                metrics['cpu_temperature'].add_metric([cpu_id], float(filter(str.isdigit, cpu_temp)) if bool(re.search(r'\d', cpu_temp)) else float(0))
                count = count + 1

        count = 0
        for info in cpu_info.splitlines():
            info = info.strip().lower()
            cpu_id = "CPU" + str(count)
            if "status" in info:
                cpu_status = info.split("|")[4].strip()
                cpu_status = 0 if "presence detected" == cpu_status else 10
                metrics['cpu_status'].add_metric([cpu_id], float(cpu_status))
                count = count + 1
    
    collect_equipment_state_last_result = metrics.values()
    return collect_equipment_state_last_result


def collect_equipment_state():
    metrics = {
        'power_supply': GaugeMetricFamily('power_supply',
                                          'power supply', None, ['ps_id']),
        'ipmi_status': GaugeMetricFamily('ipmi_status', 'ipmi status', None, []),
    }

    r, ps_info = bash_ro("ipmitool sdr type 'power supply'")  # type: (int, str)
    if r == 0:
        for info in ps_info.splitlines():
            info = info.strip()
            ps_id = info.split("|")[0].strip().split(" ")[0]
            health = 10 if "fail" in info.lower() or "lost" in info.lower() else 0
            metrics['power_supply'].add_metric([ps_id], health)

    metrics['ipmi_status'].add_metric([], bash_r("ipmitool mc info"))
    return metrics.values()


def fetch_vm_qemu_processes():
    processes = []
    for process in psutil.process_iter():
        if process.name() == QEMU_CMD: # /usr/libexec/qemu-kvm
            processes.append(process)
    return processes


def find_vm_uuid_from_vm_qemu_process(process):
    prefix = 'guest='
    suffix = ',debug-threads=on'
    for word in process.cmdline():
        # word like 'guest=707e9d31751e499eb6110cce557b4168,debug-threads=on'
        if word.startswith(prefix) and word.endswith(suffix):
            return word[len(prefix) : len(word) - len(suffix)]
    return None


def collect_vm_statistics():
    metrics = {
        'cpu_occupied_by_vm': GaugeMetricFamily('cpu_occupied_by_vm',
                                     'Percentage of CPU used by vm', None, ['vmUuid'])
    }

    processes = fetch_vm_qemu_processes()
    if len(processes) == 0:
        return metrics.values()

    pid_vm_map = {}
    for process in processes:
        pid_vm_map[str(process.pid)] = find_vm_uuid_from_vm_qemu_process(process)

    def collect(vm_pid_arr):
        vm_pid_arr_str = ','.join(vm_pid_arr)

        r, pid_cpu_usages_str = bash_ro("top -b -n 1 -p %s -w 512" % vm_pid_arr_str)
        if r != 0 or not pid_cpu_usages_str:
            return

        for pid_cpu_usage in pid_cpu_usages_str.splitlines():
            if QEMU_CMD not in pid_cpu_usage:
                continue
            arr = pid_cpu_usage.split()
            pid = arr[0]
            vm_uuid = pid_vm_map[pid]
            cpu_usage = arr[8]
            metrics['cpu_occupied_by_vm'].add_metric([vm_uuid], float(cpu_usage))

    n = 16  # procps/top has '#define MONPIDMAX  20'
    for i in range(0, len(pid_vm_map.keys()), n):
        collect(pid_vm_map.keys()[i:i + n])

    return metrics.values()


# since Cloud 4.5.0, Because GetVmGuestToolsAction calls are too frequent,
# the information about whether pvpanic is configured for VM
# will flow to the management node through the monitoring data.
# @see ZSTAC-49036
def collect_vm_pvpanic_enable_in_domain_xml():
    KEY = 'pvpanic_enable_in_domain_xml'
    metrics = {
        KEY: GaugeMetricFamily(KEY,
                'Whether the pvpanic attribute of the VM enabled in the domain XML', None, ['vmUuid'])
    }

    processes = fetch_vm_qemu_processes()
    if len(processes) == 0:
        return metrics.values()

    # if pvpanic enable in domain xml (qemu process cmdline has 'pvpanic,ioport'), collect '1'
    # if not, collect '0'
    for process in processes:
        vm_uuid = find_vm_uuid_from_vm_qemu_process(process)

        r = filter(lambda word: word == 'pvpanic,ioport=1285', process.cmdline())
        enable = 1 if len(r) > 0 else 0
        metrics[KEY].add_metric([vm_uuid], enable)

    return metrics.values()


collect_node_disk_wwid_last_time = None
collect_node_disk_wwid_last_result = None


def collect_node_disk_wwid():

    def get_physical_devices(pvpath, is_mpath):
        if is_mpath:
            dm_name = os.path.basename(os.path.realpath(pvpath))
            disks = os.listdir("/sys/block/%s/slaves/" % dm_name)
        else:
            disks = [ os.path.basename(pvpath) ]

        return ["/dev/%s" % re.sub('[0-9]$', '', s) for s in disks]

    def get_device_from_path(ctx, devpath):
        return pyudev.Device.from_device_file(ctx, devpath)

    def get_disk_wwids(b):
        links = b.get('DEVLINKS')
        if not links:
            return []

        return [ os.path.basename(str(p)) for p in links.split() if "disk/by-id" in p and "lvm-pv" not in p ]


    global collect_node_disk_wwid_last_time
    global collect_node_disk_wwid_last_result

    # NOTE(weiw): some storage can not afford frequent TUR. ref: ZSTAC-23416
    if collect_node_disk_wwid_last_time is None or (time.time() - collect_node_disk_wwid_last_time) >= 300:
        collect_node_disk_wwid_last_time = time.time()
    elif (time.time() - collect_node_disk_wwid_last_time) < 300 and collect_node_disk_wwid_last_result is not None:
        return collect_node_disk_wwid_last_result
    
    metrics = {
        'node_disk_wwid': GaugeMetricFamily('node_disk_wwid',
                                           'node disk wwid', None, ["disk", "wwid"])
    }

    collect_node_disk_wwid_last_result = metrics.values()

    pvs = bash_o("pvs --nolocking -t --noheading -o pv_name").strip().splitlines()
    context = pyudev.Context()

    for pv in pvs:
        pv = pv.strip()
        dm_uuid = get_device_from_path(context, pv).get("DM_UUID", "")
        multipath_wwid = dm_uuid[6:] if dm_uuid.startswith("mpath-") else None

        for disk in get_physical_devices(pv, multipath_wwid):
            disk_name = os.path.basename(disk)
            wwids = get_disk_wwids(get_device_from_path(context, disk))
            if multipath_wwid is not None:
                wwids.append(multipath_wwid)
            if len(wwids) > 0:
                metrics['node_disk_wwid'].add_metric([disk_name, ";".join([w.strip() for w in wwids])], 1)

    collect_node_disk_wwid_last_result = metrics.values()
    return collect_node_disk_wwid_last_result


def collect_physical_network_interface_state():
    metrics = {
        'physical_network_interface': GaugeMetricFamily('physical_network_interface',
                                                        'physical network interface', None,
                                                        ['interface_name', 'speed']),
    }
    
    nics = get_host_physicl_nics()
    if len(nics) != 0:
        for nic in nics:
            nic = nic.strip()
            try:
                # NOTE(weiw): sriov nic contains carrier file but can not read
                status = linux.read_nic_carrier("/sys/class/net/%s/carrier" % nic).strip() == "1"
            except Exception as e:
                status = False
            speed = str(get_nic_supported_max_speed(nic))
            metrics['physical_network_interface'].add_metric([nic, speed], status)
    
    return metrics.values()
    

def collect_host_conntrack_statistics():
    metrics = {
        'zstack_conntrack_in_count': GaugeMetricFamily('zstack_conntrack_in_count',
                                                       'zstack conntrack in count'),
        'zstack_conntrack_in_percent': GaugeMetricFamily('zstack_conntrack_in_percent',
                                                         'zstack conntrack in percent')
    }
    conntrack_count = linux.read_file("/proc/sys/net/netfilter/nf_conntrack_count")
    metrics['zstack_conntrack_in_count'].add_metric([], float(conntrack_count))

    conntrack_max = linux.read_file("/proc/sys/net/netfilter/nf_conntrack_max")
    percent = float(format(float(conntrack_count) / float(conntrack_max) * 100, '.2f'))
    conntrack_percent = 1.0 if percent <= 1.0 else percent
    metrics['zstack_conntrack_in_percent'].add_metric([], conntrack_percent)

    return metrics.values()


kvmagent.register_prometheus_collector(collect_host_network_statistics)
kvmagent.register_prometheus_collector(collect_host_capacity_statistics)
kvmagent.register_prometheus_collector(collect_vm_statistics)
kvmagent.register_prometheus_collector(collect_vm_pvpanic_enable_in_domain_xml)
kvmagent.register_prometheus_collector(collect_node_disk_wwid)
kvmagent.register_prometheus_collector(collect_host_conntrack_statistics)
kvmagent.register_prometheus_collector(collect_physical_network_interface_state)

if misc.isMiniHost():
    kvmagent.register_prometheus_collector(collect_lvm_capacity_statistics)
    kvmagent.register_prometheus_collector(collect_mini_raid_state)
    kvmagent.register_prometheus_collector(collect_equipment_state)
    
if misc.isHyperConvergedHost():
    kvmagent.register_prometheus_collector(collect_raid_state)
    kvmagent.register_prometheus_collector(collect_ipmi_state)
    kvmagent.register_prometheus_collector(collect_ssd_state)
else:
    kvmagent.register_prometheus_collector(collect_physical_cpu_state)


class PrometheusPlugin(kvmagent.KvmAgent):

    COLLECTD_PATH = "/prometheus/collectdexporter/start"

    @kvmagent.replyerror
    @in_bash
    def start_prometheus_exporter(self, req):
        @in_bash
        def start_collectd(cmd):
            conf_path = os.path.join(os.path.dirname(cmd.binaryPath), 'collectd.conf')
            ingore_block_device = "/:sd[c-e]/" if kvmagent.host_arch in ["mips64el", "aarch64", "loongarch64"] else "//"

            conf = '''Interval {{INTERVAL}}
# version {{VERSION}}
FQDNLookup false

LoadPlugin syslog
LoadPlugin aggregation
LoadPlugin cpu
LoadPlugin disk
LoadPlugin interface
LoadPlugin memory
LoadPlugin network
LoadPlugin virt

<Plugin aggregation>
	<Aggregation>
		#Host "unspecified"
		Plugin "cpu"
		#PluginInstance "unspecified"
		Type "cpu"
		#TypeInstance "unspecified"

		GroupBy "Host"
		GroupBy "TypeInstance"

		CalculateNum false
		CalculateSum false
		CalculateAverage true
		CalculateMinimum false
		CalculateMaximum false
		CalculateStddev false
	</Aggregation>
</Plugin>

<Plugin cpu>
  ReportByCpu true
  ReportByState true
  ValuesPercentage true
</Plugin>

<Plugin disk>
  Disk "/^sd[a-z]$/"
  Disk "/^hd[a-z]$/"
  Disk "/^vd[a-z]$/"
  Disk "/^nvme[0-9][a-z][0-9]$/"
  IgnoreSelected false
</Plugin>

<Plugin "interface">
{% for i in INTERFACES -%}
  Interface "{{i}}"
{% endfor -%}
  IgnoreSelected false
</Plugin>

<Plugin memory>
	ValuesAbsolute true
	ValuesPercentage false
</Plugin>

<Plugin virt>
	Connection "qemu:///system"
	RefreshInterval {{INTERVAL}}
	HostnameFormat name
    PluginInstanceFormat name
    BlockDevice "/:hd[a-z]/"
    BlockDevice "{{IGNORE}}"
    IgnoreSelected true
    ExtraStats "vcpu memory"
</Plugin>

<Plugin network>
	Server "localhost" "25826"
</Plugin>

'''

            tmpt = Template(conf)
            conf = tmpt.render({
                'INTERVAL': cmd.interval,
                'INTERFACES': interfaces,
                'VERSION': cmd.version,
                'IGNORE': ingore_block_device
            })

            need_restart_collectd = False
            if os.path.exists(conf_path):
                with open(conf_path, 'r') as fd:
                    old_conf = fd.read()

                if old_conf != conf:
                    with open(conf_path, 'w') as fd:
                        fd.write(conf)
                    need_restart_collectd = True
            else:
                with open(conf_path, 'w') as fd:
                    fd.write(conf)
                need_restart_collectd = True

            cpid = linux.find_process_by_command('collectd', [conf_path])
            mpid = linux.find_process_by_command('collectdmon', [conf_path])

            if not cpid:
                bash_errorout('collectdmon -- -C %s' % conf_path)
            else:
                bash_errorout('kill -TERM %s' % cpid)
                if need_restart_collectd:
                    if not mpid:
                        bash_errorout('collectdmon -- -C %s' % conf_path)
                    else:
                        bash_errorout('kill -HUP %s' % mpid)
                else:
                    if not mpid:
                        bash_errorout('collectdmon -- -C %s' % conf_path)

        def run_in_systemd(binPath, args, log):
            def get_systemd_name(path):
                if "collectd_exporter" in path:
                    return "collectd_exporter"
                elif "node_exporter" in path:
                    return "node_exporter"
                elif "pushgateway" in path:
                    return "pushgateway"

            def reload_and_restart_service(service_name):
                bash_errorout("systemctl daemon-reload && systemctl restart %s.service" % service_name)

            service_name = get_systemd_name(binPath)
            service_path = '/etc/systemd/system/%s.service' % service_name

            service_conf = '''
[Unit]
Description=prometheus %s
After=network.target

[Service]
ExecStart=/bin/sh -c '%s %s > %s 2>&1'
ExecStop=/bin/sh -c 'pkill -TERM -f %s'

Restart=always
RestartSec=30s
[Install]
WantedBy=multi-user.target
''' % (service_name, binPath, args, '/dev/null' if log.endswith('/pushgateway.log') else log, binPath)

            if not os.path.exists(service_path):
                linux.write_file(service_path, service_conf, True)
                os.chmod(service_path, 0o644)
                reload_and_restart_service(service_name)
                return

            if linux.read_file(service_path) != service_conf:
                linux.write_file(service_path, service_conf, True)
                logger.info("%s.service conf changed" % service_name)

            os.chmod(service_path, 0o644)
            # restart service regardless of conf changes, for ZSTAC-23539
            reload_and_restart_service(service_name)

        @lock.file_lock("/run/collectd-conf.lock", locker=lock.Flock())
        def start_collectd_exporter(cmd):
            start_collectd(cmd)
            start_exporter(cmd)

        @in_bash
        def start_exporter(cmd):
            EXPORTER_PATH = cmd.binaryPath
            LOG_FILE = os.path.join(os.path.dirname(EXPORTER_PATH), cmd.binaryPath + '.log')
            ARGUMENTS = cmd.startupArguments
            if not ARGUMENTS:
                ARGUMENTS = ""
            os.chmod(EXPORTER_PATH, 0o755)
            run_in_systemd(EXPORTER_PATH, ARGUMENTS, LOG_FILE)

        para = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        eths = os.listdir("/sys/class/net")
        interfaces = []
        for eth in eths:
            if eth == 'lo': continue
            if eth == 'bonding_masters': continue
            elif eth.startswith('vnic'): continue
            elif eth.startswith('outer'): continue
            elif eth.startswith('br_'): continue
            elif not eth: continue
            else:
                interfaces.append(eth)

        for cmd in para.cmds:
            if "collectd_exporter" in cmd.binaryPath:
                start_collectd_exporter(cmd)
            else:
                start_exporter(cmd)

        return jsonobject.dumps(rsp)

    def install_colletor(self):
        class Collector(object):
            __collector_cache = {}

            @classmethod
            def __get_cache__(cls):
                # type: () -> list
                keys = cls.__collector_cache.keys()
                if keys is None or len(keys) == 0:
                    return None
                if (time.time() - keys[0]) < 9:
                    return cls.__collector_cache.get(keys[0])
                return None

            @classmethod
            def __store_cache__(cls, ret):
                # type: (list) -> None
                cls.__collector_cache.clear()
                cls.__collector_cache.update({time.time(): ret})

            @classmethod
            def check(cls, v):
                try:
                    if v is None:
                        return False
                    if isinstance(v, GaugeMetricFamily):
                        return Collector.check(v.samples)
                    if isinstance(v, list) or isinstance(v, tuple):
                        for vl in v:
                            if Collector.check(vl) is False:
                                return False
                    if isinstance(v, dict):
                        for vk in v.iterkeys():
                            if vk == "timestamp" or vk == "exemplar":
                                continue
                            if Collector.check(v[vk]) is False:
                                return False
                except Exception as e:
                    logger.warn("got exception in check value %s: %s" % (v, e))
                    return True
                return True

            def collect(self):
                global latest_collect_result
                ret = []

                def get_result_run(f, fname):
                    # type: (typing.Callable, str) -> None
                    global collectResultLock
                    global latest_collect_result

                    r = f()
                    if not Collector.check(r):
                        logger.warn("result from collector %s contains illegal character None, details: \n%s" % (fname, r))
                        return
                    with collectResultLock:
                        latest_collect_result[fname] = r

                cache = Collector.__get_cache__()
                if cache is not None:
                    return cache

                for c in kvmagent.metric_collectors:
                    name = "%s.%s" % (c.__module__, c.__name__)
                    if collector_dict.get(name) is not None and collector_dict.get(name).is_alive():
                        continue
                    collector_dict[name] = thread.ThreadFacade.run_in_thread(get_result_run, (c, name,))

                for i in range(7):
                    for t in collector_dict.values():
                        if t.is_alive():
                            time.sleep(0.5)
                            break

                for k in collector_dict.iterkeys():
                    if collector_dict[k].is_alive():
                        logger.warn("It seems that the collector [%s] has not been completed yet,"
                                    " temporarily use the last calculation result." % k)

                for v in latest_collect_result.itervalues():
                    ret.extend(v)
                Collector.__store_cache__(ret)
                return ret

        REGISTRY.register(Collector())

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.COLLECTD_PATH, self.start_prometheus_exporter)

        self.install_colletor()
        start_http_server(7069)

    def stop(self):
        pass
    
    def configure(self, config):
        global ALARM_CONFIG
        ALARM_CONFIG = config

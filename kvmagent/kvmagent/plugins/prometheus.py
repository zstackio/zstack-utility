import os.path
import pyudev       # installed by ansible
import threading
import time
from collections import defaultdict

import typing
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY
import psutil

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import lock
from zstacklib.utils import lvm
from zstacklib.utils import shell
from zstacklib.utils import misc
from zstacklib.utils import thread
from zstacklib.utils.bash import *
from zstacklib.utils.ip import get_host_physicl_nics
from zstacklib.utils.ip import get_nic_supported_max_speed

logger = log.get_logger(__name__)
collector_dict = {}  # type: Dict[str, threading.Thread]
collectd_dir = "/var/lib/zstack/collectd/"
latest_collect_result = {}
collectResultLock = threading.RLock()
asyncDataCollectorLock = threading.RLock()
QEMU_CMD = os.path.basename(kvmagent.get_qemu_path())
ALARM_CONFIG = None
PAGE_SIZE = None
disk_list_record = None
cpu_status_abnormal_list_record = set()
memory_status_abnormal_list_record = set()
fan_status_abnormal_list_record = set()
power_supply_status_abnormal_list_record = set()
disk_status_abnormal_list_record = {}

# collect domain max memory
domain_max_memory = {}

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
def send_physical_power_supply_status_alarm_to_mn(name, status):
    class PhysicalPowerSupplyStatusAlarm(object):
        def __init__(self):
            self.host = None
            self.name = None
            self.status = None

    if ALARM_CONFIG is None:
        return

    url = ALARM_CONFIG.get(kvmagent.SEND_COMMAND_URL)
    if not url:
        logger.warn(
            "cannot find SEND_COMMAND_URL, unable to transmit physical fan status alarm info to management node")
        return

    global power_supply_status_abnormal_list_record
    if name not in power_supply_status_abnormal_list_record:
        physical_power_supply_status_alarm = PhysicalPowerSupplyStatusAlarm()
        physical_power_supply_status_alarm.host = ALARM_CONFIG.get(kvmagent.HOST_UUID)
        physical_power_supply_status_alarm.name = name
        physical_power_supply_status_alarm.status = status
        http.json_dump_post(url, physical_power_supply_status_alarm, {'commandpath': '/host/physical/powersupply/status/alarm'})
        power_supply_status_abnormal_list_record.add(name)

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

# use lazy loading to avoid re-registering global configuration when other modules are initialized
host_network_interface_service_type_map = None

@lock.lock('serviceTypeMapLock')
def get_service_type_map():
    global host_network_interface_service_type_map
    if host_network_interface_service_type_map is None:
        host_network_interface_service_type_map = {}
    return host_network_interface_service_type_map

@lock.lock('serviceTypeMapLock')
def register_service_type(dev_name, service_type):
    host_network_interface_service_type_map = get_service_type_map()
    host_network_interface_service_type_map[dev_name] = service_type

def collect_host_network_statistics():
    all_eths = os.listdir("/sys/class/net/")
    virtual_eths = os.listdir("/sys/devices/virtual/net/")

    interfaces = []
    for eth in all_eths:
        eth = eth.strip(' \t\n\r')
        if eth in virtual_eths:
            continue
        elif eth == 'bonding_masters':
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

    service_types = ['ManagementNetwork', 'TenantNetwork', 'StorageNetwork', 'BackupNetwork', 'MigrationNetwork']
    all_in_bytes_by_service_type = {service_type: 0 for service_type in service_types}
    all_in_packets_by_service_type = {service_type: 0 for service_type in service_types}
    all_in_errors_by_service_type = {service_type: 0 for service_type in service_types}
    all_out_bytes_by_service_type = {service_type: 0 for service_type in service_types}
    all_out_packets_by_service_type = {service_type: 0 for service_type in service_types}
    all_out_errors_by_service_type = {service_type: 0 for service_type in service_types}

    host_network_interface_service_type_map = get_service_type_map()
    host_network_service_type_interface_map = defaultdict(list)
    for interface, types in host_network_interface_service_type_map.items():
        for service_type in types:
            host_network_service_type_interface_map[service_type].append(interface)

    for service_type in service_types:
        eths = sorted(host_network_service_type_interface_map.get(service_type, []))
        eths_filter_subinterfaces = []
        eths_filter_bridges = []

        # Filter out the corresponding sub interface zsn0.10 of interface like zsn0
        for eth in eths:
            if '.' in eth:
                interface_name  = eth.split('.')[0]
                if interface_name in eths_filter_subinterfaces:
                    continue
            eths_filter_subinterfaces.append(eth)

        # Filter out the corresponding bridge interface br_zsn0_1987 of interface like zsn0.1987
        for eth in eths_filter_subinterfaces:
            if eth.startswith('br_'):
                eth_interface = eth[3:].replace('_', '.')
                if eth_interface in eths_filter_subinterfaces:
                    continue
            eths_filter_bridges.append(eth)

        for eth in eths_filter_bridges:
            all_in_bytes_by_service_type[service_type] += read_number("/sys/class/net/{}/statistics/rx_bytes".format(eth))
            all_in_packets_by_service_type[service_type] += read_number("/sys/class/net/{}/statistics/rx_packets".format(eth))
            all_in_errors_by_service_type[service_type] += read_number("/sys/class/net/{}/statistics/rx_errors".format(eth))
            all_out_bytes_by_service_type[service_type] += read_number("/sys/class/net/{}/statistics/tx_bytes".format(eth))
            all_out_packets_by_service_type[service_type] += read_number("/sys/class/net/{}/statistics/tx_packets".format(eth))
            all_out_errors_by_service_type[service_type] += read_number("/sys/class/net/{}/statistics/tx_errors".format(eth))

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
        'host_network_all_in_bytes_by_service_type': GaugeMetricFamily('host_network_all_in_bytes_by_service_type',
                                                                      'Host all inbound traffic in bytes by service type',
                                                                      None, ['service_type']),
        'host_network_all_in_packages_by_service_type': GaugeMetricFamily('host_network_all_in_packages_by_service_type',
                                                                         'Host all inbound traffic in packages by service type',
                                                                         None, ['service_type']),
        'host_network_all_in_errors_by_service_type': GaugeMetricFamily('host_network_all_in_errors_by_service_type',
                                                                       'Host all inbound traffic errors by service type',
                                                                       None, ['service_type']),
        'host_network_all_out_bytes_by_service_type': GaugeMetricFamily('host_network_all_out_bytes_by_service_type',
                                                                       'Host all outbound traffic in bytes by service type',
                                                                       None, ['service_type']),
        'host_network_all_out_packages_by_service_type': GaugeMetricFamily('host_network_all_out_packages_by_service_type',
                                                                          'Host all outbound traffic in packages by service type',
                                                                          None, ['service_type']),
        'host_network_all_out_errors_by_service_type': GaugeMetricFamily('host_network_all_out_errors_by_service_type',
                                                                        'Host all outbound traffic errors by service type',
                                                                        None, ['service_type']),
    }

    metrics['host_network_all_in_bytes'].add_metric([], float(all_in_bytes))
    metrics['host_network_all_in_packages'].add_metric([], float(all_in_packets))
    metrics['host_network_all_in_errors'].add_metric([], float(all_in_errors))
    metrics['host_network_all_out_bytes'].add_metric([], float(all_out_bytes))
    metrics['host_network_all_out_packages'].add_metric([], float(all_out_packets))
    metrics['host_network_all_out_errors'].add_metric([], float(all_out_errors))
    for service_type in service_types:
        metrics['host_network_all_in_bytes_by_service_type'].add_metric([service_type], float(all_in_bytes_by_service_type[service_type]))
        metrics['host_network_all_in_packages_by_service_type'].add_metric([service_type], float(all_in_packets_by_service_type[service_type]))
        metrics['host_network_all_in_errors_by_service_type'].add_metric([service_type], float(all_in_errors_by_service_type[service_type]))
        metrics['host_network_all_out_bytes_by_service_type'].add_metric([service_type], float(all_out_bytes_by_service_type[service_type]))
        metrics['host_network_all_out_packages_by_service_type'].add_metric([service_type], float(all_out_packets_by_service_type[service_type]))
        metrics['host_network_all_out_errors_by_service_type'].add_metric([service_type], float(all_out_errors_by_service_type[service_type]))

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
    r2, lbkInfo = bash_ro("lsblk -e 43 -db -oname,size | tail -n +2")
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
    state = state.lower().strip()
    if "optimal" in state or "optl" == state:
        return 0
    # dgrd and pdgd
    elif "degraded" in state or "dgrd" == state or "pdgd" == state or "interim recovery" in state:
        return 5
    elif "ready for recovery" in state or "rebuilding" in state or "rec" == state:
        return 10
    else:
        return 100


def convert_disk_state_to_int(state):
    """

    :type state: str
    """
    state = state.lower().strip()
    if "online" in state or "jbod" in state or "ready" in state or "optimal" in state or "hot-spare" in state \
            or "hot spare" in state or "raw" in state or "onln" == state or "ghs" == state or "dhs" == state \
            or "ugood" == state:
        return 0
    elif "rebuild" in state or "rbld" == state:
        return 5
    elif "failed" in state or "offline" in state or "offln" == state:
        return 10
    elif "missing" in state:
        return 20
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

    r, o = bash_ro("/opt/MegaRAID/storcli/storcli64 /call/vall show all J")
    if r == 0 and jsonobject.loads(o)['Controllers'][0]['Command Status']['Status'] == "Success":
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
            drive_state = serial_number = slot_number = enclosure_device_id = "unknown"
            is_hard_drive = False
            for l in infos.splitlines():
                if l.strip() == "":
                    continue
                if l.strip().lower() == "device is a hard drive":
                    is_hard_drive = True
                    continue
                k = l.split(":")[0].strip().lower()
                v = ":".join(l.split(":")[1:]).strip()
                if "state" == k:
                    drive_state = v.split(" ")[0].strip()
                elif "serial number" in k:
                    serial_number = v
                elif "reported location" in k and "Enclosure" in v and "Slot" in v:
                    enclosure_device_id = v.split(",")[0].split(" ")[1].strip()
                    slot_number = v.split("Slot ")[1].split("(")[0].strip()

            if not is_hard_drive or serial_number.lower() == "unknown" or enclosure_device_id == "unknown" or slot_number == "unknown" or drive_state == "unknown":
                continue
            disk_status = convert_disk_state_to_int(drive_state)
            metrics['physical_disk_state'].add_metric([slot_number, enclosure_device_id], disk_status)
            disk_list[serial_number] = "%s-%s" % (enclosure_device_id, slot_number)
            if disk_status == 0 and (serial_number in disk_status_abnormal_list_record.keys()):
                disk_status_abnormal_list_record.pop(serial_number)
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
                if drive_status != 20:
                    disk_list[serial_number] = "%s-%s" % (enclosure_device_id, slot_number)
                if drive_status == 0 and (serial_number in disk_status_abnormal_list_record.keys()):
                    disk_status_abnormal_list_record.pop(serial_number)
                elif drive_status != 0:
                    send_physical_disk_status_alarm_to_mn(serial_number, slot_number, enclosure_device_id, state)

    check_disk_insert_and_remove(disk_list)
    return metrics.values()


def collect_mega_raid_state(metrics, infos):
    global disk_status_abnormal_list_record
    disk_list = {}
    vd_infos = jsonobject.loads(infos.strip())

    # collect raid vd state
    for controller in vd_infos["Controllers"]:
        controller_id = controller["Command Status"]["Controller"]
        data = controller["Response Data"]
        for attr in dir(data):
            match = re.match(r"/c%s/v(\d+)" % controller_id, attr)
            if not match:
                continue
            vd_state = data[attr][0]["State"]
            disk_group = data[attr][0]["DG/VD"].split("/")[0]
            converted_vd_state = convert_raid_state_to_int(vd_state)
            metrics['raid_state'].add_metric([disk_group], converted_vd_state)

    # collect disk state
    o = bash_o("/opt/MegaRAID/storcli/storcli64 /call/eall/sall show all J").strip()
    pd_infos = jsonobject.loads(o.strip())
    for controller in pd_infos["Controllers"]:
        controller_id = controller["Command Status"]["Controller"]
        data = controller["Response Data"]
        for attr in dir(data):
            match = re.match(r"^Drive /c%s/e(\d+)/s(\d+)$" % controller_id, attr)
            if not match:
                continue
            enclosure_id = match.group(1)
            slot_id = match.group(2)
            pd_state = data[attr][0]["State"]
            converted_pd_status = convert_disk_state_to_int(pd_state)
            metrics['physical_disk_state'].add_metric([slot_id, enclosure_id], converted_pd_status)
            pd_path = "/c%s/e%s/s%s" % (controller_id, enclosure_id, slot_id)
            pd_attributes = data["Drive %s - Detailed Information" % pd_path]["Drive %s Device attributes" % pd_path]
            serial_number = pd_attributes["SN"].replace(" ", "")
            disk_list[serial_number] = "%s-%s" % (enclosure_id, slot_id)
            if converted_pd_status == 0 and (serial_number in disk_status_abnormal_list_record.keys()):
                disk_status_abnormal_list_record.pop(serial_number)
            elif converted_pd_status != 0:
                send_physical_disk_status_alarm_to_mn(serial_number, slot_id, enclosure_id, converted_pd_status)

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
    r, cpu_temps = bash_ro("sensors")
    if r == 0:
        count = 0
        for info in cpu_temps.splitlines():
            match = re.search( r'^Physical id[^+]*\+(\d*\.\d+)', info)
            if match:
                cpu_id = "CPU" + str(count)
                metrics['cpu_temperature'].add_metric([cpu_id], float(match.group(1).strip()))
                count = count + 1

        if count == 0:
            for info in cpu_temps.splitlines():
                match = re.search(r'^temp[^+]*\+(\d*\.\d+)', info)
                if match:
                    cpu_id = "CPU" + str(count)
                    metrics['cpu_temperature'].add_metric([cpu_id], float(match.group(1).strip()))
                    count = count + 1

    # get cpu status
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

@thread.AsyncThread
def check_equipment_state_from_ipmitool():
    sensor_handlers = {
        "Memory": send_physical_memory_status_alarm_to_mn,
        "Fan": send_physical_fan_status_alarm_to_mn,
        "Power_Supply": send_physical_power_supply_status_alarm_to_mn
    }

    r, memory_infos = bash_ro("ipmi-sensors --sensor-types=Memory,fan,Power_Supply -Q --ignore-unrecognized-events --comma-separated-output "
                              "--no-header-output --sdr-cache-recreate --output-event-bitmask --output-sensor-state")
    if r == 0:
        for memory_info in memory_infos.splitlines():
            memory = memory_info.split(",")
            sensor_name = memory[1].strip()
            sensor_type = memory[2].strip()
            sensor_state = memory[3].strip()

            if sensor_state.lower() == "critical" and sensor_type in sensor_handlers:
                sensor_handlers[sensor_type](sensor_name, sensor_state)
            else:
                fan_status_abnormal_list_record.discard(sensor_name)
                power_supply_status_abnormal_list_record.discard(sensor_name)
                memory_status_abnormal_list_record.discard(sensor_name)

def collect_equipment_state_from_ipmi():
    metrics = {
        "ipmi_status": GaugeMetricFamily('ipmi_status', 'ipmi status', None, []),
        "cpu_temperature": GaugeMetricFamily('cpu_temperature', 'cpu temperature', None, ['cpu']),
        "cpu_status": GaugeMetricFamily('cpu_status', 'cpu status', None, ['cpu']),
    }
    metrics['ipmi_status'].add_metric([], bash_r("ipmitool mc info"))

    r, cpu_info = bash_ro("ipmitool sdr elist | grep -i cpu")  # type: (int, str)
    if r != 0:
        return metrics.values()

    check_equipment_state_from_ipmitool()

    '''
        ================
        CPU TEMPERATURE
        ================
        CPU1_Temp        | 39h | ok  |  7.18 | 34 degrees C
        CPU1_Core_Temp   | 39h | ok  |  7.18 | 34 degrees C
        CPU_Temp_01      | 39h | ok  |  7.18 | 34 degrees C
        CPU1 Temp        | 39h | ok  |  7.18 | 34 degrees C
        CPU1 Core Rem    | 04h | ok  |  3.96 | 41 degrees C
        
        ================
        CPU STATUS
        ================
        CPU_STATUS_01    | 52h | ok  |  3.0 | Presence detected
        CPU1 Status      | 3Ch | ok  |  3.96 | Presence detected
        CPU1_Status      | 7Eh | ok  |  3.0 | Presence detected
    '''

    cpu_temperature_pattern = r'^(cpu\d+_temp|cpu\d+_core_temp|cpu_temp_\d+|cpu\d+ temp|cpu\d+ core rem)$'
    cpu_status_pattern = r'^(cpu_status_\d+|cpu\d+ status|cpu\d+_status)$'

    for line in cpu_info.lower().splitlines():
        sensor = line.split("|")
        if len(sensor) != 5:
            continue
        sensor_id = sensor[0].strip()
        sensor_value = sensor[4].strip()
        if re.match(cpu_temperature_pattern, sensor_id):
            cpu_id = int(re.sub(r'\D', '', sensor_id))
            cpu_temperature = filter(str.isdigit, sensor_value) if bool(re.search(r'\d', sensor_value)) else 0
            metrics['cpu_temperature'].add_metric(["CPU%d" % cpu_id], float(cpu_temperature))
        if re.match(cpu_status_pattern, sensor_id):
            cpu_id = int(re.sub(r'\D', '', sensor_id))
            cpu_status = 0 if "presence detected" == sensor_value else 10
            metrics['cpu_status'].add_metric(["CPU%d" % cpu_id], float(cpu_status))
            if cpu_status == 10:
                send_cpu_status_alarm_to_mn(cpu_id, info.Status)
            else:
                cpu_status_abnormal_list_record.discard(cpu_id)

    return metrics.values()


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


def collect_memory_overcommit_statistics():
    global PAGE_SIZE

    metrics = {
        'host_ksm_pages_shared_in_bytes': GaugeMetricFamily('host_ksm_pages_shared_in_bytes',
                                               'host ksm shared pages', None, []),
        'host_ksm_pages_sharing_in_bytes': GaugeMetricFamily('host_ksm_pages_sharing_in_bytes',
                                                  'host ksm sharing pages', None, []),
        'host_ksm_pages_unshared_in_bytes': GaugeMetricFamily('host_ksm_pages_unshared_in_bytes',
                                                    'host ksm unshared pages', None, []),
        'host_ksm_pages_volatile': GaugeMetricFamily('host_ksm_pages_volatile',
                                                        'host ksm volatile pages', None, []),
        'host_ksm_full_scans': GaugeMetricFamily('host_ksm_full_scans',
                                                    'host ksm full scans', None, []),
        'collectd_virt_memory': GaugeMetricFamily('collectd_virt_memory',
                                                    'collectd_virt_memory gauge', None, ['instance', 'type', 'virt']),
    }

    if PAGE_SIZE is None:
        return metrics.values()

    # read metric from /sys/kernel/mm/ksm
    value = linux.read_file("/sys/kernel/mm/ksm/pages_shared")
    if value:
        metrics['host_ksm_pages_shared_in_bytes'].add_metric([], float(value.strip()) * PAGE_SIZE)

    value = linux.read_file("/sys/kernel/mm/ksm/pages_sharing")
    if value:
        metrics['host_ksm_pages_sharing_in_bytes'].add_metric([], float(value.strip()) * PAGE_SIZE)

    value = linux.read_file("/sys/kernel/mm/ksm/pages_unshared")
    if value:
        metrics['host_ksm_pages_unshared_in_bytes'].add_metric([], float(value.strip()) * PAGE_SIZE)

    value = linux.read_file("/sys/kernel/mm/ksm/pages_volatile")
    if value:
        metrics['host_ksm_pages_volatile'].add_metric([], float(value.strip()))

    value = linux.read_file("/sys/kernel/mm/ksm/full_scans")
    if value:
        metrics['host_ksm_full_scans'].add_metric([], float(value.strip()))

    with asyncDataCollectorLock:
        for domain_name, maximum_memory in domain_max_memory.items():
            metrics['collectd_virt_memory'].add_metric([domain_name, "max_balloon", domain_name], 1024 * float(maximum_memory.strip()))

    return metrics.values()


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

def parse_nvidia_smi_output_to_list(data):
    lines = data.splitlines()
    vgpu_list = []
    current_vgpu = None
    for line in lines:
        indentation = len(line) - len(line.lstrip())
        line = line.strip()
        if "vGPU ID" in line:
            if current_vgpu is not None:
                vgpu_list.append(current_vgpu)
            current_vgpu = {}
        if ':' in line and current_vgpu is not None:
            key, value = map(str.strip, line.split(':', 1))
            if value.isdigit():
                value = int(value)
            elif value.replace('.', '', 1).isdigit() and '%' in value:
                value = float(value.replace('%', ''))
            current_vgpu[key] = value
    if current_vgpu is not None:
        vgpu_list.append(current_vgpu)
    return vgpu_list


def collect_nvidia_gpu_state():
    metrics = {
        "gpu_power_draw": GaugeMetricFamily('gpu_power_draw', 'gpu power draw', None, ['pci_device_address', 'gpu_serial']),
        "gpu_temperature": GaugeMetricFamily('gpu_temperature', 'gpu temperature', None, ['pci_device_address', 'gpu_serial']),
        "gpu_fan_speed": GaugeMetricFamily('gpu_fan_speed', 'current percentage of gpu fan speed', None, ['pci_device_address', 'gpu_serial']),
        "gpu_utilization": GaugeMetricFamily('gpu_utilization', 'gpu utilization', None, ['pci_device_address']),
        "gpu_memory_utilization": GaugeMetricFamily('gpu_memory_utilization', 'gpu memory utilization', None, ['pci_device_address', 'gpu_serial']),
        "gpu_rxpci_in_bytes": GaugeMetricFamily('gpu_rxpci_in_bytes', 'gpu rxpci in bytes', None, ['pci_device_address', 'gpu_serial']),
        "gpu_txpci_in_bytes": GaugeMetricFamily('gpu_txpci_in_bytes', 'gpu txpci in bytes', None, ['pci_device_address', 'gpu_serial']),
        "gpu_state": GaugeMetricFamily('gpu_state', 'gpu status, 0 is critical, 1 is nominal', None, ['pci_device_address', 'gpuState', 'gpu_serial']),
        "vgpu_utilization": GaugeMetricFamily('vgpu_utilization', 'vgpu utilization', None, ['vm_uuid', 'mdev_uuid']),
        "vgpu_memory_utilization": GaugeMetricFamily('vgpu_memory_utilization', 'vgpu memory utilization', None, ['vm_uuid', 'mdev_uuid'])
    }

    if has_nvidia_smi() is False:
        return metrics.values()

    r, gpu_info = bash_ro(
        "nvidia-smi --query-gpu=power.draw,temperature.gpu,fan.speed,utilization.gpu,utilization.memory,index,gpu_bus_id,gpu_serial --format=csv,noheader")
    if r != 0:
        return metrics.values()

    gpu_index_mapping_pciaddress = {}
    for info in gpu_info.splitlines():
        info = info.strip().split(',')
        pci_device_address = info[-2].strip()
        gpu_serial = info[-1].strip()
        if len(pci_device_address.split(':')[0]) == 8:
            pci_device_address = pci_device_address[4:]

        metrics['gpu_power_draw'].add_metric([pci_device_address, gpu_serial], float(info[0].replace('W', '').strip()))
        metrics['gpu_temperature'].add_metric([pci_device_address, gpu_serial], float(info[1].strip()))
        metrics['gpu_fan_speed'].add_metric([pci_device_address, gpu_serial], float(info[2].replace('%', '').strip()))
        metrics['gpu_utilization'].add_metric([pci_device_address, gpu_serial], float(info[3].replace('%', '').strip()))
        metrics['gpu_memory_utilization'].add_metric([pci_device_address, gpu_serial], float(info[4].replace('%', '').strip()))
        gpuState, gpu_state_int_value = convert_pci_state_to_int(pci_device_address)
        metrics['gpu_state'].add_metric([pci_device_address, gpuState, gpu_serial], gpu_state_int_value)
        gpu_index_mapping_pciaddress[info[5].strip()] = pci_device_address

    r, gpu_pci_rx_tx = bash_ro("nvidia-smi dmon -c 1 -s t")
    if r != 0:
        return metrics.values()

    for gpu_index_rx_tx in gpu_pci_rx_tx.splitlines()[2:]:
        index_rx_tx = gpu_index_rx_tx.split()
        pci_device_address = gpu_index_mapping_pciaddress[index_rx_tx[0]]
        if pci_device_address is None:
            logger.error("No PCI address found for GPU index {index_rx_tx[0]}")
            continue

        metrics['gpu_rxpci_in_bytes'].add_metric([pci_device_address, gpu_serial], float(index_rx_tx[1]) * 1024 * 1024)
        metrics['gpu_txpci_in_bytes'].add_metric([pci_device_address, gpu_serial], float(index_rx_tx[2]) * 1024 * 1024)

    r, vgpu_info = bash_ro("nvidia-smi vgpu -q")
    if r != 0 or "VM Name" not in vgpu_info:
        return metrics.values()

    for vgpu in parse_nvidia_smi_output_to_list(vgpu_info):
        vm_uuid = vgpu["VM Name"]
        mdev_uuid = vgpu["MDEV UUID"].replace('-', '')
        metrics['vgpu_utilization'].add_metric([vm_uuid, mdev_uuid], float(vgpu['Gpu'].replace('%', '').strip()))
        metrics['vgpu_memory_utilization'].add_metric([vm_uuid, mdev_uuid],
                                                      float(vgpu['Memory'].replace('%', '').strip()))
    return metrics.values()


def collect_amd_gpu_state():
    metrics = {
        "gpu_power_draw": GaugeMetricFamily('gpu_power_draw', 'gpu power draw', None, ['pci_device_address', 'gpu_serial']),
        "gpu_temperature": GaugeMetricFamily('gpu_temperature', 'gpu temperature', None, ['pci_device_address', 'gpu_serial']),
        "gpu_fan_speed": GaugeMetricFamily('gpu_fan_speed', 'current percentage of gpu fan speed', None, ['pci_device_address', 'gpu_serial']),
        "gpu_utilization": GaugeMetricFamily('gpu_utilization', 'gpu utilization', None, ['pci_device_address', 'gpu_serial']),
        "gpu_memory_utilization": GaugeMetricFamily('gpu_memory_utilization', 'gpu memory utilization', None,
                                                    ['pci_device_address', 'gpu_serial']),
        "gpu_state": GaugeMetricFamily('gpu_state', 'gpu status, 0 is critical, 1 is nominal', None,
                                        ['pci_device_address', 'gpuState', 'gpu_serial']),
        "gpu_rxpci": GaugeMetricFamily('gpu_rxpci', 'gpu rxpci', None, ['pci_device_address']),
        "gpu_txpci": GaugeMetricFamily('gpu_txpci', 'gpu txpci', None, ['pci_device_address'])
    }

    if has_rocm_smi() is False:
        return metrics.values()

    r, gpu_info = bash_ro('rocm-smi --showpower --showtemp  --showmemuse --showuse --showfan --showbus  --showserial --json')
    if r != 0:
        return metrics.values()

    gpu_info_json = json.loads(gpu_info.strip())
    for card_name, card_data in gpu_info_json.items():
        gpu_serial = card_data['Serial Number']
        pci_device_address = card_data['PCI Bus']
        metrics['gpu_power_draw'].add_metric([pci_device_address, gpu_serial],
                                             float(card_data['Average Graphics Package Power (W)']))
        metrics['gpu_temperature'].add_metric([pci_device_address, gpu_serial], float(card_data['Temperature (Sensor edge) (C)']))
        metrics['gpu_fan_speed'].add_metric([pci_device_address, gpu_serial], float(card_data['Fan Speed (%)']))
        metrics['gpu_utilization'].add_metric([pci_device_address, gpu_serial], float(card_data['GPU use (%)']))
        gpuState , gpu_state_int_value = convert_pci_state_to_int(pci_device_address)
        metrics['gpu_state'].add_metric([pci_device_address, gpuState, gpu_serial], gpu_state_int_value)
        metrics['gpu_memory_utilization'].add_metric([pci_device_address, gpu_serial], float(card_data['GPU memory use (%)']))

    return metrics.values()

@in_bash
def convert_pci_state_to_int(pci_address):
    r, pci_status = bash_ro("lspci -s %s| grep -i 'rev ff'" % pci_address)
    if r == 0 and len(pci_status.strip()) != 0:
        return "critical", 0

    return "nominal", 1


def has_nvidia_smi():
    return shell.run("which nvidia-smi") == 0

def has_rocm_smi():
    if bash_r("lsmod | grep -q amdgpu") != 0:
        if bash_r("modprobe amdgpu") != 0:
            return False
    return shell.run("which rocm-smi") == 0



kvmagent.register_prometheus_collector(collect_host_network_statistics)
kvmagent.register_prometheus_collector(collect_host_capacity_statistics)
kvmagent.register_prometheus_collector(collect_vm_statistics)
kvmagent.register_prometheus_collector(collect_vm_pvpanic_enable_in_domain_xml)
kvmagent.register_prometheus_collector(collect_node_disk_wwid)
kvmagent.register_prometheus_collector(collect_host_conntrack_statistics)
kvmagent.register_prometheus_collector(collect_physical_network_interface_state)
kvmagent.register_prometheus_collector(collect_memory_overcommit_statistics)

if misc.isMiniHost():
    kvmagent.register_prometheus_collector(collect_lvm_capacity_statistics)
    kvmagent.register_prometheus_collector(collect_mini_raid_state)
    kvmagent.register_prometheus_collector(collect_equipment_state)
    
if misc.isHyperConvergedHost():
    kvmagent.register_prometheus_collector(collect_ipmi_state)
else:
    kvmagent.register_prometheus_collector(collect_equipment_state_from_ipmi)

kvmagent.register_prometheus_collector(collect_raid_state)
kvmagent.register_prometheus_collector(collect_ssd_state)
kvmagent.register_prometheus_collector(collect_nvidia_gpu_state)
kvmagent.register_prometheus_collector(collect_amd_gpu_state)

class SetServiceTypeOnHostNetworkInterfaceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(SetServiceTypeOnHostNetworkInterfaceRsp, self).__init__()

class PrometheusPlugin(kvmagent.KvmAgent):

    COLLECTD_PATH = "/prometheus/collectdexporter/start"
    SET_SERVICE_TYPE_ON_HOST_NETWORK_INTERFACE = "/host/setservicetype/networkinterface"

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
  Disk "/^sd[a-z]{1,2}$/"
  Disk "/^hd[a-z]{1,2}$/"
  Disk "/^vd[a-z]{1,2}$/"
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
    BlockDevice "/:hd[c-e]/"
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
                if not mpid:
                    bash_errorout('collectdmon -- -C %s' % conf_path)
                else:
                    bash_errorout('kill -TERM %s;collectdmon -- -C %s' % (mpid, conf_path))
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

        @in_bash
        def start_ipmi_exporter(cmd):
            bash_errorout("modprobe ipmi_msghandler; modprobe ipmi_devintf; modprobe ipmi_poweroff; modprobe ipmi_si; modprobe ipmi_watchdog")
            EXPORTER_PATH = cmd.binaryPath
            LOG_FILE = os.path.join(os.path.dirname(EXPORTER_PATH), cmd.binaryPath + '.log')
            ARGUMENTS = cmd.startupArguments

            conf_path = os.path.join(os.path.dirname(EXPORTER_PATH), 'ipmi.yml')

            conf = '''
# Configuration file for ipmi_exporter
modules:
  default:
    collectors:
      - bmc
      - ipmi
      - dcmi
      - chassis
    exclude_sensor_ids:
      - 2
      - 29
      - 32'''

            if not os.path.exists(conf_path) or open(conf_path, 'r').read() != conf:
                with open(conf_path, 'w') as fd:
                    fd.write(conf)

            os.chmod(EXPORTER_PATH, 0o755)
            run_in_systemd(EXPORTER_PATH, ARGUMENTS, LOG_FILE)


        para = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        eths = os.listdir("/sys/class/net")
        interfaces = []
        for eth in eths:
            if eth in ['lo', 'bonding_masters']: continue
            elif eth.startswith(('br_', 'vnic', 'docker', 'gre', 'erspan', 'outer', 'ud_')):continue
            elif not eth: continue
            else:
                interfaces.append(eth)

        for cmd in para.cmds:
            if "collectd_exporter" in cmd.binaryPath:
                start_collectd_exporter(cmd)
            elif "ipmi_exporter" in cmd.binaryPath:
                start_ipmi_exporter(cmd)
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
            def __store_cache__(cls, collectStartTime, ret):
                # type: (list) -> None
                cls.__collector_cache.clear()
                cls.__collector_cache.update({collectStartTime: ret})

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

                collectStartTime = time.time()
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
                Collector.__store_cache__(collectStartTime, ret)
                return ret

        REGISTRY.register(Collector())


    @thread.AsyncThread
    def start_async_data_collectors(self):
        while True:
            self.collect_domain_maximum_memory()
            time.sleep(300)


    def collect_domain_maximum_memory(self):
        o = bash_o('virsh domstats --list-running --balloon')
        if not o:
            return

        # Domain: '8e5c8fb20a8a4276b6c17267105e7710'
        #   balloon.current=1048576
        #   balloon.maximum=1048576
        #   balloon.swap_in=0
        #   balloon.swap_out=0
        #   balloon.major_fault=336
        #   balloon.minor_fault=3514274
        #   balloon.unused=793852
        #   balloon.available=1017068
        #   balloon.last-update=1690513108
        #   balloon.rss=411420
        #
        # Domain: '3f512fc8c3e5430bbfddb45db5485f11'
        #   balloon.current=1048576
        #   balloon.maximum=1048576
        #   balloon.swap_in=0
        #   balloon.swap_out=0
        #   balloon.major_fault=336
        #   balloon.minor_fault=3511963
        #   balloon.unused=793576
        #   balloon.available=1017068
        #   balloon.last-update=1690513112
        #   balloon.rss=412900

        # collect balloon.maximum and domain name
        with asyncDataCollectorLock:
            domain_max_memory.clear()
            for line in o.splitlines():
                if line.startswith("Domain:"):
                    domain = line.split("'")[1]
                elif line.startswith("  balloon.maximum="):
                    if domain is None:
                        logger.warn("can not get domain name, skip this domain")
                        continue

                    domain_max_memory[domain] = line.split("=")[1]
                    domain = None

    def init_global_config(self):
        global PAGE_SIZE
        output = bash_o("getconf PAGESIZE")
        if output == "" or output is None:
            PAGE_SIZE = 4096
        else:
            PAGE_SIZE = int(output)

    @kvmagent.replyerror
    def set_service_type_on_host_network_interface(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetServiceTypeOnHostNetworkInterfaceRsp()
        rsp.success = False

        dev_name = cmd.interfaceName
        if cmd.vlanId is not None and cmd.vlanId is not 0:
            dev_name = '%s.%s' % (cmd.interfaceName, cmd.vlanId)

        register_service_type(dev_name, cmd.serviceType)
        rsp.success = True

        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.COLLECTD_PATH, self.start_prometheus_exporter)
        http_server.register_async_uri(self.SET_SERVICE_TYPE_ON_HOST_NETWORK_INTERFACE,
                                       self.set_service_type_on_host_network_interface)

        self.init_global_config()
        self.install_colletor()
        self.start_async_data_collectors()
        start_http_server(7069)

    def stop(self):
        pass
    
    def configure(self, config):
        global ALARM_CONFIG
        ALARM_CONFIG = config

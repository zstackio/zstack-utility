import os.path
import pyudev       # installed by ansible
import re
import threading

import typing
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import lvm
from zstacklib.utils import misc
from zstacklib.utils import thread
from zstacklib.utils.bash import *
from zstacklib.utils.ip import get_nic_supported_max_speed

logger = log.get_logger(__name__)
collector_dict = {}  # type: Dict[str, threading.Thread]
latest_collect_result = {}
collectResultLock = threading.RLock()
QEMU_CMD = os.path.basename(kvmagent.get_qemu_path())

def read_number(fname):
    res = linux.read_file(fname)
    return 0 if not res else int(res)

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
                                                           'ZStack used capacity in bytes')
    }

    global collect_node_disk_capacity_last_time
    global collect_node_disk_capacity_last_result

    if collect_node_disk_capacity_last_time is None:
        collect_node_disk_capacity_last_time = time.time()
    elif time.time() - collect_node_disk_capacity_last_time < 60 and collect_node_disk_capacity_last_result is not None:
        return collect_node_disk_capacity_last_result

    zstack_used_capacity = 0
    for d in zstack_dir:
        if not os.path.exists(d):
            continue
        res = bash_o("du -bs %s" % d) # split()[0] is far cheaper than awk
        zstack_used_capacity += int(res.split()[0])

    metrics['zstack_used_capacity_in_bytes'].add_metric([], float(zstack_used_capacity))
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
    if state == "optimal":
        return 0
    elif state == "degraded":
        return 5
    else:
        return 100


def convert_disk_state_to_int(state):
    """

    :type state: str
    """
    state = state.lower()
    if "online" in state or "jobd" in state:
        return 0
    elif "rebuild" in state:
        return 5
    elif "failed" in state:
        return 10
    elif "unconfigured" in state:
        return 15
    else:
        return 100


def collect_raid_state():
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

    raid_info = bash_o("/opt/MegaRAID/MegaCli/MegaCli64 -LDInfo -LALL -aAll | grep -E 'Target Id|State'").strip().splitlines()
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


def collect_equipment_state():
    metrics = {
        'power_supply': GaugeMetricFamily('power_supply',
                                          'power supply', None, ['ps_id']),
        'ipmi_status': GaugeMetricFamily('ipmi_status', 'ipmi status', None, []),
        'physical_network_interface': GaugeMetricFamily('physical_network_interface',
                                                        'physical network interface', None,
                                                        ['interface_name', 'speed']),
    }

    r, ps_info = bash_ro("ipmitool sdr type 'power supply'")  # type: (int, str)
    if r == 0:
        for info in ps_info.splitlines():
            info = info.strip()
            ps_id = info.split("|")[0].strip().split(" ")[0]
            health = 10 if "fail" in info.lower() or "lost" in info.lower() else 0
            metrics['power_supply'].add_metric([ps_id], health)

    metrics['ipmi_status'].add_metric([], bash_r("ipmitool mc info"))

    nics = bash_o("find /sys/class/net -type l -not -lname '*virtual*' -printf '%f\\n'").splitlines()
    if len(nics) != 0:
        for nic in nics:
            nic = nic.strip()
            try:
                # NOTE(weiw): sriov nic contains carrier file but can not read
                status = linux.read_file("/sys/class/net/%s/carrier" % nic) == 1
            except Exception as e:
                status = True
            speed = str(get_nic_supported_max_speed(nic))
            metrics['physical_network_interface'].add_metric([nic, speed], status)

    return metrics.values()


def collect_vm_statistics():
    metrics = {
        'cpu_occupied_by_vm': GaugeMetricFamily('cpu_occupied_by_vm',
                                     'Percentage of CPU used by vm', None, ['vmUuid'])
    }

    r, pid_vm_map_str = bash_ro("ps -aux --no-headers | awk '/%s [-]name/{print $2,$13}'" % QEMU_CMD)
    if r != 0 or len(pid_vm_map_str.splitlines()) == 0:
        return metrics.values()
    pid_vm_map_str = pid_vm_map_str.replace(",debug-threads=on", "").replace("guest=", "")
    '''pid_vm_map_str samples:
    38149 e8e6f27bfb2d47e08c59cbea1d0488c3
    38232 afa02edca7eb4afcb5d2904ac1216eb1
    '''

    pid_vm_map = {}
    for pid_vm in pid_vm_map_str.splitlines():
        arr = pid_vm.split()
        if len(arr) == 2:
            pid_vm_map[arr[0]] = arr[1]

    def collect(vm_pid_arr):
        vm_pid_arr_str = ','.join(vm_pid_arr)

        r, pid_cpu_usages_str = bash_ro("top -b -n 1 -p %s" % vm_pid_arr_str)
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
    if collect_node_disk_wwid_last_time is None:
        collect_node_disk_wwid_last_time = time.time()
    elif time.time() - collect_node_disk_wwid_last_time < 300 and collect_node_disk_wwid_last_result is not None:
        return collect_node_disk_wwid_last_result

    metrics = {
        'node_disk_wwid': GaugeMetricFamily('node_disk_wwid',
                                           'node disk wwid', None, ["disk", "wwid"])
    }

    pvs = bash_o("pvs --nolocking --noheading -o pv_name").strip().splitlines()
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
kvmagent.register_prometheus_collector(collect_node_disk_wwid)
kvmagent.register_prometheus_collector(collect_host_conntrack_statistics)

if misc.isMiniHost():
    kvmagent.register_prometheus_collector(collect_lvm_capacity_statistics)
    kvmagent.register_prometheus_collector(collect_raid_state)
    kvmagent.register_prometheus_collector(collect_equipment_state)


class PrometheusPlugin(kvmagent.KvmAgent):

    COLLECTD_PATH = "/prometheus/collectdexporter/start"

    @kvmagent.replyerror
    @in_bash
    def start_prometheus_exporter(self, req):
        @in_bash
        def start_collectd(cmd):
            conf_path = os.path.join(os.path.dirname(cmd.binaryPath), 'collectd.conf')
            ingore_block_device = "/:sd[c-e]/" if kvmagent.os_arch in ["mips64el", "aarch64"] else "//"

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
                            continue

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

import os.path
import threading

import typing
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import iptables
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
IPTABLES_CMD = iptables.get_iptables_cmd()

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
        res = linux.read_file("/sys/class/net/{}/statistics/rx_bytes".format(intf))
        all_in_bytes += int(res)

        res = linux.read_file("/sys/class/net/{}/statistics/rx_packets".format(intf))
        all_in_packets += int(res)

        res = linux.read_file("/sys/class/net/{}/statistics/rx_errors".format(intf))
        all_in_errors += int(res)

        res = linux.read_file("/sys/class/net/{}/statistics/tx_bytes".format(intf))
        all_out_bytes += int(res)

        res = linux.read_file("/sys/class/net/{}/statistics/tx_packets".format(intf))
        all_out_packets += int(res)

        res = linux.read_file("/sys/class/net/{}/statistics/tx_errors".format(intf))
        all_out_errors += int(res)

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

    zstack_used_capacity = 0
    for dir in zstack_dir:
        if not os.path.exists(dir):
            continue
        cmd = "du -bs %s | awk {\'print $1\'}" % dir
        res = bash_o(cmd)
        zstack_used_capacity += int(res)

    metrics['zstack_used_capacity_in_bytes'].add_metric([], float(zstack_used_capacity))
    return metrics.values()


def collect_lvm_capacity_statistics():
    metrics = {
        'vg_size': GaugeMetricFamily('vg_size',
                                     'volume group size', None, ['vg_name']),
        'vg_avail': GaugeMetricFamily('vg_avail',
                                      'volume group and thin pool free size', None, ['vg_name']),
    }

    r = bash_r("grep '^[[:space:]]*use_lvmlockd=1' /etc/lvm/lvm.conf")
    if r == 0:
        return metrics.values()

    r = bash_r("grep -Ev '^[[:space:]]*#|^[[:space:]]*$' /etc/multipath/wwids")
    if r == 0:
        linux.set_fail_if_no_path()

    r, o, e = bash_roe("vgs --nolocking --noheading -oname")
    if r != 0 or len(o.splitlines()) == 0:
        return metrics.values()

    vg_names = o.splitlines()
    for name in vg_names:
        name = name.strip()
        size, avail = lvm.get_vg_size(name, False)
        metrics['vg_size'].add_metric([name], float(size))
        metrics['vg_avail'].add_metric([name], float(avail))

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

    r, pid_vm_map_str = bash_ro("ps --no-headers u -C \"qemu-kvm -name\" | awk '{print $2,$13}'")
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

        r, pid_cpu_usages_str = bash_ro("top -b -n 1 -p %s | awk '/qemu-kvm/{print $1,$9}'" % vm_pid_arr_str)
        if r != 0 or len(pid_cpu_usages_str.splitlines()) == 0:
            return

        for pid_cpu_usage in pid_cpu_usages_str.splitlines():
            arr = pid_cpu_usage.split()
            pid = arr[0]
            vm_uuid = pid_vm_map[pid]
            cpu_usage = arr[1]
            metrics['cpu_occupied_by_vm'].add_metric([vm_uuid], float(cpu_usage))

    n = 10
    for i in range(0, len(pid_vm_map.keys()), n):
        collect(pid_vm_map.keys()[i:i + n])

    return metrics.values()

kvmagent.register_prometheus_collector(collect_host_network_statistics)
kvmagent.register_prometheus_collector(collect_host_capacity_statistics)
kvmagent.register_prometheus_collector(collect_vm_statistics)

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

            conf = '''Interval {{INTERVAL}}
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
    IgnoreSelected true
</Plugin>

<Plugin network>
	Server "localhost" "25826"
</Plugin>

'''

            tmpt = Template(conf)
            conf = tmpt.render({
                'INTERVAL': cmd.interval,
                'INTERFACES': interfaces,
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
''' % (service_name, binPath, args, log, binPath)

            if not os.path.exists(service_path):
                linux.write_file(service_path, service_conf, True)
                os.chmod(service_path, 0644)
                reload_and_restart_service(service_name)
                return

            if linux.read_file(service_path) != service_conf:
                linux.write_file(service_path, service_conf, True)
                logger.info("%s.service conf changed" % service_name)

            os.chmod(service_path, 0644)
            # restart service regardless of conf changes, for ZSTAC-23539
            reload_and_restart_service(service_name)

        @in_bash
        def start_exporter(cmd):
            if "collectd_exporter" in cmd.binaryPath:
                start_collectd(cmd)

            EXPORTER_PATH = cmd.binaryPath
            LOG_FILE = os.path.join(os.path.dirname(EXPORTER_PATH), cmd.binaryPath + '.log')
            ARGUMENTS = cmd.startupArguments
            if not ARGUMENTS:
                ARGUMENTS = ""
            bash_errorout('chmod +x {{EXPORTER_PATH}}')
            run_in_systemd(EXPORTER_PATH, ARGUMENTS, LOG_FILE)

        para = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        eths = bash_o("ls /sys/class/net").split()
        interfaces = []
        for eth in eths:
            eth = eth.strip(' \t\n\r')
            if eth == 'lo': continue
            if eth == 'bonding_masters': continue
            elif eth.startswith('vnic'): continue
            elif eth.startswith('outer'): continue
            elif eth.startswith('br_'): continue
            elif not eth: continue
            else:
                interfaces.append(eth)

        for cmd in para.cmds:
            start_exporter(cmd)

        self.install_iptables()

        return jsonobject.dumps(rsp)

    @in_bash
    @lock.file_lock('/run/xtables.lock')
    def install_iptables(self):
        def install_iptables_port(rules, port):
            needle = '-A INPUT -p tcp -m tcp --dport %d' % port
            drules = [ r.replace("-A ", "-D ") for r in rules if needle in r ]
            for rule in drules:
                bash_r("%s %s" % (IPTABLES_CMD, rule))

            bash_r("%s -I INPUT -p tcp --dport %s -j ACCEPT" % (IPTABLES_CMD, port))

        rules = bash_o("%s -S INPUT" % IPTABLES_CMD).splitlines()
        install_iptables_port(rules, 7069)
        install_iptables_port(rules, 9100)
        install_iptables_port(rules, 9103)

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
                        for vv in v.itervalues():
                            if Collector.check(vv) is False:
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
                        logger.warn("result from collector %s contains illegal character None" % fname)
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

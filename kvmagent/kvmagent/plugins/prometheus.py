from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils.bash import *
from zstacklib.utils import linux
from zstacklib.utils import thread
from jinja2 import Template
import os.path
import re
import time
import traceback
from prometheus_client.core import GaugeMetricFamily,REGISTRY
from prometheus_client import start_http_server

logger = log.get_logger(__name__)

def collect_host_network_statistics():

    all_eths = bash_o("ls /sys/class/net/").split()
    virtual_eths = bash_o("ls /sys/devices/virtual/net/").split()

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
        res = bash_o("cat /sys/class/net/{}/statistics/rx_bytes".format(intf))
        all_in_bytes += int(res)

        res = bash_o("cat /sys/class/net/{}/statistics/rx_packets".format(intf))
        all_in_packets += int(res)

        res = bash_o("cat /sys/class/net/{}/statistics/rx_errors".format(intf))
        all_in_errors += int(res)

        res = bash_o("cat /sys/class/net/{}/statistics/tx_bytes".format(intf))
        all_out_bytes += int(res)

        res = bash_o("cat /sys/class/net/{}/statistics/tx_packets".format(intf))
        all_out_packets += int(res)

        res = bash_o("cat /sys/class/net/{}/statistics/tx_errors".format(intf))
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
                                                           'ZStack used capacity in bytes'),
        'host_fs_size': GaugeMetricFamily('host_fs_size',
                                          'Host filesystem total capacity in bytes', None, ['device', 'mountpoint']),
        'host_fs_avail': GaugeMetricFamily('host_fs_avail',
                                           'Host filesystem available capacity in bytes', None, ['device', 'mountpoint']),
        'host_root_fs_size': GaugeMetricFamily('host_root_fs_size',
                                               'Host root filesystem available capacity in bytes', None,
                                               ['device', 'mountpoint']),
        'host_root_fs_avail': GaugeMetricFamily('host_root_fs_avail',
                                                'Host root filesystem available capacity in bytes', None,
                                                ['device', 'mountpoint']),
        'host_root_fs_used': GaugeMetricFamily('host_root_fs_used',
                                               'Host root filesystem used capacity in bytes', None,
                                               ['device', 'mountpoint'])
    }

    file_sizes = bash_o('df -k').splitlines()
    for i in range(1, len(file_sizes)):
        info = file_sizes[i].split()
        metrics['host_fs_size'].add_metric([info[0], info[5]], float(info[1])*1024)
        metrics['host_fs_avail'].add_metric([info[0], info[5]], float(info[3])*1024)
        if info[5] == '/':
            metrics['host_root_fs_size'].add_metric([info[0], info[5]], float(info[1])*1024)
            metrics['host_root_fs_avail'].add_metric([info[0], info[5]], float(info[3])*1024)
            metrics['host_root_fs_used'].add_metric([info[0], info[5]], float(info[2])*1024)

    zstack_used_capacity = 0
    for dir in zstack_dir:
        if not os.path.exists(dir):
            continue
        cmd = "du -bs %s | awk {\'print $1\'}" % dir
        res = bash_o(cmd)
        zstack_used_capacity += int(res)

    metrics['zstack_used_capacity_in_bytes'].add_metric([], float(zstack_used_capacity))
    return metrics.values()


kvmagent.register_prometheus_collector(collect_host_network_statistics)
kvmagent.register_prometheus_collector(collect_host_capacity_statistics)

class PrometheusPlugin(kvmagent.KvmAgent):

    COLLECTD_PATH = "/prometheus/collectdexporter/start"

    @kvmagent.replyerror
    @in_bash
    def start_collectd_exporter(self, req):

        @in_bash
        def start_exporter(cmd):
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

            cpid = linux.find_process_by_cmdline(['collectd', conf_path])
            mpid = linux.find_process_by_cmdline(['collectdmon', conf_path])

            if not cpid:
                bash_errorout('collectdmon -- -C %s' % conf_path)
            else:
                if need_restart_collectd:
                    if not mpid:
                        bash_errorout('kill -TERM %s' % cpid)
                        bash_errorout('collectdmon -- -C %s' % conf_path)
                    else:
                        bash_errorout('kill -HUP %s' % mpid)

            pid = linux.find_process_by_cmdline([cmd.binaryPath])
            if not pid:
                EXPORTER_PATH = cmd.binaryPath
                LOG_FILE = os.path.join(os.path.dirname(EXPORTER_PATH), cmd.binaryPath + '.log')
                ARGUMENTS = cmd.startupArguments
                if not ARGUMENTS:
                    ARGUMENTS = ""
                bash_errorout('chmod +x {{EXPORTER_PATH}}')
                bash_errorout("nohup {{EXPORTER_PATH}} {{ARGUMENTS}} >{{LOG_FILE}} 2>&1 < /dev/null &\ndisown")

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
                bash_r("iptables -w %s" % rule)

            bash_r("iptables -w -I INPUT -p tcp --dport %s -j ACCEPT" % port)

        rules = bash_o("iptables -w -S INPUT").splitlines()
        install_iptables_port(rules, 7069)
        install_iptables_port(rules, 9100)
        install_iptables_port(rules, 9103)

    def install_colletor(self):
        class Collector(object):
            def collect(self):
                try:
                    ret = []
                    for c in kvmagent.metric_collectors:
                        ret.extend(c())

                    return ret
                except Exception as e:
                    content = traceback.format_exc()
                    err = '%s\n%s\n' % (str(e), content)
                    logger.warn(err)
                    return []

        REGISTRY.register(Collector())

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.COLLECTD_PATH, self.start_collectd_exporter)

        self.install_colletor()
        start_http_server(7069)

    def stop(self):
        pass

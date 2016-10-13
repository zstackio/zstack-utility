from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils.bash import *
from zstacklib.utils import linux
from zstacklib.utils import thread
from jinja2 import Template
import os.path
import re
import time
import traceback

class PrometheusPlugin(kvmagent.KvmAgent):

    COLLECTD_PATH = "/prometheus/collectdexporter/start"

    @kvmagent.replyerror
    @in_bash
    def start_collectd_exporter(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        eths = bash_o("ls /sys/class/net").split()
        interfaces = []
        for eth in eths:
            eth = eth.strip(' \t\n\r')
            if eth == 'lo': continue
            elif eth.startswith('vnic'): continue
            elif eth.startswith('outer'): continue
            elif eth.startswith('br_'): continue
            elif not eth: continue
            else:
                interfaces.append(eth)

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
  Disk "/^sd/"
  Disk "/^hd/"
  Disk "/^vd/"
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

        pid = linux.find_process_by_cmdline(['collectd', conf_path])
        if not pid:
            bash_errorout('collectd -C %s' % conf_path)
        else:
            if need_restart_collectd:
                bash_errorout('kill -9 %s' % pid)
                bash_errorout('collectd -C %s' % conf_path)

        pid = linux.find_process_by_cmdline(['collectd_exporter'])
        if not pid:
            EXPORTER_PATH = cmd.binaryPath
            LOG_FILE = os.path.join(os.path.dirname(EXPORTER_PATH), 'collectd_exporter.log')
            bash_errorout('chmod +x {{EXPORTER_PATH}}')
            bash_errorout("nohup {{EXPORTER_PATH}} -collectd.listen-address :25826 >{{LOG_FILE}} 2>&1 < /dev/null &\ndisown")

        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.COLLECTD_PATH, self.start_collectd_exporter)

    def stop(self):
        pass

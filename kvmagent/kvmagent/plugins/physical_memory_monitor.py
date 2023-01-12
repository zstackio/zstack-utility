from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import thread
from zstacklib.utils import bash

log.configure_log('/var/log/zstack/zstack-kvmagent.log')
logger = log.get_logger(__name__)


class AgentRsp(object):
	def __init__(self):
		self.success = True
		self.error = None


class PhysicalMemoryECCErrorAlarm(object):
	def __init__(self):
		self.detail = None
		self.host = None


class PhysicalMemoryMonitor(kvmagent.KvmAgent):
	PHYSICAL_MEMORY_MONITOR = "/host/physical/memory/monitor/start"
	
	state = None
	time_lock = 0
	interval = 60
	
	def __init__(self):
		self.state = False
	
	def configure(self, config):
		self.config = config
	
	def start(self):
		http_server = kvmagent.get_http_server()
		http_server.register_async_uri(self.PHYSICAL_MEMORY_MONITOR, self.start_physical_memory_monitor)
	
	def stop(self):
		pass
	
	@kvmagent.replyerror
	def start_physical_memory_monitor(self, req):
		self.time_lock += 1
		self.state = True
		logger.debug("start monitor physical memory!")
		self.monitor_physical_memory_ecc_error(self.time_lock)
		return jsonobject.dumps(AgentRsp())
	
	@lock.lock('monitor_physical_memory_ecc_error')
	def monitor_physical_memory_ecc_error(self, time_lock_now):
		if time_lock_now != self.time_lock or not self.state:
			return
		
		'''
			title: monitor physical memory ECC_ERROR, include UE&&CE
			cmd: edac-util --report=default
			zero error return: "edac-util: No errors to report."
			non-zero error return: "csrow0: ch0: 43722040 Corrected Errors"
		'''
		r, o = bash.bash_ro("edac-util --report=default")
		if r == 0 and ("No errors to report" not in o and "No memory controller data found" in o):
			self.send_physical_memory_ecc_error_alarm_to_mn(o)
		
		thread.timer(self.interval, self.monitor_physical_memory_ecc_error, args=[time_lock_now]).start()
	
	def send_physical_memory_ecc_error_alarm_to_mn(self, detail):
		physical_memory_ecc_error_alarm = PhysicalMemoryECCErrorAlarm()
		physical_memory_ecc_error_alarm.host = self.config.get(kvmagent.HOST_UUID)
		physical_memory_ecc_error_alarm.detail = detail
		
		url = self.config.get(kvmagent.SEND_COMMAND_URL)
		if not url:
			raise kvmagent.KvmError(
				"cannot find SEND_COMMAND_URL, unable to transmit physical memory ecc error alarm info to management node")
		
		logger.debug('transmitting physical memory ecc error alarm info [detail:%s] to management node' % detail)
		http.json_dump_post(url, physical_memory_ecc_error_alarm,
							{'commandpath': '/host/physical/memory/ecc/error/alarm'})

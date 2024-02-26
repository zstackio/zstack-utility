import time

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import thread
from zstacklib.utils import iproute
from zstacklib.utils import linux
import zstacklib.utils.ip as ip_utils

log.configure_log('/var/log/zstack/zstack-kvmagent.log')
logger = log.get_logger(__name__)


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


class PhysicalNicAlarm(object):
    def __init__(self):
        self.nic = None
        self.ip = None
        self.bond = None
        self.status = None
        self.host = None

    def fill_none(self):
        if not self.nic:
            self.nic = 'None'
        if not self.ip:
            self.ip = 'None'
        if not self.bond:
            self.bond = 'None'
        if not self.status:
            self.status = 'None'


class NicStatusChangeEvent(object):
    def __init__(self, status):
        self.status = status
        self.change_time = time.time()


class PhysicalNicMonitor(kvmagent.KvmAgent):
    UPDATE_PHYSICAL_NIC_MONITOR_SETTINGS = "/host/physicalNic/update"
    TEST_PHYSICAL_NIC_MONITOR = "/host/physicalNic/test"
    ALARM_WAITING_TIME = 3

    bond_info = {}
    ip_info = {}
    nic_info = {}
    history_nics = []
    state = None
    time_lock = 0
    alarms_to_send = {}

    def __init__(self):
        super(PhysicalNicMonitor, self).__init__()
        self.state = False

    def configure(self, config):
        self.config = config

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.UPDATE_PHYSICAL_NIC_MONITOR_SETTINGS, self.update_physical_nic_monitor)
        http_server.register_async_uri(self.TEST_PHYSICAL_NIC_MONITOR, self.test_physical_nic_alarm)

    def stop(self):
        pass

    def initial_data(self, nics):
        for nic in nics:
            self.nic_info[nic.interfaceName] = (lambda x: 'up' if x is True else 'down')(nic.carrierActive)
            self.history_nics.append(nic.interfaceName)

    @lock.lock('physical_nic_monitor_send_to_mn')
    def send_to_mn(self, physical_nic_alarm):
        logger.debug('transmitting physical_nic alarm info [name:%s, status:%s] to management node' % (
            physical_nic_alarm.nic, physical_nic_alarm.status))
        physical_nic_alarm.host = self.config.get(kvmagent.HOST_UUID)
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            raise kvmagent.KvmError("cannot find SEND_COMMAND_URL, unable to transmit vm operation to management node")
        http.json_dump_post(url, physical_nic_alarm, {'commandpath': '/host/physicalNic/alarm'})

    def get_nic_info(self, nic, status):
        physical_nic_alarm = PhysicalNicAlarm()
        physical_nic_alarm.nic = nic
        physical_nic_alarm.status = status
        ip = []
        physical_nic_alarm.bond = linux.get_bond_info_by_nic(nic)
        if physical_nic_alarm.bond:
            self.bond_info[physical_nic_alarm.nic] = physical_nic_alarm.bond

        if physical_nic_alarm.bond:
            ip = linux.get_ipv4_addr_by_bond(physical_nic_alarm.bond)
        else:
            ip = linux.get_ipv4_addr_by_nic(physical_nic_alarm.nic)
        if len(ip) > 0:
            physical_nic_alarm.ip = ip[0]
            self.ip_info[physical_nic_alarm.nic] = ip[0]
        # fill old date when can not collage data
        if not physical_nic_alarm.bond:
            if physical_nic_alarm.nic in self.bond_info:
                physical_nic_alarm.bond = self.bond_info[physical_nic_alarm.nic]
        if not physical_nic_alarm.ip:
            if physical_nic_alarm.nic in self.ip_info:
                physical_nic_alarm.ip = self.ip_info[physical_nic_alarm.nic]
        # fill none when can not collage data
        physical_nic_alarm.fill_none()
        logger.debug('get_nic_info physical_nic alarm info [name:%s, status:%s, ip:%s, bond:%s] to management node' % (
            physical_nic_alarm.nic, physical_nic_alarm.status, physical_nic_alarm.ip, physical_nic_alarm.bond))
        return physical_nic_alarm

    @lock.lock('alarms_to_send')
    def add_alarm_to_send(self, nic, status):
        if nic not in self.history_nics:
            return
        nic_events = self.alarms_to_send.get(nic, [])
        nic_events.append(NicStatusChangeEvent(status))
        self.alarms_to_send[nic] = nic_events

    @lock.lock('alarms_to_send')
    def send_alarms(self):
        for nic, events in self.alarms_to_send.items():
            if len(events) == 0:
                continue

            last_time = events[-1].change_time
            current_time = time.time()
            if current_time - last_time < self.ALARM_WAITING_TIME:
                continue

            if len(events) % 2 == 0:
                status = events[-2].status
                self.send_to_mn(self.get_nic_info(nic, status))
                status = events[-1].status
                thread.timer(1, self.send_to_mn, args=(self.get_nic_info(nic, status),)).start()

            else:
                status = events[-1].status
                self.send_to_mn(self.get_nic_info(nic, status))

            self.alarms_to_send[nic] = []

        return True

    @kvmagent.replyerror
    def test_physical_nic_alarm(self, req):
        physical_nic_alarm_test = PhysicalNicAlarm()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        logger.debug(jsonobject.dumps(cmd))
        physical_nic_alarm_test.host = self.config.get(kvmagent.HOST_UUID)
        physical_nic_alarm_test.bond = 'bond0'
        physical_nic_alarm_test.ip = '192.168.1.1/24'
        physical_nic_alarm_test.nic = 'enp2s0'
        physical_nic_alarm_test.status = 'down'
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            raise kvmagent.KvmError("cannot find SEND_COMMAND_URL, unable to transmit vm operation to management node")
        logger.debug(
            'transmitting physical_nic alarm info [url:%s, host:%s] to management node' % (
                url, physical_nic_alarm_test.host))
        http.json_dump_post(url, physical_nic_alarm_test, {'commandpath': '/host/physicalNic/alarm'})
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def update_physical_nic_monitor(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if cmd.nics:
            self.time_lock += 1
            self.initial_data(cmd.nics)
            self.state = True  # start thread
            logger.debug("physical_nic monitor settings :state change to %s", jsonobject.dumps(self.state))
            thread.timer(1, self.physical_nic_monitor).start()
            thread.timer(1, self.send_alarms).start()
        return jsonobject.dumps(AgentRsp())

    @linux.retry(times=2, sleep_time=3)
    def physical_nic_monitor_get(self, ip):
        get_msg = ip.get()
        if get_msg is None or len(get_msg) == 0:
            return
        msg = get_msg[0]
        if 'event' in msg and msg['event'] == 'RTM_NEWLINK':
            nic = msg.get_attr('IFLA_IFNAME')
            status = msg.get_attr('IFLA_OPERSTATE').lower()
            if not nic or not status:
                return
            # update nic record
            for new_nic in ip_utils.find_host_physicl_nics():
                if new_nic not in self.history_nics:
                    self.history_nics.append(new_nic)
            # old nic alarm
            if nic in self.nic_info:
                if self.nic_info[nic] != status and ((status == 'down') or linux.get_nic_state_by_name(nic)):
                    logger.info("old physical_nic active detect, IfName[%s]---State[%s]" % (nic, status))
                    self.nic_info[nic] = status
                    self.add_alarm_to_send(nic, status)
            # new nic alarm
            else:
                if status != 'down' and nic in self.history_nics:
                    if linux.get_nic_state_by_name(nic):
                        logger.info("new physical_nic active detect, IfName[%s]---State[%s]" % (nic, status))
                        self.nic_info[nic] = status
                        self.add_alarm_to_send(nic, status)
                    else:
                        logger.warn("new physical_nic detect, but IfName[%s] has been down" % nic)

    @lock.lock('physical_nic_monitor')
    def physical_nic_monitor(self):
        time_lock_now = self.time_lock
        if self.state:
            ip = iproute.get_iproute()
            ip.bind()
            while True:
                if time_lock_now != self.time_lock:
                    break
                self.physical_nic_monitor_get(ip)

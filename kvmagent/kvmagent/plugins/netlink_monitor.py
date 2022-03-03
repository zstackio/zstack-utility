import os.path

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import thread
from zstacklib.utils import bash
from zstacklib.utils import iproute
from zstacklib.utils import linux

log.configure_log('/var/log/zstack/zstack-kvmagent.log')
logger = log.get_logger(__name__)


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class NetLinkAlarm(object):
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


class NetlinkMonitor(kvmagent.KvmAgent):
    UPDATE_NETLINK_MONITOR_SETTINGS = "/host/netlink/update"
    TEST_NETLINK_MONITOR = "/host/netlink/test"

    bond_info = {}
    ip_info = {}
    nic_info ={}
    state = None

    def __init__(self):
        self.state = False

    def configure(self, config):
        self.config = config

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.UPDATE_NETLINK_MONITOR_SETTINGS, self.update_netlink_monitor)
        http_server.register_async_uri(self.TEST_NETLINK_MONITOR, self.test_netlink_alarm)

    def stop(self):
        pass

    def initial_data(self, nics):
        for nic in nics:
            self.nic_info[nic] = nic.carrierActive

    @lock.lock('netlink_monitor_send_to_mn')
    def send_to_mn(self, netlink_alarm):
        logger.debug('transmitting netlink alarm info [name:%s, status:%s] to management node' % (
        netlink_alarm.nic, netlink_alarm.status))
        netlink_alarm.host = self.config.get(kvmagent.HOST_UUID)
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            raise kvmagent.KvmError("cannot find SEND_COMMAND_URL, unable to transmit vm operation to management node")
        http.json_dump_post(url, netlink_alarm, {'commandpath': '/host/netlink/alarm'})

    def get_nic_info(self, nic, status):
        netlink_alarm = NetLinkAlarm()
        netlink_alarm.nic = nic
        netlink_alarm.status = status
        ip = []
        netlink_alarm.bond = linux.get_bond_info_by_nic(nic)
        if netlink_alarm.bond:
            self.bond_info[netlink_alarm.nic] = netlink_alarm.bond

        if netlink_alarm.bond:
            ip = linux.get_ipv4_addr_by_bond(netlink_alarm.bond)
        else:
            ip = linux.get_ipv4_addr_by_nic(netlink_alarm.nic)
        if len(ip) > 0:
            netlink_alarm.ip = ip[0]
            self.ip_info[netlink_alarm.nic] = ip[0]
        # fill old date when can not collage data
        if not netlink_alarm.bond:
            if netlink_alarm.nic in self.bond_info:
                netlink_alarm.bond = self.bond_info[netlink_alarm.nic]
        if not netlink_alarm.ip:
            if netlink_alarm.nic in self.ip_info:
                netlink_alarm.ip = self.ip_info[netlink_alarm.nic]
        # fill none when can not collage data
        netlink_alarm.fill_none()
        logger.debug('get_nic_info netlink alarm info [name:%s, status:%s, ip:%s, bond:%s] to management node' % (
        netlink_alarm.nic, netlink_alarm.status, netlink_alarm.ip, netlink_alarm.bond))
        return netlink_alarm

    def send_alarm(self, nic, status):
        interface_all = get_host_physicl_nics()
        if nic not in interface_all and status == 'up':
            return
        self.send_to_mn(self.get_nic_info(nic, status))


    @kvmagent.replyerror
    def test_netlink_alarm(self, req):
        netlink_alarm_test = NetLinkAlarm()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        logger.debug(jsonobject.dumps(cmd))
        netlink_alarm_test.host = self.config.get(kvmagent.HOST_UUID)
        netlink_alarm_test.bond = 'bond0'
        netlink_alarm_test.ip = '192.168.1.1/24'
        netlink_alarm_test.nic = 'enp2s0'
        netlink_alarm_test.status = 'down'
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            raise kvmagent.KvmError("cannot find SEND_COMMAND_URL, unable to transmit vm operation to management node")
        logger.debug(
            'transmitting netlink alarm info [url:%s, host:%s] to management node' % (url, netlink_alarm_test.host))
        http.json_dump_post(url, netlink_alarm_test, {'commandpath': '/host/netlink/alarm'})
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def update_netlink_monitor(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if cmd.nics:
            self.state = True
            logger.debug("netlink monitor settings :state change to %s", jsonobject.dumps(self.state))
            self.initial_data(cmd.nics)
            thread.timer(1, self.netlink_monitor).start()
        return jsonobject.dumps(AgentRsp())

    @linux.retry(times=2, sleep_time=3)
    def netlink_monitor_get(self, ip):
        get_msg = ip.get()
        if len(get_msg) > 0:
            msg = get_msg[0]
        else:
            return
        if msg['event'] == 'RTM_NEWLINK':
            nic = msg.get_attr('IFLA_IFNAME')
            status = msg['state']
            if not nic or not status:
                return
            logger.info("netlink active detect, IfName[%s]---State[%s]" % (nic, status))
            if nic in self.nic_info:
                if self.nic_info[nic] != status:
                    logger.info("netlink active detect, IfName[%s]---State[%s]" % (nic, status))
                    self.nic_info[nic] = status
                    self.send_alarm(nic, status)
            else:
                logger.info("netlink active detect, IfName[%s]---State[%s]" % (nic, status))
                self.nic_info[nic] = status
                self.send_alarm(nic, status)

    @lock.lock('netlink_monitor')
    def netlink_monitor(self):
        if self.state:
            ip = iproute.get_iproute()
            ip.bind()
            while True:
                if not self.state:
                    break
                self.netlink_monitor_get(ip)

def get_host_physicl_nics():
    nic_names = bash.bash_o("find /sys/class/net -type l -not -lname '*virtual*' -printf '%f\\n'").splitlines()
    if nic_names is None or len(nic_names) == 0:
        return []
    nics = []
    for nic in nic_names:
        # exclude sriov vf nics
        if not os.path.exists("/sys/class/net/%s/device/physfn/" % nic):
            nics.append(nic)
    return nics

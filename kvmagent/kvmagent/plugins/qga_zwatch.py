import os.path
import time
import libvirt
import json
import threading

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import thread
from zstacklib.utils.qga import VmQga
from kvmagent.plugins import vm_plugin

log.configure_log('/var/log/zstack/zstack-kvmagent.log')
logger = log.get_logger(__name__)


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


class ZWatchMetricMonitor(kvmagent.KvmAgent):
    TEST_ZWATCH_METRIC_MONITOR = "/host/zwatchMetricMonitor/test"
    INIT_ZWATCH_METRIC_MONITOR = "/host/zwatchMetricMonitor/init"
    CONFIG_ZWATCH_METRIC_MONITOR = "/host/zwatchMetricMonitor/config"

    ZWATCH_RESTART_CMD = "/bin/systemctl restart zwatch-vm-agent.service"
    ZWATCH_RESTART_CMD_EL6 = "service zwatch-vm-agent restart"
    ZWATCH_VM_INFO_PATH = "/var/log/zstack/vm.info"
    ZWATCH_VM_METRIC_PATH = "/var/log/zstack/vm_metrics.prom"
    ZWATCH_GET_NIC_INFO_PATH = "/usr/local/zstack/zs-tools/nic_info_linux.sh"

    WIN_ZWATCH_BASE_PATH = "C:\\Program Files\\GuestTools"
    WIN_ZWATCH_RESTART_CMD = "Restart-Service|zstack_zwatch_agent"
    WIN_ZWATCH_VM_INFO_PATH = WIN_ZWATCH_BASE_PATH + "\\" + "vm.info"
    WIN_ZWATCH_VM_METRIC_PATH = WIN_ZWATCH_BASE_PATH + "\\" + "vm_metrics.prom"
    WIN_ZWATCH_GET_NIC_INFO_PATH = WIN_ZWATCH_BASE_PATH + "\\" + "zs-tools\\nic_info_win.ps1"

    PROMETHEUS_PUSHGATEWAY_URL = "http://127.0.0.1:9092/metrics/job/zwatch_vm_agent/vmUuid/"

    state = None
    push_interval_time = 10
    scan_interval_time = 30

    def __init__(self):
        self.state = False
        self.vm_list = {}
        self.vm_nic_info = {}
        self.running_vm_list = []
        self.qga_state = {}
        self.tools_state = {}
        self.running_vm_lock = threading.Lock()
        self.zwatch_qga_lock = threading.Lock()

    def configure(self, config):
        self.config = config

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_ZWATCH_METRIC_MONITOR, self.init_zwatch_qga_monitor)
        http_server.register_async_uri(self.CONFIG_ZWATCH_METRIC_MONITOR, self.config_zwatch_qga_monitor)

    def stop(self):
        pass

    @thread.AsyncThread
    def zwatch_qga_monitor(self):
        if self.zwatch_qga_lock.acquire(False):
            try:
                if not self.state:
                    return
                while True:
                    try:
                        if not self.state or http.AsyncUirHandler.STOP_WORLD:
                            break
                        domains = get_domains()
                        vm_states, vm_dict = get_guest_tools_states(domains)
                        self.report_vm_qga_state({
                            vmUuid: qgaStatus.qgaRunning for vmUuid, qgaStatus in vm_states.items()
                        }, {
                            vmUuid: qgaStatus.zsToolsFound for vmUuid, qgaStatus in vm_states.items()
                        })
                        # remove stopped vm which in running_vm_list
                        logger.debug('current QGA running vm list (count: %d): %s' %
                                     (len(self.running_vm_list), self.running_vm_list))
                        last_monitor_vm_list = self.running_vm_list[:]
                        with self.running_vm_lock:
                            self.running_vm_list = [
                                vmUuid for vmUuid, qgaStatus in vm_states.items() if qgaStatus.qgaRunning
                            ]
                        new_vm_list = set(self.running_vm_list) - set(last_monitor_vm_list)
                        logger.debug('recently detected vm list without QGA (count: %d): %s' %
                                     (len(new_vm_list), new_vm_list))
                        for vmUuid in new_vm_list:
                            # new vm found
                            qga = vm_dict.get(vmUuid)
                            if qga:
                                self.zwatch_qga_monitor_vm(vmUuid, qga)
                        for vmUuid in self.running_vm_list:
                            qga = vm_dict.get(vmUuid)
                            if qga:
                                self.qga_get_vm_nic(vmUuid, qga)
                        time.sleep(self.scan_interval_time)
                    except Exception as e:
                        logger.debug('qga zwatch monitor reboot, crash due to [%s]' % str(e))
                        time.sleep(self.scan_interval_time)
            finally:
                self.zwatch_qga_lock.release()
        else:
            pass

    @thread.AsyncThread
    def qga_get_vm_nic(self, uuid, qga):
        try:
            if qga.os and 'mswindows' in qga.os:
                zwatch_nic_info_path = self.WIN_ZWATCH_GET_NIC_INFO_PATH
            else:
                zwatch_nic_info_path = self.ZWATCH_GET_NIC_INFO_PATH
            nicInfoStatus = qga.guest_file_is_exist(zwatch_nic_info_path)
            if not nicInfoStatus:
                return
            if is_windows_2008(qga):
                nicInfo = get_nic_info_for_windows_2008(uuid, qga)
            else:
                nicInfo = qga.guest_exec_cmd_no_exitcode(zwatch_nic_info_path)
            nicInfo = str(nicInfo).strip()
            need_update = False
            if not self.vm_nic_info.get(uuid):
                need_update = True
            elif isinstance(nicInfo, str) and isinstance(self.vm_nic_info[uuid], str):
                need_update = nicInfo != self.vm_nic_info[uuid]
            if need_update:
                self.vm_nic_info[uuid] = nicInfo
                self.send_nic_info_to_mn(uuid, self.vm_nic_info[uuid])
        except Exception as e:
            logger.debug('vm[%s] read nic info by qga failed due to [%s]' % (uuid, str(e)))
            return

    @thread.AsyncThread
    def zwatch_qga_monitor_vm(self, uuid, qga):
        while True:
            try:
                if uuid not in self.running_vm_list:
                    logger.debug('vm[%s] has been stop running' % uuid)
                    break
                if qga.os and 'mswindows' in qga.os:
                    zwatch_vm_info_path = self.WIN_ZWATCH_VM_INFO_PATH
                    zwatch_vm_metric_path = self.WIN_ZWATCH_VM_METRIC_PATH
                    zwatch_restart_cmd = self.WIN_ZWATCH_RESTART_CMD
                else:
                    zwatch_vm_info_path = self.ZWATCH_VM_INFO_PATH
                    zwatch_vm_metric_path = self.ZWATCH_VM_METRIC_PATH
                    zwatch_restart_cmd = self.ZWATCH_RESTART_CMD
                    # centos version 6.x need special cmd
                    if qga.os_version == '6':
                        zwatch_restart_cmd = self.ZWATCH_RESTART_CMD_EL6
                dhcpStatus = not qga.guest_file_is_exist(zwatch_vm_info_path)
                # skip when dhcp enable
                if dhcpStatus:
                    with self.running_vm_lock:
                        self.running_vm_list.remove(uuid)
                    break
                _, qgaZWatch = qga.guest_file_read(zwatch_vm_info_path)
                logger.debug('vm[%s] start monitor with qga' % uuid)
                # set vmUuid by qga at first
                if qgaZWatch != uuid:
                    logger.debug('vm[%s] init zwatch qga vm.info first...' % uuid)
                    ret = qga.guest_file_write(zwatch_vm_info_path, uuid)
                    if ret == 0:
                        logger.debug('config vm[%s], write qga zwatch qga vm.info failed' % uuid)
                        with self.running_vm_lock:
                            self.running_vm_list.remove(uuid)
                        break
                    # switch zwatch mode to qga
                    qga.guest_exec_cmd_no_exitcode(zwatch_restart_cmd)
                # fetch zwatch metrics
                _, vmMetrics = qga.guest_file_read(zwatch_vm_metric_path)
                if vmMetrics:
                    push_metrics_to_gateway(self.PROMETHEUS_PUSHGATEWAY_URL, uuid, vmMetrics)
                time.sleep(self.push_interval_time)
            except Exception as e:
                logger.debug('vm[%s] end monitor with qga due to [%s]' % (uuid, str(e)))
                with self.running_vm_lock:
                    self.running_vm_list.remove(uuid)
                break

    @kvmagent.replyerror
    def config_zwatch_qga_monitor(self, req):
        self.state = False
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def init_zwatch_qga_monitor(self, req):
        self.state = True
        self.zwatch_qga_monitor()
        return jsonobject.dumps(AgentRsp())

    @lock.lock('qga_nic_info_send_to_mn')
    def send_nic_info_to_mn(self, uuid, nic_info):
        logger.debug('transmitting vm nic info [ vm:[%s], nicInfo:[%s] ] to management node' % (
            uuid, nic_info))
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            raise kvmagent.KvmError("cannot find SEND_COMMAND_URL, unable to transmit vm operation to management node")
        http.json_dump_post(url, VmNicInfo(uuid, nic_info), {'commandpath': '/vm/nicinfo/sync'})

    @lock.lock('qga_state_report_to_mn')
    def report_vm_qga_state(self, qga_state, tools_state):
        if not qga_state or not tools_state:
            return
        if self.qga_state == qga_state and self.tools_state == tools_state:
            return
        else:
            self.qga_state = qga_state
            self.tools_state = tools_state
        qga_state_json = json.dumps(self.qga_state)
        tools_state_json = json.dumps(self.tools_state)
        logger.debug('transmitting vm qga state [%s] and tools state [%s] to management node' % (
            qga_state_json, tools_state_json))
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            raise kvmagent.KvmError("cannot find SEND_COMMAND_URL, unable to transmit vm operation to management node")
        http.json_dump_post(url, VmQgaState(qga_state_json, tools_state_json), {'commandpath': '/vm/qgastate/report'})


class VmQgaStatus:
    def __init__(self):
        self.qgaRunning = False
        self.zsToolsFound = False
        self.version = ""
        self.platForm = ""
        self.osType = ""


class VmNicInfo:
    def __init__(self, uuid, nic_info):
        self.vmUuid = uuid
        self.nicInfo = nic_info


class VmQgaState:
    def __init__(self, qga_state, tools_state):
        self.qgaState = qga_state
        self.toolsState = tools_state


@vm_plugin.LibvirtAutoReconnect
def get_domains(conn):
    dom_ids = conn.listDomainsID()
    doms = []
    for dom_id in dom_ids:
        try:
            domain = conn.lookupByID(dom_id)
        except libvirt.libvirtError as ex:
            if ex.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                continue
            raise ex
        uuid = domain.name()
        if uuid.startswith("guestfs-"):
            continue
        if uuid == "ZStack Management Node VM":
            continue
        doms.append(domain)
    return doms


def get_guest_tools_states(domains):
    def get_state(domain):
        qga_status = VmQgaStatus()
        vm_state, _, _, _, _ = domain.info()
        if vm_state != vm_plugin.Vm.VIR_DOMAIN_RUNNING:
            return qga_status
        qga = VmQga(domain)
        if qga.state != VmQga.QGA_STATE_RUNNING:
            return qga_status
        qga_status.qgaRunning = True
        qga_status.osType = '{} {}'.format(qga.os, qga.os_version)
        if qga.os and 'mswindows' in qga.os:
            qga_status.platForm = 'Windows'
            try:
                ret = qga.guest_file_is_exist(VmQga.ZS_TOOLS_PATN_WIN)
                if not ret:
                    logger.debug("open {} failed".format(VmQga.ZS_TOOLS_PATN_WIN))
                    return qga_status
                qga_status.zsToolsFound = True
                return qga_status
            except Exception as e:
                logger.debug("get vm {} guest-info failed {}".format(domain, e))
                return qga_status
        else:
            qga_status.platForm = 'Linux'
            try:
                _, config = qga.guest_file_read('/usr/local/zstack/guesttools')
                if not config:
                    logger.debug("read /usr/local/zstack/guesttools failed")
                    return qga_status
            except Exception as e:
                logger.debug("read /usr/local/zstack/guesttools failed {}".format(e))
                return qga_status

        qga_status.zsToolsFound = True

        version_config = [line for line in config.split('\n') if 'version' in line]
        if version_config:
            qga_status.version = version_config[0].split('=')[1].strip()

        return qga_status

    vm_states = {dom.name(): get_state(dom) for dom in domains}
    vm_dict = {dom.name(): VmQga(dom) if dom else None for dom in domains}
    return vm_states, vm_dict


def push_metrics_to_gateway(url, uuid, metrics):
    url = url + uuid
    metrics += "\n\n"
    headers = {
        "Content-Type": "application/json"
    }
    rsp = http.json_post(url, body=metrics, headers=headers)
    logger.debug('vm[%s] push metric with rsp[%s]' % (uuid, rsp))


def is_windows_2008(qga):
    return qga.os and 'mswindows' in qga.os and '2008r2' in qga.os_version


def subnet_mask_to_prefix_length(mask):
    return sum(bin(int(x)).count('1') for x in mask.split('.'))


def get_nic_info_for_windows_2008(uuid, qga):
    exitcode, ret_data = qga.guest_exec_wmic(
        "nicconfig where IPEnabled=True get InterfaceIndex, IPaddress, IPSubnet, MACAddress /FORMAT:csv")
    if exitcode != 0:
        logger.debug('vm[%s] get nic info failed: %s' % (uuid, ret_data))
        return None

    lines = ret_data.replace('\r', '').strip().split('\n')
    mac_to_ip = {}
    for line in lines:
        logger.debug('vm[%s] get nic info line: [%s]' % (uuid, line))
        columns = line.split(',')
        if len(columns) < 5:
            logger.debug('vm[%s] skipping line: [%s]' % (uuid, line))
            continue
        else:
            raw_ip_addresses = columns[2].strip('{}').split(';')
            raw_ip_subnets = columns[3].strip('{}').split(';')
            mac_address = columns[4].strip().lower()

            if not len(mac_address.split(':')) == 6:
                continue

            ip_addresses_with_subnets = []
            for ip, subnet in zip(raw_ip_addresses, raw_ip_subnets):
                if '.' in subnet:  # Check if this is an IPv4 subnet mask
                    prefix_length = subnet_mask_to_prefix_length(subnet)
                    ip_addresses_with_subnets.append("{}/{}".format(ip, prefix_length))
                else:  # Assume this is an IPv6 subnet in prefix length format
                    ip_addresses_with_subnets.append("{}/{}".format(ip, subnet))

            mac_to_ip[mac_address] = ip_addresses_with_subnets

    mac_to_ip_json = json.dumps(mac_to_ip, indent=4)
    logger.debug('vm[%s] get nic info all: [%s]' % (uuid, mac_to_ip_json))
    return mac_to_ip_json


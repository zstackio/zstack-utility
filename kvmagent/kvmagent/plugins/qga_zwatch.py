import os.path
import time
import libvirt

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
    ZWATCH_VM_INFO_PATH = "/var/log/zstack/vm.info"
    ZWATCH_VM_METRIC_PATH = "/var/log/zstack/vm_metrics.prom"

    WIN_ZWATCH_BASE_PATH = "C:\\Program Files\\GuestTools"
    WIN_ZWATCH_RESTART_CMD = "Restart-Service -Name zstack_zwatch_agent"
    WIN_ZWATCH_VM_INFO_PATH = WIN_ZWATCH_BASE_PATH + "\\" + "vm.info"
    WIN_ZWATCH_VM_METRIC_PATH = WIN_ZWATCH_BASE_PATH + "\\" + "vm_metrics.prom"

    PROMETHEUS_PUSHGATEWAY_URL = "http://127.0.0.1:9092/metrics/job/zwatch_vm_agent/vmUuid/"

    state = None
    push_interval_time = 10
    scan_interval_time = 30

    def __init__(self):
        self.state = False
        self.vm_list = {}
        self.running_vm_list = []

    def configure(self, config):
        self.config = config

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_ZWATCH_METRIC_MONITOR, self.init_zwatch_qga_monitor)
        http_server.register_async_uri(self.CONFIG_ZWATCH_METRIC_MONITOR, self.config_zwatch_qga_monitor)

    def stop(self):
        pass

    @lock.lock('zwatch_qga_monitor')
    def zwatch_qga_monitor(self):
        if self.state:
            while True:
                if not self.state:
                    break
                logger.debug('update vm list')
                domains = get_domains()
                tools_states, vm_dict = get_guest_tools_states(domains)
                # remove stopped vm which in running_vm_list
                logger.debug('debug: vm list: %s' % self.running_vm_list)
                last_monitor_vm_list = self.running_vm_list
                self.running_vm_list = [vmUuid for vmUuid, qgaStatus in tools_states.items() if qgaStatus.qgaRunning]
                new_vm_list = set(self.running_vm_list) - set(last_monitor_vm_list)
                logger.debug('debug: new vm list: %s' % new_vm_list)
                for vmUuid in new_vm_list:
                    # new vm found
                    qga = vm_dict.get(vmUuid)
                    qga and self.zwatch_qga_monitor_vm(vmUuid, qga)
                time.sleep(self.scan_interval_time)

    @thread.AsyncThread
    def zwatch_qga_monitor_vm(self, uuid, qga):
        while True:
            try:
                if uuid not in self.running_vm_list:
                    logger.debug('vm[%s] has been stop running' % uuid)
                    break
                if "mswindows" in qga.os:
                    zwatch_vm_info_path = self.WIN_ZWATCH_VM_INFO_PATH
                    zwatch_vm_metric_path = self.WIN_ZWATCH_VM_METRIC_PATH
                    zwatch_restart_cmd = self.WIN_ZWATCH_RESTART_CMD
                else:
                    zwatch_vm_info_path = self.ZWATCH_VM_INFO_PATH
                    zwatch_vm_metric_path = self.ZWATCH_VM_METRIC_PATH
                    zwatch_restart_cmd = self.ZWATCH_RESTART_CMD
                dhcpStatus = not qga.guest_file_is_exist(zwatch_vm_info_path)
                _, qgaZWatch = qga.guest_file_read(zwatch_vm_info_path)
                # skip when dhcp enable
                if dhcpStatus:
                    self.running_vm_list.remove(uuid)
                    break
                logger.debug('vm[%s] start monitor with qga' % uuid)
                # set vmUuid by qga at first
                if qgaZWatch != uuid:
                    logger.debug('vm[%s] init zwatch qga vm.info first...' % uuid)
                    ret = qga.guest_file_write(zwatch_vm_info_path, uuid)
                    if ret == 0:
                        logger.debug('config vm[%s], write qga zwatch qga vm.info failed' % uuid)
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


class VmQgaStatus:
    def __init__(self):
        self.qgaRunning = False
        self.zsToolsFound = False
        self.version = ""
        self.platForm = ""
        self.osType = ""


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
        if 'mswindows' in qga.os:
            qga_status.platForm = 'Windows'
        else:
            qga_status.platForm = 'Linux'
        return qga_status

    tools_states = {dom.name(): get_state(dom) for dom in domains}
    vm_dict = {dom.name(): VmQga(dom) if dom else None for dom in domains}
    return tools_states, vm_dict


def push_metrics_to_gateway(url, uuid, metrics):
    url = url + uuid
    metrics += "\n\n"
    headers = {
        "Content-Type": "application/json"
    }
    rsp = http.json_post(url, body=metrics, headers=headers)
    logger.debug('vm[%s] push metric with rsp[%s]' % (uuid, rsp))

from jinja2 import Template

import time
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import linux
from zstacklib.utils.bash import *
from zstacklib.utils import thread
from zstacklib.utils import http

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class ReportHostGatewayChangeCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.expectedGateway = None
        self.gateway = None
        self.repair = None

class ReportSuricataCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.content = None
        self.src_ip = None
        self.src_port = None
        self.dst_ip = None
        self.dst_port = None
        self.repair = None

class ReportVmGatewayChangeCmd(object):
    def __init__(self):
        self.vmInstanceUuid = None
        self.expectedGateway = None
        self.gateway = None
        self.repair = None

class VmGatewayChangedRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(kvmagent.AgentResponse, self).__init__()


class SecurityInspection(kvmagent.KvmAgent):

    START_SECURITY_INPSECTION_PATH = "/networkSecurityInspection/start"
    VM_GATEWAY_CHANGED_PATH = "/host/kvm/VmGatewayChanged"
    SURICATA_FAST_LOG_FILE = "/var/log/suricata/fast.log"
    ACTION_ALARM = "alarmOnly"
    ACTION_REPAIR = "alarmAndRepair"

    action = ACTION_ALARM
    line = 0
    url = None
    host_uuid = None
    expected_gateway_ip = None
    start_time = None

    @kvmagent.replyerror
    def vm_gateway_changed(self, req):
        rsp = VmGatewayChangedRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        result = ReportVmGatewayChangeCmd()
        result.vmInstanceUuid = cmd.vmInstanceUuid
        result.expectedGateway = cmd.expectedGateway
        result.gateway = cmd.gateway
        result.repair = cmd.repair

        logger.debug('transmitting vm gateway changed [uuid:{0}] cmd [expectedGateway:{1}, gateway: {2}, repair:{3}] to management node'
                     .format(cmd.vmInstanceUuid, cmd.expectedGateway, cmd.gateway, cmd.repair))
        # http.json_dump_post(self.url, result, {'commandpath': '/kvm/VmGatewayChanged'})
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def start_security_inspection(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        # self.action = cmd.action
        # self.start_time = time.time()
        # ifNames = cmd.suricataInterface.split(",")
        # ifParams = " ".join("-i {0}".format(x) for x in ifNames)

        # r, o, e = bash_roe("echo '' > {0}; pids=`pidof /usr/local/bin/suricata`; for pid in $pids; do kill $pid; done;rm -rf /usr/local/var/run/suricata.pid; /usr/local/bin/suricata -c /etc/suricata/suricata.yaml -l /var/log/suricata/ {1} -D"
        #                    .format(self.SURICATA_FAST_LOG_FILE, ifParams))
        # if r != 0:
        #     rsp.success = False
        #     rsp.error = e
        #     return jsonobject.dumps(rsp)

        # gatewayTimer = thread.timer(cmd.gatewayCheckInterval, self._gateway_inspection,
        #                             args=[self.start_time], stop_on_exception=False)
        # gatewayTimer.start()

        # suricateTimer = thread.timer(cmd.suricataInterval, self._suricata_inspection,
        #                              args=[self.start_time], stop_on_exception=False)
        # suricateTimer.start()

        # this is an operation outside zstack, report it
        self.url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not self.url:
            rsp.success = False
            rsp.error = 'cannot find SEND_COMMAND_URL, unable to ask the mgmt server to reconnect us'
            return jsonobject.dumps(rsp)

        self.host_uuid = self.config.get(kvmagent.HOST_UUID)
        if not self.host_uuid:
            rsp.success = False
            rsp.error = 'cannot find HOST_UUID, unable to ask the mgmt server to reconnect us'
            return jsonobject.dumps(rsp)

        self.expected_gateway_ip = cmd.gateway_ip

        host_config = """
{
   "hostUuid":"{HOST_UUID}",
   "hostExpectedGateway":"{HOST_EXPECTED_GATE_WAY}",
   "vmExpectedGateway":"172.20.0.1",
   "callbackUrl":"172.21.0.201:8080/zstack/asyncrest/sendcommand"
}
""".format(HOST_UUID=self.host_uuid,
           HOST_EXPECTED_GATE_WAY=self.expected_gateway_ip)
           
        with open("/var/lib/zstack/ioControl/host.json", 'w') as fd:
            fd.write(host_config)

        bash_roe("/var/lib/zstack/ioControl/ioControl -s /var/lib/zstack/ioControl/host.json")

        return jsonobject.dumps(rsp)

    #suppose there is only 1 gateway
    @in_bash
    def _gateway_inspection(self, start_time):
        if start_time != self.start_time:
            logger.debug('old timer detected!!! start at '.format(time.asctime(time.localtime(start_time))))
            return False

        gateway = bash_o("ip route | grep default | awk '{print $3}'").strip()
        if self.expected_gateway_ip == gateway:
            return True

        logger.debug('detected host {0} default gateway change to {1}'.format(self.host_uuid, gateway))

        # cmd = ReportHostGatewayChangeCmd()
        # cmd.hostUuid = self.host_uuid
        # cmd.expectedGateway = self.expected_gateway_ip
        # cmd.gateway = gateway
        # cmd.repair = False
        # http.json_dump_post(self.url, cmd, {'commandpath': '/kvm/HostGatewayChanged'})

        # if self.action == self.ACTION_REPAIR:
        #     cmds =[]
        #     gateways = gateway.split("\n")
        #     for g in gateways:
        #         if g != "":
        #             cmds.append("ip route del default via {0}".format(g))
        #     cmds.append("ip route add default via {0}".format(self.expected_gateway_ip))
        #     r, o, e = bash_roe(";".join(cmds))
        #     if r != 0:
        #         logger.debug('restore default route failed: error {0}, output {1}'.format(e, o))
        #     else:
        #         gateway = bash_o("ip route | grep default | awk '{print $3}'").strip()
        #         cmd.gateway = gateway
        #         cmd.repair = True
        #         http.json_dump_post(self.url, cmd, {'commandpath': '/kvm/HostGatewayChanged'})

        return True

    @in_bash
    def _suricata_inspection(self, start_time):

        def getTupleFromAlert(alert):
            ''' alert format:
            01/16/2020-15:57:26.801360  [**] [1:1:1] http proxy alert [**] [Classification: Targeted Malicious Activity was Detected] [Priority: 1] {TCP} 10.86.4.243:54538 -> 10.86.4.175:80
            '''
            items = alert.split("}")
            if len(items) < 2:
                return False, "", "", "", "",

            itemss = items[1].split("->")
            if len(itemss) < 2:
                return False, "", "", "", "",

            src = itemss[0].strip().split(":")
            dst = itemss[1].strip().split(":")

            return True, src[0], src[1], dst[0], dst[1]

        if start_time != self.start_time:
            logger.debug('old timer detected!!! start at '.format(time.asctime(time.localtime(start_time))))
            return False

        content = linux.read_file(self.SURICATA_FAST_LOG_FILE).strip()
        alerts = content.split("\n")
        if len(alerts) <= self.line:
            # no new lines
            return True

        line = 0
        for alert in alerts:
            if alert.strip() == "":
                continue

            line = line + 1
            #skip old line
            if line <= self.line:
                continue

            cmd = ReportSuricataCmd()
            cmd.hostUuid = self.host_uuid
            cmd.content = alert
            cmd.repair = False
            success, src_ip, src_port, dst_ip, dst_port = getTupleFromAlert(alert)
            if success:
                cmd.src_ip = src_ip
                cmd.src_port = src_port
                cmd.dst_ip = dst_ip
                cmd.dst_port = dst_port

            # http.json_dump_post(self.url, cmd, {'commandpath': '/kvm/invalidHttpProxy'})

            # if self.action == self.ACTION_REPAIR:
            #     r, o, e = bash_roe(
            #         """iptables -D OUTPUT -d {0}/32 -p tcp -m comment --comment 'block invalid http proxy' -m tcp --dport {1} -j DROP;
            #          iptables -D FORWARD -d {0}/32 -p tcp -m comment --comment 'block invalid http proxy' -m tcp --dport {1} -j DROP;
            #          iptables -I OUTPUT -d {0}/32 -p tcp -m comment --comment 'block invalid http proxy' -m tcp --dport {1} -j DROP;
            #          iptables -I FORWARD -d {0}/32 -p tcp -m comment --comment 'block invalid http proxy' -m tcp --dport {1} -j DROP;"""
            #             .format(dst_ip, dst_port))
            #     if r != 0:
            #         logger.debug('blocked invalid http proxy failed: error {0}, output {1}'.format(e, o))
            #     else:
            #         cmd.content = ("""iptables -I OUTPUT -d {0}/32 -p tcp -m comment --comment 'block invalid http proxy' -m tcp --dport {1} -j DROP;
            #                           iptables -I FORWARD -d {0}/32 -p tcp -m comment --comment 'block invalid http proxy' -m tcp --dport {1} -j DROP"""
            #                        .format(dst_ip, dst_port))
            #         cmd.repair = True
            #         http.json_dump_post(self.url, cmd, {'commandpath': '/kvm/invalidHttpProxy'})

        self.line = line

        return True

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.START_SECURITY_INPSECTION_PATH, self.start_security_inspection)
        http_server.register_sync_uri(self.VM_GATEWAY_CHANGED_PATH, self.vm_gateway_changed)

    def stop(self):
        pass

    def configure(self, config):
        self.config = config
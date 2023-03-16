import libvirt
from kvmagent.plugins import vm_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils.qga import VmQga

from kvmagent import kvmagent

ZSTACK_START_COMMENT = "Generated by zstack customization engine. Do not edit."

logger = log.get_logger(__name__)


class VmQgaStatus:
    def __init__(self):
        self.qgaRunning = False
        self.zsToolsFound = False
        self.version = ""
        self.platForm = ""
        self.osType = ""


def get_virt_domain(vmUuid):
    try:
        @vm_plugin.LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(vmUuid)

        return call_libvirt(vmUuid)
    except libvirt.libvirtError as e:
        error_code = e.get_error_code()
        if error_code == libvirt.VIR_ERR_NO_DOMAIN:
            return None
        err = 'error happened when looking up vm[uuid:%(uuid)s], libvirt error code: %(error_code)s, %(e)s' % locals()
        raise libvirt.libvirtError(err)


def get_guest_tools_states():
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

            doms.append(domain)
        return doms

    def check_guest_tools_state(domain):
        qga_status = VmQgaStatus()

        vm_state, _, _, _, _ = domain.info()
        if vm_state != vm_plugin.Vm.VIR_DOMAIN_RUNNING:
            return qga_status

        qga = VmQga(domain)
        if qga.state != VmQga.QGA_STATE_RUNNING:
            return qga_status

        qga_status.qgaRunning = True
        qga_status.osType = '{} {}'.format(qga.os, qga.os_version)
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

    tools_states = {}
    domains = get_domains()
    for dom in domains:
        uuid = dom.name()
        if uuid.startswith("guestfs-"):
            continue
        if uuid == "ZStack Management Node VM":
            continue

        state = check_guest_tools_state(dom)
        if state:
            tools_states[uuid] = state

    return tools_states


class VmConfigSyncResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(VmConfigSyncResponse, self).__init__()
        self.errorCode = None


class GetGuestToolsStateResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetGuestToolsStateResponse, self).__init__()
        self.states = None


class VmConfigPlugin(kvmagent.KvmAgent):
    VM_CONFIG_PORTS = "/vm/configsync/ports"
    VM_GUEST_TOOLS_STATE = "/vm/guesttools/state"

    VM_QGA_PARAM_FILE = "/usr/local/zstack/zs-nics.json"
    VM_QGA_CONFIG_LINUX_CMD = "/usr/local/zstack/zs-tools/config_linux.py"
    VM_CONFIG_SYNC_OS_VERSION_SUPPORT = {
        VmQga.VM_OS_LINUX_CENTOS: ("7", "8"),
        VmQga.VM_OS_LINUX_KYLIN: ("v10",),
        VmQga.VM_OS_LINUX_UOS: ("20",)
    }

    @lock.lock('config_vm_by_qga')
    def config_vm_by_qga(self, domain, nicParams):

        vm_uuid = domain.name()
        qga = VmQga(domain)
        if qga.state != VmQga.QGA_STATE_RUNNING:
            return 1, "qga is not running for vm {}".format(vm_uuid)

        if qga.os in VmConfigPlugin.VM_CONFIG_SYNC_OS_VERSION_SUPPORT.keys() and \
                qga.os_version in VmConfigPlugin.VM_CONFIG_SYNC_OS_VERSION_SUPPORT[qga.os]:
            cmd_file = self.VM_QGA_CONFIG_LINUX_CMD
        else:
            return 1, "not support for os {}".format(qga.os)

        # write command to a file
        ret = qga.guest_file_write(self.VM_QGA_PARAM_FILE, jsonobject.dumps(nicParams))
        if ret == 0:
            logger.debug("config vm {}, write parameters file {} failed".format(vm_uuid, self.VM_QGA_PARAM_FILE))
            return 1, "config vm {}, write parameters file {} failed".format(vm_uuid, self.VM_QGA_PARAM_FILE)

        # exec qga command
        ret, msg = qga.guest_exec_python(cmd_file)
        if ret != 0:
            logger.debug("config vm {} by qga failed: {}".format(vm_uuid, msg))
            return 1, "config vm {} by qga failed: {}".format(vm_uuid, msg)

        return 0, msg

    @kvmagent.replyerror
    def vm_config_ports(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VmConfigSyncResponse()

        domain = get_virt_domain(cmd.vmUuid)
        if not domain or not domain.isActive():
            rsp.success = False
            rsp.error = 'vm {} not running'.format(cmd.vmUuid)
            return jsonobject.dumps(rsp)

        ret, msg = self.config_vm_by_qga(domain, cmd.portsConfig)
        if ret != 0:
            rsp.success = False
            rsp.error = msg
        else:
            logger.debug("config vm {} by qga successfully, detail info {}", cmd.vmUuid, msg)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def vm_guest_tools_state(self, req):
        rsp = GetGuestToolsStateResponse()
        rsp.states = get_guest_tools_states()
        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.VM_CONFIG_PORTS, self.vm_config_ports)
        http_server.register_async_uri(self.VM_GUEST_TOOLS_STATE, self.vm_guest_tools_state)

    def stop(self):
        pass

    def configure(self, config=None):
        pass


if __name__ == "__main__":
    str_config = '''{
    "portsConfig":{
        "ports":[
            {
                "mac":"fa:4a:4e:74:49:00",
                "mtu":1500,
                "vmIps":[
                    {
                        "proto":"dhcp",
                        "version":4,
                        "dns":[
                            "223.5.5.5",
                            "7.7.7.7"
                        ],
                        "ip":"172.25.116.171",
                        "netmask":"255.255.0.0",
                        "gateway": "172.25.0.1"
                    }
                ]
            },
            {
                "mac":"fa:1c:c7:de:4a:01",
                "mtu":1500,
                "vmIps":[
                    {
                        "ip":"10.2.2.219",
                        "netmask":"255.255.255.0",
                        "proto":"static",
                        "version":4
                    }
                ]
            }
        ],
        "vmUUid":"ceede61af61a4268874dbac977a2d0e2"
    },
    "vmUuid":"ceede61af61a4268874dbac977a2d0e2"
}'''

    cmd = jsonobject.loads(str_config)
    rsp = VmConfigSyncResponse()

    domain = get_virt_domain(cmd.vmUuid)
    if not domain:
        print('get vm dom failed.')
        exit(1)
    if not domain.isActive():
        print('vm dom os not active.')
        exit(1)

    """
    try:
        print("init start.")
        config_driver = VmConfigDriverBase.get_driver(domain)
        print("ports_config start.")
        config_driver.config_ports(cmd.portsConfig)
    except QgaException as e:
        print("result error: code=%s, message=%s." % (e.error_code, e.message))
    """
    print('config success')

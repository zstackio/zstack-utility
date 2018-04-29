'''

@author: frank
'''

import platform
from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import sizeunit
from zstacklib.utils import linux
from zstacklib.utils import thread
from zstacklib.utils import xmlobject
from zstacklib.utils.bash import *
from zstacklib.utils.report import Report
import os.path
import re
import threading
import time
import libvirt
import pyudev
import traceback
import Queue

IS_AARCH64 = platform.machine() == 'aarch64'


class ReconnectMeCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.reason = None

class ConnectResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ConnectResponse, self).__init__()
        self.iptablesSucc = None

class HostCapacityResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(HostCapacityResponse, self).__init__()
        self.cpuNum = None
        self.cpuSpeed = None
        self.usedCpu = None
        self.totalMemory = None
        self.usedMemory = None
        self.cpuSockets = None

class HostFactResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(HostFactResponse, self).__init__()
        self.osDistribution = None
        self.osVersion = None
        self.osRelease = None
        self.qemuImgVersion = None
        self.libvirtVersion = None
        self.hvmCpuFlag = None
        self.cpuModelName = None

class SetupMountablePrimaryStorageHeartbeatCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SetupMountablePrimaryStorageHeartbeatCmd, self).__init__()
        self.heartbeatFilePaths = None
        self.heartbeatInterval = None

class SetupMountablePrimaryStorageHeartbeatResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SetupMountablePrimaryStorageHeartbeatResponse, self).__init__()

class PingResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(PingResponse, self).__init__()
        self.hostUuid = None

class GetUsbDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetUsbDevicesRsp, self).__init__()
        self.usbDevicesInfo = None

class ReportDeviceEventCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ReportDeviceEventCmd, self).__init__()
        self.hostUuid = None

class UpdateHostOSCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(UpdateHostOSCmd, self).__init__()
        self.hostUuid = None
        self.excludePackages = None

class UpdateHostOSRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateHostOSRsp, self).__init__()

logger = log.get_logger(__name__)

def _get_memory(word):
    out = shell.call("grep '%s' /proc/meminfo" % word)
    (name, capacity) = out.split(':')
    capacity = re.sub('[k|K][b|B]', '', capacity).strip()
    #capacity = capacity.rstrip('kB').rstrip('KB').rstrip('kb').strip()
    return sizeunit.KiloByte.toByte(long(capacity))

def _get_total_memory():
    return _get_memory('MemTotal')

def _get_free_memory():
    return _get_memory('MemFree')

def _get_used_memory():
    return _get_total_memory() - _get_free_memory()


class LibvirtAutoReconnect(object):
    conn = libvirt.open('qemu:///system')

    if not conn:
        raise Exception('unable to get libvirt connection')

    libvirt_event_callbacks = {}

    def __init__(self, func):
        self.func = func
        self.exception = None

    @staticmethod
    def add_libvirt_callback(id, cb):
        cbs = LibvirtAutoReconnect.libvirt_event_callbacks.get(id, None)
        if cbs is None:
            cbs = []
            LibvirtAutoReconnect.libvirt_event_callbacks[id] = cbs
        cbs.append(cb)

    @staticmethod
    def register_libvirt_callbacks():
        def reboot_callback(conn, dom, opaque):
            cbs = LibvirtAutoReconnect.libvirt_event_callbacks.get(libvirt.VIR_DOMAIN_EVENT_ID_REBOOT)
            if not cbs:
                return

            for cb in cbs:
                try:
                    cb(conn, dom, opaque)
                except:
                    content = traceback.format_exc()
                    logger.warn(content)

        LibvirtAutoReconnect.conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_REBOOT, reboot_callback,
                                                         None)

        def lifecycle_callback(conn, dom, event, detail, opaque):
            cbs = LibvirtAutoReconnect.libvirt_event_callbacks.get(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE)
            if not cbs:
                return

            for cb in cbs:
                try:
                    cb(conn, dom, event, detail, opaque)
                except:
                    content = traceback.format_exc()
                    logger.warn(content)

        LibvirtAutoReconnect.conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
                                                         lifecycle_callback, None)

        # NOTE: the keepalive doesn't work on some libvirtd even the versions are the same
        # the error is like "the caller doesn't support keepalive protocol; perhaps it's missing event loop implementation"

        # def start_keep_alive(_):
        #     try:
        #         LibvirtAutoReconnect.conn.setKeepAlive(5, 3)
        #         return True
        #     except Exception as e:
        #         logger.warn('unable to start libvirt keep-alive, %s' % str(e))
        #         return False
        #
        # if not linux.wait_callback_success(start_keep_alive, timeout=5, interval=0.5):
        #     raise Exception('unable to start libvirt keep-alive after 5 seconds, see the log for detailed error')

    @lock.lock('libvirt-reconnect')
    def _reconnect(self):
        def test_connection():
            try:
                LibvirtAutoReconnect.conn.getLibVersion()
                return None
            except libvirt.libvirtError as ex:
                return ex

        ex = test_connection()
        if not ex:
            # the connection is ok
            return

        logger.warn("the libvirt connection is broken, there is no safeway to auto-reconnect without fd leak, we"
                    " will ask the mgmt server to reconnect us after self quit")
        HostPlugin.queue.put("exit")

    def __call__(self, *args, **kwargs):
        try:
            return self.func(LibvirtAutoReconnect.conn)
        except libvirt.libvirtError as ex:
            err = str(ex)
            if 'client socket is closed' in err or 'Broken pipe' in err:
                logger.debug('socket to the libvirt is broken[%s], try reconnecting' % err)
                self._reconnect()
                return self.func(LibvirtAutoReconnect.conn)
            else:
                raise


class HostPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    CONNECT_PATH = '/host/connect'
    CAPACITY_PATH = '/host/capacity'
    ECHO_PATH = '/host/echo'
    FACT_PATH = '/host/fact'
    PING_PATH = "/host/ping"
    GET_USB_DEVICES_PATH = "/host/usbdevice/get"
    SETUP_MOUNTABLE_PRIMARY_STORAGE_HEARTBEAT = "/host/mountableprimarystorageheartbeat"
    UPDATE_OS_PATH = "/host/updateos"

    queue = Queue.Queue()

    def _get_libvirt_version(self):
        ret = shell.call('libvirtd --version')
        return ret.split()[-1]

    def _get_qemu_version(self):
        # to be compatible with both `2.6.0` and `2.9.0(qemu-kvm-ev-2.9.0-16.el7_4.8.1)`
        ret = shell.call('%s -version' % kvmagent.get_qemu_path())
        words = ret.split()
        for w in words:
            if w == 'version':
                return words[words.index(w)+1].strip().split('(')[0]

        raise kvmagent.KvmError('cannot get qemu version[%s]' % ret)

    @lock.file_lock('/run/xtables.lock')
    @in_bash
    def apply_iptables_rules(self, rules):
        logger.debug("starting add iptables rules : %s" % rules)
        if len(rules) != 0 and rules is not None:
            for item in rules:
                rule = item.strip("'").strip('"')
                clean_rule = ' '.join(rule.split(' ')[1:])
                ret = bash_r("iptables -C %s " % clean_rule)
                if ret == 0:
                    continue
                elif ret == 1:
                    # didn't find this rule
                    set_rules_ret = bash_r("iptables %s" % rule)
                    if set_rules_ret != 0:
                        raise Exception('cannot set iptables rule: %s' % rule)
                else:
                    raise Exception('check iptables rule: %s failed' % rule)
        return True

    @kvmagent.replyerror
    def connect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.host_uuid = cmd.hostUuid
        self.config[kvmagent.HOST_UUID] = self.host_uuid
        self.config[kvmagent.SEND_COMMAND_URL] = cmd.sendCommandUrl
        Report.serverUuid = self.host_uuid
        Report.url = cmd.sendCommandUrl
        logger.debug(http.path_msg(self.CONNECT_PATH, 'host[uuid: %s] connected' % cmd.hostUuid))
        rsp = ConnectResponse()
        rsp.libvirtVersion = self.libvirt_version
        rsp.qemuVersion = self.qemu_version

        # create udev rule
        self.handle_usb_device_events()

        vm_plugin.cleanup_stale_vnc_iptable_chains()
        apply_iptables_result = self.apply_iptables_rules(cmd.iptablesRules)
        rsp.iptablesSucc = apply_iptables_result
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def ping(self, req):
        rsp = PingResponse()
        rsp.hostUuid = self.host_uuid
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @kvmagent.replyerror
    def fact(self, req):
        rsp = HostFactResponse()
        rsp.osDistribution, rsp.osVersion, rsp.osRelease = platform.dist()
        # to be compatible with both `2.6.0` and `2.9.0(qemu-kvm-ev-2.9.0-16.el7_4.8.1)`
        qemu_img_version = shell.call("qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1")
        qemu_img_version = qemu_img_version.strip('\t\r\n ,')
        ipV4Addrs = shell.call("ip addr | grep -w inet | grep -v 127.0.0.1 | awk '{print $2}' | cut -d/ -f1")
        rsp.qemuImgVersion = qemu_img_version
        rsp.libvirtVersion = self.libvirt_version
        rsp.ipAddresses = ipV4Addrs.splitlines()

        if IS_AARCH64:
            # FIXME how to check vt of aarch64?
            rsp.hvmCpuFlag = 'vt'
        else:
            if shell.run('grep vmx /proc/cpuinfo') == 0:
                rsp.hvmCpuFlag = 'vmx'

            if not rsp.hvmCpuFlag:
                if shell.run('grep svm /proc/cpuinfo') == 0:
                    rsp.hvmCpuFlag = 'svm'

            rsp.cpuModelName = self._get_host_cpu_model()

        return jsonobject.dumps(rsp)

    @LibvirtAutoReconnect
    def _get_host_cpu_model(conn):
        xml_object = xmlobject.loads(conn.getCapabilities())
        return str(xml_object.host.cpu.model.text_)


    @kvmagent.replyerror
    @in_bash
    def capacity(self, req):
        rsp = HostCapacityResponse()
        rsp.cpuNum = linux.get_cpu_num()
        rsp.cpuSpeed = linux.get_cpu_speed()
        (used_cpu, used_memory) = vm_plugin.get_cpu_memory_used_by_running_vms()
        rsp.usedCpu = used_cpu
        rsp.totalMemory = _get_total_memory()
        rsp.usedMemory = used_memory

        sockets = bash_o('grep "physical id" /proc/cpuinfo | sort -u | wc -l').strip('\n')
        rsp.cpuSockets = int(sockets)

        ret = jsonobject.dumps(rsp)
        logger.debug('get host capacity: %s' % ret)
        return ret

    def _heartbeat_func(self, heartbeat_file):
        class Heartbeat(object):
            def __init__(self):
                self.current = None

        hb = Heartbeat()
        hb.current = time.time()
        with open(heartbeat_file, 'w') as fd:
            fd.write(jsonobject.dumps(hb))
        return True

    @kvmagent.replyerror
    def setup_heartbeat_file(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetupMountablePrimaryStorageHeartbeatResponse()

        for hb in cmd.heartbeatFilePaths:
            hb_dir = os.path.dirname(hb)
            mount_path = os.path.dirname(hb_dir)
            if not linux.is_mounted(mount_path):
                rsp.error = '%s is not mounted, setup heartbeat file[%s] failed' % (mount_path, hb)
                rsp.success = False
                return jsonobject.dumps(rsp)

        for hb in cmd.heartbeatFilePaths:
            t = self.heartbeat_timer.get(hb, None)
            if t:
                t.cancel()

            hb_dir = os.path.dirname(hb)
            if not os.path.exists(hb_dir):
                os.makedirs(hb_dir, 0755)

            t = thread.timer(cmd.heartbeatInterval, self._heartbeat_func, args=[hb], stop_on_exception=False)
            t.start()
            self.heartbeat_timer[hb] = t
            logger.debug('create heartbeat file at[%s]' % hb)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def get_usb_devices(self, req):
        class UsbDeviceInfo(object):
            def __init__(self):
                self.busNum = ""
                self.devNum = ""
                self.idVendor = ""
                self.idProduct = ""
                self.iManufacturer = ""
                self.iProduct = ""
                self.iSerial = ""
                self.usbVersion = ""
            def toString(self):
                return self.busNum + ':' + self.devNum + ':' + self.idVendor + ':' + self.idProduct + ':' + self.iManufacturer + ':' + self.iProduct + ':' + self.iSerial + ':' + self.usbVersion + ";"

        # use 'lsusb.py -U' to get device ID, like '0751:9842'
        rsp = GetUsbDevicesRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        r, o, e = bash_roe("lsusb.py -U")
        if r != 0:
            rsp.success = False
            rsp.error = "%s %s" % (e, o)
            return jsonobject.dumps(rsp)

        idSet = set()
        usbDevicesInfo = ''
        for line in o.split('\n'):
            line = line.split()
            if len(line) < 2:
                continue
            idSet.add(line[1])

        for devId in idSet:
            # use 'lsusb -v -d ID' to get device info[s]
            r, o, e = bash_roe("lsusb -v -d %s" % devId)
            if r != 0:
                rsp.success = False
                rsp.error = "%s %s" % (e, o)
                return jsonobject.dumps(rsp)

            for line in o.split('\n'):
                line = line.strip().split()
                if len(line) < 2:
                    continue

                if line[0] == 'Bus':
                    info = UsbDeviceInfo()
                    info.idVendor, info.idProduct = devId.split(':')
                    info.busNum = line[1]
                    info.devNum = line[3].rsplit(':')[0]
                elif line[0] == 'idVendor':
                    info.iManufacturer = ' '.join(line[2:]) if len(line) > 2 else ""
                elif line[0] == 'idProduct':
                    info.iProduct = ' '.join(line[2:]) if len(line) > 2 else ""
                elif line[0] == 'bcdUSB':
                    info.usbVersion = line[1]
                    # special case: USB2.0 with full speed should be attached to USB1.1 Controller
                    rst = bash_r("lsusb.py | grep -v 'grep' | grep '%s' | grep '12MBit/s'" % devId)
                    info.usbVersion = info.usbVersion if rst != 0 else '1.1'
                elif line[0] == 'iManufacturer' and len(line) > 2:
                    info.iManufacturer = ' '.join(line[2:])
                elif line[0] == 'iProduct' and len(line) > 2:
                    info.iProduct = ' '.join(line[2:])
                elif line[0] == 'iSerial':
                    info.iSerial = ' '.join(line[2:]) if len(line) > 2 else ""
                    if info.busNum == '' or info.devNum == '' or info.idVendor == '' or info.idProduct == '':
                        rsp.success = False
                        rsp.error = "cannot get enough info of usb device"
                        return jsonobject.dumps(rsp)
                    else:
                        usbDevicesInfo += info.toString()
        rsp.usbDevicesInfo = usbDevicesInfo
        return jsonobject.dumps(rsp)

    @lock.file_lock('/usr/bin/_report_device_event.sh')
    def handle_usb_device_events(self):
        bash_str = """#!/usr/bin/env python
import urllib2
def post_msg(data, post_url):
    headers = {"content-type": "application/json", "commandpath": "/host/reportdeviceevent"}
    req = urllib2.Request(post_url, data, headers)
    response = urllib2.urlopen(req)
    response.close()

if __name__ == "__main__":
    post_msg("{'hostUuid':'%s'}", '%s')
""" % (self.config.get(kvmagent.HOST_UUID), self.config.get(kvmagent.SEND_COMMAND_URL))

        bash_file = '/usr/bin/_report_device_event.py'
        with open(bash_file, 'w') as f:
            f.write(bash_str)
        os.chmod(bash_file, 0o755)

        rule_str = 'ACTION=="add|remove", SUBSYSTEM=="usb", RUN="%s"' % bash_file
        rule_file = '/etc/udev/rules.d/usb.rules'
        with open(rule_file, 'w') as f:
            f.write(rule_str)

    @kvmagent.replyerror
    @in_bash
    def update_os(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if not cmd.excludePackages:
            exclude = ""
        else:
            exclude = "--exclude=" + cmd.excludePackages
        yum_cmd = "yum --enablerepo=* clean all && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn %s update -y" % exclude

        rsp = UpdateHostOSRsp()
        if shell.run("which yum") != 0:
            rsp.success = False
            rsp.error = "no yum command found, cannot update host os"
        elif shell.run("yum --disablerepo=* --enablerepo=zstack-mn repoinfo") != 0:
            rsp.success = False
            rsp.error = "no zstack-mn repo found, cannot update host os"
        elif shell.run("yum --disablerepo=* --enablerepo=qemu-kvm-ev-mn repoinfo") != 0:
            rsp.success = False
            rsp.error = "no qemu-kvm-ev-mn repo found, cannot update host os"
        elif shell.run(yum_cmd) != 0:
            rsp.success = False
            rsp.error = "failed to update host os using zstack-mn,qemu-kvm-ev-mn repo"
        else:
            logger.debug("successfully run: %s" % yum_cmd)
        return jsonobject.dumps(rsp)

    def start(self):
        self.host_uuid = None

        http_server = kvmagent.get_http_server()
        http_server.register_sync_uri(self.CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.PING_PATH, self.ping)
        http_server.register_async_uri(self.CAPACITY_PATH, self.capacity)
        http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        http_server.register_async_uri(self.SETUP_MOUNTABLE_PRIMARY_STORAGE_HEARTBEAT, self.setup_heartbeat_file)
        http_server.register_async_uri(self.FACT_PATH, self.fact)
        http_server.register_async_uri(self.GET_USB_DEVICES_PATH, self.get_usb_devices)
        http_server.register_async_uri(self.UPDATE_OS_PATH, self.update_os)

        self.heartbeat_timer = {}
        self.libvirt_version = self._get_libvirt_version()
        self.qemu_version = self._get_qemu_version()
        filepath = r'/etc/libvirt/qemu/networks/autostart/default.xml'
        if os.path.exists(filepath):
            os.unlink(filepath)

        @thread.AsyncThread
        def wait_end_signal():
            while True:
                try:
                    self.queue.get(True)

                    # the libvirt has been stopped or restarted
                    # to prevent fd leak caused by broken libvirt connection
                    # we have to ask mgmt server to reboot the agent
                    url = self.config.get(kvmagent.SEND_COMMAND_URL)
                    if not url:
                        logger.warn('cannot find SEND_COMMAND_URL, unable to ask the mgmt server to reconnect us')
                        os._exit(1)

                    host_uuid = self.config.get(kvmagent.HOST_UUID)
                    if not host_uuid:
                        logger.warn('cannot find HOST_UUID, unable to ask the mgmt server to reconnect us')
                        os._exit(1)

                    logger.warn("libvirt has been rebooted or stopped, ask the mgmt server to reconnt us")
                    cmd = ReconnectMeCmd()
                    cmd.hostUuid = host_uuid
                    cmd.reason = "libvirt rebooted or stopped"
                    http.json_dump_post(url, cmd, {'commandpath': '/kvm/reconnectme'})
                    os._exit(1)
                except:
                    content = traceback.format_exc()
                    logger.warn(content)

        wait_end_signal()

        @thread.AsyncThread
        def monitor_libvirt():
            while True:
                if shell.run('pid=$(cat /var/run/libvirtd.pid); ps -p $pid > /dev/null') != 0:
                    logger.warn(
                        "cannot find the libvirt process, assume it's dead, ask the mgmt server to reconnect us")
                    self.queue.put("exit")

                time.sleep(20)

        monitor_libvirt()


    def stop(self):
        pass

    def configure(self, config):
        self.config = config

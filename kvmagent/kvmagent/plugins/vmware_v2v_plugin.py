#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import commands

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import http
from zstacklib.utils import thread
from zstacklib.utils.bash import in_bash
from zstacklib.utils.linux import shellquote
from zstacklib.utils.plugin import completetask

logger = log.get_logger(__name__)


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


class CheckBitsRsp(AgentRsp):
    def __init__(self):
        super(CheckBitsRsp, self).__init__()
        self.existing = False


class ConvertRsp(AgentRsp):
    def __init__(self):
        super(ConvertRsp, self).__init__()
        self.rootVolumeInfo = None
        self.dataVolumeInfos = []
        self.bootMode = None


QOS_IFB = "ifb0"

VDDK_VERSION = '/var/lib/zstack/v2v/vddk_version'
WINDOWS_VIRTIO_DRIVE_ISO_VERSION = '/var/lib/zstack/v2v/windows_virtio_version'
V2V_LIB_PATH = '/var/lib/zstack/v2v/'

class VMwareV2VPlugin(kvmagent.KvmAgent):
    INIT_PATH = "/vmwarev2v/conversionhost/init"
    CONVERT_PATH = "/vmwarev2v/conversionhost/convert"
    CLEAN_PATH = "/vmwarev2v/conversionhost/clean"
    CHECK_BITS = "/vmwarev2v/conversionhost/checkbits"
    CONFIG_QOS_PATH = "/vmwarev2v/conversionhost/qos/config"
    DELETE_QOS_PATH = "/vmwarev2v/conversionhost/qos/delete"
    CANCEL_CONVERT_PATH = "/vmwarev2v/conversionhost/convert/cancel"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.CONVERT_PATH, self.convert)
        http_server.register_async_uri(self.CLEAN_PATH, self.clean)
        http_server.register_async_uri(self.CANCEL_CONVERT_PATH, self.clean_convert)
        http_server.register_async_uri(self.CHECK_BITS, self.check_bits)
        http_server.register_async_uri(self.CONFIG_QOS_PATH, self.config_qos)
        http_server.register_async_uri(self.DELETE_QOS_PATH, self.delete_qos)

    def stop(self):
        pass

    @in_bash
    @kvmagent.replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        path = "/var/lib/zstack/v2v"
        if not os.path.exists(path):
            os.makedirs(path, 0775)

        if not os.path.exists(WINDOWS_VIRTIO_DRIVE_ISO_VERSION) \
                and os.path.exists(V2V_LIB_PATH + 'zstack-windows-virtio-driver.iso'):
            last_modified = shell.call("curl -I %s | grep 'Last-Modified'" % cmd.virtioDriverUrl)
            with open(WINDOWS_VIRTIO_DRIVE_ISO_VERSION, 'w') as fd:
                fd.write(last_modified.strip('\n\r'))
        else:
            last_modified = shell.call("curl -I %s | grep 'Last-Modified'" % cmd.virtioDriverUrl).strip('\n\r')

            with open(WINDOWS_VIRTIO_DRIVE_ISO_VERSION, 'r') as fd:
                version = fd.readline()

            if version != last_modified:
                cmdstr = 'cd /var/lib/zstack/v2v && wget -c {} -O zstack-windows-virtio-driver.iso'.format(
                    cmd.virtioDriverUrl)
                if shell.run(cmdstr) != 0:
                    rsp.success = False
                    rsp.error = "failed to download zstack-windows-virtio-driver.iso " \
                                "from management node to v2v conversion host"
                    return jsonobject.dumps(rsp)

                with open(WINDOWS_VIRTIO_DRIVE_ISO_VERSION, 'w') as fd:
                    fd.write(last_modified)

        if not os.path.exists(VDDK_VERSION) and os.path.exists(V2V_LIB_PATH + 'vmware-vix-disklib-distrib.tar.gz'):
            with open(VDDK_VERSION, 'w') as fd:
                fd.write(cmd.vddkLibUrl.split('/')[-1])
        else:
            current_version = cmd.vddkLibUrl.split('/')[-1]

            with open(VDDK_VERSION, 'r') as fd:
                version = fd.readline()

            if current_version != version:
                cmdstr = 'cd /var/lib/zstack/v2v && wget -c {} -O vmware-vix-disklib-distrib.tar.gz && ' \
                         'tar zxf vmware-vix-disklib-distrib.tar.gz'.format(
                    cmd.vddkLibUrl)
                if shell.run(cmdstr) != 0:
                    rsp.success = False
                    rsp.error = "failed to download vmware-vix-disklib-distrib.tar.gz " \
                                "from management node to v2v conversion host"
                    return jsonobject.dumps(rsp)

                with open(VDDK_VERSION, 'w') as fd:
                    fd.write(current_version)

        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    @completetask
    def convert(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConvertRsp()

        storage_dir = os.path.join(cmd.storagePath, cmd.srcVmUuid)

        def validate_and_make_dir(_dir):
            existing = os.path.exists(_dir)
            if not existing:
                shell.call("mkdir -p %s" % _dir)
            return existing

        last_task = self.load_and_save_task(req, rsp, validate_and_make_dir, storage_dir)
        if last_task and last_task.agent_pid == os.getpid():
            rsp = self.wait_task_complete(last_task)
            return jsonobject.dumps(rsp)

        new_task = self.load_task(req)

        cmdstr = "echo '{1}' > {0}/passwd".format(storage_dir, cmd.vCenterPassword)
        if shell.run(cmdstr) != 0:
            rsp.success = False
            rsp.error = "failed to create passwd {} in v2v conversion host".format(storage_dir)
            return jsonobject.dumps(rsp)

        @thread.AsyncThread
        def save_pid():
            linux.wait_callback_success(os.path.exists, v2v_pid_path)
            with open(v2v_pid_path, 'r') as fd:
                new_task.current_pid = fd.read().strip()
            new_task.current_process_cmd = echo_pid_cmd
            new_task.current_process_name = "virt_v2v_cmd"
            logger.debug("longjob[uuid:%s] saved process[pid:%s, name:%s]" %
                         (cmd.longJobUuid, new_task.current_pid, new_task.current_process_name))

        virt_v2v_cmd = 'VIRTIO_WIN=/var/lib/zstack/v2v/zstack-windows-virtio-driver.iso \
                        virt-v2v -ic vpx://{0}?no_verify=1 {1} -it vddk \
                        --vddk-libdir=/var/lib/zstack/v2v/vmware-vix-disklib-distrib \
                        --vddk-thumbprint={3} -o local -os {2} --password-file {2}/passwd \
                        -of {4} > {2}/virt_v2v_log 2>&1'.format(cmd.srcVmUri, shellquote(cmd.srcVmName), storage_dir,
                                                                cmd.thumbprint, cmd.format)

        v2v_pid_path = os.path.join(storage_dir, "convert.pid")
        v2v_cmd_ret_path = os.path.join(storage_dir, "convert.ret")
        echo_pid_cmd = "echo $$ > %s; %s; ret=$?; echo $ret > %s; exit $ret" % (
        v2v_pid_path, virt_v2v_cmd, v2v_cmd_ret_path)

        src_vm_uri = cmd.srcVmUri
        vmware_host_ip = src_vm_uri.split('/')[-1]
        interface = self._get_network_interface_to_ip_address(vmware_host_ip)

        if interface:
            cmdstr = "tc filter replace dev %s protocol ip parent 1: prio 1 u32 match ip src %s/32 flowid 1:1" \
                     % (QOS_IFB, vmware_host_ip)
            shell.run(cmdstr)

        def run_convert_if_need():
            def do_run():
                save_pid()
                ret = shell.run(echo_pid_cmd)
                new_task.current_process_return_code = ret
                return ret

            pid = linux.read_file(v2v_pid_path)
            if not pid:
                return do_run()

            pid = int(pid.strip())
            process_completed = os.path.exists(v2v_cmd_ret_path)
            process_has_been_killed = not os.path.exists(v2v_cmd_ret_path) and not os.path.exists('/proc/%d' % pid)
            process_still_running = not os.path.exists(v2v_cmd_ret_path) and os.path.exists('/proc/%d' % pid)
            if process_has_been_killed:
                return do_run()

            if process_still_running:
                linux.wait_callback_success(os.path.exists, v2v_cmd_ret_path, timeout=259200, interval=60)

            ret = linux.read_file(v2v_cmd_ret_path)
            return int(ret.strip() if ret else 126)

        if run_convert_if_need() != 0:
            v2v_log_file = "/tmp/v2v_log/%s-virt-v2v-log" % cmd.longJobUuid

            rsp.success = False
            rsp.error = "failed to run virt-v2v command, log in conversion host: %s" % v2v_log_file

            # create folder to save virt-v2v log
            tail_cmd = 'mkdir -p /tmp/v2v_log; tail -c 1M %s/virt_v2v_log > %s' % (storage_dir, v2v_log_file)
            shell.run(tail_cmd)
            with open(v2v_log_file, 'a') as fd:
                fd.write('\n>>> VCenter Password: %s\n' % cmd.vCenterPassword)
                fd.write('\n>>> virt_v2v command: %s\n' % virt_v2v_cmd)
            return jsonobject.dumps(rsp)

        root_vol = r"%s/%s-sda" % (storage_dir, cmd.srcVmName)
        logger.debug(root_vol)
        if not os.path.exists(root_vol):
            rsp.success = False
            rsp.error = "failed to convert root volume of " + cmd.srcVmName
            return jsonobject.dumps(rsp)
        root_volume_actual_size, root_volume_virtual_size = self._get_qcow2_sizes(root_vol)
        rsp.rootVolumeInfo = {"installPath": root_vol,
                              "actualSize": root_volume_actual_size,
                              "virtualSize": root_volume_virtual_size,
                              "deviceId": 0}

        rsp.dataVolumeInfos = []
        for dev in 'bcdefghijklmnopqrstuvwxyz':
            data_vol = r"%s/%s-sd%c" % (storage_dir, cmd.srcVmName, dev)
            if os.path.exists(data_vol):
                aSize, vSize = self._get_qcow2_sizes(data_vol)
                rsp.dataVolumeInfos.append({"installPath": data_vol,
                                            "actualSize": aSize,
                                            "virtualSize": vSize,
                                            "deviceId": ord(dev) - ord('a')})
            else:
                break

        xml = r"%s/%s.xml" % (storage_dir, cmd.srcVmName)
        if self._check_str_in_file(xml, "<nvram "):
            rsp.bootMode = 'UEFI'

        def collect_time_cost():
            # [ 138.3] Copying disk 1/13 to
            # [ 408.1] Copying disk 2/13 to
            # ...
            # [1055.2] Copying disk 11/13 to
            # [1082.3] Copying disk 12/13 to
            # [1184.9] Copying disk 13/13 to
            s = shell.ShellCmd("""awk -F"[][]" '/Copying disk/{print $2}'""" % storage_dir)
            s(False)
            if s.return_code != 0:
                return

            times = s.stdout.split('\n')

            if len(times) == 0:
                return

            rsp.rootVolumeInfo['downloadTime'] = times[0]
            for i in xrange(0, len(rsp.dataVolumeInfos)):
                if i + 1 < len(times):
                    rsp.dataVolumeInfos[i]["downloadTime"] = int(float(times[i + 1]) - float(times[i]))

        try:
            collect_time_cost()
        except Exception as e:
            logger.debug("Failed to collect time cost, because %s" % e.message)

        return jsonobject.dumps(rsp)

    def _check_str_in_file(self, fname, txt):
        with open(fname) as dataf:
            return any(txt in line for line in dataf)

    @in_bash
    def _get_qcow2_sizes(self, path):
        cmd = "qemu-img info --output=json '%s'" % path
        _, output = commands.getstatusoutput(cmd)
        return long(json.loads(output)['actual-size']), long(json.loads(output)['virtual-size'])

    @in_bash
    @kvmagent.replyerror
    def clean(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if not cmd.srcVmUuid:
            cleanUpPath = cmd.storagePath
        else:
            cleanUpPath = os.path.join(cmd.storagePath, cmd.srcVmUuid)
            shell.run("pkill -9 -f '%s'" % cleanUpPath)

        linux.rm_dir_force(cleanUpPath)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def clean_convert(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        clean_up_path = os.path.join(cmd.storagePath, cmd.srcVmUuid)
        shell.run("pkill -9 -f '%s'" % clean_up_path)
        linux.rm_dir_force(clean_up_path)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        rsp.existing = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)

    @staticmethod
    def _get_network_interface_to_ip_address(ip_address):
        s = shell.ShellCmd("ip r get %s | sed 's/^.*dev \([^ ]*\).*$/\\1/;q'" % ip_address)
        s(False)

        if s.return_code == 0:
            return s.stdout.replace('\n', '')
        else:
            return None

    @staticmethod
    def _get_ip_address_to_domain(domain):
        s = shell.ShellCmd("ping -c 1 %s | head -2 | tail -1 | awk '{ print $5 }' |"
                           " sed 's/(//g' | sed 's/)://g'" % domain)
        s(False)

        if s.return_code == 0:
            return s.stdout
        else:
            return None

    @in_bash
    @kvmagent.replyerror
    def config_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        shell.run("modprobe ifb; ip link set %s up" % QOS_IFB)

        if cmd.vCenterIps:
            interface_setup_rule = []

            def set_up_qos_rules(target_interface):
                # a bare number in tc class use bytes as unit
                config_qos_cmd = "tc qdisc add dev {0} ingress;" \
                                 "tc filter add dev {0} parent ffff: protocol ip u32 match " \
                                 "u32 0 0 flowid 1:1 action mirred egress redirect dev {1};" \
                                 "tc qdisc del dev {1} root >/dev/null 2>&1;" \
                                 "tc qdisc add dev {1} root handle 1: htb;" \
                                 "tc class add dev {1} parent 1: classid 1:1 htb rate {2} burst 100m" \
                                 .format(target_interface, QOS_IFB, cmd.inboundBandwidth)
                return shell.run(config_qos_cmd)

            for vcenter_ip in cmd.vCenterIps:
                interface = self._get_network_interface_to_ip_address(vcenter_ip)

                if interface is None:
                    interface = self._get_network_interface_to_ip_address(self._get_ip_address_to_domain(vcenter_ip))

                if interface and interface not in interface_setup_rule:
                    if set_up_qos_rules(interface) == 0:
                        interface_setup_rule.append(interface)
                    else:
                        logger.debug("Failed to set up qos rules on interface %s" % interface)
                    continue

            list_url_cmd = shell.ShellCmd("ps aux | grep '[v]irt-v2v' | grep -v convert.ret | awk '{print $13}'")
            list_url_cmd(False)

            limited_interface = []
            if list_url_cmd.return_code == 0 and list_url_cmd.stdout:
                # will get a url format like
                # vpx://administrator%40vsphere.local@xx.xx.xx.xx/Datacenter-xxx/Cluster-xxx/127.0.0.1?no_verify=1
                for url in list_url_cmd.stdout.split('\n'):
                    vmware_host_ip = url.split('/')[-1].split('?')[0]
                    interface = self._get_network_interface_to_ip_address(vmware_host_ip)

                    if interface:
                        cmdstr = "tc filter replace dev %s protocol ip parent 1: prio 1 u32 match ip src %s/32 flowid 1:1" \
                                 % (QOS_IFB, vmware_host_ip)
                        if shell.run(cmdstr) != 0:
                            logger.debug("Failed to set up tc filter on interface %s for ip %s"
                                         % (interface, vmware_host_ip))
                        else:
                            limited_interface.append(interface)

        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def delete_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        if cmd.vCenterIps:
            def delete_qos_rules(target_interface):
                if target_interface:
                    cmdstr = "tc qdisc del dev %s root >/dev/null 2>&1" % target_interface
                    shell.run(cmdstr)
                    cmdstr = "tc qdisc del dev %s ingress >/dev/null 2>&1" % QOS_IFB
                    shell.run(cmdstr)

            for vcenter_ip in cmd.vCenterIps:
                interface = self._get_network_interface_to_ip_address(vcenter_ip)

                if interface is None:
                    interface = self._get_network_interface_to_ip_address(self._get_ip_address_to_domain(vcenter_ip))

                if interface:
                    delete_qos_rules(interface)

        return jsonobject.dumps(rsp)

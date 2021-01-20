#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import random
import string
import platform
import uuid

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import shell
from zstacklib.utils import powershell
from zstacklib.utils.bash import in_bash
from zstacklib.utils.plugin import completetask
from zstacklib.utils.report import *

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class VolumeInfo(object):
    def __init__(self):
        self.name = None       # type: str
        self.size = -1         # type: long
        self.physicalSize = -1 # type: long
        self.type = None       # type: string
        self.path = None       # type: string

class VmInfo(object):
    def __init__(self):
        self.name = None        # type: str
        self.uuid = None        # type: str
        self.cpuNum = -1        # type: int
        self.memorySize = -1    # type: long
        self.macAddresses = []  # type: list[str]
        self.volumes = []       # type: list[VolumeInfo]
        self.cdromNum = 0       # type: int
        self.bootMode = None    # type: str


class ListVmCmd(object):
    @log.sensitive_fields("credential.remotePassword")
    def __init__(self):
        self.credential = None


class ListVmRsp(AgentRsp):
    def __init__(self):
        super(ListVmRsp, self).__init__()
        self.vms = []              # type: list[VmInfo]

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

def getRealStoragePath(storagePath):
    return os.path.abspath(os.path.join(storagePath, "v2v-cache"))

V2V_LIB_PATH = '/var/lib/zstack/v2v/'
HYPERV_V2V_LIB_PATH = "/var/lib/zstack/v2v/hyperv/vsftpd/"
VSFTPD_CONF_PATH = HYPERV_V2V_LIB_PATH + "vsftpd.conf"
VSFTPD_LOG_PATH = HYPERV_V2V_LIB_PATH + "vsftpd.log"
WINDOWS_VIRTIO_DRIVE_ISO_VERSION = '/var/lib/zstack/v2v/windows_virtio_version'

class HyperVV2VPlugin(kvmagent.KvmAgent):
    INIT_PATH = "/hypervv2v/conversionhost/init"
    LIST_VM_PATH = "/hypervv2v/conversionhost/listvm"
    CONVERT_PATH = "/hypervv2v/conversionhost/convert"
    CLEAN_PATH = "/hypervv2v/conversionhost/clean"
    CHECK_BITS = "/hypervv2v/conversionhost/checkbits"
    CONFIG_QOS_PATH = "/hypervv2v/conversionhost/qos/config"
    DELETE_QOS_PATH = "/hypervv2v/conversionhost/qos/delete"
    CANCEL_CONVERT_PATH = "/hypervv2v/conversionhost/convert/cancel"

    def start(self):
        random.seed()
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.LIST_VM_PATH, self.listvm, cmd=ListVmCmd())
        http_server.register_async_uri(self.CONVERT_PATH, self.convert)
        http_server.register_async_uri(self.CLEAN_PATH, self.clean)
        http_server.register_async_uri(self.CANCEL_CONVERT_PATH, self.cancel_and_clean_convert)
        http_server.register_async_uri(self.CHECK_BITS, self.check_bits)
        http_server.register_async_uri(self.CONFIG_QOS_PATH, self.config_qos)
        http_server.register_async_uri(self.DELETE_QOS_PATH, self.delete_qos)

    def stop(self):
        pass

    @in_bash
    @kvmagent.replyerror
    def init(self, req):
        def get_dep_version_from_version_file(version_file):
            if not os.path.exists(version_file):
                return None
            else:
                with open(version_file, 'r') as vfd:
                    return vfd.readline()

        def get_win_virtio_iso():
            tmpl = {'releasever': releasever}
            virtioDriverUrl = string.Template(cmd.virtioDriverUrl)
            cmd.virtioDriverUrl = virtioDriverUrl.substitute(tmpl)
            if not os.path.exists(WINDOWS_VIRTIO_DRIVE_ISO_VERSION) \
                    and os.path.exists(V2V_LIB_PATH + 'zstack-windows-virtio-driver.iso'):
                last_modified = shell.call("curl -I %s | grep 'Last-Modified'" % cmd.virtioDriverUrl)
                with open(WINDOWS_VIRTIO_DRIVE_ISO_VERSION, 'w') as fd:
                    fd.write(last_modified.strip('\n\r'))
            else:
                last_modified = shell.call("curl -I %s | grep 'Last-Modified'" % cmd.virtioDriverUrl).strip('\n\r')

                version = get_dep_version_from_version_file(WINDOWS_VIRTIO_DRIVE_ISO_VERSION)

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

        def config_ftp_server():
            # init vsftpd.conf
            anon_path = os.path.abspath(os.path.join(getRealStoragePath(cmd.storagePath), "ftp"))
            if not os.path.exists(anon_path):
                linux.mkdir(anon_path, 0755)

            if not os.path.exists(HYPERV_V2V_LIB_PATH):
                linux.mkdir(HYPERV_V2V_LIB_PATH, 0755)

            vsftpd_conf = """
listen=YES
local_enable=YES
write_enable=YES
xferlog_file=YES

#anonymous users are restricted (chrooted) to anon_root
anonymous_enable=YES
anon_root={VSFTPD_ANON_ROOT}
anon_upload_enable=YES
anon_mkdir_write_enable=YES

#500 OOPS: bad bool value in config file for: chown_uploads
chown_uploads=YES
chown_username=ftp
""".format(VSFTPD_ANON_ROOT=anon_path,
                               VSFTPD_LOG_PATH=VSFTPD_LOG_PATH)
            linux.write_file(VSFTPD_CONF_PATH, vsftpd_conf, True)

            vsftpd_service_path = "/usr/lib/systemd/system/vsftpd.service"
            vsftpd_service_conf = """
[Unit]
Description=Vsftpd ftp daemon
After=network.target

[Service]
Type=forking
ExecStart=/usr/sbin/vsftpd %s

[Install]
WantedBy=multi-user.target
""" % VSFTPD_CONF_PATH

            linux.write_file(vsftpd_service_path, vsftpd_service_conf, True)
            os.chmod(vsftpd_service_path, 0644)
            logger.info("vsftpd service conf changed")
            shell.call("systemctl daemon-reload && systemctl restart vsftpd.service")

        rsp = AgentRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        _, os_version, _ = platform.dist()
        versions = os_version.split('.')
        # check if os is centos 7.2
        if len(versions) > 2 and versions[0] == '7' and versions[1] == '2':
            rsp.success = False
            rsp.error = "v2v feature is not supported on centos 7.2"
            return jsonobject.dumps(rsp)

        path = "/var/lib/zstack/v2v"
        if not os.path.exists(path):
            os.makedirs(path, 0775)

        if cmd.storagePath:
            spath = getRealStoragePath(cmd.storagePath)
            if not os.path.exists(spath):
                linux.mkdir(spath, 0775)

        releasever = kvmagent.get_host_yum_release()
        yum_cmd = "export YUM0={}; yum --enablerepo=* clean all && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn " \
                  "install vsftpd libguestfs-tools libguestfs-tools-c perl-Sys-Guestfs libguestfs-winsupport virt-v2v " \
                  "powershell omi omi-psrp-server gssntlmssp -y".format(
            releasever)
        if shell.run(yum_cmd) != 0 or shell.run("pwsh --version") != 0:
            rsp.success = False
            rsp.error = "failed to update install conversion host dependencies from zstack-mn,qemu-kvm-ev-mn repo"
            return jsonobject.dumps(rsp)

        config_ftp_server()
        get_win_virtio_iso()

        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def listvm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        ps = powershell.OpenRemotePS(cmd.credential)
        rsp = ListVmRsp()
        rsp.vms = ps.get_vm_info()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @completetask
    def convert(self, req):
        def validate_and_make_dir(_dir):
            exists = os.path.exists(_dir)
            if not exists:
                linux.mkdir(_dir)
            return exists

        def makeVolumeInfo(v, startTime, devId, destPath):
            return { "installPath": destPath,
                     "actualSize":  v.physicalSize,
                     "virtualSize": v.size,
                     "virtioScsi":  v.bus == 'scsi',
                     "deviceName":  v.name,
                     "downloadTime": int(time.time() - startTime),
                     "deviceId":    devId }

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        real_storage_path = getRealStoragePath(cmd.storagePath)
        storage_dir = os.path.join(real_storage_path, "ftp/%s" % cmd.vmInfo.uuid)
        rsp = ConvertRsp()
        last_task = self.load_and_save_task(req, rsp, validate_and_make_dir, storage_dir)
        if last_task and last_task.agent_pid == os.getpid():
            rsp = self.wait_task_complete(last_task)
            return jsonobject.dumps(rsp)

        if linux.find_route_interface_by_destination_ip(linux.get_host_by_name(cmd.managementIp)):
            cmdstr = "tc filter replace dev %s protocol ip parent 1: prio 1 u32 match ip src %s/32 flowid 1:1" \
                     % (QOS_IFB, cmd.managementIp)
            shell.run(cmdstr)

        if os.path.exists(storage_dir):
            linux.rm_dir_force(storage_dir)
        linux.mkdir(storage_dir, 0777)

        report = Report(cmd.threadContext, cmd.threadContextStack)
        report.processType = "HYPERV-V2V"
        report.progress_report(10, "start")

        startTime = time.time()
        ps = powershell.OpenRemotePS(cmd.credential)
        vmInfos = ps.get_vm_info(cmd.vmInfo.uuid)
        if len(vmInfos) < 1:
            raise Exception("cannot get src vm:%s info" % cmd.credential.srcVmUuid)

        cmd.vmInfo = vmInfos[0]
        logger.debug("get srcVmInfo: %s" % jsonobject.dumps(cmd.vmInfo))
        ps.fetch_vm_disk(cmd.vmInfo, storage_dir, cmd.managementIp)

        report.progress_report(30, "start")

        volumes = cmd.vmInfo.volumes

        if not rsp.success:
            return jsonobject.dumps(rsp)

        idx = 1
        rv, dvs = None, []
        progress = 30
        volume_num = len(volumes)
        for v in volumes:
            srcPath  = os.path.join(storage_dir, v.name)
            if v.type == 'Root':
                virt_v2v_cmd = "VIRTIO_WIN=/var/lib/zstack/v2v/zstack-windows-virtio-driver.iso " \
                               "virt-v2v -i disk \"%s\"  -o local -of %s -os %s " \
                               "> %s/virt_v2v_log 2>&1" % (srcPath, cmd.format, storage_dir, storage_dir)
                if shell.run(virt_v2v_cmd.encode('utf-8')) != 0:
                    v2v_log_file = "/tmp/v2v_log/%s-virt-v2v-log" % cmd.longJobUuid

                    # create folder to save virt-v2v log
                    tail_cmd = 'mkdir -p /tmp/v2v_log; tail -c 1M %s/virt_v2v_log > %s' % (storage_dir, v2v_log_file)
                    shell.run(tail_cmd)
                    with open(v2v_log_file, 'a') as fd:
                        fd.write('\n>>> virt_v2v command: %s\n' % virt_v2v_cmd)

                    rsp.success = False
                    rsp.error = "failed to run virt-v2v command, log in conversion host: %s" % v2v_log_file

                    return jsonobject.dumps(rsp)

                destPath = "%s-sda" % srcPath
                rv = makeVolumeInfo(v, startTime, 0, destPath)
            else:
                destPath = os.path.join(storage_dir,
                                        "%s%s" % (v.name.rstrip(".vhdx").rstrip(".vhd"), ".%s" % cmd.format))
                cmd = "%s -p -O %s \"%s\" \"%s\"" % (linux.qemu_img.subcmd("convert"), cmd.format, srcPath, destPath)
                shell.call(cmd.encode('utf-8'))
                dvs.append(makeVolumeInfo(v, startTime, idx, destPath))
                idx += 1

            progress += 1.0 * (30 / float(volume_num))
            report.progress_report(progress, "start")

        report.progress_report(65, "start")

        rsp.rootVolumeInfo = rv
        rsp.dataVolumeInfos = dvs

        return jsonobject.dumps(rsp)


    @in_bash
    @kvmagent.replyerror
    def clean(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        real_storage_path = getRealStoragePath(cmd.storagePath)
        if not cmd.credential:
            cleanUpPath = real_storage_path
            shell.call('systemctl stop vsftpd.service')
        else:
            normalUuid = str(uuid.UUID(cmd.credential.srcVmUuid))
            cleanUpPath = os.path.join(real_storage_path, ("ftp/%s" % normalUuid))

        linux.rm_dir_force(cleanUpPath)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def cancel_and_clean_convert(self, req):
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


    @kvmagent.replyerror
    def config_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        shell.run("modprobe ifb; ip link set %s up" % QOS_IFB)

        if not cmd.sourceHosts:
            return jsonobject.dumps(rsp)

        interfaces_to_setup_rule = {}

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

        for host in cmd.sourceHosts:
            host_ip = linux.get_host_by_name(host)
            interface = linux.find_route_interface_by_destination_ip(host_ip)
            if interface:
                interfaces_to_setup_rule[host_ip] = interface

        for interface in set(interfaces_to_setup_rule.values()):
            if set_up_qos_rules(interface) != 0:
                logger.debug("Failed to set up qos rules on interface %s" % interface)

        for host_ip, interface in interfaces_to_setup_rule.items():
            cmdstr = "tc filter replace dev %s protocol ip parent 1: prio 1 u32 match ip src %s/32 flowid 1:1" \
                     % (QOS_IFB, host_ip)
            if shell.run(cmdstr) != 0:
                logger.debug("Failed to set up tc filter on interface %s for ip %s"
                             % (interface, host_ip))

        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def delete_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        if not cmd.sourceHosts:
            return jsonobject.dumps(rsp)

        def delete_qos_rules(target_interface):
            if target_interface:
                # delete ifb interface tc rules
                cmdstr = "tc qdisc del dev %s root >/dev/null 2>&1" % QOS_IFB
                shell.run(cmdstr)
                # delete target interface tc rules
                cmdstr = "tc qdisc del dev %s ingress >/dev/null 2>&1" % target_interface
                shell.run(cmdstr)

        for host in cmd.sourceHosts:
            host_ip = linux.get_host_by_name(host)
            interface = linux.find_route_interface_by_destination_ip(host_ip)

            if interface:
                delete_qos_rules(interface)

        return jsonobject.dumps(rsp)

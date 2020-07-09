#!/usr/bin/env python
# -*- coding: utf-8 -*-

import libvirt
import os
import random
import tempfile
import time
import urlparse

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import http
from zstacklib.utils import xmlobject
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
        self.type = None       # type: str
        self.bus = None        # type: str
        self.protocol = None   # type: str
        self.endTime = None    # type: float

class VmInfo(object):
    def __init__(self):
        self.name = None        # type: str
        self.description = None # type: str
        self.uuid = None        # type: str
        self.cpuNum = -1        # type: int
        self.memorySize = -1    # type: long
        self.macAddresses = []  # type: list[str]
        self.volumes = []       # type: list[VolumeInfo]
        self.v2vCaps = {}       # type: dict[str, bool]
        self.cdromNum = 0       # type: int

class ListVmRsp(AgentRsp):
    def __init__(self):
        super(ListVmRsp, self).__init__()
        self.qemuVersion = None    # type: str
        self.libvirtVersion = None # type: str
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


def getHostname(uri):
    return urlparse.urlparse(uri).hostname

def getUsername(uri):
    u = urlparse.urlparse(uri)
    return u.username if u.username else 'root'

def getSshTargetAndPort(uri):
    u = urlparse.urlparse(uri)
    target = u.username+'@'+u.hostname if u.username else u.hostname
    port = 22 if not u.port else u.port
    return target, port

def uriAddQuery(uri, key, val):
    if urlparse.urlparse(uri).query:
        return "{}&{}={}".format(uri, key, val)
    return "{}&{}={}".format(uri, key, val)

class LibvirtConn(object):
    @staticmethod
    def get_connection(uri=None, sasluser=None, saslpass=None):
        def request_cred(credentials, user_data):
            for credential in credentials:
                if credential[0] == libvirt.VIR_CRED_AUTHNAME:
                    credential[4] = sasluser
                elif credential[0] == libvirt.VIR_CRED_PASSPHRASE:
                    credential[4] = saslpass
            return 0

        if sasluser and saslpass:
            auth = [[libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE],
                    request_cred, None]
            return libvirt.openAuth(uri, auth, 0)

        return libvirt.open(uri)

    def __init__(self, uri, sasluser=None, saslpass=None, keystr=None):
        self.uri = uri
        self.sasluser = sasluser
        self.saslpass = saslpass
        self.keystr = keystr
        self.conn = None

    def __enter__(self):
        tmpkeyfile = None
        if self.keystr:
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(self.keystr)
                tmpkeyfile = f.name
            self.uri = uriAddQuery(self.uri, 'keyfile', tmpkeyfile)
        elif os.path.exists(V2V_PRIV_KEY):
            self.uri = uriAddQuery(self.uri, 'keyfile', V2V_PRIV_KEY)

        try:
            self.conn = self.get_connection(self.uri, self.sasluser, self.saslpass)
            return self.conn
        finally:
            if tmpkeyfile:
                os.remove(tmpkeyfile)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()


@in_bash
def runSshCmd(libvirtURI, keystr, cmdstr):
    target, port = getSshTargetAndPort(libvirtURI)
    ssh_opts = DEF_SSH_OPTS
    ssh_cmd = "ssh" if not os.path.exists(V2V_PRIV_KEY) else "ssh -i {}".format(V2V_PRIV_KEY)

    if not keystr:
        return shell.check_run( "{} {} -p {} {} {}".format(
            ssh_cmd,
            target,
            port,
            DEF_SSH_OPTS,
            linux.shellquote(cmdstr)))

    tmpkeyfile = None
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(keystr)
        tmpkeyfile = f.name
    try:
        return shell.check_run("ssh {} -p {} {} -i {} {}".format(
            target,
            port,
            DEF_SSH_OPTS,
            tmpkeyfile,
            linux.shellquote(cmdstr)))
    finally:
        os.remove(tmpkeyfile)

def getCdromNum(dom, dxml=None):
    if not dxml:
        dxml = xmlobject.loads(dom.XMLDesc(0))

    def countCdrom(domain_xml):
        disk = domain_xml.devices.disk

        if not disk:
            return 0

        if isinstance(disk, list):
            counter = 0
            for disk_xml in disk:
                if disk_xml.device_ == 'cdrom':
                    counter += 1

            return counter
        else:
            return 0

    return countCdrom(dxml)

def buildFilterDict(filterList):
    fdict = {}
    if not filterList:
        return fdict
    for f in filterList:
        fdict[f.deviceId] = f
    return fdict

def skipVolume(fdict, name):
    f = fdict.get(name)
    return f and f.skip

def getVolumes(dom, dxml=None):
    def getVolume(dom, diskxml):
        v = VolumeInfo()
        if diskxml.device_ in [ 'cdrom', 'floppy' ]:
            return None

        if diskxml.hasattr('boot') and diskxml.boot and diskxml.boot.hasattr('order_') and diskxml.boot.order_ == '1':
            v.type = 'ROOT'
        else:
            v.type = 'DATA'

        v.name = diskxml.target.dev_
        v.bus = diskxml.target.bus_
        if hasattr(diskxml.source, 'protocol_'):
            v.protocol = diskxml.source.protocol_
        v.size, _, v.physicalSize = dom.blockInfo(v.name)
        return v

    def listVolumes(dom, disk):
        if not disk:
            return []
        if isinstance(disk, list):
            return [ getVolume(dom, d) for d in disk ]
        return [ getVolume(dom, disk) ]

    if not dxml:
        dxml = xmlobject.loads(dom.XMLDesc(0))

    volumes = filter(lambda v:v, listVolumes(dom, dxml.devices.disk))

    if len(volumes) == 0:
        raise Exception("no disks found for VM: "+dom.name())

    if len(filter(lambda v: v.type == 'ROOT', volumes)) == 0:
        volumes[0].type = 'ROOT'

    return volumes

def getVerNumber(major, minor, build=0):
    return major * 1000000 + minor * 1000 + build

def listVirtualMachines(url, sasluser, saslpass, keystr):
    def getMac(ifxml):
        return ifxml.mac.address_ if ifxml.mac else ""

    def getMacs(iface):
        if not iface:
            return []
        if isinstance(iface, list):
            return [ getMac(inf) for inf in iface ]
        return [ getMac(iface) ]

    def getV2vCap(qemuver, libvirtver, vminfo):
        if qemuver < getVerNumber(1, 1):
            return False

        if any(map(lambda v: v.protocol == 'rbd', vminfo.volumes)):
            return libvirtver >= getVerNumber(1, 2, 16)
        return libvirtver >= getVerNumber(1, 2, 9)

    vms = []
    v2vCaps = {}
    qemuVersion, libvirtVersion = None, None
    with LibvirtConn(url, sasluser, saslpass, keystr) as c:
        qemuVersion = c.getVersion()
        libvirtVersion = c.getLibVersion()

        for dom in filter(lambda d: d.isActive(), c.listAllDomains()):
            info = VmInfo()

            info.name = dom.name()
            info.uuid = dom.UUIDString()

            dinfo = dom.info()
            info.memorySize = dinfo[1] * 1024
            info.cpuNum = dinfo[3]

            try:
                info.description = dom.metadata(libvirt.VIR_DOMAIN_METADATA_DESCRIPTION, None)
            except libvirt.libvirtError as ex:
                pass

            xmldesc = dom.XMLDesc(0)
            logger.info("domain xml for vm: {}\n{}".format(info.name, xmldesc))

            dxml = xmlobject.loads(xmldesc)
            if dxml.devices.hasattr('interface'):
                info.macAddresses = getMacs(dxml.devices.interface)
            else:
                info.macAddresses = []

            info.volumes = getVolumes(dom, dxml)
            cap = getV2vCap(qemuVersion, libvirtVersion, info)
            v2vCaps[info.uuid] = cap
            info.cdromNum = getCdromNum(dom, dxml)

            vms.append(info)

    return qemuVersion, libvirtVersion, vms, v2vCaps


QOS_IFB = "ifb0"

def getRealStoragePath(storagePath):
    return os.path.abspath(os.path.join(storagePath, "v2v-cache"))

V2V_PRIV_KEY = os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa_v2v")
V2V_PUB_KEY = V2V_PRIV_KEY+".pub"
DEF_SSH_OPTS = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

class KVMV2VPlugin(kvmagent.KvmAgent):
    INIT_PATH = "/kvmv2v/conversionhost/init"
    LIST_VM_PATH = "/kvmv2v/conversionhost/listvm"
    CONVERT_PATH = "/kvmv2v/conversionhost/convert"
    CLEAN_PATH = "/kvmv2v/conversionhost/clean"
    CHECK_BITS = "/kvmv2v/conversionhost/checkbits"
    CONFIG_QOS_PATH = "/kvmv2v/conversionhost/qos/config"
    DELETE_QOS_PATH = "/kvmv2v/conversionhost/qos/delete"
    CANCEL_CONVERT_PATH = "/kvmv2v/conversionhost/convert/cancel"

    def start(self):
        random.seed()
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.LIST_VM_PATH, self.listvm)
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
        rsp = AgentRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        spath = None
        if cmd.storagePath:
            spath = getRealStoragePath(cmd.storagePath)
            linux.mkdir(spath)

            with open('/etc/exports.d/zs-v2v.exports', 'w') as f:
                f.write("{} *(rw,sync,no_root_squash)\n".format(spath))

        shell.check_run('systemctl restart nfs-server')

        if spath is not None:
            fstype = shell.call("""stat -f -c '%T' {}""".format(spath)).strip()
            if fstype not in [ "xfs", "ext2", "ext3", "ext4", "jfs", "btrfs" ]:
                raise Exception("unexpected fstype '{}' on '{}'".format(fstype, cmd.storagePath))

        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def listvm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ListVmRsp()

        if cmd.sshPassword and not cmd.sshPrivKey:
            target, port = getSshTargetAndPort(cmd.libvirtURI)
            ssh_pswd_file = linux.write_to_temp_file(cmd.sshPassword)
            if not os.path.exists(V2V_PRIV_KEY) or not os.path.exists(V2V_PUB_KEY):
                shell.check_run("yes | ssh-keygen -t rsa -N '' -f {}".format(V2V_PRIV_KEY))
            cmdstr = "HOME={4} timeout 30 sshpass -f {0} ssh-copy-id -i {5} -p {1} {2} {3}".format(
                    ssh_pswd_file,
                    port,
                    DEF_SSH_OPTS,
                    target,
                    os.path.expanduser("~"),
                    V2V_PUB_KEY)
            shell.check_run(cmdstr)
            linux.rm_file_force(ssh_pswd_file)

        rsp.qemuVersion, rsp.libvirtVersion, rsp.vms, rsp.v2vCaps = listVirtualMachines(cmd.libvirtURI,
                cmd.saslUser,
                cmd.saslPass,
                cmd.sshPrivKey)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @completetask
    def convert(self, req):
        def get_mount_command(cmd):
            timeout_str = "timeout 30"
            username = getUsername(cmd.libvirtURI)
            if username == 'root':
                return "{0} mount".format(timeout_str)
            if cmd.sshPassword:
                return "echo {0} | {1} sudo -S mount".format(cmd.sshPassword, timeout_str)
            return "{0} sudo mount".format(timeout_str)

        def validate_and_make_dir(_dir):
            exists = os.path.exists(_dir)
            if not exists:
                linux.mkdir(_dir)
            return exists

        def do_ssh_mount(cmd, local_mount_point, vm_v2v_dir, real_storage_path):
            mount_cmd = get_mount_command(cmd)
            mount_paths = "{}:{} {}".format(cmd.managementIp, real_storage_path, local_mount_point)
            alternative_mount = mount_cmd + " -o vers=3"

            with lock.NamedLock(local_mount_point):
                cmdstr = "mkdir -p {0} && ls {1} 2>/dev/null || {2} {3} || {4} {3}".format(
                            local_mount_point,
                            vm_v2v_dir,
                            mount_cmd,
                            mount_paths,
                            alternative_mount)
                try:
                    runSshCmd(cmd.libvirtURI, cmd.sshPrivKey, cmdstr)
                except shell.ShellError as ex:
                    if "Stale file handle" in str(ex):
                        cmdstr = "umount {0} && {1} {2} || {3} {2}".format(
                                local_mount_point,
                                mount_cmd,
                                mount_paths,
                                alternative_mount)
                        runSshCmd(cmd.libvirtURI, cmd.sshPrivKey, cmdstr)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        real_storage_path = getRealStoragePath(cmd.storagePath)
        storage_dir = os.path.join(real_storage_path, cmd.srcVmUuid)

        rsp = ConvertRsp()
        last_task = self.load_and_save_task(req, rsp, validate_and_make_dir, storage_dir)
        if last_task and last_task.agent_pid == os.getpid():
            rsp = self.wait_task_complete(last_task)
            return jsonobject.dumps(rsp)

        local_mount_point = os.path.join("/tmp/zs-v2v/", cmd.managementIp)
        vm_v2v_dir = os.path.join(local_mount_point, cmd.srcVmUuid)
        libvirtHost = getHostname(cmd.libvirtURI)

        try:
            do_ssh_mount(cmd, local_mount_point, vm_v2v_dir, real_storage_path)
        except shell.ShellError as ex:
            logger.info(str(ex))
            raise Exception('host {} cannot access NFS on {}'.format(libvirtHost, cmd.managementIp))

        if linux.find_route_interface_by_destination_ip(linux.get_host_by_name(cmd.managementIp)):
            cmdstr = "tc filter replace dev %s protocol ip parent 1: prio 1 u32 match ip src %s/32 flowid 1:1" \
                     % (QOS_IFB, cmd.managementIp)
            shell.run(cmdstr)

        volumes = None
        filters = buildFilterDict(cmd.volumeFilters)
        startTime = time.time()
        with LibvirtConn(cmd.libvirtURI, cmd.saslUser, cmd.saslPass, cmd.sshPrivKey) as c:
            dom = c.lookupByUUIDString(cmd.srcVmUuid)
            if not dom:
                raise Exception('VM not found: {}'.format(cmd.srcVmUuid))

            xmlDesc = dom.XMLDesc(0)
            dxml = xmlobject.loads(xmlDesc)
            if dxml.os.hasattr('firmware_') and dxml.os.firmware_ == 'efi' or dxml.os.hasattr('loader'):
                rsp.bootMode = 'UEFI'

            volumes = filter(lambda v: not skipVolume(filters, v.name), getVolumes(dom, dxml))
            oldstat, _ = dom.state()
            needResume = True

            if cmd.pauseVm and oldstat != libvirt.VIR_DOMAIN_PAUSED:
                dom.suspend()
                needResume = False

            # libvirt >= 3.7.0 ?
            flags = 0 if c.getLibVersion() < getVerNumber(3, 7) else libvirt.VIR_DOMAIN_BLOCK_COPY_TRANSIENT_JOB
            needDefine = False
            if flags == 0 and dom.isPersistent():
                dom.undefine()
                needDefine = True

            for v in volumes:
                localpath = os.path.join(storage_dir, v.name)
                info = dom.blockJobInfo(v.name, 0)
                if os.path.exists(localpath) and not info:
                    os.remove(localpath)
                if not os.path.exists(localpath) and info:
                    raise Exception("blockjob already exists on disk: "+v.name)
                if info:
                    continue

                logger.info("start copying {}/{} ...".format(cmd.srcVmUuid, v.name))

                # c.f. https://github.com/OpenNebula/one/issues/2646
                linux.touch_file(localpath)

                dom.blockCopy(v.name,
                    "<disk type='file'><source file='{}'/><driver type='{}'/></disk>".format(os.path.join(vm_v2v_dir, v.name), cmd.format),
                    None,
                    flags)

            end_progress = 60
            total_volume_size = sum(volume.size for volume in volumes)

            if cmd.sendCommandUrl:
                Report.url = cmd.sendCommandUrl

            report = Report(cmd.threadContext, cmd.threadContextStack)
            report.processType = "KVM-V2V"
            while True:
                current_progress = 0.0
                job_canceled = False
                for v in volumes:
                    if v.endTime:
                        current_progress += 1.0 * float(v.size) / float(total_volume_size)
                        continue

                    info = dom.blockJobInfo(v.name, 0)
                    if not info:
                        err_msg = 'blockjob not found on disk %s, maybe job has been canceled' % v.name
                        logger.warn(err_msg)
                        job_canceled = True
                        continue
                    end = info['end']
                    cur = info['cur']
                    if cur == end :
                        v.endTime = time.time()
                        logger.info("completed copying {}/{} ...".format(cmd.srcVmUuid, v.name))
                        progress = 1.0
                    else:
                        progress = float(cur) / float(end)

                    current_progress += progress * float(v.size) / float(total_volume_size)

                report.progress_report(str(int(current_progress * float(end_progress))), "start")
                if all(map(lambda v: v.endTime, volumes)) or job_canceled:
                    break
                time.sleep(5)

            if job_canceled:
                rsp.success = False
                rsp.error = "cannot find blockjob on vm %s, maybe it has been canceled" % cmd.srcVmUuid

            if not cmd.pauseVm and oldstat != libvirt.VIR_DOMAIN_PAUSED:
                dom.suspend()
                needResume = True

            try:
                for v in volumes:
                    if dom.blockJobInfo(v.name, 0):
                        dom.blockJobAbort(v.name)
            finally:
                if needResume:
                    dom.resume()
                if needDefine:
                    c.defineXML(xmlDesc)

        # TODO
        #  - monitor progress

        def makeVolumeInfo(v, startTime, devId):
            return { "installPath": os.path.join(storage_dir, v.name),
                     "actualSize":  v.physicalSize,
                     "virtualSize": v.size,
                     "virtioScsi":  v.bus == 'scsi',
                     "deviceName":  v.name,
                     "downloadTime": int(v.endTime - startTime),
                     "deviceId":    devId }

        if not rsp.success:
            return jsonobject.dumps(rsp)

        idx = 1
        rv, dvs = None, []
        for v in volumes:
            if v.type == 'ROOT':
                rv = makeVolumeInfo(v, startTime, 0)
            else:
                dvs.append(makeVolumeInfo(v, startTime, idx))
                idx += 1

        rsp.rootVolumeInfo = rv
        rsp.dataVolumeInfos = dvs

        return jsonobject.dumps(rsp)


    @in_bash
    @kvmagent.replyerror
    def clean(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        real_storage_path = getRealStoragePath(cmd.storagePath)
        if not cmd.srcVmUuid:
            cleanUpPath = real_storage_path
        else:
            cleanUpPath = os.path.join(real_storage_path, cmd.srcVmUuid)

        linux.rm_dir_force(cleanUpPath)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def cancel_and_clean_convert(self, req):
        def abort_block_job(conn, filters):
            with LibvirtConn(conn.libvirtURI, conn.saslUser, conn.saslPass, conn.sshPrivKey) as c:
                dom = c.lookupByUUIDString(cmd.srcVmUuid)
                if not dom:
                    logger.info('VM not found: {}'.format(cmd.srcVmUuid))
                    return

                xmlDesc = dom.XMLDesc(0)
                dxml = xmlobject.loads(xmlDesc)

                volumes = filter(lambda v: not skipVolume(filters, v.name), getVolumes(dom, dxml))

                for v in volumes:
                    info = dom.blockJobInfo(v.name, 0)
                    if info:
                        dom.blockJobAbort(v.name)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        abort_block_job(cmd.libvirtConn, buildFilterDict(cmd.volumeFilters))
        real_storage_path = getRealStoragePath(cmd.storagePath)
        clean_up_path = os.path.join(real_storage_path, cmd.srcVmUuid)
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

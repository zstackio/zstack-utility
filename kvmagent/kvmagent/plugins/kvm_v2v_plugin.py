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
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import http
from zstacklib.utils import xmlobject
from zstacklib.utils.bash import in_bash

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

class VmInfo(object):
    def __init__(self):
        self.name = None        # type: str
        self.description = None # type: str
        self.uuid = None        # type: str
        self.cpuNum = -1        # type: int
        self.memorySize = -1    # type: long
        self.macAddresses = []  # type: list[str]
        self.volumes = []       # type: list[VolumeInfo]

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


def getSshTargetAndPort(uri):
    u = urlparse.urlparse(uri)
    target = u.username+'@'+u.hostname if u.username else u.hostname
    port = 22 if u.port is None else u.port
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
        keyfile = None
        if self.keystr:
            with tempfile.NamedTemporaryFile(delete=False) as f:
                keyfile.write(keystr)
                keyfile = f.name
            self.uri = uriAddQuery(self.uri, 'keyfile', keyfile)

        try:
            self.conn = self.get_connection(self.uri, self.sasluser, self.saslpass)
            return self.conn
        finally:
            if keyfile:
                os.remove(keyfile)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()


@in_bash
def runSshCmd(libvirtURI, keystr, cmdstr):
    targegt, port = getSshTargetAndPort(libvirtURI)
    if keystr is None:
        return shell.check_run( "ssh {} -p {} {} {}".format(
            targegt,
            port,
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
            linux.shellquote(cmdstr)))
    keyfile = None
    with tempfile.NamedTemporaryFile(delete=False) as f:
        keyfile.write(keystr)
        keyfile = f.name
    try:
        return shell.check_run("ssh {} -p {} {} -i {} {}".format(
            target,
            port,
            "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
            keyfile,
            linux.shellquote(cmdstr)))
    finally:
        os.remove(keyfile)

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
        v.size, _, v.physicalSize = dom.blockInfo(v.name)
        return v

    def listVolumes(dom, disk):
        if not disk:
            return []
        if isinstance(disk, list):
            return [ getVolume(dom, d) for d in disk ]
        return [ getVolume(dom, disk) ]

    if dxml is None:
        dxml = xmlobject.loads(dom.XMLDesc(0))

    volumes = filter(lambda v:v, listVolumes(dom, dxml.devices.disk))
    if len(volumes) == 0:
        raise Exception("no disks found for VM: "+dom.name())

    if len(filter(lambda v: v.type == 'ROOT', volumes)) == 0:
        volumes[0].type = 'ROOT'

    return volumes

def listVirtualMachines(url, sasluser, saslpass, keystr):
    def getMac(ifxml):
        return ifxml.mac.address_ if ifxml.mac else ""

    def getMacs(iface):
        if not iface:
            return []
        if isinstance(iface, list):
            return [ getMac(inf) for inf in iface ]
        return [ getMac(iface) ]

    vms = []
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
            info.macAddresses = getMacs(dxml.devices.interface)
            info.volumes = getVolumes(dom, dxml)

            vms.append(info)

    return qemuVersion, libvirtVersion, vms


QOS_IFB = "ifb0"

def getRealStoragePath(storagePath):
    return os.path.abspath(os.path.join(storagePath, "v2v-cache"))

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
        if cmd.storagePath:
            spath = getRealStoragePath(cmd.storagePath)
            with open('/etc/exports.d/zs-v2v.exports', 'w') as f:
                f.write("{} *(rw,sync,no_root_squash)\n".format(spath))

        shell.check_run('systemctl restart nfs-server')
        shell.check_run('iptables-save | grep -w 2049 || iptables -I INPUT -p tcp --dport 2049 -j ACCEPT')
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def listvm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ListVmRsp()

        if cmd.sshPassword and not cmd.sshPrivKey:
            target, port = getSshTargetAndPort(cmd.libvirtURI)
            privkey = os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa")
            if not os.path.exists(privkey):
                shell.check_run("ssh-keygen -t rsa -N '' -f {}".format(privkey))
            cmdstr = "HOME={4} timeout 10 sshpass -p {0} ssh-copy-id -i {5} -p {1} {2} {3}".format(
                    linux.shellquote(cmd.sshPassword),
                    port,
                    "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
                    target,
                    os.path.expanduser("~"),
                    privkey+".pub")
            shell.check_run(cmdstr)

        rsp.qemuVersion, rsp.libvirtVersion, rsp.vms = listVirtualMachines(cmd.libvirtURI,
                cmd.saslUser,
                cmd.saslPass,
                cmd.sshPrivKey)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def convert(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConvertRsp()

        real_storage_path = getRealStoragePath(cmd.storagePath)
        storage_dir = os.path.join(real_storage_path, cmd.srcVmUuid)
        linux.mkdir(storage_dir)

        try:
            runSshCmd(cmd.libvirtURI, cmd.sshPrivKey,
                    "mkdir -p /tmp/zs-v2v && ls /tmp/zs-v2v/{} 2>/dev/null || timeout 10 mount {}:/{} /tmp/zs-v2v".format(
                        cmd.srcVmUuid,
                        cmd.managementIp,
                        real_storage_path))
        except shell.ShellError as ex:
            logger.info(str(ex))
            raise Exception('target host cannot access NFS on {}'.format(cmd.managementIp))

        volumes = None
        with LibvirtConn(cmd.libvirtURI, cmd.saslUser, cmd.saslPass, cmd.sshPrivKey) as c:
            dom = c.lookupByUUIDString(cmd.srcVmUuid)
            if not dom:
                raise Exception('VM not found: {}'.format(cmd.srcVmUuid))

            dxml = xmlobject.loads(dom.XMLDesc(0))
            if dxml.os.hasattr('firmware_') and dxml.os.firmware_ == 'efi':
                rsp.bootMode = 'UEFI'

            volumes = getVolumes(dom, dxml)

            for v in volumes:
                localpath = os.path.join(storage_dir, v.name)
                info = dom.blockJobInfo(v.name, 0)
                if os.path.exists(localpath) and not info:
                    os.remove(localpath)
                if not os.path.exists(localpath) and info:
                    raise Exception("unknown blockjob on disk: "+v.name)
                if info:
                    continue

                dom.blockCopy(v.name,
                    "<disk type='file'><source file='/tmp/zs-v2v/{}/{}'/><driver type='qcow2'/></disk>".format(cmd.srcVmUuid, v.name),
                    None,
                    libvirt.VIR_DOMAIN_BLOCK_COPY_TRANSIENT_JOB)

            for v in volumes:
                while True:
                    info = dom.blockJobInfo(v.name, 0)
                    if not info:
                        raise Exception('blockjob not found on disk: '+v.name)
                    if info['cur'] == info['end']:
                        break
                    time.sleep(5)

            curstat, _ = dom.state()
            if curstat != libvirt.VIR_DOMAIN_PAUSED:
                dom.suspend()

            try:
                for v in volumes:
                    dom.blockJobAbort(v.name)
            finally:
                if curstat != libvirt.VIR_DOMAIN_PAUSED:
                    dom.resume()

        # TODO
        #  - monitor progress

        def makeVolumeInfo(v, devId):
            return { "installPath": os.path.join(storage_dir, v.name),
                     "actualSize":  v.physicalSize,
                     "virtualSize": v.size,
                     "deviceId":    devId }

        idx = 1
        rv, dvs = None, []
        for v in volumes:
            if v.type == 'ROOT':
                rv = makeVolumeInfo(v, 0)
            else:
                dvs.append(makeVolumeInfo(v, idx))
                idx += 1

        rsp.rootVolumeInfo = rv
        rsp.dataVolumeInfos = dvs

        return jsonobject.dumps(rsp)


    @in_bash
    @kvmagent.replyerror
    def clean(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if not cmd.srcVmUuid:
            cleanUpPath = cmd.storagePath
        else:
            cleanUpPath = os.path.join(cmd.storagePath, cmd.srcVmUuid)

        linux.rm_dir_force(cleanUpPath)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def cancel_and_clean_convert(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        clean_up_path = os.path.join(cmd.storagePath, cmd.srcVmUuid)
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

        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def delete_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        return jsonobject.dumps(rsp)

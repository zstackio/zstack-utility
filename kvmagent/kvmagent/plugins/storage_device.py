import random
import re
import time
import string
import os.path

import simplejson

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import multipath
from zstacklib.utils import lock
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import lvm
from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import thread
from zstacklib.utils import misc

logger = log.get_logger(__name__)


class RetryException(Exception):
    pass


class AgentCmd(object):
    def __init__(self):
        pass


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


class RaidPhysicalDriveStruct(object):
    rotationRate = None  # type: int
    size = None  # type: long
    diskGroup = None  # type: int
    deviceId = None  # type: int
    slotNumber = None  # type: int
    enclosureDeviceId = None  # type: int

    def __init__(self):
        self.raidLevel = None
        self.enclosureDeviceId = None
        self.slotNumber = None
        self.deviceId = None
        self.diskGroup = None
        self.wwn = None
        self.serialNumber = None
        self.deviceModel = None
        self.size = 0
        self.driveState = None
        self.locateStatus = None
        self.driveType = None
        self.mediaType = None
        self.rotationRate = None
        self.raidControllerSasAddreess = None
        self.raidControllerProductName = None
        self.raidControllerNumber = None


class SmartDataStruct(object):
    rawValue = None  # type: long
    thresh = None  # type: int
    worst = None  # type: int
    value = None  # type: int
    id = None  # type: int

    def __init__(self):
        self.id = None
        self.attributeName = None
        self.flag = None
        self.value = None
        self.worst = None
        self.thresh = None
        self.type = None
        self.updated = None
        self.whenFailed = None
        self.rawValue = None
        self.state = None


class RaidPhysicalDriveSmartRsp(object):
    smartDataStructs = None  # type: list[SmartDataStruct]

    def __init__(self):
        self.smartDataStructs = None


class RaidPhysicalDriveSmartTestRsp(object):
    result = None  # type: str

    def __init__(self):
        self.result = None


class RaidScanRsp(object):
    raidPhysicalDriveStructs = None  # type: list[RaidPhysicalDriveStruct]

    def __init__(self):
        self.raidPhysicalDriveStructs = []

class ScsiLunStruct(object):
    def __init__(self):
        self.wwids = []
        self.vendor = ""
        self.model = ""
        self.wwn = ""
        self.serial = ""
        self.type = ""
        self.path = ""
        self.size = ""
        self.hctl = ""
        self.multipathDeviceUuid = ""


class FiberChannelLunStruct(ScsiLunStruct):
    def __init__(self):
        super(FiberChannelLunStruct, self).__init__()
        self.storageWwnn = ""


class IscsiTargetStruct(object):
    iscsiLunStructList = None  # type: list[IscsiLunStruct]

    def __init__(self):
        self.iqn = ""
        self.iscsiLunStructList = []


class IscsiLunStruct(ScsiLunStruct):
    def __init__(self):
        super(IscsiLunStruct, self).__init__()
        self.hctl = ""


class FcSanScanRsp(AgentRsp):
    def __init__(self):
        super(FcSanScanRsp, self).__init__()
        self.fiberChannelLunStructs = []
        self.hbaWwnns = []


class IscsiLoginCmd(AgentCmd):
    @log.sensitive_fields("iscsiChapUserPassword")
    def __init__(self):
        super(IscsiLoginCmd, self).__init__()
        self.iscsiServerIp = None
        self.iscsiServerPort = None
        self.iscsiChapUserName = None
        self.iscsiChapUserPassword = None
        self.iscsiTargets = []


class IscsiLoginRsp(AgentRsp):
    iscsiTargetStructList = None  # type: list[IscsiTargetStruct]

    def __init__(self):
        super(IscsiLoginRsp, self).__init__()
        self.iscsiTargetStructList = []


class IscsiLogoutCmd(AgentCmd):
    @log.sensitive_fields("iscsiChapUserPassword")
    def __init__(self):
        super(IscsiLogoutCmd, self).__init__()
        self.iscsiServerIp = None
        self.iscsiServerPort = None
        self.iscsiChapUserName = None
        self.iscsiChapUserPassword = None
        self.iscsiTargets = []


class StorageDevicePlugin(kvmagent.KvmAgent):

    ISCSI_LOGIN_PATH = "/storagedevice/iscsi/login"
    ISCSI_LOGOUT_PATH = "/storagedevice/iscsi/logout"
    FC_SCAN_PATH = "/storagedevice/fc/scan"
    MULTIPATH_ENABLE_PATH = "/storagedevice/multipath/enable"
    ATTACH_SCSI_LUN_PATH = "/storagedevice/scsilun/attach"
    DETACH_SCSI_LUN_PATH = "/storagedevice/scsilun/detach"
    DETACH_SCSI_DEV_PATH = "/storagedevice/scsilun/detachdev"
    RAID_SCAN_PATH = "/storagedevice/raid/scan"
    RAID_SMART_PATH = "/storagedevice/raid/smart"
    RAID_LOCATE_PATH = "/storagedevice/raid/locate"
    RAID_SELF_TEST_PATH = "/storagedevice/raid/selftest"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.ISCSI_LOGIN_PATH, self.iscsi_login, cmd=IscsiLoginCmd())
        http_server.register_async_uri(self.ISCSI_LOGOUT_PATH, self.iscsi_logout, cmd=IscsiLogoutCmd())
        http_server.register_async_uri(self.FC_SCAN_PATH, self.scan_sg_devices)
        http_server.register_async_uri(self.MULTIPATH_ENABLE_PATH, self.enable_multipath)
        http_server.register_async_uri(self.ATTACH_SCSI_LUN_PATH, self.attach_scsi_lun)
        http_server.register_async_uri(self.DETACH_SCSI_LUN_PATH, self.detach_scsi_lun)
        http_server.register_async_uri(self.DETACH_SCSI_DEV_PATH, self.detach_scsi_dev)
        http_server.register_async_uri(self.RAID_SCAN_PATH, self.raid_scan)
        http_server.register_async_uri(self.RAID_SMART_PATH, self.raid_smart)
        http_server.register_async_uri(self.RAID_LOCATE_PATH, self.raid_locate)
        http_server.register_async_uri(self.RAID_SELF_TEST_PATH, self.drive_self_test)

    def stop(self):
        pass

    @kvmagent.replyerror
    @bash.in_bash
    def attach_scsi_lun(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        lvm.unpriv_sgio()

        if not cmd.multipath and "mpath" in cmd.volume.installPath:
            cmd.volume.installPath = self.get_slave_path(cmd.volume.installPath)

        if not os.path.exists(cmd.volume.installPath):
            shell.run("timeout 30 iscsiadm -m session -R")

        vm = vm_plugin.get_vm_by_uuid(cmd.vmInstanceUuid)
        vm.attach_data_volume(cmd.volume, cmd.addons)
        return jsonobject.dumps(rsp)

    def get_slave_path(self, multipath_path):
        def get_wwids(dev_name):
            symlinks = shell.call("udevadm info -q symlink -n %s" % dev_name).strip().split()
            wwids = map(lambda p: os.path.basename(p), filter(lambda s: 'by-id' in s, symlinks))
            wwids.sort()

            stable_wwids = filter(lambda w: "lvm-pv" not in w, wwids)
            return stable_wwids if stable_wwids else wwids

        dm = os.path.basename(os.path.realpath(multipath_path))
        slaves = linux.listdir("/sys/class/block/%s/slaves/" % dm)
        if not slaves:
            raise "can not find any slave from multpath device: %s" % multipath_path
        return "/dev/disk/by-id/%s" % get_wwids(slaves[0])[0]

    @kvmagent.replyerror
    @bash.in_bash
    def detach_scsi_dev(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        def _do_detach_disks(devpaths):
            for devpath in devpaths:
                logger.info("flushing disk: %s" % devpath)
                shell.run('blockdev --flushbufs %s' % devpath)
                linux.write_file("/sys/block/%s/device/delete" % os.path.basename(devpath), "1")

        dev_path = os.path.realpath('/dev/disk/by-id/scsi-%s' % cmd.wwid)
        r, mpath_dev = bash.bash_ro("multipath -v1 -l %s" % dev_path)
        if r != 0:
            _do_detach_disks([dev_path])
        else:
            mpath = os.path.join("/dev/mapper", mpath_dev.strip())
            logger.info("flushing multipath: %s" % mpath)
            bash.bash_r("multipath -f %s" % mpath)
            slaves = linux.listdir('/sys/class/block/%s/slaves' % os.path.basename(os.path.realpath(mpath)))
            _do_detach_disks([os.path.join("/dev", s) for s in slaves])

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def detach_scsi_lun(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        vm = vm_plugin.get_vm_by_uuid(cmd.vmInstanceUuid)
        try:
            vm.detach_data_volume(cmd.volume)
        except Exception as e:
            # failure to detach volume may be due to the multipath of the scsi changed, try again.
            if cmd.volume.installPath == "/dev/disk/by-id/scsi-%s" % cmd.wwid:
                cmd.volume.installPath = "/dev/disk/by-id/dm-uuid-mpath-%s" % cmd.wwid
                vm.detach_data_volume(cmd.volume)
            elif cmd.volume.installPath == "/dev/disk/by-id/dm-uuid-mpath-%s" % cmd.wwid:
                cmd.volume.installPath = "/dev/disk/by-id/scsi-%s" % cmd.wwid
                vm.detach_data_volume(cmd.volume)
            else:
                raise e

        return jsonobject.dumps(rsp)

    @lock.lock('iscsiadm')
    @kvmagent.replyerror
    @bash.in_bash
    def iscsi_login(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = IscsiLoginRsp()

        @linux.retry(times=5, sleep_time=1)
        def discovery_iscsi(iscsiServerIp, iscsiServerPort):
            r, o, e = bash.bash_roe(
                "timeout 10 iscsiadm -m discovery --type sendtargets --portal %s:%s" % (
                    iscsiServerIp, iscsiServerPort))
            if r != 0:
                raise RetryException("can not discovery iscsi portal %s:%s, cause %s" % (iscsiServerIp, iscsiServerPort, e))

            iqns = []
            for i in o.splitlines():
                if i.startswith("%s:%s," % (iscsiServerIp, iscsiServerPort)):
                    iqns.append(i.strip().split(" ")[-1])
            return iqns

        def list_iscsi_disks(iscsiServerIp, iscsiServerPort, iscsiIqn):
            s = "%s:%s" % (iscsiServerIp, iscsiServerPort)
            return [ f for f in os.listdir("/dev/disk/by-path") if s in f and iscsiIqn in f ]

        def refresh_mpath(disks_by_path):
            devpaths = [os.path.realpath(os.path.join("/dev/disk/by-path", s)) for s in disks_by_path]
            mpaths = set()
            for devpath in devpaths:
                if devpath: mpaths.add(shell.call("multipath -l -v1 "+devpath).strip())
            for mpath in mpaths:
                if mpath: shell.run("multipathd resize map "+mpath)

        @linux.retry(times=20, sleep_time=1)
        def wait_iscsi_mknode(iscsiServerIp, iscsiServerPort, iscsiIqn, e=None):
            disks_by_dev = list_iscsi_disks(iscsiServerIp, iscsiServerPort, iscsiIqn)
            sid = bash.bash_o("iscsiadm -m session | grep %s:%s | grep %s | awk '{print $2}'" % (iscsiServerIp, iscsiServerPort, iscsiIqn)).strip("[]\n ")
            if sid == "" or sid is None:
                err = "sid not found, this may because chap authentication failed"
                if e != None and e != "":
                    err += " ,error: %s" % e
                raise RetryException(e)
            bash.bash_o("iscsiadm -m session -r %s --rescan" % sid)
            #Get the host_Number of iqn, Will match the HTCL attribute of iscsi according to Host_number
            host_Number = bash.bash_o("iscsiadm -m session -P 3 --sid=%s | grep 'Host Number:' | awk '{print $3}'" % sid).strip()
            #Use HCTL, IQN, "-" to match the number of unmounted Luns according to lsscsi --transport
            disks_by_no_mapping_lun = bash.bash_o("lsscsi --transport | grep -w %s | awk '{print $1,$NF}' | grep -E '\<%s\>:[[:digit:]]*:[[:digit:]]*:[[:digit:]]*' | awk '{print $NF}' | grep -x '-'" % (iscsiIqn, host_Number)).strip().splitlines()
            disks_by_iscsi = bash.bash_o("iscsiadm -m session -P 3 --sid=%s | grep Lun" % sid).strip().splitlines()
            if len(disks_by_dev) < (len(disks_by_iscsi) - len(disks_by_no_mapping_lun)):
                raise RetryException("iscsiadm says there are [%s] disks but only found [%s] disks on /dev/disk[%s], so not all disks loged in, and you can check the iscsi mounted disk by lsscsi --transport"
                                     "it may recover after a while so check and login again" %((len(disks_by_iscsi) - len(disks_by_no_mapping_lun)), len(disks_by_dev), disks_by_dev))

        def check_iscsi_conf():
            shell.call("sed -i 's/.*iscsid.startup.*=.*/iscsid.startup = \/bin\/systemctl start iscsid.socket iscsiuio.soccket/' /etc/iscsi/iscsid.conf", exception=False)

        check_iscsi_conf()
        path = "/var/lib/iscsi/nodes"
        self.clean_iscsi_cache_configuration(path, cmd.iscsiServerIp, cmd.iscsiServerPort)
        iqns = cmd.iscsiTargets
        if iqns is None or len(iqns) == 0:
            try:
                iqns = discovery_iscsi(cmd.iscsiServerIp, cmd.iscsiServerPort)
            except Exception as e:
                current_hostname = linux.get_hostname()
                rsp.error = "login iscsi server %s:%s on host %s failed, because %s" % \
                            (cmd.iscsiServerIp, cmd.iscsiServerPort, current_hostname, e.message)
                rsp.success = False
                return jsonobject.dumps(rsp)
    
        if iqns is None or len(iqns) == 0:
            rsp.iscsiTargetStructList = []
            return jsonobject.dumps(rsp)

        for iqn in iqns:
            t = IscsiTargetStruct()
            t.iqn = iqn
            try:
                if cmd.iscsiChapUserName and cmd.iscsiChapUserPassword:
                    bash.bash_o(
                        'iscsiadm --mode node --targetname "%s" -p %s:%s --op=update --name node.session.auth.authmethod --value=CHAP' % (
                            iqn, cmd.iscsiServerIp, cmd.iscsiServerPort))
                    bash.bash_o(
                        'iscsiadm --mode node --targetname "%s" -p %s:%s --op=update --name node.session.auth.username --value=%s' % (
                            iqn, cmd.iscsiServerIp, cmd.iscsiServerPort, cmd.iscsiChapUserName))
                    bash.bash_o(
                        'iscsiadm --mode node --targetname "%s" -p %s:%s --op=update --name node.session.auth.password --value=%s' % (
                            iqn, cmd.iscsiServerIp, cmd.iscsiServerPort, linux.shellquote(cmd.iscsiChapUserPassword)))                
                r, o, e = bash.bash_roe('iscsiadm --mode node --targetname "%s" -p %s:%s --login' %
                            (iqn, cmd.iscsiServerIp, cmd.iscsiServerPort))
                wait_iscsi_mknode(cmd.iscsiServerIp, cmd.iscsiServerPort, iqn, e)
            finally:
                disks = list_iscsi_disks(cmd.iscsiServerIp, cmd.iscsiServerPort, iqn)

                # refresh mpath dev if any
                refresh_mpath(disks)

                if len(disks) == 0:
                    rsp.iscsiTargetStructList.append(t)
                else:
                    scsi_info = lvm.get_lsscsi_info()
                    for d in disks:
                        lun_struct = self.get_disk_info_by_path(d.strip(), scsi_info)
                        if lun_struct is not None:
                            t.iscsiLunStructList.append(lun_struct)
                    rsp.iscsiTargetStructList.append(t)

        linux.set_fail_if_no_path()
        return jsonobject.dumps(rsp)

    @staticmethod
    def clean_iscsi_cache_configuration(path, iscsiServerIp, iscsiServerPort):
        # clean cache configuration file:/var/lib/iscsi/nodes/iqnxxx/ip,port
        results = bash.bash_o(("ls %s/*/ | grep %s | grep %s" % (path, iscsiServerIp, iscsiServerPort))).strip().splitlines()
        if results is None or len(results) == 0:
            return
        for result in results:
            dpaths = bash.bash_o("dirname %s/*/%s" % (path, result)).strip().splitlines()
            if dpaths is None or len(dpaths) == 0:
                continue
            for dpath in dpaths:
                ipath = "%s/%s" % (dpath, result)
                if os.path.isdir(ipath):
                    linux.rm_dir_force(ipath)
                else:
                    linux.rm_file_force(ipath)

    @staticmethod
    def get_disk_info_by_path(path, scsi_info):
        # type: (str) -> IscsiLunStruct
        r = bash.bash_r("multipath -l | grep -e '/multipath.conf' | grep -e 'line'")
        if r == 0:
            current_hostname = linux.get_hostname()
            raise Exception(
                "The multipath.conf setting on host[%s] may be error, please check and try again" % current_hostname)

        abs_path = os.path.realpath("/dev/disk/by-path/%s" % path)
        candidate_struct = lvm.get_device_info(abs_path.split("/")[-1], scsi_info)
        if candidate_struct is None:
            return None
        lun_struct = IscsiLunStruct()
        lun_struct.path = path
        lun_struct.size = candidate_struct.size
        lun_struct.hctl = candidate_struct.hctl
        lun_struct.serial = candidate_struct.serial
        lun_struct.model = candidate_struct.model
        lun_struct.vendor = candidate_struct.vendor
        lun_struct.type = candidate_struct.type
        lun_struct.wwn = candidate_struct.wwn
        lun_struct.wwids = [candidate_struct.wwid]
        if lvm.is_slave_of_multipath(abs_path):
            lun_struct.type = "mpath"
        return lun_struct

    @lock.lock('iscsiadm')
    @kvmagent.replyerror
    def iscsi_logout(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        iqns = cmd.iscsiTargets
        if iqns is None or len(iqns) == 0:
            iqns = shell.call("timeout 10 iscsiadm -m discovery --type sendtargets --portal %s:%s | awk '{print $2}'" % (
                cmd.iscsiServerIp, cmd.iscsiServerPort)).strip().splitlines()

        if iqns is None or len(iqns) == 0:
            rsp.iscsiTargetStructList = []
            return jsonobject.dumps(rsp)

        for iqn in iqns:
            r = bash.bash_r("iscsiadm -m session | grep %s:%s | grep %s" % (cmd.iscsiServerIp, cmd.iscsiServerPort, iqn))
            if r == 0:
                shell.call('timeout 10 iscsiadm --mode node --targetname "%s" -p %s:%s --logout' % (iqn, cmd.iscsiServerIp, cmd.iscsiServerPort))
                shell.call('timeout 10 iscsiadm -m node -o delete -T "%s" -p %s:%s' % (iqn, cmd.iscsiServerIp, cmd.iscsiServerPort))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def scan_sg_devices(self, req):
        #1. find fc devices
        #2. distinct by device wwid and storage wwn
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = FcSanScanRsp()
        bash.bash_roe("timeout 120 /usr/bin/rescan-scsi-bus.sh -a >/dev/null")
        rsp.fiberChannelLunStructs = self.get_fc_luns(cmd.rescan)
        if cmd.identifiers:
            for disk_id in cmd.identifiers:
                p = '/dev/disk/by-id/dm-uuid-mpath-'+disk_id
                if os.path.exists(p):
                    shell.run('multipathd resize map '+os.path.realpath(p))
        linux.set_fail_if_no_path()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def raid_smart(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RaidPhysicalDriveSmartRsp()

        r, raid_info, e = bash.bash_roe("/opt/MegaRAID/MegaCli/MegaCli64 -LdPdInfo -aALL")
        if r != 0:
            raise Exception("can not execute MegaCli: returnCode: %s, stdout: %s, stderr: %s" % (r, raid_info, e))

        bus_number = self.get_bus_number()
        drive = self.get_megaraid_device_info_megacli("/dev/bus/%d -d megaraid,%d" % (bus_number, cmd.deviceNumber), raid_info)
        if drive.wwn != cmd.wwn:
            raise Exception("expect drive[busNumber %s, deviceId %s, slotNumber %s] wwn is %s, but is %s actually" %
                            (bus_number, cmd.deviceNumber, cmd.slotNumber, cmd.wwn, drive.wwn))

        rsp.smartDataStructs = self.get_smart_data(bus_number, cmd.deviceNumber)
        return jsonobject.dumps(rsp)

    @staticmethod
    def get_smart_data(busNumber, deviceNumber):
        # type: (int, int) -> list[SmartDataStruct]
        r, text, e = bash.bash_roe("smartctl --all /dev/bus/%s -d megaraid,%s" % (busNumber, deviceNumber))
        if r != 0 and "vendor specific smart attributes with thresholds" not in text.lower():
            raise Exception("read smart info failed, return: %s, stdout: %s, stderr: %s" % (r, text, e))
        data = []
        in_data = None
        for l in text.splitlines():
            if "vendor specific smart attributes with thresholds" in l.lower():
                in_data = True
                continue
            if "smart error log version" in l.lower():
                break
            if in_data is None:
                continue
            if "id" in l.lower() and "attribute_name" in l.lower():
                continue
            if l.strip() == "":
                continue
            data.append(l)

        if len(data) == 0:
            logger.warn("can not find smart data!")
            return []

        result = []
        attrs = ["id", "attributeName", "flag", "value", "worst", "thresh", "type", "updated", "whenFailed", "rawValue"]
        for d in data:
            logger.debug("processing smart data %s" % d)
            r = SmartDataStruct()
            for column_number in range(len(attrs)):
                if d.split()[column_number].isdigit():
                    exec("r.%s = int(\"%s\")" % (attrs[column_number], d.split()[column_number]))
                else:
                    exec("r.%s = \"%s\"" % (attrs[column_number], d.split()[column_number]))
            if r.value < r.thresh:
                r.state = "error"
            elif r.value - r.thresh < int(r.thresh * 0.2):
                r.state = "warning"
            else:
                r.state = "health"
            result.append(r)

        return result

    @kvmagent.replyerror
    @bash.in_bash
    def raid_locate(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        if misc.isHyperConvergedHost():
            r, o, e = bash.bash_roe("/opt/MegaRAID/storcli/storcli64 /call/vall show all J")
            if r == 0 and jsonobject.loads(o)['Controllers'][0]['Command Status']['Status'] == "Success":
                self.mega_raid_locate_storcli(cmd, o)
                return jsonobject.dumps(rsp)
        else:
            r, o, e = bash.bash_roe("/opt/MegaRAID/MegaCli/MegaCli64 -LdPdInfo -aALL")
            if r == 0 and "Adapter #" in o:
                self.mega_raid_locate_megacli(cmd, o)
                return jsonobject.dumps(rsp)

        r, o, e = bash.bash_roe("arcconf list")
        if r == 0 and "Controller ID" in o:
            self.arcconf_raid_locate(cmd)
            return jsonobject.dumps(rsp)

        r, o, e = bash.bash_roe("sas3ircu list")
        if r == 0 and "Index" in o:
            self.sas_raid_locate(cmd)
            return jsonobject.dumps(rsp)
    
        raise Exception("Failed to locate device[wwn: %s, enclosureDeviceID: %s, slotNumber: %s]" % (
            cmd.wwn, cmd.enclosureDeviceID, cmd.slotNumber,))

    @bash.in_bash
    def sas_raid_locate(self, cmd):
        command = "on" if cmd.locate is True else "off"
        bash.bash_errorout("sas3ircu %s locate %s:%s %s" % (
            cmd.raidControllerNumber, cmd.enclosureDeviceID, cmd.slotNumber, command))

    @bash.in_bash
    def arcconf_raid_locate(self, cmd):
        rsp = AgentRsp()
        r, o = bash.bash_ro("arcconf getconfig %s PD | grep -B 1 'Enclosure %s, Slot %s' | grep 'Reported Channel'" % (
            cmd.raidControllerNumber, cmd.enclosureDeviceID, cmd.slotNumber))
        if r != 0 or o.strip == "":
            raise Exception("Failed to locate device[wwn: %s, enclosureDeviceID: %s, slotNumber: %s]" % (
                cmd.wwn, cmd.enclosureDeviceID, cmd.slotNumber,))
    
        channel = o.splitlines()[0].split(":")[2].split(",")[0].strip()
        command = "start" if cmd.locate is True else "stop"

        r, o, e = bash.bash_roe(
            "arcconf identify %s device %s %s %s" % (cmd.raidControllerNumber, channel, cmd.deviceNumber, command))
        if r != 0 and "No devices are blinking" not in e:
            raise Exception(
                "Failed to locate disk drive[%s:%s], stderr: %s" % (cmd.enclosureDeviceID, cmd.slotNumber, e))
        return jsonobject.dumps(rsp)

    @bash.in_bash
    def mega_raid_locate_megacli(self, cmd, raid_info):
        bus_number = self.get_bus_number()
        drive = self.get_megaraid_device_info_megacli("/dev/bus/%d -d megaraid,%d" % (bus_number, cmd.deviceNumber), raid_info)
        if drive.wwn != cmd.wwn:
            raise Exception("expect drive[busNumber %s, deviceId %s, slotNumber %s] wwn is %s, but is %s actually" %
                            (bus_number, cmd.deviceNumber, cmd.slotNumber, cmd.wwn, drive.wwn))

        command = "start" if cmd.locate is True else "stop"
        
        # -a specific a adaptor id but not bus number
        # TODO: fix hardcode because mini only have one adaptor
        bash.bash_errorout("/opt/MegaRAID/MegaCli/MegaCli64 -PdLocate -%s -physdrv[%d:%d] -a0" % (
            command, cmd.enclosureDeviceID, cmd.slotNumber))

    @bash.in_bash
    def mega_raid_locate_storcli(self, cmd, raid_info):
        # when disk status is abnormal, this command will return no 0.
        pd_info = bash.bash_o("/opt/MegaRAID/storcli/storcli64 /call/eall/sall show all J")
        bus_number = self.get_bus_number()
        drive = self.get_megaraid_device_info_storcli("/dev/bus/%d -d megaraid,%d" % (bus_number, cmd.deviceNumber),
                                                      raid_info, pd_info)
        if drive.wwn != cmd.wwn:
            raise Exception("expect drive[busNumber %s, deviceId %s, slotNumber %s] wwn is %s, but is %s actually" %
                            (bus_number, cmd.deviceNumber, cmd.slotNumber, cmd.wwn, drive.wwn))

        command = "start" if cmd.locate is True else "stop"
        pd_path = "/c%s/e%s/s%s" % (drive.raidControllerNumber, cmd.enclosureDeviceID, cmd.slotNumber)

        bash.bash_errorout("/opt/MegaRAID/storcli/storcli64 %s %s locate" % (
            pd_path, command))

    @bash.in_bash
    def get_bus_number(self):
        r, megaraid_info, e = bash.bash_roe("smartctl --scan | grep -E 'megaraid_disk_[0-9]+\], SCSI device'")
        if r != 0:
            raise Exception("failed to get bus info")
        
        # get megaraid_info like following 
        # /dev/bus/0 -d megaraid,0 # /dev/bus/0 [megaraid_disk_00], SCSI device
        return int(megaraid_info.split("\n")[0].split(" ")[0][-1])
            
    @kvmagent.replyerror
    @bash.in_bash
    def drive_self_test(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RaidPhysicalDriveSmartTestRsp()

        r, raid_info, e = bash.bash_roe("/opt/MegaRAID/MegaCli/MegaCli64 -LdPdInfo -aALL")
        if r != 0:
            raise Exception("can not execute MegaCli: returnCode: %s, stdout: %s, stderr: %s" % (r, raid_info, e))

        bus_number = self.get_bus_number()
        drive = self.get_megaraid_device_info_megacli("/dev/bus/%d -d megaraid,%d" % (bus_number, cmd.deviceNumber), raid_info)
        if drive.wwn != cmd.wwn:
            raise Exception("expect drive[busNumber %s, deviceId %s, slotNumber %s] wwn is %s, but is %s actually" %
                            (bus_number, cmd.deviceNumber, cmd.slotNumber, cmd.wwn, drive.wwn))

        rsp.result = self.run_self_test(bus_number, cmd.deviceNumber, cmd.wwn)
        return jsonobject.dumps(rsp)

    @staticmethod
    @bash.in_bash
    @lock.file_lock("/var/run/zstack/local_raid_self_test.lock")
    def run_self_test(busNumber, deviceNumber, wwn):
        @linux.retry(10, 1)
        @bash.in_bash
        def self_test_is_running(bus, device):
            r = bash.bash_r("smartctl -l selftest -d megaraid,%s /dev/bus/%s | grep 'Self-test routine in progress'" % (device, bus))
            if r == 0:
                return
            r, o, e = bash.bash_roe("smartctl -a /dev/bus/%s -d megaraid,%s" % (bus, device))
            if "Self-test routine in progress" in o+e:
                return
            raise RetryException("can not find self test in progress on drive %s" % wwn)

        @linux.retry(10, 30)
        @bash.in_bash
        def get_self_test_result(bus, device):
            r, o = bash.bash_ro(
                "smartctl -l selftest -d megaraid,%s /dev/bus/%s | grep -E '^# 1'" % (device, bus))
            if r != 0 or "00%" not in o:
                raise RetryException("latest self test not finished on drive %s" % wwn)
            return o.split("Short offline")[1].split("00%")[0].strip()

        @bash.in_bash
        def check_no_running_test(bus, device):
            r, o = bash.bash_ro(
                "smartctl -a /dev/bus/%s -d megaraid,%s | grep 'Self-test routine in progress' -C 5" % (bus, device))
            if r == 0:
                return False
            return True

        for i in range(5):
            if check_no_running_test(busNumber, deviceNumber) is True:
                break
            if i == 4:
                # bash.bash_r("smartctl -X /dev/bus/%s -d megaraid,%s")
                raise Exception("there is running test on drive wwn %s" % wwn)
            time.sleep(30)

        bash.bash_errorout("smartctl --test=short /dev/bus/%s -d megaraid,%s" % (busNumber, deviceNumber))
        self_test_is_running(busNumber, deviceNumber)
        return get_self_test_result(busNumber, deviceNumber)

    @kvmagent.replyerror
    @bash.in_bash
    def raid_scan(self, req):
        # 1. find raid device
        # 2. get each device info

        # TODO: host has different types of raid cards at the same time.
        rsp = RaidScanRsp()
        r, o, e = bash.bash_roe("smartctl --scan | grep megaraid")
        if r == 0 and o.strip() != "":
            if misc.isHyperConvergedHost():
                rsp.raidPhysicalDriveStructs = self.get_megaraid_devices_storcli(o)
            else:
                rsp.raidPhysicalDriveStructs = self.get_megaraid_devices_megacli(o)
            return jsonobject.dumps(rsp)

        r, o, e = bash.bash_roe("arcconf list | grep -A 8 'Controller ID' | awk '{print $2}'")
        if r == 0 and o.strip() != "":
            rsp.raidPhysicalDriveStructs = self.get_arcconf_device(o)
            return jsonobject.dumps(rsp)

        r, o, e = bash.bash_roe("sas3ircu list | grep -A 8 'Index' | awk '{print $1}'")
        if r == 0 and o.strip() != "":
            rsp.raidPhysicalDriveStructs = self.get_sas_device(o)
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @bash.in_bash
    def get_megaraid_devices_megacli(self, smart_scan_result):
        # type: (str) -> list[RaidPhysicalDriveStruct]
        result = []
        r1, raid_info = bash.bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -LdPdInfo -aALL")
        r2, device_info = bash.bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -PDList -aAll")
        if r1 != 0 or r2 != 0:
            return result
        for line in smart_scan_result.splitlines():
            if line.strip() == "":
                continue
            d = self.get_megaraid_device_info_megacli(line, raid_info)
            if d.wwn is None or d.raidControllerSasAddreess is None:
                d = self.get_megaraid_device_info_megacli(line, device_info)
            if d.wwn is not None and d.raidControllerSasAddreess is not None:
                result.append(d)

        result.extend(self.get_nvme_device_info(result))
        if misc.isMiniHost():
            result.extend(self.get_missing(result))
        return result

    @bash.in_bash
    def get_missing(self, normal_devices):
        # type: (list[RaidPhysicalDriveStruct]) -> list[RaidPhysicalDriveStruct]
        result = []
        r, o = bash.bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -PdGetMissing -aALL")
        if r != 0:
            return result
        in_entry = False
        allocated_slots = map(lambda x: x.slotNumber, normal_devices)
        for line in o.splitlines():
            if in_entry is True and "mb" not in line.lower():
                in_entry = False
                continue
            if "size expected" in line.lower() and "no" in line.lower() and "array" in line.lower() and "row" in line.lower():
                in_entry = True
                continue
            if in_entry is True:
                d = RaidPhysicalDriveStruct()
                array = line.split()[1]
                row = line.split()[2]
                size = line.split()[3]
                unit = line.split()[4]
                d = self.get_info_from_size(size, unit, d, allocated_slots)
                if d.slotNumber is None:
                    continue
                allocated_slots.append(d.slotNumber)
                d.driveState = "Slot Missing"
                d.enclosureDeviceId = normal_devices[0].enclosureDeviceId
                d.raidControllerNumber = normal_devices[0].raidControllerNumber
                d.raidControllerProductName = normal_devices[0].raidControllerProductName
                d.raidControllerSasAddreess = normal_devices[0].raidControllerSasAddreess
                d.wwn = "5FFFFFF%s" % "".join(random.sample(string.ascii_letters + string.digits, 8))
                d.wwn = d.wwn.upper()
                result.append(d)
        return result

    @staticmethod
    def get_info_from_size(size, unit, d, allocated_slots):
        # type: (str, str, RaidPhysicalDriveStruct) -> RaidPhysicalDriveStruct
        #TODO(weiw): warning: very hard code
        if "mb" not in unit.lower():
            logger.warn("unexpected unit on missing drive 'Size Expected': %s" % unit)
            return d
        # d.size = int(size) * 1024 * 1024
        if int(size) <= 1048576: #It should be 952720MB or 3814697MB
            d.diskGroup = 0
            d.raidLevel = "raid1"
            d.slotNumber = 0 if 0 not in allocated_slots else 1
        else:
            d.diskGroup = 1
            d.raidLevel = "raid5"
            unallocated = set(filter(lambda x: x > 1, allocated_slots)).symmetric_difference({2, 3, 4, 5})
            d.slotNumber = unallocated.pop() if len(unallocated) > 0 else None
        return d

    @bash.in_bash
    def get_megaraid_device_info_megacli(self, line, raid_info):
        # type: (str, str) -> RaidPhysicalDriveStruct
        d = self.get_megaraid_device_disk_info_smartctl(line)

        in_correct_pd = False
        adapter = raid_level = enclosure_device_id = slot_number = disk_group = wwn = size = None
        for l in raid_info.splitlines():
            k = l.split(":")[0].lower()
            v = ":".join(l.split(":")[1:]).strip()
            if "adapter #" in l.lower():
                adapter = l.lower().split("adapter #")[1].strip()
                continue
            elif "raid level" in k:
                raid_level = self.convert_raid_level(v)
                continue
            elif "enclosure device id" in k:
                enclosure_device_id = int(v)
                continue
            elif "slot number" in k:
                slot_number = int(v)
                continue
            elif "drive's position" in k:
                disk_group = int(v.lower().split("diskgroup: ")[1].split(",")[0])
                continue
            elif "device id" in k and int(v) == d.deviceId:
                in_correct_pd = True
                continue
            elif "wwn" in k and d.wwn is None:
                wwn = v.lower()
                continue
            elif "raw size" in k and d.size == 0:
                if "TB" in v:
                    size = int(float(v.split(" TB")[0].strip()) * 1024 * 1024 * 1024 * 1024)
                elif "GB" in v:
                    size = int(float(v.split(" GB")[0].strip()) * 1024 * 1024 * 1024)
                elif "MB" in v:
                    size = int(float(v.split(" MB")[0].strip()) * 1024 * 1024)
                continue

            if in_correct_pd is True and "drive has flagged" in k:
                d.raidLevel = raid_level
                d.enclosureDeviceId = enclosure_device_id
                d.slotNumber = slot_number
                d.diskGroup = disk_group
                d.raidControllerNumber = adapter
                d.wwn = wwn if d.wwn is None else d.wwn
                d.size = size if d.size == 0 else d.size

                d.raidControllerProductName, d.raidControllerSasAddreess = self.get_megaraid_controller_info_megacli(adapter)
                return d
            elif in_correct_pd is False and "drive has flagged" in k:
                disk_group = None
                continue

            if in_correct_pd is False:
                continue

            if "pd type" in k:
                d.driveType = v
            elif "firmware state" in k:
                d.driveState = v
            elif "media type" in k:
                d.mediaType = self.convert_media_type(v)

        return d

    @bash.in_bash
    def get_megaraid_device_disk_info_smartctl(self, line):
        # type: (str, str) -> RaidPhysicalDriveStruct
        line = line.split(" #")[0]
        d = RaidPhysicalDriveStruct()
        r, o = bash.bash_ro("smartctl -i %s " % line)
        if r != 0 and misc.isMiniHost():
            logger.warn("can not get device %s info" % line)
            return d
        d.deviceId = int(line.split("megaraid,")[-1].strip())

        for l in o.splitlines():  # type: str
            k = l.split(":")[0].lower()
            v = ":".join(l.split(":")[1:]).strip()
            if "device model" in k:
                d.deviceModel = v
            elif "serial number" in k:
                d.serialNumber = v
            elif "lu wwn device id" in k:
                d.wwn = v.replace(" ", "")
            elif "user capacity" in k:
                d.size = int(v.split(" bytes")[0].strip().replace(",", ""))
            elif "rotation rate" in k and "solid state device" not in v.strip().lower():
                d.rotationRate = int(v.split(" rpm")[0].strip())

        return d

    @staticmethod
    @bash.in_bash
    def get_megaraid_controller_info_megacli(adapter_number):
        # type: (str) -> (str, str)
        r, o = bash.bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -AdpAllInfo -a%s | grep -E 'Product Name|SAS Address'" % adapter_number)
        if r != 0:
            return None, None
        return o.splitlines()[0].split(":")[1].strip(), o.splitlines()[1].split(":")[1].strip()

    @staticmethod
    @bash.in_bash
    def get_megaraid_controller_info_storcli(adapter_number):
        # type: (str) -> (str, str)
        r, o = bash.bash_ro("/opt/MegaRAID/storcli/storcli64 /c%s show | grep -E 'Product Name|SAS Address'" % adapter_number)
        if r != 0:
            return None, None
        return o.splitlines()[0].split("=")[1].strip(), o.splitlines()[1].split("=")[1].strip()

    @staticmethod
    def convert_media_type(origin):
        # type: (str) -> str
        origin = origin.lower()
        if "Solid State Device".lower() in origin:
            return "SSD"
        elif "Hard Disk Device".lower() in origin:
            return "HDD"
        else:
            return origin

    @staticmethod
    def convert_raid_level(origin):
        # type: (str) -> str
        origin = origin.lower()
        if "Primary-1, Secondary-0, RAID Level Qualifier-0".lower() in origin:
            return "raid1"
        elif "Primary-5, Secondary-0, RAID Level Qualifier-3".lower() in origin:
            return "raid5"
        elif "Primary-0, Secondary-0, RAID Level Qualifier-0".lower() in origin:
            return "raid0"
        elif "Primary-1, Secondary-3, RAID Level Qualifier-0".lower() in origin:
            return "raid10"
        elif "Primary-6, Secondary-0, RAID Level Qualifier-3".lower() in origin:
            return "raid6"
        else:
            return origin.strip()

    @bash.in_bash
    def get_fc_luns(self, rescan):
        o = bash.bash_o("ls -1c /sys/bus/scsi/devices/target*/fc_transport | awk -F 'target' '/^target/{print $2}'")
        fc_targets = o.strip().splitlines()
        if not fc_targets:
            logger.debug("not find any fc targets")
            return []

        fc_targets.sort()
        scsi_infos = filter(lambda s: "/dev/" in s, lvm.run_lsscsi_i())
        if not scsi_infos:
            logger.debug("not find any usable fc disks")
            return []

        luns = [[] for _ in enumerate(fc_targets)]

        def fill_lun_info(fc_target, i):
            for target_scsi_info in filter(lambda x: '[' + fc_target in x, scsi_infos):
                device_info = self.get_device_info(target_scsi_info, rescan)
                if device_info:
                    luns[i].append(device_info)

        threads = []
        for idx, fc_target in enumerate(fc_targets, start=0):
            threads.append(thread.ThreadFacade.run_in_thread(fill_lun_info, [fc_target, idx]))
        for t in threads:
            t.join()

        return sum(filter(None, luns), [])

    @kvmagent.replyerror
    @bash.in_bash
    def enable_multipath(self, req):
        rsp = AgentRsp()
        cmd_dict = simplejson.loads(req[http.REQUEST_BODY])
        lvm.enable_multipath()

        r = bash.bash_r("grep '^[[:space:]]*alias' /etc/multipath.conf")
        if r == 0:
            bash.bash_roe("sed -i 's/^[[:space:]]*alias/#alias/g' /etc/multipath.conf")
            bash.bash_roe("systemctl reload multipathd")

        if multipath.write_multipath_conf("/etc/multipath.conf", cmd_dict.get("blacklist", None)):
            bash.bash_roe("systemctl reload multipathd")

        linux.set_fail_if_no_path()
        return jsonobject.dumps(rsp)

    def get_device_info(self, scsi_info, rescan):
        # type: (str, bool) -> FiberChannelLunStruct
        s = FiberChannelLunStruct()

        dev_name = os.path.basename(scsi_info.split()[-2])
        wwid = scsi_info.split()[-1]
        if not wwid  or wwid == "-":
            return None

        # rescan disk size
        if rescan:
            linux.write_file("/sys/block/%s/device/rescan" % dev_name, "1")
            logger.debug("rescaned disk %s" % dev_name)

        r, o, e = bash.bash_roe(
            "lsblk --pair -b -p -o NAME,VENDOR,MODEL,WWN,SERIAL,HCTL,TYPE,SIZE /dev/%s" % dev_name, False)
        if r != 0 or o.strip() == "":
            logger.warn("can not get device information from %s" % dev_name)
            return None

        o = o.strip().splitlines()[0]

        def get_data(e):
            return e.split("=")[1].strip().strip('"')

        def get_path(dev):
            return shell.call(
                "udevadm info -n %s | grep 'by-path' | grep -v DEVLINKS | head -n1 | awk -F 'by-path/' '{print $2}'" % dev).strip()

        def get_storage_wwnn(hctl):
            o = shell.call(
                "systool -c fc_transport -A node_name | grep '\"target%s\"' -B2 | awk '/node_name/{print $NF}'" % ":".join(hctl.split(":")[0:3]))
            return o.strip().strip('"')

        for entry in o.split('" '):  # type: str
            if entry.startswith("VENDOR"):
                s.vendor = get_data(entry)
            elif entry.startswith("MODEL"):
                s.model = get_data(entry)
            elif entry.startswith("WWN"):
                s.wwn = get_data(entry)
            elif entry.startswith("SERIAL"):
                s.serial = get_data(entry)
            elif entry.startswith('HCTL'):
                s.hctl = get_data(entry)
            elif entry.startswith('SIZE'):
                s.size = get_data(entry)
            elif entry.startswith('TYPE'):
                s.type = get_data(entry)

        s.wwids = [wwid]
        s.path = get_path(dev_name)
        if lvm.is_slave_of_multipath("/dev/%s" % dev_name):
            s.type = "mpath"
        s.storageWwnn = get_storage_wwnn(s.hctl)
        return s

    @bash.in_bash
    def get_megaraid_devices_storcli(self, smart_scan_result):
        result = []
        r1, vd_info = bash.bash_ro("/opt/MegaRAID/storcli/storcli64 /call/vall show all J")
        r2, pd_info = bash.bash_ro("/opt/MegaRAID/storcli/storcli64 /call/eall/sall show all J")

        if r1 != 0 or r2 != 0:
            return result
        for line in smart_scan_result.splitlines():
            if line.strip() == "":
                continue
            d = self.get_megaraid_device_info_storcli(line, vd_info, pd_info)
            if d.wwn is not None and d.raidControllerSasAddreess is not None:
                result.append(d)

        result.extend(self.get_nvme_device_info(result))
        return result

    @bash.in_bash
    def get_megaraid_device_info_storcli(self, line, vd_info, pd_info):
        # type: (str, str, str) -> RaidPhysicalDriveStruct

        # cannot get disk rotation from storcli
        d = self.get_megaraid_device_disk_info_smartctl(line)

        # get disk raid info
        vd_infos = jsonobject.loads(vd_info.strip())
        for controller in vd_infos["Controllers"]:
            controller_id = controller["Command Status"]["Controller"]
            data = controller["Response Data"]
            for attr in dir(data):
                match = re.match(r"^PDs for VD (\d+)", attr)
                if match:
                    vid = match.group(1)
                    vd_path = "/c%s/v%s" % (controller_id, vid)
                    for pd in data[attr]:
                        if pd["DID"] != d.deviceId:
                            continue
                        d.diskGroup = int(data[vd_path][0]["DG/VD"].split("/")[0])
                        d.raidLevel = data[vd_path][0]["TYPE"].lower()

        # get disk info
        pd_infos = jsonobject.loads(pd_info.strip())
        for controller in pd_infos["Controllers"]:
            controller_id = controller["Command Status"]["Controller"]
            raid_controller_product_name, raid_controller_sas_address = \
                self.get_megaraid_controller_info_storcli(controller_id)
            data = controller["Response Data"]
            for attr in dir(data):
                match = re.match(r"^Drive /c%s/e(\d+)/s(\d+)$" % controller_id, attr)
                if not match:
                    continue
                if d.deviceId != data[attr][0]["DID"]:
                    continue

                enclosure_id = match.group(1)
                slot_id = match.group(2)

                pd_path = "/c%s/e%s/s%s" % (controller_id, enclosure_id, slot_id)
                pd_detailed_info = data["Drive %s - Detailed Information" % pd_path]
                pd_attributes = pd_detailed_info["Drive %s Device attributes" % pd_path]

                drive_type = data[attr][0]["Intf"]
                media_type = data[attr][0]["Med"]
                drive_state = data[attr][0]["State"]
                wwn = pd_attributes["WWN"].lower()
                raw_size = pd_attributes["Raw size"]

                if "TB" in raw_size:
                    size = int(float(raw_size.split(" TB")[0].strip()) * 1024 * 1024 * 1024 * 1024)
                elif "GB" in raw_size:
                    size = int(float(raw_size.split(" GB")[0].strip()) * 1024 * 1024 * 1024)
                elif "MB" in raw_size:
                    size = int(float(raw_size.split(" MB")[0].strip()) * 1024 * 1024)
                else:
                    size = 0

                d.raidControllerNumber = int(controller_id)
                d.enclosureDeviceId = int(enclosure_id)
                d.slotNumber = int(slot_id)
                d.wwn = wwn if d.wwn is None else d.wwn
                d.size = size if d.size == 0 else d.size
                d.driveState = drive_state
                d.driveType = drive_type
                d.mediaType = media_type
                d.raidControllerSasAddreess = raid_controller_sas_address
                d.raidControllerProductName = raid_controller_product_name

        return d

    @bash.in_bash
    def get_arcconf_device(self, adapter_info):
        result = []
        for adapter in adapter_info.splitlines():
            if adapter.strip() == "":
                continue
        
            adapter = adapter.split(":")[0].strip()
            if not adapter.isdigit():
                continue
        
            r, device_info = bash.bash_ro("arcconf getconfig %s AL" % adapter)
            if r != 0 or device_info.strip() == "":
                continue
            
            # Contain at least raid controller into and a hardDisk info
            device_arr = device_info.split("Device #")
            if len(device_arr) < 3:
                continue
            
            productName, sasAddress , raidLevelMap, diskGroupMap = self.get_arcconf_raid_info(device_arr[0])

            for infos in device_arr[1:]:
                d = self.get_arcconf_device_info(infos)
                if d.serialNumber is not None and d.deviceModel is not None and d.enclosureDeviceId is not None and d.slotNumber is not None:
                    d.raidLevel = raidLevelMap.get("%s:%s" % (d.enclosureDeviceId, d.slotNumber))
                    d.diskGroup = diskGroupMap.get("%s:%s" % (d.enclosureDeviceId, d.slotNumber))
                    d.raidControllerNumber = adapter
                    d.raidControllerProductName = productName
                    d.raidControllerSasAddreess = sasAddress
                    result.append(d)

        result.extend(self.get_nvme_device_info(result))
        return result

    @bash.in_bash
    def get_arcconf_device_info(self, infos):
        d = RaidPhysicalDriveStruct()
        
        if not infos.splitlines()[0].strip().isdigit():
            return d
        device_id = int(infos.splitlines()[0].strip())

        serial_number = media_type = drive_type = enclosure_device_id = slot_number = drive_state = device_model = wwn = size = rotation_rate = None
        for l in infos.splitlines()[1:]:
            if l.strip() == "":
                continue
            k = l.split(":")[0].strip().lower()
            v = ":".join(l.split(":")[1:]).strip()
            if "state" in k:
                drive_state = v.split(" ")[0].strip()
            elif "transfer speed" in k:
                drive_type = v.split(" ")[0].strip()
            elif "reported location" in k and "Enclosure" in v and "Slot" in v:
                enclosure_device_id = int(v.split(",")[0].split(" ")[1].strip())
                slot_number = int(v.split("Slot ")[1].split("(")[0].strip())
            elif "model" == k:
                device_model = v
            elif "serial number" in k:
                serial_number = v
            elif "world-wide name" in k:
                wwn = v
            elif "total size" in k:
                if "mb" in v.lower():
                    size = int(v.split(" ")[0].strip()) * 1024 * 1024
                elif "gb" in v.lower():
                    size = int(v.split(" ")[0].strip()) * 1024 * 1024 * 1024
                elif "kb" in v.lower():
                    size = int(v.split(" ")[0].strip()) * 1024
                elif "byte" in v.lower():
                    size = int(v.split(" ")[0].strip())
            elif "ssd" == k:
                media_type = "SSD" if "yes" in v.lower() else "HDD"
            elif "rotational speed" in k:
                rotation_rate = 0 if "solid state device" in v.strip().lower() else int(
                    v.lower().split(" rpm")[0].strip())
        
            if "last failure reason" in k:
                d.deviceId = device_id
                d.driveState = drive_state
                d.driveType = drive_type
                d.enclosureDeviceId = enclosure_device_id
                d.slotNumber = slot_number
                d.deviceModel = device_model
                d.wwn = wwn
                d.size = size
                d.mediaType = media_type
                d.rotationRate = rotation_rate
                d.serialNumber = serial_number
                return d
        
        return d

    @staticmethod
    @bash.in_bash
    def get_arcconf_raid_info(raid_info):
        produce_name = sas_address = None
        raid_levels = {}
        disk_groups = {}

        disk_group = level = None
        for l in raid_info.splitlines():
            if l.strip() == "":
                continue
            k = l.split(":")[0].strip().lower()
            v = ":".join(l.split(":")[1:]).strip()
            if "controller model" == k and produce_name is None:
                produce_name = v
            elif "sas address" == k and sas_address is None:
                sas_address = v
            elif "Logical Device number" in l:
                disk_group = l.strip().split(" ")[-1]
            elif "raid level" == k:
                level = "RAID%s" % v
            elif "Enclosure" in v and "Slot" in v:
                enclosure_id = v.split("Enclosure:")[1].split(",")[0].strip()
                slot_id = v.split("Slot:")[1].split(")")[0].strip()
                locate = "%s:%s" % (enclosure_id, slot_id)
                raid_levels[locate] = level
                disk_groups[locate] = disk_group
    
        return produce_name, sas_address, raid_levels, disk_groups

    @bash.in_bash
    def get_sas_device(self, adapter_info):
        result = []
        for adapter in adapter_info.splitlines():
            if not adapter.strip().isdigit():
                continue
        
            r, device_info = bash.bash_ro("sas3ircu %s display" % adapter.strip())
            if r != 0 or device_info.strip() == "":
                continue

            # Contain at least raid controller into and a hardDisk info
            device_arr = device_info.split("Device is a Hard disk")
            if len(device_arr) < 3:
                continue
            
            productName, sasAddress, raidLevelMap, diskGroupMap = self.get_sas_raid_info(device_arr[0], adapter.strip())

            for infos in device_arr[1:]:
                d = self.get_sas_device_info(infos)
                if d.serialNumber is not None and d.deviceModel is not None and d.enclosureDeviceId is not None and d.slotNumber is not None:
                    d.raidLevel = raidLevelMap.get("%s:%s" % (d.enclosureDeviceId, d.slotNumber))
                    d.diskGroup = diskGroupMap.get("%s:%s" % (d.enclosureDeviceId, d.slotNumber))
                    d.raidControllerNumber = adapter.strip()
                    d.raidControllerProductName = productName
                    d.raidControllerSasAddreess = sasAddress
                    result.append(d)

        result.extend(self.get_nvme_device_info(result))
        return result

    @bash.in_bash
    def get_sas_device_info(self, infos):
        d = RaidPhysicalDriveStruct()
    
        wwn = serial_number = model_number = size = drive_type = enclosure_device_id = slot_number = drive_state = None
        for l in infos.splitlines():
            if l.strip() == "":
                continue
            k = l.split(":")[0].strip().lower()
            v = ":".join(l.split(":")[1:]).strip()
            if "enclosure" in k:
                enclosure_device_id = int(v)
            elif "slot" in k:
                slot_number = int(v)
            elif "state" == k:
                drive_state = v.split(" ")[0].strip()
            elif "size" in k:
                if "mb" in k:
                    size = int(v.split("/")[0].strip()) * 1024 * 1024
                elif "gb" in v.lower():
                    size = int(v.split("/")[0].strip()) * 1024 * 1024 * 1024
                elif "kb" in v.lower():
                    size = int(v.split("/")[0].strip()) * 1024
                elif "byte" in v.lower():
                    size = int(v.split("/")[0].strip())
            elif "model number" == k:
                model_number = v
            elif "serial no" == k:
                serial_number = v
            elif "guid" == k:
                wwn = v
            elif "protocol" == k:
                drive_type = v.strip()
            elif "drive type" == k:
                d.enclosureDeviceId = enclosure_device_id
                d.slotNumber = slot_number
                d.driveState = drive_state
                d.size = size
                d.deviceModel = model_number
                d.serialNumber = serial_number
                d.wwn = wwn
                d.driveType = drive_type
                d.mediaType = "SSD" if "sata_ssd" in v.strip().lower() else "HDD"
                return d
    
        return d

    @staticmethod
    @bash.in_bash
    def get_sas_raid_info(infos, adapter_number):
        produce_name = sas_address = None
        raid_levels = {}
        disk_groups = {}
    
        r, o = bash.bash_ro(
            "/opt/MegaRAID/storcli/storcli64 /c%s show | grep -E 'Product Name|SAS Address'" % adapter_number)
        if r != 0:
            return produce_name, sas_address, raid_levels, disk_groups
    
        produce_name = o.splitlines()[0].split("=")[1].strip()
        sas_address = o.splitlines()[1].split("=")[1].strip()
    
        disk_group = level = None
        for l in infos.splitlines():
            if l.strip() == "":
                continue
            k = l.split(":")[0].strip().lower()
            v = ":".join(l.split(":")[1:]).strip()
            if "volume id" in k:
                disk_group = v
            elif "raid level" in k:
                level = v
            elif "enclosure#/slot#" in k:
                disk_groups[v] = disk_group
                raid_levels[v] = level
    
        return produce_name, sas_address, raid_levels, disk_groups

    @bash.in_bash
    def get_nvme_device_info(self, normal_devices):
        result = []
        
        if not misc.isHyperConvergedHost():
            return result
    
        r, o = bash.bash_ro("nvme list | grep '/dev/' | awk '{print $1}'")
        if r != 0 or o.strip() == "":
            return []
        
        for l in o.splitlines():
            d = RaidPhysicalDriveStruct()
            
            r, wwn_info = bash.bash_ro("udevadm info --name=%s | grep -i 'id_wwn'" % l.strip())
            if r != 0 or wwn_info.strip() == "":
                continue
            d.wwn = wwn_info.strip()[-16:]

            r, device_info = bash.bash_ro("smartctl -i %s" % l.strip())
            if r != 0:
                continue

            for info in device_info.splitlines():
                if info.strip() == "":
                    continue
                k = info.split(":")[0].lower()
                v = ":".join(info.split(":")[1:]).strip()
                
                if "model number" in k:
                    d.deviceModel = v
                elif "serial number" in k:
                    d.serialNumber = v
                elif "total nvm capacity" in k:
                    d.size = int(v.split()[0].strip().replace(",", ""))
            
            if d.wwn is not None and d.deviceModel is not None and d.serialNumber is not None and d.size is not None:
                d.enclosureDeviceId = -1
                d.slotNumber = -1
                d.mediaType = "SSD"
                d.driveType = "NVMe"
                d.raidControllerNumber = normal_devices[0].raidControllerNumber
                d.raidControllerProductName = normal_devices[0].raidControllerProductName
                d.raidControllerSasAddreess = normal_devices[0].raidControllerSasAddreess
                result.append(d)
       
        return result
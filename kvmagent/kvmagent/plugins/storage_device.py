import random
import time
import string
import os.path

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin

from zstacklib.utils import lock
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import lvm
from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import thread
from zstacklib import *

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

        vm = vm_plugin.get_vm_by_uuid(cmd.vmInstanceUuid)
        vm.attach_data_volume(cmd.volume, cmd.addons)
        return jsonobject.dumps(rsp)

    @bash.in_bash
    def get_slave_path(self, multipath_path):
        def get_wwids(dev_name):
            result = []
            wwids = shell.call(
                "udevadm info -n %s | grep 'by-id' | grep -v DEVLINKS | awk -F 'by-id/' '{print $2}'" % dev_name).strip().split()
            wwids.sort()
            for wwid in wwids:
                if "lvm-pv" not in wwid:
                    result.append(wwid)
            if len(result) == 0:
                return wwids

        dm = bash.bash_o("realpath %s | grep -E -o 'dm-.*'" % multipath_path)
        slaves = shell.call("ls -1 /sys/class/block/%s/slaves/" % dm).strip().split("\n")
        if slaves is None or len(slaves) == 0:
            raise "can not find any slave from multpath device: %s" % multipath_path
        return "/dev/disk/by-id/%s" % get_wwids(slaves[0])[0]

    @kvmagent.replyerror
    @bash.in_bash
    def detach_scsi_lun(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        vm = vm_plugin.get_vm_by_uuid(cmd.vmInstanceUuid)
        vm.detach_data_volume(cmd.volume)
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

        @linux.retry(times=20, sleep_time=1)
        def wait_iscsi_mknode(iscsiServerIp, iscsiServerPort, iscsiIqn, e=None):
            disks_by_dev = bash.bash_o("ls /dev/disk/by-path | grep %s:%s | grep %s" % (iscsiServerIp, iscsiServerPort, iscsiIqn)).strip().splitlines()
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
                current_hostname = shell.call('hostname')
                current_hostname = current_hostname.strip(' \t\n\r')
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
                            iqn, cmd.iscsiServerIp, cmd.iscsiServerPort, cmd.iscsiChapUserPassword))                
                r, o, e = bash.bash_roe('iscsiadm --mode node --targetname "%s" -p %s:%s --login' %
                            (iqn, cmd.iscsiServerIp, cmd.iscsiServerPort))
                wait_iscsi_mknode(cmd.iscsiServerIp, cmd.iscsiServerPort, iqn, e)
            finally:
                if bash.bash_r("ls /dev/disk/by-path | grep %s:%s | grep %s" % (cmd.iscsiServerIp, cmd.iscsiServerPort, iqn)) != 0:
                    rsp.iscsiTargetStructList.append(t)
                else:
                    disks = bash.bash_o("ls /dev/disk/by-path | grep %s:%s | grep %s" % (cmd.iscsiServerIp, cmd.iscsiServerPort, iqn)).strip().splitlines()
                    for d in disks:
                        lun_struct = self.get_disk_info_by_path(d.strip())
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
    def get_disk_info_by_path(path):
        # type: (str) -> IscsiLunStruct
        r = bash.bash_r("multipath -l | grep -e '/multipath.conf' | grep -e 'line'")
        if r == 0:
            current_hostname = shell.call('hostname')
            current_hostname = current_hostname.strip(' \t\n\r')
            raise Exception(
                "The multipath.conf setting on host[%s] may be error, please check and try again" % current_hostname)

        abs_path = bash.bash_o("readlink -e /dev/disk/by-path/%s" % path).strip()
        candidate_struct = lvm.get_device_info(abs_path.split("/")[-1])
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
        lun_struct.wwids = candidate_struct.wwids
        if lvm.is_slave_of_multipath(abs_path):
            lun_struct.type = "mpath"
            if kvmagent.get_host_os_type() == "debian":
                mpath_wwid = bash.bash_o("multipath -l %s | head -n1 | awk '{print $1}'" % abs_path).strip()
            else :
                mpath_wwid = bash.bash_o("multipath -l %s | head -n1 | awk '{print $2}'" % abs_path).strip("() \n")
            lun_struct.wwids = [mpath_wwid]
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
        rsp = FcSanScanRsp()
        bash.bash_roe("timeout 120 /usr/bin/rescan-scsi-bus.sh -a")
        rsp.fiberChannelLunStructs = self.get_fc_luns()
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
        drive = self.get_raid_device_info("/dev/bus/%d -d megaraid,%d" % (cmd.busNumber, cmd.deviceNumber), raid_info)
        if drive.wwn != cmd.wwn:
            raise Exception("expect drive[busNumber %s, deviceId %s, slotNumber %s] wwn is %s, but is %s actually" %
                            (cmd.busNumber, cmd.deviceNumber, cmd.slotNumber, cmd.wwn, drive.wwn))

        rsp.smartDataStructs = self.get_smart_data(cmd.busNumber, cmd.deviceNumber)
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

        r, raid_info, e = bash.bash_roe("/opt/MegaRAID/MegaCli/MegaCli64 -LdPdInfo -aALL")
        if r != 0:
            raise Exception("can not execute MegaCli: returnCode: %s, stdout: %s, stderr: %s" % (r, raid_info, e))
        drive = self.get_raid_device_info("/dev/bus/%d -d megaraid,%d" % (cmd.busNumber, cmd.deviceNumber), raid_info)
        if drive.wwn != cmd.wwn:
            raise Exception("expect drive[busNumber %s, deviceId %s, slotNumber %s] wwn is %s, but is %s actually" %
                            (cmd.busNumber, cmd.deviceNumber, cmd.slotNumber, cmd.wwn, drive.wwn))

        command = "start" if cmd.locate is True else "stop"
        bash.bash_errorout("/opt/MegaRAID/MegaCli/MegaCli64 -PdLocate -%s -physdrv[%d:%d] -a%d" % (command, cmd.enclosureDeviceID, cmd.slotNumber, cmd.busNumber))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def drive_self_test(self, req):

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RaidPhysicalDriveSmartTestRsp()

        r, raid_info, e = bash.bash_roe("/opt/MegaRAID/MegaCli/MegaCli64 -LdPdInfo -aALL")
        if r != 0:
            raise Exception("can not execute MegaCli: returnCode: %s, stdout: %s, stderr: %s" % (r, raid_info, e))
        drive = self.get_raid_device_info("/dev/bus/%d -d megaraid,%d" % (cmd.busNumber, cmd.deviceNumber), raid_info)
        if drive.wwn != cmd.wwn:
            raise Exception("expect drive[busNumber %s, deviceId %s, slotNumber %s] wwn is %s, but is %s actually" %
                            (cmd.busNumber, cmd.deviceNumber, cmd.slotNumber, cmd.wwn, drive.wwn))

        rsp.result = self.run_self_test(cmd.busNumber, cmd.deviceNumber, cmd.wwn)
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
        rsp = RaidScanRsp()
        r, o, e = bash.bash_roe("smartctl --scan | grep megaraid")
        if r != 0 or o.strip() == "":
            return jsonobject.dumps(rsp)
        rsp.raidPhysicalDriveStructs = self.get_megaraid_devices(o)
        return jsonobject.dumps(rsp)

    @bash.in_bash
    def get_megaraid_devices(self, smart_scan_result):
        # type: (str) -> list[RaidPhysicalDriveStruct]
        result = []
        r, raid_info = bash.bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -LdPdInfo -aALL")
        if r != 0:
            return result
        for line in smart_scan_result.splitlines():
            if line.strip() == "":
                continue
            d = self.get_raid_device_info(line, raid_info)
            if d.wwn is not None and d.raidControllerSasAddreess is not None:
                result.append(d)
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
    def get_raid_device_info(self, line, raid_info):
        # type: (str, str) -> RaidPhysicalDriveStruct
        line = line.split(" #")[0]
        d = RaidPhysicalDriveStruct()
        r, o = bash.bash_ro("smartctl -i %s " % line)
        if r != 0:
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
            elif "rotation rate" in k:
                d.rotationRate = int(v.split(" rpm")[0].strip())

        in_correct_pd = False
        adapter = raid_level = enclosure_device_id = slot_number = disk_group = None
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
            elif "wwn" in k and v.lower() == d.wwn.lower():
                in_correct_pd = True
                continue

            if in_correct_pd is True and "drive has flagged" in k:
                d.raidLevel = raid_level
                d.enclosureDeviceId = enclosure_device_id
                d.slotNumber = slot_number
                d.diskGroup = disk_group
                d.raidControllerNumber = adapter

                d.raidControllerProductName, d.raidControllerSasAddreess = self.get_raid_controller_info(adapter)
                return d
            if in_correct_pd is False:
                continue

            if "pd type" in k:
                d.driveType = v
            elif "firmware state" in k:
                d.driveState = v
            elif "media type" in k:
                d.mediaType = self.convert_media_type(v)

        return d

    @staticmethod
    @bash.in_bash
    def get_raid_controller_info(adapter_number):
        # type: (str) -> (str, str)
        r, o = bash.bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -AdpAllInfo -a%s | grep -E 'Product Name|SAS Address'" % adapter_number)
        if r != 0:
            return None, None
        return o.splitlines()[0].split(":")[1].strip(), o.splitlines()[1].split(":")[1].strip()

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
    def get_fc_luns(self):
        o = bash.bash_o("ls -1c /sys/bus/scsi/devices/target*/fc_transport | grep ^target | awk -F 'target' '{print $2}'")
        fc_targets = o.strip().splitlines()
        if len(fc_targets) == 0 or (len(fc_targets) == 1 and fc_targets[0] == ""):
            logger.debug("not find any fc targets")
            return []

        o = bash.bash_o("lsscsi | grep '\/dev\/'").strip().splitlines()
        if len(o) == 0 or (len(o) == 1 and o[0] == ""):
            logger.debug("not find any usable fc disks")
            return []

        luns = [None] * len(fc_targets)

        def get_lun_info(fc_target, i):
            t = filter(lambda x: "[%s" % fc_target in x, o)
            mapped_t = map(lambda x: self.get_device_info(x.split("/dev/")[1]), t)
            luns[i] = filter(lambda x: x is not None, mapped_t)

        threads = []
        for idx, fc_target in enumerate(fc_targets, start=0):
            threads.append(thread.ThreadFacade.run_in_thread(get_lun_info, [fc_target, idx]))
        for t in threads:
            t.join()

        luns_info = {}
        for lun_list in luns:
            for lun in lun_list:  # type: FiberChannelLunStruct
                if lun.storageWwnn not in luns_info or len(luns_info[lun.storageWwnn])==0:
                    luns_info[lun.storageWwnn] = []
                    luns_info[lun.storageWwnn].append(lun)
                elif lun.wwids[0] not in map(lambda x:x.wwids[0], luns_info[lun.storageWwnn]):
                    luns_info[lun.storageWwnn].append(lun)

        result = []
        for i in luns_info.values():
            result.extend(i)
        return result

    @kvmagent.replyerror
    @bash.in_bash
    def enable_multipath(self, req):
        rsp = AgentRsp()
        lvm.enable_multipath()

        r = bash.bash_r("grep '^[[:space:]]*alias' /etc/multipath.conf")
        if r == 0:
            bash.bash_roe("sed -i 's/^[[:space:]]*alias/#alias/g' /etc/multipath.conf")
            bash.bash_roe("systemctl reload multipathd")

        linux.set_fail_if_no_path()
        return jsonobject.dumps(rsp)

    def get_device_info(self, dev_name):
        # type: (str) -> FiberChannelLunStruct
        s = FiberChannelLunStruct()
        r, o, e = bash.bash_roe(
            "lsblk --pair -b -p -o NAME,VENDOR,MODEL,WWN,SERIAL,HCTL,TYPE,SIZE /dev/%s" % dev_name, False)
        if r != 0 or o.strip() == "":
            logger.warn("can not get device information from %s" % dev_name)
            return None

        o = o.strip().splitlines()[0]

        def get_data(e):
            return e.split("=")[1].strip().strip('"')

        def get_wwids(dev):
            return shell.call(
                "udevadm info -n %s | grep 'by-id' | grep -v DEVLINKS | awk -F 'by-id/' '{print $2}'" % dev).strip().split()

        def get_path(dev):
            return shell.call(
                "udevadm info -n %s | grep 'by-path' | grep -v DEVLINKS | head -n1 | awk -F 'by-path/' '{print $2}'" % dev).strip()

        def get_storage_wwnn(hctl):
            o = shell.call(
                "systool -c fc_transport -A node_name | grep '\"target%s\"' -B2 | grep node_name | awk '{print $NF}'" % ":".join(hctl.split(":")[0:3]))
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

        s.wwids = get_wwids(dev_name)
        s.wwids.sort()
        s.path = get_path(dev_name)
        if lvm.is_slave_of_multipath("/dev/%s" % dev_name):
            s.type = "mpath"
            if kvmagent.get_host_os_type() == "debian":
                wwid = bash.bash_o("multipath -l /dev/%s | head -n1 | awk '{print $1}'" % dev_name).strip()
            else :
                wwid = bash.bash_o("multipath -l /dev/%s | head -n1 | awk '{print $2}'" % dev_name).strip().strip("()")
            s.wwids = [wwid] if wwid != "" else s.wwids
        s.storageWwnn = get_storage_wwnn(s.hctl)

        return s

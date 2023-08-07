import random
import re
import time
import string
import simplejson
import os.path

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
        self.raidTool = None
        self.raidControllerSasAddress = None
        self.raidControllerProductName = None
        self.raidControllerNumber = None


class RaidLogicalDriveStruct(object):
    def __int__(self):
        self.raidControllerNumber = None
        self.raidLevel = None
        self.wwn = None
        self.size = None
        self.driveState = None
        self.writePolicy = None
        self.id = None
        self.raidControllerSasAddress = None


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
    raidLogicalDriveStructs = None  # type: list[RaidLogicalDriveStruct]

    def __init__(self):
        self.raidPhysicalDriveStructs = []
        self.raidLogicalDriveStructs = []



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


class LocalScsiDriveStruct(object):
    def __int__(self):
        self.name = None
        self.wwn = None
        self.path = None
        self.model = None
        self.mediaType = None
        self.mountPaths = None
        self.serial = None
        self.size = None
        self.vendor = None


class HBAStruct(object):
    def __int__(self):
        self.nodeName = ""
        self.portName = ""
        self.maxSupportedSpeed = -1
        self.speed = -1
        self.manufacturer = ""
        self.model = ""
        self.firmwareVersion = ""
        self.driverVersion = ""


class FiberChannelLunStruct(ScsiLunStruct):
    def __init__(self):
        super(FiberChannelLunStruct, self).__init__()
        self.storageWwnn = ""


class NvmeLunStruct(ScsiLunStruct):
    def __init__(self):
        super(NvmeLunStruct, self).__init__()
        self.nqn = ""
        self.transport = ""

    @staticmethod
    def example(i):
        s = NvmeLunStruct()
        s.vendor = "COMPELNT"
        s.hctl = "15:0:2:" + i
        s.multipathDeviceUuid = ""
        s.nqn = "0x5000d31000e56801"
        s.path = "fc-0x21000024ff326b55-0x5000d31000e56826-lun-" + i
        s.model = "Compellent Vol"
        s.wwn = "0x6000d31000e56800"
        s.type = "mpath"
        s.wwids = ["36000d31000e56800000000000000010" + i]
        s.serial = "6000d31000e56800000000000000010" + i
        s.size = "21990232555520"
        return s


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


class NvmeSanScanRsp(AgentRsp):
    def __init__(self):
        super(NvmeSanScanRsp, self).__init__()
        self.nvmeLunStructs = []


class IscsiLoginCmd(AgentCmd):
    @log.sensitive_fields("iscsiChapUserPassword")
    def __init__(self):
        super(IscsiLoginCmd, self).__init__()
        self.iscsiServerIp = None
        self.iscsiServerPort = None
        self.iscsiChapUserName = None
        self.iscsiChapUserPassword = None
        self.iscsiTargets = []


class HBAScanRsp(AgentRsp):
    def __init__(self):
        super(HBAScanRsp, self).__init__()
        self.hbaStructs = []


class LocalScsiScanRsp(AgentRsp):
    def __init__(self):
        super(LocalScsiScanRsp, self).__init__()
        self.localScsiDriveStructs = []
        self.raidPhysicalDriveStructs = []
        self.raidLogicalDriveStructs = []


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
    NVME_SCAN_PATH = "/storagedevice/nvme/scan"
    MULTIPATH_ENABLE_PATH = "/storagedevice/multipath/enable"
    MULTIPATH_DISABLE_PATH = "/storagedevice/multipath/disable"
    ATTACH_SCSI_LUN_PATH = "/storagedevice/scsilun/attach"
    DETACH_SCSI_LUN_PATH = "/storagedevice/scsilun/detach"
    DETACH_SCSI_DEV_PATH = "/storagedevice/scsilun/detachdev"
    RAID_SCAN_PATH = "/storagedevice/raid/scan"
    RAID_SMART_PATH = "/storagedevice/raid/smart"
    RAID_LOCATE_PATH = "/storagedevice/raid/locate"
    RAID_SELF_TEST_PATH = "/storagedevice/raid/selftest"
    HBA_SCAN_PATH = "/storagedevice/hba/scan"
    LOCAL_SCSI_SCAN_PATH = "/storagedevice/local/scsi/scan"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.ISCSI_LOGIN_PATH, self.iscsi_login, cmd=IscsiLoginCmd())
        http_server.register_async_uri(self.ISCSI_LOGOUT_PATH, self.iscsi_logout, cmd=IscsiLogoutCmd())
        http_server.register_async_uri(self.FC_SCAN_PATH, self.scan_sg_devices)
        http_server.register_async_uri(self.NVME_SCAN_PATH, self.scan_nvme_devices)
        http_server.register_async_uri(self.MULTIPATH_ENABLE_PATH, self.enable_multipath)
        http_server.register_async_uri(self.MULTIPATH_DISABLE_PATH, self.disable_multipath)
        http_server.register_async_uri(self.ATTACH_SCSI_LUN_PATH, self.attach_scsi_lun)
        http_server.register_async_uri(self.DETACH_SCSI_LUN_PATH, self.detach_scsi_lun)
        http_server.register_async_uri(self.DETACH_SCSI_DEV_PATH, self.detach_scsi_dev)
        http_server.register_async_uri(self.RAID_SCAN_PATH, self.raid_scan)
        http_server.register_async_uri(self.RAID_SMART_PATH, self.raid_smart)
        http_server.register_async_uri(self.RAID_LOCATE_PATH, self.raid_locate)
        http_server.register_async_uri(self.RAID_SELF_TEST_PATH, self.drive_self_test)
        http_server.register_async_uri(self.HBA_SCAN_PATH, self.hba_scan)
        http_server.register_async_uri(self.LOCAL_SCSI_SCAN_PATH, self.scan_local_scsi)

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
                r, o = bash.bash_ro("multipath -l -v1 %s" % devpath)
                if r == 0 and o.strip() != "":
                    mpaths.add(o.strip())
            for mpath in mpaths:
                if mpath: shell.run("multipathd resize map "+mpath)

        @linux.retry(times=20, sleep_time=1)
        def wait_iscsi_mknode(iscsiServerIp, iscsiServerPort, iscsiIqn, e=None):
            @linux.retry(times=3, sleep_time=1)
            def get_disks_by_no_mapping_lun():
                # Use HCTL, IQN, "-" to match the number of unmounted Luns according to lsscsi --transport
                disks_by_no_mapping_lun = bash.bash_o(
                    "lsscsi --transport | grep -w %s | awk '{print $1,$NF}' | grep -E '\<%s\>:[[:digit:]]*:[[:digit:]]*:"
                    "[[:digit:]]*' | awk '{print $NF}' | grep -x '-'" % (
                        iscsiIqn, host_Number)).strip().splitlines()
                if len(disks_by_no_mapping_lun) > 0 and lsscsi_retry_counter[0] != 2:
                    lsscsi_retry_counter[0] += 1
                    raise RetryException("found invalid device name, retrieve again")
                return disks_by_no_mapping_lun

            lsscsi_retry_counter = [0]
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
            disks_by_no_mapping_lun = get_disks_by_no_mapping_lun()
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

        login_failed = 0
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
            except Exception:
                login_failed = login_failed + 1
                if login_failed == len(iqns):
                    raise
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
        # type: (str, dict[str, str]) -> IscsiLunStruct
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
        lun_struct.type = 'mpath' if lvm.is_slave_of_multipath(abs_path) else candidate_struct.type
        lun_struct.wwn = candidate_struct.wwn
        lun_struct.wwids = [candidate_struct.wwid]
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
    def scan_nvme_devices(self, req):
        # 1. find nvme devices
        # 2. distinct by device wwid and nqn
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = NvmeSanScanRsp()
        rsp.nvmeLunStructs = self.get_nvme_luns(cmd.rescan)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def raid_smart(self, req):
        # don't use megacli!
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

        if cmd.raidTool == "STORCLI":
            self.mega_raid_locate_storcli(cmd)
        elif cmd.raidTool == "ARCCONF":
            self.arcconf_raid_locate(cmd)
        elif cmd.raidTool == "SAS3IRCU":
            self.sas_raid_locate(cmd)
        else:
            raise Exception("Unsupported raid command %s" % cmd.raidTool)
        return jsonobject.dumps(rsp)

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
        # don't use megacli!
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
    def mega_raid_locate_storcli(self, cmd):
        # when disk status is abnormal, this command will return no 0.
        _, pd_info, e = bash.bash_roe("/opt/MegaRAID/storcli/storcli64 /call/eall/sall show all J")
        if jsonobject.loads(pd_info)['Controllers'][0]['Command Status']['Status'] != "Success":
            raise Exception("Failed to get raid pd info, stderr: %s" % e)

        bus_number = self.get_bus_number()
        drive = self.get_megaraid_physical_drive_info_storcli("/dev/bus/%d -d megaraid,%d"
                                                                 % (bus_number, cmd.deviceNumber), None, pd_info)
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
        # don't use megacli!
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

    @staticmethod
    def convert_raid_state(state):
        """
        :type state: str
        """
        state = state.lower().strip()
        if "optimal" in state or "optl" == state or "okay" in state:
            return "online"
        # dgrd and pdgd
        elif "degraded" in state or "dgrd" == state or "pdgd" == state or "interim recovery" in state:
            return "degraded"
        elif "ready for recovery" in state or "rebuilding" in state or "rec" == state:
            return "rebuild"
        else:
            return "unknown"

    @staticmethod
    def convert_disk_state(state):
        """
        :type state: str
        """
        state = state.lower().strip()
        if "online" in state or "jbod" in state or "ready" in state or "optimal" in state or "hot-spare" in state \
                or "hot spare" in state or "raw" in state or "onln" == state or "ghs" == state or "dhs" == state \
                or "ugood" == state:
            return "online"
        elif "rebuild" in state or "rbld" == state:
            return "rebuild"
        elif "failed" in state or "offline" in state or "missing" in state or "offln" == state:
            return "offline"
        else:
            return "unknown"

    @kvmagent.replyerror
    def raid_scan(self, req):
        # 1. find raid device
        # 2. get each device info

        rsp = RaidScanRsp()
        raid_physical_drive_lists, raid_logic_drive_lists = self.get_raid_devices()

        rsp.raidPhysicalDriveStructs = raid_physical_drive_lists
        rsp.raidLogicalDriveStructs = raid_logic_drive_lists
        return jsonobject.dumps(rsp)

    @bash.in_bash
    def get_raid_devices(self):
        raid_physical_drive_lists = []
        raid_logic_drive_lists = []

        pds, vds = self.get_megaraid_devices_storcli()
        raid_physical_drive_lists.extend(pds)
        raid_logic_drive_lists.extend(vds)

        pds, vds = self.get_arcconf_devices()
        raid_physical_drive_lists.extend(pds)
        raid_logic_drive_lists.extend(vds)

        pds, vds = self.get_sas_devices()
        raid_physical_drive_lists.extend(pds)
        raid_logic_drive_lists.extend(vds)

        return raid_physical_drive_lists, raid_logic_drive_lists

    @bash.in_bash
    def get_megaraid_devices_megacli(self, smart_scan_result):
        # type: (str) -> list[RaidPhysicalDriveStruct]
        # don't use megacli!
        result = []
        r1, raid_info = bash.bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -LdPdInfo -aALL")
        r2, device_info = bash.bash_ro("/opt/MegaRAID/MegaCli/MegaCli64 -PDList -aAll")
        if r1 != 0 or r2 != 0:
            return result
        for line in smart_scan_result.splitlines():
            if line.strip() == "":
                continue
            d = self.get_megaraid_device_info_megacli(line, raid_info)
            if d.wwn is None or d.raidControllerSasAddress is None:
                d = self.get_megaraid_device_info_megacli(line, device_info)
            if d.wwn is not None and d.raidControllerSasAddress is not None:
                result.append(d)

        if misc.isMiniHost():
            result.extend(self.get_missing(result))
        return result

    @bash.in_bash
    def get_missing(self, normal_devices):
        # type: (list[RaidPhysicalDriveStruct]) -> list[RaidPhysicalDriveStruct]
        # don't use megacli!
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
                d.raidControllerSasAddreess = normal_devices[0].raidControllerSasAddress
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
                wwn = v.upper()
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
                d.serialNumber = v.upper()
            elif "lu wwn device id" in k:
                d.wwn = v.replace(" ", "").upper()
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

    @staticmethod
    def convert_raid_write_policy(origin):
        # type: (str) -> str
        origin = origin.lower()
        if origin in ["writethrough", "disable"]:
            return "WT"
        elif origin in ["writeback", "enable"]:
            return "WB"
        return origin

    @staticmethod
    def convert_size_in_bytes(origin):
        origin.replace(" ", "").upper()
        if "T" in origin:
            return int(float(origin.split("T")[0].strip()) * 1024 * 1024 * 1024 * 1024)
        elif "G" in origin:
            return int(float(origin.split("G")[0].strip()) * 1024 * 1024 * 1024)
        elif "M" in origin:
            return int(float(origin.split("M")[0].strip()) * 1024 * 1024)
        else:
            return 0

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
                device_info = self.get_fc_device_info(target_scsi_info, rescan)
                if device_info:
                    luns[i].append(device_info)

        threads = []
        for idx, fc_target in enumerate(fc_targets, start=0):
            threads.append(thread.ThreadFacade.run_in_thread(fill_lun_info, [fc_target, idx]))
        for t in threads:
            t.join()

        return sum(filter(None, luns), [])

    def multipath_conf_cannot_change(self):
        r, o, e = bash.bash_roe('''grep -rF "<disk type='block' device='lun'" /var/run/libvirt/qemu/* ''')
        return r == 0

    @kvmagent.replyerror
    @bash.in_bash
    def enable_multipath(self, req):
        rsp = AgentRsp()
        cmd_dict = simplejson.loads(req[http.REQUEST_BODY])

        if self.multipath_conf_cannot_change():
            rsp.error = "there are VM using lun as disk, cannot change multipath config"
            rsp.success = False
            return jsonobject.dumps(rsp)

        lvm.enable_multipath()

        r = bash.bash_r("grep '^[[:space:]]*alias' /etc/multipath.conf")
        if r == 0:
            bash.bash_roe("sed -i 's/^[[:space:]]*alias/#alias/g' /etc/multipath.conf")
            bash.bash_roe("systemctl reload multipathd")

        if multipath.write_multipath_conf("/etc/multipath.conf", cmd_dict.get("blacklist", None)):
            bash.bash_roe("systemctl reload multipathd")

        linux.set_fail_if_no_path()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def disable_multipath(self, req):
        rsp = AgentRsp()
        lvm.disable_multipath()
        return jsonobject.dumps(rsp)

    @staticmethod
    def get_fc_device_info(scsi_info, rescan):
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

        def get_storage_wwnn(hctl):
            o = shell.call(
                "systool -c fc_transport -A node_name | grep '\"target%s\"' -B2 | awk '/node_name/{print $NF}'" % ":".join(hctl.split(":")[0:3]))
            return o.strip().strip('"')

        blk_info = lvm.lsblk_info(dev_name)
        if not blk_info:
            return None

        s.vendor = blk_info.vendor
        s.model = blk_info.model
        s.wwn = blk_info.wwn
        s.serial = blk_info.serial
        s.hctl = blk_info.hctl
        s.size = blk_info.size
        s.type = 'mpath' if lvm.is_slave_of_multipath("/dev/%s" % dev_name) else blk_info.type
        s.wwids = [wwid]
        s.path = lvm.get_device_path(dev_name)
        s.storageWwnn = get_storage_wwnn(s.hctl)
        return s

    @bash.in_bash
    def get_nvme_luns(self, rescan):
        # type: (bool) -> list[NvmeLunStruct]
        ret = []

        o = bash.bash_errorout("nvme list -o json")
        if not o:
            return []

        nvme_luns = jsonobject.loads(o).Devices
        nvme_subsystems = os.listdir("/sys/class/nvme-subsystem/")

        def get_nqn():
            nqn = linux.read_file("/sys/class/block/%s/device/subsysnqn" % dev_name)
            if nqn:
                return nqn.strip()

            for target in nvme_subsystems:
                nqn = linux.read_file("/sys/class/nvme-subsystem/%s/subsysnqn" % target)
                if nqn and any(os.path.basename(fpath) == dev_name for fpath in
                               linux.walk("/sys/class/nvme-subsystem/%s" % target, depth=2)):
                    return nqn.strip()

        for lun in nvme_luns:
            s = NvmeLunStruct()
            dev_name = os.path.basename(lun.DevicePath)
            blk_info = lvm.lsblk_info(dev_name)
            s.vendor = blk_info.vendor
            s.model = blk_info.model
            s.wwn = blk_info.wwn
            s.serial = blk_info.serial
            s.hctl = blk_info.hctl
            s.size = blk_info.size
            s.type = 'mpath' if lvm.is_slave_of_multipath(lun.DevicePath) else blk_info.type
            s.wwids = [s.wwn]
            path = lvm.get_device_path(lun.DevicePath)
            s.path = path if path else s.wwn
            s.nqn = get_nqn()

            ret.append(s)
        return ret

    @bash.in_bash
    def get_megaraid_devices_storcli(self):
        pd_lists = vd_lists = []
        r, o, e = bash.bash_roe("smartctl --scan | grep megaraid")
        if r != 0 or o.strip() == "":
            return pd_lists, vd_lists

        r1, vd_info = bash.bash_ro("/opt/MegaRAID/storcli/storcli64 /call/vall show all J")
        if r1 != 0 or jsonobject.loads(vd_info)['Controllers'][0]['Command Status']['Status'] != "Success":
            return pd_lists, vd_lists

        # when a RAID-built disk is pulled out, this cmd's return code is 45.
        r2, pd_info = bash.bash_ro("/opt/MegaRAID/storcli/storcli64 /call/eall/sall show all J")
        if jsonobject.loads(pd_info)['Controllers'][0]['Command Status']['Status'] != "Success":
            return pd_lists, vd_lists

        for line in o.splitlines():
            if line.strip() == "":
                continue
            d = self.get_megaraid_physical_drive_info_storcli(line, vd_info, pd_info)
            if d.wwn is not None and d.raidControllerSasAddress is not None:
                pd_lists.append(d)

        vd_lists = self.get_megaraid_logical_drive_info_storcli(vd_info)

        return pd_lists, vd_lists

    @bash.in_bash
    def get_megaraid_physical_drive_info_storcli(self, line, vd_info, pd_info):
        # type: (str, any, str) -> RaidPhysicalDriveStruct

        # cannot get disk rotation from storcli
        d = self.get_megaraid_device_disk_info_smartctl(line)

        def get_logic_disk_related_info(d_):
            if vd_info is None:
                return
            vd_infos = jsonobject.loads(vd_info.strip())
            for controller_ in vd_infos["Controllers"]:
                controller_id_ = controller_["Command Status"]["Controller"]

                data_ = controller["Response Data"]
                for attr_ in dir(data):
                    match_ = re.match(r"^PDs for VD (\d+)", attr)
                    if not match_:
                        continue
                    vid = match_.group(1)
                    vd_path = "/c%s/v%s" % (controller_id_, vid)
                    raid_level = data_[vd_path][0]["TYPE"]
                    for pd in data_[attr_]:
                        if pd["DID"] != d_.deviceId:
                            continue
                        d_.diskGroup = int(data[vd_path][0]["DG/VD"].split("/")[0])
                        d_.raidLevel = raid_level

        # get raid logic disk info
        get_logic_disk_related_info(d)

        # get disk info
        pd_infos = jsonobject.loads(pd_info.strip())
        for controller in pd_infos["Controllers"]:
            controller_id = controller["Command Status"]["Controller"]
            raid_controller_product_name, raid_controller_sas_address = self.get_megaraid_controller_info_storcli(controller_id)
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
                drive_state = self.convert_disk_state(data[attr][0]["State"])
                wwn = pd_attributes["WWN"].upper()
                raw_size = pd_attributes["Raw size"]
                size = self.convert_size_in_bytes(raw_size)

                d.raidControllerNumber = int(controller_id)
                d.enclosureDeviceId = int(enclosure_id)
                d.slotNumber = int(slot_id)
                d.wwn = wwn if d.wwn is None else d.wwn
                d.size = size if d.size == 0 else d.size
                d.driveState = drive_state
                d.driveType = drive_type
                d.mediaType = media_type
                d.raidTool = "STORCLI"
                d.raidControllerSasAddreess = raid_controller_sas_address
                d.raidControllerProductName = raid_controller_product_name

        return d

    @bash.in_bash
    def get_megaraid_logical_drive_info_storcli(self, vd_info):
        logical_drive_list = []
        vd_infos = jsonobject.loads(vd_info.strip())
        for controller in vd_infos["Controllers"]:
            controller_id = controller["Command Status"]["Controller"]
            _, raid_controller_sas_address = self.get_megaraid_controller_info_storcli(controller_id)
            data = controller["Response Data"]
            for attr in dir(data):
                match = re.match(r"^PDs for VD (\d+)", attr)
                if not match:
                    continue
                vid = match.group(1)
                vd_path = "/c%s/v%s" % (controller_id, vid)
                vd_properties = data["VD%s Properties" % vid]

                v = RaidLogicalDriveStruct()
                v.id = int(data[vd_path][0]["DG/VD"].split("/")[0])
                v.size = self.convert_size_in_bytes(vd_properties["Size"])
                v.driveState = self.convert_raid_state(data[vd_path][0]["State"])
                v.raidLevel = data[vd_path][0]["TYPE"]
                v.raidControllerSasAddress = raid_controller_sas_address
                v.raidControllerNumber = controller_id
                v.writePolicy = self.convert_raid_write_policy(vd_properties["Write Cache(initial setting)"])
                v.wwn = vd_properties["SCSI NAA Id"].upper()
                logical_drive_list.append(v)
        return logical_drive_list

    @bash.in_bash
    def get_arcconf_devices(self):
        pd_list = vd_lists = []
        r, o, e = bash.bash_roe("arcconf list | grep -A 8 'Controller ID' | awk '{print $2}'")
        if r != 0 or o.strip() == "":
            return pd_list, vd_lists
        for adapter in o.splitlines():
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
            vd_lists = self.get_arcconf_logical_drive_info(device_info, adapter)
            raid_produce_name, raid_sas_address, raid_level_map, disk_group_map = \
                self.get_arcconf_raid_info(device_arr[0])

            for v in vd_lists:
                v.raidControllerSasAddress = raid_sas_address

            for infos in device_arr[1:]:
                d = self.get_arcconf_physical_drive_info(infos)
                if d.serialNumber is not None and d.deviceModel is not None and d.enclosureDeviceId is not None and d.slotNumber is not None:
                    d.raidLevel = raid_level_map.get("%s:%s" % (d.enclosureDeviceId, d.slotNumber))
                    d.diskGroup = disk_group_map.get("%s:%s" % (d.enclosureDeviceId, d.slotNumber))
                    d.raidControllerNumber = adapter
                    d.raidControllerProductName = raid_produce_name
                    d.raidControllerSasAddress = raid_sas_address
                    pd_list.append(d)

        return pd_list, vd_lists

    @bash.in_bash
    def get_arcconf_physical_drive_info(self, infos):
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
                drive_state = self.convert_disk_state(v.split(" ")[0].strip())
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
                d.wwn = wwn.upper()
                d.size = size
                d.mediaType = media_type
                d.rotationRate = rotation_rate
                d.serialNumber = serial_number.upper()
                d.raidTool = "ARCCONF"
                return d

        return d

    @bash.in_bash
    def get_arcconf_logical_drive_info(self, infos, adapter):
        res = []
        logical_pattern = r"Logical device information(.*?)(?=Array Physical Device Information|$)"
        logical_match = re.search(logical_pattern, infos, re.S)
        logical_info = logical_match.group(1).strip() if logical_match else ""
        if logical_info == "":
            return res
        logical_device_pattern = r"Logical Device number (\d+)(.*?)(?=Logical Device number|$)"
        logical_device_matches = re.findall(logical_device_pattern, logical_info, re.S)
        var_pattern = r"(.*?)(?:\s*:\s*)(.*?)(?=\n|$)"

        # # only get the first port sas address of the raid controller
        # pattern = r"Connector information.*?SAS Address\s*:\s*(.*?)\n"
        # sas_address_match = re.search(pattern, infos, re.S)
        # raid_controller_sas_address = sas_address_match.group(1).strip() if sas_address_match else None

        for logical_device_match in logical_device_matches:
            logical_id = logical_device_match[0]
            logical_device_info = logical_device_match[1].strip()
            variables = {key.strip(): value.strip() for key, value in re.findall(var_pattern, logical_device_info, re.S)}
            v = RaidLogicalDriveStruct()
            v.raidControllerNumber = adapter
            v.raidLevel = "RAID%s" % variables["RAID level"]
            v.driveState = self.convert_raid_state(variables["Status of Logical Device"])
            v.size = self.convert_size_in_bytes(variables["Size"])
            v.wwn = variables["Volume Unique Identifier"].upper()
            v.id = int(logical_id)
            v.writePolicy = self.convert_raid_write_policy(variables["Caching"])
            # v.raidControllerSasAddress = raid_controller_sas_address
            res.append(v)
        return res

    @staticmethod
    @bash.in_bash
    def get_arcconf_raid_info(raid_info):
        produce_name = sas_address = None
        raid_levels = {}
        disk_groups = {}

        # only read connector 0's sas address
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
    def get_sas_devices(self):
        pd_lists = vd_lists = []
        r, o, e = bash.bash_roe("sas3ircu list | grep -A 8 'Index' | awk '{print $1}'")
        if r != 0 or o.strip() == "":
            return pd_lists, vd_lists
        for adapter in o.splitlines():
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
            vd_lists = self.get_sas_logical_drive_info(device_arr[0], adapter.strip())
            for v in vd_lists:
                v.raidControllerSasAddress = sasAddress

            for infos in device_arr[1:]:
                d = self.get_sas_physical_drive_info(infos)
                if d.serialNumber is not None and d.deviceModel is not None and d.enclosureDeviceId is not None and d.slotNumber is not None:
                    d.raidLevel = raidLevelMap.get("%s:%s" % (d.enclosureDeviceId, d.slotNumber))
                    d.diskGroup = diskGroupMap.get("%s:%s" % (d.enclosureDeviceId, d.slotNumber))
                    d.raidControllerNumber = adapter.strip()
                    d.raidControllerProductName = productName
                    d.raidControllerSasAddreess = sasAddress
                    pd_lists.append(d)

        return pd_lists, vd_lists

    @bash.in_bash
    def get_sas_physical_drive_info(self, infos):
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
                drive_state = self.convert_disk_state(v.split(" ")[0].strip())
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
                d.serialNumber = serial_number.upper()
                d.wwn = wwn.upper()
                d.driveType = drive_type
                d.mediaType = "SSD" if "sata_ssd" in v.strip().lower() else "HDD"
                return d

        return d

    @bash.in_bash
    def get_sas_logical_drive_info(self, infos, adapter):
        def get_logical_drive_status():
            r, o = bash.bash_ro("sas3ircu %s status" % adapter)
            if r != 0:
                return None
            logical_state_pattern = r"IR volume (\d+).*?Volume state(?:\s*:\s*)(.*?)(?=\n|$)"
            return {key.strip(): value.strip() for key, value in re.findall(logical_state_pattern, o, re.S)}

        res = []
        logical_pattern = r"IR Volume information(.*?)(?=Physical device information|$)"
        logical_match = re.search(logical_pattern, infos, re.S)
        logical_info = logical_match.group(1).strip() if logical_match else ""
        if logical_info == "":
            return res
        logical_device_pattern = r"IR volume (\d+)(.*?)(?=IR volume|$)"
        logical_device_matches = re.findall(logical_device_pattern, logical_info, re.S)
        var_pattern = r"(.*?)(?:\s*:\s*)(.*?)(?=\n|$)"

        logical_states = get_logical_drive_status()

        for logical_device_match in logical_device_matches:
            logical_id = logical_device_match[0]
            logical_device_info = logical_device_match[1].strip()
            variables = {key.strip(): value.strip() for key, value in re.findall(var_pattern, logical_device_info, re.S)}
            v = RaidLogicalDriveStruct()
            v.id = int(logical_id)
            v.raidControllerNumber = adapter
            v.raidLevel = variables["RAID level"]
            state = "unknown" if logical_states is None or logical_id not in logical_states.keys() \
                else logical_states[logical_id]
            v.driveState = self.convert_raid_state(state)
            v.size = self.convert_size_in_bytes(variables["Size (in MB)"])
            v.wwn = variables["Volume wwid"].upper()

            res.append(v)
        return res

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

    @kvmagent.replyerror
    @bash.in_bash
    def hba_scan(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = HBAScanRsp()
        rsp.hbaStructs = self.get_hba_devices()
        return jsonobject.dumps(rsp)

    @bash.in_bash
    def get_hba_devices(self):
        def get_speed_number(speed):
            digits = re.findall(r'\d+', speed)
            if digits:
                return int(digits[0])
            return 0

        def get_hba_max_supported_speed(speeds):
            max_speed_number = -1
            max_speed = ""
            for speed in speeds.split(","):
                speed_number = get_speed_number(speed)
                if speed_number > max_speed_number:
                    max_speed_number = speed_number
                    max_speed = speed
            return max_speed

        def decode_symbolic_name(symbolic_name):
            manufacturer = ""
            model = ""
            firm_version = ""
            driver_version = ""

            values = symbolic_name.strip().split(" ")
            if symbolic_name.lower().startswith("qle"):
                # QLE2562 FW:v8.07.00 DVR:v10.02.00.106-k
                manufacturer = "Qlogic"
                model = values[0]
                firm_version = values[1][3:]
                driver_version = values[2][4:]
            elif symbolic_name.lower().startswith("emulex"):
                # Emulex LPe16002B-M6 FV12.2.299.27 DV12.8.0.10 HN:172-25-200-214 OS:Linux
                manufacturer = "Emulex"
                model = values[1]
                firm_version = values[2][2:]
                driver_version = values[3][2:]

            return manufacturer, model, firm_version, driver_version
        ret = []
        r, o, e = bash.bash_roe("systool -c fc_host -v")
        if r != 0:
            return ret

        h = HBAStruct()
        node_name_ = port_name_ = speed_ = max_supported_speed_ = manufacturer_ = model_ = firmware_version_ = driver_version_ = None
        for line in o.strip().split("\n"):
            infos = line.split("=")
            k = infos[0].lower().strip()
            v = "=".join(infos[1:]).strip().strip('"')
            if k == "node_name":
                node_name_ = v[2:]
            if k == "port_name":
                port_name_ = v[2:]
            if k == "speed":
                speed_ = v
            if k == "supported_speeds":
                max_supported_speed_ = get_hba_max_supported_speed(v)
            if k == "symbolic_name":
                manufacturer_, model_, firmware_version_, driver_version_ = decode_symbolic_name(v)
            if k == "device path":
                h.nodeName = node_name_
                h.portName = port_name_
                h.speed = speed_
                h.maxSupportedSpeed = max_supported_speed_
                h.manufacturer = manufacturer_
                h.firmwareVersion = firmware_version_
                h.driverVersion = driver_version_
                h.model = model_
                ret.append(h)
                h = HBAStruct()
        return ret

    @kvmagent.replyerror
    @bash.in_bash
    def scan_local_scsi(self, req):
        # only scan local scsi disks
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = LocalScsiScanRsp()
        rsp.localScsiDriveStructs = self.get_local_scsi_devices()
        rsp.raidPhysicalDriveStructs, rsp.raidLogicalDriveStructs = self.get_raid_devices()
        return jsonobject.dumps(rsp)

    @bash.in_bash
    def get_local_scsi_devices(self):
        # type: (str) -> list[LocalScsiDriveStruct]
        # raid logical disk will be collected

        devices = []
        cmd = "lsblk -P -p -o name,size,wwn,tran,model,serial,rota,vendor,mountpoint,type,pkname"
        r1, devices_info = bash.bash_ro(cmd)

        scsi_infos = lvm.run_lsscsi_i()
        if r1 != 0:
            return devices

        pattern = r'(\w+)="([^"]*)"'

        def get_mount_paths(path):
            mount_paths = []
            for device_ in devices_info.splitlines():
                matches_ = re.findall(pattern, device_)
                variables_ = {key.strip(): value.strip() for key, value in matches_}
                if path not in variables_["PKNAME"]:
                    continue
                if variables_["MOUNTPOINT"] == "":
                    continue
                mount_paths.append(variables_["MOUNTPOINT"])
            return mount_paths

        for device in devices_info.splitlines():
            matches = re.findall(pattern, device)
            variables = {key.strip(): value.strip() for key, value in matches}
            if variables["TYPE"] != "disk":
                continue
            if variables["PKNAME"] != "":
                continue
            if not any(variables["NAME"] in a for a in scsi_infos):
                continue
            tran = variables["TRAN"].lower()
            if tran == "fc" or tran == "iscsi" or tran == "usb":
                continue
            d = LocalScsiDriveStruct()
            d.name = variables["NAME"].split("/dev/")[1]
            d.path = variables["NAME"]
            # wwn: 0x5000c500c85f2899
            d.wwn = variables["WWN"] if len(variables["WWN"]) <= 2 else variables["WWN"][2:].upper()
            d.size = self.convert_size_in_bytes(variables["SIZE"])
            d.serial = variables["SERIAL"]
            d.model = variables["MODEL"]
            d.mediaType = "HDD" if int(variables["ROTA"]) == 0 else "SSD"
            d.vendor = variables["VENDOR"]
            d.mountPaths = get_mount_paths(d.path)
            devices.append(d)

        return devices


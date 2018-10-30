import random

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

logger = log.get_logger(__name__)


class RetryException(Exception):
    pass


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


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
    iscsiLunStructList = None  # type: List[IscsiLunStruct]

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


class IscsiLoginRsp(AgentRsp):
    iscsiTargetStructList = None  # type: List[IscsiTargetStruct]

    def __init__(self):
        self.iscsiTargetStructList = []


class StorageDevicePlugin(kvmagent.KvmAgent):

    ISCSI_LOGIN_PATH = "/storagedevice/iscsi/login"
    ISCSI_LOGOUT_PATH = "/storagedevice/iscsi/logout"
    FC_SCAN_PATH = "/storage/fc/scan"
    MULTIPATH_ENABLE_PATH = "/storage/multipath/enable"
    ATTACH_SCSI_LUN_PATH = "/storage/scsilun/attach"
    DETACH_SCSI_LUN_PATH = "/storage/scsilun/detach"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.ISCSI_LOGIN_PATH, self.iscsi_login)
        http_server.register_async_uri(self.ISCSI_LOGOUT_PATH, self.iscsi_logout)
        http_server.register_async_uri(self.FC_SCAN_PATH, self.scan_sg_devices)
        http_server.register_async_uri(self.MULTIPATH_ENABLE_PATH, self.enable_multipath)
        http_server.register_async_uri(self.ATTACH_SCSI_LUN_PATH, self.attach_scsi_lun)
        http_server.register_async_uri(self.DETACH_SCSI_LUN_PATH, self.detach_scsi_lun)

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
            return [i.strip().split(" ")[-1] for i in o.splitlines()]

        @linux.retry(times=5, sleep_time=random.uniform(0.1, 3))
        def wait_iscsi_mknode(iscsiServerIp, iscsiServerPort, iscsiIqn, e = None):
            disks_by_dev = bash.bash_o("ls /dev/disk/by-path | grep %s:%s | grep %s" % (iscsiServerIp, iscsiServerPort, iscsiIqn)).strip().splitlines()
            sid = bash.bash_o("iscsiadm -m session | grep %s:%s | grep %s | awk '{print $2}'" % (iscsiServerIp, iscsiServerPort, iscsiIqn)).strip("[]\n ")
            if sid == "" or sid is None:
                err = "sid not found, this may because chap authentication failed"
                if e != None and e != "":
                    err += " ,error: %s" % e
                raise RetryException(e)
            disks_by_iscsi = bash.bash_o("iscsiadm -m session -P 3 --sid=%s | grep Lun" % sid).strip().splitlines()
            if len(disks_by_dev) != len(disks_by_iscsi):
                raise RetryException("disks number by /dev/disk not equal to iscsiadm")

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
                        t.iscsiLunStructList.append(self.get_disk_info_by_path(d.strip()))
                    rsp.iscsiTargetStructList.append(t)

        return jsonobject.dumps(rsp)

    @staticmethod
    def get_disk_info_by_path(path):
        # type: (str) -> IscsiLunStruct
        abs_path = bash.bash_o("readlink -e /dev/disk/by-path/%s" % path).strip()
        candidate_struct = lvm.get_device_info(abs_path.split("/")[-1])
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
            shell.call('timeout 10 iscsiadm --mode node --targetname "%s" -p %s:%s --logout' % (
                iqn, cmd.iscsiServerIp, cmd.iscsiServerPort))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def scan_sg_devices(self, req):
        #1. find fc devices
        #2. distinct by device wwid and storage wwn
        rsp = FcSanScanRsp()
        bash.bash_roe("/usr/bin/rescan-scsi-bus.sh")
        rsp.fiberChannelLunStructs = self.get_fc_luns()
        return jsonobject.dumps(rsp)

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

        luns = []
        for fc_target in fc_targets:
            t = filter(lambda x: "[%s" % fc_target in x, o)
            luns.extend(map(lambda x: self.get_device_info(x.split("/dev/")[1]), t))

        luns_info = {}
        for lun in luns:  # type: FiberChannelLunStruct
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
        return jsonobject.dumps(rsp)

    def get_device_info(self, dev_name):
        # type: (str) -> FiberChannelLunStruct
        s = FiberChannelLunStruct()
        o = shell.call(
            "lsblk --pair -b -p -o NAME,VENDOR,MODEL,WWN,SERIAL,HCTL,TYPE,SIZE /dev/%s" % dev_name).strip().split("\n")[0]
        if o == "":
            raise Exception("can not get device information from %s" % dev_name)

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
                "systool -c fc_transport -A node_name | grep 'target%s' -B2 | grep node_name | awk '{print $NF}'" % ":".join(hctl.split(":")[0:3]))
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
            wwid = bash.bash_o("multipath -l /dev/%s | head -n1 | awk '{print $2}'" % dev_name).strip().strip("()")
            s.wwids = [wwid] if wwid != "" else s.wwids
        s.storageWwnn = get_storage_wwnn(s.hctl)

        return s

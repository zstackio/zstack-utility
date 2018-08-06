from kvmagent import kvmagent

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


class IscsiTargetStruct(object):
    iscsiLunStructList = None  # type: List[IscsiLunStruct]

    def __init__(self):
        self.iqn = ""
        self.iscsiLunStructList = []


class IscsiLunStruct(object):
    def __init__(self):
        self.wwids = []
        self.vendor = ""
        self.model = ""
        self.wwn = ""
        self.serial = ""
        self.hctl = ""
        self.type = ""
        self.path = ""
        self.size = ""
        self.multipathDeviceUuid = ""


class IscsiLoginRsp(AgentRsp):
    iscsiTargetStructList = None  # type: List[IscsiTargetStruct]

    def __init__(self):
        self.iscsiTargetStructList = []


class StorageDevicePlugin(kvmagent.KvmAgent):

    ISCSI_LOGIN_PATH = "/storagedevice/iscsi/login"
    ISCSI_LOGOUT_PATH = "/storagedevice/iscsi/logout"
    FC_SCAN_PATH = "/storage/fc/scan"
    MULTIPATH_ENABLE_PATH = "/storage/multipath/enable"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.ISCSI_LOGIN_PATH, self.iscsi_login)
        http_server.register_async_uri(self.ISCSI_LOGOUT_PATH, self.iscsi_logout)
        http_server.register_async_uri(self.FC_SCAN_PATH, self.scan_sg_devices)
        http_server.register_async_uri(self.MULTIPATH_ENABLE_PATH, self.enable_multipath)

    def stop(self):
        pass

    @lock.lock('iscsiadm')
    @kvmagent.replyerror
    @bash.in_bash
    def iscsi_login(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = IscsiLoginRsp()

        iqns = cmd.iscsiTargets
        if iqns is None or len(iqns) == 0:
            iqns = bash.bash_o("iscsiadm -m discovery --type sendtargets --portal %s:%s | awk '{print $2}'" % (
                cmd.iscsiServerIp, cmd.iscsiServerPort)).strip().splitlines()

        if iqns is None or len(iqns) == 0:
            rsp.iscsiTargetStructList = []
            return jsonobject.dumps(rsp)

        for iqn in iqns:
            t = IscsiTargetStruct()
            t.iqn = iqn
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
            bash.bash_o('iscsiadm --mode node --targetname "%s" -p %s:%s --login' % (
                iqn, cmd.iscsiServerIp, cmd.iscsiServerPort))
            if bash.bash_r("ls /dev/disk/by-path | grep %s:%s | grep %s" % (cmd.iscsiServerIp, cmd.iscsiServerPort, iqn)) != 0:
                rsp.iscsiTargetStructList.append(t)
                continue
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
            mpath_wwid = bash.bash_o("multipath -l %s | egrep ^mpath | awk '{print $2}'" % abs_path).strip("() \n")
            lun_struct.wwids = [mpath_wwid]
        return lun_struct

    @lock.lock('iscsiadm')
    @kvmagent.replyerror
    def iscsi_logout(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        iqns = cmd.iscsiTargets
        if iqns is None or len(iqns) == 0:
            iqns = shell.call("iscsiadm -m discovery --type sendtargets --portal %s:%s | awk '{print $2}'" % (
                cmd.iscsiServerIp, cmd.iscsiServerPort)).strip().splitlines()

        if iqns is None or len(iqns) == 0:
            rsp.iscsiTargetStructList = []
            return jsonobject.dumps(rsp)

        for iqn in iqns:
            shell.call('iscsiadm --mode node --targetname "%s" -p %s:%s --logout' % (
                iqn, cmd.iscsiServerIp, cmd.iscsiServerPort))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def scan_sg_devices(self, req):
        rsp = AgentRsp()
        bash.bash_roe("sg_scan -i")
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    @linux.retry(times=3, sleep_time=1)
    def enable_multipath(self, req):
        rsp = AgentRsp()
        bash.bash_roe("modprobe dm-multipath")
        bash.bash_roe("modprobe dm-round-robin")
        bash.bash_roe("mpathconf --enable --with_multipathd y")
        if not lvm.is_multipath_running:
            raise RetryException("multipath still not running")
        return jsonobject.dumps(rsp)
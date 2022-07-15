import os.path
import random
import time

from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import bash
from zstacklib.utils import qemu_img
from zstacklib.utils import lock

logger = log.get_logger(__name__)

INITIATOR_FILE_PATH = "/etc/iscsi/initiatorname.iscsi"


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None
        self.totalCapacity = None
        self.availableCapacity = None


class AgentCmd(object):
    def __init__(self):
        pass


class GetInitiatorNameRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetInitiatorNameRsp, self).__init__()
        self.initiatorName = None


class CreateHeartbeatCmd(AgentCmd):
    @log.sensitive_fields("iscsiChapUserPassword")
    def __init__(self):
        super(CreateHeartbeatCmd, self).__init__()
        self.wwn = None
        self.iscsiServerIp = None
        self.iscsiServerPort = None
        self.iscsiChapUserName = None
        self.iscsiChapUserPassword = None
        self.target = None


class DiscoverLunCmd(CreateHeartbeatCmd):
    def __init__(self):
        super(DiscoverLunCmd, self).__init__()


class LogoutLunCmd(CreateHeartbeatCmd):
    def __init__(self):
        super(LogoutLunCmd, self).__init__()


class CreateHeartbeatRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateHeartbeatRsp, self).__init__()


def translate_absolute_path_from_install_paht(path):
    if path is None:
        raise Exception("install path can not be null")
    return path.replace("block:/", "/dev/disk/by-id/wwn-0x")


def translate_absolute_path_from_wwn(wwn):
    if wwn is None:
        raise Exception("wwn can not be null")
    return "/dev/disk/by-id/wwn-0x" + wwn


class BlockStoragePlugin(kvmagent.KvmAgent):
    GET_INITIATOR_NAME_PATH = "/block/primarystorage/getinitiatorname"
    CREATE_HEART_BEAT_PATH = "/block/primarystorage/createheartbeat"
    DOWNLOAD_FROM_IMAGESTORE = "/block/imagestore/download"
    UPLOAD_TO_IMAGESTORE = "/block/imagestore/upload"
    COMMIT_VOLUME_AS_IMAGE = "/block/imagestore/commit"
    DISCOVERY_LUN = "/block/primarystorage/discoverlun"
    LOGOUT_TARGET = "/block/primarystorage/logouttarget"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.GET_INITIATOR_NAME_PATH, self.get_initiator_name)
        http_server.register_async_uri(self.CREATE_HEART_BEAT_PATH, self.create_heart_beat, cmd=CreateHeartbeatCmd())
        http_server.register_async_uri(self.DOWNLOAD_FROM_IMAGESTORE, self.download_from_imagestore)
        http_server.register_async_uri(self.DISCOVERY_LUN, self.discover_lun, cmd=DiscoverLunCmd())
        http_server.register_async_uri(self.LOGOUT_TARGET, self.logout_target, cmd=LogoutLunCmd())
        http_server.register_async_uri(self.UPLOAD_TO_IMAGESTORE, self.upload_to_imagestore)
        http_server.register_async_uri(self.COMMIT_VOLUME_AS_IMAGE, self.commit_to_imagestore)

        self.imagestore_client = ImageStoreClient()

    @kvmagent.replyerror
    def get_initiator_name(self, req):
        logger.debug("start to get host initiator")
        rsp = GetInitiatorNameRsp()
        initiator_name = linux.read_file(INITIATOR_FILE_PATH)
        file_content = initiator_name.splitlines()[0]
        rsp.initiatorName = file_content.split("InitiatorName=")[-1]
        rsp.success = True
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.lock('iscsiadm')
    @bash.in_bash
    def create_heart_beat(self, req):
        logger.debug("start to create heart beat")
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateHeartbeatRsp()

        heartbeat_path = cmd.heartbeatPath
        target = cmd.target
        logger.debug("start to discover target:" + cmd.target)
        self.discovery_iscsi(cmd)
        logger.debug("start to login")
        self.iscsi_login(cmd)

        heartbeat_lun_wwn = translate_absolute_path_from_wwn(cmd.wwn)
        try:
            self.make_sure_lun_has_been_mapped(cmd)

            logger.debug("successfully login iscsi server let's start to init heart beat fs")

            # check heartbeat fs
            r, o, e = bash.bash_roe('file -Ls %s | grep "XFS"' % heartbeat_lun_wwn)
            if r != 0:
                shell.call("mkfs.xfs -f %s" % heartbeat_lun_wwn)
            logger.debug("mount heart beat path")
            if linux.is_mounted(heartbeat_path) is not True:
                linux.mount(heartbeat_lun_wwn, heartbeat_path)
            rsp.success = True
        except Exception as e:
            rsp.success = False
            rsp.error = e.message

        return jsonobject.dumps(rsp)

    def make_sure_lun_has_been_mapped(self, cmd_info):
        successfully_find_lun = False
        try:
            bash.bash_roe("timeout 120 /usr/bin/rescan-scsi-bus.sh -a >/dev/null")
            successfully_find_lun = self.check_lun_status(cmd_info)
        except Exception as e:
            pass
        if successfully_find_lun is True:
            return successfully_find_lun

        try:
            self._logout_target(cmd_info)
        except Exception as e:
            pass
        # just sleep 1 second
        time.sleep(1)
        self.iscsi_login(cmd_info)
        try:
            bash.bash_roe("timeout 120 /usr/bin/rescan-scsi-bus.sh -a >/dev/null")
            successfully_find_lun = self.check_lun_status(cmd_info)
        except Exception as e:
            pass
        return successfully_find_lun

    @linux.retry(times=10, sleep_time=random.uniform(0.1,3))
    def check_lun_status(self, cmd_info):
        abs_path = translate_absolute_path_from_wwn(cmd_info.wwn)
        if os.path.exists(abs_path) is not True:
            logger.debug("Can not find lun wwn: " + abs_path)
            r, o, e = bash.bash_roe("ls %s" % abs_path)
            raise Exception("Can not find lun wwn: " + abs_path)
        logger.debug("successfully find lun wwn: " + abs_path)
        return True

    @kvmagent.replyerror
    def discover_lun(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        logger.debug("start to discover target:" + cmd.target)
        self.discovery_iscsi(cmd)
        iscsi_already_login = self.find_iscsi_session(cmd)
        if iscsi_already_login is True:
            logger.debug("iscsi already login, just to find lun")
            bash.bash_roe("timeout 120 /usr/bin/rescan-scsi-bus.sh -a >/dev/null")
        else:
            logger.debug("start to login")
            self.iscsi_login(cmd)
        rsp.success = self.make_sure_lun_has_been_mapped(cmd)
        return jsonobject.dumps(rsp)

    @bash.in_bash
    def discovery_iscsi(self, loginCmd):
        r, o, e = bash.bash_roe(
            "timeout 10 iscsiadm -m discovery --type sendtargets --portal %s" % (loginCmd.iscsiServerIp)
        )
        if r != 0:
            raise Exception("can not discovery iscsi portal %s, cause %s" % (
                loginCmd.iscsiServerIp, e))

    @bash.in_bash
    def find_iscsi_session(self, loginCmd):
        sid = bash.bash_o("iscsiadm -m session | grep %s:%s | grep %s | awk '{print $2}'" % (
            loginCmd.iscsiServerIp, loginCmd.iscsiServerPort, loginCmd.target)).strip("[]\n ")
        if sid == "" or sid is None:
            return False
        return True

    @kvmagent.replyerror
    def logout_target(self, req):
        logout_cmd = jsonobject.loads(req[http.REQUEST_BODY])
        try:
            self._logout_target(logout_cmd)
        except Exception as e:
            logger.debug(e)
        rsp = AgentRsp
        return jsonobject.dumps(rsp)


    @bash.in_bash
    def _logout_target(self, logoutCmd):
        r, o, e = bash.bash_roe('iscsiadm --mode node --targetname "%s" -p %s:%s --logout' %
                                (logoutCmd.target, logoutCmd.iscsiServerIp, logoutCmd.iscsiServerPort))
        if r != 0:
            raise Exception("fail to logout iscsi %s" % logoutCmd.target)
        r, o, e = bash.bash_roe("timeout 120 /usr/bin/rescan-scsi-bus.sh -r >/dev/null")
        if r != 0:
            raise Exception("fail to logout iscsi %s" % logoutCmd.target)

    @bash.in_bash
    def iscsi_login(self, loginCmd):
        already_login = self.find_iscsi_session(loginCmd)
        if already_login is True:
            return True
        target = loginCmd.target
        if loginCmd.iscsiChapUserName and loginCmd.iscsiChapUserPassword:
            bash.bash_o(
                'iscsiadm --mode node --targetname "%s" -p %s:%s --op=update --name node.session.auth.authmethod --value=CHAP' % (
                    target, loginCmd.iscsiServerIp, loginCmd.iscsiServerPort))
            bash.bash_o(
                'iscsiadm --mode node --targetname "%s" -p %s:%s --op=update --name node.session.auth.username --value=%s' % (
                    target, loginCmd.iscsiServerIp, loginCmd.iscsiServerPort, loginCmd.iscsiChapUserName))
            bash.bash_o(
                'iscsiadm --mode node --targetname "%s" -p %s:%s --op=update --name node.session.auth.password --value=%s' % (
                    target, loginCmd.iscsiServerIp, loginCmd.iscsiServerPort,
                    linux.shellquote(loginCmd.iscsiChapUserPassword)))
        r, o, e = bash.bash_roe('iscsiadm --mode node --targetname "%s" -p %s:%s --login' %
                                (target, loginCmd.iscsiServerIp, loginCmd.iscsiServerPort))
        if r != 0:
            raise Exception("fail to login iscsi %s")

        @linux.retry(times=5, sleep_time=random.uniform(1, 3))
        def retry_check_session(login_info):
            login = self.find_iscsi_session(login_info)
            if login is not True:
                raise Exception("fail to login iscsi %s")

        try:
            retry_check_session(loginCmd)
        except Exception as e:
            return False

        return True

        # check iscsi session

    @kvmagent.replyerror
    def download_from_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        self.imagestore_client.image_info(cmd.hostname, cmd.backupStorageInstallPath)
        self.imagestore_client.download_from_imagestore(None, cmd.hostname, cmd.backupStorageInstallPath,
                                                        cmd.primaryStorageInstallPath)
        bash.bash_o("sync")
        rsp = AgentRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def upload_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.upload_to_imagestore(cmd, req)

    @kvmagent.replyerror
    def commit_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.commit_to_imagestore(cmd, req)

    def stop(self):
        pass

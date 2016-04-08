from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import thread
import os.path
import re
import time
import traceback

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class ScanRsp(object):
    def __init__(self):
        super(ScanRsp, self).__init__()
        self.result = None

class HaPlugin(kvmagent.KvmAgent):
    SCAN_HOST_PATH = "/ha/scanhost"
    SETUP_SELF_FENCER_PATH = "/ha/selffencer/setup"

    RET_SUCCESS = "success"
    RET_FAILURE = "failure"
    RET_NOT_STABLE = "unstable"

    @kvmagent.replyerror
    def setup_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        @thread.AsyncThread
        def heartbeat_file_fencer(heartbeat_file_path):
            try:
                failure = 0

                while True:
                    time.sleep(cmd.interval)

                    if shell.run('timeout 15 touch %s; exit $?' % heartbeat_file_path) == 0:
                        failure = 0
                        continue

                    failure += 1

                    if failure == cmd.maxAttempts:
                        logger.warn('failed to touch the heartbeat file[%s] %s times, we lost the connection to the storage,'
                                    'shutdown ourselves' % (heartbeat_file_path, cmd.maxAttempts))
                        shell.call('init 0')
            except:
                content = traceback.format_exc()
                logger.warn(content)


        gateway = cmd.storageGateway
        if not gateway:
            gateway = linux.get_gateway_by_default_route()

        @thread.AsyncThread
        def storage_gateway_fencer(gw):
            failure = 0

            try:
                while True:
                    time.sleep(cmd.interval)

                    if shell.run("nmap -sP -PI %s | grep 'Host is up'" % gw) == 0:
                        failure = 0
                        continue

                    failure += 1

                    if failure == cmd.maxAttempts:
                        logger.warn('failed to ping storage gateway[%s] %s times, we lost connection to the storage,'
                                    'shutdown ourselves' % (gw, cmd.maxAttempts))
                        shell.call('init 0')
            except:
                content = traceback.format_exc()
                logger.warn(content)

        for mount_point in cmd.mountPoints:
            if not os.path.isdir(mount_point):
                raise Exception('the mount point[%s] is not a directory' % mount_point)

            hb_file = os.path.join(mount_point, 'heartbeat-file-kvm-host-%s.hb' % cmd.hostUuid)
            heartbeat_file_fencer(hb_file)

        if gateway:
            storage_gateway_fencer(gateway)
        else:
            logger.warn('cannot find storage gateway, unable to setup storage gateway fencer')

        return jsonobject.dumps(AgentRsp())


    @kvmagent.replyerror
    def scan_host(self, req):
        rsp = ScanRsp()

        success = 0
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        for i in range(0, cmd.times):
            if shell.run("nmap -sP -PI %s | grep 'Host is up'" % cmd.ip) == 0:
                success += 1

            time.sleep(cmd.interval)

        if success == cmd.successTimes:
            rsp.result = self.RET_SUCCESS
            return jsonobject.dumps(rsp)

        if success == 0:
            rsp.result = self.RET_FAILURE
            return jsonobject.dumps(rsp)

        # WE SUCCEED A FEW TIMES, IT SEEMS THE CONNECTION NOT STABLE
        success = 0
        for i in range(0, cmd.successTimes):
            if shell.run("nmap -sP -PI %s | grep 'Host is up'" % cmd.ip) == 0:
                success += 1

            time.sleep(cmd.successInterval)

        if success == cmd.successTimes:
            rsp.result = self.RET_SUCCESS
            return jsonobject.dumps(rsp)

        rsp.result = self.RET_NOT_STABLE
        return jsonobject.dumps(rsp)


    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.SCAN_HOST_PATH, self.scan_host)
        http_server.register_async_uri(self.SETUP_SELF_FENCER_PATH, self.setup_self_fencer)

    def stop(self):
        pass
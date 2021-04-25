# coding=utf-8
'''

@author: mingjian.deng
'''
import os.path
import traceback

import zstacklib.utils.uuidhelper as uuidhelper
from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils.bash import *

logger = log.get_logger(__name__)

tdcversion = 1

class AliyunEbsStoragePlugin(kvmagent.KvmAgent):
    INSTALL_TDC_PATH = "/aliyun/ebs/primarystorage/installtdc"
    DETACH_VOLUME_PATH = "/aliyun/ebs/primarystorage/detachvolume"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INSTALL_TDC_PATH, self.installtdc)
        http_server.register_async_uri(self.DETACH_VOLUME_PATH, self.detachvolume)

        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    @kvmagent.replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @kvmagent.replyerror
    def installtdc(self, req):
        def overwriteConfig(config, cfile):
            c = open(cfile, 'w')
            c.write(config)
            c.close()

        def updateTdcConfig(config, cfile):
            '''
               1. read /opt/tdc/apsara_global_config.json if existed
               2. compare with config
               3. overwrite if it is different
            '''
            if not os.path.exists(cfile):
                d = os.path.dirname(cfile)
                if not os.path.exists(d):
                    os.makedirs(d, 0o755)
                overwriteConfig(config, cfile)
                return True

            updated = False
            c = open(cfile)
            if config != c.read().strip():
                overwriteConfig(config, cfile)
                updated = True

            c.close()
            return updated

        def installTdc(cmd):
            logger.debug('install tdc pkg')
            if cmd.version != tdcversion:
                return "no matched tdc version found, agent need version %d" % tdcversion

            startCmd = shell.ShellCmd("/opt/tdc/tdc_admin lsi")
            startCmd(False)
            if startCmd.return_code != 0:
                linux.mkdir("/apsara", 0o755)
                e = shell.ShellCmd('rpm -qi tdc-unified-8.2.0.release.el5.x86_64')
                e(False)
                if e.return_code != 0:
                    shell.call("export YUM0={}; yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn clean metadata".format(kvmagent.get_host_yum_release()))
                    shell.call("export YUM0={}; yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn install -y tdc-unified-8.2.0.release.el5.x86_64".format(kvmagent.get_host_yum_release()))
                shell.call("service tdc restart")

                startCmd = shell.ShellCmd("/opt/tdc/tdc_admin lsi")
                startCmd(False)
                if startCmd.return_code != 0:
                    return "tdc_admin lsi failed: %s" % startCmd.stderr
            return None
        def installVrbd():
            logger.debug('modprobe vrbd')
            lsModCmd = shell.ShellCmd("lsmod|grep vrbd")
            lsModCmd(False)
            if lsModCmd.return_code != 0:
                e = shell.ShellCmd('rpm -qi kernel-3.10.0-693.11.1.el7.x86_64-vrbd-1.0-0.1.release1.alios7.x86_64')
                e(False)
                if e.return_code != 0:
                    shell.call("export YUM0={}; yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn clean metadata".format(kvmagent.get_host_yum_release()))
                    shell.call("export YUM0={}; yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn install -y kernel-3.10.0-693.11.1.el7.x86_64-vrbd-1.0-0.1.release1.alios7.x86_64".format(kvmagent.get_host_yum_release()))
                shell.call("modprobe vrbd")
            else:
                return
            lsModCmd(False)
            if lsModCmd.return_code != 0:
                return "cannot attach vrbd mod"

        rsp = kvmagent.AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        rsp.error = installTdc(cmd) or installVrbd()
        if rsp.error is not None:
            return jsonobject.dumps(rsp)

        if cmd.tdcConfig and cmd.nuwaConfig and cmd.nuwaCfg:
            tdc = updateTdcConfig(cmd.tdcConfig, '/opt/tdc/apsara_global_flag.json')
            nuwa1 = updateTdcConfig(cmd.nuwaConfig, '/apsara/conf/conffiles/nuwa/client/nuwa_config.json')
            nuwa2 = updateTdcConfig(cmd.nuwaCfg, '/apsara/nuwa/nuwa.cfg')
            if tdc or nuwa1 or nuwa2:
                logger.debug('config changed, restart tdc service')
                shell.call("service tdc restart")

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detachvolume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        logger.debug('detach volume %s' % cmd.volumeId)
        rsp = kvmagent.AgentResponse()
        s = shell.ShellCmd("/opt/tdc/tdc_admin destroy-vrbd --device_id=%s" % cmd.volumeId)
        s(False)
        if s.return_code != 0:
            rsp.success = False
            rsp.error = "detach volume failed: %s" % s.stderr

        return jsonobject.dumps(rsp)

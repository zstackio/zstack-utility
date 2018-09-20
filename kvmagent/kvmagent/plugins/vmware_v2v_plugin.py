import os
import json
import commands
import traceback

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import http
from zstacklib.utils.bash import in_bash

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class ConvertRsp(AgentRsp):
    def __init__(self):
        self.rootVolumeActualSize = None
        self.rootVolumeVirtualSize = None
        self.dataVolumeActualSizes = []
        self.dataVolumeVirtualSizes = []
        self.bootMode = None

class VMwareV2VPlugin(kvmagent.KvmAgent):
    INIT_PATH = "/vmwarev2v/conversionhost/init"
    CONVERT_PATH = "/vmwarev2v/conversionhost/convert"
    CLEAN_PATH = "/vmwarev2v/conversionhost/clean"
    CONFIG_QOS_PATH = "/vmwarev2v/conversionhost/qos/config"
    DELETE_QOS_PATH = "/vmwarev2v/conversionhost/qos/delete"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.CONVERT_PATH, self.convert)
        http_server.register_async_uri(self.CLEAN_PATH, self.clean)
        http_server.register_async_uri(self.CONFIG_QOS_PATH, self.config_qos)
        http_server.register_async_uri(self.DELETE_QOS_PATH, self.delete_qos)

    def stop(self):
        pass

    @in_bash
    @kvmagent.replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        cmdstr = 'which docker || yum --disablerepo=* --enablerepo={0} clean all; yum --disablerepo=* --enablerepo={0} install docker -y'.format(cmd.zstackRepo)
        if shell.run(cmdstr) != 0:
            rsp.success = False
            rsp.error = "failed to install docker in conversion host"
            return jsonobject.dumps(rsp)

        cmdstr = 'systemctl start docker && docker history zs_virt_v2v'
        if (shell.run(cmdstr)) == 0:
            return jsonobject.dumps(rsp)

        cmdstr = 'mkdir -p {0} && cd {0} && wget -c {1} -O virt_v2v_image.tgz && tar xvf virt_v2v_image.tgz'.format(cmd.storagePath, cmd.v2vImageUrl)
        if shell.run(cmdstr) != 0:
            rsp.success = False
            rsp.error = "failed to download virt_v2v_image.tgz from management node to v2v conversion host"
            return jsonobject.dumps(rsp)

        cmdstr = 'systemctl start docker && docker load < {0}/virt_v2v_image.tar && rm -f {0}/virt_v2v_image*'.format(cmd.storagePath)
        if shell.run(cmdstr) != 0:
            rsp.success = False
            rsp.error = "failed to import virt_v2v_image to docker in v2v conversion host"
            return jsonobject.dumps(rsp)

        cmdstr = 'cd /usr/local/zstack && wget -c {} -O zstack-windows-virtio-driver.iso'.format(cmd.virtioDriverUrl)
        if shell.run(cmdstr) != 0:
            rsp.success = False
            rsp.error = "failed to download zstack-windows-virtio-driver.iso from management node to v2v conversion host"
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def convert(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConvertRsp()
        storagePath = '{}/{}'.format(cmd.storagePath, cmd.dstVmUuid)
        cmdstr = "mkdir -p {0} && echo '{1}' > {0}/passwd".format(storagePath, cmd.vCenterPassword)
        if shell.run(cmdstr) != 0:
            rsp.success = False
            rsp.error = "failed to create storagePath {} in v2v conversion host[hostUuid:{}]".format(storagePath, cmd.hostUuid)
            return jsonobject.dumps(rsp)

        virt_v2v_cmd = 'virt-v2v -v -x \
                -ic vpx://{0}?no_verify=1 "{1}" \
                -it vddk \
                --vddk-libdir=/home/v2v/vmware-vix-disklib-distrib \
                --vddk-thumbprint={3}    \
                -o local -os {2} \
                --password-file {2}/passwd \
                -of qcow2 --compress > {2}/virt_v2v_log 2>&1'.format(cmd.srcVmUri, cmd.srcVmName, storagePath, cmd.thumbprint)
        docker_run_cmd = 'systemctl start docker && docker run --rm -v /usr/local/zstack:/usr/local/zstack -v {0}:{0} \
                -e VIRTIO_WIN=/usr/local/zstack/zstack-windows-virtio-driver.iso \
                -e PATH=/home/v2v/nbdkit:$PATH \
                zs_virt_v2v {1}'.format(cmd.storagePath, virt_v2v_cmd)
        if shell.run(docker_run_cmd) != 0:
            rsp.success = False
            rsp.error = "failed to run virt-v2v command: " + docker_run_cmd
            return jsonobject.dumps(rsp)

        rootVol = r"%s/%s-sda" % (storagePath, cmd.srcVmName)
        if not os.path.exists(rootVol):
            rsp.success = False
            rsp.error = "failed to convert root volume of " + cmd.srcVmName
            return jsonobject.dumps(rsp)
        rsp.rootVolumeActualSize, rsp.rootVolumeVirtualSize = self._get_qcow2_sizes(rootVol)

        for dev in 'bcdefghijklmnopqrstuvwxyz':
            dataVol = r"%s/%s-sd%c" % (storagePath, cmd.srcVmName, dev)
            if os.path.exists(dataVol):
                aSize, vSize = self._get_qcow2_sizes(dataVol)
                rsp.dataVolumeActualSizes.append(aSize)
                rsp.dataVolumeVirtualSizes.append(vSize)
            else:
                break
        return jsonobject.dumps(rsp)

    @in_bash
    def _get_qcow2_sizes(self, path):
        cmd = "qemu-img info --output=json " + path
        _, output = commands.getstatusoutput(cmd)
        return long(json.loads(output)['actual-size']), long(json.loads(output)['virtual-size'])

    @in_bash
    @kvmagent.replyerror
    def clean(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if not cmd.dstVmUuid:
            cleanUpPath = cmd.storagePath
        else:
            cleanUpPath = '{}/{}'.format(cmd.storagePath, cmd.dstVmUuid)
        cmdstr = "/bin/rm -rf " + cleanUpPath
        shell.run(cmdstr)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def config_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        cmdstr = "tc qdisc del dev docker0 root >/dev/null 2>&1; tc qdisc add dev docker0 root tbf rate %sbit latency 10ms burst 100m" % cmd.inboundBandwidth
        shell.run(cmdstr)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def delete_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        cmdstr = "tc qdisc del dev docker0 root >/dev/null 2>&1"
        shell.run(cmdstr)
        return jsonobject.dumps(rsp)

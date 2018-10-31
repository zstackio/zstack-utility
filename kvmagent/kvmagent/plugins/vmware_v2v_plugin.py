#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import commands

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import http
from zstacklib.utils import thread
from zstacklib.utils.bash import in_bash
from zstacklib.utils.linux import shellquote
from zstacklib.utils.plugin import completetask

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

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

class VMwareV2VPlugin(kvmagent.KvmAgent):
    INIT_PATH = "/vmwarev2v/conversionhost/init"
    CONVERT_PATH = "/vmwarev2v/conversionhost/convert"
    CLEAN_PATH = "/vmwarev2v/conversionhost/clean"
    CHECK_BITS = "/vmwarev2v/conversionhost/checkbits"
    CONFIG_QOS_PATH = "/vmwarev2v/conversionhost/qos/config"
    DELETE_QOS_PATH = "/vmwarev2v/conversionhost/qos/delete"
    CANCEL_CONVERT_PATH = "/vmwarev2v/conversionhost/convert/cancel"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.CONVERT_PATH, self.convert)
        http_server.register_async_uri(self.CLEAN_PATH, self.clean)
        http_server.register_async_uri(self.CANCEL_CONVERT_PATH, self.clean_convert)
        http_server.register_async_uri(self.CHECK_BITS, self.check_bits)
        http_server.register_async_uri(self.CONFIG_QOS_PATH, self.config_qos)
        http_server.register_async_uri(self.DELETE_QOS_PATH, self.delete_qos)

    def stop(self):
        pass

    @in_bash
    @kvmagent.replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        cmdstr = 'cd /usr/local/zstack && wget -c {} -O zstack-windows-virtio-driver.iso'.format(cmd.virtioDriverUrl)
        if shell.run(cmdstr) != 0:
            rsp.success = False
            rsp.error = "failed to download zstack-windows-virtio-driver.iso from management node to v2v conversion host"
            return jsonobject.dumps(rsp)

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

        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    @completetask
    def convert(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConvertRsp()

        storage_dir = os.path.join(cmd.storagePath, cmd.srcVmUuid)

        def validate_and_make_dir(_dir):
            existing = os.path.exists(_dir)
            if not existing:
                shell.call("mkdir -p %s" % _dir)
            return existing

        last_task = self.load_and_save_task(req, rsp, validate_and_make_dir, storage_dir)
        if last_task and last_task.agent_pid == os.getpid():
            rsp = self.wait_task_complete(last_task)
            return jsonobject.dumps(rsp)

        new_task = self.load_task(req)

        cmdstr = "echo '{1}' > {0}/passwd".format(storage_dir, cmd.vCenterPassword)
        if shell.run(cmdstr) != 0:
            rsp.success = False
            rsp.error = "failed to create passwd {} in v2v conversion host".format(storage_dir)
            return jsonobject.dumps(rsp)


        @thread.AsyncThread
        def save_pid():
            linux.wait_callback_success(os.path.exists, v2v_pid_path)
            with open(v2v_pid_path, 'r') as fd:
                new_task.current_pid = fd.read().strip()
            new_task.current_process_cmd = echo_pid_cmd
            new_task.current_process_name = "virt_v2v_cmd"
            logger.debug("longjob[uuid:%s] saved process[pid:%s, name:%s]" %
                         (cmd.longJobUuid, new_task.current_pid, new_task.current_process_name))

        virt_v2v_cmd = 'virt-v2v \
                -ic vpx://{0}?no_verify=1 {1} \
                -it vddk \
                --vddk-libdir=/home/v2v/vmware-vix-disklib-distrib \
                --vddk-thumbprint={3}    \
                -o local -os {2} \
                --password-file {2}/passwd \
                -of qcow2 --compress > {2}/virt_v2v_log 2>&1'.format(cmd.srcVmUri, shellquote(cmd.srcVmName), storage_dir, cmd.thumbprint)
        docker_run_cmd = 'systemctl start docker && docker run --rm -v /usr/local/zstack:/usr/local/zstack -v {0}:{0} \
                -e VIRTIO_WIN=/usr/local/zstack/zstack-windows-virtio-driver.iso \
                -e PATH=/home/v2v/nbdkit:$PATH \
                zs_virt_v2v {1}'.format(cmd.storagePath.rstrip('/'), virt_v2v_cmd)

        v2v_pid_path = os.path.join(storage_dir, "convert.pid")
        v2v_cmd_ret_path = os.path.join(storage_dir, "convert.ret")
        echo_pid_cmd = "echo $$ > %s; %s; ret=$?; echo $ret > %s; exit $ret" % (v2v_pid_path, docker_run_cmd, v2v_cmd_ret_path)

        def run_convert_if_need():
            def do_run():
                self.check_docker()
                save_pid()
                ret = shell.run(echo_pid_cmd)
                new_task.current_process_return_code = ret
                return ret

            pid = linux.read_file(v2v_pid_path)
            if not pid:
                return do_run()

            pid = int(pid.strip())
            process_completed = os.path.exists(v2v_cmd_ret_path)
            process_has_been_killed = not os.path.exists(v2v_cmd_ret_path) and not os.path.exists('/proc/%d' % pid)
            process_still_running = not os.path.exists(v2v_cmd_ret_path) and os.path.exists('/proc/%d' % pid)
            if process_has_been_killed:
                return do_run()

            if process_still_running:
                linux.wait_callback_success(os.path.exists, v2v_cmd_ret_path, timeout=259200, interval=60)

            ret = linux.read_file(v2v_cmd_ret_path)
            return int(ret.strip() if ret else 126)

        if run_convert_if_need() != 0:
            v2v_log_file = "/tmp/v2v_log/%s-virt-v2v-log" % cmd.longJobUuid

            rsp.success = False
            rsp.error = "failed to run virt-v2v command, log in conversion host: %s" % v2v_log_file

            # create folder to save virt-v2v log
            tail_cmd = 'mkdir -p /tmp/v2v_log; tail -c 1M %s/virt_v2v_log > %s' % (storage_dir, v2v_log_file)
            shell.run(tail_cmd)
            with open(v2v_log_file, 'a') as fd:
                fd.write('\n>>> VCenter Password: %s\n' % cmd.vCenterPassword)
                fd.write('\n>>> virt_v2v command: %s\n' % docker_run_cmd)
            return jsonobject.dumps(rsp)

        root_vol = r"%s/%s-sda" % (storage_dir, cmd.srcVmName)
        if not os.path.exists(root_vol):
            rsp.success = False
            rsp.error = "failed to convert root volume of " + cmd.srcVmName
            return jsonobject.dumps(rsp)
        root_volume_actual_size, root_volume_virtual_size = self._get_qcow2_sizes(root_vol)
        rsp.rootVolumeInfo = {"installPath": root_vol,
                              "actualSize": root_volume_actual_size,
                              "virtualSize": root_volume_virtual_size,
                              "deviceId": 0}

        rsp.dataVolumeInfos = []
        for dev in 'bcdefghijklmnopqrstuvwxyz':
            data_vol = r"%s/%s-sd%c" % (storage_dir, cmd.srcVmName, dev)
            if os.path.exists(data_vol):
                aSize, vSize = self._get_qcow2_sizes(data_vol)
                rsp.dataVolumeInfos.append({"installPath": data_vol,
                                            "actualSize": aSize,
                                            "virtualSize": vSize,
                                            "deviceId": ord(dev) - ord('a')})
            else:
                break

        xml = r"%s/%s.xml" % (storage_dir, cmd.srcVmName)
        if self._check_str_in_file(xml, "<nvram "):
            rsp.bootMode = 'UEFI'

        return jsonobject.dumps(rsp)

    def check_docker(self):
        if shell.run("ip addr show docker0 > /dev/null && /sbin/iptables-save | grep -q 'FORWARD.*docker0'") != 0:
            logger.warn("cannot find docker iptables rule, restart docker server!")
            shell.run("systemctl restart docker")

    def _check_str_in_file(self, fname, txt):
        with open(fname) as dataf:
            return any(txt in line for line in dataf)

    @in_bash
    def _get_qcow2_sizes(self, path):
        cmd = "qemu-img info --output=json '%s'" % path
        _, output = commands.getstatusoutput(cmd)
        return long(json.loads(output)['actual-size']), long(json.loads(output)['virtual-size'])

    @in_bash
    @kvmagent.replyerror
    def clean(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()
        if not cmd.srcVmUuid:
            cleanUpPath = cmd.storagePath
        else:
            cleanUpPath = os.path.join(cmd.storagePath, cmd.srcVmUuid)
            shell.run("pkill -9 -f '%s'" % cleanUpPath)

        cmdstr = "/bin/rm -rf " + cleanUpPath
        shell.run(cmdstr)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def clean_convert(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        clean_up_path = os.path.join(cmd.storagePath, cmd.srcVmUuid)
        shell.run("pkill -9 -f '%s'" % clean_up_path)
        shell.run("/bin/rm -rf " + clean_up_path)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsRsp()
        rsp.existing = os.path.exists(cmd.path)
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

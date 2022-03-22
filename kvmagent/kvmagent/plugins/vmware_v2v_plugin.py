#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import commands
import platform
import string
import re
import tempfile

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import http
from zstacklib.utils import thread
from zstacklib.utils import qemu_img
from zstacklib.utils import iproute
from zstacklib.utils.bash import in_bash
from zstacklib.utils.linux import shellquote
from zstacklib.utils.plugin import completetask

logger = log.get_logger(__name__)

class RetryException(Exception):
    pass

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


class GetConvertProgressRsp(AgentRsp):
    def __init__(self):
        super(GetConvertProgressRsp, self).__init__()
        self.currentDiskNum = None
        self.currentProgress = None
        self.totalDiskNum = None


QOS_IFB = "ifb0"
HOST_ARCH = platform.machine()

VDDK_VERSION = '/var/lib/zstack/v2v/vddk_version'
NBDKIT_BUILD_LOG_PATH = '/var/lib/zstack/v2v/nbdkit_build_lib/log'
NBDKIT_BUILD_LIB_PATH = '/var/lib/zstack/v2v/nbdkit_build_lib/'
NBDKIT_VERSION_PATH = '/var/lib/zstack/v2v/nbdkit_build_lib/nbdkit_version'
ADAPTED_VDDK_VERSION_PATH = '/var/lib/zstack/v2v/nbdkit_build_lib/vddk_version'
WINDOWS_VIRTIO_DRIVE_ISO_VERSION = '/var/lib/zstack/v2v/windows_virtio_version'
V2V_LIB_PATH = '/var/lib/zstack/v2v/'
LIBGUESTFS_TEST_LOG_PATH = '/var/lib/zstack/v2v/libguestfs-test.log'

class VMwareV2VPlugin(kvmagent.KvmAgent):
    INIT_PATH = "/vmwarev2v/conversionhost/init"
    CONVERT_PATH = "/vmwarev2v/conversionhost/convert"
    CONVERT_PROGRESS_PATH = "/vmwarev2v/conversionhost/convert/progress"
    CLEAN_PATH = "/vmwarev2v/conversionhost/clean"
    CHECK_BITS = "/vmwarev2v/conversionhost/checkbits"
    CONFIG_QOS_PATH = "/vmwarev2v/conversionhost/qos/config"
    DELETE_QOS_PATH = "/vmwarev2v/conversionhost/qos/delete"
    CANCEL_CONVERT_PATH = "/vmwarev2v/conversionhost/convert/cancel"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.CONVERT_PATH, self.convert)
        http_server.register_async_uri(self.CONVERT_PROGRESS_PATH, self.get_convert_progress)
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

        _, os_version, _ = platform.dist()
        versions = os_version.split('.')
        # check if os is centos 7.2
        if len(versions) > 2 and versions[0] == '7' and versions[1] == '2':
            rsp.success = False
            rsp.error = "v2v feature is not supported on centos 7.2"
            return jsonobject.dumps(rsp)

        x86_64_c74 = "libguestfs-tools libguestfs-tools-c perl-Sys-Guestfs libguestfs-winsupport virt-v2v"
        x86_64_c76 = "libguestfs-tools libguestfs-tools-c perl-Sys-Guestfs libguestfs-winsupport virt-v2v"
        x86_64_ns10 = "libguestfs"

        releasever = kvmagent.get_host_yum_release()
        dep_list = eval("%s_%s" % (HOST_ARCH, releasever))
        yum_cmd = "export YUM0={}; yum --enablerepo=* clean all && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn " \
                  "install {} -y".format(releasever, dep_list)
        if shell.run(yum_cmd) != 0:
            rsp.success = False
            rsp.error = "failed to update install conversion host dependencies from zstack-mn,qemu-kvm-ev-mn repo"
            return jsonobject.dumps(rsp)

        path = "/var/lib/zstack/v2v"
        if not os.path.exists(path):
            os.makedirs(path, 0775)

        if not os.path.exists(cmd.storagePath):
            os.makedirs(cmd.storagePath, 0775)

        def get_dep_version_from_version_file(version_file):
            if not os.path.exists(version_file):
                return None
            else:
                with open(version_file, 'r') as vfd:
                    return vfd.readline()
        tmpl = {'releasever': releasever}
        virtioDriverUrl = string.Template(cmd.virtioDriverUrl)
        vddkLibUrl = string.Template(cmd.vddkLibUrl)
        adaptedVddkLibUrl = string.Template(cmd.adaptedVddkLibUrl)
        nbdkitUrl = string.Template(cmd.nbdkitUrl)

        cmd.virtioDriverUrl = virtioDriverUrl.substitute(tmpl)
        cmd.vddkLibUrl = vddkLibUrl.substitute(tmpl)
        cmd.adaptedVddkLibUrl = adaptedVddkLibUrl.substitute(tmpl)
        cmd.nbdkitUrl = nbdkitUrl.substitute(tmpl)

        def check_libguestfs():
            cmd = "/usr/bin/libguestfs-test-tool > {} 2>&1".format(LIBGUESTFS_TEST_LOG_PATH)

            if shell.run(cmd) != 0:
                rsp.success = False
                rsp.error = "libguestfs test failed, log file: %s" % LIBGUESTFS_TEST_LOG_PATH
                return jsonobject.dumps(rsp)

        def check_nbdkit_version(cmd, rsp):
            if os.path.exists(NBDKIT_VERSION_PATH) and os.path.exists(ADAPTED_VDDK_VERSION_PATH):
                current_nbdkit_version = linux.read_file(NBDKIT_VERSION_PATH).strip()
                current_vddk_version = linux.read_file(ADAPTED_VDDK_VERSION_PATH).strip()

                remote_nbdkit_version = cmd.nbdkitUrl.split("/")[-1]
                remote_vddk_version = cmd.adaptedVddkLibUrl.split("/")[-1]

                if current_nbdkit_version == remote_nbdkit_version \
                        and current_vddk_version == remote_vddk_version \
                        and self._ndbkit_is_work():
                    logger.info("local nbdkit[%s] and vddk[%s] version is as same as remote version" % (current_nbdkit_version, current_vddk_version))
                    return
                else:
                    build_nbdkit_with_adapted_vddk(cmd, rsp)
            else:
                build_nbdkit_with_adapted_vddk(cmd, rsp)

        def get_dir_path_from_url(url):
            return "%s%s" % (NBDKIT_BUILD_LIB_PATH, url.split("/")[-1].strip('.tar.gz'))

        def build_nbdkit_with_adapted_vddk(cmd, rsp):
            logger.info("start build nbdkit with adapted vddk......")
            if os.path.exists(NBDKIT_BUILD_LIB_PATH):
                linux.rm_dir_force(NBDKIT_BUILD_LIB_PATH)

            wget_path_file = linux.write_to_temp_file("%s\n%s" % (cmd.adaptedVddkLibUrl, cmd.nbdkitUrl))

            # wget ndbkit and old vddk
            linux.mkdir(NBDKIT_BUILD_LIB_PATH)
            wget_cmd = 'cd {} && wget -c -i {} && tar zxf {} && tar zxf {};'.format(
                NBDKIT_BUILD_LIB_PATH, wget_path_file,
                cmd.nbdkitUrl.split("/")[-1], cmd.adaptedVddkLibUrl.split("/")[-1])

            if shell.run(wget_cmd) != 0:
                rsp.success = False
                rsp.error = "failed to download nbdkit and vddklib " \
                            "from management node to v2v conversion host"
                os.remove(wget_path_file)
                return jsonobject.dumps(rsp)

            logger.info("wget nbdkit and vddk lib from mn success")
            os.remove(wget_path_file)

            build_cmd = "cd {} && ./configure --with-vddk={} > {} 2>&1; " \
                        "make install >> {} 2>&1".format(get_dir_path_from_url(cmd.nbdkitUrl), get_dir_path_from_url(cmd.adaptedVddkLibUrl),
                                                         NBDKIT_BUILD_LOG_PATH, NBDKIT_BUILD_LOG_PATH)

            # persist nbdkit and vddk version
            linux.write_file(NBDKIT_VERSION_PATH, cmd.nbdkitUrl.split("/")[-1], True)
            linux.write_file(ADAPTED_VDDK_VERSION_PATH, cmd.adaptedVddkLibUrl.split("/")[-1], True)

            # build nbdkit
            if shell.run(build_cmd) != 0 or not self._ndbkit_is_work():
                rsp.success = False
                rsp.error = "failed to build nbdkit with vddk, log in conversion host: %s" % NBDKIT_BUILD_LOG_PATH
                return jsonobject.dumps(rsp)

        if not os.path.exists(WINDOWS_VIRTIO_DRIVE_ISO_VERSION) \
                and os.path.exists(V2V_LIB_PATH + 'zstack-windows-virtio-driver.iso'):
            last_modified = shell.call("curl -I %s | grep 'Last-Modified'" % cmd.virtioDriverUrl)
            with open(WINDOWS_VIRTIO_DRIVE_ISO_VERSION, 'w') as fd:
                fd.write(last_modified.strip('\n\r'))
        else:
            last_modified = shell.call("curl -I %s | grep 'Last-Modified'" % cmd.virtioDriverUrl).strip('\n\r')

            version = get_dep_version_from_version_file(WINDOWS_VIRTIO_DRIVE_ISO_VERSION)

            if version != last_modified:
                cmdstr = 'cd /var/lib/zstack/v2v && wget -c {} -O zstack-windows-virtio-driver.iso'.format(
                    cmd.virtioDriverUrl)
                if shell.run(cmdstr) != 0:
                    rsp.success = False
                    rsp.error = "failed to download zstack-windows-virtio-driver.iso " \
                                "from management node to v2v conversion host"
                    return jsonobject.dumps(rsp)

                with open(WINDOWS_VIRTIO_DRIVE_ISO_VERSION, 'w') as fd:
                    fd.write(last_modified)

        if not os.path.exists(VDDK_VERSION) and os.path.exists(V2V_LIB_PATH + 'vmware-vix-disklib-distrib.tar.gz'):
            with open(VDDK_VERSION, 'w') as fd:
                fd.write(cmd.vddkLibUrl.split('/')[-1])
        else:
            current_version = cmd.vddkLibUrl.split('/')[-1]

            version = get_dep_version_from_version_file(VDDK_VERSION)

            if current_version != version:
                cmdstr = 'cd /var/lib/zstack/v2v && wget -c {} -O vmware-vix-disklib-distrib.tar.gz && ' \
                         'tar zxf vmware-vix-disklib-distrib.tar.gz'.format(
                    cmd.vddkLibUrl)
                if shell.run(cmdstr) != 0:
                    rsp.success = False
                    rsp.error = "failed to download vmware-vix-disklib-distrib.tar.gz " \
                                "from management node to v2v conversion host"
                    return jsonobject.dumps(rsp)

                with open(VDDK_VERSION, 'w') as fd:
                    fd.write(current_version)

        check_nbdkit_version(cmd, rsp)
        check_libguestfs()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_convert_progress(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetConvertProgressRsp()

        storage_dir = os.path.join(cmd.storagePath, cmd.srcVmUuid)
        v2v_pid_path = os.path.join(storage_dir, "convert.pid")
        pid = linux.read_file(v2v_pid_path)
        if not pid:
            rsp.success = False
            rsp.error = "no v2v process exists"
            return jsonobject.dumps(rsp)

        v2v_log_file = "%s/virt_v2v_log" % storage_dir

        tail_log_cmd = shell.ShellCmd('tail -2 %s' % v2v_log_file)
        tail_log_cmd(False)

        if tail_log_cmd.return_code == 0 and tail_log_cmd.stdout:
            out = tail_log_cmd.stdout
            if 'Converting' in out and 'to run on KVM' in out:
                rsp.currentDiskNum = '0'
                rsp.currentProgress = '10'
            elif 'Inspecting the overlay' in out:
                rsp.currentDiskNum = '0'
                rsp.currentProgress = '7'
            elif 'Opening the overlay' in out:
                rsp.currentDiskNum = '0'
                rsp.currentProgress = '3'
            elif 'Copying disk' in out:
                output = out.split('\n')
                percentage = None
                search_result = None

                if 'Copying disk' in output[1]:
                    percentage = '0'
                    search_result = re.search("Copying disk.*.to", output[1])
                else:
                    percentage = output[1].replace('\015', '').split(' ')[-1].replace('(', '').split('/')[0]
                    search_result = re.search("Copying disk.*.to", output[0])

                if search_result is not None:
                    num_ret = search_result.group().split(' ')[2].split('/')
                    rsp.currentDiskNum = num_ret[0]
                    rsp.currentProgress = percentage
                    if len(num_ret) > 1 and num_ret[1].isdigit():
                        rsp.totalDiskNum = num_ret[1]
            else:
                logger.debug("not handled log keep progress")
        else:
            logger.debug("Failed to tail log, keep the progress")

        return jsonobject.dumps(rsp)

    @staticmethod
    def _ndbkit_is_work():
        if not os.path.exists(NBDKIT_VERSION_PATH):
            return False

        nbd_version = linux.read_file(NBDKIT_VERSION_PATH)
        check_cmd = shell.ShellCmd(".%s%s/nbdkit --version" % (NBDKIT_BUILD_LIB_PATH, nbd_version.strip('.tar.gz')))
        check_cmd(False)

        if check_cmd.return_code != 0:
            return False
        return True

    @staticmethod
    def _get_nbdkit_dir_path():
        version = linux.read_file(NBDKIT_VERSION_PATH)
        return "%s%s/" % (NBDKIT_BUILD_LIB_PATH, version.strip('tar.gz'))

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

        def get_v2v_cmd(cmd, rsp):
            extra_params = ""
            if cmd.extraParams:
                for k, v in cmd.extraParams.__dict__.items():
                    extra_params = ' '.join((extra_params, ("--%s" % k), v))

            # if source virtual machine is dual-boot or multi boot
            # need to set --root to specific one root filesystem for convertion
            # if no rootFileSystem set, use 'ask' which is default argument
            # for --root
            if cmd.vddkVersion == '6.5':
                return 'export PATH={6}:$PATH; \
                        VIRTIO_WIN=/var/lib/zstack/v2v/zstack-windows-virtio-driver.iso \
                        virt-v2v -ic vpx://{0}?no_verify=1 {1} -it vddk \
                        --vddk-libdir=/var/lib/zstack/v2v/vmware-vix-disklib-distrib \
                        --vddk-thumbprint={3} -o local -os {2} --password-file {2}/passwd {5} \
                        --root {7} \
                        -of {4} > {2}/virt_v2v_log 2>&1'.format(cmd.srcVmUri, shellquote(cmd.srcVmName), storage_dir,
                                                                cmd.thumbprint, cmd.format, extra_params, self._get_nbdkit_dir_path(),
                                                                cmd.rootFileSystem if cmd.rootFileSystem else 'ask')
            if cmd.vddkVersion == '5.5':
                return 'export PATH={5}:$PATH; \
                        VIRTIO_WIN=/var/lib/zstack/v2v/zstack-windows-virtio-driver.iso \
                        virt-v2v -ic vpx://{0}?no_verify=1 {1} -it vddk \
                        --vddk-libdir=/var/lib/zstack/v2v/nbdkit_build_lib/vmware-vix-disklib-distrib \
                        --vddk-thumbprint={3} -o local -os {2} --password-file {2}/passwd {6} \
                        -of {4} > {2}/virt_v2v_log 2>&1'.format(cmd.srcVmUri, shellquote(cmd.srcVmName),
                                                                storage_dir,
                                                                cmd.thumbprint, cmd.format, self._get_nbdkit_dir_path(), extra_params)

        if cmd.vddkVersion == '5.5' and not self._ndbkit_is_work():
            rsp.success = False
            rsp.error = "nbdkit with vddk 5.5 is not work, try to reconnect conversion host"
            return jsonobject.dumps(rsp)

        def detect_v2v_connection():
            # print information about the source guest and stop.
            # no convertion
            connection_test_cmd = "%s --print-source" % get_v2v_cmd(cmd, rsp)
            s = shell.ShellCmd(connection_test_cmd)
            s(False)
            if s.return_code == 0:
                return

            raise Exception('Failed to connect to host by conversion network address %s,' \
                ' check conversion network setttings. Details %s' % (cmd.srcHostIp, s.stderr))

        def dnat_to_convert_interface(ip, dnat_ip, dnat_interface):
            if shell.run("route -n |grep %s |grep %s" % (ip, dnat_interface)) != 0:
                shell.run("route add -host %s dev %s" % (ip, dnat_interface))

            if shell.run("iptables -t nat -nL --line-number | grep DNAT |grep %s | grep %s" % (ip, dnat_ip)) != 0:
                shell.run("iptables -t nat -A OUTPUT -d %s -j DNAT --to-destination %s" % (ip, dnat_ip))

        virt_v2v_cmd = get_v2v_cmd(cmd, rsp)
        src_vm_uri = cmd.srcVmUri
        host_name = src_vm_uri.split('/')[-1]
        if not linux.is_valid_hostname(host_name):
            rsp.success = False
            rsp.error = "cannot resolve hostname %s, check the hostname configured on the DNS server" % host_name
            return jsonobject.dumps(rsp)

        v2v_pid_path = os.path.join(storage_dir, "convert.pid")
        v2v_cmd_ret_path = os.path.join(storage_dir, "convert.ret")
        echo_pid_cmd = "echo $$ > %s; %s; ret=$?; echo $ret > %s; exit $ret" % (
        v2v_pid_path, virt_v2v_cmd, v2v_cmd_ret_path)

        vmware_host_ip = linux.get_host_by_name(host_name)
        convertInterface = linux.find_route_interface_by_destination_ip(cmd.srcHostIp)

        if vmware_host_ip != cmd.srcHostIp:
            # vmware_host_ip is management address of vcenter resources
            # cmd.srcHostIp is extra address matches conversion network 
            # IMPORTANT: configure a route interface and DNAT rule to route all converion traffic
            # from vmware_host_ip to srcHostIp
            dnat_to_convert_interface(vmware_host_ip, cmd.srcHostIp, convertInterface)

            # test connection to avoid conversion network misconfiguration
            detect_v2v_connection()

        if convertInterface:
            cmdstr = "tc filter replace dev %s protocol ip parent 1: prio 1 u32 match ip src %s/32 flowid 1:1" \
                     % (QOS_IFB, cmd.srcHostIp)
            shell.run(cmdstr)

        max_retry_times = 1
        retry_counter = [0]

        @linux.retry(times=max_retry_times+1, sleep_time=1)
        def run_convert_if_need():
            def do_run():
                save_pid()
                ret = shell.run(echo_pid_cmd)
                new_task.current_process_return_code = ret
                retry_if_needed(ret)
                return ret

            def retry_if_needed(ret):
                if ret == 0:
                    return

                if retry_counter[0] != max_retry_times and shell.run("grep -q 'guestfs_launch failed' %s" % log_path) == 0:
                    retry_counter[0] += 1
                    raise RetryException(
                        "launch guestfs failed, rerun v2v longjob %s" % cmd.longJobUuid)

            pid = linux.read_file(v2v_pid_path)
            log_path = "%s/virt_v2v_log" % storage_dir
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

            # delete password file
            passwd_file = os.path.join(storage_dir, "passwd")
            if os.path.exists(passwd_file):
                os.remove(passwd_file)

            ret = linux.read_file(v2v_cmd_ret_path)
            retry_if_needed(ret)
            return int(ret.strip() if ret else 126)

        if run_convert_if_need() != 0:
            v2v_log_file = "/tmp/v2v_log/%s-virt-v2v-log" % cmd.longJobUuid

            # create folder to save virt-v2v log
            tail_cmd = 'mkdir -p /tmp/v2v_log; tail -c 1M %s/virt_v2v_log > %s' % (storage_dir, v2v_log_file)
            shell.run(tail_cmd)
            with open(v2v_log_file, 'a') as fd:
                fd.write('\n>>> virt_v2v command: %s\n' % virt_v2v_cmd)

            rsp.success = False
            # Check if the v2v convert fails due to vCenter 5.5 bug: https://bugzilla.redhat.com/show_bug.cgi?id=1287681#c14
            ret = shell.call("grep -io 'File name .* refers to non-existing datastore .*' %s | tail -n 1" % v2v_log_file)
            if ret:
                rsp.error = ret.strip("\n") + ". This may be a bug in vCenter 5.5, please detach ISO in vSphere client and try again"
            else:
                err_fmt = linux.filter_file_lines_by_regex(v2v_log_file, '^virt-v2v: error:')[0][16:].strip()
                rsp.error = "failed to run virt-v2v command, because %s... for more details, please see log in conversion host: %s" % (
                err_fmt, v2v_log_file)

            return jsonobject.dumps(rsp)

        root_vol = (r"%s/%s-sda" % (storage_dir, cmd.srcVmName)).encode('utf-8')
        logger.debug(root_vol)
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
            data_vol = (r"%s/%s-sd%c" % (storage_dir, cmd.srcVmName, dev)).encode('utf-8')
            if os.path.exists(data_vol):
                aSize, vSize = self._get_qcow2_sizes(data_vol)
                rsp.dataVolumeInfos.append({"installPath": data_vol,
                                            "actualSize": aSize,
                                            "virtualSize": vSize,
                                            "deviceId": ord(dev) - ord('a')})
            else:
                break

        xml = (r"%s/%s.xml" % (storage_dir, cmd.srcVmName)).encode('utf-8')
        if self._check_str_in_file(xml, "<nvram "):
            rsp.bootMode = 'UEFI'

        def collect_time_cost():
            # [ 138.3] Copying disk 1/13 to
            # [ 408.1] Copying disk 2/13 to
            # ...
            # [1055.2] Copying disk 11/13 to
            # [1082.3] Copying disk 12/13 to
            # [1184.9] Copying disk 13/13 to
            # [1218.0] Finishing off
            # Copying disk is start time of copy, so also get finish off time for calculating last disk's time cost
            s = shell.ShellCmd("""awk -F"[][]" '/Copying disk|Finishing off/{print $2}' %s/virt_v2v_log""" % storage_dir)
            s(False)
            if s.return_code != 0:
                return

            times = s.stdout.split('\n')

            if len(times) < 2:
                return

            rsp.rootVolumeInfo['downloadTime'] = int(float(times[1]) - float(times[0]))
            times = times[1:]
            for i in xrange(0, len(rsp.dataVolumeInfos)):
                if i + 1 < len(times):
                    rsp.dataVolumeInfos[i]["downloadTime"] = int(float(times[i + 1]) - float(times[i]))

        try:
            collect_time_cost()
        except Exception as e:
            logger.debug("Failed to collect time cost, because %s" % e.message)

        return jsonobject.dumps(rsp)

    def _check_str_in_file(self, fname, txt):
        with open(fname) as dataf:
            return any(txt in line for line in dataf)

    @in_bash
    def _get_qcow2_sizes(self, path):
        cmd = "%s --output=json '%s'" % (qemu_img.subcmd('info'), path)
        _, output = commands.getstatusoutput(cmd)
        return long(json.loads(output)['actual-size']), long(json.loads(output)['virtual-size'])

    def clean_dnat(self, host_name, convert_ip):
        vmware_host_ip = linux.get_host_by_name(host_name)
        dnat_interface = linux.find_route_interface_by_destination_ip(convert_ip)
        if vmware_host_ip == convert_ip:
            return

        if shell.run("route -n |grep %s |grep %s" % (vmware_host_ip, dnat_interface)) == 0:
            shell.run("route del -host %s dev %s" % (vmware_host_ip, dnat_interface))

        if shell.run("iptables -t nat -nL --line-number | grep DNAT |grep %s | grep %s" % (vmware_host_ip, convert_ip)) == 0:
            nat_number = shell.call("iptables -t nat -nL --line-number | grep DNAT |grep %s | grep %s" % (vmware_host_ip, convert_ip)).split(" ")[0]
            shell.run("iptables -D OUTPUT %s -t nat" % nat_number)

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
        if cmd.needCleanDnat:
            self.clean_dnat(cmd.dnatInfo.hostName, cmd.dnatInfo.convertIp)
        linux.rm_dir_force(cleanUpPath)
        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def clean_convert(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        clean_up_path = os.path.join(cmd.storagePath, cmd.srcVmUuid)
        shell.run("pkill -9 -f '%s'" % clean_up_path)
        linux.rm_dir_force(clean_up_path)
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

        shell.run("modprobe ifb")
        iproute.set_link_up(QOS_IFB)

        if cmd.vCenterIps:
            interface_setup_rule = []

            def set_up_qos_rules(target_interface):
                # a bare number in tc class use bytes as unit
                config_qos_cmd = "tc qdisc add dev {0} ingress;" \
                                 "tc filter add dev {0} parent ffff: protocol ip u32 match " \
                                 "u32 0 0 flowid 1:1 action mirred egress redirect dev {1};" \
                                 "tc qdisc del dev {1} root >/dev/null 2>&1;" \
                                 "tc qdisc add dev {1} root handle 1: htb;" \
                                 "tc class add dev {1} parent 1: classid 1:1 htb rate {2} burst 100m" \
                                 .format(target_interface, QOS_IFB, cmd.inboundBandwidth)
                return shell.run(config_qos_cmd)

            for vcenter_ip in cmd.vCenterIps:
                interface = linux.find_route_interface_by_destination_ip(linux.get_host_by_name(vcenter_ip))

                if interface and interface not in interface_setup_rule:
                    if set_up_qos_rules(interface) == 0:
                        interface_setup_rule.append(interface)
                    else:
                        logger.debug("Failed to set up qos rules on interface %s" % interface)
                    continue

            list_url_cmd = shell.ShellCmd("ps aux | grep '[v]irt-v2v' | grep -v convert.ret | awk '{print $13}'")
            list_url_cmd(False)

            limited_interface = []
            if list_url_cmd.return_code == 0 and list_url_cmd.stdout:
                # will get a url format like
                # vpx://administrator%40vsphere.local@xx.xx.xx.xx/Datacenter-xxx/Cluster-xxx/127.0.0.1?no_verify=1
                for url in list_url_cmd.stdout.split('\n'):
                    vmware_host_ip = linux.get_host_by_name(url.split('/')[-1].split('?')[0])
                    interface = linux.find_route_interface_by_destination_ip(vmware_host_ip)

                    if interface:
                        cmdstr = "tc filter replace dev %s protocol ip parent 1: prio 1 u32 match ip src %s/32 flowid 1:1" \
                                 % (QOS_IFB, vmware_host_ip)
                        if shell.run(cmdstr) != 0:
                            logger.debug("Failed to set up tc filter on interface %s for ip %s"
                                         % (interface, vmware_host_ip))
                        else:
                            limited_interface.append(interface)

        return jsonobject.dumps(rsp)

    @in_bash
    @kvmagent.replyerror
    def delete_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentRsp()

        if cmd.vCenterIps:
            def delete_qos_rules(target_interface):
                if target_interface:
                    # delete ifb interface tc rules
                    cmdstr = "tc qdisc del dev %s root >/dev/null 2>&1" % QOS_IFB
                    shell.run(cmdstr)
                    # delete target interface tc rules
                    cmdstr = "tc qdisc del dev %s ingress >/dev/null 2>&1" % target_interface
                    shell.run(cmdstr)

            for vcenter_ip in cmd.vCenterIps:
                interface = linux.find_route_interface_by_destination_ip(linux.get_host_by_name(vcenter_ip))

                if interface:
                    delete_qos_rules(interface)

        return jsonobject.dumps(rsp)

import base64
import json
import time

import libvirt
import libvirt_qemu

import log

logger = log.get_logger(__name__)

"""
VM_OS_LINUX_DEBIAN = "debian"
VM_OS_LINUX_KYLIN = "kylin"
VM_OS_LINUX_UOS = "uos"
VM_OS_WINDOWS = "mswindows"
VM_OS_LINUX_SUPPORT = [VM_OS_LINUX_UBUNTU, VM_OS_LINUX_CENTOS, VM_OS_LINUX_DEBIAN, VM_OS_LINUX_KYLIN, VM_OS_LINUX_UOS]

ERROR_CODE_VM_NOT_RUNNING = 'VM_NOT_RUNNING'
ERROR_CODE_VM_CONFIG_IPV6_NOT_SUPPORT = 'VM_CONFIG_IPV6_NOT_SUPPORT'
ERROR_CODE_VM_CONFIG_NOT_EFFECTIVE_IP = 'VM_CONFIG_NOT_EFFECTIVE_NET_IP'
ERROR_CODE_VM_CONFIG_NOT_EFFECTIVE_GW = 'VM_CONFIG_NOT_EFFECTIVE_NET_GW'
ERROR_CODE_VM_CONFIG_NOT_EFFECTIVE_MTU = 'VM_CONFIG_NOT_EFFECTIVE_NET_MTU'
ERROR_CODE_VM_CONFIG_NOT_EFFECTIVE_DNS = 'VM_CONFIG_NOT_EFFECTIVE_NET_DNS'
ERROR_CODE_VM_CONFIG_PERSISTENCE_FAILED = 'VM_CONFIG_PERSISTENCE_FAILED'
ERROR_CODE_VM_CONFIG_INTERNAL = 'VM_CONFIG_INTERNAL'
ERROR_CODE_QGA_NOT_RUNNING = 'QGA_NOT_RUNNING'
ERROR_CODE_QGA_OS_NOT_SUPPORT = 'QGA_OS_NOT_SUPPORT'
ERROR_CODE_QGA_COMMAND_IS_DISABLED = 'QGA_COMMAND_IS_DISABLED'
ERROR_CODE_QGA_VERSION_TOO_LOWER = 'QGA_VERSION_TOO_LOWER'
ERROR_CODE_QGA_COMMAND_ERROR = 'QGA_COMMAND_EXEC_ERROR'
ERROR_CODE_QGA_RETURN_VALUE_ERROR = 'QGA_RETURN_VALUE_ERROR'

VM_CONFIG_SYNC_OS_VERSION_SUPPORT = {
    # VM_OS_LINUX_UBUNTU: ("16", "18", "20", "21", "22"),
    # VM_OS_LINUX_CENTOS: ("6", "7", "8"),
    VM_OS_LINUX_KYLIN: ("v10",),
    VM_OS_LINUX_UOS: ("20",)
}
"""
# qga command wait 30 seconds
qga_exec_wait_interval = 1
qga_exec_wait_retry = 30


class QgaException(Exception):
    """ The base exception class for all exceptions this agent raises."""

    def __init__(self, error_code, msg=None):
        self.error_code = error_code
        super(QgaException, self).__init__('QGA exception' if msg is None else msg)


class VmQga(object):
    QGA_STATE_RUNNING = "Running"
    QGA_STATE_NOT_RUNNING = "NotRunning"

    VM_OS_LINUX_KYLIN = "kylin"
    VM_OS_LINUX_UOS = "uos"
    VM_OS_LINUX_UBUNTU = "ubuntu"
    VM_OS_LINUX_CENTOS = "centos"
    VM_OS_LINUX_OPEN_SUSE = "opensuse-leap"
    VM_OS_LINUX_SUSE_S = "sles"
    VM_OS_LINUX_SUSE_D = "sled"
    VM_OS_LINUX_ORACLE = "ol"
    VM_OS_LINUX_REDHAT = "rhel"
    VM_OS_WINDOWS = "mswindows"

    ZS_TOOLS_PATN_WIN = "C:\Program Files\GuestTools\zs-tools\zs-tools.exe"

    def __init__(self, domain):
        self.domain = domain
        self.vm_uuid = domain.name()
        self.state = self.QGA_STATE_NOT_RUNNING
        self.version = None
        self.supported_commands = {}
        self.os = None
        self.os_version = None
        self.os_id_like = None
        self.qga_init()
        # self.qga_debug()

    '''
    def qga_debug(self):
        logger.debug('qga info: vm_uuid: %s\n state:%s\n version:%s\n os:%s\n os_version:%s\n supported_commands:%s' \
                     % (self.vm_uuid, self.state, self.version, self.os, self.os_version, self.supported_commands))
    '''

    def call_qga_command(self, command, args=None, timeout=3):
        """
        Execute QEMU-GA command and return result as dict or None on error

        command   the command to execute (string)
        args      arguments to the command (dict) or None
        :rtype: dict
        """
        if self.supported_commands:
            if command not in self.supported_commands:
                raise Exception('qga command {} not support, qga version is {}'.format(command, self.version))
            if not self.supported_commands[command]:
                raise Exception('qga command {} has been disabled'.format(command))

        cmd = {'execute': command}
        if args:
            if 'buf-b64' in args:
                args['buf-b64'] = base64.b64encode(args['buf-b64'])
            cmd['arguments'] = args
        cmd = json.dumps(cmd)
        try:
            ret = libvirt_qemu.qemuAgentCommand(self.domain, cmd,
                                                timeout, 0)
        except libvirt.libvirtError as e:
            message = 'exec qga command[{}] args[{}] error: {}'.format(cmd, args, e.message)
            raise Exception(message)

        try:
            logger.debug("vm {} run qga command {} result {}".format(self.vm_uuid, cmd, ret))
            
            parsed = json.loads(ret)
        except ValueError:
            raise Exception('qga command return value parsing error:{}'.format(ret))

        if 'return' not in parsed:
            raise Exception('qga command return value format error:{}'.format(ret))

        parsedRet = parsed['return']
        if isinstance(parsedRet, dict):
            if 'out-data' in parsedRet:
                parsedRet['out-data'] = base64.b64decode(parsedRet['out-data'])
            if 'err-data' in parsedRet:
                parsedRet['err-data'] = base64.b64decode(parsedRet['err-data'])
            if 'buf-b64' in parsedRet:
                parsedRet['buf-b64'] = base64.b64decode(parsedRet['buf-b64'])

        return parsedRet

    def guest_exec_status(self, pid):
        ret = self.call_qga_command("guest-exec-status", args={'pid': pid})
        if not ret or 'exited' not in ret:
            raise Exception('guest-exec-status exception')
        return ret

    def guest_exec(self, args):
        return self.call_qga_command("guest-exec", args=args)

    def guest_exec_bash_no_exitcode(self, cmd, exception=True, output=True):
        exitcode, ret_data = self.guest_exec_bash(cmd, output)
        if exitcode != 0:
            logger.debug("qga exec command: {}, exitcode {}, ret {}".format(cmd, exitcode, ret_data))
            if exception:
                raise Exception('cmd {}, exitcode {}, ret {}'
                                .format(cmd, exitcode, ret_data))
            return None
        return ret_data

    def guest_exec_bash(self, cmd, output=True, wait=qga_exec_wait_interval, retry=qga_exec_wait_retry):

        ret = self.guest_exec(
            {"path": "bash", "arg": ["-c", cmd], "capture-output": output})
        if ret and "pid" in ret:
            pid = ret["pid"]
        else:
            raise Exception('qga exec cmd {} failed for vm {}'.format(cmd, self.vm_uuid))

        if not output:
            logger.debug("run qga bash: {} failed, no output".format(cmd))
            return 0, None

        ret = None
        for i in range(retry):
            time.sleep(wait)
            ret = self.guest_exec_status(pid)
            # format: {"return":{"exited":false}}
            if ret['exited']:
                break

        if not ret or not ret.get('exited'):
            raise Exception('qga exec cmd {} timeout for vm {}'.format(cmd, self.vm_uuid))

        exit_code = ret.get('exitcode')
        ret_data = None
        if 'out-data' in ret:
            ret_data = ret['out-data']
        elif 'err-data' in ret:
            ret_data = ret['err-data']

        return exit_code, ret_data

    # not a good function, just for hurry push
    def guest_exec_python(self, file, params=None, output=True, wait=qga_exec_wait_interval, retry=qga_exec_wait_retry):
        path = self.guest_exec_bash_no_exitcode("which python2", exception=False)
        if not path:
            path = self.guest_exec_bash_no_exitcode("which python3", exception=False)

        if not path:
            raise Exception('python not installed in vm {}'.format(file, self.vm_uuid))

        args = [file]
        if params is not None:
            for d in params:
                args.append(d)

        ret = self.guest_exec(
            {"path": path.strip(), "arg": args, "capture-output": output})
        if ret and "pid" in ret:
            pid = ret["pid"]
        else:
            raise Exception('qga exec cmd {} failed for vm {}'.format(file, self.vm_uuid))

        if not output:
            logger.debug("run qga python: {} failed, no output".format(file))
            return 0, None

        ret = None
        for i in range(retry):
            time.sleep(wait)
            ret = self.guest_exec_status(pid)
            # format: {"return":{"exited":false}}
            if ret['exited']:
                break

        if not ret or not ret.get('exited'):
            raise Exception('qga exec cmd {} timeout for vm {}'.format(file, self.vm_uuid))

        exit_code = ret.get('exitcode')
        ret_data = None
        if 'out-data' in ret:
            ret_data = ret['out-data']
            res = json.loads(ret_data)
            exit_code = 0 if res.get('result') == "success" else 1
        elif 'err-data' in ret:
            exit_code = 1
            ret_data = ret['err-data']

        return exit_code, ret_data

    def guest_exec_zs_tools(self, operate, config, output=True, wait=qga_exec_wait_interval, retry=qga_exec_wait_retry):
        if operate == 'net':
            ret = self.guest_exec(
                {"path": self.ZS_TOOLS_PATN_WIN, "arg": [operate, "--config", config], "capture-output": output})
            if ret and "pid" in ret:
                pid = ret["pid"]
            else:
                raise Exception('qga exec zs-tools operate {} config {} failed for vm {}'.format(operate, config, self.vm_uuid))
        else:
            raise Exception('qga exec zs-tools unknow operate {} for vm {}'.format(operate, self.vm_uuid))

        ret = None
        for i in range(retry):
            time.sleep(wait)
            ret = self.guest_exec_status(pid)
            if ret['exited']:
                break

        if not ret or not ret.get('exited'):
            raise Exception('qga exec zs-tools operate {} config {} timeout for vm {}'.format(operate, config, self.vm_uuid))

        exit_code = ret.get('exitcode')
        ret_data = None
        if 'out-data' in ret:
            ret_data = ret['out-data'].decode('utf-8').encode('utf-8')
        elif 'err-data' in ret:
            ret_data = ret['err-data'].decode('utf-8').encode('utf-8')

        return exit_code, ret_data.replace('\r\n', '')

    def guest_exec_powershell(self, cmd, output=True, wait=qga_exec_wait_interval, retry=qga_exec_wait_retry):

        ret = self.guest_exec(
            {"path": "powershell.exe", "arg": ["-Command", cmd], "capture-output": output})
        if ret and "pid" in ret:
            pid = ret["pid"]
        else:
            raise Exception('qga exec cmd {} failed for vm {}'.format(cmd, self.vm_uuid))

        if not output:
            logger.debug("run qga powershell: {} failed, no output".format(cmd))
            return 0, None

        ret = None
        for i in range(retry):
            time.sleep(wait)
            ret = self.guest_exec_status(pid)
            if ret['exited']:
                break

        if not ret or not ret.get('exited'):
            raise Exception('qga exec cmd {} timeout for vm {}'.format(cmd, self.vm_uuid))

        exit_code = ret.get('exitcode')
        ret_data = None
        if 'out-data' in ret:
            ret_data = ret['out-data'].decode("GB2312")
        elif 'err-data' in ret:
            ret_data = ret['err-data'].decode("GB2312")

        return exit_code, ret_data

    def guest_exec_powershell_no_exitcode(self, cmd, exception=True, output=True):
        exitcode, ret_data = self.guest_exec_powershell('& "{}"'.format(cmd), output)
        if exitcode != 0:
            if exception:
                raise Exception('cmd {}, exitcode {}, ret {}'
                                .format(cmd, exitcode, ret_data))
            return None
        return ret_data

    def guest_exec_cmd_no_exitcode(self, cmd, exception=True, output=True):
        if "mswindows" in self.os:
            return self.guest_exec_powershell_no_exitcode(cmd, exception, output)
        else:
            return self.guest_exec_bash_no_exitcode(cmd, exception, output)

    def guest_info(self):
        """
        {"return":{
                "version":"2.12.0",
                "supported_commands":[
                    {"enabled":true,"name":"guest-get-osinfo","success-response":true},
                    {"enabled":true,"name":"guest-get-timezone","success-response":true},
                    {"enabled":true,"name":"guest-get-users","success-response":true},
                    {"enabled":true,"name":"guest-get-host-name","success-response":true},
                    {"enabled":true,"name":"guest-exec","success-response":true},
                    {"enabled":true,"name":"guest-exec-status","success-response":true},
                    {"enabled":true,"name":"guest-get-memory-block-info","success-response":true},
                    {"enabled":true,"name":"guest-set-memory-blocks","success-response":true},
                    {"enabled":true,"name":"guest-get-memory-blocks","success-response":true},
                    {"enabled":true,"name":"guest-set-user-password","success-response":true},
                    {"enabled":true,"name":"guest-get-fsinfo","success-response":true},
                    {"enabled":true,"name":"guest-set-vcpus","success-response":true},
                    {"enabled":true,"name":"guest-get-vcpus","success-response":true},
                    {"enabled":true,"name":"guest-network-get-interfaces","success-response":true},
                    {"enabled":true,"name":"guest-suspend-hybrid","success-response":false},
                    {"enabled":true,"name":"guest-suspend-ram","success-response":false},
                    {"enabled":true,"name":"guest-suspend-disk","success-response":false},
                    {"enabled":true,"name":"guest-fstrim","success-response":true},
                    {"enabled":true,"name":"guest-fsfreeze-thaw","success-response":true},
                    {"enabled":true,"name":"guest-fsfreeze-freeze-list","success-response":true},
                    {"enabled":true,"name":"guest-fsfreeze-freeze","success-response":true},
                    {"enabled":true,"name":"guest-fsfreeze-status","success-response":true},
                    {"enabled":true,"name":"guest-file-flush","success-response":true},
                    {"enabled":true,"name":"guest-file-seek","success-response":true},
                    {"enabled":true,"name":"guest-file-write","success-response":true},
                    {"enabled":true,"name":"guest-file-read","success-response":true},
                    {"enabled":true,"name":"guest-file-close","success-response":true},
                    {"enabled":true,"name":"guest-file-open","success-response":true},
                    {"enabled":true,"name":"guest-shutdown","success-response":false},
                    {"enabled":true,"name":"guest-info","success-response":true},
                    {"enabled":true,"name":"guest-set-time","success-response":true},
                    {"enabled":true,"name":"guest-get-time","success-response":true},
                    {"enabled":true,"name":"guest-ping","success-response":true},
                    {"enabled":true,"name":"guest-sync","success-response":true},
                    {"enabled":true,"name":"guest-sync-delimited","success-response":true}]}}
        """
        return self.call_qga_command("guest-info")

    def guest_ping(self):
        ret = self.call_qga_command("guest-ping")
        return ret

    def guest_agent_available(self):
        try:
            ret = self.guest_ping()
            if ret is None:
                return False
            return True
        except:
            return False

    def guest_exec_get_os_info(self):
        """
        {"name":"CentOS Linux",
        "kernel-release":"3.10.0-957.el7.x86_64",
        "version":"7 (Core)",
        "pretty-name":"CentOS Linux 7 (Core)",
        "version-id":"7",
        "kernel-version":"#1 SMP Thu Nov 8 23:39:32 UTC 2018",
        "machine":"x86_64",
        "id":"centos" }
        """
        ret = self.call_qga_command("guest-get-osinfo")
        if ret and "id" in ret and "version-id" in ret:
            vm_os = ret["id"].lower()
            version = ret["version-id"].lower().split(".")[0]
            return vm_os, version
        raise Exception('get vm %s os info failed' % self.vm_uuid)

    def guest_get_os_id_like(self):
        """
        # cat /etc/os-release
            NAME="CentOS Linux"
            VERSION="7 (Core)"
            ID="centos"
            ID_LIKE="rhel fedora"
            VERSION_ID="7"
            PRETTY_NAME="CentOS Linux 7 (Core)"
            ANSI_COLOR="0;31"
            CPE_NAME="cpe:/o:centos:centos:7"
            HOME_URL="https://www.centos.org/"
            BUG_REPORT_URL="https://bugs.centos.org/"

            CENTOS_MANTISBT_PROJECT="CentOS-7"
            CENTOS_MANTISBT_PROJECT_VERSION="7"
            REDHAT_SUPPORT_PRODUCT="centos"
            REDHAT_SUPPORT_PRODUCT_VERSION="7"
        """
        ret = self.guest_exec_bash_no_exitcode('cat /etc/os-release | grep ID_LIKE', exception=False)
        if ret:
            info = ret.split("=")
            return info[1] if len(info) > 1 else None
        return None

    def guest_get_os_info(self):
        ret = self.guest_exec_bash_no_exitcode('cat /etc/os-release')
        if not ret:
            raise Exception('get os info failed')

        lines = [line for line in ret.split('\n') if line != ""]
        config = {}
        for line in lines:
            if line.startswith('#'):
                continue

            info = line.split('=')
            if len(info) != 2:
                continue
            config[info[0].strip()] = info[1].strip().strip('"')

        vm_os = config.get('ID')
        version = config.get('VERSION_ID')
        if vm_os and version and vm_os == self.VM_OS_LINUX_UBUNTU:
            version = version.split(".")[0]

        return vm_os, version, config.get('ID_LIKE')

    def qga_init(self):
        self.state = self.QGA_STATE_NOT_RUNNING
        if self.domain.isActive() and self.guest_agent_available():
            self.state = self.QGA_STATE_RUNNING

        if self.state != self.QGA_STATE_RUNNING:
            return

        ret = self.guest_info()
        if ret:
            self.version = ret["version"]
            supported_commands = ret["supported_commands"]
            self.supported_commands = {cmd["name"]: cmd["enabled"] for cmd in supported_commands}

        try:
            if 'guest-get-osinfo' in self.supported_commands and \
                    self.supported_commands['guest-get-osinfo']:
                self.os, self.os_version = self.guest_exec_get_os_info()
                if self.os == VmQga.VM_OS_WINDOWS:
                    self.os_id_like = "windows"
                else:
                    self.os_id_like = self.guest_get_os_id_like()
            else:
                self.os, self.os_version, self.os_id_like = self.guest_get_os_info()
        except Exception as e:
            logger.debug("qga init failed {}".format(e))

    """
    def guest_get_hostname(self):
        ret = self.call_qga_command("guest-get-host-name")
        if ret and 'host-name' in ret:
            return ret['host-name']
        else:
            raise QgaException(ERROR_CODE_QGA_RETURN_VALUE_ERROR, 'qga get hostname failed for vm %s' % self.vm_uuid)
    """

    def guest_file_open(self, path, create=False):
        if create:
            mode = "w+"
        else:
            mode = "r"
        return self.call_qga_command("guest-file-open", args={"path": path, "mode": mode})

    def guest_file_close(self, handle):
        return self.call_qga_command("guest-file-close", args={"handle": handle})

    def guest_file_flush(self, handle):
        return self.call_qga_command("guest-file-flush", args={"handle": handle})

    def guest_file_read(self, path, not_exist_exception=False):
        try:
            handle = self.call_qga_command("guest-file-open", args={"path": path, "mode": 'r'})
        except Exception as e:
            if 'No such file' in e.message and not not_exist_exception:
                return 0, None
            raise e

        data_b64 = ''
        total_count = 0

        try:
            while True:
                ret = self.call_qga_command("guest-file-read", args={"handle": handle})
                data_b64 += ret.get('buf-b64')
                total_count += ret.get('count')
                if ret.get('count') == 0:
                    break
        finally:
            self.guest_file_close(handle)
        return total_count, data_b64

    def guest_file_is_exist(self, path):
        try:
            handle = self.call_qga_command("guest-file-open", args={"path": path, "mode": 'r'})
        except Exception as e:
            if 'No such file' in e.message:
                return False
            else:
                raise e

        self.guest_file_close(handle)
        return True

    def guest_file_write(self, path, contents):
        handle = self.guest_file_open(path, True)
        try:
            ret = self.call_qga_command("guest-file-write", args={"handle": handle, "buf-b64": contents})
        finally:
            self.guest_file_close(handle)
        return ret.get('count')

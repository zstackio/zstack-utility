import time
import libvirt
import libvirt_qemu
import json
import base64

# logger = log.get_logger(__name__)

VM_OS_LINUX_UBUNTU = "ubuntu"
VM_OS_LINUX_CENTOS = "centos"
VM_OS_LINUX_DEBIAN = "debian"
VM_OS_LINUX_KYLIN = "kylin"
VM_OS_LINUX_UOS = "uos"
VM_OS_WINDOWS = "mswindows"
VM_OS_LINUX_LIST = [VM_OS_LINUX_UBUNTU, VM_OS_LINUX_CENTOS, VM_OS_LINUX_DEBIAN, VM_OS_LINUX_KYLIN, VM_OS_LINUX_UOS]

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
    VM_OS_LINUX_UBUNTU: ("16", "18", "20", "21", "22"),
    VM_OS_LINUX_CENTOS: ("6", "7", "8"),
    VM_OS_LINUX_KYLIN: ("v10",),
    VM_OS_LINUX_UOS: ("20",)
}


class QgaException(Exception):
    """ The base exception class for all exceptions this agent raises."""

    def __init__(self, error_code, msg=None):
        self.error_code = error_code
        super(QgaException, self).__init__('QGA exception' if msg is None else msg)


class Qga(object):
    QGA_STATE_UNKNOWN = "Unknown"
    QGA_STATE_RUNNING = "Running"
    QGA_STATE_NOT_RUNNING = "NotRunning"

    def __init__(self, domain):
        self.domain = domain
        self.vm_uuid = domain.name()
        self.state = Qga.QGA_STATE_NOT_RUNNING
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
                raise QgaException(ERROR_CODE_QGA_VERSION_TOO_LOWER, 'qga command {} not support, qga version is {}'
                                   .format(command, self.version))
            if not self.supported_commands[command]:
                raise QgaException(ERROR_CODE_QGA_COMMAND_IS_DISABLED, 'qga command {} has been disabled'
                                   .format(command))

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
            raise QgaException(ERROR_CODE_QGA_COMMAND_ERROR, message)

        try:
            parsed = json.loads(ret)
        except ValueError:
            raise QgaException(ERROR_CODE_QGA_RETURN_VALUE_ERROR,
                               'qga command return value parsing error:{}'.format(ret))

        if 'return' not in parsed:
            raise QgaException(ERROR_CODE_QGA_RETURN_VALUE_ERROR,
                               'qga command return value format error:{}'.format(ret))

        parsedRet = parsed['return']
        if isinstance(parsedRet, dict):
            if 'out-data' in parsedRet:
                parsedRet['out-data'] = base64.b64decode(parsedRet['out-data'])  # .decode("GB2312")
            if 'err-data' in parsedRet:
                parsedRet['err-data'] = base64.b64decode(parsedRet['err-data'])  # .decode("GB2312")
            if 'buf-b64' in parsedRet:
                parsedRet['buf-b64'] = base64.b64decode(parsedRet['buf-b64'])

        return parsedRet

    def guest_exec_status(self, pid):
        return self.call_qga_command("guest-exec-status", args={'pid': pid})

    def guest_exec(self, args):
        return self.call_qga_command("guest-exec", args=args)

    def guest_exec_bash_no_exitcode(self, cmd, exception=True, output=True, wait=0.1):
        exitcode, ret_data = self.guest_exec_bash(cmd, output, wait)
        if exitcode != 0:
            if exception:
                raise QgaException(ERROR_CODE_QGA_COMMAND_ERROR, 'cmd {}, exitcode {}, ret {}'
                                   .format(cmd, exitcode, ret_data))
            return None
        return ret_data

    def guest_exec_bash(self, cmd, output=True, wait=0.1):

        ret = self.guest_exec(
            {"path": "bash", "arg": ["-c", cmd], "capture-output": output})
        if ret and "pid" in ret:
            pid = ret["pid"]
        else:
            raise QgaException(ERROR_CODE_QGA_RETURN_VALUE_ERROR,
                               'qga exec cmd {} failed for vm {}'.format(cmd, self.vm_uuid))

        if not output:
            return 0, None

        time.sleep(wait)
        ret = self.guest_exec_status(pid)
        if not ret or 'exited' not in ret:
            raise QgaException(ERROR_CODE_QGA_RETURN_VALUE_ERROR,
                               'qga exec cmd {} failed for vm {}'.format(cmd, self.vm_uuid))

        # format: {"return":{"exited":false}}
        if not ret['exited']:
            raise QgaException(ERROR_CODE_QGA_COMMAND_ERROR,
                               'qga exec cmd {} timeout for vm {}'.format(cmd, self.vm_uuid))

        exit_code = ret.get('exitcode')
        ret_data = None
        if 'out-data' in ret:
            ret_data = ret['out-data']
        elif 'err-data' in ret:
            ret_data = ret['err-data']
        return exit_code, ret_data

    def guest_info(self):
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
        ret = self.call_qga_command("guest-get-osinfo")
        if ret and "id" in ret and "version-id" in ret:
            vm_os = ret["id"].lower()
            version = ret["version-id"].lower()
            if vm_os == VM_OS_LINUX_UBUNTU:
                version = version.split(".")[0]
            return vm_os, version
        raise QgaException(ERROR_CODE_QGA_RETURN_VALUE_ERROR,
                           'get vm %s os info failed' % self.vm_uuid)

    def guest_get_os_id_like(self):
        ret = self.guest_exec_bash_no_exitcode('cat /etc/os-release | grep ID_LIKE', exception=False)
        if ret:
            info = ret.split("=")
            return info[1] if len(info) > 1 else None
        return None

    def guest_get_os_info(self):
        ret = self.guest_exec_bash_no_exitcode('cat /etc/os-release')
        if not ret:
            raise QgaException(ERROR_CODE_QGA_COMMAND_ERROR, 'get os info failed')

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
        if vm_os and version and vm_os == VM_OS_LINUX_UBUNTU:
            version = version.split(".")[0]

        return vm_os, version, config.get('ID_LIKE')

    def qga_init(self):
        if not self.domain.isActive():
            self.state = Qga.QGA_STATE_NOT_RUNNING
            return

        self.state = Qga.QGA_STATE_RUNNING if self.guest_agent_available() else Qga.QGA_STATE_NOT_RUNNING
        if self.state != Qga.QGA_STATE_RUNNING:
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
                self.os_id_like = self.guest_get_os_id_like()
            else:
                self.os, self.os_version, self.os_id_like = self.guest_get_os_info()
        except QgaException as e:
            if e.error_code in (ERROR_CODE_QGA_COMMAND_IS_DISABLED, ERROR_CODE_QGA_VERSION_TOO_LOWER):
                self.os, self.os_version, self.os_id_like = 'Unknown', 'Unknown', 'Unknown'
            else:
                raise e

    def guest_get_hostname(self):
        ret = self.call_qga_command("guest-get-host-name")
        if ret and 'host-name' in ret:
            return ret['host-name']
        else:
            raise QgaException(ERROR_CODE_QGA_RETURN_VALUE_ERROR, 'qga get hostname failed for vm %s' % self.vm_uuid)

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

        try:
            ret = self.call_qga_command("guest-file-read", args={"handle": handle})
        finally:
            self.guest_file_close(handle)
        return ret.get('count'), ret.get('buf-b64')

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

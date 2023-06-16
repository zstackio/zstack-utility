
import bash
import os
import log
import jsonobject
import shell
from linux import get_vm_pid, HOST_ARCH

logger = log.get_logger(__name__)

def get_colo_path():
    return '/var/lib/zstack/colo/qemu-system-x86_64'

def get_path():
    if os.path.exists('/usr/libexec/qemu-kvm'):
        return '/usr/libexec/qemu-kvm'
    elif os.path.exists('/bin/qemu-kvm'):
        return '/bin/qemu-kvm'
    elif os.path.exists('/usr/bin/qemu-system-{}'.format(HOST_ARCH)):
        return '/usr/bin/qemu-system-{}'.format(HOST_ARCH)
    else:
        raise Exception(
            'Could not find qemu-kvm in /bin/qemu-kvm or /usr/libexec/qemu-kvm or /usr/bin/qemu-system-{}'
            % HOST_ARCH)


def get_version():
    version = shell.call("virsh version | awk '/hypervisor.*QEMU/{print $4}'", False).strip()

    # failed to get qemu version, fallback to get its version from path
    if version == "":
        return get_version_from_exe_file2(get_path())

    return version


def get_running_version(vm_uuid):
    pid = get_vm_pid(vm_uuid)
    if pid:
        exe = "/proc/%s/exe" % pid
        r, o, e = bash.bash_roe("%s --version" % exe)
        if r == 0:
            return _parse_version(o.strip())
        logger.debug("cannot get version from %s: %s" % (exe, e))

    r, o, e = bash.bash_roe("""virsh qemu-monitor-command %s '{"execute":"query-version"}'""" % vm_uuid)
    if r == 0:
        ret = jsonobject.loads(o.strip())
        if ret["return"].package:
            return _parse_version(ret["return"].package)
        else:
            qv = ret["return"].qemu
            return "%d.%d.%d" % (qv.major, qv.minor, qv.micro)

    logger.debug("cannot get vm[uuid:%s] version from qmp: %s" % (vm_uuid, e))
    return _parse_version(shell.call("%s --version" % get_path()))

# QEMU emulator version 2.12.0 (qemu-kvm-ev-2.12.0-44.1.el7_9.1)
# return qemu-kvm-ev-2.12.0-44.1.el7_9.1
def get_version_from_exe_file(path, error_out=False):
    r, o, e = bash.bash_roe("%s --version" % path)
    if r == 0:
        return _parse_version(o.strip())

    if error_out:
        raise Exception("cannot get version from %s: %s" % (path, e))
    else:
        logger.debug("cannot get version from %s: %s" % (path, e))

    return ""

# QEMU emulator version 2.12.0 (qemu-kvm-ev-2.12.0-44.1.el7_9.1)
# return 2.12.0
def get_version_from_exe_file2(path, error_out=False):
    r, o, e = bash.bash_roe("%s --version" % path)
    if r == 0:
        return _parse_version2(o.strip())

    if error_out:
        raise Exception("cannot get version from %s: %s" % (path, e))
    else:
        logger.debug("cannot get version from %s: %s" % (path, e))

    return ""

# QEMU emulator version 2.12.0 (qemu-kvm-ev-2.12.0-44.1.el7_9.1)
# return qemu-kvm-ev-2.12.0-44.1.el7_9.1
def _parse_version(version_output):
    lines = version_output.splitlines()
    ver_line = lines[0].strip()

    for line in lines:
        if line.lower().startswith("qemu"):
            ver_line = line.strip()
            break

    if "(" in ver_line:
        full_ver = ver_line.split("(", 1)[1].split(")", 1)[0]
    else:
        full_ver = ver_line

    return "-".join(filter(lambda s: s[0].isdigit(), full_ver.split("-")))

# QEMU emulator version 2.12.0 (qemu-kvm-ev-2.12.0-44.1.el7_9.1)
# return 2.12.0
def _parse_version2(version_output):
    return version_output.splitlines()[0].strip().split(" ")[3]


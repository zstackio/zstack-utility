import os
import re
import shell
from linux import get_vm_pid, HOST_ARCH

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
    return shell.call("virsh version | awk '/hypervisor.*QEMU/{print $4}'").strip()


def get_running_version(vm_uuid):
    pid = get_vm_pid(vm_uuid)
    if pid:
        exe = "/proc/%s/exe" % pid
    else:
        exe = get_path()
    return _parse_version(shell.call("%s --version" % exe))


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


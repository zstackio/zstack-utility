
import os
import os.path
import pipes
import re

from zstacklib.utils import bash, log

logger = log.get_logger(__name__)

# /var/lib/libvirt/qemu/nvram/{vm_uuid} is a folder for NvRam type volume
def build_nvram_mount_folder_path(vm_uuid):
    # type: (str) -> str
    return "/var/lib/libvirt/qemu/nvram/%s" % vm_uuid

def build_nvram_vm_host_file_path(vm_uuid):
    # type: (str) -> str
    return "/var/lib/libvirt/qemu/nvram/%s-host-files/%s.fd" % (vm_uuid, vm_uuid)

def build_nvram_delete_token_file_path(vm_uuid):
    # type: (str) -> str
    return "/var/lib/libvirt/qemu/nvram/%s-host-files/delete" % (vm_uuid)

def extract_vm_uuid_from_nvram_vm_host_file_path(path):
    # type: (str) -> str
    if not path:
        return ''
    uuid_pattern = r'[a-fA-F0-9]{8}[a-fA-F0-9]{4}[a-fA-F0-9]{4}[a-fA-F0-9]{4}[a-fA-F0-9]{12}'
    pattern = r'^/var/lib/libvirt/qemu/nvram/({0})-host-files/({0})\.fd(\.snapshot-backup)?$'.format(uuid_pattern)
    match = re.match(pattern, path)
    if not match:
        return ''
    uuid1 = match.group(1)
    uuid2 = match.group(2)
    return uuid1 if uuid1.lower() == uuid2.lower() else ''

def check_nvram_vm_host_file_path_format(path):
    # type: (str) -> bool
    return bool(extract_vm_uuid_from_nvram_vm_host_file_path(path))

def find_source_path_by_mount_folder(mount_folder):
    # type: (str) -> str
    device_node = ''
    if not os.path.exists('/proc/self/mountinfo'):
        return ''

    # /var/lib/libvirt/qemu/nvram/{vm_uuid}  =>  /dev/loop0 or /dev/xxx/yyy
    with open('/proc/self/mountinfo', 'r') as f:
        for line in f:
            # format: ID  Parent Major:Minor Root MountPoint                       Options ... - Type Source     Permission
            # ex:     123 45     7:0         /    /var/lib/libvirt/qemu/nvram/uuid rw      ... - ext4 /dev/loop0 rw
            parts = line.split()
            if len(parts) > 4 and parts[4] == mount_folder:
                try:
                    sep_index = parts.index('-')
                    device_node = parts[sep_index + 2] # ex: '/dev/loop0'
                except (ValueError, IndexError):
                    continue
                break

    return device_node

def find_mount_folder_by_source_path(source_path):
    # type: (str) -> str
    # /dev/loop0  =>  /var/lib/libvirt/qemu/nvram/{vm_uuid}
    mount_folder = ''
    if os.path.exists('/proc/self/mountinfo'):
        with open('/proc/self/mountinfo', 'r') as f:
            for line in f:
                parts = line.split()
                try:
                    sep_index = parts.index('-')
                    source_device = parts[sep_index + 2]
                    if source_device == source_path:
                        mount_folder = parts[4]
                        break
                except (ValueError, IndexError):
                    continue

    return mount_folder

def umount_nvram_folder(mount_path):
    # type: (str) -> None
    is_mounted = False
    if os.path.exists('/proc/mounts'):
        with open('/proc/mounts', 'r') as f:
            is_mounted = any(
                len(parts) >= 2 and parts[1] == mount_path
                for parts in (line.split() for line in f)
            )

    if is_mounted:
        ret = bash.bash_r("umount %s" % pipes.quote(mount_path))
        if ret != 0:
            bash.bash_r("umount -l %s" % pipes.quote(mount_path))

def extract_vm_uuid_from_nvram_mount_folder_path(nvram_mount_folder_path):
    # type: (str) -> str
    return os.path.basename(nvram_mount_folder_path.rstrip('/'))

def is_nvram_install_path(install_path):
    # type: (str) -> bool
    # install_path format is ".../nvRam/acct-{account_uuid}/vol-{volume_uuid}/{volume_uuid}.raw"
    normalized_path = os.path.normpath(install_path)
    path_parts = normalized_path.split(os.sep)
    if len(path_parts) >= 4:
        return path_parts[-4] == 'nvRam'
    return False

def make_ext4_nvram_filesystem(nvram_install_path):
    # type: (str) -> None
    cmd = "mkfs.ext4 -F -L VM_NVRAM %s" % pipes.quote(nvram_install_path)
    ret = bash.bash_r(cmd) # type: int
    if ret != 0:
        raise Exception("Failed to format ext4 on %s" % nvram_install_path)

def check_raw_has_file_system(nvram_install_path):
    # type: (str) -> bool
    lines = bash.bash_o("blkid -p -o export %s" % pipes.quote(nvram_install_path)).splitlines() # type: list[str]
    info = {}
    for line in lines:
        if '=' in line:
            k, v = line.split('=', 1)
            info[k.strip()] = v.strip()
    is_ext4 = info.get('TYPE') == 'ext4'
    is_label_ok = info.get('LABEL') == 'VM_NVRAM'
    is_fs = info.get('USAGE') == 'filesystem'
    return is_ext4 and is_label_ok and is_fs

def prepare_vm_nvram_folder(source_path, mount_path):
    # type: (str, str) -> None
    if not os.path.exists(mount_path):
        ret = bash.bash_r("mkdir -p %s" % pipes.quote(mount_path))
        if ret != 0:
            raise Exception("failed to create nvram mount directory %s" % mount_path)

    is_mounted = False
    if os.path.exists('/proc/mounts'):
        with open('/proc/mounts', 'r') as f:
            is_mounted = any(
                len(parts) >= 2 and parts[1] == mount_path
                for parts in (line.split() for line in f)
            )

    if not is_mounted:
        ret = bash.bash_r("mount -t ext4 %s %s" % (pipes.quote(source_path), pipes.quote(mount_path)))
        if ret != 0:
            raise Exception("failed to mount %s to %s" % (source_path, mount_path))

    ret, _, e = bash.bash_roe("chmod 750 %s" % pipes.quote(mount_path))
    if ret != 0:
        logger.warn("failed to chmod %s when prepare nvram folder: %s" % (mount_path, e))
    ret, _, e = bash.bash_roe("chown qemu:qemu %s" % pipes.quote(mount_path))
    if ret != 0:
        logger.warn("failed to chown %s when prepare nvram folder: %s" % (mount_path, e))

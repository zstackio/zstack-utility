
import glob
import os
import os.path
import pipes

from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

class LocalNvRamVmExtensions(object):
    def __init__(self):
        self.nvram_volume = None
        self.vm_uuid = ''
        self.nvram_install_path = ''

    def prepare_nvram_before_vm_start(self):
        if self.vm_uuid == '':
            raise Exception("invalid vm_uuid: %s" % self.vm_uuid)
        if not self.nvram_install_path and self.nvram_volume is not None:
            self.nvram_install_path = self.nvram_volume.installPath  # type: str
        if not self.nvram_install_path:
            raise Exception("nvram_install_path is not set")

        loop_device_path = find_loop_device_path_by_nvram_install_path(self.nvram_install_path)
        if loop_device_path is None:
            loop_device_path = self._make_nvram_to_block_device()

        if not self._check_raw_has_file_system():
            self._make_ext4_nvram_filesystem()

        self._prepare_vm_nvram_folder(loop_device_path)

    def _make_nvram_to_block_device(self):
        cmd = "losetup --find --show %s" % pipes.quote(self.nvram_install_path)
        loop_dev = bash.bash_o(cmd).strip() # type: str
        if not loop_dev:
            raise Exception("Failed to setup loop device for %s" % self.nvram_install_path)
        return loop_dev

    def _check_raw_has_file_system(self):
        lines = bash.bash_o("blkid -p -o export %s" % pipes.quote(self.nvram_install_path)).splitlines() # type: str
        info = {}
        for line in lines:
            if '=' in line:
                k, v = line.split('=', 1)
                info[k.strip()] = v.strip()
        is_ext4 = info.get('TYPE') == 'ext4'
        is_label_ok = info.get('LABEL') == 'VM_NVRAM'
        is_fs = info.get('USAGE') == 'filesystem'
        return is_ext4 and is_label_ok and is_fs

    def _make_ext4_nvram_filesystem(self):
        cmd = "mkfs.ext4 -F -L VM_NVRAM %s" % pipes.quote(self.nvram_install_path)
        ret = bash.bash_r(cmd) # type: str
        if ret != 0:
            raise Exception("Failed to format ext4 on %s" % self.nvram_install_path)

    def _prepare_vm_nvram_folder(self, loop_device_path):
        '''
        :type loop_device_path: str
        '''
        mount_path = "/var/lib/libvirt/qemu/nvram/%s" % self.vm_uuid

        if not os.path.exists(mount_path):
            bash.bash_r("mkdir -p %s" % pipes.quote(mount_path))

        is_mounted = False
        with open('/proc/mounts', 'r') as f:
            is_mounted = any(
                len(parts) >= 2 and parts[1] == mount_path
                for parts in (line.split() for line in f)
            )

        if not is_mounted:
            ret = bash.bash_r("mount -t ext4 %s %s" % (pipes.quote(loop_device_path), pipes.quote(mount_path)))
            if ret != 0:
                raise Exception("failed to mount %s to %s" % (loop_device_path, mount_path))

        bash.bash_r("chmod 750 %s" % pipes.quote(mount_path))
        bash.bash_r("chown qemu:qemu %s" % pipes.quote(mount_path))

    def cleanup_nvram_after_vm_stop(self):
        if self.vm_uuid == '':
            if self.nvram_install_path == '':
                raise Exception('vm_uuid and nvram_install_path in LocalNvRamVmExtensions cannot both be empty.')
            self.vm_uuid = find_vm_uuid_by_nvram_install_path(self.nvram_install_path)
        else:
            if self.nvram_install_path == '':
                self.nvram_install_path = find_nvram_install_path_by_mount_folder(self.vm_uuid)

        # if save in nvram/{vm_uuid}.fd, it will be delete
        fd_path = "/var/lib/libvirt/qemu/nvram/%s.fd" % self.vm_uuid
        linux.rm_file_checked(fd_path)

        if self.vm_uuid:
            mount_folder = build_nvram_mount_folder_path(self.vm_uuid)
            if os.path.exists(mount_folder):
                # DO NOT delete nvram raw file: it will save in local primary storage
                # MN will delete nvram volume by other command if needed
                self._umount_nvram_folder(mount_folder)
            if self.nvram_install_path:
                self._detach_loop_device()
            if os.path.exists(mount_folder): # double check after umount
                bash.bash_r("rmdir %s" % pipes.quote(mount_folder))

    def _umount_nvram_folder(self, mount_path):
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

    def _detach_loop_device(self):
        loop_dev = find_loop_device_path_by_nvram_install_path(self.nvram_install_path)

        if loop_dev:
            if os.path.exists(loop_dev):
                r, o, e = bash.bash_roe("losetup -d %s" % pipes.quote(loop_dev))
                if r != 0:
                    logger.warn("Warning: Failed to detach loop device %s: %s" % (loop_dev, e))

# use for libvirt
def build_nvram_fd_path(vm_uuid):
    nvram_fd_path = '/var/lib/libvirt/qemu/nvram/%s.fd' % vm_uuid

    nvram_folder_path = build_nvram_mount_folder_path(vm_uuid)
    if os.path.exists(nvram_folder_path):
        nvram_fd_path = os.path.join(nvram_folder_path, '%s.fd' % vm_uuid)
    return nvram_fd_path

# /var/lib/libvirt/qemu/nvram/{vm_uuid} is a folder for NvRam type volume
def build_nvram_mount_folder_path(vm_uuid):
    # type: (str) -> str
    return "/var/lib/libvirt/qemu/nvram/%s" % vm_uuid

def extract_vm_uuid_from_nvram_mount_folder_path(nvram_mount_folder_path):
    # type: (str) -> str
    return os.path.basename(nvram_mount_folder_path.rstrip('/'))

def cleanup_nvram_links_if_needed(install_path):
    # type: (str) -> None
    if not is_nvram_install_path(install_path):
        return
    
    extension = LocalNvRamVmExtensions()
    extension.nvram_install_path = install_path
    extension.cleanup_nvram_after_vm_stop()

def is_nvram_install_path(install_path):
    # type: (str) -> bool
    # install_path format is ".../nvRam/acct-{account_uuid}/vol-{volume_uuid}/{volume_uuid}.raw"
    normalized_path = os.path.normpath(install_path)
    path_parts = normalized_path.split(os.sep)
    if len(path_parts) >= 4:
        return path_parts[-4] == 'nvRam'
    return False

def find_loop_device_path_by_nvram_install_path(nvram_install_path):
    # type: (str) -> str
    # if loop_device_path not found, return ''
    if not nvram_install_path:
        return ''

    target_raw_path = os.path.abspath(nvram_install_path)
    loop_dev_path = ''
    loop_backing_files = glob.glob('/sys/class/block/loop*/loop/backing_file')
    for bf_path in loop_backing_files:
        try:
            with open(bf_path, 'r') as f:
                if f.read().strip() == target_raw_path:
                    loop_name = bf_path.split('/')[4] # ex: loop0
                    loop_dev_path = "/dev/%s" % loop_name
                    break
        except (IOError, OSError):
            continue

    return loop_dev_path

def find_vm_uuid_by_nvram_install_path(nvram_install_path):
    # type: (str) -> str
    # if vm_uuid not found, return ''

    # /vms_ds/nvRam/acct-{account_uuid}/vol-{volume_uuid}/{volume_uuid}.raw  =>  /dev/loop0
    loop_dev_path = find_loop_device_path_by_nvram_install_path(nvram_install_path)
    if not loop_dev_path:
        return ''

    # /dev/loop0  =>  /var/lib/libvirt/qemu/nvram/{vm_uuid}
    mount_folder = ''
    if os.path.exists('/proc/self/mountinfo'):
        with open('/proc/self/mountinfo', 'r') as f:
            for line in f:
                parts = line.split()
                try:
                    sep_index = parts.index('-')
                    source_device = parts[sep_index + 2]
                    if source_device == loop_dev_path:
                        mount_folder = parts[4]
                        break
                except (ValueError, IndexError):
                    continue

    if not mount_folder:
        return ''

    return extract_vm_uuid_from_nvram_mount_folder_path(mount_folder)

def find_nvram_install_path_by_mount_folder(vm_uuid):
    # type: (str) -> str
    device_node = None
    if not os.path.exists('/proc/self/mountinfo'):
        return ''

    mount_folder = build_nvram_mount_folder_path(vm_uuid)
    # /var/lib/libvirt/qemu/nvram/{vm_uuid}  =>  /dev/loop0
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

    if not device_node or not device_node.startswith('/dev/loop'):
        return ''

    # /dev/loop0  =>  ex:/vms_ds/nvRam/acct-{account_uuid}/vol-{volume_uuid}/{volume_uuid}.raw
    loop_name = os.path.basename(device_node)  # ex: 'loop0'
    backing_file_path = "/sys/class/block/%s/loop/backing_file" % loop_name

    if os.path.exists(backing_file_path):
        with open(backing_file_path, 'r') as f:
            raw_path = f.read().strip()
            return os.path.abspath(raw_path) if raw_path else ''
    return ''

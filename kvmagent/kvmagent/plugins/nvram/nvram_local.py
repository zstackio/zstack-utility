
import glob
import os
import os.path
import shlex

from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

class LocalNvRamVmExtensions(object):
    def __init__(self):
        self.nvram_volume = None
        self.vm_uuid = ''

    def prepare_nvram_before_vm_start(self):
        nvram_install_path = self.nvram_volume.installPath  # type: str

        if self.vm_uuid == '':
            raise Exception("invalid vm_uuid: %s" % self.vm_uuid)

        loop_device_path = self._find_loop_block_device_by_file(nvram_install_path)
        if loop_device_path is None:
            loop_device_path = self._make_nvram_to_block_device(nvram_install_path)

        if not self._check_raw_has_file_system(nvram_install_path):
            self._make_ext4_nvram_filesystem(nvram_install_path)

        self._prepare_vm_nvram_folder(loop_device_path)

    def _find_loop_block_device_by_file(self, nvram_install_path):
        expected = os.path.abspath(nvram_install_path)
        for sys_path in glob.glob("/sys/class/block/loop*/loop/backing_file"):
            try:
                with open(sys_path, "r") as f:
                    backing = os.path.abspath(f.read().strip())
                if backing == expected:
                    dev_name = sys_path.split("/")[-3]  # ex: loop0
                    return "/dev/%s" % dev_name
            except IOError:
                continue
        return None

    def _make_nvram_to_block_device(self, nvram_install_path):
        cmd = "losetup --find --show '%s'" % shlex.quote(nvram_install_path)
        loop_dev = bash.bash_o(cmd).strip() # type: str
        if not loop_dev:
            raise Exception("Failed to setup loop device for %s" % nvram_install_path)
        return loop_dev

    def _check_raw_has_file_system(self, nvram_install_path):
        lines = bash.bash_o("blkid -p -o export '%s'" % nvram_install_path).splitlines() # type: str
        info = {}
        for line in lines:
            if '=' in line:
                k, v = line.split('=', 1)
                info[k.strip()] = v.strip()
        is_ext4 = info.get('TYPE') == 'ext4'
        is_label_ok = info.get('LABEL') == 'VM_NVRAM'
        is_fs = info.get('USAGE') == 'filesystem'
        return is_ext4 and is_label_ok and is_fs

    def _make_ext4_nvram_filesystem(self, nvram_install_path):
        cmd = "mkfs.ext4 -F -L VM_NVRAM '%s'" % nvram_install_path
        ret = bash.bash_r(cmd) # type: str
        if ret != 0:
            raise Exception("Failed to format ext4 on %s" % nvram_install_path)

    def _prepare_vm_nvram_folder(self, loop_device_path):
        '''
        :type loop_device_path: str
        '''
        mount_path = "/var/lib/libvirt/qemu/nvram/%s" % self.vm_uuid

        if not os.path.exists(mount_path):
            bash.bash_r("mkdir -p %s" % shlex.quote(mount_path))

        is_mounted = False
        with open('/proc/mounts', 'r') as f:
            is_mounted = any(
                len(parts) >= 2 and parts[1] == mount_path
                for parts in (line.split() for line in f)
            )

        if not is_mounted:
            ret = bash.bash_r("mount -t ext4 %s %s" % (shlex.quote(loop_device_path), shlex.quote(mount_path)))
            if ret != 0:
                raise Exception("failed to mount %s to %s" % (loop_device_path, mount_path))

        bash.bash_r("chmod 750 %s" % shlex.quote(mount_path))
        bash.bash_r("chown qemu:qemu %s" % shlex.quote(mount_path))

    def cleanup_nvram_after_vm_stop(self):
        if self.vm_uuid == '':
            raise Exception("invalid vm_uuid: %s" % self.vm_uuid)

        # if save in nvram/{vm_uuid}.fd, it will be delete
        fd_path = "/var/lib/libvirt/qemu/nvram/%s.fd" % self.vm_uuid
        linux.rm_file_checked(fd_path)

        mount_folder = "/var/lib/libvirt/qemu/nvram/%s" % self.vm_uuid
        if os.path.exists(mount_folder):
            # DO NOT delete nvram raw file: it will save in local primary storage
            # MN will delete nvram volume by other command if needed
            nvram_install_path = self._find_nvram_raw_path_by_mount_folder(mount_folder)
            self._umount_nvram_folder(mount_folder)
            if nvram_install_path:
                self._detach_loop_device_by_file(nvram_install_path)
            if os.path.exists(mount_folder): # double check after umount
                bash.bash_r("rmdir %s" % shlex.quote(mount_folder))

    def _find_nvram_raw_path_by_mount_folder(self, mount_folder):
        device_node = None
        if not os.path.exists('/proc/self/mountinfo'):
            return None

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
            return None

        # /dev/loop0  =>  ex:/vms_ds/nvRam/acct-{account_uuid}/vol-{volume_uuid}/{volume_uuid}.raw
        loop_name = os.path.basename(device_node)  # ex: 'loop0'
        backing_file_path = "/sys/class/block/%s/loop/backing_file" % loop_name

        if os.path.exists(backing_file_path):
            with open(backing_file_path, 'r') as f:
                raw_path = f.read().strip()
                return os.path.abspath(raw_path) if raw_path else None
        return None

    def _umount_nvram_folder(self, mount_path):
        is_mounted = False
        if os.path.exists('/proc/mounts'):
            with open('/proc/mounts', 'r') as f:
                is_mounted = any(
                    len(parts) >= 2 and parts[1] == mount_path
                    for parts in (line.split() for line in f)
                )

        if is_mounted:
            ret = bash.bash_r("umount %s" % shlex.quote(mount_path))
            if ret != 0:
                bash.bash_r("umount -l %s" % shlex.quote(mount_path))

    def _detach_loop_device_by_file(self, nvram_install_path):
        loop_dev = self._find_loop_block_device_by_file(nvram_install_path)

        if loop_dev:
            if os.path.exists(loop_dev):
                r, o, e = bash.bash_roe("losetup -d %s" % shlex.quote(loop_dev))
                if r != 0:
                    logger.warn("Warning: Failed to detach loop device %s: %s" % (loop_dev, e))

def build_nvram_fd_path(vm_uuid):
    nvram_fd_path = '/var/lib/libvirt/qemu/nvram/%s.fd' % vm_uuid

    if os.path.exists('/var/lib/libvirt/qemu/nvram/%s' % vm_uuid):
        # /var/lib/libvirt/qemu/nvram/{vm_uuid} is a folder for NvRam type volume
        nvram_fd_path = '/var/lib/libvirt/qemu/nvram/%s/%s.fd' % (vm_uuid, vm_uuid)
    return nvram_fd_path


import glob
import os
import os.path
import pipes

from kvmagent.plugins.nvram import nvram_common

from zstacklib.utils import bash
from zstacklib.utils import log

logger = log.get_logger(__name__)

class LocalNvRamVmExtensions(object):
    def __init__(self):
        self.vm_uuid = ''
        self.nvram_install_path = ''

    def prepare_nvram_before_vm_start(self):
        if self.vm_uuid == '':
            raise Exception("invalid vm_uuid: %s" % self.vm_uuid)
        if not self.nvram_install_path:
            raise Exception("nvram_install_path is not set")

        loop_device_path = find_loop_device_path_by_nvram_install_path(self.nvram_install_path)
        if not loop_device_path:
            loop_device_path = self._make_nvram_to_block_device()

        if not nvram_common.check_raw_has_file_system(self.nvram_install_path):
            nvram_common.make_ext4_nvram_filesystem(self.nvram_install_path)

        mount_folder = nvram_common.build_nvram_mount_folder_path(self.vm_uuid)
        nvram_common.prepare_vm_nvram_folder(loop_device_path, mount_folder)

    def _make_nvram_to_block_device(self):
        cmd = "losetup --find --show %s" % pipes.quote(self.nvram_install_path)
        loop_dev = bash.bash_o(cmd).strip() # type: str
        if not loop_dev:
            raise Exception("Failed to setup loop device for %s" % self.nvram_install_path)
        return loop_dev

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
    mount_folder = nvram_common.find_mount_folder_by_source_path(loop_dev_path)
    if not mount_folder:
        return ''

    return nvram_common.extract_vm_uuid_from_nvram_mount_folder_path(mount_folder)

def detach_loop_device(loop_path):
    # type: (str) -> None
    if loop_path:
        if os.path.exists(loop_path):
            r, _, e = bash.bash_roe("losetup -d %s" % pipes.quote(loop_path))
            if r != 0:
                logger.warn("Warning: Failed to detach loop device %s: %s" % (loop_path, e))

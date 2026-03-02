
import os
import os.path
import pipes

from kvmagent.plugins.nvram import nvram_common, nvram_sblk, nvram_local

from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

class NvRamVmExtensions(object):
    def __init__(self):
        self.nvram_volume = None
        self.vm_uuid = ''
        self.nvram_install_path = ''

    def prepare(self):
        if not self.nvram_install_path and self.nvram_volume is not None:
            self.nvram_install_path = self.nvram_volume.installPath  # type: str
        if not self.nvram_install_path:
            raise Exception("nvram_install_path is not set")

        if nvram_sblk.is_sharedblock_install_path(self.nvram_install_path):
            extension = nvram_sblk.SblkNvRamVmExtensions()
            extension.vm_uuid = self.vm_uuid
            extension.nvram_install_path = self.nvram_install_path
            extension.prepare_nvram_before_vm_start()
        else:
            extension = nvram_local.LocalNvRamVmExtensions()
            extension.vm_uuid = self.vm_uuid
            extension.nvram_install_path = self.nvram_install_path
            extension.prepare_nvram_before_vm_start()

    def cleanup(self):
        if not self.vm_uuid:
            if not self.nvram_install_path:
                raise Exception('vm_uuid and nvram_install_path in NvRamVmExtensions cannot both be empty.')
            is_sblk = nvram_sblk.is_sharedblock_install_path(self.nvram_install_path)
            if not is_sblk and not nvram_common.is_nvram_install_path(self.nvram_install_path):
                return

            if is_sblk:
                self.vm_uuid = nvram_sblk.find_vm_uuid_by_sharedblock_install_path(self.nvram_install_path)
            else: # expect local storage
                self.vm_uuid = nvram_local.find_vm_uuid_by_nvram_install_path(self.nvram_install_path)

        if not self.vm_uuid:
            logger.debug("skip nvram cleanup: cannot determine vm_uuid from install path %s" % self.nvram_install_path)
            return

        # if save in nvram/{vm_uuid}.fd, it will be deleted
        fd_path = "/var/lib/libvirt/qemu/nvram/%s.fd" % self.vm_uuid
        linux.rm_file_checked(fd_path)

        mount_folder = nvram_common.build_nvram_mount_folder_path(self.vm_uuid)
        if os.path.exists(mount_folder):
            logger.debug('cleanup nvram file for VM: %s' % self.vm_uuid)
            # DO NOT delete nvram raw file: it will save in local primary storage
            # MN will delete nvram volume by other command if needed
            source_path = nvram_common.find_source_path_by_mount_folder(mount_folder)
            nvram_common.umount_nvram_folder(mount_folder)

            if os.path.exists(mount_folder): # double check after umount
                bash.bash_r("rmdir %s" % pipes.quote(mount_folder))

            if not source_path:
                return
            
            if source_path.startswith('/dev/loop'):
                nvram_local.detach_loop_device(source_path)
            elif nvram_sblk.is_sharedblock_device(source_path):
                nvram_sblk.deactivate_sharedblock_nvram_volume_if_needed(source_path, self.vm_uuid)

def cleanup_nvram_links_if_needed(install_path):
    # type: (str) -> None
    if not nvram_common.is_nvram_install_path(install_path):
        return
    
    extension = NvRamVmExtensions()
    extension.nvram_install_path = install_path
    extension.cleanup()

# use for libvirt
def build_nvram_fd_path(vm_uuid):
    nvram_fd_path = '/var/lib/libvirt/qemu/nvram/%s.fd' % vm_uuid

    nvram_folder_path = nvram_common.build_nvram_mount_folder_path(vm_uuid)
    if os.path.exists(nvram_folder_path):
        nvram_fd_path = os.path.join(nvram_folder_path, '%s.fd' % vm_uuid)
    return nvram_fd_path

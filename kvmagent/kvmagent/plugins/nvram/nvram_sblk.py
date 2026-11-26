import pipes

from kvmagent.plugins import shared_block_plugin
from kvmagent.plugins.nvram import nvram_common
from zstacklib.utils import bash, log, linux, lvm

logger = log.get_logger(__name__)

class SblkNvRamVmExtensions(object):
    def __init__(self):
        self.vm_uuid = ''
        self.nvram_install_path = ''  # format: 'sharedblock://{ps.uuid}/{volume.uuid}'
        self.local_install_path = ''

    def prepare_nvram_before_vm_start(self):
        if self.vm_uuid == '':
            raise Exception("invalid vm_uuid: %s" % self.vm_uuid)
        if not self.nvram_install_path:
            raise Exception("nvram_install_path is not set")

        self.local_install_path = translate_absolute_path_from_install_path(self.nvram_install_path)
        if not nvram_common.check_raw_has_file_system(self.local_install_path):
            nvram_common.make_ext4_nvram_filesystem(self.local_install_path)

        mount_folder = nvram_common.build_nvram_mount_folder_path(self.vm_uuid)
        nvram_common.prepare_vm_nvram_folder(self.local_install_path, mount_folder)

# sharedblock://xxx/yyy => /dev/xxx/yyy
def translate_absolute_path_from_install_path(install_path):
    # type: (str) -> str
    return shared_block_plugin.translate_absolute_path_from_install_path(install_path)

def is_sharedblock_install_path(install_path):
    # type: (str) -> bool
    return install_path and install_path.startswith('sharedblock://')

def find_vm_uuid_by_sharedblock_install_path(install_path):
    # type: (str) -> str
    dev_path = translate_absolute_path_from_install_path(install_path) # /dev/xxx/yyy
    mount_folder = nvram_common.find_mount_folder_by_source_path(dev_path) # /var/lib/libvirt/qemu/nvram/{vm_uuid}
    if not mount_folder:
        return ''
    return nvram_common.extract_vm_uuid_from_nvram_mount_folder_path(mount_folder)

def is_sharedblock_device(dev_path):
    # type: (str) -> bool
    lock_type = bash.bash_o("lvs --noheading --nolocking -t %s -ovg_lock_type" % pipes.quote(dev_path)).strip()  # type: str
    return "sanlock" in lock_type

def deactivate_sharedblock_nvram_volume_if_needed(dev_path, vm_uuid):
    # type: (str, str) -> None
    logger.debug("deactivating sharedblock nvram volume %s" % dev_path)

    used_process = linux.linux_lsof(dev_path)  # type: str
    if not used_process:
        try:
            lvm.deactive_lv(dev_path, False)
            logger.debug("deactivated sharedblock nvram volume %s for happened on vm %s success" % (dev_path, vm_uuid))
        except Exception as e:
            logger.warn("deactivate sharedblock nvram volume %s for happened on vm %s failed, %s" % (dev_path, vm_uuid, str(e)))
    else:
        logger.info("vm: %s, sharedblock nvram volume %s still used: %s, skip to deactivate" % (vm_uuid, dev_path, used_process))


from kvmagent.plugins import shared_block_plugin
from kvmagent.plugins.nvram import nvram_common
from zstacklib.utils import log

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

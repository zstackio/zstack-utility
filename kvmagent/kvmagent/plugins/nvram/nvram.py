import errno
import os
import os.path
import pipes
import time

from kvmagent.plugins.nvram import nvram_common, nvram_sblk, nvram_local
from kvmagent.plugins.vms import vm_host_file

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
        elif nvram_common.is_nvram_install_path(self.nvram_install_path):
            extension = nvram_local.LocalNvRamVmExtensions()
            extension.vm_uuid = self.vm_uuid
            extension.nvram_install_path = self.nvram_install_path
            extension.prepare_nvram_before_vm_start()
        elif nvram_common.check_nvram_vm_host_file_path_format(self.nvram_install_path):
            NvRamHostFile().prepare(self.vm_uuid, self.nvram_install_path)
        else:
            raise Exception("invalid nvram_install_path: " + self.nvram_install_path)

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

        # for NvRam host file
        NvRamHostFile().cleanup(self.vm_uuid)

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

class NvRamHostFile(object):
    def __init__(self):
        pass

    def prepare(self, vm_uuid, install_path):
        # type: (str, str) -> None
        expect_vm_uuid = nvram_common.extract_vm_uuid_from_nvram_vm_host_file_path(install_path)
        if expect_vm_uuid != vm_uuid:
            raise Exception('invalid nvram vm host file path ' + install_path)

        base_dir = os.path.dirname(install_path)
        try:
            os.makedirs(base_dir)
        except OSError as e:
            if e.errno != errno.EEXIST:  # ignore folder already exists error
                raise

        token_path = nvram_common.build_nvram_delete_token_file_path(vm_uuid)
        if os.path.isfile(token_path):
            os.remove(token_path)
            logger.debug('remove nvram delete token in %s' % token_path)

    def cleanup(self, vm_uuid):
        # type: (str) -> None
        # add 'delete' token with timestamp (milliseconds)
        token_path = nvram_common.build_nvram_delete_token_file_path(vm_uuid)
        token_dir = os.path.dirname(token_path)
        if not os.path.isdir(token_dir):
            return
        timestamp_ms = int(time.time() * 1000)
        with open(token_path, 'w') as fs:
            fs.write('%d\n' % timestamp_ms)
            logger.debug('add nvram delete token with timestamp %d in %s' % (timestamp_ms, token_path))

    def read_file(self, to):
        # type: (vm_host_file.VmHostFileTO) -> vm_host_file.VmHostFileTO
        result = vm_host_file.VmHostFileTO()
        result.path = to.path
        result.type = to.type

        if not nvram_common.check_nvram_vm_host_file_path_format(result.path):
            result.error = 'invalid nvram vm host file path ' + result.path
            return result

        # Check file size and choose appropriate reading method
        # If file size > 10KB, use read_vm_host_file_targz, else read_vm_host_file_base64
        try:
            file_size = os.path.getsize(result.path)
            if file_size > 10 * 1024:  # 10KB
                vm_host_file.read_vm_host_file_targz(result)
            else:
                vm_host_file.read_vm_host_file_base64(result)
        except OSError as e:
            result.error = 'failed to read nvram file: ' + str(e)
            logger.warning('failed to read nvram file %s: %s' % (result.path, str(e)))

        return result

    def write_file(self, to):
        # type: (vm_host_file.VmHostFileTO) -> None
        if not nvram_common.check_nvram_vm_host_file_path_format(to.path):
            raise Exception('invalid nvram vm host file path ' + to.path)
        vm_host_file.write_vm_host_file(to)

def cleanup_nvram_links_if_needed(install_path):
    # type: (str) -> None
    if not nvram_common.is_nvram_install_path(install_path):
        return

    extension = NvRamVmExtensions()
    extension.nvram_install_path = install_path
    extension.cleanup()

# use for libvirt
def build_nvram_fd_path(vm_uuid, need_register_nvram = False):
    # type: (str, bool) -> str
    nvram_fd_path = '/var/lib/libvirt/qemu/nvram/%s.fd' % vm_uuid
    if not need_register_nvram:
        return nvram_fd_path

    nvram_host_file_path = nvram_common.build_nvram_vm_host_file_path(vm_uuid)
    if os.path.exists(os.path.dirname(nvram_host_file_path)):
        return nvram_host_file_path

    nvram_folder_path = nvram_common.build_nvram_mount_folder_path(vm_uuid)
    if os.path.exists(nvram_folder_path):
        nvram_fd_path = os.path.join(nvram_folder_path, '%s.fd' % vm_uuid)
    return nvram_fd_path

from zstacklib.utils import linux
from zstacklib.utils import qcow2


class PlainSharedBlockVolumeDriver(object):
    # Storage plugins retain LV creation, activation, locks and rollback.
    # Drivers provide only data operations and format-specific allocation requirements.
    def __init__(self, cmd):
        self.cmd = cmd

    def validate_create_request(self):
        pass

    def required_allocation_size(self, volume_size):
        return int(volume_size)

    def validate_existing_target(self, target_path):
        # Preserve the ordinary create path's acceptance of an existing LV.
        pass

    def create_empty(self, target_path, volume_size, backing_path=None, qcow2_options=''):
        if backing_path:
            return linux.qcow2_create_with_backing_file_and_option(backing_path, target_path, qcow2_options)
        return linux.qcow2_create_with_option(target_path, volume_size, qcow2_options, discard_on_metadata=False)

    def zero_fill_if_requested(self, target_path):
        if self.cmd.zeroFilled:
            linux.qcow2_fill(0, 1048576, target_path)

    def create_with_backing(self, backing_path, target_path, volume_size, qcow2_options):
        return linux.qcow2_clone_with_option(
            backing_path, target_path, qcow2_options, self.cmd.virtualSize if self.cmd.virtualSize else '')

    def resize(self, target_path, volume_size):
        return linux.qemu_img_resize(target_path, volume_size, 'qcow2', self.cmd.force)

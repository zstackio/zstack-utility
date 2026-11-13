from kvmagent.crypto.shared_block import operations


class LuksSharedBlockVolumeDriver(object):
    def __init__(self, cmd):
        self.cmd = cmd

    def validate_create_request(self):
        operations.validate_create_request(self.cmd)

    def required_allocation_size(self, volume_size):
        # Include the LUKS header in capacity; the storage plugin still performs LV mutations.
        return operations.allocation_size(self.cmd, volume_size)

    def validate_existing_target(self, target_path):
        raise FileExistsError(target_path)

    def create_empty(self, target_path, volume_size, backing_path=None, qcow2_options=''):
        return operations.create_empty(self.cmd, target_path, volume_size, backing_path, qcow2_options)

    def zero_fill_if_requested(self, target_path):
        # The plain zero-fill helper has no LUKS secret and cannot initialize this format.
        pass

    def create_with_backing(self, backing_path, target_path, volume_size, qcow2_options):
        return operations.create_with_backing(self.cmd, backing_path, target_path, volume_size, qcow2_options)

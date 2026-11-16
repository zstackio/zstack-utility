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

    def clone(self, source_path, target_path, volume_size, qcow2_options):
        return operations.clone(self.cmd, source_path, target_path, volume_size, qcow2_options)

    def create_template(self, source_path, target_path, shell):
        return operations.create_template(self.cmd, source_path, target_path)

    def create_template_with_task_daemon(self, source_path, target_path):
        return operations.create_template(self.cmd, source_path, target_path)

    def rebase(self, backing_path, target_path):
        return operations.safe_rebase(self.cmd, backing_path, target_path)

    def rebase_no_check(self, backing_path, target_path):
        return operations.rebase(self.cmd, backing_path, target_path)

    def commit(self, top_path, base_path):
        return operations.commit(self.cmd, top_path, base_path)

    def resize(self, target_path, volume_size):
        return operations.resize(self.cmd, target_path, volume_size)

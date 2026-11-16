from kvmagent.crypto.file_volume import operations


class LuksFileVolumeDriver(object):
    # Keep LUKS independent of Plain so new ordinary writes cannot be inherited.
    def __init__(self, cmd):
        self.cmd = cmd

    def create_empty(self, volume_size=None):
        return operations.create_empty(self.cmd)

    def create_with_backing(self, source_path, target_path):
        return operations.create_with_backing(self.cmd, source_path, target_path)

    def clone(self, source_path, target_path):
        return operations.clone(self.cmd, source_path, target_path, getattr(self.cmd, 'virtualSize', None))

    def create_incremental_template(self, source_path, target_path):
        return operations.clone(self.cmd, source_path, target_path)

    def resize(self, target_path, volume_size):
        return operations.resize(self.cmd, target_path, volume_size)

    def rebase_no_check(self, backing_path, target_path):
        return operations.rebase(self.cmd, backing_path, target_path)

    def rebase(self, backing_path, target_path):
        return operations.safe_rebase(self.cmd, backing_path, target_path)

    def commit(self, top_path, base_path):
        return operations.commit(self.cmd, top_path, base_path)

    def create_template(self, source_path, target_path, **kwargs):
        return operations.create_template(self.cmd, source_path, target_path)

    def create_template_with_task_daemon(self, source_path, target_path):
        return operations.create_template(self.cmd, source_path, target_path)

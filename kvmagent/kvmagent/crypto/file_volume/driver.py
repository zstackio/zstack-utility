from kvmagent.crypto.file_volume import operations


class LuksFileVolumeDriver(object):
    # Keep LUKS independent of Plain so new ordinary writes cannot be inherited.
    def __init__(self, cmd):
        self.cmd = cmd

    def create_empty(self, volume_size=None):
        return operations.create_empty(self.cmd)

    def create_with_backing(self, source_path, target_path):
        return operations.create_with_backing(self.cmd, source_path, target_path)

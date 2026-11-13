from zstacklib.utils import linux


class PlainFileVolumeDriver(object):
    # Drivers perform data operations; plugins retain directories, capacity reporting and rollback.
    def __init__(self, cmd):
        self.cmd = cmd

    def create_empty(self, volume_size=None):
        cmd = self.cmd
        if cmd.volumeFormat == 'raw':
            return linux.raw_create(cmd.installUrl, cmd.size)
        if cmd.backingFile:
            # Local supplies a size; NFS keeps the backing image's size by omitting it.
            if volume_size is None:
                return linux.qcow2_create_with_backing_file_and_cmd(cmd.backingFile, cmd.installUrl, cmd)
            return linux.qcow2_create_with_backing_file_and_cmd(cmd.backingFile, cmd.installUrl, cmd, volume_size)
        return linux.qcow2_create_with_cmd(cmd.installUrl, cmd.size, cmd)

    def create_with_backing(self, source_path, target_path):
        return linux.qcow2_clone_with_cmd(source_path, target_path, self.cmd)

from zstacklib.utils import linux
from zstacklib.utils import qcow2


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

    def clone(self, source_path, target_path):
        return linux.qcow2_clone_with_cmd(source_path, target_path, self.cmd)

    def create_incremental_template(self, source_path, target_path):
        return linux.qcow2_create_with_backing_file_and_option(source_path, target_path)

    def resize(self, target_path, volume_size):
        return linux.qemu_img_resize(target_path, volume_size, 'qcow2', self.cmd.force)

    def rebase_no_check(self, backing_path, target_path):
        return linux.qcow2_rebase_no_check(backing_path, target_path)

    def rebase(self, backing_path, target_path):
        return linux.qcow2_rebase(backing_path, target_path)

    def commit(self, top_path, base_path):
        return linux.qcow2_commit(top_path, base_path)

    def create_template(self, source_path, target_path, **kwargs):
        return linux.create_template(source_path, target_path, **kwargs)

    def create_template_with_task_daemon(self, source_path, target_path):
        return qcow2.create_template_with_task_daemon(source_path, target_path, task_spec=self.cmd)

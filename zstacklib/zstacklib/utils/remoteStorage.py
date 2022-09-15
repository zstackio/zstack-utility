import os
from zstacklib.utils import shell


class RemoteStorage(object):
    def __init__(self, mount_path, volume_mounted_device):
        self.volume_mounted_device = volume_mounted_device
        self.mount_path = mount_path

    def mount(self):
        raise Exception('function mount not be implemented')

    def umount(self):
        raise Exception('function umount not be implemented')

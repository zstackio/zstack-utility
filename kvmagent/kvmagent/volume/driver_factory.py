from kvmagent.volume import driver_registry
from kvmagent.volume.plain_file_driver import PlainFileVolumeDriver
from kvmagent.volume.plain_shared_block_driver import PlainSharedBlockVolumeDriver


def get_file_driver(cmd):
    # Plain is an explicit fallback, not another matching provider.
    return driver_registry.get_driver('file', cmd, PlainFileVolumeDriver)


def get_shared_block_driver(cmd):
    return driver_registry.get_driver('sharedblock', cmd, PlainSharedBlockVolumeDriver)

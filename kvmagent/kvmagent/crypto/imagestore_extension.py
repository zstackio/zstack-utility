from kvmagent.crypto import imagestore


class ImageStoreEncryptionExtension(object):
    @staticmethod
    def prepare_image_add_command(command_line, addons, device_id):
        # A backup parent upload uses the source disk's spec, including device ID zero.
        if device_id is not None:
            addons = {'ImageStoreEncryption': imagestore.backup_encryption_spec(addons, device_id) or {}}
        return imagestore.prepare_command({'kind': 'add', 'addons': addons}, command_line)

    @staticmethod
    def prepare_image_pull_command(command_line, addons):
        return imagestore.prepare_command({'kind': 'pull', 'addons': addons}, command_line)

    @staticmethod
    def prepare_volume_backup_command(command_line, addons, device_id):
        return imagestore.prepare_command(
            {'kind': 'single-backup', 'addons': addons, 'deviceId': device_id}, command_line)

    @staticmethod
    def prepare_batch_backup_command(command_line, addons, backup_args, device_ids):
        return imagestore.prepare_command(
            {'kind': 'batch-backup', 'addons': addons, 'args': backup_args, 'deviceIds': device_ids or ()}, command_line)
